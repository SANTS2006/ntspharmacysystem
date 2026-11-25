# POS and Sales Workflow

**Shift first.** A cashier must have an open shift (one per cashier, DB-enforced) before selling. Opening cash is recorded; the drawer's *expected cash* is always
`opening + cash received − cash refunds − approved withdrawals + deposits`. Deposits are immediate; withdrawals are pending until a user with `sales.refund` approves
(never the requester). Closing requires a counted amount, freezes expected cash and records the discrepancy; pending withdrawals block closing.

**Selling.** `POST /sales/` with an `Idempotency-Key` header (required). The client sends product ids, quantities, an optional discount percent and payment tenders;
it never sends prices. The server computes line gross, discount, tax (`medicine.tax_rate`, applied on the discounted net, half-up rounding) and totals. Cashiers may
discount up to `cashier_max_discount_pct` (tenant setting, default 5); more needs `sales.refund`. Stock is taken first-expiry-first-out from saleable batches inside the
same transaction, so a failure (stock, payment validation, duplicate reference) leaves no sale, payment or stock change behind. Replaying a key returns the original sale (HTTP 200).

**Prescription medicines are never rung up directly.** A pharmacist dispenses against an approved prescription (Phase 6, which deducts stock); the cashier then bills
the dispensing via `dispensing_ids`. A dispensing can be billed once; stock is not deducted a second time.

**Payments.** Cash, mobile money, card, bank transfer. Cash may exceed the amount due (change is returned; the stored cash payment is net of change). Non-cash needs a
transaction reference, cannot exceed the amount due, and a reference cannot be reused. In-store non-cash payments are confirmed by the cashier entering the terminal/provider
reference: **gateway-verified confirmation (Monime webhooks) arrives in Phase 9 and is not implemented.** Partial payment is off by default; with tenant setting
`allow_partial_payments` the sale becomes `partially_paid` (customer name required) and `POST /sales/{id}/payments/` settles it.

**Receipts.** A permanent, immutable snapshot is created with the sale (`RC-YYYY-NNNNN`): JSON, PDF (reportlab) and email (queued through the notification service).
Cashiers can only open receipts of their own sales.

**Returns, refunds, cancellation.** Completed sales are never edited. A user with `sales.refund` issues a credit note (`CN-...`) for chosen lines and quantities; refunds are
proportional per unit and the last unit absorbs rounding so the refund can never exceed what was paid. Restocking is optional, only for non-prescription lines and only into
batches that are still available/quarantined and unexpired. Cash refunds need the processor to have an open shift (they reduce expected cash). Cancelling a sale is a full return
with restock; sales containing dispensed prescription items cannot be cancelled (return them instead). Every step is audited.

**Visibility.** Cashiers (`sales.view_own`) see only their own sales, receipts and shifts and their personal dashboard (`/pos/dashboard/`). Managers (`sales.view_branch`) see their
branch; pharmacy-level roles see all branches. Other pharmacies' data is never reachable.

**Not implemented.** Accounting journal postings (Phase 10), revenue/cash reports and exports (Phase 12), held carts, customer accounts and loyalty, camera barcode scanning
(USB scanners work through the search box), thermal-printer layout, batch-level selling prices (medicine price is used), credit-note PDF.
