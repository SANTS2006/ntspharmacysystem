// Marketing/legal copy. LEGAL TEXT BELOW IS A DRAFT TEMPLATE and must be reviewed by qualified counsel
// (including Sierra Leone data-protection and Pharmacy Board requirements) before launch.
export const solutions = [
  { id: "inventory", title: "Inventory management", text: "Batch and expiry tracking with first-expiry-first-out allocation, low-stock and expiry alerts, transfers between branches and stocktaking." },
  { id: "prescriptions", title: "Prescription management", text: "Record and verify prescriptions, flag safety concerns, require pharmacist approval before dispensing restricted medicines." },
  { id: "sales", title: "Sales and billing", text: "A fast point of sale with barcode scanning, multiple payment methods, receipts, returns and refunds." },
  { id: "branches", title: "Multi-branch management", text: "Run many branches with branch-level staff, stock and reports, while owners see the whole organisation." },
  { id: "finance", title: "Financial management", text: "Double-entry accounting, expenses, supplier payments, cash management and profit and loss reporting." },
  { id: "reporting", title: "Reporting and analytics", text: "Sales, inventory, procurement, prescription and staff reports with filters and export." },
];

export const faqs = [
  ["Does every pharmacy get its own website?", "Yes. Each registered pharmacy gets a branded website address, its own staff accounts, inventory and records, isolated from every other pharmacy."],
  ["Is our data separated from other pharmacies?", "Yes. Every record belongs to one pharmacy and is only accessible to users of that pharmacy, enforced on the server."],
  ["How do we get started?", "Pharmacies are registered by the platform team. The pharmacy administrator then receives a secure onboarding email and must set a new password at first sign-in."],
  ["Can prescription medicines be sold online?", "Only with a valid prescription and pharmacist approval, subject to your local regulations and your own configuration."],
  ["Which payment methods are supported?", "Payment features are being rolled out in phases. Mobile money (Monime) and online payments are planned and not yet available."],
];

export const legalDocs: Record<string, { title: string; sections: [string, string][] }> = {
  privacy: { title: "Privacy Policy", sections: [
    ["What we collect", "Account details of pharmacy staff and administrators, usage logs and, on behalf of each pharmacy, the customer and prescription data the pharmacy enters."],
    ["Roles", "For pharmacy customer and patient data, the pharmacy is the data controller and PharmaCloud acts as a processor."],
    ["Your rights", "You may request access, correction or deletion of your personal data by contacting the pharmacy or the platform."],
    ["Retention", "Data is retained for as long as the account is active and as required by applicable pharmacy and tax regulations."]] },
  terms: { title: "Terms of Service", sections: [
    ["Use of the service", "The service is for licensed pharmacy operations. You are responsible for compliance with local pharmacy, medicines and data-protection law."],
    ["Accounts", "Keep credentials confidential. Temporary credentials must be changed at first sign-in."],
    ["Suspension", "Access may be suspended for non-payment or breach of these terms."],
    ["Clinical responsibility", "System alerts support but never replace professional pharmacist judgment."]] },
  "payment-refund": { title: "Payment and Refund Policy", sections: [
    ["Subscriptions", "Subscription invoices are issued per plan and are payable by the due date."],
    ["Refunds", "Refunds are issued at the platform's discretion up to the amount paid and are recorded against the original invoice."]] },
  "data-protection": { title: "Data Protection Policy", sections: [
    ["Isolation", "Each pharmacy's data is logically separated and access is role-based."],
    ["Safeguards", "Passwords are hashed, sessions can be revoked and important actions are audit-logged."],
    ["Incidents", "Security incidents affecting personal data will be reported to affected pharmacies without undue delay."]] },
  security: { title: "Security Information", sections: [
    ["Access control", "Role-based permissions are enforced on the server, not just in the interface."],
    ["Authentication", "Login attempts are rate-limited, accounts lock after repeated failures, and temporary passwords expire."],
    ["Auditability", "Sensitive actions are recorded in an append-only audit log."]] },
  cookies: { title: "Cookie Policy", sections: [
    ["Cookies", "The platform website uses only essential storage needed to keep you signed in. No advertising cookies are used."]] },
};
