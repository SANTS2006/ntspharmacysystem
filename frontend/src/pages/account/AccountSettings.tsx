/** "Settings" for the signed-in person: profile and picture, email address, password, appearance, and (customers) their pharmacy profile. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Check, MapPin, Moon, Pencil, Plus, Sun, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { PasswordRules } from "../../components/auth/AuthUi";
import { Avatar, ErrorState, FormModal, Loading, PageHeader, PasswordInput, Spinner, Tabs, errorMessage, useConfirm, useToast } from "../../components/ui";
import { api, changePassword, type User } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { day } from "../../lib/format";
import { useTheme } from "../../lib/theme";

type Tab = "profile" | "details" | "email" | "password" | "appearance";

function ProfileTab({ user }: { user: User }) {
  const { setUser } = useAuth(); const toast = useToast(); const confirm = useConfirm();
  const [name, setName] = useState(user.full_name);
  const [phone, setPhone] = useState(user.phone ?? "");
  const file = useRef<HTMLInputElement>(null);
  const fail = (e: unknown) => toast(errorMessage(e), "error");
  const save = useMutation({ mutationFn: () => api<User>("/auth/me/profile/", { method: "PATCH", body: { full_name: name, phone } }), onSuccess: (u) => { setUser(u); toast("Profile saved."); }, onError: fail });
  const upload = useMutation({ mutationFn: (f: File) => { const fd = new FormData(); fd.append("avatar", f); return api<User>("/auth/me/avatar/", { method: "POST", body: fd }); }, onSuccess: (u) => { setUser(u); toast("Profile picture updated."); }, onError: fail });
  const remove = useMutation({ mutationFn: () => api<User>("/auth/me/avatar/", { method: "DELETE" }), onSuccess: (u) => { setUser(u); toast("Profile picture removed."); }, onError: fail });
  return (
    <div className="grid gap-5 lg:grid-cols-[20rem_1fr]">
      <section className="card flex flex-col items-center gap-4 p-6 text-center">
        <div className="relative">
          <Avatar src={user.avatar} name={user.full_name} size={132} />
          {upload.isPending && <span className="backdrop absolute inset-0 grid place-items-center rounded-full text-white"><Spinner size={28} /></span>}
          <button type="button" onClick={() => file.current?.click()} aria-label="Change profile picture" className="btn btn-primary absolute bottom-0 right-0 !h-11 !min-h-0 !w-11 !rounded-full !p-0"><Camera size={18} aria-hidden /></button>
        </div>
        <input ref={file} type="file" className="sr-only" aria-label="Choose a profile picture" accept="image/png,image/jpeg,image/webp" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
        <div><p className="font-bold">{user.full_name}</p><p className="break-all text-sm text-muted">{user.email}</p></div>
        <p className="text-xs text-muted">PNG, JPG or WebP, up to 2 MB.</p>
        {user.avatar && <button className="btn-link btn-link-danger" disabled={remove.isPending} onClick={async () => { if (await confirm({ title: "Remove your profile picture?", confirmLabel: "Remove", danger: true })) remove.mutate(); }}><Trash2 size={13} aria-hidden />Remove picture</button>}
      </section>
      <section className="card p-6">
        <h2 className="section-title">Personal information</h2>
        <form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <label className="field-label">Full name<input required maxLength={200} className="mt-1.5 w-full" autoComplete="name" placeholder="Enter your full name" value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="field-label">Phone number<input maxLength={30} type="tel" className="mt-1.5 w-full" autoComplete="tel" placeholder="Enter your phone number" value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
          <div className="sm:col-span-2"><button className="btn btn-primary" disabled={save.isPending}>{save.isPending ? <Spinner /> : <Check size={16} aria-hidden />}Save changes</button></div>
        </form>
        <dl className="mt-6 grid gap-4 border-t border-line pt-5 text-sm sm:grid-cols-2">
          {([["Role", user.is_platform_admin ? "Platform administrator" : user.role_name], ["Pharmacy", user.pharmacy_name], ["Branch", user.branch_name], ["Member since", user.date_joined ? day(user.date_joined) : null]] as const)
            .filter(([, v]) => v).map(([k, v]) => <div key={k}><dt className="text-muted">{k}</dt><dd className="font-semibold">{v}</dd></div>)}
        </dl>
      </section>
    </div>
  );
}

function EmailTab({ user }: { user: User }) {
  const { setUser } = useAuth(); const toast = useToast();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [sentTo, setSentTo] = useState(""); const [code, setCode] = useState("");
  const request = useMutation({ mutationFn: () => api<{ sent_to: string }>("/auth/me/email/", { method: "POST", body: { new_email: email, password } }), onSuccess: (r) => { setSentTo(r.sent_to); setPassword(""); } });
  const verify = useMutation({ mutationFn: () => api<User>("/auth/me/email/confirm/", { method: "POST", body: { code: code.trim().toUpperCase() } }), onSuccess: (u) => { setUser(u); setSentTo(""); setEmail(""); setCode(""); toast("Your email address has been changed."); } });
  if (user.has_password === false) return <div className="card p-6 text-sm text-muted">You sign in with Google, so your email address is managed by your Google account.</div>;
  return (
    <section className="card max-w-xl p-6">
      <h2 className="section-title">Email address</h2>
      <p className="mt-1 text-sm text-muted">You sign in with <b className="text-ink">{user.email}</b>. We send a code to the new address to confirm it is yours.</p>
      {!sentTo ? (
        <form className="mt-4 space-y-4" onSubmit={(e) => { e.preventDefault(); request.mutate(); }}>
          {request.isError && <p role="alert" className="alert alert-error">{errorMessage(request.error)}</p>}
          <label className="field-label">New email address<input required type="email" className="mt-1.5 w-full" autoComplete="email" placeholder="Enter your new email address" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label className="field-label">Current password<span className="mt-1.5 block"><PasswordInput required autoComplete="current-password" placeholder="Enter your current password" value={password} onChange={(e) => setPassword(e.target.value)} /></span></label>
          <button className="btn btn-primary" disabled={request.isPending}>{request.isPending && <Spinner />}Send confirmation code</button>
        </form>
      ) : (
        <form className="mt-4 space-y-4" onSubmit={(e) => { e.preventDefault(); verify.mutate(); }}>
          <p className="alert alert-info">Enter the 6-character code we sent to {sentTo}.</p>
          {verify.isError && <p role="alert" className="alert alert-error">{errorMessage(verify.error)}</p>}
          <label className="field-label">Confirmation code<input required minLength={6} maxLength={6} autoComplete="one-time-code" className="mt-1.5 w-full text-center !text-2xl font-bold uppercase tracking-[0.4em]" placeholder="Enter your code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} /></label>
          <div className="flex flex-wrap gap-2"><button className="btn btn-primary" disabled={verify.isPending}>{verify.isPending && <Spinner />}Confirm new email</button><button type="button" className="btn btn-outline" onClick={() => setSentTo("")}>Cancel</button></div>
        </form>)}
    </section>
  );
}

function PasswordTab({ user }: { user: User }) {
  const toast = useToast();
  const [f, setF] = useState({ old: "", next: "", confirm: "" });
  const [problem, setProblem] = useState("");
  const save = useMutation({ mutationFn: () => changePassword(f.old, f.next, user.tenant_slug), onSuccess: () => { setF({ old: "", next: "", confirm: "" }); toast("Password changed. Other devices have been signed out."); }, onError: (e) => setProblem(errorMessage(e)) });
  if (user.has_password === false) return <div className="card p-6 text-sm text-muted">You sign in with Google, so there is no password to change here.</div>;
  const field = (key: keyof typeof f, label: string, auto: string) => <label className="field-label">{label}<span className="mt-1.5 block"><PasswordInput required autoComplete={auto} placeholder={`Enter your ${label.toLowerCase()}`} value={f[key]} onChange={(e) => setF({ ...f, [key]: e.target.value })} /></span></label>;
  return (
    <section className="card max-w-xl p-6">
      <h2 className="section-title">Change password</h2>
      <p className="mt-1 text-sm text-muted">Changing your password signs you out everywhere else.</p>
      <form className="mt-4 space-y-4" onSubmit={(e) => { e.preventDefault(); setProblem(""); if (f.next !== f.confirm) setProblem("The new passwords do not match."); else save.mutate(); }}>
        {problem && <p role="alert" className="alert alert-error">{problem}</p>}
        {field("old", "Current password", "current-password")}
        {field("next", "New password", "new-password")}
        <PasswordRules value={f.next} />
        {field("confirm", "Confirm new password", "new-password")}
        <button className="btn btn-primary" disabled={save.isPending}>{save.isPending && <Spinner />}Update password</button>
      </form>
    </section>
  );
}

interface CustomerProfile { full_name: string; phone: string; date_of_birth: string | null; gender: string; address: string; delivery_addresses: { label: string; address: string }[]; emergency_contact_name: string; emergency_contact_phone: string; notification_prefs: { email_orders?: boolean; email_marketing?: boolean } }

function CustomerDetailsTab({ user }: { user: User }) {
  const qc = useQueryClient(); const toast = useToast(); const confirm = useConfirm();
  const [editing, setEditing] = useState(false); const [address, setAddress] = useState<number | "new" | null>(null);
  const q = useQuery({ queryKey: ["my-profile"], queryFn: () => api<CustomerProfile>("/shop/me/", { tenant: user.tenant_slug }), retry: false });
  const patch = async (body: Partial<CustomerProfile>) => { const next = await api<CustomerProfile>("/shop/me/", { method: "PATCH", body, tenant: user.tenant_slug }); qc.setQueryData(["my-profile"], next); toast("Saved."); };
  if (q.isLoading) return <Loading rows={3} />;
  if (!q.data) return <ErrorState onRetry={() => q.refetch()}>{errorMessage(q.error)}</ErrorState>;
  const p = q.data;
  const rows: [string, string][] = [["Date of birth", p.date_of_birth ? day(p.date_of_birth) : "Not set"], ["Gender", p.gender || "Not set"], ["Home address", p.address || "Not set"], ["Emergency contact", [p.emergency_contact_name, p.emergency_contact_phone].filter(Boolean).join(" · ") || "Not set"]];
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="card p-6">
        <div className="flex items-center justify-between gap-2"><h2 className="section-title">My details</h2><button className="btn-link" onClick={() => setEditing(true)}><Pencil size={13} aria-hidden />Edit</button></div>
        <dl className="mt-4 space-y-3 text-sm">{rows.map(([k, v]) => <div key={k} className="flex justify-between gap-4 border-b border-line pb-2"><dt className="text-muted">{k}</dt><dd className="text-right font-semibold">{v}</dd></div>)}</dl>
        <h3 className="mt-5 text-sm font-bold">Email preferences</h3>
        {([["email_orders", "Email me about my orders"], ["email_marketing", "Email me offers and health news"]] as const).map(([k, label]) => (
          <label key={k} className="mt-2 flex items-center gap-2.5 text-sm"><input type="checkbox" checked={!!p.notification_prefs?.[k]} onChange={(e) => patch({ notification_prefs: { ...p.notification_prefs, [k]: e.target.checked } }).catch((err) => toast(errorMessage(err), "error"))} />{label}</label>))}
      </section>
      <section className="card p-6">
        <div className="flex items-center justify-between gap-2"><h2 className="section-title">Delivery addresses</h2><button className="btn btn-primary btn-sm" disabled={p.delivery_addresses.length >= 10} onClick={() => setAddress("new")}><Plus size={14} aria-hidden />Add address</button></div>
        {p.delivery_addresses.length === 0 && <p className="mt-4 text-sm text-muted">No saved addresses yet.</p>}
        <ul className="mt-4 space-y-2">{p.delivery_addresses.map((a, i) => (
          <li key={`${a.address}-${i}`} className="flex items-start gap-3 rounded-xl border border-line p-3 text-sm">
            <MapPin size={16} aria-hidden className="mt-0.5 text-primary" /><span className="min-w-0 flex-1"><b className="block">{a.label || "Address"}</b><span className="text-muted">{a.address}</span></span>
            <button className="btn-link" onClick={() => setAddress(i)}>Edit</button>
            <button className="btn-link btn-link-danger" onClick={async () => { if (await confirm({ title: "Delete this address?", message: a.address, confirmLabel: "Delete", danger: true })) patch({ delivery_addresses: p.delivery_addresses.filter((_, n) => n !== i) }).catch((e) => toast(errorMessage(e), "error")); }}>Delete</button>
          </li>))}</ul>
      </section>
      {editing && <FormModal title="Edit my details" onClose={() => setEditing(false)} onSubmit={(v) => patch({ date_of_birth: v.date_of_birth || null, gender: v.gender, address: v.address, emergency_contact_name: v.emergency_contact_name, emergency_contact_phone: v.emergency_contact_phone })}
        fields={[
          { name: "date_of_birth", label: "Date of birth", type: "date", required: false, defaultValue: p.date_of_birth },
          { name: "gender", label: "Gender", type: "select", required: false, defaultValue: p.gender, options: [["", "Prefer not to say"], ["female", "Female"], ["male", "Male"], ["other", "Other"]] },
          { name: "address", label: "Home address", required: false, wide: true, defaultValue: p.address },
          { name: "emergency_contact_name", label: "Emergency contact name", required: false, defaultValue: p.emergency_contact_name },
          { name: "emergency_contact_phone", label: "Emergency contact phone", type: "tel", required: false, defaultValue: p.emergency_contact_phone },
        ]} />}
      {address !== null && <FormModal title={address === "new" ? "Add a delivery address" : "Edit delivery address"} onClose={() => setAddress(null)}
        onSubmit={(v) => { const row = { label: v.label, address: v.address }; return patch({ delivery_addresses: address === "new" ? [...p.delivery_addresses, row] : p.delivery_addresses.map((a, n) => (n === address ? row : a)) }); }}
        fields={[{ name: "label", label: "Address label", required: false, hint: "For example Home or Office", defaultValue: address === "new" ? "" : p.delivery_addresses[address]?.label }, { name: "address", label: "Delivery address", type: "textarea", maxLength: 300, defaultValue: address === "new" ? "" : p.delivery_addresses[address]?.address }]} />}
    </div>
  );
}

function AppearanceTab() {
  const { theme, setTheme } = useTheme();
  return (
    <section className="card max-w-xl p-6">
      <h2 className="section-title">Appearance</h2>
      <p className="mt-1 text-sm text-muted">Choose how the system looks on this device.</p>
      <div role="radiogroup" aria-label="Theme" className="mt-4 grid grid-cols-2 gap-3">
        {([["light", "Light mode", Sun, "#f4f7fa", "#ffffff"], ["dark", "Dark mode", Moon, "#0a1120", "#121c30"]] as const).map(([key, label, Icon, bg, panel]) => (
          <button key={key} type="button" role="radio" aria-checked={theme === key} onClick={() => setTheme(key)} className={`card card-hover p-3 text-left ${theme === key ? "ring-2 ring-offset-2" : ""}`} style={theme === key ? ({ "--tw-ring-color": "var(--brand)", "--tw-ring-offset-color": "var(--color-canvas)" } as React.CSSProperties) : undefined}>
            <span className="block h-20 rounded-lg p-2" style={{ background: bg }} aria-hidden><span className="block h-3 w-1/2 rounded" style={{ background: "var(--brand)" }} /><span className="mt-2 block h-10 rounded" style={{ background: panel }} /></span>
            <span className="mt-2 flex items-center gap-2 text-sm font-bold"><Icon size={15} aria-hidden />{label}{theme === key && <Check size={15} aria-hidden className="ml-auto text-primary" />}</span>
          </button>))}
      </div>
    </section>
  );
}

export default function AccountSettings() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("profile");
  if (!user) return null;
  const customer = user.role === "customer";
  const tabs: [Tab, string][] = [["profile", "Profile"], ...(customer ? [["details", "My details"] as [Tab, string]] : []), ["email", "Email"], ["password", "Password"], ["appearance", "Appearance"]];
  return (
    <div className="space-y-5">
      <PageHeader title="Settings" subtitle="Manage your profile, sign-in details and how the system looks." />
      <Tabs label="Settings sections" tabs={tabs} value={tab} onChange={setTab} />
      <div key={tab} className="animate-rise">
        {tab === "profile" && <ProfileTab user={user} />}
        {tab === "details" && <CustomerDetailsTab user={user} />}
        {tab === "email" && <EmailTab user={user} />}
        {tab === "password" && <PasswordTab user={user} />}
        {tab === "appearance" && <AppearanceTab />}
      </div>
    </div>
  );
}
