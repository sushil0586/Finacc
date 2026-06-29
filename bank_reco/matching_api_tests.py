from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, EntityBankAccountV2, EntityFinancialYear, GstRegistrationType, SubEntity
from financial.models import AccountBankDetails, Ledger, account, accountHead
from numbering.models import DocumentNumberSeries, DocumentType
from posting.models import Entry, EntryStatus, JournalLine, PostingBatch, TxnType
from subscriptions.services import SubscriptionService
from vouchers.models.voucher_config import VoucherSettings
from vouchers.models.voucher_core import VoucherHeader

from .models import BankReconciliationAuditLog, BankReconciliationMatch, BankStatementLine
from .services.matching import get_or_create_run


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class BankRecoMatchingAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"bank-reco-match-{suffix}",
            email=f"bank-reco-match-{suffix}@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)
        customer_account = SubscriptionService.ensure_customer_account(user=self.user)
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Reco Match Entity",
            legalname="Reco Match Entity Pvt Ltd",
            GstRegitrationType=gst_type,
            createdby=self.user,
            customer_account=customer_account,
        )
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            year_code="FY2627M",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.other_entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2027-28",
            year_code="FY2728M",
            finstartyear=timezone.make_aware(datetime(2027, 4, 1)),
            finendyear=timezone.make_aware(datetime(2028, 3, 31)),
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Head Office", is_head_office=True)
        self.other_subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch Office")
        self.bank_account = EntityBankAccountV2.objects.create(
            entity=self.entity,
            bank_name="HDFC",
            branch="Main",
            account_number="123456789012",
            ifsc_code="HDFC0001234",
            createdby=self.user,
        )
        self.bank_head = accountHead.objects.create(
            entity=self.entity,
            name="Bank Head",
            code=9001,
            drcreffect="Debit",
            createdby=self.user,
        )
        self.other_bank_head = accountHead.objects.create(
            entity=self.entity,
            name="Other Bank Head",
            code=9002,
            drcreffect="Debit",
            createdby=self.user,
        )
        self.bank_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=1001,
            name="Reco Bank Ledger",
            accounthead=self.bank_head,
            createdby=self.user,
        )
        self.other_bank_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=1002,
            name="Other Bank Ledger",
            accounthead=self.other_bank_head,
            createdby=self.user,
        )
        self.bank_book_account = account.objects.create(
            entity=self.entity,
            accountname="Reco Bank Account",
            ledger=self.bank_ledger,
            createdby=self.user,
        )
        self.other_bank_book_account = account.objects.create(
            entity=self.entity,
            accountname="Other Bank Account",
            ledger=self.other_bank_ledger,
            createdby=self.user,
        )
        self.customer_head = accountHead.objects.create(
            entity=self.entity,
            name="Customer Head",
            code=9101,
            drcreffect="Credit",
            createdby=self.user,
        )
        self.vendor_head = accountHead.objects.create(
            entity=self.entity,
            name="Vendor Head",
            code=9102,
            drcreffect="Debit",
            createdby=self.user,
        )
        self.income_head = accountHead.objects.create(
            entity=self.entity,
            name="Income Head",
            code=9103,
            drcreffect="Credit",
            createdby=self.user,
        )
        self.expense_head = accountHead.objects.create(
            entity=self.entity,
            name="Expense Head",
            code=9104,
            drcreffect="Debit",
            createdby=self.user,
        )
        self.tax_head = accountHead.objects.create(
            entity=self.entity,
            name="Tax Head",
            code=9105,
            drcreffect="Credit",
            createdby=self.user,
        )
        self.customer_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1101, name="Customer Ledger", accounthead=self.customer_head, createdby=self.user)
        self.vendor_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1102, name="Vendor Ledger", accounthead=self.vendor_head, createdby=self.user)
        self.interest_income_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1103, name="Interest Income Ledger", accounthead=self.income_head, createdby=self.user)
        self.bank_charges_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1104, name="Bank Charges Ledger", accounthead=self.expense_head, createdby=self.user)
        self.loan_emi_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1105, name="Loan EMI Ledger", accounthead=self.expense_head, createdby=self.user)
        self.gst_payable_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1106, name="GST Payable Ledger", accounthead=self.tax_head, createdby=self.user)
        self.tds_payable_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1107, name="TDS Payable Ledger", accounthead=self.tax_head, createdby=self.user)
        self.tcs_payable_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1108, name="TCS Payable Ledger", accounthead=self.tax_head, createdby=self.user)
        self.transfer_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1109, name="Transfer Ledger", accounthead=self.expense_head, createdby=self.user)
        self.customer_account = account.objects.create(entity=self.entity, accountname="Customer A", ledger=self.customer_ledger, createdby=self.user)
        self.vendor_account = account.objects.create(entity=self.entity, accountname="Vendor A", ledger=self.vendor_ledger, createdby=self.user)
        self.interest_income_account = account.objects.create(entity=self.entity, accountname="Interest Income", ledger=self.interest_income_ledger, createdby=self.user)
        self.bank_charges_account = account.objects.create(entity=self.entity, accountname="Bank Charges", ledger=self.bank_charges_ledger, createdby=self.user)
        self.loan_emi_account = account.objects.create(entity=self.entity, accountname="Loan EMI", ledger=self.loan_emi_ledger, createdby=self.user)
        self.gst_payable_account = account.objects.create(entity=self.entity, accountname="GST Payable", ledger=self.gst_payable_ledger, createdby=self.user)
        self.tds_payable_account = account.objects.create(entity=self.entity, accountname="TDS Payable", ledger=self.tds_payable_ledger, createdby=self.user)
        self.tcs_payable_account = account.objects.create(entity=self.entity, accountname="TCS Payable", ledger=self.tcs_payable_ledger, createdby=self.user)
        self.transfer_account = account.objects.create(entity=self.entity, accountname="Transfer Clearing", ledger=self.transfer_ledger, createdby=self.user)
        AccountBankDetails.objects.create(
            account=self.bank_book_account,
            entity=self.entity,
            bankname="HDFC",
            banKAcno=self.bank_account.account_number,
            ifsc=self.bank_account.ifsc_code,
            isprimary=True,
            createdby=self.user,
        )
        self.other_bank_account = EntityBankAccountV2.objects.create(
            entity=self.entity,
            bank_name="ICICI",
            branch="Second",
            account_number="222233334444",
            ifsc_code="ICIC0004321",
            createdby=self.user,
        )
        AccountBankDetails.objects.create(
            account=self.other_bank_book_account,
            entity=self.entity,
            bankname="ICICI",
            banKAcno=self.other_bank_account.account_number,
            ifsc=self.other_bank_account.ifsc_code,
            isprimary=True,
            createdby=self.user,
        )
        VoucherSettings.objects.update_or_create(
            entity=self.entity,
            subentity=None,
            defaults={
                "default_workflow_action": VoucherSettings.DefaultWorkflowAction.DRAFT,
                "policy_controls": {
                    "require_confirm_before_post": "on",
                    "require_submit_before_approve": "off",
                    "allow_edit_after_submit": "on",
                    "unpost_target_status": "confirmed",
                    "voucher_maker_checker": "off",
                    "same_user_submit_approve": "on",
                    "require_reference_number": "off",
                    "allow_control_account_lines": "on",
                    "require_cash_bank_account_for_cash_bank": "on",
                    "cash_bank_mixed_entry_rule": "off",
                },
            },
        )
        self.bank_voucher_doc_type, _ = DocumentType.objects.get_or_create(
            module="vouchers",
            doc_key="BANK_VOUCHER",
            defaults={"name": "Bank Voucher", "default_code": "BV", "is_active": True},
        )
        DocumentNumberSeries.objects.update_or_create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=None,
            doc_type=self.bank_voucher_doc_type,
            doc_code="BV",
            defaults={
                "prefix": "",
                "suffix": "",
                "starting_number": 1,
                "current_number": 1,
                "number_padding": 4,
                "include_year": False,
                "include_month": False,
                "separator": "-",
                "reset_frequency": "none",
                "is_active": True,
                "created_by": self.user,
            },
        )

        self.other_user = User.objects.create_user(
            username=f"bank-reco-foreign-{suffix}",
            email=f"bank-reco-foreign-{suffix}@example.com",
            password="pass123",
        )
        other_ca = SubscriptionService.ensure_customer_account(user=self.other_user)
        self.other_entity = Entity.objects.create(
            entityname="Foreign Entity",
            legalname="Foreign Entity Pvt Ltd",
            GstRegitrationType=gst_type,
            createdby=self.other_user,
            customer_account=other_ca,
        )
        self.other_entityfin = EntityFinancialYear.objects.create(
            entity=self.other_entity,
            desc="FY 2026-27",
            year_code="FY2627O",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.other_user,
        )
        self.foreign_head = accountHead.objects.create(
            entity=self.other_entity,
            name="Foreign Head",
            code=9003,
            drcreffect="Debit",
            createdby=self.other_user,
        )
        self.foreign_ledger = Ledger.objects.create(
            entity=self.other_entity,
            ledger_code=2001,
            name="Foreign Bank Ledger",
            accounthead=self.foreign_head,
            createdby=self.other_user,
        )
        self.foreign_account = account.objects.create(
            entity=self.other_entity,
            accountname="Foreign Bank Account",
            ledger=self.foreign_ledger,
            createdby=self.other_user,
        )

    def _csv_file(self, name: str, body: str):
        return SimpleUploadedFile(name, body.encode("utf-8"), content_type="text/csv")

    def _create_import_and_run(self, lines: list[str], opening="1000.00", closing="1000.00", entityfin=None, subentity=None, bank_account=None):
        entityfin = entityfin or self.entityfin
        bank_account = bank_account or self.bank_account
        dated_rows = [row.split(",")[0].strip() for row in lines if row.split(",")[0].strip()]
        statement_from = min(dated_rows) if dated_rows else None
        statement_to = max(dated_rows) if dated_rows else None
        payload = {
            "entity": self.entity.id,
            "entityfinid": entityfin.id,
            "bank_account": bank_account.id,
            "source_file_type": "csv",
            "opening_balance": opening,
            "closing_balance": closing,
            "file": self._csv_file(
                "statement.csv",
                "transaction_date,description,reference_number,cheque_no,debit_amount,credit_amount,balance_amount\n"
                + "\n".join(lines),
            ),
        }
        if subentity is not None:
            payload["subentity"] = subentity.id
        if statement_from:
            payload["statement_from"] = statement_from
        if statement_to:
            payload["statement_to"] = statement_to
        response = self.client.post(
            reverse("bank_reco_api:bank-reco-import-create"),
            payload,
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.json())
        import_id = response.json()["id"]
        validate = self.client.post(reverse("bank_reco_api:bank-reco-import-validate", args=[import_id]))
        self.assertEqual(validate.status_code, 200)
        statement_import = self.entity.bank_statement_imports.get(pk=import_id)
        run = get_or_create_run(statement_import=statement_import, actor=self.user)
        return statement_import, run

    def _create_book_line(self, *, amount: str, posting_date: str, description: str = "", voucher_no="V001", drcr=True, txn_type=TxnType.RECEIPT, book_account=None, entity=None, entityfin=None, subentity=None, txn_id=1):
        entity = entity or self.entity
        entityfin = entityfin or self.entityfin
        book_account = book_account or self.bank_book_account
        batch = PostingBatch.objects.create(
            entity=entity,
            entityfin=entityfin,
            subentity=subentity,
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=voucher_no,
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=entity,
            entityfin=entityfin,
            subentity=subentity,
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=voucher_no,
            voucher_date=posting_date,
            posting_date=posting_date,
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration=description,
            created_by=self.user,
        )
        return JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=entity,
            entityfin=entityfin,
            subentity=subentity,
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=voucher_no,
            account=book_account,
            ledger=book_account.ledger,
            drcr=drcr,
            amount=amount,
            description=description,
            posting_date=posting_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )

    def test_exact_auto_match_confirms_high_confidence_match(self):
        statement_import, run = self._create_import_and_run(["2026-04-05,Receipt from customer,UTR123,,0,5000,6000"], closing="6000.00")
        self._create_book_line(amount="5000.00", posting_date="2026-04-05", description="Receipt UTR123", voucher_no="RV001", drcr=True, txn_id=11)
        response = self.client.post(reverse("bank_reco_api:bank-reco-import-auto-match", args=[statement_import.id]))
        self.assertEqual(response.status_code, 200)
        match = BankReconciliationMatch.objects.get(run=run)
        self.assertEqual(match.status, BankReconciliationMatch.Status.CONFIRMED)
        self.assertEqual(match.match_type, BankReconciliationMatch.MatchType.EXACT)
        self.assertIn("reference_match", match.reason_codes)

    def test_date_tolerance_auto_match_creates_suggestion(self):
        statement_import, run = self._create_import_and_run(["2026-04-05,Receipt from customer,,,0,5000,6000"], closing="6000.00")
        self._create_book_line(amount="5000.00", posting_date="2026-04-07", description="Receipt no ref", voucher_no="RV002", drcr=True, txn_id=12)
        response = self.client.post(reverse("bank_reco_api:bank-reco-import-auto-match", args=[statement_import.id]))
        self.assertEqual(response.status_code, 200)
        match = BankReconciliationMatch.objects.get(run=run)
        self.assertEqual(match.status, BankReconciliationMatch.Status.SUGGESTED)
        self.assertIn("date_tolerance", match.reason_codes)

    def test_narration_similarity_creates_possible_suggestion(self):
        statement_import, run = self._create_import_and_run([",Amazon settlement,,,0,4200,5200"], closing="5200.00")
        self._create_book_line(amount="4200.00", posting_date="2026-04-10", description="Amazon settlement payout", voucher_no="RV003", drcr=True, txn_id=13)
        response = self.client.post(reverse("bank_reco_api:bank-reco-import-auto-match", args=[statement_import.id]))
        self.assertEqual(response.status_code, 200)
        match = BankReconciliationMatch.objects.get(run=run)
        self.assertEqual(match.match_type, BankReconciliationMatch.MatchType.POSSIBLE)
        self.assertTrue(any(code.startswith("narration_similarity") for code in match.reason_codes))

    def test_cheque_number_match_is_detected(self):
        statement_import, run = self._create_import_and_run(["2026-04-05,Cheque receipt,,CHQ100,0,2500,3500"], closing="3500.00")
        self._create_book_line(amount="2500.00", posting_date="2026-04-05", description="Receipt CHQ100", voucher_no="RV004", drcr=True, txn_id=14)
        response = self.client.post(reverse("bank_reco_api:bank-reco-import-auto-match", args=[statement_import.id]))
        self.assertEqual(response.status_code, 200)
        match = BankReconciliationMatch.objects.get(run=run)
        self.assertIn("cheque_match", match.reason_codes)

    def test_utr_reference_match_is_detected(self):
        statement_import, run = self._create_import_and_run(["2026-04-05,NEFT receipt,UTR555,,0,3000,4000"], closing="4000.00")
        self._create_book_line(amount="3000.00", posting_date="2026-04-05", description="Bank receipt UTR555", voucher_no="RV005", drcr=True, txn_id=15)
        response = self.client.post(reverse("bank_reco_api:bank-reco-import-auto-match", args=[statement_import.id]))
        self.assertEqual(response.status_code, 200)
        match = BankReconciliationMatch.objects.get(run=run)
        self.assertIn("reference_match", match.reason_codes)

    def test_manual_one_to_one_match(self):
        statement_import, run = self._create_import_and_run(["2026-04-06,Manual receipt,MAN001,,0,2000,3000"], closing="3000.00")
        journal = self._create_book_line(amount="2000.00", posting_date="2026-04-06", description="Manual receipt", voucher_no="RV006", drcr=True, txn_id=16)
        line = statement_import.lines.first()
        response = self.client.post(reverse("bank_reco_api:bank-reco-match"), {"run_id": run.id, "bank_line_id": line.id, "journal_line_id": journal.id}, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        match = BankReconciliationMatch.objects.get(run=run)
        self.assertEqual(match.status, BankReconciliationMatch.Status.CONFIRMED)
        line.refresh_from_db()
        self.assertEqual(line.reconciliation_status, BankStatementLine.ReconciliationStatus.CONFIRMED)

    def test_one_bank_to_many_book_entries_group_match(self):
        statement_import, run = self._create_import_and_run(["2026-04-07,Gateway settlement,GW001,,0,10000,11000"], closing="11000.00")
        j1 = self._create_book_line(amount="6000.00", posting_date="2026-04-07", description="Order 1 GW001", voucher_no="RV007", drcr=True, txn_id=17)
        j2 = self._create_book_line(amount="4000.00", posting_date="2026-04-07", description="Order 2 GW001", voucher_no="RV008", drcr=True, txn_id=18)
        line = statement_import.lines.first()
        response = self.client.post(reverse("bank_reco_api:bank-reco-group-match"), {"run_id": run.id, "bank_line_ids": [line.id], "journal_line_ids": [j1.id, j2.id]}, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        match = BankReconciliationMatch.objects.get(run=run)
        self.assertEqual(match.match_kind, BankReconciliationMatch.MatchKind.ONE_TO_MANY)

    def test_many_bank_to_one_book_entry_group_match(self):
        statement_import, run = self._create_import_and_run(
            ["2026-04-07,Part 1,REFA,,0,6000,7000", "2026-04-07,Part 2,REFB,,0,4000,11000"],
            closing="11000.00",
        )
        journal = self._create_book_line(amount="10000.00", posting_date="2026-04-07", description="Combined receipt", voucher_no="RV009", drcr=True, txn_id=19)
        lines = list(statement_import.lines.order_by("line_no"))
        response = self.client.post(reverse("bank_reco_api:bank-reco-group-match"), {"run_id": run.id, "bank_line_ids": [line.id for line in lines], "journal_line_ids": [journal.id]}, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        match = BankReconciliationMatch.objects.get(run=run)
        self.assertEqual(match.match_kind, BankReconciliationMatch.MatchKind.MANY_TO_ONE)

    def test_partial_match(self):
        statement_import, run = self._create_import_and_run(["2026-04-08,Net receipt,NET001,,0,10000,11000"], closing="11000.00")
        journal = self._create_book_line(amount="9800.00", posting_date="2026-04-08", description="Net receipt NET001", voucher_no="RV010", drcr=True, txn_id=20)
        line = statement_import.lines.first()
        response = self.client.post(reverse("bank_reco_api:bank-reco-match"), {"run_id": run.id, "bank_line_id": line.id, "journal_line_id": journal.id}, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        match = BankReconciliationMatch.objects.get(run=run)
        self.assertEqual(match.status, BankReconciliationMatch.Status.PARTIALLY_MATCHED)

    def test_unmatch_and_rematch(self):
        statement_import, run = self._create_import_and_run(["2026-04-09,Receipt rematch,REM001,,0,1500,2500"], closing="2500.00")
        journal1 = self._create_book_line(amount="1500.00", posting_date="2026-04-09", description="Wrong receipt", voucher_no="RV011", drcr=True, txn_id=21)
        journal2 = self._create_book_line(amount="1500.00", posting_date="2026-04-09", description="Correct receipt REM001", voucher_no="RV012", drcr=True, txn_id=22)
        line = statement_import.lines.first()
        self.client.post(reverse("bank_reco_api:bank-reco-match"), {"run_id": run.id, "bank_line_id": line.id, "journal_line_id": journal1.id}, format="json")
        match = BankReconciliationMatch.objects.get(run=run, book_lines__journal_line=journal1)
        unmatch_response = self.client.post(reverse("bank_reco_api:bank-reco-unmatch"), {"match_id": match.id}, format="json")
        self.assertEqual(unmatch_response.status_code, 200)
        rematch_response = self.client.post(reverse("bank_reco_api:bank-reco-match"), {"run_id": run.id, "bank_line_id": line.id, "journal_line_id": journal2.id}, format="json")
        self.assertEqual(rematch_response.status_code, 201)
        self.assertEqual(BankReconciliationMatch.objects.filter(run=run, status=BankReconciliationMatch.Status.CONFIRMED).count(), 1)

    def test_audit_log_creation_for_match_flow(self):
        statement_import, run = self._create_import_and_run(["2026-04-10,Audit receipt,AUD001,,0,2200,3200"], closing="3200.00")
        journal = self._create_book_line(amount="2200.00", posting_date="2026-04-10", description="Audit receipt AUD001", voucher_no="RV013", drcr=True, txn_id=23)
        line = statement_import.lines.first()
        self.client.post(reverse("bank_reco_api:bank-reco-match"), {"run_id": run.id, "bank_line_id": line.id, "journal_line_id": journal.id}, format="json")
        self.assertTrue(BankReconciliationAuditLog.objects.filter(run=run, action="manual_match_confirmed").exists())

    def test_audit_trail_captures_import_match_unmatch_user_and_scope(self):
        statement_import, run = self._create_import_and_run(
            ["2026-04-10,Audit scope receipt,AUDSCOPE,,0,2200,3200"],
            closing="3200.00",
            subentity=self.subentity,
        )
        import_log = BankReconciliationAuditLog.objects.get(statement_import=statement_import, action="import_created")
        self.assertEqual(import_log.actor_id, self.user.id)
        self.assertEqual(import_log.statement_import.entity_id, self.entity.id)
        self.assertEqual(import_log.statement_import.entityfin_id, self.entityfin.id)
        self.assertEqual(import_log.statement_import.subentity_id, self.subentity.id)

        journal = self._create_book_line(
            amount="2200.00",
            posting_date="2026-04-10",
            description="Audit scoped receipt AUDSCOPE",
            voucher_no="RV013A",
            drcr=True,
            subentity=self.subentity,
            txn_id=2301,
        )
        line = statement_import.lines.first()
        match_response = self.client.post(
            reverse("bank_reco_api:bank-reco-match"),
            {"run_id": run.id, "bank_line_id": line.id, "journal_line_id": journal.id},
            format="json",
        )
        self.assertEqual(match_response.status_code, 201, match_response.json())
        match = BankReconciliationMatch.objects.get(run=run)

        unmatch_response = self.client.post(reverse("bank_reco_api:bank-reco-unmatch"), {"match_id": match.id}, format="json")
        self.assertEqual(unmatch_response.status_code, 200, unmatch_response.json())

        audit_trail = self.client.get(
            reverse("bank_reco_api:bank-reco-report-audit-trail"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "run_id": run.id, "action": "unmatched"},
        )
        self.assertEqual(audit_trail.status_code, 200, audit_trail.json())
        self.assertEqual(audit_trail.json()["count"], 1)
        row = audit_trail.json()["results"][0]
        self.assertEqual(row["action"], "unmatched")
        self.assertEqual(row["actor"], self.user.username)
        self.assertEqual(run.entity_id, self.entity.id)
        self.assertEqual(run.entityfin_id, self.entityfin.id)
        self.assertEqual(run.subentity_id, self.subentity.id)

    def test_duplicate_match_prevention(self):
        statement_import, run = self._create_import_and_run(["2026-04-11,Dup receipt,DUP001,,0,1800,2800"], closing="2800.00")
        journal = self._create_book_line(amount="1800.00", posting_date="2026-04-11", description="Dup receipt", voucher_no="RV014", drcr=True, txn_id=24)
        line = statement_import.lines.first()
        self.client.post(reverse("bank_reco_api:bank-reco-match"), {"run_id": run.id, "bank_line_id": line.id, "journal_line_id": journal.id}, format="json")
        second = self.client.post(reverse("bank_reco_api:bank-reco-match"), {"run_id": run.id, "bank_line_id": line.id, "journal_line_id": journal.id}, format="json")
        self.assertEqual(second.status_code, 400)

    def test_cross_entity_protection(self):
        statement_import, run = self._create_import_and_run(["2026-04-12,Foreign attempt,X001,,0,2100,3100"], closing="3100.00")
        foreign_journal = self._create_book_line(
            amount="2100.00",
            posting_date="2026-04-12",
            description="Foreign receipt",
            voucher_no="RV015",
            drcr=True,
            book_account=self.foreign_account,
            entity=self.other_entity,
            entityfin=self.other_entityfin,
            txn_id=25,
        )
        line = statement_import.lines.first()
        response = self.client.post(reverse("bank_reco_api:bank-reco-match"), {"run_id": run.id, "bank_line_id": line.id, "journal_line_id": foreign_journal.id}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_wrong_bank_ledger_protection(self):
        statement_import, run = self._create_import_and_run(["2026-04-13,Wrong bank ledger,WBL001,,0,2400,3400"], closing="3400.00")
        wrong_journal = self._create_book_line(
            amount="2400.00",
            posting_date="2026-04-13",
            description="Wrong bank ledger receipt",
            voucher_no="RV016",
            drcr=True,
            book_account=self.other_bank_book_account,
            txn_id=26,
        )
        line = statement_import.lines.first()
        response = self.client.post(reverse("bank_reco_api:bank-reco-match"), {"run_id": run.id, "bank_line_id": line.id, "journal_line_id": wrong_journal.id}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_workspace_returns_suggested_matches_and_unmatched_rows(self):
        statement_import, run = self._create_import_and_run(["2026-04-14,Workspace receipt,,,0,2600,3600"], closing="3600.00")
        self._create_book_line(amount="2600.00", posting_date="2026-04-16", description="Workspace receipt", voucher_no="RV017", drcr=True, txn_id=27)
        self.client.post(reverse("bank_reco_api:bank-reco-import-auto-match", args=[statement_import.id]))
        response = self.client.get(reverse("bank_reco_api:bank-reco-workspace"), {"entity": self.entity.id, "entityfinid": self.entityfin.id, "import_id": statement_import.id})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["run"]["id"], run.id)
        self.assertTrue(len(payload["suggested_matches"]) >= 1)

    def test_workspace_and_brs_respect_run_scope_for_entityfin_subentity_and_bank_account(self):
        statement_import, run = self._create_import_and_run(
            ["2026-04-14,Scoped workspace receipt,SC001,,0,2600,3600"],
            closing="3600.00",
            subentity=self.subentity,
        )
        scoped_line = self._create_book_line(
            amount="2600.00",
            posting_date="2026-04-14",
            description="Scoped workspace receipt SC001",
            voucher_no="RV017A",
            drcr=True,
            subentity=self.subentity,
            txn_id=2701,
        )
        excluded_subentity_line = self._create_book_line(
            amount="999.00",
            posting_date="2026-04-14",
            description="Different subentity line should stay out",
            voucher_no="RV017B",
            drcr=True,
            subentity=self.other_subentity,
            txn_id=2702,
        )
        excluded_fy_line = self._create_book_line(
            amount="777.00",
            posting_date="2027-04-14",
            description="Different FY line should stay out",
            voucher_no="RV017C",
            drcr=True,
            entityfin=self.other_entityfin,
            subentity=self.subentity,
            txn_id=2703,
        )
        excluded_bank_line = self._create_book_line(
            amount="888.00",
            posting_date="2026-04-14",
            description="Different bank binding should stay out",
            voucher_no="RV017E",
            drcr=True,
            book_account=self.other_bank_book_account,
            subentity=self.subentity,
            txn_id=2705,
        )

        workspace = self.client.get(
            reverse("bank_reco_api:bank-reco-workspace"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "import_id": statement_import.id},
        )
        self.assertEqual(workspace.status_code, 200, workspace.json())
        payload = workspace.json()
        self.assertEqual(payload["import"]["id"], statement_import.id)
        self.assertEqual(payload["run"]["id"], run.id)
        self.assertEqual(len(payload["unmatched_bank_lines"]), 1)
        journal_line_ids = {row["journal_line_id"] for row in payload["unmatched_book_lines"]}
        self.assertIn(scoped_line.id, journal_line_ids)
        self.assertNotIn(excluded_subentity_line.id, journal_line_ids)
        self.assertNotIn(excluded_fy_line.id, journal_line_ids)
        self.assertNotIn(excluded_bank_line.id, journal_line_ids)

        run.as_of_date = datetime(2026, 4, 14).date()
        run.save(update_fields=["as_of_date", "updated_at"])
        self._create_book_line(
            amount="555.00",
            posting_date="2026-04-20",
            description="After as-of should be excluded",
            voucher_no="RV017D",
            drcr=True,
            subentity=self.subentity,
            txn_id=2704,
        )
        brs = self.client.get(
            reverse("bank_reco_api:bank-reco-report-brs"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "run_id": run.id},
        )
        self.assertEqual(brs.status_code, 200, brs.json())
        export_labels = [row["Section"] for row in brs.json()["export_rows"]]
        section_labels = [row["label"] for row in brs.json()["sections"]]
        self.assertEqual(export_labels, section_labels)
        self.assertEqual(brs.json()["supporting_rows"]["unmatched_bank_count"], 1)

    def test_bank_charges_voucher_creation_posts_and_auto_matches(self):
        statement_import, run = self._create_import_and_run(["2026-04-15,Bank charges,BC001,,120.00,0,3480"], closing="3480.00")
        line = statement_import.lines.first()
        response = self.client.post(
            reverse("bank_reco_api:bank-reco-create-voucher-from-bank-line"),
            {
                "run_id": run.id,
                "bank_line_id": line.id,
                "voucher_kind": "bank_charges",
                "counterpart_account_id": self.bank_charges_account.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.json())
        line.refresh_from_db()
        self.assertEqual(line.reconciliation_status, BankStatementLine.ReconciliationStatus.CONFIRMED)
        self.assertIsNotNone(line.created_voucher_id)
        header = VoucherHeader.objects.get(pk=line.created_voucher_id)
        self.assertEqual(int(header.status), int(VoucherHeader.Status.POSTED))
        self.assertTrue(BankReconciliationAuditLog.objects.filter(run=run, action="voucher_created_from_bank_line").exists())

    def test_interest_received_voucher_creation(self):
        statement_import, run = self._create_import_and_run(["2026-04-16,Interest credit,INT001,,0,75.00,3555"], closing="3555.00")
        line = statement_import.lines.first()
        response = self.client.post(
            reverse("bank_reco_api:bank-reco-create-voucher-from-bank-line"),
            {
                "run_id": run.id,
                "bank_line_id": line.id,
                "voucher_kind": "interest_received",
                "counterpart_account_id": self.interest_income_account.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.json())
        line.refresh_from_db()
        self.assertEqual(line.reconciliation_status, BankStatementLine.ReconciliationStatus.CONFIRMED)

    def test_direct_customer_receipt_voucher_creation(self):
        statement_import, run = self._create_import_and_run(["2026-04-17,Direct customer receipt,RC001,,0,2500,6055"], closing="6055.00")
        line = statement_import.lines.first()
        response = self.client.post(
            reverse("bank_reco_api:bank-reco-create-voucher-from-bank-line"),
            {
                "run_id": run.id,
                "bank_line_id": line.id,
                "voucher_kind": "direct_customer_receipt",
                "counterpart_account_id": self.customer_account.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.json())

    def test_direct_vendor_payment_voucher_creation(self):
        statement_import, run = self._create_import_and_run(["2026-04-18,Direct vendor payment,PV001,,800.00,0,5255"], closing="5255.00")
        line = statement_import.lines.first()
        response = self.client.post(
            reverse("bank_reco_api:bank-reco-create-voucher-from-bank-line"),
            {
                "run_id": run.id,
                "bank_line_id": line.id,
                "voucher_kind": "direct_vendor_payment",
                "counterpart_account_id": self.vendor_account.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_bank_transfer_voucher_creation(self):
        statement_import, run = self._create_import_and_run(["2026-04-19,Bank transfer,TR001,,1500.00,0,3755"], closing="3755.00")
        line = statement_import.lines.first()
        response = self.client.post(
            reverse("bank_reco_api:bank-reco-create-voucher-from-bank-line"),
            {
                "run_id": run.id,
                "bank_line_id": line.id,
                "voucher_kind": "bank_transfer",
                "counterpart_account_id": self.transfer_account.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_tax_and_loan_voucher_creation_variants(self):
        scenarios = [
            ("loan_emi", self.loan_emi_account, "2026-04-20,Loan EMI,EMI001,,3000.00,0,2000", "5000.00", "2000.00"),
            ("gst_payment", self.gst_payable_account, "2026-04-21,GST payment,GST001,,500.00,0,4500", "5000.00", "4500.00"),
            ("tds_payment", self.tds_payable_account, "2026-04-22,TDS payment,TDS001,,200.00,0,4800", "5000.00", "4800.00"),
            ("tcs_payment", self.tcs_payable_account, "2026-04-23,TCS payment,TCS001,,55.00,0,4945", "5000.00", "4945.00"),
        ]
        for voucher_kind, counterpart, line_csv, opening, closing in scenarios:
            statement_import, run = self._create_import_and_run([line_csv], opening=opening, closing=closing)
            line = statement_import.lines.first()
            response = self.client.post(
                reverse("bank_reco_api:bank-reco-create-voucher-from-bank-line"),
                {
                    "run_id": run.id,
                    "bank_line_id": line.id,
                    "voucher_kind": voucher_kind,
                    "counterpart_account_id": counterpart.id,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.json())

    def test_cheque_bounce_and_reversal_adjustment_voucher_creation(self):
        for voucher_kind, counterpart, row, opening, closing in [
            ("cheque_bounce", self.customer_account, "2026-04-24,Cheque bounce,CB001,CHQ777,900.00,0,100", "1000.00", "100.00"),
            ("reversal_adjustment", self.transfer_account, "2026-04-25,Reversal adjustment,REV001,,0,900.00,1900", "1000.00", "1900.00"),
        ]:
            statement_import, run = self._create_import_and_run([row], opening=opening, closing=closing)
            line = statement_import.lines.first()
            response = self.client.post(
                reverse("bank_reco_api:bank-reco-create-voucher-from-bank-line"),
                {
                    "run_id": run.id,
                    "bank_line_id": line.id,
                    "voucher_kind": voucher_kind,
                    "counterpart_account_id": counterpart.id,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.json())

    def test_create_voucher_from_bank_line_rejects_oversized_fields(self):
        statement_import, run = self._create_import_and_run(
            ["2026-04-26,Bank charges oversized,BC001,,50.00,0,950"],
            closing="950.00",
        )
        line = statement_import.lines.first()
        response = self.client.post(
            reverse("bank_reco_api:bank-reco-create-voucher-from-bank-line"),
            {
                "run_id": run.id,
                "bank_line_id": line.id,
                "voucher_kind": "bank_charges",
                "counterpart_account_id": self.bank_charges_account.id,
                "reference_number": "R" * 101,
                "instrument_no": "I" * 51,
                "allocations": [
                    {
                        "counterpart_account_id": self.bank_charges_account.id,
                        "amount": "50.00",
                        "narration": "N" * 256,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("reference_number", payload)
        self.assertIn("instrument_no", payload)
        self.assertIn("allocations", payload)

    def test_duplicate_voucher_creation_prevention(self):
        statement_import, run = self._create_import_and_run(["2026-04-26,Bank charges duplicate,BC002,,50.00,0,950"], closing="950.00")
        line = statement_import.lines.first()
        payload = {
            "run_id": run.id,
            "bank_line_id": line.id,
            "voucher_kind": "bank_charges",
            "counterpart_account_id": self.bank_charges_account.id,
        }
        first = self.client.post(reverse("bank_reco_api:bank-reco-create-voucher-from-bank-line"), payload, format="json")
        self.assertEqual(first.status_code, 201, first.json())
        second = self.client.post(reverse("bank_reco_api:bank-reco-create-voucher-from-bank-line"), payload, format="json")
        self.assertEqual(second.status_code, 400)

    def test_mark_bank_and_book_error_ignore_hold_and_pending_clearance(self):
        statement_import, run = self._create_import_and_run(["2026-04-27,Exception line,EX001,,0,400,1400"], closing="1400.00")
        line = statement_import.lines.first()
        for action, expected in [
            ("mark_as_bank_error", BankStatementLine.ExceptionStatus.BANK_ERROR),
            ("mark_as_book_error", BankStatementLine.ExceptionStatus.BOOK_ERROR),
            ("hold_for_review", BankStatementLine.ExceptionStatus.HOLD_FOR_REVIEW),
            ("mark_as_pending_clearance", BankStatementLine.ExceptionStatus.PENDING_CLEARANCE),
            ("ignore", BankStatementLine.ExceptionStatus.IGNORED),
        ]:
            response = self.client.post(
                reverse("bank_reco_api:bank-reco-exception-action"),
                {"run_id": run.id, "bank_line_id": line.id, "action": action, "reason": action},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            line.refresh_from_db()
            self.assertEqual(line.exception_status, expected)
        self.assertTrue(BankReconciliationAuditLog.objects.filter(run=run, action="mark_as_bank_error").exists())
        self.assertTrue(BankReconciliationAuditLog.objects.filter(run=run, action="ignore").exists())

    def test_unmatched_reports_audit_brs_and_opening_items(self):
        previous_import, previous_run = self._create_import_and_run(["2026-04-01,Opening bank line,OPEN1,,0,1000,2000"], opening="1000.00", closing="2000.00")
        current_import, current_run = self._create_import_and_run(["2026-04-30,Current line,CURR1,,0,500,2500"], opening="2000.00", closing="2500.00")
        self._create_book_line(amount="200.00", posting_date="2026-03-31", description="Cheque deposit not cleared CHQDEP", voucher_no="RV018", drcr=True, txn_id=28)
        self._create_book_line(amount="300.00", posting_date="2026-04-29", description="Cheque issued not presented CHQISS", voucher_no="RV019", drcr=False, txn_id=29)
        prev_line = previous_import.lines.first()
        self.client.post(
            reverse("bank_reco_api:bank-reco-exception-action"),
            {"run_id": current_run.id, "bank_line_id": prev_line.id, "action": "mark_as_book_error", "reason": "carry forward"},
            format="json",
        )
        unmatched_bank = self.client.get(reverse("bank_reco_api:bank-reco-report-unmatched-bank"), {"entity": self.entity.id, "entityfinid": self.entityfin.id, "run_id": current_run.id})
        self.assertEqual(unmatched_bank.status_code, 200)
        self.assertTrue(any(row["is_opening_item"] for row in unmatched_bank.json()["results"]))
        self.assertIn("totals", unmatched_bank.json())
        self.assertIn("export_rows", unmatched_bank.json())
        self.assertEqual(unmatched_bank.json()["bank_account"]["id"], current_run.bank_account_id)
        unmatched_books = self.client.get(reverse("bank_reco_api:bank-reco-report-unmatched-books"), {"entity": self.entity.id, "entityfinid": self.entityfin.id, "run_id": current_run.id})
        self.assertEqual(unmatched_books.status_code, 200)
        self.assertTrue(any(row["is_opening_item"] for row in unmatched_books.json()["results"]))
        self.assertIn("totals", unmatched_books.json())
        self.assertEqual(unmatched_books.json()["bank_account"]["id"], current_run.bank_account_id)
        audit_trail = self.client.get(reverse("bank_reco_api:bank-reco-report-audit-trail"), {"entity": self.entity.id, "entityfinid": self.entityfin.id, "run_id": current_run.id})
        self.assertEqual(audit_trail.status_code, 200)
        self.assertTrue(audit_trail.json()["count"] >= 1)
        self.assertIn("export_rows", audit_trail.json())
        self.assertEqual(audit_trail.json()["bank_account"]["id"], current_run.bank_account_id)
        brs = self.client.get(reverse("bank_reco_api:bank-reco-report-brs"), {"entity": self.entity.id, "entityfinid": self.entityfin.id, "run_id": current_run.id})
        self.assertEqual(brs.status_code, 200)
        self.assertIn("balance_as_per_books", brs.json())
        self.assertIn("sections", brs.json())
        self.assertIn("export_rows", brs.json())
        self.assertEqual(brs.json()["bank_account"]["id"], current_run.bank_account_id)
