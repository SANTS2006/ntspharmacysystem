"""A pharmacy's own subscription and invoices, with online payment. Scoped to the caller's pharmacy: no tenant id is ever accepted."""
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantPermission
from apps.core.views import TenantContextMixin
from apps.payments import monime

from . import services
from .models import Invoice, Subscription


def invoice_out(i: Invoice):
    return {"id": i.pk, "number": i.number, "plan": i.plan.name if i.plan_id else None, "amount": i.amount, "currency": i.currency, "status": i.status,
            "due_date": i.due_date, "paid_at": i.paid_at, "payment_method": i.payment_method, "payment_reference": i.payment_reference,
            "created_at": i.created_at, "payable_online": i.status == "issued" and monime.ready() and i.currency in monime.CURRENCIES,
            "checkout_open": bool(i.checkout_url) and i.status == "issued"}


class Base(TenantContextMixin, APIView):
    permission_classes = [HasTenantPermission]
    required_permission = "settings.manage"

    def mine(self):
        return Invoice.objects.filter(pharmacy=self.request.user.tenant).select_related("plan")


class SubscriptionView(Base):
    def get(self, request):
        sub = Subscription.objects.select_related("plan").filter(pharmacy=request.user.tenant).first()
        return Response({"subscription": None if not sub else {"plan": sub.plan.name, "price": sub.plan.price, "currency": sub.plan.currency,
                                                             "interval": sub.plan.interval, "status": sub.status, "current_period_end": sub.current_period_end,
                                                             "features": sub.plan.features},
                         "invoices": [invoice_out(i) for i in self.mine()[:100]]})


class PayInvoiceView(Base):
    def post(self, request, pk):
        inv = get_object_or_404(self.mine(), pk=pk)
        inv = services.start_invoice_checkout(inv.pk, actor=request.user, request=request)
        if inv.status == "paid":
            return Response({"paid": True, "redirect_url": None})
        return Response({"paid": False, "redirect_url": inv.checkout_url})


class RefreshInvoiceView(Base):
    def post(self, request, pk):
        inv = get_object_or_404(self.mine(), pk=pk)
        if inv.status == "issued" and inv.provider_session_id:
            try:
                services.apply_invoice_session(inv.pk, monime.retrieve_checkout_session(inv.provider_session_id))
            except monime.ProviderError:
                pass
        return Response(invoice_out(self.mine().get(pk=pk)))
