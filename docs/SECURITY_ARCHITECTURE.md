# Security Architecture (Phase 1 state)

| Concern | Status |
|---|---|
| Tenant isolation | Implemented at identity, queryset, write, permission layers; tested. RLS planned. |
| Broken access control | Default-deny DRF permissions; server-side RBAC; tests for platform-only, audit, forced password change. |
| Brute force / enumeration | Throttle + lockout + generic errors; tested. Distributed throttling needs Redis in production. |
| Session hijack/revocation | Short access tokens, rotating blacklisted refresh, credential_version revocation, suspension revocation. |
| Audit | Append-only `AuditLog` (ORM-level immutability; also revoke UPDATE/DELETE grants at DB level in production). Secrets redacted from metadata. |
| Headers/transport | HSTS, SSL redirect, secure cookies when `DJANGO_DEBUG=false`; nosniff, frame deny, restrictive CSP on API responses. |
| CORS/CSRF | Explicit origin allow-list; API uses bearer tokens (no cookie auth), Django CSRF stays on for admin. |
| Mass assignment | Serializers whitelist fields; `status` changes only via audited actions; `tenant` is non-editable. |
| Uploads, payments, webhooks, backups, field encryption | **Not implemented yet** (later phases). |
| Dependency scanning | Not yet set up (`pip-audit` / `npm audit` in Phase 14). |

Known limitations: access token is held in memory and the refresh token in `sessionStorage` (XSS-exposed); an httpOnly-cookie refresh
flow is a candidate hardening. The default-password convention is weak by nature; prefer invitations.
