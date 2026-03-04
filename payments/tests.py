from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from payments.models import PaymentVoucherHeader
from payments.services.payment_voucher_service import PaymentVoucherService
from posting.adapters.payment_voucher import PaymentVoucherPostingAdapter


class PaymentPostingAdapterTests(SimpleTestCase):
    def _header(self):
        return SimpleNamespace(
            id=1,
            voucher_code="PPV-1",
            cash_paid_amount=Decimal("100.00"),
            paid_from_id=10,
            paid_to_id=20,
        )

    def test_build_journal_lines_with_adjustments(self):
        header = self._header()
        adjustments = [
            SimpleNamespace(id=1, amount=Decimal("10.00"), ledger_account_id=101, settlement_effect="PLUS", adj_type="TDS"),
            SimpleNamespace(id=2, amount=Decimal("5.00"), ledger_account_id=102, settlement_effect="MINUS", adj_type="BANK_CHARGES"),
        ]
        jl = PaymentVoucherPostingAdapter._build_journal_lines(header=header, adjustments=adjustments, reverse=False)

        # Vendor settlement = 100 + 10 - 5 = 105
        self.assertEqual(jl[0].account_id, 20)
        self.assertTrue(jl[0].drcr)
        self.assertEqual(jl[0].amount, Decimal("105.00"))

        # Cash credit
        self.assertEqual(jl[1].account_id, 10)
        self.assertFalse(jl[1].drcr)
        self.assertEqual(jl[1].amount, Decimal("100.00"))

        # PLUS => CR ledger
        self.assertEqual(jl[2].account_id, 101)
        self.assertFalse(jl[2].drcr)
        self.assertEqual(jl[2].amount, Decimal("10.00"))

        # MINUS => DR ledger
        self.assertEqual(jl[3].account_id, 102)
        self.assertTrue(jl[3].drcr)
        self.assertEqual(jl[3].amount, Decimal("5.00"))


class PaymentVoucherServiceTests(SimpleTestCase):
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_post_voucher_calls_posting_adapter(self, mock_header_objects, mock_get_policy, mock_post_adapter):
        header = SimpleNamespace(
            id=11,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.CONFIRMED,
            payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            voucher_date=None,
            voucher_code="PPV-11",
            reference_number=None,
            narration=None,
            cash_paid_amount=Decimal("0.00"),
            total_adjustment_amount=Decimal("0.00"),
            created_by_id=5,
            ap_settlement_id=None,
            approved_at=None,
            approved_by_id=None,
            adjustments=SimpleNamespace(all=lambda: []),
            allocations=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )

        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header

        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_allocation_on_post": "off",
            "sync_ap_settlement_on_post": "off",
        })

        res = PaymentVoucherService.post_voucher.__wrapped__(voucher_id=11, posted_by_id=9)
        self.assertEqual(res.message, "Posted.")
        self.assertEqual(header.status, PaymentVoucherHeader.Status.POSTED)
        mock_post_adapter.assert_called_once()

    @patch("payments.services.payment_voucher_service.PurchaseApService.cancel_settlement")
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.unpost_payment_voucher")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_unpost_voucher_cancels_ap_and_reverses_posting(self, mock_header_objects, mock_unpost_adapter, mock_cancel_settlement):
        header = SimpleNamespace(
            id=12,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.POSTED,
            ap_settlement_id=99,
            created_by_id=5,
            voucher_code="PPV-12",
            adjustments=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header

        res = PaymentVoucherService.unpost_voucher.__wrapped__(voucher_id=12, unposted_by_id=9)
        self.assertEqual(res.message, "Unposted with reversal entry.")
        self.assertEqual(header.status, PaymentVoucherHeader.Status.CONFIRMED)
        self.assertIsNone(header.ap_settlement_id)
        mock_cancel_settlement.assert_called_once_with(settlement_id=99, cancelled_by_id=9)
        mock_unpost_adapter.assert_called_once()

    @patch("payments.services.payment_voucher_service.PaymentVoucherAllocation.objects")
    def test_validate_adjustment_allocation_links_rejects_foreign_allocation(self, mock_alloc_objects):
        mock_alloc_objects.filter.return_value.exists.return_value = False
        with self.assertRaisesMessage(ValueError, "allocation must belong to this payment voucher"):
            PaymentVoucherService._validate_adjustment_allocation_links(
                voucher_id=1,
                adjustments=[{"allocation": 99, "amount": Decimal("10.00")}],
            )

    def test_validate_allocation_effective_match_hard_raises(self):
        with self.assertRaisesMessage(ValueError, "does not match settlement effective amount"):
            PaymentVoucherService._validate_allocation_effective_match(
                effective_amount=Decimal("100.00"),
                allocation_total=Decimal("90.00"),
                level="hard",
            )

    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_post_voucher_warn_mode_returns_warning_message(self, mock_header_objects, mock_get_policy, mock_post_adapter):
        row = SimpleNamespace(open_item_id=501, settled_amount=Decimal("120.00"))
        header = SimpleNamespace(
            id=21,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.CONFIRMED,
            payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            voucher_date=None,
            voucher_code="PPV-21",
            reference_number=None,
            narration=None,
            created_by_id=5,
            ap_settlement_id=None,
            approved_at=None,
            approved_by_id=None,
            cash_paid_amount=Decimal("120.00"),
            total_adjustment_amount=Decimal("0.00"),
            adjustments=SimpleNamespace(all=lambda: []),
            allocations=SimpleNamespace(all=lambda: [row]),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_allocation_on_post": "hard",
            "sync_ap_settlement_on_post": "off",
            "over_settlement_rule": "warn",
            "allocation_amount_match_rule": "warn",
        })
        with patch.object(PaymentVoucherService, "_validate_allocations", return_value=["over settlement"]) as mock_val:
            res = PaymentVoucherService.post_voucher.__wrapped__(voucher_id=21, posted_by_id=9)
        self.assertIn("Posted with warnings", res.message)
        mock_val.assert_called_once()
        mock_post_adapter.assert_called_once()
