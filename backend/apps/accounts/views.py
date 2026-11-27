from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.views import TenantContextMixin

from . import services
from .models import User
from .permissions import IsAuthenticatedAndSettled


def error(code, message, http_status):
    return Response({"success": False, "error": {"code": code, "message": message, "details": None}},
                    status=http_status)


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="role.code", default=None)
    permissions = serializers.SerializerMethodField()
    tenant_slug = serializers.CharField(source="tenant.slug", default=None)
    avatar = serializers.SerializerMethodField()
    role_name = serializers.CharField(source="role.name", default=None)
    branch_name = serializers.CharField(source="branch.name", default=None)
    pharmacy_name = serializers.CharField(source="tenant.name", default=None)
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "role", "permissions", "tenant_slug", "branch",
                  "is_platform_admin", "email_verified", "must_change_password",
                  "avatar", "role_name", "branch_name", "pharmacy_name", "has_password", "date_joined"]

    def get_avatar(self, user):
        return user.avatar.url if user.avatar else None

    def get_has_password(self, user):
        return user.has_usable_password()

    def get_permissions(self, user):  # UI hint only; the backend re-checks every request
        return sorted(user.role.permissions) if user.role_id else []


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class PasswordPolicyMixin:
    def validate_new_password(self, value):
        validate_password(value, getattr(self.context.get("request"), "user", None))
        return value


class ChangePasswordSerializer(PasswordPolicyMixin, serializers.Serializer):
    old_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)


class AcceptInvitationSerializer(PasswordPolicyMixin, serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(trim_whitespace=False)


class LoginView(TenantContextMixin, APIView):
    """Tenant users log in with the pharmacy's X-Tenant-Slug (or subdomain); no hint => platform login."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle
        return [ScopedRateThrottle()]

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        from apps.core.views import resolve_hint
        tenant = resolve_hint(request)  # ignores active status: inactive tenants get a specific error post-auth
        if getattr(request._request, "tenant_hint", None) and tenant is None:
            return error("invalid_credentials", "Invalid email or password.", status.HTTP_401_UNAUTHORIZED)
        try:
            user = services.authenticate(s.validated_data["email"], s.validated_data["password"], tenant, request)
        except services.AuthError as e:
            return error(e.code, e.message, e.status)
        return Response({"success": True, "tokens": services.issue_tokens(user),
                         "user": UserSerializer(user).data})


class PlatformGoogleView(APIView):
    """Google sign-in for EXISTING platform administrators only. It never creates an account or reaches a pharmacy account."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle
        return [ScopedRateThrottle()]

    def post(self, request):
        try:
            user = services.google_platform_login(str(request.data.get("id_token", "")), request)
        except services.AuthError as e:
            return error(e.code, e.message, e.status)
        return Response({"success": True, "tokens": services.issue_tokens(user), "user": UserSerializer(user).data})


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle
        return [ScopedRateThrottle()]

    def post(self, request):
        raw = request.data.get("refresh", "")
        try:
            old = RefreshToken(raw)
            user = User.objects.select_related("tenant").get(pk=old["user_id"])
            if old.get("cv") != user.credential_version or not user.is_active or (
                    user.tenant_id and not user.tenant.is_active_tenant):
                raise TokenError("revoked")
            old.blacklist()
        except (TokenError, User.DoesNotExist, KeyError):
            return error("invalid_token", "Session expired. Please sign in again.", status.HTTP_401_UNAUTHORIZED)
        return Response({"success": True, "tokens": services.issue_tokens(user)})


class LogoutView(APIView):
    allow_pending_password_change = True

    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except TokenError:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(TenantContextMixin, APIView):
    allow_pending_password_change = True  # frontend needs this to route to the forced-change screen

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(TenantContextMixin, APIView):
    allow_pending_password_change = True
    throttle_scope = "sensitive"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle
        return [ScopedRateThrottle()]

    def post(self, request):
        s = ChangePasswordSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        try:
            tokens = services.change_password(request.user, s.validated_data["old_password"],
                                              s.validated_data["new_password"], request)
        except services.AuthError as e:
            raise ValidationError({"detail": e.message})
        return Response({"success": True, "tokens": tokens})


class AcceptInvitationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "sensitive"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle
        return [ScopedRateThrottle()]

    def post(self, request):
        s = AcceptInvitationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            tokens = services.accept_invitation(s.validated_data["token"], s.validated_data["new_password"], request)
        except services.AuthError as e:
            return error(e.code, e.message, e.status)
        return Response({"success": True, "tokens": tokens})


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(PasswordPolicyMixin, serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(trim_whitespace=False)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "sensitive"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle
        return [ScopedRateThrottle()]

    def post(self, request):
        from apps.core.views import resolve_hint
        s = PasswordResetRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        hinted = getattr(request._request, "tenant_hint", None)
        tenant = resolve_hint(request)
        if not (hinted and tenant is None):
            services.request_password_reset(s.validated_data["email"], tenant, request)
        return Response(status=status.HTTP_204_NO_CONTENT)  # identical response whether or not the account exists


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "sensitive"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle
        return [ScopedRateThrottle()]

    def post(self, request):
        from apps.core.views import resolve_hint
        s = PasswordResetConfirmSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        tenant = resolve_hint(request)
        if getattr(request._request, "tenant_hint", None) and tenant is None:
            return error("invalid_reset", "This reset link is invalid or has expired.", 400)
        try:
            tokens = services.confirm_password_reset(s.validated_data["uid"], s.validated_data["token"],
                                                     s.validated_data["new_password"], tenant, request)
        except services.AuthError as e:
            return error(e.code, e.message, e.status)
        return Response({"success": True, "tokens": tokens})
