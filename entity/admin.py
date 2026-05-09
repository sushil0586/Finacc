from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
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
    Godown,
    SubEntity,
    SubEntityAddress,
    SubEntityCapability,
    SubEntityContact,
    SubEntityGstRegistration,
    UserEntityContext,
)


class GstRegitrationTypesAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ["Name", "Description"]
    search_fields = ["Name", "Description"]


class EntityAddressInline(admin.TabularInline):
    model = EntityAddress
    extra = 0


class EntityContactInline(admin.TabularInline):
    model = EntityContact
    extra = 0


class EntityGstRegistrationInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        active_count = 0
        primary_count = 0
        active_primary_count = 0
        active_gstins = []
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            is_active = bool(form.cleaned_data.get("isactive"))
            is_primary = bool(form.cleaned_data.get("is_primary"))
            gstin = str(form.cleaned_data.get("gstin") or "").strip().upper()

            if is_active:
                active_count += 1
                if gstin:
                    active_gstins.append(gstin)
            if is_primary:
                primary_count += 1
            if is_active and is_primary:
                active_primary_count += 1

        if active_count > 1:
            raise ValidationError(
                "Only one active GST registration is allowed per entity. "
                "Uncheck Inactive on the old GST row before saving the new one."
            )

        if primary_count > 1:
            raise ValidationError(
                "Only one GST row should remain marked Primary. "
                "If you are keeping a new GSTIN, uncheck Primary on the old row first."
            )

        if active_count == 1 and active_primary_count == 0:
            kept = active_gstins[0] if active_gstins else "the active GST row"
            raise ValidationError(
                f"{kept} is the only active GST registration, so it must also be marked Primary. "
                "Uncheck Primary on the old row and mark the kept active row as Primary."
            )


class EntityGstRegistrationInline(admin.TabularInline):
    model = EntityGstRegistration
    formset = EntityGstRegistrationInlineFormSet
    extra = 0
    verbose_name = "Entity GST registration"
    verbose_name_plural = "Entity GST registration"
    fields = (
        "isactive",
        "is_primary",
        "gstin",
        "registration_type",
        "gst_status",
        "state",
        "nature_of_business",
        "gst_effective_from",
        "gst_cancelled_from",
    )

    def has_add_permission(self, request, obj=None):
        if not obj:
            return True
        return not obj.gst_registrations.filter(isactive=True).exists()


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


class GodownInline(admin.TabularInline):
    model = Godown
    extra = 0
    fk_name = "subentity"


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
        GodownInline,
    ]


@admin.register(EntityFinancialYear)
class EntityFinancialYearAdmin(admin.ModelAdmin):
    list_display = ["id", "entity", "desc", "year_code", "period_status", "is_year_closed", "isactive"]
    search_fields = ["entity__entityname", "desc", "year_code", "assessment_year_label"]
    list_filter = ["period_status", "is_year_closed", "is_audit_closed", "isactive"]


@admin.register(Godown)
class GodownAdmin(admin.ModelAdmin):
    list_display = ["id", "entity", "subentity", "name", "code", "city", "state", "is_default", "is_active"]
    search_fields = ["name", "code", "entity__entityname", "subentity__subentityname", "city", "state"]
    list_filter = ["is_active", "is_default", "entity", "subentity", "state"]
    autocomplete_fields = ["entity", "subentity"]
    list_select_related = ["entity", "subentity"]


admin.site.register(GstRegistrationType, GstRegitrationTypesAdmin)
admin.site.register(Constitution)
admin.site.register(BankDetail)
admin.site.register(UserEntityContext)
