# Inventory Workflow

**Model.** `Medicine` (shared catalogue per pharmacy) -> `Batch` (per branch, medicine and batch number) -> `StockMovement` (append-only ledger).
Medicine "stock" is *derived* from saleable batches, never stored, so it cannot drift.

**Saleable batch** = status `available`, quantity > 0, and not past its expiry date. Expired, recalled, quarantined and damaged batches never sell;
expired stock stays on the books (shown in alerts and as unsaleable value) until written off by an explicit, audited action. Batch rows are never deleted.

**Receiving.** Expiry date required (unless the medicine is flagged no-expiry) and must be in the future. Same batch number at the same branch tops up
the batch only if the expiry matches; recalled/damaged batches cannot receive stock.

**Allocation.** `deduct_fefo` picks saleable batches by earliest expiry (FIFO by purchase date when no expiry), all-or-nothing. POS (Phase 7) will call it.

**Concurrency.** Every change goes through `_move`: row lock (`SELECT ... FOR UPDATE`) plus a conditional atomic `UPDATE ... WHERE quantity_available >= n`
and a DB CHECK constraint, so stock cannot go negative even if a lock is not honoured. **Verified only on SQLite; a multi-connection concurrency test on PostgreSQL is still required.**

**Other operations.** Adjustment (reason mandatory), write-off (expired only when past expiry; damaged), status changes (quarantine -> available allowed;
recalled/damaged terminal), pharmacy-wide recall by batch number, branch-to-branch transfer (executed atomically; no in-transit state yet).

**Not yet implemented.** Reservations, formal stocktaking sessions and reconciliation, inventory exports, scheduled/email expiry and low-stock alerts, camera barcode scanning
(USB scanners work through the search box), supplier FK on batches (Phase 5), medicine image upload UI.
