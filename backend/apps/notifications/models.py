from django.db import models


class EmailLog(models.Model):
    """Every transactional email attempt. Body is intentionally NOT stored (may contain credentials/PHI)."""
    class Status(models.TextChoices):
        QUEUED = "queued"
        SENT = "sent"
        FAILED = "failed"

    tenant = models.ForeignKey("tenants.Pharmacy", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    to_email = models.EmailField()
    subject = models.CharField(max_length=255)
    template = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    provider = models.CharField(max_length=20, blank=True)
    provider_message_id = models.CharField(max_length=120, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
