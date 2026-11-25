from datetime import timedelta
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce

from apps.medicines.models import Medicine

from .models import Batch
from .services import saleable_q, today


def branch_ids_for(user):
    """None = all branches; otherwise the single branch a branch-scoped user may see."""
    return [user.branch_id] if user.is_branch_scoped else None


def scoped_batches(user):
    qs = Batch.objects.select_related("medicine", "branch")
    ids = branch_ids_for(user)
    return qs.filter(branch_id__in=ids) if ids else qs


def medicines_with_stock(user, branch_id=None):
    """Saleable stock is DERIVED from batches (never a stored counter that could drift)."""
    q = Q(batches__status="available", batches__quantity_available__gt=0) & (Q(batches__expiry_date__isnull=True) | Q(batches__expiry_date__gte=today()))
    ids = branch_ids_for(user)
    if ids:
        q &= Q(batches__branch_id__in=ids)
    if branch_id:
        q &= Q(batches__branch_id=branch_id)
    return Medicine.objects.select_related("category").annotate(stock=Coalesce(Sum("batches__quantity_available", filter=q), 0))


def alerts(user, near_expiry_days=90):
    stock = medicines_with_stock(user).filter(status="active")
    batches = scoped_batches(user).filter(quantity_available__gt=0)
    horizon = today() + timedelta(days=near_expiry_days)
    return {
        "low_stock": stock.filter(stock__gt=0, stock__lte=F("reorder_level")),
        "out_of_stock": stock.filter(stock=0),
        "near_expiry": batches.filter(saleable_q(), expiry_date__lte=horizon).order_by("expiry_date"),
        "expired": batches.filter(expiry_date__lt=today()).order_by("expiry_date"),
    }


def valuation(user):
    value = ExpressionWrapper(F("quantity_available") * F("purchase_cost"), output_field=DecimalField(max_digits=16, decimal_places=2))
    qs = scoped_batches(user).filter(quantity_available__gt=0)
    total = lambda f: qs.filter(f).aggregate(t=Sum(value))["t"] or Decimal("0")  # noqa: E731
    return {"saleable_value": total(saleable_q()), "unsaleable_value": total(~saleable_q())}
