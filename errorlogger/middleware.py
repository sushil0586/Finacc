# errorlogger/middleware.py

import json
import traceback
from django.utils.deprecation import MiddlewareMixin
from django.utils.timezone import now
from django.http import RawPostDataException
from .models import ErrorLog

FORM_CTYPES = ("application/x-www-form-urlencoded", "multipart/form-data")

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
                    payload["POST"] = dict(request.POST)
                except Exception:
                    payload["POST"] = None
            else:
                # Non-form requests: try raw body (may still be consumed)
                try:
                    raw = request.body  # may raise RawPostDataException
                    payload["body"] = raw.decode(request.encoding or "utf-8", errors="replace")[: self.MAX_BODY_CHARS]
                except RawPostDataException:
                    # Stream already read; fall back to POST dict
                    try:
                        payload["POST"] = dict(request.POST)
                    except Exception:
                        payload["POST"] = None
        except Exception:
            payload = {"error": "failed to capture request payload safely"}

        # Serialize ASCII-only so Windows consoles/handlers don't choke on unicode
        request_data = json.dumps(payload, ensure_ascii=True)

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
        # Return None to let Django continue its normal error handling
        return None
