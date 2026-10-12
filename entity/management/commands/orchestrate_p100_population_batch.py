from __future__ import annotations

import json
import time
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Sum

from entity.management.commands.seed_multitenant_performance_population import Command as PopulationCommand
from entity.models import Entity, PerformanceFixtureCheckpoint, PerformanceFixtureRun
from purchase.models.purchase_ap import VendorBillOpenItem, VendorSettlement
from purchase.models.purchase_core import PurchaseInvoiceHeader
from sales.models import CustomerBillOpenItem, CustomerSettlement, SalesInvoiceHeader


DEFAULT_BACKUP_PATH = "docs/qa/performance/evidence/phase2c/backups/phase2c2c3_finacc_perf_local_2026-10-11.dump"
PROTECTED_ENTITY_IDS = {5, 6, 7, 8, 9, 10, 11, 12}


class Command(BaseCommand):
    help = "Orchestrate safety gates and bounded execution windows for the approved Phase 2C p100 population."

    def add_arguments(self, parser):
        parser.add_argument("--namespace", required=True)
        parser.add_argument("--expected-fingerprint", required=True)
        parser.add_argument("--start-sequence", type=int, required=True)
        parser.add_argument("--end-sequence", type=int, required=True)
        parser.add_argument("--seed", type=int, default=20261011)
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--allow-db-name", action="append", default=[])
        parser.add_argument("--allow-db-host", action="append", default=[])
        parser.add_argument("--backup-path", default=DEFAULT_BACKUP_PATH)
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--execute-window", action="store_true", help="Actually invoke the generator for the bounded window.")
        parser.add_argument("--allow-execution-namespace", action="append", default=[])
        parser.add_argument("--confirm-execute-namespace", default="")
        parser.add_argument("--password-env", default=PopulationCommand.PASSWORD_ENV)
        parser.add_argument("--provision-auth", action="store_true")

    def handle(self, *args, **options):
        started = time.perf_counter()
        namespace = PopulationCommand._normalize_namespace(options["namespace"])
        start_sequence = int(options["start_sequence"])
        end_sequence = int(options["end_sequence"])
        selected_count = self._validate_window(start_sequence, end_sequence)
        backup = self._verify_backup(options["backup_path"])

        population = PopulationCommand()
        self._assert_safety(options)
        tenants = population._population_tenants(namespace, "p100")
        selected = population._selected_tenant_window(
            tenants,
            start_sequence=start_sequence,
            limit=selected_count,
        )
        fingerprint = population._config_fingerprint(namespace, "p100", int(options["seed"]), tenants)
        if fingerprint != options["expected_fingerprint"]:
            raise CommandError("Expected fingerprint does not match the approved p100 configuration.")
        run = self._verify_run(namespace, fingerprint)

        before = self._state_snapshot(population, namespace, run, selected)
        if options["execute_window"]:
            self._assert_execution_authorized(namespace, options)
            self._execute_generator(namespace, start_sequence, selected_count, options)
        else:
            self._dry_run_generator(namespace, start_sequence, selected_count, options)
        after = self._state_snapshot(population, namespace, run, selected)

        payload = {
            "mode": "execute" if options["execute_window"] else "readiness",
            "namespace": namespace,
            "profile": "p100",
            "generator_version": population.GENERATOR_VERSION,
            "fingerprint": fingerprint,
            "selected_window": population._selected_window_payload(selected),
            "selected_estimated_records": population._estimate_records([tenant for _sequence, tenant in selected]),
            "backup": backup,
            "before": before,
            "after": after,
            "checks": self._checks(before, after, execute=options["execute_window"]),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
        self._write(payload, options)

    @staticmethod
    def _validate_window(start_sequence: int, end_sequence: int) -> int:
        if start_sequence < 1:
            raise CommandError("--start-sequence must be 1 or greater.")
        if end_sequence < start_sequence:
            raise CommandError("--end-sequence must be greater than or equal to --start-sequence.")
        selected_count = end_sequence - start_sequence + 1
        if selected_count > 10:
            raise CommandError("A p100 orchestration batch may not exceed 10 tenants.")
        if end_sequence > 100:
            raise CommandError("p100 sequence windows cannot exceed sequence 100.")
        return selected_count

    @staticmethod
    def _verify_backup(path_value: str) -> dict:
        path = Path(path_value)
        if not path.exists() or not path.is_file():
            raise CommandError(f"Required recovery backup is missing: {path_value}")
        if path.stat().st_size <= 0:
            raise CommandError(f"Required recovery backup is empty: {path_value}")
        return {"path": path_value, "size_bytes": path.stat().st_size}

    def _assert_safety(self, options):
        out = StringIO()
        args = ["--json", "--strict"]
        for name in options["allow_db_name"]:
            args.extend(["--allow-db-name", name])
        for host in options["allow_db_host"]:
            args.extend(["--allow-db-host", host])
        call_command("audit_performance_staging", *args, stdout=out)
        payload = json.loads(out.getvalue())
        if not payload.get("ready"):
            raise CommandError("Batch orchestration blocked because strict safety audit is not ready.")

    @staticmethod
    def _verify_run(namespace: str, fingerprint: str) -> PerformanceFixtureRun:
        try:
            run = PerformanceFixtureRun.objects.get(namespace=namespace)
        except PerformanceFixtureRun.DoesNotExist as exc:
            raise CommandError(f"No durable fixture run exists for namespace {namespace}.") from exc
        if run.profile != "p100":
            raise CommandError(f"Namespace {namespace} is not a p100 run.")
        if run.config_fingerprint != fingerprint:
            raise CommandError("Existing run fingerprint does not match the approved p100 configuration.")
        if run.target_tenants != 100:
            raise CommandError("Existing run target_tenants is not 100.")
        return run

    @staticmethod
    def _assert_execution_authorized(namespace: str, options):
        allowed = {item.strip().upper() for item in options["allow_execution_namespace"] if item.strip()}
        if namespace not in allowed:
            raise CommandError("--allow-execution-namespace must include the exact namespace for execution.")
        if options["confirm_execute_namespace"] != namespace:
            raise CommandError("--confirm-execute-namespace must exactly match --namespace for execution.")

    def _dry_run_generator(self, namespace: str, start_sequence: int, selected_count: int, options):
        out = StringIO()
        args = [
            "--namespace",
            namespace,
            "--profile",
            "p100",
            "--seed",
            str(options["seed"]),
            "--batch-size",
            str(options["batch_size"]),
            "--tenant-start-sequence",
            str(start_sequence),
            "--tenant-limit",
            str(selected_count),
            "--json",
        ]
        for name in options["allow_db_name"]:
            args.extend(["--allow-db-name", name])
        for host in options["allow_db_host"]:
            args.extend(["--allow-db-host", host])
        call_command("seed_multitenant_performance_population", *args, stdout=out)
        return json.loads(out.getvalue())

    def _execute_generator(self, namespace: str, start_sequence: int, selected_count: int, options):
        args = [
            "--namespace",
            namespace,
            "--profile",
            "p100",
            "--seed",
            str(options["seed"]),
            "--batch-size",
            str(options["batch_size"]),
            "--tenant-start-sequence",
            str(start_sequence),
            "--tenant-limit",
            str(selected_count),
            "--execute",
            "--allow-execution-namespace",
            namespace,
            "--confirm-execute-namespace",
            namespace,
            "--max-tenants",
            "100",
            "--password-env",
            options["password_env"],
            "--json",
        ]
        for name in options["allow_db_name"]:
            args.extend(["--allow-db-name", name])
        for host in options["allow_db_host"]:
            args.extend(["--allow-db-host", host])
        if options["provision_auth"]:
            args.append("--provision-auth")
        call_command("seed_multitenant_performance_population", *args, stdout=StringIO())

    def _state_snapshot(self, population: PopulationCommand, namespace: str, run: PerformanceFixtureRun, selected) -> dict:
        source_system = population._source_system(namespace)
        selected_sequences = [sequence for sequence, _tenant in selected]
        selected_checkpoints = list(
            PerformanceFixtureCheckpoint.objects.filter(run=run, sequence__in=selected_sequences)
            .order_by("sequence")
            .values(
                "sequence",
                "tenant_code",
                "entity_id",
                "status",
                "committed_sales",
                "committed_purchase",
                "reconciliation_hash",
            )
        )
        all_checkpoints = PerformanceFixtureCheckpoint.objects.filter(run=run)
        aggregate = population._validate_namespace(namespace, source_system)
        protected = population._protected_snapshot()
        return {
            "run_status": PerformanceFixtureRun.objects.get(pk=run.pk).status,
            "completed_checkpoints": all_checkpoints.filter(status=PerformanceFixtureCheckpoint.Status.COMPLETED).count(),
            "failed_checkpoints": all_checkpoints.filter(status=PerformanceFixtureCheckpoint.Status.FAILED).count(),
            "max_checkpoint_sequence": all_checkpoints.order_by("-sequence").values_list("sequence", flat=True).first() or 0,
            "selected_checkpoints": selected_checkpoints,
            "aggregate_validation": aggregate,
            "protected_snapshot": protected,
            "namespace_financial": self._namespace_financial(namespace),
            "runtime": population._runtime_snapshot(),
        }

    @staticmethod
    def _namespace_financial(namespace: str) -> dict:
        entities = Entity.objects.filter(entityname__startswith=f"{namespace} ", isactive=True)
        entity_ids = list(entities.values_list("id", flat=True))
        return {
            "tenant_count": len(entity_ids),
            "sales_count": SalesInvoiceHeader.objects.filter(entity_id__in=entity_ids).count(),
            "purchase_count": PurchaseInvoiceHeader.objects.filter(entity_id__in=entity_ids).count(),
            "ar_open_sum": str(CustomerBillOpenItem.objects.filter(entity_id__in=entity_ids).aggregate(total=Sum("outstanding_amount"))["total"] or 0),
            "ap_open_sum": str(VendorBillOpenItem.objects.filter(entity_id__in=entity_ids).aggregate(total=Sum("outstanding_amount"))["total"] or 0),
            "customer_settlements": CustomerSettlement.objects.filter(entity_id__in=entity_ids).count(),
            "vendor_settlements": VendorSettlement.objects.filter(entity_id__in=entity_ids).count(),
            "duplicate_sales_doc_numbers": list(
                SalesInvoiceHeader.objects.filter(entity_id__in=entity_ids)
                .values("entity_id", "doc_no")
                .annotate(c=Count("id"))
                .filter(c__gt=1)
                .values("entity_id", "doc_no", "c")[:20]
            ),
            "duplicate_purchase_doc_numbers": list(
                PurchaseInvoiceHeader.objects.filter(entity_id__in=entity_ids)
                .values("entity_id", "doc_no")
                .annotate(c=Count("id"))
                .filter(c__gt=1)
                .values("entity_id", "doc_no", "c")[:20]
            ),
        }

    @staticmethod
    def _checks(before: dict, after: dict, *, execute: bool) -> dict:
        protected_unchanged = before["protected_snapshot"] == after["protected_snapshot"]
        no_failed_checkpoints = after["failed_checkpoints"] == 0
        no_duplicate_docs = (
            not after["namespace_financial"]["duplicate_sales_doc_numbers"]
            and not after["namespace_financial"]["duplicate_purchase_doc_numbers"]
        )
        balanced = bool(after["aggregate_validation"].get("balanced"))
        selected_complete_or_pending = all(
            row["status"] in {PerformanceFixtureCheckpoint.Status.COMPLETED, PerformanceFixtureCheckpoint.Status.PLANNED}
            for row in after["selected_checkpoints"]
        )
        return {
            "protected_unchanged": protected_unchanged,
            "no_failed_checkpoints": no_failed_checkpoints,
            "no_duplicate_documents": no_duplicate_docs,
            "balanced_namespace": balanced,
            "selected_checkpoints_complete_or_pending": selected_complete_or_pending,
            "mode": "execute" if execute else "readiness",
            "pass": all([protected_unchanged, no_failed_checkpoints, no_duplicate_docs, balanced, selected_complete_or_pending]),
        }

    def _write(self, payload: dict, options):
        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
        else:
            self.stdout.write(f"p100 batch orchestration {payload['mode']}: pass={payload['checks']['pass']}")
