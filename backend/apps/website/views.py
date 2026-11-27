"""Public website content and contact forms, plus their management: the platform admin for the main website,
a pharmacy's own staff for theirs. The scope always comes from the signed-in account, never from the request."""
import json
import os

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsPlatformAdminOrTenantPermission
from apps.audit import services as audit
from apps.core.tenant_context import tenant_context
from apps.core.views import TenantContextMixin
from apps.notifications import inapp
from apps.notifications.services import render_branded_html, send_email
from apps.tenants.models import Pharmacy

from .content import PHARMACY_KEYS, PLATFORM_KEYS, clean
from .models import ContactMessage, SitePage

MAX_CONTENT_BYTES = 200_000
MAX_IMAGE_BYTES = 4 * 1024 * 1024


def _public_tenant(slug):
    if slug is None:
        return None
    t = Pharmacy.objects.filter(slug=slug, status=Pharmacy.Status.ACTIVE).first()
    if t is None:
        raise NotFound()
    return t


def _check_key(tenant, key):
    if key not in (PHARMACY_KEYS if tenant else PLATFORM_KEYS):
        raise NotFound()


class PublicPageView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, key, slug=None):
        tenant = _public_tenant(slug)
        _check_key(tenant, key)
        row = SitePage.objects.filter(tenant=tenant, key=key).first()
        return Response({"content": row.content if row else None})  # null: the website shows its built-in starting content


class ContactIn(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    subject = serializers.CharField(max_length=200)
    message = serializers.CharField(max_length=3000)
    website = serializers.CharField(required=False, allow_blank=True, default="")  # honeypot


class PublicContactView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_write"

    def get_throttles(self):
        return [ScopedRateThrottle()]

    def post(self, request, slug=None):
        tenant = _public_tenant(slug)
        s = ContactIn(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        if data.pop("website"):  # bots fill hidden fields: pretend it worked
            return Response({"received": True}, status=201)
        row = ContactMessage.objects.create(tenant=tenant, **data)
        title, body = f"Website message from {row.name}"[:160], row.subject
        if tenant:
            with tenant_context(tenant):
                inapp.push_staff(tenant.pk, "engagement.manage", None, kind="contact", title=title, body=body, link="/website-contact")
        else:
            inapp.push(inapp.platform_admins(), kind="contact", title=title, body=body, link="/website-contact")
        return Response({"received": True}, status=201)


class Manage(TenantContextMixin, APIView):
    permission_classes = [IsPlatformAdminOrTenantPermission]

    def scope(self):
        user = self.request.user
        return None if user.is_platform_admin else user.tenant


class PagesView(Manage):
    required_permissions = {"GET": "settings.manage"}

    def get(self, request):
        return Response([{"key": p.key, "updated_at": p.updated_at} for p in SitePage.objects.filter(tenant=self.scope())])


class PageView(Manage):
    required_permissions = {"GET": "settings.manage", "PUT": "settings.manage", "DELETE": "settings.manage"}

    def get(self, request, key):
        _check_key(self.scope(), key)
        row = SitePage.objects.filter(tenant=self.scope(), key=key).first()
        return Response({"content": row.content if row else None})

    def put(self, request, key):
        tenant = self.scope()
        _check_key(tenant, key)
        raw = request.data.get("content")
        if len(json.dumps(raw)) > MAX_CONTENT_BYTES:
            raise serializers.ValidationError({"content": "This page is too large. Shorten some text."})
        row, _ = SitePage.objects.update_or_create(tenant=tenant, key=key, defaults={"content": clean(key, raw), "updated_by": request.user})
        audit.record("website.page_saved", actor=request.user, tenant=tenant, target=row, request=request, page=key)
        return Response({"content": row.content})

    def delete(self, request, key):
        tenant = self.scope()
        _check_key(tenant, key)
        SitePage.objects.filter(tenant=tenant, key=key).delete()
        audit.record("website.page_reset", actor=request.user, tenant=tenant, request=request, page=key)
        return Response(status=204)


class ImageView(Manage):
    required_permissions = {"POST": "settings.manage"}
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        f = request.FILES.get("image")
        if f is None or f.size > MAX_IMAGE_BYTES or os.path.splitext(f.name)[1].lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            raise serializers.ValidationError({"image": "Choose a PNG, JPG or WebP picture of 4 MB or less."})
        try:
            serializers.ImageField().run_validation(f)
        except DjangoValidationError:
            raise serializers.ValidationError({"image": "That file is not a picture."})
        f.seek(0)
        folder = f"site-images/{self.scope().pk if self.scope() else 'platform'}"
        name = default_storage.save(f"{folder}/{f.name}", f)
        return Response({"url": default_storage.url(name)}, status=201)


def message_out(m):
    return {"id": m.pk, "name": m.name, "email": m.email, "phone": m.phone, "subject": m.subject, "message": m.message, "status": m.status,
            "staff_note": m.staff_note, "reply": m.reply, "replied_at": m.replied_at, "created_at": m.created_at,
            "handled_by": m.handled_by.full_name if m.handled_by else None}


class MessagesBase(Manage):
    required_permissions = {"GET": "engagement.manage", "POST": "engagement.manage", "PATCH": "engagement.manage", "DELETE": "engagement.manage"}

    def rows(self):
        return ContactMessage.objects.filter(tenant=self.scope()).select_related("handled_by")


class MessagesView(MessagesBase):
    def get(self, request):
        from django.db.models import Q
        qs = self.rows()
        if status := request.query_params.get("status"):
            qs = qs.filter(status=status)
        if term := request.query_params.get("search", "").strip():
            qs = qs.filter(Q(name__icontains=term) | Q(email__icontains=term) | Q(subject__icontains=term) | Q(message__icontains=term))
        pg = PageNumberPagination()
        pg.page_size = 25
        resp = pg.get_paginated_response([message_out(m) for m in pg.paginate_queryset(qs, request)])
        counts = self.rows()
        resp.data["summary"] = {s.value: counts.filter(status=s.value).count() for s in ContactMessage.Status}
        return resp


class MessageIn(serializers.Serializer):
    status = serializers.ChoiceField(choices=ContactMessage.Status.values, required=False)
    staff_note = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class MessageView(MessagesBase):
    def patch(self, request, pk):
        m = get_object_or_404(self.rows(), pk=pk)
        s = MessageIn(data=request.data)
        s.is_valid(raise_exception=True)
        for k, v in s.validated_data.items():
            setattr(m, k, v)
        m.handled_by = request.user
        m.save()
        audit.record("website.message_updated", actor=request.user, tenant=m.tenant, target=m, request=request, status=m.status)
        return Response(message_out(m))

    def delete(self, request, pk):
        m = get_object_or_404(self.rows(), pk=pk)
        audit.record("website.message_deleted", actor=request.user, tenant=m.tenant, target=m, request=request)
        m.delete()
        return Response(status=204)


class ReplyView(MessagesBase):
    def post(self, request, pk):
        m = get_object_or_404(self.rows(), pk=pk)
        reply = serializers.CharField(max_length=3000).run_validation(request.data.get("message"))
        send_email(to=m.email, subject=f"Re: {m.subject}"[:200], text=reply, tenant=m.tenant, template="contact_reply",
                   html_body=render_branded_html(title="Reply to your message", pharmacy=m.tenant, paragraphs=[f"Hello {m.name},", reply],
                                                 details=[("Your subject", m.subject)]))
        m.reply, m.replied_at, m.status, m.handled_by = reply, timezone.now(), ContactMessage.Status.RESOLVED, request.user
        m.save()
        audit.record("website.message_replied", actor=request.user, tenant=m.tenant, target=m, request=request)
        return Response(message_out(m))
