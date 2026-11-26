/** The pharmacy dashboard. The API returns only the sections this person's role allows, so each role gets its own analysis. */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Banknote, Boxes, CalendarClock, ClipboardList, FileText, HeartHandshake, Package, PackageMinus, Pill, Receipt, RotateCcw, ScrollText, ShoppingCart, Star, Truck, UserPlus, Users, Wallet, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { ChartCard, DonutChart, RankBars, TrendChart, itemsTable, type Item } from "../../components/charts";
import { ErrorState, Loading, StatCard, errorMessage } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { day, money, words } from "../../lib/format";

type Num = string | number;
interface Analytics {
  days: number; from: string; to: string; scope: string; currency: string;
  sales?: { own_only: boolean; revenue: Num; previous_revenue: Num; transactions: number; today: Num; average_sale: Num; refunds: Num; discounts: Num; tax: Num; trend: { date: string; pos: Num; online: Num }[]; payment_methods: Item[]; top_products: (Item & { quantity: number })[]; categories: Item[]; by_hour: Item[]; by_weekday: Item[]; by_branch?: Item[]; by_cashier?: Item[] };
  orders?: { total: number; open: number; by_status: Item[]; by_fulfilment: Item[]; trend: { date: string; orders: number }[] };
  inventory?: { products: number; stock_value: Num; unsaleable_value: Num; low_stock: number; out_of_stock: number; near_expiry: number; expired: number; value_by_category: Item[]; expiring_soon: { medicine: string; batch: string; branch: string; expiry: string; quantity: number }[] };
  prescriptions?: { total: number; waiting: number; by_status: Item[]; trend: { date: string; prescriptions: number }[] };
  finance?: { monthly: { month: string; revenue: Num; expenses: Num }[]; expense_breakdown: Item[] };
  customers?: { total: number; new: number; verified: number; trend: { date: string; customers: number }[]; top: (Item & { orders: number })[] };
  procurement?: { by_status: Item[]; ordered_value: Num; awaiting_approval: number };
  people?: { staff: number; by_role: Item[]; present_today: number; attendance_today: Item[]; pending_leave: number };
  engagement?: { appointments: Item[]; open_inquiries: number; average_rating: number | null; ratings: Item[] };
  delivery?: { own_only: boolean; by_status: Item[]; active: number };
}
const shortDay = (v: string) => new Date(`${v}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });
const PERIODS: [number, string][] = [[7, "7 days"], [30, "30 days"], [90, "90 days"], [365, "12 months"]];
type Row = Record<string, unknown>;
const asRows = (items: unknown) => items as Row[];

function Section({ title, icon: Icon, to, linkLabel, children }: { title: string; icon: LucideIcon; to?: string; linkLabel?: string; children: ReactNode }) {
  return (
    <section className="space-y-4" aria-label={title}>
      <div className="flex items-center justify-between gap-3"><h2 className="flex items-center gap-2.5 text-lg !font-bold"><span className="grid h-9 w-9 place-items-center rounded-xl bg-teal-50 text-teal-700"><Icon size={18} aria-hidden /></span>{title}</h2>{to && <Link to={to} className="btn-link">{linkLabel ?? "Open"}</Link>}</div>
      {children}
    </section>
  );
}
const Stats = ({ children }: { children: ReactNode }) => <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{children}</div>;

export default function DashboardHome() {
  const { slug = "" } = useParams(); const { user, can } = useAuth(); const base = `/${slug}/admin`;
  const [days, setDays] = useState(30);
  const q = useQuery({ queryKey: ["analytics", days], queryFn: () => api<Analytics>(`/analytics/?days=${days}`), refetchInterval: 120_000, placeholderData: (p) => p });
  const hour = new Date().getHours();
  const actions: [boolean, string, string, LucideIcon][] = [
    [can("pos.sell"), "pos", "New sale", Receipt], [can("order.manage"), "orders", "Online orders", Package], [can("prescription.view"), "prescriptions", "Prescriptions", ScrollText],
    [can("inventory.view"), "inventory", "Inventory", Boxes], [can("customer.view"), "customers", "Customers", Users], [can("report.view", "accounting.view"), "reports", "Reports", FileText],
    [can("delivery.perform"), "deliveries", "My deliveries", Truck], [true, "my-work", "My work", CalendarClock],
  ];
  const d = q.data;
  const cur = d?.currency;
  const m = (v: Num) => money(v, cur);
  const num = (v: number) => v.toLocaleString();
  const s = d?.sales;
  const change = s && Number(s.previous_revenue) > 0 ? ((Number(s.revenue) - Number(s.previous_revenue)) / Number(s.previous_revenue)) * 100 : null;
  const donut = (title: string, items: Item[], name: string, value: string, format = num, center = "Total") => (
    <ChartCard title={title} table={itemsTable(name, value, items)}><DonutChart items={items} format={format} centerLabel={center} /></ChartCard>);
  const bars = (title: string, items: Item[], name: string, value: string, format = num) => (
    <ChartCard title={title} table={itemsTable(name, value, items)}><RankBars items={items} format={format} /></ChartCard>);
  return (
    <div className="space-y-8">
      <section className="hero-surface animate-rise overflow-hidden rounded-3xl p-6 sm:p-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div><p className="text-sm text-white/75">{hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"},</p><h1 className="mt-1 text-2xl !font-extrabold sm:text-3xl">{user?.full_name}</h1><p className="mt-1 text-sm text-white/75">{user?.role_name ?? words(user?.role)} · {d?.scope === "branch" ? user?.branch_name ?? "Your branch" : "All branches"} · {new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</p></div>
          <div role="group" aria-label="Period" className="glass flex flex-wrap gap-1 rounded-2xl p-1">{PERIODS.map(([v, label]) => <button key={v} type="button" aria-pressed={days === v} onClick={() => setDays(v)} className={`rounded-xl px-3 py-1.5 text-sm font-semibold transition ${days === v ? "bg-[#fff]" : "text-white/85 hover:bg-white/10"}`} style={days === v ? { color: "#0b1324" } : undefined}>{label}</button>)}</div>
        </div>
        <div className="mt-6 flex flex-wrap gap-2">{actions.filter((a) => a[0]).map(([, to, label, Icon]) => <Link key={to} to={`${base}/${to}`} className="btn glass text-white"><Icon size={16} aria-hidden />{label}</Link>)}</div>
      </section>

      {q.isLoading && <Loading rows={6} label="Preparing your analysis…" />}
      {q.isError && <ErrorState onRetry={() => q.refetch()}>{errorMessage(q.error)}</ErrorState>}

      {d && s && <Section title={s.own_only ? "My sales" : "Sales performance"} icon={Banknote} to={can("report.view", "accounting.view") ? `${base}/reports` : undefined} linkLabel="Reports">
        <Stats>
          <StatCard label="Revenue" value={m(s.revenue)} icon={Banknote} hint={change === null ? "No sales in the previous period" : <span className={`inline-flex items-center gap-1 font-semibold ${change >= 0 ? "text-success" : "text-danger"}`}>{change >= 0 ? <ArrowUpRight size={13} aria-hidden /> : <ArrowDownRight size={13} aria-hidden />}{Math.abs(change).toFixed(1)}% vs previous period</span>} />
          <StatCard label="Sales today" value={m(s.today)} icon={Wallet} tone="info" />
          <StatCard label="Transactions" value={num(s.transactions)} icon={ShoppingCart} tone="navy" hint={`Average ${m(s.average_sale)}`} />
          <StatCard label="Refunds" value={m(s.refunds)} icon={RotateCcw} tone="warning" hint={`Discounts ${m(s.discounts)} · Tax ${m(s.tax)}`} />
        </Stats>
        <div className="grid gap-5 xl:grid-cols-3">
          <ChartCard className="xl:col-span-2" title="Revenue trend" subtitle={`${shortDay(d.from)} – ${shortDay(d.to)}`} legend={s.own_only ? undefined : [{ label: "In store", color: "var(--series-1)" }, { label: "Online", color: "var(--series-2)" }]}
            table={{ head: ["Date", "In store", "Online"], rows: s.trend.map((r) => [shortDay(r.date), Number(r.pos), Number(r.online)]) }}>
            <TrendChart rows={s.trend} x="date" xLabel={shortDay} format={m} height={280} series={s.own_only ? [{ key: "pos", label: "My sales" }] : [{ key: "pos", label: "In store" }, { key: "online", label: "Online" }]} />
          </ChartCard>
          {donut("Payment methods", s.payment_methods, "Method", "Amount", m, "Taken")}
          {bars("Top products", s.top_products.map((p) => ({ ...p, note: `${p.quantity} sold` })), "Product", "Revenue", m)}
          {donut("Sales by category", s.categories, "Category", "Revenue", m, "Revenue")}
          {s.by_branch ? bars("Sales by branch", s.by_branch, "Branch", "Revenue", m) : s.by_cashier && bars("Sales by cashier", s.by_cashier, "Cashier", "Revenue", m)}
          <ChartCard className="xl:col-span-2" title="Busiest hours" subtitle="Number of counter sales by hour of day" table={itemsTable("Hour", "Sales", s.by_hour)}><TrendChart kind="column" rows={asRows(s.by_hour)} x="label" series={[{ key: "value", label: "Sales" }]} /></ChartCard>
          <ChartCard title="Day of the week" table={itemsTable("Day", "Revenue", s.by_weekday)}><TrendChart kind="column" rows={asRows(s.by_weekday)} x="label" series={[{ key: "value", label: "Revenue" }]} format={m} /></ChartCard>
          {s.by_branch && s.by_cashier && <div className="xl:col-span-3">{bars("Sales by cashier", s.by_cashier, "Cashier", "Revenue", m)}</div>}
        </div>
      </Section>}

      {d?.finance && <Section title="Finance" icon={Wallet} to={`${base}/accounting`} linkLabel="Accounting">
        <div className="grid gap-5 xl:grid-cols-3">
          <ChartCard className="xl:col-span-2" title="Revenue and expenses by month" subtitle="From the accounting ledger" legend={[{ label: "Revenue", color: "var(--series-1)" }, { label: "Expenses", color: "var(--series-2)" }]} table={{ head: ["Month", "Revenue", "Expenses"], rows: d.finance.monthly.map((r) => [r.month, Number(r.revenue), Number(r.expenses)]) }}>
            <TrendChart rows={d.finance.monthly} x="month" format={m} series={[{ key: "revenue", label: "Revenue" }, { key: "expenses", label: "Expenses" }]} />
          </ChartCard>
          {donut("Expense breakdown", d.finance.expense_breakdown, "Category", "Amount", m, "Spent")}
        </div>
      </Section>}

      {d?.orders && <Section title="Online orders" icon={Package} to={`${base}/orders`} linkLabel="Manage orders">
        <div className="grid gap-4 sm:grid-cols-2"><StatCard label="Orders in period" value={num(d.orders.total)} icon={Package} to={`${base}/orders`} /><StatCard label="Open orders" value={num(d.orders.open)} icon={ClipboardList} tone="warning" to={`${base}/orders`} /></div>
        <div className="grid gap-5 xl:grid-cols-3">
          <ChartCard title="Orders per day" table={{ head: ["Date", "Orders"], rows: d.orders.trend.map((r) => [shortDay(r.date), r.orders]) }}><TrendChart kind="column" rows={d.orders.trend} x="date" xLabel={shortDay} series={[{ key: "orders", label: "Orders" }]} /></ChartCard>
          {donut("Order status", d.orders.by_status, "Status", "Orders", num, "Orders")}
          {donut("Pickup and delivery", d.orders.by_fulfilment, "Type", "Orders", num, "Orders")}
        </div>
      </Section>}

      {d?.inventory && <Section title="Inventory health" icon={Boxes} to={`${base}/inventory`} linkLabel="Open inventory">
        <Stats>
          <StatCard label="Stock value" value={m(d.inventory.stock_value)} icon={Boxes} hint={`${d.inventory.products} active medicines · ${m(d.inventory.unsaleable_value)} unsaleable`} />
          <StatCard label="Low stock" value={d.inventory.low_stock} icon={PackageMinus} tone="warning" to={`${base}/inventory`} />
          <StatCard label="Out of stock" value={d.inventory.out_of_stock} icon={Pill} tone="danger" to={`${base}/inventory`} />
          <StatCard label="Expiring / expired" value={`${d.inventory.near_expiry} / ${d.inventory.expired}`} icon={AlertTriangle} tone="danger" to={`${base}/inventory`} />
        </Stats>
        <div className="grid gap-5 xl:grid-cols-2">
          {bars("Stock value by category", d.inventory.value_by_category, "Category", "Value", m)}
          <ChartCard title="Expiring soon" subtitle="Sell or return these first">
            {d.inventory.expiring_soon.length === 0 ? <p className="py-8 text-center text-sm text-muted">Nothing is close to expiry.</p> : <ul className="divide-y divide-line">{d.inventory.expiring_soon.map((b) => <li key={`${b.medicine}-${b.batch}-${b.branch}`} className="flex items-center justify-between gap-3 py-2.5 text-sm"><span className="min-w-0"><b className="block truncate">{b.medicine}</b><span className="text-xs text-muted">Batch {b.batch} · {b.branch} · {b.quantity} units</span></span><span className="badge badge-warning">{day(b.expiry)}</span></li>)}</ul>}
          </ChartCard>
        </div>
      </Section>}

      {d?.prescriptions && <Section title="Prescriptions" icon={ScrollText} to={`${base}/prescriptions`} linkLabel="Open register">
        <div className="grid gap-4 sm:grid-cols-2"><StatCard label="Received in period" value={d.prescriptions.total} icon={ScrollText} /><StatCard label="Waiting for review" value={d.prescriptions.waiting} icon={ClipboardList} tone="warning" to={`${base}/prescriptions`} /></div>
        <div className="grid gap-5 xl:grid-cols-3"><ChartCard className="xl:col-span-2" title="Prescriptions per day" table={{ head: ["Date", "Prescriptions"], rows: d.prescriptions.trend.map((r) => [shortDay(r.date), r.prescriptions]) }}><TrendChart kind="column" rows={d.prescriptions.trend} x="date" xLabel={shortDay} series={[{ key: "prescriptions", label: "Prescriptions" }]} /></ChartCard>{donut("Prescription status", d.prescriptions.by_status, "Status", "Count")}</div>
      </Section>}

      {d?.customers && <Section title="Customers" icon={Users} to={`${base}/customers`} linkLabel="All customers">
        <div className="grid gap-4 sm:grid-cols-3"><StatCard label="Registered customers" value={num(d.customers.total)} icon={Users} to={`${base}/customers`} /><StatCard label="New in period" value={num(d.customers.new)} icon={UserPlus} tone="info" /><StatCard label="Verified" value={num(d.customers.verified)} icon={HeartHandshake} tone="navy" /></div>
        <div className="grid gap-5 xl:grid-cols-3"><ChartCard className="xl:col-span-2" title="New registrations" table={{ head: ["Date", "Customers"], rows: d.customers.trend.map((r) => [shortDay(r.date), r.customers]) }}><TrendChart rows={d.customers.trend} x="date" xLabel={shortDay} series={[{ key: "customers", label: "New customers" }]} /></ChartCard>{bars("Top online customers", d.customers.top.map((c) => ({ ...c, note: `${c.orders} orders` })), "Customer", "Spent", m)}</div>
      </Section>}

      {d?.procurement && <Section title="Procurement" icon={ShoppingCart} to={`${base}/procurement`}>
        <div className="grid gap-4 sm:grid-cols-2"><StatCard label="Ordered in period" value={m(d.procurement.ordered_value)} icon={ShoppingCart} /><StatCard label="Awaiting approval" value={d.procurement.awaiting_approval} icon={ClipboardList} tone="warning" /></div>
        {donut("Purchase orders by status", d.procurement.by_status, "Status", "Orders")}
      </Section>}

      {d?.people && <Section title="Team" icon={Users} to={`${base}/hr`}>
        <div className="grid gap-4 sm:grid-cols-3"><StatCard label="Active staff" value={d.people.staff} icon={Users} /><StatCard label="Clocked in today" value={d.people.present_today} icon={CalendarClock} tone="info" /><StatCard label="Leave awaiting approval" value={d.people.pending_leave} icon={ClipboardList} tone="warning" /></div>
        <div className="grid gap-5 xl:grid-cols-2">{bars("Staff by role", d.people.by_role, "Role", "Staff")}{donut("Attendance today", d.people.attendance_today, "Status", "Staff")}</div>
      </Section>}

      {d?.engagement && <Section title="Customer care" icon={HeartHandshake} to={`${base}/engagement`}>
        <div className="grid gap-4 sm:grid-cols-2"><StatCard label="Average rating" value={d.engagement.average_rating ? `${d.engagement.average_rating.toFixed(1)} / 5` : "—"} icon={Star} tone="warning" /><StatCard label="Open enquiries" value={d.engagement.open_inquiries} icon={HeartHandshake} tone="info" /></div>
        <div className="grid gap-5 xl:grid-cols-2">{bars("Ratings", d.engagement.ratings, "Rating", "Reviews")}{donut("Appointments", d.engagement.appointments, "Status", "Appointments")}</div>
      </Section>}

      {d?.delivery && <Section title={d.delivery.own_only ? "My deliveries" : "Deliveries"} icon={Truck} to={`${base}/deliveries`}>
        <div className="grid gap-5 xl:grid-cols-2"><StatCard label="Active deliveries" value={d.delivery.active} icon={Truck} to={`${base}/deliveries`} />{donut("Delivery status", d.delivery.by_status, "Status", "Deliveries")}</div>
      </Section>}
    </div>
  );
}
