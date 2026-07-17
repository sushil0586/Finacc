from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from django.test import TestCase

from purchase.models.purchase_core import PurchaseInvoiceHeader, ItcClaimStatus, Status
from purchase.serializers.purchase_actions import ItcClaimSerializer, ItcReviewSerializer
from purchase.services.purchase_invoice_actions import PurchaseInvoiceActions


class _DummyHeader(SimpleNamespace):
    def save(self, update_fields=None):
        self._saved_fields = list(update_fields or [])


class PurchaseItcPolicyActionTests(TestCase):
    def test_itc_claim_serializer_rejects_invalid_month(self):
        ser = ItcClaimSerializer(data={"period": "2026-13"})
        self.assertFalse(ser.is_valid())
        self.assertIn("period", ser.errors)

    def test_itc_review_serializer_requires_claim_period_for_claimed_status(self):
        ser = ItcReviewSerializer(data={
            "target_status": int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED),
            "claim_period": "",
        })
        self.assertFalse(ser.is_valid())
        self.assertEqual(
            ser.errors["claim_period"][0],
            "Claim period is required when marking ITC as claimed.",
        )

    def test_itc_review_serializer_requires_reason_for_blocked_status(self):
        ser = ItcReviewSerializer(data={
            "target_status": int(PurchaseInvoiceHeader.ItcClaimStatus.BLOCKED),
            "block_reason": "   ",
        })
        self.assertFalse(ser.is_valid())
        self.assertEqual(
            ser.errors["block_reason"][0],
            "Reason is required when blocking or reversing ITC.",
        )

    def test_itc_review_serializer_rejects_invalid_claim_period_month(self):
        ser = ItcReviewSerializer(data={
            "target_status": int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED),
            "claim_period": "2026-13",
        })
        self.assertFalse(ser.is_valid())
        self.assertEqual(
            ser.errors["claim_period"][0],
            "claim_period month must be between 01 and 12",
        )

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
        _mock_log.assert_called_once()
        self.assertIn("not allowed for ITC claim by policy", _mock_log.call_args.kwargs["notes"])

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_itc_claim_hard_gate_allows_partial_when_policy_permits_it(self, mock_get, mock_get_policy, _mock_assert, _mock_log):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            is_itc_eligible=True,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.PARTIAL,
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

        result = PurchaseInvoiceActions.mark_itc_claimed(1, "2026-04")

        self.assertEqual(header.itc_claim_status, ItcClaimStatus.CLAIMED)
        self.assertEqual(header.itc_claim_period, "2026-04")
        self.assertEqual(result.message, "ITC marked as Claimed.")

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
    def test_itc_claim_rejects_ineligible_invoice(self, mock_get, mock_get_policy, _mock_assert, _mock_log):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            is_itc_eligible=False,
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

        with self.assertRaisesMessage(ValueError, "Cannot claim ITC: document is not ITC-eligible."):
            PurchaseInvoiceActions.mark_itc_claimed(1, "2026-04")

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

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_itc_claim_blocks_rcm_invoice_until_payment_tracking_exists(self, mock_get, mock_get_policy, _mock_assert, _mock_log):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            is_itc_eligible=True,
            is_reverse_charge=True,
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

        with self.assertRaisesMessage(ValueError, "RCM ITC should be claimed only after reverse-charge tax payment is tracked."):
            PurchaseInvoiceActions.mark_itc_claimed(1, "2026-04")

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_itc_claim_allows_rcm_invoice_once_posted_payment_exists(self, mock_get, mock_get_policy, _mock_assert, _mock_log):
        settlement_lines = MagicMock()
        settlement_lines.filter.return_value.exists.return_value = True
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            is_itc_eligible=True,
            is_reverse_charge=True,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED,
            itc_claim_status=ItcClaimStatus.PENDING,
            itc_claim_period=None,
            itc_claimed_at=None,
            ap_open_item=SimpleNamespace(settlement_lines=settlement_lines),
        )
        mock_get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(
            itc_claim_2b_gate="off",
            itc_claim_allowed_2b_statuses={"matched", "partial"},
            enforce_2b_before_itc_claim=False,
        )

        result = PurchaseInvoiceActions.mark_itc_claimed(1, "2026-04")

        self.assertEqual(header.itc_claim_status, ItcClaimStatus.CLAIMED)
        self.assertEqual(header.itc_claim_period, "2026-04")
        self.assertEqual(result.message, "ITC marked as Claimed.")
        self.assertIsNotNone(header.itc_claimed_at)
        self.assertIn("itc_claimed_at", header._saved_fields)
        _mock_log.assert_called_once_with(
            header=header,
            action_type="CLAIM",
            acted_by_id=None,
            from_status=int(ItcClaimStatus.PENDING),
            to_status=int(ItcClaimStatus.CLAIMED),
            period="2026-04",
            notes=None,
        )

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceService.rebuild_tax_summary")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_itc_reverse_marks_status_reason_and_rebuilds_summary(
        self,
        mock_get,
        _mock_assert,
        mock_log,
        mock_rebuild,
    ):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            is_itc_eligible=True,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED,
            itc_claim_status=ItcClaimStatus.CLAIMED,
            itc_claim_period="2026-04",
            itc_claimed_at="2026-04-20T10:00:00Z",
            itc_block_reason=None,
        )
        mock_get.return_value = header

        result = PurchaseInvoiceActions.mark_itc_reversed(
            1,
            "Annual reversal required after exempt turnover allocation.",
        )

        self.assertEqual(header.itc_claim_status, ItcClaimStatus.REVERSED)
        self.assertEqual(header.itc_block_reason, "Annual reversal required after exempt turnover allocation.")
        self.assertIn("itc_claim_status", header._saved_fields)
        self.assertIn("itc_block_reason", header._saved_fields)
        self.assertEqual(result.message, "ITC marked as Reversed.")
        mock_log.assert_called_once_with(
            header=header,
            action_type="REVERSE",
            acted_by_id=None,
            from_status=int(ItcClaimStatus.CLAIMED),
            to_status=int(ItcClaimStatus.REVERSED),
            reason="Annual reversal required after exempt turnover allocation.",
        )
        mock_rebuild.assert_called_once_with(header)

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_repeated_itc_claim_with_same_period_is_idempotent(self, mock_get, mock_get_policy, _mock_assert, mock_log):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            is_itc_eligible=True,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED,
            itc_claim_status=ItcClaimStatus.CLAIMED,
            itc_claim_period="2026-04",
            itc_claimed_at="2026-04-20T10:00:00Z",
        )
        mock_get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(
            itc_claim_2b_gate="off",
            itc_claim_allowed_2b_statuses={"matched", "partial"},
            enforce_2b_before_itc_claim=False,
        )

        result = PurchaseInvoiceActions.mark_itc_claimed(1, "2026-04")

        self.assertEqual(result.message, "Already claimed.")
        mock_log.assert_not_called()

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceService.rebuild_tax_summary")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_repeated_itc_block_with_same_reason_is_idempotent(self, mock_get, _mock_assert, mock_log, mock_rebuild):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            is_itc_eligible=False,
            itc_claim_status=ItcClaimStatus.BLOCKED,
            itc_block_reason="Blocked for review",
        )
        mock_get.return_value = header

        result = PurchaseInvoiceActions.mark_itc_blocked(1, "Blocked for review")

        self.assertEqual(result.message, "Already blocked.")
        mock_log.assert_not_called()
        mock_rebuild.assert_not_called()

    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._log_itc_action")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._assert_action_allowed_by_level")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoiceActions._get")
    def test_repeated_2b_status_update_to_same_value_is_idempotent(self, mock_get, _mock_assert, mock_log):
        header = _DummyHeader(
            id=1,
            entity_id=1,
            subentity_id=None,
            status=Status.CONFIRMED,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED,
        )
        mock_get.return_value = header

        result = PurchaseInvoiceActions.update_2b_match_status(
            1,
            int(PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED),
        )

        self.assertEqual(result.message, "GSTR-2B status unchanged.")
        mock_log.assert_not_called()
