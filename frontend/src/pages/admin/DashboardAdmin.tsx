import { useQuery } from "@tanstack/react-query";
import { Building2, CircleCheck, CirclePause, Database, Mail, Store, Users, Wallet, Clock, UserRound } from "lucide-react";
import { BarList, EmptyState, ErrorState, Loading, PageHeader, StatCard, StatusBadge } from "../../components/ui";
import { api } from "../../lib/api";

interface Dash {
  pharmacies: { total: number; active: number; suspended: number; deactivated: number };
  branches: number; users: number; customers: number;
  subscription_revenue: { collected: string | number; refunded: string | number; outstanding: string | number };
  registration_trend: { month: string; count: number }[];
  usage: { emails_sent_30d: number; emails_failed_30d: number };
  system_health: { database: string };
  recent_activity: { id: number; action: string; actor: string | null; tenant: string | null; at: string }[];
}

export default function DashboardAdmin() {
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ["platform-dashboard"], queryFn: () => api<Dash>("/platform/dashboard/") });
  if (isLoading) return <Loading rows={5} />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()}>The dashboard could not be loaded.</ErrorState>;
  const money = (v: string | number) => Number(v).toLocaleString();
  return (
    <div className="space-y-6">
      <PageHeader title="Platform dashboard" subtitle="Tenants, subscription revenue and system health." />
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label="Pharmacies" value={data.pharmacies.total} icon={Store} />
        <StatCard label="Active" value={data.pharmacies.active} icon={CircleCheck} />
        <StatCard label="Suspended" value={data.pharmacies.suspended} icon={CirclePause} tone="warning" />
        <StatCard label="Branches" value={data.branches} icon={Building2} tone="navy" />
        <StatCard label="Staff users" value={data.users} icon={Users} tone="navy" />
        <StatCard label="Customers" value={data.customers} icon={UserRound} tone="info" />
        <StatCard label="Revenue collected" value={money(data.subscription_revenue.collected)} icon={Wallet} />
        <StatCard label="Outstanding" value={money(data.subscription_revenue.outstanding)} icon={Clock} tone="warning" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <section className="card p-5 lg:col-span-2">
          <h2 className="section-title mb-4">Pharmacy registrations by month</h2>
          <BarList empty="No registrations yet." items={data.registration_trend.map((t) => ({ label: t.month, value: t.count }))} />
        </section>
        <section className="card space-y-4 p-5">
          <h2 className="section-title">System health</h2>
          <div className="flex items-center justify-between text-sm"><span className="flex items-center gap-2"><Database size={17} aria-hidden className="text-muted" />Database</span><StatusBadge status={data.system_health.database} tone={data.system_health.database === "ok" ? "success" : "danger"} /></div>
          <div className="flex items-center justify-between text-sm"><span className="flex items-center gap-2"><Mail size={17} aria-hidden className="text-muted" />Emails sent (30 days)</span><strong>{data.usage.emails_sent_30d}</strong></div>
          <div className="flex items-center justify-between text-sm"><span className="flex items-center gap-2"><Mail size={17} aria-hidden className="text-muted" />Emails failed (30 days)</span><strong className={data.usage.emails_failed_30d ? "text-danger" : ""}>{data.usage.emails_failed_30d}</strong></div>
        </section>
      </div>
      <section className="space-y-3">
        <h2 className="section-title">Recent activity</h2>
        {data.recent_activity.length === 0 ? <EmptyState>No activity yet.</EmptyState> : (
          <div className="table-wrap"><table className="table"><thead><tr><th>Action</th><th>By</th><th>Pharmacy</th><th>When</th></tr></thead>
            <tbody>{data.recent_activity.map((a) => <tr key={a.id}><td><code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{a.action}</code></td><td>{a.actor ?? "system"}</td><td>{a.tenant ?? "—"}</td><td className="whitespace-nowrap">{new Date(a.at).toLocaleString()}</td></tr>)}</tbody></table></div>)}
      </section>
    </div>
  );
}
