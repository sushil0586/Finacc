from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone

from entity.models import EntityGstRegistration, SubEntityGstRegistration
from gst_reconciliation.models import GstReconciliationItem, GstReconciliationRun
from reports.gst_compliance.contracts import GstComplianceScope, build_gst_compliance_deep_link
from reports.gst_compliance.itc_ledger import build_input_tax_ledger_reconciliation
from reports.gstr3b.selectors import Gstr3bScope
from reports.gstr3b.services import Gstr3bSummaryService
from reports.models import GstPortalFilingRun, GstPortalProfile, ReportFilingRun, ReportFreezeSnapshot
from sales.models import SalesInvoiceHeader
from sales.models.sales_compliance import SalesEInvoiceStatus, SalesEWayStatus


@dataclass(frozen=True)
class GstComplianceCardDefinition:
    code: str
    title: str
    target: str
    description: str


GST_COMPLIANCE_CARD_DEFINITIONS: tuple[GstComplianceCardDefinition, ...] = (
    GstComplianceCardDefinition("gstr1", "GSTR-1", "gstr1", "Outward supply readiness, validation, and filing export."),
    GstComplianceCardDefinition("gstr3b", "GSTR-3B", "gstr3b", "Tax payment, ITC, and monthly summary review."),
    GstComplianceCardDefinition("gstr9", "GSTR-9", "gstr9", "Annual return review, freeze, and filing pack."),
    GstComplianceCardDefinition("itc_2b", "ITC / 2B", "gst_reconciliation", "Imported 2B, ITC matching, and reviewer queue."),
    GstComplianceCardDefinition("exceptions", "GST Exceptions", "gst_exception_dashboard", "Mismatches, validation warnings, and blocked filing items."),
    GstComplianceCardDefinition("portal", "GST Portal", "gst_portal", "WhiteBooks/GSTN profile, save/proceed/file status, and provider health."),
    GstComplianceCardDefinition("einvoice_eway", "E-Invoice / E-Way", "sales_compliance", "IRN, EWB, cancellation, expiry, and retry health."),
    GstComplianceCardDefinition("gst_tds", "GST-TDS", "gst_tds", "GST-TDS deduction, return, and compliance status."),
    GstComplianceCardDefinition("tcs", "TCS", "tcs", "TCS collection, return, and filing status."),
)


class GstComplianceSnapshotService:
    report_code = "gst-compliance-snapshot"
    report_name = "GST Compliance Center Snapshot"

    def build(self, *, scope: GstComplianceScope, permission_codes: set[str] | None = None) -> dict[str, Any]:
        permissions = set(permission_codes or ())
        resolved_gstin = self._resolve_gstin(scope)
        period = self._period(scope)
        ret_period = self._portal_return_period(scope)
        setup_warnings = self._setup_warnings(scope, resolved_gstin)
        input_tax_ledger_reconciliation = self._input_tax_ledger_reconciliation(scope)
        itc_decision_summary = self._itc_decision_summary(scope=scope, gstin=resolved_gstin)

        cards = [
            self._card(
                definition=definition,
                scope=scope,
                permissions=permissions,
                resolved_gstin=resolved_gstin,
                period=period,
                ret_period=ret_period,
                setup_warnings=setup_warnings,
                input_tax_ledger_reconciliation=input_tax_ledger_reconciliation,
                itc_decision_summary=itc_decision_summary,
            )
            for definition in GST_COMPLIANCE_CARD_DEFINITIONS
        ]
        summary = self._summary(cards)
        next_actions = self._next_actions(cards)
        return {
            "report_code": self.report_code,
            "report_name": self.report_name,
            "generated_at": timezone.now().isoformat(),
            "scope": {
                **scope.as_filters(),
                "resolved_gstin": resolved_gstin,
                "period_label": period["label"],
                "portal_return_period": ret_period,
            },
            "summary": summary,
            "cards": cards,
            "next_actions": next_actions,
            "setup_warnings": setup_warnings,
            "input_tax_ledger_reconciliation": input_tax_ledger_reconciliation,
            "itc_decision_summary": itc_decision_summary,
        }

    def _card(
        self,
        *,
        definition: GstComplianceCardDefinition,
        scope: GstComplianceScope,
        permissions: set[str],
        resolved_gstin: str | None,
        period: dict[str, Any],
        ret_period: str | None,
        setup_warnings: list[dict[str, str]],
        input_tax_ledger_reconciliation: dict[str, Any] | None = None,
        itc_decision_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        link = build_gst_compliance_deep_link(definition.target, scope)
        has_permission = not link["permissions"] or any(code in permissions for code in link["permissions"])
        status = "ready"
        blockers: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        signals: dict[str, Any] = {
            "period": period["label"],
            "gstin": resolved_gstin,
        }

        if definition.code in {"gstr1", "gstr3b", "portal"}:
            if not resolved_gstin:
                blockers.append(
                    {
                        "code": "GSTIN_NOT_CONFIGURED",
                        "message": "No active GSTIN is configured for this scope.",
                    }
                )
            elif definition.code == "portal":
                profile = self._portal_profile(scope=scope, gstin=resolved_gstin)
                filing_run = self._latest_portal_filing(scope=scope, gstin=resolved_gstin, return_type="gstr1", ret_period=ret_period)
                signals.update(
                    {
                        "profile_configured": bool(profile),
                        "profile_verified": bool(getattr(profile, "is_verified", False)) if profile else False,
                        "last_portal_status": getattr(filing_run, "status", "") if filing_run else "",
                        "last_portal_reference": getattr(filing_run, "portal_reference", "") if filing_run else "",
                    }
                )
                if not profile:
                    warnings.append(
                        {
                            "code": "GST_PORTAL_PROFILE_MISSING",
                            "message": "GST portal profile is not configured for this GSTIN.",
                        }
                    )
                elif not profile.is_verified:
                    warnings.append(
                        {
                            "code": "GST_PORTAL_PROFILE_UNVERIFIED",
                            "message": "GST portal profile exists but is not verified yet.",
                        }
                    )
                status = self._portal_status(filing_run, default="ready")
            elif definition.code in {"gstr1", "gstr3b"}:
                filing_run = self._latest_portal_filing(
                    scope=scope,
                    gstin=resolved_gstin,
                    return_type="gstr1" if definition.code == "gstr1" else "gstr3b",
                    ret_period=ret_period,
                )
                signals.update(
                    {
                        "last_portal_status": getattr(filing_run, "status", "") if filing_run else "",
                        "last_portal_reference": getattr(filing_run, "portal_reference", "") if filing_run else "",
                    }
                )
                status = self._portal_status(filing_run, default="ready")

        if definition.code == "gstr9":
            freeze_snapshot = self._latest_gstr9_freeze(scope)
            filing_run = self._latest_gstr9_filing(scope)
            signals.update(
                {
                    "freeze_version": getattr(freeze_snapshot, "version", None) if freeze_snapshot else None,
                    "filing_status": getattr(filing_run, "status", "") if filing_run else "",
                    "portal_reference": getattr(filing_run, "portal_reference", "") if filing_run else "",
                }
            )
            status = self._annual_status(freeze_snapshot=freeze_snapshot, filing_run=filing_run)

        if definition.code in {"itc_2b", "exceptions"}:
            warnings.extend(setup_warnings)
            if setup_warnings:
                status = "needs_review"

        if definition.code == "itc_2b":
            ledger_reconciliation = input_tax_ledger_reconciliation or {}
            ledger_summary = ledger_reconciliation.get("summary") or {}
            ledger_warnings = ledger_reconciliation.get("warnings") or []
            decision_summary = itc_decision_summary or {}
            mismatch_count = int(ledger_summary.get("mismatch_count") or 0)
            warning_count = len(ledger_warnings)
            pending_items = int(decision_summary.get("pending_items") or 0)
            deferred_items = int(decision_summary.get("deferred_items") or 0)
            rejected_items = int(decision_summary.get("rejected_items") or 0)
            blocked_items = int(decision_summary.get("blocked_items") or 0)
            portal_context_summary = decision_summary.get("portal_context_summary") or {}
            amended_rows = int(portal_context_summary.get("amended_rows") or 0)
            vendor_revised_rows = int(portal_context_summary.get("vendor_revised_rows") or 0)
            ims_pending_rows = int(portal_context_summary.get("ims_pending_rows") or 0)
            ims_rejected_rows = int(portal_context_summary.get("ims_rejected_rows") or 0)
            signals.update(
                {
                    "input_ledger_mismatch_count": mismatch_count,
                    "input_ledger_difference_total_itc": ledger_summary.get("difference_total_itc", 0),
                    "input_ledger_warning_count": warning_count,
                    "itc_review_run_id": decision_summary.get("run_id"),
                    "itc_decided_items": decision_summary.get("decided_items", 0),
                    "itc_pending_items": pending_items,
                    "itc_accepted_items": decision_summary.get("accepted_items", 0),
                    "itc_deferred_items": deferred_items,
                    "itc_rejected_items": rejected_items,
                    "itc_blocked_items": blocked_items,
                    "portal_amended_rows": amended_rows,
                    "portal_vendor_revised_rows": vendor_revised_rows,
                    "ims_pending_rows": ims_pending_rows,
                    "ims_rejected_rows": ims_rejected_rows,
                }
            )
            if mismatch_count:
                warnings.append(
                    {
                        "code": "GST_INPUT_LEDGER_MISMATCH",
                        "message": f"{mismatch_count} input GST ledger component requires ITC tie-out review.",
                    }
                )
                status = "needs_review"
            if pending_items:
                warnings.append(
                    {
                        "code": "GST_ITC_DECISION_PENDING",
                        "message": f"{pending_items} GSTR-2B reconciliation item still needs an ITC decision.",
                    }
                )
                status = "needs_review"
            if deferred_items or rejected_items or blocked_items:
                warnings.append(
                    {
                        "code": "GST_ITC_DECISION_EXCEPTION",
                        "message": "Deferred, rejected, or blocked ITC decisions are present in the selected period.",
                    }
                )
                status = "needs_review"
            if amended_rows or vendor_revised_rows:
                warnings.append(
                    {
                        "code": "GST_2B_AMENDED_OR_REVISED_ROWS",
                        "message": f"{amended_rows + vendor_revised_rows} GSTR-2B portal row needs amended/vendor-revised review.",
                    }
                )
                status = "needs_review"
            if ims_pending_rows or ims_rejected_rows:
                warnings.append(
                    {
                        "code": "GST_IMS_ACTION_REVIEW",
                        "message": f"{ims_pending_rows + ims_rejected_rows} IMS row needs action/rejection review before ITC is finalized.",
                    }
                )
                status = "needs_review"
            if warning_count:
                warnings.append(
                    {
                        "code": "GST_INPUT_LEDGER_SETUP_WARNING",
                        "message": f"{warning_count} input GST ledger setup warning must be reviewed before claiming ITC.",
                    }
                )
                status = "needs_review"

        if definition.code in {"einvoice_eway", "gst_tds", "tcs"}:
            if not resolved_gstin and definition.code in {"einvoice_eway", "gst_tds"}:
                warnings.append(
                    {
                        "code": "GSTIN_RECOMMENDED",
                        "message": "Configure GSTIN to make this compliance card period-specific.",
                    }
                )
                status = "needs_review"

        summary: dict[str, Any] | None = None
        if definition.code == "einvoice_eway":
            compliance_summary = self._einvoice_eway_summary(scope=scope, gstin=resolved_gstin)
            summary = compliance_summary["summary"]
            signals.update(compliance_summary["signals"])
            warnings.extend(compliance_summary["warnings"])
            blockers.extend(compliance_summary["blockers"])
            if compliance_summary["status"] == "blocked":
                status = "blocked"
            elif compliance_summary["status"] == "needs_review" and status == "ready":
                status = "needs_review"

        if blockers:
            status = "blocked"
        elif warnings and status == "ready":
            status = "needs_review"

        return {
            "code": definition.code,
            "title": definition.title,
            "description": definition.description,
            "status": status,
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "info_count": len(signals),
            "blockers": blockers,
            "warnings": warnings,
            "summary": summary or {},
            "signals": signals,
            "link": link,
            "links": {"primary": link},
            "access": {
                "has_permission": has_permission,
                "required_permissions": link["permissions"],
                "feature": link["feature"],
                "access_mode": link["access_mode"],
            },
        }

    def _summary(self, cards: list[dict[str, Any]]) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        for card in cards:
            by_status[card["status"]] = by_status.get(card["status"], 0) + 1
        return {
            "card_count": len(cards),
            "blocked_count": by_status.get("blocked", 0),
            "needs_review_count": by_status.get("needs_review", 0),
            "ready_count": by_status.get("ready", 0),
            "filed_count": by_status.get("filed", 0),
            "frozen_count": by_status.get("frozen", 0),
            "prepared_count": by_status.get("prepared", 0),
            "by_status": by_status,
        }

    def _next_actions(self, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = {"blocked": 0, "needs_review": 1, "prepared": 2, "frozen": 3, "ready": 4, "filed": 5}
        ordered = sorted(cards, key=lambda card: (ranked.get(card["status"], 9), card["title"]))
        actions = []
        for card in ordered[:5]:
            if card["status"] == "filed":
                continue
            actions.append(
                {
                    "code": f"open_{card['code']}",
                    "label": f"Open {card['title']}",
                    "status": card["status"],
                    "link": card["link"],
                    "blocked": card["blocker_count"] > 0,
                }
            )
        return actions

    def _resolve_gstin(self, scope: GstComplianceScope) -> str | None:
        if scope.gstin:
            return scope.gstin
        if scope.subentity_id:
            subentity_gstin = (
                SubEntityGstRegistration.objects.filter(subentity_id=scope.subentity_id, isactive=True, is_primary=True)
                .values_list("gstin", flat=True)
                .first()
            )
            if subentity_gstin:
                return str(subentity_gstin).strip().upper()
        entity_gstin = (
            EntityGstRegistration.objects.filter(entity_id=scope.entity_id, isactive=True, is_primary=True)
            .values_list("gstin", flat=True)
            .first()
        )
        if entity_gstin:
            return str(entity_gstin).strip().upper()
        return None

    def _setup_warnings(self, scope: GstComplianceScope, gstin: str | None) -> list[dict[str, str]]:
        warnings: list[dict[str, str]] = []
        if not gstin:
            warnings.append(
                {
                    "code": "GSTIN_NOT_CONFIGURED",
                    "message": "No GSTIN is configured for this compliance scope.",
                }
            )
        if not scope.entityfinid_id:
            warnings.append(
                {
                    "code": "FINANCIAL_YEAR_NOT_SELECTED",
                    "message": "Financial year is required for filing-ready GST evidence.",
                }
            )
        return warnings

    def _input_tax_ledger_reconciliation(self, scope: GstComplianceScope) -> dict[str, Any]:
        try:
            gstr3b_scope = Gstr3bScope(
                entity_id=scope.entity_id,
                entityfinid_id=scope.entityfinid_id,
                subentity_id=scope.subentity_id,
                month=scope.month,
                year=scope.year,
                from_date=scope.from_date,
                to_date=scope.to_date,
            )
            gstr3b_summary = Gstr3bSummaryService().build(gstr3b_scope)
            return build_input_tax_ledger_reconciliation(gstr3b_summary=gstr3b_summary, scope=scope)
        except Exception as exc:  # pragma: no cover - defensive cockpit fallback
            return {
                "rows": [],
                "summary": {
                    "comparison_count": 0,
                    "matched_count": 0,
                    "mismatch_count": 0,
                    "return_total_itc": 0,
                    "ledger_total_itc": 0,
                    "difference_total_itc": 0,
                },
                "warnings": [
                    {
                        "code": "GST_INPUT_LEDGER_RECONCILIATION_FAILED",
                        "severity": "warning",
                        "message": f"Input GST ledger reconciliation could not be prepared: {exc}",
                    }
                ],
            }

    def _itc_decision_summary(self, *, scope: GstComplianceScope, gstin: str | None) -> dict[str, Any]:
        run = self._latest_gstr2b_run(scope=scope, gstin=gstin)
        empty = {
            "run_id": None,
            "run_status": "",
            "return_period": scope.return_period or "",
            "total_items": 0,
            "decided_items": 0,
            "pending_items": 0,
            "accepted_items": 0,
            "deferred_items": 0,
            "rejected_items": 0,
            "blocked_items": 0,
            "tax_by_decision": {
                "ACCEPT": "0.00",
                "DEFER": "0.00",
                "REJECT": "0.00",
                "BLOCK": "0.00",
                "PENDING": "0.00",
            },
            "portal_context_summary": {
                "amended_rows": 0,
                "vendor_revised_rows": 0,
                "ims_rows": 0,
                "ims_pending_rows": 0,
                "ims_rejected_rows": 0,
            },
        }
        if not run:
            return empty

        summary = {**empty, "run_id": run.id, "run_status": run.status, "return_period": run.return_period}
        items = GstReconciliationItem.objects.filter(run=run, is_active=True)
        totals = {key: 0 for key in ("ACCEPT", "DEFER", "REJECT", "BLOCK", "PENDING")}
        tax_by_decision = {key: 0 for key in totals}

        for item in items.values(
            "metadata_json",
            "cgst_books",
            "sgst_books",
            "igst_books",
            "cess_books",
            "cgst_imported",
            "sgst_imported",
            "igst_imported",
            "cess_imported",
        ):
            decision = ((item.get("metadata_json") or {}).get("itc_decision") or {}).get("decision") or "PENDING"
            decision = str(decision).strip().upper()
            if decision not in totals:
                decision = "PENDING"
            totals[decision] += 1
            tax_by_decision[decision] += self._itc_item_tax_total(item)

        summary.update(
            {
                "total_items": sum(totals.values()),
                "decided_items": totals["ACCEPT"] + totals["DEFER"] + totals["REJECT"] + totals["BLOCK"],
                "pending_items": totals["PENDING"],
                "accepted_items": totals["ACCEPT"],
                "deferred_items": totals["DEFER"],
                "rejected_items": totals["REJECT"],
                "blocked_items": totals["BLOCK"],
                "tax_by_decision": {key: f"{value:.2f}" for key, value in tax_by_decision.items()},
                "portal_context_summary": {
                    **empty["portal_context_summary"],
                    **((run.summary_json or {}).get("portal_context_summary") or {}),
                },
            }
        )
        return summary

    def _latest_gstr2b_run(self, *, scope: GstComplianceScope, gstin: str | None):
        qs = GstReconciliationRun.objects.filter(
            entity_id=scope.entity_id,
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            is_active=True,
        )
        if scope.entityfinid_id:
            qs = qs.filter(entityfinid_id=scope.entityfinid_id)
        if scope.subentity_id:
            qs = qs.filter(subentity_id=scope.subentity_id)
        if gstin:
            qs = qs.filter(gst_registration_gstin__iexact=gstin)
        if scope.return_period:
            qs = qs.filter(return_period=scope.return_period)
        elif scope.from_date and scope.to_date:
            qs = qs.filter(period_from__gte=scope.from_date, period_to__lte=scope.to_date)
        return qs.order_by("-revision_no", "-created_at", "-id").first()

    def _itc_item_tax_total(self, item: dict[str, Any]):
        books_total = (
            (item.get("cgst_books") or 0)
            + (item.get("sgst_books") or 0)
            + (item.get("igst_books") or 0)
            + (item.get("cess_books") or 0)
        )
        imported_total = (
            (item.get("cgst_imported") or 0)
            + (item.get("sgst_imported") or 0)
            + (item.get("igst_imported") or 0)
            + (item.get("cess_imported") or 0)
        )
        return books_total if books_total else imported_total

    def _einvoice_eway_summary(self, *, scope: GstComplianceScope, gstin: str | None) -> dict[str, Any]:
        empty = {
            "summary": {
                "invoices": 0,
                "irn_failed": 0,
                "ewb_failed": 0,
                "ewb_expired": 0,
            },
            "signals": {
                "irn_generated": 0,
                "irn_pending": 0,
                "irn_cancelled": 0,
                "ewb_generated": 0,
                "ewb_pending": 0,
                "ewb_cancelled": 0,
                "retry_ready": 0,
                "not_applicable": 0,
            },
            "warnings": [],
            "blockers": [],
            "status": "ready",
        }

        qs = (
            SalesInvoiceHeader.objects.filter(entity_id=scope.entity_id)
            .filter(status__in=[SalesInvoiceHeader.Status.CONFIRMED, SalesInvoiceHeader.Status.POSTED])
            .select_related("einvoice_artifact", "eway_artifact")
        )
        if hasattr(SalesInvoiceHeader, "is_active"):
            qs = qs.filter(is_active=True)
        if scope.entityfinid_id:
            qs = qs.filter(entityfinid_id=scope.entityfinid_id)
        if scope.subentity_id is not None:
            qs = qs.filter(subentity_id=scope.subentity_id)
        if scope.from_date:
            qs = qs.filter(bill_date__gte=scope.from_date)
        if scope.to_date:
            qs = qs.filter(bill_date__lte=scope.to_date)
        if gstin:
            qs = qs.filter(
                Q(seller_gstin__iexact=gstin)
                | Q(einvoice_artifact__credential_gstin__iexact=gstin)
                | Q(eway_artifact__credential_gstin__iexact=gstin)
            )

        counters = {
            "invoices": 0,
            "irn_generated": 0,
            "irn_pending": 0,
            "irn_failed": 0,
            "irn_cancelled": 0,
            "irn_not_applicable": 0,
            "ewb_generated": 0,
            "ewb_pending": 0,
            "ewb_failed": 0,
            "ewb_cancelled": 0,
            "ewb_not_applicable": 0,
            "ewb_expired": 0,
            "ewb_expiring_soon": 0,
            "ewb_missing_transport": 0,
            "retry_ready": 0,
        }
        provider_names: set[str] = set()
        provider_environments: set[str] = set()
        last_error = ""
        now = timezone.now()
        expiry_cutoff = now + timedelta(days=3)

        for invoice in qs:
            counters["invoices"] += 1
            einv = getattr(invoice, "einvoice_artifact", None)
            eway = getattr(invoice, "eway_artifact", None)

            if bool(getattr(invoice, "is_einvoice_applicable", False)):
                einv_status = int(getattr(einv, "status", 0) or 0) if einv else int(SalesEInvoiceStatus.PENDING)
                if einv_status == int(SalesEInvoiceStatus.GENERATED) and getattr(einv, "irn", None):
                    counters["irn_generated"] += 1
                elif einv_status == int(SalesEInvoiceStatus.CANCELLED):
                    counters["irn_cancelled"] += 1
                elif einv_status == int(SalesEInvoiceStatus.FAILED):
                    counters["irn_failed"] += 1
                    counters["retry_ready"] += 1
                else:
                    counters["irn_pending"] += 1
            else:
                counters["irn_not_applicable"] += 1

            if bool(getattr(invoice, "is_eway_applicable", False)):
                eway_status = int(getattr(eway, "status", 0) or 0) if eway else int(SalesEWayStatus.PENDING)
                if eway_status == int(SalesEWayStatus.GENERATED) and getattr(eway, "ewb_no", None):
                    counters["ewb_generated"] += 1
                    valid_upto = getattr(eway, "valid_upto", None)
                    if valid_upto and valid_upto < now:
                        counters["ewb_expired"] += 1
                    elif valid_upto and valid_upto <= expiry_cutoff:
                        counters["ewb_expiring_soon"] += 1
                    if not (getattr(eway, "vehicle_no", None) or getattr(eway, "transporter_id", None) or getattr(eway, "transporter_name", None)):
                        counters["ewb_missing_transport"] += 1
                elif eway_status == int(SalesEWayStatus.CANCELLED):
                    counters["ewb_cancelled"] += 1
                elif eway_status == int(SalesEWayStatus.FAILED):
                    counters["ewb_failed"] += 1
                    counters["retry_ready"] += 1
                else:
                    counters["ewb_pending"] += 1
            else:
                counters["ewb_not_applicable"] += 1

            for artifact in (einv, eway):
                provider_name = str(getattr(artifact, "provider_name", "") or "").strip()
                if provider_name:
                    provider_names.add(provider_name)
                provider_environment = getattr(artifact, "provider_environment", None)
                if provider_environment not in (None, ""):
                    provider_environments.add(str(provider_environment))
                error_message = str(getattr(artifact, "last_error_message", "") or "").strip()
                error_code = str(getattr(artifact, "last_error_code", "") or "").strip()
                if error_message or error_code:
                    last_error = error_message or error_code

        warnings: list[dict[str, str]] = []
        blockers: list[dict[str, str]] = []
        if counters["irn_failed"] or counters["ewb_failed"]:
            warnings.append(
                {
                    "code": "EINVOICE_EWAY_FAILED_ITEMS",
                    "message": f"{counters['irn_failed'] + counters['ewb_failed']} e-invoice/e-way item needs retry or correction.",
                }
            )
        if counters["irn_pending"] or counters["ewb_pending"]:
            warnings.append(
                {
                    "code": "EINVOICE_EWAY_PENDING_ITEMS",
                    "message": f"{counters['irn_pending'] + counters['ewb_pending']} e-invoice/e-way item is still pending for this period.",
                }
            )
        if counters["ewb_expired"]:
            blockers.append(
                {
                    "code": "EWAY_EXPIRED",
                    "message": f"{counters['ewb_expired']} generated e-way bill has expired in this period.",
                }
            )
        elif counters["ewb_expiring_soon"]:
            warnings.append(
                {
                    "code": "EWAY_EXPIRING_SOON",
                    "message": f"{counters['ewb_expiring_soon']} e-way bill expires within 3 days.",
                }
            )
        if counters["ewb_missing_transport"]:
            warnings.append(
                {
                    "code": "EWAY_TRANSPORT_DETAILS_INCOMPLETE",
                    "message": f"{counters['ewb_missing_transport']} generated e-way bill is missing vehicle/transporter detail.",
                }
            )

        return {
            "summary": {
                "invoices": counters["invoices"],
                "irn_failed": counters["irn_failed"],
                "ewb_failed": counters["ewb_failed"],
                "ewb_expired": counters["ewb_expired"],
            },
            "signals": {
                "irn_generated": counters["irn_generated"],
                "irn_pending": counters["irn_pending"],
                "irn_cancelled": counters["irn_cancelled"],
                "ewb_generated": counters["ewb_generated"],
                "ewb_pending": counters["ewb_pending"],
                "ewb_cancelled": counters["ewb_cancelled"],
                "retry_ready": counters["retry_ready"],
                "not_applicable": counters["irn_not_applicable"] + counters["ewb_not_applicable"],
                "ewb_expiring_soon": counters["ewb_expiring_soon"],
                "ewb_missing_transport": counters["ewb_missing_transport"],
                "provider_names": ", ".join(sorted(provider_names)),
                "provider_environments": ", ".join(sorted(provider_environments)),
                "last_provider_error": last_error,
            },
            "warnings": warnings,
            "blockers": blockers,
            "status": "blocked" if blockers else "needs_review" if warnings else "ready",
        }

    def _period(self, scope: GstComplianceScope) -> dict[str, Any]:
        if scope.return_period:
            return {"code": scope.return_period, "label": scope.return_period}
        if scope.from_date and scope.to_date:
            return {"code": f"{scope.from_date.isoformat()}:{scope.to_date.isoformat()}", "label": f"{scope.from_date.isoformat()} to {scope.to_date.isoformat()}"}
        return {"code": "", "label": "Current scope"}

    def _portal_return_period(self, scope: GstComplianceScope) -> str | None:
        if scope.month and scope.year:
            return f"{scope.month:02d}{scope.year}"
        if scope.return_period:
            parts = scope.return_period.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return f"{int(parts[1]):02d}{int(parts[0])}"
        if scope.from_date:
            return f"{scope.from_date.month:02d}{scope.from_date.year}"
        return None

    def _portal_profile(self, *, scope: GstComplianceScope, gstin: str):
        return (
            GstPortalProfile.objects.filter(entity_id=scope.entity_id, gstin__iexact=gstin, isactive=True)
            .order_by("-is_verified", "-last_verified_at", "-updated_at", "-id")
            .first()
        )

    def _latest_portal_filing(self, *, scope: GstComplianceScope, gstin: str, return_type: str, ret_period: str | None):
        qs = GstPortalFilingRun.objects.filter(
            entity_id=scope.entity_id,
            return_type=return_type,
            gstin__iexact=gstin,
            isactive=True,
        )
        if scope.entityfinid_id:
            qs = qs.filter(entityfinid_id=scope.entityfinid_id)
        if scope.subentity_id:
            qs = qs.filter(subentity_id=scope.subentity_id)
        if ret_period:
            qs = qs.filter(ret_period=ret_period)
        return qs.order_by("-created_at", "-id").first()

    def _latest_gstr9_freeze(self, scope: GstComplianceScope):
        qs = ReportFreezeSnapshot.objects.filter(report_code="gstr9", entity_id=scope.entity_id, isactive=True)
        if scope.entityfinid_id:
            qs = qs.filter(entityfinid_id=scope.entityfinid_id)
        if scope.subentity_id:
            qs = qs.filter(subentity_id=scope.subentity_id)
        return qs.order_by("-version", "-created_at", "-id").first()

    def _latest_gstr9_filing(self, scope: GstComplianceScope):
        qs = ReportFilingRun.objects.filter(report_code="gstr9", entity_id=scope.entity_id, isactive=True)
        if scope.entityfinid_id:
            qs = qs.filter(entityfinid_id=scope.entityfinid_id)
        if scope.subentity_id:
            qs = qs.filter(subentity_id=scope.subentity_id)
        return qs.order_by("-created_at", "-id").first()

    def _portal_status(self, filing_run, *, default: str) -> str:
        if not filing_run:
            return default
        if filing_run.status == GstPortalFilingRun.Status.FILED:
            return "filed"
        if filing_run.status == GstPortalFilingRun.Status.FAILED:
            return "blocked"
        if filing_run.status in {
            GstPortalFilingRun.Status.PREPARED,
            GstPortalFilingRun.Status.SAVED,
            GstPortalFilingRun.Status.PROCEEDED,
            GstPortalFilingRun.Status.SUMMARY_FETCHED,
            GstPortalFilingRun.Status.OFFSET,
            GstPortalFilingRun.Status.EVC_REQUESTED,
        }:
            return "prepared"
        return default

    def _annual_status(self, *, freeze_snapshot, filing_run) -> str:
        if filing_run:
            if filing_run.status == ReportFilingRun.Status.SUBMITTED:
                return "filed"
            if filing_run.status == ReportFilingRun.Status.FAILED:
                return "blocked"
            if filing_run.status == ReportFilingRun.Status.PREPARED:
                return "prepared"
        if freeze_snapshot:
            return "frozen"
        return "ready"
