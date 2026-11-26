/** Report runner with sorting, pagination and exports. (The visual analysis lives on the dashboard.) */
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, FileDown, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { EmptyState, ErrorState, PageHeader, Pagination, StatCard, TableLoader, errorMessage, useToast } from "../../components/ui";
import { api, downloadFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { money, words } from "../../lib/format";

interface Meta { slug: string; title: string; group: string }
interface Col { key: string; label: string; kind: string }
interface Result { title: string; columns: Col[]; rows: Record<string, unknown>[]; count: number; page: number; page_size: number; summary: Record<string, unknown> }
const today = () => new Date().toISOString().slice(0, 10);
const monthStart = () => today().slice(0, 8) + "01";
const value = (v: unknown) => (typeof v === "string" || typeof v === "number") && v !== "" && !Number.isNaN(Number(v)) ? (Number.isInteger(v) ? Number(v).toLocaleString() : money(v)) : String(v ?? "");

export function ReportsPage() {
  const { user } = useAuth(); const toast = useToast();
  const list = useQuery({ queryKey: ["report-list"], queryFn: () => api<Meta[]>("/reports/") });
  const [picked, setPicked] = useState(""); const [from, setFrom] = useState(monthStart()); const [to, setTo] = useState(today());
  const [group, setGroup] = useState("day"); const [search, setSearch] = useState(""); const [ordering, setOrdering] = useState(""); const [page, setPage] = useState(1);
  const slug = picked || list.data?.[0]?.slug || "";
  const qs = useMemo(() => `date_from=${from}&date_to=${to}&group=${group}&search=${encodeURIComponent(search)}&ordering=${ordering}&page=${page}&page_size=15`, [from, to, group, search, ordering, page]);
  const res = useQuery({ queryKey: ["report", slug, qs], queryFn: () => api<Result>(`/reports/${slug}/?${qs}`), enabled: !!slug, placeholderData: (p) => p });
  const groups = useMemo(() => Object.entries((list.data ?? []).reduce<Record<string, Meta[]>>((a, r) => ({ ...a, [r.group]: [...(a[r.group] ?? []), r] }), {})), [list.data]);
  const exportAs = (fmt: "csv" | "xlsx" | "pdf") => downloadFile(`/reports/${slug}/?${qs}&export=${fmt}`, `${slug}.${fmt}`).catch((e) => toast(errorMessage(e), "error"));
  if (list.isError) return <ErrorState onRetry={() => list.refetch()}>{errorMessage(list.error)}</ErrorState>;
  return (
    <div className="space-y-5">
      <PageHeader title="Reports" subtitle={user?.branch ? "Reports are limited to your branch." : "Run, filter and export reports."}
        actions={([["pdf", "PDF"], ["xlsx", "Excel"], ["csv", "CSV"]] as const).map(([fmt, label]) => <button key={fmt} className="btn btn-outline" disabled={!slug} onClick={() => exportAs(fmt)}><FileDown size={15} aria-hidden />{label}</button>)} />
      <div className="card grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-5">
        <label className="field-label">Report<select className="mt-1.5 w-full" value={slug} onChange={(e) => { setPicked(e.target.value); setPage(1); setOrdering(""); }}>{groups.map(([g, items]) => <optgroup key={g} label={g}>{items.map((r) => <option key={r.slug} value={r.slug}>{r.title}</option>)}</optgroup>)}</select></label>
        <label className="field-label">From<input type="date" className="mt-1.5 w-full" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1); }} /></label>
        <label className="field-label">To<input type="date" className="mt-1.5 w-full" value={to} onChange={(e) => { setTo(e.target.value); setPage(1); }} /></label>
        <label className="field-label">Group by<select className="mt-1.5 w-full" disabled={slug !== "sales-summary"} value={group} onChange={(e) => setGroup(e.target.value)}><option value="day">Day</option><option value="week">Week</option><option value="month">Month</option><option value="year">Year</option></select></label>
        <label className="field-label">Filter rows<span className="relative mt-1.5 block"><Search size={15} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input type="search" className="w-full !pl-9" placeholder="Enter your filter text" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} /></span></label>
      </div>
      {res.isError && <ErrorState onRetry={() => res.refetch()}>{errorMessage(res.error)}</ErrorState>}
      {res.isLoading && <TableLoader />}
      {res.data && <>
        {Object.keys(res.data.summary).length > 0 && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Object.entries(res.data.summary).map(([k, v]) => <StatCard key={k} label={words(k)[0].toUpperCase() + words(k).slice(1)} value={value(v)} />)}</div>}
        {res.data.rows.length === 0 ? <EmptyState>No data for this selection.</EmptyState> : <div className="table-wrap"><table className="table"><thead><tr>{res.data.columns.map((c) => <th key={c.key} className={c.kind === "money" || c.kind === "int" ? "text-right" : ""} aria-sort={ordering === c.key ? "ascending" : ordering === `-${c.key}` ? "descending" : undefined}><button type="button" className="inline-flex items-center gap-1 uppercase" onClick={() => { setOrdering(ordering === c.key ? `-${c.key}` : c.key); setPage(1); }}>{c.label}{ordering === c.key ? <ChevronUp size={12} aria-hidden /> : ordering === `-${c.key}` ? <ChevronDown size={12} aria-hidden /> : null}</button></th>)}</tr></thead>
          <tbody>{res.data.rows.map((r, i) => <tr key={i}>{res.data!.columns.map((c) => <td key={c.key} className={c.kind === "money" || c.kind === "int" ? "text-right tabular-nums" : ""}>{c.kind === "money" ? money(r[c.key]) : String(r[c.key] ?? "")}</td>)}</tr>)}</tbody></table></div>}
        <Pagination page={page} setPage={setPage} total={res.data.count} pageSize={res.data.page_size} />
      </>}
    </div>
  );
}
