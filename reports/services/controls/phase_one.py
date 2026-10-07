from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from django.db.models import Count, Q

from bank_reco.models import BankReconciliationRun
from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.models import FinancialSettings
from financial.profile_access import account_pan
from gst_reconciliation.models import GstReconciliationItem, GstReconciliationRun
from payments.models.payment_core import PaymentVoucherHeader
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr3b.services import Gstr3bSummaryService
from reports.services.controls.year_end_close import build_year_end_close_preview
from reports.services.gst_exception_dashboard import build_gst_exception_dashboard
from reports.services.gst_reconciliation import build_gstr1_vs_gstr3b_reconciliation
from reports.services.controls.opening_policy import resolve_opening_policy, summarize_opening_policy
from reports.services.controls.approval_workflow import build_approval_workflow_readiness
from reports.services.controls.audit_trail import build_audit_trail_readiness
from reports.services.controls.attachment_vault import build_attachment_vault_readiness
from reports.services.controls.recurring_journals import build_recurring_journal_readiness
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


def _build_control_compliance_snapshot(*, entity_id: int, entityfin_id: int | None, subentity_id: int | None) -> dict:
    """Return a bounded, persisted compliance snapshot for the controls landing page."""
    base_params = {
        "entityfinid": entityfin_id,
        "subentity": subentity_id,
    }
    actions = [
        {
            "label": "Open GST Reconciliation",
            "route": "/reports/compliance/gst-exception-dashboard",
            "params": {**base_params, "tab": 3, "focus": "reconciliation"},
        },
        {
            "label": "Open GST Blockers",
            "route": "/reports/compliance/gst-exception-dashboard",
            "params": {**base_params, "tab": 1, "focus": "blockers"},
        },
        {
            "label": "Open Purchase TDS",
            "route": "/purchasestatutory",
            "params": {**base_params, "workspace": "overview", "tax_type": "IT_TDS"},
        },
        {
            "label": "Open TCS Workspace",
            "route": "/tcsstatutory",
            "params": base_params,
        },
    ]
    if not entityfin_id:
        return {
            "status": "review",
            "status_label": "Review",
            "summary_cards": [
                {"label": "GST Reconciliation", "value": "Scope required", "note": "Select a financial year", "tone": "warning"},
                {"label": "GST Exceptions", "value": "-", "note": "Open the GST workspace for live detail", "tone": "neutral"},
                {"label": "TDS / TCS", "value": "Open reports", "note": "Use the statutory workspaces for current totals", "tone": "neutral"},
            ],
            "actions": actions,
            "snapshot_source": "persisted_reconciliation",
        }

    try:
        runs = GstReconciliationRun.objects.filter(entity_id=entity_id, entityfinid_id=entityfin_id, is_active=True)
        if subentity_id:
            runs = runs.filter(subentity_id=subentity_id)
        latest_run = runs.only("id", "status", "return_period", "updated_at").order_by("-updated_at", "-id").first()
        if latest_run is None:
            return {
                "status": "review",
                "status_label": "Review",
                "summary_cards": [
                    {"label": "GST Reconciliation", "value": "Not run", "note": "Run reconciliation to create a certified snapshot", "tone": "warning"},
                    {"label": "GST Exceptions", "value": "-", "note": "No persisted reconciliation result", "tone": "neutral"},
                    {"label": "TDS / TCS", "value": "Open reports", "note": "Use the statutory workspaces for current totals", "tone": "neutral"},
                ],
                "actions": actions,
                "snapshot_source": "persisted_reconciliation",
            }

        counts = latest_run.items.aggregate(
            mismatch_count=Count(
                "id",
                filter=Q(
                    match_status__in=[
                        GstReconciliationItem.MatchStatus.PARTIAL,
                        GstReconciliationItem.MatchStatus.MISMATCHED,
                        GstReconciliationItem.MatchStatus.DUPLICATE,
                    ]
                ),
            ),
            unmatched_count=Count(
                "id",
                filter=Q(
                    match_status__in=[
                        GstReconciliationItem.MatchStatus.MISSING_IN_BOOKS,
                        GstReconciliationItem.MatchStatus.MISSING_IN_RETURN,
                    ]
                ),
            ),
            pending_review_count=Count(
                "id",
                filter=Q(
                    resolution_status__in=[
                        GstReconciliationItem.ResolutionStatus.PENDING_REVIEW,
                        GstReconciliationItem.ResolutionStatus.ASSIGNED,
                        GstReconciliationItem.ResolutionStatus.REOPENED,
                    ]
                ),
            ),
        )
        exceptions = int(counts["mismatch_count"] or 0) + int(counts["unmatched_count"] or 0)
        pending_review = int(counts["pending_review_count"] or 0)
        is_failed = latest_run.status in {GstReconciliationRun.Status.FAILED, GstReconciliationRun.Status.REJECTED}
        status = "blocked" if is_failed or exceptions else "review" if pending_review else "ready_to_file"
        status_label = "Blocked" if status == "blocked" else "Review" if status == "review" else "Ready to File"
        period = str(latest_run.return_period or "latest period")
        return {
            "status": status,
            "status_label": status_label,
            "summary_cards": [
                {"label": "GST Reconciliation", "value": status_label, "note": f"Latest saved run: {period}", "tone": "warning" if status != "ready_to_file" else "neutral"},
                {"label": "GST Exceptions", "value": exceptions, "note": f"{pending_review} item(s) pending review", "tone": "warning" if exceptions else "neutral"},
                {"label": "TDS / TCS", "value": "Open reports", "note": "Use the statutory workspaces for current totals", "tone": "neutral"},
            ],
            "actions": actions,
            "snapshot_source": "persisted_reconciliation",
            "snapshot_run_id": latest_run.id,
            "snapshot_updated_at": latest_run.updated_at.isoformat() if latest_run.updated_at else None,
        }
    except Exception:
        return {
            "status": "review",
            "status_label": "Review",
            "summary_cards": [
                {"label": "GST Reconciliation", "value": "Unavailable", "note": "Open the GST workspace to retry", "tone": "warning"},
                {"label": "GST Exceptions", "value": "-", "note": "Persisted snapshot unavailable", "tone": "neutral"},
                {"label": "TDS / TCS", "value": "Open reports", "note": "Use the statutory workspaces for current totals", "tone": "neutral"},
            ],
            "actions": actions,
            "snapshot_source": "persisted_reconciliation",
        }


def _build_bank_reconciliation_snapshot(*, entity_id: int, entityfin_id: int | None, subentity_id: int | None) -> dict:
    actions = [
        {
            "label": "Open Bank Reconciliation",
            "route": "/bank-reco/dashboard",
            "params": {"entityfinid": entityfin_id, "subentity": subentity_id},
        },
        {
            "label": "Open Matching Workspace",
            "route": "/bank-reco/workspace",
            "params": {"entityfinid": entityfin_id, "subentity": subentity_id},
        },
    ]
    if not entityfin_id:
        return {
            "status": "review",
            "status_label": "Scope Required",
            "summary_cards": [
                {"label": "Latest Run", "value": "Select FY", "note": "Choose a financial year for bank controls", "tone": "warning"},
                {"label": "Unmatched Bank", "value": "-", "note": "No scoped run selected", "tone": "neutral"},
                {"label": "Difference", "value": "-", "note": "No scoped run selected", "tone": "neutral"},
            ],
            "actions": actions,
        }

    try:
        runs = BankReconciliationRun.objects.filter(entity_id=entity_id, entityfin_id=entityfin_id)
        if subentity_id:
            runs = runs.filter(subentity_id=subentity_id)
        latest_run = runs.only(
            "id",
            "run_code",
            "status",
            "as_of_date",
            "unmatched_bank_amount",
            "unmatched_book_amount",
            "difference_amount",
            "matched_line_count",
            "statement_line_count",
            "exception_line_count",
            "locked_at",
        ).order_by("-as_of_date", "-updated_at", "-id").first()
        if latest_run is None:
            return {
                "status": "review",
                "status_label": "Not Run",
                "summary_cards": [
                    {"label": "Latest Run", "value": "Not run", "note": "Create or import a reconciliation run", "tone": "warning"},
                    {"label": "Unmatched Bank", "value": "0.00", "note": "No run found for this scope", "tone": "neutral"},
                    {"label": "Difference", "value": "0.00", "note": "No run found for this scope", "tone": "neutral"},
                ],
                "actions": actions,
            }

        unmatched_bank = _q2(latest_run.unmatched_bank_amount)
        unmatched_books = _q2(latest_run.unmatched_book_amount)
        difference = _q2(latest_run.difference_amount)
        exceptions = int(latest_run.exception_line_count or 0)
        is_locked_or_reconciled = latest_run.status in {
            BankReconciliationRun.Status.RECONCILED,
            BankReconciliationRun.Status.LOCKED,
        }
        has_blockers = bool(unmatched_bank or unmatched_books or difference or exceptions)
        status = "ready" if is_locked_or_reconciled and not has_blockers else "blocked" if has_blockers else "review"
        status_label = "Ready" if status == "ready" else "Blocked" if status == "blocked" else "Review"
        actions.extend(
            [
                {
                    "label": "View BRS",
                    "route": "/bank-reco/reports/brs",
                    "params": {"run_id": latest_run.id, "entityfinid": entityfin_id, "subentity": subentity_id},
                },
                {
                    "label": "Audit Trail",
                    "route": "/bank-reco/reports/audit-trail",
                    "params": {"run_id": latest_run.id, "entityfinid": entityfin_id, "subentity": subentity_id},
                },
            ]
        )
        return {
            "status": status,
            "status_label": status_label,
            "run_id": latest_run.id,
            "run_code": latest_run.run_code,
            "summary_cards": [
                {
                    "label": "Latest Run",
                    "value": str(latest_run.as_of_date or latest_run.run_code or latest_run.id),
                    "note": f"Status: {latest_run.status.replace('_', ' ').title()}",
                    "tone": "accent" if status == "ready" else "warning" if status == "blocked" else "neutral",
                },
                {
                    "label": "Unmatched Bank",
                    "value": str(unmatched_bank),
                    "note": f"Book unmatched {unmatched_books}",
                    "tone": "warning" if unmatched_bank or unmatched_books else "accent",
                },
                {
                    "label": "Difference",
                    "value": str(difference),
                    "note": f"{latest_run.matched_line_count}/{latest_run.statement_line_count} statement lines matched",
                    "tone": "warning" if difference or exceptions else "accent",
                },
            ],
            "actions": actions,
        }
    except Exception:
        return {
            "status": "review",
            "status_label": "Unavailable",
            "summary_cards": [
                {"label": "Latest Run", "value": "Unavailable", "note": "Open bank reconciliation to retry", "tone": "warning"},
                {"label": "Unmatched Bank", "value": "-", "note": "Snapshot unavailable", "tone": "neutral"},
                {"label": "Difference", "value": "-", "note": "Snapshot unavailable", "tone": "neutral"},
            ],
            "actions": actions,
        }


def _close_checklist_scope_key(entityfin_id: int | None, subentity_id: int | None) -> str:
    return f"fy:{entityfin_id or 'all'}|sub:{subentity_id or 'all'}"


def _close_checklist_overrides(reporting_policy: dict, *, entityfin_id: int | None, subentity_id: int | None) -> dict:
    close_checklist = reporting_policy.get("close_checklist") or {}
    items = close_checklist.get("items") or {}
    scoped = items.get(_close_checklist_scope_key(entityfin_id, subentity_id)) or {}
    return scoped if isinstance(scoped, dict) else {}


def _resolve_close_checklist_overrides(*, entity_id: int, entityfin_id: int | None, subentity_id: int | None) -> dict:
    try:
        settings = FinancialSettings.objects.filter(entity_id=entity_id).only("reporting_policy").first()
    except Exception:
        return {}
    policy = getattr(settings, "reporting_policy", None) or {}
    return _close_checklist_overrides(policy, entityfin_id=entityfin_id, subentity_id=subentity_id)


def _apply_close_checklist_overrides(checklist: list[dict], overrides: dict) -> list[dict]:
    rows = []
    for item in checklist or []:
        row = dict(item)
        override = overrides.get(str(row.get("key") or "")) or {}
        if isinstance(override, dict):
            if row.get("status") != "blocked" and override.get("status") in {"done", "review"}:
                row["status"] = override.get("status")
                row["tone"] = "available" if row["status"] == "done" else "warning"
            if override.get("comment"):
                row["comment"] = override.get("comment")
            if override.get("updated_at"):
                row["updated_at"] = override.get("updated_at")
            if override.get("updated_by"):
                row["updated_by"] = override.get("updated_by")
        rows.append(row)
    return rows


def _build_year_end_close_snapshot(*, entity_id: int, entityfin_id: int | None, subentity_id: int | None, opening_policy: dict, reporting_policy: dict | None = None) -> dict:
    actions = [
        {
            "label": "Open Year-End Close",
            "route": "/reports/controls/year-end-close",
            "params": {"entityfinid": entityfin_id, "subentity": subentity_id},
        }
    ]
    if not entityfin_id:
        checklist = [
            {
                "key": "scope_required",
                "label": "Select financial year",
                "status": "blocked",
                "mandatory": True,
                "detail": "Choose a financial year before the close checklist can be evaluated.",
                "tone": "warning",
            }
        ]
        return {
            "status": "review",
            "status_label": "Scope Required",
            "summary_cards": [
                {"label": "Readiness", "value": "Select FY", "note": "Choose a financial year for close controls", "tone": "warning"},
                {"label": "Drafts", "value": "-", "note": "No scoped close preview", "tone": "neutral"},
                {"label": "Balance Difference", "value": "-", "note": "No scoped close preview", "tone": "neutral"},
            ],
            "checklist": checklist,
            "actions": actions,
        }

    try:
        preview = build_year_end_close_preview(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            reporting_policy=opening_policy,
        )
        close_state = preview.get("close_state") or {}
        readiness_state = str(close_state.get("readiness_state") or "review")
        is_closed = bool(close_state.get("is_year_closed"))
        status = "closed" if is_closed else readiness_state
        status_label = "Closed" if is_closed else readiness_state.replace("_", " ").title()
        summary_cards = preview.get("summary_cards") or []
        preview_checks = preview.get("checks") or []
        checklist = _build_close_checklist_items(preview_checks)
        checklist = _apply_close_checklist_overrides(
            checklist,
            _close_checklist_overrides(reporting_policy or {}, entityfin_id=entityfin_id, subentity_id=subentity_id),
        )
        source_summary = preview.get("source_summary") or []
        balance_difference = next((item for item in source_summary if item.get("label") == "Balance Difference"), None)
        cards = [
            {
                "label": "Readiness",
                "value": status_label,
                "note": "Year already closed" if is_closed else "Close checklist distilled",
                "tone": "accent" if status in {"ready", "closed"} else "warning" if status == "blocked" else "neutral",
            }
        ]
        cards.extend(summary_cards[:2])
        if balance_difference:
            cards.append(balance_difference)
        return {
            "status": status,
            "status_label": status_label,
            "summary_cards": cards[:4],
            "checks": preview_checks,
            "checklist": checklist,
            "warnings": preview.get("warnings") or [],
            "actions": actions,
        }
    except Exception:
        return {
            "status": "review",
            "status_label": "Unavailable",
            "summary_cards": [
                {"label": "Readiness", "value": "Unavailable", "note": "Open year-end close to retry", "tone": "warning"},
                {"label": "Drafts", "value": "-", "note": "Close snapshot unavailable", "tone": "neutral"},
                {"label": "Balance Difference", "value": "-", "note": "Close snapshot unavailable", "tone": "neutral"},
            ],
            "checklist": [
                {
                    "key": "close_preview_unavailable",
                    "label": "Close preview available",
                    "status": "blocked",
                    "mandatory": True,
                    "detail": "Close checklist cannot be evaluated right now.",
                    "tone": "warning",
                }
            ],
            "actions": actions,
        }


def _build_close_checklist_items(checks: list[dict]) -> list[dict]:
    mandatory_keys = {"year_not_closed", "drafts", "balance_sheet"}
    items = []
    for check in checks or []:
        status = str(check.get("status") or "warning").lower()
        items.append(
            {
                "key": check.get("key") or check.get("label") or "close_check",
                "label": check.get("label") or "Close checklist item",
                "status": "done" if status == "pass" else "blocked" if status == "fail" else "review",
                "mandatory": (check.get("key") in mandatory_keys) or status == "fail",
                "detail": check.get("detail") or "",
                "tone": check.get("tone") or "neutral",
            }
        )
    return items


def _checklist_status_from_readiness(status: str) -> str:
    if status in {"ready", "ready_to_file", "closed"}:
        return "done"
    if status in {"blocked", "fail"}:
        return "blocked"
    return "review"


def _close_checklist_module_item(
    *,
    key: str,
    label: str,
    readiness: dict,
    mandatory: bool,
    ready_detail: str,
    review_detail: str,
    blocked_detail: str,
    action: dict | None = None,
) -> dict:
    raw_status = str(readiness.get("status") or "review")
    status = _checklist_status_from_readiness(raw_status)
    return {
        "key": key,
        "label": label,
        "status": status,
        "mandatory": mandatory,
        "detail": ready_detail if status == "done" else blocked_detail if status == "blocked" else review_detail,
        "tone": "available" if status == "done" else "blocked" if status == "blocked" else "warning",
        "action": action,
    }


def _extend_close_checklist_with_module_gates(
    *,
    year_end_close: dict,
    compliance: dict,
    bank_reconciliation: dict,
    recurring_journals: dict,
    approval_workflow: dict,
    attachment_vault: dict,
    opening_policy: dict,
) -> dict:
    checklist = list(year_end_close.get("checklist") or [])
    close_action = _first_action(year_end_close)
    require_closed = bool(opening_policy.get("require_closed_source_year", True))
    checklist.extend(
        [
            _close_checklist_module_item(
                key="bank_reconciliation_gate",
                label="Bank reconciliation complete",
                readiness=bank_reconciliation,
                mandatory=True,
                ready_detail="Latest bank reconciliation is ready for close.",
                review_detail="Run or review bank reconciliation before close.",
                blocked_detail="Resolve reconciliation differences before close.",
                action=_first_action(bank_reconciliation),
            ),
            _close_checklist_module_item(
                key="compliance_gate",
                label="Statutory compliance reviewed",
                readiness=compliance,
                mandatory=True,
                ready_detail="GST/TDS/TCS readiness is clean for close review.",
                review_detail="Review statutory exceptions and advisories before close.",
                blocked_detail="Resolve statutory blockers before close.",
                action=_compliance_action(compliance, str(compliance.get("status") or "review")),
            ),
            _close_checklist_module_item(
                key="recurring_journals_gate",
                label="Recurring journals processed",
                readiness=recurring_journals,
                mandatory=True,
                ready_detail="Recurring journals are scheduled with no failed runs.",
                review_detail="Review due recurring journals before close.",
                blocked_detail="Fix failed recurring journal templates before close.",
                action=_phase_one_action("Review Recurring Journals", tab="policies", policy="recurring"),
            ),
            _close_checklist_module_item(
                key="approval_workflow_gate",
                label="Approvals cleared",
                readiness=approval_workflow,
                mandatory=True,
                ready_detail="Approval workflow is configured and clear.",
                review_detail="Review pending approvals and workflow policy before close.",
                blocked_detail="Resolve rejected items or approval policy blockers before close.",
                action=_phase_one_action("Review Approval Workflow", tab="policies", policy="approvals"),
            ),
            _close_checklist_module_item(
                key="attachment_vault_gate",
                label="Required evidence attached",
                readiness=attachment_vault,
                mandatory=True,
                ready_detail="Required close evidence is indexed.",
                review_detail="Review attachment coverage before close.",
                blocked_detail="Attach required evidence before close.",
                action=_phase_one_action("Review Attachment Vault", tab="policies", policy="attachments"),
            ),
            {
                "key": "opening_policy_confirmed_gate",
                "label": "Opening policy confirmed",
                "status": "done" if require_closed else "review",
                "mandatory": True,
                "detail": (
                    "Opening policy requires the source year to be closed."
                    if require_closed
                    else "Opening policy allows partial opening; finance should confirm this before close."
                ),
                "tone": "available" if require_closed else "warning",
                "action": _action_with_params(close_action, focus="checklist"),
            },
        ]
    )
    return {**year_end_close, "checklist": checklist}


def mandatory_close_checklist_blockers(*, entity_id: int, entityfin_id: int | None = None, subentity_id: int | None = None) -> list[dict]:
    hub = build_phase_one_controls_hub(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id)
    checklist = (hub.get("year_end_close_readiness") or {}).get("checklist") or []
    return [
        item
        for item in checklist
        if item.get("mandatory") and str(item.get("status") or "").lower() == "blocked"
    ]


def _first_action(snapshot: dict) -> dict | None:
    actions = snapshot.get("actions") or []
    return actions[0] if actions else None


def _action_by_label(snapshot: dict, label: str) -> dict | None:
    actions = snapshot.get("actions") or []
    for action in actions:
        if action.get("label") == label:
            return action
    return None


def _action_with_params(action: dict | None, **params) -> dict | None:
    if not action:
        return None
    return {
        **action,
        "params": {
            **(action.get("params") or {}),
            **{key: value for key, value in params.items() if value is not None},
        },
    }


def _phase_one_action(label: str, **params) -> dict:
    return {
        "label": label,
        "route": "/reports/controls/phase-one",
        "params": {key: value for key, value in params.items() if value is not None},
    }


def _control_check(
    *,
    key: str,
    area: str,
    label: str,
    status: str,
    detail: str,
    action: dict | None = None,
) -> dict:
    tone = "available" if status == "pass" else "blocked" if status == "fail" else "warning" if status == "warning" else "neutral"
    return {
        "key": key,
        "area": area,
        "label": label,
        "status": status,
        "detail": detail,
        "tone": tone,
        "action": action,
    }


def _build_control_checks(*, compliance: dict, bank_reconciliation: dict, year_end_close: dict, recurring_journals: dict, approval_workflow: dict, audit_trail: dict, attachment_vault: dict, opening_policy: dict) -> list[dict]:
    checks: list[dict] = []
    bank_status = str(bank_reconciliation.get("status") or "review")
    bank_action = (
        _action_by_label(bank_reconciliation, "Open Matching Workspace")
        if bank_status in {"blocked", "review"}
        else _action_by_label(bank_reconciliation, "View BRS") or _first_action(bank_reconciliation)
    )
    checks.append(
        _control_check(
            key="bank_reconciliation",
            area="Bank",
            label="Bank reconciliation readiness",
            status="pass" if bank_status == "ready" else "fail" if bank_status == "blocked" else "warning",
            detail=(
                "Latest bank reconciliation is ready for close."
                if bank_status == "ready"
                else "Resolve unmatched bank/book lines or reconciliation differences."
                if bank_status == "blocked"
                else "Review or create the latest bank reconciliation run."
            ),
            action=bank_action,
        )
    )

    close_status = str(year_end_close.get("status") or "review")
    close_action = _action_with_params(
        _first_action(year_end_close),
        focus="blockers" if close_status == "blocked" else "checklist",
    )
    checks.append(
        _control_check(
            key="year_end_close",
            area="Close",
            label="Year-end close readiness",
            status="pass" if close_status in {"ready", "closed"} else "fail" if close_status == "blocked" else "warning",
            detail=(
                "Source year close checks are ready or already closed."
                if close_status in {"ready", "closed"}
                else "Resolve close blockers before executing year-end close."
                if close_status == "blocked"
                else "Review the year-end close checklist before final close."
            ),
            action=close_action,
        )
    )

    compliance_status = str(compliance.get("status") or "review")
    compliance_action = _compliance_action(compliance, compliance_status)
    checks.append(
        _control_check(
            key="compliance_readiness",
            area="Compliance",
            label="GST/TDS/TCS readiness",
            status="pass" if compliance_status == "ready_to_file" else "fail" if compliance_status == "blocked" else "warning",
            detail=(
                "Compliance snapshot is ready for filing review."
                if compliance_status == "ready_to_file"
                else "Resolve statutory blockers before treating close as clean."
                if compliance_status == "blocked"
                else "Review statutory exceptions and reconciliation advisories."
            ),
            action=compliance_action,
        )
    )

    recurring_status = str(recurring_journals.get("status") or "review")
    checks.append(
        _control_check(
            key="recurring_journals",
            area="Recurring",
            label="Recurring journal scheduler",
            status="pass" if recurring_status == "ready" else "fail" if recurring_status == "blocked" else "warning",
            detail=(
                "Recurring journal templates are configured and scheduled."
                if recurring_status == "ready"
                else "Resolve failed recurring journal templates before close."
                if recurring_status == "blocked"
                else "Review due or missing recurring journal templates."
            ),
            action=_phase_one_action("Review Recurring Journals", tab="policies", policy="recurring"),
        )
    )

    approval_status = str(approval_workflow.get("status") or "review")
    checks.append(
        _control_check(
            key="approval_workflow",
            area="Approval",
            label="Approval workflow readiness",
            status="pass" if approval_status == "ready" else "fail" if approval_status == "blocked" else "warning",
            detail=(
                "Approval policy covers the configured voucher workflow."
                if approval_status == "ready"
                else "Configure document coverage before relying on approval controls."
                if approval_status == "blocked"
                else "Review approval workflow policy before enabling automated posting."
            ),
            action=_phase_one_action("Review Approval Workflow", tab="policies", policy="approvals"),
        )
    )

    audit_status = str(audit_trail.get("status") or "review")
    checks.append(
        _control_check(
            key="audit_trail",
            area="Audit",
            label="Audit trail coverage",
            status="pass" if audit_status == "ready" else "fail" if audit_status == "blocked" else "warning",
            detail=(
                "Audit trail is capturing recent control activity."
                if audit_status == "ready"
                else "Enable write capture and module coverage for audit trail controls."
                if audit_status == "blocked"
                else "Review audit trail coverage and recent event activity."
            ),
            action=_phase_one_action("Review Audit Trail", tab="policies", policy="audit"),
        )
    )

    attachment_status = str(attachment_vault.get("status") or "review")
    checks.append(
        _control_check(
            key="attachment_vault",
            area="Documents",
            label="Attachment vault coverage",
            status="pass" if attachment_status == "ready" else "fail" if attachment_status == "blocked" else "warning",
            detail=(
                "Attachment vault has indexed evidence for the entity."
                if attachment_status == "ready"
                else "Configure required document classes before relying on document controls."
                if attachment_status == "blocked"
                else "Review attachment coverage and upload required evidence."
            ),
            action=_phase_one_action("Review Attachment Vault", tab="policies", policy="attachments"),
        )
    )

    require_closed = bool(opening_policy.get("require_closed_source_year", True))
    checks.append(
        _control_check(
            key="opening_policy_closed_source",
            area="Opening",
            label="Opening source-year policy",
            status="pass" if require_closed and close_status in {"closed", "ready"} else "warning" if require_closed else "pass",
            detail=(
                "Opening generation requires the source year to be closed."
                if require_closed
                else "Opening policy allows partial opening before source close."
            ),
            action=_phase_one_action("Review Opening Preview", tab="opening", opening="preview"),
        )
    )

    for check in (year_end_close.get("checks") or [])[:3]:
        check_key = check.get("key")
        checks.append(
            _control_check(
                key=f"year_end_close_{check_key}",
                area="Close",
                label=str(check.get("label") or "Close check"),
                status="fail" if check.get("status") == "fail" else "warning" if check.get("status") == "warning" else "pass" if check.get("status") == "pass" else "info",
                detail=str(check.get("detail") or ""),
                action=_action_with_params(_first_action(year_end_close), focus="check", check=check_key),
            )
        )

    return checks


def _audit_status_from_checks(checks: list[dict]) -> str:
    statuses = {str(item.get("status") or "") for item in checks}
    if "fail" in statuses:
        return "blocked"
    if "warning" in statuses:
        return "review"
    return "ready"


def _metric_value(snapshot: dict, label: str, fallback="-") -> object:
    for metric in snapshot.get("summary_cards") or []:
        if metric.get("label") == label:
            return metric.get("value", fallback)
    return fallback


def _metric_int(snapshot: dict, label: str) -> int:
    value = _metric_value(snapshot, label, 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _compliance_action(compliance: dict, status: str) -> dict | None:
    if status == "blocked":
        if _metric_int(compliance, "GST Exceptions") > 0 or _metric_int(compliance, "GST Blockers") > 0:
            return _action_by_label(compliance, "Open GST Blockers") or _first_action(compliance)
        if _metric_int(compliance, "TDS Blockers") > 0:
            return (
                _action_by_label(compliance, "Open Purchase Statutory (TDS Blocked)")
                or _action_by_label(compliance, "Open Purchase TDS Blockers")
                or _first_action(compliance)
            )
        if _metric_int(compliance, "TCS Blockers") > 0:
            return (
                _action_by_label(compliance, "Open TCS Pending Collection")
                or _action_by_label(compliance, "Open TCS Pending Deposit")
                or _action_by_label(compliance, "Open TCS Missing Section")
                or _action_by_label(compliance, "Open TCS Workspace (Blocked)")
                or _first_action(compliance)
            )
        return _action_by_label(compliance, "Open GST Blockers") or _first_action(compliance)
    return (
        _action_by_label(compliance, "Open GST Reconciliation Gaps")
        or _action_by_label(compliance, "Open GST Reconciliation")
        or _first_action(compliance)
    )


def _build_audit_pack(*, scope: dict, generated_at: str, compliance: dict, bank_reconciliation: dict, year_end_close: dict, recurring_journals: dict, approval_workflow: dict, audit_trail: dict, attachment_vault: dict, opening_policy: dict, control_checks: list[dict]) -> dict:
    status = _audit_status_from_checks(control_checks)
    evidence_rows = [
        {
            "section": "Scope",
            "label": "Entity",
            "value": scope.get("entity_name") or "-",
            "status": "info",
            "note": "Report entity scope.",
        },
        {
            "section": "Scope",
            "label": "Financial Year",
            "value": scope.get("entityfin_name") or "Current FY",
            "status": "info",
            "note": "Report financial year scope.",
        },
        {
            "section": "Scope",
            "label": "Subentity",
            "value": scope.get("subentity_name") or "All subentities",
            "status": "info",
            "note": "Report branch/subentity scope.",
        },
        {
            "section": "Bank Reconciliation",
            "label": "Latest run",
            "value": bank_reconciliation.get("run_code") or _metric_value(bank_reconciliation, "Latest Run"),
            "status": bank_reconciliation.get("status") or "review",
            "note": f"Difference: {_metric_value(bank_reconciliation, 'Difference')}",
        },
        {
            "section": "Year-End Close",
            "label": "Close readiness",
            "value": year_end_close.get("status_label") or "-",
            "status": year_end_close.get("status") or "review",
            "note": f"Balance difference: {_metric_value(year_end_close, 'Balance Difference')}",
        },
        {
            "section": "Compliance",
            "label": "GST/TDS/TCS readiness",
            "value": compliance.get("status_label") or "-",
            "status": compliance.get("status") or "review",
            "note": f"GST exceptions: {_metric_value(compliance, 'GST Exceptions')}",
        },
        {
            "section": "Opening Policy",
            "label": "Opening mode",
            "value": str(opening_policy.get("opening_mode") or "hybrid").replace("_", " "),
            "status": "info",
            "note": f"Require closed source year: {bool(opening_policy.get('require_closed_source_year', True))}",
        },
        {
            "section": "Recurring Journals",
            "label": "Scheduler readiness",
            "value": recurring_journals.get("status_label") or "-",
            "status": recurring_journals.get("status") or "review",
            "note": f"Templates: {_metric_value(recurring_journals, 'Templates')} | Due: {_metric_value(recurring_journals, 'Due')}",
        },
        {
            "section": "Approval Workflow",
            "label": "Voucher approval readiness",
            "value": approval_workflow.get("status_label") or "-",
            "status": approval_workflow.get("status") or "review",
            "note": f"Mode: {_metric_value(approval_workflow, 'Mode')} | Documents: {_metric_value(approval_workflow, 'Documents')}",
        },
        {
            "section": "Audit Trail",
            "label": "Capture readiness",
            "value": audit_trail.get("status_label") or "-",
            "status": audit_trail.get("status") or "review",
            "note": f"Recent events: {_metric_value(audit_trail, 'Recent events')} | Retention: {_metric_value(audit_trail, 'Retention')}",
        },
        {
            "section": "Attachment Vault",
            "label": "Document coverage",
            "value": attachment_vault.get("status_label") or "-",
            "status": attachment_vault.get("status") or "review",
            "note": f"Attachments: {_metric_value(attachment_vault, 'Attachments')} | Required docs: {_metric_value(attachment_vault, 'Required docs')}",
        },
    ]
    close_history = year_end_close.get("close_history") or {}
    if isinstance(close_history, dict) and close_history:
        close_summary = close_history.get("summary") or {}
        journal_entry = close_history.get("journal_entry") or {}
        evidence_rows.extend(
            [
                {
                    "section": "Year-End Close",
                    "label": "Executed close",
                    "value": close_history.get("closed_on") or close_history.get("closed_at") or "-",
                    "status": close_history.get("status") or "closed",
                    "note": f"Closed by: {((close_history.get('closed_by') or {}).get('username') or 'System')}",
                },
                {
                    "section": "Year-End Close",
                    "label": "Close net profit",
                    "value": close_summary.get("net_profit") or "-",
                    "status": "info",
                    "note": (
                        f"Income: {close_summary.get('income_total') or '-'} | "
                        f"Expense: {close_summary.get('expense_total') or '-'}"
                    ),
                },
                {
                    "section": "Year-End Close",
                    "label": "Close journal",
                    "value": journal_entry.get("voucher_no") or "-",
                    "status": "info" if journal_entry else "review",
                    "note": (
                        f"Entry: {journal_entry.get('entry_id') or '-'} | "
                        f"Lines: {journal_entry.get('line_count') or 0}"
                    ),
                },
            ]
        )
    evidence_rows.extend(
        {
            "section": "Missing Evidence",
            "label": item.get("label") or item.get("key"),
            "value": item.get("status") or "missing",
            "status": "fail",
            "note": item.get("detail") or "",
        }
        for item in attachment_vault.get("missing_evidence") or []
    )
    evidence_rows.extend(
        {
            "section": "Control Check",
            "label": item.get("label") or item.get("key"),
            "value": item.get("status"),
            "status": item.get("status"),
            "note": item.get("detail") or "",
        }
        for item in control_checks
    )
    return {
        "pack_code": "financial-controls-phase-one-audit-pack",
        "pack_name": "Financial Controls Phase 1 Audit Pack",
        "status": status,
        "status_label": "Ready" if status == "ready" else "Blocked" if status == "blocked" else "Review",
        "generated_at": generated_at,
        "summary": {
            "evidence_rows": len(evidence_rows),
            "failed_checks": sum(1 for item in control_checks if item.get("status") == "fail"),
            "review_checks": sum(1 for item in control_checks if item.get("status") == "warning"),
            "passed_checks": sum(1 for item in control_checks if item.get("status") == "pass"),
        },
        "evidence_rows": evidence_rows,
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
                    "status": "available",
                    "status_label": "Available",
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
                    "status": "available",
                    "status_label": "Available",
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
                    "status": "available",
                    "status_label": "Available",
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
                    "status": "available",
                    "status_label": "Available",
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
                    "status": "available",
                    "status_label": "Available",
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
    gst_compliance = _build_control_compliance_snapshot(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    )
    bank_reconciliation = _build_bank_reconciliation_snapshot(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    )
    year_end_close = _build_year_end_close_snapshot(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        opening_policy=opening_policy,
        reporting_policy={},
    )
    recurring_journals = build_recurring_journal_readiness(entity_id)
    approval_workflow = build_approval_workflow_readiness(entity_id)
    audit_trail = build_audit_trail_readiness(entity_id)
    attachment_vault = build_attachment_vault_readiness(entity_id)
    year_end_close = _extend_close_checklist_with_module_gates(
        year_end_close=year_end_close,
        compliance=gst_compliance,
        bank_reconciliation=bank_reconciliation,
        recurring_journals=recurring_journals,
        approval_workflow=approval_workflow,
        attachment_vault=attachment_vault,
        opening_policy=opening_policy,
    )
    year_end_close = {
        **year_end_close,
        "checklist": _apply_close_checklist_overrides(
            year_end_close.get("checklist") or [],
            _resolve_close_checklist_overrides(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id),
        ),
    }
    control_checks = _build_control_checks(
        compliance=gst_compliance,
        bank_reconciliation=bank_reconciliation,
        year_end_close=year_end_close,
        recurring_journals=recurring_journals,
        approval_workflow=approval_workflow,
        audit_trail=audit_trail,
        attachment_vault=attachment_vault,
        opening_policy=opening_policy,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    scoped_names = {
        "entity_name": scope_names["entity_name"] or f"Entity {entity_id}",
        "entityfin_name": scope_names["entityfin_name"] or "Current FY",
        "subentity_name": scope_names["subentity_name"] or "All subentities",
    }
    audit_pack = _build_audit_pack(
        scope=scoped_names,
        generated_at=generated_at,
        compliance=gst_compliance,
        bank_reconciliation=bank_reconciliation,
        year_end_close=year_end_close,
        recurring_journals=recurring_journals,
        approval_workflow=approval_workflow,
        audit_trail=audit_trail,
        attachment_vault=attachment_vault,
        opening_policy=opening_policy,
        control_checks=control_checks,
    )
    total_cards = sum(len(section["cards"]) for section in sections)
    planned_cards = sum(1 for section in sections for card in section["cards"] if card["status"] == "planned")
    available_cards = sum(1 for section in sections for card in section["cards"] if card["status"] == "available")
    return {
        "report_code": "phase_one_controls_hub",
        "report_name": "Financial Controls Phase 1",
        "report_eyebrow": "Financial Hub",
        "entity_id": entity_id,
        "entity_name": scoped_names["entity_name"],
        "entityfin_id": entityfin_id,
        "entityfin_name": scoped_names["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": scoped_names["subentity_name"],
        "generated_at": generated_at,
        "summary_cards": [
            {"label": "Utilities", "value": total_cards, "note": "Phase 1 control workstreams", "tone": "accent"},
            {"label": "Planned", "value": planned_cards, "note": "Future controls still on the roadmap", "tone": "warning"},
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
        "bank_reconciliation_readiness": bank_reconciliation,
        "year_end_close_readiness": year_end_close,
        "recurring_journals_readiness": recurring_journals,
        "approval_workflow_readiness": approval_workflow,
        "audit_trail_readiness": audit_trail,
        "attachment_vault_readiness": attachment_vault,
        "control_checks": control_checks,
        "audit_pack": audit_pack,
    }
