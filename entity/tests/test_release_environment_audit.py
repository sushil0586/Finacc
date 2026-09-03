from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class ReleaseEnvironmentAuditCommandTests(SimpleTestCase):
    def _call_json(self, *args):
        out = StringIO()
        call_command("audit_release_environment", *args, json=True, stdout=out)
        return json.loads(out.getvalue())

    @override_settings(
        DEBUG=False,
        SECRET_KEY="release-secret-key-with-enough-length-and-entropy-12345",
        ALLOWED_HOSTS=["accerio.in", "www.accerio.in"],
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        AUTH_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=31536000,
        CORS_ORIGIN_ALLOW_ALL=False,
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.com",
        EMAIL_HOST_USER="noreply@example.com",
        EMAIL_HOST_PASSWORD="app-password",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_audit_passes_for_hardened_production_settings(self):
        payload = self._call_json("--require-email")

        self.assertTrue(payload["ready"])
        self.assertEqual(payload["fail_count"], 0)
        self.assertEqual(payload["warn_count"], 0)
        statuses = {row["key"]: row["status"] for row in payload["checks"]}
        self.assertEqual(statuses["DEBUG"], "pass")
        self.assertEqual(statuses["SMTP_INVITE_DELIVERY"], "pass")

    @override_settings(
        DEBUG=True,
        SECRET_KEY="django-insecure-short",
        ALLOWED_HOSTS=["*"],
        SECURE_SSL_REDIRECT=False,
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
        AUTH_COOKIE_SECURE=False,
        SECURE_HSTS_SECONDS=0,
        CORS_ORIGIN_ALLOW_ALL=True,
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_HOST="",
        EMAIL_HOST_USER="",
        EMAIL_HOST_PASSWORD="",
        DEFAULT_FROM_EMAIL="",
    )
    def test_audit_fails_for_dev_like_settings(self):
        payload = self._call_json("--require-email")

        self.assertFalse(payload["ready"])
        failing_keys = {row["key"] for row in payload["checks"] if row["status"] == "fail"}
        self.assertIn("DEBUG", failing_keys)
        self.assertIn("SECRET_KEY", failing_keys)
        self.assertIn("ALLOWED_HOSTS", failing_keys)
        self.assertIn("SECURE_SSL_REDIRECT", failing_keys)
        self.assertIn("SESSION_COOKIE_SECURE", failing_keys)
        self.assertIn("CSRF_COOKIE_SECURE", failing_keys)
        self.assertIn("AUTH_COOKIE_SECURE", failing_keys)
        self.assertIn("SECURE_HSTS_SECONDS", failing_keys)
        self.assertIn("CORS_ORIGIN_ALLOW_ALL", failing_keys)
        self.assertIn("SMTP_INVITE_DELIVERY", failing_keys)

    @override_settings(
        DEBUG=True,
        SECRET_KEY="django-insecure-short",
        ALLOWED_HOSTS=["*"],
        SECURE_SSL_REDIRECT=False,
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
        AUTH_COOKIE_SECURE=False,
        SECURE_HSTS_SECONDS=0,
        CORS_ORIGIN_ALLOW_ALL=True,
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_HOST="",
        EMAIL_HOST_USER="",
        EMAIL_HOST_PASSWORD="",
        DEFAULT_FROM_EMAIL="",
    )
    def test_strict_mode_exits_nonzero_when_blockers_exist(self):
        with self.assertRaises(CommandError):
            call_command("audit_release_environment", strict=True, stdout=StringIO(), stderr=StringIO())

    @override_settings(
        DEBUG=False,
        SECRET_KEY="release-secret-key-with-enough-length-and-entropy-12345",
        ALLOWED_HOSTS=["accerio.in"],
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        AUTH_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=31536000,
        CORS_ORIGIN_ALLOW_ALL=False,
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_HOST="",
        EMAIL_HOST_USER="",
        EMAIL_HOST_PASSWORD="",
        DEFAULT_FROM_EMAIL="",
    )
    def test_email_gap_is_warning_unless_required(self):
        payload = self._call_json()

        self.assertTrue(payload["ready"])
        self.assertEqual(payload["fail_count"], 0)
        self.assertEqual(payload["warn_count"], 1)
        smtp = next(row for row in payload["checks"] if row["key"] == "SMTP_INVITE_DELIVERY")
        self.assertEqual(smtp["status"], "warn")

    @override_settings(
        DEBUG=False,
        SECRET_KEY="release-secret-key-with-enough-length-and-entropy-12345",
        ALLOWED_HOSTS=["accerio.in"],
        SECURE_SSL_REDIRECT=False,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        AUTH_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=0,
        CORS_ORIGIN_ALLOW_ALL=False,
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.com",
        EMAIL_HOST_USER="noreply@example.com",
        EMAIL_HOST_PASSWORD="app-password",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_explicit_edge_controls_can_satisfy_redirect_and_hsts(self):
        payload = self._call_json("--require-email", "--edge-https-redirect", "--edge-hsts")

        self.assertTrue(payload["ready"])
        self.assertEqual(payload["fail_count"], 0)
        statuses = {row["key"]: row["status"] for row in payload["checks"]}
        self.assertEqual(statuses["SECURE_SSL_REDIRECT"], "pass")
        self.assertEqual(statuses["SECURE_HSTS_SECONDS"], "pass")
