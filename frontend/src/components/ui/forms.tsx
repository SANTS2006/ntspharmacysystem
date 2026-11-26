/** Form building blocks shared by every add / edit dialog: labelled fields with placeholders, password visibility and colour pickers. */
import { Eye, EyeOff, Pipette, Wand2 } from "lucide-react";
import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode } from "react";

export interface FieldDef {
  name: string; label: string;
  type?: "text" | "number" | "email" | "password" | "tel" | "url" | "date" | "time" | "datetime-local" | "month" | "textarea" | "select" | "checkbox" | "file" | "color";
  options?: [string, string][]; defaultValue?: string | number | boolean | null; required?: boolean; placeholder?: string; hint?: ReactNode;
  min?: number | string; max?: number | string; step?: string; maxLength?: number; minLength?: number; accept?: string; wide?: boolean; autoComplete?: string;
}
export type Values = Record<string, string>;

/** "Batch number (optional)" -> "Enter your batch number". */
export function placeholderFor(label: string): string {
  const clean = label.replace(/\(.*?\)/g, "").replace(/[*:?]/g, "").trim();
  const words = clean.split(/\s+/).map((w) => (/^[A-Z0-9]{2,}$/.test(w) ? w : w.toLowerCase())).join(" ");
  return `Enter your ${words}`;
}

type PwProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;
export const PasswordInput = forwardRef<HTMLInputElement, PwProps>(function PasswordInput({ className = "", placeholder = "Enter your password", ...rest }, ref) {
  const [show, setShow] = useState(false);
  return (
    <span className="relative block">
      <input ref={ref} {...rest} placeholder={placeholder} type={show ? "text" : "password"} className={`w-full !pr-11 ${className}`} />
      <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}
        className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800">
        {show ? <EyeOff size={17} aria-hidden /> : <Eye size={17} aria-hidden />}
      </button>
    </span>
  );
});

const SWATCHES = ["#047857", "#0f766e", "#0369a1", "#015dc9", "#4338ca", "#7c3aed", "#be185d", "#b91c1c", "#c2410c", "#a16207", "#142d3d", "#334155"];

/** The most common distinct, non-white colours of an uploaded logo. */
export async function colorsFromImage(source: Blob, count = 5): Promise<string[]> {
  const bitmap = await createImageBitmap(source);
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext("2d");
  if (!ctx) return [];
  ctx.drawImage(bitmap, 0, 0, 64, 64);
  const buckets = new Map<string, { n: number; r: number; g: number; b: number }>();
  const px = ctx.getImageData(0, 0, 64, 64).data;
  for (let i = 0; i < px.length; i += 4) {
    const [r, g, b, a] = [px[i], px[i + 1], px[i + 2], px[i + 3]];
    if (a < 200 || (r > 235 && g > 235 && b > 235)) continue;
    const key = `${r >> 5}-${g >> 5}-${b >> 5}`;
    const e = buckets.get(key) ?? { n: 0, r: 0, g: 0, b: 0 };
    e.n++; e.r += r; e.g += g; e.b += b;
    buckets.set(key, e);
  }
  const hex = (v: number) => Math.round(v).toString(16).padStart(2, "0");
  return [...buckets.values()].sort((x, y) => y.n - x.n).slice(0, count).map((e) => `#${hex(e.r / e.n)}${hex(e.g / e.n)}${hex(e.b / e.n)}`);
}

/** Visual colour picker: spectrum picker, preset swatches, colours taken from the logo, screen eyedropper and a hex box. */
export function ColorPicker({ label, value, onChange, logo }: { label: string; value: string; onChange: (v: string) => void; logo?: Blob | null }) {
  const id = useId();
  const [fromLogo, setFromLogo] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const valid = /^#[0-9a-f]{6}$/i.test(value);
  const Dropper = (window as unknown as { EyeDropper?: new () => { open: () => Promise<{ sRGBHex: string }> } }).EyeDropper;
  const pick = (list: string[]) => list.map((c) => (
    <button key={c} type="button" onClick={() => onChange(c)} aria-label={`Use ${c}`} title={c} className={`h-7 w-7 rounded-full border-2 transition hover:scale-110 ${value.toLowerCase() === c.toLowerCase() ? "border-slate-900" : "border-transparent"}`} style={{ background: c }} />
  ));
  return (
    <fieldset className="rounded-xl border border-line p-3">
      <legend className="px-1 text-[0.8125rem] font-semibold">{label}</legend>
      <div className="flex items-center gap-3">
        <label className="relative h-14 w-14 shrink-0 cursor-pointer overflow-hidden rounded-xl border border-line shadow-sm" style={{ background: valid ? value : "#ffffff" }} title="Open the colour picker">
          <input type="color" aria-label={`${label} picker`} value={valid ? value : "#047857"} onChange={(e) => onChange(e.target.value)} className="absolute inset-0 h-full w-full cursor-pointer opacity-0" />
        </label>
        <div className="min-w-0 flex-1">
          <label htmlFor={id} className="sr-only">{label} hex code</label>
          <input id={id} className="w-full font-mono uppercase" value={value} maxLength={7} placeholder={placeholderFor(label)} onChange={(e) => onChange(e.target.value.startsWith("#") ? e.target.value : `#${e.target.value}`)} />
          <div className="mt-2 flex flex-wrap gap-2">
            {Dropper && <button type="button" className="btn btn-outline btn-sm" onClick={() => new Dropper().open().then((r) => onChange(r.sRGBHex)).catch(() => {})}><Pipette size={14} aria-hidden />Pick from screen</button>}
            {logo && <button type="button" className="btn btn-outline btn-sm" onClick={() => colorsFromImage(logo).then((c) => { setFromLogo(c); setNote(c.length ? "" : "No colours found in this image."); }).catch(() => setNote("This image could not be read."))}><Wand2 size={14} aria-hidden />Colours from logo</button>}
          </div>
        </div>
      </div>
      {fromLogo.length > 0 && <div className="mt-3 flex flex-wrap items-center gap-2"><span className="text-xs text-muted">From logo:</span>{pick(fromLogo)}</div>}
      {note && <p className="mt-2 text-xs text-muted">{note}</p>}
      <div className="mt-3 flex flex-wrap gap-2">{pick(SWATCHES)}</div>
    </fieldset>
  );
}

export function initialValues(fields: FieldDef[]): Values {
  return Object.fromEntries(fields.map((f) => [f.name, f.type === "checkbox" ? (f.defaultValue ? "true" : "") : f.type === "color" ? String(f.defaultValue || "#047857") : String(f.defaultValue ?? "")]));
}

export function FormFields({ fields, values, set, setFile, errors = {} }: { fields: FieldDef[]; values: Values; set: (name: string, v: string) => void; setFile?: (name: string, f: File | null) => void; errors?: Record<string, string> }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {fields.map((f, i) => {
        const required = f.required ?? (f.type !== "checkbox" && f.type !== "file");
        const wide = f.wide ?? (f.type === "textarea" || f.type === "color" || fields.length === 1);
        const error = errors[f.name];
        const common = { name: f.name, required, autoFocus: i === 0, "aria-invalid": error ? true : undefined, className: "mt-1.5 w-full" };
        if (f.type === "checkbox") {
          return <label key={f.name} className="flex items-start gap-2.5 text-sm sm:col-span-2"><input type="checkbox" className="mt-0.5" checked={values[f.name] === "true"} onChange={(e) => set(f.name, e.target.checked ? "true" : "")} /><span>{f.label}{f.hint && <span className="block text-xs text-muted">{f.hint}</span>}</span></label>;
        }
        if (f.type === "color") return <div key={f.name} className="sm:col-span-2"><ColorPicker label={f.label} value={values[f.name]} onChange={(v) => set(f.name, v)} />{error && <p role="alert" className="mt-1 text-xs text-danger">{error}</p>}</div>;
        const placeholder = f.placeholder ?? placeholderFor(f.label);
        const text = { ...common, value: values[f.name] ?? "", placeholder, maxLength: f.maxLength, minLength: f.minLength, onChange: (e: { target: { value: string } }) => set(f.name, e.target.value) };
        return (
          <label key={f.name} className={`field-label ${wide ? "sm:col-span-2" : ""}`}>
            {f.label}{required && <span aria-hidden className="text-danger"> *</span>}
            {f.type === "select" ? (
              <select {...common} value={values[f.name] ?? ""} onChange={(e) => set(f.name, e.target.value)}>
                {!f.options?.some(([v]) => v === "") && <option value="">{`Select your ${placeholder.replace(/^Enter your /, "")}`}</option>}
                {f.options?.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            ) : f.type === "textarea" ? <textarea {...text} rows={3} />
              : f.type === "password" ? <PasswordInput {...text} className="" autoComplete={f.autoComplete ?? "new-password"} />
                : f.type === "file" ? <input {...common} type="file" accept={f.accept} onChange={(e) => setFile?.(f.name, e.target.files?.[0] ?? null)} />
                  : <input {...text} type={f.type ?? "text"} min={f.min} max={f.max} step={f.step ?? (f.type === "number" ? "any" : undefined)} autoComplete={f.autoComplete} />}
            {error ? <span role="alert" className="mt-1 block text-xs font-normal text-danger">{error}</span> : f.hint && <span className="mt-1 block text-xs font-normal text-muted">{f.hint}</span>}
          </label>
        );
      })}
    </div>
  );
}
