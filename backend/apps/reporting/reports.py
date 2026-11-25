"""Report definitions. Every report is a function (params) -> (columns, rows, summary) over tenant-scoped querysets; branch-scoped users are
forced onto their own branch by the caller. Numbers stay Decimal/int here and are formatted by the exporters."""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek, TruncYear
from django.utils import timezone

from apps.accounting import reports as ledger
from apps.hr.models import AttendanceRecord
from apps.inventory import services as inv
from apps.inventory.models import Batch, StockMovement, StockTransfer
from apps.medicines.models import Medicine
from apps.payroll.models import PayrollRun
from apps.prescriptions.models import Prescription
from apps.procurement.models import GoodsReceipt, GoodsReceiptItem, PurchaseOrder, PurchaseReturn
from apps.procurement.services import supplier_balances
from apps.sales.models import Payment, Sale, SaleLine, SaleReturn
from apps.shop.models import Order
from apps.accounts.models import User

ZERO = Decimal("0.00")
Z = lambda v: v if v is not None else ZERO  # noqa: E731
col = lambda key, label, kind="text": {"key": key, "label": label, "kind": kind}  # noqa: E731  (kind: text | int | money | date)


class P:
    """Normalised report parameters."""

    def __init__(self, date_from=None, date_to=None, branch=None, group="day", days=90):
        self.date_to = date_to or timezone.localdate()
        self.date_from = date_from or (self.date_to - timedelta(days=30))
        self.branch, self.group, self.days = branch, group if group in ("day", "week", "month", "year") else "day", days

    def dates(self, qs, field):
        return qs.filter(**{f"{field}__date__gte": self.date_from, f"{field}__date__lte": self.date_to})

    def branch_q(self, qs, field="branch_id"):
        return qs.filter(**{field: self.branch}) if self.branch else qs


TRUNC = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth, "year": TruncYear}


def _sales(p):
    return p.branch_q(p.dates(Sale.objects.exclude(status="cancelled"), "created_at"))


# ---------------- sales ----------------
def sales_summary(p):
    t = TRUNC[p.group]
    rows = {r["p"].date(): {"period": r["p"].date(), "sales": r["n"], "subtotal": Z(r["sub"]), "discounts": Z(r["d"]), "tax": Z(r["tax"]), "total": Z(r["tot"]), "refunds": ZERO}
            for r in _sales(p).annotate(p=t("created_at")).values("p").annotate(n=Count("id"), sub=Sum("subtotal"), d=Sum("discount_total"), tax=Sum("tax_total"), tot=Sum("total"))}
    refunds = p.branch_q(p.dates(SaleReturn.objects.all(), "created_at"), "sale__branch_id")
    for r in refunds.annotate(p=t("created_at")).values("p").annotate(x=Sum("refund_total")):
        rows.setdefault(r["p"].date(), {"period": r["p"].date(), "sales": 0, "subtotal": ZERO, "discounts": ZERO, "tax": ZERO, "total": ZERO, "refunds": ZERO})["refunds"] = Z(r["x"])
    out = sorted(rows.values(), key=lambda r: r["period"])
    for r in out:
        r["net_sales"] = r["total"] - r["refunds"]
    summary = {"sales": sum(r["sales"] for r in out), "total": sum((r["total"] for r in out), ZERO), "refunds": sum((r["refunds"] for r in out), ZERO), "net_sales": sum((r["net_sales"] for r in out), ZERO)}
    return [col("period", "Period", "date"), col("sales", "Sales", "int"), col("subtotal", "Subtotal", "money"), col("discounts", "Discounts", "money"), col("tax", "Tax", "money"),
            col("total", "Total", "money"), col("refunds", "Refunds", "money"), col("net_sales", "Net sales", "money")], out, summary


def sales_by_product(p):
    qs = SaleLine.objects.filter(sale__in=_sales(p))
    rows = [{"product": r["medicine__name"], "category": r["medicine__category__name"], "quantity": r["q"], "returned": r["ret"], "revenue": Z(r["rev"])}
            for r in qs.values("medicine__name", "medicine__category__name").annotate(q=Sum("quantity"), ret=Sum("quantity_returned"), rev=Sum("line_total")).order_by("-rev")]
    return [col("product", "Product"), col("category", "Category"), col("quantity", "Qty sold", "int"), col("returned", "Qty returned", "int"), col("revenue", "Revenue (incl. tax)", "money")], rows, {"products": len(rows)}


def sales_by_category(p):
    qs = SaleLine.objects.filter(sale__in=_sales(p))
    rows = [{"category": r["medicine__category__name"], "quantity": r["q"], "revenue": Z(r["rev"])} for r in qs.values("medicine__category__name").annotate(q=Sum("quantity"), rev=Sum("line_total")).order_by("-rev")]
    return [col("category", "Category"), col("quantity", "Qty sold", "int"), col("revenue", "Revenue (incl. tax)", "money")], rows, {}


def sales_by_cashier(p):
    refunds = {r["processed_by"]: Z(r["x"]) for r in p.branch_q(p.dates(SaleReturn.objects.all(), "created_at"), "sale__branch_id").values("processed_by").annotate(x=Sum("refund_total"))}
    rows = [{"cashier": r["cashier__full_name"], "sales": r["n"], "total": Z(r["t"]), "average": Z(r["a"]).quantize(Decimal("0.01")), "refunds_processed": refunds.get(r["cashier"], ZERO)}
            for r in _sales(p).values("cashier", "cashier__full_name").annotate(n=Count("id"), t=Sum("total"), a=Avg("total")).order_by("-t")]
    return [col("cashier", "Cashier"), col("sales", "Sales", "int"), col("total", "Total", "money"), col("average", "Average sale", "money"), col("refunds_processed", "Refunds processed", "money")], rows, {}


def sales_by_branch(p):
    rows = [{"branch": r["branch__name"], "sales": r["n"], "total": Z(r["t"])} for r in _sales(p).values("branch__name").annotate(n=Count("id"), t=Sum("total")).order_by("-t")]
    return [col("branch", "Branch"), col("sales", "Sales", "int"), col("total", "Total", "money")], rows, {}


def payment_methods(p):
    qs = p.branch_q(p.dates(Payment.objects.all(), "created_at"), "sale__branch_id")
    rows = [{"method": r["method"].replace("_", " "), "payments": r["n"], "amount": Z(r["t"])} for r in qs.values("method").annotate(n=Count("id"), t=Sum("amount")).order_by("-t")]
    return [col("method", "Method"), col("payments", "Payments", "int"), col("amount", "Amount", "money")], rows, {"total": sum((r["amount"] for r in rows), ZERO)}


def online_orders(p):
    qs = p.branch_q(p.dates(Order.objects.all(), "created_at"))
    rows = [{"status": r["status"].replace("_", " "), "orders": r["n"], "value": Z(r["t"])} for r in qs.values("status").annotate(n=Count("id"), t=Sum("total")).order_by("status")]
    return [col("status", "Status"), col("orders", "Orders", "int"), col("value", "Value", "money")], rows, {"orders": sum(r["orders"] for r in rows)}


# ---------------- inventory ----------------
def _batches(p):
    return p.branch_q(Batch.objects.select_related("medicine", "branch").filter(quantity_available__gt=0))


def stock_current(p):
    value = ExpressionWrapper(F("quantity_available") * F("purchase_cost"), output_field=DecimalField(max_digits=16, decimal_places=2))
    rows = [{"medicine": r["medicine__name"], "branch": r["branch__name"], "saleable": r["q"], "value": Z(r["v"])}
            for r in _batches(p).filter(inv.saleable_q()).values("medicine__name", "branch__name").annotate(q=Sum("quantity_available"), v=Sum(value)).order_by("medicine__name")]
    return [col("medicine", "Medicine"), col("branch", "Branch"), col("saleable", "Saleable qty", "int"), col("value", "Value at cost", "money")], rows, {"value": sum((r["value"] for r in rows), ZERO)}


def stock_valuation(p):
    value = ExpressionWrapper(F("quantity_available") * F("purchase_cost"), output_field=DecimalField(max_digits=16, decimal_places=2))
    rows = []
    for r in _batches(p).values("branch__name").annotate(total=Sum(value), saleable=Sum(value, filter=inv.saleable_q())).order_by("branch__name"):
        rows.append({"branch": r["branch__name"], "saleable_value": Z(r["saleable"]), "unsaleable_value": Z(r["total"]) - Z(r["saleable"]), "total_value": Z(r["total"])})
    return [col("branch", "Branch"), col("saleable_value", "Saleable", "money"), col("unsaleable_value", "Expired/held", "money"), col("total_value", "Total", "money")], rows, {}


def _stock_levels(p):
    qs = Medicine.objects.filter(status="active")
    out = []
    for m in qs:
        bq = Batch.objects.filter(medicine=m).filter(inv.saleable_q())
        bq = p.branch_q(bq)
        out.append((m, bq.aggregate(t=Sum("quantity_available"))["t"] or 0))
    return out


def low_stock(p):
    rows = [{"medicine": m.name, "saleable": q, "reorder_level": m.reorder_level} for m, q in _stock_levels(p) if 0 < q <= m.reorder_level]
    return [col("medicine", "Medicine"), col("saleable", "Saleable qty", "int"), col("reorder_level", "Reorder level", "int")], rows, {}


def out_of_stock(p):
    rows = [{"medicine": m.name, "reorder_level": m.reorder_level} for m, q in _stock_levels(p) if q == 0]
    return [col("medicine", "Medicine"), col("reorder_level", "Reorder level", "int")], rows, {}


def _batch_rows(qs):
    return [{"medicine": b.medicine.name, "branch": b.branch.name, "batch": b.batch_number, "expiry": b.expiry_date, "quantity": b.quantity_available, "status": b.status, "value": b.quantity_available * b.purchase_cost} for b in qs.order_by("expiry_date")]


BATCH_COLS = [col("medicine", "Medicine"), col("branch", "Branch"), col("batch", "Batch"), col("expiry", "Expiry", "date"), col("quantity", "Qty", "int"), col("status", "Status"), col("value", "Value at cost", "money")]


def expired_stock(p):
    return BATCH_COLS, _batch_rows(_batches(p).filter(expiry_date__lt=inv.today())), {}


def near_expiry(p):
    return BATCH_COLS, _batch_rows(_batches(p).filter(inv.saleable_q(), expiry_date__lte=inv.today() + timedelta(days=p.days))), {"days": p.days}


def stock_movements(p, types=None):
    qs = p.branch_q(p.dates(StockMovement.objects.select_related("medicine", "batch", "branch", "user"), "created_at"))
    if types:
        qs = qs.filter(movement_type__in=types)
    rows = [{"when": m.created_at.date(), "medicine": m.medicine.name, "batch": m.batch.batch_number, "branch": m.branch.name, "type": m.movement_type, "change": m.quantity_change,
             "before": m.previous_quantity, "after": m.new_quantity, "by": m.user.full_name if m.user else "", "reason": m.reason} for m in qs.order_by("-created_at")[:5000]]
    return [col("when", "Date", "date"), col("medicine", "Medicine"), col("batch", "Batch"), col("branch", "Branch"), col("type", "Type"), col("change", "Change", "int"),
            col("before", "Before", "int"), col("after", "After", "int"), col("by", "By"), col("reason", "Reason")], rows, {}


def damaged_and_adjustments(p):
    return stock_movements(p, ["adjustment", "damage", "expiry_writeoff", "purchase_return"])


def stock_transfers(p):
    qs = p.dates(StockTransfer.objects.select_related("medicine", "from_branch", "to_branch", "created_by"), "created_at")
    if p.branch:
        qs = qs.filter(Q(from_branch_id=p.branch) | Q(to_branch_id=p.branch))
    rows = [{"when": t.created_at.date(), "medicine": t.medicine.name, "from": t.from_branch.name, "to": t.to_branch.name, "quantity": t.quantity, "by": t.created_by.full_name if t.created_by else ""} for t in qs]
    return [col("when", "Date", "date"), col("medicine", "Medicine"), col("from", "From"), col("to", "To"), col("quantity", "Qty", "int"), col("by", "By")], rows, {}


# ---------------- procurement ----------------
def supplier_purchases(p):
    qs = p.branch_q(p.dates(GoodsReceiptItem.objects.all(), "created_at"), "receipt__branch_id")
    value = ExpressionWrapper(F("quantity") * F("unit_cost"), output_field=DecimalField(max_digits=16, decimal_places=2))
    rows = [{"supplier": r["receipt__order__supplier__name"], "receipts": r["n"], "value": Z(r["v"])} for r in qs.values("receipt__order__supplier__name").annotate(n=Count("receipt", distinct=True), v=Sum(value)).order_by("-v")]
    return [col("supplier", "Supplier"), col("receipts", "Goods receipts", "int"), col("value", "Value received", "money")], rows, {"total": sum((r["value"] for r in rows), ZERO)}


def purchase_history(p):
    qs = p.branch_q(p.dates(PurchaseOrder.objects.select_related("supplier", "branch"), "created_at"))
    rows = [{"number": o.number, "date": o.created_at.date(), "supplier": o.supplier.name, "branch": o.branch.name, "status": o.status.replace("_", " "), "total": o.total} for o in qs]
    return [col("number", "Order"), col("date", "Date", "date"), col("supplier", "Supplier"), col("branch", "Branch"), col("status", "Status"), col("total", "Total", "money")], rows, {}


def supplier_outstanding(p):
    rows = [{"supplier": b["name"], "invoiced": b["invoiced"], "paid": b["paid"], "outstanding": b["outstanding"]} for b in supplier_balances()]
    return [col("supplier", "Supplier"), col("invoiced", "Invoiced", "money"), col("paid", "Paid", "money"), col("outstanding", "Outstanding", "money")], rows, {"total": sum((r["outstanding"] for r in rows), ZERO)}


def purchase_returns(p):
    qs = p.branch_q(p.dates(PurchaseReturn.objects.select_related("supplier", "batch__medicine", "batch__branch"), "created_at"), "batch__branch_id")
    rows = [{"date": r.created_at.date(), "supplier": r.supplier.name, "medicine": r.batch.medicine.name, "quantity": r.quantity, "credit": r.credit_amount, "reason": r.reason} for r in qs]
    return [col("date", "Date", "date"), col("supplier", "Supplier"), col("medicine", "Medicine"), col("quantity", "Qty", "int"), col("credit", "Credit", "money"), col("reason", "Reason")], rows, {}


# ---------------- prescriptions ----------------
def prescriptions_summary(p):
    qs = p.branch_q(p.dates(Prescription.objects.all(), "created_at"))
    rows = [{"status": r["status"].replace("_", " "), "prescriptions": r["n"]} for r in qs.values("status").annotate(n=Count("id")).order_by("status")]
    return [col("status", "Status"), col("prescriptions", "Prescriptions", "int")], rows, {"total": sum(r["prescriptions"] for r in rows)}


# ---------------- financial ----------------
def refunds_report(p):
    pos = p.branch_q(p.dates(SaleReturn.objects.select_related("sale", "processed_by"), "created_at"), "sale__branch_id")
    rows = [{"date": r.created_at.date(), "type": "POS cancellation" if r.is_cancellation else "POS return", "reference": r.number, "against": r.sale.reference_number, "method": r.refund_method, "amount": r.refund_total, "by": r.processed_by.full_name if r.processed_by else ""} for r in pos]
    from apps.payments.models import OrderRefund
    for r in p.branch_q(p.dates(OrderRefund.objects.select_related("order", "processed_by"), "created_at"), "order__branch_id"):
        rows.append({"date": r.created_at.date(), "type": "Online order refund", "reference": r.reference, "against": r.order.reference_number, "method": r.method, "amount": r.amount, "by": r.processed_by.full_name if r.processed_by else ""})
    rows.sort(key=lambda r: r["date"], reverse=True)
    return [col("date", "Date", "date"), col("type", "Type"), col("reference", "Reference"), col("against", "Against"), col("method", "Method"), col("amount", "Amount", "money"), col("by", "By")], rows, {"total": sum((r["amount"] for r in rows), ZERO)}


def profit_and_loss(p):
    d = ledger.income_statement(p.date_from, p.date_to, p.branch)
    rows = [{"section": s, "code": x["code"], "account": x["name"], "amount": x["amount"]} for s, k in (("Revenue", "revenue"), ("Cost of sales", "cost_of_sales"), ("Operating expenses", "operating_expenses")) for x in d[k]]
    rows += [{"section": "Result", "code": "", "account": "Gross profit", "amount": d["gross_profit"]}, {"section": "Result", "code": "", "account": "Net profit", "amount": d["net_profit"]}]
    return [col("section", "Section"), col("code", "Code"), col("account", "Account"), col("amount", "Amount", "money")], rows, {"net_profit": d["net_profit"]}


def cash_flow_report(p):
    d = ledger.cash_flow(p.date_from, p.date_to, p.branch)
    rows = [{"source": r["source"].replace("_", " "), "inflow": r["inflow"], "outflow": r["outflow"], "net": r["net"]} for r in d["by_source"]]
    return [col("source", "Source"), col("inflow", "Inflow", "money"), col("outflow", "Outflow", "money"), col("net", "Net", "money")], rows, {"opening": d["opening_cash"], "closing": d["closing_cash"]}


# ---------------- staff ----------------
def attendance_summary(p):
    qs = AttendanceRecord.objects.filter(date__gte=p.date_from, date__lte=p.date_to)
    if p.branch:
        qs = qs.filter(user__branch_id=p.branch)
    rows = [{"staff": r["user__full_name"], "present": r["pr"], "late": r["la"], "absent": r["ab"], "on_leave": r["ol"], "days_recorded": r["n"]}
            for r in qs.values("user__full_name").annotate(n=Count("id"), pr=Count("id", filter=Q(status="present")), la=Count("id", filter=Q(status="late")), ab=Count("id", filter=Q(status="absent")), ol=Count("id", filter=Q(status="on_leave"))).order_by("user__full_name")]
    return [col("staff", "Staff"), col("present", "Present", "int"), col("late", "Late", "int"), col("absent", "Absent", "int"), col("on_leave", "On leave", "int"), col("days_recorded", "Days recorded", "int")], rows, {}


def branch_performance(p):
    rows = [{"branch": r["name"], "net_revenue": r["net_revenue"], "cost_of_sales": r["cost_of_sales"], "gross_profit": r["gross_profit"], "operating_expenses": r["operating_expenses"], "net_profit": r["net_profit"]}
            for r in ledger.branch_summary(p.date_from, p.date_to) if not p.branch or r["branch"] == p.branch]
    return [col("branch", "Branch"), col("net_revenue", "Net revenue", "money"), col("cost_of_sales", "Cost of sales", "money"), col("gross_profit", "Gross profit", "money"),
            col("operating_expenses", "Expenses", "money"), col("net_profit", "Net profit", "money")], rows, {}


def payroll_summary(p):
    rows = []
    for r in PayrollRun.objects.exclude(status="cancelled").filter(period__gte=p.date_from.strftime("%Y-%m"), period__lte=p.date_to.strftime("%Y-%m")):
        lines = r.lines.filter(user__branch_id=p.branch) if p.branch else r.lines.all()  # branch-scoped viewers only ever total their own branch
        t = lines.aggregate(g=Sum("gross"), n=Sum("net"), x=Sum("tax"), paid=Sum("paid_amount"), c=Count("id"))
        rows.append({"period": r.period, "status": r.status, "staff": t["c"], "gross": Z(t["g"]), "tax": Z(t["x"]), "net": Z(t["n"]), "paid": Z(t["paid"])})
    return [col("period", "Period"), col("status", "Status"), col("staff", "Staff", "int"), col("gross", "Gross", "money"), col("tax", "Tax", "money"), col("net", "Net", "money"), col("paid", "Paid", "money")], rows, {}


# slug -> (title, group, any-of permissions, function)
REGISTRY = {
    "sales-summary": ("POS sales summary", "Sales", ("report.view",), sales_summary),
    "sales-by-product": ("POS sales by product", "Sales", ("report.view",), sales_by_product),
    "sales-by-category": ("POS sales by category", "Sales", ("report.view",), sales_by_category),
    "sales-by-cashier": ("Cashier performance", "Sales", ("report.view",), sales_by_cashier),
    "sales-by-branch": ("POS sales by branch", "Sales", ("report.view",), sales_by_branch),
    "payment-methods": ("Payment method breakdown", "Sales", ("report.view",), payment_methods),
    "online-orders": ("Online orders by status", "Sales", ("report.view",), online_orders),
    "stock-current": ("Current stock", "Inventory", ("report.view",), stock_current),
    "stock-valuation": ("Stock valuation", "Inventory", ("report.view",), stock_valuation),
    "low-stock": ("Low stock", "Inventory", ("report.view",), low_stock),
    "out-of-stock": ("Out of stock", "Inventory", ("report.view",), out_of_stock),
    "expired-stock": ("Expired medicines", "Inventory", ("report.view",), expired_stock),
    "near-expiry": ("Near-expiry medicines", "Inventory", ("report.view",), near_expiry),
    "stock-movements": ("Stock movements", "Inventory", ("report.view",), stock_movements),
    "stock-adjustments": ("Damaged stock and adjustments", "Inventory", ("report.view",), damaged_and_adjustments),
    "stock-transfers": ("Stock transfers", "Inventory", ("report.view",), stock_transfers),
    "supplier-purchases": ("Supplier purchases", "Procurement", ("procurement.view", "accounting.view"), supplier_purchases),
    "purchase-history": ("Purchase history", "Procurement", ("procurement.view", "accounting.view"), purchase_history),
    "supplier-outstanding": ("Outstanding supplier balances", "Procurement", ("accounting.view",), supplier_outstanding),
    "purchase-returns": ("Purchase returns", "Procurement", ("procurement.view", "accounting.view"), purchase_returns),
    "prescriptions-summary": ("Prescriptions by status", "Prescriptions", ("report.view",), prescriptions_summary),
    "refunds": ("Refunds and credit notes", "Financial", ("accounting.view",), refunds_report),
    "profit-and-loss": ("Profit and loss", "Financial", ("accounting.view",), profit_and_loss),
    "cash-flow": ("Cash flow", "Financial", ("accounting.view",), cash_flow_report),
    "branch-performance": ("Branch performance", "Staff & branches", ("report.view",), branch_performance),
    "attendance-summary": ("Attendance summary", "Staff & branches", ("hr.view",), attendance_summary),
    "payroll-summary": ("Payroll summary", "Staff & branches", ("payroll.view",), payroll_summary),
}
