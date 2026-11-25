from .models import DEFAULT_CATEGORIES, Category


def seed_default_categories():
    """Call inside tenant_context(pharmacy)."""
    for name in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(name=name, defaults={"is_system": True})
