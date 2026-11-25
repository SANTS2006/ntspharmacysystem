from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation
from apps.core.realtime import notify_topic
from apps.core.tenant_context import get_current_tenant
from apps.notifications.services import render_branded_html, send_email

from .models import Appointment, PharmacyService

ACTIVE = ("requested", "confirmed")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _mail(to, subject, body, template):
    t = get_current_tenant()
    send_email(to=to, subject=subject, text=body, tenant=t, template=template, html_body=render_branded_html(title=subject, pharmacy=t, paragraphs=[body]))


def within_opening_hours(branch, start, end) -> bool:
    """operating_hours is optional JSON like {"mon": {"open": "08:00", "close": "18:00"}}. Missing data means no restriction."""
    hours = branch.operating_hours or {}
    if not hours:
        return True
    local_start, local_end = timezone.localtime(start), timezone.localtime(end)
    day = hours.get(DAYS[local_start.weekday()])
    if not day:
        return False
    o = tuple(int(x) for x in day["open"].split(":"))
    c = tuple(int(x) for x in day["close"].split(":"))
    return (local_start.hour, local_start.minute) >= o and (local_end.hour, local_end.minute) <= c and local_end.date() == local_start.date()


@transaction.atomic
def book(*, customer, service: PharmacyService, branch, start_at: datetime, note="") -> Appointment:
    service = PharmacyService.objects.select_for_update(of=("self",)).get(pk=service.pk)  # serialises bookings of one service so capacity cannot be exceeded
    if not service.is_available or not service.requires_booking:
        raise BusinessRuleViolation("This service cannot be booked online.")
    if branch.status != "active":
        raise ValidationError({"branch": "This branch is not available."})
    allowed = list(service.branches.values_list("pk", flat=True))
    if allowed and branch.pk not in allowed:
        raise ValidationError({"branch": "This service is not offered at that branch."})
    now = timezone.now()
    if start_at < now + timedelta(minutes=15) or start_at > now + timedelta(days=90):
        raise ValidationError({"start_at": "Choose a time between 15 minutes and 90 days from now."})
    end_at = start_at + timedelta(minutes=service.duration_minutes)
    if not within_opening_hours(branch, start_at, end_at):
        raise ValidationError({"start_at": "The branch is closed at that time."})
    taken = Appointment.objects.filter(service=service, branch=branch, status__in=ACTIVE, start_at__lt=end_at, end_at__gt=start_at).count()
    if taken >= service.capacity:
        raise BusinessRuleViolation("That time slot is fully booked. Please choose another time.")
    if Appointment.objects.filter(customer=customer, status__in=ACTIVE, start_at__lt=end_at, end_at__gt=start_at).exists():
        raise ValidationError({"start_at": "You already have an appointment at that time."})
    a = Appointment.objects.create(customer=customer, service=service, branch=branch, start_at=start_at, end_at=end_at, customer_note=note[:300])
    audit.record("appointment.requested", actor=customer, target=a, branch_id=branch.pk)
    notify_topic(a.tenant_id, branch.pk, "orders", "appointment.requested", {"id": a.pk, "kind": "appointment"})
    _mail(customer.email, f"Appointment request received: {service.name}", f"We received your request for {service.name} on {timezone.localtime(start_at):%Y-%m-%d %H:%M}. We will confirm it shortly.", "appointment_requested")
    return a


@transaction.atomic
def set_status(pk, status: str, *, actor, note="") -> Appointment:
    a = Appointment.objects.select_for_update(of=("self",)).select_related("customer", "service").get(pk=pk)
    flow = {"requested": {"confirmed", "cancelled"}, "confirmed": {"completed", "cancelled", "no_show"}}
    if status not in flow.get(a.status, set()):
        raise BusinessRuleViolation(f"A {a.status.replace('_', ' ')} appointment cannot become {status.replace('_', ' ')}.")
    if status in ("completed", "no_show") and a.start_at > timezone.now():
        raise BusinessRuleViolation("The appointment has not started yet.")
    a.status, a.handled_by, a.staff_note = status, actor, note[:300] or a.staff_note
    a.save()
    audit.record(f"appointment.{status}", actor=actor, target=a, branch_id=a.branch_id)
    if status in ("confirmed", "cancelled"):
        when = f"{timezone.localtime(a.start_at):%Y-%m-%d %H:%M}"
        _mail(a.customer.email, f"Appointment {status}: {a.service.name}", f"Your appointment for {a.service.name} on {when} is {status}." + (f" Note: {note}" if note else ""), f"appointment_{status}")
    return a


@transaction.atomic
def customer_cancel(pk, *, customer) -> Appointment:
    a = Appointment.objects.select_for_update(of=("self",)).get(pk=pk, customer=customer)
    if a.status not in ACTIVE or a.start_at <= timezone.now() + timedelta(hours=1):
        raise BusinessRuleViolation("This appointment can no longer be cancelled online. Please contact the pharmacy.")
    a.status = "cancelled"
    a.save(update_fields=["status", "updated_at"])
    audit.record("appointment.cancelled_by_customer", actor=customer, target=a, branch_id=a.branch_id)
    return a
