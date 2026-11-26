import { LayoutDashboard, LogOut, Mail, MapPin, Phone, ShoppingCart, UserRound } from "lucide-react";
import { createContext, Suspense, useContext, useEffect, type CSSProperties } from "react";
import { Link, NavLink, Outlet, useLocation, useParams } from "react-router-dom";
import { Loading, PageLoader, BrandProvider } from "../../components/brand/Brand";
import { ThemeToggle } from "../../components/layout/AppShell";
import { PageBoundary } from "../../components/ui/PageBoundary";
import { MobileMenu, ScrollProgress } from "../../components/site/motion";
import { useAuth } from "../../lib/auth";
import { useCart } from "../../lib/cart";
import { readableOn } from "../../lib/format";
import { useRealtime } from "../../lib/realtime";
import { brandOf, homeFor, useSiteQuery, type Site } from "../../lib/site";

export type { Site };
const SiteCtx = createContext<Site | null>(null);
export const useSite = () => useContext(SiteCtx);

/** Each pharmacy's public website: branding comes from the API (name, logo, colours). */
export default function SiteLayout() {
  const { slug = "" } = useParams();
  const { user, signOut } = useAuth();
  const cart = useCart(slug);
  const { pathname } = useLocation();
  const mine = user?.tenant_slug === slug;
  useRealtime(!!mine && user.role === "customer" && user.email_verified);
  const q = useSiteQuery(slug);
  const color = q.data?.primary_color, color2 = q.data?.secondary_color;
  useEffect(() => {
    if (!color) return;
    const root = document.documentElement.style;
    root.setProperty("--brand", color); root.setProperty("--brand-2", color2 ?? color); root.setProperty("--on-brand", readableOn(color));
    return () => { ["--brand", "--brand-2", "--on-brand"].forEach((p) => root.removeProperty(p)); };
  }, [color, color2]);
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  if (q.isLoading) return <PageLoader label="Opening the pharmacy…" />;
  if (q.isError || !q.data) return (
    <main className="grid min-h-screen place-items-center p-6">
      <div className="card max-w-md p-8 text-center"><img src="/logo.webp" alt="" className="mx-auto h-14 w-14" /><h1 className="page-title mt-4">Pharmacy not found</h1><p className="mt-2 text-sm text-muted">This pharmacy website is not available.</p><Link to="/" className="btn btn-primary mt-5">Go to NTS Pharmacy System</Link></div>
    </main>);
  const s = q.data;
  const brand = brandOf(s);
  const customer = mine && user.role === "customer";
  const link = ({ isActive }: { isActive: boolean }) => `block whitespace-nowrap rounded-full px-3.5 py-2 text-sm font-semibold transition-colors ${isActive ? "bg-slate-100" : "hover:bg-slate-100"}`;
  const pages: [string, string][] = [[`/${slug}`, "Home"], [`/${slug}/products`, "Products"], [`/${slug}/services`, "Services"], [`/${slug}/institutional`, "Bulk & institutions"]];
  const logo = s.logo ? <img src={s.logo} alt={`${s.name} logo`} width="44" height="44" className="h-11 w-11 rounded-xl border border-line bg-[#fff] object-contain p-1" /> : <span className="grid h-11 w-11 place-items-center rounded-xl text-lg font-black" style={{ background: "var(--brand)", color: "var(--on-brand)" }}>{s.name[0]}</span>;
  const account = mine
    ? <Link to={homeFor(user)} className="btn btn-primary btn-sm !rounded-full">{customer ? <><UserRound size={15} aria-hidden />My account</> : <><LayoutDashboard size={15} aria-hidden />Dashboard</>}</Link>
    : <Link to={`/${slug}/login`} className="btn btn-primary btn-sm !rounded-full"><UserRound size={15} aria-hidden />Sign in</Link>;
  const out = () => signOut({ brand, to: `/${slug}` });
  return (
    <SiteCtx.Provider value={s}>
      <BrandProvider brand={brand}>
        <ScrollProgress />
        <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-2">Skip to content</a>
        <div className="flex min-h-screen flex-col overflow-x-clip" style={{ "--brand": s.primary_color, "--brand-2": s.secondary_color } as CSSProperties}>
          <header className="topbar sticky top-0 z-40">
            <div style={{ background: "linear-gradient(90deg, var(--brand), var(--brand-2))" }} className="h-1" />
            <div className="site-wrap flex h-[4.5rem] items-center gap-2">
              <Link to={`/${slug}`} className="mr-auto flex min-w-0 items-center gap-3 text-lg font-extrabold">{logo}<span className="truncate">{s.name}</span></Link>
              <nav aria-label="Pharmacy" className="hidden items-center gap-1 lg:flex">{pages.map(([to, label]) => <NavLink key={to} to={to} end className={link}>{label}</NavLink>)}</nav>
              <ThemeToggle />
              <Link to={`/${slug}/checkout`} aria-label={`Cart, ${cart.count} items`} className="icon-btn relative">
                <ShoppingCart size={20} aria-hidden />{cart.count > 0 && <span key={cart.count} className="animate-pop absolute right-0.5 top-0.5 grid h-5 min-w-5 place-items-center rounded-full px-1 text-[11px] font-bold" style={{ background: "var(--brand)", color: "var(--on-brand)" }}>{cart.count}</span>}
              </Link>
              <div className="hidden items-center gap-2 sm:flex">{account}{mine && <button type="button" onClick={out} className="icon-btn" aria-label="Sign out" title="Sign out"><LogOut size={19} aria-hidden /></button>}</div>
              <MobileMenu title={s.name}>{[
                ...pages.map(([to, label]) => <NavLink key={to} to={to} end className={link}>{label}</NavLink>),
                <div key="account" className="mt-3 grid">{account}</div>,
                !mine && <Link key="reg" to={`/${slug}/register`} className="btn btn-outline w-full">Create an account</Link>,
                mine && <button key="out" type="button" className="btn btn-outline w-full" onClick={out}><LogOut size={16} aria-hidden />Sign out</button>,
              ]}</MobileMenu>
            </div>
          </header>
          <main id="content" className="flex-1"><PageBoundary key={pathname}><Suspense fallback={<div className="site-wrap py-8"><Loading /></div>}><Outlet /></Suspense></PageBoundary></main>
          <footer className="side border-t border-white/10 text-sm">
            <div className="site-wrap grid gap-8 py-12 md:grid-cols-3">
              <div><p className="flex items-center gap-3 text-lg font-bold text-white">{logo}{s.name}</p><p className="mt-3 max-w-sm text-[#a9bfd1]">{s.description || "Your trusted local pharmacy."}</p></div>
              <nav aria-label="Footer"><p className="mb-3 font-bold text-white">Quick links</p><ul className="space-y-2">{[...pages, [`/${slug}/login`, "Sign in"], [`/${slug}/register`, "Create an account"]].map(([to, label]) => <li key={to}><Link to={to} className="text-[#a9bfd1] hover:text-white hover:underline">{label}</Link></li>)}</ul></nav>
              <address className="space-y-2.5 not-italic text-[#a9bfd1]"><p className="font-bold text-white">Contact us</p>
                {(s.address || s.city) && <p className="flex gap-2"><MapPin size={16} aria-hidden className="mt-0.5 shrink-0" />{[s.address, s.city, s.country].filter(Boolean).join(", ")}</p>}
                {s.contact_phone && <a className="flex gap-2 hover:text-white" href={`tel:${s.contact_phone}`}><Phone size={16} aria-hidden className="mt-0.5 shrink-0" />{s.contact_phone}</a>}
                {s.contact_email && <a className="flex gap-2 break-all hover:text-white" href={`mailto:${s.contact_email}`}><Mail size={16} aria-hidden className="mt-0.5 shrink-0" />{s.contact_email}</a>}
              </address>
            </div>
            <p className="site-wrap border-t border-white/10 py-5 text-xs text-[#8ea7bb]">© {new Date().getFullYear()} {s.name} · Powered by <Link to="/" className="underline">NTS Pharmacy System</Link></p>
          </footer>
        </div>
      </BrandProvider>
    </SiteCtx.Provider>
  );
}
