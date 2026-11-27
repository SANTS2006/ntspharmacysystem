/** Website content: the shapes the builder edits, and the starting content shown until someone saves a page. */
import { useQuery } from "@tanstack/react-query";
import { faqs, legalDocs, solutions } from "../pages/public/content";
import { api } from "./api";
import type { Site } from "./site";

export type Model = "none" | "pharmacy" | "capsules" | "molecule" | "dna" | "cross";
export type BlockType = "text" | "items" | "split" | "gallery" | "stats" | "cta" | "branches" | "products" | "services" | "plans" | "contact" | "map";
export interface Btn { label: string; href: string }
export interface Item { title: string; text: string; image: string; href: string }
export interface Block { type: BlockType; title: string; subtitle: string; body: string; image: string; imageSide: "left" | "right"; layout: "cards" | "accordion" | "carousel" | "steps" | "list"; animation: "none" | "up" | "left" | "right" | "zoom"; background: "plain" | "tinted" | "brand"; model: Model; button: Btn; items: Item[] }
export interface Hero { eyebrow: string; title: string; highlight: string; subtitle: string; image: string; model: Model; primary: Btn; secondary: Btn }
export interface PageContent { hero: Hero; blocks: Block[] }
export interface GlobalContent { footerAbout: string; email: string; phone: string; whatsapp: string; address: string; hours: string; latitude: string; longitude: string; social: { title: string; href: string }[] }

const none: Btn = { label: "", href: "" };
export const item = (title = "", text = "", image = "", href = ""): Item => ({ title, text, image, href });
export const block = (type: BlockType, over: Partial<Block> = {}): Block => ({ type, title: "", subtitle: "", body: "", image: "", imageSide: "right", layout: "cards", animation: "up", background: "plain", model: "none", button: { ...none }, items: [], ...over });
const hero = (title: string, subtitle: string, over: Partial<Hero> = {}): Hero => ({ eyebrow: "", title, highlight: "", subtitle, image: "", model: "pharmacy", primary: { ...none }, secondary: { ...none }, ...over });
const page = (h: Hero, ...blocks: Block[]): PageContent => ({ hero: h, blocks });
export const EMPTY_GLOBAL: GlobalContent = { footerAbout: "", email: "", phone: "", whatsapp: "", address: "", hours: "", latitude: "", longitude: "", social: [] };

export const PLATFORM_PAGES: [string, string, string][] = [
  ["home", "Home", "/"], ["features", "Features", "/features"], ["solutions", "Solutions", "/solutions"], ["pricing", "Pricing", "/pricing"], ["about", "About", "/about"],
  ["faq", "FAQ", "/faq"], ["contact", "Contact", "/contact"], ["support", "Support", "/support"], ["legal-privacy", "Privacy policy", "/legal/privacy"], ["legal-terms", "Terms", "/legal/terms"],
  ["legal-payment-refund", "Payments & refunds", "/legal/payment-refund"], ["legal-data-protection", "Data protection", "/legal/data-protection"], ["legal-security", "Security", "/legal/security"], ["legal-cookies", "Cookies", "/legal/cookies"],
];
export const PHARMACY_PAGES: [string, string, string][] = [["home", "Home", ""], ["about", "About us", "/about"], ["products", "Products", "/products"], ["services", "Services", "/services"], ["institutional", "Bulk & institutions", "/institutional"], ["contact", "Contact us", "/contact"]];

const FEATURES = [
  item("Batch & expiry inventory", "First-expiry-first-out allocation, recalls, transfers and expiry alerts for every branch."), item("Prescription workflow", "Pharmacist verification and safety checks before restricted dispensing."),
  item("Point of sale", "Fast selling with barcode scanning, shifts, receipts, returns and refunds."), item("Mobile money", "Take payments at the till and online. A payment counts only when the provider confirms it."),
  item("A website for each pharmacy", "Your own branded online shop, service bookings and customer accounts."), item("Finance & analytics", "Double-entry accounting, live dashboards and exportable reports."),
  item("Multi-branch operations", "Branch-level staff, stock and reports, with a view across the whole business."), item("People & payroll", "Attendance, leave, shifts, salaries and payslips."), item("Security first", "Tenant isolation, role-based access and an audit trail."),
];
const cta = () => block("cta", { title: "Ready to modernise your pharmacy?", subtitle: "Talk to us and we will set up your pharmacy.", button: { label: "Contact us", href: "/contact" }, animation: "zoom" });

export function platformDefault(key: string): PageContent {
  if (key.startsWith("legal-")) {
    const doc = legalDocs[key.slice(6)];
    return page(hero(doc?.title ?? "Policy", `${doc?.title ?? "Policy"} for the NTS Pharmacy System platform.`, { model: "molecule" }),
      block("text", { body: "Draft template pending legal review.", background: "tinted" }), ...(doc?.sections ?? []).map(([title, body]) => block("text", { title, body })));
  }
  const all: Record<string, PageContent> = {
    home: page(hero("The operating system for", "Inventory, prescriptions, point of sale, finance and a branded website for every pharmacy on one secure platform.", { eyebrow: "Secure multi-branch pharmacy platform", highlight: "modern pharmacies", primary: { label: "Register your pharmacy", href: "/contact" }, secondary: { label: "Explore features", href: "/features" } }),
      block("items", { title: "Everything your pharmacy runs on", subtitle: "From the dispensing counter to the accounts office, in one place.", items: FEATURES.slice(0, 6), button: { label: "See all features", href: "/features" } }),
      block("items", { title: "Up and running in four steps", layout: "steps", background: "tinted", animation: "left", items: [item("Register your pharmacy", "We create your secure space, your first branch and your administrator account."), item("Set up your catalogue", "Add medicines, receive stock by batch and invite your team with the right roles."), item("Sell in store and online", "Use the point of sale and share your pharmacy website with customers."), item("Grow with insight", "Follow revenue, stock and finances on live dashboards.")] }), cta()),
    features: page(hero("Features", "Everything a pharmacy needs in one secure platform.", { model: "capsules" }), block("items", { items: FEATURES }), cta()),
    solutions: page(hero("Pharmacy management solutions", "Inventory, prescriptions, sales, multi-branch, finance and reporting for pharmacies.", { model: "dna" }), block("items", { items: solutions.map((s) => item(s.title, s.text)), animation: "left" })),
    pricing: page(hero("Pricing", "Simple subscription plans for independent pharmacies and chains.", { model: "cross" }), block("plans"), cta()),
    about: page(hero("About the platform", "NTS Pharmacy System helps pharmacies run safely and profitably.", { model: "molecule" }), block("split", { title: "Built for pharmacies", body: "NTS Pharmacy System is a **multi-tenant pharmacy management platform**. Every pharmacy gets an isolated environment with its own branding, staff, inventory, records and customer website, so independent pharmacies and chains can run on the same secure foundation.", model: "capsules" }), block("items", { items: FEATURES.slice(0, 3) })),
    faq: page(hero("Frequently asked questions", "Answers about pharmacies, data separation, onboarding and payments.", { model: "molecule" }), block("items", { layout: "accordion", items: faqs.map(([q, a]) => item(q, a)) }), cta()),
    contact: page(hero("Contact us", "Get in touch with the NTS Pharmacy System team.", { model: "capsules" }), block("contact", { title: "Send us a message" })),
    support: page(hero("Support", "Get help with your pharmacy account.", { model: "cross" }), block("text", { body: "Pharmacy staff: please contact your pharmacy administrator first for account and password issues.", background: "tinted" }), block("contact", { title: "Ask for help" })),
  };
  return all[key] ?? all.home;
}

export function pharmacyDefault(key: string, s: Site): PageContent {
  const about = s.description || `${s.name} is your trusted local pharmacy: medicines, advice and services, online and in store.`;
  const base = `/${s.slug}`;
  const all: Record<string, PageContent> = {
    home: page(hero(s.name, about, { eyebrow: [s.city, s.country].filter(Boolean).join(", "), primary: { label: "Shop medicines", href: `${base}/products` }, secondary: { label: "Our services", href: `${base}/services` } }),
      block("items", { items: [item("Order online", "Browse our catalogue and order in a few taps."), item("Pharmacist checked", "Prescription medicines are reviewed before they are supplied."), item(s.online_payments ? "Mobile money" : "Easy payment", s.online_payments ? "Pay securely online with mobile money." : "Pay when you collect or on delivery."), item("Pickup or delivery", "Collect from a branch or have it brought to you.")] }),
      block("products", { title: "Popular products", subtitle: "A selection from our shelves." }), block("services", { title: "Services we offer", background: "tinted" }), block("branches", { title: "Visit our branches", subtitle: "Find us on the map and get directions." })),
    about: page(hero(`About ${s.name}`, "Who we are and how we care for our customers.", { model: "molecule" }), block("split", { title: "Our pharmacy", body: about, model: "capsules" }), block("branches", { title: "Where to find us" })),
    products: page(hero("Products", "Search our catalogue and add medicines to your cart.", { model: "capsules" })),
    services: page(hero("Our services", "Advice and care from our pharmacy team.", { model: "cross" }), block("services")),
    institutional: page(hero("Bulk and institutional orders", "For hospitals, companies, schools and event organisers.", { model: "dna" })),
    contact: page(hero("Contact us", `Send ${s.name} a message or visit one of our branches.`, { model: "capsules" }), block("contact", { title: "Send us a message" }), block("branches", { title: "Our branches" })),
  };
  return all[key] ?? all.home;
}

const publicPath = (key: string, slug?: string) => (slug ? `/public/pharmacies/${slug}/pages/${key}/` : `/public/site-pages/${key}/`);
export const useSavedPage = <T,>(key: string, slug?: string) => useQuery({ queryKey: ["site-page", slug ?? "platform", key], queryFn: () => api<{ content: T | null }>(publicPath(key, slug)), staleTime: 60_000, retry: false });
/** Footer and contact details for one website. */
export function useGlobalContent(slug?: string): GlobalContent {
  const q = useSavedPage<GlobalContent>("global", slug);
  return { ...EMPTY_GLOBAL, ...(q.data?.content ?? {}) };
}

/** Footer / contact-block details: what was entered in Website content, else the pharmacy's own profile. */
export const contactOf = (s: Site, g: GlobalContent): GlobalContent => ({ ...g, email: g.email || s.contact_email, phone: g.phone || s.contact_phone, address: g.address || [s.address, s.city, s.country].filter(Boolean).join(", ") });
