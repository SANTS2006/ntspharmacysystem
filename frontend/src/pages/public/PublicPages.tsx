import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BarChart3, Boxes, Building2, Check, ChevronDown, FileText, Globe, Mail, MessageCircle, Receipt, ShieldCheck, Smartphone, Users, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { PublicLayout, usePageMeta, usePlatformInfo } from "../../components/PublicLayout";
import { Reveal, Tilt } from "../../components/site/motion";
import { Scene3D } from "../../components/three/Scene3D";
import { Loading } from "../../components/ui";
import { api } from "../../lib/api";
import { faqs, legalDocs, solutions } from "./content";

const Hero = ({ title, desc }: { title: string; desc: string }) => (
  <header className="hero-surface relative overflow-hidden">
    <Scene3D className="absolute inset-y-0 right-0 hidden w-1/2 opacity-70 md:block" />
    <div className="site-wrap animate-rise relative py-14 md:py-20">
      <h1 className="max-w-2xl text-3xl font-extrabold tracking-tight md:text-5xl">{title}</h1>
      <p className="mt-3 max-w-xl text-lg text-white/80">{desc}</p>
    </div>
  </header>
);

const Page = ({ title, desc, children, jsonLd }: { title: string; desc: string; children: ReactNode; jsonLd?: object }) => {
  usePageMeta(title, desc, jsonLd);
  return <PublicLayout><main><Hero title={title} desc={desc} /><div className="site-wrap py-12">{children}</div></main></PublicLayout>;
};

const Heading = ({ eyebrow, title, text }: { eyebrow: string; title: string; text: string }) => (
  <Reveal className="mx-auto mb-10 max-w-2xl text-center"><p className="text-xs font-bold uppercase tracking-[0.2em] text-primary">{eyebrow}</p><h2 className="mt-2 text-2xl !font-extrabold tracking-tight md:text-4xl">{title}</h2><p className="mt-3 text-muted">{text}</p></Reveal>
);

const features: { icon: LucideIcon; title: string; text: string }[] = [
  { icon: Boxes, title: "Batch & expiry inventory", text: "First-expiry-first-out allocation, recalls, transfers and expiry alerts for every branch." },
  { icon: FileText, title: "Prescription workflow", text: "Pharmacist verification and safety checks before restricted dispensing." },
  { icon: Receipt, title: "Point of sale", text: "Fast selling with barcode scanning, shifts, receipts, returns and refunds." },
  { icon: Smartphone, title: "Mobile money", text: "Take payments at the till and online. A payment counts only when the provider confirms it." },
  { icon: Globe, title: "A website for each pharmacy", text: "Your own branded online shop, service bookings and customer accounts." },
  { icon: BarChart3, title: "Finance & analytics", text: "Double-entry accounting, live dashboards and exportable reports." },
  { icon: Building2, title: "Multi-branch operations", text: "Branch-level staff, stock and reports, with a view across the whole business." },
  { icon: Users, title: "People & payroll", text: "Attendance, leave, shifts, salaries and payslips." },
  { icon: ShieldCheck, title: "Security first", text: "Tenant isolation, role-based access and an audit trail." },
];

function FeatureGrid({ limit }: { limit?: number }) {
  return (
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {features.slice(0, limit).map(({ icon: Icon, title, text }, i) => (
        <Reveal key={title} delay={(i % 3) * 90} className="h-full">
          <Tilt className="card h-full p-6">
            <span className="tilt-pop mb-4 grid h-13 w-13 place-items-center rounded-2xl text-white shadow-lg" style={{ background: "linear-gradient(135deg, #047857, #0369a1)" }}><Icon aria-hidden size={23} /></span>
            <h3 className="section-title !text-lg">{title}</h3>
            <p className="mt-2 text-sm leading-6 text-muted">{text}</p>
          </Tilt>
        </Reveal>
      ))}
    </div>
  );
}

const STEPS = [["Register your pharmacy", "We create your secure space, your first branch and your administrator account."], ["Set up your catalogue", "Add medicines, receive stock by batch and invite your team with the right roles."], ["Sell in store and online", "Use the point of sale and share your pharmacy website with customers."], ["Grow with insight", "Follow revenue, stock and finances on live dashboards."]];

export function Home() {
  usePageMeta("Pharmacy Management Platform", "Multi-branch pharmacy software: inventory, prescriptions, point of sale, mobile money and finance, with a branded website for every pharmacy.", {
    "@context": "https://schema.org", "@type": "SoftwareApplication", name: "NTS Pharmacy System", applicationCategory: "BusinessApplication", operatingSystem: "Web",
    description: "Multi-tenant pharmacy management software with a branded website for every pharmacy.",
  });
  return (
    <PublicLayout>
      <main>
        <section className="hero-surface relative overflow-hidden">
          <Scene3D className="absolute inset-0 opacity-25 lg:left-[46%] lg:opacity-100" />
          <div className="site-wrap relative grid min-h-[36rem] items-center py-16 lg:min-h-[42rem]">
            <div className="animate-rise max-w-2xl">
              <p className="glass inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-bold text-emerald-300"><ShieldCheck size={14} aria-hidden />Secure multi-branch pharmacy platform</p>
              <h1 className="mt-5 text-4xl font-extrabold leading-[1.08] tracking-tight sm:text-5xl xl:text-6xl">The operating system for <span className="gradient-text">modern pharmacies</span></h1>
              <p className="mt-5 max-w-xl text-lg leading-8 text-white/80">Inventory, prescriptions, point of sale, finance and a branded website for every pharmacy on one secure platform.</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/contact" className="btn btn-primary !min-h-12 !px-7">Register your pharmacy<ArrowRight size={17} aria-hidden /></Link>
                <Link to="/features" className="btn glass !min-h-12 !px-7 text-white">Explore features</Link>
              </div>
              <ul className="mt-10 flex flex-wrap gap-x-6 gap-y-2 text-sm text-white/75">{["Your own pharmacy website", "Mobile money ready", "Works on phone and desktop"].map((t) => <li key={t} className="flex items-center gap-2"><Check size={16} aria-hidden className="text-emerald-300" />{t}</li>)}</ul>
            </div>
          </div>
        </section>
        <section className="site-wrap py-16 md:py-24">
          <Heading eyebrow="Platform" title="Everything your pharmacy runs on" text="From the dispensing counter to the accounts office, in one place." />
          <FeatureGrid limit={6} />
          <p className="mt-8 text-center"><Link to="/features" className="btn btn-outline">See all features<ArrowRight size={16} aria-hidden /></Link></p>
        </section>
        <section className="border-y border-line bg-white py-16 md:py-24">
          <div className="site-wrap">
            <Heading eyebrow="How it works" title="Up and running in four steps" text="A clear path from registration to daily operation." />
            <ol className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">{STEPS.map(([t, d], i) => <Reveal as="li" key={t} from={i % 2 ? "right" : "left"} delay={i * 80}><div className="card card-hover h-full p-6"><span className="text-4xl font-black text-primary opacity-60">{String(i + 1).padStart(2, "0")}</span><h3 className="mt-3 section-title">{t}</h3><p className="mt-2 text-sm text-muted">{d}</p></div></Reveal>)}</ol>
          </div>
        </section>
        <section className="site-wrap py-16 md:py-24">
          <Reveal from="zoom"><div className="hero-surface overflow-hidden rounded-3xl p-8 text-center md:p-14"><h2 className="text-2xl !font-extrabold md:text-4xl">Ready to modernise your pharmacy?</h2><p className="mx-auto mt-3 max-w-xl text-white/80">Talk to us and we will set up your pharmacy.</p><div className="mt-7 flex flex-wrap justify-center gap-3"><Link to="/contact" className="btn btn-primary !min-h-12 !px-7">Contact us</Link><Link to="/pricing" className="btn glass !min-h-12 !px-7 text-white">View pricing</Link></div></div></Reveal>
        </section>
      </main>
    </PublicLayout>
  );
}

export const Features = () => <Page title="Features" desc="Everything a pharmacy needs in one secure platform."><FeatureGrid /></Page>;

export const Solutions = () => (
  <Page title="Pharmacy management solutions" desc="Inventory, prescriptions, sales, multi-branch, finance and reporting for pharmacies.">
    <div className="grid gap-5 md:grid-cols-2">
      {solutions.map((s, i) => (
        <Reveal key={s.id} from={i % 2 ? "right" : "left"}><section id={s.id} className="card card-hover h-full p-7"><span className="text-sm font-black text-primary">{String(i + 1).padStart(2, "0")}</span><h2 className="mt-2 text-xl">{s.title}</h2><p className="mt-2 leading-7 text-muted">{s.text}</p></section></Reveal>
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
      {isError && <p role="alert" className="alert alert-error">Plans could not be loaded. Please try again later.</p>}
      {data?.length === 0 && <p className="empty">Pricing is being finalised. <Link to="/contact" className="font-bold text-primary underline">Contact us</Link> for a quote.</p>}
      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {data?.map((p, i) => (
          <Reveal key={p.code} delay={i * 90}><Tilt className="card h-full p-7">
            <h2 className="text-xl">{p.name}</h2>
            <p className="my-3 text-4xl font-extrabold">{p.currency} {Number(p.price).toLocaleString()}<span className="text-sm font-normal text-muted"> / {p.interval === "yearly" ? "year" : "month"}</span></p>
            <ul className="space-y-2 text-sm">
              {[`Up to ${p.max_branches} branch(es)`, `Up to ${p.max_users} users`, ...p.features].map((f) => <li key={f} className="flex gap-2"><Check aria-hidden size={17} className="shrink-0 text-primary" />{f}</li>)}
            </ul>
            <Link to="/contact" className="btn btn-primary mt-6 w-full">Choose {p.name}</Link>
          </Tilt></Reveal>
        ))}
      </div>
    </Page>
  );
}

export const About = () => (
  <Page title="About the platform" desc="NTS Pharmacy System helps pharmacies run safely and profitably.">
    <Reveal><p className="max-w-3xl text-lg leading-8">NTS Pharmacy System is a multi-tenant pharmacy management platform. Every pharmacy gets an isolated environment with its own branding, staff, inventory, records and customer website, so independent pharmacies and chains can run on the same secure foundation.</p></Reveal>
    <div className="mt-10"><FeatureGrid limit={3} /></div>
  </Page>
);

export const Faq = () => (
  <Page title="Frequently asked questions" desc="Answers about pharmacies, data separation, onboarding and payments."
    jsonLd={{ "@context": "https://schema.org", "@type": "FAQPage", mainEntity: faqs.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })) }}>
    <div className="mx-auto max-w-3xl space-y-3">{faqs.map(([q, a], i) => <Reveal key={q} delay={i * 60}><details className="card group p-5"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-bold">{q}<ChevronDown size={18} aria-hidden className="shrink-0 transition-transform group-open:rotate-180" /></summary><p className="mt-3 leading-7 text-muted">{a}</p></details></Reveal>)}</div>
  </Page>
);

export function Contact({ support = false }: { support?: boolean }) {
  const { data } = usePlatformInfo();
  const wa = data?.whatsapp_number?.replace(/\D/g, "");
  return (
    <Page title={support ? "Support" : "Contact"} desc="Get in touch with the NTS Pharmacy System team.">
      <div className="grid gap-5 md:grid-cols-2">
        {data?.contact_email && <Reveal from="left"><a className="card card-hover block p-7" href={`mailto:${data.contact_email}`}><Mail size={28} aria-hidden className="text-primary" /><h2 className="mt-3 text-lg">Email us</h2><p className="mt-1 break-all text-muted">{data.contact_email}</p></a></Reveal>}
        {wa && <Reveal from="right"><a className="card card-hover block p-7" href={`https://wa.me/${wa}`} target="_blank" rel="noopener noreferrer"><MessageCircle size={28} aria-hidden className="text-primary" /><h2 className="mt-3 text-lg">WhatsApp</h2><p className="mt-1 text-muted">Start a chat with our team</p></a></Reveal>}
        {data && !data.contact_email && !wa && <p className="empty">Contact details are being configured.</p>}
      </div>
      {support && <p className="alert alert-info mt-6">Pharmacy staff: please contact your pharmacy administrator first for account and password issues.</p>}
    </Page>
  );
}

export function Legal() {
  const { doc = "" } = useParams();
  const d = legalDocs[doc];
  if (!d) return <Page title="Not found" desc="Page not found."><p>This document does not exist.</p></Page>;
  return (
    <Page title={d.title} desc={`${d.title} for the NTS Pharmacy System platform.`}>
      <p className="alert alert-warning mb-6">Draft template pending legal review.</p>
      <article className="card mx-auto max-w-3xl space-y-6 p-7">{d.sections.map(([h, t]) => <section key={h}><h2 className="section-title !text-lg">{h}</h2><p className="mt-1 leading-7 text-muted">{t}</p></section>)}</article>
    </Page>
  );
}
