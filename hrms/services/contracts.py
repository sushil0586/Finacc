from __future__ import annotations

from django.db.models import Q

from hrms.models import HrEmploymentContract


class EmploymentContractService:
    @staticmethod
    def list_contracts(
        *,
        entity_id,
        subentity_id=None,
        employee_id=None,
        payroll_eligible=None,
        status=None,
        search=None,
        active_only=True,
        ordering="-payroll_effective_from",
    ):
        queryset = HrEmploymentContract.all_objects.for_entity(entity_id=entity_id, subentity_id=subentity_id)
        if active_only:
            queryset = queryset.active()
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        if payroll_eligible is not None:
            queryset = queryset.filter(is_payroll_eligible=payroll_eligible)
        if status:
            queryset = queryset.filter(status=status)
        if search:
            queryset = queryset.filter(
                Q(contract_code__icontains=search)
                | Q(employee__display_name__icontains=search)
                | Q(employee__employee_number__icontains=search)
                | Q(pay_group_code__icontains=search)
                | Q(vendor_reference__icontains=search)
            )
        allowed_ordering = {
            "contract_code": "contract_code",
            "-contract_code": "-contract_code",
            "payroll_effective_from": "payroll_effective_from",
            "-payroll_effective_from": "-payroll_effective_from",
            "start_date": "start_date",
            "-start_date": "-start_date",
            "status": "status",
            "-status": "-status",
            "contract_type": "contract_type",
            "-contract_type": "-contract_type",
            "employee_display_name": "employee__display_name",
            "-employee_display_name": "-employee__display_name",
        }
        queryset = queryset.order_by(allowed_ordering.get(ordering, "-payroll_effective_from"))
        return queryset.select_related(
            "entity",
            "subentity",
            "employee",
            "business_unit",
            "department",
            "team",
            "designation",
            "grade",
            "cost_center",
            "work_location",
            "reports_to_contract",
            "default_shift",
            "holiday_calendar",
        )

    @staticmethod
    def current_contract_for_employee(*, entity_id, employee_id):
        queryset = HrEmploymentContract.all_objects.filter(
            entity_id=entity_id,
            employee_id=employee_id,
            deleted_at__isnull=True,
        ).exclude(
            status__in=[
                HrEmploymentContract.ContractStatus.CLOSED,
                HrEmploymentContract.ContractStatus.EXPIRED,
                HrEmploymentContract.ContractStatus.TERMINATED,
            ]
        )
        return queryset.order_by("-payroll_effective_from", "-created_at").first()
