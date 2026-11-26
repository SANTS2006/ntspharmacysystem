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


class Notification(models.Model):
    """In-app notification for one user. Rows are private to their recipient: every query filters on `user`."""
    class Level(models.TextChoices):
        INFO = "info"
        SUCCESS = "success"
        WARNING = "warning"
        DANGER = "danger"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notifications")
    tenant = models.ForeignKey("tenants.Pharmacy", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=40, db_index=True)  # e.g. order, payment, inventory, security
    level = models.CharField(max_length=8, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=1000, blank=True)
    link = models.CharField(max_length=200, blank=True)  # path inside the recipient's own portal, e.g. "/orders/12"
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "read_at", "-created_at"])]
