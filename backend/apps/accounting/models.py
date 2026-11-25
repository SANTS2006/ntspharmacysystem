from decimal import Decimal

from django.db import models

from apps.core.models import TenantOwnedModel

ZERO = Decimal("0.00")


class Account(TenantOwnedModel):
    class Type(models.TextChoices):
        ASSET = "asset"
        LIABILITY = "liability"
        EQUITY = "equity"
        REVENUE = "revenue"
        EXPENSE = "expense"

    code = models.CharField(max_length=10)
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=10, choices=Type.choices)
    is_system = models.BooleanField(default=False)  # seeded accounts are referenced by automatic postings and cannot be deactivated
    is_active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="uniq_account_code")]
        ordering = ["code"]

    @property
    def debit_normal(self) -> bool:
        return self.type in (self.Type.ASSET, self.Type.EXPENSE)


class JournalEntry(TenantOwnedModel):
    """Posted entries are IMMUTABLE. Mistakes are corrected with a reversal entry, never by editing."""
    number = models.CharField(max_length=30)
    date = models.DateField(db_index=True)
    description = models.CharField(max_length=300)
    source_type = models.CharField(max_length=30)  # sale | sale_return | grn | supplier_payment | order_payment | expense | manual | reversal ...
    source_id = models.CharField(max_length=60, blank=True)
    total = models.DecimalField(max_digits=16, decimal_places=2)  # sum of debits (= sum of credits)
    reverses = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by")
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_journal_number"),
            models.UniqueConstraint(fields=["tenant", "source_type", "source_id"], condition=~models.Q(source_id=""), name="uniq_journal_source"),  # a business event posts once
        ]
        indexes = [models.Index(fields=["tenant", "date"])]
        ordering = ["-date", "-id"]

    def save(self, *a, **k):
        if self.pk is not None:
            raise PermissionError("Posted journal entries are immutable.")
        super().save(*a, **k)

    def delete(self, *a, **k):
        raise PermissionError("Posted journal entries cannot be deleted.")


class JournalLine(TenantOwnedModel):
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    branch = models.ForeignKey("tenants.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    debit = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO)
    credit = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO)
    memo = models.CharField(max_length=200, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(
            condition=(models.Q(debit__gt=0, credit=0) | models.Q(credit__gt=0, debit=0)), name="journal_line_one_sided_positive")]
        indexes = [models.Index(fields=["tenant", "account"]), models.Index(fields=["tenant", "branch"])]

    def save(self, *a, **k):
        if self.pk is not None:
            raise PermissionError("Journal lines are immutable.")
        super().save(*a, **k)

    def delete(self, *a, **k):
        raise PermissionError("Journal lines cannot be deleted.")


class DailyClose(TenantOwnedModel):
    """Closing a date locks it: nothing can be posted into a closed date (corrections are reversals dated in an open period)."""
    date = models.DateField()
    closed_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    summary = models.JSONField(default=dict)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "date"], name="uniq_daily_close")]
        ordering = ["-date"]


class Expense(TenantOwnedModel):
    class Status(models.TextChoices):
        POSTED = "posted"
        REVERSED = "reversed"

    date = models.DateField()
    branch = models.ForeignKey("tenants.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")  # expense category
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=15)  # cash | bank | mobile_money
    vendor = models.CharField(max_length=150, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=300)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    journal_entry = models.OneToOneField(JournalEntry, null=True, on_delete=models.PROTECT, related_name="expense")
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="expense_positive")]
        ordering = ["-date", "-id"]
