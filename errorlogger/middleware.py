# errorlogger/middleware.py

import json
import traceback
from django.utils.deprecation import MiddlewareMixin
from django.utils.timezone import now
from django.http import JsonResponse, RawPostDataException
from .models import ErrorLog

FORM_CTYPES = ("application/x-www-form-urlencoded", "multipart/form-data")
SENSITIVE_KEYS = {
    "authorization", "client_secret", "gst_password", "password", "refresh",
    "refresh_token", "secret", "token", "access_token",
}


def _redact_payload(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else _redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value

def _is_form_like(request):
    ctype = (request.META.get("CONTENT_TYPE") or "").split(";", 1)[0].strip().lower()
    return any(ctype.startswith(x) for x in FORM_CTYPES)

def _is_admin(request):
    # adjust if your admin path differs
    return request.path.startswith("/admin/")

class GlobalExceptionLoggingMiddleware(MiddlewareMixin):
    MAX_BODY_CHARS = 10000  # prevent megabyte logs

    def process_exception(self, request, exception):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            user = None

        # Build a safe payload
        payload = {}
        try:
            if _is_admin(request) or _is_form_like(request):
                # Admin/form posts: never touch raw body; use POST dict instead
                try:
                    payload["POST"] = _redact_payload(dict(request.POST))
                except Exception:
                    payload["POST"] = None
            else:
                # Non-form requests: try raw body (may still be consumed)
                try:
                    raw = request.body  # may raise RawPostDataException
                    decoded = raw.decode(request.encoding or "utf-8", errors="replace")[: self.MAX_BODY_CHARS]
                    try:
                        payload["body"] = _redact_payload(json.loads(decoded))
                    except (TypeError, ValueError):
                        payload["body"] = "[NON_JSON_BODY OMITTED]" if decoded else ""
                except RawPostDataException:
                    # Stream already read; fall back to POST dict
                    try:
                            payload["POST"] = _redact_payload(dict(request.POST))
                    except Exception:
                        payload["POST"] = None
        except Exception:
            payload = {"error": "failed to capture request payload safely"}

        # Serialize ASCII-only so Windows consoles/handlers don't choke on unicode
        request_data = json.dumps(payload, ensure_ascii=True)

        try:
            ErrorLog.objects.create(
                timestamp=now(),
                user=user,
                path=getattr(request, "get_full_path", lambda: request.path)(),
                method=request.method,
                message=str(exception),
                stacktrace=traceback.format_exc(),
                ip_address=request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR"),
                request_data=request_data,
            )
        except Exception:
            # Error reporting must never replace the original failure.
            pass

        if request.path.startswith("/api/"):
            return JsonResponse(
                {
                    "code": "server_error",
                    "detail": "The server could not complete this request. Please try again or contact support if the problem continues.",
                },
                status=500,
            )
        return None
