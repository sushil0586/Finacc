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
from receipts.models import ReceiptVoucherHeader
from receipts.serializers.receipt_voucher import ReceiptVoucherHeaderSerializer
from receipts.services.receipt_voucher_service import ReceiptVoucherService
from receipts.services.receipt_settings_service import ReceiptSettingsService
from receipts.views.receipt_exports import ReceiptVoucherPDFAPIView
from receipts.views.receipt_meta import ReceiptVoucherDetailFormMetaAPIView
from receipts.views.receipt_voucher import (
    ReceiptVoucherApprovalAPIView,
    ReceiptVoucherCancelAPIView,
    ReceiptVoucherLookupAPIView,
    ReceiptVoucherListCreateAPIView,
    ReceiptVoucherPostAPIView,
    _duplicate_reference_warnings,
)
from receipts.views.receipt_settings import ReceiptSettingsAPIView
from posting.adapters.receipt_voucher import ReceiptVoucherPostingAdapter
from withholding.models import WithholdingBaseRule

User = get_user_model()


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
            received_in=SimpleNamespace(accountname="Cash In Hand", ledger_id=10),
            received_from=SimpleNamespace(accountname="Customer-A", ledger_id=20),
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
        self.assertIn("Customer Customer-A", jl[1].description)
        self.assertIn("Into Cash In Hand", jl[0].description)


class ReceiptVoucherReferenceWarningTests(SimpleTestCase):
    def _header(self):
        return SimpleNamespace(
            id=1,
            voucher_code="RV-1",
            cash_received_amount=Decimal("100.00"),
            received_in_id=10,
            received_from_id=20,
            received_in=SimpleNamespace(accountname="Cash In Hand", ledger_id=10),
            received_from=SimpleNamespace(accountname="Customer-A", ledger_id=20),
        )

    @patch("receipts.views.receipt_voucher.ReceiptVoucherHeader.objects")
    def test_duplicate_reference_warning_includes_existing_voucher_code(self, mocked_objects):
        mocked_objects.filter.return_value.exclude.return_value.order_by.return_value.filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            voucher_code="RV-2002",
            doc_code="RV",
            doc_no=2002,
        )
        voucher = SimpleNamespace(
            id=99,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=5,
            received_from_id=77,
            reference_number="UTR-001",
        )

        warnings = _duplicate_reference_warnings(voucher)

        self.assertEqual(warnings, [
            "Reference already appears on voucher RV-2002. Please double-check before proceeding."
        ])

    def test_receipt_posting_error_explains_bank_charges_double_counting(self):
        header = self._header()
        adjustments = [
            SimpleNamespace(
                id=1,
                amount=Decimal("200.00"),
                ledger_account_id=101,
                settlement_effect="MINUS",
                adj_type="BANK_CHARGES",
            )
        ]
        with self.assertRaisesMessage(
            ValueError,
            "enter that amount only in Cash Received and remove the BANK_CHARGES adjustment row",
        ):
            ReceiptVoucherPostingAdapter._build_journal_lines(
                header=SimpleNamespace(**{**header.__dict__, "cash_received_amount": Decimal("200.00")}),
                adjustments=adjustments,
                reverse=False,
            )


class ReceiptVoucherServiceTests(SimpleTestCase):
    databases = {"default"}

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_submit_voucher_returns_already_submitted_for_repeat_submit(self, mock_header_objects):
        header = SimpleNamespace(
            status=ReceiptVoucherHeader.Status.DRAFT,
            workflow_payload={"_approval_state": {"status": "SUBMITTED", "submitted_by": 7}},
        )
        mock_header_objects.select_for_update.return_value.get.return_value = header

        result = ReceiptVoucherService.submit_voucher.__wrapped__(voucher_id=11, submitted_by_id=7, remarks="Retry")

        self.assertEqual(result.message, "Already submitted.")

    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_approve_voucher_returns_already_approved_for_repeat_approve(self, mock_header_objects, mock_get_policy):
        header = SimpleNamespace(
            entity_id=1,
            subentity_id=None,
            status=ReceiptVoucherHeader.Status.CONFIRMED,
            workflow_payload={"_approval_state": {"status": "APPROVED", "submitted_by": 7, "approved_by": 8}},
        )
        mock_header_objects.select_for_update.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={})

        result = ReceiptVoucherService.approve_voucher.__wrapped__(voucher_id=11, approved_by_id=8, remarks="Retry")

        self.assertEqual(result.message, "Already approved.")

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_reject_voucher_returns_already_rejected_for_repeat_reject(self, mock_header_objects):
        header = SimpleNamespace(
            status=ReceiptVoucherHeader.Status.CONFIRMED,
            workflow_payload={"_approval_state": {"status": "REJECTED", "rejected_by": 8}},
        )
        mock_header_objects.select_for_update.return_value.get.return_value = header

        result = ReceiptVoucherService.reject_voucher.__wrapped__(voucher_id=11, rejected_by_id=8, remarks="Retry")

        self.assertEqual(result.message, "Already rejected.")

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._resolve_financial_year")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
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
            ReceiptVoucherService.post_voucher.__wrapped__(voucher_id=51, posted_by_id=9)

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._resolve_financial_year")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
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
            ReceiptVoucherService.unpost_voucher.__wrapped__(voucher_id=52, unposted_by_id=9)

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._resolve_financial_year")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
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
            ReceiptVoucherService.cancel_voucher.__wrapped__(voucher_id=53, cancelled_by_id=9)

    def test_validate_positive_receipt_support_raises_guidance_for_bank_charges_duplicate(self):
        with self.assertRaisesMessage(
            ValueError,
            "enter that amount only in Cash Received and remove the BANK_CHARGES adjustment row",
        ):
            ReceiptVoucherService._validate_positive_receipt_support(
                cash_received_amount=Decimal("200.00"),
                adjustments=[
                    {
                        "adj_type": "BANK_CHARGES",
                        "amount": Decimal("200.00"),
                        "settlement_effect": "MINUS",
                    }
                ],
                effective_amount=Decimal("0.00"),
            )

    @patch("receipts.services.receipt_voucher_service.FinancialAccount.objects.filter")
    @patch("receipts.services.receipt_voucher_service.SalesAdvanceAdjustment.objects")
    def test_sync_gstr1_table11_rows_creates_advance_receipt_row_from_receipt_gst_fields(
        self,
        mock_manager,
        mock_account_exists,
    ):
        mock_manager.filter.side_effect = [[], []]
        mock_account_exists.return_value.exists.return_value = True

        header = SimpleNamespace(
            entity_id=10,
            entityfinid_id=20,
            subentity_id=None,
            voucher_date="2026-04-20",
            voucher_code="RV-ADV-001",
            doc_code="RV",
            doc_no=1,
            receipt_type=ReceiptVoucherHeader.ReceiptType.ADVANCE,
            received_from_id=171,
            received_from=SimpleNamespace(accountname="Customer-A", legalname=""),
            customer_gstin="27ABCDE1234F1Z5",
            place_of_supply_state=SimpleNamespace(gst_state_code="27"),
            advance_taxable_value=Decimal("500.00"),
            advance_cgst=Decimal("45.00"),
            advance_sgst=Decimal("45.00"),
            advance_igst=Decimal("0.00"),
            advance_cess=Decimal("0.00"),
        )

        ReceiptVoucherService._sync_gstr1_table11_rows(header=header, live_advance_rows=[], track_amendments=True)

        mock_manager.create.assert_called_once()
        payload = mock_manager.create.call_args.kwargs
        self.assertEqual(payload["voucher_number"], "RV-ADV-001")
        self.assertEqual(payload["entry_type"], "ADVANCE_RECEIPT")
        self.assertEqual(payload["customer_id"], 171)
        self.assertEqual(payload["taxable_value"], Decimal("500.00"))
        self.assertEqual(payload["cgst_amount"], Decimal("45.00"))
        self.assertEqual(payload["sgst_amount"], Decimal("45.00"))
        self.assertEqual(payload["igst_amount"], Decimal("0.00"))

    @patch("receipts.services.receipt_voucher_service.CustomerBillOpenItem.objects.filter")
    @patch("receipts.services.receipt_voucher_service.FinancialAccount.objects.filter")
    @patch("receipts.services.receipt_voucher_service.SalesAdvanceAdjustment.objects")
    def test_sync_gstr1_table11_rows_creates_advance_adjustment_row_linked_to_invoice(
        self,
        mock_manager,
        mock_account_exists,
        mock_open_item_filter,
    ):
        mock_manager.filter.side_effect = [[], []]
        mock_account_exists.return_value.exists.return_value = True
        mock_open_item_filter.return_value.only.return_value.first.return_value = SimpleNamespace(header_id=77)

        source_receipt = SimpleNamespace(
            advance_taxable_value=Decimal("100.00"),
            advance_cgst=Decimal("9.00"),
            advance_sgst=Decimal("9.00"),
            advance_igst=Decimal("0.00"),
            advance_cess=Decimal("0.00"),
        )
        advance_balance = SimpleNamespace(
            receipt_voucher=source_receipt,
            original_amount=Decimal("118.00"),
        )
        live_advance_row = SimpleNamespace(
            adjusted_amount=Decimal("59.00"),
            open_item_id=55,
            advance_balance=advance_balance,
        )
        header = SimpleNamespace(
            entity_id=10,
            entityfinid_id=20,
            subentity_id=None,
            voucher_date="2026-04-25",
            voucher_code="RV-ADJ-001",
            doc_code="RV",
            doc_no=2,
            receipt_type=ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE,
            received_from_id=171,
            received_from=SimpleNamespace(accountname="Customer-A", legalname=""),
            customer_gstin="27ABCDE1234F1Z5",
            place_of_supply_state=SimpleNamespace(gst_state_code="27"),
            advance_taxable_value=Decimal("0.00"),
            advance_cgst=Decimal("0.00"),
            advance_sgst=Decimal("0.00"),
            advance_igst=Decimal("0.00"),
            advance_cess=Decimal("0.00"),
        )

        ReceiptVoucherService._sync_gstr1_table11_rows(
            header=header,
            live_advance_rows=[live_advance_row],
            track_amendments=True,
        )

        mock_manager.create.assert_called_once()
        payload = mock_manager.create.call_args.kwargs
        self.assertEqual(payload["entry_type"], "ADVANCE_ADJUSTMENT")
        self.assertEqual(payload["linked_invoice_id"], 77)
        self.assertEqual(payload["voucher_number"], "RV-ADJ-001-ADJ-1")
        self.assertEqual(payload["taxable_value"], Decimal("50.00"))
        self.assertEqual(payload["cgst_amount"], Decimal("4.50"))
        self.assertEqual(payload["sgst_amount"], Decimal("4.50"))
        self.assertEqual(payload["igst_amount"], Decimal("0.00"))

    @patch("receipts.services.receipt_voucher_service.logger")
    @patch("receipts.services.receipt_voucher_service.logger")
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
        _mock_logger_one,
        _mock_logger_two,
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

        mock_header_objects.select_related.return_value.prefetch_related.return_value.select_for_update.return_value.get.return_value = header
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
            voucher_date=date(2026, 5, 28),
            ap_settlement_id=99,
            created_by_id=5,
            voucher_code="RV-12",
            workflow_payload={"_approval_state": {"status": "APPROVED", "approved_by": 8, "approved_at": "2026-05-28T10:00:00+0530"}},
            approved_at="2026-05-28T10:00:00+0530",
            approved_by_id=8,
            adjustments=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.select_for_update.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={"unpost_target_status": "confirmed"})

        res = ReceiptVoucherService.unpost_voucher.__wrapped__(voucher_id=12, unposted_by_id=9)
        self.assertEqual(res.message, "Unposted with reversal entry. Voucher reopened for correction and reposting.")
        self.assertEqual(header.status, ReceiptVoucherHeader.Status.CONFIRMED)
        self.assertIsNone(header.ap_settlement_id)
        self.assertEqual(header.workflow_payload["_approval_state"]["status"], "DRAFT")
        self.assertIsNone(header.approved_at)
        self.assertIsNone(header.approved_by_id)
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

    @patch("receipts.services.receipt_voucher_service.logger")
    @patch("receipts.services.receipt_voucher_service.logger")
    @patch("receipts.services.receipt_voucher_service.logger")
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
        mock_logger,
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

    @patch("receipts.services.receipt_voucher_service.logger")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._sync_runtime_tcs_computation")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._fresh_allocation_rows")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherPostingAdapter.post_receipt_voucher")
    @patch("receipts.services.receipt_voucher_service.SalesArService.post_settlement")
    @patch("receipts.services.receipt_voucher_service.SalesArService.create_settlement")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_post_voucher_reuses_existing_ar_settlement_ids_on_retry(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_create_settlement,
        mock_post_settlement,
        mock_post_adapter,
        mock_fresh_allocs,
        _mock_sync_tcs,
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
            status=ReceiptVoucherHeader.Status.CONFIRMED,
            receipt_type=ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE,
            voucher_date="2026-03-07",
            voucher_code="RV-33",
            reference_number="UTR-2",
            narration="retry",
            received_from_id=99,
            cash_received_amount=Decimal("66000.00"),
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
            "sync_ar_settlement_on_post": "on",
            "allocation_amount_match_rule": "hard",
            "require_confirm_before_post": "on",
            "receipt_maker_checker": "off",
            "over_settlement_rule": "block",
            "allocation_policy": "manual",
            "sync_advance_balance_on_post": "off",
        })
        mock_post_settlement.side_effect = [
            SimpleNamespace(settlement=SimpleNamespace(id=201)),
            SimpleNamespace(settlement=SimpleNamespace(id=202)),
        ]

        with patch.object(ReceiptVoucherService, "_validate_advance_adjustments", return_value=None), \
             patch.object(ReceiptVoucherService, "_validate_allocations", return_value=[]):
            res = ReceiptVoucherService.post_voucher.__wrapped__(voucher_id=33, posted_by_id=9)

        self.assertIn("Posted with warnings:", res.message)
        self.assertIn("Receipt settlement resumed from existing linked settlement", res.message)
        self.assertIn("Advance adjustment settlement resumed from existing linked settlement", res.message)
        mock_create_settlement.assert_not_called()
        self.assertEqual(mock_post_settlement.call_args_list[0].kwargs["settlement_id"], 201)
        self.assertEqual(mock_post_settlement.call_args_list[1].kwargs["settlement_id"], 202)
        self.assertEqual(mock_logger.info.call_count, 2)
        mock_post_adapter.assert_called_once()

    @patch("receipts.services.receipt_voucher_service.CustomerAdvanceBalance.objects")
    @patch("receipts.services.receipt_voucher_service.logger")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._sync_runtime_tcs_computation")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherPostingAdapter.post_receipt_voucher")
    @patch("receipts.services.receipt_voucher_service.ReceiptSettingsService.get_policy")
    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherHeader.objects")
    def test_post_voucher_reuses_existing_advance_balance_on_retry(
        self,
        mock_header_objects,
        mock_get_policy,
        mock_post_adapter,
        _mock_sync_tcs,
        mock_logger,
        mocked_adv_objects,
    ):
        existing_advance = SimpleNamespace(id=301)
        header = SimpleNamespace(
            id=34,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            status=ReceiptVoucherHeader.Status.CONFIRMED,
            receipt_type=ReceiptVoucherHeader.ReceiptType.ADVANCE,
            voucher_date="2026-03-08",
            voucher_code="RV-34",
            reference_number="UTR-3",
            narration="advance retry",
            received_from_id=99,
            cash_received_amount=Decimal("5000.00"),
            total_adjustment_amount=Decimal("0.00"),
            settlement_effective_amount=Decimal("5000.00"),
            settlement_effective_amount_base_currency=Decimal("5000.00"),
            exchange_rate=Decimal("1.000000"),
            created_by_id=5,
            ap_settlement_id=None,
            approved_at=None,
            approved_by_id=None,
            workflow_payload={},
            customer_advance_balance=None,
            adjustments=SimpleNamespace(all=lambda: [], values=lambda *args, **kwargs: []),
            allocations=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: []),
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={
            "require_allocation_on_post": "hard",
            "require_confirm_before_post": "on",
            "receipt_maker_checker": "off",
            "sync_ar_settlement_on_post": "on",
            "sync_advance_balance_on_post": "on",
            "residual_to_advance_balance": "on",
        })
        mocked_adv_objects.filter.return_value.first.return_value = existing_advance

        with patch.object(ReceiptVoucherService, "_validate_allocations", return_value=[]), \
             patch.object(ReceiptVoucherService, "_validate_advance_adjustments", return_value=None), \
             patch("receipts.services.receipt_voucher_service.SalesArService.create_advance_balance") as mock_create_adv:
            res = ReceiptVoucherService.post_voucher.__wrapped__(voucher_id=34, posted_by_id=9)

        self.assertIn("Posted with warnings:", res.message)
        self.assertIn("Receipt advance balance resumed from existing linked balance", res.message)
        mock_create_adv.assert_not_called()
        self.assertIs(header.customer_advance_balance, existing_advance)
        mock_logger.info.assert_called_once()
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
            workflow_payload={"_approval_state": {"status": "SUBMITTED", "submitted_by": 7}},
            approved_at="2026-05-28T10:00:00+0530",
            approved_by_id=8,
            adjustments=SimpleNamespace(all=lambda: []),
            advance_adjustments=SimpleNamespace(all=lambda: [advance_row]),
            customer_advance_balance=advance_balance,
            save=MagicMock(),
        )
        mock_header_objects.select_related.return_value.prefetch_related.return_value.get.return_value = header
        mock_get_policy.return_value = SimpleNamespace(controls={"unpost_target_status": "draft"})

        res = ReceiptVoucherService.unpost_voucher.__wrapped__(voucher_id=41, unposted_by_id=9)

        self.assertEqual(res.message, "Unposted with reversal entry. Voucher reopened for correction and reposting.")
        self.assertEqual(header.status, ReceiptVoucherHeader.Status.DRAFT)
        self.assertIsNone(header.ap_settlement_id)
        self.assertIsNone(advance_row.ap_settlement_id)
        self.assertEqual(header.workflow_payload["_approval_state"]["status"], "DRAFT")
        self.assertIsNone(header.approved_at)
        self.assertIsNone(header.approved_by_id)
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

    @patch("receipts.views.receipt_voucher.ReceiptVoucherLookupAPIView.get_serializer")
    @patch("receipts.views.receipt_voucher._require_receipt_permission")
    @patch("receipts.views.receipt_voucher.ReceiptVoucherHeader.objects")
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

        request = self._request("/api/receipts/receipt-vouchers/lookup/?entity=1&entityfinid=2&limit=500")

        response = ReceiptVoucherLookupAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_count"], 320)
        self.assertEqual(response.data["returned_count"], 2)
        self.assertEqual(response.data["limit"], 250)
        self.assertTrue(response.data["has_more"])

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

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch("receipts.views.receipt_voucher.ReceiptVoucherHeader.objects")
    def test_approval_view_rejects_oversized_remarks(self, mocked_header_objects, mocked_error_log):
        mocked_header_objects.only.return_value.get.return_value = SimpleNamespace(id=9, entity_id=1)
        request = self._request(
            "/api/receipts/receipt-vouchers/9/approval/",
            {"action": "submit", "remarks": "R" * 256},
        )

        response = ReceiptVoucherApprovalAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 400)
        self.assertIn("remarks", response.data)
        mocked_error_log.assert_called_once()

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch("receipts.views.receipt_voucher._require_receipt_permission")
    @patch("receipts.views.receipt_voucher.ReceiptVoucherHeader.objects")
    def test_cancel_view_rejects_oversized_reason(
        self,
        mocked_header_objects,
        _mocked_require_permission,
        mocked_error_log,
    ):
        mocked_header_objects.only.return_value.get.return_value = SimpleNamespace(id=9, entity_id=1)
        request = self._request(
            "/api/receipts/receipt-vouchers/9/cancel/",
            {"reason": "C" * 256},
        )

        response = ReceiptVoucherCancelAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 400)
        self.assertIn("reason", response.data)
        mocked_error_log.assert_called_once()

    @patch("receipts.views.receipt_voucher._require_receipt_permission")
    @patch("receipts.views.receipt_voucher.ReceiptVoucherService.post_voucher")
    @patch("receipts.views.receipt_voucher.ReceiptVoucherHeaderSerializer")
    @patch.object(ReceiptVoucherPostAPIView, "_get_header")
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
            message="Posted with warnings: Round-off line inserted | Static fallback used",
            header=SimpleNamespace(id=9),
        )
        request = self._request("/api/receipts/receipt-vouchers/9/post/", {})

        response = ReceiptVoucherPostAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["notice"], "Posting completed with policy warnings.")
        self.assertEqual(response.data["warnings"], [
            "Round-off line inserted",
            "Static fallback used",
        ])

    @patch("receipts.views.receipt_voucher.ReceiptVoucherService.post_voucher")
    @patch("receipts.views.receipt_voucher.EffectivePermissionService.permission_codes_for_user", return_value=set())
    @patch("receipts.views.receipt_voucher.EffectivePermissionService.entity_for_user", return_value=SimpleNamespace(id=1))
    @patch.object(ReceiptVoucherPostAPIView, "_get_header")
    def test_post_view_requires_backend_permission_before_service_call(
        self,
        mocked_get_header,
        _mocked_entity,
        _mocked_codes,
        mocked_post_voucher,
    ):
        mocked_get_header.return_value = SimpleNamespace(id=9, entity_id=1)
        request = self._request("/api/receipts/receipt-vouchers/9/post/?entity=1&entityfinid=2", {})

        response = ReceiptVoucherPostAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 403)
        self.assertIn("Missing permission", str(response.data))
        mocked_post_voucher.assert_not_called()

    @patch("receipts.views.receipt_voucher.ReceiptVoucherService.post_voucher")
    @patch.object(ReceiptVoucherPostAPIView, "_get_header")
    def test_post_view_rejects_out_of_scope_header_before_service_call(
        self,
        mocked_get_header,
        mocked_post_voucher,
    ):
        mocked_get_header.side_effect = Http404()
        request = self._request("/api/receipts/receipt-vouchers/9/post/?entity=1&entityfinid=2&subentity=99", {})

        response = ReceiptVoucherPostAPIView.as_view()(request, pk=9)

        self.assertEqual(response.status_code, 404)
        mocked_post_voucher.assert_not_called()



class ReceiptSettingsValidationTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=7)

    def _request(self, path: str, data=None):
        request = self.factory.patch(path, data or {}, format="json")
        force_authenticate(request, user=self.user)
        return request

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch.object(ReceiptSettingsAPIView, "_payload", return_value={"ok": True})
    @patch.object(ReceiptSettingsAPIView, "_scope", return_value=(1, None, 2))
    @patch("receipts.views.receipt_settings.ReceiptSettingsService.upsert_settings")
    def test_settings_patch_rejects_oversized_lock_period_reason(
        self,
        mocked_upsert,
        _mocked_scope,
        _mocked_payload,
        mocked_error_log,
    ):
        mocked_upsert.return_value = SimpleNamespace(default_doc_code_receipt="RV")
        request = self._request(
            "/api/receipts/settings/?entity=1&entityfinid=2",
            {"lock_periods": [{"lock_date": "2026-04-01", "reason": "R" * 201}]},
        )

        response = ReceiptSettingsAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("lock_periods", response.data)
        mocked_error_log.assert_called_once()

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch.object(ReceiptSettingsAPIView, "_payload", return_value={"ok": True})
    @patch.object(ReceiptSettingsAPIView, "_scope", return_value=(1, None, 2))
    @patch.object(ReceiptSettingsAPIView, "_valid_override_keys", return_value={"receipt_modes": {"NEFT"}})
    @patch("receipts.views.receipt_settings.ReceiptChoiceService.compile_choices", return_value={"receipt_modes": [{"key": "NEFT"}]})
    @patch("receipts.views.receipt_settings.ReceiptSettingsService.upsert_settings")
    def test_settings_patch_rejects_oversized_choice_override_label(
        self,
        mocked_upsert,
        _mocked_compile_choices,
        _mocked_valid_override_keys,
        _mocked_scope,
        _mocked_payload,
        mocked_error_log,
    ):
        mocked_upsert.return_value = SimpleNamespace(default_doc_code_receipt="RV")
        request = self._request(
            "/api/receipts/settings/?entity=1&entityfinid=2",
            {
                "choice_overrides": [
                    {
                        "choice_group": "receipt_modes",
                        "choice_key": "NEFT",
                        "is_enabled": True,
                        "override_label": "L" * 201,
                    }
                ]
            },
        )

        response = ReceiptSettingsAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("choice_overrides", response.data)
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
        self.assertEqual(adjustments[0]["settlement_effect"], "MINUS")
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
        self.assertEqual(payload.get("withholding_runtime_result", {}).get("collection_status"), "NOT_COLLECTED")
        self.assertTrue(payload.get("withholding_runtime_result", {}).get("zero_collection"))
        self.assertFalse(payload.get("withholding_runtime_result", {}).get("user_selected_add_tcs"))

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._resolve_entity_runtime_tcs_mapping")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_ledger_id")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_account_id")
    @patch("receipts.services.receipt_voucher_service.compute_withholding_preview")
    def test_runtime_withholding_reverse_calculates_base_for_gross_advance_receipt(
        self,
        mock_preview,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_resolve_entity,
    ):
        mock_resolve_entity.return_value = (None, None)
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001
        mock_preview.return_value = SimpleNamespace(
            rate=Decimal("1.0000"),
            amount=Decimal("10.00"),
            reason="advance receipt tcs computed",
            reason_code="OK",
            section=SimpleNamespace(id=5, section_code="206C1H"),
        )

        adjustments, payload = ReceiptVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            received_from_id=55,
            voucher_date=None,
            cash_received_amount=Decimal("1010.00"),
            allocations=[],
            adjustments=[],
            workflow_payload={"withholding": {"enabled": True, "section_id": 5, "mode": "AUTO", "allow_static_fallback": True}},
        )

        runtime = payload.get("withholding_runtime_result", {})
        self.assertEqual(len(adjustments), 1)
        self.assertEqual(adjustments[0]["adj_type"], "TCS")
        self.assertEqual(adjustments[0]["amount"], Decimal("10.00"))
        self.assertEqual(runtime.get("base_amount"), "1000.00")
        self.assertEqual(runtime.get("collection_status"), "COLLECTED")

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._resolve_entity_runtime_tcs_mapping")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_ledger_id")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_account_id")
    @patch("receipts.services.receipt_voucher_service.WithholdingSection.objects.filter")
    def test_runtime_withholding_manual_mode_reverse_calculates_gross_advance_receipt(
        self,
        mock_filter,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_resolve_entity,
    ):
        mock_filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            id=5,
            base_rule=WithholdingBaseRule.RECEIPT_VALUE,
            section_code="206C(1)",
        )
        mock_resolve_entity.return_value = (None, None)
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001

        adjustments, payload = ReceiptVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            received_from_id=55,
            voucher_date=None,
            cash_received_amount=Decimal("50500.00"),
            allocations=[],
            adjustments=[],
            workflow_payload={"withholding": {"enabled": True, "section_id": 5, "mode": "MANUAL", "manual_rate": "1.0000", "allow_static_fallback": True}},
        )

        runtime = payload.get("withholding_runtime_result", {})
        self.assertEqual(len(adjustments), 1)
        self.assertEqual(adjustments[0]["adj_type"], "TCS")
        self.assertEqual(adjustments[0]["amount"], Decimal("500.00"))
        self.assertEqual(runtime.get("base_amount"), "50000.00")
        self.assertEqual(runtime.get("amount"), "500.00")
        self.assertEqual(runtime.get("collection_status"), "COLLECTED")

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._resolve_entity_runtime_tcs_mapping")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_ledger_id")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_account_id")
    @patch("receipts.services.receipt_voucher_service.compute_withholding_preview")
    def test_runtime_withholding_uses_partial_receipt_allocation_base(
        self,
        mock_preview,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_resolve_entity,
    ):
        mock_resolve_entity.return_value = (None, None)
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001
        mock_preview.return_value = SimpleNamespace(
            rate=Decimal("1.0000"),
            amount=Decimal("4.00"),
            reason="partial receipt tcs computed",
            reason_code="OK",
            section=SimpleNamespace(id=5, section_code="206C1H"),
        )

        adjustments, payload = ReceiptVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            received_from_id=55,
            voucher_date=None,
            cash_received_amount=Decimal("40.00"),
            allocations=[{"open_item": 1, "settled_amount": Decimal("40.00")}],
            adjustments=[],
            workflow_payload={"withholding": {"enabled": True, "section_id": 5, "mode": "AUTO", "allow_static_fallback": True}},
        )

        runtime = payload.get("withholding_runtime_result", {})
        self.assertEqual(len(adjustments), 1)
        self.assertEqual(adjustments[0]["amount"], Decimal("4.00"))
        self.assertEqual(runtime.get("base_amount"), "40.00")
        self.assertEqual(runtime.get("collection_status"), "COLLECTED")

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._resolve_entity_runtime_tcs_mapping")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_ledger_id")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_account_id")
    @patch("receipts.services.receipt_voucher_service.compute_withholding_preview")
    def test_runtime_withholding_uses_multi_invoice_receipt_allocation_total(
        self,
        mock_preview,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_resolve_entity,
    ):
        mock_resolve_entity.return_value = (None, None)
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001
        mock_preview.return_value = SimpleNamespace(
            rate=Decimal("1.0000"),
            amount=Decimal("10.00"),
            reason="multi invoice receipt tcs computed",
            reason_code="OK",
            section=SimpleNamespace(id=5, section_code="206C1H"),
        )

        adjustments, payload = ReceiptVoucherService._apply_runtime_withholding_to_adjustments(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            received_from_id=55,
            voucher_date=None,
            cash_received_amount=Decimal("100.00"),
            allocations=[
                {"open_item": 1, "settled_amount": Decimal("60.00")},
                {"open_item": 2, "settled_amount": Decimal("40.00")},
            ],
            adjustments=[],
            workflow_payload={"withholding": {"enabled": True, "section_id": 5, "mode": "AUTO", "allow_static_fallback": True}},
        )

        runtime = payload.get("withholding_runtime_result", {})
        self.assertEqual(len(adjustments), 1)
        self.assertEqual(adjustments[0]["amount"], Decimal("10.00"))
        self.assertEqual(runtime.get("base_amount"), "100.00")
        self.assertEqual(runtime.get("collection_status"), "COLLECTED")

    @patch("receipts.services.receipt_voucher_service.ReceiptVoucherService._resolve_entity_runtime_tcs_mapping")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_ledger_id")
    @patch("receipts.services.receipt_voucher_service.StaticAccountService.get_account_id")
    @patch("receipts.services.receipt_voucher_service.compute_withholding_preview")
    def test_runtime_withholding_snapshot_persists_status_and_section_code(
        self,
        mock_preview,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_resolve_entity,
    ):
        mock_resolve_entity.return_value = (None, None)
        mock_get_account_id.return_value = 9001
        mock_get_ledger_id.return_value = 3001
        mock_preview.return_value = SimpleNamespace(
            rate=Decimal("1.0000"),
            amount=Decimal("10.00"),
            reason="receipt-stage tcs computed",
            reason_code="OK",
            section=SimpleNamespace(id=5, section_code="206C1H"),
        )

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

        runtime = payload.get("withholding_runtime_result", {})
        self.assertEqual(len(adjustments), 1)
        self.assertEqual(runtime.get("section_code"), "206C1H")
        self.assertEqual(runtime.get("collection_status"), "COLLECTED")
        self.assertFalse(runtime.get("zero_collection"))
        self.assertTrue(runtime.get("user_selected_add_tcs"))

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


class ReceiptVoucherDetailFormMetaAttachmentTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="receipt_meta_user",
            email="receipt_meta_user@example.com",
            password="pass@12345",
        )

    @patch("receipts.views.receipt_meta.ReceiptVoucherAttachmentSerializer")
    @patch("receipts.views.receipt_meta.ReceiptVoucherHeaderSerializer")
    @patch.object(ReceiptVoucherDetailFormMetaAPIView, "enforce_scope")
    @patch.object(ReceiptVoucherDetailFormMetaAPIView, "_action_flags")
    @patch.object(ReceiptVoucherDetailFormMetaAPIView, "_account_block")
    @patch.object(ReceiptVoucherDetailFormMetaAPIView, "_voucher_form_meta")
    @patch.object(ReceiptVoucherDetailFormMetaAPIView, "_voucher_queryset")
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
        header_qs.filter.return_value.first.return_value = header
        mocked_queryset.return_value = header_qs
        mocked_form_meta.return_value = {"entity_id": 10, "entityfinid_id": 11, "subentity_id": 12}
        mocked_account_block.side_effect = [{"id": 21}, {"id": 22}]
        mocked_action_flags.return_value = {"can_edit": True}
        mocked_header_serializer.return_value.data = {"id": 99, "navigation": {"previous_id": 1}, "number_navigation": {"next_doc_no": 3}}
        mocked_attachment_serializer.return_value.data = [{"id": 801, "file_name": "receipt-proof.pdf"}]

        request = self.factory.get("/api/receipts/meta/voucher-detail-form/?entity=10&entityfinid=11&subentity=12&voucher=99")
        force_authenticate(request, user=self.user)

        response = ReceiptVoucherDetailFormMetaAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["attachments"], [{"id": 801, "file_name": "receipt-proof.pdf"}])
        mocked_attachment_serializer.assert_called_once_with(["attachment-row"], many=True)


class ReceiptNumberingSeedCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="receipt-seed-user",
            email="receipt-seed-user@example.com",
            password="pass@12345",
        )
        self.entity = Entity.objects.create(
            entityname="Receipt Seed Entity",
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

    def test_seed_receipt_numbering_without_subentity_seeds_root_and_active_branches(self):
        call_command(
            "seed_receipt_numbering",
            entity=self.entity.id,
            entityfinid=self.entityfin.id,
            verbosity=0,
        )

        doc_type = DocumentType.objects.get(module="receipts", doc_key="RECEIPT_VOUCHER")
        self.assertEqual(doc_type.name, "Receipt Voucher")
        self.assertEqual(
            DocumentNumberSeries.objects.filter(
                entity_id=self.entity.id,
                entityfinid_id=self.entityfin.id,
                doc_type_id=doc_type.id,
                doc_code="RV",
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


class ReceiptNumberingRecoveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="receipt-recovery-user",
            email="receipt-recovery-user@example.com",
            password="pass@12345",
        )
        self.entity = Entity.objects.create(entityname="Receipt Recovery Entity", createdby=self.user)
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
            module="receipts",
            doc_key="RECEIPT_VOUCHER",
            name="Receipt Voucher",
            default_code="RV",
            prefix="RV",
            start=5,
            padding=4,
        )

        payload = ReceiptSettingsService.get_current_doc_no(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.branch_scope.id,
            doc_key="RECEIPT_VOUCHER",
            doc_code="RV",
        )

        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["current_number"], 1)
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.branch_scope,
                doc_code="RV",
            ).exists()
        )
