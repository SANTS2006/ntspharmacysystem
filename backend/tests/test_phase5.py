from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.tenant_context import tenant_context
from apps.inventory.models import Batch, StockMovement
from apps.medicines.models import Category, Medicine
from apps.procurement.models import GoodsReceipt, PurchaseOrder, Supplier
from apps.tenants.models import Branch, Pharmacy

from .test_foundation import (api, login, platform_admin, platform_client,  # noqa: F401
                              register, settled_token, two_pharmacies)

pytestmark = pytest.mark.django_db(transaction=True)
PW = "Staff-Passw0rd-123!"
D = lambda n: str(timezone.localdate() + timedelta(days=n))  # noqa: E731


@pytest.fixture
def env(two_pharmacies):
    g, b = Pharmacy.objects.get(slug="greenlife"), Pharmacy.objects.get(slug="bluecross")
    y = timezone.now().year
    admin = api("greenlife", settled_token("greenlife", "a@green.test", f"GLP@{y}"))
    admin_b = api("bluecross", settled_token("bluecross", "a@blue.test", f"BCP@{y}"))
    with tenant_context(g):
        main, second = Branch.objects.get(code="MAIN"), Branch.objects.create(name="Second", code="B2")
        cat, _ = Category.objects.get_or_create(name="Antibiotics")
        med = Medicine.objects.create(name="Amoxicillin", category=cat, purchase_price=1, selling_price=2)
        med2 = Medicine.objects.create(name="Paracetamol", category=cat, purchase_price=1, selling_price=2)
    for email, role, branch in [("po@green.test", "procurement_officer", main), ("acc@green.test", "accountant", None), ("cash@green.test", "cashier", main)]:
        User.objects.create_user(email, PW, tenant=g, full_name=email, role=g.roles.get(code=role), branch=branch)
    tok = lambda e: api("greenlife", login("greenlife", e, PW).data["tokens"]["access"])  # noqa: E731
    return dict(g=g, b=b, admin=admin, admin_b=admin_b, main=main, second=second, med=med, med2=med2,
                officer=tok("po@green.test"), acc=tok("acc@green.test"), cash=tok("cash@green.test"))


def mk_supplier(c, name="MediSupply", **kw):
    r = c.post("/api/v1/suppliers/", {"name": name, **kw}, format="json")
    assert r.status_code == 201, r.data
    return r.data["id"]


def mk_order(c, e, supplier, branch=None, qty=100, cost="2.00", items=None):
    r = c.post("/api/v1/procurement/orders/", {"branch": (branch or e["main"]).pk, "supplier": supplier,
                                               "items": items or [{"medicine": e["med"].pk, "quantity": qty, "unit_cost": cost}]}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def approved_order(e, supplier, **kw):
    po = mk_order(e["officer"], e, supplier, **kw)
    r = e["officer"].post(f"/api/v1/procurement/orders/{po['id']}/submit/")
    assert r.status_code == 200 and r.data["status"] == "approved", r.data
    return r.data


# ---------------- suppliers ----------------
def test_supplier_rules_and_sensitive_fields(env):
    sid = mk_supplier(env["admin"], payment_details="Bank 123")
    assert env["admin"].post("/api/v1/suppliers/", {"name": "medisupply"}, format="json").status_code == 400
    assert env["officer"].get(f"/api/v1/suppliers/{sid}/").data["payment_details"] == "Bank 123"
    assert "payment_details" not in env["acc"].get(f"/api/v1/suppliers/{sid}/").data  # view-only role: hidden
    assert env["cash"].get("/api/v1/suppliers/").status_code == 403
    assert env["admin_b"].get(f"/api/v1/suppliers/{sid}/").status_code == 404
    assert env["admin_b"].post("/api/v1/suppliers/", {"name": "MediSupply"}, format="json").status_code == 201  # per-tenant uniqueness


# ---------------- requisitions ----------------
def test_requisition_workflow_and_segregation(env):
    o, a = env["officer"], env["admin"]
    r = o.post("/api/v1/procurement/requisitions/", {"branch": env["main"].pk, "items": [{"medicine": env["med"].pk, "quantity": 50}], "submit": True}, format="json")
    assert r.status_code == 201 and r.data["status"] == "submitted" and r.data["number"].startswith("REQ-")
    rid = r.data["id"]
    assert o.post(f"/api/v1/procurement/requisitions/{rid}/approve/").status_code == 403  # lacks procurement.approve
    assert a.post(f"/api/v1/procurement/requisitions/{rid}/approve/").data["status"] == "approved"
    assert a.post(f"/api/v1/procurement/requisitions/{rid}/reject/").status_code == 409  # invalid transition
    mine = a.post("/api/v1/procurement/requisitions/", {"branch": env["main"].pk, "items": [{"medicine": env["med"].pk, "quantity": 5}], "submit": True}, format="json")
    assert a.post(f"/api/v1/procurement/requisitions/{mine.data['id']}/approve/").status_code == 403  # cannot approve own
    assert o.post("/api/v1/procurement/requisitions/", {"branch": env["main"].pk, "items": []}, format="json").status_code == 400
    assert o.post("/api/v1/procurement/requisitions/", {"branch": env["second"].pk, "items": [{"medicine": env["med"].pk, "quantity": 1}]}, format="json").status_code == 403


def test_requisition_converts_to_order_only_when_approved(env):
    sid = mk_supplier(env["admin"])
    o, a = env["officer"], env["admin"]
    rid = o.post("/api/v1/procurement/requisitions/", {"branch": env["main"].pk, "items": [{"medicine": env["med"].pk, "quantity": 10}], "submit": True}, format="json").data["id"]
    body = {"branch": env["main"].pk, "supplier": sid, "requisition": rid, "items": [{"medicine": env["med"].pk, "quantity": 10, "unit_cost": "1"}]}
    assert o.post("/api/v1/procurement/orders/", body, format="json").status_code == 400
    a.post(f"/api/v1/procurement/requisitions/{rid}/approve/")
    assert o.post("/api/v1/procurement/orders/", body, format="json").status_code == 201


# ---------------- purchase orders ----------------
def test_order_validation_and_numbering(env):
    sid = mk_supplier(env["admin"])
    o = env["officer"]
    base = {"branch": env["main"].pk, "supplier": sid}
    assert o.post("/api/v1/procurement/orders/", {**base, "items": []}, format="json").status_code == 400
    dup = [{"medicine": env["med"].pk, "quantity": 1, "unit_cost": "1"}] * 2
    assert o.post("/api/v1/procurement/orders/", {**base, "items": dup}, format="json").status_code == 400
    assert o.post("/api/v1/procurement/orders/", {**base, "items": [{"medicine": env["med"].pk, "quantity": 1, "unit_cost": "-1"}]}, format="json").status_code == 400
    p1, p2 = mk_order(o, env, sid), mk_order(o, env, sid)
    y = timezone.now().year
    assert (p1["number"], p2["number"]) == (f"PO-{y}-00001", f"PO-{y}-00002") and Decimal(str(p1["total"])) == Decimal("200.00")
    # another tenant starts its own sequence and cannot use this tenant's supplier
    bsid = mk_supplier(env["admin_b"], "Other")
    bbranch = Branch.all_objects.filter(tenant=env["b"]).first()
    bmed = Medicine.all_objects.filter(tenant=env["b"]).first()
    assert env["admin_b"].post("/api/v1/procurement/orders/", {"branch": bbranch.pk, "supplier": sid, "items": [{"medicine": env["med"].pk, "quantity": 1, "unit_cost": "1"}]}, format="json").status_code == 400


def test_approval_threshold_and_segregation_of_duties(env):
    sid = mk_supplier(env["admin"])
    big = mk_order(env["officer"], env, sid, qty=1000, cost="5.00")  # 5000 > default threshold 1000
    sub = env["officer"].post(f"/api/v1/procurement/orders/{big['id']}/submit/")
    assert sub.data["status"] == "pending_approval"
    assert env["officer"].post(f"/api/v1/procurement/orders/{big['id']}/approve/").status_code == 403
    assert env["admin"].post(f"/api/v1/procurement/orders/{big['id']}/approve/").data["status"] == "approved"
    mine = mk_order(env["admin"], env, sid, qty=1000, cost="5.00")
    env["admin"].post(f"/api/v1/procurement/orders/{mine['id']}/submit/")
    assert env["admin"].post(f"/api/v1/procurement/orders/{mine['id']}/approve/").status_code == 403  # creator cannot approve
    small = mk_order(env["officer"], env, sid, qty=10, cost="1.00")
    assert env["officer"].post(f"/api/v1/procurement/orders/{small['id']}/submit/").data["status"] == "approved"
    assert env["officer"].post(f"/api/v1/procurement/orders/{small['id']}/submit/").status_code == 409


# ---------------- goods receipt ----------------
def grn(c, order, lines, **kw):
    return c.post("/api/v1/procurement/goods-receipts/", {"order": order["id"], "lines": lines, **kw}, format="json")


def test_partial_deliveries_create_batches_and_complete_order(env):
    sid = mk_supplier(env["admin"], "Acme")
    po = approved_order(env, sid, qty=100, cost="2.00")
    item = po["items"][0]["id"]
    r = grn(env["officer"], po, [{"order_item": item, "quantity": 60, "batch_number": "L1", "expiry_date": D(200)}])
    assert r.status_code == 201 and r.data["number"].startswith("GRN-")
    assert env["officer"].get(f"/api/v1/procurement/orders/{po['id']}/").data["status"] == "partially_received"
    with tenant_context(env["g"]):
        b = Batch.objects.get(batch_number="L1")
        assert (b.quantity_available, b.purchase_cost, b.supplier.name, b.branch_id) == (60, Decimal("2.00"), "Acme", env["main"].pk)
        assert StockMovement.objects.filter(batch=b, reference_type="grn").exists()
    assert grn(env["officer"], po, [{"order_item": item, "quantity": 41, "batch_number": "L2", "expiry_date": D(200)}]).status_code == 400  # over-receipt
    assert grn(env["officer"], po, [{"order_item": item, "quantity": 40, "batch_number": "L2", "expiry_date": D(300)}]).status_code == 201
    assert env["officer"].get(f"/api/v1/procurement/orders/{po['id']}/").data["status"] == "received"
    assert grn(env["officer"], po, [{"order_item": item, "quantity": 1, "batch_number": "L3", "expiry_date": D(300)}]).status_code == 409  # already received
    assert "procurement.goods_received" in set(AuditLog.objects.values_list("action", flat=True))


def test_failed_receipt_rolls_back_completely(env):
    sid = mk_supplier(env["admin"])
    po = approved_order(env, sid, items=[{"medicine": env["med"].pk, "quantity": 10, "unit_cost": "1"}, {"medicine": env["med2"].pk, "quantity": 10, "unit_cost": "1"}])
    i1, i2 = [i["id"] for i in po["items"]]
    bad = grn(env["officer"], po, [{"order_item": i1, "quantity": 5, "batch_number": "OK1", "expiry_date": D(100)},
                                   {"order_item": i2, "quantity": 5, "batch_number": "EXP", "expiry_date": D(-3)}])  # expired stock rejected
    assert bad.status_code == 400
    with tenant_context(env["g"]):
        assert Batch.objects.count() == 0 and GoodsReceipt.objects.count() == 0
        assert not PurchaseOrder.objects.get(pk=po["id"]).items.filter(quantity_received__gt=0).exists()


def test_cannot_receive_on_unapproved_or_cancelled_order(env):
    sid = mk_supplier(env["admin"])
    draft = mk_order(env["officer"], env, sid)
    ln = [{"order_item": draft["items"][0]["id"], "quantity": 1, "batch_number": "X", "expiry_date": D(100)}]
    assert grn(env["officer"], draft, ln).status_code == 409
    env["officer"].post(f"/api/v1/procurement/orders/{draft['id']}/submit/")
    assert env["officer"].post(f"/api/v1/procurement/orders/{draft['id']}/cancel/").data["status"] == "cancelled"
    assert grn(env["officer"], draft, ln).status_code == 409


def test_branch_isolation_in_procurement(env):
    sid = mk_supplier(env["admin"])
    other = mk_order(env["admin"], env, sid, branch=env["second"])
    mine = mk_order(env["officer"], env, sid)
    assert {p["id"] for p in env["officer"].get("/api/v1/procurement/orders/").data["results"]} == {mine["id"]}
    assert env["officer"].get(f"/api/v1/procurement/orders/{other['id']}/").status_code == 404
    assert env["officer"].post(f"/api/v1/procurement/orders/{other['id']}/submit/").status_code == 404
    assert env["officer"].post("/api/v1/procurement/orders/", {"branch": env["second"].pk, "supplier": sid, "items": [{"medicine": env["med"].pk, "quantity": 1, "unit_cost": "1"}]}, format="json").status_code == 403
    assert env["admin_b"].get("/api/v1/procurement/orders/").data["count"] == 0
    assert env["officer"].get("/api/v1/procurement/invoices/").status_code == 403  # pharmacy-level area


# ---------------- invoices and payments ----------------
def test_invoice_and_payment_rules(env):
    sid = mk_supplier(env["admin"])
    c, acc = env["admin"], env["acc"]
    r = c.post("/api/v1/procurement/invoices/", {"supplier": sid, "invoice_number": "SI-1", "amount": "500.00", "due_date": D(30)}, format="json")
    assert r.status_code == 201, r.data
    iid = r.data["id"]
    assert c.post("/api/v1/procurement/invoices/", {"supplier": sid, "invoice_number": "SI-1", "amount": "1.00", "due_date": D(30)}, format="json").status_code == 400
    pay = lambda cl, amt, ref: cl.post(f"/api/v1/procurement/invoices/{iid}/pay/", {"amount": amt, "method": "bank_transfer", "reference": ref}, format="json")  # noqa: E731
    assert pay(env["officer"], "10", "R0").status_code == 403
    assert pay(acc, "600", "R1").status_code == 400  # exceeds balance
    p1 = pay(acc, "200", "R1")
    assert p1.status_code == 201 and p1.data["invoice_status"] == "partially_paid" and Decimal(str(p1.data["outstanding"])) == Decimal("300")
    assert pay(acc, "100", "R1").status_code == 400  # duplicate reference
    bal = acc.get("/api/v1/procurement/supplier-balances/").data
    assert len(bal) == 1 and Decimal(str(bal[0]["outstanding"])) == Decimal("300")
    assert pay(acc, "300", "R2").data["invoice_status"] == "paid"
    assert pay(acc, "1", "R3").status_code == 409  # already paid
    assert acc.get("/api/v1/procurement/supplier-balances/").data == []
    assert {"procurement.invoice_recorded", "procurement.supplier_paid"} <= set(AuditLog.objects.values_list("action", flat=True))


# ---------------- purchase returns ----------------
def test_purchase_return_reduces_stock(env):
    sid = mk_supplier(env["admin"])
    po = approved_order(env, sid, qty=20)
    grn(env["officer"], po, [{"order_item": po["items"][0]["id"], "quantity": 20, "batch_number": "RET", "expiry_date": D(100)}])
    with tenant_context(env["g"]):
        bid = Batch.objects.get(batch_number="RET").pk
    o = env["officer"]
    assert o.post("/api/v1/procurement/returns/", {"batch": bid, "quantity": 5}, format="json").status_code == 400  # reason required
    r = o.post("/api/v1/procurement/returns/", {"batch": bid, "quantity": 5, "reason": "damaged on arrival", "credit_amount": "10"}, format="json")
    assert r.status_code == 201
    assert o.post("/api/v1/procurement/returns/", {"batch": bid, "quantity": 99, "reason": "x"}, format="json").status_code == 409
    with tenant_context(env["g"]):
        assert Batch.objects.get(pk=bid).quantity_available == 15
        assert StockMovement.objects.filter(movement_type="purchase_return", quantity_change=-5).exists()
    assert env["admin_b"].post("/api/v1/procurement/returns/", {"batch": bid, "quantity": 1, "reason": "x"}, format="json").status_code == 404
