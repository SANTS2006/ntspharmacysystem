from django.db import models

from apps.core.models import TenantOwnedModel


class Delivery(TenantOwnedModel):
    class Status(models.TextChoices):
        ASSIGNED = "assigned"
        PICKED_UP = "picked_up"
        DELIVERED = "delivered"
        FAILED = "failed"
        CANCELLED = "cancelled"  # reassigned or order cancelled

    order = models.ForeignKey("shop.Order", on_delete=models.PROTECT, related_name="deliveries")
    driver = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="deliveries")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ASSIGNED, db_index=True)
    assigned_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    picked_up_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["order"], condition=models.Q(status__in=["assigned", "picked_up"]), name="one_active_delivery_per_order")]
        ordering = ["-created_at"]
