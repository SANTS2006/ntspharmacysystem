import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { EmptyState, PageHeader, StatusBadge, useConfirm, usePrompt } from "../../components/ui";

interface Page<T> { count: number; results: T[] }
interface Profile { user: number; full_name: string; staff_id: string; role: string | null; employment_status: string; job_title: string; employment_date: string; branch: number | null }
interface Att { id: number; name: string; date: string; status: string; clock_in: string | null; clock_out: string | null; source: string }
interface Leave { id: number; name: string; leave_type: string; start_date: string; end_date: string; days: number; status: string; reason: string }
interface Balance { leave_type: number; name: string; allowance: number; used: number; pending: number; remaining: number | null }
interface Run { id: number; period: string; status: string; staff: number; gross: string; net: string; tax: string; paid: string; created_by: number; lines?: Line[] }
interface Line { id: number; user: number; name: string; gross: string; tax: string; net: string; paid_amount: string; warnings: string[] }
interface Structure { id: number; user: number; basic_salary: string; effective_from: string; items: { component: string; value: string }[] }

const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const inputCls = "mt-1 px-3 py-2 font-normal";
const brand = { background: "var(--brand)" };
const money = (v: string | number) => Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const thisMonth = () => new Date().toISOString().slice(0, 7);
function useNote() { const [m, setM] = useState<{ ok: boolean; t: string } | null>(null); return { m, ok: (t: string) => setM({ ok: true, t }), fail: (e: unknown) => setM({ ok: false, t: errText(e) }), view: m && <p role={m.ok ? "status" : "alert"} className={`alert ${m.ok ? "alert-success" : "alert-error"}`}>{m.t}</p> }; }
const Tabs = <T extends string>({ tabs, tab, set }: { tabs: [T, string][]; tab: T; set: (t: T) => void }) => <div role="tablist" className="tablist">{tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => set(k)} className={`tab ${tab === k ? "tab-active" : ""}`}>{l}</button>)}</div>;

// ======================= HR (managers) =======================
export function HrPage() {
  const promptFor = usePrompt(); const confirmDialog = useConfirm();
  const { user } = useAuth(); const qc = useQueryClient(); const n = useNote();
  const can = (p: string) => !!user?.permissions.includes(p);
  const [tab, setTab] = useState<"staff" | "attendance" | "leave">("staff");
  const refresh = () => qc.invalidateQueries();
  const staff = useQuery({ queryKey: ["hr-staff"], queryFn: () => api<Page<Profile>>("/hr/staff/") });
  const att = useQuery({ queryKey: ["hr-att"], queryFn: () => api<Page<Att>>("/hr/attendance/"), enabled: tab === "attendance" });
  const leave = useQuery({ queryKey: ["hr-leave"], queryFn: () => api<Page<Leave>>("/hr/leave/?status=pending"), enabled: tab === "leave" });
  const [f, setF] = useState({ user: "", employment_date: "", job_title: "" });
  const users = useQuery({ queryKey: ["staff-for-hr"], queryFn: () => api<Page<{ id: number; full_name: string }>>("/staff/"), enabled: can("hr.manage") });
  const add = useMutation({ mutationFn: () => api("/hr/staff/", { method: "POST", body: { ...f, user: Number(f.user) } }), onSuccess: () => { n.ok("HR record created."); refresh(); }, onError: n.fail });
  const decide = async (id: number, what: "approve" | "reject") => { const v = await promptFor({ title: what === "approve" ? "Approve leave" : "Reject leave", confirmLabel: what === "approve" ? "Approve" : "Reject", danger: what === "reject", fields: [{ name: "note", label: "Note (optional)", type: "textarea", required: false }] }); if (v) api(`/hr/leave/${id}/${what}/`, { method: "POST", body: { note: v.note } }).then(() => { n.ok("Done."); refresh(); }).catch(n.fail); };
  const terminate = async (p: Profile) => { const v = await promptFor({ title: `End ${p.full_name}'s employment`, message: "Their access is removed immediately.", confirmLabel: "End employment", danger: true, fields: [{ name: "reason", label: "Reason", type: "textarea" }] }); if (v?.reason) api(`/hr/staff/${p.user}/terminate/`, { method: "POST", body: { reason: v.reason } }).then(() => { n.ok("Employment ended."); refresh(); }).catch(n.fail); };
  const markAbsence = async () => { const v = await promptFor({ title: "Record or correct attendance", confirmLabel: "Save", fields: [{ name: "user", label: "Staff user id", type: "number", min: 1, step: "1" }, { name: "date", label: "Date (YYYY-MM-DD)", placeholder: "YYYY-MM-DD" }, { name: "status", label: "Status", type: "select", defaultValue: "absent", options: [["present", "Present"], ["late", "Late"], ["absent", "Absent"], ["on_leave", "On leave"]] }] }); if (v?.user && v.date) api("/hr/attendance/manual/", { method: "POST", body: { user: Number(v.user), date: v.date, status: v.status } }).then(() => { n.ok("Attendance recorded."); refresh(); }).catch(n.fail); };
  return (
    <div className="space-y-4"><PageHeader title="Human resources" subtitle="Staff records, attendance, leave and shifts." />{n.view}
      <Tabs tabs={[["staff", "Staff records"], ["attendance", "Attendance"], ["leave", "Leave requests"]]} tab={tab} set={setTab} />
      {tab === "staff" && <>
        {can("hr.manage") && <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }} className="flex flex-wrap items-end gap-2 card p-4">
          <label className="text-sm font-medium">Staff member<select required className={`${inputCls} block`} value={f.user} onChange={(e) => setF({ ...f, user: e.target.value })}><option value="">Select a staff member</option>{users.data?.results.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label>
          <label className="text-sm font-medium">Employment date<input required type="date" className={`${inputCls} block`} value={f.employment_date} onChange={(e) => setF({ ...f, employment_date: e.target.value })} /></label>
          <label className="text-sm font-medium">Job title<input className={`${inputCls} block`} placeholder="Enter the job title" value={f.job_title} onChange={(e) => setF({ ...f, job_title: e.target.value })} /></label>
          <button className="btn btn-primary">Create HR record</button></form>}
        <div className="table-wrap"><table className="table"><thead><tr><th>Staff ID</th><th>Name</th><th>Role</th><th>Title</th><th>Since</th><th>Status</th><th /></tr></thead>
          <tbody>{staff.data?.results.map((p) => <tr key={p.user}><td>{p.staff_id}</td><td>{p.full_name}</td><td>{p.role}</td><td>{p.job_title}</td><td>{p.employment_date}</td><td>{p.employment_status}</td>
            <td>{can("hr.sensitive") && p.employment_status !== "terminated" && <button className="btn-link" onClick={() => terminate(p)}>End employment</button>}</td></tr>)}</tbody></table>{staff.data?.results.length === 0 && <p className="p-3 text-slate-500">No HR records yet.</p>}</div></>}
      {tab === "attendance" && <>{can("hr.manage") && <button className="btn btn-outline btn-sm" onClick={markAbsence}>Record or correct attendance</button>}
        <div className="table-wrap"><table className="table"><thead><tr><th>Date</th><th>Name</th><th>Status</th><th>In</th><th>Out</th><th>Source</th></tr></thead>
          <tbody>{att.data?.results.map((a) => <tr key={a.id}><td>{a.date}</td><td>{a.name}</td><td><StatusBadge status={a.status} /></td><td>{a.clock_in ? new Date(a.clock_in).toLocaleTimeString() : ""}</td><td>{a.clock_out ? new Date(a.clock_out).toLocaleTimeString() : ""}</td><td>{a.source}</td></tr>)}</tbody></table></div></>}
      {tab === "leave" && <div className="space-y-2">{leave.data?.results.length === 0 && <EmptyState>No pending leave requests.</EmptyState>}{leave.data?.results.map((l) => <article key={l.id} className="flex flex-wrap items-center justify-between gap-2 card p-3 text-sm "><span><strong>{l.name}</strong> · {l.leave_type} · {l.start_date} to {l.end_date} ({l.days} days) {l.reason && `· ${l.reason}`}</span>
        {can("hr.manage") && <span className="space-x-2"><button className="btn-link" onClick={() => decide(l.id, "approve")}>Approve</button><button className="btn-link" onClick={() => decide(l.id, "reject")}>Reject</button></span>}</article>)}</div>}
    </div>
  );
}

// ======================= Payroll (HR / approvers / branch viewers) =======================
export function PayrollPage() {
  const promptFor = usePrompt(); const confirmDialog = useConfirm();
  const { user } = useAuth(); const qc = useQueryClient(); const n = useNote();
  const can = (p: string) => !!user?.permissions.includes(p);
  const [tab, setTab] = useState<"runs" | "structures" | "setup">("runs"); const [open, setOpen] = useState<number | null>(null);
  const refresh = () => qc.invalidateQueries();
  const runs = useQuery({ queryKey: ["pr-runs"], queryFn: () => api<Page<Run>>("/payroll/runs/") });
  const detail = useQuery({ queryKey: ["pr-run", open], queryFn: () => api<Run>(`/payroll/runs/${open}/`), enabled: open !== null });
  const structures = useQuery({ queryKey: ["pr-struct"], queryFn: () => api<Structure[]>("/payroll/structures/"), enabled: tab === "structures" });
  const cfg = useQuery({ queryKey: ["pr-config"], queryFn: () => api<{ pension_employee_pct: string; pension_employer_pct: string; tax_brackets: { up_to: string | null; rate: string }[] }>("/payroll/config/"), enabled: tab === "setup" });
  const [period, setPeriod] = useState(thisMonth());
  const act = (path: string, label: string, body: object = {}) => api(path, { method: "POST", body }).then(() => { n.ok(label); refresh(); }).catch(n.fail);
  const pay = async (l: Line) => {
    const v = await promptFor({ title: `Pay ${l.name}`, confirmLabel: "Continue", fields: [
      { name: "amount", label: `Amount (outstanding ${money(Number(l.net) - Number(l.paid_amount))})`, type: "number", min: 0.01, step: "0.01" },
      { name: "method", label: "Method", type: "select", defaultValue: "bank_transfer", options: [["cash", "Cash"], ["bank_transfer", "Bank transfer"], ["mobile_money", "Mobile money"]] }, { name: "reference", label: "Payment reference" }] });
    if (!v) return; const { amount, method, reference } = v;
    if (await confirmDialog({ title: "Record this salary payment?", message: `${amount} to ${l.name}. This is permanent.`, confirmLabel: "Record payment" })) act(`/payroll/lines/${l.id}/pay/`, "Payment recorded.", { amount, method, reference });
  };
  const staffId = { name: "user", label: "Staff user id", type: "number" as const, min: 1, step: "1" };
  const adjust = async () => { const v = await promptFor({ title: "Add a payroll adjustment", confirmLabel: "Add adjustment", fields: [staffId, { name: "kind", label: "Kind", type: "select", defaultValue: "bonus", options: [["bonus", "Bonus"], ["commission", "Commission"], ["overtime", "Overtime"], ["deduction", "Deduction"]] }, { name: "amount", label: "Amount", type: "number", min: 0.01, step: "0.01" }, { name: "note", label: "Note" }] }); if (v) act("/payroll/adjustments/", "Adjustment added to this month's payroll.", { user: Number(v.user), period, kind: v.kind, amount: v.amount, note: v.note }); };
  const advance = async () => { const v = await promptFor({ title: "Record a salary advance", confirmLabel: "Record advance", fields: [staffId, { name: "amount", label: "Advance amount", type: "number", min: 0.01, step: "0.01" }, { name: "rec", label: "Monthly recovery amount", type: "number", min: 0.01, step: "0.01" }, { name: "ref", label: "Payment reference" }] }); if (v) act("/payroll/advances/", "Advance recorded.", { user: Number(v.user), amount: v.amount, monthly_recovery: v.rec, method: "cash", reference: v.ref }); };
  const setStructure = async () => { const v = await promptFor({ title: "New salary version", confirmLabel: "Save salary", fields: [staffId, { name: "basic", label: "Basic monthly salary", type: "number", min: 0, step: "0.01" }, { name: "eff", label: "Effective date (YYYY-MM-DD)", placeholder: "YYYY-MM-DD" }] }); if (v) act("/payroll/structures/", "New salary version saved.", { user: Number(v.user), basic_salary: v.basic, effective_from: v.eff, items: [] }); };
  const saveCfg = async () => { const v = await promptFor({ title: "Payroll configuration", confirmLabel: "Save", fields: [{ name: "e", label: "Employee pension percentage", defaultValue: cfg.data?.pension_employee_pct ?? "0" }, { name: "r", label: "Employer pension percentage", defaultValue: cfg.data?.pension_employer_pct ?? "0" }, { name: "b", label: 'Tax brackets (JSON), e.g. [{"up_to":"500","rate":"0"},{"up_to":null,"rate":"15"}]', type: "textarea", defaultValue: JSON.stringify(cfg.data?.tax_brackets ?? []) }] }); if (!v) return; try { const tax_brackets = JSON.parse(v.b); api("/payroll/config/", { method: "PUT", body: { pension_employee_pct: v.e, pension_employer_pct: v.r, tax_brackets } }).then(() => { n.ok("Saved."); refresh(); }).catch(n.fail); } catch { n.fail(new Error("Invalid JSON")); } };
  return (
    <div className="space-y-4"><PageHeader title="Payroll" subtitle="Salary structures, payroll runs and payslips." /><p className="text-sm text-amber-700">Confidential. Access is logged.</p>{n.view}
      <Tabs tabs={[["runs", "Payroll runs"], ["structures", "Salary structures"], ["setup", "Rates & advances"]]} tab={tab} set={setTab} />
      {tab === "runs" && <>
        {can("payroll.manage") && !user?.branch && <div className="flex flex-wrap items-end gap-2 card p-4"><label className="text-sm font-medium">Month<input type="month" className={`${inputCls} block`} value={period} onChange={(e) => setPeriod(e.target.value)} /></label>
          <button className="btn btn-primary" onClick={() => act("/payroll/runs/", "Payroll run created.", { period })}>Create payroll run</button><button className="btn btn-outline btn-sm" onClick={adjust}>Add bonus / commission / overtime / deduction</button></div>}
        <div className="table-wrap"><table className="table"><thead><tr><th>Period</th><th>Staff</th><th>Gross</th><th>Tax</th><th>Net</th><th>Paid</th><th>Status</th><th /></tr></thead>
          <tbody>{runs.data?.results.map((r) => <tr key={r.id}><td>{r.period}</td><td>{r.staff}</td><td>{money(r.gross)}</td><td>{money(r.tax)}</td><td>{money(r.net)}</td><td>{money(r.paid)}</td><td><StatusBadge status={r.status} /></td>
            <td className="space-x-2"><button className="btn-link" onClick={() => setOpen(r.id)}>Open</button>
              {r.status === "draft" && can("payroll.manage") && <><button className="btn-link" onClick={() => act(`/payroll/runs/${r.id}/recalculate/`, "Recalculated.")}>Recalculate</button><button className="btn-link" onClick={() => act(`/payroll/runs/${r.id}/submit/`, "Submitted for approval.")}>Submit</button></>}
              {["draft", "submitted"].includes(r.status) && can("payroll.manage") && <button className="btn-link" onClick={async () => { if (await confirmDialog({ title: "Cancel this payroll run?", confirmLabel: "Cancel run", danger: true })) act(`/payroll/runs/${r.id}/cancel/`, "Cancelled."); }}>Cancel</button>}
              {r.status === "submitted" && can("payroll.approve") && r.created_by !== user?.id && <button className="btn-link" onClick={async () => { if (await confirmDialog({ title: "Approve this payroll?", message: "It is posted to the books and cannot be edited.", confirmLabel: "Approve payroll" })) act(`/payroll/runs/${r.id}/approve/`, "Approved and posted."); }}>Approve</button>}</td></tr>)}</tbody></table>{runs.data?.results.length === 0 && <p className="p-3 text-slate-500">No payroll runs.</p>}</div>
        {detail.data?.lines && open !== null && <section className="card p-4"><div className="flex justify-between"><h2 className="section-title">Run {detail.data.period} · {detail.data.status}</h2><button className="btn-link" onClick={() => setOpen(null)}>Close</button></div>
          <table className="mt-2 w-full text-left text-sm"><thead><tr><th>Name</th><th>Gross</th><th>Tax</th><th>Net</th><th>Paid</th><th /></tr></thead><tbody>{detail.data.lines.map((l) => <tr key={l.id}><td>{l.name} {l.warnings.length > 0 && <em className="text-amber-700" title={l.warnings.join(" ")}>⚠</em>}</td><td>{money(l.gross)}</td><td>{money(l.tax)}</td><td>{money(l.net)}</td><td>{money(l.paid_amount)}</td>
            <td className="space-x-2">{["approved", "paid"].includes(detail.data!.status) && <button className="btn-link" onClick={() => openProtectedFile(`/payroll/lines/${l.id}/payslip/pdf/`).catch(n.fail)}>Payslip</button>}{detail.data!.status === "approved" && can("payroll.manage") && Number(l.paid_amount) < Number(l.net) && <button className="btn-link" onClick={() => pay(l)}>Pay</button>}</td></tr>)}</tbody></table></section>}</>}
      {tab === "structures" && <>{can("payroll.manage") && <button className="btn btn-outline btn-sm" onClick={setStructure}>Set a new salary version</button>}
        <div className="table-wrap"><table className="table"><thead><tr><th>Staff user</th><th>Basic</th><th>Effective</th><th>Components</th></tr></thead><tbody>{structures.data?.map((s) => <tr key={s.id}><td>{s.user}</td><td>{money(s.basic_salary)}</td><td>{s.effective_from}</td><td>{s.items.map((i) => `${i.component} ${i.value}`).join(", ")}</td></tr>)}</tbody></table></div></>}
      {tab === "setup" && <div className="space-y-3 card p-4 text-sm "><p>Employee pension: {cfg.data?.pension_employee_pct}% · Employer pension: {cfg.data?.pension_employer_pct}% · Tax brackets: {cfg.data?.tax_brackets.map((b) => `${b.up_to ?? "above"}→${b.rate}%`).join(", ") || "none"}</p>
        <p className="text-slate-600">Enter the rates that apply in your jurisdiction; nothing statutory is built in.</p><div className="space-x-2">{can("payroll.manage") && <button className="btn btn-outline btn-sm" onClick={saveCfg}>Edit rates</button>}{can("payroll.approve") && <button className="btn btn-outline btn-sm" onClick={advance}>Grant a salary advance</button>}</div></div>}
    </div>
  );
}

// ======================= My work (every staff member: own data only) =======================
export function MyWorkPage() {
  const qc = useQueryClient(); const n = useNote();
  const me = useQuery({ queryKey: ["my-hr"], queryFn: () => api<{ staff_id?: string; job_title?: string; employment_date?: string; note?: string }>("/hr/me/") });
  const att = useQuery({ queryKey: ["my-att"], queryFn: () => api<Page<Att>>("/hr/me/attendance/") });
  const leave = useQuery({ queryKey: ["my-leave"], queryFn: () => api<{ balances: Balance[]; requests: Leave[] }>("/hr/me/leave/") });
  const slips = useQuery({ queryKey: ["my-slips"], queryFn: () => api<{ id: number; period: string; net: string; status: string }[]>("/hr/me/payslips/") });
  const shifts = useQuery({ queryKey: ["my-shifts"], queryFn: () => api<Page<{ id: number; date: string; start_time: string; end_time: string }>>("/hr/me/shifts/") });
  const [lv, setLv] = useState({ leave_type: "", start_date: "", end_date: "", reason: "" });
  const clock = (what: "in" | "out") => api(`/hr/attendance/clock-${what}/`, { method: "POST" }).then(() => { n.ok(what === "in" ? "Clocked in." : "Clocked out."); qc.invalidateQueries(); }).catch(n.fail);
  const request = useMutation({ mutationFn: () => api("/hr/me/leave/", { method: "POST", body: { ...lv, leave_type: Number(lv.leave_type) } }), onSuccess: () => { n.ok("Leave requested."); qc.invalidateQueries(); }, onError: n.fail });
  return (
    <div className="space-y-4"><PageHeader title="My work" subtitle="Your shifts, attendance, leave and payslips." />{n.view}
      <p className="text-sm text-slate-600">{me.data?.staff_id ? `Staff ID ${me.data.staff_id} · ${me.data.job_title ?? ""} · since ${me.data.employment_date}` : me.data?.note}</p>
      <div className="flex gap-2"><button className="btn btn-primary" onClick={() => clock("in")}>Clock in</button><button className="btn btn-outline" onClick={() => clock("out")}>Clock out</button></div>
      <section className="card p-4"><h2 className="section-title">Leave</h2><ul className="text-sm">{leave.data?.balances.map((b) => <li key={b.leave_type}>{b.name}: {b.used} used{b.remaining !== null ? `, ${b.remaining} left` : ""}{b.pending ? ` (${b.pending} pending)` : ""}</li>)}</ul>
        <form onSubmit={(e) => { e.preventDefault(); request.mutate(); }} className="mt-2 flex flex-wrap items-end gap-2"><select required aria-label="Leave type" className={inputCls} value={lv.leave_type} onChange={(e) => setLv({ ...lv, leave_type: e.target.value })}><option value="">Select a leave type</option>{leave.data?.balances.map((b) => <option key={b.leave_type} value={b.leave_type}>{b.name}</option>)}</select>
          <input required type="date" aria-label="Start date" className={inputCls} value={lv.start_date} onChange={(e) => setLv({ ...lv, start_date: e.target.value })} /><input required type="date" aria-label="End date" className={inputCls} value={lv.end_date} onChange={(e) => setLv({ ...lv, end_date: e.target.value })} />
          <input aria-label="Reason" className={inputCls} placeholder="Enter a reason" value={lv.reason} onChange={(e) => setLv({ ...lv, reason: e.target.value })} /><button className="btn btn-primary">Request leave</button></form>
        <ul className="mt-2 text-sm">{leave.data?.requests.map((l) => <li key={l.id}>{l.leave_type} {l.start_date} → {l.end_date}: {l.status} {["pending", "approved"].includes(l.status) && <button className="btn-link" onClick={() => api(`/hr/me/leave/${l.id}/cancel/`, { method: "POST" }).then(() => qc.invalidateQueries()).catch(n.fail)}>cancel</button>}</li>)}</ul></section>
      <section className="card p-4"><h2 className="section-title">Upcoming shifts</h2>{shifts.data?.results.length === 0 && <p className="text-sm text-slate-500">None scheduled.</p>}<ul className="text-sm">{shifts.data?.results.map((s) => <li key={s.id}>{s.date} {s.start_time}–{s.end_time}</li>)}</ul></section>
      <section className="card p-4"><h2 className="section-title">Salary slips</h2>{slips.data?.length === 0 && <EmptyState>No salary slips yet.</EmptyState>}<ul className="text-sm">{slips.data?.map((s) => <li key={s.id}>{s.period} · {s.status} <button className="btn-link" onClick={() => openProtectedFile(`/hr/me/payslips/${s.id}/pdf/`).catch(n.fail)}>Download</button></li>)}</ul></section>
      <section className="card p-4"><h2 className="section-title">Recent attendance</h2><ul className="text-sm">{att.data?.results.slice(0, 10).map((a) => <li key={a.id}>{a.date}: {a.status}</li>)}</ul></section>
    </div>
  );
}
