"""Object stores for backups. Production uses Cloudflare R2 (S3 API). Objects are private and only ever read back by the server:
no public or pre-signed URL is ever produced, and credentials never leave settings."""
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class LocalStore:
    """Development/test store on disk. Not for production (same failure domain as the app server)."""

    def __init__(self, root):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("Invalid object key.")
        return p

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class R2Store:
    def __init__(self, client, bucket):
        self.client, self.bucket = client, bucket

    def put(self, key: str, data: bytes) -> None:
        import io
        self.client.upload_fileobj(io.BytesIO(data), self.bucket, key, ExtraArgs={"ContentType": "application/octet-stream"})  # multipart for large objects

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False


def r2_client():
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com", aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY, region_name="auto", config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}))


def get_store():
    if settings.BACKUP_STORAGE == "r2":
        missing = [k for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BACKUP_BUCKET") if not getattr(settings, k)]
        if missing:
            raise ImproperlyConfigured(f"Cloudflare R2 backup storage is selected but not configured: {', '.join(missing)}.")
        if settings.R2_BACKUP_BUCKET == settings.R2_MEDIA_BUCKET:
            raise ImproperlyConfigured("Backups and application files must use different R2 buckets.")
        return R2Store(r2_client(), settings.R2_BACKUP_BUCKET)
    if not settings.DEBUG and settings.BACKUP_STORAGE != "local-ok":
        raise ImproperlyConfigured("Production backups must use BACKUP_STORAGE=r2 (local disk shares the application's failure domain).")
    return LocalStore(settings.BACKUP_LOCAL_DIR)
