from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db import models
from django.db.models import Q

from payroll.models import ContractAttendanceSummary, ContractPayrollProfile, PayrollPeriod


class ContractAttendanceSummaryService:
    @staticmethod
    def list_summaries(
        *,
        entity_id: int,
        search: str | None = None,
        contract_payroll_profile_id: str | None = None,
        payroll_period_id: int | None = None,
        approval_status: str | None = None,
        source: str | None = None,
        is_active: bool | None = None,
    ):
        queryset = ContractAttendanceSummary.objects.select_related(
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
            )
        if contract_payroll_profile_id:
            queryset = queryset.filter(contract_payroll_profile_id=contract_payroll_profile_id)
        if payroll_period_id:
            queryset = queryset.filter(payroll_period_id=payroll_period_id)
        if approval_status:
            queryset = queryset.filter(approval_status=approval_status)
        if source:
            queryset = queryset.filter(source=source)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("-payroll_period__period_end", "contract_payroll_profile__hrms_contract__contract_code", "-id")

    @staticmethod
    def validate_entity_consistency(*, contract_payroll_profile: ContractPayrollProfile, payroll_period: PayrollPeriod, entity_id: int) -> None:
        if contract_payroll_profile.entity_id != entity_id:
            raise ValueError({"contract_payroll_profile": ["Contract payroll profile must belong to the selected entity."]})
        if payroll_period.entity_id != entity_id:
            raise ValueError({"payroll_period": ["Payroll period must belong to the selected entity."]})

    @classmethod
    @transaction.atomic
    def create_or_update_summary(
        cls,
        attrs: dict,
        *,
        instance: ContractAttendanceSummary | None = None,
    ) -> ContractAttendanceSummary:
        summary = instance or ContractAttendanceSummary()
        for key, value in attrs.items():
            setattr(summary, key, value)
        cls.validate_entity_consistency(
            contract_payroll_profile=summary.contract_payroll_profile,
            payroll_period=summary.payroll_period,
            entity_id=summary.entity_id,
        )
        try:
            summary.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        summary.save()
        return summary

    @staticmethod
    def get_summary(
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_period: PayrollPeriod,
    ) -> ContractAttendanceSummary | None:
        return (
            ContractAttendanceSummary.objects.select_related("payroll_period")
            .filter(
                contract_payroll_profile=contract_payroll_profile,
                payroll_period=payroll_period,
            )
            .order_by("-is_active", "-updated_at", "-id")
            .first()
        )

    @staticmethod
    def resolve_summary(
        *,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_period: PayrollPeriod,
    ) -> ContractAttendanceSummary | None:
        return (
            ContractAttendanceSummary.objects.select_related("payroll_period")
            .filter(
                contract_payroll_profile=contract_payroll_profile,
                payroll_period=payroll_period,
                is_active=True,
            )
            .exclude(approval_status=ContractAttendanceSummary.ApprovalStatus.REJECTED)
            .order_by(
                models.Case(
                    models.When(approval_status=ContractAttendanceSummary.ApprovalStatus.APPROVED, then=0),
                    models.When(approval_status=ContractAttendanceSummary.ApprovalStatus.SUBMITTED, then=1),
                    models.When(approval_status=ContractAttendanceSummary.ApprovalStatus.DRAFT, then=2),
                    default=99,
                    output_field=models.IntegerField(),
                ),
                "-updated_at",
                "-id",
            )
            .first()
        )
