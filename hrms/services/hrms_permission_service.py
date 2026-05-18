from __future__ import annotations

from rbac.services import EffectivePermissionService


class HrmsPermissionService:
    ENTITY_PERMISSION_CODES = {
        "organization_unit_view": {"hrms.organization_unit.view"},
        "organization_unit_create": {"hrms.organization_unit.create"},
        "organization_unit_update": {"hrms.organization_unit.update"},
        "organization_unit_delete": {"hrms.organization_unit.delete"},
        "employee_view": {"hrms.employee.view"},
        "employee_create": {"hrms.employee.create"},
        "employee_update": {"hrms.employee.update"},
        "employee_delete": {"hrms.employee.delete"},
        "employment_contract_view": {"hrms.employment_contract.view"},
        "employment_contract_create": {"hrms.employment_contract.create"},
        "employment_contract_update": {"hrms.employment_contract.update"},
        "employment_contract_delete": {"hrms.employment_contract.delete"},
        "shift_view": {"hrms.shift.view"},
        "shift_create": {"hrms.shift.create"},
        "shift_update": {"hrms.shift.update"},
        "shift_delete": {"hrms.shift.delete"},
        "holiday_calendar_view": {"hrms.holiday_calendar.view"},
        "holiday_calendar_create": {"hrms.holiday_calendar.create"},
        "holiday_calendar_update": {"hrms.holiday_calendar.update"},
        "holiday_calendar_delete": {"hrms.holiday_calendar.delete"},
        "onboarding_view": {"hrms.onboarding.view"},
        "onboarding_adopt": {"hrms.onboarding.adopt"},
        "onboarding_update": {"hrms.onboarding.update"},
        "attendance_entry_view": {"hrms.attendance_entry.view"},
        "attendance_entry_create": {"hrms.attendance_entry.create"},
        "attendance_entry_update": {"hrms.attendance_entry.update"},
        "attendance_import_batch_view": {"hrms.attendance_import_batch.view"},
        "attendance_import_batch_create": {"hrms.attendance_import_batch.create"},
        "attendance_summary_view": {"hrms.attendance_summary.view"},
        "attendance_payroll_period_view": {"hrms.attendance_payroll_period.view"},
        "attendance_approval_view": {"hrms.attendance_approval.view"},
        "attendance_approval_submit": {"hrms.attendance_approval.submit"},
        "attendance_approval_approve": {"hrms.attendance_approval.approve"},
        "attendance_approval_reject": {"hrms.attendance_approval.reject"},
        "attendance_monthly_close_view": {"hrms.attendance_monthly_close.view"},
        "attendance_monthly_close_create": {"hrms.attendance_monthly_close.create"},
        "attendance_monthly_close_submit": {"hrms.attendance_monthly_close.submit"},
        "attendance_monthly_close_approve": {"hrms.attendance_monthly_close.approve"},
        "attendance_monthly_close_close": {"hrms.attendance_monthly_close.close"},
        "leave_policy_view": {"hrms.leave_policy.view"},
        "leave_policy_update": {"hrms.leave_policy.update"},
        "leave_balance_view": {"hrms.leave_balance.view"},
        "leave_ledger_view": {"hrms.leave_ledger.view"},
        "leave_application_view": {"hrms.leave_application.view"},
        "leave_application_create": {"hrms.leave_application.create"},
        "leave_application_approve": {"hrms.leave_application.approve"},
        "leave_application_reject": {"hrms.leave_application.reject"},
        "leave_application_cancel": {"hrms.leave_application.cancel"},
    }

    @classmethod
    def has_entity_permission_access(cls, *, user, entity_id: int | None, permission_key: str) -> bool:
        if not entity_id or not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        available_codes = set(EffectivePermissionService.permission_codes_for_user(user, entity_id))
        required_codes = cls.ENTITY_PERMISSION_CODES.get(permission_key, set())
        return bool(required_codes & available_codes)

    @classmethod
    def assert_entity_permission_access(cls, *, user, entity_id: int | None, permission_key: str, label: str) -> None:
        if cls.has_entity_permission_access(user=user, entity_id=entity_id, permission_key=permission_key):
            return
        raise PermissionError(f"You do not have permission to {label}.")
