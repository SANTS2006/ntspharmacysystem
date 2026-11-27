from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.tenant_context import tenant_context
from apps.inventory import services as inv
from apps.inventory.models import Batch, StockMovement
from apps.medicines.models import Category, Medicine
from apps.tenants.models import Branch, Pharmacy

from .test_foundation import (api, login, platform_admin, platform_client,  # noqa: F401
                              register, settled_token, two_pharmacies)

pytestmark = pytest.mark.django_db(transaction=True)
PW = "Staff-Passw0rd-123!"
D = lambda n: timezone.localdate() + timedelta(days=n)  # noqa: E731


@pytest.fixture
def env(two_pharmacies):
    g, b = Pharmacy.objects.get(slug="greenlife"), Pharmacy.objects.get(slug="bluecross")
    y = timezone.now().year
    admin_g = api("greenlife", settled_token("greenlife", "a@green.test", f"GLP@{y}"))
    admin_b = api("bluecross", settled_token("bluecross", "a@blue.test", f"BCP@{y}"))
    with tenant_context(g):
        main = Branch.objects.get(code="MAIN")
        second = Branch.objects.create(name="Second", code="B2")
        cat, _ = Category.objects.get_or_create(name="Antibiotics")
        med = Medicine.objects.create(name="Amoxicillin 500mg", category=cat, barcode="1234567890", sku="AMX500", reorder_level=20, purchase_cost=0) if False else Medicine.objects.create(name="Amoxicillin 500mg", category=cat, barcode="1234567890", sku="AMX500", reorder_level=20, purchase_price=1, selling_price=2)
    officer = User.objects.create_user("io@green.test", PW, tenant=g, full_name="IO", role=g.roles.get(code="inventory_officer"), branch=main)
    cashier = User.objects.create_user("c@green.test", PW, tenant=g, full_name="C", role=g.roles.get(code="cashier"), branch=main)
    tok = lambda e: api("greenlife", login("greenlife", e, PW).data["tokens"]["access"])  # noqa: E731
    return dict(g=g, b=b, admin_g=admin_g, admin_b=admin_b, main=main, second=second, med=med, cat=cat,
                officer=officer, officer_c=tok("io@green.test"), cashier_c=tok("c@green.test"))


def receive(e, qty, batch="B1", days=100, branch=None, cost="1.00", user=None, med=None):
    with tenant_context(e["g"]):
        return inv.receive_stock(medicine=med or e["med"], branch=branch or e["main"], batch_number=batch, quantity=qty,
                                 purchase_cost=cost, expiry_date=D(days), user=user or e["officer"])


def make_expired(e, qty=10, batch="OLD"):
    with tenant_context(e["g"]):
        return Batch.objects.create(medicine=e["med"], branch=e["main"], batch_number=batch, purchase_date=D(-300), expiry_date=D(-5),
                                    quantity_received=qty, quantity_available=qty, purchase_cost="1.00")


def stock(e, branch=None):
    with tenant_context(e["g"]):
        qs = Batch.objects.filter(medicine=e["med"]).filter(inv.saleable_q())
        if branch:
            qs = qs.filter(branch=branch)
        return sum(b.quantity_available for b in qs)


# ---------------- catalogue ----------------
def test_new_pharmacies_have_no_built_in_categories_and_manage_their_own(env):
    c = env["admin_g"]
    assert [x["name"] for x in c.get("/api/v1/categories/").data] == ["Antibiotics"]  # only the one this test setup created
    assert env["admin_b"].get("/api/v1/categories/").data == []
    r = c.post("/api/v1/categories/", {"name": "Herbal"}, format="json")
    assert r.status_code == 201 and set(r.data) == {"id", "name"}
    assert c.post("/api/v1/categories/", {"name": "herbal"}, format="json").status_code == 400
    assert c.patch(f"/api/v1/categories/{r.data['id']}/", {"name": "Herbals"}, format="json").status_code == 200
    assert c.delete(f"/api/v1/categories/{env['cat'].pk}/").status_code == 400  # in use by a medicine
    assert c.delete(f"/api/v1/categories/{r.data['id']}/").status_code == 204


def test_medicine_validation_rules(env):
    c, cat = env["admin_g"], env["cat"].pk
    base = {"name": "Morphine 10mg", "category": cat}
    assert c.post("/api/v1/medicines/", {**base, "classification": "controlled"}, format="json").status_code == 400  # needs reg number
    r = c.post("/api/v1/medicines/", {**base, "classification": "controlled", "registration_number": "PBSL-1", "is_online_visible": True}, format="json")
    assert r.status_code == 201 and r.data["is_online_visible"] is False and r.data["requires_prescription"] is True
    assert c.post("/api/v1/medicines/", {"name": "X", "category": cat, "barcode": "12"}, format="json").status_code == 400  # bad barcode
    assert c.post("/api/v1/medicines/", {"name": "Dup", "category": cat, "barcode": "1234567890"}, format="json").status_code == 400
    assert c.post("/api/v1/medicines/", {"name": "N", "category": cat, "selling_price": "-1"}, format="json").status_code == 400
    other_cat = Category.all_objects.create(tenant=env["b"], name="Antibiotics").pk
    assert c.post("/api/v1/medicines/", {"name": "Y", "category": other_cat}, format="json").status_code == 400  # other tenant's category
    # same barcode is fine in another pharmacy
    bc = other_cat
    assert env["admin_b"].post("/api/v1/medicines/", {"name": "Z", "category": bc, "barcode": "1234567890"}, format="json").status_code == 201


def test_medicine_tenant_isolation_and_barcode_lookup(env):
    assert env["admin_b"].get(f"/api/v1/medicines/{env['med'].pk}/").status_code == 404
    assert env["admin_b"].get("/api/v1/medicines/").data["count"] == 0
    assert env["admin_g"].get("/api/v1/medicines/barcode/1234567890/").data["name"] == "Amoxicillin 500mg"
    assert env["admin_b"].get("/api/v1/medicines/barcode/1234567890/").status_code == 404


def test_permissions_cashier_reads_catalogue_only(env):
    c = env["cashier_c"]
    assert c.get("/api/v1/medicines/").status_code == 200
    assert c.post("/api/v1/medicines/", {"name": "X", "category": env["cat"].pk}, format="json").status_code == 403
    assert c.get("/api/v1/batches/").status_code == 403 and c.get("/api/v1/inventory/alerts/").status_code == 403


# ---------------- receiving ----------------
def test_receive_rules(env):
    with tenant_context(env["g"]):
        kw = dict(medicine=env["med"], branch=env["main"], quantity=10, purchase_cost="1", user=env["officer"])
        with pytest.raises(ValidationError):
            inv.receive_stock(batch_number="X", **kw)  # expiry required
        with pytest.raises(ValidationError):
            inv.receive_stock(batch_number="X", expiry_date=D(-1), **kw)  # expired
        with pytest.raises(ValidationError):
            inv.receive_stock(batch_number="X", expiry_date=D(30), manufacturing_date=D(40), **kw)
    b = receive(env, 50)
    assert b.quantity_available == 50 and b.quantity_received == 50
    b2 = receive(env, 25)  # same batch number tops up
    assert b2.pk == b.pk and b2.quantity_available == 75
    with pytest.raises(ValidationError):
        receive(env, 5, days=200)  # same number, different expiry
    with tenant_context(env["g"]):
        moves = list(StockMovement.objects.filter(batch=b).order_by("id"))
    assert [(m.previous_quantity, m.new_quantity, m.movement_type) for m in moves] == [(0, 50, "receipt"), (50, 75, "receipt")]


def test_medicine_without_expiry_uses_fifo(env):
    with tenant_context(env["g"]):
        bandage = Medicine.objects.create(name="Bandage", category=env["cat"], has_expiry=False)
        a = inv.receive_stock(medicine=bandage, branch=env["main"], batch_number="A", quantity=5, purchase_cost="1", user=env["officer"], purchase_date=D(-10))
        inv.receive_stock(medicine=bandage, branch=env["main"], batch_number="B", quantity=5, purchase_cost="1", user=env["officer"], purchase_date=D(-1))
        alloc = inv.deduct_fefo(medicine=bandage, branch=env["main"], quantity=7, user=env["officer"])
    assert [(x.batch_number, q) for x, q in alloc] == [("A", 5), ("B", 2)]


# ---------------- FEFO / expiry ----------------
def test_fefo_allocation_and_ledger(env):
    receive(env, 10, "LATE", 200)
    receive(env, 10, "SOON", 30)
    with tenant_context(env["g"]):
        alloc = inv.deduct_fefo(medicine=env["med"], branch=env["main"], quantity=15, user=env["officer"], ref_type="sale", ref_id="S1")
        assert [(b.batch_number, q) for b, q in alloc] == [("SOON", 10), ("LATE", 5)]
        assert Batch.objects.get(batch_number="SOON").quantity_available == 0
        assert Batch.objects.get(batch_number="LATE").quantity_available == 5
        sales = StockMovement.objects.filter(movement_type="sale")
        assert sales.count() == 2 and all(m.reference_id == "S1" and m.quantity_change < 0 for m in sales)


def test_insufficient_stock_is_atomic_and_never_negative(env):
    receive(env, 5, "A", 30)
    receive(env, 5, "B", 60)
    with tenant_context(env["g"]):
        with pytest.raises(inv.InsufficientStock):
            inv.deduct_fefo(medicine=env["med"], branch=env["main"], quantity=11, user=env["officer"])
        assert sorted(Batch.objects.values_list("quantity_available", flat=True)) == [5, 5]  # nothing partially deducted
        b = Batch.objects.get(batch_number="A")
        with pytest.raises(inv.InsufficientStock):
            inv._move(b.pk, -6, "sale", user=env["officer"])  # conditional update refuses to go below zero
        assert Batch.objects.get(pk=b.pk).quantity_available == 5


def test_expired_recalled_quarantined_never_sold(env):
    make_expired(env, 10)
    receive(env, 10, "OK", 50)
    q = receive(env, 10, "Q", 40)
    with tenant_context(env["g"]):
        inv.set_batch_status(batch_id=q.pk, status="quarantined", reason="suspect", user=env["officer"])
    assert stock(env) == 10
    with tenant_context(env["g"]):
        with pytest.raises(inv.InsufficientStock):
            inv.deduct_fefo(medicine=env["med"], branch=env["main"], quantity=11, user=env["officer"])
        assert [b.batch_number for b, _ in inv.deduct_fefo(medicine=env["med"], branch=env["main"], quantity=10, user=env["officer"])] == ["OK"]
    # derived stock in the API matches
    assert env["admin_g"].get(f"/api/v1/medicines/{env['med'].pk}/").data["stock"] == 0


def test_alerts_low_out_near_expiry_expired(env):
    make_expired(env, 4)
    receive(env, 5, "NEAR", 20)  # below reorder level 20, near expiry
    c = env["admin_g"]
    a = c.get("/api/v1/inventory/alerts/").data
    assert [m["name"] for m in a["low_stock"]] == ["Amoxicillin 500mg"] and a["out_of_stock"] == []
    assert [b["batch_number"] for b in a["near_expiry"]] == ["NEAR"] and [b["batch_number"] for b in a["expired"]] == ["OLD"]
    assert a["expired"][0]["saleable"] is False and a["expired"][0]["is_expired"] is True
    with tenant_context(env["g"]):
        inv.deduct_fefo(medicine=env["med"], branch=env["main"], quantity=5, user=env["officer"])
    assert [m["name"] for m in c.get("/api/v1/inventory/alerts/").data["out_of_stock"]] == ["Amoxicillin 500mg"]


def test_write_off_rules(env):
    old = make_expired(env, 10)
    fresh = receive(env, 10, "FRESH", 90)
    with tenant_context(env["g"]):
        with pytest.raises(ValidationError):
            inv.write_off(batch_id=fresh.pk, kind="expired", reason="x", user=env["officer"])
        out = inv.write_off(batch_id=old.pk, kind="expired", reason="expired", user=env["officer"])
        assert out.quantity_available == 0 and Batch.objects.filter(pk=old.pk).exists()  # history kept
        dm = inv.write_off(batch_id=fresh.pk, kind="damaged", reason="water damage", user=env["officer"])
        assert dm.status == "damaged"
        assert {"expiry_writeoff", "damage"} <= set(StockMovement.objects.values_list("movement_type", flat=True))


def test_batch_status_rules_and_recall_across_branches(env):
    a = receive(env, 5, "R1", 60)
    b = receive(env, 5, "R1", 60, branch=env["second"])
    c = env["admin_g"]
    r = c.post("/api/v1/inventory/recall/", {"medicine": env["med"].pk, "batch_number": "R1", "reason": "manufacturer notice"}, format="json")
    assert r.status_code == 200 and r.data["recalled_batches"] == 2
    assert stock(env) == 0
    with tenant_context(env["g"]):
        with pytest.raises(ValidationError):
            inv.set_batch_status(batch_id=a.pk, status="available", reason="oops", user=env["officer"])  # recalled is terminal
        with pytest.raises(ValidationError):
            inv.receive_stock(medicine=env["med"], branch=env["main"], batch_number="R1", quantity=1, purchase_cost="1", expiry_date=D(60), user=env["officer"])
    assert env["officer_c"].post("/api/v1/inventory/recall/", {"medicine": env["med"].pk, "batch_number": "R1", "reason": "x"}, format="json").status_code == 403
    assert "inventory.batch_recalled" in set(AuditLog.objects.values_list("action", flat=True))


def test_adjustment_requires_reason_and_is_logged(env):
    b = receive(env, 10, "ADJ", 60)
    c = env["officer_c"]
    assert c.post(f"/api/v1/batches/{b.pk}/adjust/", {"new_quantity": 8}, format="json").status_code == 400
    r = c.post(f"/api/v1/batches/{b.pk}/adjust/", {"new_quantity": 8, "reason": "stocktake count"}, format="json")
    assert r.status_code == 200 and r.data["quantity_available"] == 8
    with tenant_context(env["g"]):
        m = StockMovement.objects.filter(movement_type="adjustment").get()
        assert (m.previous_quantity, m.new_quantity, m.quantity_change, m.user_id) == (10, 8, -2, env["officer"].pk)
        with pytest.raises(PermissionError):
            m.quantity_change = 99
            m.save()


def test_transfer_between_branches(env):
    b = receive(env, 20, "T1", 90)
    with tenant_context(env["g"]):
        inv.transfer_stock(batch_id=b.pk, to_branch=env["second"], quantity=8, user=env["officer"], reason="rebalance")
        assert Batch.objects.get(pk=b.pk).quantity_available == 12
        dest = Batch.objects.get(branch=env["second"], batch_number="T1")
        assert dest.quantity_available == 8 and dest.expiry_date == b.expiry_date
        assert {"transfer_out", "transfer_in"} <= set(StockMovement.objects.values_list("movement_type", flat=True))
        with pytest.raises(inv.InsufficientStock):
            inv.transfer_stock(batch_id=b.pk, to_branch=env["second"], quantity=13, user=env["officer"])
        with pytest.raises(ValidationError):
            inv.transfer_stock(batch_id=b.pk, to_branch=env["main"], quantity=1, user=env["officer"])
    blue_branch = Branch.all_objects.filter(tenant=env["b"]).first()
    r = env["admin_g"].post("/api/v1/inventory/transfers/", {"batch": b.pk, "to_branch": blue_branch.pk, "quantity": 1}, format="json")
    assert r.status_code == 404  # another pharmacy's branch is invisible


def test_branch_scoping_for_inventory(env):
    receive(env, 10, "M1", 90)
    receive(env, 7, "S1", 90, branch=env["second"])
    o, a = env["officer_c"], env["admin_g"]
    assert {x["batch_number"] for x in o.get("/api/v1/batches/").data["results"]} == {"M1"}
    assert {x["batch_number"] for x in a.get("/api/v1/batches/").data["results"]} == {"M1", "S1"}
    assert o.get(f"/api/v1/medicines/{env['med'].pk}/").data["stock"] == 10 and a.get(f"/api/v1/medicines/{env['med'].pk}/").data["stock"] == 17
    body = {"medicine": env["med"].pk, "batch_number": "N1", "quantity": 5, "purchase_cost": "1.00", "expiry_date": str(D(90))}
    assert o.post("/api/v1/inventory/receive/", {**body, "branch": env["second"].pk}, format="json").status_code == 403
    assert o.post("/api/v1/inventory/receive/", {**body, "branch": env["main"].pk}, format="json").status_code == 201
    s1 = Batch.all_objects.get(batch_number="S1")
    assert o.post(f"/api/v1/batches/{s1.pk}/adjust/", {"new_quantity": 1, "reason": "x"}, format="json").status_code == 404
    assert env["admin_b"].get("/api/v1/batches/").data["count"] == 0


def test_archive_blocked_with_stock_and_valuation(env):
    receive(env, 10, "V1", 90, cost="2.50")
    make_expired(env, 4)
    c = env["admin_g"]
    assert c.post(f"/api/v1/medicines/{env['med'].pk}/archive/").status_code == 400
    v = c.get("/api/v1/inventory/valuation/").data
    assert float(v["saleable_value"]) == 25.0 and float(v["unsaleable_value"]) == 4.0
    with tenant_context(env["g"]):
        old = Batch.objects.get(batch_number="OLD")
        inv.write_off(batch_id=old.pk, kind="expired", reason="x", user=env["officer"])
        v1 = Batch.objects.get(batch_number="V1")
        inv.adjust_stock(batch_id=v1.pk, new_quantity=0, reason="clear", user=env["officer"])
    assert c.post(f"/api/v1/medicines/{env['med'].pk}/archive/").status_code == 200
    assert c.post("/api/v1/inventory/receive/", {"medicine": env["med"].pk, "branch": env["main"].pk, "batch_number": "Z", "quantity": 1, "purchase_cost": "1", "expiry_date": str(D(50))}, format="json").status_code == 400
