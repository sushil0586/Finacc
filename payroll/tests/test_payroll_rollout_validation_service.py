from __future__ import annotations

from django.test import TestCase

from payroll.services.payroll_setup_service import PayrollSetupService
from payroll.services.payroll_rollout_validation_service import PayrollRolloutValidationService
from payroll.tests.factories import PayrollFactory


class PayrollRolloutValidationServiceTests(TestCase):
    def test_validation_passes_with_complete_setup(self):
        setup = PayrollFactory.full_payroll_setup()
        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )
        self.assertTrue(result.passed)

    def test_validation_fails_when_critical_config_missing(self):
        scope = PayrollFactory.entity_scope()
        result = PayrollRolloutValidationService.validate_setup(
            entity_id=scope["entity"].id,
            entityfinid_id=scope["entityfinid"].id,
            subentity_id=scope["subentity"].id,
        )
        self.assertFalse(result.passed)
        codes = {issue.code for issue in result.issues}
        self.assertIn("missing_components", codes)
        self.assertIn("missing_ledger_policy", codes)

    def test_validation_warns_for_outdated_versions_and_incomplete_policy(self):
        setup = PayrollFactory.full_payroll_setup()
        old_version = setup["version"]
        old_version.calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "ctc",
        }
        old_version.save(update_fields=["calculation_policy_json"])

        current_version = PayrollFactory.salary_structure_version(
            salary_structure=setup["structure"],
            version_no=old_version.version_no + 1,
        )
        current_version.calculation_policy_json = {}
        current_version.save(update_fields=["calculation_policy_json"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_outdated_structure_version"], 1)
        self.assertEqual(result.checks["approved_versions_missing_calculation_policy"], 1)
        self.assertEqual(result.checks["approved_versions_incomplete_calculation_policy"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_outdated_structure_version", codes)
        self.assertIn("approved_versions_missing_calculation_policy", codes)
        self.assertIn("approved_versions_incomplete_calculation_policy", codes)

    def test_validation_warns_when_tds_policy_metadata_is_missing(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["version"].calculation_policy_json = {
            **(setup["version"].calculation_policy_json or {}),
            "tax_policy_code": "",
            "tax_policy_version": "",
            "tax_policy_financial_year": "",
            "tax_policy_effective_from": "",
            "tds_standard_deduction_old_regime": "50000.00",
        }
        setup["version"].save(update_fields=["calculation_policy_json"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["approved_versions_missing_tax_policy_metadata"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("approved_versions_missing_tax_policy_metadata", codes)

    def test_validation_warns_for_regime_mismatch_and_missing_taxable_carry_in(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["profile"].tax_regime = "new_regime"
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "declared_deductions": "150000.00",
                "deduction_80c": "180000.00",
                "previous_employer_income": "250000.00",
            },
        }
        setup["profile"].save(update_fields=["tax_regime", "extra_data"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_with_new_regime_old_regime_tds_declarations"], 1)
        self.assertEqual(result.checks["profiles_missing_previous_employer_taxable_income"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_with_new_regime_old_regime_tds_declarations", codes)
        self.assertIn("profiles_missing_previous_employer_taxable_income", codes)

    def test_validation_warns_for_conflicting_tds_projection_inputs(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "annual_tax": "120000.00",
                "projected_taxable_income": "640000.00",
            },
        }
        setup["profile"].save(update_fields=["extra_data"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_with_conflicting_tds_projection_inputs"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_with_conflicting_tds_projection_inputs", codes)

    def test_validation_warns_for_policy_disabled_old_regime_deduction_bucket(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["version"].calculation_policy_json = {
            **(setup["version"].calculation_policy_json or {}),
            "tds_allow_80c_old_regime": False,
            "tds_allow_80d_old_regime": True,
            "tds_allow_hra_exemption_old_regime": True,
        }
        setup["version"].save(update_fields=["calculation_policy_json"])
        setup["profile"].tax_regime = "old_regime"
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "deduction_80c": "180000.00",
            },
        }
        setup["profile"].save(update_fields=["tax_regime", "extra_data"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_with_policy_disabled_old_regime_tds_buckets"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_with_policy_disabled_old_regime_tds_buckets", codes)

    def test_validation_warns_for_mixed_generic_and_structured_tds_deductions(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["profile"].tax_regime = "old_regime"
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "declared_deductions": "50000.00",
                "deduction_80c": "180000.00",
            },
        }
        setup["profile"].save(update_fields=["tax_regime", "extra_data"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_with_mixed_generic_and_structured_tds_deductions"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_with_mixed_generic_and_structured_tds_deductions", codes)

    def test_validation_warns_for_legacy_declared_deductions_field_usage(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["profile"].tax_regime = "old_regime"
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "declared_deductions": "50000.00",
            },
        }
        setup["profile"].save(update_fields=["tax_regime", "extra_data"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_using_legacy_tds_declared_deductions"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_using_legacy_tds_declared_deductions", codes)

    def test_validation_warns_for_hra_exemption_without_hra_component(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["profile"].tax_regime = "old_regime"
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "hra_exemption": "120000.00",
            },
        }
        setup["profile"].save(update_fields=["tax_regime", "extra_data"])

        for line in setup["version"].lines.filter(component__code__startswith="HRA"):
            line.delete()

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_with_hra_exemption_without_hra_component"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_with_hra_exemption_without_hra_component", codes)

    def test_validation_warns_for_hra_exemption_missing_support_inputs(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["profile"].tax_regime = "old_regime"
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "hra_exemption": "120000.00",
                "hra_rent_paid_annual": "240000.00",
            },
        }
        setup["profile"].save(update_fields=["tax_regime", "extra_data"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_with_hra_exemption_missing_support_inputs"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_with_hra_exemption_missing_support_inputs", codes)

    def test_validation_warns_for_invalid_hra_rent_months(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["profile"].tax_regime = "old_regime"
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "hra_rent_paid_annual": "240000.00",
                "hra_rent_months": 13,
            },
        }
        setup["profile"].save(update_fields=["tax_regime", "extra_data"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_with_invalid_hra_rent_months"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_with_invalid_hra_rent_months", codes)

    def test_validation_warns_for_missing_hra_landlord_pan_flag(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["profile"].tax_regime = "old_regime"
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "hra_rent_paid_annual": "240000.00",
                "hra_rent_months": 12,
            },
        }
        setup["profile"].save(update_fields=["tax_regime", "extra_data"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_with_hra_missing_landlord_pan_flag"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_with_hra_missing_landlord_pan_flag", codes)

    def test_validation_warns_for_unverified_hra_evidence(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["profile"].tax_regime = "old_regime"
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "hra_rent_paid_annual": "240000.00",
                "hra_rent_months": 12,
                "hra_landlord_pan_available": True,
                "hra_evidence_verified": False,
            },
        }
        setup["profile"].save(update_fields=["tax_regime", "extra_data"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_with_unverified_hra_evidence"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_with_unverified_hra_evidence", codes)

    def test_validation_warns_for_unverified_80c_and_80d_evidence(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["profile"].tax_regime = "old_regime"
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "deduction_80c": "150000.00",
                "deduction_80c_evidence_verified": False,
                "deduction_80d": "25000.00",
                "deduction_80d_evidence_verified": False,
            },
        }
        setup["profile"].save(update_fields=["tax_regime", "extra_data"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_with_unverified_80c_evidence"], 1)
        self.assertEqual(result.checks["profiles_with_unverified_80d_evidence"], 1)
        self.assertEqual(result.checks["profiles_with_unverified_tax_declaration_evidence"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_with_unverified_80c_evidence", codes)
        self.assertIn("profiles_with_unverified_80d_evidence", codes)
        self.assertIn("profiles_with_unverified_tax_declaration_evidence", codes)

    def test_validation_warns_for_tds_bucket_values_above_policy_caps(self):
        setup = PayrollFactory.full_payroll_setup()
        setup["profile"].tax_regime = "old_regime"
        setup["profile"].extra_data = {
            **(setup["profile"].extra_data or {}),
            "tax_projection_snapshot": {
                "deduction_80c": "180000.00",
                "deduction_80d": "40000.00",
            },
        }
        setup["profile"].save(update_fields=["tax_regime", "extra_data"])

        result = PayrollRolloutValidationService.validate_setup(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
            period_code=setup["period"].code,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.checks["profiles_with_tds_deduction_values_above_policy_caps"], 1)
        codes = {issue.code for issue in result.issues}
        self.assertIn("profiles_with_tds_deduction_values_above_policy_caps", codes)


class PayrollSetupServiceReadinessTests(TestCase):
    def test_readiness_summary_counts_version_and_policy_gaps(self):
        setup = PayrollFactory.full_payroll_setup()
        old_version = setup["version"]
        old_version.calculation_policy_json = {
            "country_code": "IN",
            "salary_mode": "ctc",
        }
        old_version.save(update_fields=["calculation_policy_json"])

        current_version = PayrollFactory.salary_structure_version(
            salary_structure=setup["structure"],
            version_no=old_version.version_no + 1,
        )
        current_version.calculation_policy_json = {}
        current_version.save(update_fields=["calculation_policy_json"])

        result = PayrollSetupService.readiness_summary(
            entity_id=setup["entity"].id,
            entityfinid_id=setup["entityfinid"].id,
            subentity_id=setup["subentity"].id,
        )

        self.assertEqual(result["outdated_structure_version_count"], 1)
        self.assertEqual(result["incomplete_calculation_policy_count"], 1)
        self.assertEqual(result["missing_calculation_policy_count"], 0)
