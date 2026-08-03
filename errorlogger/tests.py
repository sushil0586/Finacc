from types import SimpleNamespace
from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase
from rest_framework import exceptions

from errorlogger.drf_exception_handler import custom_exception_handler


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
