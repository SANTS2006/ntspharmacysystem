from django.db import models

from apps.core.models import TimeStampedModel


class SitePage(TimeStampedModel):
    """Editable content of one public page. tenant=None is the platform's own website. Not auto-scoped (tenant may be null):
    every query filters on `tenant` explicitly."""
    tenant = models.ForeignKey("tenants.Pharmacy", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    key = models.CharField(max_length=40)
    content = models.JSONField(default=dict)
    updated_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], condition=models.Q(tenant__isnull=False), name="uniq_site_page_per_tenant"),
            models.UniqueConstraint(fields=["key"], condition=models.Q(tenant__isnull=True), name="uniq_platform_site_page"),
        ]


class ContactMessage(TimeStampedModel):
    """A contact-form submission. tenant=None came from the platform website."""
    class Status(models.TextChoices):
        NEW = "new"
        IN_PROGRESS = "in_progress"
        RESOLVED = "resolved"

    tenant = models.ForeignKey("tenants.Pharmacy", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=200)
    message = models.CharField(max_length=3000)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    staff_note = models.CharField(max_length=1000, blank=True)
    reply = models.CharField(max_length=3000, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["tenant", "status", "-created_at"])]
