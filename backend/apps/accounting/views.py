from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantPermission, IsAuthenticatedAndSettled
from apps.core.fields import TenantPKField
from apps.core.views import TenantContextMixin
from apps.tenants.models import Branch

from . import engine, reports
from .models import Account, DailyClose, Expense, JournalEntry


class Base(TenantContextMixin):
    permission_classes = [HasTenantPermission]


class ReportAccess(IsAuthenticatedAndSettled):
    """Pharmacy-wide reports need accounting.view; branch managers (report.view) may read their OWN branch's statements only."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        u = request.user
        return u.has_tenant_perm("accounting.view") or (getattr(view, "branch_manager_ok", False) and u.has_tenant_perm("report.view") and u.is_branch_scoped)


def params(request):
    date = lambda k: serializers.DateField(required=False).run_validation(request.query_params.get(k) or serializers.empty) if request.query_params.get(k) else None  # noqa: E731
    branch = request.query_params.get("branch")
    if request.user.is_branch_scoped:
        if branch and str(branch) != str(request.user.branch_id):
            raise PermissionDenied("You can only view your own branch.")
        branch = request.user.branch_id
    if branch and not Branch.objects.filter(pk=branch).exists():
        raise NotFound()
    return date("date_from"), date("date_to"), date("as_of"), (int(branch) if branch else None)


# ---------------- chart of accounts ----------------
def acc_out(a):
    return {"id": a.pk, "code": a.code, "name": a.name, "type": a.type, "is_system": a.is_system, "is_active": a.is_active}


class AccountsView(Base, APIView):
    required_permissions = {"GET": "accounting.view", "POST": "accounting.manage"}

    def get(self, request):
        engine.ensure_chart()
        return Response([acc_out(a) for a in Account.objects.all()])

    def post(self, request):
        a = engine.create_account(user=request.user, code=str(request.data.get("code", "")).strip(), name=str(request.data.get("name", "")), type_=str(request.data.get("type", "")))
        return Response(acc_out(a), status=201)


class AccountDetailView(Base, APIView):
    required_permission = "accounting.manage"

    def patch(self, request, pk):
        a = get_object_or_404(Account, pk=pk)
        if a.is_system:
            raise serializers.ValidationError({"detail": "Default accounts cannot be changed."})
        if "name" in request.data:
            a.name = str(request.data["name"]).strip()[:120] or a.name
        if "is_active" in request.data:
            if request.data["is_active"] is False and a.lines.exists():
                pass  # deactivating keeps history intact; only new postings are refused
            a.is_active = bool(request.data["is_active"])
        a.save()
        return Response(acc_out(a))


# ---------------- journal ----------------
def entry_out(e, lines=True):
    d = {"id": e.pk, "number": e.number, "date": e.date, "description": e.description, "source_type": e.source_type, "source_id": e.source_id, "total": e.total,
         "reversed": hasattr(e, "reversed_by"), "reverses": e.reverses.number if e.reverses_id else None}
    if lines:
        d["lines"] = [{"account": l.account.code, "account_name": l.account.name, "branch": l.branch_id, "debit": l.debit, "credit": l.credit, "memo": l.memo} for l in e.lines.select_related("account")]
    return d


class LineIn(serializers.Serializer):
    account = serializers.CharField(max_length=10)
    debit = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=0, required=False, default=0)
    credit = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=0, required=False, default=0)
    branch = TenantPKField(Branch, required=False, allow_null=True)
    memo = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class ManualIn(serializers.Serializer):
    date = serializers.DateField(required=False)
    description = serializers.CharField(max_length=300)
    lines = LineIn(many=True, min_length=2)


class JournalView(Base, APIView):
    required_permissions = {"GET": "accounting.view", "POST": "accounting.manage"}

    def get(self, request):
        qs = JournalEntry.objects.select_related("reverses")
        q = request.query_params
        for key, f in (("source_type", "source_type"), ("date_from", "date__gte"), ("date_to", "date__lte")):
            if q.get(key):
                qs = qs.filter(**{f: q[key]})
        if q.get("search"):
            qs = qs.filter(description__icontains=q["search"]) | qs.filter(number__icontains=q["search"])
        pg = PageNumberPagination()
        return pg.get_paginated_response([entry_out(e, False) for e in pg.paginate_queryset(qs.order_by("-date", "-id"), request)])

    def post(self, request):
        s = ManualIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        lines = [(l["account"], l["debit"], l["credit"], l.get("branch"), l["memo"]) for l in d["lines"]]
        e = engine.post_manual(user=request.user, description=d["description"], lines=lines, date=d.get("date"), idempotency_key=request.headers.get("Idempotency-Key", ""))
        return Response(entry_out(e), status=201)


class JournalDetailView(Base, APIView):
    required_permission = "accounting.view"

    def get(self, request, pk):
        return Response(entry_out(get_object_or_404(JournalEntry.objects.select_related("reverses"), pk=pk)))


class ReverseView(Base, APIView):
    required_permission = "accounting.manage"

    def post(self, request, pk):
        e = get_object_or_404(JournalEntry, pk=pk)
        return Response(entry_out(engine.reverse_entry(e.pk, user=request.user, reason=str(request.data.get("reason", "")))), status=201)


# ---------------- expenses ----------------
def exp_out(x):
    return {"id": x.pk, "date": x.date, "branch": x.branch_id, "account": x.account.code, "account_name": x.account.name, "amount": x.amount, "payment_method": x.payment_method,
            "vendor": x.vendor, "reference": x.reference, "description": x.description, "status": x.status, "journal_entry": x.journal_entry.number if x.journal_entry_id else None}


class ExpenseIn(serializers.Serializer):
    date = serializers.DateField()
    account = serializers.CharField(max_length=10)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    payment_method = serializers.CharField(max_length=15)
    description = serializers.CharField(max_length=300)
    branch = TenantPKField(Branch, required=False, allow_null=True)
    vendor = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class ExpensesView(Base, APIView):
    required_permissions = {"GET": "accounting.view", "POST": "accounting.manage"}

    def get(self, request):
        qs = Expense.objects.select_related("account", "journal_entry")
        for k, f in (("date_from", "date__gte"), ("date_to", "date__lte"), ("branch", "branch_id"), ("status", "status")):
            if request.query_params.get(k):
                qs = qs.filter(**{f: request.query_params[k]})
        pg = PageNumberPagination()
        return pg.get_paginated_response([exp_out(x) for x in pg.paginate_queryset(qs, request)])

    def post(self, request):
        s = ExpenseIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        engine.ensure_chart()  # a pharmacy that has not posted anything yet still needs its default accounts
        acc = Account.objects.filter(code=d.pop("account")).first()
        if acc is None:
            raise serializers.ValidationError({"account": "Unknown account."})
        x = engine.create_expense(user=request.user, account=acc, **d)
        return Response(exp_out(x), status=201)


class ReverseExpenseView(Base, APIView):
    required_permission = "accounting.manage"

    def post(self, request, pk):
        x = get_object_or_404(Expense, pk=pk)
        if x.status == Expense.Status.REVERSED:
            raise serializers.ValidationError({"detail": "This expense was already reversed."})
        rev = engine.reverse_entry(x.journal_entry_id, user=request.user, reason=str(request.data.get("reason", "")))
        return Response(entry_out(rev), status=201)


# ---------------- daily close ----------------
class CloseView(Base, APIView):
    required_permissions = {"GET": "accounting.view", "POST": "accounting.manage"}

    def get(self, request):
        return Response([{"date": c.date, "closed_by": c.closed_by.email if c.closed_by else None, "summary": c.summary} for c in DailyClose.objects.select_related("closed_by")[:90]])

    def post(self, request):
        d = serializers.DateField().run_validation(request.data.get("date"))
        c = engine.close_day(user=request.user, date=d)
        return Response({"date": c.date, "summary": c.summary}, status=201)


# ---------------- reports ----------------
class ReportBase(TenantContextMixin, APIView):
    permission_classes = [ReportAccess]
    branch_manager_ok = False


class TrialBalanceView(ReportBase):
    def get(self, request):
        _, _, as_of, branch = params(request)
        return Response(reports.trial_balance(as_of, branch))


class IncomeStatementView(ReportBase):
    branch_manager_ok = True

    def get(self, request):
        f, t, _, branch = params(request)
        return Response(reports.income_statement(f, t, branch))


class BalanceSheetView(ReportBase):
    def get(self, request):
        _, _, as_of, branch = params(request)
        return Response(reports.balance_sheet(as_of, branch))


class CashFlowView(ReportBase):
    def get(self, request):
        f, t, _, branch = params(request)
        return Response(reports.cash_flow(f, t, branch))


class GeneralLedgerView(ReportBase):
    def get(self, request, code):
        f, t, _, branch = params(request)
        out = reports.general_ledger(code, f, t, branch)
        if out is None:
            raise NotFound()
        return Response(out)


class BranchSummaryView(ReportBase):
    branch_manager_ok = True

    def get(self, request):
        f, t, _, branch = params(request)
        rows = reports.branch_summary(f, t)
        return Response([r for r in rows if branch is None or r["branch"] == branch])


class ReceivablesView(ReportBase):
    def get(self, request):
        return Response(reports.receivables())


class PayablesView(ReportBase):
    def get(self, request):
        return Response(reports.payables())


class IntegrityView(ReportBase):
    def get(self, request):
        return Response(reports.integrity())
