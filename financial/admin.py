from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from .models import (
    FinancialSettings,
    Ledger,
    accounttype,
    accountHead,
    account,
    ShippingDetails,
    ContactDetails,
)
from .admin_resources import (
    AccountTypeResource,
    AccountHeadResource,
    AccountResource,
)


@admin.register(FinancialSettings)
class FinancialSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "entity",
        "opening_balance_edit_mode",
        "enforce_gst_uniqueness",
        "enforce_pan_uniqueness",
        "require_gst_for_registered_parties",
        "isactive",
    )
    list_filter = (
        "opening_balance_edit_mode",
        "enforce_gst_uniqueness",
        "enforce_pan_uniqueness",
        "require_gst_for_registered_parties",
        "isactive",
    )
    search_fields = ("entity__entityname",)
    list_select_related = ("entity", "createdby")


@admin.register(Ledger)
class LedgerAdmin(ImportExportModelAdmin):
    list_display = ("ledger_code", "name", "entity", "accounthead", "is_party", "is_system")
    list_filter = ("entity", "is_party", "is_system", "isactive")
    search_fields = ("name", "legal_name", "ledger_code")
    ordering = ("entity", "ledger_code")
    list_select_related = ("entity", "accounthead", "creditaccounthead", "accounttype")


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
    list_display = ("accountname", "accountcode", "compliance_gstno", "entity", "accounthead")
    list_filter = ("entity",)
    search_fields = ("accountname", "compliance_profile__gstno", "accountcode")
    ordering = ("entity", "accountcode")
    list_select_related = ("entity", "accounthead", "compliance_profile")

    @admin.display(description="GSTIN")
    def compliance_gstno(self, obj):
        profile = getattr(obj, "compliance_profile", None)
        return getattr(profile, "gstno", None)


# Optional: keep these normal (not import/export), because they depend on Account IDs heavily
@admin.register(ShippingDetails)
class ShippingDetailsAdmin(admin.ModelAdmin):
    list_display = ("account", "full_name", "gstno", "isprimary")
    search_fields = ("account__accountname", "full_name", "gstno")


@admin.register(ContactDetails)
class ContactDetailsAdmin(admin.ModelAdmin):
    list_display = ("account", "full_name", "designation")
    search_fields = ("account__accountname", "full_name", "designation")
