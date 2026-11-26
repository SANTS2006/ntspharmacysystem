import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Banknote, Clock, FileText, Plus, RotateCcw, TrendingUp } from "lucide-react";
import { useState } from "react";
import { DataTable, FormModal, PageHeader, StatCard, StatusBadge, Tabs, errorMessage, useConfirm, usePrompt, useToast } from "../../components/ui";
import { ServerTable, type ApiPage } from "../../components/ui/ServerTable";
import { api } from "../../lib/api";
import { day, money } from "../../lib/format";

interface Invoice { id: number; number: string; pharmacy_name: string; amount: string; currency: string; status: string; due_date: string; refunded_amount: string; payment_method: string }
interface Plan { id: number; name: string; code: string; price: string; currency: string; interval: string; max_branches: number; max_users: number; is_active: boolean }
interface Revenue { collected: string; refunded: string; net_revenue: string; outstanding: string }

export default function Billing() {
  const prompt = usePrompt(); const confirm = useConfirm(); const toast = useToast(); const qc = useQueryClient();
  const [tab, setTab] = useState<"invoices" | "plans">("invoices");
  const [dialog, setDialog] = useState<"invoice" | "plan" | null>(null);
  const rev = useQuery({ queryKey: ["revenue"], queryFn: () => api<Revenue>("/platform/billing/revenue/") });
  const plans = useQuery({ queryKey: ["plans-admin"], queryFn: () => api<Plan[]>("/platform/billing/plans/") });
  const pharmacies = useQuery({ queryKey: ["pharmacies", "options"], queryFn: () => api<ApiPage<{ id: number; name: string }>>("/platform/pharmacies/?page_size=200"), enabled: dialog === "invoice" });
  const done = (t: string) => { ["invoices", "revenue", "plans-admin"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); toast(t); };
  const act = (id: number, action: string, body: object, text: string) => api(`/platform/billing/invoices/${id}/${action}/`, { method: "POST", body }).then(() => done(text)).catch((e) => toast(errorMessage(e), "error"));
  const pay = async (i: Invoice) => { const v = await prompt({ title: `Record payment · ${i.number}`, confirmLabel: "Record payment", fields: [{ name: "payment_reference", label: "Payment reference" }, { name: "payment_method", label: "Payment method", type: "select", defaultValue: "mobile_money", options: [["mobile_money", "Mobile money"], ["bank_transfer", "Bank transfer"], ["cash", "Cash"]] }] }); if (v) act(i.id, "pay", v, "Payment recorded."); };
  const refund = async (i: Invoice) => { const v = await prompt({ title: `Refund · ${i.number}`, message: `Maximum ${money(i.amount, i.currency)}`, confirmLabel: "Continue", fields: [{ name: "amount", label: "Refund amount", type: "number", step: "0.01", min: 0.01 }, { name: "reason", label: "Refund reason", type: "textarea", required: false }] }); if (v && await confirm({ title: "Record this refund?", message: `${money(v.amount, i.currency)} on ${i.number}. This is recorded permanently.`, confirmLabel: "Record refund", danger: true })) act(i.id, "refund", v, "Refund recorded."); };
  return (
    <div className="space-y-5">
      <PageHeader title="Subscription billing" subtitle="Plans, invoices and revenue. Pharmacies can pay SLE or USD invoices online with mobile money."
        actions={tab === "invoices" ? <button className="btn btn-primary" onClick={() => setDialog("invoice")} disabled={!plans.data?.length}><Plus size={16} aria-hidden />Issue invoice</button> : <button className="btn btn-primary" onClick={() => setDialog("plan")}><Plus size={16} aria-hidden />Create plan</button>} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><StatCard label="Collected" value={rev.data ? money(rev.data.collected) : "…"} icon={Banknote} /><StatCard label="Refunded" value={rev.data ? money(rev.data.refunded) : "…"} icon={RotateCcw} tone="warning" /><StatCard label="Net revenue" value={rev.data ? money(rev.data.net_revenue) : "…"} icon={TrendingUp} tone="navy" /><StatCard label="Outstanding" value={rev.data ? money(rev.data.outstanding) : "…"} icon={Clock} tone="info" /></div>
      <Tabs tabs={[["invoices", "Invoices"], ["plans", "Plans"]]} value={tab} onChange={setTab} />
      {plans.data?.length === 0 && <p className="alert alert-warning"><FileText size={16} aria-hidden />No plans exist yet. Create a plan before issuing invoices.</p>}
      {tab === "invoices" && <ServerTable<Invoice> queryKey={["invoices"]} path="/platform/billing/invoices/" rowKey={(i) => i.id} search="Enter your invoice or pharmacy search" empty="No invoices."
        filters={[{ name: "status", label: "All statuses", options: [["issued", "Issued"], ["paid", "Paid"], ["refunded", "Refunded"], ["void", "Void"]] }]}
        columns={[{ key: "number", header: "Invoice", render: (i) => <b>{i.number}</b> }, { key: "pharmacy", header: "Pharmacy", render: (i) => i.pharmacy_name }, { key: "amount", header: "Amount", align: "right", render: (i) => <><b>{money(i.amount, i.currency)}</b>{Number(i.refunded_amount) > 0 && <span className="block text-xs text-warning">refunded {money(i.refunded_amount)}</span>}</> }, { key: "due", header: "Due", render: (i) => day(i.due_date) }, { key: "status", header: "Status", render: (i) => <StatusBadge status={i.status} /> }, { key: "method", header: "Paid by", render: (i) => i.payment_method.replace(/_/g, " ") || "—" },
          { key: "actions", header: "Actions", align: "right", render: (i) => <span className="inline-flex gap-1.5">{i.status === "issued" && <><button className="btn-link" onClick={() => pay(i)}>Record payment</button><button className="btn-link btn-link-danger" onClick={async () => { if (await confirm({ title: "Delete this invoice?", message: `${i.number} is voided and can no longer be paid.`, confirmLabel: "Void invoice", danger: true })) act(i.id, "void", {}, "Invoice voided."); }}>Void</button></>}{i.status === "paid" && <button className="btn-link" onClick={() => refund(i)}>Refund</button>}</span> }]} />}
      {tab === "plans" && <DataTable<Plan> rows={plans.data} loading={plans.isLoading} rowKey={(x) => x.id} empty="No plans yet."
        columns={[{ key: "name", header: "Plan", render: (x) => <><b className="block">{x.name}</b><span className="text-xs text-muted">{x.code}</span></> }, { key: "price", header: "Price", align: "right", render: (x) => <b>{money(x.price, x.currency)}</b>, sort: (x) => Number(x.price) }, { key: "interval", header: "Billed", render: (x) => <span className="capitalize">{x.interval}</span> }, { key: "branches", header: "Branches", align: "center", render: (x) => x.max_branches }, { key: "users", header: "Users", align: "center", render: (x) => x.max_users }, { key: "status", header: "Status", render: (x) => <StatusBadge status={x.is_active ? "active" : "inactive"} /> }]} />}
      {dialog === "invoice" && <FormModal title="Issue invoice" submitLabel="Issue invoice" onClose={() => setDialog(null)} fields={[{ name: "pharmacy", label: "Pharmacy", type: "select", wide: true, options: (pharmacies.data?.results ?? []).map((x) => [String(x.id), x.name]) }, { name: "plan", label: "Plan", type: "select", wide: true, options: (plans.data ?? []).filter((x) => x.is_active).map((x) => [String(x.id), `${x.name} (${x.currency} ${x.price})`]) }]}
        onSubmit={async (v) => { await api("/platform/billing/invoices/issue/", { method: "POST", body: v }); done("Invoice issued."); }} />}
      {dialog === "plan" && <FormModal title="Create plan" submitLabel="Create plan" onClose={() => setDialog(null)} fields={[{ name: "name", label: "Plan name" }, { name: "code", label: "Plan code" }, { name: "price", label: "Price", type: "number", min: 0.01, step: "0.01" }, { name: "currency", label: "Currency", type: "select", defaultValue: "SLE", options: [["SLE", "SLE"], ["USD", "USD"]] }, { name: "interval", label: "Billing interval", type: "select", defaultValue: "monthly", options: [["monthly", "Monthly"], ["yearly", "Yearly"]] }, { name: "max_branches", label: "Maximum branches", type: "number", min: 1, step: "1", defaultValue: 1 }, { name: "max_users", label: "Maximum users", type: "number", min: 1, step: "1", defaultValue: 10 }]}
        onSubmit={async (v) => { await api("/platform/billing/plans/", { method: "POST", body: v }); done("Plan created."); }} />}
    </div>
  );
}
