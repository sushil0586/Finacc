from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
from financial.models import Ledger, account, accountHead, accounttype
from financial.services_opening_balance import account_opening_txn_id
from financial.services import apply_normalized_profile_payload, create_account_with_synced_ledger
from geography.models import City, Country, District, State
from payments.models.payment_core import PaymentVoucherHeader
from posting.models import Entry, EntryStatus, PostingBatch, JournalLine, StaticAccount, EntityStaticAccountMap, TxnType
from purchase.models.purchase_core import PurchaseInvoiceHeader, PurchaseInvoiceLine
from receipts.models.receipt_core import ReceiptVoucherHeader
from sales.models.sales_core import SalesInvoiceHeader, SalesInvoiceLine
from vouchers.models.voucher_core import VoucherHeader


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class BookReportAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="reportuser", email="report@example.com", password="pass123")
        self.permission_codes_patch = patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=[
                "reports.financial_hub.trial_balance.view",
                "reports.financial_hub.ledger_book.view",
                "reports.financial_hub.ledger_summary.view",
                "reports.financial_hub.profit_loss.view",
                "reports.financial_hub.balance_sheet.view",
                "reports.financial_hub.trading_account.view",
                "reports.financial_hub.daybook.view",
                "reports.financial_hub.cashbook.view",
            ],
        )
        self.permission_codes_patch.start()
        self.addCleanup(self.permission_codes_patch.stop)
        self.client.force_authenticate(user=self.user)
        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="State", statecode="ST", country=self.country)
        self.district = District.objects.create(districtname="District", districtcode="DT", state=self.state)
        self.city = City.objects.create(cityname="City", citycode="CT", pincode="123456", distt=self.district)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Finacc Test Entity",
            legalname="Finacc Test Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch A")
        self.other_subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch B")
        fy_start = timezone.make_aware(datetime(2025, 4, 1))
        fy_end = timezone.make_aware(datetime(2026, 3, 31))
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=fy_start,
            finendyear=fy_end,
            createdby=self.user,
        )
        self.other_entity = Entity.objects.create(
            entityname="Other Entity",
            legalname="Other Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.other_entityfin = EntityFinancialYear.objects.create(
            entity=self.other_entity,
            desc="FY 2025-26",
            finstartyear=fy_start,
            finendyear=fy_end,
            createdby=self.user,
        )
        self.acc_type = accounttype.objects.create(entity=self.entity, accounttypename="Assets", accounttypecode="A100", createdby=self.user)
        self.head_cash = accountHead.objects.create(
            entity=self.entity,
            name="Cash Head",
            code=100,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.head_bank = accountHead.objects.create(
            entity=self.entity,
            name="Bank Head",
            code=101,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.head_expense = accountHead.objects.create(
            entity=self.entity,
            name="Expense Head",
            code=200,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.head_income = accountHead.objects.create(
            entity=self.entity,
            name="Income Head",
            code=300,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.cash_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1001, name="Cash In Hand", accounthead=self.head_cash, openingbdr=Decimal("100.00"), createdby=self.user)
        self.bank_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1002, name="Main Bank", accounthead=self.head_bank, openingbdr=Decimal("200.00"), createdby=self.user)
        self.expense_ledger = Ledger.objects.create(entity=self.entity, ledger_code=2001, name="Office Expense", accounthead=self.head_expense, createdby=self.user)
        self.income_ledger = Ledger.objects.create(entity=self.entity, ledger_code=3001, name="Sales Income", accounthead=self.head_income, createdby=self.user)
        self.cash_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": self.cash_ledger, "accountname": "Cash In Hand", "createdby": self.user},
            ledger_overrides={"ledger_code": 1001, "accounthead": self.head_cash, "is_party": True},
        )
        self.bank_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": self.bank_ledger, "accountname": "Main Bank", "createdby": self.user},
            ledger_overrides={"ledger_code": 1002, "accounthead": self.head_bank, "is_party": True},
        )
        apply_normalized_profile_payload(
            self.bank_account,
            compliance_data={},
            commercial_data={"partytype": "Bank"},
            primary_address_data={},
        )
        self.expense_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": self.expense_ledger, "accountname": "Office Expense", "createdby": self.user},
            ledger_overrides={"ledger_code": 2001, "accounthead": self.head_expense, "is_party": True},
        )
        self.income_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": self.income_ledger, "accountname": "Sales Income", "createdby": self.user},
            ledger_overrides={"ledger_code": 3001, "accounthead": self.head_income, "is_party": True},
        )
        self.ap_ledger = Ledger.objects.create(entity=self.entity, ledger_code=4001, name="Sundry Creditors", accounthead=self.head_bank, createdby=self.user)
        self.ap_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": self.ap_ledger, "accountname": "Sundry Creditors", "createdby": self.user},
            ledger_overrides={"ledger_code": 4001, "accounthead": self.head_bank, "is_party": True},
        )
        self.other_cash_ledger = Ledger.objects.create(entity=self.other_entity, ledger_code=9001, name="Other Cash", accounthead=self.head_cash, createdby=self.user)
        self.other_cash_account = create_account_with_synced_ledger(
            account_data={"entity": self.other_entity, "ledger": self.other_cash_ledger, "accountname": "Other Cash", "createdby": self.user},
            ledger_overrides={"ledger_code": 9001, "accounthead": self.head_cash, "is_party": True},
        )

        static_cash = StaticAccount.objects.create(code="CASH", name="Cash", group="CASH_BANK")
        static_bank = StaticAccount.objects.create(code="BANK_MAIN", name="Bank", group="CASH_BANK")
        EntityStaticAccountMap.objects.create(entity=self.entity, static_account=static_cash, account=self.cash_account, ledger=self.cash_ledger, createdby=self.user)
        EntityStaticAccountMap.objects.create(entity=self.entity, static_account=static_bank, account=self.bank_account, ledger=self.bank_ledger, createdby=self.user)
        self._create_entry(
            txn_type=TxnType.OPENING_BALANCE,
            txn_id=account_opening_txn_id(self.cash_account.id),
            voucher_no="ACC-OPEN-CASH",
            posting_date="2025-04-01",
            voucher_date="2025-04-01",
            status=EntryStatus.POSTED,
            narration="Opening balance for Cash In Hand",
            subentity=None,
            lines=[
                (self.cash_account, self.cash_ledger, True, "100.00", "Opening debit"),
                (self.income_account, self.income_ledger, False, "100.00", "Opening offset"),
            ],
        )
        self._create_entry(
            txn_type=TxnType.OPENING_BALANCE,
            txn_id=account_opening_txn_id(self.bank_account.id),
            voucher_no="ACC-OPEN-BANK",
            posting_date="2025-04-01",
            voucher_date="2025-04-01",
            status=EntryStatus.POSTED,
            narration="Opening balance for Main Bank",
            subentity=None,
            lines=[
                (self.bank_account, self.bank_ledger, True, "200.00", "Opening debit"),
                (self.income_account, self.income_ledger, False, "200.00", "Opening offset"),
            ],
        )
        self.cash_entry = self._create_entry(
            txn_type=TxnType.JOURNAL_CASH,
            txn_id=1,
            voucher_no="CV-001",
            posting_date="2025-04-05",
            voucher_date="2025-04-05",
            status=EntryStatus.POSTED,
            narration="Cash sale",
            subentity=self.subentity,
            lines=[
                (self.cash_account, self.cash_ledger, True, "50.00", "Cash received"),
                (self.income_account, self.income_ledger, False, "50.00", "Sales booked"),
            ],
        )
        VoucherHeader.objects.create(
            id=1,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_date="2025-04-05",
            voucher_code="CV-001",
            voucher_type=VoucherHeader.VoucherType.CASH,
            cash_bank_account=self.cash_account,
            cash_bank_ledger=self.cash_ledger,
            reference_number="REF-CASH-001",
            narration="Cash sale",
            status=VoucherHeader.Status.POSTED,
            created_by=self.user,
        )
        self.bank_entry = self._create_entry(
            txn_type=TxnType.JOURNAL_BANK,
            txn_id=2,
            voucher_no="BV-001",
            posting_date="2025-04-05",
            voucher_date="2025-04-05",
            status=EntryStatus.POSTED,
            narration="Bank expense",
            subentity=self.subentity,
            lines=[
                (self.expense_account, self.expense_ledger, True, "25.00", "Expense"),
                (self.bank_account, self.bank_ledger, False, "25.00", "Bank paid"),
            ],
        )
        VoucherHeader.objects.create(
            id=2,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_date="2025-04-05",
            voucher_code="BV-001",
            voucher_type=VoucherHeader.VoucherType.BANK,
            cash_bank_account=self.bank_account,
            cash_bank_ledger=self.bank_ledger,
            reference_number="REF-BANK-001",
            narration="Bank expense",
            status=VoucherHeader.Status.POSTED,
            created_by=self.user,
        )
        self.backdated_cash_entry = self._create_entry(
            txn_type=TxnType.RECEIPT,
            txn_id=3,
            voucher_no="RV-001",
            posting_date="2025-04-03",
            voucher_date="2025-04-03",
            status=EntryStatus.POSTED,
            narration="Customer receipt",
            subentity=self.subentity,
            lines=[
                (self.bank_account, self.bank_ledger, True, "40.00", "Receipt in bank"),
                (self.income_account, self.income_ledger, False, "40.00", "Customer settlement"),
            ],
        )
        ReceiptVoucherHeader.objects.create(
            id=3,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_date="2025-04-03",
            voucher_code="RV-001",
            received_in=self.bank_account,
            received_from=self.income_account,
            received_in_ledger=self.bank_ledger,
            received_from_ledger=self.income_ledger,
            cash_received_amount=Decimal("40.00"),
            reference_number="RCP-REF-001",
            narration="Customer receipt",
            status=ReceiptVoucherHeader.Status.POSTED,
            created_by=self.user,
        )
        self.draft_entry = self._create_entry(
            txn_type=TxnType.JOURNAL,
            txn_id=4,
            voucher_no="JV-001",
            posting_date="2025-04-06",
            voucher_date="2025-04-06",
            status=EntryStatus.DRAFT,
            narration="Draft journal",
            subentity=self.subentity,
            lines=[
                (self.expense_account, self.expense_ledger, True, "10.00", "Draft debit"),
                (self.income_account, self.income_ledger, False, "10.00", "Draft credit"),
            ],
        )
        self.reversed_entry = self._create_entry(
            txn_type=TxnType.PAYMENT,
            txn_id=5,
            voucher_no="PV-001",
            posting_date="2025-04-07",
            voucher_date="2025-04-07",
            status=EntryStatus.REVERSED,
            narration="Reversed payment",
            subentity=self.subentity,
            lines=[
                (self.expense_account, self.expense_ledger, True, "15.00", "Payment expense"),
                (self.cash_account, self.cash_ledger, False, "15.00", "Cash paid"),
            ],
        )
        PaymentVoucherHeader.objects.create(
            id=5,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_date="2025-04-07",
            voucher_code="PV-001",
            paid_from=self.cash_account,
            paid_from_ledger=self.cash_ledger,
            paid_to=self.expense_account,
            paid_to_ledger=self.expense_ledger,
            cash_paid_amount=Decimal("15.00"),
            reference_number="PAY-REF-001",
            narration="Reversed payment",
            status=PaymentVoucherHeader.Status.CANCELLED,
            is_cancelled=True,
            created_by=self.user,
        )
        self.other_entity_entry = self._create_entry(
            entity=self.other_entity,
            entityfin=self.other_entityfin,
            txn_type=TxnType.JOURNAL_CASH,
            txn_id=99,
            voucher_no="CV-999",
            posting_date="2025-04-05",
            voucher_date="2025-04-05",
            status=EntryStatus.POSTED,
            narration="Other entity cash",
            lines=[
                (self.other_cash_account, self.other_cash_ledger, True, "30.00", "Other cash"),
            ],
        )

    def _create_entry(self, *, entity=None, entityfin=None, subentity=None, txn_type, txn_id, voucher_no, posting_date, voucher_date, status, narration, lines):
        entity = entity or self.entity
        entityfin = entityfin or self.entityfin
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
            voucher_date=voucher_date,
            posting_date=posting_date,
            status=status,
            narration=narration,
            posting_batch=batch,
            created_by=self.user,
        )
        for idx, line in enumerate(lines, start=1):
            if isinstance(line, dict):
                acct = line["account"]
                ledger = getattr(acct, "ledger", None)
                drcr = line["drcr"]
                amount = line["amount"]
                description = line.get("description")
            else:
                acct, ledger, drcr, amount, description = line
            JournalLine.objects.create(
                entry=entry,
                posting_batch=batch,
                entity=entity,
                entityfin=entityfin,
                subentity=subentity,
                txn_type=txn_type,
                txn_id=txn_id,
                detail_id=idx,
                voucher_no=voucher_no,
                account=acct,
                ledger=ledger,
                drcr=drcr,
                amount=Decimal(amount),
                description=description,
                posting_date=posting_date,
                created_by=self.user,
            )
        return entry

    def test_daybook_happy_path_and_summary(self):
        response = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id, "from_date": "2025-04-01", "to_date": "2025-04-30"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        print("TB_PERIODS", data["periods"])
        self.assertTrue(data["balance_integrity"])
        self.assertEqual(data["mode"], "voucher_list")
        self.assertEqual(data["totals"]["transaction_count"], 4)
        self.assertEqual(data["totals"]["debit_total"], "125.00")
        self.assertEqual(data["totals"]["credit_total"], "125.00")
        self.assertEqual(data["count"], 4)
        self.assertIsNone(data["next"])
        self.assertIsNone(data["previous"])
        self.assertEqual(data["results"][0]["voucher_number"], "RV-001")
        self.assertEqual(data["results"][1]["voucher_number"], "CV-001")
        self.assertEqual([row["voucher_number"] for row in data["results"][:3]], ["RV-001", "CV-001", "BV-001"])

    def test_financial_meta_includes_daybook_cashbook_filter_support(self):
        response = self.client.get(reverse("reports_api:financial-meta"), {"entity": self.entity.id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        print("PL_PERIODS", data["periods"])
        self.assertIn("voucher_types", data)
        self.assertIn("daybook_voucher_types", data)
        self.assertIn("cashbook_voucher_types", data)
        self.assertIn("daybook_statuses", data)
        self.assertIn("all_accounts", data)
        self.assertIn("cash_accounts", data)
        self.assertIn("bank_accounts", data)
        self.assertIn("hub", data)
        self.assertIn("scope_contract", data)
        self.assertEqual(data["hub"]["default_report_code"], "trial_balance")
        self.assertEqual(data["scope_contract"]["default_scope_mode"], "financial_year")

        voucher_types = {row["code"]: row["name"] for row in data["voucher_types"]}
        self.assertEqual(voucher_types[TxnType.PAYMENT], "Payment Voucher")
        self.assertEqual(voucher_types[TxnType.RECEIPT], "Receipt Voucher")
        self.assertNotIn(TxnType.FIXED_ASSET_CAPITALIZATION, voucher_types)

        daybook_voucher_types = {row["code"] for row in data["daybook_voucher_types"]}
        cashbook_voucher_types = {row["code"] for row in data["cashbook_voucher_types"]}
        self.assertIn(TxnType.JOURNAL, daybook_voucher_types)
        self.assertIn(TxnType.PAYMENT, daybook_voucher_types)
        self.assertNotIn(TxnType.FIXED_ASSET_DISPOSAL, daybook_voucher_types)
        self.assertEqual(
            cashbook_voucher_types,
            {TxnType.JOURNAL_CASH, TxnType.JOURNAL_BANK, TxnType.RECEIPT, TxnType.PAYMENT},
        )

        statuses = {row["value"]: row["label"] for row in data["daybook_statuses"]}
        self.assertEqual(statuses, {"draft": "Draft", "posted": "Posted", "reversed": "Reversed"})

        report_codes = {row["code"] for row in data["reports"]}
        self.assertTrue({"trial_balance", "ledger_book", "ledger_summary", "profit_loss", "balance_sheet", "trading_account", "daybook", "cashbook"}.issubset(report_codes))
        self.assertEqual(
            [report["code"] for section in data["hub"]["sections"] for report in section["reports"]][:3],
            ["trial_balance", "ledger_book", "ledger_summary"],
        )

        all_accounts = {row["id"]: row for row in data["all_accounts"]}
        self.assertEqual(all_accounts[self.cash_account.id]["account_type"], "cash")
        self.assertEqual(all_accounts[self.bank_account.id]["account_type"], "bank")
        self.assertEqual(all_accounts[self.expense_account.id]["account_type"], "ledger")
        self.assertEqual(all_accounts[self.cash_account.id]["code"], self.cash_ledger.ledger_code)

        cash_ids = {row["id"] for row in data["cash_accounts"]}
        bank_ids = {row["id"] for row in data["bank_accounts"]}
        all_ids = {row["id"] for row in data["all_accounts"]}
        self.assertIn(self.cash_account.id, cash_ids)
        self.assertIn(self.bank_account.id, bank_ids)
        self.assertNotIn(self.other_cash_account.id, all_ids)

    def test_daybook_filters_voucher_type_status_posted_and_search(self):
        response = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id, "voucher_type": f"{TxnType.JOURNAL_BANK},{TxnType.PAYMENT}", "status": "posted", "posted": True, "search": "REF-BANK-001"})
        self.assertEqual(response.status_code, 200)
        rows = response.json()["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["voucher_number"], "BV-001")

    def test_daybook_search_matches_purchase_supplier_invoice_and_vendor_name(self):
        vendor_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=4101,
            name="Vendor Searchable",
            accounthead=self.head_bank,
            createdby=self.user,
        )
        vendor = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": vendor_ledger, "accountname": "Vendor Searchable", "createdby": self.user},
            ledger_overrides={"ledger_code": 4101, "accounthead": self.head_bank, "is_party": True},
        )
        purchase_document = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            created_by=self.user,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date=date(2025, 4, 11),
            posting_date=date(2025, 4, 11),
            doc_code="PINV",
            doc_no=88,
            purchase_number="PINV-SEARCH-88",
            supplier_invoice_number="SUP-SEARCH-88",
            vendor=vendor,
            vendor_name="Vendor Searchable",
        )
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=purchase_document.id,
            voucher_no="ENTRY-PUR-88",
            posting_date=date(2025, 4, 11),
            voucher_date=date(2025, 4, 11),
            status=EntryStatus.POSTED,
            narration="Purchase invoice posting",
            lines=[
                {"account": self.expense_account, "drcr": True, "amount": "50.00", "description": "Expense Dr"},
                {"account": self.ap_account, "drcr": False, "amount": "50.00", "description": "Payable Cr"},
            ],
        )

        supplier_response = self.client.get(
            reverse("reports_api:financial-daybook"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id, "search": "SUP-SEARCH-88"},
        )
        self.assertEqual(supplier_response.status_code, 200)
        self.assertEqual([row["voucher_number"] for row in supplier_response.json()["results"]], ["ENTRY-PUR-88"])

        vendor_response = self.client.get(
            reverse("reports_api:financial-daybook"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id, "search": "Vendor Searchable"},
        )
        self.assertEqual(vendor_response.status_code, 200)
        self.assertEqual([row["voucher_number"] for row in vendor_response.json()["results"]], ["ENTRY-PUR-88"])

    def test_daybook_search_matches_sales_customer_name(self):
        customer_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=4102,
            name="Customer Searchable",
            accounthead=self.head_cash,
            createdby=self.user,
        )
        customer = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": customer_ledger, "accountname": "Customer Searchable", "createdby": self.user},
            ledger_overrides={"ledger_code": 4102, "accounthead": self.head_cash, "is_party": True},
        )
        sales_document = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            created_by=self.user,
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date=date(2025, 4, 12),
            posting_date=date(2025, 4, 12),
            doc_code="SCN",
            doc_no=25,
            invoice_number="SCN-SEARCH-25",
            customer=customer,
            customer_name="Customer Searchable",
        )
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            txn_id=sales_document.id,
            voucher_no="ENTRY-SAL-25",
            posting_date=date(2025, 4, 12),
            voucher_date=date(2025, 4, 12),
            status=EntryStatus.POSTED,
            narration="Sales credit note posting",
            lines=[
                {"account": self.income_account, "drcr": True, "amount": "30.00", "description": "Revenue reversal"},
                {"account": self.cash_account, "drcr": False, "amount": "30.00", "description": "Receivable reversal"},
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-daybook"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id, "search": "Customer Searchable"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["voucher_number"] for row in response.json()["results"]], ["ENTRY-SAL-25"])

    def test_daybook_account_filter_and_scope_isolation(self):
        response = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id, "account": str(self.cash_account.id)})
        self.assertEqual(response.status_code, 200)
        vouchers = {row["voucher_number"] for row in response.json()["results"]}
        self.assertEqual(vouchers, {"CV-001"})
        self.assertNotIn("CV-999", vouchers)

    def test_daybook_pagination_keeps_totals_for_full_filtered_set(self):
        response = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id, "page": 1, "page_size": 2})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        print("BS_PERIODS", data["periods"])
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["count"], 4)
        self.assertEqual(data["totals"]["debit_total"], "125.00")
        self.assertIsNotNone(data["next"])
        self.assertIsNone(data["previous"])

    def test_daybook_detail_returns_journal_lines(self):
        response = self.client.get(reverse("reports_api:financial-daybook-detail", args=[self.cash_entry.id]), {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["voucher_number"], "CV-001")
        self.assertEqual(len(data["lines"]), 2)

    def test_daybook_invalid_filters_and_account_scope_validation(self):
        invalid_date = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id, "from_date": "2025-04-30", "to_date": "2025-04-01"})
        self.assertEqual(invalid_date.status_code, 400)
        invalid_account = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id, "account": str(self.other_cash_account.id)})
        self.assertEqual(invalid_account.status_code, 400)
        invalid_voucher_type = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id, "voucher_type": "BAD"})
        self.assertEqual(invalid_voucher_type.status_code, 400)
        invalid_posted = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id, "posted": "notabool"})
        self.assertEqual(invalid_posted.status_code, 400)

    def test_daybook_posted_filter_true_false_and_omitted(self):
        omitted = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id})
        only_posted = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id, "posted": True})
        non_posted = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id, "posted": False})
        self.assertEqual(omitted.status_code, 200)
        self.assertEqual(only_posted.status_code, 200)
        self.assertEqual(non_posted.status_code, 200)
        self.assertEqual(omitted.json()["count"], 4)
        self.assertEqual(only_posted.json()["count"], 3)
        self.assertEqual(non_posted.json()["count"], 1)

    def test_daybook_response_contract_and_nullability(self):
        data = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id}).json()
        self.assertIn("filters", data)
        self.assertIn("totals", data)
        self.assertIn("results", data)
        self.assertIsNone(data["opening_balance"])
        self.assertIsNone(data["closing_balance"])
        self.assertIsNone(data["running_balance_scope"])
        self.assertEqual(data["account_summaries"], [])
        first = data["results"][0]
        self.assertIsInstance(first["debit_total"], str)
        self.assertIn("entry_id", first)
        self.assertIn("txn_id", first)
        self.assertIn("drilldown_params", first)

    def test_daybook_envelope_exposes_ui_contract(self):
        response = self.client.get(
            reverse("reports_api:financial-daybook"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_code"], "daybook")
        self.assertEqual(data["report_name"], "Daybook")
        self.assertTrue(data["actions"]["can_view"])
        self.assertTrue(data["actions"]["can_export_excel"])
        self.assertTrue(data["actions"]["can_export_pdf"])
        self.assertTrue(data["actions"]["can_export_csv"])
        self.assertTrue(data["actions"]["can_drilldown"])
        self.assertTrue(data["actions"]["can_print"])
        self.assertEqual(
            data["available_exports"],
            ["excel", "pdf", "csv", "print", "excel_landscape", "excel_portrait", "pdf_landscape", "pdf_portrait"],
        )
        self.assertEqual(
            set(data["actions"]["export_urls"].keys()),
            {"excel", "pdf", "csv", "print", "excel_landscape", "excel_portrait", "pdf_landscape", "pdf_portrait"},
        )
        for key in ["excel", "pdf", "csv", "print", "excel_landscape", "excel_portrait", "pdf_landscape", "pdf_portrait"]:
            self.assertIn("entity=", data["actions"]["export_urls"][key])
            self.assertIn(f"entityfinid={self.entityfin.id}", data["actions"]["export_urls"][key])
            self.assertIn(f"subentity={self.subentity.id}", data["actions"]["export_urls"][key])
            self.assertIn("from_date=2025-04-01", data["actions"]["export_urls"][key])
            self.assertIn("to_date=2025-04-30", data["actions"]["export_urls"][key])

    def test_daybook_purchase_rows_use_purchase_invoice_drilldown(self):
        purchase_entry = self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=46,
            voucher_no="PI-PINV-1001",
            posting_date=date(2025, 4, 6),
            voucher_date=date(2025, 4, 6),
            status=EntryStatus.POSTED,
            narration="Purchase Invoice PI-PINV-1001",
            lines=[
                {"account": self.expense_account, "drcr": True, "amount": "25.00", "description": "Purchase Dr"},
                {"account": self.ap_account, "drcr": False, "amount": "25.00", "description": "Purchase Cr"},
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-daybook"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(response.status_code, 200)
        rows = [row for row in response.json()["results"] if row["entry_id"] == purchase_entry.id]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drilldown_target"], "purchase_invoice_detail")
        self.assertEqual(rows[0]["drilldown_params"]["id"], 46)
        self.assertEqual(rows[0]["txn_id"], 46)

    def test_daybook_purchase_service_rows_expose_service_invoice_route(self):
        purchase_document = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            created_by=self.user,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date=date(2025, 4, 7),
            posting_date=date(2025, 4, 7),
            doc_code="PSI",
            doc_no=47,
            purchase_number="PSI-47",
        )
        PurchaseInvoiceLine.objects.create(
            header=purchase_document,
            line_no=1,
            is_service=True,
            purchase_behavior="expense",
            product_desc="Consulting service",
        )
        purchase_entry = self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=purchase_document.id,
            voucher_no="PSI-47",
            posting_date=date(2025, 4, 7),
            voucher_date=date(2025, 4, 7),
            status=EntryStatus.POSTED,
            narration="Service purchase invoice PSI-47",
            lines=[
                {"account": self.expense_account, "drcr": True, "amount": "25.00", "description": "Purchase Dr"},
                {"account": self.ap_account, "drcr": False, "amount": "25.00", "description": "Purchase Cr"},
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-daybook"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(response.status_code, 200)
        rows = [row for row in response.json()["results"] if row["entry_id"] == purchase_entry.id]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drilldown_target"], "purchase_invoice_detail")
        self.assertEqual(rows[0]["drilldown_route"], "/purchaseserviceinvoice")

    def test_daybook_sales_service_rows_expose_service_invoice_route(self):
        sales_document = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            created_by=self.user,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date=date(2025, 4, 7),
            posting_date=date(2025, 4, 7),
            doc_code="SSI",
            doc_no=57,
            invoice_number="SSI-57",
        )
        SalesInvoiceLine.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=sales_document,
            line_no=1,
            is_service=True,
            hsn_sac_code="9983",
            qty=Decimal("1.000"),
            rate=Decimal("25.00"),
            taxable_value=Decimal("25.00"),
            line_total=Decimal("25.00"),
        )
        sales_entry = self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=sales_document.id,
            voucher_no="SSI-57",
            posting_date=date(2025, 4, 7),
            voucher_date=date(2025, 4, 7),
            status=EntryStatus.POSTED,
            narration="Service sales invoice SSI-57",
            lines=[
                {"account": self.cash_account, "drcr": True, "amount": "25.00", "description": "Receivable Dr"},
                {"account": self.income_account, "drcr": False, "amount": "25.00", "description": "Revenue Cr"},
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-daybook"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(response.status_code, 200)
        rows = [row for row in response.json()["results"] if row["entry_id"] == sales_entry.id]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drilldown_target"], "sales_invoice_detail")
        self.assertEqual(rows[0]["drilldown_route"], "/saleserviceinvoice")

    def test_ledger_book_purchase_service_rows_expose_service_invoice_route(self):
        purchase_document = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            created_by=self.user,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date=date(2025, 4, 8),
            posting_date=date(2025, 4, 8),
            doc_code="PSI",
            doc_no=48,
            purchase_number="PSI-48",
        )
        PurchaseInvoiceLine.objects.create(
            header=purchase_document,
            line_no=1,
            is_service=True,
            purchase_behavior="expense",
            product_desc="Legal service",
        )
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=purchase_document.id,
            voucher_no="PSI-48",
            posting_date=date(2025, 4, 8),
            voucher_date=date(2025, 4, 8),
            status=EntryStatus.POSTED,
            narration="Service purchase invoice PSI-48",
            lines=[
                {"account": self.expense_account, "drcr": True, "amount": "40.00", "description": "Expense Dr"},
                {"account": self.ap_account, "drcr": False, "amount": "40.00", "description": "AP Cr"},
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-ledger-book"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "ledger": self.expense_ledger.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        rows = [row for row in response.json()["rows"] if row["txn_id"] == purchase_document.id]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drilldown_target"], "purchase_invoice_detail")
        self.assertEqual(rows[0]["drilldown_route"], "/purchaseserviceinvoice")

    def test_ledger_book_sales_service_rows_expose_service_invoice_route(self):
        sales_document = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            created_by=self.user,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date=date(2025, 4, 8),
            posting_date=date(2025, 4, 8),
            doc_code="SSI",
            doc_no=58,
            invoice_number="SSI-58",
        )
        SalesInvoiceLine.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=sales_document,
            line_no=1,
            is_service=True,
            hsn_sac_code="9984",
            qty=Decimal("1.000"),
            rate=Decimal("40.00"),
            taxable_value=Decimal("40.00"),
            line_total=Decimal("40.00"),
        )
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=sales_document.id,
            voucher_no="SSI-58",
            posting_date=date(2025, 4, 8),
            voucher_date=date(2025, 4, 8),
            status=EntryStatus.POSTED,
            narration="Service sales invoice SSI-58",
            lines=[
                {"account": self.cash_account, "drcr": True, "amount": "40.00", "description": "Receivable Dr"},
                {"account": self.income_account, "drcr": False, "amount": "40.00", "description": "Revenue Cr"},
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-ledger-book"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "ledger": self.income_ledger.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        rows = [
            row
            for row in response.json()["rows"]
            if row["txn_id"] == sales_document.id and row["txn_type"] == TxnType.SALES
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drilldown_target"], "sales_invoice_detail")
        self.assertEqual(rows[0]["drilldown_route"], "/saleserviceinvoice")

    def test_ledger_book_financial_year_shows_posted_opening_as_normal_row(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-book"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "ledger": self.cash_ledger.id,
                "scope_mode": "financial_year",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["opening_balance"], "0.00")
        self.assertEqual(data["totals"]["closing_balance"], "150.00")
        self.assertEqual([row["voucher_number"] for row in data["rows"]], ["ACC-OPEN-CASH", "CV-001"])
        self.assertEqual(data["rows"][0]["voucher_type"], TxnType.OPENING_BALANCE)
        self.assertEqual(data["rows"][0]["running_balance"], "100.00")
        self.assertEqual(data["rows"][0]["drilldown_target"], "account_opening_detail")
        self.assertEqual(data["rows"][0]["drilldown_params"]["account_id"], self.cash_account.id)
        self.assertEqual(data["rows"][0]["drilldown_params"]["entry_id"], data["rows"][0]["entry_id"])

    def test_ledger_book_custom_scope_keeps_brought_forward_opening_separate(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-book"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "ledger": self.cash_ledger.id,
                "scope_mode": "custom",
                "from_date": "2025-04-05",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["opening_balance"], "100.00")
        self.assertEqual([row["voucher_number"] for row in data["rows"]], ["CV-001"])
        self.assertEqual(data["totals"]["closing_balance"], "150.00")

    def test_ledger_book_fixed_asset_rows_expose_asset_history_drilldown(self):
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.FIXED_ASSET_CAPITALIZATION,
            txn_id=901,
            voucher_no="FA-000001",
            posting_date=date(2025, 4, 9),
            voucher_date=date(2025, 4, 9),
            status=EntryStatus.POSTED,
            narration="Fixed asset capitalization",
            lines=[
                {"account": self.expense_account, "drcr": True, "amount": "250.00", "description": "Asset Dr"},
                {"account": self.ap_account, "drcr": False, "amount": "250.00", "description": "AP Cr"},
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-ledger-book"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "ledger": self.expense_ledger.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        rows = [row for row in response.json()["rows"] if row["voucher_number"] == "FA-000001"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drilldown_target"], "asset_history_detail")
        self.assertEqual(rows[0]["drilldown_params"]["asset_id"], 901)

    def test_posting_lookup_resolves_purchase_invoice_entry(self):
        purchase_document = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            created_by=self.user,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date=date(2025, 4, 9),
            posting_date=date(2025, 4, 9),
            doc_code="PINV",
            doc_no=101,
            purchase_number="PI-PINV-101",
        )
        purchase_entry = self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=purchase_document.id,
            voucher_no="PI-PINV-101",
            posting_date=date(2025, 4, 9),
            voucher_date=date(2025, 4, 9),
            status=EntryStatus.POSTED,
            narration="Purchase invoice posting",
            lines=[
                {"account": self.expense_account, "drcr": True, "amount": "80.00", "description": "Expense Dr"},
                {"account": self.ap_account, "drcr": False, "amount": "80.00", "description": "Payable Cr"},
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-posting-lookup"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "document_type": "purchase_invoice",
                "document_id": purchase_document.id,
                "source_module": "purchase",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["entry_id"], purchase_entry.id)
        self.assertEqual(data["txn_type"], TxnType.PURCHASE)
        self.assertEqual(data["source_module"], "purchase")

    def test_posting_lookup_resolves_sales_credit_note_entry(self):
        sales_credit_note = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            created_by=self.user,
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date=date(2025, 4, 10),
            posting_date=date(2025, 4, 10),
            doc_code="SCN",
            doc_no=14,
            invoice_number="SI-SCN-14",
        )
        credit_entry = self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            txn_id=sales_credit_note.id,
            voucher_no="SI-SCN-14",
            posting_date=date(2025, 4, 10),
            voucher_date=date(2025, 4, 10),
            status=EntryStatus.POSTED,
            narration="Sales credit note posting",
            lines=[
                {"account": self.income_account, "drcr": True, "amount": "30.00", "description": "Revenue reversal"},
                {"account": self.cash_account, "drcr": False, "amount": "30.00", "description": "Receivable reversal"},
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-posting-lookup"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "document_type": "credit_note",
                "document_id": sales_credit_note.id,
                "source_module": "sales",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["entry_id"], credit_entry.id)
        self.assertEqual(data["txn_type"], TxnType.SALES_CREDIT_NOTE)
        self.assertEqual(data["source_module"], "sales")

    def test_cashbook_happy_path_running_balance_and_opening(self):
        response = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "cash_account": str(self.cash_account.id), "from_date": "2025-04-01", "to_date": "2025-04-30"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["balance_integrity"])
        self.assertEqual(data["mode"], "single_account_detail")
        self.assertEqual(data["opening_balance"], "100.00")
        self.assertEqual(data["closing_balance"], "150.00")
        self.assertEqual(data["totals"]["receipt_total"], "50.00")
        self.assertEqual(data["totals"]["payment_total"], "0.00")
        self.assertEqual([row["voucher_number"] for row in data["results"]], ["CV-001"])
        self.assertEqual(data["results"][0]["running_balance"], "150.00")

    def test_cashbook_service_purchase_rows_expose_service_invoice_route(self):
        purchase_document = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            created_by=self.user,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date=date(2025, 4, 11),
            posting_date=date(2025, 4, 11),
            doc_code="PSI",
            doc_no=49,
            purchase_number="PSI-49",
        )
        PurchaseInvoiceLine.objects.create(
            header=purchase_document,
            line_no=1,
            is_service=True,
            purchase_behavior="expense",
            product_desc="Maintenance service",
        )
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=purchase_document.id,
            voucher_no="PSI-49",
            posting_date=date(2025, 4, 11),
            voucher_date=date(2025, 4, 11),
            status=EntryStatus.POSTED,
            narration="Service purchase via cashbook",
            lines=[
                {"account": self.expense_account, "drcr": True, "amount": "55.00", "description": "Service expense"},
                {"account": self.cash_account, "drcr": False, "amount": "55.00", "description": "Cash paid"},
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-cashbook"),
            {
                "entity": self.entity.id,
                "cash_account": str(self.cash_account.id),
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        rows = [
            row
            for row in response.json()["results"]
            if row["drilldown"]["txn_id"] == purchase_document.id
            and row["drilldown"]["txn_type"] == TxnType.PURCHASE
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drilldown"]["drilldown_route"], "/purchaseserviceinvoice")

    def test_cashbook_service_sales_rows_expose_service_invoice_route(self):
        sales_document = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            created_by=self.user,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date=date(2025, 4, 12),
            posting_date=date(2025, 4, 12),
            doc_code="SSI",
            doc_no=59,
            invoice_number="SSI-59",
        )
        SalesInvoiceLine.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=sales_document,
            line_no=1,
            is_service=True,
            hsn_sac_code="9985",
            qty=Decimal("1.000"),
            rate=Decimal("65.00"),
            taxable_value=Decimal("65.00"),
            line_total=Decimal("65.00"),
        )
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=sales_document.id,
            voucher_no="SSI-59",
            posting_date=date(2025, 4, 12),
            voucher_date=date(2025, 4, 12),
            status=EntryStatus.POSTED,
            narration="Service sales via cashbook",
            lines=[
                {"account": self.cash_account, "drcr": True, "amount": "65.00", "description": "Cash received"},
                {"account": self.income_account, "drcr": False, "amount": "65.00", "description": "Revenue"},
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-cashbook"),
            {
                "entity": self.entity.id,
                "cash_account": str(self.cash_account.id),
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        rows = [
            row
            for row in response.json()["results"]
            if row["drilldown"]["txn_id"] == sales_document.id
            and row["drilldown"]["txn_type"] == TxnType.SALES
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drilldown"]["drilldown_route"], "/saleserviceinvoice")

    def test_cashbook_bank_mode_uses_backdated_entry_for_opening(self):
        response = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "bank_account": str(self.bank_account.id), "from_date": "2025-04-05", "to_date": "2025-04-30"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mode"], "single_account_detail")
        self.assertEqual(data["opening_balance"], "240.00")
        self.assertEqual(data["closing_balance"], "215.00")
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["voucher_number"], "BV-001")

    def test_cashbook_multiple_accounts_returns_per_account_running_scope(self):
        response = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "cash_account": str(self.cash_account.id), "bank_account": str(self.bank_account.id), "from_date": "2025-04-01", "to_date": "2025-04-30"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mode"], "multi_account_summary")
        self.assertEqual(data["running_balance_scope"], "combined_accounts")
        self.assertEqual(data["opening_balance"], "300.00")
        self.assertEqual(data["closing_balance"], "365.00")
        self.assertEqual(len(data["account_summaries"]), 2)
        impacted = {row["account_impacted"]["name"] for row in data["results"]}
        self.assertEqual(impacted, {"Cash In Hand", "Main Bank"})
        self.assertEqual(
            [(row["voucher_number"], row["running_balance"]) for row in data["results"]],
            [("RV-001", "340.00"), ("CV-001", "390.00"), ("BV-001", "365.00")],
        )
        self.assertIn("combined post-transaction balance", data["balance_note"])

    def test_cashbook_filters_by_counter_account_and_search_disable_running_balance(self):
        response = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "cash_account": str(self.cash_account.id), "account": str(self.expense_account.id), "search": "PV-001"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        rows = data["results"]
        self.assertEqual(len(rows), 0)
        self.assertTrue(data["balance_integrity"])
        self.assertEqual(data["opening_balance"], "100.00")
        self.assertEqual(data["closing_balance"], "150.00")
        self.assertEqual(data["totals"]["receipt_total"], "0.00")
        self.assertEqual(data["totals"]["payment_total"], "0.00")
        self.assertEqual(data["totals"]["period_receipt_total"], "50.00")
        self.assertEqual(data["totals"]["period_payment_total"], "0.00")
        self.assertEqual(data["running_balance_scope"], "account")
        self.assertIn("Filtered views may omit intermediate rows", data["balance_note"])

    def test_cashbook_single_account_filtered_rows_still_show_true_running_balance(self):
        response = self.client.get(
            reverse("reports_api:financial-cashbook"),
            {
                "entity": self.entity.id,
                "cash_account": str(self.cash_account.id),
                "search": "CV-001",
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mode"], "multi_account_summary")
        self.assertEqual(data["running_balance_scope"], "account")
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["voucher_number"], "CV-001")
        self.assertEqual(data["results"][0]["running_balance"], "150.00")

    def test_cashbook_empty_results_and_pagination(self):
        response = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "cash_account": str(self.cash_account.id), "from_date": "2025-05-01", "to_date": "2025-05-31", "page": 1, "page_size": 1})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["totals"]["transaction_count"], 0)
        self.assertEqual(data["results"], [])
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["opening_balance"], "150.00")
        self.assertEqual(data["closing_balance"], "150.00")

    def test_cashbook_invalid_account_scope_and_date_validation(self):
        invalid_account = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "cash_account": str(self.other_cash_account.id)})
        self.assertEqual(invalid_account.status_code, 400)
        invalid_date = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "from_date": "2025-04-30", "to_date": "2025-04-01"})
        self.assertEqual(invalid_date.status_code, 400)
        invalid_voucher_type = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "voucher_type": "BAD"})
        self.assertEqual(invalid_voucher_type.status_code, 400)
        conflicting_mode = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "mode": "cash", "bank_account": str(self.bank_account.id)})
        self.assertEqual(conflicting_mode.status_code, 400)

    def test_cashbook_response_contract_and_account_summary_shape(self):
        data = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "cash_account": str(self.cash_account.id)}).json()
        self.assertIn("filters", data)
        self.assertIn("totals", data)
        self.assertIn("results", data)
        self.assertIn("balance_basis", data)
        self.assertIn("running_balance_scope", data)
        self.assertIsInstance(data["opening_balance"], str)
        self.assertIsInstance(data["closing_balance"], str)
        first = data["results"][0]
        self.assertIsInstance(first["receipt_amount"], str)
        self.assertIsInstance(first["payment_amount"], str)
        self.assertIn("journal_line_id", first)
        self.assertIn("drilldown", first)
        summary = data["account_summaries"][0]
        self.assertIn("account_id", summary)
        self.assertIn("opening_balance", summary)
        self.assertIn("closing_balance", summary)

    def test_cashbook_envelope_exposes_ui_contract(self):
        response = self.client.get(
            reverse("reports_api:financial-cashbook"),
            {
                "entity": self.entity.id,
                "cash_account": str(self.cash_account.id),
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_code"], "cashbook")
        self.assertEqual(data["report_name"], "Cashbook")
        self.assertTrue(data["actions"]["can_view"])
        self.assertTrue(data["actions"]["can_export_excel"])
        self.assertTrue(data["actions"]["can_export_pdf"])
        self.assertTrue(data["actions"]["can_export_csv"])
        self.assertTrue(data["actions"]["can_drilldown"])
        self.assertTrue(data["actions"]["can_print"])
        self.assertEqual(
            data["available_exports"],
            ["excel", "pdf", "csv", "print", "excel_landscape", "excel_portrait", "pdf_landscape", "pdf_portrait"],
        )
        self.assertEqual(
            set(data["actions"]["export_urls"].keys()),
            {"excel", "pdf", "csv", "print", "excel_landscape", "excel_portrait", "pdf_landscape", "pdf_portrait"},
        )
        for key in ["excel", "pdf", "csv", "print", "excel_landscape", "excel_portrait", "pdf_landscape", "pdf_portrait"]:
            self.assertIn("entity=", data["actions"]["export_urls"][key])
            self.assertIn(f"cash_account={self.cash_account.id}", data["actions"]["export_urls"][key])
            self.assertIn(f"entityfinid={self.entityfin.id}", data["actions"]["export_urls"][key])
            self.assertIn(f"subentity={self.subentity.id}", data["actions"]["export_urls"][key])
            self.assertIn("from_date=2025-04-01", data["actions"]["export_urls"][key])
            self.assertIn("to_date=2025-04-30", data["actions"]["export_urls"][key])

    def test_trial_balance_totals_match_posted_ledger_movements(self):
        response = self.client.get(
            reverse("reports_api:financial-trial-balance"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "scope_mode": "custom",
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "group_by": "ledger",
                "posted_only": True,
                "include_opening": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        rows = {row["ledger_name"]: row for row in data["rows"]}
        self.assertEqual(Decimal(str(data["totals"]["debit"])), Decimal("115.00"))
        self.assertEqual(Decimal(str(data["totals"]["credit"])), Decimal("115.00"))
        self.assertEqual(Decimal(str(data["totals"]["closing"])), Decimal("390.00"))

        self.assertEqual(Decimal(str(rows["Cash In Hand"]["opening"])), Decimal("100.00"))
        self.assertEqual(Decimal(str(rows["Cash In Hand"]["debit"])), Decimal("50.00"))
        self.assertEqual(Decimal(str(rows["Cash In Hand"]["credit"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(rows["Cash In Hand"]["closing"])), Decimal("150.00"))

        self.assertEqual(Decimal(str(rows["Main Bank"]["opening"])), Decimal("200.00"))
        self.assertEqual(Decimal(str(rows["Main Bank"]["debit"])), Decimal("40.00"))
        self.assertEqual(Decimal(str(rows["Main Bank"]["credit"])), Decimal("25.00"))
        self.assertEqual(Decimal(str(rows["Main Bank"]["closing"])), Decimal("215.00"))

        self.assertEqual(Decimal(str(rows["Office Expense"]["debit"])), Decimal("25.00"))
        self.assertEqual(Decimal(str(rows["Sales Income"]["credit"])), Decimal("90.00"))

    def test_trial_balance_financial_year_hides_opening_values_by_default(self):
        response = self.client.get(
            reverse("reports_api:financial-trial-balance"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "scope_mode": "financial_year",
                "group_by": "ledger",
                "posted_only": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        rows = {row["ledger_name"]: row for row in data["rows"]}
        self.assertEqual(Decimal(str(data["totals"]["opening"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(rows["Cash In Hand"]["opening"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(rows["Cash In Hand"]["closing"])), Decimal("150.00"))

    def test_trial_balance_prefers_posted_opening_balance_over_legacy_master_opening(self):
        self.cash_ledger.openingbdr = Decimal("999.00")
        self.cash_ledger.save(update_fields=["openingbdr"])
        self._create_entry(
            txn_type=TxnType.OPENING_BALANCE,
            txn_id=account_opening_txn_id(self.cash_account.id),
            voucher_no="ACC-OPEN-CASH",
            posting_date="2025-04-01",
            voucher_date="2025-04-01",
            status=EntryStatus.POSTED,
            narration="Opening balance for Cash In Hand",
            subentity=None,
            lines=[
                (self.cash_account, self.cash_ledger, True, "100.00", "Opening debit"),
                (self.income_account, self.income_ledger, False, "100.00", "Opening offset"),
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-trial-balance"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "scope_mode": "custom",
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "group_by": "ledger",
                "include_opening": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        cash_row = next(row for row in rows if row["ledger_id"] == self.cash_ledger.id)
        self.assertEqual(cash_row["opening"], "100.00")

    def test_trial_balance_ignores_legacy_opening_without_posted_entry(self):
        orphan_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=9901,
            name="Legacy Opening Only",
            accounthead=self.head_cash,
            openingbdr=Decimal("500.00"),
            createdby=self.user,
        )
        orphan_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": orphan_ledger, "accountname": "Legacy Opening Only", "createdby": self.user},
            ledger_overrides={"ledger_code": 9901, "accounthead": self.head_cash, "is_party": True},
        )

        response = self.client.get(
            reverse("reports_api:financial-trial-balance"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "group_by": "ledger", "include_zero_balances": True},
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        orphan_row = next(row for row in rows if row["ledger_id"] == orphan_ledger.id)
        self.assertEqual(orphan_row["opening"], "0.00")
        self.assertEqual(orphan_row["closing"], "0.00")

    def test_trial_balance_includes_posted_opening_only_ledgers_in_rows_and_totals(self):
        opening_only_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=9902,
            name="Posted Opening Only",
            accounthead=self.head_cash,
            openingbdr=Decimal("500.00"),
            createdby=self.user,
        )
        opening_only_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": opening_only_ledger, "accountname": "Posted Opening Only", "createdby": self.user},
            ledger_overrides={"ledger_code": 9902, "accounthead": self.head_cash, "is_party": True},
        )
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=None,
            txn_type=TxnType.OPENING_BALANCE,
            txn_id=account_opening_txn_id(opening_only_account.id),
            voucher_no="ACC-OPEN-POSTED-ONLY",
            posting_date="2025-04-01",
            voucher_date="2025-04-01",
            status=EntryStatus.POSTED,
            narration="Opening balance for posted opening only ledger",
            lines=[
                (opening_only_account, opening_only_ledger, True, "500.00", "Opening debit"),
                (self.income_account, self.income_ledger, False, "500.00", "Opening offset"),
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-trial-balance"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "scope_mode": "custom",
                "from_date": "2025-04-02",
                "to_date": "2025-04-30",
                "group_by": "ledger",
                "posted_only": True,
                "include_opening": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        rows = {row["ledger_name"]: row for row in data["rows"]}

        self.assertEqual(Decimal(str(data["totals"]["opening"])), Decimal("800.00"))
        self.assertEqual(Decimal(str(data["totals"]["closing"])), Decimal("890.00"))
        self.assertEqual(Decimal(str(data["totals"]["opening_debit"])), Decimal("800.00"))
        self.assertEqual(Decimal(str(data["totals"]["opening_credit"])), Decimal("800.00"))
        self.assertEqual(Decimal(str(data["totals"]["closing_debit"])), Decimal("890.00"))
        self.assertEqual(Decimal(str(data["totals"]["closing_credit"])), Decimal("890.00"))
        self.assertEqual(Decimal(str(rows["Posted Opening Only"]["opening"])), Decimal("500.00"))
        self.assertEqual(Decimal(str(rows["Posted Opening Only"]["closing"])), Decimal("500.00"))

    def test_trial_balance_date_range_without_scope_mode_still_includes_opening(self):
        response = self.client.get(
            reverse("reports_api:financial-trial-balance"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "from_date": "2025-04-02",
                "to_date": "2025-04-30",
                "group_by": "ledger",
                "posted_only": True,
                "include_opening": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        rows = {row["ledger_name"]: row for row in data["rows"]}
        self.assertEqual(Decimal(str(data["totals"]["opening"])), Decimal("300.00"), data)
        self.assertEqual(Decimal(str(rows["Cash In Hand"]["opening"])), Decimal("100.00"))
        self.assertEqual(Decimal(str(rows["Main Bank"]["opening"])), Decimal("200.00"))

    def test_trial_balance_exposes_standard_export_actions(self):
        response = self.client.get(
            reverse("reports_api:financial-trial-balance"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "group_by": "ledger",
                "posted_only": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["available_exports"], ["excel", "pdf", "csv", "print"])
        self.assertEqual(set(data["actions"]["export_urls"].keys()), {"excel", "pdf", "csv", "print"})
        for key in ["excel", "pdf", "csv", "print"]:
            self.assertIn("entity=", data["actions"]["export_urls"][key])
            self.assertIn(f"entityfinid={self.entityfin.id}", data["actions"]["export_urls"][key])
            self.assertIn("group_by=ledger", data["actions"]["export_urls"][key])

    def test_trial_balance_envelope_exposes_ui_contract(self):
        response = self.client.get(
            reverse("reports_api:financial-trial-balance"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "group_by": "ledger",
                "posted_only": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_code"], "trial_balance")
        self.assertEqual(data["report_name"], "Trial Balance")
        self.assertTrue(data["actions"]["can_view"])
        self.assertTrue(data["actions"]["can_export_excel"])
        self.assertTrue(data["actions"]["can_export_pdf"])
        self.assertTrue(data["actions"]["can_export_csv"])
        self.assertTrue(data["actions"]["can_drilldown"])
        self.assertTrue(data["actions"]["can_print"])
        self.assertEqual(data["available_exports"], ["excel", "pdf", "csv", "print"])
        self.assertEqual(set(data["actions"]["export_urls"].keys()), {"excel", "pdf", "csv", "print"})
        self.assertIn("group_by=ledger", data["actions"]["export_urls"]["excel"])

    def test_trial_balance_year_period_by_splits_current_financial_year_by_calendar_year(self):
        response = self.client.get(
            reverse("reports_api:financial-trial-balance"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "group_by": "ledger",
                "posted_only": True,
                "period_by": "year",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data["periods"]), 2, data["periods"])
        self.assertEqual(data["periods"][0]["period_label"], "2025")
        self.assertEqual(data["periods"][1]["period_label"], "2026")

        rows = {row["ledger_name"]: row for row in data["rows"]}
        self.assertEqual(rows["Cash In Hand"]["periods"][0]["debit"], "50.00")
        self.assertEqual(rows["Cash In Hand"]["periods"][0]["closing"], "150.00")
        self.assertEqual(rows["Cash In Hand"]["periods"][1]["debit"], "0.00")
        self.assertEqual(rows["Sales Income"]["periods"][0]["credit"], "90.00")

    def test_profit_loss_year_period_by_uses_previous_financial_year_snapshot(self):
        previous_fy = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2024-25",
            finstartyear=timezone.make_aware(datetime(2024, 4, 1)),
            finendyear=timezone.make_aware(datetime(2025, 3, 31)),
            createdby=self.user,
        )
        expense_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Indirect Expenses Prior",
            accounttypecode="5209",
            createdby=self.user,
        )
        income_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Indirect Income Prior",
            accounttypecode="6209",
            createdby=self.user,
        )
        pl_expense_head = accountHead.objects.create(
            entity=self.entity,
            name="Prior Expense",
            code=5291,
            detailsingroup=2,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=expense_type,
            createdby=self.user,
        )
        pl_income_head = accountHead.objects.create(
            entity=self.entity,
            name="Prior Income",
            code=6291,
            detailsingroup=2,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=income_type,
            createdby=self.user,
        )
        pl_expense_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=5291,
            name="Prior Expense",
            accounthead=pl_expense_head,
            accounttype=expense_type,
            createdby=self.user,
        )
        pl_income_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=6291,
            name="Prior Income",
            accounthead=pl_income_head,
            accounttype=income_type,
            createdby=self.user,
        )
        pl_expense_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": pl_expense_ledger, "accountname": "Prior Expense", "createdby": self.user},
            ledger_overrides={"ledger_code": 5291, "accounthead": pl_expense_head, "is_party": True},
        )
        pl_income_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": pl_income_ledger, "accountname": "Prior Income", "createdby": self.user},
            ledger_overrides={"ledger_code": 6291, "accounthead": pl_income_head, "is_party": True},
        )
        self._create_entry(
            entity=self.entity,
            entityfin=previous_fy,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL,
            txn_id=602,
            voucher_no="JV-PREV-PL-001",
            posting_date="2024-04-11",
            voucher_date="2024-04-11",
            status=EntryStatus.POSTED,
            narration="Previous FY profit loss comparison",
            lines=[
                (pl_expense_account, pl_expense_ledger, True, "7.00", "Expense debit"),
                (pl_income_account, pl_income_ledger, False, "19.00", "Income credit"),
                (self.cash_account, self.cash_ledger, True, "12.00", "Balancing cash"),
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-profit-loss"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "group_by": "ledger",
                "posted_only": True,
                "period_by": "year",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data["periods"]), 1)
        self.assertEqual(data["periods"][0]["period_label"], "FY 2024-25")
        self.assertEqual(Decimal(str(data["periods"][0]["totals"]["income"])), Decimal("19.00"), data["periods"])
        self.assertEqual(Decimal(str(data["periods"][0]["totals"]["expense"])), Decimal("7.00"))
        self.assertEqual(Decimal(str(data["periods"][0]["totals"]["net_profit"])), Decimal("12.00"))

    def test_balance_sheet_year_period_by_uses_previous_financial_year_snapshot(self):
        previous_fy = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2024-25",
            finstartyear=timezone.make_aware(datetime(2024, 4, 1)),
            finendyear=timezone.make_aware(datetime(2025, 3, 31)),
            createdby=self.user,
        )
        asset_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Current Assets Prior",
            accounttypecode="1109",
            createdby=self.user,
        )
        asset_head = accountHead.objects.create(
            entity=self.entity,
            name="Prior Cash Asset",
            code=1191,
            detailsingroup=3,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=asset_type,
            createdby=self.user,
        )
        asset_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=1191,
            name="Prior Cash Asset",
            accounthead=asset_head,
            accounttype=asset_type,
            createdby=self.user,
        )
        asset_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": asset_ledger, "accountname": "Prior Cash Asset", "createdby": self.user},
            ledger_overrides={"ledger_code": 1191, "accounthead": asset_head, "is_party": True},
        )
        equity_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Capital and Equity Prior",
            accounttypecode="3109",
            createdby=self.user,
        )
        equity_head = accountHead.objects.create(
            entity=self.entity,
            name="Prior Capital",
            code=3191,
            detailsingroup=3,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=equity_type,
            createdby=self.user,
        )
        equity_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=3191,
            name="Prior Capital",
            accounthead=equity_head,
            accounttype=equity_type,
            createdby=self.user,
        )
        equity_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": equity_ledger, "accountname": "Prior Capital", "createdby": self.user},
            ledger_overrides={"ledger_code": 3191, "accounthead": equity_head, "is_party": True},
        )
        self._create_entry(
            entity=self.entity,
            entityfin=previous_fy,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL,
            txn_id=603,
            voucher_no="JV-PREV-BS-001",
            posting_date="2024-04-12",
            voucher_date="2024-04-12",
            status=EntryStatus.POSTED,
            narration="Previous FY balance sheet comparison",
            lines=[
                (asset_account, asset_ledger, True, "12.00", "Asset debit"),
                (equity_account, equity_ledger, False, "12.00", "Capital credit"),
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-balance-sheet"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "group_by": "ledger",
                "posted_only": True,
                "period_by": "year",
                "include_diagnostics": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data["periods"]), 1)
        self.assertEqual(data["periods"][0]["period_label"], "FY 2024-25")
        self.assertEqual(Decimal(str(data["periods"][0]["totals"]["assets"])), Decimal("12.00"), data["periods"])
        self.assertEqual(Decimal(str(data["periods"][0]["totals"]["liabilities_and_equity"])), Decimal("12.00"))

    def test_ledger_summary_date_range_without_scope_mode_still_includes_opening(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-summary"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "from_date": "2025-04-02",
                "to_date": "2025-04-30",
                "group_by": "ledger",
                "posted_only": True,
                "include_opening": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        rows = {row["ledger_name"]: row for row in data["rows"]}

        self.assertEqual(Decimal(str(data["totals"]["opening"])), Decimal("300.00"))
        self.assertEqual(Decimal(str(rows["Cash In Hand"]["opening"])), Decimal("100.00"))
        self.assertEqual(Decimal(str(rows["Main Bank"]["opening"])), Decimal("200.00"))

    def test_ledger_summary_exposes_standard_export_actions(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-summary"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "group_by": "ledger",
                "posted_only": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["available_exports"], ["excel", "pdf", "csv", "print"])
        self.assertEqual(set(data["actions"]["export_urls"].keys()), {"excel", "pdf", "csv", "print"})
        for key in ["excel", "pdf", "csv", "print"]:
            self.assertIn("entity=", data["actions"]["export_urls"][key])
            self.assertIn(f"entityfinid={self.entityfin.id}", data["actions"]["export_urls"][key])
            self.assertIn("group_by=ledger", data["actions"]["export_urls"][key])

    def test_ledger_summary_envelope_exposes_ui_contract(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-summary"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "group_by": "ledger",
                "posted_only": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_code"], "ledger_summary")
        self.assertEqual(data["report_name"], "Ledger Summary")
        self.assertTrue(data["actions"]["can_view"])
        self.assertTrue(data["actions"]["can_export_excel"])
        self.assertTrue(data["actions"]["can_export_pdf"])
        self.assertTrue(data["actions"]["can_export_csv"])
        self.assertTrue(data["actions"]["can_drilldown"])
        self.assertTrue(data["actions"]["can_print"])
        self.assertEqual(data["available_exports"], ["excel", "pdf", "csv", "print"])
        self.assertEqual(set(data["actions"]["export_urls"].keys()), {"excel", "pdf", "csv", "print"})
        self.assertIn("group_by=ledger", data["actions"]["export_urls"]["excel"])

    def test_ledger_book_date_range_without_scope_mode_keeps_opening_separate(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-book"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "ledger": self.cash_ledger.id,
                "from_date": "2025-04-05",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["opening_balance"], "100.00")
        self.assertEqual([row["voucher_number"] for row in data["rows"]], ["CV-001"])
        self.assertEqual(data["totals"]["closing_balance"], "150.00")

    def test_ledger_book_exposes_standard_export_actions(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-book"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "ledger": self.cash_ledger.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["available_exports"], ["excel", "pdf", "csv", "print"])
        self.assertEqual(set(data["actions"]["export_urls"].keys()), {"excel", "pdf", "csv", "print"})
        for key in ["excel", "pdf", "csv", "print"]:
            self.assertIn("entity=", data["actions"]["export_urls"][key])
            self.assertIn(f"entityfinid={self.entityfin.id}", data["actions"]["export_urls"][key])
            self.assertIn(f"ledger={self.cash_ledger.id}", data["actions"]["export_urls"][key])

    def test_ledger_book_envelope_exposes_ui_contract(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-book"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "ledger": self.cash_ledger.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_code"], "ledger_book")
        self.assertEqual(data["report_name"], "Ledger Book")
        self.assertTrue(data["actions"]["can_view"])
        self.assertTrue(data["actions"]["can_export_excel"])
        self.assertTrue(data["actions"]["can_export_pdf"])
        self.assertTrue(data["actions"]["can_export_csv"])
        self.assertTrue(data["actions"]["can_drilldown"])
        self.assertTrue(data["actions"]["can_print"])
        self.assertEqual(data["available_exports"], ["excel", "pdf", "csv", "print"])
        self.assertEqual(set(data["actions"]["export_urls"].keys()), {"excel", "pdf", "csv", "print"})
        self.assertIn(f"ledger={self.cash_ledger.id}", data["actions"]["export_urls"]["excel"])
        self.assertEqual(data["running_balance_scope"], "account")
        self.assertEqual(data["balance_basis"], "ledger_running_balance")
        self.assertTrue(data["balance_integrity"])
        self.assertIn("ordered deterministically", data["balance_note"])
        self.assertEqual(data["reporting"]["basis"], "ledger_running_balance")
        self.assertEqual(data["reporting"]["scope_mode"], "financial_year")

    def test_ledger_book_csv_export_includes_balance_context_metadata(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-book-csv"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "ledger": self.cash_ledger.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        self.assertIn("Ledger Book", content)
        self.assertIn("Display Unit", content)
        self.assertIn("Running Balance Scope", content)
        self.assertIn("Balance Basis", content)
        self.assertIn("Balance Integrity", content)
        self.assertIn("Report Total", content)

    def test_ledger_summary_financial_year_hides_opening_values_by_default(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-summary"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "scope_mode": "financial_year",
                "group_by": "ledger",
                "posted_only": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        rows = {row["ledger_name"]: row for row in data["rows"]}
        self.assertEqual(Decimal(str(data["totals"]["opening"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(rows["Cash In Hand"]["opening"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(rows["Cash In Hand"]["balance"])), Decimal("150.00"))

    def test_ledger_summary_financial_year_scope_with_explicit_dates_keeps_single_window(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-summary"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "scope_mode": "financial_year",
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "group_by": "ledger",
                "posted_only": True,
                "include_opening": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        rows = {row["ledger_name"]: row for row in data["rows"]}
        self.assertEqual(Decimal(str(data["totals"]["opening"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(rows["Cash In Hand"]["opening"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(rows["Cash In Hand"]["balance"])), Decimal("150.00"))

    def test_ledger_summary_reporting_uses_resolved_sort_key(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-summary"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "group_by": "ledger",
                "sort_by": "balance",
                "sort_order": "desc",
                "posted_only": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["reporting"]["sort_by"], "closing")
        self.assertEqual(data["reporting"]["sort_order"], "desc")

    def test_ledger_book_financial_year_scope_with_explicit_dates_does_not_split_opening(self):
        response = self.client.get(
            reverse("reports_api:financial-ledger-book"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "ledger": self.cash_ledger.id,
                "scope_mode": "financial_year",
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["opening_balance"], "0.00")
        self.assertEqual([row["voucher_number"] for row in data["rows"]], ["ACC-OPEN-CASH", "CV-001"])
        self.assertEqual(data["totals"]["closing_balance"], "150.00")

    def test_profit_loss_totals_match_posted_income_and_expense_ledgers(self):
        expense_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Indirect Expenses",
            accounttypecode="5200",
            createdby=self.user,
        )
        income_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Indirect Income",
            accounttypecode="6200",
            createdby=self.user,
        )
        pl_expense_head = accountHead.objects.create(
            entity=self.entity,
            name="Administrative Expense",
            code=5201,
            detailsingroup=2,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=expense_type,
            createdby=self.user,
        )
        pl_income_head = accountHead.objects.create(
            entity=self.entity,
            name="Service Income",
            code=6201,
            detailsingroup=2,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=income_type,
            createdby=self.user,
        )
        pl_expense_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=5201,
            name="Administrative Expense",
            accounthead=pl_expense_head,
            accounttype=expense_type,
            createdby=self.user,
        )
        pl_income_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=6201,
            name="Service Income",
            accounthead=pl_income_head,
            accounttype=income_type,
            createdby=self.user,
        )
        pl_expense_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": pl_expense_ledger, "accountname": "Administrative Expense", "createdby": self.user},
            ledger_overrides={"ledger_code": 5201, "accounthead": pl_expense_head, "is_party": True},
        )
        pl_income_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": pl_income_ledger, "accountname": "Service Income", "createdby": self.user},
            ledger_overrides={"ledger_code": 6201, "accounthead": pl_income_head, "is_party": True},
        )
        self._create_entry(
            txn_type=TxnType.JOURNAL,
            txn_id=108,
            voucher_no="JV-PL-001",
            posting_date="2025-04-09",
            voucher_date="2025-04-09",
            status=EntryStatus.POSTED,
            narration="Profit and loss classification test",
            subentity=self.subentity,
            lines=[
                (pl_expense_account, pl_expense_ledger, True, "25.00", "Administrative expense"),
                (pl_income_account, pl_income_ledger, False, "90.00", "Service income"),
                (self.cash_account, self.cash_ledger, True, "65.00", "Balancing cash"),
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-profit-loss"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "posted_only": True,
                "group_by": "ledger",
                "view_type": "summary",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(Decimal(str(data["totals"]["income"])), Decimal("90.00"))
        self.assertEqual(Decimal(str(data["totals"]["expense"])), Decimal("25.00"))
        self.assertEqual(Decimal(str(data["totals"]["net_profit"])), Decimal("65.00"))

        income_labels = {row.get("label") or row.get("ledger_name") for row in data["income"]}
        expense_labels = {row.get("label") or row.get("ledger_name") for row in data["expenses"]}
        self.assertIn("Service Income", income_labels)
        self.assertIn("Administrative Expense", expense_labels)

    def test_profit_loss_treats_credit_balance_expense_as_income(self):
        expense_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Indirect Expenses",
            accounttypecode="5201",
            createdby=self.user,
        )
        expense_head = accountHead.objects.create(
            entity=self.entity,
            name="Expense Reversal",
            code=5202,
            detailsingroup=2,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=expense_type,
            createdby=self.user,
        )
        expense_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=5202,
            name="Expense Reversal",
            accounthead=expense_head,
            accounttype=expense_type,
            createdby=self.user,
        )
        expense_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": expense_ledger, "accountname": "Expense Reversal", "createdby": self.user},
            ledger_overrides={"ledger_code": 5202, "accounthead": expense_head, "is_party": True},
        )

        self._create_entry(
            txn_type=TxnType.JOURNAL,
            txn_id=109,
            voucher_no="JV-PL-REV-001",
            posting_date="2025-04-10",
            voucher_date="2025-04-10",
            status=EntryStatus.POSTED,
            narration="Expense reversal classification test",
            subentity=self.subentity,
            lines=[
                (self.cash_account, self.cash_ledger, True, "5.00", "Cash debit"),
                (expense_account, expense_ledger, False, "5.00", "Expense reversal"),
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-profit-loss"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "posted_only": True,
                "group_by": "ledger",
                "view_type": "summary",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(Decimal(str(data["totals"]["income"])), Decimal("5.00"))
        self.assertEqual(Decimal(str(data["totals"]["expense"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(data["totals"]["net_profit"])), Decimal("5.00"))

        income_labels = {row.get("label") or row.get("ledger_name") for row in data["income"]}
        self.assertIn("Expense Reversal", income_labels)

    def test_profit_loss_export_urls_keep_current_scope_filters(self):
        response = self.client.get(
            reverse("reports_api:financial-profit-loss"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "posted_only": True,
                "group_by": "ledger",
                "search": "Sales",
            },
        )
        self.assertEqual(response.status_code, 200)
        export_urls = response.json()["actions"]["export_urls"]

        for key in ["csv", "print", "pdf_landscape", "excel_landscape"]:
            with self.subTest(key=key):
                self.assertIn("entity=", export_urls[key])
                self.assertIn(f"entityfinid={self.entityfin.id}", export_urls[key])
                self.assertIn(f"subentity={self.subentity.id}", export_urls[key])
                self.assertIn("from_date=2025-04-01", export_urls[key])
                self.assertIn("to_date=2025-04-30", export_urls[key])
                self.assertIn("group_by=ledger", export_urls[key])
                self.assertIn("search=Sales", export_urls[key])

    def test_balance_sheet_moves_negative_bank_balance_to_liabilities(self):
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL_BANK,
            txn_id=88,
            voucher_no="BV-OD-001",
            posting_date="2025-04-08",
            voucher_date="2025-04-08",
            status=EntryStatus.POSTED,
            narration="Bank overdraft test",
            lines=[
                (self.expense_account, self.expense_ledger, True, "6000.00", "Expense"),
                (self.bank_account, self.bank_ledger, False, "6000.00", "Bank overdraft"),
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-balance-sheet"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "account_group": "ledger",
                "posted_only": True,
                "hide_zero_rows": True,
                "include_diagnostics": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        asset_ledger_names = {row.get("ledger_name") for row in data.get("assets", [])}
        self.assertNotIn("Main Bank", asset_ledger_names)

    def test_balance_sheet_moves_debit_balance_of_liability_head_to_assets(self):
        liability_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Current Liabilities",
            accounttypecode="1006",
            createdby=self.user,
        )
        liability_head = accountHead.objects.create(
            entity=self.entity,
            name="Accrued Expenses",
            code=8401,
            detailsingroup=3,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=liability_type,
            createdby=self.user,
        )
        liability_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=8401,
            name="Accrued Expenses Control",
            accounthead=liability_head,
            accounttype=liability_type,
            openingbcr=Decimal("100.00"),
            createdby=self.user,
        )
        liability_account = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": liability_ledger,
                "accountname": "Accrued Expenses Control",
                "createdby": self.user,
            },
            ledger_overrides={
                "ledger_code": 8401,
                "accounthead": liability_head,
                "is_party": True,
            },
        )
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=None,
            txn_type=TxnType.OPENING_BALANCE,
            txn_id=account_opening_txn_id(liability_account.id),
            voucher_no="ACC-OPEN-LIAB",
            posting_date="2025-04-01",
            voucher_date="2025-04-01",
            status=EntryStatus.POSTED,
            narration="Opening balance for Accrued Expenses Control",
            lines=[
                (self.income_account, self.income_ledger, True, "100.00", "Opening offset"),
                (liability_account, liability_ledger, False, "100.00", "Opening credit"),
            ],
        )
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL,
            txn_id=89,
            voucher_no="JV-CONTRA-001",
            posting_date="2025-04-09",
            voucher_date="2025-04-09",
            status=EntryStatus.POSTED,
            narration="Liability debit balance test",
            lines=[
                (liability_account, liability_ledger, True, "250.00", "Over-adjusted liability"),
                (self.income_account, self.income_ledger, False, "250.00", "Offset credit"),
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-balance-sheet"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "account_group": "ledger",
                "posted_only": True,
                "hide_zero_rows": True,
                "include_diagnostics": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        asset_ledger_names = {row.get("ledger_name") for row in data.get("assets", [])}
        liability_ledger_names = {row.get("ledger_name") for row in data.get("liabilities_and_equity", [])}

        self.assertIn("Accrued Expenses Control", asset_ledger_names)
        self.assertNotIn("Accrued Expenses Control", liability_ledger_names)

    def test_balance_sheet_diagnostics_identify_excluded_rows_as_primary_reason(self):
        suspense_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Suspense Mapping",
            accounttypecode="9999",
            createdby=self.user,
        )
        suspense_head = accountHead.objects.create(
            entity=self.entity,
            name="Suspense Head",
            code=9101,
            detailsingroup=2,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=suspense_type,
            createdby=self.user,
        )
        suspense_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=9101,
            name="Suspense Balance",
            accounthead=suspense_head,
            accounttype=suspense_type,
            createdby=self.user,
        )
        suspense_account = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": suspense_ledger,
                "accountname": "Suspense Balance",
                "createdby": self.user,
            },
            ledger_overrides={
                "ledger_code": 9101,
                "accounthead": suspense_head,
                "accounttype": suspense_type,
                "is_party": True,
            },
        )

        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL,
            txn_id=901,
            voucher_no="JV-SUSP-001",
            posting_date="2025-04-11",
            voucher_date="2025-04-11",
            status=EntryStatus.POSTED,
            narration="Excluded suspense balance test",
            lines=[
                (self.cash_account, self.cash_ledger, True, "125.00", "Cash debit"),
                (suspense_account, suspense_ledger, False, "125.00", "Suspense credit"),
            ],
        )

        response = self.client.get(
            reverse("reports_api:financial-balance-sheet"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "account_group": "ledger",
                "posted_only": True,
                "hide_zero_rows": True,
                "include_diagnostics": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        diagnostics = data.get("diagnostics") or {}

        self.assertEqual(diagnostics.get("difference"), "125.00")
        self.assertEqual((diagnostics.get("primary_reason") or {}).get("code"), "excluded_balance_sheet_rows")
        self.assertEqual((diagnostics.get("primary_reason") or {}).get("amount"), "125.00")
        excluded_ledgers = {
            row.get("ledger_name")
            for row in diagnostics.get("excluded_rows", [])
            if row.get("excluded_reason") == "not_balance_sheet_classification"
        }
        self.assertIn("Suspense Balance", excluded_ledgers)
        reason_codes = {row.get("code") for row in diagnostics.get("reason_cards", [])}
        self.assertIn("base_balance_gap", reason_codes)
        self.assertIn("excluded_balance_sheet_rows", reason_codes)

    def test_balance_sheet_api_omits_diagnostics_by_default(self):
        response = self.client.get(
            reverse("reports_api:financial-balance-sheet"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "account_group": "ledger",
                "posted_only": True,
                "hide_zero_rows": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("diagnostics", data)

    def test_balance_sheet_api_includes_diagnostics_when_requested(self):
        response = self.client.get(
            reverse("reports_api:financial-balance-sheet"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "account_group": "ledger",
                "posted_only": True,
                "hide_zero_rows": True,
                "include_diagnostics": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("diagnostics", data)

    def test_balance_sheet_does_not_double_count_posted_opening_balance(self):
        from reports.services.financial.statements import _closing_map

        asset_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Current Assets",
            accounttypecode="1100",
            createdby=self.user,
        )
        equity_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Capital and Equity",
            accounttypecode="3100",
            createdby=self.user,
        )
        asset_head = accountHead.objects.create(
            entity=self.entity,
            name="Test Debtors",
            code=1101,
            detailsingroup=1,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=asset_type,
            createdby=self.user,
        )
        equity_head = accountHead.objects.create(
            entity=self.entity,
            name="Opening Equity",
            code=3101,
            detailsingroup=3,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=equity_type,
            createdby=self.user,
        )
        asset_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=9911,
            name="BS Opening Asset",
            accounthead=asset_head,
            accounttype=asset_type,
            openingbdr=Decimal("500.00"),
            createdby=self.user,
        )
        equity_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=9912,
            name="BS Opening Equity",
            accounthead=equity_head,
            accounttype=equity_type,
            openingbcr=Decimal("500.00"),
            createdby=self.user,
        )
        asset_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": asset_ledger, "accountname": "BS Opening Asset", "createdby": self.user},
            ledger_overrides={"ledger_code": 9911, "accounthead": asset_head, "is_party": True},
        )
        equity_account = create_account_with_synced_ledger(
            account_data={"entity": self.entity, "ledger": equity_ledger, "accountname": "BS Opening Equity", "createdby": self.user},
            ledger_overrides={"ledger_code": 9912, "accounthead": equity_head, "is_party": True},
        )
        self._create_entry(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=None,
            txn_type=TxnType.OPENING_BALANCE,
            txn_id=account_opening_txn_id(asset_account.id),
            voucher_no="ACC-OPEN-BS-ASSET",
            posting_date="2025-04-01",
            voucher_date="2025-04-01",
            status=EntryStatus.POSTED,
            narration="Opening balance for balance-sheet asset",
            lines=[
                (asset_account, asset_ledger, True, "500.00", "Opening debit"),
                (equity_account, equity_ledger, False, "500.00", "Opening credit"),
            ],
        )

        _, _, _, _, _, closing = _closing_map(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            from_date="2025-04-01",
            to_date="2025-04-30",
            posted_only=True,
            ledger_ids=[asset_ledger.id, equity_ledger.id],
        )

        self.assertEqual(closing[asset_ledger.id]["amount"], Decimal("500.00"))
        self.assertEqual(closing[equity_ledger.id]["amount"], Decimal("-500.00"))

    def test_profit_loss_envelope_exposes_ui_contract(self):
        response = self.client.get(
            reverse("reports_api:financial-profit-loss"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "posted_only": True,
                "group_by": "ledger",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_code"], "profit_loss")
        self.assertEqual(data["report_name"], "Profit and Loss")
        self.assertTrue(data["actions"]["can_view"])
        self.assertTrue(data["actions"]["can_export_excel"])
        self.assertTrue(data["actions"]["can_export_pdf"])
        self.assertTrue(data["actions"]["can_export_csv"])
        self.assertTrue(data["actions"]["can_drilldown"])
        self.assertTrue(data["actions"]["can_print"])
        self.assertEqual(
            data["available_exports"],
            ["excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"],
        )
        self.assertEqual(
            set(data["actions"]["export_urls"].keys()),
            {"excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"},
        )
        for key in ["excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"]:
            self.assertIn("entity=", data["actions"]["export_urls"][key])
            self.assertIn(f"entityfinid={self.entityfin.id}", data["actions"]["export_urls"][key])
            self.assertIn("group_by=ledger", data["actions"]["export_urls"][key])

    def test_balance_sheet_envelope_exposes_ui_contract(self):
        response = self.client.get(
            reverse("reports_api:financial-balance-sheet"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "account_group": "ledger",
                "posted_only": True,
                "hide_zero_rows": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_code"], "balance_sheet")
        self.assertEqual(data["report_name"], "Balance Sheet")
        self.assertTrue(data["actions"]["can_view"])
        self.assertTrue(data["actions"]["can_export_excel"])
        self.assertTrue(data["actions"]["can_export_pdf"])
        self.assertTrue(data["actions"]["can_export_csv"])
        self.assertTrue(data["actions"]["can_drilldown"])
        self.assertTrue(data["actions"]["can_print"])
        self.assertEqual(
            data["available_exports"],
            ["excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"],
        )
        self.assertEqual(
            set(data["actions"]["export_urls"].keys()),
            {"excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"},
        )
        for key in ["excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"]:
            self.assertIn("entity=", data["actions"]["export_urls"][key])
            self.assertIn(f"entityfinid={self.entityfin.id}", data["actions"]["export_urls"][key])
            self.assertIn("account_group=ledger", data["actions"]["export_urls"][key])

    def test_trading_account_envelope_exposes_ui_contract(self):
        response = self.client.get(
            reverse("reports_api:financial-trading-account"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
                "group_by": "ledger",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_code"], "trading_account")
        self.assertEqual(data["report_name"], "Trading Account")
        self.assertTrue(data["actions"]["can_view"])
        self.assertTrue(data["actions"]["can_export_excel"])
        self.assertTrue(data["actions"]["can_export_pdf"])
        self.assertTrue(data["actions"]["can_export_csv"])
        self.assertTrue(data["actions"]["can_drilldown"])
        self.assertTrue(data["actions"]["can_print"])
        self.assertEqual(
            data["available_exports"],
            ["excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"],
        )
        self.assertEqual(
            set(data["actions"]["export_urls"].keys()),
            {"excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"},
        )
        for key in ["excel", "pdf", "csv", "print", "pdf_landscape", "pdf_portrait", "excel_landscape", "excel_portrait"]:
            self.assertIn("entity=", data["actions"]["export_urls"][key])
            self.assertIn(f"entityfinid={self.entityfin.id}", data["actions"]["export_urls"][key])
            self.assertIn("group_by=ledger", data["actions"]["export_urls"][key] or "")
