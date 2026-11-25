from .models import AuditLog

_SENSITIVE = {"password", "token", "secret", "code"}


def _clean(meta: dict) -> dict:
    return {k: ("[redacted]" if any(s in k.lower() for s in _SENSITIVE) else v) for k, v in (meta or {}).items()}


def client_ip(request):
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or None


def record(action, *, actor=None, tenant=None, branch_id=None, target=None, request=None, **metadata):
    tenant = tenant or getattr(actor, "tenant", None)
    return AuditLog.objects.create(
        tenant=tenant, branch_id=branch_id, actor=actor if getattr(actor, "pk", None) else None, action=action,
        target_type=type(target).__name__ if target is not None else "",
        target_id=str(getattr(target, "pk", "")) if target is not None else "",
        metadata=_clean(metadata), ip_address=client_ip(request))
