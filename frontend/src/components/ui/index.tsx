/** Shared UI primitives for NTS Pharmacy System. Presentational only: no data fetching happens here. */
import { AlertTriangle, CheckCircle2, Inbox, Info, Trash2, X, XCircle, type LucideIcon } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { Spinner } from "../brand/Brand";
import { FormFields, initialValues, type FieldDef, type Values } from "./forms";

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

export { Loading, TableLoader, PageLoader, Spinner } from "../brand/Brand";
export * from "./forms";
export * from "./data";

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

export function StatCard({ label, value, icon: Icon, tone = "primary", hint, to }: { label: string; value: ReactNode; icon?: LucideIcon; tone?: "primary" | "info" | "warning" | "danger" | "navy"; hint?: ReactNode; to?: string }) {
  const tones = { primary: "bg-teal-50 text-teal-700", info: "bg-sky-50 text-sky-700", warning: "bg-amber-50 text-amber-700", danger: "bg-red-50 text-red-700", navy: "bg-slate-100 text-slate-700" };
  const body = (
    <>
      <div className="min-w-0">
        <p className="text-[0.8125rem] font-semibold text-muted">{label}</p>
        <p className="mt-1 truncate text-[1.65rem] font-bold leading-tight text-ink">{value}</p>
        {hint && <p className="mt-1.5 text-xs text-muted">{hint}</p>}
      </div>
      {Icon && <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${tones[tone]}`}><Icon size={20} aria-hidden /></span>}
    </>
  );
  const cls = "card card-hover animate-rise flex items-start justify-between gap-3 p-4";
  return to ? <Link to={to} className={cls}>{body}</Link> : <div className={cls}>{body}</div>;
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
  return createPortal(
    <div className="backdrop animate-fade fixed inset-0 z-[80] grid place-items-end p-0 sm:place-items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} className={`animate-pop flex max-h-[92vh] w-full flex-col border border-line rounded-t-2xl bg-white shadow-pop outline-none sm:rounded-2xl ${size === "lg" ? "sm:max-w-3xl" : "sm:max-w-md"}`}>
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5"><h2 className="section-title">{title}</h2><button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><X size={18} /></button></header>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</footer>}
      </div>
    </div>, document.body);
}

// ---------- form dialogs ----------
const apiErrors = (e: unknown): { message: string; fields: Record<string, string> } => {
  if (e instanceof ApiError) {
    const fields: Record<string, string> = {};
    const d = e.details;
    if (d && typeof d === "object" && !Array.isArray(d)) for (const [k, v] of Object.entries(d)) fields[k] = Array.isArray(v) ? v.join(" ") : typeof v === "string" ? v : JSON.stringify(v);
    return { message: e.message, fields };
  }
  return { message: e instanceof Error ? e.message : "Something went wrong. Please try again.", fields: {} };
};
const sentence = (message: string, fields: Record<string, string>) => {
  const extra = Object.entries(fields).map(([k, v]) => (["detail", "non_field_errors"].includes(k) ? v : `${k.replace(/_/g, " ")}: ${v}`)).join(" ");
  return extra && !message.includes(extra) ? `${message} ${extra}` : message;
};
/** One readable sentence for any API error. */
export const errorMessage = (e: unknown): string => { const { message, fields } = apiErrors(e); return sentence(message, fields); };

/** Add / edit dialog. `onSubmit` may call the API: errors are shown inside the dialog and it only closes on success. */
export function FormModal({ title, description, fields, submitLabel = "Save", danger, size, onSubmit, onClose, children }: {
  title: string; description?: ReactNode; fields: FieldDef[]; submitLabel?: string; danger?: boolean; size?: "md" | "lg";
  onSubmit: (values: Values, files: Record<string, File | null>) => unknown; onClose: () => void; children?: ReactNode;
}) {
  const [values, setValues] = useState<Values>(() => initialValues(fields));
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ message: string; fields: Record<string, string> } | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setFailure(null);
    try { await onSubmit(values, files); onClose(); }
    catch (err) { setFailure(apiErrors(err)); setBusy(false); }
  };
  const unplaced = Object.fromEntries(Object.entries(failure?.fields ?? {}).filter(([k]) => !fields.some((f) => f.name === k)));
  return (
    <Modal title={title} onClose={onClose} size={size ?? (fields.length > 4 ? "lg" : "md")}>
      <form onSubmit={submit} className="space-y-4">
        {description && <div className="text-sm text-muted">{description}</div>}
        {failure && <p role="alert" className="alert alert-error">{sentence(failure.message, unplaced)}</p>}
        <FormFields fields={fields} values={values} errors={failure?.fields} set={(n, v) => setValues((x) => ({ ...x, [n]: v }))} setFile={(n, f) => setFiles((x) => ({ ...x, [n]: f }))} />
        {children}
        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy} className={`btn ${danger ? "btn-danger" : "btn-primary"}`}>{busy && <Spinner />}{busy ? "Saving…" : submitLabel}</button>
        </div>
      </form>
    </Modal>
  );
}

// ---------- confirmation dialogs and toasts ----------
interface ConfirmOptions { title: string; message?: ReactNode; confirmLabel?: string; danger?: boolean }
export type PromptField = FieldDef;
interface PromptOptions { title: string; message?: ReactNode; fields: PromptField[]; confirmLabel?: string; danger?: boolean }
type Answers = Values;
type Toast = { id: number; text: string; kind: "success" | "error" | "info" };
interface Feedback { prompt: (o: PromptOptions) => Promise<Answers | null>; confirm: (o: ConfirmOptions) => Promise<boolean>; toast: (text: string, kind?: Toast["kind"]) => void }

// Safe defaults keep components usable in isolation (tests): confirm falls back to the browser dialog.
const FeedbackCtx = createContext<Feedback>({ prompt: async () => null, confirm: async (o) => window.confirm(o.title), toast: () => {} });
export const useConfirm = () => useContext(FeedbackCtx).confirm;
export const usePrompt = () => useContext(FeedbackCtx).prompt;
export const useToast = () => useContext(FeedbackCtx).toast;

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
      {asking && <FormModal key={asking.key} title={asking.title} description={asking.message} fields={asking.fields} submitLabel={asking.confirmLabel ?? "Continue"} danger={asking.danger}
        onSubmit={(v) => { asking.resolve(v); }} onClose={() => { asking.resolve(null); setAsking(null); }} />}
      {pending && (
        <Modal title={pending.title} onClose={() => answer(false)} footer={<>
          <button className="btn btn-outline" onClick={() => answer(false)}>Cancel</button>
          <button className={`btn ${pending.danger ? "btn-danger" : "btn-primary"}`} onClick={() => answer(true)}>{pending.confirmLabel ?? "Confirm"}</button></>}>
          <div className="flex gap-3">
            <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${pending.danger ? "bg-red-50 text-red-600" : "bg-amber-50 text-amber-600"}`}>{/delete|remove/i.test(pending.title) ? <Trash2 size={20} aria-hidden /> : <AlertTriangle size={20} aria-hidden />}</span>
            <div className="text-sm text-slate-600">{pending.message ?? "Please confirm that you want to continue."}</div>
          </div>
        </Modal>
      )}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-[130] flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((t) => {
          const I = t.kind === "success" ? CheckCircle2 : t.kind === "error" ? XCircle : Info;
          return (
            <div key={t.id} className="animate-pop pointer-events-auto flex items-start gap-2.5 rounded-xl border border-line bg-white p-3 text-sm text-ink shadow-pop">
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
