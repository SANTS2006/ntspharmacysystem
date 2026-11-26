import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { EmptyState, PageHeader, StatusBadge, useConfirm, usePrompt } from "../../components/ui";

interface Page<T> { count: number; results: T[]; average_rating?: number | null }
interface Appt { id: number; service: string; start_at: string; status: string; customer_name: string; customer_phone: string; customer_note: string }
interface Inq { id: number; kind: string; message: string; status: string; response: string; customer: string; phone: string }
interface Fb { id: number; rating: number; comment: string; status: string; response: string; customer: string }
interface Inst { id: number; organisation: string; contact_person: string; email: string; phone: string; service_required: string; products_required: string; quantity: string; status: string; details: string }
interface Svc { id: number; name: string; price: string | null; is_available: boolean; requires_booking: boolean; duration_minutes: number; capacity: number }
interface Del { id: number; order: number; reference: string; status: string; driver_name: string; order_status: string; address?: string; customer_name?: string; customer_phone?: string; collect?: string | null }
const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const brand = { background: "var(--brand)" };
const inputCls = "px-3 py-2";

function useNote() { const [m, setM] = useState<{ ok: boolean; t: string } | null>(null); return { ok: (t: string) => setM({ ok: true, t }), fail: (e: unknown) => setM({ ok: false, t: errText(e) }), view: m && <p role={m.ok ? "status" : "alert"} className={`alert ${m.ok ? "alert-success" : "alert-error"}`}>{m.t}</p> }; }

// ============ staff: appointments, enquiries, feedback, institutional requests, services ============
export function EngagementPage() {
  const promptFor = usePrompt(); const confirmDialog = useConfirm();
  const { user } = useAuth(); const qc = useQueryClient(); const n = useNote();
  const can = (p: string) => !!user?.permissions.includes(p);
  const [tab, setTab] = useState<"appointments" | "inquiries" | "feedback" | "institutional" | "services">("appointments");
  const done = (t: string) => { n.ok(t); qc.invalidateQueries(); };
  const appts = useQuery({ queryKey: ["e-appts"], queryFn: () => api<Page<Appt>>("/appointments/"), enabled: tab === "appointments" });
  const inqs = useQuery({ queryKey: ["e-inq"], queryFn: () => api<Page<Inq>>("/inquiries/"), enabled: tab === "inquiries" });
  const fb = useQuery({ queryKey: ["e-fb"], queryFn: () => api<Page<Fb>>("/feedback/"), enabled: tab === "feedback" });
  const inst = useQuery({ queryKey: ["e-inst"], queryFn: () => api<Page<Inst>>("/institutional-requests/"), enabled: tab === "institutional" });
  const svcs = useQuery({ queryKey: ["e-svc"], queryFn: () => api<Svc[]>("/services/"), enabled: tab === "services" && can("service.manage") });
  const [s, setS] = useState({ name: "", price: "", duration_minutes: "30", capacity: "1", requires_booking: true });
  const addSvc = useMutation({ mutationFn: () => api("/services/", { method: "POST", body: { ...s, price: s.price || null, duration_minutes: Number(s.duration_minutes), capacity: Number(s.capacity) } }), onSuccess: () => done("Service added."), onError: n.fail });
  const status = async (id: number, st: string) => { const v = await promptFor({ title: "Update appointment", confirmLabel: "Update", fields: [{ name: "note", label: "Note for the customer (optional)", type: "textarea", required: false }] }); if (v) api(`/appointments/${id}/status/`, { method: "POST", body: { status: st, note: v.note } }).then(() => done("Updated.")).catch(n.fail); };
  const respond = async (path: string, label: string, extra: object = {}) => { const v = await promptFor({ title: "Send a response", confirmLabel: "Send", fields: [{ name: "response", label, type: "textarea" }] }); if (v?.response) api(path, { method: "POST", body: { response: v.response, ...extra } }).then(() => done("Sent.")).catch(n.fail); };
  const tabs: [typeof tab, string, boolean][] = [["appointments", "Appointments", true], ["inquiries", "Enquiries", true], ["feedback", "Feedback", true], ["institutional", "Institutional requests", true], ["services", "Services", can("service.manage")]];
  return (
    <div className="space-y-4"><h1 className="page-title">Customer engagement</h1>{n.view}
      <div role="tablist" className="tablist">{tabs.filter((t) => t[2]).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`tab ${tab === k ? "tab-active" : ""}`}>{l}</button>)}</div>
      {tab === "appointments" && <div className="space-y-2">{appts.data?.results.length === 0 && <EmptyState>No appointments.</EmptyState>}{appts.data?.results.map((a) => <article key={a.id} className="card p-3 text-sm "><div className="flex flex-wrap justify-between"><strong>{a.service}</strong><span>{new Date(a.start_at).toLocaleString()}</span><span>{a.status.replace("_", " ")}</span></div><p>{a.customer_name} · {a.customer_phone} {a.customer_note && `· “${a.customer_note}”`}</p>
        <div className="space-x-2">{a.status === "requested" && <button className="btn-link" onClick={() => status(a.id, "confirmed")}>Confirm</button>}{["requested", "confirmed"].includes(a.status) && <button className="btn-link" onClick={() => status(a.id, "cancelled")}>Cancel</button>}{a.status === "confirmed" && <><button className="btn-link" onClick={() => status(a.id, "completed")}>Completed</button><button className="btn-link" onClick={() => status(a.id, "no_show")}>No-show</button></>}</div></article>)}</div>}
      {tab === "inquiries" && <div className="space-y-2">{inqs.data?.results.length === 0 && <EmptyState>No enquiries.</EmptyState>}{inqs.data?.results.map((i) => <article key={i.id} className="card p-3 text-sm "><strong>{i.customer}</strong> · {i.phone} · {i.kind.replace("_", " ")} · {i.status}<p>{i.message}</p>{i.response && <p className="text-green-800">Reply: {i.response}</p>}{i.status !== "answered" && <button className="btn-link" onClick={() => respond(`/inquiries/${i.id}/respond/`, "Enter your reply")}>Reply</button>}</article>)}</div>}
      {tab === "feedback" && <div className="space-y-2">{fb.data?.average_rating != null && <p className="text-sm">Average rating: <strong>{fb.data.average_rating.toFixed(1)} / 5</strong></p>}{fb.data?.results.map((f) => <article key={f.id} className="card p-3 text-sm "><strong>{"★".repeat(f.rating)}{"☆".repeat(5 - f.rating)}</strong> {f.customer}<p>{f.comment}</p>{f.response && <p className="text-green-800">Reply: {f.response}</p>}{f.status === "new" && <button className="btn-link" onClick={() => respond(`/feedback/${f.id}/respond/`, "Enter a reply (optional)")}>Reply</button>}</article>)}</div>}
      {tab === "institutional" && <div className="space-y-2">{inst.data?.results.length === 0 && <EmptyState>No requests.</EmptyState>}{inst.data?.results.map((r) => <article key={r.id} className="card p-3 text-sm "><div className="flex justify-between"><strong>{r.organisation}</strong><span>{r.status}</span></div><p>{r.contact_person} · {r.email} · {r.phone}</p><p>{r.service_required}: {r.products_required} {r.quantity && `(${r.quantity})`}</p>{r.details && <p className="text-slate-600">{r.details}</p>}
        {r.status !== "closed" && <div className="space-x-2"><button className="btn-link" onClick={() => respond(`/institutional-requests/${r.id}/respond/`, "Enter the quotation or response", { status: "quoted" })}>Send quotation</button><button className="btn-link" onClick={() => api(`/institutional-requests/${r.id}/respond/`, { method: "POST", body: { status: "closed" } }).then(() => done("Closed.")).catch(n.fail)}>Close</button></div>}</article>)}</div>}
      {tab === "services" && <>
        <form onSubmit={(e) => { e.preventDefault(); addSvc.mutate(); }} className="flex flex-wrap items-end gap-2 card p-4">
          <input required className={inputCls} placeholder="Enter the service name" aria-label="Service name" value={s.name} onChange={(e) => setS({ ...s, name: e.target.value })} /><input className={`${inputCls} w-28`} type="number" min="0" step="0.01" placeholder="Price" aria-label="Price" value={s.price} onChange={(e) => setS({ ...s, price: e.target.value })} />
          <input className={`${inputCls} w-24`} type="number" min="5" aria-label="Duration in minutes" value={s.duration_minutes} onChange={(e) => setS({ ...s, duration_minutes: e.target.value })} /><input className={`${inputCls} w-20`} type="number" min="1" aria-label="Capacity" value={s.capacity} onChange={(e) => setS({ ...s, capacity: e.target.value })} />
          <label className="text-sm"><input type="checkbox" checked={s.requires_booking} onChange={(e) => setS({ ...s, requires_booking: e.target.checked })} /> Needs booking</label><button className="btn btn-primary">Add service</button></form>
        <ul className="text-sm">{svcs.data?.map((x) => <li key={x.id} className="border-b py-1">{x.name} · {x.price ?? "ask"} · {x.duration_minutes} min · capacity {x.capacity} {x.requires_booking ? "· booking" : ""} {!x.is_available && <em>(unavailable)</em>}</li>)}</ul></>}
    </div>
  );
}

// ============ staff + drivers: deliveries ============
export function DeliveriesPage() {
  const promptFor = usePrompt(); const confirmDialog = useConfirm();
  const { user } = useAuth(); const qc = useQueryClient(); const n = useNote();
  const can = (p: string) => !!user?.permissions.includes(p);
  const staff = can("delivery.manage");
  const list = useQuery({ queryKey: ["deliveries"], queryFn: () => api<Page<Del>>("/deliveries/"), enabled: staff, refetchInterval: 20000 });
  const drivers = useQuery({ queryKey: ["drivers"], queryFn: () => api<{ id: number; name: string }[]>("/deliveries/drivers/"), enabled: staff });
  const mine = useQuery({ queryKey: ["my-deliveries"], queryFn: () => api<Del[]>("/deliveries/mine/"), enabled: can("delivery.perform"), refetchInterval: 20000 });
  const orders = useQuery({ queryKey: ["staff-orders", "preparing"], queryFn: () => api<Page<{ id: number; reference_number: string; fulfilment: string; delivery_address: string; customer_name: string }>>("/orders/?status=preparing"), enabled: staff });
  const act = (path: string, label: string, body: object = {}) => api(path, { method: "POST", body }).then(() => { n.ok(label); qc.invalidateQueries(); }).catch(n.fail);
  const assign = async (order: number) => { const v = await promptFor({ title: "Assign a driver", confirmLabel: "Assign", fields: [{ name: "driver", label: "Driver", type: "select", options: [["", "Select a driver"], ...(drivers.data ?? []).map((d): [string, string] => [String(d.id), d.name])] }] }); if (v?.driver) act("/deliveries/", "Driver assigned.", { order, driver: Number(v.driver) }); };
  return (
    <div className="space-y-4"><PageHeader title="Deliveries" subtitle="Assign and track deliveries." />{n.view}
      {can("delivery.perform") && <section className="space-y-2"><h2 className="section-title">My deliveries</h2>{mine.data?.length === 0 && <p className="text-slate-500">Nothing assigned to you.</p>}
        {mine.data?.map((d) => <article key={d.id} className="card p-3 text-sm "><strong>{d.reference}</strong> · {d.status.replace("_", " ")}<p>{d.address} · {d.customer_name} · {d.customer_phone}</p>{d.collect && <p className="font-semibold">Collect cash on delivery: {d.collect}</p>}
          <div className="space-x-2">{d.status === "assigned" && <button className="btn-link" onClick={() => act(`/deliveries/${d.id}/pickup/`, "Picked up.")}>Picked up</button>}{d.status === "picked_up" && <button className="btn-link" onClick={async () => { const v = await promptFor({ title: "Confirm delivery", confirmLabel: "Mark delivered", fields: [{ name: "note", label: "Delivery note (optional)", required: false }] }); if (v) act(`/deliveries/${d.id}/deliver/`, "Delivered.", { note: v.note }); }}>Delivered</button>}
            <button className="btn-link" onClick={async () => { const v = await promptFor({ title: "Could not deliver", confirmLabel: "Report", danger: true, fields: [{ name: "reason", label: "Why did the delivery fail?", type: "textarea" }] }); if (v?.reason) act(`/deliveries/${d.id}/fail/`, "Reported.", { reason: v.reason }); }}>Could not deliver</button></div></article>)}</section>}
      {staff && <>
        <section><h2 className="section-title mb-3">Orders being prepared for delivery</h2>{orders.data?.results.filter((o) => o.fulfilment === "delivery").map((o) => <p key={o.id} className="text-sm">{o.reference_number} · {o.customer_name} · {o.delivery_address} <button className="btn-link" onClick={() => assign(o.id)}>Assign driver</button></p>)}</section>
        <section><h2 className="section-title mb-3">All deliveries</h2><div className="table-wrap"><table className="table"><thead><tr><th>Order</th><th>Driver</th><th>Delivery</th><th>Order status</th><th /></tr></thead><tbody>{list.data?.results.map((d) => <tr key={d.id}><td>{d.reference}</td><td>{d.driver_name}</td><td><StatusBadge status={d.status} /></td><td>{d.order_status.replace(/_/g, " ")}</td><td>{["failed", "assigned"].includes(d.status) && <button className="btn-link" onClick={() => assign(d.order)}>Reassign</button>}</td></tr>)}</tbody></table></div></section></>}
    </div>
  );
}
