from datetime import date, datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation
from apps.core.tenant_context import get_current_tenant
from apps.procurement.models import next_number

from .models import AttendanceRecord, LeaveRequest, LeaveType, StaffProfile, WorkShift

DEFAULT_LEAVE_TYPES = [("Annual leave", 21, True), ("Sick leave", 10, True), ("Unpaid leave", 0, False)]


def staff_scope(actor: User):
    """Staff records the actor may see: pharmacy-level roles see everyone; branch-scoped roles only their own branch."""
    qs = StaffProfile.objects.select_related("user", "user__role", "user__branch")
    return qs.filter(user__branch_id=actor.branch_id) if actor.is_branch_scoped else qs


def user_scope(actor: User):
    qs = User.objects.filter(tenant=actor.tenant).exclude(role__code="customer")
    return qs.filter(branch_id=actor.branch_id) if actor.is_branch_scoped else qs


# ---------------- staff records ----------------
@transaction.atomic
def create_profile(*, actor, target: User, employment_date: date, staff_id="", **extra) -> StaffProfile:
    if target.tenant_id != actor.tenant_id or (target.role_id and target.role.code == "customer"):
        raise ValidationError({"user": "Select a staff member of this pharmacy."})
    if hasattr(target, "staff_profile"):
        raise ValidationError({"user": "This staff member already has an HR record."})
    sid = staff_id.strip() or next_number("STF")
    if StaffProfile.objects.filter(staff_id=sid).exists():
        raise ValidationError({"staff_id": "This staff ID is already in use."})
    p = StaffProfile.objects.create(user=target, staff_id=sid, employment_date=employment_date, **extra)
    audit.record("hr.profile_created", actor=actor, target=p, branch_id=target.branch_id, staff=target.pk)
    return p


@transaction.atomic
def terminate(profile_id, *, actor, on: date, reason: str) -> StaffProfile:
    p = StaffProfile.objects.select_for_update(of=("self",)).select_related("user").get(pk=profile_id)
    if p.employment_status == "terminated":
        raise BusinessRuleViolation("This employment has already ended.")
    if p.user_id == actor.pk:
        raise PermissionDenied("You cannot terminate your own employment.")
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required."})
    p.employment_status, p.terminated_on, p.termination_reason = "terminated", on, reason[:255]
    p.save()
    u = p.user
    u.is_active = False
    u.credential_version += 1  # all sessions end immediately
    u.save(update_fields=["is_active", "credential_version"])
    audit.record("hr.terminated", actor=actor, target=p, branch_id=u.branch_id, staff=u.pk, reason=reason)
    return p


# ---------------- attendance ----------------
def _workday_start() -> time:
    h, m = ((get_current_tenant().settings or {}).get("workday_start", "08:30")).split(":")
    return time(int(h), int(m))


@transaction.atomic
def clock_in(user: User) -> AttendanceRecord:
    today = timezone.localdate()
    now = timezone.now()
    grace = int((get_current_tenant().settings or {}).get("late_grace_minutes", 15))
    late = timezone.localtime(now).time() > (datetime.combine(today, _workday_start()) + timedelta(minutes=grace)).time()
    rec, created = AttendanceRecord.objects.select_for_update(of=("self",)).get_or_create(user=user, date=today, defaults={"branch": user.branch, "clock_in": now, "status": "late" if late else "present", "source": "self"})
    if not created:
        if rec.clock_in:
            raise BusinessRuleViolation("You have already clocked in today.")
        rec.clock_in, rec.status, rec.source = now, ("late" if late else "present"), "self"  # a manager-marked absence can be overridden by an actual clock-in
        rec.save()
    audit.record("hr.clock_in", actor=user, target=rec, branch_id=user.branch_id)
    return rec


@transaction.atomic
def clock_out(user: User) -> AttendanceRecord:
    rec = AttendanceRecord.objects.select_for_update(of=("self",)).filter(user=user, date=timezone.localdate()).first()
    if rec is None or rec.clock_in is None:
        raise BusinessRuleViolation("You have not clocked in today.")
    if rec.clock_out:
        raise BusinessRuleViolation("You have already clocked out today.")
    rec.clock_out = timezone.now()
    rec.save(update_fields=["clock_out", "updated_at"])
    return rec


@transaction.atomic
def manual_attendance(*, actor: User, target: User, on: date, status: str, clock_in=None, clock_out=None, note="") -> AttendanceRecord:
    if status not in {s.value for s in AttendanceRecord.Status}:
        raise ValidationError({"status": "Unknown status."})
    if on > timezone.localdate():
        raise ValidationError({"date": "Attendance cannot be recorded for a future date."})
    if clock_in and clock_out and clock_out < clock_in:
        raise ValidationError({"clock_out": "Clock-out cannot be before clock-in."})
    rec, _ = AttendanceRecord.objects.select_for_update(of=("self",)).get_or_create(user=target, date=on, defaults={"branch": target.branch})
    old = rec.status
    rec.status, rec.clock_in, rec.clock_out, rec.note, rec.source, rec.recorded_by = status, clock_in, clock_out, note[:255], "manual", actor
    rec.save()
    audit.record("hr.attendance_adjusted", actor=actor, target=rec, branch_id=target.branch_id, staff=target.pk, date=str(on), old=old, new=status)
    return rec


# ---------------- work shifts ----------------
@transaction.atomic
def schedule_shift(*, actor, target: User, branch, on: date, start: time, end: time, notes="") -> WorkShift:
    if end <= start:
        raise ValidationError({"end_time": "The shift must end after it starts."})
    clash = WorkShift.objects.filter(user=target, date=on, start_time__lt=end, end_time__gt=start).exists()
    if clash:
        raise ValidationError({"detail": "This staff member already has an overlapping shift."})
    if actor.is_branch_scoped and branch.pk != actor.branch_id:
        raise PermissionDenied("You can only schedule your own branch.")
    return WorkShift.objects.create(user=target, branch=branch, date=on, start_time=start, end_time=end, notes=notes[:200], created_by=actor)


# ---------------- leave ----------------
def ensure_leave_types():
    if not LeaveType.objects.exists():
        for name, days, paid in DEFAULT_LEAVE_TYPES:
            LeaveType.objects.get_or_create(name=name, defaults={"days_per_year": days, "is_paid": paid})


def leave_used(user, leave_type, year, statuses=("approved",)) -> int:
    return LeaveRequest.objects.filter(user=user, leave_type=leave_type, status__in=statuses, start_date__year=year).aggregate(t=Sum("days"))["t"] or 0


def balance(user, leave_type, year=None):
    year = year or timezone.localdate().year
    used = leave_used(user, leave_type, year)
    allowance = leave_type.days_per_year
    return {"leave_type": leave_type.pk, "name": leave_type.name, "allowance": allowance, "used": used, "pending": leave_used(user, leave_type, year, ("pending",)),
            "remaining": (allowance - used) if allowance else None, "paid": leave_type.is_paid}


@transaction.atomic
def request_leave(*, user: User, leave_type: LeaveType, start: date, end: date, reason="") -> LeaveRequest:
    if not leave_type.is_active:
        raise ValidationError({"leave_type": "This leave type is not available."})
    if end < start or (end - start).days > 365:
        raise ValidationError({"end_date": "Choose valid dates."})
    days = (end - start).days + 1
    if LeaveRequest.objects.filter(user=user, status__in=("pending", "approved"), start_date__lte=end, end_date__gte=start).exists():
        raise ValidationError({"start_date": "You already have leave requested or approved for these dates."})
    if leave_type.days_per_year:
        committed = leave_used(user, leave_type, start.year, ("approved", "pending"))
        if committed + days > leave_type.days_per_year:
            raise ValidationError({"days": f"This exceeds your {leave_type.name} allowance ({leave_type.days_per_year - committed} days left)."})
    lr = LeaveRequest.objects.create(user=user, leave_type=leave_type, start_date=start, end_date=end, days=days, reason=reason[:300])
    audit.record("hr.leave_requested", actor=user, target=lr, branch_id=user.branch_id, days=days)
    return lr


@transaction.atomic
def decide_leave(pk, *, actor: User, approve: bool, note="") -> LeaveRequest:
    lr = LeaveRequest.objects.select_for_update(of=("self",)).select_related("user").get(pk=pk)
    if lr.status != "pending":
        raise BusinessRuleViolation("This request was already decided.")
    if lr.user_id == actor.pk:
        raise PermissionDenied("You cannot decide your own leave request.")
    if actor.is_branch_scoped and lr.user.branch_id != actor.branch_id:
        raise PermissionDenied("This staff member belongs to another branch.")
    lr.status, lr.decided_by, lr.decision_note = ("approved" if approve else "rejected"), actor, note[:255]
    lr.save()
    audit.record("hr.leave_approved" if approve else "hr.leave_rejected", actor=actor, target=lr, branch_id=lr.user.branch_id, staff=lr.user_id)
    return lr


@transaction.atomic
def cancel_leave(pk, *, actor: User) -> LeaveRequest:
    lr = LeaveRequest.objects.select_for_update(of=("self",)).get(pk=pk, user=actor)
    if lr.status not in ("pending", "approved") or (lr.status == "approved" and lr.start_date <= timezone.localdate()):
        raise BusinessRuleViolation("This leave can no longer be cancelled.")
    lr.status = "cancelled"
    lr.save(update_fields=["status", "updated_at"])
    audit.record("hr.leave_cancelled", actor=actor, target=lr, branch_id=actor.branch_id)
    return lr
