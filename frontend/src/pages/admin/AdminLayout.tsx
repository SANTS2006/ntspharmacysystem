import { DatabaseBackup, LayoutDashboard, Receipt, ScrollText, Store } from "lucide-react";
import { Navigate, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../../lib/auth";

const items = [
  { to: "/platform/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/platform/pharmacies", label: "Pharmacies", icon: Store },
  { to: "/platform/billing", label: "Billing", icon: Receipt },
  { to: "/platform/audit", label: "Audit log", icon: ScrollText },
  { to: "/platform/backups", label: "Backups", icon: DatabaseBackup },
];

/** UI guard only. Every API call is independently authorised by the backend. */
export default function AdminLayout() {
  const { user, loading, signOut } = useAuth();
  if (loading) return <p className="p-8">Loading…</p>;
  if (!user || !user.is_platform_admin) return <Navigate to="/platform/login" replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b bg-slate-900 p-4 text-white md:w-56 md:border-b-0">
        <p className="mb-4 flex items-center gap-2 text-lg font-bold"><img src="/logo.webp" alt="" className="h-8 w-8 rounded bg-white p-0.5" />PharmaCloud</p>
        <nav aria-label="Platform" className="flex gap-2 md:flex-col">
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => `flex items-center gap-2 rounded px-3 py-2 text-sm ${isActive ? "bg-teal-700" : "hover:bg-slate-800"}`}>
              <Icon size={16} aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>
        <button onClick={signOut} className="mt-4 text-sm text-slate-300 underline">Sign out</button>
      </aside>
      <main className="flex-1 bg-slate-50 p-4 md:p-8"><Outlet /></main>
    </div>
  );
}
