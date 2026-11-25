import { useQuery } from "@tanstack/react-query";
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

const Card = ({ label, value }: { label: string; value: string | number }) => (
  <div className="rounded-xl bg-white p-4 shadow-sm"><p className="text-xs uppercase text-slate-500">{label}</p><p className="text-2xl font-semibold">{value}</p></div>
);

export default function DashboardAdmin() {
  const { data, isLoading, isError } = useQuery({ queryKey: ["platform-dashboard"], queryFn: () => api<Dash>("/platform/dashboard/") });
  if (isLoading) return <p>Loading dashboard…</p>;
  if (isError || !data) return <p role="alert">The dashboard could not be loaded.</p>;
  const max = Math.max(1, ...data.registration_trend.map((t) => t.count));
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Platform dashboard</h1>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card label="Pharmacies" value={data.pharmacies.total} />
        <Card label="Active" value={data.pharmacies.active} />
        <Card label="Suspended" value={data.pharmacies.suspended} />
        <Card label="Branches" value={data.branches} />
        <Card label="Staff users" value={data.users} />
        <Card label="Customers" value={data.customers} />
        <Card label="Collected" value={Number(data.subscription_revenue.collected).toLocaleString()} />
        <Card label="Outstanding" value={Number(data.subscription_revenue.outstanding).toLocaleString()} />
      </div>
      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="mb-3 font-semibold">Pharmacy registrations (last 12 months)</h2>
        {data.registration_trend.length === 0 ? <p className="text-sm text-slate-500">No registrations yet.</p> : (
          <div className="flex h-32 items-end gap-2" role="img" aria-label="Registrations per month">
            {data.registration_trend.map((t) => (
              <div key={t.month} className="flex flex-1 flex-col items-center text-xs">
                <div className="w-full rounded-t bg-teal-600" style={{ height: `${(t.count / max) * 100}%` }} title={`${t.count}`} />
                <span>{t.month.slice(2)}</span>
              </div>
            ))}
          </div>
        )}
      </section>
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl bg-white p-4 shadow-sm">
          <h2 className="mb-2 font-semibold">System health</h2>
          <p>Database: <strong className={data.system_health.database === "ok" ? "text-green-700" : "text-red-700"}>{data.system_health.database}</strong></p>
          <p className="text-sm text-slate-600">Emails 30d: {data.usage.emails_sent_30d} sent, {data.usage.emails_failed_30d} failed</p>
        </section>
        <section className="rounded-xl bg-white p-4 shadow-sm">
          <h2 className="mb-2 font-semibold">Recent activity</h2>
          <ul className="space-y-1 text-sm">
            {data.recent_activity.map((a) => <li key={a.id}><code>{a.action}</code> {a.actor ?? "system"} {a.tenant ? `· ${a.tenant}` : ""}</li>)}
          </ul>
        </section>
      </div>
    </div>
  );
}
