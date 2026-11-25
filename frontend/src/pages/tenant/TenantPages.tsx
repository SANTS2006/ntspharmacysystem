import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ApiError, api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";

interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const inputCls = "mt-1 w-full rounded border p-2 font-normal";
const Err = ({ m }: { m?: string }) => (m ? <span role="alert" className="block text-xs text-red-600">{m}</span> : null);
const Pager = ({ page, setPage, d }: { page: number; setPage: (n: number) => void; d?: { next: string | null; previous: string | null } }) => (
  <div className="flex items-center gap-2"><button disabled={!d?.previous} onClick={() => setPage(page - 1)} className="rounded border px-3 py-1 disabled:opacity-40">Previous</button>
    <span className="text-sm">Page {page}</span><button disabled={!d?.next} onClick={() => setPage(page + 1)} className="rounded border px-3 py-1 disabled:opacity-40">Next</button></div>
);

// ---------------- Dashboard ----------------
export function TenantDashboard() {
  const { user } = useAuth();
  const { data, isLoading, isError } = useQuery({ queryKey: ["tenant-dashboard"], queryFn: () => api<{ scope: string; branches: number; employees: number; pharmacists: number; customers: number | null; staff_by_role: { role__name: string; n: number }[] }>("/tenants/dashboard/") });
  if (isLoading) return <p>Loading…</p>;
  if (isError || !data) return <p role="alert">The dashboard could not be loaded.</p>;
  const cards: [string, number | null][] = [["Branches", data.branches], ["Employees", data.employees], ["Pharmacists", data.pharmacists], ["Customers", data.customers]];
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Welcome, {user?.full_name}</h1>
      <p className="text-sm text-slate-600">Showing {data.scope === "branch" ? "your branch" : "all branches"}.</p>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards.filter(([, v]) => v !== null).map(([k, v]) => <div key={k} className="rounded-xl bg-white p-4 shadow-sm"><p className="text-xs uppercase text-slate-500">{k}</p><p className="text-2xl font-semibold">{v}</p></div>)}
      </div>
      <section className="rounded-xl bg-white p-4 shadow-sm"><h2 className="mb-2 font-semibold">Staff by role</h2>
        <ul className="text-sm">{data.staff_by_role.map((r) => <li key={r.role__name}>{r.role__name}: {r.n}</li>)}</ul></section>
      <p className="text-sm text-slate-500">Inventory, sales and prescription metrics appear here as those modules are released.</p>
    </div>
  );
}

// ---------------- Branches ----------------
interface Branch { id: number; name: string; code: string; address: string; phone: string; status: string; manager: number | null }
const branchSchema = z.object({ name: z.string().min(2, "Enter the branch name."), code: z.string().min(2, "Enter the branch code.").max(20), address: z.string().optional(), phone: z.string().optional() });

export function Branches() {
  const { user } = useAuth(); const qc = useQueryClient();
  const canManage = user?.permissions.includes("branch.manage");
  const [err, setErr] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["branches"], queryFn: () => api<Page<Branch>>("/branches/") });
  const { register, handleSubmit, reset, formState: { errors } } = useForm<z.infer<typeof branchSchema>>({ resolver: zodResolver(branchSchema) });
  const create = useMutation({ mutationFn: (v: object) => api("/branches/", { method: "POST", body: v }), onSuccess: () => { reset(); setErr(null); qc.invalidateQueries({ queryKey: ["branches"] }); }, onError: (e) => setErr(errText(e)) });
  const toggle = useMutation({ mutationFn: (b: Branch) => api(`/branches/${b.id}/`, { method: "PATCH", body: { status: b.status === "active" ? "inactive" : "active" } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["branches"] }), onError: (e) => setErr(errText(e)) });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Branches</h1>
      {canManage && (
        <form noValidate onSubmit={handleSubmit((v) => create.mutate(v))} className="grid gap-3 rounded-xl bg-white p-4 shadow-sm md:grid-cols-4">
          <label className="text-sm font-medium">Name <span aria-hidden className="text-red-600">*</span><input className={inputCls} placeholder="Enter the branch name" {...register("name")} /><Err m={errors.name?.message} /></label>
          <label className="text-sm font-medium">Code <span aria-hidden className="text-red-600">*</span><input className={inputCls} placeholder="Enter the branch code" {...register("code")} /><Err m={errors.code?.message} /></label>
          <label className="text-sm font-medium">Address<input className={inputCls} placeholder="Enter the branch address" {...register("address")} /></label>
          <label className="text-sm font-medium">Phone<input className={inputCls} placeholder="Enter the branch phone" {...register("phone")} /></label>
          <button disabled={create.isPending} className="rounded px-4 py-2 text-white md:col-span-4 md:w-40" style={{ background: "var(--brand)" }}>Add branch</button>
        </form>)}
      {err && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">{err}</p>}
      {q.isLoading && <p>Loading…</p>}{q.data?.results.length === 0 && <p className="text-slate-500">No branches.</p>}
      {q.data && q.data.results.length > 0 && <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Name</th><th>Code</th><th>Address</th><th>Status</th><th /></tr></thead>
        <tbody>{q.data.results.map((b) => <tr key={b.id} className="border-t"><td className="p-3">{b.name}</td><td>{b.code}</td><td>{b.address}</td><td>{b.status}</td>
          <td><button className="mr-2 underline" onClick={() => openProtectedFile(`/branches/${b.id}/qr/`).catch((e) => setErr(errText(e)))}>QR code</button>{canManage && <button onClick={() => toggle.mutate(b)} className="underline">{b.status === "active" ? "Deactivate" : "Activate"}</button>}</td></tr>)}</tbody></table></div>}
    </div>
  );
}

// ---------------- Staff ----------------
interface Staff { id: number; email: string; full_name: string; role: string; role_name: string; branch: number | null; branch_name: string | null; is_active: boolean; must_change_password: boolean }
interface Role { id: number; code: string; name: string; permissions: string[]; branch_scoped: boolean }
const staffSchema = z.object({ full_name: z.string().min(2, "Enter the full name."), email: z.string().email("Enter a valid email address."), phone: z.string().optional(), role: z.string().min(1, "Select a role."), branch: z.string().optional(), use_invitation: z.boolean() });

export function StaffPage() {
  const { user } = useAuth(); const qc = useQueryClient();
  const canManage = user?.permissions.includes("staff.manage");
  const [q, setQ] = useState(""); const [page, setPage] = useState(1); const [err, setErr] = useState<string | null>(null); const [ok, setOk] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["staff", q, page], queryFn: () => api<Page<Staff>>(`/staff/?page=${page}&search=${encodeURIComponent(q)}`) });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles/") });
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => api<Page<Branch>>("/branches/"), enabled: !!user?.permissions.includes("branch.view") });
  const { register, handleSubmit, reset, formState: { errors } } = useForm<z.infer<typeof staffSchema>>({ resolver: zodResolver(staffSchema), defaultValues: { use_invitation: true } });
  const create = useMutation({
    mutationFn: (v: z.infer<typeof staffSchema>) => api("/staff/", { method: "POST", body: { ...v, branch: v.branch ? Number(v.branch) : null } }),
    onSuccess: () => { reset(); setErr(null); setOk("Staff member added. Onboarding email queued."); qc.invalidateQueries({ queryKey: ["staff"] }); }, onError: (e) => { setOk(null); setErr(errText(e)); },
  });
  const toggle = useMutation({ mutationFn: (s: Staff) => api(`/staff/${s.id}/`, { method: "PATCH", body: { is_active: !s.is_active } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["staff"] }), onError: (e) => setErr(errText(e)) });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Staff</h1>
      {canManage && (
        <form noValidate onSubmit={handleSubmit((v) => create.mutate(v))} className="grid gap-3 rounded-xl bg-white p-4 shadow-sm md:grid-cols-3">
          <label className="text-sm font-medium">Full name <span aria-hidden className="text-red-600">*</span><input className={inputCls} placeholder="Enter the full name" {...register("full_name")} /><Err m={errors.full_name?.message} /></label>
          <label className="text-sm font-medium">Email <span aria-hidden className="text-red-600">*</span><input className={inputCls} placeholder="Enter the email address" {...register("email")} /><Err m={errors.email?.message} /></label>
          <label className="text-sm font-medium">Phone<input className={inputCls} placeholder="Enter the phone number" {...register("phone")} /></label>
          <label className="text-sm font-medium">Role <span aria-hidden className="text-red-600">*</span><select className={inputCls} {...register("role")}><option value="">Select a role</option>{roles.data?.filter((r) => r.code !== "customer").map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}</select><Err m={errors.role?.message} /></label>
          <label className="text-sm font-medium">Branch<select className={inputCls} {...register("branch")}><option value="">Select a branch</option>{branches.data?.results.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <label className="flex items-center gap-2 self-end text-sm"><input type="checkbox" {...register("use_invitation")} /> Send invitation link (recommended)</label>
          <button disabled={create.isPending} className="rounded px-4 py-2 text-white md:w-40" style={{ background: "var(--brand)" }}>{create.isPending ? "Adding…" : "Add staff"}</button>
        </form>)}
      {ok && <p role="status" className="rounded bg-green-50 p-3 text-sm text-green-800">{ok}</p>}
      {err && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">{err}</p>}
      <input aria-label="Search staff" placeholder="Enter a name or email" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} className="w-64 rounded border p-2" />
      {list.isLoading && <p>Loading…</p>}{list.data?.results.length === 0 && <p className="text-slate-500">No staff found.</p>}
      {list.data && list.data.results.length > 0 && <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Name</th><th>Email</th><th>Role</th><th>Branch</th><th>Status</th><th /></tr></thead>
        <tbody>{list.data.results.map((s) => <tr key={s.id} className="border-t"><td className="p-3">{s.full_name}</td><td>{s.email}</td><td>{s.role_name}</td><td>{s.branch_name ?? "—"}</td><td>{s.is_active ? (s.must_change_password ? "Invited" : "Active") : "Deactivated"}</td>
          <td>{canManage && s.email !== user?.email && <button onClick={() => window.confirm(`${s.is_active ? "Deactivate" : "Activate"} ${s.full_name}?`) && toggle.mutate(s)} className="underline">{s.is_active ? "Deactivate" : "Activate"}</button>}</td></tr>)}</tbody></table></div>}
      <Pager page={page} setPage={setPage} d={list.data} />
    </div>
  );
}

// ---------------- Roles ----------------
export function RolesPage() {
  const { user } = useAuth(); const qc = useQueryClient();
  const canEdit = user?.permissions.includes("role.manage");
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles/") });
  const [editing, setEditing] = useState<Role | null>(null); const [sel, setSel] = useState<string[]>([]); const [err, setErr] = useState<string | null>(null);
  const save = useMutation({ mutationFn: () => api(`/roles/${editing!.id}/`, { method: "PATCH", body: { permissions: sel } }), onSuccess: () => { setEditing(null); setErr(null); qc.invalidateQueries({ queryKey: ["roles"] }); }, onError: (e) => setErr(errText(e)) });
  const all = user?.permissions ?? [];
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Roles & permissions</h1>
      {roles.isLoading && <p>Loading…</p>}
      <div className="grid gap-3 md:grid-cols-2">{roles.data?.map((r) => (
        <article key={r.id} className="rounded-xl bg-white p-4 shadow-sm"><div className="flex justify-between"><h2 className="font-semibold">{r.name}</h2>
          {canEdit && r.code !== "pharmacy_admin" && <button className="text-sm underline" onClick={() => { setEditing(r); setSel(r.permissions); }}>Edit</button>}</div>
          <p className="mt-1 text-xs text-slate-600">{r.permissions.length ? r.permissions.join(", ") : "No permissions"}</p></article>))}</div>
      {editing && (
        <div role="dialog" aria-label={`Edit ${editing.name}`} className="space-y-3 rounded-xl border bg-white p-4">
          <h2 className="font-semibold">Edit {editing.name}</h2>
          <p className="text-sm text-slate-600">Saving signs out everyone with this role so changes apply immediately. You can only grant permissions you hold.</p>
          <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">{all.map((p) => <label key={p} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={sel.includes(p)} onChange={(e) => setSel(e.target.checked ? [...sel, p] : sel.filter((x) => x !== p))} />{p}</label>)}</div>
          {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
          <div className="flex gap-2"><button onClick={() => save.mutate()} disabled={save.isPending} className="rounded px-3 py-1 text-white" style={{ background: "var(--brand)" }}>Save</button><button onClick={() => setEditing(null)} className="rounded border px-3 py-1">Cancel</button></div>
        </div>)}
    </div>
  );
}

// ---------------- Settings ----------------
const settingsSchema = z.object({ description: z.string().optional(), address: z.string().optional(), city: z.string().optional(), region: z.string().optional(), contact_email: z.union([z.literal(""), z.string().email("Enter a valid email address.")]), contact_phone: z.string().optional(), primary_color: z.string().regex(/^#[0-9A-Fa-f]{6}$/, "Enter a color like #015dc9."), secondary_color: z.string().regex(/^#[0-9A-Fa-f]{6}$/, "Enter a color like #25bcfb.") });
export function SettingsPage() {
  const qc = useQueryClient(); const [msg, setMsg] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["tenant-settings"], queryFn: () => api<z.infer<typeof settingsSchema> & { name: string }>("/tenants/me/") });
  const { register, handleSubmit, formState: { errors } } = useForm<z.infer<typeof settingsSchema>>({ resolver: zodResolver(settingsSchema), values: q.data });
  const save = useMutation({ mutationFn: (v: object) => api("/tenants/me/", { method: "PATCH", body: v }), onSuccess: () => { setMsg("Saved."); qc.invalidateQueries({ queryKey: ["branding"] }); }, onError: (e) => setMsg(errText(e)) });
  if (q.isLoading) return <p>Loading…</p>;
  const f = (k: keyof z.infer<typeof settingsSchema>, label: string, ph: string) => <label className="text-sm font-medium">{label}<input className={inputCls} placeholder={ph} {...register(k)} /><Err m={errors[k]?.message} /></label>;
  return (
    <form noValidate onSubmit={handleSubmit((v) => { setMsg(null); save.mutate(v); })} className="grid max-w-3xl gap-3 rounded-xl bg-white p-6 shadow-sm md:grid-cols-2">
      <h1 className="text-2xl font-semibold md:col-span-2">Pharmacy settings — {q.data?.name}</h1>
      {f("address", "Address", "Enter the pharmacy address")}{f("city", "City", "Enter the city")}{f("region", "Region", "Enter the region")}
      {f("contact_email", "Contact email", "Enter the contact email")}{f("contact_phone", "Contact phone", "Enter the contact phone")}
      {f("primary_color", "Primary color", "Enter the primary color")}{f("secondary_color", "Secondary color", "Enter the secondary color")}
      <label className="text-sm font-medium md:col-span-2">Description<textarea className={inputCls} placeholder="Enter the pharmacy description" {...register("description")} /></label>
      <button disabled={save.isPending} className="rounded px-4 py-2 text-white md:w-32" style={{ background: "var(--brand)" }}>Save</button>
      {msg && <p role="status" className="text-sm md:col-span-2">{msg}</p>}
    </form>
  );
}
