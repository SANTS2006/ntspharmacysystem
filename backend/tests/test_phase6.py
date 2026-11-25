from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.core.tenant_context import tenant_context
from apps.inventory import services as inv
from apps.inventory.models import Batch, StockMovement
from apps.medicines.models import Category, Medicine
from apps.prescriptions.models import ControlledDrugRegisterEntry, Prescription
from apps.tenants.models import Branch, Pharmacy

from .test_foundation import (api, login, platform_admin, platform_client,  # noqa: F401
                              register, settled_token, two_pharmacies)

pytestmark = pytest.mark.django_db(transaction=True)
PW = "Staff-Passw0rd-123!"
TODAY = lambda: timezone.localdate()  # noqa: E731
D = lambda n: str(TODAY() + timedelta(days=n))  # noqa: E731
PDF = b"%PDF-1.4\n%fake but valid header\n"
VERIFY = {"prescriber_verified": True, "patient_verified": True, "dosage_reviewed": True}


@pytest.fixture
def env(two_pharmacies):
    g, b = Pharmacy.objects.get(slug="greenlife"), Pharmacy.objects.get(slug="bluecross")
    y = timezone.now().year
    admin = api("greenlife", settled_token("greenlife", "a@green.test", f"GLP@{y}"))
    admin_b = api("bluecross", settled_token("bluecross", "a@blue.test", f"BCP@{y}"))
    with tenant_context(g):
        main, second = Branch.objects.get(code="MAIN"), Branch.objects.create(name="Second", code="B2")
        cat = Category.objects.get(name="Antibiotics")
        amox = Medicine.objects.create(name="Amoxicillin 500mg", active_ingredient="amoxicillin", category=cat, classification="prescription", registration_number="R1", purchase_price=1, selling_price=2)
        ibu = Medicine.objects.create(name="Ibuprofen 400mg", active_ingredient="ibuprofen", category=cat, purchase_price=1, selling_price=2, contraindications="Avoid in pregnancy and peptic ulcer.")
        warf = Medicine.objects.create(name="Warfarin 5mg", active_ingredient="warfarin", category=cat, classification="prescription", registration_number="R2", purchase_price=1, selling_price=2)
        morph = Medicine.objects.create(name="Morphine 10mg", active_ingredient="morphine", category=cat, classification="controlled", registration_number="R3", purchase_price=1, selling_price=2)
    people = {}
    for key, role, branch in [("pharm", "pharmacist", main), ("tech", "pharmacy_technician", main), ("cash", "cashier", main), ("pharm2", "pharmacist", second)]:
        User.objects.create_user(f"{key}@green.test", PW, tenant=g, full_name=key, role=g.roles.get(code=role), branch=branch)
        people[key] = api("greenlife", login("greenlife", f"{key}@green.test", PW).data["tokens"]["access"])
    return dict(g=g, b=b, admin=admin, admin_b=admin_b, main=main, second=second, amox=amox, ibu=ibu, warf=warf, morph=morph, **people)


def stock(e, med, qty=100, batch="B1", days=200, branch=None):
    with tenant_context(e["g"]):
        return inv.receive_stock(medicine=med, branch=branch or e["main"], batch_number=batch, quantity=qty, purchase_cost="1", expiry_date=TODAY() + timedelta(days=days), user=User.objects.get(email="pharm@green.test"))


def mk_patient(c, **kw):
    r = c.post("/api/v1/patients/", {"full_name": "Jane Doe", "phone": "077", **kw}, format="json")
    assert r.status_code == 201, r.data
    return r.data["id"]


def mk_rx(c, e, patient, meds=None, qty=10, **kw):
    meds = meds or [e["amox"]]
    body = {"patient": patient, "branch": e["main"].pk, "prescriber_name": "Dr Kamara", "prescriber_registration": "MDC-1", "prescription_date": D(-1),
            "items": [{"medicine": m.pk, "dosage": "500mg", "frequency": "3x daily", "quantity_prescribed": qty} for m in meds], **kw}
    r = c.post("/api/v1/prescriptions/", body, format="json")
    assert r.status_code == 201, r.data
    return r.data


def reviewed(e, rx):
    r = e["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/start-review/")
    assert r.status_code == 200, r.data
    return r.data


def approved(e, rx):
    reviewed(e, rx)
    r = e["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/approve/", {"verification": VERIFY}, format="json")
    assert r.status_code == 200, r.data
    return r.data


def dispense(c, rx, lines, status=201):
    r = c.post(f"/api/v1/dispensing/prescriptions/{rx['id']}/", {"lines": lines}, format="json")
    assert r.status_code == status, r.data
    return r


# ---------------- registration ----------------
def test_registration_permissions_and_defaults(env):
    assert env["cash"].post("/api/v1/patients/", {"full_name": "X"}, format="json").status_code == 403
    assert env["cash"].get("/api/v1/prescriptions/").status_code == 403
    pid = mk_patient(env["tech"], allergies=["Penicillin", " "][:1])
    rx = mk_rx(env["tech"], env, pid)
    assert rx["reference_number"].startswith("RX-") and rx["status"] == "received"
    assert str(rx["expiry_date"]) == str(TODAY() - timedelta(days=1) + timedelta(days=30))
    bad = env["tech"].post("/api/v1/prescriptions/", {"patient": pid, "branch": env["main"].pk, "prescriber_name": "Dr", "prescription_date": D(3),
                                                       "items": [{"medicine": env["amox"].pk, "dosage": "1", "frequency": "1", "quantity_prescribed": 1}]}, format="json")
    assert bad.status_code == 400  # future-dated
    assert env["tech"].post("/api/v1/prescriptions/", {"patient": pid, "branch": env["main"].pk, "prescriber_name": "Dr", "prescription_date": D(-1), "items": []}, format="json").status_code == 400
    assert env["tech"].post("/api/v1/patients/", {"full_name": "A", "allergies": "peanuts"}, format="json").status_code == 400


def test_document_upload_validation_and_protected_download(env):
    rx = mk_rx(env["tech"], env, mk_patient(env["tech"]))
    up = lambda f: env["tech"].post(f"/api/v1/prescriptions/{rx['id']}/document/", {"document": f}, format="multipart")  # noqa: E731
    assert up(SimpleUploadedFile("rx.pdf", b"just text pretending", "application/pdf")).status_code == 400  # magic bytes
    assert up(SimpleUploadedFile("rx.exe", PDF, "application/octet-stream")).status_code == 400
    assert up(SimpleUploadedFile("rx.pdf", PDF + b"0" * (5 * 1024 * 1024), "application/pdf")).status_code == 400  # too big
    assert up(SimpleUploadedFile("rx.pdf", PDF, "application/pdf")).status_code == 201
    r = env["pharm"].get(f"/api/v1/prescriptions/{rx['id']}/document/")
    assert r.status_code == 200 and r["X-Content-Type-Options"] == "nosniff" and b"".join(r.streaming_content).startswith(b"%PDF")
    assert env["cash"].get(f"/api/v1/prescriptions/{rx['id']}/document/").status_code == 403
    assert env["admin_b"].get(f"/api/v1/prescriptions/{rx['id']}/document/").status_code == 404
    assert "prescription.document_viewed" in set(AuditLog.objects.values_list("action", flat=True))
    # an uploaded image never authorizes anything
    assert env["pharm"].get(f"/api/v1/prescriptions/{rx['id']}/").data["status"] == "received"
    stock(env, env["amox"])
    dispense(env["pharm"], rx, [{"item": 1, "quantity": 1}], status=409)


# ---------------- workflow and authorization ----------------
def test_pharmacist_review_and_approval_required(env):
    rx = mk_rx(env["tech"], env, mk_patient(env["tech"]))
    assert env["tech"].post(f"/api/v1/prescriptions/{rx['id']}/start-review/").status_code == 403
    assert env["cash"].post(f"/api/v1/prescriptions/{rx['id']}/approve/", {"verification": VERIFY}, format="json").status_code == 403
    assert env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/approve/", {"verification": VERIFY}, format="json").status_code == 409  # not reviewed yet
    reviewed(env, rx)
    assert env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/approve/", {"verification": {"prescriber_verified": True}}, format="json").status_code == 400
    assert env["tech"].post(f"/api/v1/prescriptions/{rx['id']}/approve/", {"verification": VERIFY}, format="json").status_code == 403
    out = env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/approve/", {"verification": VERIFY}, format="json")
    assert out.status_code == 200 and out.data["status"] == "approved"
    assert env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/approve/", {"verification": VERIFY}, format="json").status_code == 409
    stock(env, env["amox"])
    assert env["tech"].post(f"/api/v1/dispensing/prescriptions/{rx['id']}/", {"lines": [{"item": rx["items"][0]["id"], "quantity": 1}]}, format="json").status_code == 403
    assert env["cash"].post(f"/api/v1/dispensing/prescriptions/{rx['id']}/", {"lines": []}, format="json").status_code == 403


def test_reject_and_cancel_rules(env):
    pid = mk_patient(env["tech"])
    rx = mk_rx(env["tech"], env, pid)
    assert env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/reject/", {}, format="json").status_code == 400
    r = env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/reject/", {"reason": "Illegible"}, format="json")
    assert r.data["status"] == "rejected"
    assert env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/start-review/").status_code == 409
    rx2 = mk_rx(env["tech"], env, pid)
    assert env["pharm"].post(f"/api/v1/prescriptions/{rx2['id']}/cancel/", {"reason": "Patient left"}, format="json").data["status"] == "cancelled"


# ---------------- safety ----------------
def test_allergy_alert_blocks_until_pharmacist_decides(env):
    rx = mk_rx(env["tech"], env, mk_patient(env["tech"], allergies=["Amoxicillin"]))
    d = reviewed(env, rx)
    alert = [a for a in d["safety_alerts"] if a["type"] == "allergy"][0]
    assert alert["severity"] == "critical" and alert["source"] == "system" and alert["decision"] == ""
    blocked = env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/approve/", {"verification": VERIFY}, format="json")
    assert blocked.status_code == 409
    url = f"/api/v1/prescriptions/{rx['id']}/alerts/{alert['id']}/acknowledge/"
    assert env["pharm"].post(url, {}, format="json").status_code == 400  # decision note mandatory
    assert env["tech"].post(url, {"note": "ok"}, format="json").status_code == 403
    ack = env["pharm"].post(url, {"note": "Prescriber confirmed tolerance; counselled patient."}, format="json")
    a2 = [a for a in ack.data["safety_alerts"] if a["id"] == alert["id"]][0]
    assert a2["decision"] == "acknowledged" and "tolerance" in a2["decision_note"] and "tolerance" not in a2["message"]
    assert env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/approve/", {"verification": VERIFY}, format="json").status_code == 200
    iv = env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/interventions/", {"type": "Prescriber contact", "note": "Called Dr Kamara"}, format="json")
    assert iv.status_code == 201 and iv.data["interventions"][0]["pharmacist"] == "pharm@green.test"
    assert env["tech"].post(f"/api/v1/prescriptions/{rx['id']}/interventions/", {"type": "x", "note": "y"}, format="json").status_code == 403


def test_interactions_come_only_from_the_pharmacys_own_table(env):
    pid = mk_patient(env["tech"])
    rx = mk_rx(env["tech"], env, pid, meds=[env["warf"], env["ibu"]])
    assert [a for a in reviewed(env, rx)["safety_alerts"] if a["type"] == "interaction"] == []  # nothing invented
    assert env["tech"].post("/api/v1/interaction-rules/", {"ingredient_a": "warfarin", "ingredient_b": "ibuprofen", "description": "x"}, format="json").status_code == 403
    r = env["admin"].post("/api/v1/interaction-rules/", {"ingredient_a": "Warfarin", "ingredient_b": "Ibuprofen", "severity": "warning", "description": "Bleeding risk (entered by pharmacy)", "source": "Pharmacy reference 2026"}, format="json")
    assert r.status_code == 201
    assert env["admin"].post("/api/v1/interaction-rules/", {"ingredient_a": "x", "ingredient_b": "X", "description": "same"}, format="json").status_code == 400
    out = env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/recheck-safety/")
    al = [a for a in out.data["safety_alerts"] if a["type"] == "interaction"]
    assert len(al) == 1 and "Bleeding risk" in al[0]["message"] and "Pharmacy reference 2026" in al[0]["message"]
    assert env["admin_b"].get("/api/v1/interaction-rules/").data["count"] == 0  # per-pharmacy data


def test_duplicate_therapy_contraindication_and_pregnancy_flags(env):
    pid = mk_patient(env["tech"], is_pregnant=True)
    first = approved_after_stock(env, pid)
    rx = mk_rx(env["tech"], env, pid, meds=[env["amox"], env["ibu"]])
    types = {a["type"] for a in reviewed(env, rx)["safety_alerts"]}
    assert {"duplicate_therapy", "contraindication", "pregnancy"} <= types
    assert first["status"] == "approved"


def approved_after_stock(env, pid):
    rx = mk_rx(env["tech"], env, pid)
    return approved(env, rx)


def test_recheck_clears_stale_alerts_but_keeps_decisions(env):
    pid = mk_patient(env["tech"], allergies=["amoxicillin"])
    rx = mk_rx(env["tech"], env, pid)
    assert any(a["type"] == "allergy" for a in reviewed(env, rx)["safety_alerts"])
    env["tech"].patch(f"/api/v1/patients/{pid}/", {"allergies": []}, format="json")
    out = env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/recheck-safety/")
    assert not any(a["type"] == "allergy" for a in out.data["safety_alerts"])


# ---------------- dispensing ----------------
def test_partial_then_complete_dispensing_with_fefo_ledger(env):
    stock(env, env["amox"], 20, "LATE", 300)
    stock(env, env["amox"], 5, "SOON", 40)
    rx = approved(env, mk_rx(env["tech"], env, mk_patient(env["tech"]), qty=12))
    item = rx["items"][0]["id"]
    assert rx["availability"][0]["sufficient"] is True
    dispense(env["pharm"], rx, [{"item": item, "quantity": 13}], status=400)  # more than prescribed
    r = dispense(env["pharm"], rx, [{"item": item, "quantity": 7}])
    assert r.data["status"] == "partially_dispensed" and r.data["items"][0]["quantity_dispensed"] == 7
    assert [(x["batch"], x["quantity"]) for x in r.data["dispensings"][0]["items"]] == [("SOON", 5), ("LATE", 2)]
    r = dispense(env["pharm"], rx, [{"item": item, "quantity": 5}])
    assert r.data["status"] == "dispensed"
    dispense(env["pharm"], rx, [{"item": item, "quantity": 1}], status=409)
    with tenant_context(env["g"]):
        assert StockMovement.objects.filter(movement_type="dispense", reference_id=rx["reference_number"]).count() == 3
        assert Batch.objects.get(batch_number="SOON").quantity_available == 0
    assert {"prescription.approved", "prescription.dispensed"} <= set(AuditLog.objects.values_list("action", flat=True))


def test_expired_stock_and_expired_prescription_cannot_be_dispensed(env):
    with tenant_context(env["g"]):  # only stock on hand is expired
        Batch.objects.create(medicine=env["amox"], branch=env["main"], batch_number="OLD", purchase_date=TODAY() - timedelta(days=400),
                             expiry_date=TODAY() - timedelta(days=2), quantity_received=50, quantity_available=50, purchase_cost=1)
    rx = approved(env, mk_rx(env["tech"], env, mk_patient(env["tech"])))
    item = rx["items"][0]["id"]
    assert dispense(env["pharm"], rx, [{"item": item, "quantity": 1}], status=409).data["error"]["code"] == "insufficient_stock"
    stock(env, env["amox"], 10, "GOOD", 100)
    Prescription.all_objects.filter(pk=rx["id"]).update(expiry_date=TODAY() - timedelta(days=1))
    assert env["pharm"].get(f"/api/v1/prescriptions/{rx['id']}/").data["status"] == "expired"
    dispense(env["pharm"], rx, [{"item": item, "quantity": 1}], status=409)
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="OLD").quantity_available == 50 and Batch.objects.get(batch_number="GOOD").quantity_available == 10


def test_dispensing_is_all_or_nothing(env):
    stock(env, env["amox"], 10)
    rx = approved(env, mk_rx(env["tech"], env, mk_patient(env["tech"]), meds=[env["amox"], env["warf"]], qty=5))  # no warfarin stock
    lines = [{"item": i["id"], "quantity": 5} for i in rx["items"]]
    dispense(env["pharm"], rx, lines, status=409)
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="B1").quantity_available == 10
    assert env["pharm"].get(f"/api/v1/prescriptions/{rx['id']}/").data["status"] == "approved"


def test_controlled_medicine_register(env):
    stock(env, env["morph"], 30)
    rx = approved(env, mk_rx(env["tech"], env, mk_patient(env["tech"]), meds=[env["morph"]], qty=4))
    dispense(env["pharm"], rx, [{"item": rx["items"][0]["id"], "quantity": 4}])
    reg = env["pharm"].get("/api/v1/controlled-register/").data["results"]
    assert len(reg) == 1 and reg[0]["quantity"] == 4 and reg[0]["balance_after"] == 26 and reg[0]["prescriber_name"] == "Dr Kamara"
    assert env["tech"].get("/api/v1/controlled-register/").status_code == 403
    with tenant_context(env["g"]):
        e = ControlledDrugRegisterEntry.objects.get()
        e.quantity = 1
        with pytest.raises(PermissionError):
            e.save()
        with pytest.raises(PermissionError):
            e.delete()


def test_refills(env):
    stock(env, env["amox"], 100)
    pid = mk_patient(env["tech"])
    none = approved(env, mk_rx(env["tech"], env, pid, qty=5))
    dispense(env["pharm"], none, [{"item": none["items"][0]["id"], "quantity": 5}])
    assert env["pharm"].post(f"/api/v1/prescriptions/{none['id']}/refill/").status_code == 409  # no refills allowed
    rx = approved(env, mk_rx(env["tech"], env, pid, qty=5, refills_allowed=1))
    item = rx["items"][0]["id"]
    assert env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/refill/").status_code == 409  # not fully dispensed yet
    dispense(env["pharm"], rx, [{"item": item, "quantity": 5}])
    assert env["tech"].post(f"/api/v1/prescriptions/{rx['id']}/refill/").status_code == 403
    r = env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/refill/")
    assert r.data["status"] == "approved" and r.data["refills_used"] == 1 and r.data["items"][0]["quantity_dispensed"] == 0
    dispense(env["pharm"], rx, [{"item": item, "quantity": 5}])
    assert env["pharm"].post(f"/api/v1/prescriptions/{rx['id']}/refill/").status_code == 409  # exhausted
    assert len(env["pharm"].get(f"/api/v1/prescriptions/{rx['id']}/").data["dispensings"]) == 2  # history preserved


# ---------------- isolation ----------------
def test_branch_and_tenant_isolation(env):
    pid = mk_patient(env["tech"])
    rx = mk_rx(env["tech"], env, pid)
    assert env["pharm2"].get("/api/v1/prescriptions/").data["count"] == 0
    assert env["pharm2"].get(f"/api/v1/prescriptions/{rx['id']}/").status_code == 404
    assert env["pharm2"].post(f"/api/v1/prescriptions/{rx['id']}/start-review/").status_code == 404
    assert env["pharm2"].get(f"/api/v1/patients/{pid}/").status_code == 404
    assert env["pharm2"].post("/api/v1/prescriptions/", {"patient": pid, "branch": env["main"].pk, "prescriber_name": "D", "prescription_date": D(-1),
                                                          "items": [{"medicine": env["amox"].pk, "dosage": "1", "frequency": "1", "quantity_prescribed": 1}]}, format="json").status_code in (400, 403)
    assert env["admin"].get("/api/v1/prescriptions/").data["count"] == 1
    assert env["admin_b"].get("/api/v1/prescriptions/").data["count"] == 0
    assert env["admin_b"].get(f"/api/v1/prescriptions/{rx['id']}/").status_code == 404
    assert env["admin_b"].get("/api/v1/patients/").data["count"] == 0


def test_sync_role_permissions_command(env):
    role = Role.objects.get(tenant=env["g"], code="pharmacist")
    role.permissions = [p for p in role.permissions if p != "prescription.register"]
    role.save()
    call_command("sync_role_permissions")
    role.refresh_from_db()
    assert "prescription.register" in role.permissions
