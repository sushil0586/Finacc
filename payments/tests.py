from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from payments.models import PaymentVoucherHeader
from payments.serializers.payment_voucher import PaymentVoucherHeaderSerializer
from payments.services.payment_voucher_service import PaymentVoucherService
from payments.views.payment_exports import PaymentVoucherPDFAPIView
from payments.views.payment_voucher import (
    PaymentVoucherApprovalAPIView,
    PaymentVoucherListCreateAPIView,
)
from posting.adapters.payment_voucher import PaymentVoucherPostingAdapter
from withholding.models import WithholdingBaseRule


class FakeRelated(list):
    def all(self):
        return self


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
    databases = {"default"}
    @patch.object(PaymentVoucherService, "_fresh_allocation_rows", return_value=[])
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_post_voucher_calls_posting_adapter(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_post_adapter,
        _mock_fresh_allocs,
    ):
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
            settlement_effective_amount=Decimal("0.00"),
            created_by_id=5,
            ap_settlement_id=None,
            approved_at=None,
            approved_by_id=None,
            workflow_payload={},
            adjustments=SimpleNamespace(all=lambda: [], values=lambda *args, **kwargs: []),
            allocations=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: []),
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
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_unpost_voucher_cancels_ap_and_reverses_posting(self, mock_header_objects, mock_get_policy, mock_unpost_adapter, mock_cancel_settlement):
        header = SimpleNamespace(
            id=12,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.POSTED,
            ap_settlement_id=99,
            created_by_id=5,
            voucher_code="PPV-12",
            workflow_payload={},
            adjustments=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={"unpost_target_status": "confirmed"})

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

    @patch.object(PaymentVoucherService, "_fresh_allocation_rows", return_value=[SimpleNamespace(open_item_id=501, settled_amount=Decimal("120.00"))])
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_post_voucher_warn_mode_returns_warning_message(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_post_adapter,
        _mock_fresh_allocs,
    ):
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
            workflow_payload={},
            cash_paid_amount=Decimal("120.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("120.00"),
            adjustments=SimpleNamespace(all=lambda: [], values=lambda *args, **kwargs: []),
            allocations=SimpleNamespace(all=lambda: [row]),
            advance_adjustments=SimpleNamespace(all=lambda: []),
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

    @patch("payments.services.payment_voucher_service.VendorBillOpenItem.objects")
    @patch("payments.services.payment_voucher_service.PurchaseApService.list_open_advances")
    def test_validate_advance_adjustments_rejects_over_consumption(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            paid_to_id=99,
        )
        advance = SimpleNamespace(id=14, outstanding_amount=Decimal("50000.00"))
        open_item = SimpleNamespace(
            id=55,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            vendor_id=99,
        )
        mock_list_open_advances.return_value.filter.return_value.first.return_value = advance
        mock_open_item_objects.filter.return_value.first.return_value = open_item

        with self.assertRaisesMessage(ValueError, "exceeds available balance"):
            PaymentVoucherService._validate_advance_adjustments(
                voucher=voucher,
                allocations=[{"open_item": 55, "settled_amount": Decimal("60000.00")}],
                advance_adjustments=[{
                    "advance_balance_id": 14,
                    "open_item": 55,
                    "adjusted_amount": Decimal("50001.00"),
                }],
            )

    @patch.object(PaymentVoucherService, "_fresh_allocation_rows", return_value=[SimpleNamespace(open_item_id=55, settled_amount=Decimal("116000.00"))])
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_post_voucher_with_advance_adjustments_requires_ap_sync(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_post_adapter,
        _mock_fresh_allocs,
    ):
        advance_row = SimpleNamespace(
            advance_balance_id=14,
            allocation_id=None,
            open_item_id=55,
            adjusted_amount=Decimal("50000.00"),
        )
        alloc_row = SimpleNamespace(open_item_id=55, settled_amount=Decimal("116000.00"))
        header = SimpleNamespace(
            id=31,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.CONFIRMED,
            payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            voucher_date=None,
            voucher_code="PPV-31",
            reference_number=None,
            narration=None,
            cash_paid_amount=Decimal("66000.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("66000.00"),
            exchange_rate=Decimal("1.000000"),
            created_by_id=5,
            ap_settlement_id=None,
            approved_at=None,
            approved_by_id=None,
            workflow_payload={},
            adjustments=SimpleNamespace(all=lambda: [], values=lambda *args, **kwargs: []),
            allocations=SimpleNamespace(all=lambda: [alloc_row]),
            advance_adjustments=SimpleNamespace(all=lambda: [advance_row]),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_allocation_on_post": "hard",
            "sync_ap_settlement_on_post": "off",
            "allocation_amount_match_rule": "hard",
            "require_confirm_before_post": "on",
            "payment_maker_checker": "off",
            "over_settlement_rule": "block",
            "allocation_policy": "manual",
        })

        with patch.object(PaymentVoucherService, "_validate_advance_adjustments", return_value=None), \
             patch.object(PaymentVoucherService, "_validate_allocations", return_value=[]):
            with self.assertRaisesMessage(ValueError, "Advance adjustments require AP settlement sync to be enabled."):
                PaymentVoucherService.post_voucher.__wrapped__(voucher_id=31, posted_by_id=9)
        mock_post_adapter.assert_not_called()

    @patch.object(PaymentVoucherService, "_fresh_allocation_rows", return_value=[SimpleNamespace(open_item_id=55, settled_amount=Decimal("116000.00"))])
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("payments.services.payment_voucher_service.PurchaseApService.post_settlement")
    @patch("payments.services.payment_voucher_service.PurchaseApService.create_settlement")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_post_voucher_with_advance_adjustment_creates_cash_and_advance_settlements(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_create_settlement,
        mock_post_settlement,
        mock_post_adapter,
        _mock_fresh_allocs,
    ):
        advance_row = SimpleNamespace(
            advance_balance_id=14,
            allocation_id=None,
            open_item_id=55,
            adjusted_amount=Decimal("50000.00"),
            ap_settlement_id=None,
            remarks="adjust",
            save=MagicMock(),
        )
        alloc_row = SimpleNamespace(open_item_id=55, settled_amount=Decimal("116000.00"))
        header = SimpleNamespace(
            id=32,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.CONFIRMED,
            payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            voucher_date="2026-03-07",
            voucher_code="PPV-32",
            reference_number="UTR-1",
            narration="test",
            paid_to_id=99,
            cash_paid_amount=Decimal("66000.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("66000.00"),
            settlement_effective_amount_base_currency=Decimal("66000.00"),
            exchange_rate=Decimal("1.000000"),
            created_by_id=5,
            ap_settlement_id=None,
            approved_at=None,
            approved_by_id=None,
            workflow_payload={},
            adjustments=SimpleNamespace(all=lambda: [], values=lambda *args, **kwargs: []),
            allocations=SimpleNamespace(all=lambda: [alloc_row]),
            advance_adjustments=SimpleNamespace(all=lambda: [advance_row]),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_allocation_on_post": "hard",
            "sync_ap_settlement_on_post": "on",
            "allocation_amount_match_rule": "hard",
            "require_confirm_before_post": "on",
            "payment_maker_checker": "off",
            "over_settlement_rule": "block",
            "allocation_policy": "manual",
            "sync_advance_balance_on_post": "off",
        })
        mock_create_settlement.side_effect = [
            SimpleNamespace(settlement=SimpleNamespace(id=101)),
            SimpleNamespace(settlement=SimpleNamespace(id=102)),
        ]
        mock_post_settlement.side_effect = [
            SimpleNamespace(settlement=SimpleNamespace(id=201)),
            SimpleNamespace(settlement=SimpleNamespace(id=202)),
        ]

        with patch.object(PaymentVoucherService, "_validate_advance_adjustments", return_value=None), \
             patch.object(PaymentVoucherService, "_validate_allocations", return_value=[]):
            res = PaymentVoucherService.post_voucher.__wrapped__(voucher_id=32, posted_by_id=9)

        self.assertEqual(res.message, "Posted.")
        self.assertEqual(header.status, PaymentVoucherHeader.Status.POSTED)
        self.assertEqual(header.ap_settlement_id, 201)
        self.assertEqual(advance_row.ap_settlement_id, 202)
        cash_call = mock_create_settlement.call_args_list[0].kwargs
        adv_call = mock_create_settlement.call_args_list[1].kwargs
        self.assertEqual(cash_call["settlement_type"], "payment")
        self.assertEqual(cash_call["lines"][0]["amount"], Decimal("66000.00"))
        self.assertEqual(adv_call["settlement_type"], "advance_adjustment")
        self.assertEqual(adv_call["advance_balance_id"], 14)
        self.assertEqual(adv_call["lines"][0]["amount"], Decimal("50000.00"))
        mock_post_adapter.assert_called_once()

    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PurchaseApService.cancel_settlement")
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.unpost_payment_voucher")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_unpost_voucher_reopens_advance_adjustment_settlements(
        self,
        mock_header_objects,
        mock_unpost_adapter,
        mock_cancel_settlement,
        mock_get_policy,
    ):
        advance_balance = SimpleNamespace(is_open=True, adjusted_amount=Decimal("0.00"), outstanding_amount=Decimal("0.00"), save=MagicMock())
        advance_row = SimpleNamespace(ap_settlement_id=202, save=MagicMock())
        header = SimpleNamespace(
            id=41,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.POSTED,
            ap_settlement_id=201,
            created_by_id=5,
            voucher_code="PPV-41",
            workflow_payload={},
            adjustments=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: [advance_row]),
            vendor_advance_balance=advance_balance,
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={"unpost_target_status": "draft"})

        res = PaymentVoucherService.unpost_voucher.__wrapped__(voucher_id=41, unposted_by_id=9)

        self.assertEqual(res.message, "Unposted with reversal entry.")
        self.assertEqual(header.status, PaymentVoucherHeader.Status.DRAFT)
        self.assertIsNone(header.ap_settlement_id)
        self.assertIsNone(advance_row.ap_settlement_id)
        self.assertEqual(mock_cancel_settlement.call_count, 2)
        advance_balance.save.assert_called_once()
        mock_unpost_adapter.assert_called_once()


class PaymentVoucherAdvanceEdgeCaseTests(SimpleTestCase):
    @patch("payments.services.payment_voucher_service.VendorBillOpenItem.objects")
    @patch("payments.services.payment_voucher_service.PurchaseApService.list_open_advances")
    def test_partial_advance_consumption_with_remaining_balance(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, paid_to_id=99)
        advance = SimpleNamespace(id=14, outstanding_amount=Decimal("50000.00"))
        open_item = SimpleNamespace(id=55, entity_id=1, entityfinid_id=1, subentity_id=None, vendor_id=99)
        mock_list_open_advances.return_value.filter.return_value.first.return_value = advance
        mock_open_item_objects.filter.return_value.first.return_value = open_item

        PaymentVoucherService._validate_advance_adjustments(
            voucher=voucher,
            allocations=[{"open_item": 55, "settled_amount": Decimal("60000.00")}],
            advance_adjustments=[{"advance_balance_id": 14, "open_item": 55, "adjusted_amount": Decimal("36000.00")}],
        )

    @patch("payments.services.payment_voucher_service.VendorBillOpenItem.objects")
    @patch("payments.services.payment_voucher_service.PurchaseApService.list_open_advances")
    def test_multiple_advances_against_one_bill(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, paid_to_id=99)
        advances = {
            14: SimpleNamespace(id=14, outstanding_amount=Decimal("30000.00")),
            15: SimpleNamespace(id=15, outstanding_amount=Decimal("20000.00")),
        }
        open_item = SimpleNamespace(id=55, entity_id=1, entityfinid_id=1, subentity_id=None, vendor_id=99)
        mock_list_open_advances.return_value.filter.side_effect = lambda id: SimpleNamespace(first=lambda: advances[id])
        mock_open_item_objects.filter.return_value.first.return_value = open_item

        PaymentVoucherService._validate_advance_adjustments(
            voucher=voucher,
            allocations=[{"open_item": 55, "settled_amount": Decimal("116000.00")}],
            advance_adjustments=[
                {"advance_balance_id": 14, "open_item": 55, "adjusted_amount": Decimal("30000.00")},
                {"advance_balance_id": 15, "open_item": 55, "adjusted_amount": Decimal("20000.00")},
            ],
        )

    @patch("payments.services.payment_voucher_service.VendorBillOpenItem.objects")
    @patch("payments.services.payment_voucher_service.PurchaseApService.list_open_advances")
    def test_one_advance_across_multiple_bills(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, paid_to_id=99)
        advance = SimpleNamespace(id=14, outstanding_amount=Decimal("50000.00"))
        items = {
            55: SimpleNamespace(id=55, entity_id=1, entityfinid_id=1, subentity_id=None, vendor_id=99),
            56: SimpleNamespace(id=56, entity_id=1, entityfinid_id=1, subentity_id=None, vendor_id=99),
        }
        mock_list_open_advances.return_value.filter.return_value.first.return_value = advance
        mock_open_item_objects.filter.side_effect = lambda pk: SimpleNamespace(first=lambda: items[pk])

        PaymentVoucherService._validate_advance_adjustments(
            voucher=voucher,
            allocations=[
                {"open_item": 55, "settled_amount": Decimal("30000.00")},
                {"open_item": 56, "settled_amount": Decimal("30000.00")},
            ],
            advance_adjustments=[
                {"advance_balance_id": 14, "open_item": 55, "adjusted_amount": Decimal("20000.00")},
                {"advance_balance_id": 14, "open_item": 56, "adjusted_amount": Decimal("15000.00")},
            ],
        )

    @patch("payments.services.payment_voucher_service.VendorBillOpenItem.objects")
    @patch("payments.services.payment_voucher_service.PurchaseApService.list_open_advances")
    def test_vendor_mismatch_on_advance(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, paid_to_id=99)
        advance = SimpleNamespace(id=14, outstanding_amount=Decimal("50000.00"))
        open_item = SimpleNamespace(id=55, entity_id=1, entityfinid_id=1, subentity_id=None, vendor_id=77)
        mock_list_open_advances.return_value.filter.return_value.first.return_value = advance
        mock_open_item_objects.filter.return_value.first.return_value = open_item

        with self.assertRaisesMessage(ValueError, "vendor mismatch with paid_to"):
            PaymentVoucherService._validate_advance_adjustments(
                voucher=voucher,
                allocations=[{"open_item": 55, "settled_amount": Decimal("60000.00")}],
                advance_adjustments=[{"advance_balance_id": 14, "open_item": 55, "adjusted_amount": Decimal("10000.00")}],
            )

    @patch("payments.services.payment_voucher_service.VendorBillOpenItem.objects")
    @patch("payments.services.payment_voucher_service.PurchaseApService.list_open_advances")
    def test_entity_entityfinid_mismatch_on_advance(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, paid_to_id=99)
        advance = SimpleNamespace(id=14, outstanding_amount=Decimal("50000.00"))
        open_item = SimpleNamespace(id=55, entity_id=2, entityfinid_id=1, subentity_id=None, vendor_id=99)
        mock_list_open_advances.return_value.filter.return_value.first.return_value = advance
        mock_open_item_objects.filter.return_value.first.return_value = open_item

        with self.assertRaisesMessage(ValueError, "open_item scope mismatch"):
            PaymentVoucherService._validate_advance_adjustments(
                voucher=voucher,
                allocations=[{"open_item": 55, "settled_amount": Decimal("60000.00")}],
                advance_adjustments=[{"advance_balance_id": 14, "open_item": 55, "adjusted_amount": Decimal("10000.00")}],
            )

    def test_allocation_mismatch_with_cash_and_advance_combined(self):
        with self.assertRaisesMessage(ValueError, "does not match settlement effective amount"):
            PaymentVoucherService._validate_allocation_effective_match(
                effective_amount=Decimal("116000.00"),
                allocation_total=Decimal("100000.00"),
                level="hard",
            )

    @patch("payments.services.payment_voucher_service.PaymentVoucherService.confirm_voucher")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_maker_checker_confirm_before_post_flow_requires_confirm(self, mock_header_objects, mock_get_policy, mock_confirm):
        header = SimpleNamespace(
            id=51,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.DRAFT,
            payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            workflow_payload={"_approval_state": {"status": "APPROVED"}},
            adjustments=SimpleNamespace(values=lambda *args, **kwargs: []),
            advance_adjustments=SimpleNamespace(all=lambda: []),
            allocations=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_confirm_before_post": "on",
            "payment_maker_checker": "hard",
        })

        with self.assertRaisesMessage(ValueError, "Only CONFIRMED vouchers can be posted."):
            PaymentVoucherService.post_voucher.__wrapped__(voucher_id=51, posted_by_id=9)
        mock_confirm.assert_not_called()

    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_maker_checker_confirm_before_post_flow_requires_approved_status(self, mock_header_objects, mock_get_policy, mock_post_adapter):
        header = SimpleNamespace(
            id=52,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.CONFIRMED,
            payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            workflow_payload={"_approval_state": {"status": "SUBMITTED"}},
            cash_paid_amount=Decimal("0.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("0.00"),
            exchange_rate=Decimal("1.000000"),
            created_by_id=5,
            ap_settlement_id=None,
            approved_at=None,
            approved_by_id=None,
            adjustments=SimpleNamespace(all=lambda: [], values=lambda *args, **kwargs: []),
            allocations=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_confirm_before_post": "on",
            "payment_maker_checker": "hard",
            "require_allocation_on_post": "off",
            "sync_ap_settlement_on_post": "off",
        })

        with self.assertRaisesMessage(ValueError, "Voucher must be approved before posting by policy."):
            PaymentVoucherService.post_voucher.__wrapped__(voucher_id=52, posted_by_id=9)
        mock_post_adapter.assert_not_called()

    @patch("payments.services.payment_voucher_service.PaymentVoucherService._validate_advance_adjustments")
    @patch("payments.services.payment_voucher_service.PaymentVoucherService._validate_allocations")
    @patch("payments.services.payment_voucher_service.PaymentVoucherService._validate_adjustment_allocation_links")
    @patch("payments.services.payment_voucher_service.PaymentVoucherAdjustment.objects.create")
    @patch("payments.services.payment_voucher_service.PaymentVoucherAdvanceAdjustment.objects.create")
    @patch("payments.services.payment_voucher_service.PaymentVoucherAllocation.objects.create")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects.create")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherService._account_ledger_id")
    def test_draft_create_with_advance_adjustments(
        self,
        mock_account_ledger_id,
        mock_get_policy,
        mock_header_create,
        mock_alloc_create,
        mock_adv_create,
        mock_adj_create,
        mock_validate_adj_links,
        mock_validate_allocations,
        mock_validate_adv,
    ):
        mock_account_ledger_id.return_value = None
        header = MagicMock()
        header.id = 61
        header.entity_id = 1
        header.entityfinid_id = 1
        header.subentity_id = None
        header.refresh_from_db = MagicMock()
        mock_header_create.return_value = header
        mock_get_policy.return_value = SimpleNamespace(default_action="draft", controls={
            "require_reference_number": "off",
            "allocation_policy": "manual",
            "allocation_amount_match_rule": "hard",
            "over_settlement_rule": "block",
        })
        mock_validate_allocations.return_value = []

        PaymentVoucherService.create_voucher.__wrapped__({
            "entity": SimpleNamespace(id=1),
            "entityfinid": SimpleNamespace(id=1),
            "subentity": None,
            "paid_to": SimpleNamespace(id=99),
            "cash_paid_amount": Decimal("66000.00"),
            "payment_type": PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            "doc_code": "PPV",
            "allocations": [{"open_item": 55, "settled_amount": Decimal("116000.00")}],
            "advance_adjustments": [{"advance_balance_id": 14, "open_item": 55, "adjusted_amount": Decimal("50000.00"), "remarks": "adjust"}],
            "adjustments": [],
        })
        mock_alloc_create.assert_called_once()
        mock_adv_create.assert_called_once()
        self.assertEqual(mock_adv_create.call_args.kwargs["advance_balance_id"], 14)
        self.assertEqual(mock_adv_create.call_args.kwargs["open_item_id"], 55)

    @patch("payments.services.payment_voucher_service.PaymentVoucherService._validate_advance_adjustments")
    @patch("payments.services.payment_voucher_service.PaymentVoucherService._validate_adjustment_allocation_links")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    def test_draft_update_with_advance_adjustments(self, mock_get_policy, mock_validate_adj_links, mock_validate_adv):
        adv_row = MagicMock()
        adv_row.id = 71
        alloc_row = SimpleNamespace(open_item_id=55, settled_amount=Decimal("116000.00"))
        instance = SimpleNamespace(
            id=70,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.DRAFT,
            workflow_payload={},
            cash_paid_amount=Decimal("66000.00"),
            exchange_rate=Decimal("1.000000"),
            advance_adjustments=SimpleNamespace(all=lambda: [adv_row]),
            allocations=SimpleNamespace(all=lambda: [alloc_row]),
            adjustments=SimpleNamespace(all=lambda: [], values=lambda *args, **kwargs: []),
            save=MagicMock(),
        )
        mock_get_policy.return_value = SimpleNamespace(controls={
            "allow_edit_after_submit": "on",
            "over_settlement_rule": "block",
            "allocation_amount_match_rule": "hard",
        })

        PaymentVoucherService.update_voucher.__wrapped__(instance, {
            "advance_adjustments": [{
                "id": 71,
                "advance_balance_id": 14,
                "open_item": 55,
                "adjusted_amount": Decimal("40000.00"),
                "remarks": "updated",
            }]
        })

        self.assertEqual(adv_row.advance_balance_id, 14)
        self.assertEqual(adv_row.open_item_id, 55)
        self.assertEqual(adv_row.adjusted_amount, Decimal("40000.00"))
        adv_row.save.assert_called_once()


class PaymentVoucherSerializerContractTests(SimpleTestCase):
    def test_detail_serializer_exposes_navigation_and_advance_totals(self):
        allocation_row = SimpleNamespace(
            id=1,
            open_item=SimpleNamespace(pk=55, id=55, purchase_number="PI-PINV-1010", supplier_invoice_number="VEN-1"),
            settled_amount=Decimal("116000.00"),
            is_full_settlement=True,
            is_advance_adjustment=False,
        )
        advance_adj = SimpleNamespace(
            id=1,
            advance_balance_id=14,
            advance_balance=SimpleNamespace(
                id=14,
                outstanding_amount=Decimal("0.00"),
                payment_voucher=SimpleNamespace(
                    id=81,
                    voucher_code="PPV-ADV-1004",
                    doc_code="PPV",
                    voucher_date="2026-03-06",
                    payment_type="ADVANCE",
                ),
                reference_no="PPV-ADV-1004",
            ),
            allocation=None,
            open_item_id=55,
            open_item=SimpleNamespace(pk=55, id=55, purchase_number="PI-PINV-1010"),
            adjusted_amount=Decimal("50000.00"),
            remarks="adjust",
        )
        instance = SimpleNamespace(
            id=6,
            entity=SimpleNamespace(pk=32),
            entityfinid=SimpleNamespace(pk=32),
            subentity=None,
            entity_id=32,
            entityfinid_id=32,
            subentity_id=None,
            voucher_date="2026-03-07",
            doc_code="PPV",
            doc_no=11,
            voucher_code="PPV-PPV-2026-00011",
            currency_code="INR",
            base_currency_code="INR",
            exchange_rate=Decimal("1.000000"),
            payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            supply_type=PaymentVoucherHeader.SupplyType.SERVICES,
            paid_from_id=157,
            paid_from=SimpleNamespace(pk=157, accountname="Bank"),
            paid_to_id=171,
            paid_to=SimpleNamespace(pk=171, accountname="RRR"),
            payment_mode=SimpleNamespace(pk=1, paymentmode="NEFT"),
            cash_paid_amount=Decimal("66000.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("66000.00"),
            settlement_effective_amount_base_currency=Decimal("66000.00"),
            reference_number="UTR-1003",
            narration="test",
            instrument_date=None,
            place_of_supply_state=None,
            vendor_gstin=None,
            advance_taxable_value=Decimal("0.00"),
            advance_cgst=Decimal("0.00"),
            advance_sgst=Decimal("0.00"),
            advance_igst=Decimal("0.00"),
            advance_cess=Decimal("0.00"),
            status=PaymentVoucherHeader.Status.CONFIRMED,
            approved_by=None,
            approved_at=None,
            workflow_payload={"_approval_state": {"status": "APPROVED"}},
            is_cancelled=False,
            cancelled_at=None,
            cancelled_by=None,
            cancel_reason=None,
            created_by=SimpleNamespace(pk=1),
            ap_settlement_id=None,
            ap_settlement=None,
            vendor_advance_balance=None,
            allocations=FakeRelated([allocation_row]),
            advance_adjustments=FakeRelated([advance_adj]),
            adjustments=FakeRelated([]),
            created_at=None,
            updated_at=None,
            get_status_display=lambda: "Confirmed",
            get_payment_type_display=lambda: "Against Bill",
            get_supply_type_display=lambda: "Services",
        )

        with patch("payments.serializers.payment_voucher.PaymentVoucherNavService.get_prev_next_for_instance", return_value={"previous": {"id": 5}, "next": {"id": 7}}), \
             patch("payments.serializers.payment_voucher.PaymentVoucherNavService.get_number_navigation", return_value={"enabled": True, "current_number": 11}):
            data = PaymentVoucherHeaderSerializer(instance).data

        self.assertEqual(str(data["advance_consumed_amount"]), "50000.00")
        self.assertEqual(str(data["total_settlement_support_amount"]), "116000.00")
        self.assertEqual(str(data["allocated_amount"]), "116000.00")
        self.assertEqual(str(data["settlement_balance_amount"]), "0.00")
        self.assertEqual(data["navigation"]["previous"]["id"], 5)
        self.assertEqual(data["number_navigation"]["current_number"], 11)
        self.assertEqual(data["advance_adjustments"][0]["advance_balance_id"], 14)


class PaymentVoucherPDFEndpointTests(SimpleTestCase):
    def test_pdf_endpoint_returns_pdf_blob(self):
        factory = APIRequestFactory()
        request = factory.get("/api/payments/payment-vouchers/6/pdf/?entity=32&entityfinid=32")
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))

        voucher = SimpleNamespace(
            id=6,
            voucher_code="PPV-PPV-2026-00011",
            doc_code="PPV",
            doc_no=11,
            voucher_date="2026-03-07",
            get_status_display=lambda: "Confirmed",
            get_payment_type_display=lambda: "Against Bill",
            get_supply_type_display=lambda: "Services",
            paid_from=SimpleNamespace(accountname="Bank"),
            paid_to=SimpleNamespace(accountname="RRR"),
            payment_mode=SimpleNamespace(paymentmode="NEFT"),
            reference_number="UTR-1",
            cash_paid_amount=Decimal("10000.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("10000.00"),
            adjustments=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: []),
            allocations=SimpleNamespace(all=lambda: []),
        )

        qs = MagicMock()
        qs.filter.return_value = qs
        qs.select_related.return_value = qs
        qs.prefetch_related.return_value = qs
        qs.get.return_value = voucher

        with patch("payments.views.payment_exports.PaymentVoucherHeader.objects", qs):
            response = PaymentVoucherPDFAPIView.as_view()(request, pk=6)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")


class PaymentVoucherViewValidationTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=7)

    def _request(self, path: str, data=None):
        request = self.factory.post(path, data or {}, format="json") if data is not None else self.factory.get(path)
        force_authenticate(request, user=self.user)
        return request

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    def test_list_view_reports_missing_scope_as_field_errors(self, mocked_error_log):
        request = self._request("/api/payments/payment-vouchers/")

        response = PaymentVoucherListCreateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["entity"]), "This query param is required.")
        self.assertEqual(str(response.data["entityfinid"]), "This query param is required.")
        mocked_error_log.assert_called_once()

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch("payments.views.payment_voucher.PaymentVoucherHeader.objects")
    def test_approval_view_reports_invalid_action_on_action_field(self, mocked_header_objects, mocked_error_log):
        mocked_header_objects.only.return_value.get.return_value = SimpleNamespace(id=9, entity_id=1)
        request = self._request(
            "/api/payments/payment-vouchers/9/approval/",
            {"action": "ship"},
        )

        response = PaymentVoucherApprovalAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["action"]), "Use submit, approve, or reject.")
        mocked_error_log.assert_called_once()


class PaymentVoucherCashGuardTests(SimpleTestCase):
    def test_against_bill_allows_zero_cash_with_advance(self):
        PaymentVoucherService._validate_cash_paid_input(
            payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            cash_paid_amount=Decimal("0.00"),
            advance_adjustments=[{"adjusted_amount": Decimal("100.00")}],
        )

    def test_against_bill_rejects_zero_cash_without_advance(self):
        with self.assertRaisesMessage(ValueError, "unless advance adjustments are provided"):
            PaymentVoucherService._validate_cash_paid_input(
                payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
                cash_paid_amount=Decimal("0.00"),
                advance_adjustments=[],
                has_allocations=True,
            )

    def test_advance_rejects_zero_cash(self):
        with self.assertRaisesMessage(ValueError, "must be > 0 for ADVANCE/ON_ACCOUNT"):
            PaymentVoucherService._validate_cash_paid_input(
                payment_type=PaymentVoucherHeader.PaymentType.ADVANCE,
                cash_paid_amount=Decimal("0.00"),
                advance_adjustments=[{"adjusted_amount": Decimal("500.00")}],
            )


class PaymentRuntimeWithholdingTests(SimpleTestCase):
    @patch("payments.services.payment_voucher_service.WithholdingSection.objects.filter")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_ledger_id")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_account_id")
    @patch("payments.services.payment_voucher_service.compute_withholding_preview")
    def test_runtime_withholding_adds_auto_tds_adjustment(self, mock_preview, mock_get_account_id, mock_get_ledger_id, mock_filter):
        mock_filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            id=5,
            base_rule=WithholdingBaseRule.PAYMENT_VALUE,
        )
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001
        mock_preview.return_value = SimpleNamespace(rate=Decimal("1.0000"), amount=Decimal("10.00"), reason="auto", reason_code="OK")

        adjustments, payload = PaymentVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            paid_to_id=55,
            voucher_date=None,
            cash_paid_amount=Decimal("100.00"),
            allocations=[{"open_item": 1, "settled_amount": Decimal("100.00")}],
            adjustments=[],
            workflow_payload={"withholding": {"enabled": True, "section_id": 5, "mode": "AUTO", "allow_static_fallback": True}},
        )

        self.assertEqual(len(adjustments), 1)
        self.assertEqual(adjustments[0]["adj_type"], "TDS")
        self.assertEqual(adjustments[0]["settlement_effect"], "PLUS")
        self.assertEqual(adjustments[0]["amount"], Decimal("10.00"))
        self.assertEqual(adjustments[0]["remarks"], PaymentVoucherService.AUTO_WITHHOLDING_TDS_REMARK)
        self.assertIn("withholding_runtime_result", payload)

    def test_runtime_withholding_disabled_removes_auto_row(self):
        adjustments, payload = PaymentVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            paid_to_id=55,
            voucher_date=None,
            cash_paid_amount=Decimal("100.00"),
            allocations=[],
            adjustments=[
                {"adj_type": "TDS", "amount": Decimal("5.00"), "remarks": PaymentVoucherService.AUTO_WITHHOLDING_TDS_REMARK},
                {"adj_type": "BANK_CHARGES", "amount": Decimal("2.00"), "remarks": "manual"},
            ],
            workflow_payload={"withholding": {"enabled": False}},
        )

        self.assertEqual(len(adjustments), 1)
        self.assertEqual(adjustments[0]["adj_type"], "BANK_CHARGES")
        self.assertEqual(payload.get("withholding_runtime_result", {}).get("reason_code"), "DISABLED")

    @patch("payments.services.payment_voucher_service.WithholdingSection.objects.filter")
    def test_runtime_withholding_rejects_invoice_based_section_even_in_manual_mode(self, mock_filter):
        mock_filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            id=10,
            base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
        )

        adjustments, payload = PaymentVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            paid_to_id=55,
            voucher_date=None,
            cash_paid_amount=Decimal("100.00"),
            allocations=[],
            adjustments=[],
            workflow_payload={
                "withholding": {
                    "enabled": True,
                    "section_id": 10,
                    "mode": "MANUAL",
                    "manual_rate": Decimal("1.00"),
                }
            },
        )

        self.assertEqual(adjustments, [])
        self.assertEqual(payload.get("withholding_runtime_result", {}).get("reason_code"), "INVALID_BASE_RULE")

    @patch("payments.services.payment_voucher_service.PaymentVoucherService._resolve_entity_runtime_tds_mapping")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_ledger_id")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_account_id")
    def test_static_fallback_used_when_entity_map_missing(
        self,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_resolve_entity,
    ):
        mock_resolve_entity.return_value = (None, None)
        mock_get_account_id.return_value = 7001
        mock_get_ledger_id.return_value = 3001
        section = SimpleNamespace(id=10)
        account_id, ledger_id, source = PaymentVoucherService._resolve_runtime_tds_target_accounts(
            entity_id=1,
            subentity_id=None,
            section=section,
        )
        self.assertEqual(account_id, 7001)
        self.assertEqual(ledger_id, 3001)
        self.assertEqual(source, "STATIC_FALLBACK")

    @patch("payments.services.payment_voucher_service.PaymentVoucherService._resolve_entity_runtime_tds_mapping")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_ledger_id")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_account_id")
    def test_entity_mapping_overrides_section_and_static(
        self,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_resolve_entity,
    ):
        mock_resolve_entity.return_value = (888, 444)
        section = SimpleNamespace(id=10)
        account_id, ledger_id, source = PaymentVoucherService._resolve_runtime_tds_target_accounts(
            entity_id=1,
            subentity_id=17,
            section=section,
        )
        self.assertEqual(account_id, 888)
        self.assertEqual(ledger_id, 444)
        self.assertEqual(source, "ENTITY_MAP")
        mock_get_account_id.assert_not_called()
        mock_get_ledger_id.assert_not_called()

    @patch("payments.services.payment_voucher_service.WithholdingSection.objects.filter")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_ledger_id")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_account_id")
    @patch("payments.services.payment_voucher_service.compute_withholding_preview")
    @patch("payments.services.payment_voucher_service.PaymentVoucherService._resolve_entity_runtime_tds_mapping")
    def test_runtime_withholding_blocks_when_only_static_fallback_available(
        self,
        mock_resolve_entity,
        mock_preview,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_filter,
    ):
        mock_filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            id=10,
            base_rule=WithholdingBaseRule.PAYMENT_VALUE,
        )
        mock_resolve_entity.return_value = (None, None)
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001
        mock_preview.return_value = SimpleNamespace(
            section=SimpleNamespace(id=10),
            rate=Decimal("1.0000"),
            amount=Decimal("10.00"),
            reason="auto",
            reason_code="OK",
        )
        with self.assertRaisesMessage(ValueError, "Runtime TDS mapping missing for selected section"):
            PaymentVoucherService._apply_runtime_withholding_to_adjustments(
                entity_id=1,
                entityfinid_id=1,
                subentity_id=17,
                paid_to_id=55,
                voucher_date=None,
                cash_paid_amount=Decimal("100.00"),
                allocations=[{"open_item": 1, "settled_amount": Decimal("100.00")}],
                adjustments=[],
                workflow_payload={"withholding": {"enabled": True, "section_id": 10, "mode": "AUTO"}},
            )

    @patch("payments.services.payment_voucher_service.WithholdingSection.objects.filter")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_ledger_id")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_account_id")
    @patch("payments.services.payment_voucher_service.compute_withholding_preview")
    @patch("payments.services.payment_voucher_service.PaymentVoucherService._resolve_entity_runtime_tds_mapping")
    def test_runtime_withholding_allows_static_fallback_when_explicitly_enabled(
        self,
        mock_resolve_entity,
        mock_preview,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_filter,
    ):
        mock_filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            id=10,
            base_rule=WithholdingBaseRule.PAYMENT_VALUE,
        )
        mock_resolve_entity.return_value = (None, None)
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001
        mock_preview.return_value = SimpleNamespace(
            section=SimpleNamespace(id=10),
            rate=Decimal("1.0000"),
            amount=Decimal("10.00"),
            reason="auto",
            reason_code="OK",
        )
        adjustments, _ = PaymentVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=17,
            paid_to_id=55,
            voucher_date=None,
            cash_paid_amount=Decimal("100.00"),
            allocations=[{"open_item": 1, "settled_amount": Decimal("100.00")}],
            adjustments=[],
            workflow_payload={
                "withholding": {
                    "enabled": True,
                    "section_id": 10,
                    "mode": "AUTO",
                    "allow_static_fallback": True,
                }
            },
        )
        self.assertEqual(len(adjustments), 1)
