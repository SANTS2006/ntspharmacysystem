/** Application shell shared by the pharmacy staff area and the platform administration: collapsible grouped sidebar,
 *  mobile drawer, top bar with breadcrumb, module quick-search, notifications slot and user menu. Presentational only. */
import { Bell, ChevronDown, ChevronRight, KeyRound, LogOut, Menu, PanelLeftClose, PanelLeftOpen, Search, X, type LucideIcon } from "lucide-react";
import { Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Loading } from "../ui";
import { PageBoundary } from "../ui/PageBoundary";

export interface NavItem { to: string; label: string; icon: LucideIcon; keywords?: string }
export interface NavGroup { label: string; items: NavItem[] }
export interface Notification { id: string; label: string; count: number; to: string; tone: "warning" | "danger" | "info" }

const COLLAPSE_KEY = "nts.sidebar.collapsed";
const readCollapsed = () => { try { return localStorage.getItem(COLLAPSE_KEY) === "1"; } catch { return false; } };

function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) close(); };
    const key = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("keydown", key); };
  }, [open, close]);
  return ref;
}

function QuickSearch({ items }: { items: (NavItem & { group: string })[] }) {
  const nav = useNavigate();
  const [q, setQ] = useState(""); const [open, setOpen] = useState(false); const [at, setAt] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const ref = useDismiss(open, () => setOpen(false));
  const found = items.filter((i) => `${i.label} ${i.group} ${i.keywords ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); input.current?.focus(); } };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  const go = (to: string) => { setOpen(false); setQ(""); input.current?.blur(); nav(to); };
  return (
    <div ref={ref} className="relative hidden w-72 lg:block">
      <Search size={16} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
      <input ref={input} role="combobox" aria-expanded={open} aria-controls="quick-results" aria-label="Search pages" placeholder="Search pages…  (Ctrl+K)" value={q}
        className="w-full pl-9 pr-3" onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setAt(0); setOpen(true); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setAt((a) => Math.min(a + 1, found.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setAt((a) => Math.max(a - 1, 0)); }
          if (e.key === "Enter" && found[at]) go(found[at].to);
        }} />
      {open && (
        <ul id="quick-results" role="listbox" className="animate-pop absolute right-0 top-11 z-50 max-h-80 w-full overflow-y-auto rounded-xl border border-line bg-white p-1.5 shadow-pop">
          {found.length === 0 && <li className="p-3 text-sm text-muted">No matching pages.</li>}
          {found.map((i, n) => (
            <li key={i.to} role="option" aria-selected={n === at}>
              <button type="button" onClick={() => go(i.to)} onMouseEnter={() => setAt(n)} className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm ${n === at ? "bg-teal-50 text-teal-800" : ""}`}>
                <i.icon size={16} aria-hidden /><span className="flex-1">{i.label}</span><span className="text-xs text-muted">{i.group}</span>
              </button>
            </li>))}
        </ul>)}
    </div>
  );
}

function NotificationMenu({ items }: { items: Notification[] }) {
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  const live = items.filter((i) => i.count > 0);
  const total = live.reduce((t, i) => t + i.count, 0);
  const dot = { warning: "bg-warning", danger: "bg-danger", info: "bg-info" };
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-haspopup="true" aria-expanded={open} aria-label={`Alerts: ${total}`} className="relative grid h-10 w-10 place-items-center rounded-lg text-slate-600 hover:bg-slate-100">
        <Bell size={19} aria-hidden />
        {total > 0 && <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">{total > 99 ? "99+" : total}</span>}
      </button>
      {open && (
        <div className="animate-pop absolute right-0 top-12 z-50 w-72 rounded-xl border border-line bg-white p-1.5 shadow-pop">
          <p className="px-2.5 py-2 text-xs font-semibold uppercase tracking-wide text-muted">Alerts</p>
          {live.length === 0 && <p className="px-2.5 pb-3 text-sm text-muted">You are all caught up.</p>}
          {live.map((i) => (
            <Link key={i.id} to={i.to} onClick={() => setOpen(false)} className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm hover:bg-slate-50">
              <span className={`h-2 w-2 rounded-full ${dot[i.tone]}`} aria-hidden /><span className="flex-1">{i.label}</span><span className="font-semibold tabular-nums">{i.count}</span>
            </Link>))}
        </div>)}
    </div>
  );
}

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("") || "U";

function UserMenu({ name, role, onSignOut }: { name: string; role: string; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open} className="flex items-center gap-2.5 rounded-lg py-1 pl-1 pr-2 hover:bg-slate-100">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-navy text-xs font-bold text-white">{initials(name)}</span>
        <span className="hidden text-left leading-tight md:block"><span className="block max-w-40 truncate text-sm font-semibold">{name}</span><span className="block text-xs capitalize text-muted">{role.replace(/_/g, " ")}</span></span>
        <ChevronDown size={15} aria-hidden className="text-slate-400" />
      </button>
      {open && (
        <div role="menu" className="animate-pop absolute right-0 top-12 z-50 w-60 rounded-xl border border-line bg-white p-1.5 shadow-pop">
          <div className="border-b border-line px-2.5 pb-2 pt-1"><p className="truncate text-sm font-semibold">{name}</p><p className="text-xs capitalize text-muted">{role.replace(/_/g, " ")}</p></div>
          <Link role="menuitem" to="/change-password" onClick={() => setOpen(false)} className="mt-1 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm hover:bg-slate-50"><KeyRound size={16} aria-hidden />Change password</Link>
          <button role="menuitem" type="button" onClick={onSignOut} className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-red-700 hover:bg-red-50"><LogOut size={16} aria-hidden />Sign out</button>
        </div>)}
    </div>
  );
}

function SidebarNav({ groups, collapsed, label }: { groups: NavGroup[]; collapsed: boolean; label: string }) {
  const [closed, setClosed] = useState<string[]>([]);
  return (
    <nav aria-label={label} className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
      {groups.map((g) => {
        const isOpen = collapsed || !closed.includes(g.label);
        return (
          <div key={g.label}>
            {collapsed ? <div className="mx-2 mb-2 border-t border-white/10" /> : (
              <button type="button" aria-expanded={isOpen} onClick={() => setClosed((c) => (isOpen ? [...c, g.label] : c.filter((x) => x !== g.label)))}
                className="mb-1 flex w-full items-center justify-between rounded px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200">
                {g.label}{isOpen ? <ChevronDown size={13} aria-hidden /> : <ChevronRight size={13} aria-hidden />}
              </button>)}
            {isOpen && (
              <ul className="space-y-0.5">
                {g.items.map(({ to, label: text, icon: Icon }) => (
                  <li key={to}>
                    <NavLink to={to} title={collapsed ? text : undefined} className={({ isActive }) => `flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors ${collapsed ? "justify-center" : ""} ${isActive ? "bg-primary text-white" : "text-slate-300 hover:bg-white/10 hover:text-white"}`}>
                      <Icon size={18} aria-hidden className="shrink-0" /><span className={collapsed ? "sr-only" : "truncate"}>{text}</span>
                    </NavLink>
                  </li>))}
              </ul>)}
          </div>);
      })}
    </nav>
  );
}

export function AppShell({ groups, brandName, brandCaption, logo, user, onSignOut, notifications, navLabel, children }: {
  groups: NavGroup[]; brandName: string; brandCaption: string; logo?: string | null; navLabel: string;
  user: { name: string; role: string }; onSignOut: () => void; notifications?: Notification[]; children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawer, setDrawer] = useState(false);
  const { pathname } = useLocation();
  const flat = useMemo(() => groups.flatMap((g) => g.items.map((i) => ({ ...i, group: g.label }))), [groups]);
  const current = [...flat].sort((a, b) => b.to.length - a.to.length).find((i) => pathname === i.to || pathname.startsWith(i.to + "/"));
  useEffect(() => { setDrawer(false); window.scrollTo(0, 0); }, [pathname]);
  useEffect(() => { if (current) document.title = `${current.label} · ${brandName} | NTS Pharmacy System`; }, [current, brandName]);
  useEffect(() => {
    if (!drawer) return;
    const key = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [drawer]);
  const toggle = () => setCollapsed((c) => { try { localStorage.setItem(COLLAPSE_KEY, c ? "0" : "1"); } catch { /* storage blocked */ } return !c; });

  const brand = (mini: boolean) => (
    <div className={`flex h-16 shrink-0 items-center gap-3 border-b border-white/10 px-4 ${mini ? "justify-center px-2" : ""}`}>
      <img src={logo || "/logo.webp"} alt="" className="h-10 w-10 shrink-0 rounded-xl bg-white object-contain p-1" />
      {!mini && <div className="min-w-0"><p className="truncate text-sm font-bold text-white">{brandName}</p><p className="truncate text-xs text-slate-400">{brandCaption}</p></div>}
    </div>
  );

  return (
    <div className="min-h-screen bg-canvas">
      <a href="#app-main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:rounded focus:bg-white focus:p-2">Skip to content</a>
      <aside className={`no-print fixed inset-y-0 left-0 z-40 hidden flex-col bg-navy transition-[width] duration-200 md:flex ${collapsed ? "w-[76px]" : "w-64"}`}>
        {brand(collapsed)}
        <SidebarNav groups={groups} collapsed={collapsed} label={navLabel} />
        <button type="button" onClick={toggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} className="flex items-center justify-center gap-2 border-t border-white/10 py-3 text-xs font-medium text-slate-400 hover:text-white">
          {collapsed ? <PanelLeftOpen size={17} aria-hidden /> : <><PanelLeftClose size={17} aria-hidden />Collapse</>}
        </button>
      </aside>

      {drawer && (
        <div className="no-print fixed inset-0 z-[60] md:hidden">
          <div className="animate-fade absolute inset-0 bg-slate-900/60" onClick={() => setDrawer(false)} />
          <aside role="dialog" aria-modal="true" aria-label="Menu" className="animate-pop absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-navy">
            <button type="button" autoFocus onClick={() => setDrawer(false)} aria-label="Close menu" className="absolute right-2 top-4 rounded-lg p-1.5 text-slate-300 hover:bg-white/10"><X size={18} /></button>
            {brand(false)}
            <SidebarNav groups={groups} collapsed={false} label={`${navLabel} (mobile)`} />
          </aside>
        </div>)}

      <div className={`flex min-h-screen min-w-0 flex-col transition-[padding] duration-200 ${collapsed ? "md:pl-[76px]" : "md:pl-64"}`}>
        <header className="no-print sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-white/95 px-4 backdrop-blur sm:px-6">
          <button type="button" onClick={() => setDrawer(true)} aria-label="Open menu" className="grid h-10 w-10 place-items-center rounded-lg text-slate-600 hover:bg-slate-100 md:hidden"><Menu size={20} /></button>
          <div className="min-w-0 flex-1">
            <nav aria-label="Breadcrumb"><ol className="flex items-center gap-1 text-xs text-muted"><li className="hidden truncate sm:block">{brandName}</li>{current && <><li aria-hidden className="hidden sm:block"><ChevronRight size={12} /></li><li className="truncate">{current.group}</li></>}</ol></nav>
            <p className="truncate text-sm font-semibold">{current?.label ?? brandName}</p>
          </div>
          <QuickSearch items={flat} />
          {notifications && <NotificationMenu items={notifications} />}
          <UserMenu name={user.name} role={user.role} onSignOut={onSignOut} />
        </header>
        <main id="app-main" className="mx-auto w-full max-w-[1440px] flex-1 p-4 sm:p-6 lg:p-8">
          <PageBoundary key={pathname}><Suspense fallback={<Loading />}>{children}</Suspense></PageBoundary>
        </main>
      </div>
    </div>
  );
}
