from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from entity.models import Entity, EntityFinancialYear
from financial.models import account
from payments.models import PaymentMode
from payroll.models import (
    PayrollComponent,
    PayrollLedgerPolicy,
    PayrollAdjustment,
    SalaryStructure,
    SalaryStructureLine,
    SalaryStructureVersion,
)
from rbac.models import Menu, Permission
from rbac.seeding import PayrollRBACSeedService

User = get_user_model()


@dataclass
class SeedSectionResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "notes": self.notes,
        }


class PayrollSeedService:
    SEED_MARKER = "payroll_master_seed"
    TEMPLATE_CODE = "STD_EMPLOYEE_TEMPLATE"
    TEMPLATE_NAME = "Standard Employee Structure"
    LEDGER_POLICY_CODE = "DEFAULT_PAYROLL_LEDGER_POLICY"

    COMPONENT_SPECS = (
        {
            "code": "BASIC",
            "name": "Basic Salary",
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 100,
            "description": "Seeded default payroll earning component.",
        },
        {
            "code": "HRA",
            "name": "House Rent Allowance",
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 110,
            "description": "Seeded default payroll earning component.",
        },
        {
            "code": "SPECIAL_ALLOWANCE",
            "name": "Special Allowance",
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 120,
            "description": "Seeded default payroll earning component.",
        },
        {
            "code": "PF_EMPLOYEE",
            "name": "Provident Fund Employee",
            "component_type": PayrollComponent.ComponentType.DEDUCTION,
            "posting_behavior": PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            "is_taxable": False,
            "is_statutory": True,
            "affects_net_pay": True,
            "default_sequence": 300,
            "description": "Seeded default payroll deduction component.",
        },
        {
            "code": "PF_EMPLOYER",
            "name": "Provident Fund Employer",
            "component_type": PayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION,
            "posting_behavior": PayrollComponent.PostingBehavior.EMPLOYER_LIABILITY,
            "is_taxable": False,
            "is_statutory": True,
            "affects_net_pay": False,
            "default_sequence": 400,
            "description": "Seeded default employer contribution component.",
        },
        {
            "code": "PROFESSIONAL_TAX",
            "name": "Professional Tax",
            "component_type": PayrollComponent.ComponentType.DEDUCTION,
            "posting_behavior": PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            "is_taxable": False,
            "is_statutory": True,
            "affects_net_pay": True,
            "default_sequence": 310,
            "description": "Seeded default payroll deduction component.",
        },
        {
            "code": "TDS",
            "name": "Tax Deducted at Source",
            "component_type": PayrollComponent.ComponentType.DEDUCTION,
            "posting_behavior": PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            "is_taxable": False,
            "is_statutory": True,
            "affects_net_pay": True,
            "default_sequence": 320,
            "description": "Seeded default payroll deduction component.",
        },
    )

    TEMPLATE_LINE_SPECS = (
        {"code": "BASIC", "sequence": 100},
        {"code": "HRA", "sequence": 110},
        {"code": "SPECIAL_ALLOWANCE", "sequence": 120},
        {"code": "PF_EMPLOYEE", "sequence": 300},
        {"code": "PF_EMPLOYER", "sequence": 400},
        {"code": "PROFESSIONAL_TAX", "sequence": 310},
        {"code": "TDS", "sequence": 320},
    )

    PAYMENT_MODE_SPECS = (
        {"paymentmodecode": "BANK_TRANSFER", "paymentmode": "Bank Transfer", "iscash": False},
        {"paymentmodecode": "CASH", "paymentmode": "Cash", "iscash": True},
        {"paymentmodecode": "CHEQUE", "paymentmode": "Cheque", "iscash": False},
    )

    @classmethod
    @transaction.atomic
    def seed_all(cls, *, entity_id: int | None = None) -> dict:
        summary = {
            "adjustment_types": cls.seed_adjustment_types(),
            "payment_modes": cls.seed_payment_modes(),
            "payroll_components": cls.seed_payroll_components(entity_id=entity_id),
            "salary_structure_templates": cls.seed_salary_structure_templates(entity_id=entity_id),
            "ledger_policies": cls.seed_ledger_policies(entity_id=entity_id),
            "readiness_checks": cls.seed_readiness_checks(),
            "rbac_permissions": cls.seed_rbac_permissions(),
            "menu_entries": cls.seed_menu_entries(),
        }
        totals = defaultdict(int)
        for result in summary.values():
            totals["created"] += result["created"]
            totals["updated"] += result["updated"]
            totals["skipped"] += result["skipped"]
        summary["totals"] = dict(totals)
        return summary

    @classmethod
    def seed_adjustment_types(cls) -> dict:
        result = SeedSectionResult()
        result.skipped = len(PayrollAdjustment.Kind.values)
        result.notes.append(
            "Adjustment types are enum-backed by PayrollAdjustment.Kind; no standalone master rows were created."
        )
        return result.as_dict()

    @classmethod
    def seed_payment_modes(cls) -> dict:
        result = SeedSectionResult()
        actor = cls._default_actor()
        if not actor:
            result.skipped = len(cls.PAYMENT_MODE_SPECS)
            result.notes.append("No user exists to attribute PaymentMode.createdby; payment mode seeding skipped.")
            return result.as_dict()

        for row in cls.PAYMENT_MODE_SPECS:
            mode = PaymentMode.objects.filter(paymentmodecode=row["paymentmodecode"]).first()
            if not mode:
                PaymentMode.objects.create(createdby=actor, **row)
                result.created += 1
                continue

            if not cls._is_seeded_metadata(getattr(mode, "paymentmode", "")):
                result.skipped += 1
                result.notes.append(
                    f"Skipped payment mode {row['paymentmodecode']} because it already exists and was not seed-tagged."
                )
                continue

            changed = False
            for field in ("paymentmode", "iscash"):
                if getattr(mode, field) != row[field]:
                    setattr(mode, field, row[field])
                    changed = True
            if changed:
                mode.save(update_fields=["paymentmode", "iscash"])
                result.updated += 1
            else:
                result.skipped += 1
        return result.as_dict()

    @classmethod
    def seed_payroll_components(cls, *, entity_id: int | None = None) -> dict:
        result = SeedSectionResult()
        for entity in cls._active_entities(entity_id=entity_id):
            for spec in cls.COMPONENT_SPECS:
                component = PayrollComponent.objects.filter(entity=entity, code=spec["code"]).first()
                if not component:
                    PayrollComponent.objects.create(
                        entity=entity,
                        **spec,
                        description=cls._seed_text(spec["description"]),
                    )
                    result.created += 1
                    continue

                if not cls._is_seeded_metadata(component.description):
                    result.skipped += 1
                    continue

                changed = False
                for field, value in spec.items():
                    if field == "description":
                        value = cls._seed_text(value)
                    if getattr(component, field) != value:
                        setattr(component, field, value)
                        changed = True
                if changed:
                    component.save()
                    result.updated += 1
                else:
                    result.skipped += 1
        if result.created == 0 and result.updated == 0 and result.skipped == 0:
            result.notes.append("No active entities found for payroll component seeding.")
        return result.as_dict()

    @classmethod
    def seed_salary_structure_templates(cls, *, entity_id: int | None = None) -> dict:
        result = SeedSectionResult()
        actor = cls._default_actor()
        for entity in cls._active_entities(entity_id=entity_id):
            structure = SalaryStructure.objects.filter(
                entity=entity,
                entityfinid__isnull=True,
                subentity__isnull=True,
                code=cls.TEMPLATE_CODE,
            ).first()
            if not structure:
                structure = SalaryStructure.objects.create(
                    entity=entity,
                    code=cls.TEMPLATE_CODE,
                    name=cls.TEMPLATE_NAME,
                    status=SalaryStructure.Status.ACTIVE,
                    notes=cls._seed_text("Seeded default salary structure template."),
                    is_active=True,
                    is_template=True,
                )
                result.created += 1
            elif cls._is_seeded_metadata(structure.notes):
                changed = False
                desired = {
                    "name": cls.TEMPLATE_NAME,
                    "status": SalaryStructure.Status.ACTIVE,
                    "notes": cls._seed_text("Seeded default salary structure template."),
                    "is_active": True,
                    "is_template": True,
                }
                for field, value in desired.items():
                    if getattr(structure, field) != value:
                        setattr(structure, field, value)
                        changed = True
                if changed:
                    structure.save()
                    result.updated += 1
                else:
                    result.skipped += 1
            else:
                result.skipped += 1
                continue

            version, created = SalaryStructureVersion.objects.get_or_create(
                salary_structure=structure,
                version_no=1,
                defaults={
                    "effective_from": timezone.localdate(),
                    "status": SalaryStructureVersion.Status.APPROVED,
                    "approved_by": actor,
                    "approved_at": timezone.now() if actor else None,
                    "notes": cls._seed_text("Seeded default salary structure template version."),
                },
            )
            if created:
                result.created += 1
            else:
                changed = False
                desired_status = SalaryStructureVersion.Status.APPROVED
                desired_notes = cls._seed_text("Seeded default salary structure template version.")
                if version.status != desired_status:
                    version.status = desired_status
                    changed = True
                if version.notes != desired_notes and cls._is_seeded_metadata(version.notes):
                    version.notes = desired_notes
                    changed = True
                if actor and version.approved_by_id is None:
                    version.approved_by = actor
                    version.approved_at = version.approved_at or timezone.now()
                    changed = True
                if changed:
                    version.save()
                    result.updated += 1
                else:
                    result.skipped += 1

            if structure.current_version_id != version.id:
                structure.current_version = version
                structure.save(update_fields=["current_version"])

            component_map = {
                component.code: component
                for component in PayrollComponent.objects.filter(
                    entity=entity,
                    code__in=[row["code"] for row in cls.TEMPLATE_LINE_SPECS],
                )
            }
            for line_spec in cls.TEMPLATE_LINE_SPECS:
                component = component_map.get(line_spec["code"])
                if not component:
                    result.skipped += 1
                    result.notes.append(
                        f"Template line {line_spec['code']} skipped for entity={entity.id} because component is missing."
                    )
                    continue
                line, line_created = SalaryStructureLine.objects.get_or_create(
                    salary_structure=structure,
                    salary_structure_version=version,
                    component=component,
                    defaults={
                        "sequence": line_spec["sequence"],
                        "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT,
                        "rate": Decimal("0.0000"),
                        "fixed_amount": Decimal("0.00"),
                        "is_pro_rated": True,
                        "is_override_allowed": True,
                        "is_active": True,
                    },
                )
                if line_created:
                    result.created += 1
                    continue
                changed = False
                desired_line = {
                    "salary_structure": structure,
                    "salary_structure_version": version,
                    "sequence": line_spec["sequence"],
                    "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT,
                    "is_pro_rated": True,
                    "is_override_allowed": True,
                    "is_active": True,
                }
                for field, value in desired_line.items():
                    current = getattr(line, field)
                    compare_value = value.id if hasattr(value, "id") else value
                    current_value = current.id if hasattr(current, "id") else current
                    if current_value != compare_value:
                        setattr(line, field, value)
                        changed = True
                if changed:
                    line.save()
                    result.updated += 1
                else:
                    result.skipped += 1
        if result.created == 0 and result.updated == 0 and result.skipped == 0:
            result.notes.append("No active entities found for salary structure template seeding.")
        return result.as_dict()

    @classmethod
    def seed_ledger_policies(cls, *, entity_id: int | None = None) -> dict:
        result = SeedSectionResult()
        actor = cls._default_actor()
        for entity in cls._active_entities(entity_id=entity_id):
            salary_payable_account = cls._find_salary_payable_account(entity=entity)
            if not salary_payable_account:
                result.notes.append(
                    f"Skipped ledger policy for entity={entity.id} because no Salary Payable account placeholder was found."
                )
                result.skipped += cls._active_financial_years(entity).count() or 1
                continue
            for entityfinid in cls._active_financial_years(entity):
                policy, created = PayrollLedgerPolicy.objects.get_or_create(
                    entity=entity,
                    entityfinid=entityfinid,
                    subentity=None,
                    policy_code=cls.LEDGER_POLICY_CODE,
                    version_no=1,
                    defaults={
                        "salary_payable_account": salary_payable_account,
                        "is_active": True,
                        "effective_from": timezone.localdate(),
                        "policy_json": {
                            "seed": cls.SEED_MARKER,
                            "note": "Seeded default payroll ledger policy placeholder.",
                        },
                        "approved_by": actor,
                        "approved_at": timezone.now() if actor else None,
                    },
                )
                if created:
                    result.created += 1
                    continue

                if not cls._is_seeded_policy(policy.policy_json):
                    result.skipped += 1
                    continue

                changed = False
                if policy.salary_payable_account_id != salary_payable_account.id:
                    policy.salary_payable_account = salary_payable_account
                    changed = True
                if not policy.is_active:
                    policy.is_active = True
                    changed = True
                desired_policy_json = {
                    **(policy.policy_json or {}),
                    "seed": cls.SEED_MARKER,
                    "note": "Seeded default payroll ledger policy placeholder.",
                }
                if policy.policy_json != desired_policy_json:
                    policy.policy_json = desired_policy_json
                    changed = True
                if actor and policy.approved_by_id is None:
                    policy.approved_by = actor
                    policy.approved_at = policy.approved_at or timezone.now()
                    changed = True
                if changed:
                    policy.save()
                    result.updated += 1
                else:
                    result.skipped += 1
        if result.created == 0 and result.updated == 0 and result.skipped == 0:
            result.notes.append("No active entities found for payroll ledger policy seeding.")
        return result.as_dict()

    @classmethod
    def seed_readiness_checks(cls) -> dict:
        result = SeedSectionResult()
        result.skipped = 4
        result.notes.append(
            "Readiness checks are currently service-driven; no standalone readiness-check master table exists to seed."
        )
        return result.as_dict()

    @classmethod
    def seed_rbac_permissions(cls) -> dict:
        result = SeedSectionResult()
        before_codes = set(
            Permission.objects.filter(code__in=[code for code, *_rest in PayrollRBACSeedService.PERMISSION_SPECS]).values_list(
                "code", flat=True
            )
        )
        catalog = PayrollRBACSeedService.seed_global_catalog()
        result.created = len([code for code in catalog["permissions"] if code not in before_codes])
        result.skipped = len(catalog["permissions"]) - result.created
        result.notes.append("Payroll RBAC permissions ensured via PayrollRBACSeedService global catalog.")
        return result.as_dict()

    @classmethod
    def seed_menu_entries(cls) -> dict:
        result = SeedSectionResult()
        before_codes = set(Menu.objects.filter(code__in=[spec["code"] for spec in PayrollRBACSeedService.MENU_SPECS]).values_list("code", flat=True))
        catalog = PayrollRBACSeedService.seed_global_catalog()
        result.created = len([code for code in catalog["menus"] if code not in before_codes])
        result.skipped = len(catalog["menus"]) - result.created
        result.notes.append("Payroll menu entries ensured via PayrollRBACSeedService global catalog.")
        return result.as_dict()

    @classmethod
    def _active_entities(cls, *, entity_id: int | None = None):
        qs = Entity.objects.filter(isactive=True).order_by("id")
        if entity_id is not None:
            qs = qs.filter(id=entity_id)
        return qs

    @classmethod
    def _active_financial_years(cls, entity: Entity):
        return EntityFinancialYear.objects.filter(entity=entity, isactive=True).order_by("id")

    @classmethod
    def _default_actor(cls):
        actor = User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()
        if actor:
            return actor
        return User.objects.filter(is_active=True).order_by("id").first()

    @classmethod
    def _find_salary_payable_account(cls, *, entity: Entity):
        return (
            account.objects.filter(entity=entity)
            .filter(
                Q(accountname__icontains="salary payable")
                | Q(accountname__icontains="payroll payable")
                | Q(ledger__name__icontains="salary payable")
                | Q(ledger__name__icontains="payroll payable")
            )
            .order_by("id")
            .first()
        )

    @classmethod
    def _seed_text(cls, text: str) -> str:
        return f"{text} [{cls.SEED_MARKER}]"

    @classmethod
    def _is_seeded_metadata(cls, value: str | None) -> bool:
        return cls.SEED_MARKER in (value or "")

    @classmethod
    def _is_seeded_policy(cls, payload: dict | None) -> bool:
        return (payload or {}).get("seed") == cls.SEED_MARKER
