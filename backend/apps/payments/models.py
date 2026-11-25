from decimal import Decimal

from django.db import models

from apps.core.models import TenantOwnedModel, TimeStampedModel


class PaymentProviderConfig(TenantOwnedModel):
    """Per-pharmacy provider credentials (funds must land in the PHARMACY's account). Secrets are encrypted at rest and never returned by any API."""
    provider = models.CharField(max_length=20, default="monime")
    enabled = models.BooleanField(default=False)
    space_id = models.CharField(max_length=100, blank=True)
    access_token_enc = models.TextField(blank=True)
    webhook_secret_enc = models.TextField(blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "provider"], name="uniq_provider_config")]


class PaymentAttempt(TenantOwnedModel):
    class Status(models.TextChoices):
        INITIATED = "initiated"
        PENDING = "pending"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELLED = "cancelled"
        EXPIRED = "expired"

    order = models.ForeignKey("shop.Order", on_delete=models.PROTECT, related_name="payment_attempts")
    reference = models.CharField(max_length=40)  # our unique payment reference; also the provider idempotency key
    provider = models.CharField(max_length=20, default="monime")
    provider_session_id = models.CharField(max_length=100, null=True, blank=True)
    redirect_url = models.URLField(max_length=500, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.INITIATED, db_index=True)
    status_detail = models.CharField(max_length=200, blank=True)
    needs_refund = models.BooleanField(default=False)  # paid, but the order could no longer accept the payment
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "reference"], name="uniq_payment_reference_per_tenant"),
            models.UniqueConstraint(fields=["provider", "provider_session_id"], condition=models.Q(provider_session_id__isnull=False), name="uniq_provider_session"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_attempt_positive"),
        ]
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]
        ordering = ["-created_at"]


class WebhookEvent(TimeStampedModel):
    """Every webhook delivery, keyed by the provider's event id (duplicate deliveries are no-ops). Not tenant-owned: stored per tenant slug path."""
    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=100)
    tenant = models.ForeignKey("tenants.Pharmacy", null=True, on_delete=models.SET_NULL, related_name="+")
    name = models.CharField(max_length=60)
    status = models.CharField(max_length=12, default="received")  # received | processed | ignored | failed
    detail = models.CharField(max_length=300, blank=True)
    object_id = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="uniq_webhook_event")]
        ordering = ["-created_at"]


class OrderReceipt(TenantOwnedModel):
    """Permanent receipt for an online order, created when payment is confirmed."""
    order = models.OneToOneField("shop.Order", on_delete=models.PROTECT, related_name="receipt")
    number = models.CharField(max_length=30)
    data = models.JSONField()

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_order_receipt_number")]

    def save(self, *a, **k):
        if self.pk is not None:
            raise PermissionError("Receipts are immutable.")
        super().save(*a, **k)

    def delete(self, *a, **k):
        raise PermissionError("Receipts cannot be deleted.")


class OrderRefund(TenantOwnedModel):
    """Refund record for an online order. Money movement is done outside the platform (gateway refund API not integrated); this records and audits it."""
    order = models.ForeignKey("shop.Order", on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=30)
    reference = models.CharField(max_length=100)
    reason = models.CharField(max_length=255)
    processed_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="order_refund_positive"),
            models.UniqueConstraint(fields=["tenant", "reference"], name="uniq_order_refund_reference"),
        ]
