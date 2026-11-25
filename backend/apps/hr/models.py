from django.db import models

from apps.core.models import TenantOwnedModel
from apps.prescriptions.validators import validate_prescription_file  # same upload rules: type allow-list, magic bytes, size cap


class StaffProfile(TenantOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active"
        ON_LEAVE = "on_leave"
        SUSPENDED = "suspended"
        TERMINATED = "terminated"

    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="staff_profile")
    staff_id = models.CharField(max_length=30)
    employment_date = models.DateField()
    employment_status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    job_title = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    terminated_on = models.DateField(null=True, blank=True)
    termination_reason = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "staff_id"], name="uniq_staff_id_per_tenant")]


class StaffDocument(TenantOwnedModel):
    """Sensitive HR documents (contracts, IDs). Only hr.sensitive holders may list or download; every download is audited."""
    profile = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=40)
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to="staff-documents/", validators=[validate_prescription_file])
    uploaded_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")


class DisciplinaryRecord(TenantOwnedModel):
    profile = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name="disciplinary_records")
    date = models.DateField()
    category = models.CharField(max_length=60)
    description = models.TextField()
    action_taken = models.CharField(max_length=200, blank=True)
    issued_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    def save(self, *a, **k):
        if self.pk is not None:
            raise PermissionError("Disciplinary records cannot be edited; add a new record instead.")
        super().save(*a, **k)

    def delete(self, *a, **k):
        raise PermissionError("Disciplinary records cannot be deleted.")


class AttendanceRecord(TenantOwnedModel):
    class Status(models.TextChoices):
        PRESENT = "present"
        LATE = "late"
        ABSENT = "absent"
        ON_LEAVE = "on_leave"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="attendance")
    branch = models.ForeignKey("tenants.Branch", null=True, on_delete=models.SET_NULL, related_name="+")
    date = models.DateField(db_index=True)
    clock_in = models.DateTimeField(null=True, blank=True)
    clock_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PRESENT)
    source = models.CharField(max_length=10, default="self")  # self | manual
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "user", "date"], name="uniq_attendance_per_day")]
        ordering = ["-date"]


class WorkShift(TenantOwnedModel):
    """Planned working shift (not the POS cash shift)."""
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="work_shifts")
    branch = models.ForeignKey("tenants.Branch", on_delete=models.CASCADE, related_name="+")
    date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    notes = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "user", "date", "start_time"], name="uniq_work_shift")]
        ordering = ["date", "start_time"]


class LeaveType(TenantOwnedModel):
    name = models.CharField(max_length=60)
    days_per_year = models.PositiveIntegerField(default=0)  # 0 = no annual cap
    is_paid = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "name"], name="uniq_leave_type")]


class LeaveRequest(TenantOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"
        CANCELLED = "cancelled"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.PositiveIntegerField()  # calendar days, inclusive
    reason = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    decided_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decision_note = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="leave_dates_ordered")]
        ordering = ["-start_date"]
