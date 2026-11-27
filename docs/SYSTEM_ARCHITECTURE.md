# System Architecture

## Layout
```
backend/   Django project: config/ (settings, urls, asgi, celery) + apps/
frontend/  Vite + React 19 + TS + Tailwind 4 SPA
docs/
```

## Backend apps (modular; views thin, logic in services.py)
| App | Responsibility | Phase |
|---|---|---|
| core | tenant context, TenantOwnedModel/TenantManager, tenant middleware, exception envelope, security headers | 1 |
| tenants | Pharmacy (tenant), Branch, registration/suspension services, platform API | 1 (extended 2-3) |
| accounts | custom User, per-tenant Role, permission registry, JWT auth, lockout, invitations, login history | 1 |
| audit | append-only AuditLog + service + API | 1 |
| medicines, inventory, procurement, prescriptions, pos, orders, payments, accounting, payroll, reports, notifications, backups | per roadmap | 4-13 |

Within each future app: `models.py`, `selectors.py` (reads), `services.py` (writes, transactions), `serializers.py`, `views.py`, `permissions.py`, `urls.py`.

## Request flow
`TenantResolutionMiddleware` (computes an untrusted *hint* from header `X-Tenant-Slug`, subdomain or custom domain)
→ DRF authentication (`TenantAwareJWTAuthentication`: checks credential_version, active user, active tenant)
→ `TenantContextMixin.initial` binds the tenant (always `user.tenant` for tenant users)
→ permission class (`HasTenantPermission`: default-deny, codename declared per view)
→ view → service (transaction) → `TenantManager`-scoped ORM.

## Conventions
- Errors: `{"success": false, "error": {"code", "message", "details"}}`. Lists use DRF page-number pagination.
- Auth tokens: short-lived JWT access + rotating blacklisted refresh; `cv` claim = `User.credential_version`.
- Tests: pytest-django; SQLite in-memory for speed. **Postgres-specific behaviour (row locks, RLS) must be tested against Neon/Postgres before phases 4, 7, 9, 10 are called done.**

## Roadmap
Phases 1–14 as in the project brief. See IMPLEMENTATION_PROGRESS.md for status.

## Website builder, website contact and maps

- `apps/website` stores saved pages (`SitePage`) and contact form messages (`ContactMessage`). A null tenant means the main website.
- Content is cleaned on the server (`content.py`): fixed section types, layouts, animations and 3D models, size limits and safe links only. The only text formatting is `**bold**`, bullet lines and paragraphs; no HTML is rendered.
- Until a page is saved, the website shows the starting content in `frontend/src/lib/pages.ts`.
- **Website content** is available to the platform admin (`/platform/website`) and to pharmacy staff with `settings.manage`. **Website contact** needs `engagement.manage` for pharmacy staff.
- Maps are Google Maps embeds with a directions link. They use a branch's coordinates when set, otherwise its written address. A searched address can be less accurate than coordinates.
