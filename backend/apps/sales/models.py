from decimal import Decimal

from django.db import models

from apps.core.models import TenantOwnedModel

ZERO = Decimal("0.00")


class Shift(TenantOwnedModel):
    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"

    cashier = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN, db_index=True)
    opening_cash = models.DecimalField(max_digits=14, decimal_places=2)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    counted_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)  # frozen at close
    discrepancy = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["cashier"], condition=models.Q(status="open"), name="one_open_shift_per_cashier"),
            models.CheckConstraint(condition=models.Q(opening_cash__gte=0), name="shift_opening_nonnegative"),
        ]
        ordering = ["-opened_at"]


class CashMovement(TenantOwnedModel):
    class Kind(models.TextChoices):
        WITHDRAWAL = "withdrawal"
        DEPOSIT = "deposit"

    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"

    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="cash_movements")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    decided_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="cash_movement_positive")]


class Sale(TenantOwnedModel):
    """Completed sales are never edited. Corrections happen through SaleReturn (credit notes)."""
    class Status(models.TextChoices):
        COMPLETED = "completed"
        PARTIALLY_PAID = "partially_paid"
        PARTIALLY_RETURNED = "partially_returned"
        RETURNED = "returned"
        CANCELLED = "cancelled"

    reference_number = models.CharField(max_length=30)
    idempotency_key = models.CharField(max_length=80)
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="sales")
    cashier = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED, db_index=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)  # after line discounts, before tax
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    change_due = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "reference_number"], name="uniq_sale_reference"),
            models.UniqueConstraint(fields=["tenant", "idempotency_key"], name="uniq_sale_idempotency"),
            models.CheckConstraint(condition=models.Q(total__gte=0, amount_paid__gte=0), name="sale_amounts_nonnegative"),
        ]
        indexes = [models.Index(fields=["tenant", "branch", "-created_at"]), models.Index(fields=["tenant", "cashier", "-created_at"])]
        ordering = ["-created_at"]

    @property
    def balance(self):
        return max(self.total - self.amount_paid, ZERO)


class SaleLine(TenantOwnedModel):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="+")
    dispensing_item = models.ForeignKey("prescriptions.DispensingItem", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)  # net + tax
    quantity_returned = models.PositiveIntegerField(default=0)
    amount_refunded = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="sale_line_qty_positive"),
            models.CheckConstraint(condition=models.Q(quantity_returned__lte=models.F("quantity")), name="sale_line_returns_within_qty"),
        ]


class SaleAllocation(TenantOwnedModel):
    """Which batch(es) a line came from, for traceability, recalls and returns."""
    line = models.ForeignKey(SaleLine, on_delete=models.CASCADE, related_name="allocations")
    batch = models.ForeignKey("inventory.Batch", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()
    quantity_returned = models.PositiveIntegerField(default=0)


class Payment(TenantOwnedModel):
    class Method(models.TextChoices):
        CASH = "cash"
        MOBILE_MONEY = "mobile_money"
        CARD = "card"
        BANK_TRANSFER = "bank_transfer"

    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="payments")
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=15, choices=Method.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)  # amount APPLIED to the sale (cash: net of change)
    reference = models.CharField(max_length=100, blank=True)  # provider/terminal reference for non-cash
    received_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "method", "reference"], condition=~models.Q(reference=""), name="uniq_payment_reference"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_positive"),
        ]


class Receipt(TenantOwnedModel):
    """Permanent snapshot of the sale as it was rendered to the customer."""
    sale = models.OneToOneField(Sale, on_delete=models.PROTECT, related_name="receipt")
    number = models.CharField(max_length=30)
    data = models.JSONField()

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_receipt_number")]

    def save(self, *a, **k):
        if self.pk is not None:
            raise PermissionError("Receipts are immutable.")
        super().save(*a, **k)

    def delete(self, *a, **k):
        raise PermissionError("Receipts cannot be deleted.")


class SaleReturn(TenantOwnedModel):
    """Credit note / refund record."""
    number = models.CharField(max_length=30)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="returns")
    shift = models.ForeignKey(Shift, null=True, on_delete=models.PROTECT, related_name="refunds")  # set for cash refunds
    refund_method = models.CharField(max_length=15)
    refund_reference = models.CharField(max_length=100, blank=True)
    refund_total = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255)
    is_cancellation = models.BooleanField(default=False)
    processed_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_credit_note_number")]
        ordering = ["-created_at"]


class SaleReturnLine(TenantOwnedModel):
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name="lines")
    sale_line = models.ForeignKey(SaleLine, on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    restocked_quantity = models.PositiveIntegerField(default=0)
