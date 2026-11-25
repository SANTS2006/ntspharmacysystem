from rest_framework import serializers, status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from apps.accounts.permissions import IsPlatformAdmin

from . import services
from .models import RESERVED_SLUGS, Pharmacy

READ_FIELDS = ["id", "name", "slug", "custom_domain", "logo", "description", "registration_number", "license_number",
               "license_expiry", "address", "country", "region", "city", "primary_color", "secondary_color",
               "contact_email", "contact_phone", "website_config", "status", "status_reason", "created_at"]


class PharmacySerializer(serializers.ModelSerializer):
    class Meta:
        model = Pharmacy
        fields = READ_FIELDS
        read_only_fields = ["id", "status", "status_reason", "created_at"]  # status only via suspend/activate

    def validate_slug(self, value):
        if value in RESERVED_SLUGS:
            raise serializers.ValidationError("This address is reserved.")
        return value


class PharmacyRegistrationSerializer(PharmacySerializer):
    admin_full_name = serializers.CharField(max_length=200)
    admin_email = serializers.EmailField()
    admin_phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    use_invitation = serializers.BooleanField(default=False)

    class Meta(PharmacySerializer.Meta):
        fields = READ_FIELDS + ["admin_full_name", "admin_email", "admin_phone", "use_invitation"]


class PharmacyListCreateView(ListCreateAPIView):
    permission_classes = [IsPlatformAdmin]
    queryset = Pharmacy.objects.all()
    filterset_fields = ["status", "country"]
    search_fields = ["name", "slug", "city"]
    ordering_fields = ["name", "created_at"]

    def get_serializer_class(self):
        return PharmacyRegistrationSerializer if self.request.method == "POST" else PharmacySerializer

    def create(self, request, *args, **kwargs):
        s = PharmacyRegistrationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        extra = {k: data.pop(k, "" if k == "admin_phone" else None) for k in
                 ["admin_full_name", "admin_email", "admin_phone", "use_invitation"]}
        pharmacy = services.register_pharmacy(actor=request.user, request=request, **extra, **data)
        return Response(PharmacySerializer(pharmacy).data, status=status.HTTP_201_CREATED)


class PharmacyDetailView(RetrieveUpdateAPIView):
    permission_classes = [IsPlatformAdmin]
    queryset = Pharmacy.objects.all()
    serializer_class = PharmacySerializer
    http_method_names = ["get", "patch", "head", "options"]


class PharmacyStatusView(APIView):
    permission_classes = [IsPlatformAdmin]
    target_status = None

    def post(self, request, pk):
        pharmacy = get_object_or_404(Pharmacy, pk=pk)
        pharmacy = services.set_status(pharmacy, self.target_status, actor=request.user,
                                       reason=str(request.data.get("reason", ""))[:255], request=request)
        return Response(PharmacySerializer(pharmacy).data)


class SuspendView(PharmacyStatusView):
    target_status = Pharmacy.Status.SUSPENDED


class ActivateView(PharmacyStatusView):
    target_status = Pharmacy.Status.ACTIVE


# ---------------- platform dashboard ----------------
from django.db.models import Count  # noqa: E402
from django.db.models.functions import TruncMonth  # noqa: E402
from datetime import timedelta  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.accounts.models import User  # noqa: E402
from apps.audit.models import AuditLog  # noqa: E402
from apps.billing.models import Invoice  # noqa: E402
from apps.core.tenant_context import unscoped  # noqa: E402
from apps.notifications.models import EmailLog  # noqa: E402

from .models import Branch  # noqa: E402


class PlatformDashboardView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        from django.db import connection
        from django.db.models import Sum
        by_status = dict(Pharmacy.objects.values_list("status").annotate(n=Count("id")))
        with unscoped():
            branches = Branch.objects.count()
        tenant_users = User.objects.filter(tenant__isnull=False)
        trend = (Pharmacy.objects.filter(created_at__gte=timezone.now() - timedelta(days=366))
                 .annotate(m=TruncMonth("created_at")).values("m").annotate(n=Count("id")).order_by("m"))
        paid = Invoice.objects.filter(status__in=["paid", "refunded"]).aggregate(t=Sum("amount"), r=Sum("refunded_amount"))
        try:
            connection.ensure_connection()
            db_ok = True
        except Exception:
            db_ok = False
        recent = AuditLog.objects.select_related("actor", "tenant")[:10]
        return Response({
            "pharmacies": {"total": sum(by_status.values()), "active": by_status.get("active", 0),
                           "suspended": by_status.get("suspended", 0), "deactivated": by_status.get("deactivated", 0)},
            "branches": branches,
            "users": tenant_users.exclude(role__code="customer").count(),
            "customers": tenant_users.filter(role__code="customer").count(),
            "subscription_revenue": {"collected": paid["t"] or 0, "refunded": paid["r"] or 0,
                                     "outstanding": Invoice.objects.filter(status="issued").aggregate(t=Sum("amount"))["t"] or 0},
            "registration_trend": [{"month": r["m"].strftime("%Y-%m"), "count": r["n"]} for r in trend],
            "usage": {"emails_sent_30d": EmailLog.objects.filter(status="sent", created_at__gte=timezone.now() - timedelta(days=30)).count(),
                      "emails_failed_30d": EmailLog.objects.filter(status="failed", created_at__gte=timezone.now() - timedelta(days=30)).count()},
            "system_health": {"database": "ok" if db_ok else "error"},
            "recent_activity": [{"id": a.id, "action": a.action, "actor": a.actor.email if a.actor else None,
                                 "tenant": a.tenant.name if a.tenant else None, "at": a.created_at} for a in recent],
        })


class PharmacyDetailExtrasView(APIView):
    """Admins, branches and subscription for one pharmacy (platform view)."""
    permission_classes = [IsPlatformAdmin]

    def get(self, request, pk):
        pharmacy = get_object_or_404(Pharmacy, pk=pk)
        with unscoped():
            branches = list(Branch.objects.filter(tenant=pharmacy).values("id", "name", "code", "status"))
        admins = list(User.objects.filter(tenant=pharmacy, role__code="pharmacy_admin")
                      .values("id", "email", "full_name", "phone", "is_active", "must_change_password"))
        sub = getattr(pharmacy, "subscription", None) if hasattr(pharmacy, "subscription") else None
        return Response({
            "branches": branches, "administrators": admins,
            "user_count": User.objects.filter(tenant=pharmacy).count(),
            "subscription": {"plan": sub.plan.name, "status": sub.status, "current_period_end": sub.current_period_end} if sub else None,
        })
