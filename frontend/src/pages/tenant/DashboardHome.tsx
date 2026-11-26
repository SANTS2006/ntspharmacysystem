/** Staff home dashboard. Every figure comes from an existing API; each panel is only requested when the user's permissions allow it. */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Banknote, Building2, CalendarClock, Package, PackageX, Pill, Receipt, ScrollText, ShoppingCart, Stethoscope, TrendingUp, Users, Wallet, type LucideIcon } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { BarList, EmptyState, ErrorState, Loading, PageHeader, StatCard, StatusBadge } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";

interface Page<T> { count: number; results: T[] }
interface Basic { scope: string; branches: number; employees: number; pharmacists: number; customers: number | null; staff_by_role: { role__name: string; n: number }[] }
interface Dash {
  medicines: { total: number; low_stock: number; out_of_stock: number; near_expiry_batches: number; expired_batches: number; inventory_value: string };
  sales: { today: string; month: string; transactions: number };
  orders: { pending: number };
}
interface Report { rows: Record<string, string | number>[] }
interface BatchRow { id: number; batch_number: string; medicine_name?: string; expiry_date: string | null; quantity_available: number }
interface MedRow { id: number; name: string; strength?: string }
interface Alerts { low_stock: MedRow[]; out_of_stock: MedRow[]; near_expiry: BatchRow[]; expired: BatchRow[] }
interface SaleRow { id: number; reference_number: string; status: string; total: string; customer_name: string; created_at: string; cashier_name: string }

const money = (v: string | number) => Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const iso = (d: Date) => d.toISOString().slice(0, 10);
const daysAgo = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return iso(d); };

function Panel({ title, to, linkLabel, children }: { title: string; to?: string; linkLabel?: string; children: React.ReactNode }) {
  return (
    <section className="card flex flex-col p-5">
      <div className="mb-4 flex items-center justify-between gap-3"><h2 className="section-title">{title}</h2>{to && <Link to={to} className="btn-link">{linkLabel ?? "View all"}<ArrowRight size={14} aria-hidden /></Link>}</div>
      {children}
    </section>
  );
}

/** Daily net sales as columns, using the sales-summary report rows. */
function SalesChart({ rows }: { rows: { label: string; value: number }[] }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  if (rows.every((r) => r.value === 0)) return <p className="grid h-48 place-items-center text-sm text-muted">No sales in the last 14 days.</p>;
  return (
    <div className="flex h-48 items-end gap-1.5" role="img" aria-label={`Net sales by day: ${rows.map((r) => `${r.label} ${money(r.value)}`).join(", ")}`}>
      {rows.map((r) => (
        <div key={r.label} className="group flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1.5">
          <div className="relative w-full max-w-10 rounded-t-md bg-primary/85 transition-colors group-hover:bg-primary-hover" style={{ height: `${Math.max((r.value / max) * 100, r.value > 0 ? 3 : 0.5)}%` }}>
            <span className="pointer-events-none absolute -top-7 left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded bg-ink px-2 py-0.5 text-[11px] text-white group-hover:block">{money(r.value)}</span>
          </div>
          <span className="text-[10px] text-muted">{r.label.slice(8)}</span>
        </div>))}
    </div>
  );
}

export default function DashboardHome() {
  const { user } = useAuth(); const { slug } = useParams();
  const can = (p: string) => !!user?.permissions.includes(p);
  const base = `/${slug}/admin`;
  const reports = can("report.view"), stock = can("inventory.view"), sales = can("pos.sell") || can("sales.view_branch");
  const basic = useQuery({ queryKey: ["tenant-dashboard"], queryFn: () => api<Basic>("/tenants/dashboard/") });
  const dash = useQuery({ queryKey: ["overview", "home"], queryFn: () => api<Dash>("/reports/dashboard/"), enabled: reports, retry: false });
  const trend = useQuery({ queryKey: ["report", "home-trend"], queryFn: () => api<Report>(`/reports/sales-summary/?group=day&date_from=${daysAgo(13)}&date_to=${daysAgo(0)}&page_size=31`), enabled: reports, retry: false });
  const top = useQuery({ queryKey: ["report", "home-top"], queryFn: () => api<Report>(`/reports/sales-by-product/?date_from=${daysAgo(29)}&date_to=${daysAgo(0)}&page_size=5`), enabled: reports, retry: false });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api<Alerts>("/inventory/alerts/"), enabled: stock, retry: false });
  const recent = useQuery({ queryKey: ["sales"], queryFn: () => api<Page<SaleRow>>("/sales/"), enabled: sales, retry: false });

  const byDay = new Map((trend.data?.rows ?? []).map((r) => [String(r.period).slice(0, 10), Number(r.net_sales)]));
  const days = Array.from({ length: 14 }, (_, i) => daysAgo(13 - i)).map((d) => ({ label: d, value: byDay.get(d) ?? 0 }));
  const quick: [string, string, LucideIcon, boolean][] = [
    ["pos", "New sale", Receipt, can("pos.sell")], ["prescriptions", "Prescriptions", ScrollText, can("prescription.view")],
    ["inventory", "Receive or check stock", Package, stock], ["procurement", "Purchase orders", ShoppingCart, can("procurement.view")],
  ];
  const expiring = [...(alerts.data?.expired ?? []).map((b) => ({ ...b, state: "expired" })), ...(alerts.data?.near_expiry ?? []).map((b) => ({ ...b, state: "pending" }))].slice(0, 5);
  const low = [...(alerts.data?.out_of_stock ?? []).map((m) => ({ ...m, state: "out_of_stock" })), ...(alerts.data?.low_stock ?? []).map((m) => ({ ...m, state: "low_stock" }))].filter((m, i, a) => a.findIndex((x) => x.id === m.id) === i).slice(0, 5);

  return (
    <div className="space-y-6">
      <PageHeader title={`Welcome, ${user?.full_name ?? ""}`} subtitle={`${new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}${basic.data ? ` · ${basic.data.scope === "branch" ? "Your branch" : "All branches"}` : ""}`}
        actions={can("pos.sell") && <Link to={`${base}/pos`} className="btn btn-primary"><Receipt size={16} aria-hidden />New sale</Link>} />

      {reports && (dash.isLoading ? <Loading rows={1} /> : dash.data && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Sales today (net)" value={money(dash.data.sales.today)} icon={Wallet} />
          <StatCard label="Sales this month (net)" value={money(dash.data.sales.month)} icon={TrendingUp} tone="info" />
          <StatCard label="Inventory value" value={money(dash.data.medicines.inventory_value)} icon={Banknote} tone="navy" hint={`${dash.data.medicines.total} active medicines`} />
          <StatCard label="Open online orders" value={dash.data.orders.pending} icon={Package} tone="info" />
        </div>))}

      {stock && alerts.data && (
        <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
          <StatCard label="Low stock" value={alerts.data.low_stock.length} icon={AlertTriangle} tone="warning" />
          <StatCard label="Out of stock" value={alerts.data.out_of_stock.length} icon={PackageX} tone="danger" />
          <StatCard label="Expiring soon (batches)" value={alerts.data.near_expiry.length} icon={CalendarClock} tone="warning" />
          <StatCard label="Expired batches" value={alerts.data.expired.length} icon={Pill} tone="danger" />
        </div>)}

      {basic.isLoading && <Loading />}
      {basic.isError && <ErrorState onRetry={() => basic.refetch()}>The dashboard could not be loaded.</ErrorState>}

      {reports && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2"><Panel title="Net sales · last 14 days" to={`${base}/overview`} linkLabel="Business overview">{trend.isLoading ? <div className="skeleton h-48" /> : trend.isError ? <p className="text-sm text-muted">The sales chart could not be loaded.</p> : <SalesChart rows={days} />}</Panel></div>
          <Panel title="Top-selling · 30 days" to={`${base}/reports`} linkLabel="Reports">
            <BarList empty="No sales in the last 30 days." items={(top.data?.rows ?? []).slice(0, 5).map((r) => ({ label: String(r.product), value: Number(r.quantity), note: money(r.revenue) }))} />
          </Panel>
        </div>)}

      <div className="grid gap-4 lg:grid-cols-2">
        {stock && <Panel title="Stock needing attention" to={`${base}/inventory`}>
          {low.length === 0 ? <p className="py-6 text-center text-sm text-muted">No low or out-of-stock medicines.</p> : <ul className="divide-y divide-slate-100">{low.map((m) => <li key={m.id} className="flex items-center justify-between gap-3 py-2.5 text-sm"><span className="truncate font-medium">{m.name} <span className="font-normal text-muted">{m.strength}</span></span><StatusBadge status={m.state} /></li>)}</ul>}
        </Panel>}
        {stock && <Panel title="Expiry watch" to={`${base}/inventory`}>
          {expiring.length === 0 ? <p className="py-6 text-center text-sm text-muted">No expired or soon-to-expire batches.</p> : <ul className="divide-y divide-slate-100">{expiring.map((b) => <li key={b.id} className="flex items-center justify-between gap-3 py-2.5 text-sm"><span className="min-w-0 truncate"><span className="font-medium">{b.medicine_name ?? "Batch"}</span> <span className="text-muted">· {b.batch_number} · {b.quantity_available} units</span></span><StatusBadge status={b.state === "expired" ? "expired" : `exp ${b.expiry_date}`} tone={b.state === "expired" ? "danger" : "warning"} /></li>)}</ul>}
        </Panel>}
      </div>

      {sales && <Panel title="Recent transactions" to={`${base}/pos`}>
        {recent.isLoading ? <div className="skeleton h-24" /> : !recent.data?.results.length ? <EmptyState>No sales yet.</EmptyState> : (
          <div className="relative -mx-5 -mb-5 overflow-x-auto"><table className="table"><thead><tr><th>Reference</th><th>When</th><th>Cashier</th><th>Customer</th><th className="!text-right">Total</th><th>Status</th></tr></thead>
            <tbody>{recent.data.results.slice(0, 6).map((s) => <tr key={s.id}><td className="font-semibold">{s.reference_number}</td><td className="whitespace-nowrap">{new Date(s.created_at).toLocaleString()}</td><td>{s.cashier_name}</td><td>{s.customer_name || "—"}</td><td className="text-right font-semibold tabular-nums">{money(s.total)}</td><td><StatusBadge status={s.status} /></td></tr>)}</tbody></table></div>)}
      </Panel>}

      {basic.data && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="grid grid-cols-2 gap-4 lg:col-span-2">
            <StatCard label="Branches" value={basic.data.branches} icon={Building2} tone="navy" />
            <StatCard label="Employees" value={basic.data.employees} icon={Users} tone="navy" />
            <StatCard label="Pharmacists" value={basic.data.pharmacists} icon={Stethoscope} />
            {basic.data.customers !== null && <StatCard label="Customers" value={basic.data.customers} icon={Users} tone="info" />}
          </div>
          <Panel title="Staff by role"><BarList empty="No staff yet." items={basic.data.staff_by_role.map((r) => ({ label: r.role__name ?? "No role", value: r.n }))} /></Panel>
        </div>)}

      {quick.some((q) => q[3]) && (
        <section aria-label="Quick actions" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {quick.filter((q) => q[3]).map(([to, label, Icon]) => <Link key={to} to={`${base}/${to}`} className="card flex items-center gap-3 p-4 text-sm font-semibold transition hover:border-primary hover:shadow-md"><span className="grid h-10 w-10 place-items-center rounded-lg bg-teal-50 text-teal-700"><Icon size={19} aria-hidden /></span><span className="flex-1">{label}</span><ArrowRight size={16} aria-hidden className="text-slate-400" /></Link>)}
        </section>)}
    </div>
  );
}
