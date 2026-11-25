from django.core.exceptions import PermissionDenied
from django.db import models

from .tenant_context import get_current_tenant, is_unscoped


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantManager(models.Manager):
    """Fail-closed manager: with no tenant context (and no explicit unscoped()) it returns nothing."""

    def get_queryset(self):
        qs = super().get_queryset()
        if is_unscoped():
            return qs
        tenant = get_current_tenant()
        if tenant is None:
            return qs.none()
        return qs.filter(tenant_id=tenant.pk)


class TenantOwnedModel(TimeStampedModel):
    """Base for every record owned by a pharmacy. `objects` is tenant-scoped; `all_objects` is not."""

    tenant = models.ForeignKey("tenants.Pharmacy", on_delete=models.PROTECT, related_name="+", editable=False)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "all_objects"

    def save(self, *args, **kwargs):
        current = get_current_tenant()
        if self.tenant_id is None:
            if current is None:
                raise PermissionDenied("Cannot save a tenant-owned record without a tenant context.")
            self.tenant_id = current.pk
        elif current is not None and not is_unscoped() and self.tenant_id != current.pk:
            raise PermissionDenied("Cross-tenant write blocked.")
        super().save(*args, **kwargs)
