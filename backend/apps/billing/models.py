from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class Plan(TimeStampedModel):
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    interval = models.CharField(max_length=10, choices=[("monthly", "Monthly"), ("yearly", "Yearly")], default="monthly")
    max_branches = models.PositiveIntegerField(default=1)
    max_users = models.PositiveIntegerField(default=10)
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Subscription(TimeStampedModel):
    class Status(models.TextChoices):
        TRIAL = "trial"
        ACTIVE = "active"
        PAST_DUE = "past_due"
        CANCELLED = "cancelled"

    pharmacy = models.OneToOneField("tenants.Pharmacy", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TRIAL, db_index=True)
    current_period_end = models.DateField(null=True, blank=True)


class Invoice(TimeStampedModel):
    """Financial record: amount/currency are fixed at issue. Only status/payment fields change, via services."""
    class Status(models.TextChoices):
        ISSUED = "issued"
        PAID = "paid"
        VOID = "void"
        REFUNDED = "refunded"

    number = models.CharField(max_length=30, unique=True)
    pharmacy = models.ForeignKey("tenants.Pharmacy", on_delete=models.PROTECT, related_name="invoices")
    plan = models.ForeignKey(Plan, null=True, on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED, db_index=True)
    due_date = models.DateField()
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=30, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    refunded_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    refunded_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="invoice_amount_positive"),
            models.CheckConstraint(condition=models.Q(refunded_amount__gte=0, refunded_amount__lte=models.F("amount")),
                                   name="invoice_refund_within_amount"),
            models.UniqueConstraint(fields=["payment_reference"], condition=~models.Q(payment_reference=""),
                                    name="uniq_invoice_payment_reference"),  # blocks duplicate payment records
        ]
