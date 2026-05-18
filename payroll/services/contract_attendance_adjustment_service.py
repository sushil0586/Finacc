from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from payroll.models import ContractAttendanceAdjustment, ContractPayrollProfile, PayrollPeriod


class ContractAttendanceAdjustmentService:
    @staticmethod
    def list_adjustments(
        *,
        entity_id: int,
        search: str | None = None,
        contract_payroll_profile_id: str | None = None,
        payroll_period_id: int | None = None,
        adjustment_type: str | None = None,
        approval_status: str | None = None,
        is_active: bool | None = None,
    ):
        queryset = ContractAttendanceAdjustment.objects.select_related(
            "entity",
            "contract_payroll_profile",
            "contract_payroll_profile__hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
            "payroll_period",
        ).filter(entity_id=entity_id)
        if search:
            queryset = queryset.filter(
                Q(contract_payroll_profile__hrms_contract__contract_code__icontains=search)
                | Q(contract_payroll_profile__hrms_contract__employee__employee_number__icontains=search)
                | Q(contract_payroll_profile__hrms_contract__employee__display_name__icontains=search)
                | Q(payroll_period__code__icontains=search)
                | Q(remarks__icontains=search)
            )
        if contract_payroll_profile_id:
            queryset = queryset.filter(contract_payroll_profile_id=contract_payroll_profile_id)
        if payroll_period_id:
            queryset = queryset.filter(payroll_period_id=payroll_period_id)
        if adjustment_type:
            queryset = queryset.filter(adjustment_type=adjustment_type)
        if approval_status:
            queryset = queryset.filter(approval_status=approval_status)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("-payroll_period__period_end", "contract_payroll_profile__hrms_contract__contract_code", "id")

    @staticmethod
    def validate_entity_consistency(*, contract_payroll_profile: ContractPayrollProfile, payroll_period: PayrollPeriod, entity_id: int) -> None:
        if contract_payroll_profile.entity_id != entity_id:
            raise ValueError({"contract_payroll_profile": ["Contract payroll profile must belong to the selected entity."]})
        if payroll_period.entity_id != entity_id:
            raise ValueError({"payroll_period": ["Payroll period must belong to the selected entity."]})

    @classmethod
    @transaction.atomic
    def create_or_update_adjustment(
        cls,
        attrs: dict,
        *,
        instance: ContractAttendanceAdjustment | None = None,
    ) -> ContractAttendanceAdjustment:
        adjustment = instance or ContractAttendanceAdjustment()
        for key, value in attrs.items():
            setattr(adjustment, key, value)
        cls.validate_entity_consistency(
            contract_payroll_profile=adjustment.contract_payroll_profile,
            payroll_period=adjustment.payroll_period,
            entity_id=adjustment.entity_id,
        )
        try:
            adjustment.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        adjustment.save()
        return adjustment

    @staticmethod
    def list_approved_adjustments(
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_period: PayrollPeriod,
    ):
        return ContractAttendanceAdjustment.objects.filter(
            contract_payroll_profile=contract_payroll_profile,
            payroll_period=payroll_period,
            is_active=True,
            approval_status=ContractAttendanceAdjustment.ApprovalStatus.APPROVED,
        ).order_by("id")

    @classmethod
    def aggregate_adjustments(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_period: PayrollPeriod,
    ) -> dict:
        adjustments = list(
            cls.list_approved_adjustments(
                contract_payroll_profile=contract_payroll_profile,
                payroll_period=payroll_period,
            )
        )
        totals_by_type: dict[str, Decimal] = {}
        total_adjustment_value = Decimal("0.00")
        for item in adjustments:
            totals_by_type[item.adjustment_type] = totals_by_type.get(item.adjustment_type, Decimal("0.00")) + item.adjustment_value
            total_adjustment_value += item.adjustment_value
        return {
            "adjustment_count": len(adjustments),
            "approved_adjustments": adjustments,
            "totals_by_type": totals_by_type,
            "total_adjustment_value": total_adjustment_value,
        }
