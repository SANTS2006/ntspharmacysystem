import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, KeyRound, Lock, Mail, MailCheck, Send, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { AuthShell, Field, Notice, PasswordRules, SubmitButton } from "../components/auth/AuthUi";
import { ApiError, api, fetchMe, setTokens } from "../lib/api";
import { useAuth } from "../lib/auth";

const strong = z.string().min(10, "Use at least 10 characters.").regex(/[A-Za-z]/, "Include a letter.").regex(/\d/, "Include a number.");

export function ForgotPassword({ tenant }: { tenant?: string }) {
  const [sent, setSent] = useState(false);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<{ email: string }>({ resolver: zodResolver(z.object({ email: z.string().email("Enter a valid email address.") })) });
  const back = <Link to={tenant ? `/${tenant}/admin/login` : "/platform/login"} className="inline-flex items-center gap-1 font-medium text-[var(--brand)] hover:underline"><ArrowLeft size={15} aria-hidden />Back to sign in</Link>;
  if (sent) return <AuthShell icon={MailCheck} title="Check your email" subtitle="If an account exists for that address, a reset link has been sent. The link expires soon." footer={back}><p className="text-sm text-slate-500">Did not get it? Check your spam folder, or try again in a minute.</p></AuthShell>;
  return (
    <AuthShell icon={KeyRound} title="Reset your password" subtitle="Enter your email and we will send you a secure reset link." footer={back}>
      <form noValidate className="space-y-4" onSubmit={handleSubmit(async (v) => { await api("/auth/password-reset/", { method: "POST", body: v, tenant }).catch(() => {}); setSent(true); })}>
        <Field label="Email" icon={Mail} type="email" placeholder="you@example.com" error={errors.email?.message} {...register("email")} />
        <SubmitButton busy={isSubmitting} icon={Send}>Send reset link</SubmitButton>
      </form>
    </AuthShell>
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
      setTokens(r.tokens); setUser(await fetchMe(tenant)); nav("/dashboard");
    } catch (e) { setError(e instanceof ApiError ? e.message : "Something went wrong."); }
  };
  return (
    <AuthShell icon={mode === "reset" ? KeyRound : ShieldCheck} title={mode === "reset" ? "Choose a new password" : "Set your password"}
      subtitle={mode === "reset" ? "Pick a strong password you have not used elsewhere." : "Welcome! Create a password to activate your account."}>
      <form noValidate className="space-y-4" onSubmit={handleSubmit(submit)}>
        <Notice message={error} />
        <Field label="New password" icon={Lock} type="password" autoComplete="new-password" placeholder="Enter your new password" error={errors.new_password?.message} {...register("new_password")} />
        <PasswordRules value={watch("new_password")} />
        <Field label="Confirm password" icon={Lock} type="password" autoComplete="new-password" placeholder="Confirm your new password" error={errors.confirm?.message} {...register("confirm")} />
        <SubmitButton busy={isSubmitting} icon={ShieldCheck}>Save password</SubmitButton>
      </form>
    </AuthShell>
  );
}
export const ResetPassword = () => <TokenForm mode="reset" />;
export const AcceptInvitation = () => <TokenForm mode="invite" />;
