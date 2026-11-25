from datetime import timedelta

from celery import shared_task
from django.db.models import Sum
from django.db.models.functions import Coalesce

from apps.accounts.models import User
from apps.core.tenant_context import tenant_context, unscoped
from apps.medicines.models import Medicine
from apps.notifications.services import send_email
from apps.tenants.models import Branch, Pharmacy

from . import services
from .models import Batch


def stock_alert_summary(branch):
    days = int((branch.tenant.settings or {}).get("expiry_alert_days", 90))
    saleable = services.saleable_q()
    low = []
    for m in Medicine.objects.filter(status="active", reorder_level__gt=0):
        left = Batch.objects.filter(medicine=m, branch=branch).filter(saleable).aggregate(t=Coalesce(Sum("quantity_available"), 0))["t"]
        if left <= m.reorder_level:
            low.append(f"{m.name}: {left} left (reorder at {m.reorder_level})")
    horizon = services.today() + timedelta(days=days)
    near = [f"{b.medicine.name} batch {b.batch_number}: {b.quantity_available} expire {b.expiry_date}"
            for b in Batch.objects.filter(branch=branch).filter(saleable, expiry_date__lte=horizon).select_related("medicine")]
    expired = [f"{b.medicine.name} batch {b.batch_number}: {b.quantity_available} expired {b.expiry_date}"
               for b in Batch.objects.filter(branch=branch, quantity_available__gt=0, expiry_date__lt=services.today()).select_related("medicine")]
    return low, near, expired


@shared_task
def send_stock_alerts() -> int:
    """Daily email to each branch manager and the pharmacy admins: low stock, near-expiry and expired stock. Returns emails queued."""
    sent = 0
    with unscoped():
        tenants = list(Pharmacy.objects.filter(status="active"))
    for t in tenants:
        with tenant_context(t):
            admins = list(User.objects.filter(tenant=t, is_active=True, role__code="pharmacy_admin"))
            for branch in Branch.objects.filter(status="active").select_related("tenant"):
                low, near, expired = stock_alert_summary(branch)
                if not (low or near or expired):
                    continue
                managers = list(User.objects.filter(tenant=t, is_active=True, role__code="branch_manager", branch=branch))
                text = "\n".join([f"Stock alerts for {t.name} / {branch.name}", "", "LOW STOCK", *low, "", "NEAR EXPIRY", *near, "", "EXPIRED (not sellable)", *expired])
                for u in {x.pk: x for x in admins + managers}.values():
                    send_email(to=u.email, subject=f"Stock alerts: {branch.name}", text=text, tenant=t, template="stock_alert")
                    sent += 1
    return sent
