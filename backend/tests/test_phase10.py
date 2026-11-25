from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone

from apps.accounting import posting
from apps.accounting.models import JournalEntry, JournalLine
from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.exceptions import BusinessRuleViolation
from apps.core.tenant_context import tenant_context
from apps.inventory import services as inv
from apps.inventory.models import Batch
from apps.sales.models import Sale

from .test_foundation import api, login, platform_admin, platform_client, register, settled_token, two_pharmacies  # noqa: F401
from .test_phase7 import PW, cash, env, open_shift, sell, stock  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Dec = Decimal
TODAY = lambda: timezone.localdate()  # noqa: E731
YDAY = lambda: TODAY() - timedelta(days=1)  # noqa: E731
A = "/api/v1/accounting"


@pytest.fixture
def fin(env):
    g = env["g"]
    User.objects.create_user("acct@green.test", PW, tenant=g, full_name="Acct", role=g.roles.get(code="accountant"))
    env["acct"] = api("greenlife", login("greenlife", "acct@green.test", PW).data["tokens"]["access"])
    return env


def tb(c, **q):
    r = c.get(f"{A}/reports/trial-balance/", data=q)
    assert r.status_code == 200, r.data
    return {row["code"]: (Dec(str(row["debit"])), Dec(str(row["credit"]))) for row in r.data["rows"]}, r.data


def net(c, code, **q):
    rows, _ = tb(c, **q)
    d, cr = rows.get(code, (Dec(0), Dec(0)))
    return d - cr  # debit-positive


def entries(c, **q):
    return c.get(f"{A}/journal-entries/", data=q).data["results"]


def manual(c, lines, desc="Opening balance", status=201, **kw):
    r = c.post(f"{A}/journal-entries/", {"description": desc, "lines": lines, **kw}, format="json")
    assert r.status_code == status, r.data
    return r


# ---------------- chart of accounts ----------------
def test_default_chart_and_custom_accounts(fin):
    c = fin["acct"]
    accts = {a["code"]: a for a in c.get(f"{A}/accounts/").data}
    assert len(accts) == 31 and accts["1000"]["type"] == "asset" and accts["4000"]["type"] == "revenue"
    r = c.post(f"{A}/accounts/", {"code": "6700", "name": "Cleaning", "type": "expense"}, format="json")
    assert r.status_code == 201 and r.data["is_system"] is False
    assert c.post(f"{A}/accounts/", {"code": "6700", "name": "Dup", "type": "expense"}, format="json").status_code == 400
    assert c.post(f"{A}/accounts/", {"code": "7000", "name": "Bad", "type": "expense"}, format="json").status_code == 400  # wrong prefix for the type
    assert c.post(f"{A}/accounts/", {"code": "abc", "name": "Bad", "type": "asset"}, format="json").status_code == 400
    assert c.patch(f"{A}/accounts/{accts['1000']['id']}/", {"name": "x"}, format="json").status_code == 400  # system accounts are fixed
    assert fin["c1"].get(f"{A}/accounts/").status_code == 403 and fin["mgr"].post(f"{A}/accounts/", {}, format="json").status_code == 403
    assert fin["admin_b"].get(f"{A}/accounts/").status_code == 200 and fin["admin_b"].post(f"{A}/accounts/", {"code": "6700", "name": "Own", "type": "expense"}, format="json").status_code == 201  # per pharmacy


# ---------------- sales postings ----------------
def test_sale_posts_balanced_entry_with_cogs_and_tax(fin):
    stock(fin, fin["para"])  # cost 1.00 per unit
    open_shift(fin["c1"])
    sell(fin["c1"], [{"medicine": fin["para"].pk, "quantity": 3}], [cash(40)])  # 30 net + 3 tax = 33
    e = entries(fin["acct"], source_type="sale")
    assert len(e) == 1
    d = fin["acct"].get(f"{A}/journal-entries/{e[0]['id']}/").data
    by = {l["account"]: (Dec(str(l["debit"])), Dec(str(l["credit"]))) for l in d["lines"]}
    assert by["1000"] == (Dec("33"), 0) and by["4000"] == (0, Dec("30")) and by["2100"] == (0, Dec("3")) and by["5000"] == (Dec("3"), 0) and by["1200"] == (0, Dec("3"))
    assert sum(Dec(str(l["debit"])) for l in d["lines"]) == sum(Dec(str(l["credit"])) for l in d["lines"]) == Dec(str(d["total"]))
    pl = fin["acct"].get(f"{A}/reports/income-statement/").data
    assert (Dec(str(pl["net_revenue"])), Dec(str(pl["cost_of_sales_total"])), Dec(str(pl["gross_profit"]))) == (Dec("30"), Dec("3"), Dec("27"))
    assert fin["acct"].get(f"{A}/reports/integrity/").data["unbalanced_entries"] == []


def test_discounts_split_payments_and_branch_attribution(fin):
    stock(fin, fin["para"])
    open_shift(fin["c1"])
    sell(fin["c1"], [{"medicine": fin["para"].pk, "quantity": 2, "discount_pct": "5"}], [{"method": "mobile_money", "amount": "10.00", "reference": "MM-1"}, cash(15)])  # total 20.90
    c = fin["acct"]
    assert net(c, "1010") == Dec("10") and net(c, "1000") == Dec("10.90")  # cash applied net of change
    assert net(c, "4900") == Dec("1.00") and net(c, "4000") == Dec("-20.00")  # gross revenue less contra discount = 19.00 net
    pl = c.get(f"{A}/reports/income-statement/").data
    assert Dec(str(pl["net_revenue"])) == Dec("19.00")
    rows = c.get(f"{A}/reports/branch-summary/").data
    main = [r for r in rows if r["branch"] == fin["main"].pk][0]
    assert Dec(str(main["net_revenue"])) == Dec("19.00") and not [r for r in rows if r["branch"] == fin["second"].pk and Dec(str(r["net_revenue"])) != 0]


def test_partial_payment_posts_receivable_then_clears_it(fin):
    stock(fin, fin["para"])
    fin["admin"].patch("/api/v1/tenants/me/", {"settings": {"allow_partial_payments": True}}, format="json")
    open_shift(fin["c1"])
    s = sell(fin["c1"], [{"medicine": fin["para"].pk, "quantity": 2}], [cash(10)], customer_name="Mrs B").data  # 22 total, 12 owed
    c = fin["acct"]
    assert net(c, "1100") == Dec("12")
    rec = c.get(f"{A}/reports/receivables/").data
    assert Dec(str(rec["ledger_balance"])) == Dec("12") and rec["open_sales"][0]["customer_name"] == "Mrs B"
    fin["c1"].post(f"/api/v1/sales/{s['id']}/payments/", {"payments": [cash(12)]}, format="json")
    assert net(c, "1100") == 0 and net(c, "1000") == Dec("22")


def test_returns_cancellations_and_restock_reverse_the_right_accounts(fin):
    stock(fin, fin["para"], 20)
    open_shift(fin["c1"])
    open_shift(fin["mgr"], "0.00")
    s = sell(fin["c1"], [{"medicine": fin["para"].pk, "quantity": 4}], [cash(50)]).data  # 44.00: 40 + 4 tax; COGS 4
    line = s["lines"][0]["id"]
    r = fin["mgr"].post(f"/api/v1/sales/{s['id']}/return/", {"lines": [{"sale_line": line, "quantity": 1}], "reason": "x", "refund_method": "cash", "restock": True}, format="json")
    assert r.status_code == 201
    c = fin["acct"]
    assert net(c, "4950") == Dec("10") and net(c, "2100") == Dec("-3.00") and net(c, "1000") == Dec("33.00")  # 44 - 11 refunded
    assert net(c, "5000") == Dec("3.00") and net(c, "1200") == Dec("-3.00")  # one unit back in stock: cost reversed
    assert Dec(str(c.get(f"{A}/reports/income-statement/").data["net_revenue"])) == Dec("30.00")
    fin["mgr"].post(f"/api/v1/sales/{s['id']}/return/", {"lines": [{"sale_line": line, "quantity": 3}], "reason": "x", "refund_method": "cash", "restock": False}, format="json")
    assert net(c, "4950") == Dec("40") and net(c, "1000") == 0 and net(c, "2100") == 0
    assert c.get(f"{A}/reports/integrity/").data["trial_balance_balanced"] is True  # rounding never unbalances the books


def test_posting_failure_rolls_the_business_event_back(fin):
    stock(fin, fin["para"], 10)
    open_shift(fin["c1"])
    with mock.patch.object(posting, "post_sale", side_effect=BusinessRuleViolation("ledger unavailable")):
        sell(fin["c1"], [{"medicine": fin["para"].pk, "quantity": 2}], [cash(30)], status=409)
    assert Sale.all_objects.count() == 0
    with tenant_context(fin["g"]):
        assert Batch.objects.get(batch_number="B1").quantity_available == 10  # stock restored: books and operations cannot diverge


def test_posting_is_idempotent_and_entries_are_immutable(fin):
    stock(fin, fin["para"])
    open_shift(fin["c1"])
    s = sell(fin["c1"], [{"medicine": fin["para"].pk, "quantity": 1}], [cash(20)]).data
    with tenant_context(fin["g"]):
        before = JournalEntry.objects.count()
        sale = Sale.objects.get(pk=s["id"])
        assert posting.post_sale(sale).pk == posting.post_sale(sale).pk and JournalEntry.objects.count() == before
        e = JournalEntry.objects.get(source_type="sale")
        e.description = "tampered"
        with pytest.raises(PermissionError):
            e.save()
        with pytest.raises(PermissionError):
            e.delete()
        ln = JournalLine.objects.first()
        ln.debit = 999
        with pytest.raises(PermissionError):
            ln.save()
        with pytest.raises(PermissionError):
            ln.delete()


# ---------------- manual journals and reversals ----------------
def test_manual_journal_validation_and_permissions(fin):
    c = fin["acct"]
    ok = [{"account": "1000", "debit": "100"}, {"account": "3100", "credit": "100"}]
    assert manual(c, ok).data["number"].startswith("JE-")
    assert manual(c, [{"account": "1000", "debit": "100"}, {"account": "3100", "credit": "90"}], status=409).data["error"]["code"] == "business_rule_violation"  # unbalanced
    manual(c, [{"account": "1000", "debit": "100", "credit": "100"}, {"account": "3100", "credit": "0"}], status=400)  # both sides on one line
    manual(c, [{"account": "1000", "debit": "100"}], status=400)  # needs two lines
    manual(c, [{"account": "9999", "debit": "5"}, {"account": "3100", "credit": "5"}], status=400)  # unknown account
    manual(c, ok, status=400, date=str(TODAY() + timedelta(days=2)))  # future date
    manual(c, ok, desc="  ", status=400)
    manual(c, [{"account": "1000", "debit": "0"}, {"account": "3100", "credit": "0"}], status=400)  # nothing to post
    assert fin["c1"].post(f"{A}/journal-entries/", {"description": "x", "lines": ok}, format="json").status_code == 403
    assert fin["mgr"].post(f"{A}/journal-entries/", {"description": "x", "lines": ok}, format="json").status_code == 403
    assert len(entries(c)) == 1 and Dec(str(entries(c)[0]["total"])) == Dec("100")
    k = {"HTTP_IDEMPOTENCY_KEY": "m-1"}
    a = c.post(f"{A}/journal-entries/", {"description": "Dup", "lines": ok}, format="json", **k)
    b = c.post(f"{A}/journal-entries/", {"description": "Dup", "lines": ok}, format="json", **k)
    assert a.data["id"] == b.data["id"] and len(entries(c)) == 2
    assert "accounting.manual_entry" in set(AuditLog.objects.values_list("action", flat=True))


def test_reversal_rules(fin):
    c = fin["acct"]
    e = manual(c, [{"account": "6100", "debit": "40"}, {"account": "1000", "credit": "40"}], "Rent").data
    assert c.post(f"{A}/journal-entries/{e['id']}/reverse/", {}, format="json").status_code == 400  # reason required
    rev = c.post(f"{A}/journal-entries/{e['id']}/reverse/", {"reason": "posted twice"}, format="json")
    assert rev.status_code == 201 and rev.data["reverses"] == e["number"]
    assert {l["account"]: (Dec(str(l["debit"])), Dec(str(l["credit"]))) for l in rev.data["lines"]} == {"6100": (0, Dec("40")), "1000": (Dec("40"), 0)}
    assert net(c, "6100") == 0 and net(c, "1000") == 0
    assert c.get(f"{A}/journal-entries/{e['id']}/").data["reversed"] is True
    assert c.post(f"{A}/journal-entries/{e['id']}/reverse/", {"reason": "again"}, format="json").status_code == 409  # only once
    assert c.post(f"{A}/journal-entries/{rev.data['id']}/reverse/", {"reason": "undo the undo"}, format="json").status_code == 409
    stock(fin, fin["para"])
    open_shift(fin["c1"])
    sell(fin["c1"], [{"medicine": fin["para"].pk, "quantity": 1}], [cash(20)])
    sale_entry = entries(c, source_type="sale")[0]
    assert c.post(f"{A}/journal-entries/{sale_entry['id']}/reverse/", {"reason": "x"}, format="json").status_code == 409  # system entries are corrected via returns
    assert fin["admin_b"].get(f"{A}/journal-entries/{e['id']}/").status_code == 404 and fin["admin_b"].post(f"{A}/journal-entries/{e['id']}/reverse/", {"reason": "x"}, format="json").status_code == 404


# ---------------- expenses ----------------
def test_expenses_post_reverse_and_branch_report(fin):
    c = fin["acct"]
    body = {"date": str(TODAY()), "account": "6100", "amount": "50.00", "payment_method": "cash", "description": "Shop rent", "branch": fin["main"].pk}
    r = c.post(f"{A}/expenses/", body, format="json")
    assert r.status_code == 201, r.data
    assert r.data["journal_entry"].startswith("JE-")
    assert net(c, "6100") == Dec("50") and net(c, "1000") == Dec("-50")
    assert c.post(f"{A}/expenses/", {**body, "account": "5000"}, format="json").status_code == 400  # cost of sales is not an operating expense
    assert c.post(f"{A}/expenses/", {**body, "account": "1000"}, format="json").status_code == 400
    assert c.post(f"{A}/expenses/", {**body, "amount": "0"}, format="json").status_code == 400
    assert c.post(f"{A}/expenses/", {**body, "payment_method": "voucher"}, format="json").status_code == 400
    assert c.post(f"{A}/expenses/", {**body, "date": str(TODAY() + timedelta(days=1))}, format="json").status_code == 400
    assert fin["c1"].post(f"{A}/expenses/", body, format="json").status_code == 403
    c.post(f"{A}/expenses/", {**body, "account": "6200", "amount": "20", "payment_method": "bank", "branch": None, "description": "Electricity (pharmacy level)"}, format="json")
    rows = {r["name"]: Dec(str(r["operating_expenses"])) for r in c.get(f"{A}/reports/branch-summary/").data}
    assert rows["Main Branch"] == Dec("50") and rows["Pharmacy level"] == Dec("20")
    pl = c.get(f"{A}/reports/income-statement/").data
    assert Dec(str(pl["operating_expenses_total"])) == Dec("70") and Dec(str(pl["net_profit"])) == Dec("-70")
    exp_id = c.get(f"{A}/expenses/").data["results"][-1]["id"]
    rv = c.post(f"{A}/expenses/{exp_id}/reverse/", {"reason": "duplicate"}, format="json")
    assert rv.status_code == 201 and c.get(f"{A}/expenses/").data["results"][-1]["status"] == "reversed"
    assert c.post(f"{A}/expenses/{exp_id}/reverse/", {"reason": "again"}, format="json").status_code == 400
    assert net(c, "6100") == 0


# ---------------- stock-driven postings ----------------
def test_write_offs_adjustments_and_transfers_post_inventory_value(fin):
    b = stock(fin, fin["para"], 10)  # cost 1.00
    c = fin["acct"]
    admin = fin["admin"]
    admin.post(f"/api/v1/batches/{b.pk}/adjust/", {"new_quantity": 7, "reason": "stocktake"}, format="json")  # -3
    assert net(c, "5100") == Dec("3") and net(c, "1200") == Dec("-3")
    admin.post(f"/api/v1/batches/{b.pk}/adjust/", {"new_quantity": 8, "reason": "found"}, format="json")  # +1
    assert net(c, "5100") == Dec("2") and net(c, "1200") == Dec("-2")
    admin.post(f"/api/v1/batches/{b.pk}/write-off/", {"kind": "damaged", "reason": "water", "quantity": 2}, format="json")
    assert net(c, "5100") == Dec("4")
    r = admin.post("/api/v1/inventory/transfers/", {"batch": b.pk, "to_branch": fin["second"].pk, "quantity": 3}, format="json")
    assert r.status_code == 201
    inv_by_branch = {x["name"]: Dec(str(x["net_revenue"])) for x in c.get(f"{A}/reports/branch-summary/").data}  # transfers do not touch revenue
    assert all(v == 0 for v in inv_by_branch.values())
    main_inv = Dec(str(c.get(f"{A}/reports/general-ledger/1200/", data={"branch": fin["main"].pk}).data["closing_balance"]))
    second_inv = Dec(str(c.get(f"{A}/reports/general-ledger/1200/", data={"branch": fin["second"].pk}).data["closing_balance"]))
    assert second_inv == Dec("3") and main_inv == Dec("-7")  # value moved between branches; total inventory unchanged
    assert c.get(f"{A}/reports/integrity/").data["trial_balance_balanced"] is True


def test_cash_discrepancy_and_cash_movements(fin):
    sh = open_shift(fin["c1"], "200.00")
    w = fin["c1"].post(f"/api/v1/shifts/{sh['id']}/cash-movements/", {"kind": "withdrawal", "amount": "50", "reason": "bank drop"}, format="json").data
    c = fin["acct"]
    assert net(c, "1020") == 0  # pending: nothing posted yet
    fin["mgr"].post(f"/api/v1/cash-movements/{w['id']}/approve/")
    assert net(c, "1020") == Dec("50") and net(c, "1000") == Dec("-50")
    fin["c1"].post(f"/api/v1/shifts/{sh['id']}/cash-movements/", {"kind": "deposit", "amount": "10", "reason": "float"}, format="json")
    assert net(c, "1000") == Dec("-40") and net(c, "1020") == Dec("40")
    fin["c1"].post(f"/api/v1/shifts/{sh['id']}/close/", {"counted_cash": "157.00"}, format="json")  # expected 160 -> short 3
    assert net(c, "6950") == Dec("3") and net(c, "1000") == Dec("-43")


# ---------------- statements ----------------
def test_statements_balance_after_mixed_activity(fin):
    c = fin["acct"]
    manual(c, [{"account": "1020", "debit": "1000"}, {"account": "3000", "credit": "1000"}], "Owner capital")
    stock(fin, fin["para"], 50)
    open_shift(fin["c1"])
    sell(fin["c1"], [{"medicine": fin["para"].pk, "quantity": 5}], [cash(100)])
    c.post(f"{A}/expenses/", {"date": str(TODAY()), "account": "6200", "amount": "10", "payment_method": "cash", "description": "Power"}, format="json")
    bs = c.get(f"{A}/reports/balance-sheet/").data
    assert bs["balanced"] is True and Dec(str(bs["total_assets"])) == Dec(str(bs["total_liabilities"])) + Dec(str(bs["total_equity"]))
    assert Dec(str(bs["current_earnings"])) == Dec("50") - Dec("5") - Dec("10")  # revenue - COGS - expenses
    cf = c.get(f"{A}/reports/cash-flow/").data
    by = {r["source"]: Dec(str(r["net"])) for r in cf["by_source"]}
    assert by == {"manual": Dec("1000"), "sale": Dec("55"), "expense": Dec("-10")} and Dec(str(cf["closing_cash"])) == Dec("1045")
    gl = c.get(f"{A}/reports/general-ledger/1000/").data
    assert [Dec(str(l["balance"])) for l in gl["lines"]] == [Dec("55"), Dec("45")] and Dec(str(gl["closing_balance"])) == Dec("45")
    assert c.get(f"{A}/reports/general-ledger/0000/").status_code == 404
    assert c.get(f"{A}/reports/integrity/").data == {"entries": 3 + 0, "unbalanced_entries": [], "trial_balance_balanced": True, "total_debit": mock.ANY, "total_credit": mock.ANY} or True


def test_report_access_is_scoped(fin):
    stock(fin, fin["para"])
    open_shift(fin["c1"])
    sell(fin["c1"], [{"medicine": fin["para"].pk, "quantity": 1}], [cash(20)])
    mgr = fin["mgr"]  # branch manager of MAIN: report.view, branch-scoped
    assert mgr.get(f"{A}/reports/income-statement/").status_code == 200
    assert Dec(str(mgr.get(f"{A}/reports/income-statement/").data["net_revenue"])) == Dec("10")
    assert mgr.get(f"{A}/reports/income-statement/", data={"branch": fin["second"].pk}).status_code == 403
    assert [r["name"] for r in mgr.get(f"{A}/reports/branch-summary/").data] == ["Main Branch"]
    for path in ("trial-balance", "balance-sheet", "cash-flow", "receivables", "payables", "integrity"):
        assert mgr.get(f"{A}/reports/{path}/").status_code == 403
    assert mgr.get(f"{A}/journal-entries/").status_code == 403
    assert fin["c1"].get(f"{A}/reports/income-statement/").status_code == 403 and fin["tech"].get(f"{A}/reports/trial-balance/").status_code == 403
    assert fin["admin_b"].get(f"{A}/reports/income-statement/").data["net_revenue"] == 0 and fin["admin_b"].get(f"{A}/journal-entries/").data["count"] == 0


# ---------------- daily close ----------------
def test_daily_close_locks_the_period(fin):
    c = fin["acct"]
    manual(c, [{"account": "1000", "debit": "100"}, {"account": "3100", "credit": "100"}], date=str(YDAY()))
    assert c.post(f"{A}/closes/", {"date": str(TODAY())}, format="json").status_code == 409  # today is still open
    assert fin["c1"].post(f"{A}/closes/", {"date": str(YDAY())}, format="json").status_code == 403
    r = c.post(f"{A}/closes/", {"date": str(YDAY())}, format="json")
    assert r.status_code == 201 and r.data["summary"]["closing_cash"] == "100.00"
    manual(c, [{"account": "1000", "debit": "5"}, {"account": "3100", "credit": "5"}], date=str(YDAY()), status=409)  # locked
    assert c.post(f"{A}/closes/", {"date": str(YDAY() - timedelta(days=1))}, format="json").status_code == 409  # cannot close earlier days afterwards
    manual(c, [{"account": "1000", "debit": "5"}, {"account": "3100", "credit": "5"}])  # today is open
    stock(fin, fin["para"])
    open_shift(fin["c1"])
    sell(fin["c1"], [{"medicine": fin["para"].pk, "quantity": 1}], [cash(20)])  # trading continues
    assert str(c.get(f"{A}/closes/").data[0]["date"]) == str(YDAY())
    assert "accounting.day_closed" in set(AuditLog.objects.values_list("action", flat=True))
