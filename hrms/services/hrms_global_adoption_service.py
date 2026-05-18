from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone

from hrms.models import (
    AttendancePolicy,
    GlobalAttendancePolicyTemplate,
    GlobalHolidayCalendarTemplate,
    GlobalHRPolicyTemplate,
    GlobalLeavePolicyTemplate,
    GlobalShiftTemplate,
    HRPolicy,
    HrHoliday,
    HrHolidayCalendar,
    HrShift,
    LeavePolicy,
    LeavePolicyRule,
    LeaveType,
)


class HrmsGlobalAdoptionService:
    ONBOARDING_CHOICES = {
        "sme_office": "SME Office",
        "factory": "Factory / Manufacturing",
        "retail": "Retail / Shop",
        "services": "Services Company",
        "contractor": "Contractor Workforce",
        "school": "School / Institute",
        "custom": "Custom Setup",
    }

    @staticmethod
    def _unique_code(model, *, entity_id: int, base_code: str) -> str:
        code = base_code.strip().upper()
        if not model.all_objects.filter(entity_id=entity_id, code=code, deleted_at__isnull=True).exists():
            return code
        suffix = 2
        while True:
            candidate = f"{code}_{suffix}"
            if not model.all_objects.filter(entity_id=entity_id, code=candidate, deleted_at__isnull=True).exists():
                return candidate
            suffix += 1

    @classmethod
    def _recommend_queryset(cls, queryset, *, industry_type: str, employee_category: str):
        if employee_category and employee_category != "custom":
            exact = queryset.filter(employee_category=employee_category, is_active=True, is_recommended=True, deleted_at__isnull=True)
            if industry_type:
                exact = exact.filter(industry_type__in=[industry_type, "all", ""])
            if exact.exists():
                return exact.order_by("code")
        return queryset.filter(
            deleted_at__isnull=True,
            is_active=True,
            is_recommended=True,
        ).filter(industry_type__in=[industry_type, "all", ""]).order_by("code")

    @classmethod
    def preview_adoption(cls, *, entity, subentity=None, industry_type: str, employee_category: str, year: int | None = None) -> dict:
        year = year or timezone.localdate().year
        leave_policy_templates = list(cls._recommend_queryset(GlobalLeavePolicyTemplate.all_objects, industry_type=industry_type, employee_category=employee_category))
        shift_templates = list(cls._recommend_queryset(GlobalShiftTemplate.all_objects, industry_type=industry_type, employee_category=employee_category))
        attendance_templates = list(cls._recommend_queryset(GlobalAttendancePolicyTemplate.all_objects, industry_type=industry_type, employee_category=employee_category))
        hr_policy_templates = list(cls._recommend_queryset(GlobalHRPolicyTemplate.all_objects, industry_type=industry_type, employee_category=employee_category))
        holiday_templates = list(
            GlobalHolidayCalendarTemplate.all_objects.filter(
                deleted_at__isnull=True,
                is_active=True,
                is_recommended=True,
                country_code="IN",
            ).order_by("code")
        )
        return {
            "entity_id": entity.id,
            "subentity_id": getattr(subentity, "id", None),
            "industry_type": industry_type,
            "employee_category": employee_category,
            "year": year,
            "recommended_setup": cls.ONBOARDING_CHOICES.get(employee_category, employee_category),
            "templates": {
                "leave_policy_templates": [cls._serialize_global_leave_policy(item) for item in leave_policy_templates],
                "shift_templates": [cls._serialize_global_shift(item) for item in shift_templates],
                "attendance_policy_templates": [cls._serialize_global_attendance(item) for item in attendance_templates],
                "hr_policy_templates": [cls._serialize_global_hr_policy(item) for item in hr_policy_templates],
                "holiday_calendar_templates": [cls._serialize_global_holiday(item) for item in holiday_templates],
            },
            "existing_counts": {
                "leave_types": LeaveType.objects.filter(entity=entity, deleted_at__isnull=True).count(),
                "leave_policies": LeavePolicy.objects.filter(entity=entity, deleted_at__isnull=True).count(),
                "shifts": HrShift.objects.filter(entity=entity, deleted_at__isnull=True).count(),
                "holiday_calendars": HrHolidayCalendar.objects.filter(entity=entity, deleted_at__isnull=True).count(),
                "attendance_policies": AttendancePolicy.objects.filter(entity=entity, deleted_at__isnull=True).count(),
                "hr_policies": HRPolicy.objects.filter(entity=entity, deleted_at__isnull=True).count(),
            },
        }

    @classmethod
    @transaction.atomic
    def adopt_recommended_templates(cls, *, entity, subentity=None, industry_type: str, employee_category: str, year: int | None = None) -> dict:
        preview = cls.preview_adoption(entity=entity, subentity=subentity, industry_type=industry_type, employee_category=employee_category, year=year)
        payload = {
            "leave_policy_template_ids": [item["id"] for item in preview["templates"]["leave_policy_templates"]],
            "shift_template_ids": [item["id"] for item in preview["templates"]["shift_templates"]],
            "holiday_calendar_template_ids": [item["id"] for item in preview["templates"]["holiday_calendar_templates"][:1]],
            "attendance_policy_template_ids": [item["id"] for item in preview["templates"]["attendance_policy_templates"]],
            "hr_policy_template_ids": [item["id"] for item in preview["templates"]["hr_policy_templates"]],
        }
        return cls.adopt_selected_templates(entity=entity, subentity=subentity, selection=payload, year=preview["year"])

    @classmethod
    @transaction.atomic
    def adopt_selected_templates(cls, *, entity, subentity=None, selection: dict, year: int | None = None) -> dict:
        year = year or timezone.localdate().year
        adopted = {
            "leave_types": [],
            "leave_policies": [],
            "leave_policy_rules": [],
            "shifts": [],
            "holiday_calendars": [],
            "attendance_policies": [],
            "hr_policies": [],
        }

        leave_policy_templates = GlobalLeavePolicyTemplate.objects.filter(id__in=selection.get("leave_policy_template_ids", []), deleted_at__isnull=True)
        for template in leave_policy_templates:
            adopted_leave_types = {}
            for rule in template.rules.filter(deleted_at__isnull=True).select_related("leave_type"):
                if rule.leave_type_id and rule.leave_type_id not in adopted_leave_types:
                    leave_type = cls._clone_leave_type(entity=entity, subentity=subentity, template=rule.leave_type)
                    adopted_leave_types[rule.leave_type_id] = leave_type
                    adopted["leave_types"].append(str(leave_type.id))
            leave_policy = cls._clone_leave_policy(entity=entity, subentity=subentity, template=template)
            adopted["leave_policies"].append(str(leave_policy.id))
            for rule in template.rules.filter(deleted_at__isnull=True).select_related("leave_type"):
                leave_type = adopted_leave_types.get(rule.leave_type_id) if rule.leave_type_id else None
                leave_rule = cls._clone_leave_policy_rule(entity=entity, subentity=subentity, leave_policy=leave_policy, leave_type=leave_type, template=rule)
                adopted["leave_policy_rules"].append(str(leave_rule.id))

        for template in GlobalShiftTemplate.objects.filter(id__in=selection.get("shift_template_ids", []), deleted_at__isnull=True):
            shift = cls._clone_shift(entity=entity, subentity=subentity, template=template)
            adopted["shifts"].append(str(shift.id))

        for template in GlobalHolidayCalendarTemplate.objects.filter(id__in=selection.get("holiday_calendar_template_ids", []), deleted_at__isnull=True):
            calendar = cls._clone_holiday_calendar(entity=entity, subentity=subentity, template=template, year=year)
            adopted["holiday_calendars"].append(str(calendar.id))

        for template in GlobalAttendancePolicyTemplate.objects.filter(id__in=selection.get("attendance_policy_template_ids", []), deleted_at__isnull=True):
            policy = cls._clone_attendance_policy(entity=entity, subentity=subentity, template=template)
            adopted["attendance_policies"].append(str(policy.id))

        for template in GlobalHRPolicyTemplate.objects.filter(id__in=selection.get("hr_policy_template_ids", []), deleted_at__isnull=True):
            policy = cls._clone_hr_policy(entity=entity, subentity=subentity, template=template)
            adopted["hr_policies"].append(str(policy.id))

        return {
            "entity_id": entity.id,
            "subentity_id": getattr(subentity, "id", None),
            "year": year,
            "adopted": adopted,
            "summary": cls.entity_setup_summary(entity=entity, subentity=subentity),
        }

    @classmethod
    def entity_setup_summary(cls, *, entity, subentity=None) -> dict:
        setup_filters = {"entity": entity, "deleted_at__isnull": True}
        if subentity is not None:
            setup_filters["subentity__in"] = [subentity, None]
        leave_types = LeaveType.objects.filter(**setup_filters).order_by("code")
        leave_policies = LeavePolicy.objects.filter(**setup_filters).order_by("code")
        shifts = HrShift.objects.filter(**setup_filters).order_by("code")
        calendars = HrHolidayCalendar.objects.filter(**setup_filters).order_by("-calendar_year", "code")
        attendance_policies = AttendancePolicy.objects.filter(**setup_filters).order_by("code")
        hr_policies = HRPolicy.objects.filter(**setup_filters).order_by("policy_area", "code")
        return {
            "counts": {
                "leave_types": leave_types.count(),
                "leave_policies": leave_policies.count(),
                "shifts": shifts.count(),
                "holiday_calendars": calendars.count(),
                "attendance_policies": attendance_policies.count(),
                "hr_policies": hr_policies.count(),
            },
            "leave_types": [cls._serialize_entity_leave_type(item) for item in leave_types],
            "leave_policies": [cls._serialize_entity_leave_policy(item) for item in leave_policies],
            "shifts": [cls._serialize_entity_shift(item) for item in shifts],
            "holiday_calendars": [cls._serialize_entity_holiday_calendar(item) for item in calendars],
            "attendance_policies": [cls._serialize_entity_attendance_policy(item) for item in attendance_policies],
            "hr_policies": [cls._serialize_entity_hr_policy(item) for item in hr_policies],
        }

    @classmethod
    def patch_entity_setup(cls, *, setup_type: str, obj, payload: dict):
        allowed_fields = {
            "leave_type": {"name", "description", "is_active", "color_hex", "metadata", "payroll_impact_code"},
            "leave_policy": {
                "name",
                "description",
                "is_active",
                "policy_json",
                "metadata",
                "leave_year_type",
                "year_start_month",
                "year_start_day",
                "year_end_month",
                "year_end_day",
            },
            "leave_policy_rule": {"rule_name", "rule_json", "is_active", "metadata", "sequence"},
            "shift": {"name", "description", "is_active", "weekly_off_pattern", "metadata", "status", "grace_in_minutes", "grace_out_minutes"},
            "holiday_calendar": {"name", "description", "is_active", "status", "metadata", "is_default"},
            "attendance_policy": {"name", "description", "is_active", "policy_json", "metadata", "status"},
            "hr_policy": {"name", "description", "is_active", "policy_json", "metadata", "status"},
        }
        editable = allowed_fields[setup_type]
        for key, value in payload.items():
            if key in editable:
                setattr(obj, key, value)
        obj.save()
        return obj

    @classmethod
    def _clone_leave_type(cls, *, entity, subentity, template):
        return LeaveType.objects.create(
            entity=entity,
            subentity=subentity,
            code=cls._unique_code(LeaveType, entity_id=entity.id, base_code=template.code),
            name=template.name,
            category=template.category,
            description=template.description,
            color_hex=template.color_hex,
            is_paid=template.is_paid,
            requires_balance=template.requires_balance,
            allow_negative_balance=template.allow_negative_balance,
            counts_towards_attendance=template.counts_towards_attendance,
            payroll_impact_code=template.payroll_impact_code,
            source_global_leave_type=template,
        )

    @classmethod
    def _clone_leave_policy(cls, *, entity, subentity, template):
        return LeavePolicy.objects.create(
            entity=entity,
            subentity=subentity,
            code=cls._unique_code(LeavePolicy, entity_id=entity.id, base_code=template.code),
            name=template.name,
            employee_category=template.employee_category,
            description=template.description,
            policy_json=template.policy_json,
            source_global_leave_policy_template=template,
        )

    @classmethod
    def _clone_leave_policy_rule(cls, *, entity, subentity, leave_policy, leave_type, template):
        return LeavePolicyRule.objects.create(
            entity=entity,
            subentity=subentity,
            leave_policy=leave_policy,
            leave_type=leave_type,
            rule_code=template.rule_code,
            rule_name=template.rule_name,
            sequence=template.sequence,
            rule_json=template.rule_json,
            source_global_leave_policy_rule_template=template,
        )

    @classmethod
    def _clone_shift(cls, *, entity, subentity, template):
        return HrShift.objects.create(
            entity=entity,
            subentity=subentity,
            code=cls._unique_code(HrShift, entity_id=entity.id, base_code=template.code),
            name=template.name,
            shift_type=template.shift_type,
            status=template.status,
            timezone=template.timezone,
            start_time=template.start_time,
            end_time=template.end_time,
            crosses_midnight=template.crosses_midnight,
            break_minutes=template.break_minutes,
            grace_in_minutes=template.grace_in_minutes,
            grace_out_minutes=template.grace_out_minutes,
            minimum_half_day_minutes=template.minimum_half_day_minutes,
            minimum_full_day_minutes=template.minimum_full_day_minutes,
            weekly_off_pattern=template.weekly_off_pattern,
            description=template.description,
            source_global_shift_template=template,
        )

    @classmethod
    def _clone_holiday_calendar(cls, *, entity, subentity, template, year: int):
        calendar = HrHolidayCalendar.objects.create(
            entity=entity,
            subentity=subentity,
            code=cls._unique_code(HrHolidayCalendar, entity_id=entity.id, base_code=f"{template.code}_{year}"),
            name=f"{template.name} {year}",
            calendar_year=year,
            period_start=date(year, 1, 1),
            period_end=date(year, 12, 31),
            status=template.status,
            is_default=True,
            description=template.description,
            source_global_holiday_calendar_template=template,
        )
        for holiday in template.holiday_json or []:
            HrHoliday.objects.create(
                entity=entity,
                subentity=subentity,
                holiday_calendar=calendar,
                holiday_date=date(year, int(holiday["month"]), int(holiday["day"])),
                name=holiday["name"],
                holiday_type=holiday.get("holiday_type", "public"),
                is_paid=bool(holiday.get("is_paid", True)),
                is_optional=bool(holiday.get("holiday_type") == "optional"),
                description=str(holiday.get("description", "")),
            )
        return calendar

    @classmethod
    def _clone_attendance_policy(cls, *, entity, subentity, template):
        return AttendancePolicy.objects.create(
            entity=entity,
            subentity=subentity,
            code=cls._unique_code(AttendancePolicy, entity_id=entity.id, base_code=template.code),
            name=template.name,
            status=template.status,
            description=template.description,
            policy_json=template.policy_json,
            source_global_attendance_policy_template=template,
        )

    @classmethod
    def _clone_hr_policy(cls, *, entity, subentity, template):
        return HRPolicy.objects.create(
            entity=entity,
            subentity=subentity,
            code=cls._unique_code(HRPolicy, entity_id=entity.id, base_code=template.code),
            name=template.name,
            status=template.status,
            policy_area=template.policy_area,
            description=template.description,
            policy_json=template.policy_json,
            source_global_hr_policy_template=template,
        )

    @staticmethod
    def _serialize_global_leave_policy(item):
        return {"id": str(item.id), "code": item.code, "name": item.name, "employee_category": item.employee_category, "industry_type": item.industry_type, "rule_count": item.rules.filter(deleted_at__isnull=True).count()}

    @staticmethod
    def _serialize_global_shift(item):
        return {"id": str(item.id), "code": item.code, "name": item.name, "shift_type": item.shift_type, "industry_type": item.industry_type}

    @staticmethod
    def _serialize_global_holiday(item):
        return {"id": str(item.id), "code": item.code, "name": item.name, "holiday_count": len(item.holiday_json or []), "country_code": item.country_code}

    @staticmethod
    def _serialize_global_attendance(item):
        return {"id": str(item.id), "code": item.code, "name": item.name, "industry_type": item.industry_type}

    @staticmethod
    def _serialize_global_hr_policy(item):
        return {"id": str(item.id), "code": item.code, "name": item.name, "policy_area": item.policy_area, "industry_type": item.industry_type}

    @staticmethod
    def _serialize_entity_leave_type(item):
        return {"id": str(item.id), "code": item.code, "name": item.name, "category": item.category, "is_active": item.is_active, "source_code": getattr(item.source_global_leave_type, "code", None)}

    @staticmethod
    def _serialize_entity_leave_policy(item):
        return {"id": str(item.id), "code": item.code, "name": item.name, "is_active": item.is_active, "source_code": getattr(item.source_global_leave_policy_template, "code", None), "rule_count": item.rules.filter(deleted_at__isnull=True).count()}

    @staticmethod
    def _serialize_entity_shift(item):
        return {"id": str(item.id), "code": item.code, "name": item.name, "is_active": item.is_active, "shift_type": item.shift_type, "source_code": getattr(item.source_global_shift_template, "code", None)}

    @staticmethod
    def _serialize_entity_holiday_calendar(item):
        return {"id": str(item.id), "code": item.code, "name": item.name, "calendar_year": item.calendar_year, "is_active": item.is_active, "source_code": getattr(item.source_global_holiday_calendar_template, "code", None), "holiday_count": item.holidays.filter(deleted_at__isnull=True).count()}

    @staticmethod
    def _serialize_entity_attendance_policy(item):
        return {"id": str(item.id), "code": item.code, "name": item.name, "is_active": item.is_active, "source_code": getattr(item.source_global_attendance_policy_template, "code", None)}

    @staticmethod
    def _serialize_entity_hr_policy(item):
        return {"id": str(item.id), "code": item.code, "name": item.name, "policy_area": item.policy_area, "is_active": item.is_active, "source_code": getattr(item.source_global_hr_policy_template, "code", None)}
