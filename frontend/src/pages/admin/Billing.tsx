import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../../lib/api";

interface Invoice { id: number; number: string; pharmacy_name: string; amount: string; currency: string; status: string; due_date: string; refunded_amount: string }
interface Plan { id: number; name: string; price: string; currency: string }
interface Page<T> { results: T[]; next: string | null; previous: string | null }
interface Revenue { collected: string; refunded: string; net_revenue: string; outstanding: string }

export default function Billing() {
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
  const pay = (i: Invoice) => {
    const ref = window.prompt("Enter the payment reference"); if (!ref) return;
    const method = window.prompt("Enter the payment method (e.g. mobile_money, bank_transfer, cash)", "mobile_money"); if (!method) return;
    actM.mutate({ id: i.id, action: "pay", body: { payment_reference: ref, payment_method: method } });
  };
  const refund = (i: Invoice) => {
    const amount = window.prompt(`Enter the refund amount (max ${i.amount})`); if (!amount) return;
    const reason = window.prompt("Enter the refund reason") ?? "";
    if (window.confirm(`Refund ${amount} ${i.currency} on ${i.number}? This is recorded permanently.`)) actM.mutate({ id: i.id, action: "refund", body: { amount, reason } });
  };
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Subscription billing</h1>
      {rev.data && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Object.entries({ Collected: rev.data.collected, Refunded: rev.data.refunded, "Net revenue": rev.data.net_revenue, Outstanding: rev.data.outstanding }).map(([k, v]) => (
            <div key={k} className="rounded-xl bg-white p-4 shadow-sm"><p className="text-xs uppercase text-slate-500">{k}</p><p className="text-xl font-semibold">{Number(v).toLocaleString()}</p></div>))}
        </div>)}
      <form onSubmit={(e) => { e.preventDefault(); issueM.mutate(); }} className="flex flex-wrap items-end gap-2 rounded-xl bg-white p-4 shadow-sm">
        <label className="text-sm">Pharmacy<select required className="mt-1 block rounded border p-2" value={issue.pharmacy} onChange={(e) => setIssue({ ...issue, pharmacy: e.target.value })}><option value="">Select a pharmacy</option>{pharmacies.data?.results.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label className="text-sm">Plan<select required className="mt-1 block rounded border p-2" value={issue.plan} onChange={(e) => setIssue({ ...issue, plan: e.target.value })}><option value="">Select a plan</option>{plans.data?.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.currency} {p.price})</option>)}</select></label>
        <button disabled={issueM.isPending} className="rounded bg-teal-700 px-4 py-2 text-white">Issue invoice</button>
        {plans.data?.length === 0 && <span className="text-sm text-amber-700">No plans exist yet. Create one below.</span>}
      </form>
      <form onSubmit={(e) => { e.preventDefault(); planM.mutate(); }} className="flex flex-wrap items-end gap-2 rounded-xl bg-white p-4 shadow-sm">
        <label className="text-sm">Plan name<input required placeholder="Enter the plan name" className="mt-1 block rounded border p-2" value={plan.name} onChange={(e) => setPlan({ ...plan, name: e.target.value })} /></label>
        <label className="text-sm">Code<input required placeholder="Enter the plan code" className="mt-1 block rounded border p-2" value={plan.code} onChange={(e) => setPlan({ ...plan, code: e.target.value })} /></label>
        <label className="text-sm">Price<input required type="number" min="0.01" step="0.01" placeholder="Enter the price" className="mt-1 block w-28 rounded border p-2" value={plan.price} onChange={(e) => setPlan({ ...plan, price: e.target.value })} /></label>
        <label className="text-sm">Max branches<input type="number" min="1" className="mt-1 block w-24 rounded border p-2" value={plan.max_branches} onChange={(e) => setPlan({ ...plan, max_branches: e.target.value })} /></label>
        <label className="text-sm">Max users<input type="number" min="1" className="mt-1 block w-24 rounded border p-2" value={plan.max_users} onChange={(e) => setPlan({ ...plan, max_users: e.target.value })} /></label>
        <button disabled={planM.isPending} className="rounded border px-4 py-2">Create plan</button>
      </form>
      {err && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">{err}</p>}
      <select aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="rounded border p-2">
        <option value="">All</option><option value="issued">Issued</option><option value="paid">Paid</option><option value="refunded">Refunded</option><option value="void">Void</option>
      </select>
      {inv.isLoading && <p>Loading…</p>}
      {inv.data?.results.length === 0 && <p className="text-slate-500">No invoices.</p>}
      {inv.data && inv.data.results.length > 0 && (
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm">
          <thead className="bg-slate-100"><tr><th className="p-3">Number</th><th>Pharmacy</th><th>Amount</th><th>Status</th><th>Due</th><th>Actions</th></tr></thead>
          <tbody>{inv.data.results.map((i) => (
            <tr key={i.id} className="border-t"><td className="p-3">{i.number}</td><td>{i.pharmacy_name}</td><td>{i.currency} {i.amount}{Number(i.refunded_amount) > 0 && ` (−${i.refunded_amount})`}</td><td>{i.status}</td><td>{i.due_date}</td>
              <td className="space-x-2">
                {i.status === "issued" && <><button onClick={() => pay(i)} className="underline">Record payment</button><button onClick={() => window.confirm("Void this invoice?") && actM.mutate({ id: i.id, action: "void" })} className="underline">Void</button></>}
                {i.status === "paid" && <button onClick={() => refund(i)} className="underline">Refund</button>}
              </td></tr>))}</tbody></table></div>)}
      <div className="flex gap-2">
        <button disabled={!inv.data?.previous} onClick={() => setPage((p) => p - 1)} className="rounded border px-3 py-1 disabled:opacity-40">Previous</button>
        <button disabled={!inv.data?.next} onClick={() => setPage((p) => p + 1)} className="rounded border px-3 py-1 disabled:opacity-40">Next</button>
      </div>
    </div>
  );
}
