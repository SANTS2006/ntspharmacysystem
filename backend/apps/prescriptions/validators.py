from django.conf import settings
from django.core.exceptions import ValidationError

_MAGIC = {".pdf": [b"%PDF-"], ".png": [b"\x89PNG\r\n\x1a\n"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"], ".webp": [b"RIFF"]}


def validate_prescription_file(f):
    """Extension allow-list + size cap + magic-byte check (extension alone is spoofable)."""
    name = f.name.lower()
    ext = next((e for e in _MAGIC if name.endswith(e)), None)
    if ext is None:
        raise ValidationError("Upload a PDF, PNG, JPG or WebP file.")
    if f.size > settings.PRESCRIPTION_FILE_MAX_BYTES:
        raise ValidationError("The file must be 5 MB or smaller.")
    pos = f.tell() if hasattr(f, "tell") else 0
    f.seek(0)
    head = f.read(16)
    f.seek(pos)
    if not any(head.startswith(m) for m in _MAGIC[ext]):
        raise ValidationError("The file content does not match its type.")
