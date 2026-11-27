/** The signed-in customer's own space, in the same shell as every other role. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Banknote, CalendarClock, Check, CreditCard, Download, FileUp, HeartHandshake, LayoutDashboard, Package, Plus, RefreshCw, ShoppingBag, ShoppingCart, Star, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Navigate, Outlet, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChartCard, DonutChart, TrendChart, itemsTable } from "../../components/charts";
import { PageLoader } from "../../components/brand/Brand";
import { PharmacyNotFound, SystemNotFound } from "../../components/NotFound";
import { AppShell, type NavGroup } from "../../components/layout/AppShell";
import { DataTable, EmptyState, ErrorState, FormModal, Loading, PageHeader, Pagination, StatCard, StatusBadge, TableLoader, Tabs, errorMessage, useConfirm, useToast } from "../../components/ui";
import { ApiError, api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCart } from "../../lib/cart";
import { dateTime, day, money, words } from "../../lib/format";
import { brandOf, useSiteQuery } from "../../lib/site";

interface Line { medicine: number; name: string; quantity: number; unit_price: string; line_total: string; requires_prescription: boolean }
export interface OrderRow { id: number; reference_number: string; status: string; total: string; subtotal: string; tax_total: string; delivery_fee: string; created_at: string; fulfilment: string; delivery_address: string; branch_name: string; payment_method: string; requires_prescription: boolean; prescription_status: string | null; customer_can_cancel: boolean; lines: Line[]; history: { status: string; at: string; note: string }[] }
interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
interface Summary { currency: string; orders: number; open_orders: number; awaiting_payment: number; spent: string; monthly: { month: string; spent: string }[]; by_status: { label: string; value: number }[]; recent: OrderRow[]; appointments: { id: number; service: string; start_at: string; status: string }[] }

export default function CustomerLayout() {
  const params = useParams();
  const slug = params.slug ?? "";
  const unknown = params["*"] !== undefined; // only the catch-all route sets this
  const { user, loading } = useAuth();
  const site = useSiteQuery(slug);
  const cart = useCart(slug);
  const { pathname, search } = useLocation();
  if (loading || site.isLoading) return <PageLoader label="Opening your account…" brand={brandOf(site.data)} />;
  if (site.error instanceof ApiError && site.error.status === 404) return <SystemNotFound />;
  if (unknown && (!user || user.tenant_slug !== slug || user.role !== "customer" || !user.email_verified)) return <PharmacyNotFound />;
  if (!user || user.tenant_slug !== slug) return <Navigate to={`/${slug}/login?next=${encodeURIComponent(pathname + search)}`} replace />;
  if (user.role !== "customer") return <Navigate to={`/${slug}/admin/dashboard`} replace />;
  if (!user.email_verified) return <Navigate to={`/${slug}/verify`} replace />;
  const base = `/${slug}/account`;
  const groups: NavGroup[] = [
    { label: "Home", items: [{ to: `${base}/dashboard`, label: "Dashboard", icon: LayoutDashboard }] },
    { label: "Shop", items: [
      { to: `/${slug}/products`, label: "Browse products", icon: ShoppingBag, keywords: "medicines shop website" },
      { to: `/${slug}/checkout`, label: "My cart", icon: ShoppingCart, badge: cart.count, keywords: "checkout" }] },
    { label: "My account", items: [
      { to: `${base}/orders`, label: "My orders", icon: Package, keywords: "track delivery receipt" },
      { to: `${base}/payments`, label: "Payments", icon: CreditCard, keywords: "mobile money" },
      { to: `${base}/care`, label: "Services & support", icon: HeartHandshake, keywords: "appointments feedback enquiry" }] },
  ];
  return (
    <AppShell groups={groups} navLabel="My account" brand={brandOf(site.data)} brandCaption="My account" base={base} roleLabel="Customer"
      headerActions={<Link to={`/${slug}/checkout`} aria-label={`Cart, ${cart.count} items`} className="icon-btn relative"><ShoppingCart size={19} aria-hidden />{cart.count > 0 && <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10px] font-bold" style={{ background: "var(--brand)", color: "var(--on-brand)" }}>{cart.count}</span>}</Link>}>
      <Outlet />
    </AppShell>
  );
}

const useSlug = () => useParams().slug ?? "";

function OrdersTable({ rows, base, loading }: { rows?: OrderRow[]; base: string; loading?: boolean }) {
  const nav = useNavigate();
  return <DataTable rows={rows} loading={loading} pageSize={20} rowKey={(o) => o.id} onRowClick={(o) => nav(`${base}/orders/${o.id}`)} empty="You have not placed any orders yet."
    columns={[
      { key: "ref", header: "Order", render: (o) => <Link className="font-bold text-primary" to={`${base}/orders/${o.id}`}>{o.reference_number}</Link> },
      { key: "date", header: "Placed", render: (o) => dateTime(o.created_at), sort: (o) => o.created_at },
      { key: "items", header: "Items", render: (o) => o.lines.reduce((t, l) => t + l.quantity, 0), align: "center" },
      { key: "fulfilment", header: "Fulfilment", render: (o) => <span className="capitalize">{o.fulfilment}</span> },
      { key: "status", header: "Status", render: (o) => <StatusBadge status={o.status} /> },
      { key: "total", header: "Total", align: "right", render: (o) => <b>{money(o.total)}</b>, sort: (o) => Number(o.total) },
    ]} />;
}

export function CustomerDashboard() {
  const slug = useSlug(); const { user } = useAuth(); const base = `/${slug}/account`;
  const q = useQuery({ queryKey: ["my-orders", "summary"], queryFn: () => api<Summary>("/shop/summary/", { tenant: slug }) });
  if (q.isLoading) return <Loading rows={5} label="Loading your dashboard…" />;
  if (!q.data) return <ErrorState onRetry={() => q.refetch()}>{errorMessage(q.error)}</ErrorState>;
  const s = q.data, cur = s.currency;
  return (
    <div className="space-y-5">
      <section className="hero-surface animate-rise rounded-3xl p-6 sm:p-8">
        <p className="text-sm text-white/75">Welcome back</p>
        <h1 className="mt-1 text-2xl font-extrabold sm:text-3xl">{user?.full_name}</h1>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link to={`/${slug}/products`} className="btn btn-primary"><ShoppingBag size={16} aria-hidden />Shop medicines</Link>
          <Link to={`${base}/care`} className="btn glass text-white"><CalendarClock size={16} aria-hidden />Book a service</Link>
        </div>
      </section>
      {s.awaiting_payment > 0 && <p className="alert alert-warning"><Wallet size={18} aria-hidden />You have {s.awaiting_payment} order{s.awaiting_payment > 1 ? "s" : ""} waiting for mobile money payment. <Link className="font-bold" to={`${base}/orders`}>Pay now</Link></p>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="My orders" value={s.orders} icon={Package} to={`${base}/orders`} />
        <StatCard label="In progress" value={s.open_orders} icon={RefreshCw} tone="info" />
        <StatCard label="Total spent" value={money(s.spent, cur)} icon={Banknote} tone="navy" />
        <StatCard label="Upcoming appointments" value={s.appointments.length} icon={CalendarClock} tone="warning" to={`${base}/care`} />
      </div>
      <div className="grid gap-5 xl:grid-cols-3">
        <ChartCard className="xl:col-span-2" title="My spending" subtitle="Paid orders over the last six months" table={{ head: ["Month", `Spent (${cur})`], rows: s.monthly.map((m) => [m.month, Number(m.spent)]) }}>
          <TrendChart kind="column" rows={s.monthly} x="month" series={[{ key: "spent", label: "Spent" }]} format={(n) => money(n, cur)} />
        </ChartCard>
        <ChartCard title="Orders by status" table={itemsTable("Status", "Orders", s.by_status)}><DonutChart items={s.by_status} centerLabel="Orders" /></ChartCard>
      </div>
      {s.appointments.length > 0 && <section className="card p-5"><h2 className="section-title">Upcoming appointments</h2><ul className="mt-3 grid gap-3 sm:grid-cols-2">{s.appointments.map((a) => <li key={a.id} className="flex items-center justify-between gap-3 rounded-xl border border-line p-3 text-sm"><span><b className="block">{a.service}</b><span className="text-muted">{dateTime(a.start_at)}</span></span><StatusBadge status={a.status} /></li>)}</ul></section>}
      <section className="space-y-3"><div className="flex items-center justify-between"><h2 className="section-title">Recent orders</h2><Link className="btn-link" to={`${base}/orders`}>View all</Link></div><OrdersTable rows={s.recent} base={base} /></section>
    </div>
  );
}

export function MyOrders() {
  const slug = useSlug(); const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["my-orders", page], queryFn: () => api<Page<OrderRow>>(`/shop/orders/?page=${page}`, { tenant: slug }) });
  return (
    <div className="space-y-4">
      <PageHeader title="My orders" subtitle="Track every order from payment to delivery." actions={<Link className="btn btn-primary" to={`/${slug}/products`}><Plus size={16} aria-hidden />New order</Link>} />
      {q.isError ? <ErrorState onRetry={() => q.refetch()}>{errorMessage(q.error)}</ErrorState> : <OrdersTable rows={q.data?.results} loading={q.isLoading} base={`/${slug}/account`} />}
      {q.data && (q.data.next || q.data.previous) && <Pagination page={page} setPage={setPage} hasPrev={!!q.data.previous} hasNext={!!q.data.next} total={q.data.count} />}
    </div>
  );
}

const FLOW = ["awaiting_payment", "payment_confirmed", "preparing", "ready_for_pickup", "out_for_delivery", "completed"];
const STAGE: Record<string, number> = { pending: 0, awaiting_prescription: 0, prescription_approved: 0, awaiting_payment: 0, payment_confirmed: 1, processing: 2, preparing: 2, ready_for_pickup: 3, out_for_delivery: 4, delivered: 5, completed: 5 };

export function CustomerOrderDetail() {
  const slug = useSlug(); const { id = "" } = useParams(); const qc = useQueryClient(); const toast = useToast(); const confirm = useConfirm();
  const [sp] = useSearchParams(); const returned = sp.get("payment") === "return";
  const [uploading, setUploading] = useState(false);
  const o = useQuery({ queryKey: ["my-order", id], queryFn: () => api<OrderRow>(`/shop/orders/${id}/`, { tenant: slug }), refetchInterval: 20_000, retry: false });
  const refresh = () => qc.invalidateQueries({ queryKey: ["my-order", id] });
  const verify = useMutation({ mutationFn: () => api(`/shop/orders/${id}/payments/refresh/`, { method: "POST", tenant: slug }), onSuccess: refresh });
  const waiting = o.data?.status === "awaiting_payment" && o.data.payment_method === "monime";
  useEffect(() => { // back from checkout: ask our server to check with the payment provider until it answers
    if (!returned || !waiting) return;
    verify.mutate();
    let n = 0;
    const timer = window.setInterval(() => { if (++n > 20) window.clearInterval(timer); else verify.mutate(); }, 6000);
    return () => window.clearInterval(timer);
  }, [returned, waiting]); // eslint-disable-line react-hooks/exhaustive-deps
  const pay = useMutation({ mutationFn: () => api<{ redirect_url: string }>(`/shop/orders/${id}/pay/`, { method: "POST", tenant: slug }), onSuccess: (a) => { if (a.redirect_url.startsWith("https://")) window.location.href = a.redirect_url; }, onError: (e) => toast(errorMessage(e), "error") });
  const act = useMutation({ mutationFn: ({ path, reason }: { path: string; reason: string }) => api(`/shop/orders/${id}/${path}/`, { method: "POST", body: { reason }, tenant: slug }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["my-orders"] }); refresh(); toast("Order updated."); }, onError: (e) => toast(errorMessage(e), "error") });
  const back = <Link to={`/${slug}/account/orders`} className="btn btn-outline btn-sm"><ArrowLeft size={15} aria-hidden />My orders</Link>;
  if (o.isLoading) return <Loading rows={5} />;
  if (!o.data) return <div className="space-y-4">{back}<EmptyState>This order could not be found.</EmptyState></div>;
  const d = o.data;
  const stopped = ["cancelled", "refunded", "refund_requested", "prescription_rejected"].includes(d.status);
  const stage = STAGE[d.status] ?? 0;
  const steps = FLOW.filter((s) => d.fulfilment === "pickup" ? s !== "out_for_delivery" : s !== "ready_for_pickup");
  const paid = stage >= 1 || ["refunded", "refund_requested"].includes(d.status);
  return (
    <div className="space-y-5">
      {back}
      <PageHeader title={`Order ${d.reference_number}`} subtitle={`Placed ${dateTime(d.created_at)} · ${d.branch_name}`} actions={<StatusBadge status={d.status} />} />
      {waiting && returned && <p className="alert alert-info"><RefreshCw size={17} aria-hidden className="animate-spin" />We are confirming your payment with the payment provider. This page updates automatically.</p>}
      {sp.get("payment") === "cancelled" && waiting && <p className="alert alert-warning">The payment was not completed. You can try again whenever you are ready.</p>}
      {!stopped && (
        <ol className="card flex gap-2 overflow-x-auto p-4" aria-label="Order progress">
          {steps.map((s) => { const at = FLOW.indexOf(s); const done = stage >= at && !(at === 0 && stage === 0); const current = stage === at; return (
            <li key={s} aria-current={current ? "step" : undefined} className="flex min-w-28 flex-1 flex-col items-center gap-2 text-center">
              <span className="grid h-9 w-9 place-items-center rounded-full border-2 text-xs font-bold transition" style={done || current ? { background: "var(--brand)", borderColor: "var(--brand)", color: "var(--on-brand)" } : { borderColor: "var(--color-line)" }}>{done && !current ? <Check size={16} aria-hidden /> : steps.indexOf(s) + 1}</span>
              <span className={`text-xs capitalize ${current ? "font-bold" : "text-muted"}`}>{words(s)}</span>
            </li>); })}
        </ol>)}
      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-5">
          <div className="table-wrap"><table className="table"><thead><tr><th>Item</th><th className="text-center">Qty</th><th className="text-right">Unit price</th><th className="text-right">Amount</th></tr></thead>
            <tbody>{d.lines.map((l) => <tr key={l.medicine}><td><b>{l.name}</b>{l.requires_prescription && <span className="badge badge-warning ml-2">Prescription</span>}</td><td className="text-center">{l.quantity}</td><td className="text-right">{money(l.unit_price)}</td><td className="text-right font-bold">{money(l.line_total)}</td></tr>)}</tbody></table></div>
          <section className="card p-5"><h2 className="section-title">History</h2>
            <ol className="mt-3 space-y-3 border-l-2 border-line pl-4">{[...d.history].reverse().map((h, i) => <li key={i} className="relative text-sm"><span className="absolute -left-[1.35rem] top-1.5 h-2.5 w-2.5 rounded-full" style={{ background: i === 0 ? "var(--brand)" : "var(--color-line)" }} /><b className="capitalize">{words(h.status)}</b> <span className="text-muted">· {dateTime(h.at)}</span>{h.note && <p className="text-muted">{h.note}</p>}</li>)}</ol></section>
        </div>
        <aside className="space-y-4">
          <section className="card p-5 text-sm">
            <h2 className="section-title">Summary</h2>
            <dl className="mt-3 space-y-2">{([["Subtotal", d.subtotal], ["Tax", d.tax_total], ["Delivery fee", d.delivery_fee]] as const).map(([k, v]) => <div key={k} className="flex justify-between"><dt className="text-muted">{k}</dt><dd>{money(v)}</dd></div>)}<div className="flex justify-between border-t border-line pt-2 text-base font-extrabold"><dt>Total</dt><dd>{money(d.total)}</dd></div></dl>
            <dl className="mt-4 space-y-2 border-t border-line pt-4"><div><dt className="text-muted">Payment</dt><dd className="font-semibold capitalize">{d.payment_method === "monime" ? "Mobile money (online)" : words(d.payment_method)}</dd></div><div><dt className="text-muted">Fulfilment</dt><dd className="font-semibold capitalize">{d.fulfilment}{d.delivery_address && ` · ${d.delivery_address}`}</dd></div>{d.prescription_status && <div><dt className="text-muted">Prescription</dt><dd><StatusBadge status={d.prescription_status} /></dd></div>}</dl>
          </section>
          <div className="flex flex-col gap-2">
            {waiting && <><button className="btn btn-primary !min-h-12" disabled={pay.isPending} onClick={() => pay.mutate()}><Wallet size={17} aria-hidden />{pay.isPending ? "Opening secure checkout…" : "Pay with mobile money"}</button><button className="btn btn-outline" disabled={verify.isPending} onClick={() => verify.mutate(undefined, { onSuccess: () => toast("Payment status checked.", "info") })}><RefreshCw size={15} aria-hidden className={verify.isPending ? "animate-spin" : ""} />I have paid: check status</button></>}
            {d.status === "awaiting_prescription" && !d.prescription_status && <button className="btn btn-primary" onClick={() => setUploading(true)}><FileUp size={16} aria-hidden />Upload prescription</button>}
            {paid && <button className="btn btn-outline" onClick={() => openProtectedFile(`/shop/orders/${id}/receipt/pdf/`).catch((e) => toast(errorMessage(e), "error"))}><Download size={16} aria-hidden />Download receipt</button>}
            {d.customer_can_cancel && <button className="btn btn-outline btn-link-danger" onClick={async () => { if (await confirm({ title: "Cancel this order?", message: "This cannot be undone.", confirmLabel: "Cancel order", danger: true })) act.mutate({ path: "cancel", reason: "Cancelled by customer" }); }}>Cancel order</button>}
            {["delivered", "completed", "ready_for_pickup"].includes(d.status) && <button className="btn btn-outline" onClick={async () => { if (await confirm({ title: "Request a refund?", message: "The pharmacy will review your request.", confirmLabel: "Request refund" })) act.mutate({ path: "request-refund", reason: "Customer request" }); }}>Request a refund</button>}
          </div>
        </aside>
      </div>
      {uploading && <FormModal title="Upload your prescription" description="A pharmacist must review and approve it before your order can continue." submitLabel="Upload" onClose={() => setUploading(false)}
        fields={[{ name: "prescriber_name", label: "Prescriber name" }, { name: "prescription_date", label: "Prescription date", type: "date" }, { name: "document", label: "Prescription file", type: "file", required: true, wide: true, accept: "application/pdf,image/png,image/jpeg,image/webp", hint: "PDF or photo, up to 5 MB" }]}
        onSubmit={async (v, files) => { const fd = new FormData(); fd.append("document", files.document!); fd.append("prescriber_name", v.prescriber_name); fd.append("prescription_date", v.prescription_date); await api(`/shop/orders/${id}/prescription/`, { method: "POST", body: fd, tenant: slug }); refresh(); toast("Prescription uploaded. A pharmacist will review it."); }} />}
    </div>
  );
}

interface Attempt { id: number; reference: string; order: string; amount: string; currency: string; status: string; created_at: string; completed_at: string | null }
export function MyPayments() {
  const slug = useSlug(); const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["my-payments", page], queryFn: () => api<Page<Attempt>>(`/shop/payments/?page=${page}`, { tenant: slug }) });
  return (
    <div className="space-y-4">
      <PageHeader title="Payments" subtitle="Your mobile money payments. A payment is marked completed only when the provider confirms it." />
      <DataTable rows={q.data?.results} loading={q.isLoading} pageSize={25} rowKey={(a) => a.id} empty="You have no online payments yet." search={(a) => `${a.reference} ${a.order} ${a.status}`}
        columns={[{ key: "reference", header: "Reference", render: (a) => <b>{a.reference}</b> }, { key: "order", header: "Order" }, { key: "created", header: "Started", render: (a) => dateTime(a.created_at), sort: (a) => a.created_at }, { key: "completed", header: "Completed", render: (a) => day(a.completed_at) }, { key: "status", header: "Status", render: (a) => <StatusBadge status={a.status} /> }, { key: "amount", header: "Amount", align: "right", render: (a) => <b>{money(a.amount, a.currency)}</b>, sort: (a) => Number(a.amount) }]} />
      {q.data && (q.data.next || q.data.previous) && <Pagination page={page} setPage={setPage} hasPrev={!!q.data.previous} hasNext={!!q.data.next} total={q.data.count} />}
    </div>
  );
}

interface Svc { id: number; name: string; description: string; price: string | null; requires_booking: boolean; duration_minutes: number; branches: number[] }
interface Appt { id: number; service: string; start_at: string; status: string; staff_note: string }
interface Inquiry { id: number; kind: string; message: string; status: string; response: string; created_at: string }
interface Fb { id: number; rating: number; comment: string; response: string; created_at: string }

export function CustomerCare() {
  const slug = useSlug(); const qc = useQueryClient(); const toast = useToast(); const confirm = useConfirm();
  const [tab, setTab] = useState<"appointments" | "enquiries" | "feedback">("appointments");
  const [dialog, setDialog] = useState<"book" | "ask" | "rate" | null>(null);
  const services = useQuery({ queryKey: ["pub-services", slug], queryFn: () => api<Svc[]>(`/public/pharmacies/${slug}/services/`) });
  const branches = useQuery({ queryKey: ["branches-public", slug], queryFn: () => api<{ id: number; name: string }[]>(`/public/pharmacies/${slug}/branches/`) });
  const appts = useQuery({ queryKey: ["my-appts"], queryFn: () => api<Page<Appt>>("/shop/appointments/", { tenant: slug }) });
  const asks = useQuery({ queryKey: ["my-inquiries"], queryFn: () => api<Page<Inquiry>>("/shop/inquiries/", { tenant: slug }) });
  const ratings = useQuery({ queryKey: ["my-feedback"], queryFn: () => api<Page<Fb>>("/shop/feedback/", { tenant: slug }) });
  const send = async (path: string, body: unknown, key: string, done: string) => { await api(path, { method: "POST", tenant: slug, body }); await qc.invalidateQueries({ queryKey: [key] }); toast(done); };
  const bookable = services.data?.filter((s) => s.requires_booking) ?? [];
  return (
    <div className="space-y-4">
      <PageHeader title="Services & support" subtitle="Book pharmacy services, ask questions and tell us how we did."
        actions={tab === "appointments" ? <button className="btn btn-primary" disabled={!bookable.length} onClick={() => setDialog("book")}><Plus size={16} aria-hidden />Book appointment</button> : tab === "enquiries" ? <button className="btn btn-primary" onClick={() => setDialog("ask")}><Plus size={16} aria-hidden />Ask the pharmacy</button> : <button className="btn btn-primary" onClick={() => setDialog("rate")}><Star size={16} aria-hidden />Leave feedback</button>} />
      <Tabs tabs={[["appointments", "Appointments"], ["enquiries", "Enquiries"], ["feedback", "Feedback"]]} value={tab} onChange={setTab} />
      {tab === "appointments" && <>
        {!bookable.length && !services.isLoading && <p className="alert alert-info">This pharmacy has no services open for online booking yet.</p>}
        <DataTable rows={appts.data?.results} loading={appts.isLoading} rowKey={(a) => a.id} empty="You have no appointments yet."
          columns={[{ key: "service", header: "Service", render: (a) => <b>{a.service}</b> }, { key: "when", header: "When", render: (a) => dateTime(a.start_at), sort: (a) => a.start_at }, { key: "status", header: "Status", render: (a) => <StatusBadge status={a.status} /> }, { key: "staff_note", header: "Pharmacy note", render: (a) => a.staff_note || "—" },
            { key: "actions", header: "Actions", align: "right", render: (a) => ["requested", "confirmed"].includes(a.status) ? <button className="btn-link btn-link-danger" onClick={async () => { if (await confirm({ title: "Cancel this appointment?", message: `${a.service} on ${dateTime(a.start_at)}`, confirmLabel: "Cancel appointment", danger: true })) send(`/shop/appointments/${a.id}/cancel/`, {}, "my-appts", "Appointment cancelled.").catch((e) => toast(errorMessage(e), "error")); }}>Cancel</button> : null }]} />
      </>}
      {tab === "enquiries" && (asks.isLoading ? <TableLoader /> : !asks.data?.results.length ? <EmptyState>You have not sent any enquiries.</EmptyState> : <ul className="space-y-3">{asks.data.results.map((i) => <li key={i.id} className="card p-4"><div className="flex flex-wrap items-center justify-between gap-2"><b className="capitalize">{words(i.kind)}</b><span className="flex items-center gap-2 text-xs text-muted">{day(i.created_at)}<StatusBadge status={i.status} /></span></div><p className="mt-2 text-sm">{i.message}</p>{i.response && <p className="alert alert-success mt-3">{i.response}</p>}</li>)}</ul>)}
      {tab === "feedback" && (ratings.isLoading ? <TableLoader /> : !ratings.data?.results.length ? <EmptyState>You have not left feedback yet.</EmptyState> : <ul className="grid gap-3 sm:grid-cols-2">{ratings.data.results.map((f) => <li key={f.id} className="card p-4"><p aria-label={`${f.rating} out of 5`} className="flex gap-0.5 text-amber-500">{[1, 2, 3, 4, 5].map((n) => <Star key={n} size={17} fill={n <= f.rating ? "currentColor" : "none"} aria-hidden />)}</p><p className="mt-2 text-sm">{f.comment || "No comment."}</p>{f.response && <p className="alert alert-info mt-3">{f.response}</p>}<p className="mt-2 text-xs text-muted">{day(f.created_at)}</p></li>)}</ul>)}
      {dialog === "book" && <FormModal title="Book an appointment" submitLabel="Request appointment" onClose={() => setDialog(null)}
        fields={[{ name: "service", label: "Service", type: "select", wide: true, options: bookable.map((s) => [String(s.id), `${s.name} (${s.duration_minutes} min)${s.price ? ` · ${money(s.price)}` : ""}`]) }, { name: "branch", label: "Branch", type: "select", options: (branches.data ?? []).map((b) => [String(b.id), b.name]) }, { name: "start_at", label: "Date and time", type: "datetime-local" }, { name: "note", label: "Note", type: "textarea", required: false, maxLength: 300 }]}
        onSubmit={(v) => send("/shop/appointments/", { service: Number(v.service), branch: Number(v.branch), start_at: new Date(v.start_at).toISOString(), note: v.note }, "my-appts", "Request sent. We will confirm by email.")} />}
      {dialog === "ask" && <FormModal title="Ask the pharmacy" submitLabel="Send" onClose={() => setDialog(null)} fields={[{ name: "kind", label: "Request type", type: "select", wide: true, defaultValue: "inquiry", options: [["inquiry", "General question"], ["availability", "Is a medicine available?"], ["home_delivery", "Home delivery request"]] }, { name: "message", label: "Message", type: "textarea", maxLength: 1000 }]} onSubmit={(v) => send("/shop/inquiries/", v, "my-inquiries", "Sent. We will reply by email.")} />}
      {dialog === "rate" && <FormModal title="Leave feedback" submitLabel="Send feedback" onClose={() => setDialog(null)} fields={[{ name: "rating", label: "Rating", type: "select", wide: true, defaultValue: "5", options: [5, 4, 3, 2, 1].map((n) => [String(n), `${n} star${n > 1 ? "s" : ""}`]) }, { name: "comment", label: "Comment", type: "textarea", required: false, maxLength: 1500 }]} onSubmit={(v) => send("/shop/feedback/", { rating: Number(v.rating), comment: v.comment }, "my-feedback", "Thank you for your feedback.")} />}
    </div>
  );
}
