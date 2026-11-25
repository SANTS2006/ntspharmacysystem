from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit

from .models import Invoice, Plan, Subscription


def _next_number() -> str:
    year = timezone.now().year
    n = Invoice.objects.filter(number__startswith=f"INV-{year}-").count() + 1
    return f"INV-{year}-{n:05d}"


@transaction.atomic
def issue_invoice(*, pharmacy, plan: Plan, actor, due_days=14, request=None) -> Invoice:
    inv = Invoice.objects.create(number=_next_number(), pharmacy=pharmacy, plan=plan, amount=plan.price,
                                 currency=plan.currency, due_date=timezone.now().date() + timedelta(days=due_days))
    Subscription.objects.update_or_create(pharmacy=pharmacy, defaults={"plan": plan})
    audit.record("billing.invoice_issued", actor=actor, tenant=pharmacy, target=inv, request=request,
                 amount=str(inv.amount))
    return inv


@transaction.atomic
def mark_paid(invoice_id: int, *, method: str, reference: str, actor, request=None) -> Invoice:
    inv = Invoice.objects.select_for_update(of=("self",)).get(pk=invoice_id)
    if inv.status != Invoice.Status.ISSUED:
        raise ValidationError({"detail": f"Only issued invoices can be paid (current: {inv.status})."})
    if not reference:
        raise ValidationError({"payment_reference": "A payment reference is required."})
    if Invoice.objects.filter(payment_reference=reference).exists():
        raise ValidationError({"payment_reference": "This payment reference was already recorded."})
    inv.status, inv.paid_at, inv.payment_method, inv.payment_reference = Invoice.Status.PAID, timezone.now(), method, reference
    inv.save()
    Subscription.objects.filter(pharmacy=inv.pharmacy).update(
        status=Subscription.Status.ACTIVE, current_period_end=timezone.now().date() + timedelta(days=31))
    audit.record("billing.invoice_paid", actor=actor, tenant=inv.pharmacy, target=inv, request=request,
                 method=method, reference=reference)
    return inv


@transaction.atomic
def refund(invoice_id: int, *, amount: Decimal, reason: str, actor, request=None) -> Invoice:
    inv = Invoice.objects.select_for_update(of=("self",)).get(pk=invoice_id)
    if inv.status not in (Invoice.Status.PAID,):
        raise ValidationError({"detail": "Only paid invoices can be refunded."})
    if amount <= 0 or inv.refunded_amount + amount > inv.amount:
        raise ValidationError({"amount": "Refund must be positive and not exceed the amount paid."})
    inv.refunded_amount += amount
    inv.refunded_at = timezone.now()
    if inv.refunded_amount == inv.amount:
        inv.status = Invoice.Status.REFUNDED
    inv.save()
    audit.record("billing.invoice_refunded", actor=actor, tenant=inv.pharmacy, target=inv, request=request,
                 amount=str(amount), reason=reason)
    return inv


@transaction.atomic
def void_invoice(invoice_id: int, *, actor, request=None) -> Invoice:
    inv = Invoice.objects.select_for_update(of=("self",)).get(pk=invoice_id)
    if inv.status != Invoice.Status.ISSUED:
        raise ValidationError({"detail": "Only unpaid issued invoices can be voided."})
    inv.status = Invoice.Status.VOID
    inv.save()
    audit.record("billing.invoice_voided", actor=actor, tenant=inv.pharmacy, target=inv, request=request)
    return inv
