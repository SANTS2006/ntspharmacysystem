"""Dashboard analytics. Every section is built only when the caller's role grants it (a section that is not allowed is absent, not empty),
and branch-scoped users only ever see figures for their own branch. All numbers come from the database."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay, TruncDate, TruncMonth
from django.utils import timezone

from apps.accounting.models import JournalLine
from apps.accounts.models import LoginHistory, User
from apps.delivery.models import Delivery
from apps.engagement.models import Appointment, CustomerInquiry, Feedback
from apps.hr.models import AttendanceRecord, LeaveRequest
from apps.inventory import selectors as inv_selectors
from apps.inventory.services import saleable_q
from apps.medicines.models import Medicine
from apps.prescriptions.models import Prescription
from apps.procurement.models import PurchaseOrder
from apps.sales.models import Payment, Sale, SaleLine, SaleReturn
from apps.shop.models import Order, OrderLine

ZERO = Decimal("0.00")
PAID_ONLINE = ["payment_confirmed", "processing", "preparing", "ready_for_pickup", "out_for_delivery", "delivered", "completed"]
MONEY = DecimalField(max_digits=18, decimal_places=2)


def _series(start, days, **maps):
    """One row per calendar day, with zeros for quiet days, so charts never skip time."""
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        out.append({"date": d.isoformat(), **{k: m.get(d, 0) for k, m in maps.items()}})
    return out


def _daily(qs, value=None):
    agg = Sum(value) if value else Count("id")
    return {r["d"]: r["v"] for r in qs.annotate(d=TruncDate("created_at")).values("d").annotate(v=agg)}


def _counts(qs, field="status"):
    return [{"label": r[field] or "other", "value": r["n"]} for r in qs.values(field).annotate(n=Count("id")).order_by("-n")]


def _total(qs, field):
    return qs.aggregate(t=Sum(field))["t"] or ZERO


class Scope:
    def __init__(self, user, days):
        self.user, self.days = user, days
        self.branch = user.branch_id if user.is_branch_scoped else None
        self.today = timezone.localdate()
        self.start = self.today - timedelta(days=days - 1)
        self.prev_start = self.start - timedelta(days=days)

    def b(self, qs, field="branch_id"):
        return qs.filter(**{field: self.branch}) if self.branch else qs

    def now(self, qs, field="created_at"):
        return qs.filter(**{f"{field}__date__gte": self.start, f"{field}__date__lte": self.today})

    def before(self, qs, field="created_at"):
        return qs.filter(**{f"{field}__date__gte": self.prev_start, f"{field}__date__lt": self.start})


def sales_section(s: Scope, own_only: bool):
    sales = s.b(Sale.objects.exclude(status="cancelled"))
    orders = s.b(Order.objects.filter(status__in=PAID_ONLINE))
    if own_only:
        sales, orders = sales.filter(cashier=s.user), orders.none()
    pos_now, online_now = s.now(sales), s.now(orders)
    returns = s.now(s.b(SaleReturn.objects.all(), "sale__branch_id"))
    if own_only:
        returns = returns.filter(sale__cashier=s.user)
    pos_total, online_total = _total(pos_now, "total"), _total(online_now, "total")
    previous = _total(s.before(sales), "total") + _total(s.before(orders), "total")
    revenue = pos_total + online_total
    count = pos_now.count() + online_now.count()
    methods = {r["method"]: r["t"] for r in Payment.objects.filter(sale__in=pos_now).values("method").annotate(t=Sum("amount"))}
    for r in online_now.values("payment_method").annotate(t=Sum("total")):
        key = "online mobile money" if r["payment_method"] == "monime" else r["payment_method"]
        methods[key] = methods.get(key, ZERO) + r["t"]
    lines = SaleLine.objects.filter(sale__in=pos_now)
    online_lines = OrderLine.objects.filter(order__in=online_now)
    products, categories = {}, {}
    for qs in (lines, online_lines):
        for r in qs.values("medicine__name", "medicine__category__name").annotate(q=Sum("quantity"), t=Sum("line_total")):
            p = products.setdefault(r["medicine__name"], {"label": r["medicine__name"], "value": ZERO, "quantity": 0})
            p["value"] += r["t"]
            p["quantity"] += r["q"]
            categories[r["medicine__category__name"]] = categories.get(r["medicine__category__name"], ZERO) + r["t"]
    hours = {r["h"]: r["n"] for r in pos_now.annotate(h=ExtractHour("created_at")).values("h").annotate(n=Count("id"))}
    week = {r["w"]: r["t"] for r in pos_now.annotate(w=ExtractIsoWeekDay("created_at")).values("w").annotate(t=Sum("total"))}
    today_value = _total(sales.filter(created_at__date=s.today), "total") + _total(orders.filter(created_at__date=s.today), "total")
    data = {
        "own_only": own_only, "revenue": revenue, "previous_revenue": previous, "transactions": count, "today": today_value,
        "average_sale": (revenue / count).quantize(Decimal("0.01")) if count else ZERO,
        "refunds": _total(returns, "refund_total"), "discounts": _total(pos_now, "discount_total"), "tax": _total(pos_now, "tax_total") + _total(online_now, "tax_total"),
        "trend": _series(s.start, s.days, pos=_daily(pos_now, "total"), online=_daily(online_now, "total")),
        "payment_methods": sorted(({"label": k, "value": v} for k, v in methods.items()), key=lambda r: -r["value"]),
        "top_products": sorted(products.values(), key=lambda r: -r["value"])[:8],
        "categories": sorted(({"label": k, "value": v} for k, v in categories.items()), key=lambda r: -r["value"])[:8],
        "by_hour": [{"label": f"{h:02d}:00", "value": hours.get(h, 0)} for h in range(24)],
        "by_weekday": [{"label": n, "value": week.get(i, ZERO)} for i, n in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], 1)],
    }
    if not own_only:
        if not s.branch:
            by_branch = {}
            for qs in (pos_now, online_now):
                for r in qs.values("branch__name").annotate(t=Sum("total")):
                    by_branch[r["branch__name"]] = by_branch.get(r["branch__name"], ZERO) + r["t"]
            data["by_branch"] = sorted(({"label": k, "value": v} for k, v in by_branch.items()), key=lambda r: -r["value"])
        data["by_cashier"] = [{"label": r["cashier__full_name"], "value": r["t"]} for r in pos_now.values("cashier__full_name").annotate(t=Sum("total")).order_by("-t")[:8]]
    return data


def orders_section(s: Scope):
    qs = s.b(Order.objects.all())
    window = s.now(qs)
    return {"total": window.count(), "open": qs.exclude(status__in=["delivered", "completed", "cancelled", "refunded", "prescription_rejected"]).count(),
            "by_status": _counts(window), "by_fulfilment": _counts(window, "fulfilment"), "trend": _series(s.start, s.days, orders=_daily(window))}


def inventory_section(s: Scope):
    alerts = inv_selectors.alerts(s.user)
    val = inv_selectors.valuation(s.user)
    batches = inv_selectors.scoped_batches(s.user).filter(saleable_q(), quantity_available__gt=0)
    value = ExpressionWrapper(F("quantity_available") * F("purchase_cost"), output_field=MONEY)
    cats = batches.values("medicine__category__name").annotate(t=Sum(value)).order_by("-t")[:8]
    return {"products": Medicine.objects.filter(status="active").count(), "stock_value": val["saleable_value"], "unsaleable_value": val["unsaleable_value"],
            "low_stock": alerts["low_stock"].count(), "out_of_stock": alerts["out_of_stock"].count(), "near_expiry": alerts["near_expiry"].count(),
            "expired": alerts["expired"].count(), "value_by_category": [{"label": r["medicine__category__name"], "value": r["t"]} for r in cats],
            "expiring_soon": [{"medicine": b.medicine.name, "batch": b.batch_number, "branch": b.branch.name, "expiry": b.expiry_date, "quantity": b.quantity_available}
                              for b in alerts["near_expiry"].select_related("medicine", "branch")[:6]]}


def prescriptions_section(s: Scope):
    qs = s.b(Prescription.objects.all())
    window = s.now(qs)
    return {"total": window.count(), "waiting": qs.filter(status__in=["received", "under_review"]).count(), "by_status": _counts(window),
            "trend": _series(s.start, s.days, prescriptions=_daily(window))}


def finance_section(s: Scope):
    first = (s.today.replace(day=1) - timedelta(days=150)).replace(day=1)
    lines = s.b(JournalLine.objects.filter(entry__date__gte=first, account__type__in=["revenue", "income", "expense"]))
    months = {}
    for r in lines.annotate(m=TruncMonth("entry__date")).values("m", "account__type").annotate(d=Sum("debit"), c=Sum("credit")):
        row = months.setdefault(r["m"], {"revenue": ZERO, "expenses": ZERO})
        if r["account__type"] == "expense":
            row["expenses"] += (r["d"] or ZERO) - (r["c"] or ZERO)
        else:
            row["revenue"] += (r["c"] or ZERO) - (r["d"] or ZERO)
    spend = (s.b(JournalLine.objects.filter(entry__date__gte=s.start, account__type="expense")).values("account__name")
             .annotate(d=Sum("debit"), c=Sum("credit")))
    breakdown = sorted(({"label": r["account__name"], "value": (r["d"] or ZERO) - (r["c"] or ZERO)} for r in spend), key=lambda r: -r["value"])
    return {"monthly": [{"month": m.strftime("%b %Y"), **months[m]} for m in sorted(months)], "expense_breakdown": [r for r in breakdown if r["value"] > 0][:8]}


def customers_section(s: Scope):
    qs = User.objects.filter(tenant=s.user.tenant, role__code="customer")
    joined = {r["d"]: r["n"] for r in qs.filter(date_joined__date__gte=s.start).annotate(d=TruncDate("date_joined")).values("d").annotate(n=Count("id"))}
    top = (s.b(Order.objects.filter(status__in=PAID_ONLINE)).values("customer__full_name").annotate(t=Sum("total"), n=Count("id")).order_by("-t")[:5])
    return {"total": qs.count(), "new": sum(joined.values()), "verified": qs.filter(email_verified=True).count(),
            "trend": _series(s.start, s.days, customers=joined), "top": [{"label": r["customer__full_name"], "value": r["t"], "orders": r["n"]} for r in top]}


def procurement_section(s: Scope):
    qs = s.b(PurchaseOrder.objects.all())
    return {"by_status": _counts(qs), "ordered_value": _total(s.now(qs), "total"), "awaiting_approval": qs.filter(status__in=["submitted", "pending_approval"]).count()}


def people_section(s: Scope):
    staff = User.objects.filter(tenant=s.user.tenant, is_active=True).exclude(role__code="customer")
    attendance, leave = s.b(AttendanceRecord.objects.filter(date=s.today)), LeaveRequest.objects.filter(status="pending")
    if s.branch:
        staff, leave = staff.filter(branch_id=s.branch), leave.filter(user__branch_id=s.branch)
    return {"staff": staff.count(), "by_role": [{"label": r["role__name"], "value": r["n"]} for r in staff.values("role__name").annotate(n=Count("id")).order_by("-n")],
            "present_today": attendance.filter(clock_in__isnull=False).count(), "attendance_today": _counts(attendance), "pending_leave": leave.count()}


def engagement_section(s: Scope):
    appts, inquiries, feedback = s.b(Appointment.objects.all()), s.b(CustomerInquiry.objects.all()), s.b(Feedback.objects.all())
    ratings = {r["rating"]: r["n"] for r in feedback.values("rating").annotate(n=Count("id"))}
    return {"appointments": _counts(s.now(appts)), "open_inquiries": inquiries.exclude(status__in=["answered", "closed"]).count(),
            "average_rating": feedback.aggregate(a=Avg("rating"))["a"], "ratings": [{"label": f"{i} star", "value": ratings.get(i, 0)} for i in range(5, 0, -1)]}


def delivery_section(s: Scope, own_only: bool):
    qs = s.b(Delivery.objects.all(), "order__branch_id")
    if own_only:
        qs = qs.filter(driver=s.user)
    return {"own_only": own_only, "by_status": _counts(s.now(qs)), "active": qs.filter(status__in=["assigned", "picked_up"]).count()}


def build(user, days: int) -> dict:
    s = Scope(user, days)
    can = user.has_tenant_perm
    out = {"days": days, "from": s.start, "to": s.today, "scope": "branch" if s.branch else "pharmacy",
           "currency": (user.tenant.settings or {}).get("currency", "SLE")}
    if can("sales.view_branch") or can("report.view"):
        out["sales"] = sales_section(s, False)
    elif can("sales.view_own"):
        out["sales"] = sales_section(s, True)
    if can("order.manage"):
        out["orders"] = orders_section(s)
    if can("inventory.view"):
        out["inventory"] = inventory_section(s)
    if can("prescription.view"):
        out["prescriptions"] = prescriptions_section(s)
    if can("accounting.view"):
        out["finance"] = finance_section(s)
    if can("customer.view"):
        out["customers"] = customers_section(s)
    if can("procurement.view"):
        out["procurement"] = procurement_section(s)
    if can("hr.view"):
        out["people"] = people_section(s)
    if can("engagement.manage"):
        out["engagement"] = engagement_section(s)
    if can("delivery.manage"):
        out["delivery"] = delivery_section(s, False)
    elif can("delivery.perform"):
        out["delivery"] = delivery_section(s, True)
    return out


def platform(days: int) -> dict:
    """Platform administrators: tenant and billing health only. No pharmacy's clinical or customer records are read."""
    from apps.backups.models import BackupRecord
    from apps.billing.models import Invoice, Subscription
    from apps.notifications.models import EmailLog
    from apps.tenants.models import Pharmacy

    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    year = (today.replace(day=1) - timedelta(days=334)).replace(day=1)
    joined = {r["m"].date(): r["n"] for r in Pharmacy.objects.filter(created_at__date__gte=year).annotate(m=TruncMonth("created_at")).values("m").annotate(n=Count("id"))}
    paid = {r["m"].date(): r["t"] for r in Invoice.objects.filter(status="paid", paid_at__date__gte=year).annotate(m=TruncMonth("paid_at")).values("m").annotate(t=Sum("amount"))}
    months, m = [], year
    while m <= today:
        months.append({"month": m.strftime("%b %y"), "pharmacies": joined.get(m, 0), "revenue": paid.get(m, 0)})
        m = (m + timedelta(days=32)).replace(day=1)
    logins = LoginHistory.objects.filter(success=True, created_at__date__gte=start)
    top = (Pharmacy.objects.annotate(users_count=Count("users", distinct=True)).order_by("-users_count")[:8])
    last_backup = BackupRecord.objects.filter(status="completed").order_by("-pk").first()
    return {
        "days": days,
        "pharmacies": {"total": Pharmacy.objects.count(), "by_status": _counts(Pharmacy.objects.all()), "by_country": _counts(Pharmacy.objects.all(), "country")},
        "users": {"total": User.objects.filter(is_active=True).count(), "customers": User.objects.filter(role__code="customer").count(),
                  "staff": User.objects.filter(is_active=True, tenant__isnull=False).exclude(role__code="customer").count(),
                  "top_pharmacies": [{"label": p.name, "value": p.users_count} for p in top]},
        "monthly": months,
        "logins": _series(start, days, logins=_daily(logins)),
        "subscriptions": [{"label": r["plan__name"], "value": r["n"]} for r in Subscription.objects.values("plan__name").annotate(n=Count("id")).order_by("-n")],
        "invoices": [{"label": r["status"], "value": r["n"], "amount": r["t"]} for r in Invoice.objects.values("status").annotate(n=Count("id"), t=Sum("amount"))],
        "emails": _counts(EmailLog.objects.filter(created_at__date__gte=start)),
        "last_backup": None if not last_backup else {"number": last_backup.number, "created_at": last_backup.started_at, "verification": last_backup.verification},
    }
