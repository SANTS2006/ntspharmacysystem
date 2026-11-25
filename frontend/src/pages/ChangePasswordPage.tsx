import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound, Lock, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { AuthShell, Field, Notice, PasswordRules, SubmitButton } from "../components/auth/AuthUi";
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
  const { register, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm<Form>({ resolver: zodResolver(schema) });
  const onSubmit = async (v: Form) => {
    try {
      await changePassword(v.old_password, v.new_password, slug);
      const me = await fetchMe(slug);
      setUser(me);
      nav(me.is_platform_admin ? "/platform/dashboard" : me.tenant_slug ? `/${me.tenant_slug}/admin/dashboard` : "/dashboard");
    } catch (e) {
      setError(e instanceof ApiError ? JSON.stringify(e.details ?? e.message) : "Something went wrong.");
    }
  };
  return (
    <AuthShell icon={KeyRound} title="Set a new password" subtitle="Your temporary password must be replaced before you continue.">
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
        <Notice message={error} />
        <Field label="Temporary password" icon={Lock} type="password" autoComplete="current-password" placeholder="Enter your temporary password" error={errors.old_password?.message} {...register("old_password")} />
        <Field label="New password" icon={Lock} type="password" autoComplete="new-password" placeholder="Enter your new password" error={errors.new_password?.message} {...register("new_password")} />
        <PasswordRules value={watch("new_password")} />
        <Field label="Confirm new password" icon={Lock} type="password" autoComplete="new-password" placeholder="Confirm your new password" error={errors.confirm?.message} {...register("confirm")} />
        <SubmitButton busy={isSubmitting} icon={ShieldCheck}>Update password</SubmitButton>
      </form>
    </AuthShell>
  );
}
