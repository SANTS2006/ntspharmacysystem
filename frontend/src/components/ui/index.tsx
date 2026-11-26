/** Shared UI primitives for NTS Pharmacy System. Presentational only: no data fetching happens here. */
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Inbox, Info, X, XCircle, type LucideIcon } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Skeleton placeholder announced to screen readers as "Loading". */
export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="space-y-3 py-2">
      <span className="sr-only">Loading…</span>
      <div className="skeleton h-7 w-48" />
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton h-11 w-full" />)}
    </div>
  );
}

export function EmptyState({ children, icon: Icon = Inbox, action }: { children: ReactNode; icon?: LucideIcon; action?: ReactNode }) {
  return (
    <div className="empty">
      <span className="grid h-11 w-11 place-items-center rounded-full bg-slate-100 text-slate-400"><Icon size={20} aria-hidden /></span>
      <div>{children}</div>
      {action}
    </div>
  );
}

export function ErrorState({ children, onRetry }: { children: ReactNode; onRetry?: () => void }) {
  return (
    <div role="alert" className="alert alert-error items-center justify-between">
      <span className="flex items-center gap-2"><XCircle size={18} aria-hidden />{children}</span>
      {onRetry && <button className="btn btn-outline btn-sm" onClick={onRetry}>Try again</button>}
    </div>
  );
}

const TONES: Record<string, string[]> = {
  success: ["active", "available", "approved", "paid", "completed", "delivered", "dispensed", "succeeded", "success", "received", "verified", "posted", "confirmed", "payment_confirmed", "open", "resolved", "present"],
  warning: ["pending", "invited", "partially_paid", "partially_received", "partially_dispensed", "under_review", "pending_approval", "awaiting_payment", "awaiting_prescription", "quarantined", "draft", "submitted", "low_stock", "late", "unpaid", "initiated", "processing", "preparing", "trial"],
  danger: ["rejected", "cancelled", "canceled", "expired", "failed", "recalled", "suspended", "deactivated", "inactive", "void", "voided", "damaged", "terminated", "overdue", "absent", "out_of_stock"],
  info: ["issued", "ready_for_pickup", "out_for_delivery", "prescription_approved", "assigned", "picked_up", "scheduled", "new", "refunded", "partially_refunded", "closed", "archived", "in_progress"],
};
export function statusTone(status: string): "success" | "warning" | "danger" | "info" | "neutral" {
  const key = status.toLowerCase().trim().replace(/[\s-]+/g, "_");
  for (const [tone, list] of Object.entries(TONES)) if (list.includes(key)) return tone as "success";
  return "neutral";
}
export function StatusBadge({ status, tone }: { status: string; tone?: ReturnType<typeof statusTone> }) {
  return <span className={`badge badge-${tone ?? statusTone(status)}`}>{status.replace(/_/g, " ")}</span>;
}

export function Pagination({ page, setPage, hasPrev, hasNext, total }: { page: number; setPage: (n: number) => void; hasPrev: boolean; hasNext: boolean; total?: number }) {
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm text-slate-500">Page {page}{total !== undefined ? ` · ${total.toLocaleString()} records` : ""}</p>
      <div className="flex gap-2">
        <button type="button" disabled={!hasPrev} onClick={() => setPage(page - 1)} className="btn btn-outline btn-sm"><ChevronLeft size={15} aria-hidden />Previous</button>
        <button type="button" disabled={!hasNext} onClick={() => setPage(page + 1)} className="btn btn-outline btn-sm">Next<ChevronRight size={15} aria-hidden /></button>
      </div>
    </nav>
  );
}

export function StatCard({ label, value, icon: Icon, tone = "primary", hint }: { label: string; value: ReactNode; icon?: LucideIcon; tone?: "primary" | "info" | "warning" | "danger" | "navy"; hint?: ReactNode }) {
  const tones = { primary: "bg-teal-50 text-teal-700", info: "bg-sky-50 text-sky-700", warning: "bg-amber-50 text-amber-700", danger: "bg-red-50 text-red-700", navy: "bg-slate-100 text-navy" };
  return (
    <div className="card flex items-start justify-between gap-3 p-4">
      <div className="min-w-0">
        <p className="text-[0.8125rem] font-medium text-muted">{label}</p>
        <p className="mt-1 truncate text-2xl font-bold tabular-nums text-ink">{value}</p>
        {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      </div>
      {Icon && <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg ${tones[tone]}`}><Icon size={19} aria-hidden /></span>}
    </div>
  );
}

/** Horizontal bar chart for real values returned by the API (no chart dependency). */
export function BarList({ items, format = (n) => n.toLocaleString(), empty = "No data for this period." }: { items: { label: string; value: number; note?: string }[]; format?: (n: number) => string; empty?: string }) {
  if (items.length === 0) return <p className="py-6 text-center text-sm text-muted">{empty}</p>;
  const max = Math.max(...items.map((i) => Math.abs(i.value)), 1);
  return (
    <ul className="space-y-3">
      {items.map((i) => (
        <li key={i.label}>
          <div className="mb-1 flex justify-between gap-3 text-sm"><span className="truncate capitalize text-slate-700">{i.label.replace(/_/g, " ")}</span><span className="font-semibold tabular-nums">{format(i.value)}{i.note && <span className="ml-2 font-normal text-muted">{i.note}</span>}</span></div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${Math.max((Math.abs(i.value) / max) * 100, i.value ? 3 : 0)}%` }} /></div>
        </li>
      ))}
    </ul>
  );
}

export function Modal({ title, onClose, children, footer, size = "md" }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; size?: "md" | "lg" }) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
      if (e.key === "Tab" && ref.current) { // keep keyboard focus inside the dialog
        const f = [...ref.current.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter((el) => !el.hasAttribute("disabled"));
        if (!f.length) return;
        if (e.shiftKey && (document.activeElement === f[0] || document.activeElement === ref.current)) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; prev?.focus(); };
  }, []);
  return (
    <div className="animate-fade fixed inset-0 z-[80] grid place-items-end bg-slate-900/50 p-0 sm:place-items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} className={`animate-pop flex max-h-[90vh] w-full flex-col rounded-t-2xl bg-white shadow-pop outline-none sm:rounded-2xl ${size === "lg" ? "sm:max-w-3xl" : "sm:max-w-md"}`}>
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5"><h2 className="section-title">{title}</h2><button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><X size={18} /></button></header>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</footer>}
      </div>
    </div>
  );
}

// ---------- confirmation dialogs and toasts ----------
interface ConfirmOptions { title: string; message?: ReactNode; confirmLabel?: string; danger?: boolean }
export interface PromptField { name: string; label: string; type?: "text" | "number" | "email" | "textarea" | "select"; options?: [string, string][]; defaultValue?: string; required?: boolean; placeholder?: string; min?: number; max?: number; step?: string }
interface PromptOptions { title: string; message?: ReactNode; fields: PromptField[]; confirmLabel?: string; danger?: boolean }
type Answers = Record<string, string>;
type Toast = { id: number; text: string; kind: "success" | "error" | "info" };
interface Feedback { prompt: (o: PromptOptions) => Promise<Answers | null>; confirm: (o: ConfirmOptions) => Promise<boolean>; toast: (text: string, kind?: Toast["kind"]) => void }

// Safe defaults keep components usable in isolation (tests): confirm falls back to the browser dialog.
const FeedbackCtx = createContext<Feedback>({ prompt: async () => null, confirm: async (o) => window.confirm(o.title), toast: () => {} });
export const useConfirm = () => useContext(FeedbackCtx).confirm;
export const usePrompt = () => useContext(FeedbackCtx).prompt;
export const useToast = () => useContext(FeedbackCtx).toast;

/** A small form in a dialog: replaces chains of window.prompt() with labelled, validated fields. */
function PromptDialog({ options, onDone }: { options: PromptOptions; onDone: (v: Answers | null) => void }) {
  const [values, setValues] = useState<Answers>(() => Object.fromEntries(options.fields.map((f) => [f.name, f.defaultValue ?? ""])));
  return (
    <Modal title={options.title} onClose={() => onDone(null)}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); onDone(values); }}>
        {options.message && <div className="text-sm text-slate-600">{options.message}</div>}
        {options.fields.map((f, i) => {
          const common = { required: f.required ?? true, value: values[f.name], placeholder: f.placeholder, autoFocus: i === 0, className: "mt-1 w-full p-2", onChange: (e: { target: { value: string } }) => setValues((v) => ({ ...v, [f.name]: e.target.value })) };
          return (
            <label key={f.name} className="field-label">{f.label}
              {f.type === "select" ? <select {...common}>{f.options?.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
                : f.type === "textarea" ? <textarea {...common} rows={3} />
                  : <input {...common} type={f.type ?? "text"} min={f.min} max={f.max} step={f.step} />}
            </label>);
        })}
        <div className="flex justify-end gap-2 pt-2"><button type="button" className="btn btn-outline" onClick={() => onDone(null)}>Cancel</button><button type="submit" className={`btn ${options.danger ? "btn-danger" : "btn-primary"}`}>{options.confirmLabel ?? "Continue"}</button></div>
      </form>
    </Modal>
  );
}

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<(ConfirmOptions & { resolve: (v: boolean) => void }) | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [asking, setAsking] = useState<(PromptOptions & { resolve: (v: Answers | null) => void; key: number }) | null>(null);
  const nextId = useRef(0);
  const confirm = useCallback((o: ConfirmOptions) => new Promise<boolean>((resolve) => setPending({ ...o, resolve })), []);
  const prompt = useCallback((o: PromptOptions) => new Promise<Answers | null>((resolve) => setAsking({ ...o, resolve, key: ++nextId.current })), []);
  const toast = useCallback((text: string, kind: Toast["kind"] = "success") => {
    const id = ++nextId.current;
    setToasts((t) => [...t.slice(-3), { id, text, kind }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 7000 : 4000);
  }, []);
  const answer = (v: boolean) => { pending?.resolve(v); setPending(null); };
  return (
    <FeedbackCtx.Provider value={{ prompt, confirm, toast }}>
      {children}
      {asking && <PromptDialog key={asking.key} options={asking} onDone={(v) => { const done = asking.resolve; setAsking(null); done(v); }} />}
      {pending && (
        <Modal title={pending.title} onClose={() => answer(false)} footer={<>
          <button className="btn btn-outline" onClick={() => answer(false)}>Cancel</button>
          <button className={`btn ${pending.danger ? "btn-danger" : "btn-primary"}`} onClick={() => answer(true)}>{pending.confirmLabel ?? "Confirm"}</button></>}>
          <div className="flex gap-3">
            <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${pending.danger ? "bg-red-50 text-red-600" : "bg-amber-50 text-amber-600"}`}><AlertTriangle size={20} aria-hidden /></span>
            <div className="text-sm text-slate-600">{pending.message ?? "Please confirm that you want to continue."}</div>
          </div>
        </Modal>
      )}
      <div aria-live="polite" className="pointer-events-none fixed right-4 top-4 z-[90] flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((t) => {
          const I = t.kind === "success" ? CheckCircle2 : t.kind === "error" ? XCircle : Info;
          return (
            <div key={t.id} className="animate-pop pointer-events-auto flex items-start gap-2.5 rounded-xl border border-line bg-white p-3 text-sm shadow-pop">
              <I size={18} aria-hidden className={t.kind === "success" ? "text-success" : t.kind === "error" ? "text-danger" : "text-info"} />
              <span className="flex-1">{t.text}</span>
              <button aria-label="Dismiss notification" className="text-slate-400 hover:text-slate-700" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}><X size={15} /></button>
            </div>
          );
        })}
      </div>
    </FeedbackCtx.Provider>
  );
}
