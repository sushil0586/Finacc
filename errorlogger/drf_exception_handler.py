# errorlogger/drf_exception_handler.py
import traceback
import logging

from rest_framework.views import exception_handler
from rest_framework import exceptions
from rest_framework import status
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError
from django.test.testcases import DatabaseOperationForbidden

from .models import ErrorLog
from django.utils.timezone import now

User = get_user_model()


def _normalize_auth_error(exc, request):
    message = str(exc)
    normalized_email = ""
    if request:
        normalized_email = (request.data.get("email", "") or "").strip().lower() if hasattr(request, "data") else ""

    mappings = {
        "Invalid credentials.": {"code": "invalid_credentials", "message": message},
        "Too many login attempts. Try again later.": {"code": "login_rate_limited", "message": message},
        "User account is inactive.": {"code": "account_inactive", "message": message},
        "Account is temporarily locked. Try again later.": {"code": "account_locked", "message": message},
        "User account is temporarily locked.": {"code": "account_locked", "message": message},
        "Email verification is required before login.": {
            "code": "email_not_verified",
            "message": message,
            "next_action": "verify_email",
            "email": normalized_email,
        },
        "Refresh token has expired.": {"code": "refresh_expired", "message": message},
        "Token has expired.": {"code": "session_expired", "message": message},
        "Session has expired.": {"code": "session_expired", "message": message},
        "Too many OTP requests. Please try again later.": {"code": "otp_rate_limited", "message": message},
        "Token not valid.": {"code": "invalid_session", "message": message},
        "Token not valid": {"code": "invalid_session", "message": message},
        "Invalid refresh token.": {"code": "invalid_session", "message": message},
        "Session has been revoked.": {"code": "invalid_session", "message": message},
        "Session not found.": {"code": "invalid_session", "message": message},
        "Session not valid for user.": {"code": "invalid_session", "message": message},
        "Token version invalid.": {"code": "invalid_session", "message": message},
        "Token version mismatch. Please login again.": {"code": "invalid_session", "message": message},
        "Token does not contain a session.": {"code": "invalid_session", "message": message},
    }
    return mappings.get(message)

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    request = context.get('request')
    raw_user = None
    if request is not None:
        try:
            maybe_user = getattr(request, "user", None)
            raw_user = maybe_user
        except OperationalError:
            raw_user = None
    user = raw_user if isinstance(raw_user, User) and getattr(raw_user, "is_authenticated", False) else None

    try:
        ErrorLog.objects.create(
            timestamp=now(),
            user=user,
            path=request.path if request else '',
            method=request.method if request else '',
            message=str(exc),
            stacktrace=traceback.format_exc(),
        )
    except DatabaseOperationForbidden:
        # SimpleTestCase-based API tests intentionally block DB access.
        # Swallow logger writes there so validation-path tests stay quiet.
        pass
    except Exception as log_error:
        logging.getLogger('error').exception("Failed to log DRF exception")

    if response is not None and isinstance(exc, (exceptions.AuthenticationFailed, exceptions.NotAuthenticated, exceptions.Throttled)):
        normalized_error = _normalize_auth_error(exc, request)
        if normalized_error:
            response.data = {
                **({"detail": response.data.get("detail")} if isinstance(response.data, dict) and response.data.get("detail") else {}),
                **normalized_error,
                **({"wait": response.data.get("wait")} if isinstance(response.data, dict) and response.data.get("wait") is not None else {}),
            }

    if response is None:
        if isinstance(exc, IntegrityError):
            return Response(
                {
                    "code": "data_conflict",
                    "detail": "This change conflicts with an existing record. Review unique fields and try again.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {
                "code": "server_error",
                "detail": "The server could not complete this request. Please try again or contact support if the problem continues.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response
