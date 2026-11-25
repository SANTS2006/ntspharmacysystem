import { Navigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

/** Phase 1 placeholder proving authenticated routing. Real dashboards arrive in Phases 2-3. */
export default function DashboardPage() {
  const { user, loading, signOut } = useAuth();
  if (loading) return <p className="p-8">Loading…</p>;
  if (!user) return <Navigate to="/" replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">Welcome, {user.full_name}</h1>
      <p className="text-slate-600">{user.is_platform_admin ? "Platform administrator" : `Role: ${user.role}`}</p>
      <button onClick={signOut} className="mt-4 rounded border px-3 py-1">Sign out</button>
    </main>
  );
}
