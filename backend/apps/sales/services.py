"""POS business logic. Everything that touches money or stock runs in one transaction. The server computes ALL amounts:
clients send only product ids, quantities, an optional discount percentage and payment tenders."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation
from apps.core.tenant_context import get_current_tenant
from apps.inventory import services as inv
from apps.inventory.models import Batch
from apps.medicines.models import Medicine
from apps.notifications import inapp
from apps.prescriptions.models import Dispensing, DispensingItem
from apps.procurement.models import next_number

from .models import (CashMovement, Payment, Receipt, Sale, SaleAllocation, SaleLine, SaleReturn, SaleReturnLine, Shift, ZERO)

CASH = Payment.Method.CASH


def q2(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def tsetting(key, default):
    return (get_current_tenant().settings or {}).get(key, default)


# ======================= shifts =======================
def current_shift(user) -> Shift | None:
    return Shift.objects.filter(cashier=user, status=Shift.Status.OPEN).select_related("branch").first()


@transaction.atomic
def open_shift(*, user, branch, opening_cash) -> Shift:
    if opening_cash < 0:
        raise ValidationError({"opening_cash": "Opening cash cannot be negative."})
    if user.is_branch_scoped and branch.pk != user.branch_id:
        raise PermissionDenied("You can only open a shift at your own branch.")
    if branch.status != branch.Status.ACTIVE:
        raise ValidationError({"branch": "This branch is inactive."})
    if current_shift(user):
        raise BusinessRuleViolation("You already have an open shift.")
    try:
        with transaction.atomic():
            shift = Shift.objects.create(cashier=user, branch=branch, opening_cash=opening_cash)
    except IntegrityError:
        raise BusinessRuleViolation("You already have an open shift.")
    audit.record("shift.opened", actor=user, target=shift, branch_id=branch.pk, opening_cash=str(opening_cash))
    return shift


def shift_totals(shift: Shift) -> dict:
    pay = shift.payments.values("method").annotate(t=Sum("amount"))
    by_method = {p["method"]: p["t"] for p in pay}
    cash_in = by_method.get(CASH, ZERO)
    cash_refunds = shift.refunds.filter(refund_method=CASH).aggregate(t=Sum("refund_total"))["t"] or ZERO
    mv = shift.cash_movements.filter(status=CashMovement.Status.APPROVED)
    withdrawals = mv.filter(kind="withdrawal").aggregate(t=Sum("amount"))["t"] or ZERO
    deposits = mv.filter(kind="deposit").aggregate(t=Sum("amount"))["t"] or ZERO
    expected = shift.opening_cash + cash_in - cash_refunds - withdrawals + deposits
    return {"opening_cash": shift.opening_cash, "sales_count": shift.sales.count(), "sales_total": shift.sales.aggregate(t=Sum("total"))["t"] or ZERO,
            "payments_by_method": by_method, "cash_received": cash_in, "cash_refunds": cash_refunds, "cash_withdrawals": withdrawals,
            "cash_deposits": deposits, "expected_cash": expected,
            "refunds_total": shift.refunds.aggregate(t=Sum("refund_total"))["t"] or ZERO}


@transaction.atomic
def close_shift(shift_id, *, user, counted_cash, notes="") -> Shift:
    shift = Shift.objects.select_for_update(of=("self",)).get(pk=shift_id)
    if shift.status != Shift.Status.OPEN:
        raise BusinessRuleViolation("This shift is already closed.")
    if shift.cashier_id != user.pk and not user.has_tenant_perm("sales.refund"):
        raise PermissionDenied("Only the cashier or a manager can close this shift.")
    if counted_cash < 0:
        raise ValidationError({"counted_cash": "Counted cash cannot be negative."})
    if shift.cash_movements.filter(status=CashMovement.Status.PENDING).exists():
        raise BusinessRuleViolation("Resolve pending cash withdrawals before closing the shift.")
    expected = shift_totals(shift)["expected_cash"]
    shift.status, shift.closed_at, shift.counted_cash = Shift.Status.CLOSED, timezone.now(), counted_cash
    shift.expected_cash, shift.discrepancy, shift.notes = expected, counted_cash - expected, notes[:300]
    shift.save()
    from apps.accounting.posting import post_shift_close
    post_shift_close(shift)
    audit.record("shift.closed", actor=user, target=shift, branch_id=shift.branch_id, expected=str(expected), counted=str(counted_cash), discrepancy=str(shift.discrepancy))
    return shift


@transaction.atomic
def request_cash_movement(shift_id, *, user, kind, amount, reason) -> CashMovement:
    shift = Shift.objects.select_for_update(of=("self",)).get(pk=shift_id)
    if shift.status != Shift.Status.OPEN or shift.cashier_id != user.pk:
        raise BusinessRuleViolation("Cash movements can only be recorded on your own open shift.")
    if kind not in ("withdrawal", "deposit") or amount <= 0 or not reason.strip():
        raise ValidationError({"detail": "Choose withdrawal or deposit, a positive amount and a reason."})
    if kind == "withdrawal" and amount > shift_totals(shift)["expected_cash"]:
        raise ValidationError({"amount": "Withdrawal exceeds the cash expected in the drawer."})
    status = CashMovement.Status.APPROVED if kind == "deposit" else CashMovement.Status.PENDING  # withdrawals need a manager
    m = CashMovement.objects.create(shift=shift, kind=kind, amount=amount, reason=reason[:255], status=status, requested_by=user,
                                    decided_by=user if kind == "deposit" else None)
    if m.status == CashMovement.Status.APPROVED:
        from apps.accounting.posting import post_cash_movement
        post_cash_movement(m)
    audit.record(f"shift.cash_{kind}_requested", actor=user, target=m, branch_id=shift.branch_id, amount=str(amount), reason=reason)
    if m.status == CashMovement.Status.PENDING:
        inapp.push_staff(shift.tenant_id, "sales.refund", shift.branch_id, kind="cash", level="warning", title="Cash withdrawal needs approval",
                         body=f"{user.full_name} requested {amount}: {reason}", link="/pos", exclude=user)
    return m


@transaction.atomic
def decide_cash_movement(pk, *, user, approve: bool) -> CashMovement:
    m = CashMovement.objects.select_for_update(of=("self",)).select_related("shift").get(pk=pk)
    if m.status != CashMovement.Status.PENDING:
        raise BusinessRuleViolation("This request was already decided.")
    if m.requested_by_id == user.pk:
        raise PermissionDenied("You cannot authorize your own withdrawal.")
    if approve and m.amount > shift_totals(m.shift)["expected_cash"]:
        raise ValidationError({"amount": "Withdrawal exceeds the cash expected in the drawer."})
    m.status, m.decided_by = (CashMovement.Status.APPROVED if approve else CashMovement.Status.REJECTED), user
    m.save()
    if approve:
        from apps.accounting.posting import post_cash_movement
        post_cash_movement(m)
    inapp.push([m.requested_by], kind="cash", level="success" if approve else "danger", title=f"Cash withdrawal {'approved' if approve else 'rejected'}",
               body=f"{m.amount}: {m.reason}", link="/pos")
    audit.record("shift.cash_withdrawal_approved" if approve else "shift.cash_withdrawal_rejected", actor=user, target=m, branch_id=m.shift.branch_id, amount=str(m.amount))
    return m


# ======================= payments =======================
def _apply_tenders(payments: list[dict], due: Decimal):
    """Returns (rows_to_store, applied_total, change). Cash may exceed the amount due (change); non-cash may not."""
    if not payments:
        return [], ZERO, ZERO
    valid = {m.value for m in Payment.Method}
    noncash = ZERO
    cash_tendered = ZERO
    for p in payments:
        if p["method"] not in valid:
            raise ValidationError({"payments": f"Unknown payment method '{p['method']}'."})
        if p["amount"] <= 0:
            raise ValidationError({"payments": "Payment amounts must be greater than zero."})
        if p["method"] == CASH:
            cash_tendered += p["amount"]
        else:
            if not (p.get("reference") or "").strip():
                raise ValidationError({"payments": "Enter the transaction reference for non-cash payments."})
            noncash += p["amount"]
    if noncash > due:
        raise ValidationError({"payments": "Non-cash payments cannot exceed the amount due."})
    cash_applied = min(cash_tendered, due - noncash)
    change = cash_tendered - cash_applied
    rows = [dict(p) for p in payments if p["method"] != CASH]
    if cash_applied > 0:
        rows.append({"method": CASH, "amount": cash_applied, "reference": ""})
    return rows, noncash + cash_applied, change


def _store_payments(sale, shift, rows, user):
    from apps.payments import services as gateway
    created = []
    for r in rows:
        ref = (r.get("reference") or "").strip()
        if r["method"] == Payment.Method.MOBILE_MONEY and gateway.provider_ready():
            ref = gateway.claim_collection(ref, amount=q2(r["amount"]), branch_id=shift.branch_id, used_for=sale.reference_number)
        if ref and Payment.objects.filter(method=r["method"], reference=ref).exists():
            raise ValidationError({"payments": f"Reference '{ref}' was already recorded (duplicate payment)."})
        created.append(Payment.objects.create(sale=sale, shift=shift, method=r["method"], amount=q2(r["amount"]), reference=ref[:100], received_by=user))
    return created


# ======================= sales =======================
@transaction.atomic
def create_sale(*, user, items, dispensing_ids, payments, idempotency_key, customer_name="", customer_phone="") -> tuple[Sale, bool]:
    """Returns (sale, created). A repeated idempotency key returns the original sale and changes nothing."""
    key = (idempotency_key or "").strip()
    if not key:
        raise ValidationError({"idempotency_key": "An Idempotency-Key is required to prevent duplicate sales."})
    existing = Sale.objects.filter(idempotency_key=key).first()
    if existing:
        if existing.cashier_id != user.pk:
            raise BusinessRuleViolation("This idempotency key belongs to another sale.")
        return existing, False
    shift = current_shift(user)
    if shift is None:
        raise BusinessRuleViolation("Open a shift before selling.")
    shift = Shift.objects.select_for_update(of=("self",)).get(pk=shift.pk)
    if shift.status != Shift.Status.OPEN:
        raise BusinessRuleViolation("Your shift was closed.")
    if not items and not dispensing_ids:
        raise ValidationError({"items": "Add at least one product."})

    max_disc = Decimal(str(tsetting("cashier_max_discount_pct", 5)))
    planned = []  # (medicine, qty, price, disc_pct, dispensing_item|None, batch|None)
    seen = set()
    for it in items:
        m = it["medicine"]
        if m.pk in seen:
            raise ValidationError({"items": f"{m.name} appears more than once."})
        seen.add(m.pk)
        if m.status != Medicine.Status.ACTIVE:
            raise ValidationError({"items": f"{m.name} is not available."})
        if m.requires_prescription:
            raise ValidationError({"items": f"{m.name} is a prescription medicine: a pharmacist must dispense it against an approved prescription first."})
        pct = Decimal(str(it.get("discount_pct", 0)))
        if pct < 0 or pct > 100:
            raise ValidationError({"items": "Discount must be between 0 and 100 percent."})
        if pct > max_disc and not user.has_tenant_perm("sales.refund"):
            raise PermissionDenied(f"Discounts above {max_disc}% need manager authorization.")
        planned.append((m, it["quantity"], m.selling_price, pct, None, None))

    dispensings = []
    if dispensing_ids:
        dispensings = list(Dispensing.objects.select_for_update(of=("self",)).select_related("prescription").filter(pk__in=dispensing_ids))
        if len(dispensings) != len(set(dispensing_ids)):
            raise ValidationError({"dispensing_ids": "A dispensing was not found."})
        for d in dispensings:
            if d.sale_id is not None:
                raise BusinessRuleViolation(f"Dispensing for {d.prescription.reference_number} has already been billed.")
            if d.branch_id != shift.branch_id:
                raise ValidationError({"dispensing_ids": "A dispensing belongs to a different branch."})
            for di in DispensingItem.objects.filter(dispensing=d).select_related("item__medicine", "batch"):
                planned.append((di.item.medicine, di.quantity, di.item.medicine.selling_price, Decimal("0"), di, di.batch))
        if not customer_name:
            customer_name = dispensings[0].prescription.patient.full_name

    # ---- totals (server-side only) ----
    calc, subtotal, discount_total, tax_total = [], ZERO, ZERO, ZERO
    for m, qty, price, pct, di, batch in planned:
        gross = q2(price * qty)
        disc = q2(gross * pct / 100)
        net = gross - disc
        tax = q2(net * m.tax_rate / 100)
        calc.append((m, qty, price, pct, disc, tax, net + tax, di, batch))
        subtotal += net
        discount_total += disc
        tax_total += tax
    total = subtotal + tax_total
    rows, paid, change = _apply_tenders(payments, total)
    if paid < total:
        if not tsetting("allow_partial_payments", False):
            raise ValidationError({"payments": f"Payment ({paid}) is less than the total ({total})."})
        if not customer_name.strip():
            raise ValidationError({"customer_name": "A customer name is required for partial payments."})

    try:
        with transaction.atomic():
            sale = Sale.objects.create(
                reference_number=next_number("SL"), idempotency_key=key, branch=shift.branch, shift=shift, cashier=user,
                customer_name=customer_name[:200], customer_phone=customer_phone[:30], subtotal=subtotal, discount_total=discount_total,
                tax_total=tax_total, total=total, amount_paid=paid, change_due=change,
                status=Sale.Status.COMPLETED if paid >= total else Sale.Status.PARTIALLY_PAID)
    except IntegrityError:  # concurrent duplicate submission with the same key
        return Sale.objects.get(idempotency_key=key), False

    for m, qty, price, pct, disc, tax, line_total, di, batch in calc:
        line = SaleLine.objects.create(sale=sale, medicine=m, dispensing_item=di, quantity=qty, unit_price=price, discount_pct=pct,
                                       discount_amount=disc, tax_rate=m.tax_rate, tax_amount=tax, line_total=line_total)
        if di is not None:  # stock was already deducted by the pharmacist's dispensing
            SaleAllocation.objects.create(line=line, batch=batch, quantity=qty)
        else:
            for b, taken in inv.deduct_fefo(medicine=m, branch=shift.branch, quantity=qty, user=user, ref_type="sale", ref_id=sale.reference_number):
                SaleAllocation.objects.create(line=line, batch=b, quantity=taken)
    for d in dispensings:
        d.sale_id = sale.pk
        d.save(update_fields=["sale_id", "updated_at"])
    _store_payments(sale, shift, rows, user)
    rc_number = next_number("RC")
    Receipt.objects.create(sale=sale, number=rc_number, data={**build_receipt_data(sale), "receipt_number": rc_number})
    from apps.accounting.posting import post_sale
    post_sale(sale)
    audit.record("sale.created", actor=user, target=sale, branch_id=sale.branch_id, reference=sale.reference_number, total=str(total))
    return sale, True


@transaction.atomic
def add_payment(sale_id, *, user, payments) -> Sale:
    sale = Sale.objects.select_for_update(of=("self",)).get(pk=sale_id)
    if sale.status != Sale.Status.PARTIALLY_PAID:
        raise BusinessRuleViolation("This sale has no outstanding balance.")
    shift = current_shift(user)
    if shift is None or shift.branch_id != sale.branch_id:
        raise BusinessRuleViolation("Open a shift at this branch to take payment.")
    rows, paid, change = _apply_tenders(payments, sale.balance)
    if paid <= 0:
        raise ValidationError({"payments": "Enter a payment."})
    created = _store_payments(sale, shift, rows, user)
    from apps.accounting.posting import post_sale_payments
    post_sale_payments(sale, created)
    sale.amount_paid += paid
    sale.change_due = change
    if sale.amount_paid >= sale.total:
        sale.status = Sale.Status.COMPLETED
    sale.save()
    audit.record("sale.payment_added", actor=user, target=sale, branch_id=sale.branch_id, amount=str(paid))
    return sale


# ======================= returns / refunds / cancellation =======================
@transaction.atomic
def process_return(sale_id, *, user, lines, reason, refund_method, refund_reference="", restock=False, is_cancellation=False) -> SaleReturn:
    sale = Sale.objects.select_for_update(of=("self",)).get(pk=sale_id)
    if sale.status not in (Sale.Status.COMPLETED, Sale.Status.PARTIALLY_RETURNED):
        raise BusinessRuleViolation(f"A {sale.status.replace('_', ' ')} sale cannot be returned.")
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required."})
    if refund_method not in {m.value for m in Payment.Method}:
        raise ValidationError({"refund_method": "Choose a refund method."})
    if refund_method != CASH and not refund_reference.strip():
        raise ValidationError({"refund_reference": "Enter the refund transaction reference."})
    shift = None
    if refund_method == CASH:
        shift = current_shift(user)
        if shift is None:
            raise BusinessRuleViolation("Open a shift to pay a cash refund.")
    if not lines:
        raise ValidationError({"lines": "Choose items to return."})
    sr = SaleReturn.objects.create(number=next_number("CN"), sale=sale, shift=shift, refund_method=refund_method, refund_reference=refund_reference[:100],
                                   refund_total=ZERO, reason=reason[:255], is_cancellation=is_cancellation, processed_by=user)
    total = ZERO
    for ln in lines:
        line = SaleLine.objects.select_for_update(of=("self",)).select_related("medicine").filter(pk=ln["sale_line"], sale=sale).first()
        if line is None:
            raise ValidationError({"lines": "A line does not belong to this sale."})
        qty, remaining = ln["quantity"], line.quantity - line.quantity_returned
        if qty <= 0 or qty > remaining:
            raise ValidationError({"lines": f"{line.medicine.name}: only {remaining} can still be returned."})
        amount = line.line_total - line.amount_refunded if qty == remaining else q2(line.line_total * qty / line.quantity)
        restocked = 0
        todo = qty
        for alloc in line.allocations.select_for_update(of=("self",)).select_related("batch").order_by("-id"):
            if todo == 0:
                break
            take = min(todo, alloc.quantity - alloc.quantity_returned)
            if take <= 0:
                continue
            alloc.quantity_returned += take
            alloc.save(update_fields=["quantity_returned", "updated_at"])
            b = alloc.batch
            if restock and line.dispensing_item_id is None and b.status in (Batch.Status.AVAILABLE, Batch.Status.QUARANTINED) and not inv.is_expired(b):
                inv._move(b.pk, take, inv.M.RETURN, user=user, reason=f"Return {sr.number}", ref_type="sale_return", ref_id=sr.number)
                restocked += take
            todo -= take
        line.quantity_returned += qty
        line.amount_refunded += amount
        line.save(update_fields=["quantity_returned", "amount_refunded", "updated_at"])
        SaleReturnLine.objects.create(sale_return=sr, sale_line=line, quantity=qty, amount=amount, restocked_quantity=restocked)
        total += amount
    previously_refunded = sale.returns.aggregate(t=Sum("refund_total"))["t"] or ZERO  # excludes this return (still 0)
    if previously_refunded + total > sale.amount_paid:
        raise ValidationError({"lines": "The refund would exceed the amount paid."})
    sr.refund_total = total
    sr.save(update_fields=["refund_total", "updated_at"])
    done = not sale.lines.filter(quantity_returned__lt=models_F("quantity")).exists()
    sale.status = (Sale.Status.CANCELLED if is_cancellation else Sale.Status.RETURNED) if done else Sale.Status.PARTIALLY_RETURNED
    sale.save(update_fields=["status", "updated_at"])
    from apps.accounting.posting import post_sale_return
    post_sale_return(sr)
    audit.record("sale.cancelled" if is_cancellation else "sale.returned", actor=user, target=sale, branch_id=sale.branch_id,
                 credit_note=sr.number, refund=str(total), reason=reason)
    return sr


from django.db.models import F as models_F  # noqa: E402


def cancel_sale(sale_id, *, user, reason, refund_method, refund_reference="") -> SaleReturn:
    sale = Sale.objects.get(pk=sale_id)
    if sale.lines.filter(dispensing_item__isnull=False).exists():
        raise BusinessRuleViolation("A sale containing dispensed prescription items cannot be cancelled; process a return instead.")
    lines = [{"sale_line": l.pk, "quantity": l.quantity - l.quantity_returned} for l in sale.lines.all() if l.quantity > l.quantity_returned]
    return process_return(sale_id, user=user, lines=lines, reason=reason, refund_method=refund_method, refund_reference=refund_reference,
                          restock=True, is_cancellation=True)


# ======================= receipts =======================
def build_receipt_data(sale: Sale) -> dict:
    tenant = get_current_tenant()
    cur = (tenant.settings or {}).get("currency", "SLE")
    return {
        "pharmacy": tenant.name, "branch": sale.branch.name, "branch_address": sale.branch.address, "branch_phone": sale.branch.phone or tenant.contact_phone,
        "sale_reference": sale.reference_number, "date": sale.created_at.isoformat(), "cashier": sale.cashier.full_name,
        "customer": sale.customer_name, "currency": cur,
        "lines": [{"name": l.medicine.name, "quantity": l.quantity, "unit_price": str(l.unit_price), "discount": str(l.discount_amount),
                   "tax": str(l.tax_amount), "total": str(l.line_total)} for l in sale.lines.select_related("medicine")],
        "subtotal": str(sale.subtotal), "discount_total": str(sale.discount_total), "tax_total": str(sale.tax_total), "total": str(sale.total),
        "payments": [{"method": p.method, "amount": str(p.amount), "reference": p.reference} for p in sale.payments.all()],
        "amount_paid": str(sale.amount_paid), "change_due": str(sale.change_due),
        "payment_status": "Paid" if sale.amount_paid >= sale.total else "Partially paid",
    }


def render_receipt_pdf(r: dict) -> bytes:
    from io import BytesIO
    from reportlab.lib.pagesizes import A6
    from reportlab.pdfgen import canvas
    buf = BytesIO()
    w, h = A6
    c = canvas.Canvas(buf, pagesize=A6)
    y = h - 24

    def line(text, size=8, bold=False, x=14):
        nonlocal y
        if y < 30:
            c.showPage()
            y = h - 24
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, y, str(text)[:60])
        y -= size + 4

    line(r["pharmacy"], 11, True)
    line(f"{r['branch']} {r.get('branch_address') or ''}")
    line(f"Receipt {r['receipt_number']}  Sale {r['sale_reference']}")
    line(f"{r['date'][:19].replace('T', ' ')}  Cashier: {r['cashier']}")
    if r["customer"]:
        line(f"Customer: {r['customer']}")
    y -= 4
    for l in r["lines"]:
        line(f"{l['name']}", 8, True)
        line(f"  {l['quantity']} x {l['unit_price']}   tax {l['tax']}   = {l['total']}")
    y -= 4
    for k, label in (("subtotal", "Subtotal"), ("discount_total", "Discounts"), ("tax_total", "Tax"), ("total", "TOTAL")):
        line(f"{label}: {r['currency']} {r[k]}", 9, k == "total")
    for p in r["payments"]:
        line(f"Paid {p['method']}: {p['amount']} {p['reference']}")
    line(f"Change: {r['change_due']}   Status: {r['payment_status']}")
    c.save()
    return buf.getvalue()
