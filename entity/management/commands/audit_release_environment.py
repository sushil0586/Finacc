from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


@dataclass(frozen=True)
class ReleaseEnvCheck:
    key: str
    status: str
    message: str
    expected: str
    observed: str


class Command(BaseCommand):
    help = "Audit deployment-critical settings before production release."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON output.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero when any release-critical check fails.",
        )
        parser.add_argument(
            "--require-email",
            action="store_true",
            help="Treat SMTP/invite configuration gaps as failures instead of warnings.",
        )
        parser.add_argument(
            "--edge-https-redirect",
            action="store_true",
            help="Accept HTTPS redirect as enforced by nginx/load balancer instead of Django SECURE_SSL_REDIRECT.",
        )
        parser.add_argument(
            "--edge-hsts",
            action="store_true",
            help="Accept HSTS as enforced by nginx/load balancer instead of Django SECURE_HSTS_SECONDS.",
        )

    def handle(self, *args, **options):
        checks = self._build_checks(
            require_email=options["require_email"],
            edge_https_redirect=options["edge_https_redirect"],
            edge_hsts=options["edge_hsts"],
        )
        fail_count = sum(1 for check in checks if check.status == "fail")
        warn_count = sum(1 for check in checks if check.status == "warn")
        payload = {
            "ready": fail_count == 0,
            "fail_count": fail_count,
            "warn_count": warn_count,
            "pass_count": sum(1 for check in checks if check.status == "pass"),
            "checks": [asdict(check) for check in checks],
        }

        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
        else:
            for check in checks:
                style = self.style.SUCCESS if check.status == "pass" else self.style.WARNING
                if check.status == "fail":
                    style = self.style.ERROR
                self.stdout.write(style(f"{check.status.upper()} {check.key}: {check.message}"))
            self.stdout.write(
                f"release_environment_ready={payload['ready']} "
                f"pass={payload['pass_count']} warn={warn_count} fail={fail_count}"
            )

        if options["strict"] and fail_count:
            raise CommandError(f"Release environment audit failed with {fail_count} blocking issue(s).")

    def _build_checks(
        self,
        *,
        require_email: bool,
        edge_https_redirect: bool,
        edge_hsts: bool,
    ) -> list[ReleaseEnvCheck]:
        checks = [
            self._check(
                "DEBUG",
                not bool(settings.DEBUG),
                "DEBUG is disabled.",
                "DEBUG must be False.",
                str(settings.DEBUG),
            ),
            self._check(
                "SECRET_KEY",
                self._secret_key_looks_safe(getattr(settings, "SECRET_KEY", "")),
                "SECRET_KEY shape looks production-safe.",
                "At least 50 chars, at least 5 unique chars, and not django-insecure/test placeholder.",
                self._mask_secret_shape(getattr(settings, "SECRET_KEY", "")),
            ),
            self._check(
                "ALLOWED_HOSTS",
                self._hosts_are_restricted(getattr(settings, "ALLOWED_HOSTS", [])),
                "ALLOWED_HOSTS is restricted.",
                "Must be non-empty and must not include wildcard '*'.",
                ",".join(getattr(settings, "ALLOWED_HOSTS", []) or []),
            ),
            self._check(
                "SECURE_SSL_REDIRECT",
                bool(getattr(settings, "SECURE_SSL_REDIRECT", False)) or edge_https_redirect,
                "HTTPS redirect is enabled." if not edge_https_redirect else "HTTPS redirect is explicitly accepted at the edge.",
                "SECURE_SSL_REDIRECT must be True, or equivalent edge redirect must be explicitly accepted.",
                f"django={getattr(settings, 'SECURE_SSL_REDIRECT', None)}, edge_https_redirect={edge_https_redirect}",
            ),
            self._check(
                "SESSION_COOKIE_SECURE",
                bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
                "Session cookies are secure-only.",
                "SESSION_COOKIE_SECURE must be True.",
                str(getattr(settings, "SESSION_COOKIE_SECURE", None)),
            ),
            self._check(
                "CSRF_COOKIE_SECURE",
                bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
                "CSRF cookies are secure-only.",
                "CSRF_COOKIE_SECURE must be True.",
                str(getattr(settings, "CSRF_COOKIE_SECURE", None)),
            ),
            self._check(
                "AUTH_COOKIE_SECURE",
                bool(getattr(settings, "AUTH_COOKIE_SECURE", False)),
                "Auth cookies are secure-only.",
                "AUTH_COOKIE_SECURE must be True.",
                str(getattr(settings, "AUTH_COOKIE_SECURE", None)),
            ),
            self._check(
                "SECURE_HSTS_SECONDS",
                int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0) > 0 or edge_hsts,
                "HSTS is enabled." if not edge_hsts else "HSTS is explicitly accepted at the edge.",
                "SECURE_HSTS_SECONDS must be greater than 0 after HTTPS is confirmed.",
                f"django={getattr(settings, 'SECURE_HSTS_SECONDS', None)}, edge_hsts={edge_hsts}",
            ),
            self._check(
                "CORS_ORIGIN_ALLOW_ALL",
                not bool(getattr(settings, "CORS_ORIGIN_ALLOW_ALL", False)),
                "CORS wildcard is disabled.",
                "CORS_ORIGIN_ALLOW_ALL must be False when credentialed cookies are used.",
                str(getattr(settings, "CORS_ORIGIN_ALLOW_ALL", None)),
            ),
        ]

        email_ok = self._email_settings_are_usable()
        checks.append(
            ReleaseEnvCheck(
                key="SMTP_INVITE_DELIVERY",
                status="pass" if email_ok else ("fail" if require_email else "warn"),
                message=(
                    "SMTP settings are populated; still verify a real inbox delivery."
                    if email_ok
                    else "SMTP settings are incomplete; invite/OTP delivery must be proven before go-live."
                ),
                expected="EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, and DEFAULT_FROM_EMAIL populated.",
                observed=self._email_observed_summary(),
            )
        )
        return checks

    @staticmethod
    def _check(key: str, passed: bool, pass_message: str, expected: str, observed: str) -> ReleaseEnvCheck:
        return ReleaseEnvCheck(
            key=key,
            status="pass" if passed else "fail",
            message=pass_message if passed else expected,
            expected=expected,
            observed=observed,
        )

    @staticmethod
    def _secret_key_looks_safe(secret_key: str) -> bool:
        value = str(secret_key or "")
        lowered = value.lower()
        return (
            len(value) >= 50
            and len(set(value)) >= 5
            and not lowered.startswith("django-insecure-")
            and "your-secret-key" not in lowered
            and "test-secret" not in lowered
        )

    @staticmethod
    def _hosts_are_restricted(hosts) -> bool:
        normalized = [str(host).strip() for host in hosts or [] if str(host).strip()]
        return bool(normalized) and "*" not in normalized

    @staticmethod
    def _mask_secret_shape(secret_key: str) -> str:
        value = str(secret_key or "")
        return f"length={len(value)}, unique_chars={len(set(value))}"

    @staticmethod
    def _email_settings_are_usable() -> bool:
        backend = str(getattr(settings, "EMAIL_BACKEND", "") or "")
        non_delivery_backends = ("locmem", "console", "dummy", "filebased")
        if any(part in backend for part in non_delivery_backends):
            return False
        return all(
            str(getattr(settings, name, "") or "").strip()
            for name in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "DEFAULT_FROM_EMAIL")
        )

    @staticmethod
    def _email_observed_summary() -> str:
        backend = str(getattr(settings, "EMAIL_BACKEND", "") or "")
        return (
            f"backend={backend or '<empty>'}, "
            f"host_set={bool(getattr(settings, 'EMAIL_HOST', ''))}, "
            f"user_set={bool(getattr(settings, 'EMAIL_HOST_USER', ''))}, "
            f"password_set={bool(getattr(settings, 'EMAIL_HOST_PASSWORD', ''))}, "
            f"default_from_set={bool(getattr(settings, 'DEFAULT_FROM_EMAIL', ''))}"
        )
