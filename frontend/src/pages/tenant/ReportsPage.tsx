import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ApiError, api, downloadFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { BarList, EmptyState, ErrorState, Loading, PageHeader, StatCard } from "../../components/ui";

interface Meta { slug: string; title: string; group: string }
interface Col { key: string; label: string; kind: string }
interface Result { title: string; columns: Col[]; rows: Record<string, unknown>[]; count: number; page: number; page_size: number; summary: Record<string, unknown> }
interface Dash {
  scope: string; people: { branches: number; employees: number; pharmacists: number; customers: number | null };
  medicines: { total: number; low_stock: number; out_of_stock: number; near_expiry_batches: number; expired_batches: number; inventory_value: string; unsaleable_value: string };
  sales: { today: string; month: string; range: string; transactions: number };
  finance: { revenue: string; gross_profit: string; expenses: string; net_profit_estimate: string; purchases: string; outstanding_supplier_payments: string | null; returns_and_refunds: string };
  prescriptions: Record<string, number>; orders: { pending: number; completed: number };
  payment_breakdown: { method: string; amount: string }[]; branch_performance: { branch: string; net_revenue: string; net_profit: string }[]; cashier_performance: { cashier: string; sales: number; total: string }[];
}
const money = (v: unknown) => (typeof v === "string" || typeof v === "number") && v !== "" && !Number.isNaN(Number(v)) ? Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : String(v ?? "");
const today = () => new Date().toISOString().slice(0, 10);
const monthStart = () => today().slice(0, 8) + "01";
const errText = (e: unknown) => (e instanceof ApiError ? e.message : "Request failed.");

const Card = ({ label, value }: { label: string; value: string | number | null | undefined }) => (value == null ? null : <StatCard label={label} value={value} />);

export function OverviewPage() {
  const [from, setFrom] = useState(monthStart()); const [to, setTo] = useState(today());
  const q = useQuery({ queryKey: ["overview", from, to], queryFn: () => api<Dash>(`/reports/dashboard/?date_from=${from}&date_to=${to}`) });
  const d = q.data;
  const group = (title: string, children: React.ReactNode) => <section className="space-y-3"><h2 className="section-title">{title}</h2><div className="grid grid-cols-2 gap-4 xl:grid-cols-4">{children}</div></section>;
  const panel = (title: string, children: React.ReactNode) => <section className="card p-5"><h2 className="section-title mb-4">{title}</h2>{children}</section>;
  return (
    <div className="space-y-6">
      <PageHeader title="Business overview" subtitle="Sales, finance and stock performance for the selected period."
        actions={<div className="flex flex-wrap items-center gap-2 text-sm"><label className="flex items-center gap-1.5 text-muted">From<input type="date" className="px-2 py-1" value={from} onChange={(e) => setFrom(e.target.value)} /></label><label className="flex items-center gap-1.5 text-muted">To<input type="date" className="px-2 py-1" value={to} onChange={(e) => setTo(e.target.value)} /></label></div>} />
      {q.isLoading && <Loading rows={5} />}
      {q.isError && <ErrorState onRetry={() => q.refetch()}>{errText(q.error)}</ErrorState>}
      {d && <>
        <p className="text-sm text-muted">Showing {d.scope === "branch" ? "your branch" : "the whole pharmacy"}.</p>
        {group("Sales", <>
          <Card label="Sales today (net)" value={money(d.sales.today)} /><Card label="Sales this month (net)" value={money(d.sales.month)} /><Card label="Sales in range (net)" value={money(d.sales.range)} /><Card label="Transactions" value={d.sales.transactions} /></>)}
        {group("Finance", <>
          <Card label="Revenue" value={money(d.finance.revenue)} /><Card label="Gross profit" value={money(d.finance.gross_profit)} /><Card label="Expenses" value={money(d.finance.expenses)} /><Card label="Net profit (estimate)" value={money(d.finance.net_profit_estimate)} />
          <Card label="Purchases received" value={money(d.finance.purchases)} /><Card label="Owed to suppliers" value={d.finance.outstanding_supplier_payments == null ? null : money(d.finance.outstanding_supplier_payments)} /><Card label="Returns & refunds" value={money(d.finance.returns_and_refunds)} /></>)}
        {group("Stock", <>
          <Card label="Inventory value" value={money(d.medicines.inventory_value)} /><Card label="Medicines" value={d.medicines.total} /><Card label="Low stock" value={d.medicines.low_stock} /><Card label="Out of stock" value={d.medicines.out_of_stock} />
          <Card label="Expiring soon (batches)" value={d.medicines.near_expiry_batches} /><Card label="Expired (batches)" value={d.medicines.expired_batches} /></>)}
        {group("People & orders", <>
          <Card label="Employees" value={d.people.employees} /><Card label="Pharmacists" value={d.people.pharmacists} /><Card label="Customers" value={d.people.customers} />
          <Card label="Open online orders" value={d.orders.pending} /><Card label="Completed online orders" value={d.orders.completed} /></>)}
        <div className="grid gap-4 lg:grid-cols-2">
          {panel("Payment methods", <BarList empty="No payments in this range." format={(n) => money(n)} items={d.payment_breakdown.map((p) => ({ label: p.method, value: Number(p.amount) }))} />)}
          {panel("Prescriptions", <BarList empty="No prescriptions in this range." items={Object.entries(d.prescriptions).map(([k, v]) => ({ label: k, value: v }))} />)}
          {panel("Branch performance (net revenue)", <BarList format={(n) => money(n)} items={d.branch_performance.map((b) => ({ label: b.branch, value: Number(b.net_revenue), note: `profit ${money(b.net_profit)}` }))} />)}
          {panel("Cashier performance", <BarList format={(n) => money(n)} items={d.cashier_performance.map((c) => ({ label: c.cashier, value: Number(c.total), note: `${c.sales} sales` }))} />)}
        </div></>}
    </div>
  );
}

export function ReportsPage() {
  const { user } = useAuth();
  const list = useQuery({ queryKey: ["report-list"], queryFn: () => api<Meta[]>("/reports/") });
  const [slug, setSlug] = useState("sales-summary"); const [from, setFrom] = useState(monthStart()); const [to, setTo] = useState(today());
  const [group, setGroup] = useState("day"); const [search, setSearch] = useState(""); const [ordering, setOrdering] = useState(""); const [page, setPage] = useState(1); const [msg, setMsg] = useState<string | null>(null);
  const qs = useMemo(() => `date_from=${from}&date_to=${to}&group=${group}&search=${encodeURIComponent(search)}&ordering=${ordering}&page=${page}`, [from, to, group, search, ordering, page]);
  const res = useQuery({ queryKey: ["report", slug, qs], queryFn: () => api<Result>(`/reports/${slug}/?${qs}`), enabled: !!list.data?.some((r) => r.slug === slug) });
  const groups = useMemo(() => Object.entries((list.data ?? []).reduce<Record<string, Meta[]>>((a, r) => ({ ...a, [r.group]: [...(a[r.group] ?? []), r] }), {})), [list.data]);
  const exportAs = (fmt: "csv" | "xlsx" | "pdf") => downloadFile(`/reports/${slug}/?${qs}&export=${fmt}`, `${slug}.${fmt}`).catch((e) => setMsg(errText(e)));
  const cell = (c: Col, v: unknown) => c.kind === "money" ? money(v) : String(v ?? "");
  if (list.isError) return <p role="alert" className="p-4 text-red-700">{errText(list.error)}</p>;
  return (
    <div className="space-y-4"><PageHeader title="Reports" subtitle="Run and export reports." />{user?.branch && <p className="text-sm text-slate-600">Reports are limited to your branch.</p>}
      {msg && <p role="alert" className="alert alert-error">{msg}</p>}
      <div className="flex flex-wrap items-end gap-2 text-sm">
        <label>Report<select className="ml-1 px-3 py-2" value={slug} onChange={(e) => { setSlug(e.target.value); setPage(1); setOrdering(""); }}>{groups.map(([g, items]) => <optgroup key={g} label={g}>{items.map((r) => <option key={r.slug} value={r.slug}>{r.title}</option>)}</optgroup>)}</select></label>
        <label>From<input type="date" className="ml-1 px-3 py-2" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1); }} /></label><label>To<input type="date" className="ml-1 px-3 py-2" value={to} onChange={(e) => { setTo(e.target.value); setPage(1); }} /></label>
        {slug === "sales-summary" && <label>Group by<select className="ml-1 px-3 py-2" value={group} onChange={(e) => setGroup(e.target.value)}><option value="day">Day</option><option value="week">Week</option><option value="month">Month</option><option value="year">Year</option></select></label>}
        <input aria-label="Search report" placeholder="Enter text to filter rows" className="px-3 py-2" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        <span className="ml-auto space-x-2"><button className="btn btn-outline" onClick={() => exportAs("pdf")}>PDF</button><button className="btn btn-outline" onClick={() => exportAs("xlsx")}>Excel</button><button className="btn btn-outline" onClick={() => exportAs("csv")}>CSV</button></span></div>
      {res.isLoading && <Loading />}{res.isError && <p role="alert" className="alert alert-error">{errText(res.error)}</p>}
      {res.data && <>
        <p className="text-sm text-slate-600">{res.data.count} rows {Object.entries(res.data.summary).map(([k, v]) => ` · ${k.replace(/_/g, " ")}: ${money(v)}`).join("")}</p>
        {res.data.rows.length === 0 ? <EmptyState>No data for this selection.</EmptyState> : <div className="table-wrap"><table className="table"><thead><tr>{res.data.columns.map((c) => <th key={c.key} className="p-3"><button className="font-semibold" onClick={() => { setOrdering(ordering === c.key ? `-${c.key}` : c.key); setPage(1); }}>{c.label}{ordering === c.key ? " ▲" : ordering === `-${c.key}` ? " ▼" : ""}</button></th>)}</tr></thead>
          <tbody>{res.data.rows.map((r, i) => <tr key={i}>{res.data!.columns.map((c) => <td key={c.key} className={`p-3 ${c.kind === "money" || c.kind === "int" ? "text-right" : ""}`}>{cell(c, r[c.key])}</td>)}</tr>)}</tbody></table></div>}
        <div className="flex items-center gap-2"><button disabled={page <= 1} onClick={() => setPage(page - 1)} className="btn btn-outline btn-sm">Previous</button><span className="text-sm">Page {page}</span><button disabled={page * res.data.page_size >= res.data.count} onClick={() => setPage(page + 1)} className="btn btn-outline btn-sm">Next</button></div></>}
    </div>
  );
}
