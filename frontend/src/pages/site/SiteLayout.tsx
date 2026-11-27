import { LayoutDashboard, LogOut, ShoppingCart, UserRound } from "lucide-react";
import { createContext, Suspense, useContext, useEffect, type CSSProperties } from "react";
import { Link, NavLink, Outlet, useLocation, useParams } from "react-router-dom";
import { Loading, PageLoader, BrandProvider } from "../../components/brand/Brand";
import { SiteNotFound, SystemNotFound } from "../../components/NotFound";
import { ThemeToggle } from "../../components/layout/AppShell";
import { PageBoundary } from "../../components/ui/PageBoundary";
import { MobileMenu } from "../../components/site/motion";
import { ErrorState } from "../../components/ui";
import { ApiError } from "../../lib/api";
import { SiteFooter } from "../../components/site/SiteFooter";
import { useAuth } from "../../lib/auth";
import { contactOf, useGlobalContent } from "../../lib/pages";
import { useCart } from "../../lib/cart";
import { readableOn } from "../../lib/format";
import { useRealtime } from "../../lib/realtime";
import { brandOf, homeFor, useSiteQuery, type Site } from "../../lib/site";

export type { Site };
const SiteCtx = createContext<Site | null>(null);
export const useSite = () => useContext(SiteCtx);

/** Any unknown address under a pharmacy keeps the pharmacy's own header, colours and footer. */
export function SiteNotFoundPage() {
  const site = useSite();
  return site ? <SiteNotFound site={site} /> : null;
}

/** Each pharmacy's public website: branding comes from the API (name, logo, colours). */
export default function SiteLayout() {
  const { slug = "" } = useParams();
  const { user, signOut } = useAuth();
  const cart = useCart(slug);
  const { pathname } = useLocation();
  const mine = user?.tenant_slug === slug;
  useRealtime(!!mine && user.role === "customer" && user.email_verified);
  const q = useSiteQuery(slug);
  const global = useGlobalContent(slug);
  const color = q.data?.primary_color, color2 = q.data?.secondary_color;
  useEffect(() => {
    if (!color) return;
    const root = document.documentElement.style;
    root.setProperty("--brand", color); root.setProperty("--brand-2", color2 ?? color); root.setProperty("--on-brand", readableOn(color));
    return () => { ["--brand", "--brand-2", "--on-brand"].forEach((p) => root.removeProperty(p)); };
  }, [color, color2]);
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  if (q.isLoading) return <PageLoader label="Opening the pharmacy…" />;
  if (q.error instanceof ApiError && q.error.status === 404) return <SystemNotFound />; // no such pharmacy
  if (!q.data) return <main className="grid min-h-screen place-items-center p-6"><div className="w-full max-w-md"><ErrorState onRetry={() => q.refetch()}>This pharmacy could not be loaded. Check your connection.</ErrorState></div></main>;
  const s = q.data;
  const brand = brandOf(s);
  const customer = mine && user.role === "customer";
  const link = ({ isActive }: { isActive: boolean }) => `block whitespace-nowrap rounded-full px-3.5 py-2 text-sm font-semibold transition-colors ${isActive ? "bg-slate-100" : "hover:bg-slate-100"}`;
  const pages: [string, string][] = [[`/${slug}`, "Home"], [`/${slug}/about`, "About"], [`/${slug}/products`, "Products"], [`/${slug}/services`, "Services"], [`/${slug}/institutional`, "Bulk orders"], [`/${slug}/contact`, "Contact"]];
  const logo = s.logo ? <img src={s.logo} alt={`${s.name} logo`} width="44" height="44" className="h-11 w-11 rounded-xl border border-line bg-[#fff] object-contain p-1" /> : <span className="grid h-11 w-11 place-items-center rounded-xl text-lg font-black" style={{ background: "var(--brand)", color: "var(--on-brand)" }}>{s.name[0]}</span>;
  const account = mine
    ? <Link to={homeFor(user)} className="btn btn-primary btn-sm !rounded-full">{customer ? <><UserRound size={15} aria-hidden />My account</> : <><LayoutDashboard size={15} aria-hidden />Dashboard</>}</Link>
    : <Link to={`/${slug}/login`} className="btn btn-primary btn-sm !rounded-full"><UserRound size={15} aria-hidden />Sign in</Link>;
  const out = () => signOut({ brand, to: `/${slug}` });
  return (
    <SiteCtx.Provider value={s}>
      <BrandProvider brand={brand}>
        <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-2">Skip to content</a>
        <div className="flex min-h-screen flex-col overflow-x-clip" style={{ "--brand": s.primary_color, "--brand-2": s.secondary_color } as CSSProperties}>
          <header className="topbar sticky top-0 z-40">
            <div style={{ background: "linear-gradient(90deg, var(--brand), var(--brand-2))" }} className="h-1" />
            <div className="site-wrap flex h-[4.5rem] items-center gap-2">
              <Link to={`/${slug}`} className="mr-auto flex min-w-0 items-center gap-3 text-lg font-extrabold">{logo}<span className="truncate">{s.name}</span></Link>
              <nav aria-label="Pharmacy" className="hidden items-center gap-0.5 xl:flex">{pages.map(([to, label]) => <NavLink key={to} to={to} end className={link}>{label}</NavLink>)}</nav>
              <ThemeToggle />
              <Link to={`/${slug}/checkout`} aria-label={`Cart, ${cart.count} items`} className="icon-btn relative">
                <ShoppingCart size={20} aria-hidden />{cart.count > 0 && <span key={cart.count} className="animate-pop absolute right-0.5 top-0.5 grid h-5 min-w-5 place-items-center rounded-full px-1 text-[11px] font-bold" style={{ background: "var(--brand)", color: "var(--on-brand)" }}>{cart.count}</span>}
              </Link>
              <div className="hidden items-center gap-2 sm:flex">{account}{mine && <button type="button" onClick={out} className="icon-btn" aria-label="Sign out" title="Sign out"><LogOut size={19} aria-hidden /></button>}</div>
              <MobileMenu wide title={s.name}>{[
                ...pages.map(([to, label]) => <NavLink key={to} to={to} end className={link}>{label}</NavLink>),
                <div key="account" className="mt-3 grid">{account}</div>,
                !mine && <Link key="reg" to={`/${slug}/register`} className="btn btn-outline w-full">Create an account</Link>,
                mine && <button key="out" type="button" className="btn btn-outline w-full" onClick={out}><LogOut size={16} aria-hidden />Sign out</button>,
              ]}</MobileMenu>
            </div>
          </header>
          <main id="content" className="flex-1"><PageBoundary key={pathname}><Suspense fallback={<div className="site-wrap py-8"><Loading /></div>}><Outlet /></Suspense></PageBoundary></main>
          <SiteFooter name={s.name} logo={logo} about={global.footerAbout || s.description || "Your trusted local pharmacy."}
            contact={contactOf(s, global)}
            columns={[{ title: "Our pharmacy", links: pages }, { title: "Your account", links: [[`/${slug}/login`, "Sign in"], [`/${slug}/register`, "Create an account"], [`/${slug}/checkout`, "My cart"], [`/${slug}/forgot-password`, "Forgot password"]] }]}
            credit={<>Powered by <Link to="/">NTS Pharmacy System</Link></>} />
        </div>
      </BrandProvider>
    </SiteCtx.Provider>
  );
}
