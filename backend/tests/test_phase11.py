import calendar
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.core.tenant_context import tenant_context
from apps.hr.models import DisciplinaryRecord, StaffProfile
from apps.payroll import services as payroll
from apps.payroll.models import PayrollLine

from .test_foundation import api, login, platform_admin, platform_client, register, settled_token, two_pharmacies  # noqa: F401
from .test_phase7 import PW, env  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Dec = Decimal
TODAY = lambda: timezone.localdate()  # noqa: E731
PERIOD = lambda: TODAY().strftime("%Y-%m")  # noqa: E731
PDF = b"%PDF-1.4\nx"
A = "/api/v1/accounting"


@pytest.fixture
def hr(env):
    g = env["g"]
    for k, role in (("hrm", "hr_manager"), ("acct", "accountant")):
        User.objects.create_user(f"{k}@green.test", PW, tenant=g, full_name=k.upper(), role=g.roles.get(code=role))
        env[k] = api("greenlife", login("greenlife", f"{k}@green.test", PW).data["tokens"]["access"])
    start = str(TODAY() - timedelta(days=120))
    env["uid"] = {k: User.objects.get(email=f"{k}@green.test").pk for k in ("c1", "c2", "c3", "mgr", "ph", "tech", "hrm")}
    for k in ("c1", "c2", "c3", "mgr"):
        r = env["hrm"].post("/api/v1/hr/staff/", {"user": env["uid"][k], "employment_date": start, "job_title": k}, format="json")
        assert r.status_code == 201, r.data
    return env


def cfg(c, **kw):
    body = {"pension_employee_pct": "5", "pension_employer_pct": "10", "tax_brackets": [{"up_to": "500", "rate": "0"}, {"up_to": "1000", "rate": "10"}, {"up_to": None, "rate": "20"}], **kw}
    r = c.put("/api/v1/payroll/config/", body, format="json")
    assert r.status_code == 200, r.data


def structure(c, uid, basic="1200", items=None, eff=None, status=201):
    r = c.post("/api/v1/payroll/structures/", {"user": uid, "basic_salary": basic, "effective_from": str(eff or TODAY() - timedelta(days=100)), "items": items or []}, format="json")
    assert r.status_code == status, r.data
    return r


def components(c):
    ids = {}
    for name, kind, calc in (("Transport", "earning", "fixed"), ("Housing", "earning", "percent_basic"), ("Union dues", "deduction", "fixed")):
        ids[name] = c.post("/api/v1/payroll/components/", {"name": name, "kind": kind, "calc": calc}, format="json").data["id"]
    return ids


def line_for(run, uid):
    return next(l for l in run["lines"] if l["user"] == uid)


def tb(c):
    rows = {r["code"]: Dec(str(r["debit"])) - Dec(str(r["credit"])) for r in c.get(f"{A}/reports/trial-balance/").data["rows"]}
    return rows


# ---------------- staff records ----------------
def test_staff_records_scope_and_creation_rules(hr):
    r = hr["hrm"].get("/api/v1/hr/staff/").data["results"]
    assert len(r) == 4 and all(x["staff_id"].startswith("STF-") for x in r)
    assert hr["hrm"].post("/api/v1/hr/staff/", {"user": hr["uid"]["c1"], "employment_date": str(TODAY())}, format="json").status_code == 400  # already has a record
    assert hr["hrm"].post("/api/v1/hr/staff/", {"user": hr["uid"]["ph"], "employment_date": str(TODAY()), "staff_id": r[0]["staff_id"]}, format="json").status_code == 400  # staff ID unique
    cust = User.objects.create_user("cust@green.test", PW, tenant=hr["g"], full_name="C", role=hr["g"].roles.get(code="customer"))
    assert hr["hrm"].post("/api/v1/hr/staff/", {"user": cust.pk, "employment_date": str(TODAY())}, format="json").status_code == 404  # customers are not staff
    assert {x["user"] for x in hr["mgr"].get("/api/v1/hr/staff/").data["results"]} == {hr["uid"]["c1"], hr["uid"]["c2"], hr["uid"]["mgr"]}  # own branch only
    assert hr["mgr"].get(f"/api/v1/hr/staff/{hr['uid']['c3']}/").status_code == 404
    assert hr["c1"].get("/api/v1/hr/staff/").status_code == 403 and hr["admin_b"].get("/api/v1/hr/staff/").data["count"] == 0
    assert hr["mgr"].post("/api/v1/hr/staff/", {"user": hr["uid"]["c3"], "employment_date": str(TODAY())}, format="json").status_code == 404  # other branch's user is invisible
    p = hr["hrm"].patch(f"/api/v1/hr/staff/{hr['uid']['c1']}/", {"job_title": "Senior cashier", "department": "Front of house"}, format="json")
    assert p.status_code == 200 and p.data["job_title"] == "Senior cashier"


def test_termination_revokes_access_and_is_restricted(hr):
    c2_token_client = api("greenlife", login("greenlife", "c2@green.test", PW).data["tokens"]["access"])
    assert c2_token_client.get("/api/v1/auth/me/").status_code == 200
    uid = hr["uid"]["c2"]
    assert hr["mgr"].post(f"/api/v1/hr/staff/{uid}/terminate/", {"reason": "x"}, format="json").status_code == 403  # needs hr.sensitive
    assert hr["hrm"].post(f"/api/v1/hr/staff/{uid}/terminate/", {}, format="json").status_code == 400  # reason required
    assert hr["hrm"].post(f"/api/v1/hr/staff/{uid}/terminate/", {"reason": "Resigned"}, format="json").data["employment_status"] == "terminated"
    assert c2_token_client.get("/api/v1/auth/me/").status_code == 401 and login("greenlife", "c2@green.test", PW).status_code == 401
    assert hr["hrm"].post(f"/api/v1/hr/staff/{uid}/terminate/", {"reason": "again"}, format="json").status_code == 409
    assert hr["hrm"].patch(f"/api/v1/hr/staff/{uid}/", {"job_title": "x"}, format="json").status_code == 400
    assert "hr.terminated" in set(AuditLog.objects.values_list("action", flat=True))
    assert hr["hrm"].post(f"/api/v1/hr/staff/{hr['uid']['hrm']}/terminate/", {"reason": "x"}, format="json").status_code == 404  # an HR user without a staff record cannot be terminated through this endpoint


def test_documents_and_disciplinary_records_are_hr_sensitive(hr):
    uid = hr["uid"]["c1"]
    up = lambda f: hr["hrm"].post(f"/api/v1/hr/staff/{uid}/documents/", {"file": f, "title": "Contract", "doc_type": "contract"}, format="multipart")  # noqa: E731
    assert up(SimpleUploadedFile("c.pdf", b"not a pdf", "application/pdf")).status_code == 400
    doc = up(SimpleUploadedFile("c.pdf", PDF, "application/pdf"))
    assert doc.status_code == 201
    dl = hr["hrm"].get(f"/api/v1/hr/documents/{doc.data['id']}/download/")
    assert dl.status_code == 200 and b"".join(dl.streaming_content).startswith(b"%PDF") and dl["Cache-Control"] == "private, no-store"
    assert "hr.document_viewed" in set(AuditLog.objects.values_list("action", flat=True))
    for client in (hr["mgr"], hr["c1"], hr["acct"]):  # branch managers have hr.view/manage but not hr.sensitive
        assert client.get(f"/api/v1/hr/documents/{doc.data['id']}/download/").status_code == 403
        assert client.get(f"/api/v1/hr/staff/{uid}/documents/").status_code == 403
        assert client.get(f"/api/v1/hr/staff/{uid}/disciplinary/").status_code == 403
    assert hr["hrm"].post(f"/api/v1/hr/staff/{uid}/disciplinary/", {"date": str(TODAY()), "category": "Lateness", "description": "Late three times"}, format="json").status_code == 201
    assert hr["hrm"].post(f"/api/v1/hr/staff/{uid}/disciplinary/", {"date": str(TODAY()), "category": "", "description": ""}, format="json").status_code == 400
    assert len(hr["hrm"].get(f"/api/v1/hr/staff/{uid}/disciplinary/").data) == 1
    with tenant_context(hr["g"]):
        rec = DisciplinaryRecord.objects.get()
        rec.description = "edited"
        with pytest.raises(PermissionError):
            rec.save()
        with pytest.raises(PermissionError):
            rec.delete()
    assert hr["admin_b"].get(f"/api/v1/hr/documents/{doc.data['id']}/download/").status_code == 404


# ---------------- attendance, shifts, leave ----------------
def test_attendance_clock_in_out_and_corrections(hr):
    hr["admin"].patch("/api/v1/tenants/me/", {"settings": {"workday_start": "00:00", "late_grace_minutes": 0}}, format="json")
    r = hr["c1"].post("/api/v1/hr/attendance/clock-in/")
    assert r.status_code == 201 and r.data["status"] == "late"  # after a 00:00 start with no grace
    assert hr["c1"].post("/api/v1/hr/attendance/clock-in/").status_code == 409
    assert hr["c1"].post("/api/v1/hr/attendance/clock-out/").status_code == 201
    assert hr["c1"].post("/api/v1/hr/attendance/clock-out/").status_code == 409
    assert hr["c2"].post("/api/v1/hr/attendance/clock-out/").status_code == 409  # never clocked in
    hr["admin"].patch("/api/v1/tenants/me/", {"settings": {"workday_start": "23:59", "late_grace_minutes": 0}}, format="json")
    assert hr["c2"].post("/api/v1/hr/attendance/clock-in/").data["status"] == "present"
    assert hr["c1"].post("/api/v1/hr/attendance/manual/", {"user": hr["uid"]["c2"], "date": str(TODAY()), "status": "absent"}, format="json").status_code == 403
    y = str(TODAY() - timedelta(days=1))
    m = hr["mgr"].post("/api/v1/hr/attendance/manual/", {"user": hr["uid"]["c2"], "date": y, "status": "absent", "note": "No call"}, format="json")
    assert m.status_code == 201 and m.data["source"] == "manual"
    assert hr["mgr"].post("/api/v1/hr/attendance/manual/", {"user": hr["uid"]["c3"], "date": y, "status": "absent"}, format="json").status_code == 404  # other branch
    assert hr["mgr"].post("/api/v1/hr/attendance/manual/", {"user": hr["uid"]["c2"], "date": str(TODAY() + timedelta(days=1)), "status": "present"}, format="json").status_code == 400
    assert {a["name"] for a in hr["mgr"].get("/api/v1/hr/attendance/").data["results"]} == {"C1", "C2"}
    assert [a["status"] for a in hr["c1"].get("/api/v1/hr/me/attendance/").data["results"]] == ["late"]  # staff see only their own
    assert "hr.attendance_adjusted" in set(AuditLog.objects.values_list("action", flat=True))


def test_work_shift_scheduling(hr):
    body = {"user": hr["uid"]["c1"], "branch": hr["main"].pk, "date": str(TODAY() + timedelta(days=1)), "start_time": "08:00", "end_time": "16:00"}
    assert hr["mgr"].post("/api/v1/hr/shifts/", body, format="json").status_code == 201
    assert hr["mgr"].post("/api/v1/hr/shifts/", {**body, "start_time": "15:00", "end_time": "20:00"}, format="json").status_code == 400  # overlap
    assert hr["mgr"].post("/api/v1/hr/shifts/", {**body, "end_time": "07:00"}, format="json").status_code == 400
    assert hr["mgr"].post("/api/v1/hr/shifts/", {**body, "user": hr["uid"]["c3"], "branch": hr["second"].pk}, format="json").status_code == 404
    assert hr["c1"].post("/api/v1/hr/shifts/", body, format="json").status_code == 403
    assert len(hr["c1"].get("/api/v1/hr/me/shifts/").data["results"]) == 1 and hr["c2"].get("/api/v1/hr/me/shifts/").data["count"] == 0


def test_leave_requests_balances_and_approval_rules(hr):
    types = {t["name"]: t["id"] for t in hr["hrm"].get("/api/v1/hr/leave-types/").data}
    assert {"Annual leave", "Sick leave", "Unpaid leave"} <= set(types)
    s, e = TODAY() + timedelta(days=10), TODAY() + timedelta(days=14)
    body = {"leave_type": types["Annual leave"], "start_date": str(s), "end_date": str(e), "reason": "Family"}
    r = hr["c1"].post("/api/v1/hr/me/leave/", body, format="json")
    assert r.status_code == 201 and r.data["days"] == 5 and r.data["status"] == "pending"
    assert hr["c1"].post("/api/v1/hr/me/leave/", {**body, "start_date": str(s + timedelta(days=2)), "end_date": str(e + timedelta(days=3))}, format="json").status_code == 400  # overlap
    assert hr["c1"].post("/api/v1/hr/me/leave/", {**body, "start_date": str(TODAY() + timedelta(days=60)), "end_date": str(TODAY() + timedelta(days=100))}, format="json").status_code == 400  # exceeds 21 days
    assert hr["c1"].post("/api/v1/hr/me/leave/", {**body, "end_date": str(s - timedelta(days=1))}, format="json").status_code == 400
    assert hr["c1"].post(f"/api/v1/hr/leave/{r.data['id']}/approve/").status_code == 403  # cashiers cannot decide
    assert hr["c3"].post("/api/v1/hr/leave/1/approve/").status_code == 403
    assert hr["mgr"].post(f"/api/v1/hr/leave/{r.data['id']}/approve/", {"note": "Enjoy"}, format="json").data["status"] == "approved"
    assert hr["mgr"].post(f"/api/v1/hr/leave/{r.data['id']}/approve/", {}, format="json").status_code == 409
    bal = {b["name"]: b for b in hr["c1"].get("/api/v1/hr/me/leave/").data["balances"]}
    assert bal["Annual leave"]["used"] == 5 and bal["Annual leave"]["remaining"] == 16
    # decisions stay inside the manager's branch; nobody decides their own request
    other = hr["c3"].post("/api/v1/hr/me/leave/", body, format="json").data["id"]
    assert hr["mgr"].post(f"/api/v1/hr/leave/{other}/approve/").status_code == 404
    own = hr["mgr"].post("/api/v1/hr/me/leave/", body, format="json").data["id"]
    assert hr["mgr"].post(f"/api/v1/hr/leave/{own}/approve/").status_code == 403
    assert hr["hrm"].post(f"/api/v1/hr/leave/{own}/approve/").data["status"] == "approved"  # HR (pharmacy level) decides a manager's request
    assert hr["admin"].post(f"/api/v1/hr/leave/{other}/reject/", {"note": "Busy period"}, format="json").data["status"] == "rejected"
    assert hr["c1"].post(f"/api/v1/hr/me/leave/{r.data['id']}/cancel/").data["status"] == "cancelled"  # approved leave that has not started
    assert hr["c2"].post(f"/api/v1/hr/me/leave/{r.data['id']}/cancel/").status_code == 404


# ---------------- payroll configuration and structures ----------------
def test_config_validation_and_tax_calculation():
    from decimal import Decimal as D
    br = [(D(500), D(0)), (D(1000), D(10)), (None, D(20))]
    assert payroll.income_tax(D(300), br) == 0 and payroll.income_tax(D(1000), br) == D("50.00") and payroll.income_tax(D(1360), br) == D("122.00") and payroll.income_tax(D(0), br) == 0
    from rest_framework.exceptions import ValidationError
    for bad in ({"pension_employee_pct": "120"}, {"tax_brackets": [{"up_to": "500", "rate": "5"}, {"up_to": "400", "rate": "5"}]}, {"tax_brackets": [{"up_to": None, "rate": "5"}, {"up_to": "400", "rate": "5"}]}, {"tax_brackets": [{"up_to": "1", "rate": "101"}]}):
        with pytest.raises(ValidationError):
            payroll.validate_config(bad)


def test_structures_are_versioned_confidential_and_permissioned(hr):
    cfg(hr["hrm"])
    comp = components(hr["hrm"])
    items = [{"component": comp["Transport"], "value": "100"}, {"component": comp["Housing"], "value": "10"}, {"component": comp["Union dues"], "value": "20"}]
    structure(hr["hrm"], hr["uid"]["c1"], "1200", items)
    structure(hr["hrm"], hr["uid"]["c1"], "1200", status=400)  # same effective date
    structure(hr["hrm"], hr["uid"]["c1"], "1500", eff=TODAY() - timedelta(days=10))  # a raise is a NEW version
    assert [s["basic_salary"] for s in hr["hrm"].get(f"/api/v1/payroll/structures/?user={hr['uid']['c1']}").data] == [Dec("1500.00"), Dec("1200.00")]
    structure(hr["hrm"], hr["uid"]["c1"], "-5", eff=TODAY(), status=400)
    for client in (hr["c1"], hr["ph"], hr["tech"]):
        assert client.get("/api/v1/payroll/structures/").status_code == 403 and client.post("/api/v1/payroll/structures/", {}, format="json").status_code == 403
    assert hr["mgr"].post("/api/v1/payroll/structures/", {"user": hr["uid"]["c1"], "basic_salary": "1", "effective_from": str(TODAY())}, format="json").status_code == 403  # view only
    assert {s["user"] for s in hr["mgr"].get("/api/v1/payroll/structures/").data} == {hr["uid"]["c1"]}  # branch-scoped view
    structure(hr["hrm"], hr["uid"]["c3"], "900")
    assert hr["mgr"].get(f"/api/v1/payroll/structures/?user={hr['uid']['c3']}").data == []  # another branch's salary is invisible
    assert hr["c1"].get("/api/v1/hr/me/salary/").data["current"]["basic_salary"] == Dec("1500.00") and hr["c2"].get("/api/v1/hr/me/salary/").data["current"] is None
    meta = json.dumps(list(AuditLog.objects.filter(action="payroll.salary_structure_changed").values_list("metadata", flat=True)))
    assert "1200" not in meta and "1500" not in meta  # audit proves WHO changed pay, never exposes amounts
    assert hr["admin_b"].get("/api/v1/payroll/structures/").data == []


# ---------------- payroll runs ----------------
def setup_pay(hr):
    cfg(hr["hrm"])
    comp = components(hr["hrm"])
    structure(hr["hrm"], hr["uid"]["c1"], "1200", [{"component": comp["Transport"], "value": "100"}, {"component": comp["Housing"], "value": "10"}, {"component": comp["Union dues"], "value": "20"}])
    structure(hr["hrm"], hr["uid"]["c3"], "900")


def new_run(hr, **kw):
    r = hr["hrm"].post("/api/v1/payroll/runs/", {"period": PERIOD(), **kw}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def test_calculation_matches_hand_computation(hr):
    setup_pay(hr)
    run = new_run(hr)
    l = line_for(run, hr["uid"]["c1"])
    assert (Dec(str(l["basic"])), Dec(str(l["allowances"])), Dec(str(l["gross"]))) == (Dec("1200.00"), Dec("220.00"), Dec("1420.00"))
    assert (Dec(str(l["pension_employee"])), Dec(str(l["tax"])), Dec(str(l["other_deductions"])), Dec(str(l["net"]))) == (Dec("60.00"), Dec("122.00"), Dec("20.00"), Dec("1218.00"))
    l3 = line_for(run, hr["uid"]["c3"])  # basic 900: pension 45, taxable 855 -> tax 35.50
    assert (Dec(str(l3["gross"])), Dec(str(l3["tax"])), Dec(str(l3["net"]))) == (Dec("900.00"), Dec("35.50"), Dec("819.50"))
    assert len(run["lines"]) == 2  # staff without a structure (c2, mgr) are not paid
    detail = hr["hrm"].get(f"/api/v1/payroll/lines/{l['id']}/payslip/")
    assert detail.status_code == 404  # draft runs have no payslips


def test_proration_and_unpaid_leave(hr):
    setup_pay(hr)
    first_of_this = TODAY().replace(day=1)
    prev_last = first_of_this - timedelta(days=1)
    period = prev_last.strftime("%Y-%m")
    days = calendar.monthrange(prev_last.year, prev_last.month)[1]
    with tenant_context(hr["g"]):
        StaffProfile.objects.filter(user_id=hr["uid"]["c3"]).update(employment_date=prev_last.replace(day=16))
    run = hr["hrm"].post("/api/v1/payroll/runs/", {"period": period}, format="json").data
    expected = (Dec(900) * Dec(days - 15) / Dec(days)).quantize(Dec("0.01"))
    assert Dec(str(line_for(run, hr["uid"]["c3"])["basic"])) == expected  # joined on the 16th
    hr["hrm"].post(f"/api/v1/payroll/runs/{run['id']}/cancel/")
    # approved unpaid leave reduces basic pay
    types = {t["name"]: t["id"] for t in hr["hrm"].get("/api/v1/hr/leave-types/").data}
    lv = hr["c1"].post("/api/v1/hr/me/leave/", {"leave_type": types["Unpaid leave"], "start_date": str(prev_last.replace(day=1)), "end_date": str(prev_last.replace(day=3))}, format="json")
    assert lv.status_code == 201
    hr["mgr"].post(f"/api/v1/hr/leave/{lv.data['id']}/approve/")
    run2 = hr["hrm"].post("/api/v1/payroll/runs/", {"period": period}, format="json").data
    assert Dec(str(line_for(run2, hr["uid"]["c1"])["basic"])) == (Dec(1200) * Dec(days - 3) / Dec(days)).quantize(Dec("0.01"))


def test_run_workflow_segregation_and_immutability(hr):
    setup_pay(hr)
    hr["hrm"].post("/api/v1/payroll/adjustments/", {"user": hr["uid"]["c1"], "period": PERIOD(), "kind": "bonus", "amount": "100", "note": "Target met", "taxable": False}, format="json")
    run = new_run(hr)
    assert hr["hrm"].post("/api/v1/payroll/runs/", {"period": PERIOD()}, format="json").status_code == 409  # one live run per period
    l = line_for(run, hr["uid"]["c1"])
    assert Dec(str(l["extras"])) == Dec("100.00") and Dec(str(l["gross"])) == Dec("1520.00") and Dec(str(l["tax"])) == Dec("122.00")  # non-taxable bonus does not change tax
    assert hr["hrm"].post(f"/api/v1/payroll/runs/{run['id']}/approve/").status_code == 403  # HR cannot approve
    assert hr["admin"].post(f"/api/v1/payroll/runs/{run['id']}/approve/").status_code == 409  # not submitted yet
    assert hr["hrm"].post(f"/api/v1/payroll/runs/{run['id']}/submit/").data["status"] == "submitted"
    assert hr["hrm"].post(f"/api/v1/payroll/runs/{run['id']}/recalculate/").status_code == 409
    assert hr["mgr"].post(f"/api/v1/payroll/runs/{run['id']}/approve/").status_code == 403
    ok = hr["admin"].post(f"/api/v1/payroll/runs/{run['id']}/approve/")
    assert ok.status_code == 200 and ok.data["status"] == "approved"
    assert hr["admin"].post(f"/api/v1/payroll/runs/{run['id']}/approve/").status_code == 409
    assert hr["hrm"].post(f"/api/v1/payroll/runs/{run['id']}/cancel/").status_code == 409
    assert hr["hrm"].post("/api/v1/payroll/adjustments/", {"user": hr["uid"]["c1"], "period": PERIOD(), "kind": "bonus", "amount": "5", "note": "late"}, format="json").status_code == 400
    # a creator can never approve their own run
    hr["admin"].post(f"/api/v1/payroll/runs/{run['id']}/cancel/")
    assert {"payroll.run_created", "payroll.run_submitted", "payroll.run_approved"} <= set(AuditLog.objects.values_list("action", flat=True))


def test_creator_cannot_approve_own_run(hr):
    setup_pay(hr)
    run = hr["admin"].post("/api/v1/payroll/runs/", {"period": PERIOD()}, format="json").data
    hr["admin"].post(f"/api/v1/payroll/runs/{run['id']}/submit/")
    assert hr["admin"].post(f"/api/v1/payroll/runs/{run['id']}/approve/").status_code == 403


def test_approval_posts_to_the_ledger_and_payments_clear_it(hr):
    setup_pay(hr)
    run = new_run(hr)
    hr["hrm"].post(f"/api/v1/payroll/runs/{run['id']}/submit/")
    hr["admin"].post(f"/api/v1/payroll/runs/{run['id']}/approve/")
    acct = hr["acct"]
    rows = tb(acct)
    gross, net, tax = Dec("1420") + Dec("900"), Dec("1218") + Dec("819.50"), Dec("122") + Dec("35.50")
    pension_e, pension_r = Dec("60") + Dec("45"), Dec("120") + Dec("90")
    assert rows["6000"] == gross + pension_r and rows["2300"] == -net and rows["2310"] == -tax and rows["2320"] == -(pension_e + pension_r) and rows["2330"] == -Dec("20")
    assert acct.get(f"{A}/reports/integrity/").data["trial_balance_balanced"] is True
    bs = {r["name"]: Dec(str(r["operating_expenses"])) for r in acct.get(f"{A}/reports/branch-summary/").data}
    assert bs["Main Branch"] == Dec("1420") + Dec("120") and bs["Second"] == Dec("900") + Dec("90")  # salary cost lands on each person's branch
    l1 = line_for(run, hr["uid"]["c1"])["id"]
    pay = lambda amt, ref, m="bank_transfer": hr["hrm"].post(f"/api/v1/payroll/lines/{l1}/pay/", {"amount": amt, "method": m, "reference": ref}, format="json")  # noqa: E731
    assert pay("1300", "S-1").status_code == 400 and pay("100", "").status_code == 400 and pay("100", "S-1", "voucher").status_code == 400
    assert pay("1000", "S-1").status_code == 201
    assert pay("10", "S-1").status_code == 400  # duplicate reference
    assert hr["c1"].post(f"/api/v1/payroll/lines/{l1}/pay/", {"amount": "1", "method": "cash", "reference": "x"}, format="json").status_code == 403
    mails = len(mail.outbox)
    assert pay("218", "S-2").status_code == 201
    assert any("Salary slip" in m.subject and m.to == ["c1@green.test"] for m in mail.outbox[mails:]) and not any("1218" in m.body for m in mail.outbox[mails:])  # notified, amounts not emailed
    rows = tb(acct)
    assert rows["2300"] == -(Dec("819.50")) and rows["1020"] == -Dec("1218")
    l3 = line_for(run, hr["uid"]["c3"])["id"]
    hr["hrm"].post(f"/api/v1/payroll/lines/{l3}/pay/", {"amount": "819.50", "method": "mobile_money", "reference": "S-3"}, format="json")
    assert hr["hrm"].get(f"/api/v1/payroll/runs/{run['id']}/").data["status"] == "paid"
    assert tb(acct)["2300"] == 0


def test_payslips_visibility(hr):
    setup_pay(hr)
    run = new_run(hr)
    l1, l3 = line_for(run, hr["uid"]["c1"])["id"], line_for(run, hr["uid"]["c3"])["id"]
    assert hr["hrm"].get(f"/api/v1/payroll/lines/{l1}/payslip/").status_code == 404  # drafts are not payslips
    assert hr["c1"].get("/api/v1/hr/me/payslips/").data == []
    hr["hrm"].post(f"/api/v1/payroll/runs/{run['id']}/submit/")
    hr["admin"].post(f"/api/v1/payroll/runs/{run['id']}/approve/")
    mine = hr["c1"].get("/api/v1/hr/me/payslips/").data
    assert len(mine) == 1 and mine[0]["id"] == l1
    d = hr["c1"].get(f"/api/v1/hr/me/payslips/{l1}/")
    assert d.status_code == 200 and d.data["staff_name"] == "C1" and Dec(str(d.data["net"])) == Dec("1218.00")
    pdf = hr["c1"].get(f"/api/v1/hr/me/payslips/{l1}/pdf/")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and pdf["Cache-Control"] == "private, no-store"
    assert hr["c1"].get(f"/api/v1/hr/me/payslips/{l3}/").status_code == 404  # never anyone else's
    assert hr["c2"].get(f"/api/v1/hr/me/payslips/{l1}/").status_code == 404
    assert hr["mgr"].get(f"/api/v1/payroll/lines/{l1}/payslip/").status_code == 200 and hr["mgr"].get(f"/api/v1/payroll/lines/{l3}/payslip/").status_code == 404  # branch-scoped viewer
    runs = hr["mgr"].get("/api/v1/payroll/runs/").data["results"][0]
    assert runs["staff"] == 1 and Dec(str(runs["net"])) == Dec("1218.00")  # branch totals only
    assert [l["user"] for l in hr["mgr"].get(f"/api/v1/payroll/runs/{run['id']}/").data["lines"]] == [hr["uid"]["c1"]]
    assert hr["c1"].get("/api/v1/payroll/runs/").status_code == 403 and hr["c1"].get(f"/api/v1/payroll/lines/{l1}/payslip/").status_code == 403
    assert hr["admin_b"].get(f"/api/v1/payroll/lines/{l1}/payslip/").status_code == 404 and hr["admin_b"].get("/api/v1/payroll/runs/").data["count"] == 0
    assert "payroll.payslip_viewed" in set(AuditLog.objects.values_list("action", flat=True))


def test_salary_advances_are_recovered_through_payroll(hr):
    setup_pay(hr)
    body = {"user": hr["uid"]["c1"], "amount": "300", "monthly_recovery": "100", "method": "cash", "reference": "ADV-1"}
    assert hr["hrm"].post("/api/v1/payroll/advances/", body, format="json").status_code == 403  # cash out needs approver-level permission
    assert hr["admin"].post("/api/v1/payroll/advances/", {**body, "monthly_recovery": "500"}, format="json").status_code == 400
    adv = hr["admin"].post("/api/v1/payroll/advances/", body, format="json")
    assert adv.status_code == 201 and tb(hr["acct"])["1150"] == Dec("300")
    assert hr["admin"].post("/api/v1/payroll/advances/", body, format="json").status_code == 400  # duplicate reference
    run = new_run(hr)
    l = line_for(run, hr["uid"]["c1"])
    assert Dec(str(l["advance_recovery"])) == Dec("100.00") and Dec(str(l["net"])) == Dec("1118.00")
    hr["hrm"].post(f"/api/v1/payroll/runs/{run['id']}/submit/")
    hr["admin"].post(f"/api/v1/payroll/runs/{run['id']}/approve/")
    assert [a["balance"] for a in hr["admin"].get("/api/v1/payroll/advances/").data] == [Dec("200.00")]
    assert tb(hr["acct"])["1150"] == Dec("200")  # recovered portion left the asset
    assert hr["acct"].get(f"{A}/reports/integrity/").data["trial_balance_balanced"] is True


def test_terminated_and_unstructured_staff_are_excluded(hr):
    setup_pay(hr)
    hr["hrm"].post(f"/api/v1/hr/staff/{hr['uid']['c3']}/terminate/", {"reason": "Resigned", "date": str(TODAY() - timedelta(days=40))}, format="json")
    run = new_run(hr)
    assert [l["user"] for l in run["lines"]] == [hr["uid"]["c1"]]
    hr["hrm"].post(f"/api/v1/payroll/runs/{run['id']}/cancel/")
    assert hr["hrm"].post("/api/v1/payroll/runs/", {"period": "2999-01"}, format="json").status_code == 400  # future month
    assert hr["hrm"].post("/api/v1/payroll/runs/", {"period": "nonsense"}, format="json").status_code == 400
    scoped = hr["hrm"].post("/api/v1/payroll/runs/", {"period": PERIOD(), "branch": hr["second"].pk}, format="json")
    assert scoped.status_code == 400  # nobody eligible on that branch
    assert hr["hrm"].post("/api/v1/payroll/runs/", {"period": PERIOD(), "branch": hr["main"].pk}, format="json").status_code == 201
    assert hr["hrm"].post("/api/v1/payroll/runs/", {"period": PERIOD()}, format="json").status_code == 409  # a branch run already covers this period
    assert hr["mgr"].post("/api/v1/payroll/runs/", {"period": PERIOD()}, format="json").status_code == 403
