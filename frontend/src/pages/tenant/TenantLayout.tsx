import { Banknote, BadgeCheck, Boxes, Briefcase, Building2, Calculator, CalendarClock, CreditCard, FileBarChart, HeartHandshake, LayoutDashboard, Package, Pill, Receipt, ScrollText, Shield, ShoppingCart, Store, Truck, UserRound, Users, Globe, Inbox, type LucideIcon } from "lucide-react";
import { Navigate, Outlet, useLocation, useParams } from "react-router-dom";
import { PageLoader } from "../../components/brand/Brand";
import { AppShell, type NavGroup } from "../../components/layout/AppShell";
import { PharmacyNotFound, SystemNotFound } from "../../components/NotFound";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { brandOf, useSiteQuery } from "../../lib/site";
import { MODULE_ACCESS, allowed, type Module } from "./access";

/** Staff area, in the pharmacy's own brand. Modules a role cannot use are not listed, and their addresses redirect away. */
export default function TenantLayout() {
  const params = useParams();
  const slug = params.slug ?? "";
  const unknown = params["*"] !== undefined; // only the catch-all route sets this
  const { pathname, search } = useLocation();
  const { user, loading } = useAuth();
  const site = useSiteQuery(slug);
  if (loading || site.isLoading) return <PageLoader label="Opening your workspace…" brand={brandOf(site.data)} />;
  if (site.error instanceof ApiError && site.error.status === 404) return <SystemNotFound />;
  if (unknown && (!user || user.tenant_slug !== slug || user.role === "customer")) return <PharmacyNotFound />;
  if (!user || user.is_platform_admin || user.tenant_slug !== slug) return <Navigate to={`/${slug}/login`} replace />;
  if (user.role === "customer") return <Navigate to={`/${slug}/account/dashboard`} replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace state={{ slug }} />;
  const base = `/${slug}/admin`;
  const segment = pathname.slice(base.length + 1).split("/")[0] as Module;
  if (segment in MODULE_ACCESS && !allowed(user, segment)) return <Navigate to={`${base}/dashboard${search}`} replace />;
  const item = (module: Module, label: string, icon: LucideIcon, keywords?: string) => ({ module, to: `${base}/${module}`, label, icon, keywords });
  const groups: NavGroup[] = [
    { label: "Home", items: [item("dashboard", "Dashboard", LayoutDashboard, "analytics overview charts"), item("my-work", "My work", CalendarClock, "attendance leave payslips shifts")] },
    { label: "Sales", items: [item("pos", "Point of sale", Receipt, "pos checkout receipts transactions refunds"), item("orders", "Online orders", Package), item("payments", "Online payments", CreditCard, "monime mobile money refunds"), item("deliveries", "Deliveries", Truck)] },
    { label: "Pharmacy", items: [item("prescriptions", "Prescriptions", ScrollText, "patients dispensing"), item("medicines", "Medicines", Pill, "catalogue categories barcode"), item("inventory", "Inventory", Boxes, "stock batches expiry movements"), item("procurement", "Suppliers & purchases", ShoppingCart, "purchase orders procurement")] },
    { label: "Customers", items: [item("customers", "Customers", UserRound, "registered profiles"), item("engagement", "Customer services", HeartHandshake, "appointments feedback enquiries"), item("website-contact", "Website contact", Inbox, "contact form messages")] },
    { label: "Finance & reports", items: [item("accounting", "Accounting", Calculator, "expenses ledger"), item("reports", "Reports", FileBarChart, "export"), item("payroll", "Payroll", Banknote)] },
    { label: "Administration", items: [item("hr", "Human resources", Briefcase), item("staff", "Staff", Users, "users"), item("roles", "Roles & permissions", Shield), item("branches", "Branches", Building2), item("pharmacy-settings", "Pharmacy settings", Store, "branding logo colours profile"), item("website", "Website content", Globe, "website builder pages hero footer"), item("subscription", "Subscription", BadgeCheck, "plan invoices billing")] },
  ].map((g) => ({ label: g.label, items: (g.items as ReturnType<typeof item>[]).filter((i) => allowed(user, i.module)) })).filter((g) => g.items.length > 0);
  return (
    <AppShell groups={groups} navLabel="Pharmacy" brand={brandOf(site.data)} brandCaption="Staff workspace" base={base} roleLabel={user.role_name ?? "Staff"}>
      <Outlet />
    </AppShell>
  );
}
