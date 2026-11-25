import { AlertCircle, CheckCircle2, Eye, EyeOff, Loader2, Pill, ShieldCheck, Boxes, HeartPulse, type LucideIcon } from "lucide-react";
import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router-dom";

/** Split-screen auth layout: brand panel (uses the active --brand colour) + form card. `embedded` = card only, for pages inside a pharmacy site. */
export function AuthShell({ title, subtitle, icon: Icon, children, footer, embedded = false, brandName = "PharmaCloud", logo = "/logo.webp" }: {
  title: string; subtitle?: string; icon: LucideIcon; children: ReactNode; footer?: ReactNode; embedded?: boolean; brandName?: string; logo?: string;
}) {
  const card = (
    <div className="w-full max-w-md">
      <div className="mb-6">
        <span className="mb-4 grid h-12 w-12 place-items-center rounded-2xl text-white shadow-lg" style={{ background: "linear-gradient(135deg, var(--brand), var(--brand-2))" }}><Icon size={24} aria-hidden /></span>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {children}
      {footer && <div className="mt-6 text-center text-sm text-slate-500">{footer}</div>}
    </div>
  );
  if (embedded) return <div className="grid place-items-center py-8"><div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-xl shadow-slate-200/60">{card}</div></div>;
  return (
    <main className="grid min-h-screen bg-white lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden text-white lg:flex lg:flex-col lg:justify-between lg:p-12" style={{ background: "linear-gradient(145deg, #0b3277 0%, var(--brand) 55%, var(--brand-2) 130%)" }}>
        <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-white/10 blur-2xl" aria-hidden />
        <div className="pointer-events-none absolute -bottom-32 -left-16 h-96 w-96 rounded-full bg-cyan-300/20 blur-3xl" aria-hidden />
        <Link to="/" className="relative z-10 flex items-center gap-3 text-xl font-bold"><img src={logo} alt="" className="h-11 w-11 rounded-xl bg-white p-1" />{brandName}</Link>
        <div className="relative z-10 max-w-md">
          <h2 className="text-4xl font-bold leading-tight">Run your pharmacy with confidence.</h2>
          <p className="mt-3 text-blue-100">Inventory, prescriptions, point of sale and finance in one secure, multi-branch platform.</p>
          <ul className="mt-8 space-y-4 text-sm">
            {[[ShieldCheck, "Role-based access and a full audit trail"], [Pill, "Pharmacist-approved prescriptions and safe dispensing"], [Boxes, "Batch and expiry tracking across every branch"], [HeartPulse, "Online orders and customer care, built in"]].map(([I, t], i) => {
              const Ic = I as LucideIcon;
              return <li key={i} className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-white/15"><Ic size={18} aria-hidden /></span>{t as string}</li>;
            })}
          </ul>
        </div>
        <p className="relative z-10 text-xs text-blue-100/80">© {new Date().getFullYear()} {brandName}</p>
      </aside>
      <section className="flex flex-col items-center justify-center px-6 py-10">
        <Link to="/" className="mb-8 flex items-center gap-2 text-lg font-bold text-slate-900 lg:hidden"><img src={logo} alt="" className="h-9 w-9" />{brandName}</Link>
        {card}
      </section>
    </main>
  );
}

type FieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "className"> & { label: string; icon?: LucideIcon; error?: string; hint?: string };

/** Labelled input with a leading lucide icon, inline error and (for type=password) a show/hide toggle. Works with react-hook-form's register(). */
export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field({ label, icon: Icon, error, hint, type = "text", required = true, ...rest }, ref) {
  const id = useId();
  const [show, setShow] = useState(false);
  const isPw = type === "password";
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-slate-700">{label}{required && <span aria-hidden className="text-red-500"> *</span>}</label>
      <div className="relative">
        {Icon && <Icon size={18} aria-hidden className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />}
        <input id={id} ref={ref} type={isPw && show ? "text" : type} aria-invalid={!!error} aria-describedby={error ? `${id}-e` : undefined}
          className={`w-full rounded-xl border bg-white py-2.5 text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:ring-4 ${Icon ? "pl-11" : "pl-4"} ${isPw ? "pr-11" : "pr-4"} ${error ? "border-red-400 focus:border-red-500 focus:ring-red-100" : "border-slate-300 focus:border-[var(--brand)] focus:ring-blue-100"}`}
          {...rest} />
        {isPw && <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700">{show ? <EyeOff size={18} /> : <Eye size={18} />}</button>}
      </div>
      {error ? <p id={`${id}-e`} role="alert" className="mt-1 flex items-center gap-1 text-xs text-red-600"><AlertCircle size={13} aria-hidden />{error}</p> : hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
});

export function Notice({ message, ok = false }: { message?: string | null; ok?: boolean }) {
  if (!message) return null;
  const I = ok ? CheckCircle2 : AlertCircle;
  return <p role={ok ? "status" : "alert"} className={`mb-4 flex items-start gap-2 rounded-xl border p-3 text-sm ${ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-red-200 bg-red-50 text-red-700"}`}><I size={18} className="mt-0.5 shrink-0" aria-hidden />{message}</p>;
}

export function SubmitButton({ busy, children, icon: Icon }: { busy?: boolean; children: ReactNode; icon?: LucideIcon }) {
  return (
    <button disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 font-semibold text-white shadow-lg shadow-blue-500/20 transition hover:brightness-110 focus:outline-none focus:ring-4 focus:ring-blue-200 disabled:opacity-60" style={{ background: "linear-gradient(135deg, var(--brand), var(--brand-2))" }}>
      {busy ? <Loader2 size={18} className="animate-spin" aria-hidden /> : Icon && <Icon size={18} aria-hidden />}{children}
    </button>
  );
}

/** Live password-rule checklist (matches the backend policy: 10+ characters, a letter, a number). */
export function PasswordRules({ value = "" }: { value?: string }) {
  const rules: [string, boolean][] = [["At least 10 characters", value.length >= 10], ["Contains a letter", /[A-Za-z]/.test(value)], ["Contains a number", /\d/.test(value)]];
  return <ul className="grid gap-1 text-xs">{rules.map(([t, ok]) => <li key={t} className={`flex items-center gap-1.5 ${ok ? "text-emerald-600" : "text-slate-400"}`}><CheckCircle2 size={14} aria-hidden />{t}</li>)}</ul>;
}
