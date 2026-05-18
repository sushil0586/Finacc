from __future__ import annotations

from django.db.models import Q

from hrms.models import AttendancePolicy, HRPolicy, HrEmploymentContract, HrHolidayCalendar, HrShift, LeavePolicy


class HrmsRuntimePolicyService:
    @staticmethod
    def _scoped_queryset(model, *, contract: HrEmploymentContract):
        return model.objects.filter(entity_id=contract.entity_id, deleted_at__isnull=True).filter(
            Q(subentity_id__isnull=True) | Q(subentity_id=contract.subentity_id)
        )

    @classmethod
    def resolve_runtime_setup(cls, *, contract: HrEmploymentContract) -> dict:
        leave_policy = cls._scoped_queryset(LeavePolicy, contract=contract).filter(is_active=True).order_by("-subentity_id", "-is_default", "code").first()
        attendance_policy = cls._scoped_queryset(AttendancePolicy, contract=contract).filter(is_active=True).order_by("-subentity_id", "-is_default", "code").first()
        hr_policies = list(cls._scoped_queryset(HRPolicy, contract=contract).filter(is_active=True).order_by("-subentity_id", "policy_area", "code"))
        shift = contract.default_shift or cls._scoped_queryset(HrShift, contract=contract).filter(is_active=True).order_by("-subentity_id", "code").first()
        holiday_calendar = contract.holiday_calendar or cls._scoped_queryset(HrHolidayCalendar, contract=contract).filter(is_active=True).order_by("-subentity_id", "-is_default", "-calendar_year").first()
        return {
            "leave_policy_id": str(leave_policy.id) if leave_policy else None,
            "attendance_policy_id": str(attendance_policy.id) if attendance_policy else None,
            "shift_id": str(shift.id) if shift else None,
            "holiday_calendar_id": str(holiday_calendar.id) if holiday_calendar else None,
            "hr_policy_ids": [str(item.id) for item in hr_policies],
        }
