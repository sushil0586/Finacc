from __future__ import annotations

from typing import Any

from payroll.models import GlobalSalaryStructureTemplate, PayrollComponent, SalaryStructure


class EntityAdoptionPreviewService:
    @staticmethod
    def preview_template(*, template: GlobalSalaryStructureTemplate, entity_id: int) -> dict[str, Any]:
        existing_components = {
            component.code: component
            for component in PayrollComponent.objects.filter(entity_id=entity_id)
        }
        template_lines = list(template.lines.select_related("component").order_by("sequence", "id"))

        components_to_create: list[dict[str, Any]] = []
        components_existing: list[dict[str, Any]] = []
        conflicts: list[str] = []
        warnings: list[str] = []

        for line in template_lines:
            global_component = line.component
            existing = existing_components.get(global_component.code)
            if existing is None:
                components_to_create.append(
                    {
                        "code": global_component.code,
                        "name": global_component.name,
                        "component_type": global_component.component_type,
                        "calculation_type": line.calculation_type,
                    }
                )
                continue

            existing_payload = {
                "id": existing.id,
                "code": existing.code,
                "name": existing.name,
                "component_type": existing.component_type,
            }
            components_existing.append(existing_payload)
            if existing.component_type != global_component.component_type:
                conflicts.append(
                    f"Component {existing.code} already exists for the entity with a different component type."
                )

        structure_exists = SalaryStructure.objects.filter(entity_id=entity_id, code=template.code).exists()
        if structure_exists:
            conflicts.append(f"Salary structure {template.code} already exists for this entity.")

        if not template.is_active:
            warnings.append("Template is inactive and should not be adopted until it is activated.")
        if template.effective_to:
            warnings.append("Template has an effective end date. Confirm adoption timing before rollout.")

        return {
            "template": {
                "id": str(template.id),
                "code": template.code,
                "name": template.name,
                "template_type": template.template_type,
            },
            "components_to_create": components_to_create,
            "components_existing": components_existing,
            "salary_structure": {
                "code": template.code,
                "name": template.name,
                "would_create": not structure_exists,
            },
            "conflicts": conflicts,
            "warnings": warnings,
        }
