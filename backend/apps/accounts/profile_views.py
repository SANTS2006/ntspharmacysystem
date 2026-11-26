"""Self-service account settings for every signed-in user: profile, picture and email address (password change lives in views.py)."""
import hashlib
import hmac
import os
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.views import TenantContextMixin
from apps.notifications import inapp
from apps.notifications.services import render_branded_html, send_email

from .models import EmailChange, User
from .permissions import IsAuthenticatedAndSettled
from .views import UserSerializer, error

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
AVATAR_TYPES = (".png", ".jpg", ".jpeg", ".webp")


class ProfileIn(serializers.Serializer):
    full_name = serializers.CharField(max_length=200, required=False)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)


class SettingsBase(TenantContextMixin, APIView):
    permission_classes = [IsAuthenticatedAndSettled]


class SensitiveBase(SettingsBase):
    throttle_scope = "sensitive"

    def get_throttles(self):
        return [ScopedRateThrottle()]


class ProfileView(SettingsBase):
    def patch(self, request):
        s = ProfileIn(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        if data:
            for key, value in data.items():
                setattr(request.user, key, value.strip())
            request.user.save(update_fields=list(data))
            audit.record("account.profile_updated", actor=request.user, tenant=request.user.tenant, request=request, fields=sorted(data))
        return Response(UserSerializer(request.user).data)


class AvatarView(SettingsBase):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        f = request.FILES.get("avatar")
        if f is None:
            raise serializers.ValidationError({"avatar": "Choose a picture."})
        if f.size > settings.LOGO_MAX_BYTES:
            raise serializers.ValidationError({"avatar": "The picture must be 2 MB or smaller."})
        if os.path.splitext(f.name)[1].lower() not in AVATAR_TYPES:
            raise serializers.ValidationError({"avatar": "Use a PNG, JPG or WebP picture."})
        try:
            serializers.ImageField().run_validation(f)  # decodes the file: rejects anything that is not really an image
        except DjangoValidationError:
            raise serializers.ValidationError({"avatar": "That file is not a picture."})
        f.seek(0)
        user, old = request.user, request.user.avatar.name
        user.avatar.save(f.name, f, save=False)
        user.save(update_fields=["avatar"])
        if old:
            transaction.on_commit(lambda: user.avatar.storage.delete(old))
        audit.record("account.picture_updated", actor=user, tenant=user.tenant, request=request)
        return Response(UserSerializer(user).data)

    def delete(self, request):
        user, old = request.user, request.user.avatar.name
        if old:
            user.avatar = ""
            user.save(update_fields=["avatar"])
            storage = User._meta.get_field("avatar").storage
            transaction.on_commit(lambda: storage.delete(old))
            audit.record("account.picture_removed", actor=user, tenant=user.tenant, request=request)
        return Response(UserSerializer(user).data)


def _hash(user, email, code):
    return hashlib.sha256(f"{user.pk}:{email}:{code.upper()}:{settings.SECRET_KEY}".encode()).hexdigest()


def _email_taken(user, email):
    return User.objects.filter(tenant=user.tenant, email=email).exclude(pk=user.pk).exists()


class EmailChangeIn(serializers.Serializer):
    new_email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class EmailChangeView(SensitiveBase):
    """Step 1: prove the password, then a code is sent to the NEW address. Nothing changes until it is confirmed."""

    def post(self, request):
        s = EmailChangeIn(data=request.data)
        s.is_valid(raise_exception=True)
        user, new = request.user, s.validated_data["new_email"].strip().lower()
        if not user.has_usable_password() or not user.check_password(s.validated_data["password"]):
            return error("invalid_password", "Your password is incorrect.", 400)
        if new == user.email:
            raise serializers.ValidationError({"new_email": "That is already your email address."})
        if _email_taken(user, new):
            raise serializers.ValidationError({"new_email": "Another account already uses this email address."})
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        now = timezone.now()
        EmailChange.objects.update_or_create(user=user, defaults={
            "new_email": new, "code_hash": _hash(user, new, code), "attempts": 0,
            "expires_at": now + timedelta(minutes=settings.EMAIL_CODE_TTL_MINUTES)})
        tenant = user.tenant
        note = f"Use this code to confirm your new email address. It expires in {settings.EMAIL_CODE_TTL_MINUTES} minutes."
        send_email(to=new, subject=f"Confirm your new email: {code}", text=f"{note}\n\nCode: {code}", tenant=tenant, template="email_change",
                   html_body=render_branded_html(title="Confirm your new email", pharmacy=tenant, paragraphs=[note], code=code))
        warn = f"A change of your account email to {new} was requested. If this was not you, change your password now."
        send_email(to=user.email, subject="Email change requested", text=warn, tenant=tenant, template="email_change_notice")
        return Response({"sent_to": new}, status=202)


class EmailChangeConfirmView(SensitiveBase):
    """Failures are returned, not raised, so the attempt counter survives the request transaction."""

    def post(self, request):
        code = str(request.data.get("code", "")).strip()
        user = request.user
        with transaction.atomic():
            row = EmailChange.objects.select_for_update(of=("self",)).filter(user=user).first()
            if row is None or row.expires_at < timezone.now():
                return error("invalid_code", "That code has expired. Request a new one.", 400)
            if row.attempts >= settings.EMAIL_CODE_MAX_ATTEMPTS:
                return error("too_many_attempts", "Too many incorrect attempts. Request a new code.", 429)
            if not hmac.compare_digest(row.code_hash, _hash(user, row.new_email, code)):
                row.attempts += 1
                row.save(update_fields=["attempts"])
                return error("invalid_code", "That code is incorrect.", 400)
            if _email_taken(user, row.new_email):
                return error("email_taken", "Another account already uses this email address.", 400)
            old, user.email, user.email_verified = user.email, row.new_email, True
            user.save(update_fields=["email", "email_verified"])
            row.delete()
            audit.record("account.email_changed", actor=user, tenant=user.tenant, request=request, old=old, new=user.email)
        inapp.push([user], kind="security", level="success", title="Your email address was changed", body=f"You now sign in with {user.email}.", link="/settings")
        return Response(UserSerializer(user).data)
