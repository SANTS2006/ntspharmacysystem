import { useQuery } from "@tanstack/react-query";
import { Boxes, Building2, LayoutDashboard, BarChart3, Banknote, Briefcase, HeartHandshake, Truck, CalendarClock, Calculator, CreditCard, Package, Pill, Receipt, ScrollText, Settings, Shield, ShoppingCart, Users } from "lucide-react";
import { useEffect } from "react";
import { Navigate, NavLink, Outlet, useParams } from "react-router-dom";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useRealtime } from "../../lib/realtime";

export interface Branding { name: string; primary_color: string; secondary_color: string; logo: string | null }

/** Applies the pharmacy's configured brand colours to the whole admin UI via CSS variables. */
export default function TenantLayout() {
  const { slug } = useParams();
  const { user, loading, signOut } = useAuth();
  const brand = useQuery({ queryKey: ["branding", slug], queryFn: () => api<Branding>(`/public/pharmacies/${slug}/`), enabled: !!slug });
  useEffect(() => {
    if (brand.data) document.documentElement.style.setProperty("--brand", brand.data.primary_color);
    return () => { document.documentElement.style.setProperty("--brand", "#015dc9"); };
  }, [brand.data]);
  useRealtime(!!user && !user.is_platform_admin && user.tenant_slug === slug);
  if (loading) return <p className="p-8">Loading…</p>;
  if (!user || user.is_platform_admin || user.tenant_slug !== slug) return <Navigate to={`/${slug}/admin/login`} replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace state={{ slug }} />;
  const can = (p: string) => user.permissions.includes(p); // UI hint only; the API enforces permissions
  const items = [
    { to: "dashboard", label: "Dashboard", icon: LayoutDashboard, show: true },
    { to: "medicines", label: "Medicines", icon: Pill, show: can("medicine.view") },
    { to: "inventory", label: "Inventory", icon: Boxes, show: can("inventory.view") },
    { to: "procurement", label: "Procurement", icon: ShoppingCart, show: can("procurement.view") },
    { to: "prescriptions", label: "Prescriptions", icon: ScrollText, show: can("prescription.view") },
    { to: "pos", label: "Point of sale", icon: Receipt, show: can("pos.sell") || can("sales.view_branch") },
    { to: "orders", label: "Online orders", icon: Package, show: can("order.manage") },
    { to: "payments", label: "Online payments", icon: CreditCard, show: can("settings.manage") || can("accounting.view") },
    { to: "accounting", label: "Accounting", icon: Calculator, show: can("accounting.view") || (can("report.view") && !!user.branch) },
    { to: "overview", label: "Overview", icon: BarChart3, show: can("report.view") },
    { to: "reports", label: "Reports", icon: BarChart3, show: can("report.view") || can("accounting.view") || can("hr.view") || can("payroll.view") },
    { to: "engagement", label: "Customers & services", icon: HeartHandshake, show: can("engagement.manage") },
    { to: "deliveries", label: "Deliveries", icon: Truck, show: can("delivery.manage") || can("delivery.perform") },
    { to: "my-work", label: "My work", icon: CalendarClock, show: !!user.role && user.role !== "customer" },
    { to: "hr", label: "Human resources", icon: Briefcase, show: can("hr.view") },
    { to: "payroll", label: "Payroll", icon: Banknote, show: can("payroll.view") },
    { to: "branches", label: "Branches", icon: Building2, show: can("branch.view") },
    { to: "staff", label: "Staff", icon: Users, show: can("staff.view") },
    { to: "roles", label: "Roles", icon: Shield, show: can("staff.view") },
    { to: "settings", label: "Settings", icon: Settings, show: can("settings.manage") },
  ].filter((i) => i.show);
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="p-4 text-white md:w-56" style={{ background: "var(--brand)" }}>
        <p className="mb-4 text-lg font-bold">{brand.data?.name ?? "Pharmacy"}</p>
        <nav aria-label="Pharmacy" className="flex gap-2 md:flex-col">
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={`/${slug}/admin/${to}`} className={({ isActive }) => `flex items-center gap-2 rounded px-3 py-2 text-sm ${isActive ? "bg-black/25" : "hover:bg-black/15"}`}>
              <Icon size={16} aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>
        <p className="mt-6 text-xs opacity-80">{user.full_name}<br />{user.role}</p>
        <button onClick={signOut} className="mt-2 text-sm underline">Sign out</button>
      </aside>
      <main className="flex-1 bg-slate-50 p-4 md:p-8"><Outlet /></main>
    </div>
  );
}
