import { Navigate } from "react-router-dom";
import { Loading } from "../components/ui";
import { useAuth } from "../lib/auth";

/** Generic post-sign-in address: sends each user to the right home for their account. */
export default function DashboardPage() {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-8"><Loading /></div>;
  if (!user) return <Navigate to="/" replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  if (user.is_platform_admin) return <Navigate to="/platform/dashboard" replace />;
  if (!user.tenant_slug) return <Navigate to="/" replace />;
  return <Navigate to={user.role === "customer" ? `/${user.tenant_slug}` : `/${user.tenant_slug}/admin/dashboard`} replace />;
}
