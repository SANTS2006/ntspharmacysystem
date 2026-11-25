from rest_framework import serializers
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView

from apps.accounts.models import User
from apps.accounts.permissions import HasTenantPermission
from apps.audit import services as audit
from apps.core.views import TenantContextMixin

from .models import Branch


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "code", "address", "phone", "email", "latitude", "longitude", "manager",
                  "operating_hours", "status", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_code(self, value):
        value = value.strip().upper()
        qs = Branch.objects.filter(code=value)  # tenant-scoped manager
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This branch code is already in use.")
        return value

    def validate_manager(self, user):
        tenant = self.context["request"].tenant
        if user is not None and (user.tenant_id != tenant.pk or not user.is_active):
            raise serializers.ValidationError("Select a manager from this pharmacy's staff.")
        return user


class BranchScopedMixin:
    def get_queryset(self):
        qs = Branch.objects.select_related("manager")
        u = self.request.user
        return qs.filter(pk=u.branch_id) if u.is_branch_scoped else qs


class BranchListCreateView(TenantContextMixin, BranchScopedMixin, ListCreateAPIView):
    serializer_class = BranchSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"GET": "branch.view", "POST": "branch.manage"}
    search_fields = ["name", "code", "address"]
    filterset_fields = ["status"]

    def perform_create(self, serializer):
        if self.request.user.is_branch_scoped:  # defensive: branch-scoped users never create branches
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Branch-scoped users cannot create branches.")
        b = serializer.save()
        audit.record("branch.created", actor=self.request.user, target=b, branch_id=b.pk, request=self.request, code=b.code)


class BranchDetailView(TenantContextMixin, BranchScopedMixin, RetrieveUpdateAPIView):
    serializer_class = BranchSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"GET": "branch.view", "PATCH": "branch.manage"}
    http_method_names = ["get", "patch", "head", "options"]

    def perform_update(self, serializer):
        b = serializer.save()
        audit.record("branch.updated", actor=self.request.user, target=b, branch_id=b.pk, request=self.request,
                     fields=sorted(serializer.validated_data))
