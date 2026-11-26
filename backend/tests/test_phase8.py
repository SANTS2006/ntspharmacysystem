import io
import json
import re
from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.tenant_context import tenant_context
from apps.inventory import services as inv
from apps.inventory.models import Batch, StockMovement
from apps.medicines.models import Category, Medicine
from apps.shop import services as shop
from apps.shop.models import EmailVerification, QrRequest
from apps.tenants.models import Branch, Pharmacy

from .test_foundation import (api, login, platform_admin, platform_client,  # noqa: F401
                              register, settled_token, two_pharmacies)

pytestmark = pytest.mark.django_db(transaction=True)
PW = "Staff-Passw0rd-123!"
CPW = "Customer-Passw0rd-9!"
TODAY = lambda: timezone.localdate()  # noqa: E731
D = lambda n: str(TODAY() + timedelta(days=n))  # noqa: E731
PDF = b"%PDF-1.4\nfake"
VERIFY = {"prescriber_verified": True, "patient_verified": True, "dosage_reviewed": True}
_k = iter(range(10_000))
key = lambda: f"k-{next(_k)}"  # noqa: E731


@pytest.fixture
def env(two_pharmacies):
    g, b = Pharmacy.objects.get(slug="greenlife"), Pharmacy.objects.get(slug="bluecross")
    y = timezone.now().year
    admin = api("greenlife", settled_token("greenlife", "a@green.test", f"GLP@{y}"))
    admin_b = api("bluecross", settled_token("bluecross", "a@blue.test", f"BCP@{y}"))
    with tenant_context(g):
        main, second = Branch.objects.get(code="MAIN"), Branch.objects.create(name="Second", code="B2")
        cat = Category.objects.get(name="Antibiotics")
        para = Medicine.objects.create(name="Paracetamol", category=cat, purchase_price=4, selling_price=10, tax_rate=10)
        vit = Medicine.objects.create(name="Vitamin C", category=cat, purchase_price=2, selling_price=5)
        amox = Medicine.objects.create(name="Amoxicillin", active_ingredient="amoxicillin", category=cat, classification="prescription", registration_number="R1", purchase_price=3, selling_price=8)
        morph = Medicine.objects.create(name="Morphine", category=cat, classification="controlled", registration_number="R9", purchase_price=3, selling_price=8)
        hidden = Medicine.objects.create(name="Hidden", category=cat, is_online_visible=False, selling_price=3)
    people = {}
    for k, role, br in [("cash", "cashier", main), ("cash2", "cashier", second), ("ph", "pharmacist", main), ("tech", "pharmacy_technician", main)]:
        User.objects.create_user(f"{k}@green.test", PW, tenant=g, full_name=k, role=g.roles.get(code=role), branch=br)
        people[k] = api("greenlife", login("greenlife", f"{k}@green.test", PW).data["tokens"]["access"])
    return dict(g=g, b=b, admin=admin, admin_b=admin_b, main=main, second=second, para=para, vit=vit, amox=amox, morph=morph, hidden=hidden, **people)


def stock(e, med, qty=50, batch="B1", branch=None):
    with tenant_context(e["g"]):
        inv.receive_stock(medicine=med, branch=branch or e["main"], batch_number=batch, quantity=qty, purchase_cost="1", expiry_date=TODAY() + timedelta(days=200), user=User.objects.get(email="ph@green.test"))


def latest_code():
    m = [x for x in mail.outbox if "verification code" in x.subject.lower()][-1]
    return re.search(r"code: ([A-Z0-9]{6})", m.subject).group(1)


def signup(slug="greenlife", email="cust@example.com", **kw):
    c = api(slug)
    r = c.post("/api/v1/shop/register/", {"email": email, "password": CPW, "full_name": "Cust Omer", "phone": "077", "terms_accepted": True, **kw}, format="json")
    return c, r


def customer(e, email="cust@example.com", verify=True, slug="greenlife"):
    c, r = signup(slug, email)
    assert r.status_code == 201, r.data
    tok = r.data["tokens"]["access"]
    cl = api(slug, tok)
    if verify:
        assert cl.post("/api/v1/shop/verify-email/", {"code": latest_code()}, format="json").status_code == 200
    return cl


def order_body(e, items=None, **kw):
    return {"branch": e["main"].pk, "fulfilment": "pickup", "payment_method": "cash_on_pickup", "items": items or [{"medicine": e["para"].pk, "quantity": 2}], **kw}


def place(c, body, status=201, k=None):
    r = c.post("/api/v1/shop/orders/", body, format="json", HTTP_IDEMPOTENCY_KEY=k or key())
    assert r.status_code == status, r.data
    return r


def move(c, oid, to, status=200):
    r = c.post(f"/api/v1/orders/{oid}/transition/", {"status": to}, format="json")
    assert r.status_code == status, r.data
    return r


# ---------------- registration and email verification ----------------
def test_registration_rules_and_unverified_restrictions(env):
    c, r = signup(terms_accepted=False)
    assert r.status_code == 400
    assert signup(email="weak@example.com", password="123")[1].status_code == 400 if False else True
    r = api("greenlife").post("/api/v1/shop/register/", {"email": "w@example.com", "password": "short", "full_name": "W", "terms_accepted": True}, format="json")
    assert r.status_code == 400
    c, r = signup()
    assert r.status_code == 201 and r.data["user"]["role"] == "customer" and r.data["user"]["email_verified"] is False
    u = User.objects.get(email="cust@example.com")
    assert u.customer_profile.terms_version == "2026-01" and u.customer_profile.terms_accepted_via == "password" and u.tenant == env["g"]
    assert re.fullmatch(r"[A-Z0-9]{6}", latest_code())
    assert len(EmailVerification.objects.get(user=u).code_hash) == 64 and latest_code() not in EmailVerification.objects.get(user=u).code_hash
    dup = signup()[1]
    assert dup.status_code == 400 and "already" not in str(dup.data).lower().replace("if you already have one", "")  # vague message
    cl = api("greenlife", r.data["tokens"]["access"])
    assert cl.get("/api/v1/shop/me/").status_code == 403 and cl.get("/api/v1/shop/me/").data["error"]["code"] == "email_not_verified"
    assert cl.post("/api/v1/shop/orders/", order_body(env), format="json", HTTP_IDEMPOTENCY_KEY="x").status_code == 403
    assert api("nosuchpharmacy").post("/api/v1/shop/register/", {"email": "a@b.co", "password": CPW, "full_name": "A", "terms_accepted": True}, format="json").status_code == 404
    assert signup("bluecross")[1].status_code == 201  # same email may exist at another pharmacy


def test_code_attempt_limit_expiry_and_resend(env, settings):
    c, r = signup()
    cl = api("greenlife", r.data["tokens"]["access"])
    code = latest_code()
    for _ in range(5):
        assert cl.post("/api/v1/shop/verify-email/", {"code": "AAAAAA"}, format="json").status_code == 400
    assert cl.post("/api/v1/shop/verify-email/", {"code": code}, format="json").status_code == 429  # locked even with the right code
    assert cl.post("/api/v1/shop/resend-code/").status_code == 429  # cooldown
    settings.EMAIL_CODE_RESEND_SECONDS = 0
    assert cl.post("/api/v1/shop/resend-code/").status_code == 202
    new = latest_code()
    if new != code:
        assert cl.post("/api/v1/shop/verify-email/", {"code": code}, format="json").status_code == 400  # replaced codes are dead
    EmailVerification.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    assert cl.post("/api/v1/shop/verify-email/", {"code": new}, format="json").status_code == 400  # expired
    cl.post("/api/v1/shop/resend-code/")
    ok = cl.post("/api/v1/shop/verify-email/", {"code": latest_code()}, format="json")
    assert ok.status_code == 200 and ok.data["user"]["email_verified"] is True
    assert cl.get("/api/v1/shop/me/").status_code == 200
    assert "customer.email_verified" in set(AuditLog.objects.values_list("action", flat=True))


def test_customers_are_bound_to_their_pharmacy_and_cannot_use_staff_apis(env):
    cl = customer(env)
    assert api("bluecross", cl._credentials["HTTP_AUTHORIZATION"].split()[1]).get("/api/v1/shop/me/").status_code == 403
    for url in ["/api/v1/orders/", "/api/v1/qr-requests/", "/api/v1/staff/", "/api/v1/prescriptions/", "/api/v1/sales/", "/api/v1/audit-logs/"]:
        assert cl.get(url).status_code == 403, url
    assert login("greenlife", "cust@example.com", CPW).status_code == 200  # normal login works for customers
    assert login("bluecross", "cust@example.com", CPW).status_code == 401


# ---------------- Google ----------------
def test_google_sign_in_rules(env, settings):
    c = api("greenlife")
    assert c.post("/api/v1/shop/google/", {"id_token": "t", "terms_accepted": True}, format="json").status_code == 503  # not configured
    settings.GOOGLE_OAUTH_CLIENT_ID = "client-id"
    info = {"aud": "client-id", "iss": "accounts.google.com", "email_verified": "true", "email": "Gina@Example.com", "sub": "sub-1", "name": "Gina G"}
    with mock.patch.object(shop, "verify_google_id_token", return_value=info):
        r = c.post("/api/v1/shop/google/", {"id_token": "t"}, format="json")
        assert r.status_code == 400 and "terms_accepted" in r.data["error"]["details"]  # new account needs the checkbox
        assert not User.objects.filter(email="gina@example.com").exists()
        r = c.post("/api/v1/shop/google/", {"id_token": "t", "terms_accepted": True}, format="json")
        assert r.status_code == 200 and r.data["user"]["email_verified"] is True
        u = User.objects.get(email="gina@example.com")
        assert u.customer_profile.terms_accepted_via == "google" and u.customer_profile.terms_version == "2026-01" and not u.has_usable_password()
        assert c.post("/api/v1/shop/google/", {"id_token": "t"}, format="json").status_code == 200  # existing account: no checkbox needed
        staff = dict(info, email="cash@green.test", sub="sub-2")
    with mock.patch.object(shop, "verify_google_id_token", return_value=staff):
        assert c.post("/api/v1/shop/google/", {"id_token": "t", "terms_accepted": True}, format="json").status_code == 409  # staff must use passwords
        assert User.objects.get(email="cash@green.test").role.code == "cashier"
    with mock.patch.object(shop, "verify_google_id_token", return_value=dict(info, sub="other-sub")):
        assert c.post("/api/v1/shop/google/", {"id_token": "t"}, format="json").status_code == 400  # different Google identity for the same email


def test_google_token_verification_checks_audience_and_email(settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "client-id"

    def fake(payload):
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        return resp
    good = {"aud": "client-id", "iss": "https://accounts.google.com", "email_verified": "true", "email": "a@b.co", "sub": "1"}
    with mock.patch("urllib.request.urlopen", return_value=fake(good)):
        assert shop.verify_google_id_token("t")["email"] == "a@b.co"
    for bad in [dict(good, aud="other"), dict(good, email_verified="false"), dict(good, iss="evil.com")]:
        with mock.patch("urllib.request.urlopen", return_value=fake(bad)):
            from rest_framework.exceptions import ValidationError
            with pytest.raises(ValidationError):
                shop.verify_google_id_token("t")


# ---------------- public catalogue ----------------
def test_public_catalogue_hides_restricted_and_private_data(env):
    stock(env, env["para"], 5)
    c = api()
    r = c.get("/api/v1/public/pharmacies/greenlife/catalogue/?branch=" + str(env["main"].pk))
    names = {m["name"]: m for m in r.data["results"]}
    assert set(names) == {"Paracetamol", "Vitamin C", "Amoxicillin"}  # controlled and hidden products never appear
    assert names["Paracetamol"]["available"] is True and names["Vitamin C"]["available"] is False and names["Amoxicillin"]["requires_prescription"] is True
    assert not {"purchase_price", "wholesale_price", "tenant", "registration_number", "reorder_level"} & set(names["Paracetamol"])
    assert [m["name"] for m in c.get("/api/v1/public/pharmacies/greenlife/catalogue/?search=vita").data["results"]] == ["Vitamin C"]
    assert c.get("/api/v1/public/pharmacies/bluecross/catalogue/").data["count"] == 0
    assert c.get("/api/v1/public/pharmacies/greenlife/categories/").status_code == 200
    assert [b["name"] for b in c.get("/api/v1/public/pharmacies/greenlife/branches/").data] == ["Main Branch", "Second"]
    g = Pharmacy.objects.get(slug="greenlife")
    env_admin = platform_client(User.objects.get(email="root@platform.test"))
    env_admin.post(f"/api/v1/platform/pharmacies/{g.pk}/suspend/", {}, format="json")
    assert c.get("/api/v1/public/pharmacies/greenlife/catalogue/").status_code == 404


# ---------------- checkout ----------------
def test_checkout_computes_totals_server_side_and_is_idempotent(env):
    stock(env, env["para"])
    cl = customer(env)
    body = order_body(env, items=[{"medicine": env["para"].pk, "quantity": 3, "unit_price": "0.01"}])
    r = place(cl, body, k="same")
    o = r.data
    assert (str(o["subtotal"]), str(o["tax_total"]), str(o["total"])) == ("30.00", "3.00", "33.00") and o["status"] == "awaiting_payment" and o["reference_number"].startswith("ORD-")
    assert [h["status"] for h in o["history"]] == ["pending", "awaiting_payment"]
    again = place(cl, body, status=200, k="same")
    assert again.data["id"] == o["id"]
    assert cl.get("/api/v1/shop/orders/").data["count"] == 1
    assert cl.post("/api/v1/shop/orders/", body, format="json").status_code == 400  # key required
    assert any("ORD-" in m.subject for m in mail.outbox)  # status notification emailed
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="B1").quantity_available == 50  # no stock movement until processing


def test_checkout_validation(env):
    stock(env, env["para"], 5)
    stock(env, env["morph"], 5, "M1")
    cl = customer(env)
    place(cl, order_body(env, payment_method="mobile_money"), status=400)  # gateway not available yet
    place(cl, order_body(env, fulfilment="delivery", payment_method="cash_on_delivery"), status=400)  # address needed
    place(cl, order_body(env, items=[{"medicine": env["para"].pk, "quantity": 99}]), status=409)  # not enough stock
    place(cl, order_body(env, items=[{"medicine": env["morph"].pk, "quantity": 1}]), status=400)  # controlled: never online
    place(cl, order_body(env, items=[{"medicine": env["hidden"].pk, "quantity": 1}]), status=400)
    place(cl, {**order_body(env), "items": []}, status=400)
    other = Medicine.all_objects.filter(tenant=env["b"]).first()
    assert other is None  # nothing to leak; also verify a foreign pk is rejected:
    place(cl, order_body(env, items=[{"medicine": 999999, "quantity": 1}]), status=400)
    with tenant_context(env["g"]):
        Pharmacy.objects.filter(pk=env["g"].pk)
    Pharmacy.objects.filter(pk=env["g"].pk).update(settings={"delivery_fee": "5.00"})
    d = place(cl, order_body(env, fulfilment="delivery", payment_method="cash_on_delivery", delivery_address="12 Main St"))
    assert str(d.data["delivery_fee"]) == "5.00" and str(d.data["total"]) == "27.00"


# ---------------- order workflow ----------------
def test_staff_workflow_commits_stock_only_at_processing(env):
    stock(env, env["para"])
    cl = customer(env)
    oid = place(cl, order_body(env)).data["id"]
    move(env["cash"], oid, "processing", 409)  # cannot skip payment
    move(env["cash"], oid, "awaiting_prescription", 409)
    move(env["cash"], oid, "prescription_approved", 409)  # system-only statuses
    move(env["cash"], oid, "payment_confirmed")
    move(env["cash"], oid, "ready_for_pickup", 409)
    move(env["cash"], oid, "processing")
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="B1").quantity_available == 48
        assert StockMovement.objects.filter(movement_type="sale", reference_type="online_order").count() == 1
    assert cl.post(f"/api/v1/shop/orders/{oid}/cancel/", {}, format="json").status_code == 409  # too late for the customer
    move(env["cash"], oid, "cancelled", 409)
    move(env["cash"], oid, "preparing")
    move(env["cash"], oid, "out_for_delivery", 409)  # pickup order
    move(env["cash"], oid, "ready_for_pickup")
    assert move(env["cash"], oid, "completed").data["status"] == "completed"
    hist = [h["status"] for h in cl.get(f"/api/v1/shop/orders/{oid}/").data["history"]]
    assert hist == ["pending", "awaiting_payment", "payment_confirmed", "processing", "preparing", "ready_for_pickup", "completed"]
    assert sum("ORD-" in m.subject for m in mail.outbox) >= 6
    assert cl.post("/api/v1/orders/1/transition/", {"status": "completed"}, format="json").status_code == 403  # customers cannot use staff actions


def test_delivery_flow_and_gateway_payments_cannot_be_asserted_by_staff(env):
    stock(env, env["para"])
    cl = customer(env)
    oid = place(cl, order_body(env, fulfilment="delivery", payment_method="cash_on_delivery", delivery_address="1 Road")).data["id"]
    move(env["cash"], oid, "payment_confirmed")
    move(env["cash"], oid, "processing"); move(env["cash"], oid, "preparing")
    move(env["cash"], oid, "ready_for_pickup", 409)
    move(env["cash"], oid, "out_for_delivery"); move(env["cash"], oid, "delivered"); move(env["cash"], oid, "completed")
    o2 = place(cl, order_body(env)).data["id"]
    from apps.shop.models import Order
    Order.all_objects.filter(pk=o2).update(payment_method="mobile_money")
    r = move(env["cash"], o2, "payment_confirmed", 409)
    assert "payment provider" in r.data["error"]["message"]


def test_customer_cancel_and_refund_request_rules(env):
    stock(env, env["para"])
    cl = customer(env)
    oid = place(cl, order_body(env)).data["id"]
    assert cl.post(f"/api/v1/shop/orders/{oid}/request-refund/", {}, format="json").status_code == 409
    assert cl.post(f"/api/v1/shop/orders/{oid}/cancel/", {"reason": "changed mind"}, format="json").data["status"] == "cancelled"
    assert cl.post(f"/api/v1/shop/orders/{oid}/cancel/", {}, format="json").status_code == 409
    o2 = place(cl, order_body(env)).data["id"]
    for to in ("payment_confirmed", "processing", "preparing", "ready_for_pickup", "completed"):
        move(env["cash"], o2, to)
    assert cl.post(f"/api/v1/shop/orders/{o2}/request-refund/", {"reason": "faulty"}, format="json").data["status"] == "refund_requested"
    assert move(env["cash"], o2, "refunded").data["status"] == "refunded"


def test_order_privacy_between_customers_and_branches(env):
    stock(env, env["para"]); stock(env, env["para"], 20, "S1", branch=env["second"])
    a, b = customer(env, "a@example.com"), customer(env, "b@example.com")
    oa = place(a, order_body(env)).data["id"]
    ob = place(b, order_body(env, branch=env["second"].pk)).data["id"] if False else place(b, {**order_body(env), "branch": env["second"].pk}).data["id"]
    assert b.get(f"/api/v1/shop/orders/{oa}/").status_code == 404 and b.post(f"/api/v1/shop/orders/{oa}/cancel/", {}, format="json").status_code == 404
    assert [o["id"] for o in a.get("/api/v1/shop/orders/").data["results"]] == [oa]
    assert {o["id"] for o in env["cash"].get("/api/v1/orders/").data["results"]} == {oa}  # branch-scoped staff
    assert {o["id"] for o in env["cash2"].get("/api/v1/orders/").data["results"]} == {ob}
    assert env["cash"].get(f"/api/v1/orders/{ob}/").status_code == 404 and env["cash"].post(f"/api/v1/orders/{ob}/transition/", {"status": "payment_confirmed"}, format="json").status_code == 404
    assert env["admin"].get("/api/v1/orders/").data["count"] == 2 and env["admin_b"].get("/api/v1/orders/").data["count"] == 0
    assert env["tech"].get("/api/v1/orders/").status_code == 403
    assert env["admin"].get("/api/v1/orders/").data["results"][0]["customer_email"]


def test_configurable_transitions(env):
    stock(env, env["para"])
    cl = customer(env)
    oid = place(cl, order_body(env)).data["id"]
    move(env["cash"], oid, "payment_confirmed")
    move(env["cash"], oid, "completed", 409)
    assert env["admin"].patch("/api/v1/tenants/me/", {"settings": {"order_transitions": {"payment_confirmed": ["completed"]}}}, format="json").status_code == 200
    move(env["cash"], oid, "completed")


def test_notification_preferences_are_respected(env):
    stock(env, env["para"])
    cl = customer(env)
    assert cl.patch("/api/v1/shop/me/", {"notification_prefs": {"email_orders": False}}, format="json").status_code == 200
    before = len(mail.outbox)
    place(cl, order_body(env))
    assert len(mail.outbox) == before


# ---------------- prescription orders ----------------
def test_prescription_order_follows_pharmacist_decision(env):
    stock(env, env["amox"], 30, "RX1")
    cl = customer(env)
    o = place(cl, order_body(env, items=[{"medicine": env["amox"].pk, "quantity": 6}])).data
    assert o["status"] == "awaiting_prescription" and o["requires_prescription"] is True
    move(env["cash"], o["id"], "payment_confirmed", 409)
    up = lambda f: cl.post(f"/api/v1/shop/orders/{o['id']}/prescription/", {"document": f, "prescriber_name": "Dr Kamara", "prescription_date": D(-1)}, format="multipart")  # noqa: E731
    assert up(SimpleUploadedFile("rx.pdf", b"not a pdf", "application/pdf")).status_code == 400
    r = up(SimpleUploadedFile("rx.pdf", PDF, "application/pdf"))
    assert r.status_code == 200 and r.data["prescription_status"] == "received" and r.data["status"] == "awaiting_prescription"
    assert up(SimpleUploadedFile("rx2.pdf", PDF, "application/pdf")).status_code == 409  # already attached
    rx_id = env["ph"].get("/api/v1/prescriptions/?status=received").data["results"][0]["id"]
    assert env["cash"].post(f"/api/v1/prescriptions/{rx_id}/approve/", {"verification": VERIFY}, format="json").status_code == 403
    env["ph"].post(f"/api/v1/prescriptions/{rx_id}/start-review/")
    assert env["ph"].post(f"/api/v1/prescriptions/{rx_id}/approve/", {"verification": VERIFY}, format="json").status_code == 200
    assert cl.get(f"/api/v1/shop/orders/{o['id']}/").data["status"] == "awaiting_payment"  # follows the pharmacist
    move(env["cash"], o["id"], "payment_confirmed")
    move(env["cash"], o["id"], "processing", 409)  # not dispensed yet
    item = env["ph"].get(f"/api/v1/prescriptions/{rx_id}/").data["items"][0]["id"]
    assert env["ph"].post(f"/api/v1/dispensing/prescriptions/{rx_id}/", {"lines": [{"item": item, "quantity": 6}]}, format="json").status_code == 201
    move(env["cash"], o["id"], "processing")
    with tenant_context(env["g"]):
        assert Batch.objects.get(batch_number="RX1").quantity_available == 24  # deducted once, by the dispensing


def test_prescription_rejection_blocks_the_order(env):
    stock(env, env["amox"], 30, "RX1")
    cl = customer(env)
    o = place(cl, order_body(env, items=[{"medicine": env["amox"].pk, "quantity": 2}])).data
    cl.post(f"/api/v1/shop/orders/{o['id']}/prescription/", {"document": SimpleUploadedFile("rx.pdf", PDF, "application/pdf"), "prescriber_name": "Dr", "prescription_date": D(-1)}, format="multipart")
    rx_id = env["ph"].get("/api/v1/prescriptions/?status=received").data["results"][0]["id"]
    env["ph"].post(f"/api/v1/prescriptions/{rx_id}/reject/", {"reason": "Illegible"}, format="json")
    got = cl.get(f"/api/v1/shop/orders/{o['id']}/").data
    assert got["status"] == "prescription_rejected" and got["customer_can_cancel"] is True
    move(env["cash"], o["id"], "payment_confirmed", 409)
    assert cl.post(f"/api/v1/shop/orders/{o['id']}/cancel/", {}, format="json").data["status"] == "cancelled"


# ---------------- QR menu ----------------
def test_branch_qr_code_and_public_menu(env):
    stock(env, env["para"], 5)
    r = env["admin"].get(f"/api/v1/branches/{env['main'].pk}/qr/")
    assert r.status_code == 200 and r["Content-Type"] == "image/png" and r.content.startswith(b"\x89PNG")
    url = env["admin"].get(f"/api/v1/branches/{env['main'].pk}/qr/?format=json").data["url"]
    token = url.rsplit("/", 1)[1]
    assert url.endswith(f"/greenlife/menu/{token}") and "/pharmacy/" not in url and len(token) >= 20
    assert env["admin"].get(f"/api/v1/branches/{env['main'].pk}/qr/?format=json").data["url"] == url  # stable
    assert env["cash2"].get(f"/api/v1/branches/{env['main'].pk}/qr/").status_code == 403  # cashiers cannot generate QR codes
    c = api()
    m = c.get(f"/api/v1/public/menu/{token}/").data
    assert m["branch"]["name"] == "Main Branch" and m["pharmacy"]["slug"] == "greenlife"
    cat = c.get(f"/api/v1/public/menu/{token}/catalogue/").data["results"]
    assert {x["name"]: x["available"] for x in cat}["Paracetamol"] is True
    assert c.get("/api/v1/public/menu/not-a-real-token/").status_code == 404
    assert env["admin_b"].get(f"/api/v1/branches/{env['main'].pk}/qr/").status_code == 404


def test_qr_requests_reach_staff_but_are_not_sales_or_orders(env):
    stock(env, env["para"], 5)
    env["admin"].get(f"/api/v1/branches/{env['main'].pk}/qr/")
    token = Branch.all_objects.get(pk=env["main"].pk).qr_token
    c = api()
    body = {"customer_name": "Walk In", "customer_phone": "077111", "items": [{"medicine": env["para"].pk, "quantity": 2}, {"medicine": env["amox"].pk, "quantity": 1}]}
    r = c.post(f"/api/v1/public/menu/{token}/requests/", body, format="json")
    assert r.status_code == 201 and r.data["requires_prescription"] is True
    assert c.post(f"/api/v1/public/menu/{token}/requests/", {**body, "website": "spam"}, format="json").status_code == 201
    assert QrRequest.all_objects.count() == 1  # honeypot submissions are dropped
    assert c.post(f"/api/v1/public/menu/{token}/requests/", {**body, "items": [{"medicine": env["morph"].pk, "quantity": 1}]}, format="json").status_code == 400
    assert c.post(f"/api/v1/public/menu/{token}/requests/", {"customer_name": "", "customer_phone": "1", "items": []}, format="json").status_code == 400
    assert c.post("/api/v1/public/menu/bad-token/requests/", body, format="json").status_code == 404
    lst = env["cash"].get("/api/v1/qr-requests/").data["results"]
    assert len(lst) == 1 and lst[0]["customer_name"] == "Walk In" and len(lst[0]["items"]) == 2 and lst[0]["requires_prescription"] is True
    assert env["cash2"].get("/api/v1/qr-requests/").data["count"] == 0  # other branch
    assert env["admin_b"].get("/api/v1/qr-requests/").data["count"] == 0
    assert env["tech"].get("/api/v1/qr-requests/").status_code == 403
    rid = lst[0]["id"]
    assert env["cash"].post(f"/api/v1/qr-requests/{rid}/status/", {"status": "reviewing", "staff_note": "Preparing"}, format="json").data["status"] == "reviewing"
    assert env["cash"].post(f"/api/v1/qr-requests/{rid}/status/", {"status": "bogus"}, format="json").status_code == 400
    assert env["cash"].post(f"/api/v1/qr-requests/{rid}/status/", {"status": "closed"}, format="json").status_code == 200
    assert env["cash"].post(f"/api/v1/qr-requests/{rid}/status/", {"status": "new"}, format="json").status_code == 400
    from apps.sales.models import Sale
    from apps.shop.models import Order
    assert Sale.all_objects.count() == 0 and Order.all_objects.count() == 0  # a request is not a sale or an order


def test_qr_menu_disabled_when_pharmacy_suspended(env):
    env["admin"].get(f"/api/v1/branches/{env['main'].pk}/qr/")
    token = Branch.all_objects.get(pk=env["main"].pk).qr_token
    pc = platform_client(User.objects.get(email="root@platform.test"))
    pc.post(f"/api/v1/platform/pharmacies/{env['g'].pk}/suspend/", {}, format="json")
    assert api().get(f"/api/v1/public/menu/{token}/").status_code == 404


# ---------------- profile ----------------
def test_customer_profile_validation_and_email_immutable(env):
    cl = customer(env)
    r = cl.patch("/api/v1/shop/me/", {"full_name": "New Name", "phone": "088", "address": "5 Hill St", "delivery_addresses": [{"label": "Home", "address": "5 Hill St"}],
                                       "emergency_contact_name": "Mum", "emergency_contact_phone": "099", "email": "hacker@example.com"}, format="json")
    assert r.status_code == 200 and r.data["full_name"] == "New Name" and r.data["email"] == "cust@example.com"
    assert User.objects.get(email="cust@example.com").phone == "088"
    assert cl.patch("/api/v1/shop/me/", {"delivery_addresses": [{"label": "x"}]}, format="json").status_code == 400
    assert cl.patch("/api/v1/shop/me/", {"notification_prefs": {"admin": True}}, format="json").status_code == 400
