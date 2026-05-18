from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from payroll.models import (
    GlobalPayrollComponent,
    GlobalPayrollComponentGroup,
    GlobalSalaryStructureTemplate,
    GlobalSalaryStructureTemplateLine,
)


class GlobalPayrollCatalogModelTests(TestCase):
    def setUp(self):
        self.group = GlobalPayrollComponentGroup.objects.create(
            code="EARNINGS",
            name="Earnings",
            group_type=GlobalPayrollComponentGroup.GroupType.EARNINGS,
        )
        self.component = GlobalPayrollComponent.objects.create(
            group=self.group,
            code="BASIC",
            name="Basic Salary",
            component_type=GlobalPayrollComponent.ComponentType.EARNING,
            calculation_type=GlobalPayrollComponent.CalculationType.PERCENTAGE,
            effective_from=date(2026, 4, 1),
        )
        self.template = GlobalSalaryStructureTemplate.objects.create(
            code="IN_STAFF",
            name="India Staff",
            template_type=GlobalSalaryStructureTemplate.TemplateType.MONTHLY_STAFF,
            pay_frequency=GlobalSalaryStructureTemplate.PayFrequency.MONTHLY,
            effective_from=date(2026, 4, 1),
        )

    def test_group_code_is_unique(self):
        with self.assertRaises(IntegrityError):
            GlobalPayrollComponentGroup.objects.create(
                code="EARNINGS",
                name="Duplicate",
                group_type=GlobalPayrollComponentGroup.GroupType.EARNINGS,
            )

    def test_component_rejects_invalid_effective_dates(self):
        component = GlobalPayrollComponent(
            group=self.group,
            code="HRA",
            name="HRA",
            component_type=GlobalPayrollComponent.ComponentType.EARNING,
            calculation_type=GlobalPayrollComponent.CalculationType.PERCENTAGE,
            effective_from=date(2026, 4, 1),
            effective_to=date(2026, 3, 31),
        )
        with self.assertRaises(ValidationError):
            component.full_clean()

    def test_template_line_unique_per_template_and_component(self):
        GlobalSalaryStructureTemplateLine.objects.create(
            template=self.template,
            component=self.component,
            sequence=100,
            calculation_type=GlobalSalaryStructureTemplateLine.CalculationType.PERCENTAGE,
        )
        with self.assertRaises(IntegrityError):
            GlobalSalaryStructureTemplateLine.objects.create(
                template=self.template,
                component=self.component,
                sequence=110,
                calculation_type=GlobalSalaryStructureTemplateLine.CalculationType.PERCENTAGE,
            )

    def test_template_line_amount_range_validation(self):
        line = GlobalSalaryStructureTemplateLine(
            template=self.template,
            component=self.component,
            sequence=100,
            calculation_type=GlobalSalaryStructureTemplateLine.CalculationType.FIXED,
            min_amount="5000.00",
            max_amount="1000.00",
        )
        with self.assertRaises(ValidationError):
            line.full_clean()
