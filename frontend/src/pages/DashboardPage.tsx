import { Navigate } from "react-router-dom";
import { PageLoader } from "../components/brand/Brand";
import { useAuth } from "../lib/auth";
import { homeFor } from "../lib/site";

/** Generic post-sign-in address: sends each user to the right home for their account. */
export default function DashboardPage() {
  const { user, loading } = useAuth();
  if (loading) return <PageLoader />;
  return <Navigate to={user ? homeFor(user) : "/"} replace />;
}
