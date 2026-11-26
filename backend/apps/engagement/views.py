from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantPermission
from apps.audit import services as audit
from apps.core.fields import TenantPKField
from apps.core.realtime import notify_topic
from apps.core.tenant_context import tenant_context
from apps.core.views import TenantContextMixin
from apps.notifications import inapp
from apps.inventory.selectors import branch_ids_for
from apps.shop.models import Order
from apps.shop.views import IsVerifiedCustomer
from apps.tenants.models import Branch, Pharmacy

from . import services
from .models import Appointment, CustomerInquiry, Feedback, InstitutionalRequest, PharmacyService


class Base(TenantContextMixin):
    permission_classes = [HasTenantPermission]


def page(request, qs, fn):
    pg = PageNumberPagination()
    return pg.get_paginated_response([fn(x) for x in pg.paginate_queryset(qs, request)])


def branch_filter(qs, user, field="branch_id"):
    ids = branch_ids_for(user)
    return qs.filter(**{f"{field}__in": ids}) if ids else qs


# ---------------- services catalogue ----------------
def svc_out(s: PharmacyService, request=None):
    return {"id": s.pk, "name": s.name, "description": s.description, "price": s.price, "is_available": s.is_available, "requires_booking": s.requires_booking,
            "duration_minutes": s.duration_minutes, "capacity": s.capacity, "branches": list(s.branches.values_list("pk", flat=True)),
            "image": request.build_absolute_uri(s.image.url) if request is not None and s.image else None}


class ServiceIn(serializers.ModelSerializer):
    branches = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=Branch.all_objects.none())

    class Meta:
        model = PharmacyService
        fields = ["name", "description", "image", "price", "is_available", "requires_booking", "duration_minutes", "capacity", "branches"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["branches"].child_relation.queryset = Branch.objects.all()  # bound per request: tenant-scoped

    def validate_name(self, v):
        qs = PharmacyService.objects.filter(name__iexact=v.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A service with this name already exists.")
        return v.strip()

    def validate(self, a):
        if a.get("duration_minutes", 30) < 5 or a.get("capacity", 1) < 1:
            raise serializers.ValidationError("Duration must be at least 5 minutes and capacity at least 1.")
        return a


class ServicesView(Base, APIView):
    required_permissions = {"GET": "service.manage", "POST": "service.manage"}
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        return Response([svc_out(s, request) for s in PharmacyService.objects.prefetch_related("branches")])

    def post(self, request):
        s = ServiceIn(data=request.data)
        s.is_valid(raise_exception=True)
        svc = s.save()
        audit.record("service.created", actor=request.user, target=svc, request=request)
        return Response(svc_out(svc, request), status=201)


class ServiceDetailView(Base, APIView):
    required_permission = "service.manage"
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def patch(self, request, pk):
        svc = get_object_or_404(PharmacyService, pk=pk)
        s = ServiceIn(svc, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        svc = s.save()
        audit.record("service.updated", actor=request.user, target=svc, request=request, fields=sorted(s.validated_data))
        return Response(svc_out(svc, request))


class PublicServicesView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        t = Pharmacy.objects.filter(slug=slug, status="active").first()
        if t is None:
            raise NotFound()
        with tenant_context(t):
            return Response([svc_out(s, request) for s in PharmacyService.objects.filter(is_available=True).prefetch_related("branches")])


# ---------------- appointments ----------------
def appt_out(a: Appointment, staff=False):
    d = {"id": a.pk, "service": a.service.name, "service_id": a.service_id, "branch": a.branch_id, "start_at": a.start_at, "end_at": a.end_at, "status": a.status, "customer_note": a.customer_note, "staff_note": a.staff_note}
    if staff:
        d.update(customer_name=a.customer.full_name, customer_phone=a.customer.phone, customer_email=a.customer.email)
    return d


class MyAppointmentsView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]

    def get(self, request):
        return page(request, Appointment.objects.filter(customer=request.user).select_related("service"), appt_out)

    def post(self, request):
        svc = get_object_or_404(PharmacyService, pk=request.data.get("service"))
        branch = get_object_or_404(Branch, pk=request.data.get("branch"))
        start = serializers.DateTimeField().run_validation(request.data.get("start_at"))
        return Response(appt_out(services.book(customer=request.user, service=svc, branch=branch, start_at=start, note=str(request.data.get("note", "")))), status=201)


class MyAppointmentCancelView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]

    def post(self, request, pk):
        get_object_or_404(Appointment, pk=pk, customer=request.user)
        return Response(appt_out(services.customer_cancel(pk, customer=request.user)))


class StaffAppointmentsView(Base, APIView):
    required_permission = "engagement.manage"

    def get(self, request):
        qs = branch_filter(Appointment.objects.select_related("service", "customer"), request.user)
        for k, f in (("status", "status"), ("date_from", "start_at__date__gte"), ("date_to", "start_at__date__lte")):
            if request.query_params.get(k):
                qs = qs.filter(**{f: request.query_params[k]})
        return page(request, qs, lambda a: appt_out(a, True))


class StaffAppointmentStatusView(Base, APIView):
    required_permission = "engagement.manage"

    def post(self, request, pk):
        a = get_object_or_404(branch_filter(Appointment.objects.all(), request.user), pk=pk)
        return Response(appt_out(services.set_status(a.pk, str(request.data.get("status", "")), actor=request.user, note=str(request.data.get("note", ""))), True))


# ---------------- inquiries and feedback (customers) ----------------
class MyInquiriesView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]

    def get(self, request):
        return page(request, CustomerInquiry.objects.filter(customer=request.user), lambda i: {"id": i.pk, "kind": i.kind, "message": i.message, "status": i.status, "response": i.response, "created_at": i.created_at})

    def post(self, request):
        kind, msg = request.data.get("kind", "inquiry"), str(request.data.get("message", "")).strip()
        if kind not in {k.value for k in CustomerInquiry.Kind} or not msg:
            raise serializers.ValidationError({"message": "Choose a request type and enter a message."})
        branch = Branch.objects.filter(pk=request.data["branch"]).first() if request.data.get("branch") else None
        i = CustomerInquiry.objects.create(customer=request.user, kind=kind, message=msg[:1000], branch=branch)
        notify_topic(i.tenant_id, branch.pk if branch else None, "orders", "inquiry.created", {"id": i.pk, "kind": i.kind})
        inapp.push_staff(i.tenant_id, "engagement.manage", branch.pk if branch else None, kind="inquiry", title=f"New customer {i.kind}",
                         body=f"{request.user.full_name}: {msg[:200]}", link="/engagement")
        return Response({"id": i.pk}, status=201)


class MyFeedbackView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]

    def get(self, request):
        return page(request, Feedback.objects.filter(customer=request.user), lambda f: {"id": f.pk, "rating": f.rating, "comment": f.comment, "response": f.response, "created_at": f.created_at})

    def post(self, request):
        rating = serializers.IntegerField(min_value=1, max_value=5).run_validation(request.data.get("rating"))
        order = Order.objects.filter(pk=request.data["order"], customer=request.user).first() if request.data.get("order") else None
        if request.data.get("order") and order is None:
            raise NotFound()
        if order and Feedback.objects.filter(order=order, customer=request.user).exists():
            raise serializers.ValidationError({"order": "You already left feedback for this order."})
        f = Feedback.objects.create(customer=request.user, order=order, branch=order.branch if order else None, rating=rating, comment=str(request.data.get("comment", ""))[:1500])
        return Response({"id": f.pk}, status=201)


class StaffInquiriesView(Base, APIView):
    required_permission = "engagement.manage"

    def get(self, request):
        qs = CustomerInquiry.objects.select_related("customer")
        ids = branch_ids_for(request.user)
        if ids:
            qs = qs.filter(branch_id__in=ids)
        return page(request, qs, lambda i: {"id": i.pk, "kind": i.kind, "message": i.message, "status": i.status, "response": i.response, "customer": i.customer.full_name, "phone": i.customer.phone})


class StaffInquiryRespondView(Base, APIView):
    required_permission = "engagement.manage"

    def post(self, request, pk):
        qs = CustomerInquiry.objects.select_related("customer")
        ids = branch_ids_for(request.user)
        i = get_object_or_404(qs.filter(branch_id__in=ids) if ids else qs, pk=pk)
        resp = str(request.data.get("response", "")).strip()
        if not resp:
            raise serializers.ValidationError({"response": "Enter a response."})
        i.response, i.status, i.handled_by = resp[:1000], "answered", request.user
        i.save()
        services._mail(i.customer.email, "Reply to your enquiry", resp, "inquiry_reply")
        inapp.push([i.customer], kind="inquiry", level="success", title="The pharmacy replied to your enquiry", body=resp[:300], link="/care")
        audit.record("inquiry.answered", actor=request.user, target=i)
        return Response({"id": i.pk, "status": i.status})


class StaffFeedbackView(Base, APIView):
    required_permission = "engagement.manage"

    def get(self, request):
        qs = branch_filter(Feedback.objects.select_related("customer"), request.user)
        out = page(request, qs, lambda f: {"id": f.pk, "rating": f.rating, "comment": f.comment, "status": f.status, "response": f.response, "customer": f.customer.full_name, "branch": f.branch_id, "created_at": f.created_at})
        from django.db.models import Avg
        out.data["average_rating"] = qs.aggregate(a=Avg("rating"))["a"]
        return out


class StaffFeedbackRespondView(Base, APIView):
    required_permission = "engagement.manage"

    def post(self, request, pk):
        f = get_object_or_404(branch_filter(Feedback.objects.select_related("customer"), request.user), pk=pk)
        resp = str(request.data.get("response", "")).strip()
        f.status, f.response, f.handled_by = "reviewed", resp[:1000], request.user
        f.save()
        if resp:
            services._mail(f.customer.email, "Thank you for your feedback", resp, "feedback_reply")
        return Response({"id": f.pk, "status": f.status})


# ---------------- institutional requests ----------------
class InstitutionalIn(serializers.Serializer):
    organisation = serializers.CharField(max_length=200)
    contact_person = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)
    service_required = serializers.CharField(max_length=200)
    products_required = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    quantity = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    location = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    requested_date = serializers.DateField(required=False, allow_null=True)
    details = serializers.CharField(max_length=1500, required=False, allow_blank=True, default="")
    website = serializers.CharField(required=False, allow_blank=True, default="")  # honeypot


class PublicInstitutionalView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_write"

    def get_throttles(self):
        return [ScopedRateThrottle()]

    def post(self, request, slug):
        t = Pharmacy.objects.filter(slug=slug, status="active").first()
        if t is None:
            raise NotFound()
        s = InstitutionalIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        if d.pop("website"):
            return Response({"received": True}, status=201)
        with tenant_context(t):
            r = InstitutionalRequest.objects.create(**d)
            audit.record("institutional_request.created", actor=None, tenant=t, target=r)
            notify_topic(t.pk, None, "orders", "institutional_request.created", {"id": r.pk, "kind": "institutional"})
            inapp.push_staff(t.pk, "engagement.manage", None, kind="inquiry", title=f"Bulk request from {r.organisation}", body=r.service_required, link="/engagement")
            services._mail(r.email, f"We received your request: {r.service_required}", f"Thank you {r.contact_person}. {t.name} received your request and will respond to {r.email}.", "institutional_ack")
        return Response({"received": True, "reference": r.pk}, status=201)


def inst_out(r):
    return {"id": r.pk, "organisation": r.organisation, "contact_person": r.contact_person, "email": r.email, "phone": r.phone, "service_required": r.service_required,
            "products_required": r.products_required, "quantity": r.quantity, "location": r.location, "requested_date": r.requested_date, "details": r.details,
            "status": r.status, "response": r.response, "created_at": r.created_at}


class StaffInstitutionalView(Base, APIView):
    required_permission = "engagement.manage"

    def get(self, request):
        qs = InstitutionalRequest.objects.all()
        if request.user.is_branch_scoped:  # branch staff see requests addressed to their branch or to nobody in particular
            from django.db.models import Q
            qs = qs.filter(Q(branch_id=request.user.branch_id) | Q(branch__isnull=True))
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return page(request, qs, inst_out)


class StaffInstitutionalRespondView(Base, APIView):
    required_permission = "engagement.manage"

    def post(self, request, pk):
        r = get_object_or_404(InstitutionalRequest, pk=pk)
        status = request.data.get("status", "quoted")
        if status not in ("reviewing", "quoted", "closed"):
            raise serializers.ValidationError({"status": "Choose reviewing, quoted or closed."})
        resp = str(request.data.get("response", "")).strip()
        if status == "quoted" and not resp:
            raise serializers.ValidationError({"response": "Enter the quotation or response."})
        r.status, r.handled_by = status, request.user
        if resp:
            r.response = resp[:2000]
            services._mail(r.email, f"Response to your request: {r.service_required}", resp, "institutional_response")
        r.save()
        audit.record("institutional_request.updated", actor=request.user, target=r, status=status)
        return Response(inst_out(r))
