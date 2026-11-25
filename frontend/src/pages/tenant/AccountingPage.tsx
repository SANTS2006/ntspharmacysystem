import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../../lib/api";
import { useAuth } from "../../lib/auth";

interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
interface Account { id: number; code: string; name: string; type: string; is_active: boolean }
interface Line { name: string; code: string; amount: string }
interface Income { revenue: Line[]; net_revenue: string; cost_of_sales: Line[]; cost_of_sales_total: string; gross_profit: string; operating_expenses: Line[]; operating_expenses_total: string; net_profit: string }
interface Sheet { assets: Line[]; liabilities: Line[]; equity: Line[]; current_earnings: string; total_assets: string; total_liabilities: string; total_equity: string; balanced: boolean }
interface Tb { rows: { code: string; name: string; debit: string; credit: string }[]; total_debit: string; total_credit: string; balanced: boolean }
interface Cash { opening_cash: string; by_source: { source: string; inflow: string; outflow: string; net: string }[]; net_change: string; closing_cash: string }
interface Entry { id: number; number: string; date: string; description: string; source_type: string; total: string; reversed: boolean }
interface Expense { id: number; date: string; account_name: string; amount: string; payment_method: string; description: string; status: string; branch: number | null }
interface BranchRow { branch: number | null; name: string; net_revenue: string; cost_of_sales: string; gross_profit: string; operating_expenses: string; net_profit: string }

const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const inputCls = "mt-1 rounded border p-2 font-normal";
const brand = { background: "var(--brand)" };
const money = (v: string | number) => Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const today = () => new Date().toISOString().slice(0, 10);
type Tab = "income" | "sheet" | "tb" | "cash" | "branches" | "journal" | "expenses" | "close";

const Rows = ({ rows }: { rows: Line[] }) => <>{rows.map((r) => <tr key={r.code}><td className="py-1 pl-4">{r.code} {r.name}</td><td className="text-right">{money(r.amount)}</td></tr>)}</>;
const Tot = ({ label, v, strong }: { label: string; v: string; strong?: boolean }) => <tr className={`border-t ${strong ? "font-semibold" : ""}`}><td className="py-1">{label}</td><td className="text-right">{money(v)}</td></tr>;

export default function AccountingPage() {
  const { user } = useAuth(); const qc = useQueryClient();
  const can = (p: string) => !!user?.permissions.includes(p);
  const full = can("accounting.view");
  const manage = can("accounting.manage");
  const [tab, setTab] = useState<Tab>("income"); const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const [from, setFrom] = useState(today().slice(0, 8) + "01"); const [to, setTo] = useState(today());
  const range = `date_from=${from}&date_to=${to}`;
  const ok = (t: string) => { setMsg({ ok: true, t }); qc.invalidateQueries(); };
  const fail = (e: unknown) => setMsg({ ok: false, t: errText(e) });
  const income = useQuery({ queryKey: ["acc-income", from, to], queryFn: () => api<Income>(`/accounting/reports/income-statement/?${range}`), enabled: tab === "income" });
  const sheet = useQuery({ queryKey: ["acc-sheet", to], queryFn: () => api<Sheet>(`/accounting/reports/balance-sheet/?as_of=${to}`), enabled: tab === "sheet" && full });
  const tb = useQuery({ queryKey: ["acc-tb", to], queryFn: () => api<Tb>(`/accounting/reports/trial-balance/?as_of=${to}`), enabled: tab === "tb" && full });
  const cash = useQuery({ queryKey: ["acc-cash", from, to], queryFn: () => api<Cash>(`/accounting/reports/cash-flow/?${range}`), enabled: tab === "cash" && full });
  const branches = useQuery({ queryKey: ["acc-branches", from, to], queryFn: () => api<BranchRow[]>(`/accounting/reports/branch-summary/?${range}`), enabled: tab === "branches" });
  const accounts = useQuery({ queryKey: ["acc-accounts"], queryFn: () => api<Account[]>("/accounting/accounts/"), enabled: full });
  const journal = useQuery({ queryKey: ["acc-journal"], queryFn: () => api<Page<Entry>>("/accounting/journal-entries/"), enabled: tab === "journal" && full });
  const expenses = useQuery({ queryKey: ["acc-expenses"], queryFn: () => api<Page<Expense>>("/accounting/expenses/"), enabled: tab === "expenses" && full });
  const closes = useQuery({ queryKey: ["acc-closes"], queryFn: () => api<{ date: string; closed_by: string | null; summary: Record<string, string> }[]>("/accounting/closes/"), enabled: tab === "close" && full });

  const [exp, setExp] = useState({ date: today(), account: "6100", amount: "", payment_method: "cash", description: "", vendor: "" });
  const addExpense = useMutation({ mutationFn: () => api("/accounting/expenses/", { method: "POST", body: exp }), onSuccess: () => { setExp({ ...exp, amount: "", description: "", vendor: "" }); ok("Expense recorded."); }, onError: fail });
  const [je, setJe] = useState({ description: "", a1: "", d1: "", a2: "", c2: "", date: today() });
  const addEntry = useMutation({
    mutationFn: () => api("/accounting/journal-entries/", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: { description: je.description, date: je.date, lines: [{ account: je.a1, debit: je.d1 || "0" }, { account: je.a2, credit: je.c2 || "0" }] } }),
    onSuccess: () => ok("Journal entry posted."), onError: fail,
  });
  const reverse = (id: number, number: string, kind: "entry" | "expense") => {
    const reason = window.prompt(`Enter the reason for reversing ${number}`); if (!reason) return;
    if (window.confirm("Reverse this posting? A new opposite entry is created; the original stays on record.")) api(kind === "entry" ? `/accounting/journal-entries/${id}/reverse/` : `/accounting/expenses/${id}/reverse/`, { method: "POST", body: { reason } }).then(() => ok("Reversed.")).catch(fail);
  };
  const closeDay = () => {
    const d = window.prompt("Enter the date to close (YYYY-MM-DD). Nothing can be posted into closed dates.", ""); if (!d) return;
    if (window.confirm(`Close all books through ${d}? This cannot be undone.`)) api("/accounting/closes/", { method: "POST", body: { date: d } }).then(() => ok("Day closed.")).catch(fail);
  };

  const tabs: [Tab, string, boolean][] = [["income", "Profit & loss", true], ["branches", "Branches", true], ["sheet", "Balance sheet", full], ["tb", "Trial balance", full], ["cash", "Cash flow", full], ["journal", "Journal", full], ["expenses", "Expenses", full], ["close", "Daily close", full]];
  const sel = (v: string, set: (s: string) => void, label: string, only?: string) => <select aria-label={label} required className={inputCls} value={v} onChange={(e) => set(e.target.value)}><option value="">{label}</option>{accounts.data?.filter((a) => a.is_active && (!only || a.type === only)).map((a) => <option key={a.id} value={a.code}>{a.code} {a.name}</option>)}</select>;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Accounting</h1>
      {!full && <p className="text-sm text-slate-600">Showing your branch only.</p>}
      {msg && <p role={msg.ok ? "status" : "alert"} className={`rounded p-3 text-sm ${msg.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>{msg.t}</p>}
      <div role="tablist" className="flex flex-wrap gap-2">{tabs.filter((t) => t[2]).map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`rounded px-3 py-1 text-sm ${tab === k ? "text-white" : "border"}`} style={tab === k ? brand : undefined}>{label}</button>)}</div>
      {["income", "branches", "cash"].includes(tab) && <div className="flex gap-2 text-sm"><label>From<input type="date" className={`${inputCls} block`} value={from} onChange={(e) => setFrom(e.target.value)} /></label><label>To<input type="date" className={`${inputCls} block`} value={to} onChange={(e) => setTo(e.target.value)} /></label></div>}
      {["sheet", "tb"].includes(tab) && <label className="block text-sm">As of<input type="date" className={`${inputCls} block`} value={to} onChange={(e) => setTo(e.target.value)} /></label>}

      {tab === "income" && income.data && <table className="w-full max-w-xl bg-white text-sm"><tbody>
        <tr className="font-semibold"><td colSpan={2}>Revenue</td></tr><Rows rows={income.data.revenue} /><Tot label="Net revenue" v={income.data.net_revenue} strong />
        <tr className="font-semibold"><td colSpan={2}>Cost of sales</td></tr><Rows rows={income.data.cost_of_sales} /><Tot label="Gross profit" v={income.data.gross_profit} strong />
        <tr className="font-semibold"><td colSpan={2}>Operating expenses</td></tr><Rows rows={income.data.operating_expenses} /><Tot label="Total expenses" v={income.data.operating_expenses_total} /><Tot label="Net profit" v={income.data.net_profit} strong /></tbody></table>}
      {tab === "branches" && branches.data && <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Branch</th><th>Net revenue</th><th>Cost of sales</th><th>Gross profit</th><th>Expenses</th><th>Net profit</th></tr></thead><tbody>{branches.data.map((b) => <tr key={String(b.branch)} className="border-t"><td className="p-3">{b.name}</td><td>{money(b.net_revenue)}</td><td>{money(b.cost_of_sales)}</td><td>{money(b.gross_profit)}</td><td>{money(b.operating_expenses)}</td><td>{money(b.net_profit)}</td></tr>)}</tbody></table></div>}
      {tab === "sheet" && sheet.data && <div className="max-w-xl rounded-xl bg-white p-4 text-sm shadow-sm"><table className="w-full"><tbody>
        <tr className="font-semibold"><td colSpan={2}>Assets</td></tr><Rows rows={sheet.data.assets} /><Tot label="Total assets" v={sheet.data.total_assets} strong />
        <tr className="font-semibold"><td colSpan={2}>Liabilities</td></tr><Rows rows={sheet.data.liabilities} /><Tot label="Total liabilities" v={sheet.data.total_liabilities} />
        <tr className="font-semibold"><td colSpan={2}>Equity</td></tr><Rows rows={sheet.data.equity} /><tr><td className="py-1 pl-4">Current period earnings</td><td className="text-right">{money(sheet.data.current_earnings)}</td></tr><Tot label="Total equity" v={sheet.data.total_equity} /></tbody></table>
        <p className={sheet.data.balanced ? "mt-2 text-green-700" : "mt-2 font-semibold text-red-700"}>{sheet.data.balanced ? "Balanced: assets = liabilities + equity." : "OUT OF BALANCE: contact support."}</p></div>}
      {tab === "tb" && tb.data && <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Account</th><th>Debit</th><th>Credit</th></tr></thead><tbody>{tb.data.rows.map((r) => <tr key={r.code} className="border-t"><td className="p-3">{r.code} {r.name}</td><td>{Number(r.debit) ? money(r.debit) : ""}</td><td>{Number(r.credit) ? money(r.credit) : ""}</td></tr>)}<tr className="border-t font-semibold"><td className="p-3">Totals {tb.data.balanced ? "(balanced)" : "(OUT OF BALANCE)"}</td><td>{money(tb.data.total_debit)}</td><td>{money(tb.data.total_credit)}</td></tr></tbody></table></div>}
      {tab === "cash" && cash.data && <div className="max-w-xl rounded-xl bg-white p-4 text-sm shadow-sm"><p>Opening cash: {money(cash.data.opening_cash)}</p><table className="my-2 w-full"><thead><tr className="text-left"><th>Source</th><th>In</th><th>Out</th><th>Net</th></tr></thead><tbody>{cash.data.by_source.map((r) => <tr key={r.source}><td>{r.source.replace(/_/g, " ")}</td><td>{money(r.inflow)}</td><td>{money(r.outflow)}</td><td>{money(r.net)}</td></tr>)}</tbody></table><p className="font-semibold">Closing cash: {money(cash.data.closing_cash)}</p><p className="text-slate-500">Cash includes cash on hand, mobile money clearing and bank.</p></div>}

      {tab === "journal" && <>
        {manage && <form onSubmit={(e) => { e.preventDefault(); setMsg(null); addEntry.mutate(); }} className="grid gap-2 rounded-xl bg-white p-4 shadow-sm md:grid-cols-6"><h2 className="font-semibold md:col-span-6">Manual journal entry (two lines)</h2>
          <input required className={`${inputCls} md:col-span-2`} placeholder="Enter the description" value={je.description} onChange={(e) => setJe({ ...je, description: e.target.value })} aria-label="Description" />
          <input type="date" className={inputCls} value={je.date} onChange={(e) => setJe({ ...je, date: e.target.value })} aria-label="Date" />
          {sel(je.a1, (v) => setJe({ ...je, a1: v }), "Debit account")}<input type="number" min="0.01" step="0.01" required className={inputCls} placeholder="Debit amount" value={je.d1} onChange={(e) => setJe({ ...je, d1: e.target.value, c2: e.target.value })} aria-label="Debit amount" />
          {sel(je.a2, (v) => setJe({ ...je, a2: v }), "Credit account")}<input type="number" min="0.01" step="0.01" required className={inputCls} placeholder="Credit amount" value={je.c2} onChange={(e) => setJe({ ...je, c2: e.target.value })} aria-label="Credit amount" />
          <button disabled={addEntry.isPending} className="rounded px-4 py-2 text-white" style={brand}>Post entry</button></form>}
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Number</th><th>Date</th><th>Description</th><th>Source</th><th>Amount</th><th /></tr></thead>
          <tbody>{journal.data?.results.map((e) => <tr key={e.id} className="border-t"><td className="p-3">{e.number}</td><td>{e.date}</td><td>{e.description}</td><td>{e.source_type}</td><td>{money(e.total)}</td><td>{manage && ["manual", "expense"].includes(e.source_type) && !e.reversed && <button className="underline" onClick={() => reverse(e.id, e.number, "entry")}>Reverse</button>}{e.reversed && <em>reversed</em>}</td></tr>)}</tbody></table></div></>}
      {tab === "expenses" && <>
        {manage && <form onSubmit={(e) => { e.preventDefault(); setMsg(null); addExpense.mutate(); }} className="grid gap-2 rounded-xl bg-white p-4 shadow-sm md:grid-cols-6"><h2 className="font-semibold md:col-span-6">Record an expense</h2>
          <input type="date" className={inputCls} value={exp.date} onChange={(e) => setExp({ ...exp, date: e.target.value })} aria-label="Date" />
          {sel(exp.account, (v) => setExp({ ...exp, account: v }), "Expense category", "expense")}
          <input required type="number" min="0.01" step="0.01" className={inputCls} placeholder="Enter the amount" value={exp.amount} onChange={(e) => setExp({ ...exp, amount: e.target.value })} aria-label="Amount" />
          <select aria-label="Paid from" className={inputCls} value={exp.payment_method} onChange={(e) => setExp({ ...exp, payment_method: e.target.value })}><option value="cash">Cash</option><option value="bank">Bank</option><option value="mobile_money">Mobile money</option></select>
          <input required className={`${inputCls} md:col-span-2`} placeholder="Enter the description" value={exp.description} onChange={(e) => setExp({ ...exp, description: e.target.value })} aria-label="Description" />
          <button disabled={addExpense.isPending} className="rounded px-4 py-2 text-white" style={brand}>Record expense</button></form>}
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Date</th><th>Category</th><th>Description</th><th>Amount</th><th>Paid by</th><th>Status</th><th /></tr></thead>
          <tbody>{expenses.data?.results.map((x) => <tr key={x.id} className="border-t"><td className="p-3">{x.date}</td><td>{x.account_name}</td><td>{x.description}</td><td>{money(x.amount)}</td><td>{x.payment_method}</td><td>{x.status}</td><td>{manage && x.status === "posted" && <button className="underline" onClick={() => reverse(x.id, `expense ${x.id}`, "expense")}>Reverse</button>}</td></tr>)}</tbody></table></div></>}
      {tab === "close" && <div className="space-y-2">{manage && <button className="rounded px-4 py-2 text-white" style={brand} onClick={closeDay}>Close a day</button>}
        {closes.data?.length === 0 && <p className="text-slate-500">No days closed yet.</p>}<ul className="text-sm">{closes.data?.map((c) => <li key={c.date}>{c.date}: net profit {money(c.summary.net_profit)} · closing cash {money(c.summary.closing_cash)} · closed by {c.closed_by}</li>)}</ul></div>}
    </div>
  );
}
