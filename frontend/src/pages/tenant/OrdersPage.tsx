import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { EmptyState, PageHeader, useConfirm, usePrompt } from "../../components/ui";

interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
interface OrderRow { id: number; reference_number: string; status: string; fulfilment: string; total: string; customer_name: string; customer_phone: string; branch_name: string; prescription: string | null; prescription_status: string | null; created_at: string; lines: { name: string; quantity: number }[]; delivery_address: string; payment_method: string }
interface QrRow { id: number; kind: string; customer_name: string; customer_phone: string; note: string; status: string; requires_prescription: boolean; items: { name: string; quantity: number; requires_prescription: boolean }[]; created_at: string }

// UI hints only; the server enforces valid transitions, permissions and payment rules.
const NEXT: Record<string, string[]> = {
  awaiting_payment: ["payment_confirmed", "cancelled"], payment_confirmed: ["processing", "cancelled"], processing: ["preparing"],
  preparing: ["ready_for_pickup", "out_for_delivery"], ready_for_pickup: ["completed"], out_for_delivery: ["delivered"], delivered: ["completed"], refund_requested: ["refunded", "completed"],
  prescription_rejected: ["cancelled"],
};
const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");

export default function OrdersPage() {
  const promptFor = usePrompt(); const confirmDialog = useConfirm();
  const qc = useQueryClient();
  const { user } = useAuth();
  const refund = async (o: OrderRow) => {
    const v = await promptFor({ title: `Refund ${o.reference_number}`, message: "Return the money through your payment account; this records it.", confirmLabel: "Continue", fields: [
      { name: "amount", label: `Refund amount (order total ${o.total})`, type: "number", min: 0.01, step: "0.01" },
      { name: "method", label: "Refund method", defaultValue: "mobile_money" }, { name: "reference", label: "Refund reference" }, { name: "reason", label: "Refund reason", type: "textarea" }] });
    if (!v) return;
    const { amount, method, reference, reason } = v;
    if (await confirmDialog({ title: "Record this refund?", message: `${amount} for ${o.reference_number}.`, confirmLabel: "Record refund", danger: true })) api(`/orders/${o.id}/refund/`, { method: "POST", body: { amount, method, reference, reason } }).then(() => qc.invalidateQueries()).catch((e) => setErr(errText(e)));
  };
  const [tab, setTab] = useState<"orders" | "requests">("orders"); const [status, setStatus] = useState(""); const [err, setErr] = useState<string | null>(null);
  const orders = useQuery({ queryKey: ["staff-orders", status], queryFn: () => api<Page<OrderRow>>(`/orders/${status ? `?status=${status}` : ""}`), refetchInterval: 20000, enabled: tab === "orders" });
  const reqs = useQuery({ queryKey: ["qr-requests"], queryFn: () => api<Page<QrRow>>("/qr-requests/"), refetchInterval: 20000, enabled: tab === "requests" });
  const move = useMutation({ mutationFn: ({ id, to }: { id: number; to: string }) => api(`/orders/${id}/transition/`, { method: "POST", body: { status: to } }), onSuccess: () => { setErr(null); qc.invalidateQueries(); }, onError: (e) => setErr(errText(e)) });
  const reqStatus = useMutation({ mutationFn: ({ id, st }: { id: number; st: string }) => api(`/qr-requests/${id}/status/`, { method: "POST", body: { status: st } }), onSuccess: () => qc.invalidateQueries(), onError: (e) => setErr(errText(e)) });
  return (
    <div className="space-y-4">
      <PageHeader title="Online orders" subtitle="Track and progress customer orders and QR requests." />
      {err && <p role="alert" className="alert alert-error">{err}</p>}
      <div role="tablist" className="tablist">{(["orders", "requests"] as const).map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`tab ${tab === t ? "tab-active" : ""}`}>{t === "orders" ? "Orders" : "QR requests"}</button>)}</div>
      {tab === "orders" && <>
        <select aria-label="Filter by status" className="px-3 py-2" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option>{["awaiting_prescription", "awaiting_payment", "payment_confirmed", "processing", "preparing", "ready_for_pickup", "out_for_delivery", "delivered", "completed", "cancelled", "refund_requested"].map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</select>
        {orders.data?.results.length === 0 && <EmptyState>No orders.</EmptyState>}
        <div className="space-y-2">{orders.data?.results.map((o) => (
          <article key={o.id} className="card p-3 text-sm "><div className="flex flex-wrap justify-between gap-2"><strong>{o.reference_number}</strong><span>{o.status.replace(/_/g, " ")}</span><span>{o.total}</span></div>
            <p>{o.customer_name} · {o.customer_phone} · {o.fulfilment}{o.delivery_address && ` to ${o.delivery_address}`} · {o.branch_name}</p><p className="text-slate-600">{o.lines.map((l) => `${l.name} × ${l.quantity}`).join(", ")}</p>
            {o.prescription && <p>Prescription {o.prescription}: {o.prescription_status} (review it under Prescriptions)</p>}
            <div className="mt-1 space-x-2">{(NEXT[o.status] ?? []).filter((n) => !(n === "ready_for_pickup" && o.fulfilment !== "pickup") && !(n === "out_for_delivery" && o.fulfilment !== "delivery")).map((n) => <button key={n} className="btn-link" onClick={async () => { if (n !== "cancelled" || (await confirmDialog({ title: "Cancel this order?", message: o.reference_number, confirmLabel: "Cancel order", danger: true }))) move.mutate({ id: o.id, to: n }); }}>Mark {n.replace(/_/g, " ")}</button>)}
              {o.status === "refund_requested" && user?.permissions.includes("sales.refund") && <button className="btn-link" onClick={() => refund(o)}>Record refund</button>}
              {["payment_confirmed", "processing", "preparing", "ready_for_pickup", "out_for_delivery", "delivered", "completed", "refund_requested", "refunded"].includes(o.status) && <button className="btn-link" onClick={() => openProtectedFile(`/orders/${o.id}/receipt/pdf/`).catch((e) => setErr(errText(e)))}>Receipt</button>}</div></article>))}</div></>}
      {tab === "requests" && <div className="space-y-2">{reqs.data?.results.length === 0 && <EmptyState>No requests.</EmptyState>}{reqs.data?.results.map((r) => (
        <article key={r.id} className="card p-3 text-sm "><div className="flex justify-between"><strong>{r.customer_name} · {r.customer_phone}</strong><span>{r.kind} · {r.status}</span></div>
          <p>{r.items.map((i) => `${i.name} × ${i.quantity}${i.requires_prescription ? " (Rx)" : ""}`).join(", ") || "Assistance requested"}</p>{r.note && <p className="text-slate-600">“{r.note}”</p>}
          {r.requires_prescription && <p className="text-red-700">Contains prescription medicines: a pharmacist must review a valid prescription.</p>}
          <div className="space-x-2">{["reviewing", "ready", "closed", "cancelled"].filter((s) => s !== r.status).map((s) => <button key={s} className="btn-link" onClick={() => reqStatus.mutate({ id: r.id, st: s })}>{s}</button>)}</div></article>))}</div>}
    </div>
  );
}
