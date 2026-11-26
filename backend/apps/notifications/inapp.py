"""In-app notifications: stored per recipient, then pushed over the WebSocket. Creating one must never break the business action that caused it."""
import logging

from django.db import transaction
from django.db.models import Q

from apps.core.realtime import notify, user_group

from .models import Notification

log = logging.getLogger(__name__)


def push(users, *, kind: str, title: str, body: str = "", link: str = "", level: str = "info", exclude=None) -> int:
    """`users` is an iterable of User objects. The tenant is always taken from the recipient, so a notification can never cross pharmacies."""
    skip = getattr(exclude, "pk", exclude)
    unique = {u.pk: u for u in users if u is not None and u.is_active and u.pk != skip}
    if not unique:
        return 0
    try:
        with transaction.atomic():  # savepoint: a failure here leaves the surrounding transaction usable
            Notification.objects.bulk_create([
                Notification(user=u, tenant_id=u.tenant_id, kind=kind[:40], level=level, title=title[:160], body=(body or "")[:1000], link=link[:200])
                for u in unique.values()])
    except Exception:
        log.exception("could not store notification %s", kind)
        return 0
    for u in unique.values():  # only the kind travels over the socket; the browser reads content through the authenticated API
        notify([user_group(u.tenant_id or 0, u.pk)], "notification.created", {"kind": kind})
    return len(unique)


def staff_with(tenant_id: int, permission: str, branch_id=None) -> list:
    """Active staff of one pharmacy whose role grants `permission`; branch-scoped roles only for their own branch."""
    from apps.accounts.models import User
    qs = User.objects.filter(tenant_id=tenant_id, is_active=True, role__isnull=False).exclude(role__code="customer").select_related("role")
    if branch_id:
        qs = qs.filter(Q(role__branch_scoped=False) | Q(branch_id=branch_id) | Q(branch_id__isnull=True))
    return [u for u in qs if permission in u.role.permissions]


def push_staff(tenant_id: int, permission: str, branch_id=None, **kw) -> int:
    return push(staff_with(tenant_id, permission, branch_id), **kw)


def platform_admins() -> list:
    from apps.accounts.models import User
    return list(User.objects.filter(is_platform_admin=True, is_active=True))
