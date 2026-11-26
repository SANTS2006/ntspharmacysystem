import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api, fetchMe, login, openProtectedFile } from "../../lib/api";
import { ArrowRight, Lock, LogIn, Mail, MailCheck, MapPin, Phone, ShieldCheck, User, UserPlus } from "lucide-react";
import { AuthShell, Field, Notice, PasswordRules, SubmitButton } from "../../components/auth/AuthUi";
import { useAuth } from "../../lib/auth";
import { useCart } from "../../lib/cart";
import { useSite } from "./SiteLayout";
import { EmptyState, Loading, PageHeader, useConfirm, usePrompt } from "../../components/ui";

interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
interface Med { id: number; name: string; strength: string; dosage_form: string; category: string; price: string; description: string; requires_prescription: boolean; available?: boolean }
interface Branch { id: number; name: string; address: string; phone: string }
const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Something went wrong. Please try again.");
const inputCls = "mt-1 w-full px-3 py-2";
const brand = { background: "var(--brand)" };
const Alert = ({ m, ok }: { m: string | null; ok?: boolean }) => (m ? <p role={ok ? "status" : "alert"} className={`alert ${ok ? "alert-success" : "alert-error"}`}>{m}</p> : null);

// ---------------- home ----------------
export function SiteHome() {
  const { slug = "" } = useParams(); const s = useSite();
  const branches = useQuery({ queryKey: ["branches-public", slug], queryFn: () => api<Branch[]>(`/public/pharmacies/${slug}/branches/`) });
  return (
    <div className="space-y-10">
      <section className="card overflow-hidden">
        <div className="h-1.5" style={{ background: "var(--brand)" }} />
        <div className="p-7 sm:p-12">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{s?.name}</h1>
          <p className="mt-3 max-w-2xl text-lg leading-8 text-muted">{s?.description || "Your trusted local pharmacy."}</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link to={`/${slug}/products`} className="btn btn-primary !min-h-12 !px-6">Browse products<ArrowRight size={17} aria-hidden /></Link>
            <Link to={`/${slug}/services`} className="btn btn-outline !min-h-12 !px-6">Our services</Link>
          </div>
        </div>
      </section>
      <section>
        <h2 className="mb-4 text-xl font-bold">Our branches</h2>
        {branches.isLoading && <Loading rows={2} />}
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{branches.data?.map((b) => <li key={b.id} className="card p-5 text-sm"><p className="section-title">{b.name}</p><p className="mt-2 flex gap-2 text-muted"><MapPin size={16} aria-hidden className="mt-0.5 shrink-0" />{b.address || "Address not listed"}</p>{b.phone && <p className="mt-1.5 flex gap-2 text-muted"><Phone size={16} aria-hidden className="mt-0.5 shrink-0" />{b.phone}</p>}</li>)}</ul>
      </section>
    </div>
  );
}

// ---------------- products ----------------
export function Products() {
  const { slug = "" } = useParams(); const cart = useCart(slug);
  const [q, setQ] = useState(""); const [cat, setCat] = useState(""); const [page, setPage] = useState(1);
  const cats = useQuery({ queryKey: ["cats", slug], queryFn: () => api<{ id: number; name: string }[]>(`/public/pharmacies/${slug}/categories/`) });
  const list = useQuery({ queryKey: ["catalogue", slug, q, cat, page], queryFn: () => api<Page<Med>>(`/public/pharmacies/${slug}/catalogue/?page=${page}&search=${encodeURIComponent(q)}${cat ? `&category=${cat}` : ""}`) });
  return (
    <div className="space-y-4">
      <PageHeader title="Products" subtitle="Search our catalogue and add medicines to your cart." />
      <div className="card flex flex-wrap gap-3 p-3"><input aria-label="Search products" placeholder="Search for a medicine" className="min-w-0 flex-1 px-3 py-2" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select aria-label="Category" className="px-3 py-2" value={cat} onChange={(e) => { setCat(e.target.value); setPage(1); }}><option value="">All categories</option>{cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      {list.isLoading && <Loading />}{list.data?.results.length === 0 && <EmptyState>No products found.</EmptyState>}
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{list.data?.results.map((m) => (
        <li key={m.id} className="card flex flex-col gap-1 p-5 transition hover:shadow-md"><h2 className="section-title">{m.name} <span className="font-normal text-slate-500">{m.strength}</span></h2>
          <p className="text-sm text-slate-600">{m.dosage_form} · {m.category}</p><p className="mt-1 text-xl font-bold tabular-nums">{m.price}</p>
          {m.requires_prescription && <p className="text-sm font-medium text-red-700">Prescription only: you will upload a valid prescription and a pharmacist must approve it.</p>}
          <button className="btn btn-primary mt-3 !mb-0 self-stretch" onClick={() => cart.add({ id: m.id, name: m.name, price: m.price, requires_prescription: m.requires_prescription })}>Add to cart</button></li>))}</ul>
      <div className="flex gap-2"><button disabled={!list.data?.previous} onClick={() => setPage(page - 1)} className="btn btn-outline btn-sm">Previous</button><button disabled={!list.data?.next} onClick={() => setPage(page + 1)} className="btn btn-outline btn-sm">Next</button></div>
    </div>
  );
}

// ---------------- auth ----------------
export function CustomerRegister() {
  const { slug = "" } = useParams(); const nav = useNavigate(); const { setUser } = useAuth();
  const [f, setF] = useState({ full_name: "", email: "", phone: "", password: "" }); const [terms, setTerms] = useState(false); const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    if (!terms) { setErr("You must agree to the Terms of Use and Privacy Policy."); return; }
    setBusy(true);
    try { const r = await api<{ tokens: { access: string; refresh: string }; user: never }>("/shop/register/", { method: "POST", body: { ...f, terms_accepted: true }, tenant: slug, retry: false }); const { setTokens } = await import("../../lib/api"); setTokens(r.tokens); setUser(await fetchMe(slug)); nav(`/${slug}/verify`); }
    catch (e2) { setErr(errText(e2)); } finally { setBusy(false); }
  };
  const set = (k: keyof typeof f) => ({ value: f[k], onChange: (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value }) });
  return (
    <AuthShell embedded icon={UserPlus} title="Create your account" subtitle="Order medicines online and track your orders."
      footer={<>Already registered? <Link className="font-medium text-[var(--brand)] hover:underline" to={`/${slug}/login`}>Sign in</Link></>}>
      <form onSubmit={submit} className="space-y-4"><Notice message={err} />
        <Field label="Full name" icon={User} placeholder="Enter your full name" autoComplete="name" {...set("full_name")} />
        <Field label="Email" icon={Mail} type="email" placeholder="you@example.com" autoComplete="email" {...set("email")} />
        <Field label="Phone number" icon={Phone} type="tel" required={false} placeholder="Enter your phone number" autoComplete="tel" {...set("phone")} />
        <Field label="Password" icon={Lock} type="password" minLength={10} placeholder="At least 10 characters" autoComplete="new-password" {...set("password")} />
        <PasswordRules value={f.password} />
        <label className="flex items-start gap-2 text-sm text-slate-600"><input type="checkbox" className="mt-0.5 h-4 w-4 rounded border-slate-300" checked={terms} onChange={(e) => setTerms(e.target.checked)} /> I agree to the Terms of Use and Privacy Policy</label>
        <SubmitButton busy={busy} icon={UserPlus}>{busy ? "Creating…" : "Create account"}</SubmitButton>
      </form>
    </AuthShell>
  );
}

export function CustomerLogin() {
  const { slug = "" } = useParams(); const nav = useNavigate(); const { setUser } = useAuth();
  const [f, setF] = useState({ email: "", password: "" }); const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => { e.preventDefault(); setErr(null); setBusy(true); try { const u = await login(f.email, f.password, slug); setUser(u); nav(u.email_verified ? `/${slug}/orders` : `/${slug}/verify`); } catch (e2) { setErr(errText(e2)); } finally { setBusy(false); } };
  return (
    <AuthShell embedded icon={LogIn} title="Welcome back" subtitle="Sign in to place and track your orders."
      footer={<><Link className="font-medium text-[var(--brand)] hover:underline" to={`/${slug}/admin/forgot-password`}>Forgot your password?</Link> · <Link className="font-medium text-[var(--brand)] hover:underline" to={`/${slug}/register`}>Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4"><Notice message={err} />
        <Field label="Email" icon={Mail} type="email" placeholder="you@example.com" autoComplete="username" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <Field label="Password" icon={Lock} type="password" placeholder="Enter your password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        <SubmitButton busy={busy} icon={LogIn}>{busy ? "Signing in…" : "Sign in"}</SubmitButton>
      </form>
    </AuthShell>
  );
}

export function VerifyEmail() {
  const { slug = "" } = useParams(); const nav = useNavigate(); const { user, setUser } = useAuth();
  const [code, setCode] = useState(""); const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  if (!user) return <p>Please <Link className="underline" to={`/${slug}/login`}>sign in</Link> first.</p>;
  const verify = async (e: React.FormEvent) => { e.preventDefault(); try { await api("/shop/verify-email/", { method: "POST", body: { code: code.trim().toUpperCase() }, tenant: slug }); setUser(await fetchMe(slug)); nav(`/${slug}/products`); } catch (e2) { setMsg({ ok: false, t: errText(e2) }); } };
  const resend = () => api("/shop/resend-code/", { method: "POST", tenant: slug }).then(() => setMsg({ ok: true, t: "A new code has been sent." })).catch((e) => setMsg({ ok: false, t: errText(e) }));
  return (
    <AuthShell embedded icon={MailCheck} title="Verify your email" subtitle={`Enter the 6-character code we sent to ${user.email}.`}
      footer={<button type="button" onClick={resend} className="font-medium text-[var(--brand)] hover:underline">Send a new code</button>}>
      <form onSubmit={verify} className="space-y-4"><Notice message={msg?.t ?? null} ok={msg?.ok} />
        <input aria-label="Verification code" required maxLength={6} minLength={6} autoComplete="one-time-code" className="w-full rounded-xl border border-slate-300 bg-white py-3 text-center text-3xl font-bold uppercase tracking-[0.5em] text-slate-900 shadow-sm outline-none focus:border-[var(--brand)] focus:ring-4 focus:ring-emerald-100" placeholder="······" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
        <SubmitButton icon={ShieldCheck}>Verify email</SubmitButton>
      </form>
    </AuthShell>
  );
}

// ---------------- checkout ----------------
export function Checkout() {
  const { slug = "" } = useParams(); const nav = useNavigate(); const { user } = useAuth(); const cart = useCart(slug);
  const branches = useQuery({ queryKey: ["branches-public", slug], queryFn: () => api<Branch[]>(`/public/pharmacies/${slug}/branches/`) });
  const site = useSite(); const [f, setF] = useState({ branch: "", fulfilment: "pickup", address: "", notes: "", online: false }); const [err, setErr] = useState<string | null>(null);
  const idem = useRef(crypto.randomUUID());
  const place = useMutation({
    mutationFn: () => api<{ id: number }>("/shop/orders/", { method: "POST", headers: { "Idempotency-Key": idem.current }, tenant: slug, body: { branch: Number(f.branch), fulfilment: f.fulfilment, payment_method: f.online ? "monime" : f.fulfilment === "pickup" ? "cash_on_pickup" : "cash_on_delivery", delivery_address: f.address, notes: f.notes, items: cart.items.map((i) => ({ medicine: i.id, quantity: i.quantity })) } }),
    onSuccess: (o) => { cart.clear(); idem.current = crypto.randomUUID(); nav(`/${slug}/orders/${o.id}`); }, onError: (e) => setErr(errText(e)),
  });
  const estimate = cart.items.reduce((t, i) => t + Number(i.price) * i.quantity, 0);
  if (cart.items.length === 0) return <div><h1 className="page-title">Your cart</h1><p>Your cart is empty. <Link className="underline" to={`/${slug}/products`}>Browse products</Link></p></div>;
  return (
    <div className="space-y-4"><h1 className="page-title">Checkout</h1>
      <ul className="divide-y rounded-xl border">{cart.items.map((i) => <li key={i.id} className="flex items-center gap-3 p-3 text-sm"><span className="flex-1">{i.name} {i.requires_prescription && <em className="text-red-700">(prescription required)</em>}</span>
        <input aria-label={`Quantity of ${i.name}`} type="number" min={1} max={100} className="w-16 px-2 py-1" value={i.quantity} onChange={(e) => cart.setQty(i.id, Number(e.target.value))} /><span>{(Number(i.price) * i.quantity).toFixed(2)}</span><button className="btn-link" onClick={() => cart.remove(i.id)}>Remove</button></li>)}</ul>
      <p className="text-sm text-slate-600">Estimated subtotal {estimate.toFixed(2)}. The final price including tax and any delivery fee is calculated by the pharmacy when you place the order.</p>
      {!user || user.role !== "customer" ? <p>Please <Link className="underline" to={`/${slug}/login`}>sign in</Link> or <Link className="underline" to={`/${slug}/register`}>register</Link> to place an order.</p> : !user.email_verified ? <p>Please <Link className="underline" to={`/${slug}/verify`}>verify your email</Link> to place an order.</p> : (
        <form onSubmit={(e) => { e.preventDefault(); setErr(null); place.mutate(); }} className="space-y-3 rounded-xl border p-4"><Alert m={err} />
          <label className="block text-sm font-medium">Branch<select required className={inputCls} value={f.branch} onChange={(e) => setF({ ...f, branch: e.target.value })}><option value="">Select a branch</option>{branches.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <fieldset className="text-sm"><legend className="font-medium">Fulfilment</legend><label className="mr-4"><input type="radio" checked={f.fulfilment === "pickup"} onChange={() => setF({ ...f, fulfilment: "pickup" })} /> Pickup (pay at the pharmacy)</label><label><input type="radio" checked={f.fulfilment === "delivery"} onChange={() => setF({ ...f, fulfilment: "delivery" })} /> Delivery (pay on delivery)</label></fieldset>
          {f.fulfilment === "delivery" && <label className="block text-sm font-medium">Delivery address<input required className={inputCls} placeholder="Enter your delivery address" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></label>}
          {site?.online_payments ? <fieldset className="text-sm"><legend className="font-medium">Payment</legend><label className="mr-4"><input type="radio" checked={!f.online} onChange={() => setF({ ...f, online: false })} /> Pay on {f.fulfilment === "pickup" ? "pickup" : "delivery"}</label><label><input type="radio" checked={f.online} onChange={() => setF({ ...f, online: true })} /> Pay online (mobile money)</label></fieldset> : <p className="text-sm text-slate-600">This pharmacy accepts payment on pickup or delivery.</p>}
          <button disabled={place.isPending} className="btn btn-primary">{place.isPending ? "Placing order…" : "Place order"}</button></form>)}
    </div>
  );
}

// ---------------- orders ----------------
interface OrderRow { payment_method?: string; id: number; reference_number: string; status: string; total: string; created_at: string; fulfilment: string; requires_prescription: boolean; prescription_status: string | null; customer_can_cancel: boolean; lines: { name: string; quantity: number; line_total: string }[]; history: { status: string; at: string; note: string }[] }

export function Orders() {
  const { slug = "" } = useParams();
  const list = useQuery({ queryKey: ["my-orders"], queryFn: () => api<Page<OrderRow>>("/shop/orders/", { tenant: slug }) });
  return <div className="space-y-3"><h1 className="page-title">My orders</h1>{list.data?.results.length === 0 && <p>No orders yet.</p>}
    <ul className="space-y-2">{list.data?.results.map((o) => <li key={o.id} className="flex justify-between rounded-xl border p-3"><Link className="font-medium underline" to={`/${slug}/orders/${o.id}`}>{o.reference_number}</Link><span>{o.status.replace(/_/g, " ")}</span><span>{o.total}</span></li>)}</ul></div>;
}

export function OrderDetail() {
  const promptFor = usePrompt(); const confirmDialog = useConfirm();
  const { slug = "", id = "" } = useParams(); const qc = useQueryClient();
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const returned = new URLSearchParams(location.search).get("payment") === "return";
  const o = useQuery({ queryKey: ["my-order", id], queryFn: () => api<OrderRow>(`/shop/orders/${id}/`, { tenant: slug }), refetchInterval: returned ? 4000 : 15000 });
  const act = useMutation({ mutationFn: (p: string) => api(`/shop/orders/${id}/${p}/`, { method: "POST", body: { reason: "Customer request" }, tenant: slug }), onSuccess: () => { qc.invalidateQueries(); setMsg({ ok: true, t: "Updated." }); }, onError: (e) => setMsg({ ok: false, t: errText(e) }) });
  const [rx, setRx] = useState({ prescriber_name: "", prescription_date: "" }); const file = useRef<HTMLInputElement>(null);
  const upload = async (e: React.FormEvent) => { e.preventDefault(); const f = file.current?.files?.[0]; if (!f) return; const fd = new FormData(); fd.append("document", f); fd.append("prescriber_name", rx.prescriber_name); fd.append("prescription_date", rx.prescription_date); try { await api(`/shop/orders/${id}/prescription/`, { method: "POST", body: fd, tenant: slug }); qc.invalidateQueries(); setMsg({ ok: true, t: "Prescription uploaded. A pharmacist will review it." }); } catch (e2) { setMsg({ ok: false, t: errText(e2) }); } };
  const payNow = async () => {
    try { const a = await api<{ redirect_url: string }>(`/shop/orders/${id}/pay/`, { method: "POST", tenant: slug }); if (a.redirect_url.startsWith("https://")) window.location.href = a.redirect_url; }
    catch (e) { setMsg({ ok: false, t: errText(e) }); }
  };
  if (!o.data) return <Loading />;
  const d = o.data;
  const paid = !["pending", "awaiting_prescription", "prescription_approved", "prescription_rejected", "awaiting_payment", "cancelled"].includes(d.status);
  return (
    <div className="space-y-4"><h1 className="page-title">Order {d.reference_number}</h1><Alert m={msg?.t ?? null} ok={msg?.ok} />
      <p>Status: <strong>{d.status.replace(/_/g, " ")}</strong> · {d.fulfilment} · Total {d.total}</p>
      {returned && d.status === "awaiting_payment" && <Alert m="We are confirming your payment with the payment provider. This page updates automatically and can take a minute." ok />}
      {d.status === "awaiting_payment" && d.payment_method === "monime" && <button className="btn btn-primary" onClick={payNow}>Pay now</button>}
      {paid && <button className="btn btn-outline btn-sm" onClick={() => openProtectedFile(`/shop/orders/${id}/receipt/pdf/`).catch((e) => setMsg({ ok: false, t: errText(e) }))}>Download receipt</button>}
      <ul className="text-sm">{d.lines.map((l, i) => <li key={i}>{l.name} × {l.quantity} — {l.line_total}</li>)}</ul>
      {d.status === "awaiting_prescription" && !d.prescription_status && (
        <form onSubmit={upload} className="card space-y-2 p-4"><h2 className="section-title">Upload your prescription</h2><p className="text-sm text-slate-600">A pharmacist must review and approve it before your order can continue.</p>
          <input required className={inputCls} placeholder="Enter the prescriber's name" value={rx.prescriber_name} onChange={(e) => setRx({ ...rx, prescriber_name: e.target.value })} aria-label="Prescriber" />
          <input required type="date" className={inputCls} value={rx.prescription_date} onChange={(e) => setRx({ ...rx, prescription_date: e.target.value })} aria-label="Prescription date" />
          <input ref={file} required type="file" accept="application/pdf,image/png,image/jpeg,image/webp" aria-label="Prescription file" /><button className="btn btn-primary">Upload</button></form>)}
      {d.prescription_status && <p className="text-sm">Prescription status: {d.prescription_status.replace(/_/g, " ")}</p>}
      <h2 className="section-title">Progress</h2><ol className="text-sm">{d.history.map((h, i) => <li key={i}>{new Date(h.at).toLocaleString()} — {h.status.replace(/_/g, " ")} {h.note && `(${h.note})`}</li>)}</ol>
      <div className="flex gap-2">{d.customer_can_cancel && <button className="btn btn-outline btn-sm" onClick={async () => { if (await confirmDialog({ title: "Cancel this order?", confirmLabel: "Cancel order", danger: true })) act.mutate("cancel"); }}>Cancel order</button>}
        {["delivered", "completed", "ready_for_pickup"].includes(d.status) && <button className="btn btn-outline btn-sm" onClick={() => act.mutate("request-refund")}>Request a refund</button>}</div>
    </div>
  );
}

// ---------------- QR menu ----------------
export function QrMenu() {
  const { slug = "", token = "" } = useParams(); const s = useSite();
  const info = useQuery({ queryKey: ["menu", token], queryFn: () => api<{ branch: { name: string; address: string } }>(`/public/menu/${token}/`), retry: false });
  const [q, setQ] = useState(""); const [basket, setBasket] = useState<Record<number, { m: Med; qty: number }>>({});
  const list = useQuery({ queryKey: ["menu-cat", token, q], queryFn: () => api<Page<Med>>(`/public/menu/${token}/catalogue/?search=${encodeURIComponent(q)}`), enabled: info.isSuccess });
  const [c, setC] = useState({ name: "", phone: "", note: "", website: "" }); const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const submit = async (e: React.FormEvent, kind: "shopping" | "assistance") => {
    e.preventDefault();
    try { const r = await api<{ requires_prescription: boolean }>(`/public/menu/${token}/requests/`, { method: "POST", body: { customer_name: c.name, customer_phone: c.phone, note: c.note, website: c.website, kind, items: Object.values(basket).map((b) => ({ medicine: b.m.id, quantity: b.qty })) } });
      setBasket({}); setMsg({ ok: true, t: r.requires_prescription ? "Request sent. Some items need a prescription: please bring it or show it to the pharmacist." : "Request sent. Our staff will be with you shortly." }); } catch (e2) { setMsg({ ok: false, t: errText(e2) }); }
  };
  if (info.isError) return <p>This menu is not available.</p>;
  return (
    <div className="space-y-4"><h1 className="page-title">{info.data?.branch.name} menu</h1><p className="text-sm text-slate-600">Browse our products and send a request to the pharmacy team. This is a request, not a purchase: staff confirm availability and prices.</p>
      <input aria-label="Search products" placeholder="Enter a medicine name" className="px-3 py-2" value={q} onChange={(e) => setQ(e.target.value)} />
      <ul className="grid gap-2 sm:grid-cols-2">{list.data?.results.map((m) => <li key={m.id} className="flex items-center justify-between rounded-xl border p-3 text-sm"><span>{m.name} {m.strength} {m.requires_prescription && <em className="text-red-700">(Rx)</em>}<br /><span className="text-slate-500">{m.price} · {m.available ? "In stock" : "Out of stock"}</span></span>
        <button className="btn btn-primary" onClick={() => setBasket({ ...basket, [m.id]: { m, qty: (basket[m.id]?.qty ?? 0) + 1 } })}>Add</button></li>)}</ul>
      <form onSubmit={(e) => submit(e, "shopping")} className="card space-y-2 p-4"><h2 className="section-title">Your request ({Object.keys(basket).length} items)</h2>
        <ul className="text-sm">{Object.values(basket).map((b) => <li key={b.m.id}>{b.m.name} × {b.qty}</li>)}</ul>
        <input required className={inputCls} placeholder="Enter your name" value={c.name} onChange={(e) => setC({ ...c, name: e.target.value })} aria-label="Your name" />
        <input required className={inputCls} placeholder="Enter your phone number" value={c.phone} onChange={(e) => setC({ ...c, phone: e.target.value })} aria-label="Your phone" />
        <input className={inputCls} placeholder="Add a note (optional)" value={c.note} onChange={(e) => setC({ ...c, note: e.target.value })} aria-label="Note" />
        <input tabIndex={-1} autoComplete="off" aria-hidden className="hidden" value={c.website} onChange={(e) => setC({ ...c, website: e.target.value })} />
        <div className="flex gap-2"><button disabled={Object.keys(basket).length === 0} className="btn btn-primary">Send request</button>
          <button type="button" className="btn btn-outline" onClick={(e) => submit(e as unknown as React.FormEvent, "assistance")}>Ask for assistance</button></div></form>
      <Alert m={msg?.t ?? null} ok={msg?.ok} /><p className="text-xs text-slate-500">{s?.name}</p>
    </div>
  );
}
