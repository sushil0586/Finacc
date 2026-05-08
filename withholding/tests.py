from datetime import date
from decimal import Decimal
import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import zipfile

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from withholding.models import (
    EntityPartyTaxProfile,
    EntityTcsThresholdOpening,
    PartyTaxProfile,
    WithholdingSection,
    WithholdingSectionPolicyAudit,
    WithholdingTaxType,
    WithholdingBaseRule,
)
from withholding.seed_withholding_service import WithholdingSeedService
from withholding.serializers import WithholdingSectionSerializer
from withholding.serializers import (
    EntityWithholdingConfigSerializer,
    EntityWithholdingSectionPostingMapSerializer,
    TcsCollectionSerializer,
    TcsDepositSerializer,
    TcsQuarterlyReturnSerializer,
)
from withholding.services import WithholdingResolver, compute_withholding_preview
from withholding.views import (
    TcsReportFilingPackExportAPIView,
    TcsReportFilingPackAPIView,
    TcsReportLedgerAPIView,
    TcsReturn27EqListCreateAPIView,
    TcsReturn27EqRetrieveUpdateDestroyAPIView,
    TcsDepositAllocateAPIView,
    TcsSectionListCreateAPIView,
    TcsWorkspaceTransactionsAPIView,
    _filing_readiness_errors,
    _row_readiness_status,
    _runtime_quality_flags,
    _tcs_computation_total_deposited,
    _sum_tcs_allocation_rows,
    _tcs_deposit_status_allows_allocation,
    _tcs_deposit_status_counts_as_deposited,
    _tcs_return_status_requires_clean_snapshot,
    _tcs_runtime_quality_flags,
)


class WithholdingResolverRateTests(SimpleTestCase):
    def _make_section(self, **overrides) -> WithholdingSection:
        data = {
            "tax_type": WithholdingTaxType.TDS,
            "section_code": "194C",
            "description": "Contractor",
            "rate_default": Decimal("1.0000"),
            "requires_pan": True,
            "higher_rate_no_pan": Decimal("20.0000"),
            "higher_rate_206ab": Decimal("5.0000"),
            "effective_from": date(2025, 4, 1),
            "is_active": True,
        }
        data.update(overrides)
        return WithholdingSection(**data)

    def _make_profile(self, **overrides) -> PartyTaxProfile:
        data = {
            "party_account_id": 1,
            "is_pan_available": True,
            "is_exempt_withholding": False,
            "is_specified_person_206ab": False,
            "lower_deduction_rate": None,
            "lower_deduction_valid_from": None,
            "lower_deduction_valid_to": None,
            "specified_person_valid_from": None,
            "specified_person_valid_to": None,
        }
        data.update(overrides)
        return PartyTaxProfile(**data)

    def test_resolve_rate_applies_no_pan_higher_rate(self):
        section = self._make_section()
        profile = self._make_profile(is_pan_available=False)

        result = WithholdingResolver.resolve_rate(
            section=section,
            party_profile=profile,
            doc_date=date(2026, 4, 1),
        )

        self.assertEqual(result.rate, Decimal("20.0000"))
        self.assertTrue(result.no_pan_applied)
        self.assertFalse(result.sec_206ab_applied)
        self.assertEqual(result.reason_code, "NO_PAN_206AA")

    def test_resolve_rate_applies_206ab_when_specified_person(self):
        section = self._make_section(higher_rate_no_pan=Decimal("2.0000"), higher_rate_206ab=Decimal("10.0000"))
        profile = self._make_profile(
            is_pan_available=True,
            is_specified_person_206ab=True,
            specified_person_valid_from=date(2026, 1, 1),
            specified_person_valid_to=date(2026, 12, 31),
        )

        result = WithholdingResolver.resolve_rate(
            section=section,
            party_profile=profile,
            doc_date=date(2026, 4, 1),
        )

        self.assertEqual(result.rate, Decimal("10.0000"))
        self.assertFalse(result.no_pan_applied)
        self.assertTrue(result.sec_206ab_applied)
        self.assertEqual(result.reason_code, "SEC_206AB")

    def test_resolve_rate_applies_higher_of_206aa_and_206ab(self):
        section = self._make_section(higher_rate_no_pan=Decimal("20.0000"), higher_rate_206ab=Decimal("5.0000"))
        profile = self._make_profile(
            is_pan_available=False,
            is_specified_person_206ab=True,
        )

        result = WithholdingResolver.resolve_rate(
            section=section,
            party_profile=profile,
            doc_date=date(2026, 4, 1),
        )

        self.assertEqual(result.rate, Decimal("20.0000"))
        self.assertTrue(result.no_pan_applied)
        self.assertTrue(result.sec_206ab_applied)
        self.assertEqual(result.reason_code, "NO_PAN_206AA_AND_SEC_206AB")

    def test_resolve_rate_prefers_lower_cert_when_valid(self):
        section = self._make_section()
        profile = self._make_profile(
            is_pan_available=False,
            lower_deduction_rate=Decimal("0.1000"),
            lower_deduction_valid_from=date(2026, 1, 1),
            lower_deduction_valid_to=date(2026, 12, 31),
            is_specified_person_206ab=True,
        )

        result = WithholdingResolver.resolve_rate(
            section=section,
            party_profile=profile,
            doc_date=date(2026, 6, 1),
        )

        self.assertEqual(result.rate, Decimal("0.1000"))
        self.assertTrue(result.lower_rate_applied)
        self.assertFalse(result.no_pan_applied)
        self.assertFalse(result.sec_206ab_applied)
        self.assertEqual(result.reason_code, "LOWER_CERT")


class WithholdingResolverProfileFallbackTests(SimpleTestCase):
    @patch("withholding.services.AccountComplianceProfile")
    @patch("withholding.services.PartyTaxProfile")
    def test_resolve_party_profile_uses_compliance_pan_when_party_profile_missing(self, mocked_party_profile, mocked_compliance):
        mocked_party_profile.objects.filter.return_value.first.return_value = None
        mocked_compliance.objects.filter.return_value.values_list.return_value.first.return_value = "ABCDE1234F"

        profile = WithholdingResolver.resolve_party_profile(party_account_id=10)

        self.assertIsNotNone(profile)
        self.assertTrue(profile.is_pan_available)
        self.assertEqual(profile.pan, "ABCDE1234F")

    @patch("withholding.services.AccountComplianceProfile")
    @patch("withholding.services.PartyTaxProfile")
    def test_resolve_party_profile_prefers_party_profile_and_backfills_pan_flag(self, mocked_party_profile, mocked_compliance):
        party_profile = MagicMock()
        party_profile.pan = None
        party_profile.is_pan_available = False
        mocked_party_profile.objects.filter.return_value.first.return_value = party_profile
        mocked_compliance.objects.filter.return_value.values_list.return_value.first.return_value = "AAAAA1111A"

        profile = WithholdingResolver.resolve_party_profile(party_account_id=20)

        self.assertIsNotNone(profile)
        self.assertTrue(profile.is_pan_available)
        self.assertEqual(profile.pan, "AAAAA1111A")

    @patch("withholding.services.AccountComplianceProfile")
    @patch("withholding.services.PartyTaxProfile")
    def test_resolve_party_profile_returns_none_without_pan_sources(self, mocked_party_profile, mocked_compliance):
        mocked_party_profile.objects.filter.return_value.first.return_value = None
        mocked_compliance.objects.filter.return_value.values_list.return_value.first.return_value = ""

        profile = WithholdingResolver.resolve_party_profile(party_account_id=30)
        self.assertIsNone(profile)


class WithholdingSectionApplicabilityTests(SimpleTestCase):
    @patch("withholding.services.AccountAddress")
    def test_evaluate_section_applicability_blocks_when_residency_mismatch(self, mocked_address):
        mocked_address.objects.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "IN"
        section = WithholdingSection(
            tax_type=WithholdingTaxType.TDS,
            section_code="195",
            description="Non-resident payments",
            rate_default=Decimal("10.0000"),
            effective_from=date(2025, 4, 1),
            is_active=True,
            applicability_json={"resident_status": ["non_resident"], "resident_country_codes": ["IN"]},
        )

        applicable, _, reason_code = WithholdingResolver.evaluate_section_applicability(
            section=section,
            party_account_id=99,
        )

        self.assertFalse(applicable)
        self.assertEqual(reason_code, "NOT_APPLICABLE_RESIDENCY")

    @patch("withholding.services.AccountAddress")
    def test_evaluate_section_applicability_skips_block_when_residency_unknown(self, mocked_address):
        mocked_address.objects.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        section = WithholdingSection(
            tax_type=WithholdingTaxType.TDS,
            section_code="195",
            description="Non-resident payments",
            rate_default=Decimal("10.0000"),
            effective_from=date(2025, 4, 1),
            is_active=True,
            applicability_json={"resident_status": ["non_resident"], "resident_country_codes": ["IN"]},
        )

        applicable, _, reason_code = WithholdingResolver.evaluate_section_applicability(
            section=section,
            party_account_id=99,
        )

        self.assertTrue(applicable)
        self.assertIsNone(reason_code)


class WithholdingSection195PolicyTests(SimpleTestCase):
    def _section_195(self):
        return WithholdingSection(
            tax_type=WithholdingTaxType.TDS,
            section_code="195",
            description="Non-resident payments",
            rate_default=Decimal("10.0000"),
            effective_from=date(2025, 4, 1),
            is_active=True,
            applicability_json={"resident_status": ["non_resident"], "resident_country_codes": ["IN"]},
        )


class WithholdingReadinessFlagTests(SimpleTestCase):
    def _section_195(self):
        return WithholdingSection(
            tax_type=WithholdingTaxType.TDS,
            section_code="195",
            description="Non-resident payments",
            rate_default=Decimal("10.0000"),
            effective_from=date(2025, 4, 1),
            is_active=True,
            applicability_json={"resident_status": ["non_resident"], "resident_country_codes": ["IN"]},
        )

    def test_runtime_flags_for_194a_pan_requirement(self):
        flags = _runtime_quality_flags(
            section_code="194A",
            reason_code="",
            pan="",
            tax_identifier="",
            residency_status="resident",
        )
        self.assertTrue(flags["missing_pan"])
        self.assertFalse(flags["missing_tax_id"])
        self.assertFalse(flags["residency_mismatch"])

    def test_runtime_flags_for_195_tax_id_and_residency(self):
        flags = _runtime_quality_flags(
            section_code="195",
            reason_code="",
            pan="ABCDE1234F",
            tax_identifier="",
            residency_status="resident",
        )
        self.assertTrue(flags["missing_tax_id"])
        self.assertTrue(flags["residency_mismatch"])

    def test_tcs_runtime_flags_follow_section_rules_not_tds_sections(self):
        section = SimpleNamespace(requires_pan=True)
        flags = _tcs_runtime_quality_flags(
            section=section,
            reason_code="INVALID_BASE_RULE",
            pan="",
        )
        self.assertTrue(flags["missing_pan"])
        self.assertTrue(flags["invalid_base_rule"])
        self.assertFalse(flags["missing_tax_id"])
        self.assertFalse(flags["residency_mismatch"])

    def test_tcs_runtime_flags_only_mark_missing_section_when_section_absent(self):
        flags = _tcs_runtime_quality_flags(
            section=None,
            reason_code="",
            pan="ABCDE1234F",
        )
        self.assertTrue(flags["missing_section"])
        self.assertFalse(flags["missing_pan"])

    def test_row_status_classification(self):
        ready = _row_readiness_status(
            amount=Decimal("100.00"),
            flags={"missing_pan": False, "missing_tax_id": False, "residency_mismatch": False, "invalid_base_rule": False, "missing_section": False},
        )
        blocked = _row_readiness_status(
            amount=Decimal("100.00"),
            flags={"missing_pan": False, "missing_tax_id": True, "residency_mismatch": False, "invalid_base_rule": False, "missing_section": False},
        )
        fix_now = _row_readiness_status(
            amount=Decimal("0.00"),
            flags={"missing_pan": False, "missing_tax_id": False, "residency_mismatch": False, "invalid_base_rule": False, "missing_section": False},
        )
        self.assertEqual(ready, "ready_to_file")
        self.assertEqual(blocked, "blocked")
        self.assertEqual(fix_now, "fix_now")

    def test_filing_readiness_errors_blocks_when_pending_or_exceptions_exist(self):
        errors = _filing_readiness_errors(
            {
                "counts": {
                    "missing_pan": 1,
                    "missing_section": 0,
                    "not_collected": 0,
                    "not_deposited": 0,
                    "partially_allocated": 0,
                    "deposit_mismatch": 0,
                },
                "totals": {"pending_collection": "0.00", "pending_deposit": "10.00"},
            }
        )
        self.assertTrue(errors)

    def test_filing_readiness_errors_allows_clean_snapshot(self):
        errors = _filing_readiness_errors(
            {
                "counts": {
                    "missing_pan": 0,
                    "missing_section": 0,
                    "not_collected": 0,
                    "not_deposited": 0,
                    "partially_allocated": 0,
                    "deposit_mismatch": 0,
                },
                "totals": {"pending_collection": "0.00", "pending_deposit": "0.00"},
            }
        )
        self.assertEqual(errors, [])

    @patch("withholding.services.WithholdingResolver.resolve_party_residency", return_value="resident")
    def test_validate_195_blocks_when_not_non_resident(self, _mock_residency):
        section = self._section_195()
        ok, _, reason_code = WithholdingResolver.validate_section_195_requirements(
            section=section,
            party_profile=PartyTaxProfile(party_account_id=1, is_pan_available=True),
            party_account_id=1,
            doc_date=date(2026, 4, 1),
        )
        self.assertFalse(ok)
        self.assertEqual(reason_code, "SEC195_NON_RESIDENT_REQUIRED")

    def test_validate_195_blocks_when_no_tax_identifier_and_no_pan(self):
        section = self._section_195()
        profile = PartyTaxProfile(party_account_id=1, is_pan_available=False)
        setattr(profile, "residency_status", "non_resident")
        setattr(profile, "tax_identifier", "")
        ok, _, reason_code = WithholdingResolver.validate_section_195_requirements(
            section=section,
            party_profile=profile,
            party_account_id=1,
            doc_date=date(2026, 4, 1),
        )
        self.assertFalse(ok)
        self.assertEqual(reason_code, "SEC195_TAX_ID_REQUIRED")

    def test_validate_195_blocks_when_treaty_rate_without_declaration(self):
        section = self._section_195()
        profile = PartyTaxProfile(party_account_id=1, is_pan_available=True)
        setattr(profile, "residency_status", "non_resident")
        setattr(profile, "tax_identifier", "TAX-123")
        setattr(profile, "declaration_reference", "")
        setattr(profile, "treaty_rate", Decimal("5.0000"))
        setattr(profile, "treaty_valid_from", date(2025, 4, 1))
        setattr(profile, "treaty_valid_to", date(2027, 3, 31))
        ok, _, reason_code = WithholdingResolver.validate_section_195_requirements(
            section=section,
            party_profile=profile,
            party_account_id=1,
            doc_date=date(2026, 4, 1),
        )
        self.assertFalse(ok)
        self.assertEqual(reason_code, "SEC195_DECLARATION_REQUIRED")

    def test_validate_195_allows_when_minimum_data_present(self):
        section = self._section_195()
        profile = PartyTaxProfile(party_account_id=1, is_pan_available=True)
        setattr(profile, "residency_status", "non_resident")
        setattr(profile, "tax_identifier", "TAX-123")
        setattr(profile, "declaration_reference", "FORM10F-2026")
        setattr(profile, "treaty_rate", Decimal("5.0000"))
        setattr(profile, "treaty_valid_from", date(2025, 4, 1))
        setattr(profile, "treaty_valid_to", date(2027, 3, 31))
        ok, _, reason_code = WithholdingResolver.validate_section_195_requirements(
            section=section,
            party_profile=profile,
            party_account_id=1,
            doc_date=date(2026, 4, 1),
        )
        self.assertTrue(ok)
        self.assertIsNone(reason_code)


class WithholdingTcsDepositStateTests(SimpleTestCase):
    def test_deposit_status_helpers_distinguish_draft_from_effective_deposit(self):
        self.assertFalse(_tcs_deposit_status_counts_as_deposited("DRAFT"))
        self.assertTrue(_tcs_deposit_status_counts_as_deposited("CONFIRMED"))
        self.assertTrue(_tcs_deposit_status_counts_as_deposited("FILED"))
        self.assertFalse(_tcs_deposit_status_allows_allocation("DRAFT"))
        self.assertTrue(_tcs_deposit_status_allows_allocation("CONFIRMED"))
        self.assertFalse(_tcs_deposit_status_allows_allocation("FILED"))

    def test_sum_tcs_allocation_rows_can_ignore_draft_deposits(self):
        allocations = [
            SimpleNamespace(
                allocated_amount=Decimal("40.00"),
                deposit=SimpleNamespace(status="DRAFT"),
            ),
            SimpleNamespace(
                allocated_amount=Decimal("60.00"),
                deposit=SimpleNamespace(status="CONFIRMED"),
            ),
            SimpleNamespace(
                allocated_amount=Decimal("25.00"),
                deposit=SimpleNamespace(status="FILED"),
            ),
        ]

        self.assertEqual(_sum_tcs_allocation_rows(allocations), Decimal("125.00"))
        self.assertEqual(_sum_tcs_allocation_rows(allocations, deposited_only=True), Decimal("85.00"))

    def test_computation_deposited_total_uses_only_linked_effective_allocations(self):
        deposit_allocations = [
            SimpleNamespace(
                allocated_amount=Decimal("40.00"),
                deposit=SimpleNamespace(status="DRAFT"),
            ),
            SimpleNamespace(
                allocated_amount=Decimal("60.00"),
                deposit=SimpleNamespace(status="CONFIRMED"),
            ),
        ]
        collection_open = SimpleNamespace(
            status="OPEN",
            deposit_allocations=SimpleNamespace(all=lambda: deposit_allocations),
        )
        collection_cancelled = SimpleNamespace(
            status="CANCELLED",
            deposit_allocations=SimpleNamespace(all=lambda: [
                SimpleNamespace(
                    allocated_amount=Decimal("25.00"),
                    deposit=SimpleNamespace(status="FILED"),
                )
            ]),
        )
        computation = SimpleNamespace(
            collections=SimpleNamespace(all=lambda: [collection_open, collection_cancelled]),
        )

        self.assertEqual(_tcs_computation_total_deposited(computation, deposited_only=True), Decimal("60.00"))
        self.assertEqual(_tcs_computation_total_deposited(computation, deposited_only=False), Decimal("100.00"))

    @patch("withholding.views._require_tcs_scope_permission")
    @patch("withholding.views.TcsCollection.objects.get")
    @patch("withholding.views.TcsDeposit.objects.get")
    def test_allocate_api_rejects_draft_deposit(
        self,
        mocked_deposit_get,
        mocked_collection_get,
        mocked_scope_permission,
    ):
        deposit = SimpleNamespace(id=10, entity_id=1, status="DRAFT")
        computation = SimpleNamespace(entity_id=1, fiscal_year="2026-27")
        collection = SimpleNamespace(id=20, status="OPEN", computation=computation)
        mocked_deposit_get.return_value = deposit
        mocked_collection_get.return_value = collection

        request = APIRequestFactory().post(
            "/tcs/deposits/10/allocate/",
            {"collection_id": 20, "allocated_amount": "50.00"},
            format="json",
        )
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        response = TcsDepositAllocateAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Allocation is allowed only against confirmed deposits.")
        mocked_scope_permission.assert_called_once()


class WithholdingTcsReturnLifecycleTests(SimpleTestCase):
    def test_return_status_helper_requires_clean_snapshot_for_validated_and_filed(self):
        self.assertFalse(_tcs_return_status_requires_clean_snapshot("DRAFT"))
        self.assertTrue(_tcs_return_status_requires_clean_snapshot("VALIDATED"))
        self.assertTrue(_tcs_return_status_requires_clean_snapshot("FILED"))

    def test_serializer_blocks_editing_filed_return(self):
        instance = SimpleNamespace(
            status="FILED",
            fy="2026-27",
            quarter="Q1",
            form_name="27EQ",
            return_type="ORIGINAL",
            entity=SimpleNamespace(id=1),
            ack_no="ACK-1",
            filed_on=date(2026, 5, 1),
        )
        serializer = TcsQuarterlyReturnSerializer(instance=instance)

        with self.assertRaises(Exception) as exc:
            serializer.validate({"status": "VALIDATED"})

        self.assertIn("Filed returns cannot be edited", str(exc.exception))

    @patch("withholding.views._require_tcs_scope_permission")
    @patch("withholding.views._build_tcs_27eq_snapshot")
    def test_create_validated_return_uses_same_readiness_gate_as_filed(
        self,
        mocked_snapshot,
        mocked_scope_permission,
    ):
        mocked_snapshot.return_value = {
            "counts": {
                "missing_pan": 1,
                "missing_section": 0,
                "not_collected": 0,
                "not_deposited": 0,
                "partially_allocated": 0,
                "deposit_mismatch": 0,
            },
            "totals": {"pending_collection": "0.00", "pending_deposit": "0.00"},
        }
        serializer = MagicMock()
        serializer.validated_data = {
            "entity": SimpleNamespace(id=1),
            "fy": "2026-27",
            "quarter": "Q1",
            "status": "VALIDATED",
            "json_snapshot": None,
        }
        view = TcsReturn27EqListCreateAPIView()
        view.request = APIRequestFactory().post("/tcs/returns/27eq/", {}, format="json")
        view.request.user = SimpleNamespace(is_authenticated=True)

        with self.assertRaises(Exception) as exc:
            view.perform_create(serializer)

        self.assertIn("Missing PAN rows exist", str(exc.exception))
        mocked_scope_permission.assert_called_once()

    def test_destroy_blocks_filed_return(self):
        instance = SimpleNamespace(status="FILED", delete=MagicMock())
        view = TcsReturn27EqRetrieveUpdateDestroyAPIView()

        with self.assertRaises(Exception) as exc:
            view.perform_destroy(instance)

        self.assertIn("Filed returns cannot be deleted", str(exc.exception))
        instance.delete.assert_not_called()


class WithholdingTcsWorkflowFieldLockdownTests(SimpleTestCase):
    def test_collection_serializer_rejects_direct_status_write(self):
        instance = SimpleNamespace(
            computation=None,
            collection_date=date(2026, 4, 1),
            amount_received=Decimal("100.00"),
            tcs_collected_amount=Decimal("10.00"),
            status="OPEN",
        )
        serializer = TcsCollectionSerializer(
            instance=instance,
            data={"status": "CANCELLED"},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("status", serializer.errors)

    def test_deposit_serializer_rejects_direct_status_and_depositor_writes(self):
        instance = SimpleNamespace(
            entity=None,
            financial_year="2026-27",
            month=4,
            challan_no="CH-1",
            total_deposit_amount=Decimal("10.00"),
            status="DRAFT",
            deposited_by=None,
        )
        serializer = TcsDepositSerializer(
            instance=instance,
            data={"status": "FILED", "deposited_by": 99},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("status", serializer.errors)
        self.assertIn("deposited_by", serializer.errors)

    def test_return_serializer_rejects_direct_workflow_field_writes(self):
        instance = SimpleNamespace(
            status="DRAFT",
            fy="2026-27",
            quarter="Q1",
            form_name="27EQ",
            return_type="ORIGINAL",
            entity=None,
            ack_no="",
            filed_on=None,
            json_snapshot=None,
            file_path="",
            original_return=None,
        )
        serializer = TcsQuarterlyReturnSerializer(
            instance=instance,
            data={
                "status": "FILED",
                "ack_no": "ACK-1",
                "filed_on": "2026-05-01",
                "json_snapshot": {"counts": {"missing_pan": 0}},
                "file_path": "returns/27eq.json",
            },
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("status", serializer.errors)
        self.assertIn("ack_no", serializer.errors)
        self.assertIn("filed_on", serializer.errors)
        self.assertIn("json_snapshot", serializer.errors)
        self.assertIn("file_path", serializer.errors)


class WithholdingTcsCorrectionReturnTests(SimpleTestCase):
    def _serializer_with_instance(self, **instance_overrides):
        instance = SimpleNamespace(
            status="DRAFT",
            fy="2026-27",
            quarter="Q1",
            form_name="27EQ",
            return_type="CORRECTION",
            entity=SimpleNamespace(id=10),
            original_return=None,
            ack_no="",
            filed_on=None,
        )
        for key, value in instance_overrides.items():
            setattr(instance, key, value)
        return TcsQuarterlyReturnSerializer(instance=instance)

    def test_correction_return_requires_original_reference(self):
        serializer = self._serializer_with_instance(original_return=None)

        with self.assertRaises(Exception) as exc:
            serializer.validate({"return_type": "CORRECTION"})

        self.assertIn("original return reference", str(exc.exception).lower())

    def test_correction_return_requires_filed_original(self):
        original = SimpleNamespace(
            id=1,
            entity_id=10,
            fy="2026-27",
            quarter="Q1",
            return_type="ORIGINAL",
            status="DRAFT",
        )
        serializer = self._serializer_with_instance(original_return=original)

        with self.assertRaises(Exception) as exc:
            serializer.validate({"return_type": "CORRECTION"})

        self.assertIn("filed original return", str(exc.exception).lower())

    def test_correction_return_rejects_original_from_other_quarter(self):
        original = SimpleNamespace(
            id=1,
            entity_id=10,
            fy="2026-27",
            quarter="Q2",
            return_type="ORIGINAL",
            status="FILED",
        )
        serializer = self._serializer_with_instance(original_return=original)

        with self.assertRaises(Exception) as exc:
            serializer.validate({"return_type": "CORRECTION"})

        self.assertIn("same quarter", str(exc.exception).lower())

    def test_correction_return_accepts_matching_filed_original(self):
        original = SimpleNamespace(
            id=1,
            entity_id=10,
            fy="2026-27",
            quarter="Q1",
            return_type="ORIGINAL",
            status="FILED",
        )
        serializer = self._serializer_with_instance(original_return=original)

        data = serializer.validate({"return_type": "CORRECTION"})

        self.assertEqual(data["return_type"], "CORRECTION")


class WithholdingTcsReportingExportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tcs-reporting-tests",
            email="tcs-reporting-tests@example.com",
            password="testpass123",
        )

    def test_filing_pack_view_requires_valid_scope_params(self):
        request = APIRequestFactory().get("/tcs/reports/filing-pack/?entity_id=1&fy=2026-27&quarter=Q5")
        force_authenticate(request, user=self.user)
        response = TcsReportFilingPackAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("quarter", response.data)

    def test_filing_pack_export_requires_financial_year(self):
        request = APIRequestFactory().get("/tcs/reports/filing-pack/export/?entity_id=1&quarter=Q1")
        force_authenticate(request, user=self.user)
        response = TcsReportFilingPackExportAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("fy", response.data)

    @patch.object(TcsReportFilingPackAPIView, "get")
    def test_filing_pack_export_includes_management_and_tracker_sheets(self, mocked_get):
        mocked_get.return_value = SimpleNamespace(
            data={
                "header": {
                    "fy": "2026-27",
                    "quarter": "Q1",
                    "return_status": "FILED",
                    "row_count": 2,
                    "exception_row_count": 1,
                    "total_tcs": "100.00",
                    "total_collected": "100.00",
                    "total_deposited": "90.00",
                    "pending_collection": "0.00",
                    "pending_deposit": "10.00",
                },
                "section_summary": [{"section_code": "206C(1H)", "total_tcs": "100.00"}],
                "rows": [
                    {
                        "doc_date": "2026-04-10",
                        "document_type": "invoice",
                        "document_no": "INV-1",
                        "party_name": "Buyer One",
                        "pan": "ABCDE1234F",
                        "section_code": "206C(1H)",
                        "taxable_base": "1000.00",
                        "tcs_rate": "0.10",
                        "tcs_amount": "100.00",
                        "tcs_collected_amount": "100.00",
                        "allocated_amount": "90.00",
                        "return_id": 5,
                        "return_quarter": "Q1",
                        "return_type": "ORIGINAL",
                        "return_status": "FILED",
                        "ack_no": "ACK-1",
                        "filed_on": "2026-05-05",
                        "exceptions": {
                            "missing_pan": False,
                            "invalid_pan_format": False,
                            "missing_tax_id": False,
                            "residency_mismatch": False,
                            "missing_section": False,
                            "not_collected": False,
                            "not_deposited": True,
                            "partially_allocated": True,
                            "deposit_mismatch": True,
                            "quarter_boundary_violation": False,
                            "reversal_case": False,
                        },
                    },
                    {
                        "doc_date": "2026-04-11",
                        "document_type": "invoice",
                        "document_no": "INV-2",
                        "party_name": "Buyer Two",
                        "pan": "AAAAA1111A",
                        "section_code": "206C(1H)",
                        "taxable_base": "500.00",
                        "tcs_rate": "0.10",
                        "tcs_amount": "50.00",
                        "tcs_collected_amount": "50.00",
                        "allocated_amount": "50.00",
                        "return_id": 5,
                        "return_quarter": "Q1",
                        "return_type": "ORIGINAL",
                        "return_status": "FILED",
                        "ack_no": "ACK-1",
                        "filed_on": "2026-05-05",
                        "exceptions": {
                            "missing_pan": False,
                            "invalid_pan_format": False,
                            "missing_tax_id": False,
                            "residency_mismatch": False,
                            "missing_section": False,
                            "not_collected": False,
                            "not_deposited": False,
                            "partially_allocated": False,
                            "deposit_mismatch": False,
                            "quarter_boundary_violation": False,
                            "reversal_case": False,
                        },
                    },
                ],
            }
        )

        request = APIRequestFactory().get("/tcs/reports/filing-pack/export/?entity_id=1&fy=2026-27&quarter=Q1")
        force_authenticate(request, user=self.user)
        response = TcsReportFilingPackExportAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        names = set(archive.namelist())

        self.assertIn("filing_pack_management_summary.csv", names)
        self.assertIn("filing_pack_exception_spotlight.csv", names)
        self.assertIn("filing_pack_return_tracker.csv", names)
        self.assertIn("filing_pack_transactions.csv", names)

        tracker_csv = archive.read("filing_pack_return_tracker.csv").decode("utf-8")
        self.assertIn("return_id", tracker_csv)
        tracker_lines = [line for line in tracker_csv.strip().splitlines() if line.strip()]
        self.assertEqual(len(tracker_lines), 2)
        self.assertIn("5", tracker_lines[1])

        spotlight_csv = archive.read("filing_pack_exception_spotlight.csv").decode("utf-8")
        self.assertIn("not_deposited", spotlight_csv)
        self.assertIn("deposit_mismatch", spotlight_csv)


class WithholdingTcsApiPermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_user(
            username="tcs-permission-tests",
            email="tcs-permission-tests@example.com",
            password="testpass123",
        )

    @patch("withholding.views.SubscriptionService.assert_entity_access")
    @patch("withholding.views.EffectivePermissionService.permission_codes_for_user", return_value=[])
    @patch("withholding.views.EffectivePermissionService.entity_for_user", return_value=SimpleNamespace(id=1))
    def test_tcs_sections_list_requires_view_permission(self, mocked_entity, mocked_codes, mocked_subscription):
        request = self.factory.get("/tcs/sections/?entity=1")
        force_authenticate(request, user=self.user)

        response = TcsSectionListCreateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 403)
        mocked_entity.assert_called_once_with(self.user, 1)
        mocked_codes.assert_called_once_with(self.user, 1)
        mocked_subscription.assert_called_once()

    def test_tcs_sections_list_requires_entity_scope(self):
        request = self.factory.get("/tcs/sections/")
        force_authenticate(request, user=self.user)

        response = TcsSectionListCreateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)

    @patch("withholding.views.SubscriptionService.assert_entity_access")
    @patch("withholding.views.EffectivePermissionService.permission_codes_for_user", return_value=[])
    @patch("withholding.views.EffectivePermissionService.entity_for_user", return_value=SimpleNamespace(id=1))
    def test_tcs_ledger_report_requires_report_permission(self, mocked_entity, mocked_codes, mocked_subscription):
        request = self.factory.get("/tcs/reports/ledger/?entity_id=1&fy=2025-26")
        force_authenticate(request, user=self.user)

        response = TcsReportLedgerAPIView.as_view()(request)

        self.assertEqual(response.status_code, 403)
        mocked_entity.assert_called_once_with(self.user, 1)
        mocked_codes.assert_called_once_with(self.user, 1)
        mocked_subscription.assert_called_once()

    @patch("withholding.views.SubscriptionService.assert_entity_access")
    @patch("withholding.views.EffectivePermissionService.permission_codes_for_user", return_value=[])
    @patch("withholding.views.EffectivePermissionService.entity_for_user", return_value=SimpleNamespace(id=1))
    def test_tcs_workspace_requires_workspace_permission(self, mocked_entity, mocked_codes, mocked_subscription):
        request = self.factory.get("/tcs/workspace/transactions/?entity_id=1")
        force_authenticate(request, user=self.user)

        response = TcsWorkspaceTransactionsAPIView.as_view()(request)

        self.assertEqual(response.status_code, 403)
        mocked_entity.assert_called_once_with(self.user, 1)
        mocked_codes.assert_called_once_with(self.user, 1)
        mocked_subscription.assert_called_once()


class WithholdingSeedServiceTests(SimpleTestCase):
    def test_seed_definitions_include_phase4_sections(self):
        rows = WithholdingSeedService._sections_data()
        by_code = {f"{row['tax_type']}:{row['section_code']}": row for row in rows}

        self.assertIn(f"{WithholdingTaxType.TDS}:194A", by_code)
        self.assertIn(f"{WithholdingTaxType.TDS}:194N", by_code)
        self.assertIn(f"{WithholdingTaxType.TDS}:195", by_code)

        sec_195 = by_code[f"{WithholdingTaxType.TDS}:195"]
        self.assertEqual(sec_195.get("base_rule"), WithholdingBaseRule.PAYMENT_VALUE)
        self.assertEqual(
            sec_195.get("applicability_json", {}).get("resident_status"),
            ["non_resident"],
        )

    def test_seed_definitions_include_receipt_runtime_tcs_variant(self):
        rows = WithholdingSeedService._sections_data()
        receipt_rows = [
            row
            for row in rows
            if row["tax_type"] == WithholdingTaxType.TCS
            and row["section_code"] == "206C(1)"
            and row.get("base_rule") == WithholdingBaseRule.RECEIPT_VALUE
        ]
        self.assertTrue(receipt_rows)


class WithholdingSectionSerializerTests(TestCase):
    def _valid_payload(self):
        return {
            "tax_type": WithholdingTaxType.TDS,
            "law_type": "INCOME_TAX",
            "section_code": "194A",
            "description": "Interest other than securities",
            "base_rule": WithholdingBaseRule.PAYMENT_VALUE,
            "rate_default": "10.0000",
            "threshold_default": "40000.00",
            "requires_pan": True,
            "higher_rate_no_pan": "20.0000",
            "effective_from": "2025-04-01",
            "is_active": True,
        }

    def test_applicability_json_accepts_supported_schema_and_normalizes(self):
        payload = self._valid_payload()
        payload["applicability_json"] = {
            "resident_status": "non_resident",
            "resident_country_codes": ["in", "IN"],
            "party_country_codes": ["ae", "US"],
        }
        s = WithholdingSectionSerializer(data=payload)
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(
            s.validated_data["applicability_json"],
            {
                "resident_status": ["non_resident"],
                "resident_country_codes": ["IN"],
                "party_country_codes": ["AE", "US"],
            },
        )

    def test_applicability_json_rejects_unknown_keys(self):
        payload = self._valid_payload()
        payload["applicability_json"] = {"foo": "bar"}
        s = WithholdingSectionSerializer(data=payload)
        self.assertFalse(s.is_valid())
        self.assertIn("applicability_json", s.errors)

    def test_applicability_json_rejects_invalid_resident_status(self):
        payload = self._valid_payload()
        payload["applicability_json"] = {"resident_status": ["resident", "alien"]}
        s = WithholdingSectionSerializer(data=payload)
        self.assertFalse(s.is_valid())
        self.assertIn("applicability_json", s.errors)

    def test_policy_audit_created_on_create_and_update(self):
        payload = self._valid_payload()
        payload["applicability_json"] = {"resident_status": ["resident"]}

        create_s = WithholdingSectionSerializer(data=payload)
        self.assertTrue(create_s.is_valid(), create_s.errors)
        section = create_s.save()

        first_audit = WithholdingSectionPolicyAudit.objects.filter(section=section).order_by("id").first()
        self.assertIsNotNone(first_audit)
        self.assertEqual(first_audit.action, WithholdingSectionPolicyAudit.Action.CREATED)

        update_s = WithholdingSectionSerializer(
            section,
            data={"rate_default": "12.5000", "applicability_json": {"resident_status": ["non_resident"]}},
            partial=True,
        )
        self.assertTrue(update_s.is_valid(), update_s.errors)
        update_s.save()

        latest_audit = WithholdingSectionPolicyAudit.objects.filter(section=section).order_by("-id").first()
        self.assertIsNotNone(latest_audit)
        self.assertEqual(latest_audit.action, WithholdingSectionPolicyAudit.Action.UPDATED)
        changed_fields = latest_audit.changed_fields_json or []
        self.assertIn("rate_default", changed_fields)
        self.assertIn("applicability_json", changed_fields)


class WithholdingPreviewWorkflowGuardTests(SimpleTestCase):
    @patch("withholding.services.WithholdingResolver.resolve_section")
    @patch("withholding.services.WithholdingResolver.get_entity_config")
    def test_preview_blocks_section_with_invalid_base_rule_for_workflow(self, mocked_cfg, mocked_resolve_section):
        mocked_cfg.return_value = type("Cfg", (), {"enable_tds": True, "enable_tcs": True})()
        mocked_resolve_section.return_value = WithholdingSection(
            tax_type=WithholdingTaxType.TDS,
            section_code="194A",
            description="Interest",
            base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
            rate_default=Decimal("10.0000"),
            effective_from=date(2025, 4, 1),
            is_active=True,
        )

        preview = compute_withholding_preview(
            entity_id=1,
            entityfin_id=1,
            subentity_id=None,
            party_account_id=1,
            tax_type=WithholdingTaxType.TDS,
            explicit_section_id=99,
            doc_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1000.00"),
            allowed_base_rules=[WithholdingBaseRule.PAYMENT_VALUE],
        )

        self.assertTrue(preview.enabled)
        self.assertEqual(preview.reason_code, "INVALID_BASE_RULE")
        self.assertEqual(preview.amount, Decimal("0.00"))


class WithholdingSectionResolutionDateTests(TestCase):
    def test_resolve_section_skips_expired_explicit_section(self):
        section = WithholdingSection.objects.create(
            tax_type=WithholdingTaxType.TDS,
            section_code="194A",
            description="Interest",
            base_rule=WithholdingBaseRule.PAYMENT_VALUE,
            rate_default=Decimal("10.0000"),
            effective_from=date(2024, 4, 1),
            effective_to=date(2025, 3, 31),
            is_active=True,
        )
        resolved = WithholdingResolver.resolve_section(
            tax_type=WithholdingTaxType.TDS,
            explicit_section_id=section.id,
            cfg=None,
            doc_date=date(2026, 4, 1),
        )
        self.assertIsNone(resolved)


class WithholdingSerializerGuardTests(SimpleTestCase):
    def test_section_identity_fields_are_immutable_on_update(self):
        instance = WithholdingSection(
            tax_type=WithholdingTaxType.TDS,
            section_code="194A",
            description="Interest",
            base_rule=WithholdingBaseRule.PAYMENT_VALUE,
            rate_default=Decimal("10.0000"),
            effective_from=date(2025, 4, 1),
            is_active=True,
        )
        serializer = WithholdingSectionSerializer(instance=instance)
        with self.assertRaises(Exception) as exc:
            serializer.validate({"base_rule": WithholdingBaseRule.INVOICE_VALUE_EXCL_GST})
        self.assertIn("base_rule", str(exc.exception))

    def test_entity_config_rejects_payment_basis_section_as_default(self):
        tds_payment_section = WithholdingSection(
            tax_type=WithholdingTaxType.TDS,
            section_code="194A",
            description="Interest",
            base_rule=WithholdingBaseRule.PAYMENT_VALUE,
            rate_default=Decimal("10.0000"),
            effective_from=date(2025, 4, 1),
            is_active=True,
        )
        serializer = EntityWithholdingConfigSerializer()
        with self.assertRaises(Exception) as exc:
            serializer.validate(
                {
                    "effective_from": date(2026, 4, 1),
                    "default_tds_section": tds_payment_section,
                }
            )
        self.assertIn("default_tds_section", str(exc.exception))

    def test_posting_map_rejects_cross_entity_account(self):
        serializer = EntityWithholdingSectionPostingMapSerializer()
        entity = SimpleNamespace(id=1)
        subentity = SimpleNamespace(id=10, entity_id=1)
        payable_account = SimpleNamespace(id=100, entity_id=2, ledger_id=500)
        payable_ledger = SimpleNamespace(id=500, entity_id=1)
        with self.assertRaises(Exception) as exc:
            serializer.validate(
                {
                    "entity": entity,
                    "subentity": subentity,
                    "payable_account": payable_account,
                    "payable_ledger": payable_ledger,
                }
            )
        self.assertIn("payable_account", str(exc.exception))


class WithholdingDeleteProtectionTests(SimpleTestCase):
    def test_withholding_party_links_use_protect(self):
        self.assertEqual(PartyTaxProfile._meta.get_field("party_account").remote_field.on_delete.__name__, "PROTECT")
        self.assertEqual(
            EntityPartyTaxProfile._meta.get_field("party_account").remote_field.on_delete.__name__,
            "PROTECT",
        )
        self.assertEqual(
            EntityTcsThresholdOpening._meta.get_field("party_account").remote_field.on_delete.__name__,
            "PROTECT",
        )
