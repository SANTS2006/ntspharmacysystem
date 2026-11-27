/** One sign-in page per pharmacy (staff and customers alike, routed by role) plus the platform sign-in, registration,
 *  email verification, password recovery and forced password change. */
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, KeyRound, Lock, LogIn, Mail, MailCheck, Phone, Send, ShieldCheck, Store, User as UserIcon, UserPlus } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { AuthShell, Field, Notice, PasswordRules, SubmitButton } from "../../components/auth/AuthUi";
import { PageLoader, type Brand } from "../../components/brand/Brand";
import { SystemNotFound } from "../../components/NotFound";
import { ErrorState, errorMessage } from "../../components/ui";
import { ApiError, api, changePassword, fetchMe, login, setTokens, type User } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { PHARMACY_POINTS, brandOf, homeFor, useSiteQuery, type Site } from "../../lib/site";

const strong = z.string().min(10, "Use at least 10 characters.").regex(/[A-Za-z]/, "Include a letter.").regex(/\d/, "Include a number.");
const link = "font-bold text-primary hover:underline";

/** Loads the pharmacy's identity first so its sign-in pages never flash the platform brand. */
function Branded({ slug, children }: { slug?: string; children: (v: { brand: Brand | undefined; site?: Site; extra: Record<string, unknown> }) => ReactNode }) {
  const q = useSiteQuery(slug);
  if (slug && q.isLoading) return <PageLoader label="Opening your pharmacy…" />;
  if (slug && q.error instanceof ApiError && q.error.status === 404) return <SystemNotFound />;
  if (slug && !q.data) return <main className="grid min-h-screen place-items-center p-6"><div className="w-full max-w-md"><ErrorState onRetry={() => q.refetch()}>This pharmacy could not be loaded. Check your connection.</ErrorState></div></main>;
  const s = q.data;
  const extra = s ? { headline: `Welcome to ${s.name}.`, blurb: s.description || "One secure sign-in for our team and our customers.", points: PHARMACY_POINTS, back: { to: `/${s.slug}`, label: "Back to website" } } : { back: { to: "/", label: "Home" } };
  return <>{children({ brand: s ? brandOf(s) : undefined, site: s, extra })}</>;
}

/** Only same-pharmacy paths are followed after sign-in (no open redirect). */
const safeNext = (next: string | null, slug?: string) => (next && slug && next.startsWith(`/${slug}/`) && !next.includes("//") ? next : null);

export function LoginPage() {
  const { slug } = useParams();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const { user, loading, setUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<{ email: string; password: string }>({ resolver: zodResolver(z.object({ email: z.string().email("Enter a valid email address."), password: z.string().min(1, "Enter your password.") })) });
  const go = (u: User) => {
    const next = safeNext(sp.get("next"), u.tenant_slug ?? undefined);
    nav(next && u.role === "customer" && u.email_verified ? next : homeFor(u), { replace: true, state: { slug } });
  };
  if (!loading && user && !isSubmitting && (slug ? user.tenant_slug === slug : user.is_platform_admin)) return <Navigate to={homeFor(user)} replace />;
  const submit = async (v: { email: string; password: string }) => {
    setError(null);
    try { const u = await login(v.email, v.password, slug); setUser(u); go(u); }
    catch (e) { setError(errorMessage(e)); }
  };
  return (
    <Branded slug={slug}>{({ brand, extra }) => (
      <AuthShell {...extra} brand={brand} icon={slug ? Store : LogIn} title={slug ? "Sign in" : "Platform sign in"} subtitle={slug ? "Staff and customers use the same sign-in. We take you to the right place." : "Sign in to the platform administration."}
        footer={<div className="space-y-2"><p><Link className={link} to={slug ? `/${slug}/forgot-password` : "/platform/forgot-password"}>Forgot your password?</Link></p>{slug && <p>New customer? <Link className={link} to={`/${slug}/register${sp.get("next") ? `?next=${encodeURIComponent(sp.get("next")!)}` : ""}`}>Create an account</Link></p>}</div>}>
        <form onSubmit={handleSubmit(submit)} noValidate className="space-y-4">
          <Notice message={error} />
          <Field label="Email" icon={Mail} type="email" autoComplete="username" placeholder="Enter your email" error={errors.email?.message} {...register("email")} />
          <Field label="Password" icon={Lock} type="password" autoComplete="current-password" placeholder="Enter your password" error={errors.password?.message} {...register("password")} />
          <SubmitButton busy={isSubmitting} icon={LogIn}>{isSubmitting ? "Signing in…" : "Sign in"}</SubmitButton>
        </form>
      </AuthShell>)}
    </Branded>
  );
}

const registerSchema = z.object({ full_name: z.string().min(2, "Enter your full name."), email: z.string().email("Enter a valid email address."), phone: z.string().optional(), password: strong, confirm: z.string(), terms: z.boolean().refine((v) => v, "You must agree to the Terms of Use and Privacy Policy.") })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });
type RegisterForm = z.infer<typeof registerSchema>;

export function RegisterPage() {
  const { slug = "" } = useParams();
  const nav = useNavigate(); const { setUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm<RegisterForm>({ resolver: zodResolver(registerSchema), defaultValues: { terms: false } });
  const submit = async ({ confirm: _c, terms, ...v }: RegisterForm) => {
    setError(null);
    try {
      const r = await api<{ tokens: { access: string; refresh: string } }>("/shop/register/", { method: "POST", body: { ...v, terms_accepted: terms }, tenant: slug, retry: false });
      setTokens(r.tokens); setUser(await fetchMe(slug)); nav(`/${slug}/verify`, { replace: true });
    } catch (e) { setError(errorMessage(e)); }
  };
  return (
    <Branded slug={slug}>{({ brand, extra }) => (
      <AuthShell {...extra} brand={brand} icon={UserPlus} title="Create your account" subtitle="Order medicines online and track every order." footer={<p>Already registered? <Link className={link} to={`/${slug}/login`}>Sign in</Link></p>}>
        <form onSubmit={handleSubmit(submit)} noValidate className="space-y-4">
          <Notice message={error} />
          <Field label="Full name" icon={UserIcon} autoComplete="name" error={errors.full_name?.message} {...register("full_name")} />
          <Field label="Email" icon={Mail} type="email" autoComplete="email" error={errors.email?.message} {...register("email")} />
          <Field label="Phone number" icon={Phone} type="tel" required={false} autoComplete="tel" {...register("phone")} />
          <Field label="Password" icon={Lock} type="password" autoComplete="new-password" error={errors.password?.message} {...register("password")} />
          <PasswordRules value={watch("password")} />
          <Field label="Confirm password" icon={Lock} type="password" autoComplete="new-password" error={errors.confirm?.message} {...register("confirm")} />
          <div><label className="flex items-start gap-2.5 text-sm"><input type="checkbox" className="mt-0.5" {...register("terms")} /><span>I agree to the <Link to="/legal/terms" target="_blank" className={link}>Terms of Use</Link> and <Link to="/legal/privacy" target="_blank" className={link}>Privacy Policy</Link></span></label>{errors.terms && <p role="alert" className="mt-1 text-xs text-danger">{errors.terms.message}</p>}</div>
          <SubmitButton busy={isSubmitting} icon={UserPlus}>{isSubmitting ? "Creating your account…" : "Create account"}</SubmitButton>
        </form>
      </AuthShell>)}
    </Branded>
  );
}

export function VerifyEmailPage() {
  const { slug = "" } = useParams(); const nav = useNavigate(); const { user, loading, setUser } = useAuth();
  const [code, setCode] = useState(""); const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null); const [busy, setBusy] = useState(false);
  if (loading) return <PageLoader />;
  if (!user || user.tenant_slug !== slug) return <Navigate to={`/${slug}/login`} replace />;
  if (user.email_verified) return <Navigate to={homeFor(user)} replace />;
  const verify = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true);
    try { await api("/shop/verify-email/", { method: "POST", body: { code: code.trim().toUpperCase() }, tenant: slug }); const me = await fetchMe(slug); setUser(me); nav(homeFor(me), { replace: true }); }
    catch (e2) { setMsg({ ok: false, t: errorMessage(e2) }); setBusy(false); }
  };
  const resend = () => api("/shop/resend-code/", { method: "POST", tenant: slug }).then(() => setMsg({ ok: true, t: "A new code has been sent." })).catch((e) => setMsg({ ok: false, t: errorMessage(e) }));
  return (
    <Branded slug={slug}>{({ brand, extra }) => (
      <AuthShell {...extra} brand={brand} icon={MailCheck} title="Verify your email" subtitle={`Enter the 6-character code we sent to ${user.email}.`} footer={<button type="button" onClick={resend} className={link}>Send a new code</button>}>
        <form onSubmit={verify} className="space-y-4"><Notice message={msg?.t ?? null} ok={msg?.ok} />
          <input aria-label="Verification code" required maxLength={6} minLength={6} autoComplete="one-time-code" className="w-full !min-h-16 !rounded-xl text-center !text-3xl font-bold uppercase tracking-[0.5em] placeholder:!text-base placeholder:!tracking-normal" placeholder="Enter your code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
          <SubmitButton busy={busy} icon={ShieldCheck}>Verify email</SubmitButton>
        </form>
      </AuthShell>)}
    </Branded>
  );
}

export function ForgotPasswordPage() {
  const { slug } = useParams();
  const [sent, setSent] = useState(false);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<{ email: string }>({ resolver: zodResolver(z.object({ email: z.string().email("Enter a valid email address.") })) });
  const back = <Link to={slug ? `/${slug}/login` : "/platform/login"} className={`inline-flex items-center gap-1 ${link}`}><ArrowLeft size={15} aria-hidden />Back to sign in</Link>;
  return (
    <Branded slug={slug}>{({ brand, extra }) => sent ? (
      <AuthShell {...extra} brand={brand} icon={MailCheck} title="Check your email" subtitle="If an account exists for that address, a reset link has been sent. The link expires soon." footer={back}>
        <p className="alert alert-info">Did not get it? Check your spam folder, or try again in a minute.</p>
        <button type="button" className="btn btn-outline mt-4 w-full" onClick={() => setSent(false)}>Use another email address</button>
      </AuthShell>
    ) : (
      <AuthShell {...extra} brand={brand} icon={KeyRound} title="Forgot your password?" subtitle="Enter your email and we will send you a secure reset link." footer={back}>
        <form noValidate className="space-y-4" onSubmit={handleSubmit(async (v) => { await api("/auth/password-reset/", { method: "POST", body: v, tenant: slug }).catch(() => {}); setSent(true); })}>
          <Field label="Email" icon={Mail} type="email" autoComplete="email" error={errors.email?.message} {...register("email")} />
          <SubmitButton busy={isSubmitting} icon={Send}>Send reset link</SubmitButton>
        </form>
      </AuthShell>)}
    </Branded>
  );
}

const resetSchema = z.object({ new_password: strong, confirm: z.string() }).refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });

function TokenForm({ mode }: { mode: "reset" | "invite" }) {
  const [sp] = useSearchParams(); const nav = useNavigate(); const { setUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm<z.infer<typeof resetSchema>>({ resolver: zodResolver(resetSchema) });
  const tenant = sp.get("tenant") ?? undefined;
  const submit = async (v: z.infer<typeof resetSchema>) => {
    try {
      const body = mode === "reset" ? { uid: sp.get("uid"), token: sp.get("token"), new_password: v.new_password } : { token: sp.get("token"), new_password: v.new_password };
      const r = await api<{ tokens: { access: string; refresh: string } }>(mode === "reset" ? "/auth/password-reset/confirm/" : "/auth/accept-invitation/", { method: "POST", body, tenant, retry: false });
      setTokens(r.tokens); const me = await fetchMe(tenant); setUser(me); nav(homeFor(me), { replace: true });
    } catch (e) { setError(errorMessage(e)); }
  };
  return (
    <Branded slug={tenant}>{({ brand, extra }) => (
      <AuthShell {...extra} brand={brand} icon={mode === "reset" ? KeyRound : ShieldCheck} title={mode === "reset" ? "Choose a new password" : "Set your password"} subtitle={mode === "reset" ? "Pick a strong password you have not used elsewhere." : "Welcome! Create a password to activate your account."}>
        <form noValidate className="space-y-4" onSubmit={handleSubmit(submit)}>
          <Notice message={error} />
          <Field label="New password" icon={Lock} type="password" autoComplete="new-password" error={errors.new_password?.message} {...register("new_password")} />
          <PasswordRules value={watch("new_password")} />
          <Field label="Confirm password" icon={Lock} type="password" autoComplete="new-password" error={errors.confirm?.message} {...register("confirm")} />
          <SubmitButton busy={isSubmitting} icon={ShieldCheck}>Save password</SubmitButton>
        </form>
      </AuthShell>)}
    </Branded>
  );
}
export const ResetPasswordPage = () => <TokenForm mode="reset" />;
export const AcceptInvitationPage = () => <TokenForm mode="invite" />;

const changeSchema = z.object({ old_password: z.string().min(1, "Enter your current password."), new_password: strong, confirm: z.string() }).refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });

export function ChangePasswordPage() {
  const nav = useNavigate();
  const { user, setUser } = useAuth();
  const slug = (useLocation().state as { slug?: string } | null)?.slug ?? user?.tenant_slug ?? undefined;
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm<z.infer<typeof changeSchema>>({ resolver: zodResolver(changeSchema) });
  const submit = async (v: z.infer<typeof changeSchema>) => {
    try { await changePassword(v.old_password, v.new_password, slug); const me = await fetchMe(slug); setUser(me); nav(homeFor(me), { replace: true }); }
    catch (e) { setError(errorMessage(e)); }
  };
  return (
    <Branded slug={slug}>{({ brand, extra }) => (
      <AuthShell {...extra} brand={brand} back={undefined} icon={KeyRound} title="Set a new password" subtitle="Your temporary password must be replaced before you continue.">
        <form onSubmit={handleSubmit(submit)} noValidate className="space-y-4">
          <Notice message={error} />
          <Field label="Temporary password" icon={Lock} type="password" autoComplete="current-password" error={errors.old_password?.message} {...register("old_password")} />
          <Field label="New password" icon={Lock} type="password" autoComplete="new-password" error={errors.new_password?.message} {...register("new_password")} />
          <PasswordRules value={watch("new_password")} />
          <Field label="Confirm new password" icon={Lock} type="password" autoComplete="new-password" error={errors.confirm?.message} {...register("confirm")} />
          <SubmitButton busy={isSubmitting} icon={ShieldCheck}>Update password</SubmitButton>
        </form>
      </AuthShell>)}
    </Branded>
  );
}
