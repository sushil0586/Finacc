# errorlogger/admin.py

from django.contrib import admin
from .models import ErrorLog

@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'path', 'method', 'message')
    search_fields = ('message', 'path', 'user__username')
    list_filter = ('method', 'timestamp')
