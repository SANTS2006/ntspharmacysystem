import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Boxes, Check, FileText, Receipt, ShieldCheck, Store } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { PublicLayout, usePageMeta, usePlatformInfo } from "../../components/PublicLayout";
import { api } from "../../lib/api";
import { faqs, legalDocs, solutions } from "./content";

const Page = ({ title, desc, children }: { title: string; desc: string; children: ReactNode }) => {
  usePageMeta(title, desc);
  return (
    <PublicLayout>
      <main className="mx-auto max-w-5xl px-6 py-14">
        <h1 className="mb-6 text-3xl font-bold md:text-4xl">{title}</h1>
        {children}
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
        <motion.article key={title} initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="rounded-2xl border p-6">
          <Icon aria-hidden className="mb-2 text-teal-700" />
          <h2 className="font-semibold">{title}</h2>
          <p className="text-sm text-slate-600">{text}</p>
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
        <section className="mx-auto max-w-5xl px-6 py-20 text-center">
          <motion.h1 initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-4xl font-bold md:text-6xl">
            The operating system for modern pharmacies
          </motion.h1>
          <p className="mx-auto mt-4 max-w-2xl text-slate-600">Inventory, prescriptions, POS, finance and a branded website for every pharmacy on one secure platform.</p>
          <div className="mt-8 flex justify-center gap-3">
            <Link to="/pricing" className="rounded bg-teal-700 px-5 py-2 font-medium text-white">See pricing</Link>
            <Link to="/contact" className="rounded border px-5 py-2 font-medium">Talk to us</Link>
          </div>
        </section>
        <section className="mx-auto max-w-5xl px-6 pb-20"><FeatureGrid /></section>
      </main>
    </PublicLayout>
  );
}

export const Features = () => <Page title="Features" desc="Everything a pharmacy needs in one secure platform."><FeatureGrid /></Page>;

export const Solutions = () => (
  <Page title="Pharmacy management solutions" desc="Inventory, prescriptions, sales, multi-branch, finance and reporting for pharmacies.">
    <div className="space-y-6">
      {solutions.map((s) => (
        <section key={s.id} id={s.id} className="rounded-2xl border p-6"><h2 className="text-xl font-semibold">{s.title}</h2><p className="mt-2 text-slate-600">{s.text}</p></section>
      ))}
    </div>
  </Page>
);

interface PlanRow { code: string; name: string; price: string; currency: string; interval: string; max_branches: number; max_users: number; features: string[] }
export function Pricing() {
  const { data, isLoading, isError } = useQuery({ queryKey: ["plans"], queryFn: () => api<PlanRow[]>("/public/plans/") });
  return (
    <Page title="Pricing" desc="Simple subscription plans for independent pharmacies and chains.">
      {isLoading && <p>Loading plans…</p>}
      {isError && <p role="alert">Plans could not be loaded. Please try again later.</p>}
      {data?.length === 0 && <p>Pricing is being finalised. <Link to="/contact" className="underline">Contact us</Link> for a quote.</p>}
      <div className="grid gap-4 md:grid-cols-3">
        {data?.map((p) => (
          <article key={p.code} className="rounded-2xl border p-6">
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
  <Page title="About the platform" desc="PharmaCloud helps pharmacies run safely and profitably.">
    <p className="max-w-3xl text-slate-600">PharmaCloud is a multi-tenant pharmacy management platform. Every pharmacy gets an isolated environment with its own branding, staff, inventory, records and customer website, so independent pharmacies and chains can run on the same secure foundation.</p>
  </Page>
);

export const Faq = () => (
  <Page title="Frequently asked questions" desc="Answers about pharmacies, data separation, onboarding and payments.">
    <div className="space-y-3">{faqs.map(([q, a]) => <details key={q} className="rounded-xl border p-4"><summary className="cursor-pointer font-medium">{q}</summary><p className="mt-2 text-slate-600">{a}</p></details>)}</div>
  </Page>
);

export function Contact({ support = false }: { support?: boolean }) {
  const { data } = usePlatformInfo();
  const wa = data?.whatsapp_number?.replace(/\D/g, "");
  return (
    <Page title={support ? "Support" : "Contact"} desc="Get in touch with the PharmaCloud team.">
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
    <Page title={d.title} desc={`${d.title} for the PharmaCloud platform.`}>
      <p className="mb-6 rounded bg-amber-50 p-3 text-sm text-amber-900">Draft template pending legal review.</p>
      {d.sections.map(([h, t]) => <section key={h} className="mb-5"><h2 className="font-semibold">{h}</h2><p className="text-slate-600">{t}</p></section>)}
    </Page>
  );
}
