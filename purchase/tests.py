from decimal import Decimal
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase, APIClient

from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.serializers.purchase_invoice import PurchaseInvoiceHeaderSerializer
from purchase.services.purchase_invoice_service import PurchaseInvoiceService
from purchase.services.purchase_statutory_service import PurchaseStatutoryService
from posting.adapters.purchase_invoice import (
    PurchaseInvoicePostingAdapter,
    PurchaseInvoicePostingConfig,
)
from posting.common.static_accounts import StaticAccountCodes
from withholding.services import WithholdingResult
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


class PurchaseStatutoryServiceTests(SimpleTestCase):
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


class PurchaseApiExtendedSmokeTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="purchase_api_ext_tester", password="x")
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

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.reconciliation_summary")
    def test_statutory_summary_endpoint_returns_200(self, mock_summary):
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

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.reconciliation_exceptions")
    def test_statutory_reconciliation_exceptions_endpoint_returns_200(self, mock_fn):
        mock_fn.return_value = {"exceptions": {}}
        resp = self.client.get(
            "/api/purchase/statutory/reconciliation-exceptions/?entity=1&entityfinid=1&tax_type=IT_TDS&period_from=2026-04-01&period_to=2026-04-30"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("exceptions", resp.data)

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.generate_nsdl_payload")
    def test_statutory_nsdl_export_endpoint_returns_200(self, mock_fn):
        mock_fn.return_value = {"filing_id": 1, "nsdl_txt": "HDR|..."}
        resp = self.client.get("/api/purchase/statutory/returns/1/nsdl-export/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("nsdl_txt", resp.data)

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
