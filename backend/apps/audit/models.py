from django.db import models


class AuditLog(models.Model):
    """Append-only. Updates and deletes are blocked at the ORM level (and should also be revoked at DB level)."""
    tenant = models.ForeignKey("tenants.Pharmacy", null=True, on_delete=models.PROTECT, related_name="+", db_index=True)
    branch_id = models.BigIntegerField(null=True, blank=True)
    actor = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=80, db_index=True)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["tenant", "-created_at"])]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Audit log entries are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit log entries cannot be deleted.")

