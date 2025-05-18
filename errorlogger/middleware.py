# errorlogger/middleware.py

import traceback
from django.utils.deprecation import MiddlewareMixin
from .models import ErrorLog
from django.utils.timezone import now

class GlobalExceptionLoggingMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        user = request.user if request.user.is_authenticated else None

        ErrorLog.objects.create(
            timestamp=now(),
            user=user,
            path=request.path,
            method=request.method,
            message=str(exception),
            stacktrace=traceback.format_exc(),
            ip_address=request.META.get('REMOTE_ADDR'),
            request_data=request.body.decode('utf-8') if request.body else None
        )
