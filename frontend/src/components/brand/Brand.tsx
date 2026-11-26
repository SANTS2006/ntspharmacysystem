/** Whose brand is on screen (the platform, or one pharmacy) and the loading animations that carry its logo. */
import { createContext, useContext, type CSSProperties, type ReactNode } from "react";

export interface Brand { name: string; logo: string | null; color: string; color2: string }
export const PLATFORM_BRAND: Brand = { name: "NTS Pharmacy System", logo: "/logo.webp", color: "#047857", color2: "#142d3d" };

const Ctx = createContext<Brand>(PLATFORM_BRAND);
export const useBrand = () => useContext(Ctx);
export function BrandProvider({ brand, children }: { brand: Brand; children: ReactNode }) {
  return <Ctx.Provider value={brand}>{children}</Ctx.Provider>;
}

/** The logo inside two orbiting arcs. A pharmacy without a logo shows its initial instead. */
export function OrbitLogo({ size = 72, brand }: { size?: number; brand?: Brand }) {
  const current = useBrand();
  const b = brand ?? current;
  const style = { width: size, height: size, "--brand": b.color, "--brand-2": b.color2 } as CSSProperties;
  return (
    <span className="orbit" style={style} aria-hidden>
      {b.logo ? <img src={b.logo} alt="" /> : <span className="orbit-mark" style={{ fontSize: size * 0.3 }}>{b.name.slice(0, 1).toUpperCase()}</span>}
    </span>
  );
}

/** Whole-screen loader used while an area of the app starts. */
export function PageLoader({ label, brand }: { label?: string; brand?: Brand }) {
  const current = useBrand();
  const b = brand ?? current;
  return (
    <div role="status" aria-label="Loading" className="grid min-h-screen place-items-center p-6">
      <div className="animate-rise flex flex-col items-center gap-5 text-center" style={{ "--brand": b.color, "--brand-2": b.color2 } as CSSProperties}>
        <OrbitLogo size={104} brand={b} />
        <div><p className="text-lg font-bold">{b.name}</p><p className="mt-1 text-sm text-muted">{label ?? "Loading your workspace…"}</p></div>
        <span className="loader-bar" />
      </div>
    </div>
  );
}

/** Loader for a page section, panel or component: logo plus shimmering placeholder rows. */
export function Loading({ rows = 4, label = "Loading…" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label="Loading" className="animate-fade space-y-3 py-3">
      <div className="flex items-center gap-3"><OrbitLogo size={44} /><span className="text-sm font-medium text-muted">{label}</span></div>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton h-11 w-full" style={{ opacity: 1 - i * 0.14 }} />)}
    </div>
  );
}

/** Table-shaped placeholder so the layout does not jump when rows arrive. */
export function TableLoader({ columns = 5, rows = 6 }: { columns?: number; rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="table-wrap animate-fade">
      <div className="absolute inset-0 z-10 grid place-items-center"><OrbitLogo size={64} /></div>
      <table className="table opacity-50" aria-hidden>
        <thead><tr>{Array.from({ length: columns }, (_, i) => <th key={i}><div className="skeleton h-3 w-20" /></th>)}</tr></thead>
        <tbody>{Array.from({ length: rows }, (_, r) => <tr key={r}>{Array.from({ length: columns }, (_, c) => <td key={c}><div className="skeleton h-4" style={{ width: `${55 + ((r + c) % 4) * 12}%` }} /></td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

/** Small inline spinner for buttons and tight spaces. */
export const Spinner = ({ size = 16 }: { size?: number }) => (
  <span aria-hidden className="inline-block shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent" style={{ width: size, height: size }} />
);
