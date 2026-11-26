import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../lib/api";
import { EmptyState, Loading, PageHeader } from "../../components/ui";

interface Row { id: number; created_at: string; action: string; actor_email: string | null; target_type: string; target_id: string }
interface Page { results: Row[]; next: string | null; previous: string | null }

export default function AuditLog() {
  const [q, setQ] = useState(""); const [page, setPage] = useState(1);
  const { data, isLoading, isError } = useQuery({ queryKey: ["audit", q, page], queryFn: () => api<Page>(`/audit-logs/?page=${page}&search=${encodeURIComponent(q)}`) });
  return (
    <div className="space-y-4">
      <PageHeader title="Audit log" subtitle="A tamper-evident record of important actions." />
      <input aria-label="Search audit log" placeholder="Enter an action to search" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} className="w-72 px-3 py-2" />
      {isLoading && <Loading />}{isError && <p role="alert">The audit log could not be loaded.</p>}
      {data?.results.length === 0 && <EmptyState>No entries.</EmptyState>}
      {data && data.results.length > 0 && (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Time</th><th>Action</th><th>Actor</th><th>Target</th></tr></thead>
          <tbody>{data.results.map((r) => <tr key={r.id}><td>{new Date(r.created_at).toLocaleString()}</td><td><code>{r.action}</code></td><td>{r.actor_email ?? "system"}</td><td>{r.target_type} {r.target_id}</td></tr>)}</tbody></table></div>)}
      <div className="flex gap-2">
        <button disabled={!data?.previous} onClick={() => setPage((p) => p - 1)} className="btn btn-outline btn-sm">Previous</button>
        <button disabled={!data?.next} onClick={() => setPage((p) => p + 1)} className="btn btn-outline btn-sm">Next</button>
      </div>
    </div>
  );
}
