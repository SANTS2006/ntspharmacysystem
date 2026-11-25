import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../lib/api";

interface Row { id: number; created_at: string; action: string; actor_email: string | null; target_type: string; target_id: string }
interface Page { results: Row[]; next: string | null; previous: string | null }

export default function AuditLog() {
  const [q, setQ] = useState(""); const [page, setPage] = useState(1);
  const { data, isLoading, isError } = useQuery({ queryKey: ["audit", q, page], queryFn: () => api<Page>(`/audit-logs/?page=${page}&search=${encodeURIComponent(q)}`) });
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Audit log</h1>
      <input aria-label="Search audit log" placeholder="Enter an action to search" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} className="w-72 rounded border p-2" />
      {isLoading && <p>Loading…</p>}{isError && <p role="alert">The audit log could not be loaded.</p>}
      {data?.results.length === 0 && <p className="text-slate-500">No entries.</p>}
      {data && data.results.length > 0 && (
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm">
          <thead className="bg-slate-100"><tr><th className="p-3">Time</th><th>Action</th><th>Actor</th><th>Target</th></tr></thead>
          <tbody>{data.results.map((r) => <tr key={r.id} className="border-t"><td className="p-3">{new Date(r.created_at).toLocaleString()}</td><td><code>{r.action}</code></td><td>{r.actor_email ?? "system"}</td><td>{r.target_type} {r.target_id}</td></tr>)}</tbody></table></div>)}
      <div className="flex gap-2">
        <button disabled={!data?.previous} onClick={() => setPage((p) => p - 1)} className="rounded border px-3 py-1 disabled:opacity-40">Previous</button>
        <button disabled={!data?.next} onClick={() => setPage((p) => p + 1)} className="rounded border px-3 py-1 disabled:opacity-40">Next</button>
      </div>
    </div>
  );
}
