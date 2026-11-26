/** Customer engagement (appointments, enquiries, feedback, institutional requests, services) and deliveries. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Power, Star, Truck } from "lucide-react";
import { useState } from "react";
import { DataTable, FormModal, PageHeader, StatCard, StatusBadge, Tabs, errorMessage, useConfirm, usePrompt, useToast, type FieldDef, type Values } from "../../components/ui";
import { ServerTable, type ApiPage } from "../../components/ui/ServerTable";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, money, words } from "../../lib/format";

interface Appt { id: number; service: string; start_at: string; status: string; customer_name: string; customer_phone: string; customer_note: string }
interface Inq { id: number; kind: string; message: string; status: string; response: string; customer: string; phone: string }
interface Fb { id: number; rating: number; comment: string; status: string; response: string; customer: string }
interface Inst { id: number; organisation: string; contact_person: string; email: string; phone: string; service_required: string; products_required: string; quantity: string; status: string; details: string }
interface Svc { id: number; name: string; description: string; price: string | null; is_available: boolean; requires_booking: boolean; duration_minutes: number; capacity: number; image: string | null }
interface Del { id: number; order: number; reference: string; status: string; driver_name: string; order_status: string; address?: string; customer_name?: string; customer_phone?: string; collect?: string | null }
type Tab = "appointments" | "inquiries" | "feedback" | "institutional" | "services";

function useActions(keys: string[]) {
  const qc = useQueryClient(); const toast = useToast();
  const done = (t: string) => { keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] })); toast(t); };
  const post = (path: string, body: object, text: string) => api(path, { method: "POST", body }).then(() => done(text)).catch((e) => toast(errorMessage(e), "error"));
  return { done, post, toast };
}

const serviceFields = (s?: Svc): FieldDef[] => [
  { name: "name", label: "Service name", defaultValue: s?.name }, { name: "price", label: "Price", type: "number", min: 0, step: "0.01", required: false, defaultValue: s?.price },
  { name: "duration_minutes", label: "Duration in minutes", type: "number", min: 5, step: "1", defaultValue: s?.duration_minutes ?? 30 }, { name: "capacity", label: "Bookings per time slot", type: "number", min: 1, step: "1", defaultValue: s?.capacity ?? 1 },
  { name: "description", label: "Service description", type: "textarea", required: false, defaultValue: s?.description },
  { name: "image", label: "Service picture", type: "file", accept: "image/png,image/jpeg,image/webp", wide: true },
  { name: "requires_booking", label: "Customers must book this service", type: "checkbox", defaultValue: s?.requires_booking ?? true },
];

export function EngagementPage() {
  const prompt = usePrompt(); const confirm = useConfirm(); const { can } = useAuth();
  const { done, post, toast } = useActions(["e-appts", "e-inq", "e-fb", "e-inst", "e-svc"]);
  const [tab, setTab] = useState<Tab>("appointments");
  const [service, setService] = useState<Svc | "new" | null>(null);
  const services = useQuery({ queryKey: ["e-svc"], queryFn: () => api<Svc[]>("/services/"), enabled: tab === "services" && can("service.manage") });
  const appointment = async (a: Appt, status: string, label: string) => { const v = await prompt({ title: `${label} appointment`, message: `${a.service} · ${a.customer_name} · ${dateTime(a.start_at)}`, confirmLabel: label, danger: status === "cancelled", fields: [{ name: "note", label: "Note for the customer", type: "textarea", required: false }] }); if (v) post(`/appointments/${a.id}/status/`, { status, note: v.note }, "Appointment updated."); };
  const respond = async (path: string, label: string, extra: object = {}) => { const v = await prompt({ title: "Send a response", confirmLabel: "Send", fields: [{ name: "response", label, type: "textarea" }] }); if (v?.response) post(path, { response: v.response, ...extra }, "Response sent."); };
  const saveService = async (v: Values, files: Record<string, File | null>) => {
    const data: Record<string, string> = { name: v.name, description: v.description, duration_minutes: v.duration_minutes, capacity: v.capacity, requires_booking: v.requires_booking ? "true" : "false" };
    const fd = new FormData(); Object.entries(data).forEach(([k, x]) => fd.append(k, x)); fd.append("price", v.price); if (files.image) fd.append("image", files.image);
    const body = files.image ? fd : { ...data, price: v.price || null, requires_booking: !!v.requires_booking };
    await api(service === "new" ? "/services/" : `/services/${(service as Svc).id}/`, { method: service === "new" ? "POST" : "PATCH", body });
    done("Service saved.");
  };
  const tabs: [Tab, string][] = [["appointments", "Appointments"], ["inquiries", "Enquiries"], ["feedback", "Feedback"], ["institutional", "Institutional"], ...(can("service.manage") ? [["services", "Services"] as [Tab, string]] : [])];
  return (
    <div className="space-y-5">
      <PageHeader title="Customer services" subtitle="Appointments, enquiries, feedback and the services you offer." actions={tab === "services" && <button className="btn btn-primary" onClick={() => setService("new")}><Plus size={16} aria-hidden />Add service</button>} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === "appointments" && <ServerTable<Appt> queryKey={["e-appts"]} path="/appointments/" rowKey={(a) => a.id} empty="No appointments." filters={[{ name: "status", label: "All statuses", options: ["requested", "confirmed", "completed", "cancelled", "no_show"].map((s) => [s, words(s)]) }]}
        columns={[{ key: "service", header: "Service", render: (a) => <b>{a.service}</b> }, { key: "customer", header: "Customer", render: (a) => <><b className="block">{a.customer_name}</b><span className="text-xs text-muted">{a.customer_phone}</span></> }, { key: "when", header: "When", render: (a) => dateTime(a.start_at) }, { key: "note", header: "Note", render: (a) => a.customer_note || "—" }, { key: "status", header: "Status", render: (a) => <StatusBadge status={a.status} /> },
          { key: "actions", header: "Actions", align: "right", render: (a) => <span className="inline-flex gap-1.5">{a.status === "requested" && <button className="btn-link" onClick={() => appointment(a, "confirmed", "Confirm")}>Confirm</button>}{a.status === "confirmed" && <><button className="btn-link" onClick={() => appointment(a, "completed", "Complete")}>Completed</button><button className="btn-link" onClick={() => appointment(a, "no_show", "Mark no-show")}>No-show</button></>}{["requested", "confirmed"].includes(a.status) && <button className="btn-link btn-link-danger" onClick={() => appointment(a, "cancelled", "Cancel")}>Cancel</button>}</span> }]} />}
      {tab === "inquiries" && <ServerTable<Inq> queryKey={["e-inq"]} path="/inquiries/" rowKey={(i) => i.id} empty="No enquiries."
        columns={[{ key: "customer", header: "Customer", render: (i) => <><b className="block">{i.customer}</b><span className="text-xs text-muted">{i.phone}</span></> }, { key: "kind", header: "Type", render: (i) => <span className="capitalize">{words(i.kind)}</span> }, { key: "message", header: "Message", render: (i) => <>{i.message}{i.response && <span className="mt-1 block text-xs text-success">Reply: {i.response}</span>}</> }, { key: "status", header: "Status", render: (i) => <StatusBadge status={i.status} /> }, { key: "actions", header: "Actions", align: "right", render: (i) => i.status !== "answered" && <button className="btn-link" onClick={() => respond(`/inquiries/${i.id}/respond/`, "Reply")}>Reply</button> }]} />}
      {tab === "feedback" && <ServerTable<Fb> queryKey={["e-fb"]} path="/feedback/" rowKey={(f) => f.id} empty="No feedback yet."
        columns={[{ key: "rating", header: "Rating", render: (f) => <span aria-label={`${f.rating} out of 5`} className="flex gap-0.5 text-amber-500">{[1, 2, 3, 4, 5].map((n) => <Star key={n} size={14} fill={n <= f.rating ? "currentColor" : "none"} aria-hidden />)}</span> }, { key: "customer", header: "Customer", render: (f) => <b>{f.customer}</b> }, { key: "comment", header: "Comment", render: (f) => <>{f.comment || "—"}{f.response && <span className="mt-1 block text-xs text-success">Reply: {f.response}</span>}</> }, { key: "status", header: "Status", render: (f) => <StatusBadge status={f.status} /> }, { key: "actions", header: "Actions", align: "right", render: (f) => f.status === "new" && <button className="btn-link" onClick={() => respond(`/feedback/${f.id}/respond/`, "Reply")}>Reply</button> }]} />}
      {tab === "institutional" && <ServerTable<Inst> queryKey={["e-inst"]} path="/institutional-requests/" rowKey={(r) => r.id} empty="No requests."
        columns={[{ key: "org", header: "Organisation", render: (r) => <><b className="block">{r.organisation}</b><span className="text-xs text-muted">{r.contact_person} · {r.email} · {r.phone}</span></> }, { key: "need", header: "Request", render: (r) => <>{r.service_required}{r.products_required && `: ${r.products_required}`}{r.quantity && ` (${r.quantity})`}{r.details && <span className="block text-xs text-muted">{r.details}</span>}</> }, { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
          { key: "actions", header: "Actions", align: "right", render: (r) => r.status !== "closed" && <span className="inline-flex gap-1.5"><button className="btn-link" onClick={() => respond(`/institutional-requests/${r.id}/respond/`, "Quotation or response", { status: "quoted" })}>Send quotation</button><button className="btn-link btn-link-danger" onClick={async () => { if (await confirm({ title: "Close this request?", message: r.organisation, confirmLabel: "Close", danger: true })) post(`/institutional-requests/${r.id}/respond/`, { status: "closed" }, "Request closed."); }}>Close</button></span> }]} />}
      {tab === "services" && <DataTable<Svc> rows={services.data} loading={services.isLoading} rowKey={(s) => s.id} search={(s) => s.name} empty="No services yet."
        columns={[{ key: "name", header: "Service", sort: (s) => s.name, render: (s) => <><b className="block">{s.name}</b><span className="line-clamp-1 text-xs text-muted">{s.description}</span></> }, { key: "price", header: "Price", align: "right", render: (s) => s.price ? money(s.price) : "On request" }, { key: "duration", header: "Duration", align: "center", render: (s) => `${s.duration_minutes} min` }, { key: "capacity", header: "Per slot", align: "center", render: (s) => s.capacity }, { key: "booking", header: "Booking", render: (s) => s.requires_booking ? "Required" : "Walk in" }, { key: "status", header: "Status", render: (s) => <StatusBadge status={s.is_available ? "available" : "inactive"} /> },
          { key: "actions", header: "Actions", align: "right", render: (s) => <span className="inline-flex gap-1.5"><button className="btn-link" onClick={() => setService(s)}><Pencil size={13} aria-hidden />Edit</button><button className={`btn-link ${s.is_available ? "btn-link-danger" : ""}`} onClick={async () => { if (await confirm({ title: `${s.is_available ? "Delete" : "Restore"} ${s.name}?`, message: s.is_available ? "It is removed from your website. Past bookings are kept." : "It appears on your website again.", confirmLabel: s.is_available ? "Delete" : "Restore", danger: s.is_available })) api(`/services/${s.id}/`, { method: "PATCH", body: { is_available: !s.is_available } }).then(() => done("Service updated.")).catch((e) => toast(errorMessage(e), "error")); }}><Power size={13} aria-hidden />{s.is_available ? "Delete" : "Restore"}</button></span> }]} />}
      {service && <FormModal title={service === "new" ? "Add service" : `Edit ${service.name}`} size="lg" fields={serviceFields(service === "new" ? undefined : service)} onClose={() => setService(null)} onSubmit={saveService} />}
    </div>
  );
}

export function DeliveriesPage() {
  const prompt = usePrompt(); const confirm = useConfirm(); const { can } = useAuth();
  const { post, toast } = useActions(["deliveries", "my-deliveries", "staff-orders", "drivers"]);
  const manage = can("delivery.manage"), perform = can("delivery.perform");
  const list = useQuery({ queryKey: ["deliveries"], queryFn: () => api<ApiPage<Del>>("/deliveries/?page_size=100"), enabled: manage, refetchInterval: 20000 });
  const drivers = useQuery({ queryKey: ["drivers"], queryFn: () => api<{ id: number; name: string }[]>("/deliveries/drivers/"), enabled: manage });
  const mine = useQuery({ queryKey: ["my-deliveries"], queryFn: () => api<Del[]>("/deliveries/mine/"), enabled: perform, refetchInterval: 20000 });
  const orders = useQuery({ queryKey: ["staff-orders", "preparing"], queryFn: () => api<ApiPage<{ id: number; reference_number: string; fulfilment: string; delivery_address: string; customer_name: string }>>("/orders/?status=preparing&page_size=100"), enabled: manage && can("order.manage") });
  const assign = async (order: number) => {
    if (!drivers.data?.length) { toast("Add a staff member with the Delivery Personnel role first.", "error"); return; }
    const v = await prompt({ title: "Assign a driver", confirmLabel: "Assign", fields: [{ name: "driver", label: "Driver", type: "select", options: drivers.data.map((d): [string, string] => [String(d.id), d.name]) }] });
    if (v?.driver) post("/deliveries/", { order, driver: Number(v.driver) }, "Driver assigned.");
  };
  const waiting = orders.data?.results.filter((o) => o.fulfilment === "delivery") ?? [];
  return (
    <div className="space-y-6"><PageHeader title="Deliveries" subtitle="Assign and track deliveries." />
      {perform && <section className="space-y-3"><h2 className="section-title">My deliveries</h2>
        {mine.data?.length === 0 && <p className="empty">Nothing is assigned to you right now.</p>}
        <ul className="grid gap-4 lg:grid-cols-2">{mine.data?.map((d) => <li key={d.id} className="card card-hover p-5 text-sm"><div className="flex items-center justify-between gap-2"><b className="text-base">{d.reference}</b><StatusBadge status={d.status} /></div><p className="mt-2">{d.address}</p><p className="text-muted">{d.customer_name} · {d.customer_phone}</p>{d.collect && <p className="alert alert-warning mt-3">Collect cash on delivery: {money(d.collect)}</p>}
          <div className="mt-4 flex flex-wrap gap-2">{d.status === "assigned" && <button className="btn btn-primary btn-sm" onClick={() => post(`/deliveries/${d.id}/pickup/`, {}, "Marked as picked up.")}>Picked up</button>}{d.status === "picked_up" && <button className="btn btn-primary btn-sm" onClick={async () => { const v = await prompt({ title: "Confirm delivery", confirmLabel: "Mark delivered", fields: [{ name: "note", label: "Delivery note", required: false }] }); if (v) post(`/deliveries/${d.id}/deliver/`, { note: v.note }, "Delivered."); }}>Delivered</button>}
            <button className="btn btn-outline btn-sm btn-link-danger" onClick={async () => { const v = await prompt({ title: "Could not deliver", confirmLabel: "Report", danger: true, fields: [{ name: "reason", label: "Reason the delivery failed", type: "textarea" }] }); if (v?.reason) post(`/deliveries/${d.id}/fail/`, { reason: v.reason }, "Reported."); }}>Could not deliver</button></div></li>)}</ul></section>}
      {manage && <>
        <div className="grid gap-4 sm:grid-cols-3"><StatCard label="Waiting for a driver" value={waiting.length} icon={Truck} tone="warning" /><StatCard label="On the road" value={list.data?.results.filter((d) => ["assigned", "picked_up"].includes(d.status)).length ?? "…"} icon={Truck} tone="info" /><StatCard label="Drivers" value={drivers.data?.length ?? "…"} icon={Truck} /></div>
        {waiting.length > 0 && <section className="space-y-3"><h2 className="section-title">Orders being prepared for delivery</h2><DataTable rows={waiting} rowKey={(o) => o.id} pageSize={8} columns={[{ key: "ref", header: "Order", render: (o) => <b>{o.reference_number}</b> }, { key: "customer", header: "Customer", render: (o) => o.customer_name }, { key: "address", header: "Address", render: (o) => o.delivery_address }, { key: "actions", header: "Actions", align: "right", render: (o) => <button className="btn-link" onClick={() => assign(o.id)}>Assign driver</button> }]} /></section>}
        <section className="space-y-3"><h2 className="section-title">All deliveries</h2><DataTable<Del> rows={list.data?.results} loading={list.isLoading} rowKey={(d) => d.id} search={(d) => `${d.reference} ${d.driver_name} ${d.status}`} empty="No deliveries yet."
          columns={[{ key: "ref", header: "Order", render: (d) => <b>{d.reference}</b> }, { key: "driver", header: "Driver", render: (d) => d.driver_name }, { key: "status", header: "Delivery", render: (d) => <StatusBadge status={d.status} /> }, { key: "order", header: "Order status", render: (d) => <span className="capitalize">{words(d.order_status)}</span> }, { key: "actions", header: "Actions", align: "right", render: (d) => ["failed", "assigned"].includes(d.status) && <button className="btn-link" onClick={async () => { if (await confirm({ title: "Reassign this delivery?", message: d.reference })) assign(d.order); }}>Reassign</button> }]} /></section></>}
    </div>
  );
}
