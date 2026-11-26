/** Financial statements, journal, expenses and daily close. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Banknote, CircleDollarSign, Lock, Plus, TrendingDown, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import { ChartCard, DonutChart, RankBars, TrendChart } from "../../components/charts";
import { DataTable, ErrorState, FormModal, Loading, PageHeader, StatCard, StatusBadge, Tabs, errorMessage, useConfirm, usePrompt, useToast, type FieldDef } from "../../components/ui";
import { ServerTable } from "../../components/ui/ServerTable";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { day, money, words } from "../../lib/format";

interface Account { id: number; code: string; name: string; type: string; is_active: boolean }
interface Line { name: string; code: string; amount: string }
interface Income { revenue: Line[]; net_revenue: string; cost_of_sales: Line[]; cost_of_sales_total: string; gross_profit: string; operating_expenses: Line[]; operating_expenses_total: string; net_profit: string }
interface Sheet { assets: Line[]; liabilities: Line[]; equity: Line[]; current_earnings: string; total_assets: string; total_liabilities: string; total_equity: string; balanced: boolean }
interface Tb { rows: { code: string; name: string; debit: string; credit: string }[]; total_debit: string; total_credit: string; balanced: boolean }
interface Cash { opening_cash: string; by_source: { source: string; inflow: string; outflow: string; net: string }[]; net_change: string; closing_cash: string }
interface Entry { id: number; number: string; date: string; description: string; source_type: string; total: string; reversed: boolean }
interface Expense { id: number; date: string; account_name: string; amount: string; payment_method: string; description: string; status: string }
interface BranchRow { branch: number | null; name: string; net_revenue: string; cost_of_sales: string; gross_profit: string; operating_expenses: string; net_profit: string }
type Tab = "income" | "sheet" | "tb" | "cash" | "branches" | "journal" | "expenses" | "close";
const today = () => new Date().toISOString().slice(0, 10);

function Statement({ sections, balanced }: { sections: { title: string; rows: Line[]; totals: [string, string | number][] }[]; balanced?: boolean }) {
  return (
    <div className="table-wrap"><table className="table"><thead><tr><th>Account</th><th className="text-right">Amount</th></tr></thead>
      <tbody>{sections.flatMap((s) => [
        <tr key={s.title}><td colSpan={2} className="!bg-slate-50 text-xs font-bold uppercase tracking-wider">{s.title}</td></tr>,
        ...s.rows.map((r) => <tr key={`${s.title}-${r.code}`}><td className="!pl-8">{r.code} {r.name}</td><td className="text-right tabular-nums">{money(r.amount)}</td></tr>),
        ...s.totals.map(([label, v]) => <tr key={`${s.title}-${label}`}><td className="font-bold">{label}</td><td className="text-right font-bold tabular-nums">{money(v)}</td></tr>),
      ])}</tbody></table>
      {balanced !== undefined && <p className={`m-3 alert ${balanced ? "alert-success" : "alert-error"}`}>{balanced ? "Balanced: assets = liabilities + equity." : "OUT OF BALANCE: contact support."}</p>}
    </div>
  );
}

export default function AccountingPage() {
  const prompt = usePrompt(); const confirm = useConfirm(); const toast = useToast(); const { can } = useAuth(); const qc = useQueryClient();
  const full = can("accounting.view"), manage = can("accounting.manage");
  const [tab, setTab] = useState<Tab>("income");
  const [dialog, setDialog] = useState<"expense" | "entry" | null>(null);
  const [from, setFrom] = useState(today().slice(0, 8) + "01"); const [to, setTo] = useState(today());
  const range = `date_from=${from}&date_to=${to}`;
  const done = (t: string) => { qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("acc-") }); toast(t); };
  const fail = (e: unknown) => toast(errorMessage(e), "error");
  const income = useQuery({ queryKey: ["acc-income", from, to], queryFn: () => api<Income>(`/accounting/reports/income-statement/?${range}`), enabled: tab === "income" });
  const sheet = useQuery({ queryKey: ["acc-sheet", to], queryFn: () => api<Sheet>(`/accounting/reports/balance-sheet/?as_of=${to}`), enabled: tab === "sheet" && full });
  const tb = useQuery({ queryKey: ["acc-tb", to], queryFn: () => api<Tb>(`/accounting/reports/trial-balance/?as_of=${to}`), enabled: tab === "tb" && full });
  const cash = useQuery({ queryKey: ["acc-cash", from, to], queryFn: () => api<Cash>(`/accounting/reports/cash-flow/?${range}`), enabled: tab === "cash" && full });
  const branches = useQuery({ queryKey: ["acc-branches", from, to], queryFn: () => api<BranchRow[]>(`/accounting/reports/branch-summary/?${range}`), enabled: tab === "branches" });
  const accounts = useQuery({ queryKey: ["acc-accounts"], queryFn: () => api<Account[]>("/accounting/accounts/"), enabled: full });
  const closes = useQuery({ queryKey: ["acc-closes"], queryFn: () => api<{ date: string; closed_by: string | null; summary: Record<string, string> }[]>("/accounting/closes/"), enabled: tab === "close" && full });
  const options = useMemo(() => (accounts.data ?? []).filter((a) => a.is_active), [accounts.data]);
  const accountOptions = (type?: string) => options.filter((a) => !type || a.type === type).map((a) => [a.code, `${a.code} ${a.name}`] as [string, string]);
  const reverse = async (path: string, name: string) => { const v = await prompt({ title: `Reverse ${name}`, message: "A new opposite entry is created; the original stays on record.", confirmLabel: "Reverse posting", danger: true, fields: [{ name: "reason", label: "Reason for reversing", type: "textarea" }] }); if (v) api(path, { method: "POST", body: { reason: v.reason } }).then(() => done("Reversed.")).catch(fail); };
  const closeDay = async () => { const v = await prompt({ title: "Close the books", message: "Nothing can be posted into closed dates.", confirmLabel: "Continue", fields: [{ name: "date", label: "Close books through", type: "date" }] }); if (v && await confirm({ title: `Close all books through ${v.date}?`, message: "This cannot be undone.", confirmLabel: "Close books", danger: true })) api("/accounting/closes/", { method: "POST", body: { date: v.date } }).then(() => done("Books closed.")).catch(fail); };
  const expenseFields: FieldDef[] = [{ name: "date", label: "Expense date", type: "date", defaultValue: today() }, { name: "account", label: "Expense category", type: "select", options: accountOptions("expense") }, { name: "amount", label: "Amount", type: "number", min: 0.01, step: "0.01" }, { name: "payment_method", label: "Paid from", type: "select", defaultValue: "cash", options: [["cash", "Cash"], ["bank", "Bank"], ["mobile_money", "Mobile money"]] }, { name: "vendor", label: "Vendor name", required: false }, { name: "description", label: "Description", wide: true }];
  const entryFields: FieldDef[] = [{ name: "description", label: "Description", wide: true }, { name: "date", label: "Entry date", type: "date", defaultValue: today() }, { name: "amount", label: "Amount", type: "number", min: 0.01, step: "0.01" }, { name: "debit", label: "Debit account", type: "select", options: accountOptions() }, { name: "credit", label: "Credit account", type: "select", options: accountOptions() }];
  const tabs: [Tab, string][] = [["income", "Profit & loss"], ["branches", "Branches"], ...(full ? ([["sheet", "Balance sheet"], ["tb", "Trial balance"], ["cash", "Cash flow"], ["journal", "Journal"], ["expenses", "Expenses"], ["close", "Daily close"]] as [Tab, string][]) : [])];
  const dates = (both: boolean) => <div className="flex flex-wrap items-end gap-3">{both && <label className="field-label">From<input type="date" className="mt-1.5 block" value={from} onChange={(e) => setFrom(e.target.value)} /></label>}<label className="field-label">{both ? "To" : "As of"}<input type="date" className="mt-1.5 block" value={to} onChange={(e) => setTo(e.target.value)} /></label></div>;
  const state = (q: { isLoading: boolean; isError: boolean; error: unknown; refetch: () => unknown }) => q.isLoading ? <Loading /> : q.isError ? <ErrorState onRetry={() => q.refetch()}>{errorMessage(q.error)}</ErrorState> : null;
  return (
    <div className="space-y-5">
      <PageHeader title="Accounting" subtitle={full ? "Ledger, expenses and financial statements." : "Showing your branch only."}
        actions={manage && (tab === "expenses" ? <button className="btn btn-primary" onClick={() => setDialog("expense")}><Plus size={16} aria-hidden />Record expense</button> : tab === "journal" ? <button className="btn btn-primary" onClick={() => setDialog("entry")}><Plus size={16} aria-hidden />New journal entry</button> : tab === "close" ? <button className="btn btn-primary" onClick={closeDay}><Lock size={16} aria-hidden />Close a day</button> : null)} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {["income", "branches", "cash"].includes(tab) && dates(true)}
      {["sheet", "tb"].includes(tab) && dates(false)}

      {tab === "income" && (state(income) ?? (income.data && <>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><StatCard label="Net revenue" value={money(income.data.net_revenue)} icon={CircleDollarSign} /><StatCard label="Gross profit" value={money(income.data.gross_profit)} icon={TrendingUp} tone="info" /><StatCard label="Operating expenses" value={money(income.data.operating_expenses_total)} icon={TrendingDown} tone="warning" /><StatCard label="Net profit" value={money(income.data.net_profit)} icon={Banknote} tone={Number(income.data.net_profit) < 0 ? "danger" : "navy"} /></div>
        <div className="grid items-start gap-5 xl:grid-cols-[1.4fr_1fr]">
          <Statement sections={[{ title: "Revenue", rows: income.data.revenue, totals: [["Net revenue", income.data.net_revenue]] }, { title: "Cost of sales", rows: income.data.cost_of_sales, totals: [["Gross profit", income.data.gross_profit]] }, { title: "Operating expenses", rows: income.data.operating_expenses, totals: [["Total expenses", income.data.operating_expenses_total], ["Net profit", income.data.net_profit]] }]} />
          <ChartCard title="Where the money went" subtitle="Operating expenses in this period"><DonutChart items={income.data.operating_expenses.map((r) => ({ label: r.name, value: r.amount }))} format={(n) => money(n)} centerLabel="Expenses" /></ChartCard>
        </div></>))}
      {tab === "branches" && (state(branches) ?? <>
        <ChartCard title="Net revenue by branch"><RankBars items={(branches.data ?? []).map((b) => ({ label: b.name, value: b.net_revenue }))} format={(n) => money(n)} /></ChartCard>
        <DataTable rows={branches.data} rowKey={(b) => String(b.branch)} columns={[{ key: "name", header: "Branch", render: (b) => <b>{b.name}</b> }, ...(["net_revenue", "cost_of_sales", "gross_profit", "operating_expenses", "net_profit"] as const).map((k) => ({ key: k, header: words(k), align: "right" as const, render: (b: BranchRow) => money(b[k]), sort: (b: BranchRow) => Number(b[k]) }))]} /></>)}
      {tab === "sheet" && (state(sheet) ?? (sheet.data && <div className="max-w-3xl"><Statement balanced={sheet.data.balanced} sections={[{ title: "Assets", rows: sheet.data.assets, totals: [["Total assets", sheet.data.total_assets]] }, { title: "Liabilities", rows: sheet.data.liabilities, totals: [["Total liabilities", sheet.data.total_liabilities]] }, { title: "Equity", rows: [...sheet.data.equity, { code: "", name: "Current period earnings", amount: sheet.data.current_earnings }], totals: [["Total equity", sheet.data.total_equity]] }]} /></div>))}
      {tab === "tb" && (state(tb) ?? (tb.data && <><DataTable rows={tb.data.rows} rowKey={(r) => r.code} pageSize={15} search={(r) => `${r.code} ${r.name}`} columns={[{ key: "account", header: "Account", render: (r) => <><b>{r.code}</b> {r.name}</> }, { key: "debit", header: "Debit", align: "right", render: (r) => Number(r.debit) ? money(r.debit) : "" }, { key: "credit", header: "Credit", align: "right", render: (r) => Number(r.credit) ? money(r.credit) : "" }]} />
        <p className={`alert ${tb.data.balanced ? "alert-success" : "alert-error"}`}>Total debit {money(tb.data.total_debit)} · total credit {money(tb.data.total_credit)} · {tb.data.balanced ? "balanced" : "OUT OF BALANCE"}</p></>))}
      {tab === "cash" && (state(cash) ?? (cash.data && <>
        <div className="grid gap-4 sm:grid-cols-3"><StatCard label="Opening cash" value={money(cash.data.opening_cash)} icon={Banknote} tone="navy" /><StatCard label="Net change" value={money(cash.data.net_change)} icon={Number(cash.data.net_change) < 0 ? TrendingDown : TrendingUp} tone={Number(cash.data.net_change) < 0 ? "danger" : "primary"} /><StatCard label="Closing cash" value={money(cash.data.closing_cash)} icon={CircleDollarSign} hint="Cash on hand, mobile money clearing and bank" /></div>
        <ChartCard title="Money in and out by source" legend={[{ label: "In", color: "var(--series-1)" }, { label: "Out", color: "var(--series-2)" }]}><TrendChart kind="column" rows={cash.data.by_source.map((r) => ({ source: words(r.source), inflow: r.inflow, outflow: r.outflow }))} x="source" series={[{ key: "inflow", label: "In" }, { key: "outflow", label: "Out" }]} format={(n) => money(n)} /></ChartCard>
        <DataTable rows={cash.data.by_source} rowKey={(r) => r.source} columns={[{ key: "source", header: "Source", render: (r) => <span className="capitalize">{words(r.source)}</span> }, { key: "inflow", header: "In", align: "right", render: (r) => money(r.inflow) }, { key: "outflow", header: "Out", align: "right", render: (r) => money(r.outflow) }, { key: "net", header: "Net", align: "right", render: (r) => <b>{money(r.net)}</b> }]} /></>))}
      {tab === "journal" && full && <ServerTable<Entry> queryKey={["acc-journal"]} path="/accounting/journal-entries/" rowKey={(e) => e.id} empty="No journal entries."
        columns={[{ key: "number", header: "Number", render: (e) => <b>{e.number}</b> }, { key: "date", header: "Date", render: (e) => day(e.date) }, { key: "description", header: "Description", render: (e) => e.description }, { key: "source", header: "Source", render: (e) => <span className="badge badge-neutral">{words(e.source_type)}</span> }, { key: "total", header: "Amount", align: "right", render: (e) => <b>{money(e.total)}</b> },
          { key: "actions", header: "Actions", align: "right", render: (e) => e.reversed ? <StatusBadge status="reversed" tone="neutral" /> : manage && ["manual", "expense"].includes(e.source_type) && <button className="btn-link btn-link-danger" onClick={() => reverse(`/accounting/journal-entries/${e.id}/reverse/`, e.number)}>Reverse</button> }]} />}
      {tab === "expenses" && full && <ServerTable<Expense> queryKey={["acc-expenses"]} path="/accounting/expenses/" rowKey={(x) => x.id} empty="No expenses recorded."
        columns={[{ key: "date", header: "Date", render: (x) => day(x.date) }, { key: "category", header: "Category", render: (x) => <b>{x.account_name}</b> }, { key: "description", header: "Description", render: (x) => x.description }, { key: "method", header: "Paid from", render: (x) => <span className="capitalize">{words(x.payment_method)}</span> }, { key: "status", header: "Status", render: (x) => <StatusBadge status={x.status} /> }, { key: "amount", header: "Amount", align: "right", render: (x) => <b>{money(x.amount)}</b> },
          { key: "actions", header: "Actions", align: "right", render: (x) => manage && x.status === "posted" && <button className="btn-link btn-link-danger" onClick={() => reverse(`/accounting/expenses/${x.id}/reverse/`, `this expense`)}>Reverse</button> }]} />}
      {tab === "close" && <DataTable rows={closes.data} loading={closes.isLoading} rowKey={(c) => c.date} empty="No days closed yet." columns={[{ key: "date", header: "Closed through", render: (c) => <b>{day(c.date)}</b>, sort: (c) => c.date }, { key: "profit", header: "Net profit", align: "right", render: (c) => money(c.summary.net_profit) }, { key: "cash", header: "Closing cash", align: "right", render: (c) => money(c.summary.closing_cash) }, { key: "by", header: "Closed by", render: (c) => c.closed_by ?? "—" }]} />}
      {dialog === "expense" && <FormModal title="Record an expense" size="lg" submitLabel="Record expense" fields={expenseFields} onClose={() => setDialog(null)} onSubmit={async (v) => { await api("/accounting/expenses/", { method: "POST", body: v }); done("Expense recorded."); }} />}
      {dialog === "entry" && <FormModal title="Manual journal entry" size="lg" submitLabel="Post entry" description="The same amount is posted to both accounts, so the entry always balances." fields={entryFields} onClose={() => setDialog(null)}
        onSubmit={async (v) => { await api("/accounting/journal-entries/", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: { description: v.description, date: v.date, lines: [{ account: v.debit, debit: v.amount }, { account: v.credit, credit: v.amount }] } }); done("Journal entry posted."); }} />}
    </div>
  );
}
