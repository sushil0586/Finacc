from __future__ import annotations

from datetime import time

from django.db import transaction
from django.utils import timezone

from hrms.models import (
    GlobalAttendancePolicyTemplate,
    GlobalHolidayCalendarTemplate,
    GlobalHRPolicyTemplate,
    GlobalLeavePolicyRuleTemplate,
    GlobalLeavePolicyTemplate,
    GlobalLeaveType,
    GlobalShiftTemplate,
)


class HrmsGlobalSeedService:
    LEAVE_TYPES = [
        {
            "code": "CL",
            "name": "Casual Leave",
            "category": GlobalLeaveType.Category.CASUAL,
            "color_hex": "#7C9AFA",
            "requires_balance": True,
            "allow_negative_balance": False,
            "counts_towards_attendance": True,
            "payroll_impact_code": "PAID_LEAVE",
        },
        {
            "code": "SL",
            "name": "Sick Leave",
            "category": GlobalLeaveType.Category.SICK,
            "color_hex": "#79C99E",
            "requires_balance": True,
            "allow_negative_balance": False,
            "counts_towards_attendance": True,
            "payroll_impact_code": "PAID_LEAVE",
        },
        {
            "code": "EL",
            "name": "Earned Leave",
            "category": GlobalLeaveType.Category.EARNED,
            "color_hex": "#F3A85B",
            "requires_balance": True,
            "allow_negative_balance": False,
            "counts_towards_attendance": True,
            "payroll_impact_code": "PAID_LEAVE",
        },
        {
            "code": "LWP",
            "name": "Leave Without Pay",
            "category": GlobalLeaveType.Category.LOP,
            "color_hex": "#E17A7A",
            "is_paid": False,
            "requires_balance": False,
            "allow_negative_balance": True,
            "counts_towards_attendance": False,
            "payroll_impact_code": "LOSS_OF_PAY",
        },
        {
            "code": "ML",
            "name": "Maternity Leave",
            "category": GlobalLeaveType.Category.MATERNITY,
            "color_hex": "#D98FC5",
            "requires_balance": True,
            "counts_towards_attendance": True,
            "payroll_impact_code": "PAID_LEAVE",
        },
        {
            "code": "PL",
            "name": "Paternity Leave",
            "category": GlobalLeaveType.Category.PATERNITY,
            "color_hex": "#90C4E8",
            "requires_balance": True,
            "counts_towards_attendance": True,
            "payroll_impact_code": "PAID_LEAVE",
        },
        {
            "code": "CO",
            "name": "Comp Off",
            "category": GlobalLeaveType.Category.COMP_OFF,
            "color_hex": "#8EC6A1",
            "requires_balance": True,
            "counts_towards_attendance": True,
            "payroll_impact_code": "COMP_OFF",
        },
        {
            "code": "OH",
            "name": "Optional Holiday",
            "category": GlobalLeaveType.Category.OPTIONAL_HOLIDAY,
            "color_hex": "#B8A2E0",
            "requires_balance": True,
            "counts_towards_attendance": True,
            "payroll_impact_code": "OPTIONAL_HOLIDAY",
        },
    ]

    @classmethod
    def _upsert(cls, model, *, code: str, defaults: dict, force: bool):
        obj = model.all_objects.filter(code=code).first()
        if obj is None:
            model.objects.create(code=code, **defaults)
            return "created"
        if force:
            for key, value in defaults.items():
                setattr(obj, key, value)
            obj.deleted_at = None
            obj.is_active = True
            obj.save()
            return "updated"
        return "skipped"

    @classmethod
    @transaction.atomic
    def seed_default_catalog(cls, *, force: bool = False, dry_run: bool = False) -> dict:
        result = {
            "dry_run": dry_run,
            "force": force,
            "leave_types": {"created": 0, "updated": 0, "skipped": 0},
            "leave_policies": {"created": 0, "updated": 0, "skipped": 0},
            "leave_policy_rules": {"created": 0, "updated": 0, "skipped": 0},
            "shifts": {"created": 0, "updated": 0, "skipped": 0},
            "holiday_calendars": {"created": 0, "updated": 0, "skipped": 0},
            "attendance_policies": {"created": 0, "updated": 0, "skipped": 0},
            "hr_policies": {"created": 0, "updated": 0, "skipped": 0},
        }

        leave_type_lookup = {}
        for row in cls.LEAVE_TYPES:
            payload = {
                "name": row["name"],
                "description": row["name"],
                "category": row["category"],
                "color_hex": row["color_hex"],
                "is_paid": row.get("is_paid", True),
                "requires_balance": row.get("requires_balance", True),
                "allow_negative_balance": row.get("allow_negative_balance", False),
                "counts_towards_attendance": row.get("counts_towards_attendance", True),
                "payroll_impact_code": row.get("payroll_impact_code", ""),
                "country_code": "IN",
            }
            status = cls._upsert(GlobalLeaveType, code=row["code"], defaults=payload, force=force)
            result["leave_types"][status] += 1
            if not dry_run:
                leave_type_lookup[row["code"]] = GlobalLeaveType.objects.get(code=row["code"])

        policies = [
            {
                "code": "SME_OFFICE_STD",
                "name": "SME Office Leave Policy",
                "industry_type": "sme_office",
                "employee_category": GlobalLeavePolicyTemplate.EmployeeCategory.SME_OFFICE,
                "policy_json": {"recommended_for": "SME Office", "attendance_basis": "monthly"},
                "rules": [
                    {"rule_code": "CL_YEARLY", "rule_name": "Casual Leave yearly quota", "leave_code": "CL", "sequence": 10, "rule_json": {"accrual_frequency": "yearly", "annual_quota": 12, "carry_forward": {"enabled": False}, "payroll_impact": {"lop_on_exhaustion": True}}},
                    {"rule_code": "SL_YEARLY", "rule_name": "Sick Leave yearly quota", "leave_code": "SL", "sequence": 20, "rule_json": {"accrual_frequency": "yearly", "annual_quota": 6, "carry_forward": {"enabled": True, "max_days": 6}}},
                    {"rule_code": "EL_MONTHLY_ATT_90", "rule_name": "Earned Leave monthly accrual at 90% attendance", "leave_code": "EL", "sequence": 30, "rule_json": {"accrual_frequency": "monthly", "monthly_quota": 1.5, "conditions": {"attendance_percentage_gte": 90, "probation_completed": True}, "carry_forward": {"enabled": True, "max_days": 30}, "encashment": {"enabled": True, "max_days": 10}}},
                ],
            },
            {
                "code": "FACTORY_WORKER_STD",
                "name": "Factory Worker Leave Policy",
                "industry_type": "factory",
                "employee_category": GlobalLeavePolicyTemplate.EmployeeCategory.FACTORY,
                "policy_json": {"recommended_for": "Factory / Manufacturing", "attendance_basis": "working_days"},
                "rules": [
                    {"rule_code": "EL_FACTORY", "rule_name": "Earned Leave monthly accrual for factory workers", "leave_code": "EL", "sequence": 10, "rule_json": {"accrual_frequency": "monthly", "monthly_quota": 1.75, "conditions": {"attendance_percentage_gte": 90}, "carry_forward": {"enabled": True, "max_days": 45}, "payroll_impact": {"lop_on_exhaustion": True}}},
                    {"rule_code": "CO_FACTORY", "rule_name": "Comp off with lapse after 60 days", "leave_code": "CO", "sequence": 20, "rule_json": {"accrual_frequency": "manual", "lapse": {"enabled": True, "days": 60}}},
                ],
            },
            {
                "code": "CORPORATE_STAFF_STD",
                "name": "Corporate Staff Leave Policy",
                "industry_type": "services",
                "employee_category": GlobalLeavePolicyTemplate.EmployeeCategory.SERVICES,
                "policy_json": {"recommended_for": "Services Company", "attendance_basis": "monthly"},
                "rules": [
                    {"rule_code": "CL_CORP", "rule_name": "Casual Leave yearly quota", "leave_code": "CL", "sequence": 10, "rule_json": {"accrual_frequency": "yearly", "annual_quota": 10}},
                    {"rule_code": "SL_CORP", "rule_name": "Sick Leave yearly quota", "leave_code": "SL", "sequence": 20, "rule_json": {"accrual_frequency": "yearly", "annual_quota": 8}},
                    {"rule_code": "EL_CORP", "rule_name": "Earned Leave monthly accrual", "leave_code": "EL", "sequence": 30, "rule_json": {"accrual_frequency": "monthly", "monthly_quota": 1.5, "conditions": {"attendance_percentage_gte": 90, "probation_completed": True}, "carry_forward": {"enabled": True, "max_days": 30}, "encashment": {"enabled": True, "max_days": 15}}},
                ],
            },
        ]

        for policy_row in policies:
            defaults = {
                "name": policy_row["name"],
                "description": policy_row["name"],
                "industry_type": policy_row["industry_type"],
                "employee_category": policy_row["employee_category"],
                "country_code": "IN",
                "policy_json": policy_row["policy_json"],
            }
            status = cls._upsert(GlobalLeavePolicyTemplate, code=policy_row["code"], defaults=defaults, force=force)
            result["leave_policies"][status] += 1
            if dry_run:
                continue
            template = GlobalLeavePolicyTemplate.objects.get(code=policy_row["code"])
            for rule in policy_row["rules"]:
                leave_type = leave_type_lookup.get(rule["leave_code"])
                obj = GlobalLeavePolicyRuleTemplate.all_objects.filter(template=template, rule_code=rule["rule_code"]).first()
                if obj is None:
                    GlobalLeavePolicyRuleTemplate.objects.create(
                        template=template,
                        leave_type=leave_type,
                        rule_code=rule["rule_code"],
                        rule_name=rule["rule_name"],
                        sequence=rule["sequence"],
                        rule_json=rule["rule_json"],
                    )
                    result["leave_policy_rules"]["created"] += 1
                elif force:
                    obj.leave_type = leave_type
                    obj.rule_name = rule["rule_name"]
                    obj.sequence = rule["sequence"]
                    obj.rule_json = rule["rule_json"]
                    obj.deleted_at = None
                    obj.is_active = True
                    obj.save()
                    result["leave_policy_rules"]["updated"] += 1
                else:
                    result["leave_policy_rules"]["skipped"] += 1

        shift_rows = [
            {"code": "GENERAL_9_6", "name": "General 9 to 6", "industry_type": "services", "employee_category": GlobalShiftTemplate.EmployeeCategory.SERVICES, "shift_type": "fixed", "start_time": time(9, 0), "end_time": time(18, 0), "break_minutes": 60, "minimum_half_day_minutes": 240, "minimum_full_day_minutes": 480, "weekly_off_pattern": ["SAT_HALF", "SUN"]},
            {"code": "FACTORY_A", "name": "Factory A Shift", "industry_type": "factory", "employee_category": GlobalShiftTemplate.EmployeeCategory.FACTORY, "shift_type": "fixed", "start_time": time(6, 0), "end_time": time(14, 0), "break_minutes": 30, "minimum_half_day_minutes": 210, "minimum_full_day_minutes": 450, "weekly_off_pattern": ["SUN"]},
            {"code": "RETAIL_DAY", "name": "Retail Day Shift", "industry_type": "retail", "employee_category": GlobalShiftTemplate.EmployeeCategory.RETAIL, "shift_type": "fixed", "start_time": time(10, 0), "end_time": time(19, 0), "break_minutes": 45, "minimum_half_day_minutes": 240, "minimum_full_day_minutes": 480, "weekly_off_pattern": ["SUN"]},
        ]
        for row in shift_rows:
            status = cls._upsert(
                GlobalShiftTemplate,
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "description": row["name"],
                    "industry_type": row["industry_type"],
                    "employee_category": row["employee_category"],
                    "country_code": "IN",
                    "shift_type": row["shift_type"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "break_minutes": row["break_minutes"],
                    "minimum_half_day_minutes": row["minimum_half_day_minutes"],
                    "minimum_full_day_minutes": row["minimum_full_day_minutes"],
                    "weekly_off_pattern": row["weekly_off_pattern"],
                },
                force=force,
            )
            result["shifts"][status] += 1

        holiday_status = cls._upsert(
            GlobalHolidayCalendarTemplate,
            code="INDIA_STANDARD",
            defaults={
                "name": "India Standard Holiday Calendar",
                "description": "Reusable India holiday calendar template.",
                "industry_type": "all",
                "employee_category": GlobalHolidayCalendarTemplate.EmployeeCategory.CUSTOM,
                "country_code": "IN",
                "template_year": timezone.localdate().year,
                "holiday_json": [
                    {"month": 1, "day": 26, "name": "Republic Day", "holiday_type": "public", "is_paid": True},
                    {"month": 8, "day": 15, "name": "Independence Day", "holiday_type": "public", "is_paid": True},
                    {"month": 10, "day": 2, "name": "Gandhi Jayanti", "holiday_type": "public", "is_paid": True},
                    {"month": 12, "day": 25, "name": "Christmas", "holiday_type": "optional", "is_paid": True},
                ],
            },
            force=force,
        )
        result["holiday_calendars"][holiday_status] += 1

        attendance_rows = [
            {"code": "ATT_SME", "name": "SME Attendance Policy", "industry_type": "sme_office", "employee_category": GlobalAttendancePolicyTemplate.EmployeeCategory.SME_OFFICE, "policy_json": {"grace_in_minutes": 10, "grace_out_minutes": 10, "half_day_after_minutes": 240, "lop_after_minutes": 120}},
            {"code": "ATT_FACTORY", "name": "Factory Attendance Policy", "industry_type": "factory", "employee_category": GlobalAttendancePolicyTemplate.EmployeeCategory.FACTORY, "policy_json": {"grace_in_minutes": 5, "grace_out_minutes": 5, "overtime_rounding_minutes": 30, "minimum_attendance_percentage": 90}},
            {"code": "ATT_SERVICES", "name": "Services Attendance Policy", "industry_type": "services", "employee_category": GlobalAttendancePolicyTemplate.EmployeeCategory.SERVICES, "policy_json": {"grace_in_minutes": 10, "grace_out_minutes": 10, "half_day_after_minutes": 240, "lop_after_minutes": 120, "minimum_attendance_percentage": 90}},
        ]
        for row in attendance_rows:
            status = cls._upsert(
                GlobalAttendancePolicyTemplate,
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "description": row["name"],
                    "industry_type": row["industry_type"],
                    "employee_category": row["employee_category"],
                    "country_code": "IN",
                    "policy_json": row["policy_json"],
                },
                force=force,
            )
            result["attendance_policies"][status] += 1

        hr_policy_rows = [
            {"code": "HR_PROBATION_STD", "name": "Standard Probation Policy", "industry_type": "services", "employee_category": GlobalHRPolicyTemplate.EmployeeCategory.CUSTOM, "policy_area": "probation", "policy_json": {"probation_months": 6, "confirmation_requires_review": True}},
            {"code": "HR_NOTICE_STD", "name": "Standard Notice Policy", "industry_type": "all", "employee_category": GlobalHRPolicyTemplate.EmployeeCategory.CUSTOM, "policy_area": "notice", "policy_json": {"notice_period_days": 30, "buyout_allowed": True}},
            {"code": "HR_REMOTE_STD", "name": "Standard Remote Work Policy", "industry_type": "services", "employee_category": GlobalHRPolicyTemplate.EmployeeCategory.SERVICES, "policy_area": "remote_work", "policy_json": {"hybrid_allowed": True, "onsite_days_per_week": 2}},
        ]
        for row in hr_policy_rows:
            status = cls._upsert(
                GlobalHRPolicyTemplate,
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "description": row["name"],
                    "industry_type": row["industry_type"],
                    "employee_category": row["employee_category"],
                    "country_code": "IN",
                    "policy_area": row["policy_area"],
                    "policy_json": row["policy_json"],
                },
                force=force,
            )
            result["hr_policies"][status] += 1

        if dry_run:
            transaction.set_rollback(True)
        return result
