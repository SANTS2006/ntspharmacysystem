# Payment Integration (Monime) and Real-time

**Status: implemented and tested ONLY against mocked Monime responses. It has never been run against Monime with real credentials. Do not claim it works in production until a test-mode end-to-end payment has been completed.**

## Sources and unverified details
Implemented from Monime's developer documentation (docs.monime.io): `POST /v1/checkout-sessions` and `GET /v1/checkout-sessions/{id}` on `https://api.monime.io`, headers `Authorization: Bearer`,
`Monime-Space-Id`, `Idempotency-Key`, and webhooks signed with `Monime-Signature: t=<unix>,v1=<base64 HMAC-SHA256 of "<t>_<raw body>">` (5 min past / 1 min future tolerance). The documentation was read through
extracted summaries, so these must be re-checked against the OpenAPI file (`https://docs.monime.io/apis/openapi/caph-2025-08-23.json`) before go-live:
the `lineItems` schema we send, the minor-unit rule (we send `value = amount × 100` for SLE/USD), session-id prefixes, the exact `status` values, and whether `lineItems` is echoed on retrieval
(amount cross-checks are skipped if it is not). Gateway refunds and a single-payment lookup were not found in the docs and are not integrated.

## Per-pharmacy credentials
Money must reach the pharmacy, so each pharmacy configures its own Monime space (`/payments/config/`, `settings.manage`): space id, access token and webhook secret. Tokens/secrets are encrypted at rest
with Fernet (`FIELD_ENCRYPTION_KEY`, required when `DEBUG` is off), are write-only (never returned or logged), and blank updates keep the stored value. The webhook URL is per pharmacy:
`/api/v1/webhooks/monime/<slug>/`, so the correct secret is known before the body is trusted.

## Flow
1. Customer places an order with `payment_method: "monime"` (allowed only when the pharmacy has enabled and fully configured the provider).
2. `POST /shop/orders/{id}/pay/` creates a `PaymentAttempt` (unique `PAY-` reference, used as the provider `reference` and `Idempotency-Key`), creates the checkout session, returns `redirect_url`. An open checkout is reused.
3. The customer pays on Monime's page and is redirected back. **The redirect proves nothing**: the order page only shows "confirming" and polls.
4. Monime calls the webhook. We verify the HMAC over the **raw** body in constant time with replay-window checks, record the event id (duplicates are acknowledged and ignored), then **fetch the session from Monime server-to-server**; the provider's status
   (and amount, when echoed) decides. Only `completed` confirms the payment; the order moves to `payment_confirmed` through the normal workflow, a permanent receipt is created (`RC-...`), and payment-confirmation and receipt emails are queued (Brevo when configured).
5. `cancelled` / `expired` mark the attempt, email the customer, and leave the order payable again (new attempt).
6. Provider unreachable during a webhook: HTTP 503 and the event is not recorded, so Monime's retry is processed. Invalid signature: 400 and nothing is read from the body. Unknown pharmacy: 404.
7. A payment that completes after the customer cancelled is recorded and flagged `needs_refund` (never silently dropped); it appears in the reconciliation report.

**Reconciliation.** `POST /payments/reconcile/` (`accounting.manage`) and the Celery beat task `apps.payments.tasks.reconcile_all` (every 10 min) ask the provider about attempts still pending; `GET /payments/reconciliation/` summarises statuses, stale pendings and refunds needed.
**Refunds.** Staff with `sales.refund` record refunds against orders with a refund request (`POST /orders/{id}/refund/`): partial or full, unique reference, audited, customer emailed. The money itself must be returned through Monime/the pharmacy's account; no gateway refund call exists.
Staff cannot confirm payment for provider-paid orders. Cash-on-pickup/delivery orders are confirmed by staff and also get receipts.

Not stored: card data, wallet PINs or any provider credential outside the encrypted fields.

## Real-time notifications
WebSocket `ws(s)://<host>/ws/notifications/` (Daphne/ASGI, Redis channel layer in production; in-memory otherwise, which does **not** work across processes). The client's first message `{"type":"auth","token":"<access JWT>"}` (10 s deadline) is validated like a REST request
(credential version, active user and tenant, no forced password change); platform admins have no feed. **Subscriptions are derived server-side** from tenant, branch and permissions (`order.manage` → orders/qr/payments, `prescription.view`, `inventory.view`);
branch-scoped staff only join their branch's groups, customers only their own user group. Events carry ids/status only (e.g. `order.created`, `order.updated`, `payment.confirmed`, `qr_request.created`, `prescription.updated`, `inventory.low_stock`); clients refetch details through the REST API.
The socket closes when the access token expires (the frontend reconnects with a fresh token); pages keep polling as a fallback.
Not implemented: POS sale notifications, manager approval notifications, delivery tracking, presence, load-tested WebSocket scaling.

## Notifications (Brevo path)
Order status, payment confirmed/failed, receipts, refund confirmation, email verification and daily stock alerts (`apps.inventory.tasks.send_stock_alerts`, branch managers + admins) go through the notification service (Brevo when `BREVO_API_KEY` is set, otherwise Django's backend).
**Brevo delivery itself is still unverified.** Not yet built: supplier purchase notification emails, payroll and appointment emails, WhatsApp automation.
