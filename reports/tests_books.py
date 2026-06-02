from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

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
        self.assertIn("voucher_types", data)
        self.assertIn("daybook_voucher_types", data)
        self.assertIn("cashbook_voucher_types", data)
        self.assertIn("daybook_statuses", data)
        self.assertIn("all_accounts", data)
        self.assertIn("cash_accounts", data)
        self.assertIn("bank_accounts", data)

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
        rows = [row for row in response.json()["rows"] if row["txn_id"] == sales_document.id]
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
        rows = [row for row in response.json()["results"] if row["drilldown"]["txn_id"] == purchase_document.id]
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
        rows = [row for row in response.json()["results"] if row["drilldown"]["txn_id"] == sales_document.id]
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
        self.assertIsNone(data["running_balance_scope"])
        self.assertEqual(data["opening_balance"], "300.00")
        self.assertEqual(data["closing_balance"], "365.00")
        self.assertEqual(len(data["account_summaries"]), 2)
        impacted = {row["account_impacted"]["name"] for row in data["results"]}
        self.assertEqual(impacted, {"Cash In Hand", "Main Bank"})
        self.assertTrue(all(row["running_balance"] is None for row in data["results"]))
        self.assertIn("suppress it", data["balance_note"])

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
        self.assertIn("suppress it", data["balance_note"])

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
        self.fail(str(data))
        self.assertEqual(Decimal(str(data["totals"]["debit"])), Decimal("115.00"))
        self.assertEqual(Decimal(str(data["totals"]["credit"])), Decimal("115.00"))
        self.assertEqual(Decimal(str(data["totals"]["closing"])), Decimal("300.00"))

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
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        asset_ledger_names = {row.get("ledger_name") for row in data.get("assets", [])}
        liability_ledger_names = {row.get("ledger_name") for row in data.get("liabilities_and_equity", [])}

        self.assertIn("Accrued Expenses Control", asset_ledger_names)
        self.assertNotIn("Accrued Expenses Control", liability_ledger_names)

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
