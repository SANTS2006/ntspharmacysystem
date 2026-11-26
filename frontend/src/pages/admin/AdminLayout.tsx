import { DatabaseBackup, LayoutDashboard, Receipt, ScrollText, Store } from "lucide-react";
import { Navigate, Outlet } from "react-router-dom";
import { PLATFORM_BRAND, PageLoader } from "../../components/brand/Brand";
import { AppShell, type NavGroup } from "../../components/layout/AppShell";
import { useAuth } from "../../lib/auth";

const groups: NavGroup[] = [
  { label: "Overview", items: [{ to: "/platform/dashboard", label: "Dashboard", icon: LayoutDashboard }] },
  { label: "Tenants", items: [
    { to: "/platform/pharmacies", label: "Pharmacies", icon: Store, keywords: "register tenants" },
    { to: "/platform/billing", label: "Billing", icon: Receipt, keywords: "invoices plans revenue" }] },
  { label: "System", items: [
    { to: "/platform/audit", label: "Audit log", icon: ScrollText },
    { to: "/platform/backups", label: "Backups", icon: DatabaseBackup, keywords: "restore" }] },
];

/** UI guard only. Every API call is independently authorised by the backend. */
export default function AdminLayout() {
  const { user, loading } = useAuth();
  if (loading) return <PageLoader label="Opening platform administration…" />;
  if (!user || !user.is_platform_admin) return <Navigate to="/platform/login" replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  return (
    <AppShell groups={groups} navLabel="Platform" brand={PLATFORM_BRAND} brandCaption="Platform administration" base="/platform" roleLabel="Platform admin">
      <Outlet />
    </AppShell>
  );
}
