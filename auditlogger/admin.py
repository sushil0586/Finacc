from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ( 'user', 'method')
    search_fields = ('user', 'method')
    list_filter = ('method', 'timestamp')
