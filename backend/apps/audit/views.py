from rest_framework import serializers
from rest_framework.generics import ListAPIView

from apps.accounts.permissions import HasTenantPermission, IsPlatformAdminOrTenantPermission
from apps.core.views import TenantContextMixin

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "created_at", "action", "actor_email", "target_type", "target_id", "branch_id",
                  "metadata", "ip_address"]


class AuditLogListView(TenantContextMixin, ListAPIView):
    """Platform admins see everything (optionally ?tenant=<id>); tenant users see only their own tenant."""
    serializer_class = AuditLogSerializer
    permission_classes = [IsPlatformAdminOrTenantPermission]
    required_permission = "audit.view"
    filterset_fields = ["action", "branch_id"]
    search_fields = ["action", "target_type", "target_id"]

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor")
        user = self.request.user
        if user.is_platform_admin:
            tenant_id = self.request.query_params.get("tenant")
            return qs.filter(tenant_id=tenant_id) if tenant_id else qs
        qs = qs.filter(tenant_id=user.tenant_id)
        if user.is_branch_scoped:
            qs = qs.filter(branch_id=user.branch_id)
        return qs
