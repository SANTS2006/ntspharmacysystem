/** Human resources, payroll and each staff member's own "My work" page. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarPlus, Download, LogIn, LogOut, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { DataTable, FormModal, Loading, PageHeader, StatCard, StatusBadge, Tabs, errorMessage, useConfirm, usePrompt, useToast, type FieldDef } from "../../components/ui";
import { ServerTable, type ApiPage } from "../../components/ui/ServerTable";
import { api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { day, money, words } from "../../lib/format";

interface Profile { user: number; full_name: string; staff_id: string; role: string | null; employment_status: string; job_title: string; employment_date: string }
interface Att { id: number; name: string; date: string; status: string; clock_in: string | null; clock_out: string | null; source: string }
interface Leave { id: number; name: string; leave_type: string; start_date: string; end_date: string; days: number; status: string; reason: string }
interface Balance { leave_type: number; name: string; allowance: number; used: number; pending: number; remaining: number | null }
interface Run { id: number; period: string; status: string; staff: number; gross: string; net: string; tax: string; paid: string; created_by: number; lines?: Line[] }
interface Line { id: number; user: number; name: string; gross: string; tax: string; net: string; paid_amount: string; warnings: string[] }
interface Structure { id: number; user: number; basic_salary: string; effective_from: string; items: { component: string; value: string }[] }
const thisMonth = () => new Date().toISOString().slice(0, 7);
const time = (v: string | null) => (v ? new Date(v).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "—");

function useActions() {
  const qc = useQueryClient(); const toast = useToast();
  const refresh = () => qc.invalidateQueries({ predicate: (q) => /^(hr-|pr-|my-)/.test(String(q.queryKey[0])) });
  const done = (t: string) => { refresh(); toast(t); };
  const fail = (e: unknown) => toast(errorMessage(e), "error");
  return { done, fail, post: (path: string, body: object, text: string) => api(path, { method: "POST", body }).then(() => done(text)).catch(fail) };
}

/** Staff list for drop-downs, so nobody has to type a numeric user id. */
function useStaffOptions(enabled: boolean) {
  const q = useQuery({ queryKey: ["hr-user-options"], queryFn: () => api<ApiPage<{ id: number; full_name: string; email: string }>>("/staff/?page_size=200"), enabled });
  return useMemo(() => (q.data?.results ?? []).map((u) => [String(u.id), `${u.full_name} (${u.email})`] as [string, string]), [q.data]);
}

export function HrPage() {
  const prompt = usePrompt(); const { can } = useAuth(); const { done, fail, post } = useActions();
  const manage = can("hr.manage");
  const [tab, setTab] = useState<"staff" | "attendance" | "leave">("staff");
  const [dialog, setDialog] = useState<"record" | "attendance" | null>(null);
  const people = useStaffOptions(dialog !== null && can("staff.view"));
  const decide = async (l: Leave, what: "approve" | "reject") => { const v = await prompt({ title: what === "approve" ? "Approve leave" : "Reject leave", message: `${l.name}: ${l.leave_type}, ${l.days} days`, confirmLabel: what === "approve" ? "Approve" : "Reject", danger: what === "reject", fields: [{ name: "note", label: "Note", type: "textarea", required: false }] }); if (v) post(`/hr/leave/${l.id}/${what}/`, { note: v.note }, `Leave ${what === "approve" ? "approved" : "rejected"}.`); };
  const terminate = async (p: Profile) => { const v = await prompt({ title: `End ${p.full_name}'s employment`, message: "Their access is removed immediately.", confirmLabel: "End employment", danger: true, fields: [{ name: "reason", label: "Reason", type: "textarea" }] }); if (v?.reason) post(`/hr/staff/${p.user}/terminate/`, { reason: v.reason }, "Employment ended."); };
  return (
    <div className="space-y-5">
      <PageHeader title="Human resources" subtitle="Staff records, attendance and leave." actions={manage && (tab === "staff" ? <button className="btn btn-primary" onClick={() => setDialog("record")}><Plus size={16} aria-hidden />Add HR record</button> : tab === "attendance" ? <button className="btn btn-primary" onClick={() => setDialog("attendance")}><CalendarPlus size={16} aria-hidden />Record attendance</button> : null)} />
      <Tabs tabs={[["staff", "Staff records"], ["attendance", "Attendance"], ["leave", "Leave requests"]]} value={tab} onChange={setTab} />
      {tab === "staff" && <ServerTable<Profile> queryKey={["hr-staff"]} path="/hr/staff/" rowKey={(p) => p.user} empty="No HR records yet."
        columns={[{ key: "id", header: "Staff ID", render: (p) => p.staff_id }, { key: "name", header: "Name", render: (p) => <b>{p.full_name}</b> }, { key: "role", header: "Role", render: (p) => <span className="capitalize">{words(p.role)}</span> }, { key: "title", header: "Job title", render: (p) => p.job_title || "—" }, { key: "since", header: "Since", render: (p) => day(p.employment_date) }, { key: "status", header: "Status", render: (p) => <StatusBadge status={p.employment_status} /> },
          ...(can("hr.sensitive") ? [{ key: "actions", header: "Actions", align: "right" as const, render: (p: Profile) => p.employment_status !== "terminated" && <button className="btn-link btn-link-danger" onClick={() => terminate(p)}>End employment</button> }] : [])]} />}
      {tab === "attendance" && <ServerTable<Att> queryKey={["hr-att"]} path="/hr/attendance/" rowKey={(a) => a.id} empty="No attendance recorded."
        columns={[{ key: "date", header: "Date", render: (a) => day(a.date) }, { key: "name", header: "Name", render: (a) => <b>{a.name}</b> }, { key: "status", header: "Status", render: (a) => <StatusBadge status={a.status} /> }, { key: "in", header: "Clock in", render: (a) => time(a.clock_in) }, { key: "out", header: "Clock out", render: (a) => time(a.clock_out) }, { key: "source", header: "Source", render: (a) => <span className="capitalize">{a.source}</span> }]} />}
      {tab === "leave" && <ServerTable<Leave> queryKey={["hr-leave"]} path="/hr/leave/?status=pending" rowKey={(l) => l.id} empty="No pending leave requests."
        columns={[{ key: "name", header: "Staff member", render: (l) => <b>{l.name}</b> }, { key: "type", header: "Leave type", render: (l) => l.leave_type }, { key: "dates", header: "Dates", render: (l) => `${day(l.start_date)} – ${day(l.end_date)}` }, { key: "days", header: "Days", align: "center", render: (l) => l.days }, { key: "reason", header: "Reason", render: (l) => l.reason || "—" },
          ...(manage ? [{ key: "actions", header: "Actions", align: "right" as const, render: (l: Leave) => <span className="inline-flex gap-1.5"><button className="btn-link" onClick={() => decide(l, "approve")}>Approve</button><button className="btn-link btn-link-danger" onClick={() => decide(l, "reject")}>Reject</button></span> }] : [])]} />}
      {dialog === "record" && <FormModal title="Add HR record" onClose={() => setDialog(null)} fields={[{ name: "user", label: "Staff member", type: "select", wide: true, options: people }, { name: "employment_date", label: "Employment date", type: "date" }, { name: "job_title", label: "Job title", required: false }]}
        onSubmit={async (v) => { await api("/hr/staff/", { method: "POST", body: { ...v, user: Number(v.user) } }).catch((e) => { fail(e); throw e; }); done("HR record created."); }} />}
      {dialog === "attendance" && <FormModal title="Record or correct attendance" onClose={() => setDialog(null)} fields={[{ name: "user", label: "Staff member", type: "select", wide: true, options: people }, { name: "date", label: "Date", type: "date" }, { name: "status", label: "Status", type: "select", defaultValue: "present", options: [["present", "Present"], ["late", "Late"], ["absent", "Absent"], ["on_leave", "On leave"]] }]}
        onSubmit={async (v) => { await api("/hr/attendance/manual/", { method: "POST", body: { user: Number(v.user), date: v.date, status: v.status } }); done("Attendance recorded."); }} />}
    </div>
  );
}

export function PayrollPage() {
  const prompt = usePrompt(); const confirm = useConfirm(); const { user, can } = useAuth(); const { done, fail, post } = useActions();
  const manage = can("payroll.manage"), approve = can("payroll.approve");
  const [tab, setTab] = useState<"runs" | "structures" | "setup">("runs");
  const [open, setOpen] = useState<number | null>(null);
  const [dialog, setDialog] = useState<"run" | "adjust" | "salary" | "advance" | "rates" | null>(null);
  const detail = useQuery({ queryKey: ["pr-run", open], queryFn: () => api<Run>(`/payroll/runs/${open}/`), enabled: open !== null });
  const structures = useQuery({ queryKey: ["pr-struct"], queryFn: () => api<Structure[]>("/payroll/structures/"), enabled: tab === "structures" });
  const cfg = useQuery({ queryKey: ["pr-config"], queryFn: () => api<{ pension_employee_pct: string; pension_employer_pct: string; tax_brackets: { up_to: string | null; rate: string }[] }>("/payroll/config/"), enabled: tab === "setup" });
  const people = useStaffOptions(can("staff.view"));
  const nameOf = (id: number) => people.find(([v]) => v === String(id))?.[1] ?? `Staff #${id}`;
  const person: FieldDef = { name: "user", label: "Staff member", type: "select", wide: true, options: people };
  const pay = async (l: Line) => {
    const v = await prompt({ title: `Pay ${l.name}`, message: `Outstanding: ${money(Number(l.net) - Number(l.paid_amount))}. Record a payment you have made.`, confirmLabel: "Continue", fields: [{ name: "amount", label: "Amount paid", type: "number", min: 0.01, step: "0.01", defaultValue: (Number(l.net) - Number(l.paid_amount)).toFixed(2) }, { name: "method", label: "Payment method", type: "select", defaultValue: "bank_transfer", options: [["cash", "Cash"], ["bank_transfer", "Bank transfer"], ["mobile_money", "Mobile money"]] }, { name: "reference", label: "Payment reference" }] });
    if (v && await confirm({ title: "Record this salary payment?", message: `${money(v.amount)} to ${l.name}. This is permanent.`, confirmLabel: "Record payment" })) post(`/payroll/lines/${l.id}/pay/`, v, "Payment recorded.");
  };
  const runColumns = [
    { key: "period", header: "Period", render: (r: Run) => <b>{r.period}</b> }, { key: "staff", header: "Staff", align: "center" as const, render: (r: Run) => r.staff }, { key: "gross", header: "Gross", align: "right" as const, render: (r: Run) => money(r.gross) }, { key: "tax", header: "Tax", align: "right" as const, render: (r: Run) => money(r.tax) }, { key: "net", header: "Net", align: "right" as const, render: (r: Run) => <b>{money(r.net)}</b> }, { key: "paid", header: "Paid", align: "right" as const, render: (r: Run) => money(r.paid) }, { key: "status", header: "Status", render: (r: Run) => <StatusBadge status={r.status} /> },
    { key: "actions", header: "Actions", align: "right" as const, render: (r: Run) => <span className="inline-flex flex-wrap justify-end gap-1.5"><button className="btn-link" onClick={() => setOpen(r.id)}>Open</button>
      {r.status === "draft" && manage && <><button className="btn-link" onClick={() => post(`/payroll/runs/${r.id}/recalculate/`, {}, "Recalculated.")}>Recalculate</button><button className="btn-link" onClick={() => post(`/payroll/runs/${r.id}/submit/`, {}, "Submitted for approval.")}>Submit</button></>}
      {r.status === "submitted" && approve && r.created_by !== user?.id && <button className="btn-link" onClick={async () => { if (await confirm({ title: "Approve this payroll?", message: "It is posted to the books and cannot be edited.", confirmLabel: "Approve payroll" })) post(`/payroll/runs/${r.id}/approve/`, {}, "Approved and posted."); }}>Approve</button>}
      {["draft", "submitted"].includes(r.status) && manage && <button className="btn-link btn-link-danger" onClick={async () => { if (await confirm({ title: "Cancel this payroll run?", message: r.period, confirmLabel: "Cancel run", danger: true })) post(`/payroll/runs/${r.id}/cancel/`, {}, "Run cancelled."); }}>Cancel</button>}</span> },
  ];
  if (open !== null) {
    const d = detail.data;
    return (
      <div className="space-y-5">
        <button className="btn btn-outline btn-sm" onClick={() => setOpen(null)}><ArrowLeft size={15} aria-hidden />All payroll runs</button>
        {!d?.lines ? <Loading /> : <>
          <PageHeader title={`Payroll ${d.period}`} subtitle="Confidential. Access is logged." actions={<StatusBadge status={d.status} />} />
          <div className="grid gap-4 sm:grid-cols-3">{(["gross", "tax", "net"] as const).map((k) => <StatCard key={k} label={`Total ${k}`} value={money(d.lines!.reduce((t, l) => t + Number(l[k]), 0))} />)}</div>
          <DataTable<Line> rows={d.lines} rowKey={(l) => l.id} search={(l) => l.name} pageSize={15}
            columns={[{ key: "name", header: "Staff member", render: (l) => <><b>{l.name}</b>{l.warnings.length > 0 && <span className="block text-xs text-warning">{l.warnings.join(" ")}</span>}</> }, { key: "gross", header: "Gross", align: "right", render: (l) => money(l.gross) }, { key: "tax", header: "Tax", align: "right", render: (l) => money(l.tax) }, { key: "net", header: "Net", align: "right", render: (l) => <b>{money(l.net)}</b> }, { key: "paid", header: "Paid", align: "right", render: (l) => money(l.paid_amount) },
              { key: "actions", header: "Actions", align: "right", render: (l) => <span className="inline-flex gap-1.5">{["approved", "paid"].includes(d.status) && <button className="btn-link" onClick={() => openProtectedFile(`/payroll/lines/${l.id}/payslip/pdf/`).catch(fail)}><Download size={13} aria-hidden />Payslip</button>}{d.status === "approved" && manage && Number(l.paid_amount) < Number(l.net) && <button className="btn-link" onClick={() => pay(l)}>Pay</button>}</span> }]} />
        </>}
      </div>
    );
  }
  return (
    <div className="space-y-5">
      <PageHeader title="Payroll" subtitle="Salary structures, payroll runs and payslips. Confidential: access is logged."
        actions={<>{tab === "runs" && manage && !user?.branch && <><button className="btn btn-outline" onClick={() => setDialog("adjust")}>Add adjustment</button><button className="btn btn-primary" onClick={() => setDialog("run")}><Plus size={16} aria-hidden />New payroll run</button></>}{tab === "structures" && manage && <button className="btn btn-primary" onClick={() => setDialog("salary")}><Plus size={16} aria-hidden />Set salary</button>}{tab === "setup" && <>{approve && <button className="btn btn-outline" onClick={() => setDialog("advance")}>Grant salary advance</button>}{manage && <button className="btn btn-primary" onClick={() => setDialog("rates")}>Edit rates</button>}</>}</>} />
      <Tabs tabs={[["runs", "Payroll runs"], ["structures", "Salary structures"], ["setup", "Rates & advances"]]} value={tab} onChange={setTab} />
      {tab === "runs" && <ServerTable<Run> queryKey={["pr-runs"]} path="/payroll/runs/" rowKey={(r) => r.id} columns={runColumns} empty="No payroll runs." />}
      {tab === "structures" && <DataTable<Structure> rows={structures.data} loading={structures.isLoading} rowKey={(s) => s.id} search={(s) => nameOf(s.user)} empty="No salaries set up yet."
        columns={[{ key: "user", header: "Staff member", render: (s) => <b>{nameOf(s.user)}</b> }, { key: "basic", header: "Basic salary", align: "right", render: (s) => money(s.basic_salary), sort: (s) => Number(s.basic_salary) }, { key: "from", header: "Effective from", render: (s) => day(s.effective_from) }, { key: "items", header: "Components", render: (s) => s.items.map((i) => `${i.component} ${i.value}`).join(", ") || "—" }]} />}
      {tab === "setup" && <section className="card p-6 text-sm">{cfg.isLoading ? <Loading rows={2} /> : <><div className="grid gap-4 sm:grid-cols-3"><StatCard label="Employee pension" value={`${cfg.data?.pension_employee_pct ?? 0}%`} /><StatCard label="Employer pension" value={`${cfg.data?.pension_employer_pct ?? 0}%`} /><StatCard label="Tax brackets" value={cfg.data?.tax_brackets.length ?? 0} /></div><p className="mt-4">{cfg.data?.tax_brackets.map((b) => `${b.up_to ? `up to ${b.up_to}` : "above"} → ${b.rate}%`).join(" · ") || "No tax brackets set."}</p><p className="mt-2 text-muted">Enter the rates that apply in your jurisdiction; nothing statutory is built in.</p></>}</section>}
      {dialog === "run" && <FormModal title="New payroll run" submitLabel="Create run" fields={[{ name: "period", label: "Month", type: "month", defaultValue: thisMonth() }]} onClose={() => setDialog(null)} onSubmit={async (v) => { await api("/payroll/runs/", { method: "POST", body: v }); done("Payroll run created."); }} />}
      {dialog === "adjust" && <FormModal title="Add a payroll adjustment" submitLabel="Add adjustment" onClose={() => setDialog(null)} fields={[person, { name: "period", label: "Month", type: "month", defaultValue: thisMonth() }, { name: "kind", label: "Adjustment type", type: "select", defaultValue: "bonus", options: [["bonus", "Bonus"], ["commission", "Commission"], ["overtime", "Overtime"], ["deduction", "Deduction"]] }, { name: "amount", label: "Amount", type: "number", min: 0.01, step: "0.01" }, { name: "note", label: "Note" }]} onSubmit={async (v) => { await api("/payroll/adjustments/", { method: "POST", body: { ...v, user: Number(v.user) } }); done("Adjustment added."); }} />}
      {dialog === "salary" && <FormModal title="New salary version" submitLabel="Save salary" onClose={() => setDialog(null)} fields={[person, { name: "basic_salary", label: "Basic monthly salary", type: "number", min: 0, step: "0.01" }, { name: "effective_from", label: "Effective date", type: "date" }]} onSubmit={async (v) => { await api("/payroll/structures/", { method: "POST", body: { ...v, user: Number(v.user), items: [] } }); done("Salary saved."); }} />}
      {dialog === "advance" && <FormModal title="Grant a salary advance" submitLabel="Record advance" onClose={() => setDialog(null)} fields={[person, { name: "amount", label: "Advance amount", type: "number", min: 0.01, step: "0.01" }, { name: "monthly_recovery", label: "Monthly recovery amount", type: "number", min: 0.01, step: "0.01" }, { name: "reference", label: "Payment reference" }]} onSubmit={async (v) => { await api("/payroll/advances/", { method: "POST", body: { ...v, user: Number(v.user), method: "cash" } }); done("Advance recorded."); }} />}
      {dialog === "rates" && <FormModal title="Payroll rates" onClose={() => setDialog(null)} fields={[{ name: "e", label: "Employee pension percentage", type: "number", min: 0, step: "0.01", defaultValue: cfg.data?.pension_employee_pct ?? "0" }, { name: "r", label: "Employer pension percentage", type: "number", min: 0, step: "0.01", defaultValue: cfg.data?.pension_employer_pct ?? "0" }, { name: "b", label: "Tax brackets", type: "textarea", defaultValue: JSON.stringify(cfg.data?.tax_brackets ?? []), hint: 'JSON, for example [{"up_to":"500","rate":"0"},{"up_to":null,"rate":"15"}]' }]}
        onSubmit={async (v) => { let tax_brackets: unknown; try { tax_brackets = JSON.parse(v.b); } catch { throw new Error("The tax brackets are not valid JSON."); } await api("/payroll/config/", { method: "PUT", body: { pension_employee_pct: v.e, pension_employer_pct: v.r, tax_brackets } }); done("Rates saved."); }} />}
    </div>
  );
}

export function MyWorkPage() {
  const confirm = useConfirm(); const { done, fail, post } = useActions();
  const [asking, setAsking] = useState(false);
  const me = useQuery({ queryKey: ["my-hr"], queryFn: () => api<{ staff_id?: string; job_title?: string; employment_date?: string; note?: string }>("/hr/me/") });
  const att = useQuery({ queryKey: ["my-att"], queryFn: () => api<ApiPage<Att>>("/hr/me/attendance/") });
  const leave = useQuery({ queryKey: ["my-leave"], queryFn: () => api<{ balances: Balance[]; requests: Leave[] }>("/hr/me/leave/") });
  const slips = useQuery({ queryKey: ["my-slips"], queryFn: () => api<{ id: number; period: string; net: string; status: string }[]>("/hr/me/payslips/") });
  const shifts = useQuery({ queryKey: ["my-shifts"], queryFn: () => api<ApiPage<{ id: number; date: string; start_time: string; end_time: string }>>("/hr/me/shifts/") });
  return (
    <div className="space-y-6">
      <PageHeader title="My work" subtitle={me.data?.staff_id ? `Staff ID ${me.data.staff_id} · ${me.data.job_title ?? ""} · since ${day(me.data.employment_date)}` : me.data?.note ?? "Your shifts, attendance, leave and payslips."}
        actions={<><button className="btn btn-primary" onClick={() => post("/hr/attendance/clock-in/", {}, "Clocked in.")}><LogIn size={16} aria-hidden />Clock in</button><button className="btn btn-outline" onClick={() => post("/hr/attendance/clock-out/", {}, "Clocked out.")}><LogOut size={16} aria-hidden />Clock out</button><button className="btn btn-outline" onClick={() => setAsking(true)}><CalendarPlus size={16} aria-hidden />Request leave</button></>} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{leave.data?.balances.map((b) => <StatCard key={b.leave_type} label={`${b.name} leave`} value={b.remaining ?? b.used} hint={b.remaining !== null ? `days left · ${b.used} used${b.pending ? ` · ${b.pending} pending` : ""}` : "days used"} />)}</div>
      <div className="grid items-start gap-5 xl:grid-cols-2">
        <section className="space-y-2"><h2 className="section-title">My leave requests</h2><DataTable rows={leave.data?.requests} loading={leave.isLoading} rowKey={(l) => l.id} pageSize={6} empty="No leave requests." columns={[{ key: "type", header: "Type", render: (l) => <b>{l.leave_type}</b> }, { key: "dates", header: "Dates", render: (l) => `${day(l.start_date)} – ${day(l.end_date)}` }, { key: "status", header: "Status", render: (l) => <StatusBadge status={l.status} /> }, { key: "actions", header: "", align: "right", render: (l) => ["pending", "approved"].includes(l.status) && <button className="btn-link btn-link-danger" onClick={async () => { if (await confirm({ title: "Cancel this leave request?", confirmLabel: "Cancel request", danger: true })) post(`/hr/me/leave/${l.id}/cancel/`, {}, "Leave cancelled."); }}>Cancel</button> }]} /></section>
        <section className="space-y-2"><h2 className="section-title">Upcoming shifts</h2><DataTable rows={shifts.data?.results} loading={shifts.isLoading} rowKey={(s) => s.id} pageSize={6} empty="No shifts scheduled." columns={[{ key: "date", header: "Date", render: (s) => <b>{day(s.date)}</b> }, { key: "time", header: "Time", render: (s) => `${s.start_time.slice(0, 5)} – ${s.end_time.slice(0, 5)}` }]} /></section>
        <section className="space-y-2"><h2 className="section-title">Salary slips</h2><DataTable rows={slips.data} loading={slips.isLoading} rowKey={(s) => s.id} pageSize={6} empty="No salary slips yet." columns={[{ key: "period", header: "Month", render: (s) => <b>{s.period}</b> }, { key: "status", header: "Status", render: (s) => <StatusBadge status={s.status} /> }, { key: "actions", header: "", align: "right", render: (s) => <button className="btn-link" onClick={() => openProtectedFile(`/hr/me/payslips/${s.id}/pdf/`).then(() => done("Salary slip opened.")).catch(fail)}><Download size={13} aria-hidden />Download</button> }]} /></section>
        <section className="space-y-2"><h2 className="section-title">Recent attendance</h2><DataTable rows={att.data?.results} loading={att.isLoading} rowKey={(a) => a.id} pageSize={6} empty="No attendance yet." columns={[{ key: "date", header: "Date", render: (a) => day(a.date) }, { key: "status", header: "Status", render: (a) => <StatusBadge status={a.status} /> }, { key: "in", header: "In", render: (a) => time(a.clock_in) }, { key: "out", header: "Out", render: (a) => time(a.clock_out) }]} /></section>
      </div>
      {asking && <FormModal title="Request leave" submitLabel="Send request" onClose={() => setAsking(false)} fields={[{ name: "leave_type", label: "Leave type", type: "select", wide: true, options: (leave.data?.balances ?? []).map((b) => [String(b.leave_type), b.name]) }, { name: "start_date", label: "Start date", type: "date" }, { name: "end_date", label: "End date", type: "date" }, { name: "reason", label: "Reason", type: "textarea", required: false }]}
        onSubmit={async (v) => { await api("/hr/me/leave/", { method: "POST", body: { ...v, leave_type: Number(v.leave_type) } }); done("Leave requested."); }} />}
    </div>
  );
}
