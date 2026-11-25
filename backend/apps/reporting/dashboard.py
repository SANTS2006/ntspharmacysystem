"""Pharmacy dashboard: one call, scoped to the caller's branch when they are branch-scoped, with an optional date range."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.accounting import reports as ledger
from apps.accounts.models import User
from apps.inventory import selectors as inv_selectors
from apps.medicines.models import Medicine
from apps.payments.models import OrderRefund
from apps.prescriptions.models import Prescription
from apps.procurement.models import GoodsReceiptItem
from apps.procurement.services import supplier_balances
from apps.sales.models import Payment, Sale, SaleReturn
from apps.shop.models import Order
from apps.tenants.models import Branch

from . import reports

ZERO = Decimal("0.00")


def build(user, p: "reports.P") -> dict:
    today = timezone.localdate()
    sales = lambda **f: reports.P(p.date_from, p.date_to, p.branch).branch_q(Sale.objects.exclude(status="cancelled").filter(**f))  # noqa: E731
    net_sales = lambda qs, rq: (qs.aggregate(t=Sum("total"))["t"] or ZERO) - (rq.aggregate(t=Sum("refund_total"))["t"] or ZERO)  # noqa: E731
    returns = lambda **f: reports.P(p.date_from, p.date_to, p.branch).branch_q(SaleReturn.objects.filter(**f), "sale__branch_id")  # noqa: E731
    month_start = today.replace(day=1)
    alerts = inv_selectors.alerts(user)
    val = inv_selectors.valuation(user)
    staff = User.objects.filter(tenant=user.tenant, is_active=True).exclude(role__code="customer")
    if p.branch:
        staff = staff.filter(branch_id=p.branch)
    rx = reports.P(p.date_from, p.date_to, p.branch).dates(reports.P(p.date_from, p.date_to, p.branch).branch_q(Prescription.objects.all()), "created_at")
    orders = reports.P(p.date_from, p.date_to, p.branch).branch_q(Order.objects.all())
    pl = ledger.income_statement(p.date_from, p.date_to, p.branch)
    purchases = reports.P(p.date_from, p.date_to, p.branch).dates(reports.P(p.date_from, p.date_to, p.branch).branch_q(GoodsReceiptItem.objects.all(), "receipt__branch_id"), "created_at")
    from django.db.models import ExpressionWrapper, F, DecimalField
    purchase_value = purchases.aggregate(v=Sum(ExpressionWrapper(F("quantity") * F("unit_cost"), output_field=DecimalField(max_digits=16, decimal_places=2))))["v"] or ZERO
    refund_total = (returns(created_at__date__gte=p.date_from, created_at__date__lte=p.date_to).aggregate(t=Sum("refund_total"))["t"] or ZERO) + \
                   (reports.P(p.date_from, p.date_to, p.branch).dates(reports.P(p.date_from, p.date_to, p.branch).branch_q(OrderRefund.objects.all(), "order__branch_id"), "created_at").aggregate(t=Sum("amount"))["t"] or ZERO)
    return {
        "scope": "branch" if p.branch else "pharmacy", "range": {"from": p.date_from, "to": p.date_to},
        "people": {"branches": Branch.objects.filter(pk=p.branch).count() if p.branch else Branch.objects.count(), "employees": staff.count(), "pharmacists": staff.filter(role__code="pharmacist").count(),
                   "customers": User.objects.filter(tenant=user.tenant, role__code="customer").count() if not p.branch else None},
        "medicines": {"total": Medicine.objects.filter(status="active").count(), "low_stock": alerts["low_stock"].count(), "out_of_stock": alerts["out_of_stock"].count(),
                      "near_expiry_batches": alerts["near_expiry"].count(), "expired_batches": alerts["expired"].count(), "inventory_value": val["saleable_value"], "unsaleable_value": val["unsaleable_value"]},
        "sales": {"today": net_sales(sales(created_at__date=today), returns(created_at__date=today)), "month": net_sales(sales(created_at__date__gte=month_start), returns(created_at__date__gte=month_start)),
                  "range": net_sales(sales(created_at__date__gte=p.date_from, created_at__date__lte=p.date_to), returns(created_at__date__gte=p.date_from, created_at__date__lte=p.date_to)),
                  "transactions": sales(created_at__date__gte=p.date_from, created_at__date__lte=p.date_to).count()},
        "finance": {"revenue": pl["net_revenue"], "gross_profit": pl["gross_profit"], "expenses": pl["operating_expenses_total"], "net_profit_estimate": pl["net_profit"], "purchases": purchase_value,
                    "outstanding_supplier_payments": sum((b["outstanding"] for b in supplier_balances()), ZERO) if not p.branch else None, "returns_and_refunds": refund_total},
        "prescriptions": {r["status"]: r["n"] for r in rx.values("status").annotate(n=Count("id"))},
        "orders": {"pending": orders.filter(status__in=["pending", "awaiting_prescription", "prescription_approved", "awaiting_payment", "payment_confirmed", "processing", "preparing", "ready_for_pickup", "out_for_delivery"]).count(),
                   "completed": orders.filter(status__in=["delivered", "completed"], created_at__date__gte=p.date_from, created_at__date__lte=p.date_to).count()},
        "payment_breakdown": reports.payment_methods(p)[1],
        "branch_performance": reports.branch_performance(p)[1],
        "cashier_performance": reports.sales_by_cashier(p)[1],
    }
