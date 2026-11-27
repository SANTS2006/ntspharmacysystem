/** Administration: branches, staff, roles and the pharmacy's own settings. Buttons appear only for people who may use them. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Check, ImageUp, Pencil, Plus, Power, QrCode, ShieldCheck, Users } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Avatar, ColorPicker, ErrorState, FormModal, Loading, Modal, PageHeader, Spinner, StatusBadge, errorMessage, placeholderFor, useConfirm, useToast, type FieldDef, parsePoint } from "../../components/ui";
import { ServerTable, type ApiPage } from "../../components/ui/ServerTable";
import { api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";

// ---------------- Branches ----------------
export interface Branch { latitude?: string | null; longitude?: string | null; id: number; name: string; code: string; address: string; phone: string; email: string; status: string; manager: number | null }

const branchFields = (b?: Branch): FieldDef[] => [
  { name: "name", label: "Branch name", defaultValue: b?.name, maxLength: 150 }, { name: "code", label: "Branch code", defaultValue: b?.code, maxLength: 20 },
  { name: "address", label: "Branch address", defaultValue: b?.address, required: false, wide: true },
  { name: "phone", label: "Branch phone", type: "tel", defaultValue: b?.phone, required: false }, { name: "email", label: "Branch email", type: "email", defaultValue: b?.email, required: false },
  { name: "location", label: "Map location (shown on your website)", type: "location", defaultValue: b?.latitude && b?.longitude ? `${b.latitude}, ${b.longitude}` : "", required: false },
];

export function Branches() {
  const { can } = useAuth(); const qc = useQueryClient(); const toast = useToast(); const confirm = useConfirm();
  const manage = can("branch.manage");
  const [editing, setEditing] = useState<Branch | "new" | null>(null);
  const done = (text: string) => { qc.invalidateQueries({ queryKey: ["branches"] }); toast(text); };
  const toggle = async (b: Branch) => {
    const off = b.status === "active";
    if (!(await confirm({ title: `${off ? "Deactivate" : "Activate"} ${b.name}?`, message: off ? "No new sales or orders can be made at an inactive branch." : "The branch becomes available again.", confirmLabel: off ? "Deactivate" : "Activate", danger: off }))) return;
    api(`/branches/${b.id}/`, { method: "PATCH", body: { status: off ? "inactive" : "active" } }).then(() => done("Branch updated.")).catch((e) => toast(errorMessage(e), "error"));
  };
  return (
    <div className="space-y-5">
      <PageHeader title="Branches" subtitle="Locations your pharmacy operates from." actions={manage && <button className="btn btn-primary" onClick={() => setEditing("new")}><Plus size={16} aria-hidden />Add branch</button>} />
      <ServerTable<Branch> queryKey={["branches"]} path="/branches/" rowKey={(b) => b.id} search="Enter your branch search" empty="No branches yet."
        filters={[{ name: "status", label: "All statuses", options: [["active", "Active"], ["inactive", "Inactive"]] }]}
        columns={[
          { key: "name", header: "Branch", sort: (b) => b.name, render: (b) => <span className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-teal-50 text-teal-700"><Building2 size={18} aria-hidden /></span><span><b className="block">{b.name}</b><span className="text-xs text-muted">{b.code}</span></span></span> },
          { key: "address", header: "Address", render: (b) => b.address || "—" },
          { key: "contact", header: "Contact", render: (b) => <>{b.phone || "—"}{b.email && <span className="block text-xs text-muted">{b.email}</span>}</> },
          { key: "status", header: "Status", render: (b) => <StatusBadge status={b.status} /> },
          { key: "actions", header: "Actions", align: "right", render: (b) => <span className="inline-flex gap-1.5">
            <button className="btn-link" onClick={() => openProtectedFile(`/branches/${b.id}/qr/`).catch((e) => toast(errorMessage(e), "error"))}><QrCode size={13} aria-hidden />QR menu</button>
            {manage && <><button className="btn-link" onClick={() => setEditing(b)}><Pencil size={13} aria-hidden />Edit</button><button className={`btn-link ${b.status === "active" ? "btn-link-danger" : ""}`} onClick={() => toggle(b)}><Power size={13} aria-hidden />{b.status === "active" ? "Deactivate" : "Activate"}</button></>}
          </span> },
        ]} />
      {editing && <FormModal title={editing === "new" ? "Add branch" : `Edit ${editing.name}`} fields={branchFields(editing === "new" ? undefined : editing)} onClose={() => setEditing(null)} submitLabel={editing === "new" ? "Add branch" : "Save changes"}
        onSubmit={async ({ location: spot, ...v }) => {
          const point = parsePoint(spot ?? "");
          if (spot?.trim() && !point) throw new Error("Enter the map location as latitude, longitude. For example 8.484000, -13.229900.");
          await api(editing === "new" ? "/branches/" : `/branches/${editing.id}/`, { method: editing === "new" ? "POST" : "PATCH", body: { ...v, latitude: point?.[0] ?? null, longitude: point?.[1] ?? null } }); done(editing === "new" ? "Branch added." : "Branch updated."); }} />}
    </div>
  );
}

// ---------------- Staff ----------------
interface Staff { id: number; email: string; full_name: string; phone: string; role: string; role_name: string; branch: number | null; branch_name: string | null; is_active: boolean; must_change_password: boolean }
export interface Role { id: number; code: string; name: string; permissions: string[]; branch_scoped: boolean }

export function useBranchOptions(): [string, string][] {
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["branches", "options"], queryFn: () => api<ApiPage<{ id: number; name: string }>>("/branches/?page_size=200"), enabled: can("branch.view") });
  return useMemo(() => (q.data?.results ?? []).map((b) => [String(b.id), b.name] as [string, string]), [q.data]);
}

export function StaffPage() {
  const { user, can } = useAuth(); const qc = useQueryClient(); const toast = useToast(); const confirm = useConfirm();
  const manage = can("staff.manage");
  const [editing, setEditing] = useState<Staff | "new" | null>(null);
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles/") });
  const branches = useBranchOptions();
  const roleOptions = (roles.data ?? []).filter((r) => r.code !== "customer").map((r) => [r.code, r.name] as [string, string]);
  const done = (text: string) => { qc.invalidateQueries({ queryKey: ["staff"] }); toast(text); };
  const toggle = async (s: Staff) => {
    const verb = s.is_active ? "Deactivate" : "Activate";
    if (!(await confirm({ title: `${verb} ${s.full_name}?`, message: s.is_active ? "They will no longer be able to sign in." : "They will be able to sign in again.", confirmLabel: verb, danger: s.is_active }))) return;
    api(`/staff/${s.id}/`, { method: "PATCH", body: { is_active: !s.is_active } }).then(() => done("Staff member updated.")).catch((e) => toast(errorMessage(e), "error"));
  };
  const fields = (s?: Staff): FieldDef[] => [
    { name: "full_name", label: "Full name", defaultValue: s?.full_name }, { name: "email", label: "Email address", type: "email", defaultValue: s?.email },
    { name: "phone", label: "Phone number", type: "tel", required: false, defaultValue: s?.phone },
    ...(s && s.email === user?.email ? [] : [
      { name: "role", label: "Role", type: "select" as const, options: roleOptions, defaultValue: s?.role },
      { name: "branch", label: "Branch", type: "select" as const, required: false, options: [["", "No branch (whole pharmacy)"] as [string, string], ...branches], defaultValue: s?.branch ?? user?.branch ?? "", hint: "Required for branch-based roles" }]),
    ...(s ? [] : [{ name: "use_invitation", label: "Send an invitation link (recommended)", type: "checkbox" as const, defaultValue: true }]),
  ];
  return (
    <div className="space-y-5">
      <PageHeader title="Staff" subtitle="Invite team members and manage their access." actions={manage && <button className="btn btn-primary" onClick={() => setEditing("new")}><Plus size={16} aria-hidden />Add staff member</button>} />
      <ServerTable<Staff> queryKey={["staff"]} path="/staff/" rowKey={(s) => s.id} search="Enter your name or email search" empty="No staff found."
        filters={[{ name: "role__code", label: "All roles", options: roleOptions }, { name: "is_active", label: "Any status", options: [["true", "Active"], ["false", "Deactivated"]] }]}
        columns={[
          { key: "name", header: "Name", sort: (s) => s.full_name, render: (s) => <span className="flex items-center gap-3"><Avatar name={s.full_name} size={38} /><span><b className="block">{s.full_name}</b><span className="text-xs text-muted">{s.email}</span></span></span> },
          { key: "phone", header: "Phone", render: (s) => s.phone || "—" },
          { key: "role", header: "Role", render: (s) => s.role_name, sort: (s) => s.role_name },
          { key: "branch", header: "Branch", render: (s) => s.branch_name ?? "All branches" },
          { key: "status", header: "Status", render: (s) => <StatusBadge status={s.is_active ? (s.must_change_password ? "invited" : "active") : "deactivated"} /> },
          ...(manage ? [{ key: "actions", header: "Actions", align: "right" as const, render: (s: Staff) => <span className="inline-flex gap-1.5"><button className="btn-link" onClick={() => setEditing(s)}><Pencil size={13} aria-hidden />Edit</button>{s.email !== user?.email && <button className={`btn-link ${s.is_active ? "btn-link-danger" : ""}`} onClick={() => toggle(s)}><Power size={13} aria-hidden />{s.is_active ? "Deactivate" : "Activate"}</button>}</span> }] : []),
        ]} />
      {editing && <FormModal title={editing === "new" ? "Add staff member" : `Edit ${editing.full_name}`} fields={fields(editing === "new" ? undefined : editing)} onClose={() => setEditing(null)} submitLabel={editing === "new" ? "Add staff member" : "Save changes"}
        onSubmit={async (v) => {
          const body: Record<string, unknown> = { ...v };
          if ("branch" in v) body.branch = v.branch ? Number(v.branch) : null;
          if (editing === "new") body.use_invitation = v.use_invitation === "true";
          await api(editing === "new" ? "/staff/" : `/staff/${editing.id}/`, { method: editing === "new" ? "POST" : "PATCH", body });
          done(editing === "new" ? "Staff member added. Their onboarding email is on its way." : "Staff member updated.");
        }} />}
    </div>
  );
}

// ---------------- Roles ----------------
const pretty = (p: string) => p.split(".")[1].replace(/_/g, " ");

export function RolesPage() {
  const { user, can } = useAuth(); const qc = useQueryClient(); const toast = useToast();
  const edit = can("role.manage");
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles/") });
  const [editing, setEditing] = useState<Role | null>(null); const [sel, setSel] = useState<string[]>([]);
  const save = useMutation({ mutationFn: () => api(`/roles/${editing!.id}/`, { method: "PATCH", body: { permissions: sel } }), onSuccess: () => { setEditing(null); qc.invalidateQueries({ queryKey: ["roles"] }); toast("Role updated."); } });
  const groups = useMemo(() => {
    const out: Record<string, string[]> = {};
    [...new Set([...(user?.permissions ?? []), ...(editing?.permissions ?? [])])].sort().forEach((p) => (out[p.split(".")[0]] ??= []).push(p));
    return Object.entries(out);
  }, [user, editing]);
  if (roles.isLoading) return <Loading />;
  return (
    <div className="space-y-5">
      <PageHeader title="Roles & permissions" subtitle="People only see the modules and buttons their role allows." />
      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{roles.data?.filter((r) => r.code !== "customer").map((r) => (
        <article key={r.id} className="card card-hover flex flex-col p-5">
          <div className="flex items-start justify-between gap-3"><span className="flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-xl bg-teal-50 text-teal-700"><ShieldCheck size={20} aria-hidden /></span><span><h2 className="section-title">{r.name}</h2><span className="text-xs text-muted">{r.branch_scoped ? "Limited to one branch" : "Whole pharmacy"}</span></span></span>
            {edit && r.code !== "pharmacy_admin" && <button className="btn-link" onClick={() => { save.reset(); setEditing(r); setSel(r.permissions); }}><Pencil size={13} aria-hidden />Edit</button>}</div>
          <p className="mt-4 text-sm font-semibold"><Users size={14} aria-hidden className="mr-1.5 inline" />{r.permissions.length} permissions</p>
          <ul className="mt-2 flex flex-wrap gap-1.5">{r.permissions.slice(0, 12).map((p) => <li key={p} className="badge badge-neutral">{p.replace(".", ": ").replace(/_/g, " ")}</li>)}{r.permissions.length > 12 && <li className="badge badge-info">+{r.permissions.length - 12} more</li>}{!r.permissions.length && <li className="text-sm text-muted">No permissions</li>}</ul>
        </article>))}</div>
      {editing && (
        <Modal title={`Edit ${editing.name}`} size="lg" onClose={() => setEditing(null)} footer={<><button className="btn btn-outline" onClick={() => setEditing(null)}>Cancel</button><button className="btn btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? <Spinner /> : <Check size={16} aria-hidden />}Save permissions</button></>}>
          <p className="text-sm text-muted">Saving signs out everyone with this role so changes apply immediately. You can only grant permissions you hold.</p>
          {save.isError && <p role="alert" className="alert alert-error mt-3">{errorMessage(save.error)}</p>}
          <div className="mt-4 grid gap-3 sm:grid-cols-2">{groups.map(([group, list]) => (
            <fieldset key={group} className="rounded-xl border border-line p-3"><legend className="px-1 text-sm font-bold capitalize">{group.replace(/_/g, " ")}</legend>
              {list.map((p) => <label key={p} className="flex items-center gap-2.5 py-1 text-sm capitalize"><input type="checkbox" checked={sel.includes(p)} onChange={(e) => setSel(e.target.checked ? [...sel, p] : sel.filter((x) => x !== p))} />{pretty(p)}</label>)}
            </fieldset>))}</div>
        </Modal>)}
    </div>
  );
}

// ---------------- Pharmacy settings ----------------
interface PharmacySettingsData { name: string; slug: string; logo: string | null; description: string; address: string; city: string; region: string; contact_email: string; contact_phone: string; primary_color: string; secondary_color: string }
const TEXT_KEYS = ["description", "address", "city", "region", "contact_email", "contact_phone", "primary_color", "secondary_color"] as const;

export function SettingsPage() {
  const qc = useQueryClient(); const toast = useToast();
  const q = useQuery({ queryKey: ["tenant-settings"], queryFn: () => api<PharmacySettingsData>("/tenants/me/") });
  const [form, setForm] = useState<PharmacySettingsData | null>(null);
  const [logo, setLogo] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => { if (q.data) setForm(q.data); }, [q.data]);
  useEffect(() => { if (!logo) { setPreview(null); return; } const url = URL.createObjectURL(logo); setPreview(url); return () => URL.revokeObjectURL(url); }, [logo]);
  const save = useMutation({
    mutationFn: () => { const fd = new FormData(); TEXT_KEYS.forEach((k) => fd.append(k, form![k] ?? "")); if (logo) fd.append("logo", logo); return api<PharmacySettingsData>("/tenants/me/", { method: "PATCH", body: fd }); },
    onSuccess: (d) => { setLogo(null); qc.setQueryData(["tenant-settings"], d); qc.invalidateQueries({ queryKey: ["site"] }); toast("Pharmacy settings saved."); },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  if (q.isError) return <ErrorState onRetry={() => q.refetch()}>{errorMessage(q.error)}</ErrorState>;
  if (!form) return <Loading />;
  const text = (key: keyof PharmacySettingsData, label: string, type = "text") => <label className="field-label">{label}<input type={type} className="mt-1.5 w-full" placeholder={placeholderFor(label)} value={String(form[key] ?? "")} onChange={(e) => setForm({ ...form, [key]: e.target.value })} /></label>;
  const picture = preview ?? form.logo;
  return (
    <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <PageHeader title="Pharmacy settings" subtitle={`${form.name} · your website, emails and loading screens use these details.`} actions={<button className="btn btn-primary" disabled={save.isPending}>{save.isPending ? <Spinner /> : <Check size={16} aria-hidden />}Save changes</button>} />
      <div className="grid gap-5 xl:grid-cols-[1fr_22rem]">
        <div className="space-y-5">
          <section className="card p-6"><h2 className="section-title">Contact and location</h2><div className="mt-4 grid gap-4 sm:grid-cols-2">
            {text("contact_email", "Contact email", "email")}{text("contact_phone", "Contact phone", "tel")}{text("address", "Pharmacy address")}{text("city", "City")}{text("region", "Region")}
            <label className="field-label sm:col-span-2">Description<textarea rows={4} className="mt-1.5 w-full" placeholder={placeholderFor("Pharmacy description")} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          </div></section>
          <section className="card p-6"><h2 className="section-title">Brand colours</h2><div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ColorPicker label="Primary color" value={form.primary_color} onChange={(v) => setForm({ ...form, primary_color: v })} />
            <ColorPicker label="Secondary color" value={form.secondary_color} onChange={(v) => setForm({ ...form, secondary_color: v })} />
          </div></section>
        </div>
        <aside className="space-y-5">
          <section className="card p-6 text-center"><h2 className="section-title">Logo</h2>
            <div className="mx-auto mt-4 grid h-36 w-36 place-items-center overflow-hidden rounded-3xl border border-line bg-[#fff]">{picture ? <img src={picture} alt="Pharmacy logo" className="h-full w-full object-contain p-3" /> : <span className="text-5xl font-black" style={{ color: "#0b1324" }}>{form.name[0]}</span>}</div>
            <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" aria-label="Choose a logo" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} />
            <button type="button" className="btn btn-outline mt-4" onClick={() => file.current?.click()}><ImageUp size={16} aria-hidden />{picture ? "Change logo" : "Upload logo"}</button>
            <p className="mt-2 text-xs text-muted">PNG, JPG or WebP, up to 2 MB. Save to apply.</p></section>
          <section className="card overflow-hidden"><div className="p-5 text-center" style={{ background: `linear-gradient(135deg, ${form.primary_color}, ${form.secondary_color})` }}><p className="text-lg font-extrabold text-white drop-shadow">{form.name}</p></div><div className="p-4 text-center"><span className="btn btn-sm text-white" style={{ background: form.primary_color }}>Button preview</span></div></section>
        </aside>
      </div>
    </form>
  );
}
