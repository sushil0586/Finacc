from __future__ import annotations

from collections import OrderedDict


DASHBOARD_CODE = "home"
DASHBOARD_NAME = "Command Center"
DASHBOARD_PHASE = 0
DASHBOARD_PAGE_PERMISSION = "dashboard.home.view"
DASHBOARD_TYPE = "workspace"
DASHBOARD_TYPES = OrderedDict(
    [
        (
            "workspace",
            {
                "code": "workspace",
                "label": "Workspace",
                "description": "Action-first operational dashboard.",
            },
        ),
        (
            "analytics",
            {
                "code": "analytics",
                "label": "Analytics",
                "description": "Visual summary dashboard.",
            },
        ),
    ]
)


FILTER_GROUPS = [
    {
        "code": "context",
        "label": "Context",
        "filters": ["entity", "entityfinid", "subentity"],
        "description": "Select the company, fiscal year, and location scope.",
    },
    {
        "code": "time",
        "label": "Time",
        "filters": ["as_of_date", "from_date", "to_date"],
        "description": "Control the date snapshot or analysis range.",
    },
    {
        "code": "search",
        "label": "Search",
        "filters": ["currency", "search"],
        "description": "Narrow the dashboard to a specific currency or keyword.",
    },
]


FILTER_CATALOG = [
    {
        "code": "entity",
        "label": "Entity",
        "type": "entity",
        "group": "context",
        "required": True,
        "default_source": "request",
        "ui_control": "entity-picker",
        "help_text": "Primary company scope for every dashboard tile.",
    },
    {
        "code": "entityfinid",
        "label": "Financial Year",
        "type": "entity_financial_year",
        "group": "context",
        "required": False,
        "default_source": "latest_open_financial_year",
        "ui_control": "financial-year-picker",
        "help_text": "Defaults to the latest open or active financial year for the selected entity.",
    },
    {
        "code": "subentity",
        "label": "Sub-Entity",
        "type": "subentity",
        "group": "context",
        "required": False,
        "default_source": "head_office_or_first_active_subentity",
        "ui_control": "subentity-picker",
        "help_text": "Branch, depot, warehouse, or head office context.",
    },
    {
        "code": "as_of_date",
        "label": "As of Date",
        "type": "date",
        "group": "time",
        "required": False,
        "default_source": "today",
        "ui_control": "date-picker",
        "help_text": "Snapshot date for aging, balances, and risk cards.",
    },
    {
        "code": "from_date",
        "label": "From Date",
        "type": "date",
        "group": "time",
        "required": False,
        "default_source": None,
        "ui_control": "date-picker",
        "help_text": "Optional lower bound for range-based widgets.",
    },
    {
        "code": "to_date",
        "label": "To Date",
        "type": "date",
        "group": "time",
        "required": False,
        "default_source": None,
        "ui_control": "date-picker",
        "help_text": "Optional upper bound for range-based widgets.",
    },
    {
        "code": "currency",
        "label": "Currency",
        "type": "text",
        "group": "search",
        "required": False,
        "default_source": None,
        "ui_control": "text",
        "help_text": "Optional currency filter when a user needs a single-currency view.",
    },
    {
        "code": "search",
        "label": "Search",
        "type": "text",
        "group": "search",
        "required": False,
        "default_source": None,
        "ui_control": "search",
        "help_text": "Keyword filter for quick dashboard narrowing.",
    },
]


LAYOUT_ZONES = [
    {
        "code": "scope_bar",
        "label": "Scope Bar",
        "order": 1,
        "max_widgets": 1,
        "purpose": "Hold the active entity and time context.",
    },
    {
        "code": "attention_strip",
        "label": "Attention Strip",
        "order": 2,
        "max_widgets": 3,
        "purpose": "Surface urgent items that need immediate action.",
    },
    {
        "code": "summary_grid",
        "label": "Summary Grid",
        "order": 3,
        "max_widgets": 6,
        "purpose": "Show only the most important decision cards.",
    },
    {
        "code": "risk_panel",
        "label": "Risk Panel",
        "order": 4,
        "max_widgets": 4,
        "purpose": "Group aging, exposure, and working-capital risk cards.",
    },
    {
        "code": "control_panel",
        "label": "Control Panel",
        "order": 5,
        "max_widgets": 4,
        "purpose": "Keep close, reconciliation, and exception control visible.",
    },
    {
        "code": "activity_panel",
        "label": "Activity Panel",
        "order": 6,
        "max_widgets": 5,
        "purpose": "Show recent operational movement and updates.",
    },
    {
        "code": "quick_actions",
        "label": "Quick Actions",
        "order": 7,
        "max_widgets": 8,
        "purpose": "Offer one-click access to the most common workflows.",
    },
]


WIDGET_CATALOG = [
    {
        "code": "scope_context",
        "label": "Scope Context",
        "description": "Pinned scope summary for entity, financial year, and branch.",
        "zone": "scope_bar",
        "widget_type": "context",
        "phase": 0,
        "status": "active",
        "required_permissions": [DASHBOARD_PAGE_PERMISSION],
        "required_filters": ["entity"],
        "default_roles": ["owner", "finance_ops", "controller", "payroll"],
        "drilldown_target": None,
        "priority": 10,
    },
    {
        "code": "attention_strip",
        "label": "Attention Strip",
        "description": "Top-priority issues that need a decision or follow-up.",
        "zone": "attention_strip",
        "widget_type": "alert-rail",
        "phase": 0,
        "status": "active",
        "required_permissions": [DASHBOARD_PAGE_PERMISSION],
        "required_filters": ["entity", "as_of_date"],
        "default_roles": ["owner", "finance_ops", "controller", "payroll"],
        "drilldown_target": None,
        "priority": 20,
    },
    {
        "code": "summary_shell",
        "label": "Summary Shell",
        "description": "Reserved space for the few highest-value summary cards.",
        "zone": "summary_grid",
        "widget_type": "summary-shell",
        "phase": 0,
        "status": "active",
        "required_permissions": [DASHBOARD_PAGE_PERMISSION],
        "required_filters": ["entity", "as_of_date"],
        "default_roles": ["owner", "finance_ops", "controller"],
        "drilldown_target": None,
        "priority": 30,
    },
    {
        "code": "quick_actions_shell",
        "label": "Quick Actions Shell",
        "description": "Reserved shortcuts for the most common workflows.",
        "zone": "quick_actions",
        "widget_type": "action-shell",
        "phase": 0,
        "status": "active",
        "required_permissions": [DASHBOARD_PAGE_PERMISSION],
        "required_filters": ["entity"],
        "default_roles": ["owner", "finance_ops", "controller", "payroll"],
        "drilldown_target": None,
        "priority": 40,
    },
    {
        "code": "recent_activity_shell",
        "label": "Recent Activity Shell",
        "description": "Placeholder for recent documents and approvals.",
        "zone": "activity_panel",
        "widget_type": "activity-shell",
        "phase": 0,
        "status": "active",
        "required_permissions": [DASHBOARD_PAGE_PERMISSION],
        "required_filters": ["entity"],
        "default_roles": ["owner", "finance_ops", "controller"],
        "drilldown_target": None,
        "priority": 50,
    },
    {
        "code": "payables_risk",
        "label": "Payables Risk",
        "description": "Working-capital pressure from AP exposure and aging.",
        "zone": "risk_panel",
        "widget_type": "risk-card",
        "phase": 2,
        "status": "planned",
        "required_permissions": [
            "dashboard.home.view",
            "reports.vendoroutstanding.view",
            "reports.accountspayableaging.view",
        ],
        "required_filters": ["entity", "as_of_date"],
        "default_roles": ["owner", "finance_ops", "controller"],
        "drilldown_target": "reports.payables.payables_dashboard_summary",
        "priority": 60,
    },
    {
        "code": "receivables_risk",
        "label": "Receivables Risk",
        "description": "Cash conversion pressure from receivable exposure and aging.",
        "zone": "risk_panel",
        "widget_type": "risk-card",
        "phase": 2,
        "status": "planned",
        "required_permissions": [
            "dashboard.home.view",
            "reports.outstanding.view",
            "reports.accounts_receivable_aging.view",
        ],
        "required_filters": ["entity", "as_of_date"],
        "default_roles": ["owner", "finance_ops", "controller"],
        "drilldown_target": "reports.outstandingreport",
        "priority": 70,
    },
    {
        "code": "close_readiness",
        "label": "Close Readiness",
        "description": "Period close health, reconciliation, and exception control.",
        "zone": "control_panel",
        "widget_type": "control-card",
        "phase": 3,
        "status": "planned",
        "required_permissions": [
            "dashboard.home.view",
            "reports.apglreconciliation.view",
            "reports.payablesclosepack.view",
        ],
        "required_filters": ["entity", "as_of_date"],
        "default_roles": ["controller", "finance_ops", "owner"],
        "drilldown_target": "reports.payables.payables_close_readiness_summary",
        "priority": 80,
    },
    {
        "code": "payroll_snapshot",
        "label": "Payroll Snapshot",
        "description": "Payroll run status and readiness for payroll-enabled tenants.",
        "zone": "control_panel",
        "widget_type": "module-status",
        "phase": 3,
        "status": "planned",
        "required_permissions": ["dashboard.home.view", "payroll.dashboard.view"],
        "required_filters": ["entity"],
        "default_roles": ["payroll", "controller", "owner"],
        "drilldown_target": "payroll.dashboard.summary",
        "priority": 90,
    },
]


ROLE_VIEW_PROFILES = [
    {
        "code": "owner",
        "label": "Owner / CFO",
        "focus_widgets": ["attention_strip", "summary_shell", "payables_risk", "receivables_risk", "close_readiness"],
    },
    {
        "code": "finance_ops",
        "label": "Finance Operations",
        "focus_widgets": ["attention_strip", "summary_shell", "payables_risk", "receivables_risk", "recent_activity_shell"],
    },
    {
        "code": "controller",
        "label": "Controller",
        "focus_widgets": ["attention_strip", "close_readiness", "summary_shell", "recent_activity_shell"],
    },
    {
        "code": "payroll",
        "label": "Payroll",
        "focus_widgets": ["payroll_snapshot", "attention_strip", "recent_activity_shell"],
    },
]


def widget_codes() -> list[str]:
    return [widget["code"] for widget in WIDGET_CATALOG]


def widget_by_code() -> OrderedDict:
    return OrderedDict((widget["code"], widget) for widget in sorted(WIDGET_CATALOG, key=lambda item: item["priority"]))
