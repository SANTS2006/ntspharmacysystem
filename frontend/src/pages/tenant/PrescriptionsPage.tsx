import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";

interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
interface Rx { id: number; reference_number: string; status: string; patient_name: string; prescriber_name: string; prescription_date: string; expiry_date: string; has_document: boolean }
interface Alert { id: number; type: string; severity: string; message: string; source: string; decision: string; decision_note: string; decided_by: string | null }
interface RxDetail extends Rx {
  patient_allergies: string[]; refills_allowed: number; refills_used: number;
  items: { id: number; medicine_name: string; classification: string; dosage: string; frequency: string; quantity_prescribed: number; quantity_dispensed: number }[];
  safety_alerts: Alert[]; interventions: { id: number; type: string; note: string; pharmacist: string | null }[];
  dispensings: { id: number; at: string; by: string | null; items: { medicine: string; batch: string; quantity: number }[] }[];
  availability: { item: number; medicine: string; needed: number; available: number; sufficient: boolean }[];
}
const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const inputCls = "mt-1 w-full rounded border p-2 font-normal";
const brand = { background: "var(--brand)" };
const sev: Record<string, string> = { critical: "bg-red-100 text-red-800", warning: "bg-amber-100 text-amber-800", info: "bg-slate-100 text-slate-700" };

function Detail({ id, onClose }: { id: number; onClose: () => void }) {
  const { user } = useAuth(); const qc = useQueryClient();
  const can = (p: string) => !!user?.permissions.includes(p);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const q = useQuery({ queryKey: ["rx", id], queryFn: () => api<RxDetail>(`/prescriptions/${id}/`) });
  const act = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: object }) => api<RxDetail>(path, { method: "POST", body: body ?? {} }),
    onSuccess: (d) => { qc.setQueryData(["rx", id], d); qc.invalidateQueries({ queryKey: ["rxs"] }); setMsg({ ok: true, t: "Saved." }); }, onError: (e) => setMsg({ ok: false, t: errText(e) }),
  });
  const upload = useMutation({ mutationFn: (f: File) => { const fd = new FormData(); fd.append("document", f); return api(`/prescriptions/${id}/document/`, { method: "POST", body: fd }); }, onSuccess: () => { qc.invalidateQueries({ queryKey: ["rx", id] }); setMsg({ ok: true, t: "Document attached." }); }, onError: (e) => setMsg({ ok: false, t: errText(e) }) });
  if (q.isLoading || !q.data) return <p>Loading…</p>;
  const r = q.data; const base = `/prescriptions/${id}`;
  const ask = (label: string) => window.prompt(label) ?? "";
  const approve = () => { if (window.confirm("Confirm that you verified the prescriber and patient, and reviewed the dosage?")) act.mutate({ path: `${base}/approve/`, body: { verification: { prescriber_verified: true, patient_verified: true, dosage_reviewed: true } } }); };
  const dispense = () => {
    const lines = r.items.map((i) => ({ item: i.id, remaining: i.quantity_prescribed - i.quantity_dispensed, name: i.medicine_name })).filter((i) => i.remaining > 0)
      .map((i) => ({ item: i.item, quantity: Number(window.prompt(`Enter the quantity to dispense for ${i.name} (remaining ${i.remaining}, 0 to skip)`, String(i.remaining)) || 0) })).filter((l) => l.quantity > 0);
    if (lines.length) act.mutate({ path: `/dispensing/prescriptions/${id}/`, body: { lines } });
  };
  return (
    <section aria-label="Prescription detail" className="space-y-3 rounded-xl border bg-white p-4 shadow">
      <div className="flex justify-between"><h2 className="text-lg font-semibold">{r.reference_number} · {r.status.replace("_", " ")}</h2><button onClick={onClose} className="underline">Close</button></div>
      <p className="text-sm">Patient: <strong>{r.patient_name}</strong>{r.patient_allergies.length > 0 && <span className="ml-2 rounded bg-red-100 px-2 text-red-800">Allergies: {r.patient_allergies.join(", ")}</span>} · Prescriber: {r.prescriber_name} · Valid until {r.expiry_date} · Refills {r.refills_used}/{r.refills_allowed}</p>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`rounded p-2 text-sm ${msg.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>{msg.t}</p>}
      <table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-2">Medicine</th><th>Dose</th><th>Prescribed</th><th>Dispensed</th><th>In stock</th></tr></thead>
        <tbody>{r.items.map((i) => { const a = r.availability.find((x) => x.item === i.id); return <tr key={i.id} className="border-t"><td className="p-2">{i.medicine_name} {i.classification !== "otc" && <span className="text-xs text-red-700">({i.classification})</span>}</td><td>{i.dosage}, {i.frequency}</td><td>{i.quantity_prescribed}</td><td>{i.quantity_dispensed}</td><td className={a && !a.sufficient ? "text-red-700" : ""}>{a?.available}</td></tr>; })}</tbody></table>
      <div><h3 className="font-semibold">Safety alerts <span className="text-xs font-normal text-slate-500">(system-generated; decisions are the pharmacist's)</span></h3>
        {r.safety_alerts.length === 0 && <p className="text-sm text-slate-500">None. This is not a clinical clearance.</p>}
        <ul className="space-y-1">{r.safety_alerts.map((a) => <li key={a.id} className="rounded border p-2 text-sm"><span className={`mr-2 rounded px-2 text-xs ${sev[a.severity]}`}>{a.severity}</span>{a.message}
          {a.decision ? <p className="mt-1 text-xs text-green-800">Pharmacist decision ({a.decided_by}): {a.decision_note}</p> : can("prescription.verify") && <button className="ml-2 underline" onClick={() => { const note = ask("Enter your decision about this alert"); if (note) act.mutate({ path: `${base}/alerts/${a.id}/acknowledge/`, body: { note } }); }}>Record decision</button>}</li>)}</ul></div>
      {r.interventions.length > 0 && <div><h3 className="font-semibold">Clinical interventions</h3><ul className="text-sm">{r.interventions.map((i) => <li key={i.id}>{i.type}: {i.note} ({i.pharmacist})</li>)}</ul></div>}
      {r.dispensings.length > 0 && <div><h3 className="font-semibold">Dispensing history</h3><ul className="text-sm">{r.dispensings.map((d) => <li key={d.id}>{new Date(d.at).toLocaleString()} by {d.by}: {d.items.map((i) => `${i.medicine} ${i.quantity} (batch ${i.batch})`).join(", ")}</li>)}</ul></div>}
      <div className="flex flex-wrap items-center gap-2">
        {r.has_document && <button className="rounded border px-3 py-1" onClick={() => openProtectedFile(`${base}/document/`).catch((e) => setMsg({ ok: false, t: errText(e) }))}>Open document</button>}
        {can("prescription.register") && ["received", "under_review", "approved", "partially_dispensed"].includes(r.status) && <label className="text-sm">Attach document <input type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} /></label>}
        {can("prescription.verify") && r.status === "received" && <button className="rounded px-3 py-1 text-white" style={brand} onClick={() => act.mutate({ path: `${base}/start-review/` })}>Start pharmacist review</button>}
        {can("prescription.verify") && r.status === "under_review" && <><button className="rounded px-3 py-1 text-white" style={brand} onClick={approve}>Approve</button><button className="rounded border px-3 py-1" onClick={() => act.mutate({ path: `${base}/recheck-safety/` })}>Re-run safety checks</button></>}
        {can("prescription.verify") && ["received", "under_review"].includes(r.status) && <button className="rounded border px-3 py-1" onClick={() => { const reason = ask("Enter the rejection reason"); if (reason) act.mutate({ path: `${base}/reject/`, body: { reason } }); }}>Reject</button>}
        {can("prescription.verify") && ["received", "under_review", "approved", "partially_dispensed"].includes(r.status) && <button className="rounded border px-3 py-1" onClick={() => { const reason = ask("Enter the cancellation reason"); if (reason) act.mutate({ path: `${base}/cancel/`, body: { reason } }); }}>Cancel</button>}
        {can("prescription.verify") && r.status !== "rejected" && <button className="rounded border px-3 py-1" onClick={() => { const type = ask("Enter the intervention type"); const note = type && ask("Enter the intervention note"); if (type && note) act.mutate({ path: `${base}/interventions/`, body: { type, note } }); }}>Record intervention</button>}
        {can("prescription.dispense") && ["approved", "partially_dispensed"].includes(r.status) && <button className="rounded px-3 py-1 text-white" style={brand} onClick={dispense}>Dispense</button>}
        {can("prescription.dispense") && r.status === "dispensed" && r.refills_used < r.refills_allowed && <button className="rounded border px-3 py-1" onClick={() => act.mutate({ path: `${base}/refill/` })}>Authorize refill</button>}
      </div>
    </section>
  );
}

export default function PrescriptionsPage() {
  const { user } = useAuth(); const qc = useQueryClient();
  const can = (p: string) => !!user?.permissions.includes(p);
  const [status, setStatus] = useState(""); const [q, setQ] = useState(""); const [page, setPage] = useState(1); const [open, setOpen] = useState<number | null>(null); const [err, setErr] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["rxs", status, q, page], queryFn: () => api<Page<Rx>>(`/prescriptions/?page=${page}&search=${encodeURIComponent(q)}${status ? `&status=${status}` : ""}`) });
  const meds = useQuery({ queryKey: ["medicines-all"], queryFn: () => api<Page<{ id: number; name: string; strength: string }>>("/medicines/?status=active&ordering=name"), enabled: can("prescription.register") });
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => api<Page<{ id: number; name: string }>>("/branches/"), enabled: can("branch.view") });
  const [f, setF] = useState({ patient_name: "", phone: "", dob: "", allergies: "", branch: user?.branch ? String(user.branch) : "", prescriber_name: "", prescriber_registration: "", prescription_date: "", medicine: "", dosage: "", frequency: "", quantity: "", refills: "0" });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const create = useMutation({
    mutationFn: async () => {
      const p = await api<{ id: number }>("/patients/", { method: "POST", body: { full_name: f.patient_name, phone: f.phone, date_of_birth: f.dob || null, allergies: f.allergies.split(",").map((s) => s.trim()).filter(Boolean) } });
      return api<{ id: number }>("/prescriptions/", { method: "POST", body: { patient: p.id, branch: Number(f.branch), prescriber_name: f.prescriber_name, prescriber_registration: f.prescriber_registration, prescription_date: f.prescription_date, refills_allowed: Number(f.refills), items: [{ medicine: Number(f.medicine), dosage: f.dosage, frequency: f.frequency, quantity_prescribed: Number(f.quantity) }] } });
    },
    onSuccess: (d) => { setErr(null); qc.invalidateQueries({ queryKey: ["rxs"] }); setOpen(d.id); }, onError: (e) => setErr(errText(e)),
  });
  const inp = (k: keyof typeof f, label: string, ph: string, type = "text", req = true) => <label className="text-sm font-medium">{label}<input type={type} required={req} className={inputCls} placeholder={ph} value={f[k]} onChange={set(k)} /></label>;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Prescriptions</h1>
      {can("prescription.register") && (
        <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="grid gap-3 rounded-xl bg-white p-4 shadow-sm md:grid-cols-4">
          <h2 className="font-semibold md:col-span-4">Register a prescription</h2>
          {inp("patient_name", "Patient name", "Enter the patient's full name")}{inp("phone", "Patient phone", "Enter the patient's phone", "tel", false)}{inp("dob", "Date of birth", "", "date", false)}{inp("allergies", "Allergies (comma separated)", "Enter known allergies", "text", false)}
          {inp("prescriber_name", "Prescriber", "Enter the prescriber's name")}{inp("prescriber_registration", "Prescriber registration", "Enter the registration number", "text", false)}{inp("prescription_date", "Prescription date", "", "date")}
          <label className="text-sm font-medium">Branch<select required className={inputCls} value={f.branch} onChange={set("branch")}><option value="">Select a branch</option>{branches.data?.results.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <label className="text-sm font-medium">Medicine<select required className={inputCls} value={f.medicine} onChange={set("medicine")}><option value="">Select a medicine</option>{meds.data?.results.map((m) => <option key={m.id} value={m.id}>{m.name} {m.strength}</option>)}</select></label>
          {inp("dosage", "Dosage", "Enter the dosage")}{inp("frequency", "Frequency", "Enter the frequency")}{inp("quantity", "Quantity", "Enter the quantity", "number")}{inp("refills", "Refills allowed", "Enter refills allowed", "number", false)}
          <button disabled={create.isPending} className="self-end rounded px-4 py-2 text-white" style={brand}>Register</button>
          {err && <p role="alert" className="rounded bg-red-50 p-2 text-sm text-red-700 md:col-span-4">{err}</p>}
        </form>)}
      {open && <Detail id={open} onClose={() => setOpen(null)} />}
      <div className="flex gap-2"><input aria-label="Search prescriptions" placeholder="Enter a reference or patient name" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} className="w-72 rounded border p-2" />
        <select aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="rounded border p-2"><option value="">All statuses</option>{["received", "under_review", "approved", "partially_dispensed", "dispensed", "rejected", "cancelled"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</select></div>
      {list.isLoading && <p>Loading…</p>}{list.data?.results.length === 0 && <p className="text-slate-500">No prescriptions.</p>}
      {list.data && list.data.results.length > 0 && <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Reference</th><th>Patient</th><th>Prescriber</th><th>Date</th><th>Status</th><th /></tr></thead>
        <tbody>{list.data.results.map((r) => <tr key={r.id} className="border-t"><td className="p-3">{r.reference_number}</td><td>{r.patient_name}</td><td>{r.prescriber_name}</td><td>{r.prescription_date}</td><td>{r.status.replace("_", " ")}</td><td><button className="underline" onClick={() => setOpen(r.id)}>Open</button></td></tr>)}</tbody></table></div>}
      <div className="flex gap-2"><button disabled={!list.data?.previous} onClick={() => setPage(page - 1)} className="rounded border px-3 py-1 disabled:opacity-40">Previous</button><button disabled={!list.data?.next} onClick={() => setPage(page + 1)} className="rounded border px-3 py-1 disabled:opacity-40">Next</button></div>
    </div>
  );
}
