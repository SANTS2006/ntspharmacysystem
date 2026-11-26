import { useQuery } from "@tanstack/react-query";
import { ShoppingCart } from "lucide-react";
import { createContext, Suspense, useContext, useEffect } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCart } from "../../lib/cart";
import { useRealtime } from "../../lib/realtime";
import { Loading } from "../../components/ui";

export interface Site { name: string; slug: string; description: string; logo: string | null; primary_color: string; secondary_color: string; contact_email: string; contact_phone: string; address: string; city: string; online_payments?: boolean }
const SiteCtx = createContext<Site | null>(null);
export const useSite = () => useContext(SiteCtx);

/** Each pharmacy's public website: branding comes from the API (name, logo, colours). */
export default function SiteLayout() {
  const { slug = "" } = useParams();
  const { user, signOut } = useAuth();
  const cart = useCart(slug);
  useRealtime(!!user && user.tenant_slug === slug && user.role === "customer" && user.email_verified);
  const q = useQuery({ queryKey: ["site", slug], queryFn: () => api<Site>(`/public/pharmacies/${slug}/`), retry: false });
  useEffect(() => {
    if (q.data) { document.documentElement.style.setProperty("--brand", q.data.primary_color); document.title = `${q.data.name} | Online pharmacy`; }
    return () => { document.documentElement.style.setProperty("--brand", "#059669"); };
  }, [q.data]);
  if (q.isLoading) return <div className="p-8"><Loading /></div>;
  if (q.isError || !q.data) return (
    <main className="grid min-h-screen place-items-center p-6">
      <div className="card max-w-md p-8 text-center"><img src="/logo.webp" alt="" className="mx-auto h-14 w-14" /><h1 className="page-title mt-4">Pharmacy not found</h1><p className="mt-2 text-sm text-muted">This pharmacy website is not available.</p><Link to="/" className="btn btn-primary mt-5">Go to NTS Pharmacy System</Link></div>
    </main>);
  const s = q.data;
  const isCustomer = user?.tenant_slug === slug && user.role === "customer";
  const link = ({ isActive }: { isActive: boolean }) => `whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive ? "bg-white/20 text-white" : "text-white/85 hover:bg-white/10 hover:text-white"}`;
  return (
    <SiteCtx.Provider value={s}>
      <a href="#content" className="sr-only focus:not-sr-only">Skip to content</a>
      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-40 text-white shadow-sm" style={{ background: "var(--brand)" }}>
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 sm:px-6">
            <Link to={`/${slug}`} className="flex min-w-0 items-center gap-2.5 text-lg font-bold">{s.logo ? <img src={s.logo} alt="" className="h-9 w-9 rounded-lg bg-white object-contain p-0.5" /> : <img src="/logo.webp" alt="" className="h-9 w-9 rounded-lg bg-white p-0.5" />}<span className="truncate">{s.name}</span></Link>
            <Link to={`/${slug}/checkout`} aria-label={`Cart, ${cart.items.length} items`} className="relative ml-auto grid h-10 w-10 place-items-center rounded-lg hover:bg-white/10 lg:order-3 lg:ml-0">
              <ShoppingCart size={20} aria-hidden />{cart.items.length > 0 && <span className="absolute right-0 top-0 grid h-5 min-w-5 place-items-center rounded-full bg-white px-1 text-[11px] font-bold text-ink">{cart.items.length}</span>}
            </Link>
            <nav aria-label="Pharmacy" className="flex w-full items-center gap-1 overflow-x-auto lg:order-2 lg:ml-auto lg:w-auto">
              <NavLink to={`/${slug}/products`} className={link}>Products</NavLink><NavLink to={`/${slug}/services`} className={link}>Services</NavLink><NavLink to={`/${slug}/institutional`} className={link}>Bulk &amp; institutions</NavLink>
              {isCustomer ? <><NavLink to={`/${slug}/orders`} className={link}>My orders</NavLink><NavLink to={`/${slug}/feedback`} className={link}>Feedback</NavLink><button onClick={signOut} className="whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium text-white/85 hover:bg-white/10">Sign out</button></>
                : <><NavLink to={`/${slug}/login`} className={link}>Sign in</NavLink><NavLink to={`/${slug}/register`} className={link}>Register</NavLink></>}
            </nav>
          </div>
        </header>
        <main id="content" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6"><Suspense fallback={<Loading />}><Outlet /></Suspense></main>
        <footer className="bg-navy px-4 py-8 text-sm text-slate-300 sm:px-6">
          <div className="mx-auto flex max-w-6xl flex-col gap-2 md:flex-row md:justify-between">
            <p className="font-semibold text-white">{s.name}</p>
            <p>{[[s.address, s.city].filter(Boolean).join(", "), s.contact_phone, s.contact_email].filter(Boolean).join(" · ")}</p>
          </div>
        </footer>
      </div>
    </SiteCtx.Provider>
  );
}
