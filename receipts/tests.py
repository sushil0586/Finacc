from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from receipts.models import ReceiptVoucherHeader
from receipts.serializers.receipt_voucher import ReceiptVoucherHeaderSerializer
from receipts.services.receipt_voucher_service import ReceiptVoucherService
from receipts.views.receipt_exports import ReceiptVoucherPDFAPIView
from receipts.views.receipt_voucher import (
    ReceiptVoucherApprovalAPIView,
    ReceiptVoucherListCreateAPIView,
)
from posting.adapters.receipt_voucher import ReceiptVoucherPostingAdapter


class FakeRelated(list):
    def all(self):
        return self


class PaymentPostingAdapterTests(SimpleTestCase):
    def _header(self):
        return SimpleNamespace(
            id=1,
            voucher_code="RV-1",
            cash_received_amount=Decimal("100.00"),
            received_in_id=10,
            received_from_id=20,
        )

    def test_build_journal_lines_with_adjustments(self):
        header = self._header()
        adjustments = [
            SimpleNamespace(id=1, amount=Decimal("10.00"), ledger_account_id=101, settlement_effect="PLUS", adj_type="TDS"),
            SimpleNamespace(id=2, amount=Decimal("5.00"), ledger_account_id=102, settlement_effect="MINUS", adj_type="BANK_CHARGES"),
        ]
        jl = ReceiptVoucherPostingAdapter._build_journal_lines(header=header, adjustments=adjustments, reverse=False)

        # Receipt posts Dr Bank/Cash, Cr Customer. Adjustment rows follow.
        self.assertEqual(jl[0].account_id, 10)
        self.assertTrue(jl[0].drcr)
        self.assertEqual(jl[0].amount, Decimal("100.00"))

        # Customer settlement = 100 + 10 - 5 = 105
        self.assertEqual(jl[1].account_id, 20)
        self.assertFalse(jl[1].drcr)
        self.assertEqual(jl[1].amount, Decimal("105.00"))

        # PLUS => DR ledger
        self.assertEqual(jl[2].account_id, 101)
        self.assertTrue(jl[2].drcr)
        self.assertEqual(jl[2].amount, Decimal("10.00"))

        # MINUS => CR ledger
        self.assertEqual(jl[3].account_id, 102)
        self.assertFalse(jl[3].drcr)
        self.assertEqual(jl[3].amount, Decimal("5.00"))


class ReceiptVoucherServiceTests(SimpleTestCase):
    databases = {"default"}

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._sync_runtime_tcs_computation")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._fresh_allocation_rows")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherPostingAdapter.post_receipt_voucher")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_post_voucher_calls_posting_adapter(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_post_adapter,
        mock_fresh_allocs,
        _mock_sync_tcs,
    ):
        header = SimpleNamespace(
            id=11,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=ReceiptVoucherHeader.Status.CONFIRMED,
            receipt_type=ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE,
            voucher_date=None,
            voucher_code="RV-11",
            reference_number=None,
            narration=None,
            cash_received_amount=Decimal("0.00"),
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
        mock_fresh_allocs.return_value = []

        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_allocation_on_post": "off",
            "sync_ar_settlement_on_post": "off",
        })

        res = ReceiptVoucherService.post_voucher.__wrapped__(voucher_id=11, posted_by_id=9)
        self.assertEqual(res.message, "Posted.")
        self.assertEqual(header.status, ReceiptVoucherHeader.Status.POSTED)
        mock_post_adapter.assert_called_once()

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._sync_runtime_tcs_computation")
    @patch("receipts.services.receipt_voucher_service.SalesArService.cancel_settlement")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherPostingAdapter.unpost_receipt_voucher")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_unpost_voucher_cancels_ap_and_reverses_posting(self, mock_header_objects, mock_get_policy, mock_unpost_adapter, mock_cancel_settlement, _mock_sync_tcs):
        header = SimpleNamespace(
            id=12,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=ReceiptVoucherHeader.Status.POSTED,
            ap_settlement_id=99,
            created_by_id=5,
            voucher_code="RV-12",
            workflow_payload={},
            adjustments=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={"unpost_target_status": "confirmed"})

        res = ReceiptVoucherService.unpost_voucher.__wrapped__(voucher_id=12, unposted_by_id=9)
        self.assertEqual(res.message, "Unposted with reversal entry.")
        self.assertEqual(header.status, ReceiptVoucherHeader.Status.CONFIRMED)
        self.assertIsNone(header.ap_settlement_id)
        mock_cancel_settlement.assert_called_once_with(settlement_id=99, cancelled_by_id=9)
        mock_unpost_adapter.assert_called_once()

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherAllocation.objects")
    def test_validate_adjustment_allocation_links_rejects_foreign_allocation(self, mock_alloc_objects):
        mock_alloc_objects.filter.return_value.exists.return_value = False
        with self.assertRaisesMessage(ValueError, "allocation must belong to this receipt voucher"):
            ReceiptVoucherService._validate_adjustment_allocation_links(
                voucher_id=1,
                adjustments=[{"allocation": 99, "amount": Decimal("10.00")}],
            )

    def test_validate_allocation_effective_match_hard_raises(self):
        with self.assertRaisesMessage(ValueError, "does not match settlement effective amount"):
            ReceiptVoucherService._validate_allocation_effective_match(
                effective_amount=Decimal("100.00"),
                allocation_total=Decimal("90.00"),
                level="hard",
            )

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._sync_runtime_tcs_computation")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._fresh_allocation_rows")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherPostingAdapter.post_receipt_voucher")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_post_voucher_warn_mode_returns_warning_message(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_post_adapter,
        mock_fresh_allocs,
        _mock_sync_tcs,
    ):
        row = SimpleNamespace(open_item_id=501, settled_amount=Decimal("120.00"))
        header = SimpleNamespace(
            id=21,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=ReceiptVoucherHeader.Status.CONFIRMED,
            receipt_type=ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE,
            voucher_date=None,
            voucher_code="RV-21",
            reference_number=None,
            narration=None,
            created_by_id=5,
            ap_settlement_id=None,
            approved_at=None,
            approved_by_id=None,
            workflow_payload={},
            cash_received_amount=Decimal("120.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("120.00"),
            adjustments=SimpleNamespace(all=lambda: [], values=lambda *args, **kwargs: []),
            allocations=SimpleNamespace(all=lambda: [row]),
            advance_adjustments=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_fresh_allocs.return_value = [row]
        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_allocation_on_post": "hard",
            "sync_ar_settlement_on_post": "off",
            "over_settlement_rule": "warn",
            "allocation_amount_match_rule": "warn",
        })
        with patch.object(ReceiptVoucherService, "_validate_allocations", return_value=["over settlement"]) as mock_val:
            res = ReceiptVoucherService.post_voucher.__wrapped__(voucher_id=21, posted_by_id=9)
        self.assertIn("Posted with warnings", res.message)
        mock_val.assert_called_once()
        mock_post_adapter.assert_called_once()

    @patch("receipts.services.receipt_voucher_service.CustomerBillOpenItem.objects")
    @patch("receipts.services.receipt_voucher_service.SalesArService.list_open_advances")
    def test_validate_advance_adjustments_rejects_over_consumption(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            received_from_id=99,
        )
        advance = SimpleNamespace(id=14, outstanding_amount=Decimal("50000.00"))
        open_item = SimpleNamespace(
            id=55,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            customer_id=99,
        )
        mock_list_open_advances.return_value.filter.return_value.first.return_value = advance
        mock_open_item_objects.filter.return_value.first.return_value = open_item

        with self.assertRaisesMessage(ValueError, "exceeds available balance"):
            ReceiptVoucherService._validate_advance_adjustments(
                voucher=voucher,
                allocations=[{"open_item": 55, "settled_amount": Decimal("60000.00")}],
                advance_adjustments=[{
                    "advance_balance_id": 14,
                    "open_item": 55,
                    "adjusted_amount": Decimal("50001.00"),
                }],
            )

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._sync_runtime_tcs_computation")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._fresh_allocation_rows")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherPostingAdapter.post_receipt_voucher")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_post_voucher_with_advance_adjustments_requires_ap_sync(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_post_adapter,
        mock_fresh_allocs,
        _mock_sync_tcs,
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
            status=ReceiptVoucherHeader.Status.CONFIRMED,
            receipt_type=ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE,
            voucher_date=None,
            voucher_code="RV-31",
            reference_number=None,
            narration=None,
            cash_received_amount=Decimal("66000.00"),
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
        mock_fresh_allocs.return_value = [alloc_row]
        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_allocation_on_post": "hard",
            "sync_ar_settlement_on_post": "off",
            "allocation_amount_match_rule": "hard",
            "require_confirm_before_post": "on",
            "receipt_maker_checker": "off",
            "over_settlement_rule": "block",
            "allocation_policy": "manual",
        })

        with patch.object(ReceiptVoucherService, "_validate_advance_adjustments", return_value=None), \
             patch.object(ReceiptVoucherService, "_validate_allocations", return_value=[]):
            with self.assertRaisesMessage(ValueError, "Advance adjustments require AR settlement sync to be enabled."):
                ReceiptVoucherService.post_voucher.__wrapped__(voucher_id=31, posted_by_id=9)
        mock_post_adapter.assert_not_called()

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._sync_runtime_tcs_computation")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._fresh_allocation_rows")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherPostingAdapter.post_receipt_voucher")
    @patch("receipts.services.receipt_voucher_service.SalesArService.post_settlement")
    @patch("receipts.services.receipt_voucher_service.SalesArService.create_settlement")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_post_voucher_with_advance_adjustment_creates_cash_and_advance_settlements(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_create_settlement,
        mock_post_settlement,
        mock_post_adapter,
        mock_fresh_allocs,
        _mock_sync_tcs,
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
            status=ReceiptVoucherHeader.Status.CONFIRMED,
            receipt_type=ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE,
            voucher_date="2026-03-07",
            voucher_code="RV-32",
            reference_number="UTR-1",
            narration="test",
            received_from_id=99,
            cash_received_amount=Decimal("66000.00"),
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
        mock_fresh_allocs.return_value = [alloc_row]
        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_allocation_on_post": "hard",
            "sync_ar_settlement_on_post": "on",
            "allocation_amount_match_rule": "hard",
            "require_confirm_before_post": "on",
            "receipt_maker_checker": "off",
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

        with patch.object(ReceiptVoucherService, "_validate_advance_adjustments", return_value=None), \
             patch.object(ReceiptVoucherService, "_validate_allocations", return_value=[]):
            res = ReceiptVoucherService.post_voucher.__wrapped__(voucher_id=32, posted_by_id=9)

        self.assertEqual(res.message, "Posted.")
        self.assertEqual(header.status, ReceiptVoucherHeader.Status.POSTED)
        self.assertEqual(header.ap_settlement_id, 201)
        self.assertEqual(advance_row.ap_settlement_id, 202)
        cash_call = mock_create_settlement.call_args_list[0].kwargs
        adv_call = mock_create_settlement.call_args_list[1].kwargs
        self.assertEqual(cash_call["settlement_type"], "receipt")
        self.assertEqual(cash_call["lines"][0]["amount"], Decimal("66000.00"))
        self.assertEqual(adv_call["settlement_type"], "advance_adjustment")
        self.assertEqual(adv_call["advance_balance_id"], 14)
        self.assertEqual(adv_call["lines"][0]["amount"], Decimal("50000.00"))
        mock_post_adapter.assert_called_once()

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._sync_runtime_tcs_computation")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.SalesArService.cancel_settlement")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherPostingAdapter.unpost_receipt_voucher")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_unpost_voucher_reopens_advance_adjustment_settlements(
        self,
        mock_header_objects,
        mock_unpost_adapter,
        mock_cancel_settlement,
        mock_get_policy,
        _mock_sync_tcs,
    ):
        advance_balance = SimpleNamespace(is_open=True, adjusted_amount=Decimal("0.00"), outstanding_amount=Decimal("0.00"), save=MagicMock())
        advance_row = SimpleNamespace(ap_settlement_id=202, save=MagicMock())
        header = SimpleNamespace(
            id=41,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=ReceiptVoucherHeader.Status.POSTED,
            ap_settlement_id=201,
            created_by_id=5,
            voucher_code="RV-41",
            workflow_payload={},
            adjustments=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: [advance_row]),
            customer_advance_balance=advance_balance,
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={"unpost_target_status": "draft"})

        res = ReceiptVoucherService.unpost_voucher.__wrapped__(voucher_id=41, unposted_by_id=9)

        self.assertEqual(res.message, "Unposted with reversal entry.")
        self.assertEqual(header.status, ReceiptVoucherHeader.Status.DRAFT)
        self.assertIsNone(header.ap_settlement_id)
        self.assertIsNone(advance_row.ap_settlement_id)
        self.assertEqual(mock_cancel_settlement.call_count, 2)
        advance_balance.save.assert_called_once()
        mock_unpost_adapter.assert_called_once()


class PaymentVoucherAdvanceEdgeCaseTests(SimpleTestCase):
    @patch("receipts.services.receipt_voucher_service.CustomerBillOpenItem.objects")
    @patch("receipts.services.receipt_voucher_service.SalesArService.list_open_advances")
    def test_partial_advance_consumption_with_remaining_balance(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, received_from_id=99)
        advance = SimpleNamespace(id=14, outstanding_amount=Decimal("50000.00"))
        open_item = SimpleNamespace(id=55, entity_id=1, entityfinid_id=1, subentity_id=None, customer_id=99)
        mock_list_open_advances.return_value.filter.return_value.first.return_value = advance
        mock_open_item_objects.filter.return_value.first.return_value = open_item

        ReceiptVoucherService._validate_advance_adjustments(
            voucher=voucher,
            allocations=[{"open_item": 55, "settled_amount": Decimal("60000.00")}],
            advance_adjustments=[{"advance_balance_id": 14, "open_item": 55, "adjusted_amount": Decimal("36000.00")}],
        )

    @patch("receipts.services.receipt_voucher_service.CustomerBillOpenItem.objects")
    @patch("receipts.services.receipt_voucher_service.SalesArService.list_open_advances")
    def test_multiple_advances_against_one_bill(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, received_from_id=99)
        advances = {
            14: SimpleNamespace(id=14, outstanding_amount=Decimal("30000.00")),
            15: SimpleNamespace(id=15, outstanding_amount=Decimal("20000.00")),
        }
        open_item = SimpleNamespace(id=55, entity_id=1, entityfinid_id=1, subentity_id=None, customer_id=99)
        mock_list_open_advances.return_value.filter.side_effect = lambda id: SimpleNamespace(first=lambda: advances[id])
        mock_open_item_objects.filter.return_value.first.return_value = open_item

        ReceiptVoucherService._validate_advance_adjustments(
            voucher=voucher,
            allocations=[{"open_item": 55, "settled_amount": Decimal("116000.00")}],
            advance_adjustments=[
                {"advance_balance_id": 14, "open_item": 55, "adjusted_amount": Decimal("30000.00")},
                {"advance_balance_id": 15, "open_item": 55, "adjusted_amount": Decimal("20000.00")},
            ],
        )

    @patch("receipts.services.receipt_voucher_service.CustomerBillOpenItem.objects")
    @patch("receipts.services.receipt_voucher_service.SalesArService.list_open_advances")
    def test_one_advance_across_multiple_bills(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, received_from_id=99)
        advance = SimpleNamespace(id=14, outstanding_amount=Decimal("50000.00"))
        items = {
            55: SimpleNamespace(id=55, entity_id=1, entityfinid_id=1, subentity_id=None, customer_id=99),
            56: SimpleNamespace(id=56, entity_id=1, entityfinid_id=1, subentity_id=None, customer_id=99),
        }
        mock_list_open_advances.return_value.filter.return_value.first.return_value = advance
        mock_open_item_objects.filter.side_effect = lambda pk: SimpleNamespace(first=lambda: items[pk])

        ReceiptVoucherService._validate_advance_adjustments(
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

    @patch("receipts.services.receipt_voucher_service.CustomerBillOpenItem.objects")
    @patch("receipts.services.receipt_voucher_service.SalesArService.list_open_advances")
    def test_customer_mismatch_on_advance(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, received_from_id=99)
        advance = SimpleNamespace(id=14, outstanding_amount=Decimal("50000.00"))
        open_item = SimpleNamespace(id=55, entity_id=1, entityfinid_id=1, subentity_id=None, customer_id=77)
        mock_list_open_advances.return_value.filter.return_value.first.return_value = advance
        mock_open_item_objects.filter.return_value.first.return_value = open_item

        with self.assertRaisesMessage(ValueError, "customer mismatch with received_from"):
            ReceiptVoucherService._validate_advance_adjustments(
                voucher=voucher,
                allocations=[{"open_item": 55, "settled_amount": Decimal("60000.00")}],
                advance_adjustments=[{"advance_balance_id": 14, "open_item": 55, "adjusted_amount": Decimal("10000.00")}],
            )

    @patch("receipts.services.receipt_voucher_service.CustomerBillOpenItem.objects")
    @patch("receipts.services.receipt_voucher_service.SalesArService.list_open_advances")
    def test_entity_entityfinid_mismatch_on_advance(self, mock_list_open_advances, mock_open_item_objects):
        voucher = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, received_from_id=99)
        advance = SimpleNamespace(id=14, outstanding_amount=Decimal("50000.00"))
        open_item = SimpleNamespace(id=55, entity_id=2, entityfinid_id=1, subentity_id=None, customer_id=99)
        mock_list_open_advances.return_value.filter.return_value.first.return_value = advance
        mock_open_item_objects.filter.return_value.first.return_value = open_item

        with self.assertRaisesMessage(ValueError, "open_item scope mismatch"):
            ReceiptVoucherService._validate_advance_adjustments(
                voucher=voucher,
                allocations=[{"open_item": 55, "settled_amount": Decimal("60000.00")}],
                advance_adjustments=[{"advance_balance_id": 14, "open_item": 55, "adjusted_amount": Decimal("10000.00")}],
            )

    def test_allocation_mismatch_with_cash_and_advance_combined(self):
        with self.assertRaisesMessage(ValueError, "does not match settlement effective amount"):
            ReceiptVoucherService._validate_allocation_effective_match(
                effective_amount=Decimal("116000.00"),
                allocation_total=Decimal("100000.00"),
                level="hard",
            )

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService.confirm_voucher")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_maker_checker_confirm_before_post_flow_requires_confirm(self, mock_header_objects, mock_get_policy, mock_confirm):
        header = SimpleNamespace(
            id=51,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=ReceiptVoucherHeader.Status.DRAFT,
            receipt_type=ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE,
            workflow_payload={"_approval_state": {"status": "APPROVED"}},
            adjustments=SimpleNamespace(values=lambda *args, **kwargs: []),
            advance_adjustments=SimpleNamespace(all=lambda: []),
            allocations=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_confirm_before_post": "on",
            "receipt_maker_checker": "hard",
        })

        with self.assertRaisesMessage(ValueError, "Only CONFIRMED vouchers can be posted."):
            ReceiptVoucherService.post_voucher.__wrapped__(voucher_id=51, posted_by_id=9)
        mock_confirm.assert_not_called()

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherPostingAdapter.post_receipt_voucher")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_maker_checker_confirm_before_post_flow_requires_approved_status(self, mock_header_objects, mock_get_policy, mock_post_adapter):
        header = SimpleNamespace(
            id=52,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=ReceiptVoucherHeader.Status.CONFIRMED,
            receipt_type=ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE,
            workflow_payload={"_approval_state": {"status": "SUBMITTED"}},
            cash_received_amount=Decimal("0.00"),
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
            "receipt_maker_checker": "hard",
            "require_allocation_on_post": "off",
            "sync_ar_settlement_on_post": "off",
        })

        with self.assertRaisesMessage(ValueError, "Voucher must be approved before posting by policy."):
            ReceiptVoucherService.post_voucher.__wrapped__(voucher_id=52, posted_by_id=9)
        mock_post_adapter.assert_not_called()

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._validate_advance_adjustments")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._validate_allocations")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._validate_adjustment_allocation_links")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherAdjustment.objects.create")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherAdvanceAdjustment.objects.create")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherAllocation.objects.create")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects.create")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._sync_runtime_tcs_computation")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._account_ledger_id")
    def test_draft_create_with_advance_adjustments(
        self,
        mock_account_ledger_id,
        _mock_sync_tcs,
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

        ReceiptVoucherService.create_voucher.__wrapped__({
            "entity": SimpleNamespace(id=1),
            "entityfinid": SimpleNamespace(id=1),
            "subentity": None,
            "received_from": SimpleNamespace(id=99),
            "cash_received_amount": Decimal("66000.00"),
            "receipt_type": ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE,
            "doc_code": "RV",
            "allocations": [{"open_item": 55, "settled_amount": Decimal("116000.00")}],
            "advance_adjustments": [{"advance_balance_id": 14, "open_item": 55, "adjusted_amount": Decimal("50000.00"), "remarks": "adjust"}],
            "adjustments": [],
        })
        mock_alloc_create.assert_called_once()
        mock_adv_create.assert_called_once()
        self.assertEqual(mock_adv_create.call_args.kwargs["advance_balance_id"], 14)
        self.assertEqual(mock_adv_create.call_args.kwargs["open_item_id"], 55)

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._sync_runtime_tcs_computation")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._validate_advance_adjustments")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._validate_adjustment_allocation_links")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    def test_draft_update_with_advance_adjustments(self, mock_get_policy, mock_validate_adj_links, mock_validate_adv, _mock_sync_tcs):
        adv_row = MagicMock()
        adv_row.id = 71
        alloc_row = SimpleNamespace(open_item_id=55, settled_amount=Decimal("116000.00"))
        instance = SimpleNamespace(
            id=70,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=ReceiptVoucherHeader.Status.DRAFT,
            workflow_payload={},
            cash_received_amount=Decimal("66000.00"),
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

        ReceiptVoucherService.update_voucher.__wrapped__(instance, {
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
                receipt_voucher=SimpleNamespace(
                    id=81,
                    voucher_code="RV-ADV-1004",
                    doc_code="RV",
                    voucher_date="2026-03-06",
                    receipt_type="ADVANCE",
                ),
                reference_no="RV-ADV-1004",
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
            doc_code="RV",
            doc_no=11,
            voucher_code="RV-RV-2026-00011",
            currency_code="INR",
            base_currency_code="INR",
            exchange_rate=Decimal("1.000000"),
            receipt_type=ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE,
            supply_type=ReceiptVoucherHeader.SupplyType.SERVICES,
            received_in_id=157,
            received_in=SimpleNamespace(pk=157, accountname="Bank"),
            received_from_id=171,
            received_from=SimpleNamespace(pk=171, accountname="RRR"),
            receipt_mode=SimpleNamespace(pk=1, paymentmode="NEFT"),
            cash_received_amount=Decimal("66000.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("66000.00"),
            settlement_effective_amount_base_currency=Decimal("66000.00"),
            reference_number="UTR-1003",
            narration="test",
            instrument_date=None,
            place_of_supply_state=None,
            customer_gstin=None,
            advance_taxable_value=Decimal("0.00"),
            advance_cgst=Decimal("0.00"),
            advance_sgst=Decimal("0.00"),
            advance_igst=Decimal("0.00"),
            advance_cess=Decimal("0.00"),
            status=ReceiptVoucherHeader.Status.CONFIRMED,
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
            customer_advance_balance=None,
            allocations=FakeRelated([allocation_row]),
            advance_adjustments=FakeRelated([advance_adj]),
            adjustments=FakeRelated([]),
            created_at=None,
            updated_at=None,
            get_status_display=lambda: "Confirmed",
            get_receipt_type_display=lambda: "Against Invoice",
            get_supply_type_display=lambda: "Services",
        )

        with patch("receipts.serializers.receipt_voucher.ReceiptVoucherNavService.get_prev_next_for_instance", return_value={"previous": {"id": 5}, "next": {"id": 7}}), \
             patch("receipts.serializers.receipt_voucher.ReceiptVoucherNavService.get_number_navigation", return_value={"enabled": True, "current_number": 11}):
            data = ReceiptVoucherHeaderSerializer(instance).data

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
        request = factory.get("/api/payments/receipt-vouchers/6/pdf/?entity=32&entityfinid=32")
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))

        voucher = SimpleNamespace(
            id=6,
            voucher_code="RV-RV-2026-00011",
            doc_code="RV",
            doc_no=11,
            voucher_date="2026-03-07",
            get_status_display=lambda: "Confirmed",
            get_receipt_type_display=lambda: "Against Invoice",
            get_supply_type_display=lambda: "Services",
            received_in=SimpleNamespace(accountname="Bank"),
            received_from=SimpleNamespace(accountname="RRR"),
            receipt_mode=SimpleNamespace(paymentmode="NEFT"),
            reference_number="UTR-1",
            cash_received_amount=Decimal("10000.00"),
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

        with patch("receipts.views.receipt_exports.ReceiptVoucherHeader.objects", qs):
            response = ReceiptVoucherPDFAPIView.as_view()(request, pk=6)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")


class ReceiptVoucherViewValidationTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=7)

    def _request(self, path: str, data=None):
        request = self.factory.post(path, data or {}, format="json") if data is not None else self.factory.get(path)
        force_authenticate(request, user=self.user)
        return request

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    def test_list_view_reports_missing_scope_as_field_errors(self, mocked_error_log):
        request = self._request("/api/receipts/receipt-vouchers/")

        response = ReceiptVoucherListCreateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["entity"]), "This query param is required.")
        self.assertEqual(str(response.data["entityfinid"]), "This query param is required.")
        mocked_error_log.assert_called_once()

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch("receipts.views.receipt_voucher.ReceiptVoucherHeader.objects")
    def test_approval_view_reports_invalid_action_on_action_field(self, mocked_header_objects, mocked_error_log):
        mocked_header_objects.only.return_value.get.return_value = SimpleNamespace(id=9, entity_id=1)
        request = self._request(
            "/api/receipts/receipt-vouchers/9/approval/",
            {"action": "ship"},
        )

        response = ReceiptVoucherApprovalAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["action"]), "Use submit, approve, or reject.")
        mocked_error_log.assert_called_once()



class ReceiptRuntimeWithholdingTests(SimpleTestCase):
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_ledger_id")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_account_id")
    @patch("receipts.services.receipt_voucher_service.compute_withholding_preview")
    def test_runtime_withholding_adds_auto_tcs_adjustment(self, mock_preview, mock_get_account_id, mock_get_ledger_id):
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001
        mock_preview.return_value = SimpleNamespace(rate=Decimal("1.0000"), amount=Decimal("10.00"), reason="auto", reason_code="OK")

        adjustments, payload = ReceiptVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            received_from_id=55,
            voucher_date=None,
            cash_received_amount=Decimal("100.00"),
            allocations=[{"open_item": 1, "settled_amount": Decimal("100.00")}],
            adjustments=[],
            workflow_payload={"withholding": {"enabled": True, "section_id": 5, "mode": "AUTO", "allow_static_fallback": True}},
        )

        self.assertEqual(len(adjustments), 1)
        self.assertEqual(adjustments[0]["adj_type"], "TCS")
        self.assertEqual(adjustments[0]["settlement_effect"], "PLUS")
        self.assertEqual(adjustments[0]["amount"], Decimal("10.00"))
        self.assertEqual(adjustments[0]["remarks"], ReceiptVoucherService.AUTO_WITHHOLDING_TCS_REMARK)
        self.assertIn("withholding_runtime_result", payload)

    def test_runtime_withholding_disabled_removes_auto_row(self):
        adjustments, payload = ReceiptVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            received_from_id=55,
            voucher_date=None,
            cash_received_amount=Decimal("100.00"),
            allocations=[],
            adjustments=[
                {"adj_type": "TCS", "amount": Decimal("5.00"), "remarks": ReceiptVoucherService.AUTO_WITHHOLDING_TCS_REMARK},
                {"adj_type": "BANK_CHARGES", "amount": Decimal("2.00"), "remarks": "manual"},
            ],
            workflow_payload={"withholding": {"enabled": False}},
        )

        self.assertEqual(len(adjustments), 1)
        self.assertEqual(adjustments[0]["adj_type"], "BANK_CHARGES")
        self.assertEqual(payload.get("withholding_runtime_result", {}).get("reason_code"), "DISABLED")

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._resolve_entity_runtime_tcs_mapping")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_ledger_id")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_account_id")
    def test_entity_mapping_overrides_section_and_static(
        self,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_resolve_entity,
    ):
        mock_resolve_entity.return_value = (888, 444)
        section = SimpleNamespace(id=10)
        account_id, ledger_id, source = ReceiptVoucherService._resolve_runtime_tcs_target_accounts(
            entity_id=1,
            subentity_id=17,
            section=section,
        )
        self.assertEqual(account_id, 888)
        self.assertEqual(ledger_id, 444)
        self.assertEqual(source, "ENTITY_MAP")
        mock_get_account_id.assert_not_called()
        mock_get_ledger_id.assert_not_called()

    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_ledger_id")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_account_id")
    @patch("receipts.services.receipt_voucher_service.compute_withholding_preview")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._resolve_entity_runtime_tcs_mapping")
    def test_runtime_withholding_blocks_when_only_static_fallback_available(
        self,
        mock_resolve_entity,
        mock_preview,
        mock_get_account_id,
        mock_get_ledger_id,
    ):
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
        with self.assertRaisesMessage(ValueError, "Runtime TCS mapping missing for selected section"):
            ReceiptVoucherService._apply_runtime_withholding_to_adjustments(
                entity_id=1,
                entityfinid_id=1,
                subentity_id=17,
                received_from_id=55,
                voucher_date=None,
                cash_received_amount=Decimal("100.00"),
                allocations=[{"open_item": 1, "settled_amount": Decimal("100.00")}],
                adjustments=[],
                workflow_payload={"withholding": {"enabled": True, "section_id": 10, "mode": "AUTO"}},
            )
