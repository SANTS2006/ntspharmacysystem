import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { getAccessToken } from "./api";

const REFRESH: Record<string, string[]> = {
  "order.": ["staff-orders", "my-orders", "my-order", "orders", "payments", "sales"],
  "payment.": ["my-order", "staff-orders", "attempts"],
  "qr_request.": ["qr-requests"],
  "prescription.": ["rxs", "rx"],
  "inventory.": ["alerts", "inv-overview", "batches", "medicines"],
};

/** Live updates over an authenticated WebSocket. The first message carries the access token (never the URL); events hold only ids, so we
 *  refetch through the normal permission-checked REST API. If the socket cannot connect, the pages' polling keeps working. */
export function useRealtime(enabled: boolean) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let tries = 0;
    let stopped = false;
    const connect = () => {
      const token = getAccessToken();
      if (!token || stopped) return;
      ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/notifications/`);
      ws.onopen = () => ws?.send(JSON.stringify({ type: "auth", token }));
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data);
        if (msg.type === "ready") tries = 0;
        if (msg.type === "event") {
          for (const [prefix, keys] of Object.entries(REFRESH)) {
            if (String(msg.event).startsWith(prefix)) keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
          }
        }
      };
      ws.onclose = () => {
        if (!stopped) timer = window.setTimeout(connect, Math.min(30000, 1000 * 2 ** tries++));
      };
    };
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      ws?.close();
    };
  }, [enabled, qc]);
}
