/** Website motion: reveal-on-scroll, 3D tilt cards, a scroll progress bar, the slide-in mobile menu and page SEO. */
import { Menu, X } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties, type ElementType, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";

export function Reveal({ children, from = "up", delay = 0, className = "", as: Tag = "div" }: { children: ReactNode; from?: "up" | "left" | "right" | "zoom"; delay?: number; className?: string; as?: ElementType }) {
  const ref = useRef<HTMLElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") { setShown(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setShown(true); io.disconnect(); } }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  const dir = from === "up" ? "" : `reveal-${from}`;
  return <Tag ref={ref} className={`reveal ${dir} ${shown ? "is-visible" : ""} ${className}`} style={{ transitionDelay: `${delay}ms` } as CSSProperties}>{children}</Tag>;
}

/** Tilts toward the pointer. Touch devices and reduced-motion users get a flat card. */
export function Tilt({ children, className = "", max = 7 }: { children: ReactNode; className?: string; max?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const move = (e: React.PointerEvent) => {
    const el = ref.current;
    if (!el || e.pointerType !== "mouse" || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const r = el.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(900px) rotateX(${-y * max}deg) rotateY(${x * max}deg) translateY(-4px)`;
  };
  return <div ref={ref} onPointerMove={move} onPointerLeave={() => { if (ref.current) ref.current.style.transform = ""; }} className={`tilt ${className}`}>{children}</div>;
}

export function ScrollProgress() {
  const ref = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();
  useEffect(() => {
    const update = () => { const max = document.documentElement.scrollHeight - window.innerHeight; if (ref.current) ref.current.style.transform = `scaleX(${max > 0 ? Math.min(1, window.scrollY / max) : 0})`; };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => { window.removeEventListener("scroll", update); window.removeEventListener("resize", update); };
  }, [pathname]);
  return <div ref={ref} className="scroll-progress" aria-hidden />;
}

/** Slide-in menu for small screens; links arrive one after another. */
export function MobileMenu({ title, children }: { title: ReactNode; children: ReactNode[] }) {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", key);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", key); document.body.style.overflow = ""; };
  }, [open]);
  return (
    <>
      <button type="button" className="icon-btn !text-current lg:hidden" aria-expanded={open} aria-label="Open menu" onClick={() => setOpen(true)}><Menu size={22} /></button>
      {createPortal(
        <div className={`fixed inset-0 z-[70] overflow-hidden lg:hidden ${open ? "" : "pointer-events-none"}`}>
          <div className={`backdrop absolute inset-0 transition-opacity duration-300 ${open ? "opacity-100" : "opacity-0"}`} onClick={() => setOpen(false)} />
          <div role="dialog" aria-modal="true" aria-label="Menu" className={`drawer absolute inset-y-0 right-0 flex w-[min(20rem,86vw)] flex-col bg-white text-ink shadow-pop ${open ? "drawer-open" : ""}`}>
            <div className="flex items-center justify-between gap-3 border-b border-line p-4"><div className="min-w-0 font-bold">{title}</div><button type="button" aria-label="Close menu" className="icon-btn" onClick={() => setOpen(false)}><X size={20} /></button></div>
            <nav aria-label="Menu" className="flex flex-1 flex-col gap-1.5 overflow-y-auto p-4" onClick={(e) => { if ((e.target as HTMLElement).closest("a,button")) setOpen(false); }}>
              {children.filter(Boolean).map((c, i) => <div key={i} className="drawer-item" style={{ transitionDelay: open ? `${90 + i * 55}ms` : "0ms" }}>{c}</div>)}
            </nav>
          </div>
        </div>, document.body)}
    </>
  );
}

/** Per-page title, description, canonical address, social tags and structured data. */
export function useSeo(title: string, description: string, { image, jsonLd, noindex }: { image?: string | null; jsonLd?: object; noindex?: boolean } = {}) {
  const data = jsonLd ? JSON.stringify(jsonLd) : "";
  useEffect(() => {
    document.title = title;
    const meta = (key: "name" | "property", id: string, content: string) => {
      let m = document.head.querySelector<HTMLMetaElement>(`meta[${key}="${id}"]`);
      if (!m) { m = document.createElement("meta"); m.setAttribute(key, id); document.head.appendChild(m); }
      m.content = content;
    };
    const url = location.origin + location.pathname.replace(/(.)\/$/, "$1");
    const picture = new URL(image || "/logo.webp", location.origin).href;
    meta("name", "description", description);
    meta("name", "robots", noindex ? "noindex,nofollow" : "index,follow");
    meta("property", "og:title", title); meta("property", "og:description", description); meta("property", "og:url", url); meta("property", "og:image", picture); meta("property", "og:type", "website");
    meta("name", "twitter:card", "summary"); meta("name", "twitter:title", title); meta("name", "twitter:description", description);
    let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!canonical) { canonical = document.createElement("link"); canonical.rel = "canonical"; document.head.appendChild(canonical); }
    canonical.href = url;
    let script: HTMLScriptElement | null = null;
    if (data) { script = document.createElement("script"); script.type = "application/ld+json"; script.textContent = data; document.head.appendChild(script); }
    return () => { script?.remove(); };
  }, [title, description, image, data, noindex]);
}
