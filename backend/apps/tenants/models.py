from django.core.validators import RegexValidator
from django.db import models

from apps.core.models import TenantOwnedModel, TimeStampedModel

RESERVED_SLUGS = {"www", "api", "app", "admin", "platform", "static", "media", "pharmacy", "login", "support", "mail", "ftp", "smtp", "dashboard", "help", "docs", "blog", "ntspharmacy"}
def validate_logo(f):
    from django.core.exceptions import ValidationError
    from django.conf import settings
    if f.size > settings.LOGO_MAX_BYTES:
        raise ValidationError("Logo must be 2 MB or smaller.")
    if not f.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        raise ValidationError("Logo must be PNG, JPG or WebP.")  # SVG excluded: can carry scripts


hex_color = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Enter a color like #1A7F5A.")
slug_validator = RegexValidator(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$", "Use 3-63 lowercase letters, numbers, hyphens.")


class Pharmacy(TimeStampedModel):
    """The tenant. Everything tenant-owned references this row."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DEACTIVATED = "deactivated", "Deactivated"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=63, unique=True, validators=[slug_validator])
    custom_domain = models.CharField(max_length=253, unique=True, null=True, blank=True)  # future custom domains
    logo = models.ImageField(upload_to="tenant-logos/", blank=True, validators=[validate_logo])
    description = models.TextField(blank=True)
    registration_number = models.CharField(max_length=100, blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    license_expiry = models.DateField(null=True, blank=True)
    address = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=100, default="Sierra Leone")
    region = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    primary_color = models.CharField(max_length=7, default="#015dc9", validators=[hex_color])
    secondary_color = models.CharField(max_length=7, default="#25bcfb", validators=[hex_color])
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    website_config = models.JSONField(default=dict, blank=True)
    settings = models.JSONField(default=dict, blank=True)  # per-tenant config incl. compliance toggles
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    status_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name_plural = "pharmacies"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_active_tenant(self) -> bool:
        return self.status == self.Status.ACTIVE


class Branch(TenantOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    manager = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    operating_hours = models.JSONField(default=dict, blank=True)
    qr_token = models.CharField(max_length=40, null=True, blank=True, unique=True)  # unguessable token for the branch QR menu
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="uniq_branch_code_per_tenant")]
        indexes = [models.Index(fields=["tenant", "status"])]
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"
