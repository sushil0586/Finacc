from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from payroll.models import ContractPayrollInputSnapshot, ContractTaxDeclaration
from payroll.services import (
    ContractAttendanceSummaryService,
    ContractPayrollInputSnapshotService,
    ContractPayrollProfileService,
    ContractTaxDeclarationService,
    PayrollCalculationInputResolver,
)
from payroll.tests.factories import PayrollFactory


class ContractNativeTaxInputServiceTests(TestCase):
    def setUp(self):
        self.setup = PayrollFactory.full_payroll_setup()
        self.setup["profile"].employee_user = self.setup["user"]
        self.setup["profile"].save(update_fields=["employee_user"])
        self.hrms_employee = PayrollFactory.hrms_employee(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            user=self.setup["user"],
            employee_number=self.setup["profile"].employee_code,
        )
        self.contract = PayrollFactory.hrms_contract(
            entity=self.setup["entity"],
            subentity=self.setup["subentity"],
            employee=self.hrms_employee,
        )
        self.contract.start_date = date(2025, 4, 1)
        self.contract.payroll_effective_from = date(2025, 4, 1)
        self.contract.save(update_fields=["start_date", "payroll_effective_from", "updated_at"])
        self.contract_profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.setup["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "tax_regime": "NEW",
                "payment_mode": "BANK_TRANSFER",
                "payroll_start_date": self.contract.payroll_effective_from,
                "tds_applicable": True,
                "attendance_required": True,
                "is_active": True,
            }
        )
        ContractAttendanceSummaryService.create_or_update_summary(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "attendance_days": "30.00",
                "payable_days": "30.00",
                "lop_days": "0.00",
                "weekly_off_days": "0.00",
                "holiday_days": "0.00",
                "overtime_hours": "0.00",
                "late_count": 0,
                "half_days": "0.00",
                "source": "MANUAL",
                "approval_status": "APPROVED",
                "is_active": True,
            }
        )

    def _create_declaration(self, **overrides):
        payload = {
            "entity": self.setup["entity"],
            "contract_payroll_profile": self.contract_profile,
            "financial_year": self.setup["entityfinid"],
            "tax_regime": "NEW",
            "declaration_status": ContractTaxDeclaration.DeclarationStatus.APPROVED,
            "declared_annual_income": "650000.00",
            "previous_employer_income": "45000.00",
            "previous_employer_tds": "2500.00",
            "standard_deduction_amount": "50000.00",
            "professional_tax_declared": "2400.00",
            "is_active": True,
        }
        payload.update(overrides)
        return ContractTaxDeclarationService.create_or_update_declaration(payload)

    def test_declaration_uniqueness_per_contract_year(self):
        self._create_declaration()
        with self.assertRaises(ValueError):
            self._create_declaration()

    def test_approved_declaration_resolver(self):
        draft = self._create_declaration(declaration_status=ContractTaxDeclaration.DeclarationStatus.DRAFT)
        approved = ContractTaxDeclarationService.create_or_update_declaration(
            {"declaration_status": ContractTaxDeclaration.DeclarationStatus.APPROVED},
            instance=draft,
        )
        resolved = ContractTaxDeclarationService.resolve_approved_declaration(
            contract_payroll_profile=self.contract_profile,
            declaration_date=self.setup["period"].period_end,
        )
        self.assertEqual(resolved.id, approved.id)

    def test_input_snapshot_resolver(self):
        snapshot = ContractPayrollInputSnapshotService.create_or_update_snapshot(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "input_type": ContractPayrollInputSnapshot.InputType.ATTENDANCE_SUMMARY,
                "input_json": {"attendance_days": "29", "payable_days": "28", "period_days": "30"},
                "source": ContractPayrollInputSnapshot.SourceType.MANUAL,
                "effective_from": self.setup["period"].period_start,
                "is_active": True,
            }
        )
        resolved = ContractPayrollInputSnapshotService.resolve_snapshot(
            contract_payroll_profile=self.contract_profile,
            input_type=ContractPayrollInputSnapshot.InputType.ATTENDANCE_SUMMARY,
            snapshot_date=self.setup["period"].period_end,
            payroll_period=self.setup["period"],
        )
        self.assertEqual(resolved.id, snapshot.id)

    def test_resolver_prefers_contract_native_over_legacy_extra_data(self):
        declaration = self._create_declaration()
        ContractTaxDeclarationService.create_or_update_line(
            {
                "declaration": declaration,
                "section_code": "80C",
                "description": "ELSS",
                "declared_amount": "150000.00",
                "approved_amount": "120000.00",
                "evidence_required": True,
                "evidence_status": "VERIFIED",
                "metadata": {"review_note": "Matched receipts"},
                "is_active": True,
            }
        )
        ContractPayrollInputSnapshotService.create_or_update_snapshot(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "input_type": ContractPayrollInputSnapshot.InputType.TAX_PROJECTION,
                "input_json": {"monthly_tds": "900.00", "other_income": "15000.00"},
                "source": ContractPayrollInputSnapshot.SourceType.MANUAL,
                "effective_from": self.setup["period"].period_start,
                "is_active": True,
            }
        )
        ContractPayrollInputSnapshotService.create_or_update_snapshot(
            {
                "entity": self.setup["entity"],
                "contract_payroll_profile": self.contract_profile,
                "payroll_period": self.setup["period"],
                "input_type": ContractPayrollInputSnapshot.InputType.ATTENDANCE_SUMMARY,
                "input_json": {
                    "attendance_days": "30",
                    "payable_days": "29",
                    "period_days": "30",
                    "attendance_snapshot": {"present_days": 30},
                    "payable_days_snapshot": {"payable_days": 29},
                },
                "source": ContractPayrollInputSnapshot.SourceType.SYSTEM,
                "effective_from": self.setup["period"].period_start,
                "is_active": True,
            }
        )

        resolved = PayrollCalculationInputResolver.resolve(
            contract_payroll_profile=self.contract_profile,
            salary_assignment=None,
            readiness_snapshot={},
            payroll_date=self.setup["period"].period_end,
            payroll_period=self.setup["period"],
        )

        self.assertEqual(resolved.tax_projection_snapshot.get("monthly_tds"), "900.00")
        self.assertEqual(resolved.tax_projection_snapshot.get("deduction_80c"), "120000.00")
        self.assertEqual(resolved.tax_projection_snapshot.get("previous_employer_income"), "45000.00")
        self.assertEqual(resolved.attendance_snapshot.get("attendance_days"), "30.00")
        self.assertEqual(resolved.source_markers.get("tax_projection_snapshot"), "contract_native")
        self.assertEqual(resolved.source_markers.get("attendance_snapshot"), "contract_native")

    def test_resolver_returns_empty_tax_projection_when_no_contract_native_tax_input_exists(self):
        resolved = PayrollCalculationInputResolver.resolve(
            contract_payroll_profile=self.contract_profile,
            salary_assignment=None,
            readiness_snapshot={},
            payroll_date=self.setup["period"].period_end,
            payroll_period=self.setup["period"],
        )
        self.assertEqual(resolved.tax_projection_snapshot, {})
        self.assertEqual(resolved.attendance_snapshot.get("attendance_days"), "30.00")
        self.assertIsNone(resolved.source_markers.get("tax_projection_snapshot"))
        self.assertEqual(resolved.source_markers.get("attendance_snapshot"), "contract_native")


class ContractNativeTaxInputApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = PayrollFactory.user()
        self.client.force_authenticate(self.user)
        self.scope = PayrollFactory.entity_scope(user=self.user)
        self.hrms_employee = PayrollFactory.hrms_employee(
            entity=self.scope["entity"],
            subentity=self.scope["subentity"],
            user=self.user,
        )
        self.contract = PayrollFactory.hrms_contract(
            entity=self.scope["entity"],
            subentity=self.scope["subentity"],
            employee=self.hrms_employee,
        )
        self.contract_profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.payroll_setup_views.PayrollPermissionService.has_entity_permission_access", return_value=True)
    def test_create_and_update_contract_tax_declaration(self, _perm, _scope):
        create_response = self.client.post(
            "/api/payroll/contract-tax-declarations/",
            {
                "entity": self.scope["entity"].id,
                "contract_payroll_profile": str(self.contract_profile.id),
                "financial_year": self.scope["entityfinid"].id,
                "tax_regime": "NEW",
                "declaration_status": "DRAFT",
                "declared_annual_income": "500000.00",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        declaration_id = create_response.json()["id"]

        list_response = self.client.get(f"/api/payroll/contract-tax-declarations/?entity={self.scope['entity'].id}")
        self.assertEqual(list_response.status_code, 200, list_response.content)
        list_payload = list_response.json()
        results = list_payload.get("results", list_payload) if isinstance(list_payload, dict) else list_payload
        self.assertEqual(len(results), 1)

        patch_response = self.client.patch(
            f"/api/payroll/contract-tax-declarations/{declaration_id}/",
            {"declaration_status": "APPROVED"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        self.assertEqual(patch_response.json()["declaration_status"], "APPROVED")

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.payroll_setup_views.PayrollPermissionService.has_entity_permission_access", return_value=True)
    def test_create_line_and_input_snapshot(self, _perm, _scope):
        declaration = ContractTaxDeclarationService.create_or_update_declaration(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.contract_profile,
                "financial_year": self.scope["entityfinid"],
                "tax_regime": "NEW",
                "declaration_status": "DRAFT",
                "is_active": True,
            }
        )

        line_response = self.client.post(
            f"/api/payroll/contract-tax-declarations/{declaration.id}/lines/",
            {
                "section_code": "HRA",
                "description": "Rent proofs",
                "declared_amount": "120000.00",
                "approved_amount": "90000.00",
                "evidence_required": True,
                "evidence_status": "VERIFIED",
                "metadata": {"hra_rent_paid_annual": "180000.00"},
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(line_response.status_code, 201, line_response.content)

        snapshot_response = self.client.post(
            "/api/payroll/contract-input-snapshots/",
            {
                "entity": self.scope["entity"].id,
                "contract_payroll_profile": str(self.contract_profile.id),
                "input_type": "TAX_PROJECTION",
                "input_json": {"monthly_tds": "850.00"},
                "source": "MANUAL",
                "effective_from": str(self.scope["entityfinid"].finstartyear.date()),
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(snapshot_response.status_code, 201, snapshot_response.content)

        list_response = self.client.get(f"/api/payroll/contract-input-snapshots/?entity={self.scope['entity'].id}")
        self.assertEqual(list_response.status_code, 200, list_response.content)
        list_payload = list_response.json()
        results = list_payload.get("results", list_payload) if isinstance(list_payload, dict) else list_payload
        self.assertEqual(len(results), 1)
