import { lazy, Suspense } from "react";
import { Route, Routes, useParams } from "react-router-dom";
import { Home } from "./pages/public/PublicPages";

const PP = (n: string) => lazy(() => import("./pages/public/PublicPages").then((m) => ({ default: (m as never as Record<string, React.ComponentType>)[n] })));
const Features = PP("Features"), Solutions = PP("Solutions"), Pricing = PP("Pricing"), About = PP("About"), Faq = PP("Faq"), Contact = PP("Contact"), Legal = PP("Legal");
const LoginPage = lazy(() => import("./pages/LoginPage"));
const ChangePasswordPage = lazy(() => import("./pages/ChangePasswordPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const AdminLayout = lazy(() => import("./pages/admin/AdminLayout"));
const DashboardAdmin = lazy(() => import("./pages/admin/DashboardAdmin"));
const Pharmacies = lazy(() => import("./pages/admin/Pharmacies"));
const PharmacyDetail = lazy(() => import("./pages/admin/PharmacyDetail"));
const Billing = lazy(() => import("./pages/admin/Billing"));
const AuditLog = lazy(() => import("./pages/admin/AuditLog"));
const TenantLayout = lazy(() => import("./pages/tenant/TenantLayout"));
const T = (n: string) => lazy(() => import("./pages/tenant/TenantPages").then((m) => ({ default: (m as never as Record<string, React.ComponentType>)[n] })));
const TenantDashboard = T("TenantDashboard"), Branches = T("Branches"), StaffPage = T("StaffPage"), RolesPage = T("RolesPage"), SettingsPage = T("SettingsPage");
const I = (n: string) => lazy(() => import("./pages/tenant/InventoryPages").then((m) => ({ default: (m as never as Record<string, React.ComponentType>)[n] })));
const MedicinesPage = I("MedicinesPage"), InventoryPage = I("InventoryPage");
const ProcurementPage = lazy(() => import("./pages/tenant/ProcurementPage"));
const PrescriptionsPage = lazy(() => import("./pages/tenant/PrescriptionsPage"));
const PosPage = lazy(() => import("./pages/tenant/PosPage"));
const SiteLayout = lazy(() => import("./pages/site/SiteLayout"));
const SP = (n: string) => lazy(() => import("./pages/site/SitePages").then((m) => ({ default: (m as never as Record<string, React.ComponentType>)[n] })));
const SiteHome = SP("SiteHome"), Products = SP("Products"), CustomerRegister = SP("CustomerRegister"), CustomerLogin = SP("CustomerLogin"), VerifyEmail = SP("VerifyEmail"), Checkout = SP("Checkout"), Orders = SP("Orders"), OrderDetail = SP("OrderDetail"), QrMenu = SP("QrMenu");
const StaffOrders = lazy(() => import("./pages/tenant/OrdersPage"));
const PaymentsPage = lazy(() => import("./pages/tenant/PaymentsPage"));
const AccountingPage = lazy(() => import("./pages/tenant/AccountingPage"));
const HP = (n: string) => lazy(() => import("./pages/tenant/HrPages").then((m) => ({ default: (m as never as Record<string, React.ComponentType>)[n] })));
const HrPage = HP("HrPage"), PayrollPage = HP("PayrollPage"), MyWorkPage = HP("MyWorkPage");
const RP = (n: string) => lazy(() => import("./pages/tenant/ReportsPage").then((m) => ({ default: (m as never as Record<string, React.ComponentType>)[n] })));
const OverviewPage = RP("OverviewPage"), ReportsPage = RP("ReportsPage");
const EP = (n: string) => lazy(() => import("./pages/tenant/EngagePages").then((m) => ({ default: (m as never as Record<string, React.ComponentType>)[n] })));
const EngagementPage = EP("EngagementPage"), DeliveriesPage = EP("DeliveriesPage");
const XP = (n: string) => lazy(() => import("./pages/site/SiteExtras").then((m) => ({ default: (m as never as Record<string, React.ComponentType>)[n] })));
const ServicesPage = XP("ServicesPage"), InstitutionalPage = XP("InstitutionalPage"), FeedbackPage = XP("FeedbackPage");
const Backups = lazy(() => import("./pages/admin/Backups"));
const ForgotPassword = lazy(() => import("./pages/PasswordPages").then((m) => ({ default: m.ForgotPassword })));
const ResetPassword = lazy(() => import("./pages/PasswordPages").then((m) => ({ default: m.ResetPassword })));
const AcceptInvitation = lazy(() => import("./pages/PasswordPages").then((m) => ({ default: m.AcceptInvitation })));

function TenantForgot() { const { slug } = useParams(); return <ForgotPassword tenant={slug} />; }
const Support = lazy(() => import("./pages/public/PublicPages").then((m) => ({ default: () => <m.Contact support /> })));

export default function App() {
  return (
    <Suspense fallback={<p className="p-8">Loading…</p>}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/features" element={<Features />} />
        <Route path="/solutions" element={<Solutions />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/about" element={<About />} />
        <Route path="/faq" element={<Faq />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/support" element={<Support />} />
        <Route path="/legal/:doc" element={<Legal />} />
        <Route path="/platform/login" element={<LoginPage />} />
        <Route path="/platform/forgot-password" element={<ForgotPassword />} />
        <Route path="/pharmacy/:slug/admin/login" element={<LoginPage />} />
        <Route path="/pharmacy/:slug/admin/forgot-password" element={<TenantForgot />} />
        <Route path="/pharmacy/:slug/admin" element={<TenantLayout />}>
          <Route path="dashboard" element={<TenantDashboard />} />
          <Route path="branches" element={<Branches />} />
          <Route path="staff" element={<StaffPage />} />
          <Route path="roles" element={<RolesPage />} />
          <Route path="medicines" element={<MedicinesPage />} />
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="procurement" element={<ProcurementPage />} />
          <Route path="prescriptions" element={<PrescriptionsPage />} />
          <Route path="pos" element={<PosPage />} />
          <Route path="orders" element={<StaffOrders />} />
          <Route path="payments" element={<PaymentsPage />} />
          <Route path="accounting" element={<AccountingPage />} />
          <Route path="hr" element={<HrPage />} />
          <Route path="payroll" element={<PayrollPage />} />
          <Route path="my-work" element={<MyWorkPage />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="engagement" element={<EngagementPage />} />
          <Route path="deliveries" element={<DeliveriesPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="/pharmacy/:slug" element={<SiteLayout />}>
          <Route index element={<SiteHome />} />
          <Route path="products" element={<Products />} />
          <Route path="register" element={<CustomerRegister />} />
          <Route path="login" element={<CustomerLogin />} />
          <Route path="verify" element={<VerifyEmail />} />
          <Route path="checkout" element={<Checkout />} />
          <Route path="services" element={<ServicesPage />} />
          <Route path="institutional" element={<InstitutionalPage />} />
          <Route path="feedback" element={<FeedbackPage />} />
          <Route path="orders" element={<Orders />} />
          <Route path="orders/:id" element={<OrderDetail />} />
          <Route path="menu/:token" element={<QrMenu />} />
        </Route>
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/accept-invitation" element={<AcceptInvitation />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/platform" element={<AdminLayout />}>
          <Route path="dashboard" element={<DashboardAdmin />} />
          <Route path="pharmacies" element={<Pharmacies />} />
          <Route path="pharmacies/:id" element={<PharmacyDetail />} />
          <Route path="billing" element={<Billing />} />
          <Route path="audit" element={<AuditLog />} />
          <Route path="backups" element={<Backups />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
