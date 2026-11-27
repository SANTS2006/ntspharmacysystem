"""Account business logic: credentials, lockout, roles, invitations. Views stay thin."""
import hashlib
import re
import secrets
import unicodedata
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit import services as audit

from .models import Invitation, LoginHistory, Role, User
from .permissions_registry import DEFAULT_ROLE_PERMISSIONS, ROLES

_dummy_hash = None


def _burn_hash_time(password: str) -> None:
    """Equalize timing for unknown accounts by verifying against a real hash."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = make_password(secrets.token_urlsafe(8))
    check_password(password, _dummy_hash)


class AuthError(Exception):
    def __init__(self, code, message, status=401):
        self.code, self.message, self.status = code, message, status


# ---------- credentials ----------
def pharmacy_initials(name: str) -> str:
    """'Green Life Pharmacy' -> 'GLP'. Accents stripped, non-alphanumerics are word separators."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = [w for w in re.split(r"[^A-Za-z0-9]+", ascii_name) if w]
    return "".join(w[0] for w in words).upper() or "PH"


def build_default_password(pharmacy_name: str, year: int | None = None) -> str:
    return f"{pharmacy_initials(pharmacy_name)}@{year or timezone.now().year}"


def issue_temporary_credentials(user: User, raw_password: str) -> None:
    """Temporary credential: hashed, expires, forces change at first login. Caller saves audit + delivery."""
    user.set_password(raw_password)
    user.must_change_password = True
    user.temp_password_expires_at = timezone.now() + timedelta(hours=settings.TEMP_CREDENTIAL_TTL_HOURS)
    user.credential_version += 1
    user.save()


# ---------- roles ----------
def seed_default_roles(tenant) -> dict[str, Role]:
    roles = {}
    for code, (name, scoped) in ROLES.items():
        roles[code], _ = Role.objects.get_or_create(
            tenant=tenant, code=code,
            defaults={"name": name, "branch_scoped": scoped, "permissions": sorted(DEFAULT_ROLE_PERMISSIONS[code])})
    return roles


# ---------- login ----------
def _log(email, tenant, user, success, reason, request):
    LoginHistory.objects.create(
        user=user, tenant=tenant, email_attempted=email[:254], success=success, reason=reason,
        ip_address=audit.client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") if request else "")[:255])


def authenticate(email: str, password: str, tenant, request=None) -> User:
    """Generic failure messages (no account enumeration); constant-ish timing via dummy hash check."""
    email = (email or "").strip().lower()
    user = User.objects.select_related("role", "tenant").filter(email=email, tenant=tenant).first()
    if user is None:
        _burn_hash_time(password)
        _log(email, tenant, None, False, "unknown", request)
        raise AuthError("invalid_credentials", "Invalid email or password.")
    if user.is_locked:
        _log(email, tenant, user, False, "locked", request)
        raise AuthError("account_locked", "Too many failed attempts. Try again later.", 429)
    if not user.check_password(password) or not user.is_active:
        _register_failure(user, request)
        raise AuthError("invalid_credentials", "Invalid email or password.")
    # Password correct from here on: specific messages are safe.
    if tenant is not None and not tenant.is_active_tenant:
        _log(email, tenant, user, False, "tenant_inactive", request)
        raise AuthError("tenant_inactive", "This pharmacy account is not active.", 403)
    if user.temp_credentials_expired:
        _log(email, tenant, user, False, "temp_expired", request)
        raise AuthError("credentials_expired", "Temporary credentials expired. Ask your administrator for a new invitation.", 403)
    user.failed_login_count, user.locked_until = 0, None
    user.save(update_fields=["failed_login_count", "locked_until"])
    _log(email, tenant, user, True, "", request)
    audit.record("auth.login", actor=user, tenant=tenant, request=request)
    return user


def google_platform_login(id_token: str, request=None) -> User:
    from apps.shop.services import verify_google_id_token
    info = verify_google_id_token(id_token)  # checks audience, issuer and that Google verified the address
    email = str(info.get("email", "")).lower()
    user = User.objects.filter(tenant__isnull=True, is_platform_admin=True, email=email).first()
    if user is None or not user.is_active:
        _log(email, None, user, False, "google_not_admin", request)
        raise AuthError("google_not_allowed", "This Google account is not a platform administrator.", 403)
    if user.is_locked:
        raise AuthError("account_locked", "Too many failed attempts. Try again later.", 429)
    _log(email, None, user, True, "google", request)
    audit.record("auth.google_login", actor=user, tenant=None, request=request)
    return user


def _register_failure(user, request):
    user.failed_login_count += 1
    if user.failed_login_count >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
        user.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
        user.failed_login_count = 0
        audit.record("auth.account_locked", actor=user, tenant=user.tenant, request=request)
    user.save(update_fields=["failed_login_count", "locked_until"])
    _log(user.email, user.tenant, user, False, "bad_password", request)
    audit.record("auth.login_failed", actor=user, tenant=user.tenant, request=request)


def issue_tokens(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["cv"] = user.credential_version
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


@transaction.atomic
def change_password(user: User, old_password: str, new_password: str, request=None) -> dict:
    if not user.check_password(old_password):
        raise AuthError("invalid_credentials", "Current password is incorrect.", 400)
    if old_password == new_password:
        raise AuthError("password_reuse", "New password must differ from the current one.", 400)
    return _set_new_password(user, new_password, request, "auth.password_changed")


def _set_new_password(user, new_password, request, action):
    user.set_password(new_password)
    user.must_change_password = False
    user.temp_password_expires_at = None
    user.credential_version += 1  # revokes every previously issued token
    user.save()
    audit.record(action, actor=user, tenant=user.tenant, request=request)
    from apps.notifications import inapp
    inapp.push([user], kind="security", level="warning", title="Your password was changed",
               body="If this was not you, reset your password now and tell your administrator.", link="/settings")
    return issue_tokens(user)


# ---------- invitations ----------
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_invitation(user: User) -> str:
    """Returns the raw token ONCE (to be emailed). Only its hash is persisted."""
    raw = secrets.token_urlsafe(32)
    Invitation.objects.create(
        user=user, token_hash=_hash(raw), expires_at=timezone.now() + timedelta(hours=settings.INVITATION_TTL_HOURS))
    return raw


@transaction.atomic
def accept_invitation(raw_token: str, new_password: str, request=None) -> dict:
    inv = (Invitation.objects.select_for_update(of=("self",)).select_related("user", "user__tenant")
           .filter(token_hash=_hash(raw_token)).first())
    if inv is None or inv.used_at or inv.expires_at < timezone.now():
        raise AuthError("invalid_invitation", "This invitation is invalid or has expired.", 400)
    user = inv.user
    inv.used_at = timezone.now()
    inv.save(update_fields=["used_at", "updated_at"])
    user.email_verified = True
    return _set_new_password(user, new_password, request, "auth.invitation_accepted")


# ---------- password reset (email link; token is single-use because it hashes the current password) ----------
def request_password_reset(email: str, tenant, request=None) -> None:
    """Always returns silently: never reveals whether the account exists."""
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode
    from apps.notifications.services import render_branded_html, send_email

    user = User.objects.select_related("tenant").filter(email=(email or "").strip().lower(), tenant=tenant, is_active=True).first()
    if user is None or (tenant and not tenant.is_active_tenant):
        return
    uid, token = urlsafe_base64_encode(force_bytes(user.pk)), default_token_generator.make_token(user)
    scope = f"&tenant={tenant.slug}" if tenant else ""
    link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?uid={uid}&token={token}{scope}"
    text = f"Use this link to reset your password (valid for a limited time): {link}\nIf you did not ask for this, ignore this email."
    send_email(to=user.email, subject="Reset your password", text=text, tenant=tenant, template="password_reset",
               html_body=render_branded_html(title="Reset your password", pharmacy=tenant, button=("Choose a new password", link),
                                             paragraphs=["We received a request to reset your password.", "If this was not you, ignore this email."]))
    audit.record("auth.password_reset_requested", actor=user, tenant=tenant, request=request)


@transaction.atomic
def confirm_password_reset(uid: str, token: str, new_password: str, tenant, request=None) -> dict:
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_str
    from django.utils.http import urlsafe_base64_decode
    try:
        user = User.objects.select_for_update(of=("self",)).get(pk=force_str(urlsafe_base64_decode(uid)), tenant=tenant, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        raise AuthError("invalid_reset", "This reset link is invalid or has expired.", 400)
    if not default_token_generator.check_token(user, token):
        raise AuthError("invalid_reset", "This reset link is invalid or has expired.", 400)
    user.failed_login_count, user.locked_until = 0, None
    return _set_new_password(user, new_password, request, "auth.password_reset_completed")
