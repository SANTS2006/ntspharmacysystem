import pytest
from django.core import mail

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.tenant_context import tenant_context
from apps.tenants.models import Branch, Pharmacy

from .test_foundation import (STRONG, api, login, platform_admin, platform_client,  # noqa: F401
                              register, settled_token, temp_pw, two_pharmacies)

pytestmark = pytest.mark.django_db(transaction=True)
PW = "Staff-Passw0rd-123!"


@pytest.fixture
def env(two_pharmacies):
    """Admin tokens for both pharmacies + a second Green branch + a Green branch manager and cashier."""
    g, b = Pharmacy.objects.get(slug="greenlife"), Pharmacy.objects.get(slug="bluecross")
    admin_g = api("greenlife", settled_token("greenlife", "a@green.test", f"GLP@{__import__('django.utils.timezone', fromlist=['now']).now().year}"))
    admin_b = api("bluecross", settled_token("bluecross", "a@blue.test", f"BCP@{__import__('django.utils.timezone', fromlist=['now']).now().year}"))
    with tenant_context(g):
        main = Branch.objects.get(code="MAIN")
        second = Branch.objects.create(name="Second", code="B2")
    mgr = User.objects.create_user("m@green.test", PW, tenant=g, full_name="Mgr", role=g.roles.get(code="branch_manager"), branch=main)
    cash = User.objects.create_user("c@green.test", PW, tenant=g, full_name="Cash", role=g.roles.get(code="cashier"), branch=second)
    return dict(g=g, b=b, admin_g=admin_g, admin_b=admin_b, main=main, second=second, mgr=mgr, cash=cash,
                mgr_c=api("greenlife", login("greenlife", "m@green.test", PW).data["tokens"]["access"]),
                cash_c=api("greenlife", login("greenlife", "c@green.test", PW).data["tokens"]["access"]))


def ids(resp):
    return {r["id"] for r in resp.data["results"]}


# ---------- branches ----------
def test_admin_creates_branch_and_codes_unique_per_tenant(env):
    r = env["admin_g"].post("/api/v1/branches/", {"name": "North", "code": "north"}, format="json")
    assert r.status_code == 201 and r.data["code"] == "NORTH"
    assert env["admin_g"].post("/api/v1/branches/", {"name": "N2", "code": "NORTH"}, format="json").status_code == 400
    assert env["admin_b"].post("/api/v1/branches/", {"name": "N", "code": "NORTH"}, format="json").status_code == 201  # other tenant ok
    assert AuditLog.objects.filter(action="branch.created").exists()


def test_branch_visibility_by_tenant_and_scope(env):
    assert len(env["admin_g"].get("/api/v1/branches/").data["results"]) == 2
    assert ids(env["mgr_c"].get("/api/v1/branches/")) == {env["main"].pk}  # branch manager: own branch only
    assert env["admin_b"].get(f"/api/v1/branches/{env['main'].pk}/").status_code == 404  # other tenant: invisible
    assert env["mgr_c"].get(f"/api/v1/branches/{env['second'].pk}/").status_code == 404  # other branch: invisible


def test_branch_write_needs_permission_and_valid_manager(env):
    assert env["mgr_c"].post("/api/v1/branches/", {"name": "X", "code": "X"}, format="json").status_code == 403
    assert env["cash_c"].get("/api/v1/branches/").status_code == 403  # cashier lacks branch.view
    other = User.objects.get(email="a@blue.test")
    r = env["admin_g"].patch(f"/api/v1/branches/{env['main'].pk}/", {"manager": other.pk}, format="json")
    assert r.status_code == 400  # manager from another tenant rejected
    assert env["admin_g"].patch(f"/api/v1/branches/{env['main'].pk}/", {"manager": env["mgr"].pk}, format="json").status_code == 200


# ---------- staff ----------
def test_admin_creates_staff_with_invitation_email(env):
    r = env["admin_g"].post("/api/v1/staff/", {"email": "ph@green.test", "full_name": "Pat Pharm", "role": "pharmacist", "branch": env["main"].pk}, format="json")
    assert r.status_code == 201, r.data
    assert "password" not in str(r.data).lower().replace("must_change_password", "")
    u = User.objects.get(email="ph@green.test")
    assert u.tenant == env["g"] and u.must_change_password and not u.has_usable_password()
    assert "accept-invitation?token=" in mail.outbox[-1].body
    assert {"staff.created", "auth.credentials_issued"} <= set(AuditLog.objects.values_list("action", flat=True))


def test_staff_temp_password_option(env):
    r = env["admin_g"].post("/api/v1/staff/", {"email": "t@green.test", "full_name": "Tee", "role": "cashier", "branch": env["main"].pk, "use_invitation": False}, format="json")
    assert r.status_code == 201
    assert "Temporary password" in mail.outbox[-1].body


def test_staff_validation(env):
    c = env["admin_g"]
    base = {"email": "x@green.test", "full_name": "X"}
    assert c.post("/api/v1/staff/", {**base, "role": "cashier"}, format="json").status_code == 400  # branch required
    assert c.post("/api/v1/staff/", {**base, "role": "customer", "branch": env["main"].pk}, format="json").status_code == 400
    assert c.post("/api/v1/staff/", {**base, "role": "cashier", "branch": 999999}, format="json").status_code == 400
    assert c.post("/api/v1/staff/", {"email": "m@green.test", "full_name": "Dup", "role": "cashier", "branch": env["main"].pk}, format="json").status_code == 400
    # same email allowed in a different pharmacy
    assert env["admin_b"].post("/api/v1/staff/", {"email": "m@green.test", "full_name": "Other", "role": "cashier",
                                                  "branch": Branch.all_objects.filter(tenant=env["b"]).first().pk}, format="json").status_code == 201


def test_cross_tenant_branch_and_role_rejected(env):
    blue_branch = Branch.all_objects.filter(tenant=env["b"]).first()
    r = env["admin_g"].post("/api/v1/staff/", {"email": "y@green.test", "full_name": "Y", "role": "cashier", "branch": blue_branch.pk}, format="json")
    assert r.status_code == 400
    assert env["admin_g"].patch(f"/api/v1/roles/{env['b'].roles.get(code='cashier').pk}/", {"permissions": []}, format="json").status_code == 404


def test_branch_manager_staff_scope_and_no_escalation(env):
    m = env["mgr_c"]
    assert ids(m.get("/api/v1/staff/")) == {env["mgr"].pk}  # sees only own branch (cashier is in branch 2)
    ok = m.post("/api/v1/staff/", {"email": "t2@green.test", "full_name": "T", "role": "pharmacy_technician", "branch": env["main"].pk}, format="json")
    assert ok.status_code == 201
    assert m.post("/api/v1/staff/", {"email": "t3@green.test", "full_name": "T", "role": "cashier", "branch": env["second"].pk}, format="json").status_code == 400  # other branch
    assert m.post("/api/v1/staff/", {"email": "a2@green.test", "full_name": "A", "role": "pharmacy_admin", "branch": env["main"].pk}, format="json").status_code == 400  # escalation
    assert m.post("/api/v1/staff/", {"email": "p2@green.test", "full_name": "P", "role": "pharmacist", "branch": env["main"].pk}, format="json").status_code == 400  # more access than manager
    assert m.patch(f"/api/v1/staff/{env['cash'].pk}/", {"full_name": "Hack"}, format="json").status_code == 404  # other branch's staff


def test_cashier_cannot_manage_staff(env):
    assert env["cash_c"].get("/api/v1/staff/").status_code == 403
    assert env["cash_c"].post("/api/v1/staff/", {}, format="json").status_code == 403


def test_role_change_and_deactivation_revoke_sessions(env):
    old_token_client = env["cash_c"]
    assert old_token_client.get("/api/v1/auth/me/").status_code == 200
    r = env["admin_g"].patch(f"/api/v1/staff/{env['cash'].pk}/", {"is_active": False}, format="json")
    assert r.status_code == 200
    assert old_token_client.get("/api/v1/auth/me/").status_code == 401
    assert login("greenlife", "c@green.test", PW).status_code == 401
    assert "staff.deactivated" in set(AuditLog.objects.values_list("action", flat=True))
    r = env["admin_g"].patch(f"/api/v1/staff/{env['cash'].pk}/", {"is_active": True, "role": "inventory_officer"}, format="json")
    assert r.status_code == 200 and "staff.role_changed" in set(AuditLog.objects.values_list("action", flat=True))


def test_cannot_change_own_role_or_deactivate_self(env):
    me = User.objects.get(email="a@green.test")
    assert env["admin_g"].patch(f"/api/v1/staff/{me.pk}/", {"is_active": False}, format="json").status_code == 400


# ---------- roles ----------
def test_role_permissions_editing_rules(env):
    cashier_role = env["g"].roles.get(code="cashier")
    admin_role = env["g"].roles.get(code="pharmacy_admin")
    c = env["admin_g"]
    assert c.patch(f"/api/v1/roles/{admin_role.pk}/", {"permissions": []}, format="json").status_code == 403
    assert c.patch(f"/api/v1/roles/{cashier_role.pk}/", {"permissions": ["nope.nope"]}, format="json").status_code == 400
    assert c.patch(f"/api/v1/roles/{cashier_role.pk}/", {"permissions": ["pos.sell", "sales.view_own"]}, format="json").status_code == 200
    assert env["cash_c"].get("/api/v1/auth/me/").status_code == 401  # sessions revoked so the change applies at once
    assert env["mgr_c"].patch(f"/api/v1/roles/{cashier_role.pk}/", {"permissions": []}, format="json").status_code == 403  # no role.manage
    assert AuditLog.objects.filter(action="role.permissions_changed").exists()


# ---------- settings / dashboard ----------
def test_settings_only_own_pharmacy_and_protected_fields(env):
    r = env["admin_g"].patch("/api/v1/tenants/me/", {"primary_color": "#112233", "slug": "hijack", "status": "suspended", "name": "Renamed"}, format="json")
    assert r.status_code == 200
    g = Pharmacy.objects.get(pk=env["g"].pk)
    assert g.primary_color == "#112233" and g.slug == "greenlife" and g.status == "active" and g.name == "Green Life Pharmacy"
    assert Pharmacy.objects.get(pk=env["b"].pk).primary_color != "#112233"
    assert env["admin_g"].patch("/api/v1/tenants/me/", {"primary_color": "red"}, format="json").status_code == 400
    assert env["mgr_c"].patch("/api/v1/tenants/me/", {"primary_color": "#000000"}, format="json").status_code == 403


def test_tenant_dashboard_counts_and_scope(env):
    d = env["admin_g"].get("/api/v1/tenants/dashboard/").data
    assert d["scope"] == "pharmacy" and d["branches"] == 2 and d["employees"] == 3
    m = env["mgr_c"].get("/api/v1/tenants/dashboard/").data
    assert m["scope"] == "branch" and m["branches"] == 1 and m["employees"] == 1
    assert env["admin_b"].get("/api/v1/tenants/dashboard/").data["branches"] == 1
    assert api().get("/api/v1/tenants/dashboard/").status_code == 401
