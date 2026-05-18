from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from payroll.models import ContractPayrollInputSnapshot, ContractPayrollProfile, PayrollPeriod


class ContractPayrollInputSnapshotService:
    @staticmethod
    def list_snapshots(
        *,
        entity_id: int,
        search: str | None = None,
        contract_payroll_profile_id: str | None = None,
        payroll_period_id: int | None = None,
        input_type: str | None = None,
        source: str | None = None,
        is_active: bool | None = None,
    ):
        queryset = ContractPayrollInputSnapshot.objects.select_related(
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
            )
        if contract_payroll_profile_id:
            queryset = queryset.filter(contract_payroll_profile_id=contract_payroll_profile_id)
        if payroll_period_id:
            queryset = queryset.filter(payroll_period_id=payroll_period_id)
        if input_type:
            queryset = queryset.filter(input_type=input_type)
        if source:
            queryset = queryset.filter(source=source)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("-effective_from", "-id")

    @staticmethod
    @transaction.atomic
    def create_or_update_snapshot(attrs: dict, *, instance: ContractPayrollInputSnapshot | None = None) -> ContractPayrollInputSnapshot:
        snapshot = instance or ContractPayrollInputSnapshot()
        for key, value in attrs.items():
            setattr(snapshot, key, value)
        try:
            snapshot.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        snapshot.save()
        return snapshot

    @staticmethod
    def resolve_snapshot(
        *,
        contract_payroll_profile: ContractPayrollProfile,
        input_type: str,
        snapshot_date: date,
        payroll_period: PayrollPeriod | None = None,
    ) -> ContractPayrollInputSnapshot | None:
        queryset = ContractPayrollInputSnapshot.objects.filter(
            contract_payroll_profile=contract_payroll_profile,
            input_type=input_type,
            is_active=True,
            effective_from__lte=snapshot_date,
        ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=snapshot_date))
        if payroll_period is not None:
            queryset = queryset.filter(Q(payroll_period=payroll_period) | Q(payroll_period__isnull=True))
        return queryset.order_by("-payroll_period_id", "-effective_from", "-id").first()

    @classmethod
    def resolve_input_bundle(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        snapshot_date: date,
        payroll_period: PayrollPeriod | None = None,
    ) -> dict[str, ContractPayrollInputSnapshot | None]:
        return {
            "tax_projection": cls.resolve_snapshot(
                contract_payroll_profile=contract_payroll_profile,
                input_type=ContractPayrollInputSnapshot.InputType.TAX_PROJECTION,
                snapshot_date=snapshot_date,
                payroll_period=payroll_period,
            ),
            "attendance_summary": cls.resolve_snapshot(
                contract_payroll_profile=contract_payroll_profile,
                input_type=ContractPayrollInputSnapshot.InputType.ATTENDANCE_SUMMARY,
                snapshot_date=snapshot_date,
                payroll_period=payroll_period,
            ),
            "manual_payroll_input": cls.resolve_snapshot(
                contract_payroll_profile=contract_payroll_profile,
                input_type=ContractPayrollInputSnapshot.InputType.MANUAL_PAYROLL_INPUT,
                snapshot_date=snapshot_date,
                payroll_period=payroll_period,
            ),
        }
