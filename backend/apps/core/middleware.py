import re

from django.conf import settings

from .tenant_context import reset_current_tenant, set_current_tenant

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def extract_tenant_hint(request):
    """Return ('slug'|'domain', value) or None. This is only a HINT: authenticated users are bound to
    their own tenant by the DRF layer, and a mismatching hint is rejected (see TenantContextMixin)."""
    header = request.headers.get("X-Tenant-Slug", "").strip().lower()
    if header and SLUG_RE.match(header):
        return ("slug", header)
    host = request.get_host().split(":")[0].lower()
    base = settings.PLATFORM_BASE_DOMAIN.lower()
    if host.endswith("." + base):
        sub = host[: -(len(base) + 1)]
        if sub and "." not in sub and SLUG_RE.match(sub) and sub not in {"www", "api", "app"}:
            return ("slug", sub)
    elif host != base and host not in settings.ALLOWED_HOSTS:
        return ("domain", host)
    return None


class TenantResolutionMiddleware:
    """Centralized tenant resolution. Attaches `request.tenant_hint`; guarantees the context never leaks."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant_hint = extract_tenant_hint(request)
        token = set_current_tenant(None)
        try:
            return self.get_response(request)
        finally:
            reset_current_tenant(token)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(self)")
        if request.path.startswith("/api/") and not request.path.startswith("/api/docs/"):
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        elif not request.path.startswith(("/admin/", "/api/docs/")):
            response.headers.setdefault("Content-Security-Policy", settings.SPA_CSP)
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response
