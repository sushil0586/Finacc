from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity, UnitType
from financial.models import Ledger, account, accountHead, accounttype
from geography.models import City, Country, District, State
from payroll.models import (
    PayrollComponent,
    PayrollComponentPosting,
    PayrollEmployeeProfile,
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
            unitType=unit_type,
            GstRegitrationType=gst_type,
            address="Address",
            phoneoffice="9999999999",
            phoneresidence="9999999998",
            country=country,
            state=state,
            district=district,
            city=city,
            createdby=user,
        )
        subentity = SubEntity.objects.create(entity=entity, subentityname=cls.seq("Branch"), address="Branch")
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
        return account.objects.create(
            entity=entity,
            ledger=ledger,
            accounthead=accounthead,
            accountname=ledger_name,
            accountcode=ledger.ledger_code,
            partytype=partytype,
            createdby=user,
        )

    @classmethod
    def component(cls, *, entity, code="BASIC", component_type=PayrollComponent.ComponentType.EARNING, posting_behavior=PayrollComponent.PostingBehavior.GROSS_EARNING):
        return PayrollComponent.objects.create(
            entity=entity,
            code=f"{code}_{cls.counter}",
            name=f"{code} Component",
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
        )
        salary_structure.current_version = version
        salary_structure.save(update_fields=["current_version"])
        return version

    @classmethod
    def salary_structure_line(cls, *, salary_structure, salary_structure_version, component, fixed_amount="1000.00", sequence=100):
        return SalaryStructureLine.objects.create(
            salary_structure=salary_structure,
            salary_structure_version=salary_structure_version,
            component=component,
            sequence=sequence,
            calculation_basis=SalaryStructureLine.CalculationBasis.FIXED,
            fixed_amount=Decimal(fixed_amount),
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
    ):
        return PayrollEmployeeProfile.objects.create(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            employee_code=employee_code or cls.seq("EMP"),
            full_name="Payroll Employee",
            work_email=f"{cls.seq('emp')}@example.com",
            date_of_joining=timezone.localdate(),
            salary_structure=salary_structure,
            salary_structure_version=salary_structure_version,
            ctc_annual=Decimal("120000.00"),
            payment_account=payment_account,
            status=PayrollEmployeeProfile.Status.ACTIVE,
        )

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
    def payroll_run_employee(cls, *, payroll_run, employee_profile, salary_structure, salary_structure_version, ledger_policy_version, **overrides):
        defaults = {
            "payroll_run": payroll_run,
            "employee_profile": employee_profile,
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
        )
        period = cls.payroll_period(entity=scope["entity"], entityfinid=scope["entityfinid"], subentity=scope["subentity"])
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
            "period": period,
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
