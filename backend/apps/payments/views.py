from decimal import Decimal

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantPermission, IsAuthenticatedAndSettled
from apps.core.exceptions import BusinessRuleViolation
from apps.core.views import TenantContextMixin
from apps.sales.services import render_receipt_pdf
from apps.shop.models import Order
from apps.shop.views import IsVerifiedCustomer, order_out, staff_orders

from . import monime, services
from .models import MobileMoneyCollection, OrderReceipt, PaymentAttempt

MAX_WEBHOOK_BYTES = 64 * 1024


@csrf_exempt
@require_POST
def monime_webhook(request, slug=None):
    """Public endpoint (one for the whole platform). Authenticity comes only from the HMAC signature over the raw body."""
    raw = request.body
    if len(raw) > MAX_WEBHOOK_BYTES:
        return JsonResponse({"error": "too_large"}, status=413)
    code, outcome = services.handle_webhook(raw, request.headers.get("Monime-Signature", ""))
    return JsonResponse({"received": code == 200, "outcome": outcome}, status=code)


def attempt_out(a: PaymentAttempt, with_redirect=False):
    d = {"id": a.pk, "reference": a.reference, "order": a.order.reference_number, "amount": a.amount, "currency": a.currency, "status": a.status,
         "created_at": a.created_at, "completed_at": a.completed_at, "needs_refund": a.needs_refund}
    if with_redirect:
        d["redirect_url"] = a.redirect_url
    return d


# ---------------- customer ----------------
class PayOrderView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]

    def post(self, request, pk):
        a = services.start_payment(get_object_or_404(Order, pk=pk, customer=request.user).pk, user=request.user)
        return Response(attempt_out(a, True), status=201)


class OrderPaymentsView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]

    def get(self, request, pk):
        o = get_object_or_404(Order, pk=pk, customer=request.user)
        # The browser redirect is never proof of payment: this reflects only provider-verified state.
        return Response([attempt_out(a) for a in o.payment_attempts.select_related("order")])


class PaymentHistoryView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]

    def get(self, request):
        pg = PageNumberPagination()
        qs = PaymentAttempt.objects.filter(order__customer=request.user).select_related("order")
        return pg.get_paginated_response([attempt_out(a) for a in pg.paginate_queryset(qs, request)])


def _receipt_response(order, pdf):
    r = get_object_or_404(OrderReceipt, order=order)
    if pdf:
        resp = HttpResponse(render_receipt_pdf(r.data), content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{r.number}.pdf"'
        resp["X-Content-Type-Options"] = "nosniff"
        return resp
    return Response({"number": r.number, **r.data})


class CustomerReceiptView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]
    pdf = False

    def get(self, request, pk):
        return _receipt_response(get_object_or_404(Order, pk=pk, customer=request.user), self.pdf)


class CustomerReceiptPdfView(CustomerReceiptView):
    pdf = True


class RefreshOrderPaymentsView(TenantContextMixin, APIView):
    """The customer's order page calls this after returning from checkout: the server asks the provider what happened."""
    permission_classes = [IsVerifiedCustomer]
    throttle_scope = "payment_refresh"

    def get_throttles(self):
        return [ScopedRateThrottle()]

    def post(self, request, pk):
        o = get_object_or_404(Order, pk=pk, customer=request.user)
        try:
            services.refresh_attempts(o.payment_attempts.all())
        except monime.ProviderError:
            pass
        o.refresh_from_db()
        return Response({"status": o.status, "payments": [attempt_out(a) for a in o.payment_attempts.select_related("order")]})


# ---------------- staff ----------------
class StaffBase(TenantContextMixin):
    permission_classes = [HasTenantPermission]


class StatusView(StaffBase, APIView):
    """Read-only: whether mobile money is available. Credentials live in the server environment and are never shown or editable."""
    permission_classes = [IsAuthenticatedAndSettled]

    def get(self, request):
        return Response({"provider": "monime", "enabled": services.provider_ready(), "currency": services.currency()})


def collection_out(c: MobileMoneyCollection):
    return {"id": c.pk, "reference": c.reference, "amount": c.amount, "currency": c.currency, "status": c.status, "ussd_code": c.ussd_code,
            "customer_name": c.customer_name, "expires_at": c.expires_at, "completed_at": c.completed_at, "used": c.used_at is not None, "used_for": c.used_for}


class CollectionBase(StaffBase, APIView):
    required_permission = "pos.sell"

    def rows(self, request):
        qs = MobileMoneyCollection.objects.all()
        return qs.filter(branch_id=request.user.branch_id) if request.user.is_branch_scoped else qs

    def shift_branch(self, request):
        from apps.sales.services import current_shift
        shift = current_shift(request.user)
        if shift is None:
            raise BusinessRuleViolation("Open a shift before taking payments.")
        return shift.branch


class CollectionsView(CollectionBase):
    def get(self, request):
        """Money received at this branch that no sale has used yet (e.g. the sale failed after the customer paid)."""
        branch = self.shift_branch(request)
        qs = self.rows(request).filter(branch=branch, status="completed", used_at__isnull=True)[:20]
        return Response([collection_out(c) for c in qs])

    def post(self, request):
        amount = serializers.DecimalField(max_digits=14, decimal_places=2).run_validation(request.data.get("amount"))
        row = services.create_collection(user=request.user, branch=self.shift_branch(request), amount=amount,
                                         customer_name=str(request.data.get("customer_name", "")).strip())
        return Response(collection_out(row), status=201)


class CollectionDetailView(CollectionBase):
    def get(self, request, pk):
        row = get_object_or_404(self.rows(request), pk=pk)
        try:
            row = services.refresh_collection(row)
        except monime.ProviderError:
            pass  # show the last known state; the screen polls again
        return Response(collection_out(row))


class CollectionCancelView(CollectionBase):
    def post(self, request, pk):
        return Response(collection_out(services.cancel_collection(get_object_or_404(self.rows(request), pk=pk), user=request.user)))


class AttemptsView(StaffBase, APIView):
    required_permission = "order.manage"

    def get(self, request):
        from apps.inventory.selectors import branch_ids_for
        qs = PaymentAttempt.objects.select_related("order")
        ids = branch_ids_for(request.user)
        if ids:
            qs = qs.filter(order__branch_id__in=ids)
        if st := request.query_params.get("status"):
            qs = qs.filter(status=st)
        pg = PageNumberPagination()
        return pg.get_paginated_response([attempt_out(a) for a in pg.paginate_queryset(qs, request)])


class ReconcileView(StaffBase, APIView):
    required_permission = "accounting.manage"

    def post(self, request):
        return Response(services.reconcile(request.tenant, older_than_minutes=int(request.data.get("older_than_minutes", 5))))


class ReconciliationReportView(StaffBase, APIView):
    required_permission = "accounting.view"

    def get(self, request):
        return Response(services.reconciliation_report())


class StaffReceiptView(StaffBase, APIView):
    required_permission = "order.manage"
    pdf = False

    def get(self, request, pk):
        return _receipt_response(get_object_or_404(staff_orders(request.user), pk=pk), self.pdf)


class StaffReceiptPdfView(StaffReceiptView):
    pdf = True


class OrderRefundView(StaffBase, APIView):
    required_permission = "sales.refund"

    def post(self, request, pk):
        o = get_object_or_404(staff_orders(request.user), pk=pk)
        amount = serializers.DecimalField(max_digits=14, decimal_places=2).run_validation(request.data.get("amount"))
        r = services.refund_order(o.pk, user=request.user, amount=Decimal(amount), method=str(request.data.get("method", "")),
                                  reference=str(request.data.get("reference", "")), reason=str(request.data.get("reason", "")))
        o.refresh_from_db()
        return Response({"refund": r.pk, "order": order_out(o, True)}, status=201)
