import { PageHeader } from "../../components/ui";
import { ServerTable } from "../../components/ui/ServerTable";
import { dateTime } from "../../lib/format";

interface Row { id: number; created_at: string; action: string; actor_email: string | null; target_type: string; target_id: string }

export default function AuditLog() {
  return (
    <div className="space-y-5">
      <PageHeader title="Audit log" subtitle="A tamper-evident record of important actions." />
      <ServerTable<Row> queryKey={["audit"]} path="/audit-logs/" rowKey={(r) => r.id} search="Enter your action search" empty="No entries."
        columns={[{ key: "time", header: "Time", render: (r) => dateTime(r.created_at) }, { key: "action", header: "Action", render: (r) => <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{r.action}</code> }, { key: "actor", header: "Actor", render: (r) => r.actor_email ?? "system" }, { key: "target", header: "Target", render: (r) => `${r.target_type} ${r.target_id}` }]} />
    </div>
  );
}
