/** Mobile money activity and reconciliation. The provider connection is configured on the server only: nothing is entered here. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock, RefreshCw, Smartphone, Wallet, XCircle } from "lucide-react";
import { DataTable, PageHeader, Spinner, StatCard, StatusBadge, errorMessage, useToast } from "../../components/ui";
import { ServerTable } from "../../components/ui/ServerTable";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, money, words } from "../../lib/format";

interface Status { enabled: boolean; currency: string }
interface Attempt { id: number; reference: string; order: string; amount: string; currency: string; status: string; created_at: string; needs_refund: boolean }
interface Report { by_status: Record<string, { count: number; amount: string }>; stale_pending: number; needs_refund: { id: number; reference: string; amount: string; order__reference_number: string }[]; unapplied_collections: { id: number; reference: string; amount: string; completed_at: string }[] }

export default function PaymentsPage() {
  const { can } = useAuth(); const qc = useQueryClient(); const toast = useToast();
  const status = useQuery({ queryKey: ["momo-status"], queryFn: () => api<Status>("/payments/status/") });
  const report = useQuery({ queryKey: ["pay-report"], queryFn: () => api<Report>("/payments/reconciliation/"), enabled: can("accounting.view") });
  const reconcile = useMutation({
    mutationFn: () => api<{ checked: number; confirmed: number; failed: number; still_pending: number; errors: number }>("/payments/reconcile/", { method: "POST", body: { older_than_minutes: 0 } }),
    onSuccess: (r) => { toast(`Checked ${r.checked}: ${r.confirmed} confirmed, ${r.failed} failed, ${r.still_pending} pending${r.errors ? `, ${r.errors} could not be checked` : ""}.`, r.errors ? "error" : "success"); ["pay-report", "attempts", "staff-orders"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const cur = status.data?.currency;
  const of = (k: string) => report.data?.by_status[k] ?? { count: 0, amount: "0" };
  return (
    <div className="space-y-5">
      <PageHeader title="Online payments" subtitle="Mobile money payments and reconciliation."
        actions={can("accounting.manage") && <button className="btn btn-primary" disabled={reconcile.isPending || !status.data?.enabled} onClick={() => reconcile.mutate()}>{reconcile.isPending ? <Spinner /> : <RefreshCw size={16} aria-hidden />}Check pending payments</button>} />
      {status.data && <p className={`alert ${status.data.enabled ? "alert-success" : "alert-warning"}`}><Smartphone size={18} aria-hidden />{status.data.enabled ? "Mobile money is active: customers can pay online and cashiers can request payments at the till." : "Mobile money is not available yet. Please contact the platform administrator."}</p>}
      {report.data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Completed" value={money(of("completed").amount, cur)} hint={`${of("completed").count} payments`} icon={CheckCircle2} />
            <StatCard label="Pending" value={of("pending").count + of("initiated").count} hint={report.data.stale_pending ? `${report.data.stale_pending} waiting over 30 minutes` : "Nothing overdue"} icon={Clock} tone="warning" />
            <StatCard label="Not completed" value={of("failed").count + of("cancelled").count + of("expired").count} icon={XCircle} tone="danger" />
            <StatCard label="Counter money not yet applied" value={report.data.unapplied_collections.length} icon={Wallet} tone="info" />
          </div>
          {report.data.needs_refund.length > 0 && <section className="space-y-2"><h2 className="section-title flex items-center gap-2 text-red-700"><AlertTriangle size={17} aria-hidden />Paid but not fulfilled: arrange a refund</h2>
            <DataTable rows={report.data.needs_refund} rowKey={(r) => r.id} pageSize={5} columns={[{ key: "reference", header: "Payment", render: (r) => <b>{r.reference}</b> }, { key: "order", header: "Order", render: (r) => r.order__reference_number }, { key: "amount", header: "Amount", align: "right", render: (r) => money(r.amount, cur) }]} /></section>}
          {report.data.unapplied_collections.length > 0 && <section className="space-y-2"><h2 className="section-title">Money received at the till that no sale has used</h2>
            <DataTable rows={report.data.unapplied_collections} rowKey={(r) => r.id} pageSize={5} columns={[{ key: "reference", header: "Reference", render: (r) => <b>{r.reference}</b> }, { key: "when", header: "Received", render: (r) => dateTime(r.completed_at) }, { key: "amount", header: "Amount", align: "right", render: (r) => money(r.amount, cur) }]} /></section>}
        </>)}
      {can("order.manage") && <section className="space-y-3"><h2 className="section-title">Online payment history</h2>
        <ServerTable<Attempt> queryKey={["attempts"]} path="/payments/attempts/" rowKey={(a) => a.id} empty="No online payments yet." refetchInterval={30000}
          filters={[{ name: "status", label: "All statuses", options: ["pending", "completed", "failed", "cancelled", "expired"].map((s) => [s, words(s)]) }]}
          columns={[{ key: "reference", header: "Reference", render: (a) => <b>{a.reference}</b> }, { key: "order", header: "Order", render: (a) => a.order }, { key: "created", header: "Started", render: (a) => dateTime(a.created_at) }, { key: "status", header: "Status", render: (a) => <><StatusBadge status={a.status} />{a.needs_refund && <span className="badge badge-danger ml-1">refund needed</span>}</> }, { key: "amount", header: "Amount", align: "right", render: (a) => <b>{money(a.amount, a.currency)}</b> }]} /></section>}
    </div>
  );
}
