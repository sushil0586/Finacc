from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from entity.models import SubEntity
from hrms.models import HrEmploymentContract
from payroll.models import ContractPayrollProfile, ContractSalaryStructureAssignment, ContractTaxDeclaration, SalaryStructure, SalaryStructureVersion
from payroll.services import (
    ContractPayrollProfileService,
    ContractSalaryAssignmentService,
    ContractTaxDeclarationService,
    PayrollPermissionService,
)
from payroll.tests.factories import PayrollFactory
from rbac.models import Permission, Role, RolePermission, UserRoleAssignment


class ContractPayrollBridgeServiceTests(TestCase):
    def setUp(self):
        self.scope = PayrollFactory.entity_scope()
        self.contract = PayrollFactory.hrms_contract(entity=self.scope["entity"], subentity=self.scope["subentity"])
        self.structure = PayrollFactory.salary_structure(
            entity=self.scope["entity"],
            entityfinid=self.scope["entityfinid"],
            subentity=self.scope["subentity"],
        )
        self.version = PayrollFactory.salary_structure_version(salary_structure=self.structure, version_no=1)

    def test_one_active_profile_per_contract(self):
        ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )

        with self.assertRaisesMessage(ValueError, "already exists"):
            ContractPayrollProfileService.create_or_update_profile(
                {
                    "entity": self.scope["entity"],
                    "hrms_contract": self.contract,
                    "pay_frequency": "MONTHLY",
                    "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
                    "payroll_start_date": self.contract.payroll_effective_from,
                    "is_active": True,
                }
            )

    def test_entity_mismatch_blocked(self):
        other_scope = PayrollFactory.entity_scope()

        with self.assertRaisesMessage(ValueError, "selected entity"):
            ContractPayrollProfileService.create_or_update_profile(
                {
                    "entity": other_scope["entity"],
                    "hrms_contract": self.contract,
                    "pay_frequency": "MONTHLY",
                    "payroll_start_date": self.contract.payroll_effective_from,
                    "is_active": True,
                }
            )

    def test_invalid_hrms_contract_blocked(self):
        inactive_contract = PayrollFactory.hrms_contract(
            entity=self.scope["entity"],
            subentity=self.scope["subentity"],
            status=HrEmploymentContract.ContractStatus.CLOSED,
        )

        with self.assertRaisesMessage(ValueError, "payroll-eligible status"):
            ContractPayrollProfileService.create_or_update_profile(
                {
                    "entity": self.scope["entity"],
                    "hrms_contract": inactive_contract,
                    "pay_frequency": "MONTHLY",
                    "payroll_start_date": inactive_contract.payroll_effective_from,
                    "is_active": True,
                }
            )

    def test_salary_assignment_overlap_blocked(self):
        profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )
        ContractSalaryAssignmentService.assign_salary_structure(
            {
                "contract_payroll_profile": profile,
                "salary_structure": self.structure,
                "salary_structure_version": self.version,
                "effective_from": date(2026, 4, 1),
                "assignment_status": ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
                "ctc_amount": "100000.00",
                "gross_amount": "80000.00",
                "is_active": True,
            }
        )

        with self.assertRaisesMessage(ValueError, "overlap"):
            ContractSalaryAssignmentService.assign_salary_structure(
                {
                    "contract_payroll_profile": profile,
                    "salary_structure": self.structure,
                    "salary_structure_version": self.version,
                    "effective_from": date(2026, 4, 15),
                    "assignment_status": ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
                    "ctc_amount": "110000.00",
                    "gross_amount": "90000.00",
                    "is_active": True,
                }
            )

    def test_active_assignment_resolver_works(self):
        profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )
        assignment = ContractSalaryAssignmentService.assign_salary_structure(
            {
                "contract_payroll_profile": profile,
                "salary_structure": self.structure,
                "salary_structure_version": self.version,
                "effective_from": date(2026, 4, 1),
                "assignment_status": ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
                "ctc_amount": "120000.00",
                "gross_amount": "95000.00",
                "is_active": True,
            }
        )

        resolved = ContractSalaryAssignmentService.get_active_assignment_for_payroll_date(
            contract_payroll_profile=profile,
            payroll_date=date(2026, 4, 25),
        )

        self.assertEqual(resolved.id, assignment.id)

    def test_structure_version_mismatch_blocked(self):
        other_structure = PayrollFactory.salary_structure(entity=self.scope["entity"])
        other_version = PayrollFactory.salary_structure_version(salary_structure=other_structure, version_no=1)
        profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )

        with self.assertRaisesMessage(ValueError, "must belong"):
            ContractSalaryAssignmentService.assign_salary_structure(
                {
                    "contract_payroll_profile": profile,
                    "salary_structure": self.structure,
                    "salary_structure_version": other_version,
                    "effective_from": date(2026, 4, 1),
                    "assignment_status": ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
                    "ctc_amount": "120000.00",
                    "gross_amount": "95000.00",
                    "is_active": True,
                }
            )

    @patch("payroll.services.payroll_permission_service.EffectivePermissionService.permission_codes_for_user")
    def test_contract_profile_permissions_are_resolved_from_entity_rbac(self, mocked_codes):
        mocked_codes.return_value = {"payroll.contract_profile.view"}
        user = SimpleNamespace(is_authenticated=True, is_superuser=False)

        self.assertTrue(
            PayrollPermissionService.has_entity_permission_access(
                user=user,
                entity_id=self.scope["entity"].id,
                permission_key="profile_view",
            )
        )

        mocked_codes.return_value = {"payroll.contract_profile.edit"}
        self.assertTrue(
            PayrollPermissionService.has_entity_permission_access(
                user=user,
                entity_id=self.scope["entity"].id,
                permission_key="profile_edit",
            )
        )

        mocked_codes.reset_mock()
        mocked_codes.return_value = {"payroll.run.calculate"}
        self.assertTrue(
            PayrollPermissionService.has_action_access(
                user=user,
                entity_id=self.scope["entity"].id,
                subentity_id=self.scope["subentity"].id,
                action="calculate",
            )
        )
        mocked_codes.assert_called_once_with(
            user,
            self.scope["entity"].id,
            subentity_id=self.scope["subentity"].id,
        )


class ContractPayrollBridgeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = PayrollFactory.user()
        self.client.force_authenticate(self.user)
        self.scope = PayrollFactory.entity_scope(user=self.user)
        self.contract = PayrollFactory.hrms_contract(entity=self.scope["entity"], subentity=self.scope["subentity"])
        self.structure = PayrollFactory.salary_structure(
            entity=self.scope["entity"],
            entityfinid=self.scope["entityfinid"],
            subentity=self.scope["subentity"],
        )
        self.version = PayrollFactory.salary_structure_version(salary_structure=self.structure, version_no=1)

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.payroll_setup_views.PayrollPermissionService.has_entity_permission_access", return_value=True)
    def test_create_list_and_update_contract_profile(self, _perm, _scope):
        create_response = self.client.post(
            "/api/payroll/contract-profiles/",
            {
                "entity": self.scope["entity"].id,
                "hrms_contract": str(self.contract.id),
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "tax_regime": "NEW",
                "payment_mode": "BANK_TRANSFER",
                "payroll_start_date": str(self.contract.payroll_effective_from),
                "pf_applicable": True,
                "tds_applicable": True,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        profile_id = create_response.json()["id"]

        list_response = self.client.get(f"/api/payroll/contract-profiles/?entity={self.scope['entity'].id}")
        self.assertEqual(list_response.status_code, 200, list_response.content)
        list_payload = list_response.json()
        results = list_payload.get("results", list_payload) if isinstance(list_payload, dict) else list_payload
        self.assertEqual(len(results), 1)

        patch_response = self.client.patch(
            f"/api/payroll/contract-profiles/{profile_id}/",
            {"payment_mode": "CASH", "overtime_eligible": True},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        self.assertEqual(patch_response.json()["payment_mode"], "CASH")
        self.assertTrue(patch_response.json()["overtime_eligible"])

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.payroll_setup_views.PayrollPermissionService.has_entity_permission_access", return_value=True)
    def test_create_and_update_salary_assignment(self, _perm, _scope):
        profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )

        create_response = self.client.post(
            f"/api/payroll/contract-profiles/{profile.id}/salary-assignments/",
            {
                "salary_structure": self.structure.id,
                "salary_structure_version": self.version.id,
                "effective_from": "2026-04-01",
                "assignment_status": "ACTIVE",
                "ctc_amount": "240000.00",
                "gross_amount": "180000.00",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        assignment_id = create_response.json()["id"]

        patch_response = self.client.patch(
            f"/api/payroll/contract-salary-assignments/{assignment_id}/",
            {"gross_amount": "190000.00"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        self.assertEqual(float(patch_response.json()["gross_amount"]), 190000.0)


@override_settings(RBAC_DEV_ALLOW_ALL_ACCESS=False)
class ContractPayrollSensitiveObjectIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = PayrollFactory.user()
        self.client.force_authenticate(self.user)
        self.scope = PayrollFactory.entity_scope(user=self.user)
        self.branch_a = self.scope["subentity"]
        self.branch_b = SubEntity.objects.create(
            entity=self.scope["entity"],
            subentityname="Restricted payroll branch",
            branch_type=SubEntity.BranchType.BRANCH,
        )
        self.profile_a, self.assignment_a, self.declaration_a = self._payroll_objects(self.branch_a, "A")
        self.profile_b, self.assignment_b, self.declaration_b = self._payroll_objects(self.branch_b, "B")

    def _payroll_objects(self, branch, suffix):
        contract = PayrollFactory.hrms_contract(entity=self.scope["entity"], subentity=branch)
        profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": ContractPayrollProfile.PayrollStatus.ACTIVE,
                "payment_mode": "BANK_TRANSFER",
                "bank_account_details": {"account_number": f"SENSITIVE-{suffix}"},
                "payroll_start_date": contract.payroll_effective_from,
                "is_active": True,
            }
        )
        structure = PayrollFactory.salary_structure(
            entity=self.scope["entity"],
            entityfinid=self.scope["entityfinid"],
            subentity=branch,
        )
        version = PayrollFactory.salary_structure_version(salary_structure=structure, version_no=1)
        assignment = ContractSalaryAssignmentService.assign_salary_structure(
            {
                "contract_payroll_profile": profile,
                "salary_structure": structure,
                "salary_structure_version": version,
                "effective_from": date(2025, 4, 1),
                "assignment_status": ContractSalaryStructureAssignment.AssignmentStatus.ACTIVE,
                "ctc_amount": "120000.00",
                "gross_amount": "95000.00",
                "is_active": True,
            }
        )
        declaration = ContractTaxDeclarationService.create_or_update_declaration(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": profile,
                "financial_year": self.scope["entityfinid"],
                "tax_regime": ContractTaxDeclaration.TaxRegime.NEW,
                "declaration_status": ContractTaxDeclaration.DeclarationStatus.DRAFT,
                "declared_annual_income": "500000.00",
                "is_active": True,
            }
        )
        return profile, assignment, declaration

    def _grant(self, *, branch, code, role_suffix):
        permission, _ = Permission.objects.get_or_create(
            code=code,
            defaults={
                "name": code,
                "module": "payroll",
                "resource": "contract_profile",
                "action": code.rsplit(".", 1)[-1],
            },
        )
        role = Role.objects.create(
            entity=self.scope["entity"],
            name=f"Payroll branch {role_suffix}",
            code=f"payroll_branch_{role_suffix}_{self.scope['entity'].id}",
        )
        RolePermission.objects.create(role=role, permission=permission)
        UserRoleAssignment.objects.create(
            user=self.user,
            entity=self.scope["entity"],
            role=role,
            subentity=branch,
        )

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    def test_permissions_from_one_branch_cannot_expose_another_branch_sensitive_objects(self, _scope):
        self._grant(branch=self.branch_a, code="payroll.contract_profile.view", role_suffix="view_a")
        self._grant(branch=self.branch_b, code="payroll.component.view", role_suffix="scope_b")

        urls = [
            f"/api/payroll/contract-profiles/{self.profile_b.id}/",
            f"/api/payroll/contract-salary-assignments/{self.assignment_b.id}/",
            f"/api/payroll/contract-tax-declarations/{self.declaration_b.id}/",
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403, response.content)
                self.assertNotIn("SENSITIVE-B", response.content.decode(errors="ignore"))

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    def test_branch_scoped_profile_and_tax_lists_return_only_that_branch(self, _scope):
        self._grant(branch=self.branch_a, code="payroll.contract_profile.view", role_suffix="view_a")
        self._grant(branch=self.branch_b, code="payroll.contract_profile.view", role_suffix="view_b")

        profile_response = self.client.get(
            f"/api/payroll/contract-profiles/?entity={self.scope['entity'].id}&subentity={self.branch_a.id}"
        )
        self.assertEqual(profile_response.status_code, 200, profile_response.content)
        profile_payload = profile_response.json()
        profile_results = profile_payload.get("results", profile_payload) if isinstance(profile_payload, dict) else profile_payload
        self.assertEqual([row["id"] for row in profile_results], [str(self.profile_a.id)])
        self.assertNotIn("SENSITIVE-B", profile_response.content.decode(errors="ignore"))

        tax_response = self.client.get(
            f"/api/payroll/contract-tax-declarations/?entity={self.scope['entity'].id}&subentity={self.branch_a.id}"
        )
        self.assertEqual(tax_response.status_code, 200, tax_response.content)
        tax_payload = tax_response.json()
        tax_results = tax_payload.get("results", tax_payload) if isinstance(tax_payload, dict) else tax_payload
        self.assertEqual([row["id"] for row in tax_results], [str(self.declaration_a.id)])
