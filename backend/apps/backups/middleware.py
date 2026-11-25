from django.core.cache import cache
from django.http import JsonResponse


class MaintenanceMiddleware:
    """While a restore replaces the database, every API call except platform administration and health checks gets a clear 503 (never a half-restored read or write)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        p = request.path
        if p.startswith("/api/") and not p.startswith(("/api/v1/platform/", "/api/v1/auth/", "/health/")):
            try:
                on = cache.get("maintenance_mode")
            except Exception:  # cache outage must not look like maintenance
                on = False
            if on:
                r = JsonResponse({"success": False, "error": {"code": "maintenance", "message": "The system is being restored from a backup. Please try again in a few minutes.", "details": None}}, status=503)
                r["Retry-After"] = "120"
                return r
        return self.get_response(request)
