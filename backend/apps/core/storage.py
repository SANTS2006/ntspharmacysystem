"""Cloudinary-backed Django storage.

* Branding/catalogue images (logos, medicine and service images) are public image assets, delivered through Cloudinary's CDN.
* Clinical and HR documents (prescription scans, staff documents) are uploaded as *authenticated* raw assets: they have no public URL,
  `url()` refuses to produce one, and the server reads them back with a signed request inside an already-authorised view.
Stored names are always replaced by a random id so names cannot be guessed or collide.
"""
import os
import ssl
import urllib.request
import uuid

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

PRIVATE_PREFIXES = ("prescriptions/", "staff-documents/")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _cloudinary():
    import cloudinary
    if not (settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET):
        raise ImproperlyConfigured("Cloudinary credentials are not configured.")
    cloudinary.config(cloud_name=settings.CLOUDINARY_CLOUD_NAME, api_key=settings.CLOUDINARY_API_KEY,
                      api_secret=settings.CLOUDINARY_API_SECRET, secure=True)
    return cloudinary


def _is_private(name: str) -> bool:
    return name.startswith(PRIVATE_PREFIXES)


def _kind(name: str) -> tuple[str, str, str]:
    """-> (resource_type, delivery type, public_id) derived purely from the stored name."""
    stem, ext = os.path.splitext(name)
    if _is_private(name):
        return "raw", "authenticated", name  # raw ids keep their extension
    if ext.lower() in IMAGE_EXT:
        return "image", "upload", stem
    return "raw", "upload", name


@deconstructible
class CloudinaryStorage(Storage):
    def get_available_name(self, name, max_length=None):
        folder, _, base = name.replace("\\", "/").rpartition("/")
        ext = os.path.splitext(base)[1].lower()[:10]
        return f"{folder + '/' if folder else ''}{uuid.uuid4().hex}{ext}"

    def _save(self, name, content):
        cl = _cloudinary()
        import cloudinary.uploader
        rtype, dtype, public_id = _kind(name)
        content.seek(0)
        cloudinary.uploader.upload(content.read(), public_id=public_id, resource_type=rtype, type=dtype, overwrite=False, invalidate=True)
        return name

    def _open(self, name, mode="rb"):
        _cloudinary()
        from cloudinary.utils import cloudinary_url
        rtype, dtype, public_id = _kind(name)
        ext = os.path.splitext(name)[1].lstrip(".")
        if dtype == "authenticated":  # signed with the API secret via the download endpoint: works regardless of delivery restrictions
            from cloudinary.utils import private_download_url
            url = private_download_url(public_id, "", resource_type=rtype, type=dtype, attachment=False)
        else:
            url, _ = cloudinary_url(public_id, resource_type=rtype, type=dtype, secure=True, format=ext if rtype == "image" else None)
        import certifi
        with urllib.request.urlopen(url, timeout=20, context=ssl.create_default_context(cafile=certifi.where())) as r:  # noqa: S310 (https Cloudinary host)
            return ContentFile(r.read(), name=name)

    def exists(self, name):
        return False  # names are random; never overwritten

    def delete(self, name):
        if not name:
            return
        _cloudinary()
        import cloudinary.uploader
        rtype, dtype, public_id = _kind(name)
        try:
            cloudinary.uploader.destroy(public_id, resource_type=rtype, type=dtype, invalidate=True)
        except Exception:  # deletion of an orphaned asset must never break a business transaction
            pass

    def url(self, name):
        if not name or _is_private(name):
            return ""  # private documents are only served through authorised views
        _cloudinary()
        from cloudinary.utils import cloudinary_url
        rtype, dtype, public_id = _kind(name)
        ext = os.path.splitext(name)[1].lstrip(".")
        return cloudinary_url(public_id, resource_type=rtype, type=dtype, secure=True, format=ext if rtype == "image" else None)[0]

    def size(self, name):
        return len(self._open(name).read())
