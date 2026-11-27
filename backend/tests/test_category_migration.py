"""The upgrade must delete unused built-in categories and never orphan a medicine."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)


def migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return MigrationExecutor(connection).loader.project_state(target).apps


def test_only_unused_built_in_categories_are_deleted():
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        apps = migrate([("medicines", "0001_initial")])
        Pharmacy, Category, Medicine = apps.get_model("tenants", "Pharmacy"), apps.get_model("medicines", "Category"), apps.get_model("medicines", "Medicine")
        t = Pharmacy._base_manager.create(name="Old", slug="oldpharmacy")
        used = Category._base_manager.create(tenant=t, name="Antibiotics", is_system=True)
        Category._base_manager.create(tenant=t, name="Analgesics", is_system=True)
        Category._base_manager.create(tenant=t, name="Herbal", is_system=False)
        Medicine._base_manager.create(tenant=t, name="Amoxicillin", category=used)
        apps = migrate([("medicines", "0003_remove_category_is_system")])
        names = sorted(apps.get_model("medicines", "Category")._base_manager.values_list("name", flat=True))
        assert names == ["Antibiotics", "Herbal"]
    finally:
        migrate(leaves)
