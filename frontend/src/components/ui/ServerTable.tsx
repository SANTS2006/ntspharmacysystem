/** A table over a paginated API endpoint: server-side search, filters and pagination. */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../../lib/api";
import { ErrorState } from ".";
import { DataTable, Pagination, type Column } from "./data";

export interface ApiPage<T> { count: number; next: string | null; previous: string | null; results: T[] }
export const PAGE_SIZE = 25;

export function ServerTable<T>({ queryKey, path, columns, rowKey, search, filters, empty, onRowClick, refetchInterval, tenant }: {
  queryKey: unknown[]; path: string; columns: Column<T>[]; rowKey: (row: T) => string | number; search?: string;
  filters?: { name: string; label: string; options: [string, string][] }[]; empty?: ReactNode; onRowClick?: (row: T) => void; refetchInterval?: number; tenant?: string;
}) {
  const [page, setPage] = useState(1);
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  useEffect(() => { const t = window.setTimeout(() => setDebounced(term), 300); return () => window.clearTimeout(t); }, [term]);
  const params = new URLSearchParams({ page: String(page) });
  if (debounced) params.set("search", debounced);
  Object.entries(values).forEach(([k, v]) => v && params.set(k, v));
  const url = `${path}${path.includes("?") ? "&" : "?"}${params}`;
  useEffect(() => { setPage(1); }, [debounced, path]);
  const q = useQuery({ queryKey: [...queryKey, url], queryFn: () => api<ApiPage<T>>(url, { tenant }), placeholderData: keepPreviousData, refetchInterval });
  useEffect(() => { if (q.isError && page > 1) setPage(1); }, [q.isError, page]);
  return (
    <div className="space-y-3">
      {(search || filters) && (
        <div className="flex flex-wrap items-center gap-2">
          {search && <span className="relative min-w-0 flex-1 sm:max-w-sm"><Search size={16} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input type="search" aria-label={search} placeholder={search} value={term} onChange={(e) => setTerm(e.target.value)} className="w-full !pl-9" /></span>}
          {filters?.map((f) => <select key={f.name} aria-label={f.label} value={values[f.name] ?? ""} onChange={(e) => { setValues((v) => ({ ...v, [f.name]: e.target.value })); setPage(1); }}><option value="">{f.label}</option>{f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>)}
        </div>)}
      {q.isError ? <ErrorState onRetry={() => q.refetch()}>These records could not be loaded.</ErrorState>
        : <DataTable columns={columns} rows={q.data?.results} loading={q.isLoading} rowKey={rowKey} pageSize={Math.max(PAGE_SIZE, q.data?.results.length ?? 0)} empty={debounced ? "No records match your search." : empty} onRowClick={onRowClick} hidePager={!!q.data && q.data.count > PAGE_SIZE} />}
      {q.data && q.data.count > PAGE_SIZE && <Pagination page={page} setPage={setPage} hasPrev={!!q.data.previous} hasNext={!!q.data.next} total={q.data.count} pageSize={PAGE_SIZE} />}
    </div>
  );
}
