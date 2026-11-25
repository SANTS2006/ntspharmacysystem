from django.db import models

from apps.core.models import TenantOwnedModel
from .validators import validate_prescription_file


class Patient(TenantOwnedModel):
    """Patient health information: sensitive. Access is permission- and branch-scoped; document/record views are audited."""
    full_name = models.CharField(max_length=200)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    allergies = models.JSONField(default=list, blank=True)  # list of free-text allergens, e.g. ["penicillin"]
    is_pregnant = models.BooleanField(default=False)
    user = models.OneToOneField("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")  # customer account (Phase 8)
    branch = models.ForeignKey("tenants.Branch", null=True, on_delete=models.SET_NULL, related_name="+")  # registered at

    class Meta(TenantOwnedModel.Meta):
        indexes = [models.Index(fields=["tenant", "full_name"])]
        ordering = ["full_name"]


class DrugInteraction(TenantOwnedModel):
    """Interaction knowledge is entered by the pharmacy from its own licensed reference. The platform ships NO clinical data."""
    ingredient_a = models.CharField(max_length=200)
    ingredient_b = models.CharField(max_length=200)
    severity = models.CharField(max_length=10, choices=[("info", "Info"), ("warning", "Warning"), ("critical", "Critical")], default="warning")
    description = models.CharField(max_length=500)
    source = models.CharField(max_length=200, blank=True)  # citation of the reference used

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "ingredient_a", "ingredient_b"], name="uniq_interaction_pair")]


class Prescription(TenantOwnedModel):
    class Status(models.TextChoices):
        RECEIVED = "received"
        UNDER_REVIEW = "under_review"
        APPROVED = "approved"
        REJECTED = "rejected"
        PARTIALLY_DISPENSED = "partially_dispensed"
        DISPENSED = "dispensed"
        CANCELLED = "cancelled"
        EXPIRED = "expired"

    reference_number = models.CharField(max_length=30)  # internal RX-YYYY-NNNNN
    external_reference = models.CharField(max_length=60, blank=True)  # number on the paper prescription
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="prescriptions")
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    prescriber_name = models.CharField(max_length=200)
    prescriber_registration = models.CharField(max_length=100, blank=True)
    facility = models.CharField(max_length=200, blank=True)
    prescription_date = models.DateField()
    expiry_date = models.DateField()
    document = models.FileField(upload_to="prescriptions/", blank=True, validators=[validate_prescription_file])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    refills_allowed = models.PositiveSmallIntegerField(default=0)
    refills_used = models.PositiveSmallIntegerField(default=0)
    notes = models.CharField(max_length=500, blank=True)
    entered_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    verification = models.JSONField(default=dict, blank=True)  # checklist the pharmacist confirmed at approval
    rejection_reason = models.CharField(max_length=500, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "reference_number"], name="uniq_rx_reference")]
        indexes = [models.Index(fields=["tenant", "branch", "status"]), models.Index(fields=["tenant", "patient"])]
        ordering = ["-created_at"]


class PrescriptionItem(TenantOwnedModel):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="items")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="+")
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    duration_days = models.PositiveIntegerField(null=True, blank=True)
    quantity_prescribed = models.PositiveIntegerField()
    quantity_dispensed = models.PositiveIntegerField(default=0)  # current refill cycle
    instructions = models.CharField(max_length=300, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity_prescribed__gt=0), name="rx_item_qty_positive"),
            models.CheckConstraint(condition=models.Q(quantity_dispensed__lte=models.F("quantity_prescribed")), name="rx_item_no_over_dispense"),
        ]


class SafetyAlert(TenantOwnedModel):
    """SYSTEM-generated alert. A pharmacist's decision about it is stored in decision_* fields, never mixed into `message`."""
    class Severity(models.TextChoices):
        INFO = "info"
        WARNING = "warning"
        CRITICAL = "critical"

    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="alerts")
    item = models.ForeignKey(PrescriptionItem, null=True, blank=True, on_delete=models.CASCADE, related_name="alerts")
    alert_type = models.CharField(max_length=20)  # allergy | interaction | duplicate_therapy | contraindication | pregnancy
    severity = models.CharField(max_length=10, choices=Severity.choices)
    key = models.CharField(max_length=200)  # dedupe key
    message = models.CharField(max_length=600)
    decision = models.CharField(max_length=12, blank=True)  # "" (open) | acknowledged
    decision_note = models.CharField(max_length=500, blank=True)
    decided_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["prescription", "key"], name="uniq_alert_key")]


class ClinicalIntervention(TenantOwnedModel):
    """A pharmacist's documented clinical action (e.g. called prescriber, changed quantity advice)."""
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="interventions")
    pharmacist = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    intervention_type = models.CharField(max_length=60)
    note = models.TextField()
    outcome = models.CharField(max_length=200, blank=True)


class Dispensing(TenantOwnedModel):
    prescription = models.ForeignKey(Prescription, on_delete=models.PROTECT, related_name="dispensings")
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    dispensed_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    refill_number = models.PositiveSmallIntegerField(default=0)
    notes = models.CharField(max_length=300, blank=True)
    sale_id = models.PositiveBigIntegerField(null=True, blank=True)  # linked by POS in Phase 7 (payment/receipt)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-created_at"]


class DispensingItem(TenantOwnedModel):
    dispensing = models.ForeignKey(Dispensing, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(PrescriptionItem, on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey("inventory.Batch", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()


class ControlledDrugRegisterEntry(TenantOwnedModel):
    """Append-only register of every controlled-medicine dispense (regulatory dispensing record)."""
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey("inventory.Batch", on_delete=models.PROTECT, related_name="+")
    prescription = models.ForeignKey(Prescription, on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()
    balance_after = models.PositiveIntegerField()
    patient_name = models.CharField(max_length=200)
    prescriber_name = models.CharField(max_length=200)
    prescriber_registration = models.CharField(max_length=100, blank=True)
    pharmacist = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-created_at", "-id"]

    def save(self, *a, **k):
        if self.pk is not None:
            raise PermissionError("Controlled drug register entries are immutable.")
        super().save(*a, **k)

    def delete(self, *a, **k):
        raise PermissionError("Controlled drug register entries cannot be deleted.")
