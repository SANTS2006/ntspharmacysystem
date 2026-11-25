# Backup and Recovery (Phase 13)

**Status: the backup/verify/retention/restore logic is tested end-to-end against a local-disk store (including a real restore). The Cloudflare R2 store is tested only with a mocked S3 client: it has never talked to R2. Run a full backup → verify → restore drill against a staging R2 bucket before relying on it.**

## What is backed up
A **full logical dump** of the database (`dumpdata`, all tenants) → gzip → **Fernet (AES-128-CBC + HMAC) encryption** → object store, then **verified immediately** (checksum of the stored object, decryption, deserialisation of every record into known models, object counts compared with the counts taken at backup time).
Excluded: `backups` (history must survive a restore), `contenttypes`, `sessions`, `token_blacklist`, `admin`. **Uploaded files (prescription documents, logos, HR documents) are not in these backups**; they live in a separate R2 bucket (`R2_MEDIA_BUCKET`, private, versioning recommended) and need their own bucket-level protection. Backups and media must use different buckets (enforced).
Incremental backups are **not supported** by this strategy (full dumps only). For large databases use Neon point-in-time recovery / branching and `pg_dump`; this logical backup refuses objects above `BACKUP_MAX_BYTES` (default 1 GB, held in memory) rather than failing unpredictably.

## Security
- Encryption key `BACKUP_ENCRYPTION_KEY` (Fernet) is separate from `FIELD_ENCRYPTION_KEY`, lives only in the environment/secret manager, and is **never stored in the database or the bucket**. Each backup records only a key *fingerprint*, so a wrong key is reported clearly. **If you lose the key, every backup is unreadable.** Store a sealed copy offline; rotate by taking a new backup under the new key and keeping the old key until old backups expire.
- R2 credentials come from environment variables, are used server-side only, and no public or pre-signed URL is ever generated. "Download" returns the *encrypted* object through an authenticated, audited endpoint.
- Only platform administrators can see or use any backup endpoint (tenant users get 403, anonymous 401).
- Production refuses local-disk backup storage and refuses to run without the key.

## Schedule, retention, alerts
Celery beat: `scheduled_backup` every `BACKUP_SCHEDULE_HOURS` (default 6), `purge_expired` daily. Retention `BACKUP_RETENTION_DAYS` (30); the newest `BACKUP_MIN_KEEP` verified backups are never purged, and a backup tied to an open restore is protected. Purged objects are deleted from R2 and the record is kept as history.
Failed backups, failed verification, failed restores and a scheduled backup that cannot start are emailed to all platform administrators (Brevo path) and audited. One backup runs at a time (DB-enforced).
`GET /platform/backups/health/` and the dashboard show the last verified backup, its age, whether the RPO target is breached, key configuration, recent failures.

## Restore (default OFF: set `BACKUP_ALLOW_RESTORE=true` only when you mean it)
1. Administrator A **requests** a restore of a *verified* backup (password re-entered, reason ≥ 10 characters; one open request at a time).
2. Administrator B (**a different person**) **approves** (password re-entered) within `RESTORE_APPROVAL_MINUTES` (60) or the request expires. Rejection is possible.
3. A or B **executes** by typing `RESTORE <backup number>` and re-entering their password. A third administrator cannot.
4. The service re-verifies the backup, **takes a verified safety backup of the current database (if that fails, nothing is changed)**, switches on **maintenance mode** (tenant API calls get 503 + `Retry-After`; platform administration and health checks keep working), then in **one transaction** deletes all restorable rows and loads the backup; foreign keys are checked at commit, so *any* failure rolls the whole thing back and leaves the database untouched. Afterwards every user's `credential_version` is bumped, which **signs everyone out**.
5. The recovery log (verification, safety backup, maintenance, result) is stored on the request; a `restore.completed` audit entry records requester, approver, executor, reason, backup and safety backup. Because the restore rolls the audit log back to the backup point, the workflow's history is re-recorded in that single entry, and everything rolled back is preserved in the safety backup.
Consequences to accept: data created after the backup is removed (the safety backup contains it), uploaded files are not rolled back, and the maintenance flag is a cache key (use Redis in production so every web process sees it).
Restore of a *single* tenant is not implemented (whole-database only).

## RPO / RTO (targets, not guarantees)
- **RPO ≈ `BACKUP_SCHEDULE_HOURS` (6 h)** by default; lower it for a smaller loss window. The dashboard flags a breach when the newest verified backup is older than 1.5× the interval. Neon's own point-in-time recovery can provide a much smaller RPO and should be enabled as the primary safety net.
- **RTO**: dominated by decrypt + load time. Rule of thumb for this logical method: minutes per hundred MB on a modest worker; a 1 GB dump can take tens of minutes. **Measure it in a drill** and write the number down; plus operator time for the approval steps (≥ 2 people).
- Drill at least quarterly: restore into a staging environment, sign in, spot-check tenants, record the timing.

## Not implemented
Incremental or differential backups, pg_dump/pg_restore backups, per-tenant restore, restoring into a *different* database from the UI, automatic restore drills, offsite replication to a second provider, backup of media files, key rotation tooling, streaming encryption for very large dumps.
