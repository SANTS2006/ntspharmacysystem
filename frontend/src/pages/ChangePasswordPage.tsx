import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { ApiError, changePassword, fetchMe } from "../lib/api";
import { useAuth } from "../lib/auth";

const schema = z.object({
  old_password: z.string().min(1, "Enter your current password."),
  new_password: z.string().min(10, "Use at least 10 characters.").regex(/[A-Za-z]/, "Include a letter.").regex(/\d/, "Include a number."),
  confirm: z.string(),
}).refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });
type Form = z.infer<typeof schema>;

export default function ChangePasswordPage() {
  const nav = useNavigate();
  const slug = (useLocation().state as { slug?: string } | null)?.slug;
  const { setUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Form>({ resolver: zodResolver(schema) });
  const onSubmit = async (v: Form) => {
    try {
      await changePassword(v.old_password, v.new_password, slug);
      const me = await fetchMe(slug);
      setUser(me);
      nav(me.is_platform_admin ? "/platform/dashboard" : me.tenant_slug ? `/pharmacy/${me.tenant_slug}/admin/dashboard` : "/dashboard");
    } catch (e) {
      setError(e instanceof ApiError ? JSON.stringify(e.details ?? e.message) : "Something went wrong.");
    }
  };
  const field = (name: keyof Form, label: string, ph: string) => (
    <label className="block text-sm font-medium">{label} <span aria-hidden className="text-red-600">*</span>
      <input type="password" placeholder={ph} className="mt-1 w-full rounded border p-2" {...register(name)} />
      {errors[name] && <span role="alert" className="text-xs text-red-600">{errors[name]?.message}</span>}
    </label>
  );
  return (
    <main className="min-h-screen grid place-items-center bg-slate-50 p-4">
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="w-full max-w-md space-y-4 rounded-2xl bg-white p-8 shadow">
        <h1 className="text-2xl font-semibold">Set a new password</h1>
        <p className="text-sm text-slate-600">Your temporary password must be replaced before you continue.</p>
        {error && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        {field("old_password", "Temporary password", "Enter your temporary password")}
        {field("new_password", "New password", "Enter your new password")}
        {field("confirm", "Confirm new password", "Confirm your new password")}
        <button disabled={isSubmitting} className="w-full rounded bg-teal-700 p-2 font-medium text-white disabled:opacity-60">Update password</button>
      </form>
    </main>
  );
}
