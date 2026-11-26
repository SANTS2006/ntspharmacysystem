/** Prescription register, patient records and the prescription detail page. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Check, FileText, Paperclip, Pencil, Pill, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { EmptyState, FormModal, Loading, PageHeader, StatusBadge, Tabs, errorMessage, useConfirm, usePrompt, useToast, type FieldDef } from "../../components/ui";
import { ServerTable, type ApiPage } from "../../components/ui/ServerTable";
import { api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, day, words } from "../../lib/format";
import { useBranchOptions } from "./TenantPages";

interface Rx { id: number; reference_number: string; status: string; patient_name: string; prescriber_name: string; prescription_date: string; expiry_date: string; has_document: boolean }
interface Alert { id: number; type: string; severity: string; message: string; source: string; decision: string; decision_note: string; decided_by: string | null }
interface RxDetail extends Rx {
  patient_allergies: string[]; refills_allowed: number; refills_used: number;
  items: { id: number; medicine_name: string; classification: string; dosage: string; frequency: string; quantity_prescribed: number; quantity_dispensed: number }[];
  safety_alerts: Alert[]; interventions: { id: number; type: string; note: string; pharmacist: string | null }[];
  dispensings: { id: number; at: string; by: string | null; items: { medicine: string; batch: string; quantity: number }[] }[];
  availability: { item: number; medicine: string; needed: number; available: number; sufficient: boolean }[];
}
interface Patient { id: number; full_name: string; phone: string; date_of_birth: string | null; gender: string; allergies: string[] }
const SEVERITY: Record<string, string> = { critical: "badge-danger", warning: "badge-warning", info: "badge-neutral" };
const STATUSES = ["received", "under_review", "approved", "partially_dispensed", "dispensed", "rejected", "cancelled"];

export function PrescriptionDetail() {
  const { rxId = "", slug = "" } = useParams();
  const prompt = usePrompt(); const confirm = useConfirm(); const toast = useToast(); const { can } = useAuth(); const qc = useQueryClient();
  const [attaching, setAttaching] = useState(false);
  const q = useQuery({ queryKey: ["rx", rxId], queryFn: () => api<RxDetail>(`/prescriptions/${rxId}/`), retry: false });
  const act = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: object; done?: string }) => api<RxDetail>(path, { method: "POST", body: body ?? {} }),
    onSuccess: (d, v) => { if (d?.items) qc.setQueryData(["rx", rxId], d); else qc.invalidateQueries({ queryKey: ["rx", rxId] }); qc.invalidateQueries({ queryKey: ["rxs"] }); toast(v.done ?? "Saved."); }, onError: (e) => toast(errorMessage(e), "error"),
  });
  const back = <Link to={`/${slug}/admin/prescriptions`} className="btn btn-outline btn-sm"><ArrowLeft size={15} aria-hidden />All prescriptions</Link>;
  if (q.isLoading) return <Loading rows={5} label="Opening prescription…" />;
  if (!q.data) return <div className="space-y-4">{back}<EmptyState>{errorMessage(q.error)}</EmptyState></div>;
  const r = q.data; const base = `/prescriptions/${rxId}`;
  const verify = can("prescription.verify"), dispenseAllowed = can("prescription.dispense");
  const ask = async (label: string, title: string, danger = false) => (await prompt({ title, danger, fields: [{ name: "text", label, type: "textarea" }] }))?.text ?? "";
  const approve = async () => { if (await confirm({ title: "Approve this prescription?", message: "Confirm that you verified the prescriber and patient, and reviewed the dosage.", confirmLabel: "I verified, approve" })) act.mutate({ path: `${base}/approve/`, body: { verification: { prescriber_verified: true, patient_verified: true, dosage_reviewed: true } }, done: "Prescription approved." }); };
  const dispense = async () => {
    const open = r.items.map((i) => ({ item: i.id, remaining: i.quantity_prescribed - i.quantity_dispensed, name: i.medicine_name })).filter((i) => i.remaining > 0);
    const v = await prompt({ title: "Dispense medicines", message: "Enter the quantity to dispense for each item (0 to skip).", confirmLabel: "Dispense",
      fields: open.map((i) => ({ name: String(i.item), label: `${i.name} (remaining ${i.remaining})`, type: "number" as const, min: 0, max: i.remaining, step: "1", defaultValue: i.remaining, wide: true })) });
    if (!v) return;
    const lines = open.map((i) => ({ item: i.item, quantity: Number(v[String(i.item)] || 0) })).filter((l) => l.quantity > 0);
    if (lines.length) act.mutate({ path: `/dispensing/prescriptions/${rxId}/`, body: { lines }, done: "Medicines dispensed." });
  };
  return (
    <div className="space-y-5">
      {back}
      <PageHeader title={r.reference_number} subtitle={`${r.patient_name} · prescribed by ${r.prescriber_name} on ${day(r.prescription_date)}`} actions={<StatusBadge status={r.status} />} />
      {r.patient_allergies.length > 0 && <p className="alert alert-error"><AlertTriangle size={17} aria-hidden /><span><b>Allergies:</b> {r.patient_allergies.join(", ")}</span></p>}
      <div className="grid items-start gap-5 xl:grid-cols-[1.7fr_1fr]">
        <div className="space-y-5">
          <div className="table-wrap"><table className="table"><thead><tr><th>Medicine</th><th>Dosage</th><th className="text-center">Prescribed</th><th className="text-center">Dispensed</th><th className="text-center">In stock</th></tr></thead>
            <tbody>{r.items.map((i) => { const a = r.availability.find((x) => x.item === i.id); return <tr key={i.id}><td><span className="flex items-center gap-2"><Pill size={15} aria-hidden className="text-primary" /><b>{i.medicine_name}</b>{i.classification !== "otc" && <span className="badge badge-danger">{i.classification}</span>}</span></td><td>{i.dosage}, {i.frequency}</td><td className="text-center">{i.quantity_prescribed}</td><td className="text-center">{i.quantity_dispensed}</td><td className="text-center">{a ? <span className={`badge ${a.sufficient ? "badge-success" : "badge-danger"}`}>{a.available}</span> : "—"}</td></tr>; })}</tbody></table></div>
          <section className="card p-5"><h2 className="section-title">Safety alerts</h2><p className="text-xs text-muted">System-generated; decisions are the pharmacist's.</p>
            {r.safety_alerts.length === 0 && <p className="mt-3 text-sm text-muted">None. This is not a clinical clearance.</p>}
            <ul className="mt-3 space-y-2">{r.safety_alerts.map((a) => <li key={a.id} className="rounded-xl border border-line p-3 text-sm"><div className="flex flex-wrap items-start gap-2"><span className={`badge ${SEVERITY[a.severity] ?? "badge-neutral"}`}>{a.severity}</span><span className="min-w-0 flex-1">{a.message}</span>{!a.decision && verify && <button className="btn-link" onClick={async () => { const note = await ask("Your decision about this alert", "Record pharmacist decision"); if (note) act.mutate({ path: `${base}/alerts/${a.id}/acknowledge/`, body: { note } }); }}>Record decision</button>}</div>{a.decision && <p className="mt-2 flex gap-1.5 text-xs text-success"><Check size={14} aria-hidden />Pharmacist decision ({a.decided_by}): {a.decision_note}</p>}</li>)}</ul></section>
          {r.interventions.length > 0 && <section className="card p-5"><h2 className="section-title">Clinical interventions</h2><ul className="mt-3 space-y-2 text-sm">{r.interventions.map((i) => <li key={i.id} className="rounded-xl border border-line p-3"><b>{i.type}</b>: {i.note} <span className="text-muted">({i.pharmacist})</span></li>)}</ul></section>}
          {r.dispensings.length > 0 && <section className="card p-5"><h2 className="section-title">Dispensing history</h2><ol className="mt-3 space-y-3 border-l-2 border-line pl-4 text-sm">{r.dispensings.map((d) => <li key={d.id}><b>{dateTime(d.at)}</b> <span className="text-muted">by {d.by}</span><p>{d.items.map((i) => `${i.medicine} × ${i.quantity} (batch ${i.batch})`).join(", ")}</p></li>)}</ol></section>}
        </div>
        <aside className="space-y-4">
          <section className="card p-5 text-sm"><h2 className="section-title">Details</h2><dl className="mt-3 space-y-2">{([["Patient", r.patient_name], ["Prescriber", r.prescriber_name], ["Prescription date", day(r.prescription_date)], ["Valid until", day(r.expiry_date)], ["Refills used", `${r.refills_used} of ${r.refills_allowed}`]] as const).map(([k, v]) => <div key={k} className="flex justify-between gap-3 border-b border-line pb-2"><dt className="text-muted">{k}</dt><dd className="text-right font-semibold">{v}</dd></div>)}</dl>
            <div className="mt-4 flex flex-wrap gap-2">
              {r.has_document && <button className="btn btn-outline btn-sm" onClick={() => openProtectedFile(`${base}/document/`).catch((e) => toast(errorMessage(e), "error"))}><FileText size={14} aria-hidden />Open document</button>}
              {can("prescription.register") && ["received", "under_review", "approved", "partially_dispensed"].includes(r.status) && <button className="btn btn-outline btn-sm" onClick={() => setAttaching(true)}><Paperclip size={14} aria-hidden />{r.has_document ? "Replace document" : "Attach document"}</button>}
            </div></section>
          {(verify || dispenseAllowed) && <section className="card flex flex-col gap-2 p-5"><h2 className="section-title">Actions</h2>
            {verify && r.status === "received" && <button className="btn btn-primary" onClick={() => act.mutate({ path: `${base}/start-review/` })}>Start pharmacist review</button>}
            {verify && r.status === "under_review" && <><button className="btn btn-primary" onClick={approve}>Approve</button><button className="btn btn-outline" onClick={() => act.mutate({ path: `${base}/recheck-safety/` })}>Re-run safety checks</button></>}
            {dispenseAllowed && ["approved", "partially_dispensed"].includes(r.status) && <button className="btn btn-primary" onClick={dispense}>Dispense</button>}
            {dispenseAllowed && r.status === "dispensed" && r.refills_used < r.refills_allowed && <button className="btn btn-outline" onClick={async () => { if (await confirm({ title: "Authorize a refill?" })) act.mutate({ path: `${base}/refill/` }); }}>Authorize refill</button>}
            {verify && r.status !== "rejected" && <button className="btn btn-outline" onClick={async () => { const v = await prompt({ title: "Record intervention", fields: [{ name: "type", label: "Intervention type" }, { name: "note", label: "Intervention note", type: "textarea" }] }); if (v?.type && v.note) act.mutate({ path: `${base}/interventions/`, body: { type: v.type, note: v.note } }); }}>Record intervention</button>}
            {verify && ["received", "under_review"].includes(r.status) && <button className="btn btn-outline btn-link-danger" onClick={async () => { const reason = await ask("Rejection reason", "Reject prescription", true); if (reason) act.mutate({ path: `${base}/reject/`, body: { reason }, done: "Prescription rejected." }); }}>Reject</button>}
            {verify && ["received", "under_review", "approved", "partially_dispensed"].includes(r.status) && <button className="btn btn-outline btn-link-danger" onClick={async () => { const reason = await ask("Cancellation reason", "Cancel prescription", true); if (reason) act.mutate({ path: `${base}/cancel/`, body: { reason }, done: "Prescription cancelled." }); }}>Cancel prescription</button>}
          </section>}
        </aside>
      </div>
      {attaching && <FormModal title="Attach the prescription document" submitLabel="Upload" onClose={() => setAttaching(false)} fields={[{ name: "document", label: "Prescription file", type: "file", required: true, accept: "application/pdf,image/png,image/jpeg,image/webp", hint: "PDF or photo, up to 5 MB" }]}
        onSubmit={async (_v, files) => { const fd = new FormData(); fd.append("document", files.document!); await api(`${base}/document/`, { method: "POST", body: fd }); qc.invalidateQueries({ queryKey: ["rx", rxId] }); toast("Document attached."); }} />}
    </div>
  );
}

const patientFields = (p?: Patient): FieldDef[] => [
  { name: "full_name", label: "Patient name", defaultValue: p?.full_name }, { name: "phone", label: "Patient phone", type: "tel", required: false, defaultValue: p?.phone },
  { name: "date_of_birth", label: "Date of birth", type: "date", required: false, defaultValue: p?.date_of_birth },
  { name: "gender", label: "Gender", type: "select", required: false, defaultValue: p?.gender, options: [["", "Not stated"], ["female", "Female"], ["male", "Male"], ["other", "Other"]] },
  { name: "allergies", label: "Allergies", required: false, wide: true, defaultValue: p?.allergies?.join(", "), hint: "Separate with commas" },
];
const patientBody = (v: Record<string, string>) => ({ full_name: v.full_name, phone: v.phone, gender: v.gender, date_of_birth: v.date_of_birth || null, allergies: v.allergies.split(",").map((s) => s.trim()).filter(Boolean) });

export default function PrescriptionsPage() {
  const { slug = "" } = useParams(); const nav = useNavigate(); const { user, can } = useAuth(); const qc = useQueryClient(); const toast = useToast();
  const register = can("prescription.register");
  const [tab, setTab] = useState<"prescriptions" | "patients">("prescriptions");
  const [adding, setAdding] = useState(false); const [patient, setPatient] = useState<Patient | "new" | null>(null);
  const branches = useBranchOptions();
  const meds = useQuery({ queryKey: ["medicines", "options"], queryFn: () => api<ApiPage<{ id: number; name: string; strength: string }>>("/medicines/?status=active&ordering=name&page_size=200"), enabled: adding && can("medicine.view") });
  const patients = useQuery({ queryKey: ["patients", "options"], queryFn: () => api<ApiPage<Patient>>("/patients/?page_size=200"), enabled: adding });
  const patientOptions = useMemo(() => [["", "New patient (enter below)"] as [string, string], ...(patients.data?.results ?? []).map((p) => [String(p.id), `${p.full_name}${p.phone ? ` · ${p.phone}` : ""}`] as [string, string])], [patients.data]);
  const open = (r: Rx) => nav(`/${slug}/admin/prescriptions/${r.id}`);
  return (
    <div className="space-y-5">
      <PageHeader title="Prescriptions" subtitle="Review, approve and dispense prescriptions safely."
        actions={register && (tab === "prescriptions" ? <button className="btn btn-primary" onClick={() => setAdding(true)}><Plus size={16} aria-hidden />Register prescription</button> : <button className="btn btn-primary" onClick={() => setPatient("new")}><Plus size={16} aria-hidden />Add patient</button>)} />
      <Tabs tabs={[["prescriptions", "Prescriptions"], ["patients", "Patients"]]} value={tab} onChange={setTab} />
      {tab === "prescriptions" && <ServerTable<Rx> queryKey={["rxs"]} path="/prescriptions/" rowKey={(r) => r.id} search="Enter your reference or patient search" empty="No prescriptions." onRowClick={open}
        filters={[{ name: "status", label: "All statuses", options: STATUSES.map((s) => [s, words(s)]) }]}
        columns={[{ key: "ref", header: "Reference", render: (r) => <b>{r.reference_number}</b> }, { key: "patient", header: "Patient", render: (r) => r.patient_name }, { key: "prescriber", header: "Prescriber", render: (r) => r.prescriber_name }, { key: "date", header: "Date", render: (r) => day(r.prescription_date) }, { key: "expiry", header: "Valid until", render: (r) => day(r.expiry_date) }, { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> }, { key: "actions", header: "Actions", align: "right", render: (r) => <button className="btn-link" onClick={() => open(r)}>Open</button> }]} />}
      {tab === "patients" && <ServerTable<Patient> queryKey={["patients"]} path="/patients/" rowKey={(p) => p.id} search="Enter your patient search" empty="No patients yet."
        columns={[{ key: "name", header: "Patient", render: (p) => <b>{p.full_name}</b> }, { key: "phone", header: "Phone", render: (p) => p.phone || "—" }, { key: "dob", header: "Date of birth", render: (p) => day(p.date_of_birth) }, { key: "allergies", header: "Allergies", render: (p) => p.allergies?.length ? <span className="badge badge-danger">{p.allergies.join(", ")}</span> : "None recorded" },
          ...(register ? [{ key: "actions", header: "Actions", align: "right" as const, render: (p: Patient) => <button className="btn-link" onClick={() => setPatient(p)}><Pencil size={13} aria-hidden />Edit</button> }] : [])]} />}
      {patient && <FormModal title={patient === "new" ? "Add patient" : `Edit ${patient.full_name}`} fields={patientFields(patient === "new" ? undefined : patient)} onClose={() => setPatient(null)}
        onSubmit={async (v) => { await api(patient === "new" ? "/patients/" : `/patients/${patient.id}/`, { method: patient === "new" ? "POST" : "PATCH", body: patientBody(v) }); qc.invalidateQueries({ queryKey: ["patients"] }); toast("Patient saved."); }} />}
      {adding && <FormModal title="Register a prescription" size="lg" submitLabel="Register" onClose={() => setAdding(false)}
        fields={[
          { name: "patient", label: "Existing patient", type: "select", required: false, wide: true, options: patientOptions },
          { name: "patient_name", label: "New patient name", required: false }, { name: "phone", label: "New patient phone", type: "tel", required: false },
          { name: "dob", label: "Date of birth", type: "date", required: false }, { name: "allergies", label: "Allergies", required: false, hint: "Separate with commas" },
          { name: "prescriber_name", label: "Prescriber name" }, { name: "prescriber_registration", label: "Prescriber registration number", required: false },
          { name: "prescription_date", label: "Prescription date", type: "date" }, { name: "branch", label: "Branch", type: "select", options: branches, defaultValue: user?.branch ?? "" },
          { name: "medicine", label: "Medicine", type: "select", options: (meds.data?.results ?? []).map((m) => [String(m.id), `${m.name} ${m.strength}`]) },
          { name: "dosage", label: "Dosage" }, { name: "frequency", label: "Frequency" }, { name: "quantity", label: "Quantity", type: "number", min: 1, step: "1" }, { name: "refills", label: "Refills allowed", type: "number", min: 0, step: "1", required: false, defaultValue: 0 },
        ]}
        onSubmit={async (v) => {
          let id = Number(v.patient);
          if (!id) {
            if (!v.patient_name.trim()) throw new Error("Choose a patient or enter the new patient's name.");
            id = (await api<{ id: number }>("/patients/", { method: "POST", body: patientBody({ full_name: v.patient_name, phone: v.phone, gender: "", date_of_birth: v.dob, allergies: v.allergies }) })).id;
          }
          const created = await api<{ id: number }>("/prescriptions/", { method: "POST", body: { patient: id, branch: Number(v.branch), prescriber_name: v.prescriber_name, prescriber_registration: v.prescriber_registration, prescription_date: v.prescription_date, refills_allowed: Number(v.refills || 0), items: [{ medicine: Number(v.medicine), dosage: v.dosage, frequency: v.frequency, quantity_prescribed: Number(v.quantity) }] } });
          qc.invalidateQueries({ queryKey: ["rxs"] }); toast("Prescription registered."); nav(`/${slug}/admin/prescriptions/${created.id}`);
        }} />}
    </div>
  );
}
