"""Online payment orchestration. Payment is confirmed ONLY from provider data fetched server-to-server (never from a browser redirect or a bare
webhook body); every step is idempotent so duplicate callbacks cannot double-confirm, double-receipt or double-email."""
import json
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
from apps.notifications import inapp
from apps.notifications.services import receipt_parts, render_branded_html, send_email
from apps.procurement.models import next_number
from apps.shop import services as shop
from apps.shop.models import Order

from . import monime
from .models import MobileMoneyCollection, OrderReceipt, OrderRefund, PaymentAttempt, WebhookEvent

A = PaymentAttempt.Status
S = Order.Status
ONLINE = "monime"


def provider_ready(tenant=None) -> bool:
    """Credentials are platform-wide (environment), so every pharmacy can take mobile money as soon as they are set."""
    return monime.ready()


to_minor = monime.to_minor


def currency() -> str:
    return (get_current_tenant().settings or {}).get("currency", "SLE")


# ---------------- starting a payment ----------------
def refresh_attempts(attempts) -> None:
    """Ask the provider about open checkouts and apply its answer (works even when a webhook never arrives)."""
    for a in attempts:
        if a.status in (A.INITIATED, A.PENDING) and a.provider_session_id:
            apply_session_state(a.pk, monime.retrieve_checkout_session(a.provider_session_id), "refresh")


def start_payment(order_id, *, user) -> PaymentAttempt:
    order = Order.objects.get(pk=order_id, customer=user)
    if order.payment_method == ONLINE and order.status == S.AWAITING_PAYMENT and provider_ready():
        try:  # an earlier checkout may have been paid, cancelled or expired since we last looked
            refresh_attempts(order.payment_attempts.filter(status__in=[A.INITIATED, A.PENDING]))
        except monime.ProviderError:
            pass
    return _open_checkout(order_id, user=user)


@transaction.atomic
def _open_checkout(order_id, *, user) -> PaymentAttempt:
    order = Order.objects.select_for_update(of=("self",)).select_related("customer").get(pk=order_id, customer=user)
    if order.payment_method != ONLINE:
        raise BusinessRuleViolation("This order is paid on pickup or delivery.")
    if order.status != S.AWAITING_PAYMENT:
        raise BusinessRuleViolation("This order is not waiting for payment.")
    if not provider_ready():
        raise BusinessRuleViolation("Online payment is not available at the moment.")
    if currency() not in monime.CURRENCIES:
        raise BusinessRuleViolation("Mobile money payments are only available in SLE or USD.")
    live = order.payment_attempts.filter(status__in=[A.INITIATED, A.PENDING]).exclude(redirect_url="").first()
    if live:  # reuse the open checkout instead of creating a second one
        return live
    tenant = get_current_tenant()
    attempt = PaymentAttempt.objects.create(order=order, reference=next_number("PAY"), amount=order.total, currency=currency(), created_by=user)
    from apps.core.links import site_url
    base = site_url(tenant.slug, f"/account/orders/{order.pk}")
    session = monime.create_checkout_session(key=monime.idempotency_key(tenant.pk, attempt.reference), reference=attempt.reference,
                                             name=f"Order {order.reference_number} - {tenant.name}", amount_minor=to_minor(order.total),
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
    ok = event == "payment.confirmed"
    inapp.push([o.customer], kind="payment", level="success" if ok else "danger", title=f"Payment {'received' if ok else 'not completed'}",
               body=f"{attempt.currency} {attempt.amount} for order {o.reference_number}.", link=f"/orders/{o.pk}")
    if ok:
        inapp.push_staff(attempt.tenant_id, "order.manage", o.branch_id, kind="payment", level="warning" if attempt.needs_refund else "success",
                         title=f"{'Refund needed' if attempt.needs_refund else 'Mobile money received'}: {o.reference_number}",
                         body=f"{attempt.currency} {attempt.amount} paid online.", link="/payments" if attempt.needs_refund else "/orders")
    notify_topic(attempt.tenant_id, o.branch_id, "payments", event, {"order": o.pk, "reference": o.reference_number, "status": attempt.status}, users=[o.customer_id])


def _email_payment(attempt, ok: bool):
    o, t = attempt.order, attempt.tenant
    if ok:
        subject, body = f"Payment received for order {o.reference_number}", f"We received your payment of {attempt.currency} {attempt.amount} for order {o.reference_number}."
    else:
        subject, body = f"Payment not completed for order {o.reference_number}", "Your payment was not completed. You can try again from your order page."
    send_email(to=o.customer.email, subject=subject, text=body, tenant=t, template="payment_confirmation" if ok else "payment_failed",
               html_body=render_branded_html(title=subject, pharmacy=t, paragraphs=[body]))


# ---------------- counter collections (USSD payment codes) ----------------
OPEN_COLLECTION = [MobileMoneyCollection.Status.PENDING, MobileMoneyCollection.Status.PROCESSING]
C = MobileMoneyCollection.Status


@transaction.atomic
def create_collection(*, user, branch, amount: Decimal, customer_name="") -> MobileMoneyCollection:
    if not provider_ready():
        raise BusinessRuleViolation("Mobile money payments are not configured.")
    if currency() not in monime.CURRENCIES:
        raise BusinessRuleViolation("Mobile money payments are only available in SLE or USD.")
    if amount <= 0:
        raise ValidationError({"amount": "Enter an amount greater than zero."})
    tenant = get_current_tenant()
    row = MobileMoneyCollection.objects.create(reference=next_number("MM"), amount=amount, currency=currency(), branch=branch,
                                               created_by=user, customer_name=customer_name[:100], expires_at=timezone.now() + timedelta(minutes=10))
    res = monime.create_payment_code(key=monime.idempotency_key(tenant.pk, row.reference), reference=row.reference, name=f"{tenant.name}"[:60],
                                     amount_minor=to_minor(amount), currency=row.currency, customer_name=row.customer_name)
    row.provider_code_id = str(res.get("id", ""))[:100] or None
    row.ussd_code = str(res.get("ussdCode", ""))[:60]
    if not row.provider_code_id or not row.ussd_code:
        raise monime.ProviderError("The payment provider did not return a payment code.")
    row.save()
    audit.record("payment.collection_requested", actor=user, target=row, branch_id=branch.pk, reference=row.reference, amount=str(amount))
    return row


def apply_code_state(collection_id, data: dict, source: str) -> str:
    with transaction.atomic():
        row = MobileMoneyCollection.objects.select_for_update(of=("self",)).get(pk=collection_id)
        if row.status == C.COMPLETED:
            return "duplicate"
        status = str(data.get("status", "")).lower()
        if status not in {c.value for c in C} or status == row.status:
            return row.status
        if status == C.COMPLETED:
            amount = data.get("amount") or {}
            if amount and (int(amount.get("value", -1)) != to_minor(row.amount) or str(amount.get("currency", row.currency)) != row.currency):
                row.status = C.FAILED
                row.save(update_fields=["status", "updated_at"])
                audit.record("payment.amount_mismatch", actor=None, tenant=row.tenant, target=row)
                return "mismatch"
            row.completed_at = timezone.now()
            audit.record("payment.collection_received", actor=None, tenant=row.tenant, target=row, branch_id=row.branch_id, reference=row.reference, via=source)
            inapp.push([row.created_by], kind="payment", level="success", title="Mobile money received",
                       body=f"{row.currency} {row.amount} ({row.reference}) is paid.", link="/pos")
        row.status = status
        row.save(update_fields=["status", "completed_at", "updated_at"])
        return status


def refresh_collection(row: MobileMoneyCollection) -> MobileMoneyCollection:
    if row.status in OPEN_COLLECTION and row.provider_code_id:
        apply_code_state(row.pk, monime.retrieve_payment_code(row.provider_code_id), "refresh")
        row.refresh_from_db()
    return row


def cancel_collection(row: MobileMoneyCollection, *, user) -> MobileMoneyCollection:
    refresh_collection(row)  # never cancel money that has already arrived
    if row.status != C.PENDING:
        raise BusinessRuleViolation("Only a payment that has not been made can be cancelled.")
    monime.delete_payment_code(row.provider_code_id)
    row.status = C.CANCELLED
    row.save(update_fields=["status", "updated_at"])
    audit.record("payment.collection_cancelled", actor=user, target=row, branch_id=row.branch_id)
    return row


def claim_collection(reference: str, *, amount: Decimal, branch_id: int, used_for: str) -> str:
    """Called inside the sale transaction: proves a mobile money tender is real, unused and for exactly this amount."""
    row = MobileMoneyCollection.objects.select_for_update(of=("self",)).filter(reference=reference).first()
    if row is None:
        raise ValidationError({"payments": "Request the mobile money payment from this screen so it can be verified."})
    if row.status != C.COMPLETED:
        raise ValidationError({"payments": f"{reference} has not been paid yet."})
    if row.used_at:
        raise ValidationError({"payments": f"{reference} was already used on {row.used_for}."})
    if row.branch_id != branch_id:
        raise ValidationError({"payments": f"{reference} was collected at another branch."})
    if row.amount != amount:
        raise ValidationError({"payments": f"{reference} is for {row.amount}; the tender must match it exactly."})
    row.used_at, row.used_for = timezone.now(), used_for[:40]
    row.save(update_fields=["used_at", "used_for", "updated_at"])
    return row.reference


# ---------------- webhooks ----------------
def handle_webhook(raw_body: bytes, signature_header: str) -> tuple[int, str]:
    """Returns (http_status, outcome). Invalid signature -> 400 before anything in the body is trusted.
    The body only says WHICH object changed; its state is always fetched from the provider."""
    cfg = monime.config()
    if not (cfg.ready and monime.verify_signature(cfg.webhook_secret, signature_header, raw_body)):
        return 400, "invalid_signature"
    try:
        payload = json.loads(raw_body)
        event = payload["event"]
        event_id, name = str(event["id"])[:100], str(event["name"])[:60]
        object_id = str((payload.get("object") or {}).get("id") or (payload.get("data") or {}).get("id") or "")[:100]
    except (ValueError, KeyError, TypeError, AttributeError):
        return 400, "malformed"
    try:
        with transaction.atomic():
            ev = WebhookEvent.objects.create(provider="monime", event_id=event_id, name=name, object_id=object_id)
    except IntegrityError:
        return 200, "duplicate"  # already received: acknowledge so the provider stops retrying

    def done(outcome, tenant=None, status="processed"):
        WebhookEvent.objects.filter(pk=ev.pk).update(status=status, detail=outcome[:300], tenant=tenant)
        return 200, outcome

    if not object_id or not name.startswith(("checkout_session.", "payment_code.")):
        return done("ignored", status="ignored")
    try:
        if name.startswith("payment_code."):
            row = MobileMoneyCollection.all_objects.select_related("tenant").filter(provider_code_id=object_id).first()
            if row is None:
                return done("ignored", status="ignored")
            with tenant_context(row.tenant):
                outcome = apply_code_state(row.pk, monime.retrieve_payment_code(object_id), "webhook")
            return done(outcome, row.tenant)
        attempt = PaymentAttempt.all_objects.select_related("tenant").filter(provider_session_id=object_id).first()
        if attempt is not None:
            with tenant_context(attempt.tenant):
                outcome = apply_session_state(attempt.pk, monime.retrieve_checkout_session(object_id), "webhook")
            return done(outcome, attempt.tenant)
        from apps.billing.models import Invoice
        invoice = Invoice.objects.select_related("pharmacy").filter(provider_session_id=object_id).first()
        if invoice is not None:
            from apps.billing.services import apply_invoice_session
            return done(apply_invoice_session(invoice.pk, monime.retrieve_checkout_session(object_id)), invoice.pharmacy)
        return done("ignored", status="ignored")
    except monime.ProviderError:
        WebhookEvent.objects.filter(pk=ev.pk).delete()  # let the provider retry later
        return 503, "provider_unavailable"


# ---------------- reconciliation ----------------
def reconcile(tenant, older_than_minutes=5) -> dict:
    """Ask the provider about payments still pending (missed or blocked webhooks) and apply the answer."""
    out = {"checked": 0, "confirmed": 0, "failed": 0, "still_pending": 0, "errors": 0}
    if not provider_ready():
        return out
    with tenant_context(tenant):
        cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
        for a in PaymentAttempt.objects.filter(status__in=[A.INITIATED, A.PENDING], created_at__lte=cutoff).exclude(provider_session_id=None):
            out["checked"] += 1
            try:
                res = apply_session_state(a.pk, monime.retrieve_checkout_session(a.provider_session_id), "reconcile")
            except monime.ProviderError:
                out["errors"] += 1
                continue
            out["confirmed" if res in ("confirmed", "needs_refund") else "failed" if res in ("failed", "mismatch") else "still_pending"] += 1
        for row in MobileMoneyCollection.objects.filter(status__in=OPEN_COLLECTION, created_at__lte=cutoff).exclude(provider_code_id=None):
            out["checked"] += 1
            try:
                res = apply_code_state(row.pk, monime.retrieve_payment_code(row.provider_code_id), "reconcile")
            except monime.ProviderError:
                out["errors"] += 1
                continue
            out["confirmed" if res == "completed" else "failed" if res in ("expired", "cancelled", "failed", "mismatch") else "still_pending"] += 1
    return out


def reconciliation_report() -> dict:
    qs = PaymentAttempt.objects.all()
    stale = timezone.now() - timedelta(minutes=30)
    from django.db.models import Count, Sum
    by_status = {r["status"]: {"count": r["n"], "amount": r["t"]} for r in qs.values("status").annotate(n=Count("id"), t=Sum("amount"))}
    unused = MobileMoneyCollection.objects.filter(status=C.COMPLETED, used_at__isnull=True)
    return {"by_status": by_status, "stale_pending": qs.filter(status__in=[A.INITIATED, A.PENDING], created_at__lte=stale).count(),
            "needs_refund": list(qs.filter(needs_refund=True).values("id", "reference", "amount", "order__reference_number")),
            "unapplied_collections": list(unused.values("id", "reference", "amount", "completed_at"))}


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
    from apps.core.links import site_url
    send_email(to=order.customer.email, subject=f"Your receipt {number} from {t.name}", text="\n".join(paragraphs), tenant=t, template="receipt",
               html_body=render_branded_html(title="Your receipt", pharmacy=t, paragraphs=[f"Hello {order.customer.full_name}, thank you for your purchase."],
                                             button=("View your order", site_url(t.slug, f"/account/orders/{order.pk}")), **receipt_parts(r.data)))
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


def tenants_with_pending_payments():
    with unscoped():
        ids = set(PaymentAttempt.all_objects.filter(status__in=[A.INITIATED, A.PENDING]).values_list("tenant_id", flat=True))
        ids |= set(MobileMoneyCollection.all_objects.filter(status__in=OPEN_COLLECTION).values_list("tenant_id", flat=True))
    from apps.tenants.models import Pharmacy
    return [t for t in Pharmacy.objects.filter(pk__in=ids) if t.is_active_tenant]
