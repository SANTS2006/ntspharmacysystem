import { useSyncExternalStore } from "react";

export interface CartItem { id: number; name: string; price: string; quantity: number; requires_prescription: boolean }

/** Cart lives in the browser only; prices shown here are informational, the server prices every order.
 *  One shared store per pharmacy, so the header badge, product pages and checkout always agree. */
const cache = new Map<string, CartItem[]>();
const listeners = new Set<() => void>();
const k = (slug: string) => `cart:${slug}`;
const read = (slug: string): CartItem[] => {
  let items = cache.get(slug);
  if (!items) {
    try { items = JSON.parse(localStorage.getItem(k(slug)) ?? "[]") as CartItem[]; } catch { items = []; }
    cache.set(slug, items);
  }
  return items;
};
const write = (slug: string, next: CartItem[]) => {
  cache.set(slug, next);
  try { localStorage.setItem(k(slug), JSON.stringify(next)); } catch { /* storage blocked */ }
  listeners.forEach((l) => l());
};
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };

export function useCart(slug: string) {
  const items = useSyncExternalStore(subscribe, () => read(slug));
  return {
    items,
    count: items.reduce((t, i) => t + i.quantity, 0),
    add: (i: Omit<CartItem, "quantity">) => {
      const c = read(slug);
      write(slug, c.some((x) => x.id === i.id) ? c.map((x) => x.id === i.id ? { ...x, quantity: Math.min(100, x.quantity + 1) } : x) : [...c, { ...i, quantity: 1 }]);
    },
    setQty: (id: number, q: number) => write(slug, read(slug).map((x) => x.id === id ? { ...x, quantity: Math.max(1, Math.min(100, q || 1)) } : x)),
    remove: (id: number) => write(slug, read(slug).filter((x) => x.id !== id)),
    clear: () => write(slug, []),
  };
}
