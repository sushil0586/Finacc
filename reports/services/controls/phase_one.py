from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.profile_access import account_pan
from payments.models.payment_core import PaymentVoucherHeader
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr3b.services import Gstr3bSummaryService
from reports.services.gst_exception_dashboard import build_gst_exception_dashboard
from reports.services.gst_reconciliation import build_gstr1_vs_gstr3b_reconciliation
from reports.services.controls.opening_policy import resolve_opening_policy, summarize_opening_policy
from withholding.models import EntityPartyTaxProfile, TcsCollection, TcsComputation, WithholdingSection


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


def _iso_date(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "date"):
        try:
            value = value.date()
        except Exception:
            pass
    return str(value)


def _q2(value) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _tcs_counts(entity_id: int, entityfin_id: int | None, subentity_id: int | None, from_date: str, to_date: str) -> dict:
    qs = (
        TcsComputation.objects.filter(entity_id=entity_id, doc_date__gte=from_date, doc_date__lte=to_date)
        .exclude(status__in=[TcsComputation.Status.DRAFT, TcsComputation.Status.REVERSED])
        .prefetch_related("collections__deposit_allocations__deposit")
    )
    if entityfin_id:
        qs = qs.filter(entityfin_id=entityfin_id)
    if subentity_id:
        qs = qs.filter(subentity_id=subentity_id)

    total_rows = 0
    missing_section = 0
    pending_collection = 0
    pending_deposit = 0
    no_computed_tcs = 0
    total_gap = Decimal("0.00")

    for comp in qs:
        total_rows += 1
        if not comp.section_id:
            missing_section += 1
        comp_tcs = _q2(comp.tcs_amount)
        collected = Decimal("0.00")
        deposited = Decimal("0.00")
        for col in comp.collections.all():
            if col.status == TcsCollection.Status.CANCELLED:
                continue
            collected += _q2(col.tcs_collected_amount)
            for alloc in col.deposit_allocations.all():
                dep = alloc.deposit
                dep_status = str(getattr(dep, "status", "") or "").upper()
                if dep_status in {"CONFIRMED", "FILED"}:
                    deposited += _q2(alloc.allocated_amount)
        if comp_tcs <= Decimal("0.00"):
            no_computed_tcs += 1
            continue
        if _q2(comp_tcs - collected) > Decimal("0.00"):
            pending_collection += 1
            total_gap += _q2(comp_tcs - collected)
        if _q2(collected - deposited) > Decimal("0.00"):
            pending_deposit += 1
            total_gap += _q2(collected - deposited)

    blockers = missing_section + pending_collection + pending_deposit
    review_items = no_computed_tcs
    status = "ready_to_file" if blockers == 0 and review_items == 0 else ("blocked" if blockers > 0 else "review")
    return {
        "status": status,
        "total_rows": total_rows,
        "blockers": blockers,
        "review_items": review_items,
        "pending_collection": pending_collection,
        "pending_deposit": pending_deposit,
        "missing_section": missing_section,
        "total_gap": str(_q2(total_gap)),
    }


def _tds_counts(entity_id: int, entityfin_id: int | None, subentity_id: int | None, from_date: str, to_date: str) -> dict:
    vouchers = PaymentVoucherHeader.objects.filter(entity_id=entity_id, voucher_date__gte=from_date, voucher_date__lte=to_date).exclude(
        status=PaymentVoucherHeader.Status.CANCELLED
    ).select_related("paid_to")
    if entityfin_id:
        vouchers = vouchers.filter(entityfinid_id=entityfin_id)
    if subentity_id:
        vouchers = vouchers.filter(subentity_id=subentity_id)

    rows = list(vouchers)
    party_ids = [row.paid_to_id for row in rows if row.paid_to_id]
    profile_map = {
        int(p.party_account_id): p
        for p in EntityPartyTaxProfile.objects.filter(entity_id=entity_id, party_account_id__in=party_ids, is_active=True)
    }
    section_ids = set()
    for voucher in rows:
        payload = voucher.workflow_payload if isinstance(voucher.workflow_payload, dict) else {}
        runtime = payload.get("withholding_runtime_result") if isinstance(payload.get("withholding_runtime_result"), dict) else {}
        sid = runtime.get("section_id")
        if sid:
            try:
                section_ids.add(int(sid))
            except Exception:
                pass
    section_map = {
        int(sec.id): str(sec.section_code or "").strip().upper()
        for sec in WithholdingSection.objects.filter(id__in=section_ids).only("id", "section_code")
    }

    target_sections = {"194A", "194N", "195"}
    total_rows = 0
    blockers = 0
    review_items = 0
    for voucher in rows:
        payload = voucher.workflow_payload if isinstance(voucher.workflow_payload, dict) else {}
        runtime = payload.get("withholding_runtime_result") if isinstance(payload.get("withholding_runtime_result"), dict) else {}
        withholding_cfg = payload.get("withholding") if isinstance(payload.get("withholding"), dict) else {}
        enabled = bool(runtime.get("enabled", withholding_cfg.get("enabled", False)))
        if not enabled:
            continue
        sid = runtime.get("section_id") or withholding_cfg.get("section_id")
        code = section_map.get(int(sid), "") if sid not in (None, "") else str(runtime.get("section_code") or "").strip().upper()
        if code and code not in target_sections:
            continue
        total_rows += 1
        pan = (account_pan(voucher.paid_to) or getattr(voucher.paid_to, "pan", None) or "").strip().upper()
        profile = profile_map.get(int(voucher.paid_to_id or 0))
        tax_identifier = str(getattr(profile, "tax_identifier", "") or "").strip()
        residency = str(getattr(profile, "residency_status", "") or "").strip().lower()
        amount = _q2(runtime.get("amount"))

        is_blocked = False
        is_review = False
        if not code:
            is_blocked = True
        elif code in {"194A", "194N"} and not pan:
            is_review = True
        elif code == "195":
            if not tax_identifier:
                is_blocked = True
            if residency and residency != "non_resident":
                is_blocked = True
        if amount <= Decimal("0.00"):
            is_review = True
        if is_blocked:
            blockers += 1
        elif is_review:
            review_items += 1
    status = "ready_to_file" if blockers == 0 and review_items == 0 else ("blocked" if blockers > 0 else "review")
    return {
        "status": status,
        "total_rows": total_rows,
        "blockers": blockers,
        "review_items": review_items,
    }


def _build_gst_compliance_snapshot(*, entity_id: int, entityfin_id: int | None, subentity_id: int | None) -> dict:
    if not entityfin_id:
        return {
            "status": "review",
            "status_label": "Review",
            "summary_cards": [
                {"label": "GST Blockers", "value": 0, "note": "Select a financial year for scoped checks", "tone": "warning"},
                {"label": "GST Review Items", "value": 0, "note": "Validation scope pending", "tone": "neutral"},
                {"label": "GST Advisories", "value": 0, "note": "Informational mismatches", "tone": "neutral"},
            ],
            "actions": [],
        }

    try:
        fin = EntityFinancialYear.objects.filter(pk=entityfin_id, entity_id=entity_id).only("finstartyear", "finendyear").first()
        from_date = _iso_date(getattr(fin, "finstartyear", None))
        to_date = _iso_date(getattr(fin, "finendyear", None))
        if not from_date or not to_date:
            return {
                "status": "review",
                "status_label": "Review",
                "summary_cards": [
                    {"label": "GST Blockers", "value": 0, "note": "Financial year dates unavailable", "tone": "warning"},
                    {"label": "GST Review Items", "value": 0, "note": "Validation scope pending", "tone": "neutral"},
                    {"label": "GST Advisories", "value": 0, "note": "Informational mismatches", "tone": "neutral"},
                ],
                "actions": [],
            }

        gstr1_service = Gstr1ReportService()
        gstr3b_service = Gstr3bSummaryService()
        params = {
            "entity": str(entity_id),
            "entityfinid": str(entityfin_id),
            "from_date": from_date,
            "to_date": to_date,
        }
        if subentity_id:
            params["subentity"] = str(subentity_id)
        gstr1_scope = gstr1_service.build_scope(params)
        gstr3b_scope = gstr3b_service.build_scope(params)
        gstr1_warnings = gstr1_service.validations(gstr1_scope)
        gstr3b_warnings = gstr3b_service.validations(gstr3b_scope)
        reconciliation = build_gstr1_vs_gstr3b_reconciliation(
            gstr1_summary=gstr1_service.summary(gstr1_scope),
            gstr3b_summary=gstr3b_service.build(gstr3b_scope),
            scope_params={
                "entityfinid": gstr1_scope.entityfinid_id,
                "subentity": gstr1_scope.subentity_id,
                "from_date": gstr1_scope.from_date,
                "to_date": gstr1_scope.to_date,
            },
            gstr1_scope=gstr1_scope,
        )
        payload = build_gst_exception_dashboard(
            gstr1_warnings=gstr1_warnings,
            gstr3b_warnings=gstr3b_warnings,
            reconciliation_payload=reconciliation,
            scope_params={
                "entityfinid": gstr1_scope.entityfinid_id,
                "subentity": gstr1_scope.subentity_id,
                "from_date": gstr1_scope.from_date,
                "to_date": gstr1_scope.to_date,
            },
        )
        overview = payload.get("overview", {})
        blockers = int(overview.get("blocking_exception_count") or 0)
        review_items = int(overview.get("total_exception_count") or 0) - blockers
        advisories = int(overview.get("reconciliation_advisory_count") or 0)
        status = "ready_to_file" if blockers == 0 and review_items == 0 else ("blocked" if blockers > 0 else "review")
        status_label = "Ready to File" if status == "ready_to_file" else ("Blocked" if status == "blocked" else "Review")
        tds = _tds_counts(entity_id, entityfin_id, subentity_id, from_date, to_date)
        tcs = _tcs_counts(entity_id, entityfin_id, subentity_id, from_date, to_date)

        actions = [
            {
                "label": "Open GST Blockers",
                "route": "/reports/compliance/gst-exception-dashboard",
                "params": {
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "from_date": from_date,
                    "to_date": to_date,
                    "tab": 1,
                    "focus": "blockers",
                },
            },
            {
                "label": "Open GST Reconciliation Gaps",
                "route": "/reports/compliance/gst-exception-dashboard",
                "params": {
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "from_date": from_date,
                    "to_date": to_date,
                    "tab": 3,
                    "focus": "reconciliation",
                },
            },
            {
                "label": "Open Purchase Statutory (TDS Blocked)",
                "route": "/purchasestatutory",
                "params": {
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "workspace": "overview",
                    "readiness_status": "blocked",
                    "tax_type": "IT_TDS",
                },
            },
            {
                "label": "Open Purchase Statutory (TDS Fix Now)",
                "route": "/purchasestatutory",
                "params": {
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "workspace": "overview",
                    "readiness_status": "fix_now",
                    "tax_type": "IT_TDS",
                },
            },
            {
                "label": "Open TCS Workspace (Blocked)",
                "route": "/tcsstatutory",
                "params": {
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "readiness": "blocked",
                },
            },
        ]
        if tcs["pending_collection"] > 0:
            actions.append(
                {
                    "label": "Open TCS Pending Collection",
                    "route": "/tcsstatutory",
                    "params": {
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "workspace_status": "COMPUTED_PENDING_COLLECTION",
                    },
                }
            )
        if tcs["pending_deposit"] > 0:
            actions.append(
                {
                    "label": "Open TCS Pending Deposit",
                    "route": "/tcsstatutory",
                    "params": {
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "workspace_status": "COLLECTED_PENDING_DEPOSIT",
                    },
                }
            )
        if tcs["missing_section"] > 0:
            actions.append(
                {
                    "label": "Open TCS Missing Section",
                    "route": "/tcsstatutory",
                    "params": {
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "section": "UNMAPPED",
                    },
                }
            )

        return {
            "status": status,
            "status_label": status_label,
            "summary_cards": [
                {"label": "GST Blockers", "value": blockers, "note": "Must be resolved before filing", "tone": "warning" if blockers else "neutral"},
                {"label": "GST Review Items", "value": max(review_items, 0), "note": "Need finance review", "tone": "accent" if review_items > 0 else "neutral"},
                {"label": "GST Advisories", "value": advisories, "note": "Informational reconciliation notes", "tone": "neutral"},
                {
                    "label": "Max Tax Gap",
                    "value": str(overview.get("max_reconciliation_tax_gap") or "0.00"),
                    "note": "Largest mismatch in total tax",
                    "tone": "neutral",
                },
                {
                    "label": "TDS Blockers",
                    "value": tds["blockers"],
                    "note": f"{tds['review_items']} review items across {tds['total_rows']} payment rows",
                    "tone": "warning" if tds["blockers"] else ("accent" if tds["review_items"] else "neutral"),
                },
                {
                    "label": "TCS Blockers",
                    "value": tcs["blockers"],
                    "note": f"{tcs['pending_collection']} pending collection · {tcs['pending_deposit']} pending deposit · {tcs['missing_section']} missing section",
                    "tone": "warning" if tcs["blockers"] else ("accent" if tcs["review_items"] else "neutral"),
                },
            ],
            "actions": actions,
        }
    except Exception:
        return {
            "status": "review",
            "status_label": "Review",
            "summary_cards": [
                {"label": "GST Blockers", "value": 0, "note": "Compliance snapshot unavailable", "tone": "warning"},
                {"label": "GST Review Items", "value": 0, "note": "Retry after data refresh", "tone": "neutral"},
                {"label": "GST Advisories", "value": 0, "note": "No advisory snapshot", "tone": "neutral"},
            ],
            "actions": [],
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
                    "status": "available",
                    "status_label": "Available",
                    "priority": 1,
                    "owner": "Finance Ops",
                    "summary": "Import statements, match bank lines against posted activity, and isolate timing differences.",
                    "why_it_matters": [
                        "Reduces month-end cleanup",
                        "Highlights unmatched items early",
                        "Creates a clear reconciliation trail",
                    ],
                    "deliverables": [
                        "Statement import and matching workspace",
                        "Unmatched item queue and audit trail",
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
    gst_compliance = _build_gst_compliance_snapshot(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    )
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
            {
                "label": "Compliance Status",
                "value": gst_compliance["status_label"],
                "note": "GST readiness from exception and reconciliation checks",
                "tone": "warning" if gst_compliance["status"] == "blocked" else "accent" if gst_compliance["status"] == "review" else "neutral",
            },
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
        "compliance_readiness": gst_compliance,
    }
