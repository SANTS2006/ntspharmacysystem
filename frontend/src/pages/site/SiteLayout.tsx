import { useQuery } from "@tanstack/react-query";
import { ShoppingCart } from "lucide-react";
import { createContext, useContext, useEffect } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCart } from "../../lib/cart";
import { useRealtime } from "../../lib/realtime";

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
    return () => { document.documentElement.style.setProperty("--brand", "#015dc9"); };
  }, [q.data]);
  if (q.isLoading) return <p className="p-8">Loading…</p>;
  if (q.isError || !q.data) return <main className="p-8"><h1 className="text-xl font-semibold">Pharmacy not found</h1><p>This pharmacy website is not available.</p></main>;
  const s = q.data;
  const isCustomer = user?.tenant_slug === slug && user.role === "customer";
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "font-semibold underline" : "hover:underline");
  return (
    <SiteCtx.Provider value={s}>
      <a href="#content" className="sr-only focus:not-sr-only">Skip to content</a>
      <header className="text-white" style={{ background: "var(--brand)" }}>
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-4 px-4 py-3">
          <Link to={`/${slug}`} className="flex items-center gap-2 text-lg font-bold">{s.logo && <img src={s.logo} alt="" className="h-8 w-8 rounded bg-white object-contain" />}{s.name}</Link>
          <nav aria-label="Pharmacy" className="ml-auto flex flex-wrap items-center gap-4 text-sm">
            <NavLink to={`/${slug}/products`} className={link}>Products</NavLink><NavLink to={`/${slug}/services`} className={link}>Services</NavLink><NavLink to={`/${slug}/institutional`} className={link}>Bulk &amp; institutions</NavLink>
            {isCustomer ? <><NavLink to={`/${slug}/orders`} className={link}>My orders</NavLink><NavLink to={`/${slug}/feedback`} className={link}>Feedback</NavLink><button onClick={signOut} className="underline">Sign out</button></>
              : <><NavLink to={`/${slug}/login`} className={link}>Sign in</NavLink><NavLink to={`/${slug}/register`} className={link}>Register</NavLink></>}
            <NavLink to={`/${slug}/checkout`} className={link} aria-label={`Cart, ${cart.items.length} items`}><ShoppingCart size={18} aria-hidden className="inline" /> {cart.items.length}</NavLink>
          </nav>
        </div>
      </header>
      <main id="content" className="mx-auto max-w-5xl px-4 py-8"><Outlet /></main>
      <footer className="border-t bg-slate-50 px-4 py-6 text-sm text-slate-600"><div className="mx-auto max-w-5xl">{s.name} · {[s.address, s.city].filter(Boolean).join(", ")} · {s.contact_phone} · {s.contact_email}</div></footer>
    </SiteCtx.Provider>
  );
}
