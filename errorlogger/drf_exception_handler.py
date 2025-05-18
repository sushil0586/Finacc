# errorlogger/drf_exception_handler.py

import traceback
from rest_framework.views import exception_handler
from .models import ErrorLog
from django.utils.timezone import now

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
        import logging
        logging.getLogger('error').exception("Failed to log DRF exception")

    return response
