"""Canonical subscription, role, menu, and permission access catalog.

This module is the product contract for launch RBAC seeding. Migrations,
onboarding services, and role-template logic should read from here instead of
reconstructing menu/permission rules independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


FEATURE_FINANCIAL = "feature_financial"
FEATURE_SALES = "feature_sales"
FEATURE_PURCHASE = "feature_purchase"
FEATURE_CATALOG = "feature_catalog"
FEATURE_INVENTORY = "feature_inventory"
FEATURE_MANUFACTURING = "feature_manufacturing"
FEATURE_ASSETS = "feature_assets"
FEATURE_REPORTING = "feature_reporting"
FEATURE_PAYABLES = "feature_payables"
FEATURE_RECEIVABLES = "feature_receivables"
FEATURE_TREASURY = "feature_treasury"
FEATURE_COMPLIANCE = "feature_compliance"
FEATURE_GST_COMPLIANCE = "feature_gst_compliance"
FEATURE_HRMS = "feature_hrms"
FEATURE_PAYROLL = "feature_payroll"
FEATURE_RBAC = "feature_rbac"


ALL_FEATURE_CODES = (
    FEATURE_FINANCIAL,
    FEATURE_SALES,
    FEATURE_PURCHASE,
    FEATURE_CATALOG,
    FEATURE_INVENTORY,
    FEATURE_MANUFACTURING,
    FEATURE_ASSETS,
    FEATURE_REPORTING,
    FEATURE_PAYABLES,
    FEATURE_RECEIVABLES,
    FEATURE_TREASURY,
    FEATURE_COMPLIANCE,
    FEATURE_GST_COMPLIANCE,
    FEATURE_HRMS,
    FEATURE_PAYROLL,
    FEATURE_RBAC,
)


PACKAGE_BASIC_ACCOUNTING = "basic_accounting"
PACKAGE_PROFESSIONAL_ACCOUNTING = "professional_accounting"
PACKAGE_COMPLIANCE = "compliance"
PACKAGE_TREASURY = "treasury"
PACKAGE_PEOPLE = "people"
PACKAGE_ENTERPRISE = "enterprise"


SUBSCRIPTION_PACKAGE_FEATURES = {
    PACKAGE_BASIC_ACCOUNTING: frozenset(
        {
            FEATURE_FINANCIAL,
            FEATURE_SALES,
            FEATURE_PURCHASE,
            FEATURE_CATALOG,
            FEATURE_REPORTING,
            FEATURE_RBAC,
        }
    ),
    PACKAGE_PROFESSIONAL_ACCOUNTING: frozenset(
        {
            FEATURE_FINANCIAL,
            FEATURE_SALES,
            FEATURE_PURCHASE,
            FEATURE_CATALOG,
            FEATURE_REPORTING,
            FEATURE_RBAC,
            FEATURE_PAYABLES,
            FEATURE_RECEIVABLES,
            FEATURE_ASSETS,
            FEATURE_INVENTORY,
        }
    ),
    PACKAGE_COMPLIANCE: frozenset(
        {
            FEATURE_COMPLIANCE,
            FEATURE_GST_COMPLIANCE,
            FEATURE_REPORTING,
        }
    ),
    PACKAGE_TREASURY: frozenset(
        {
            FEATURE_TREASURY,
            FEATURE_FINANCIAL,
            FEATURE_PAYABLES,
            FEATURE_RECEIVABLES,
        }
    ),
    PACKAGE_PEOPLE: frozenset(
        {
            FEATURE_HRMS,
            FEATURE_PAYROLL,
            FEATURE_RBAC,
        }
    ),
    PACKAGE_ENTERPRISE: frozenset(ALL_FEATURE_CODES),
}


ROLE_ENTITY_SUPER_ADMIN = "entity.super_admin"
ROLE_ADMIN = "admin"
ROLE_ACCOUNTS_MANAGER = "accounts_manager"
ROLE_SALES_USER = "sales_user"
ROLE_PURCHASE_USER = "purchase_user"
ROLE_FINANCIAL_REPORT_VIEWER = "financial_report_viewer"
ROLE_PAYABLES_USER = "payables_user"
ROLE_RECEIVABLES_USER = "receivables_user"
ROLE_ASSET_MANAGER = "asset_manager"
ROLE_INVENTORY_USER = "inventory_user"
ROLE_MANUFACTURING_USER = "manufacturing_user"
ROLE_TREASURY_USER = "treasury_user"
ROLE_TREASURY_APPROVER = "treasury_approver"
ROLE_COMPLIANCE_USER = "compliance_user"
ROLE_GST_REVIEWER = "gst_reviewer"
ROLE_HRMS_USER = "hrms_user"
ROLE_HRMS_APPROVER = "hrms_approver"
ROLE_PAYROLL_USER = "payroll_user"
ROLE_PAYROLL_APPROVER = "payroll_approver"
ROLE_PAYROLL_FINANCE_MANAGER = "payroll_finance_manager"


@dataclass(frozen=True)
class RoleSpec:
    code: str
    name: str
    created_for_features: frozenset[str]
    priority: int
    description: str


@dataclass(frozen=True)
class MenuSpec:
    code: str
    name: str
    feature_code: str
    permission_code: str
    parent_code: str | None = None
    route_path: str = ""
    icon: str = ""
    sort_order: int = 100
    menu_type: str = "screen"
    default_role_codes: tuple[str, ...] = ()
    access_mode: str = "operational"
    canonical: bool = True


@dataclass(frozen=True)
class PermissionSpec:
    code: str
    feature_code: str


ROLE_SPECS = (
    RoleSpec(
        ROLE_ENTITY_SUPER_ADMIN,
        "Entity Super Admin",
        frozenset(ALL_FEATURE_CODES),
        1,
        "All permissions allowed by the entity subscription.",
    ),
    RoleSpec(ROLE_ADMIN, "Admin", frozenset(ALL_FEATURE_CODES), 20, "Subscribed setup and administration access."),
    RoleSpec(ROLE_ACCOUNTS_MANAGER, "Accounts Manager", frozenset({FEATURE_FINANCIAL}), 30, "Core accounting operations."),
    RoleSpec(ROLE_SALES_USER, "Sales User", frozenset({FEATURE_SALES}), 40, "Sales document workflow."),
    RoleSpec(ROLE_PURCHASE_USER, "Purchase User", frozenset({FEATURE_PURCHASE}), 50, "Purchase document workflow."),
    RoleSpec(
        ROLE_FINANCIAL_REPORT_VIEWER,
        "Financial Report Viewer",
        frozenset({FEATURE_REPORTING}),
        60,
        "Read-only financial reports.",
    ),
    RoleSpec(ROLE_PAYABLES_USER, "Payables User", frozenset({FEATURE_PAYABLES}), 70, "Vendor and AP workflows."),
    RoleSpec(ROLE_RECEIVABLES_USER, "Receivables User", frozenset({FEATURE_RECEIVABLES}), 80, "Customer and AR workflows."),
    RoleSpec(ROLE_ASSET_MANAGER, "Asset Manager", frozenset({FEATURE_ASSETS}), 90, "Fixed asset workflows."),
    RoleSpec(ROLE_INVENTORY_USER, "Inventory User", frozenset({FEATURE_INVENTORY}), 100, "Inventory operations."),
    RoleSpec(ROLE_MANUFACTURING_USER, "Manufacturing User", frozenset({FEATURE_MANUFACTURING}), 110, "Manufacturing operations."),
    RoleSpec(ROLE_TREASURY_USER, "Treasury User", frozenset({FEATURE_TREASURY}), 120, "Daily treasury execution."),
    RoleSpec(ROLE_TREASURY_APPROVER, "Treasury Approver", frozenset({FEATURE_TREASURY}), 130, "Treasury approval controls."),
    RoleSpec(ROLE_COMPLIANCE_USER, "Compliance User", frozenset({FEATURE_COMPLIANCE}), 140, "Tax and statutory compliance."),
    RoleSpec(ROLE_GST_REVIEWER, "GST Reviewer", frozenset({FEATURE_GST_COMPLIANCE}), 150, "GST reconciliation and review."),
    RoleSpec(ROLE_HRMS_USER, "HRMS User", frozenset({FEATURE_HRMS}), 160, "HRMS operations."),
    RoleSpec(ROLE_HRMS_APPROVER, "HRMS Approver", frozenset({FEATURE_HRMS}), 170, "HRMS approvals."),
    RoleSpec(ROLE_PAYROLL_USER, "Payroll User", frozenset({FEATURE_PAYROLL}), 180, "Payroll preparation."),
    RoleSpec(ROLE_PAYROLL_APPROVER, "Payroll Approver", frozenset({FEATURE_PAYROLL}), 190, "Payroll approvals."),
    RoleSpec(
        ROLE_PAYROLL_FINANCE_MANAGER,
        "Payroll Finance Manager",
        frozenset({FEATURE_PAYROLL, FEATURE_FINANCIAL}),
        200,
        "Payroll posting, handoff, and accounting reconciliation.",
    ),
)

ROLE_ROUTE_PERMISSION_CODES = {
    ROLE_SALES_USER: frozenset(
        {
            "compliance.tcs_section.view",
            "financial.account.view",
            "reports.accountspayableaging.view",
            "reports.daybook.view",
            "reports.financial_hub.daybook.view",
            "reports.financial_hub.receivables_hub.receivable_aging.view",
            "reports.payables.view",
            "reports.vendoroutstanding.view",
            "retail.ticket.view",
            "tcs.section.view",
            "tcs.sections.view",
        }
    ),
    ROLE_PURCHASE_USER: frozenset(
        {
            "financial.account.view",
            "inventory.transfer.view",
            "reports.accountspayableaging.view",
            "reports.daybook.view",
            "reports.financial_hub.daybook.view",
            "reports.financial_hub.receivables_hub.receivable_aging.view",
            "reports.payables.view",
            "reports.vendoroutstanding.view",
        }
    ),
    ROLE_ACCOUNTS_MANAGER: frozenset(
        {
            "financial.account.view",
            "financial.account.create",
            "financial.account.update",
            "financial.account.delete",
            "financial.account_type.view",
            "financial.account_type.create",
            "financial.account_type.update",
            "financial.account_type.delete",
            "financial.account_head.view",
            "financial.account_head.create",
            "financial.account_head.update",
            "financial.account_head.delete",
            "financial.ledger.view",
            "financial.ledger.create",
            "financial.ledger.update",
            "financial.ledger.delete",
            "posting.static_account_settings.bulk_upsert",
            "posting.static_account_settings.create",
            "posting.static_account_settings.delete",
            "posting.static_account_settings.edit",
            "posting.static_account_settings.update",
            "posting.static_account_settings.validate",
            "posting.static_account_settings.view",
            "reports.daybook.view",
            "reports.financial_hub.daybook.view",
            "reports.financial_hub.receivables_hub.receivable_aging.view",
            "tcs.partyprofile.view",
            "retail.ticket.view",
        }
    ),
    ROLE_FINANCIAL_REPORT_VIEWER: frozenset(
        {
            "reports.financial_hub.view",
            "reports.financial_hub.trial_balance.view",
            "reports.trial_balance.view",
            "reports.financial_hub.ledger_book.view",
            "reports.ledger_book.view",
            "reports.financial_hub.ledger_summary.view",
            "reports.ledgersummary.view",
            "reports.financial_hub.profit_loss.view",
            "reports.income_expenditure.view",
            "reports.financial_hub.balance_sheet.view",
            "reports.balance_sheet.view",
            "reports.financial_hub.daybook.view",
            "reports.daybook.view",
            "reports.financial_hub.cashbook.view",
            "reports.cash_book.view",
            "reports.cashbook.view",
        }
    ),
    ROLE_PAYABLES_USER: frozenset(
        {
            "financial.account.view",
            "reports.payables.view",
            "reports.payables.ap_compliance_aging.view",
            "reports.payables.ap_payment_forecast.view",
            "reports.payables.duplicate_anomalous_bill_detection.view",
            "reports.payables.grn_invoice_posting_exceptions.view",
            "reports.payables.upcoming_payments_calendar.view",
            "reports.payables.vendor_reconciliation_statement.view",
            "reports.accountspayableaging.view",
            "reports.vendorledgerstatement.view",
            "reports.vendoroutstanding.view",
        }
    ),
    ROLE_RECEIVABLES_USER: frozenset(
        {
            "financial.account.view",
            "reports.financial_hub.receivables_hub.view",
            "reports.financial_hub.receivables_hub.collections_history.view",
            "reports.financial_hub.receivables_hub.credit_exposure.view",
            "reports.financial_hub.receivables_hub.customer_ledger_statement.view",
            "reports.financial_hub.receivables_hub.customer_outstanding.view",
            "reports.financial_hub.receivables_hub.open_items.view",
            "reports.financial_hub.receivables_hub.overdue_customers.view",
            "reports.financial_hub.receivables_hub.receivable_aging.view",
            "reports.financial_hub.receivables_hub.receivable_aging_detail.view",
            "reports.financial_hub.receivables_hub.receivables_exception_report.view",
            "reports.accounts_receivable_aging.view",
            "reports.outstanding.view",
        }
    ),
    ROLE_GST_REVIEWER: frozenset(
        {
            "compliance.tcs_section.view",
            "gst.reconciliation.view",
            "reports.gst_compliance_center.view",
            "reports.gst_exception_dashboard.view",
            "reports.gstr1_gstr3b_reconciliation.view",
            "reports.gstr1report.view",
            "reports.gstr3b.view",
            "reports.gstr9.view",
            "reports.financial_hub.gst_tds_compliance_center.view",
            "tcs.section.view",
            "tcs.sections.view",
        }
    ),
    ROLE_COMPLIANCE_USER: frozenset(
        {
            "compliance.tcs_config.create",
            "compliance.tcs_config.delete",
            "compliance.tcs_config.export",
            "compliance.tcs_config.import",
            "compliance.tcs_config.update",
            "compliance.tcs_config.view",
            "compliance.tcs_party_profile.create",
            "compliance.tcs_party_profile.delete",
            "compliance.tcs_party_profile.update",
            "compliance.tcs_party_profile.view",
            "compliance.tcs_return_27eq.file",
            "compliance.tcs_return_27eq.view",
            "compliance.tcs_rule.create",
            "compliance.tcs_rule.delete",
            "compliance.tcs_rule.export",
            "compliance.tcs_rule.import",
            "compliance.tcs_rule.update",
            "compliance.tcs_rule.view",
            "compliance.tcs_section.create",
            "compliance.tcs_section.delete",
            "compliance.tcs_section.export",
            "compliance.tcs_section.import",
            "compliance.tcs_section.update",
            "compliance.tcs_section.view",
            "compliance.tcs_statutory.view",
            "reports.financial_hub.tcs_compliance_center.view",
            "reports.tcs_ca_pack.export",
            "reports.tcs_filing_pack.export",
            "reports.tcs_workspace.export",
            "reports.tcsfilingpack.view",
            "reports.tcsledgerreport.view",
            "tcs.config.create",
            "tcs.config.delete",
            "tcs.config.edit",
            "tcs.config.export",
            "tcs.config.import",
            "tcs.config.update",
            "tcs.config.view",
            "tcs.filing_pack.view",
            "tcs.ledger_report.view",
            "tcs.menu.access",
            "tcs.party_profile.create",
            "tcs.party_profile.delete",
            "tcs.party_profile.update",
            "tcs.party_profile.view",
            "tcs.party_profiles.view",
            "tcs.partyprofile.create",
            "tcs.partyprofile.delete",
            "tcs.partyprofile.edit",
            "tcs.partyprofile.update",
            "tcs.partyprofile.view",
            "tcs.return_27eq.view",
            "tcs.rule.create",
            "tcs.rule.delete",
            "tcs.rule.export",
            "tcs.rule.import",
            "tcs.rule.update",
            "tcs.rule.view",
            "tcs.rules.create",
            "tcs.rules.delete",
            "tcs.rules.view",
            "tcs.section.create",
            "tcs.section.delete",
            "tcs.section.export",
            "tcs.section.import",
            "tcs.section.update",
            "tcs.section.view",
            "tcs.sections.create",
            "tcs.sections.delete",
            "tcs.sections.view",
        }
    ),
    ROLE_HRMS_USER: frozenset(
        {
            "hrms.attendance_entry.view",
            "hrms.attendance_import_batch.view",
            "hrms.attendance_payroll_period.view",
            "hrms.attendance_summary.view",
            "hrms.employee.view",
            "hrms.employment_contract.view",
            "hrms.holiday_calendar.view",
            "hrms.leave_application.view",
            "hrms.leave_ledger.view",
            "hrms.leave_policy.view",
            "hrms.onboarding.view",
            "hrms.organization_unit.view",
            "hrms.shift.view",
        }
    ),
    ROLE_PAYROLL_USER: frozenset(
        {
            "payroll.attendance_adjustments.view",
            "payroll.attendance_summaries.view",
            "payroll.component.view",
            "payroll.contract_profile.view",
            "payroll.contract_statutory_profiles.view",
            "payroll.global_component.view",
            "payroll.global_component_group.view",
            "payroll.global_salary_template.view",
            "payroll.one_time_pay_items.view",
            "payroll.period.view",
            "payroll.policies.view",
            "payroll.recurring_pay_items.view",
            "payroll.run.view",
            "payroll.structure.view",
        }
    ),
    ROLE_TREASURY_USER: frozenset(
        {
            "financial.account.view",
            "posting.static_account_settings.bulk_upsert",
            "posting.static_account_settings.update",
            "posting.static_account_settings.validate",
            "posting.static_account_settings.view",
            "treasury.payment_batch.view",
            "treasury.setup.view",
            "reports.financial_hub.bank_reconciliation.view",
            "voucher.payment.view",
        }
    ),
    ROLE_TREASURY_APPROVER: frozenset(
        {
            "financial.account.view",
            "treasury.payment_batch.view",
            "treasury.setup.view",
        }
    ),
    ROLE_HRMS_APPROVER: frozenset(
        {
            "hrms.attendance_payroll_period.view",
            "hrms.attendance_summary.view",
            "hrms.employee.view",
            "hrms.leave_application.view",
        }
    ),
    ROLE_PAYROLL_APPROVER: frozenset(
        {
            "payroll.run.view",
            "payroll.period.view",
        }
    ),
    ROLE_PAYROLL_FINANCE_MANAGER: frozenset(
        {
            "payroll.contract_profile.view",
            "payroll.contract_salary_assignment.view",
            "payroll.period.view",
            "payroll.run.view",
            "accounts.ledger.view",
            "voucher.journal.view",
            "voucher.payment.view",
            "reports.financial_hub.view",
            "reports.financial_hub.ledger_book.view",
        }
    ),
}

ADMIN_MANAGEMENT_PERMISSION_CODES = frozenset(
    {
        "admin.user.create",
        "admin.user.update",
        "admin.user.delete",
        "admin.user_access.view",
        "admin.user_access.update",
        "admin.role.create",
        "admin.role.update",
        "admin.role.delete",
        "admin.role_access.update",
        "admin.menu.view",
        "admin.menu.update",
    }
)

UNIVERSAL_LANDING_PERMISSION_CODES = frozenset(
    {
        "dashboard.home.view",
    }
)


ROOT_MENU_SPECS = (
    MenuSpec("dashboard", "Dashboard", FEATURE_FINANCIAL, "dashboard.home.view", menu_type="group", icon="layout-dashboard", sort_order=10),
    MenuSpec("purchase", "Purchase", FEATURE_PURCHASE, "purchase.invoice.view", menu_type="group", icon="shopping-cart", sort_order=20),
    MenuSpec("sales", "Sales", FEATURE_SALES, "sales.invoice.view", menu_type="group", icon="receipt", sort_order=30),
    MenuSpec("accounts", "Accounts", FEATURE_FINANCIAL, "accounts.ledger.view", menu_type="group", icon="landmark", sort_order=40),
    MenuSpec("catalog", "Catalog", FEATURE_CATALOG, "catalog.product.view", menu_type="group", icon="boxes", sort_order=50),
    MenuSpec("assets", "Assets", FEATURE_ASSETS, "assets.asset.view", menu_type="group", icon="building-2", sort_order=60),
    MenuSpec("treasury", "Treasury", FEATURE_TREASURY, "treasury.payment_batch.view", menu_type="group", icon="banknote", sort_order=70),
    MenuSpec("compliance", "Compliance", FEATURE_COMPLIANCE, "reports.gst_compliance_center.view", menu_type="group", icon="shield-check", sort_order=80),
    MenuSpec("reports", "Reports", FEATURE_REPORTING, "reports.financial_hub.view", menu_type="group", icon="bar-chart-3", sort_order=90),
    MenuSpec("admin", "Admin", FEATURE_RBAC, "admin.user.view", menu_type="group", icon="settings", sort_order=100, access_mode="setup"),
    MenuSpec("payroll", "Payroll", FEATURE_PAYROLL, "payroll.run.view", menu_type="group", icon="wallet-cards", sort_order=110),
    MenuSpec("hrms", "HRMS", FEATURE_HRMS, "hrms.employee.view", menu_type="group", icon="users", sort_order=120),
)


MENU_SPECS = ROOT_MENU_SPECS + (
    MenuSpec("dashboard.home", "Home", FEATURE_FINANCIAL, "dashboard.home.view", "dashboard", "/home", "home", 10, default_role_codes=(ROLE_ADMIN, ROLE_ACCOUNTS_MANAGER, ROLE_SALES_USER, ROLE_PURCHASE_USER)),
    MenuSpec("dashboard.analytics", "Analytics", FEATURE_REPORTING, "dashboard.analytics.view", "dashboard", "/dashboard-analytics", "activity", 20, default_role_codes=(ROLE_ADMIN, ROLE_FINANCIAL_REPORT_VIEWER)),
    MenuSpec("dashboard.dashboard", "Dashboard", FEATURE_FINANCIAL, "dashboard.home.view", "dashboard", "/dashboard", "layout-dashboard", 30, default_role_codes=(ROLE_ADMIN, ROLE_ACCOUNTS_MANAGER, ROLE_SALES_USER, ROLE_PURCHASE_USER)),
    MenuSpec("purchase.transactions", "Transactions", FEATURE_PURCHASE, "purchase.invoice.view", "purchase", icon="files", sort_order=10, menu_type="group", default_role_codes=(ROLE_PURCHASE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("purchase.tools", "Tools", FEATURE_PURCHASE, "purchase.invoice.view", "purchase", icon="wrench", sort_order=20, menu_type="group", default_role_codes=(ROLE_PURCHASE_USER, ROLE_ADMIN)),
    MenuSpec("purchase.compliance", "Compliance", FEATURE_PURCHASE, "purchase.statutory.view", "purchase", icon="shield-check", sort_order=30, menu_type="group", default_role_codes=(ROLE_PURCHASE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("purchase.setup", "Setup", FEATURE_PURCHASE, "purchase.settings.view", "purchase", icon="settings", sort_order=40, menu_type="group", default_role_codes=(ROLE_PURCHASE_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("purchase.invoice", "Purchase Invoice", FEATURE_PURCHASE, "purchase.invoice.view", "purchase.transactions", "/purchaseinvoice", "file-plus-2", 10, default_role_codes=(ROLE_PURCHASE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("purchase.service_invoice", "Purchase Service Invoice", FEATURE_PURCHASE, "purchase.invoice.view", "purchase.transactions", "/purchaseserviceinvoice", "file-plus-2", 20, default_role_codes=(ROLE_PURCHASE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("purchase.credit_note", "Purchase Credit Note", FEATURE_PURCHASE, "purchase.credit_note.view", "purchase.transactions", "/purchasecreditnoteinvoice", "file-minus-2", 30, default_role_codes=(ROLE_PURCHASE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("purchase.debit_note", "Purchase Debit Note", FEATURE_PURCHASE, "purchase.debit_note.view", "purchase.transactions", "/purchasedebitnoteinvoice", "file-pen-line", 40, default_role_codes=(ROLE_PURCHASE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("purchase.service_credit_note", "Purchase Service Credit Note", FEATURE_PURCHASE, "purchase.credit_note.view", "purchase.transactions", "/purchaseservicecreditnoteinvoice", "file-minus-2", 50, default_role_codes=(ROLE_PURCHASE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("purchase.service_debit_note", "Purchase Service Debit Note", FEATURE_PURCHASE, "purchase.debit_note.view", "purchase.transactions", "/purchaseservicedebitnoteinvoice", "file-pen-line", 60, default_role_codes=(ROLE_PURCHASE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("purchase.legacy_import", "Legacy Import", FEATURE_PURCHASE, "purchase.invoice.view", "purchase.tools", "/purchase-legacy-import", "upload", 10, default_role_codes=(ROLE_PURCHASE_USER, ROLE_ADMIN)),
    MenuSpec("purchase.statutory", "Purchase Statutory", FEATURE_PURCHASE, "purchase.statutory.view", "purchase.compliance", "/purchasestatutory", "shield-check", 10, default_role_codes=(ROLE_PURCHASE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("purchase.settings", "Purchase Settings", FEATURE_PURCHASE, "purchase.settings.view", "purchase.setup", "/purchasesettings", "settings", 10, default_role_codes=(ROLE_PURCHASE_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("sales.transactions", "Transactions", FEATURE_SALES, "sales.invoice.view", "sales", icon="files", sort_order=10, menu_type="group", default_role_codes=(ROLE_SALES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("sales.channels_tools", "Channels and Tools", FEATURE_SALES, "sales.invoice.view", "sales", icon="store", sort_order=20, menu_type="group", default_role_codes=(ROLE_SALES_USER, ROLE_ADMIN)),
    MenuSpec("sales.setup", "Setup", FEATURE_SALES, "sales.settings.view", "sales", icon="settings", sort_order=30, menu_type="group", default_role_codes=(ROLE_SALES_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("sales.invoice", "Sales Invoice", FEATURE_SALES, "sales.invoice.view", "sales.transactions", "/saleinvoice", "receipt-text", 10, default_role_codes=(ROLE_SALES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("sales.service_invoice", "Sales Service Invoice", FEATURE_SALES, "sales.invoice.view", "sales.transactions", "/saleserviceinvoice", "receipt-text", 20, default_role_codes=(ROLE_SALES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("sales.credit_note", "Sales Credit Note", FEATURE_SALES, "sales.credit_note.view", "sales.transactions", "/salecreditnoteinvoice", "file-minus-2", 30, default_role_codes=(ROLE_SALES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("sales.debit_note", "Sales Debit Note", FEATURE_SALES, "sales.debit_note.view", "sales.transactions", "/saledebitnoteinvoice", "file-pen-line", 40, default_role_codes=(ROLE_SALES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("sales.service_credit_note", "Sales Service Credit Note", FEATURE_SALES, "sales.credit_note.view", "sales.transactions", "/saleservicecreditnoteinvoice", "file-minus-2", 50, default_role_codes=(ROLE_SALES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("sales.service_debit_note", "Sales Service Debit Note", FEATURE_SALES, "sales.debit_note.view", "sales.transactions", "/saleservicedebitnoteinvoice", "file-pen-line", 60, default_role_codes=(ROLE_SALES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("sales.retail_sale", "Retail Sale", FEATURE_SALES, "retail.ticket.view", "sales.channels_tools", "/retail-sale-entry", "store", 10, default_role_codes=(ROLE_SALES_USER, ROLE_ADMIN)),
    MenuSpec("sales.commerce_line_tester", "Commerce Line Tester", FEATURE_SALES, "commerce.line_tester.view", "sales.channels_tools", "/commerce-line-tester", "flask-conical", 20, default_role_codes=(ROLE_SALES_USER, ROLE_ADMIN)),
    MenuSpec("sales.bulk_print", "Bulk Print Center", FEATURE_SALES, "sales.invoice.view", "sales.channels_tools", "/sales-bulk-print-center", "printer", 30, default_role_codes=(ROLE_SALES_USER, ROLE_ADMIN)),
    MenuSpec("sales.legacy_import", "Legacy Import", FEATURE_SALES, "sales.invoice.view", "sales.channels_tools", "/sales-legacy-import", "upload", 40, default_role_codes=(ROLE_SALES_USER, ROLE_ADMIN)),
    MenuSpec("sales.settings", "Sales Settings", FEATURE_SALES, "sales.settings.view", "sales.setup", "/salessettings", "settings", 10, default_role_codes=(ROLE_SALES_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("accounts.vouchers", "Vouchers", FEATURE_FINANCIAL, "voucher.journal.view", "accounts", icon="book-open-check", sort_order=10, menu_type="group", default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("accounts.financial_masters", "Financial Masters", FEATURE_FINANCIAL, "accounts.ledger.view", "accounts", icon="landmark", sort_order=20, menu_type="group", default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("accounts.settings", "Settings", FEATURE_FINANCIAL, "voucher.settings.view", "accounts", icon="settings-2", sort_order=90, menu_type="group", default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("accounts.journal_voucher", "Journal Voucher", FEATURE_FINANCIAL, "voucher.journal.view", "accounts.vouchers", "/journalvoucher", "book-open", 10, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("accounts.bank_voucher", "Bank Voucher", FEATURE_FINANCIAL, "voucher.bank.view", "accounts.vouchers", "/bankvoucher", "landmark", 20, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_TREASURY_USER, ROLE_ADMIN)),
    MenuSpec("accounts.cash_voucher", "Cash Voucher", FEATURE_FINANCIAL, "voucher.cash.view", "accounts.vouchers", "/cashvoucher", "coins", 30, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("accounts.receipt_voucher", "Receipt Voucher", FEATURE_FINANCIAL, "voucher.receipt.view", "accounts.vouchers", "/receiptvoucher", "arrow-down-to-line", 40, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_RECEIVABLES_USER, ROLE_ADMIN)),
    MenuSpec("accounts.payment_voucher", "Payment Voucher", FEATURE_FINANCIAL, "voucher.payment.view", "accounts.vouchers", "/paymentvoucher", "arrow-up-from-line", 50, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_PAYABLES_USER, ROLE_TREASURY_USER, ROLE_ADMIN)),
    MenuSpec("accounts.account_types", "Account Types", FEATURE_FINANCIAL, "accounts.account_type.view", "accounts.financial_masters", "/financialmaster/accounttypes", "layers", 10, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("accounts.account_heads", "Account Heads", FEATURE_FINANCIAL, "accounts.account_head.view", "accounts.financial_masters", "/financialmaster/accountheads", "list-tree", 20, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("accounts.ledgers", "Ledgers", FEATURE_FINANCIAL, "accounts.ledger.view", "accounts.financial_masters", "/financialmaster/ledgers", "list-tree", 30, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("accounts.accounts", "Accounts", FEATURE_FINANCIAL, "accounts.account.view", "accounts.financial_masters", "/financialmaster/accounts", "book-user", 40, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("accounts.payment_settings", "Payment Settings", FEATURE_FINANCIAL, "voucher.payment_settings.view", "accounts.settings", "/paymentsettings", "settings", 10, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("accounts.receipt_settings", "Receipt Settings", FEATURE_FINANCIAL, "voucher.receipt_settings.view", "accounts.settings", "/receiptsettings", "settings", 20, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("accounts.voucher_settings", "Voucher Settings", FEATURE_FINANCIAL, "voucher.settings.view", "accounts.settings", "/vouchersettings", "settings", 30, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("accounts.static_account_settings", "Static Account Settings", FEATURE_FINANCIAL, "posting.static_account_settings.view", "accounts.settings", "/staticaccountsettings", "settings", 40, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("accounts.capital_distribution_setup", "Capital & Distribution", FEATURE_FINANCIAL, "capital_distribution.setup.view", "accounts.settings", "/capital-distribution-setup", "network", 50, default_role_codes=(ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("catalog.products_group", "Products", FEATURE_CATALOG, "catalog.product.view", "catalog", icon="package", sort_order=10, menu_type="group", default_role_codes=(ROLE_SALES_USER, ROLE_PURCHASE_USER, ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("catalog.classification", "Classification", FEATURE_CATALOG, "catalog.hsn_sac.view", "catalog", icon="folder-tree", sort_order=20, menu_type="group", default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("catalog.commercial", "Commercial", FEATURE_CATALOG, "catalog.product.view", "catalog", icon="badge-indian-rupee", sort_order=30, menu_type="group", default_role_codes=(ROLE_SALES_USER, ROLE_PURCHASE_USER, ROLE_ADMIN)),
    MenuSpec("catalog.products", "Products", FEATURE_CATALOG, "catalog.product.view", "catalog.products_group", "/catalogproducts", "package", 10, default_role_codes=(ROLE_SALES_USER, ROLE_PURCHASE_USER, ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("catalog.categories", "Product Categories", FEATURE_CATALOG, "catalog.category.view", "catalog.products_group", "/catalogproductcategories", "folder-tree", 20, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("catalog.brands", "Brands", FEATURE_CATALOG, "catalog.brand.view", "catalog.classification", "/catalogbrands", "badge", 10, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("catalog.uoms", "UOMs", FEATURE_CATALOG, "catalog.uom.view", "catalog.classification", "/cataloguoms", "ruler", 20, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("catalog.hsn_sac", "HSN SAC", FEATURE_CATALOG, "catalog.hsn_sac.view", "catalog.classification", "/cataloghsnsac", "badge-indian-rupee", 30, default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("catalog.price_lists", "Price Lists", FEATURE_CATALOG, "catalog.price_list.view", "catalog.commercial", "/catalogpricelists", "list", 10, default_role_codes=(ROLE_SALES_USER, ROLE_ADMIN)),
    MenuSpec("catalog.product_attributes", "Product Attributes", FEATURE_CATALOG, "catalog.product_attribute.view", "catalog.commercial", "/catalogproductattributes", "sliders-horizontal", 20, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("assets.registry", "Registry", FEATURE_ASSETS, "assets.asset.view", "assets", icon="building-2", sort_order=10, menu_type="group", default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ADMIN)),
    MenuSpec("assets.depreciation", "Depreciation", FEATURE_ASSETS, "assets.depreciation_run.view", "assets", icon="calculator", sort_order=20, menu_type="group", default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("assets.controls", "Controls", FEATURE_ASSETS, "assets.settings.view", "assets", icon="settings", sort_order=30, menu_type="group", default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("assets.dashboard", "Asset Dashboard", FEATURE_ASSETS, "assets.asset_dashboard.view", "assets.registry", "/asset-dashboard", "gauge", 10, default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ADMIN)),
    MenuSpec("assets.master", "Asset Master", FEATURE_ASSETS, "assets.asset.view", "assets.registry", "/asset-master", "building-2", 20, default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ADMIN)),
    MenuSpec("assets.category_master", "Asset Category Master", FEATURE_ASSETS, "assets.category.view", "assets.registry", "/asset-category-master", "folder-tree", 30, default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ADMIN)),
    MenuSpec("assets.depreciation_run", "Depreciation Run", FEATURE_ASSETS, "assets.depreciation_run.view", "assets.depreciation", "/depreciation-run", "calculator", 10, default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("assets.settings", "Asset Settings", FEATURE_ASSETS, "assets.settings.view", "assets.controls", "/asset-settings", "settings", 10, default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("treasury.setup", "Treasury Setup", FEATURE_TREASURY, "treasury.setup.view", "treasury", "/treasury-setup", "settings-2", 10, default_role_codes=(ROLE_TREASURY_USER, ROLE_TREASURY_APPROVER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("treasury.execution", "Treasury Execution", FEATURE_TREASURY, "treasury.payment_batch.view", "treasury", "/treasury-execution", "banknote", 20, default_role_codes=(ROLE_TREASURY_USER, ROLE_TREASURY_APPROVER, ROLE_ADMIN)),
    MenuSpec("treasury.instruments", "Treasury Instruments", FEATURE_TREASURY, "treasury.payment_batch.view", "treasury", "/treasury-instruments", "landmark", 30, default_role_codes=(ROLE_TREASURY_USER, ROLE_TREASURY_APPROVER, ROLE_ADMIN)),
    MenuSpec("compliance.gst_and_tds", "GST and TDS", FEATURE_GST_COMPLIANCE, "gst.reconciliation.view", "compliance", icon="badge-indian-rupee", sort_order=10, menu_type="group", default_role_codes=(ROLE_GST_REVIEWER, ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("compliance.tcs_setup", "TCS Setup", FEATURE_COMPLIANCE, "compliance.tcs_config.view", "compliance", icon="settings", sort_order=20, menu_type="group", default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("compliance.tcs_operations", "TCS Operations", FEATURE_COMPLIANCE, "compliance.tcs_return_27eq.view", "compliance", icon="file-check-2", sort_order=30, menu_type="group", default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("compliance.gst_reconciliation", "GST Reconciliation", FEATURE_GST_COMPLIANCE, "gst.reconciliation.view", "compliance.gst_and_tds", "/gst-reconciliation", "git-compare-arrows", 10, default_role_codes=(ROLE_GST_REVIEWER, ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("compliance.gst_tds_config", "GST-TDS Config", FEATURE_GST_COMPLIANCE, "gst.tds.config.view", "compliance.gst_and_tds", "/gstdsconfig", "settings", 20, default_role_codes=(ROLE_GST_REVIEWER, ROLE_COMPLIANCE_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("compliance.tcs_config", "TCS Config", FEATURE_COMPLIANCE, "compliance.tcs_config.view", "compliance.tcs_setup", "/tcsconfig", "settings", 10, default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("compliance.tcs_sections", "TCS Sections", FEATURE_COMPLIANCE, "compliance.tcs_section.view", "compliance.tcs_setup", "/tcssections", "list-tree", 20, default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("compliance.tcs_rules", "TCS Rules", FEATURE_COMPLIANCE, "compliance.tcs_rule.view", "compliance.tcs_setup", "/tcsrules", "scale", 30, default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("compliance.tcs_party_profiles", "TCS Party Profiles", FEATURE_COMPLIANCE, "compliance.tcs_party_profile.view", "compliance.tcs_setup", "/tcspartyprofiles", "users", 40, default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("compliance.tcs_return_27eq", "TCS Return 27EQ", FEATURE_COMPLIANCE, "compliance.tcs_return_27eq.view", "compliance.tcs_operations", "/tcsreturn27eq", "file-check-2", 10, default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("compliance.tcs_statutory", "TCS Statutory", FEATURE_COMPLIANCE, "compliance.tcs_statutory.view", "compliance.tcs_operations", "/tcsstatutory", "shield-check", 20, default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("reports.controls", "Controls Reports", FEATURE_REPORTING, "reports.financial_hub.controls_phase_one.view", "reports", icon="shield-check", sort_order=5, menu_type="group", default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial", "Financial Reports", FEATURE_REPORTING, "reports.financial_hub.view", "reports", icon="bar-chart-3", sort_order=10, menu_type="group", default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.compliance", "Compliance Reports", FEATURE_COMPLIANCE, "reports.financial_hub.tds_compliance_center.view", "reports", icon="shield-check", sort_order=20, menu_type="group", default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_GST_REVIEWER, ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("reports.payables", "Payables Reports", FEATURE_PAYABLES, "reports.payables.view", "reports", icon="wallet", sort_order=40, menu_type="group", default_role_codes=(ROLE_PAYABLES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.receivables_hub", "Receivables Hub", FEATURE_RECEIVABLES, "reports.financial_hub.receivables_hub.view", "reports", "/reports/receivables", "hand-coins", 50, default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.receivables", "Receivables Reports", FEATURE_RECEIVABLES, "reports.financial_hub.receivables_hub.view", "reports", icon="hand-coins", sort_order=52, menu_type="group", default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.manufacturing", "Manufacturing Reports", FEATURE_MANUFACTURING, "reports.inventory.view", "reports", icon="factory", sort_order=54, menu_type="group", default_role_codes=(ROLE_MANUFACTURING_USER, ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.assets", "Asset Reports", FEATURE_ASSETS, "assets.fixed_asset_register.view", "reports", icon="building-2", sort_order=56, menu_type="group", default_role_codes=(ROLE_ASSET_MANAGER, ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.inventory", "Inventory Hub", FEATURE_INVENTORY, "reports.inventory.view", "reports", "/reports/inventory", "warehouse", 60, default_role_codes=(ROLE_INVENTORY_USER, ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.controls.control_center", "Control Center", FEATURE_REPORTING, "reports.financial_hub.controls_phase_one.view", "reports.controls", "/reports/controls/phase-one", "shield", 10, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.controls.year_end_close", "Year-End Close", FEATURE_REPORTING, "reports.financial_hub.year_end_close.view", "reports.controls", "/reports/controls/year-end-close", "calendar-check", 20, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.controls.posting_setup", "Posting Setup", FEATURE_REPORTING, "reports.financial_hub.posting_setup.view", "reports.controls", "/reports/controls/posting-setup", "settings", 30, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial_hub", "Financial Hub", FEATURE_REPORTING, "reports.financial_hub.view", "reports.financial", icon="layout-grid", sort_order=10, menu_type="group", default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial_hub.index", "Hub Overview", FEATURE_REPORTING, "reports.financial_hub.view", "reports.financial_hub", "/reports/financial", "layout-grid", 10, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial_hub.trial_balance", "Trial Balance", FEATURE_REPORTING, "reports.financial_hub.trial_balance.view", "reports.financial_hub", "/reports/financial/trial-balance", "scale", 20, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial_hub.ledger_book", "Ledger Book", FEATURE_REPORTING, "reports.financial_hub.ledger_book.view", "reports.financial_hub", "/reports/financial/ledger-book", "book-open", 30, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial_hub.ledger_summary", "Ledger Summary", FEATURE_REPORTING, "reports.financial_hub.ledger_summary.view", "reports.financial_hub", "/reports/financial/ledger-summary", "list-tree", 40, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial_hub.profit_loss", "Profit & Loss", FEATURE_REPORTING, "reports.financial_hub.profit_loss.view", "reports.financial_hub", "/reports/financial/profit-loss", "trending-up", 50, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial_hub.balance_sheet", "Balance Sheet", FEATURE_REPORTING, "reports.financial_hub.balance_sheet.view", "reports.financial_hub", "/reports/financial/balance-sheet", "columns-3", 60, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial_hub.trading_account", "Trading Account", FEATURE_REPORTING, "reports.financial_hub.trial_balance.view", "reports.financial_hub", "/reports/financial/trading-account", "chart-no-axes-column", 70, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial_hub.daybook", "Daybook", FEATURE_REPORTING, "reports.financial_hub.daybook.view", "reports.financial_hub", "/reports/financial/daybook", "calendar-days", 80, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial_hub.cashbook", "Cashbook", FEATURE_REPORTING, "reports.financial_hub.cashbook.view", "reports.financial_hub", "/reports/financial/cashbook", "wallet", 90, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.financial_hub.settings", "Report Settings", FEATURE_REPORTING, "reports.financial_hub.settings.view", "reports.financial_hub", "/reports/financial/settings", "settings", 100, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("reports.financial_hub.bank_reconciliation", "Bank Reconciliation", FEATURE_TREASURY, "reports.financial_hub.bank_reconciliation.view", "reports.financial_hub", "/bank-reco", "landmark", 110, default_role_codes=(ROLE_TREASURY_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.tds_compliance_center", "TDS Compliance Center", FEATURE_COMPLIANCE, "reports.financial_hub.tds_compliance_center.view", "reports.financial_hub", "/reports/tds", "receipt-indian-rupee", 120, default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.gst_tds_compliance_center", "GST-TDS Compliance Center", FEATURE_GST_COMPLIANCE, "reports.financial_hub.gst_tds_compliance_center.view", "reports.financial_hub", "/reports/gst-tds", "badge-indian-rupee", 130, default_role_codes=(ROLE_GST_REVIEWER, ROLE_COMPLIANCE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.tcs_compliance_center", "TCS Compliance Center", FEATURE_COMPLIANCE, "reports.financial_hub.tcs_compliance_center.view", "reports.financial_hub", "/reports/tcs", "file-check-2", 140, default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.tradingaccountstatement", "Trading Account Statement", FEATURE_REPORTING, "reports.tradingaccountstatement.view", "reports.financial_hub", "/tradingaccountstatement", "chart-no-axes-column", 150, default_role_codes=(ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.interestcalculatorindividualreport", "Interest Calculator", FEATURE_REPORTING, "reports.interestcalculatorindividualreport.view", "reports.financial_hub", icon="calculator", sort_order=160, canonical=False),
    MenuSpec("reports.gst_compliance_center", "GST Compliance Center", FEATURE_GST_COMPLIANCE, "reports.gst_compliance_center.view", "reports.compliance", "/reports/compliance/gst-compliance-center", "shield-check", 10, default_role_codes=(ROLE_GST_REVIEWER, ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("reports.gstr1_outward", "GSTR-1 Outward", FEATURE_GST_COMPLIANCE, "reports.gstr1report.view", "reports.compliance", "/gstreport", "file-spreadsheet", 20, default_role_codes=(ROLE_GST_REVIEWER, ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("reports.tcs_ledger", "TCS Ledger", FEATURE_COMPLIANCE, "reports.tcsledgerreport.view", "reports.compliance", "/tcsledgerreport", "book-open", 30, default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("reports.tcs_filing_pack", "TCS Filing Pack", FEATURE_COMPLIANCE, "reports.tcsfilingpack.view", "reports.compliance", "/tcsfilingpack", "package-check", 40, default_role_codes=(ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("reports.gstr1_gstr3b_reconciliation", "GSTR-1 vs GSTR-3B Reconciliation", FEATURE_GST_COMPLIANCE, "reports.gstr1_gstr3b_reconciliation.view", "reports.compliance", "/reports/compliance/gstr1-vs-gstr3b", "git-compare-arrows", 50, default_role_codes=(ROLE_GST_REVIEWER, ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("reports.gstr9", "GSTR-9 Annual Return", FEATURE_GST_COMPLIANCE, "reports.gstr9.view", "reports.compliance", "/gstr9report", "file-badge", 60, default_role_codes=(ROLE_GST_REVIEWER, ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("reports.gst_exception_dashboard", "GST Exception Dashboard", FEATURE_GST_COMPLIANCE, "reports.gst_exception_dashboard.view", "reports.compliance", "/reports/compliance/gst-exception-dashboard", "triangle-alert", 70, default_role_codes=(ROLE_GST_REVIEWER, ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("reports.gstr3b", "GSTR3B Report", FEATURE_GST_COMPLIANCE, "reports.gstr3b.view", "reports.compliance", "/gstr3breport", "file-spreadsheet", 80, default_role_codes=(ROLE_GST_REVIEWER, ROLE_COMPLIANCE_USER, ROLE_ADMIN)),
    MenuSpec("reports.vendoroutstanding", "Vendor Outstanding", FEATURE_PAYABLES, "reports.vendoroutstanding.view", "reports.payables", "/reports/payables/vendor_outstanding", "hand-coins", 10, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.vendorledgerstatement", "Vendor Ledger Statement", FEATURE_PAYABLES, "reports.vendorledgerstatement.view", "reports.payables", "/reports/payables/vendor_ledger_statement", "book-open", 20, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.payablesclosepack", "Payables Close Pack", FEATURE_PAYABLES, "reports.payablesclosepack.view", "reports.payables", "/reports/payables/payables_close_pack", "package-check", 30, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.vendorsettlementhistory", "Vendor Settlement History", FEATURE_PAYABLES, "reports.vendorsettlementhistory.view", "reports.payables", "/reports/payables/vendor_settlement_history", "history", 40, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.vendornoteregister", "Vendor Debit/Credit Note Register", FEATURE_PAYABLES, "reports.vendornoteregister.view", "reports.payables", "/reports/payables/vendor_note_register", "file-text", 50, default_role_codes=(ROLE_PAYABLES_USER, ROLE_PURCHASE_USER, ROLE_ADMIN)),
    MenuSpec("reports.apglreconciliation", "AP to GL Reconciliation", FEATURE_PAYABLES, "reports.apglreconciliation.view", "reports.payables", "/reports/payables/ap_gl_reconciliation", "git-compare-arrows", 60, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.payables.hub", "Payables Reports", FEATURE_PAYABLES, "reports.payables.view", "reports.payables", "/reports/payables", "wallet", 70, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.payables.purchase_register", "Purchase Register", FEATURE_PAYABLES, "reports.financial_hub.payables_hub.purchase_register.view", "reports.payables", "/reports/payables/purchase-register", "file-text", 80, default_role_codes=(ROLE_PAYABLES_USER, ROLE_PURCHASE_USER, ROLE_ADMIN)),
    MenuSpec("reports.vendorbalanceexceptions", "Vendor Balance Exceptions", FEATURE_PAYABLES, "reports.vendorbalanceexceptions.view", "reports.payables", "/reports/payables/vendor_balance_exceptions", "triangle-alert", 90, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.payables.ap_aging", "AP Aging", FEATURE_PAYABLES, "reports.accountspayableaging.view", "reports.payables.hub", "/reports/payables/ap_aging", "clock", 10, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ACCOUNTS_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.payables.upcoming_payments_calendar", "Upcoming Payments Calendar", FEATURE_PAYABLES, "reports.payables.upcoming_payments_calendar.view", "reports.payables.hub", "/reports/payables/upcoming_payments_calendar", "calendar", 20, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.payables.ap_payment_forecast", "AP Payment Forecast", FEATURE_PAYABLES, "reports.payables.ap_payment_forecast.view", "reports.payables.hub", "/reports/payables/ap_payment_forecast", "chart-line", 30, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.payables.msme_overdue", "MSME Overdue Report", FEATURE_PAYABLES, "reports.payables.msme_overdue.view", "reports.payables.hub", "/reports/payables/msme_overdue", "timer", 40, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.payables.vendor_reconciliation_statement", "Vendor Reconciliation Statement", FEATURE_PAYABLES, "reports.payables.vendor_reconciliation_statement.view", "reports.payables.hub", "/reports/payables/vendor_reconciliation_statement", "git-compare-arrows", 50, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.payables.grn_invoice_posting_exceptions", "GRN Invoice Posting Exceptions", FEATURE_PAYABLES, "reports.payables.grn_invoice_posting_exceptions.view", "reports.payables.hub", "/reports/payables/grn_invoice_posting_exceptions", "triangle-alert", 60, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.payables.ap_compliance_aging", "AP Compliance Aging", FEATURE_PAYABLES, "reports.payables.ap_compliance_aging.view", "reports.payables.hub", "/reports/payables/ap_compliance_aging", "shield-alert", 70, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.payables.duplicate_anomalous_bill_detection", "Duplicate/Anomalous Bill Detection", FEATURE_PAYABLES, "reports.payables.duplicate_anomalous_bill_detection.view", "reports.payables.hub", "/reports/payables/duplicate_anomalous_bill_detection", "copy-x", 80, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.payables.settings", "Payables Settings", FEATURE_PAYABLES, "reports.payables.settings.view", "reports.payables.hub", "/reports/payables/settings", "settings", 90, default_role_codes=(ROLE_PAYABLES_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("reports.receivables.customer_ledger_statement", "Customer Ledger Statement", FEATURE_RECEIVABLES, "reports.financial_hub.receivables_hub.customer_ledger_statement.view", "reports.receivables", "/reports/receivables/customer-ledger-statement", "book-open", 10, default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.receivables.customer_outstanding", "Customer Outstanding", FEATURE_RECEIVABLES, "reports.financial_hub.receivables_hub.customer_outstanding.view", "reports.receivables", "/reports/receivables/customer-outstanding", "hand-coins", 20, default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.receivables.receivable_aging", "Receivable Aging", FEATURE_RECEIVABLES, "reports.financial_hub.receivables_hub.receivable_aging.view", "reports.receivables", "/reports/receivables/receivable-aging", "clock", 30, default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.receivables.receivable_aging_detail", "Receivable Aging Detail", FEATURE_RECEIVABLES, "reports.financial_hub.receivables_hub.receivable_aging_detail.view", "reports.receivables", "/reports/receivables/receivable-aging-detail", "list", 40, default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.receivables.overdue_customers", "Overdue Customers", FEATURE_RECEIVABLES, "reports.financial_hub.receivables_hub.overdue_customers.view", "reports.receivables", "/reports/receivables/overdue-customers", "timer", 50, default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.receivables.credit_exposure", "Credit Exposure", FEATURE_RECEIVABLES, "reports.financial_hub.receivables_hub.credit_exposure.view", "reports.receivables", "/reports/receivables/credit-exposure", "gauge", 60, default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.receivables.open_items", "Open Items", FEATURE_RECEIVABLES, "reports.financial_hub.receivables_hub.open_items.view", "reports.receivables", "/reports/receivables/open-items", "list-checks", 70, default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.receivables.collections_history", "Collections History", FEATURE_RECEIVABLES, "reports.financial_hub.receivables_hub.collections_history.view", "reports.receivables", "/reports/receivables/collections-history", "history", 80, default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.receivables.sales_register", "Sales Register", FEATURE_RECEIVABLES, "reports.sales_register.view", "reports.receivables", "/reports/salesregister", "receipt-text", 90, default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_SALES_USER, ROLE_ADMIN)),
    MenuSpec("reports.receivables.exceptions", "Receivables Exceptions", FEATURE_RECEIVABLES, "reports.financial_hub.receivables_hub.receivables_exception_report.view", "reports.receivables", "/reports/receivables/exceptions", "triangle-alert", 100, default_role_codes=(ROLE_RECEIVABLES_USER, ROLE_ADMIN)),
    MenuSpec("reports.manufacturing.hub", "Manufacturing Hub", FEATURE_MANUFACTURING, "reports.inventory.manufacturing_hub.view", "reports.manufacturing", "/reports/manufacturing", "factory", 10, default_role_codes=(ROLE_MANUFACTURING_USER, ROLE_ADMIN)),
    MenuSpec("reports.manufacturing.summary", "Manufacturing Summary", FEATURE_MANUFACTURING, "reports.inventory.manufacturing_summary.view", "reports.manufacturing", "/reports/manufacturing/summary", "chart-bar", 20, default_role_codes=(ROLE_MANUFACTURING_USER, ROLE_ADMIN)),
    MenuSpec("reports.manufacturing.material_consumption", "Material Consumption Report", FEATURE_MANUFACTURING, "reports.inventory.manufacturing_material_consumption.view", "reports.manufacturing", "/reports/manufacturing/material-consumption", "boxes", 30, default_role_codes=(ROLE_MANUFACTURING_USER, ROLE_ADMIN)),
    MenuSpec("reports.manufacturing.output_yield", "Output And Yield Report", FEATURE_MANUFACTURING, "reports.inventory.manufacturing_output_yield.view", "reports.manufacturing", "/reports/manufacturing/output-yield", "chart-pie", 40, default_role_codes=(ROLE_MANUFACTURING_USER, ROLE_ADMIN)),
    MenuSpec("reports.manufacturing.posting_audit", "Posting Audit Report", FEATURE_MANUFACTURING, "reports.inventory.manufacturing_posting_audit.view", "reports.manufacturing", "/reports/manufacturing/posting-audit", "clipboard-check", 50, default_role_codes=(ROLE_MANUFACTURING_USER, ROLE_ADMIN)),
    MenuSpec("reports.manufacturing.wip_cost_summary", "WIP And Cost Summary", FEATURE_MANUFACTURING, "reports.inventory.manufacturing_wip_cost_summary.view", "reports.manufacturing", "/reports/manufacturing/wip-cost-summary", "chart-no-axes-column", 60, default_role_codes=(ROLE_MANUFACTURING_USER, ROLE_ADMIN)),
    MenuSpec("reports.assets.fixed_register", "Fixed Asset Register", FEATURE_ASSETS, "assets.fixed_asset_register.view", "reports.assets", "/fixed-asset-register", "clipboard-list", 10, default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.assets.depreciation_schedule", "Depreciation Schedule", FEATURE_ASSETS, "assets.depreciation_schedule.view", "reports.assets", "/depreciation-schedule", "calendar", 20, default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.assets.asset_events", "Asset Events", FEATURE_ASSETS, "assets.asset_events.view", "reports.assets", "/asset-events", "activity", 30, default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.assets.asset_history", "Asset History", FEATURE_ASSETS, "assets.asset_history.view", "reports.assets", "/asset-history", "history", 40, default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.assets.location_custodian", "Asset Location / Custodian", FEATURE_ASSETS, "assets.asset_location_custodian.view", "reports.assets", "/asset-location-custodian", "map-pin", 50, default_role_codes=(ROLE_ASSET_MANAGER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.setup", "Setup", FEATURE_INVENTORY, "inventory.location.view", "reports.inventory", icon="settings", sort_order=10, menu_type="group", default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.operations", "Operations", FEATURE_INVENTORY, "inventory.transfer.view", "reports.inventory", icon="arrow-left-right", sort_order=20, menu_type="group", default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.analysis", "Analysis Reports", FEATURE_INVENTORY, "reports.inventory.stock_summary.view", "reports.inventory", icon="chart-bar", sort_order=30, menu_type="group", default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.controls", "Control Reports", FEATURE_INVENTORY, "reports.inventory.reorder_status.view", "reports.inventory", icon="shield-check", sort_order=40, menu_type="group", default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.location_master", "Location Master", FEATURE_INVENTORY, "inventory.location.view", "reports.inventory.setup", "/inventory-location-master", "map-pin", 10, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.settings", "Inventory Settings", FEATURE_INVENTORY, "inventory.settings.view", "reports.inventory.setup", "/inventorysettings", "settings", 20, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN), access_mode="setup"),
    MenuSpec("reports.inventory.transfer_entry", "Transfer Entry", FEATURE_INVENTORY, "inventory.transfer.view", "reports.inventory.operations", "/inventory-transfer-entry", "arrow-left-right", 10, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.transfer_browser", "Transfer Browser", FEATURE_INVENTORY, "inventory.transfer.view", "reports.inventory.operations", "/inventory-transfer-list", "list", 20, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.adjustment_entry", "Adjustment Entry", FEATURE_INVENTORY, "inventory.adjustment.view", "reports.inventory.operations", "/inventory-adjustment-entry", "sliders-horizontal", 30, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.adjustment_browser", "Adjustment Browser", FEATURE_INVENTORY, "inventory.adjustment.view", "reports.inventory.operations", "/inventory-adjustment-list", "list-checks", 40, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.stock_summary", "Stock Summary", FEATURE_INVENTORY, "reports.inventory.stock_summary.view", "reports.inventory.analysis", "/reports/inventory/stock-summary", "chart-bar", 10, default_role_codes=(ROLE_INVENTORY_USER, ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.stock_ledger", "Stock Ledger", FEATURE_INVENTORY, "reports.inventory.stock_ledger.view", "reports.inventory.analysis", "/reports/inventory/stock-ledger", "book-open", 20, default_role_codes=(ROLE_INVENTORY_USER, ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.stock_aging", "Stock Aging", FEATURE_INVENTORY, "reports.inventory.stock_aging.view", "reports.inventory.analysis", "/reports/inventory/stock-aging", "clock", 30, default_role_codes=(ROLE_INVENTORY_USER, ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.location_stock", "Location Stock", FEATURE_INVENTORY, "reports.inventory.location_stock.view", "reports.inventory.analysis", "/reports/inventory/location-stock", "map-pin", 40, default_role_codes=(ROLE_INVENTORY_USER, ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.stock_movement", "Stock Movement", FEATURE_INVENTORY, "reports.inventory.stock_movement.view", "reports.inventory.analysis", "/reports/inventory/stock-movement", "arrow-left-right", 50, default_role_codes=(ROLE_INVENTORY_USER, ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.stock_day_book", "Stock Day Book", FEATURE_INVENTORY, "reports.inventory.stock_day_book.view", "reports.inventory.analysis", "/reports/inventory/stock-day-book", "calendar-days", 60, default_role_codes=(ROLE_INVENTORY_USER, ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.stock_book_summary", "Stock Book Summary", FEATURE_INVENTORY, "reports.inventory.stock_book_summary.view", "reports.inventory.analysis", "/reports/inventory/stock-book-summary", "book-open", 70, default_role_codes=(ROLE_INVENTORY_USER, ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.stock_book_detail", "Stock Book Detail", FEATURE_INVENTORY, "reports.inventory.stock_book_detail.view", "reports.inventory.analysis", "/reports/inventory/stock-book-detail", "book-open-text", 80, default_role_codes=(ROLE_INVENTORY_USER, ROLE_FINANCIAL_REPORT_VIEWER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.non_moving_stock", "Non-Moving Stock", FEATURE_INVENTORY, "reports.inventory.non_moving_stock.view", "reports.inventory.controls", "/reports/inventory/non-moving-stock", "pause-circle", 10, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.reorder_status", "Reorder Status", FEATURE_INVENTORY, "reports.inventory.reorder_status.view", "reports.inventory.controls", "/reports/inventory/reorder-status", "refresh-cw", 20, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.slow_moving_dead_stock", "Slow Moving vs Dead Stock", FEATURE_INVENTORY, "reports.inventory.slow_moving_dead_stock.view", "reports.inventory.controls", "/reports/inventory/slow-moving-dead-stock", "timer-off", 30, default_role_codes=(ROLE_INVENTORY_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.production_order", "Manufacturing Work Order", FEATURE_MANUFACTURING, "manufacturing.workorder.view", "reports.inventory", "/productionorder", "factory", 70, default_role_codes=(ROLE_MANUFACTURING_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.manufacturing_browser", "Manufacturing Browser", FEATURE_MANUFACTURING, "manufacturing.workorder.view", "reports.inventory", "/manufacturing-work-order-list", "list-checks", 80, default_role_codes=(ROLE_MANUFACTURING_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.manufacturing_boms", "Manufacturing BOMs", FEATURE_MANUFACTURING, "manufacturing.bom.view", "reports.inventory", "/manufacturing-boms", "git-branch", 90, default_role_codes=(ROLE_MANUFACTURING_USER, ROLE_ADMIN)),
    MenuSpec("reports.inventory.manufacturing_routes", "Manufacturing Routes", FEATURE_MANUFACTURING, "manufacturing.route.view", "reports.inventory", "/manufacturing-routes", "route", 100, default_role_codes=(ROLE_MANUFACTURING_USER, ROLE_ADMIN)),
    MenuSpec("admin.access", "Access and Users", FEATURE_RBAC, "admin.user.view", "admin", icon="users", sort_order=10, menu_type="group", default_role_codes=(ROLE_ADMIN, ROLE_ENTITY_SUPER_ADMIN), access_mode="setup"),
    MenuSpec("admin.configuration", "Configuration", FEATURE_RBAC, "admin.invoice_custom_fields.view", "admin", icon="settings", sort_order=20, menu_type="group", default_role_codes=(ROLE_ADMIN, ROLE_ENTITY_SUPER_ADMIN), access_mode="setup"),
    MenuSpec("admin.module_controls", "Module Controls", FEATURE_RBAC, "admin.business_settings.view", "admin", icon="sliders-horizontal", sort_order=30, menu_type="group", default_role_codes=(ROLE_ADMIN, ROLE_ENTITY_SUPER_ADMIN), access_mode="setup"),
    MenuSpec("admin.role_list", "Roles", FEATURE_RBAC, "admin.role.view", "admin.access", "/rbacmanagement?tab=roles", "shield", 10, default_role_codes=(ROLE_ADMIN, ROLE_ENTITY_SUPER_ADMIN), access_mode="setup"),
    MenuSpec("admin.users", "Users", FEATURE_RBAC, "admin.user.view", "admin.access", "/user", "user-cog", 20, default_role_codes=(ROLE_ADMIN, ROLE_ENTITY_SUPER_ADMIN), access_mode="setup"),
    MenuSpec("admin.rbac_management", "RBAC Management", FEATURE_RBAC, "admin.role_access.update", "admin.access", "/rbacmanagement", "shield-check", 30, default_role_codes=(ROLE_ADMIN, ROLE_ENTITY_SUPER_ADMIN), access_mode="setup"),
    MenuSpec("admin.change_password", "Change Password", FEATURE_RBAC, "admin.user.view", "admin.access", "/changepassword", "key-round", 40, default_role_codes=(ROLE_ADMIN, ROLE_ENTITY_SUPER_ADMIN), access_mode="setup"),
    MenuSpec("admin.invoice_custom_fields", "Invoice Custom Fields", FEATURE_RBAC, "admin.invoice_custom_fields.view", "admin.configuration", "/invoicecustomfields", "form-input", 10, default_role_codes=(ROLE_ADMIN,), access_mode="setup"),
    MenuSpec("admin.business_settings", "Business Settings", FEATURE_FINANCIAL, "admin.business_settings.view", "admin.module_controls", "/businesssettings", "settings", 10, default_role_codes=(ROLE_ADMIN,), access_mode="setup"),
    MenuSpec("admin.manufacturing_settings", "Manufacturing Settings", FEATURE_MANUFACTURING, "manufacturing.settings.view", "admin.module_controls", "/manufacturingsettings", "settings", 40, default_role_codes=(ROLE_ADMIN, ROLE_MANUFACTURING_USER), access_mode="setup"),
    MenuSpec("admin.commerce_promotions", "Commerce Promotions", FEATURE_SALES, "commerce.promotion.view", "admin.module_controls", "/commerce-promotions", "tags", 50, default_role_codes=(ROLE_ADMIN, ROLE_SALES_USER), access_mode="setup"),
    MenuSpec("payroll.attendance_summaries", "Attendance Summaries", FEATURE_PAYROLL, "payroll.attendance_summaries.view", "payroll", "/payroll/attendance-summaries", "calendar-days", 10, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.attendance_adjustments", "Attendance Adjustments", FEATURE_PAYROLL, "payroll.attendance_adjustments.view", "payroll", "/payroll/attendance-adjustments", "calendar-clock", 20, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.statutory_schemes", "Statutory Schemes", FEATURE_PAYROLL, "payroll.policies.view", "payroll", "/payroll/statutory/schemes", "shield-check", 30, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.policies", "Payroll Policies", FEATURE_PAYROLL, "payroll.policies.view", "payroll", "/payroll/policies", "scroll-text", 40, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.statutory_rules", "Statutory Rules", FEATURE_PAYROLL, "payroll.policies.view", "payroll", "/payroll/statutory/rules", "gavel", 50, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.statutory_registrations", "Statutory Registrations", FEATURE_PAYROLL, "payroll.policies.view", "payroll", "/payroll/statutory/registrations", "badge-check", 60, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.contract_statutory_profiles", "Contract Statutory Profiles", FEATURE_PAYROLL, "payroll.contract_statutory_profiles.view", "payroll", "/payroll/statutory/contract-profiles", "id-card", 70, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.recurring_pay_items", "Recurring Pay Items", FEATURE_PAYROLL, "payroll.recurring_pay_items.view", "payroll", "/payroll/recurring-pay-items", "repeat", 80, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.one_time_pay_items", "One-Time Pay Items", FEATURE_PAYROLL, "payroll.one_time_pay_items.view", "payroll", "/payroll/one-time-pay-items", "badge-plus", 90, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.salary_structures", "Salary Structures", FEATURE_PAYROLL, "payroll.structure.view", "payroll", "/payroll/salary-structures", "layers", 100, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.contract_profiles", "Contract Payroll Profiles", FEATURE_PAYROLL, "payroll.contract_profile.view", "payroll", "/payroll/contract-profiles", "id-card", 110, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.contract_tax_declarations", "Contract Tax Declarations", FEATURE_PAYROLL, "payroll.contract_profile.view", "payroll", "/payroll/contract-tax-declarations", "file-text", 120, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.contract_input_snapshots", "Contract Input Snapshots", FEATURE_PAYROLL, "payroll.contract_profile.view", "payroll", "/payroll/contract-input-snapshots", "camera", 130, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.runtime_readiness", "Payroll Readiness", FEATURE_PAYROLL, "payroll.run.view", "payroll", "/payroll/runtime/readiness", "check-circle", 140, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.approval_policies", "Approval Policies", FEATURE_PAYROLL, "payroll.policies.view", "payroll", "/payroll/approval-policies", "shield-check", 150, default_role_codes=(ROLE_PAYROLL_APPROVER, ROLE_ADMIN)),
    MenuSpec("payroll.onboarding", "Onboarding", FEATURE_PAYROLL, "payroll.run.view", "payroll", "/payroll/onboarding", "rocket", 160, default_role_codes=(ROLE_PAYROLL_USER, ROLE_ADMIN)),
    MenuSpec("payroll.global_component_groups", "Global Component Groups", FEATURE_PAYROLL, "payroll.global_component_group.view", "payroll", "/payroll/global/component-groups", "folder-tree", 170, default_role_codes=(ROLE_PAYROLL_USER, ROLE_ADMIN)),
    MenuSpec("payroll.global_components", "Global Components", FEATURE_PAYROLL, "payroll.global_component.view", "payroll", "/payroll/global/components", "puzzle", 180, default_role_codes=(ROLE_PAYROLL_USER, ROLE_ADMIN)),
    MenuSpec("payroll.global_salary_templates", "Global Salary Templates", FEATURE_PAYROLL, "payroll.global_salary_template.view", "payroll", "/payroll/global/salary-templates", "file-stack", 190, default_role_codes=(ROLE_PAYROLL_USER, ROLE_ADMIN)),
    MenuSpec("payroll.workspace", "Payroll Workspace", FEATURE_PAYROLL, "payroll.run.view", "payroll", "/payroll", "wallet-cards", 200, default_role_codes=(ROLE_PAYROLL_USER, ROLE_PAYROLL_APPROVER, ROLE_PAYROLL_FINANCE_MANAGER, ROLE_ADMIN)),
    MenuSpec("hrms.organization_units", "Organization Units", FEATURE_HRMS, "hrms.organization_unit.view", "hrms", "/hrms/organization-units", "network", 10, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.employees", "Employees", FEATURE_HRMS, "hrms.employee.view", "hrms", "/hrms/employees", "users", 20, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.contracts", "Employment Contracts", FEATURE_HRMS, "hrms.employment_contract.view", "hrms", "/hrms/contracts", "file-signature", 30, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.shifts", "Shifts", FEATURE_HRMS, "hrms.shift.view", "hrms", "/hrms/shifts", "clock", 40, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.holiday_calendars", "Holiday Calendars", FEATURE_HRMS, "hrms.holiday_calendar.view", "hrms", "/hrms/holiday-calendars", "calendar", 50, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.onboarding", "Onboarding", FEATURE_HRMS, "hrms.onboarding.view", "hrms", "/hrms/onboarding", "rocket", 60, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.attendance", "Attendance", FEATURE_HRMS, "hrms.attendance_entry.view", "hrms", "/hrms/attendance", "calendar-check", 70, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.attendance_monthly_summary", "Attendance Summary", FEATURE_HRMS, "hrms.attendance_summary.view", "hrms", "/hrms/attendance-monthly-summary", "calendar-days", 80, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.attendance_import", "Attendance Import", FEATURE_HRMS, "hrms.attendance_import_batch.view", "hrms", "/hrms/attendance-import", "upload", 90, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.attendance_approval_close", "Attendance Approval & Close", FEATURE_HRMS, "hrms.attendance_approval.view", "hrms", "/hrms/attendance-approval-close", "badge-check", 100, default_role_codes=(ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.attendance_daily_grid", "Daily Attendance Grid", FEATURE_HRMS, "hrms.attendance_summary.view", "hrms", "/hrms/attendance-daily-grid", "table", 110, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.leave", "Leave", FEATURE_HRMS, "hrms.leave_application.view", "hrms", "/hrms/leave", "calendar-minus", 120, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.leave_policy_rules", "Leave Policy Rules", FEATURE_HRMS, "hrms.leave_policy.view", "hrms", "/hrms/leave-policy-rules", "scroll-text", 130, default_role_codes=(ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.leave_balance_ledger", "Leave Balance Ledger", FEATURE_HRMS, "hrms.leave_ledger.view", "hrms", "/hrms/leave-balance-ledger", "book-open", 140, default_role_codes=(ROLE_HRMS_USER, ROLE_HRMS_APPROVER, ROLE_ADMIN)),
    MenuSpec("hrms.ess_leave_application", "ESS Leave Application", FEATURE_HRMS, "hrms.leave_application.view", "hrms", "/hrms/ess-leave-application", "send", 150, default_role_codes=(ROLE_HRMS_USER, ROLE_ADMIN)),
    MenuSpec("hrms.my_attendance", "My Attendance", FEATURE_HRMS, "hrms.attendance_entry.view", "hrms", "/hrms/employee-attendance-view", "calendar-user", 160, default_role_codes=(ROLE_HRMS_USER, ROLE_ADMIN)),
    MenuSpec("hrms.leave_approval", "Leave Approval", FEATURE_HRMS, "hrms.leave_application.view", "hrms", "/hrms/manager-leave-approval", "badge-check", 170, default_role_codes=(ROLE_HRMS_APPROVER, ROLE_ADMIN)),
)


ROUTE_PERMISSION_CODES = frozenset(
    {
        "admin.branch.view",
        "admin.invoice_custom_fields.view",
        "admin.role.view",
        "admin.user.view",
        "accounts.account_head.view",
        "accounts.account_type.view",
        "assets.asset.view",
        "assets.asset_dashboard.view",
        "assets.asset_events.view",
        "assets.asset_history.view",
        "assets.asset_location_custodian.view",
        "assets.category.view",
        "assets.depreciation_run.view",
        "assets.depreciation_schedule.view",
        "assets.fixed_asset_register.view",
        "assets.settings.view",
        "capital_distribution.policy.view",
        "capital_distribution.run.view",
        "capital_distribution.setup.view",
        "commerce.line_tester.view",
        "commerce.promotion.view",
        "compliance.tcs_config.view",
        "compliance.tcs_config.create",
        "compliance.tcs_config.delete",
        "compliance.tcs_config.export",
        "compliance.tcs_config.import",
        "compliance.tcs_config.update",
        "compliance.tcs_party_profile.create",
        "compliance.tcs_party_profile.delete",
        "compliance.tcs_party_profile.update",
        "compliance.tcs_party_profile.view",
        "compliance.tcs_return_27eq.file",
        "compliance.tcs_return_27eq.view",
        "compliance.tcs_rule.create",
        "compliance.tcs_rule.delete",
        "compliance.tcs_rule.export",
        "compliance.tcs_rule.import",
        "compliance.tcs_rule.update",
        "compliance.tcs_rule.view",
        "compliance.tcs_section.create",
        "compliance.tcs_section.delete",
        "compliance.tcs_section.export",
        "compliance.tcs_section.import",
        "compliance.tcs_section.update",
        "compliance.tcs_section.view",
        "compliance.tcs_statutory.view",
        "dashboard.analytics.view",
        "dashboard.home.view",
        "financial.account.create",
        "financial.account.delete",
        "financial.account.update",
        "financial.account.view",
        "financial.account_head.create",
        "financial.account_head.delete",
        "financial.account_head.update",
        "financial.account_head.view",
        "financial.account_type.create",
        "financial.account_type.delete",
        "financial.account_type.update",
        "financial.account_type.view",
        "financial.ledger.create",
        "financial.ledger.delete",
        "financial.ledger.update",
        "financial.ledger.view",
        "gst.reconciliation.view",
        "gst.tds.config.create",
        "gst.tds.config.edit",
        "gst.tds.config.update",
        "gst.tds.config.view",
        "hrms.attendance_approval.view",
        "hrms.attendance_entry.view",
        "hrms.attendance_import_batch.view",
        "hrms.attendance_payroll_period.view",
        "hrms.attendance_summary.view",
        "hrms.employee.view",
        "hrms.employment_contract.view",
        "hrms.holiday_calendar.view",
        "hrms.leave_application.view",
        "hrms.leave_ledger.view",
        "hrms.leave_policy.view",
        "hrms.onboarding.view",
        "hrms.organization_unit.view",
        "hrms.shift.view",
        "inventory.adjustment.view",
        "inventory.location.view",
        "inventory.settings.view",
        "inventory.transfer.view",
        "manufacturing.bom.view",
        "manufacturing.route.view",
        "manufacturing.settings.view",
        "manufacturing.workorder.cancel",
        "manufacturing.workorder.operate",
        "manufacturing.workorder.post",
        "manufacturing.workorder.qc_approve",
        "manufacturing.workorder.unpost",
        "manufacturing.workorder.view",
        "payments.payroll.handoff",
        "payroll.attendance_adjustments.view",
        "payroll.attendance_summaries.view",
        "payroll.component.manage",
        "payroll.component.view",
        "payroll.contract_profile.manage",
        "payroll.contract_profile.view",
        "payroll.contract_salary_assignment.view",
        "payroll.contract_statutory_profiles.view",
        "payroll.global_component.view",
        "payroll.global_component_group.view",
        "payroll.global_salary_template.view",
        "payroll.one_time_pay_items.view",
        "payroll.period.manage",
        "payroll.period.view",
        "payroll.policies.view",
        "payroll.recurring_pay_items.view",
        "payroll.run.manage",
        "payroll.run.payment_handoff",
        "payroll.run.view",
        "payroll.structure.manage",
        "payroll.structure.view",
        "posting.static_account_settings.bulk_upsert",
        "posting.static_account_settings.create",
        "posting.static_account_settings.delete",
        "posting.static_account_settings.edit",
        "posting.static_account_settings.update",
        "posting.static_account_settings.validate",
        "posting.static_account_settings.view",
        "purchase.credit_note.view",
        "purchase.debit_note.view",
        "purchase.invoice.view",
        "purchase.settings.view",
        "purchase.statutory.view",
        "reports.accounts_receivable_aging.view",
        "reports.accountspayableaging.view",
        "reports.balance_sheet.view",
        "reports.cash_book.view",
        "reports.cashbook.view",
        "reports.daybook.view",
        "reports.financial_hub.balance_sheet.view",
        "reports.financial_hub.bank_reconciliation.view",
        "reports.financial_hub.cashbook.view",
        "reports.financial_hub.controls_phase_one.view",
        "reports.financial_hub.daybook.view",
        "reports.financial_hub.gst_tds_compliance_center.view",
        "reports.financial_hub.ledger_book.view",
        "reports.financial_hub.ledger_summary.view",
        "reports.financial_hub.payables_hub.purchase_register.view",
        "reports.financial_hub.posting_setup.view",
        "reports.financial_hub.profit_loss.view",
        "reports.financial_hub.receivables_hub.collections_history.view",
        "reports.financial_hub.receivables_hub.credit_exposure.view",
        "reports.financial_hub.receivables_hub.customer_ledger_statement.view",
        "reports.financial_hub.receivables_hub.customer_outstanding.view",
        "reports.financial_hub.receivables_hub.open_items.view",
        "reports.financial_hub.receivables_hub.overdue_customers.view",
        "reports.financial_hub.receivables_hub.receivable_aging.view",
        "reports.financial_hub.receivables_hub.receivable_aging_detail.view",
        "reports.financial_hub.receivables_hub.receivables_exception_report.view",
        "reports.financial_hub.settings.view",
        "reports.financial_hub.tcs_compliance_center.view",
        "reports.financial_hub.tds_compliance_center.view",
        "reports.financial_hub.trial_balance.view",
        "reports.financial_hub.view",
        "reports.financial_hub.year_end_close.view",
        "reports.gst.view",
        "reports.gst_compliance_center.view",
        "reports.gst_exception_dashboard.view",
        "reports.gstr1_gstr3b_reconciliation.view",
        "reports.gstr1report.view",
        "reports.gstr3b.view",
        "reports.gstr9.view",
        "reports.income_expenditure.view",
        "reports.inventory.location_stock.view",
        "reports.inventory.non_moving_stock.view",
        "reports.inventory.reorder_status.view",
        "reports.inventory.slow_moving_dead_stock.view",
        "reports.inventory.stock_aging.view",
        "reports.inventory.stock_book_detail.view",
        "reports.inventory.stock_book_summary.view",
        "reports.inventory.stock_day_book.view",
        "reports.inventory.stock_ledger.view",
        "reports.inventory.stock_movement.view",
        "reports.inventory.stock_summary.view",
        "reports.inventory.view",
        "reports.ledger_book.view",
        "reports.ledgersummary.view",
        "reports.outstanding.view",
        "reports.apglreconciliation.view",
        "reports.payables.ap_compliance_aging.view",
        "reports.payables.ap_payment_forecast.view",
        "reports.payables.duplicate_anomalous_bill_detection.view",
        "reports.payables.grn_invoice_posting_exceptions.view",
        "reports.payables.settings.view",
        "reports.payables.upcoming_payments_calendar.view",
        "reports.payables.vendor_reconciliation_statement.view",
        "reports.payables.view",
        "reports.payablesclosepack.view",
        "reports.payroll.view",
        "reports.purchase_book.view",
        "reports.purchase_register.view",
        "reports.purchasebook.view",
        "reports.sales_book.view",
        "reports.sales_register.view",
        "reports.tcsfilingpack.view",
        "reports.tcsledgerreport.view",
        "reports.tcs_ca_pack.export",
        "reports.tcs_filing_pack.export",
        "reports.tcs_workspace.export",
        "reports.tds.view",
        "reports.tradingaccountstatement.view",
        "reports.trial_balance.view",
        "reports.vendorbalanceexceptions.view",
        "reports.vendorledgerstatement.view",
        "reports.vendornoteregister.view",
        "reports.vendoroutstanding.view",
        "reports.vendorsettlementhistory.view",
        "retail.ticket.view",
        "sales.credit_note.view",
        "sales.debit_note.view",
        "sales.invoice.view",
        "sales.settings.view",
        "tcs.config.view",
        "tcs.config.create",
        "tcs.config.delete",
        "tcs.config.edit",
        "tcs.config.export",
        "tcs.config.import",
        "tcs.config.update",
        "tcs.filing_pack.view",
        "tcs.ledger_report.view",
        "tcs.menu.access",
        "tcs.party_profile.create",
        "tcs.party_profile.delete",
        "tcs.party_profile.update",
        "tcs.party_profile.view",
        "tcs.party_profiles.view",
        "tcs.partyprofile.create",
        "tcs.partyprofile.delete",
        "tcs.partyprofile.edit",
        "tcs.partyprofile.update",
        "tcs.partyprofile.view",
        "tcs.return_27eq.view",
        "tcs.rule.create",
        "tcs.rule.delete",
        "tcs.rule.export",
        "tcs.rule.import",
        "tcs.rule.update",
        "tcs.rule.view",
        "tcs.rules.create",
        "tcs.rules.delete",
        "tcs.rules.view",
        "tcs.section.create",
        "tcs.section.delete",
        "tcs.section.export",
        "tcs.section.import",
        "tcs.section.update",
        "tcs.section.view",
        "tcs.sections.create",
        "tcs.sections.delete",
        "tcs.sections.view",
        "treasury.payment_batch.view",
        "treasury.setup.view",
        "voucher.bank.view",
        "voucher.cash.view",
        "voucher.journal.view",
        "voucher.payment.view",
        "voucher.payment_settings.view",
        "voucher.receipt.view",
        "voucher.receipt_settings.view",
        "voucher.settings.view",
    }
)


def feature_for_permission_code(permission_code: str) -> str:
    if permission_code.startswith("hrms."):
        return FEATURE_HRMS
    if permission_code.startswith("payroll.") or permission_code.startswith("payments.payroll."):
        return FEATURE_PAYROLL
    if permission_code.startswith("treasury."):
        return FEATURE_TREASURY
    if permission_code.startswith("assets."):
        return FEATURE_ASSETS
    if permission_code.startswith("inventory.") or permission_code.startswith("reports.inventory."):
        return FEATURE_INVENTORY
    if permission_code.startswith("manufacturing."):
        return FEATURE_MANUFACTURING
    if permission_code.startswith("sales.") or permission_code.startswith("retail.") or permission_code.startswith("commerce."):
        return FEATURE_SALES
    if permission_code.startswith("purchase."):
        return FEATURE_PURCHASE
    if permission_code.startswith("reports.payables.") or permission_code in {
        "reports.apglreconciliation.view",
        "reports.accountspayableaging.view",
        "reports.payablesclosepack.view",
        "reports.vendorbalanceexceptions.view",
        "reports.vendorledgerstatement.view",
        "reports.vendornoteregister.view",
        "reports.vendoroutstanding.view",
        "reports.vendorsettlementhistory.view",
    }:
        return FEATURE_PAYABLES
    if permission_code.startswith("reports.financial_hub.payables_hub."):
        return FEATURE_PAYABLES
    if permission_code.startswith("reports.financial_hub.receivables_hub.") or permission_code in {
        "reports.accounts_receivable_aging.view",
        "reports.outstanding.view",
    }:
        return FEATURE_RECEIVABLES
    if permission_code.startswith("gst.") or permission_code.startswith("reports.gst") or permission_code.startswith("reports.gstr"):
        return FEATURE_GST_COMPLIANCE
    if "gst_tds" in permission_code:
        return FEATURE_GST_COMPLIANCE
    if permission_code.startswith("tcs.") or permission_code.startswith("compliance.") or "tcs_compliance" in permission_code or "tds_compliance" in permission_code:
        return FEATURE_COMPLIANCE
    if permission_code.startswith("catalog."):
        return FEATURE_CATALOG
    if permission_code.startswith("admin."):
        return FEATURE_RBAC
    if permission_code.startswith("reports.") or permission_code.startswith("dashboard."):
        return FEATURE_REPORTING
    return FEATURE_FINANCIAL


ROUTE_PERMISSION_SPECS = tuple(
    PermissionSpec(code=code, feature_code=feature_for_permission_code(code))
    for code in sorted(ROUTE_PERMISSION_CODES)
)


LEGACY_MENU_CODES_TO_DISABLE = frozenset(
    {
        "inventory",
        "manufacturing",
        "masters",
        "payroll.components",
        "payroll.dashboard",
        "payroll.periods",
        "payroll.reports",
        "payroll.runs",
        "reports.cashbooksummary",
        "reports.hub",
        "reports.interestcalculatorindividualreport",
    }
)


LEGACY_DUPLICATE_MENU_CODES_TO_DISABLE = frozenset(
    {
        "accounts.financialmaster.accountheads",
        "accounts.financialmaster.accounttypes",
        "accounts.financialmaster.accounts",
        "accounts.financialmaster.ledgers",
        "admin.role",
        "reports.ledgerbook",
        "reports.ledgersummary",
    }
)


LEGACY_ROUTE_PREFIXES_TO_KEEP_OUT_OF_MENUS = (
    "/assetmaster",
    "/assetcategorymaster",
    "/depreciationrun",
    "/financialmaster/",
    "/saleschargetypes",
    "/purchasechargetypes",
)


def features_for_packages(package_codes: Iterable[str]) -> frozenset[str]:
    features: set[str] = set()
    for package_code in package_codes:
        features.update(SUBSCRIPTION_PACKAGE_FEATURES.get(package_code, ()))
    return frozenset(features)


def role_specs_for_features(feature_codes: Iterable[str]) -> tuple[RoleSpec, ...]:
    feature_set = set(feature_codes)
    role_specs = []
    for spec in ROLE_SPECS:
        if spec.code in {ROLE_ENTITY_SUPER_ADMIN, ROLE_ADMIN}:
            role_specs.append(spec)
            continue
        if spec.created_for_features.intersection(feature_set):
            role_specs.append(spec)
    return tuple(role_specs)


def menu_specs_for_features(feature_codes: Iterable[str]) -> tuple[MenuSpec, ...]:
    feature_set = set(feature_codes)
    visible_specs = []
    for spec in MENU_SPECS:
        if spec.feature_code in feature_set:
            visible_specs.append(spec)
    return tuple(visible_specs)


def permission_codes_for_features(feature_codes: Iterable[str]) -> frozenset[str]:
    feature_set = set(feature_codes)
    menu_permission_codes = {
        spec.permission_code
        for spec in menu_specs_for_features(feature_set)
    }
    route_permission_codes = {
        spec.code
        for spec in ROUTE_PERMISSION_SPECS
        if spec.feature_code in feature_set
    }
    admin_management_permission_codes = ADMIN_MANAGEMENT_PERMISSION_CODES if FEATURE_RBAC in feature_set else frozenset()
    return frozenset(
        menu_permission_codes
        | route_permission_codes
        | admin_management_permission_codes
        | (UNIVERSAL_LANDING_PERMISSION_CODES if feature_set else frozenset())
    )
