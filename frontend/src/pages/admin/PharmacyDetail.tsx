import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../../lib/api";
import type { Pharmacy } from "./Pharmacies";

interface Overview {
  branches: { id: number; name: string; code: string; status: string }[];
  administrators: { id: number; email: string; full_name: string; is_active: boolean; must_change_password: boolean }[];
  user_count: number; subscription: { plan: string; status: string; current_period_end: string | null } | null;
}

function BrandingForm({ id, pharmacy }: { id: string; pharmacy: Pharmacy & { contact_email: string } }) {
  const qc = useQueryClient();
  const [v, setV] = useState({ name: pharmacy.name, primary_color: pharmacy.primary_color, secondary_color: (pharmacy as unknown as { secondary_color: string }).secondary_color ?? "#25bcfb", contact_email: pharmacy.contact_email ?? "" });
  const [logo, setLogo] = useState<File | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      Object.entries(v).forEach(([k, val]) => fd.append(k, val));
      if (logo) fd.append("logo", logo);
      return api(`/platform/pharmacies/${id}/`, { method: "PATCH", body: fd });
    },
    onSuccess: () => { setMsg("Saved."); qc.invalidateQueries({ queryKey: ["pharmacy", id] }); },
    onError: (e) => setMsg(e instanceof ApiError ? `${e.message} ${JSON.stringify(e.details ?? "")}` : "Save failed."),
  });
  const f = (k: keyof typeof v, label: string, ph: string) => (
    <label className="text-sm">{label}<input placeholder={ph} className="mt-1 block rounded border p-2" value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} /></label>
  );
  return (
    <form onSubmit={(e) => { e.preventDefault(); setMsg(null); m.mutate(); }} className="flex flex-wrap items-end gap-3 rounded-xl bg-white p-4 shadow-sm">
      <h2 className="w-full font-semibold">Branding</h2>
      {f("name", "Name", "Enter the pharmacy name")}{f("primary_color", "Primary color", "Enter the primary color")}
      {f("secondary_color", "Secondary color", "Enter the secondary color")}{f("contact_email", "Contact email", "Enter the contact email")}
      <label className="text-sm">Logo<input type="file" accept="image/png,image/jpeg,image/webp" className="mt-1 block" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} /></label>
      <button disabled={m.isPending} className="rounded bg-teal-700 px-4 py-2 text-white">Save</button>
      {msg && <p role="status" className="w-full text-sm">{msg}</p>}
    </form>
  );
}

export default function PharmacyDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState<"suspend" | "activate" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const p = useQuery({ queryKey: ["pharmacy", id], queryFn: () => api<Pharmacy & { license_number: string; registration_number: string; contact_email: string }>(`/platform/pharmacies/${id}/`) });
  const o = useQuery({ queryKey: ["pharmacy-overview", id], queryFn: () => api<Overview>(`/platform/pharmacies/${id}/overview/`) });
  const act = useMutation({
    mutationFn: (a: "suspend" | "activate") => api(`/platform/pharmacies/${id}/${a}/`, { method: "POST", body: { reason } }),
    onSuccess: () => { setConfirming(null); setReason(""); qc.invalidateQueries({ queryKey: ["pharmacy", id] }); qc.invalidateQueries({ queryKey: ["pharmacies"] }); },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Action failed."),
  });
  if (p.isLoading) return <p>Loading…</p>;
  if (p.isError || !p.data) return <p role="alert">Pharmacy not found.</p>;
  const ph = p.data;
  return (
    <div className="space-y-4">
      <Link to="/platform/pharmacies" className="text-sm underline">← All pharmacies</Link>
      <div className="flex flex-wrap items-center gap-3">
        <span className="h-6 w-6 rounded" style={{ background: ph.primary_color }} aria-hidden />
        <h1 className="text-2xl font-semibold">{ph.name}</h1>
        <span className="rounded bg-slate-200 px-2 py-0.5 text-xs">{ph.status}</span>
        {ph.status === "active"
          ? <button onClick={() => setConfirming("suspend")} className="ml-auto rounded border border-red-600 px-3 py-1 text-red-700">Suspend</button>
          : <button onClick={() => setConfirming("activate")} className="ml-auto rounded border border-green-700 px-3 py-1 text-green-800">Activate</button>}
      </div>
      {confirming && (
        <div role="dialog" aria-label={`Confirm ${confirming}`} className="space-y-2 rounded-xl border bg-white p-4">
          <p>{confirming === "suspend" ? "Suspending blocks all logins and revokes active sessions for this pharmacy." : "Activating restores access for this pharmacy."}</p>
          <input aria-label="Reason" placeholder="Enter the reason" value={reason} onChange={(e) => setReason(e.target.value)} className="w-full rounded border p-2" />
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          <div className="flex gap-2">
            <button disabled={act.isPending} onClick={() => act.mutate(confirming)} className="rounded bg-slate-900 px-3 py-1 text-white">Confirm {confirming}</button>
            <button onClick={() => setConfirming(null)} className="rounded border px-3 py-1">Cancel</button>
          </div>
        </div>
      )}
      <BrandingForm id={id!} pharmacy={ph} />
      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl bg-white p-4 shadow-sm"><h2 className="mb-2 font-semibold">Details</h2>
          <dl className="grid grid-cols-2 gap-1 text-sm">
            <dt>Website</dt><dd>/{ph.slug}</dd><dt>License</dt><dd>{ph.license_number || "—"}</dd>
            <dt>Registration</dt><dd>{ph.registration_number || "—"}</dd><dt>Contact</dt><dd>{ph.contact_email || "—"}</dd>
            <dt>Users</dt><dd>{o.data?.user_count ?? "…"}</dd>
            <dt>Subscription</dt><dd>{o.data?.subscription ? `${o.data.subscription.plan} (${o.data.subscription.status})` : "None"}</dd>
          </dl></div>
        <div className="rounded-xl bg-white p-4 shadow-sm"><h2 className="mb-2 font-semibold">Administrators</h2>
          <ul className="text-sm">{o.data?.administrators.map((a) => <li key={a.id}>{a.full_name} · {a.email} {a.must_change_password && <em>(pending first login)</em>}</li>)}</ul>
          <h2 className="mb-2 mt-4 font-semibold">Branches</h2>
          <ul className="text-sm">{o.data?.branches.map((b) => <li key={b.id}>{b.name} ({b.code}) · {b.status}</li>)}</ul></div>
      </section>
    </div>
  );
}
