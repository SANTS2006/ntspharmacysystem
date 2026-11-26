"""Account settings, in-app notifications, the Customers module, counter mobile money and subscription payments."""
from decimal import Decimal
from io import BytesIO
from unittest import mock

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import User
from apps.billing.models import Invoice, Plan
from apps.notifications.models import Notification
from apps.payments import monime
from apps.payments.models import MobileMoneyCollection

from .test_foundation import api, login, platform_admin, platform_client, register, settled_token, two_pharmacies  # noqa: F401
from .test_phase8 import CPW, customer, env, order_body, place, signup, stock  # noqa: F401
from .test_phase9 import configure, event, post_hook, session  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def png():
    b = BytesIO()
    Image.new("RGB", (8, 8), "green").save(b, "PNG")
    return b.getvalue()


def test_profile_and_picture(env):
    c = env["cash"]
    r = c.patch("/api/v1/auth/me/profile/", {"full_name": "New Name", "phone": "076", "email": "evil@x.test", "is_platform_admin": True}, format="json")
    assert r.status_code == 200 and r.data["full_name"] == "New Name" and r.data["email"] != "evil@x.test" and r.data["is_platform_admin"] is False
    bad = SimpleUploadedFile("a.png", b"<script>", content_type="image/png")
    assert c.post("/api/v1/auth/me/avatar/", {"avatar": bad}, format="multipart").status_code == 400
    r = c.post("/api/v1/auth/me/avatar/", {"avatar": SimpleUploadedFile("a.png", png(), content_type="image/png")}, format="multipart")
    assert r.status_code == 200 and "avatars/" in r.data["avatar"]
    assert c.delete("/api/v1/auth/me/avatar/").data["avatar"] is None


def test_email_change_needs_password_and_code_sent_to_new_address(env):
    c = customer(env, "move@example.com")
    assert c.post("/api/v1/auth/me/email/", {"new_email": "n@example.com", "password": "wrong"}, format="json").status_code == 400
    mail.outbox.clear()
    with mock.patch("apps.accounts.profile_views.secrets.choice", return_value="A"):
        assert c.post("/api/v1/auth/me/email/", {"new_email": "n@example.com", "password": CPW}, format="json").status_code == 202
    assert {m.to[0] for m in mail.outbox} == {"n@example.com", "move@example.com"}
    assert c.post("/api/v1/auth/me/email/confirm/", {"code": "BBBBBB"}, format="json").status_code == 400
    assert User.objects.filter(email="move@example.com").exists()
    r = c.post("/api/v1/auth/me/email/confirm/", {"code": "AAAAAA"}, format="json")
    assert r.status_code == 200 and r.data["email"] == "n@example.com"
    assert c.post("/api/v1/auth/me/email/confirm/", {"code": "AAAAAA"}, format="json").status_code == 400  # single use


def test_notifications_are_private_and_scoped(env):
    stock(env, env["para"])
    cl = customer(env, "buyer@example.com")
    place(cl, order_body(env))
    staff = env["cash"].get("/api/v1/notifications/").data
    assert staff["unread"] >= 1 and any("New online order" in n["title"] for n in staff["results"])
    assert not any("New online order" in n["title"] for n in env["cash2"].get("/api/v1/notifications/").data["results"])  # other branch
    assert not any("New online order" in n["title"] for n in env["admin_b"].get("/api/v1/notifications/").data["results"])  # other pharmacy
    mine = next(n for n in staff["results"] if "New online order" in n["title"])
    assert cl.get(f"/api/v1/notifications/{mine['id']}/").status_code == 404  # belongs to someone else
    assert cl.post(f"/api/v1/notifications/{mine['id']}/read/", {}, format="json").status_code == 404
    assert env["cash"].post(f"/api/v1/notifications/{mine['id']}/read/", {}, format="json").data["read"] is True
    env["cash"].post("/api/v1/notifications/read-all/")
    assert env["cash"].get("/api/v1/notifications/?unread=1").data["count"] == 0
    assert env["cash"].delete(f"/api/v1/notifications/{mine['id']}/").status_code == 204
    assert any("placed" in n["title"] for n in cl.get("/api/v1/notifications/").data["results"])
    assert api().get("/api/v1/notifications/").status_code == 401


def test_customers_module_is_permission_and_tenant_scoped(env):
    stock(env, env["para"])
    cl = customer(env, "person@example.com")
    place(cl, order_body(env))
    r = env["admin"].get("/api/v1/customers/?search=person")
    assert r.status_code == 200 and r.data["count"] == 1 and r.data["results"][0]["orders"] == 1 and r.data["summary"]["total"] >= 1
    pk = r.data["results"][0]["id"]
    d = env["admin"].get(f"/api/v1/customers/{pk}/").data
    assert d["email"] == "person@example.com" and len(d["recent_orders"]) == 1 and "password" not in str(d.keys())
    assert env["admin_b"].get(f"/api/v1/customers/{pk}/").status_code == 404
    assert env["admin_b"].get("/api/v1/customers/").data["count"] == 0
    assert cl.get("/api/v1/customers/").status_code == 403
    assert env["cash"].patch(f"/api/v1/customers/{pk}/", {"is_active": False}, format="json").status_code == 403  # view only
    assert env["admin"].patch(f"/api/v1/customers/{pk}/", {"is_active": False}, format="json").data["is_active"] is False
    assert cl.get("/api/v1/shop/orders/").status_code == 401  # signed out everywhere


def test_counter_mobile_money_must_be_verified_by_the_provider(env, settings):
    stock(env, env["para"])
    configure(settings)
    c = env["cash"]
    assert c.post("/api/v1/shifts/open/", {"branch": env["main"].pk, "opening_cash": "0"}, format="json").status_code in (200, 201)

    def sale(ref, amount, key):
        return c.post("/api/v1/sales/", {"items": [{"medicine": env["para"].pk, "quantity": 2}], "payments": [{"method": "mobile_money", "amount": amount, "reference": ref}]},
                      format="json", HTTP_IDEMPOTENCY_KEY=key)

    assert sale("TYPED-BY-HAND", "22.00", "k1").status_code == 400
    with mock.patch.object(monime, "create_payment_code", return_value={"id": "pmc-1", "ussdCode": "*715*1#"}) as made:
        r = c.post("/api/v1/payments/mobile-money/", {"amount": "22.00"}, format="json")
    assert r.status_code == 201 and r.data["ussd_code"] == "*715*1#" and made.call_args.kwargs["amount_minor"] == 2200
    ref, pk = r.data["reference"], r.data["id"]
    assert sale(ref, "22.00", "k2").status_code == 400  # not paid yet
    with mock.patch.object(monime, "retrieve_payment_code", return_value={"status": "completed", "amount": {"currency": "SLE", "value": 2200}}):
        assert c.get(f"/api/v1/payments/mobile-money/{pk}/").data["status"] == "completed"
    assert sale(ref, "11.00", "k3").status_code == 400  # amount must match
    ok = sale(ref, "22.00", "k4")
    assert ok.status_code == 201, ok.data
    assert sale(ref, "22.00", "k5").status_code == 400  # money cannot be used twice
    assert MobileMoneyCollection.all_objects.get(reference=ref).used_at
    assert env["admin_b"].get(f"/api/v1/payments/mobile-money/{pk}/").status_code == 404


def test_subscription_invoice_paid_only_on_provider_confirmation(env, settings):
    configure(settings)
    plan = Plan.objects.create(code="pro", name="Pro", price=Decimal("100.00"), currency="SLE")
    inv = Invoice.objects.create(number="INV-T-1", pharmacy=env["g"], plan=plan, amount=plan.price, currency="SLE", due_date="2030-01-01")
    a = env["admin"]
    assert a.get("/api/v1/subscription/").data["invoices"][0]["payable_online"] is True
    assert env["admin_b"].post(f"/api/v1/subscription/invoices/{inv.pk}/pay/").status_code == 404
    assert env["cash"].get("/api/v1/subscription/").status_code == 403
    with mock.patch.object(monime, "create_checkout_session", return_value=session("pending", "chk-inv")):
        assert a.post(f"/api/v1/subscription/invoices/{inv.pk}/pay/").data["redirect_url"].startswith("https://")
    assert Invoice.objects.get(pk=inv.pk).status == "issued"
    with mock.patch.object(monime, "retrieve_checkout_session", return_value=session("completed", "chk-inv", 10000)):
        assert post_hook("greenlife", event("chk-inv")).json()["outcome"] == "confirmed"
    assert Invoice.objects.get(pk=inv.pk).status == "paid"
    assert Notification.objects.filter(kind="billing", title__contains="paid").exists()


def test_customer_summary_counts_only_their_own_orders(env):
    stock(env, env["para"])
    one, two = customer(env, "one@example.com"), customer(env, "two@example.com")
    place(one, order_body(env))
    a, b = one.get("/api/v1/shop/summary/").data, two.get("/api/v1/shop/summary/").data
    assert a["orders"] == 1 and len(a["recent"]) == 1 and len(a["monthly"]) >= 5 and b["orders"] == 0 and b["recent"] == []
    assert env["admin"].get("/api/v1/shop/summary/").status_code == 403


def test_dashboard_analytics_only_contains_permitted_sections(env, settings):
    stock(env, env["para"])
    a = env["admin"].get("/api/v1/analytics/?days=30")
    assert a.status_code == 200 and {"sales", "orders", "inventory", "finance", "customers", "people", "prescriptions"} <= set(a.data)
    assert len(a.data["sales"]["trend"]) == 30
    cashier = env["cash"].get("/api/v1/analytics/").data
    assert cashier["sales"]["own_only"] is True and "finance" not in cashier and "inventory" not in cashier and "people" not in cashier
    tech = env["tech"].get("/api/v1/analytics/").data
    assert "sales" not in tech and "finance" not in tech and "inventory" in tech
    assert customer(env, "c2@example.com").get("/api/v1/analytics/").status_code == 403
    assert env["admin"].get("/api/v1/analytics/platform/").status_code == 403
    p = platform_client(User.objects.get(email="root@platform.test")).get("/api/v1/analytics/platform/")
    assert p.status_code == 200 and p.data["pharmacies"]["total"] >= 2 and len(p.data["monthly"]) >= 11


def test_public_pages_get_server_side_seo_and_private_pages_are_not_indexed(env, rf):
    from apps.core import seo
    html = '<html><head><meta name="description" content="x" /><title>x</title></head></html>'
    env["g"].description = 'Caring <script>alert(1)</script> pharmacy'
    env["g"].save()
    out = seo.inject(html, rf.get("/greenlife"))
    assert "<title>" + env["g"].name in out and "og:title" in out and "canonical" in out and "<script>alert" not in out
    for private in ("/greenlife/admin/dashboard", "/greenlife/account/orders", "/greenlife/login", "/platform/dashboard", "/no-such-pharmacy"):
        assert "noindex" in seo.inject(html, rf.get(private)), private
    robots = seo.robots_txt(rf.get("/robots.txt")).content.decode()
    assert "Disallow: /*/admin" in robots and "Sitemap:" in robots
    sitemap = seo.sitemap_xml(rf.get("/sitemap.xml")).content.decode()
    assert "/greenlife/products" in sitemap and "/admin" not in sitemap
