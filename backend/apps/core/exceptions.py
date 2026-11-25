from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exc
from rest_framework.response import Response
from rest_framework.views import exception_handler


class BusinessRuleViolation(drf_exc.APIException):
    status_code = 409
    default_code = "business_rule_violation"
    default_detail = "The operation violates a business rule."


def api_exception_handler(exc, context):
    """Uniform error envelope: {"success": false, "error": {"code", "message", "details"}}."""
    if isinstance(exc, PermissionDenied):
        exc = drf_exc.PermissionDenied(str(exc) or None)
    elif isinstance(exc, Http404):
        exc = drf_exc.NotFound()
    response = exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> 500 via Django (no internals leaked when DEBUG is off)
    data = response.data
    code = getattr(getattr(exc, "detail", None), "code", None) or getattr(exc, "default_code", "error")  # specific code when the raiser set one
    if isinstance(data, dict) and set(data) == {"detail"}:
        message, details = str(data["detail"]), None
    else:
        message, details = "Validation failed." if response.status_code == 400 else "Request failed.", data
    return Response({"success": False, "error": {"code": code, "message": message, "details": details}},
                    status=response.status_code, headers=dict(response.items()))
