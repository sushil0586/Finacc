from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity, UnitType
from financial.models import Ledger, account, accountHead, accounttype
from financial.services import apply_normalized_profile_payload
from geography.models import City, Country, District, State
from payments.models.payment_core import PaymentVoucherHeader
from posting.models import Entry, EntryStatus, PostingBatch, JournalLine, StaticAccount, EntityStaticAccountMap, TxnType
from receipts.models.receipt_core import ReceiptVoucherHeader
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
        self.unit_type = UnitType.objects.create(UnitName="Business", UnitDesc="Business")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Finacc Test Entity",
            legalname="Finacc Test Entity Pvt Ltd",
            unitType=self.unit_type,
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
            unitType=self.unit_type,
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
        self.cash_account = account.objects.create(entity=self.entity, ledger=self.cash_ledger, accounthead=self.head_cash, accountname="Cash In Hand", accountcode=1001, createdby=self.user)
        self.bank_account = account.objects.create(
            entity=self.entity,
            ledger=self.bank_ledger,
            accounthead=self.head_bank,
            accountname="Main Bank",
            accountcode=1002,
            createdby=self.user,
        )
        apply_normalized_profile_payload(
            self.bank_account,
            compliance_data={},
            commercial_data={"partytype": "Bank"},
            primary_address_data={},
        )
        self.expense_account = account.objects.create(entity=self.entity, ledger=self.expense_ledger, accounthead=self.head_expense, accountname="Office Expense", accountcode=2001, createdby=self.user)
        self.income_account = account.objects.create(entity=self.entity, ledger=self.income_ledger, accounthead=self.head_income, accountname="Sales Income", accountcode=3001, createdby=self.user)
        self.ap_ledger = Ledger.objects.create(entity=self.entity, ledger_code=4001, name="Sundry Creditors", accounthead=self.head_bank, createdby=self.user)
        self.ap_account = account.objects.create(entity=self.entity, ledger=self.ap_ledger, accounthead=self.head_bank, accountname="Sundry Creditors", accountcode=4001, createdby=self.user)
        self.other_cash_ledger = Ledger.objects.create(entity=self.other_entity, ledger_code=9001, name="Other Cash", accounthead=self.head_cash, createdby=self.user)
        self.other_cash_account = account.objects.create(entity=self.other_entity, ledger=self.other_cash_ledger, accounthead=self.head_cash, accountname="Other Cash", accountcode=9001, createdby=self.user)

        static_cash = StaticAccount.objects.create(code="CASH", name="Cash", group="CASH_BANK")
        static_bank = StaticAccount.objects.create(code="BANK_MAIN", name="Bank", group="CASH_BANK")
        EntityStaticAccountMap.objects.create(entity=self.entity, static_account=static_cash, account=self.cash_account, ledger=self.cash_ledger, createdby=self.user)
        EntityStaticAccountMap.objects.create(entity=self.entity, static_account=static_bank, account=self.bank_account, ledger=self.bank_ledger, createdby=self.user)

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
        self.assertEqual(data["totals"]["transaction_count"], 5)
        self.assertEqual(data["totals"]["debit_total"], "140.00")
        self.assertEqual(data["totals"]["credit_total"], "140.00")
        self.assertEqual(data["count"], 5)
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
        self.assertEqual(vouchers, {"CV-001", "PV-001"})
        self.assertNotIn("CV-999", vouchers)

    def test_daybook_pagination_keeps_totals_for_full_filtered_set(self):
        response = self.client.get(reverse("reports_api:financial-daybook"), {"entity": self.entity.id, "page": 1, "page_size": 2})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["count"], 5)
        self.assertEqual(data["totals"]["debit_total"], "140.00")
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
        self.assertEqual(omitted.json()["count"], 5)
        self.assertEqual(only_posted.json()["count"], 3)
        self.assertEqual(non_posted.json()["count"], 2)

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

    def test_cashbook_happy_path_running_balance_and_opening(self):
        response = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "cash_account": str(self.cash_account.id), "from_date": "2025-04-01", "to_date": "2025-04-30"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["balance_integrity"])
        self.assertEqual(data["mode"], "single_account_detail")
        self.assertEqual(data["opening_balance"], "100.00")
        self.assertEqual(data["closing_balance"], "135.00")
        self.assertEqual(data["totals"]["receipt_total"], "50.00")
        self.assertEqual(data["totals"]["payment_total"], "15.00")
        self.assertEqual([row["voucher_number"] for row in data["results"]], ["CV-001", "PV-001"])
        self.assertEqual(data["results"][0]["running_balance"], "150.00")
        self.assertEqual(data["results"][1]["running_balance"], "135.00")

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
        self.assertEqual(data["closing_balance"], "350.00")
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
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["voucher_number"], "PV-001")
        self.assertIsNone(rows[0]["running_balance"])
        self.assertTrue(data["balance_integrity"])
        self.assertEqual(data["opening_balance"], "100.00")
        self.assertEqual(data["closing_balance"], "135.00")
        self.assertEqual(data["totals"]["receipt_total"], "0.00")
        self.assertEqual(data["totals"]["payment_total"], "15.00")
        self.assertEqual(data["totals"]["period_receipt_total"], "50.00")
        self.assertEqual(data["totals"]["period_payment_total"], "15.00")
        self.assertIn("suppress it", data["balance_note"])

    def test_cashbook_empty_results_and_pagination(self):
        response = self.client.get(reverse("reports_api:financial-cashbook"), {"entity": self.entity.id, "cash_account": str(self.cash_account.id), "from_date": "2025-05-01", "to_date": "2025-05-31", "page": 1, "page_size": 1})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["totals"]["transaction_count"], 0)
        self.assertEqual(data["results"], [])
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["opening_balance"], "135.00")
        self.assertEqual(data["closing_balance"], "135.00")

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
