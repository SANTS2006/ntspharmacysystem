from decimal import Decimal
from unittest import mock

import pytest

from .test_foundation import api, login, platform_admin, platform_client, register, settled_token, two_pharmacies  # noqa: F401
from .test_phase8 import customer, env, move, order_body, place, signup, stock  # noqa: F401
from .test_phase9 import event, pay, post_hook, provider, start  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Dec = Decimal
A = "/api/v1/accounting"


def net(c, code):
    rows = {r["code"]: Dec(str(r["debit"])) - Dec(str(r["credit"])) for r in c.get(f"{A}/reports/trial-balance/").data["rows"]}
    return rows.get(code, Dec(0))


def run_to_completion(env_, oid, c):
    for to in ("processing", "preparing", "ready_for_pickup", "completed"):
        move(c, oid, to)


def test_cash_on_pickup_order_defers_revenue_until_fulfilment(env):
    stock(env, env["para"])
    cl = customer(env)
    oid = place(cl, order_body(env)).data["id"]  # 2 x 10 + 10% tax = 22
    admin = env["admin"]
    assert net(admin, "1000") == 0
    move(env["cash"], oid, "payment_confirmed")
    assert net(admin, "1000") == Dec("22") and net(admin, "2200") == Dec("-22")
    assert Dec(str(admin.get(f"{A}/reports/income-statement/").data["net_revenue"])) == 0  # cash received is not yet revenue
    for to in ("processing", "preparing", "ready_for_pickup"):
        move(env["cash"], oid, to)
    assert net(admin, "4000") == 0
    move(env["cash"], oid, "completed")
    pl = admin.get(f"{A}/reports/income-statement/").data
    assert (Dec(str(pl["net_revenue"])), Dec(str(pl["cost_of_sales_total"]))) == (Dec("20"), Dec("2"))
    assert net(admin, "2200") == 0 and net(admin, "2100") == Dec("-2")
    assert admin.get(f"{A}/reports/balance-sheet/").data["balanced"] is True
    move(env["cash"], oid, "completed", 409)
    assert len(admin.get(f"{A}/journal-entries/", data={"source_type": "order_revenue"}).data["results"]) == 1  # recognised once


def test_refund_after_recognition_hits_returns_account(env):
    stock(env, env["para"])
    cl = customer(env)
    oid = place(cl, order_body(env)).data["id"]
    move(env["cash"], oid, "payment_confirmed")
    run_to_completion(env, oid, env["cash"])
    cl.post(f"/api/v1/shop/orders/{oid}/request-refund/", {"reason": "faulty"}, format="json")
    r = env["admin"].post(f"/api/v1/orders/{oid}/refund/", {"amount": "22.00", "method": "cash", "reference": "RF-1", "reason": "faulty"}, format="json")
    assert r.status_code == 201
    admin = env["admin"]
    assert net(admin, "4950") == Dec("20") and net(admin, "2100") == 0 and net(admin, "1000") == 0
    assert Dec(str(admin.get(f"{A}/reports/income-statement/").data["net_revenue"])) == 0


def test_refund_before_recognition_unwinds_the_prepayment(env):
    stock(env, env["para"])
    cl = customer(env)
    oid = place(cl, order_body(env)).data["id"]
    move(env["cash"], oid, "payment_confirmed")
    move(env["cash"], oid, "refund_requested")
    env["admin"].post(f"/api/v1/orders/{oid}/refund/", {"amount": "22.00", "method": "cash", "reference": "RF-2", "reason": "cancelled by pharmacy"}, format="json")
    assert net(env["admin"], "2200") == 0 and net(env["admin"], "1000") == 0 and net(env["admin"], "4000") == 0
    assert env["cash"].post(f"/api/v1/orders/{oid}/transition/", {"status": "cancelled"}, format="json").status_code == 409


def test_paid_orders_cannot_be_plainly_cancelled(env):
    stock(env, env["para"])
    cl = customer(env)
    oid = place(cl, order_body(env)).data["id"]
    move(env["cash"], oid, "payment_confirmed")
    move(env["cash"], oid, "cancelled", 409)  # must go through a refund request so the money is accounted for


def test_online_payment_is_held_in_clearing_until_fulfilment(pay):
    cl = customer(pay)
    oid, a, _ = start(pay, cl)
    with provider("completed", total_minor=2200):
        assert post_hook("greenlife", event("chk-1")).json()["outcome"] == "confirmed"
    admin = pay["admin"]
    assert net(admin, "1010") == Dec("22") and net(admin, "2200") == Dec("-22") and net(admin, "4000") == 0
    run_to_completion(pay, oid, pay["cash"])
    assert net(admin, "2200") == 0 and net(admin, "4000") == Dec("-20")
    assert admin.get(f"{A}/reports/integrity/").data["trial_balance_balanced"] is True


def test_payment_after_cancellation_becomes_a_refund_liability(pay):
    cl = customer(pay)
    oid, a, _ = start(pay, cl)
    cl.post(f"/api/v1/shop/orders/{oid}/cancel/", {}, format="json")
    with provider("completed"):
        assert post_hook("greenlife", event("chk-1")).json()["outcome"] == "needs_refund"
    admin = pay["admin"]
    assert net(admin, "1010") == Dec("22") and net(admin, "2250") == Dec("-22") and net(admin, "4000") == 0
