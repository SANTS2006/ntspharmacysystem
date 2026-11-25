"""Single source of truth for permission codenames and default role grants.

Later phases append codenames here. Roles are per-tenant rows (configurable); these are only the defaults
seeded at pharmacy onboarding. Platform-level permissions are held by User.is_platform_admin, not roles."""

# role code -> (display name, branch_scoped)
ROLES = {
    "pharmacy_admin": ("Pharmacy Administrator", False),
    "branch_manager": ("Branch Manager", True),
    "pharmacist": ("Pharmacist", True),
    "pharmacy_technician": ("Pharmacy Technician", True),
    "cashier": ("Cashier", True),
    "inventory_officer": ("Inventory Officer", True),
    "procurement_officer": ("Procurement Officer", True),
    "accountant": ("Accountant", False),
    "hr_manager": ("Human Resource Manager", False),
    "delivery_personnel": ("Delivery Personnel", True),
    "customer": ("Customer/Patient", False),
}
STAFF_ROLE_CODES = [c for c in ROLES if c != "customer"]

PERMISSIONS = {
    "branch.view", "branch.manage",
    "staff.view", "staff.manage", "role.manage",
    "customer.view", "customer.manage",
    "medicine.view", "medicine.manage",
    "inventory.view", "inventory.manage",
    "procurement.view", "procurement.manage", "procurement.approve",
    "prescription.view", "prescription.register", "prescription.verify", "prescription.dispense",
    "pos.sell", "order.manage", "sales.view_own", "sales.view_branch", "sales.refund",
    "accounting.view", "accounting.manage",
    "payroll.view", "payroll.manage", "payroll.approve",
    "hr.view", "hr.manage", "hr.sensitive",
    "service.manage", "engagement.manage", "delivery.manage", "delivery.perform",
    "report.view", "audit.view", "settings.manage",
}

_ALL = set(PERMISSIONS)
DEFAULT_ROLE_PERMISSIONS = {
    "pharmacy_admin": _ALL,
    "branch_manager": {"branch.view", "staff.view", "staff.manage", "medicine.view", "inventory.view",
                       "inventory.manage", "procurement.view", "procurement.manage", "prescription.view", "prescription.register",
                       "pos.sell", "order.manage", "sales.view_branch", "sales.refund", "report.view", "customer.view", "payroll.view",
                       "hr.view", "hr.manage", "service.manage", "engagement.manage", "delivery.manage", "delivery.perform"},
    "pharmacist": {"medicine.view", "inventory.view", "prescription.view", "prescription.register", "prescription.verify",
                   "prescription.dispense", "customer.view", "engagement.manage"},
    "pharmacy_technician": {"medicine.view", "inventory.view", "prescription.view", "prescription.register", "customer.view"},
    "cashier": {"medicine.view", "pos.sell", "order.manage", "sales.view_own", "customer.view", "engagement.manage", "delivery.manage"},
    "inventory_officer": {"medicine.view", "medicine.manage", "inventory.view", "inventory.manage"},
    "procurement_officer": {"medicine.view", "inventory.view", "procurement.view", "procurement.manage"},
    "accountant": {"accounting.view", "accounting.manage", "report.view", "procurement.view", "sales.view_branch"},
    "hr_manager": {"staff.view", "staff.manage", "payroll.view", "payroll.manage", "hr.view", "hr.manage", "hr.sensitive", "report.view"},
    "delivery_personnel": {"delivery.perform"},
    "customer": set(),
}
assert set(DEFAULT_ROLE_PERMISSIONS) == set(ROLES)
assert all(p <= PERMISSIONS for p in DEFAULT_ROLE_PERMISSIONS.values())
