"""Patient-safety checks.

IMPORTANT: these are rule-based checks over data the pharmacy itself entered (patient allergies, the pharmacy's own interaction
table, medicine contraindication text). No clinical content is invented or bundled, and nothing here is a clinical decision:
alerts are SYSTEM output; a pharmacist records the decision separately. Age/dosage/pregnancy-dose rules require a licensed
drug database and are NOT implemented."""
from itertools import combinations

from .models import DrugInteraction, Prescription, SafetyAlert

ACTIVE = (Prescription.Status.APPROVED, Prescription.Status.PARTIALLY_DISPENSED)


def _ingredient(m) -> str:
    return (m.active_ingredient or m.generic_name or "").strip().lower()


def _terms(m) -> set[str]:
    return {t.strip().lower() for t in (m.active_ingredient, m.generic_name, m.name, m.brand_name) if t and len(t.strip()) >= 3}


def compute(rx: Prescription) -> dict:
    items = list(rx.items.select_related("medicine"))
    desired: dict[str, tuple] = {}  # key -> (type, severity, item, message)

    for it in items:
        m = it.medicine
        for allergy in (a.strip().lower() for a in rx.patient.allergies if isinstance(a, str) and len(a.strip()) >= 3):
            if any(allergy in t or t in allergy for t in _terms(m)):
                desired[f"allergy:{it.pk}:{allergy}"] = ("allergy", "critical", it, f"Patient has a recorded allergy to '{allergy}' which may match {m.name}.")
        if m.contraindications.strip():
            desired[f"contra:{it.pk}"] = ("contraindication", "info", it, f"Contraindications recorded by this pharmacy for {m.name}: {m.contraindications.strip()[:400]}")
            if rx.patient.is_pregnant and "pregnan" in m.contraindications.lower():
                desired[f"pregnancy:{it.pk}"] = ("pregnancy", "warning", it, f"Patient is recorded as pregnant and the recorded contraindications for {m.name} mention pregnancy. Review.")

    # duplicate therapy: inside this prescription and against the patient's other active prescriptions
    others = list(PrescriptionItemQS(rx))
    by_ing: dict[str, list] = {}
    for it in items:
        if _ingredient(it.medicine):
            by_ing.setdefault(_ingredient(it.medicine), []).append(it)
    for ing, group in by_ing.items():
        if len(group) > 1:
            desired[f"dup:{ing}"] = ("duplicate_therapy", "warning", group[0], f"{len(group)} items on this prescription contain '{ing}'.")
        for o in others:
            if _ingredient(o.medicine) == ing:
                desired[f"dup-active:{ing}:{o.prescription_id}"] = ("duplicate_therapy", "warning", group[0], f"Patient already has active prescription {o.prescription.reference_number} containing '{ing}'.")

    # interactions from the pharmacy's own table
    rules = {}
    for r in DrugInteraction.objects.all():
        rules[(r.ingredient_a.strip().lower(), r.ingredient_b.strip().lower())] = r
        rules[(r.ingredient_b.strip().lower(), r.ingredient_a.strip().lower())] = r
    if rules:
        pool = [(it, _ingredient(it.medicine)) for it in items] + [(o, _ingredient(o.medicine)) for o in others]
        for (i1, a), (i2, b) in combinations(pool, 2):
            rule = rules.get((a, b)) if a and b and a != b else None
            if rule is None:
                continue
            target = i1 if i1.prescription_id == rx.pk else i2
            src = f" (source: {rule.source})" if rule.source else ""
            desired[f"interaction:{min(a, b)}:{max(a, b)}"] = ("interaction", rule.severity, target, f"Interaction {a} + {b}: {rule.description}{src}")
    return desired


def PrescriptionItemQS(rx):
    from .models import PrescriptionItem
    return (PrescriptionItem.objects.filter(prescription__patient=rx.patient, prescription__status__in=ACTIVE)
            .exclude(prescription=rx).select_related("medicine", "prescription"))


def run_checks(rx: Prescription) -> list[SafetyAlert]:
    """Make stored alerts match current data. Acknowledged alerts (with a pharmacist's decision) are kept as history."""
    desired = compute(rx)
    existing = {a.key: a for a in rx.alerts.all()}
    for key, (typ, sev, item, msg) in desired.items():
        a = existing.get(key)
        if a is None:
            SafetyAlert.objects.create(prescription=rx, item=item if item.prescription_id == rx.pk else None, alert_type=typ, severity=sev, key=key, message=msg)
        elif not a.decision and (a.message != msg or a.severity != sev):
            a.message, a.severity = msg, sev
            a.save(update_fields=["message", "severity", "updated_at"])
    for key, a in existing.items():
        if key not in desired and not a.decision:
            a.delete()  # stale system alert nobody has acted on
    return list(rx.alerts.all())


def open_critical(rx: Prescription):
    return rx.alerts.filter(severity=SafetyAlert.Severity.CRITICAL, decision="")
