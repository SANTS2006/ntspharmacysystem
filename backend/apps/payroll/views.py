from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import HasTenantPermission, IsAuthenticatedAndSettled
from apps.audit import services as audit
from apps.core.fields import TenantPKField
from apps.core.views import TenantContextMixin
from apps.hr.services import user_scope
from apps.tenants.models import Branch

from . import services
from .models import PayrollAdjustment, PayrollLine, PayrollRun, SalaryAdvance, SalaryComponent, SalaryStructure


class Base(TenantContextMixin):
    permission_classes = [HasTenantPermission]


def visible_lines(actor):
    """Payroll lines the actor may see: pharmacy-level payroll roles see all, branch-scoped managers only their branch's staff."""
    qs = PayrollLine.objects.select_related("user", "run", "branch")
    return qs.filter(user__branch_id=actor.branch_id) if actor.is_branch_scoped else qs


def line_out(l: PayrollLine, detail=False):
    d = {"id": l.pk, "run": l.run_id, "period": l.run.period, "user": l.user_id, "name": l.user.full_name, "branch": l.branch_id, "basic": l.basic, "allowances": l.allowances,
         "extras": l.extras, "gross": l.gross, "tax": l.tax, "pension_employee": l.pension_employee, "other_deductions": l.other_deductions, "advance_recovery": l.advance_recovery,
         "net": l.net, "paid_amount": l.paid_amount, "warnings": l.warnings}
    if detail:
        d["details"] = l.details
    return d


def run_out(r: PayrollRun, actor=None, with_lines=False):
    lines = r.lines.all()
    if actor is not None and actor.is_branch_scoped:
        lines = lines.filter(user__branch_id=actor.branch_id)  # branch managers never see other branches' totals
    from django.db.models import Sum
    t = lines.aggregate(g=Sum("gross"), n=Sum("net"), x=Sum("tax"), p=Sum("paid_amount"), c=Sum("pension_employer"))
    d = {"id": r.pk, "period": r.period, "branch": r.branch_id, "status": r.status, "created_by": r.created_by_id, "approved_by": r.approved_by_id, "note": r.note,
         "staff": lines.count(), "gross": t["g"] or 0, "net": t["n"] or 0, "tax": t["x"] or 0, "paid": t["p"] or 0, "employer_pension": t["c"] or 0}
    if with_lines:
        d["lines"] = [line_out(l) for l in lines.select_related("user", "run")]
    return d


# ---------------- configuration, components ----------------
class ConfigView(Base, APIView):
    required_permissions = {"GET": "payroll.view", "PUT": "payroll.manage"}

    def get(self, request):
        return Response((request.tenant.settings or {}).get("payroll") or {"pension_employee_pct": "0", "pension_employer_pct": "0", "tax_brackets": []})

    def put(self, request):
        cfg = services.validate_config(request.data)
        s = dict(request.tenant.settings or {})
        s["payroll"] = cfg
        request.tenant.settings = s
        request.tenant.save(update_fields=["settings", "updated_at"])
        audit.record("payroll.config_updated", actor=request.user, tenant=request.tenant)
        return Response(cfg)


class ComponentsView(Base, APIView):
    required_permissions = {"GET": "payroll.view", "POST": "payroll.manage"}

    def get(self, request):
        return Response([{"id": c.pk, "name": c.name, "kind": c.kind, "calc": c.calc, "taxable": c.taxable, "is_active": c.is_active} for c in SalaryComponent.objects.all()])

    def post(self, request):
        d = request.data
        name = str(d.get("name", "")).strip()
        if not name or SalaryComponent.objects.filter(name__iexact=name).exists():
            raise serializers.ValidationError({"name": "Enter a unique component name."})
        if d.get("kind") not in ("earning", "deduction") or d.get("calc", "fixed") not in ("fixed", "percent_basic"):
            raise serializers.ValidationError({"kind": "Choose earning or deduction, and fixed or percent_basic."})
        c = SalaryComponent.objects.create(name=name[:80], kind=d["kind"], calc=d.get("calc", "fixed"), taxable=bool(d.get("taxable", True)))
        audit.record("payroll.component_created", actor=request.user, target=c)
        return Response({"id": c.pk, "name": c.name}, status=201)


# ---------------- salary structures ----------------
class StructureItemIn(serializers.Serializer):
    component = TenantPKField(SalaryComponent)
    value = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)


class StructureIn(serializers.Serializer):
    user = serializers.IntegerField()
    basic_salary = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    effective_from = serializers.DateField()
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    items = StructureItemIn(many=True, required=False, default=list)


def structure_out(st: SalaryStructure):
    return {"id": st.pk, "user": st.user_id, "basic_salary": st.basic_salary, "effective_from": st.effective_from, "note": st.note,
            "items": [{"component": i.component.name, "kind": i.component.kind, "calc": i.component.calc, "value": i.value} for i in st.items.select_related("component")]}


class StructuresView(Base, APIView):
    required_permissions = {"GET": "payroll.view", "POST": "payroll.manage"}

    def get(self, request):
        qs = SalaryStructure.objects.select_related("user").prefetch_related("items__component")
        if request.user.is_branch_scoped:
            qs = qs.filter(user__branch_id=request.user.branch_id)
        if request.query_params.get("user"):
            qs = qs.filter(user_id=request.query_params["user"])
        return Response([structure_out(s) for s in qs[:200]])

    def post(self, request):
        s = StructureIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        target = get_object_or_404(user_scope(request.user), pk=d["user"])
        st = services.set_structure(target=target, basic=d["basic_salary"], items=d["items"], effective_from=d["effective_from"], actor=request.user, note=d["note"])
        return Response(structure_out(st), status=201)


# ---------------- adjustments and advances ----------------
class AdjustmentsView(Base, APIView):
    required_permissions = {"GET": "payroll.view", "POST": "payroll.manage"}

    def get(self, request):
        qs = PayrollAdjustment.objects.select_related("user")
        if request.user.is_branch_scoped:
            qs = qs.filter(user__branch_id=request.user.branch_id)
        if request.query_params.get("period"):
            qs = qs.filter(period=request.query_params["period"])
        return Response([{"id": a.pk, "user": a.user_id, "name": a.user.full_name, "period": a.period, "kind": a.kind, "amount": a.amount, "note": a.note, "applied": a.applied_run_id is not None} for a in qs[:200]])

    def post(self, request):
        d = request.data
        target = get_object_or_404(user_scope(request.user), pk=d.get("user"))
        services.period_bounds(str(d.get("period", "")))
        amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01")).run_validation(d.get("amount"))
        if d.get("kind") not in ("bonus", "commission", "overtime", "deduction") or not str(d.get("note", "")).strip():
            raise serializers.ValidationError({"detail": "Choose a kind and enter a note."})
        if PayrollRun.objects.filter(period=d["period"]).exclude(status="cancelled").exclude(status="draft").exists():
            raise serializers.ValidationError({"period": "This period's payroll is already submitted or approved."})
        a = PayrollAdjustment.objects.create(user=target, period=d["period"], kind=d["kind"], amount=amount, taxable=bool(d.get("taxable", True)), note=str(d["note"])[:200], created_by=request.user)
        audit.record("payroll.adjustment_added", actor=request.user, target=a, user=target.pk, period=a.period)
        return Response({"id": a.pk}, status=201)


class AdvancesView(Base, APIView):
    required_permissions = {"GET": "payroll.view", "POST": "payroll.approve"}  # cash leaves the business: approver-level

    def get(self, request):
        qs = SalaryAdvance.objects.select_related("user")
        if request.user.is_branch_scoped:
            qs = qs.filter(user__branch_id=request.user.branch_id)
        return Response([{"id": a.pk, "user": a.user_id, "name": a.user.full_name, "amount": a.amount, "balance": a.balance, "monthly_recovery": a.monthly_recovery, "status": a.status} for a in qs[:200]])

    def post(self, request):
        d = request.data
        target = get_object_or_404(user_scope(request.user), pk=d.get("user"))
        dec = lambda k: serializers.DecimalField(max_digits=14, decimal_places=2).run_validation(d.get(k))  # noqa: E731
        a = services.grant_advance(target=target, amount=dec("amount"), monthly_recovery=dec("monthly_recovery"), method=str(d.get("method", "")), reference=str(d.get("reference", "")), actor=request.user)
        return Response({"id": a.pk, "balance": a.balance}, status=201)


# ---------------- runs ----------------
class RunsView(Base, APIView):
    required_permissions = {"GET": "payroll.view", "POST": "payroll.manage"}

    def get(self, request):
        pg = PageNumberPagination()
        qs = PayrollRun.objects.all()
        return pg.get_paginated_response([run_out(r, request.user) for r in pg.paginate_queryset(qs, request)])

    def post(self, request):
        if request.user.is_branch_scoped:
            raise PermissionDenied("Payroll runs are created by pharmacy-level payroll staff.")
        branch = get_object_or_404(Branch, pk=request.data["branch"]) if request.data.get("branch") else None
        r = services.create_run(period=str(request.data.get("period", "")), branch=branch, actor=request.user, note=str(request.data.get("note", "")))
        return Response(run_out(r, request.user, True), status=201)


class RunDetailView(Base, APIView):
    required_permission = "payroll.view"

    def get(self, request, pk):
        return Response(run_out(get_object_or_404(PayrollRun, pk=pk), request.user, True))


class RunActionView(Base, APIView):
    required_permission = "payroll.manage"
    action = None

    def post(self, request, pk):
        run = get_object_or_404(PayrollRun, pk=pk)
        fn = {"recalculate": services.recalculate, "submit": services.submit, "cancel": services.cancel, "approve": services.approve}[self.action]
        return Response(run_out(fn(run.pk, actor=request.user), request.user, True))


def _action(name, perm):
    return type(f"Run{name.title()}", (RunActionView,), {"action": name, "required_permission": perm})


RunRecalculate, RunSubmit, RunCancel = _action("recalculate", "payroll.manage"), _action("submit", "payroll.manage"), _action("cancel", "payroll.manage")
RunApprove = _action("approve", "payroll.approve")


class PayLineView(Base, APIView):
    required_permission = "payroll.manage"

    def post(self, request, pk):
        line = get_object_or_404(PayrollLine, pk=pk)
        amount = serializers.DecimalField(max_digits=14, decimal_places=2).run_validation(request.data.get("amount", line.net - line.paid_amount))
        p = services.pay_line(line.pk, amount=amount, method=str(request.data.get("method", "")), reference=str(request.data.get("reference", "")), actor=request.user)
        line.refresh_from_db()
        return Response({"payment": p.pk, "line": line_out(line)}, status=201)


def _pdf(data):
    r = HttpResponse(services.render_payslip_pdf(data), content_type="application/pdf")
    r["Content-Disposition"] = f'attachment; filename="{data["reference"]}.pdf"'
    r["X-Content-Type-Options"] = "nosniff"
    r["Cache-Control"] = "private, no-store"
    return r


class PayslipView(Base, APIView):
    required_permission = "payroll.view"
    pdf = False

    def get(self, request, pk):
        line = get_object_or_404(visible_lines(request.user).exclude(run__status__in=["draft", "cancelled"]), pk=pk)
        audit.record("payroll.payslip_viewed", actor=request.user, target=line, user=line.user_id, request=request)
        d = services.payslip_data(line)
        return _pdf(d) if self.pdf else Response(d)


class PayslipPdfView(PayslipView):
    pdf = True


# ---------------- employee self-service: ONLY the caller's own pay ----------------
class IsStaff(IsAuthenticatedAndSettled):
    def has_permission(self, request, view):
        u = request.user
        return super().has_permission(request, view) and not u.is_platform_admin and bool(u.role_id and u.role.code != "customer")


class MySalaryView(TenantContextMixin, APIView):
    permission_classes = [IsStaff]

    def get(self, request):
        from django.utils import timezone
        st = services.structure_on(request.user, timezone.localdate())
        return Response({"current": structure_out(st) if st else None, "history": [{"effective_from": s.effective_from, "basic_salary": s.basic_salary} for s in SalaryStructure.objects.filter(user=request.user)]})


class MyPayslipsView(TenantContextMixin, APIView):
    permission_classes = [IsStaff]

    def get(self, request):
        lines = PayrollLine.objects.filter(user=request.user, run__status__in=["approved", "paid"]).select_related("run", "user")
        return Response([{"id": l.pk, "period": l.run.period, "net": l.net, "paid": l.paid_amount, "status": "paid" if l.paid_amount == l.net else "pending"} for l in lines])


class MyPayslipView(TenantContextMixin, APIView):
    permission_classes = [IsStaff]
    pdf = False

    def get(self, request, pk):
        line = get_object_or_404(PayrollLine.objects.select_related("run", "user", "branch"), pk=pk, user=request.user, run__status__in=["approved", "paid"])
        d = services.payslip_data(line)
        return _pdf(d) if self.pdf else Response(d)


class MyPayslipPdfView(MyPayslipView):
    pdf = True
