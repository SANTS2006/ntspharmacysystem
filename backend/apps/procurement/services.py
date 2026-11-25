"""Procurement workflow. All state changes lock the row, validate the transition, and write an audit entry."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory import services as inv
from apps.inventory.models import Batch

from .models import (GoodsReceipt, GoodsReceiptItem, PurchaseOrder, PurchaseOrderItem, PurchaseReturn, Requisition,
                     RequisitionItem, SupplierInvoice, SupplierPayment, next_number)

PO, REQ, INV = PurchaseOrder.Status, Requisition.Status, SupplierInvoice.Status


def _transition(obj, allowed_from, to, label):
    if obj.status not in allowed_from:
        raise BusinessRuleViolation(f"A {obj.status.replace('_', ' ')} {label} cannot be changed to {to.replace('_', ' ')}.")


def approval_threshold(tenant) -> Decimal:
    return Decimal(str((tenant.settings or {}).get("po_approval_threshold", 1000)))


# ---------------- requisitions ----------------
@transaction.atomic
def create_requisition(*, branch, user, items, notes="", submit=False) -> Requisition:
    if not items:
        raise ValidationError({"items": "Add at least one medicine."})
    r = Requisition.objects.create(number=next_number("REQ"), branch=branch, requested_by=user, notes=notes[:255])
    for it in items:
        RequisitionItem.objects.create(requisition=r, medicine=it["medicine"], quantity=it["quantity"])
    audit.record("procurement.requisition_created", actor=user, target=r, branch_id=branch.pk, number=r.number)
    return submit_requisition(r.pk, user=user) if submit else r


@transaction.atomic
def submit_requisition(pk, *, user) -> Requisition:
    r = Requisition.objects.select_for_update(of=("self",)).get(pk=pk)
    _transition(r, {REQ.DRAFT}, REQ.SUBMITTED, "requisition")
    r.status = REQ.SUBMITTED
    r.save(update_fields=["status", "updated_at"])
    audit.record("procurement.requisition_submitted", actor=user, target=r, branch_id=r.branch_id)
    return r


@transaction.atomic
def decide_requisition(pk, *, approve: bool, user, note="") -> Requisition:
    r = Requisition.objects.select_for_update(of=("self",)).get(pk=pk)
    _transition(r, {REQ.SUBMITTED}, REQ.APPROVED if approve else REQ.REJECTED, "requisition")
    if r.requested_by_id == user.pk:
        raise PermissionDenied("You cannot approve your own requisition.")
    r.status = REQ.APPROVED if approve else REQ.REJECTED
    r.decided_by, r.decided_at, r.decision_note = user, timezone.now(), note[:255]
    r.save()
    audit.record(f"procurement.requisition_{r.status}", actor=user, target=r, branch_id=r.branch_id, note=note)
    return r


@transaction.atomic
def cancel_requisition(pk, *, user) -> Requisition:
    r = Requisition.objects.select_for_update(of=("self",)).get(pk=pk)
    _transition(r, {REQ.DRAFT, REQ.SUBMITTED}, REQ.CANCELLED, "requisition")
    r.status = REQ.CANCELLED
    r.save(update_fields=["status", "updated_at"])
    audit.record("procurement.requisition_cancelled", actor=user, target=r, branch_id=r.branch_id)
    return r


# ---------------- purchase orders ----------------
@transaction.atomic
def create_order(*, branch, supplier, user, items, expected_date=None, notes="", requisition=None) -> PurchaseOrder:
    if not items:
        raise ValidationError({"items": "Add at least one medicine."})
    if supplier.status != supplier.Status.ACTIVE:
        raise ValidationError({"supplier": "This supplier is inactive."})
    if requisition is not None:
        if requisition.status != REQ.APPROVED:
            raise ValidationError({"requisition": "Only approved requisitions can be converted to a purchase order."})
        if requisition.branch_id != branch.pk:
            raise ValidationError({"requisition": "The requisition belongs to a different branch."})
    seen = set()
    for it in items:
        if it["medicine"].pk in seen:
            raise ValidationError({"items": "A medicine appears more than once."})
        seen.add(it["medicine"].pk)
        if it["medicine"].status != "active":
            raise ValidationError({"items": f"{it['medicine'].name} is archived."})
    po = PurchaseOrder.objects.create(number=next_number("PO"), branch=branch, supplier=supplier, requisition=requisition,
                                      expected_date=expected_date, notes=notes[:255], created_by=user)
    total = Decimal("0")
    for it in items:
        PurchaseOrderItem.objects.create(order=po, medicine=it["medicine"], quantity_ordered=it["quantity"], unit_cost=it["unit_cost"])
        total += it["quantity"] * it["unit_cost"]
    po.total = total
    po.save(update_fields=["total", "updated_at"])
    audit.record("procurement.order_created", actor=user, target=po, branch_id=branch.pk, number=po.number, total=str(total))
    return po


@transaction.atomic
def submit_order(pk, *, user) -> PurchaseOrder:
    """Orders at or below the tenant's threshold are approved automatically; larger ones need an approver."""
    po = PurchaseOrder.objects.select_for_update(of=("self",)).select_related("branch").get(pk=pk)
    _transition(po, {PO.DRAFT}, PO.PENDING_APPROVAL, "purchase order")
    from apps.core.tenant_context import get_current_tenant
    if po.total > approval_threshold(get_current_tenant()):
        po.status = PO.PENDING_APPROVAL
    else:
        po.status, po.approved_by, po.decided_at = PO.APPROVED, user, timezone.now()
    po.save()
    audit.record("procurement.order_submitted", actor=user, target=po, branch_id=po.branch_id, outcome=po.status)
    return po


@transaction.atomic
def decide_order(pk, *, approve: bool, user, note="") -> PurchaseOrder:
    po = PurchaseOrder.objects.select_for_update(of=("self",)).get(pk=pk)
    _transition(po, {PO.PENDING_APPROVAL}, PO.APPROVED if approve else PO.REJECTED, "purchase order")
    if po.created_by_id == user.pk:
        raise PermissionDenied("You cannot approve a purchase order you created.")  # segregation of duties
    po.status = PO.APPROVED if approve else PO.REJECTED
    po.approved_by, po.decided_at, po.decision_note = user, timezone.now(), note[:255]
    po.save()
    audit.record(f"procurement.order_{po.status}", actor=user, target=po, branch_id=po.branch_id, note=note)
    return po


@transaction.atomic
def cancel_order(pk, *, user) -> PurchaseOrder:
    po = PurchaseOrder.objects.select_for_update(of=("self",)).get(pk=pk)
    _transition(po, {PO.DRAFT, PO.PENDING_APPROVAL, PO.APPROVED}, PO.CANCELLED, "purchase order")
    if po.receipts.exists():
        raise BusinessRuleViolation("An order with deliveries recorded cannot be cancelled.")
    po.status = PO.CANCELLED
    po.save(update_fields=["status", "updated_at"])
    audit.record("procurement.order_cancelled", actor=user, target=po, branch_id=po.branch_id)
    return po


# ---------------- goods receipt (GRN) ----------------
@transaction.atomic
def receive_goods(*, order_id, user, lines, delivery_note="", notes="") -> GoodsReceipt:
    """lines: [{order_item: PurchaseOrderItem pk, quantity, batch_number, expiry_date, selling_price?}].
    Supports partial deliveries; never exceeds the quantity ordered; creates batches through the inventory service."""
    po = PurchaseOrder.objects.select_for_update(of=("self",)).select_related("supplier", "branch").get(pk=order_id)
    if po.status not in (PO.APPROVED, PO.PARTIALLY_RECEIVED):
        raise BusinessRuleViolation("Only approved orders can receive goods.")
    if not lines:
        raise ValidationError({"lines": "Add at least one delivered line."})
    grn = GoodsReceipt.objects.create(number=next_number("GRN"), order=po, branch=po.branch, delivery_note=delivery_note[:60],
                                      received_by=user, notes=notes[:255])
    for ln in lines:
        item = PurchaseOrderItem.objects.select_for_update(of=("self",)).select_related("medicine").filter(pk=ln["order_item"], order=po).first()
        if item is None:
            raise ValidationError({"lines": "A line does not belong to this order."})
        qty = ln["quantity"]
        if qty <= 0 or item.quantity_received + qty > item.quantity_ordered:
            raise ValidationError({"lines": f"{item.medicine.name}: cannot receive more than the {item.quantity_ordered - item.quantity_received} still outstanding."})
        batch = inv.receive_stock(medicine=item.medicine, branch=po.branch, batch_number=ln["batch_number"], quantity=qty,
                                  purchase_cost=item.unit_cost, user=user, expiry_date=ln.get("expiry_date"), supplier=po.supplier,
                                  selling_price=ln.get("selling_price"), ref_type="grn", ref_id=grn.number)
        item.quantity_received += qty
        item.save(update_fields=["quantity_received", "updated_at"])
        GoodsReceiptItem.objects.create(receipt=grn, order_item=item, batch=batch, quantity=qty, unit_cost=item.unit_cost)
    done = not po.items.filter(quantity_received__lt=models_F("quantity_ordered")).exists()
    po.status = PO.RECEIVED if done else PO.PARTIALLY_RECEIVED
    po.save(update_fields=["status", "updated_at"])
    from apps.accounting.posting import post_goods_receipt
    post_goods_receipt(grn)
    audit.record("procurement.goods_received", actor=user, target=grn, branch_id=po.branch_id, order=po.number, number=grn.number)
    return grn


from django.db.models import F as models_F  # noqa: E402


# ---------------- supplier invoices and payments ----------------
@transaction.atomic
def record_invoice(*, supplier, invoice_number, amount, due_date, user, order=None) -> SupplierInvoice:
    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    if order is not None and order.supplier_id != supplier.pk:
        raise ValidationError({"order": "This order belongs to a different supplier."})
    if SupplierInvoice.objects.filter(supplier=supplier, invoice_number=invoice_number).exists():
        raise ValidationError({"invoice_number": "This supplier invoice was already recorded."})
    inv_ = SupplierInvoice.objects.create(supplier=supplier, order=order, invoice_number=invoice_number, amount=amount,
                                          due_date=due_date, created_by=user)
    audit.record("procurement.invoice_recorded", actor=user, target=inv_, invoice=invoice_number, amount=str(amount))
    return inv_


@transaction.atomic
def pay_invoice(pk, *, amount: Decimal, method: str, reference: str, user) -> SupplierPayment:
    invoice = SupplierInvoice.objects.select_for_update(of=("self",)).get(pk=pk)
    reference = reference.strip()
    if not reference or not method:
        raise ValidationError({"reference": "A payment method and reference are required."})
    if invoice.status in (INV.PAID, INV.CANCELLED):
        raise BusinessRuleViolation(f"This invoice is {invoice.status}.")
    if amount <= 0 or amount > invoice.balance:
        raise ValidationError({"amount": f"Amount must be between 0.01 and the outstanding balance ({invoice.balance})."})
    if SupplierPayment.objects.filter(reference=reference).exists():
        raise ValidationError({"reference": "This payment reference was already recorded."})
    pay = SupplierPayment.objects.create(invoice=invoice, amount=amount, method=method[:30], reference=reference[:100], paid_by=user)
    invoice.amount_paid += amount
    invoice.status = INV.PAID if invoice.amount_paid == invoice.amount else INV.PARTIALLY_PAID
    invoice.save()
    from apps.accounting.posting import post_supplier_payment
    post_supplier_payment(pay)
    audit.record("procurement.supplier_paid", actor=user, target=pay, invoice=invoice.invoice_number, amount=str(amount), reference=reference)
    return pay


def supplier_balances():
    rows = (SupplierInvoice.objects.exclude(status=INV.CANCELLED).values("supplier_id", "supplier__name")
            .annotate(invoiced=Sum("amount"), paid=Sum("amount_paid")))
    return [{"supplier": r["supplier_id"], "name": r["supplier__name"], "invoiced": r["invoiced"], "paid": r["paid"],
             "outstanding": r["invoiced"] - r["paid"]} for r in rows if r["invoiced"] - r["paid"] > 0]


# ---------------- purchase returns ----------------
@transaction.atomic
def return_to_supplier(*, batch_id, quantity, reason, user, credit_amount=Decimal("0")) -> PurchaseReturn:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required."})
    batch = Batch.objects.select_for_update(of=("self",)).get(pk=batch_id)
    if batch.supplier_id is None:
        raise ValidationError({"batch": "This batch has no supplier on record."})
    inv._move(batch.pk, -quantity, inv.M.PURCHASE_RETURN, user=user, reason=reason, ref_type="purchase_return", ref_id=batch.batch_number)
    pr = PurchaseReturn.objects.create(supplier_id=batch.supplier_id, batch=batch, quantity=quantity, reason=reason[:255],
                                       credit_amount=credit_amount, created_by=user)
    from apps.accounting.posting import post_purchase_return
    post_purchase_return(pr)
    audit.record("procurement.purchase_return", actor=user, target=pr, branch_id=batch.branch_id, quantity=quantity, reason=reason)
    return pr
