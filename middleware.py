import json
from .models import AuditLog

class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user if request.user.is_authenticated else None
        ip = request.META.get('REMOTE_ADDR')
        method = request.method
        path = request.path

        response = self.get_response(request)

        # Log only modifying requests
        if method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            try:
                AuditLog.objects.create(
                    user=user,
                    ip_address=ip,
                    method=method,
                    path=path,
                    action=f'{method} on {path}',
                    new_data=request.data
                )
            except Exception as e:
                import logging
                logging.getLogger('myapp').error(f"Audit logging failed: {str(e)}")

        return response
