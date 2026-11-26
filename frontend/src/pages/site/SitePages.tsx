/** A pharmacy's public website: home, products, checkout and the in-branch QR menu. */
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarClock, Check, Clock, FileCheck2, MapPin, Minus, PackageSearch, Phone, Pill, Plus, Search, ShoppingCart, Smartphone, Trash2, Truck } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Reveal, Tilt, useSeo } from "../../components/site/motion";
import { Scene3D } from "../../components/three/Scene3D";
import { EmptyState, Loading, Pagination, Spinner, errorMessage, placeholderFor, useConfirm, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCart } from "../../lib/cart";
import { money } from "../../lib/format";
import { useSite } from "./SiteLayout";

interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
interface Med { id: number; name: string; strength: string; dosage_form: string; category: string; price: string; description: string; requires_prescription: boolean; available?: boolean; image?: string | null }
interface Branch { id: number; name: string; address: string; phone: string }
interface Svc { id: number; name: string; description: string; price: string | null; duration_minutes: number; requires_booking: boolean }

function ProductCard({ m, onAdd }: { m: Med; onAdd: () => void }) {
  return (
    <Tilt className="card flex h-full flex-col overflow-hidden" max={5}>
      <div className="relative grid h-36 place-items-center overflow-hidden" style={{ background: "linear-gradient(135deg, color-mix(in srgb, var(--brand) 16%, var(--color-surface)), color-mix(in srgb, var(--brand-2) 16%, var(--color-surface)))" }}>
        {m.image ? <img src={m.image} alt={m.name} loading="lazy" className="h-full w-full object-cover" /> : <Pill size={44} aria-hidden className="tilt-pop opacity-60" style={{ color: "var(--brand)" }} />}
        <span className="badge badge-neutral absolute left-3 top-3">{m.category}</span>
      </div>
      <div className="flex flex-1 flex-col p-4">
        <h3 className="section-title">{m.name} <span className="font-normal text-muted">{m.strength}</span></h3>
        <p className="text-sm text-muted">{m.dosage_form}</p>
        {m.requires_prescription && <p className="mt-2 flex items-start gap-1.5 text-xs font-semibold text-red-700"><FileCheck2 size={14} aria-hidden className="mt-px shrink-0" />Prescription only: upload it after ordering for pharmacist approval.</p>}
        <div className="mt-auto flex items-end justify-between gap-2 pt-4"><p className="text-xl font-extrabold">{money(m.price)}</p><button className="btn btn-primary btn-sm" onClick={onAdd}><Plus size={14} aria-hidden />Add<span className="sr-only"> {m.name} to cart</span></button></div>
      </div>
    </Tilt>
  );
}

function useAdd(slug: string) {
  const cart = useCart(slug); const toast = useToast();
  return (m: Med) => { cart.add({ id: m.id, name: m.name, price: m.price, requires_prescription: m.requires_prescription }); toast(`${m.name} added to your cart.`); };
}

// ---------------- home ----------------
export function SiteHome() {
  const { slug = "" } = useParams(); const s = useSite(); const add = useAdd(slug);
  const branches = useQuery({ queryKey: ["branches-public", slug], queryFn: () => api<Branch[]>(`/public/pharmacies/${slug}/branches/`) });
  const featured = useQuery({ queryKey: ["catalogue", slug, "", "", 1], queryFn: () => api<Page<Med>>(`/public/pharmacies/${slug}/catalogue/?page=1&search=`) });
  const services = useQuery({ queryKey: ["pub-services", slug], queryFn: () => api<Svc[]>(`/public/pharmacies/${slug}/services/`) });
  useSeo(`${s?.name ?? "Pharmacy"} | Online pharmacy`, (s?.description || `${s?.name} is an online pharmacy. Browse medicines, book services and order online.`).slice(0, 160), {
    image: s?.logo,
    jsonLd: s ? { "@context": "https://schema.org", "@type": "Pharmacy", name: s.name, description: s.description || undefined, url: `${location.origin}/${slug}`, logo: s.logo || undefined, image: s.logo || undefined, telephone: s.contact_phone || undefined, email: s.contact_email || undefined, address: { "@type": "PostalAddress", streetAddress: s.address || undefined, addressLocality: s.city || undefined, addressCountry: s.country || undefined } } : undefined,
  });
  const perks = [[PackageSearch, "Order online", "Browse our catalogue and order in a few taps."], [FileCheck2, "Pharmacist checked", "Prescription medicines are reviewed before they are supplied."], [Smartphone, s?.online_payments ? "Mobile money" : "Easy payment", s?.online_payments ? "Pay securely online with mobile money." : "Pay when you collect or on delivery."], [Truck, "Pickup or delivery", "Collect from a branch or have it brought to you."]] as const;
  return (
    <>
      <section className="hero-surface relative overflow-hidden">
        <Scene3D color={s?.primary_color} color2={s?.secondary_color} className="absolute inset-0 opacity-25 lg:left-[48%] lg:opacity-100" />
        <div className="site-wrap relative grid min-h-[32rem] items-center py-16 lg:min-h-[38rem]">
          <div className="animate-rise max-w-2xl">
            {s?.city && <p className="glass inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-bold"><MapPin size={14} aria-hidden />{[s.city, s.country].filter(Boolean).join(", ")}</p>}
            <h1 className="mt-5 text-4xl font-extrabold leading-[1.1] tracking-tight sm:text-5xl xl:text-6xl">{s?.name}</h1>
            <p className="mt-5 max-w-xl text-lg leading-8 text-white/85">{s?.description || "Your trusted local pharmacy: medicines, advice and services, online and in store."}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to={`/${slug}/products`} className="btn btn-primary !min-h-12 !px-7">Shop medicines<ArrowRight size={17} aria-hidden /></Link>
              <Link to={`/${slug}/services`} className="btn glass !min-h-12 !px-7 text-white"><CalendarClock size={17} aria-hidden />Our services</Link>
            </div>
          </div>
        </div>
      </section>
      <div className="site-wrap space-y-16 py-12 md:space-y-24 md:py-16">
        <section aria-label="Why choose us" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {perks.map(([I, t, d], i) => <Reveal key={t} delay={i * 80} className="h-full"><div className="card card-hover h-full p-6"><span className="grid h-12 w-12 place-items-center rounded-2xl" style={{ background: "linear-gradient(135deg, var(--brand), var(--brand-2))", color: "#fff" }}><I size={22} aria-hidden /></span><h2 className="mt-4 section-title">{t}</h2><p className="mt-1.5 text-sm text-muted">{d}</p></div></Reveal>)}
        </section>
        {!!featured.data?.results.length && <section>
          <Reveal className="mb-6 flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-2xl !font-extrabold md:text-3xl">Popular products</h2><p className="text-muted">A selection from our shelves.</p></div><Link className="btn btn-outline" to={`/${slug}/products`}>View all<ArrowRight size={16} aria-hidden /></Link></Reveal>
          <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{featured.data.results.slice(0, 8).map((m, i) => <Reveal as="li" key={m.id} delay={(i % 4) * 80}><ProductCard m={m} onAdd={() => add(m)} /></Reveal>)}</ul>
        </section>}
        {!!services.data?.length && <section>
          <Reveal><h2 className="mb-6 text-2xl !font-extrabold md:text-3xl">Services we offer</h2></Reveal>
          <ul className="grid gap-5 md:grid-cols-3">{services.data.slice(0, 6).map((v, i) => <Reveal as="li" key={v.id} from={i % 3 === 0 ? "left" : i % 3 === 2 ? "right" : "up"}><div className="card card-hover h-full p-6"><h3 className="section-title">{v.name}</h3><p className="mt-2 line-clamp-3 text-sm text-muted">{v.description}</p><p className="mt-4 flex items-center gap-2 text-sm font-semibold"><Clock size={15} aria-hidden />{v.duration_minutes} min{v.price && ` · from ${money(v.price)}`}</p></div></Reveal>)}</ul>
        </section>}
        <section>
          <Reveal><h2 className="mb-6 text-2xl !font-extrabold md:text-3xl">Visit our branches</h2></Reveal>
          {branches.isLoading && <Loading rows={2} />}
          <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{branches.data?.map((b, i) => <Reveal as="li" key={b.id} delay={(i % 3) * 90}><div className="card card-hover h-full p-6 text-sm"><p className="section-title">{b.name}</p><p className="mt-3 flex gap-2 text-muted"><MapPin size={16} aria-hidden className="mt-0.5 shrink-0" />{b.address || "Address not listed"}</p>{b.phone && <a href={`tel:${b.phone}`} className="mt-2 flex gap-2 text-muted hover:underline"><Phone size={16} aria-hidden className="mt-0.5 shrink-0" />{b.phone}</a>}</div></Reveal>)}</ul>
        </section>
      </div>
    </>
  );
}

// ---------------- products ----------------
export function Products() {
  const { slug = "" } = useParams(); const s = useSite(); const add = useAdd(slug);
  const [q, setQ] = useState(""); const [cat, setCat] = useState(""); const [page, setPage] = useState(1);
  useSeo(`Medicines and health products | ${s?.name}`, `Browse medicines and health products available from ${s?.name} and order online.`, { image: s?.logo });
  const cats = useQuery({ queryKey: ["cats", slug], queryFn: () => api<{ id: number; name: string }[]>(`/public/pharmacies/${slug}/categories/`) });
  const list = useQuery({ queryKey: ["catalogue", slug, q, cat, page], queryFn: () => api<Page<Med>>(`/public/pharmacies/${slug}/catalogue/?page=${page}&search=${encodeURIComponent(q)}${cat ? `&category=${cat}` : ""}`), placeholderData: (p) => p });
  const chip = (id: string, label: string) => <button key={id} type="button" aria-pressed={cat === id} onClick={() => { setCat(id); setPage(1); }} className={`btn btn-sm !rounded-full ${cat === id ? "btn-primary" : "btn-outline"}`}>{label}</button>;
  return (
    <div className="site-wrap space-y-6 py-8">
      <div><h1 className="text-3xl !font-extrabold">Products</h1><p className="text-muted">Search our catalogue and add medicines to your cart.</p></div>
      <div className="card space-y-3 p-4">
        <span className="relative block"><Search size={18} aria-hidden className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" /><input type="search" aria-label="Search products" placeholder="Enter your medicine name" className="w-full !min-h-12 !pl-11" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></span>
        <div role="group" aria-label="Category" className="flex flex-wrap gap-2">{chip("", "All")}{cats.data?.map((c) => chip(String(c.id), c.name))}</div>
      </div>
      {list.isLoading && <Loading label="Loading products…" />}
      {list.data?.results.length === 0 && <EmptyState>No products found.</EmptyState>}
      <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">{list.data?.results.map((m, i) => <li key={m.id} className="animate-rise" style={{ animationDelay: `${(i % 8) * 45}ms` }}><ProductCard m={m} onAdd={() => add(m)} /></li>)}</ul>
      {list.data && <Pagination page={page} setPage={(n) => { setPage(n); window.scrollTo({ top: 0, behavior: "smooth" }); }} hasPrev={!!list.data.previous} hasNext={!!list.data.next} total={list.data.count} pageSize={24} />}
    </div>
  );
}

// ---------------- checkout ----------------
export function Checkout() {
  const { slug = "" } = useParams(); const nav = useNavigate(); const { user } = useAuth(); const cart = useCart(slug); const confirm = useConfirm();
  const branches = useQuery({ queryKey: ["branches-public", slug], queryFn: () => api<Branch[]>(`/public/pharmacies/${slug}/branches/`) });
  const site = useSite(); const [f, setF] = useState({ branch: "", fulfilment: "pickup", address: "", notes: "", online: false });
  useSeo(`Your cart | ${site?.name}`, "Review your cart and place your order.", { noindex: true });
  const idem = useRef(crypto.randomUUID());
  const place = useMutation({
    mutationFn: () => api<{ id: number }>("/shop/orders/", { method: "POST", headers: { "Idempotency-Key": idem.current }, tenant: slug, body: { branch: Number(f.branch), fulfilment: f.fulfilment, payment_method: f.online ? "monime" : f.fulfilment === "pickup" ? "cash_on_pickup" : "cash_on_delivery", delivery_address: f.address, notes: f.notes, items: cart.items.map((i) => ({ medicine: i.id, quantity: i.quantity })) } }),
    onSuccess: (o) => { cart.clear(); idem.current = crypto.randomUUID(); nav(`/${slug}/account/orders/${o.id}`); },
  });
  const estimate = cart.items.reduce((t, i) => t + Number(i.price) * i.quantity, 0);
  if (cart.items.length === 0) return <div className="site-wrap py-12"><EmptyState icon={ShoppingCart} action={<Link className="btn btn-primary" to={`/${slug}/products`}>Browse products</Link>}><p className="text-lg font-bold">Your cart is empty</p></EmptyState></div>;
  const canOrder = user?.role === "customer" && user.tenant_slug === slug && user.email_verified;
  const option = (on: boolean, label: string, hint: string, pick: () => void, name: string) => (
    <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 text-sm transition ${on ? "bg-teal-50" : "hover:bg-slate-100"}`} style={{ borderColor: on ? "var(--brand)" : "var(--color-line)" }}>
      <input type="radio" name={name} className="mt-0.5" checked={on} onChange={pick} /><span><b className="block">{label}</b><span className="text-muted">{hint}</span></span>
    </label>);
  return (
    <div className="site-wrap py-8">
      <h1 className="text-3xl !font-extrabold">Checkout</h1>
      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-5">
          <ul className="card divide-y divide-line">{cart.items.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center gap-3 p-4 text-sm">
              <span className="min-w-40 flex-1"><b className="block">{i.name}</b><span className="text-muted">{money(i.price)} each</span>{i.requires_prescription && <span className="badge badge-warning ml-2">Prescription</span>}</span>
              <span className="flex items-center gap-1">
                <button type="button" className="btn btn-outline btn-sm !min-w-9 !px-2" aria-label={`Decrease ${i.name}`} disabled={i.quantity <= 1} onClick={() => cart.setQty(i.id, i.quantity - 1)}><Minus size={14} /></button>
                <input aria-label={`Quantity of ${i.name}`} placeholder="Qty" type="number" min={1} max={100} className="w-16 text-center" value={i.quantity} onChange={(e) => cart.setQty(i.id, Number(e.target.value))} />
                <button type="button" className="btn btn-outline btn-sm !min-w-9 !px-2" aria-label={`Increase ${i.name}`} onClick={() => cart.setQty(i.id, i.quantity + 1)}><Plus size={14} /></button>
              </span>
              <b className="w-24 text-right">{money(Number(i.price) * i.quantity)}</b>
              <button className="btn-link btn-link-danger" aria-label={`Remove ${i.name}`} onClick={async () => { if (await confirm({ title: "Remove this item?", message: i.name, confirmLabel: "Remove", danger: true })) cart.remove(i.id); }}><Trash2 size={13} aria-hidden />Remove</button>
            </li>))}</ul>
        </div>
        <aside className="card space-y-4 p-5 lg:sticky lg:top-24">
          <div className="flex justify-between text-lg font-extrabold"><span>Estimated subtotal</span><span>{money(estimate)}</span></div>
          <p className="text-xs text-muted">The final price, including tax and any delivery fee, is calculated by the pharmacy when you place the order.</p>
          {!canOrder ? (
            user?.tenant_slug === slug && user.role !== "customer" ? <p className="alert alert-info">Staff accounts cannot place website orders.</p> :
              user?.tenant_slug === slug ? <Link className="btn btn-primary w-full" to={`/${slug}/verify`}>Verify your email to order</Link> :
                <div className="grid gap-2"><Link className="btn btn-primary" to={`/${slug}/login?next=${encodeURIComponent(`/${slug}/checkout`)}`}>Sign in to order</Link><Link className="btn btn-outline" to={`/${slug}/register`}>Create an account</Link></div>
          ) : (
            <form onSubmit={(e) => { e.preventDefault(); place.mutate(); }} className="space-y-4">
              {place.isError && <p role="alert" className="alert alert-error">{errorMessage(place.error)}</p>}
              <label className="field-label">Branch<select required className="mt-1.5 w-full" value={f.branch} onChange={(e) => setF({ ...f, branch: e.target.value })}><option value="">Select your branch</option>{branches.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
              <fieldset className="grid gap-2"><legend className="field-label mb-1.5">Fulfilment</legend>
                {option(f.fulfilment === "pickup", "Pickup", "Collect from the branch", () => setF({ ...f, fulfilment: "pickup" }), "fulfilment")}
                {option(f.fulfilment === "delivery", "Delivery", "Brought to your address", () => setF({ ...f, fulfilment: "delivery" }), "fulfilment")}</fieldset>
              {f.fulfilment === "delivery" && <label className="field-label">Delivery address<input required className="mt-1.5 w-full" placeholder="Enter your delivery address" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></label>}
              <fieldset className="grid gap-2"><legend className="field-label mb-1.5">Payment</legend>
                {site?.online_payments && option(f.online, "Pay now with mobile money", "Secure checkout by Monime", () => setF({ ...f, online: true }), "payment")}
                {option(!f.online, `Pay on ${f.fulfilment === "pickup" ? "pickup" : "delivery"}`, "Pay the pharmacy directly", () => setF({ ...f, online: false }), "payment")}</fieldset>
              <label className="field-label">Order note (optional)<textarea rows={2} maxLength={300} className="mt-1.5 w-full" placeholder={placeholderFor("Order note")} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></label>
              <button disabled={place.isPending} className="btn btn-primary !min-h-12 w-full">{place.isPending ? <Spinner /> : <Check size={17} aria-hidden />}{place.isPending ? "Placing order…" : "Place order"}</button>
            </form>)}
        </aside>
      </div>
    </div>
  );
}

// ---------------- QR menu ----------------
export function QrMenu() {
  const { slug = "", token = "" } = useParams(); const s = useSite(); const toast = useToast();
  useSeo(`Branch menu | ${s?.name}`, "Browse and send a request to the pharmacy team.", { noindex: true });
  const info = useQuery({ queryKey: ["menu", token], queryFn: () => api<{ branch: { name: string; address: string } }>(`/public/menu/${token}/`), retry: false, enabled: !!slug });
  const [q, setQ] = useState(""); const [basket, setBasket] = useState<Record<number, { m: Med; qty: number }>>({});
  const list = useQuery({ queryKey: ["menu-cat", token, q], queryFn: () => api<Page<Med>>(`/public/menu/${token}/catalogue/?search=${encodeURIComponent(q)}`), enabled: info.isSuccess });
  const [c, setC] = useState({ name: "", phone: "", note: "", website: "" }); const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const send = async (kind: "shopping" | "assistance") => {
    if (!c.name.trim() || !c.phone.trim()) { setMsg({ ok: false, t: "Enter your name and phone number." }); return; }
    try { const r = await api<{ requires_prescription: boolean }>(`/public/menu/${token}/requests/`, { method: "POST", body: { customer_name: c.name, customer_phone: c.phone, note: c.note, website: c.website, kind, items: Object.values(basket).map((b) => ({ medicine: b.m.id, quantity: b.qty })) } });
      setBasket({}); setMsg({ ok: true, t: r.requires_prescription ? "Request sent. Some items need a prescription: please bring it or show it to the pharmacist." : "Request sent. Our staff will be with you shortly." }); } catch (e2) { setMsg({ ok: false, t: errorMessage(e2) }); }
  };
  if (info.isError) return <div className="site-wrap py-12"><EmptyState>This menu is not available.</EmptyState></div>;
  const input = (key: "name" | "phone" | "note", label: string) => <input aria-label={label} className="w-full" placeholder={placeholderFor(label)} value={c[key]} onChange={(e) => setC({ ...c, [key]: e.target.value })} />;
  return (
    <div className="site-wrap space-y-4 py-8"><h1 className="page-title">{info.data?.branch.name} menu</h1><p className="text-sm text-muted">Browse our products and send a request to the pharmacy team. This is a request, not a purchase: staff confirm availability and prices.</p>
      <input type="search" aria-label="Search products" placeholder="Enter your medicine name" className="w-full sm:max-w-sm" value={q} onChange={(e) => setQ(e.target.value)} />
      {list.isLoading && <Loading />}
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{list.data?.results.map((m) => <li key={m.id} className="card flex items-center justify-between gap-3 p-4 text-sm"><span><b>{m.name} {m.strength}</b> {m.requires_prescription && <span className="badge badge-warning">Rx</span>}<br /><span className="text-muted">{money(m.price)} · {m.available ? "In stock" : "Out of stock"}</span></span>
        <button className="btn btn-primary btn-sm" onClick={() => { setBasket({ ...basket, [m.id]: { m, qty: (basket[m.id]?.qty ?? 0) + 1 } }); toast(`${m.name} added to your request.`); }}>Add</button></li>)}</ul>
      <form onSubmit={(e) => { e.preventDefault(); send("shopping"); }} className="card space-y-3 p-5"><h2 className="section-title">Your request ({Object.keys(basket).length} items)</h2>
        <ul className="space-y-1 text-sm">{Object.values(basket).map((b) => <li key={b.m.id} className="flex items-center gap-2">{b.m.name} × {b.qty}<button type="button" className="btn-link btn-link-danger" onClick={() => setBasket(Object.fromEntries(Object.entries(basket).filter(([k]) => Number(k) !== b.m.id)))}>Remove</button></li>)}</ul>
        <div className="grid gap-3 sm:grid-cols-3">{input("name", "Name")}{input("phone", "Phone number")}{input("note", "Note")}</div>
        <input tabIndex={-1} autoComplete="off" aria-hidden className="hidden" value={c.website} onChange={(e) => setC({ ...c, website: e.target.value })} />
        <div className="flex flex-wrap gap-2"><button disabled={Object.keys(basket).length === 0} className="btn btn-primary">Send request</button><button type="button" className="btn btn-outline" onClick={() => send("assistance")}>Ask for assistance</button></div></form>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`alert ${msg.ok ? "alert-success" : "alert-error"}`}>{msg.t}</p>}
    </div>
  );
}
