/** "Website contact": messages sent through the website's contact form, with follow-up tools. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Inbox, MailOpen, Save, Send, Trash2 } from "lucide-react";
import { useState } from "react";
import { Modal, PageHeader, Spinner, StatCard, StatusBadge, errorMessage, useConfirm, useToast } from "../../components/ui";
import { ServerTable } from "../../components/ui/ServerTable";
import { api } from "../../lib/api";
import { day } from "../../lib/format";

interface Message { id: number; name: string; email: string; phone: string; subject: string; message: string; status: "new" | "in_progress" | "resolved"; staff_note: string; reply: string; replied_at: string | null; created_at: string; handled_by: string | null }
const STATUSES: [string, string][] = [["new", "New"], ["in_progress", "In progress"], ["resolved", "Resolved"]];

function Detail({ message, onClose, changed }: { message: Message; onClose: () => void; changed: () => void }) {
  const toast = useToast(); const confirm = useConfirm();
  const [m, setM] = useState(message); const [status, setStatus] = useState<string>(message.status); const [note, setNote] = useState(message.staff_note);
  const [reply, setReply] = useState(""); const [busy, setBusy] = useState<string | null>(null);
  const run = async (what: string, work: () => Promise<void>) => { setBusy(what); try { await work(); changed(); } catch (e) { toast(errorMessage(e), "error"); } setBusy(null); };
  const save = () => run("save", async () => { setM(await api<Message>(`/website/messages/${m.id}/`, { method: "PATCH", body: { status, staff_note: note } })); toast("Message updated."); });
  const send = (e: React.FormEvent) => { e.preventDefault(); run("reply", async () => { const next = await api<Message>(`/website/messages/${m.id}/reply/`, { method: "POST", body: { message: reply } }); setM(next); setStatus(next.status); setReply(""); toast("Your reply was submitted for emailing."); }); };
  const remove = async () => { if (await confirm({ title: "Delete this message?", message: "It is permanently removed and cannot be recovered.", confirmLabel: "Delete", danger: true })) run("delete", async () => { await api(`/website/messages/${m.id}/`, { method: "DELETE" }); toast("Message deleted."); onClose(); }); };
  const rows: [string, React.ReactNode][] = [["From", m.name], ["Email", <a className="text-primary" href={`mailto:${m.email}`}>{m.email}</a>], ["Phone", m.phone ? <a className="text-primary" href={`tel:${m.phone}`}>{m.phone}</a> : "—"], ["Received", new Date(m.created_at).toLocaleString()], ["Handled by", m.handled_by ?? "—"]];
  return (
    <Modal title={m.subject} size="lg" onClose={onClose}>
      <div className="space-y-5">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">{rows.map(([k, v]) => <div key={k}><dt className="text-xs font-bold uppercase tracking-wide text-muted">{k}</dt><dd className="break-words font-semibold">{v}</dd></div>)}</dl>
        <p className="whitespace-pre-line break-words rounded-xl border border-line p-4 text-sm leading-6">{m.message}</p>
        {m.reply && <div className="alert alert-success"><b>Reply{m.replied_at ? ` on ${day(m.replied_at)}` : ""}</b><p className="mt-1 whitespace-pre-line">{m.reply}</p></div>}
        <div className="grid gap-4 sm:grid-cols-[12rem_1fr]">
          <label className="field-label">Status<select className="mt-1.5 w-full" value={status} onChange={(e) => setStatus(e.target.value)}>{STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <label className="field-label">Internal note<input className="mt-1.5 w-full" maxLength={1000} value={note} placeholder="Enter your internal note" onChange={(e) => setNote(e.target.value)} /></label>
        </div>
        <div className="flex flex-wrap justify-between gap-2"><button className="btn btn-outline btn-link-danger" disabled={!!busy} onClick={remove}><Trash2 size={15} aria-hidden />Delete</button><button className="btn btn-outline" disabled={!!busy} onClick={save}>{busy === "save" ? <Spinner /> : <Save size={15} aria-hidden />}Save status and note</button></div>
        <form onSubmit={send} className="space-y-3 border-t border-line pt-4">
          <label className="field-label">Reply by email<textarea className="mt-1.5 w-full" rows={4} required maxLength={3000} value={reply} placeholder="Enter your reply" onChange={(e) => setReply(e.target.value)} /></label>
          <button className="btn btn-primary" disabled={!!busy}>{busy === "reply" ? <Spinner /> : <Send size={15} aria-hidden />}Send reply</button>
        </form>
      </div>
    </Modal>
  );
}

export default function WebsiteMessages() {
  const qc = useQueryClient(); const [open, setOpen] = useState<Message | null>(null);
  const summary = useQuery({ queryKey: ["website-messages", "summary"], queryFn: () => api<{ summary: Record<string, number> }>("/website/messages/"), refetchInterval: 60_000 });
  const count = (k: string) => summary.data?.summary[k] ?? "…";
  return (
    <div className="space-y-5">
      <PageHeader title="Website contact" subtitle="Messages sent through the contact form on your website." />
      <div className="grid gap-4 sm:grid-cols-3"><StatCard label="New" value={count("new")} icon={Inbox} tone="info" /><StatCard label="In progress" value={count("in_progress")} icon={MailOpen} tone="warning" /><StatCard label="Resolved" value={count("resolved")} icon={CheckCircle2} /></div>
      <ServerTable<Message> queryKey={["website-messages"]} path="/website/messages/" rowKey={(m) => m.id} search="Enter your message search" empty="No messages yet." onRowClick={setOpen} refetchInterval={60_000}
        filters={[{ name: "status", label: "All statuses", options: STATUSES }]}
        columns={[
          { key: "received", header: "Received", render: (m) => day(m.created_at) },
          { key: "from", header: "From", render: (m) => <span><b className="block">{m.name}</b><span className="text-xs text-muted">{m.email}</span></span> },
          { key: "phone", header: "Phone", render: (m) => m.phone || "—" },
          { key: "subject", header: "Subject", render: (m) => <span className="block max-w-sm"><b className="block truncate">{m.subject}</b><span className="block truncate text-xs text-muted">{m.message}</span></span> },
          { key: "status", header: "Status", render: (m) => <StatusBadge status={m.status} /> },
          { key: "actions", header: "Actions", align: "right", render: (m) => <button className="btn-link" onClick={(e) => { e.stopPropagation(); setOpen(m); }}>Open</button> },
        ]} />
      {open && <Detail key={open.id} message={open} onClose={() => setOpen(null)} changed={() => qc.invalidateQueries({ queryKey: ["website-messages"] })} />}
    </div>
  );
}
