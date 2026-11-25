# Online Pharmacy Workflow

**Accounts.** Customers register on a pharmacy site (tenant from `X-Tenant-Slug`); terms acceptance and its version (`TERMS_VERSION`) are stored. A six-character code
(alphabet without look-alike characters) is emailed; only a salted hash is stored, it expires (15 min), resend has a cooldown (60 s), five wrong attempts lock it until a new
code is requested, and a used code is consumed. **Verification attempts are returned, not raised, because an exception would roll back the request transaction and discard the counter.**
Unverified customers can sign in but every protected customer endpoint answers `email_not_verified`. Duplicate-email registration gives a vague message (no account enumeration).
Google sign-in verifies the ID token with Google's tokeninfo endpoint (audience, issuer, verified email); **new** accounts require `terms_accepted: true`, existing customers sign in without it;
staff emails are refused. It needs `GOOGLE_OAUTH_CLIENT_ID` and **has only been tested with a mocked verifier; the Google button is not in the UI yet.**

**Catalogue.** Public and read-only: active, online-visible, non-controlled medicines with a per-branch availability flag; no cost or regulatory fields. Prescription-only items are labelled.

**Orders.** Prices, tax and delivery fee are computed by the server; `Idempotency-Key` is mandatory. Payment is **pay on pickup / pay on delivery only**; online/mobile-money payment is rejected until Phase 9.
Status flow (default, overridable per pharmacy through `settings.order_transitions`): pending -> awaiting_prescription | awaiting_payment -> payment_confirmed -> processing -> preparing -> ready_for_pickup | out_for_delivery -> delivered -> completed,
with cancelled, refund_requested and refunded. Customers can cancel only before payment is confirmed and request refunds after fulfilment; some statuses are set only by the workflow itself.
Staff cannot assert payment for provider-paid orders. Stock is committed (FEFO) when an order reaches *processing*; there is no reservation at checkout, so availability is re-checked then and can fail.
Every change is an immutable event and emails the customer (unless they opted out).

**Prescription orders.** The customer uploads a validated file; a `received` prescription is created for pharmacist review (Phase 6). The pharmacist's approval/rejection moves the order automatically.
Processing is blocked until the pharmacist has dispensed. Uploading a file alone never authorizes anything.

**QR menu.** Each branch has an unguessable token (`/pharmacy/{slug}/menu/{token}`) and a PNG QR code for staff. Visitors browse and submit a *request* (throttled, honeypot, rate-limited by IP scope `public_write`);
requests appear for branch staff with prescription warnings. A request is neither an order nor a sale.

**Not implemented.** Online payments, receipts/invoices for online orders and accounting (Phases 9-10), real-time staff notifications and WebSockets (staff screens poll every 20 s), delivery personnel assignment and tracking,
reservations, stock-aware cart totals, customer-facing prescription refill requests, the Google button, product images, SEO/server rendering for pharmacy sites, QR-request-to-order conversion (staff re-enter items in POS), customer payment history.
