import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";
const KEY = "nts.theme";
const listeners = new Set<() => void>();
const current = (): Theme => (document.documentElement.classList.contains("dark") ? "dark" : "light");

export function setTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try { localStorage.setItem(KEY, theme); } catch { /* storage blocked */ }
  listeners.forEach((l) => l());
}

export function useTheme() {
  const theme = useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l); }; }, current, () => "light" as Theme);
  return { theme, toggle: () => setTheme(theme === "dark" ? "light" : "dark"), setTheme };
}
