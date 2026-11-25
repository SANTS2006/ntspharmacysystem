import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { ApiError, api, fetchMe, setTokens } from "../lib/api";
import { useAuth } from "../lib/auth";

const Shell = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <main className="grid min-h-screen place-items-center bg-slate-50 p-4">
    <div className="w-full max-w-md space-y-4 rounded-2xl bg-white p-8 shadow"><h1 className="text-2xl font-semibold">{title}</h1>{children}</div>
  </main>
);
const strong = z.string().min(10, "Use at least 10 characters.").regex(/[A-Za-z]/, "Include a letter.").regex(/\d/, "Include a number.");

export function ForgotPassword({ tenant }: { tenant?: string }) {
  const [sent, setSent] = useState(false);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<{ email: string }>({ resolver: zodResolver(z.object({ email: z.string().email("Enter a valid email address.") })) });
  if (sent) return <Shell title="Check your email"><p>If an account exists for that address, a reset link has been sent.</p></Shell>;
  return (
    <Shell title="Reset your password">
      <form noValidate className="space-y-4" onSubmit={handleSubmit(async (v) => { await api("/auth/password-reset/", { method: "POST", body: v, tenant }).catch(() => {}); setSent(true); })}>
        <label className="block text-sm font-medium">Email <span aria-hidden className="text-red-600">*</span>
          <input type="email" placeholder="Enter your email address" className="mt-1 w-full rounded border p-2" {...register("email")} />
          {errors.email && <span role="alert" className="text-xs text-red-600">{errors.email.message}</span>}</label>
        <button disabled={isSubmitting} className="w-full rounded bg-teal-700 p-2 text-white">Send reset link</button>
      </form>
    </Shell>
  );
}

const resetSchema = z.object({ new_password: strong, confirm: z.string() }).refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });

function TokenForm({ mode }: { mode: "reset" | "invite" }) {
  const [sp] = useSearchParams(); const nav = useNavigate(); const { setUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof resetSchema>>({ resolver: zodResolver(resetSchema) });
  const tenant = sp.get("tenant") ?? undefined;
  const submit = async (v: z.infer<typeof resetSchema>) => {
    try {
      const body = mode === "reset" ? { uid: sp.get("uid"), token: sp.get("token"), new_password: v.new_password } : { token: sp.get("token"), new_password: v.new_password };
      const r = await api<{ tokens: { access: string; refresh: string } }>(mode === "reset" ? "/auth/password-reset/confirm/" : "/auth/accept-invitation/", { method: "POST", body, tenant, retry: false });
      setTokens(r.tokens); setUser(await fetchMe(tenant)); nav("/dashboard");
    } catch (e) { setError(e instanceof ApiError ? e.message : "Something went wrong."); }
  };
  return (
    <Shell title={mode === "reset" ? "Choose a new password" : "Set your password"}>
      <form noValidate className="space-y-4" onSubmit={handleSubmit(submit)}>
        {error && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">{error} <Link to="/" className="underline">Home</Link></p>}
        <label className="block text-sm font-medium">New password <span aria-hidden className="text-red-600">*</span>
          <input type="password" autoComplete="new-password" placeholder="Enter your new password" className="mt-1 w-full rounded border p-2" {...register("new_password")} />
          {errors.new_password && <span role="alert" className="text-xs text-red-600">{errors.new_password.message}</span>}</label>
        <label className="block text-sm font-medium">Confirm password <span aria-hidden className="text-red-600">*</span>
          <input type="password" autoComplete="new-password" placeholder="Confirm your new password" className="mt-1 w-full rounded border p-2" {...register("confirm")} />
          {errors.confirm && <span role="alert" className="text-xs text-red-600">{errors.confirm.message}</span>}</label>
        <button disabled={isSubmitting} className="w-full rounded bg-teal-700 p-2 text-white">Save password</button>
      </form>
    </Shell>
  );
}
export const ResetPassword = () => <TokenForm mode="reset" />;
export const AcceptInvitation = () => <TokenForm mode="invite" />;
