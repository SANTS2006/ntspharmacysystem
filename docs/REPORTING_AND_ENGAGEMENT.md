# Reporting, Services, Appointments and Delivery (Phase 12)

## Reports (`/api/v1/reports/`)
One engine, 27 reports in 6 groups (sales, inventory, procurement, prescriptions, financial, staff & branches). `GET /reports/` lists what the caller may run;
`GET /reports/{slug}/` takes `date_from`, `date_to`, `branch`, `group` (day/week/month/year), `days` (near-expiry horizon), `search` (any text column), `ordering` (`col` or `-col`, validated against the report's columns), `page`, `page_size` (max 200).
**Exports** use `?export=csv|xlsx|pdf` (not `format`, which DRF reserves). Exports are capped at 20,000 rows, sent `private, no-store`, **audited (`report.exported` with report, format, row count)**, and cells that start with `= + - @` are prefixed with `'` so a malicious product or customer name cannot run as a spreadsheet formula.
Access: `report.view` for operational reports, `accounting.view` for profit & loss, cash flow, refunds and supplier balances, `hr.view` for attendance, `payroll.view` for payroll totals. Branch-scoped users are forced onto their own branch (another branch returns 403), including payroll totals.
`GET /reports/dashboard/` is the pharmacy overview: people, medicines (low/out of stock, expiring, expired, stock value), net sales today / this month / in range, revenue, gross profit, expenses, estimated net profit, purchases received, supplier balances (pharmacy level only), returns & refunds, prescriptions by status, open and completed online orders, payment breakdown, branch and cashier performance.

Report notes: sales reports are **POS sales** (online orders appear in "Online orders by status" and, once fulfilled, in the ledger-based financial reports); product/category revenue is tax-inclusive line totals; "net sales" subtracts POS refunds in the period (online-order refunds appear in the refunds report and the ledger);
inventory reports reflect saleable stock only (expired/recalled/quarantined stock is reported separately); stock-movement style reports are capped at 5,000 rows.

## Services and appointments
Pharmacies define services (name, description, image, price or "ask", availability, booking required, duration, capacity per slot, branches). The public site lists available services. Verified customers book services that require booking:
future (15 min–90 days), within the branch's `operating_hours` when configured, at a branch that offers the service, never beyond slot capacity (the service row is locked while booking) and never overlapping their own appointments.
Staff (`engagement.manage`, branch-scoped) confirm, cancel, complete (only after the start time) or mark no-show; customers get emails on request/confirmation/cancellation and may cancel up to one hour before.

## Enquiries, feedback, institutional requests
Verified customers send enquiries (general, medicine availability, home-delivery request) and feedback (1–5, optionally tied to one of their orders, once per order); staff reply (customer is emailed) and see the average rating.
Organisations submit quotation / bulk requests through a public form (rate-limited, honeypot); the contact is emailed an acknowledgement, staff review and send a quotation (emailed), then close. Requests are visible to branch staff for their branch or unassigned.

## Delivery management
Staff with `delivery.manage` assign a `delivery_personnel` user **of the order's branch** to a delivery order that is being prepared (reassigning cancels the previous assignment). Drivers (`delivery.perform`) see only their own active deliveries with address, customer phone and the cash-on-delivery amount to collect, and can mark picked up (moves the order to out-for-delivery), delivered (moves it to delivered), or failed with a reason (the order stays open for reassignment). Drivers have no other access.
Customers see the delivery status and the driver's first name only. Changes push real-time events (ids only).

## Not implemented
GPS tracking, proof-of-delivery photos or signatures, delivery fees by distance, appointment reminders and rescheduling, calendar views, recurring appointments, staff task assignment and performance scoring beyond cashier/attendance reports, scheduled/emailed reports, saved report filters, charts in the report pages,
product-level online sales in reports, medicine image upload UI, per-report export row streaming for very large datasets, and branded PDF layouts. Verified on SQLite only.
