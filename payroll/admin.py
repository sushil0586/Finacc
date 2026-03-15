from django.contrib import admin

from payroll.models import (
    PayrollAdjustment,
    PayrollComponent,
    PayrollComponentPosting,
    PayrollEmployeeProfile,
    PayrollLedgerPolicy,
    PayrollPeriod,
    PayrollRun,
    PayrollRunActionLog,
    PayrollRunEmployee,
    PayrollRunEmployeeComponent,
    Payslip,
    SalaryStructure,
    SalaryStructureLine,
    SalaryStructureVersion,
)


@admin.register(PayrollComponent)
class PayrollComponentAdmin(admin.ModelAdmin):
    list_display = ("entity", "code", "name", "component_type", "posting_behavior", "is_active")
    list_filter = ("entity", "component_type", "posting_behavior", "is_active")
    search_fields = ("code", "name")


@admin.register(PayrollComponentPosting)
class PayrollComponentPostingAdmin(admin.ModelAdmin):
    list_display = ("entity", "component", "expense_account", "liability_account", "payable_account", "is_active")
    list_filter = ("entity", "is_active")
    search_fields = ("component__code", "component__name")


class SalaryStructureLineInline(admin.TabularInline):
    model = SalaryStructureLine
    extra = 0


class SalaryStructureVersionInline(admin.TabularInline):
    model = SalaryStructureVersion
    extra = 0


@admin.register(SalaryStructure)
class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = ("entity", "code", "name", "status", "is_active")
    list_filter = ("entity", "status", "is_active")
    search_fields = ("code", "name")
    inlines = [SalaryStructureVersionInline]


@admin.register(SalaryStructureVersion)
class SalaryStructureVersionAdmin(admin.ModelAdmin):
    list_display = ("salary_structure", "version_no", "effective_from", "effective_to", "status")
    list_filter = ("status",)
    search_fields = ("salary_structure__code", "salary_structure__name")


@admin.register(PayrollEmployeeProfile)
class PayrollEmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ("entity", "employee_code", "full_name", "subentity", "status", "salary_structure")
    list_filter = ("entity", "subentity", "status")
    search_fields = ("employee_code", "full_name", "work_email")


@admin.register(PayrollLedgerPolicy)
class PayrollLedgerPolicyAdmin(admin.ModelAdmin):
    list_display = ("entity", "entityfinid", "subentity", "salary_payable_account", "is_active")
    list_filter = ("entity", "entityfinid", "is_active")


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ("entity", "entityfinid", "subentity", "code", "period_start", "period_end", "status")
    list_filter = ("entity", "entityfinid", "status")
    search_fields = ("code",)


class PayrollRunEmployeeComponentInline(admin.TabularInline):
    model = PayrollRunEmployeeComponent
    extra = 0


class PayrollRunEmployeeInline(admin.TabularInline):
    model = PayrollRunEmployee
    extra = 0
    show_change_link = True


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ("entity", "entityfinid", "subentity", "run_number", "run_type", "status", "payment_status", "posting_date")
    list_filter = ("entity", "entityfinid", "status", "payment_status", "run_type")
    search_fields = ("run_number", "doc_code", "doc_no")
    inlines = [PayrollRunEmployeeInline]


@admin.register(PayrollRunEmployee)
class PayrollRunEmployeeAdmin(admin.ModelAdmin):
    list_display = ("payroll_run", "employee_profile", "status", "gross_amount", "deduction_amount", "payable_amount")
    list_filter = ("status",)
    search_fields = ("employee_profile__employee_code", "employee_profile__full_name")
    inlines = [PayrollRunEmployeeComponentInline]


@admin.register(PayrollAdjustment)
class PayrollAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("entity", "employee_profile", "kind", "amount", "effective_date", "status")
    list_filter = ("entity", "kind", "status")
    search_fields = ("employee_profile__employee_code", "employee_profile__full_name", "remarks")


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ("payslip_number", "payroll_run_employee", "generated_at", "published_at")
    search_fields = ("payslip_number", "payroll_run_employee__employee_profile__employee_code")


@admin.register(PayrollRunActionLog)
class PayrollRunActionLogAdmin(admin.ModelAdmin):
    list_display = ("payroll_run", "action", "old_status", "new_status", "old_payment_status", "new_payment_status", "acted_by", "created_at")
    list_filter = ("action", "new_status", "new_payment_status")
    search_fields = ("payroll_run__run_number", "comment", "reason_code")
