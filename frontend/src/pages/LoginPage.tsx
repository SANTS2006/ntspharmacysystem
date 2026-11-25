import { zodResolver } from "@hookform/resolvers/zod";
import { LogIn } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { ApiError, login } from "../lib/api";
import { useAuth } from "../lib/auth";

const schema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
type Form = z.infer<typeof schema>;

/** Used for the platform login (/platform/login) and pharmacy login (/pharmacy/:slug/admin/login). */
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
      nav(user.must_change_password ? "/change-password" : user.is_platform_admin ? "/platform/dashboard" : user.tenant_slug ? `/pharmacy/${user.tenant_slug}/admin/dashboard` : "/dashboard", { state: { slug } });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
    }
  };
  return (
    <main className="min-h-screen grid place-items-center bg-slate-50 p-4">
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="w-full max-w-md space-y-4 rounded-2xl bg-white p-8 shadow">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><LogIn aria-hidden /> {slug ? "Pharmacy sign in" : "Platform sign in"}</h1>
        {error && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <label className="block text-sm font-medium">Email <span aria-hidden className="text-red-600">*</span>
          <input type="email" autoComplete="username" placeholder="Enter your email address" className="mt-1 w-full rounded border p-2" aria-invalid={!!errors.email} {...register("email")} />
          {errors.email && <span role="alert" className="text-xs text-red-600">{errors.email.message}</span>}
        </label>
        <label className="block text-sm font-medium">Password <span aria-hidden className="text-red-600">*</span>
          <input type="password" autoComplete="current-password" placeholder="Enter your password" className="mt-1 w-full rounded border p-2" aria-invalid={!!errors.password} {...register("password")} />
          {errors.password && <span role="alert" className="text-xs text-red-600">{errors.password.message}</span>}
        </label>
        <button disabled={isSubmitting} className="w-full rounded bg-teal-700 p-2 font-medium text-white disabled:opacity-60">{isSubmitting ? "Signing in…" : "Sign in"}</button>
      </form>
    </main>
  );
}
