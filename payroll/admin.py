from django.contrib import admin,messages
from simple_history.admin import SimpleHistoryAdmin
from django.forms.models import BaseInlineFormSet

from .models import (
     TaxRegime, InvestmentSection,
    CalculationType, BonusFrequency, CalculationValue, ComponentType,
    PayrollComponent, EntityPayrollComponentConfig, salarycomponent,
    employeenew, EmployeePayrollComponent, employeesalary,
    salarytrans, salarytransdetails, EmployeeInvestment,
    EmployeeInvestmentSummary, EmployeeLoan,EntityPayrollComponent,ComponentFamily,
    BusinessUnit, Department, Location, CostCenter,
    OptionSet, Option,
    Employee, EmploymentAssignment, EmployeeCompensation,
    EmployeeStatutoryIN, EmployeeBankAccount, EmployeeDocument,GradeBand, Designation,
)
from entity.models import Entity

from .models import (
    PayrollComponentGlobal,
    PayrollComponentCap,
    SlabGroup,
    Slab,
    CityCategory,
    ComponentTypeGlobal,
    CalcMethod,PayStructure, PayStructureComponent,
)


from .services import apply_structure_to_entity
from django.utils.dateparse import parse_date
from django.contrib.admin.helpers import ActionForm
from django.utils.dateparse import parse_date




# payroll/admin.py
#from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models


admin.site.register(TaxRegime)
admin.site.register(InvestmentSection)
admin.site.register(CalculationType)
admin.site.register(BonusFrequency)
admin.site.register(CalculationValue)
admin.site.register(ComponentType)
admin.site.register(PayrollComponent)
admin.site.register(EntityPayrollComponentConfig)
admin.site.register(salarycomponent)
admin.site.register(employeenew)
admin.site.register(EmployeePayrollComponent)
admin.site.register(employeesalary)
admin.site.register(salarytrans)
admin.site.register(salarytransdetails)
admin.site.register(EmployeeInvestment)
admin.site.register(EmployeeInvestmentSummary)
admin.site.register(EmployeeLoan)

# --- 1) Register Option with search_fields so it works with autocomplete_fields ---
@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    # Add your real fields here if available, e.g. ('name','code')
    search_fields = ('id',)           # safe default; passes system check
    list_display = ('id',)            # optional
    # If Option has a lot of rows, consider:
    # list_per_page = 25


@admin.register(BusinessUnit)
class BusinessUnitAdmin(admin.ModelAdmin):
    list_display = ("entity", "name")
    list_filter = ("entity",)
    search_fields = ("name",)
    autocomplete_fields = ("entity",)
    ordering = ("entity", "name")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("entity", "name")
    list_filter = ("entity",)
    search_fields = ("name",)
    autocomplete_fields = ("entity",)
    ordering = ("entity", "name")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("entity", "name", "city", "state", "country")
    list_filter = ("entity", "country", "state", "city")
    search_fields = ("name", "city", "state", "country")
    autocomplete_fields = ("entity",)
    ordering = ("entity", "name")


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ("entity", "code", "name")
    list_filter = ("entity",)
    search_fields = ("code", "name")
    autocomplete_fields = ("entity",)
    ordering = ("entity", "code")


class OptionInline(admin.TabularInline):
    model = Option
    extra = 3
    fields = ("code", "label", "sort_order", "is_active", "extra")
    show_change_link = True


@admin.register(OptionSet)
class OptionSetAdmin(admin.ModelAdmin):
    list_display = ("key", "entity", "created_at")
    list_filter = ("key", "entity")
    search_fields = ("key",)
    autocomplete_fields = ("entity",)
    inlines = [OptionInline]
    ordering = ("key", "entity")

class EntityScopedAdminMixin:
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # assume request.user.profile.entity
        return qs.filter(entity=request.user.profile.entity) | qs.filter(entity__isnull=True)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "entity" and not request.user.is_superuser:
            kwargs["queryset"] = Entity.objects.filter(pk=request.user.profile.entity_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)





class PayrollComponentGlobalAdminForm(forms.ModelForm):
    class Meta:
        model = PayrollComponentGlobal
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        # ensure code stays in sync with family.code for validation
        fam = cleaned.get("family") or self.instance.family
        if fam:
            self.instance.family = fam
            self.instance.code = fam.code.upper()
        # copy all cleaned values to instance so model.clean() sees them
        for k, v in cleaned.items():
            setattr(self.instance, k, v)
        self.instance.clean()  # run model-level validations (overlaps, method fields, bands, etc.)
        return cleaned

class PayStructureComponentAdminForm(forms.ModelForm):
    class Meta:
        model = PayStructureComponent
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        for k, v in cleaned.items():
            setattr(self.instance, k, v)
        self.instance.clean()  # validates against resolved global method
        return cleaned
    
class PayrollComponentGlobalInline(admin.StackedInline):
    model = PayrollComponentGlobal
    form = PayrollComponentGlobalAdminForm
    extra = 0
    fields = (
        ("effective_from", "effective_to"),
        ("type", "calc_method", "priority"),
        ("frequency", "rounding", "is_proratable"),
        ("proration_method", "payout_policy", "payout_months"),
        "percent_basis", ("basis_cap_amount", "basis_cap_periodicity"),
        "slab_group", ("slab_base", "slab_percent_basis"), "slab_scope_field",
        "formula_text", "default_params", "required_vars",
        ("policy_band_min_percent", "policy_band_max_percent"),
        ("taxability", "pf_include", "esi_include", "pt_include", "lwf_include"),
        ("payslip_group", "display_order", "show_on_payslip"),
        "name",
    )

    

class PayStructureComponentInline(admin.StackedInline):
    model = PayStructureComponent
    form = PayStructureComponentAdminForm
    extra = 0
    ordering = ("priority", "id")
    fields = (
        ("family", "pinned_global_component"),
        ("enabled", "required", "priority"),
        ("default_amount", "default_percent"),
        "param_overrides",
        "slab_scope_value",
        ("allow_emp_override", "emp_min_percent", "emp_max_percent"),
        ("show_on_payslip", "display_order"),
        "notes",
    )


@admin.register(ComponentFamily)
class ComponentFamilyAdmin(admin.ModelAdmin):
    search_fields = ("code", "display_name")   # required for autocomplete to work
    list_display = ("code", "display_name", "version_count")
    ordering = ("code",)
    inlines = (PayrollComponentGlobalInline,)

    def version_count(self, obj):
        return obj.versions.count()



# ---------- Common widgets / overrides ----------

class JSONTextarea(forms.Textarea):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("attrs", {}).update({"rows": 6, "style": "font-family: ui-monospace, monospace;"})
        super().__init__(*args, **kwargs)

# Apply a decent textarea to JSONFields in admin
JSONFIELD_OVERRIDES = {models.JSONField: {"widget": JSONTextarea}}

# ---------- List filters ----------

class ActiveNowListFilter(admin.SimpleListFilter):
    title = "Active (today)"
    parameter_name = "active_now"

    def lookups(self, request, model_admin):
        return (("yes", "Yes"), ("no", "No"))

    def queryset(self, request, queryset):
        today = date.today()
        val = self.value()
        if val == "yes":
            return queryset.filter(effective_from__lte=today).filter(
                models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=today)
            )
        if val == "no":
            return queryset.exclude(
                models.Q(effective_to__isnull=True, effective_from__lte=today) |
                models.Q(effective_to__gte=today, effective_from__lte=today)
            )
        return queryset

class CalcMethodListFilter(admin.SimpleListFilter):
    title = "Calc method"
    parameter_name = "calc_method"

    def lookups(self, request, model_admin):
        return CalcMethod.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(calc_method=self.value())
        return queryset

class ComponentTypeListFilter(admin.SimpleListFilter):
    title = "Type"
    parameter_name = "type"

    def lookups(self, request, model_admin):
        return ComponentTypeGlobal.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(type=self.value())
        return queryset

# ---------- Inlines ----------

class PayrollComponentCapInline(admin.TabularInline):
    model = PayrollComponentCap
    extra = 0
    fields = ("cap_type", "cap_basis", "cap_value", "periodicity", "conditions", "notes", "sort_order")
    formfield_overrides = {models.JSONField: {"widget": admin.widgets.AdminTextareaWidget(attrs={"rows": 3})}}
    ordering = ("sort_order", "id")

class SlabInline(admin.TabularInline):
    model = Slab
    extra = 0
    fields = (
        "state_scope", "scope_json", "from_amount", "to_amount",
        "rate_type", "value", "percent_of", "cycle", "months",
        "effective_from", "effective_to",
    )
    ordering = ("state_scope", "from_amount", "effective_from")

# ---------- Admin actions ----------

@admin.action(description="Close selected versions as of today")
def close_selected_today(modeladmin, request, queryset):
    today = date.today()
    updated = 0
    for obj in queryset:
        if obj.effective_to is None or obj.effective_to > today:
            obj.effective_to = today
            obj.full_clean()
            obj.save()
            updated += 1
    modeladmin.message_user(request, f"Closed {updated} record(s).")

@admin.action(description="Duplicate as new version starting tomorrow")
def duplicate_as_new_version(modeladmin, request, queryset):
    tomorrow = date.today() + timedelta(days=1)
    created = 0
    for obj in queryset:
        new_obj = deepcopy(obj)
        new_obj.pk = None
        # carry forward, open-ended; you can set a default end if desired
        new_obj.effective_from = tomorrow
        new_obj.effective_to = None
        try:
            new_obj.full_clean()
            new_obj.save()
            # also duplicate caps if component
            if isinstance(new_obj, PayrollComponentGlobal):
                for cap in obj.caps.all():
                    new_cap = deepcopy(cap)
                    new_cap.pk = None
                    new_cap.component = new_obj
                    new_cap.full_clean()
                    new_cap.save()
            created += 1
        except ValidationError as e:
            modeladmin.message_user(request, f"Skipped {obj}: {e}", level="error")
    modeladmin.message_user(request, f"Created {created} new version(s).")

# ---------- ModelAdmins ----------

# === Main admin for the versioned global component ===
@admin.register(PayrollComponentGlobal)
class PayrollComponentGlobalAdmin(EntityScopedAdminMixin,SimpleHistoryAdmin):
    form = PayrollComponentGlobalAdminForm

    # remove the first list_display (you had it twice); keep only this one:
    list_display = (
        "family", "code", "name", "entity", "type", "calc_method",
        "effective_from", "effective_to", "priority", "frequency", "rounding",
    )
    list_filter  = ("entity", "family", "type", "calc_method", "frequency", "rounding")
    search_fields = ("code", "name", "family__code", "entity__entityname")  # adjust field to your Entity model
    autocomplete_fields = ("family", "slab_group", "entity")
    inlines = [PayrollComponentCapInline]

    fieldsets = (
        ("Identity & Versioning", {
            "fields": (
                ("family", "entity"),          # <-- add entity here
                ("code", "name"),
                ("type", "calc_method", "priority"),
                ("effective_from", "effective_to"),
            )
        }),
        ("Behavior", {
            "fields": (("frequency", "rounding", "is_proratable"),)
        }),
        ("Flags & Tax", {
            "fields": (("taxability", "pf_include", "esi_include", "pt_include", "lwf_include"),)
        }),
        ("Percent Settings (method = percent)", {
            "classes": ("collapse",),
            "fields": (("percent_basis", "basis_cap_amount", "basis_cap_periodicity"),)
        }),
        ("Slab Settings (method = slab)", {
            "classes": ("collapse",),
            "fields": (("slab_group", "slab_base", "slab_percent_basis", "slab_scope_field"),)
        }),
        ("Formula Settings (method = formula)", {
            "classes": ("collapse",),
            "fields": ("formula_text", "default_params", "required_vars")
        }),
        ("Governance & Eligibility", {
            "classes": ("collapse",),
            "fields": (("policy_band_min_percent", "policy_band_max_percent"), "eligibility")
        }),
        ("Payout & Proration", {
            "classes": ("collapse",),
            "fields": ("proration_method", "payout_policy", "payout_months", "allow_negative")
        }),
        ("Payslip Presentation", {
            "classes": ("collapse",),
            "fields": ("payslip_group", "display_order", "show_on_payslip")
        }),
    )

    actions = ["duplicate_as_new_version"]


    def duplicate_as_new_version(self, request, queryset):
        from datetime import timedelta
        from django.utils import timezone
        count = 0
        tomorrow = timezone.localdate() + timedelta(days=1)
        for obj in queryset:
            clone = PayrollComponentGlobal(
                **{f.name: getattr(obj, f.name) for f in obj._meta.fields
                   if f.name not in ("id", "created_at", "updated_at", "effective_from", "effective_to")}
            )
            clone.effective_from = tomorrow
            clone.effective_to = None
            clone.save()
            count += 1
        self.message_user(request, f"Created {count} new version(s) effective {tomorrow}.")
    duplicate_as_new_version.short_description = "Duplicate as new version (effective tomorrow)"

    
@admin.register(PayrollComponentCap)
class PayrollComponentCapAdmin(admin.ModelAdmin):
    list_display = ("component", "cap_type", "cap_basis", "cap_value", "periodicity", "sort_order")
    list_filter = ("cap_type", "periodicity")
    search_fields = ("component__code", "notes")
    formfield_overrides = JSONFIELD_OVERRIDES
    ordering = ("component__code", "sort_order", "id")

@admin.register(SlabGroup)
class SlabGroupAdmin(SimpleHistoryAdmin):
    list_display = ("group_key", "name", "type", "effective_from", "effective_to")
    list_filter  = ("type",)
    search_fields = ("group_key", "name")
    date_hierarchy = "effective_from"
    inlines = (SlabInline,)

    def get_inline_instances(self, request, obj=None):
        # When adding a new SlabGroup (obj is None) or in popup add (_popup=1),
        # don't render inlines to avoid filtering by an unsaved parent instance.
        if obj is None or request.GET.get("_popup") == "1":
            return []
        return super().get_inline_instances(request, obj)

@admin.register(Slab)
class SlabAdmin(admin.ModelAdmin):
    list_display = (
        "group", "state_scope", "from_amount", "to_amount",
        "rate_type", "value", "cycle", "months", "effective_from", "effective_to"
    )
    list_filter = (ActiveNowListFilter, "group__type", "state_scope", "rate_type", "cycle")
    search_fields = ("group__group_key", "state_scope")
    date_hierarchy = "effective_from"
    ordering = ("group__group_key", "state_scope", "from_amount", "effective_from")

@admin.register(CityCategory)
class CityCategoryAdmin(admin.ModelAdmin):
    list_display = ("city_code", "city_name", "category", "effective_from", "effective_to")
    list_filter = (ActiveNowListFilter, "category")
    search_fields = ("city_code", "city_name")
    date_hierarchy = "effective_from"
    ordering = ("city_code", "effective_from")








@admin.register(EntityPayrollComponent)
class EntityPayrollComponentAdmin(EntityScopedAdminMixin,SimpleHistoryAdmin):
    list_display = (
        "entity", "family", "component", "enabled",
        "effective_from", "effective_to",
        "default_percent", "default_amount", "slab_scope_value",
    )
    list_filter = ("enabled", "family", "entity")
    search_fields = ("family__code","entity__entityname")  # <-- tuple
    date_hierarchy = "effective_from"
    ordering = ("family__code", "effective_from")      # <-- tuple
    # list_select_related = ("family", "component")
    # autocomplete_fields = ("family", "component")
    fieldsets = (
        ("Entity & Link", {
            "fields": (
                ("entity", "family", "component", "enabled"),
                ("effective_from", "effective_to"),
            )
        }),
        ("Defaults (method-aware)", {
            "fields": (
                ("default_percent", "default_amount"),
                "param_overrides",
                "slab_scope_value",
            )
        }),
        ("Employee Overrides Policy (optional)", {
            "classes": ("collapse",),
            "fields": (
                ("allow_emp_override", "emp_min_percent", "emp_max_percent"),
                "notes",
            )
        }),
    )



# 1) Use ActionForm (includes the 'action' field the changelist expects)
class ApplyActionForm(ActionForm):
    entity = forms.ModelChoiceField(
        label="Entity",
        queryset=Entity.objects.all(),
        required=True,
    )
    effective_from = forms.DateField(
        label="Effective from",
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
    )


@admin.register(PayStructure)
class PayStructureAdmin(EntityScopedAdminMixin, SimpleHistoryAdmin):
    list_display = ("code", "name", "entity", "status", "effective_from", "effective_to",
                    "rounding", "proration_method", "updated_at")
    list_filter = ("status", "entity", "rounding", "proration_method")
    search_fields = ("code", "name", "notes")
    inlines = ()  # or your PayStructureComponentInline
    action_form = ApplyActionForm
    actions = ("apply_to_entity_dry_run", "apply_to_entity_real")

    # (optional) restrict Entity choices per user
    def get_action_form(self, request, *args, **kwargs):
        form = super().get_action_form(request, *args, **kwargs)
        if not request.user.is_superuser:
            try:
                # narrow to the user’s entity, adjust to your profile path
                form.base_fields["entity"].queryset = Entity.objects.filter(pk=request.user.profile.entity_id)
            except Exception:
                pass
        return form

    def _get_apply_params(self, request):
        """
        Read from POST (action form) first; fall back to GET querystring.
        Always return (entity_id, date or None).
        """
        entity_id = (
            request.POST.get("entity")
            or request.POST.get("entity_id")
            or request.GET.get("entity")
            or request.GET.get("entity_id")
        )
        eff_str = request.POST.get("effective_from") or request.GET.get("effective_from")
        eff_date = parse_date(eff_str) if eff_str else None
        return entity_id, eff_date

    # ---- DRY-RUN (preview; no writes) ----
    def apply_to_entity_dry_run(self, request, queryset):
        entity_id, eff_date = self._get_apply_params(request)
        if not entity_id or not eff_date:
            self.message_user(request, "Provide Entity & Effective From …", level=messages.ERROR)
            return
        for ps in queryset:
            try:
                res = apply_structure_to_entity(
                    structure=ps,                      # <-- here
                    entity_id=int(entity_id),
                    eff_from=eff_date,
                    dry_run=True,
                )
                self.message_user(request, f"{ps.code}: {res}", level=messages.INFO)
            except Exception as e:
                self.message_user(request, f"{ps.code}: {e}", level=messages.ERROR)
    apply_to_entity_dry_run.short_description = "Dry-run apply to entity"

    # ---- REAL APPLY (writes EPC rows) ----
    def apply_to_entity_real(self, request, queryset):
        entity_id, eff_date = self._get_apply_params(request)
        if not entity_id or not eff_date:
            self.message_user(request, "Provide Entity & Effective From …", level=messages.ERROR)
            return
        for ps in queryset:
            try:
                res = apply_structure_to_entity(
                    structure=ps,                      # <-- and here
                    entity_id=int(entity_id),
                    eff_from=eff_date,
                    dry_run=False,
                )
                self.message_user(request, f"{ps.code}: {res}", level=messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"{ps.code}: {e}", level=messages.ERROR)
    apply_to_entity_real.short_description = "Apply to entity (WRITE EPC rows)"

    
@admin.register(PayStructureComponent)
class PayStructureComponentAdmin(admin.ModelAdmin):
    form = PayStructureComponentAdminForm
    list_display = ("template", "family", "priority", "enabled", "required",
                    "default_percent", "default_amount",
                    "allow_emp_override", "show_on_payslip", "display_order", "updated_at")
    list_filter = ("enabled", "required", "family")
    search_fields = ("template__code", "family__code", "notes")
    ordering = ("template", "priority", "id")



# =====================================================================
# Inlines
# =====================================================================


TS_CREATED_CANDIDATES = ("created", "created_at", "created_on")
TS_MODIFIED_CANDIDATES = ("modified", "modified_at", "updated_at", "updated_on")

def _pick_ts(obj, candidates):
    for name in candidates:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None

@admin.register(GradeBand)
class GradeBandAdmin(admin.ModelAdmin):
    list_display = ("entity", "code", "name", "level", "min_ctc", "max_ctc", "created_col", "modified_col")

    def created_col(self, obj): return _pick_ts(obj, TS_CREATED_CANDIDATES) or "-"
    created_col.short_description = "Created"

    def modified_col(self, obj): return _pick_ts(obj, TS_MODIFIED_CANDIDATES) or "-"
    modified_col.short_description = "Modified"

@admin.register(Designation)
class DesignationAdmin(admin.ModelAdmin):
    list_display = ("entity", "name", "grade_band", "parent", "created_col", "modified_col")

    def created_col(self, obj): return _pick_ts(obj, TS_CREATED_CANDIDATES) or "-"
    created_col.short_description = "Created"

    def modified_col(self, obj): return _pick_ts(obj, TS_MODIFIED_CANDIDATES) or "-"
    modified_col.short_description = "Modified"



# =====================================================================
# Masters & Options (for autocomplete + quick edits)
# =====================================================================



