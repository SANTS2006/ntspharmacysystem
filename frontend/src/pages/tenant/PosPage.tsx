import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ApiError, api, openProtectedFile } from "../../lib/api";
import { useAuth } from "../../lib/auth";

interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
interface Product { id: number; name: string; strength: string; price: string; tax_rate: string; stock: number; requires_prescription: boolean }
interface Shift { id: number; status: string; opening_cash: string; expected_cash: string; totals: { sales_count: number; sales_total: string; cash_received: string; cash_refunds: string; expected_cash: string }; cash_movements: { id: number; kind: string; amount: string; status: string }[] }
interface SaleRow { id: number; reference_number: string; status: string; total: string; amount_paid: string; balance: string; customer_name: string; created_at: string; cashier_name: string }
interface SaleDetail extends SaleRow { receipt_number: string; lines: { id: number; name: string; quantity: number; quantity_returned: number; line_total: string }[] }
interface Pending { id: number; prescription: string; patient: string; estimated_total: string; items: { medicine: string; quantity: number }[] }
interface CartLine { product: Product; quantity: number; discount_pct: number }

const errText = (e: unknown) => (e instanceof ApiError ? `${e.message} ${e.details ? JSON.stringify(e.details) : ""}` : "Request failed.");
const inputCls = "rounded border p-2";
const brand = { background: "var(--brand)" };
const money = (n: number) => n.toFixed(2);

export default function PosPage() {
  const { user } = useAuth(); const qc = useQueryClient();
  const can = (p: string) => !!user?.permissions.includes(p);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const fail = (e: unknown) => setMsg({ ok: false, t: errText(e) });
  const refresh = () => qc.invalidateQueries();

  const shift = useQuery({ queryKey: ["shift"], queryFn: () => api<Shift | null>("/shifts/current/") });
  const history = useQuery({ queryKey: ["sales"], queryFn: () => api<Page<SaleRow>>("/sales/") });
  const pending = useQuery({ queryKey: ["pending-disp", shift.data?.id], queryFn: () => api<Pending[]>("/pos/pending-dispensings/"), enabled: !!shift.data });
  const branches = useQuery({ queryKey: ["branches"], queryFn: () => api<Page<{ id: number; name: string }>>("/branches/"), enabled: can("branch.view") && !user?.branch });

  // ---------- shift ----------
  const [opening, setOpening] = useState("0"); const [branch, setBranch] = useState(user?.branch ? String(user.branch) : "");
  const openShift = useMutation({ mutationFn: () => api("/shifts/open/", { method: "POST", body: { opening_cash: opening, branch: branch ? Number(branch) : undefined } }), onSuccess: () => { setMsg({ ok: true, t: "Shift opened." }); refresh(); }, onError: fail });
  const closeShift = () => {
    const sh = shift.data; if (!sh) return;
    const counted = window.prompt(`Enter the counted cash in the drawer (expected ${sh.totals.expected_cash})`); if (counted === null) return;
    if (window.confirm("Close the shift? This cannot be undone.")) api(`/shifts/${sh.id}/close/`, { method: "POST", body: { counted_cash: counted } }).then((r) => { const d = r as { discrepancy: string }; setMsg({ ok: true, t: `Shift closed. Discrepancy: ${d.discrepancy}` }); refresh(); }).catch(fail);
  };
  const cashMove = (kind: "withdrawal" | "deposit") => {
    const amount = window.prompt(`Enter the ${kind} amount`); if (!amount) return; const reason = window.prompt("Enter the reason"); if (!reason) return;
    api(`/shifts/${shift.data!.id}/cash-movements/`, { method: "POST", body: { kind, amount, reason } }).then(() => { setMsg({ ok: true, t: kind === "withdrawal" ? "Withdrawal requested: a manager must approve it." : "Deposit recorded." }); refresh(); }).catch(fail);
  };

  // ---------- cart ----------
  const [term, setTerm] = useState(""); const [cart, setCart] = useState<CartLine[]>([]); const [billing, setBilling] = useState<number[]>([]);
  const [tender, setTender] = useState({ method: "cash", amount: "", reference: "" }); const [payments, setPayments] = useState<{ method: string; amount: string; reference: string }[]>([]);
  const [customer, setCustomer] = useState(""); const idemKey = useRef(crypto.randomUUID());
  const results = useQuery({ queryKey: ["pos-search", term], queryFn: () => api<Product[]>(`/pos/products/?${/^\d{6,}$/.test(term) ? "barcode" : "search"}=${encodeURIComponent(term)}`), enabled: term.length >= 2 && !!shift.data });
  const addProduct = (p: Product) => { if (p.requires_prescription) { setMsg({ ok: false, t: `${p.name} needs a pharmacist to dispense it against an approved prescription first.` }); return; } setCart((c) => c.some((l) => l.product.id === p.id) ? c.map((l) => l.product.id === p.id ? { ...l, quantity: l.quantity + 1 } : l) : [...c, { product: p, quantity: 1, discount_pct: 0 }]); setTerm(""); };
  const pend = pending.data?.filter((d) => billing.includes(d.id)) ?? [];
  // Display estimate only: the server recomputes every amount.
  const est = cart.reduce((t, l) => { const net = Number(l.product.price) * l.quantity * (1 - l.discount_pct / 100); return t + net * (1 + Number(l.product.tax_rate) / 100); }, 0) + pend.reduce((t, d) => t + Number(d.estimated_total), 0);
  const tendered = payments.reduce((t, p) => t + Number(p.amount || 0), 0);

  const [receipt, setReceipt] = useState<SaleDetail | null>(null);
  const checkout = useMutation({
    mutationFn: () => api<SaleDetail>("/sales/", { method: "POST", headers: { "Idempotency-Key": idemKey.current }, body: { items: cart.map((l) => ({ medicine: l.product.id, quantity: l.quantity, discount_pct: l.discount_pct })), dispensing_ids: billing, payments, customer_name: customer } }),
    onSuccess: (s) => { setReceipt(s); setCart([]); setBilling([]); setPayments([]); setCustomer(""); idemKey.current = crypto.randomUUID(); setMsg({ ok: true, t: `Sale ${s.reference_number} completed.` }); refresh(); },
    onError: fail, // the same idempotency key is kept so a retry can never double-charge
  });

  const sellRef = async (s: SaleRow | SaleDetail) => { try { await openProtectedFile(`/sales/${s.id}/receipt/pdf/`); } catch (e) { fail(e); } };
  const emailReceipt = (s: SaleRow | SaleDetail) => { const email = window.prompt("Enter the customer's email address"); if (email) api(`/sales/${s.id}/receipt/email/`, { method: "POST", body: { email } }).then(() => setMsg({ ok: true, t: "Receipt queued for email." })).catch(fail); };
  const refund = (s: SaleRow, cancel: boolean) => {
    const reason = window.prompt(cancel ? "Enter the reason for cancelling this sale" : "Enter the return reason"); if (!reason) return;
    const method = window.prompt("Enter the refund method (cash, mobile_money, card, bank_transfer)", "cash"); if (!method) return;
    const reference = method === "cash" ? "" : window.prompt("Enter the refund reference") ?? "";
    const run = async () => {
      if (cancel) return api(`/sales/${s.id}/cancel/`, { method: "POST", body: { reason, refund_method: method, refund_reference: reference } });
      const d = await api<SaleDetail>(`/sales/${s.id}/`);
      const lines = d.lines.map((l) => ({ l, max: l.quantity - l.quantity_returned })).filter((x) => x.max > 0).map((x) => ({ sale_line: x.l.id, quantity: Number(window.prompt(`Enter the quantity to return for ${x.l.name} (max ${x.max}, 0 to skip)`, "0") || 0) })).filter((x) => x.quantity > 0);
      if (!lines.length) return null;
      const restock = window.confirm("Return the items to sellable stock? (Never for damaged goods or dispensed prescriptions.)");
      return api(`/sales/${s.id}/return/`, { method: "POST", body: { lines, reason, refund_method: method, refund_reference: reference, restock } });
    };
    if (window.confirm(`${cancel ? "Cancel" : "Return items on"} sale ${s.reference_number}? A credit note is issued and this is permanent.`)) run().then((r) => { if (r) { setMsg({ ok: true, t: "Credit note issued." }); refresh(); } }).catch(fail);
  };

  const sh = shift.data;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Point of sale</h1>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`rounded p-3 text-sm ${msg.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>{msg.t}</p>}
      {!sh && can("pos.sell") && (
        <form onSubmit={(e) => { e.preventDefault(); openShift.mutate(); }} className="flex flex-wrap items-end gap-3 rounded-xl bg-white p-4 shadow-sm">
          <label className="text-sm font-medium">Opening cash<input type="number" min="0" step="0.01" required className={`${inputCls} mt-1 block`} value={opening} onChange={(e) => setOpening(e.target.value)} placeholder="Enter the opening cash" /></label>
          {!user?.branch && <label className="text-sm font-medium">Branch<select required className={`${inputCls} mt-1 block`} value={branch} onChange={(e) => setBranch(e.target.value)}><option value="">Select a branch</option>{branches.data?.results.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>}
          <button className="rounded px-4 py-2 text-white" style={brand}>Start shift</button><p className="text-sm text-slate-600">You must open a shift before selling.</p>
        </form>)}
      {sh && (
        <section className="flex flex-wrap items-center gap-4 rounded-xl bg-white p-3 text-sm shadow-sm">
          <span>Shift open · {sh.totals.sales_count} sales · {sh.totals.sales_total} · expected cash <strong>{sh.totals.expected_cash}</strong></span>
          <button className="underline" onClick={() => cashMove("deposit")}>Cash deposit</button><button className="underline" onClick={() => cashMove("withdrawal")}>Cash withdrawal</button><button className="underline" onClick={closeShift}>Close shift</button>
          {sh.cash_movements.filter((m) => m.status === "pending").map((m) => <span key={m.id} className="rounded bg-amber-100 px-2 text-amber-800">Withdrawal {m.amount} awaiting approval {can("sales.refund") && <button className="underline" onClick={() => api(`/cash-movements/${m.id}/approve/`, { method: "POST" }).then(refresh).catch(fail)}>Approve</button>}</span>)}
        </section>)}

      {sh && can("pos.sell") && (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="space-y-2 rounded-xl bg-white p-4 shadow-sm">
            <input autoFocus aria-label="Search products or scan a barcode" placeholder="Enter a product name or scan a barcode" className={`${inputCls} w-full`} value={term} onChange={(e) => setTerm(e.target.value)} />
            <ul className="divide-y text-sm">{results.data?.map((p) => <li key={p.id}><button className="flex w-full justify-between py-2 text-left hover:bg-slate-50" onClick={() => addProduct(p)}><span>{p.name} {p.strength} {p.requires_prescription && <em className="text-red-700">(Rx)</em>}</span><span>{p.price} · stock {p.stock}</span></button></li>)}</ul>
            {pending.data && pending.data.length > 0 && <div><h2 className="font-semibold">Dispensed prescriptions awaiting payment</h2>{pending.data.map((d) => <label key={d.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={billing.includes(d.id)} onChange={(e) => setBilling(e.target.checked ? [...billing, d.id] : billing.filter((x) => x !== d.id))} />{d.prescription} · {d.patient} · ≈{d.estimated_total}</label>)}</div>}
          </section>
          <section className="space-y-2 rounded-xl bg-white p-4 shadow-sm">
            <h2 className="font-semibold">Cart</h2>
            {cart.length === 0 && pend.length === 0 && <p className="text-sm text-slate-500">Cart is empty.</p>}
            {cart.map((l) => <div key={l.product.id} className="flex items-center gap-2 text-sm"><span className="flex-1">{l.product.name}</span>
              <input aria-label={`Quantity of ${l.product.name}`} type="number" min="1" className="w-16 rounded border p-1" value={l.quantity} onChange={(e) => setCart(cart.map((x) => x.product.id === l.product.id ? { ...x, quantity: Math.max(1, Number(e.target.value)) } : x))} />
              <input aria-label={`Discount percent for ${l.product.name}`} type="number" min="0" max="100" className="w-16 rounded border p-1" value={l.discount_pct} onChange={(e) => setCart(cart.map((x) => x.product.id === l.product.id ? { ...x, discount_pct: Number(e.target.value) } : x))} placeholder="%" />
              <button className="underline" onClick={() => setCart(cart.filter((x) => x.product.id !== l.product.id))}>Remove</button></div>)}
            {pend.map((d) => <p key={d.id} className="text-sm">Prescription {d.prescription}: {d.items.map((i) => `${i.medicine} × ${i.quantity}`).join(", ")}</p>)}
            <p className="text-lg font-semibold">Estimated total: {money(est)} <span className="text-xs font-normal text-slate-500">(final amount is calculated by the server)</span></p>
            <input aria-label="Customer name" className={`${inputCls} w-full`} placeholder="Enter the customer's name (optional)" value={customer} onChange={(e) => setCustomer(e.target.value)} />
            <div className="flex flex-wrap gap-2"><select aria-label="Payment method" className={inputCls} value={tender.method} onChange={(e) => setTender({ ...tender, method: e.target.value })}><option value="cash">Cash</option><option value="mobile_money">Mobile money</option><option value="card">Card</option><option value="bank_transfer">Bank transfer</option></select>
              <input aria-label="Amount tendered" type="number" min="0.01" step="0.01" className={`${inputCls} w-28`} placeholder="Enter the amount" value={tender.amount} onChange={(e) => setTender({ ...tender, amount: e.target.value })} />
              {tender.method !== "cash" && <input aria-label="Transaction reference" className={`${inputCls} w-40`} placeholder="Enter the reference" value={tender.reference} onChange={(e) => setTender({ ...tender, reference: e.target.value })} />}
              <button className="rounded border px-3" onClick={() => { if (Number(tender.amount) > 0) { setPayments([...payments, tender]); setTender({ method: "cash", amount: "", reference: "" }); } }}>Add payment</button></div>
            <ul className="text-sm">{payments.map((p, i) => <li key={i}>{p.method} {p.amount} {p.reference} <button className="underline" onClick={() => setPayments(payments.filter((_, j) => j !== i))}>remove</button></li>)}</ul>
            <p className="text-sm">Tendered {money(tendered)} · change ≈ {money(Math.max(0, tendered - est))}</p>
            <button disabled={checkout.isPending || (cart.length === 0 && billing.length === 0)} onClick={() => checkout.mutate()} className="w-full rounded px-4 py-2 text-white disabled:opacity-50" style={brand}>{checkout.isPending ? "Processing…" : "Complete sale"}</button>
          </section>
        </div>)}

      {receipt && <section aria-label="Receipt" className="rounded-xl border bg-white p-4 shadow"><h2 className="font-semibold">Receipt {receipt.receipt_number} · {receipt.reference_number}</h2><p className="text-sm">Total {receipt.total} · Paid {receipt.amount_paid}</p>
        <div className="mt-2 flex gap-2"><button className="rounded border px-3 py-1" onClick={() => sellRef(receipt)}>Open PDF / print</button><button className="rounded border px-3 py-1" onClick={() => emailReceipt(receipt)}>Email receipt</button><button className="underline" onClick={() => setReceipt(null)}>Close</button></div></section>}

      <section><h2 className="mb-2 font-semibold">{can("sales.view_branch") ? "Branch sales" : "My sales"}</h2>
        {history.data?.results.length === 0 && <p className="text-slate-500">No sales yet.</p>}
        {history.data && history.data.results.length > 0 && <div className="overflow-x-auto rounded-xl bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Reference</th><th>When</th><th>Cashier</th><th>Customer</th><th>Total</th><th>Status</th><th /></tr></thead>
          <tbody>{history.data.results.map((s) => <tr key={s.id} className="border-t"><td className="p-3">{s.reference_number}</td><td>{new Date(s.created_at).toLocaleString()}</td><td>{s.cashier_name}</td><td>{s.customer_name}</td><td>{s.total}</td><td>{s.status.replace("_", " ")}</td>
            <td className="space-x-2"><button className="underline" onClick={() => sellRef(s)}>Receipt</button><button className="underline" onClick={() => emailReceipt(s)}>Email</button>
              {can("sales.refund") && ["completed", "partially_returned"].includes(s.status) && <><button className="underline" onClick={() => refund(s, false)}>Return</button><button className="underline" onClick={() => refund(s, true)}>Cancel</button></>}</td></tr>)}</tbody></table></div>}</section>
    </div>
  );
}
