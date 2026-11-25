from io import BytesIO

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts import services as account_services
from apps.accounts.permissions import HasTenantPermission, IsAuthenticatedAndSettled
from apps.accounts.views import UserSerializer
from apps.audit import services as audit
from apps.core.fields import TenantPKField
from apps.core.tenant_context import tenant_context
from apps.core.views import TenantContextMixin, resolve_hint
from apps.inventory.selectors import branch_ids_for
from apps.medicines.models import Category, Medicine
from apps.tenants.models import Branch, Pharmacy

from . import services
from .models import CustomerProfile, Order, QrRequest


# ======================= public (anonymous) =======================
def _tenant(slug):
    t = Pharmacy.objects.filter(slug=slug, status=Pharmacy.Status.ACTIVE).first()
    if t is None:
        raise NotFound()
    return t


def medicine_card(m, branch=None, with_stock=True):
    d = {"id": m.pk, "name": m.name, "generic_name": m.generic_name, "brand_name": m.brand_name, "strength": m.strength, "dosage_form": m.dosage_form,
         "category": m.category.name, "price": m.selling_price, "description": m.description, "requires_prescription": m.requires_prescription,
         "image": None}
    if with_stock and branch is not None:
        d["available"] = services.saleable_stock(m, branch) > 0
    return d


def catalogue_response(request, tenant, branch=None):
    with tenant_context(tenant):
        qs = services.online_visible().select_related("category")
        if q := request.query_params.get("search"):
            qs = qs.filter(Q(name__icontains=q) | Q(generic_name__icontains=q) | Q(brand_name__icontains=q))
        if c := request.query_params.get("category"):
            qs = qs.filter(category_id=c)
        if branch is None and (b := request.query_params.get("branch")):
            branch = Branch.objects.filter(pk=b, status="active").first()
        pg = PageNumberPagination()
        pg.page_size = 24
        page = pg.paginate_queryset(qs.order_by("name"), request)
        return pg.get_paginated_response([medicine_card(m, branch) for m in page])


class PublicBase(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


class PublicCatalogueView(PublicBase):
    def get(self, request, slug):
        return catalogue_response(request, _tenant(slug))


class PublicCategoriesView(PublicBase):
    def get(self, request, slug):
        with tenant_context(_tenant(slug)):
            return Response(list(Category.objects.filter(medicines__status="active", medicines__is_online_visible=True).distinct().values("id", "name")))


class PublicBranchesView(PublicBase):
    def get(self, request, slug):
        with tenant_context(_tenant(slug)):
            return Response(list(Branch.objects.filter(status="active").values("id", "name", "address", "phone", "email", "operating_hours")))


class PublicMenuView(PublicBase):
    def get(self, request, token):
        b = services.resolve_qr(token)
        t = b.tenant
        return Response({"branch": {"id": b.pk, "name": b.name, "address": b.address, "phone": b.phone}, "pharmacy": {"name": t.name, "slug": t.slug, "primary_color": t.primary_color, "secondary_color": t.secondary_color}})


class PublicMenuCatalogueView(PublicBase):
    def get(self, request, token):
        b = services.resolve_qr(token)
        with tenant_context(b.tenant):
            return catalogue_response(request, b.tenant, branch=Branch.objects.get(pk=b.pk))


class QrItemIn(serializers.Serializer):
    medicine = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=100)


class QrRequestIn(serializers.Serializer):
    customer_name = serializers.CharField(max_length=150)
    customer_phone = serializers.CharField(max_length=30)
    kind = serializers.ChoiceField(choices=["shopping", "assistance"], default="shopping")
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    items = QrItemIn(many=True, required=False, default=list)
    website = serializers.CharField(required=False, allow_blank=True, default="")  # honeypot


class PublicQrRequestView(PublicBase):
    throttle_scope = "public_write"

    def get_throttles(self):
        return [ScopedRateThrottle()]

    def post(self, request, token):
        b = services.resolve_qr(token)
        s = QrRequestIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if d["website"]:  # bots fill hidden fields; pretend success
            return Response({"received": True}, status=201)
        with tenant_context(b.tenant):
            items = []
            for it in d["items"]:
                m = Medicine.objects.filter(pk=it["medicine"]).first()
                if m is None:
                    raise serializers.ValidationError({"items": "A product was not found."})
                items.append({"medicine": m, "quantity": it["quantity"]})
        req = services.create_qr_request(b, name=d["customer_name"], phone=d["customer_phone"], kind=d["kind"], note=d["note"], items=items)
        return Response({"received": True, "reference": req.pk, "requires_prescription": req.requires_prescription}, status=201)


# ======================= customer auth =======================
class IsVerifiedCustomer(IsAuthenticatedAndSettled):
    def has_permission(self, request, view):
        u = request.user
        if not super().has_permission(request, view):
            return False
        if not (u.role_id and u.role.code == "customer"):
            return False
        if not u.email_verified:
            self.message, self.code = "Verify your email address to continue.", "email_not_verified"
            return False
        return True


class IsCustomer(IsAuthenticatedAndSettled):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and bool(request.user.role_id and request.user.role.code == "customer")


class RegisterIn(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)
    full_name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    terms_accepted = serializers.BooleanField()

    def validate(self, a):
        from django.contrib.auth.password_validation import validate_password
        validate_password(a["password"])
        return a


def _tenant_from_hint(request):
    t = resolve_hint(request)
    if t is None or not t.is_active_tenant:
        raise NotFound()
    return t


class Throttled(APIView):
    throttle_scope = "login"

    def get_throttles(self):
        return [ScopedRateThrottle()]


class RegisterView(Throttled):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        t = _tenant_from_hint(request)
        s = RegisterIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        user = services.register_customer(tenant=t, email=d["email"], password=d["password"], full_name=d["full_name"], phone=d["phone"], terms_accepted=d["terms_accepted"], request=request)
        return Response({"success": True, "tokens": account_services.issue_tokens(user), "user": UserSerializer(user).data}, status=201)


class GoogleView(Throttled):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        t = _tenant_from_hint(request)
        user = services.google_sign_in(tenant=t, id_token=str(request.data.get("id_token", "")), terms_accepted=request.data.get("terms_accepted") is True, request=request)
        return Response({"success": True, "tokens": account_services.issue_tokens(user), "user": UserSerializer(user).data})


class VerifyEmailView(TenantContextMixin, APIView):
    permission_classes = [IsCustomer]
    throttle_scope = "verify"

    def get_throttles(self):
        return [ScopedRateThrottle()]

    def post(self, request):
        result = services.verify_email_code(request.user, str(request.data.get("code", "")), request)
        if result == "locked":
            return Response({"success": False, "error": {"code": "too_many_attempts", "message": "Too many incorrect attempts. Request a new code.", "details": None}}, status=429)
        if result == "bad":
            return Response({"success": False, "error": {"code": "invalid_code", "message": "That code is incorrect or has expired.", "details": None}}, status=400)
        request.user.refresh_from_db()
        return Response({"verified": True, "user": UserSerializer(request.user).data})


class ResendCodeView(TenantContextMixin, APIView):
    permission_classes = [IsCustomer]
    throttle_scope = "verify"

    def get_throttles(self):
        return [ScopedRateThrottle()]

    def post(self, request):
        if request.user.email_verified:
            return Response({"verified": True})
        services.send_verification_code(request.user)
        return Response(status=202)


# ======================= customer profile =======================
class ProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name", max_length=200)
    phone = serializers.CharField(source="user.phone", max_length=30, required=False, allow_blank=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = ["full_name", "email", "phone", "date_of_birth", "gender", "address", "delivery_addresses", "emergency_contact_name", "emergency_contact_phone", "notification_prefs", "terms_version"]
        read_only_fields = ["terms_version"]

    def validate_delivery_addresses(self, v):
        if not isinstance(v, list) or len(v) > 10 or any(not isinstance(a, dict) or not str(a.get("address", "")).strip() for a in v):
            raise serializers.ValidationError("Provide up to 10 addresses with an 'address' each.")
        return [{"label": str(a.get("label", ""))[:40], "address": str(a["address"])[:300]} for a in v]

    def validate_notification_prefs(self, v):
        allowed = {"email_orders", "email_marketing"}
        if not isinstance(v, dict) or set(v) - allowed or any(not isinstance(x, bool) for x in v.values()):
            raise serializers.ValidationError("Invalid preferences.")
        return v

    def update(self, inst, data):
        u = data.pop("user", {})
        for k, v in u.items():
            setattr(inst.user, k, v)
        if u:
            inst.user.save(update_fields=list(u))
        return super().update(inst, data)


class MeView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]

    def get(self, request):
        return Response(ProfileSerializer(request.user.customer_profile).data)

    def patch(self, request):
        s = ProfileSerializer(request.user.customer_profile, data=request.data, partial=True)  # email changes are not allowed here
        s.is_valid(raise_exception=True)
        s.save()
        audit.record("customer.profile_updated", actor=request.user, request=request, fields=sorted(request.data))
        return Response(s.data)


# ======================= customer orders =======================
class OrderItemIn(serializers.Serializer):
    medicine = TenantPKField(Medicine)
    quantity = serializers.IntegerField(min_value=1, max_value=100)


class OrderIn(serializers.Serializer):
    branch = TenantPKField(Branch)
    fulfilment = serializers.ChoiceField(choices=["pickup", "delivery"])
    payment_method = serializers.CharField(max_length=20)
    delivery_address = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    items = OrderItemIn(many=True)


def order_out(o: Order, staff=False):
    d = {"id": o.pk, "reference_number": o.reference_number, "status": o.status, "fulfilment": o.fulfilment, "delivery_address": o.delivery_address,
         "payment_method": o.payment_method, "branch": o.branch_id, "branch_name": o.branch.name, "subtotal": o.subtotal, "tax_total": o.tax_total,
         "delivery_fee": o.delivery_fee, "total": o.total, "requires_prescription": o.requires_prescription, "created_at": o.created_at,
         "prescription_status": o.prescription.status if o.prescription_id else None,
         "lines": [{"medicine": l.medicine_id, "name": l.medicine.name, "quantity": l.quantity, "unit_price": l.unit_price, "line_total": l.line_total, "requires_prescription": l.medicine.requires_prescription} for l in o.lines.select_related("medicine")],
         "history": [{"status": e.to_status, "at": e.created_at, "note": e.note} for e in o.events.all()],
         "customer_can_cancel": o.status in services.CUSTOMER_CAN[services.S.CANCELLED]}
    if staff:
        d.update(customer_name=o.customer.full_name, customer_phone=o.customer.phone, customer_email=o.customer.email, notes=o.notes,
                 prescription=o.prescription.reference_number if o.prescription_id else None, prescription_id=o.prescription_id)
    return d


class ShopOrdersView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]

    def get(self, request):
        pg = PageNumberPagination()
        qs = Order.objects.filter(customer=request.user).select_related("branch", "prescription")
        return pg.get_paginated_response([order_out(o) for o in pg.paginate_queryset(qs, request)])

    def post(self, request):
        s = OrderIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        o, created = services.create_order(customer=request.user, branch=d["branch"], fulfilment=d["fulfilment"], items=d["items"], payment_method=d["payment_method"],
                                           idempotency_key=request.headers.get("Idempotency-Key", ""), delivery_address=d["delivery_address"], notes=d["notes"])
        return Response(order_out(o), status=201 if created else 200)


class ShopOrderDetailView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]

    def get(self, request, pk):
        return Response(order_out(get_object_or_404(Order.objects.select_related("branch", "prescription"), pk=pk, customer=request.user)))


class ShopOrderActionView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]
    target = None

    def post(self, request, pk):
        o = get_object_or_404(Order, pk=pk, customer=request.user)
        o = services.transition(o.pk, self.target, actor=request.user, kind="customer", note=str(request.data.get("reason", "")))
        return Response(order_out(o))


class ShopOrderCancelView(ShopOrderActionView):
    target = services.S.CANCELLED


class ShopOrderRefundView(ShopOrderActionView):
    target = services.S.REFUND_REQUESTED


class ShopOrderPrescriptionView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk):
        o = get_object_or_404(Order, pk=pk, customer=request.user)
        f = request.FILES.get("document")
        if f is None:
            raise serializers.ValidationError({"document": "Choose a file."})
        date = serializers.DateField().run_validation(request.data.get("prescription_date"))
        o = services.attach_prescription(o.pk, customer=request.user, prescriber_name=str(request.data.get("prescriber_name", "")).strip() or "Not stated", prescription_date=date, document=f)
        return Response(order_out(o))


# ======================= staff =======================
def staff_orders(user):
    qs = Order.objects.select_related("branch", "customer", "prescription")
    ids = branch_ids_for(user)
    return qs.filter(branch_id__in=ids) if ids else qs


class StaffBase(TenantContextMixin):
    permission_classes = [HasTenantPermission]
    required_permission = "order.manage"


class StaffOrdersView(StaffBase, APIView):
    def get(self, request):
        qs = staff_orders(request.user)
        if st := request.query_params.get("status"):
            qs = qs.filter(status=st)
        if s := request.query_params.get("search"):
            qs = qs.filter(Q(reference_number__icontains=s) | Q(customer__full_name__icontains=s))
        pg = PageNumberPagination()
        return pg.get_paginated_response([order_out(o, True) for o in pg.paginate_queryset(qs, request)])


class StaffOrderDetailView(StaffBase, APIView):
    def get(self, request, pk):
        return Response(order_out(get_object_or_404(staff_orders(request.user), pk=pk), True))


class StaffTransitionView(StaffBase, APIView):
    def post(self, request, pk):
        o = get_object_or_404(staff_orders(request.user), pk=pk)
        o = services.transition(o.pk, request.data.get("status", ""), actor=request.user, kind="staff", note=str(request.data.get("note", "")))
        return Response(order_out(o, True))


def qr_out(r: QrRequest):
    return {"id": r.pk, "branch": r.branch_id, "kind": r.kind, "customer_name": r.customer_name, "customer_phone": r.customer_phone, "note": r.note, "status": r.status,
            "requires_prescription": r.requires_prescription, "staff_note": r.staff_note, "created_at": r.created_at,
            "items": [{"medicine": i.medicine_id, "name": i.medicine.name, "quantity": i.quantity, "requires_prescription": i.medicine.requires_prescription} for i in r.items.select_related("medicine")]}


class StaffQrRequestsView(StaffBase, APIView):
    def get(self, request):
        qs = QrRequest.objects.all()
        ids = branch_ids_for(request.user)
        if ids:
            qs = qs.filter(branch_id__in=ids)
        if st := request.query_params.get("status"):
            qs = qs.filter(status=st)
        pg = PageNumberPagination()
        return pg.get_paginated_response([qr_out(r) for r in pg.paginate_queryset(qs, request)])


class StaffQrStatusView(StaffBase, APIView):
    def post(self, request, pk):
        qs = QrRequest.objects.all()
        ids = branch_ids_for(request.user)
        r = get_object_or_404(qs.filter(branch_id__in=ids) if ids else qs, pk=pk)
        st = request.data.get("status")
        if st not in {s.value for s in QrRequest.Status}:
            raise serializers.ValidationError({"status": "Unknown status."})
        if r.status in ("closed", "cancelled"):
            raise serializers.ValidationError({"status": "This request is already finished."})
        r.status, r.handled_by, r.staff_note = st, request.user, str(request.data.get("staff_note", r.staff_note))[:500]
        r.save()
        audit.record("qr_request.updated", actor=request.user, target=r, branch_id=r.branch_id, status=st)
        return Response(qr_out(r))


class BranchQrView(TenantContextMixin, APIView):
    permission_classes = [HasTenantPermission]
    required_permission = "branch.view"

    def get(self, request, pk):
        import qrcode
        from django.conf import settings
        ids = branch_ids_for(request.user)
        qs = Branch.objects.filter(pk__in=ids) if ids else Branch.objects.all()
        b = get_object_or_404(qs, pk=pk)
        token = services.ensure_qr_token(b)
        url = f"{settings.FRONTEND_URL.rstrip('/')}/pharmacy/{request.tenant.slug}/menu/{token}"
        if request.query_params.get("format") == "json":
            return Response({"url": url})
        buf = BytesIO()
        qrcode.make(url).save(buf, format="PNG")
        resp = HttpResponse(buf.getvalue(), content_type="image/png")
        resp["Content-Disposition"] = f'inline; filename="branch-{b.code}-qr.png"'
        return resp
