from decimal import Decimal
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase, APIClient

from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.serializers.purchase_invoice import PurchaseInvoiceHeaderSerializer
from purchase.services.purchase_invoice_service import PurchaseInvoiceService
from posting.adapters.purchase_invoice import (
    PurchaseInvoicePostingAdapter,
    PurchaseInvoicePostingConfig,
)
from posting.common.static_accounts import StaticAccountCodes
from withholding.services import WithholdingResult


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

    def test_manual_mode_requires_section(self):
        header = self._make_header(withholding_enabled=True, tds_is_manual=True, tds_section_id=None)

        with self.assertRaisesMessage(ValueError, "TDS section is required when withholding_enabled is true."):
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


class PurchaseApiSmokeTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="purchase_api_tester", password="x")
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

    def test_charge_type_detail_missing_id_returns_404(self):
        resp = self.client.get("/api/purchase/charge-types/999999/")
        self.assertEqual(resp.status_code, 404)


class _ListManager:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


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
