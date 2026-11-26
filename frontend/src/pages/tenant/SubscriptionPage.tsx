/** The pharmacy's own subscription invoices, payable with mobile money. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, CalendarDays, Check, RefreshCw, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { DataTable, ErrorState, Loading, PageHeader, StatCard, StatusBadge, errorMessage, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { day, money } from "../../lib/format";

interface Invoice { id: number; number: string; plan: string | null; amount: string; currency: string; status: string; due_date: string; paid_at: string | null; payment_method: string; payable_online: boolean; checkout_open: boolean }
interface Data { subscription: { plan: string; price: string; currency: string; interval: string; status: string; current_period_end: string | null; features: string[] } | null; invoices: Invoice[] }

export default function SubscriptionPage() {
  const qc = useQueryClient(); const toast = useToast(); const [sp] = useSearchParams(); const [busy, setBusy] = useState<number | null>(null);
  const q = useQuery({ queryKey: ["subscription"], queryFn: () => api<Data>("/subscription/") });
  const check = async (i: Invoice) => { await api(`/subscription/invoices/${i.id}/refresh/`, { method: "POST" }).catch((e) => toast(errorMessage(e), "error")); qc.invalidateQueries({ queryKey: ["subscription"] }); };
  const returned = sp.get("payment") === "return";
  const open = q.data?.invoices.find((i) => i.checkout_open);
  useEffect(() => { // back from checkout: ask the server to verify with the provider
    if (!returned || !open) return;
    check(open);
    const t = window.setInterval(() => check(open), 6000);
    return () => window.clearInterval(t);
  }, [returned, open?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const pay = async (i: Invoice) => {
    setBusy(i.id);
    try { const r = await api<{ paid: boolean; redirect_url: string | null }>(`/subscription/invoices/${i.id}/pay/`, { method: "POST" }); if (r.redirect_url?.startsWith("https://")) window.location.href = r.redirect_url; else qc.invalidateQueries({ queryKey: ["subscription"] }); }
    catch (e) { toast(errorMessage(e), "error"); }
    setBusy(null);
  };
  if (q.isLoading) return <Loading />;
  if (!q.data) return <ErrorState onRetry={() => q.refetch()}>{errorMessage(q.error)}</ErrorState>;
  const s = q.data.subscription;
  const due = q.data.invoices.filter((i) => i.status === "issued");
  return (
    <div className="space-y-5">
      <PageHeader title="Subscription" subtitle="Your plan and invoices." />
      {returned && open && <p className="alert alert-info"><RefreshCw size={16} aria-hidden className="animate-spin" />We are confirming your payment with the provider.</p>}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Plan" value={s?.plan ?? "Not assigned"} icon={BadgeCheck} hint={s ? `${money(s.price, s.currency)} per ${s.interval === "yearly" ? "year" : "month"}` : undefined} />
        <StatCard label="Status" value={<span className="capitalize">{s?.status.replace("_", " ") ?? "—"}</span>} icon={CalendarDays} tone="info" hint={s?.current_period_end ? `Current period ends ${day(s.current_period_end)}` : undefined} />
        <StatCard label="Amount due" value={due.length ? money(due.reduce((t, i) => t + Number(i.amount), 0), due[0].currency) : "Nothing due"} icon={Wallet} tone={due.length ? "warning" : "primary"} />
      </div>
      {!!s?.features.length && <ul className="card flex flex-wrap gap-x-6 gap-y-2 p-5 text-sm">{s.features.map((f) => <li key={f} className="flex items-center gap-2"><Check size={15} aria-hidden className="text-primary" />{f}</li>)}</ul>}
      <DataTable<Invoice> rows={q.data.invoices} rowKey={(i) => i.id} search={(i) => `${i.number} ${i.status}`} empty="No invoices yet."
        columns={[{ key: "number", header: "Invoice", render: (i) => <b>{i.number}</b> }, { key: "plan", header: "Plan", render: (i) => i.plan ?? "—" }, { key: "due", header: "Due", render: (i) => day(i.due_date) }, { key: "status", header: "Status", render: (i) => <StatusBadge status={i.status} /> }, { key: "paid", header: "Paid on", render: (i) => day(i.paid_at) }, { key: "amount", header: "Amount", align: "right", render: (i) => <b>{money(i.amount, i.currency)}</b> },
          { key: "actions", header: "Actions", align: "right", render: (i) => i.status === "issued" && <span className="inline-flex gap-1.5">{i.payable_online ? <button className="btn btn-primary btn-sm" disabled={busy === i.id} onClick={() => pay(i)}><Wallet size={14} aria-hidden />{busy === i.id ? "Opening…" : "Pay with mobile money"}</button> : <span className="text-xs text-muted">Pay the platform team directly</span>}{i.checkout_open && <button className="btn-link" onClick={() => check(i)}>Check status</button>}</span> }]} />
    </div>
  );
}
