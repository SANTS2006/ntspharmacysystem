/** Notification list and detail pages, shared by the platform, staff and customer areas. */
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowUpRight, CheckCheck, MailOpen, Mail, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { EmptyState, ErrorState, Loading, PageHeader, Pagination, StatusBadge, Tabs, useConfirm, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { ago, dateTime, words } from "../../lib/format";
import { NOTE_TONES, noteIcon, useNoteActions, type Note, type NotePage } from "../../lib/notifications";

const KINDS = ["order", "payment", "inventory", "prescription", "delivery", "appointment", "inquiry", "customer", "cash", "payroll", "billing", "backup", "security", "account"];
const PAGE = 12;

export function NotificationsPage({ base }: { base: string }) {
  const [tab, setTab] = useState<"all" | "unread">("all");
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);
  const confirm = useConfirm(); const toast = useToast(); const nav = useNavigate();
  const { markAll, markRead, remove } = useNoteActions();
  const q = useQuery({ queryKey: ["notifications", "list", tab, kind, page], queryFn: () => api<NotePage>(`/notifications/?page=${page}&page_size=${PAGE}${tab === "unread" ? "&unread=1" : ""}${kind ? `&kind=${kind}` : ""}`) });
  useEffect(() => { if (q.isError && page > 1) setPage(1); }, [q.isError, page]);
  const destroy = async (n: Note) => { if (await confirm({ title: "Delete this notification?", message: n.title, confirmLabel: "Delete", danger: true })) remove.mutate(n.id, { onSuccess: () => toast("Notification deleted.") }); };
  return (
    <div className="space-y-5">
      <PageHeader title="Notifications" subtitle="Everything that needs your attention. New items appear here as they happen."
        actions={<button className="btn btn-outline" disabled={!q.data?.unread || markAll.isPending} onClick={() => markAll.mutate()}><CheckCheck size={16} aria-hidden />Mark all as read</button>} />
      <div className="flex flex-wrap items-center gap-3">
        <Tabs label="Filter" tabs={[["all", "All"], ["unread", "Unread", q.data?.unread]]} value={tab} onChange={(v) => { setTab(v); setPage(1); }} />
        <select aria-label="Type of notification" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }}><option value="">All types</option>{KINDS.map((k) => <option key={k} value={k}>{k[0].toUpperCase() + k.slice(1)}</option>)}</select>
      </div>
      {q.isLoading && <Loading rows={5} />}
      {q.isError && <ErrorState onRetry={() => q.refetch()}>Notifications could not be loaded.</ErrorState>}
      {q.data?.results.length === 0 && <EmptyState>{tab === "unread" ? "No unread notifications." : "You have no notifications yet."}</EmptyState>}
      <ul className="space-y-2.5">
        {q.data?.results.map((n) => {
          const Icon = noteIcon(n.kind);
          return (
            <li key={n.id} className={`card card-hover animate-rise flex flex-wrap items-center gap-4 p-4 ${n.read ? "" : "border-l-4"}`} style={n.read ? undefined : { borderLeftColor: "var(--brand)" }}>
              <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${NOTE_TONES[n.level]}`}><Icon size={20} aria-hidden /></span>
              <button type="button" className="min-w-0 flex-1 basis-56 text-left" onClick={() => nav(`${base}/notifications/${n.id}`)}>
                <span className={`block ${n.read ? "font-medium" : "font-bold"}`}>{n.title}</span>
                <span className="line-clamp-1 text-sm text-muted">{n.body}</span>
                <span className="text-xs text-muted">{ago(n.created_at)} · <span className="capitalize">{words(n.kind)}</span></span>
              </button>
              <div className="flex gap-1.5">
                <button className="btn-link" onClick={() => markRead.mutate({ id: n.id, read: !n.read })}>{n.read ? <><Mail size={13} aria-hidden />Mark unread</> : <><MailOpen size={13} aria-hidden />Mark read</>}</button>
                <button className="btn-link btn-link-danger" aria-label={`Delete ${n.title}`} onClick={() => destroy(n)}><Trash2 size={13} aria-hidden />Delete</button>
              </div>
            </li>);
        })}
      </ul>
      {q.data && <Pagination page={page} setPage={setPage} total={q.data.count} pageSize={PAGE} />}
    </div>
  );
}

export function NotificationDetail({ base }: { base: string }) {
  const { noteId = "" } = useParams();
  const nav = useNavigate(); const confirm = useConfirm(); const toast = useToast();
  const { markRead, remove } = useNoteActions();
  const q = useQuery({ queryKey: ["notifications", "item", noteId], queryFn: () => api<Note>(`/notifications/${noteId}/`), retry: false });
  const opened = useRef<number | null>(null);
  useEffect(() => { // opening a notification reads it (once, so "mark as unread" stays unread)
    if (q.data && !q.data.read && opened.current !== q.data.id) markRead.mutate({ id: q.data.id });
    if (q.data) opened.current = q.data.id;
  }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const back = <Link to={`${base}/notifications`} className="btn btn-outline btn-sm"><ArrowLeft size={15} aria-hidden />All notifications</Link>;
  if (q.isLoading) return <Loading rows={3} />;
  if (!q.data) return <div className="space-y-4">{back}<EmptyState>This notification no longer exists.</EmptyState></div>;
  const n = q.data, Icon = noteIcon(n.kind);
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      {back}
      <article className="card animate-rise overflow-hidden">
        <div className="h-1.5" style={{ background: "linear-gradient(90deg, var(--brand), var(--brand-2))" }} />
        <div className="p-6 sm:p-8">
          <div className="flex items-start gap-4">
            <span className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl ${NOTE_TONES[n.level]}`}><Icon size={26} aria-hidden /></span>
            <div className="min-w-0"><h1 className="page-title">{n.title}</h1><p className="mt-1 text-sm text-muted">{dateTime(n.created_at)} · {ago(n.created_at)}</p></div>
          </div>
          <p className="mt-6 whitespace-pre-wrap text-base leading-7">{n.body || "There are no further details."}</p>
          <dl className="mt-6 grid gap-3 rounded-xl border border-line p-4 text-sm sm:grid-cols-3">
            <div><dt className="text-muted">Type</dt><dd className="font-semibold capitalize">{words(n.kind)}</dd></div>
            <div><dt className="text-muted">Priority</dt><dd><StatusBadge status={n.level} tone={n.level === "info" ? "info" : n.level} /></dd></div>
            <div><dt className="text-muted">Status</dt><dd className="font-semibold">{n.read ? "Read" : "Unread"}</dd></div>
          </dl>
          <div className="mt-6 flex flex-wrap gap-2">
            {n.link && <Link to={`${base}${n.link}`} className="btn btn-primary">Open related page<ArrowUpRight size={16} aria-hidden /></Link>}
            <button className="btn btn-outline" onClick={() => markRead.mutate({ id: n.id, read: !n.read }, { onSuccess: () => q.refetch() })}>{n.read ? "Mark as unread" : "Mark as read"}</button>
            <button className="btn btn-outline btn-link-danger" onClick={async () => { if (await confirm({ title: "Delete this notification?", message: n.title, confirmLabel: "Delete", danger: true })) remove.mutate(n.id, { onSuccess: () => { toast("Notification deleted."); nav(`${base}/notifications`); } }); }}><Trash2 size={16} aria-hidden />Delete</button>
          </div>
        </div>
      </article>
    </div>
  );
}
