# Implementation Progress

Started from an empty directory. Environment: Python 3.13, Node 26, no local PostgreSQL/Redis. Stack: Django 5.2 + DRF, React 19 + TypeScript + Tailwind 4.
**Everything below was tested on in-memory SQLite only. Nothing has been run on PostgreSQL/Neon or Redis, and no frontend page has been exercised in a browser.**
Backend tests: 218 passing. Frontend: 3 unit tests (hidden login trigger); `tsc` and `vite build` clean.

| Phase | Status | Summary |
|---|---|---|
| 1 Foundation | Done | Tenancy (fail-closed manager, identity-bound tenant), JWT auth with revocation, lockout, forced password change, invitations, RBAC registry, append-only audit |
| 2 Platform admin | Mostly done | Public site + legal drafts, platform dashboard, pharmacy registration/suspension, billing (plans, invoices, payments, refunds), Brevo/Django email with log, password reset, logo validation |
| 3 Pharmacy admin | Done (for existing modules) | Branches, staff onboarding, roles (anti-escalation), settings, branded admin shell |
| 4 Medicines & inventory | Core done | Catalogue, batches, expiry rules, FEFO, immutable ledger, adjustments, write-offs, recalls, transfers, alerts, valuation |
| 5 Procurement | Core done | Suppliers, requisitions, POs with threshold approval, GRNs (partial, atomic), supplier invoices/payments, returns |
| 6 Prescriptions | Core done | Patients, prescriptions, pharmacist review/approval, rule-based safety alerts + decisions, dispensing, refills, controlled-drug register |
| 7 POS & sales | Core done | Shifts, cash movements, sales with server-side totals, idempotency, split payments, receipts (JSON/PDF/email), returns/credit notes, cancellation, cashier dashboard |
| 8 Online pharmacy | Core done | Customer accounts + 6-char email verification, Google sign-in (backend, mocked), public catalogue, checkout, order workflow + notifications, prescription orders, QR menu + requests, branded pharmacy website pages |
| 9 Payments & real-time | Core done (Monime untested live) | Per-pharmacy encrypted Monime config, checkout sessions, verified webhooks with idempotency, provider-authoritative confirmation, reconciliation, online-order receipts, refund records, WebSocket notifications, stock-alert emails |
| 10 Accounting | Core done (not tax/audit ready) | Double-entry ledger, immutable idempotent postings from sales/returns/procurement/inventory/cash/online orders/payments, expenses, manual journals + reversals, daily close, statements, branch financials |
| 11 HR & payroll | Core done (rates are user-configured, not legal advice) | Staff records, attendance, shifts, leave, versioned salary structures, adjustments, advances, payroll runs with segregated approval, partial salary payments, payslips (JSON/PDF/self-service), ledger postings |
| 12 Reports, services, delivery | Core done | 27 reports with PDF/Excel/CSV export (audited, formula-safe), pharmacy dashboard, services + appointments, enquiries, feedback, institutional quotes, delivery management with driver workflow |
| 13 Backups & infrastructure | Core done (R2 and PostgreSQL untested live) | Encrypted, verified, retained logical backups to R2 (S3 API), two-person re-authenticated restore with safety backup, atomic load and session revocation, maintenance mode, health probes, R2 media storage switch, Redis/pool tuning, deployment guide, query-count regression tests |
| 14 | Not started | Final testing, security hardening, documentation completion |

## Phase 13 detail (latest)
App `backups` (migration `backups/0001`); new dependencies boto3, django-storages. See BACKUP_AND_RECOVERY.md and DEPLOYMENT_GUIDE.md.
**Unverified:** Cloudflare R2 (mocked client only), PostgreSQL behaviour of the restore transaction, multi-process maintenance flag (needs Redis), the R2 media storage switch (config only, no test), Neon pooling/psycopg pool settings.
Bugs found by tests: tenant-scoped managers made `dumpdata` produce EMPTY tenant tables (fixed with the base manager + unscoped); health checks returned 500 during a database outage because of ATOMIC_REQUESTS (now non-atomic, 503); a restore rolls back the audit log, so the workflow history is re-recorded in one `restore.completed` entry.
Not done: incremental / pg_dump backups, per-tenant restore, media-file backups, key rotation tooling, automatic restore drills.

## Phase 12 detail
Apps `engagement`, `delivery`, `reporting` (migrations `engagement/0001`, `delivery/0001`); new permissions `service.manage`, `engagement.manage`, `delivery.manage`, `delivery.perform` (run `manage.py sync_role_permissions`; delivery personnel now hold `delivery.perform`). New dependency: openpyxl.
See REPORTING_AND_ENGAGEMENT.md. Bugs found by tests: `?format=` is reserved by DRF (exports use `?export=`). Frontend: Overview, Reports (filters, sort, search, pagination, exports), Customers & services, Deliveries (staff + driver), public Services/booking, Bulk & institutions, Feedback pages.
Not done: GPS/proof of delivery, reminders, charts, scheduled reports, task management.

## Phase 11 detail
Apps `hr` and `payroll` (migrations `hr/0001`, `payroll/0001`); new permissions `hr.view`, `hr.manage`, `hr.sensitive` (run `manage.py sync_role_permissions` for existing pharmacies); chart of accounts gained 1150, 2300, 2310, 2320, 2330 (added automatically to existing charts).
See HR_AND_PAYROLL.md for the permission matrix, calculation rules and the (long) not-implemented list. Frontend: My work (everyone), Human resources, Payroll pages.
No payroll or tax law is built in: pension percentages and tax brackets are entered by the pharmacy and must be verified with an accountant. Verified on SQLite only.

## Phase 10 detail
App `accounting` (migration `accounting/0001`); postings are hooked into sales, procurement, inventory, shop and payments services (see ACCOUNTING_ARCHITECTURE.md for the posting table and limitations).
Behaviour changes: a paid online order can no longer be plainly cancelled (use a refund request); cash-on-delivery payments map to the cash account.
Bugs found by tests: first expense on a fresh pharmacy failed (chart not yet seeded); cash-on-pickup payments were mapped to the bank account.
Frontend: Accounting page (P&L, branches, balance sheet, trial balance, cash flow, journal with manual entry and reversal, expenses, daily close); branch managers see only their branch's P&L.
Not done: tax/VAT returns, depreciation, multi-currency, bank reconciliation, budgets, fiscal-year close, backfill of pre-Phase-10 data, PDF/Excel export, payroll postings, PostgreSQL concurrency verification.

## Phase 9 detail
App `payments` (migration `payments/0001`); `core.realtime`, `core.consumers`, ASGI routing; tasks `payments.reconcile_all`, `inventory.send_stock_alerts` (Celery beat schedule added). See PAYMENT_INTEGRATION.md.
**The Monime integration was built from documentation summaries and mocked tests; it has never talked to Monime.** Several request/response details are flagged there for verification.
Frontend: online-payment choice at checkout, Pay now + receipt on order page, staff Online payments page (config, reconciliation, attempts), refund/receipt actions, live updates via WebSocket with polling fallback.
Tests found two real bugs: receipts were built before the completed attempt was saved, and test settings needed an encryption key (production requires one by design).
Not done: gateway refunds, Monime payment codes/USSD, POS/manager real-time events, delivery tracking, supplier/payroll/appointment emails, WhatsApp automation, WebSocket load testing, multi-process verification of the channel layer on Redis.

## Phase 8 detail
App `shop` (migrations `shop/0001`, `tenants` qr_token). New default permission `order.manage` (cashier, branch manager); run `manage.py sync_role_permissions` for existing pharmacies.
Bugs found by tests: verification attempt counters were rolled back by ATOMIC_REQUESTS when failures were raised (now returned); error codes now carry the specific code (e.g. `email_not_verified`).
Frontend: pharmacy website (`/pharmacy/:slug`: home, products, register/login/verify, checkout, orders, order detail with prescription upload, QR menu) and staff Online orders page. See ONLINE_PHARMACY_WORKFLOW.md.

## Phase 7 detail
App `sales` (migration `sales/0001`). New default permission: `pos.sell` for branch managers (run `manage.py sync_role_permissions` for existing pharmacies).
Frontend: Point of sale page (shift, search/barcode, cart, split tender, receipt, history, returns/cancel). See POS_AND_SALES_WORKFLOW.md.
Not done: see that document (gateway-confirmed payments, accounting postings, held/parked carts, customer accounts, camera scanning, reports, thermal-printer layout, modal dialogs instead of prompts).

## Known gaps across the project (honest list)
- PostgreSQL concurrency/row-lock behaviour, RLS, Redis, Celery workers and Brevo live delivery are unverified.
- Brevo is mock-tested only; Monime, Google OAuth, WhatsApp automation, Cloudflare R2, backups, WebSockets are not implemented.
- No double-entry accounting yet: invoices, payments, sales and refunds are recorded operationally and will be posted to journals in Phase 10.
- Licensed drug-interaction data, age/dosage rules are not available; safety checks are rule-based over pharmacy-entered data.
- Many secondary dialogs use browser `prompt()`/`confirm()`; they should become accessible modals. Only the hidden-trigger component has frontend tests.
- Legal pages are draft templates needing legal review. No git repository; no CI; no dependency audit yet.
- A stray test run once created `test_neondb` on the Neon project (the real `neondb` was untouched). Tests are now pinned to SQLite via `config/settings_test.py`.

## Next
Phase 14: PostgreSQL verification (run everything on Neon), concurrency drills, security review (dependency audit, CSP, RLS decision), remaining docs (DATABASE_SCHEMA, INVENTORY/PRESCRIPTION workflows exist), frontend tests, and a launch checklist.
