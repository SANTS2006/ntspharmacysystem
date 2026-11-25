from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.generics import ListAPIView, ListCreateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsPlatformAdmin
from apps.tenants.models import Pharmacy

from . import services
from .models import Invoice, Plan


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "code", "name", "price", "currency", "interval", "max_branches", "max_users", "features", "is_active"]


class InvoiceSerializer(serializers.ModelSerializer):
    pharmacy_name = serializers.CharField(source="pharmacy.name", read_only=True)

    class Meta:
        model = Invoice
        fields = ["id", "number", "pharmacy", "pharmacy_name", "plan", "amount", "currency", "status", "due_date",
                  "paid_at", "payment_method", "payment_reference", "refunded_amount", "refunded_at", "created_at"]
        read_only_fields = fields


class PlanListCreateView(ListCreateAPIView):
    permission_classes = [IsPlatformAdmin]
    queryset = Plan.objects.all().order_by("price")
    serializer_class = PlanSerializer
    pagination_class = None


class InvoiceListView(ListAPIView):
    permission_classes = [IsPlatformAdmin]
    queryset = Invoice.objects.select_related("pharmacy").all()
    serializer_class = InvoiceSerializer
    filterset_fields = ["status", "pharmacy"]
    search_fields = ["number", "pharmacy__name", "payment_reference"]
    ordering_fields = ["created_at", "amount", "due_date"]


class IssueInvoiceView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request):
        pharmacy = get_object_or_404(Pharmacy, pk=request.data.get("pharmacy"))
        plan = get_object_or_404(Plan, pk=request.data.get("plan"), is_active=True)
        inv = services.issue_invoice(pharmacy=pharmacy, plan=plan, actor=request.user, request=request)
        return Response(InvoiceSerializer(inv).data, status=201)


class InvoiceActionView(APIView):
    permission_classes = [IsPlatformAdmin]
    action = ""

    def post(self, request, pk):
        get_object_or_404(Invoice, pk=pk)
        d = request.data
        if self.action == "pay":
            inv = services.mark_paid(pk, method=str(d.get("payment_method", ""))[:30],
                                     reference=str(d.get("payment_reference", "")).strip()[:100], actor=request.user, request=request)
        elif self.action == "refund":
            try:
                amount = Decimal(str(d.get("amount")))
            except InvalidOperation:
                raise serializers.ValidationError({"amount": "Enter a valid amount."})
            inv = services.refund(pk, amount=amount, reason=str(d.get("reason", ""))[:255], actor=request.user, request=request)
        else:
            inv = services.void_invoice(pk, actor=request.user, request=request)
        return Response(InvoiceSerializer(inv).data)


class PayView(InvoiceActionView):
    action = "pay"


class RefundView(InvoiceActionView):
    action = "refund"


class VoidView(InvoiceActionView):
    action = "void"


class RevenueSummaryView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        s = lambda **f: Invoice.objects.filter(**f).aggregate(t=Sum("amount"))["t"] or 0  # noqa: E731
        refunded = Invoice.objects.aggregate(t=Sum("refunded_amount"))["t"] or 0
        paid = s(status__in=["paid", "refunded"])
        return Response({"collected": paid, "refunded": refunded, "net_revenue": paid - refunded,
                         "outstanding": s(status="issued"), "currency_note": "Totals are summed across invoices; mixed currencies are not converted."})
