/** Pharmacy website pages: services and bulk/institutional requests. */
import { Send } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { FormFields, Spinner, errorMessage, initialValues, type FieldDef } from "../../components/ui";
import { api } from "../../lib/api";
import { BuilderPage } from "./SitePages";

export const ServicesPage = () => <BuilderPage key="services" pageKey="services" />;

const FIELDS: FieldDef[] = [
  { name: "organisation", label: "Organisation name" }, { name: "contact_person", label: "Contact person" },
  { name: "email", label: "Contact email", type: "email" }, { name: "phone", label: "Contact phone", type: "tel" },
  { name: "service_required", label: "Service or supply required", wide: true }, { name: "products_required", label: "Products required", required: false },
  { name: "quantity", label: "Quantity", required: false }, { name: "location", label: "Location", required: false },
  { name: "requested_date", label: "Date needed", type: "date", required: false }, { name: "details", label: "Other details", type: "textarea", required: false },
];

export const InstitutionalPage = () => <BuilderPage key="institutional" pageKey="institutional"><InstitutionalForm /></BuilderPage>;

function InstitutionalForm() {
  const { slug = "" } = useParams();
  const [values, setValues] = useState(() => initialValues(FIELDS));
  const [website, setWebsite] = useState(""); const [busy, setBusy] = useState(false);
  const [m, setM] = useState<{ ok: boolean; t: string } | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setM(null);
    try { await api(`/public/pharmacies/${slug}/institutional-requests/`, { method: "POST", body: { ...values, website, requested_date: values.requested_date || null } }); setM({ ok: true, t: "Thank you. We received your request and will reply by email." }); setValues(initialValues(FIELDS)); }
    catch (e2) { setM({ ok: false, t: errorMessage(e2) }); } finally { setBusy(false); }
  };
  return (
    <div className="site-wrap py-8">
      <form onSubmit={submit} className="card mx-auto max-w-3xl space-y-4 p-6 sm:p-8">
        <h2 className="page-title">Request a quotation or bulk supply</h2>
        {m && <p role={m.ok ? "status" : "alert"} className={`alert ${m.ok ? "alert-success" : "alert-error"}`}>{m.t}</p>}
        <FormFields fields={FIELDS} values={values} set={(n, v) => setValues((x) => ({ ...x, [n]: v }))} />
        <input tabIndex={-1} autoComplete="off" aria-hidden className="hidden" value={website} onChange={(e) => setWebsite(e.target.value)} />
        <button className="btn btn-primary" disabled={busy}>{busy ? <Spinner /> : <Send size={16} aria-hidden />}Send request</button>
      </form>
    </div>
  );
}
