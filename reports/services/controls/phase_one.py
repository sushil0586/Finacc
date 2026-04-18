from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from entity.models import Entity, EntityFinancialYear, SubEntity
from reports.services.controls.opening_policy import resolve_opening_policy, summarize_opening_policy


@dataclass(frozen=True)
class ControlMetric:
    label: str
    value: str
    note: str | None = None
    tone: str = "neutral"


def _safe_label(value, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _resolve_scope(entity_id: int, entityfin_id: int | None = None, subentity_id: int | None = None) -> dict[str, str | int | None]:
    entity = Entity.objects.filter(pk=entity_id).only("id", "entityname", "trade_name", "short_name").first()
    entity_fin = (
        EntityFinancialYear.objects.filter(pk=entityfin_id, entity_id=entity_id).only("id", "desc", "year_code").first()
        if entityfin_id
        else None
    )
    subentity = (
        SubEntity.objects.filter(pk=subentity_id, entity_id=entity_id).only("id", "subentityname", "subentity_code").first()
        if subentity_id
        else None
    )

    entity_name = None
    if entity:
        entity_name = _safe_label(entity.trade_name or entity.short_name or entity.entityname, f"Entity {entity_id}")

    entityfin_name = None
    if entity_fin:
        entityfin_name = _safe_label(entity_fin.desc or entity_fin.year_code, f"FY {entity_fin.id}")

    subentity_name = None
    if subentity:
        subentity_name = _safe_label(subentity.subentityname, f"Subentity {subentity.id}")

    return {
        "entity_name": entity_name,
        "entityfin_name": entityfin_name,
        "subentity_name": subentity_name,
    }


def _control_sections() -> list[dict[str, object]]:
    return [
        {
            "key": "control_basics",
            "title": "Control Basics",
            "description": "Day-to-day safeguards that reduce manual follow-up and make finance operations auditable.",
            "cards": [
                {
                    "code": "bank_reconciliation",
                    "title": "Bank Reconciliation",
                    "status": "planned",
                    "status_label": "Planned",
                    "priority": 1,
                    "owner": "Finance Ops",
                    "summary": "Match bank statement lines against cashbook activity and isolate timing differences.",
                    "why_it_matters": [
                        "Reduces month-end cleanup",
                        "Highlights unmatched items early",
                        "Creates a clear reconciliation trail",
                    ],
                    "deliverables": [
                        "Statement import and matching rules",
                        "Unmatched item queue",
                        "Reconciliation summary and export",
                    ],
                },
                {
                    "code": "recurring_journals",
                    "title": "Recurring Journals",
                    "status": "planned",
                    "status_label": "Planned",
                    "priority": 2,
                    "owner": "Controller",
                    "summary": "Schedule repeat entries such as depreciation, rent, accruals, and loan interest.",
                    "why_it_matters": [
                        "Removes repetitive monthly posting",
                        "Standardizes adjustments",
                        "Supports consistent close routines",
                    ],
                    "deliverables": [
                        "Journal templates",
                        "Frequency and effective-date rules",
                        "Preview before posting",
                    ],
                },
                {
                    "code": "voucher_approvals",
                    "title": "Approval Workflow",
                    "status": "planned",
                    "status_label": "Planned",
                    "priority": 3,
                    "owner": "Approver",
                    "summary": "Control who can submit, review, approve, and post vouchers before accounting impact.",
                    "why_it_matters": [
                        "Improves segregation of duties",
                        "Adds maker-checker control",
                        "Keeps audit questions easy to answer",
                    ],
                    "deliverables": [
                        "Submit/approve/reject states",
                        "Role-based routing",
                        "Approval audit history",
                    ],
                },
            ],
        },
        {
            "key": "posting_setup",
            "title": "Posting Setup",
            "description": "A separate provisioning workspace that auto-creates the ledgers and mappings needed for opening carry-forward.",
            "cards": [
                {
                    "code": "posting_setup",
                    "title": "Automatic Posting Setup",
                    "status": "available",
                    "status_label": "Available",
                    "priority": 4,
                    "owner": "Posting",
                    "summary": "Review the ownership rows, then auto-provision the entity's opening ledgers and static mappings in a dedicated page.",
                    "why_it_matters": [
                        "Keeps onboarding clean and focused on ownership capture",
                        "Lets the posting engine own the final accounting identities",
                        "Makes partner and capital setup reviewable before activation",
                    ],
                    "deliverables": [
                        "Proposed ledger list",
                        "Auto-create or map destination ledgers",
                        "Posting admin reconciliation trail",
                    ],
                },
            ],
        },
        {
            "key": "close_operations",
            "title": "Close Operations",
            "description": "Utilities that help carry balances into the next year with clean controls and traceability.",
            "cards": [
                {
                    "code": "opening_policy",
                    "title": "Opening Policy",
                    "status": "available",
                    "status_label": "Available",
                    "priority": 4,
                    "owner": "Finance Lead",
                    "summary": "Configure how each entity carries balances forward into the next financial year.",
                    "why_it_matters": [
                        "Keeps year-opening behavior entity-specific",
                        "Supports single, grouped, or hybrid carry-forward styles",
                        "Avoids hidden assumptions in opening batch creation",
                    ],
                    "deliverables": [
                        "Entity opening policy JSON",
                        "Carry-forward toggle groups",
                        "Batch materialization strategy",
                    ],
                },
                {
                    "code": "opening_preview",
                    "title": "Opening Preview",
                    "status": "available",
                    "status_label": "Available",
                    "priority": 5,
                    "owner": "Finance Lead",
                    "summary": "Preview the carry-forward snapshot and destination year before any opening batch is generated.",
                    "why_it_matters": [
                        "Shows the next FY opening structure before posting",
                        "Makes carry-forward logic transparent to users",
                        "Keeps Phase 2 preview-only and audit friendly",
                    ],
                    "deliverables": [
                        "Opening preview API",
                        "Carry-forward tables",
                        "Destination FY planning",
                    ],
                },
                {
                    "code": "audit_trail",
                    "title": "Audit Trail",
                    "status": "planned",
                    "status_label": "Planned",
                    "priority": 6,
                    "owner": "Audit",
                    "summary": "Record who changed what, when, and from where for every material control event.",
                    "why_it_matters": [
                        "Supports audit review",
                        "Makes exception analysis faster",
                        "Improves change accountability",
                    ],
                    "deliverables": [
                        "Action log by entity and period",
                        "Diff-friendly before/after snapshots",
                        "Filterable event timeline",
                    ],
                },
                {
                    "code": "document_attachments",
                    "title": "Document Attachments",
                    "status": "planned",
                    "status_label": "Planned",
                    "priority": 7,
                    "owner": "Operations",
                    "summary": "Attach source documents to vouchers, reconciliations, and close items.",
                    "why_it_matters": [
                        "Reduces file hunting",
                        "Strengthens evidence trail",
                        "Helps with handover and review",
                    ],
                    "deliverables": [
                        "Upload/download/delete flow",
                        "Attachment metadata",
                        "Report-level drilldowns",
                    ],
                },
                {
                    "code": "year_end_close",
                    "title": "Year-End Close",
                    "status": "planned",
                    "status_label": "Planned",
                    "priority": 8,
                    "owner": "Finance Lead",
                    "summary": "Lock the old year, roll opening balances forward, and preserve a clean audit boundary.",
                    "why_it_matters": [
                        "Protects closed books",
                        "Creates a clean next-year opening",
                        "Shows whether temporary accounts were settled",
                    ],
                    "deliverables": [
                        "Close checklist and validation",
                        "Opening balance carry-forward",
                        "Retained earnings transfer",
                    ],
                },
            ],
        },
    ]


def build_phase_one_controls_hub(*, entity_id: int, entityfin_id: int | None = None, subentity_id: int | None = None) -> dict:
    scope_names = _resolve_scope(entity_id, entityfin_id, subentity_id)
    sections = _control_sections()
    opening_policy = resolve_opening_policy(entity_id)
    total_cards = sum(len(section["cards"]) for section in sections)
    planned_cards = total_cards
    available_cards = sum(1 for section in sections for card in section["cards"] if card["status"] == "available")
    return {
        "report_code": "phase_one_controls_hub",
        "report_name": "Financial Controls Phase 1",
        "report_eyebrow": "Financial Hub",
        "entity_id": entity_id,
        "entity_name": scope_names["entity_name"] or f"Entity {entity_id}",
        "entityfin_id": entityfin_id,
        "entityfin_name": scope_names["entityfin_name"] or "Current FY",
        "subentity_id": subentity_id,
        "subentity_name": scope_names["subentity_name"] or "All subentities",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary_cards": [
            {"label": "Utilities", "value": total_cards, "note": "Phase 1 control workstreams", "tone": "accent"},
            {"label": "Planned", "value": planned_cards, "note": "All controls start from a clean build", "tone": "warning"},
            {"label": "Available now", "value": available_cards, "note": "No legacy shortcuts used", "tone": "neutral"},
            {"label": "Sections", "value": len(sections), "note": "Daily control and close operations", "tone": "neutral"},
        ],
        "sections": sections,
        "opening_policy": opening_policy,
        "opening_policy_summary": summarize_opening_policy(opening_policy),
        "build_principles": [
            "No legacy screen reuse",
            "Control-first design",
            "Entity-aware from the start",
            "Audit trail ready",
        ],
        "next_steps": [
            "Posting setup workspace",
            "Opening policy configuration",
            "Bank reconciliation workspace",
            "Recurring journal scheduler",
            "Approval workflow shell",
            "Audit trail viewer",
            "Document attachment vault",
            "Year-end close wizard",
        ],
        "roadmap": [
            {"phase": "1", "title": "Control Foundation", "status": "current"},
            {"phase": "2", "title": "Close Process", "status": "planned"},
            {"phase": "3", "title": "Alerts and Exceptions", "status": "planned"},
            {"phase": "4", "title": "Forecasting and Variance", "status": "planned"},
        ],
    }
