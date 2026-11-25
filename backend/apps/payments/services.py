"""Online payment orchestration. Payment is confirmed ONLY from provider data fetched server-to-server (never from a browser redirect or a bare
webhook body); every step is idempotent so duplicate callbacks cannot double-confirm, double-receipt or double-email."""
import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation
from apps.core.realtime import notify_topic
from apps.core.tenant_context import get_current_tenant, tenant_context, unscoped
from apps.notifications.services import render_branded_html, send_email
from apps.procurement.models import next_number
from apps.shop import services as shop
from apps.shop.models import Order

from . import monime
from .crypto import decrypt, encrypt
from .models import OrderReceipt, OrderRefund, PaymentAttempt, PaymentProviderConfig, WebhookEvent

A = PaymentAttempt.Status
S = Order.Status
ONLINE = "monime"


@dataclass
class Cfg:
    space_id: str
    access_token: str
    webhook_secret: str
    enabled: bool


def get_config(tenant=None) -> Cfg | None:
    row = PaymentProviderConfig.all_objects.filter(tenant=tenant or get_current_tenant(), provider="monime").first()
    if row is None:
        return None
    return Cfg(row.space_id, decrypt(row.access_token_enc), decrypt(row.webhook_secret_enc), row.enabled)


def provider_ready(tenant=None) -> bool:
    c = get_config(tenant)
    return bool(c and c.enabled and c.space_id and c.access_token and c.webhook_secret)


@transaction.atomic
def save_config(*, user, space_id=None, access_token=None, webhook_secret=None, enabled=None) -> PaymentProviderConfig:
    tenant = get_current_tenant()
    row, _ = PaymentProviderConfig.objects.get_or_create(provider="monime")
    if space_id is not None:
        row.space_id = space_id.strip()[:100]
    if access_token:  # write-only: blank means "keep the stored value"
        row.access_token_enc = encrypt(access_token.strip())
    if webhook_secret:
        if not 32 <= len(webhook_secret.strip()) <= 100:
            raise ValidationError({"webhook_secret": "The webhook secret must be 32-100 characters (copy it from the Monime dashboard)."})
        row.webhook_secret_enc = encrypt(webhook_secret.strip())
    if enabled is not None:
        if enabled and not (row.space_id and row.access_token_enc and row.webhook_secret_enc):
            raise ValidationError({"enabled": "Enter the space id, access token and webhook secret before enabling online payments."})
        row.enabled = enabled
    row.save()
    audit.record("payments.config_updated", actor=user, tenant=tenant, target=row, enabled=row.enabled)  # secrets are never logged
    return row


def to_minor(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())  # SLE/USD minor units per Monime docs (see monime.py note)


def currency() -> str:
    return (get_current_tenant().settings or {}).get("currency", "SLE")


# ---------------- starting a payment ----------------
@transaction.atomic
def start_payment(order_id, *, user) -> PaymentAttempt:
    order = Order.objects.select_for_update(of=("self",)).select_related("customer").get(pk=order_id, customer=user)
    if order.payment_method != ONLINE:
        raise BusinessRuleViolation("This order is paid on pickup or delivery.")
    if order.status != S.AWAITING_PAYMENT:
        raise BusinessRuleViolation("This order is not waiting for payment.")
    cfg = get_config()
    if not provider_ready():
        raise BusinessRuleViolation("Online payment is not available for this pharmacy.")
    live = order.payment_attempts.filter(status__in=[A.INITIATED, A.PENDING]).exclude(redirect_url="").first()
    if live:  # reuse the open checkout instead of creating a second one
        return live
    tenant = get_current_tenant()
    attempt = PaymentAttempt.objects.create(order=order, reference=next_number("PAY"), amount=order.total, currency=currency(), created_by=user)
    base = f"{settings.FRONTEND_URL.rstrip('/')}/pharmacy/{tenant.slug}/orders/{order.pk}"
    session = monime.create_checkout_session(cfg, reference=attempt.reference, name=f"Order {order.reference_number}", amount_minor=to_minor(order.total),
                                             currency=attempt.currency, success_url=f"{base}?payment=return", cancel_url=f"{base}?payment=cancelled")
    attempt.provider_session_id = str(session.get("id", ""))[:100] or None
    attempt.redirect_url = str(session.get("redirectUrl", ""))[:500]
    attempt.status = A.PENDING
    if not attempt.provider_session_id or not attempt.redirect_url.startswith("https://"):
        raise monime.ProviderError("The payment provider returned an invalid checkout session.")
    attempt.save()
    audit.record("payment.initiated", actor=user, target=attempt, branch_id=order.branch_id, order=order.reference_number, reference=attempt.reference)
    return attempt


# ---------------- applying provider state (idempotent) ----------------
def _session_amount_matches(session: dict, attempt: PaymentAttempt) -> bool:
    items = ((session.get("lineItems") or {}).get("data")) or session.get("lineItems")
    if not isinstance(items, list) or not items:
        return True  # amount not echoed by the provider: rely on our own reference + server-to-server status
    try:
        total = sum(int(i["price"]["value"]) * int(i.get("quantity", 1)) for i in items)
    except (KeyError, TypeError, ValueError):
        return True
    return total == to_minor(attempt.amount)


def apply_session_state(attempt_id, session: dict, source: str) -> str:
    """Returns 'confirmed' | 'duplicate' | 'failed' | 'pending' | 'mismatch' | 'needs_refund'."""
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update(of=("self",)).select_related("order", "order__customer").get(pk=attempt_id)
        if attempt.status == A.COMPLETED:
            return "duplicate"
        status = str(session.get("status", "")).lower()
        order = attempt.order
        if status == "completed":
            if not _session_amount_matches(session, attempt):
                attempt.status, attempt.status_detail = A.FAILED, "Amount mismatch reported by provider"
                attempt.save()
                audit.record("payment.amount_mismatch", actor=None, tenant=attempt.tenant, target=attempt, order=order.reference_number)
                return "mismatch"
            attempt.status, attempt.completed_at = A.COMPLETED, timezone.now()
            attempt.save()  # persisted first: the receipt issued during the order transition reads completed attempts
            result = "confirmed"
            try:
                with transaction.atomic():
                    shop.transition(order.pk, S.PAYMENT_CONFIRMED, actor=None, kind="system", note=f"Paid online ({attempt.reference})")
            except BusinessRuleViolation:
                attempt.needs_refund, result = True, "needs_refund"  # e.g. the customer cancelled while paying: refund must be arranged
                audit.record("payment.received_for_unpayable_order", actor=None, tenant=attempt.tenant, target=attempt, order=order.reference_number)
                from apps.accounting.posting import post_unfulfillable_payment
                post_unfulfillable_payment(attempt)
            attempt.save()
            audit.record("payment.confirmed", actor=None, tenant=attempt.tenant, target=attempt, branch_id=order.branch_id, via=source, reference=attempt.reference)
            _notify_payment(attempt, "payment.confirmed")
            if result == "confirmed":
                _email_payment(attempt, ok=True)
            return result
        if status in ("cancelled", "expired"):
            attempt.status = A.CANCELLED if status == "cancelled" else A.EXPIRED
            attempt.save()
            _notify_payment(attempt, "payment.failed")
            _email_payment(attempt, ok=False)
            audit.record("payment.failed", actor=None, tenant=attempt.tenant, target=attempt, status=status, via=source)
            return "failed"
        return "pending"


def _notify_payment(attempt, event):
    o = attempt.order
    notify_topic(attempt.tenant_id, o.branch_id, "payments", event, {"order": o.pk, "reference": o.reference_number, "status": attempt.status}, users=[o.customer_id])


def _email_payment(attempt, ok: bool):
    o, t = attempt.order, attempt.tenant
    if ok:
        subject, body = f"Payment received for order {o.reference_number}", f"We received your payment of {attempt.currency} {attempt.amount} for order {o.reference_number}."
    else:
        subject, body = f"Payment not completed for order {o.reference_number}", "Your payment was not completed. You can try again from your order page."
    send_email(to=o.customer.email, subject=subject, text=body, tenant=t, template="payment_confirmation" if ok else "payment_failed",
               html_body=render_branded_html(title=subject, pharmacy=t, paragraphs=[body]))


# ---------------- webhooks ----------------
def handle_webhook(tenant, raw_body: bytes, signature_header: str) -> tuple[int, str]:
    """Returns (http_status, outcome). Invalid signature -> 400 before anything in the body is trusted."""
    with tenant_context(tenant):
        cfg = get_config(tenant)
        if not (cfg and cfg.enabled and monime.verify_signature(cfg.webhook_secret, signature_header, raw_body)):
            return 400, "invalid_signature"
        try:
            payload = json.loads(raw_body)
            event = payload["event"]
            event_id, name = str(event["id"])[:100], str(event["name"])[:60]
            data = payload.get("data") or {}
            object_id = str(data.get("id") or (payload.get("object") or {}).get("id") or "")[:100]
        except (ValueError, KeyError, TypeError):
            return 400, "malformed"
        try:
            with transaction.atomic():
                ev = WebhookEvent.objects.create(provider="monime", event_id=event_id, tenant=tenant, name=name, object_id=object_id)
        except IntegrityError:
            return 200, "duplicate"  # already received: acknowledge so the provider stops retrying
        if not name.startswith("checkout_session."):
            WebhookEvent.objects.filter(pk=ev.pk).update(status="ignored")
            return 200, "ignored"
        attempt = PaymentAttempt.objects.filter(provider_session_id=object_id).first()
        if attempt is None:
            WebhookEvent.objects.filter(pk=ev.pk).update(status="ignored", detail="unknown session")
            return 200, "ignored"
        try:
            session = monime.retrieve_checkout_session(cfg, object_id)  # the provider's answer, not the webhook body, decides
            outcome = apply_session_state(attempt.pk, session, "webhook")
        except monime.ProviderError:
            WebhookEvent.objects.filter(pk=ev.pk).delete()  # let the provider retry later
            return 503, "provider_unavailable"
        WebhookEvent.objects.filter(pk=ev.pk).update(status="processed", detail=outcome)
        return 200, outcome


# ---------------- reconciliation ----------------
def reconcile(tenant, older_than_minutes=5) -> dict:
    """Ask the provider about attempts still pending (missed/blocked webhooks) and apply the answer."""
    out = {"checked": 0, "confirmed": 0, "failed": 0, "still_pending": 0, "errors": 0}
    with tenant_context(tenant):
        cfg = get_config(tenant)
        if not (cfg and cfg.enabled):
            return out
        cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
        for a in PaymentAttempt.objects.filter(status__in=[A.INITIATED, A.PENDING], created_at__lte=cutoff).exclude(provider_session_id=None):
            out["checked"] += 1
            try:
                res = apply_session_state(a.pk, monime.retrieve_checkout_session(cfg, a.provider_session_id), "reconcile")
            except monime.ProviderError:
                out["errors"] += 1
                continue
            out["confirmed" if res in ("confirmed", "needs_refund") else "failed" if res in ("failed", "mismatch") else "still_pending"] += 1
    return out


def reconciliation_report() -> dict:
    qs = PaymentAttempt.objects.all()
    stale = timezone.now() - timedelta(minutes=30)
    from django.db.models import Count, Sum
    by_status = {r["status"]: {"count": r["n"], "amount": r["t"]} for r in qs.values("status").annotate(n=Count("id"), t=Sum("amount"))}
    return {"by_status": by_status, "stale_pending": qs.filter(status__in=[A.INITIATED, A.PENDING], created_at__lte=stale).count(),
            "needs_refund": list(qs.filter(needs_refund=True).values("id", "reference", "amount", "order__reference_number"))}


# ---------------- receipts ----------------
def issue_order_receipt(order: Order) -> OrderReceipt:
    existing = OrderReceipt.objects.filter(order=order).first()
    if existing:
        return existing
    t = get_current_tenant()
    cur = (t.settings or {}).get("currency", "SLE")
    data = {"pharmacy": t.name, "branch": order.branch.name, "branch_address": order.branch.address, "branch_phone": order.branch.phone or t.contact_phone,
            "order_reference": order.reference_number, "date": timezone.now().isoformat(), "cashier": "Online order", "customer": order.customer.full_name,
            "currency": cur, "payment_method": order.payment_method, "fulfilment": order.fulfilment,
            "lines": [{"name": l.medicine.name, "quantity": l.quantity, "unit_price": str(l.unit_price), "discount": "0.00", "tax": str(l.tax_amount), "total": str(l.line_total)} for l in order.lines.select_related("medicine")],
            "subtotal": str(order.subtotal), "discount_total": "0.00", "tax_total": str(order.tax_total), "delivery_fee": str(order.delivery_fee), "total": str(order.total),
            "payments": [{"method": order.payment_method, "amount": str(order.total), "reference": ", ".join(order.payment_attempts.filter(status=A.COMPLETED).values_list("reference", flat=True))}],
            "amount_paid": str(order.total), "change_due": "0.00", "payment_status": "Paid", "sale_reference": order.reference_number}
    number = next_number("RC")
    r = OrderReceipt.objects.create(order=order, number=number, data={**data, "receipt_number": number})
    lines = [f"{l['name']} x{l['quantity']} = {l['total']}" for l in data["lines"]]
    paragraphs = [f"Receipt {number} · Order {order.reference_number}", *lines, f"Total: {cur} {order.total}", "Status: Paid"]
    send_email(to=order.customer.email, subject=f"Your receipt {number} from {t.name}", text="\n".join(paragraphs), tenant=t, template="receipt",
               html_body=render_branded_html(title="Your receipt", pharmacy=t, paragraphs=paragraphs))
    audit.record("order.receipt_issued", actor=None, tenant=t, target=order, branch_id=order.branch_id, receipt=number)
    return r


# ---------------- refunds ----------------
@transaction.atomic
def refund_order(order_id, *, user, amount: Decimal, method: str, reference: str, reason: str) -> OrderRefund:
    order = Order.objects.select_for_update(of=("self",)).select_related("customer").get(pk=order_id)
    if order.status != S.REFUND_REQUESTED:
        raise BusinessRuleViolation("A refund can only be recorded for an order with a refund request.")
    if not (method.strip() and reference.strip() and reason.strip()):
        raise ValidationError({"detail": "Enter the refund method, reference and reason."})
    refunded = sum((r.amount for r in order.refunds.all()), Decimal("0"))
    if amount <= 0 or refunded + amount > order.total:
        raise ValidationError({"amount": f"Refund must be positive and at most the remaining {order.total - refunded}."})
    if OrderRefund.objects.filter(reference=reference.strip()).exists():
        raise ValidationError({"reference": "This refund reference was already recorded."})
    r = OrderRefund.objects.create(order=order, amount=amount, method=method[:30], reference=reference.strip()[:100], reason=reason[:255], processed_by=user)
    from apps.accounting.posting import post_order_refund
    post_order_refund(r)
    audit.record("order.refunded", actor=user, target=order, branch_id=order.branch_id, amount=str(amount), reference=reference)
    t = get_current_tenant()
    body = f"A refund of {amount} for order {order.reference_number} has been processed (reference {reference})."
    send_email(to=order.customer.email, subject=f"Refund confirmation for order {order.reference_number}", text=body, tenant=t, template="refund_confirmation",
               html_body=render_branded_html(title="Refund confirmation", pharmacy=t, paragraphs=[body]))
    if refunded + amount == order.total:
        shop.transition(order.pk, S.REFUNDED, actor=user, kind="staff", note=f"Refunded ({reference})")
    return r


def tenants_with_online_payments():
    with unscoped():
        return [c.tenant for c in PaymentProviderConfig.all_objects.select_related("tenant").filter(enabled=True) if c.tenant.is_active_tenant]
