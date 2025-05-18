# errorlogger/models.py

from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class ErrorLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    path = models.CharField(max_length=500, null=True, blank=True)
    method = models.CharField(max_length=10, null=True, blank=True)
    message = models.TextField()
    stacktrace = models.TextField(null=True, blank=True)
    
    # Additional optional fields
    status_code = models.IntegerField(null=True, blank=True)
    request_data = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    module = models.CharField(max_length=100, null=True, blank=True)
    view_name = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return f"{self.timestamp} - {self.message[:50]}"

