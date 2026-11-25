from rest_framework import serializers
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import HasTenantPermission, IsAuthenticatedAndSettled
from apps.audit import services as audit
from apps.core.views import TenantContextMixin

from .models import Branch, Pharmacy, hex_color


class PharmacySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pharmacy
        fields = ["name", "slug", "logo", "description", "address", "country", "region", "city", "primary_color",
                  "secondary_color", "contact_email", "contact_phone", "website_config", "settings", "status"]
        read_only_fields = ["slug", "status", "name", "country"]  # identity/status are platform-controlled

    def validate_settings(self, value):
        if not isinstance(value, dict) or len(str(value)) > 20_000:
            raise serializers.ValidationError("Settings must be an object under 20 KB.")
        return value


class PharmacySettingsView(TenantContextMixin, RetrieveUpdateAPIView):
    """The caller's OWN pharmacy only; there is no id in the URL to tamper with."""
    serializer_class = PharmacySettingsSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"GET": "staff.view", "PATCH": "settings.manage"}
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user.tenant

    def perform_update(self, serializer):
        p = serializer.save()
        audit.record("settings.updated", actor=self.request.user, tenant=p, target=p, request=self.request,
                     fields=sorted(serializer.validated_data))


class TenantDashboardView(TenantContextMixin, RetrieveUpdateAPIView):
    """Counts for what exists today. Metrics from later phases (stock, sales...) are added as those modules land;
    they are deliberately absent rather than faked."""
    permission_classes = [IsAuthenticatedAndSettled]
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        u = request.user
        if u.is_platform_admin or not u.role_id:
            return Response(status=403)
        branches = Branch.objects.all()
        staff = User.objects.filter(tenant=u.tenant, is_active=True).exclude(role__code="customer")
        customers = User.objects.filter(tenant=u.tenant, role__code="customer")
        if u.is_branch_scoped:
            branches, staff = branches.filter(pk=u.branch_id), staff.filter(branch_id=u.branch_id)
            customers = customers.none()  # customers are pharmacy-wide until branch-linked in Phase 8
        return Response({
            "scope": "branch" if u.is_branch_scoped else "pharmacy",
            "branches": branches.count(), "employees": staff.count(),
            "pharmacists": staff.filter(role__code="pharmacist").count(),
            "customers": customers.count() if u.has_tenant_perm("customer.view") else None,
            "staff_by_role": list(staff.values("role__name").order_by("role__name").annotate(n=__import__("django.db.models", fromlist=["Count"]).Count("id"))),
        })
