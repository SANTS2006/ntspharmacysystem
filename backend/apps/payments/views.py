from decimal import Decimal

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantPermission
from apps.core.views import TenantContextMixin
from apps.sales.services import render_receipt_pdf
from apps.shop.models import Order
from apps.shop.views import IsVerifiedCustomer, order_out, staff_orders
from apps.tenants.models import Pharmacy

from . import services
from .models import OrderReceipt, PaymentAttempt, PaymentProviderConfig

MAX_WEBHOOK_BYTES = 64 * 1024


@csrf_exempt
@require_POST
def monime_webhook(request, slug):
    """Public endpoint. Authenticity comes only from the HMAC signature over the raw body, checked with this pharmacy's own secret."""
    tenant = Pharmacy.objects.filter(slug=slug, status=Pharmacy.Status.ACTIVE).first()
    if tenant is None:
        return JsonResponse({"error": "not_found"}, status=404)
    raw = request.body
    if len(raw) > MAX_WEBHOOK_BYTES:
        return JsonResponse({"error": "too_large"}, status=413)
    code, outcome = services.handle_webhook(tenant, raw, request.headers.get("Monime-Signature", ""))
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


# ---------------- staff ----------------
class StaffBase(TenantContextMixin):
    permission_classes = [HasTenantPermission]


class ConfigSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    space_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    access_token = serializers.CharField(max_length=500, required=False, allow_blank=True, write_only=True)
    webhook_secret = serializers.CharField(max_length=200, required=False, allow_blank=True, write_only=True)


def config_out(request):
    row = PaymentProviderConfig.objects.filter(provider="monime").first()
    path = f"/api/v1/webhooks/monime/{request.tenant.slug}/"
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return {"provider": "monime", "enabled": bool(row and row.enabled), "space_id": row.space_id if row else "",
            "access_token_set": bool(row and row.access_token_enc), "webhook_secret_set": bool(row and row.webhook_secret_enc),
            "webhook_path": path, "webhook_url": base + path if base else None}


class ConfigView(StaffBase, APIView):
    required_permissions = {"GET": "settings.manage", "PUT": "settings.manage"}

    def get(self, request):
        return Response(config_out(request))

    def put(self, request):
        s = ConfigSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.save_config(user=request.user, **s.validated_data)
        return Response(config_out(request))  # secrets are write-only: never echoed


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
