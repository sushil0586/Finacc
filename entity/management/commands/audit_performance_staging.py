from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


@dataclass(frozen=True)
class StagingGate:
    key: str
    status: str
    message: str
    expected: str
    observed: str


class Command(BaseCommand):
    help = "Audit performance-staging isolation and side-effect safety without printing secrets."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
        parser.add_argument("--strict", action="store_true", help="Exit non-zero when any gate is blocked.")
        parser.add_argument(
            "--allow-db-name",
            action="append",
            default=[],
            help="Allowed staging DB name. Repeat for aliases. Defaults to FINACC_PERF_ALLOWED_DB_NAMES.",
        )
        parser.add_argument(
            "--allow-db-host",
            action="append",
            default=[],
            help="Allowed staging DB host. Repeat for aliases. Defaults to FINACC_PERF_ALLOWED_DB_HOSTS.",
        )

    def handle(self, *args, **options):
        gates = self._build_gates(
            allowed_db_names=self._csv_env("FINACC_PERF_ALLOWED_DB_NAMES") + list(options["allow_db_name"]),
            allowed_db_hosts=self._csv_env("FINACC_PERF_ALLOWED_DB_HOSTS") + list(options["allow_db_host"]),
        )
        payload = {
            "ready": all(gate.status in {"verified", "not_applicable"} for gate in gates),
            "verified_count": sum(1 for gate in gates if gate.status == "verified"),
            "blocked_count": sum(1 for gate in gates if gate.status == "blocked"),
            "not_applicable_count": sum(1 for gate in gates if gate.status == "not_applicable"),
            "gates": [asdict(gate) for gate in gates],
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
        else:
            for gate in gates:
                style = self.style.SUCCESS if gate.status == "verified" else self.style.WARNING
                if gate.status == "blocked":
                    style = self.style.ERROR
                self.stdout.write(style(f"{gate.status.upper()} {gate.key}: {gate.message}"))
            self.stdout.write(
                "performance_staging_ready="
                f"{payload['ready']} verified={payload['verified_count']} "
                f"blocked={payload['blocked_count']} not_applicable={payload['not_applicable_count']}"
            )
        if options["strict"] and payload["blocked_count"]:
            raise CommandError(f"Performance staging audit blocked by {payload['blocked_count']} gate(s).")

    def _build_gates(self, *, allowed_db_names: list[str], allowed_db_hosts: list[str]) -> list[StagingGate]:
        db = settings.DATABASES["default"]
        db_name = str(db.get("NAME") or "")
        db_host = str(db.get("HOST") or "")
        cache_backend = str(settings.CACHES["default"].get("BACKEND") or "")
        cache_location = str(settings.CACHES["default"].get("LOCATION") or "")
        email_backend = str(getattr(settings, "EMAIL_BACKEND", "") or "")
        whitebooks_url = str(getattr(settings, "WHITEBOOKS_BASE_URL", "") or "")
        mastergst_env = str(getattr(settings, "MASTERGST_ENV", "") or "")
        storage_backend = str(getattr(settings, "FILE_STORAGE_BACKEND", "") or "")

        gates = [
            self._gate(
                "DEBUG_DISABLED",
                not bool(settings.DEBUG),
                "DEBUG is disabled.",
                "DEBUG must be False for staging performance tests.",
                str(settings.DEBUG),
            ),
            self._gate(
                "DB_NAME_ALLOWLIST",
                bool(db_name) and self._matches_allowlist(db_name, allowed_db_names),
                "Database name is explicitly allowlisted for performance staging.",
                "DB name must match FINACC_PERF_ALLOWED_DB_NAMES or --allow-db-name.",
                self._redact_identifier(db_name),
            ),
            self._gate(
                "DB_HOST_ALLOWLIST",
                bool(db_host) and self._matches_allowlist(db_host, allowed_db_hosts),
                "Database host is explicitly allowlisted for performance staging.",
                "DB host must match FINACC_PERF_ALLOWED_DB_HOSTS or --allow-db-host.",
                self._redact_identifier(db_host),
            ),
            self._gate(
                "DB_PRODUCTION_NAME_GUARD",
                not self._looks_production_identifier(db_name),
                "Database name does not look production-like.",
                "DB name must not contain prod/production/live.",
                self._redact_identifier(db_name),
            ),
            self._gate(
                "DB_PRODUCTION_HOST_GUARD",
                not self._looks_production_identifier(db_host),
                "Database host does not look production-like.",
                "DB host must not contain prod/production/live.",
                self._redact_identifier(db_host),
            ),
            self._gate(
                "DB_VENDOR_POSTGRESQL",
                connection.vendor == "postgresql",
                "Database vendor is PostgreSQL.",
                "Performance certification uses PostgreSQL.",
                connection.vendor,
            ),
            self._gate(
                "GST_WHITEBOOKS_SANDBOX",
                bool(getattr(settings, "WHITEBOOKS_SANDBOX_MODE", False))
                and "sandbox" in whitebooks_url.lower(),
                "Whitebooks GST is sandbox-routed.",
                "WHITEBOOKS_SANDBOX_MODE=True and sandbox base URL required.",
                f"sandbox_mode={getattr(settings, 'WHITEBOOKS_SANDBOX_MODE', None)}, host={self._host_only(whitebooks_url)}",
            ),
            self._gate(
                "GST_LIVE_FLAGS_DISABLED",
                not any(
                    bool(getattr(settings, name, False))
                    for name in (
                        "WHITEBOOKS_ENABLE_GSTR1_SAVE_LIVE",
                        "WHITEBOOKS_ENABLE_GSTR1_FILE_LIVE",
                        "WHITEBOOKS_ENABLE_GSTR3B_SAVE_LIVE",
                        "WHITEBOOKS_ENABLE_GSTR3B_OFFSET_LIVE",
                        "WHITEBOOKS_ENABLE_GSTR3B_FILE_LIVE",
                    )
                ),
                "All Whitebooks live GSTR mutation flags are disabled.",
                "All live save/file/offset flags must be False.",
                self._live_gst_flag_summary(),
            ),
            self._gate(
                "MASTERGST_SANDBOX_OR_DISABLED",
                mastergst_env.upper() in {"", "SANDBOX", "TEST", "DISABLED"},
                "MasterGST environment is sandbox/test/disabled.",
                "MASTERGST_ENV must not be production/live for staging performance tests.",
                mastergst_env or "<empty>",
            ),
            self._gate(
                "EMAIL_SAFE_SINK",
                self._email_backend_is_safe(email_backend),
                "Email backend is a non-delivery safe sink.",
                "Use locmem, console, dummy, or filebased email backend in staging load windows.",
                email_backend or "<empty>",
            ),
            self._gate(
                "CACHE_MULTI_WORKER_READY",
                "redis" in cache_backend.lower(),
                "Redis cache backend is configured for multi-worker staging.",
                "Redis cache is required for representative multi-worker cache behavior.",
                f"backend={cache_backend}, location={self._redact_url(cache_location)}",
            ),
            self._gate(
                "STORAGE_SAFE_TARGET",
                storage_backend == "local" or self._s3_bucket_looks_staging(),
                "Storage target is local or staging-named S3.",
                "S3 buckets for performance staging must be staging/test/perf named.",
                self._storage_observed(storage_backend),
            ),
            self._gate(
                "WRITE_TESTS_EXPLICITLY_GATED",
                self._env_false("FINACC_ENABLE_WRITE_TESTS") and self._env_false("FINACC_ENABLE_LIFECYCLE_TESTS"),
                "Locust write/lifecycle tests are disabled by default.",
                "FINACC_ENABLE_WRITE_TESTS and FINACC_ENABLE_LIFECYCLE_TESTS must be unset/false before read-only gates.",
                (
                    f"FINACC_ENABLE_WRITE_TESTS={os.environ.get('FINACC_ENABLE_WRITE_TESTS', '<unset>')}, "
                    f"FINACC_ENABLE_LIFECYCLE_TESTS={os.environ.get('FINACC_ENABLE_LIFECYCLE_TESTS', '<unset>')}"
                ),
            ),
        ]
        return gates

    @staticmethod
    def _gate(key: str, passed: bool, pass_message: str, expected: str, observed: str) -> StagingGate:
        return StagingGate(
            key=key,
            status="verified" if passed else "blocked",
            message=pass_message if passed else expected,
            expected=expected,
            observed=observed,
        )

    @staticmethod
    def _csv_env(name: str) -> list[str]:
        return [part.strip() for part in os.environ.get(name, "").split(",") if part.strip()]

    @staticmethod
    def _matches_allowlist(value: str, allowed: list[str]) -> bool:
        normalized = str(value or "").strip().lower()
        return bool(normalized) and normalized in {item.strip().lower() for item in allowed if item.strip()}

    @staticmethod
    def _looks_production_identifier(value: str) -> bool:
        lowered = str(value or "").strip().lower()
        return any(token in lowered for token in ("prod", "production", "live"))

    @staticmethod
    def _redact_identifier(value: str) -> str:
        raw = str(value or "")
        if not raw:
            return "<empty>"
        if len(raw) <= 6:
            return f"length={len(raw)}"
        return f"{raw[:3]}...{raw[-3:]} length={len(raw)}"

    @staticmethod
    def _host_only(url: str) -> str:
        if not url:
            return "<empty>"
        parsed = urlparse(url if "://" in url else f"//{url}")
        return parsed.netloc or parsed.path

    @staticmethod
    def _redact_url(value: str) -> str:
        if not value:
            return "<empty>"
        parsed = urlparse(value)
        if parsed.scheme and parsed.hostname:
            return f"{parsed.scheme}://{parsed.hostname}{':' + str(parsed.port) if parsed.port else ''}/..."
        return Command._redact_identifier(value)

    @staticmethod
    def _email_backend_is_safe(backend: str) -> bool:
        lowered = str(backend or "").lower()
        return any(token in lowered for token in ("locmem", "console", "dummy", "filebased"))

    @staticmethod
    def _env_false(name: str) -> bool:
        return str(os.environ.get(name, "")).strip().lower() in {"", "0", "false", "no", "off"}

    @staticmethod
    def _live_gst_flag_summary() -> str:
        names = (
            "WHITEBOOKS_ENABLE_GSTR1_SAVE_LIVE",
            "WHITEBOOKS_ENABLE_GSTR1_FILE_LIVE",
            "WHITEBOOKS_ENABLE_GSTR3B_SAVE_LIVE",
            "WHITEBOOKS_ENABLE_GSTR3B_OFFSET_LIVE",
            "WHITEBOOKS_ENABLE_GSTR3B_FILE_LIVE",
        )
        return ", ".join(f"{name}={bool(getattr(settings, name, False))}" for name in names)

    @staticmethod
    def _s3_bucket_looks_staging() -> bool:
        bucket = str(getattr(settings, "AWS_STORAGE_BUCKET_NAME", "") or "").lower()
        return bool(bucket) and any(token in bucket for token in ("staging", "stage", "perf", "test"))

    @staticmethod
    def _storage_observed(storage_backend: str) -> str:
        if storage_backend == "s3":
            return f"backend=s3 bucket={Command._redact_identifier(getattr(settings, 'AWS_STORAGE_BUCKET_NAME', ''))}"
        return f"backend={storage_backend or '<empty>'}"
