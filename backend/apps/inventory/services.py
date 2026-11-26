"""Inventory business rules. Every quantity change goes through `_move`, which (1) locks the batch row,
(2) applies a CONDITIONAL atomic UPDATE so stock can never go negative even if a lock is not honoured
(SQLite), and (3) writes an immutable StockMovement. Run inside tenant context."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation

from .models import Batch, StockMovement, StockTransfer

M = StockMovement.Type


class InsufficientStock(BusinessRuleViolation):
    default_code = "insufficient_stock"
    default_detail = "Not enough saleable stock available."


def today():
    return timezone.localdate()


def saleable_q(on=None) -> Q:
    """Saleable = available status, quantity > 0, not expired. Expired/recalled/quarantined/damaged never sell."""
    on = on or today()
    return Q(status=Batch.Status.AVAILABLE, quantity_available__gt=0) & (Q(expiry_date__isnull=True) | Q(expiry_date__gte=on))


def is_expired(batch: Batch) -> bool:
    return batch.expiry_date is not None and batch.expiry_date < today()


@transaction.atomic
def _move(batch_id, delta, movement_type, *, user, reason="", ref_type="", ref_id="") -> Batch:
    batch = Batch.objects.select_for_update(of=("self",)).select_related("medicine").get(pk=batch_id)
    prev = batch.quantity_available
    if delta == 0:
        raise ValidationError({"quantity": "Quantity change cannot be zero."})
    qs = Batch.objects.filter(pk=batch.pk)
    if delta < 0:
        qs = qs.filter(quantity_available__gte=-delta)  # conditional update: never below zero
    updates = {"quantity_available": F("quantity_available") + delta}
    if delta > 0 and movement_type in (M.RECEIPT, M.TRANSFER_IN, M.ADJUSTMENT):
        updates["quantity_received"] = F("quantity_received") + delta
    try:
        with transaction.atomic():
            updated = qs.update(**updates)
    except IntegrityError:
        raise ValidationError({"quantity": "Quantity would exceed the quantity received for this batch."})
    if not updated:
        raise InsufficientStock()
    mv = StockMovement.objects.create(
        medicine=batch.medicine, batch=batch, branch_id=batch.branch_id, movement_type=movement_type,
        quantity_change=delta, previous_quantity=prev, new_quantity=prev + delta, user=user, reason=reason[:255],
        reference_type=ref_type, reference_id=str(ref_id))
    batch.refresh_from_db()
    batch.last_movement = mv
    if delta < 0:
        _low_stock_push(batch)
    return batch


def _low_stock_push(batch):
    """Real-time alert when saleable stock at the branch falls to the reorder level (ids only)."""
    from django.db.models import Sum
    from apps.core.realtime import notify_topic
    m = batch.medicine
    if m.reorder_level <= 0:
        return
    left = Batch.objects.filter(medicine=m, branch_id=batch.branch_id).filter(saleable_q()).aggregate(t=Sum("quantity_available"))["t"] or 0
    if left <= m.reorder_level:
        notify_topic(batch.tenant_id, batch.branch_id, "inventory", "inventory.low_stock", {"medicine": m.pk, "name": m.name, "available": left})
        from apps.notifications import inapp
        from apps.notifications.models import Notification
        title = f"{'Out of stock' if left == 0 else 'Low stock'}: {m.name}"[:160]
        if not Notification.objects.filter(tenant_id=batch.tenant_id, title=title, read_at__isnull=True).exists():  # one open alert per product
            inapp.push_staff(batch.tenant_id, "inventory.view", batch.branch_id, kind="inventory", level="danger" if left == 0 else "warning",
                             title=title, body=f"{left} left at {batch.branch.name} (reorder level {m.reorder_level}).", link="/inventory")


@transaction.atomic
def receive_stock(*, medicine, branch, batch_number, quantity, purchase_cost, user, expiry_date=None, purchase_date=None,
                  manufacturing_date=None, supplier=None, supplier_name="", selling_price=None, storage_location="", ref_type="", ref_id="") -> Batch:
    if quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    if medicine.status != medicine.Status.ACTIVE:
        raise ValidationError({"medicine": "Archived medicines cannot receive stock."})
    if branch.status != branch.Status.ACTIVE:
        raise ValidationError({"branch": "This branch is inactive."})
    if medicine.has_expiry:
        if not expiry_date:
            raise ValidationError({"expiry_date": "An expiry date is required for this medicine."})
        if expiry_date < today():
            raise ValidationError({"expiry_date": "Expired stock cannot be received."})
    if manufacturing_date and expiry_date and manufacturing_date >= expiry_date:
        raise ValidationError({"manufacturing_date": "Manufacturing date must be before the expiry date."})
    batch_number = batch_number.strip()
    if not batch_number:
        raise ValidationError({"batch_number": "A batch number is required."})
    batch = Batch.objects.select_for_update(of=("self",)).filter(branch=branch, medicine=medicine, batch_number=batch_number).first()
    if batch is None:
        try:
            with transaction.atomic():
                batch = Batch.objects.create(
                    medicine=medicine, branch=branch, batch_number=batch_number, supplier=supplier,
                    supplier_name=supplier.name if supplier else supplier_name,
                    purchase_date=purchase_date or today(), manufacturing_date=manufacturing_date, expiry_date=expiry_date,
                    quantity_received=0, quantity_available=0, purchase_cost=purchase_cost, selling_price=selling_price,
                    storage_location=storage_location, received_by=user)
        except IntegrityError:  # concurrent first receipt of the same batch
            batch = Batch.objects.select_for_update(of=("self",)).get(branch=branch, medicine=medicine, batch_number=batch_number)
    else:
        if batch.status in (Batch.Status.RECALLED, Batch.Status.DAMAGED):
            raise ValidationError({"batch_number": f"This batch is {batch.status} and cannot receive stock."})
        if batch.expiry_date != expiry_date:
            raise ValidationError({"expiry_date": "This batch number already exists with a different expiry date."})
    batch = _move(batch.pk, quantity, M.RECEIPT, user=user, reason="Stock received", ref_type=ref_type or "receipt", ref_id=ref_id or batch.pk)
    audit.record("inventory.received", actor=user, target=batch, branch_id=batch.branch_id, quantity=quantity, batch=batch_number)
    return batch


@transaction.atomic
def deduct_fefo(*, medicine, branch, quantity, user, ref_type="sale", ref_id="", movement_type=M.SALE, reason="") -> list[tuple[Batch, int]]:
    """First-expiry-first-out (FIFO by purchase date when there is no expiry). All-or-nothing."""
    if quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    candidates = list(Batch.objects.select_for_update(of=("self",)).filter(medicine=medicine, branch=branch).filter(saleable_q())
                      .order_by(F("expiry_date").asc(nulls_last=True), "purchase_date", "id"))
    if sum(b.quantity_available for b in candidates) < quantity:
        raise InsufficientStock()
    remaining, allocations = quantity, []
    for b in candidates:
        take = min(b.quantity_available, remaining)
        _move(b.pk, -take, movement_type, user=user, reason=reason, ref_type=ref_type, ref_id=ref_id)
        allocations.append((b, take))
        remaining -= take
        if remaining == 0:
            break
    return allocations


@transaction.atomic
def adjust_stock(*, batch_id, new_quantity, reason, user) -> Batch:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required for stock adjustments."})
    batch = Batch.objects.select_for_update(of=("self",)).get(pk=batch_id)
    delta = new_quantity - batch.quantity_available
    if delta == 0:
        raise ValidationError({"new_quantity": "The quantity is unchanged."})
    batch = _move(batch.pk, delta, M.ADJUSTMENT, user=user, reason=reason, ref_type="adjustment")
    from apps.accounting.posting import post_stock_movement_value
    post_stock_movement_value(batch.last_movement)
    audit.record("inventory.adjusted", actor=user, target=batch, branch_id=batch.branch_id, delta=delta, reason=reason)
    return batch


@transaction.atomic
def write_off(*, batch_id, kind, reason, user, quantity=None) -> Batch:
    """kind: 'expired' (requires batch to be past expiry), 'damaged'. Zeroes (or reduces) stock; the batch row stays."""
    batch = Batch.objects.select_for_update(of=("self",)).get(pk=batch_id)
    if kind == "expired" and not is_expired(batch):
        raise ValidationError({"kind": "Only batches past their expiry date can be written off as expired."})
    if kind not in ("expired", "damaged"):
        raise ValidationError({"kind": "Choose 'expired' or 'damaged'."})
    qty = quantity or batch.quantity_available
    if qty <= 0 or qty > batch.quantity_available:
        raise ValidationError({"quantity": "Invalid write-off quantity."})
    batch = _move(batch.pk, -qty, M.EXPIRY_WRITEOFF if kind == "expired" else M.DAMAGE, user=user, reason=reason or kind, ref_type="writeoff")
    from apps.accounting.posting import post_stock_movement_value
    post_stock_movement_value(batch.last_movement)
    if kind == "damaged" and batch.quantity_available == 0:
        Batch.objects.filter(pk=batch.pk).update(status=Batch.Status.DAMAGED, status_reason=reason[:255])
    audit.record("inventory.written_off", actor=user, target=batch, branch_id=batch.branch_id, kind=kind, quantity=qty, reason=reason)
    return Batch.objects.get(pk=batch.pk)


_ALLOWED = {
    Batch.Status.AVAILABLE: {Batch.Status.QUARANTINED, Batch.Status.RECALLED, Batch.Status.DAMAGED},
    Batch.Status.QUARANTINED: {Batch.Status.AVAILABLE, Batch.Status.RECALLED, Batch.Status.DAMAGED},
    Batch.Status.DAMAGED: set(), Batch.Status.RECALLED: set(),  # terminal
}


@transaction.atomic
def set_batch_status(*, batch_id, status, reason, user) -> Batch:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required."})
    batch = Batch.objects.select_for_update(of=("self",)).get(pk=batch_id)
    if status not in _ALLOWED[batch.status]:
        raise ValidationError({"status": f"A {batch.status} batch cannot change to {status}."})
    if status == Batch.Status.AVAILABLE and is_expired(batch):
        raise ValidationError({"status": "An expired batch cannot be made available."})
    old = batch.status
    batch.status, batch.status_reason = status, reason[:255]
    batch.save(update_fields=["status", "status_reason", "updated_at"])
    audit.record(f"inventory.batch_{status}", actor=user, target=batch, branch_id=batch.branch_id, old=old, reason=reason)
    return batch


@transaction.atomic
def recall_batch_number(*, medicine, batch_number, reason, user) -> int:
    """Recall a manufacturer batch across ALL branches of the pharmacy."""
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required."})
    batches = list(Batch.objects.select_for_update(of=("self",)).filter(medicine=medicine, batch_number=batch_number)
                   .exclude(status=Batch.Status.RECALLED))
    for b in batches:
        b.status, b.status_reason = Batch.Status.RECALLED, reason[:255]
        b.save(update_fields=["status", "status_reason", "updated_at"])
        audit.record("inventory.batch_recalled", actor=user, target=b, branch_id=b.branch_id, reason=reason, recall_scope="pharmacy")
    return len(batches)


@transaction.atomic
def transfer_stock(*, batch_id, to_branch, quantity, user, reason="") -> StockTransfer:
    batch = Batch.objects.select_for_update(of=("self",)).select_related("medicine").get(pk=batch_id)
    if to_branch.pk == batch.branch_id:
        raise ValidationError({"to_branch": "Choose a different branch."})
    if to_branch.status != to_branch.Status.ACTIVE:
        raise ValidationError({"to_branch": "The destination branch is inactive."})
    if batch.status != Batch.Status.AVAILABLE or is_expired(batch):
        raise ValidationError({"batch": "Only available, unexpired batches can be transferred."})
    if quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    ref = f"{batch.branch_id}->{to_branch.pk}"
    _move(batch.pk, -quantity, M.TRANSFER_OUT, user=user, reason=reason, ref_type="transfer", ref_id=ref)
    dest = Batch.objects.select_for_update(of=("self",)).filter(branch=to_branch, medicine=batch.medicine, batch_number=batch.batch_number).first()
    if dest is None:
        dest = Batch.objects.create(
            medicine=batch.medicine, branch=to_branch, batch_number=batch.batch_number, supplier_id=batch.supplier_id, supplier_name=batch.supplier_name,
            purchase_date=batch.purchase_date, manufacturing_date=batch.manufacturing_date, expiry_date=batch.expiry_date,
            quantity_received=0, quantity_available=0, purchase_cost=batch.purchase_cost, selling_price=batch.selling_price,
            received_by=user)
    elif dest.expiry_date != batch.expiry_date or dest.status != Batch.Status.AVAILABLE:
        raise ValidationError({"batch": "The destination already holds this batch number with a different expiry or status."})
    _move(dest.pk, quantity, M.TRANSFER_IN, user=user, reason=reason, ref_type="transfer", ref_id=ref)
    t = StockTransfer.objects.create(from_branch_id=batch.branch_id, to_branch=to_branch, batch=batch, medicine=batch.medicine,
                                     quantity=quantity, created_by=user, reason=reason[:255])
    from apps.accounting.posting import post_transfer
    post_transfer(t)
    audit.record("inventory.transferred", actor=user, target=t, branch_id=batch.branch_id, to_branch=to_branch.pk, quantity=quantity)
    return t
