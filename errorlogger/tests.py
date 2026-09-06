from types import SimpleNamespace
from unittest.mock import patch

from django.db import IntegrityError, OperationalError
from django.test import SimpleTestCase
from django.test import RequestFactory
from rest_framework import exceptions

from errorlogger.drf_exception_handler import custom_exception_handler
from errorlogger.middleware import GlobalExceptionLoggingMiddleware


class _ExplodingRequest:
    path = "/api/purchase/purchase-invoices/"
    method = "GET"

    @property
    def user(self):
        raise OperationalError("too many clients already")


class DrfExceptionHandlerTests(SimpleTestCase):
    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch("errorlogger.drf_exception_handler.exception_handler")
    def test_skips_request_user_resolution_when_db_is_unavailable(
        self,
        mocked_exception_handler,
        mocked_error_log_create,
    ):
        response = SimpleNamespace(data={"detail": "bad auth"})
        mocked_exception_handler.return_value = response

        result = custom_exception_handler(
            exceptions.AuthenticationFailed("Invalid credentials."),
            {"request": _ExplodingRequest()},
        )

        self.assertIs(result, response)
        mocked_error_log_create.assert_called_once()
        self.assertIsNone(mocked_error_log_create.call_args.kwargs["user"])
        self.assertEqual(result.data["code"], "invalid_credentials")

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch("errorlogger.drf_exception_handler.exception_handler", return_value=None)
    def test_returns_json_conflict_for_unhandled_integrity_error(
        self,
        mocked_exception_handler,
        mocked_error_log_create,
    ):
        result = custom_exception_handler(
            IntegrityError('duplicate key violates constraint "uq_example"'),
            {"request": SimpleNamespace(path="/api/example/", method="POST", user=None)},
        )

        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "data_conflict")
        self.assertNotIn("uq_example", result.data["detail"])

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch("errorlogger.drf_exception_handler.exception_handler", return_value=None)
    def test_returns_safe_json_for_unhandled_server_error(
        self,
        mocked_exception_handler,
        mocked_error_log_create,
    ):
        result = custom_exception_handler(
            RuntimeError("internal secret detail"),
            {"request": SimpleNamespace(path="/api/example/", method="GET", user=None)},
        )

        self.assertEqual(result.status_code, 500)
        self.assertEqual(result.data["code"], "server_error")
        self.assertNotIn("internal secret detail", result.data["detail"])


class GlobalExceptionLoggingMiddlewareTests(SimpleTestCase):
    @patch("errorlogger.middleware.ErrorLog.objects.create")
    def test_api_exception_returns_json_and_redacts_credentials(self, mocked_create):
        request = RequestFactory().post(
            "/api/entity/onboarding/register/",
            data='{"email":"user@example.com","password":"secret123","nested":{"client_secret":"provider-secret"}}',
            content_type="application/json",
        )
        middleware = GlobalExceptionLoggingMiddleware(lambda _request: None)

        response = middleware.process_exception(request, RuntimeError("failure"))

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["Content-Type"], "application/json")
        logged_payload = mocked_create.call_args.kwargs["request_data"]
        self.assertIn("[REDACTED]", logged_payload)
        self.assertNotIn("secret123", logged_payload)
        self.assertNotIn("provider-secret", logged_payload)
