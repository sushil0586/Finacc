from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.http import Http404
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
from numbering.models import DocumentNumberSeries, DocumentType
from numbering.seeding import NumberingSeedService
from payments.models import PaymentVoucherHeader
from payments.serializers.payment_voucher import PaymentVoucherHeaderSerializer
from payments.services.payment_voucher_service import PaymentVoucherService
from payments.services.payment_settings_service import PaymentSettingsService
from payments.views.payment_exports import PaymentVoucherPDFAPIView
from payments.views.payment_meta import PaymentVoucherDetailFormMetaAPIView
from payments.views.payment_voucher import (
    PaymentVoucherApprovalAPIView,
    PaymentVoucherCancelAPIView,
    PaymentVoucherLookupAPIView,
    PaymentVoucherListCreateAPIView,
    PaymentVoucherPostAPIView,
    _duplicate_reference_warnings,
)
from payments.views.payment_settings import PaymentSettingsAPIView
from posting.adapters.payment_voucher import PaymentVoucherPostingAdapter
from purchase.models.purchase_ap import VendorSettlement
from purchase.services.purchase_ap_service import PurchaseApService
from withholding.models import WithholdingBaseRule

User = get_user_model()


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
            paid_from=SimpleNamespace(accountname="HDFC Bank", ledger_id=10),
            paid_to=SimpleNamespace(accountname="Vendor-A", ledger_id=20),
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
        self.assertIn("Vendor Vendor-A", jl[0].description)
        self.assertIn("From HDFC Bank", jl[0].description)


class PaymentVoucherReferenceWarningTests(SimpleTestCase):
    @patch("payments.views.payment_voucher.PaymentVoucherHeader.objects")
    def test_duplicate_reference_warning_includes_existing_voucher_code(self, mocked_objects):
        mocked_objects.filter.return_value.exclude.return_value.order_by.return_value.filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            voucher_code="PPV-1002",
            doc_code="PPV",
            doc_no=1002,
        )
        voucher = SimpleNamespace(
            id=99,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=5,
            paid_to_id=77,
            reference_number="UTR-001",
        )

        warnings = _duplicate_reference_warnings(voucher)

        self.assertEqual(warnings, [
            "Reference already appears on voucher PPV-1002. Please double-check before proceeding."
        ])


class PaymentVoucherServiceTests(SimpleTestCase):
    databases = {"default"}

    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_submit_voucher_returns_already_submitted_for_repeat_submit(self, mock_header_objects):
        header = SimpleNamespace(
            status=PaymentVoucherHeader.Status.DRAFT,
            workflow_payload={"_approval_state": {"status": "SUBMITTED", "submitted_by": 7}},
        )
        mock_header_objects.select_for_update.return_value.get.return_value = header

        result = PaymentVoucherService.submit_voucher.__wrapped__(voucher_id=11, submitted_by_id=7, remarks="Retry")

        self.assertEqual(result.message, "Already submitted.")

    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_approve_voucher_returns_already_approved_for_repeat_approve(self, mock_header_objects, mock_get_policy):
        header = SimpleNamespace(
            entity_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.CONFIRMED,
            workflow_payload={"_approval_state": {"status": "APPROVED", "submitted_by": 7, "approved_by": 8}},
        )
        mock_header_objects.select_for_update.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={})

        result = PaymentVoucherService.approve_voucher.__wrapped__(voucher_id=11, approved_by_id=8, remarks="Retry")

        self.assertEqual(result.message, "Already approved.")

    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_reject_voucher_returns_already_rejected_for_repeat_reject(self, mock_header_objects):
        header = SimpleNamespace(
            status=PaymentVoucherHeader.Status.CONFIRMED,
            workflow_payload={"_approval_state": {"status": "REJECTED", "rejected_by": 8}},
        )
        mock_header_objects.select_for_update.return_value.get.return_value = header

        result = PaymentVoucherService.reject_voucher.__wrapped__(voucher_id=11, rejected_by_id=8, remarks="Retry")

        self.assertEqual(result.message, "Already rejected.")

    @patch("payments.services.payment_voucher_service.PaymentVoucherService._resolve_financial_year")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_post_voucher_blocks_when_books_locked(self, mock_header_objects, mock_resolve_year):
        header = SimpleNamespace(
            id=51,
            entity_id=1,
            entityfinid_id=2,
            voucher_date=date(2026, 4, 15),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.select_for_update.return_value.get.return_value = header
        mock_resolve_year.return_value = SimpleNamespace(
            id=2,
            desc="FY 2026-27",
            year_code="2026-27",
            is_year_closed=False,
            period_status="OPEN",
            books_locked_until=date(2026, 4, 30),
            ap_ar_locked_until=None,
            gst_locked_until=None,
            inventory_locked_until=None,
        )

        with self.assertRaisesMessage(ValueError, "Cannot post voucher: Books locked up to 2026-04-30 in financial year FY 2026-27."):
            PaymentVoucherService.post_voucher.__wrapped__(voucher_id=51, posted_by_id=9)

    @patch("payments.services.payment_voucher_service.PaymentVoucherService._resolve_financial_year")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_unpost_voucher_blocks_when_books_locked(self, mock_header_objects, mock_resolve_year):
        header = SimpleNamespace(
            id=52,
            entity_id=1,
            entityfinid_id=2,
            voucher_date=date(2026, 4, 15),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.select_for_update.return_value.get.return_value = header
        mock_resolve_year.return_value = SimpleNamespace(
            id=2,
            desc="FY 2026-27",
            year_code="2026-27",
            is_year_closed=False,
            period_status="OPEN",
            books_locked_until=date(2026, 4, 30),
            ap_ar_locked_until=None,
            gst_locked_until=None,
            inventory_locked_until=None,
        )

        with self.assertRaisesMessage(ValueError, "Cannot unpost voucher: Books locked up to 2026-04-30 in financial year FY 2026-27."):
            PaymentVoucherService.unpost_voucher.__wrapped__(voucher_id=52, unposted_by_id=9)

    @patch("payments.services.payment_voucher_service.PaymentVoucherService._resolve_financial_year")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_cancel_voucher_blocks_when_books_locked(self, mock_header_objects, mock_resolve_year):
        header = SimpleNamespace(
            id=53,
            entity_id=1,
            entityfinid_id=2,
            voucher_date=date(2026, 4, 15),
        )
        mock_header_objects.select_for_update.return_value.get.return_value = header
        mock_resolve_year.return_value = SimpleNamespace(
            id=2,
            desc="FY 2026-27",
            year_code="2026-27",
            is_year_closed=False,
            period_status="OPEN",
            books_locked_until=date(2026, 4, 30),
            ap_ar_locked_until=None,
            gst_locked_until=None,
            inventory_locked_until=None,
        )

        with self.assertRaisesMessage(ValueError, "Cannot cancel voucher: Books locked up to 2026-04-30 in financial year FY 2026-27."):
            PaymentVoucherService.cancel_voucher.__wrapped__(voucher_id=53, cancelled_by_id=9)

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

        mock_header_objects.select_related.return_value.prefetch_related.return_value.select_for_update.return_value.get.return_value = header

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
            voucher_date=date(2026, 5, 28),
            ap_settlement_id=99,
            created_by_id=5,
            voucher_code="PPV-12",
            workflow_payload={"_approval_state": {"status": "APPROVED", "approved_by": 8, "approved_at": "2026-05-28T10:00:00+0530"}},
            approved_at="2026-05-28T10:00:00+0530",
            approved_by_id=8,
            adjustments=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.select_for_update.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={"unpost_target_status": "confirmed"})

        res = PaymentVoucherService.unpost_voucher.__wrapped__(voucher_id=12, unposted_by_id=9)
        self.assertEqual(res.message, "Unposted with reversal entry. Voucher reopened for correction and reposting.")
        self.assertEqual(header.status, PaymentVoucherHeader.Status.CONFIRMED)
        self.assertIsNone(header.ap_settlement_id)
        self.assertEqual(header.workflow_payload["_approval_state"]["status"], "DRAFT")
        self.assertIsNone(header.approved_at)
        self.assertIsNone(header.approved_by_id)
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


class PurchaseApServiceUnitTests(SimpleTestCase):
    databases = {"default"}

    @patch("purchase.services.purchase_ap_service.VendorSettlement.objects")
    def test_post_settlement_returns_already_posted_for_repeat_post(self, mocked_objects):
        settlement = SimpleNamespace(
            status=VendorSettlement.Status.POSTED,
            total_amount=Decimal("125.00"),
        )
        mocked_objects.select_for_update.return_value.get.return_value = settlement

        result = PurchaseApService.post_settlement(settlement_id=91, posted_by_id=7)

        self.assertIs(result.settlement, settlement)
        self.assertEqual(result.applied_total, Decimal("125.00"))
        self.assertEqual(result.message, "Settlement already posted.")

    @patch("purchase.services.purchase_ap_service.VendorSettlement.objects")
    def test_cancel_settlement_returns_already_cancelled_for_repeat_cancel(self, mocked_objects):
        settlement = SimpleNamespace(status=VendorSettlement.Status.CANCELLED)
        mocked_objects.select_for_update.return_value.get.return_value = settlement

        result = PurchaseApService.cancel_settlement(settlement_id=92, cancelled_by_id=7)

        self.assertIs(result.settlement, settlement)
        self.assertEqual(result.message, "Settlement already cancelled.")

    @patch("purchase.services.purchase_ap_service.VendorSettlement.objects")
    def test_cancel_settlement_cancels_draft_without_reversal_work(self, mocked_objects):
        save_spy = MagicMock()
        settlement = SimpleNamespace(
            status=VendorSettlement.Status.DRAFT,
            save=save_spy,
        )
        mocked_objects.select_for_update.return_value.get.return_value = settlement

        result = PurchaseApService.cancel_settlement(settlement_id=93, cancelled_by_id=7)

        self.assertIs(result.settlement, settlement)
        self.assertEqual(settlement.status, VendorSettlement.Status.CANCELLED)
        self.assertEqual(result.message, "Draft settlement cancelled.")
        save_spy.assert_called_once_with(update_fields=["status", "updated_at"])

    @patch("purchase.services.purchase_ap_service.PurchaseApAllocationService.allocatable_map")
    @patch("purchase.services.purchase_ap_service.PurchaseSettingsService.get_policy")
    @patch("purchase.services.purchase_ap_service.VendorSettlement.objects")
    def test_post_settlement_warn_mode_caps_over_allocated_line_and_returns_warning(
        self,
        mocked_objects,
        mock_get_policy,
        mock_allocatable_map,
    ):
        item_save = MagicMock()
        line_save = MagicMock()
        settlement_save = MagicMock()
        open_item = SimpleNamespace(
            id=501,
            is_open=True,
            outstanding_amount=Decimal("100.00"),
            original_amount=Decimal("100.00"),
            settled_amount=Decimal("0.00"),
            last_settled_at=None,
            save=item_save,
        )
        line = SimpleNamespace(
            open_item=open_item,
            amount=Decimal("120.00"),
            applied_amount_signed=Decimal("0.00"),
            save=line_save,
        )
        settlement = SimpleNamespace(
            id=91,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            vendor_id=9,
            advance_balance_id=None,
            status=VendorSettlement.Status.DRAFT,
            settlement_type="payment_voucher",
            total_amount=Decimal("0.00"),
            posted_at=None,
            posted_by_id=None,
            lines=SimpleNamespace(
                select_related=lambda *args, **kwargs: SimpleNamespace(
                    select_for_update=lambda: SimpleNamespace(order_by=lambda *a, **k: [line])
                )
            ),
            save=settlement_save,
        )
        mocked_objects.select_for_update.return_value.get.return_value = settlement
        mock_get_policy.return_value = SimpleNamespace(controls={"over_settlement_rule": "warn"})
        mock_allocatable_map.return_value = {501: Decimal("80.00")}

        result = PurchaseApService.post_settlement(settlement_id=91, posted_by_id=7)

        self.assertEqual(result.applied_total, Decimal("80.00"))
        self.assertIn("Settlement posted with warnings:", result.message)
        self.assertIn("Line for open item 501 exceeds allocatable amount.", result.message)
        self.assertEqual(open_item.settled_amount, Decimal("80.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("20.00"))
        self.assertTrue(open_item.is_open)
        self.assertEqual(line.applied_amount_signed, Decimal("80.00"))
        item_save.assert_called_once()
        line_save.assert_called_once()
        settlement_save.assert_called_once_with(
            update_fields=["total_amount", "status", "posted_at", "posted_by", "updated_at"]
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

    @patch("payments.services.payment_voucher_service.logger")
    @patch("payments.services.payment_voucher_service.PaymentVoucherService._fresh_allocation_rows")
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("payments.services.payment_voucher_service.PurchaseApService.post_settlement")
    @patch("payments.services.payment_voucher_service.PurchaseApService.create_settlement")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_post_voucher_reuses_existing_ap_settlement_ids_on_retry(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_create_settlement,
        mock_post_settlement,
        mock_post_adapter,
        mock_fresh_allocs,
        mock_logger,
    ):
        advance_row = SimpleNamespace(
            advance_balance_id=14,
            allocation_id=None,
            open_item_id=55,
            adjusted_amount=Decimal("50000.00"),
            ap_settlement_id=202,
            remarks="adjust",
            save=MagicMock(),
        )
        alloc_row = SimpleNamespace(open_item_id=55, settled_amount=Decimal("116000.00"))
        header = SimpleNamespace(
            id=33,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.CONFIRMED,
            payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            voucher_date="2026-03-07",
            voucher_code="PPV-33",
            reference_number="UTR-2",
            narration="retry",
            paid_to_id=99,
            cash_paid_amount=Decimal("66000.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("66000.00"),
            settlement_effective_amount_base_currency=Decimal("66000.00"),
            exchange_rate=Decimal("1.000000"),
            created_by_id=5,
            ap_settlement_id=201,
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
            "sync_ap_settlement_on_post": "on",
            "allocation_amount_match_rule": "hard",
            "require_confirm_before_post": "on",
            "payment_maker_checker": "off",
            "over_settlement_rule": "block",
            "allocation_policy": "manual",
            "sync_advance_balance_on_post": "off",
        })
        mock_post_settlement.side_effect = [
            SimpleNamespace(settlement=SimpleNamespace(id=201)),
            SimpleNamespace(settlement=SimpleNamespace(id=202)),
        ]

        with patch.object(PaymentVoucherService, "_validate_advance_adjustments", return_value=None), \
             patch.object(PaymentVoucherService, "_validate_allocations", return_value=[]):
            res = PaymentVoucherService.post_voucher.__wrapped__(voucher_id=33, posted_by_id=9)

        self.assertIn("Posted with warnings:", res.message)
        self.assertIn("Payment settlement resumed from existing linked settlement", res.message)
        self.assertIn("Advance adjustment settlement resumed from existing linked settlement", res.message)
        mock_create_settlement.assert_not_called()
        self.assertEqual(mock_post_settlement.call_args_list[0].kwargs["settlement_id"], 201)
        self.assertEqual(mock_post_settlement.call_args_list[1].kwargs["settlement_id"], 202)
        self.assertEqual(mock_logger.info.call_count, 2)
        mock_post_adapter.assert_called_once()

    @patch.object(PaymentVoucherService, "_auto_fifo_allocations")
    @patch.object(PaymentVoucherService, "_fresh_allocation_rows", return_value=[])
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_post_voucher_manual_allocation_policy_does_not_auto_allocate_against_bill(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_post_adapter,
        _mock_fresh_allocations,
        mock_auto_fifo_allocations,
    ):
        header = SimpleNamespace(
            id=91,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.CONFIRMED,
            payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            voucher_date="2026-07-18",
            voucher_code="PPV-91",
            reference_number="UTR-MANUAL",
            narration="manual allocation policy",
            paid_to_id=99,
            cash_paid_amount=Decimal("590.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("590.00"),
            settlement_effective_amount_base_currency=Decimal("590.00"),
            exchange_rate=Decimal("1.000000"),
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
            "require_allocation_on_post": "hard",
            "sync_ap_settlement_on_post": "on",
            "allocation_amount_match_rule": "hard",
            "require_confirm_before_post": "on",
            "payment_maker_checker": "off",
            "over_settlement_rule": "block",
            "allocation_policy": "manual",
        })

        with patch.object(PaymentVoucherService, "_validate_advance_adjustments", return_value=None), \
             patch.object(PaymentVoucherService, "_validate_allocations", return_value=[]):
            with self.assertRaisesMessage(ValueError, "Allocations are required for AGAINST_BILL posting."):
                PaymentVoucherService.post_voucher.__wrapped__(voucher_id=91, posted_by_id=9)

        mock_auto_fifo_allocations.assert_not_called()
        mock_post_adapter.assert_not_called()

    @patch.object(PaymentVoucherService, "_fresh_allocation_rows")
    @patch.object(PaymentVoucherService, "_auto_fifo_allocations")
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("payments.services.payment_voucher_service.PurchaseApService.post_settlement")
    @patch("payments.services.payment_voucher_service.PurchaseApService.create_settlement")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherAllocation.objects.create")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_post_voucher_fifo_allocation_policy_auto_allocates_against_bill_before_post(
        self,
        mock_header_objects,
        mock_allocation_create,
        mock_get_policy,
        mock_create_settlement,
        mock_post_settlement,
        mock_post_adapter,
        mock_auto_fifo_allocations,
        mock_fresh_allocations,
    ):
        created_allocation = SimpleNamespace(open_item_id=55, settled_amount=Decimal("590.00"))
        header = SimpleNamespace(
            id=92,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.CONFIRMED,
            payment_type=PaymentVoucherHeader.PaymentType.AGAINST_BILL,
            voucher_date="2026-07-18",
            voucher_code="PPV-92",
            reference_number="UTR-FIFO",
            narration="fifo allocation policy",
            paid_to_id=99,
            cash_paid_amount=Decimal("590.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("590.00"),
            settlement_effective_amount_base_currency=Decimal("590.00"),
            exchange_rate=Decimal("1.000000"),
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
            "require_allocation_on_post": "hard",
            "sync_ap_settlement_on_post": "on",
            "allocation_amount_match_rule": "hard",
            "require_confirm_before_post": "on",
            "payment_maker_checker": "off",
            "over_settlement_rule": "block",
            "allocation_policy": "fifo",
            "sync_advance_balance_on_post": "off",
        })
        mock_auto_fifo_allocations.return_value = [
            {"open_item": 55, "settled_amount": Decimal("590.00"), "is_full_settlement": True, "is_advance_adjustment": False}
        ]
        mock_fresh_allocations.side_effect = [[], [created_allocation], [created_allocation]]
        mock_create_settlement.return_value = SimpleNamespace(settlement=SimpleNamespace(id=301))
        mock_post_settlement.return_value = SimpleNamespace(settlement=SimpleNamespace(id=401))

        with patch.object(PaymentVoucherService, "_validate_advance_adjustments", return_value=None), \
             patch.object(PaymentVoucherService, "_validate_allocations", return_value=[]):
            res = PaymentVoucherService.post_voucher.__wrapped__(voucher_id=92, posted_by_id=9)

        self.assertEqual(res.message, "Posted.")
        mock_auto_fifo_allocations.assert_called_once()
        mock_allocation_create.assert_called_once_with(
            payment_voucher=header,
            open_item_id=55,
            settled_amount=Decimal("590.00"),
            is_full_settlement=True,
            is_advance_adjustment=False,
        )
        mock_post_adapter.assert_called_once()

    @patch("payments.services.payment_voucher_service.VendorAdvanceBalance.objects")
    @patch("payments.services.payment_voucher_service.logger")
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("payments.services.payment_voucher_service.PaymentSettingsService.get_policy")
    @patch("payments.services.payment_voucher_service.PaymentVoucherHeader.objects")
    def test_post_voucher_reuses_existing_vendor_advance_balance_on_retry(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_post_adapter,
        mock_logger,
        mocked_adv_objects,
    ):
        existing_advance = SimpleNamespace(id=301)
        header = SimpleNamespace(
            id=34,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=PaymentVoucherHeader.Status.CONFIRMED,
            payment_type=PaymentVoucherHeader.PaymentType.ADVANCE,
            voucher_date="2026-03-08",
            voucher_code="PPV-34",
            reference_number="UTR-3",
            narration="advance retry",
            paid_to_id=99,
            cash_paid_amount=Decimal("5000.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("5000.00"),
            settlement_effective_amount_base_currency=Decimal("5000.00"),
            exchange_rate=Decimal("1.000000"),
            created_by_id=5,
            ap_settlement_id=None,
            approved_at=None,
            approved_by_id=None,
            workflow_payload={},
            vendor_advance_balance=None,
            adjustments=SimpleNamespace(all=lambda: [], values=lambda *args, **kwargs: []),
            allocations=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_allocation_on_post": "hard",
            "require_confirm_before_post": "on",
            "payment_maker_checker": "off",
            "sync_ap_settlement_on_post": "on",
            "sync_advance_balance_on_post": "on",
            "residual_to_advance_balance": "on",
        })
        mocked_adv_objects.filter.return_value.first.return_value = existing_advance

        with patch.object(PaymentVoucherService, "_validate_allocations", return_value=[]), \
             patch.object(PaymentVoucherService, "_validate_advance_adjustments", return_value=None), \
             patch("payments.services.payment_voucher_service.PurchaseApService.create_advance_balance") as mock_create_adv:
            res = PaymentVoucherService.post_voucher.__wrapped__(voucher_id=34, posted_by_id=9)

        self.assertIn("Posted with warnings:", res.message)
        self.assertIn("Payment advance balance resumed from existing linked balance", res.message)
        mock_create_adv.assert_not_called()
        self.assertIs(header.vendor_advance_balance, existing_advance)
        mock_logger.info.assert_called_once()
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
            workflow_payload={"_approval_state": {"status": "SUBMITTED", "submitted_by": 7}},
            approved_at="2026-05-28T10:00:00+0530",
            approved_by_id=8,
            adjustments=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: [advance_row]),
            vendor_advance_balance=advance_balance,
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={"unpost_target_status": "draft"})

        res = PaymentVoucherService.unpost_voucher.__wrapped__(voucher_id=41, unposted_by_id=9)

        self.assertEqual(res.message, "Unposted with reversal entry. Voucher reopened for correction and reposting.")
        self.assertEqual(header.status, PaymentVoucherHeader.Status.DRAFT)
        self.assertIsNone(header.ap_settlement_id)
        self.assertIsNone(advance_row.ap_settlement_id)
        self.assertEqual(header.workflow_payload["_approval_state"]["status"], "DRAFT")
        self.assertIsNone(header.approved_at)
        self.assertIsNone(header.approved_by_id)
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
            open_item=SimpleNamespace(
                pk=55,
                id=55,
                purchase_number="PI-PINV-1010",
                supplier_invoice_number="VEN-1",
                bill_date="2026-03-01",
                due_date="2026-03-31",
                gross_amount=Decimal("1428000.00"),
                net_payable_amount=Decimal("1141140.00"),
                tds_deducted=Decimal("20020.00"),
                gst_tds_deducted=Decimal("20020.00"),
            ),
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
        self.assertEqual(data["allocations"][0]["bill_date"], "2026-03-01")
        self.assertEqual(data["allocations"][0]["due_date"], "2026-03-31")
        self.assertEqual(str(data["allocations"][0]["gross_amount"]), "1428000.00")
        self.assertEqual(str(data["allocations"][0]["net_payable_amount"]), "1141140.00")
        self.assertEqual(str(data["allocations"][0]["tds_deducted"]), "20020.00")
        self.assertEqual(str(data["allocations"][0]["gst_tds_deducted"]), "20020.00")


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
    databases = {"default"}

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

    @patch("payments.views.payment_voucher.PaymentVoucherLookupAPIView.get_serializer")
    @patch("payments.views.payment_voucher._require_payment_permission")
    @patch("payments.views.payment_voucher.PaymentVoucherHeader.objects")
    def test_lookup_view_returns_capped_compact_payload(
        self,
        mocked_objects,
        _mocked_require_permission,
        mocked_get_serializer,
    ):
        queryset = MagicMock()
        queryset.filter.return_value = queryset
        queryset.select_related.return_value = queryset
        queryset.order_by.return_value = queryset
        queryset.only.return_value = queryset
        queryset.count.return_value = 320
        queryset.__getitem__.return_value = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        mocked_objects.filter.return_value = queryset
        mocked_get_serializer.return_value.data = [{"id": 1}, {"id": 2}]

        request = self._request("/api/payments/payment-vouchers/lookup/?entity=1&entityfinid=2&limit=500")

        response = PaymentVoucherLookupAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_count"], 320)
        self.assertEqual(response.data["returned_count"], 2)
        self.assertEqual(response.data["limit"], 250)
        self.assertTrue(response.data["has_more"])

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
        self.assertIn("not a valid choice", str(response.data["action"]))
        mocked_error_log.assert_called_once()

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch("payments.views.payment_voucher.PaymentVoucherHeader.objects")
    def test_approval_view_rejects_oversized_remarks(self, mocked_header_objects, mocked_error_log):
        mocked_header_objects.only.return_value.get.return_value = SimpleNamespace(id=9, entity_id=1)
        request = self._request(
            "/api/payments/payment-vouchers/9/approval/",
            {"action": "submit", "remarks": "R" * 256},
        )

        response = PaymentVoucherApprovalAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 400)
        self.assertIn("remarks", response.data)
        mocked_error_log.assert_called_once()

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch("payments.views.payment_voucher._require_payment_permission")
    @patch("payments.views.payment_voucher.PaymentVoucherHeader.objects")
    def test_cancel_view_rejects_oversized_reason(
        self,
        mocked_header_objects,
        _mocked_require_permission,
        mocked_error_log,
    ):
        mocked_header_objects.only.return_value.get.return_value = SimpleNamespace(id=9, entity_id=1)
        request = self._request(
            "/api/payments/payment-vouchers/9/cancel/",
            {"reason": "C" * 256},
        )

        response = PaymentVoucherCancelAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 400)
        self.assertIn("reason", response.data)
        mocked_error_log.assert_called_once()

    @patch("payments.views.payment_voucher._require_payment_permission")
    @patch("payments.views.payment_voucher.PaymentVoucherService.post_voucher")
    @patch("payments.views.payment_voucher.PaymentVoucherHeaderSerializer")
    @patch.object(PaymentVoucherPostAPIView, "_get_header")
    def test_post_view_returns_structured_warning_feedback(
        self,
        mocked_get_header,
        mocked_serializer,
        mocked_post_voucher,
        _mocked_require_permission,
    ):
        mocked_get_header.return_value = SimpleNamespace(id=9, entity_id=1)
        mocked_serializer.return_value.data = {"id": 9}
        mocked_post_voucher.return_value = SimpleNamespace(
            message="Posted with warnings: Advance settlement synced later | Static fallback used",
            header=SimpleNamespace(id=9),
        )
        request = self._request("/api/payments/payment-vouchers/9/post/", {})

        response = PaymentVoucherPostAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["notice"], "Posting completed with policy warnings.")
        self.assertEqual(response.data["warnings"], [
            "Advance settlement synced later",
            "Static fallback used",
        ])

    @patch("payments.views.payment_voucher.PaymentVoucherService.post_voucher")
    @patch("payments.views.payment_voucher.EffectivePermissionService.permission_codes_for_user", return_value=set())
    @patch("payments.views.payment_voucher.EffectivePermissionService.entity_for_user", return_value=SimpleNamespace(id=1))
    @patch.object(PaymentVoucherPostAPIView, "_get_header")
    def test_post_view_requires_backend_permission_before_service_call(
        self,
        mocked_get_header,
        _mocked_entity,
        _mocked_codes,
        mocked_post_voucher,
    ):
        mocked_get_header.return_value = SimpleNamespace(id=9, entity_id=1)
        request = self._request("/api/payments/payment-vouchers/9/post/?entity=1&entityfinid=2", {})

        response = PaymentVoucherPostAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 403)
        self.assertIn("Missing permission", str(response.data))
        mocked_post_voucher.assert_not_called()

    @patch("payments.views.payment_voucher.PaymentVoucherService.post_voucher")
    @patch.object(PaymentVoucherPostAPIView, "_get_header")
    def test_post_view_rejects_out_of_scope_header_before_service_call(
        self,
        mocked_get_header,
        mocked_post_voucher,
    ):
        mocked_get_header.side_effect = Http404()
        request = self._request("/api/payments/payment-vouchers/9/post/?entity=1&entityfinid=2&subentity=99", {})

        response = PaymentVoucherPostAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 404)
        mocked_post_voucher.assert_not_called()


class PaymentSettingsValidationTests(SimpleTestCase):
    databases = {"default"}

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=7)

    def _request(self, path: str, data=None):
        request = self.factory.patch(path, data or {}, format="json")
        force_authenticate(request, user=self.user)
        return request

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch.object(PaymentSettingsAPIView, "_payload", return_value={"ok": True})
    @patch.object(PaymentSettingsAPIView, "_scope", return_value=(1, None, 2))
    @patch("payments.views.payment_settings.PaymentSettingsService.upsert_settings")
    def test_settings_patch_rejects_oversized_lock_period_reason(
        self,
        mocked_upsert,
        _mocked_scope,
        _mocked_payload,
        mocked_error_log,
    ):
        mocked_upsert.return_value = SimpleNamespace(default_doc_code_payment="PPV")
        request = self._request(
            "/api/payments/settings/?entity=1&entityfinid=2",
            {"lock_periods": [{"lock_date": "2026-04-01", "reason": "R" * 201}]},
        )

        response = PaymentSettingsAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("lock_periods", response.data)
        mocked_error_log.assert_called_once()

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch.object(PaymentSettingsAPIView, "_payload", return_value={"ok": True})
    @patch.object(PaymentSettingsAPIView, "_scope", return_value=(1, None, 2))
    @patch.object(PaymentSettingsAPIView, "_valid_override_keys", return_value={"payment_modes": {"NEFT"}})
    @patch("payments.views.payment_settings.PaymentChoiceService.compile_choices", return_value={"payment_modes": [{"key": "NEFT"}]})
    @patch("payments.views.payment_settings.PaymentSettingsService.upsert_settings")
    def test_settings_patch_rejects_oversized_choice_override_label(
        self,
        mocked_upsert,
        _mocked_compile_choices,
        _mocked_valid_override_keys,
        _mocked_scope,
        _mocked_payload,
        mocked_error_log,
    ):
        mocked_upsert.return_value = SimpleNamespace(default_doc_code_payment="PPV")
        request = self._request(
            "/api/payments/settings/?entity=1&entityfinid=2",
            {
                "choice_overrides": [
                    {
                        "choice_group": "payment_modes",
                        "choice_key": "NEFT",
                        "is_enabled": True,
                        "override_label": "L" * 201,
                    }
                ]
            },
        )

        response = PaymentSettingsAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("choice_overrides", response.data)
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
    @patch("payments.services.payment_voucher_service.PaymentVoucherService._resolve_entity_runtime_tds_mapping")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_ledger_id")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_account_id")
    @patch("payments.services.payment_voucher_service.WithholdingSection.objects.filter")
    def test_runtime_withholding_manual_mode_reverse_calculates_base_from_net_payment_cash(
        self,
        mock_filter,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_resolve_entity,
    ):
        mock_filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            id=5,
            base_rule=WithholdingBaseRule.PAYMENT_VALUE,
            section_code="194A",
        )
        mock_resolve_entity.return_value = (None, None)
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001

        adjustments, payload = PaymentVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            paid_to_id=55,
            voucher_date=None,
            cash_paid_amount=Decimal("49500.00"),
            allocations=[],
            adjustments=[],
            workflow_payload={
                "withholding": {
                    "enabled": True,
                    "section_id": 5,
                    "mode": "MANUAL",
                    "manual_rate": "1.00",
                    "manual_amount": "0.00",
                    "allow_static_fallback": True,
                }
            },
        )

        self.assertEqual(adjustments[0]["settlement_effect"], "PLUS")
        self.assertEqual(adjustments[0]["amount"], Decimal("500.00"))
        self.assertEqual(payload["withholding_runtime_result"]["base_amount"], "50000.00")
        self.assertEqual(payload["withholding_runtime_result"]["amount"], "500.00")

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

    @patch("payments.services.payment_voucher_service.WithholdingSection.objects.filter")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_ledger_id")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_account_id")
    @patch("payments.services.payment_voucher_service.compute_withholding_preview")
    def test_runtime_withholding_auto_mode_uses_reverse_calculated_payment_base_without_allocations(self, mock_preview, mock_get_account_id, mock_get_ledger_id, mock_filter):
        mock_filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            id=5,
            base_rule=WithholdingBaseRule.PAYMENT_VALUE,
            section_code="194A",
            rate_default=Decimal("1.0000"),
        )
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001
        mock_preview.return_value = SimpleNamespace(rate=Decimal("1.0000"), amount=Decimal("500.00"), reason="auto", reason_code="OK")

        adjustments, payload = PaymentVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            paid_to_id=55,
            voucher_date=None,
            cash_paid_amount=Decimal("49500.00"),
            allocations=[],
            adjustments=[],
            workflow_payload={"withholding": {"enabled": True, "section_id": 5, "mode": "AUTO", "allow_static_fallback": True}},
        )

        self.assertEqual(mock_preview.call_count, 1)
        preview_call = mock_preview.call_args.kwargs
        self.assertEqual(preview_call["taxable_total"], Decimal("50000.00"))
        self.assertEqual(adjustments[0]["amount"], Decimal("500.00"))
        self.assertEqual(payload["withholding_runtime_result"]["base_amount"], "50000.00")

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
        self.assertEqual(payload.get("withholding_runtime_result", {}).get("deduction_status"), "NOT_DEDUCTED")
        self.assertTrue(payload.get("withholding_runtime_result", {}).get("zero_deduction"))
        self.assertFalse(payload.get("withholding_runtime_result", {}).get("user_selected_add_tds"))

    @patch("payments.services.payment_voucher_service.WithholdingSection.objects.filter")
    def test_runtime_withholding_rejects_invoice_based_section_even_in_manual_mode(self, mock_filter):
        mock_filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            id=10,
            base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
            section_code="194C",
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
        self.assertEqual(payload.get("withholding_runtime_result", {}).get("section_code"), "194C")
        self.assertEqual(payload.get("withholding_runtime_result", {}).get("deduction_status"), "NOT_DEDUCTED")

    @patch("payments.services.payment_voucher_service.WithholdingSection.objects.filter")
    @patch("payments.services.payment_voucher_service.PaymentVoucherService._resolve_entity_runtime_tds_mapping")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_ledger_id")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_account_id")
    @patch("payments.services.payment_voucher_service.compute_withholding_preview")
    def test_runtime_withholding_snapshot_persists_status_and_section_code(
        self,
        mock_preview,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_resolve_entity,
        mock_filter,
    ):
        mock_resolve_entity.return_value = (None, None)
        mock_filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            id=5,
            base_rule=WithholdingBaseRule.PAYMENT_VALUE,
            section_code="194A",
        )
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001
        mock_preview.return_value = SimpleNamespace(
            rate=Decimal("10.0000"),
            amount=Decimal("10.00"),
            reason="payment-stage tds computed",
            reason_code="OK",
            section=SimpleNamespace(id=5, section_code="194A"),
        )

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

        runtime = payload.get("withholding_runtime_result", {})
        self.assertEqual(len(adjustments), 1)
        self.assertEqual(runtime.get("section_code"), "194A")
        self.assertEqual(runtime.get("deduction_status"), "DEDUCTED")
        self.assertFalse(runtime.get("zero_deduction"))
        self.assertTrue(runtime.get("user_selected_add_tds"))

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


class PaymentVoucherDetailFormMetaAttachmentTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="payment_meta_user",
            email="payment_meta_user@example.com",
            password="pass@12345",
        )

    @patch("payments.views.payment_meta.PaymentVoucherAttachmentSerializer")
    @patch("payments.views.payment_meta.PaymentVoucherHeaderSerializer")
    @patch.object(PaymentVoucherDetailFormMetaAPIView, "enforce_scope")
    @patch.object(PaymentVoucherDetailFormMetaAPIView, "_action_flags")
    @patch.object(PaymentVoucherDetailFormMetaAPIView, "_account_block")
    @patch.object(PaymentVoucherDetailFormMetaAPIView, "_voucher_form_meta")
    @patch.object(PaymentVoucherDetailFormMetaAPIView, "_voucher_queryset")
    def test_detail_meta_includes_attachments_payload(
        self,
        mocked_queryset,
        mocked_form_meta,
        mocked_account_block,
        mocked_action_flags,
        _mocked_enforce_scope,
        mocked_header_serializer,
        mocked_attachment_serializer,
    ):
        header_qs = MagicMock()
        header = MagicMock()
        header.attachments.order_by.return_value = ["attachment-row"]
        header_qs.get.return_value = header
        mocked_queryset.return_value = header_qs
        mocked_form_meta.return_value = {"entity_id": 10, "entityfinid_id": 11, "subentity_id": 12}
        mocked_account_block.side_effect = [{"id": 21}, {"id": 22}]
        mocked_action_flags.return_value = {"can_edit": True}
        mocked_header_serializer.return_value.data = {"id": 99, "navigation": {"previous_id": 1}, "number_navigation": {"next_doc_no": 3}}
        mocked_attachment_serializer.return_value.data = [{"id": 701, "file_name": "payment-proof.pdf"}]

        request = self.factory.get("/api/payments/meta/voucher-detail-form/?entity=10&entityfinid=11&subentity=12&voucher=99")
        force_authenticate(request, user=self.user)

        response = PaymentVoucherDetailFormMetaAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["attachments"], [{"id": 701, "file_name": "payment-proof.pdf"}])
        mocked_attachment_serializer.assert_called_once_with(["attachment-row"], many=True)


class PaymentNumberingSeedCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="payment-seed-user",
            email="payment-seed-user@example.com",
            password="pass@12345",
        )
        self.entity = Entity.objects.create(
            entityname="Payment Seed Entity",
            createdby=self.user,
            GstRegitrationType=GstRegistrationType.objects.create(Name="Regular", Description="Regular"),
        )
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1, 0, 0, 0)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31, 23, 59, 59)),
            createdby=self.user,
        )
        self.root_scope = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Head Office",
            is_head_office=True,
        )
        self.branch_scope = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Branch A",
            branch_type=SubEntity.BranchType.BRANCH,
        )
        self.inactive_scope = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Inactive Branch",
            branch_type=SubEntity.BranchType.BRANCH,
        )
        self.inactive_scope.isactive = False
        self.inactive_scope.save(update_fields=["isactive"])

    def test_seed_payment_numbering_without_subentity_seeds_root_and_active_branches(self):
        call_command(
            "seed_payment_numbering",
            entity=self.entity.id,
            entityfinid=self.entityfin.id,
            verbosity=0,
        )

        doc_type = DocumentType.objects.get(module="payments", doc_key="PAYMENT_VOUCHER")
        self.assertEqual(doc_type.name, "Payment Voucher")
        self.assertEqual(
            DocumentNumberSeries.objects.filter(
                entity_id=self.entity.id,
                entityfinid_id=self.entityfin.id,
                doc_type_id=doc_type.id,
                doc_code="PPV",
                is_active=True,
            ).count(),
            3,
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity_id=self.entity.id,
                entityfinid_id=self.entityfin.id,
                subentity_id=None,
                doc_type_id=doc_type.id,
            ).exists()
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity_id=self.entity.id,
                entityfinid_id=self.entityfin.id,
                subentity_id=self.root_scope.id,
                doc_type_id=doc_type.id,
            ).exists()
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity_id=self.entity.id,
                entityfinid_id=self.entityfin.id,
                subentity_id=self.branch_scope.id,
                doc_type_id=doc_type.id,
            ).exists()
        )
        self.assertFalse(
            DocumentNumberSeries.objects.filter(
                entity_id=self.entity.id,
                entityfinid_id=self.entityfin.id,
                subentity_id=self.inactive_scope.id,
                doc_type_id=doc_type.id,
            ).exists()
        )


class PaymentNumberingRecoveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="payment-recovery-user",
            email="payment-recovery-user@example.com",
            password="pass@12345",
        )
        self.entity = Entity.objects.create(entityname="Payment Recovery Entity", createdby=self.user)
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1, 0, 0, 0)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31, 23, 59, 59)),
            createdby=self.user,
        )
        self.root_scope = SubEntity.objects.create(entity=self.entity, subentityname="Head Office", is_head_office=True)
        self.branch_scope = SubEntity.objects.create(entity=self.entity, subentityname="Branch A", branch_type=SubEntity.BranchType.BRANCH)

    def test_current_doc_no_auto_seeds_missing_branch_scope(self):
        NumberingSeedService.seed_document(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=None,
            module="payments",
            doc_key="PAYMENT_VOUCHER",
            name="Payment Voucher",
            default_code="PPV",
            prefix="PPV",
            start=5,
            padding=4,
        )

        payload = PaymentSettingsService.get_current_doc_no(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.branch_scope.id,
            doc_key="PAYMENT_VOUCHER",
            doc_code="PPV",
        )

        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["current_number"], 1)
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.branch_scope,
                doc_code="PPV",
            ).exists()
        )
