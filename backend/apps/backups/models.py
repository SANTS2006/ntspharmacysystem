from django.db import models


class BackupRecord(models.Model):
    """Platform-level (not tenant-owned) and EXCLUDED from backups/restores so history survives a restore."""
    class Status(models.TextChoices):
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"
        DELETED = "deleted"  # object removed by retention; the record stays as history

    number = models.CharField(max_length=40, unique=True)
    kind = models.CharField(max_length=12, default="manual")  # manual | scheduled | pre_restore
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING, db_index=True)
    method = models.CharField(max_length=20, default="logical-json")  # full logical dump; incremental backups are not supported by this strategy
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, blank=True)  # of the encrypted object
    object_key = models.CharField(max_length=300, blank=True)
    key_fingerprint = models.CharField(max_length=16, blank=True)  # identifies the encryption key used (never the key)
    object_counts = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=500, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verification = models.CharField(max_length=300, blank=True)
    retention_until = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["status"], condition=models.Q(status="running"), name="one_backup_running")]
        ordering = ["-started_at"]


class RestoreRequest(models.Model):
    """Two-person, time-limited, fully logged restore workflow."""
    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        EXECUTING = "executing"
        COMPLETED = "completed"
        FAILED = "failed"
        REJECTED = "rejected"
        EXPIRED = "expired"

    backup = models.ForeignKey(BackupRecord, on_delete=models.PROTECT, related_name="restores")
    reason = models.CharField(max_length=300)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    requested_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    approved_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    executed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    safety_backup = models.ForeignKey(BackupRecord, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    log = models.JSONField(default=list)  # ordered recovery log lines
    error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
