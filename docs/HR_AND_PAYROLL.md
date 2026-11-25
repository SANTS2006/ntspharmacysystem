# HR and Payroll (Phase 11)

**Confidentiality model.** Salary data is the most sensitive data in the system. Access is permission-gated on the server and branch-scoped; every payslip view, document download and disciplinary-record view is audited;
audit entries for salary changes record *who changed whose pay and when* but **never the amounts**; payslip emails say that a slip is available and contain no figures; payslip PDFs are served `private, no-store`.

| Who | Can |
|---|---|
| Any staff member | Clock in/out, see their own attendance, shifts, leave balances and requests, own salary structure, own payslips (approved/paid runs only), update their phone, address and emergency contact |
| Branch manager (`hr.view/manage`, `payroll.view`) | See and manage HR records, attendance, schedules and leave **for their own branch only**; view branch staff salary structures and payslips; never create runs or change pay |
| HR manager (`hr.*`, `payroll.view/manage`) | Staff records, terminations, documents, disciplinary records (`hr.sensitive`), salary structures, adjustments, payroll runs (create/recalculate/submit/cancel), record salary payments |
| Pharmacy admin (`payroll.approve`) | Approve payroll runs (never their own), grant salary advances |
| Accountant | Reads the resulting ledger entries; no access to individual salaries |

**Staff records.** Staff ID (auto `STF-YYYY-NNNNN` or manual, unique), employment date and status, job title, department, contacts. Ending employment (needs `hr.sensitive`, reason required) deactivates the account and revokes every session immediately.
Documents (PDF/PNG/JPG/WebP, magic-byte checked, 5 MB) and disciplinary records (append-only: no edit, no delete) are `hr.sensitive` only.

**Attendance.** Self clock-in/out once a day (late if after `workday_start` + `late_grace_minutes`, both tenant settings), manager corrections are marked `manual` and audited; no future dates. Work shifts reject overlaps.
**Leave.** Per-pharmacy leave types (defaults: annual 21 paid, sick 10 paid, unpaid), allowance checks including pending requests, overlap prevention, nobody decides their own request, managers decide only their own branch, staff can cancel before the leave starts.

**Salary structures** are versioned and immutable (a raise is a new version with an effective date); components are configurable (earning/deduction, fixed or % of basic, taxable or not).
**Statutory rates are NOT built in**: the pharmacy enters employee/employer pension percentages and progressive monthly tax brackets (`/payroll/config/`, validated). Nothing here encodes Sierra Leone (or any) tax or pension law; check the figures with an accountant.

**Calculation (per person, per month).** Basic is prorated for joining/leaving mid-month and reduced for approved *unpaid* leave days; allowances follow the same proration (percent components use the prorated basic); bonuses, commissions and overtime come from adjustments for that period;
gross = basic + allowances + extras. Employee pension = % of basic; taxable income = taxable earnings − employee pension (assumption: pension is deductible); tax is progressive over the configured brackets; other deductions and advance recoveries are capped so net pay is never negative (with a warning on the line).

**Workflow.** Draft (recalculable) → submitted → approved (by someone other than the creator; locks the run, consumes advance balances, posts to the ledger) → paid. One live run per period and scope (pharmacy or branch); post-approval changes are impossible (cancel is refused; corrections go in the next period).
**Payments** are recorded per person (partial allowed, unique reference, over-payment refused); the run becomes `paid` when every line is settled. **Advances** are paid out by an approver, recovered automatically up to the monthly amount, and cleared when the balance reaches zero.

**Accounting.** Approval: Dr Salaries & wages (gross + employer pension) / Cr Salaries payable (net), Payroll tax payable, Pension payable (employee + employer), Other deductions payable, Staff advances (recoveries), tagged per employee branch.
Payment: Dr Salaries payable / Cr cash, bank or mobile money. Advance payout: Dr Staff advances / Cr cash or bank.

## Not implemented
Tasks, performance dashboards and staff-performance reports, profile-picture upload and profile-change *requests* (staff edit allowed fields directly), overtime-from-attendance calculation (overtime is entered as an adjustment), leave carry-over and public holidays, termination/final-pay settlement, payroll for part-month terminations beyond the proration above, bank payment files, statutory filings, PDF payroll register export (Phase 12), notification emails for leave decisions, UI for documents/disciplinary records and shift scheduling (API only), multi-component editing in the UI (API supports it). Verified on SQLite only.
