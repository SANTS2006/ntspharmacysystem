/** Suppliers, requisitions, purchase orders, goods received and supplier invoices. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Power } from "lucide-react";
import { useMemo, useState } from "react";
import { FormModal, PageHeader, StatusBadge, Tabs, errorMessage, useConfirm, usePrompt, useToast, type FieldDef } from "../../components/ui";
import { ServerTable, type ApiPage } from "../../components/ui/ServerTable";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { day, money } from "../../lib/format";
import { useBranchOptions } from "./TenantPages";

interface Supplier { id: number; name: string; contact_person: string; phone: string; email: string; address: string; payment_terms_days: number; status: string }
interface OrderItem { id: number; medicine: number; medicine_name: string; quantity_ordered: number; quantity_received: number; unit_cost: string }
interface Order { id: number; number: string; supplier_name: string; branch: number; status: string; total: string; items: OrderItem[]; created_by: number }
interface Req { id: number; number: string; branch: number; status: string; requested_by: number; items: { medicine_name: string; quantity: number }[] }
interface Invoice { id: number; invoice_number: string; supplier_name: string; amount: string; amount_paid: string; balance: string; due_date: string; status: string }
type Tab = "orders" | "requisitions" | "suppliers" | "invoices";

const supplierFields = (s?: Supplier): FieldDef[] => [
  { name: "name", label: "Supplier name", defaultValue: s?.name }, { name: "contact_person", label: "Contact person", required: false, defaultValue: s?.contact_person },
  { name: "phone", label: "Supplier phone", type: "tel", required: false, defaultValue: s?.phone }, { name: "email", label: "Supplier email", type: "email", required: false, defaultValue: s?.email },
  { name: "address", label: "Supplier address", required: false, wide: true, defaultValue: s?.address }, { name: "payment_terms_days", label: "Payment terms in days", type: "number", min: 0, step: "1", required: false, defaultValue: s?.payment_terms_days ?? 30 },
];

export default function ProcurementPage() {
  const prompt = usePrompt(); const confirm = useConfirm(); const toast = useToast();
  const { user, can } = useAuth(); const qc = useQueryClient();
  const manage = can("procurement.manage"), approve = can("procurement.approve");
  const pharmacyLevel = !user?.branch; // invoices and payments are restricted to pharmacy-level staff by the API
  const [tab, setTab] = useState<Tab>("orders");
  const [dialog, setDialog] = useState<"order" | "requisition" | "invoice" | null>(null);
  const [supplier, setSupplier] = useState<Supplier | "new" | null>(null);
  const done = (text: string) => { ["suppliers", "reqs", "purchase-orders", "supplier-invoices", "batches", "alerts"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); toast(text); };
  const post = (path: string, body: object = {}, text = "Done.") => api(path, { method: "POST", body }).then(() => done(text)).catch((e) => toast(errorMessage(e), "error"));

  const suppliers = useQuery({ queryKey: ["suppliers", "options"], queryFn: () => api<ApiPage<Supplier>>("/suppliers/?page_size=200"), enabled: dialog !== null });
  const meds = useQuery({ queryKey: ["medicines", "options"], queryFn: () => api<ApiPage<{ id: number; name: string; strength: string }>>("/medicines/?status=active&ordering=name&page_size=200"), enabled: (dialog === "order" || dialog === "requisition") && can("medicine.view") });
  const branches = useBranchOptions();
  const supplierOptions = useMemo(() => (suppliers.data?.results ?? []).filter((s) => s.status !== "inactive").map((s) => [String(s.id), s.name] as [string, string]), [suppliers.data]);
  const medOptions = useMemo(() => (meds.data?.results ?? []).map((m) => [String(m.id), `${m.name} ${m.strength}`] as [string, string]), [meds.data]);
  const branchField: FieldDef = { name: "branch", label: "Branch", type: "select", options: branches, defaultValue: user?.branch ?? "" };
  const medField: FieldDef = { name: "medicine", label: "Medicine", type: "select", options: medOptions };
  const qtyField: FieldDef = { name: "quantity", label: "Quantity", type: "number", min: 1, step: "1" };

  const receive = async (o: Order) => {
    const item = o.items.find((i) => i.quantity_received < i.quantity_ordered);
    if (!item) return;
    const v = await prompt({ title: `Receive goods · ${item.medicine_name}`, message: `Outstanding: ${item.quantity_ordered - item.quantity_received} units.`, confirmLabel: "Receive stock", fields: [
      { name: "qty", label: "Quantity delivered", type: "number", min: 1, max: item.quantity_ordered - item.quantity_received, step: "1" }, { name: "batch", label: "Batch number" }, { name: "expiry", label: "Expiry date", type: "date" }] });
    if (v) post("/procurement/goods-receipts/", { order: o.id, lines: [{ order_item: item.id, quantity: Number(v.qty), batch_number: v.batch, expiry_date: v.expiry }] }, "Goods received into stock.");
  };
  const decide = async (path: string, verb: "Approve" | "Reject") => { const v = await prompt({ title: `${verb} this request?`, confirmLabel: verb, danger: verb === "Reject", fields: [{ name: "note", label: "Note", type: "textarea", required: false }] }); if (v) post(path, { note: v.note }, verb === "Approve" ? "Approved." : "Rejected."); };
  const cancel = async (path: string, what: string) => { if (await confirm({ title: `Cancel ${what}?`, message: "This cannot be undone.", confirmLabel: "Cancel it", danger: true })) post(path, {}, "Cancelled."); };
  const pay = async (i: Invoice) => {
    const v = await prompt({ title: `Pay ${i.invoice_number}`, message: `Outstanding: ${money(i.balance)}. Record a payment you have made to the supplier.`, confirmLabel: "Continue", fields: [
      { name: "amount", label: "Payment amount", type: "number", min: 0.01, step: "0.01", defaultValue: i.balance }, { name: "method", label: "Payment method", type: "select", defaultValue: "bank_transfer", options: [["bank_transfer", "Bank transfer"], ["mobile_money", "Mobile money"], ["cash", "Cash"]] }, { name: "reference", label: "Payment reference" }] });
    if (v && await confirm({ title: "Record this payment?", message: `${money(v.amount)} for ${i.invoice_number}. This is permanent.`, confirmLabel: "Record payment" })) post(`/procurement/invoices/${i.id}/pay/`, v, "Payment recorded.");
  };
  const tabs: [Tab, string][] = [["orders", "Purchase orders"], ["requisitions", "Requisitions"], ["suppliers", "Suppliers"], ...(pharmacyLevel ? [["invoices", "Supplier invoices"] as [Tab, string]] : [])];
  const label = { orders: "New purchase order", requisitions: "New requisition", suppliers: "Add supplier", invoices: "Record invoice" }[tab];

  return (
    <div className="space-y-5">
      <PageHeader title="Suppliers & purchases" subtitle="Suppliers, requisitions, purchase orders and goods received."
        actions={manage && <button className="btn btn-primary" onClick={() => tab === "suppliers" ? setSupplier("new") : setDialog(tab === "orders" ? "order" : tab === "requisitions" ? "requisition" : "invoice")}><Plus size={16} aria-hidden />{label}</button>} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === "orders" && <ServerTable<Order> queryKey={["purchase-orders"]} path="/procurement/orders/" rowKey={(o) => o.id} empty="No purchase orders."
        columns={[{ key: "number", header: "Order", render: (o) => <b>{o.number}</b> }, { key: "supplier", header: "Supplier", render: (o) => o.supplier_name }, { key: "items", header: "Items (received / ordered)", render: (o) => o.items.map((i) => <span key={i.id} className="block">{i.medicine_name} <span className="text-muted">{i.quantity_received}/{i.quantity_ordered}</span></span>) }, { key: "total", header: "Total", align: "right", render: (o) => <b>{money(o.total)}</b> }, { key: "status", header: "Status", render: (o) => <StatusBadge status={o.status} /> },
          { key: "actions", header: "Actions", align: "right", render: (o) => <span className="inline-flex flex-wrap justify-end gap-1.5">
            {o.status === "draft" && manage && <button className="btn-link" onClick={() => post(`/procurement/orders/${o.id}/submit/`, {}, "Submitted for approval.")}>Submit</button>}
            {o.status === "pending_approval" && approve && o.created_by !== user?.id && <><button className="btn-link" onClick={() => decide(`/procurement/orders/${o.id}/approve/`, "Approve")}>Approve</button><button className="btn-link btn-link-danger" onClick={() => decide(`/procurement/orders/${o.id}/reject/`, "Reject")}>Reject</button></>}
            {["approved", "partially_received"].includes(o.status) && manage && <button className="btn-link" onClick={() => receive(o)}>Receive goods</button>}
            {["draft", "pending_approval", "approved"].includes(o.status) && manage && <button className="btn-link btn-link-danger" onClick={() => cancel(`/procurement/orders/${o.id}/cancel/`, o.number)}>Cancel</button>}
          </span> }]} />}
      {tab === "requisitions" && <ServerTable<Req> queryKey={["reqs"]} path="/procurement/requisitions/" rowKey={(r) => r.id} empty="No requisitions."
        columns={[{ key: "number", header: "Requisition", render: (r) => <b>{r.number}</b> }, { key: "items", header: "Items", render: (r) => r.items.map((i) => `${i.medicine_name} × ${i.quantity}`).join(", ") }, { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
          { key: "actions", header: "Actions", align: "right", render: (r) => <span className="inline-flex gap-1.5">
            {r.status === "submitted" && approve && r.requested_by !== user?.id && <><button className="btn-link" onClick={() => decide(`/procurement/requisitions/${r.id}/approve/`, "Approve")}>Approve</button><button className="btn-link btn-link-danger" onClick={() => decide(`/procurement/requisitions/${r.id}/reject/`, "Reject")}>Reject</button></>}
            {["draft", "submitted"].includes(r.status) && manage && <button className="btn-link btn-link-danger" onClick={() => cancel(`/procurement/requisitions/${r.id}/cancel/`, r.number)}>Cancel</button>}
          </span> }]} />}
      {tab === "suppliers" && <ServerTable<Supplier> queryKey={["suppliers"]} path="/suppliers/" rowKey={(s) => s.id} search="Enter your supplier search" empty="No suppliers yet."
        columns={[{ key: "name", header: "Supplier", render: (s) => <><b className="block">{s.name}</b><span className="text-xs text-muted">{s.address}</span></> }, { key: "contact", header: "Contact person", render: (s) => s.contact_person || "—" }, { key: "phone", header: "Phone", render: (s) => s.phone || "—" }, { key: "email", header: "Email", render: (s) => s.email || "—" }, { key: "status", header: "Status", render: (s) => <StatusBadge status={s.status} /> },
          ...(manage ? [{ key: "actions", header: "Actions", align: "right" as const, render: (s: Supplier) => { const off = s.status === "active"; return <span className="inline-flex gap-1.5"><button className="btn-link" onClick={() => setSupplier(s)}><Pencil size={13} aria-hidden />Edit</button><button className={`btn-link ${off ? "btn-link-danger" : ""}`} onClick={async () => { if (await confirm({ title: `${off ? "Delete" : "Restore"} ${s.name}?`, message: off ? "The supplier is deactivated. Purchase history is kept." : "The supplier becomes active again.", confirmLabel: off ? "Delete" : "Restore", danger: off })) api(`/suppliers/${s.id}/`, { method: "PATCH", body: { status: off ? "inactive" : "active" } }).then(() => done("Supplier updated.")).catch((e) => toast(errorMessage(e), "error")); }}><Power size={13} aria-hidden />{off ? "Delete" : "Restore"}</button></span>; } }] : [])]} />}
      {tab === "invoices" && pharmacyLevel && <ServerTable<Invoice> queryKey={["supplier-invoices"]} path="/procurement/invoices/" rowKey={(i) => i.id} empty="No supplier invoices."
        columns={[{ key: "number", header: "Invoice", render: (i) => <b>{i.invoice_number}</b> }, { key: "supplier", header: "Supplier", render: (i) => i.supplier_name }, { key: "amount", header: "Amount", align: "right", render: (i) => money(i.amount) }, { key: "paid", header: "Paid", align: "right", render: (i) => money(i.amount_paid) }, { key: "due", header: "Due", render: (i) => day(i.due_date) }, { key: "status", header: "Status", render: (i) => <StatusBadge status={i.status} /> },
          ...(can("accounting.manage") ? [{ key: "actions", header: "Actions", align: "right" as const, render: (i: Invoice) => !["paid", "cancelled"].includes(i.status) && <button className="btn-link" onClick={() => pay(i)}>Record payment</button> }] : [])]} />}

      {supplier && <FormModal title={supplier === "new" ? "Add supplier" : `Edit ${supplier.name}`} fields={supplierFields(supplier === "new" ? undefined : supplier)} onClose={() => setSupplier(null)}
        onSubmit={async (v) => { await api(supplier === "new" ? "/suppliers/" : `/suppliers/${supplier.id}/`, { method: supplier === "new" ? "POST" : "PATCH", body: { ...v, payment_terms_days: Number(v.payment_terms_days || 30) } }); done("Supplier saved."); }} />}
      {dialog === "order" && <FormModal title="New purchase order" submitLabel="Create order" onClose={() => setDialog(null)} fields={[{ name: "supplier", label: "Supplier", type: "select", options: supplierOptions }, branchField, medField, qtyField, { name: "unit_cost", label: "Unit cost", type: "number", min: 0, step: "0.01" }]}
        onSubmit={async (v) => { await api("/procurement/orders/", { method: "POST", body: { branch: Number(v.branch), supplier: Number(v.supplier), items: [{ medicine: Number(v.medicine), quantity: Number(v.quantity), unit_cost: v.unit_cost }] } }); done("Purchase order created."); }} />}
      {dialog === "requisition" && <FormModal title="New requisition" submitLabel="Submit requisition" onClose={() => setDialog(null)} fields={[branchField, medField, qtyField]}
        onSubmit={async (v) => { await api("/procurement/requisitions/", { method: "POST", body: { branch: Number(v.branch), submit: true, items: [{ medicine: Number(v.medicine), quantity: Number(v.quantity) }] } }); done("Requisition submitted."); }} />}
      {dialog === "invoice" && <FormModal title="Record supplier invoice" submitLabel="Record invoice" onClose={() => setDialog(null)} fields={[{ name: "supplier", label: "Supplier", type: "select", options: supplierOptions }, { name: "invoice_number", label: "Invoice number" }, { name: "amount", label: "Invoice amount", type: "number", min: 0.01, step: "0.01" }, { name: "due_date", label: "Due date", type: "date" }]}
        onSubmit={async (v) => { await api("/procurement/invoices/", { method: "POST", body: { ...v, supplier: Number(v.supplier) } }); done("Invoice recorded."); }} />}
    </div>
  );
}
