from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import GenericAPIView, ListAPIView, ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.response import Response

from apps.audit import services as audit
from apps.core.views import TenantContextMixin
from apps.core.links import site_url
from apps.notifications.services import render_branded_html, send_email
from apps.tenants.models import Branch

from . import services
from .models import Role, User
from .permissions import HasTenantPermission
from .permissions_registry import PERMISSIONS, STAFF_ROLE_CODES


def can_assign(actor: User, role: Role) -> bool:
    """Anti-escalation: only a pharmacy admin may grant admin; everyone else only roles whose permissions
    are a subset of their own."""
    if role.code == "pharmacy_admin":
        return actor.role.code == "pharmacy_admin"
    return set(role.permissions) <= set(actor.role.permissions)


class TenantRoleField(serializers.SlugRelatedField):
    """Resolve role codes only within the caller's pharmacy (codes repeat across tenants)."""

    def get_queryset(self):
        return Role.objects.filter(tenant=self.context["request"].tenant)


class StaffSerializer(serializers.ModelSerializer):
    role = TenantRoleField(slug_field="code")
    role_name = serializers.CharField(source="role.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    use_invitation = serializers.BooleanField(write_only=True, default=True)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "role", "role_name", "branch", "branch_name", "is_active",
                  "must_change_password", "date_joined", "use_invitation"]
        read_only_fields = ["id", "must_change_password", "date_joined"]

    def validate_role(self, role):
        actor, tenant = self.context["request"].user, self.context["request"].tenant
        if role.tenant_id != tenant.pk or role.code not in STAFF_ROLE_CODES:
            raise serializers.ValidationError("Select a valid staff role.")
        if not can_assign(actor, role):
            raise serializers.ValidationError("You cannot assign a role with more access than your own.")
        return role

    def validate_branch(self, branch):
        actor, tenant = self.context["request"].user, self.context["request"].tenant
        if branch is not None and branch.tenant_id != tenant.pk:
            raise serializers.ValidationError("Select a branch of this pharmacy.")
        if actor.is_branch_scoped and (branch is None or branch.pk != actor.branch_id):
            raise serializers.ValidationError("You can only manage staff of your own branch.")
        return branch

    def validate_email(self, value):
        value = value.strip().lower()
        qs = User.objects.filter(tenant=self.context["request"].tenant, email=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        role, branch = attrs.get("role") or (self.instance and self.instance.role), attrs.get("branch", self.instance.branch if self.instance else None)
        if role is not None and role.branch_scoped and branch is None:
            raise serializers.ValidationError({"branch": "This role must be assigned to a branch."})
        if self.instance:
            actor = self.context["request"].user
            if self.instance.pk == actor.pk and ({"role", "is_active", "branch"} & set(attrs)):
                raise serializers.ValidationError("You cannot change your own role, branch or status.")
            if not can_assign(actor, self.instance.role):
                raise serializers.ValidationError("You cannot modify a user with more access than your own.")
        return attrs


class StaffScopedMixin:
    def get_queryset(self):
        u = self.request.user
        qs = (User.objects.filter(tenant=u.tenant, role__code__in=STAFF_ROLE_CODES).select_related("role", "branch")
              .order_by("full_name"))
        return qs.filter(branch_id=u.branch_id) if u.is_branch_scoped else qs


class StaffListCreateView(TenantContextMixin, StaffScopedMixin, ListCreateAPIView):
    serializer_class = StaffSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"GET": "staff.view", "POST": "staff.manage"}
    search_fields = ["full_name", "email", "phone"]
    filterset_fields = ["role__code", "branch", "is_active"]

    @transaction.atomic
    def perform_create(self, serializer):
        d, actor, tenant = dict(serializer.validated_data), self.request.user, self.request.tenant
        invite = d.pop("use_invitation", True)
        user = User.objects.create_user(tenant=tenant, created_by=actor, password=None, **d)
        urls = site_url(tenant.slug, "/admin/login")
        if invite:
            user.set_unusable_password()
            user.must_change_password = True
            user.save()
            link = f"{settings.FRONTEND_URL.rstrip('/')}/accept-invitation?token={services.create_invitation(user)}"
            cred, method = f"Set your password with this one-time link: {link}", "invitation"
        else:
            temp = services.build_default_password(tenant.name)
            services.issue_temporary_credentials(user, temp)
            cred, method = f"Temporary password: {temp} (expires in {settings.TEMP_CREDENTIAL_TTL_HOURS} hours; you must change it at first login).", "temporary_password"
        audit.record("staff.created", actor=actor, target=user, branch_id=user.branch_id, request=self.request, role=user.role.code)
        audit.record("auth.credentials_issued", actor=actor, target=user, branch_id=user.branch_id, request=self.request, method=method)
        text = f"Hello {user.full_name},\nYou have been added to {tenant.name} as {user.role.name}.\nLogin: {urls}\nEmail: {user.email}\n{cred}"
        send_email(to=user.email, subject=f"Your {tenant.name} staff account", text=text, tenant=tenant, template="staff_onboarding",
                   html_body=render_branded_html(title="Your staff account", pharmacy=tenant, button=("Open login", urls),
                                                 paragraphs=[f"You have been added as {user.role.name}.", f"Email: {user.email}", cred]))
        serializer.instance = user


class StaffDetailView(TenantContextMixin, StaffScopedMixin, RetrieveUpdateAPIView):
    serializer_class = StaffSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"GET": "staff.view", "PATCH": "staff.manage"}
    http_method_names = ["get", "patch", "head", "options"]

    @transaction.atomic
    def perform_update(self, serializer):
        old = self.get_object()
        old_role, old_active = old.role.code, old.is_active
        serializer.validated_data.pop("use_invitation", None)
        user = serializer.save()
        revoke = (user.role.code != old_role) or (old_active and not user.is_active)
        if revoke:
            user.credential_version += 1  # role change / deactivation takes effect immediately
            user.save(update_fields=["credential_version"])
        if user.role.code != old_role:
            audit.record("staff.role_changed", actor=self.request.user, target=user, branch_id=user.branch_id,
                         request=self.request, old=old_role, new=user.role.code)
        if old_active != user.is_active:
            audit.record("staff.activated" if user.is_active else "staff.deactivated", actor=self.request.user,
                         target=user, branch_id=user.branch_id, request=self.request)
        audit.record("staff.updated", actor=self.request.user, target=user, branch_id=user.branch_id, request=self.request,
                     fields=sorted(serializer.validated_data))


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "code", "name", "permissions", "branch_scoped", "is_system"]
        read_only_fields = ["id", "code", "name", "is_system"]

    def validate_permissions(self, perms):
        unknown = set(perms) - PERMISSIONS
        if unknown:
            raise serializers.ValidationError(f"Unknown permissions: {sorted(unknown)}")
        actor = self.context["request"].user
        if not set(perms) <= set(actor.role.permissions):
            raise serializers.ValidationError("You cannot grant permissions you do not have.")
        return sorted(set(perms))


class RoleListView(TenantContextMixin, ListAPIView):
    serializer_class = RoleSerializer
    permission_classes = [HasTenantPermission]
    required_permission = "staff.view"
    pagination_class = None

    def get_queryset(self):
        return Role.objects.filter(tenant=self.request.user.tenant).order_by("name")


class RoleDetailView(TenantContextMixin, RetrieveUpdateAPIView):
    serializer_class = RoleSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"GET": "staff.view", "PATCH": "role.manage"}
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return Role.objects.filter(tenant=self.request.user.tenant)

    @transaction.atomic
    def perform_update(self, serializer):
        role = serializer.instance
        if role.code == "pharmacy_admin":
            raise PermissionDenied("The administrator role cannot be modified.")
        old = list(role.permissions)
        role = serializer.save()
        # permission changes must apply at once: revoke sessions of everyone holding the role
        User.objects.filter(role=role).update(credential_version=models_F("credential_version") + 1)
        audit.record("role.permissions_changed", actor=self.request.user, target=role, request=self.request,
                     added=sorted(set(role.permissions) - set(old)), removed=sorted(set(old) - set(role.permissions)))


from django.db.models import F as models_F  # noqa: E402
