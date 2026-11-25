import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../../lib/api";
import { useAuth } from "../../lib/auth";

interface Config { enabled: boolean; space_id: string; access_token_set: boolean; webhook_secret_set: boolean; webhook_path: string; webhook_url: string | null }
interface Attempt { id: number; reference: string; order: string; amount: string; currency: string; status: string; created_at: string; needs_refund: boolean }
interface Page<T> { results: T[]; count: number }
interface Report { by_status: Record<string, { count: number; amount: string }>; stale_pending: number; needs_refund: { id: number; reference: string; amount: string; order__reference_number: string }[] }
const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const inputCls = "mt-1 w-full rounded border p-2 font-normal";

export default function PaymentsPage() {
  const { user } = useAuth(); const qc = useQueryClient();
  const can = (p: string) => !!user?.permissions.includes(p);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const cfg = useQuery({ queryKey: ["pay-config"], queryFn: () => api<Config>("/payments/config/"), enabled: can("settings.manage") });
  const attempts = useQuery({ queryKey: ["attempts"], queryFn: () => api<Page<Attempt>>("/payments/attempts/"), enabled: can("order.manage") });
  const report = useQuery({ queryKey: ["pay-report"], queryFn: () => api<Report>("/payments/reconciliation/"), enabled: can("accounting.view") });
  const [f, setF] = useState({ space_id: "", access_token: "", webhook_secret: "", enabled: false });
  const save = useMutation({
    mutationFn: () => api<Config>("/payments/config/", { method: "PUT", body: { ...f, space_id: f.space_id || cfg.data?.space_id || "" } }),
    onSuccess: () => { setF({ ...f, access_token: "", webhook_secret: "" }); setMsg({ ok: true, t: "Saved. Secrets are stored encrypted and cannot be viewed again." }); qc.invalidateQueries({ queryKey: ["pay-config"] }); }, onError: (e) => setMsg({ ok: false, t: errText(e) }),
  });
  const reconcile = useMutation({ mutationFn: () => api<{ checked: number; confirmed: number; failed: number; still_pending: number }>("/payments/reconcile/", { method: "POST", body: {} }), onSuccess: (r) => { setMsg({ ok: true, t: `Checked ${r.checked}: ${r.confirmed} confirmed, ${r.failed} failed, ${r.still_pending} still pending.` }); qc.invalidateQueries(); }, onError: (e) => setMsg({ ok: false, t: errText(e) }) });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Online payments</h1>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`rounded p-3 text-sm ${msg.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>{msg.t}</p>}
      {can("settings.manage") && cfg.data && (
        <form onSubmit={(e) => { e.preventDefault(); setMsg(null); save.mutate(); }} className="grid max-w-2xl gap-3 rounded-xl bg-white p-4 shadow-sm">
          <h2 className="font-semibold">Monime connection</h2>
          <p className="text-sm text-slate-600">Use this pharmacy's own Monime space so payments go to your account. In the Monime dashboard create a webhook pointing to <code>{cfg.data.webhook_url ?? cfg.data.webhook_path}</code> (event: checkout session completed/cancelled/expired) and paste its HMAC secret below.</p>
          <label className="text-sm font-medium">Space id<input className={inputCls} placeholder="Enter your Monime space id" defaultValue={cfg.data.space_id} onChange={(e) => setF({ ...f, space_id: e.target.value })} /></label>
          <label className="text-sm font-medium">Access token {cfg.data.access_token_set && <em className="font-normal text-green-700">(saved)</em>}<input type="password" autoComplete="off" className={inputCls} placeholder="Enter a new access token to replace the saved one" value={f.access_token} onChange={(e) => setF({ ...f, access_token: e.target.value })} /></label>
          <label className="text-sm font-medium">Webhook secret {cfg.data.webhook_secret_set && <em className="font-normal text-green-700">(saved)</em>}<input type="password" autoComplete="off" className={inputCls} placeholder="Enter the webhook HMAC secret" value={f.webhook_secret} onChange={(e) => setF({ ...f, webhook_secret: e.target.value })} /></label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.enabled} onChange={(e) => setF({ ...f, enabled: e.target.checked })} /> Enable online payment at checkout (currently {cfg.data.enabled ? "on" : "off"})</label>
          <button disabled={save.isPending} className="w-40 rounded px-4 py-2 text-white" style={{ background: "var(--brand)" }}>Save</button>
        </form>)}
      {can("accounting.view") && report.data && (
        <section className="rounded-xl bg-white p-4 shadow-sm"><div className="flex items-center justify-between"><h2 className="font-semibold">Reconciliation</h2>{can("accounting.manage") && <button className="rounded border px-3 py-1 text-sm" onClick={() => reconcile.mutate()}>Check pending payments with provider</button>}</div>
          <ul className="mt-2 text-sm">{Object.entries(report.data.by_status).map(([k, v]) => <li key={k}>{k}: {v.count} · {v.amount}</li>)}</ul>
          {report.data.stale_pending > 0 && <p className="text-amber-700">{report.data.stale_pending} payment(s) have been pending for over 30 minutes.</p>}
          {report.data.needs_refund.length > 0 && <div className="mt-2 rounded bg-red-50 p-2 text-sm text-red-800"><strong>Paid but not fulfilled: arrange a refund</strong><ul>{report.data.needs_refund.map((r) => <li key={r.id}>{r.reference} · order {r.order__reference_number} · {r.amount}</li>)}</ul></div>}</section>)}
      {can("order.manage") && <section><h2 className="mb-2 font-semibold">Payment attempts</h2>{attempts.data?.results.length === 0 && <p className="text-slate-500">No online payments yet.</p>}
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Reference</th><th>Order</th><th>Amount</th><th>Status</th><th>Created</th></tr></thead>
          <tbody>{attempts.data?.results.map((a) => <tr key={a.id} className="border-t"><td className="p-3">{a.reference}</td><td>{a.order}</td><td>{a.currency} {a.amount}</td><td>{a.status}{a.needs_refund && " · refund needed"}</td><td>{new Date(a.created_at).toLocaleString()}</td></tr>)}</tbody></table></div></section>}
    </div>
  );
}
