from __future__ import annotations

from statistics import mean
from time import perf_counter

from django.core.management.base import BaseCommand, CommandError

from bank_reco.models import BankReconciliationRun, BankStatementImport
from bank_reco.services.imports import build_workspace_summary
from bank_reco.services.matching import build_workspace_payload
from bank_reco.services.reports import (
    build_audit_trail_report,
    build_brs_report,
    build_unmatched_bank_report,
    build_unmatched_books_report,
)


REPORT_CHOICES = (
    "workspace_summary",
    "workspace_payload",
    "unmatched_bank",
    "unmatched_books",
    "audit_trail",
    "brs",
)


class Command(BaseCommand):
    help = "Benchmark bank reconciliation workspace/report builders for a given scope."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, required=True)
        parser.add_argument("--entityfin-id", type=int, default=None)
        parser.add_argument("--subentity-id", type=int, default=None)
        parser.add_argument("--bank-account-id", type=int, default=None)
        parser.add_argument("--run-id", type=int, default=None)
        parser.add_argument("--import-id", type=int, default=None)
        parser.add_argument("--iterations", type=int, default=3)
        parser.add_argument("--warmup", type=int, default=1)
        parser.add_argument(
            "--report",
            action="append",
            choices=REPORT_CHOICES,
            dest="reports",
            help="Run only the selected benchmark. Repeat to benchmark multiple builders.",
        )

    def handle(self, *args, **options):
        entity_id = options["entity_id"]
        entityfin_id = options.get("entityfin_id")
        subentity_id = options.get("subentity_id")
        bank_account_id = options.get("bank_account_id")
        run_id = options.get("run_id")
        import_id = options.get("import_id")
        iterations = max(int(options.get("iterations") or 1), 1)
        warmup = max(int(options.get("warmup") or 0), 0)
        reports = options.get("reports") or list(REPORT_CHOICES)

        scope = self._resolve_scope(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            bank_account_id=bank_account_id,
            run_id=run_id,
            import_id=import_id,
        )

        self.stdout.write(self.style.SUCCESS("Bank reconciliation benchmark"))
        self.stdout.write(f"Entity: {scope['entity'].id}")
        self.stdout.write(f"Financial year: {getattr(scope['entityfin'], 'id', None) or '-'}")
        self.stdout.write(f"Subentity: {getattr(scope['subentity'], 'id', None) or '-'}")
        self.stdout.write(f"Bank account: {getattr(scope['bank_account'], 'id', None) or '-'}")
        self.stdout.write(f"Import: {getattr(scope['statement_import'], 'id', None) or '-'}")
        self.stdout.write(f"Run: {getattr(scope['run'], 'id', None) or '-'}")
        self.stdout.write(f"Warmup iterations: {warmup}")
        self.stdout.write(f"Measured iterations: {iterations}")
        self.stdout.write("")

        for report_code in reports:
            builder = self._builder(report_code=report_code, scope=scope)

            for _ in range(warmup):
                builder()

            timings_ms: list[float] = []
            item_count = None
            for _ in range(iterations):
                started_at = perf_counter()
                payload = builder()
                elapsed_ms = (perf_counter() - started_at) * 1000
                timings_ms.append(elapsed_ms)
                item_count = self._item_count(report_code, payload)

            self.stdout.write(
                f"{report_code}: avg={mean(timings_ms):.2f} ms | "
                f"min={min(timings_ms):.2f} ms | max={max(timings_ms):.2f} ms | "
                f"items={item_count}"
            )

    def _resolve_scope(
        self,
        *,
        entity_id: int,
        entityfin_id: int | None,
        subentity_id: int | None,
        bank_account_id: int | None,
        run_id: int | None,
        import_id: int | None,
    ):
        statement_import = None
        run = None

        if run_id:
            run = (
                BankReconciliationRun.objects.select_related(
                    "entity",
                    "entityfin",
                    "subentity",
                    "bank_account",
                    "statement_import",
                )
                .get(pk=run_id)
            )
            statement_import = run.statement_import
        elif import_id:
            statement_import = (
                BankStatementImport.objects.select_related(
                    "entity",
                    "entityfin",
                    "subentity",
                    "bank_account",
                )
                .get(pk=import_id)
            )
            run = (
                BankReconciliationRun.objects.select_related(
                    "entity",
                    "entityfin",
                    "subentity",
                    "bank_account",
                    "statement_import",
                )
                .filter(statement_import=statement_import)
                .order_by("-created_at", "-id")
                .first()
            )
        else:
            imports = BankStatementImport.objects.select_related(
                "entity",
                "entityfin",
                "subentity",
                "bank_account",
            ).filter(entity_id=entity_id)
            runs = BankReconciliationRun.objects.select_related(
                "entity",
                "entityfin",
                "subentity",
                "bank_account",
                "statement_import",
            ).filter(entity_id=entity_id)
            if entityfin_id:
                imports = imports.filter(entityfin_id=entityfin_id)
                runs = runs.filter(entityfin_id=entityfin_id)
            if subentity_id:
                imports = imports.filter(subentity_id=subentity_id)
                runs = runs.filter(subentity_id=subentity_id)
            if bank_account_id:
                imports = imports.filter(bank_account_id=bank_account_id)
                runs = runs.filter(bank_account_id=bank_account_id)
            run = runs.order_by("-created_at", "-id").first()
            statement_import = (
                run.statement_import
                if run is not None
                else imports.order_by("-created_at", "-id").first()
            )

        if statement_import is None and run is None:
            raise CommandError("No bank reconciliation import or run found for the selected scope.")

        entity = getattr(run, "entity", None) or getattr(statement_import, "entity", None)
        entityfin = getattr(run, "entityfin", None) or getattr(statement_import, "entityfin", None)
        subentity = getattr(run, "subentity", None) or getattr(statement_import, "subentity", None)
        bank_account = getattr(run, "bank_account", None) or getattr(statement_import, "bank_account", None)

        return {
            "entity": entity,
            "entityfin": entityfin,
            "subentity": subentity,
            "bank_account": bank_account,
            "statement_import": statement_import,
            "run": run,
        }

    def _builder(self, *, report_code: str, scope: dict):
        if report_code == "workspace_summary":
            return lambda: build_workspace_summary(
                entity=scope["entity"],
                entityfin=scope["entityfin"],
                subentity=scope["subentity"],
                bank_account=scope["bank_account"],
            )
        if report_code == "workspace_payload":
            statement_import = scope["statement_import"]
            if statement_import is None:
                raise CommandError("workspace_payload benchmark requires a statement import in scope.")
            return lambda: build_workspace_payload(
                statement_import=statement_import,
                run=scope["run"],
            )
        if report_code == "unmatched_bank":
            run = scope["run"]
            if run is None:
                raise CommandError("unmatched_bank benchmark requires a reconciliation run in scope.")
            return lambda: build_unmatched_bank_report(run=run)
        if report_code == "unmatched_books":
            run = scope["run"]
            if run is None:
                raise CommandError("unmatched_books benchmark requires a reconciliation run in scope.")
            return lambda: build_unmatched_books_report(run=run)
        if report_code == "audit_trail":
            run = scope["run"]
            if run is None:
                raise CommandError("audit_trail benchmark requires a reconciliation run in scope.")
            return lambda: build_audit_trail_report(run=run)
        if report_code == "brs":
            run = scope["run"]
            if run is None:
                raise CommandError("brs benchmark requires a reconciliation run in scope.")
            return lambda: build_brs_report(run=run)
        raise CommandError(f"Unsupported benchmark code: {report_code}")

    def _item_count(self, report_code: str, payload: dict) -> int:
        if report_code == "workspace_summary":
            return len(payload.get("recent_imports") or []) + len(payload.get("recent_activity") or [])
        if report_code == "workspace_payload":
            return (
                len(payload.get("unmatched_bank_lines") or [])
                + len(payload.get("unmatched_book_lines") or [])
                + len(payload.get("suggested_matches") or [])
                + len(payload.get("confirmed_matches") or [])
            )
        if report_code in {"unmatched_bank", "unmatched_books", "audit_trail"}:
            return len(payload.get("rows") or [])
        if report_code == "brs":
            return len(payload.get("sections") or [])
        return 0
