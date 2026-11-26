import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowRight, Boxes, Check, FileText, Receipt, ShieldCheck, Store } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { PublicLayout, usePageMeta, usePlatformInfo } from "../../components/PublicLayout";
import { api } from "../../lib/api";
import { faqs, legalDocs, solutions } from "./content";
import { Loading } from "../../components/ui";

const Page = ({ title, desc, children }: { title: string; desc: string; children: ReactNode }) => {
  usePageMeta(title, desc);
  return (
    <PublicLayout>
      <main>
        <header className="border-b border-line bg-white">
          <div className="mx-auto max-w-6xl px-5 py-12 sm:px-6">
            <h1 className="text-3xl font-bold tracking-tight md:text-4xl">{title}</h1>
            <p className="mt-2 max-w-2xl text-muted">{desc}</p>
          </div>
        </header>
        <div className="mx-auto max-w-6xl px-5 py-10 sm:px-6">{children}</div>
      </main>
    </PublicLayout>
  );
};

const features = [
  { icon: Boxes, title: "Batch & expiry inventory", text: "FEFO allocation, recalls and expiry alerts per branch." },
  { icon: FileText, title: "Prescription workflow", text: "Pharmacist verification before any restricted dispensing." },
  { icon: Store, title: "Multi-branch operations", text: "Each pharmacy gets its own site, staff and isolated data." },
  { icon: Receipt, title: "Sales and finance", text: "POS, receipts, double-entry accounting and reports." },
  { icon: ShieldCheck, title: "Security first", text: "Tenant isolation, audit trails and role-based access." },
];

function FeatureGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {features.map(({ icon: Icon, title, text }) => (
        <motion.article key={title} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="card p-6 transition-shadow hover:shadow-md">
          <span className="mb-4 grid h-11 w-11 place-items-center rounded-xl bg-teal-50 text-teal-700"><Icon aria-hidden size={21} /></span>
          <h2 className="section-title">{title}</h2>
          <p className="mt-1 text-sm leading-6 text-muted">{text}</p>
        </motion.article>
      ))}
    </div>
  );
}

export function Home() {
  usePageMeta("Pharmacy Management Platform", "Multi-branch pharmacy software: inventory, prescriptions, POS and finance, with a branded website for every pharmacy.");
  return (
    <PublicLayout>
      <main>
        <section className="relative overflow-hidden bg-navy text-white">
          <div aria-hidden className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full bg-primary/25 blur-3xl" />
          <div className="relative mx-auto grid max-w-6xl items-center gap-10 px-5 py-16 sm:px-6 md:py-24 lg:grid-cols-[1.2fr_.8fr]">
            <div>
              <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-semibold text-emerald-300"><ShieldCheck size={14} aria-hidden />Secure multi-branch pharmacy platform</p>
              <motion.h1 initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-4xl font-bold leading-[1.1] tracking-tight md:text-5xl xl:text-6xl">
                The operating system for modern pharmacies
              </motion.h1>
              <p className="mt-5 max-w-xl text-lg leading-8 text-slate-300">Inventory, prescriptions, point of sale, finance and a branded website for every pharmacy on one secure platform.</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/pricing" className="btn btn-primary !min-h-12 !px-6">See pricing<ArrowRight size={17} aria-hidden /></Link>
                <Link to="/contact" className="btn !min-h-12 !px-6 border-white/25 text-white hover:bg-white/10">Talk to us</Link>
              </div>
            </div>
            <ul className="space-y-3">
              {features.slice(0, 4).map(({ icon: Icon, title }) => <li key={title} className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-4 text-sm font-medium backdrop-blur"><span className="grid h-10 w-10 place-items-center rounded-lg bg-primary/25 text-emerald-300"><Icon size={19} aria-hidden /></span>{title}</li>)}
            </ul>
          </div>
        </section>
        <section className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <h2 className="text-2xl font-bold tracking-tight md:text-3xl">Everything your pharmacy runs on</h2>
          <p className="mb-8 mt-2 max-w-2xl text-muted">From the dispensing counter to the accounts office, in one place.</p>
          <FeatureGrid />
        </section>
      </main>
    </PublicLayout>
  );
}

export const Features = () => <Page title="Features" desc="Everything a pharmacy needs in one secure platform."><FeatureGrid /></Page>;

export const Solutions = () => (
  <Page title="Pharmacy management solutions" desc="Inventory, prescriptions, sales, multi-branch, finance and reporting for pharmacies.">
    <div className="space-y-6">
      {solutions.map((s) => (
        <section key={s.id} id={s.id} className="card p-6"><h2 className="text-xl font-semibold">{s.title}</h2><p className="mt-2 text-slate-600">{s.text}</p></section>
      ))}
    </div>
  </Page>
);

interface PlanRow { code: string; name: string; price: string; currency: string; interval: string; max_branches: number; max_users: number; features: string[] }
export function Pricing() {
  const { data, isLoading, isError } = useQuery({ queryKey: ["plans"], queryFn: () => api<PlanRow[]>("/public/plans/") });
  return (
    <Page title="Pricing" desc="Simple subscription plans for independent pharmacies and chains.">
      {isLoading && <Loading rows={3} />}
      {isError && <p role="alert">Plans could not be loaded. Please try again later.</p>}
      {data?.length === 0 && <p>Pricing is being finalised. <Link to="/contact" className="underline">Contact us</Link> for a quote.</p>}
      <div className="grid gap-4 md:grid-cols-3">
        {data?.map((p) => (
          <article key={p.code} className="card p-6">
            <h2 className="text-xl font-semibold">{p.name}</h2>
            <p className="my-2 text-3xl font-bold">{p.currency} {Number(p.price).toLocaleString()}<span className="text-sm font-normal text-slate-500"> / {p.interval === "yearly" ? "year" : "month"}</span></p>
            <ul className="space-y-1 text-sm">
              <li className="flex gap-2"><Check aria-hidden size={16} /> Up to {p.max_branches} branch(es)</li>
              <li className="flex gap-2"><Check aria-hidden size={16} /> Up to {p.max_users} users</li>
              {p.features.map((f) => <li key={f} className="flex gap-2"><Check aria-hidden size={16} /> {f}</li>)}
            </ul>
          </article>
        ))}
      </div>
    </Page>
  );
}

export const About = () => (
  <Page title="About the platform" desc="NTS Pharmacy System helps pharmacies run safely and profitably.">
    <p className="max-w-3xl text-slate-600">NTS Pharmacy System is a multi-tenant pharmacy management platform. Every pharmacy gets an isolated environment with its own branding, staff, inventory, records and customer website, so independent pharmacies and chains can run on the same secure foundation.</p>
  </Page>
);

export const Faq = () => (
  <Page title="Frequently asked questions" desc="Answers about pharmacies, data separation, onboarding and payments.">
    <div className="space-y-3">{faqs.map(([q, a]) => <details key={q} className="card p-4"><summary className="cursor-pointer font-medium">{q}</summary><p className="mt-2 text-slate-600">{a}</p></details>)}</div>
  </Page>
);

export function Contact({ support = false }: { support?: boolean }) {
  const { data } = usePlatformInfo();
  const wa = data?.whatsapp_number?.replace(/\D/g, "");
  return (
    <Page title={support ? "Support" : "Contact"} desc="Get in touch with the NTS Pharmacy System team.">
      <div className="space-y-3 text-slate-700">
        {data?.contact_email && <p>Email: <a className="underline" href={`mailto:${data.contact_email}`}>{data.contact_email}</a></p>}
        {wa && <p>WhatsApp: <a className="underline" href={`https://wa.me/${wa}`} target="_blank" rel="noopener noreferrer">Start a chat</a></p>}
        {!data?.contact_email && !wa && <p>Contact details are being configured.</p>}
        {support && <p>Pharmacy staff: please contact your pharmacy administrator first for account and password issues.</p>}
      </div>
    </Page>
  );
}

export function Legal() {
  const { doc = "" } = useParams();
  const d = legalDocs[doc];
  if (!d) return <Page title="Not found" desc="Page not found."><p>This document does not exist.</p></Page>;
  return (
    <Page title={d.title} desc={`${d.title} for the NTS Pharmacy System platform.`}>
      <p className="mb-6 rounded bg-amber-50 p-3 text-sm text-amber-900">Draft template pending legal review.</p>
      {d.sections.map(([h, t]) => <section key={h} className="mb-5"><h2 className="section-title">{h}</h2><p className="text-slate-600">{t}</p></section>)}
    </Page>
  );
}
