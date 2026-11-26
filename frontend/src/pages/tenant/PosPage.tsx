import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, ArrowUpFromLine, Banknote, CheckCircle2, CreditCard, FileText, Landmark, Lock, Mail, Minus, Plus, Printer, ScanBarcode, Search, ShoppingCart, Smartphone, Trash2, Wallet } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { Loading, Modal, PageHeader, StatusBadge, errorMessage, placeholderFor, useConfirm, usePrompt, useToast } from "../../components/ui";
import { ServerTable } from "../../components/ui/ServerTable";
import { dateTime } from "../../lib/format";
import { MobileMoneyDialog, type Collection } from "./MobileMoney";
import { api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";

interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
interface Product { id: number; name: string; strength: string; price: string; tax_rate: string; stock: number; requires_prescription: boolean }
interface Shift { id: number; status: string; opening_cash: string; expected_cash: string; totals: { sales_count: number; sales_total: string; cash_received: string; cash_refunds: string; expected_cash: string }; cash_movements: { id: number; kind: string; amount: string; status: string }[] }
interface SaleRow { id: number; reference_number: string; status: string; total: string; amount_paid: string; balance: string; customer_name: string; created_at: string; cashier_name: string }
interface SaleDetail extends SaleRow { receipt_number: string; lines: { id: number; name: string; quantity: number; quantity_returned: number; line_total: string }[] }
interface Pending { id: number; prescription: string; patient: string; estimated_total: string; items: { medicine: string; quantity: number }[] }
interface CartLine { product: Product; quantity: number; discount_pct: number }

const errText = errorMessage;
const money = (n: number) => n.toFixed(2);
const METHODS = [["cash", "Cash", Banknote], ["mobile_money", "Mobile money", Smartphone], ["card", "Card", CreditCard], ["bank_transfer", "Bank transfer", Landmark]] as const;
const methodLabel = (m: string) => METHODS.find((x) => x[0] === m)?.[1] ?? m;

export default function PosPage() {
  const { user } = useAuth(); const qc = useQueryClient();
  const confirmDialog = useConfirm(); const promptFor = usePrompt(); const toast = useToast();
  const can = (p: string) => !!user?.permissions.includes(p);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const succeed = (t: string) => { setMsg(null); toast(t); };
  const fail = (e: unknown) => setMsg({ ok: false, t: errText(e) });
  const refresh = () => qc.invalidateQueries();

  const shift = useQuery({ queryKey: ["shift"], queryFn: () => api<Shift | null>("/shifts/current/").then((s) => (s?.id ? s : null)), enabled: can("pos.sell") }); // "no open shift" arrives as an empty body
  const momo = useQuery({ queryKey: ["momo-status"], queryFn: () => api<{ enabled: boolean; currency: string }>("/payments/status/") });
  const unused = useQuery({ queryKey: ["momo-unused", shift.data?.id], queryFn: () => api<Collection[]>("/payments/mobile-money/"), enabled: !!shift.data && !!momo.data?.enabled, refetchInterval: 30000 });
  const [collecting, setCollecting] = useState(false);
  const pending = useQuery({ queryKey: ["pending-disp", shift.data?.id], queryFn: () => api<Pending[]>("/pos/pending-dispensings/"), enabled: !!shift.data });
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => api<Page<{ id: number; name: string }>>("/branches/"), enabled: can("branch.view") && !user?.branch });

  // ---------- shift ----------
  const [opening, setOpening] = useState("0"); const [branch, setBranch] = useState(user?.branch ? String(user.branch) : "");
  const openShift = useMutation({ mutationFn: () => api("/shifts/open/", { method: "POST", body: { opening_cash: opening, branch: branch ? Number(branch) : undefined } }), onSuccess: () => { succeed("Shift opened."); refresh(); }, onError: fail });
  const closeShift = async () => {
    const sh = shift.data; if (!sh) return;
    const v = await promptFor({ title: "Close shift", message: <>Expected cash in the drawer: <strong>{sh.totals.expected_cash}</strong></>, confirmLabel: "Continue", fields: [{ name: "counted", label: "Counted cash", type: "number", min: 0, step: "0.01" }] });
    if (!v) return;
    if (await confirmDialog({ title: "Close the shift?", message: "This cannot be undone.", confirmLabel: "Close shift", danger: true })) api(`/shifts/${sh.id}/close/`, { method: "POST", body: { counted_cash: v.counted } }).then((r) => { const d = r as { discrepancy: string }; setMsg({ ok: true, t: `Shift closed. Discrepancy: ${d.discrepancy}` }); refresh(); }).catch(fail);
  };
  const cashMove = async (kind: "withdrawal" | "deposit") => {
    const v = await promptFor({ title: kind === "deposit" ? "Cash deposit" : "Cash withdrawal", confirmLabel: "Record", fields: [{ name: "amount", label: "Amount", type: "number", min: 0.01, step: "0.01" }, { name: "reason", label: "Reason" }] });
    if (!v) return;
    api(`/shifts/${shift.data!.id}/cash-movements/`, { method: "POST", body: { kind, amount: v.amount, reason: v.reason } }).then(() => { succeed(kind === "withdrawal" ? "Withdrawal requested: a manager must approve it." : "Deposit recorded."); refresh(); }).catch(fail);
  };

  // ---------- cart ----------
  const [term, setTerm] = useState(""); const [cart, setCart] = useState<CartLine[]>([]); const [billing, setBilling] = useState<number[]>([]);
  const [tender, setTender] = useState({ method: "cash", amount: "", reference: "" }); const [payments, setPayments] = useState<{ method: string; amount: string; reference: string }[]>([]);
  const [customer, setCustomer] = useState(""); const idemKey = useRef(crypto.randomUUID());
  const searchBox = useRef<HTMLInputElement>(null);
  const results = useQuery({ queryKey: ["pos-search", term], queryFn: () => api<Product[]>(`/pos/products/?${/^\d{6,}$/.test(term) ? "barcode" : "search"}=${encodeURIComponent(term)}`), enabled: term.length >= 2 && !!shift.data });
  const addProduct = (p: Product) => { if (p.requires_prescription) { setMsg({ ok: false, t: `${p.name} needs a pharmacist to dispense it against an approved prescription first.` }); return; } setMsg(null); setCart((c) => c.some((l) => l.product.id === p.id) ? c.map((l) => l.product.id === p.id ? { ...l, quantity: l.quantity + 1 } : l) : [...c, { product: p, quantity: 1, discount_pct: 0 }]); setTerm(""); searchBox.current?.focus(); };
  const patchLine = (id: number, patch: Partial<CartLine>) => setCart((c) => c.map((x) => (x.product.id === id ? { ...x, ...patch } : x)));
  const pend = pending.data?.filter((d) => billing.includes(d.id)) ?? [];
  // Display estimate only: the server recomputes every amount.
  const gross = cart.reduce((t, l) => t + Number(l.product.price) * l.quantity, 0);
  const discount = cart.reduce((t, l) => t + Number(l.product.price) * l.quantity * (l.discount_pct / 100), 0);
  const tax = cart.reduce((t, l) => t + Number(l.product.price) * l.quantity * (1 - l.discount_pct / 100) * (Number(l.product.tax_rate) / 100), 0);
  const rxTotal = pend.reduce((t, d) => t + Number(d.estimated_total), 0);
  const est = gross - discount + tax + rxTotal;
  const tendered = payments.reduce((t, p) => t + Number(p.amount || 0), 0);
  const verified = !!momo.data?.enabled && tender.method === "mobile_money"; // the reference then comes from the provider, never typed
  const useCollection = useCallback((c: Collection) => setPayments((list) => list.some((p) => p.reference === c.reference) ? list : [...list, { method: "mobile_money", amount: c.amount, reference: c.reference }]), []);
  const addPayment = () => { if (Number(tender.amount) > 0) { setPayments([...payments, tender]); setTender({ method: "cash", amount: "", reference: "" }); } };

  const [receipt, setReceipt] = useState<SaleDetail | null>(null);
  const checkout = useMutation({
    mutationFn: () => api<SaleDetail>("/sales/", { method: "POST", headers: { "Idempotency-Key": idemKey.current }, body: { items: cart.map((l) => ({ medicine: l.product.id, quantity: l.quantity, discount_pct: l.discount_pct })), dispensing_ids: billing, payments, customer_name: customer } }),
    onSuccess: (s) => { setReceipt(s); setCart([]); setBilling([]); setPayments([]); setCustomer(""); idemKey.current = crypto.randomUUID(); succeed(`Sale ${s.reference_number} completed.`); refresh(); },
    onError: fail, // the same idempotency key is kept so a retry can never double-charge
  });

  const sellRef = async (s: SaleRow | SaleDetail) => { try { await openProtectedFile(`/sales/${s.id}/receipt/pdf/`); } catch (e) { fail(e); } };
  const emailReceipt = async (s: SaleRow | SaleDetail) => {
    const v = await promptFor({ title: "Email receipt", confirmLabel: "Send receipt", fields: [{ name: "email", label: "Customer's email address", type: "email" }] });
    if (v?.email) api(`/sales/${s.id}/receipt/email/`, { method: "POST", body: { email: v.email } }).then(() => succeed("Receipt queued for email.")).catch(fail);
  };
  const refund = async (s: SaleRow, cancel: boolean) => {
    const v = await promptFor({ title: `${cancel ? "Cancel sale" : "Return items"} · ${s.reference_number}`, confirmLabel: "Continue", danger: true, fields: [
      { name: "reason", label: cancel ? "Reason for cancelling this sale" : "Return reason", type: "textarea" },
      { name: "method", label: "Refund method", type: "select", defaultValue: "cash", options: METHODS.map((m) => [m[0], m[1]]) },
      { name: "reference", label: "Refund reference (not needed for cash)", required: false }] });
    if (!v) return;
    const { reason, method } = v;
    const reference = method === "cash" ? "" : v.reference;
    if (!(await confirmDialog({ title: `${cancel ? "Cancel" : "Return items on"} sale ${s.reference_number}?`, message: "A credit note is issued and this is permanent.", confirmLabel: cancel ? "Cancel sale" : "Continue return", danger: true }))) return;
    try {
      if (cancel) {
        await api(`/sales/${s.id}/cancel/`, { method: "POST", body: { reason, refund_method: method, refund_reference: reference } });
      } else {
        const d = await api<SaleDetail>(`/sales/${s.id}/`);
        const open = d.lines.map((l) => ({ l, max: l.quantity - l.quantity_returned })).filter((x) => x.max > 0);
        const r = await promptFor({ title: "Quantities to return", confirmLabel: "Issue credit note", danger: true, fields: [
          ...open.map((x) => ({ name: String(x.l.id), label: `${x.l.name} (max ${x.max}, 0 to skip)`, type: "number" as const, min: 0, max: x.max, step: "1", defaultValue: "0" })),
          { name: "restock", label: "Return the items to sellable stock? (Never for damaged goods or dispensed prescriptions.)", type: "select", defaultValue: "no", options: [["no", "No, do not restock"], ["yes", "Yes, return to stock"]] }] });
        if (!r) return;
        const lines = open.map((x) => ({ sale_line: x.l.id, quantity: Number(r[String(x.l.id)] || 0) })).filter((x) => x.quantity > 0);
        if (!lines.length) return;
        await api(`/sales/${s.id}/return/`, { method: "POST", body: { lines, reason, refund_method: method, refund_reference: reference, restock: r.restock === "yes" } });
      }
      succeed("Credit note issued."); refresh();
    } catch (e) { fail(e); }
  };

  const sh = shift.data;
  return (
    <div className="space-y-5">
      <PageHeader title="Point of sale" subtitle="Search or scan medicines, take payment and print the receipt."
        actions={sh && <>
          <button className="btn btn-outline btn-sm" onClick={() => cashMove("deposit")}><ArrowDownToLine size={15} aria-hidden />Cash deposit</button>
          <button className="btn btn-outline btn-sm" onClick={() => cashMove("withdrawal")}><ArrowUpFromLine size={15} aria-hidden />Cash withdrawal</button>
          <button className="btn btn-secondary btn-sm" onClick={closeShift}><Lock size={15} aria-hidden />Close shift</button></>} />
      {msg && <p role={msg.ok ? "status" : "alert"} className={`alert ${msg.ok ? "alert-success" : "alert-error"}`}>{msg.t}</p>}
      {shift.isLoading && <Loading rows={2} />}

      {!shift.isLoading && !sh && can("pos.sell") && (
        <form onSubmit={(e) => { e.preventDefault(); openShift.mutate(); }} className="card mx-auto max-w-lg space-y-4 p-6">
          <div className="flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-xl bg-teal-50 text-teal-700"><Wallet size={22} aria-hidden /></span><div><h2 className="section-title">Start your shift</h2><p className="text-sm text-muted">You must open a shift before selling.</p></div></div>
          <label className="field-label">Opening cash<input type="number" min="0" step="0.01" required className="mt-1 w-full px-3 py-2" value={opening} onChange={(e) => setOpening(e.target.value)} placeholder="Enter your opening cash" /></label>
          {!user?.branch && <label className="field-label">Branch<select required className="mt-1 w-full px-3 py-2" value={branch} onChange={(e) => setBranch(e.target.value)}><option value="">Select a branch</option>{branches.data?.results.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>}
          <button className="btn btn-primary w-full" disabled={openShift.isPending}>Start shift</button>
        </form>)}

      {sh && (
        <div className="card flex flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 text-sm">
          <span className="badge badge-success">Shift open</span>
          <span><span className="text-muted">Sales </span><strong className="tabular-nums">{sh.totals.sales_count}</strong></span>
          <span><span className="text-muted">Sales total </span><strong className="tabular-nums">{sh.totals.sales_total}</strong></span>
          <span><span className="text-muted">Expected cash </span><strong className="tabular-nums">{sh.totals.expected_cash}</strong></span>
          {sh.cash_movements.filter((m) => m.status === "pending").map((m) => <span key={m.id} className="flex items-center gap-2"><span className="badge badge-warning">Withdrawal {m.amount} awaiting approval</span>{can("sales.refund") && (["approve", "reject"] as const).map((what) => <button key={what} className={`btn-link capitalize ${what === "reject" ? "btn-link-danger" : ""}`} onClick={async () => { if (await confirmDialog({ title: `${what === "approve" ? "Approve" : "Reject"} this withdrawal?`, message: `Amount ${m.amount}`, danger: what === "reject" })) api(`/cash-movements/${m.id}/${what}/`, { method: "POST" }).then(refresh).catch(fail); }}>{what}</button>)}</span>)}
        </div>)}

      {sh && can("pos.sell") && (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_26rem]">
          <div className="space-y-4">
            <section aria-label="Find medicines" className="card p-4">
              <div className="relative">
                <Search size={18} aria-hidden className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input ref={searchBox} autoFocus aria-label="Search products or scan a barcode" placeholder="Enter your medicine name or scan a barcode" className="w-full py-3 pl-11 pr-11 !text-base" value={term} onChange={(e) => setTerm(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && results.data?.length === 1) { e.preventDefault(); addProduct(results.data[0]); } }} />
                <ScanBarcode size={20} aria-hidden className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              </div>
              {term.length < 2 && <p className="px-1 pt-6 pb-4 text-center text-sm text-muted">Type at least two characters or scan a barcode to find medicines.</p>}
              {results.isFetching && <p role="status" className="pt-3 text-sm text-muted">Searching…</p>}
              {term.length >= 2 && results.data?.length === 0 && <p className="pt-6 pb-4 text-center text-sm text-muted">No medicines match “{term}”.</p>}
              {results.isError && <p role="alert" className="alert alert-error mt-3">{errText(results.error)}</p>}
              {!!results.data?.length && (
                <ul className="mt-4 grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
                  {results.data.map((p) => (
                    <li key={p.id}>
                      <button type="button" onClick={() => addProduct(p)} className="flex h-full w-full flex-col rounded-xl border border-line bg-white p-3.5 text-left transition hover:border-primary hover:shadow-md">
                        <span className="flex items-start justify-between gap-2"><span className="font-semibold leading-snug">{p.name}</span>{p.requires_prescription && <span className="badge badge-danger">Rx</span>}</span>
                        <span className="text-xs text-muted">{p.strength}</span>
                        <span className="mt-3 flex items-end justify-between"><span className="text-lg font-bold tabular-nums text-primary">{p.price}</span><span className={`text-xs font-medium ${p.stock <= 0 ? "text-danger" : "text-muted"}`}>{p.stock} in stock</span></span>
                      </button>
                    </li>))}
                </ul>)}
            </section>
            {!!pending.data?.length && (
              <section className="card p-4">
                <h2 className="section-title mb-1">Dispensed prescriptions awaiting payment</h2><p className="mb-3 text-sm text-muted">Tick a prescription to add it to this sale.</p>
                <ul className="space-y-2">{pending.data.map((d) => (
                  <li key={d.id}><label className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-sm ${billing.includes(d.id) ? "border-primary bg-teal-50" : "border-line"}`}>
                    <input type="checkbox" checked={billing.includes(d.id)} onChange={(e) => setBilling(e.target.checked ? [...billing, d.id] : billing.filter((x) => x !== d.id))} />
                    <FileText size={17} aria-hidden className="text-muted" /><span className="flex-1"><strong>{d.prescription}</strong> · {d.patient}<span className="block text-xs text-muted">{d.items.map((i) => `${i.medicine} × ${i.quantity}`).join(", ")}</span></span><span className="font-semibold tabular-nums">≈ {d.estimated_total}</span>
                  </label></li>))}</ul>
              </section>)}
          </div>

          <section aria-label="Cart" className="card flex flex-col xl:sticky xl:top-24">
            <header className="flex items-center justify-between border-b border-line px-4 py-3"><h2 className="section-title flex items-center gap-2"><ShoppingCart size={18} aria-hidden />Cart</h2><span className="text-sm text-muted">{cart.length + pend.length} item{cart.length + pend.length === 1 ? "" : "s"}</span></header>
            <div className="max-h-[38vh] space-y-3 overflow-y-auto px-4 py-3">
              {cart.length === 0 && pend.length === 0 && <p className="py-6 text-center text-sm text-muted">The cart is empty.</p>}
              {cart.map((l) => (
                <div key={l.product.id} className="rounded-lg border border-line p-3">
                  <div className="flex items-start justify-between gap-2"><div><p className="text-sm font-semibold">{l.product.name}</p><p className="text-xs text-muted">{l.product.strength} · {l.product.price} each</p></div>
                    <button aria-label={`Remove ${l.product.name}`} className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-danger" onClick={async () => { if (await confirmDialog({ title: "Remove this item?", message: l.product.name, confirmLabel: "Remove", danger: true })) setCart((c) => c.filter((x) => x.product.id !== l.product.id)); }}><Trash2 size={16} /></button></div>
                  <div className="mt-2 flex items-center gap-3">
                    <div className="flex items-center rounded-lg border border-line">
                      <button type="button" aria-label={`Decrease quantity of ${l.product.name}`} className="p-2 hover:bg-slate-100" onClick={() => patchLine(l.product.id, { quantity: Math.max(1, l.quantity - 1) })}><Minus size={14} /></button>
                      <input aria-label={`Quantity of ${l.product.name}`} placeholder="Qty" type="number" min="1" className="w-14 !min-h-8 !border-0 text-center !shadow-none" value={l.quantity} onChange={(e) => patchLine(l.product.id, { quantity: Math.max(1, Number(e.target.value)) })} />
                      <button type="button" aria-label={`Increase quantity of ${l.product.name}`} className="p-2 hover:bg-slate-100" onClick={() => patchLine(l.product.id, { quantity: l.quantity + 1 })}><Plus size={14} /></button>
                    </div>
                    <label className="flex items-center gap-1 text-xs text-muted">Disc. %<input aria-label={`Discount percent for ${l.product.name}`} placeholder="0" type="number" min="0" max="100" className="w-16 !min-h-8 px-2 py-1" value={l.discount_pct} onChange={(e) => patchLine(l.product.id, { discount_pct: Number(e.target.value) })} /></label>
                    <span className="ml-auto text-sm font-semibold tabular-nums">{money(Number(l.product.price) * l.quantity * (1 - l.discount_pct / 100))}</span>
                  </div>
                </div>))}
              {pend.map((d) => <p key={d.id} className="flex justify-between rounded-lg bg-slate-50 p-3 text-sm"><span>Prescription {d.prescription}</span><span className="font-semibold tabular-nums">≈ {d.estimated_total}</span></p>)}
            </div>
            <div className="space-y-3 border-t border-line px-4 py-3">
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between"><dt className="text-muted">Subtotal</dt><dd className="tabular-nums">{money(gross + rxTotal)}</dd></div>
                {discount > 0 && <div className="flex justify-between"><dt className="text-muted">Discount</dt><dd className="tabular-nums text-danger">−{money(discount)}</dd></div>}
                <div className="flex justify-between"><dt className="text-muted">Tax</dt><dd className="tabular-nums">{money(tax)}</dd></div>
                <div className="flex items-baseline justify-between border-t border-line pt-2"><dt className="font-semibold">Estimated total</dt><dd className="text-2xl font-bold tabular-nums">{money(est)}</dd></div>
              </dl>
              <p className="text-xs text-muted">The final amount is calculated by the server.</p>
              <input aria-label="Customer name" className="w-full px-3 py-2" placeholder={placeholderFor("Customer name")} value={customer} onChange={(e) => setCustomer(e.target.value)} />
              <div role="radiogroup" aria-label="Payment method" className="grid grid-cols-4 gap-1.5">
                {METHODS.map(([value, label, Icon]) => <button type="button" role="radio" aria-checked={tender.method === value} key={value} onClick={() => setTender({ ...tender, method: value })}
                  className={`flex flex-col items-center gap-1 rounded-lg border px-1 py-2 text-[11px] font-semibold leading-tight ${tender.method === value ? "border-primary bg-teal-50 text-teal-800" : "border-line text-slate-600 hover:bg-slate-50"}`}><Icon size={17} aria-hidden />{label}</button>)}
              </div>
              {verified ? (
                <div className="space-y-2">
                  <button type="button" className="btn btn-secondary w-full" disabled={est - tendered <= 0} onClick={() => setCollecting(true)}><Smartphone size={16} aria-hidden />Request mobile money payment</button>
                  {(unused.data ?? []).filter((c) => !payments.some((p) => p.reference === c.reference)).map((c) => <p key={c.id} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-sm"><span>Received, not yet used: <b>{c.amount}</b> <span className="text-xs text-muted">{c.reference}</span></span><button type="button" className="btn-link" onClick={() => useCollection(c)}>Use</button></p>)}
                </div>
              ) : (
              <div className="flex flex-wrap gap-2">
                <input aria-label="Amount tendered" type="number" min="0.01" step="0.01" className="min-w-0 flex-1 px-3 py-2" placeholder="Enter your tendered amount" value={tender.amount} onChange={(e) => setTender({ ...tender, amount: e.target.value })} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addPayment(); } }} />
                {tender.method !== "cash" && <input aria-label="Transaction reference" className="min-w-0 flex-1 px-3 py-2" placeholder="Enter your transaction reference" value={tender.reference} onChange={(e) => setTender({ ...tender, reference: e.target.value })} />}
                <button type="button" className="btn btn-outline" onClick={addPayment}>Add payment</button>
              </div>)}
              {payments.length > 0 && <ul className="space-y-1 text-sm">{payments.map((p, i) => <li key={i} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-1.5"><span>{methodLabel(p.method)} {p.reference && <span className="text-xs text-muted">· {p.reference}</span>}</span><span className="flex items-center gap-2"><strong className="tabular-nums">{p.amount}</strong><button aria-label="Remove payment" className="text-slate-400 hover:text-danger" onClick={() => setPayments(payments.filter((_, j) => j !== i))}><Trash2 size={14} /></button></span></li>)}</ul>}
              <p className="flex justify-between text-sm"><span className="text-muted">Tendered <strong className="text-ink tabular-nums">{money(tendered)}</strong></span><span className="text-muted">Change ≈ <strong className="text-ink tabular-nums">{money(Math.max(0, tendered - est))}</strong></span></p>
              <button disabled={checkout.isPending || (cart.length === 0 && billing.length === 0)} onClick={() => checkout.mutate()} className="btn btn-primary w-full !min-h-12 !text-base"><CheckCircle2 size={19} aria-hidden />{checkout.isPending ? "Processing…" : "Complete sale"}</button>
            </div>
          </section>
        </div>)}

      {receipt && (
        <Modal title="Sale completed" onClose={() => setReceipt(null)} footer={<>
          <button className="btn btn-outline" onClick={() => emailReceipt(receipt)}><Mail size={16} aria-hidden />Email receipt</button>
          <button className="btn btn-primary" onClick={() => sellRef(receipt)}><Printer size={16} aria-hidden />Open PDF / print</button></>}>
          <section aria-label="Receipt" className="text-center">
            <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-green-50 text-success"><CheckCircle2 size={30} aria-hidden /></span>
            <p className="mt-3 text-sm text-muted">Receipt {receipt.receipt_number} · {receipt.reference_number}</p>
            <p className="mt-1 text-3xl font-bold tabular-nums">{receipt.total}</p><p className="text-sm text-muted">Paid {receipt.amount_paid}</p>
          </section>
        </Modal>)}

      {collecting && <MobileMoneyDialog suggested={Math.max(0, est - tendered)} customer={customer} currency={momo.data?.currency ?? ""} onPaid={useCollection} onClose={() => setCollecting(false)} />}
      {(can("sales.view_branch") || can("sales.view_own")) && <section className="space-y-3">
        <h2 className="section-title">{can("sales.view_branch") ? "Branch sales" : "My sales"}</h2>
        <ServerTable<SaleRow> queryKey={["sales"]} path="/sales/" rowKey={(x) => x.id} empty="No sales yet."
          columns={[{ key: "ref", header: "Reference", render: (x) => <b>{x.reference_number}</b> }, { key: "when", header: "When", render: (x) => dateTime(x.created_at) }, { key: "cashier", header: "Cashier", render: (x) => x.cashier_name }, { key: "customer", header: "Customer", render: (x) => x.customer_name || "—" }, { key: "total", header: "Total", align: "right", render: (x) => <b>{x.total}</b> }, { key: "status", header: "Status", render: (x) => <StatusBadge status={x.status} /> },
            { key: "actions", header: "Actions", align: "right", render: (x) => <span className="inline-flex flex-wrap justify-end gap-1.5"><button className="btn-link" onClick={() => sellRef(x)}>Receipt</button>{can("pos.sell") && <button className="btn-link" onClick={() => emailReceipt(x)}>Email</button>}
              {can("sales.refund") && ["completed", "partially_returned"].includes(x.status) && <><button className="btn-link" onClick={() => refund(x, false)}>Return</button><button className="btn-link btn-link-danger" onClick={() => refund(x, true)}>Cancel</button></>}</span> }]} />
      </section>}
    </div>
  );
}
