import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Banknote, Bell, Boxes, CalendarClock, CreditCard, DatabaseBackup, MessageSquare, Package, Receipt, ScrollText, ShieldAlert, Truck, UserPlus, Wallet, type LucideIcon } from "lucide-react";
import { api } from "./api";

export interface Note { id: number; kind: string; level: "info" | "success" | "warning" | "danger"; title: string; body: string; link: string; read: boolean; read_at: string | null; created_at: string }
export interface NotePage { count: number; next: string | null; previous: string | null; unread: number; results: Note[] }

const ICONS: Record<string, LucideIcon> = { order: Package, payment: CreditCard, inventory: Boxes, prescription: ScrollText, delivery: Truck, appointment: CalendarClock, inquiry: MessageSquare, contact: MessageSquare, customer: UserPlus, security: ShieldAlert, billing: Receipt, backup: DatabaseBackup, cash: Wallet, payroll: Banknote };
export const noteIcon = (kind: string) => ICONS[kind] ?? Bell;
export const NOTE_TONES: Record<Note["level"], string> = { info: "bg-sky-50 text-sky-700", success: "bg-emerald-50 text-emerald-700", warning: "bg-amber-50 text-amber-700", danger: "bg-red-50 text-red-700" };

/** Newest notifications for the bell. Updates arrive over the WebSocket; the slow poll covers a dropped connection. */
export const useLatestNotes = () => useQuery({ queryKey: ["notifications", "latest"], queryFn: () => api<NotePage>("/notifications/?page_size=6"), refetchInterval: 45_000, retry: false });

export function useNoteActions() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ["notifications"] });
  return {
    markRead: useMutation({ mutationFn: ({ id, read = true }: { id: number; read?: boolean }) => api<Note>(`/notifications/${id}/read/`, { method: "POST", body: { read } }), onSuccess: done }),
    markAll: useMutation({ mutationFn: () => api("/notifications/read-all/", { method: "POST" }), onSuccess: done }),
    remove: useMutation({ mutationFn: (id: number) => api(`/notifications/${id}/`, { method: "DELETE" }), onSuccess: done }),
  };
}
