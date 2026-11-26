from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import GenericAPIView

from .tenant_context import reset_current_tenant, set_current_tenant


def resolve_hint(request):
    from apps.tenants.models import Pharmacy
    hint = getattr(request._request, "tenant_hint", None)
    if not hint:
        return None
    kind, value = hint
    return Pharmacy.objects.filter(**({"slug": value} if kind == "slug" else {"custom_domain": value})).first()


class TenantContextMixin:
    """Binds the tenant for the request AFTER authentication.

    - Tenant users: tenant is ALWAYS user.tenant. A conflicting hint (slug/header/domain) is rejected.
    - Platform admins: may act inside a tenant only through an explicit, validated hint.
    - Anonymous: the hint selects the public pharmacy site; suspended pharmacies are invisible.
    """

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        user = request.user
        hinted = resolve_hint(request)
        if user.is_authenticated and not user.is_platform_admin:
            if hinted is not None and hinted.pk != user.tenant_id:
                raise PermissionDenied("Tenant mismatch.")
            tenant = user.tenant
        else:
            tenant = hinted
            if tenant is not None and not user.is_authenticated and not tenant.is_active_tenant:
                tenant = None
        request.tenant = tenant
        self._tenant_token = set_current_tenant(tenant)

    def finalize_response(self, request, response, *args, **kwargs):
        token = getattr(self, "_tenant_token", None)
        if token is not None:
            reset_current_tenant(token)
            self._tenant_token = None
        return super().finalize_response(request, response, *args, **kwargs)


class TenantAPIView(TenantContextMixin, GenericAPIView):
    pass


def spa_index(request, *args, **kwargs):
    """Serve the built React app's index.html for client-side routes (no-store so a deploy is picked up immediately)."""
    from django.conf import settings
    from django.http import Http404, HttpResponse
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        raise Http404("Frontend build not found.")
    from .seo import inject
    resp = HttpResponse(inject(index.read_text(encoding="utf-8"), request), content_type="text/html; charset=utf-8")
    resp["Cache-Control"] = "no-store"
    return resp
