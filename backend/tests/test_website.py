"""Website builder, contact forms, platform Google sign-in, pharmacy editing, and a guard against server errors on every dashboard."""
from unittest import mock

import pytest
from django.core import mail

from apps.accounts.models import User
from apps.backups.models import BackupRecord
from apps.notifications.models import Notification
from apps.website.content import clean_page
from apps.website.models import ContactMessage

from .test_foundation import api, login, platform_admin, platform_client, register, settled_token, two_pharmacies  # noqa: F401
from .test_phase8 import customer, env, order_body, place, signup, stock  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def root():
    return platform_client(User.objects.get(email="root@platform.test"))


def test_dashboards_never_error_once_there_is_data(env):
    """Production showed "Request failed" because the platform analytics crashed as soon as a completed backup existed."""
    stock(env, env["para"])
    place(customer(env, "d@example.com"), order_body(env))
    BackupRecord.objects.create(number="BK-1", status="completed", verification="OK")
    r = root()
    for url in ("/api/v1/analytics/platform/?days=30", "/api/v1/platform/dashboard/", "/api/v1/platform/billing/revenue/", "/api/v1/platform/backups/",
                "/api/v1/platform/backups/health/", "/api/v1/platform/restores/", "/api/v1/audit-logs/", "/api/v1/notifications/", "/api/v1/website/messages/"):
        assert r.get(url).status_code == 200, url
    for url in ("/api/v1/analytics/?days=7", "/api/v1/analytics/?days=365", "/api/v1/tenants/dashboard/", "/api/v1/reports/dashboard/", "/api/v1/customers/",
                "/api/v1/inventory/alerts/", "/api/v1/orders/", "/api/v1/sales/", "/api/v1/payments/reconciliation/", "/api/v1/subscription/", "/api/v1/website/pages/"):
        assert env["admin"].get(url).status_code == 200, url


def test_website_content_is_scoped_and_sanitised(env):
    page = {"hero": {"title": "Hi **there**", "model": "dna", "primary": {"label": "Go", "href": "javascript:alert(1)"}, "image": "data:text/html,x", "evil": 1},
            "blocks": [{"type": "items", "layout": "accordion", "items": [{"title": "A", "href": "//evil.example"}]}]}
    r = env["admin"].put("/api/v1/website/pages/home/", {"content": page}, format="json")
    assert r.status_code == 200, r.data
    saved = r.data["content"]
    assert saved["hero"]["primary"]["href"] == "" and saved["hero"]["image"] == "" and "evil" not in saved["hero"] and saved["blocks"][0]["items"][0]["href"] == ""
    assert api().get("/api/v1/public/pharmacies/greenlife/pages/home/").data["content"]["hero"]["title"] == "Hi **there**"
    assert api().get("/api/v1/public/pharmacies/bluecross/pages/home/").data["content"] is None
    assert api().get("/api/v1/public/site-pages/home/").data["content"] is None  # a pharmacy never edits the main website
    assert root().put("/api/v1/website/pages/pricing/", {"content": {"hero": {"title": "Plans"}}}, format="json").status_code == 200
    assert api().get("/api/v1/public/site-pages/pricing/").data["content"]["hero"]["title"] == "Plans"
    assert env["cash"].put("/api/v1/website/pages/home/", {"content": page}, format="json").status_code == 403
    assert env["admin"].put("/api/v1/website/pages/pricing/", {"content": page}, format="json").status_code == 404
    assert env["admin"].put("/api/v1/website/pages/home/", {"content": {"blocks": [{"type": "script"}]}}, format="json").status_code == 400
    assert env["admin"].delete("/api/v1/website/pages/home/").status_code == 204
    g = root().put("/api/v1/website/pages/global/", {"content": {"address": "1 Road", "latitude": "8.48", "longitude": "999", "social": [{"title": "X", "href": "https://x.com/a"}]}}, format="json").data["content"]
    assert g["latitude"] == "8.48" and g["longitude"] == ""
    assert clean_page({})["blocks"] == []


def test_contact_messages_reach_only_their_owner(env):
    body = {"name": "Visitor", "email": "v@example.com", "subject": "Hello", "message": "Do you deliver?"}
    assert api().post("/api/v1/public/pharmacies/greenlife/contact/", body, format="json").status_code == 201
    assert api().post("/api/v1/public/contact/", {**body, "subject": "Platform"}, format="json").status_code == 201
    assert api().post("/api/v1/public/contact/", {**body, "website": "spam"}, format="json").status_code == 201
    assert ContactMessage.objects.count() == 2
    mine = env["admin"].get("/api/v1/website/messages/").data
    assert mine["count"] == 1 and mine["summary"]["new"] == 1 and mine["results"][0]["subject"] == "Hello"
    pk = mine["results"][0]["id"]
    assert env["admin_b"].get("/api/v1/website/messages/").data["count"] == 0
    assert env["admin_b"].patch(f"/api/v1/website/messages/{pk}/", {"status": "resolved"}, format="json").status_code == 404
    assert root().get("/api/v1/website/messages/").data["results"][0]["subject"] == "Platform"
    assert env["tech"].get("/api/v1/website/messages/").status_code == 403
    mail.outbox.clear()
    r = env["admin"].post(f"/api/v1/website/messages/{pk}/reply/", {"message": "Yes we do."}, format="json")
    assert r.status_code == 200 and r.data["status"] == "resolved" and mail.outbox[0].to == ["v@example.com"]
    assert Notification.objects.filter(kind="contact").exists()
    assert env["admin"].delete(f"/api/v1/website/messages/{pk}/").status_code == 204


def test_google_sign_in_only_for_existing_platform_admins(env, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "client-1"
    claims = lambda e: mock.patch("apps.shop.services.verify_google_id_token", return_value={"email": e, "sub": "1"})  # noqa: E731
    with claims("root@platform.test"):
        r = api().post("/api/v1/auth/google/platform/", {"id_token": "t"}, format="json")
        assert r.status_code == 200 and r.data["user"]["is_platform_admin"] is True and r.data["tokens"]["access"]
    before = User.objects.count()
    for email in ("a@green.test", "stranger@example.com"):
        with claims(email):
            assert api().post("/api/v1/auth/google/platform/", {"id_token": "t"}, format="json").status_code == 403
    assert User.objects.count() == before
    settings.GOOGLE_OAUTH_CLIENT_ID = ""
    assert api().post("/api/v1/auth/google/platform/", {"id_token": "t"}, format="json").status_code == 503


def test_platform_can_edit_every_registration_field_later(env):
    g = env["g"]
    r = root().patch(f"/api/v1/platform/pharmacies/{g.pk}/", {"registration_number": "REG-9", "license_number": "LIC-9", "region": "West", "city": "Freetown",
                                                          "description": "Later", "admin_full_name": "New Boss", "admin_email": "boss@green.test", "admin_phone": "076"}, format="json")
    assert r.status_code == 200, r.data
    admin = User.objects.get(tenant=g, role__code="pharmacy_admin")
    assert (admin.full_name, admin.email, admin.phone) == ("New Boss", "boss@green.test", "076") and r.data["license_number"] == "LIC-9"
    assert env["admin"].get("/api/v1/auth/me/").status_code == 401  # the old session ended with the email change
    assert env["admin_b"].patch(f"/api/v1/platform/pharmacies/{g.pk}/", {"city": "x"}, format="json").status_code == 403
