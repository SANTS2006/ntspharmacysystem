/** Tables, pagination, avatars and tabs. */
import { ChevronLeft, ChevronRight, ChevronsUpDown, ChevronDown, ChevronUp, Search } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { TableLoader } from "../brand/Brand";

export function Avatar({ src, name, size = 40, className = "" }: { src?: string | null; name: string; size?: number; className?: string }) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [src]);
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("") || "U";
  const style = { width: size, height: size, fontSize: Math.max(10, size * 0.34) };
  return src && !broken
    ? <img src={src} alt="" onError={() => setBroken(true)} style={style} className={`shrink-0 rounded-full border border-line object-cover ${className}`} />
    : <span aria-hidden style={{ ...style, background: "linear-gradient(135deg, var(--brand), #142d3d)" }} className={`grid shrink-0 place-items-center rounded-full font-bold text-white ${className}`}>{initials}</span>;
}

export function Tabs<T extends string>({ tabs, value, onChange, label = "Sections" }: { tabs: [T, string, number?][]; value: T; onChange: (v: T) => void; label?: string }) {
  return (
    <div role="tablist" aria-label={label} className="tablist">
      {tabs.map(([k, text, count]) => (
        <button key={k} type="button" role="tab" aria-selected={value === k} onClick={() => onChange(k)} className={`tab ${value === k ? "tab-active" : ""}`}>
          {text}{count ? <span className="ml-1.5 rounded-full bg-black/15 px-1.5 text-[11px]">{count}</span> : null}
        </button>))}
    </div>
  );
}

const pageList = (page: number, pages: number): (number | "…")[] => {
  const keep = new Set([1, pages, page - 1, page, page + 1].filter((n) => n >= 1 && n <= pages));
  const out: (number | "…")[] = [];
  [...keep].sort((a, b) => a - b).forEach((n, i, all) => { if (i && n - all[i - 1] > 1) out.push("…"); out.push(n); });
  return out;
};

export function Pagination({ page, setPage, hasPrev, hasNext, total, pageSize }: { page: number; setPage: (n: number) => void; hasPrev?: boolean; hasNext?: boolean; total?: number; pageSize?: number }) {
  const pages = total !== undefined && pageSize ? Math.max(1, Math.ceil(total / pageSize)) : undefined;
  const prev = hasPrev ?? page > 1;
  const next = hasNext ?? (pages ? page < pages : false);
  if (!prev && !next && (total ?? 0) === 0) return null;
  const range = total !== undefined && pageSize ? `Showing ${total ? (page - 1) * pageSize + 1 : 0}–${Math.min(page * pageSize, total)} of ${total.toLocaleString()}` : `Page ${page}${total !== undefined ? ` · ${total.toLocaleString()} records` : ""}`;
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted">{range}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" disabled={!prev} onClick={() => setPage(page - 1)} className="btn btn-outline btn-sm"><ChevronLeft size={15} aria-hidden />Previous</button>
        {pages && pages > 1 && pageList(page, pages).map((n, i) => n === "…" ? <span key={`gap-${i}`} className="px-1 text-muted">…</span> : (
          <button key={n} type="button" aria-current={n === page ? "page" : undefined} onClick={() => setPage(n)} className={`btn btn-sm !min-w-9 !px-2 ${n === page ? "btn-primary" : "btn-outline"}`}>{n}</button>))}
        <button type="button" disabled={!next} onClick={() => setPage(page + 1)} className="btn btn-outline btn-sm">Next<ChevronRight size={15} aria-hidden /></button>
      </div>
    </nav>
  );
}

/** Client-side paging for a list that is already loaded. */
export function usePaged<T>(rows: T[], pageSize = 10) {
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  useEffect(() => { if (page > pages) setPage(pages); }, [page, pages]);
  const safe = Math.min(page, pages);
  return { rows: rows.slice((safe - 1) * pageSize, safe * pageSize), page: safe, setPage, total: rows.length, pageSize };
}

export interface Column<T> { key: string; header: string; render?: (row: T) => ReactNode; align?: "right" | "center"; sort?: (row: T) => string | number; className?: string }

/** A listing with search, column sorting and pagination. */
export function DataTable<T>({ columns, rows, rowKey, search, searchLabel = "Search", loading, empty = "Nothing to show yet.", toolbar, pageSize = 10, onRowClick, hidePager }: {
  columns: Column<T>[]; rows: T[] | undefined; rowKey: (row: T) => string | number; search?: (row: T) => string; searchLabel?: string; loading?: boolean; empty?: ReactNode; toolbar?: ReactNode; pageSize?: number; onRowClick?: (row: T) => void; hidePager?: boolean;
}) {
  const [q, setQ] = useState("");
  const [order, setOrder] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const filtered = useMemo(() => {
    let list = rows ?? [];
    if (q && search) list = list.filter((r) => search(r).toLowerCase().includes(q.toLowerCase()));
    const col = order && columns.find((c) => c.key === order.key);
    if (order && col?.sort) {
      const get = col.sort;
      list = [...list].sort((a, b) => { const x = get(a), y = get(b); return (x > y ? 1 : x < y ? -1 : 0) * order.dir; });
    }
    return list;
  }, [rows, q, search, order, columns]);
  const paged = usePaged(filtered, pageSize);
  useEffect(() => { paged.setPage(1); }, [q]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="space-y-3">
      {(search || toolbar) && (
        <div className="flex flex-wrap items-center gap-2">
          {search && <span className="relative min-w-0 flex-1 sm:max-w-xs"><Search size={16} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input type="search" aria-label={searchLabel} placeholder="Enter your search term" value={q} onChange={(e) => setQ(e.target.value)} className="w-full !pl-9" /></span>}
          {toolbar}
        </div>)}
      {loading ? <TableLoader columns={columns.length} /> : filtered.length === 0 ? <div className="empty">{q ? "No records match your search." : empty}</div> : (
        <div className="table-wrap animate-fade">
          <table className="table">
            <thead><tr>{columns.map((c) => (
              <th key={c.key} scope="col" aria-sort={order?.key === c.key ? (order.dir === 1 ? "ascending" : "descending") : undefined} className={c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : ""}>
                {c.sort ? <button type="button" className="inline-flex items-center gap-1 uppercase tracking-wider" onClick={() => setOrder((o) => o?.key === c.key ? { key: c.key, dir: o.dir === 1 ? -1 : 1 } : { key: c.key, dir: 1 })}>{c.header}{order?.key === c.key ? (order.dir === 1 ? <ChevronUp size={12} aria-hidden /> : <ChevronDown size={12} aria-hidden />) : <ChevronsUpDown size={12} aria-hidden className="opacity-50" />}</button> : c.header}
              </th>))}</tr></thead>
            <tbody>{paged.rows.map((r) => (
              <tr key={rowKey(r)} onClick={onRowClick ? (e) => { if (!(e.target as HTMLElement).closest("button,a,input,select")) onRowClick(r); } : undefined} className={onRowClick ? "cursor-pointer" : ""}>
                {columns.map((c) => <td key={c.key} className={`${c.align === "right" ? "text-right tabular-nums" : c.align === "center" ? "text-center" : ""} ${c.className ?? ""}`}>{c.render ? c.render(r) : String((r as Record<string, unknown>)[c.key] ?? "—")}</td>)}
              </tr>))}</tbody>
          </table>
        </div>)}
      {!hidePager && !loading && filtered.length > 0 && <Pagination page={paged.page} setPage={paged.setPage} total={paged.total} pageSize={paged.pageSize} />}
    </div>
  );
}
