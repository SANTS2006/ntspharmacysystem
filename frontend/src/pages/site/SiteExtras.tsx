/** Pharmacy website pages: services and bulk/institutional requests. */
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, Clock, Send } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Reveal, Tilt, useSeo } from "../../components/site/motion";
import { EmptyState, FormFields, Loading, Spinner, errorMessage, initialValues, type FieldDef } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { money } from "../../lib/format";
import { useSite } from "./SiteLayout";

interface Svc { id: number; name: string; description: string; price: string | null; requires_booking: boolean; duration_minutes: number; image: string | null }

export function ServicesPage() {
  const { slug = "" } = useParams(); const s = useSite(); const { user } = useAuth();
  useSeo(`Pharmacy services | ${s?.name}`, `Services offered by ${s?.name}. Book appointments online.`, { image: s?.logo });
  const svcs = useQuery({ queryKey: ["pub-services", slug], queryFn: () => api<Svc[]>(`/public/pharmacies/${slug}/services/`) });
  const verified = user?.tenant_slug === slug && user.role === "customer" && user.email_verified;
  const bookTo = verified ? `/${slug}/account/care` : `/${slug}/login?next=${encodeURIComponent(`/${slug}/account/care`)}`;
  return (
    <div className="site-wrap space-y-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-3xl !font-extrabold">Our services</h1><p className="text-muted">Advice and care from our pharmacy team.</p></div><Link to={bookTo} className="btn btn-primary"><CalendarClock size={16} aria-hidden />Book an appointment</Link></div>
      {svcs.isLoading && <Loading rows={3} />}
      {svcs.data?.length === 0 && <EmptyState>No services are listed yet.</EmptyState>}
      <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{svcs.data?.map((v, i) => (
        <Reveal as="li" key={v.id} delay={(i % 3) * 90}><Tilt className="card flex h-full flex-col overflow-hidden" max={5}>
          {v.image && <img src={v.image} alt={v.name} loading="lazy" className="h-40 w-full object-cover" />}
          <div className="flex flex-1 flex-col p-5"><h2 className="section-title !text-lg">{v.name}</h2><p className="mt-2 text-sm text-muted">{v.description}</p>
            <p className="mt-4 flex items-center gap-2 text-sm font-semibold"><Clock size={15} aria-hidden />{v.duration_minutes} min · {v.price ? `from ${money(v.price)}` : "ask us for the price"}</p>
            {v.requires_booking && <Link to={bookTo} className="btn btn-outline btn-sm mt-4 self-start">Book online</Link>}</div>
        </Tilt></Reveal>))}</ul>
    </div>
  );
}

const FIELDS: FieldDef[] = [
  { name: "organisation", label: "Organisation name" }, { name: "contact_person", label: "Contact person" },
  { name: "email", label: "Contact email", type: "email" }, { name: "phone", label: "Contact phone", type: "tel" },
  { name: "service_required", label: "Service or supply required", wide: true }, { name: "products_required", label: "Products required", required: false },
  { name: "quantity", label: "Quantity", required: false }, { name: "location", label: "Location", required: false },
  { name: "requested_date", label: "Date needed", type: "date", required: false }, { name: "details", label: "Other details", type: "textarea", required: false },
];

export function InstitutionalPage() {
  const { slug = "" } = useParams(); const s = useSite();
  useSeo(`Bulk and institutional orders | ${s?.name}`, `Request a quotation or bulk supply from ${s?.name}.`, { image: s?.logo });
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
        <div><h1 className="page-title">Request a quotation or bulk supply</h1><p className="mt-1 text-sm text-muted">For hospitals, companies, schools and event organisers.</p></div>
        {m && <p role={m.ok ? "status" : "alert"} className={`alert ${m.ok ? "alert-success" : "alert-error"}`}>{m.t}</p>}
        <FormFields fields={FIELDS} values={values} set={(n, v) => setValues((x) => ({ ...x, [n]: v }))} />
        <input tabIndex={-1} autoComplete="off" aria-hidden className="hidden" value={website} onChange={(e) => setWebsite(e.target.value)} />
        <button className="btn btn-primary" disabled={busy}>{busy ? <Spinner /> : <Send size={16} aria-hidden />}Send request</button>
      </form>
    </div>
  );
}
