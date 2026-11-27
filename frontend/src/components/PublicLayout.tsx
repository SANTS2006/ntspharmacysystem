import { useQuery } from "@tanstack/react-query";
import { ArrowRight, MessageCircle } from "lucide-react";
import { SiteFooter } from "./site/SiteFooter";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { useGlobalContent } from "../lib/pages";
import { HiddenLoginTrigger } from "./HiddenLoginTrigger";
import { ThemeToggle } from "./layout/AppShell";
import { MobileMenu, useSeo } from "./site/motion";

export interface PlatformInfo { name: string; whatsapp_number: string; contact_email: string; google_client_id?: string }
export const usePlatformInfo = () =>
  useQuery({ queryKey: ["platform-info"], queryFn: () => api<PlatformInfo>("/public/platform/"), staleTime: 300_000 });

export const usePageMeta = (title: string, description: string, jsonLd?: object) => useSeo(`${title} | NTS Pharmacy System`, description, { jsonLd });

const nav = [["/features", "Features"], ["/solutions", "Solutions"], ["/pricing", "Pricing"], ["/about", "About"], ["/faq", "FAQ"], ["/contact", "Contact"]];
const legal = [["/legal/privacy", "Privacy"], ["/legal/terms", "Terms"], ["/legal/payment-refund", "Payments & refunds"], ["/legal/data-protection", "Data protection"], ["/legal/security", "Security"], ["/legal/cookies", "Cookies"]];

export function PublicLayout({ children }: { children: ReactNode }) {
  const { data } = usePlatformInfo();
  const global = useGlobalContent();
  const wa = (global.whatsapp || data?.whatsapp_number || "").replace(/\D/g, "");
  const { pathname } = useLocation();
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on(); window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  const link = ({ isActive }: { isActive: boolean }) => `block rounded-full px-3.5 py-2 text-sm font-semibold transition-colors ${isActive ? "bg-teal-50 text-teal-800" : "text-slate-700 hover:bg-slate-100"}`;
  const brand = <Link to="/" className="flex items-center gap-2.5 font-extrabold"><img src="/logo.webp" alt="NTS Pharmacy System logo" width="40" height="40" className="h-10 w-10" /><span className="whitespace-nowrap">NTS Pharmacy System</span></Link>;
  return (
    <div className="flex min-h-screen flex-col overflow-x-clip">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-2">Skip to content</a>
      <header className={`topbar sticky top-0 z-40 transition-shadow ${scrolled ? "shadow-pop" : ""}`}>
        <div className="site-wrap flex h-[4.5rem] items-center gap-3">
          {brand}
          <HiddenLoginTrigger />
          <nav aria-label="Primary" className="hidden items-center gap-1 lg:flex">
            {nav.map(([to, label]) => <NavLink key={to} to={to} className={link}>{label}</NavLink>)}
          </nav>
          <ThemeToggle />
          <MobileMenu title="Menu">{[<NavLink key="home" to="/" end className={link}>Home</NavLink>, ...nav.map(([to, label]) => <NavLink key={to} to={to} className={link}>{label}</NavLink>), <Link key="cta" to="/contact" className="btn btn-primary mt-3 w-full">Register your pharmacy</Link>]}</MobileMenu>
        </div>
      </header>
      <div id="main" className="flex-1">{children}</div>
      <SiteFooter name="NTS Pharmacy System" logo={<img src="/logo.webp" alt="" width="44" height="44" className="h-11 w-11 rounded-xl bg-[#fff] p-1" />}
        about={global.footerAbout || "Inventory, prescriptions, point of sale, mobile money and finance, with a branded website for every pharmacy."}
        contact={{ ...global, email: global.email || data?.contact_email || "" }}
        columns={[{ title: "Explore", links: [["/", "Home"], ...(nav as [string, string][])] }, { title: "Legal", links: legal as [string, string][] }]}
        action={<Link to="/contact" className="btn !bg-[#fff] !text-[#0b2257]">Get started<ArrowRight size={16} aria-hidden /></Link>} />
      {wa && (
        <a href={`https://wa.me/${wa}`} target="_blank" rel="noopener noreferrer" aria-label="Chat with us on WhatsApp"
           className="fixed bottom-5 right-5 z-50 grid h-14 w-14 place-items-center rounded-full bg-green-700 text-white shadow-lg transition hover:scale-110">
          <MessageCircle aria-hidden />
        </a>
      )}
    </div>
  );
}
