import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";

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
  const qc = useQueryClient();
  const { user } = useAuth();
  const refund = (o: OrderRow) => {
    const amount = window.prompt(`Enter the refund amount (order total ${o.total})`); if (!amount) return;
    const method = window.prompt("Enter the refund method (e.g. mobile_money)", "mobile_money"); if (!method) return;
    const reference = window.prompt("Enter the refund reference"); if (!reference) return;
    const reason = window.prompt("Enter the refund reason"); if (!reason) return;
    if (window.confirm(`Record a refund of ${amount} for ${o.reference_number}? The money must be returned through your payment account; this records it.`)) api(`/orders/${o.id}/refund/`, { method: "POST", body: { amount, method, reference, reason } }).then(() => qc.invalidateQueries()).catch((e) => setErr(errText(e)));
  };
  const [tab, setTab] = useState<"orders" | "requests">("orders"); const [status, setStatus] = useState(""); const [err, setErr] = useState<string | null>(null);
  const orders = useQuery({ queryKey: ["staff-orders", status], queryFn: () => api<Page<OrderRow>>(`/orders/${status ? `?status=${status}` : ""}`), refetchInterval: 20000, enabled: tab === "orders" });
  const reqs = useQuery({ queryKey: ["qr-requests"], queryFn: () => api<Page<QrRow>>("/qr-requests/"), refetchInterval: 20000, enabled: tab === "requests" });
  const move = useMutation({ mutationFn: ({ id, to }: { id: number; to: string }) => api(`/orders/${id}/transition/`, { method: "POST", body: { status: to } }), onSuccess: () => { setErr(null); qc.invalidateQueries(); }, onError: (e) => setErr(errText(e)) });
  const reqStatus = useMutation({ mutationFn: ({ id, st }: { id: number; st: string }) => api(`/qr-requests/${id}/status/`, { method: "POST", body: { status: st } }), onSuccess: () => qc.invalidateQueries(), onError: (e) => setErr(errText(e)) });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Online orders & requests</h1>
      {err && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">{err}</p>}
      <div role="tablist" className="flex gap-2">{(["orders", "requests"] as const).map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`rounded px-3 py-1 text-sm ${tab === t ? "text-white" : "border"}`} style={tab === t ? { background: "var(--brand)" } : undefined}>{t === "orders" ? "Orders" : "QR requests"}</button>)}</div>
      {tab === "orders" && <>
        <select aria-label="Filter by status" className="rounded border p-2" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option>{["awaiting_prescription", "awaiting_payment", "payment_confirmed", "processing", "preparing", "ready_for_pickup", "out_for_delivery", "delivered", "completed", "cancelled", "refund_requested"].map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</select>
        {orders.data?.results.length === 0 && <p className="text-slate-500">No orders.</p>}
        <div className="space-y-2">{orders.data?.results.map((o) => (
          <article key={o.id} className="rounded-xl bg-white p-3 text-sm shadow-sm"><div className="flex flex-wrap justify-between gap-2"><strong>{o.reference_number}</strong><span>{o.status.replace(/_/g, " ")}</span><span>{o.total}</span></div>
            <p>{o.customer_name} · {o.customer_phone} · {o.fulfilment}{o.delivery_address && ` to ${o.delivery_address}`} · {o.branch_name}</p><p className="text-slate-600">{o.lines.map((l) => `${l.name} × ${l.quantity}`).join(", ")}</p>
            {o.prescription && <p>Prescription {o.prescription}: {o.prescription_status} (review it under Prescriptions)</p>}
            <div className="mt-1 space-x-2">{(NEXT[o.status] ?? []).filter((n) => !(n === "ready_for_pickup" && o.fulfilment !== "pickup") && !(n === "out_for_delivery" && o.fulfilment !== "delivery")).map((n) => <button key={n} className="underline" onClick={() => (n !== "cancelled" || window.confirm("Cancel this order?")) && move.mutate({ id: o.id, to: n })}>Mark {n.replace(/_/g, " ")}</button>)}
              {o.status === "refund_requested" && user?.permissions.includes("sales.refund") && <button className="underline" onClick={() => refund(o)}>Record refund</button>}
              {["payment_confirmed", "processing", "preparing", "ready_for_pickup", "out_for_delivery", "delivered", "completed", "refund_requested", "refunded"].includes(o.status) && <button className="underline" onClick={() => openProtectedFile(`/orders/${o.id}/receipt/pdf/`).catch((e) => setErr(errText(e)))}>Receipt</button>}</div></article>))}</div></>}
      {tab === "requests" && <div className="space-y-2">{reqs.data?.results.length === 0 && <p className="text-slate-500">No requests.</p>}{reqs.data?.results.map((r) => (
        <article key={r.id} className="rounded-xl bg-white p-3 text-sm shadow-sm"><div className="flex justify-between"><strong>{r.customer_name} · {r.customer_phone}</strong><span>{r.kind} · {r.status}</span></div>
          <p>{r.items.map((i) => `${i.name} × ${i.quantity}${i.requires_prescription ? " (Rx)" : ""}`).join(", ") || "Assistance requested"}</p>{r.note && <p className="text-slate-600">“{r.note}”</p>}
          {r.requires_prescription && <p className="text-red-700">Contains prescription medicines: a pharmacist must review a valid prescription.</p>}
          <div className="space-x-2">{["reviewing", "ready", "closed", "cancelled"].filter((s) => s !== r.status).map((s) => <button key={s} className="underline" onClick={() => reqStatus.mutate({ id: r.id, st: s })}>{s}</button>)}</div></article>))}</div>}
    </div>
  );
}
