import { AlertCircle, ArrowLeft, CheckCircle2, ShieldCheck, Boxes, HeartPulse, Pill, type LucideIcon } from "lucide-react";
import { forwardRef, useEffect, useId, type CSSProperties, type InputHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { readableOn } from "../../lib/format";
import { PLATFORM_BRAND, Spinner, type Brand } from "../brand/Brand";
import { ThemeToggle } from "../layout/AppShell";
import { Scene3D } from "../three/Scene3D";
import { PasswordInput, placeholderFor } from "../ui/forms";

const POINTS: [LucideIcon, string][] = [[ShieldCheck, "Role-based access and a full audit trail"], [Pill, "Pharmacist-approved prescriptions and safe dispensing"], [Boxes, "Batch and expiry tracking across every branch"], [HeartPulse, "Online orders and customer care, built in"]];

/** Split-screen sign-in family: an animated brand panel beside a focused form card. */
export function AuthShell({ title, subtitle, icon: Icon, children, footer, brand = PLATFORM_BRAND, headline = "Run your pharmacy with confidence.", blurb = "Inventory, prescriptions, point of sale and finance in one secure, multi-branch platform.", points = POINTS, back }: {
  title: string; subtitle?: string; icon: LucideIcon; children: ReactNode; footer?: ReactNode; brand?: Brand; headline?: string; blurb?: string; points?: [LucideIcon, string][]; back?: { to: string; label: string };
}) {
  useEffect(() => {
    const root = document.documentElement.style;
    root.setProperty("--brand", brand.color); root.setProperty("--brand-2", brand.color2); root.setProperty("--on-brand", readableOn(brand.color));
    document.title = `${title} · ${brand.name}`;
    return () => { ["--brand", "--brand-2", "--on-brand"].forEach((p) => root.removeProperty(p)); };
  }, [brand.color, brand.color2, brand.name, title]);
  const logo = (cls: string) => brand.logo ? <img src={brand.logo} alt="" className={`${cls} rounded-xl bg-[#fff] object-contain p-1`} /> : <span className={`${cls} grid place-items-center rounded-xl bg-[#fff] text-lg font-black`} style={{ color: "#0b1324" }}>{brand.name[0]}</span>;
  return (
    <main className="grid min-h-screen bg-canvas lg:grid-cols-[1.1fr_1fr]" style={{ "--brand": brand.color, "--brand-2": brand.color2 } as CSSProperties}>
      <aside className="hero-surface relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-12">
        <Scene3D color={brand.color} color2={brand.color2} className="absolute inset-0 opacity-80" />
        <div className="pointer-events-none absolute inset-0" style={{ background: "linear-gradient(90deg, rgb(4 12 20 / .82) 0%, rgb(4 12 20 / .35) 60%, transparent 100%)" }} aria-hidden />
        <Link to="/" className="relative z-10 flex items-center gap-3 text-xl font-bold">{logo("h-12 w-12")}{brand.name}</Link>
        <div className="animate-rise relative z-10 max-w-md">
          <h2 className="text-4xl font-extrabold leading-tight">{headline}</h2>
          <p className="mt-4 text-white/80">{blurb}</p>
          <ul className="mt-8 space-y-3 text-sm">
            {points.map(([I, text]) => <li key={text} className="glass flex items-center gap-3 rounded-2xl p-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/15"><I size={18} aria-hidden /></span>{text}</li>)}
          </ul>
        </div>
        <p className="relative z-10 text-xs text-white/60">© {new Date().getFullYear()} {brand.name}</p>
      </aside>
      <section className="relative flex flex-col items-center justify-center px-4 py-16 sm:px-8">
        <div className="absolute inset-x-4 top-4 flex items-center justify-between sm:inset-x-8">
          {back ? <Link to={back.to} className="btn btn-outline btn-sm"><ArrowLeft size={15} aria-hidden />{back.label}</Link> : <span />}
          <ThemeToggle />
        </div>
        <Link to="/" className="mb-6 flex items-center gap-2.5 text-lg font-bold lg:hidden">{logo("h-11 w-11 border border-line")}{brand.name}</Link>
        <div className="card animate-pop w-full max-w-md overflow-hidden !rounded-3xl !shadow-pop">
          <div className="h-1.5" style={{ background: "linear-gradient(90deg, var(--brand), var(--brand-2))" }} />
          <div className="p-6 sm:p-9">
            <div className="mb-6">
              <span className="mb-4 grid h-14 w-14 place-items-center rounded-2xl shadow-lg" style={{ background: "linear-gradient(135deg, var(--brand), var(--brand-2))", color: "#fff" }}><Icon size={26} aria-hidden /></span>
              <h1 className="text-2xl font-extrabold tracking-tight">{title}</h1>
              {subtitle && <p className="mt-1.5 text-sm text-muted">{subtitle}</p>}
            </div>
            {children}
            {footer && <div className="mt-6 border-t border-line pt-5 text-center text-sm text-muted">{footer}</div>}
          </div>
        </div>
      </section>
    </main>
  );
}

type FieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "className"> & { label: string; icon?: LucideIcon; error?: string; hint?: string };

/** Labelled input with a leading icon, inline error and (for passwords) a show/hide toggle. Works with react-hook-form's register(). */
export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field({ label, icon: Icon, error, hint, type = "text", required = true, placeholder, ...rest }, ref) {
  const id = useId();
  const common = { id, ref, required: undefined, "aria-required": required, "aria-invalid": !!error, "aria-describedby": error ? `${id}-e` : undefined, placeholder: placeholder ?? placeholderFor(label), ...rest };
  const cls = `w-full !min-h-12 !rounded-xl ${Icon ? "!pl-11" : ""}`;
  return (
    <div>
      <label htmlFor={id} className="field-label mb-1.5">{label}{required && <span aria-hidden className="text-danger"> *</span>}</label>
      <div className="relative">
        {Icon && <Icon size={18} aria-hidden className="pointer-events-none absolute left-3.5 top-1/2 z-10 -translate-y-1/2 text-slate-400" />}
        {type === "password" ? <PasswordInput {...common} className={cls} /> : <input {...common} type={type} className={cls} />}
      </div>
      {error ? <p id={`${id}-e`} role="alert" className="mt-1 flex items-center gap-1 text-xs text-danger"><AlertCircle size={13} aria-hidden />{error}</p> : hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
});

export function Notice({ message, ok = false }: { message?: string | null; ok?: boolean }) {
  if (!message) return null;
  const I = ok ? CheckCircle2 : AlertCircle;
  return <p role={ok ? "status" : "alert"} className={`alert mb-4 ${ok ? "alert-success" : "alert-error"}`}><I size={18} className="mt-0.5 shrink-0" aria-hidden />{message}</p>;
}

export function SubmitButton({ busy, children, icon: Icon }: { busy?: boolean; children: ReactNode; icon?: LucideIcon }) {
  return <button disabled={busy} className="btn btn-primary !min-h-12 w-full !rounded-xl !text-[0.95rem]">{busy ? <Spinner size={18} /> : Icon && <Icon size={18} aria-hidden />}{children}</button>;
}

/** Live password-rule checklist (matches the backend policy: 10+ characters, a letter, a number). */
export function PasswordRules({ value = "" }: { value?: string }) {
  const rules: [string, boolean][] = [["At least 10 characters", value.length >= 10], ["Contains a letter", /[A-Za-z]/.test(value)], ["Contains a number", /\d/.test(value)]];
  return <ul className="grid gap-1 text-xs">{rules.map(([t, ok]) => <li key={t} className={`flex items-center gap-1.5 ${ok ? "text-success" : "text-muted"}`}><CheckCircle2 size={14} aria-hidden />{t}</li>)}</ul>;
}
