import { useEffect, useState } from "react";

export interface CartItem { id: number; name: string; price: string; quantity: number; requires_prescription: boolean }
const k = (slug: string) => `cart:${slug}`;
const read = (slug: string): CartItem[] => { try { return JSON.parse(localStorage.getItem(k(slug)) ?? "[]"); } catch { return []; } };

/** Cart lives in the browser only; prices shown here are informational, the server prices every order. */
export function useCart(slug: string) {
  const [items, setItems] = useState<CartItem[]>(() => read(slug));
  useEffect(() => { try { localStorage.setItem(k(slug), JSON.stringify(items)); } catch { /* storage blocked */ } }, [slug, items]);
  return {
    items,
    add: (i: Omit<CartItem, "quantity">) => setItems((c) => c.some((x) => x.id === i.id) ? c.map((x) => x.id === i.id ? { ...x, quantity: Math.min(100, x.quantity + 1) } : x) : [...c, { ...i, quantity: 1 }]),
    setQty: (id: number, q: number) => setItems((c) => c.map((x) => x.id === id ? { ...x, quantity: Math.max(1, Math.min(100, q)) } : x)),
    remove: (id: number) => setItems((c) => c.filter((x) => x.id !== id)),
    clear: () => setItems([]),
  };
}
