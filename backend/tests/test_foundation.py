from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.tenant_context import tenant_context, unscoped
from apps.tenants.models import Branch, Pharmacy

pytestmark = pytest.mark.django_db
STRONG = "Str0ng-Passw0rd-Xyz!"
ROOT_PW = "Root-Passw0rd-123!"


def api(slug=None, token=None):
    c = APIClient()
    creds = {}
    if slug:
        creds["HTTP_X_TENANT_SLUG"] = slug
    if token:
        creds["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    c.credentials(**creds)
    return c


def temp_pw():
    return f"GLP@{timezone.now().year}"


@pytest.fixture
def platform_admin():
    return User.objects.create_platform_admin("root@platform.test", ROOT_PW, full_name="Root")


def platform_client(admin):
    r = api().post("/api/v1/auth/login/", {"email": admin.email, "password": ROOT_PW}, format="json")
    assert r.status_code == 200, r.data
    return api(token=r.data["tokens"]["access"])


def register(client, name, slug, email, **extra):
    return client.post("/api/v1/platform/pharmacies/", {
        "name": name, "slug": slug, "admin_full_name": "Admin " + slug, "admin_email": email, **extra},
        format="json")


@pytest.fixture
def two_pharmacies(platform_admin):
    pc = platform_client(platform_admin)
    assert register(pc, "Green Life Pharmacy", "greenlife", "a@green.test").status_code == 201
    assert register(pc, "Blue Cross Pharmacy", "bluecross", "a@blue.test").status_code == 201
    return pc


def login(slug, email, password):
    return api(slug).post("/api/v1/auth/login/", {"email": email, "password": password}, format="json")


def settled_token(slug, email, temp):
    r = login(slug, email, temp)
    assert r.status_code == 200 and r.data["user"]["must_change_password"] is True
    r = api(slug, r.data["tokens"]["access"]).post(
        "/api/v1/auth/change-password/", {"old_password": temp, "new_password": STRONG}, format="json")
    assert r.status_code == 200, r.data
    return r.data["tokens"]["access"]


def test_default_password_format():
    assert services.build_default_password("Green Life Pharmacy", 2026) == "GLP@2026"
    assert services.build_default_password("  éclair & co.-pharma ", 2026) == "ECP@2026"


@pytest.mark.django_db(transaction=True)
def test_registration_provisions_tenant(platform_admin, two_pharmacies):
    g = Pharmacy.objects.get(slug="greenlife")
    assert g.roles.count() == 11
    with tenant_context(g):
        assert Branch.objects.filter(code="MAIN").exists()
    admin = User.objects.get(email="a@green.test")
    assert admin.role.code == "pharmacy_admin" and admin.must_change_password
    assert admin.password.startswith("argon2") and "GLP@" not in admin.password
    body = [m for m in mail.outbox if "a@green.test" in m.to][0].body
    assert temp_pw() in body
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"platform.pharmacy_registered", "auth.credentials_issued"} <= actions


def test_api_never_returns_password(two_pharmacies):
    r = register(two_pharmacies, "Zed Pharmacy", "zedpharm", "z@zed.test")
    assert r.status_code == 201
    assert "password" not in str(r.data).lower() and "ZP@" not in str(r.data)


def test_reserved_and_duplicate_slugs_rejected(two_pharmacies):
    assert register(two_pharmacies, "X", "admin", "x@x.test").status_code == 400
    assert register(two_pharmacies, "Dup", "greenlife", "d@d.test").status_code == 400


def test_non_platform_user_cannot_use_platform_api(two_pharmacies):
    tok = settled_token("greenlife", "a@green.test", temp_pw())
    assert api("greenlife", tok).get("/api/v1/platform/pharmacies/").status_code == 403


def test_forced_password_change_blocks_everything_else(two_pharmacies):
    r = login("greenlife", "a@green.test", temp_pw())
    c = api("greenlife", r.data["tokens"]["access"])
    assert c.get("/api/v1/audit-logs/").status_code == 403
    assert c.get("/api/v1/auth/me/").status_code == 200
    new = settled_token("greenlife", "a@green.test", temp_pw())
    assert c.get("/api/v1/auth/me/").status_code == 401  # old token revoked by credential_version bump
    assert api("greenlife", new).get("/api/v1/audit-logs/").status_code == 200


def test_weak_new_password_rejected(two_pharmacies):
    tok = login("greenlife", "a@green.test", temp_pw()).data["tokens"]["access"]
    r = api("greenlife", tok).post("/api/v1/auth/change-password/",
                                   {"old_password": temp_pw(), "new_password": "short1"}, format="json")
    assert r.status_code == 400


def test_login_requires_matching_tenant_and_is_generic(two_pharmacies):
    wrong_tenant = login("bluecross", "a@green.test", temp_pw())
    wrong_pw = login("greenlife", "a@green.test", "nope")
    unknown = login("greenlife", "ghost@green.test", "nope")
    assert wrong_tenant.status_code == wrong_pw.status_code == unknown.status_code == 401
    assert (wrong_tenant.data["error"]["message"] == wrong_pw.data["error"]["message"]
            == unknown.data["error"]["message"])
    assert login("nonexistent", "a@green.test", temp_pw()).status_code == 401


def test_lockout_after_repeated_failures(two_pharmacies, settings):
    settings.LOGIN_MAX_FAILED_ATTEMPTS = 3
    for _ in range(3):
        login("greenlife", "a@green.test", "bad")
    assert login("greenlife", "a@green.test", temp_pw()).status_code == 429  # correct pw, but locked
    assert AuditLog.objects.filter(action="auth.account_locked").exists()


def test_temporary_credentials_expire(two_pharmacies):
    u = User.objects.get(email="a@green.test")
    User.objects.filter(pk=u.pk).update(temp_password_expires_at=timezone.now() - timedelta(minutes=1))
    r = login("greenlife", "a@green.test", temp_pw())
    assert r.status_code == 403 and r.data["error"]["code"] == "credentials_expired"


def test_cross_tenant_hint_rejected_for_authenticated_user(two_pharmacies):
    tok = settled_token("greenlife", "a@green.test", temp_pw())
    assert api("bluecross", tok).get("/api/v1/auth/me/").status_code == 403
    assert api("greenlife", tok).get("/api/v1/auth/me/").status_code == 200
    assert api(None, tok).get("/api/v1/auth/me/").status_code == 200  # tenant always comes from the user


def test_tenant_manager_fails_closed_and_isolates(two_pharmacies):
    g, b = Pharmacy.objects.get(slug="greenlife"), Pharmacy.objects.get(slug="bluecross")
    assert Branch.objects.count() == 0  # no context => nothing visible
    with tenant_context(g):
        assert list(Branch.objects.values_list("tenant__slug", flat=True)) == ["greenlife"]
        Branch.objects.create(name="Second", code="B2")
    with tenant_context(b):
        assert Branch.objects.filter(code="B2").count() == 0
        assert Branch.objects.count() == 1
    with unscoped():
        assert Branch.objects.count() == 3


def test_cross_tenant_write_blocked(two_pharmacies):
    g, b = Pharmacy.objects.get(slug="greenlife"), Pharmacy.objects.get(slug="bluecross")
    with tenant_context(g):
        with pytest.raises(PermissionDenied):
            Branch(name="Evil", code="EV", tenant=b).save()
    with pytest.raises(PermissionDenied):
        Branch(name="NoCtx", code="NC").save()


def test_audit_log_is_immutable(two_pharmacies):
    entry = AuditLog.objects.first()
    entry.action = "tampered"
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(PermissionError):
        entry.delete()


def test_audit_visibility_scoped_by_tenant_and_permission(two_pharmacies):
    tok = settled_token("greenlife", "a@green.test", temp_pw())
    rows = api("greenlife", tok).get("/api/v1/audit-logs/").data["results"]
    assert rows and all("bluecross" not in str(r) for r in rows)
    g = Pharmacy.objects.get(slug="greenlife")
    User.objects.create_user("c@green.test", "Cashier-Passw0rd-1!", tenant=g, full_name="C",
                             role=g.roles.get(code="cashier"))
    ct = login("greenlife", "c@green.test", "Cashier-Passw0rd-1!").data["tokens"]["access"]
    assert api("greenlife", ct).get("/api/v1/audit-logs/").status_code == 403


def test_suspension_blocks_login_and_existing_tokens(two_pharmacies):
    tok = settled_token("greenlife", "a@green.test", temp_pw())
    g = Pharmacy.objects.get(slug="greenlife")
    r = two_pharmacies.post(f"/api/v1/platform/pharmacies/{g.pk}/suspend/", {"reason": "unpaid"}, format="json")
    assert r.status_code == 200
    assert api("greenlife", tok).get("/api/v1/auth/me/").status_code == 401
    r = login("greenlife", "a@green.test", STRONG)
    assert r.status_code == 403 and r.data["error"]["code"] == "tenant_inactive"
    assert two_pharmacies.post(f"/api/v1/platform/pharmacies/{g.pk}/activate/").status_code == 200
    assert login("greenlife", "a@green.test", STRONG).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_invitation_flow_single_use(platform_admin):
    pc = platform_client(platform_admin)
    assert register(pc, "Inv Pharmacy", "invpharm", "i@inv.test", use_invitation=True).status_code == 201
    body = mail.outbox[-1].body
    assert "Temporary password" not in body
    token = body.split("token=")[1].split()[0]
    ok = api().post("/api/v1/auth/accept-invitation/", {"token": token, "new_password": STRONG}, format="json")
    assert ok.status_code == 200
    again = api().post("/api/v1/auth/accept-invitation/", {"token": token, "new_password": STRONG + "2"},
                       format="json")
    assert again.status_code == 400
    assert login("invpharm", "i@inv.test", STRONG).status_code == 200


def test_logout_blacklists_refresh(two_pharmacies):
    r = login("greenlife", "a@green.test", temp_pw())
    c = api("greenlife", r.data["tokens"]["access"])
    assert c.post("/api/v1/auth/logout/", {"refresh": r.data["tokens"]["refresh"]}, format="json").status_code == 204
    assert api().post("/api/v1/auth/refresh/", {"refresh": r.data["tokens"]["refresh"]},
                      format="json").status_code == 401
