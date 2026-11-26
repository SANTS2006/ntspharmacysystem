import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, downloadFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useConfirm, usePrompt } from "../../components/ui";

interface Page<T> { results: T[] }
interface Rec { id: number; number: string; kind: string; status: string; started_at: string; size_bytes: number; verified_at: string | null; verification: string; retention_until: string | null; error: string; objects: number }
interface Health { storage: string; restore_enabled: boolean; last_verified_backup: string | null; last_backup_age_hours: number | null; rpo_target_hours: number; rpo_breached: boolean; retention_days: number; encryption_key_configured: boolean; recent_failures: number }
interface Req { id: number; backup: string; backup_id: number; reason: string; status: string; requested_by: string | null; approved_by: string | null; expires_at: string; log: string[]; error: string; confirmation_phrase: string | null }
const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const mb = (n: number) => `${(n / 1024 / 1024).toFixed(2)} MB`;

export default function Backups() {
  const promptFor = usePrompt(); const confirmDialog = useConfirm();
  const { user } = useAuth(); const qc = useQueryClient();
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const [f, setF] = useState({ backup: "", reason: "", password: "" }); const [pw, setPw] = useState<Record<number, string>>({}); const [phrase, setPhrase] = useState<Record<number, string>>({});
  const list = useQuery({ queryKey: ["backups"], queryFn: () => api<Page<Rec>>("/platform/backups/") });
  const health = useQuery({ queryKey: ["backup-health"], queryFn: () => api<Health>("/platform/backups/health/") });
  const restores = useQuery({ queryKey: ["restores"], queryFn: () => api<Req[]>("/platform/restores/"), refetchInterval: 15000 });
  const done = (t: string) => { setMsg({ ok: true, t }); qc.invalidateQueries(); };
  const fail = (e: unknown) => setMsg({ ok: false, t: errText(e) });
  const create = useMutation({ mutationFn: () => api<Rec>("/platform/backups/", { method: "POST" }), onSuccess: (r) => done(`Backup ${r.number} ${r.status}. ${r.verification}`), onError: fail });
  const verify = (id: number) => api(`/platform/backups/${id}/verify/`, { method: "POST" }).then(() => done("Verification finished.")).catch(fail);
  const request = useMutation({ mutationFn: () => api("/platform/restores/", { method: "POST", body: { backup: Number(f.backup), reason: f.reason, password: f.password } }), onSuccess: () => { setF({ ...f, password: "", reason: "" }); done("Restore requested. A different administrator must approve it."); }, onError: fail });
  const decide = (id: number, what: "approve" | "reject") => api(`/platform/restores/${id}/${what}/`, { method: "POST", body: { password: pw[id] ?? "" } }).then(() => { setPw({ ...pw, [id]: "" }); done(what === "approve" ? "Approved." : "Rejected."); }).catch(fail);
  const execute = async (r: Req) => { if (await confirmDialog({ title: "Replace the ENTIRE database?", message: `Backup ${r.backup} will replace all current data. Everyone is signed out and changes made since that backup are removed. A safety backup is taken first.`, confirmLabel: "Restore database", danger: true })) api(`/platform/restores/${r.id}/execute/`, { method: "POST", body: { password: pw[r.id] ?? "", confirmation: phrase[r.id] ?? "" } }).then(() => done("Restore completed. Please sign in again.")).catch(fail); };
  const h = health.data;
  const completed = list.data?.results.filter((r) => r.status === "completed" && r.verification.startsWith("OK")) ?? [];
  return (
    <div className="space-y-4"><h1 className="page-title">Backup & recovery</h1>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`alert ${msg.ok ? "alert-success" : "alert-error"}`}>{msg.t}</p>}
      {h && <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className={`rounded-xl p-4 shadow-sm ${h.rpo_breached ? "bg-red-50" : "bg-white"}`}><p className="text-xs uppercase text-slate-500">Last verified backup</p><p className="font-semibold">{h.last_verified_backup ?? "None yet"}</p><p className="text-sm">{h.last_backup_age_hours != null ? `${h.last_backup_age_hours} h ago` : ""} {h.rpo_breached && <strong className="text-red-700">Older than the {h.rpo_target_hours} h target</strong>}</p></div>
        <div className="card p-4"><p className="text-xs uppercase text-slate-500">Storage</p><p className="font-semibold">{h.storage === "r2" ? "Cloudflare R2" : h.storage}</p><p className="text-sm">Retention {h.retention_days} days</p></div>
        <div className="card p-4"><p className="text-xs uppercase text-slate-500">Encryption key</p><p className={h.encryption_key_configured ? "font-semibold text-green-700" : "font-semibold text-red-700"}>{h.encryption_key_configured ? "Configured" : "NOT configured"}</p></div>
        <div className="card p-4"><p className="text-xs uppercase text-slate-500">Failures (7 days)</p><p className={h.recent_failures ? "font-semibold text-red-700" : "font-semibold"}>{h.recent_failures}</p><p className="text-sm">Restore {h.restore_enabled ? "enabled" : "disabled"}</p></div></section>}
      <button disabled={create.isPending} onClick={() => { setMsg(null); create.mutate(); }} className="rounded px-4 py-2 text-white disabled:opacity-60" style={{ background: "#0f172a" }}>{create.isPending ? "Backing up…" : "Back up now"}</button>
      <div className="table-wrap"><table className="table"><thead><tr><th>Backup</th><th>Type</th><th>Status</th><th>Size</th><th>Verification</th><th>Keep until</th><th /></tr></thead>
        <tbody>{list.data?.results.map((r) => <tr key={r.id}><td>{r.number}<br /><span className="text-xs text-slate-500">{new Date(r.started_at).toLocaleString()}</span></td><td>{r.kind.replace("_", " ")}</td><td className={r.status === "failed" ? "text-red-700" : ""}>{r.status}{r.error && <span title={r.error}> ⚠</span>}</td><td>{mb(r.size_bytes)}</td>
          <td className={r.verification.startsWith("OK") ? "text-green-700" : "text-red-700"}>{r.verification || "—"}</td><td>{r.retention_until ?? ""}</td>
          <td className="space-x-2">{r.status === "completed" && <><button className="btn-link" onClick={() => verify(r.id)}>Verify</button><button className="btn-link" onClick={() => downloadFile(`/platform/backups/${r.id}/download/`, `${r.number}.bak.enc`).catch(fail)}>Download (encrypted)</button></>}</td></tr>)}</tbody></table>
        {list.data?.results.length === 0 && <p className="p-3 text-slate-500">No backups yet.</p>}</div>
      <section className="space-y-3 rounded-xl border border-red-200 bg-white p-4"><h2 className="font-semibold text-red-800">Restore (two administrators required)</h2>
        <p className="text-sm text-slate-600">A restore replaces the whole database with a verified backup. One administrator requests it, a <em>different</em> administrator approves it, and it is executed by typing the confirmation phrase. Both confirm with their password. A safety backup is taken first and all sessions are signed out afterwards.</p>
        <form onSubmit={(e) => { e.preventDefault(); setMsg(null); request.mutate(); }} className="flex flex-wrap items-end gap-2">
          <select required aria-label="Backup to restore" className="px-3 py-2" value={f.backup} onChange={(e) => setF({ ...f, backup: e.target.value })}><option value="">Select a verified backup</option>{completed.map((r) => <option key={r.id} value={r.id}>{r.number}</option>)}</select>
          <input required minLength={10} aria-label="Reason" placeholder="Enter the reason for this restore" className="min-w-64 px-3 py-2" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} />
          <input required type="password" autoComplete="current-password" aria-label="Your password" placeholder="Enter your password" className="px-3 py-2" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <button className="btn btn-outline">Request restore</button></form>
        {restores.data?.map((r) => <article key={r.id} className="rounded border p-3 text-sm"><div className="flex flex-wrap justify-between"><strong>{r.backup}</strong><span>{r.status}</span></div><p>{r.reason} · requested by {r.requested_by}{r.approved_by && ` · approved by ${r.approved_by}`}</p>
          {["pending", "approved"].includes(r.status) && <div className="mt-2 flex flex-wrap items-end gap-2"><input type="password" autoComplete="current-password" aria-label="Your password" placeholder="Enter your password" className="px-3 py-2" value={pw[r.id] ?? ""} onChange={(e) => setPw({ ...pw, [r.id]: e.target.value })} />
            {r.status === "pending" && r.requested_by !== user?.email && <><button className="btn-link" onClick={() => decide(r.id, "approve")}>Approve</button><button className="btn-link" onClick={() => decide(r.id, "reject")}>Reject</button></>}
            {r.status === "approved" && <><input aria-label="Confirmation phrase" placeholder={`Type: ${r.confirmation_phrase}`} className="min-w-72 px-3 py-2" value={phrase[r.id] ?? ""} onChange={(e) => setPhrase({ ...phrase, [r.id]: e.target.value })} /><button className="rounded bg-red-700 px-3 py-2 text-white" onClick={() => execute(r)}>Execute restore</button></>}</div>}
          {r.log.length > 0 && <details className="mt-1"><summary className="cursor-pointer">Recovery log</summary><ul className="text-xs text-slate-600">{r.log.map((l, i) => <li key={i}>{l}</li>)}</ul></details>}{r.error && <p className="text-red-700">{r.error}</p>}</article>)}</section>
    </div>
  );
}
