import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../../lib/api";
import { useAuth } from "../../lib/auth";

interface Svc { id: number; name: string; description: string; price: string | null; requires_booking: boolean; duration_minutes: number; branches: number[]; image: string | null }
interface Branch { id: number; name: string }
interface Appt { id: number; service: string; start_at: string; status: string }
const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Something went wrong. Please try again.");
const inputCls = "mt-1 w-full rounded border p-2";
const brand = { background: "var(--brand)" };
const Msg = ({ m }: { m: { ok: boolean; t: string } | null }) => m && <p role={m.ok ? "status" : "alert"} className={`rounded p-3 text-sm ${m.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>{m.t}</p>;

export function ServicesPage() {
  const { slug = "" } = useParams(); const { user } = useAuth(); const qc = useQueryClient();
  const svcs = useQuery({ queryKey: ["pub-services", slug], queryFn: () => api<Svc[]>(`/public/pharmacies/${slug}/services/`) });
  const branches = useQuery({ queryKey: ["branches-public", slug], queryFn: () => api<Branch[]>(`/public/pharmacies/${slug}/branches/`) });
  const mine = useQuery({ queryKey: ["my-appts"], queryFn: () => api<{ results: Appt[] }>("/shop/appointments/", { tenant: slug }), enabled: !!user && user.email_verified && user.role === "customer" });
  const [m, setM] = useState<{ ok: boolean; t: string } | null>(null); const [f, setF] = useState({ service: "", branch: "", start_at: "", note: "" });
  const verified = user?.role === "customer" && user.email_verified;
  const book = async (e: React.FormEvent) => { e.preventDefault(); try { await api("/shop/appointments/", { method: "POST", tenant: slug, body: { ...f, service: Number(f.service), branch: Number(f.branch), start_at: new Date(f.start_at).toISOString() } }); setM({ ok: true, t: "Request sent. We will confirm by email." }); qc.invalidateQueries({ queryKey: ["my-appts"] }); } catch (e2) { setM({ ok: false, t: errText(e2) }); } };
  return (
    <div className="space-y-4"><h1 className="text-2xl font-semibold">Our services</h1>
      <ul className="grid gap-3 sm:grid-cols-2">{svcs.data?.map((s) => <li key={s.id} className="rounded-xl border p-4">{s.image && <img src={s.image} alt="" className="mb-2 h-24 w-full rounded object-cover" />}<h2 className="font-semibold">{s.name}</h2><p className="text-sm text-slate-600">{s.description}</p><p className="text-sm">{s.price ? `From ${s.price}` : "Ask us for the price"} · {s.duration_minutes} min {s.requires_booking && "· booking required"}</p></li>)}</ul>
      {svcs.data?.length === 0 && <p className="text-slate-500">No services are listed yet.</p>}
      <h2 className="text-xl font-semibold">Book an appointment</h2>
      {!verified ? <p>Please <Link className="underline" to={`/pharmacy/${slug}/login`}>sign in</Link> with a verified account to book.</p> : (
        <form onSubmit={book} className="space-y-2 rounded-xl border p-4"><Msg m={m} />
          <label className="block text-sm font-medium">Service<select required className={inputCls} value={f.service} onChange={(e) => setF({ ...f, service: e.target.value })}><option value="">Select a service</option>{svcs.data?.filter((s) => s.requires_booking).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          <label className="block text-sm font-medium">Branch<select required className={inputCls} value={f.branch} onChange={(e) => setF({ ...f, branch: e.target.value })}><option value="">Select a branch</option>{branches.data?.filter((b) => !f.service || !svcs.data?.find((s) => s.id === Number(f.service))?.branches.length || svcs.data?.find((s) => s.id === Number(f.service))?.branches.includes(b.id)).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <label className="block text-sm font-medium">Date and time<input required type="datetime-local" className={inputCls} value={f.start_at} onChange={(e) => setF({ ...f, start_at: e.target.value })} /></label>
          <label className="block text-sm font-medium">Note<input className={inputCls} placeholder="Enter anything we should know" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></label>
          <button className="rounded px-4 py-2 text-white" style={brand}>Request appointment</button></form>)}
      {mine.data && mine.data.results.length > 0 && <section><h2 className="font-semibold">My appointments</h2><ul className="text-sm">{mine.data.results.map((a) => <li key={a.id}>{a.service} · {new Date(a.start_at).toLocaleString()} · {a.status} {["requested", "confirmed"].includes(a.status) && <button className="underline" onClick={() => api(`/shop/appointments/${a.id}/cancel/`, { method: "POST", tenant: slug }).then(() => qc.invalidateQueries({ queryKey: ["my-appts"] })).catch((e) => setM({ ok: false, t: errText(e) }))}>cancel</button>}</li>)}</ul></section>}
    </div>
  );
}

export function InstitutionalPage() {
  const { slug = "" } = useParams();
  const [m, setM] = useState<{ ok: boolean; t: string } | null>(null);
  const [f, setF] = useState({ organisation: "", contact_person: "", email: "", phone: "", service_required: "", products_required: "", quantity: "", location: "", requested_date: "", details: "", website: "" });
  const field = (k: keyof typeof f, label: string, ph: string, type = "text", req = true) => <label className="block text-sm font-medium">{label}{req && <span aria-hidden className="text-red-600"> *</span>}<input type={type} required={req} className={inputCls} placeholder={ph} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>;
  const submit = async (e: React.FormEvent) => { e.preventDefault(); try { await api(`/public/pharmacies/${slug}/institutional-requests/`, { method: "POST", body: { ...f, requested_date: f.requested_date || null } }); setM({ ok: true, t: "Thank you. We received your request and will reply by email." }); } catch (e2) { setM({ ok: false, t: errText(e2) }); } };
  return (
    <form onSubmit={submit} className="mx-auto max-w-xl space-y-3"><h1 className="text-2xl font-semibold">Request a quotation or bulk supply</h1><p className="text-sm text-slate-600">For hospitals, companies, schools and event organisers.</p><Msg m={m} />
      {field("organisation", "Organisation", "Enter the organisation name")}{field("contact_person", "Contact person", "Enter the contact person")}{field("email", "Email", "Enter the contact email", "email")}{field("phone", "Phone", "Enter the contact phone", "tel")}
      {field("service_required", "Service or supply required", "Enter what you need")}{field("products_required", "Products", "Enter the products required", "text", false)}{field("quantity", "Quantity", "Enter the quantity", "text", false)}{field("location", "Location", "Enter the location", "text", false)}{field("requested_date", "Needed by", "", "date", false)}
      <label className="block text-sm font-medium">Details<textarea className={inputCls} placeholder="Enter any other details" value={f.details} onChange={(e) => setF({ ...f, details: e.target.value })} /></label>
      <input tabIndex={-1} autoComplete="off" aria-hidden className="hidden" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} />
      <button className="rounded px-4 py-2 text-white" style={brand}>Send request</button></form>
  );
}

export function FeedbackPage() {
  const { slug = "" } = useParams(); const { user } = useAuth();
  const [m, setM] = useState<{ ok: boolean; t: string } | null>(null); const [f, setF] = useState({ rating: "5", comment: "", kind: "feedback", message: "" });
  const sendFeedback = async (e: React.FormEvent) => { e.preventDefault(); try { await api("/shop/feedback/", { method: "POST", tenant: slug, body: { rating: Number(f.rating), comment: f.comment } }); setM({ ok: true, t: "Thank you for your feedback." }); } catch (e2) { setM({ ok: false, t: errText(e2) }); } };
  const sendInquiry = async (e: React.FormEvent) => { e.preventDefault(); try { await api("/shop/inquiries/", { method: "POST", tenant: slug, body: { kind: f.kind, message: f.message } }); setM({ ok: true, t: "Sent. We will reply by email." }); } catch (e2) { setM({ ok: false, t: errText(e2) }); } };
  if (!(user?.role === "customer" && user.email_verified)) return <p>Please <Link className="underline" to={`/pharmacy/${slug}/login`}>sign in</Link> with a verified account.</p>;
  return (
    <div className="mx-auto max-w-xl space-y-6"><Msg m={m} />
      <form onSubmit={sendFeedback} className="space-y-2 rounded-xl border p-4"><h1 className="text-xl font-semibold">Leave feedback</h1>
        <label className="block text-sm font-medium">Rating<select className={inputCls} value={f.rating} onChange={(e) => setF({ ...f, rating: e.target.value })}>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n} star{n > 1 ? "s" : ""}</option>)}</select></label>
        <label className="block text-sm font-medium">Comment<textarea className={inputCls} placeholder="Tell us about your experience" value={f.comment} onChange={(e) => setF({ ...f, comment: e.target.value })} /></label><button className="rounded px-4 py-2 text-white" style={brand}>Send feedback</button></form>
      <form onSubmit={sendInquiry} className="space-y-2 rounded-xl border p-4"><h2 className="text-xl font-semibold">Ask the pharmacy</h2>
        <label className="block text-sm font-medium">Type<select className={inputCls} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="feedback" hidden>Choose</option><option value="inquiry">General question</option><option value="availability">Is a medicine available?</option><option value="home_delivery">Home delivery request</option></select></label>
        <label className="block text-sm font-medium">Message<textarea required className={inputCls} placeholder="Enter your message" value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} /></label><button className="rounded px-4 py-2 text-white" style={brand}>Send</button></form>
    </div>
  );
}
