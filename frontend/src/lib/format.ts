export const money = (v: unknown, currency?: string) => {
  const n = Number(v ?? 0);
  const text = Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : String(v);
  return currency ? `${currency} ${text}` : text;
};
export const compact = (v: unknown) => new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(Number(v ?? 0));
export const day = (v?: string | null) => (v ? new Date(v).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }) : "—");
export const dateTime = (v?: string | null) => (v ? new Date(v).toLocaleString(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
export const words = (v?: string | null) => (v ? v.replace(/_/g, " ") : "—");
export const ago = (v: string) => {
  const s = Math.max(0, (Date.now() - new Date(v).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 604800) return `${Math.floor(s / 86400)} d ago`;
  return day(v);
};
/** Black or white, whichever reads better on a pharmacy's own colour. */
export const readableOn = (hex: string) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex ?? "");
  if (!m) return "#ffffff";
  const n = parseInt(m[1], 16);
  return 0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255) > 165 ? "#0b1324" : "#ffffff";
};
