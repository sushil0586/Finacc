from django.contrib import admin

from hrms.models import (
    HrEmployee,
    HrEmploymentContract,
    HrHoliday,
    HrHolidayCalendar,
    HrOrganizationUnit,
    HrShift,
)


@admin.register(HrOrganizationUnit)
class HrOrganizationUnitAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "unit_type", "entity", "subentity", "status", "is_active")
    list_filter = ("unit_type", "status", "entity")
    search_fields = ("code", "name", "short_name")


@admin.register(HrEmployee)
class HrEmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_number", "display_name", "entity", "subentity", "work_email", "lifecycle_status", "is_active")
    list_filter = ("lifecycle_status", "entity")
    search_fields = ("employee_number", "display_name", "work_email", "pan", "uan")


@admin.register(HrEmploymentContract)
class HrEmploymentContractAdmin(admin.ModelAdmin):
    list_display = ("contract_code", "employee", "entity", "status", "contract_type", "start_date", "payroll_effective_from", "is_payroll_eligible")
    list_filter = ("status", "contract_type", "entity", "is_payroll_eligible")
    search_fields = ("contract_code", "employee__employee_number", "employee__display_name")


@admin.register(HrShift)
class HrShiftAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "entity", "subentity", "shift_type", "status", "is_active")
    list_filter = ("shift_type", "status", "entity")
    search_fields = ("code", "name")


class HrHolidayInline(admin.TabularInline):
    model = HrHoliday
    extra = 0


@admin.register(HrHolidayCalendar)
class HrHolidayCalendarAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "calendar_year", "entity", "subentity", "status", "is_default")
    list_filter = ("calendar_year", "status", "entity")
    search_fields = ("code", "name")
    inlines = [HrHolidayInline]
