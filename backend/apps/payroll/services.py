"""Payroll engine and workflow. Salary data is highly confidential: every entry point here is reached only through permission-checked views,
runs are immutable once approved, every step is audited (WITHOUT salary amounts in the audit metadata) and money movements post to the ledger."""
import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.accounting.engine import pay_account, post_entry
from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation
from apps.core.tenant_context import get_current_tenant
from apps.hr.models import LeaveRequest, StaffProfile
from apps.notifications.services import render_branded_html, send_email

from .models import (PayrollAdjustment, PayrollLine, PayrollRun, SalaryAdvance, SalaryComponent, SalaryPayment, SalaryStructure, SalaryStructureItem, ZERO)

R = PayrollRun.Status


def q2(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------- configuration (tax brackets, pension) ----------------
def validate_config(cfg: dict) -> dict:
    """payroll config lives in tenant.settings['payroll']. Nothing statutory is hard-coded: the pharmacy enters the rates that apply to it."""
    if not isinstance(cfg, dict):
        raise ValidationError({"config": "Invalid configuration."})
    out = {}
    for k in ("pension_employee_pct", "pension_employer_pct"):
        v = Decimal(str(cfg.get(k, 0)))
        if v < 0 or v > 100:
            raise ValidationError({k: "Enter a percentage between 0 and 100."})
        out[k] = str(v)
    brackets, last = [], Decimal(-1)
    for b in cfg.get("tax_brackets", []):
        up = b.get("up_to")
        rate = Decimal(str(b.get("rate", 0)))
        if rate < 0 or rate > 100:
            raise ValidationError({"tax_brackets": "Rates must be between 0 and 100."})
        if up is not None:
            up = Decimal(str(up))
            if up <= last:
                raise ValidationError({"tax_brackets": "Brackets must have increasing upper limits."})
            last = up
        elif b is not cfg["tax_brackets"][-1]:
            raise ValidationError({"tax_brackets": "Only the last bracket may be open-ended."})
        brackets.append({"up_to": None if up is None else str(up), "rate": str(rate)})
    out["tax_brackets"] = brackets
    return out


def config() -> dict:
    cfg = (get_current_tenant().settings or {}).get("payroll") or {}
    return {"pension_employee_pct": Decimal(str(cfg.get("pension_employee_pct", 0))), "pension_employer_pct": Decimal(str(cfg.get("pension_employer_pct", 0))),
            "tax_brackets": [(None if b.get("up_to") is None else Decimal(str(b["up_to"])), Decimal(str(b.get("rate", 0)))) for b in cfg.get("tax_brackets", [])]}


def income_tax(taxable: Decimal, brackets) -> Decimal:
    tax, lower = ZERO, Decimal(0)
    for upper, rate in brackets:
        top = taxable if upper is None else min(taxable, upper)
        if top > lower:
            tax += (top - lower) * rate / 100
        if upper is None or taxable <= upper:
            break
        lower = upper
    return q2(tax)


# ---------------- salary structures ----------------
def structure_on(user, on: date):
    return SalaryStructure.objects.filter(user=user, effective_from__lte=on).prefetch_related("items__component").order_by("-effective_from").first()


@transaction.atomic
def set_structure(*, target: User, basic, items, effective_from: date, actor, note="") -> SalaryStructure:
    if basic < 0:
        raise ValidationError({"basic_salary": "Basic salary cannot be negative."})
    if target.role_id and target.role.code == "customer":
        raise ValidationError({"user": "Customers have no salary."})
    if SalaryStructure.objects.filter(user=target, effective_from=effective_from).exists():
        raise ValidationError({"effective_from": "A salary structure already exists for this date. Use a later effective date."})
    st = SalaryStructure.objects.create(user=target, basic_salary=basic, effective_from=effective_from, note=note[:200], created_by=actor)
    for it in items:
        comp = it["component"]
        if not comp.is_active:
            raise ValidationError({"items": f"{comp.name} is inactive."})
        if it["value"] < 0 or (comp.calc == SalaryComponent.Calc.PERCENT_BASIC and it["value"] > 100):
            raise ValidationError({"items": f"Invalid value for {comp.name}."})
        SalaryStructureItem.objects.create(structure=st, component=comp, value=it["value"])
    audit.record("payroll.salary_structure_changed", actor=actor, target=st, user=target.pk, effective_from=str(effective_from))  # amounts deliberately not logged
    return st


# ---------------- calculation ----------------
def period_bounds(period: str):
    try:
        y, m = int(period[:4]), int(period[5:7])
        assert period[4] == "-" and 1 <= m <= 12
    except (ValueError, AssertionError, IndexError):
        raise ValidationError({"period": "Use the format YYYY-MM."})
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def calculate_line(user: User, period: str, cfg: dict):
    first, last = period_bounds(period)
    prof = StaffProfile.objects.filter(user=user).first()
    if prof is None or prof.employment_date > last or (prof.employment_status == "terminated" and (prof.terminated_on is None or prof.terminated_on < first)):
        return None
    st = structure_on(user, last)
    if st is None:
        return None
    days = (last - first).days + 1
    start = max(first, prof.employment_date)
    end = prof.terminated_on if prof.terminated_on and prof.terminated_on < last else last
    worked = Decimal((end - start).days + 1) / days
    unpaid = 0
    for lv in LeaveRequest.objects.filter(user=user, status="approved", leave_type__is_paid=False, start_date__lte=end, end_date__gte=start):
        unpaid += (min(lv.end_date, end) - max(lv.start_date, start)).days + 1
    factor = max(Decimal(0), worked - Decimal(unpaid) / days)
    basic = q2(st.basic_salary * factor)
    earn, ded, allowances, taxable_allow, comp_ded = [{"name": "Basic salary", "amount": str(basic)}], [], ZERO, ZERO, ZERO
    for it in st.items.all():
        c = it.component
        amt = q2(basic * it.value / 100) if c.calc == "percent_basic" else q2(it.value * factor)
        if c.kind == "earning":
            allowances += amt
            taxable_allow += amt if c.taxable else ZERO
            earn.append({"name": c.name, "amount": str(amt)})
        else:
            comp_ded += amt
            ded.append({"name": c.name, "amount": str(amt)})
    extras = taxable_extra = adj_ded = ZERO
    adjustments = list(PayrollAdjustment.objects.filter(user=user, period=period, applied_run__isnull=True))
    for a in adjustments:
        if a.kind == "deduction":
            adj_ded += a.amount
            ded.append({"name": f"Deduction: {a.note}", "amount": str(a.amount)})
        else:
            extras += a.amount
            taxable_extra += a.amount if a.taxable else ZERO
            earn.append({"name": f"{a.kind.title()}: {a.note}", "amount": str(a.amount)})
    gross = basic + allowances + extras
    pension_e = q2(basic * cfg["pension_employee_pct"] / 100)
    pension_r = q2(basic * cfg["pension_employer_pct"] / 100)
    taxable_income = max(ZERO, basic + taxable_allow + taxable_extra - pension_e)  # employee pension is treated as deductible; check your local rules
    tax = min(income_tax(taxable_income, cfg["tax_brackets"]), gross - pension_e if gross > pension_e else ZERO)
    warnings = []
    other = comp_ded + adj_ded
    room = gross - tax - pension_e
    if other > room:
        warnings.append("Deductions exceeded available pay and were capped.")
        other = max(room, ZERO)
    room -= other
    recovery = ZERO
    for adv in SalaryAdvance.objects.filter(user=user, status="active").order_by("id"):
        take = min(adv.balance, adv.monthly_recovery, max(room - recovery, ZERO))
        recovery += take
    if recovery < sum((min(a.balance, a.monthly_recovery) for a in SalaryAdvance.objects.filter(user=user, status="active")), ZERO):
        warnings.append("Advance recovery was reduced to keep net pay non-negative.")
    if pension_e:
        ded.append({"name": "Employee pension", "amount": str(pension_e)})
    if tax:
        ded.append({"name": "Income tax", "amount": str(tax)})
    if recovery:
        ded.append({"name": "Salary advance recovery", "amount": str(recovery)})
    net = gross - tax - pension_e - other - recovery
    return {"user": user, "branch": user.branch, "basic": basic, "allowances": allowances, "extras": extras, "gross": gross, "taxable_income": taxable_income, "tax": tax,
            "pension_employee": pension_e, "pension_employer": pension_r, "other_deductions": other, "advance_recovery": recovery, "net": net,
            "details": {"earnings": earn, "deductions": ded, "worked_fraction": str(q2(factor))}, "warnings": warnings, "_adjustments": adjustments}


def _build_lines(run: PayrollRun):
    cfg = config()
    users = User.objects.filter(tenant=run.tenant, is_active=True).exclude(role__code="customer").select_related("branch", "role")
    if run.branch_id:
        users = users.filter(branch_id=run.branch_id)
    created = 0
    for u in users:
        data = calculate_line(u, run.period, cfg)
        if data is None:
            continue
        adjustments = data.pop("_adjustments")
        PayrollLine.objects.create(run=run, **data)
        for a in adjustments:
            a.applied_run = run
            a.save(update_fields=["applied_run", "updated_at"])
        created += 1
    if not created:
        raise ValidationError({"period": "No eligible staff with a salary structure for this period."})


@transaction.atomic
def create_run(*, period: str, branch, actor, note="") -> PayrollRun:
    first, last = period_bounds(period)
    if first > timezone.localdate():
        raise ValidationError({"period": "Payroll cannot be run for a future month."})
    scope = str(branch.pk) if branch else "all"
    live = PayrollRun.objects.filter(period=period).exclude(status=R.CANCELLED)
    if live.filter(scope_key="all").exists() or (scope == "all" and live.exists()) or live.filter(scope_key=scope).exists():
        raise BusinessRuleViolation("A payroll run already exists for this period and scope.")
    run = PayrollRun.objects.create(period=period, branch=branch, scope_key=scope, created_by=actor, note=note[:255])
    _build_lines(run)
    audit.record("payroll.run_created", actor=actor, target=run, period=period, scope=scope, staff=run.lines.count())
    return run


def _release(run):
    run.adjustments.update(applied_run=None)


@transaction.atomic
def recalculate(run_id, *, actor) -> PayrollRun:
    run = PayrollRun.objects.select_for_update(of=("self",)).get(pk=run_id)
    if run.status != R.DRAFT:
        raise BusinessRuleViolation("Only draft payroll runs can be recalculated.")
    _release(run)
    run.lines.all().delete()
    _build_lines(run)
    audit.record("payroll.run_recalculated", actor=actor, target=run, period=run.period)
    return run


@transaction.atomic
def submit(run_id, *, actor) -> PayrollRun:
    run = PayrollRun.objects.select_for_update(of=("self",)).get(pk=run_id)
    if run.status != R.DRAFT:
        raise BusinessRuleViolation("Only draft payroll runs can be submitted.")
    run.status = R.SUBMITTED
    run.save(update_fields=["status", "updated_at"])
    audit.record("payroll.run_submitted", actor=actor, target=run, period=run.period)
    return run


@transaction.atomic
def cancel(run_id, *, actor) -> PayrollRun:
    run = PayrollRun.objects.select_for_update(of=("self",)).get(pk=run_id)
    if run.status not in (R.DRAFT, R.SUBMITTED):
        raise BusinessRuleViolation("An approved payroll run cannot be cancelled.")
    _release(run)
    run.status = R.CANCELLED
    run.save(update_fields=["status", "updated_at"])
    audit.record("payroll.run_cancelled", actor=actor, target=run, period=run.period)
    return run


@transaction.atomic
def approve(run_id, *, actor) -> PayrollRun:
    run = PayrollRun.objects.select_for_update(of=("self",)).get(pk=run_id)
    if run.status != R.SUBMITTED:
        raise BusinessRuleViolation("Only submitted payroll runs can be approved.")
    if run.created_by_id == actor.pk:
        raise PermissionDenied("You cannot approve a payroll run you created.")
    lines = list(run.lines.select_related("user", "branch"))
    for ln in lines:  # consume advance balances in the same order the calculation used
        left = ln.advance_recovery
        for adv in SalaryAdvance.objects.select_for_update(of=("self",)).filter(user=ln.user, status="active").order_by("id"):
            if left <= 0:
                break
            take = min(adv.balance, adv.monthly_recovery, left)
            adv.balance -= take
            if adv.balance == 0:
                adv.status = SalaryAdvance.Status.CLEARED
            adv.save()
            left -= take
        if left > 0:
            raise BusinessRuleViolation(f"The salary advance of {ln.user.full_name} changed since calculation. Recalculate the run.")
    by_branch: dict = {}
    for ln in lines:
        by_branch.setdefault(ln.branch, []).append(ln)
    post_lines = []
    for b, group in by_branch.items():
        s = lambda f: sum((getattr(x, f) for x in group), ZERO)  # noqa: E731
        post_lines += [("6000", s("gross") + s("pension_employer"), 0, b), ("2300", 0, s("net"), b), ("2310", 0, s("tax"), b), ("2320", 0, s("pension_employee") + s("pension_employer"), b),
                       ("2330", 0, s("other_deductions"), b), ("1150", 0, s("advance_recovery"), b)]
    post_entry(description=f"Payroll {run.period}", lines=post_lines, source_type="payroll_run", source_id=run.pk, user=actor)
    run.status, run.approved_by, run.approved_at = R.APPROVED, actor, timezone.now()
    run.save()
    audit.record("payroll.run_approved", actor=actor, target=run, period=run.period)
    return run


# ---------------- payments ----------------
@transaction.atomic
def pay_line(line_id, *, amount: Decimal, method: str, reference: str, actor) -> SalaryPayment:
    line = PayrollLine.objects.select_for_update(of=("self",)).select_related("run", "user", "branch").get(pk=line_id)
    run = line.run
    if run.status != R.APPROVED:
        raise BusinessRuleViolation("Salaries can only be paid from an approved payroll run.")
    reference = reference.strip()
    if not reference or method not in ("cash", "bank", "bank_transfer", "mobile_money"):
        raise ValidationError({"detail": "Choose a payment method and enter a payment reference."})
    outstanding = line.net - line.paid_amount
    if amount <= 0 or amount > outstanding:
        raise ValidationError({"amount": f"Enter an amount up to the outstanding {outstanding}."})
    if SalaryPayment.objects.filter(reference=reference).exists():
        raise ValidationError({"reference": "This payment reference was already recorded."})
    pay = SalaryPayment.objects.create(line=line, amount=amount, method=method, reference=reference[:100], paid_by=actor)
    line.paid_amount += amount
    line.save(update_fields=["paid_amount", "updated_at"])
    post_entry(description=f"Salary payment {run.period} {line.user.full_name}", lines=[("2300", amount, 0, line.branch), (pay_account(method), 0, amount, line.branch)],
               source_type="salary_payment", source_id=pay.pk, user=actor, branch=line.branch)
    if not run.lines.filter(paid_amount__lt=models_F("net")).exists():
        run.status = R.PAID
        run.save(update_fields=["status", "updated_at"])
    audit.record("payroll.salary_paid", actor=actor, target=line, period=run.period, user=line.user_id, reference=reference)
    if line.paid_amount == line.net:
        t = get_current_tenant()
        body = f"Your salary for {run.period} has been paid. You can view and download your salary slip in your staff account."
        send_email(to=line.user.email, subject=f"Salary slip {run.period}", text=body, tenant=t, template="payroll_notification",
                   html_body=render_branded_html(title="Salary paid", pharmacy=t, paragraphs=[body]))  # no amounts in email
        from apps.notifications import inapp
        inapp.push([line.user], kind="payroll", level="success", title=f"Salary slip {run.period}", body="Your salary has been paid.", link="/my-work")
    return pay


from django.db.models import F as models_F  # noqa: E402


# ---------------- advances ----------------
@transaction.atomic
def grant_advance(*, target: User, amount: Decimal, monthly_recovery: Decimal, method: str, reference: str, actor) -> SalaryAdvance:
    if amount <= 0 or monthly_recovery <= 0 or monthly_recovery > amount:
        raise ValidationError({"amount": "Enter a positive amount and a monthly recovery that does not exceed it."})
    if not reference.strip() or method not in ("cash", "bank", "bank_transfer", "mobile_money"):
        raise ValidationError({"detail": "Choose a payment method and enter a payment reference."})
    if not StaffProfile.objects.filter(user=target).exclude(employment_status="terminated").exists():
        raise ValidationError({"user": "Advances can only be given to current staff."})
    if SalaryAdvance.objects.filter(reference=reference.strip()).exists():
        raise ValidationError({"reference": "This reference was already recorded."})
    adv = SalaryAdvance.objects.create(user=target, amount=amount, monthly_recovery=monthly_recovery, balance=amount, method=method, reference=reference.strip()[:100], approved_by=actor)
    post_entry(description=f"Salary advance to {target.full_name}", lines=[("1150", amount, 0, target.branch), (pay_account(method), 0, amount, target.branch)],
               source_type="salary_advance", source_id=adv.pk, user=actor, branch=target.branch)
    audit.record("payroll.advance_granted", actor=actor, target=adv, user=target.pk)
    return adv


# ---------------- payslips ----------------
def payslip_data(line: PayrollLine) -> dict:
    t = get_current_tenant()
    prof = StaffProfile.objects.filter(user=line.user).first()
    return {"pharmacy": t.name, "branch": line.branch.name if line.branch else "", "period": line.run.period, "staff_name": line.user.full_name,
            "staff_id": prof.staff_id if prof else "", "job_title": prof.job_title if prof else "", "currency": (t.settings or {}).get("currency", "SLE"),
            "earnings": line.details.get("earnings", []), "deductions": line.details.get("deductions", []), "basic": str(line.basic), "gross": str(line.gross),
            "total_deductions": str(line.gross - line.net), "net": str(line.net), "paid": str(line.paid_amount), "status": "Paid" if line.paid_amount == line.net else "Pending",
            "payments": [{"method": p.method, "amount": str(p.amount), "reference": p.reference, "date": p.created_at.date().isoformat()} for p in line.payments.all()],
            "reference": f"PS-{line.run.period}-{line.pk}"}


def render_payslip_pdf(d: dict) -> bytes:
    from io import BytesIO
    from reportlab.lib.pagesizes import A5
    from reportlab.pdfgen import canvas
    buf = BytesIO()
    w, h = A5
    c = canvas.Canvas(buf, pagesize=A5)
    y = h - 30

    def line(text, size=9, bold=False):
        nonlocal y
        if y < 30:
            c.showPage()
            y = h - 30
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(28, y, str(text)[:80])
        y -= size + 5

    line(d["pharmacy"], 13, True)
    line(f"Salary slip {d['period']}  ·  {d['reference']}", 10, True)
    line(f"{d['staff_name']}  ({d['staff_id']})  {d['job_title']}  {d['branch']}")
    y -= 4
    line("Earnings", 10, True)
    for e in d["earnings"]:
        line(f"  {e['name']}: {d['currency']} {e['amount']}")
    line(f"Gross: {d['currency']} {d['gross']}", 10, True)
    line("Deductions", 10, True)
    for e in d["deductions"]:
        line(f"  {e['name']}: {d['currency']} {e['amount']}")
    line(f"NET PAY: {d['currency']} {d['net']}   ({d['status']})", 11, True)
    for p in d["payments"]:
        line(f"Paid {p['amount']} by {p['method']} on {p['date']} ref {p['reference']}")
    c.save()
    return buf.getvalue()
