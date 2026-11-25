import io
from unittest import mock

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.billing.models import Invoice, Plan
from apps.notifications import services as notif
from apps.notifications.models import EmailLog
from apps.tenants.models import Pharmacy

from .test_foundation import (STRONG, api, login, platform_admin, platform_client,  # noqa: F401
                              register, settled_token, temp_pw, two_pharmacies)

pytestmark = pytest.mark.django_db(transaction=True)


# ---------------- email ----------------
def test_email_logged_and_branded_html_escaped(two_pharmacies):
    g = Pharmacy.objects.get(slug="greenlife")
    g.name = '<script>x</script> Pharm'
    html_body = notif.render_branded_html(title="Hi", paragraphs=["a < b"], pharmacy=g, button=("Go", "javascript:alert(1)"))
    assert "<script>" not in html_body and "javascript:" not in html_body and g.primary_color in html_body
    log = EmailLog.objects.get(to_email="a@green.test")
    assert log.status == "sent" and log.template == "admin_onboarding" and log.attempts == 1
    assert mail.outbox[0].alternatives  # html part present


def test_brevo_path_and_failure_recording(settings, two_pharmacies):
    settings.BREVO_API_KEY = "test-key"
    with mock.patch.object(notif, "_post_brevo", return_value="<msg-1>") as post:
        e = notif.send_email(to="x@y.test", subject="S", text="T", html_body="<p>T</p>", template="t")
    entry = EmailLog.objects.get(pk=e.pk)
    assert entry.provider == "brevo" and entry.status == "sent" and entry.provider_message_id == "<msg-1>"
    assert post.call_args[0][0]["to"] == [{"email": "x@y.test"}]
    with mock.patch.object(notif, "_post_brevo", side_effect=RuntimeError("boom")):
        e2 = notif.send_email(to="z@y.test", subject="S", text="T")  # must not raise to caller
    entry2 = EmailLog.objects.get(pk=e2.pk)
    assert entry2.status == "failed" and "boom" in entry2.last_error and entry2.attempts == 1


# ---------------- password reset ----------------
def _reset_params():
    body = mail.outbox[-1].body
    link = body.split("link to reset your password (valid for a limited time): ")[1].split()[0]
    q = dict(p.split("=") for p in link.split("?")[1].split("&"))
    return q


def test_password_reset_flow(two_pharmacies):
    settled_token("greenlife", "a@green.test", temp_pw())
    n = len(mail.outbox)
    r1 = api("greenlife").post("/api/v1/auth/password-reset/", {"email": "a@green.test"}, format="json")
    r2 = api("greenlife").post("/api/v1/auth/password-reset/", {"email": "ghost@green.test"}, format="json")
    assert r1.status_code == r2.status_code == 204
    assert len(mail.outbox) == n + 1  # nothing sent for unknown account
    q = _reset_params()
    new = "An0ther-Str0ng-Pass!"
    # wrong tenant must fail
    assert api("bluecross").post("/api/v1/auth/password-reset/confirm/", {**q, "new_password": new}, format="json").status_code == 400
    ok = api("greenlife").post("/api/v1/auth/password-reset/confirm/", {"uid": q["uid"], "token": q["token"], "new_password": new}, format="json")
    assert ok.status_code == 200
    again = api("greenlife").post("/api/v1/auth/password-reset/confirm/", {"uid": q["uid"], "token": q["token"], "new_password": new + "x"}, format="json")
    assert again.status_code == 400  # single use
    assert login("greenlife", "a@green.test", new).status_code == 200
    assert AuditLog.objects.filter(action="auth.password_reset_completed").exists()


def test_password_reset_enforces_policy(two_pharmacies):
    api("greenlife").post("/api/v1/auth/password-reset/", {"email": "a@green.test"}, format="json")
    q = _reset_params()
    r = api("greenlife").post("/api/v1/auth/password-reset/confirm/", {**q, "new_password": "weak"}, format="json")
    assert r.status_code == 400


# ---------------- dashboard ----------------
def test_platform_dashboard(two_pharmacies):
    r = two_pharmacies.get("/api/v1/platform/dashboard/")
    assert r.status_code == 200
    d = r.data
    assert d["pharmacies"]["total"] == 2 and d["pharmacies"]["active"] == 2
    assert d["branches"] == 2 and d["users"] == 2 and d["customers"] == 0
    assert d["system_health"]["database"] == "ok" and d["registration_trend"]
    assert d["recent_activity"]


def test_dashboard_forbidden_for_tenant_users(two_pharmacies):
    tok = settled_token("greenlife", "a@green.test", temp_pw())
    c = api("greenlife", tok)
    for url in ["/api/v1/platform/dashboard/", "/api/v1/platform/billing/invoices/", "/api/v1/platform/billing/revenue/"]:
        assert c.get(url).status_code == 403
    assert api().get("/api/v1/platform/dashboard/").status_code == 401


def test_pharmacy_overview(two_pharmacies):
    g = Pharmacy.objects.get(slug="greenlife")
    r = two_pharmacies.get(f"/api/v1/platform/pharmacies/{g.pk}/overview/")
    assert r.status_code == 200 and r.data["branches"][0]["code"] == "MAIN"
    assert r.data["administrators"][0]["email"] == "a@green.test"


# ---------------- billing ----------------
@pytest.fixture
def plan():
    return Plan.objects.create(code="basic", name="Basic", price="50.00")


def _issue(pc, plan_obj, slug="greenlife"):
    g = Pharmacy.objects.get(slug=slug)
    r = pc.post("/api/v1/platform/billing/invoices/issue/", {"pharmacy": g.pk, "plan": plan_obj.pk}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def test_invoice_payment_lifecycle(two_pharmacies, plan):
    pc = two_pharmacies
    inv = _issue(pc, plan)
    pay = pc.post(f"/api/v1/platform/billing/invoices/{inv['id']}/pay/", {"payment_method": "mobile_money", "payment_reference": "MM-1"}, format="json")
    assert pay.status_code == 200 and pay.data["status"] == "paid"
    assert pc.post(f"/api/v1/platform/billing/invoices/{inv['id']}/pay/", {"payment_method": "cash", "payment_reference": "MM-2"}, format="json").status_code == 400
    inv2 = _issue(pc, plan, "bluecross")
    dup = pc.post(f"/api/v1/platform/billing/invoices/{inv2['id']}/pay/", {"payment_method": "mobile_money", "payment_reference": "MM-1"}, format="json")
    assert dup.status_code == 400  # duplicate payment reference blocked
    assert pc.post(f"/api/v1/platform/billing/invoices/{inv['id']}/refund/", {"amount": "60"}, format="json").status_code == 400
    assert pc.post(f"/api/v1/platform/billing/invoices/{inv['id']}/refund/", {"amount": "20", "reason": "goodwill"}, format="json").status_code == 200
    assert pc.post(f"/api/v1/platform/billing/invoices/{inv['id']}/refund/", {"amount": "31"}, format="json").status_code == 400
    rev = pc.get("/api/v1/platform/billing/revenue/").data
    assert float(rev["collected"]) == 50 and float(rev["refunded"]) == 20 and float(rev["net_revenue"]) == 30
    assert float(rev["outstanding"]) == 50
    assert {"billing.invoice_issued", "billing.invoice_paid", "billing.invoice_refunded"} <= set(AuditLog.objects.values_list("action", flat=True))
    assert Pharmacy.objects.get(slug="greenlife").subscription.status == "active"


def test_cannot_void_paid_or_pay_voided(two_pharmacies, plan):
    pc = two_pharmacies
    inv = _issue(pc, plan)
    assert pc.post(f"/api/v1/platform/billing/invoices/{inv['id']}/void/").status_code == 200
    assert pc.post(f"/api/v1/platform/billing/invoices/{inv['id']}/pay/", {"payment_reference": "R"}, format="json").status_code == 400
    assert Invoice.objects.get(pk=inv["id"]).status == "void"


def test_invoice_amount_not_editable_via_api(two_pharmacies, plan):
    inv = _issue(two_pharmacies, plan)
    assert two_pharmacies.patch(f"/api/v1/platform/billing/invoices/{inv['id']}/", {"amount": "1"}, format="json").status_code in (404, 405)


# ---------------- public branding ----------------
def test_public_branding_active_only_and_no_sensitive_fields(two_pharmacies):
    r = api().get("/api/v1/public/pharmacies/greenlife/")
    assert r.status_code == 200 and r.data["name"] == "Green Life Pharmacy"
    assert not ({"license_number", "registration_number", "status", "settings", "id"} & set(r.data))
    g = Pharmacy.objects.get(slug="greenlife")
    two_pharmacies.post(f"/api/v1/platform/pharmacies/{g.pk}/suspend/", {}, format="json")
    assert api().get("/api/v1/public/pharmacies/greenlife/").status_code == 404
    assert api().get("/api/v1/public/pharmacies/nope/").status_code == 404


def test_public_platform_info(settings):
    settings.PLATFORM_WHATSAPP_NUMBER = "23277000000"
    assert api().get("/api/v1/public/platform/").data["whatsapp_number"] == "23277000000"


# ---------------- logo upload ----------------
def _png():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    return buf.getvalue()


def _reg_with_logo(pc, name, slug, upload):
    return pc.post("/api/v1/platform/pharmacies/", {"name": "Logo Pharm", "slug": slug, "admin_full_name": "A",
                                                   "admin_email": f"{slug}@x.test", "logo": upload}, format="multipart")


def test_logo_upload_validation(two_pharmacies, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    assert _reg_with_logo(two_pharmacies, "L", "logook", SimpleUploadedFile("l.png", _png(), "image/png")).status_code == 201
    assert _reg_with_logo(two_pharmacies, "L", "logobad", SimpleUploadedFile("l.png", b"not an image", "image/png")).status_code == 400
    svg = SimpleUploadedFile("l.svg", b"<svg onload=alert(1)/>", "image/svg+xml")
    assert _reg_with_logo(two_pharmacies, "L", "logosvg", svg).status_code == 400
    settings.LOGO_MAX_BYTES = 10
    assert _reg_with_logo(two_pharmacies, "L", "logobig", SimpleUploadedFile("l.png", _png(), "image/png")).status_code == 400


def test_public_plans_lists_only_active(plan):
    Plan.objects.create(code="old", name="Old", price="1", is_active=False)
    r = api().get("/api/v1/public/plans/")
    assert [p["code"] for p in r.data] == ["basic"]
