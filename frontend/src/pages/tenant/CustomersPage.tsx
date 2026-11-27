/** Customers who registered on the pharmacy website: list and full profile. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BadgeCheck, CalendarDays, Mail, MapPin, Package, Phone, Power, ShieldAlert, Star, UserCheck, UserPlus, Users, Wallet } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Avatar, DataTable, EmptyState, Loading, PageHeader, StatCard, StatusBadge, Tabs, errorMessage, useConfirm, useToast } from "../../components/ui";
import { ServerTable, type ApiPage } from "../../components/ui/ServerTable";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, day, money, words } from "../../lib/format";

interface Customer { id: number; full_name: string; email: string; phone: string; avatar: string | null; email_verified: boolean; is_active: boolean; joined: string; address: string; gender: string; orders: number; spent: string; last_order: string | null }
interface Detail extends Customer {
  last_login: string | null; date_of_birth: string | null; delivery_addresses: { label: string; address: string }[]; emergency_contact_name: string; emergency_contact_phone: string;
  notification_prefs: { email_orders?: boolean; email_marketing?: boolean }; terms_version: string; terms_accepted_at: string | null; signed_up_with: string;
  recent_orders: { id: number; reference_number: string; status: string; total: string; branch: string; fulfilment: string; payment_method: string; created_at: string }[];
  appointments: { id: number; service: string; status: string; start_at: string }[];
  inquiries: { id: number; kind: string; message: string; status: string; response: string; created_at: string }[];
  feedback: { id: number; rating: number; comment: string; response: string; created_at: string }[];
}
const stateOf = (c: Customer) => (!c.is_active ? "deactivated" : c.email_verified ? "verified" : "pending");

export default function CustomersPage() {
  const { slug = "" } = useParams(); const nav = useNavigate();
  const open = (c: Customer) => nav(`/${slug}/admin/customers/${c.id}`);
  const summary = useQuery({ queryKey: ["customers", "summary"], queryFn: () => api<ApiPage<Customer> & { summary: { total: number; verified: number; new_30_days: number; with_orders: number } }>("/customers/") });
  const s = summary.data?.summary;
  return (
    <div className="space-y-5">
      <PageHeader title="Customers" subtitle="Everyone who created an account on your pharmacy website." />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Registered" value={s?.total ?? "…"} icon={Users} /><StatCard label="Verified" value={s?.verified ?? "…"} icon={UserCheck} tone="info" />
        <StatCard label="New in 30 days" value={s?.new_30_days ?? "…"} icon={UserPlus} tone="navy" /><StatCard label="Have ordered" value={s?.with_orders ?? "…"} icon={Package} tone="warning" />
      </div>
      <ServerTable<Customer> queryKey={["customers"]} path="/customers/" rowKey={(c) => c.id} search="Enter your name, email or phone search" empty="No customers have registered yet." onRowClick={open}
        filters={[{ name: "status", label: "All customers", options: [["verified", "Verified"], ["unverified", "Not verified"], ["inactive", "Deactivated"]] }, { name: "ordering", label: "Newest first", options: [["joined", "Oldest first"], ["name", "Name A–Z"], ["-name", "Name Z–A"]] }]}
        columns={[
          { key: "name", header: "Customer", render: (c) => <span className="flex items-center gap-3"><Avatar src={c.avatar} name={c.full_name} size={42} /><span><Link className="block font-bold" to={`/${slug}/admin/customers/${c.id}`}>{c.full_name}</Link><span className="text-xs text-muted">{c.email}</span></span></span> },
          { key: "phone", header: "Phone", render: (c) => c.phone || "—" }, { key: "address", header: "Address", render: (c) => c.address || "—" }, { key: "joined", header: "Joined", render: (c) => day(c.joined) },
          { key: "orders", header: "Orders", align: "center", render: (c) => c.orders }, { key: "spent", header: "Spent", align: "right", render: (c) => <b>{money(c.spent)}</b> }, { key: "last", header: "Last order", render: (c) => day(c.last_order) },
          { key: "status", header: "Status", render: (c) => <StatusBadge status={stateOf(c)} /> }, { key: "actions", header: "Actions", align: "right", render: (c) => <button className="btn-link" onClick={() => open(c)}>View profile</button> },
        ]} />
    </div>
  );
}

export function CustomerDetailPage() {
  const { slug = "", customerId = "" } = useParams(); const { can } = useAuth(); const qc = useQueryClient(); const toast = useToast(); const confirm = useConfirm();
  const [tab, setTab] = useState<"orders" | "appointments" | "inquiries" | "feedback">("orders");
  const q = useQuery({ queryKey: ["customers", "one", customerId], queryFn: () => api<Detail>(`/customers/${customerId}/`), retry: false });
  const back = <Link to={`/${slug}/admin/customers`} className="btn btn-outline btn-sm"><ArrowLeft size={15} aria-hidden />All customers</Link>;
  if (q.isLoading) return <Loading rows={5} label="Opening profile…" />;
  if (!q.data) return <div className="space-y-4">{back}<EmptyState>{errorMessage(q.error)}</EmptyState></div>;
  const c = q.data;
  const toggle = async () => {
    const off = c.is_active;
    if (!(await confirm({ title: `${off ? "Deactivate" : "Reactivate"} ${c.full_name}?`, message: off ? "They are signed out everywhere and cannot sign in. Their history is kept." : "They will be able to sign in again.", confirmLabel: off ? "Deactivate" : "Reactivate", danger: off }))) return;
    api<Detail>(`/customers/${c.id}/`, { method: "PATCH", body: { is_active: !off } }).then((d) => { qc.setQueryData(["customers", "one", customerId], d); qc.invalidateQueries({ queryKey: ["customers"] }); toast("Customer updated."); }).catch((e) => toast(errorMessage(e), "error"));
  };
  const info: [string, string][] = [["Gender", c.gender || "Not given"], ["Date of birth", c.date_of_birth ? day(c.date_of_birth) : "Not given"], ["Signed up with", c.signed_up_with], ["Last sign-in", dateTime(c.last_login)], ["Terms accepted", c.terms_accepted_at ? `${day(c.terms_accepted_at)} (version ${c.terms_version})` : "—"], ["Order emails", c.notification_prefs.email_orders === false ? "Off" : "On"], ["Marketing emails", c.notification_prefs.email_marketing ? "On" : "Off"]];
  return (
    <div className="space-y-5">
      {back}
      <section className="card animate-rise overflow-hidden">
        <div className="hero-surface h-28" />
        <div className="flex flex-wrap items-end gap-4 px-5 pb-5">
          <div className="-mt-12 rounded-full border-4 border-[var(--color-surface)]"><Avatar src={c.avatar} name={c.full_name} size={104} /></div>
          <div className="min-w-0 flex-1 pt-3"><h1 className="page-title flex flex-wrap items-center gap-2">{c.full_name}{c.email_verified && <BadgeCheck size={20} aria-label="Verified" className="text-primary" />}<StatusBadge status={stateOf(c)} /></h1>
            <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted"><li className="flex items-center gap-1.5 break-all"><Mail size={14} aria-hidden /><a href={`mailto:${c.email}`} className="hover:underline">{c.email}</a></li><li className="flex items-center gap-1.5"><Phone size={14} aria-hidden />{c.phone || "No phone"}</li><li className="flex items-center gap-1.5"><CalendarDays size={14} aria-hidden />Joined {day(c.joined)}</li></ul></div>
          {can("customer.manage") && <button className={`btn ${c.is_active ? "btn-outline btn-link-danger" : "btn-primary"}`} onClick={toggle}><Power size={15} aria-hidden />{c.is_active ? "Deactivate" : "Reactivate"}</button>}
        </div>
      </section>
      <div className="grid gap-4 sm:grid-cols-3"><StatCard label="Orders" value={c.orders} icon={Package} /><StatCard label="Total spent" value={money(c.spent)} icon={Wallet} tone="navy" /><StatCard label="Last order" value={day(c.last_order)} icon={CalendarDays} tone="info" /></div>
      <div className="grid items-start gap-5 xl:grid-cols-3">
        <section className="card p-5 text-sm"><h2 className="section-title">Profile</h2><dl className="mt-3 space-y-2.5">{info.map(([k, v]) => <div key={k} className="flex justify-between gap-3 border-b border-line pb-2"><dt className="text-muted">{k}</dt><dd className="text-right font-semibold">{v}</dd></div>)}</dl></section>
        <section className="card p-5 text-sm"><h2 className="section-title">Addresses</h2><p className="mt-3 flex gap-2"><MapPin size={15} aria-hidden className="mt-0.5 shrink-0" /><span><b className="block">Home</b>{c.address || "Not given"}</span></p>
          {c.delivery_addresses.map((a, i) => <p key={i} className="mt-3 flex gap-2"><MapPin size={15} aria-hidden className="mt-0.5 shrink-0" /><span><b className="block">{a.label || "Delivery address"}</b>{a.address}</span></p>)}</section>
        <section className="card p-5 text-sm"><h2 className="section-title flex items-center gap-2"><ShieldAlert size={16} aria-hidden />Emergency contact</h2><p className="mt-3 font-semibold">{c.emergency_contact_name || "Not given"}</p><p className="text-muted">{c.emergency_contact_phone}</p></section>
      </div>
      <Tabs tabs={[["orders", "Orders", c.recent_orders.length], ["appointments", "Appointments", c.appointments.length], ["inquiries", "Enquiries", c.inquiries.length], ["feedback", "Feedback", c.feedback.length]]} value={tab} onChange={setTab} />
      {tab === "orders" && <DataTable rows={c.recent_orders} rowKey={(o) => o.id} search={(o) => `${o.reference_number} ${o.status}`} empty="No orders yet."
        columns={[{ key: "ref", header: "Order", render: (o) => can("order.manage") ? <Link className="font-bold text-primary" to={`/${slug}/admin/orders/${o.id}`}>{o.reference_number}</Link> : <b>{o.reference_number}</b> }, { key: "date", header: "Placed", render: (o) => dateTime(o.created_at), sort: (o) => o.created_at }, { key: "branch", header: "Branch", render: (o) => o.branch }, { key: "fulfilment", header: "Fulfilment", render: (o) => <span className="capitalize">{o.fulfilment}</span> }, { key: "payment", header: "Payment", render: (o) => <span className="capitalize">{o.payment_method === "monime" ? "Mobile money" : words(o.payment_method)}</span> }, { key: "status", header: "Status", render: (o) => <StatusBadge status={o.status} /> }, { key: "total", header: "Total", align: "right", render: (o) => <b>{money(o.total)}</b>, sort: (o) => Number(o.total) }]} />}
      {tab === "appointments" && <DataTable rows={c.appointments} rowKey={(a) => a.id} empty="No appointments." columns={[{ key: "service", header: "Service", render: (a) => <b>{a.service}</b> }, { key: "when", header: "When", render: (a) => dateTime(a.start_at) }, { key: "status", header: "Status", render: (a) => <StatusBadge status={a.status} /> }]} />}
      {tab === "inquiries" && <DataTable rows={c.inquiries} rowKey={(i) => i.id} empty="No enquiries." columns={[{ key: "kind", header: "Type", render: (i) => <span className="capitalize">{words(i.kind)}</span> }, { key: "message", header: "Message", render: (i) => <>{i.message}{i.response && <span className="block text-xs text-success">Reply: {i.response}</span>}</> }, { key: "status", header: "Status", render: (i) => <StatusBadge status={i.status} /> }, { key: "date", header: "Sent", render: (i) => day(i.created_at) }]} />}
      {tab === "feedback" && <DataTable rows={c.feedback} rowKey={(f) => f.id} empty="No feedback." columns={[{ key: "rating", header: "Rating", render: (f) => <span className="flex items-center gap-1 font-bold"><Star size={14} aria-hidden className="text-amber-500" fill="currentColor" />{f.rating}/5</span> }, { key: "comment", header: "Comment", render: (f) => f.comment || "—" }, { key: "response", header: "Reply", render: (f) => f.response || "—" }, { key: "date", header: "Date", render: (f) => day(f.created_at) }]} />}
    </div>
  );
}
