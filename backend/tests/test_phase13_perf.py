import pytest

from apps.medicines.models import Category, Medicine
from apps.core.tenant_context import tenant_context

from .test_foundation import api, login, platform_admin, platform_client, register, settled_token, two_pharmacies  # noqa: F401
from .test_phase7 import cash, env, open_shift, sell, stock  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def test_list_endpoints_do_not_grow_queries_with_row_count(env, django_assert_max_num_queries):
    """Guards against N+1 regressions: query counts for list pages must stay flat as data grows."""
    with tenant_context(env["g"]):
        cat = Category.objects.get(name="Antibiotics")
        meds = [Medicine.objects.create(name=f"Med {i}", category=cat, purchase_price=1, selling_price=2) for i in range(25)]
    for m in meds[:12]:
        stock(env, m, 20, f"B{m.pk}")
    open_shift(env["c1"])
    for m in meds[:6]:
        sell(env["c1"], [{"medicine": m.pk, "quantity": 1}], [cash(5)])
    for client, url, limit in ((env["admin"], "/api/v1/medicines/", 12), (env["admin"], "/api/v1/batches/", 12), (env["admin"], "/api/v1/sales/", 14), (env["admin"], "/api/v1/inventory/overview/", 12),
                               (env["admin"], "/api/v1/inventory/movements/", 12), (env["c1"], "/api/v1/sales/", 14), (env["admin"], "/api/v1/reports/sales-by-product/", 40)):
        with django_assert_max_num_queries(limit):
            assert client.get(url).status_code == 200, url
    # more rows, same bound
    with tenant_context(env["g"]):
        more = [Medicine.objects.create(name=f"Extra {i}", category=cat, purchase_price=1, selling_price=2) for i in range(20)]
    for m in more:
        stock(env, m, 5, f"E{m.pk}")
    with django_assert_max_num_queries(12):
        assert env["admin"].get("/api/v1/medicines/").status_code == 200
    with django_assert_max_num_queries(12):
        assert env["admin"].get("/api/v1/batches/").status_code == 200
