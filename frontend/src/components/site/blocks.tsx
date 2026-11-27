/** Renders website-builder content. All values are drawn as plain text; the only formatting is **bold**, bullet lines and paragraphs. */
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, ChevronDown, ChevronLeft, ChevronRight, Clock, Mail, MapPin, MessageCircle, Navigation, Phone, Pill, Plus, Send } from "lucide-react";
import { Fragment, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useCart } from "../../lib/cart";
import { money } from "../../lib/format";
import type { Block, GlobalContent, Hero, PageContent } from "../../lib/pages";
import { Scene3D } from "../three/Scene3D";
import { FormFields, Spinner, errorMessage, initialValues, useToast, type FieldDef } from "../ui";
import { Reveal, Tilt } from "./motion";

export interface SiteInfo { slug?: string; name: string; contact: GlobalContent; colors?: [string, string] }

export function Inline({ text }: { text: string }) {
  return <>{text.split(/(\*\*[^*]+\*\*)/g).map((part, i) => part.startsWith("**") && part.endsWith("**") && part.length > 4 ? <strong key={i} className="font-extrabold">{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>)}</>;
}

export function RichText({ text, className = "" }: { text: string; className?: string }) {
  if (!text) return null;
  return (
    <div className={`space-y-3 ${className}`}>
      {text.split(/\n{2,}/).map((chunk, i) => {
        const lines = chunk.split("\n");
        return lines.every((l) => l.startsWith("- "))
          ? <ul key={i} className="space-y-2">{lines.map((l, n) => <li key={n} className="flex gap-2.5"><Check size={17} aria-hidden className="mt-1 shrink-0 text-primary" /><span><Inline text={l.slice(2)} /></span></li>)}</ul>
          : <p key={i} className="whitespace-pre-line leading-7"><Inline text={chunk} /></p>;
      })}
    </div>
  );
}

/** Internal paths stay in the app; everything else opens normally. */
export function SmartLink({ href, className, children }: { href: string; className?: string; children: ReactNode }) {
  if (href.startsWith("/")) return <Link to={href} className={className}>{children}</Link>;
  return <a href={href || "#"} className={className} {...(href.startsWith("https://") ? { target: "_blank", rel: "noopener noreferrer" } : {})}>{children}</a>;
}

export function HeroSection({ hero, info }: { hero: Hero; info: SiteInfo }) {
  const scene = hero.model !== "none" && !hero.image;
  return (
    <section className="hero-surface relative overflow-hidden">
      {scene && <Scene3D variant={hero.model} color={info.colors?.[0]} color2={info.colors?.[1]} className="absolute inset-0 opacity-25 lg:left-[48%] lg:opacity-100" />}
      <div className={`site-wrap relative grid min-h-[26rem] items-center gap-10 py-14 lg:min-h-[32rem] ${hero.image ? "lg:grid-cols-2" : ""}`}>
        <div className="animate-rise max-w-2xl">
          {hero.eyebrow && <p className="glass inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-bold">{hero.eyebrow}</p>}
          <h1 className="mt-4 text-4xl !font-extrabold leading-[1.1] tracking-tight sm:text-5xl xl:text-6xl"><Inline text={hero.title} /> {hero.highlight && <span className="gradient-text">{hero.highlight}</span>}</h1>
          {hero.subtitle && <p className="mt-5 max-w-xl text-lg leading-8 text-white/85"><Inline text={hero.subtitle} /></p>}
          {(hero.primary.label || hero.secondary.label) && <div className="mt-8 flex flex-wrap gap-3">
            {hero.primary.label && <SmartLink href={hero.primary.href} className="btn !min-h-12 !bg-[#fff] !px-7 !text-[#0b2257]">{hero.primary.label}<ArrowRight size={17} aria-hidden /></SmartLink>}
            {hero.secondary.label && <SmartLink href={hero.secondary.href} className="btn glass !min-h-12 !px-7 text-white">{hero.secondary.label}</SmartLink>}
          </div>}
        </div>
        {hero.image && <img src={hero.image} alt="" className="animate-pop mx-auto max-h-96 w-full rounded-3xl object-cover shadow-pop" />}
      </div>
    </section>
  );
}

export function MapCard({ label, address, latitude, longitude, phone, className = "" }: { label?: string; address: string; latitude?: string | number | null; longitude?: string | number | null; phone?: string; className?: string }) {
  const point = latitude && longitude ? `${latitude},${longitude}` : address;
  if (!point) return null;
  const q = encodeURIComponent(point);
  return (
    <figure className={`card flex h-full flex-col overflow-hidden ${className}`}>
      <iframe title={`Map of ${label || address || point}`} src={`https://maps.google.com/maps?q=${q}&z=15&output=embed`} loading="lazy" referrerPolicy="no-referrer-when-downgrade" className="h-60 w-full border-0" />
      <figcaption className="flex flex-1 flex-col gap-2 p-4 text-sm">
        {label && <b className="text-base">{label}</b>}
        <span className="flex gap-2 text-muted"><MapPin size={16} aria-hidden className="mt-0.5 shrink-0" />{address || point}</span>
        {phone && <a href={`tel:${phone}`} className="flex gap-2 text-muted"><Phone size={16} aria-hidden className="mt-0.5 shrink-0" />{phone}</a>}
        <a href={`https://www.google.com/maps/dir/?api=1&destination=${q}`} target="_blank" rel="noopener noreferrer" className="btn btn-primary btn-sm mt-auto self-start"><Navigation size={14} aria-hidden />Get directions</a>
      </figcaption>
    </figure>
  );
}

const CONTACT_FIELDS: FieldDef[] = [{ name: "name", label: "Full name", maxLength: 150 }, { name: "email", label: "Email address", type: "email" }, { name: "phone", label: "Phone number", type: "tel", required: false }, { name: "subject", label: "Subject", maxLength: 200 }, { name: "message", label: "Message", type: "textarea", maxLength: 3000 }];

export function ContactForm({ slug }: { slug?: string }) {
  const [values, setValues] = useState(() => initialValues(CONTACT_FIELDS));
  const [trap, setTrap] = useState(""); const [busy, setBusy] = useState(false); const [state, setState] = useState<{ ok: boolean; t: string } | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setState(null);
    try { await api(slug ? `/public/pharmacies/${slug}/contact/` : "/public/contact/", { method: "POST", body: { ...values, website: trap } }); setState({ ok: true, t: "Thank you. Your message has been sent." }); setValues(initialValues(CONTACT_FIELDS)); }
    catch (err) { setState({ ok: false, t: errorMessage(err) }); }
    setBusy(false);
  };
  return (
    <form onSubmit={submit} className="card space-y-4 p-6 sm:p-8">
      {state && <p role={state.ok ? "status" : "alert"} className={`alert ${state.ok ? "alert-success" : "alert-error"}`}>{state.t}</p>}
      <FormFields fields={CONTACT_FIELDS.map((f, i) => (i === 0 ? { ...f, wide: false } : f))} values={values} set={(n, v) => setValues((x) => ({ ...x, [n]: v }))} />
      <input tabIndex={-1} autoComplete="off" aria-hidden className="hidden" value={trap} onChange={(e) => setTrap(e.target.value)} />
      <button className="btn btn-primary !min-h-12 w-full" disabled={busy}>{busy ? <Spinner /> : <Send size={16} aria-hidden />}Send message</button>
    </form>
  );
}

function ContactDetails({ contact }: { contact: GlobalContent }) {
  const rows = [[Mail, "Email", contact.email, `mailto:${contact.email}`], [Phone, "Phone", contact.phone, `tel:${contact.phone}`], [MessageCircle, "WhatsApp", contact.whatsapp, `https://wa.me/${contact.whatsapp.replace(/\D/g, "")}`], [Clock, "Opening hours", contact.hours, ""], [MapPin, "Address", contact.address, ""]] as const;
  return (
    <div className="space-y-3">
      {rows.filter((r) => r[2]).map(([Icon, label, value, href]) => <div key={label} className="card card-hover flex gap-3 p-4"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700"><Icon size={19} aria-hidden /></span><div className="min-w-0"><p className="text-xs font-bold uppercase tracking-wide text-muted">{label}</p>{href ? <a href={href} className="break-words font-semibold text-primary">{value}</a> : <p className="whitespace-pre-line break-words font-semibold">{value}</p>}</div></div>)}
      <MapCard address={contact.address} latitude={contact.latitude} longitude={contact.longitude} />
    </div>
  );
}

function Cards({ b }: { b: Block }) {
  return <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{b.items.map((i, n) => (
    <Reveal as="li" key={n} delay={(n % 3) * 90} from={b.animation === "none" ? "up" : b.animation} className="h-full">
      <Tilt className="card flex h-full flex-col overflow-hidden">
        {i.image && <img src={i.image} alt="" loading="lazy" className="h-44 w-full object-cover" />}
        <div className="flex flex-1 flex-col p-6">{!i.image && <span className="mb-4 grid h-12 w-12 place-items-center rounded-2xl font-black text-white shadow-lg" style={{ background: "linear-gradient(135deg, var(--brand), #0c9cfc)" }} aria-hidden>{String(n + 1).padStart(2, "0")}</span>}<h3 className="section-title !text-lg"><Inline text={i.title} /></h3><RichText text={i.text} className="mt-2 text-sm text-muted" />{i.href && <SmartLink href={i.href} className="btn-link mt-4 self-start">Learn more<ArrowRight size={13} aria-hidden /></SmartLink>}</div>
      </Tilt>
    </Reveal>))}</ul>;
}

function Accordion({ b }: { b: Block }) {
  return <div className="mx-auto max-w-3xl space-y-3">{b.items.map((i, n) => <Reveal key={n} delay={n * 50}><details className="card group p-5"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-bold"><span><Inline text={i.title} /></span><ChevronDown size={18} aria-hidden className="shrink-0 transition-transform group-open:rotate-180" /></summary><div className="animate-rise mt-3 space-y-3">{i.image && <img src={i.image} alt="" loading="lazy" className="max-h-72 w-full rounded-xl object-cover" />}<RichText text={i.text} className="text-muted" /></div></details></Reveal>)}</div>;
}

function Carousel({ b }: { b: Block }) {
  const track = useRef<HTMLUListElement>(null);
  const move = (dir: number) => track.current?.scrollBy({ left: dir * track.current.clientWidth * 0.8, behavior: "smooth" });
  return (
    <div role="region" aria-roledescription="carousel" aria-label={b.title || "Highlights"}>
      <ul ref={track} tabIndex={0} className="flex snap-x snap-mandatory gap-5 overflow-x-auto pb-4">{b.items.map((i, n) => (
        <li key={n} className="card w-[85%] shrink-0 snap-start overflow-hidden sm:w-[48%] lg:w-[32%]">{i.image && <img src={i.image} alt="" loading="lazy" className="h-52 w-full object-cover" />}<div className="p-5"><h3 className="section-title !text-lg"><Inline text={i.title} /></h3><RichText text={i.text} className="mt-2 text-sm text-muted" />{i.href && <SmartLink href={i.href} className="btn-link mt-4">Learn more</SmartLink>}</div></li>))}</ul>
      <div className="mt-2 flex justify-center gap-3"><button type="button" className="btn btn-outline btn-sm !rounded-full" aria-label="Previous" onClick={() => move(-1)}><ChevronLeft size={16} /></button><button type="button" className="btn btn-outline btn-sm !rounded-full" aria-label="Next" onClick={() => move(1)}><ChevronRight size={16} /></button></div>
    </div>
  );
}

function ItemsView({ b }: { b: Block }) {
  if (b.layout === "accordion") return <Accordion b={b} />;
  if (b.layout === "carousel") return <Carousel b={b} />;
  if (b.layout === "steps") return <ol className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">{b.items.map((i, n) => <Reveal as="li" key={n} from={n % 2 ? "right" : "left"} delay={n * 80}><div className="card card-hover h-full p-6"><span className="text-4xl font-black text-primary opacity-60">{String(n + 1).padStart(2, "0")}</span>{i.image && <img src={i.image} alt="" loading="lazy" className="mt-3 h-32 w-full rounded-xl object-cover" />}<h3 className="section-title mt-3"><Inline text={i.title} /></h3><RichText text={i.text} className="mt-2 text-sm text-muted" /></div></Reveal>)}</ol>;
  if (b.layout === "list") return <ul className="mx-auto max-w-3xl space-y-3">{b.items.map((i, n) => <Reveal as="li" key={n} from="left" delay={n * 50}><div className="card flex gap-4 p-4">{i.image ? <img src={i.image} alt="" loading="lazy" className="h-20 w-20 shrink-0 rounded-xl object-cover" /> : <Check size={20} aria-hidden className="mt-0.5 shrink-0 text-primary" />}<div><h3 className="font-bold"><Inline text={i.title} /></h3><RichText text={i.text} className="mt-1 text-sm text-muted" /></div></div></Reveal>)}</ul>;
  return <Cards b={b} />;
}

interface BranchRow { id: number; name: string; address: string; phone: string; latitude: string | null; longitude: string | null }
function Branches({ info }: { info: SiteInfo }) {
  const q = useQuery({ queryKey: ["branches-public", info.slug], queryFn: () => api<BranchRow[]>(`/public/pharmacies/${info.slug}/branches/`), enabled: !!info.slug });
  return <ul className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{q.data?.map((b) => <li key={b.id} className="animate-rise">{b.address || b.latitude ? <MapCard label={b.name} address={b.address} latitude={b.latitude} longitude={b.longitude} phone={b.phone} /> : <div className="card h-full p-5"><b>{b.name}</b><p className="mt-2 text-sm text-muted">Address not listed yet.</p></div>}</li>)}</ul>;
}

interface Med { id: number; name: string; strength: string; price: string; category: string; requires_prescription: boolean; image?: string | null }
function Products({ info }: { info: SiteInfo }) {
  const slug = info.slug ?? ""; const cart = useCart(slug); const toast = useToast();
  const q = useQuery({ queryKey: ["catalogue", slug, "", "", 1], queryFn: () => api<{ results: Med[] }>(`/public/pharmacies/${slug}/catalogue/?page=1&search=`), enabled: !!slug });
  if (!q.data?.results.length) return <p className="text-center text-muted">Products will appear here soon.</p>;
  return (
    <><ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{q.data.results.slice(0, 8).map((m, n) => <Reveal as="li" key={m.id} delay={(n % 4) * 80}><Tilt className="card flex h-full flex-col overflow-hidden" max={5}><div className="grid h-36 place-items-center bg-teal-50">{m.image ? <img src={m.image} alt={m.name} loading="lazy" className="h-full w-full object-cover" /> : <Pill size={40} aria-hidden className="text-primary opacity-60" />}</div><div className="flex flex-1 flex-col p-4"><h3 className="font-bold">{m.name} <span className="font-normal text-muted">{m.strength}</span></h3><p className="text-xs text-muted">{m.category}</p><div className="mt-auto flex items-center justify-between pt-3"><b className="text-lg">{money(m.price)}</b><button className="btn btn-primary btn-sm" onClick={() => { cart.add({ id: m.id, name: m.name, price: m.price, requires_prescription: m.requires_prescription }); toast(`${m.name} added to your cart.`); }}><Plus size={14} aria-hidden />Add</button></div></div></Tilt></Reveal>)}</ul>
      <p className="mt-6 text-center"><Link to={`/${slug}/products`} className="btn btn-outline">View all products<ArrowRight size={15} aria-hidden /></Link></p></>
  );
}

interface Svc { id: number; name: string; description: string; price: string | null; duration_minutes: number; requires_booking: boolean; image: string | null }
function Services({ info }: { info: SiteInfo }) {
  const q = useQuery({ queryKey: ["pub-services", info.slug], queryFn: () => api<Svc[]>(`/public/pharmacies/${info.slug}/services/`), enabled: !!info.slug });
  if (q.data && !q.data.length) return <p className="text-center text-muted">No services are listed yet.</p>;
  const book = `/${info.slug}/login?next=${encodeURIComponent(`/${info.slug}/account/care`)}`;
  return <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{q.data?.map((v, n) => <Reveal as="li" key={v.id} delay={(n % 3) * 90}><Tilt className="card flex h-full flex-col overflow-hidden" max={5}>{v.image && <img src={v.image} alt={v.name} loading="lazy" className="h-40 w-full object-cover" />}<div className="flex flex-1 flex-col p-5"><h3 className="section-title !text-lg">{v.name}</h3><p className="mt-2 text-sm text-muted">{v.description}</p><p className="mt-4 flex items-center gap-2 text-sm font-semibold"><Clock size={15} aria-hidden />{v.duration_minutes} min · {v.price ? `from ${money(v.price)}` : "ask us for the price"}</p>{v.requires_booking && <Link to={book} className="btn btn-outline btn-sm mt-4 self-start">Book online</Link>}</div></Tilt></Reveal>)}</ul>;
}

interface PlanRow { code: string; name: string; price: string; currency: string; interval: string; max_branches: number; max_users: number; features: string[] }
function Plans() {
  const q = useQuery({ queryKey: ["plans"], queryFn: () => api<PlanRow[]>("/public/plans/") });
  if (q.data && !q.data.length) return <p className="empty">Pricing is being finalised. <Link to="/contact" className="font-bold text-primary">Contact us</Link> for a quote.</p>;
  return <ul className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{q.data?.map((p, i) => <Reveal as="li" key={p.code} delay={i * 90}><Tilt className="card h-full p-7"><h3 className="text-xl font-bold">{p.name}</h3><p className="my-3 text-4xl font-extrabold">{p.currency} {Number(p.price).toLocaleString()}<span className="text-sm font-normal text-muted"> / {p.interval === "yearly" ? "year" : "month"}</span></p><ul className="space-y-2 text-sm">{[`Up to ${p.max_branches} branch(es)`, `Up to ${p.max_users} users`, ...p.features].map((f) => <li key={f} className="flex gap-2"><Check aria-hidden size={17} className="shrink-0 text-primary" />{f}</li>)}</ul><Link to="/contact" className="btn btn-primary mt-6 w-full">Choose {p.name}</Link></Tilt></Reveal>)}</ul>;
}

function Body({ b, info }: { b: Block; info: SiteInfo }) {
  switch (b.type) {
    case "text": return <div className="mx-auto max-w-3xl"><RichText text={b.body} className="text-lg" /></div>;
    case "items": return <ItemsView b={b} />;
    case "split": return (
      <div className="grid items-center gap-10 lg:grid-cols-2">
        <Reveal from={b.imageSide === "left" ? "right" : "left"} className={b.imageSide === "left" ? "lg:order-2" : ""}>{b.title && <h2 className="mb-4 text-2xl !font-extrabold md:text-4xl"><Inline text={b.title} /></h2>}<RichText text={b.body} className="text-lg text-muted" />{b.button.label && <SmartLink href={b.button.href} className="btn btn-primary mt-6">{b.button.label}</SmartLink>}</Reveal>
        <Reveal from="zoom">{b.image ? <img src={b.image} alt="" loading="lazy" className="max-h-[28rem] w-full rounded-3xl object-cover shadow-pop" /> : b.model !== "none" ? <div className="hero-surface relative h-80 overflow-hidden rounded-3xl"><Scene3D variant={b.model} color={info.colors?.[0]} color2={info.colors?.[1]} className="absolute inset-0" /></div> : null}</Reveal>
      </div>);
    case "gallery": return <ul className="grid grid-cols-2 gap-4 lg:grid-cols-4">{b.items.filter((i) => i.image).map((i, n) => <Reveal as="li" key={n} from="zoom" delay={(n % 4) * 70}><figure className="card card-hover overflow-hidden"><img src={i.image} alt={i.title} loading="lazy" className="h-52 w-full object-cover" />{i.title && <figcaption className="p-3 text-sm font-semibold"><Inline text={i.title} /></figcaption>}</figure></Reveal>)}</ul>;
    case "stats": return <dl className="grid grid-cols-2 gap-5 lg:grid-cols-4">{b.items.map((i, n) => <Reveal key={n} from="zoom" delay={n * 80}><div className="card card-hover p-6 text-center"><dt className="text-4xl font-black text-primary">{i.title}</dt><dd className="mt-2 text-sm text-muted"><Inline text={i.text} /></dd></div></Reveal>)}</dl>;
    case "cta": return <Reveal from="zoom"><div className="hero-surface relative overflow-hidden rounded-3xl p-8 text-center md:p-14">{b.image && <img src={b.image} alt="" className="absolute inset-0 h-full w-full object-cover opacity-20" />}<div className="relative"><h2 className="text-2xl !font-extrabold md:text-4xl"><Inline text={b.title} /></h2>{b.subtitle && <p className="mx-auto mt-3 max-w-xl text-white/85"><Inline text={b.subtitle} /></p>}<RichText text={b.body} className="mx-auto mt-3 max-w-xl text-white/85" />{b.button.label && <SmartLink href={b.button.href} className="btn mt-7 !min-h-12 !bg-[#fff] !px-7 !text-[#0b2257]">{b.button.label}</SmartLink>}</div></div></Reveal>;
    case "branches": return <Branches info={info} />;
    case "products": return <Products info={info} />;
    case "services": return <Services info={info} />;
    case "plans": return <Plans />;
    case "contact": return <div className="grid items-start gap-6 lg:grid-cols-[1.4fr_1fr]"><Reveal from="left"><ContactForm slug={info.slug} /></Reveal><Reveal from="right"><ContactDetails contact={info.contact} /></Reveal></div>;
    case "map": return <div className="mx-auto max-w-3xl"><MapCard label={info.name} address={info.contact.address} latitude={info.contact.latitude} longitude={info.contact.longitude} phone={info.contact.phone} /></div>;
  }
}

export function Blocks({ blocks, info }: { blocks: Block[]; info: SiteInfo }) {
  return <>{blocks.map((b, n) => {
    const ownHeading = b.type === "split" || b.type === "cta";
    const surface = b.background === "tinted" ? "border-y border-line bg-white" : b.background === "brand" ? "bg-teal-50" : "";
    return (
      <section key={`${b.type}-${n}`} className={`py-12 md:py-16 ${surface}`} aria-label={b.title || undefined}>
        <div className="site-wrap">
          {!ownHeading && (b.title || b.subtitle) && <Reveal className="mx-auto mb-10 max-w-2xl text-center">{b.title && <h2 className="text-2xl !font-extrabold tracking-tight md:text-4xl"><Inline text={b.title} /></h2>}{b.subtitle && <p className="mt-3 text-muted"><Inline text={b.subtitle} /></p>}</Reveal>}
          {!ownHeading && b.type !== "text" && b.body && <RichText text={b.body} className="mx-auto mb-8 max-w-3xl text-center text-muted" />}
          <Body b={b} info={info} />
          {b.type === "items" && b.button.label && <p className="mt-8 text-center"><SmartLink href={b.button.href} className="btn btn-outline">{b.button.label}<ArrowRight size={15} aria-hidden /></SmartLink></p>}
        </div>
      </section>);
  })}</>;
}

export function PageView({ content, info, children }: { content: PageContent; info: SiteInfo; children?: ReactNode }) {
  return <><HeroSection hero={content.hero} info={info} />{children}<Blocks blocks={content.blocks} info={info} /></>;
}
