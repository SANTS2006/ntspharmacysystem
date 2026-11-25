from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class TenantAwareJWTAuthentication(JWTAuthentication):
    """Rejects tokens whose credential_version is stale (password change / revocation), disabled users,
    and users of non-active pharmacies. Token claims are never trusted for tenant identity."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if validated_token.get("cv") != user.credential_version:
            raise AuthenticationFailed("Session expired. Please sign in again.", code="token_revoked")
        if user.tenant_id and not user.tenant.is_active_tenant:
            raise AuthenticationFailed("This pharmacy account is not active.", code="tenant_inactive")
        return user
