# API Documentation (through Phase 2)



Interactive OpenAPI: `/api/docs/` (schema at `/api/schema/`). Base path `/api/v1/`. Errors use

`{"success": false, "error": {"code", "message", "details"}}`. Lists are page-number paginated (`?page=`), with `?search=`, `?ordering=` and field filters.

Send `X-Tenant-Slug: <slug>` for pharmacy-scoped login and public calls; it is only a hint for authenticated users.



## auth/

`POST login/` · `POST refresh/` · `POST logout/` · `GET me/` · `POST change-password/` · `POST accept-invitation/` ·

`POST password-reset/` (always 204) · `POST password-reset/confirm/` `{uid, token, new_password}`



## platform/ (platform admin only)

- `GET /dashboard/` — counts, revenue, registration trend, health, recent activity

- `GET|POST /pharmacies/` (multipart accepted for `logo`) · `GET|PATCH /pharmacies/{id}/` · `GET /pharmacies/{id}/overview/`

- `POST /pharmacies/{id}/suspend|activate/` `{reason}`

- `GET|POST /billing/plans/` · `GET /billing/invoices/` · `POST /billing/invoices/issue/` `{pharmacy, plan}`

- `POST /billing/invoices/{id}/pay/` `{payment_method, payment_reference}` (reference must be unique)

- `POST /billing/invoices/{id}/refund/` `{amount, reason}` · `POST /billing/invoices/{id}/void/` · `GET /billing/revenue/`



## public/ (no auth)

`GET platform/` (name, WhatsApp number, contact email) · `GET plans/` (active plans) · `GET pharmacies/{slug}/` (branding of ACTIVE pharmacies only)



## audit-logs/

`GET /` — platform admins see all (`?tenant=`), tenant users with `audit.view` see their tenant (branch-scoped users only their branch).



## Email

Transactional email goes through `apps.notifications.services.send_email` (async via Celery, `EmailLog` per attempt, body not stored).

Brevo is used when `BREVO_API_KEY` is set; otherwise the Django email backend. **Brevo delivery is unverified (mock-tested only).**



## Pharmacy admin (Phase 3; tenant users, permission-gated, branch-scoped where the role is branch-scoped)

- `GET|POST /branches/` (`branch.view` / `branch.manage`) · `GET|PATCH /branches/{id}/` · codes unique per pharmacy; manager must belong to the pharmacy

- `GET|POST /staff/` (`staff.view` / `staff.manage`) · `GET|PATCH /staff/{id}/` · `use_invitation` (default true) or temporary password; role/branch validated inside the caller's pharmacy

- `GET /roles/` · `PATCH /roles/{id}/` (`role.manage`) · admin role immutable; editors can only grant permissions they hold; saving revokes sessions of role holders

- `GET|PATCH /tenants/me/` (`settings.manage` to write) · caller's own pharmacy; slug/status/name/country not editable

- `GET /tenants/dashboard/` · branch/employee/pharmacist/customer counts only (other metrics arrive with their modules)



Anti-escalation: a user can only assign roles whose permissions are a subset of their own (only a pharmacy admin may assign `pharmacy_admin`),

cannot edit users with more access, and cannot change their own role/branch/status.


## Medicines & inventory (Phase 4)
- `GET|POST /categories/`, `PATCH|DELETE /categories/{id}/` (defaults protected) · `GET|POST /medicines/` (stock = derived saleable qty), `GET|PATCH /medicines/{id}/`,
  `POST /medicines/{id}/archive|restore/` (archive blocked while stock exists), `GET /medicines/barcode/{code}/`
- `GET /batches/` (filters: branch, medicine, status, expiry_date__lte/gte) · `POST /batches/{id}/adjust|write-off|status/`
- `GET /inventory/overview|alerts|valuation|movements/` · `POST /inventory/receive|recall/` · `GET|POST /inventory/transfers/`
Permissions: `medicine.view/manage`, `inventory.view/manage`; branch-scoped users only see and act on their own branch (other branches' rows are 404/403).

## Procurement (Phase 5)
- `GET|POST /suppliers/`, `GET|PATCH /suppliers/{id}/` (`payment_details` only for `procurement.manage`)
- `GET|POST /procurement/requisitions/` (+ `{id}/submit|approve|reject|cancel/`) — approve/reject need `procurement.approve`; no self-approval
- `GET|POST /procurement/orders/`, `GET /orders/{id}/`, `POST /orders/{id}/submit|approve|reject|cancel/` — total above tenant setting `po_approval_threshold` (default 1000) needs approval; creators cannot approve their own orders
- `GET|POST /procurement/goods-receipts/` — partial deliveries; creates batches via inventory; cannot exceed ordered quantity; all-or-nothing
- `GET|POST /procurement/invoices/`, `POST /invoices/{id}/pay/` (`accounting.manage`), `GET /procurement/supplier-balances/` — pharmacy-level staff only
- `GET|POST /procurement/returns/` — returns stock to supplier (ledger movement `purchase_return`)
Document numbers: `REQ|PO|GRN-<year>-<5 digits>`, per pharmacy, row-locked sequence.

## Prescriptions (Phase 6)
- `GET|POST /patients/`, `GET|PATCH /patients/{id}/` (`prescription.view` / `prescription.register`)
- `GET|POST /prescriptions/`, `GET /prescriptions/{id}/` (each detail view is audited), `GET|POST /prescriptions/{id}/document/` (authorized download / validated upload)
- `POST /prescriptions/{id}/start-review|recheck-safety|approve|reject|cancel/` (`prescription.verify`), `POST .../refill/` (`prescription.dispense`)
- `POST /prescriptions/{id}/alerts/{alert_id}/acknowledge/` (decision note required) · `POST /prescriptions/{id}/interventions/`
- `POST /dispensing/prescriptions/{id}/` `{lines:[{item, quantity}], notes}` (`prescription.dispense`)
- `GET|POST /interaction-rules/`, `PATCH|DELETE /interaction-rules/{id}/` (pharmacy-entered interaction knowledge) · `GET /controlled-register/`

## POS and sales (Phase 7)
- Shifts: `POST /shifts/open/`, `GET /shifts/current/`, `GET /shifts/`, `GET /shifts/{id}/`, `POST /shifts/{id}/close/`, `POST /shifts/{id}/cash-movements/`, `POST /cash-movements/{id}/approve|reject/` (`sales.refund`)
- POS: `GET /pos/products/?search=|barcode=`, `GET /pos/pending-dispensings/`, `GET /pos/dashboard/`
- Sales: `GET|POST /sales/` (POST needs `Idempotency-Key`), `GET /sales/{id}/`, `POST /sales/{id}/payments/`, `POST /sales/{id}/return|cancel/` (`sales.refund`)
- Receipts: `GET /sales/{id}/receipt/`, `GET /sales/{id}/receipt/pdf/`, `POST /sales/{id}/receipt/email/`

## Online pharmacy (Phase 8)
Public (no auth): `GET /public/pharmacies/{slug}/catalogue|categories|branches/`, `GET /public/menu/{token}/`, `GET /public/menu/{token}/catalogue/`, `POST /public/menu/{token}/requests/` (throttled, honeypot).
Customer (send `X-Tenant-Slug`): `POST /shop/register/` (terms required), `POST /shop/google/`, `POST /shop/verify-email/`, `POST /shop/resend-code/`, `GET|PATCH /shop/me/`,
`GET|POST /shop/orders/` (POST needs `Idempotency-Key`), `GET /shop/orders/{id}/`, `POST /shop/orders/{id}/cancel|request-refund/`, `POST /shop/orders/{id}/prescription/` (multipart).
Staff (`order.manage`, branch-scoped): `GET /orders/`, `GET /orders/{id}/`, `POST /orders/{id}/transition/`, `GET /qr-requests/`, `POST /qr-requests/{id}/status/`; `GET /branches/{id}/qr/` (PNG, `branch.view`).

## Payments, receipts and real-time (Phase 9)
- Webhook (public, signed): `POST /webhooks/monime/` (header `Monime-Signature`; the older `/webhooks/monime/{slug}/` still works)
- Customer: `POST /shop/orders/{id}/pay/`, `GET /shop/orders/{id}/payments/`, `GET /shop/orders/{id}/receipt/` and `/receipt/pdf/`, `GET /shop/payments/`
- Staff: `GET|PUT /payments/config/` (`settings.manage`; secrets write-only), `GET /payments/attempts/` (`order.manage`), `POST /payments/reconcile/` (`accounting.manage`), `GET /payments/reconciliation/` (`accounting.view`),
  `GET /orders/{id}/receipt/` and `/receipt/pdf/`, `POST /orders/{id}/refund/` (`sales.refund`)
- WebSocket: `/ws/notifications/` (first message `{type:"auth", token}`); see PAYMENT_INTEGRATION.md

## Accounting (Phase 10)
- Chart: `GET|POST /accounting/accounts/`, `PATCH /accounting/accounts/{id}/` (custom accounts only)
- Journal: `GET|POST /accounting/journal-entries/` (POST: balanced lines, optional `Idempotency-Key`), `GET /accounting/journal-entries/{id}/`, `POST /accounting/journal-entries/{id}/reverse/` (manual/expense entries only)
- Expenses: `GET|POST /accounting/expenses/`, `POST /accounting/expenses/{id}/reverse/`
- Daily close: `GET|POST /accounting/closes/`
- Reports (`?date_from=&date_to=&as_of=&branch=`): `/accounting/reports/trial-balance|income-statement|balance-sheet|cash-flow|branch-summary|receivables|payables|integrity/`, `/accounting/reports/general-ledger/{code}/`
Permissions: `accounting.view` / `accounting.manage` (admin, accountant); branch managers get branch-scoped income statement and branch summary via `report.view`.

## HR and payroll (Phase 11)
- HR (`hr.view` / `hr.manage` / `hr.sensitive`, branch-scoped): `GET|POST /hr/staff/`, `GET|PATCH /hr/staff/{user}/`, `POST /hr/staff/{user}/terminate/`, `GET|POST /hr/staff/{user}/documents/`, `GET /hr/documents/{id}/download/`, `GET|POST /hr/staff/{user}/disciplinary/`,
  `GET /hr/attendance/`, `POST /hr/attendance/manual/`, `GET|POST /hr/shifts/`, `GET|POST /hr/leave-types/`, `GET /hr/leave/`, `POST /hr/leave/{id}/approve|reject/`
- Self-service (any staff, own data only): `POST /hr/attendance/clock-in|clock-out/`, `GET|PATCH /hr/me/`, `GET /hr/me/attendance|shifts/`, `GET|POST /hr/me/leave/`, `POST /hr/me/leave/{id}/cancel/`, `GET /hr/me/salary/`, `GET /hr/me/payslips/`, `GET /hr/me/payslips/{id}/` and `/pdf/`
- Payroll (`payroll.view` / `payroll.manage` / `payroll.approve`): `GET|PUT /payroll/config/`, `GET|POST /payroll/components/`, `GET|POST /payroll/structures/`, `GET|POST /payroll/adjustments/`, `GET|POST /payroll/advances/` (POST: approver),
  `GET|POST /payroll/runs/`, `GET /payroll/runs/{id}/`, `POST /payroll/runs/{id}/recalculate|submit|cancel|approve/`, `POST /payroll/lines/{id}/pay/`, `GET /payroll/lines/{id}/payslip/` and `/pdf/`

## Reports, services, engagement, delivery (Phase 12)
- Reports: `GET /reports/`, `GET /reports/{slug}/?date_from&date_to&branch&group&search&ordering&page&page_size[&export=csv|xlsx|pdf]`, `GET /reports/dashboard/`
- Services: `GET|POST /services/`, `PATCH /services/{id}/` (`service.manage`), public `GET /public/pharmacies/{slug}/services/`
- Appointments: customer `GET|POST /shop/appointments/`, `POST /shop/appointments/{id}/cancel/`; staff (`engagement.manage`) `GET /appointments/`, `POST /appointments/{id}/status/`
- Enquiries/feedback: customer `GET|POST /shop/inquiries/`, `GET|POST /shop/feedback/`; staff `GET /inquiries/`, `POST /inquiries/{id}/respond/`, `GET /feedback/`, `POST /feedback/{id}/respond/`
- Institutional: public `POST /public/pharmacies/{slug}/institutional-requests/`; staff `GET /institutional-requests/`, `POST /institutional-requests/{id}/respond/`
- Delivery: `GET|POST /deliveries/`, `GET /deliveries/drivers/` (`delivery.manage`); drivers `GET /deliveries/mine/`, `POST /deliveries/{id}/pickup|deliver|fail/` (`delivery.perform`); customer `GET /shop/orders/{id}/delivery/`

## Backups and health (Phase 13)
- Platform administrators only: `GET|POST /platform/backups/`, `GET /platform/backups/health/`, `POST /platform/backups/{id}/verify/`, `GET /platform/backups/{id}/download/` (encrypted object), `GET|POST /platform/restores/`, `POST /platform/restores/{id}/approve|reject|execute/`
- Load balancer probes (no auth, no data): `GET /health/live/`, `GET /health/ready/`

## Account, notifications, customers, analytics and mobile money
- `PATCH /auth/me/profile/`, `POST|DELETE /auth/me/avatar/`, `POST /auth/me/email/` then `/auth/me/email/confirm/`
- `GET /notifications/`, `GET|DELETE /notifications/{id}/`, `POST /notifications/{id}/read/`, `POST /notifications/read-all/` (own only)
- `GET /customers/`, `GET|PATCH /customers/{id}/` (`customer.view` / `customer.manage`)
- `GET /analytics/?days=` (sections depend on the caller's permissions), `GET /analytics/platform/` (platform admins)
- `GET /shop/summary/`, `POST /shop/orders/{id}/payments/refresh/`
- `GET /payments/status/`, `GET|POST /payments/mobile-money/`, `GET /payments/mobile-money/{id}/`, `POST /payments/mobile-money/{id}/cancel/` (`pos.sell`)
- `GET /subscription/`, `POST /subscription/invoices/{id}/pay/`, `POST /subscription/invoices/{id}/refresh/` (`settings.manage`)
- Removed: `GET|PUT /payments/config/`
