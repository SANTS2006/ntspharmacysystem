/** Medicine catalogue and stock control. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Archive, ArchiveRestore, Boxes, CalendarX2, PackageMinus, PackagePlus, Pencil, Pill, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { DataTable, ErrorState, FormModal, Loading, PageHeader, StatCard, StatusBadge, Tabs, errorMessage, useConfirm, usePrompt, useToast, type FieldDef, type Values } from "../../components/ui";
import { ServerTable, type ApiPage } from "../../components/ui/ServerTable";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, day, money, words } from "../../lib/format";
import { useBranchOptions } from "./TenantPages";

interface Medicine { id: number; name: string; generic_name: string; brand_name: string; strength: string; dosage_form: string; barcode: string; sku: string; classification: "otc" | "prescription" | "controlled"; registration_number: string; category: number; category_name: string; purchase_price: string; selling_price: string; reorder_level: number; stock: number | null; status: string; image: string | null; description: string; is_online_visible: boolean; tax_rate: string }
interface Category { id: number; name: string }
interface BatchRow { id: number; medicine: number; medicine_name: string; branch: number; branch_name: string; batch_number: string; expiry_date: string | null; quantity_available: number; status: string; is_expired: boolean; saleable: boolean }

const useCategories = () => useQuery({ queryKey: ["categories"], queryFn: () => api<Category[]>("/categories/") });

function medicineFields(categories: Category[], m?: Medicine): FieldDef[] {
  return [
    { name: "name", label: "Medicine name", defaultValue: m?.name }, { name: "generic_name", label: "Generic name", required: false, defaultValue: m?.generic_name },
    { name: "brand_name", label: "Brand name", required: false, defaultValue: m?.brand_name },
    { name: "category", label: "Category", type: "select", options: categories.map((c) => [String(c.id), c.name]), defaultValue: m?.category },
    { name: "strength", label: "Strength", required: false, defaultValue: m?.strength }, { name: "dosage_form", label: "Dosage form", required: false, defaultValue: m?.dosage_form },
    { name: "barcode", label: "Barcode", required: false, defaultValue: m?.barcode, hint: "6–32 letters, numbers or hyphens" }, { name: "sku", label: "SKU", required: false, defaultValue: m?.sku },
    { name: "classification", label: "Classification", type: "select", defaultValue: m?.classification ?? "otc", options: [["otc", "Over the counter"], ["prescription", "Prescription only"], ["controlled", "Controlled"]] },
    { name: "registration_number", label: "Registration number", required: false, defaultValue: m?.registration_number, hint: "Required for prescription and controlled medicines" },
    { name: "purchase_price", label: "Purchase price", type: "number", min: 0, step: "0.01", defaultValue: m?.purchase_price ?? "0" },
    { name: "selling_price", label: "Selling price", type: "number", min: 0, step: "0.01", defaultValue: m?.selling_price ?? "0" },
    { name: "tax_rate", label: "Tax rate percent", type: "number", min: 0, max: 100, step: "0.01", defaultValue: m?.tax_rate ?? "0" },
    { name: "reorder_level", label: "Reorder level", type: "number", min: 0, step: "1", defaultValue: m?.reorder_level ?? 0 },
    { name: "description", label: "Description", type: "textarea", required: false, defaultValue: m?.description },
    { name: "image", label: "Product picture", type: "file", accept: "image/png,image/jpeg,image/webp", wide: true, hint: "Shown on your website" },
    { name: "is_online_visible", label: "Show on the pharmacy website", type: "checkbox", defaultValue: m?.is_online_visible ?? true },
  ];
}

export function MedicinesPage() {
  const { can } = useAuth(); const qc = useQueryClient(); const toast = useToast(); const confirm = useConfirm();
  const manage = can("medicine.manage");
  const [tab, setTab] = useState<"medicines" | "categories">("medicines");
  const [editing, setEditing] = useState<Medicine | "new" | null>(null);
  const [category, setCategory] = useState<Category | "new" | null>(null);
  const cats = useCategories();
  const done = (text: string) => { qc.invalidateQueries({ queryKey: ["medicines"] }); qc.invalidateQueries({ queryKey: ["categories"] }); toast(text); };
  const fail = (e: unknown) => toast(errorMessage(e), "error");
  const archive = async (m: Medicine) => {
    const restore = m.status !== "active";
    if (!(await confirm({ title: `${restore ? "Restore" : "Delete"} ${m.name}?`, message: restore ? "It becomes available again." : "It is archived: removed from selling and the website, while its stock and sales history are kept.", confirmLabel: restore ? "Restore" : "Delete", danger: !restore }))) return;
    api(`/medicines/${m.id}/${restore ? "restore" : "archive"}/`, { method: "POST" }).then(() => done(restore ? "Medicine restored." : "Medicine archived.")).catch(fail);
  };
  const save = async (v: Values, files: Record<string, File | null>) => {
    const data: Record<string, string> = { ...v, is_online_visible: v.is_online_visible === "true" ? "true" : "false" };
    delete data.image;
    let body: unknown = data;
    if (files.image) { const fd = new FormData(); Object.entries(data).forEach(([k, x]) => fd.append(k, x)); fd.append("image", files.image); body = fd; }
    await api(editing === "new" ? "/medicines/" : `/medicines/${(editing as Medicine).id}/`, { method: editing === "new" ? "POST" : "PATCH", body });
    done(editing === "new" ? "Medicine added." : "Medicine updated.");
  };
  return (
    <div className="space-y-5">
      <PageHeader title="Medicines" subtitle="Your medicine catalogue, pricing and classification."
        actions={manage && (tab === "medicines" ? <button className="btn btn-primary" disabled={!cats.data?.length} onClick={() => setEditing("new")}><Plus size={16} aria-hidden />Add medicine</button> : <button className="btn btn-primary" onClick={() => setCategory("new")}><Plus size={16} aria-hidden />Add category</button>)} />
      <Tabs tabs={[["medicines", "Medicines"], ["categories", "Categories"]]} value={tab} onChange={setTab} />
      {cats.data?.length === 0 && <div className="alert alert-info flex-wrap items-center justify-between"><span>{manage ? "Create your first medicine category. Every medicine belongs to one." : "No medicine categories have been created yet."}</span>{manage && <button className="btn btn-primary btn-sm" onClick={() => { setTab("categories"); setCategory("new"); }}><Plus size={14} aria-hidden />Create a category</button>}</div>}
      {tab === "medicines" && <ServerTable<Medicine> queryKey={["medicines"]} path="/medicines/" rowKey={(m) => m.id} search="Enter your name, barcode or SKU" empty="No medicines found."
        filters={[{ name: "category", label: "All categories", options: (cats.data ?? []).map((c) => [String(c.id), c.name]) }, { name: "classification", label: "All classes", options: [["otc", "Over the counter"], ["prescription", "Prescription only"], ["controlled", "Controlled"]] }, { name: "status", label: "Any status", options: [["active", "Active"], ["archived", "Archived"]] }]}
        columns={[
          { key: "name", header: "Medicine", sort: (m) => m.name, render: (m) => <span className="flex items-center gap-3">{m.image ? <img src={m.image} alt="" className="h-10 w-10 rounded-xl border border-line object-cover" /> : <span className="grid h-10 w-10 place-items-center rounded-xl bg-teal-50 text-teal-700"><Pill size={18} aria-hidden /></span>}<span><b className="block">{m.name} <span className="font-normal text-muted">{m.strength}</span></b><span className="text-xs text-muted">{[m.generic_name, m.dosage_form].filter(Boolean).join(" · ")}</span></span></span> },
          { key: "category", header: "Category", render: (m) => m.category_name },
          { key: "class", header: "Class", render: (m) => m.classification === "otc" ? <span className="badge badge-neutral">OTC</span> : <span className="badge badge-danger">{m.classification === "controlled" ? "Controlled" : "Rx only"}</span> },
          { key: "price", header: "Price", align: "right", sort: (m) => Number(m.selling_price), render: (m) => <b>{money(m.selling_price)}</b> },
          { key: "stock", header: "In stock", align: "center", render: (m) => <span className={`badge ${!m.stock ? "badge-danger" : m.stock <= m.reorder_level ? "badge-warning" : "badge-success"}`}>{m.stock ?? 0}</span> },
          { key: "status", header: "Status", render: (m) => <StatusBadge status={m.status} /> },
          ...(manage ? [{ key: "actions", header: "Actions", align: "right" as const, render: (m: Medicine) => <span className="inline-flex gap-1.5"><button className="btn-link" onClick={() => setEditing(m)}><Pencil size={13} aria-hidden />Edit</button><button className={`btn-link ${m.status === "active" ? "btn-link-danger" : ""}`} onClick={() => archive(m)}>{m.status === "active" ? <><Archive size={13} aria-hidden />Delete</> : <><ArchiveRestore size={13} aria-hidden />Restore</>}</button></span> }] : []),
        ]} />}
      {tab === "categories" && <DataTable<Category> rows={cats.data} loading={cats.isLoading} rowKey={(c) => c.id} search={(c) => c.name} empty="No categories yet." pageSize={12}
        columns={[{ key: "name", header: "Category", sort: (c) => c.name, render: (c) => <b>{c.name}</b> },
          ...(manage ? [{ key: "actions", header: "Actions", align: "right" as const, render: (c: Category) => <span className="inline-flex gap-1.5"><button className="btn-link" onClick={() => setCategory(c)}><Pencil size={13} aria-hidden />Edit</button><button className="btn-link btn-link-danger" onClick={async () => { if (await confirm({ title: `Delete the category ${c.name}?`, message: "Only categories without medicines can be deleted.", confirmLabel: "Delete", danger: true })) api(`/categories/${c.id}/`, { method: "DELETE" }).then(() => done("Category deleted.")).catch(fail); }}><Trash2 size={13} aria-hidden />Delete</button></span> }] : [])]} />}
      {editing && <FormModal title={editing === "new" ? "Add medicine" : `Edit ${editing.name}`} size="lg" fields={medicineFields(cats.data ?? [], editing === "new" ? undefined : editing)} onClose={() => setEditing(null)} onSubmit={save} submitLabel={editing === "new" ? "Add medicine" : "Save changes"} />}
      {category && <FormModal title={category === "new" ? "Add category" : `Edit ${category.name}`} fields={[{ name: "name", label: "Category name", defaultValue: category === "new" ? "" : category.name }]} onClose={() => setCategory(null)}
        onSubmit={async (v) => { await api(category === "new" ? "/categories/" : `/categories/${category.id}/`, { method: category === "new" ? "POST" : "PATCH", body: v }); done("Category saved."); }} />}
    </div>
  );
}

type Tab = "overview" | "batches" | "alerts" | "movements";
interface Alerts { near_expiry_days: number; low_stock: Medicine[]; out_of_stock: Medicine[]; near_expiry: BatchRow[]; expired: BatchRow[] }
interface Movement { id: number; created_at: string; medicine_name: string; batch_number: string; movement_type: string; quantity_change: number; previous_quantity: number; new_quantity: number; user_email: string | null; reason: string }

export function InventoryPage() {
  const prompt = usePrompt(); const toast = useToast(); const { user, can } = useAuth(); const qc = useQueryClient();
  const manage = can("inventory.manage");
  const [tab, setTab] = useState<Tab>("overview");
  const [receiving, setReceiving] = useState(false);
  const branches = useBranchOptions();
  const meds = useQuery({ queryKey: ["medicines", "options"], queryFn: () => api<ApiPage<Medicine>>("/medicines/?status=active&ordering=name&page_size=200"), enabled: receiving && can("medicine.view") });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api<Alerts>("/inventory/alerts/") });
  const medOptions = useMemo(() => (meds.data?.results ?? []).map((m) => [String(m.id), `${m.name} ${m.strength}`] as [string, string]), [meds.data]);
  const refresh = (text: string) => { ["batches", "alerts", "inv-overview", "movements", "medicines", "analytics"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); toast(text); };
  const act = async (id: number, path: string, body: object, text: string) => { try { await api(`/batches/${id}/${path}/`, { method: "POST", body }); refresh(text); } catch (e) { toast(errorMessage(e), "error"); } };
  const writeOff = async (b: BatchRow, kind: "expired" | "damaged") => { const v = await prompt({ title: `Write off ${b.batch_number} as ${kind}`, message: "ALL remaining stock of this batch is written off. This is permanent and logged.", confirmLabel: "Write off stock", danger: true, fields: [{ name: "reason", label: "Reason", type: "textarea" }] }); if (v?.reason) act(b.id, "write-off", { kind, reason: v.reason }, "Stock written off."); };
  const adjust = async (b: BatchRow) => { const v = await prompt({ title: `Adjust ${b.batch_number}`, confirmLabel: "Save adjustment", fields: [{ name: "n", label: "Counted quantity", type: "number", min: 0, step: "1", defaultValue: b.quantity_available }, { name: "reason", label: "Reason for the adjustment", type: "textarea" }] }); if (v?.reason) act(b.id, "adjust", { new_quantity: Number(v.n), reason: v.reason }, "Stock adjusted."); };
  const setStatus = async (b: BatchRow, status: "quarantined" | "available") => { const v = await prompt({ title: status === "quarantined" ? `Quarantine ${b.batch_number}` : `Release ${b.batch_number}`, confirmLabel: status === "quarantined" ? "Quarantine" : "Release", danger: status === "quarantined", fields: [{ name: "reason", label: "Reason", type: "textarea" }] }); if (v?.reason) act(b.id, "status", { status, reason: v.reason }, "Batch updated."); };

  const batchColumns = [
    { key: "medicine", header: "Medicine", render: (b: BatchRow) => <b>{b.medicine_name}</b>, sort: (b: BatchRow) => b.medicine_name },
    { key: "branch", header: "Branch", render: (b: BatchRow) => b.branch_name }, { key: "batch", header: "Batch", render: (b: BatchRow) => b.batch_number },
    { key: "expiry", header: "Expiry", render: (b: BatchRow) => day(b.expiry_date), sort: (b: BatchRow) => b.expiry_date ?? "9999" },
    { key: "qty", header: "Quantity", align: "center" as const, render: (b: BatchRow) => b.quantity_available, sort: (b: BatchRow) => b.quantity_available },
    { key: "status", header: "Status", render: (b: BatchRow) => <StatusBadge status={b.is_expired ? "expired" : b.status} /> },
    ...(manage ? [{ key: "actions", header: "Actions", align: "right" as const, render: (b: BatchRow) => b.quantity_available > 0 && <span className="inline-flex gap-1.5">
      <button className="btn-link" onClick={() => adjust(b)}>Adjust</button>
      {b.is_expired ? <button className="btn-link btn-link-danger" onClick={() => writeOff(b, "expired")}>Write off</button> : <><button className="btn-link btn-link-danger" onClick={() => writeOff(b, "damaged")}>Damaged</button>{b.status === "available" ? <button className="btn-link" onClick={() => setStatus(b, "quarantined")}>Quarantine</button> : b.status === "quarantined" && <button className="btn-link" onClick={() => setStatus(b, "available")}>Release</button>}</>}
    </span> }] : []),
  ];
  const a = alerts.data;
  return (
    <div className="space-y-5">
      <PageHeader title="Inventory" subtitle="Stock levels, batches, expiry alerts and movement history." actions={manage && <button className="btn btn-primary" onClick={() => setReceiving(true)}><PackagePlus size={16} aria-hidden />Receive stock</button>} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Low stock" value={a?.low_stock.length ?? "…"} icon={PackageMinus} tone="warning" />
        <StatCard label="Out of stock" value={a?.out_of_stock.length ?? "…"} icon={Boxes} tone="danger" />
        <StatCard label="Expiring soon" value={a?.near_expiry.length ?? "…"} icon={AlertTriangle} tone="warning" hint={a ? `Within ${a.near_expiry_days} days` : undefined} />
        <StatCard label="Expired batches" value={a?.expired.length ?? "…"} icon={CalendarX2} tone="danger" />
      </div>
      <Tabs tabs={[["overview", "Overview"], ["batches", "Batches"], ["alerts", "Alerts", a ? a.expired.length + a.out_of_stock.length : 0], ["movements", "Movements"]]} value={tab} onChange={setTab} />
      {tab === "overview" && <ServerTable<Medicine> queryKey={["inv-overview"]} path="/inventory/overview/" rowKey={(m) => m.id} empty="No stock yet."
        columns={[{ key: "name", header: "Medicine", render: (m) => <b>{m.name} <span className="font-normal text-muted">{m.strength}</span></b>, sort: (m) => m.name }, { key: "category", header: "Category", render: (m) => m.category_name }, { key: "stock", header: "Saleable stock", align: "center", sort: (m) => m.stock ?? 0, render: (m) => <span className={`badge ${!m.stock ? "badge-danger" : m.stock <= m.reorder_level ? "badge-warning" : "badge-success"}`}>{m.stock ?? 0}</span> }, { key: "reorder", header: "Reorder at", align: "center", render: (m) => m.reorder_level }]} />}
      {tab === "batches" && <ServerTable<BatchRow> queryKey={["batches"]} path="/batches/?ordering=expiry_date" rowKey={(b) => b.id} columns={batchColumns} search="Enter your batch or medicine search" empty="No batches yet." />}
      {tab === "alerts" && (alerts.isLoading ? <Loading /> : alerts.isError ? <ErrorState onRetry={() => alerts.refetch()}>{errorMessage(alerts.error)}</ErrorState> : a && <div className="space-y-6">
        <section className="space-y-2"><h2 className="section-title">Expired (not sellable)</h2><DataTable rows={a.expired} columns={batchColumns} rowKey={(b) => b.id} pageSize={8} empty="No expired batches." /></section>
        <section className="space-y-2"><h2 className="section-title">Expiring within {a.near_expiry_days} days</h2><DataTable rows={a.near_expiry} columns={batchColumns} rowKey={(b) => b.id} pageSize={8} empty="Nothing is close to expiry." /></section>
        <section className="space-y-2"><h2 className="section-title">Low and out of stock</h2><DataTable rows={[...a.out_of_stock, ...a.low_stock.filter((m) => !a.out_of_stock.some((o) => o.id === m.id))]} rowKey={(m) => m.id} pageSize={8} empty="Stock levels are healthy."
          columns={[{ key: "name", header: "Medicine", render: (m) => <b>{m.name}</b> }, { key: "stock", header: "In stock", align: "center", render: (m) => <span className={`badge ${m.stock ? "badge-warning" : "badge-danger"}`}>{m.stock ?? 0}</span> }, { key: "reorder", header: "Reorder at", align: "center", render: (m) => m.reorder_level }]} /></section>
      </div>)}
      {tab === "movements" && <ServerTable<Movement> queryKey={["movements"]} path="/inventory/movements/" rowKey={(m) => m.id} empty="No stock movements yet."
        columns={[{ key: "when", header: "When", render: (m) => dateTime(m.created_at) }, { key: "medicine", header: "Medicine", render: (m) => <b>{m.medicine_name}</b> }, { key: "batch", header: "Batch", render: (m) => m.batch_number }, { key: "type", header: "Type", render: (m) => <span className="badge badge-neutral">{words(m.movement_type)}</span> }, { key: "change", header: "Change", align: "right", render: (m) => <b className={m.quantity_change < 0 ? "text-red-700" : "text-emerald-700"}>{m.quantity_change > 0 ? `+${m.quantity_change}` : m.quantity_change}</b> }, { key: "balance", header: "Before → after", align: "center", render: (m) => `${m.previous_quantity} → ${m.new_quantity}` }, { key: "by", header: "By", render: (m) => m.user_email ?? "System" }]} />}
      {receiving && <FormModal title="Receive stock" size="lg" submitLabel="Receive stock" onClose={() => setReceiving(false)}
        fields={[{ name: "medicine", label: "Medicine", type: "select", options: medOptions }, { name: "branch", label: "Branch", type: "select", options: branches, defaultValue: user?.branch ?? "" }, { name: "batch_number", label: "Batch number" }, { name: "quantity", label: "Quantity", type: "number", min: 1, step: "1" }, { name: "purchase_cost", label: "Unit cost", type: "number", min: 0, step: "0.01" }, { name: "expiry_date", label: "Expiry date", type: "date", required: false }, { name: "supplier_name", label: "Supplier name", required: false }]}
        onSubmit={async (v) => { await api("/inventory/receive/", { method: "POST", body: { ...v, medicine: Number(v.medicine), branch: Number(v.branch), quantity: Number(v.quantity), expiry_date: v.expiry_date || null } }); refresh("Stock received."); }} />}
    </div>
  );
}
