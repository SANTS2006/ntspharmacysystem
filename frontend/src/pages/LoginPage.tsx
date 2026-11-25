import { zodResolver } from "@hookform/resolvers/zod";
import { Lock, LogIn, Mail } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { AuthShell, Field, Notice, SubmitButton } from "../components/auth/AuthUi";
import { ApiError, login } from "../lib/api";
import { useAuth } from "../lib/auth";

const schema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
type Form = z.infer<typeof schema>;

/** Used for the platform login (/platform/login) and pharmacy staff login (/:slug/admin/login). */
export default function LoginPage() {
  const { slug } = useParams();
  const nav = useNavigate();
  const { setUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Form>({ resolver: zodResolver(schema) });
  const onSubmit = async (v: Form) => {
    setError(null);
    try {
      const user = await login(v.email, v.password, slug);
      setUser(user);
      nav(user.must_change_password ? "/change-password" : user.is_platform_admin ? "/platform/dashboard" : user.tenant_slug ? `/${user.tenant_slug}/admin/dashboard` : "/dashboard", { state: { slug } });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
    }
  };
  return (
    <AuthShell icon={LogIn} title={slug ? "Pharmacy sign in" : "Platform sign in"} subtitle={slug ? "Welcome back. Sign in to manage your pharmacy." : "Sign in to the platform administration."}
      footer={<Link className="font-medium text-[var(--brand)] hover:underline" to={slug ? `/${slug}/admin/forgot-password` : "/platform/forgot-password"}>Forgot your password?</Link>}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
        <Notice message={error} />
        <Field label="Email" icon={Mail} type="email" autoComplete="username" placeholder="you@example.com" error={errors.email?.message} {...register("email")} />
        <Field label="Password" icon={Lock} type="password" autoComplete="current-password" placeholder="Enter your password" error={errors.password?.message} {...register("password")} />
        <SubmitButton busy={isSubmitting} icon={LogIn}>{isSubmitting ? "Signing in…" : "Sign in"}</SubmitButton>
      </form>
    </AuthShell>
  );
}
