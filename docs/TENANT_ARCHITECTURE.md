# Tenant Architecture

**Model:** shared database, shared schema, `tenant_id` on every tenant-owned row. The tenant is `tenants.Pharmacy`.

## Layers of isolation
1. **Identity binding** — an authenticated tenant user's tenant is *always* `user.tenant`. Header/subdomain/domain values are
   hints only; a hint that names a different tenant gets 403 (`TenantContextMixin`). Platform admins (tenant = NULL,
   enforced by a DB CHECK constraint) must pass an explicit hint to act inside a tenant.
2. **Queryset layer** — `TenantOwnedModel.objects` is a `TenantManager` that filters by the context tenant and
   **returns nothing when there is no context** (fail closed). `all_objects` and `unscoped()` are explicit escape hatches
   for platform/system code and are greppable.
3. **Write layer** — `TenantOwnedModel.save()` auto-fills the tenant from context and raises if a different tenant is supplied.
4. **Permission layer** — RBAC codenames (default deny) plus branch scoping (`User.is_branch_scoped`).
5. **Planned: PostgreSQL Row-Level Security** — policies on tenant tables keyed on `current_setting('app.tenant_id')`, set per
   transaction. *Not yet implemented*; with Neon's pooled (PgBouncer transaction mode) endpoint it must use `SET LOCAL` inside the
   request transaction (`ATOMIC_REQUESTS` is on). Tracked for Phase 14 hardening.

## Tenant resolution
Order: `X-Tenant-Slug` header (SPA on `/pharmacy/<slug>`), subdomain of `PLATFORM_BASE_DOMAIN`, then `Pharmacy.custom_domain`
(column exists, unique; DNS/TLS provisioning is future work). Reserved slugs are rejected.

## Suspension
`status != active` ⇒ login refused (403 `tenant_inactive` after correct credentials), existing tokens rejected (401) on the next
request, anonymous public-site resolution returns no tenant. Reactivation restores access.

## Rules for new tenant-owned models
Inherit `TenantOwnedModel`; add `UniqueConstraint(fields=["tenant", ...])` instead of global uniques; index `(tenant, ...)`;
never accept `tenant`/`tenant_id` from request bodies (field is `editable=False`); add an isolation test.
`accounts.User` and `accounts.Role` are tenant-linked but use plain managers — always filter by tenant explicitly in selectors.
