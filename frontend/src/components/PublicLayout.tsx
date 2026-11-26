import { useQuery } from "@tanstack/react-query";
import { Menu, MessageCircle, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { HiddenLoginTrigger } from "./HiddenLoginTrigger";

export interface PlatformInfo { name: string; whatsapp_number: string; contact_email: string }
export const usePlatformInfo = () =>
  useQuery({ queryKey: ["platform-info"], queryFn: () => api<PlatformInfo>("/public/platform/"), staleTime: 300_000 });

/** Per-page SEO: title + meta description. */
export function usePageMeta(title: string, description: string) {
  useEffect(() => {
    document.title = `${title} | NTS Pharmacy System`;
    let m = document.querySelector('meta[name="description"]');
    if (!m) { m = document.createElement("meta"); m.setAttribute("name", "description"); document.head.appendChild(m); }
    m.setAttribute("content", description);
  }, [title, description]);
}

const nav = [["/features", "Features"], ["/solutions", "Solutions"], ["/pricing", "Pricing"], ["/about", "About"], ["/faq", "FAQ"], ["/contact", "Contact"]];
const legal = [["/legal/privacy", "Privacy"], ["/legal/terms", "Terms"], ["/legal/payment-refund", "Payments & refunds"], ["/legal/data-protection", "Data protection"], ["/legal/security", "Security"], ["/legal/cookies", "Cookies"]];

export function PublicLayout({ children }: { children: ReactNode }) {
  const { data } = usePlatformInfo();
  const wa = data?.whatsapp_number?.replace(/\D/g, "");
  const [menu, setMenu] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setMenu(false), [pathname]);
  const link = ({ isActive }: { isActive: boolean }) => `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive ? "bg-teal-50 text-teal-800" : "text-slate-600 hover:bg-slate-100 hover:text-ink"}`;
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-2">Skip to content</a>
      <header className="sticky top-0 z-40 border-b border-line bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-5 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5 font-bold text-navy"><img src="/logo.webp" alt="" className="h-9 w-9" /><span className="whitespace-nowrap">NTS Pharmacy System</span></Link>
          <HiddenLoginTrigger />
          <nav aria-label="Primary" className="hidden items-center gap-1 lg:flex">
            {nav.map(([to, label]) => <NavLink key={to} to={to} className={link}>{label}</NavLink>)}
          </nav>
          <button type="button" className="grid h-10 w-10 place-items-center rounded-lg hover:bg-slate-100 lg:hidden" aria-expanded={menu} aria-label={menu ? "Close menu" : "Open menu"} onClick={() => setMenu((m) => !m)}>{menu ? <X size={20} /> : <Menu size={20} />}</button>
        </div>
        {menu && <nav aria-label="Primary (mobile)" className="animate-pop grid gap-1 border-t border-line px-4 py-3 lg:hidden">{nav.map(([to, label]) => <NavLink key={to} to={to} className={link}>{label}</NavLink>)}</nav>}
      </header>
      <div id="main" className="flex-1">{children}</div>
      <footer className="bg-navy px-5 py-10 text-sm text-slate-300 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <p className="flex items-center gap-2.5"><img src="/logo.webp" alt="" className="h-8 w-8 rounded-lg bg-white p-0.5" />© {new Date().getFullYear()} NTS Pharmacy System</p>
          <nav aria-label="Legal" className="flex flex-wrap gap-x-5 gap-y-2">{legal.map(([to, l]) => <Link key={to} to={to} className="hover:text-white hover:underline">{l}</Link>)}</nav>
        </div>
      </footer>
      {wa && (
        <a href={`https://wa.me/${wa}`} target="_blank" rel="noopener noreferrer" aria-label="Chat with us on WhatsApp"
           className="fixed bottom-5 right-5 z-50 grid h-14 w-14 place-items-center rounded-full bg-green-600 text-white shadow-lg hover:bg-green-700">
          <MessageCircle aria-hidden />
        </a>
      )}
    </div>
  );
}
