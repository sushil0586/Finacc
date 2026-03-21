from django.contrib import admin
from import_export.admin import ImportExportMixin

from entity.models import (
    BankDetail,
    Constitution,
    Entity,
    EntityAddress,
    EntityBankAccountV2,
    EntityComplianceProfile,
    EntityConstitutionV2,
    EntityContact,
    EntityFinancialYear,
    EntityGstRegistration,
    EntityOwnershipV2,
    EntityTaxProfile,
    GstRegistrationType,
    SubEntity,
    SubEntityAddress,
    SubEntityCapability,
    SubEntityContact,
    SubEntityGstRegistration,
    UserEntityContext,
    UnitType,
)


class UnitTypeAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ["UnitName", "UnitDesc"]
    search_fields = ["UnitName", "UnitDesc"]


class GstRegitrationTypesAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ["Name", "Description"]
    search_fields = ["Name", "Description"]


class EntityAddressInline(admin.TabularInline):
    model = EntityAddress
    extra = 0


class EntityContactInline(admin.TabularInline):
    model = EntityContact
    extra = 0


class EntityGstRegistrationInline(admin.TabularInline):
    model = EntityGstRegistration
    extra = 0


class EntityBankAccountV2Inline(admin.TabularInline):
    model = EntityBankAccountV2
    extra = 0


class EntityTaxProfileInline(admin.StackedInline):
    model = EntityTaxProfile
    extra = 0
    can_delete = False


class EntityComplianceProfileInline(admin.StackedInline):
    model = EntityComplianceProfile
    extra = 0
    can_delete = False


class EntityConstitutionV2Inline(admin.TabularInline):
    model = EntityConstitutionV2
    extra = 0


class EntityOwnershipV2Inline(admin.TabularInline):
    model = EntityOwnershipV2
    extra = 0


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "entityname",
        "entity_code",
        "legalname",
        "organization_status",
        "business_type",
        "isactive",
    ]
    search_fields = ["entityname", "entity_code", "legalname"]
    list_filter = ["organization_status", "business_type", "isactive"]
    inlines = [
        EntityTaxProfileInline,
        EntityComplianceProfileInline,
        EntityAddressInline,
        EntityContactInline,
        EntityGstRegistrationInline,
        EntityBankAccountV2Inline,
        EntityConstitutionV2Inline,
        EntityOwnershipV2Inline,
    ]


class SubEntityAddressInline(admin.TabularInline):
    model = SubEntityAddress
    extra = 0


class SubEntityContactInline(admin.TabularInline):
    model = SubEntityContact
    extra = 0


class SubEntityGstRegistrationInline(admin.TabularInline):
    model = SubEntityGstRegistration
    extra = 0


class SubEntityCapabilityInline(admin.StackedInline):
    model = SubEntityCapability
    extra = 0
    can_delete = False


@admin.register(SubEntity)
class SubEntityAdmin(admin.ModelAdmin):
    list_display = ["id", "subentityname", "subentity_code", "entity", "branch_type", "is_head_office", "isactive"]
    search_fields = ["subentityname", "subentity_code", "entity__entityname"]
    list_filter = ["branch_type", "is_head_office", "isactive"]
    inlines = [
        SubEntityCapabilityInline,
        SubEntityAddressInline,
        SubEntityContactInline,
        SubEntityGstRegistrationInline,
    ]


@admin.register(EntityFinancialYear)
class EntityFinancialYearAdmin(admin.ModelAdmin):
    list_display = ["id", "entity", "desc", "year_code", "period_status", "is_year_closed", "isactive"]
    search_fields = ["entity__entityname", "desc", "year_code", "assessment_year_label"]
    list_filter = ["period_status", "is_year_closed", "is_audit_closed", "isactive"]


admin.site.register(UnitType, UnitTypeAdmin)
admin.site.register(GstRegistrationType, GstRegitrationTypesAdmin)
admin.site.register(Constitution)
admin.site.register(BankDetail)
admin.site.register(UserEntityContext)
