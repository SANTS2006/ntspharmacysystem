/** The footer shared by the main website and every pharmacy website. */
import { Clock, ExternalLink, Mail, MapPin, MessageCircle, Phone } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { GlobalContent } from "../../lib/pages";

export function SiteFooter({ name, logo, about, contact, columns, action, credit }: { name: string; logo: ReactNode; about: string; contact: GlobalContent; columns: { title: string; links: [string, string][] }[]; action?: ReactNode; credit?: ReactNode }) {
  const row = "flex gap-2.5 text-[#c3d4f2]";
  const point = contact.latitude && contact.longitude ? `${contact.latitude},${contact.longitude}` : contact.address;
  const wa = contact.whatsapp.replace(/\D/g, "");
  return (
    <footer className="side border-t border-white/10 text-sm">
      <div className="h-1" style={{ background: "linear-gradient(90deg, var(--brand), #0c9cfc, var(--brand))" }} />
      <div className="site-wrap grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1.3fr]">
        <div>
          <p className="flex items-center gap-3 text-lg font-extrabold text-white">{logo}<span>{name}</span></p>
          <p className="mt-4 max-w-sm leading-7 text-[#c3d4f2]">{about}</p>
          {contact.social.length > 0 && <ul className="mt-5 flex flex-wrap gap-2">{contact.social.filter((s) => s.title && s.href).map((s) => <li key={s.href}><a href={s.href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-full border border-white/20 px-3.5 py-1.5 font-semibold text-white transition hover:bg-white/10">{s.title}<ExternalLink size={12} aria-hidden /></a></li>)}</ul>}
          {action && <div className="mt-6">{action}</div>}
        </div>
        {columns.map((c) => <nav key={c.title} aria-label={c.title}><p className="mb-4 text-xs font-bold uppercase tracking-[0.14em] text-white">{c.title}</p><ul className="space-y-2.5">{c.links.map(([to, label]) => <li key={to}><Link to={to} className="inline-block text-[#c3d4f2] transition hover:translate-x-1 hover:text-white">{label}</Link></li>)}</ul></nav>)}
        <address className="space-y-3 not-italic">
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.14em] text-white">Contact us</p>
          {contact.address && <p className={row}><MapPin size={16} aria-hidden className="mt-0.5 shrink-0" />{contact.address}</p>}
          {contact.phone && <a className={`${row} hover:text-white`} href={`tel:${contact.phone}`}><Phone size={16} aria-hidden className="mt-0.5 shrink-0" />{contact.phone}</a>}
          {contact.email && <a className={`${row} break-all hover:text-white`} href={`mailto:${contact.email}`}><Mail size={16} aria-hidden className="mt-0.5 shrink-0" />{contact.email}</a>}
          {wa && <a className={`${row} hover:text-white`} href={`https://wa.me/${wa}`} target="_blank" rel="noopener noreferrer"><MessageCircle size={16} aria-hidden className="mt-0.5 shrink-0" />WhatsApp</a>}
          {contact.hours && <p className={`${row} whitespace-pre-line`}><Clock size={16} aria-hidden className="mt-0.5 shrink-0" />{contact.hours}</p>}
          {point && <a href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(point)}`} target="_blank" rel="noopener noreferrer" className="btn btn-sm !bg-white/10 !text-white">Get directions</a>}
        </address>
      </div>
      <div className="site-wrap flex flex-wrap items-center justify-between gap-2 border-t border-white/10 py-5 text-xs text-[#9db4de]"><p>© {new Date().getFullYear()} {name}. All rights reserved.</p>{credit && <p>{credit}</p>}</div>
    </footer>
  );
}
