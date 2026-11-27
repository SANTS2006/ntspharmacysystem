/** "Page not found" pages: the platform's own, each pharmacy's (website and signed-out addresses), and one inside the signed-in areas. */
import { ArrowLeft, Home, LayoutDashboard, LogIn, SearchX, type LucideIcon } from "lucide-react";
import { useEffect, type CSSProperties, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { readableOn } from "../lib/format";
import { brandOf, useSiteQuery, type Site } from "../lib/site";
import { OrbitLogo, PageLoader, PLATFORM_BRAND, useBrand, type Brand } from "./brand/Brand";
import { ThemeToggle } from "./layout/AppShell";
import { PublicLayout } from "./PublicLayout";
import { useSeo } from "./site/motion";
import { Scene3D } from "./three/Scene3D";

type Quick = [to: string, label: string];

function BackButton({ className }: { className: string }) {
  const nav = useNavigate();
  // A visitor who typed or followed the address directly has nowhere to go back to.
  if (typeof window !== "undefined" && window.history.length <= 1) return null;
  return <button type="button" className={className} onClick={() => nav(-1)}><ArrowLeft size={17} aria-hidden />Go back</button>;
}

function Hero({ brand, title, message, home, links, showLogo, children }: { brand: Brand; title: string; message: string; home: { to: string; label: string; icon: LucideIcon }; links: Quick[]; showLogo?: boolean; children?: ReactNode }) {
  const { pathname } = useLocation();
  const HomeIcon = home.icon;
  return (
    <section className="hero-surface relative flex flex-1 items-center overflow-hidden" style={{ "--brand": brand.color, "--brand-2": brand.color2 } as CSSProperties}>
      <Scene3D color={brand.color} color2={brand.color2} className="absolute inset-0 opacity-25 lg:left-1/2 lg:opacity-100" />
      <div className="site-wrap animate-rise relative py-16 text-center lg:text-left">
        <div className="mx-auto max-w-xl lg:mx-0">
          {showLogo && <div className="mb-5 flex justify-center lg:justify-start"><OrbitLogo size={84} brand={brand} /></div>}
          <p className="gradient-text text-[7rem] font-black leading-none tracking-tighter sm:text-[10rem]" aria-hidden>404</p>
          <h1 className="mt-2 text-2xl !font-extrabold sm:text-4xl"><span className="sr-only">Error 404: </span>{title}</h1>
          <p className="mt-3 text-lg text-white/80">{message}</p>
          <p className="glass mt-4 inline-block max-w-full truncate rounded-full px-4 py-1.5 font-mono text-sm text-white/85" title={pathname}>{pathname}</p>
          <div className="mt-7 flex flex-wrap justify-center gap-3 lg:justify-start">
            <Link to={home.to} className="btn btn-primary !min-h-12 !px-7"><HomeIcon size={17} aria-hidden />{home.label}</Link>
            <BackButton className="btn glass !min-h-12 !px-7 text-white" />
          </div>
          <nav aria-label="Helpful pages" className="mt-8 flex flex-wrap justify-center gap-x-5 gap-y-2 text-sm lg:justify-start">{links.map(([to, label]) => <Link key={to} to={to} className="font-semibold text-white/80 hover:text-white">{label}</Link>)}</nav>
          {children}
        </div>
      </div>
    </section>
  );
}

const SYSTEM_LINKS: Quick[] = [["/features", "Features"], ["/pricing", "Pricing"], ["/faq", "FAQ"], ["/contact", "Contact us"]];

/** The platform's 404, also used when an address names a pharmacy that does not exist. */
export function SystemNotFound() {
  useSeo("Page not found | NTS Pharmacy System", "The page you are looking for could not be found.", { noindex: true });
  return (
    <PublicLayout>
      <main className="flex min-h-[38rem] flex-col"><Hero brand={PLATFORM_BRAND} title="Page not found" message="The page you are looking for does not exist, or it has moved." home={{ to: "/", label: "Go to the home page", icon: Home }} links={SYSTEM_LINKS} /></main>
    </PublicLayout>
  );
}

const pharmacyLinks = (slug: string): Quick[] => [[`/${slug}/products`, "Products"], [`/${slug}/services`, "Services"], [`/${slug}/institutional`, "Bulk orders"], [`/${slug}/login`, "Sign in"]];
const pharmacyMessage = (name: string) => `We could not find that page at ${name}. Check the address, or use one of the links below.`;

/** Shown inside a pharmacy's website, between its own header and footer. */
export function SiteNotFound({ site }: { site: Site }) {
  useSeo(`Page not found | ${site.name}`, "The page you are looking for could not be found.", { noindex: true, image: site.logo });
  return <div className="flex min-h-[36rem] flex-col"><Hero brand={brandOf(site)} title="Page not found" message={pharmacyMessage(site.name)} home={{ to: `/${site.slug}`, label: "Pharmacy home page", icon: Home }} links={pharmacyLinks(site.slug)} /></div>;
}

/** A whole-screen pharmacy 404 for unknown staff or customer addresses opened by someone who is not signed in to that area. */
export function PharmacyNotFound() {
  const { slug = "" } = useParams();
  const q = useSiteQuery(slug);
  const color = q.data?.primary_color, color2 = q.data?.secondary_color;
  useEffect(() => {
    if (!color) return;
    const root = document.documentElement.style;
    root.setProperty("--brand", color); root.setProperty("--brand-2", color2 ?? color); root.setProperty("--on-brand", readableOn(color));
    return () => { ["--brand", "--brand-2", "--on-brand"].forEach((p) => root.removeProperty(p)); };
  }, [color, color2]);
  if (q.isLoading) return <PageLoader />;
  return q.data ? <PharmacyScreen slug={slug} site={q.data} /> : <SystemNotFound />;
}

function PharmacyScreen({ slug, site }: { slug: string; site: Site }) {
  useSeo(`Page not found | ${site.name}`, "The page you are looking for could not be found.", { noindex: true, image: site.logo });
  const brand = brandOf(site);
  return (
    <main className="flex min-h-screen flex-col">
      <div className="topbar"><div className="site-wrap flex h-16 items-center justify-between gap-3"><Link to={`/${slug}`} className="min-w-0 truncate font-extrabold">{brand.name}</Link><ThemeToggle /></div></div>
      <Hero showLogo brand={brand} title="Page not found" message={pharmacyMessage(brand.name)} home={{ to: `/${slug}`, label: "Pharmacy home page", icon: LogIn }} links={pharmacyLinks(slug)} />
    </main>
  );
}

/** Inside a signed-in area: the sidebar and top bar stay, only the content says the page is missing. */
export function ShellNotFound({ area }: { area: "admin" | "account" | "platform" }) {
  const { slug } = useParams();
  const brand = useBrand();
  const { pathname } = useLocation();
  useEffect(() => { const t = window.setTimeout(() => { document.title = `Page not found · ${brand.name}`; }, 0); return () => window.clearTimeout(t); }, [brand.name, pathname]);
  const home = area === "platform" ? "/platform/dashboard" : `/${slug}/${area}/dashboard`;
  return (
    <section className="card animate-pop mx-auto max-w-2xl overflow-hidden text-center">
      <div className="h-1.5" style={{ background: "linear-gradient(90deg, var(--brand), var(--brand-2))" }} />
      <div className="px-6 py-12">
        <div className="flex justify-center"><OrbitLogo size={92} /></div>
        <p className="mt-6 flex items-center justify-center gap-3 text-6xl font-black text-primary" aria-hidden><SearchX size={44} />404</p>
        <h1 className="page-title mt-3"><span className="sr-only">Error 404: </span>Page not found</h1>
        <p className="mx-auto mt-2 max-w-md text-muted">There is nothing at this address in {brand.name}.</p>
        <p className="mx-auto mt-3 inline-block max-w-full truncate rounded-full border border-line px-4 py-1.5 font-mono text-sm text-muted" title={pathname}>{pathname}</p>
        <div className="mt-7 flex flex-wrap justify-center gap-3"><Link to={home} className="btn btn-primary"><LayoutDashboard size={16} aria-hidden />Go to dashboard</Link><BackButton className="btn btn-outline" /></div>
      </div>
    </section>
  );
}
