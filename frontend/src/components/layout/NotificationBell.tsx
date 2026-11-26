import { Bell, CheckCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ago } from "../../lib/format";
import { NOTE_TONES, noteIcon, useLatestNotes, useNoteActions } from "../../lib/notifications";
import { Spinner } from "../brand/Brand";
import { useToast } from "../ui";
import { useDismiss } from "./useDismiss";

export function NotificationBell({ base }: { base: string }) {
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  const q = useLatestNotes();
  const { markAll, markRead } = useNoteActions();
  const nav = useNavigate();
  const toast = useToast();
  const unread = q.data?.unread ?? 0;
  const newest = useRef<number | null>(null);
  const [ring, setRing] = useState(false);
  useEffect(() => { // announce notifications that arrive while the app is open (not the ones already there on load)
    if (!q.data) return;
    const top = q.data.results[0]?.id ?? 0;
    if (newest.current !== null && top > newest.current && !q.data.results[0].read) {
      toast(q.data.results[0].title, "info");
      setRing(true);
      window.setTimeout(() => setRing(false), 1500);
    }
    newest.current = Math.max(newest.current ?? 0, top);
  }, [q.data, toast]);
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-haspopup="true" aria-expanded={open} aria-label={`Notifications: ${unread} unread`} className="icon-btn relative">
        <Bell size={19} aria-hidden className={ring ? "animate-bounce" : ""} />
        {unread > 0 && <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-[#c81e1e] px-1 text-[10px] font-bold text-white">{unread > 99 ? "99+" : unread}</span>}
      </button>
      {open && (
        <div className="popover animate-pop fixed inset-x-3 top-[4.75rem] z-50 sm:absolute sm:inset-x-auto sm:right-0 sm:top-12 sm:w-96">
          <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
            <p className="text-sm font-bold">Notifications {unread > 0 && <span className="text-muted">({unread} unread)</span>}</p>
            {unread > 0 && <button type="button" className="btn-link" onClick={() => markAll.mutate()}><CheckCheck size={13} aria-hidden />Mark all read</button>}
          </div>
          <ul className="max-h-96 overflow-y-auto p-1.5">
            {q.isLoading && <li className="grid place-items-center p-6"><Spinner size={22} /></li>}
            {q.isError && <li className="p-4 text-sm text-muted">Notifications could not be loaded.</li>}
            {q.data?.results.length === 0 && <li className="p-6 text-center text-sm text-muted">You are all caught up.</li>}
            {q.data?.results.map((n) => {
              const Icon = noteIcon(n.kind);
              return (
                <li key={n.id}>
                  <button type="button" onClick={() => { setOpen(false); if (!n.read) markRead.mutate({ id: n.id }); nav(`${base}/notifications/${n.id}`); }} className={`flex w-full gap-3 rounded-xl p-2.5 text-left transition hover:bg-slate-100 ${n.read ? "" : "bg-teal-50"}`}>
                    <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${NOTE_TONES[n.level]}`}><Icon size={17} aria-hidden /></span>
                    <span className="min-w-0 flex-1"><span className={`block truncate text-sm ${n.read ? "font-medium" : "font-bold"}`}>{n.title}</span><span className="line-clamp-2 text-xs text-muted">{n.body}</span><span className="mt-0.5 block text-[11px] text-muted">{ago(n.created_at)}</span></span>
                    {!n.read && <span aria-label="Unread" className="mt-2 h-2 w-2 shrink-0 rounded-full" style={{ background: "var(--brand)" }} />}
                  </button>
                </li>);
            })}
          </ul>
          <Link to={`${base}/notifications`} onClick={() => setOpen(false)} className="block border-t border-line px-4 py-3 text-center text-sm font-bold text-primary hover:bg-slate-100">View all notifications</Link>
        </div>)}
    </div>
  );
}
