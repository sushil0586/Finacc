from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity, UnitType
from financial.models import Ledger, account, accountHead, accounttype
from financial.services import apply_normalized_profile_payload, create_account_with_synced_ledger
from geography.models import City, Country, District, State
from hrms.models import HrEmployee, HrEmploymentContract
from payroll.models import (
    ContractAttendanceAdjustment,
    ContractAttendanceSummary,
    ContractPayrollInputSnapshot,
    ContractSalaryStructureAssignment,
    ContractTaxDeclaration,
    ContractTaxDeclarationLine,
    PayrollComponent,
    PayrollComponentPosting,
    PayrollLedgerPolicy,
    PayrollPeriod,
    PayrollRun,
    PayrollRunEmployee,
    PayrollRunEmployeeComponent,
    Payslip,
    SalaryStructure,
    SalaryStructureLine,
    SalaryStructureVersion,
)


@dataclass
class LegacyPayrollProfileFixture:
    entity: Entity
    entityfinid: EntityFinancialYear | None
    subentity: SubEntity | None
    employee_user: User | None
    employee_code: str
    full_name: str
    work_email: str
    salary_structure: SalaryStructure
    salary_structure_version: SalaryStructureVersion | None
    ctc_annual: Decimal
    payment_account: account | None
    tax_regime: str
    pay_frequency: str
    extra_data: dict = field(default_factory=dict)
    contract_payroll_profile: object | None = None
    payroll_period: object | None = None
    attendance_summary: object | None = None

    @property
    def employee_user_id(self) -> int | None:
        return getattr(self.employee_user, "id", None)

    @property
    def payment_account_id(self) -> int | None:
        return getattr(self.payment_account, "id", None)

    @property
    def salary_structure_id(self) -> int | None:
        return getattr(self.salary_structure, "id", None)

    @property
    def salary_structure_version_id(self) -> int | None:
        return getattr(self.salary_structure_version, "id", None)

    def save(self, update_fields=None):
        contract_profile = self.contract_payroll_profile
        period = self.payroll_period
        if contract_profile is None:
            return self

        updates: list[str] = []
        if contract_profile.tax_regime != (self.tax_regime or ""):
            contract_profile.tax_regime = self.tax_regime or ""
            updates.append("tax_regime")
        if contract_profile.pay_frequency != (self.pay_frequency or "MONTHLY"):
            contract_profile.pay_frequency = self.pay_frequency or "MONTHLY"
            updates.append("pay_frequency")
        if contract_profile.bank_account_id != self.payment_account_id:
            contract_profile.bank_account = self.payment_account
            updates.append("bank_account")
        if updates:
            updates.append("updated_at")
            contract_profile.save(update_fields=updates)

        extra_data = self.extra_data or {}
        if period is not None and any(
            key in extra_data
            for key in ("attendance_days", "payable_days", "lop_days", "overtime_hours", "late_count", "half_days")
        ):
            from payroll.services import ContractAttendanceSummaryService

            self.attendance_summary = ContractAttendanceSummaryService.create_or_update_summary(
                {
                    "entity": self.entity,
                    "contract_payroll_profile": contract_profile,
                    "payroll_period": period,
                    "attendance_days": str(extra_data.get("attendance_days", "0")),
                    "payable_days": str(extra_data.get("payable_days", "0")),
                    "lop_days": str(extra_data.get("lop_days", "0")),
                    "weekly_off_days": str(extra_data.get("weekly_off_days", "0")),
                    "holiday_days": str(extra_data.get("holiday_days", "0")),
                    "overtime_hours": str(extra_data.get("overtime_hours", "0")),
                    "late_count": int(extra_data.get("late_count", 0) or 0),
                    "half_days": str(extra_data.get("half_days", "0")),
                    "source": "MANUAL",
                    "approval_status": "APPROVED",
                    "is_active": True,
                },
                instance=self.attendance_summary,
            )

        if period is not None and "tax_projection_snapshot" in extra_data:
            from payroll.services import ContractPayrollInputSnapshotService

            existing = ContractPayrollInputSnapshot.objects.filter(
                contract_payroll_profile=contract_profile,
                payroll_period=period,
                input_type=ContractPayrollInputSnapshot.InputType.TAX_PROJECTION,
            ).first()
            ContractPayrollInputSnapshotService.create_or_update_snapshot(
                {
                    "entity": self.entity,
                    "contract_payroll_profile": contract_profile,
                    "payroll_period": period,
                    "input_type": ContractPayrollInputSnapshot.InputType.TAX_PROJECTION,
                    "input_json": extra_data.get("tax_projection_snapshot") or {},
                    "source": ContractPayrollInputSnapshot.SourceType.MANUAL,
                    "effective_from": period.period_start,
                    "is_active": True,
                },
                instance=existing,
            )

        if period is not None and "fixed_salary" in extra_data:
            from payroll.services import ContractPayrollInputSnapshotService

            existing = ContractPayrollInputSnapshot.objects.filter(
                contract_payroll_profile=contract_profile,
                payroll_period=period,
                input_type=ContractPayrollInputSnapshot.InputType.MANUAL_PAYROLL_INPUT,
            ).first()
            ContractPayrollInputSnapshotService.create_or_update_snapshot(
                {
                    "entity": self.entity,
                    "contract_payroll_profile": contract_profile,
                    "payroll_period": period,
                    "input_type": ContractPayrollInputSnapshot.InputType.MANUAL_PAYROLL_INPUT,
                    "input_json": {"fixed_salary": extra_data.get("fixed_salary")},
                    "source": ContractPayrollInputSnapshot.SourceType.MANUAL,
                    "effective_from": period.period_start,
                    "is_active": True,
                },
                instance=existing,
            )
        return self


class PayrollFactory:
    counter = 1

    @classmethod
    def seq(cls, prefix: str) -> str:
        value = f"{prefix}{cls.counter}"
        cls.counter += 1
        return value

    @classmethod
    def next_int(cls, base: int = 1) -> int:
        value = base + cls.counter
        cls.counter += 1
        return value

    @classmethod
    def user(cls, **overrides):
        defaults = {
            "username": cls.seq("payuser"),
            "email": f"{cls.seq('mail')}@example.com",
            "password": "pass123",
        }
        defaults.update(overrides)
        return User.objects.create_user(**defaults)

    @classmethod
    def geography(cls):
        country = Country.objects.create(
            countryname=cls.seq("Country"),
            countrycode=f"{cls.next_int(10)}",
        )
        state = State.objects.create(
            statename=cls.seq("State"),
            statecode=f"{cls.next_int(20)}",
            country=country,
        )
        district = District.objects.create(districtname=f"District {cls.counter}", districtcode=cls.seq("DT"), state=state)
        city = City.objects.create(cityname=f"City {cls.counter}", citycode=cls.seq("CT"), pincode="400001", distt=district)
        return country, state, district, city

    @classmethod
    def entity_scope(cls, *, user=None, name_prefix="Entity"):
        user = user or cls.user()
        country, state, district, city = cls.geography()
        unit_type = UnitType.objects.create(UnitName=cls.seq("Unit"), UnitDesc="Unit")
        gst_type = GstRegistrationType.objects.create(Name=cls.seq("GST"), Description="GST")
        entity = Entity.objects.create(
            entityname=cls.seq(name_prefix),
            legalname=cls.seq(f"{name_prefix} Legal"),
            GstRegitrationType=gst_type,
            createdby=user,
        )
        subentity = SubEntity.objects.create(
            entity=entity,
            subentityname=cls.seq("Branch"),
            branch_type=SubEntity.BranchType.HEAD_OFFICE,
            is_head_office=True,
        )
        fy_start = timezone.make_aware(datetime(2025, 4, 1))
        fy_end = timezone.make_aware(datetime(2026, 3, 31))
        entityfin = EntityFinancialYear.objects.create(
            entity=entity,
            desc=f"{entity.entityname} FY",
            finstartyear=fy_start,
            finendyear=fy_end,
            createdby=user,
        )
        return {
            "user": user,
            "country": country,
            "state": state,
            "district": district,
            "city": city,
            "unit_type": unit_type,
            "gst_type": gst_type,
            "entity": entity,
            "subentity": subentity,
            "entityfinid": entityfin,
        }

    @classmethod
    def accounting_setup(cls, *, entity, user):
        acc_type = accounttype.objects.create(
            entity=entity,
            accounttypename=cls.seq("Type"),
            accounttypecode=cls.seq("T"),
            createdby=user,
        )
        head = accountHead.objects.create(
            entity=entity,
            name=cls.seq("Head"),
            code=100 + cls.counter,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=acc_type,
            createdby=user,
        )
        return {"accounttype": acc_type, "accounthead": head}

    @classmethod
    def gl_account(cls, *, entity, user, accounthead, partytype="Employee", accountname=None, accountcode=None):
        ledger_name = accountname or cls.seq("Ledger")
        ledger_code = accountcode if accountcode is not None else cls.next_int(1000)
        ledger = Ledger.objects.create(
            entity=entity,
            ledger_code=ledger_code,
            name=ledger_name,
            accounthead=accounthead,
            createdby=user,
            is_party=True,
        )
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": entity,
                "ledger": ledger,
                "accountname": ledger_name,
                "createdby": user,
            },
            ledger_overrides={"ledger_code": ledger.ledger_code, "accounthead": accounthead, "is_party": True},
        )
        apply_normalized_profile_payload(acc, commercial_data={"partytype": partytype}, createdby=user)
        return acc

    @classmethod
    def component(
        cls,
        *,
        entity,
        code="BASIC",
        component_type=PayrollComponent.ComponentType.EARNING,
        posting_behavior=PayrollComponent.PostingBehavior.GROSS_EARNING,
        semantic_code=None,
    ):
        return PayrollComponent.objects.create(
            entity=entity,
            code=f"{code}_{cls.counter}",
            name=f"{code} Component",
            semantic_code=semantic_code or PayrollComponent.default_semantic_code_for_code(code),
            component_type=component_type,
            posting_behavior=posting_behavior,
        )

    @classmethod
    def salary_structure(cls, *, entity, entityfinid=None, subentity=None):
        return SalaryStructure.objects.create(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            code=cls.seq("STR"),
            name="Salary Structure",
            status=SalaryStructure.Status.ACTIVE,
            is_active=True,
        )

    @classmethod
    def salary_structure_version(cls, *, salary_structure, version_no=1):
        version = SalaryStructureVersion.objects.create(
            salary_structure=salary_structure,
            version_no=version_no,
            effective_from=datetime(2025, 4, 1).date(),
            status=SalaryStructureVersion.Status.APPROVED,
            calculation_policy_json={
                "country_code": "IN",
                "salary_mode": "ctc",
                "proration_basis": "attendance_days",
                "rounding_policy": "half_up",
            },
        )
        salary_structure.current_version = version
        salary_structure.save(update_fields=["current_version"])
        return version

    @classmethod
    def salary_structure_line(
        cls,
        *,
        salary_structure,
        salary_structure_version,
        component,
        fixed_amount="1000.00",
        sequence=100,
        rule_mode=SalaryStructureLine.RuleMode.STANDARD,
        recurrence_frequency=SalaryStructureLine.RecurrenceFrequency.MONTHLY,
        compensation_bucket=SalaryStructureLine.CompensationBucket.FIXED_PAY,
        ctc_treatment=SalaryStructureLine.CTCTreatment.INCLUDED,
        gross_treatment=SalaryStructureLine.GrossTreatment.INCLUDED,
        rule_json=None,
    ):
        return SalaryStructureLine.objects.create(
            salary_structure=salary_structure,
            salary_structure_version=salary_structure_version,
            component=component,
            sequence=sequence,
            rule_mode=rule_mode,
            calculation_basis=SalaryStructureLine.CalculationBasis.FIXED,
            fixed_amount=Decimal(fixed_amount),
            recurrence_frequency=recurrence_frequency,
            compensation_bucket=compensation_bucket,
            ctc_treatment=ctc_treatment,
            gross_treatment=gross_treatment,
            rule_json=rule_json,
        )

    @classmethod
    def employee_profile(
        cls,
        *,
        entity,
        subentity,
        payment_account,
        salary_structure,
        salary_structure_version,
        entityfinid=None,
        employee_code=None,
        employee_user=None,
    ):
        return LegacyPayrollProfileFixture(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            employee_user=employee_user,
            employee_code=employee_code or cls.seq("EMP"),
            full_name="Payroll Employee",
            work_email=f"{cls.seq('emp')}@example.com",
            salary_structure=salary_structure,
            salary_structure_version=salary_structure_version,
            ctc_annual=Decimal("120000.00"),
            payment_account=payment_account,
            tax_regime="",
            pay_frequency="MONTHLY",
            extra_data={},
        )

    @classmethod
    def hrms_employee(cls, *, entity, subentity=None, user=None, employee_number=None):
        return HrEmployee.objects.create(
            entity=entity,
            subentity=subentity,
            linked_user=user,
            employee_number=employee_number or cls.seq("HEMP"),
            legal_first_name="Bridge",
            legal_last_name="Employee",
            display_name="Bridge Employee",
            work_email=f"{cls.seq('hrmsemp')}@example.com",
            lifecycle_status=HrEmployee.LifecycleStatus.ACTIVE,
        )

    @classmethod
    def hrms_contract(
        cls,
        *,
        entity,
        subentity=None,
        employee=None,
        contract_code=None,
        status=HrEmploymentContract.ContractStatus.ACTIVE,
        is_payroll_eligible=True,
    ):
        employee = employee or cls.hrms_employee(entity=entity, subentity=subentity)
        return HrEmploymentContract.objects.create(
            entity=entity,
            subentity=subentity,
            employee=employee,
            contract_code=contract_code or cls.seq("HCON"),
            status=status,
            contract_type=HrEmploymentContract.ContractType.PERMANENT,
            work_model=HrEmploymentContract.WorkModel.ONSITE,
            compensation_basis=HrEmploymentContract.CompensationBasis.ANNUAL,
            start_date=datetime(2025, 4, 1).date(),
            payroll_effective_from=datetime(2025, 4, 1).date(),
            is_payroll_eligible=is_payroll_eligible,
        )

    @classmethod
    def contract_payroll_profile(
        cls,
        *,
        entity,
        hrms_contract=None,
        pay_frequency="MONTHLY",
        payroll_status="ACTIVE",
        tax_regime="",
        payment_mode="",
        bank_account=None,
        payroll_start_date=None,
        is_active=True,
        **overrides,
    ):
        hrms_contract = hrms_contract or cls.hrms_contract(entity=entity, subentity=getattr(entity, "subentity", None))
        defaults = {
            "entity": entity,
            "hrms_contract": hrms_contract,
            "pay_frequency": pay_frequency,
            "payroll_status": payroll_status,
            "tax_regime": tax_regime,
            "payment_mode": payment_mode,
            "bank_account": bank_account,
            "payroll_start_date": payroll_start_date or datetime(2025, 4, 1).date(),
            "is_active": is_active,
        }
        defaults.update(overrides)
        return PayrollFactory._create_contract_payroll_profile(**defaults)

    @staticmethod
    def _create_contract_payroll_profile(**kwargs):
        from payroll.models import ContractPayrollProfile

        return ContractPayrollProfile.objects.create(**kwargs)

    @classmethod
    def contract_attendance_summary(
        cls,
        *,
        entity,
        contract_payroll_profile,
        payroll_period,
        attendance_days="26.00",
        payable_days="26.00",
        lop_days="0.00",
        weekly_off_days="4.00",
        holiday_days="0.00",
        overtime_hours="0.00",
        late_count=0,
        half_days="0.00",
        source=ContractAttendanceSummary.Source.MANUAL,
        approval_status=ContractAttendanceSummary.ApprovalStatus.DRAFT,
        is_active=True,
        **overrides,
    ):
        defaults = {
            "entity": entity,
            "contract_payroll_profile": contract_payroll_profile,
            "payroll_period": payroll_period,
            "attendance_days": Decimal(attendance_days),
            "payable_days": Decimal(payable_days),
            "lop_days": Decimal(lop_days),
            "weekly_off_days": Decimal(weekly_off_days),
            "holiday_days": Decimal(holiday_days),
            "overtime_hours": Decimal(overtime_hours),
            "late_count": late_count,
            "half_days": Decimal(half_days),
            "source": source,
            "approval_status": approval_status,
            "is_active": is_active,
        }
        defaults.update(overrides)
        return ContractAttendanceSummary.objects.create(**defaults)

    @classmethod
    def contract_attendance_adjustment(
        cls,
        *,
        entity,
        contract_payroll_profile,
        payroll_period,
        adjustment_type=ContractAttendanceAdjustment.AdjustmentType.PAYABLE_DAY,
        adjustment_value="1.00",
        approval_status=ContractAttendanceAdjustment.ApprovalStatus.DRAFT,
        remarks="",
        is_active=True,
        **overrides,
    ):
        defaults = {
            "entity": entity,
            "contract_payroll_profile": contract_payroll_profile,
            "payroll_period": payroll_period,
            "adjustment_type": adjustment_type,
            "adjustment_value": Decimal(adjustment_value),
            "approval_status": approval_status,
            "remarks": remarks,
            "is_active": is_active,
        }
        defaults.update(overrides)
        return ContractAttendanceAdjustment.objects.create(**defaults)

    @classmethod
    def contract_input_snapshot(
        cls,
        *,
        entity,
        contract_payroll_profile,
        input_type,
        payroll_period=None,
        input_json=None,
        source=ContractPayrollInputSnapshot.SourceType.MANUAL,
        effective_from=None,
        effective_to=None,
        is_active=True,
        **overrides,
    ):
        defaults = {
            "entity": entity,
            "contract_payroll_profile": contract_payroll_profile,
            "payroll_period": payroll_period,
            "input_type": input_type,
            "input_json": input_json or {},
            "source": source,
            "effective_from": effective_from or datetime(2025, 4, 1).date(),
            "effective_to": effective_to,
            "is_active": is_active,
        }
        defaults.update(overrides)
        return ContractPayrollInputSnapshot.objects.create(**defaults)

    @classmethod
    def contract_tax_declaration(
        cls,
        *,
        entity,
        contract_payroll_profile,
        financial_year,
        tax_regime=ContractTaxDeclaration.TaxRegime.OLD,
        declaration_status=ContractTaxDeclaration.DeclarationStatus.APPROVED,
        approval_status=None,
        declared_annual_income="0.00",
        previous_employer_income="0.00",
        previous_employer_tds="0.00",
        standard_deduction_amount="50000.00",
        professional_tax_declared="0.00",
        is_active=True,
        **overrides,
    ):
        if approval_status is None:
            approval_status = {
                ContractTaxDeclaration.DeclarationStatus.APPROVED: ContractTaxDeclaration.ApprovalStatus.APPROVED,
                ContractTaxDeclaration.DeclarationStatus.REJECTED: ContractTaxDeclaration.ApprovalStatus.REJECTED,
                ContractTaxDeclaration.DeclarationStatus.SUBMITTED: ContractTaxDeclaration.ApprovalStatus.PENDING_APPROVAL,
            }.get(declaration_status, ContractTaxDeclaration.ApprovalStatus.DRAFT)
        defaults = {
            "entity": entity,
            "contract_payroll_profile": contract_payroll_profile,
            "financial_year": financial_year,
            "tax_regime": tax_regime,
            "declaration_status": declaration_status,
            "approval_status": approval_status,
            "declared_annual_income": Decimal(declared_annual_income),
            "previous_employer_income": Decimal(previous_employer_income),
            "previous_employer_tds": Decimal(previous_employer_tds),
            "standard_deduction_amount": Decimal(standard_deduction_amount),
            "professional_tax_declared": Decimal(professional_tax_declared),
            "is_active": is_active,
        }
        defaults.update(overrides)
        return ContractTaxDeclaration.objects.create(**defaults)

    @classmethod
    def contract_tax_declaration_line(
        cls,
        *,
        declaration,
        section_code=ContractTaxDeclarationLine.SectionCode.OTHER,
        description="",
        declared_amount="0.00",
        approved_amount="0.00",
        evidence_required=False,
        evidence_status=ContractTaxDeclarationLine.EvidenceStatus.PENDING,
        metadata=None,
        is_active=True,
        **overrides,
    ):
        defaults = {
            "declaration": declaration,
            "section_code": section_code,
            "description": description,
            "declared_amount": Decimal(declared_amount),
            "approved_amount": Decimal(approved_amount),
            "evidence_required": evidence_required,
            "evidence_status": evidence_status,
            "metadata": metadata or {},
            "is_active": is_active,
        }
        defaults.update(overrides)
        return ContractTaxDeclarationLine.objects.create(**defaults)

    @classmethod
    def component_posting(
        cls,
        *,
        entity,
        entityfinid,
        subentity,
        component,
        expense_account,
        liability_account,
        payable_account,
        version_no=1,
    ):
        return PayrollComponentPosting.objects.create(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            component=component,
            expense_account=expense_account,
            liability_account=liability_account,
            payable_account=payable_account,
            version_no=version_no,
            effective_from=datetime(2025, 4, 1).date(),
            is_active=True,
        )

    @classmethod
    def ledger_policy(cls, *, entity, entityfinid, subentity, salary_payable_account, payroll_clearing_account=None):
        return PayrollLedgerPolicy.objects.create(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            salary_payable_account=salary_payable_account,
            payroll_clearing_account=payroll_clearing_account,
            version_no=1,
            effective_from=datetime(2025, 4, 1).date(),
            is_active=True,
        )

    @classmethod
    def payroll_period(cls, *, entity, entityfinid, subentity, code="APR-2025", status=PayrollPeriod.Status.OPEN):
        return PayrollPeriod.objects.create(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            code=f"{code}-{cls.counter}",
            period_start=datetime(2025, 4, 1).date(),
            period_end=datetime(2025, 4, 30).date(),
            payout_date=datetime(2025, 5, 1).date(),
            status=status,
        )

    @classmethod
    def payroll_run(cls, *, entity, entityfinid, subentity, payroll_period, **overrides):
        defaults = {
            "entity": entity,
            "entityfinid": entityfinid,
            "subentity": subentity,
            "payroll_period": payroll_period,
            "run_type": PayrollRun.RunType.REGULAR,
            "doc_code": "PRUN",
            "posting_date": payroll_period.period_end,
            "status": PayrollRun.Status.DRAFT,
            "payment_status": PayrollRun.PaymentStatus.NOT_READY,
        }
        defaults.update(overrides)
        return PayrollRun.objects.create(**defaults)

    @classmethod
    def payroll_run_employee(cls, *, payroll_run, employee_profile=None, salary_structure, salary_structure_version, ledger_policy_version, **overrides):
        contract_payroll_profile = overrides.pop("contract_payroll_profile", None)
        if contract_payroll_profile is None and employee_profile is not None:
            contract_payroll_profile = getattr(employee_profile, "contract_payroll_profile", None)
        if contract_payroll_profile is None:
            assignment = ContractSalaryStructureAssignment.objects.filter(
                salary_structure=salary_structure,
                salary_structure_version=salary_structure_version,
                contract_payroll_profile__entity_id=payroll_run.entity_id,
            ).select_related("contract_payroll_profile").first()
            contract_payroll_profile = getattr(assignment, "contract_payroll_profile", None)
        defaults = {
            "payroll_run": payroll_run,
            "contract_payroll_profile": contract_payroll_profile,
            "salary_structure": salary_structure,
            "salary_structure_version": salary_structure_version,
            "ledger_policy_version": ledger_policy_version,
            "gross_amount": Decimal("1000.00"),
            "deduction_amount": Decimal("100.00"),
            "employer_contribution_amount": Decimal("0.00"),
            "reimbursement_amount": Decimal("0.00"),
            "payable_amount": Decimal("900.00"),
        }
        defaults.update(overrides)
        return PayrollRunEmployee.objects.create(**defaults)

    @classmethod
    def payroll_run_component(cls, *, payroll_run_employee, component, component_posting_version=None, source_structure_line=None, amount="1000.00", sequence=100):
        return PayrollRunEmployeeComponent.objects.create(
            payroll_run_employee=payroll_run_employee,
            component=component,
            component_code=component.code,
            component_name=component.name,
            component_type=component.component_type,
            posting_behavior=component.posting_behavior,
            component_posting_version=component_posting_version,
            source_structure_line=source_structure_line,
            amount=Decimal(amount),
            taxable_amount=Decimal(amount),
            sequence=sequence,
        )

    @classmethod
    def payslip(cls, *, payroll_run_employee):
        return Payslip.objects.create(
            payroll_run_employee=payroll_run_employee,
            payslip_number=cls.seq("PSL"),
            payload={"ok": True},
        )

    @classmethod
    def full_payroll_setup(cls):
        scope = cls.entity_scope()
        accounting = cls.accounting_setup(entity=scope["entity"], user=scope["user"])
        expense = cls.gl_account(entity=scope["entity"], user=scope["user"], accounthead=accounting["accounthead"], accountname="Salary Expense")
        liability = cls.gl_account(entity=scope["entity"], user=scope["user"], accounthead=accounting["accounthead"], accountname="Payroll Liability")
        payable = cls.gl_account(entity=scope["entity"], user=scope["user"], accounthead=accounting["accounthead"], accountname="Salary Payable")
        component = cls.component(entity=scope["entity"])
        structure = cls.salary_structure(entity=scope["entity"], entityfinid=scope["entityfinid"], subentity=scope["subentity"])
        version = cls.salary_structure_version(salary_structure=structure)
        line = cls.salary_structure_line(
            salary_structure=structure,
            salary_structure_version=version,
            component=component,
        )
        component_posting = cls.component_posting(
            entity=scope["entity"],
            entityfinid=scope["entityfinid"],
            subentity=scope["subentity"],
            component=component,
            expense_account=expense,
            liability_account=liability,
            payable_account=payable,
        )
        policy = cls.ledger_policy(
            entity=scope["entity"],
            entityfinid=scope["entityfinid"],
            subentity=scope["subentity"],
            salary_payable_account=payable,
        )
        profile = cls.employee_profile(
            entity=scope["entity"],
            entityfinid=scope["entityfinid"],
            subentity=scope["subentity"],
            payment_account=payable,
            salary_structure=structure,
            salary_structure_version=version,
            employee_user=scope["user"],
        )
        hrms_employee = cls.hrms_employee(
            entity=scope["entity"],
            subentity=scope["subentity"],
            user=scope["user"],
        )
        hrms_contract = cls.hrms_contract(
            entity=scope["entity"],
            subentity=scope["subentity"],
            employee=hrms_employee,
        )
        contract_profile = cls.contract_payroll_profile(
            entity=scope["entity"],
            hrms_contract=hrms_contract,
            pay_frequency=profile.pay_frequency,
            tax_regime=profile.tax_regime,
            bank_account=profile.payment_account,
            payroll_status="ACTIVE",
            payroll_start_date=datetime(2025, 4, 1).date(),
            pf_applicable=True,
            tds_applicable=True,
        )
        assignment = ContractSalaryStructureAssignment.objects.create(
            contract_payroll_profile=contract_profile,
            salary_structure=structure,
            salary_structure_version=version,
            effective_from=datetime(2025, 4, 1).date(),
            assignment_status=ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
            ctc_amount=Decimal("10000.00"),
            gross_amount=Decimal("0.00"),
            is_active=True,
        )
        period = cls.payroll_period(entity=scope["entity"], entityfinid=scope["entityfinid"], subentity=scope["subentity"])
        attendance_summary = cls.contract_attendance_summary(
            entity=scope["entity"],
            contract_payroll_profile=contract_profile,
            payroll_period=period,
            attendance_days="30.00",
            payable_days="30.00",
            lop_days="0.00",
            weekly_off_days="0.00",
            holiday_days="0.00",
            overtime_hours="0.00",
            late_count=0,
            half_days="0.00",
            approval_status=ContractAttendanceSummary.ApprovalStatus.APPROVED,
            is_active=True,
        )
        profile.contract_payroll_profile = contract_profile
        profile.payroll_period = period
        profile.attendance_summary = attendance_summary
        return {
            **scope,
            **accounting,
            "expense_account": expense,
            "liability_account": liability,
            "payable_account": payable,
            "component": component,
            "structure": structure,
            "version": version,
            "line": line,
            "component_posting": component_posting,
            "ledger_policy": policy,
            "profile": profile,
            "hrms_employee": hrms_employee,
            "hrms_contract": hrms_contract,
            "contract_profile": contract_profile,
            "salary_assignment": assignment,
            "period": period,
            "attendance_summary": attendance_summary,
        }

    @staticmethod
    def legacy_snapshot_payload(**overrides):
        payload = {
            "employee_count": 1,
            "gross_amount": "1000.00",
            "deduction_amount": "100.00",
            "net_pay_amount": "900.00",
            "component_totals": {"BASIC_1": "1000.00"},
        }
        payload.update(overrides)
        return payload
