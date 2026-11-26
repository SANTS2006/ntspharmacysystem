from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

from .permissions_registry import ROLES


class Role(TimeStampedModel):
    """Per-tenant, configurable role. `permissions` is a list of codenames from permissions_registry."""
    tenant = models.ForeignKey("tenants.Pharmacy", on_delete=models.CASCADE, related_name="roles")
    code = models.CharField(max_length=40, choices=[(c, v[0]) for c, v in ROLES.items()])
    name = models.CharField(max_length=80)
    permissions = models.JSONField(default=list)
    branch_scoped = models.BooleanField(default=True)
    is_system = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="uniq_role_code_per_tenant")]

    def __str__(self):
        return f"{self.name} @ {self.tenant_id}"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        return self._create(email, password, **extra)

    def create_platform_admin(self, email, password, **extra):
        extra.update(is_platform_admin=True, is_staff=True, is_superuser=True, tenant=None)
        return self._create(email, password, **extra)

    create_superuser = create_platform_admin


class User(AbstractBaseUser, PermissionsMixin):
    """Platform admins have tenant=None. Everyone else belongs to exactly one pharmacy (and optionally a branch)."""
    tenant = models.ForeignKey("tenants.Pharmacy", null=True, blank=True, on_delete=models.PROTECT, related_name="users")
    branch = models.ForeignKey("tenants.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="staff")
    role = models.ForeignKey(Role, null=True, blank=True, on_delete=models.PROTECT, related_name="users")
    email = models.EmailField()
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
    is_platform_admin = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)  # Django admin access only
    is_active = models.BooleanField(default=True)
    email_verified = models.BooleanField(default=False)

    must_change_password = models.BooleanField(default=False)
    temp_password_expires_at = models.DateTimeField(null=True, blank=True)
    credential_version = models.PositiveIntegerField(default=1)  # bump => all issued tokens die
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]
    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "email"], name="uniq_email_per_tenant"),
            models.UniqueConstraint(fields=["email"], condition=models.Q(tenant__isnull=True),
                                    name="uniq_platform_email"),
            models.CheckConstraint(
                condition=models.Q(is_platform_admin=True, tenant__isnull=True) |
                      models.Q(is_platform_admin=False, tenant__isnull=False),
                name="platform_admin_xor_tenant"),
        ]
        indexes = [models.Index(fields=["tenant", "role"]), models.Index(fields=["tenant", "branch"])]

    def __str__(self):
        return self.email

    # ---- permission helpers (backend is the only source of truth) ----
    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    @property
    def temp_credentials_expired(self) -> bool:
        return bool(self.must_change_password and self.temp_password_expires_at
                    and self.temp_password_expires_at < timezone.now())

    def has_tenant_perm(self, codename: str) -> bool:
        if self.is_platform_admin or not self.role_id:
            return False
        return codename in self.role.permissions

    @property
    def is_branch_scoped(self) -> bool:
        return bool(self.role_id and self.role.branch_scoped and self.branch_id)


class LoginHistory(models.Model):
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="login_history")
    tenant = models.ForeignKey("tenants.Pharmacy", null=True, on_delete=models.SET_NULL, related_name="+")
    email_attempted = models.EmailField()
    success = models.BooleanField()
    reason = models.CharField(max_length=40, blank=True)
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class Invitation(TimeStampedModel):
    """Secure alternative to emailed temporary passwords. Only the SHA-256 of the token is stored."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="invitations")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class EmailChange(models.Model):
    """A pending change of sign-in address. The code is stored only as a salted hash; one pending change per user."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="email_change")
    new_email = models.EmailField()
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now=True)
