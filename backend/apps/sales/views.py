from datetime import timedelta

from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantPermission, IsAuthenticatedAndSettled
from apps.audit import services as audit
from apps.core.fields import TenantPKField
from apps.core.views import TenantContextMixin
from apps.inventory.selectors import branch_ids_for, medicines_with_stock
from apps.medicines.models import Medicine
from apps.notifications.services import render_branded_html, send_email
from apps.prescriptions.models import Dispensing
from apps.tenants.models import Branch

from . import services
from .models import CashMovement, Payment, Sale, SaleReturn, Shift, ZERO


class Base(TenantContextMixin):
    permission_classes = [HasTenantPermission]


class AnyPerm(IsAuthenticatedAndSettled):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and any(request.user.has_tenant_perm(p) for p in view.any_permission)


# ---------------- scoping (cashiers only ever see their own records) ----------------
def sales_queryset(user):
    qs = Sale.objects.select_related("cashier", "branch")
    if user.has_tenant_perm("sales.view_branch"):
        ids = branch_ids_for(user)
        return qs.filter(branch_id__in=ids) if ids else qs
    if user.has_tenant_perm("sales.view_own"):
        return qs.filter(cashier=user)
    return qs.none()


def shifts_queryset(user):
    qs = Shift.objects.select_related("cashier", "branch")
    if user.has_tenant_perm("sales.view_branch"):
        ids = branch_ids_for(user)
        return qs.filter(branch_id__in=ids) if ids else qs
    return qs.filter(cashier=user)


def sale_out(s: Sale, detail=False):
    d = {"id": s.pk, "reference_number": s.reference_number, "status": s.status, "branch": s.branch_id, "cashier": s.cashier_id, "cashier_name": s.cashier.full_name,
         "customer_name": s.customer_name, "subtotal": s.subtotal, "discount_total": s.discount_total, "tax_total": s.tax_total, "total": s.total,
         "amount_paid": s.amount_paid, "balance": s.balance, "change_due": s.change_due, "created_at": s.created_at}
    if detail:
        d["lines"] = [{"id": l.pk, "medicine": l.medicine_id, "name": l.medicine.name, "quantity": l.quantity, "unit_price": l.unit_price, "discount_amount": l.discount_amount,
                       "tax_amount": l.tax_amount, "line_total": l.line_total, "quantity_returned": l.quantity_returned, "from_prescription": l.dispensing_item_id is not None}
                      for l in s.lines.select_related("medicine")]
        d["payments"] = [{"method": p.method, "amount": p.amount, "reference": p.reference} for p in s.payments.all()]
        d["returns"] = [{"number": r.number, "refund_total": r.refund_total, "method": r.refund_method, "reason": r.reason, "is_cancellation": r.is_cancellation} for r in s.returns.all()]
        d["receipt_number"] = s.receipt.number
    return d


def shift_out(sh: Shift, with_totals=False):
    d = {"id": sh.pk, "cashier": sh.cashier_id, "cashier_name": sh.cashier.full_name, "branch": sh.branch_id, "branch_name": sh.branch.name, "status": sh.status,
         "opening_cash": sh.opening_cash, "opened_at": sh.opened_at, "closed_at": sh.closed_at, "counted_cash": sh.counted_cash,
         "expected_cash": sh.expected_cash, "discrepancy": sh.discrepancy, "notes": sh.notes}
    if with_totals:
        d["totals"] = services.shift_totals(sh)
        d["cash_movements"] = [{"id": m.pk, "kind": m.kind, "amount": m.amount, "reason": m.reason, "status": m.status} for m in sh.cash_movements.all()]
        if sh.status == Shift.Status.OPEN:
            d["expected_cash"] = d["totals"]["expected_cash"]
    return d


# ---------------- shifts ----------------
class OpenShiftView(Base, APIView):
    required_permission = "pos.sell"

    def post(self, request):
        s = serializers.Serializer(data={})
        branch_id = request.data.get("branch") or request.user.branch_id
        branch = get_object_or_404(Branch, pk=branch_id)
        opening = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0).run_validation(request.data.get("opening_cash", 0))
        sh = services.open_shift(user=request.user, branch=branch, opening_cash=opening)
        return Response(shift_out(sh, True), status=201)


class CurrentShiftView(Base, APIView):
    required_permission = "pos.sell"

    def get(self, request):
        sh = services.current_shift(request.user)
        return Response(shift_out(sh, True) if sh else None)


class ShiftListView(Base, ListAPIView):
    any_permission = ["pos.sell", "sales.view_branch"]
    permission_classes = [AnyPerm]
    filterset_fields = ["status", "branch", "cashier"]

    def get_queryset(self):
        return shifts_queryset(self.request.user)

    def list(self, request, *a, **k):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response([shift_out(s) for s in page])


class ShiftDetailView(Base, APIView):
    any_permission = ["pos.sell", "sales.view_branch"]
    permission_classes = [AnyPerm]

    def get(self, request, pk):
        return Response(shift_out(get_object_or_404(shifts_queryset(request.user), pk=pk), True))


class CloseShiftView(Base, APIView):
    any_permission = ["pos.sell", "sales.refund"]
    permission_classes = [AnyPerm]

    def post(self, request, pk):
        sh = get_object_or_404(shifts_queryset(request.user), pk=pk)
        counted = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0).run_validation(request.data.get("counted_cash"))
        sh = services.close_shift(sh.pk, user=request.user, counted_cash=counted, notes=str(request.data.get("notes", "")))
        return Response(shift_out(sh, True))


class CashMovementView(Base, APIView):
    required_permission = "pos.sell"

    def post(self, request, pk):
        sh = get_object_or_404(Shift.objects.filter(cashier=request.user), pk=pk)
        amount = serializers.DecimalField(max_digits=14, decimal_places=2).run_validation(request.data.get("amount"))
        m = services.request_cash_movement(sh.pk, user=request.user, kind=str(request.data.get("kind", "")), amount=amount, reason=str(request.data.get("reason", "")))
        return Response({"id": m.pk, "kind": m.kind, "amount": m.amount, "status": m.status}, status=201)


class DecideCashMovementView(Base, APIView):
    required_permission = "sales.refund"
    approve = True

    def post(self, request, pk):
        m = get_object_or_404(CashMovement.objects.select_related("shift"), pk=pk)
        if request.user.is_branch_scoped and m.shift.branch_id != request.user.branch_id:
            raise PermissionDenied("Different branch.")
        m = services.decide_cash_movement(pk, user=request.user, approve=self.approve)
        return Response({"id": m.pk, "status": m.status})


class RejectCashMovementView(DecideCashMovementView):
    approve = False


# ---------------- POS helpers ----------------
class ProductSearchView(Base, APIView):
    required_permission = "pos.sell"

    def get(self, request):
        sh = services.current_shift(request.user)
        branch = sh.branch_id if sh else request.user.branch_id
        qs = medicines_with_stock(request.user, branch).filter(status="active")
        if code := request.query_params.get("barcode"):
            qs = qs.filter(barcode=code)
        elif q := request.query_params.get("search"):
            from django.db.models import Q
            qs = qs.filter(Q(name__icontains=q) | Q(generic_name__icontains=q) | Q(brand_name__icontains=q) | Q(barcode=q) | Q(sku__iexact=q))
        else:
            qs = qs.none()
        return Response([{"id": m.pk, "name": m.name, "strength": m.strength, "dosage_form": m.dosage_form, "barcode": m.barcode, "price": m.selling_price,
                          "tax_rate": m.tax_rate, "stock": m.stock, "requires_prescription": m.requires_prescription, "classification": m.classification} for m in qs[:30]])


class PendingDispensingsView(Base, APIView):
    """Pharmacist-dispensed prescriptions waiting to be billed."""
    required_permission = "pos.sell"

    def get(self, request):
        sh = services.current_shift(request.user)
        if sh is None:
            return Response([])
        out = []
        for d in Dispensing.objects.filter(branch=sh.branch, sale_id__isnull=True).select_related("prescription__patient"):
            items = list(d.items.select_related("item__medicine", "batch"))
            total = sum((services.q2(i.item.medicine.selling_price * i.quantity) for i in items), ZERO)
            out.append({"id": d.pk, "prescription": d.prescription.reference_number, "patient": d.prescription.patient.full_name, "estimated_total": total,
                        "items": [{"medicine": i.item.medicine.name, "quantity": i.quantity} for i in items]})
        return Response(out)


class CashierDashboardView(Base, APIView):
    required_permission = "pos.sell"

    def get(self, request):
        u, now = request.user, timezone.localtime()
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        mine = Sale.objects.filter(cashier=u).exclude(status=Sale.Status.CANCELLED)
        agg = lambda qs: {"count": qs.count(), "total": qs.aggregate(t=Sum("total"))["t"] or ZERO}  # noqa: E731
        by_method = {p["method"]: p["t"] for p in Payment.objects.filter(received_by=u, created_at__gte=day).values("method").annotate(t=Sum("amount"))}
        refunds = SaleReturn.objects.filter(processed_by=u, created_at__gte=day)
        sh = services.current_shift(u)
        return Response({"today": agg(mine.filter(created_at__gte=day)), "month": agg(mine.filter(created_at__gte=day.replace(day=1))),
                         "payments_today": by_method, "refunds_today": {"count": refunds.count(), "total": refunds.aggregate(t=Sum("refund_total"))["t"] or ZERO},
                         "receipts_today": Sale.objects.filter(cashier=u, created_at__gte=day).count(),
                         "current_shift": shift_out(sh, True) if sh else None,
                         "recent_sales": [sale_out(s) for s in Sale.objects.filter(cashier=u).select_related("cashier")[:10]]})


# ---------------- sales ----------------
class ItemIn(serializers.Serializer):
    medicine = TenantPKField(Medicine)
    quantity = serializers.IntegerField(min_value=1)
    discount_pct = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False, default=0)


class PayIn(serializers.Serializer):
    method = serializers.CharField(max_length=15)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class SaleIn(serializers.Serializer):
    items = ItemIn(many=True, required=False, default=list)
    dispensing_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    payments = PayIn(many=True, required=False, default=list)
    customer_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    customer_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")


class SaleListCreateView(Base, APIView):
    any_permission = ["pos.sell", "sales.view_own", "sales.view_branch"]
    permission_classes = [AnyPerm]

    def get(self, request):
        from rest_framework.pagination import PageNumberPagination
        qs = sales_queryset(request.user)
        for k in ("status", "branch", "cashier"):
            if request.query_params.get(k):
                qs = qs.filter(**{f"{k}_id" if k != "status" else k: request.query_params[k]})
        if s := request.query_params.get("search"):
            qs = qs.filter(reference_number__icontains=s)
        pg = PageNumberPagination()
        page = pg.paginate_queryset(qs, request)
        return pg.get_paginated_response([sale_out(x) for x in page])

    def post(self, request):
        if not request.user.has_tenant_perm("pos.sell"):
            raise PermissionDenied("You are not allowed to make sales.")
        s = SaleIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        key = request.headers.get("Idempotency-Key") or request.data.get("idempotency_key", "")
        sale, created = services.create_sale(user=request.user, items=d["items"], dispensing_ids=d["dispensing_ids"], payments=[dict(p) for p in d["payments"]],
                                             idempotency_key=key, customer_name=d["customer_name"], customer_phone=d["customer_phone"])
        return Response(sale_out(sale, True), status=201 if created else 200)


class SaleDetailView(Base, APIView):
    any_permission = ["pos.sell", "sales.view_own", "sales.view_branch"]
    permission_classes = [AnyPerm]

    def get(self, request, pk):
        return Response(sale_out(get_object_or_404(sales_queryset(request.user), pk=pk), True))


class AddPaymentView(Base, APIView):
    required_permission = "pos.sell"

    def post(self, request, pk):
        sale = get_object_or_404(sales_queryset(request.user), pk=pk)
        s = PayIn(data=request.data.get("payments") or [], many=True)
        s.is_valid(raise_exception=True)
        sale = services.add_payment(sale.pk, user=request.user, payments=[dict(p) for p in s.validated_data])
        return Response(sale_out(sale, True))


class ReturnLineIn(serializers.Serializer):
    sale_line = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class ReturnView(Base, APIView):
    required_permission = "sales.refund"
    cancel = False

    def post(self, request, pk):
        sale = get_object_or_404(sales_queryset(request.user), pk=pk)
        common = dict(user=request.user, reason=str(request.data.get("reason", "")), refund_method=str(request.data.get("refund_method", "")),
                      refund_reference=str(request.data.get("refund_reference", "")))
        if self.cancel:
            sr = services.cancel_sale(sale.pk, **common)
        else:
            s = ReturnLineIn(data=request.data.get("lines") or [], many=True)
            s.is_valid(raise_exception=True)
            sr = services.process_return(sale.pk, lines=s.validated_data, restock=bool(request.data.get("restock", False)), **common)
        return Response({"credit_note": sr.number, "refund_total": sr.refund_total, "sale_status": Sale.objects.get(pk=sale.pk).status}, status=201)


class CancelView(ReturnView):
    cancel = True


# ---------------- receipts ----------------
def _receipt(request, pk):
    sale = get_object_or_404(sales_queryset(request.user), pk=pk)
    return sale, sale.receipt


class ReceiptView(Base, APIView):
    any_permission = ["pos.sell", "sales.view_own", "sales.view_branch"]
    permission_classes = [AnyPerm]

    def get(self, request, pk):
        return Response({"number": _receipt(request, pk)[1].number, **_receipt(request, pk)[1].data})


class ReceiptPdfView(ReceiptView):
    def get(self, request, pk):
        sale, rc = _receipt(request, pk)
        audit.record("receipt.downloaded", actor=request.user, target=sale, branch_id=sale.branch_id)
        resp = HttpResponse(services.render_receipt_pdf({**rc.data, "receipt_number": rc.number}), content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{rc.number}.pdf"'
        resp["X-Content-Type-Options"] = "nosniff"
        return resp


class ReceiptEmailView(Base, APIView):
    required_permission = "pos.sell"

    def post(self, request, pk):
        sale, rc = _receipt(request, pk)
        to = serializers.EmailField().run_validation(request.data.get("email"))
        d = rc.data
        rows = [f"{l['name']} x{l['quantity']} = {l['total']}" for l in d["lines"]]
        paragraphs = [f"Receipt {rc.number} · Sale {d['sale_reference']}", *rows, f"Total: {d['currency']} {d['total']}", f"Paid: {d['amount_paid']} ({d['payment_status']})"]
        send_email(to=to, subject=f"Your receipt {rc.number} from {d['pharmacy']}", text="\n".join(paragraphs), tenant=request.tenant, template="receipt",
                   html_body=render_branded_html(title="Your receipt", pharmacy=request.tenant, paragraphs=paragraphs))
        audit.record("receipt.emailed", actor=request.user, target=sale, branch_id=sale.branch_id)
        return Response(status=202)
