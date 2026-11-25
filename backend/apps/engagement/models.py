from django.db import models

from apps.core.models import TenantOwnedModel
from apps.tenants.models import validate_logo


class PharmacyService(TenantOwnedModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="service-images/", blank=True, validators=[validate_logo])
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)  # null = ask the pharmacy
    is_available = models.BooleanField(default=True)
    requires_booking = models.BooleanField(default=False)
    duration_minutes = models.PositiveIntegerField(default=30)
    capacity = models.PositiveIntegerField(default=1)  # simultaneous bookings per slot
    branches = models.ManyToManyField("tenants.Branch", blank=True, related_name="+")  # empty = every branch

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "name"], name="uniq_service_name")]
        ordering = ["name"]


class Appointment(TenantOwnedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested"
        CONFIRMED = "confirmed"
        COMPLETED = "completed"
        CANCELLED = "cancelled"
        NO_SHOW = "no_show"

    customer = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="appointments")
    service = models.ForeignKey(PharmacyService, on_delete=models.PROTECT, related_name="appointments")
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT, related_name="+")
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    customer_note = models.CharField(max_length=300, blank=True)
    staff_note = models.CharField(max_length=300, blank=True)
    handled_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        indexes = [models.Index(fields=["tenant", "branch", "start_at"])]
        ordering = ["start_at"]


class CustomerInquiry(TenantOwnedModel):
    class Kind(models.TextChoices):
        INQUIRY = "inquiry"
        HOME_DELIVERY = "home_delivery"
        AVAILABILITY = "availability"

    customer = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="inquiries")
    branch = models.ForeignKey("tenants.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=14, choices=Kind.choices, default=Kind.INQUIRY)
    message = models.CharField(max_length=1000)
    status = models.CharField(max_length=10, default="new", db_index=True)  # new | answered | closed
    response = models.CharField(max_length=1000, blank=True)
    handled_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-created_at"]


class InstitutionalRequest(TenantOwnedModel):
    """Bulk supply / service quotation request from an organisation (public, no account needed)."""
    organisation = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    service_required = models.CharField(max_length=200)
    products_required = models.CharField(max_length=1000, blank=True)
    quantity = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=200, blank=True)
    requested_date = models.DateField(null=True, blank=True)
    details = models.CharField(max_length=1500, blank=True)
    branch = models.ForeignKey("tenants.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=10, default="new", db_index=True)  # new | reviewing | quoted | closed
    response = models.CharField(max_length=2000, blank=True)
    handled_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-created_at"]


class Feedback(TenantOwnedModel):
    customer = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="feedback")
    order = models.ForeignKey("shop.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    branch = models.ForeignKey("tenants.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    rating = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=1500, blank=True)
    status = models.CharField(max_length=10, default="new")  # new | reviewed
    response = models.CharField(max_length=1000, blank=True)
    handled_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="feedback_rating_1_5")]
        ordering = ["-created_at"]
