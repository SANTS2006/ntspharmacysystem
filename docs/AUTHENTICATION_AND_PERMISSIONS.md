# Authentication & Permissions

## Endpoints (`/api/v1/auth/`)
`login/`, `refresh/`, `logout/`, `me/`, `change-password/`, `accept-invitation/`.
Tenant login sends `X-Tenant-Slug`; no header ⇒ platform login.

## Credentials
- Hashing: Argon2 (PBKDF2 fallback). Password policy: min 10 chars, common/numeric/similarity validators.
- Pharmacy admin default password: initials of the normalized pharmacy name + `@` + current year (`Green Life Pharmacy` → `GLP@2026`).
  It is a **temporary** credential: hashed, expires after `TEMP_CREDENTIAL_TTL_HOURS` (72), `must_change_password=True`, and every other
  endpoint returns 403 `password_change_required` until it is changed. The default password is guessable by design of the spec,
  so the **invitation flow** (`use_invitation=true`) is the recommended path: one-time token (SHA-256 stored), expires, single use.
- Changing a password bumps `credential_version`, instantly revoking all tokens issued earlier.
- The password is only ever delivered in the onboarding email, never in an API response.

## Brute-force & enumeration
Scoped throttle (`login` 10/min per IP), per-account lockout (`LOGIN_MAX_FAILED_ATTEMPTS` → `LOGIN_LOCKOUT_MINUTES`), identical
401 message for wrong tenant/unknown email/wrong password, dummy hash verification for unknown users, LoginHistory + audit rows.

## RBAC
`permissions_registry.py` is the single source of codenames and default grants for the 11 roles. Roles are per-tenant rows seeded at
onboarding (editable later). Views declare `required_permission`/`required_permissions`; missing declaration ⇒ denied.
Branch-scoped roles (`branch_scoped` and user has a branch) must filter querysets by `user.branch_id`. The frontend permission list from
`/auth/me/` only drives UI visibility.

## Not yet implemented
Google OAuth, customer registration + 6-character email verification, device/session listing, password reset by email (Phase 2/8).
