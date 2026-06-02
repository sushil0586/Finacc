# errorlogger/drf_exception_handler.py
import traceback
import logging

from rest_framework.views import exception_handler
from rest_framework import exceptions

from .models import ErrorLog
from django.utils.timezone import now


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
    user = request.user if request and request.user.is_authenticated else None

    try:
        ErrorLog.objects.create(
            timestamp=now(),
            user=user,
            path=request.path if request else '',
            method=request.method if request else '',
            message=str(exc),
            stacktrace=traceback.format_exc(),
        )
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

    return response
