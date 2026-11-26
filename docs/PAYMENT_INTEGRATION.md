# Payment integration (Monime) and real-time updates

**Status:** request and webhook formats were checked against Monime's OpenAPI document (release `caph.2025-08-23`). The configured token and space id
were accepted by a read-only API call. No checkout, payment code or webhook has yet completed against Monime with real money: test one small payment of
each kind before relying on it.

## Configuration (environment only)
`MONIME_SPACE_ID`, `MONIME_ACCESS_TOKEN`, `MONIME_WEBHOOK_SECRET` (`MONIME_API_KEY` is still read as an alias of the token). Nothing is entered in the app
and no API returns these values. **One Monime space serves the whole platform: money from every pharmacy arrives in that account.** Settling each
pharmacy's share is done outside the system.

Webhook to create in the Monime dashboard: `https://<host>/api/v1/webhooks/monime/`, HMAC (HS256) with the same secret, events
`checkout_session.completed|cancelled|expired` and `payment_code.processed|completed|expired|cancelled`.

## Where mobile money is used
| Area | Monime feature | How it is confirmed |
|---|---|---|
| Online orders | Checkout session | Webhook, the customer's order page, or "Check pending payments" |
| Point of sale (and balance payments on a sale) | One-time USSD payment code | The till polls until Monime reports it paid; the sale accepts only that verified, unused reference for exactly that amount and branch |
| Subscription invoices (SLE or USD) | Checkout session | Webhook or the Subscription page |

Supplier payments, salaries, expenses and refunds are **records of payments made outside the system**. No payouts are sent.

## Rules
* A redirect or a webhook body is never proof: the server fetches the object from Monime and applies that answer, once.
* Idempotency keys include the pharmacy, because payment numbers repeat between pharmacies.
* If a customer pays but the sale then fails, the money appears as "received, not yet used" at that branch and on the Online payments page.
* On Render's free plan there is no background worker, so scheduled reconciliation does not run. Webhooks, the open order/till screens and the manual
  check cover this.

## Real-time updates
`/ws/notifications/` (first message carries the access token). Events carry only identifiers; the browser refetches through the REST API. Stored
notifications (`/api/v1/notifications/`) are private to their recipient and are pushed to that user's channel as they are created.
