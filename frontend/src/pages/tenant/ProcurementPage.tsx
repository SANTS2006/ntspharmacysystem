import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { PageHeader, StatusBadge, useConfirm, usePrompt } from "../../components/ui";

interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
interface Supplier { id: number; name: string; contact_person: string; phone: string; email: string; status: string }
interface Med { id: number; name: string; strength: string }
interface Branch { id: number; name: string }
interface OrderItem { id: number; medicine: number; medicine_name: string; quantity_ordered: number; quantity_received: number; unit_cost: string }
interface Order { id: number; number: string; supplier_name: string; branch: number; status: string; total: string; items: OrderItem[]; created_by: number }
interface Req { id: number; number: string; branch: number; status: string; requested_by: number; items: { medicine_name: string; quantity: number }[] }
interface Invoice { id: number; invoice_number: string; supplier_name: string; amount: string; amount_paid: string; balance: string; due_date: string; status: string }

const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const inputCls = "mt-1 w-full px-3 py-2 font-normal";
const brand = { background: "var(--brand)" };
type Tab = "orders" | "requisitions" | "suppliers" | "invoices";

export default function ProcurementPage() {
  const promptFor = usePrompt(); const confirmDialog = useConfirm();
  const { user } = useAuth(); const qc = useQueryClient();
  const can = (p: string) => !!user?.permissions.includes(p);
  const pharmacyLevel = !user?.branch; // invoices/payments are restricted to pharmacy-level staff by the API
  const [tab, setTab] = useState<Tab>("orders"); const [err, setErr] = useState<string | null>(null); const [ok, setOk] = useState<string | null>(null);
  const onError = (e: unknown) => { setOk(null); setErr(errText(e)); };
  const done = (m: string) => { setErr(null); setOk(m); qc.invalidateQueries(); };

  const suppliers = useQuery({ queryKey: ["suppliers"], queryFn: () => api<Page<Supplier>>("/suppliers/") });
  const meds = useQuery({ queryKey: ["medicines-all"], queryFn: () => api<Page<Med>>("/medicines/?status=active&ordering=name") });
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => api<Page<Branch>>("/branches/"), enabled: can("branch.view") });
  const orders = useQuery({ queryKey: ["orders"], queryFn: () => api<Page<Order>>("/procurement/orders/"), enabled: tab === "orders" });
  const reqs = useQuery({ queryKey: ["reqs"], queryFn: () => api<Page<Req>>("/procurement/requisitions/"), enabled: tab === "requisitions" });
  const invoices = useQuery({ queryKey: ["invoices"], queryFn: () => api<Page<Invoice>>("/procurement/invoices/"), enabled: tab === "invoices" && pharmacyLevel });

  const post = useMutation({ mutationFn: ({ path, body }: { path: string; body?: object }) => api(path, { method: "POST", body: body ?? {} }), onSuccess: () => done("Done."), onError });

  // ----- forms (plain state; server validates everything) -----
  const [sup, setSup] = useState({ name: "", contact_person: "", phone: "", email: "" });
  const [po, setPo] = useState({ supplier: "", branch: user?.branch ? String(user.branch) : "", medicine: "", quantity: "", unit_cost: "" });
  const [rq, setRq] = useState({ branch: user?.branch ? String(user.branch) : "", medicine: "", quantity: "" });
  const [inv, setInv] = useState({ supplier: "", invoice_number: "", amount: "", due_date: "" });

  const receive = async (o: Order) => {
    const item = o.items.find((i) => i.quantity_received < i.quantity_ordered);
    if (!item) return;
    const v = await promptFor({ title: `Receive goods · ${item.medicine_name}`, confirmLabel: "Receive stock", fields: [
      { name: "qty", label: `Quantity delivered (outstanding ${item.quantity_ordered - item.quantity_received})`, type: "number", min: 1, step: "1" },
      { name: "batch", label: "Batch number" }, { name: "expiry", label: "Expiry date (YYYY-MM-DD)", placeholder: "YYYY-MM-DD" }] });
    if (!v) return; const { qty, batch, expiry } = v;
    post.mutate({ path: "/procurement/goods-receipts/", body: { order: o.id, lines: [{ order_item: item.id, quantity: Number(qty), batch_number: batch, expiry_date: expiry }] } });
  };
  const decide = async (path: string) => { const v = await promptFor({ title: "Add a note", fields: [{ name: "note", label: "Note (optional)", type: "textarea", required: false }] }); if (v) post.mutate({ path, body: { note: v.note } }); };
  const pay = async (i: Invoice) => {
    const v = await promptFor({ title: `Pay ${i.invoice_number}`, confirmLabel: "Continue", fields: [
      { name: "amount", label: `Payment amount (outstanding ${i.balance})`, type: "number", min: 0.01, step: "0.01" },
      { name: "reference", label: "Payment reference" }, { name: "method", label: "Payment method", defaultValue: "bank_transfer" }] });
    if (!v) return; const { amount, reference, method } = v;
    if (await confirmDialog({ title: "Record this payment?", message: `${amount} for ${i.invoice_number}. This is permanent.`, confirmLabel: "Record payment" })) post.mutate({ path: `/procurement/invoices/${i.id}/pay/`, body: { amount, reference, method } });
  };
  const sel = (v: string, set: (s: string) => void, ph: string, opts: { id: number; name: string }[] | undefined) => (
    <select required className={inputCls} value={v} onChange={(e) => set(e.target.value)} aria-label={ph}><option value="">{ph}</option>{opts?.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>);
  const tabs: Tab[] = pharmacyLevel ? ["orders", "requisitions", "suppliers", "invoices"] : ["orders", "requisitions", "suppliers"];

  return (
    <div className="space-y-4">
      <PageHeader title="Procurement" subtitle="Suppliers, requisitions, purchase orders and goods received." />
      {ok && <p role="status" className="alert alert-success">{ok}</p>}
      {err && <p role="alert" className="alert alert-error">{err}</p>}
      <div role="tablist" className="tablist">{tabs.map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`tab ${tab === t ? "tab-active" : ""}`}>{t[0].toUpperCase() + t.slice(1)}</button>)}</div>

      {tab === "suppliers" && <>
        {can("procurement.manage") && <form onSubmit={(e) => { e.preventDefault(); post.mutate({ path: "/suppliers/", body: sup }); setSup({ name: "", contact_person: "", phone: "", email: "" }); }} className="grid gap-3 card p-4  md:grid-cols-5">
          {(["name", "contact_person", "phone", "email"] as const).map((k) => <label key={k} className="text-sm font-medium">{k.replace("_", " ")}<input required={k === "name"} className={inputCls} placeholder={`Enter the supplier ${k.replace("_", " ")}`} value={sup[k]} onChange={(e) => setSup({ ...sup, [k]: e.target.value })} /></label>)}
          <button className="btn btn-primary self-end">Add supplier</button></form>}
        <div className="table-wrap"><table className="table"><thead><tr><th>Name</th><th>Contact</th><th>Phone</th><th>Email</th></tr></thead>
          <tbody>{suppliers.data?.results.map((s) => <tr key={s.id}><td>{s.name}</td><td>{s.contact_person}</td><td>{s.phone}</td><td>{s.email}</td></tr>)}</tbody></table>{suppliers.data?.results.length === 0 && <p className="p-3 text-slate-500">No suppliers yet.</p>}</div></>}

      {tab === "requisitions" && <>
        {can("procurement.manage") && <form onSubmit={(e) => { e.preventDefault(); post.mutate({ path: "/procurement/requisitions/", body: { branch: Number(rq.branch), submit: true, items: [{ medicine: Number(rq.medicine), quantity: Number(rq.quantity) }] } }); }} className="grid gap-3 card p-4  md:grid-cols-4">
          {sel(rq.branch, (v) => setRq({ ...rq, branch: v }), "Select a branch", branches.data?.results)}{sel(rq.medicine, (v) => setRq({ ...rq, medicine: v }), "Select a medicine", meds.data?.results.map((m) => ({ id: m.id, name: `${m.name} ${m.strength}` })))}
          <input required type="number" min="1" className={inputCls} placeholder="Enter the quantity" value={rq.quantity} onChange={(e) => setRq({ ...rq, quantity: e.target.value })} aria-label="Quantity" />
          <button className="btn btn-primary">Submit requisition</button></form>}
        <div className="table-wrap"><table className="table"><thead><tr><th>Number</th><th>Items</th><th>Status</th><th /></tr></thead>
          <tbody>{reqs.data?.results.map((r) => <tr key={r.id}><td>{r.number}</td><td>{r.items.map((i) => `${i.medicine_name} × ${i.quantity}`).join(", ")}</td><td><StatusBadge status={r.status} /></td>
            <td className="space-x-2">{r.status === "submitted" && can("procurement.approve") && r.requested_by !== user?.id && <><button className="btn-link" onClick={() => decide(`/procurement/requisitions/${r.id}/approve/`)}>Approve</button><button className="btn-link" onClick={() => decide(`/procurement/requisitions/${r.id}/reject/`)}>Reject</button></>}</td></tr>)}</tbody></table>{reqs.data?.results.length === 0 && <p className="p-3 text-slate-500">No requisitions.</p>}</div></>}

      {tab === "orders" && <>
        {can("procurement.manage") && <form onSubmit={(e) => { e.preventDefault(); post.mutate({ path: "/procurement/orders/", body: { branch: Number(po.branch), supplier: Number(po.supplier), items: [{ medicine: Number(po.medicine), quantity: Number(po.quantity), unit_cost: po.unit_cost }] } }); }} className="grid gap-3 card p-4  md:grid-cols-6">
          {sel(po.supplier, (v) => setPo({ ...po, supplier: v }), "Select a supplier", suppliers.data?.results)}{sel(po.branch, (v) => setPo({ ...po, branch: v }), "Select a branch", branches.data?.results)}
          {sel(po.medicine, (v) => setPo({ ...po, medicine: v }), "Select a medicine", meds.data?.results.map((m) => ({ id: m.id, name: `${m.name} ${m.strength}` })))}
          <input required type="number" min="1" className={inputCls} placeholder="Enter the quantity" value={po.quantity} onChange={(e) => setPo({ ...po, quantity: e.target.value })} aria-label="Quantity" />
          <input required type="number" min="0" step="0.01" className={inputCls} placeholder="Enter the unit cost" value={po.unit_cost} onChange={(e) => setPo({ ...po, unit_cost: e.target.value })} aria-label="Unit cost" />
          <button className="btn btn-primary">Create order</button></form>}
        <div className="table-wrap"><table className="table"><thead><tr><th>Number</th><th>Supplier</th><th>Items (received/ordered)</th><th>Total</th><th>Status</th><th /></tr></thead>
          <tbody>{orders.data?.results.map((o) => <tr key={o.id}><td>{o.number}</td><td>{o.supplier_name}</td><td>{o.items.map((i) => `${i.medicine_name} ${i.quantity_received}/${i.quantity_ordered}`).join(", ")}</td><td>{o.total}</td><td><StatusBadge status={o.status} /></td>
            <td className="space-x-2">{o.status === "draft" && can("procurement.manage") && <button className="btn-link" onClick={() => post.mutate({ path: `/procurement/orders/${o.id}/submit/` })}>Submit</button>}
              {o.status === "pending_approval" && can("procurement.approve") && o.created_by !== user?.id && <><button className="btn-link" onClick={() => decide(`/procurement/orders/${o.id}/approve/`)}>Approve</button><button className="btn-link" onClick={() => decide(`/procurement/orders/${o.id}/reject/`)}>Reject</button></>}
              {(o.status === "approved" || o.status === "partially_received") && can("procurement.manage") && <button className="btn-link" onClick={() => receive(o)}>Receive goods</button>}
              {["draft", "pending_approval", "approved"].includes(o.status) && can("procurement.manage") && <button className="btn-link" onClick={async () => { if (await confirmDialog({ title: "Cancel this order?", confirmLabel: "Cancel order", danger: true })) post.mutate({ path: `/procurement/orders/${o.id}/cancel/` }); }}>Cancel</button>}</td></tr>)}</tbody></table>{orders.data?.results.length === 0 && <p className="p-3 text-slate-500">No purchase orders.</p>}</div></>}

      {tab === "invoices" && pharmacyLevel && <>
        {can("procurement.manage") && <form onSubmit={(e) => { e.preventDefault(); post.mutate({ path: "/procurement/invoices/", body: { ...inv, supplier: Number(inv.supplier) } }); }} className="grid gap-3 card p-4  md:grid-cols-5">
          {sel(inv.supplier, (v) => setInv({ ...inv, supplier: v }), "Select a supplier", suppliers.data?.results)}
          <input required className={inputCls} placeholder="Enter the invoice number" value={inv.invoice_number} onChange={(e) => setInv({ ...inv, invoice_number: e.target.value })} aria-label="Invoice number" />
          <input required type="number" min="0.01" step="0.01" className={inputCls} placeholder="Enter the amount" value={inv.amount} onChange={(e) => setInv({ ...inv, amount: e.target.value })} aria-label="Amount" />
          <input required type="date" className={inputCls} value={inv.due_date} onChange={(e) => setInv({ ...inv, due_date: e.target.value })} aria-label="Due date" />
          <button className="btn btn-primary">Record invoice</button></form>}
        <div className="table-wrap"><table className="table"><thead><tr><th>Invoice</th><th>Supplier</th><th>Amount</th><th>Paid</th><th>Due</th><th>Status</th><th /></tr></thead>
          <tbody>{invoices.data?.results.map((i) => <tr key={i.id}><td>{i.invoice_number}</td><td>{i.supplier_name}</td><td>{i.amount}</td><td>{i.amount_paid}</td><td>{i.due_date}</td><td><StatusBadge status={i.status} /></td>
            <td>{can("accounting.manage") && i.status !== "paid" && i.status !== "cancelled" && <button className="btn-link" onClick={() => pay(i)}>Record payment</button>}</td></tr>)}</tbody></table>{invoices.data?.results.length === 0 && <p className="p-3 text-slate-500">No supplier invoices.</p>}</div></>}
    </div>
  );
}
