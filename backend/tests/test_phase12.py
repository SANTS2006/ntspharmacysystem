import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.tenant_context import tenant_context
from apps.inventory import services as inv
from apps.inventory.models import Batch
from apps.medicines.models import Medicine

from .test_foundation import api, login, platform_admin, platform_client, register, settled_token, two_pharmacies  # noqa: F401
from .test_phase7 import PW, cash, env, open_shift, sell, stock  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Dec = Decimal
R = "/api/v1/reports"
TODAY = lambda: timezone.localdate()  # noqa: E731


@pytest.fixture
def rep(env):
    g = env["g"]
    for k, role in (("acct", "accountant"), ("hrm", "hr_manager")):
        User.objects.create_user(f"{k}@green.test", PW, tenant=g, full_name=k.upper(), role=g.roles.get(code=role))
        env[k] = api("greenlife", login("greenlife", f"{k}@green.test", PW).data["tokens"]["access"])
    return env


def run(c, slug, status=200, **q):
    r = c.get(f"{R}/{slug}/", data=q)
    assert r.status_code == status, getattr(r, "data", r)
    return r


def trade(env):
    """Two sales by two cashiers on different branches plus one partial return."""
    stock(env, env["para"], 50)
    stock(env, env["vit"], 50, "V1")
    stock(env, env["para"], 20, "S1", branch=env["second"])
    open_shift(env["c1"])
    open_shift(env["c3"])
    open_shift(env["mgr"], "0.00")
    s1 = sell(env["c1"], [{"medicine": env["para"].pk, "quantity": 3}, {"medicine": env["vit"].pk, "quantity": 2}], [cash(100)]).data  # 33 + 10 = 43
    sell(env["c3"], [{"medicine": env["para"].pk, "quantity": 1}], [{"method": "mobile_money", "amount": "11.00", "reference": "MM-9"}])  # 11
    line = s1["lines"][0]["id"]
    env["mgr"].post(f"/api/v1/sales/{s1['id']}/return/", {"lines": [{"sale_line": line, "quantity": 1}], "reason": "x", "refund_method": "cash", "restock": True}, format="json")  # 11
    return s1


# ---------------- access ----------------
def test_report_catalogue_depends_on_role(rep):
    slugs = lambda c: {r["slug"] for r in c.get(f"{R}/").data}  # noqa: E731
    assert {"sales-summary", "profit-and-loss", "payroll-summary", "attendance-summary", "stock-current"} <= slugs(rep["admin"])
    mgr = slugs(rep["mgr"])
    assert "sales-summary" in mgr and "attendance-summary" in mgr and "payroll-summary" in mgr and "profit-and-loss" not in mgr and "refunds" not in mgr
    acc = slugs(rep["acct"])
    assert "profit-and-loss" in acc and "supplier-outstanding" in acc and "payroll-summary" not in acc and "attendance-summary" not in acc
    assert rep["c1"].get(f"{R}/").status_code == 403 and rep["tech"].get(f"{R}/sales-summary/").status_code == 403
    run(rep["acct"], "payroll-summary", 403)
    run(rep["mgr"], "profit-and-loss", 403)
    assert rep["admin"].get(f"{R}/nope/").status_code == 404
    assert api().get(f"{R}/").status_code == 401


# ---------------- sales reports ----------------
def test_sales_reports_numbers_and_filters(rep):
    trade(rep)
    a = rep["admin"]
    d = run(a, "sales-summary").data
    assert d["count"] == 1 and d["summary"]["sales"] == 2
    row = d["rows"][0]
    assert (Dec(str(row["total"])), Dec(str(row["refunds"])), Dec(str(row["net_sales"]))) == (Dec("54"), Dec("11"), Dec("43"))
    assert run(a, "sales-summary", group="month").data["rows"][0]["sales"] == 2 and run(a, "sales-summary", group="year").data["count"] == 1
    assert run(a, "sales-summary", date_from=str(TODAY() + timedelta(days=1)), date_to=str(TODAY() + timedelta(days=5))).data["count"] == 0
    assert run(a, "sales-summary", date_from=str(TODAY()), date_to=str(TODAY() - timedelta(days=3)), status=400)
    assert run(a, "sales-summary", date_from="bad", status=400)
    p = {r["product"]: r for r in run(a, "sales-by-product").data["rows"]}
    assert p["Paracetamol"]["quantity"] == 4 and p["Paracetamol"]["returned"] == 1 and p["Vitamin C"]["quantity"] == 2
    assert {r["category"] for r in run(a, "sales-by-category").data["rows"]} == {"Antibiotics"}
    cashiers = {r["cashier"]: r for r in run(a, "sales-by-cashier").data["rows"]}
    assert cashiers["C1"]["sales"] == 1 and Dec(str(cashiers["C1"]["total"])) == Dec("43") and Dec(str(cashiers["C3"]["total"])) == Dec("11")
    assert {r["branch"] for r in run(a, "sales-by-branch").data["rows"]} == {"Main Branch", "Second"}
    pm = {r["method"]: Dec(str(r["amount"])) for r in run(a, "payment-methods").data["rows"]}
    assert pm == {"cash": Dec("43"), "mobile money": Dec("11")}
    only_second = run(a, "sales-by-branch", branch=rep["second"].pk).data["rows"]
    assert [r["branch"] for r in only_second] == ["Second"]


def test_search_ordering_and_pagination(rep):
    trade(rep)
    a = rep["admin"]
    assert [r["product"] for r in run(a, "sales-by-product", search="vita").data["rows"]] == ["Vitamin C"]
    asc = [r["quantity"] for r in run(a, "sales-by-product", ordering="quantity").data["rows"]]
    assert asc == sorted(asc) and [r["quantity"] for r in run(a, "sales-by-product", ordering="-quantity").data["rows"]] == sorted(asc, reverse=True)
    run(a, "sales-by-product", status=400, ordering="password")
    pg = run(a, "stock-movements", page_size=2).data
    assert len(pg["rows"]) == 2 and pg["count"] > 2 and pg["page_size"] == 2
    assert run(a, "stock-movements", page_size=2, page=2).data["rows"][0] != pg["rows"][0]


def test_branch_managers_are_pinned_to_their_branch(rep):
    trade(rep)
    m = rep["mgr"]
    assert [r["branch"] for r in run(m, "sales-by-branch").data["rows"]] == ["Main Branch"]
    run(m, "sales-by-branch", 403, branch=rep["second"].pk)
    assert {r["cashier"] for r in run(m, "sales-by-cashier").data["rows"]} == {"C1"}
    assert Dec(str(run(m, "sales-summary").data["rows"][0]["total"])) == Dec("43")
    assert run(rep["admin_b"], "sales-summary").data["rows"] == []  # other pharmacy sees nothing


# ---------------- inventory / procurement / financial ----------------
def test_inventory_reports(rep):
    stock(rep, rep["para"], 5, "LOW")
    with tenant_context(rep["g"]):
        Medicine.objects.filter(pk=rep["para"].pk).update(reorder_level=10)
        Batch.objects.create(medicine=rep["vit"], branch=rep["main"], batch_number="OLD", purchase_date=TODAY() - timedelta(days=200), expiry_date=TODAY() - timedelta(days=3), quantity_received=7, quantity_available=7, purchase_cost=2)
        inv.receive_stock(medicine=rep["amox"], branch=rep["main"], batch_number="NEAR", quantity=4, purchase_cost="3", expiry_date=TODAY() + timedelta(days=20), user=User.objects.get(email="ph@green.test"))
    a = rep["admin"]
    assert [(r["medicine"], r["saleable"]) for r in run(a, "low-stock").data["rows"]] == [("Paracetamol", 5)]
    assert "Vitamin C" in {r["medicine"] for r in run(a, "out-of-stock").data["rows"]}
    exp = run(a, "expired-stock").data["rows"]
    assert [(r["medicine"], r["quantity"], r["batch"]) for r in exp] == [("Vitamin C", 7, "OLD")] and Dec(str(exp[0]["value"])) == Dec("14")
    assert [r["batch"] for r in run(a, "near-expiry", days=30).data["rows"]] == ["NEAR"] and run(a, "near-expiry", days=10).data["rows"] == []
    val = run(a, "stock-valuation").data["rows"][0]
    assert Dec(str(val["saleable_value"])) == Dec("5") * Dec("1") + Dec("12") and Dec(str(val["unsaleable_value"])) == Dec("14")
    cur = {(r["medicine"], r["branch"]): r["saleable"] for r in run(a, "stock-current").data["rows"]}
    assert cur[("Paracetamol", "Main Branch")] == 5
    batch = Batch.all_objects.get(batch_number="LOW")
    a.post(f"/api/v1/batches/{batch.pk}/adjust/", {"new_quantity": 4, "reason": "count"}, format="json")
    assert [r["type"] for r in run(a, "stock-adjustments").data["rows"]] == ["adjustment"]
    a.post("/api/v1/inventory/transfers/", {"batch": batch.pk, "to_branch": rep["second"].pk, "quantity": 2}, format="json")
    assert [(r["from"], r["to"], r["quantity"]) for r in run(a, "stock-transfers").data["rows"]] == [("Main Branch", "Second", 2)]
    assert run(rep["mgr"], "low-stock").status_code == 200 and run(rep["c1"], "low-stock", 403)


def test_financial_and_staff_reports(rep):
    trade(rep)
    acc = rep["acct"]
    pl = {r["account"]: Dec(str(r["amount"])) for r in run(acc, "profit-and-loss").data["rows"]}
    assert pl["Net profit"] == pl["Gross profit"] and "Sales revenue" in pl
    refunds = run(acc, "refunds").data
    assert refunds["count"] == 1 and Dec(str(refunds["summary"]["total"])) == Dec("11")
    assert run(acc, "cash-flow").data["summary"]["closing"] != 0
    assert run(acc, "branch-performance").data["count"] >= 1
    rep["c1"].post("/api/v1/hr/attendance/clock-in/")
    att = run(rep["mgr"], "attendance-summary").data["rows"]
    assert [r["staff"] for r in att] == ["C1"]
    assert run(rep["hrm"], "attendance-summary").data["count"] == 1
    run(rep["tech"], "attendance-summary", 403)


# ---------------- exports ----------------
def test_exports_in_every_format_and_are_audited(rep):
    trade(rep)
    a = rep["admin"]
    csv = a.get(f"{R}/sales-by-product/?export=csv")
    assert csv.status_code == 200 and csv["Content-Type"].startswith("text/csv") and "attachment" in csv["Content-Disposition"] and csv["Cache-Control"] == "private, no-store"
    body = csv.content.decode("utf-8-sig")
    assert body.splitlines()[0].startswith("Product,Category") and "Paracetamol" in body
    x = a.get(f"{R}/sales-by-product/?export=xlsx")
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(x.content)).active
    assert [c.value for c in ws[1]][:2] == ["Product", "Category"] and ws.max_row == 3
    pdf = a.get(f"{R}/sales-by-product/?export=pdf")
    assert pdf.content.startswith(b"%PDF") and pdf["Content-Type"] == "application/pdf"
    assert a.get(f"{R}/sales-by-product/?export=docx").status_code == 400
    log = list(AuditLog.objects.filter(action="report.exported").values_list("metadata", flat=True))
    assert {m["format"] for m in log} == {"csv", "xlsx", "pdf"} and all(m["report"] == "sales-by-product" for m in log)
    before = AuditLog.objects.filter(action="report.exported").count()
    assert rep["c1"].get(f"{R}/sales-by-product/?export=csv").status_code == 403 and rep["tech"].get(f"{R}/stock-current/?export=xlsx").status_code == 403
    assert AuditLog.objects.filter(action="report.exported").count() == before  # refused exports are not exported


def test_exports_neutralise_spreadsheet_formulas(rep):
    with tenant_context(rep["g"]):
        evil = Medicine.objects.create(name='=HYPERLINK("http://evil.example","click")', category=rep["para"].category, purchase_price=1, selling_price=5)
    stock(rep, evil, 5, "EV")
    open_shift(rep["c1"])
    sell(rep["c1"], [{"medicine": evil.pk, "quantity": 1}], [cash(10)])
    a = rep["admin"]
    assert "'=HYPERLINK" in a.get(f"{R}/sales-by-product/?export=csv").content.decode("utf-8-sig")
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(a.get(f"{R}/sales-by-product/?export=xlsx").content)).active
    cells = [c.value for row in ws.iter_rows(min_row=2) for c in row if isinstance(c.value, str)]
    assert any(v.startswith("'=HYPERLINK") for v in cells) and not any(v.startswith("=") for v in cells)


# ---------------- dashboard ----------------
def test_dashboard_metrics_and_scoping(rep):
    trade(rep)
    d = rep["admin"].get(f"{R}/dashboard/").data
    assert d["scope"] == "pharmacy" and d["people"]["branches"] == 2 and d["people"]["pharmacists"] == 1
    assert Dec(str(d["sales"]["today"])) == Dec("43") and d["sales"]["transactions"] == 2
    assert Dec(str(d["finance"]["revenue"])) > 0 and d["finance"]["outstanding_supplier_payments"] is not None
    assert d["medicines"]["total"] == 3 and Dec(str(d["medicines"]["inventory_value"])) > 0
    assert {r["method"] for r in d["payment_breakdown"]} == {"cash", "mobile money"} and {r["branch"] for r in d["branch_performance"]} >= {"Main Branch", "Second"}
    m = rep["mgr"].get(f"{R}/dashboard/").data
    assert m["scope"] == "branch" and Dec(str(m["sales"]["today"])) == Dec("32")  # 43 sold less the 11 refunded and m["finance"]["outstanding_supplier_payments"] is None and m["people"]["customers"] is None
    assert {r["cashier"] for r in m["cashier_performance"]} == {"C1"}
    assert rep["mgr"].get(f"{R}/dashboard/?branch={rep['second'].pk}").status_code == 403
    assert rep["c1"].get(f"{R}/dashboard/").status_code == 403
    e = rep["admin_b"].get(f"{R}/dashboard/").data
    assert e["sales"]["transactions"] == 0 and e["medicines"]["total"] == 0
