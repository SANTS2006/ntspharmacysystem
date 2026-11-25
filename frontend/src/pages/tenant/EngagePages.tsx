import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../../lib/api";
import { useAuth } from "../../lib/auth";

interface Page<T> { count: number; results: T[]; average_rating?: number | null }
interface Appt { id: number; service: string; start_at: string; status: string; customer_name: string; customer_phone: string; customer_note: string }
interface Inq { id: number; kind: string; message: string; status: string; response: string; customer: string; phone: string }
interface Fb { id: number; rating: number; comment: string; status: string; response: string; customer: string }
interface Inst { id: number; organisation: string; contact_person: string; email: string; phone: string; service_required: string; products_required: string; quantity: string; status: string; details: string }
interface Svc { id: number; name: string; price: string | null; is_available: boolean; requires_booking: boolean; duration_minutes: number; capacity: number }
interface Del { id: number; order: number; reference: string; status: string; driver_name: string; order_status: string; address?: string; customer_name?: string; customer_phone?: string; collect?: string | null }
const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const brand = { background: "var(--brand)" };
const inputCls = "rounded border p-2";

function useNote() { const [m, setM] = useState<{ ok: boolean; t: string } | null>(null); return { ok: (t: string) => setM({ ok: true, t }), fail: (e: unknown) => setM({ ok: false, t: errText(e) }), view: m && <p role={m.ok ? "status" : "alert"} className={`rounded p-3 text-sm ${m.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>{m.t}</p> }; }

// ============ staff: appointments, enquiries, feedback, institutional requests, services ============
export function EngagementPage() {
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
  const status = (id: number, st: string) => { const note = window.prompt("Enter a note for the customer (optional)") ?? ""; api(`/appointments/${id}/status/`, { method: "POST", body: { status: st, note } }).then(() => done("Updated.")).catch(n.fail); };
  const respond = (path: string, label: string, extra: object = {}) => { const response = window.prompt(label); if (response) api(path, { method: "POST", body: { response, ...extra } }).then(() => done("Sent.")).catch(n.fail); };
  const tabs: [typeof tab, string, boolean][] = [["appointments", "Appointments", true], ["inquiries", "Enquiries", true], ["feedback", "Feedback", true], ["institutional", "Institutional requests", true], ["services", "Services", can("service.manage")]];
  return (
    <div className="space-y-4"><h1 className="text-2xl font-semibold">Customer engagement</h1>{n.view}
      <div role="tablist" className="flex flex-wrap gap-2">{tabs.filter((t) => t[2]).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`rounded px-3 py-1 text-sm ${tab === k ? "text-white" : "border"}`} style={tab === k ? brand : undefined}>{l}</button>)}</div>
      {tab === "appointments" && <div className="space-y-2">{appts.data?.results.length === 0 && <p className="text-slate-500">No appointments.</p>}{appts.data?.results.map((a) => <article key={a.id} className="rounded-xl bg-white p-3 text-sm shadow-sm"><div className="flex flex-wrap justify-between"><strong>{a.service}</strong><span>{new Date(a.start_at).toLocaleString()}</span><span>{a.status.replace("_", " ")}</span></div><p>{a.customer_name} · {a.customer_phone} {a.customer_note && `· “${a.customer_note}”`}</p>
        <div className="space-x-2">{a.status === "requested" && <button className="underline" onClick={() => status(a.id, "confirmed")}>Confirm</button>}{["requested", "confirmed"].includes(a.status) && <button className="underline" onClick={() => status(a.id, "cancelled")}>Cancel</button>}{a.status === "confirmed" && <><button className="underline" onClick={() => status(a.id, "completed")}>Completed</button><button className="underline" onClick={() => status(a.id, "no_show")}>No-show</button></>}</div></article>)}</div>}
      {tab === "inquiries" && <div className="space-y-2">{inqs.data?.results.length === 0 && <p className="text-slate-500">No enquiries.</p>}{inqs.data?.results.map((i) => <article key={i.id} className="rounded-xl bg-white p-3 text-sm shadow-sm"><strong>{i.customer}</strong> · {i.phone} · {i.kind.replace("_", " ")} · {i.status}<p>{i.message}</p>{i.response && <p className="text-green-800">Reply: {i.response}</p>}{i.status !== "answered" && <button className="underline" onClick={() => respond(`/inquiries/${i.id}/respond/`, "Enter your reply")}>Reply</button>}</article>)}</div>}
      {tab === "feedback" && <div className="space-y-2">{fb.data?.average_rating != null && <p className="text-sm">Average rating: <strong>{fb.data.average_rating.toFixed(1)} / 5</strong></p>}{fb.data?.results.map((f) => <article key={f.id} className="rounded-xl bg-white p-3 text-sm shadow-sm"><strong>{"★".repeat(f.rating)}{"☆".repeat(5 - f.rating)}</strong> {f.customer}<p>{f.comment}</p>{f.response && <p className="text-green-800">Reply: {f.response}</p>}{f.status === "new" && <button className="underline" onClick={() => respond(`/feedback/${f.id}/respond/`, "Enter a reply (optional)")}>Reply</button>}</article>)}</div>}
      {tab === "institutional" && <div className="space-y-2">{inst.data?.results.length === 0 && <p className="text-slate-500">No requests.</p>}{inst.data?.results.map((r) => <article key={r.id} className="rounded-xl bg-white p-3 text-sm shadow-sm"><div className="flex justify-between"><strong>{r.organisation}</strong><span>{r.status}</span></div><p>{r.contact_person} · {r.email} · {r.phone}</p><p>{r.service_required}: {r.products_required} {r.quantity && `(${r.quantity})`}</p>{r.details && <p className="text-slate-600">{r.details}</p>}
        {r.status !== "closed" && <div className="space-x-2"><button className="underline" onClick={() => respond(`/institutional-requests/${r.id}/respond/`, "Enter the quotation or response", { status: "quoted" })}>Send quotation</button><button className="underline" onClick={() => api(`/institutional-requests/${r.id}/respond/`, { method: "POST", body: { status: "closed" } }).then(() => done("Closed.")).catch(n.fail)}>Close</button></div>}</article>)}</div>}
      {tab === "services" && <>
        <form onSubmit={(e) => { e.preventDefault(); addSvc.mutate(); }} className="flex flex-wrap items-end gap-2 rounded-xl bg-white p-4 shadow-sm">
          <input required className={inputCls} placeholder="Enter the service name" aria-label="Service name" value={s.name} onChange={(e) => setS({ ...s, name: e.target.value })} /><input className={`${inputCls} w-28`} type="number" min="0" step="0.01" placeholder="Price" aria-label="Price" value={s.price} onChange={(e) => setS({ ...s, price: e.target.value })} />
          <input className={`${inputCls} w-24`} type="number" min="5" aria-label="Duration in minutes" value={s.duration_minutes} onChange={(e) => setS({ ...s, duration_minutes: e.target.value })} /><input className={`${inputCls} w-20`} type="number" min="1" aria-label="Capacity" value={s.capacity} onChange={(e) => setS({ ...s, capacity: e.target.value })} />
          <label className="text-sm"><input type="checkbox" checked={s.requires_booking} onChange={(e) => setS({ ...s, requires_booking: e.target.checked })} /> Needs booking</label><button className="rounded px-4 py-2 text-white" style={brand}>Add service</button></form>
        <ul className="text-sm">{svcs.data?.map((x) => <li key={x.id} className="border-b py-1">{x.name} · {x.price ?? "ask"} · {x.duration_minutes} min · capacity {x.capacity} {x.requires_booking ? "· booking" : ""} {!x.is_available && <em>(unavailable)</em>}</li>)}</ul></>}
    </div>
  );
}

// ============ staff + drivers: deliveries ============
export function DeliveriesPage() {
  const { user } = useAuth(); const qc = useQueryClient(); const n = useNote();
  const can = (p: string) => !!user?.permissions.includes(p);
  const staff = can("delivery.manage");
  const list = useQuery({ queryKey: ["deliveries"], queryFn: () => api<Page<Del>>("/deliveries/"), enabled: staff, refetchInterval: 20000 });
  const drivers = useQuery({ queryKey: ["drivers"], queryFn: () => api<{ id: number; name: string }[]>("/deliveries/drivers/"), enabled: staff });
  const mine = useQuery({ queryKey: ["my-deliveries"], queryFn: () => api<Del[]>("/deliveries/mine/"), enabled: can("delivery.perform"), refetchInterval: 20000 });
  const orders = useQuery({ queryKey: ["staff-orders", "preparing"], queryFn: () => api<Page<{ id: number; reference_number: string; fulfilment: string; delivery_address: string; customer_name: string }>>("/orders/?status=preparing"), enabled: staff });
  const act = (path: string, label: string, body: object = {}) => api(path, { method: "POST", body }).then(() => { n.ok(label); qc.invalidateQueries(); }).catch(n.fail);
  const assign = (order: number) => { const id = window.prompt("Enter the driver number:\n" + (drivers.data ?? []).map((d) => `${d.id} = ${d.name}`).join("\n")); if (id) act("/deliveries/", "Driver assigned.", { order, driver: Number(id) }); };
  return (
    <div className="space-y-4"><h1 className="text-2xl font-semibold">Deliveries</h1>{n.view}
      {can("delivery.perform") && <section className="space-y-2"><h2 className="font-semibold">My deliveries</h2>{mine.data?.length === 0 && <p className="text-slate-500">Nothing assigned to you.</p>}
        {mine.data?.map((d) => <article key={d.id} className="rounded-xl bg-white p-3 text-sm shadow-sm"><strong>{d.reference}</strong> · {d.status.replace("_", " ")}<p>{d.address} · {d.customer_name} · {d.customer_phone}</p>{d.collect && <p className="font-semibold">Collect cash on delivery: {d.collect}</p>}
          <div className="space-x-2">{d.status === "assigned" && <button className="underline" onClick={() => act(`/deliveries/${d.id}/pickup/`, "Picked up.")}>Picked up</button>}{d.status === "picked_up" && <button className="underline" onClick={() => act(`/deliveries/${d.id}/deliver/`, "Delivered.", { note: window.prompt("Enter a delivery note (optional)") ?? "" })}>Delivered</button>}
            <button className="underline" onClick={() => { const reason = window.prompt("Enter why the delivery failed"); if (reason) act(`/deliveries/${d.id}/fail/`, "Reported.", { reason }); }}>Could not deliver</button></div></article>)}</section>}
      {staff && <>
        <section><h2 className="mb-2 font-semibold">Orders being prepared for delivery</h2>{orders.data?.results.filter((o) => o.fulfilment === "delivery").map((o) => <p key={o.id} className="text-sm">{o.reference_number} · {o.customer_name} · {o.delivery_address} <button className="underline" onClick={() => assign(o.id)}>Assign driver</button></p>)}</section>
        <section><h2 className="mb-2 font-semibold">All deliveries</h2><div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Order</th><th>Driver</th><th>Delivery</th><th>Order status</th><th /></tr></thead><tbody>{list.data?.results.map((d) => <tr key={d.id} className="border-t"><td className="p-3">{d.reference}</td><td>{d.driver_name}</td><td>{d.status.replace("_", " ")}</td><td>{d.order_status.replace(/_/g, " ")}</td><td>{["failed", "assigned"].includes(d.status) && <button className="underline" onClick={() => assign(d.order)}>Reassign</button>}</td></tr>)}</tbody></table></div></section></>}
    </div>
  );
}
