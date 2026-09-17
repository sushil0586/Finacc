from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from bank_reco.models import BankReconciliationMatch, BankReconciliationRun, BankStatementImport, BankStatementLine
from bank_reco.services.matching import confirm_manual_match, unmatch
from entity.models import Entity, EntityFinancialYear, SubEntity
from entity.models import EntityBankAccountV2
from financial.models import AccountBankDetails, Ledger, account
from payments.models import PaymentMode, PaymentVoucherHeader
from posting.models import Entry, EntryStatus, JournalLine, PostingBatch, TxnType
from purchase.models.purchase_ap import VendorBillOpenItem, VendorSettlement
from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.services.purchase_settings_service import PurchaseSettingsService
from vouchers.models import VoucherHeader, VoucherLine

from .models import TreasuryCashMovement, TreasuryChequeBook, TreasuryChequeLeaf, TreasuryPaymentBatch, TreasuryPaymentBatchLine, TreasuryPaymentInstrument
from .serializers import TreasuryVendorPayableCandidateSerializer
from .services import TreasuryPaymentBatchService


class TreasuryPaymentBatchServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="treasury-tests@example.com",
            email="treasury-tests@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Treasury Entity", createdby=self.user)
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            year_code="FY2026-27",
            desc="FY 2026-27",
            finstartyear=timezone.datetime(2026, 4, 1, tzinfo=timezone.get_current_timezone()),
            finendyear=timezone.datetime(2027, 3, 31, tzinfo=timezone.get_current_timezone()),
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Head Office", is_head_office=True)
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"settlement_mode": "basic", "allocation_policy": "manual"}},
        )
        self.vendor_ledger = Ledger.objects.create(entity=self.entity, ledger_code=9001, name="Vendor One", is_party=True, createdby=self.user)
        self.bank_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1001, name="Main Bank", createdby=self.user)
        self.cash_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1002, name="Cash In Hand", createdby=self.user)
        self.transfer_bank_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1003, name="Reserve Bank", createdby=self.user)
        self.vendor = account.objects.create(entity=self.entity, ledger=self.vendor_ledger, accountname="Vendor One", createdby=self.user)
        self.bank_account = account.objects.create(entity=self.entity, ledger=self.bank_ledger, accountname="Main Bank", createdby=self.user)
        self.cash_account = account.objects.create(entity=self.entity, ledger=self.cash_ledger, accountname="Cash In Hand", createdby=self.user)
        self.reserve_bank_account = account.objects.create(entity=self.entity, ledger=self.transfer_bank_ledger, accountname="Reserve Bank", createdby=self.user)
        self.payment_mode = PaymentMode.objects.create(
            paymentmode="NEFT",
            paymentmodecode="NEFT",
            iscash=False,
            createdby=self.user,
        )
        self.cheque_payment_mode = PaymentMode.objects.create(
            paymentmode="Cheque",
            paymentmodecode="CHEQUE",
            iscash=False,
            createdby=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        AccountBankDetails.objects.create(
            account=self.vendor,
            entity=self.entity,
            bankname="HDFC Bank",
            banKAcno="1234567890",
            ifsc="HDFC0123456",
            branch="Main",
            isprimary=True,
            createdby=self.user,
        )

    def _open_item(self, *, amount=Decimal("1180.00"), vendor=None, number="PI/PINV/2026/1001"):
        vendor = vendor or self.vendor
        doc_no_match = re.search(r"(\d+)$", number)
        doc_no = int(doc_no_match.group(1)) if doc_no_match else 1001
        header = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=vendor,
            bill_date=date(2026, 9, 1),
            due_date=date(2026, 9, 15),
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            doc_code="PINV",
            doc_no=doc_no,
            purchase_number=number,
            status=PurchaseInvoiceHeader.Status.POSTED,
            default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE,
            tax_regime=PurchaseInvoiceHeader.TaxRegime.INTRA,
            grand_total=amount,
        )
        return VendorBillOpenItem.objects.create(
            header=header,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=vendor,
            doc_type=header.doc_type,
            bill_date=header.bill_date,
            due_date=header.due_date,
            purchase_number=header.purchase_number,
            original_amount=amount,
            gross_amount=amount,
            net_payable_amount=amount,
            outstanding_amount=amount,
            is_open=True,
        )

    def _bank_statement_line_for_reconciliation(self, *, amount=Decimal("590.00"), reference_no="UTR590"):
        bank_account = EntityBankAccountV2.objects.create(
            entity=self.entity,
            bank_name="HDFC Bank",
            branch="Main",
            account_number="123456789012",
            ifsc_code="HDFC0001234",
            book_ledger=self.bank_ledger,
            createdby=self.user,
        )
        statement_import = BankStatementImport.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            bank_account=bank_account,
            status=BankStatementImport.Status.READY,
            source_file_name="hdfc.csv",
            source_file_sha256=reference_no.lower(),
            statement_from=date(2026, 9, 1),
            statement_to=date(2026, 9, 30),
            opening_balance=Decimal("10000.00"),
            closing_balance=Decimal("9410.00"),
            imported_line_count=1,
            uploaded_by=self.user,
        )
        line = BankStatementLine.objects.create(
            statement_import=statement_import,
            line_no=1,
            txn_date=date(2026, 9, 16),
            value_date=date(2026, 9, 16),
            narration=f"Vendor payment {reference_no}",
            reference_no=reference_no,
            debit_amount=amount,
            credit_amount=Decimal("0.00"),
            balance=Decimal("9410.00"),
            validation_status=BankStatementLine.ValidationStatus.VALID,
            reconciliation_status=BankStatementLine.ReconciliationStatus.UNMATCHED,
        )
        run = BankReconciliationRun.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            bank_account=bank_account,
            statement_import=statement_import,
            status=BankReconciliationRun.Status.MATCHING,
            as_of_date=date(2026, 9, 30),
            statement_opening_balance=statement_import.opening_balance,
            statement_closing_balance=statement_import.closing_balance,
            statement_line_count=1,
            metadata={"book_account_id": self.bank_account.id},
            created_by=self.user,
        )
        return run, line

    def _bank_book_line_for_reconciliation(self, *, amount=Decimal("590.00"), reference_no="UTR590"):
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PAYMENT,
            txn_id=9001,
            voucher_no=f"PV-{reference_no}",
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PAYMENT,
            txn_id=9001,
            voucher_no=f"PV-{reference_no}",
            voucher_date=date(2026, 9, 16),
            posting_date=date(2026, 9, 16),
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration=f"Vendor payment {reference_no}",
            created_by=self.user,
        )
        return JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PAYMENT,
            txn_id=9001,
            voucher_no=f"PV-{reference_no}",
            account=self.bank_account,
            ledger=self.bank_account.ledger,
            drcr=False,
            amount=amount,
            description=f"Vendor payment {reference_no}",
            posting_date=date(2026, 9, 16),
            posted_at=timezone.now(),
            created_by=self.user,
        )

    def _posted_bank_balance(self, *, amount=Decimal("5000.00"), drcr=True, reference_no="BANKBAL"):
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL,
            txn_id=9901,
            voucher_no=f"JV-{reference_no}",
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL,
            txn_id=9901,
            voucher_no=f"JV-{reference_no}",
            voucher_date=date(2026, 9, 16),
            posting_date=date(2026, 9, 16),
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration=f"Treasury forecast seed {reference_no}",
            created_by=self.user,
        )
        return JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL,
            txn_id=9901,
            voucher_no=f"JV-{reference_no}",
            account=self.bank_account,
            ledger=self.bank_account.ledger,
            drcr=drcr,
            amount=amount,
            description=f"Treasury forecast seed {reference_no}",
            posting_date=date(2026, 9, 16),
            posted_at=timezone.now(),
            created_by=self.user,
        )

    def test_cash_forecast_summarizes_bank_balance_batches_and_unbatched_ap(self):
        self._posted_bank_balance(amount=Decimal("5000.00"))
        active_item = self._open_item(amount=Decimal("1180.00"), number="PI/PINV/2026/9001")
        self._open_item(amount=Decimal("300.00"), number="PI/PINV/2026/9002")
        TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[active_item.id],
            paid_from_id=self.bank_account.id,
            payment_mode_id=self.payment_mode.id,
            user_id=self.user.id,
        )

        forecast = TreasuryPaymentBatchService.build_cash_forecast(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of=date(2026, 9, 16),
            horizon_days=30,
        )

        self.assertEqual(forecast["book_cash_balance"], "5000.00")
        self.assertEqual(forecast["active_batch_outflow"], "1180.00")
        self.assertEqual(forecast["unbatched_ap_due"], "300.00")
        self.assertEqual(forecast["planned_outflow"], "1480.00")
        self.assertEqual(forecast["projected_balance"], "3520.00")
        overdue_bucket = next(row for row in forecast["buckets"] if row["key"] == "overdue")
        self.assertEqual(overdue_bucket["count"], 1)
        self.assertEqual(overdue_bucket["amount"], "300.00")
        self.assertEqual(forecast["pending_instrument_count"], 1)

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("core.entitlements.EffectivePermissionService.has_data_scope_access", return_value=True)
    @patch("core.entitlements.EffectivePermissionService.has_scope_access", return_value=True)
    @patch("treasury.views.EffectivePermissionService.permission_codes_for_user", return_value={"treasury.payment_batch.view"})
    @patch("treasury.views.EffectivePermissionService.entity_for_user")
    def test_cash_forecast_api_uses_treasury_scope_and_permissions(
        self,
        mock_entity_for_user,
        mock_permission_codes,
        mock_scope_access,
        mock_data_scope_access,
        mock_subscription_access,
    ):
        mock_entity_for_user.return_value = self.entity
        self._posted_bank_balance(amount=Decimal("2500.00"))

        response = self.client.get(
            "/api/treasury/cash-forecast/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "as_of": "2026-09-16",
                "horizon_days": "45",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["book_cash_balance"], "2500.00")
        self.assertEqual(response.data["horizon_days"], 45)
        self.assertIn("Main Bank", {row["account_name"] for row in response.data["accounts"]})

    def test_vendor_payable_batch_validates_approves_exports_and_marks_paid(self):
        item = self._open_item()

        batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[item.id],
            batch_name="September vendor run",
            payout_date=date(2026, 9, 16),
            user_id=self.user.id,
        )

        self.assertEqual(batch.status, TreasuryPaymentBatch.Status.VALIDATED)
        self.assertEqual(batch.total_lines, 1)
        self.assertEqual(batch.payable_line_count, 1)
        self.assertEqual(batch.invalid_line_count, 0)
        self.assertEqual(batch.total_amount, Decimal("1180.00"))
        instrument = batch.instruments.get()
        self.assertEqual(instrument.status, TreasuryPaymentInstrument.Status.PREPARED)
        self.assertEqual(instrument.amount, Decimal("1180.00"))

        batch = TreasuryPaymentBatchService.approve_batch(batch=batch, user_id=self.user.id)
        self.assertEqual(batch.status, TreasuryPaymentBatch.Status.APPROVED)
        result = TreasuryPaymentBatchService.export_batch(batch=batch, user_id=self.user.id)
        self.assertIn("beneficiary_account_number", result.file_content)
        self.assertIn("1234567890", result.file_content)
        instrument.refresh_from_db()
        self.assertEqual(instrument.status, TreasuryPaymentInstrument.Status.EXPORTED)
        self.assertEqual(instrument.reference_no, result.batch.export_reference)
        batch = TreasuryPaymentBatchService.mark_paid(batch=result.batch, user_id=self.user.id, payment_reference="UTR123")
        self.assertEqual(batch.status, TreasuryPaymentBatch.Status.PAID)
        self.assertEqual(batch.lines.first().line_status, TreasuryPaymentBatchLine.LineStatus.PAID)
        instrument.refresh_from_db()
        self.assertEqual(instrument.status, TreasuryPaymentInstrument.Status.CLEARED)
        self.assertEqual(instrument.reference_no, "UTR123")
        self.assertIsNotNone(instrument.cleared_at)
        item.refresh_from_db()
        self.assertFalse(item.is_open)
        self.assertEqual(item.settled_amount, Decimal("1180.00"))
        self.assertEqual(item.outstanding_amount, Decimal("0.00"))
        handoff = batch.config_json["ap_handoff"]
        self.assertEqual(handoff["settlement_total"], "1180.00")
        settlement = VendorSettlement.objects.get(pk=handoff["settlement_ids"][0])
        self.assertEqual(settlement.status, VendorSettlement.Status.POSTED)
        self.assertEqual(settlement.reference_no, "UTR123")

    def test_vendor_payable_candidates_serialize_active_batch_flag(self):
        self._open_item(amount=Decimal("875.00"), number="PI/PINV/2026/1099")

        candidates = TreasuryPaymentBatchService.list_vendor_payable_candidates(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
        )

        data = TreasuryVendorPayableCandidateSerializer(candidates, many=True).data

        self.assertEqual(len(data), 1)
        self.assertIn("is_selected_in_active_batch", data[0])
        self.assertFalse(data[0]["is_selected_in_active_batch"])

    def test_vendor_payable_batch_can_mark_paid_through_payment_voucher(self):
        item = self._open_item(amount=Decimal("590.00"))
        batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[item.id],
            batch_name="Voucher backed run",
            payout_date=date(2026, 9, 16),
            paid_from_id=self.bank_account.id,
            payment_mode_id=self.payment_mode.id,
            instrument_no="NEFT-590",
            user_id=self.user.id,
        )
        batch = TreasuryPaymentBatchService.approve_batch(batch=batch, user_id=self.user.id)

        batch = TreasuryPaymentBatchService.mark_paid(batch=batch, user_id=self.user.id, payment_reference="UTR590")

        self.assertEqual(batch.status, TreasuryPaymentBatch.Status.PAID)
        handoff = batch.config_json["payment_voucher_handoff"]
        self.assertEqual(handoff["mode"], "vendor_payables_payment_voucher")
        self.assertEqual(handoff["settlement_total"], "590.00")
        voucher = PaymentVoucherHeader.objects.get(pk=handoff["payment_voucher_ids"][0])
        self.assertEqual(voucher.status, PaymentVoucherHeader.Status.POSTED)
        self.assertEqual(voucher.paid_from_id, self.bank_account.id)
        self.assertEqual(voucher.payment_mode_id, self.payment_mode.id)
        self.assertEqual(voucher.reference_number, "UTR590")
        self.assertIsNotNone(voucher.ap_settlement_id)
        instrument = batch.instruments.get()
        self.assertEqual(instrument.status, TreasuryPaymentInstrument.Status.CLEARED)
        self.assertEqual(instrument.instrument_type, TreasuryPaymentInstrument.InstrumentType.NEFT)
        self.assertEqual(instrument.source_account_id, self.bank_account.id)
        self.assertEqual(instrument.payment_mode_id, self.payment_mode.id)
        self.assertEqual(instrument.reference_no, "UTR590")
        self.assertEqual(instrument.instrument_no, "NEFT-590")
        item.refresh_from_db()
        self.assertFalse(item.is_open)
        self.assertEqual(item.outstanding_amount, Decimal("0.00"))

    def test_bank_reconciliation_match_links_and_unlinks_cleared_treasury_instrument(self):
        item = self._open_item(amount=Decimal("590.00"), number="PI/PINV/2026/2101")
        batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[item.id],
            paid_from_id=self.bank_account.id,
            payment_mode_id=self.payment_mode.id,
            instrument_no="NEFT-590",
            user_id=self.user.id,
        )
        batch = TreasuryPaymentBatchService.approve_batch(batch=batch, user_id=self.user.id)
        batch = TreasuryPaymentBatchService.mark_paid(batch=batch, user_id=self.user.id, payment_reference="UTR590")
        instrument = batch.instruments.get()
        self.assertEqual(instrument.status, TreasuryPaymentInstrument.Status.CLEARED)
        self.assertIsNone(instrument.reconciliation_match_id)

        run, bank_line = self._bank_statement_line_for_reconciliation(amount=Decimal("590.00"), reference_no="UTR590")
        journal_line = self._bank_book_line_for_reconciliation(amount=Decimal("590.00"), reference_no="UTR590")

        match = confirm_manual_match(run=run, bank_lines=[bank_line], journal_lines=[journal_line], actor=self.user)

        instrument.refresh_from_db()
        self.assertEqual(match.status, BankReconciliationMatch.Status.CONFIRMED)
        self.assertEqual(instrument.reconciliation_match_id, match.id)
        self.assertEqual(instrument.reconciled_bank_line_id, bank_line.id)
        self.assertIsNotNone(instrument.reconciled_at)
        self.assertEqual(instrument.metadata_json["bank_reconciliation"]["match_code"], match.match_code)

        unmatch(match=match, actor=self.user, notes="Wrong bank line")

        instrument.refresh_from_db()
        self.assertIsNone(instrument.reconciliation_match_id)
        self.assertIsNone(instrument.reconciled_bank_line_id)
        self.assertIsNone(instrument.reconciled_at)
        self.assertEqual(
            instrument.metadata_json["bank_reconciliation"]["cleared_reason"],
            "bank_reconciliation_match_cancelled",
        )

    def test_vendor_payable_batch_instrument_tracks_failed_status(self):
        item = self._open_item(amount=Decimal("250.00"))
        batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[item.id],
            paid_from_id=self.bank_account.id,
            payment_mode_id=self.payment_mode.id,
            user_id=self.user.id,
        )
        batch = TreasuryPaymentBatchService.approve_batch(batch=batch, user_id=self.user.id)

        batch = TreasuryPaymentBatchService.mark_failed(
            batch=batch,
            user_id=self.user.id,
            failure_reason="Rejected by bank",
        )

        self.assertEqual(batch.status, TreasuryPaymentBatch.Status.FAILED)
        instrument = batch.instruments.get()
        self.assertEqual(instrument.status, TreasuryPaymentInstrument.Status.FAILED)
        self.assertEqual(instrument.status_reason, "Rejected by bank")
        self.assertIsNotNone(instrument.failed_at)
        item.refresh_from_db()
        self.assertTrue(item.is_open)

    def test_vendor_payable_batch_instrument_tracks_cancelled_status(self):
        item = self._open_item(amount=Decimal("350.00"))
        batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[item.id],
            paid_from_id=self.bank_account.id,
            payment_mode_id=self.payment_mode.id,
            user_id=self.user.id,
        )

        batch = TreasuryPaymentBatchService.cancel_batch(
            batch=batch,
            user_id=self.user.id,
            cancellation_reason="Wrong vendor selected",
        )

        self.assertEqual(batch.status, TreasuryPaymentBatch.Status.CANCELLED)
        instrument = batch.instruments.get()
        self.assertEqual(instrument.status, TreasuryPaymentInstrument.Status.CANCELLED)
        self.assertEqual(instrument.status_reason, "Wrong vendor selected")
        self.assertIsNotNone(instrument.cancelled_at)
        item.refresh_from_db()
        self.assertTrue(item.is_open)

    def test_vendor_open_item_cannot_be_added_to_two_active_batches(self):
        item = self._open_item()
        TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[item.id],
            user_id=self.user.id,
        )

        with self.assertRaisesMessage(ValueError, "already part of an active treasury batch"):
            TreasuryPaymentBatchService.create_from_vendor_open_items(
                entity_id=self.entity.id,
                entityfinid_id=self.entityfin.id,
                subentity_id=self.subentity.id,
                open_item_ids=[item.id],
                user_id=self.user.id,
            )

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("core.entitlements.EffectivePermissionService.has_data_scope_access", return_value=True)
    @patch("core.entitlements.EffectivePermissionService.has_scope_access", return_value=True)
    @patch("treasury.views.EffectivePermissionService.permission_codes_for_user", return_value={"treasury.payment_batch.view"})
    @patch("treasury.views.EffectivePermissionService.entity_for_user")
    def test_payment_instrument_register_filters_by_status_and_search(
        self,
        mock_entity_for_user,
        mock_permission_codes,
        mock_scope_access,
        mock_data_scope_access,
        mock_subscription_access,
    ):
        mock_entity_for_user.return_value = self.entity
        item = self._open_item(amount=Decimal("590.00"), number="PI/PINV/2026/2001")
        batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[item.id],
            paid_from_id=self.bank_account.id,
            payment_mode_id=self.payment_mode.id,
            instrument_no="NEFT-590",
            user_id=self.user.id,
        )
        batch = TreasuryPaymentBatchService.approve_batch(batch=batch, user_id=self.user.id)
        TreasuryPaymentBatchService.mark_paid(batch=batch, user_id=self.user.id, payment_reference="UTR590")

        response = self.client.get(
            "/api/treasury/payment-instruments/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "status": TreasuryPaymentInstrument.Status.CLEARED,
                "search": "UTR590",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["reference_no"], "UTR590")
        self.assertEqual(response.data[0]["batch_number"], batch.batch_number)
        self.assertEqual(response.data[0]["party_names"], ["Vendor One"])

    def test_instrument_lifecycle_transitions_and_blocks_invalid_regression(self):
        item = self._open_item(amount=Decimal("720.00"), number="PI/PINV/2026/3001")
        batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[item.id],
            paid_from_id=self.bank_account.id,
            payment_mode_id=self.payment_mode.id,
            instrument_no="NEFT-720",
            user_id=self.user.id,
        )
        batch = TreasuryPaymentBatchService.approve_batch(batch=batch, user_id=self.user.id)
        result = TreasuryPaymentBatchService.export_batch(batch=batch, user_id=self.user.id)
        instrument = result.batch.instruments.get()

        instrument = TreasuryPaymentBatchService.transition_instrument(
            instrument=instrument,
            action="sent-to-bank",
            user_id=self.user.id,
            reference_no="BANK-FILE-1",
            reason="Uploaded to bank portal",
        )
        self.assertEqual(instrument.status, TreasuryPaymentInstrument.Status.SENT_TO_BANK)
        self.assertEqual(instrument.reference_no, "BANK-FILE-1")
        self.assertIn("lifecycle_history", instrument.metadata_json)

        instrument = TreasuryPaymentBatchService.transition_instrument(
            instrument=instrument,
            action="cleared",
            user_id=self.user.id,
            reference_no="UTR720",
        )
        self.assertEqual(instrument.status, TreasuryPaymentInstrument.Status.CLEARED)
        self.assertEqual(instrument.reference_no, "UTR720")
        self.assertIsNotNone(instrument.cleared_at)

        with self.assertRaisesMessage(ValueError, "Cannot move instrument"):
            TreasuryPaymentBatchService.transition_instrument(
                instrument=instrument,
                action="sent-to-bank",
                user_id=self.user.id,
            )

    def test_cheque_book_creation_generates_leaves_and_rejects_duplicates(self):
        book = TreasuryPaymentBatchService.create_cheque_book(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            bank_account_id=self.bank_account.id,
            book_number="CHQ-001",
            start_leaf="000101",
            end_leaf="000103",
            user_id=self.user.id,
        )

        self.assertEqual(book.total_leaves, 3)
        self.assertEqual(
            list(book.leaves.order_by("leaf_no").values_list("leaf_no", "status")),
            [
                ("000101", TreasuryChequeLeaf.Status.AVAILABLE),
                ("000102", TreasuryChequeLeaf.Status.AVAILABLE),
                ("000103", TreasuryChequeLeaf.Status.AVAILABLE),
            ],
        )

        with self.assertRaisesMessage(ValueError, "already exist"):
            TreasuryPaymentBatchService.create_cheque_book(
                entity_id=self.entity.id,
                entityfinid_id=self.entityfin.id,
                subentity_id=self.subentity.id,
                bank_account_id=self.bank_account.id,
                book_number="CHQ-002",
                start_leaf="000103",
                end_leaf="000105",
                user_id=self.user.id,
            )

    def test_cheque_leaf_links_to_instrument_and_tracks_lifecycle(self):
        book = TreasuryPaymentBatchService.create_cheque_book(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            bank_account_id=self.bank_account.id,
            book_number="CHQ-003",
            start_leaf="2001",
            end_leaf="2002",
            user_id=self.user.id,
        )
        leaf = book.leaves.get(leaf_no="2001")
        item = self._open_item(amount=Decimal("650.00"), number="PI/PINV/2026/4001")
        batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[item.id],
            paid_from_id=self.bank_account.id,
            payment_mode_id=self.cheque_payment_mode.id,
            user_id=self.user.id,
        )
        instrument = batch.instruments.get()

        instrument = TreasuryPaymentBatchService.transition_instrument(
            instrument=instrument,
            action="sent-to-bank",
            user_id=self.user.id,
            cheque_leaf_id=leaf.id,
            reason="Cheque handed over",
        )

        self.assertEqual(instrument.cheque_leaf_id, leaf.id)
        self.assertEqual(instrument.instrument_no, "2001")
        leaf.refresh_from_db()
        self.assertEqual(leaf.status, TreasuryChequeLeaf.Status.ISSUED)
        self.assertIsNotNone(leaf.used_at)

        instrument = TreasuryPaymentBatchService.transition_instrument(
            instrument=instrument,
            action="cleared",
            user_id=self.user.id,
            reference_no="CHQ-CLR-2001",
        )
        leaf.refresh_from_db()
        self.assertEqual(instrument.status, TreasuryPaymentInstrument.Status.CLEARED)
        self.assertEqual(leaf.status, TreasuryChequeLeaf.Status.CLEARED)

    def test_cheque_leaf_cannot_be_linked_to_two_instruments(self):
        book = TreasuryPaymentBatchService.create_cheque_book(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            bank_account_id=self.bank_account.id,
            book_number="CHQ-004",
            start_leaf="3001",
            end_leaf="3001",
            user_id=self.user.id,
        )
        leaf = book.leaves.get()
        first_item = self._open_item(amount=Decimal("200.00"), number="PI/PINV/2026/5001")
        second_item = self._open_item(amount=Decimal("300.00"), number="PI/PINV/2026/5002")
        first_batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[first_item.id],
            paid_from_id=self.bank_account.id,
            payment_mode_id=self.cheque_payment_mode.id,
            user_id=self.user.id,
        )
        second_batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[second_item.id],
            paid_from_id=self.bank_account.id,
            payment_mode_id=self.cheque_payment_mode.id,
            user_id=self.user.id,
        )

        TreasuryPaymentBatchService.transition_instrument(
            instrument=first_batch.instruments.get(),
            action="sent-to-bank",
            user_id=self.user.id,
            cheque_leaf_id=leaf.id,
        )

        with self.assertRaisesMessage(ValueError, "already linked"):
            TreasuryPaymentBatchService.transition_instrument(
                instrument=second_batch.instruments.get(),
                action="sent-to-bank",
                user_id=self.user.id,
                cheque_leaf_id=leaf.id,
            )

    def test_cash_deposit_posts_bank_voucher_with_treasury_trace(self):
        movement = TreasuryPaymentBatchService.create_cash_movement(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            movement_type=TreasuryCashMovement.MovementType.CASH_DEPOSIT,
            movement_date=date(2026, 9, 16),
            source_account_id=self.cash_account.id,
            destination_account_id=self.bank_account.id,
            payment_mode_id=self.payment_mode.id,
            amount=Decimal("1250.00"),
            reference_no="DEP-001",
            narration="Daily cash deposit",
            user_id=self.user.id,
        )

        self.assertEqual(movement.status, TreasuryCashMovement.Status.POSTED)
        self.assertTrue(movement.movement_number.startswith(f"TCM-{self.entity.id}-"))
        voucher = movement.voucher
        self.assertEqual(voucher.status, VoucherHeader.Status.POSTED)
        self.assertEqual(voucher.voucher_type, VoucherHeader.VoucherType.BANK)
        self.assertEqual(voucher.cash_bank_account_id, self.bank_account.id)
        self.assertEqual(voucher.reference_number, "DEP-001")
        rows = list(voucher.lines.order_by("line_no"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].account_id, self.cash_account.id)
        self.assertEqual(rows[0].cr_amount, Decimal("1250.00"))
        self.assertEqual(rows[1].account_id, self.bank_account.id)
        self.assertEqual(rows[1].dr_amount, Decimal("1250.00"))
        self.assertEqual(rows[1].system_line_role, VoucherLine.SystemLineRole.BANK_OFFSET)

    def test_bank_to_bank_movement_posts_and_cancels_linked_voucher(self):
        movement = TreasuryPaymentBatchService.create_cash_movement(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            movement_type=TreasuryCashMovement.MovementType.BANK_TO_BANK,
            movement_date=date(2026, 9, 16),
            source_account_id=self.bank_account.id,
            destination_account_id=self.reserve_bank_account.id,
            amount=Decimal("3000.00"),
            reference_no="B2B-001",
            user_id=self.user.id,
        )
        voucher_id = movement.voucher_id

        movement = TreasuryPaymentBatchService.cancel_cash_movement(
            movement=movement,
            user_id=self.user.id,
            reason="Wrong bank selected",
        )

        self.assertEqual(movement.status, TreasuryCashMovement.Status.CANCELLED)
        self.assertEqual(movement.cancellation_reason, "Wrong bank selected")
        voucher = VoucherHeader.objects.get(pk=voucher_id)
        self.assertEqual(voucher.status, VoucherHeader.Status.CANCELLED)
        self.assertEqual(voucher.cancel_reason, "Wrong bank selected")

    def test_cash_movement_rejects_same_source_and_destination(self):
        with self.assertRaisesMessage(ValueError, "Source and destination accounts must be different"):
            TreasuryPaymentBatchService.create_cash_movement(
                entity_id=self.entity.id,
                entityfinid_id=self.entityfin.id,
                subentity_id=self.subentity.id,
                movement_type=TreasuryCashMovement.MovementType.BANK_TO_BANK,
                source_account_id=self.bank_account.id,
                destination_account_id=self.bank_account.id,
                amount=Decimal("100.00"),
                user_id=self.user.id,
            )

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("core.entitlements.EffectivePermissionService.has_data_scope_access", return_value=True)
    @patch("core.entitlements.EffectivePermissionService.has_scope_access", return_value=True)
    @patch("treasury.views.EffectivePermissionService.permission_codes_for_user", return_value={"treasury.payment_batch.update", "treasury.payment_batch.view"})
    @patch("treasury.views.EffectivePermissionService.entity_for_user")
    def test_cash_movement_api_creates_lists_and_cancels(
        self,
        mock_entity_for_user,
        mock_permission_codes,
        mock_scope_access,
        mock_data_scope_access,
        mock_subscription_access,
    ):
        mock_entity_for_user.return_value = self.entity

        response = self.client.post(
            "/api/treasury/cash-movements/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "movement_type": TreasuryCashMovement.MovementType.CASH_WITHDRAWAL,
                "movement_date": "2026-09-16",
                "source_account": self.bank_account.id,
                "destination_account": self.cash_account.id,
                "payment_mode": self.payment_mode.id,
                "amount": "700.00",
                "reference_no": "WD-001",
                "narration": "Petty cash withdrawal",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        movement_id = response.data["data"]["id"]
        self.assertEqual(response.data["data"]["status"], TreasuryCashMovement.Status.POSTED)
        self.assertEqual(response.data["data"]["voucher_status"], VoucherHeader.Status.POSTED)

        list_response = self.client.get(
            "/api/treasury/cash-movements/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "search": "WD-001",
            },
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]["reference_no"], "WD-001")

        cancel_response = self.client.post(
            f"/api/treasury/cash-movements/{movement_id}/cancel/",
            {"reason": "Duplicate entry"},
            format="json",
        )
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.data["data"]["status"], TreasuryCashMovement.Status.CANCELLED)

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("core.entitlements.EffectivePermissionService.has_data_scope_access", return_value=True)
    @patch("core.entitlements.EffectivePermissionService.has_scope_access", return_value=True)
    @patch("treasury.views.EffectivePermissionService.permission_codes_for_user", return_value={"treasury.payment_batch.update"})
    @patch("treasury.views.EffectivePermissionService.entity_for_user")
    def test_payment_instrument_action_api_updates_lifecycle(
        self,
        mock_entity_for_user,
        mock_permission_codes,
        mock_scope_access,
        mock_data_scope_access,
        mock_subscription_access,
    ):
        mock_entity_for_user.return_value = self.entity
        item = self._open_item(amount=Decimal("810.00"), number="PI/PINV/2026/3002")
        batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[item.id],
            paid_from_id=self.bank_account.id,
            payment_mode_id=self.payment_mode.id,
            user_id=self.user.id,
        )
        batch = TreasuryPaymentBatchService.approve_batch(batch=batch, user_id=self.user.id)
        result = TreasuryPaymentBatchService.export_batch(batch=batch, user_id=self.user.id)
        instrument = result.batch.instruments.get()

        response = self.client.post(
            f"/api/treasury/payment-instruments/{instrument.id}/failed/",
            {
                "reason": "Rejected by bank",
                "reference_no": "BANK-REJ-810",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], TreasuryPaymentInstrument.Status.FAILED)
        self.assertEqual(response.data["data"]["status_reason"], "Rejected by bank")
        self.assertEqual(response.data["data"]["reference_no"], "BANK-REJ-810")
        instrument.refresh_from_db()
        self.assertIsNotNone(instrument.failed_at)

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("core.entitlements.EffectivePermissionService.has_data_scope_access", return_value=True)
    @patch("core.entitlements.EffectivePermissionService.has_scope_access", return_value=True)
    @patch("treasury.views.EffectivePermissionService.permission_codes_for_user", return_value={"treasury.payment_batch.update", "treasury.payment_batch.view"})
    @patch("treasury.views.EffectivePermissionService.entity_for_user")
    def test_cheque_book_api_creates_and_lists_leaves(
        self,
        mock_entity_for_user,
        mock_permission_codes,
        mock_scope_access,
        mock_data_scope_access,
        mock_subscription_access,
    ):
        mock_entity_for_user.return_value = self.entity

        response = self.client.post(
            "/api/treasury/cheque-books/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "bank_account": self.bank_account.id,
                "book_number": "API-CHQ-001",
                "start_leaf": "9001",
                "end_leaf": "9002",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["total_leaves"], 2)
        self.assertEqual(response.data["data"]["available_leaf_count"], 2)
        self.assertTrue(TreasuryChequeBook.objects.filter(book_number="API-CHQ-001").exists())

        leaves_response = self.client.get(
            "/api/treasury/cheque-leaves/",
            {
                "entity": self.entity.id,
                "bank_account": self.bank_account.id,
                "status": TreasuryChequeLeaf.Status.AVAILABLE,
            },
        )

        self.assertEqual(leaves_response.status_code, 200)
        self.assertEqual([row["leaf_no"] for row in leaves_response.data], ["9001", "9002"])

    def test_missing_vendor_bank_details_blocks_approval(self):
        vendor_without_bank = account.objects.create(entity=self.entity, accountname="Vendor Without Bank", createdby=self.user)
        item = self._open_item(vendor=vendor_without_bank, number="PI/PINV/2026/1002")

        batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            open_item_ids=[item.id],
            user_id=self.user.id,
        )

        self.assertEqual(batch.invalid_line_count, 1)
        line = batch.lines.first()
        self.assertIn("Beneficiary bank account number is missing.", line.validation_errors_json)
        with self.assertRaisesMessage(ValueError, "Resolve invalid payment lines before approval"):
            TreasuryPaymentBatchService.approve_batch(batch=batch, user_id=self.user.id)
