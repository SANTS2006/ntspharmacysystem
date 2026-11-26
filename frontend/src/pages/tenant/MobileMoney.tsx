/** Counter mobile money: raise a USSD payment code, wait for the provider to confirm, then hand the verified reference to the sale. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Smartphone, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { OrbitLogo } from "../../components/brand/Brand";
import { Modal, Spinner, errorMessage } from "../../components/ui";
import { api } from "../../lib/api";
import { money } from "../../lib/format";

export interface Collection { id: number; reference: string; amount: string; currency: string; status: string; ussd_code: string; customer_name: string; expires_at: string | null; used: boolean }

export function MobileMoneyDialog({ suggested, customer, currency, onPaid, onClose }: { suggested: number; customer: string; currency: string; onPaid: (c: Collection) => void; onClose: () => void }) {
  const qc = useQueryClient();
  const [amount, setAmount] = useState(suggested > 0 ? suggested.toFixed(2) : "");
  const [started, setStarted] = useState<Collection | null>(null);
  const reported = useRef(false);
  const create = useMutation({ mutationFn: () => api<Collection>("/payments/mobile-money/", { method: "POST", body: { amount, customer_name: customer } }), onSuccess: setStarted });
  const live = useQuery({ queryKey: ["momo", started?.id], queryFn: () => api<Collection>(`/payments/mobile-money/${started!.id}/`), enabled: !!started, refetchInterval: (q) => (["pending", "processing"].includes(q.state.data?.status ?? "pending") ? 4000 : false) });
  const cancel = useMutation({ mutationFn: () => api<Collection>(`/payments/mobile-money/${started!.id}/cancel/`, { method: "POST" }), onSuccess: onClose });
  const c = live.data ?? started;
  useEffect(() => {
    if (c?.status === "completed" && !reported.current) { reported.current = true; onPaid(c); qc.invalidateQueries({ queryKey: ["momo-unused"] }); }
  }, [c, onPaid, qc]);
  const waiting = !!c && ["pending", "processing"].includes(c.status);
  return (
    <Modal title="Mobile money payment" onClose={onClose}>
      {!c ? (
        <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="space-y-4">
          <p className="text-sm text-muted">We create a payment code for exactly this amount. The customer dials it on their phone.</p>
          {create.isError && <p role="alert" className="alert alert-error">{errorMessage(create.error)}</p>}
          <label className="field-label">Amount to collect ({currency})<input required autoFocus type="number" min="0.01" step="0.01" className="mt-1.5 w-full !text-lg font-bold" placeholder="Enter your amount" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
          <div className="flex justify-end gap-2"><button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={create.isPending}>{create.isPending ? <Spinner /> : <Smartphone size={16} aria-hidden />}Create payment code</button></div>
        </form>
      ) : (
        <div className="space-y-4 text-center" aria-live="polite">
          {waiting && <><div className="flex justify-center"><OrbitLogo size={76} /></div>
            <p className="text-sm text-muted">Ask the customer to dial</p>
            <p className="select-all rounded-2xl border-2 border-dashed border-line p-4 text-3xl font-black tracking-wider">{c.ussd_code}</p>
            <p className="text-lg font-bold">{money(c.amount, c.currency)}</p>
            <p className="flex items-center justify-center gap-2 text-sm text-muted"><Spinner size={13} />{c.status === "processing" ? "Payment received, finishing…" : "Waiting for the provider to confirm payment…"}</p></>}
          {c.status === "completed" && <><CheckCircle2 size={56} aria-hidden className="mx-auto text-success" /><p className="text-lg font-bold">{money(c.amount, c.currency)} received</p><p className="text-sm text-muted">{c.reference} has been added to this sale.</p></>}
          {!waiting && c.status !== "completed" && <><XCircle size={56} aria-hidden className="mx-auto text-danger" /><p className="text-lg font-bold capitalize">Payment {c.status}</p><p className="text-sm text-muted">No money was added to the sale.</p></>}
          {cancel.isError && <p role="alert" className="alert alert-error">{errorMessage(cancel.error)}</p>}
          <div className="flex justify-center gap-2">
            {c.status === "pending" && <button className="btn btn-outline btn-link-danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>Cancel request</button>}
            <button className="btn btn-primary" onClick={onClose}>{waiting ? "Hide (keeps waiting)" : "Done"}</button>
          </div>
        </div>)}
    </Modal>
  );
}
