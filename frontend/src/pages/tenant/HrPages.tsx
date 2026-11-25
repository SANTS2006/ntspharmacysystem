import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";

interface Page<T> { count: number; results: T[] }
interface Profile { user: number; full_name: string; staff_id: string; role: string | null; employment_status: string; job_title: string; employment_date: string; branch: number | null }
interface Att { id: number; name: string; date: string; status: string; clock_in: string | null; clock_out: string | null; source: string }
interface Leave { id: number; name: string; leave_type: string; start_date: string; end_date: string; days: number; status: string; reason: string }
interface Balance { leave_type: number; name: string; allowance: number; used: number; pending: number; remaining: number | null }
interface Run { id: number; period: string; status: string; staff: number; gross: string; net: string; tax: string; paid: string; created_by: number; lines?: Line[] }
interface Line { id: number; user: number; name: string; gross: string; tax: string; net: string; paid_amount: string; warnings: string[] }
interface Structure { id: number; user: number; basic_salary: string; effective_from: string; items: { component: string; value: string }[] }

const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const inputCls = "mt-1 rounded border p-2 font-normal";
const brand = { background: "var(--brand)" };
const money = (v: string | number) => Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const thisMonth = () => new Date().toISOString().slice(0, 7);
function useNote() { const [m, setM] = useState<{ ok: boolean; t: string } | null>(null); return { m, ok: (t: string) => setM({ ok: true, t }), fail: (e: unknown) => setM({ ok: false, t: errText(e) }), view: m && <p role={m.ok ? "status" : "alert"} className={`rounded p-3 text-sm ${m.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>{m.t}</p> }; }
const Tabs = <T extends string>({ tabs, tab, set }: { tabs: [T, string][]; tab: T; set: (t: T) => void }) => <div role="tablist" className="flex flex-wrap gap-2">{tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => set(k)} className={`rounded px-3 py-1 text-sm ${tab === k ? "text-white" : "border"}`} style={tab === k ? brand : undefined}>{l}</button>)}</div>;

// ======================= HR (managers) =======================
export function HrPage() {
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
  const decide = (id: number, what: "approve" | "reject") => { const note = window.prompt("Enter a note (optional)") ?? ""; api(`/hr/leave/${id}/${what}/`, { method: "POST", body: { note } }).then(() => { n.ok("Done."); refresh(); }).catch(n.fail); };
  const terminate = (p: Profile) => { const reason = window.prompt(`Enter the reason for ending ${p.full_name}'s employment`); if (reason && window.confirm("End this employment? Their access is removed immediately.")) api(`/hr/staff/${p.user}/terminate/`, { method: "POST", body: { reason } }).then(() => { n.ok("Employment ended."); refresh(); }).catch(n.fail); };
  const markAbsence = () => { const uid = window.prompt("Enter the staff user id"); const date = uid && window.prompt("Enter the date (YYYY-MM-DD)"); const status = date && window.prompt("Enter the status (present, late, absent, on_leave)", "absent"); if (uid && date && status) api("/hr/attendance/manual/", { method: "POST", body: { user: Number(uid), date, status } }).then(() => { n.ok("Attendance recorded."); refresh(); }).catch(n.fail); };
  return (
    <div className="space-y-4"><h1 className="text-2xl font-semibold">Human resources</h1>{n.view}
      <Tabs tabs={[["staff", "Staff records"], ["attendance", "Attendance"], ["leave", "Leave requests"]]} tab={tab} set={setTab} />
      {tab === "staff" && <>
        {can("hr.manage") && <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }} className="flex flex-wrap items-end gap-2 rounded-xl bg-white p-4 shadow-sm">
          <label className="text-sm font-medium">Staff member<select required className={`${inputCls} block`} value={f.user} onChange={(e) => setF({ ...f, user: e.target.value })}><option value="">Select a staff member</option>{users.data?.results.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label>
          <label className="text-sm font-medium">Employment date<input required type="date" className={`${inputCls} block`} value={f.employment_date} onChange={(e) => setF({ ...f, employment_date: e.target.value })} /></label>
          <label className="text-sm font-medium">Job title<input className={`${inputCls} block`} placeholder="Enter the job title" value={f.job_title} onChange={(e) => setF({ ...f, job_title: e.target.value })} /></label>
          <button className="rounded px-4 py-2 text-white" style={brand}>Create HR record</button></form>}
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Staff ID</th><th>Name</th><th>Role</th><th>Title</th><th>Since</th><th>Status</th><th /></tr></thead>
          <tbody>{staff.data?.results.map((p) => <tr key={p.user} className="border-t"><td className="p-3">{p.staff_id}</td><td>{p.full_name}</td><td>{p.role}</td><td>{p.job_title}</td><td>{p.employment_date}</td><td>{p.employment_status}</td>
            <td>{can("hr.sensitive") && p.employment_status !== "terminated" && <button className="underline" onClick={() => terminate(p)}>End employment</button>}</td></tr>)}</tbody></table>{staff.data?.results.length === 0 && <p className="p-3 text-slate-500">No HR records yet.</p>}</div></>}
      {tab === "attendance" && <>{can("hr.manage") && <button className="rounded border px-3 py-1 text-sm" onClick={markAbsence}>Record or correct attendance</button>}
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Date</th><th>Name</th><th>Status</th><th>In</th><th>Out</th><th>Source</th></tr></thead>
          <tbody>{att.data?.results.map((a) => <tr key={a.id} className="border-t"><td className="p-3">{a.date}</td><td>{a.name}</td><td>{a.status}</td><td>{a.clock_in ? new Date(a.clock_in).toLocaleTimeString() : ""}</td><td>{a.clock_out ? new Date(a.clock_out).toLocaleTimeString() : ""}</td><td>{a.source}</td></tr>)}</tbody></table></div></>}
      {tab === "leave" && <div className="space-y-2">{leave.data?.results.length === 0 && <p className="text-slate-500">No pending leave requests.</p>}{leave.data?.results.map((l) => <article key={l.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white p-3 text-sm shadow-sm"><span><strong>{l.name}</strong> · {l.leave_type} · {l.start_date} to {l.end_date} ({l.days} days) {l.reason && `· ${l.reason}`}</span>
        {can("hr.manage") && <span className="space-x-2"><button className="underline" onClick={() => decide(l.id, "approve")}>Approve</button><button className="underline" onClick={() => decide(l.id, "reject")}>Reject</button></span>}</article>)}</div>}
    </div>
  );
}

// ======================= Payroll (HR / approvers / branch viewers) =======================
export function PayrollPage() {
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
  const pay = (l: Line) => {
    const amount = window.prompt(`Enter the amount to pay ${l.name} (outstanding ${money(Number(l.net) - Number(l.paid_amount))})`); if (!amount) return;
    const method = window.prompt("Enter the method (cash, bank_transfer, mobile_money)", "bank_transfer"); if (!method) return;
    const reference = window.prompt("Enter the payment reference"); if (!reference) return;
    if (window.confirm(`Record a salary payment of ${amount} to ${l.name}? This is permanent.`)) act(`/payroll/lines/${l.id}/pay/`, "Payment recorded.", { amount, method, reference });
  };
  const adjust = () => { const uid = window.prompt("Enter the staff user id"); const kind = uid && window.prompt("Enter the kind (bonus, commission, overtime, deduction)", "bonus"); const amount = kind && window.prompt("Enter the amount"); const note = amount && window.prompt("Enter a note"); if (uid && kind && amount && note) act("/payroll/adjustments/", "Adjustment added to this month's payroll.", { user: Number(uid), period, kind, amount, note }); };
  const advance = () => { const uid = window.prompt("Enter the staff user id"); const amount = uid && window.prompt("Enter the advance amount"); const rec = amount && window.prompt("Enter the monthly recovery amount"); const ref = rec && window.prompt("Enter the payment reference"); if (uid && amount && rec && ref) act("/payroll/advances/", "Advance recorded.", { user: Number(uid), amount, monthly_recovery: rec, method: "cash", reference: ref }); };
  const setStructure = () => { const uid = window.prompt("Enter the staff user id"); const basic = uid && window.prompt("Enter the basic monthly salary"); const eff = basic && window.prompt("Enter the effective date (YYYY-MM-DD)"); if (uid && basic && eff) act("/payroll/structures/", "New salary version saved.", { user: Number(uid), basic_salary: basic, effective_from: eff, items: [] }); };
  const saveCfg = () => { const e = window.prompt("Enter the employee pension percentage", cfg.data?.pension_employee_pct ?? "0"); const r = e !== null && window.prompt("Enter the employer pension percentage", cfg.data?.pension_employer_pct ?? "0"); const b = r !== null && e !== null && window.prompt('Enter tax brackets as JSON, e.g. [{"up_to":"500","rate":"0"},{"up_to":null,"rate":"15"}]', JSON.stringify(cfg.data?.tax_brackets ?? [])); if (e !== null && r !== false && r !== null && b) { try { api("/payroll/config/", { method: "PUT", body: { pension_employee_pct: e, pension_employer_pct: r, tax_brackets: JSON.parse(b) } }).then(() => { n.ok("Saved."); refresh(); }).catch(n.fail); } catch { n.fail(new Error("Invalid JSON")); } } };
  return (
    <div className="space-y-4"><h1 className="text-2xl font-semibold">Payroll</h1><p className="text-sm text-amber-700">Confidential. Access is logged.</p>{n.view}
      <Tabs tabs={[["runs", "Payroll runs"], ["structures", "Salary structures"], ["setup", "Rates & advances"]]} tab={tab} set={setTab} />
      {tab === "runs" && <>
        {can("payroll.manage") && !user?.branch && <div className="flex flex-wrap items-end gap-2 rounded-xl bg-white p-4 shadow-sm"><label className="text-sm font-medium">Month<input type="month" className={`${inputCls} block`} value={period} onChange={(e) => setPeriod(e.target.value)} /></label>
          <button className="rounded px-4 py-2 text-white" style={brand} onClick={() => act("/payroll/runs/", "Payroll run created.", { period })}>Create payroll run</button><button className="rounded border px-3 py-2 text-sm" onClick={adjust}>Add bonus / commission / overtime / deduction</button></div>}
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Period</th><th>Staff</th><th>Gross</th><th>Tax</th><th>Net</th><th>Paid</th><th>Status</th><th /></tr></thead>
          <tbody>{runs.data?.results.map((r) => <tr key={r.id} className="border-t"><td className="p-3">{r.period}</td><td>{r.staff}</td><td>{money(r.gross)}</td><td>{money(r.tax)}</td><td>{money(r.net)}</td><td>{money(r.paid)}</td><td>{r.status}</td>
            <td className="space-x-2"><button className="underline" onClick={() => setOpen(r.id)}>Open</button>
              {r.status === "draft" && can("payroll.manage") && <><button className="underline" onClick={() => act(`/payroll/runs/${r.id}/recalculate/`, "Recalculated.")}>Recalculate</button><button className="underline" onClick={() => act(`/payroll/runs/${r.id}/submit/`, "Submitted for approval.")}>Submit</button></>}
              {["draft", "submitted"].includes(r.status) && can("payroll.manage") && <button className="underline" onClick={() => window.confirm("Cancel this run?") && act(`/payroll/runs/${r.id}/cancel/`, "Cancelled.")}>Cancel</button>}
              {r.status === "submitted" && can("payroll.approve") && r.created_by !== user?.id && <button className="underline" onClick={() => window.confirm("Approve this payroll? It is posted to the books and cannot be edited.") && act(`/payroll/runs/${r.id}/approve/`, "Approved and posted.")}>Approve</button>}</td></tr>)}</tbody></table>{runs.data?.results.length === 0 && <p className="p-3 text-slate-500">No payroll runs.</p>}</div>
        {detail.data?.lines && open !== null && <section className="rounded-xl bg-white p-4 shadow-sm"><div className="flex justify-between"><h2 className="font-semibold">Run {detail.data.period} · {detail.data.status}</h2><button className="underline" onClick={() => setOpen(null)}>Close</button></div>
          <table className="mt-2 w-full text-left text-sm"><thead><tr><th>Name</th><th>Gross</th><th>Tax</th><th>Net</th><th>Paid</th><th /></tr></thead><tbody>{detail.data.lines.map((l) => <tr key={l.id} className="border-t"><td>{l.name} {l.warnings.length > 0 && <em className="text-amber-700" title={l.warnings.join(" ")}>⚠</em>}</td><td>{money(l.gross)}</td><td>{money(l.tax)}</td><td>{money(l.net)}</td><td>{money(l.paid_amount)}</td>
            <td className="space-x-2">{["approved", "paid"].includes(detail.data!.status) && <button className="underline" onClick={() => openProtectedFile(`/payroll/lines/${l.id}/payslip/pdf/`).catch(n.fail)}>Payslip</button>}{detail.data!.status === "approved" && can("payroll.manage") && Number(l.paid_amount) < Number(l.net) && <button className="underline" onClick={() => pay(l)}>Pay</button>}</td></tr>)}</tbody></table></section>}</>}
      {tab === "structures" && <>{can("payroll.manage") && <button className="rounded border px-3 py-1 text-sm" onClick={setStructure}>Set a new salary version</button>}
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Staff user</th><th>Basic</th><th>Effective</th><th>Components</th></tr></thead><tbody>{structures.data?.map((s) => <tr key={s.id} className="border-t"><td className="p-3">{s.user}</td><td>{money(s.basic_salary)}</td><td>{s.effective_from}</td><td>{s.items.map((i) => `${i.component} ${i.value}`).join(", ")}</td></tr>)}</tbody></table></div></>}
      {tab === "setup" && <div className="space-y-3 rounded-xl bg-white p-4 text-sm shadow-sm"><p>Employee pension: {cfg.data?.pension_employee_pct}% · Employer pension: {cfg.data?.pension_employer_pct}% · Tax brackets: {cfg.data?.tax_brackets.map((b) => `${b.up_to ?? "above"}→${b.rate}%`).join(", ") || "none"}</p>
        <p className="text-slate-600">Enter the rates that apply in your jurisdiction; nothing statutory is built in.</p><div className="space-x-2">{can("payroll.manage") && <button className="rounded border px-3 py-1" onClick={saveCfg}>Edit rates</button>}{can("payroll.approve") && <button className="rounded border px-3 py-1" onClick={advance}>Grant a salary advance</button>}</div></div>}
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
    <div className="space-y-4"><h1 className="text-2xl font-semibold">My work</h1>{n.view}
      <p className="text-sm text-slate-600">{me.data?.staff_id ? `Staff ID ${me.data.staff_id} · ${me.data.job_title ?? ""} · since ${me.data.employment_date}` : me.data?.note}</p>
      <div className="flex gap-2"><button className="rounded px-4 py-2 text-white" style={brand} onClick={() => clock("in")}>Clock in</button><button className="rounded border px-4 py-2" onClick={() => clock("out")}>Clock out</button></div>
      <section className="rounded-xl bg-white p-4 shadow-sm"><h2 className="font-semibold">Leave</h2><ul className="text-sm">{leave.data?.balances.map((b) => <li key={b.leave_type}>{b.name}: {b.used} used{b.remaining !== null ? `, ${b.remaining} left` : ""}{b.pending ? ` (${b.pending} pending)` : ""}</li>)}</ul>
        <form onSubmit={(e) => { e.preventDefault(); request.mutate(); }} className="mt-2 flex flex-wrap items-end gap-2"><select required aria-label="Leave type" className={inputCls} value={lv.leave_type} onChange={(e) => setLv({ ...lv, leave_type: e.target.value })}><option value="">Select a leave type</option>{leave.data?.balances.map((b) => <option key={b.leave_type} value={b.leave_type}>{b.name}</option>)}</select>
          <input required type="date" aria-label="Start date" className={inputCls} value={lv.start_date} onChange={(e) => setLv({ ...lv, start_date: e.target.value })} /><input required type="date" aria-label="End date" className={inputCls} value={lv.end_date} onChange={(e) => setLv({ ...lv, end_date: e.target.value })} />
          <input aria-label="Reason" className={inputCls} placeholder="Enter a reason" value={lv.reason} onChange={(e) => setLv({ ...lv, reason: e.target.value })} /><button className="rounded px-3 py-2 text-white" style={brand}>Request leave</button></form>
        <ul className="mt-2 text-sm">{leave.data?.requests.map((l) => <li key={l.id}>{l.leave_type} {l.start_date} → {l.end_date}: {l.status} {["pending", "approved"].includes(l.status) && <button className="underline" onClick={() => api(`/hr/me/leave/${l.id}/cancel/`, { method: "POST" }).then(() => qc.invalidateQueries()).catch(n.fail)}>cancel</button>}</li>)}</ul></section>
      <section className="rounded-xl bg-white p-4 shadow-sm"><h2 className="font-semibold">Upcoming shifts</h2>{shifts.data?.results.length === 0 && <p className="text-sm text-slate-500">None scheduled.</p>}<ul className="text-sm">{shifts.data?.results.map((s) => <li key={s.id}>{s.date} {s.start_time}–{s.end_time}</li>)}</ul></section>
      <section className="rounded-xl bg-white p-4 shadow-sm"><h2 className="font-semibold">Salary slips</h2>{slips.data?.length === 0 && <p className="text-sm text-slate-500">No salary slips yet.</p>}<ul className="text-sm">{slips.data?.map((s) => <li key={s.id}>{s.period} · {s.status} <button className="underline" onClick={() => openProtectedFile(`/hr/me/payslips/${s.id}/pdf/`).catch(n.fail)}>Download</button></li>)}</ul></section>
      <section className="rounded-xl bg-white p-4 shadow-sm"><h2 className="font-semibold">Recent attendance</h2><ul className="text-sm">{att.data?.results.slice(0, 10).map((a) => <li key={a.id}>{a.date}: {a.status}</li>)}</ul></section>
    </div>
  );
}
