from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.notifications import inapp
from apps.payments import monime

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
    inapp.push_staff(pharmacy.pk, "settings.manage", None, kind="billing", level="warning", title=f"New subscription invoice {inv.number}",
                     body=f"{inv.currency} {inv.amount} due {inv.due_date:%d %b %Y}.", link="/subscription")
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
    inapp.push_staff(inv.pharmacy_id, "settings.manage", None, kind="billing", level="success", title=f"Invoice {inv.number} paid",
                     body=f"{inv.currency} {inv.amount} received.", link="/subscription")
    inapp.push(inapp.platform_admins(), kind="billing", level="success", title=f"{inv.pharmacy.name} paid {inv.number}",
               body=f"{inv.currency} {inv.amount} by {method}.", link="/billing", exclude=actor)
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


# ---------------- paying an invoice online (Monime checkout) ----------------
def start_invoice_checkout(invoice_id: int, *, actor, request=None) -> Invoice:
    current = Invoice.objects.get(pk=invoice_id)
    if current.provider_session_id and current.status == Invoice.Status.ISSUED:
        apply_invoice_session(current.pk, monime.retrieve_checkout_session(current.provider_session_id))
    return _open_invoice_checkout(invoice_id, actor=actor, request=request)


@transaction.atomic
def _open_invoice_checkout(invoice_id: int, *, actor, request=None) -> Invoice:
    from apps.core.links import site_url
    inv = Invoice.objects.select_for_update(of=("self",)).select_related("pharmacy").get(pk=invoice_id)
    if inv.status != Invoice.Status.ISSUED:
        raise ValidationError({"detail": "This invoice is not awaiting payment."})
    if inv.currency not in monime.CURRENCIES:
        raise ValidationError({"detail": "Mobile money payments are only available for SLE or USD invoices."})
    if inv.checkout_url:  # still open at the provider
        return inv
    inv.checkout_attempt += 1
    reference = f"{inv.number}-{inv.checkout_attempt}"
    base = site_url(inv.pharmacy.slug, "/admin/subscription")
    session = monime.create_checkout_session(key=monime.idempotency_key("inv", reference), reference=reference,
                                             name=f"Subscription {inv.number}", amount_minor=monime.to_minor(inv.amount), currency=inv.currency,
                                             success_url=f"{base}?payment=return", cancel_url=f"{base}?payment=cancelled")
    inv.provider_session_id, inv.checkout_url = str(session.get("id", ""))[:100], str(session.get("redirectUrl", ""))[:500]
    if not inv.provider_session_id or not inv.checkout_url.startswith("https://"):
        raise monime.ProviderError("The payment provider returned an invalid checkout session.")
    inv.save()
    audit.record("billing.checkout_started", actor=actor, tenant=inv.pharmacy, target=inv, request=request)
    return inv


@transaction.atomic
def apply_invoice_session(invoice_id: int, session: dict) -> str:
    """Only the provider's own answer reaches this function."""
    inv = Invoice.objects.select_for_update(of=("self",)).select_related("pharmacy").get(pk=invoice_id)
    if inv.status != Invoice.Status.ISSUED:
        return "duplicate"
    status = str(session.get("status", "")).lower()
    if status == "completed":
        items = (session.get("lineItems") or {})
        items = items.get("data") if isinstance(items, dict) else items
        if items:
            total = sum(int(i["price"]["value"]) * int(i.get("quantity", 1)) for i in items)
            if total != monime.to_minor(inv.amount):
                audit.record("billing.amount_mismatch", actor=None, tenant=inv.pharmacy, target=inv)
                return "mismatch"
        mark_paid(inv.pk, method="monime", reference=inv.provider_session_id, actor=None)
        return "confirmed"
    if status in ("cancelled", "expired"):
        inv.checkout_url = ""
        inv.save(update_fields=["checkout_url", "updated_at"])
        return "failed"
    return "pending"
