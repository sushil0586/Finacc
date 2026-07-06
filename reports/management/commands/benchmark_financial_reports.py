from __future__ import annotations

from statistics import mean
from time import perf_counter

from django.core.management.base import BaseCommand, CommandError

from reports.selectors.financial import resolve_date_window
from reports.services.financial.statements import build_balance_sheet, build_profit_and_loss
from reports.services.financial.trial_balance import build_trial_balance
from reports.services.trading_account import build_trading_account_dynamic


REPORT_CHOICES = ("trial_balance", "profit_loss", "balance_sheet", "trading_account")


class Command(BaseCommand):
    help = "Benchmark core financial report builders for a given entity/scope."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, required=True)
        parser.add_argument("--entityfin-id", type=int, default=None)
        parser.add_argument("--subentity-id", type=int, default=None)
        parser.add_argument("--from-date", type=str, default=None)
        parser.add_argument("--to-date", type=str, default=None)
        parser.add_argument("--as-of-date", type=str, default=None)
        parser.add_argument("--iterations", type=int, default=3)
        parser.add_argument("--warmup", type=int, default=1)
        parser.add_argument(
            "--period-by",
            choices=("month", "quarter", "year"),
            default=None,
            help="Benchmark comparison mode as well as the base report shape.",
        )
        parser.add_argument(
            "--report",
            action="append",
            choices=REPORT_CHOICES,
            dest="reports",
            help="Run only the selected report. Repeat the flag to benchmark multiple reports.",
        )

    def handle(self, *args, **options):
        entity_id = options["entity_id"]
        entityfin_id = options.get("entityfin_id")
        subentity_id = options.get("subentity_id")
        from_date = options.get("from_date")
        to_date = options.get("to_date")
        as_of_date = options.get("as_of_date")
        iterations = max(int(options.get("iterations") or 1), 1)
        warmup = max(int(options.get("warmup") or 0), 0)
        period_by = options.get("period_by")
        reports = options.get("reports") or list(REPORT_CHOICES)

        report_start, report_end = self._resolve_window(
            entityfin_id=entityfin_id,
            from_date=from_date,
            to_date=to_date,
            as_of_date=as_of_date,
        )

        self.stdout.write(self.style.SUCCESS("Financial report benchmark"))
        self.stdout.write(f"Entity: {entity_id}")
        self.stdout.write(f"Financial year: {entityfin_id or '-'}")
        self.stdout.write(f"Subentity: {subentity_id or '-'}")
        self.stdout.write(f"Window: {report_start} -> {report_end}")
        self.stdout.write(f"Warmup iterations: {warmup}")
        self.stdout.write(f"Measured iterations: {iterations}")
        self.stdout.write("")

        for report_code in reports:
            builder = self._builder(
                report_code=report_code,
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                from_date=from_date,
                to_date=to_date,
                as_of_date=as_of_date,
                report_start=report_start,
                report_end=report_end,
                period_by=period_by,
            )

            for _ in range(warmup):
                builder()

            timings_ms: list[float] = []
            row_count = None
            for _ in range(iterations):
                started_at = perf_counter()
                payload = builder()
                elapsed_ms = (perf_counter() - started_at) * 1000
                timings_ms.append(elapsed_ms)
                row_count = self._row_count(report_code, payload)

            self.stdout.write(
                f"{report_code}: avg={mean(timings_ms):.2f} ms | "
                f"min={min(timings_ms):.2f} ms | max={max(timings_ms):.2f} ms | "
                f"rows={row_count}"
            )

    def _resolve_window(self, *, entityfin_id, from_date, to_date, as_of_date):
        if entityfin_id:
            start, end = resolve_date_window(entityfin_id, from_date, as_of_date or to_date)
            return start.isoformat(), end.isoformat()
        if from_date and (to_date or as_of_date):
            return from_date, as_of_date or to_date
        raise CommandError(
            "Provide either --entityfin-id or an explicit --from-date with --to-date/--as-of-date."
        )

    def _builder(
        self,
        *,
        report_code,
        entity_id,
        entityfin_id,
        subentity_id,
        from_date,
        to_date,
        as_of_date,
        report_start,
        report_end,
        period_by,
    ):
        if report_code == "trial_balance":
            return lambda: build_trial_balance(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                from_date=from_date,
                to_date=to_date,
                as_of_date=as_of_date,
                page=1,
                page_size=100,
                period_by=period_by,
            )
        if report_code == "profit_loss":
            return lambda: build_profit_and_loss(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                from_date=from_date,
                to_date=to_date,
                as_of_date=as_of_date,
                page=1,
                page_size=100,
                period_by=period_by,
            )
        if report_code == "balance_sheet":
            return lambda: build_balance_sheet(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                from_date=from_date,
                to_date=to_date,
                as_of_date=as_of_date,
                page=1,
                page_size=100,
                period_by=period_by,
            )
        if report_code == "trading_account":
            return lambda: build_trading_account_dynamic(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                startdate=report_start,
                enddate=report_end,
                period_by=period_by,
                inventory_breakdown=False,
            )
        raise CommandError(f"Unsupported report code: {report_code}")

    def _row_count(self, report_code: str, payload: dict) -> int:
        if report_code == "trial_balance":
            return len(payload.get("rows") or [])
        if report_code == "profit_loss":
            return len(payload.get("income") or []) + len(payload.get("expenses") or [])
        if report_code == "balance_sheet":
            return len(payload.get("assets") or []) + len(payload.get("liabilities_and_equity") or [])
        if report_code == "trading_account":
            return len(payload.get("debit_rows") or []) + len(payload.get("credit_rows") or [])
        return 0
