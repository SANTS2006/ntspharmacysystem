/** Which permissions open each staff module. This mirrors the API's rules; the API still checks every request. */
import type { User } from "../../lib/api";

const any = (...perms: string[]) => (u: User) => perms.some((p) => u.permissions.includes(p));

export const MODULE_ACCESS = {
  dashboard: () => true,
  "my-work": () => true,
  pos: any("pos.sell", "sales.view_branch"),
  orders: any("order.manage"),
  payments: any("accounting.view", "order.manage"),
  deliveries: any("delivery.manage", "delivery.perform"),
  prescriptions: any("prescription.view"),
  medicines: any("medicine.view"),
  inventory: any("inventory.view"),
  procurement: any("procurement.view"),
  customers: any("customer.view"),
  engagement: any("engagement.manage"),
  // branch-scoped staff with report access get the branch profit & loss view
  accounting: (u: User) => u.permissions.includes("accounting.view") || (u.permissions.includes("report.view") && !!u.branch),
  reports: any("report.view", "accounting.view", "hr.view", "payroll.view"),
  payroll: any("payroll.view"),
  hr: any("hr.view"),
  staff: any("staff.view"),
  roles: any("staff.view"),
  branches: any("branch.view"),
  "pharmacy-settings": any("settings.manage"),
  subscription: any("settings.manage"),
} satisfies Record<string, (u: User) => boolean>;

export type Module = keyof typeof MODULE_ACCESS;
export const allowed = (u: User, module: Module) => MODULE_ACCESS[module](u);
