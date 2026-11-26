import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Building2, ExternalLink, Pencil, Power, Users, Wallet } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DataTable, EmptyState, FormModal, Loading, StatCard, StatusBadge, errorMessage, usePrompt, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { day, readableOn } from "../../lib/format";
import type { Pharmacy } from "./Pharmacies";

interface Overview {
  branches: { id: number; name: string; code: string; status: string }[];
  administrators: { id: number; email: string; full_name: string; is_active: boolean; must_change_password: boolean }[];
  user_count: number; subscription: { plan: string; status: string; current_period_end: string | null } | null;
}
type Full = Pharmacy & { license_number: string; registration_number: string; contact_email: string; contact_phone: string; address: string; description: string };

export default function PharmacyDetail() {
  const { id } = useParams(); const qc = useQueryClient(); const prompt = usePrompt(); const toast = useToast();
  const [editing, setEditing] = useState(false);
  const p = useQuery({ queryKey: ["pharmacy", id], queryFn: () => api<Full>(`/platform/pharmacies/${id}/`), retry: false });
  const o = useQuery({ queryKey: ["pharmacy-overview", id], queryFn: () => api<Overview>(`/platform/pharmacies/${id}/overview/`) });
  const back = <Link to="/platform/pharmacies" className="btn btn-outline btn-sm"><ArrowLeft size={15} aria-hidden />All pharmacies</Link>;
  if (p.isLoading) return <Loading rows={5} />;
  if (!p.data) return <div className="space-y-4">{back}<EmptyState>Pharmacy not found.</EmptyState></div>;
  const ph = p.data;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["pharmacy", id] }); qc.invalidateQueries({ queryKey: ["pharmacies"] }); };
  const act = async (what: "suspend" | "activate") => {
    const v = await prompt({ title: `${what === "suspend" ? "Suspend" : "Activate"} ${ph.name}?`, message: what === "suspend" ? "Suspending blocks all sign-ins and revokes active sessions for this pharmacy." : "Activating restores access for this pharmacy.", confirmLabel: what === "suspend" ? "Suspend" : "Activate", danger: what === "suspend", fields: [{ name: "reason", label: "Reason", type: "textarea", required: what === "suspend" }] });
    if (v) api(`/platform/pharmacies/${id}/${what}/`, { method: "POST", body: v }).then(() => { refresh(); toast("Pharmacy updated."); }).catch((e) => toast(errorMessage(e), "error"));
  };
  return (
    <div className="space-y-5">
      {back}
      <section className="card animate-rise overflow-hidden">
        <div className="h-24" style={{ background: `linear-gradient(135deg, ${ph.primary_color}, ${ph.secondary_color})` }} />
        <div className="flex flex-wrap items-end gap-4 px-5 pb-5">
          {ph.logo ? <img src={ph.logo} alt="" className="-mt-10 h-24 w-24 rounded-2xl border-4 border-[var(--color-surface)] bg-[#fff] object-contain p-2" /> : <span className="-mt-10 grid h-24 w-24 place-items-center rounded-2xl border-4 border-[var(--color-surface)] text-4xl font-black" style={{ background: ph.primary_color, color: readableOn(ph.primary_color) }}>{ph.name[0]}</span>}
          <div className="min-w-0 flex-1 pt-3"><h1 className="page-title flex flex-wrap items-center gap-2">{ph.name}<StatusBadge status={ph.status} /></h1><a href={`/${ph.slug}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">/{ph.slug}<ExternalLink size={13} aria-hidden /></a></div>
          <div className="flex flex-wrap gap-2"><button className="btn btn-outline" onClick={() => setEditing(true)}><Pencil size={15} aria-hidden />Edit</button>
            <button className={`btn ${ph.status === "active" ? "btn-outline btn-link-danger" : "btn-primary"}`} onClick={() => act(ph.status === "active" ? "suspend" : "activate")}><Power size={15} aria-hidden />{ph.status === "active" ? "Suspend" : "Activate"}</button></div>
        </div>
      </section>
      <div className="grid gap-4 sm:grid-cols-3"><StatCard label="Users" value={o.data?.user_count ?? "…"} icon={Users} /><StatCard label="Branches" value={o.data?.branches.length ?? "…"} icon={Building2} tone="navy" /><StatCard label="Subscription" value={o.data?.subscription?.plan ?? "None"} icon={Wallet} tone="info" hint={o.data?.subscription ? `${o.data.subscription.status}${o.data.subscription.current_period_end ? ` until ${day(o.data.subscription.current_period_end)}` : ""}` : undefined} /></div>
      <div className="grid items-start gap-5 xl:grid-cols-[1fr_2fr]">
        <section className="card p-5 text-sm"><h2 className="section-title">Details</h2><dl className="mt-3 space-y-2.5">{([["Licence", ph.license_number], ["Registration", ph.registration_number], ["Contact email", ph.contact_email], ["Contact phone", ph.contact_phone], ["Address", [ph.address, ph.city, ph.country].filter(Boolean).join(", ")]] as const).map(([k, v]) => <div key={k} className="flex justify-between gap-3 border-b border-line pb-2"><dt className="text-muted">{k}</dt><dd className="break-all text-right font-semibold">{v || "—"}</dd></div>)}</dl></section>
        <div className="space-y-5">
          <section className="space-y-2"><h2 className="section-title">Administrators</h2><DataTable rows={o.data?.administrators} loading={o.isLoading} rowKey={(a) => a.id} pageSize={5} columns={[{ key: "name", header: "Name", render: (a) => <b>{a.full_name}</b> }, { key: "email", header: "Email", render: (a) => a.email }, { key: "status", header: "Status", render: (a) => <StatusBadge status={!a.is_active ? "deactivated" : a.must_change_password ? "invited" : "active"} /> }]} /></section>
          <section className="space-y-2"><h2 className="section-title">Branches</h2><DataTable rows={o.data?.branches} loading={o.isLoading} rowKey={(b) => b.id} pageSize={5} columns={[{ key: "name", header: "Branch", render: (b) => <b>{b.name}</b> }, { key: "code", header: "Code", render: (b) => b.code }, { key: "status", header: "Status", render: (b) => <StatusBadge status={b.status} /> }]} /></section>
        </div>
      </div>
      {editing && <FormModal title={`Edit ${ph.name}`} size="lg" onClose={() => setEditing(false)}
        fields={[{ name: "name", label: "Pharmacy name", defaultValue: ph.name }, { name: "contact_email", label: "Contact email", type: "email", required: false, defaultValue: ph.contact_email }, { name: "logo", label: "Logo", type: "file", accept: "image/png,image/jpeg,image/webp", wide: true }, { name: "primary_color", label: "Primary color", type: "color", defaultValue: ph.primary_color }, { name: "secondary_color", label: "Secondary color", type: "color", defaultValue: ph.secondary_color }]}
        onSubmit={async (v, files) => { const fd = new FormData(); (["name", "contact_email", "primary_color", "secondary_color"] as const).forEach((k) => fd.append(k, v[k])); if (files.logo) fd.append("logo", files.logo); await api(`/platform/pharmacies/${id}/`, { method: "PATCH", body: fd }); refresh(); toast("Pharmacy updated."); }} />}
    </div>
  );
}
