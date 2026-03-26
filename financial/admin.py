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
    AccountBankDetails,
    AccountAddress,
    AccountComplianceProfile,
    AccountCommercialProfile,
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
    inlines = []

    @admin.display(description="GSTIN")
    def compliance_gstno(self, obj):
        profile = getattr(obj, "compliance_profile", None)
        return getattr(profile, "gstno", None)


class AccountComplianceProfileInline(admin.StackedInline):
    model = AccountComplianceProfile
    fk_name = "account"
    extra = 0
    max_num = 1
    show_change_link = True


class AccountCommercialProfileInline(admin.StackedInline):
    model = AccountCommercialProfile
    fk_name = "account"
    extra = 0
    max_num = 1
    show_change_link = True


class AccountAddressInline(admin.TabularInline):
    model = AccountAddress
    fk_name = "account"
    extra = 0
    show_change_link = True


class AccountBankDetailsInline(admin.TabularInline):
    model = AccountBankDetails
    fk_name = "account"
    extra = 0
    show_change_link = True


class ShippingDetailsInline(admin.TabularInline):
    model = ShippingDetails
    fk_name = "account"
    extra = 0
    show_change_link = True


class ContactDetailsInline(admin.TabularInline):
    model = ContactDetails
    fk_name = "account"
    extra = 0
    show_change_link = True


AccountAdmin.inlines = [
    AccountComplianceProfileInline,
    AccountCommercialProfileInline,
    AccountAddressInline,
    AccountBankDetailsInline,
    ShippingDetailsInline,
    ContactDetailsInline,
]


# Optional: keep these normal (not import/export), because they depend on Account IDs heavily
@admin.register(ShippingDetails)
class ShippingDetailsAdmin(admin.ModelAdmin):
    list_display = ("account", "full_name", "gstno", "isprimary")
    search_fields = ("account__accountname", "full_name", "gstno")


@admin.register(ContactDetails)
class ContactDetailsAdmin(admin.ModelAdmin):
    list_display = ("account", "full_name", "designation")
    search_fields = ("account__accountname", "full_name", "designation")


@admin.register(AccountBankDetails)
class AccountBankDetailsAdmin(admin.ModelAdmin):
    list_display = ("account", "bankname", "banKAcno", "ifsc", "isprimary", "isactive")
    list_filter = ("isprimary", "isactive", "entity")
    search_fields = ("account__accountname", "bankname", "banKAcno", "ifsc")
    list_select_related = ("account", "entity")


@admin.register(AccountAddress)
class AccountAddressAdmin(admin.ModelAdmin):
    list_display = ("account", "address_type", "line1", "pincode", "isprimary", "isactive")
    list_filter = ("address_type", "isprimary", "isactive", "entity")
    search_fields = ("account__accountname", "line1", "pincode")
    list_select_related = ("account", "entity", "country", "state", "district", "city")


@admin.register(AccountComplianceProfile)
class AccountComplianceProfileAdmin(admin.ModelAdmin):
    list_display = ("account", "gstno", "pan", "gstintype", "gstregtype", "is_sez", "isactive")
    list_filter = ("gstintype", "gstregtype", "is_sez", "isactive", "entity")
    search_fields = ("account__accountname", "gstno", "pan")
    list_select_related = ("account", "entity")


@admin.register(AccountCommercialProfile)
class AccountCommercialProfileAdmin(admin.ModelAdmin):
    list_display = ("account", "partytype", "currency", "creditdays", "creditlimit", "approved", "isactive")
    list_filter = ("partytype", "currency", "approved", "isactive", "entity")
    search_fields = ("account__accountname", "agent", "blockedreason")
    list_select_related = ("account", "entity")
