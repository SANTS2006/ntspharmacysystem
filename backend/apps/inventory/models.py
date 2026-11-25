from django.db import models

from apps.core.models import TenantOwnedModel


class Batch(TenantOwnedModel):
    """Batch-level stock at one branch. Never deleted: history is kept; stock is zeroed by audited movements."""

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        QUARANTINED = "quarantined", "Quarantined"
        RECALLED = "recalled", "Recalled"
        DAMAGED = "damaged", "Damaged"

    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="batches")
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="batches")
    batch_number = models.CharField(max_length=60)
    supplier = models.ForeignKey("procurement.Supplier", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    supplier_name = models.CharField(max_length=200, blank=True)  # denormalised for history/free-text receipts
    purchase_date = models.DateField()
    manufacturing_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)  # null only for medicines with has_expiry=False
    quantity_received = models.PositiveIntegerField()
    quantity_available = models.PositiveIntegerField()
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)  # null => medicine price
    storage_location = models.CharField(max_length=100, blank=True)
    received_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    status_reason = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "branch", "medicine", "batch_number"], name="uniq_batch_per_branch_medicine"),
            models.CheckConstraint(condition=models.Q(quantity_available__lte=models.F("quantity_received")), name="batch_available_lte_received"),
        ]
        indexes = [models.Index(fields=["tenant", "branch", "medicine", "expiry_date"]), models.Index(fields=["tenant", "expiry_date"])]
        ordering = ["expiry_date", "id"]


class StockMovement(TenantOwnedModel):
    """Append-only ledger of every quantity change."""

    class Type(models.TextChoices):
        RECEIPT = "receipt"
        SALE = "sale"
        ADJUSTMENT = "adjustment"
        TRANSFER_OUT = "transfer_out"
        TRANSFER_IN = "transfer_in"
        RETURN = "return"
        DAMAGE = "damage"
        EXPIRY_WRITEOFF = "expiry_writeoff"
        RECALL = "recall"
        PURCHASE_RETURN = "purchase_return"
        DISPENSE = "dispense"

    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="movements")
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    movement_type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    quantity_change = models.IntegerField()  # signed
    previous_quantity = models.PositiveIntegerField()
    new_quantity = models.PositiveIntegerField()
    user = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    reason = models.CharField(max_length=255, blank=True)
    reference_type = models.CharField(max_length=30, blank=True)  # purchase / sale / transfer / adjustment ...
    reference_id = models.CharField(max_length=40, blank=True)

    class Meta(TenantOwnedModel.Meta):
        indexes = [models.Index(fields=["tenant", "branch", "-created_at"]), models.Index(fields=["tenant", "medicine", "-created_at"])]
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Stock movements are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Stock movements cannot be deleted.")


class StockTransfer(TenantOwnedModel):
    """Executed atomically (out of source + into destination in one transaction). In-transit staging is future work."""
    from_branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    to_branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="+")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    reason = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="transfer_qty_positive")]
        ordering = ["-created_at"]
