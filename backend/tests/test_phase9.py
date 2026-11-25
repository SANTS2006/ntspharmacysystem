import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.core import mail
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.consumers import NotificationConsumer
from apps.core.tenant_context import tenant_context
from apps.inventory.tasks import send_stock_alerts
from apps.medicines.models import Medicine
from apps.payments import monime, services
from apps.payments.models import OrderReceipt, PaymentAttempt, PaymentProviderConfig, WebhookEvent
from apps.shop.models import Order

from .test_foundation import api, login, platform_admin, platform_client, register, settled_token, two_pharmacies  # noqa: F401
from .test_phase8 import PW, customer, env, move, order_body, place, signup, stock  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
SECRET = "s" * 40
OTHER_SECRET = "o" * 40
_ev = iter(range(10_000))


@pytest.fixture
def pay(env):
    g = env["g"]
    User.objects.create_user("acc@green.test", PW, tenant=g, full_name="Acc", role=g.roles.get(code="accountant"))
    env["acc"] = api("greenlife", login("greenlife", "acc@green.test", PW).data["tokens"]["access"])
    r = env["admin"].put("/api/v1/payments/config/", {"enabled": True, "space_id": "spc-1", "access_token": "mon_test_TOKEN", "webhook_secret": SECRET}, format="json")
    assert r.status_code == 200, r.data
    stock(env, env["para"])
    return env


def sign(body: bytes, secret=SECRET, t=None):
    t = int(time.time()) if t is None else t
    sig = base64.b64encode(hmac.new(secret.encode(), f"{t}_".encode() + body, hashlib.sha256).digest()).decode()
    return f"t={t},v1={sig}"


def event(session_id, name="checkout_session.completed", eid=None):
    return json.dumps({"apiVersion": "caph.2025-08-23", "event": {"id": eid or f"wke-{next(_ev)}", "name": name, "timestamp": str(int(time.time()))},
                       "object": {"id": session_id, "type": "checkout_session"}, "data": {"id": session_id, "status": "completed"}}).encode()


def post_hook(slug, body, header=None, secret=SECRET):
    return api().generic("POST", f"/api/v1/webhooks/monime/{slug}/", body, content_type="application/json", HTTP_MONIME_SIGNATURE=header if header is not None else sign(body, secret))


def session(status="completed", sid="chk-1", total_minor=None):
    s = {"id": sid, "status": status, "redirectUrl": "https://pay.example/checkout/abc"}
    if total_minor is not None:
        s["lineItems"] = {"data": [{"quantity": 1, "price": {"currency": "SLE", "value": total_minor}}]}
    return s


def start(pay_env, cl, sid="chk-1", items=None):
    body = order_body(pay_env, payment_method="monime", **({"items": items} if items else {}))
    oid = place(cl, body).data["id"]
    with mock.patch.object(monime, "create_checkout_session", return_value=session("pending", sid)) as m:
        r = cl.post(f"/api/v1/shop/orders/{oid}/pay/")
    assert r.status_code == 201, r.data
    return oid, r.data, m


def provider(status="completed", sid="chk-1", total_minor=None):
    return mock.patch.object(monime, "retrieve_checkout_session", return_value=session(status, sid, total_minor))


# ---------------- configuration and secrets ----------------
def test_config_secrets_are_encrypted_and_write_only(env):
    c = env["admin"]
    assert c.put("/api/v1/payments/config/", {"enabled": True}, format="json").status_code == 400  # incomplete
    assert c.put("/api/v1/payments/config/", {"webhook_secret": "short"}, format="json").status_code == 400
    r = c.put("/api/v1/payments/config/", {"space_id": "spc-1", "access_token": "mon_test_SECRETTOKEN", "webhook_secret": SECRET, "enabled": True}, format="json")
    assert r.status_code == 200 and r.data["enabled"] is True and r.data["access_token_set"] is True
    blob = json.dumps(r.data) + json.dumps(c.get("/api/v1/payments/config/").data)
    assert "SECRETTOKEN" not in blob and SECRET not in blob and "access_token\"" not in blob.replace("access_token_set", "")
    row = PaymentProviderConfig.all_objects.get(tenant=env["g"])
    assert "SECRETTOKEN" not in row.access_token_enc and SECRET not in row.webhook_secret_enc and row.access_token_enc
    assert "SECRETTOKEN" not in json.dumps(list(AuditLog.objects.values_list("metadata", flat=True)))
    assert c.put("/api/v1/payments/config/", {"space_id": "spc-2"}, format="json").status_code == 200
    assert services.get_config(env["g"]).access_token == "mon_test_SECRETTOKEN"  # blank keeps the stored secret
    assert env["cash"].get("/api/v1/payments/config/").status_code == 403
    assert env["admin_b"].get("/api/v1/payments/config/").data["access_token_set"] is False  # per pharmacy


# ---------------- signature verification ----------------
def test_signature_verification_rules():
    body = b'{"a":1}'
    now = 1_700_000_000
    good = sign(body, t=now)
    assert monime.verify_signature(SECRET, good, body, now=now + 10)
    assert not monime.verify_signature(OTHER_SECRET, good, body, now=now + 10)
    assert not monime.verify_signature(SECRET, good, body + b" ", now=now + 10)  # tampered body
    assert not monime.verify_signature(SECRET, good, body, now=now + 301)  # too old (replay)
    assert not monime.verify_signature(SECRET, good, body, now=now - 61)  # from the future
    hexsig = hmac.new(SECRET.encode(), f"{now}_".encode() + body, hashlib.sha256).hexdigest()
    assert not monime.verify_signature(SECRET, f"t={now},v1={hexsig}", body, now=now)  # must be base64
    dotted = base64.b64encode(hmac.new(SECRET.encode(), f"{now}.".encode() + body, hashlib.sha256).digest()).decode()
    assert not monime.verify_signature(SECRET, f"t={now},v1={dotted}", body, now=now)  # separator is an underscore
    for bad in ["", "garbage", "t=abc,v1=xx", f"t={now}", "v1=AAAA"]:
        assert not monime.verify_signature(SECRET, bad, body, now=now)
    assert not monime.verify_signature("", good, body, now=now)


# ---------------- starting a payment ----------------
def test_online_method_needs_enabled_provider_and_staff_cannot_confirm_it(env):
    cl = customer(env)
    stock(env, env["para"])
    place(cl, order_body(env, payment_method="monime"), status=400)  # not configured
    env["admin"].put("/api/v1/payments/config/", {"enabled": True, "space_id": "s", "access_token": "t" * 12, "webhook_secret": SECRET}, format="json")
    oid = place(cl, order_body(env, payment_method="monime")).data["id"]
    r = move(env["cash"], oid, "payment_confirmed", 409)
    assert "payment provider" in r.data["error"]["message"]


def test_pay_creates_one_checkout_and_redirect_is_not_proof(pay):
    cl = customer(pay)
    oid, a, m = start(pay, cl)
    assert a["status"] == "pending" and a["redirect_url"].startswith("https://") and a["reference"].startswith("PAY-")
    kw = m.call_args.kwargs
    assert kw["amount_minor"] == 2200 and kw["reference"] == a["reference"] and kw["currency"] == "SLE" and f"/orders/{oid}" in kw["success_url"]
    with mock.patch.object(monime, "create_checkout_session") as m2:
        again = cl.post(f"/api/v1/shop/orders/{oid}/pay/")
        assert again.data["id"] == a["id"] and not m2.called  # reuses the open checkout
    assert cl.get(f"/api/v1/shop/orders/{oid}/").data["status"] == "awaiting_payment"  # the browser coming back changes nothing
    assert cl.get(f"/api/v1/shop/orders/{oid}/payments/").data[0]["status"] == "pending"
    cash_oid = place(cl, order_body(pay)).data["id"]
    assert cl.post(f"/api/v1/shop/orders/{cash_oid}/pay/").status_code == 409
    other = customer(pay, "other@example.com")
    assert other.post(f"/api/v1/shop/orders/{oid}/pay/").status_code == 404
    assert pay["cash"].post(f"/api/v1/shop/orders/{oid}/pay/").status_code == 403


def test_provider_failure_leaves_no_attempt(pay):
    cl = customer(pay)
    oid = place(cl, order_body(pay, payment_method="monime")).data["id"]
    with mock.patch.object(monime, "create_checkout_session", side_effect=monime.ProviderError()):
        assert cl.post(f"/api/v1/shop/orders/{oid}/pay/").status_code == 502
    assert PaymentAttempt.all_objects.count() == 0


# ---------------- webhooks ----------------
def test_verified_webhook_confirms_payment_issues_receipt_and_emails(pay):
    cl = customer(pay)
    oid, a, _ = start(pay, cl)
    body = event("chk-1")
    with provider("completed", total_minor=2200) as p:
        r = post_hook("greenlife", body)
    assert r.status_code == 200 and r.json()["outcome"] == "confirmed" and p.called
    got = cl.get(f"/api/v1/shop/orders/{oid}/").data
    assert got["status"] == "payment_confirmed" and [h["status"] for h in got["history"]][-1] == "payment_confirmed"
    with tenant_context(pay["g"]):
        att = PaymentAttempt.objects.get()
        assert att.status == "completed" and att.completed_at and not att.needs_refund
        rc = OrderReceipt.objects.get()
        assert rc.number.startswith("RC-") and rc.data["total"] == "22.00" and rc.data["payments"][0]["reference"] == att.reference
    subjects = [m.subject for m in mail.outbox]
    assert any("Payment received" in s for s in subjects) and any("Your receipt" in s for s in subjects)  # emailed through the notification service
    assert {"payment.initiated", "payment.confirmed", "order.receipt_issued"} <= set(AuditLog.objects.values_list("action", flat=True))
    rj = cl.get(f"/api/v1/shop/orders/{oid}/receipt/")
    assert rj.status_code == 200 and rj.data["order_reference"].startswith("ORD-")
    pdf = cl.get(f"/api/v1/shop/orders/{oid}/receipt/pdf/")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert customer(pay, "x@example.com").get(f"/api/v1/shop/orders/{oid}/receipt/").status_code == 404
    assert pay["cash"].get(f"/api/v1/orders/{oid}/receipt/").status_code == 200
    assert cl.get("/api/v1/shop/payments/").data["count"] == 1
    with tenant_context(pay["g"]):
        rc = OrderReceipt.objects.get()
        rc.data = {}
        with pytest.raises(PermissionError):
            rc.save()


def test_duplicate_and_replayed_webhooks_cannot_double_confirm(pay):
    cl = customer(pay)
    oid, a, _ = start(pay, cl)
    body = event("chk-1", eid="wke-fixed")
    with provider():
        assert post_hook("greenlife", body).json()["outcome"] == "confirmed"
        again = post_hook("greenlife", body)  # identical redelivery
        assert again.status_code == 200 and again.json()["outcome"] == "duplicate"
        second_event = post_hook("greenlife", event("chk-1"))  # a different event for the same payment
        assert second_event.status_code == 200 and second_event.json()["outcome"] == "duplicate"
    hist = [h["status"] for h in cl.get(f"/api/v1/shop/orders/{oid}/").data["history"]]
    assert hist.count("payment_confirmed") == 1
    with tenant_context(pay["g"]):
        assert OrderReceipt.objects.count() == 1 and PaymentAttempt.objects.filter(status="completed").count() == 1
    assert sum("Payment received" in m.subject for m in mail.outbox) == 1
    assert WebhookEvent.objects.filter(event_id="wke-fixed").count() == 1


def test_forged_unsigned_or_misrouted_webhooks_change_nothing(pay):
    cl = customer(pay)
    oid, a, _ = start(pay, cl)
    body = event("chk-1")
    with provider() as p:
        assert post_hook("greenlife", body, header="").status_code == 400
        assert post_hook("greenlife", body, header="t=1,v1=AAAA").status_code == 400
        assert post_hook("greenlife", body, secret=OTHER_SECRET).status_code == 400  # signed with someone else's secret
        assert post_hook("greenlife", body, header=sign(body, t=int(time.time()) - 3600)).status_code == 400  # replayed old delivery
        assert post_hook("bluecross", body).status_code == 400  # another pharmacy has no such secret/config
        assert post_hook("nosuchslug", body).status_code == 404
        assert api().get("/api/v1/webhooks/monime/greenlife/").status_code == 405
        assert not p.called  # nothing in an unverified body is acted on
    assert cl.get(f"/api/v1/shop/orders/{oid}/").data["status"] == "awaiting_payment"
    assert WebhookEvent.objects.count() == 0 and not OrderReceipt.all_objects.exists()


def test_provider_status_not_webhook_body_decides(pay):
    cl = customer(pay)
    oid, a, _ = start(pay, cl)
    with provider("pending"):
        assert post_hook("greenlife", event("chk-1")).json()["outcome"] == "pending"  # webhook claims completed; provider says otherwise
    assert cl.get(f"/api/v1/shop/orders/{oid}/").data["status"] == "awaiting_payment"
    with provider("completed", total_minor=999):  # provider reports a different amount
        r = post_hook("greenlife", event("chk-1"))
    assert r.json()["outcome"] == "mismatch" and cl.get(f"/api/v1/shop/orders/{oid}/").data["status"] == "awaiting_payment"
    assert "payment.amount_mismatch" in set(AuditLog.objects.values_list("action", flat=True))


def test_provider_outage_returns_503_and_allows_retry(pay):
    cl = customer(pay)
    oid, a, _ = start(pay, cl)
    body = event("chk-1", eid="wke-retry")
    with mock.patch.object(monime, "retrieve_checkout_session", side_effect=monime.ProviderError()):
        assert post_hook("greenlife", body).status_code == 503
    assert WebhookEvent.objects.count() == 0  # not recorded, so the provider's retry is processed
    with provider():
        assert post_hook("greenlife", body).json()["outcome"] == "confirmed"


def test_unknown_session_and_other_events_are_acknowledged_and_ignored(pay):
    with provider() as p:
        assert post_hook("greenlife", event("chk-unknown")).json()["outcome"] == "ignored"
        assert post_hook("greenlife", event("x", name="payment.created")).json()["outcome"] == "ignored"
        assert not p.called
    assert post_hook("greenlife", b"not json").status_code == 400


def test_cancelled_payment_can_be_retried(pay):
    cl = customer(pay)
    oid, a, _ = start(pay, cl)
    with provider("cancelled"):
        assert post_hook("greenlife", event("chk-1", "checkout_session.cancelled")).json()["outcome"] == "failed"
    assert cl.get(f"/api/v1/shop/orders/{oid}/payments/").data[0]["status"] == "cancelled"
    assert cl.get(f"/api/v1/shop/orders/{oid}/").data["status"] == "awaiting_payment"
    assert any("not completed" in m.subject for m in mail.outbox)
    with mock.patch.object(monime, "create_checkout_session", return_value=session("pending", "chk-2")):
        r = cl.post(f"/api/v1/shop/orders/{oid}/pay/")
    assert r.status_code == 201 and r.data["id"] != a["id"]
    with provider("completed", "chk-2"):
        assert post_hook("greenlife", event("chk-2")).json()["outcome"] == "confirmed"


def test_payment_after_cancellation_is_flagged_for_refund(pay):
    cl = customer(pay)
    oid, a, _ = start(pay, cl)
    assert cl.post(f"/api/v1/shop/orders/{oid}/cancel/", {}, format="json").data["status"] == "cancelled"
    with provider():
        assert post_hook("greenlife", event("chk-1")).json()["outcome"] == "needs_refund"
    assert cl.get(f"/api/v1/shop/orders/{oid}/").data["status"] == "cancelled" and not OrderReceipt.all_objects.exists()
    rep = pay["acc"].get("/api/v1/payments/reconciliation/").data
    assert len(rep["needs_refund"]) == 1 and rep["by_status"]["completed"]["count"] == 1


# ---------------- reconciliation ----------------
def test_reconciliation_resolves_missed_webhooks(pay):
    cl = customer(pay)
    oid, a, _ = start(pay, cl)
    assert pay["cash"].post("/api/v1/payments/reconcile/", {}, format="json").status_code == 403
    assert pay["acc"].post("/api/v1/payments/reconcile/", {}, format="json").data["checked"] == 0  # too recent
    PaymentAttempt.all_objects.update(created_at=timezone.now() - timedelta(minutes=40))
    assert pay["acc"].get("/api/v1/payments/reconciliation/").data["stale_pending"] == 1
    with provider("pending"):
        assert pay["acc"].post("/api/v1/payments/reconcile/", {}, format="json").data["still_pending"] == 1
    with provider("completed", total_minor=2200):
        res = pay["acc"].post("/api/v1/payments/reconcile/", {}, format="json").data
    assert res["confirmed"] == 1 and cl.get(f"/api/v1/shop/orders/{oid}/").data["status"] == "payment_confirmed"
    with provider("completed"):
        assert pay["acc"].post("/api/v1/payments/reconcile/", {}, format="json").data["checked"] == 0  # nothing pending any more
    from apps.payments.tasks import reconcile_all
    assert reconcile_all() == {"greenlife": {"checked": 0, "confirmed": 0, "failed": 0, "still_pending": 0, "errors": 0}}


def test_staff_attempt_listing_is_branch_scoped(pay):
    cl = customer(pay)
    start(pay, cl)
    assert pay["cash"].get("/api/v1/payments/attempts/").data["count"] == 1
    assert pay["cash2"].get("/api/v1/payments/attempts/").data["count"] == 0
    assert pay["admin_b"].get("/api/v1/payments/attempts/").data["count"] == 0
    assert "redirect_url" not in pay["cash"].get("/api/v1/payments/attempts/").data["results"][0]


# ---------------- cash orders get receipts too; refunds ----------------
def test_cash_orders_receive_receipts_at_payment_confirmation(pay):
    cl = customer(pay)
    oid = place(cl, order_body(pay)).data["id"]
    assert cl.get(f"/api/v1/shop/orders/{oid}/receipt/").status_code == 404
    move(pay["cash"], oid, "payment_confirmed")
    assert cl.get(f"/api/v1/shop/orders/{oid}/receipt/").data["payments"][0]["method"] == "cash_on_pickup"


def test_refund_recording_rules(pay):
    cl = customer(pay)
    oid = place(cl, order_body(pay)).data["id"]
    for to in ("payment_confirmed", "processing", "preparing", "ready_for_pickup", "completed"):
        move(pay["cash"], oid, to)
    mgr = pay["admin"]
    body = lambda **kw: {"amount": "10.00", "method": "mobile_money", "reference": "RF-1", "reason": "faulty", **kw}  # noqa: E731
    assert mgr.post(f"/api/v1/orders/{oid}/refund/", body(), format="json").status_code == 409  # no refund request yet
    cl.post(f"/api/v1/shop/orders/{oid}/request-refund/", {"reason": "faulty"}, format="json")
    assert pay["cash"].post(f"/api/v1/orders/{oid}/refund/", body(), format="json").status_code == 403
    assert cl.post(f"/api/v1/orders/{oid}/refund/", body(), format="json").status_code == 403
    assert mgr.post(f"/api/v1/orders/{oid}/refund/", body(amount="30"), format="json").status_code == 400  # more than paid (22.00)
    assert mgr.post(f"/api/v1/orders/{oid}/refund/", body(reference=""), format="json").status_code == 400
    part = mgr.post(f"/api/v1/orders/{oid}/refund/", body(), format="json")
    assert part.status_code == 201 and part.data["order"]["status"] == "refund_requested"  # partial refund keeps it open
    assert mgr.post(f"/api/v1/orders/{oid}/refund/", body(), format="json").status_code == 400  # duplicate reference
    assert mgr.post(f"/api/v1/orders/{oid}/refund/", body(amount="13", reference="RF-2"), format="json").status_code == 400  # exceeds remaining 12.00
    full = mgr.post(f"/api/v1/orders/{oid}/refund/", body(amount="12.00", reference="RF-2"), format="json")
    assert full.data["order"]["status"] == "refunded"
    assert any("Refund confirmation" in m.subject for m in mail.outbox)
    assert "order.refunded" in set(AuditLog.objects.values_list("action", flat=True))


# ---------------- stock alert emails ----------------
def test_daily_stock_alert_emails(pay):
    with tenant_context(pay["g"]):
        Medicine.objects.filter(pk=pay["para"].pk).update(reorder_level=100)
    g = pay["g"]
    User.objects.create_user("bm@green.test", PW, tenant=g, full_name="BM", role=g.roles.get(code="branch_manager"), branch=pay["main"])
    before = len(mail.outbox)
    sent = send_stock_alerts()
    msgs = mail.outbox[before:]
    assert sent == 3 and {m.to[0] for m in msgs} == {"a@green.test", "bm@green.test"}  # admin: both branches; branch manager: Main only
    assert "Paracetamol" in msgs[0].body and "LOW STOCK" in msgs[0].body
    assert [m.to[0] for m in msgs if "Second" in m.subject] == ["a@green.test"]  # the manager of Main never hears about the other branch
    assert not any(m.to == ["a@blue.test"] for m in msgs)


# ---------------- real-time ----------------
def token_for(email, slug="greenlife"):
    return login(slug, email, PW).data["tokens"]["access"]


async def connect(token=None, timeout=3):
    comm = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
    ok, _ = await comm.connect()
    assert ok
    if token:
        await comm.send_json_to({"type": "auth", "token": token})
    return comm


async def drain(comm, wait=0.3):
    """Collect everything currently queued. receive_nothing never cancels the application (a timed-out receive_from would)."""
    out = []
    while not await comm.receive_nothing(timeout=wait, interval=0.05):
        out.append(await comm.receive_json_from())
    return out


def test_websocket_rejects_unauthenticated_and_invalid_tokens(env):
    ptoken = api().post("/api/v1/auth/login/", {"email": "root@platform.test", "password": "Root-Passw0rd-123!"}, format="json").data["tokens"]["access"]

    async def run():
        c = await connect("not-a-token")
        out = await c.receive_output(timeout=3)
        assert out["type"] == "websocket.close" and out["code"] == 4401
        with mock.patch.object(NotificationConsumer, "AUTH_TIMEOUT", 0.2):
            c2 = await connect()
            out = await c2.receive_output(timeout=3)
            assert out["type"] == "websocket.close" and out["code"] == 4401  # never authenticated
        platform = await connect(ptoken)
        out = await platform.receive_output(timeout=3)
        assert out["type"] == "websocket.close"  # platform admins have no tenant feed

    async_to_sync(run)()


def test_websocket_events_are_tenant_branch_and_permission_scoped(pay):
    cust_a, cust_b = customer(pay, "a@example.com"), customer(pay, "b@example.com")
    tok = lambda c: c._credentials["HTTP_AUTHORIZATION"].split()[1]  # noqa: E731
    g = pay["g"]
    User.objects.create_user("ph2@green.test", PW, tenant=g, full_name="ph2", role=g.roles.get(code="pharmacist"), branch=pay["second"])

    tokens = [token_for("cash@green.test"), token_for("cash2@green.test"), tok(pay["admin"]), token_for("tech@green.test"), tok(cust_a), tok(cust_b), tok(pay["admin_b"])]

    async def run():
        cash, cash2, admin_c, tech, cust1, cust2, blue = [await connect(t) for t in tokens]
        for c in (cash, cash2, admin_c, tech, cust1, cust2, blue):
            assert (await c.receive_json_from(timeout=3))["type"] == "ready"
        order_id = await sync_to_async(lambda: place(cust_a, order_body(pay)).data["id"])()  # branch MAIN, customer A
        got = {n: await drain(c) for n, c in dict(cash=cash, cash2=cash2, admin=admin_c, tech=tech, cust1=cust1, cust2=cust2, blue=blue).items()}
        ev = lambda lst: [e for e in lst if e["event"].startswith("order.")]  # noqa: E731
        assert any(e["event"] == "order.created" and e["data"]["id"] == order_id for e in ev(got["cash"]))  # branch staff
        assert ev(got["admin"]) and ev(got["cust1"])  # pharmacy-level staff and the owner
        assert not ev(got["cash2"]) and not ev(got["tech"]) and not ev(got["cust2"]) and not ev(got["blue"])  # other branch, no permission, other customer, other pharmacy
        for lst in got.values():
            for e in lst:
                assert set(e["data"]) <= {"id", "reference", "status", "kind", "name", "available", "medicine", "order"}  # ids only: no names/addresses/contacts
        await sync_to_async(lambda: move(pay["cash"], order_id, "payment_confirmed"))()
        again = await drain(cust1)
        assert any(e["event"] == "order.updated" and e["data"]["status"] == "payment_confirmed" for e in again)
        assert not [e for e in await drain(cust2) if e["event"].startswith("order.")]
        for c in (cash, cash2, admin_c, tech, cust1, cust2, blue):
            await c.disconnect()
    async_to_sync(run)()


def test_websocket_prescription_and_inventory_topics(pay):
    from apps.inventory import services as inv
    tokens = [token_for("ph@green.test"), token_for("tech@green.test"), token_for("cash@green.test")]

    async def run():
        ph, tech, cash = [await connect(t) for t in tokens]
        for c in (ph, tech, cash):
            await c.receive_json_from(timeout=3)

        def trigger():
            with tenant_context(pay["g"]):
                Medicine.objects.filter(pk=pay["para"].pk).update(reorder_level=60)
                inv.deduct_fefo(medicine=Medicine.objects.get(pk=pay["para"].pk), branch=pay["main"], quantity=5, user=User.objects.get(email="ph@green.test"), ref_type="test")
            pid = pay["tech"].post("/api/v1/patients/", {"full_name": "P"}, format="json").data["id"]
            pay["tech"].post("/api/v1/prescriptions/", {"patient": pid, "branch": pay["main"].pk, "prescriber_name": "Dr", "prescription_date": str(timezone.localdate() - timedelta(days=1)),
                                                        "items": [{"medicine": pay["amox"].pk, "dosage": "1", "frequency": "1", "quantity_prescribed": 1}]}, format="json")
        await sync_to_async(trigger)()
        p, t, c = await drain(ph), await drain(tech), await drain(cash)
        assert {e["event"] for e in p} >= {"inventory.low_stock", "prescription.created"}
        assert {e["event"] for e in t} == {"prescription.created", "inventory.low_stock"}  # technicians hold prescription.view and inventory.view
        assert c == []  # cashiers have neither
        for x in (ph, tech, cash):
            await x.disconnect()
    async_to_sync(run)()
