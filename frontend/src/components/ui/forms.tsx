/** Form building blocks shared by every add / edit dialog: labelled fields with placeholders, password visibility and colour pickers. */
import { Eye, EyeOff, LocateFixed } from "lucide-react";
import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode } from "react";

export interface FieldDef {
  name: string; label: string;
  type?: "text" | "number" | "email" | "password" | "tel" | "url" | "date" | "time" | "datetime-local" | "month" | "textarea" | "select" | "checkbox" | "file" | "color" | "location";
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

/** A colour field: the square opens the system colour picker, the box beside it takes a hex code. */
export function ColorPicker({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const id = useId();
  const valid = /^#[0-9a-f]{6}$/i.test(value);
  return (
    <div>
      <label htmlFor={id} className="field-label">{label}</label>
      <div className="mt-1.5 flex items-center gap-2.5">
        <input type="color" aria-label={`${label} picker`} value={valid ? value : "#0c54cc"} onChange={(e) => onChange(e.target.value)} className="h-12 w-12 shrink-0 cursor-pointer rounded-lg border border-line bg-white p-1" />
        <input id={id} className="w-full !min-h-12 font-mono" value={value} maxLength={7} placeholder={placeholderFor(label)} onChange={(e) => onChange(e.target.value.startsWith("#") ? e.target.value : `#${e.target.value}`)} />
      </div>
    </div>
  );
}

/** "latitude, longitude" -> a pair rounded to what the server stores, or null when it is not a valid point. */
export function parsePoint(value: string): [string, string] | null {
  const m = value.trim().match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
  if (!m || Math.abs(Number(m[1])) > 90 || Math.abs(Number(m[2])) > 180) return null;
  return [Number(m[1]).toFixed(6), Number(m[2]).toFixed(6)];
}

/** A map point: typed or pasted from a map, or taken from this device, with a preview. */
function LocationInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const id = useId();
  const [note, setNote] = useState("");
  const point = parsePoint(value);
  const locate = () => {
    if (!navigator.geolocation) { setNote("This browser cannot share its location."); return; }
    setNote("Finding your location…");
    navigator.geolocation.getCurrentPosition((p) => { onChange(`${p.coords.latitude.toFixed(6)}, ${p.coords.longitude.toFixed(6)}`); setNote(""); }, () => setNote("Your location could not be read. Allow location access, or paste the coordinates."), { enableHighAccuracy: true, timeout: 15000 });
  };
  return (
    <div className="space-y-2 sm:col-span-2">
      <label htmlFor={id} className="field-label">{label}</label>
      <div className="flex flex-wrap gap-2">
        <input id={id} className="min-w-48 flex-1" value={value} placeholder="Enter your latitude, longitude" onChange={(e) => onChange(e.target.value)} />
        <button type="button" className="btn btn-outline" onClick={locate}><LocateFixed size={15} aria-hidden />Use my current location</button>
      </div>
      <p className="text-xs text-muted" role="status">{note || "In Google Maps, right-click the branch to copy its coordinates. Without them, the website map searches for the written address."}</p>
      {point && <iframe title="Location preview" src={`https://maps.google.com/maps?q=${point.join(",")}&z=16&output=embed`} loading="lazy" className="h-52 w-full rounded-xl border border-line" />}
    </div>
  );
}

export function initialValues(fields: FieldDef[]): Values {
  return Object.fromEntries(fields.map((f) => [f.name, f.type === "checkbox" ? (f.defaultValue ? "true" : "") : f.type === "color" ? String(f.defaultValue || "#0c54cc") : String(f.defaultValue ?? "")]));
}

export function FormFields({ fields, values, set, setFile, errors = {} }: { fields: FieldDef[]; values: Values; set: (name: string, v: string) => void; setFile?: (name: string, f: File | null) => void; errors?: Record<string, string> }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {fields.map((f, i) => {
        const required = f.required ?? (f.type !== "checkbox" && f.type !== "file");
        const wide = f.wide ?? (f.type === "textarea" || fields.length === 1);
        const error = errors[f.name];
        const common = { name: f.name, required, autoFocus: i === 0, "aria-invalid": error ? true : undefined, className: "mt-1.5 w-full" };
        if (f.type === "checkbox") {
          return <label key={f.name} className="flex items-start gap-2.5 text-sm sm:col-span-2"><input type="checkbox" className="mt-0.5" checked={values[f.name] === "true"} onChange={(e) => set(f.name, e.target.checked ? "true" : "")} /><span>{f.label}{f.hint && <span className="block text-xs text-muted">{f.hint}</span>}</span></label>;
        }
        if (f.type === "location") return <LocationInput key={f.name} label={f.label} value={values[f.name] ?? ""} onChange={(v) => set(f.name, v)} />;
        if (f.type === "color") return <div key={f.name}><ColorPicker label={f.label} value={values[f.name]} onChange={(v) => set(f.name, v)} />{error && <p role="alert" className="mt-1 text-xs text-danger">{error}</p>}</div>;
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
