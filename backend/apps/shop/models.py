from decimal import Decimal

from django.db import models

from apps.core.models import TenantOwnedModel

ZERO = Decimal("0.00")


def default_prefs():
    return {"email_orders": True, "email_marketing": False}


class CustomerProfile(TenantOwnedModel):
    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="customer_profile")
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    delivery_addresses = models.JSONField(default=list, blank=True)  # [{"label","address"}]
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    notification_prefs = models.JSONField(default=default_prefs, blank=True)
    google_sub = models.CharField(max_length=64, null=True, blank=True)
    terms_version = models.CharField(max_length=20, blank=True)  # version of Terms/Privacy accepted
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    terms_accepted_via = models.CharField(max_length=10, blank=True)  # password | google

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "google_sub"], condition=models.Q(google_sub__isnull=False), name="uniq_google_sub_per_tenant")]


class EmailVerification(models.Model):
    """Six-character code. Only a salted hash is stored; single active code per user."""
    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="email_verification")
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)


class Order(TenantOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending"
        AWAITING_PRESCRIPTION = "awaiting_prescription"
        PRESCRIPTION_APPROVED = "prescription_approved"
        PRESCRIPTION_REJECTED = "prescription_rejected"
        AWAITING_PAYMENT = "awaiting_payment"
        PAYMENT_CONFIRMED = "payment_confirmed"
        PROCESSING = "processing"
        PREPARING = "preparing"
        READY_FOR_PICKUP = "ready_for_pickup"
        OUT_FOR_DELIVERY = "out_for_delivery"
        DELIVERED = "delivered"
        COMPLETED = "completed"
        CANCELLED = "cancelled"
        REFUND_REQUESTED = "refund_requested"
        REFUNDED = "refunded"

    reference_number = models.CharField(max_length=30)
    idempotency_key = models.CharField(max_length=80)
    customer = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="orders")
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    fulfilment = models.CharField(max_length=10, choices=[("pickup", "Pickup"), ("delivery", "Delivery")])
    delivery_address = models.CharField(max_length=300, blank=True)
    payment_method = models.CharField(max_length=20)  # cash_on_pickup | cash_on_delivery (gateway methods arrive in Phase 9)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    delivery_fee = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    requires_prescription = models.BooleanField(default=False)
    prescription = models.ForeignKey("prescriptions.Prescription", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.CharField(max_length=300, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "reference_number"], name="uniq_order_reference"),
            models.UniqueConstraint(fields=["tenant", "idempotency_key"], name="uniq_order_idempotency"),
        ]
        indexes = [models.Index(fields=["tenant", "branch", "status"]), models.Index(fields=["tenant", "customer", "-created_at"])]
        ordering = ["-created_at"]


class OrderLine(TenantOwnedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    stock_deducted = models.BooleanField(default=False)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="order_line_qty_positive")]


class OrderEvent(TenantOwnedModel):
    """Append-only status history (also drives customer notifications)."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24)
    actor = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=300, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["created_at", "id"]

    def save(self, *a, **k):
        if self.pk is not None:
            raise PermissionError("Order events are immutable.")
        super().save(*a, **k)


class QrRequest(TenantOwnedModel):
    """A shopping/assistance request from the branch QR menu. NOT a sale or an order."""
    class Status(models.TextChoices):
        NEW = "new"
        REVIEWING = "reviewing"
        READY = "ready"
        CLOSED = "closed"
        CANCELLED = "cancelled"

    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=10, choices=[("shopping", "Shopping"), ("assistance", "Assistance")], default="shopping")
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=30)
    note = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW, db_index=True)
    requires_prescription = models.BooleanField(default=False)
    handled_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    staff_note = models.CharField(max_length=500, blank=True)

    class Meta(TenantOwnedModel.Meta):
        indexes = [models.Index(fields=["tenant", "branch", "status"])]
        ordering = ["-created_at"]


class QrRequestItem(TenantOwnedModel):
    request = models.ForeignKey(QrRequest, on_delete=models.CASCADE, related_name="items")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()
