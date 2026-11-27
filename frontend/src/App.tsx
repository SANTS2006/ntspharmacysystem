import { lazy, Suspense, type ComponentType } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import { PageLoader } from "./components/brand/Brand";
import { ShellNotFound, SystemNotFound } from "./components/NotFound";
import { Home } from "./pages/public/PublicPages";

/** Lazy-load one named export of a module, so each area is downloaded only when it is opened. */
const named = <M extends object>(load: () => Promise<M>, name: keyof M) => lazy(() => load().then((m) => ({ default: m[name] as unknown as ComponentType })));

const pub = () => import("./pages/public/PublicPages");
const Features = named(pub, "Features"), Solutions = named(pub, "Solutions"), Pricing = named(pub, "Pricing"), About = named(pub, "About"), Faq = named(pub, "Faq"), Legal = named(pub, "Legal"), Contact = named(pub, "Contact");
const Support = lazy(() => pub().then((m) => ({ default: () => <m.Contact support /> })));
const auth = () => import("./pages/auth/AuthPages");
const LoginPage = named(auth, "LoginPage"), RegisterPage = named(auth, "RegisterPage"), VerifyEmailPage = named(auth, "VerifyEmailPage"), ForgotPasswordPage = named(auth, "ForgotPasswordPage"), ResetPasswordPage = named(auth, "ResetPasswordPage"), AcceptInvitationPage = named(auth, "AcceptInvitationPage"), ChangePasswordPage = named(auth, "ChangePasswordPage");
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const AccountSettings = lazy(() => import("./pages/account/AccountSettings"));

type Area = "admin" | "account" | "platform";
function useBase(area: Area) { const { slug } = useParams(); return area === "platform" ? "/platform" : `/${slug}/${area}`; }
const notes = () => import("./pages/account/Notifications");
const Notes = lazy(() => notes().then((m) => ({ default: function Notes({ area }: { area: Area }) { return <m.NotificationsPage base={useBase(area)} />; } })));
const NoteDetail = lazy(() => notes().then((m) => ({ default: function NoteDetail({ area }: { area: Area }) { return <m.NotificationDetail base={useBase(area)} />; } })));

const AdminLayout = lazy(() => import("./pages/admin/AdminLayout"));
const DashboardAdmin = lazy(() => import("./pages/admin/DashboardAdmin"));
const Pharmacies = lazy(() => import("./pages/admin/Pharmacies"));
const PharmacyDetail = lazy(() => import("./pages/admin/PharmacyDetail"));
const Billing = lazy(() => import("./pages/admin/Billing"));
const AuditLog = lazy(() => import("./pages/admin/AuditLog"));
const Backups = lazy(() => import("./pages/admin/Backups"));

const TenantLayout = lazy(() => import("./pages/tenant/TenantLayout"));
const TenantDashboard = lazy(() => import("./pages/tenant/DashboardHome"));
const tp = () => import("./pages/tenant/TenantPages");
const Branches = named(tp, "Branches"), StaffPage = named(tp, "StaffPage"), RolesPage = named(tp, "RolesPage"), PharmacySettings = named(tp, "SettingsPage");
const inv = () => import("./pages/tenant/InventoryPages");
const MedicinesPage = named(inv, "MedicinesPage"), InventoryPage = named(inv, "InventoryPage");
const ProcurementPage = lazy(() => import("./pages/tenant/ProcurementPage"));
const rx = () => import("./pages/tenant/PrescriptionsPage");
const PrescriptionsPage = lazy(rx), PrescriptionDetail = named(rx, "PrescriptionDetail");
const PosPage = lazy(() => import("./pages/tenant/PosPage"));
const ord = () => import("./pages/tenant/OrdersPage");
const StaffOrders = lazy(ord), OrderDetailPage = named(ord, "OrderDetailPage");
const PaymentsPage = lazy(() => import("./pages/tenant/PaymentsPage"));
const AccountingPage = lazy(() => import("./pages/tenant/AccountingPage"));
const hr = () => import("./pages/tenant/HrPages");
const HrPage = named(hr, "HrPage"), PayrollPage = named(hr, "PayrollPage"), MyWorkPage = named(hr, "MyWorkPage");
const ReportsPage = named(() => import("./pages/tenant/ReportsPage"), "ReportsPage");
const ep = () => import("./pages/tenant/EngagePages");
const EngagementPage = named(ep, "EngagementPage"), DeliveriesPage = named(ep, "DeliveriesPage");
const cust = () => import("./pages/tenant/CustomersPage");
const CustomersPage = lazy(cust), CustomerDetailPage = named(cust, "CustomerDetailPage");
const SubscriptionPage = lazy(() => import("./pages/tenant/SubscriptionPage"));

const WebsiteBuilder = lazy(() => import("./pages/website/WebsiteBuilder"));
const WebsiteMessages = lazy(() => import("./pages/website/WebsiteMessages"));

const portal = () => import("./pages/customer/CustomerPortal");
const CustomerLayout = lazy(portal);
const CustomerDashboard = named(portal, "CustomerDashboard"), MyOrders = named(portal, "MyOrders"), CustomerOrderDetail = named(portal, "CustomerOrderDetail"), MyPayments = named(portal, "MyPayments"), CustomerCare = named(portal, "CustomerCare");

const SiteLayout = lazy(() => import("./pages/site/SiteLayout"));
const sp = () => import("./pages/site/SitePages");
const SiteNotFoundPage = named(() => import("./pages/site/SiteLayout"), "SiteNotFoundPage");
const SiteAbout = named(sp, "SiteAbout"), SiteContact = named(sp, "SiteContact");
const SiteHome = named(sp, "SiteHome"), Products = named(sp, "Products"), Checkout = named(sp, "Checkout"), QrMenu = named(sp, "QrMenu");
const xp = () => import("./pages/site/SiteExtras");
const ServicesPage = named(xp, "ServicesPage"), InstitutionalPage = named(xp, "InstitutionalPage");

/** Older addresses (including links already sent by email) keep working: they move to the new place with their query string. */
function Moved({ to }: { to: string }) {
  const params = useParams(); const { search } = useLocation();
  const target = to.replace(/:(\w+)/g, (_, k: string) => params[k] ?? "");
  return <Navigate to={`${target}${search}`} replace />;
}

export default function App() {
  return (
    <Suspense fallback={<PageLoader label="Loading…" />}>
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
        <Route path="/platform/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/accept-invitation" element={<AcceptInvitationPage />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />

        {/* One sign-in per pharmacy, for staff and customers alike */}
        <Route path="/:slug/login" element={<LoginPage />} />
        <Route path="/:slug/register" element={<RegisterPage />} />
        <Route path="/:slug/verify" element={<VerifyEmailPage />} />
        <Route path="/:slug/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/:slug/admin/login" element={<Moved to="/:slug/login" />} />
        <Route path="/:slug/admin/forgot-password" element={<Moved to="/:slug/forgot-password" />} />

        <Route path="/:slug/admin" element={<TenantLayout />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<TenantDashboard />} />
          <Route path="overview" element={<Moved to="/:slug/admin/dashboard" />} />
          <Route path="branches" element={<Branches />} />
          <Route path="staff" element={<StaffPage />} />
          <Route path="roles" element={<RolesPage />} />
          <Route path="medicines" element={<MedicinesPage />} />
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="procurement" element={<ProcurementPage />} />
          <Route path="prescriptions" element={<PrescriptionsPage />} />
          <Route path="prescriptions/:rxId" element={<PrescriptionDetail />} />
          <Route path="pos" element={<PosPage />} />
          <Route path="orders" element={<StaffOrders />} />
          <Route path="orders/:orderId" element={<OrderDetailPage />} />
          <Route path="payments" element={<PaymentsPage />} />
          <Route path="accounting" element={<AccountingPage />} />
          <Route path="hr" element={<HrPage />} />
          <Route path="payroll" element={<PayrollPage />} />
          <Route path="my-work" element={<MyWorkPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="engagement" element={<EngagementPage />} />
          <Route path="deliveries" element={<DeliveriesPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="customers/:customerId" element={<CustomerDetailPage />} />
          <Route path="pharmacy-settings" element={<PharmacySettings />} />
          <Route path="subscription" element={<SubscriptionPage />} />
          <Route path="website" element={<WebsiteBuilder />} />
          <Route path="website-contact" element={<WebsiteMessages />} />
          <Route path="settings" element={<AccountSettings />} />
          <Route path="notifications" element={<Notes area="admin" />} />
          <Route path="notifications/:noteId" element={<NoteDetail area="admin" />} />
          <Route path="*" element={<ShellNotFound area="admin" />} />
        </Route>

        <Route path="/:slug/account" element={<CustomerLayout />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<CustomerDashboard />} />
          <Route path="orders" element={<MyOrders />} />
          <Route path="orders/:id" element={<CustomerOrderDetail />} />
          <Route path="payments" element={<MyPayments />} />
          <Route path="care" element={<CustomerCare />} />
          <Route path="settings" element={<AccountSettings />} />
          <Route path="notifications" element={<Notes area="account" />} />
          <Route path="notifications/:noteId" element={<NoteDetail area="account" />} />
          <Route path="*" element={<ShellNotFound area="account" />} />
        </Route>

        <Route path="/:slug" element={<SiteLayout />}>
          <Route index element={<SiteHome />} />
          <Route path="about" element={<SiteAbout />} />
          <Route path="contact" element={<SiteContact />} />
          <Route path="products" element={<Products />} />
          <Route path="checkout" element={<Checkout />} />
          <Route path="services" element={<ServicesPage />} />
          <Route path="institutional" element={<InstitutionalPage />} />
          <Route path="menu/:token" element={<QrMenu />} />
          <Route path="orders" element={<Moved to="/:slug/account/orders" />} />
          <Route path="orders/:id" element={<Moved to="/:slug/account/orders/:id" />} />
          <Route path="feedback" element={<Moved to="/:slug/account/care" />} />
          <Route path="*" element={<SiteNotFoundPage />} />
        </Route>

        <Route path="/platform" element={<AdminLayout />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<DashboardAdmin />} />
          <Route path="pharmacies" element={<Pharmacies />} />
          <Route path="pharmacies/:id" element={<PharmacyDetail />} />
          <Route path="billing" element={<Billing />} />
          <Route path="audit" element={<AuditLog />} />
          <Route path="backups" element={<Backups />} />
          <Route path="website" element={<WebsiteBuilder />} />
          <Route path="website-contact" element={<WebsiteMessages />} />
          <Route path="settings" element={<AccountSettings />} />
          <Route path="notifications" element={<Notes area="platform" />} />
          <Route path="notifications/:noteId" element={<NoteDetail area="platform" />} />
          <Route path="*" element={<ShellNotFound area="platform" />} />
        </Route>
        <Route path="*" element={<SystemNotFound />} />
      </Routes>
    </Suspense>
  );
}
