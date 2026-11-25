import { useQuery } from "@tanstack/react-query";
import { MessageCircle } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { api } from "../lib/api";
import { HiddenLoginTrigger } from "./HiddenLoginTrigger";

export interface PlatformInfo { name: string; whatsapp_number: string; contact_email: string }
export const usePlatformInfo = () =>
  useQuery({ queryKey: ["platform-info"], queryFn: () => api<PlatformInfo>("/public/platform/"), staleTime: 300_000 });

/** Per-page SEO: title + meta description. */
export function usePageMeta(title: string, description: string) {
  useEffect(() => {
    document.title = `${title} | PharmaCloud`;
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
  return (
    <div className="flex min-h-screen flex-col text-slate-800">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-2">Skip to content</a>
      <header className="sticky top-0 z-40 flex flex-wrap items-center gap-x-6 border-b bg-white/90 px-6 backdrop-blur">
        <Link to="/" className="flex items-center gap-2 py-2 text-lg font-bold text-teal-800"><img src="/logo.webp" alt="" className="h-9 w-9" />PharmaCloud</Link>
        <HiddenLoginTrigger />
        <nav aria-label="Primary" className="flex flex-wrap gap-4 py-2 text-sm">
          {nav.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "font-semibold text-teal-800" : "hover:text-teal-800")}>{label}</NavLink>
          ))}
        </nav>
      </header>
      <div id="main" className="flex-1">{children}</div>
      <footer className="border-t bg-slate-50 px-6 py-8 text-sm">
        <div className="mx-auto flex max-w-5xl flex-wrap justify-between gap-4">
          <p>© {new Date().getFullYear()} PharmaCloud</p>
          <nav aria-label="Legal" className="flex flex-wrap gap-4">{legal.map(([to, l]) => <Link key={to} to={to} className="hover:underline">{l}</Link>)}</nav>
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
