import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ApiError, api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { EmptyState, Loading, PageHeader, useConfirm, usePrompt } from "../../components/ui";

interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
interface Medicine { id: number; name: string; generic_name: string; strength: string; dosage_form: string; barcode: string; classification: string; category: number; category_name: string; selling_price: string; reorder_level: number; stock: number | null; status: string }
interface Category { id: number; name: string }
interface Branch { id: number; name: string }
interface BatchRow { id: number; medicine: number; medicine_name: string; branch: number; branch_name: string; batch_number: string; expiry_date: string | null; quantity_available: number; status: string; is_expired: boolean; saleable: boolean }

const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const inputCls = "mt-1 w-full px-3 py-2 font-normal";
const Err = ({ m }: { m?: string }) => (m ? <span role="alert" className="block text-xs text-red-600">{m}</span> : null);
const brand = { background: "var(--brand)" };

// ---------------- Medicines ----------------
const medSchema = z.object({
  name: z.string().min(2, "Enter the medicine name."), generic_name: z.string().optional(), brand_name: z.string().optional(),
  category: z.string().min(1, "Select a category."), strength: z.string().optional(), dosage_form: z.string().optional(),
  barcode: z.union([z.literal(""), z.string().regex(/^[A-Za-z0-9-]{6,32}$/, "Use 6-32 letters, numbers or hyphens.")]),
  sku: z.string().optional(), classification: z.enum(["otc", "prescription", "controlled"]), registration_number: z.string().optional(),
  purchase_price: z.string(), selling_price: z.string(), reorder_level: z.string(),
}).refine((v) => v.classification === "otc" || !!v.registration_number, { path: ["registration_number"], message: "Enter the registration number for prescription and controlled medicines." });

export function MedicinesPage() {
  const { user } = useAuth(); const qc = useQueryClient();
  const canManage = user?.permissions.includes("medicine.manage");
  const [q, setQ] = useState(""); const [page, setPage] = useState(1); const [err, setErr] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["medicines", q, page], queryFn: () => api<Page<Medicine>>(`/medicines/?page=${page}&search=${encodeURIComponent(q)}`) });
  const cats = useQuery({ queryKey: ["categories"], queryFn: () => api<Category[]>("/categories/") });
  const { register, handleSubmit, reset, formState: { errors } } = useForm<z.infer<typeof medSchema>>({ resolver: zodResolver(medSchema), defaultValues: { classification: "otc", purchase_price: "0", selling_price: "0", reorder_level: "0", barcode: "" } });
  const create = useMutation({
    mutationFn: (v: z.infer<typeof medSchema>) => api("/medicines/", { method: "POST", body: { ...v, category: Number(v.category), reorder_level: Number(v.reorder_level) } }),
    onSuccess: () => { reset(); setErr(null); qc.invalidateQueries({ queryKey: ["medicines"] }); }, onError: (e) => setErr(errText(e)),
  });
  const f = (k: keyof z.infer<typeof medSchema>, label: string, ph: string, req = false) => <label className="text-sm font-medium">{label}{req && <span aria-hidden className="text-red-600"> *</span>}<input className={inputCls} placeholder={ph} {...register(k)} /><Err m={errors[k]?.message} /></label>;
  return (
    <div className="space-y-4">
      <PageHeader title="Medicines" subtitle="Your medicine catalogue, pricing and classification." />
      {canManage && (
        <form noValidate onSubmit={handleSubmit((v) => create.mutate(v))} className="grid gap-3 card p-4  md:grid-cols-4">
          {f("name", "Name", "Enter the medicine name", true)}{f("generic_name", "Generic name", "Enter the generic name")}{f("brand_name", "Brand name", "Enter the brand name")}
          <label className="text-sm font-medium">Category <span aria-hidden className="text-red-600">*</span><select className={inputCls} {...register("category")}><option value="">Select a category</option>{cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select><Err m={errors.category?.message} /></label>
          {f("strength", "Strength", "Enter the strength")}{f("dosage_form", "Dosage form", "Enter the dosage form")}{f("barcode", "Barcode", "Enter the barcode")}{f("sku", "SKU", "Enter the SKU")}
          <label className="text-sm font-medium">Classification<select className={inputCls} {...register("classification")}><option value="otc">Over the counter</option><option value="prescription">Prescription only</option><option value="controlled">Controlled</option></select></label>
          {f("registration_number", "Registration number", "Enter the registration number")}{f("purchase_price", "Purchase price", "Enter the purchase price")}{f("selling_price", "Selling price", "Enter the selling price")}{f("reorder_level", "Reorder level", "Enter the reorder level")}
          <button disabled={create.isPending} className="btn btn-primary self-end">Add medicine</button>
        </form>)}
      {err && <p role="alert" className="alert alert-error">{err}</p>}
      <input aria-label="Search medicines" placeholder="Enter a name, barcode or SKU" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} className="w-72 px-3 py-2" />
      {list.isLoading && <Loading />}{list.data?.results.length === 0 && <EmptyState>No medicines found.</EmptyState>}
      {list.data && list.data.results.length > 0 && <div className="table-wrap"><table className="table"><thead><tr><th>Name</th><th>Category</th><th>Class</th><th>Price</th><th>In stock</th></tr></thead>
        <tbody>{list.data.results.map((m) => <tr key={m.id}><td>{m.name} <span className="text-slate-500">{m.strength}</span></td><td>{m.category_name}</td>
          <td>{m.classification === "otc" ? "OTC" : <strong className="text-red-700">{m.classification === "controlled" ? "Controlled" : "Rx only"}</strong>}</td><td>{m.selling_price}</td>
          <td className={m.stock === 0 ? "text-red-700" : ""}>{m.stock}</td></tr>)}</tbody></table></div>}
      <div className="flex gap-2"><button disabled={!list.data?.previous} onClick={() => setPage(page - 1)} className="btn btn-outline btn-sm">Previous</button><button disabled={!list.data?.next} onClick={() => setPage(page + 1)} className="btn btn-outline btn-sm">Next</button></div>
    </div>
  );
}

// ---------------- Inventory ----------------
const recvSchema = z.object({ medicine: z.string().min(1, "Select a medicine."), branch: z.string().min(1, "Select a branch."), batch_number: z.string().min(1, "Enter the batch number."), quantity: z.string().regex(/^[1-9]\d*$/, "Enter a whole number above zero."), purchase_cost: z.string().min(1, "Enter the purchase cost."), expiry_date: z.string().optional(), supplier_name: z.string().optional() });
type Tab = "overview" | "batches" | "alerts" | "movements";

export function InventoryPage() {
  const promptFor = usePrompt(); const confirmDialog = useConfirm();
  const { user } = useAuth(); const qc = useQueryClient();
  const canManage = user?.permissions.includes("inventory.manage");
  const [tab, setTab] = useState<Tab>("overview"); const [err, setErr] = useState<string | null>(null);
  const meds = useQuery({ queryKey: ["medicines-all"], queryFn: () => api<Page<Medicine>>("/medicines/?status=active&ordering=name") });
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => api<Page<Branch>>("/branches/"), enabled: !!user?.permissions.includes("branch.view") });
  const overview = useQuery({ queryKey: ["inv-overview"], queryFn: () => api<Page<Medicine>>("/inventory/overview/"), enabled: tab === "overview" });
  const batches = useQuery({ queryKey: ["batches"], queryFn: () => api<Page<BatchRow>>("/batches/?ordering=expiry_date"), enabled: tab === "batches" });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api<{ near_expiry_days: number; low_stock: Medicine[]; out_of_stock: Medicine[]; near_expiry: BatchRow[]; expired: BatchRow[] }>("/inventory/alerts/"), enabled: tab === "alerts" });
  const moves = useQuery({ queryKey: ["movements"], queryFn: () => api<Page<{ id: number; created_at: string; medicine_name: string; batch_number: string; movement_type: string; quantity_change: number; previous_quantity: number; new_quantity: number; user_email: string | null; reason: string }>>("/inventory/movements/"), enabled: tab === "movements" });
  const { register, handleSubmit, reset, formState: { errors } } = useForm<z.infer<typeof recvSchema>>({ resolver: zodResolver(recvSchema), defaultValues: { branch: user?.branch ? String(user.branch) : "" } });
  const refresh = () => qc.invalidateQueries();
  const receive = useMutation({ mutationFn: (v: z.infer<typeof recvSchema>) => api("/inventory/receive/", { method: "POST", body: { ...v, medicine: Number(v.medicine), branch: Number(v.branch), quantity: Number(v.quantity), expiry_date: v.expiry_date || null } }), onSuccess: () => { reset(); setErr(null); refresh(); }, onError: (e) => setErr(errText(e)) });
  const action = useMutation({ mutationFn: ({ id, path, body }: { id: number; path: string; body: object }) => api(`/batches/${id}/${path}/`, { method: "POST", body }), onSuccess: () => { setErr(null); refresh(); }, onError: (e) => setErr(errText(e)) });
  const writeOff = async (b: BatchRow, kind: "expired" | "damaged") => { const v = await promptFor({ title: `Write off ${b.batch_number} as ${kind}`, message: "ALL remaining stock of this batch is written off. This is permanent and logged.", confirmLabel: "Write off stock", danger: true, fields: [{ name: "reason", label: "Reason", type: "textarea" }] }); if (v?.reason) action.mutate({ id: b.id, path: "write-off", body: { kind, reason: v.reason } }); };
  const adjust = async (b: BatchRow) => { const v = await promptFor({ title: `Adjust ${b.batch_number}`, confirmLabel: "Save adjustment", fields: [{ name: "n", label: `Counted quantity (currently ${b.quantity_available})`, type: "number", min: 0, step: "1" }, { name: "reason", label: "Reason for the adjustment", type: "textarea" }] }); if (v?.reason) action.mutate({ id: b.id, path: "adjust", body: { new_quantity: Number(v.n), reason: v.reason } }); };
  const quarantine = async (b: BatchRow) => { const v = await promptFor({ title: `Quarantine ${b.batch_number}`, confirmLabel: "Quarantine", danger: true, fields: [{ name: "reason", label: "Reason to quarantine this batch", type: "textarea" }] }); if (v?.reason) action.mutate({ id: b.id, path: "status", body: { status: "quarantined", reason: v.reason } }); };
  const badge = (b: BatchRow) => b.is_expired ? <span className="rounded bg-red-100 px-2 text-xs text-red-800">expired</span> : <span className={`rounded px-2 text-xs ${b.status === "available" ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"}`}>{b.status}</span>;
  const BatchTable = ({ rows, actions = true }: { rows: BatchRow[]; actions?: boolean }) => rows.length === 0 ? <p className="text-slate-500">None.</p> : (
    <div className="table-wrap"><table className="table"><thead><tr><th>Medicine</th><th>Branch</th><th>Batch</th><th>Expiry</th><th>Qty</th><th>Status</th><th /></tr></thead>
      <tbody>{rows.map((b) => <tr key={b.id}><td>{b.medicine_name}</td><td>{b.branch_name}</td><td>{b.batch_number}</td><td>{b.expiry_date ?? "—"}</td><td>{b.quantity_available}</td><td>{badge(b)}</td>
        <td className="space-x-2">{canManage && actions && b.quantity_available > 0 && <>
          <button className="btn-link" onClick={() => adjust(b)}>Adjust</button>
          {b.is_expired ? <button className="btn-link" onClick={() => writeOff(b, "expired")}>Write off</button> : <><button className="btn-link" onClick={() => writeOff(b, "damaged")}>Damaged</button>{b.status === "available" && <button className="btn-link" onClick={() => quarantine(b)}>Quarantine</button>}</>}</>}</td></tr>)}</tbody></table></div>);
  return (
    <div className="space-y-4">
      <PageHeader title="Inventory" subtitle="Stock levels, batches, expiry alerts and movement history." />
      {canManage && (
        <form noValidate onSubmit={handleSubmit((v) => receive.mutate(v))} className="grid gap-3 card p-4  md:grid-cols-4">
          <h2 className="font-semibold md:col-span-4">Receive stock</h2>
          <label className="text-sm font-medium">Medicine<select className={inputCls} {...register("medicine")}><option value="">Select a medicine</option>{meds.data?.results.map((m) => <option key={m.id} value={m.id}>{m.name} {m.strength}</option>)}</select><Err m={errors.medicine?.message} /></label>
          <label className="text-sm font-medium">Branch<select className={inputCls} {...register("branch")}><option value="">Select a branch</option>{branches.data?.results.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select><Err m={errors.branch?.message} /></label>
          <label className="text-sm font-medium">Batch number<input className={inputCls} placeholder="Enter the batch number" {...register("batch_number")} /><Err m={errors.batch_number?.message} /></label>
          <label className="text-sm font-medium">Quantity<input className={inputCls} placeholder="Enter the quantity" {...register("quantity")} /><Err m={errors.quantity?.message} /></label>
          <label className="text-sm font-medium">Unit cost<input className={inputCls} placeholder="Enter the unit cost" {...register("purchase_cost")} /><Err m={errors.purchase_cost?.message} /></label>
          <label className="text-sm font-medium">Expiry date<input type="date" className={inputCls} {...register("expiry_date")} /></label>
          <label className="text-sm font-medium">Supplier<input className={inputCls} placeholder="Enter the supplier name" {...register("supplier_name")} /></label>
          <button disabled={receive.isPending} className="btn btn-primary self-end">Receive</button>
        </form>)}
      {err && <p role="alert" className="alert alert-error">{err}</p>}
      <div role="tablist" className="tablist">{(["overview", "batches", "alerts", "movements"] as Tab[]).map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`tab ${tab === t ? "tab-active" : ""}`}>{t[0].toUpperCase() + t.slice(1)}</button>)}</div>
      {tab === "overview" && (overview.isLoading ? <Loading /> : <div className="table-wrap"><table className="table"><thead><tr><th>Medicine</th><th>Category</th><th>Saleable</th><th>Reorder at</th></tr></thead><tbody>{overview.data?.results.map((m) => <tr key={m.id}><td>{m.name}</td><td>{m.category_name}</td><td className={m.stock === 0 ? "font-semibold text-red-700" : (m.stock ?? 0) <= m.reorder_level ? "font-semibold text-amber-700" : ""}>{m.stock}</td><td>{m.reorder_level}</td></tr>)}</tbody></table></div>)}
      {tab === "batches" && (batches.isLoading ? <Loading /> : <BatchTable rows={batches.data?.results ?? []} />)}
      {tab === "alerts" && (alerts.isLoading ? <Loading /> : alerts.data && <div className="space-y-4">
        <section><h2 className="section-title">Expired (not sellable)</h2><BatchTable rows={alerts.data.expired} /></section>
        <section><h2 className="section-title">Expiring within {alerts.data.near_expiry_days} days</h2><BatchTable rows={alerts.data.near_expiry} /></section>
        <section><h2 className="section-title">Low stock</h2><ul className="text-sm">{alerts.data.low_stock.map((m) => <li key={m.id}>{m.name}: {m.stock} (reorder at {m.reorder_level})</li>)}{alerts.data.low_stock.length === 0 && <li className="text-slate-500">None.</li>}</ul></section>
        <section><h2 className="section-title">Out of stock</h2><ul className="text-sm">{alerts.data.out_of_stock.map((m) => <li key={m.id}>{m.name}</li>)}{alerts.data.out_of_stock.length === 0 && <li className="text-slate-500">None.</li>}</ul></section></div>)}
      {tab === "movements" && (moves.isLoading ? <Loading /> : <div className="table-wrap"><table className="table"><thead><tr><th>When</th><th>Medicine</th><th>Batch</th><th>Type</th><th>Change</th><th>Before → after</th><th>By</th></tr></thead><tbody>{moves.data?.results.map((m) => <tr key={m.id}><td>{new Date(m.created_at).toLocaleString()}</td><td>{m.medicine_name}</td><td>{m.batch_number}</td><td>{m.movement_type}</td><td>{m.quantity_change}</td><td>{m.previous_quantity} → {m.new_quantity}</td><td>{m.user_email}</td></tr>)}</tbody></table></div>)}
    </div>
  );
}
