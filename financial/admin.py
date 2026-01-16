from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from .models import (
    accounttype,
    accountHead,
    account,
    ShippingDetails,
    ContactDetails,
    staticacounts,
    staticacountsmapping,
)
from .admin_resources import (
    AccountTypeResource,
    AccountHeadResource,
    AccountResource,
    StaticAccountsResource,
    StaticAccountsMappingResource,
)


@admin.register(accounttype)
class AccountTypeAdmin(ImportExportModelAdmin):
    resource_class = AccountTypeResource
    list_display = ("accounttypename", "accounttypecode", "balanceType", "entity")
    list_filter = ("entity", "balanceType")
    search_fields = ("accounttypename", "accounttypecode")
    ordering = ("accounttypecode",)


@admin.register(accountHead)
class AccountHeadAdmin(ImportExportModelAdmin):
    resource_class = AccountHeadResource
    list_display = ("name", "code", "drcreffect", "entity", "canbedeleted")
    list_filter = ("entity", "drcreffect", "canbedeleted")
    search_fields = ("name", "code")
    ordering = ("entity", "code")


@admin.register(account)
class AccountAdmin(ImportExportModelAdmin):
    resource_class = AccountResource
    list_display = ("accountname", "accountcode", "gstno", "entity", "accounthead")
    list_filter = ("entity",)
    search_fields = ("accountname", "gstno", "accountcode")
    ordering = ("entity", "accountcode")
    list_select_related = ("entity", "accounthead")


@admin.register(staticacounts)
class StaticAccountsAdmin(ImportExportModelAdmin):
    resource_class = StaticAccountsResource
    list_display = ("staticaccount", "code", "entity")
    list_filter = ("entity",)
    search_fields = ("staticaccount", "code")
    ordering = ("entity", "code")


@admin.register(staticacountsmapping)
class StaticAccountsMappingAdmin(ImportExportModelAdmin):
    resource_class = StaticAccountsMappingResource
    list_display = ("staticaccount", "account", "entity")
    list_filter = ("entity",)
    search_fields = ("staticaccount__code", "account__accountname", "account__accountcode")
    ordering = ("entity",)


# Optional: keep these normal (not import/export), because they depend on Account IDs heavily
@admin.register(ShippingDetails)
class ShippingDetailsAdmin(admin.ModelAdmin):
    list_display = ("account", "full_name", "gstno", "isprimary")
    search_fields = ("account__accountname", "full_name", "gstno")


@admin.register(ContactDetails)
class ContactDetailsAdmin(admin.ModelAdmin):
    list_display = ("account", "full_name", "designation")
    search_fields = ("account__accountname", "full_name", "designation")
