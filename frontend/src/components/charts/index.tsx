/** Small, dependency-free SVG charts. Colours come from the validated series tokens (light and dark have their own steps),
 *  text uses ink tokens, every chart has hover values and a table view, and a legend appears when there are two or more series. */
import { BarChart3, Table2 } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { compact } from "../../lib/format";

export const seriesColor = (i: number) => `var(--series-${(i % 8) + 1})`;
type Fmt = (n: number) => string;
const plain: Fmt = (n) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });

export interface TableData { head: string[]; rows: (string | number)[][] }

export function ChartCard({ title, subtitle, table, legend, actions, children, className = "" }: { title: string; subtitle?: ReactNode; table?: TableData; legend?: { label: string; color: string }[]; actions?: ReactNode; children: ReactNode; className?: string }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className={`card animate-rise flex min-w-0 flex-col p-5 ${className}`}>
      <header className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div><h2 className="section-title">{title}</h2>{subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}</div>
        <div className="flex flex-wrap items-center gap-3">
          {legend && legend.length > 1 && <ul className="flex flex-wrap gap-3 text-xs text-muted">{legend.map((l) => <li key={l.label} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: l.color }} aria-hidden />{l.label}</li>)}</ul>}
          {actions}
          {table && table.rows.length > 0 && <button type="button" className="icon-btn !h-8 !w-8" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable} aria-label={asTable ? `Show ${title} as a chart` : `Show ${title} as a table`} title={asTable ? "Chart view" : "Table view"}>{asTable ? <BarChart3 size={15} /> : <Table2 size={15} />}</button>}
        </div>
      </header>
      {asTable && table ? (
        <div className="max-h-72 overflow-auto rounded-lg border border-line"><table className="table"><thead><tr>{table.head.map((h, i) => <th key={h} className={i ? "text-right" : ""}>{h}</th>)}</tr></thead>
          <tbody>{table.rows.map((r, n) => <tr key={n}>{r.map((c, i) => <td key={i} className={i ? "text-right tabular-nums" : ""}>{typeof c === "number" ? plain(c) : c}</td>)}</tr>)}</tbody></table></div>
      ) : <div className="min-w-0 flex-1">{children}</div>}
    </section>
  );
}

export const NoData = ({ children = "No activity in this period yet." }: { children?: ReactNode }) => <p className="grid min-h-40 place-items-center text-center text-sm text-muted">{children}</p>;

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(240, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, width };
}

const niceMax = (v: number) => {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return ([1, 2, 2.5, 5, 10].find((m) => m * p >= v) ?? 10) * p;
};

export interface Series { key: string; label: string; color?: string }
type Row = Record<string, unknown>;
const num = (r: Row, k: string) => Number(r[k] ?? 0);

/** Change over time. `kind="area"` for a continuous trend, `"column"` for counts or discrete periods (stacked when several series). */
export function TrendChart({ rows, x, series, format = plain, height = 240, kind = "area", xLabel = (v) => v }: { rows: Row[]; x: string; series: Series[]; format?: Fmt; height?: number; kind?: "area" | "column"; xLabel?: (v: string) => string }) {
  const { ref, width } = useWidth();
  const [at, setAt] = useState<number | null>(null);
  const id = useId().replace(/:/g, "");
  const left = 44, right = 8, top = 10, bottom = 24;
  const w = width - left - right, h = height - top - bottom;
  const stacked = kind === "column";
  const max = niceMax(Math.max(0, ...rows.map((r) => stacked ? series.reduce((t, s) => t + Math.max(0, num(r, s.key)), 0) : Math.max(...series.map((s) => num(r, s.key))))));
  const slot = w / Math.max(rows.length, 1);
  const px = (i: number) => left + (kind === "column" ? slot * i + slot / 2 : rows.length === 1 ? w / 2 : (w * i) / (rows.length - 1));
  const py = (v: number) => top + h - (Math.max(0, v) / max) * h;
  const every = Math.ceil(rows.length / Math.max(2, Math.floor(w / 72)));
  const empty = rows.every((r) => series.every((s) => !num(r, s.key)));
  const move = (clientX: number, rect: DOMRect) => {
    const rel = clientX - rect.left - left;
    const i = kind === "column" ? Math.floor(rel / slot) : Math.round((rel / w) * (rows.length - 1));
    setAt(i >= 0 && i < rows.length ? i : null);
  };
  return (
    <div ref={ref} className="relative w-full">
      <svg width={width} height={height} role="img" aria-label={`${series.map((s) => s.label).join(" and ")} over time`}
        onPointerMove={(e) => move(e.clientX, e.currentTarget.getBoundingClientRect())} onPointerLeave={() => setAt(null)}>
        <defs>{series.map((s, i) => <linearGradient key={s.key} id={`${id}-${i}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={s.color ?? seriesColor(i)} stopOpacity="0.28" /><stop offset="100%" stopColor={s.color ?? seriesColor(i)} stopOpacity="0" /></linearGradient>)}</defs>
        {[0, 0.25, 0.5, 0.75, 1].map((f) => <g key={f}><line x1={left} x2={width - right} y1={py(max * f)} y2={py(max * f)} stroke="var(--grid)" /><text x={left - 8} y={py(max * f) + 3.5} textAnchor="end" fontSize="10.5" fill="var(--color-muted)">{compact(max * f)}</text></g>)}
        {rows.map((r, i) => i % every === 0 && <text key={i} x={px(i)} y={height - 7} textAnchor="middle" fontSize="10.5" fill="var(--color-muted)">{xLabel(String(r[x]))}</text>)}
        {!empty && kind === "area" && series.map((s, si) => {
          const line = rows.map((r, i) => `${i ? "L" : "M"}${px(i)},${py(num(r, s.key))}`).join("");
          return <g key={s.key} className="animate-fade"><path d={`${line}L${px(rows.length - 1)},${top + h}L${px(0)},${top + h}Z`} fill={`url(#${id}-${si})`} /><path d={line} fill="none" stroke={s.color ?? seriesColor(si)} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" /></g>;
        })}
        {!empty && kind === "column" && rows.map((r, i) => {
          let base = top + h;
          const bw = Math.max(2, Math.min(28, slot - 2));
          const live = series.map((s, si) => ({ s, si, v: Math.max(0, num(r, s.key)) })).filter((e) => e.v > 0);
          return <g key={i} opacity={at === null || at === i ? 1 : 0.55}>{live.map((e, n) => {
            const size = (e.v / max) * h;
            const y = base - size;
            base = y - 2;
            const rad = n === live.length - 1 ? Math.min(4, bw / 2, size) : 0;
            const X = px(i) - bw / 2;
            return <path key={e.s.key} fill={e.s.color ?? seriesColor(e.si)} d={`M${X},${y + size}V${y + rad}Q${X},${y} ${X + rad},${y}H${X + bw - rad}Q${X + bw},${y} ${X + bw},${y + rad}V${y + size}Z`} />;
          })}</g>;
        })}
        {at !== null && !empty && kind === "area" && <g><line x1={px(at)} x2={px(at)} y1={top} y2={top + h} stroke="var(--color-muted)" strokeDasharray="3 3" />{series.map((s, i) => <circle key={s.key} cx={px(at)} cy={py(num(rows[at], s.key))} r="4.5" fill={s.color ?? seriesColor(i)} stroke="var(--color-surface)" strokeWidth="2" />)}</g>}
      </svg>
      {empty && <p className="absolute inset-0 grid place-items-center text-sm text-muted">No activity in this period yet.</p>}
      {at !== null && !empty && (
        <div className="popover pointer-events-none absolute top-1 z-10 min-w-36 px-3 py-2 text-xs" style={{ left: Math.min(Math.max(px(at) + 12, 0), width - 160) }}>
          <p className="mb-1 font-semibold">{xLabel(String(rows[at][x]))}</p>
          {series.map((s, i) => <p key={s.key} className="flex items-center justify-between gap-3"><span className="flex items-center gap-1.5 text-muted"><span className="h-2 w-2 rounded-sm" style={{ background: s.color ?? seriesColor(i) }} />{s.label}</span><b className="tabular-nums">{format(num(rows[at], s.key))}</b></p>)}
        </div>)}
    </div>
  );
}

export interface Item { label: string; value: number | string; note?: string }

/** Share of a whole. More than six slices fold into "Other". */
export function DonutChart({ items, format = plain, centerLabel = "Total" }: { items: Item[]; format?: Fmt; centerLabel?: string }) {
  const [at, setAt] = useState<number | null>(null);
  let list = items.map((i) => ({ label: i.label.replace(/_/g, " "), value: Number(i.value) })).filter((i) => i.value > 0);
  if (list.length > 6) list = [...list.slice(0, 5), { label: "Other", value: list.slice(5).reduce((t, i) => t + i.value, 0) }];
  const total = list.reduce((t, i) => t + i.value, 0);
  if (!total) return <NoData />;
  const R = 62, C = 2 * Math.PI * R;
  let offset = 0;
  const shown = at === null ? null : list[at];
  return (
    <div className="flex flex-wrap items-center justify-center gap-5">
      <svg width="170" height="170" viewBox="0 0 170 170" role="img" aria-label={list.map((i) => `${i.label}: ${format(i.value)}`).join(", ")}>
        <g transform="rotate(-90 85 85)">{list.map((i, n) => {
          const len = (i.value / total) * C;
          const seg = <circle key={i.label} cx="85" cy="85" r={R} fill="none" stroke={seriesColor(n)} strokeWidth={at === n ? 26 : 20} strokeDasharray={`${Math.max(len - (list.length > 1 ? 2 : 0), 0.5)} ${C}`} strokeDashoffset={-offset} onPointerEnter={() => setAt(n)} onPointerLeave={() => setAt(null)} style={{ transition: "stroke-width .18s" }} />;
          offset += len;
          return seg;
        })}</g>
        <text x="85" y="81" textAnchor="middle" fontSize="11" fill="var(--color-muted)">{shown ? shown.label.slice(0, 18) : centerLabel}</text>
        <text x="85" y="100" textAnchor="middle" fontSize="16" fontWeight="700" fill="var(--color-ink)">{compact(shown ? shown.value : total)}</text>
      </svg>
      <ul className="min-w-40 flex-1 space-y-1.5 text-sm">
        {list.map((i, n) => <li key={i.label} onPointerEnter={() => setAt(n)} onPointerLeave={() => setAt(null)} className={`flex items-center gap-2 rounded-md px-1.5 py-0.5 ${at === n ? "bg-slate-100" : ""}`}><span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: seriesColor(n) }} aria-hidden /><span className="min-w-0 flex-1 truncate capitalize">{i.label}</span><span className="font-semibold tabular-nums">{format(i.value)}</span><span className="w-10 text-right text-xs text-muted">{Math.round((i.value / total) * 100)}%</span></li>)}
      </ul>
    </div>
  );
}

/** Ranked magnitudes in a single hue. */
export function RankBars({ items, format = plain, empty = "No data for this period." }: { items: Item[]; format?: Fmt; empty?: string }) {
  if (!items.length || items.every((i) => !Number(i.value))) return <NoData>{empty}</NoData>;
  const max = Math.max(...items.map((i) => Math.abs(Number(i.value))), 1);
  return (
    <ul className="space-y-3">
      {items.map((i) => (
        <li key={i.label} className="group" title={`${i.label}: ${format(Number(i.value))}`}>
          <div className="mb-1 flex justify-between gap-3 text-sm"><span className="truncate capitalize">{i.label.replace(/_/g, " ")}</span><span className="shrink-0 font-semibold tabular-nums">{format(Number(i.value))}{i.note && <span className="ml-2 font-normal text-muted">{i.note}</span>}</span></div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full transition-[width,filter] duration-700 group-hover:brightness-110" style={{ width: `${Math.max((Math.abs(Number(i.value)) / max) * 100, Number(i.value) ? 3 : 0)}%`, background: "var(--series-1)" }} /></div>
        </li>))}
    </ul>
  );
}

export const itemsTable = (name: string, valueName: string, items: Item[] = []): TableData => ({ head: [name, valueName], rows: items.map((i) => [i.label.replace(/_/g, " "), Number(i.value)]) });
