from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import models
from django.utils import timezone

from entity.models import Entity, EntityApprovalPolicy, EntityFinancialYear, SubEntity
from financial.models import AccountBankDetails, Ledger, account, accountHead, accounttype
from financial.services import apply_normalized_profile_payload, create_account_with_synced_ledger
from hrms.models import AttendanceApproval, AttendanceMonthlyClose, HrEmployee, HrEmploymentContract
from payroll.models import (
    ContractAttendanceSummary,
    ContractPayrollProfile,
    ContractSalaryStructureAssignment,
    PayrollComponent,
    PayrollComponentPosting,
    PayrollLedgerPolicy,
    PayrollPaymentBatch,
    PayrollPeriod,
    PayrollRun,
    SalaryStructure,
    SalaryStructureLine,
    SalaryStructureVersion,
)
from payroll.services import PayrollPaymentBatchService, PayrollRunService
from payroll.services.contract_payroll_profile_service import ContractPayrollProfileService
from payroll.services.contract_salary_assignment_service import ContractSalaryAssignmentService
from payroll.services.payslip_service import PayslipService
from payroll.services.payroll_run_readiness_resolver_service import PayrollRunReadinessResolverService
from rbac.seeding import PayrollRBACSeedService, RBACSeedService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


User = get_user_model()


class Command(BaseCommand):
    help = "Prepare deterministic payroll data for local Playwright browser coverage."

    marker_prefix = "PW-E2E"

    def add_arguments(self, parser):
        parser.add_argument("--user-email", required=True)
        parser.add_argument("--entity-name", required=True)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        user = User.objects.filter(email=options["user_email"]).first()
        if user is None:
            raise CommandError(f"User '{options['user_email']}' was not found.")

        entity = Entity.objects.filter(entityname=options["entity_name"]).first()
        if entity is None:
            raise CommandError(f"Entity '{options['entity_name']}' was not found.")

        if not entity.customer_account_id:
            SubscriptionService.register_entity_creation(entity=entity, owner=user)
            entity.refresh_from_db()

        self._ensure_subscription(entity=entity, user=user)
        self._ensure_access_and_roles(entity=entity, user=user)

        scope = self._resolve_scope(entity=entity)
        payroll_setup = self._ensure_payroll_setup(entity=entity, user=user, scope=scope)
        self._ensure_run_attendance_prerequisites(entity=entity, user=user, scope=scope)
        staged = self._stage_runs_and_batches(entity=entity, user=user, scope=scope)

        payload = {
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "user_id": user.id,
            "user_email": user.email,
            "entityfinid_id": scope["entityfinid"].id,
            "subentity_id": scope["subentity"].id if scope["subentity"] else None,
            "payroll_period_id": scope["period"].id,
            "payroll_period_code": scope["period"].code,
            **payroll_setup,
            **staged,
        }

        output = json.dumps(payload, default=str)
        if options["as_json"]:
            self.stdout.write(output)
        else:
            self.stdout.write(self.style.SUCCESS(output))

    def _ensure_subscription(self, *, entity: Entity, user: User) -> None:
        subscription = SubscriptionService.ensure_active_subscription(customer_account=entity.customer_account)
        payroll_limit = subscription.plan.limits.filter(key=SubscriptionLimitCodes.FEATURE_PAYROLL).first()
        if payroll_limit and payroll_limit.bool_value is not True:
            payroll_limit.bool_value = True
            payroll_limit.save(update_fields=["bool_value", "updated_at"])
        SubscriptionService.ensure_account_membership(
            customer_account=entity.customer_account,
            user=user,
            role="owner",
            granted_by=user,
        )

    def _ensure_access_and_roles(self, *, entity: Entity, user: User) -> None:
        RBACSeedService.seed_entity(entity=entity, actor=user)
        PayrollRBACSeedService.seed_entity_roles(entity=entity, actor=user)

        for group_name in ("payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"):
            Group.objects.get_or_create(name=group_name)[0].user_set.add(user)

    def _resolve_scope(self, *, entity: Entity) -> dict[str, object]:
        entityfinid = EntityFinancialYear.objects.filter(entity=entity).order_by("-finstartyear", "-id").first()
        if entityfinid is None:
            raise CommandError("No financial year exists for the selected entity.")

        subentity = SubEntity.objects.filter(entity=entity, isactive=True).order_by("-is_head_office", "id").first()
        if subentity is None:
            raise CommandError("No active subentity exists for the selected entity.")

        today = timezone.localdate()
        period_start = date(today.year, today.month, 1)
        if today.month == 12:
            next_month = date(today.year + 1, 1, 1)
        else:
            next_month = date(today.year, today.month + 1, 1)
        period_end = next_month - timedelta(days=1)
        code = f"{today.strftime('%b').upper()}-{today.year}-PW-E2E"
        period, _ = PayrollPeriod.objects.get_or_create(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            code=code,
            defaults={
                "period_start": period_start,
                "period_end": period_end,
                "payout_date": period_end,
                "status": PayrollPeriod.Status.OPEN,
            },
        )
        fields_to_update: list[str] = []
        if period.entityfinid_id != entityfinid.id:
            period.entityfinid = entityfinid
            fields_to_update.append("entityfinid")
        if period.subentity_id != subentity.id:
            period.subentity = subentity
            fields_to_update.append("subentity")
        if period.period_start != period_start:
            period.period_start = period_start
            fields_to_update.append("period_start")
        if period.period_end != period_end:
            period.period_end = period_end
            fields_to_update.append("period_end")
        if period.payout_date != period_end:
            period.payout_date = period_end
            fields_to_update.append("payout_date")
        if period.status != PayrollPeriod.Status.OPEN:
            period.status = PayrollPeriod.Status.OPEN
            fields_to_update.append("status")
        if fields_to_update:
            period.save(update_fields=[*fields_to_update, "updated_at"])
        return {
            "period": period,
            "subentity": subentity,
            "entityfinid": entityfinid,
        }

    def _ensure_payroll_setup(self, *, entity: Entity, user: User, scope: dict[str, object]) -> dict[str, object]:
        entityfinid: EntityFinancialYear = scope["entityfinid"]
        subentity: SubEntity = scope["subentity"]
        period: PayrollPeriod = scope["period"]
        subentity_id = subentity.id if subentity else None

        account_type, _ = accounttype.objects.get_or_create(
            entity=entity,
            accounttypecode="PWRE2E",
            defaults={
                "accounttypename": "Playwright Payroll E2E",
                "createdby": user,
            },
        )
        account_head, _ = accountHead.objects.get_or_create(
            entity=entity,
            code=9910,
            defaults={
                "name": "Playwright Payroll E2E",
                "balanceType": "Debit",
                "drcreffect": "Debit",
                "accounttype": account_type,
                "createdby": user,
            },
        )

        expense_account = self._ensure_gl_account(
            entity=entity,
            user=user,
            account_head=account_head,
            account_name="PW Salary Expense",
            account_code=991001,
            party_type="Employee",
        )
        liability_account = self._ensure_gl_account(
            entity=entity,
            user=user,
            account_head=account_head,
            account_name="PW Payroll Liability",
            account_code=991002,
            party_type="Employee",
        )
        payable_account = self._ensure_gl_account(
            entity=entity,
            user=user,
            account_head=account_head,
            account_name="PW Salary Payable",
            account_code=991003,
            party_type="Employee",
        )
        AccountBankDetails.objects.update_or_create(
            account=payable_account,
            isprimary=True,
            defaults={
                "entity": entity,
                "createdby": user,
                "bankname": "HDFC Bank",
                "banKAcno": "123456789012",
                "ifsc": "HDFC0001234",
                "branch": "MG Road",
                "isactive": True,
            },
        )

        component, _ = PayrollComponent.objects.get_or_create(
            entity=entity,
            code="PW_BASIC",
            defaults={
                "name": "Playwright Basic Salary",
                "semantic_code": PayrollComponent.SemanticCode.BASIC_PAY,
                "component_type": PayrollComponent.ComponentType.EARNING,
                "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            },
        )

        structure = (
            SalaryStructure.objects.filter(
                entity=entity,
                entityfinid=entityfinid,
                subentity=subentity,
                code="PW_PAYROLL_E2E",
            )
            .order_by("id")
            .first()
        )
        if structure is None:
            structure = SalaryStructure.objects.create(
                entity=entity,
                entityfinid=entityfinid,
                subentity=subentity,
                code="PW_PAYROLL_E2E",
                name="Playwright Payroll E2E Structure",
                status=SalaryStructure.Status.ACTIVE,
                is_active=True,
            )
        version = structure.current_version
        if version is None:
            version = SalaryStructureVersion.objects.create(
                salary_structure=structure,
                version_no=1,
                effective_from=date(2025, 4, 1),
                status=SalaryStructureVersion.Status.APPROVED,
                calculation_policy_json={
                    "country_code": "IN",
                    "salary_mode": "ctc",
                    "proration_basis": "attendance_days",
                    "rounding_policy": "half_up",
                },
            )
            structure.current_version = version
            structure.save(update_fields=["current_version", "updated_at"])

        SalaryStructureLine.objects.get_or_create(
            salary_structure=structure,
            salary_structure_version=version,
            component=component,
            defaults={
                "sequence": 100,
                "rule_mode": SalaryStructureLine.RuleMode.STANDARD,
                "calculation_basis": SalaryStructureLine.CalculationBasis.FIXED,
                "fixed_amount": Decimal("12000.00"),
                "recurrence_frequency": SalaryStructureLine.RecurrenceFrequency.MONTHLY,
                "compensation_bucket": SalaryStructureLine.CompensationBucket.FIXED_PAY,
                "ctc_treatment": SalaryStructureLine.CTCTreatment.INCLUDED,
                "gross_treatment": SalaryStructureLine.GrossTreatment.INCLUDED,
                "rule_json": {},
            },
        )

        PayrollComponentPosting.objects.get_or_create(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            component=component,
            version_no=1,
            defaults={
                "expense_account": expense_account,
                "liability_account": liability_account,
                "payable_account": payable_account,
                "effective_from": date(2025, 4, 1),
                "is_active": True,
            },
        )

        PayrollLedgerPolicy.objects.update_or_create(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            policy_code="PW_PLAYWRIGHT_LEDGER",
            version_no=1,
            defaults={
                "salary_payable_account": payable_account,
                "payroll_clearing_account": liability_account,
                "employer_contribution_payable_account": liability_account,
                "reimbursement_payable_account": liability_account,
                "is_active": True,
                "effective_from": date(2025, 4, 1),
                "approved_by": user,
                "approved_at": timezone.now(),
                "policy_json": {"seed": self.marker_prefix},
            },
        )

        employee, _ = HrEmployee.objects.get_or_create(
            entity=entity,
            employee_number="PW-E2E-EMP",
            defaults={
                "subentity": subentity,
                "linked_user": user,
                "legal_first_name": "Playwright",
                "legal_last_name": "Payroll",
                "display_name": "Playwright Payroll",
                "work_email": user.email,
                "lifecycle_status": HrEmployee.LifecycleStatus.ACTIVE,
            },
        )
        if employee.linked_user_id != user.id or employee.subentity_id != subentity_id:
            employee.linked_user = user
            employee.subentity = subentity
            employee.work_email = user.email
            employee.lifecycle_status = HrEmployee.LifecycleStatus.ACTIVE
            employee.save(update_fields=["linked_user", "subentity", "work_email", "lifecycle_status", "updated_at"])

        contract, _ = HrEmploymentContract.objects.get_or_create(
            entity=entity,
            employee=employee,
            contract_code="PW-E2E-CONTRACT",
            defaults={
                "subentity": subentity,
                "status": HrEmploymentContract.ContractStatus.ACTIVE,
                "contract_type": HrEmploymentContract.ContractType.PERMANENT,
                "work_model": HrEmploymentContract.WorkModel.ONSITE,
                "compensation_basis": HrEmploymentContract.CompensationBasis.ANNUAL,
                "start_date": date(2025, 4, 1),
                "payroll_effective_from": date(2025, 4, 1),
                "is_payroll_eligible": True,
            },
        )
        if contract.subentity_id != subentity_id or contract.status != HrEmploymentContract.ContractStatus.ACTIVE or not contract.is_payroll_eligible:
            contract.subentity = subentity
            contract.status = HrEmploymentContract.ContractStatus.ACTIVE
            contract.is_payroll_eligible = True
            contract.payroll_effective_from = date(2025, 4, 1)
            contract.save(update_fields=["subentity", "status", "is_payroll_eligible", "payroll_effective_from", "updated_at"])

        profile_seed_email = f"playwright.profile.{entity.id}@example.com"
        profile_seed_employee, _ = HrEmployee.objects.get_or_create(
            entity=entity,
            employee_number="PW-E2E-EMP-PROFILE",
            defaults={
                "subentity": subentity,
                "linked_user": user,
                "legal_first_name": "Playwright",
                "legal_last_name": "Profile",
                "display_name": "Playwright Profile Candidate",
                "work_email": profile_seed_email,
                "lifecycle_status": HrEmployee.LifecycleStatus.ACTIVE,
            },
        )
        if (
            profile_seed_employee.linked_user_id != user.id
            or profile_seed_employee.subentity_id != subentity_id
            or profile_seed_employee.lifecycle_status != HrEmployee.LifecycleStatus.ACTIVE
        ):
            profile_seed_employee.linked_user = user
            profile_seed_employee.subentity = subentity
            profile_seed_employee.work_email = profile_seed_email
            profile_seed_employee.lifecycle_status = HrEmployee.LifecycleStatus.ACTIVE
            profile_seed_employee.save(update_fields=["linked_user", "subentity", "work_email", "lifecycle_status", "updated_at"])

        profile_seed_contract, _ = HrEmploymentContract.objects.get_or_create(
            entity=entity,
            employee=profile_seed_employee,
            contract_code="PW-E2E-CONTRACT-NEW",
            defaults={
                "subentity": subentity,
                "status": HrEmploymentContract.ContractStatus.ACTIVE,
                "contract_type": HrEmploymentContract.ContractType.PERMANENT,
                "work_model": HrEmploymentContract.WorkModel.ONSITE,
                "compensation_basis": HrEmploymentContract.CompensationBasis.ANNUAL,
                "start_date": date(2025, 4, 1),
                "payroll_effective_from": date(2025, 4, 1),
                "is_payroll_eligible": True,
            },
        )
        if (
            profile_seed_contract.subentity_id != subentity_id
            or profile_seed_contract.status != HrEmploymentContract.ContractStatus.ACTIVE
            or not profile_seed_contract.is_payroll_eligible
        ):
            profile_seed_contract.subentity = subentity
            profile_seed_contract.status = HrEmploymentContract.ContractStatus.ACTIVE
            profile_seed_contract.is_payroll_eligible = True
            profile_seed_contract.payroll_effective_from = date(2025, 4, 1)
            profile_seed_contract.save(update_fields=["subentity", "status", "is_payroll_eligible", "payroll_effective_from", "updated_at"])

        ContractPayrollProfile.objects.filter(hrms_contract=profile_seed_contract).delete()

        overlap_seed_email = f"playwright.overlap.{entity.id}@example.com"
        overlap_seed_employee, _ = HrEmployee.objects.get_or_create(
            entity=entity,
            employee_number="PW-E2E-EMP-OVERLAP",
            defaults={
                "subentity": subentity,
                "linked_user": user,
                "legal_first_name": "Playwright",
                "legal_last_name": "Overlap",
                "display_name": "Playwright Overlap Candidate",
                "work_email": overlap_seed_email,
                "lifecycle_status": HrEmployee.LifecycleStatus.ACTIVE,
            },
        )
        if (
            overlap_seed_employee.linked_user_id != user.id
            or overlap_seed_employee.subentity_id != subentity_id
            or overlap_seed_employee.lifecycle_status != HrEmployee.LifecycleStatus.ACTIVE
        ):
            overlap_seed_employee.linked_user = user
            overlap_seed_employee.subentity = subentity
            overlap_seed_employee.work_email = overlap_seed_email
            overlap_seed_employee.lifecycle_status = HrEmployee.LifecycleStatus.ACTIVE
            overlap_seed_employee.save(update_fields=["linked_user", "subentity", "work_email", "lifecycle_status", "updated_at"])

        overlap_seed_contract, _ = HrEmploymentContract.objects.get_or_create(
            entity=entity,
            employee=overlap_seed_employee,
            contract_code="PW-E2E-CONTRACT-OVERLAP",
            defaults={
                "subentity": subentity,
                "status": HrEmploymentContract.ContractStatus.ACTIVE,
                "contract_type": HrEmploymentContract.ContractType.PERMANENT,
                "work_model": HrEmploymentContract.WorkModel.ONSITE,
                "compensation_basis": HrEmploymentContract.CompensationBasis.ANNUAL,
                "start_date": date(2025, 4, 1),
                "payroll_effective_from": date(2025, 4, 1),
                "is_payroll_eligible": True,
            },
        )
        if (
            overlap_seed_contract.subentity_id != subentity_id
            or overlap_seed_contract.status != HrEmploymentContract.ContractStatus.ACTIVE
            or not overlap_seed_contract.is_payroll_eligible
        ):
            overlap_seed_contract.subentity = subentity
            overlap_seed_contract.status = HrEmploymentContract.ContractStatus.ACTIVE
            overlap_seed_contract.is_payroll_eligible = True
            overlap_seed_contract.payroll_effective_from = date(2025, 4, 1)
            overlap_seed_contract.save(update_fields=["subentity", "status", "is_payroll_eligible", "payroll_effective_from", "updated_at"])

        contract_profile, _ = ContractPayrollProfile.objects.get_or_create(
            entity=entity,
            hrms_contract=contract,
            defaults={
                "pay_frequency": "MONTHLY",
                "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
                "bank_account": payable_account,
                "payroll_start_date": date(2025, 4, 1),
                "pf_applicable": False,
                "esi_applicable": False,
                "pt_applicable": False,
                "tds_applicable": False,
                "attendance_required": True,
                "is_active": True,
                "metadata": {"seed": self.marker_prefix},
            },
        )
        contract_profile.payroll_status = ContractPayrollProfile.PayrollStatus.ACTIVE
        contract_profile.bank_account = payable_account
        contract_profile.pay_frequency = "MONTHLY"
        contract_profile.attendance_required = True
        contract_profile.is_active = True
        contract_profile.metadata = {**(contract_profile.metadata or {}), "seed": self.marker_prefix}
        contract_profile.save(
            update_fields=[
                "payroll_status",
                "bank_account",
                "pay_frequency",
                "attendance_required",
                "is_active",
                "metadata",
                "updated_at",
            ]
        )

        overlap_profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": entity,
                "hrms_contract": overlap_seed_contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
                "payment_mode": "BANK_TRANSFER",
                "bank_account": payable_account,
                "payroll_start_date": date(2025, 4, 1),
                "attendance_required": True,
                "is_active": True,
                "metadata": {"seed": self.marker_prefix, "case": "overlap"},
            },
            instance=ContractPayrollProfile.objects.filter(hrms_contract=overlap_seed_contract).first(),
        )

        ContractSalaryStructureAssignment.objects.update_or_create(
            contract_payroll_profile=contract_profile,
            salary_structure=structure,
            salary_structure_version=version,
            effective_from=date(2025, 4, 1),
            defaults={
                "assignment_status": ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
                "ctc_amount": Decimal("144000.00"),
                "gross_amount": Decimal("0.00"),
                "is_active": True,
            },
        )
        overlap_assignment = ContractSalaryStructureAssignment.objects.filter(
            contract_payroll_profile=overlap_profile
        ).order_by("-effective_from", "-id").first()
        if overlap_assignment is None:
            overlap_assignment = ContractSalaryAssignmentService.assign_salary_structure(
                {
                    "contract_payroll_profile": overlap_profile,
                    "salary_structure": structure,
                    "salary_structure_version": version,
                    "effective_from": date(2025, 4, 1),
                    "assignment_status": ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
                    "ctc_amount": "144000.00",
                    "gross_amount": "12000.00",
                    "is_active": True,
                    "metadata": {"seed": self.marker_prefix, "case": "overlap"},
                }
            )

        self._upsert_contract_attendance_summary(
            entity=entity,
            contract_payroll_profile=contract_profile,
            payroll_period=period,
            attendance_days=Decimal("30.00"),
            payable_days=Decimal("30.00"),
            metadata={"seed": self.marker_prefix, "source": "prepare_playwright_payroll_data"},
        )

        self._ensure_policy(
            entity=entity,
            subentity=subentity,
            user=user,
            policy_key=EntityApprovalPolicy.PolicyKey.PAYROLL_RUN,
            code="PW-PAYRUN",
            name="Playwright Payroll Run Approval",
            approver_roles=["payroll_reviewer"],
        )
        self._ensure_policy(
            entity=entity,
            subentity=subentity,
            user=user,
            policy_key=EntityApprovalPolicy.PolicyKey.PAYROLL_POSTING,
            code="PW-POST",
            name="Playwright Payroll Posting Approval",
            approver_roles=["payroll_finance"],
        )
        self._ensure_policy(
            entity=entity,
            subentity=subentity,
            user=user,
            policy_key=EntityApprovalPolicy.PolicyKey.PAYROLL_PAYMENT_HANDOFF,
            code="PW-HANDOFF",
            name="Playwright Payroll Payment Handoff Approval",
            approver_roles=["payroll_finance"],
        )

        return {
            "contract_payroll_profile_id": str(contract_profile.id),
            "new_contract_id": str(profile_seed_contract.id),
            "new_contract_code": profile_seed_contract.contract_code,
            "overlap_contract_profile_id": str(overlap_profile.id),
            "overlap_contract_code": overlap_seed_contract.contract_code,
            "overlap_assignment_id": str(overlap_assignment.id),
            "salary_structure_id": structure.id,
            "salary_structure_version_id": version.id,
            "ledger_policy_code": "PW_PLAYWRIGHT_LEDGER",
            "component_code": component.code,
        }

    def _ensure_run_attendance_prerequisites(self, *, entity: Entity, user: User, scope: dict[str, object]) -> None:
        period: PayrollPeriod = scope["period"]
        subentity: SubEntity = scope["subentity"]
        now = timezone.now()

        monthly_close, _ = AttendanceMonthlyClose.objects.update_or_create(
            entity=entity,
            subentity=subentity,
            payroll_period_code=period.code,
            deleted_at__isnull=True,
            defaults={
                "period_start": period.period_start,
                "period_end": period.period_end,
                "status": AttendanceMonthlyClose.Status.CLOSED,
                "summary_json": {"seed": self.marker_prefix, "source": "prepare_playwright_payroll_data"},
                "submitted_at": now,
                "submitted_by": user,
                "approved_at": now,
                "approved_by": user,
                "closed_at": now,
                "closed_by": user,
                "close_note": f"{self.marker_prefix} seed close for payroll browser runs",
            },
        )

        profiles = (
            ContractPayrollProfile.objects.select_related("hrms_contract")
            .filter(
                entity=entity,
                is_active=True,
                payroll_status=ContractPayrollProfile.PayrollStatus.ACTIVE,
                payroll_start_date__lte=period.period_end,
                hrms_contract__is_payroll_eligible=True,
                hrms_contract__status__in=PayrollRunReadinessResolverService.CONTRACT_READY_STATUSES,
                hrms_contract__payroll_effective_from__lte=period.period_end,
                hrms_contract__subentity=subentity,
            )
            .filter(
                models.Q(payroll_end_date__isnull=True) | models.Q(payroll_end_date__gte=period.period_start),
                models.Q(hrms_contract__end_date__isnull=True) | models.Q(hrms_contract__end_date__gte=period.period_start),
            )
        )
        calendar_days = Decimal(str((period.period_end - period.period_start).days + 1))
        for profile in profiles:
            self._upsert_contract_attendance_summary(
                entity=entity,
                contract_payroll_profile=profile,
                payroll_period=period,
                attendance_days=calendar_days,
                payable_days=calendar_days,
                metadata={"seed": self.marker_prefix, "source": "prepare_playwright_payroll_data"},
            )
            AttendanceApproval.objects.update_or_create(
                entity=entity,
                subentity=subentity,
                contract=profile.hrms_contract,
                payroll_period_code=period.code,
                deleted_at__isnull=True,
                defaults={
                    "period_start": period.period_start,
                    "period_end": period.period_end,
                    "monthly_close": monthly_close,
                    "status": AttendanceApproval.Status.APPROVED,
                    "summary_json": {"seed": self.marker_prefix, "source": "prepare_playwright_payroll_data"},
                    "submitted_at": now,
                    "submitted_by": user,
                    "approved_at": now,
                    "approved_by": user,
                    "review_note": f"{self.marker_prefix} seed approval for payroll browser runs",
                },
            )

    def _upsert_contract_attendance_summary(
        self,
        *,
        entity: Entity,
        contract_payroll_profile: ContractPayrollProfile,
        payroll_period: PayrollPeriod,
        attendance_days: Decimal,
        payable_days: Decimal,
        metadata: dict[str, object],
    ) -> ContractAttendanceSummary:
        defaults = {
            "attendance_days": attendance_days,
            "payable_days": payable_days,
            "lop_days": Decimal("0.00"),
            "weekly_off_days": Decimal("0.00"),
            "holiday_days": Decimal("0.00"),
            "overtime_hours": Decimal("0.00"),
            "late_count": 0,
            "half_days": Decimal("0.00"),
            "source": ContractAttendanceSummary.Source.MANUAL,
            "approval_status": ContractAttendanceSummary.ApprovalStatus.APPROVED,
            "metadata": metadata,
            "is_active": True,
        }
        summary = (
            ContractAttendanceSummary.objects.filter(
                entity=entity,
                contract_payroll_profile=contract_payroll_profile,
                payroll_period=payroll_period,
            )
            .order_by("-is_active", "-updated_at", "-id")
            .first()
        )
        if summary is None:
            return ContractAttendanceSummary.objects.create(
                entity=entity,
                contract_payroll_profile=contract_payroll_profile,
                payroll_period=payroll_period,
                **defaults,
            )

        for field, value in defaults.items():
            setattr(summary, field, value)
        summary.save(update_fields=[*defaults.keys(), "updated_at"])
        return summary

    def _ensure_gl_account(
        self,
        *,
        entity: Entity,
        user: User,
        account_head: accountHead,
        account_name: str,
        account_code: int,
        party_type: str,
    ) -> account:
        existing = account.objects.filter(entity=entity, accountname=account_name).first()
        if existing:
            return existing

        ledger = Ledger.objects.create(
            entity=entity,
            ledger_code=account_code,
            name=account_name,
            accounthead=account_head,
            createdby=user,
            is_party=True,
        )
        created = create_account_with_synced_ledger(
            account_data={
                "entity": entity,
                "ledger": ledger,
                "accountname": account_name,
                "createdby": user,
            },
            ledger_overrides={
                "ledger_code": ledger.ledger_code,
                "accounthead": account_head,
                "is_party": True,
            },
        )
        apply_normalized_profile_payload(created, commercial_data={"partytype": party_type}, createdby=user)
        return created

    def _ensure_policy(
        self,
        *,
        entity: Entity,
        subentity: SubEntity,
        user: User,
        policy_key: str,
        code: str,
        name: str,
        approver_roles: list[str],
    ) -> None:
        policy = (
            EntityApprovalPolicy.objects.filter(entity=entity, code=code)
            .order_by("id")
            .first()
        )
        if policy is None:
            policy = EntityApprovalPolicy(entity=entity, code=code, createdby=user)

        policy.subentity = subentity
        policy.policy_key = policy_key
        policy.name = name
        policy.approval_mode = EntityApprovalPolicy.ApprovalMode.FIXED_USERS
        policy.approver_roles = approver_roles
        policy.min_approvers = 1
        policy.status = EntityApprovalPolicy.Status.ACTIVE
        policy.isactive = True
        policy.save()

    def _stage_runs_and_batches(self, *, entity: Entity, user: User, scope: dict[str, object]) -> dict[str, object]:
        entityfinid: EntityFinancialYear = scope["entityfinid"]
        subentity: SubEntity = scope["subentity"]
        period: PayrollPeriod = scope["period"]

        draft_run = self._create_seeded_run(
            marker="DRAFT",
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            period=period,
            user=user,
        )
        calculated_run = self._create_seeded_run(
            marker="CALCULATED",
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            period=period,
            user=user,
            after_create="calculate",
        )
        submitted_run = self._create_seeded_run(
            marker="SUBMITTED",
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            period=period,
            user=user,
            after_create="submit",
        )
        approved_run = self._create_seeded_run(
            marker="APPROVED",
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            period=period,
            user=user,
            after_create="approve",
        )
        batch_source_run = self._create_seeded_run(
            marker="BATCH_SOURCE",
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            period=period,
            user=user,
            after_create="approve",
        )
        validated_batch_run = self._create_seeded_run(
            marker="BATCH_VALIDATED",
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            period=period,
            user=user,
            after_create="approve",
        )
        approved_batch_run = self._create_seeded_run(
            marker="BATCH_APPROVED",
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            period=period,
            user=user,
            after_create="post",
        )
        exported_batch_run = self._create_seeded_run(
            marker="BATCH_EXPORTED",
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            period=period,
            user=user,
            after_create="post",
        )
        invalid_batch_run = self._create_seeded_run(
            marker="BATCH_INVALID",
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            period=period,
            user=user,
            after_create="approve",
        )

        batch = self._create_seeded_batch(
            run=batch_source_run,
            user=user,
            marker="DRAFT",
        )
        validated_batch = self._create_seeded_batch(
            run=validated_batch_run,
            user=user,
            marker="VALIDATED",
            after_create="validate",
        )
        approved_batch = self._create_seeded_batch(
            run=approved_batch_run,
            user=user,
            marker="APPROVED",
            after_create="approve",
        )
        exported_batch = self._create_seeded_batch(
            run=exported_batch_run,
            user=user,
            marker="EXPORTED",
            after_create="export",
        )
        invalid_validated_batch = self._create_seeded_invalid_validated_batch(
            run=invalid_batch_run,
            user=user,
            marker="INVALID",
        )
        seeded_payslip = self._create_seeded_payslip(run=exported_batch_run, user=user)

        request = self._approval_request_for_run(run=submitted_run)

        return {
            "draft_run_id": draft_run.id,
            "draft_run_number": draft_run.run_number,
            "calculated_run_id": calculated_run.id,
            "calculated_run_number": calculated_run.run_number,
            "submitted_run_id": submitted_run.id,
            "submitted_run_number": submitted_run.run_number,
            "submitted_request_id": request.id if request else None,
            "approved_run_id": approved_run.id,
            "approved_run_number": approved_run.run_number,
            "batch_source_run_id": batch_source_run.id,
            "batch_source_run_number": batch_source_run.run_number,
            "validated_batch_run_id": validated_batch_run.id,
            "validated_batch_run_number": validated_batch_run.run_number,
            "approved_batch_run_id": approved_batch_run.id,
            "approved_batch_run_number": approved_batch_run.run_number,
            "exported_batch_run_id": exported_batch_run.id,
            "exported_batch_run_number": exported_batch_run.run_number,
            "invalid_batch_run_id": invalid_batch_run.id,
            "invalid_batch_run_number": invalid_batch_run.run_number,
            "payment_batch_id": batch.id,
            "payment_batch_name": batch.batch_name,
            "validated_payment_batch_id": validated_batch.id,
            "validated_payment_batch_name": validated_batch.batch_name,
            "approved_payment_batch_id": approved_batch.id,
            "approved_payment_batch_name": approved_batch.batch_name,
            "exported_payment_batch_id": exported_batch.id,
            "exported_payment_batch_name": exported_batch.batch_name,
            "invalid_validated_payment_batch_id": invalid_validated_batch.id,
            "invalid_validated_payment_batch_name": invalid_validated_batch.batch_name,
            "ess_payslip_id": seeded_payslip.id,
            "ess_payslip_number": seeded_payslip.payslip_number,
        }

    def _create_seeded_payslip(self, *, run: PayrollRun, user: User):
        run_employee = run.employee_runs.select_related(
            "contract_payroll_profile__hrms_contract__employee",
            "payroll_run",
        ).prefetch_related("components").order_by("id").first()
        if run_employee is None:
            raise CommandError(f"Unable to build seeded payslip because payroll run {run.id} has no employee rows.")

        payslip = PayslipService.build_for_run_employee(run_employee)
        if payslip.published_at is None or payslip.published_by_id != user.id:
            payslip.published_at = timezone.now()
            payslip.published_by = user
            payslip.save(update_fields=["published_at", "published_by", "updated_at"])
        return payslip

    def _create_seeded_batch(
        self,
        *,
        run: PayrollRun,
        user: User,
        marker: str,
        after_create: str | None = None,
    ) -> PayrollPaymentBatch:
        batch = PayrollPaymentBatchService.create_from_payroll_run(
            run=run,
            user_id=user.id,
            batch_name=f"{self.marker_prefix}-BATCH-{marker}-{timezone.now().strftime('%H%M%S%f')}",
        )
        batch = PayrollPaymentBatch.objects.get(pk=batch.pk)
        if after_create in {"validate", "approve", "export"}:
            batch = PayrollPaymentBatchService.validate_batch(
                batch=batch,
                user_id=user.id,
                comment=f"{self.marker_prefix} validate {marker}",
            )
        if after_create in {"approve", "export"}:
            batch = PayrollPaymentBatchService.approve_batch(
                batch=batch,
                user_id=user.id,
                comment=f"{self.marker_prefix} approve {marker}",
            )
        if after_create == "export":
            batch = PayrollPaymentBatchService.export_batch(
                batch=batch,
                user_id=user.id,
                export_format=batch.export_format,
                comment=f"{self.marker_prefix} export {marker}",
            ).batch
        batch.refresh_from_db()
        return batch

    def _create_seeded_invalid_validated_batch(
        self,
        *,
        run: PayrollRun,
        user: User,
        marker: str,
    ) -> PayrollPaymentBatch:
        batch = PayrollPaymentBatchService.create_from_payroll_run(
            run=run,
            user_id=user.id,
            batch_name=f"{self.marker_prefix}-BATCH-{marker}-{timezone.now().strftime('%H%M%S%f')}",
        )
        line = batch.lines.order_by("sequence", "id").first()
        if line is None:
            raise CommandError(f"Unable to create invalid seeded batch because batch {batch.id} has no lines.")
        line.payment_account = None
        line.account_number = ""
        line.ifsc_code = ""
        line.save(update_fields=["payment_account", "account_number", "ifsc_code", "updated_at"])
        batch = PayrollPaymentBatchService.validate_batch(
            batch=batch,
            user_id=user.id,
            comment=f"{self.marker_prefix} validate {marker}",
        )
        batch.refresh_from_db()
        return batch

    def _create_seeded_run(
        self,
        *,
        marker: str,
        entity: Entity,
        entityfinid: EntityFinancialYear,
        subentity: SubEntity,
        period: PayrollPeriod,
        user: User,
        after_create: str | None = None,
    ) -> PayrollRun:
        result = PayrollRunService.create_run(
            entity_id=entity.id,
            entityfinid_id=entityfinid.id,
            subentity_id=subentity.id if subentity else None,
            payroll_period_id=period.id,
            run_type=PayrollRun.RunType.REGULAR,
            posting_date=period.period_end,
            payout_date=period.payout_date,
            created_by_id=user.id,
        )
        run = result.run
        run.status_comment = f"{self.marker_prefix}:{marker}"
        run.save(update_fields=["status_comment", "updated_at"])

        if after_create in {"calculate", "submit", "approve", "post"}:
            run = PayrollRunService.calculate_run(run).run
        if after_create in {"submit", "approve", "post"}:
            PayrollRunService.submit_run(
                run,
                submitted_by_id=user.id,
                note=f"{self.marker_prefix} submit",
                reason_code="READY",
            )
            run = PayrollRun.objects.get(pk=run.pk)
        if after_create in {"approve", "post"}:
            run = PayrollRunService.approve_run(
                run,
                approved_by_id=user.id,
                note=f"{self.marker_prefix} approve",
            ).run
        if after_create == "post":
            run = PayrollRunService.post_run(
                run,
                posted_by_id=user.id,
            ).run

        run.refresh_from_db()
        return run

    def _approval_request_for_run(self, *, run: PayrollRun):
        from entity.models import ApprovalRequest

        return ApprovalRequest.objects.filter(
            entity_id=run.entity_id,
            workflow_key="payroll_run",
            object_id=str(run.id),
            isactive=True,
        ).order_by("-id").first()
