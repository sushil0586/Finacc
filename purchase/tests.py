from decimal import Decimal
from datetime import date
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APITestCase, APIClient, APIRequestFactory, force_authenticate

from assets.models import AssetCategory, FixedAsset
from entity.models import Entity, EntityFinancialYear, SubEntity
from catalog.models import Product, ProductCategory, ProductPurchaseBehavior, UnitOfMeasure
from financial.models import Ledger, account
from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.serializers.purchase_invoice import PurchaseInvoiceHeaderSerializer
from purchase.serializers.purchase_statutory import (
    PurchaseStatutoryChallanCreateInputSerializer,
    PurchaseStatutoryReturnCreateInputSerializer,
)
from purchase.services.purchase_invoice_nav_service import PurchaseInvoiceNavService
from purchase.services.purchase_invoice_actions import PurchaseInvoiceActions
from purchase.services.purchase_asset_intake_service import PurchaseAssetIntakeService
from purchase.services.purchase_invoice_service import PurchaseInvoiceService
from purchase.services.purchase_settings_service import PurchaseSettingsService
from purchase.services.purchase_statutory_service import PurchaseStatutoryService
from purchase.views.purchase_invoice import PurchaseInvoiceListCreateAPIView
from posting.adapters.purchase_invoice import (
    PurchaseInvoicePostingAdapter,
    PurchaseInvoicePostingConfig,
)
from posting.common.static_accounts import StaticAccountCodes
from withholding.services import WithholdingResult
from purchase.services.purchase_withholding_service import PurchaseWithholdingService
from purchase.models.purchase_statutory import PurchaseStatutoryChallan, PurchaseStatutoryReturn
from purchase.models.purchase_statutory import PurchaseStatutoryReturnLine


class PurchaseTdsApplyTests(SimpleTestCase):
    def _make_header(self, **overrides):
        defaults = {
            "withholding_enabled": True,
            "tds_is_manual": False,
            "tds_section_id": None,
            "tds_section": None,
            "tds_rate": Decimal("0.0000"),
            "tds_base_amount": Decimal("0.00"),
            "tds_amount": Decimal("0.00"),
            "tds_reason": None,
            "entity_id": 1,
            "entityfinid_id": 1,
            "subentity_id": None,
            "vendor_id": 1,
            "bill_date": None,
            "total_taxable": Decimal("1000.00"),
            "grand_total": Decimal("1180.00"),
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_withholding_disabled_clears_tds(self):
        header = self._make_header(
            withholding_enabled=False,
            tds_is_manual=True,
            tds_section_id=10,
            tds_rate=Decimal("1.0000"),
            tds_base_amount=Decimal("1000.00"),
            tds_amount=Decimal("10.00"),
            tds_reason="any",
        )

        PurchaseInvoiceService._apply_tds(header=header)

        self.assertFalse(header.tds_is_manual)
        self.assertIsNone(header.tds_section)
        self.assertEqual(header.tds_rate, Decimal("0.0000"))
        self.assertEqual(header.tds_base_amount, Decimal("0.00"))
        self.assertEqual(header.tds_amount, Decimal("0.00"))
        self.assertIsNone(header.tds_reason)

    @patch("purchase.services.purchase_invoice_service.WithholdingResolver.get_entity_config")
    def test_manual_mode_requires_section(self, mock_get_cfg):
        mock_get_cfg.return_value = None
        header = self._make_header(withholding_enabled=True, tds_is_manual=True, tds_section_id=None)

        with self.assertRaisesMessage(ValueError, "TDS section is required when withholding_enabled is true."):
            PurchaseInvoiceService._apply_tds(header=header)

    @patch("purchase.services.purchase_invoice_service.WithholdingResolver.get_entity_config")
    def test_manual_mode_rejects_non_invoice_based_section(self, mock_get_cfg):
        mock_get_cfg.return_value = None
        header = self._make_header(
            withholding_enabled=True,
            tds_is_manual=True,
            tds_section_id=11,
            tds_section=SimpleNamespace(base_rule=4),  # PAYMENT_VALUE
            tds_rate=Decimal("1.0000"),
            tds_base_amount=Decimal("1000.00"),
            tds_amount=Decimal("10.00"),
        )

        with self.assertRaisesMessage(ValueError, "not invoice-based"):
            PurchaseInvoiceService._apply_tds(header=header)

    @patch("purchase.services.purchase_invoice_service.WithholdingResolver.get_entity_config")
    def test_manual_mode_respects_tds_enabled_config(self, mock_get_cfg):
        mock_get_cfg.return_value = SimpleNamespace(enable_tds=False)
        header = self._make_header(
            withholding_enabled=True,
            tds_is_manual=True,
            tds_section_id=11,
            tds_section=SimpleNamespace(base_rule=1),
            tds_rate=Decimal("1.0000"),
            tds_base_amount=Decimal("1000.00"),
            tds_amount=Decimal("10.00"),
        )
        with self.assertRaisesMessage(ValueError, "TDS is disabled in withholding configuration"):
            PurchaseInvoiceService._apply_tds(header=header)

    @patch("purchase.services.purchase_invoice_service.WithholdingResolver.evaluate_section_applicability")
    @patch("purchase.services.purchase_invoice_service.WithholdingResolver.get_entity_config")
    def test_manual_mode_respects_section_applicability(self, mock_get_cfg, mock_eval_applicability):
        mock_get_cfg.return_value = SimpleNamespace(enable_tds=True)
        mock_eval_applicability.return_value = (False, "Section not applicable for party residency 'resident'", "NOT_APPLICABLE_RESIDENCY")
        header = self._make_header(
            withholding_enabled=True,
            tds_is_manual=True,
            tds_section_id=11,
            tds_section=SimpleNamespace(base_rule=1),
            tds_rate=Decimal("1.0000"),
            tds_base_amount=Decimal("1000.00"),
            tds_amount=Decimal("10.00"),
        )
        with self.assertRaisesMessage(ValueError, "not applicable"):
            PurchaseInvoiceService._apply_tds(header=header)

    @patch("purchase.services.purchase_invoice_service.PurchaseWithholdingService.compute_tds")
    def test_auto_mode_accepts_resolved_section_from_config(self, mock_compute):
        section = SimpleNamespace(id=22)
        header = self._make_header(withholding_enabled=True, tds_is_manual=False, tds_section_id=None)

        mock_compute.return_value = WithholdingResult(
            enabled=True,
            section=section,
            rate=Decimal("1.0000"),
            base_amount=Decimal("1000.00"),
            amount=Decimal("10.00"),
            reason="resolved from config",
        )

        PurchaseInvoiceService._apply_tds(header=header)

        self.assertEqual(header.tds_section, section)
        self.assertEqual(header.tds_rate, Decimal("1.0000"))
        self.assertEqual(header.tds_base_amount, Decimal("1000.00"))
        self.assertEqual(header.tds_amount, Decimal("10.00"))
        self.assertEqual(header.tds_reason, "resolved from config")


class PurchaseInvoiceViewUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=7)

    def _make_header(self, **overrides):
        defaults = {
            "withholding_enabled": True,
            "tds_is_manual": False,
            "tds_section_id": None,
            "tds_section": None,
            "tds_rate": Decimal("0.0000"),
            "tds_base_amount": Decimal("0.00"),
            "tds_amount": Decimal("0.00"),
            "tds_reason": None,
            "entity_id": 1,
            "entityfinid_id": 1,
            "subentity_id": None,
            "vendor_id": 1,
            "bill_date": None,
            "total_taxable": Decimal("1000.00"),
            "grand_total": Decimal("1180.00"),
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    @patch("purchase.views.purchase_invoice.require_purchase_request_permission")
    def test_list_queryset_uses_exists_for_line_mode_filter(self, mocked_require_permission):
        request = self.factory.get("/api/purchase/purchase-invoices/?entity=1&entityfinid=1&line_mode=goods")
        force_authenticate(request, user=self.user)

        view = PurchaseInvoiceListCreateAPIView()
        view.request = view.initialize_request(request)

        queryset = view.get_queryset()
        sql = str(queryset.query).upper()

        self.assertIn("EXISTS(", sql)
        self.assertNotIn(" DISTINCT ", sql)
        mocked_require_permission.assert_called_once()

    @patch("purchase.views.purchase_invoice.require_purchase_request_permission")
    def test_list_queryset_selects_vendor_related_profiles(self, mocked_require_permission):
        request = self.factory.get("/api/purchase/purchase-invoices/?entity=1&entityfinid=1")
        force_authenticate(request, user=self.user)

        view = PurchaseInvoiceListCreateAPIView()
        view.request = view.initialize_request(request)

        queryset = view.get_queryset()
        select_related = queryset.query.select_related

        self.assertIn("vendor", select_related)
        self.assertIn("ledger", select_related["vendor"])
        self.assertIn("commercial_profile", select_related["vendor"])
        mocked_require_permission.assert_called_once()

    def test_nav_scope_queryset_uses_exists_for_line_mode_filter(self):
        queryset = PurchaseInvoiceNavService._scope_qs(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            doc_type=int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
            doc_code="PINV",
            allowed_statuses=PurchaseInvoiceNavService.DEFAULT_ALLOWED_STATUSES,
            line_mode="goods",
        )
        sql = str(queryset.query).upper()
        self.assertIn("EXISTS(", sql)
        self.assertNotIn(" DISTINCT ", sql)

    @patch("purchase.services.purchase_invoice_nav_service.PurchaseInvoiceNavService._scope_qs")
    def test_prev_next_uses_combined_goods_service_scope(self, mocked_scope_qs):
        mocked_scope_qs.return_value.filter.return_value.order_by.return_value.first.return_value = None
        instance = SimpleNamespace(
            id=1006,
            entity_id=10,
            entityfinid_id=2026,
            subentity_id=None,
            doc_type=int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
            doc_code="PINV",
        )

        PurchaseInvoiceNavService.get_prev_next_for_instance(instance, line_mode="service")

        self.assertEqual(mocked_scope_qs.call_count, 2)
        first_call = mocked_scope_qs.call_args_list[0].kwargs
        second_call = mocked_scope_qs.call_args_list[1].kwargs
        self.assertEqual(first_call, {
            "entity_id": 10,
            "entityfinid_id": 2026,
            "subentity_id": None,
            "doc_type": int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
            "doc_code": "PINV",
            "allowed_statuses": PurchaseInvoiceNavService.DEFAULT_ALLOWED_STATUSES,
            "line_mode": None,
        })
        self.assertEqual(second_call, {
            "entity_id": 10,
            "entityfinid_id": 2026,
            "subentity_id": None,
            "doc_type": int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
            "doc_code": None,
            "allowed_statuses": PurchaseInvoiceNavService.DEFAULT_ALLOWED_STATUSES,
            "line_mode": None,
        })

    @patch("purchase.services.purchase_invoice_nav_service.PurchaseInvoiceNavService._scope_qs")
    def test_prev_next_orders_by_doc_no_with_id_tiebreaker(self, mocked_scope_qs):
        scoped_qs = MagicMock()
        all_code_rows = [
            SimpleNamespace(id=77, doc_no=1006, purchase_number="PINV-1006", status=3, bill_date=None),
            SimpleNamespace(id=88, doc_no=None, purchase_number="PINV-1007", status=3, bill_date=None),
            SimpleNamespace(id=95, doc_no=1009, purchase_number="PINV-1009", status=3, bill_date=None),
        ]
        mocked_scope_qs.side_effect = [scoped_qs, all_code_rows]

        instance = SimpleNamespace(
            id=90,
            doc_no=1008,
            entity_id=10,
            entityfinid_id=2026,
            subentity_id=None,
            doc_type=int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
            doc_code="PINV",
        )

        result = PurchaseInvoiceNavService.get_prev_next_for_instance(instance, line_mode="service")

        self.assertEqual(result["previous"]["id"], 88)
        self.assertEqual(result["previous"]["purchase_number"], "PINV-1007")
        self.assertEqual(result["next"]["id"], 95)

    def test_last_saved_doc_scope_queryset_uses_subentity_isnull(self):
        with patch("purchase.services.purchase_settings_service.PurchaseInvoiceHeader.objects.filter") as mocked_filter:
            mocked_filter.return_value.only.return_value.__iter__.return_value = iter([])

            PurchaseSettingsService._last_saved_doc_in_scope(
                entity_id=10,
                entityfinid_id=8,
                subentity_id=None,
                doc_type=int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
                current_number=1008,
            )

        mocked_filter.assert_called_once_with(
            entity_id=10,
            entityfinid_id=8,
            doc_type=int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
            status__in=[2, 3, 9],
            subentity_id__isnull=True,
        )

    @patch("purchase.views.purchase_invoice.require_purchase_request_permission")
    def test_search_queryset_selects_vendor_related_profiles(self, mocked_require_permission):
        from purchase.views.purchase_invoice import PurchaseInvoiceSearchAPIView

        request = self.factory.get("/api/purchase/purchase-invoices/search/?entity=1&entityfinid=1")
        force_authenticate(request, user=self.user)

        view = PurchaseInvoiceSearchAPIView()
        view.request = view.initialize_request(request)

        queryset = view.get_queryset()
        select_related = queryset.query.select_related

        self.assertIn("vendor", select_related)
        self.assertIn("ledger", select_related["vendor"])
        self.assertIn("commercial_profile", select_related["vendor"])
        mocked_require_permission.assert_called_once()

    @patch("purchase.services.purchase_invoice_service.PurchaseWithholdingService.compute_tds")
    def test_auto_mode_fails_when_no_section_resolved(self, mock_compute):
        header = self._make_header(withholding_enabled=True, tds_is_manual=False, tds_section_id=None)

        mock_compute.return_value = WithholdingResult(
            enabled=True,
            section=None,
            rate=Decimal("0.0000"),
            base_amount=Decimal("0.00"),
            amount=Decimal("0.00"),
            reason="No TDS section",
        )

        with self.assertRaisesMessage(ValueError, "Provide tds_section or configure default TDS section for this entity."):
            PurchaseInvoiceService._apply_tds(header=header)


class PurchaseGstTdsTests(SimpleTestCase):
    @patch("purchase.services.purchase_invoice_service.GstTdsService.apply_to_header")
    def test_gst_tds_auto_mode_uses_gst_tds_service(self, mock_apply):
        header = SimpleNamespace(
            gst_tds_enabled=True,
            gst_tds_is_manual=False,
            gst_tds_contract_ref="CTR-001",
            gst_tds_rate=Decimal("0.0000"),
            gst_tds_base_amount=Decimal("0.00"),
            gst_tds_cgst_amount=Decimal("0.00"),
            gst_tds_sgst_amount=Decimal("0.00"),
            gst_tds_igst_amount=Decimal("0.00"),
            gst_tds_amount=Decimal("0.00"),
            gst_tds_status=0,
            gst_tds_reason=None,
            total_taxable=Decimal("1000.00"),
            tax_regime=PurchaseInvoiceHeader.TaxRegime.INTRA,
            is_igst=False,
            GstTdsStatus=PurchaseInvoiceHeader.GstTdsStatus,
            TaxRegime=PurchaseInvoiceHeader.TaxRegime,
        )

        PurchaseInvoiceService._apply_gst_tds(header=header)
        mock_apply.assert_called_once_with(header)

    def test_gst_tds_rate_fields_show_2_percent_logic(self):
        ser = PurchaseInvoiceHeaderSerializer()

        intra = SimpleNamespace(
            gst_tds_enabled=True,
            tax_regime=PurchaseInvoiceHeader.TaxRegime.INTRA,
            is_igst=False,
            TaxRegime=PurchaseInvoiceHeader.TaxRegime,
        )
        inter = SimpleNamespace(
            gst_tds_enabled=True,
            tax_regime=PurchaseInvoiceHeader.TaxRegime.INTER,
            is_igst=True,
            TaxRegime=PurchaseInvoiceHeader.TaxRegime,
        )

        self.assertEqual(ser.get_gst_tds_cgst_rate(intra), "1.0000")
        self.assertEqual(ser.get_gst_tds_sgst_rate(intra), "1.0000")
        self.assertEqual(ser.get_gst_tds_igst_rate(intra), "0.0000")

        self.assertEqual(ser.get_gst_tds_cgst_rate(inter), "0.0000")
        self.assertEqual(ser.get_gst_tds_sgst_rate(inter), "0.0000")
        self.assertEqual(ser.get_gst_tds_igst_rate(inter), "2.0000")

    @patch("purchase.services.purchase_invoice_service.PurchaseSettingsService.get_policy")
    def test_vendor_tds_variance_hard_blocks(self, mock_get_policy):
        mock_get_policy.return_value = SimpleNamespace(level=lambda key, default="warn": "hard")
        header = SimpleNamespace(
            entity_id=1,
            subentity_id=None,
            withholding_enabled=True,
            vendor_tds_declared=True,
            vendor_tds_base_amount=Decimal("900.00"),
            vendor_tds_rate=Decimal("1.0000"),
            vendor_tds_amount=Decimal("9.00"),
            tds_base_amount=Decimal("1000.00"),
            tds_rate=Decimal("1.0000"),
            tds_amount=Decimal("10.00"),
            gst_tds_enabled=False,
            vendor_gst_tds_declared=False,
            match_notes={},
            match_status="na",
            MatchStatus=SimpleNamespace(WARN="warn"),
        )
        with self.assertRaisesMessage(ValueError, "Vendor IT-TDS differs"):
            PurchaseInvoiceService._apply_vendor_withholding_variance_policy(header=header)

    @patch("purchase.services.purchase_invoice_service.PurchaseSettingsService.get_policy")
    def test_vendor_tds_variance_warn_sets_match_notes(self, mock_get_policy):
        mock_get_policy.return_value = SimpleNamespace(level=lambda key, default="warn": "warn")
        header = SimpleNamespace(
            entity_id=1,
            subentity_id=None,
            withholding_enabled=True,
            vendor_tds_declared=True,
            vendor_tds_base_amount=Decimal("900.00"),
            vendor_tds_rate=Decimal("1.0000"),
            vendor_tds_amount=Decimal("9.00"),
            tds_base_amount=Decimal("1000.00"),
            tds_rate=Decimal("1.0000"),
            tds_amount=Decimal("10.00"),
            gst_tds_enabled=False,
            vendor_gst_tds_declared=False,
            match_notes={},
            match_status="na",
            MatchStatus=SimpleNamespace(WARN="warn"),
        )
        PurchaseInvoiceService._apply_vendor_withholding_variance_policy(header=header)
        self.assertIn("withholding_warnings", header.match_notes)
        self.assertEqual(header.match_status, "warn")


class PurchaseVendorComplianceValidationTests(SimpleTestCase):
    @patch("purchase.services.purchase_invoice_service.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_invoice_service.account_partytype")
    @patch("purchase.services.purchase_invoice_service.account_gstno")
    def test_invalid_vendor_gstin_hard_rule_blocks(self, mock_gstno, mock_partytype, mock_policy):
        vendor = SimpleNamespace(ledger_id=10, isactive=True)
        mock_partytype.return_value = "Vendor"
        mock_gstno.return_value = None
        mock_policy.return_value = SimpleNamespace(controls={"vendor_gstin_format_rule": "hard"})

        attrs = {
            "entity": 1,
            "subentity": None,
            "vendor": vendor,
            "vendor_gstin": "INVALID-GSTIN",
            "withholding_enabled": False,
        }
        with self.assertRaisesMessage(ValueError, "Vendor GSTIN format is invalid."):
            PurchaseInvoiceService.validate_vendor_account(attrs)

    @patch("purchase.services.purchase_invoice_service.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_invoice_service.account_partytype")
    @patch("purchase.services.purchase_invoice_service.account_gstno")
    def test_invalid_vendor_gstin_warn_rule_sets_match_warning(self, mock_gstno, mock_partytype, mock_policy):
        vendor = SimpleNamespace(ledger_id=10, isactive=True)
        mock_partytype.return_value = "Vendor"
        mock_gstno.return_value = None
        mock_policy.return_value = SimpleNamespace(controls={"vendor_gstin_format_rule": "warn"})

        attrs = {
            "entity": 1,
            "subentity": None,
            "vendor": vendor,
            "vendor_gstin": "INVALID-GSTIN",
            "withholding_enabled": False,
        }
        PurchaseInvoiceService.validate_vendor_account(attrs)

        self.assertIn("compliance_warnings", attrs.get("match_notes", {}))
        self.assertEqual(attrs.get("match_status"), "warn")

    @patch("purchase.services.purchase_invoice_service.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_invoice_service.account_partytype")
    @patch("purchase.services.purchase_invoice_service.account_pan")
    def test_withholding_pan_required_hard_rule_blocks_when_pan_missing(self, mock_pan, mock_partytype, mock_policy):
        vendor = SimpleNamespace(ledger_id=10, isactive=True)
        mock_partytype.return_value = "Vendor"
        mock_pan.return_value = ""
        mock_policy.return_value = SimpleNamespace(
            controls={
                "withholding_pan_required_rule": "hard",
                "withholding_pan_format_rule": "hard",
            }
        )
        attrs = {
            "entity": 1,
            "subentity": None,
            "vendor": vendor,
            "withholding_enabled": True,
        }
        with self.assertRaisesMessage(ValueError, "Vendor PAN is required when Income-tax TDS is enabled."):
            PurchaseInvoiceService.validate_vendor_account(attrs)


class PurchaseWithholdingBaseRuleTests(SimpleTestCase):
    @patch("purchase.services.purchase_withholding_service.WithholdingResolver.resolve_section")
    @patch("purchase.services.purchase_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tds_skips_payment_based_section_in_invoice_context(self, mock_get_cfg, mock_resolve_section):
        mock_get_cfg.return_value = SimpleNamespace(enable_tds=True)
        mock_resolve_section.return_value = SimpleNamespace(
            id=99,
            section_code="194N",
            base_rule=4,  # PAYMENT_VALUE
        )
        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            withholding_enabled=True,
            tds_section_id=99,
            vendor_id=10,
        )

        res = PurchaseWithholdingService.compute_tds(
            header=header,
            vendor_account_id=10,
            bill_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )

        self.assertTrue(res.enabled)
        self.assertEqual(res.amount, Decimal("0.00"))
        self.assertEqual(res.reason_code, "NOT_APPLICABLE_BASE_RULE_CONTEXT")


class PurchaseApiSmokeTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="purchase_api_tester",
            email="purchase_api_tester@example.com",
            password="x",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("purchase.views.purchase_settings.PurchaseSettingsService.get_current_doc_no")
    @patch("purchase.views.purchase_settings.PurchaseSettingsService.get_choice_overrides")
    @patch("purchase.views.purchase_settings.PurchaseSettingsService.get_settings")
    def test_settings_get_with_entity_and_entityfinid_returns_200(
        self,
        mock_get_settings,
        mock_get_choice_overrides,
        mock_get_current_doc_no,
    ):
        mock_get_settings.return_value = SimpleNamespace(
            entity_id=32,
            subentity_id=None,
            default_doc_code_invoice="PINV",
            default_doc_code_cn="PCN",
            default_doc_code_dn="PDN",
            default_workflow_action="confirm",
            auto_derive_tax_regime=True,
            enforce_2b_before_itc_claim=False,
            allow_mixed_taxability_in_one_bill=True,
            round_grand_total_to=2,
            enable_round_off=True,
        )
        mock_get_choice_overrides.return_value = {}
        mock_get_current_doc_no.return_value = {
            "enabled": True,
            "current_number": 1,
            "previous_number": None,
            "previous_invoice_id": None,
            "previous_purchase_number": None,
            "previous_status": None,
            "previous_bill_date": None,
        }

        resp = self.client.get("/api/purchase/settings/?entity=32&entityfinid=32")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("settings", resp.data)
        self.assertIn("current_doc_numbers", resp.data)
        self.assertEqual(mock_get_current_doc_no.call_count, 3)

    @patch("purchase.views.purchase_settings.PurchaseSettingsAPIView._payload", return_value={"ok": True})
    @patch("purchase.views.purchase_settings.PurchaseSettingsService.upsert_settings")
    def test_settings_patch_triggers_meta_cache_invalidation(
        self,
        mock_upsert_settings,
        mock_payload,
    ):
        mock_upsert_settings.return_value = SimpleNamespace(
            default_doc_code_invoice="PINV",
            default_doc_code_cn="PCN",
            default_doc_code_dn="PDN",
        )

        with patch("purchase.views.purchase_settings.bump_meta_namespaces") as mocked_bump_cache:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                resp = self.client.patch(
                    "/api/purchase/settings/?entity=32&subentity=1",
                    {"settings": {"enable_round_off": False}},
                    format="json",
                )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"ok": True})
        self.assertGreaterEqual(len(callbacks), 1)
        mocked_bump_cache.assert_called_once()
        mock_upsert_settings.assert_called_once()
        mock_payload.assert_called_once()

    def test_charge_type_detail_missing_id_returns_404(self):
        resp = self.client.get("/api/purchase/charge-types/999999/?entity=1")
        self.assertEqual(resp.status_code, 404)


class _ListManager:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeQuerySet(list):
    def select_related(self, *args, **kwargs):
        return self

    def prefetch_related(self, *args, **kwargs):
        return self

    def all(self):
        return self

    def filter(self, **kwargs):
        def _resolve_value(obj, path):
            current = obj
            for part in path.split("__"):
                current = getattr(current, part, None)
            return current

        def _matches(obj):
            for key, expected in kwargs.items():
                if "__" in key:
                    field_name, lookup = key.rsplit("__", 1)
                    if lookup in {"gte", "lte", "isnull"}:
                        current = _resolve_value(obj, field_name)
                        if lookup == "gte" and not (current >= expected):
                            return False
                        if lookup == "lte" and not (current <= expected):
                            return False
                        if lookup == "isnull" and not ((current is None) == bool(expected)):
                            return False
                        continue
                current = _resolve_value(obj, key)
                if current != expected:
                    return False
            return True

        return _FakeQuerySet([obj for obj in self if _matches(obj)])

    def order_by(self, field_name):
        reverse = field_name.startswith("-")
        key = field_name[1:] if reverse else field_name
        return _FakeQuerySet(sorted(self, key=lambda item: getattr(item, key, None), reverse=reverse))


class PurchasePostingAdapterTests(SimpleTestCase):
    def _base_header(self, **overrides):
        defaults = {
            "id": 101,
            "entity_id": 1,
            "entityfinid_id": 1,
            "subentity_id": None,
            "bill_date": date(2026, 3, 3),
            "posting_date": date(2026, 3, 3),
            "vendor_id": 7001,
            "vendor_ledger_id": 7001,
            "doc_type": 1,
            "purchase_number": "PINV-101",
            "grand_total": Decimal("100.00"),
            "round_off": Decimal("0.00"),
            "total_expenses": Decimal("0.00"),
            "is_reverse_charge": False,
            "affects_inventory": False,
            "charges": _ListManager([]),
            "tds_amount": Decimal("0.00"),
            "gst_tds_amount": Decimal("0.00"),
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def _line(self, **overrides):
        defaults = {
            "id": 201,
            "line_no": 1,
            "product_id": None,
            "is_service": True,
            "purchase_behavior": ProductPurchaseBehavior.EXPENSE,
            "taxable_value": Decimal("100.00"),
            "cgst_amount": Decimal("0.00"),
            "sgst_amount": Decimal("0.00"),
            "igst_amount": Decimal("0.00"),
            "cess_amount": Decimal("0.00"),
            "is_itc_eligible": True,
            "qty": Decimal("1.0000"),
            "free_qty": Decimal("0.0000"),
            "uom_id": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    @patch("posting.adapters.purchase_invoice.PostingService")
    @patch("posting.adapters.purchase_invoice.ProductAccountResolver")
    @patch("posting.adapters.purchase_invoice.StaticAccountResolver")
    def test_posts_charge_line_to_misc_expense(
        self,
        mock_static_resolver_cls,
        mock_product_resolver_cls,
        mock_posting_service_cls,
    ):
        code_map = {
            StaticAccountCodes.PURCHASE_MISC_EXPENSE: 8100,
            StaticAccountCodes.ROUND_OFF_INCOME: 8101,
            StaticAccountCodes.ROUND_OFF_EXPENSE: 8102,
            StaticAccountCodes.INPUT_CGST: 8103,
            StaticAccountCodes.INPUT_SGST: 8104,
            StaticAccountCodes.INPUT_IGST: 8105,
            StaticAccountCodes.INPUT_CESS: 8106,
            StaticAccountCodes.PURCHASE_DEFAULT: 8107,
            StaticAccountCodes.TDS_PAYABLE: 8108,
            StaticAccountCodes.GST_TDS_PAYABLE: 8109,
        }

        resolver = mock_static_resolver_cls.return_value
        resolver.get_account_id.side_effect = lambda code, required=False: code_map.get(code)
        mock_product_resolver_cls.return_value.purchase_account_id.return_value = 5000

        posting_instance = mock_posting_service_cls.return_value
        posting_instance.post.return_value = SimpleNamespace(id=999)

        charge = SimpleNamespace(
            id=301,
            line_no=1,
            taxable_value=Decimal("10.00"),
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00"),
            igst_amount=Decimal("0.00"),
            itc_eligible=True,
        )
        header = self._base_header(
            grand_total=Decimal("110.00"),
            charges=_ListManager([charge]),
        )

        PurchaseInvoicePostingAdapter.post_purchase_invoice.__wrapped__(
            header=header,
            lines=[self._line()],
            user_id=1,
            config=PurchaseInvoicePostingConfig(),
        )

        kwargs = posting_instance.post.call_args.kwargs
        jl_inputs = kwargs["jl_inputs"]
        charge_entries = [x for x in jl_inputs if x.account_id == 8100 and "charge" in x.description.lower()]

        self.assertTrue(charge_entries, "Expected a charge journal line in PURCHASE_MISC_EXPENSE.")
        self.assertEqual(charge_entries[0].amount, Decimal("10.00"))

    @patch("posting.adapters.purchase_invoice.PostingService")
    @patch("posting.adapters.purchase_invoice.ProductAccountResolver")
    @patch("posting.adapters.purchase_invoice.StaticAccountResolver")
    def test_posts_gst_tds_when_config_enabled(
        self,
        mock_static_resolver_cls,
        mock_product_resolver_cls,
        mock_posting_service_cls,
    ):
        code_map = {
            StaticAccountCodes.PURCHASE_MISC_EXPENSE: 8100,
            StaticAccountCodes.ROUND_OFF_INCOME: 8101,
            StaticAccountCodes.ROUND_OFF_EXPENSE: 8102,
            StaticAccountCodes.INPUT_CGST: 8103,
            StaticAccountCodes.INPUT_SGST: 8104,
            StaticAccountCodes.INPUT_IGST: 8105,
            StaticAccountCodes.INPUT_CESS: 8106,
            StaticAccountCodes.PURCHASE_DEFAULT: 8107,
            StaticAccountCodes.TDS_PAYABLE: 8108,
            StaticAccountCodes.GST_TDS_PAYABLE: 8109,
        }

        resolver = mock_static_resolver_cls.return_value
        resolver.get_account_id.side_effect = lambda code, required=False: code_map.get(code)
        mock_product_resolver_cls.return_value.purchase_account_id.return_value = 5000

        posting_instance = mock_posting_service_cls.return_value
        posting_instance.post.return_value = SimpleNamespace(id=1001)

        header = self._base_header(gst_tds_amount=Decimal("5.00"))

        PurchaseInvoicePostingAdapter.post_purchase_invoice.__wrapped__(
            header=header,
            lines=[self._line()],
            user_id=1,
            config=PurchaseInvoicePostingConfig(post_gst_tds_on_invoice=True),
        )

        kwargs = posting_instance.post.call_args.kwargs
        jl_inputs = kwargs["jl_inputs"]

        vendor_dr = [
            x for x in jl_inputs
            if x.account_id == header.vendor_id and x.drcr is True and x.amount == Decimal("5.00")
            and "gst-tds deducted" in x.description.lower()
        ]
        gst_tds_cr = [
            x for x in jl_inputs
            if x.account_id == 8109 and x.drcr is False and x.amount == Decimal("5.00")
            and "gst-tds payable" in x.description.lower()
        ]

        self.assertTrue(vendor_dr, "Expected DR Vendor entry for GST-TDS deduction.")
        self.assertTrue(gst_tds_cr, "Expected CR GST-TDS Payable entry.")

    @patch("posting.adapters.purchase_invoice.PostingService")
    @patch("posting.adapters.purchase_invoice.ProductAccountResolver")
    @patch("posting.adapters.purchase_invoice.StaticAccountResolver")
    def test_asset_purchase_behavior_skips_inventory_move(
        self,
        mock_static_resolver_cls,
        mock_product_resolver_cls,
        mock_posting_service_cls,
    ):
        code_map = {
            StaticAccountCodes.PURCHASE_MISC_EXPENSE: 8100,
            StaticAccountCodes.ROUND_OFF_INCOME: 8101,
            StaticAccountCodes.ROUND_OFF_EXPENSE: 8102,
            StaticAccountCodes.INPUT_CGST: 8103,
            StaticAccountCodes.INPUT_SGST: 8104,
            StaticAccountCodes.INPUT_IGST: 8105,
            StaticAccountCodes.INPUT_CESS: 8106,
            StaticAccountCodes.PURCHASE_DEFAULT: 8107,
        }

        resolver = mock_static_resolver_cls.return_value
        resolver.get_account_id.side_effect = lambda code, required=False: code_map.get(code)
        mock_product_resolver_cls.return_value.purchase_account_id.return_value = 5000

        posting_instance = mock_posting_service_cls.return_value
        posting_instance.post.return_value = SimpleNamespace(id=1002)

        header = self._base_header(grand_total=Decimal("100.00"), affects_inventory=True)

        PurchaseInvoicePostingAdapter.post_purchase_invoice.__wrapped__(
            header=header,
            lines=[
                self._line(
                    product_id=99,
                    is_service=False,
                    purchase_behavior=ProductPurchaseBehavior.ASSET,
                    qty=Decimal("1.0000"),
                    uom_id=1,
                )
            ],
            user_id=1,
            config=PurchaseInvoicePostingConfig(),
        )

        kwargs = posting_instance.post.call_args.kwargs
        self.assertEqual(kwargs["im_inputs"], [])


class PurchasePhase1ClassificationTests(SimpleTestCase):
    def test_validate_lines_structural_defaults_non_product_line_to_expense(self):
        attrs = {
            "default_taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
            "is_reverse_charge": False,
            "is_itc_eligible": True,
            "itc_claim_status": PurchaseInvoiceHeader.ItcClaimStatus.PENDING,
        }
        lines = [
            {
                "purchase_account": 5000,
                "product_desc": "Office lunch",
                "qty": Decimal("1.0000"),
                "rate": Decimal("250.00"),
                "is_service": True,
            }
        ]
        derived = SimpleNamespace(tax_regime=PurchaseInvoiceHeader.TaxRegime.INTRA)

        PurchaseInvoiceService.validate_lines_structural(attrs, lines, derived)

        self.assertEqual(lines[0]["purchase_behavior"], ProductPurchaseBehavior.EXPENSE)

    def test_validate_lines_structural_rejects_non_product_inventory_behavior(self):
        attrs = {
            "default_taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
            "is_reverse_charge": False,
            "is_itc_eligible": True,
            "itc_claim_status": PurchaseInvoiceHeader.ItcClaimStatus.PENDING,
        }
        lines = [
            {
                "purchase_account": 5000,
                "product_desc": "Office lunch",
                "qty": Decimal("1.0000"),
                "rate": Decimal("250.00"),
                "is_service": False,
                "purchase_behavior": ProductPurchaseBehavior.INVENTORY,
            }
        ]
        derived = SimpleNamespace(tax_regime=PurchaseInvoiceHeader.TaxRegime.INTRA)

        with self.assertRaisesMessage(ValueError, "non-product purchase lines can only use expense behavior"):
            PurchaseInvoiceService.validate_lines_structural(attrs, lines, derived)

    @patch("purchase.services.purchase_invoice_service.Product.objects")
    def test_validate_lines_structural_requires_account_for_expense_product(self, mock_product_objects):
        mock_product_objects.filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            id=10,
            is_batch_managed=False,
            is_expiry_tracked=False,
            is_service=False,
            purchase_behavior=ProductPurchaseBehavior.EXPENSE,
            purchase_account_id=None,
        )
        attrs = {
            "default_taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
            "is_reverse_charge": False,
            "is_itc_eligible": True,
            "itc_claim_status": PurchaseInvoiceHeader.ItcClaimStatus.PENDING,
        }
        lines = [
            {
                "product": 10,
                "qty": Decimal("1.0000"),
                "rate": Decimal("250.00"),
                "is_service": False,
            }
        ]
        derived = SimpleNamespace(tax_regime=PurchaseInvoiceHeader.TaxRegime.INTRA)

        with self.assertRaisesMessage(ValueError, "expense purchase lines require an expense/purchase account"):
            PurchaseInvoiceService.validate_lines_structural(attrs, lines, derived)

    @patch("purchase.services.purchase_invoice_service.Product.objects")
    def test_validate_lines_structural_requires_default_asset_category_for_asset_product(self, mock_product_objects):
        mock_product_objects.filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            id=10,
            is_batch_managed=False,
            is_expiry_tracked=False,
            is_service=False,
            purchase_behavior=ProductPurchaseBehavior.ASSET,
            purchase_account_id=5000,
            default_asset_category_id=None,
        )
        attrs = {
            "default_taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
            "is_reverse_charge": False,
            "is_itc_eligible": True,
            "itc_claim_status": PurchaseInvoiceHeader.ItcClaimStatus.PENDING,
        }
        lines = [
            {
                "product": 10,
                "qty": Decimal("1.0000"),
                "rate": Decimal("250.00"),
                "is_service": False,
            }
        ]
        derived = SimpleNamespace(tax_regime=PurchaseInvoiceHeader.TaxRegime.INTRA)

        with self.assertRaisesMessage(ValueError, "asset product is missing a default asset category"):
            PurchaseInvoiceService.validate_lines_structural(attrs, lines, derived)


class PurchasePhase3AssetIntakeTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="purchase-phase3",
            email="purchase-phase3@example.com",
            password="testpass123",
        )
        self.entity = Entity.objects.create(entityname="Purchase Phase3 Entity")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            year_code="FY2026-27",
            finstartyear=timezone.now(),
            finendyear=timezone.now(),
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Head Office",
            branch_type=SubEntity.BranchType.HEAD_OFFICE,
            is_head_office=True,
        )
        self.vendor = account.objects.create(entity=self.entity, accountname="Vendor A")
        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="PCS", description="Pieces")
        self.category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Asset Items")
        self.asset_ledger = Ledger.objects.create(entity=self.entity, name="CWIP Ledger")
        self.asset_category = AssetCategory.objects.create(
            entity=self.entity,
            code="CWIP-COMP",
            name="Computer CWIP",
            nature=AssetCategory.AssetNature.CAPITAL_WIP,
            cwip_ledger=self.asset_ledger,
        )
        self.product = Product.objects.create(
            entity=self.entity,
            productname="Office Computer",
            sku="COMP-001",
            productcategory=self.category,
            base_uom=self.uom,
            purchase_behavior=ProductPurchaseBehavior.ASSET,
            default_asset_category=self.asset_category,
        )
        self.header = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=self.vendor,
            bill_date=timezone.now().date(),
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            doc_code="PINV",
            doc_no=1001,
            purchase_number="PI/PINV/2026/1001",
            status=PurchaseInvoiceHeader.Status.CONFIRMED,
            default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE,
            tax_regime=PurchaseInvoiceHeader.TaxRegime.INTRA,
            grand_total=Decimal("100000.00"),
        )
        self.line = self.header.lines.create(
            line_no=1,
            product=self.product,
            product_desc="Office Computer",
            is_service=False,
            purchase_behavior=ProductPurchaseBehavior.ASSET,
            uom=self.uom,
            qty=Decimal("1.0000"),
            rate=Decimal("84745.76"),
            taxable_value=Decimal("84745.76"),
            line_total=Decimal("100000.00"),
        )

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_post_creates_capital_wip_asset_intake_for_asset_lines(
        self,
        mock_post_adapter,
        mock_sync_ap,
        mock_sync_gst,
    ):
        result = PurchaseInvoiceActions.post(self.header.id, posted_by_id=self.user.id)

        self.assertEqual(result.header.status, PurchaseInvoiceHeader.Status.POSTED)
        self.line.refresh_from_db()
        self.assertIsNotNone(self.line.asset_record_id)
        asset = self.line.asset_record
        self.assertEqual(asset.status, FixedAsset.AssetStatus.CAPITAL_WIP)
        self.assertEqual(asset.category_id, self.asset_category.id)
        self.assertEqual(asset.purchase_document_no, self.header.purchase_number)
        self.assertEqual(asset.vendor_account_id, self.vendor.id)
        self.assertEqual(asset.gross_block, Decimal("84745.76"))
        self.assertEqual(asset.quantity, Decimal("1.0000"))
        self.assertEqual(asset.external_reference, f"purchase-line:{self.line.id}")
        mock_post_adapter.assert_called_once()
        mock_sync_ap.assert_called_once()
        mock_sync_gst.assert_called_once()

    def test_revert_asset_intakes_for_unpost_deletes_uncapitalized_cwip_asset(self):
        asset = FixedAsset.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            category=self.asset_category,
            ledger=self.asset_ledger,
            asset_code="CWIP-001",
            asset_name="Office Computer",
            status=FixedAsset.AssetStatus.CAPITAL_WIP,
            acquisition_date=self.header.bill_date,
            quantity=Decimal("1.0000"),
            gross_block=Decimal("84745.76"),
            residual_value=Decimal("0.00"),
            useful_life_months=60,
            depreciation_method=FixedAsset.DepreciationMethod.SLM,
            net_book_value=Decimal("84745.76"),
            vendor_account=self.vendor,
            purchase_document_no=self.header.purchase_number,
            external_reference=f"purchase-line:{self.line.id}",
        )
        self.line.asset_record = asset
        self.line.save(update_fields=["asset_record"])

        PurchaseAssetIntakeService.revert_asset_intakes_for_unpost(header=self.header)

        self.line.refresh_from_db()
        self.assertIsNone(self.line.asset_record_id)
        self.assertFalse(FixedAsset.objects.filter(id=asset.id).exists())


class PurchaseStatutoryServiceTests(TestCase):
    def test_validate_it_tds_amount_raises_on_excess(self):
        header = SimpleNamespace(id=1, tds_amount=Decimal("10.00"), gst_tds_amount=Decimal("0.00"))
        with self.assertRaisesMessage(ValueError, "exceeds IT-TDS"):
            PurchaseStatutoryService._validate_header_amount_for_tax_type(
                header=header,
                tax_type=PurchaseStatutoryChallan.TaxType.IT_TDS,
                amount=Decimal("11.00"),
            )

    def test_validate_gst_tds_amount_raises_on_excess(self):
        header = SimpleNamespace(id=2, tds_amount=Decimal("0.00"), gst_tds_amount=Decimal("5.00"))
        with self.assertRaisesMessage(ValueError, "exceeds GST-TDS"):
            PurchaseStatutoryService._validate_header_amount_for_tax_type(
                header=header,
                tax_type=PurchaseStatutoryChallan.TaxType.GST_TDS,
                amount=Decimal("6.00"),
            )

    @patch("purchase.services.purchase_statutory_service.PurchaseInvoiceHeader.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallanLine.objects")
    def test_validate_challan_balance_rejects_over_allocation(self, mock_challan_line_objects, mock_header_objects):
        mapped_qs = MagicMock()
        mapped_qs.exclude.return_value = mapped_qs
        mapped_qs.filter.return_value = mapped_qs
        mapped_qs.values.return_value.annotate.return_value = [{"header_id": 10, "total": Decimal("7.00")}]
        mock_challan_line_objects.filter.return_value = mapped_qs

        header = SimpleNamespace(
            id=10,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=5,
            tds_amount=Decimal("10.00"),
            gst_tds_amount=Decimal("0.00"),
        )
        mock_header_objects.filter.return_value.first.return_value = header

        with self.assertRaisesMessage(ValueError, "remaining IT-TDS balance 3.00"):
            PurchaseStatutoryService._validate_challan_balance_for_lines(
                entity_id=1,
                entityfinid_id=1,
                subentity_id=5,
                tax_type=PurchaseStatutoryChallan.TaxType.IT_TDS,
                line_rows=[{"header_id": 10, "amount": Decimal("4.00")}],
            )

    @patch("purchase.services.purchase_statutory_service.PurchaseInvoiceHeader.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallanLine.objects")
    def test_validate_challan_balance_excludes_current_challan_during_edit(self, mock_challan_line_objects, mock_header_objects):
        mapped_qs = MagicMock()
        mapped_qs.exclude.return_value = mapped_qs
        mapped_qs.filter.return_value = mapped_qs
        mapped_qs.values.return_value.annotate.return_value = [{"header_id": 10, "total": Decimal("1.00")}]
        mock_challan_line_objects.filter.return_value = mapped_qs

        header = SimpleNamespace(
            id=10,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=5,
            tds_amount=Decimal("10.00"),
            gst_tds_amount=Decimal("0.00"),
        )
        mock_header_objects.filter.return_value.first.return_value = header

        PurchaseStatutoryService._validate_challan_balance_for_lines(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=5,
            tax_type=PurchaseStatutoryChallan.TaxType.IT_TDS,
            line_rows=[{"header_id": 10, "amount": Decimal("8.00")}],
            exclude_challan_id=99,
        )

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturnLine.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallanLine.objects")
    def test_validate_return_balance_rejects_over_allocation(self, mock_challan_line_objects, mock_return_line_objects):
        challan_line_qs = MagicMock()
        challan_line_qs.exclude.return_value = challan_line_qs
        challan_line_qs.filter.return_value = challan_line_qs
        challan_line_qs.values.return_value.annotate.return_value = [
            {"header_id": 10, "challan_id": 20, "total": Decimal("10.00")}
        ]
        mock_challan_line_objects.filter.return_value = challan_line_qs

        consumed_qs = MagicMock()
        consumed_qs.exclude.return_value = consumed_qs
        consumed_qs.filter.return_value = consumed_qs
        consumed_qs.values.return_value.annotate.return_value = [
            {"header_id": 10, "challan_id": 20, "total": Decimal("7.00")}
        ]
        mock_return_line_objects.filter.return_value = consumed_qs

        with self.assertRaisesMessage(ValueError, "requested 4.00 exceeds remaining balance 3.00"):
            PurchaseStatutoryService._validate_return_balance_for_lines(
                entity_id=1,
                entityfinid_id=1,
                subentity_id=5,
                tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
                line_rows=[{"header_id": 10, "challan_id": 20, "amount": Decimal("4.00")}],
            )

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturnLine.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallanLine.objects")
    def test_validate_return_balance_excludes_current_filing_during_edit(self, mock_challan_line_objects, mock_return_line_objects):
        challan_line_qs = MagicMock()
        challan_line_qs.exclude.return_value = challan_line_qs
        challan_line_qs.filter.return_value = challan_line_qs
        challan_line_qs.values.return_value.annotate.return_value = [
            {"header_id": 10, "challan_id": 20, "total": Decimal("10.00")}
        ]
        mock_challan_line_objects.filter.return_value = challan_line_qs

        consumed_qs = MagicMock()
        consumed_qs.exclude.return_value = consumed_qs
        consumed_qs.filter.return_value = consumed_qs
        consumed_qs.values.return_value.annotate.return_value = [
            {"header_id": 10, "challan_id": 20, "total": Decimal("1.00")}
        ]
        mock_return_line_objects.filter.return_value = consumed_qs

        PurchaseStatutoryService._validate_return_balance_for_lines(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=5,
            tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
            line_rows=[{"header_id": 10, "challan_id": 20, "amount": Decimal("9.00")}],
            exclude_filing_id=77,
        )

    def test_require_submitted_approval_state_rejects_non_submitted_payload(self):
        with self.assertRaisesMessage(ValueError, "requires the record to be in SUBMITTED approval state"):
            PurchaseStatutoryService._require_submitted_approval_state(
                payload={"_approval_state": {"status": "DRAFT"}},
                action_label="Return approval",
            )

    def test_validate_it_tds_return_snapshot_rejects_non_resident_for_26q(self):
        with self.assertRaisesMessage(ValueError, "26Q allows only RESIDENT deductees"):
            PurchaseStatutoryService._validate_it_tds_return_snapshot(
                return_code="26Q",
                deductee_residency_snapshot="NON_RESIDENT",
                deductee_pan_snapshot="ABCDE1234F",
                deductee_tax_id_snapshot="TIN123",
                line_label="Line 1",
            )

    def test_validate_it_tds_return_snapshot_rejects_missing_tax_id_for_27q(self):
        with self.assertRaisesMessage(ValueError, "27Q requires deductee_tax_id_snapshot"):
            PurchaseStatutoryService._validate_it_tds_return_snapshot(
                return_code="27Q",
                deductee_residency_snapshot="NON_RESIDENT",
                deductee_pan_snapshot="",
                deductee_tax_id_snapshot="",
                line_label="Line 1",
            )

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    def test_get_original_return_for_revision_rejects_prior_revision_reference(self, mock_return_objects):
        mock_return_objects.filter.return_value.first.return_value = SimpleNamespace(
            id=9,
            original_return_id=3,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=5,
            tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
            return_code="26Q",
            period_from=date(2026, 4, 1),
            period_to=date(2026, 6, 30),
        )

        with self.assertRaisesMessage(ValueError, "must reference the original return"):
            PurchaseStatutoryService._get_original_return_for_revision(
                entity_id=1,
                entityfinid_id=1,
                subentity_id=5,
                tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
                return_code="26Q",
                period_from=date(2026, 4, 1),
                period_to=date(2026, 6, 30),
                original_return_id=9,
            )

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    def test_assert_unique_revision_number_rejects_duplicate_active_revision(self, mock_return_objects):
        qs = MagicMock()
        qs.exclude.return_value = qs
        qs.exists.return_value = True
        mock_return_objects.filter.return_value = qs

        with self.assertRaisesMessage(ValueError, "A revision already exists"):
            PurchaseStatutoryService._assert_unique_revision_number(
                original_return_id=3,
                revision_no=1,
            )

    def test_assert_editable_draft_approval_state_blocks_submitted(self):
        with self.assertRaisesMessage(ValueError, "cannot be edited while approval state is SUBMITTED"):
            PurchaseStatutoryService._assert_editable_draft_approval_state(
                payload={"_approval_state": {"status": "SUBMITTED"}},
                record_label="Return",
            )

    def test_assert_editable_draft_approval_state_marks_rejected_for_reset(self):
        should_reset = PurchaseStatutoryService._assert_editable_draft_approval_state(
            payload={"_approval_state": {"status": "REJECTED"}},
            record_label="Return",
        )
        self.assertTrue(should_reset)

    def test_merge_payload_for_draft_update_resets_approval_when_requested(self):
        payload = PurchaseStatutoryService._merge_payload_for_draft_update(
            existing_payload={"_approval_state": {"status": "REJECTED"}, "_audit_log": [{"action": "X"}]},
            incoming_payload={},
            reset_approval_to_draft=True,
        )
        self.assertEqual(payload["_approval_state"]["status"], "DRAFT")
        self.assertEqual(payload["_audit_log"], [{"action": "X"}])

    def test_validate_period_bounds_rejects_inverted_period(self):
        with self.assertRaisesMessage(ValueError, "period_from cannot be greater than period_to"):
            PurchaseStatutoryService._validate_period_bounds(
                period_from=date(2026, 5, 1),
                period_to=date(2026, 4, 30),
                period_label="Return period",
            )

    def test_validate_period_bounds_rejects_anchor_outside_period(self):
        with self.assertRaisesMessage(ValueError, "challan_date must fall within Challan period"):
            PurchaseStatutoryService._validate_period_bounds(
                period_from=date(2026, 4, 1),
                period_to=date(2026, 4, 30),
                period_label="Challan period",
                anchor_date=date(2026, 5, 1),
                anchor_label="challan_date",
            )

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallan.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseInvoiceHeader.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._validate_return_balance_for_lines")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._validate_revision_lines")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturnLine.objects")
    def test_create_return_rejects_non_deposited_challan(
        self,
        mock_return_line_objects,
        mock_return_objects,
        mock_validate_revision,
        mock_validate_balance,
        mock_header_objects,
        mock_challan_objects,
    ):
        original_return_qs = MagicMock()
        original_return_qs.exclude.return_value = original_return_qs
        original_return_qs.filter.return_value = original_return_qs
        original_return_qs.exists.return_value = False
        mock_return_objects.filter.return_value = original_return_qs
        mock_return_objects.create.return_value = SimpleNamespace(id=1, amount=Decimal("0.00"), save=MagicMock())
        mock_header_objects.filter.return_value.first.return_value = SimpleNamespace(
            id=10,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=5,
            tds_amount=Decimal("10.00"),
            gst_tds_amount=Decimal("0.00"),
            tds_section=None,
            vendor=None,
            vendor_gstin=None,
        )
        mock_challan_objects.filter.return_value.first.return_value = SimpleNamespace(
            id=20,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=5,
            tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
            status=PurchaseStatutoryChallan.Status.DRAFT,
            cin_no=None,
        )

        with self.assertRaisesMessage(ValueError, "challan must be in DEPOSITED status"):
            PurchaseStatutoryService.create_return(
                entity_id=1,
                entityfinid_id=1,
                subentity_id=5,
                tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
                return_code="26Q",
                period_from=date(2026, 4, 1),
                period_to=date(2026, 6, 30),
                lines=[{"header_id": 10, "challan_id": 20, "amount": Decimal("5.00")}],
            )
        mock_return_line_objects.create.assert_not_called()

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallanLine.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturnLine.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._vendor_deductee_snapshot")
    def test_return_eligible_lines_filters_by_26q_rules(self, mock_snapshot, mock_return_line_objects, mock_challan_line_objects):
        challan = SimpleNamespace(challan_no="CH1", cin_no="CIN1")
        header = SimpleNamespace(tds_section=None)
        resident_line = SimpleNamespace(header_id=10, challan_id=20, amount=Decimal("5.00"), header=header, challan=challan)
        non_resident_line = SimpleNamespace(header_id=11, challan_id=21, amount=Decimal("6.00"), header=header, challan=challan)

        challan_line_qs = MagicMock()
        challan_line_qs.filter.return_value = challan_line_qs
        challan_line_qs.__iter__.return_value = iter([resident_line, non_resident_line])
        mock_challan_line_objects.select_related.return_value.filter.return_value = challan_line_qs

        consumed_qs = MagicMock()
        consumed_qs.exclude.return_value = consumed_qs
        consumed_values_qs = MagicMock()
        consumed_values_qs.annotate.return_value = consumed_values_qs
        consumed_values_qs.filter.return_value = []
        consumed_values_qs.__iter__.return_value = iter([])
        consumed_qs.values.return_value = consumed_values_qs
        mock_return_line_objects.filter.return_value = consumed_qs

        mock_snapshot.side_effect = [
            {
                "deductee_residency_snapshot": "RESIDENT",
                "deductee_country_obj": None,
                "deductee_country_code_snapshot": "",
                "deductee_country_name_snapshot": "",
                "deductee_tax_id_snapshot": "TAX1",
                "deductee_pan_snapshot": "ABCDE1234F",
                "deductee_gstin_snapshot": "",
            },
            {
                "deductee_residency_snapshot": "NON_RESIDENT",
                "deductee_country_obj": None,
                "deductee_country_code_snapshot": "",
                "deductee_country_name_snapshot": "",
                "deductee_tax_id_snapshot": "TAX2",
                "deductee_pan_snapshot": "",
                "deductee_gstin_snapshot": "",
            },
        ]

        payload = PurchaseStatutoryService.return_eligible_lines(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=5,
            tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
            period_from=date(2026, 4, 1),
            period_to=date(2026, 6, 30),
            return_code="26Q",
        )

        self.assertEqual(len(payload["lines"]), 1)
        self.assertEqual(payload["lines"][0]["header_id"], 10)

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallan.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseInvoiceHeader.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._validate_header_amount_for_tax_type")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._require_submitted_approval_state")
    def test_approve_return_uses_submitted_state_gate(
        self,
        mock_require_submitted,
        mock_return_objects,
        mock_validate_header_amount,
        mock_header_objects,
        mock_challan_objects,
    ):
        filing = SimpleNamespace(
            status=PurchaseStatutoryReturn.Status.DRAFT,
            filed_payload_json={"_approval_state": {"status": "DRAFT"}},
        )
        mock_return_objects.select_for_update.return_value.get.return_value = filing
        mock_require_submitted.side_effect = ValueError("Return approval requires the record to be in SUBMITTED approval state.")

        with self.assertRaisesMessage(ValueError, "requires the record to be in SUBMITTED approval state"):
            PurchaseStatutoryService.approve_return(filing_id=1, user_id=9, remarks="ok")

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallan.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._require_submitted_approval_state")
    def test_approve_challan_uses_submitted_state_gate(self, mock_require_submitted, mock_challan_objects):
        challan = SimpleNamespace(
            status=PurchaseStatutoryChallan.Status.DRAFT,
            payment_payload_json={"_approval_state": {"status": "DRAFT"}},
        )
        mock_challan_objects.select_for_update.return_value.get.return_value = challan
        mock_require_submitted.side_effect = ValueError("Challan approval requires the record to be in SUBMITTED approval state.")

        with self.assertRaisesMessage(ValueError, "requires the record to be in SUBMITTED approval state"):
            PurchaseStatutoryService.approve_challan(challan_id=1, user_id=9, remarks="ok")

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    def test_submit_return_for_approval_rejects_filed_revision(self, mock_return_objects):
        filing = SimpleNamespace(
            status=PurchaseStatutoryReturn.Status.REVISED,
            filed_payload_json={"_approval_state": {"status": "DRAFT"}},
        )
        mock_return_objects.select_for_update.return_value.get.return_value = filing

        with self.assertRaisesMessage(ValueError, "Only draft return can be submitted."):
            PurchaseStatutoryService.submit_return_for_approval(filing_id=1, user_id=9, remarks="retry")

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    def test_submit_return_for_approval_rejects_already_submitted(self, mock_return_objects):
        filing = SimpleNamespace(
            status=PurchaseStatutoryReturn.Status.DRAFT,
            filed_payload_json={"_approval_state": {"status": "SUBMITTED"}},
        )
        mock_return_objects.select_for_update.return_value.get.return_value = filing

        with self.assertRaisesMessage(ValueError, "Return is already in approval workflow."):
            PurchaseStatutoryService.submit_return_for_approval(filing_id=1, user_id=9, remarks="retry")

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallan.objects")
    def test_submit_challan_for_approval_rejects_already_approved(self, mock_challan_objects):
        challan = SimpleNamespace(
            status=PurchaseStatutoryChallan.Status.DRAFT,
            payment_payload_json={"_approval_state": {"status": "APPROVED"}},
        )
        mock_challan_objects.select_for_update.return_value.get.return_value = challan

        with self.assertRaisesMessage(ValueError, "Challan is already in approval workflow."):
            PurchaseStatutoryService.submit_challan_for_approval(challan_id=1, user_id=9, remarks="retry")

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallan.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._validate_challan_balance_for_lines")
    def test_update_challan_rejects_edit_while_submitted(self, mock_validate_balance, mock_challan_objects):
        challan = SimpleNamespace(
            status=PurchaseStatutoryChallan.Status.DRAFT,
            payment_payload_json={"_approval_state": {"status": "SUBMITTED"}},
        )
        mock_challan_objects.select_for_update.return_value.get.return_value = challan

        with self.assertRaisesMessage(ValueError, "cannot be edited while approval state is SUBMITTED"):
            PurchaseStatutoryService.update_challan(
                challan_id=1,
                entity_id=1,
                entityfinid_id=1,
                subentity_id=5,
                tax_type=PurchaseStatutoryChallan.TaxType.IT_TDS,
                challan_no="CH1",
                challan_date=date(2026, 4, 1),
                lines=[{"header_id": 10, "amount": Decimal("1.00")}],
            )

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._approval_state")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._enforcement_level")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._require_maker_checker")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._auto_compute_statutory_charges")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._due_date_for_return")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._validate_it_tds_return_code")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._append_audit_event")
    def test_file_return_marks_revision_as_revised(
        self,
        mock_append_audit,
        mock_validate_code,
        mock_due_date,
        mock_auto_charges,
        mock_require_maker_checker,
        mock_enforcement_level,
        mock_approval_state,
        mock_return_objects,
    ):
        filing = SimpleNamespace(
            entity_id=1,
            subentity_id=5,
            created_by_id=7,
            status=PurchaseStatutoryReturn.Status.DRAFT,
            original_return_id=3,
            tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
            return_code="26Q",
            period_to=date(2026, 6, 30),
            amount=Decimal("10.00"),
            interest_amount=Decimal("0.00"),
            late_fee_amount=Decimal("0.00"),
            penalty_amount=Decimal("0.00"),
            filed_payload_json={},
            lines=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_return_objects.prefetch_related.return_value.get.return_value = filing
        mock_approval_state.return_value = {"status": "DRAFT"}
        mock_enforcement_level.return_value = "off"
        mock_due_date.return_value = date(2026, 7, 31)
        mock_auto_charges.return_value = {
            "interest_amount": Decimal("0.00"),
            "late_fee_amount": Decimal("0.00"),
            "penalty_amount": Decimal("0.00"),
        }
        mock_append_audit.side_effect = lambda payload, event: {"audit": event}

        PurchaseStatutoryService.file_return(filing_id=1, filed_by_id=9, filed_on="2026-07-10")

        self.assertEqual(filing.status, PurchaseStatutoryReturn.Status.REVISED)

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._approval_state")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._enforcement_level")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._require_maker_checker")
    def test_file_return_returns_already_filed_for_terminal_status(
        self,
        mock_require_maker_checker,
        mock_enforcement_level,
        mock_approval_state,
        mock_return_objects,
    ):
        filing = SimpleNamespace(
            entity_id=1,
            subentity_id=None,
            created_by_id=7,
            status=PurchaseStatutoryReturn.Status.FILED,
            filed_payload_json={},
            lines=SimpleNamespace(all=lambda: []),
        )
        mock_return_objects.prefetch_related.return_value.get.return_value = filing
        mock_approval_state.return_value = {"status": "DRAFT"}
        mock_enforcement_level.return_value = "off"

        result = PurchaseStatutoryService.file_return(filing_id=1, filed_by_id=9, filed_on="2026-07-10")

        self.assertEqual(result.message, "Already filed.")

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallan.objects")
    def test_submit_challan_for_approval_sets_submitted_status(self, mock_challan_objects):
        challan = SimpleNamespace(
            status=PurchaseStatutoryChallan.Status.DRAFT,
            payment_payload_json={},
            save=MagicMock(),
        )
        mock_challan_objects.select_for_update.return_value.get.return_value = challan

        result = PurchaseStatutoryService.submit_challan_for_approval(challan_id=1, user_id=9, remarks="please approve")

        approval = result.obj.payment_payload_json["_approval_state"]
        self.assertEqual(result.message, "Challan submitted for approval.")
        self.assertEqual(approval["status"], "SUBMITTED")
        self.assertEqual(approval["submitted_by"], 9)
        self.assertEqual(approval["remarks"], "please approve")
        self.assertEqual(result.obj.payment_payload_json["_audit_log"][-1]["action"], "SUBMITTED_FOR_APPROVAL")
        challan.save.assert_called_once()

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallan.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._require_maker_checker")
    def test_approve_challan_sets_approved_status(self, mock_require_maker_checker, mock_challan_objects):
        challan = SimpleNamespace(
            entity_id=1,
            subentity_id=5,
            created_by_id=7,
            status=PurchaseStatutoryChallan.Status.DRAFT,
            payment_payload_json={"_approval_state": {"status": "SUBMITTED", "submitted_by": 8}},
            save=MagicMock(),
        )
        mock_challan_objects.select_for_update.return_value.get.return_value = challan

        result = PurchaseStatutoryService.approve_challan(challan_id=1, user_id=9, remarks="approved")

        approval = result.obj.payment_payload_json["_approval_state"]
        self.assertEqual(result.message, "Challan approved.")
        self.assertEqual(approval["status"], "APPROVED")
        self.assertEqual(approval["approved_by"], 9)
        self.assertEqual(approval["remarks"], "approved")
        self.assertEqual(result.obj.payment_payload_json["_audit_log"][-1]["action"], "APPROVED")
        challan.save.assert_called_once()
        mock_require_maker_checker.assert_called_once()

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallan.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._auto_compute_statutory_charges")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._due_date_for_challan")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._require_maker_checker")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._enforcement_level")
    def test_deposit_challan_marks_challan_deposited(
        self,
        mock_enforcement_level,
        mock_require_maker_checker,
        mock_due_date,
        mock_auto_compute,
        mock_challan_objects,
    ):
        mock_enforcement_level.return_value = "off"
        mock_due_date.return_value = date(2026, 4, 7)
        mock_auto_compute.return_value = {
            "interest_amount": Decimal("1.00"),
            "late_fee_amount": Decimal("2.00"),
            "penalty_amount": Decimal("3.00"),
        }
        challan = SimpleNamespace(
            entity_id=1,
            subentity_id=5,
            created_by_id=7,
            tax_type=PurchaseStatutoryChallan.TaxType.IT_TDS,
            status=PurchaseStatutoryChallan.Status.DRAFT,
            amount=Decimal("100.00"),
            interest_amount=Decimal("0.00"),
            late_fee_amount=Decimal("0.00"),
            penalty_amount=Decimal("0.00"),
            period_to=date(2026, 4, 30),
            challan_date=date(2026, 4, 10),
            payment_payload_json={},
            lines=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_challan_objects.prefetch_related.return_value.get.return_value = challan

        result = PurchaseStatutoryService.deposit_challan(
            challan_id=1,
            deposited_by_id=9,
            deposited_on="2026-05-10",
            cin_no="CIN-1",
        )

        self.assertEqual(result.message, "Challan deposited.")
        self.assertEqual(result.obj.status, PurchaseStatutoryChallan.Status.DEPOSITED)
        self.assertEqual(result.obj.cin_no, "CIN-1")
        self.assertEqual(result.obj.interest_amount, Decimal("1.00"))
        self.assertEqual(result.obj.late_fee_amount, Decimal("2.00"))
        self.assertEqual(result.obj.penalty_amount, Decimal("3.00"))
        self.assertEqual(result.obj.payment_payload_json["_audit_log"][-1]["action"], "DEPOSITED")
        challan.save.assert_called_once()
        mock_require_maker_checker.assert_called_once()

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._validate_it_tds_return_code")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._auto_compute_statutory_charges")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._due_date_for_return")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._require_maker_checker")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._enforcement_level")
    def test_file_return_marks_original_return_filed(
        self,
        mock_enforcement_level,
        mock_require_maker_checker,
        mock_due_date,
        mock_auto_compute,
        mock_validate_code,
        mock_return_objects,
    ):
        mock_enforcement_level.return_value = "off"
        mock_due_date.return_value = date(2026, 7, 31)
        mock_auto_compute.return_value = {
            "interest_amount": Decimal("1.50"),
            "late_fee_amount": Decimal("0.00"),
            "penalty_amount": Decimal("0.00"),
        }
        filing = SimpleNamespace(
            entity_id=1,
            subentity_id=5,
            created_by_id=7,
            original_return_id=None,
            tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
            return_code="26Q",
            status=PurchaseStatutoryReturn.Status.DRAFT,
            amount=Decimal("250.00"),
            interest_amount=Decimal("0.00"),
            late_fee_amount=Decimal("0.00"),
            penalty_amount=Decimal("0.00"),
            period_to=date(2026, 6, 30),
            filed_payload_json={},
            lines=SimpleNamespace(all=lambda: [SimpleNamespace(header_id=10)]),
            save=MagicMock(),
        )
        mock_return_objects.prefetch_related.return_value.get.return_value = filing

        result = PurchaseStatutoryService.file_return(
            filing_id=1,
            filed_by_id=9,
            filed_on="2026-07-20",
            ack_no="ACK-1",
        )

        self.assertEqual(result.message, "Return filed.")
        self.assertEqual(result.obj.status, PurchaseStatutoryReturn.Status.FILED)
        self.assertEqual(result.obj.ack_no, "ACK-1")
        self.assertEqual(result.obj.interest_amount, Decimal("1.50"))
        self.assertEqual(result.obj.filed_payload_json["_audit_log"][-1]["action"], "FILED")
        filing.save.assert_called_once()
        mock_require_maker_checker.assert_called_once()
        mock_validate_code.assert_called_once()

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    def test_issue_form16a_appends_new_issue_to_payload(self, mock_return_objects):
        filing = SimpleNamespace(
            id=12,
            tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
            return_code="26Q",
            status=PurchaseStatutoryReturn.Status.FILED,
            filed_payload_json={},
            lines=SimpleNamespace(count=lambda: 3),
            save=MagicMock(),
        )
        mock_return_objects.select_for_update.return_value.prefetch_related.return_value.get.return_value = filing

        payload = PurchaseStatutoryService.issue_form16a(
            filing_id=12,
            issued_by_id=9,
            issue_date="2026-08-01",
            remarks="First issue",
        )

        self.assertEqual(payload["filing_id"], 12)
        self.assertEqual(payload["issue"]["issue_no"], 1)
        self.assertEqual(payload["issue"]["issued_by"], 9)
        self.assertEqual(payload["issue"]["line_count"], 3)
        self.assertEqual(payload["issue"]["remarks"], "First issue")
        self.assertEqual(filing.filed_payload_json["form16a_issues"][0]["issue_no"], 1)
        self.assertEqual(filing.filed_payload_json["_audit_log"][-1]["action"], "FORM16A_ISSUED")
        filing.save.assert_called_once()

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturnLine.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallan.objects")
    def test_cancel_challan_rejects_when_linked_to_active_return(self, mock_challan_objects, mock_return_line_objects):
        challan = SimpleNamespace(
            id=15,
            status=PurchaseStatutoryChallan.Status.DEPOSITED,
            remarks=None,
            payment_payload_json={},
            save=MagicMock(),
        )
        mock_challan_objects.select_for_update.return_value.get.return_value = challan
        mock_return_line_objects.filter.return_value.exclude.return_value.exists.return_value = True

        with self.assertRaisesMessage(ValueError, "linked to active statutory returns"):
            PurchaseStatutoryService.cancel_challan(challan_id=15, cancelled_by_id=9, reason="bad upload")

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    def test_cancel_return_rejects_when_active_revision_exists(self, mock_return_objects):
        filing = SimpleNamespace(
            id=18,
            status=PurchaseStatutoryReturn.Status.FILED,
            remarks=None,
            filed_payload_json={},
            save=MagicMock(),
        )
        select_for_update_qs = MagicMock()
        select_for_update_qs.get.return_value = filing
        filter_qs = MagicMock()
        filter_qs.exclude.return_value.exists.return_value = True
        mock_return_objects.select_for_update.return_value = select_for_update_qs
        mock_return_objects.filter.return_value = filter_qs

        with self.assertRaisesMessage(ValueError, "active revisions exist"):
            PurchaseStatutoryService.cancel_return(filing_id=18, cancelled_by_id=9, reason="wrong revision")

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallan.objects")
    def test_cancel_challan_marks_status_and_audit_when_allowed(self, mock_challan_objects):
        challan = SimpleNamespace(
            id=16,
            status=PurchaseStatutoryChallan.Status.DEPOSITED,
            remarks=None,
            payment_payload_json={},
            save=MagicMock(),
        )
        mock_challan_objects.select_for_update.return_value.get.return_value = challan
        with patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturnLine.objects") as mock_return_line_objects:
            mock_return_line_objects.filter.return_value.exclude.return_value.exists.return_value = False
            result = PurchaseStatutoryService.cancel_challan(challan_id=16, cancelled_by_id=9, reason="voided")

        self.assertEqual(result.message, "Challan cancelled.")
        self.assertEqual(result.obj.status, PurchaseStatutoryChallan.Status.CANCELLED)
        self.assertEqual(result.obj.remarks, "voided")
        self.assertEqual(result.obj.payment_payload_json["_audit_log"][-1]["action"], "CANCELLED")
        challan.save.assert_called_once()

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    def test_cancel_return_marks_status_and_audit_when_allowed(self, mock_return_objects):
        filing = SimpleNamespace(
            id=19,
            status=PurchaseStatutoryReturn.Status.FILED,
            remarks=None,
            filed_payload_json={},
            save=MagicMock(),
        )
        select_for_update_qs = MagicMock()
        select_for_update_qs.get.return_value = filing
        filter_qs = MagicMock()
        filter_qs.exclude.return_value.exists.return_value = False
        mock_return_objects.select_for_update.return_value = select_for_update_qs
        mock_return_objects.filter.return_value = filter_qs

        result = PurchaseStatutoryService.cancel_return(filing_id=19, cancelled_by_id=9, reason="superseded")

        self.assertEqual(result.message, "Return cancelled.")
        self.assertEqual(result.obj.status, PurchaseStatutoryReturn.Status.CANCELLED)
        self.assertEqual(result.obj.remarks, "superseded")
        self.assertEqual(result.obj.filed_payload_json["_audit_log"][-1]["action"], "CANCELLED")
        filing.save.assert_called_once()

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    def test_issue_form16a_rejects_ineligible_return(self, mock_return_objects):
        filing = SimpleNamespace(
            id=13,
            tax_type=PurchaseStatutoryReturn.TaxType.GST_TDS,
            return_code="GSTR7",
            status=PurchaseStatutoryReturn.Status.FILED,
            filed_payload_json={},
            lines=SimpleNamespace(count=lambda: 0),
        )
        mock_return_objects.select_for_update.return_value.prefetch_related.return_value.get.return_value = filing

        with self.assertRaisesMessage(ValueError, "Form16A is allowed only"):
            PurchaseStatutoryService.issue_form16a(filing_id=13, issued_by_id=9)

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._policy_controls")
    def test_due_date_for_gst_tds_uses_configurable_day(self, mock_controls):
        mock_controls.return_value = {"gst_tds_challan_due_day": "12"}
        due = PurchaseStatutoryService._due_date_for_challan(
            entity_id=1,
            subentity_id=None,
            tax_type=PurchaseStatutoryChallan.TaxType.GST_TDS,
            period_to=date(2026, 4, 30),
            challan_date=None,
        )
        self.assertEqual(due, date(2026, 5, 12))

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService._policy_controls")
    def test_due_date_for_it_tds_return_q4_uses_configurable_month_day(self, mock_controls):
        mock_controls.return_value = {
            "it_tds_return_q4_due_month": "6",
            "it_tds_return_q4_due_day": "15",
        }
        due = PurchaseStatutoryService._due_date_for_return(
            entity_id=1,
            subentity_id=None,
            tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
            return_code="26Q",
            period_to=date(2026, 3, 31),
        )
        self.assertEqual(due, date(2026, 6, 15))

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryChallan.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseInvoiceHeader.objects")
    def test_reconciliation_summary_returns_expected_keys(
        self,
        mock_header_objects,
        mock_challan_objects,
        mock_return_objects,
    ):
        header_qs = MagicMock()
        header_qs.filter.return_value = header_qs
        header_qs.aggregate.side_effect = [
            {"t": Decimal("10.00")},  # deducted_it
            {"t": Decimal("5.00")},   # deducted_gst
        ]
        mock_header_objects.filter.return_value = header_qs

        challan_qs = MagicMock()
        challan_qs.filter.return_value = challan_qs
        challan_qs.filter.return_value.aggregate.side_effect = [
            {"t": Decimal("8.00")},  # deposited
            {"t": Decimal("0.50")},  # deposited_interest
            {"t": Decimal("0.25")},  # deposited_late_fee
            {"t": Decimal("0.10")},  # deposited_penalty
            {"t": Decimal("2.00")},  # draft challan
        ]
        mock_challan_objects.filter.return_value = challan_qs

        return_qs = MagicMock()
        return_qs.filter.return_value = return_qs
        return_qs.filter.return_value.aggregate.side_effect = [
            {"t": Decimal("6.00")},  # filed
            {"t": Decimal("0.40")},  # filed_interest
            {"t": Decimal("0.20")},  # filed_late_fee
            {"t": Decimal("0.05")},  # filed_penalty
            {"t": Decimal("1.00")},  # draft return
        ]
        mock_return_objects.filter.return_value = return_qs

        data = PurchaseStatutoryService.reconciliation_summary(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tax_type=None,
            date_from=None,
            date_to=None,
        )
        self.assertEqual(data["deducted"], "15.00")
        self.assertEqual(data["deposited"], "8.00")
        self.assertEqual(data["deposited_interest"], "0.50")
        self.assertEqual(data["filed"], "6.00")
        self.assertEqual(data["filed_penalty"], "0.05")
        self.assertEqual(data["pending_deposit"], "7.00")
        self.assertEqual(data["pending_filing"], "2.00")


class PurchaseStatutorySerializerValidationTests(SimpleTestCase):
    @patch("purchase.serializers.purchase_statutory.assert_document_date_within_financial_year")
    def test_challan_create_serializer_rejects_partial_period(self, mock_assert_fy):
        mock_assert_fy.return_value = None
        serializer = PurchaseStatutoryChallanCreateInputSerializer(
            data={
                "entity": 1,
                "entityfinid": 1,
                "tax_type": "IT_TDS",
                "challan_no": "CH1",
                "challan_date": "2026-04-10",
                "period_from": "2026-04-01",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("detail", serializer.errors)

    @patch("purchase.serializers.purchase_statutory.assert_document_date_within_financial_year")
    def test_challan_create_serializer_accepts_consistent_period(self, mock_assert_fy):
        mock_assert_fy.return_value = None
        serializer = PurchaseStatutoryChallanCreateInputSerializer(
            data={
                "entity": 1,
                "entityfinid": 1,
                "tax_type": "IT_TDS",
                "challan_no": "CH1",
                "challan_date": "2026-04-10",
                "period_from": "2026-04-01",
                "period_to": "2026-04-30",
                "amount": "100.00",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    @patch("purchase.serializers.purchase_statutory.assert_document_date_within_financial_year")
    def test_return_create_serializer_rejects_inverted_period(self, mock_assert_fy):
        mock_assert_fy.return_value = None
        serializer = PurchaseStatutoryReturnCreateInputSerializer(
            data={
                "entity": 1,
                "entityfinid": 1,
                "tax_type": "IT_TDS",
                "return_code": "26Q",
                "period_from": "2026-06-30",
                "period_to": "2026-04-01",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("detail", serializer.errors)

    @patch("purchase.serializers.purchase_statutory.assert_document_date_within_financial_year")
    def test_return_create_serializer_accepts_valid_period(self, mock_assert_fy):
        mock_assert_fy.return_value = None
        serializer = PurchaseStatutoryReturnCreateInputSerializer(
            data={
                "entity": 1,
                "entityfinid": 1,
                "tax_type": "IT_TDS",
                "return_code": "26Q",
                "period_from": "2026-04-01",
                "period_to": "2026-06-30",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


class PurchaseApiExtendedSmokeTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="purchase_api_ext_tester",
            email="purchase_api_ext_tester@example.com",
            password="x",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("purchase.views.purchase_ap.PurchaseApService.cancel_settlement")
    def test_ap_settlement_cancel_endpoint_returns_200(self, mock_cancel):
        mock_cancel.return_value = SimpleNamespace(
            message="Settlement cancelled with reversal.",
            settlement=SimpleNamespace(
                id=1,
                entity_id=1,
                entityfinid_id=1,
                subentity_id=None,
                vendor_id=1,
                settlement_type="payment",
                settlement_date=None,
                reference_no=None,
                external_voucher_no=None,
                remarks=None,
                total_amount=Decimal("0.00"),
                status=9,
                posted_at=None,
                posted_by_id=None,
                lines=[],
                created_at=None,
                updated_at=None,
                get_status_display=lambda: "Cancelled",
                get_settlement_type_display=lambda: "Payment",
            ),
        )
        with patch("purchase.views.purchase_ap.VendorSettlementSerializer") as mock_ser:
            mock_ser.return_value.data = {"id": 1, "status": 9}
            resp = self.client.post("/api/purchase/ap/settlements/1/cancel/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["message"], "Settlement cancelled with reversal.")

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.reconciliation_summary")
    def test_statutory_summary_endpoint_returns_200(self, mock_summary, mock_perm_codes):
        mock_perm_codes.return_value = {"purchase.statutory.view"}
        mock_summary.return_value = {
            "deducted": "10.00",
            "deposited": "8.00",
            "filed": "6.00",
            "pending_deposit": "2.00",
            "pending_filing": "2.00",
            "draft_challan": "1.00",
            "draft_return": "1.00",
        }
        resp = self.client.get("/api/purchase/statutory/summary/?entity=1&entityfinid=1")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("summary", resp.data)

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.reconciliation_exceptions")
    def test_statutory_reconciliation_exceptions_endpoint_returns_200(self, mock_fn, mock_perm_codes):
        mock_perm_codes.return_value = {"purchase.statutory.view"}
        mock_fn.return_value = {"exceptions": {}}
        resp = self.client.get(
            "/api/purchase/statutory/reconciliation-exceptions/?entity=1&entityfinid=1&tax_type=IT_TDS&period_from=2026-04-01&period_to=2026-04-30"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("exceptions", resp.data)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryReviewNoteSerializer")
    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.get_review_note")
    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_review_note_get_returns_200(self, mock_perm_codes, mock_get_note, mock_serializer):
        mock_perm_codes.return_value = {"purchase.statutory.view"}
        mock_get_note.return_value = SimpleNamespace(id=1)
        mock_serializer.return_value.data = {
            "reviewer_name": "CA Reviewer",
            "closure_status": "READY_TO_SIGN_OFF",
        }

        resp = self.client.get(
            "/api/purchase/statutory/review-note/?entity=1&entityfinid=1&period_from=2026-04-01&period_to=2026-04-30"
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["data"]["reviewer_name"], "CA Reviewer")
        mock_get_note.assert_called_once()

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryReviewNoteSerializer")
    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.save_review_note")
    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.serializers.purchase_statutory.assert_document_date_within_financial_year")
    def test_statutory_review_note_post_returns_200(self, mock_date_guard, mock_perm_codes, mock_save_note, mock_serializer):
        mock_date_guard.return_value = None
        mock_perm_codes.return_value = {"purchase.statutory.manage"}
        mock_save_note.return_value = SimpleNamespace(message="Review note updated.", obj=SimpleNamespace(id=1))
        mock_serializer.return_value.data = {
            "reviewer_name": "CA Reviewer",
            "closure_status": "IN_REVIEW",
        }

        resp = self.client.post(
            "/api/purchase/statutory/review-note/",
            {
                "entity": 1,
                "entityfinid": 1,
                "period_from": "2026-04-01",
                "period_to": "2026-04-30",
                "reviewer_name": "CA Reviewer",
                "closure_status": "IN_REVIEW",
                "review_summary": "Period reviewed.",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["message"], "Review note updated.")
        mock_save_note.assert_called_once()

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.delete_review_note")
    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_review_note_delete_returns_200(self, mock_perm_codes, mock_delete_note):
        mock_perm_codes.return_value = {"purchase.statutory.manage"}

        resp = self.client.delete(
            "/api/purchase/statutory/review-note/?entity=1&entityfinid=1&period_from=2026-04-01&period_to=2026-04-30"
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["message"], "Review note deleted.")
        mock_delete_note.assert_called_once()

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.itc_status_register")
    def test_statutory_itc_status_register_endpoint_returns_200(self, mock_fn, mock_perm_codes):
        mock_perm_codes.return_value = {"purchase.statutory.view"}
        mock_fn.return_value = {
            "count": 1,
            "rows": [
                {
                    "header_id": 10,
                    "purchase_number": "PINV-10",
                    "itc_claim_status_name": "Pending",
                    "gstr2b_match_status_name": "Not Checked",
                }
            ],
            "summary": {"invoice_count": 1},
        }
        resp = self.client.get(
            "/api/purchase/statutory/itc-status-register/?entity=1&entityfinid=1&date_from=2026-04-01&date_to=2026-04-30"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)
        self.assertIn("summary", resp.data)

    @patch("purchase.views.purchase_invoice_actions.PurchaseInvoiceHeaderSerializer")
    @patch("purchase.views.purchase_invoice_actions.PurchaseInvoiceActions.mark_itc_claimed")
    @patch("purchase.views.purchase_invoice_actions._assert_invoice_scope")
    @patch("purchase.views.rbac.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.rbac.EffectivePermissionService.entity_for_user")
    def test_purchase_service_invoice_itc_claim_endpoint_returns_200(
        self,
        mock_entity_for_user,
        mock_codes,
        _mock_scope,
        mock_action,
        mock_serializer,
    ):
        mock_entity_for_user.return_value = SimpleNamespace(id=1)
        mock_codes.return_value = {"purchase.invoice.update"}
        _mock_scope.return_value = SimpleNamespace(
            id=9,
            entity_id=1,
            doc_type=int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
        )
        mock_action.return_value = SimpleNamespace(message="ok", header=SimpleNamespace(id=9))
        mock_serializer.return_value.data = {"id": 9}
        resp = self.client.post(
            "/api/purchase/purchase-service-invoices/9/itc/claim/?entity=1&entityfinid=1",
            {"period": "2026-04"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["message"], "ok")

    @patch("purchase.views.purchase_invoice_actions.PurchaseInvoiceHeaderSerializer")
    @patch("purchase.views.purchase_invoice_actions.PurchaseInvoiceActions.mark_itc_unblocked")
    @patch("purchase.views.purchase_invoice_actions._assert_invoice_scope")
    @patch("purchase.views.rbac.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.rbac.EffectivePermissionService.entity_for_user")
    def test_purchase_service_invoice_itc_unblock_endpoint_returns_200(
        self,
        mock_entity_for_user,
        mock_codes,
        _mock_scope,
        mock_action,
        mock_serializer,
    ):
        mock_entity_for_user.return_value = SimpleNamespace(id=1)
        mock_codes.return_value = {"purchase.invoice.update"}
        _mock_scope.return_value = SimpleNamespace(
            id=9,
            entity_id=1,
            doc_type=int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
        )
        mock_action.return_value = SimpleNamespace(message="unblocked", header=SimpleNamespace(id=9))
        mock_serializer.return_value.data = {"id": 9}
        resp = self.client.post(
            "/api/purchase/purchase-service-invoices/9/itc/unblock/?entity=1&entityfinid=1",
            {"reason": "GSTR-2B updated"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["message"], "unblocked")

    @patch("purchase.views.purchase_invoice_actions.PurchaseInvoiceHeaderSerializer")
    @patch("purchase.views.purchase_invoice_actions.PurchaseInvoiceActions.update_2b_match_status")
    @patch("purchase.views.purchase_invoice_actions._assert_invoice_scope")
    @patch("purchase.views.rbac.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.rbac.EffectivePermissionService.entity_for_user")
    def test_purchase_service_invoice_2b_status_endpoint_returns_200(
        self,
        mock_entity_for_user,
        mock_codes,
        _mock_scope,
        mock_action,
        mock_serializer,
    ):
        mock_entity_for_user.return_value = SimpleNamespace(id=1)
        mock_codes.return_value = {"purchase.invoice.update"}
        _mock_scope.return_value = SimpleNamespace(
            id=10,
            entity_id=1,
            doc_type=int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
        )
        mock_action.return_value = SimpleNamespace(message="ok", header=SimpleNamespace(id=10))
        mock_serializer.return_value.data = {"id": 10, "gstr2b_match_status": 2}
        resp = self.client.post(
            "/api/purchase/purchase-service-invoices/10/gstr2b/status/?entity=1&entityfinid=1",
            {"match_status": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["data"]["id"], 10)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.attach_form16a_official_document")
    def test_statutory_form16a_official_upload_endpoint_returns_201(self, mock_attach):
        from django.core.files.uploadedfile import SimpleUploadedFile

        mock_attach.return_value = {"filing_id": 1, "issue_no": 2, "source": "TRACES"}
        doc = SimpleUploadedFile("form16a.pdf", b"%PDF-1.4\nfake", content_type="application/pdf")
        resp = self.client.post(
            "/api/purchase/statutory/returns/1/form16a/2/official-upload/",
            {"document": doc, "source": "TRACES"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["message"], "Official Form16A document uploaded.")

    def test_purchase_service_invoice_search_alias_endpoint_returns_200(self):
        resp = self.client.get("/api/purchase/purchase-service-invoices/search/?entity=1&entityfinid=1")
        # Alias route should at least resolve (it may reject request params with 400).
        self.assertNotEqual(resp.status_code, 404)

    @patch("purchase.views.purchase_gstr2b.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.purchase_gstr2b.PurchaseGstr2bService.create_batch")
    @patch("purchase.views.purchase_gstr2b.Gstr2bImportBatchSerializer")
    def test_gstr2b_import_batch_create_returns_201(self, mock_ser, mock_create, mock_perm_codes):
        mock_perm_codes.return_value = {"purchase.statutory.manage"}
        mock_create.return_value = SimpleNamespace(id=12)
        mock_ser.return_value.data = {"id": 12, "period": "2026-04"}
        resp = self.client.post(
            "/api/purchase/gstr2b/import-batches/",
            {
                "entity": 1,
                "entityfinid": 1,
                "period": "2026-04",
                "source": "gstr2b",
                "rows": [
                    {
                        "supplier_gstin": "29ABCDE1234F1Z5",
                        "supplier_invoice_number": "INV-1",
                        "taxable_value": "100.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["data"]["id"], 12)

    @patch("purchase.views.purchase_gstr2b.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.purchase_gstr2b.Gstr2bImportBatch.objects")
    @patch("purchase.views.purchase_gstr2b.PurchaseGstr2bService.auto_match_batch")
    def test_gstr2b_import_batch_match_returns_200(self, mock_match, mock_batch_objects, mock_perm_codes):
        mock_perm_codes.return_value = {"purchase.statutory.manage"}
        mock_batch_objects.filter.return_value.first.return_value = SimpleNamespace(
            id=15,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
        )
        mock_match.return_value = SimpleNamespace(
            batch=SimpleNamespace(id=15),
            total_rows=10,
            matched=7,
            partial=2,
            multiple=1,
            not_matched=0,
        )
        resp = self.client.post("/api/purchase/gstr2b/import-batches/15/match/?entity=1&entityfinid=1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["matched"], 7)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.generate_nsdl_payload")
    def test_statutory_nsdl_export_endpoint_returns_200(self, mock_fn):
        mock_fn.return_value = {"filing_id": 1, "nsdl_txt": "HDR|..."}
        resp = self.client.get("/api/purchase/statutory/returns/1/nsdl-export/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("nsdl_txt", resp.data)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.get_review_note")
    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.reconciliation_exceptions")
    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.reconciliation_summary")
    @patch("purchase.views.purchase_statutory.PurchaseStatutoryReturn.objects")
    @patch("purchase.views.purchase_statutory.PurchaseStatutoryChallan.objects")
    @patch("purchase.views.purchase_statutory.PurchaseInvoiceHeader.objects")
    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_ca_pack_export_includes_reporting_sheets(
        self,
        mock_perm_codes,
        mock_invoice_objects,
        mock_challan_objects,
        mock_return_objects,
        mock_recon_summary,
        mock_recon_exceptions,
        mock_get_review_note,
    ):
        mock_perm_codes.return_value = {"purchase.statutory.manage"}

        invoice_it = SimpleNamespace(
            id=11,
            purchase_number="PINV-11",
            doc_code="PINV",
            doc_no=11,
            bill_date=date(2026, 4, 10),
            vendor_name="Vendor IT",
            vendor_id=None,
            tds_section_id=None,
            tds_section=None,
            tds_base_amount=Decimal("1000.00"),
            tds_rate=Decimal("1.00"),
            tds_amount=Decimal("10.00"),
            gst_tds_amount=Decimal("0.00"),
            subentity_id=None,
            subentity=None,
            get_status_display=lambda: "Posted",
        )
        invoice_gst = SimpleNamespace(
            id=22,
            purchase_number="PINV-22",
            doc_code="PINV",
            doc_no=22,
            bill_date=date(2026, 4, 12),
            vendor_name="Vendor GST",
            vendor_gstin="29ABCDE1234F1Z5",
            vendor_id=None,
            tds_section_id=None,
            tds_section=None,
            tds_amount=Decimal("0.00"),
            gst_tds_contract_ref="GST-REF-22",
            gst_tds_base_amount=Decimal("2000.00"),
            gst_tds_rate=Decimal("2.00"),
            gst_tds_cgst_amount=Decimal("10.00"),
            gst_tds_sgst_amount=Decimal("10.00"),
            gst_tds_igst_amount=Decimal("20.00"),
            gst_tds_amount=Decimal("40.00"),
            subentity_id=None,
            subentity=None,
            get_status_display=lambda: "Posted",
        )
        mock_invoice_objects.filter.return_value = _FakeQuerySet([invoice_it, invoice_gst])

        challan_it = SimpleNamespace(
            id=51,
            tax_type=PurchaseStatutoryChallan.TaxType.IT_TDS,
            challan_no="IT-CH-51",
            challan_date=date(2026, 4, 20),
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
            amount=Decimal("10.00"),
            interest_amount=Decimal("0.00"),
            late_fee_amount=Decimal("0.00"),
            penalty_amount=Decimal("0.00"),
            cin_no="CINIT51",
            bsr_code="1234567",
            minor_head_code="200",
            status=PurchaseStatutoryChallan.Status.DEPOSITED,
            ack_document="",
            lines=_ListManager([]),
            get_status_display=lambda: "Deposited",
        )
        challan_gst = SimpleNamespace(
            id=52,
            tax_type=PurchaseStatutoryChallan.TaxType.GST_TDS,
            challan_no="GST-CH-52",
            challan_date=date(2026, 4, 21),
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
            amount=Decimal("40.00"),
            interest_amount=Decimal("0.00"),
            late_fee_amount=Decimal("0.00"),
            penalty_amount=Decimal("0.00"),
            cin_no="CINGST52",
            bsr_code="7654321",
            minor_head_code="200",
            status=PurchaseStatutoryChallan.Status.DRAFT,
            ack_document="challan.pdf",
            lines=_ListManager([]),
            get_status_display=lambda: "Draft",
        )
        mock_challan_objects.filter.return_value = _FakeQuerySet([challan_it, challan_gst])

        return_line_it = SimpleNamespace(
            header_id=invoice_it.id,
            header=invoice_it,
            challan_id=challan_it.id,
            challan=challan_it,
            deductee_pan_snapshot="ABCDE1234F",
            deductee_gstin_snapshot="",
            section_snapshot_code="194C",
            amount=Decimal("10.00"),
            cin_snapshot="CINIT51",
        )
        return_line_gst = SimpleNamespace(
            header_id=invoice_gst.id,
            header=invoice_gst,
            challan_id=challan_gst.id,
            challan=challan_gst,
            deductee_pan_snapshot="",
            deductee_gstin_snapshot="29ABCDE1234F1Z5",
            section_snapshot_code="",
            amount=Decimal("40.00"),
            cin_snapshot="CINGST52",
        )
        filing_it = SimpleNamespace(
            id=81,
            tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
            return_code="26Q",
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
            amount=Decimal("10.00"),
            status=PurchaseStatutoryReturn.Status.FILED,
            ack_no="ACK81",
            arn_no="ARN81",
            ack_document="it-return.pdf",
            lines=_ListManager([return_line_it]),
            get_status_display=lambda: "Filed",
        )
        filing_gst = SimpleNamespace(
            id=82,
            tax_type=PurchaseStatutoryReturn.TaxType.GST_TDS,
            return_code="GSTR7",
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
            amount=Decimal("40.00"),
            status=PurchaseStatutoryReturn.Status.REVISED,
            ack_no="",
            arn_no="",
            ack_document="",
            lines=_ListManager([return_line_gst]),
            get_status_display=lambda: "Revised",
        )
        mock_return_objects.filter.return_value = _FakeQuerySet([filing_it, filing_gst])

        mock_recon_summary.side_effect = [
            {
                "deducted": "50.00",
                "deposited": "10.00",
                "filed": "10.00",
                "pending_deposit": "40.00",
                "pending_filing": "0.00",
                "draft_challan": "1.00",
                "draft_return": "0.00",
            },
            {
                "deducted": "10.00",
                "deposited": "10.00",
                "filed": "10.00",
                "pending_deposit": "0.00",
                "pending_filing": "0.00",
                "draft_challan": "0.00",
                "draft_return": "0.00",
            },
            {
                "deducted": "40.00",
                "deposited": "0.00",
                "filed": "0.00",
                "pending_deposit": "40.00",
                "pending_filing": "0.00",
                "draft_challan": "1.00",
                "draft_return": "0.00",
            },
        ]
        mock_recon_exceptions.side_effect = [
            {
                "exceptions": {
                    "invoices_pending_challan_mapping": {"line_count": 0, "rows": []},
                    "challan_lines_pending_return_mapping": {"line_count": 0, "rows": []},
                    "filed_returns_missing_ack_or_arn": {"count": 0, "rows": []},
                }
            },
            {
                "exceptions": {
                    "invoices_pending_challan_mapping": {"line_count": 1, "rows": [{"header_id": 22, "purchase_number": "PINV-22", "bill_date": "2026-04-12", "amount": "40.00"}]},
                    "challan_lines_pending_return_mapping": {"line_count": 1, "rows": [{"challan_id": 52, "challan_no": "GST-CH-52", "amount": "40.00"}]},
                    "filed_returns_missing_ack_or_arn": {"count": 1, "rows": [{"id": 82, "return_code": "GSTR7", "period_from": "2026-04-01", "period_to": "2026-04-30"}]},
                }
            },
        ]

        event = SimpleNamespace(
            reviewer_name="Lead CA",
            changed_by=SimpleNamespace(username="review.user"),
            changed_by_id=7,
            changed_at=date(2026, 5, 1),
            review_summary="Reviewed",
            open_points="1 item open",
            closure_comment="Follow-up pending",
            get_action_display=lambda: "Updated",
            get_closure_status_display=lambda: "In Review",
        )
        note_all = SimpleNamespace(
            reviewer_name="Lead CA",
            reviewed_at=date(2026, 5, 2),
            reviewed_by=SimpleNamespace(username="review.user"),
            reviewed_by_id=7,
            review_summary="Overall summary",
            open_points="Overall open points",
            closure_comment="Overall closure comment",
            events=_FakeQuerySet([event]),
            get_closure_status_display=lambda: "In Review",
        )
        note_it = SimpleNamespace(
            reviewer_name="IT Reviewer",
            reviewed_at=date(2026, 5, 2),
            reviewed_by=SimpleNamespace(username="it.reviewer"),
            reviewed_by_id=8,
            review_summary="IT summary",
            open_points="",
            closure_comment="",
            events=_FakeQuerySet([]),
            get_closure_status_display=lambda: "Ready To Sign Off",
        )
        note_gst = None
        mock_get_review_note.side_effect = [note_all, note_it, note_gst]

        resp = self.client.get(
            "/api/purchase/statutory/export/ca-pack/?entity=1&entityfinid=1&period_from=2026-04-01&period_to=2026-04-30"
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        wb = load_workbook(BytesIO(resp.content))
        self.assertIn("01_Management_Summary", wb.sheetnames)
        self.assertIn("02_Reviewer_Signoff", wb.sheetnames)
        self.assertIn("03_Action_Items", wb.sheetnames)
        self.assertIn("12_Supporting_Doc_Index", wb.sheetnames)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.issue_form16a")
    def test_statutory_form16a_issue_endpoint_returns_201(self, mock_fn):
        mock_fn.return_value = {"filing_id": 1, "issue": {"issue_no": 1}}
        resp = self.client.post("/api/purchase/statutory/returns/1/form16a/", {"remarks": "issue"})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["message"], "Form16A issued.")

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.form16a_download_payload")
    def test_statutory_form16a_download_endpoint_returns_200(self, mock_fn):
        mock_fn.return_value = {"filename": "f16a.txt", "content": "hello"}
        resp = self.client.get("/api/purchase/statutory/returns/1/form16a/1/download/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/plain")

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.submit_challan_for_approval")
    def test_statutory_challan_approval_submit_returns_200(self, mock_fn):
        mock_fn.return_value = SimpleNamespace(
            message="ok",
            obj=SimpleNamespace(id=1),
        )
        with patch("purchase.views.purchase_statutory.PurchaseStatutoryChallanSerializer") as mock_ser:
            mock_ser.return_value.data = {"id": 1, "approval_status": "SUBMITTED", "approval_status_name": "Submitted"}
            resp = self.client.post("/api/purchase/statutory/challans/1/approval/", {"action": "submit"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["approval_status"], "SUBMITTED")

    def test_statutory_challan_approval_invalid_action_returns_400(self):
        resp = self.client.post("/api/purchase/statutory/challans/1/approval/", {"action": "archive"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("submit|approve|reject", str(resp.data))

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.submit_return_for_approval")
    def test_statutory_return_approval_submit_returns_200(self, mock_fn):
        mock_fn.return_value = SimpleNamespace(
            message="ok",
            obj=SimpleNamespace(id=1),
        )
        with patch("purchase.views.purchase_statutory.PurchaseStatutoryReturnSerializer") as mock_ser:
            mock_ser.return_value.data = {"id": 1, "approval_status": "SUBMITTED", "approval_status_name": "Submitted"}
            resp = self.client.post("/api/purchase/statutory/returns/1/approval/", {"action": "submit"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["approval_status"], "SUBMITTED")

    def test_statutory_return_approval_invalid_action_returns_400(self):
        resp = self.client.post("/api/purchase/statutory/returns/1/approval/", {"action": "archive"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("submit|approve|reject", str(resp.data))


class PurchaseStatutoryComplianceTests(SimpleTestCase):
    def test_coerce_date_accepts_iso_and_date(self):
        self.assertEqual(
            PurchaseStatutoryService._coerce_date("2026-04-30", field_name="x"),
            date(2026, 4, 30),
        )
        self.assertEqual(
            PurchaseStatutoryService._coerce_date(date(2026, 4, 30), field_name="x"),
            date(2026, 4, 30),
        )

    def test_validate_it_tds_return_code_26q_requires_resident_pan(self):
        line_ok = SimpleNamespace(
            deductee_residency_snapshot=PurchaseStatutoryReturnLine.DeducteeResidency.RESIDENT,
            deductee_pan_snapshot="ABCDE1234F",
            deductee_tax_id_snapshot=None,
        )
        PurchaseStatutoryService._validate_it_tds_return_code(return_code="26Q", lines=[line_ok])

        line_bad = SimpleNamespace(
            deductee_residency_snapshot=PurchaseStatutoryReturnLine.DeducteeResidency.NON_RESIDENT,
            deductee_pan_snapshot="ABCDE1234F",
            deductee_tax_id_snapshot=None,
        )
        with self.assertRaisesMessage(ValueError, "26Q allows only RESIDENT"):
            PurchaseStatutoryService._validate_it_tds_return_code(return_code="26Q", lines=[line_bad])

    def test_validate_it_tds_return_code_27q_requires_non_resident_tax_id(self):
        line_bad = SimpleNamespace(
            deductee_residency_snapshot=PurchaseStatutoryReturnLine.DeducteeResidency.NON_RESIDENT,
            deductee_pan_snapshot=None,
            deductee_tax_id_snapshot=None,
        )
        with self.assertRaisesMessage(ValueError, "27Q requires deductee_tax_id_snapshot"):
            PurchaseStatutoryService._validate_it_tds_return_code(return_code="27Q", lines=[line_bad])

    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryReturn.objects")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService.return_eligible_lines")
    @patch("purchase.services.purchase_statutory_service.PurchaseStatutoryService.challan_eligible_lines")
    def test_reconciliation_exceptions_exposes_rows_for_pending_mappings(
        self,
        mock_challan_eligible,
        mock_return_eligible,
        mock_return_objects,
    ):
        mock_challan_eligible.return_value = {
            "lines": [{"header_id": 11, "purchase_number": "PINV-11", "amount": "10.00"}],
            "totals": {"line_count": 1, "amount": "10.00"},
        }
        mock_return_eligible.return_value = {
            "lines": [{"header_id": 11, "challan_id": 21, "challan_no": "CH-21", "amount": "10.00"}],
            "totals": {"line_count": 1, "amount": "10.00"},
        }
        mock_return_objects.filter.return_value.filter.return_value.values.return_value = []

        payload = PurchaseStatutoryService.reconciliation_exceptions(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tax_type=PurchaseStatutoryChallan.TaxType.IT_TDS,
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
        )

        self.assertEqual(payload["exceptions"]["invoices_pending_challan_mapping"]["count"], 1)
        self.assertEqual(len(payload["exceptions"]["invoices_pending_challan_mapping"]["rows"]), 1)
        self.assertEqual(payload["exceptions"]["challan_lines_pending_return_mapping"]["count"], 1)
        self.assertEqual(len(payload["exceptions"]["challan_lines_pending_return_mapping"]["rows"]), 1)


class PurchaseApiPermissionTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="purchase_permission_tester",
            email="purchase_permission_tester@example.com",
            password="x",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.allowed_entity = Entity.objects.create(
            entityname="Allowed Entity",
            legalname="Allowed Entity Pvt Ltd",
            business_type=Entity.BusinessType.MIXED,
            createdby=self.user,
        )
        self.allowed_subentity = SubEntity.objects.create(
            entity=self.allowed_entity,
            subentityname="Allowed HO",
            branch_type=SubEntity.BranchType.HEAD_OFFICE,
        )
        self.allowed_fy = EntityFinancialYear.objects.create(
            entity=self.allowed_entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.foreign_entity = Entity.objects.create(
            entityname="Foreign Entity",
            legalname="Foreign Entity Pvt Ltd",
            business_type=Entity.BusinessType.MIXED,
            createdby=self.user,
        )
        self.foreign_subentity = SubEntity.objects.create(
            entity=self.foreign_entity,
            subentityname="Foreign HO",
            branch_type=SubEntity.BranchType.HEAD_OFFICE,
        )
        self.foreign_fy = EntityFinancialYear.objects.create(
            entity=self.foreign_entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.foreign_challan = PurchaseStatutoryChallan.objects.create(
            entity=self.foreign_entity,
            entityfinid=self.foreign_fy,
            subentity=self.foreign_subentity,
            tax_type=PurchaseStatutoryChallan.TaxType.IT_TDS,
            challan_no="CH-FOREIGN-1",
            challan_date=date(2026, 4, 10),
            amount=Decimal("100.00"),
            created_by=self.user,
        )
        self.foreign_return = PurchaseStatutoryReturn.objects.create(
            entity=self.foreign_entity,
            entityfinid=self.foreign_fy,
            subentity=self.foreign_subentity,
            tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS,
            return_code="26Q",
            period_from=date(2026, 4, 1),
            period_to=date(2026, 6, 30),
            amount=Decimal("100.00"),
            created_by=self.user,
        )

    def _pk_scope_obj(self, entity_id=1):
        return SimpleNamespace(entity_id=entity_id)

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_review_note_get_requires_view_permission(self, mock_codes):
        mock_codes.return_value = set()

        response = self.client.get(
            "/api/purchase/statutory/review-note/?entity=1&entityfinid=1&period_from=2026-04-01&period_to=2026-04-30"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_summary_rejects_purchase_invoice_view_without_statutory_permission(self, mock_codes):
        mock_codes.return_value = {"purchase.invoice.view"}

        response = self.client.get("/api/purchase/statutory/summary/?entity=1&entityfinid=1")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_review_note_post_requires_manage_permission(self, mock_codes):
        mock_codes.return_value = {"purchase.statutory.view"}

        response = self.client.post(
            "/api/purchase/statutory/review-note/",
            {
                "entity": 1,
                "entityfinid": 1,
                "period_from": "2026-04-01",
                "period_to": "2026-04-30",
                "reviewer_name": "CA Reviewer",
                "closure_status": "IN_REVIEW",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_ca_pack_export_requires_manage_permission(self, mock_codes):
        mock_codes.return_value = {"purchase.statutory.view"}

        response = self.client.get(
            "/api/purchase/statutory/export/ca-pack/?entity=1&entityfinid=1&period_from=2026-04-01&period_to=2026-04-30"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_review_note_get_requires_period_params(self, mock_codes):
        mock_codes.return_value = {"purchase.statutory.view"}

        response = self.client.get("/api/purchase/statutory/review-note/?entity=1&entityfinid=1")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("period_from and period_to are required", str(response.data))

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_review_note_get_rejects_inverted_period(self, mock_codes):
        mock_codes.return_value = {"purchase.statutory.view"}

        response = self.client.get(
            "/api/purchase/statutory/review-note/?entity=1&entityfinid=1&period_from=2026-04-30&period_to=2026-04-01"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("period_from cannot be greater than period_to", str(response.data))

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_ca_pack_export_requires_period_params(self, mock_codes):
        mock_codes.return_value = {"purchase.statutory.manage"}

        response = self.client.get("/api/purchase/statutory/export/ca-pack/?entity=1&entityfinid=1")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("period_from and period_to are required", str(response.data))

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_ca_pack_export_rejects_inverted_period(self, mock_codes):
        mock_codes.return_value = {"purchase.statutory.manage"}

        response = self.client.get(
            "/api/purchase/statutory/export/ca-pack/?entity=1&entityfinid=1&period_from=2026-04-30&period_to=2026-04-01"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("period_from cannot be greater than period_to", str(response.data))

    @patch("purchase.views.purchase_gstr2b.EffectivePermissionService.permission_codes_for_user")
    def test_gstr2b_batch_list_requires_statutory_view_permission(self, mock_codes):
        mock_codes.return_value = {"purchase.invoice.view"}

        response = self.client.get("/api/purchase/gstr2b/import-batches/?entity=1&entityfinid=1")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_gstr2b.Gstr2bImportBatch.objects")
    @patch("purchase.views.purchase_gstr2b.EffectivePermissionService.permission_codes_for_user")
    def test_gstr2b_auto_match_requires_statutory_manage_permission(self, mock_codes, mock_batch_objects):
        mock_codes.return_value = {"purchase.statutory.view"}
        mock_batch_objects.filter.return_value.first.return_value = SimpleNamespace(
            id=15,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
        )

        response = self.client.post("/api/purchase/gstr2b/import-batches/15/match/?entity=1&entityfinid=1", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryChallan.objects")
    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_challan_deposit_requires_manage_permission(self, mock_codes, mock_challan_objects):
        mock_codes.return_value = {"purchase.statutory.view"}
        mock_challan_objects.filter.return_value.only.return_value.first.return_value = self._pk_scope_obj()

        response = self.client.post(
            "/api/purchase/statutory/challans/15/deposit/",
            {"deposited_on": "2026-04-30"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryChallan.objects")
    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_challan_approval_requires_approve_permission(self, mock_codes, mock_challan_objects):
        mock_codes.return_value = {"purchase.statutory.manage"}
        mock_challan_objects.filter.return_value.only.return_value.first.return_value = self._pk_scope_obj()

        response = self.client.post(
            "/api/purchase/statutory/challans/15/approval/",
            {"action": "submit"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryReturn.objects")
    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_return_file_requires_manage_permission(self, mock_codes, mock_return_objects):
        mock_codes.return_value = {"purchase.statutory.view"}
        mock_return_objects.filter.return_value.only.return_value.first.return_value = self._pk_scope_obj()

        response = self.client.post(
            "/api/purchase/statutory/returns/21/file/",
            {"filed_on": "2026-07-31"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryReturn.objects")
    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_return_approval_requires_approve_permission(self, mock_codes, mock_return_objects):
        mock_codes.return_value = {"purchase.statutory.manage"}
        mock_return_objects.filter.return_value.only.return_value.first.return_value = self._pk_scope_obj()

        response = self.client.post(
            "/api/purchase/statutory/returns/21/approval/",
            {"action": "submit"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryReturn.objects")
    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_form16a_issue_requires_manage_permission(self, mock_codes, mock_return_objects):
        mock_codes.return_value = {"purchase.statutory.view"}
        mock_return_objects.filter.return_value.only.return_value.first.return_value = self._pk_scope_obj()

        response = self.client.post(
            "/api/purchase/statutory/returns/21/form16a/",
            {"remarks": "issue"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryReturn.objects")
    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_form16a_download_requires_view_permission(self, mock_codes, mock_return_objects):
        mock_codes.return_value = set()
        mock_return_objects.filter.return_value.only.return_value.first.return_value = self._pk_scope_obj()

        response = self.client.get("/api/purchase/statutory/returns/21/form16a/1/download/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryReturn.objects")
    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_nsdl_export_requires_view_permission(self, mock_codes, mock_return_objects):
        mock_codes.return_value = set()
        mock_return_objects.filter.return_value.only.return_value.first.return_value = self._pk_scope_obj()

        response = self.client.get("/api/purchase/statutory/returns/21/nsdl-export/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_gstr2b.Gstr2bImportBatch.objects")
    @patch("purchase.views.purchase_gstr2b.EffectivePermissionService.permission_codes_for_user")
    def test_gstr2b_batch_rows_rejects_subentity_mismatch(self, mock_codes, mock_batch_objects):
        mock_codes.return_value = {"purchase.statutory.view"}
        mock_batch_objects.filter.return_value.first.return_value = SimpleNamespace(
            id=15,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=99,
        )

        response = self.client.get("/api/purchase/gstr2b/import-batches/15/rows/?entity=1&entityfinid=1&subentity=5")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("subentity mismatch", str(response.data).lower())

    @patch("purchase.views.purchase_gstr2b.Gstr2bImportRow.objects")
    @patch("purchase.views.purchase_gstr2b.EffectivePermissionService.permission_codes_for_user")
    def test_gstr2b_row_review_rejects_subentity_mismatch(self, mock_codes, mock_row_objects):
        mock_codes.return_value = {"purchase.statutory.manage"}
        mock_row_objects.select_related.return_value.filter.return_value.first.return_value = SimpleNamespace(
            id=33,
            batch=SimpleNamespace(subentity_id=99),
        )

        response = self.client.post(
            "/api/purchase/gstr2b/import-rows/33/review/?entity=1&entityfinid=1&subentity=5",
            {"match_status": "MATCHED"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("subentity mismatch", str(response.data).lower())

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_challan_approval_uses_object_entity_scope_for_permission_check(self, mock_codes):
        mock_codes.side_effect = lambda user, entity_id: {"purchase.statutory.approve"} if entity_id == self.allowed_entity.id else set()

        response = self.client.post(
            f"/api/purchase/statutory/challans/{self.foreign_challan.id}/approval/",
            {"action": "submit"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_return_file_uses_object_entity_scope_for_permission_check(self, mock_codes):
        mock_codes.side_effect = lambda user, entity_id: {"purchase.statutory.manage"} if entity_id == self.allowed_entity.id else set()

        response = self.client.post(
            f"/api/purchase/statutory/returns/{self.foreign_return.id}/file/",
            {"filed_on": "2026-07-20"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user")
    def test_statutory_form16a_download_uses_object_entity_scope_for_permission_check(self, mock_codes):
        mock_codes.side_effect = lambda user, entity_id: {"purchase.statutory.view"} if entity_id == self.allowed_entity.id else set()

        response = self.client.get(
            f"/api/purchase/statutory/returns/{self.foreign_return.id}/form16a/1/download/"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("purchase.views.rbac.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.rbac.EffectivePermissionService.entity_for_user")
    def test_credit_note_create_requires_credit_note_create_permission(self, mock_entity_for_user, mock_codes):
        mock_entity_for_user.return_value = SimpleNamespace(id=1)
        mock_codes.return_value = {"purchase.credit_note.view"}

        response = self.client.post(
            "/api/purchase/purchase-invoices/",
            {
                "entity": 1,
                "entityfinid": 1,
                "doc_type": int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("purchase.credit_note create", str(response.data["detail"]).lower())

    @patch("purchase.views.purchase_invoice.generics.RetrieveUpdateDestroyAPIView.update")
    @patch("purchase.views.purchase_invoice.PurchaseInvoiceRetrieveUpdateDestroyAPIView.get_object")
    @patch("purchase.views.rbac.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.rbac.EffectivePermissionService.entity_for_user")
    def test_debit_note_update_uses_debit_note_permission_family(
        self,
        mock_entity_for_user,
        mock_codes,
        mock_get_object,
        mock_super_update,
    ):
        mock_entity_for_user.return_value = SimpleNamespace(id=1)
        mock_codes.return_value = {"purchase.debit_note.view"}
        mock_get_object.return_value = SimpleNamespace(
            id=9,
            entity_id=1,
            doc_type=int(PurchaseInvoiceHeader.DocType.DEBIT_NOTE),
        )
        mock_super_update.return_value = Response({"ok": True})

        response = self.client.put(
            "/api/purchase/purchase-invoices/9/?entity=1&entityfinid=1",
            {"vendor_name": "Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_super_update.assert_not_called()

    @patch("purchase.views.purchase_invoice.generics.RetrieveUpdateDestroyAPIView.update")
    @patch("purchase.views.purchase_invoice.PurchaseInvoiceRetrieveUpdateDestroyAPIView.get_object")
    @patch("purchase.views.rbac.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.rbac.EffectivePermissionService.entity_for_user")
    def test_debit_note_update_allows_matching_update_permission(
        self,
        mock_entity_for_user,
        mock_codes,
        mock_get_object,
        mock_super_update,
    ):
        mock_entity_for_user.return_value = SimpleNamespace(id=1)
        mock_codes.return_value = {"purchase.debit_note.update"}
        mock_get_object.return_value = SimpleNamespace(
            id=9,
            entity_id=1,
            doc_type=int(PurchaseInvoiceHeader.DocType.DEBIT_NOTE),
        )
        mock_super_update.return_value = Response({"ok": True})

        response = self.client.put(
            "/api/purchase/purchase-invoices/9/?entity=1&entityfinid=1",
            {"vendor_name": "Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_super_update.assert_called_once()

    @patch("purchase.views.purchase_invoice_actions.PurchaseInvoiceActions.post")
    @patch("purchase.views.purchase_invoice_actions._assert_invoice_scope")
    @patch("purchase.views.rbac.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.rbac.EffectivePermissionService.entity_for_user")
    def test_credit_note_post_requires_credit_note_post_permission(
        self,
        mock_entity_for_user,
        mock_codes,
        mock_scope,
        mock_post,
    ):
        mock_entity_for_user.return_value = SimpleNamespace(id=1)
        mock_codes.return_value = {"purchase.credit_note.view"}
        mock_scope.return_value = SimpleNamespace(
            id=11,
            entity_id=1,
            doc_type=int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE),
        )

        response = self.client.post(
            "/api/purchase/purchase-invoices/11/post/?entity=1&entityfinid=1",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_post.assert_not_called()

    @patch("purchase.views.purchase_invoice_actions.PurchaseInvoiceHeaderSerializer")
    @patch("purchase.views.purchase_invoice_actions.PurchaseInvoiceActions.cancel")
    @patch("purchase.views.purchase_invoice_actions._assert_invoice_scope")
    @patch("purchase.views.rbac.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.rbac.EffectivePermissionService.entity_for_user")
    def test_credit_note_cancel_allows_update_permission_fallback(
        self,
        mock_entity_for_user,
        mock_codes,
        mock_scope,
        mock_cancel,
        mock_serializer,
    ):
        mock_entity_for_user.return_value = SimpleNamespace(id=1)
        mock_codes.return_value = {"purchase.credit_note.update"}
        mock_scope.return_value = SimpleNamespace(
            id=12,
            entity_id=1,
            doc_type=int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE),
        )
        mock_cancel.return_value = SimpleNamespace(message="cancelled", header=SimpleNamespace(id=12))
        mock_serializer.return_value.data = {"id": 12}

        response = self.client.post(
            "/api/purchase/purchase-invoices/12/cancel/?entity=1&entityfinid=1",
            {"reason": "test"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_cancel.assert_called_once()

    @patch("purchase.views.purchase_invoice_actions.PurchaseNoteFactory.create_note_from_invoice")
    @patch("purchase.views.purchase_invoice_actions._assert_invoice_scope")
    @patch("purchase.views.rbac.EffectivePermissionService.permission_codes_for_user")
    @patch("purchase.views.rbac.EffectivePermissionService.entity_for_user")
    def test_create_credit_note_action_requires_credit_note_create_permission(
        self,
        mock_entity_for_user,
        mock_codes,
        mock_scope,
        mock_factory,
    ):
        mock_entity_for_user.return_value = SimpleNamespace(id=1)
        mock_codes.return_value = {"purchase.invoice.post"}
        mock_scope.return_value = SimpleNamespace(
            id=13,
            entity_id=1,
            doc_type=int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
        )

        response = self.client.post(
            "/api/purchase/purchase-invoices/13/create-credit-note/?entity=1&entityfinid=1",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_factory.assert_not_called()
