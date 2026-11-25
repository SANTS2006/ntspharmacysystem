from rest_framework import serializers


class TenantPKField(serializers.PrimaryKeyRelatedField):
    """PK field whose queryset is resolved per request, so the tenant-scoped manager sees the active tenant
    (a class-level Model.objects.all() would be evaluated at import time with no tenant and match nothing)."""

    def __init__(self, model, **kwargs):
        self._model = model
        kwargs["queryset"] = model.all_objects.none()  # placeholder required by DRF; never used for lookup
        super().__init__(**kwargs)

    def get_queryset(self):
        return self._model.objects.all()

    def use_pk_only_optimization(self):
        return True
