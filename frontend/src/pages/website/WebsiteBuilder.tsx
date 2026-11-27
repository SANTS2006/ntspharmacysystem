/** Website builder, used by the platform admin for the main website and by a pharmacy for its own. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Bold, ChevronDown, ExternalLink, Eye, ImageUp, Plus, RotateCcw, Save, Trash2, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { MapCard, PageView, type SiteInfo } from "../../components/site/blocks";
import { Loading, Modal, PageHeader, Spinner, errorMessage, placeholderFor, useConfirm, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { EMPTY_GLOBAL, PHARMACY_PAGES, PLATFORM_PAGES, block, contactOf, item, pharmacyDefault, platformDefault, type Block, type BlockType, type Btn, type GlobalContent, type Hero, type Item, type PageContent } from "../../lib/pages";
import { useSiteQuery, type Site } from "../../lib/site";

const MODELS: [string, string][] = [["none", "No 3D model"], ["pharmacy", "Pharmacy cross and medicines"], ["capsules", "Floating capsules"], ["molecule", "Molecules"], ["dna", "DNA helix"], ["cross", "Large medical cross"]];
const LAYOUTS: [string, string][] = [["cards", "Cards"], ["accordion", "Accordion"], ["carousel", "Carousel"], ["steps", "Numbered steps"], ["list", "List"]];
const ANIMATIONS: [string, string][] = [["none", "No animation"], ["up", "Slide up"], ["left", "Slide from the left"], ["right", "Slide from the right"], ["zoom", "Zoom in"]];
const BACKGROUNDS: [string, string][] = [["plain", "Plain"], ["tinted", "White panel"], ["brand", "Brand tint"]];
const TYPES: [BlockType, string, ("platform" | "pharmacy")?][] = [["text", "Text"], ["items", "Cards, accordion or carousel"], ["split", "Text beside a picture or 3D model"], ["gallery", "Picture gallery"], ["stats", "Key figures"], ["cta", "Call-to-action banner"], ["contact", "Contact form and details"], ["map", "Map of the main address"], ["branches", "Branches with maps", "pharmacy"], ["products", "Popular products", "pharmacy"], ["services", "Services list", "pharmacy"], ["plans", "Subscription plans", "platform"]];
const typeName = (t: BlockType) => TYPES.find(([k]) => k === t)?.[1] ?? t;

/** A text box with a Bold button: select words, press Bold, and they appear in bold on the website. */
function RichInput({ label, value, onChange, multiline, bold = true, max = 400 }: { label: string; value: string; onChange: (v: string) => void; multiline?: boolean; bold?: boolean; max?: number }) {
  const id = useId(); const ref = useRef<HTMLInputElement & HTMLTextAreaElement>(null);
  const wrap = () => {
    const el = ref.current; if (!el) return;
    const [a, b] = [el.selectionStart ?? 0, el.selectionEnd ?? 0];
    const picked = value.slice(a, b) || "bold text";
    onChange(`${value.slice(0, a)}**${picked}**${value.slice(b)}`);
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(a + 2, a + 2 + picked.length); });
  };
  const props = { id, ref, value, maxLength: max, placeholder: placeholderFor(label), className: "mt-1.5 w-full", onChange: (e: { target: { value: string } }) => onChange(e.target.value) };
  return (
    <div>
      <div className="flex items-center justify-between gap-2"><label htmlFor={id} className="field-label">{label}</label>{bold && <button type="button" className="btn btn-outline btn-sm !min-h-7 !px-2" onClick={wrap} title="Make the selected text bold" aria-label={`Bold the selected text in ${label}`}><Bold size={13} aria-hidden />Bold</button>}</div>
      {multiline ? <textarea {...props} rows={5} /> : <input {...props} />}
    </div>
  );
}

function Select({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return <label className="field-label">{label}<select className="mt-1.5 w-full" value={value} onChange={(e) => onChange(e.target.value)}>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>;
}

function ImageInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const toast = useToast(); const file = useRef<HTMLInputElement>(null); const [busy, setBusy] = useState(false);
  const upload = async (f?: File) => {
    if (!f) return; setBusy(true);
    try { const fd = new FormData(); fd.append("image", f); onChange((await api<{ url: string }>("/website/images/", { method: "POST", body: fd })).url); }
    catch (e) { toast(errorMessage(e), "error"); }
    setBusy(false); if (file.current) file.current.value = "";
  };
  return (
    <div>
      <span className="field-label">{label}</span>
      <div className="mt-1.5 flex items-center gap-2.5">
        {value && <img src={value} alt="" className="h-14 w-20 rounded-lg border border-line object-cover" />}
        <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" aria-label={label} onChange={(e) => upload(e.target.files?.[0])} />
        <button type="button" className="btn btn-outline btn-sm" disabled={busy} onClick={() => file.current?.click()}>{busy ? <Spinner /> : <ImageUp size={14} aria-hidden />}{value ? "Change picture" : "Upload picture"}</button>
        {value && <button type="button" className="icon-btn" aria-label={`Remove ${label}`} onClick={() => onChange("")}><X size={15} aria-hidden /></button>}
      </div>
    </div>
  );
}

const LINK_LABEL = "Link (a /page, https://, mailto: or tel:)";
function ButtonInput({ label, value, onChange }: { label: string; value: Btn; onChange: (v: Btn) => void }) {
  return <div className="grid gap-3 sm:grid-cols-2"><RichInput bold={false} max={60} label={`${label} text`} value={value.label} onChange={(v) => onChange({ ...value, label: v })} /><RichInput bold={false} label={`${label} ${LINK_LABEL.toLowerCase()}`} value={value.href} onChange={(v) => onChange({ ...value, href: v })} /></div>;
}

const move = <T,>(list: T[], i: number, by: number) => { const next = [...list]; const j = i + by; if (j < 0 || j >= next.length) return list; [next[i], next[j]] = [next[j], next[i]]; return next; };

function RowTools({ name, i, count, onMove, onRemove }: { name: string; i: number; count: number; onMove: (by: number) => void; onRemove: () => void }) {
  return <span className="flex shrink-0 gap-1"><button type="button" className="icon-btn" aria-label={`Move ${name} up`} disabled={i === 0} onClick={() => onMove(-1)}><ArrowUp size={15} /></button><button type="button" className="icon-btn" aria-label={`Move ${name} down`} disabled={i === count - 1} onClick={() => onMove(1)}><ArrowDown size={15} /></button><button type="button" className="icon-btn !text-danger" aria-label={`Delete ${name}`} onClick={onRemove}><Trash2 size={15} /></button></span>;
}

function BlockEditor({ b, change }: { b: Block; change: (b: Block) => void }) {
  const confirm = useConfirm();
  const set = <K extends keyof Block>(k: K, v: Block[K]) => change({ ...b, [k]: v });
  const setItem = (n: number, over: Partial<Item>) => set("items", b.items.map((x, i) => (i === n ? { ...x, ...over } : x)));
  const hasItems = ["items", "gallery", "stats"].includes(b.type);
  return (
    <div className="space-y-4 border-t border-line pt-4">
      <RichInput label="Section heading" value={b.title} onChange={(v) => set("title", v)} />
      {b.type !== "split" && <RichInput label="Section subheading" value={b.subtitle} onChange={(v) => set("subtitle", v)} />}
      {["text", "split", "cta", "items", "contact"].includes(b.type) && <RichInput multiline max={5000} label="Section text" value={b.body} onChange={(v) => set("body", v)} />}
      {["split", "cta"].includes(b.type) && <ImageInput label={b.type === "cta" ? "Background picture" : "Picture"} value={b.image} onChange={(v) => set("image", v)} />}
      <div className="grid gap-3 sm:grid-cols-2">
        {b.type === "items" && <Select label="Display as" value={b.layout} options={LAYOUTS} onChange={(v) => set("layout", v as Block["layout"])} />}
        {b.type === "split" && <><Select label="Picture position" value={b.imageSide} options={[["right", "Right"], ["left", "Left"]]} onChange={(v) => set("imageSide", v as "left" | "right")} /><Select label="3D model (used when there is no picture)" value={b.model} options={MODELS} onChange={(v) => set("model", v as Block["model"])} /></>}
        <Select label="Scroll animation" value={b.animation} options={ANIMATIONS} onChange={(v) => set("animation", v as Block["animation"])} />
        <Select label="Background" value={b.background} options={BACKGROUNDS} onChange={(v) => set("background", v as Block["background"])} />
      </div>
      {["split", "cta", "items"].includes(b.type) && <ButtonInput label="Button" value={b.button} onChange={(v) => set("button", v)} />}
      {hasItems && <div className="space-y-3">
        <p className="field-label">{b.type === "gallery" ? "Pictures" : b.type === "stats" ? "Figures" : "Entries"} ({b.items.length})</p>
        {b.items.map((it, n) => (
          <fieldset key={n} className="space-y-3 rounded-xl border border-line p-3">
            <div className="flex items-center justify-between gap-2"><legend className="text-sm font-bold">Entry {n + 1}</legend><RowTools name={`entry ${n + 1}`} i={n} count={b.items.length} onMove={(by) => set("items", move(b.items, n, by))} onRemove={async () => { if (await confirm({ title: "Delete this entry?", message: "It is removed when you save the page.", confirmLabel: "Delete", danger: true })) set("items", b.items.filter((_, i) => i !== n)); }} /></div>
            <RichInput label={b.type === "stats" ? "Figure" : b.type === "gallery" ? "Picture caption" : "Entry title"} value={it.title} onChange={(v) => setItem(n, { title: v })} />
            {b.type !== "gallery" && <RichInput multiline={b.type === "items"} max={2000} label={b.type === "stats" ? "Figure description" : "Entry text"} value={it.text} onChange={(v) => setItem(n, { text: v })} />}
            {b.type !== "stats" && <ImageInput label="Entry picture" value={it.image} onChange={(v) => setItem(n, { image: v })} />}
            {b.type === "items" && <RichInput bold={false} label={LINK_LABEL} value={it.href} onChange={(v) => setItem(n, { href: v })} />}
          </fieldset>))}
        <button type="button" className="btn btn-outline btn-sm" disabled={b.items.length >= 24} onClick={() => set("items", [...b.items, item()])}><Plus size={14} aria-hidden />Add entry</button>
      </div>}
    </div>
  );
}

function PageEditor({ draft, change, scope }: { draft: PageContent; change: (d: PageContent) => void; scope: "platform" | "pharmacy" }) {
  const confirm = useConfirm(); const [open, setOpen] = useState<number | null>(null); const [adding, setAdding] = useState<BlockType>("items");
  const hero = <K extends keyof Hero>(k: K, v: Hero[K]) => change({ ...draft, hero: { ...draft.hero, [k]: v } });
  const blocks = (next: Block[]) => change({ ...draft, blocks: next });
  const types = TYPES.filter(([, , only]) => !only || only === scope).map(([k, l]) => [k, l] as [string, string]);
  return (
    <div className="space-y-5">
      <section className="card space-y-4 p-5">
        <h2 className="section-title">Hero (top of the page)</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <RichInput bold={false} max={120} label="Small label above the title" value={draft.hero.eyebrow} onChange={(v) => hero("eyebrow", v)} />
          <RichInput label="Title" value={draft.hero.title} onChange={(v) => hero("title", v)} />
          <RichInput bold={false} max={120} label="Highlighted words after the title" value={draft.hero.highlight} onChange={(v) => hero("highlight", v)} />
          <Select label="3D model (shown when there is no picture)" value={draft.hero.model} options={MODELS} onChange={(v) => hero("model", v as Hero["model"])} />
        </div>
        <RichInput multiline max={600} label="Introduction" value={draft.hero.subtitle} onChange={(v) => hero("subtitle", v)} />
        <ImageInput label="Hero picture" value={draft.hero.image} onChange={(v) => hero("image", v)} />
        <ButtonInput label="Main button" value={draft.hero.primary} onChange={(v) => hero("primary", v)} />
        <ButtonInput label="Second button" value={draft.hero.secondary} onChange={(v) => hero("secondary", v)} />
      </section>
      <section className="space-y-3">
        <h2 className="section-title">Page sections ({draft.blocks.length})</h2>
        {draft.blocks.length === 0 && <p className="empty">This page has no extra sections yet.</p>}
        {draft.blocks.map((b, n) => (
          <div key={n} className="card space-y-4 p-4">
            <div className="flex items-center gap-2">
              <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left" aria-expanded={open === n} onClick={() => setOpen(open === n ? null : n)}><ChevronDown size={17} aria-hidden className={`shrink-0 transition-transform ${open === n ? "rotate-180" : ""}`} /><span className="min-w-0"><b className="block truncate">{b.title.replace(/\*\*/g, "") || typeName(b.type)}</b><span className="text-xs text-muted">{typeName(b.type)}</span></span></button>
              <RowTools name={`section ${n + 1}`} i={n} count={draft.blocks.length} onMove={(by) => { blocks(move(draft.blocks, n, by)); setOpen(null); }} onRemove={async () => { if (await confirm({ title: "Delete this section?", message: "It is removed from the website when you save the page.", confirmLabel: "Delete", danger: true })) { blocks(draft.blocks.filter((_, i) => i !== n)); setOpen(null); } }} />
            </div>
            {open === n && <BlockEditor b={b} change={(nb) => blocks(draft.blocks.map((x, i) => (i === n ? nb : x)))} />}
          </div>))}
        <div className="card flex flex-wrap items-end gap-3 p-4">
          <div className="min-w-56 flex-1"><Select label="New section type" value={adding} options={types} onChange={(v) => setAdding(v as BlockType)} /></div>
          <button type="button" className="btn btn-primary" disabled={draft.blocks.length >= 30} onClick={() => { blocks([...draft.blocks, block(adding, ["items", "gallery", "stats"].includes(adding) ? { items: [item()] } : {})]); setOpen(draft.blocks.length); }}><Plus size={16} aria-hidden />Add section</button>
        </div>
      </section>
    </div>
  );
}

function GlobalEditor({ draft, change }: { draft: GlobalContent; change: (d: GlobalContent) => void }) {
  const set = <K extends keyof GlobalContent>(k: K, v: GlobalContent[K]) => change({ ...draft, [k]: v });
  const field = (k: Exclude<keyof GlobalContent, "social">, label: string, multiline = false) => <RichInput key={k} bold={false} multiline={multiline} label={label} value={draft[k]} onChange={(v) => set(k, v)} />;
  return (
    <section className="card space-y-4 p-5">
      <h2 className="section-title">Footer and contact details</h2>
      {field("footerAbout", "Short description shown in the footer", true)}
      <div className="grid gap-4 sm:grid-cols-2">{field("email", "Contact email")}{field("phone", "Contact phone")}{field("whatsapp", "WhatsApp number")}{field("hours", "Opening hours", true)}</div>
      {field("address", "Office or shop address", true)}
      <div className="grid gap-4 sm:grid-cols-2">{field("latitude", "Map latitude (optional)")}{field("longitude", "Map longitude (optional)")}</div>
      <p className="text-xs text-muted">The map uses the coordinates when both are filled in, otherwise the written address. In Google Maps, right-click a place to copy its coordinates.</p>
      {(draft.address || (draft.latitude && draft.longitude)) && <MapCard className="max-w-xl" address={draft.address} latitude={draft.latitude} longitude={draft.longitude} />}
      <div className="space-y-3">
        <p className="field-label">Social media links</p>
        {draft.social.map((s, n) => <div key={n} className="flex items-end gap-2"><div className="grid flex-1 gap-2 sm:grid-cols-2"><RichInput bold={false} max={40} label="Network name" value={s.title} onChange={(v) => set("social", draft.social.map((x, i) => (i === n ? { ...x, title: v } : x)))} /><RichInput bold={false} label="Profile link starting with https://" value={s.href} onChange={(v) => set("social", draft.social.map((x, i) => (i === n ? { ...x, href: v } : x)))} /></div><button type="button" className="icon-btn !text-danger" aria-label={`Delete social link ${n + 1}`} onClick={() => set("social", draft.social.filter((_, i) => i !== n))}><Trash2 size={15} /></button></div>)}
        <button type="button" className="btn btn-outline btn-sm" disabled={draft.social.length >= 8} onClick={() => set("social", [...draft.social, { title: "", href: "" }])}><Plus size={14} aria-hidden />Add link</button>
      </div>
    </section>
  );
}

type Draft = PageContent | GlobalContent;

function Builder({ site }: { site?: Site }) {
  const scope = site ? "pharmacy" : "platform";
  const pages = site ? PHARMACY_PAGES : PLATFORM_PAGES;
  const qc = useQueryClient(); const toast = useToast(); const confirm = useConfirm();
  const [key, setKey] = useState("home"); const [draft, setDraft] = useState<Draft | null>(null);
  const [dirty, setDirty] = useState(false); const [busy, setBusy] = useState(false); const [preview, setPreview] = useState(false);
  const q = useQuery({ queryKey: ["website-page", scope, key], queryFn: () => api<{ content: Draft | null }>(`/website/pages/${key}/`), gcTime: 0, refetchOnWindowFocus: false });
  const initial = (): Draft => (key === "global" ? EMPTY_GLOBAL : site ? pharmacyDefault(key, site) : platformDefault(key));
  useEffect(() => { if (q.data && !draft) setDraft(q.data.content ? (key === "global" ? { ...EMPTY_GLOBAL, ...q.data.content } : q.data.content) : initial()); });
  useEffect(() => { if (!dirty) return; const warn = (e: BeforeUnloadEvent) => e.preventDefault(); window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn); }, [dirty]);
  const open = async (next: string) => {
    if (next === key || (dirty && !(await confirm({ title: "Discard unsaved changes?", message: "Your changes to this page have not been saved.", confirmLabel: "Discard", danger: true })))) return;
    setKey(next); setDraft(null); setDirty(false);
  };
  const refresh = () => qc.invalidateQueries({ queryKey: ["site-page"] });
  const save = async () => {
    setBusy(true);
    try { const r = await api<{ content: Draft }>(`/website/pages/${key}/`, { method: "PUT", body: { content: draft } }); setDraft(r.content); setDirty(false); refresh(); toast("Saved. The website now shows this content."); }
    catch (e) { toast(errorMessage(e), "error"); }
    setBusy(false);
  };
  const reset = async () => {
    if (!(await confirm({ title: "Restore the starting content?", message: "Your saved content for this page is deleted.", confirmLabel: "Restore", danger: true }))) return;
    try { await api(`/website/pages/${key}/`, { method: "DELETE" }); setDraft(initial()); setDirty(false); refresh(); toast("The starting content is back."); }
    catch (e) { toast(errorMessage(e), "error"); }
  };
  const path = key === "global" ? "" : pages.find(([k]) => k === key)?.[2] ?? "";
  const live = site ? `/${site.slug}${path}` : path || "/";
  const info: SiteInfo = site ? { slug: site.slug, name: site.name, contact: contactOf(site, EMPTY_GLOBAL), colors: [site.primary_color, site.secondary_color] } : { name: "NTS Pharmacy System", contact: EMPTY_GLOBAL };
  const change = (d: Draft) => { setDraft(d); setDirty(true); };
  return (
    <div className="space-y-5">
      <PageHeader title="Website content" subtitle={site ? "Build and update the pages of your pharmacy website." : "Build and update the pages of the main website."}
        actions={<><a className="btn btn-outline" href={live} target="_blank" rel="noopener noreferrer"><ExternalLink size={15} aria-hidden />View live page</a>{key !== "global" && <button className="btn btn-outline" disabled={!draft} onClick={() => setPreview(true)}><Eye size={15} aria-hidden />Preview</button>}<button className="btn btn-primary" disabled={!draft || busy || !dirty} onClick={save}>{busy ? <Spinner /> : <Save size={15} aria-hidden />}Save page</button></>} />
      <div className="grid items-start gap-5 lg:grid-cols-[15rem_1fr]">
        <nav aria-label="Website pages" className="card flex gap-1 overflow-x-auto p-2 lg:flex-col">
          {([["global", "Footer & contacts"], ...pages.map(([k, l]) => [k, l])] as [string, string][]).map(([k, l]) => <button key={k} type="button" aria-current={k === key ? "page" : undefined} onClick={() => open(k)} className={`shrink-0 rounded-lg px-3 py-2 text-left text-sm font-semibold ${k === key ? "bg-teal-50 text-teal-700" : "text-muted hover:bg-slate-100"}`}>{l}</button>)}
        </nav>
        <div className="min-w-0 space-y-4">
          {q.isError ? <p role="alert" className="alert alert-error">{errorMessage(q.error)}</p> : !draft ? <Loading rows={6} /> : <>
            {key === "global" ? <GlobalEditor draft={draft as GlobalContent} change={change} /> : <PageEditor key={key} draft={draft as PageContent} change={change} scope={scope} />}
            <div className="flex flex-wrap justify-between gap-2"><button className="btn btn-outline btn-link-danger" onClick={reset}><RotateCcw size={15} aria-hidden />Restore starting content</button><button className="btn btn-primary" disabled={busy || !dirty} onClick={save}>{busy ? <Spinner /> : <Save size={15} aria-hidden />}Save page</button></div>
          </>}
        </div>
      </div>
      {preview && draft && key !== "global" && <Modal title="Preview" size="lg" onClose={() => setPreview(false)}><div className="overflow-hidden rounded-xl border border-line" onClickCapture={(e) => { if ((e.target as HTMLElement).closest("a, form button")) e.preventDefault(); }}><PageView content={draft as PageContent} info={info} /></div></Modal>}
    </div>
  );
}

function PharmacyBuilder({ slug }: { slug: string }) {
  const site = useSiteQuery(slug);
  return site.data ? <Builder site={site.data} /> : <Loading rows={6} />;
}

export default function WebsiteBuilder() {
  const { slug } = useParams();
  return slug ? <PharmacyBuilder slug={slug} /> : <Builder />;
}
