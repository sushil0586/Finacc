from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from purchase.models.purchase_core import PurchaseInvoiceHeader, ItcClaimStatus, Status
from purchase.serializers.purchase_actions import ItcClaimSerializer
from purchase.services.purchase_invoice_actions import PurchaseInvoiceActions


class _DummyHeader(SimpleNamespace):
    def save(self, update_fields=None):
        self._saved_fields = list(update_fields or [])


class PurchaseItcPolicyActionTests(TestCase):
    def test_itc_claim_serializer_rejects_invalid_month(self):
        ser = ItcClaimSerializer(data={"period": "2026-13"})
        self.assertFalse(ser.is_valid())
        self.assertIn("period", ser.errors)

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_itc_claim_hard_gate_blocks_non_allowed_2b_status(self, mock_get, mock_get_policy, _mock_assert, _mock_log):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            is_itc_eligible=True,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_CHECKED,
            itc_claim_status=ItcClaimStatus.PENDING,
            itc_claim_period=None,
            itc_claimed_at=None,
        )
        mock_get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(
            itc_claim_2b_gate="hard",
            itc_claim_allowed_2b_statuses={"matched", "partial"},
            enforce_2b_before_itc_claim=False,
        )

        with self.assertRaises(ValueError):
            PurchaseInvoiceActions.mark_itc_claimed(1, "2026-04")

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_itc_claim_warn_gate_allows_with_warning_message(self, mock_get, mock_get_policy, _mock_assert, _mock_log):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            is_itc_eligible=True,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_CHECKED,
            itc_claim_status=ItcClaimStatus.PENDING,
            itc_claim_period=None,
            itc_claimed_at=None,
        )
        mock_get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(
            itc_claim_2b_gate="warn",
            itc_claim_allowed_2b_statuses={"matched"},
            enforce_2b_before_itc_claim=False,
        )

        result = PurchaseInvoiceActions.mark_itc_claimed(1, "2026-04")

        self.assertEqual(header.itc_claim_status, ItcClaimStatus.CLAIMED)
        self.assertEqual(header.itc_claim_period, "2026-04")
        self.assertIn("with warning", result.message.lower())

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_itc_claim_legacy_enforce_2b_boolean_blocks_when_gate_missing(self, mock_get, mock_get_policy, _mock_assert, _mock_log):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            is_itc_eligible=True,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_CHECKED,
            itc_claim_status=ItcClaimStatus.PENDING,
            itc_claim_period=None,
            itc_claimed_at=None,
        )
        mock_get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(
            enforce_2b_before_itc_claim=True,
            itc_claim_allowed_2b_statuses={"matched", "partial"},
        )

        with self.assertRaises(ValueError):
            PurchaseInvoiceActions.mark_itc_claimed(1, "2026-04")

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_update_2b_status_rejects_invalid_value(self, mock_get, _mock_assert, _mock_log):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_CHECKED,
        )
        mock_get.return_value = header

        with self.assertRaises(ValueError):
            PurchaseInvoiceActions.update_2b_match_status(1, 999)

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_itc_claim_rejects_future_period(self, mock_get, mock_get_policy, _mock_assert, _mock_log):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            is_itc_eligible=True,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED,
            itc_claim_status=ItcClaimStatus.PENDING,
            itc_claim_period=None,
            itc_claimed_at=None,
        )
        mock_get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(
            itc_claim_2b_gate="off",
            itc_claim_allowed_2b_statuses={"matched", "partial"},
            enforce_2b_before_itc_claim=False,
        )

        with self.assertRaises(ValueError):
            PurchaseInvoiceActions.mark_itc_claimed(1, "2999-12")
