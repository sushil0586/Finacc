from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from hrms.models import HrEmploymentContract
from payroll.models import ContractPayrollProfile, ContractSalaryStructureAssignment, SalaryStructure, SalaryStructureVersion
from payroll.services import ContractPayrollProfileService, ContractSalaryAssignmentService
from payroll.tests.factories import PayrollFactory


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
