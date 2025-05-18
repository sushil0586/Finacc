# errorlogger/utils.py

import traceback
from .models import ErrorLog

def log_exception_to_db(request, exception):
    user = request.user if request.user.is_authenticated else None
    ErrorLog.objects.create(
        user=user,
        path=request.path,
        method=request.method,
        message=str(exception),
        stacktrace=traceback.format_exc()
    )
