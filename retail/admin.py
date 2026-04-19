from django.contrib import admin

from .models import RetailConfig as RetailSetup, RetailTicket, RetailTicketLine


@admin.register(RetailSetup)
class RetailConfigAdmin(admin.ModelAdmin):
    list_display = ("entity", "subentity", "billing_mode", "posting_mode", "customer_mode")
    list_filter = ("billing_mode", "posting_mode", "customer_mode")
    search_fields = ("entity__entityname", "subentity__subentityname")


class RetailTicketLineInline(admin.TabularInline):
    model = RetailTicketLine
    extra = 0


@admin.register(RetailTicket)
class RetailTicketAdmin(admin.ModelAdmin):
    list_display = ("ticket_no", "bill_date", "status", "entity", "subentity", "location", "gross_value", "taxable_value")
    list_filter = ("status", "bill_date")
    search_fields = ("ticket_no", "customer_name", "customer_phone", "narration")
    inlines = [RetailTicketLineInline]

