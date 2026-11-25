"""Logical database backups: Django dump -> gzip -> Fernet encryption -> object store. Verified after every run, retained by policy,
restored only through a two-person, re-authenticated, logged workflow. Media files are NOT in these backups (they live in their own bucket)."""
import base64
import gzip
import hashlib
import io
import json
import logging
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation
from apps.core.tenant_context import unscoped
from apps.notifications.services import send_email

from .models import BackupRecord, RestoreRequest
from .storage import get_store

log = logging.getLogger(__name__)
# Excluded from dumps AND from the restore wipe: backup history/restore workflow must survive a restore; sessions, token blacklist and
# content types are environment-specific and regenerated.
EXCLUDED = ["backups", "contenttypes", "sessions", "token_blacklist", "admin"]
MAINTENANCE_KEY = "maintenance_mode"


# ---------------- encryption ----------------
def _fernet() -> Fernet:
    key = settings.BACKUP_ENCRYPTION_KEY
    if not key:
        if not settings.DEBUG and not getattr(settings, "BACKUP_DEV_KEY_OK", False):
            raise ImproperlyConfigured("BACKUP_ENCRYPTION_KEY must be set (a Fernet key kept OUTSIDE the database and the backup bucket).")
        key = base64.urlsafe_b64encode(hashlib.sha256(("backup:" + settings.SECRET_KEY).encode()).digest()).decode()  # development only
    return Fernet(key.encode())


def key_fingerprint() -> str:
    key = settings.BACKUP_ENCRYPTION_KEY or "dev"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


# ---------------- dump / load ----------------
def dump_json() -> bytes:
    buf = io.StringIO()
    with unscoped():  # tenant-scoped managers would otherwise return nothing
        call_command("dumpdata", exclude=EXCLUDED, use_base_manager=True, stdout=buf, verbosity=0)
    return buf.getvalue().encode("utf-8")


def count_objects(raw_json: bytes) -> dict:
    counts: dict = {}
    for o in json.loads(raw_json):
        counts[o["model"]] = counts.get(o["model"], 0) + 1
    return counts


def _number() -> str:
    return f"BK-{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _admins():
    return list(User.objects.filter(is_platform_admin=True, is_active=True))


def notify_failure(subject: str, detail: str) -> None:
    for a in _admins():
        send_email(to=a.email, subject=subject, text=f"{detail}\n\nSign in to the platform dashboard to review backups.", template="backup_alert")


# ---------------- backup ----------------
def run_backup(*, kind="manual", user=None, request=None) -> BackupRecord:
    store = get_store()  # fails fast if R2 is misconfigured
    fernet = _fernet()
    try:
        rec = BackupRecord.objects.create(number=_number(), kind=kind, created_by=user if getattr(user, "pk", None) else None, key_fingerprint=key_fingerprint())
    except IntegrityError:
        raise BusinessRuleViolation("A backup is already running.")
    try:
        raw = dump_json()
        counts = count_objects(raw)
        blob = fernet.encrypt(gzip.compress(raw, 6))
        if len(blob) > settings.BACKUP_MAX_BYTES:
            raise ValueError(f"Backup exceeds BACKUP_MAX_BYTES ({len(blob)} bytes). Use pg_dump based backups for databases of this size.")
        key = f"{settings.BACKUP_PREFIX}/{timezone.now():%Y/%m}/{rec.number}.bak.enc"
        store.put(key, blob)
        rec.object_key, rec.size_bytes, rec.checksum_sha256, rec.object_counts = key, len(blob), hashlib.sha256(blob).hexdigest(), counts
        rec.retention_until = timezone.localdate() + timedelta(days=settings.BACKUP_RETENTION_DAYS)
        rec.status, rec.finished_at = BackupRecord.Status.COMPLETED, timezone.now()
        rec.save()
    except Exception as exc:  # recorded, alerted, never silent
        log.exception("Backup %s failed", rec.number)
        rec.status, rec.finished_at, rec.error = BackupRecord.Status.FAILED, timezone.now(), f"{type(exc).__name__}: {exc}"[:500]
        rec.save()
        audit.record("backup.failed", actor=user, request=request, backup=rec.number, error=rec.error)
        notify_failure(f"Backup failed: {rec.number}", f"The {kind} backup {rec.number} failed: {rec.error}")
        return rec
    audit.record("backup.created", actor=user, request=request, backup=rec.number, kind=kind, size=rec.size_bytes)
    verify_backup(rec.pk, user=user)  # an unverified backup is not a backup
    rec.refresh_from_db()
    return rec


# ---------------- verification ----------------
def _decrypt_to_json(rec: BackupRecord) -> bytes:
    store = get_store()
    blob = store.get(rec.object_key)
    if hashlib.sha256(blob).hexdigest() != rec.checksum_sha256:
        raise ValueError("Checksum mismatch: the stored object differs from what was written.")
    if rec.key_fingerprint and rec.key_fingerprint != key_fingerprint():
        raise ValueError("This backup was encrypted with a different key than the one configured.")
    try:
        return gzip.decompress(_fernet().decrypt(blob))
    except InvalidToken:
        raise ValueError("The backup cannot be decrypted (wrong key or corrupted data).")


def verify_backup(pk, *, user=None) -> BackupRecord:
    rec = BackupRecord.objects.get(pk=pk)
    if rec.status != BackupRecord.Status.COMPLETED:
        raise BusinessRuleViolation("Only completed backups can be verified.")
    try:
        raw = _decrypt_to_json(rec)
        n = sum(1 for _ in serializers.deserialize("json", raw, ignorenonexistent=False))  # every record must deserialize into a known model/field
        counts = count_objects(raw)
        if counts != rec.object_counts:
            raise ValueError("Record counts differ from those taken at backup time.")
        rec.verification, ok = f"OK: {n} objects across {len(counts)} models", True
    except Exception as exc:
        rec.verification, ok = f"FAILED: {type(exc).__name__}: {exc}"[:300], False
    rec.verified_at = timezone.now()
    rec.save(update_fields=["verified_at", "verification"])
    audit.record("backup.verified" if ok else "backup.verification_failed", actor=user, backup=rec.number, result=rec.verification)
    if not ok:
        notify_failure(f"Backup verification failed: {rec.number}", rec.verification)
    return rec


def read_encrypted(rec: BackupRecord) -> bytes:
    if rec.status != BackupRecord.Status.COMPLETED:
        raise BusinessRuleViolation("This backup is not available.")
    return get_store().get(rec.object_key)


# ---------------- retention ----------------
def purge_expired(*, today=None) -> int:
    """Delete objects past retention but ALWAYS keep the newest verified backups (BACKUP_MIN_KEEP) so retention can never leave nothing."""
    today = today or timezone.localdate()
    keep = set(BackupRecord.objects.filter(status="completed", verification__startswith="OK").order_by("-started_at").values_list("pk", flat=True)[:settings.BACKUP_MIN_KEEP])
    store, n = get_store(), 0
    for rec in BackupRecord.objects.filter(status="completed", retention_until__lt=today).exclude(pk__in=keep):
        if RestoreRequest.objects.filter(backup=rec, status__in=["pending", "approved", "executing"]).exists():
            continue
        store.delete(rec.object_key)
        rec.status = BackupRecord.Status.DELETED
        rec.save(update_fields=["status"])
        audit.record("backup.purged", actor=None, backup=rec.number)
        n += 1
    return n


# ---------------- health ----------------
def health() -> dict:
    last = BackupRecord.objects.filter(status="completed", verification__startswith="OK").order_by("-started_at").first()
    age_h = round((timezone.now() - last.started_at).total_seconds() / 3600, 1) if last else None
    rpo = settings.BACKUP_SCHEDULE_HOURS
    return {"storage": settings.BACKUP_STORAGE, "restore_enabled": settings.BACKUP_ALLOW_RESTORE, "last_verified_backup": last.number if last else None, "last_backup_age_hours": age_h,
            "rpo_target_hours": rpo, "rpo_breached": age_h is None or age_h > rpo * 1.5, "retention_days": settings.BACKUP_RETENTION_DAYS,
            "encryption_key_configured": bool(settings.BACKUP_ENCRYPTION_KEY), "recent_failures": BackupRecord.objects.filter(status="failed", started_at__gte=timezone.now() - timedelta(days=7)).count()}


# ======================= restore =======================
def _reauth(user, password):
    if not password or not user.check_password(password):
        raise PermissionDenied("Password confirmation failed.")


def phrase(req: RestoreRequest) -> str:
    return f"RESTORE {req.backup.number}"


@transaction.atomic
def request_restore(*, user, backup_id, reason, password) -> RestoreRequest:
    _reauth(user, password)
    if not settings.BACKUP_ALLOW_RESTORE:
        raise BusinessRuleViolation("Restore is disabled on this deployment (BACKUP_ALLOW_RESTORE).")
    rec = BackupRecord.objects.get(pk=backup_id)
    if rec.status != "completed" or not rec.verification.startswith("OK"):
        raise BusinessRuleViolation("Only completed, verified backups can be restored.")
    if len(reason.strip()) < 10:
        raise ValidationError({"reason": "Describe why this restore is needed (at least 10 characters)."})
    if RestoreRequest.objects.filter(status__in=["pending", "approved", "executing"]).exists():
        raise BusinessRuleViolation("Another restore request is already open.")
    req = RestoreRequest.objects.create(backup=rec, reason=reason[:300], requested_by=user, expires_at=timezone.now() + timedelta(minutes=settings.RESTORE_APPROVAL_MINUTES))
    _log(req, f"Restore of {rec.number} requested by {user.email}")
    audit.record("restore.requested", actor=user, backup=rec.number, request_id=req.pk, reason=reason)
    for a in _admins():
        if a.pk != user.pk:
            send_email(to=a.email, subject="Restore approval needed", text=f"{user.email} requested a database restore from {rec.number}. Review it in the platform dashboard; it expires in {settings.RESTORE_APPROVAL_MINUTES} minutes.", template="restore_request")
    return req


def _log(req: RestoreRequest, line: str):
    req.log = [*req.log, f"{timezone.now():%Y-%m-%d %H:%M:%S} {line}"]
    req.save(update_fields=["log"])


def _fresh(req: RestoreRequest) -> RestoreRequest:
    if req.status in ("pending", "approved") and req.expires_at < timezone.now():
        req.status = RestoreRequest.Status.EXPIRED
        req.save(update_fields=["status"])
    return req


@transaction.atomic
def approve_restore(pk, *, user, password, approve=True) -> RestoreRequest:
    _reauth(user, password)
    req = _fresh(RestoreRequest.objects.select_for_update(of=("self",)).get(pk=pk))
    if req.status != "pending":
        raise BusinessRuleViolation(f"This request is {req.status}.")
    if req.requested_by_id == user.pk:
        raise PermissionDenied("A restore must be approved by a different platform administrator.")
    req.status = RestoreRequest.Status.APPROVED if approve else RestoreRequest.Status.REJECTED
    req.approved_by = user
    req.save()
    _log(req, f"{'Approved' if approve else 'Rejected'} by {user.email}")
    audit.record("restore.approved" if approve else "restore.rejected", actor=user, request_id=req.pk, backup=req.backup.number)
    return req


def _wipe(using="default"):
    """Remove every row of every restorable table with raw DELETEs (FK checks are deferred to commit, exactly like Django's flush)."""
    for model in apps.get_models(include_auto_created=True):
        if model._meta.app_label in EXCLUDED or not model._meta.managed:
            continue
        model._base_manager.using(using).all()._raw_delete(using)


def execute_restore(pk, *, user, password, confirmation) -> RestoreRequest:
    """Runs synchronously (call from a worker). Order: authorise -> verify -> safety backup -> maintenance on -> wipe+load in ONE transaction -> revoke sessions."""
    _reauth(user, password)
    with transaction.atomic():
        req = _fresh(RestoreRequest.objects.select_for_update(of=("self",)).select_related("backup").get(pk=pk))
        if req.status != "approved":
            raise BusinessRuleViolation(f"This request is {req.status}; it must be approved first.")
        if not settings.BACKUP_ALLOW_RESTORE:
            raise BusinessRuleViolation("Restore is disabled on this deployment (BACKUP_ALLOW_RESTORE).")
        if confirmation != phrase(req):
            raise ValidationError({"confirmation": f"Type exactly: {phrase(req)}"})
        if user.pk not in (req.requested_by_id, req.approved_by_id):
            raise PermissionDenied("Only the requester or the approver may execute this restore.")
        req.status, req.executed_by, req.started_at = RestoreRequest.Status.EXECUTING, user, timezone.now()
        req.save()
    audit.record("restore.started", actor=user, request_id=req.pk, backup=req.backup.number)
    try:
        _log(req, "Verifying backup")
        verify = verify_backup(req.backup_id, user=user)
        if not verify.verification.startswith("OK"):
            raise ValueError("The backup failed verification: " + verify.verification)
        _log(req, "Taking a safety backup of the current database")
        safety = run_backup(kind="pre_restore", user=user)
        if safety.status != "completed" or not safety.verification.startswith("OK"):
            raise ValueError("The safety backup failed; the restore was NOT started. " + (safety.error or safety.verification))
        req.safety_backup = safety
        req.save(update_fields=["safety_backup"])
        raw = _decrypt_to_json(req.backup)
        cache.set(MAINTENANCE_KEY, True, timeout=3600)
        _log(req, "Maintenance mode on; replacing database contents in one transaction")
        import os
        import tempfile
        with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as fh:
            fh.write(raw)
            path = fh.name
        try:
            with transaction.atomic():
                _wipe()
                call_command("loaddata", path, verbosity=0)  # constraint checks run at commit: any inconsistency rolls EVERYTHING back
                User.objects.update(credential_version=F("credential_version") + 1)  # every session issued before/after the backup is now dead
        finally:
            os.unlink(path)
        _log(req, "Database restored; all sessions revoked")
        req.status, req.finished_at = RestoreRequest.Status.COMPLETED, timezone.now()
        req.save()
        # The restore rolls the audit log back to the backup point, so the workflow's own history is re-recorded here in ONE entry
        # (the actors may not exist in the restored data, hence actor=None). The pre-restore safety backup keeps everything that was rolled back.
        audit.record("restore.completed", actor=None, request_id=req.pk, backup=req.backup.number, safety_backup=safety.number, reason=req.reason,
                     requested_by=req.requested_by.email if req.requested_by else None, approved_by=req.approved_by.email if req.approved_by else None,
                     executed_by=user.email, started_at=str(req.started_at))
    except Exception as exc:
        log.exception("Restore %s failed", req.pk)
        req.status, req.finished_at, req.error = RestoreRequest.Status.FAILED, timezone.now(), f"{type(exc).__name__}: {exc}"[:500]
        req.save()
        _log(req, f"FAILED: {req.error} (the database was left unchanged if the failure happened before the load transaction committed)")
        audit.record("restore.failed", actor=user, request_id=req.pk, error=req.error)
        notify_failure(f"Restore failed: {req.backup.number}", req.error)
    finally:
        cache.delete(MAINTENANCE_KEY)
    return RestoreRequest.objects.get(pk=pk)
