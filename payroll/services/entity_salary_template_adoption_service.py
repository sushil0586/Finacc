from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from entity.models import Entity, EntityFinancialYear, SubEntity
from payroll.models import (
    GlobalPayrollComponent,
    GlobalSalaryStructureTemplate,
    PayrollComponent,
    SalaryStructure,
    SalaryStructureLine,
    SalaryStructureVersion,
)


@dataclass
class EntityTemplateAdoptionSummary:
    dry_run: bool
    adopted: bool = False
    created_components: list[dict[str, Any]] = field(default_factory=list)
    reused_components: list[dict[str, Any]] = field(default_factory=list)
    created_structure: dict[str, Any] | None = None
    created_version: dict[str, Any] | None = None
    created_lines: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "adopted": self.adopted,
            "created_components": self.created_components,
            "reused_components": self.reused_components,
            "created_structure": self.created_structure,
            "created_version": self.created_version,
            "created_lines": self.created_lines,
            "warnings": self.warnings,
            "conflicts": self.conflicts,
        }


class EntitySalaryTemplateAdoptionService:
    COMPONENT_POSTING_BEHAVIOR = {
        GlobalPayrollComponent.ComponentType.EARNING: PayrollComponent.PostingBehavior.GROSS_EARNING,
        GlobalPayrollComponent.ComponentType.DEDUCTION: PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
        GlobalPayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION: PayrollComponent.PostingBehavior.EMPLOYER_LIABILITY,
        GlobalPayrollComponent.ComponentType.REIMBURSEMENT: PayrollComponent.PostingBehavior.REIMBURSEMENT,
        GlobalPayrollComponent.ComponentType.RECOVERY: PayrollComponent.PostingBehavior.RECOVERY,
        GlobalPayrollComponent.ComponentType.INFORMATIONAL: PayrollComponent.PostingBehavior.MEMO_ONLY,
    }

    @classmethod
    def adopt(
        cls,
        *,
        entity_id: int,
        global_template_id,
        effective_from,
        subentity_id: int | None = None,
        entity_financial_year_id: int | None = None,
        structure_name_override: str | None = None,
        structure_code_override: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        entity = Entity.objects.get(pk=entity_id)
        template = GlobalSalaryStructureTemplate.objects.prefetch_related("lines__component", "lines__component__group").get(
            pk=global_template_id
        )
        entityfinid = cls._load_entity_financial_year(entity, entity_financial_year_id)
        subentity = cls._load_subentity(entity, subentity_id)
        summary = cls._build_plan(
            entity=entity,
            template=template,
            effective_from=effective_from,
            entityfinid=entityfinid,
            subentity=subentity,
            structure_name_override=structure_name_override,
            structure_code_override=structure_code_override,
            dry_run=dry_run,
        )
        if dry_run or summary.conflicts:
            return summary.as_dict()

        return cls._execute_plan(
            summary=summary,
            entity=entity,
            template=template,
            effective_from=effective_from,
            entityfinid=entityfinid,
            subentity=subentity,
            structure_name_override=structure_name_override,
            structure_code_override=structure_code_override,
        )

    @staticmethod
    def _load_entity_financial_year(entity: Entity, entity_financial_year_id: int | None):
        if not entity_financial_year_id:
            return None
        return EntityFinancialYear.objects.get(pk=entity_financial_year_id, entity=entity)

    @staticmethod
    def _load_subentity(entity: Entity, subentity_id: int | None):
        if not subentity_id:
            return None
        return SubEntity.objects.get(pk=subentity_id, entity=entity)

    @classmethod
    def _build_plan(
        cls,
        *,
        entity,
        template,
        effective_from,
        entityfinid,
        subentity,
        structure_name_override,
        structure_code_override,
        dry_run: bool,
    ) -> EntityTemplateAdoptionSummary:
        summary = EntityTemplateAdoptionSummary(dry_run=dry_run)
        structure_code = (structure_code_override or template.code).strip()
        structure_name = (structure_name_override or template.name).strip()

        if not structure_code:
            summary.conflicts.append("Structure code is required.")
        if not structure_name:
            summary.conflicts.append("Structure name is required.")
        if not template.is_active:
            summary.conflicts.append("Inactive global template cannot be adopted.")
        if template.effective_to and template.effective_to < effective_from:
            summary.conflicts.append("Adoption effective date cannot be later than the template effective end date.")

        structure_exists = SalaryStructure.objects.filter(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            code=structure_code,
        ).exists()
        if structure_exists:
            summary.conflicts.append(f"Salary structure {structure_code} already exists for this scope.")

        existing_components = {
            component.code: component
            for component in PayrollComponent.objects.filter(entity=entity)
        }
        template_lines = list(template.lines.select_related("component").order_by("sequence", "id"))
        component_lookup: dict[str, PayrollComponent] = {}
        planned_new_components: dict[str, GlobalPayrollComponent] = {}

        for line in template_lines:
            global_component = line.component
            if global_component is None:
                summary.conflicts.append(f"Template line {line.id} is missing its global component reference.")
                continue
            if not global_component.is_active:
                summary.conflicts.append(f"Global component {global_component.code} is inactive and cannot be adopted.")
                continue

            existing = existing_components.get(global_component.code)
            if existing is not None:
                component_lookup[global_component.code] = existing
                summary.reused_components.append(
                    {
                        "id": existing.id,
                        "code": existing.code,
                        "name": existing.name,
                        "is_active": existing.is_active,
                    }
                )
                if existing.component_type != global_component.component_type:
                    summary.conflicts.append(
                        f"Component {existing.code} already exists for the entity with a different component type."
                    )
                if not existing.is_active:
                    summary.warnings.append(
                        f"Existing component {existing.code} is inactive and will be reused as-is."
                    )
                continue

            planned_new_components[global_component.code] = global_component
            summary.created_components.append(
                {
                    "code": global_component.code,
                    "name": global_component.name,
                    "component_type": global_component.component_type,
                    "would_create": True,
                }
            )

        for line in template_lines:
            basis_codes = list(line.basis_components or [])
            for code in basis_codes:
                if code not in component_lookup and code not in planned_new_components:
                    summary.conflicts.append(
                        f"Template line {line.component.code} references missing basis component {code}."
                    )

        summary.created_structure = {
            "code": structure_code,
            "name": structure_name,
            "would_create": not bool(summary.conflicts),
        }
        summary.created_version = {
            "version_no": 1,
            "effective_from": effective_from.isoformat(),
            "would_create": not bool(summary.conflicts),
        }

        for line in template_lines:
            summary.created_lines.append(
                {
                    "component_code": line.component.code,
                    "sequence": line.sequence,
                    "calculation_type": line.calculation_type,
                    "would_create": not bool(summary.conflicts),
                }
            )

        return summary

    @classmethod
    @transaction.atomic
    def _execute_plan(
        cls,
        *,
        summary: EntityTemplateAdoptionSummary,
        entity,
        template,
        effective_from,
        entityfinid,
        subentity,
        structure_name_override,
        structure_code_override,
    ) -> dict[str, Any]:
        created_components: list[dict[str, Any]] = []
        reused_components: list[dict[str, Any]] = []
        template_lines = list(template.lines.select_related("component").order_by("sequence", "id"))
        component_lookup: dict[str, PayrollComponent] = {}

        existing_components = {
            component.code: component
            for component in PayrollComponent.objects.filter(entity=entity)
        }

        for line in template_lines:
            global_component = line.component
            existing = existing_components.get(global_component.code)
            if existing is not None:
                component_lookup[global_component.code] = existing
                reused_components.append(
                    {
                        "id": existing.id,
                        "code": existing.code,
                        "name": existing.name,
                        "is_active": existing.is_active,
                    }
                )
                continue

            component = PayrollComponent.objects.create(
                entity=entity,
                code=global_component.code,
                name=global_component.name,
                component_type=global_component.component_type,
                posting_behavior=cls.COMPONENT_POSTING_BEHAVIOR[global_component.component_type],
                is_taxable=global_component.taxable,
                is_statutory=bool(global_component.statutory_code),
                affects_net_pay=global_component.affects_net,
                is_active=global_component.is_active,
                default_sequence=global_component.default_sequence,
                description=global_component.description,
                country_code=global_component.country_code,
                state_code=global_component.state_code,
                statutory_tag=global_component.statutory_code or "",
            )
            component_lookup[global_component.code] = component
            created_components.append(
                {
                    "id": component.id,
                    "code": component.code,
                    "name": component.name,
                    "component_type": component.component_type,
                }
            )

        structure = SalaryStructure.objects.create(
            entity=entity,
            entityfinid=entityfinid,
            subentity=subentity,
            code=(structure_code_override or template.code).strip(),
            name=(structure_name_override or template.name).strip(),
            status=SalaryStructure.Status.ACTIVE,
            notes=f"Adopted from global salary template {template.code}.",
            is_active=True,
            is_template=False,
        )
        version = SalaryStructureVersion.objects.create(
            salary_structure=structure,
            version_no=1,
            effective_from=effective_from,
            status=SalaryStructureVersion.Status.APPROVED,
            calculation_policy_json={
                "source_template": {
                    "id": str(template.id),
                    "code": template.code,
                    "name": template.name,
                    "template_type": template.template_type,
                },
                "country_code": template.country_code,
                "state_code": template.state_code,
                "pay_frequency": template.pay_frequency,
                "adopted_at": timezone.now().isoformat(),
            },
            notes=f"Adopted from global salary template {template.code}.",
        )

        created_lines: list[dict[str, Any]] = []
        for line in template_lines:
            adopted_line = cls._create_salary_structure_line(
                structure=structure,
                version=version,
                template_line=line,
                component_lookup=component_lookup,
            )
            created_lines.append(
                {
                    "id": adopted_line.id,
                    "component_code": adopted_line.component.code,
                    "sequence": adopted_line.sequence,
                    "rule_mode": adopted_line.rule_mode,
                    "calculation_basis": adopted_line.calculation_basis,
                }
            )

        structure.current_version = version
        structure.save(update_fields=["current_version"])

        summary.adopted = True
        summary.created_components = created_components
        summary.reused_components = reused_components
        summary.created_structure = {"id": structure.id, "code": structure.code, "name": structure.name}
        summary.created_version = {
            "id": version.id,
            "version_no": version.version_no,
            "effective_from": version.effective_from.isoformat(),
        }
        summary.created_lines = created_lines
        return summary.as_dict()

    @classmethod
    def _create_salary_structure_line(cls, *, structure, version, template_line, component_lookup):
        component = component_lookup[template_line.component.code]
        basis_codes = list(template_line.basis_components or [])
        basis_component = component_lookup.get(basis_codes[0]) if basis_codes else None
        rule_mode = SalaryStructureLine.RuleMode.STANDARD
        calculation_basis = SalaryStructureLine.CalculationBasis.INPUT
        fixed_amount = Decimal(template_line.amount_default or "0.00")
        rate = Decimal(template_line.percentage_default or "0.0000")

        if template_line.calculation_type == template_line.CalculationType.FIXED:
            calculation_basis = SalaryStructureLine.CalculationBasis.FIXED
        elif template_line.calculation_type == template_line.CalculationType.PERCENTAGE:
            calculation_basis = (
                SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT
                if basis_component
                else SalaryStructureLine.CalculationBasis.PERCENT_OF_CTC
            )
        elif template_line.calculation_type == template_line.CalculationType.MANUAL:
            calculation_basis = SalaryStructureLine.CalculationBasis.INPUT
        else:
            rule_mode = SalaryStructureLine.RuleMode.CUSTOM_FORMULA
            calculation_basis = SalaryStructureLine.CalculationBasis.INPUT

        rule_json = {
            "global_template_line_id": str(template_line.id),
            "global_component_code": template_line.component.code,
            "calculation_type": template_line.calculation_type,
            "formula": template_line.formula,
            "source_rule_json": template_line.rule_json or {},
            "basis_components": basis_codes,
            "amount_default": str(template_line.amount_default or "0.00"),
            "percentage_default": str(template_line.percentage_default or "0.0000"),
            "min_amount": str(template_line.min_amount) if template_line.min_amount is not None else None,
            "max_amount": str(template_line.max_amount) if template_line.max_amount is not None else None,
            "taxable_override": template_line.taxable_override,
            "affects_gross_override": template_line.affects_gross_override,
            "affects_net_override": template_line.affects_net_override,
            "affects_ctc_override": template_line.affects_ctc_override,
            "attendance_dependent": template_line.attendance_dependent,
            "lop_dependent": template_line.lop_dependent,
            "applicability_json": template_line.applicability_json or {},
        }

        compensation_bucket = cls._infer_compensation_bucket(template_line.component.component_type)
        ctc_treatment = (
            SalaryStructureLine.CTCTreatment.INCLUDED
            if template_line.affects_ctc_override is not False and template_line.component.affects_ctc
            else SalaryStructureLine.CTCTreatment.EXCLUDED
        )
        gross_treatment = (
            SalaryStructureLine.GrossTreatment.INCLUDED
            if template_line.affects_gross_override is not False and template_line.component.affects_gross
            else SalaryStructureLine.GrossTreatment.EXCLUDED
        )

        return SalaryStructureLine.objects.create(
            salary_structure=structure,
            salary_structure_version=version,
            component=component,
            sequence=template_line.sequence,
            rule_mode=rule_mode,
            calculation_basis=calculation_basis,
            basis_component=basis_component,
            rate=rate,
            fixed_amount=fixed_amount,
            is_pro_rated=template_line.pro_rata,
            is_override_allowed=False,
            is_active=template_line.is_active,
            recurrence_frequency=cls._infer_recurrence_frequency(template_line),
            compensation_bucket=compensation_bucket,
            ctc_treatment=ctc_treatment,
            gross_treatment=gross_treatment,
            rule_json=rule_json,
        )

    @staticmethod
    def _infer_compensation_bucket(component_type: str) -> str:
        mapping = {
            GlobalPayrollComponent.ComponentType.EARNING: SalaryStructureLine.CompensationBucket.FIXED_PAY,
            GlobalPayrollComponent.ComponentType.DEDUCTION: SalaryStructureLine.CompensationBucket.STATUTORY,
            GlobalPayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION: SalaryStructureLine.CompensationBucket.EMPLOYER_COST,
            GlobalPayrollComponent.ComponentType.REIMBURSEMENT: SalaryStructureLine.CompensationBucket.REIMBURSEMENT,
            GlobalPayrollComponent.ComponentType.RECOVERY: SalaryStructureLine.CompensationBucket.RECOVERY,
            GlobalPayrollComponent.ComponentType.INFORMATIONAL: SalaryStructureLine.CompensationBucket.STATUTORY,
        }
        return mapping.get(component_type, SalaryStructureLine.CompensationBucket.FIXED_PAY)

    @staticmethod
    def _infer_recurrence_frequency(template_line) -> str:
        source_rule_json = template_line.rule_json or {}
        raw_frequency = source_rule_json.get("recurrence_frequency")
        valid_values = {choice for choice, _ in SalaryStructureLine.RecurrenceFrequency.choices}
        if raw_frequency in valid_values:
            return raw_frequency
        return SalaryStructureLine.RecurrenceFrequency.MONTHLY
