"""Request-scoped tenant context (contextvars: safe for threads, async and Celery tasks)."""
from contextlib import contextmanager
from contextvars import ContextVar

_current_tenant = ContextVar("current_tenant", default=None)
_unscoped = ContextVar("tenant_unscoped", default=False)


def get_current_tenant():
    return _current_tenant.get()


def set_current_tenant(tenant):
    return _current_tenant.set(tenant)


def reset_current_tenant(token):
    _current_tenant.reset(token)


def is_unscoped() -> bool:
    return _unscoped.get()


@contextmanager
def tenant_context(tenant):
    token = _current_tenant.set(tenant)
    try:
        yield tenant
    finally:
        _current_tenant.reset(token)


@contextmanager
def unscoped():
    """Explicit, greppable escape hatch for platform-level/system code. Never use in tenant request paths."""
    token = _unscoped.set(True)
    try:
        yield
    finally:
        _unscoped.reset(token)
