/** Online orders (list and detail page) and QR-menu requests. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, Mail, MapPin, Phone, User } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { EmptyState, Loading, PageHeader, StatusBadge, Tabs, errorMessage, useConfirm, usePrompt, useToast } from "../../components/ui";
import { ServerTable } from "../../components/ui/ServerTable";
import { api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, money, words } from "../../lib/format";

interface OrderRow { id: number; reference_number: string; status: string; fulfilment: string; total: string; subtotal: string; tax_total: string; delivery_fee: string; customer_name: string; customer_phone: string; customer_email: string; branch_name: string; prescription: string | null; prescription_status: string | null; created_at: string; notes: string; delivery_address: string; payment_method: string; lines: { medicine: number; name: string; quantity: number; unit_price: string; line_total: string }[]; history: { status: string; at: string; note: string }[] }
interface QrRow { id: number; kind: string; customer_name: string; customer_phone: string; note: string; status: string; requires_prescription: boolean; items: { name: string; quantity: number; requires_prescription: boolean }[]; created_at: string }

// UI hints only; the server enforces valid transitions, permissions and payment rules.
const NEXT: Record<string, string[]> = {
  awaiting_payment: ["payment_confirmed", "cancelled"], payment_confirmed: ["processing", "cancelled"], processing: ["preparing"],
  preparing: ["ready_for_pickup", "out_for_delivery"], ready_for_pickup: ["completed"], out_for_delivery: ["delivered"], delivered: ["completed"], refund_requested: ["refunded", "completed"],
  prescription_rejected: ["cancelled"],
};
const ALL = ["awaiting_prescription", "awaiting_payment", "payment_confirmed", "processing", "preparing", "ready_for_pickup", "out_for_delivery", "delivered", "completed", "cancelled", "refund_requested", "refunded"];
const RECEIPT = ["payment_confirmed", "processing", "preparing", "ready_for_pickup", "out_for_delivery", "delivered", "completed", "refund_requested", "refunded"];
const nextSteps = (o: OrderRow) => (NEXT[o.status] ?? []).filter((n) => !(n === "ready_for_pickup" && o.fulfilment !== "pickup") && !(n === "out_for_delivery" && o.fulfilment !== "delivery") && n !== "refunded" && !(n === "payment_confirmed" && o.payment_method === "monime"));
const methodName = (m: string) => (m === "monime" ? "Mobile money (online)" : words(m));

export default function OrdersPage() {
  const { slug = "" } = useParams(); const nav = useNavigate(); const toast = useToast(); const qc = useQueryClient();
  const [tab, setTab] = useState<"orders" | "requests">("orders");
  const setRequest = (id: number, status: string) => api(`/qr-requests/${id}/status/`, { method: "POST", body: { status } }).then(() => { qc.invalidateQueries({ queryKey: ["qr-requests"] }); toast("Request updated."); }).catch((e) => toast(errorMessage(e), "error"));
  return (
    <div className="space-y-5">
      <PageHeader title="Online orders" subtitle="Track and progress customer orders and QR requests." />
      <Tabs tabs={[["orders", "Orders"], ["requests", "QR requests"]]} value={tab} onChange={setTab} />
      {tab === "orders" && <ServerTable<OrderRow> queryKey={["staff-orders"]} path="/orders/" rowKey={(o) => o.id} search="Enter your order or customer search" empty="No orders." refetchInterval={30000}
        onRowClick={(o) => nav(`/${slug}/admin/orders/${o.id}`)} filters={[{ name: "status", label: "All statuses", options: ALL.map((s) => [s, words(s)]) }]}
        columns={[{ key: "ref", header: "Order", render: (o) => <><Link className="font-bold text-primary hover:underline" to={`/${slug}/admin/orders/${o.id}`}>{o.reference_number}</Link><span className="block text-xs text-muted">{dateTime(o.created_at)}</span></> },
          { key: "customer", header: "Customer", render: (o) => <><b className="block">{o.customer_name}</b><span className="text-xs text-muted">{o.customer_phone}</span></> },
          { key: "branch", header: "Branch", render: (o) => o.branch_name }, { key: "fulfilment", header: "Fulfilment", render: (o) => <span className="capitalize">{o.fulfilment}</span> },
          { key: "payment", header: "Payment", render: (o) => <span className="capitalize">{methodName(o.payment_method)}</span> }, { key: "status", header: "Status", render: (o) => <StatusBadge status={o.status} /> },
          { key: "total", header: "Total", align: "right", render: (o) => <b>{money(o.total)}</b> }, { key: "actions", header: "Actions", align: "right", render: (o) => <Link className="btn-link" to={`/${slug}/admin/orders/${o.id}`}>View</Link> }]} />}
      {tab === "requests" && <ServerTable<QrRow> queryKey={["qr-requests"]} path="/qr-requests/" rowKey={(r) => r.id} empty="No requests." refetchInterval={30000}
        filters={[{ name: "status", label: "All statuses", options: ["new", "reviewing", "ready", "closed", "cancelled"].map((s) => [s, words(s)]) }]}
        columns={[{ key: "customer", header: "Customer", render: (r) => <><b className="block">{r.customer_name}</b><span className="text-xs text-muted">{r.customer_phone} · {dateTime(r.created_at)}</span></> },
          { key: "items", header: "Request", render: (r) => <>{r.items.map((i) => `${i.name} × ${i.quantity}${i.requires_prescription ? " (Rx)" : ""}`).join(", ") || "Assistance requested"}{r.note && <span className="block text-xs text-muted">“{r.note}”</span>}{r.requires_prescription && <span className="block text-xs font-semibold text-red-700">A pharmacist must review a valid prescription.</span>}</> },
          { key: "kind", header: "Type", render: (r) => <span className="capitalize">{r.kind}</span> }, { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
          { key: "actions", header: "Move to", align: "right", render: (r) => !["closed", "cancelled"].includes(r.status) && <select aria-label={`Change status for ${r.customer_name}`} value="" onChange={(e) => e.target.value && setRequest(r.id, e.target.value)}><option value="">Update status</option>{["reviewing", "ready", "closed", "cancelled"].filter((s) => s !== r.status).map((s) => <option key={s} value={s}>{words(s)}</option>)}</select> }]} />}
    </div>
  );
}

export function OrderDetailPage() {
  const { slug = "", orderId = "" } = useParams(); const prompt = usePrompt(); const confirm = useConfirm(); const toast = useToast(); const qc = useQueryClient(); const { can } = useAuth();
  const q = useQuery({ queryKey: ["staff-orders", "one", orderId], queryFn: () => api<OrderRow>(`/orders/${orderId}/`), retry: false, refetchInterval: 20000 });
  const done = (t: string) => { qc.invalidateQueries({ queryKey: ["staff-orders"] }); toast(t); };
  const move = useMutation({ mutationFn: (to: string) => api(`/orders/${orderId}/transition/`, { method: "POST", body: { status: to } }), onSuccess: () => done("Order updated."), onError: (e) => toast(errorMessage(e), "error") });
  const back = <Link to={`/${slug}/admin/orders`} className="btn btn-outline btn-sm"><ArrowLeft size={15} aria-hidden />All orders</Link>;
  if (q.isLoading) return <Loading rows={5} label="Opening order…" />;
  if (!q.data) return <div className="space-y-4">{back}<EmptyState>{errorMessage(q.error)}</EmptyState></div>;
  const o = q.data;
  const refund = async () => {
    const v = await prompt({ title: `Refund ${o.reference_number}`, message: `Order total ${money(o.total)}. Return the money through your payment account; this records it.`, confirmLabel: "Continue", fields: [
      { name: "amount", label: "Refund amount", type: "number", min: 0.01, step: "0.01" }, { name: "method", label: "Refund method", type: "select", defaultValue: "mobile_money", options: [["mobile_money", "Mobile money"], ["cash", "Cash"], ["bank_transfer", "Bank transfer"]] }, { name: "reference", label: "Refund reference" }, { name: "reason", label: "Refund reason", type: "textarea" }] });
    if (v && await confirm({ title: "Record this refund?", message: `${money(v.amount)} for ${o.reference_number}.`, confirmLabel: "Record refund", danger: true })) api(`/orders/${o.id}/refund/`, { method: "POST", body: v }).then(() => done("Refund recorded.")).catch((e) => toast(errorMessage(e), "error"));
  };
  const steps = nextSteps(o);
  return (
    <div className="space-y-5">
      {back}
      <PageHeader title={`Order ${o.reference_number}`} subtitle={`Placed ${dateTime(o.created_at)} · ${o.branch_name}`} actions={<StatusBadge status={o.status} />} />
      <div className="grid items-start gap-5 xl:grid-cols-[1.7fr_1fr]">
        <div className="space-y-5">
          <div className="table-wrap"><table className="table"><thead><tr><th>Item</th><th className="text-center">Qty</th><th className="text-right">Unit price</th><th className="text-right">Amount</th></tr></thead>
            <tbody>{o.lines.map((l) => <tr key={l.medicine}><td><b>{l.name}</b></td><td className="text-center">{l.quantity}</td><td className="text-right">{money(l.unit_price)}</td><td className="text-right font-bold">{money(l.line_total)}</td></tr>)}</tbody></table></div>
          {o.prescription && <p className="alert alert-info">Prescription {o.prescription}: {words(o.prescription_status)}. Review it under Prescriptions.</p>}
          {o.notes && <p className="alert alert-warning">Customer note: {o.notes}</p>}
          <section className="card p-5"><h2 className="section-title">History</h2><ol className="mt-3 space-y-3 border-l-2 border-line pl-4 text-sm">{[...o.history].reverse().map((h, i) => <li key={i}><b className="capitalize">{words(h.status)}</b> <span className="text-muted">· {dateTime(h.at)}</span>{h.note && <p className="text-muted">{h.note}</p>}</li>)}</ol></section>
        </div>
        <aside className="space-y-4">
          <section className="card p-5 text-sm"><h2 className="section-title">Customer</h2><ul className="mt-3 space-y-2"><li className="flex gap-2"><User size={15} aria-hidden />{o.customer_name}</li><li className="flex gap-2"><Phone size={15} aria-hidden />{o.customer_phone || "No phone"}</li><li className="flex gap-2 break-all"><Mail size={15} aria-hidden />{o.customer_email}</li>{o.delivery_address && <li className="flex gap-2"><MapPin size={15} aria-hidden />{o.delivery_address}</li>}</ul></section>
          <section className="card p-5 text-sm"><h2 className="section-title">Payment</h2><dl className="mt-3 space-y-2">{([["Subtotal", o.subtotal], ["Tax", o.tax_total], ["Delivery fee", o.delivery_fee]] as const).map(([k, v]) => <div key={k} className="flex justify-between"><dt className="text-muted">{k}</dt><dd>{money(v)}</dd></div>)}<div className="flex justify-between border-t border-line pt-2 text-base font-extrabold"><dt>Total</dt><dd>{money(o.total)}</dd></div></dl><p className="mt-3 capitalize"><span className="text-muted">Method: </span>{methodName(o.payment_method)}</p>
            {o.payment_method === "monime" && o.status === "awaiting_payment" && <p className="mt-2 text-xs text-muted">Online payments are confirmed automatically by the payment provider.</p>}</section>
          <section className="card flex flex-col gap-2 p-5"><h2 className="section-title">Actions</h2>
            {steps.map((n) => <button key={n} className={`btn ${n === "cancelled" ? "btn-outline btn-link-danger" : "btn-primary"}`} disabled={move.isPending} onClick={async () => { if (await confirm({ title: n === "cancelled" ? "Cancel this order?" : `Mark as ${words(n)}?`, message: o.reference_number, confirmLabel: n === "cancelled" ? "Cancel order" : "Confirm", danger: n === "cancelled" })) move.mutate(n); }}>{n === "cancelled" ? "Cancel order" : `Mark ${words(n)}`}</button>)}
            {o.status === "refund_requested" && can("sales.refund") && <button className="btn btn-primary" onClick={refund}>Record refund</button>}
            {RECEIPT.includes(o.status) && <button className="btn btn-outline" onClick={() => openProtectedFile(`/orders/${o.id}/receipt/pdf/`).catch((e) => toast(errorMessage(e), "error"))}><Download size={15} aria-hidden />Receipt</button>}
            {!steps.length && !RECEIPT.includes(o.status) && <p className="text-sm text-muted">No actions are available for this order.</p>}
          </section>
        </aside>
      </div>
    </div>
  );
}
