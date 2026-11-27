import { useParams } from "react-router-dom";
import { SystemNotFound } from "../../components/NotFound";
import { PublicLayout, usePageMeta, usePlatformInfo } from "../../components/PublicLayout";
import { PageView } from "../../components/site/blocks";
import { PageLoader } from "../../components/brand/Brand";
import { platformDefault, useGlobalContent, useSavedPage, type PageContent } from "../../lib/pages";
import { faqs, legalDocs } from "./content";

/** One builder-driven page: what the platform admin saved, or the starting content. */
function ContentPage({ pageKey, jsonLd }: { pageKey: string; jsonLd?: object }) {
  const saved = useSavedPage<PageContent>(pageKey);
  const contact = useGlobalContent();
  const info = usePlatformInfo();
  const content = saved.data?.content ?? platformDefault(pageKey);
  usePageMeta([content.hero.title, content.hero.highlight].filter(Boolean).join(" ").replace(/\*\*/g, ""), content.hero.subtitle.replace(/\*\*/g, "").slice(0, 160), jsonLd);
  if (saved.isLoading) return <PageLoader />;
  // Until the footer details are filled in, the contact block shows the platform's configured email and WhatsApp.
  const merged = { ...contact, email: contact.email || info.data?.contact_email || "", whatsapp: contact.whatsapp || info.data?.whatsapp_number || "" };
  return <PublicLayout><main><PageView content={content} info={{ name: "NTS Pharmacy System", contact: merged }} /></main></PublicLayout>;
}

export const Home = () => <ContentPage pageKey="home" jsonLd={{ "@context": "https://schema.org", "@type": "SoftwareApplication", name: "NTS Pharmacy System", applicationCategory: "BusinessApplication", operatingSystem: "Web" }} />;
export const Features = () => <ContentPage pageKey="features" />;
export const Solutions = () => <ContentPage pageKey="solutions" />;
export const Pricing = () => <ContentPage pageKey="pricing" />;
export const About = () => <ContentPage pageKey="about" />;
export const Faq = () => <ContentPage pageKey="faq" jsonLd={{ "@context": "https://schema.org", "@type": "FAQPage", mainEntity: faqs.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })) }} />;
export const Contact = ({ support = false }: { support?: boolean }) => <ContentPage key={support ? "support" : "contact"} pageKey={support ? "support" : "contact"} />;
export function Legal() {
  const { doc = "" } = useParams();
  return legalDocs[doc] ? <ContentPage key={doc} pageKey={`legal-${doc}`} /> : <SystemNotFound />;
}
