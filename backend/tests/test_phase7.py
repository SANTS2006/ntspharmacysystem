from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.tenant_context import tenant_context
from apps.inventory import services as inv
from apps.inventory.models import Batch, StockMovement
from apps.medicines.models import Category, Medicine
from apps.sales.models import Payment, Receipt, Sale
from apps.tenants.models import Branch, Pharmacy

from .test_foundation import (api, login, platform_admin, platform_client,  # noqa: F401
                              register, settled_token, two_pharmacies)

pytestmark = pytest.mark.django_db(transaction=True)
PW = "Staff-Passw0rd-123!"
TODAY = lambda: timezone.localdate()  # noqa: E731
D = lambda n: str(TODAY() + timedelta(days=n))  # noqa: E731
Dec = Decimal
VERIFY = {"prescriber_verified": True, "patient_verified": True, "dosage_reviewed": True}
_k = iter(range(10_000))


def key():
    return f"key-{next(_k)}"


@pytest.fixture
def env(two_pharmacies):
    g, b = Pharmacy.objects.get(slug="greenlife"), Pharmacy.objects.get(slug="bluecross")
    y = timezone.now().year
    admin = api("greenlife", settled_token("greenlife", "a@green.test", f"GLP@{y}"))
    admin_b = api("bluecross", settled_token("bluecross", "a@blue.test", f"BCP@{y}"))
    with tenant_context(g):
        main, second = Branch.objects.get(code="MAIN"), Branch.objects.create(name="Second", code="B2")
        cat, _ = Category.objects.get_or_create(name="Antibiotics")
        para = Medicine.objects.create(name="Paracetamol", category=cat, purchase_price=4, selling_price=10, tax_rate=10)
        vit = Medicine.objects.create(name="Vitamin C", category=cat, purchase_price=2, selling_price=5)
        amox = Medicine.objects.create(name="Amoxicillin", active_ingredient="amoxicillin", category=cat, classification="prescription", registration_number="R1", purchase_price=3, selling_price=8)
    people = {}
    for k, role, br in [("c1", "cashier", main), ("c2", "cashier", main), ("c3", "cashier", second), ("mgr", "branch_manager", main), ("ph", "pharmacist", main), ("tech", "pharmacy_technician", main)]:
        User.objects.create_user(f"{k}@green.test", PW, tenant=g, full_name=k.upper(), role=g.roles.get(code=role), branch=br)
        people[k] = api("greenlife", login("greenlife", f"{k}@green.test", PW).data["tokens"]["access"])
    return dict(g=g, b=b, admin=admin, admin_b=admin_b, main=main, second=second, para=para, vit=vit, amox=amox, **people)


def stock(e, med, qty=100, batch="B1", days=200, branch=None):
    with tenant_context(e["g"]):
        return inv.receive_stock(medicine=med, branch=branch or e["main"], batch_number=batch, quantity=qty, purchase_cost="1", expiry_date=TODAY() + timedelta(days=days), user=User.objects.get(email="ph@green.test"))


def open_shift(c, cash="100.00", **kw):
    r = c.post("/api/v1/shifts/open/", {"opening_cash": cash, **kw}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def sell(c, items, payments, status=201, k=None, **kw):
    r = c.post("/api/v1/sales/", {"items": items, "payments": payments, **kw}, format="json", HTTP_IDEMPOTENCY_KEY=k or key())
    assert r.status_code == status, r.data
    return r


def cash(n):
    return {"method": "cash", "amount": str(n)}


# ---------------- shifts ----------------
def test_cannot_sell_without_open_shift_and_one_shift_per_cashier(env):
    stock(env, env["para"])
    r = sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 1}], [cash(20)], status=409)
    assert "shift" in r.data["error"]["message"].lower()
    open_shift(env["c1"])
    assert env["c1"].post("/api/v1/shifts/open/", {"opening_cash": 5}, format="json").status_code == 409
    assert env["c3"].post("/api/v1/shifts/open/", {"opening_cash": 5, "branch": env["main"].pk}, format="json").status_code == 403  # other branch
    assert env["tech"].post("/api/v1/shifts/open/", {"opening_cash": 5}, format="json").status_code == 403  # no pos.sell


def test_shift_reconciliation_and_discrepancy(env):
    stock(env, env["para"])
    sh = open_shift(env["c1"], "100.00")
    sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 3}], [cash(40)])  # total 33.00
    sell(env["c1"], [{"medicine": env["vit"].pk, "quantity": 1}], [{"method": "mobile_money", "amount": "5.00", "reference": "MM-1"}], status=409) if False else None
    cur = env["c1"].get("/api/v1/shifts/current/").data
    assert Dec(str(cur["totals"]["expected_cash"])) == Dec("133.00")
    closed = env["c1"].post(f"/api/v1/shifts/{sh['id']}/close/", {"counted_cash": "130.00", "notes": "short 3"}, format="json")
    assert closed.status_code == 200 and Dec(str(closed.data["expected_cash"])) == Dec("133.00") and Dec(str(closed.data["discrepancy"])) == Dec("-3.00")
    assert env["c1"].post(f"/api/v1/shifts/{sh['id']}/close/", {"counted_cash": "1"}, format="json").status_code == 409
    sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 1}], [cash(20)], status=409)  # closed shift
    assert {"shift.opened", "shift.closed"} <= set(AuditLog.objects.values_list("action", flat=True))


def test_cash_movements_need_manager_authorization(env):
    sh = open_shift(env["c1"], "200.00")
    dep = env["c1"].post(f"/api/v1/shifts/{sh['id']}/cash-movements/", {"kind": "deposit", "amount": "50", "reason": "float top-up"}, format="json")
    assert dep.data["status"] == "approved"
    w = env["c1"].post(f"/api/v1/shifts/{sh['id']}/cash-movements/", {"kind": "withdrawal", "amount": "100", "reason": "bank drop"}, format="json")
    assert w.status_code == 201 and w.data["status"] == "pending"
    assert env["c1"].post(f"/api/v1/shifts/{sh['id']}/close/", {"counted_cash": "250"}, format="json").status_code == 409  # pending request blocks closing
    assert env["c1"].post(f"/api/v1/cash-movements/{w.data['id']}/approve/").status_code == 403  # cashier cannot self-authorize
    assert env["mgr"].post(f"/api/v1/cash-movements/{w.data['id']}/approve/").status_code == 200
    assert Dec(str(env["c1"].get("/api/v1/shifts/current/").data["totals"]["expected_cash"])) == Dec("150.00")
    assert env["c1"].post(f"/api/v1/shifts/{sh['id']}/cash-movements/", {"kind": "withdrawal", "amount": "999", "reason": "x"}, format="json").status_code == 400
    assert env["c1"].post(f"/api/v1/shifts/{sh['id']}/close/", {"counted_cash": "150"}, format="json").data["discrepancy"] == Dec("0.00")


# ---------------- sale totals, payments, stock ----------------
def test_server_computes_totals_tax_discounts_and_change(env):
    stock(env, env["para"])
    open_shift(env["c1"])
    r = sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 3, "unit_price": "0.01", "line_total": "1"}], [cash(50)])  # client prices are ignored
    s = r.data
    assert (Dec(str(s["subtotal"])), Dec(str(s["tax_total"])), Dec(str(s["total"])), Dec(str(s["change_due"]))) == (Dec("30.00"), Dec("3.00"), Dec("33.00"), Dec("17.00"))
    assert [(p["method"], Dec(str(p["amount"]))) for p in s["payments"]] == [("cash", Dec("33.00"))]  # cash recorded net of change
    assert s["reference_number"].startswith("SL-") and s["receipt_number"].startswith("RC-")
    disc = sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 2, "discount_pct": "5"}], [cash(30)])
    assert Dec(str(disc.data["discount_total"])) == Dec("1.00") and Dec(str(disc.data["total"])) == Dec("20.90")  # 19.00 + 1.90 tax
    sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 2, "discount_pct": "10"}], [cash(30)], status=403)  # above cashier limit
    sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 1, "discount_pct": "101"}], [cash(30)], status=400)


def test_payment_validation_and_duplicate_references(env):
    stock(env, env["para"])
    open_shift(env["c1"])
    item = [{"medicine": env["para"].pk, "quantity": 1}]  # total 11.00
    sell(env["c1"], item, [cash(5)], status=400)  # underpaid
    sell(env["c1"], item, [{"method": "mobile_money", "amount": "11.00"}], status=400)  # reference required
    sell(env["c1"], item, [{"method": "mobile_money", "amount": "20.00", "reference": "R"}], status=400)  # non-cash overpay
    sell(env["c1"], item, [{"method": "voucher", "amount": "11"}], status=400)
    sell(env["c1"], item, [{"method": "cash", "amount": "0"}], status=400)
    sell(env["c1"], item, [{"method": "mobile_money", "amount": "6.00", "reference": "MM-7"}, cash(5)])  # split payment
    sell(env["c1"], item, [{"method": "mobile_money", "amount": "11.00", "reference": "MM-7"}], status=400)  # same reference reused
    assert Payment.all_objects.filter(reference="MM-7").count() == 1


def test_stock_deducted_fefo_and_failures_roll_back(env):
    stock(env, env["para"], 5, "LATE", 300)
    stock(env, env["para"], 5, "SOON", 40)
    open_shift(env["c1"])
    r = sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 7}], [cash(100)])
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="SOON").quantity_available == 0 and Batch.objects.get(batch_number="LATE").quantity_available == 3
        assert StockMovement.objects.filter(movement_type="sale", reference_id=r.data["reference_number"]).count() == 2
    before = Sale.all_objects.count()
    sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 4}], [cash(100)], status=409, k="retry-ok")  # only 3 left
    assert Sale.all_objects.count() == before and Payment.all_objects.count() == 1
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="LATE").quantity_available == 3
    sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 3}], [cash(100)], k="retry-ok")  # the failed key is reusable


def test_expired_batches_are_never_sold(env):
    with tenant_context(env["g"]):
        Batch.objects.create(medicine=env["vit"], branch=env["main"], batch_number="OLD", purchase_date=TODAY() - timedelta(days=300), expiry_date=TODAY() - timedelta(days=1), quantity_received=50, quantity_available=50, purchase_cost=1)
    open_shift(env["c1"])
    r = sell(env["c1"], [{"medicine": env["vit"].pk, "quantity": 1}], [cash(10)], status=409)
    assert r.data["error"]["code"] == "insufficient_stock"


def test_idempotency_prevents_duplicate_sales(env):
    stock(env, env["para"])
    open_shift(env["c1"])
    items = [{"medicine": env["para"].pk, "quantity": 2}]
    first = sell(env["c1"], items, [cash(30)], k="dup-1")
    again = sell(env["c1"], items, [cash(30)], k="dup-1", status=200)
    assert again.data["id"] == first.data["id"]
    assert Sale.all_objects.count() == 1 and Payment.all_objects.count() == 1
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="B1").quantity_available == 98
    open_shift(env["c2"])
    sell(env["c2"], items, [cash(30)], k="dup-1", status=409)  # another cashier cannot reuse the key
    r = env["c1"].post("/api/v1/sales/", {"items": items, "payments": [cash(30)]}, format="json")
    assert r.status_code == 400  # key is mandatory


# ---------------- prescription items ----------------
def test_prescription_medicines_cannot_be_rung_up_directly_but_can_be_billed_after_dispensing(env):
    stock(env, env["amox"], 50)
    open_shift(env["c1"])
    sell(env["c1"], [{"medicine": env["amox"].pk, "quantity": 1}], [cash(50)], status=400)  # cashier cannot sell Rx medicine
    pid = env["tech"].post("/api/v1/patients/", {"full_name": "Jane Doe"}, format="json").data["id"]
    rx = env["tech"].post("/api/v1/prescriptions/", {"patient": pid, "branch": env["main"].pk, "prescriber_name": "Dr K", "prescription_date": D(-1),
                                                     "items": [{"medicine": env["amox"].pk, "dosage": "1", "frequency": "3x", "quantity_prescribed": 6}]}, format="json").data
    env["ph"].post(f"/api/v1/prescriptions/{rx['id']}/start-review/")
    assert env["ph"].post(f"/api/v1/prescriptions/{rx['id']}/approve/", {"verification": VERIFY}, format="json").status_code == 200
    d = env["ph"].post(f"/api/v1/dispensing/prescriptions/{rx['id']}/", {"lines": [{"item": rx["items"][0]["id"], "quantity": 6}]}, format="json")
    assert d.status_code == 201
    pend = env["c1"].get("/api/v1/pos/pending-dispensings/").data
    assert len(pend) == 1 and pend[0]["patient"] == "Jane Doe" and Dec(str(pend[0]["estimated_total"])) == Dec("48.00")
    s = sell(env["c1"], [], [cash(50)], dispensing_ids=[pend[0]["id"]])
    assert Dec(str(s.data["total"])) == Dec("48.00") and s.data["customer_name"] == "Jane Doe" and s.data["lines"][0]["from_prescription"] is True
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="B1").quantity_available == 44  # deducted once, by the pharmacist's dispensing
    sell(env["c1"], [], [cash(50)], dispensing_ids=[pend[0]["id"]], status=409)  # cannot bill the same dispensing twice
    assert env["c1"].get("/api/v1/pos/pending-dispensings/").data == []


# ---------------- receipts ----------------
def test_receipts_json_pdf_email_and_immutability(env):
    stock(env, env["para"])
    open_shift(env["c1"])
    s = sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 1}], [cash(20)], customer_name="Walk In").data
    rc = env["c1"].get(f"/api/v1/sales/{s['id']}/receipt/").data
    assert rc["pharmacy"] == "Green Life Pharmacy" and rc["customer"] == "Walk In" and rc["lines"][0]["name"] == "Paracetamol" and rc["total"] == "11.00"
    pdf = env["c1"].get(f"/api/v1/sales/{s['id']}/receipt/pdf/")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    assert env["c1"].post(f"/api/v1/sales/{s['id']}/receipt/email/", {"email": "not-an-email"}, format="json").status_code == 400
    assert env["c1"].post(f"/api/v1/sales/{s['id']}/receipt/email/", {"email": "cust@example.com"}, format="json").status_code == 202
    assert any(m.to == ["cust@example.com"] and rc["receipt_number"] in m.subject for m in mail.outbox)
    with tenant_context(env["g"]):
        r = Receipt.objects.get()
        r.data = {}
        with pytest.raises(PermissionError):
            r.save()
        with pytest.raises(PermissionError):
            r.delete()


# ---------------- privacy / isolation ----------------
def test_cashiers_see_only_their_own_sales(env):
    stock(env, env["para"])
    open_shift(env["c1"])
    open_shift(env["c2"])
    s1 = sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 1}], [cash(20)]).data
    s2 = sell(env["c2"], [{"medicine": env["para"].pk, "quantity": 2}], [cash(30)]).data
    assert {x["id"] for x in env["c1"].get("/api/v1/sales/").data["results"]} == {s1["id"]}
    assert env["c1"].get(f"/api/v1/sales/{s2['id']}/").status_code == 404
    assert env["c1"].get(f"/api/v1/sales/{s2['id']}/receipt/").status_code == 404
    assert env["c1"].get(f"/api/v1/sales/{s2['id']}/receipt/pdf/").status_code == 404
    assert {x["id"] for x in env["mgr"].get("/api/v1/sales/").data["results"]} == {s1["id"], s2["id"]}  # manager sees the branch
    assert len(env["admin"].get("/api/v1/sales/").data["results"]) == 2
    assert env["admin_b"].get("/api/v1/sales/").data["count"] == 0 and env["admin_b"].get(f"/api/v1/sales/{s1['id']}/").status_code == 404
    assert env["c1"].get("/api/v1/shifts/").data["count"] == 1  # own shifts only
    assert env["tech"].get("/api/v1/sales/").status_code == 403
    d = env["c1"].get("/api/v1/pos/dashboard/").data
    assert d["today"]["count"] == 1 and Dec(str(d["today"]["total"])) == Dec("11.00") and d["current_shift"]["cashier"] == s1["cashier"]


def test_branch_manager_cannot_see_other_branch_sales(env):
    stock(env, env["para"], 10, "S1", branch=env["second"])
    open_shift(env["c3"])
    other = sell(env["c3"], [{"medicine": env["para"].pk, "quantity": 1}], [cash(20)]).data
    assert env["mgr"].get("/api/v1/sales/").data["count"] == 0
    assert env["mgr"].get(f"/api/v1/sales/{other['id']}/").status_code == 404
    assert env["admin"].get(f"/api/v1/sales/{other['id']}/").status_code == 200


# ---------------- returns / cancellation ----------------
def test_returns_require_authority_and_refund_proportionally(env):
    stock(env, env["para"], 20)
    open_shift(env["c1"])
    s = sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 4}], [cash(60)]).data  # 44.00 total, line 11.00 each
    line = s["lines"][0]["id"]
    body = {"lines": [{"sale_line": line, "quantity": 1}], "reason": "wrong item", "refund_method": "cash", "restock": True}
    assert env["c1"].post(f"/api/v1/sales/{s['id']}/return/", body, format="json").status_code == 403  # cashier cannot refund
    assert env["mgr"].post(f"/api/v1/sales/{s['id']}/return/", body, format="json").status_code == 409  # manager needs an open shift for cash refunds
    open_shift(env["mgr"], "0.00")
    r = env["mgr"].post(f"/api/v1/sales/{s['id']}/return/", body, format="json")
    assert r.status_code == 201 and r.data["credit_note"].startswith("CN-") and Dec(str(r.data["refund_total"])) == Dec("11.00") and r.data["sale_status"] == "partially_returned"
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="B1").quantity_available == 17  # 20 - 4 + 1 restocked
    assert env["mgr"].post(f"/api/v1/sales/{s['id']}/return/", {**body, "lines": [{"sale_line": line, "quantity": 4}]}, format="json").status_code == 400  # only 3 left
    final = env["mgr"].post(f"/api/v1/sales/{s['id']}/return/", {**body, "lines": [{"sale_line": line, "quantity": 3}], "restock": False}, format="json")
    assert Dec(str(final.data["refund_total"])) == Dec("33.00") and final.data["sale_status"] == "returned"
    assert env["mgr"].post(f"/api/v1/sales/{s['id']}/return/", body, format="json").status_code == 409  # fully returned
    mshift = env["mgr"].get("/api/v1/shifts/current/").data
    assert Dec(str(mshift["totals"]["cash_refunds"])) == Dec("44.00")
    assert {"sale.returned"} <= set(AuditLog.objects.values_list("action", flat=True))
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="B1").quantity_available == 17  # second return was not restocked


def test_non_cash_refund_needs_reference_and_rounding_never_over_refunds(env):
    stock(env, env["vit"], 20)
    open_shift(env["c1"])
    s = sell(env["c1"], [{"medicine": env["vit"].pk, "quantity": 3, "discount_pct": "3.33"}], [cash(20)]).data
    total, line = Dec(str(s["total"])), s["lines"][0]["id"]
    mk = lambda q, **kw: env["mgr"].post(f"/api/v1/sales/{s['id']}/return/", {"lines": [{"sale_line": line, "quantity": q}], "reason": "x", "refund_method": "mobile_money", **kw}, format="json")  # noqa: E731
    assert mk(1).status_code == 400  # reference missing
    refunded = sum(Dec(str(mk(1, refund_reference=f"RF-{i}").data["refund_total"])) for i in range(3))
    assert refunded == total  # the last unit absorbs rounding: never refund more than was paid


def test_cancellation_restocks_and_cannot_repeat(env):
    stock(env, env["para"], 10)
    open_shift(env["c1"])
    open_shift(env["mgr"], "0.00")
    s = sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 2}], [cash(30)]).data
    assert env["c1"].post(f"/api/v1/sales/{s['id']}/cancel/", {"reason": "mistake", "refund_method": "cash"}, format="json").status_code == 403
    r = env["mgr"].post(f"/api/v1/sales/{s['id']}/cancel/", {"reason": "customer changed mind", "refund_method": "cash"}, format="json")
    assert r.status_code == 201 and r.data["sale_status"] == "cancelled"
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="B1").quantity_available == 10
        assert Sale.objects.get(pk=s["id"]).status == "cancelled" and Sale.objects.count() == 1  # record kept
    assert env["mgr"].post(f"/api/v1/sales/{s['id']}/cancel/", {"reason": "again", "refund_method": "cash"}, format="json").status_code == 409
    assert "sale.cancelled" in set(AuditLog.objects.values_list("action", flat=True))


def test_dispensed_items_are_never_restocked_and_sale_cannot_be_cancelled(env):
    stock(env, env["amox"], 20)
    open_shift(env["c1"])
    open_shift(env["mgr"], "0.00")
    pid = env["tech"].post("/api/v1/patients/", {"full_name": "P"}, format="json").data["id"]
    rx = env["tech"].post("/api/v1/prescriptions/", {"patient": pid, "branch": env["main"].pk, "prescriber_name": "Dr", "prescription_date": D(-1),
                                                     "items": [{"medicine": env["amox"].pk, "dosage": "1", "frequency": "1", "quantity_prescribed": 2}]}, format="json").data
    env["ph"].post(f"/api/v1/prescriptions/{rx['id']}/start-review/")
    env["ph"].post(f"/api/v1/prescriptions/{rx['id']}/approve/", {"verification": VERIFY}, format="json")
    env["ph"].post(f"/api/v1/dispensing/prescriptions/{rx['id']}/", {"lines": [{"item": rx["items"][0]["id"], "quantity": 2}]}, format="json")
    did = env["c1"].get("/api/v1/pos/pending-dispensings/").data[0]["id"]
    s = sell(env["c1"], [], [cash(20)], dispensing_ids=[did]).data
    assert env["mgr"].post(f"/api/v1/sales/{s['id']}/cancel/", {"reason": "x", "refund_method": "cash"}, format="json").status_code == 409
    r = env["mgr"].post(f"/api/v1/sales/{s['id']}/return/", {"lines": [{"sale_line": s["lines"][0]["id"], "quantity": 1}], "reason": "x", "refund_method": "cash", "restock": True}, format="json")
    assert r.status_code == 201
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="B1").quantity_available == 18  # stays out of stock


# ---------------- partial payments ----------------
def test_partial_payments_only_when_enabled(env):
    stock(env, env["para"])
    open_shift(env["c1"])
    item = [{"medicine": env["para"].pk, "quantity": 2}]  # 22.00
    sell(env["c1"], item, [cash(10)], status=400)
    assert env["admin"].patch("/api/v1/tenants/me/", {"settings": {"allow_partial_payments": True}}, format="json").status_code == 200
    sell(env["c1"], item, [cash(10)], status=400)  # customer name required
    s = sell(env["c1"], item, [cash(10)], customer_name="Mrs Bangura").data
    assert s["status"] == "partially_paid" and Dec(str(s["balance"])) == Dec("12.00")
    assert env["c1"].post(f"/api/v1/sales/{s['id']}/payments/", {"payments": [cash(20)]}, format="json").data["status"] == "completed"
    assert env["c1"].post(f"/api/v1/sales/{s['id']}/payments/", {"payments": [cash(1)]}, format="json").status_code == 409


# ---------------- products / isolation ----------------
def test_product_search_barcode_and_tenant_isolation(env):
    with tenant_context(env["g"]):
        Medicine.objects.filter(pk=env["para"].pk).update(barcode="6001234567")
    stock(env, env["para"], 8)
    open_shift(env["c1"])
    r = env["c1"].get("/api/v1/pos/products/?barcode=6001234567").data
    assert len(r) == 1 and r[0]["stock"] == 8 and r[0]["requires_prescription"] is False
    assert [m["name"] for m in env["c1"].get("/api/v1/pos/products/?search=amox").data] == ["Amoxicillin"]
    assert env["c1"].get("/api/v1/pos/products/").data == []
    assert env["admin_b"].get("/api/v1/pos/products/?search=para").data == []  # another pharmacy never sees this catalogue
    assert Medicine.all_objects.filter(tenant=env["b"]).count() == 0
