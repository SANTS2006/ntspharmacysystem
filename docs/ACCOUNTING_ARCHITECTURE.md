# Accounting Architecture (Phase 10)

**Principles.** Double entry: every posted entry has at least two lines and total debits = total credits (enforced in the posting engine, which refuses anything else; each line is one-sided and positive,
enforced by a DB check). Posted entries and lines are **immutable** (ORM-level; revoke UPDATE/DELETE at database level in production). Errors are corrected with **reversal entries**, never edits.
Each business event posts **once** (unique `(tenant, source_type, source_id)`). Postings run **inside the originating transaction**: if posting fails, the sale/receipt/payment rolls back, so books and operations cannot diverge (tested).
Closed days are locked: nothing can be posted dated on or before the last daily close (system postings are dated today and closing today is not allowed).

**Chart of accounts** (31 seeded lazily per pharmacy; custom accounts with a code prefix matching their type): 1000 Cash, 1010 Mobile money & gateway clearing, 1020 Bank, 1100 Receivables, 1200 Inventory,
2000 Payables, 2100 Sales tax payable, 2200 Customer prepayments, 2250 Customer refunds payable, 3000/3100 Equity, 4000 Sales, 4100 Delivery fees, 4900 Discounts (contra), 4950 Returns & refunds (contra),
5000 COGS, 5100 Inventory write-offs & adjustments, 6xxx operating expenses (salaries, rent, utilities, transport, marketing, licences, other, cash over/short, bank fees).

**Automatic postings.**
| Event | Debit | Credit |
|---|---|---|
| POS sale | Cash/Mobile/Bank per tender, Receivable for any unpaid balance, Discounts (contra) | Sales (gross), Sales tax payable; plus COGS Dr / Inventory Cr at batch cost |
| Payment on a partly paid sale | Cash/Mobile/Bank | Receivable |
| Return / cancellation | Returns (net), Sales tax payable (proportional); Inventory when restocked | Refund account; COGS when restocked |
| Goods received (GRN) | Inventory | Payables |
| Supplier payment | Payables | Cash/Bank/Mobile |
| Purchase return | Payables | Inventory (at cost) |
| Adjustment, write-off, damage | Write-offs (loss) or Inventory (gain) | Inventory or Write-offs |
| Branch stock transfer | Inventory (destination branch) | Inventory (source branch) |
| Shift close discrepancy | Cash over/short or Cash | Cash or Cash over/short |
| Cash withdrawal / deposit (approved) | Bank / Cash | Cash / Bank |
| Online order payment confirmed | Cash or Mobile money clearing | **Customer prepayments (not revenue)** |
| Online order delivered/completed | Customer prepayments | Sales, Delivery fees, Sales tax payable; COGS Dr / Inventory Cr |
| Online order refund | Returns + tax (if revenue recognised) or Prepayments | Cash/Mobile/Bank |
| Payment received for an order that can no longer accept it | Mobile money clearing | Customer refunds payable |
Cash received is separated from recognised revenue for online orders (revenue on fulfilment). Paid online orders cannot be plainly cancelled: they go through a refund request so the money is accounted for.
**Manual entries and expenses** are the only reversible entries; system entries are corrected through their business process (returns, refunds, adjustments).

**Reports** (computed from the ledger; `accounting.view`): trial balance, income statement (revenue net of discounts/returns, COGS, gross profit, operating expenses by category, net profit), balance sheet (with current-period
earnings; checks A = L + E), cash flow by source (cash + mobile money + bank), general ledger with running balance, branch financial summary, receivables (ledger vs open sales), payables (ledger vs supplier sub-ledger),
integrity check (unbalanced entries, trial balance). Branch managers (`report.view`, branch-scoped) can read **only their own branch's** income statement and branch summary. Line-level branch tagging drives branch reporting;
pharmacy-level items (e.g. supplier payments, shared expenses) appear under "Pharmacy level".

**Daily close.** `POST /accounting/closes/` for a past date: requires a balanced trial balance, stores a summary snapshot, and locks that date; closes must move forward.

## Known limitations (read before relying on these numbers)
- **Not tax or audit ready.** No VAT/GST return logic (sales tax payable is tracked, purchase-side input tax is not), no fixed assets/depreciation, no multi-currency, no budgets, no bank reconciliation, no fiscal-year closing entry.
- Events that happened **before Phase 10 are not backfilled**; opening balances must be entered as a manual journal. Stock received outside a GRN (direct receiving) has no payable/cash entry, so Inventory can show a credit balance until it is booked.
- Payables follow goods received, not supplier invoices; invoice-vs-receipt price differences are not posted. Dispensed prescription stock is expensed (COGS) when billed at the POS, so unbilled dispensings sit outside both stock and COGS.
- Online order COGS uses the stock-movement ledger; refunds restock nothing automatically. Salary/payroll postings arrive with Phase 11.
- Rounding: refunds are proportional with the last unit absorbing remainders; entries are rounded to 2 decimals, so very small differences against external statements are possible.
- Reports are JSON only; PDF/Excel export belongs to Phase 12.
- Verified on SQLite only; row locking and concurrent posting on PostgreSQL are unverified.
