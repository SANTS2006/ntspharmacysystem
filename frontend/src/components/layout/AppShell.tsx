/** Application shell shared by every signed-in area (platform, pharmacy staff and customers): grouped sidebar with the signed-in
 *  person at the bottom, top bar with page search, theme switch, live notifications and the account menu. */
import { ChevronRight, LogOut, Menu, Moon, Search, Settings, Sun, X, type LucideIcon } from "lucide-react";
import { Suspense, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { readableOn } from "../../lib/format";
import { useRealtime } from "../../lib/realtime";
import { useTheme } from "../../lib/theme";
import { BrandProvider, Loading, type Brand } from "../brand/Brand";
import { Avatar } from "../ui";
import { PageBoundary } from "../ui/PageBoundary";
import { NotificationBell } from "./NotificationBell";
import { useDismiss } from "./useDismiss";

export interface NavItem { to: string; label: string; icon: LucideIcon; keywords?: string; badge?: number }
export interface NavGroup { label: string; items: NavItem[] }

export function ThemeToggle({ className = "icon-btn" }: { className?: string }) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return <button type="button" onClick={toggle} className={className} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} title={dark ? "Light mode" : "Dark mode"}>{dark ? <Sun size={19} aria-hidden /> : <Moon size={19} aria-hidden />}</button>;
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
    <div ref={ref} className="relative hidden w-72 xl:block">
      <Search size={16} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
      <input ref={input} role="combobox" aria-expanded={open} aria-controls="quick-results" aria-label="Search pages" placeholder="Enter your page search (Ctrl+K)" value={q}
        className="w-full !pl-9" onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setAt(0); setOpen(true); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setAt((a) => Math.min(a + 1, found.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setAt((a) => Math.max(a - 1, 0)); }
          if (e.key === "Enter" && found[at]) go(found[at].to);
        }} />
      {open && (
        <ul id="quick-results" role="listbox" className="popover animate-pop absolute right-0 top-12 z-50 max-h-80 w-full overflow-y-auto p-1.5">
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

function UserMenu({ settingsTo, onSignOut }: { settingsTo: string; onSignOut: () => void }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  if (!user) return null;
  const item = "flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium";
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open} aria-label="Account menu" className="block rounded-full ring-offset-2 transition hover:scale-105">
        <Avatar src={user.avatar} name={user.full_name} size={40} />
      </button>
      {open && (
        <div role="menu" className="popover animate-pop absolute right-0 top-12 z-50 w-48 p-1.5">
          <Link role="menuitem" to={settingsTo} onClick={() => setOpen(false)} className={`${item} hover:bg-slate-100`}><Settings size={16} aria-hidden />Settings</Link>
          <button role="menuitem" type="button" onClick={() => { setOpen(false); onSignOut(); }} className={`${item} text-red-700 hover:bg-red-50`}><LogOut size={16} aria-hidden />Logout</button>
        </div>)}
    </div>
  );
}

function SidebarNav({ groups, label }: { groups: NavGroup[]; label: string }) {
  return (
    <nav aria-label={label} className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
      {groups.map((g) => (
        <div key={g.label}>
          <p className="mb-1.5 px-3 text-[11px] font-bold uppercase tracking-[0.12em] text-[#7f98ae]">{g.label}</p>
          <ul className="space-y-0.5">
            {g.items.map(({ to, label: text, icon: Icon, badge }) => (
              <li key={to}>
                <NavLink to={to} className={({ isActive }) => `side-link ${isActive ? "side-link-active" : ""}`}>
                  <Icon size={18} aria-hidden className="shrink-0" /><span className="flex-1 truncate">{text}</span>
                  {!!badge && <span className="rounded-full bg-white/20 px-1.5 text-[11px] font-bold">{badge}</span>}
                </NavLink>
              </li>))}
          </ul>
        </div>))}
    </nav>
  );
}

function SidebarUser({ roleLabel, settingsTo }: { roleLabel: string; settingsTo: string }) {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <Link to={settingsTo} className="m-3 flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.06] p-3 transition hover:bg-white/[0.12]" aria-label="Your account settings">
      <Avatar src={user.avatar} name={user.full_name} size={44} />
      <span className="min-w-0 leading-tight">
        <span className="block truncate text-sm font-bold text-white">{user.full_name}</span>
        <span className="block truncate text-xs text-[#a9bfd1]" title={user.email}>{user.email}</span>
        <span className="mt-1 inline-block max-w-full truncate rounded-full bg-white/10 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide text-[#e3eef7]">{roleLabel}</span>
      </span>
    </Link>
  );
}

export function AppShell({ groups, brand, brandCaption, base, navLabel, roleLabel, headerActions, children }: {
  groups: NavGroup[]; brand: Brand; brandCaption: string; base: string; navLabel: string; roleLabel: string; headerActions?: ReactNode; children: ReactNode;
}) {
  const { signOut } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const { pathname } = useLocation();
  useRealtime(true);
  const flat = useMemo(() => groups.flatMap((g) => g.items.map((i) => ({ ...i, group: g.label }))), [groups]);
  const current = [...flat].sort((a, b) => b.to.length - a.to.length).find((i) => pathname === i.to || pathname.startsWith(i.to + "/"));
  const extra = pathname.startsWith(`${base}/notifications`) ? "Notifications" : pathname.startsWith(`${base}/settings`) ? "Settings" : undefined;
  const title = current?.label ?? extra ?? brand.name;
  useEffect(() => { setDrawer(false); window.scrollTo(0, 0); }, [pathname]);
  useEffect(() => { document.title = `${title} · ${brand.name}`; return () => { document.title = "NTS Pharmacy System"; }; }, [title, brand.name]);
  useEffect(() => {
    if (!drawer) return;
    const key = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [drawer]);
  // The chosen brand colour drives buttons, tabs and highlights; it is set on <html> so dialogs (portals) share it.
  useEffect(() => {
    const root = document.documentElement.style;
    root.setProperty("--brand", brand.color); root.setProperty("--brand-2", brand.color2); root.setProperty("--on-brand", readableOn(brand.color));
    return () => { ["--brand", "--brand-2", "--on-brand"].forEach((p) => root.removeProperty(p)); };
  }, [brand.color, brand.color2]);
  const leave = () => signOut({ brand });
  const settingsTo = `${base}/settings`;

  const sidebar = (mobile: boolean) => (
    <>
      <Link to={`${base}/dashboard`} className="flex h-[4.5rem] shrink-0 items-center gap-3 border-b border-white/10 px-4">
        {brand.logo ? <img src={brand.logo} alt="" className="h-11 w-11 shrink-0 rounded-xl bg-[#fff] object-contain p-1" /> : <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#fff] text-lg font-black" style={{ color: "#0b1324" }}>{brand.name[0]}</span>}
        <span className="min-w-0"><span className="block truncate text-sm font-bold text-white">{brand.name}</span><span className="block truncate text-xs text-[#93abc0]">{brandCaption}</span></span>
      </Link>
      <SidebarNav groups={groups} label={mobile ? `${navLabel} (mobile)` : navLabel} />
      <SidebarUser roleLabel={roleLabel} settingsTo={settingsTo} />
    </>
  );

  return (
    <BrandProvider brand={brand}>
      <div className="min-h-screen bg-canvas" style={{ "--brand": brand.color } as CSSProperties}>
        <a href="#app-main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:rounded focus:bg-white focus:p-2">Skip to content</a>
        <aside className="side no-print fixed inset-y-0 left-0 z-40 hidden w-64 flex-col lg:flex">{sidebar(false)}</aside>
        {drawer && (
          <div className="no-print fixed inset-0 z-[60] lg:hidden">
            <div className="backdrop animate-fade absolute inset-0" onClick={() => setDrawer(false)} />
            <aside role="dialog" aria-modal="true" aria-label="Menu" className="side animate-drawer absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col">
              <button type="button" autoFocus onClick={() => setDrawer(false)} aria-label="Close menu" className="absolute right-2 top-5 z-10 rounded-lg p-1.5 text-white/80 hover:bg-white/10"><X size={18} /></button>
              {sidebar(true)}
            </aside>
          </div>)}
        <div className="flex min-h-screen min-w-0 flex-col lg:pl-64">
          <header className="topbar no-print sticky top-0 z-30 h-[4.5rem]">
            <div className="mx-auto flex h-full w-[94%] items-center gap-2 sm:w-[90%] sm:gap-3">
              <button type="button" onClick={() => setDrawer(true)} aria-label="Open menu" className="icon-btn lg:hidden"><Menu size={20} /></button>
              <div className="min-w-0 flex-1">
                <nav aria-label="Breadcrumb"><ol className="flex items-center gap-1 text-xs text-muted"><li className="hidden truncate sm:block">{brand.name}</li>{current && <><li aria-hidden className="hidden sm:block"><ChevronRight size={12} /></li><li className="hidden truncate sm:block">{current.group}</li></>}</ol></nav>
                <p className="truncate text-[0.95rem] font-bold">{title}</p>
              </div>
              <QuickSearch items={flat} />
              {headerActions}
              <ThemeToggle />
              <NotificationBell base={base} />
              <UserMenu settingsTo={settingsTo} onSignOut={leave} />
            </div>
          </header>
          <main id="app-main" className="page-wrap flex-1">
            <PageBoundary key={pathname}><Suspense fallback={<Loading />}><div className="animate-rise">{children}</div></Suspense></PageBoundary>
          </main>
        </div>
      </div>
    </BrandProvider>
  );
}
