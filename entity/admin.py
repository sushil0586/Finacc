from django.contrib import admin,messages
from django import forms
from django.contrib.admin.helpers import ActionForm  # <-- correct base
from entity.models import (
    UnitType, Entity, EntityDetail,Constitution,
    EntityFinancialYear, SubEntity, RolePrivilege, Role, UserRole,
    GstAccountDetail, MasterGstDetail,BankDetail,GstRegistrationType,OwnerShipTypes,EntityConstitution,EntityOwnership
)
from import_export.admin import ImportExportMixin


# Admin classes
class UnitTypeAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['UnitName', 'UnitDesc']
    search_fields = ['UnitName', 'UnitDesc']
    list_per_page = 50

class GstRegitrationTypesAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['Name', 'Description']
    search_fields = ['Name', 'Description']
    list_per_page = 50

class OwnerShipTypesAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['Name', 'Description']
    search_fields = ['Name', 'Description']
    list_per_page = 50


class SeedSeqActionForm(ActionForm):  # <-- subclass ActionForm, not forms.Form
    finyear   = forms.ModelChoiceField(
        queryset=EntityFinancialYear.objects.all(),
        required=False, label="Financial Year"
    )
    subentity = forms.ModelChoiceField(
        queryset=SubEntity.objects.all(),
        required=False, label="Subentity"
    )
    start     = forms.IntegerField(required=False, min_value=1, initial=1, label="Start display #")
    intstart  = forms.IntegerField(required=False, min_value=0, initial=1, label="Start integer #")
    reset     = forms.ChoiceField(
        choices=[("", "Default"), ("yearly", "Yearly"), ("monthly", "Monthly"), ("none", "No reset")],
        required=False, label="Reset policy"
    )


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display  = ['entityname', 'entity_code', 'legalname', 'gstno', 'panno', 'organization_status', 'business_type']
    search_fields = ['entityname', 'entity_code', 'legalname', 'gstno', 'panno', 'email_primary', 'phoneoffice']
    ordering      = ['entityname']
    list_filter   = ['organization_status', 'business_type', 'gst_registration_status', 'isactive']
    list_per_page = 50

    actions     = ['action_seed_sequences_quick', 'action_seed_sequences']
    action_form = SeedSeqActionForm

    # @admin.action(description="Seed numbering sequences (quick)")
    # def action_seed_sequences_quick(self, request, queryset):
    #     total_created = total_skipped = 0
    #     for ent in queryset:
    #         fin = entityfinancialyear.objects.filter(entity=ent).order_by('-id').first()
    #         if not fin:
    #             messages.error(request, f"{ent} → No financial year found.")
    #             continue
    #         created, skipped, msg = seed_sequences_for_entity(
    #             entity=ent, finyear=fin, subentity=None,
    #             start=1, intstart=1, override_reset=None
    #         )
    #         total_created += created
    #         total_skipped += skipped
    #         messages.success(request, f"{ent}: {msg} (created={created}, skipped={skipped})")
    #     messages.info(request, f"Done. Total created={total_created}, skipped={total_skipped}.")

    # @admin.action(description="Seed numbering sequences (choose FY/Subentity/reset above)")
    # def action_seed_sequences(self, request, queryset):
    #     finyear_id   = request.POST.get('finyear') or None
    #     subentity_id = request.POST.get('subentity') or None
    #     start        = int(request.POST.get('start') or 1)
    #     intstart     = int(request.POST.get('intstart') or 1)
    #     reset        = request.POST.get('reset') or None  # "", "yearly", "monthly", "none"

    #     total_created = total_skipped = 0
    #     for ent in queryset:
    #         if finyear_id:
    #             try:
    #                 fin = entityfinancialyear.objects.get(id=finyear_id, entity=ent)
    #             except entityfinancialyear.DoesNotExist:
    #                 messages.error(request, f"{ent} → FY id={finyear_id} not found for this entity.")
    #                 continue
    #         else:
    #             fin = entityfinancialyear.objects.filter(entity=ent).order_by('-id').first()
    #             if not fin:
    #                 messages.error(request, f"{ent} → No financial year found.")
    #                 continue

    #         se = None
    #         if subentity_id:
    #             try:
    #                 se = subentity.objects.get(id=subentity_id)
    #             except subentity.DoesNotExist:
    #                 messages.error(request, f"{ent} → Subentity id={subentity_id} not found.")
    #                 continue

    #         override = reset if reset in ('yearly', 'monthly', 'none') else None

    #         created, skipped, msg = seed_sequences_for_entity(
    #             entity=ent, finyear=fin, subentity=se,
    #             start=start, intstart=intstart, override_reset=override
    #         )
    #         total_created += created
    #         total_skipped += skipped
    #         messages.success(request, f"{ent}: {msg} (created={created}, skipped={skipped})")

    #     messages.info(request, f"Done. Total created={total_created}, skipped={total_skipped}.")

class SubEntityAdmin(admin.ModelAdmin):
    list_display = ['subentityname', 'subentity_code', 'entity', 'branch_type', 'gstno', 'is_head_office']
    search_fields = ['subentityname', 'subentity_code', 'address', 'gstno']
    list_filter = ['branch_type', 'is_head_office', 'can_sell', 'can_purchase', 'can_stock', 'isactive']
    list_per_page = 50


class MenuAdmin(admin.ModelAdmin):
    list_display = ['role', 'submenu', 'entity']
    list_filter = [
        ('entity', admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = ['role', 'submenu']
    list_per_page = 50


class RoleAdmin(admin.ModelAdmin):
    list_display = ['rolename', 'roledesc', 'rolelevel', 'entity']
    list_filter = [
        ('entity', admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = ['rolename', 'roledesc']
    list_per_page = 50


class UserRoleAdmin(admin.ModelAdmin):
    list_display = ['entity', 'role', 'user']
    list_filter = [
        ('entity', admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = ['role__rolename', 'user__username']
    list_per_page = 50


class GstAccountAdmin(admin.ModelAdmin):
    list_display = ['gstin', 'tradeName', 'legalName']
    search_fields = ['gstin', 'tradeName', 'legalName']
    list_per_page = 50


# Register models with admin site
admin.site.register(UnitType, UnitTypeAdmin)
admin.site.register(OwnerShipTypes, OwnerShipTypesAdmin)

admin.site.register(EntityDetail)
@admin.register(EntityFinancialYear)
class EntityFinancialYearAdmin(admin.ModelAdmin):
    list_display = ['entity', 'desc', 'year_code', 'period_status', 'is_year_closed', 'isactive']
    search_fields = ['entity__entityname', 'desc', 'year_code', 'assessment_year_label']
    list_filter = ['period_status', 'is_year_closed', 'is_audit_closed', 'isactive']
    list_per_page = 50

admin.site.register(EntityOwnership)
admin.site.register(Constitution)
admin.site.register(SubEntity,SubEntityAdmin)
admin.site.register(RolePrivilege, MenuAdmin)
admin.site.register(Role, RoleAdmin)
admin.site.register(UserRole, UserRoleAdmin)
admin.site.register(MasterGstDetail)
admin.site.register(BankDetail)
admin.site.register(GstRegistrationType)
