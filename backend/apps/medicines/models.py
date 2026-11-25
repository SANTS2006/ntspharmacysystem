from django.db import models

from apps.core.models import TenantOwnedModel
from apps.tenants.models import validate_logo  # same image rules as logos (no SVG, size cap)

DEFAULT_CATEGORIES = [
    "Prescription medicines", "Over-the-counter medicines", "Antibiotics", "Analgesics", "Antimalarials",
    "Antihypertensives", "Antidiabetics", "Vitamins and supplements", "First aid products", "Medical equipment",
    "Medical consumables", "Personal care products", "Baby care products", "Healthcare products",
]


class Category(TenantOwnedModel):
    name = models.CharField(max_length=100)
    is_system = models.BooleanField(default=False)  # seeded defaults; custom categories are is_system=False

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "name"], name="uniq_category_name_per_tenant")]
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Medicine(TenantOwnedModel):
    class Classification(models.TextChoices):
        OTC = "otc", "Over the counter"
        PRESCRIPTION = "prescription", "Prescription only"
        CONTROLLED = "controlled", "Controlled medicine"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200, blank=True)
    brand_name = models.CharField(max_length=200, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="medicines")
    active_ingredient = models.CharField(max_length=200, blank=True)
    strength = models.CharField(max_length=60, blank=True)
    dosage_form = models.CharField(max_length=60, blank=True)
    route = models.CharField(max_length=60, blank=True)
    manufacturer = models.CharField(max_length=200, blank=True)
    country_of_manufacture = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="medicine-images/", blank=True, validators=[validate_logo])
    barcode = models.CharField(max_length=32, blank=True)
    sku = models.CharField(max_length=40, blank=True)
    registration_number = models.CharField(max_length=100, blank=True)
    classification = models.CharField(max_length=15, choices=Classification.choices, default=Classification.OTC)
    storage_requirements = models.CharField(max_length=255, blank=True)
    dosage_info = models.TextField(blank=True)
    side_effects = models.TextField(blank=True)
    contraindications = models.TextField(blank=True)
    unit = models.CharField(max_length=30, default="unit")
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    wholesale_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_category = models.CharField(max_length=30, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # percent
    reorder_level = models.PositiveIntegerField(default=0)
    has_expiry = models.BooleanField(default=True)  # False => FIFO instead of FEFO
    is_online_visible = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "sku"], condition=~models.Q(sku=""), name="uniq_medicine_sku_per_tenant"),
            models.UniqueConstraint(fields=["tenant", "barcode"], condition=~models.Q(barcode=""), name="uniq_medicine_barcode_per_tenant"),
            models.CheckConstraint(condition=models.Q(purchase_price__gte=0, selling_price__gte=0, wholesale_price__gte=0, tax_rate__gte=0, tax_rate__lte=100), name="medicine_prices_valid"),
        ]
        indexes = [models.Index(fields=["tenant", "name"]), models.Index(fields=["tenant", "status"]), models.Index(fields=["tenant", "category"])]
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def requires_prescription(self) -> bool:
        return self.classification != self.Classification.OTC
