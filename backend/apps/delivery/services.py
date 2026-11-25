from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation
from apps.core.realtime import notify_topic
from apps.shop import services as shop
from apps.shop.models import Order

from .models import Delivery

S = Order.Status


def _push(d: Delivery):
    o = d.order
    notify_topic(d.tenant_id, o.branch_id, "orders", "delivery.updated", {"id": d.pk, "order": o.pk, "reference": o.reference_number, "status": d.status}, users=[d.driver_id, o.customer_id])


@transaction.atomic
def assign(order_id, driver_id, *, actor: User, note="") -> Delivery:
    order = Order.objects.select_for_update(of=("self",)).get(pk=order_id)
    if order.fulfilment != "delivery":
        raise BusinessRuleViolation("Only delivery orders can be assigned to a driver.")
    if order.status not in (S.PREPARING, S.OUT_FOR_DELIVERY):
        raise BusinessRuleViolation("Orders can be assigned once they are being prepared.")
    driver = User.objects.filter(pk=driver_id, tenant=order.tenant, is_active=True, role__code="delivery_personnel", branch_id=order.branch_id).first()
    if driver is None:
        raise ValidationError({"driver": "Choose an active delivery person of the order's branch."})
    if actor.is_branch_scoped and actor.branch_id != order.branch_id:
        raise PermissionDenied("This order belongs to another branch.")
    Delivery.objects.filter(order=order, status__in=("assigned", "picked_up")).update(status="cancelled", finished_at=timezone.now(), note="Reassigned")
    try:
        with transaction.atomic():
            d = Delivery.objects.create(order=order, driver=driver, assigned_by=actor, note=note[:300])
    except IntegrityError:
        raise BusinessRuleViolation("This order already has an active delivery.")
    audit.record("delivery.assigned", actor=actor, target=d, branch_id=order.branch_id, order=order.reference_number, driver=driver.pk)
    _push(d)
    return d


@transaction.atomic
def pickup(pk, *, driver: User) -> Delivery:
    d = Delivery.objects.select_for_update(of=("self",)).select_related("order").get(pk=pk, driver=driver)
    if d.status != "assigned":
        raise BusinessRuleViolation("This delivery is not waiting for pickup.")
    if d.order.status == S.PREPARING:
        shop.transition(d.order_id, S.OUT_FOR_DELIVERY, actor=driver, kind="system", note="Picked up by driver")
    elif d.order.status != S.OUT_FOR_DELIVERY:
        raise BusinessRuleViolation("The order is not ready for delivery.")
    d.status, d.picked_up_at = "picked_up", timezone.now()
    d.save()
    audit.record("delivery.picked_up", actor=driver, target=d, branch_id=d.order.branch_id)
    _push(d)
    return d


@transaction.atomic
def deliver(pk, *, driver: User, note="") -> Delivery:
    d = Delivery.objects.select_for_update(of=("self",)).select_related("order").get(pk=pk, driver=driver)
    if d.status != "picked_up":
        raise BusinessRuleViolation("Pick up the order before marking it delivered.")
    shop.transition(d.order_id, S.DELIVERED, actor=driver, kind="system", note="Delivered by driver")
    d.status, d.finished_at, d.note = "delivered", timezone.now(), note[:300] or d.note
    d.save()
    audit.record("delivery.delivered", actor=driver, target=d, branch_id=d.order.branch_id)
    _push(d)
    return d


@transaction.atomic
def fail(pk, *, driver: User, reason: str) -> Delivery:
    d = Delivery.objects.select_for_update(of=("self",)).select_related("order").get(pk=pk, driver=driver)
    if d.status not in ("assigned", "picked_up"):
        raise BusinessRuleViolation("This delivery is already finished.")
    if not reason.strip():
        raise ValidationError({"reason": "Enter why the delivery failed."})
    d.status, d.finished_at, d.note = "failed", timezone.now(), reason[:300]
    d.save()
    audit.record("delivery.failed", actor=driver, target=d, branch_id=d.order.branch_id, reason=reason)  # the order stays open so staff can reassign
    _push(d)
    return d
