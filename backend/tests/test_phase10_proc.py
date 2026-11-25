from decimal import Decimal

import pytest

from .test_foundation import api, login, platform_admin, platform_client, register, settled_token, two_pharmacies  # noqa: F401
from .test_phase5 import D, approved_order, env, grn, mk_supplier  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Dec = Decimal
A = "/api/v1/accounting"


def net(c, code):
    rows = {r["code"]: Dec(str(r["debit"])) - Dec(str(r["credit"])) for r in c.get(f"{A}/reports/trial-balance/").data["rows"]}
    return rows.get(code, Dec(0))


def test_purchasing_cycle_posts_inventory_payables_and_cash(env):
    acc, admin = env["acc"], env["admin"]
    sid = mk_supplier(admin)
    po = approved_order(env, sid, qty=100, cost="2.00")  # 200.00
    grn(env["officer"], po, [{"order_item": po["items"][0]["id"], "quantity": 60, "batch_number": "L1", "expiry_date": D(200)}])
    assert net(acc, "1200") == Dec("120") and net(acc, "2000") == Dec("-120")  # goods received, owed to the supplier
    inv = admin.post("/api/v1/procurement/invoices/", {"supplier": sid, "invoice_number": "SI-1", "amount": "120.00", "due_date": D(30)}, format="json").data
    assert net(acc, "2000") == Dec("-120")  # recording the invoice does not double-count the liability
    r = acc.post(f"/api/v1/procurement/invoices/{inv['id']}/pay/", {"amount": "50.00", "method": "bank_transfer", "reference": "P-1"}, format="json")
    assert r.status_code == 201
    assert net(acc, "2000") == Dec("-70") and net(acc, "1020") == Dec("-50")
    pay = acc.get(f"{A}/reports/payables/").data
    assert Dec(str(pay["ledger_balance"])) == Dec("70") and Dec(str(pay["supplier_invoices_outstanding"][0]["outstanding"])) == Dec("70")  # ledger agrees with the sub-ledger
    from apps.core.tenant_context import tenant_context
    from apps.inventory.models import Batch
    with tenant_context(env["g"]):
        bid = Batch.objects.get(batch_number="L1").pk
    env["officer"].post("/api/v1/procurement/returns/", {"batch": bid, "quantity": 10, "reason": "damaged"}, format="json")
    assert net(acc, "1200") == Dec("100") and net(acc, "2000") == Dec("-50")  # 10 units x 2.00 returned
    assert acc.get(f"{A}/reports/integrity/").data["trial_balance_balanced"] is True
    assert acc.get(f"{A}/reports/balance-sheet/").data["balanced"] is True


def test_branch_scoped_staff_cannot_read_the_ledger(env):
    for client in (env["officer"], env["cash"]):
        assert client.get(f"{A}/reports/trial-balance/").status_code == 403
        assert client.get(f"{A}/journal-entries/").status_code == 403
