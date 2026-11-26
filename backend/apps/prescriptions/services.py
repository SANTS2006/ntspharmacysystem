from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory import services as inv
from apps.inventory.models import Batch
from apps.procurement.models import next_number

from . import safety
from .models import (ClinicalIntervention, ControlledDrugRegisterEntry, Dispensing, DispensingItem, Prescription,
                     PrescriptionItem, SafetyAlert)

S = Prescription.Status
LIVE = {S.RECEIVED, S.UNDER_REVIEW, S.APPROVED, S.PARTIALLY_DISPENSED}
CHECKLIST = ("prescriber_verified", "patient_verified", "dosage_reviewed")


def today():
    return timezone.localdate()


def effective_status(rx: Prescription) -> str:
    return S.EXPIRED if rx.status in LIVE and today() > rx.expiry_date else rx.status


def _push(rx, event="prescription.updated"):
    from apps.core.realtime import notify_topic
    notify_topic(rx.tenant_id, rx.branch_id, "prescriptions", event, {"id": rx.pk, "reference": rx.reference_number, "status": rx.status})
    from apps.notifications import inapp
    status = rx.status.replace("_", " ")
    needs_review = rx.status in ("submitted", "pending", "received")  # no patient names in notifications: the record itself is permission-checked
    inapp.push_staff(rx.tenant_id, "prescription.verify" if needs_review else "prescription.view", rx.branch_id, kind="prescription",
                     level="warning" if needs_review else "info", title=f"Prescription {rx.reference_number}: {status}",
                     body="A prescription is waiting for pharmacist review." if needs_review else f"Prescription status changed to {status}.", link="/prescriptions")


def _lock(pk) -> Prescription:
    return Prescription.objects.select_for_update(of=("self",)).select_related("patient", "branch").get(pk=pk)


def _not_expired(rx):
    if today() > rx.expiry_date:
        raise BusinessRuleViolation("This prescription has expired.")


def _must_be(rx, allowed, action):
    if rx.status not in allowed:
        raise BusinessRuleViolation(f"A {rx.status.replace('_', ' ')} prescription cannot be {action}.")


@transaction.atomic
def create_prescription(*, patient, branch, user, items, prescriber_name, prescription_date, prescriber_registration="",
                        facility="", external_reference="", refills_allowed=0, notes="", expiry_date=None) -> Prescription:
    if not items:
        raise ValidationError({"items": "Add at least one medicine."})
    if prescription_date > today():
        raise ValidationError({"prescription_date": "The prescription date cannot be in the future."})
    from apps.core.tenant_context import get_current_tenant
    validity = int((get_current_tenant().settings or {}).get("prescription_validity_days", 30))
    expiry = expiry_date or prescription_date + timedelta(days=validity)
    if expiry < today():
        raise ValidationError({"prescription_date": "This prescription has already expired."})
    rx = Prescription.objects.create(
        reference_number=next_number("RX"), external_reference=external_reference, patient=patient, branch=branch,
        prescriber_name=prescriber_name, prescriber_registration=prescriber_registration, facility=facility,
        prescription_date=prescription_date, expiry_date=expiry, refills_allowed=refills_allowed, notes=notes, entered_by=user)
    for it in items:
        if it["medicine"].status != "active":
            raise ValidationError({"items": f"{it['medicine'].name} is archived."})
        PrescriptionItem.objects.create(prescription=rx, **it)
    audit.record("prescription.created", actor=user, target=rx, branch_id=branch.pk, reference=rx.reference_number)
    _push(rx, "prescription.created")
    return rx


@transaction.atomic
def start_review(pk, *, user) -> Prescription:
    rx = _lock(pk)
    _must_be(rx, {S.RECEIVED}, "reviewed")
    _not_expired(rx)
    rx.status, rx.reviewed_by = S.UNDER_REVIEW, user
    rx.save(update_fields=["status", "reviewed_by", "updated_at"])
    safety.run_checks(rx)
    audit.record("prescription.review_started", actor=user, target=rx, branch_id=rx.branch_id)
    _push(rx)
    return rx


@transaction.atomic
def recheck_safety(pk, *, user) -> list:
    rx = _lock(pk)
    _must_be(rx, LIVE, "re-checked")
    return safety.run_checks(rx)


@transaction.atomic
def acknowledge_alert(pk, alert_id, *, user, note) -> SafetyAlert:
    rx = _lock(pk)
    if not note.strip():
        raise ValidationError({"note": "Record your decision about this alert."})
    a = rx.alerts.select_for_update(of=("self",)).get(pk=alert_id)
    a.decision, a.decision_note, a.decided_by, a.decided_at = "acknowledged", note[:500], user, timezone.now()
    a.save()
    audit.record("prescription.alert_acknowledged", actor=user, target=rx, branch_id=rx.branch_id, alert=a.key, severity=a.severity)
    return a


@transaction.atomic
def record_intervention(pk, *, user, intervention_type, note, outcome="") -> ClinicalIntervention:
    rx = _lock(pk)
    if not intervention_type.strip() or not note.strip():
        raise ValidationError({"note": "Enter the intervention type and note."})
    iv = ClinicalIntervention.objects.create(prescription=rx, pharmacist=user, intervention_type=intervention_type[:60], note=note, outcome=outcome[:200])
    audit.record("prescription.intervention", actor=user, target=rx, branch_id=rx.branch_id, type=intervention_type)
    return iv


def availability(rx: Prescription) -> list[dict]:
    out = []
    for it in rx.items.select_related("medicine"):
        have = (Batch.objects.filter(medicine=it.medicine, branch=rx.branch).filter(inv.saleable_q()).aggregate(t=Sum("quantity_available"))["t"] or 0)
        need = it.quantity_prescribed - it.quantity_dispensed
        out.append({"item": it.pk, "medicine": it.medicine.name, "needed": need, "available": have, "sufficient": have >= need})
    return out


@transaction.atomic
def approve(pk, *, user, checklist: dict) -> Prescription:
    rx = _lock(pk)
    _must_be(rx, {S.UNDER_REVIEW}, "approved")  # must have been reviewed first: an uploaded image alone never authorizes dispensing
    _not_expired(rx)
    if rx.reviewed_by_id is None:
        raise BusinessRuleViolation("The prescription has not been reviewed by a pharmacist.")
    missing = [k for k in CHECKLIST if checklist.get(k) is not True]
    if missing:
        raise ValidationError({"verification": f"Confirm each verification step: {', '.join(missing)}."})
    safety.run_checks(rx)
    blocking = list(safety.open_critical(rx))
    if blocking:
        raise BusinessRuleViolation(f"{len(blocking)} critical safety alert(s) need a documented pharmacist decision before approval.")
    rx.status, rx.decided_by, rx.decided_at, rx.verification = S.APPROVED, user, timezone.now(), {k: True for k in CHECKLIST}
    rx.save()
    audit.record("prescription.approved", actor=user, target=rx, branch_id=rx.branch_id)
    _push(rx)
    from apps.shop.services import on_prescription_decision  # online orders follow the pharmacist's decision
    on_prescription_decision(rx, True, user)
    return rx


@transaction.atomic
def reject(pk, *, user, reason) -> Prescription:
    rx = _lock(pk)
    _must_be(rx, {S.RECEIVED, S.UNDER_REVIEW}, "rejected")
    if not reason.strip():
        raise ValidationError({"reason": "A rejection reason is required."})
    rx.status, rx.decided_by, rx.decided_at, rx.rejection_reason = S.REJECTED, user, timezone.now(), reason[:500]
    rx.save()
    audit.record("prescription.rejected", actor=user, target=rx, branch_id=rx.branch_id, reason=reason)
    _push(rx)
    from apps.shop.services import on_prescription_decision
    on_prescription_decision(rx, False, user)
    return rx


@transaction.atomic
def cancel(pk, *, user, reason) -> Prescription:
    rx = _lock(pk)
    _must_be(rx, {S.RECEIVED, S.UNDER_REVIEW, S.APPROVED, S.PARTIALLY_DISPENSED}, "cancelled")
    if not reason.strip():
        raise ValidationError({"reason": "A cancellation reason is required."})
    rx.status, rx.rejection_reason = S.CANCELLED, reason[:500]
    rx.save(update_fields=["status", "rejection_reason", "updated_at"])
    audit.record("prescription.cancelled", actor=user, target=rx, branch_id=rx.branch_id, reason=reason)
    return rx


@transaction.atomic
def dispense(pk, *, user, lines, notes="") -> Dispensing:
    """lines: [{item: PrescriptionItem pk, quantity}]. All-or-nothing. Stock comes from saleable (unexpired, available) batches, FEFO."""
    rx = _lock(pk)
    _must_be(rx, {S.APPROVED, S.PARTIALLY_DISPENSED}, "dispensed")
    _not_expired(rx)
    if not lines:
        raise ValidationError({"lines": "Choose at least one item to dispense."})
    safety.run_checks(rx)  # patient data may have changed since approval
    if safety.open_critical(rx).exists():
        raise BusinessRuleViolation("Critical safety alerts need a documented pharmacist decision before dispensing.")
    d = Dispensing.objects.create(prescription=rx, branch=rx.branch, dispensed_by=user, refill_number=rx.refills_used, notes=notes[:300])
    seen = set()
    for ln in lines:
        if ln["item"] in seen:
            raise ValidationError({"lines": "An item appears more than once."})
        seen.add(ln["item"])
        item = PrescriptionItem.objects.select_for_update(of=("self",)).select_related("medicine").filter(pk=ln["item"], prescription=rx).first()
        if item is None:
            raise ValidationError({"lines": "A line does not belong to this prescription."})
        qty = ln["quantity"]
        if qty <= 0 or item.quantity_dispensed + qty > item.quantity_prescribed:
            raise ValidationError({"lines": f"{item.medicine.name}: only {item.quantity_prescribed - item.quantity_dispensed} remaining to dispense."})
        if item.medicine.status != "active":
            raise ValidationError({"lines": f"{item.medicine.name} is archived."})
        allocations = inv.deduct_fefo(medicine=item.medicine, branch=rx.branch, quantity=qty, user=user, movement_type=inv.M.DISPENSE,
                                      ref_type="prescription", ref_id=rx.reference_number, reason=f"Dispensed on {rx.reference_number}")
        for batch, taken in allocations:
            DispensingItem.objects.create(dispensing=d, item=item, batch=batch, quantity=taken)
            if item.medicine.classification == item.medicine.Classification.CONTROLLED:
                ControlledDrugRegisterEntry.objects.create(
                    medicine=item.medicine, batch=batch, prescription=rx, quantity=taken, patient_name=rx.patient.full_name,
                    balance_after=Batch.objects.get(pk=batch.pk).quantity_available, prescriber_name=rx.prescriber_name,
                    prescriber_registration=rx.prescriber_registration, pharmacist=user)
        item.quantity_dispensed += qty
        item.save(update_fields=["quantity_dispensed", "updated_at"])
    complete = not rx.items.filter(quantity_dispensed__lt=models_F("quantity_prescribed")).exists()
    rx.status = S.DISPENSED if complete else S.PARTIALLY_DISPENSED
    rx.save(update_fields=["status", "updated_at"])
    audit.record("prescription.dispensed", actor=user, target=rx, branch_id=rx.branch_id, complete=complete, reference=rx.reference_number)
    _push(rx)
    return d


from django.db.models import F as models_F  # noqa: E402


@transaction.atomic
def refill(pk, *, user) -> Prescription:
    rx = _lock(pk)
    _must_be(rx, {S.DISPENSED}, "refilled")
    _not_expired(rx)
    if rx.refills_used >= rx.refills_allowed:
        raise BusinessRuleViolation("No refills remaining on this prescription.")
    rx.refills_used += 1
    rx.status = S.APPROVED
    rx.save(update_fields=["refills_used", "status", "updated_at"])
    rx.items.update(quantity_dispensed=0)  # dispensing history is preserved in Dispensing records
    audit.record("prescription.refilled", actor=user, target=rx, branch_id=rx.branch_id, refills_used=rx.refills_used)
    return rx
