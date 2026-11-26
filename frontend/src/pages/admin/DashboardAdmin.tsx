import { useQuery } from "@tanstack/react-query";
import { Building2, CircleCheck, CirclePause, Clock, Database, Mail, Plus, ShieldCheck, Store, UserRound, Users, Wallet } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ChartCard, DonutChart, RankBars, TrendChart, itemsTable, type Item } from "../../components/charts";
import { DataTable, ErrorState, Loading, StatCard, StatusBadge, errorMessage } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, money } from "../../lib/format";

interface Dash {
  pharmacies: { total: number; active: number; suspended: number; deactivated: number };
  branches: number; users: number; customers: number;
  subscription_revenue: { collected: string | number; refunded: string | number; outstanding: string | number };
  usage: { emails_sent_30d: number; emails_failed_30d: number };
  system_health: { database: string };
  recent_activity: { id: number; action: string; actor: string | null; tenant: string | null; at: string }[];
}
interface Analytics {
  pharmacies: { by_status: Item[]; by_country: Item[] }; users: { total: number; customers: number; staff: number; top_pharmacies: Item[] };
  monthly: { month: string; pharmacies: number; revenue: string | number }[]; logins: { date: string; logins: number }[]; subscriptions: Item[]; invoices: Item[]; emails: Item[];
  last_backup: { number: string; created_at: string; verification: string } | null;
}
const shortDay = (v: string) => new Date(`${v}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });

export default function DashboardAdmin() {
  const { user } = useAuth();
  const [days, setDays] = useState(30);
  const base = useQuery({ queryKey: ["platform-dashboard"], queryFn: () => api<Dash>("/platform/dashboard/") });
  const a = useQuery({ queryKey: ["analytics", "platform", days], queryFn: () => api<Analytics>(`/analytics/platform/?days=${days}`), placeholderData: (p) => p });
  if (base.isLoading) return <Loading rows={6} label="Preparing the platform dashboard…" />;
  if (!base.data) return <ErrorState onRetry={() => base.refetch()}>{errorMessage(base.error)}</ErrorState>;
  const d = base.data, x = a.data;
  const donut = (title: string, items: Item[] | undefined, name: string, center: string) => <ChartCard title={title} table={itemsTable(name, "Count", items)}><DonutChart items={items ?? []} centerLabel={center} /></ChartCard>;
  return (
    <div className="space-y-6">
      <section className="hero-surface animate-rise rounded-3xl p-6 sm:p-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div><p className="text-sm text-white/75">Platform administration</p><h1 className="mt-1 text-2xl !font-extrabold sm:text-3xl">Welcome, {user?.full_name}</h1><p className="mt-1 text-sm text-white/75">Tenants, subscription revenue and system health.</p></div>
          <div role="group" aria-label="Period" className="glass flex gap-1 rounded-2xl p-1">{[7, 30, 90].map((v) => <button key={v} type="button" aria-pressed={days === v} onClick={() => setDays(v)} className={`rounded-xl px-3 py-1.5 text-sm font-semibold ${days === v ? "bg-[#fff]" : "text-white/85 hover:bg-white/10"}`} style={days === v ? { color: "#0b1324" } : undefined}>{v} days</button>)}</div>
        </div>
        <div className="mt-6 flex flex-wrap gap-2"><Link to="/platform/pharmacies?new=1" className="btn btn-primary"><Plus size={16} aria-hidden />Register pharmacy</Link><Link to="/platform/billing" className="btn glass text-white"><Wallet size={16} aria-hidden />Billing</Link><Link to="/platform/backups" className="btn glass text-white"><ShieldCheck size={16} aria-hidden />Backups</Link></div>
      </section>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Pharmacies" value={d.pharmacies.total} icon={Store} to="/platform/pharmacies" />
        <StatCard label="Active" value={d.pharmacies.active} icon={CircleCheck} />
        <StatCard label="Suspended" value={d.pharmacies.suspended} icon={CirclePause} tone="warning" />
        <StatCard label="Branches" value={d.branches} icon={Building2} tone="navy" />
        <StatCard label="Staff users" value={d.users} icon={Users} tone="navy" />
        <StatCard label="Customers" value={d.customers} icon={UserRound} tone="info" />
        <StatCard label="Revenue collected" value={money(d.subscription_revenue.collected)} icon={Wallet} hint={`Refunded ${money(d.subscription_revenue.refunded)}`} />
        <StatCard label="Outstanding" value={money(d.subscription_revenue.outstanding)} icon={Clock} tone="warning" to="/platform/billing" />
      </div>
      {a.isLoading && <Loading rows={3} />}
      {a.isError && <ErrorState onRetry={() => a.refetch()}>{errorMessage(a.error)}</ErrorState>}
      {x && <>
        <div className="grid gap-5 xl:grid-cols-2">
          <ChartCard title="Pharmacy registrations" subtitle="Last 12 months" table={{ head: ["Month", "Registrations"], rows: x.monthly.map((r) => [r.month, r.pharmacies]) }}><TrendChart kind="column" rows={x.monthly} x="month" series={[{ key: "pharmacies", label: "Registrations" }]} /></ChartCard>
          <ChartCard title="Subscription revenue" subtitle="Paid invoices by month" table={{ head: ["Month", "Revenue"], rows: x.monthly.map((r) => [r.month, Number(r.revenue)]) }}><TrendChart rows={x.monthly} x="month" format={(n) => money(n)} series={[{ key: "revenue", label: "Revenue" }]} /></ChartCard>
        </div>
        <div className="grid gap-5 xl:grid-cols-3">
          <ChartCard className="xl:col-span-2" title="Successful sign-ins" subtitle={`Last ${days} days`} table={{ head: ["Date", "Sign-ins"], rows: x.logins.map((r) => [shortDay(r.date), r.logins]) }}><TrendChart rows={x.logins} x="date" xLabel={shortDay} series={[{ key: "logins", label: "Sign-ins" }]} /></ChartCard>
          {donut("Pharmacy status", x.pharmacies.by_status, "Status", "Pharmacies")}
          <ChartCard title="Largest pharmacies" subtitle="By user accounts" table={itemsTable("Pharmacy", "Users", x.users.top_pharmacies)}><RankBars items={x.users.top_pharmacies} /></ChartCard>
          {donut("Plans in use", x.subscriptions, "Plan", "Subscriptions")}
          {donut("Invoices", x.invoices, "Status", "Invoices")}
          {donut("Pharmacies by country", x.pharmacies.by_country, "Country", "Pharmacies")}
          {donut("Email delivery", x.emails, "Status", "Emails")}
          <section className="card space-y-4 p-5 text-sm">
            <h2 className="section-title">System health</h2>
            <div className="flex items-center justify-between"><span className="flex items-center gap-2"><Database size={17} aria-hidden />Database</span><StatusBadge status={d.system_health.database} tone={d.system_health.database === "ok" ? "success" : "danger"} /></div>
            <div className="flex items-center justify-between"><span className="flex items-center gap-2"><Mail size={17} aria-hidden />Emails sent (30 days)</span><b>{d.usage.emails_sent_30d}</b></div>
            <div className="flex items-center justify-between"><span className="flex items-center gap-2"><Mail size={17} aria-hidden />Emails failed (30 days)</span><b className={d.usage.emails_failed_30d ? "text-danger" : ""}>{d.usage.emails_failed_30d}</b></div>
            <div className="border-t border-line pt-3"><p className="text-muted">Last completed backup</p><p className="font-bold">{x.last_backup ? x.last_backup.number : "None yet"}</p>{x.last_backup && <p className="text-xs text-muted">{dateTime(x.last_backup.created_at)}</p>}</div>
          </section>
        </div>
      </>}
      <section className="space-y-3"><h2 className="section-title">Recent activity</h2>
        <DataTable rows={d.recent_activity} rowKey={(r) => r.id} pageSize={8} empty="No activity yet." columns={[{ key: "action", header: "Action", render: (r) => <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{r.action}</code> }, { key: "actor", header: "By", render: (r) => r.actor ?? "system" }, { key: "tenant", header: "Pharmacy", render: (r) => r.tenant ?? "—" }, { key: "at", header: "When", render: (r) => dateTime(r.at), sort: (r) => r.at }]} />
      </section>
    </div>
  );
}
