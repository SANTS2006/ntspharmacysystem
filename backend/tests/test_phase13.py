import gzip
import hashlib
from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command as real_call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.backups import services, storage
from apps.backups.models import BackupRecord, RestoreRequest
from apps.tenants.models import Branch, Pharmacy

from .test_foundation import ROOT_PW, api, login, platform_admin, platform_client, register, settled_token, two_pharmacies  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
B = "/api/v1/platform"


@pytest.fixture(autouse=True)
def backup_dir(settings, tmp_path):
    settings.BACKUP_LOCAL_DIR = str(tmp_path / "bk")
    cache.delete("maintenance_mode")
    yield
    cache.delete("maintenance_mode")


@pytest.fixture
def admins(two_pharmacies, platform_admin):
    User.objects.create_platform_admin("second@platform.test", ROOT_PW, full_name="Second")
    User.objects.create_platform_admin("third@platform.test", ROOT_PW, full_name="Third")
    mk = lambda email: api(token=api().post("/api/v1/auth/login/", {"email": email, "password": ROOT_PW}, format="json").data["tokens"]["access"])  # noqa: E731
    return {"a": two_pharmacies, "b": mk("second@platform.test"), "c": mk("third@platform.test")}


def make_backup(c, status=201):
    r = c.post(f"{B}/backups/", {}, format="json")
    assert r.status_code == status, r.data
    return r.data


# ---------------- creating, encrypting, verifying ----------------
def test_backup_is_complete_encrypted_and_verified(admins):
    d = make_backup(admins["a"])
    assert d["status"] == "completed" and d["verification"].startswith("OK") and d["size_bytes"] > 0 and d["kind"] == "manual"
    rec = BackupRecord.objects.get(pk=d["id"])
    assert rec.object_counts["tenants.pharmacy"] == 2 and rec.object_counts["tenants.branch"] == 2  # tenant-owned rows are included (dump bypasses the fail-closed manager)
    assert rec.object_counts["accounts.user"] >= 5 and rec.object_counts.get("accounts.role") == 22
    assert not [m for m in rec.object_counts if m.startswith(("backups.", "sessions.", "contenttypes.", "token_blacklist."))]
    blob = storage.get_store().get(rec.object_key)
    assert hashlib.sha256(blob).hexdigest() == rec.checksum_sha256 and len(blob) == rec.size_bytes
    assert b"a@green.test" not in blob and b"greenlife" not in blob  # nothing readable at rest
    with pytest.raises(Exception):
        gzip.decompress(blob)  # encrypted, not just compressed
    assert rec.retention_until == timezone.localdate() + timedelta(days=30) and rec.key_fingerprint
    assert {"backup.created", "backup.verified"} <= set(AuditLog.objects.values_list("action", flat=True))


def test_only_platform_administrators_can_touch_backups(admins):
    d = make_backup(admins["a"])
    tenant_admin = api("greenlife", settled_token("greenlife", "a@green.test", f"GLP@{timezone.now().year}"))
    for method, url in (("get", f"{B}/backups/"), ("post", f"{B}/backups/"), ("get", f"{B}/backups/health/"), ("get", f"{B}/backups/{d['id']}/download/"), ("post", f"{B}/backups/{d['id']}/verify/"),
                        ("get", f"{B}/restores/"), ("post", f"{B}/restores/")):
        assert getattr(tenant_admin, method)(url).status_code == 403, url
        assert getattr(api(), method)(url).status_code == 401, url
    assert BackupRecord.objects.count() == 1


def test_download_is_the_encrypted_object_and_audited(admins):
    d = make_backup(admins["a"])
    r = admins["a"].get(f"{B}/backups/{d['id']}/download/")
    assert r.status_code == 200 and r["Content-Type"] == "application/octet-stream" and r["Cache-Control"] == "private, no-store"
    assert hashlib.sha256(r.content).hexdigest() == BackupRecord.objects.get(pk=d["id"]).checksum_sha256 and b"greenlife" not in r.content
    assert AuditLog.objects.filter(action="backup.downloaded").count() == 1
    BackupRecord.objects.filter(pk=d["id"]).update(status="failed")
    assert admins["a"].get(f"{B}/backups/{d['id']}/download/").status_code == 409


def test_verification_detects_corruption_and_wrong_keys(admins, settings):
    d = make_backup(admins["a"])
    rec = BackupRecord.objects.get(pk=d["id"])
    path = storage.get_store()._path(rec.object_key)
    good = path.read_bytes()
    path.write_bytes(good[:-5] + b"XXXXX")  # bit rot / tampering in the bucket
    before = len(mail.outbox)
    r = admins["a"].post(f"{B}/backups/{d['id']}/verify/")
    assert r.data["verification"].startswith("FAILED") and "Checksum mismatch" in r.data["verification"]
    assert any("verification failed" in m.subject.lower() and m.to == ["root@platform.test"] for m in mail.outbox[before:])
    path.write_bytes(good)
    assert admins["a"].post(f"{B}/backups/{d['id']}/verify/").data["verification"].startswith("OK")
    settings.BACKUP_ENCRYPTION_KEY = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC="
    assert "different key" in admins["a"].post(f"{B}/backups/{d['id']}/verify/").data["verification"]


def test_failures_are_recorded_alerted_and_do_not_wedge_the_system(admins):
    before = len(mail.outbox)
    with mock.patch.object(storage.LocalStore, "put", side_effect=OSError("bucket unreachable")):
        d = admins["a"].post(f"{B}/backups/", {}, format="json")
    assert d.status_code == 500 and d.data["status"] == "failed" and "bucket unreachable" in d.data["error"]
    assert any("Backup failed" in m.subject for m in mail.outbox[before:]) and "backup.failed" in set(AuditLog.objects.values_list("action", flat=True))
    assert make_backup(admins["a"])["status"] == "completed"  # nothing left in "running"
    BackupRecord.objects.create(number="BK-stuck", status="running")
    assert admins["a"].post(f"{B}/backups/", {}, format="json").status_code == 409  # one at a time


# ---------------- Cloudflare R2 ----------------
def test_r2_store_configuration_and_calls(settings):
    settings.BACKUP_STORAGE, settings.R2_ACCOUNT_ID, settings.R2_ACCESS_KEY_ID, settings.R2_SECRET_ACCESS_KEY = "r2", "acct123", "key", "secret"
    settings.R2_BACKUP_BUCKET, settings.R2_MEDIA_BUCKET = "", ""
    with pytest.raises(ImproperlyConfigured):
        storage.get_store()  # no bucket
    settings.R2_BACKUP_BUCKET = settings.R2_MEDIA_BUCKET = "same"
    with pytest.raises(ImproperlyConfigured):
        storage.get_store()  # backups must not share a bucket with application files
    settings.R2_BACKUP_BUCKET = "backups"
    with mock.patch("boto3.client") as client:
        st = storage.get_store()
        kw = client.call_args.kwargs
        assert kw["endpoint_url"] == "https://acct123.r2.cloudflarestorage.com" and kw["region_name"] == "auto" and kw["config"].signature_version == "s3v4"
        st.put("db-backups/x.enc", b"data")
        up = client.return_value.upload_fileobj.call_args
        assert up.args[1:3] == ("backups", "db-backups/x.enc") and "ACL" not in up.kwargs.get("ExtraArgs", {})
        client.return_value.get_object.return_value = {"Body": mock.Mock(read=lambda: b"data")}
        assert st.get("db-backups/x.enc") == b"data"
        st.delete("db-backups/x.enc")
        client.return_value.delete_object.assert_called_with(Bucket="backups", Key="db-backups/x.enc")
        assert not hasattr(st, "presign") and not client.return_value.generate_presigned_url.called  # no URL to storage is ever produced


def test_production_refuses_local_disk_and_missing_key(settings):
    settings.BACKUP_STORAGE, settings.DEBUG = "local", False
    with pytest.raises(ImproperlyConfigured):
        storage.get_store()
    settings.BACKUP_ENCRYPTION_KEY = ""
    with pytest.raises(ImproperlyConfigured):
        services._fernet()


def test_local_store_blocks_path_traversal(tmp_path):
    st = storage.LocalStore(tmp_path / "root")
    with pytest.raises(ValueError):
        st.put("../../escape.txt", b"x")


# ---------------- retention and health ----------------
def test_retention_purges_old_objects_but_keeps_the_newest_verified(admins, settings):
    ids = [make_backup(admins["a"])["id"] for _ in range(3)]
    old = timezone.localdate() - timedelta(days=1)
    BackupRecord.objects.update(retention_until=old)
    settings.BACKUP_MIN_KEEP = 1
    assert services.purge_expired() == 2
    recs = {r.pk: r for r in BackupRecord.objects.all()}
    assert [recs[i].status for i in ids].count("deleted") == 2 and recs[ids[-1]].status == "completed"  # the newest survives even when "expired"
    assert not storage.get_store().exists(recs[ids[0]].object_key) and storage.get_store().exists(recs[ids[-1]].object_key)
    assert services.purge_expired() == 0
    assert admins["a"].get(f"{B}/backups/").data["count"] == 3  # history is kept


def test_health_endpoints_and_rpo_flag(admins, settings):
    assert admins["a"].get(f"{B}/backups/health/").data["rpo_breached"] is True  # no backup yet
    make_backup(admins["a"])
    h = admins["a"].get(f"{B}/backups/health/").data
    assert h["rpo_breached"] is False and h["last_verified_backup"].startswith("BK-") and h["encryption_key_configured"] is True and h["restore_enabled"] is True and h["rpo_target_hours"] == 6
    BackupRecord.objects.update(started_at=timezone.now() - timedelta(hours=30))
    assert admins["a"].get(f"{B}/backups/health/").data["rpo_breached"] is True
    assert api().get("/health/live/").json() == {"status": "ok"}
    r = api().get("/health/ready/")
    assert r.status_code == 200 and r.json()["checks"] == {"database": "ok", "cache": "ok"}
    with mock.patch("django.db.backends.utils.CursorWrapper.execute", side_effect=Exception("db down")):
        assert api().get("/health/ready/").status_code == 503


def test_scheduled_task_runs_and_reports(admins):
    from apps.backups.tasks import purge_expired, scheduled_backup
    assert BackupRecord.objects.get(pk=scheduled_backup()).kind == "scheduled"
    with mock.patch.object(services, "run_backup", side_effect=RuntimeError("storage offline")):
        before = len(mail.outbox)
        assert scheduled_backup() is None
        assert any("Scheduled backup could not start" in m.subject for m in mail.outbox[before:])
    assert purge_expired() == 0


# ---------------- restore workflow ----------------
def request(c, backup_id, password=ROOT_PW, reason="Recovering from accidental bulk deletion", status=201):
    r = c.post(f"{B}/restores/", {"backup": backup_id, "reason": reason, "password": password}, format="json")
    assert r.status_code == status, r.data
    return r.data


def test_restore_request_rules(admins, settings):
    d = make_backup(admins["a"])
    request(admins["a"], d["id"], password="wrong", status=403)
    request(admins["a"], d["id"], reason="short", status=400)
    BackupRecord.objects.filter(pk=d["id"]).update(verification="FAILED: bad")
    request(admins["a"], d["id"], status=409)  # unverified backups cannot be restored
    BackupRecord.objects.filter(pk=d["id"]).update(verification="OK: x")
    settings.BACKUP_ALLOW_RESTORE = False
    request(admins["a"], d["id"], status=409)  # disabled deployment
    settings.BACKUP_ALLOW_RESTORE = True
    r = request(admins["a"], d["id"])
    assert r["status"] == "pending" and any(m.to == ["second@platform.test"] and "Restore approval needed" in m.subject for m in mail.outbox)
    request(admins["b"], d["id"], status=409)  # only one open request at a time
    tenant_admin = api("greenlife", settled_token("greenlife", "a@green.test", f"GLP@{timezone.now().year}"))
    assert tenant_admin.post(f"{B}/restores/{r['id']}/approve/", {"password": "x"}, format="json").status_code == 403


def test_two_person_approval_and_confirmation(admins):
    d = make_backup(admins["a"])
    r = request(admins["a"], d["id"])
    ap = lambda c, pw=ROOT_PW: c.post(f"{B}/restores/{r['id']}/approve/", {"password": pw}, format="json")  # noqa: E731
    assert ap(admins["a"]).status_code == 403  # requester cannot approve their own request
    assert ap(admins["b"], "wrong").status_code == 403
    ex = lambda c, conf, pw=ROOT_PW: c.post(f"{B}/restores/{r['id']}/execute/", {"password": pw, "confirmation": conf}, format="json")  # noqa: E731
    assert ex(admins["a"], "x").status_code == 409  # not approved yet
    approved = ap(admins["b"])
    assert approved.status_code == 200 and approved.data["status"] == "approved" and approved.data["confirmation_phrase"] == f"RESTORE {d['number']}"
    assert ex(admins["a"], "RESTORE nothing").status_code == 400
    assert ex(admins["a"], approved.data["confirmation_phrase"], "wrong").status_code == 403
    assert ex(admins["c"], approved.data["confirmation_phrase"]).status_code == 403  # a bystander cannot trigger it
    assert RestoreRequest.objects.get(pk=r["id"]).status == "approved"
    RestoreRequest.objects.filter(pk=r["id"]).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert ex(admins["a"], approved.data["confirmation_phrase"]).status_code == 409  # approvals expire
    assert admins["a"].get(f"{B}/restores/").data[0]["status"] == "expired"
    rej = request(admins["a"], d["id"])
    assert admins["b"].post(f"{B}/restores/{rej['id']}/reject/", {"password": ROOT_PW}, format="json").data["status"] == "rejected"


def approved_restore(admins, backup_id):
    r = request(admins["a"], backup_id)
    admins["b"].post(f"{B}/restores/{r['id']}/approve/", {"password": ROOT_PW}, format="json")
    return r["id"], f"RESTORE {BackupRecord.objects.get(pk=backup_id).number}"


def run_restore(admins, rid, phrase, who="a", status=200):
    r = admins[who].post(f"{B}/restores/{rid}/execute/", {"password": ROOT_PW, "confirmation": phrase}, format="json")
    assert r.status_code == status, r.data
    return r.data


def test_restore_returns_the_database_to_the_backup_and_revokes_sessions(admins):
    pc = admins["a"]
    old_tenant_token = api("greenlife", settled_token("greenlife", "a@green.test", f"GLP@{timezone.now().year}"))
    d = make_backup(pc)
    snapshot = BackupRecord.objects.get(pk=d["id"]).object_counts
    # changes made AFTER the backup: a new pharmacy, a renamed one, an extra branch, a deleted staff user
    assert register(pc, "Late Pharmacy", "latepharm", "late@late.test").status_code == 201
    Pharmacy.objects.filter(slug="greenlife").update(name="Renamed After Backup")
    assert Pharmacy.objects.count() == 3 and Pharmacy.objects.get(slug="greenlife").name == "Renamed After Backup"
    later = make_backup(pc)["number"]  # history created after the snapshot must survive the restore
    rid, phrase = approved_restore(admins, d["id"])
    out = run_restore(admins, rid, phrase)
    assert out["status"] == "completed" and any("sessions revoked" in line for line in out["log"])
    assert Pharmacy.objects.count() == 2 and not Pharmacy.objects.filter(slug="latepharm").exists() and Pharmacy.objects.get(slug="greenlife").name == "Green Life Pharmacy"
    assert User.objects.filter(email="late@late.test").count() == 0 and Branch.all_objects.count() == snapshot["tenants.branch"]
    assert BackupRecord.objects.filter(number=later).exists() and BackupRecord.objects.filter(kind="pre_restore", status="completed").count() == 1  # history and the safety backup survive
    assert RestoreRequest.objects.get(pk=rid).safety_backup.verification.startswith("OK")
    assert old_tenant_token.get("/api/v1/auth/me/").status_code == 401  # every session is revoked
    assert admins["a"].get(f"{B}/backups/").status_code == 401
    assert api().post("/api/v1/auth/login/", {"email": "root@platform.test", "password": ROOT_PW}, format="json").status_code == 200  # people can sign in again
    done = AuditLog.objects.get(action="restore.completed")  # the audit log itself is rolled back to the backup point, so the whole workflow is re-recorded in this entry
    assert done.actor is None and done.metadata["requested_by"] == "root@platform.test" and done.metadata["approved_by"] == "second@platform.test" and done.metadata["reason"].startswith("Recovering")
    assert done.metadata["safety_backup"] == RestoreRequest.objects.get(pk=rid).safety_backup.number
    assert cache.get("maintenance_mode") is None


def test_failed_restore_leaves_the_database_untouched(admins):
    pc = admins["a"]
    d = make_backup(pc)
    register(pc, "Late Pharmacy", "latepharm", "late@late.test")
    # 1) the load itself fails midway: the wipe is rolled back with it
    rid, phrase = approved_restore(admins, d["id"])
    real = real_call_command

    def flaky(name, *a, **k):
        if name == "loaddata":
            raise RuntimeError("disk full")
        return real(name, *a, **k)
    with mock.patch.object(services, "call_command", side_effect=flaky):
        out = run_restore(admins, rid, phrase, status=500)
    assert out["status"] == "failed" and "disk full" in out["error"]
    assert Pharmacy.objects.count() == 3 and Pharmacy.objects.filter(slug="latepharm").exists() and User.objects.filter(email="late@late.test").exists()
    assert cache.get("maintenance_mode") is None
    # 2) a corrupted backup is rejected before anything is touched
    RestoreRequest.objects.filter(pk=rid).update(status="failed")
    path = storage.get_store()._path(BackupRecord.objects.get(pk=d["id"]).object_key)
    path.write_bytes(path.read_bytes()[:-3] + b"zzz")
    BackupRecord.objects.filter(pk=d["id"]).update(verification="OK: forged")
    rid2, phrase2 = approved_restore(admins, d["id"])
    out2 = run_restore(admins, rid2, phrase2, status=500)
    assert out2["status"] == "failed" and "verification" in out2["error"].lower() and Pharmacy.objects.count() == 3
    # 3) if the safety backup cannot be taken, the restore never starts
    d2 = make_backup(pc)
    RestoreRequest.objects.filter(status__in=["pending", "approved"]).update(status="rejected")
    rid3, phrase3 = approved_restore(admins, d2["id"])
    failed_rec = BackupRecord(number="BK-fake", status="failed", error="storage offline")
    with mock.patch.object(services, "run_backup", return_value=failed_rec):
        out3 = run_restore(admins, rid3, phrase3, status=500)
    assert "safety backup failed" in out3["error"] and Pharmacy.objects.count() == 3


def test_maintenance_mode_blocks_tenant_traffic_but_not_administration(admins):
    tenant_admin = api("greenlife", settled_token("greenlife", "a@green.test", f"GLP@{timezone.now().year}"))
    assert tenant_admin.get("/api/v1/tenants/dashboard/").status_code == 200
    cache.set("maintenance_mode", True, 60)
    r = tenant_admin.get("/api/v1/tenants/dashboard/")
    assert r.status_code == 503 and r.json()["error"]["code"] == "maintenance" and r["Retry-After"] == "120"
    assert api().get("/api/v1/public/pharmacies/greenlife/").status_code == 503
    assert admins["a"].get(f"{B}/backups/health/").status_code == 200 and api().get("/health/live/").status_code == 200
    cache.delete("maintenance_mode")
    assert tenant_admin.get("/api/v1/tenants/dashboard/").status_code == 200
