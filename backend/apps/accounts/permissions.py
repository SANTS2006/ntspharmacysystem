from rest_framework.permissions import BasePermission


class IsAuthenticatedAndSettled(BasePermission):
    """Authenticated AND not stuck in forced password change (unless the view opts in)."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.must_change_password and not getattr(view, "allow_pending_password_change", False):
            self.message = "You must change your temporary password before continuing."
            self.code = "password_change_required"
            return False
        return True


class IsPlatformAdmin(IsAuthenticatedAndSettled):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_platform_admin


class HasTenantPermission(IsAuthenticatedAndSettled):
    """View declares `required_permission = "x.y"` or `required_permissions = {"GET": "x.view", "POST": ...}`.
    Enforced server-side regardless of which routes the frontend displays."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.has_tenant_perm(_needed(view, request))


class IsPlatformAdminOrTenantPermission(IsAuthenticatedAndSettled):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.is_platform_admin or request.user.has_tenant_perm(_needed(view, request))


def _needed(view, request):
    perms = getattr(view, "required_permissions", None)
    if perms:
        return perms.get(request.method, "__denied__")
    return getattr(view, "required_permission", "__denied__")  # default deny
