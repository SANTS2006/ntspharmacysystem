import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, ImageUp, Plus, Store } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ColorPicker, FormFields, Modal, PageHeader, Spinner, StatusBadge, errorMessage, initialValues, useToast, type FieldDef, type Values } from "../../components/ui";
import { ServerTable } from "../../components/ui/ServerTable";
import { api } from "../../lib/api";
import { day, readableOn } from "../../lib/format";

export interface Pharmacy { id: number; name: string; slug: string; status: string; city: string; country: string; created_at: string; primary_color: string; secondary_color: string; logo?: string | null }

const DETAILS: FieldDef[] = [
  { name: "name", label: "Pharmacy name" }, { name: "slug", label: "Website address name", hint: "3–63 lowercase letters, numbers or hyphens" },
  { name: "registration_number", label: "Registration number", required: false }, { name: "license_number", label: "License number", required: false },
  { name: "country", label: "Country", defaultValue: "Sierra Leone" }, { name: "region", label: "Region", required: false },
  { name: "city", label: "City", required: false }, { name: "address", label: "Pharmacy address", required: false },
  { name: "contact_email", label: "Contact email", type: "email", required: false }, { name: "contact_phone", label: "Contact phone", type: "tel", required: false },
  { name: "description", label: "Pharmacy description", type: "textarea", required: false },
];
const ADMIN: FieldDef[] = [
  { name: "admin_full_name", label: "Administrator full name" }, { name: "admin_email", label: "Administrator email", type: "email" },
  { name: "admin_phone", label: "Administrator phone", type: "tel", required: false },
  { name: "use_invitation", label: "Send a one-time invitation link instead of a temporary password (recommended)", type: "checkbox", defaultValue: true },
];
const STEPS = ["Pharmacy details", "Branding", "Administrator"];
const slugify = (v: string) => v.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 63);

export interface PharmacyAdmin { full_name: string; email: string; phone?: string }
type Editable = Pharmacy & Record<string, unknown>;

/** Three short steps: details, branding (logo and colour pickers) and the administrator. The same form registers and edits. */
export function PharmacyDialog({ onClose, pharmacy, admin, onSaved }: { onClose: () => void; pharmacy?: Editable; admin?: PharmacyAdmin; onSaved?: () => void }) {
  const editing = !!pharmacy;
  const adminFields = !editing ? ADMIN : ADMIN.map((f) => (f.name === "use_invitation" ? { ...f, label: "Email the administrator a new set-password link", defaultValue: false } : f));
  const qc = useQueryClient(); const toast = useToast();
  const [step, setStep] = useState(0);
  const [values, setValues] = useState<Values>(() => {
    const base: Values = { ...initialValues([...DETAILS, ...ADMIN]), primary_color: "#0c54cc", secondary_color: "#0c3c9c" };
    if (!pharmacy) return base;
    [...DETAILS.map((f) => f.name), "primary_color", "secondary_color"].forEach((k) => { base[k] = String(pharmacy[k] ?? ""); });
    return { ...base, admin_full_name: admin?.full_name ?? "", admin_email: admin?.email ?? "", admin_phone: admin?.phone ?? "", use_invitation: "false" };
  });
  const [logo, setLogo] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [slugTouched, setSlugTouched] = useState(editing);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => { if (!logo) { setPreview(null); return; } const url = URL.createObjectURL(logo); setPreview(url); return () => URL.revokeObjectURL(url); }, [logo]);
  const set = (name: string, v: string) => {
    if (name === "slug") setSlugTouched(true);
    setValues((x) => ({ ...x, [name]: v, ...(name === "name" && !slugTouched ? { slug: slugify(v) } : {}) }));
  };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setError("");
    if (step === 0 && !/^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/.test(values.slug)) { setError("The website address name needs 3–63 lowercase letters, numbers or hyphens."); return; }
    if (step === 1 && ![values.primary_color, values.secondary_color].every((c) => /^#[0-9a-f]{6}$/i.test(c))) { setError("Both colours must be six-digit hex colours."); return; }
    if (step < 2) { setStep(step + 1); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      Object.entries(values).forEach(([k, v]) => { if (k === "use_invitation") fd.append(k, v === "true" ? "true" : "false"); else if (editing ? admin || !k.startsWith("admin_") : v !== "") fd.append(k, v); });
      if (editing && !admin) fd.delete("use_invitation");
      if (logo) fd.append("logo", logo);
      await api(pharmacy ? `/platform/pharmacies/${pharmacy.id}/` : "/platform/pharmacies/", { method: pharmacy ? "PATCH" : "POST", body: fd });
      qc.invalidateQueries({ queryKey: ["pharmacies"] }); qc.invalidateQueries({ queryKey: ["platform-dashboard"] });
      toast(editing ? "Pharmacy updated." : `${values.name} was registered. The administrator has been emailed.`); onSaved?.(); onClose();
    } catch (err) { setError(errorMessage(err)); setBusy(false); }
  };
  return (
    <Modal title={pharmacy ? `Edit ${pharmacy.name}` : "Register a pharmacy"} size="lg" onClose={onClose}>
      <ol className="mb-5 flex gap-2" aria-label="Steps">{STEPS.map((s, i) => <li key={s} aria-current={i === step ? "step" : undefined} className="flex-1"><span className="block h-1.5 rounded-full transition-colors" style={{ background: i <= step ? "var(--brand)" : "var(--color-line)" }} /><span className={`mt-1.5 block text-xs ${i === step ? "font-bold" : "text-muted"}`}>{i + 1}. {s}</span></li>)}</ol>
      <form onSubmit={submit} className="space-y-4">
        {error && <p role="alert" className="alert alert-error">{error}</p>}
        {step === 0 && <FormFields fields={DETAILS} values={values} set={set} />}
        {step === 0 && pharmacy && values.slug !== pharmacy.slug && <p className="alert alert-info">Changing the website address name changes every link to this pharmacy's website and sign-in page.</p>}
        {step === 1 && <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-4 rounded-xl border border-line p-4">
            <span className="grid h-20 w-20 place-items-center overflow-hidden rounded-2xl border border-line bg-[#fff]">{preview || pharmacy?.logo ? <img src={preview || pharmacy?.logo || ""} alt="Logo preview" className="h-full w-full object-contain p-2" /> : <Store size={30} aria-hidden style={{ color: "#64748b" }} />}</span>
            <div><input ref={file} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" aria-label="Choose a logo" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} /><button type="button" className="btn btn-outline" onClick={() => file.current?.click()}><ImageUp size={16} aria-hidden />{logo || pharmacy?.logo ? "Change logo" : "Upload logo"}</button><p className="mt-1.5 text-xs text-muted">PNG, JPG or WebP, up to 2 MB.</p></div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2"><ColorPicker label="Primary color" value={values.primary_color} onChange={(v) => set("primary_color", v)} /><ColorPicker label="Secondary color" value={values.secondary_color} onChange={(v) => set("secondary_color", v)} /></div>
          <div className="rounded-2xl p-5 text-center font-extrabold" style={{ background: `linear-gradient(135deg, ${values.primary_color}, ${values.secondary_color})`, color: readableOn(values.primary_color) }}>{values.name || "Your pharmacy"}</div>
        </div>}
        {step === 2 && (editing && !admin ? <p className="empty">This pharmacy has no administrator account to edit.</p> : <FormFields fields={adminFields} values={values} set={set} />)}
        <div className="flex justify-between gap-2 border-t border-line pt-4">
          {step > 0 ? <button type="button" className="btn btn-outline" onClick={() => { setError(""); setStep(step - 1); }}><ArrowLeft size={15} aria-hidden />Back</button> : <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>}
          <button className="btn btn-primary" disabled={busy}>{busy ? <Spinner /> : step === 2 ? <Check size={16} aria-hidden /> : null}{step === 2 ? (editing ? (busy ? "Saving…" : "Save changes") : busy ? "Registering…" : "Register pharmacy") : "Continue"}{step < 2 && <ArrowRight size={15} aria-hidden />}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function Pharmacies() {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const adding = sp.get("new") === "1";
  return (
    <div className="space-y-5">
      <PageHeader title="Pharmacies" subtitle="Register and manage pharmacy tenants." actions={<button className="btn btn-primary" onClick={() => setSp({ new: "1" })}><Plus size={16} aria-hidden />Register pharmacy</button>} />
      <ServerTable<Pharmacy> queryKey={["pharmacies"]} path="/platform/pharmacies/" rowKey={(p) => p.id} search="Enter your pharmacy search" empty="No pharmacies found." onRowClick={(p) => nav(`/platform/pharmacies/${p.id}`)}
        filters={[{ name: "status", label: "All statuses", options: [["active", "Active"], ["suspended", "Suspended"]] }]}
        columns={[
          { key: "name", header: "Pharmacy", render: (p) => <span className="flex items-center gap-3">{p.logo ? <img src={p.logo} alt="" className="h-10 w-10 rounded-xl border border-line bg-[#fff] object-contain p-1" /> : <span className="grid h-10 w-10 place-items-center rounded-xl font-bold" style={{ background: p.primary_color, color: readableOn(p.primary_color) }}>{p.name[0]}</span>}<Link className="font-bold" to={`/platform/pharmacies/${p.id}`}>{p.name}</Link></span> },
          { key: "slug", header: "Website", render: (p) => <a className="text-primary" href={`/${p.slug}`} target="_blank" rel="noopener noreferrer">/{p.slug}</a> },
          { key: "location", header: "Location", render: (p) => [p.city, p.country].filter(Boolean).join(", ") || "—" },
          { key: "created", header: "Registered", render: (p) => day(p.created_at) },
          { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} /> },
          { key: "actions", header: "Actions", align: "right", render: (p) => <Link className="btn-link" to={`/platform/pharmacies/${p.id}`}>Manage</Link> },
        ]} />
      {adding && <PharmacyDialog onClose={() => setSp({})} />}
    </div>
  );
}
