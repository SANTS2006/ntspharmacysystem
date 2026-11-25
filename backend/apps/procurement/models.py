from decimal import Decimal

from django.db import models, transaction

from apps.core.models import TenantOwnedModel


class DocumentSequence(TenantOwnedModel):
    """Per-tenant, per-kind, per-year gap-free-ish counters (row-locked) for human-readable document numbers."""
    kind = models.CharField(max_length=10)
    year = models.PositiveIntegerField()
    last = models.PositiveIntegerField(default=0)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "kind", "year"], name="uniq_sequence")]


def next_number(kind: str) -> str:
    from django.utils import timezone
    year = timezone.localdate().year
    with transaction.atomic():
        seq, _ = DocumentSequence.objects.select_for_update(of=("self",)).get_or_create(kind=kind, year=year)
        seq.last += 1
        seq.save(update_fields=["last", "updated_at"])
    return f"{kind}-{year}-{seq.last:05d}"


class Supplier(TenantOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active"
        INACTIVE = "inactive"

    name = models.CharField(max_length=200)
    company_name = models.CharField(max_length=200, blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=100, blank=True)
    registration_details = models.CharField(max_length=255, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=30)
    payment_details = models.TextField(blank=True)  # bank / mobile money: sensitive, manage-level only
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "name"], name="uniq_supplier_name_per_tenant")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Requisition(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        SUBMITTED = "submitted"
        APPROVED = "approved"
        REJECTED = "rejected"
        CANCELLED = "cancelled"

    number = models.CharField(max_length=30)
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    requested_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    notes = models.CharField(max_length=255, blank=True)
    decided_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_requisition_number")]
        ordering = ["-created_at"]


class RequisitionItem(TenantOwnedModel):
    requisition = models.ForeignKey(Requisition, on_delete=models.CASCADE, related_name="items")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="req_item_qty_positive")]


class PurchaseOrder(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        PENDING_APPROVAL = "pending_approval"
        APPROVED = "approved"
        PARTIALLY_RECEIVED = "partially_received"
        RECEIVED = "received"
        REJECTED = "rejected"
        CANCELLED = "cancelled"

    number = models.CharField(max_length=30)
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="orders")
    requisition = models.ForeignKey(Requisition, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    expected_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    approved_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_po_number")]
        indexes = [models.Index(fields=["tenant", "branch", "status"])]
        ordering = ["-created_at"]


class PurchaseOrderItem(TenantOwnedModel):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="+")
    quantity_ordered = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity_ordered__gt=0), name="po_item_qty_positive"),
            models.CheckConstraint(condition=models.Q(quantity_received__lte=models.F("quantity_ordered")), name="po_item_no_over_receipt"),
        ]


class GoodsReceipt(TenantOwnedModel):
    """Goods received note. Immutable once created; corrections are done through stock adjustments/returns."""
    number = models.CharField(max_length=30)
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    delivery_note = models.CharField(max_length=60, blank=True)
    received_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_grn_number")]
        ordering = ["-created_at"]


class GoodsReceiptItem(TenantOwnedModel):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="items")
    order_item = models.ForeignKey(PurchaseOrderItem, on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey("inventory.Batch", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)


class SupplierInvoice(TenantOwnedModel):
    class Status(models.TextChoices):
        UNPAID = "unpaid"
        PARTIALLY_PAID = "partially_paid"
        PAID = "paid"
        CANCELLED = "cancelled"

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="invoices")
    order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    invoice_number = models.CharField(max_length=60)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    due_date = models.DateField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.UNPAID, db_index=True)
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "supplier", "invoice_number"], name="uniq_supplier_invoice_number"),
            models.CheckConstraint(condition=models.Q(amount__gt=0, amount_paid__gte=0, amount_paid__lte=models.F("amount")), name="supplier_invoice_amounts_valid"),
        ]
        ordering = ["-created_at"]

    @property
    def balance(self):
        return self.amount - self.amount_paid


class SupplierPayment(TenantOwnedModel):
    """Immutable payment record. Duplicate references are rejected."""
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=30)
    reference = models.CharField(max_length=100)
    paid_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "reference"], name="uniq_supplier_payment_reference"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="supplier_payment_positive"),
        ]
        ordering = ["-created_at"]


class PurchaseReturn(TenantOwnedModel):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="returns")
    batch = models.ForeignKey("inventory.Batch", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    credit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0, credit_amount__gte=0), name="purchase_return_valid")]
        ordering = ["-created_at"]
