from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from entity.approval_workflow_service import ApprovalWorkflowService
from payroll.models import ContractPayrollProfile, ContractTaxDeclaration, ContractTaxDeclarationLine
from payroll.services.contract_salary_assignment_service import ContractSalaryAssignmentService
from payroll.services.payroll_tds_engine import PayrollTDSEngine


class ContractTaxDeclarationService:
    STATUS_PRIORITY = {
        ContractTaxDeclaration.DeclarationStatus.APPROVED: 0,
        ContractTaxDeclaration.DeclarationStatus.SUBMITTED: 1,
        ContractTaxDeclaration.DeclarationStatus.DRAFT: 2,
        ContractTaxDeclaration.DeclarationStatus.REJECTED: 3,
    }

    @staticmethod
    def _sync_projection_fields(declaration: ContractTaxDeclaration) -> None:
        assignment = ContractSalaryAssignmentService.get_active_assignment_for_payroll_date(
            contract_payroll_profile=declaration.contract_payroll_profile,
            payroll_date=declaration.financial_year.finstartyear.date(),
        )
        policy = getattr(getattr(assignment, "salary_structure_version", None), "calculation_policy_json", None) or {}
        result = PayrollTDSEngine.build_projection(
            contract_payroll_profile=declaration.contract_payroll_profile,
            salary_assignment=assignment,
            declaration=declaration,
            tax_regime=declaration.tax_regime,
            policy=policy,
        )
        declaration.annual_gross_projection = PayrollTDSEngine._decimal(result.snapshot.get("annual_gross_projection"))
        declaration.annual_other_income = PayrollTDSEngine._decimal(result.snapshot.get("annual_other_income"))
        declaration.annual_exemption_total = PayrollTDSEngine._decimal(result.snapshot.get("annual_exemption_total"))
        declaration.annual_deduction_total = PayrollTDSEngine._decimal(result.snapshot.get("annual_deduction_total"))
        declaration.projected_taxable_income = PayrollTDSEngine._decimal(result.snapshot.get("projected_taxable_income"))
        declaration.projected_annual_tax = PayrollTDSEngine._decimal(result.snapshot.get("projected_annual_tax"))
        declaration.projected_monthly_tds = PayrollTDSEngine._decimal(result.snapshot.get("projected_monthly_tds"))
        declaration.tax_already_deducted = PayrollTDSEngine._decimal(result.snapshot.get("tax_already_deducted"))
        declaration.balance_tax = PayrollTDSEngine._decimal(result.snapshot.get("balance_tax"))

    @staticmethod
    def list_declarations(
        *,
        entity_id: int,
        search: str | None = None,
        contract_payroll_profile_id: str | None = None,
        financial_year_id: int | None = None,
        declaration_status: str | None = None,
        tax_regime: str | None = None,
        is_active: bool | None = None,
    ):
        queryset = ContractTaxDeclaration.objects.select_related(
            "entity",
            "contract_payroll_profile",
            "contract_payroll_profile__hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
            "financial_year",
        ).prefetch_related("lines").filter(entity_id=entity_id)
        if search:
            queryset = queryset.filter(
                Q(contract_payroll_profile__hrms_contract__contract_code__icontains=search)
                | Q(contract_payroll_profile__hrms_contract__employee__employee_number__icontains=search)
                | Q(contract_payroll_profile__hrms_contract__employee__display_name__icontains=search)
            )
        if contract_payroll_profile_id:
            queryset = queryset.filter(contract_payroll_profile_id=contract_payroll_profile_id)
        if financial_year_id:
            queryset = queryset.filter(financial_year_id=financial_year_id)
        if declaration_status:
            queryset = queryset.filter(declaration_status=declaration_status)
        if tax_regime is not None and tax_regime != "":
            queryset = queryset.filter(tax_regime=tax_regime)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("-financial_year__finstartyear", "contract_payroll_profile__hrms_contract__contract_code")

    @staticmethod
    @transaction.atomic
    def create_or_update_declaration(attrs: dict, *, instance: ContractTaxDeclaration | None = None) -> ContractTaxDeclaration:
        declaration = instance or ContractTaxDeclaration()
        for key, value in attrs.items():
            setattr(declaration, key, value)
        if declaration.declaration_status == ContractTaxDeclaration.DeclarationStatus.SUBMITTED and not declaration.submitted_at:
            declaration.submitted_at = timezone.now()
            declaration.approval_status = ContractTaxDeclaration.ApprovalStatus.PENDING_APPROVAL
        if declaration.declaration_status == ContractTaxDeclaration.DeclarationStatus.APPROVED and not declaration.approved_at:
            declaration.approved_at = timezone.now()
            declaration.approval_status = ContractTaxDeclaration.ApprovalStatus.APPROVED
        try:
            declaration.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        declaration.save()
        ContractTaxDeclarationService._sync_projection_fields(declaration)
        declaration.save(
            update_fields=[
                "annual_gross_projection",
                "annual_other_income",
                "annual_exemption_total",
                "annual_deduction_total",
                "projected_taxable_income",
                "projected_annual_tax",
                "projected_monthly_tds",
                "tax_already_deducted",
                "balance_tax",
                "updated_at",
            ]
        )
        return declaration

    @staticmethod
    @transaction.atomic
    def create_or_update_line(attrs: dict, *, instance: ContractTaxDeclarationLine | None = None) -> ContractTaxDeclarationLine:
        line = instance or ContractTaxDeclarationLine()
        for key, value in attrs.items():
            setattr(line, key, value)
        line.declaration_category = PayrollTDSEngine.infer_line_category(
            section_code=line.section_code,
            declaration_category=getattr(line, "declaration_category", ""),
        )
        if not line.declaration_code:
            line.declaration_code = PayrollTDSEngine.infer_line_code(line=line)
        try:
            line.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        line.save()
        ContractTaxDeclarationService._sync_projection_fields(line.declaration)
        line.declaration.save(
            update_fields=[
                "annual_gross_projection",
                "annual_other_income",
                "annual_exemption_total",
                "annual_deduction_total",
                "projected_taxable_income",
                "projected_annual_tax",
                "projected_monthly_tds",
                "tax_already_deducted",
                "balance_tax",
                "updated_at",
            ]
        )
        return line

    @classmethod
    def resolve_approved_declaration(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        declaration_date: date,
        financial_year_id: int | None = None,
    ) -> ContractTaxDeclaration | None:
        queryset = cls._active_queryset(
            contract_payroll_profile=contract_payroll_profile,
            declaration_date=declaration_date,
            financial_year_id=financial_year_id,
        ).filter(
            declaration_status=ContractTaxDeclaration.DeclarationStatus.APPROVED,
            approval_status__in=[
                ContractTaxDeclaration.ApprovalStatus.APPROVED,
                ContractTaxDeclaration.ApprovalStatus.LOCKED,
            ],
        )
        return queryset.order_by("-approved_at", "-updated_at", "-id").first()

    @classmethod
    def resolve_preferred_declaration(
        cls,
        *,
        contract_payroll_profile: ContractPayrollProfile,
        declaration_date: date,
        financial_year_id: int | None = None,
    ) -> ContractTaxDeclaration | None:
        declarations = list(
            cls._active_queryset(
                contract_payroll_profile=contract_payroll_profile,
                declaration_date=declaration_date,
                financial_year_id=financial_year_id,
            )
            .exclude(
                approval_status__in=[
                    ContractTaxDeclaration.ApprovalStatus.REJECTED,
                    ContractTaxDeclaration.ApprovalStatus.CANCELLED,
                ]
            )
        )
        if not declarations:
            return None
        declarations.sort(
            key=lambda item: (
                cls.STATUS_PRIORITY.get(item.declaration_status, 99),
                -(item.approved_at.timestamp() if item.approved_at else 0),
                -(item.submitted_at.timestamp() if item.submitted_at else 0),
                -item.updated_at.timestamp(),
            )
        )
        return declarations[0]

    @staticmethod
    def _active_queryset(
        *,
        contract_payroll_profile: ContractPayrollProfile,
        declaration_date: date,
        financial_year_id: int | None = None,
    ):
        queryset = ContractTaxDeclaration.objects.select_related(
            "financial_year",
            "contract_payroll_profile",
            "contract_payroll_profile__hrms_contract",
        ).prefetch_related("lines").filter(
            contract_payroll_profile=contract_payroll_profile,
            is_active=True,
        )
        if financial_year_id:
            queryset = queryset.filter(financial_year_id=financial_year_id)
        else:
            queryset = queryset.filter(
                financial_year__finstartyear__date__lte=declaration_date,
                financial_year__finendyear__date__gte=declaration_date,
            )
        return queryset

    @classmethod
    @transaction.atomic
    def submit_for_approval(cls, *, declaration: ContractTaxDeclaration, actor_id: int | None, remarks: str = "") -> ContractTaxDeclaration:
        declaration.declaration_status = ContractTaxDeclaration.DeclarationStatus.SUBMITTED
        declaration.submitted_at = timezone.now()
        declaration.requested_by_id = actor_id
        declaration.save(update_fields=["declaration_status", "submitted_at", "requested_by", "updated_at"])
        ApprovalWorkflowService.submit_for_approval(
            instance=declaration,
            workflow_key="contract_tax_declaration",
            actor_id=actor_id,
            remarks=remarks,
            title=f"Tax Declaration {declaration.contract_payroll_profile.employee_code or declaration.id}",
        )
        return declaration

    @classmethod
    @transaction.atomic
    def approve(cls, *, declaration: ContractTaxDeclaration, actor_id: int | None, remarks: str = "") -> ContractTaxDeclaration:
        ApprovalWorkflowService.approve(
            instance=declaration,
            workflow_key="contract_tax_declaration",
            actor_id=actor_id,
            remarks=remarks,
        )
        declaration.declaration_status = ContractTaxDeclaration.DeclarationStatus.APPROVED
        declaration.approved_by_id = actor_id
        declaration.approved_at = timezone.now()
        declaration.save(update_fields=["declaration_status", "approved_by", "approved_at", "updated_at"])
        return declaration

    @classmethod
    @transaction.atomic
    def reject(cls, *, declaration: ContractTaxDeclaration, actor_id: int | None, remarks: str = "") -> ContractTaxDeclaration:
        ApprovalWorkflowService.reject(
            instance=declaration,
            workflow_key="contract_tax_declaration",
            actor_id=actor_id,
            remarks=remarks,
        )
        declaration.declaration_status = ContractTaxDeclaration.DeclarationStatus.REJECTED
        declaration.rejected_by_id = actor_id
        declaration.rejected_at = timezone.now()
        declaration.save(update_fields=["declaration_status", "rejected_by", "rejected_at", "updated_at"])
        return declaration

    @classmethod
    @transaction.atomic
    def cancel(cls, *, declaration: ContractTaxDeclaration, actor_id: int | None, remarks: str = "") -> ContractTaxDeclaration:
        ApprovalWorkflowService.cancel(
            instance=declaration,
            workflow_key="contract_tax_declaration",
            actor_id=actor_id,
            remarks=remarks,
        )
        declaration.cancelled_by_id = actor_id
        declaration.cancelled_at = timezone.now()
        declaration.save(update_fields=["cancelled_by", "cancelled_at", "updated_at"])
        return declaration
