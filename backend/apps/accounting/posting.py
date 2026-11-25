"""Automatic postings. Each function is called INSIDE the originating business transaction, so a failure rolls the business event back
(the books and the operational records can never silently diverge) and each is idempotent per source event."""
from decimal import Decimal

from django.db.models import Sum

from .engine import pay_account, post_entry, q2
from .models import ZERO


def _unit_cost_of_line(line) -> Decimal:
    allocs = list(line.allocations.select_related("batch"))
    qty = sum(a.quantity for a in allocs)
    return (sum((a.quantity * a.batch.purchase_cost for a in allocs), ZERO) / qty) if qty else ZERO


# ---------------- sales ----------------
def post_sale(sale):
    b = sale.branch
    lines = [(pay_account(p.method), p.amount, 0, b) for p in sale.payments.all()]
    if sale.balance > 0:
        lines.append(("1100", sale.balance, 0, b))
    lines += [("4000", 0, sale.subtotal + sale.discount_total, b), ("4900", sale.discount_total, 0, b), ("2100", 0, sale.tax_total, b)]
    cost = sum((a.quantity * a.batch.purchase_cost for l in sale.lines.all() for a in l.allocations.select_related("batch")), ZERO)
    lines += [("5000", cost, 0, b), ("1200", 0, cost, b)]
    return post_entry(description=f"Sale {sale.reference_number}", lines=lines, source_type="sale", source_id=sale.pk, user=sale.cashier, branch=b)


def post_sale_payments(sale, payments):
    if not payments:
        return None
    b = sale.branch
    lines = [(pay_account(p.method), p.amount, 0, b) for p in payments] + [("1100", 0, sum((p.amount for p in payments), ZERO), b)]
    return post_entry(description=f"Payment on sale {sale.reference_number}", lines=lines, source_type="sale_payment", source_id=min(p.pk for p in payments), branch=b)


def post_sale_return(sr):
    sale, b = sr.sale, sr.sale.branch
    net_total = tax_total = restock_value = ZERO
    for rl in sr.lines.select_related("sale_line"):
        line = rl.sale_line
        tax = q2(rl.amount * line.tax_amount / line.line_total) if line.line_total else ZERO
        tax_total += tax
        net_total += rl.amount - tax
        restock_value += q2(rl.restocked_quantity * _unit_cost_of_line(line))
    lines = [("4950", net_total, 0, b), ("2100", tax_total, 0, b), (pay_account(sr.refund_method), 0, sr.refund_total, b), ("1200", restock_value, 0, b), ("5000", 0, restock_value, b)]
    return post_entry(description=f"{'Cancellation' if sr.is_cancellation else 'Return'} {sr.number} of {sale.reference_number}", lines=lines, source_type="sale_return",
                      source_id=sr.pk, user=sr.processed_by, branch=b)


def post_shift_close(shift):
    d = shift.discrepancy or ZERO
    if d == 0:
        return None
    b = shift.branch
    lines = [("6950", -d, 0, b), ("1000", 0, -d, b)] if d < 0 else [("1000", d, 0, b), ("6950", 0, d, b)]
    return post_entry(description=f"Cash {'shortage' if d < 0 else 'overage'} at shift close #{shift.pk}", lines=lines, source_type="shift_close", source_id=shift.pk, user=shift.cashier, branch=b)


def post_cash_movement(m):
    b = m.shift.branch
    lines = [("1020", m.amount, 0, b), ("1000", 0, m.amount, b)] if m.kind == "withdrawal" else [("1000", m.amount, 0, b), ("1020", 0, m.amount, b)]
    return post_entry(description=f"Cash {m.kind}: {m.reason}", lines=lines, source_type="cash_movement", source_id=m.pk, user=m.decided_by or m.requested_by, branch=b)


# ---------------- procurement & inventory ----------------
def post_goods_receipt(grn):
    value = sum((i.quantity * i.unit_cost for i in grn.items.all()), ZERO)
    return post_entry(description=f"Goods received {grn.number}", lines=[("1200", value, 0, grn.branch), ("2000", 0, value, grn.branch)], source_type="grn", source_id=grn.pk, user=grn.received_by, branch=grn.branch)


def post_supplier_payment(pay):
    return post_entry(description=f"Supplier payment {pay.reference}", lines=[("2000", pay.amount, 0), (pay_account(pay.method), 0, pay.amount)], source_type="supplier_payment", source_id=pay.pk, user=pay.paid_by)


def post_purchase_return(pr):
    b = pr.batch.branch
    cost = q2(pr.quantity * pr.batch.purchase_cost)
    return post_entry(description=f"Purchase return to {pr.supplier.name}", lines=[("2000", cost, 0, b), ("1200", 0, cost, b)], source_type="purchase_return", source_id=pr.pk, user=pr.created_by, branch=b)


def post_stock_movement_value(movement):
    """Write-offs, damage and adjustments change inventory value without a sale or purchase."""
    value = q2(abs(movement.quantity_change) * movement.batch.purchase_cost)
    b = movement.branch
    if movement.quantity_change < 0:
        lines = [("5100", value, 0, b), ("1200", 0, value, b)]
    else:
        lines = [("1200", value, 0, b), ("5100", 0, value, b)]
    return post_entry(description=f"Stock {movement.movement_type}: {movement.medicine.name} batch {movement.batch.batch_number}", lines=lines, source_type="stock_adjustment",
                      source_id=movement.pk, user=movement.user, branch=b)


def post_transfer(t):
    value = q2(t.quantity * t.batch.purchase_cost)
    return post_entry(description=f"Stock transfer of {t.medicine.name}", lines=[("1200", value, 0, t.to_branch), ("1200", 0, value, t.from_branch)], source_type="stock_transfer", source_id=t.pk, user=t.created_by)


# ---------------- online orders ----------------
def post_order_payment(order):
    """Cash received is NOT revenue yet: it is held as a customer prepayment until the order is delivered/completed."""
    return post_entry(description=f"Payment received for order {order.reference_number}", lines=[(pay_account(order.payment_method), order.total, 0, order.branch), ("2200", 0, order.total, order.branch)],
                      source_type="order_payment", source_id=order.pk, branch=order.branch)


def post_order_revenue(order):
    from apps.inventory.models import StockMovement
    from apps.prescriptions.models import DispensingItem
    b = order.branch
    cost = sum((abs(m.quantity_change) * m.batch.purchase_cost for m in StockMovement.objects.filter(reference_type="online_order", reference_id=order.reference_number, movement_type="sale").select_related("batch")), ZERO)
    if order.prescription_id:
        rx_meds = [l.medicine_id for l in order.lines.select_related("medicine") if l.medicine.requires_prescription]
        cost += sum((di.quantity * di.batch.purchase_cost for di in DispensingItem.objects.filter(dispensing__prescription_id=order.prescription_id, item__medicine_id__in=rx_meds).select_related("batch")), ZERO)
    lines = [("2200", order.total, 0, b), ("4000", 0, order.subtotal, b), ("4100", 0, order.delivery_fee, b), ("2100", 0, order.tax_total, b), ("5000", cost, 0, b), ("1200", 0, cost, b)]
    return post_entry(description=f"Revenue recognised for order {order.reference_number}", lines=lines, source_type="order_revenue", source_id=order.pk, branch=b)


def post_order_refund(refund):
    from .models import JournalEntry
    order, b = refund.order, refund.order.branch
    recognised = JournalEntry.objects.filter(source_type="order_revenue", source_id=str(order.pk)).exists()
    if recognised:
        tax = q2(order.tax_total * refund.amount / order.total) if order.total else ZERO
        debit_lines = [("4950", refund.amount - tax, 0, b), ("2100", tax, 0, b)]
    else:
        debit_lines = [("2200", refund.amount, 0, b)]
    return post_entry(description=f"Refund {refund.reference} for order {order.reference_number}", lines=debit_lines + [(pay_account(refund.method), 0, refund.amount, b)],
                      source_type="order_refund", source_id=refund.pk, user=refund.processed_by, branch=b)


def post_unfulfillable_payment(attempt):
    """Money received for an order that could no longer accept it: held as a refund liability until it is paid back."""
    o = attempt.order
    return post_entry(description=f"Payment {attempt.reference} received for unpayable order {o.reference_number}", lines=[("1010", attempt.amount, 0, o.branch), ("2250", 0, attempt.amount, o.branch)],
                      source_type="payment_unapplied", source_id=attempt.pk, branch=o.branch)
