from django.utils.deprecation import MiddlewareMixin
from .models import AuditLog
import logging
import json

class AuditMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Only log after AuthenticationMiddleware has set request.user
        user = getattr(request, 'user', None)
        ip = request.META.get('REMOTE_ADDR')
        method = request.method
        path = request.path

        try:
            if method == 'GET':
                new_data = request.GET.dict()
            elif request.content_type == 'application/json':
                try:
                    new_data = json.loads(request.body.decode('utf-8'))
                except Exception:
                    new_data = {}
            else:
                new_data = request.POST.dict()
        except Exception:
            new_data = {}

        try:
            AuditLog.objects.create(
                user=user if user and user.is_authenticated else None,
                ip_address=ip,
                method=method,
                path=path,
                action=f'{method} on {path}',
                new_data=new_data
            )
        except Exception as e:
            logging.getLogger('audit').error(f"Audit logging failed: {str(e)}")

        return None
