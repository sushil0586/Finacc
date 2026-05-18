from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from payroll.models import ContractSalaryStructureAssignment
from payroll.services import (
    ContractPayrollProfileService,
    ContractSalaryAssignmentService,
    ContractStatutoryProfileService,
    EntityPayrollPolicyService,
    EntityStatutoryRegistrationService,
    OneTimePayItemService,
    PayrollRunReadinessResolverService,
    RecurringPayItemService,
    StatutorySchemeService,
)
from payroll.tests.factories import PayrollFactory


class PayrollRuntimeReadinessResolverServiceTests(TestCase):
    def setUp(self):
        self.scope = PayrollFactory.entity_scope()
        self.contract = PayrollFactory.hrms_contract(entity=self.scope["entity"], subentity=self.scope["subentity"])
        self.profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "payroll_start_date": self.contract.payroll_effective_from,
                "pf_applicable": True,
                "tds_applicable": True,
                "is_active": True,
            }
        )
        self.structure = PayrollFactory.salary_structure(
            entity=self.scope["entity"],
            entityfinid=self.scope["entityfinid"],
            subentity=self.scope["subentity"],
        )
        self.version = PayrollFactory.salary_structure_version(
            salary_structure=self.structure,
            version_no=1,
        )
        self.version.status = self.version.Status.APPROVED
        self.version.save(update_fields=["status", "updated_at"])
        self.component = PayrollFactory.component(entity=self.scope["entity"], code="BASIC")
        self.pf_scheme = StatutorySchemeService.create_or_update_scheme(
            {
                "code": "PF_IN",
                "name": "Provident Fund India",
                "scheme_type": "PF",
                "country_code": "IN",
                "state_code": "",
                "is_system": True,
                "is_active": True,
            }
        )
        self.tds_scheme = StatutorySchemeService.create_or_update_scheme(
            {
                "code": "TDS_IN",
                "name": "Tax Deducted at Source India",
                "scheme_type": "TDS",
                "country_code": "IN",
                "state_code": "",
                "is_system": True,
                "is_active": True,
            }
        )

    def _create_assignment(self, **overrides):
        payload = {
            "contract_payroll_profile": self.profile,
            "salary_structure": self.structure,
            "salary_structure_version": self.version,
            "effective_from": date(2026, 4, 1),
            "assignment_status": ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
            "ctc_amount": "100000.00",
            "gross_amount": "80000.00",
            "is_active": True,
        }
        payload.update(overrides)
        return ContractSalaryAssignmentService.assign_salary_structure(payload)

    def _create_policy(self, **overrides):
        payload = {
            "entity": self.scope["entity"],
            "code": "MONTHLY_DEFAULT",
            "name": "Monthly Default",
            "pay_frequency": "MONTHLY",
            "effective_from": date(2026, 4, 1),
            "is_default": True,
            "is_active": True,
        }
        payload.update(overrides)
        return EntityPayrollPolicyService.create_or_update_policy(payload)

    def _create_statutory_links(self):
        ContractStatutoryProfileService.create_or_update_profile(
            {
                "contract_payroll_profile": self.profile,
                "scheme": self.pf_scheme,
                "is_applicable": True,
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )
        ContractStatutoryProfileService.create_or_update_profile(
            {
                "contract_payroll_profile": self.profile,
                "scheme": self.tds_scheme,
                "is_applicable": True,
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )
        EntityStatutoryRegistrationService.create_or_update_registration(
            {
                "entity": self.scope["entity"],
                "scheme": self.pf_scheme,
                "registration_number": "PF-REG-001",
                "registration_state": "",
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )
        EntityStatutoryRegistrationService.create_or_update_registration(
            {
                "entity": self.scope["entity"],
                "scheme": self.tds_scheme,
                "registration_number": "TDS-REG-001",
                "registration_state": "",
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )

    def test_missing_salary_assignment_blocked(self):
        self._create_policy()
        result = PayrollRunReadinessResolverService.resolve_contract_readiness(
            contract=self.contract,
            payroll_date=date(2026, 5, 31),
        )
        self.assertEqual(result.readiness_status, "BLOCKED")
        self.assertIn("Missing active salary structure assignment.", result.blocking_issues)

    def test_inactive_policy_blocked(self):
        self._create_assignment()
        self._create_policy(is_active=False, is_default=False)
        result = PayrollRunReadinessResolverService.resolve_contract_readiness(
            contract=self.contract,
            payroll_date=date(2026, 5, 31),
        )
        self.assertEqual(result.readiness_status, "BLOCKED")
        self.assertIn("No active payroll policy found for the entity and pay frequency.", result.blocking_issues)

    def test_recurring_and_one_time_item_resolution(self):
        self._create_assignment()
        self._create_policy()
        self._create_statutory_links()
        RecurringPayItemService.create_or_update_item(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_component": self.component,
                "item_type": "EARNING",
                "amount": "2500.00",
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )
        OneTimePayItemService.create_or_update_item(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_component": self.component,
                "item_type": "EARNING",
                "requested_date": date(2026, 5, 10),
                "effective_date": date(2026, 5, 20),
                "amount": "1000.00",
                "approval_status": "APPROVED",
                "source_type": "INCENTIVE",
                "is_active": True,
            }
        )
        result = PayrollRunReadinessResolverService.resolve_contract_readiness(
            contract=self.contract,
            payroll_date=date(2026, 5, 31),
        )
        self.assertEqual(len(result.recurring_items), 1)
        self.assertEqual(len(result.one_time_items), 1)

    def test_statutory_registration_resolution(self):
        self._create_assignment()
        self._create_policy()
        self._create_statutory_links()
        result = PayrollRunReadinessResolverService.resolve_contract_readiness(
            contract=self.contract,
            payroll_date=date(2026, 5, 31),
        )
        self.assertEqual(result.readiness_status, "READY")
        self.assertEqual(len(result.statutory_registrations), 2)

    def test_overlapping_assignment_detection(self):
        self._create_policy()
        self._create_statutory_links()
        first = self._create_assignment()
        ContractSalaryStructureAssignment.objects.create(
            contract_payroll_profile=self.profile,
            salary_structure=self.structure,
            salary_structure_version=self.version,
            effective_from=first.effective_from,
            assignment_status=ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
            ctc_amount="120000.00",
            gross_amount="90000.00",
            is_active=True,
        )
        result = PayrollRunReadinessResolverService.resolve_contract_readiness(
            contract=self.contract,
            payroll_date=date(2026, 5, 31),
        )
        self.assertEqual(result.readiness_status, "BLOCKED")
        self.assertIn("Multiple active salary assignments overlap for the payroll date.", result.blocking_issues)

    def test_readiness_snapshot_generation(self):
        self._create_assignment()
        self._create_policy()
        self._create_statutory_links()
        result = PayrollRunReadinessResolverService.resolve_contract_readiness(
            contract=self.contract,
            payroll_date=date(2026, 5, 31),
        )
        self.assertEqual(result.generated_snapshot_json["contract"]["contract_code"], self.contract.contract_code)
        self.assertEqual(result.generated_snapshot_json["salary_structure"]["code"], self.structure.code)
        self.assertEqual(result.generated_snapshot_json["payroll_policy"]["code"], "MONTHLY_DEFAULT")


class PayrollRuntimeReadinessApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = PayrollFactory.user()
        self.client.force_authenticate(self.user)
        self.scope = PayrollFactory.entity_scope(user=self.user)
        self.contract = PayrollFactory.hrms_contract(entity=self.scope["entity"], subentity=self.scope["subentity"])
        self.profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )
        self.structure = PayrollFactory.salary_structure(
            entity=self.scope["entity"],
            entityfinid=self.scope["entityfinid"],
            subentity=self.scope["subentity"],
        )
        self.version = PayrollFactory.salary_structure_version(
            salary_structure=self.structure,
            version_no=1,
        )
        self.version.status = self.version.Status.APPROVED
        self.version.save(update_fields=["status", "updated_at"])
        ContractSalaryAssignmentService.assign_salary_structure(
            {
                "contract_payroll_profile": self.profile,
                "salary_structure": self.structure,
                "salary_structure_version": self.version,
                "effective_from": date(2026, 4, 1),
                "assignment_status": ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
                "ctc_amount": "100000.00",
                "gross_amount": "80000.00",
                "is_active": True,
            }
        )
        EntityPayrollPolicyService.create_or_update_policy(
            {
                "entity": self.scope["entity"],
                "code": "MONTHLY_DEFAULT",
                "name": "Monthly Default",
                "pay_frequency": "MONTHLY",
                "effective_from": date(2026, 4, 1),
                "is_default": True,
                "is_active": True,
            }
        )

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.payroll_setup_views.PayrollPermissionService.has_entity_permission_access", return_value=True)
    def test_runtime_readiness_preview_api(self, _perm, _scope):
        response = self.client.post(
            "/api/payroll/runtime/readiness-preview/",
            {
                "entity": self.scope["entity"].id,
                "payroll_date": "2026-05-31",
                "contract_ids": [str(self.contract.id)],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["counts"]["total"], 1)
        self.assertEqual(payload["results"][0]["contract_code"], self.contract.contract_code)
