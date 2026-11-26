import { useQuery } from "@tanstack/react-query";
import { Banknote, BarChart3, Boxes, Briefcase, Building2, Calculator, CalendarClock, CreditCard, FileBarChart, HeartHandshake, LayoutDashboard, Package, Pill, Receipt, ScrollText, Settings, Shield, ShoppingCart, Truck, Users } from "lucide-react";
import { useEffect } from "react";
import { Navigate, Outlet, useParams } from "react-router-dom";
import { AppShell, type NavGroup, type Notification } from "../../components/layout/AppShell";
import { Loading } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useRealtime } from "../../lib/realtime";

export interface Branding { name: string; primary_color: string; secondary_color: string; logo: string | null }
interface Alerts { low_stock: unknown[]; out_of_stock: unknown[]; near_expiry: unknown[]; expired: unknown[] }

/** Staff area. The shell uses the NTS design system; the pharmacy's name and logo identify the tenant
 *  (its brand colours apply to its public website). */
export default function TenantLayout() {
  const { slug } = useParams();
  const { user, loading, signOut } = useAuth();
  const brand = useQuery({ queryKey: ["branding", slug], queryFn: () => api<Branding>(`/public/pharmacies/${slug}/`), enabled: !!slug });
  const signedIn = !!user && !user.is_platform_admin && user.tenant_slug === slug && !user.must_change_password;
  // Real stock alerts for the bell; only requested for users the API allows to see them. Shares the "alerts" cache key with the Inventory page.
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api<Alerts>("/inventory/alerts/"), enabled: signedIn && !!user?.permissions.includes("inventory.view"), staleTime: 60_000, retry: false });
  useRealtime(!!user && !user.is_platform_admin && user.tenant_slug === slug);
  useEffect(() => () => { document.title = "NTS Pharmacy System"; }, []);
  if (loading) return <div className="p-8"><Loading /></div>;
  if (!user || user.is_platform_admin || user.tenant_slug !== slug) return <Navigate to={`/${slug}/admin/login`} replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace state={{ slug }} />;
  const can = (p: string) => user.permissions.includes(p); // UI hint only; the API enforces permissions
  const base = `/${slug}/admin`;
  const item = (to: string, label: string, icon: typeof Pill, show: boolean, keywords?: string) => ({ to: `${base}/${to}`, label, icon, show, keywords });
  const groups: NavGroup[] = [
    { label: "Home", items: [
      item("dashboard", "Dashboard", LayoutDashboard, true),
      item("overview", "Business overview", BarChart3, can("report.view"), "analytics revenue profit charts"),
      item("my-work", "My work", CalendarClock, !!user.role && user.role !== "customer", "attendance leave payslips shifts")] },
    { label: "Sales", items: [
      item("pos", "Point of sale", Receipt, can("pos.sell") || can("sales.view_branch"), "pos checkout receipts transactions refunds"),
      item("orders", "Online orders", Package, can("order.manage")),
      item("payments", "Online payments", CreditCard, can("settings.manage") || can("accounting.view"), "monime refunds"),
      item("deliveries", "Deliveries", Truck, can("delivery.manage") || can("delivery.perform"))] },
    { label: "Pharmacy", items: [
      item("prescriptions", "Prescriptions", ScrollText, can("prescription.view"), "patients dispensing"),
      item("medicines", "Medicines", Pill, can("medicine.view"), "catalogue categories barcode"),
      item("inventory", "Inventory", Boxes, can("inventory.view"), "stock batches expiry movements"),
      item("procurement", "Suppliers & purchases", ShoppingCart, can("procurement.view"), "purchase orders procurement")] },
    { label: "Customers", items: [item("engagement", "Customers & services", HeartHandshake, can("engagement.manage"), "appointments feedback inquiries")] },
    { label: "Finance & reports", items: [
      item("accounting", "Accounting", Calculator, can("accounting.view") || (can("report.view") && !!user.branch), "expenses ledger"),
      item("reports", "Reports", FileBarChart, can("report.view") || can("accounting.view") || can("hr.view") || can("payroll.view"), "export"),
      item("payroll", "Payroll", Banknote, can("payroll.view"))] },
    { label: "Administration", items: [
      item("hr", "Human resources", Briefcase, can("hr.view")),
      item("staff", "Staff", Users, can("staff.view"), "users"),
      item("roles", "Roles & permissions", Shield, can("staff.view")),
      item("branches", "Branches", Building2, can("branch.view")),
      item("settings", "Settings", Settings, can("settings.manage"), "branding profile")] },
  ].map((g) => ({ label: g.label, items: g.items.filter((i) => i.show) })).filter((g) => g.items.length > 0);
  const a = alerts.data;
  const notifications: Notification[] | undefined = a ? [
    { id: "expired", label: "Expired batches", count: a.expired.length, to: `${base}/inventory`, tone: "danger" },
    { id: "out", label: "Out of stock", count: a.out_of_stock.length, to: `${base}/inventory`, tone: "danger" },
    { id: "low", label: "Low stock", count: a.low_stock.length, to: `${base}/inventory`, tone: "warning" },
    { id: "near", label: "Expiring soon", count: a.near_expiry.length, to: `${base}/inventory`, tone: "warning" },
  ] : undefined;
  return (
    <AppShell groups={groups} navLabel="Pharmacy" brandName={brand.data?.name ?? "Pharmacy"} brandCaption="NTS Pharmacy System" logo={brand.data?.logo}
      user={{ name: user.full_name, role: user.role ?? "staff" }} onSignOut={signOut} notifications={notifications}>
      <Outlet />
    </AppShell>
  );
}
