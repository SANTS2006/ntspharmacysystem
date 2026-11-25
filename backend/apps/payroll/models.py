from decimal import Decimal

from django.db import models

from apps.core.models import TenantOwnedModel

ZERO = Decimal("0.00")


class SalaryComponent(TenantOwnedModel):
    class Kind(models.TextChoices):
        EARNING = "earning"
        DEDUCTION = "deduction"

    class Calc(models.TextChoices):
        FIXED = "fixed"
        PERCENT_BASIC = "percent_basic"

    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    calc = models.CharField(max_length=15, choices=Calc.choices, default=Calc.FIXED)
    taxable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "name"], name="uniq_salary_component")]


class SalaryStructure(TenantOwnedModel):
    """Versioned and immutable: a raise creates a new row; history is never rewritten. Highly confidential."""
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="salary_structures")
    basic_salary = models.DecimalField(max_digits=14, decimal_places=2)
    effective_from = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "user", "effective_from"], name="uniq_structure_version"),
                       models.CheckConstraint(condition=models.Q(basic_salary__gte=0), name="basic_nonnegative")]
        ordering = ["-effective_from"]


class SalaryStructureItem(TenantOwnedModel):
    structure = models.ForeignKey(SalaryStructure, on_delete=models.CASCADE, related_name="items")
    component = models.ForeignKey(SalaryComponent, on_delete=models.PROTECT, related_name="+")
    value = models.DecimalField(max_digits=14, decimal_places=2)  # amount, or percent of basic for percent components


class PayrollAdjustment(TenantOwnedModel):
    class Kind(models.TextChoices):
        BONUS = "bonus"
        COMMISSION = "commission"
        OVERTIME = "overtime"
        DEDUCTION = "deduction"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="payroll_adjustments")
    period = models.CharField(max_length=7)  # YYYY-MM
    kind = models.CharField(max_length=12, choices=Kind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    taxable = models.BooleanField(default=True)
    note = models.CharField(max_length=200)
    applied_run = models.ForeignKey("PayrollRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="adjustments")
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="adjustment_positive")]


class SalaryAdvance(TenantOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active"
        CLEARED = "cleared"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="salary_advances")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    monthly_recovery = models.DecimalField(max_digits=14, decimal_places=2)
    balance = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    method = models.CharField(max_length=20)
    reference = models.CharField(max_length=100)
    approved_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0, monthly_recovery__gt=0, balance__gte=0), name="advance_valid"),
                       models.UniqueConstraint(fields=["tenant", "reference"], name="uniq_advance_reference")]


class PayrollRun(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        SUBMITTED = "submitted"
        APPROVED = "approved"
        PAID = "paid"
        CANCELLED = "cancelled"

    period = models.CharField(max_length=7)  # YYYY-MM
    branch = models.ForeignKey("tenants.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+")  # null = whole pharmacy
    scope_key = models.CharField(max_length=20)  # "all" or the branch id, so (period, scope) is unique among live runs
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    approved_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "period", "scope_key"], condition=~models.Q(status="cancelled"), name="uniq_live_run_per_period")]
        ordering = ["-period", "-id"]


class PayrollLine(TenantOwnedModel):
    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="lines")
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="payroll_lines")
    branch = models.ForeignKey("tenants.Branch", null=True, on_delete=models.SET_NULL, related_name="+")
    basic = models.DecimalField(max_digits=14, decimal_places=2)
    allowances = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    extras = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)  # bonuses, commissions, overtime
    gross = models.DecimalField(max_digits=14, decimal_places=2)
    taxable_income = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    tax = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    pension_employee = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    pension_employer = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    other_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    advance_recovery = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    net = models.DecimalField(max_digits=14, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    details = models.JSONField(default=dict)  # itemised earnings/deductions for the salary slip
    warnings = models.JSONField(default=list)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["run", "user"], name="one_line_per_user_per_run"),
                       models.CheckConstraint(condition=models.Q(net__gte=0, paid_amount__gte=0, paid_amount__lte=models.F("net")), name="payroll_line_amounts_valid")]


class SalaryPayment(TenantOwnedModel):
    line = models.ForeignKey(PayrollLine, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=20)
    reference = models.CharField(max_length=100)
    paid_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="salary_payment_positive"),
                       models.UniqueConstraint(fields=["tenant", "reference"], name="uniq_salary_payment_reference")]
