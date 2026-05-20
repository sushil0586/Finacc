from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.db.models import Case, CharField, Count, ExpressionWrapper, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from gst_reconciliation.models import GstMismatchReason, GstReconciliationItem, GstReconciliationRun
from gst_reconciliation.models.imported_returns import GstImportedReturnRow
from gst_reconciliation.services.performance import cached_run_computation


UNRESOLVED_RESOLUTION_STATUSES = [
    GstReconciliationItem.ResolutionStatus.PENDING_REVIEW,
    GstReconciliationItem.ResolutionStatus.ASSIGNED,
    GstReconciliationItem.ResolutionStatus.PARTIAL_MATCH,
    GstReconciliationItem.ResolutionStatus.MISMATCH,
    GstReconciliationItem.ResolutionStatus.REOPENED,
]


class GstReconciliationDashboardService:
    @staticmethod
    def _items_queryset(*, run: GstReconciliationRun):
        return GstReconciliationItem.objects.filter(run=run)

    @classmethod
    def run_summary(cls, *, run: GstReconciliationRun) -> dict:
        return cached_run_computation(
            run=run,
            suffix="summary",
            log_event="dashboard_summary",
            builder=lambda: cls._build_run_summary(run=run),
        ).value

    @classmethod
    def _build_run_summary(cls, *, run: GstReconciliationRun) -> dict:
        items = cls._items_queryset(run=run)
        counts = items.aggregate(
            total_items=Count("id"),
            matched_count=Count("id", filter=Q(match_status__in=[GstReconciliationItem.MatchStatus.MATCHED, GstReconciliationItem.MatchStatus.MANUALLY_RESOLVED])),
            unmatched_count=Count("id", filter=Q(match_status__in=[GstReconciliationItem.MatchStatus.MISSING_IN_BOOKS, GstReconciliationItem.MatchStatus.MISSING_IN_RETURN])),
            mismatch_count=Count("id", filter=Q(match_status__in=[GstReconciliationItem.MatchStatus.PARTIAL, GstReconciliationItem.MatchStatus.MISMATCHED, GstReconciliationItem.MatchStatus.DUPLICATE])),
            ignored_count=Count("id", filter=Q(resolution_status=GstReconciliationItem.ResolutionStatus.IGNORED)),
            accepted_mismatch_count=Count("id", filter=Q(resolution_status=GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH)),
            pending_review_count=Count("id", filter=Q(resolution_status__in=[GstReconciliationItem.ResolutionStatus.PENDING_REVIEW, GstReconciliationItem.ResolutionStatus.ASSIGNED, GstReconciliationItem.ResolutionStatus.REOPENED])),
            resolved_count=Count(
                "id",
                filter=Q(
                    resolution_status__in=[
                        GstReconciliationItem.ResolutionStatus.RESOLVED,
                        GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
                        GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED,
                        GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH,
                    ]
                ),
            ),
            assigned_count=Count("id", filter=Q(assigned_reviewer__isnull=False)),
            reviewed_count=Count("id", filter=Q(reviewed_at__isnull=False)),
            imported_taxable=Coalesce(Sum("taxable_value_imported"), Value(Decimal("0.00"))),
            books_taxable=Coalesce(Sum("taxable_value_books"), Value(Decimal("0.00"))),
        )
        total_items = counts["total_items"] or 0

        by_match = {
            row["match_status"]: row["count"]
            for row in items.values("match_status").annotate(count=Count("id")).order_by("match_status")
        }
        by_resolution = {
            row["resolution_status"]: row["count"]
            for row in items.values("resolution_status").annotate(count=Count("id")).order_by("resolution_status")
        }

        at_risk_queryset = items.filter(resolution_status__in=UNRESOLVED_RESOLUTION_STATUSES)
        at_risk_totals = at_risk_queryset.aggregate(
            taxable_value_at_risk=Coalesce(Sum("taxable_value_imported"), Value(Decimal("0.00"))),
            tax_amount_at_risk=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("cgst_imported") + F("sgst_imported") + F("igst_imported") + F("cess_imported"),
                        output_field=GstReconciliationItem._meta.get_field("cgst_imported"),
                    )
                ),
                Value(Decimal("0.00")),
            ),
        )

        mismatch_reason_rows = (
            GstMismatchReason.objects.filter(item__run=run)
            .values("code")
            .annotate(count=Count("id"))
            .order_by("-count", "code")[:5]
        )
        aging_rows = (
            at_risk_queryset.annotate(
                age_bucket=Case(
                    When(created_at__gte=timezone.now() - timedelta(days=7), then=Value("0_7_days")),
                    default=Case(
                        When(created_at__gte=timezone.now() - timedelta(days=15), then=Value("8_15_days")),
                        default=Value("16_plus_days"),
                        output_field=CharField(),
                    ),
                    output_field=CharField(),
                )
            )
            .values("age_bucket")
            .annotate(count=Count("id"))
        )
        aging = {"0_7_days": 0, "8_15_days": 0, "16_plus_days": 0}
        for row in aging_rows:
            aging[str(row["age_bucket"])] = row["count"]

        resolution_timings = []
        for created_at, resolved_at in items.filter(resolved_at__isnull=False).values_list("created_at", "resolved_at"):
            resolution_timings.append(max((resolved_at - created_at).total_seconds() / 3600, 0))
        avg_resolution_hours = round(sum(resolution_timings) / len(resolution_timings), 2) if resolution_timings else 0.0

        return {
            "run_id": run.id,
            "reconciliation_type": run.reconciliation_type,
            "return_period": run.return_period,
            "status": run.status,
            "item_count": total_items,
            "total_items": total_items,
            "matched_count": counts["matched_count"] or 0,
            "unmatched_count": counts["unmatched_count"] or 0,
            "mismatch_count": counts["mismatch_count"] or 0,
            "ignored_count": counts["ignored_count"] or 0,
            "accepted_mismatch_count": counts["accepted_mismatch_count"] or 0,
            "pending_review_count": counts["pending_review_count"] or 0,
            "resolved_count": counts["resolved_count"] or 0,
            "match_percentage": float(round(((counts["matched_count"] or 0) / total_items) * 100, 2)) if total_items else 0.0,
            "by_match_status": by_match,
            "by_resolution_status": by_resolution,
            "totals": {
                "imported_taxable": str(counts["imported_taxable"] or 0),
                "books_taxable": str(counts["books_taxable"] or 0),
            },
            "taxable_value_at_risk": str(at_risk_totals["taxable_value_at_risk"] or 0),
            "tax_amount_at_risk": str((at_risk_totals["tax_amount_at_risk"] or Decimal("0.00")).quantize(Decimal("0.01"))),
            "top_mismatch_reasons": [{"code": row["code"], "count": row["count"]} for row in mismatch_reason_rows],
            "unresolved_aging": aging,
            "reviewer_productivity": {
                "assigned_count": counts["assigned_count"] or 0,
                "reviewed_count": counts["reviewed_count"] or 0,
                "resolved_count": counts["resolved_count"] or 0,
                "avg_resolution_hours": avg_resolution_hours,
            },
        }

    @classmethod
    def supplier_mismatch_analytics(cls, *, run: GstReconciliationRun) -> list[dict]:
        return cached_run_computation(
            run=run,
            suffix="supplier-analytics",
            log_event="supplier_analytics",
            builder=lambda: cls._build_supplier_mismatch_analytics(run=run),
        ).value

    @classmethod
    def _build_supplier_mismatch_analytics(cls, *, run: GstReconciliationRun) -> list[dict]:
        items = cls._items_queryset(run=run).filter(counterparty_gstin__isnull=False).exclude(counterparty_gstin="")
        grouped_rows = list(
            items.values("counterparty_gstin")
            .annotate(
                total_items=Count("id"),
                matched_items=Count("id", filter=Q(match_status__in=[GstReconciliationItem.MatchStatus.MATCHED, GstReconciliationItem.MatchStatus.MANUALLY_RESOLVED])),
                mismatched_items=Count("id", filter=Q(match_status__in=[GstReconciliationItem.MatchStatus.PARTIAL, GstReconciliationItem.MatchStatus.MISMATCHED, GstReconciliationItem.MatchStatus.DUPLICATE])),
                missing_in_books=Count("id", filter=Q(match_status=GstReconciliationItem.MatchStatus.MISSING_IN_BOOKS)),
                accepted_mismatch_count=Count("id", filter=Q(resolution_status=GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH)),
                ignored_count=Count("id", filter=Q(resolution_status=GstReconciliationItem.ResolutionStatus.IGNORED)),
                unresolved_count=Count("id", filter=Q(resolution_status__in=UNRESOLVED_RESOLUTION_STATUSES)),
                imported_taxable=Coalesce(Sum("taxable_value_imported"), Value(Decimal("0.00"))),
                taxable_value_at_risk=Coalesce(Sum("taxable_value_imported", filter=Q(resolution_status__in=UNRESOLVED_RESOLUTION_STATUSES)), Value(Decimal("0.00"))),
                tax_amount_at_risk=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("cgst_imported") + F("sgst_imported") + F("igst_imported") + F("cess_imported"),
                            output_field=GstReconciliationItem._meta.get_field("cgst_imported"),
                        ),
                        filter=Q(resolution_status__in=UNRESOLVED_RESOLUTION_STATUSES),
                    ),
                    Value(Decimal("0.00")),
                ),
            )
            .order_by("-unresolved_count", "-mismatched_items", "counterparty_gstin")
        )
        gstin_list = [row["counterparty_gstin"] for row in grouped_rows]

        name_lookup = {}
        row_links = (
            items.filter(source_document_type="gst_imported_return_row", source_document_id__regex=r"^\d+$")
            .values("counterparty_gstin", "source_document_id")
            .order_by("counterparty_gstin", "id")
        )
        row_ids = [int(row["source_document_id"]) for row in row_links]
        imported_names = {
            row.id: row.counterparty_name
            for row in GstImportedReturnRow.objects.filter(id__in=row_ids).only("id", "counterparty_name")
        }
        for row in row_links:
            gstin = row["counterparty_gstin"]
            if gstin not in name_lookup:
                name_lookup[gstin] = imported_names.get(int(row["source_document_id"]))

        reason_rows = (
            GstMismatchReason.objects.filter(item__run=run, item__counterparty_gstin__in=gstin_list)
            .values("item__counterparty_gstin", "code")
            .annotate(count=Count("id"))
            .order_by("item__counterparty_gstin", "-count", "code")
        )
        reason_counter: dict[str, Counter[str]] = {}
        for row in reason_rows:
            reason_counter.setdefault(row["item__counterparty_gstin"], Counter())[row["code"]] = row["count"]

        status_rows = (
            items.values("counterparty_gstin", "match_status")
            .annotate(count=Count("id"))
            .order_by("counterparty_gstin", "match_status")
        )
        status_map: dict[str, dict[str, int]] = {}
        for row in status_rows:
            status_map.setdefault(row["counterparty_gstin"], {})[row["match_status"]] = row["count"]

        results = []
        for row in grouped_rows:
            gstin = row["counterparty_gstin"]
            top_reason = None
            if reason_counter.get(gstin):
                top_reason = reason_counter[gstin].most_common(1)[0][0]
            results.append(
                {
                    "counterparty_gstin": gstin,
                    "supplier_name": name_lookup.get(gstin),
                    "item_count": row["total_items"],
                    "total_items": row["total_items"],
                    "matched_items": row["matched_items"],
                    "mismatched_items": row["mismatched_items"],
                    "missing_in_books": row["missing_in_books"],
                    "accepted_mismatch_count": row["accepted_mismatch_count"],
                    "ignored_count": row["ignored_count"],
                    "unresolved_count": row["unresolved_count"],
                    "taxable_value_at_risk": str(row["taxable_value_at_risk"] or 0),
                    "tax_amount_at_risk": str((row["tax_amount_at_risk"] or Decimal("0.00")).quantize(Decimal("0.01"))),
                    "imported_taxable": str(row["imported_taxable"] or 0),
                    "top_mismatch_reason": top_reason,
                    "top_match_statuses": status_map.get(gstin, {}),
                }
            )
        return results
