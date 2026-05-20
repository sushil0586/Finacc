from __future__ import annotations

import json
import random
import time
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, SubEntity
from gst_reconciliation.models import GstImportedReturn, GstImportedReturnRow, GstReconciliationItem, GstReconciliationRun
from gst_reconciliation.services.dashboard_service import GstReconciliationDashboardService
from gst_reconciliation.services.ui_service import GstReconciliationUiService


class Command(BaseCommand):
    help = "Benchmark GST reconciliation summaries, queue operations, and pagination on large datasets."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, help="Existing reconciliation run to benchmark.")
        parser.add_argument("--entity", type=int, help="Entity id when seeding a benchmark run.")
        parser.add_argument("--entityfinid", type=int, help="Entity financial year id when seeding a benchmark run.")
        parser.add_argument("--subentity", type=int, help="Optional subentity id.")
        parser.add_argument("--user", type=int, help="User id for seeded rows.")
        parser.add_argument("--items", type=int, default=1000, help="Number of benchmark items to seed if run-id is not given.")
        parser.add_argument("--return-period", default="2026-04")
        parser.add_argument("--gstin", default="29ABCDE1234F1Z5")
        parser.add_argument("--explain", action="store_true", help="Print EXPLAIN plans for the hot queries.")

    def handle(self, *args, **options):
        run = self._resolve_run(options)
        self.stdout.write(self.style.NOTICE(f"Benchmarking run #{run.id} with {run.items.count()} items"))

        summary = self._measure("run_summary", lambda: GstReconciliationDashboardService.run_summary(run=run))
        supplier = self._measure("supplier_analytics", lambda: GstReconciliationDashboardService.supplier_mismatch_analytics(run=run))
        queue = self._measure(
            "reviewer_queue_summary",
            lambda: GstReconciliationUiService.build_reviewer_queue_summary(
                queryset=run.items.exclude(
                    resolution_status__in=[
                        GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
                        GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED,
                        GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH,
                        GstReconciliationItem.ResolutionStatus.IGNORED,
                        GstReconciliationItem.ResolutionStatus.RESOLVED,
                    ]
                )
            ),
        )
        pagination = self._measure(
            "page_slice",
            lambda: list(
                run.items.select_related("assigned_reviewer")
                .prefetch_related("mismatch_reasons")
                .order_by("-updated_at", "-id")[:100]
            ),
        )

        payload = {
            "run_id": run.id,
            "item_count": run.items.count(),
            "summary": summary,
            "supplier_analytics": supplier,
            "reviewer_queue": queue,
            "page_slice": pagination,
        }
        self.stdout.write(json.dumps(payload, indent=2, default=str))

        if options["explain"]:
            self._print_explain(run)

    def _resolve_run(self, options) -> GstReconciliationRun:
        run_id = options.get("run_id")
        if run_id:
            try:
                return GstReconciliationRun.objects.get(pk=run_id)
            except GstReconciliationRun.DoesNotExist as exc:
                raise CommandError(f"Run {run_id} not found.") from exc
        required = ["entity", "entityfinid", "user"]
        missing = [key for key in required if not options.get(key)]
        if missing:
            raise CommandError(f"Missing required args when seeding benchmark data: {', '.join(missing)}")
        return self._seed_run(options)

    def _seed_run(self, options) -> GstReconciliationRun:
        entity = Entity.objects.get(pk=options["entity"])
        entityfin = EntityFinancialYear.objects.get(pk=options["entityfinid"])
        user = User.objects.get(pk=options["user"])
        subentity = SubEntity.objects.filter(pk=options.get("subentity")).first() if options.get("subentity") else None
        imported_return = GstImportedReturn.objects.create(
            entity=entity,
            entityfinid=entityfin,
            subentity=subentity,
            gst_registration_gstin=options["gstin"],
            return_type=GstImportedReturn.ReturnType.GSTR2B,
            return_period=options["return_period"],
            source=GstImportedReturn.Source.MANUAL_ENTRY,
            status=GstImportedReturn.Status.CONSUMED,
            imported_by=user,
            imported_at=timezone.now(),
            created_by=user,
            updated_by=user,
        )
        run = GstReconciliationRun.objects.create(
            entity=entity,
            entityfinid=entityfin,
            subentity=subentity,
            gst_registration_gstin=options["gstin"],
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            return_period=options["return_period"],
            imported_return=imported_return,
            status=GstReconciliationRun.Status.IN_REVIEW,
            created_by=user,
            updated_by=user,
        )
        now = timezone.now()
        items = []
        rows = []
        reason_models = []
        for i in range(options["items"]):
            invoice_no = f"BENCH-{i:05d}"
            row = GstImportedReturnRow(
                entity=entity,
                entityfinid=entityfin,
                subentity=subentity,
                imported_return=imported_return,
                row_no=i + 1,
                row_hash=f"bench-{i}",
                counterparty_gstin=f"29SUPP{i % 9000:04d}F1Z5"[:15],
                counterparty_gstin_normalized=f"29SUPP{i % 9000:04d}F1Z5"[:15],
                counterparty_name=f"Supplier {i % 50}",
                invoice_number=invoice_no,
                invoice_number_normalized=invoice_no.replace("-", ""),
                invoice_date=datetime(2026, 4, 1).date(),
                taxable_value=Decimal("1000.00"),
                cgst=Decimal("90.00"),
                sgst=Decimal("90.00"),
                total_amount=Decimal("1180.00"),
                raw_row_json={"invoice_number": invoice_no},
                normalized_row_json={"invoice_number": invoice_no.replace("-", "")},
                created_by=user,
                updated_by=user,
            )
            rows.append(row)
        GstImportedReturnRow.objects.bulk_create(rows, batch_size=1000)
        created_rows = list(imported_return.rows.order_by("row_no"))
        statuses = [
            GstReconciliationItem.MatchStatus.MATCHED,
            GstReconciliationItem.MatchStatus.PARTIAL,
            GstReconciliationItem.MatchStatus.MISMATCHED,
            GstReconciliationItem.MatchStatus.MISSING_IN_BOOKS,
        ]
        resolution_statuses = [
            GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
            GstReconciliationItem.ResolutionStatus.PARTIAL_MATCH,
            GstReconciliationItem.ResolutionStatus.MISMATCH,
            GstReconciliationItem.ResolutionStatus.PENDING_REVIEW,
            GstReconciliationItem.ResolutionStatus.IGNORED,
            GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH,
        ]
        for i, row in enumerate(created_rows):
            match_status = statuses[i % len(statuses)]
            resolution_status = resolution_statuses[i % len(resolution_statuses)]
            item = GstReconciliationItem(
                entity=entity,
                entityfinid=entityfin,
                subentity=subentity,
                run=run,
                direction=GstReconciliationItem.Direction.PURCHASE,
                match_key=f"{row.counterparty_gstin}|{row.invoice_number}",
                source_document_type="gst_imported_return_row",
                source_document_id=str(row.id),
                gstin=options["gstin"],
                counterparty_gstin=row.counterparty_gstin,
                invoice_number=row.invoice_number,
                invoice_date=row.invoice_date,
                taxable_value_imported=row.taxable_value,
                cgst_imported=row.cgst,
                sgst_imported=row.sgst,
                match_status=match_status,
                resolution_status=resolution_status,
                mismatch_count=1 if match_status != GstReconciliationItem.MatchStatus.MATCHED else 0,
                match_confidence_score=Decimal(str(random.choice([35, 52, 78, 96]))),
                created_at=now - timedelta(days=i % 20),
                updated_at=now - timedelta(days=i % 7),
                created_by=user,
                updated_by=user,
            )
            items.append(item)
        GstReconciliationItem.objects.bulk_create(items, batch_size=1000)
        return run

    def _measure(self, label, fn):
        with CaptureQueriesContext(connection) as ctx:
            start = time.perf_counter()
            value = fn()
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
        size = None
        if isinstance(value, dict):
            size = len(value)
        elif isinstance(value, list):
            size = len(value)
        return {"duration_ms": duration_ms, "query_count": len(ctx), "result_size": size}

    def _print_explain(self, run: GstReconciliationRun):
        self.stdout.write(self.style.WARNING("EXPLAIN: run item queue query"))
        self.stdout.write(
            run.items.exclude(
                resolution_status__in=[
                    GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
                    GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED,
                    GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH,
                    GstReconciliationItem.ResolutionStatus.IGNORED,
                    GstReconciliationItem.ResolutionStatus.RESOLVED,
                ]
            )
            .order_by("-updated_at", "-id")
            .explain()
        )
