import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../../lib/api";
import { EmptyState, Loading, StatusBadge, useConfirm, usePrompt } from "../../components/ui";

interface Invoice { id: number; number: string; pharmacy_name: string; amount: string; currency: string; status: string; due_date: string; refunded_amount: string }
interface Plan { id: number; name: string; price: string; currency: string }
interface Page<T> { results: T[]; next: string | null; previous: string | null }
interface Revenue { collected: string; refunded: string; net_revenue: string; outstanding: string }

export default function Billing() {
  const promptFor = usePrompt(); const confirmDialog = useConfirm();
  const qc = useQueryClient();
  const [status, setStatus] = useState(""); const [page, setPage] = useState(1);
  const [err, setErr] = useState<string | null>(null);
  const inv = useQuery({ queryKey: ["invoices", status, page], queryFn: () => api<Page<Invoice>>(`/platform/billing/invoices/?page=${page}${status ? `&status=${status}` : ""}`) });
  const rev = useQuery({ queryKey: ["revenue"], queryFn: () => api<Revenue>("/platform/billing/revenue/") });
  const plans = useQuery({ queryKey: ["plans-admin"], queryFn: () => api<Plan[]>("/platform/billing/plans/") });
  const pharmacies = useQuery({ queryKey: ["pharmacies-all"], queryFn: () => api<Page<{ id: number; name: string }>>("/platform/pharmacies/?page=1") });
  const [issue, setIssue] = useState({ pharmacy: "", plan: "" });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["invoices"] }); qc.invalidateQueries({ queryKey: ["revenue"] }); };
  const onError = (e: unknown) => setErr(e instanceof ApiError ? `${e.message} ${JSON.stringify(e.details ?? "")}` : "Action failed.");
  const [plan, setPlan] = useState({ name: "", code: "", price: "", max_branches: "1", max_users: "10" });
  const planM = useMutation({
    mutationFn: () => api("/platform/billing/plans/", { method: "POST", body: { ...plan, currency: "USD", interval: "monthly" } }),
    onSuccess: () => { setErr(null); setPlan({ name: "", code: "", price: "", max_branches: "1", max_users: "10" }); qc.invalidateQueries({ queryKey: ["plans-admin"] }); },
    onError,
  });
  const issueM = useMutation({ mutationFn: () => api("/platform/billing/invoices/issue/", { method: "POST", body: issue }), onSuccess: () => { setErr(null); refresh(); }, onError });
  const actM = useMutation({
    mutationFn: ({ id, action, body }: { id: number; action: string; body?: object }) => api(`/platform/billing/invoices/${id}/${action}/`, { method: "POST", body: body ?? {} }),
    onSuccess: () => { setErr(null); refresh(); }, onError,
  });
  const pay = async (i: Invoice) => {
    const v = await promptFor({ title: `Record payment · ${i.number}`, confirmLabel: "Record payment", fields: [
      { name: "reference", label: "Payment reference" },
      { name: "method", label: "Payment method", type: "select", defaultValue: "mobile_money", options: [["mobile_money", "Mobile money"], ["bank_transfer", "Bank transfer"], ["cash", "Cash"]] }] });
    if (!v) return;
    actM.mutate({ id: i.id, action: "pay", body: { payment_reference: v.reference, payment_method: v.method } });
  };
  const refund = async (i: Invoice) => {
    const v = await promptFor({ title: `Refund · ${i.number}`, confirmLabel: "Continue", fields: [
      { name: "amount", label: `Refund amount (max ${i.amount})`, type: "number", step: "0.01", min: 0.01 }, { name: "reason", label: "Refund reason", type: "textarea", required: false }] });
    if (!v) return;
    const { amount, reason } = v;
    if (await confirmDialog({ title: "Record this refund?", message: `Refund ${amount} ${i.currency} on ${i.number}. This is recorded permanently.`, confirmLabel: "Record refund", danger: true })) actM.mutate({ id: i.id, action: "refund", body: { amount, reason } });
  };
  return (
    <div className="space-y-4">
      <h1 className="page-title">Subscription billing</h1>
      {rev.data && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Object.entries({ Collected: rev.data.collected, Refunded: rev.data.refunded, "Net revenue": rev.data.net_revenue, Outstanding: rev.data.outstanding }).map(([k, v]) => (
            <div key={k} className="card p-4"><p className="text-xs uppercase text-slate-500">{k}</p><p className="text-xl font-semibold">{Number(v).toLocaleString()}</p></div>))}
        </div>)}
      <form onSubmit={(e) => { e.preventDefault(); issueM.mutate(); }} className="flex flex-wrap items-end gap-2 card p-4">
        <label className="text-sm">Pharmacy<select required className="mt-1 block px-3 py-2" value={issue.pharmacy} onChange={(e) => setIssue({ ...issue, pharmacy: e.target.value })}><option value="">Select a pharmacy</option>{pharmacies.data?.results.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label className="text-sm">Plan<select required className="mt-1 block px-3 py-2" value={issue.plan} onChange={(e) => setIssue({ ...issue, plan: e.target.value })}><option value="">Select a plan</option>{plans.data?.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.currency} {p.price})</option>)}</select></label>
        <button disabled={issueM.isPending} className="btn btn-primary">Issue invoice</button>
        {plans.data?.length === 0 && <span className="text-sm text-amber-700">No plans exist yet. Create one below.</span>}
      </form>
      <form onSubmit={(e) => { e.preventDefault(); planM.mutate(); }} className="flex flex-wrap items-end gap-2 card p-4">
        <label className="text-sm">Plan name<input required placeholder="Enter the plan name" className="mt-1 block px-3 py-2" value={plan.name} onChange={(e) => setPlan({ ...plan, name: e.target.value })} /></label>
        <label className="text-sm">Code<input required placeholder="Enter the plan code" className="mt-1 block px-3 py-2" value={plan.code} onChange={(e) => setPlan({ ...plan, code: e.target.value })} /></label>
        <label className="text-sm">Price<input required type="number" min="0.01" step="0.01" placeholder="Enter the price" className="mt-1 block w-28 px-3 py-2" value={plan.price} onChange={(e) => setPlan({ ...plan, price: e.target.value })} /></label>
        <label className="text-sm">Max branches<input type="number" min="1" className="mt-1 block w-24 px-3 py-2" value={plan.max_branches} onChange={(e) => setPlan({ ...plan, max_branches: e.target.value })} /></label>
        <label className="text-sm">Max users<input type="number" min="1" className="mt-1 block w-24 px-3 py-2" value={plan.max_users} onChange={(e) => setPlan({ ...plan, max_users: e.target.value })} /></label>
        <button disabled={planM.isPending} className="btn btn-outline">Create plan</button>
      </form>
      {err && <p role="alert" className="alert alert-error">{err}</p>}
      <select aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="px-3 py-2">
        <option value="">All</option><option value="issued">Issued</option><option value="paid">Paid</option><option value="refunded">Refunded</option><option value="void">Void</option>
      </select>
      {inv.isLoading && <Loading />}
      {inv.data?.results.length === 0 && <EmptyState>No invoices.</EmptyState>}
      {inv.data && inv.data.results.length > 0 && (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Number</th><th>Pharmacy</th><th>Amount</th><th>Status</th><th>Due</th><th>Actions</th></tr></thead>
          <tbody>{inv.data.results.map((i) => (
            <tr key={i.id}><td>{i.number}</td><td>{i.pharmacy_name}</td><td>{i.currency} {i.amount}{Number(i.refunded_amount) > 0 && ` (−${i.refunded_amount})`}</td><td><StatusBadge status={i.status} /></td><td>{i.due_date}</td>
              <td className="space-x-2">
                {i.status === "issued" && <><button onClick={() => pay(i)} className="btn-link">Record payment</button><button onClick={async () => { if (await confirmDialog({ title: "Void this invoice?", message: `${i.number} will no longer be payable.`, confirmLabel: "Void invoice", danger: true })) actM.mutate({ id: i.id, action: "void" }); }} className="btn-link">Void</button></>}
                {i.status === "paid" && <button onClick={() => refund(i)} className="btn-link">Refund</button>}
              </td></tr>))}</tbody></table></div>)}
      <div className="flex gap-2">
        <button disabled={!inv.data?.previous} onClick={() => setPage((p) => p - 1)} className="btn btn-outline btn-sm">Previous</button>
        <button disabled={!inv.data?.next} onClick={() => setPage((p) => p + 1)} className="btn btn-outline btn-sm">Next</button>
      </div>
    </div>
  );
}
