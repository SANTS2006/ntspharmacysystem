import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";
import { ApiError, api } from "../../lib/api";
import { EmptyState, Loading, PageHeader } from "../../components/ui";

export interface Pharmacy { id: number; name: string; slug: string; status: string; city: string; country: string; created_at: string; primary_color: string }
interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }

const hex = z.string().regex(/^#[0-9A-Fa-f]{6}$/, "Enter a color like #059669.");
const schema = z.object({
  name: z.string().min(2, "Enter the pharmacy name."),
  slug: z.string().regex(/^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/, "Use 3-63 lowercase letters, numbers or hyphens."),
  description: z.string().optional(),
  registration_number: z.string().optional(), license_number: z.string().optional(),
  address: z.string().optional(), country: z.string().min(2, "Enter the country."), region: z.string().optional(), city: z.string().optional(),
  contact_email: z.union([z.literal(""), z.string().email("Enter a valid email address.")]), contact_phone: z.string().optional(),
  primary_color: hex, secondary_color: hex,
  admin_full_name: z.string().min(2, "Enter the administrator's full name."),
  admin_email: z.string().email("Enter a valid email address."), admin_phone: z.string().optional(),
  use_invitation: z.boolean(),
});
type Form = z.infer<typeof schema>;

function Field({ label, error, required, children }: { label: string; error?: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className="block text-sm font-medium">{label} {required && <span aria-hidden className="text-red-600">*</span>}
      {children}{error && <span role="alert" className="block text-xs text-red-600">{error}</span>}
    </label>
  );
}
const input = "mt-1 w-full px-3 py-2 font-normal";

function RegisterForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [logo, setLogo] = useState<File | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors } } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { country: "Sierra Leone", primary_color: "#059669", secondary_color: "#142D3D", use_invitation: true, contact_email: "" },
  });
  const m = useMutation({
    mutationFn: (v: Form) => {
      const fd = new FormData();
      Object.entries(v).forEach(([k, val]) => { if (val !== undefined && val !== "") fd.append(k, String(val)); });
      if (logo) fd.append("logo", logo);
      return api<Pharmacy>("/platform/pharmacies/", { method: "POST", body: fd });
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["pharmacies"] }); onDone(); },
    onError: (e) => setServerError(e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Registration failed."),
  });
  return (
    <form onSubmit={handleSubmit((v) => { setServerError(null); m.mutate(v); })} noValidate className="grid gap-3 rounded-xl bg-white p-6 shadow md:grid-cols-2">
      <h2 className="text-lg font-semibold md:col-span-2">Register a pharmacy</h2>
      {serverError && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700 md:col-span-2">{serverError}</p>}
      <Field label="Pharmacy name" required error={errors.name?.message}><input className={input} placeholder="Enter the pharmacy name" {...register("name")} /></Field>
      <Field label="Website address (slug)" required error={errors.slug?.message}><input className={input} placeholder="Enter the pharmacy slug" {...register("slug")} /></Field>
      <Field label="Registration number"><input className={input} placeholder="Enter the registration number" {...register("registration_number")} /></Field>
      <Field label="License number"><input className={input} placeholder="Enter the license number" {...register("license_number")} /></Field>
      <Field label="Country" required error={errors.country?.message}><input className={input} placeholder="Enter the country" {...register("country")} /></Field>
      <Field label="Region"><input className={input} placeholder="Enter the region" {...register("region")} /></Field>
      <Field label="City"><input className={input} placeholder="Enter the city" {...register("city")} /></Field>
      <Field label="Address"><input className={input} placeholder="Enter the address" {...register("address")} /></Field>
      <Field label="Contact email" error={errors.contact_email?.message}><input className={input} placeholder="Enter the contact email" {...register("contact_email")} /></Field>
      <Field label="Contact phone"><input className={input} placeholder="Enter the contact phone" {...register("contact_phone")} /></Field>
      <Field label="Primary color" error={errors.primary_color?.message}><input className={input} placeholder="Enter the primary color" {...register("primary_color")} /></Field>
      <Field label="Secondary color" error={errors.secondary_color?.message}><input className={input} placeholder="Enter the secondary color" {...register("secondary_color")} /></Field>
      <Field label="Logo (PNG, JPG or WebP, max 2 MB)"><input type="file" accept="image/png,image/jpeg,image/webp" className={input} onChange={(e) => setLogo(e.target.files?.[0] ?? null)} /></Field>
      <Field label="Description"><textarea className={input} placeholder="Enter the pharmacy description" {...register("description")} /></Field>
      <Field label="Administrator full name" required error={errors.admin_full_name?.message}><input className={input} placeholder="Enter the administrator's full name" {...register("admin_full_name")} /></Field>
      <Field label="Administrator email" required error={errors.admin_email?.message}><input className={input} placeholder="Enter the administrator's email" {...register("admin_email")} /></Field>
      <Field label="Administrator phone"><input className={input} placeholder="Enter the administrator's phone" {...register("admin_phone")} /></Field>
      <label className="flex items-center gap-2 text-sm md:col-span-2"><input type="checkbox" {...register("use_invitation")} /> Send a one-time invitation link instead of a temporary password (recommended)</label>
      <div className="flex gap-2 md:col-span-2">
        <button disabled={m.isPending} className="btn btn-primary">{m.isPending ? "Registering…" : "Register pharmacy"}</button>
        <button type="button" onClick={onDone} className="btn btn-outline">Cancel</button>
      </div>
    </form>
  );
}

export default function Pharmacies() {
  const [q, setQ] = useState(""); const [status, setStatus] = useState(""); const [page, setPage] = useState(1); const [adding, setAdding] = useState(false);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["pharmacies", q, status, page],
    queryFn: () => api<Page<Pharmacy>>(`/platform/pharmacies/?page=${page}&search=${encodeURIComponent(q)}${status ? `&status=${status}` : ""}`),
  });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PageHeader title="Pharmacies" subtitle="Register and manage pharmacy tenants." />
        <button onClick={() => setAdding(true)} className="btn btn-primary">Register pharmacy</button>
      </div>
      {adding && <RegisterForm onDone={() => setAdding(false)} />}
      <div className="flex gap-2">
        <input aria-label="Search pharmacies" placeholder="Enter a pharmacy name or slug" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} className="w-64 px-3 py-2" />
        <select aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="px-3 py-2">
          <option value="">All statuses</option><option value="active">Active</option><option value="suspended">Suspended</option>
        </select>
      </div>
      {isLoading && <Loading />}
      {isError && <p role="alert">Pharmacies could not be loaded.</p>}
      {data && data.results.length === 0 && <EmptyState>No pharmacies found.</EmptyState>}
      {data && data.results.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Name</th><th>Address</th><th>Location</th><th>Status</th></tr></thead>
            <tbody>{data.results.map((p) => (
              <tr key={p.id}>
                <td><Link className="font-medium text-teal-800 underline" to={`/platform/pharmacies/${p.id}`}>{p.name}</Link></td>
                <td>/{p.slug}</td><td>{[p.city, p.country].filter(Boolean).join(", ")}</td>
                <td><span className={`rounded px-2 py-0.5 text-xs ${p.status === "active" ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"}`}>{p.status}</span></td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
      <div className="flex items-center gap-2">
        <button disabled={!data?.previous} onClick={() => setPage((p) => p - 1)} className="btn btn-outline btn-sm">Previous</button>
        <span className="text-sm">Page {page}</span>
        <button disabled={!data?.next} onClick={() => setPage((p) => p + 1)} className="btn btn-outline btn-sm">Next</button>
      </div>
    </div>
  );
}
