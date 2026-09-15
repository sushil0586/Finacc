from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, Godown, GstRegistrationType, SubEntity
from financial.models import Ledger, account, accountHead, accounttype
from financial.services import apply_normalized_profile_payload
from posting.models import Entry, EntryStatus, InventoryMove, JournalLine, PostingBatch, TxnType
from purchase.models.purchase_ap import (
    VendorAdvanceBalance,
    VendorBillOpenItem,
    VendorSettlement,
    VendorSettlementLine,
)
from purchase.models.purchase_config import PurchaseSettings
from purchase.models.purchase_core import PurchaseInvoiceHeader, PurchaseTaxSummary
from purchase.services.purchase_ap_service import PurchaseApService
from reports.services.financial.books import build_daybook
from reports.services.financial.ledger_summary import build_ledger_summary
from reports.services.financial.statements import build_balance_sheet, build_profit_and_loss
from reports.services.financial.trial_balance import build_trial_balance
from reports.services.payables import build_vendor_outstanding_report
from reports.services.purchase_register_service import PurchaseRegisterService
from reports.services.receivables import build_customer_outstanding_report
from reports.services.inventory.location_stock import build_inventory_location_stock
from reports.services.inventory.valuation import value_moves_by_inventory_identity
from reports.services.statutory.gstr1_service import Gstr1Service
from reports.services.trading_account import build_trading_account_dynamic, inventory_breakdown_asof
from reports.gstr1.services.summary import Gstr1SummaryService
from reports.gstr3b.services import Gstr3bSummaryService
from sales.models.sales_ar import (
    CustomerAdvanceBalance,
    CustomerBillOpenItem,
    CustomerSettlement,
    CustomerSettlementLine,
)
from sales.models.sales_core import SalesInvoiceHeader, SalesTaxSummary
from sales.services.sales_ar_service import SalesArService


class InventoryIdentityValuationTests(TestCase):
    def test_all_valuation_methods_isolate_location_and_batch_pools(self):
        moves = [
            {"product_id": 1, "location_id": 10, "batch_number": "LOT-A", "move_type": "IN", "base_qty": "100", "unit_cost": "100"},
            {"product_id": 1, "location_id": 20, "batch_number": "LOT-B", "move_type": "IN", "base_qty": "50", "unit_cost": "120"},
            {"product_id": 1, "location_id": 20, "batch_number": "LOT-B", "move_type": "OUT", "base_qty": "10", "unit_cost": "120"},
            {"product_id": 1, "location_id": 10, "batch_number": "LOT-A", "move_type": "OUT", "base_qty": "30", "unit_cost": "100"},
            {"product_id": 1, "location_id": 10, "batch_number": "LOT-A", "move_type": "IN", "base_qty": "5", "unit_cost": "100"},
        ]

        for method in ("fifo", "lifo", "mwa", "wac", "latest"):
            with self.subTest(method=method):
                self.assertEqual(
                    value_moves_by_inventory_identity(moves, method)[1],
                    (Decimal("115"), Decimal("12300")),
                )

    def test_negative_stock_is_reported_without_inventing_negative_value(self):
        moves = [
            {"product_id": 1, "location_id": 10, "batch_number": "", "move_type": "OUT", "base_qty": "3", "unit_cost": "0"},
        ]

        for method in ("fifo", "lifo", "mwa", "wac", "latest"):
            with self.subTest(method=method):
                self.assertEqual(
                    value_moves_by_inventory_identity(moves, method)[1],
                    (Decimal("-3"), Decimal("0")),
                )


class ServiceEntityAccountingTruthMatrixTests(TestCase):
    """Dataset A: one source set must reconcile across every financial report."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="accounting-oracle",
            email="accounting-oracle@example.com",
            password="pass123",
        )
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        cls.entity = Entity.objects.create(
            entityname="Dataset A Service Entity",
            legalname="Dataset A Service Entity",
            GstRegitrationType=gst_type,
            createdby=cls.user,
        )
        cls.branch = SubEntity.objects.create(entity=cls.entity, subentityname="Head Office")
        cls.entityfin = EntityFinancialYear.objects.create(
            entity=cls.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=cls.user,
        )

        current_asset = cls._account_type("Current Assets", "1003", True)
        current_liability = cls._account_type("Current Liabilities", "1006", False)
        equity = cls._account_type("Capital and Equity", "1012", False)
        income = cls._account_type("Indirect Income", "4200", False)
        expense = cls._account_type("Indirect Expenses", "5200", True)

        cls.bank = cls._account("Main Bank", 1101, current_asset, "Debit", 3)
        cls.cash = cls._account("Cash In Hand", 1102, current_asset, "Debit", 3)
        cls.customer = cls._account("Service Customer", 1103, current_asset, "Debit", 3, is_party=True)
        cls.input_cgst = cls._account("Input CGST", 1104, current_asset, "Debit", 3)
        cls.input_sgst = cls._account("Input SGST", 1105, current_asset, "Debit", 3)
        cls.vendor = cls._account("Service Vendor", 2101, current_liability, "Credit", 3, is_party=True)
        cls.output_cgst = cls._account("Output CGST", 2102, current_liability, "Credit", 3)
        cls.output_sgst = cls._account("Output SGST", 2103, current_liability, "Credit", 3)
        cls.accrued_liability = cls._account("Accrued Liability", 2104, current_liability, "Credit", 3)
        cls.capital = cls._account("Owner Capital", 3101, equity, "Credit", 3)
        cls.service_revenue = cls._account("Service Revenue", 4101, income, "Credit", 2)
        cls.service_expense = cls._account("Service Expense", 5101, expense, "Debit", 2)
        cls.accrued_expense = cls._account("Accrued Expense", 5102, expense, "Debit", 2)

        apply_normalized_profile_payload(
            cls.customer,
            compliance_data={},
            commercial_data={"partytype": "Customer", "currency": "INR"},
            primary_address_data={},
        )
        apply_normalized_profile_payload(
            cls.vendor,
            compliance_data={},
            commercial_data={"partytype": "Vendor", "currency": "INR"},
            primary_address_data={},
        )

        cls.sales_invoice = SalesInvoiceHeader.objects.create(
            id=2,
            entity=cls.entity,
            entityfinid=cls.entityfin,
            subentity=cls.branch,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2026-04-02",
            posting_date="2026-04-02",
            doc_code="SINV",
            doc_no=2,
            invoice_number="A2-SALE",
            customer=cls.customer,
            customer_ledger=cls.customer.ledger,
            customer_name=cls.customer.accountname,
            customer_gstin="29ABCDE1234F1Z5",
            customer_state_code="29",
            seller_gstin="29AAAAA9999A1Z5",
            seller_state_code="29",
            place_of_supply_state_code="29",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            total_taxable_value=Decimal("10000.00"),
            total_cgst=Decimal("900.00"),
            total_sgst=Decimal("900.00"),
            grand_total=Decimal("11800.00"),
            created_by=cls.user,
        )
        cls.purchase_invoice = PurchaseInvoiceHeader.objects.create(
            id=4,
            entity=cls.entity,
            entityfinid=cls.entityfin,
            subentity=cls.branch,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date="2026-04-04",
            due_date="2026-04-05",
            doc_code="PINV",
            doc_no=4,
            purchase_number="A4-PURCHASE",
            supplier_invoice_number="A4-SUPPLIER",
            vendor=cls.vendor,
            vendor_ledger=cls.vendor.ledger,
            vendor_name=cls.vendor.accountname,
            vendor_gstin="29ABCDE5678F1Z5",
            total_taxable=Decimal("4000.00"),
            total_cgst=Decimal("360.00"),
            total_sgst=Decimal("360.00"),
            grand_total=Decimal("4720.00"),
            created_by=cls.user,
        )

        cls._entry(TxnType.OPENING_BALANCE, 1, "A1-OPENING", "2026-04-01", [
            (cls.bank, True, "100000.00"),
            (cls.capital, False, "100000.00"),
        ])
        cls._entry(TxnType.SALES, 2, "A2-SALE", "2026-04-02", [
            (cls.customer, True, "11800.00"),
            (cls.service_revenue, False, "10000.00"),
            (cls.output_cgst, False, "900.00"),
            (cls.output_sgst, False, "900.00"),
        ])
        cls._entry(TxnType.RECEIPT, 3, "A3-RECEIPT", "2026-04-03", [
            (cls.bank, True, "11800.00"),
            (cls.customer, False, "11800.00"),
        ])
        cls._entry(TxnType.PURCHASE, 4, "A4-PURCHASE", "2026-04-04", [
            (cls.service_expense, True, "4000.00"),
            (cls.input_cgst, True, "360.00"),
            (cls.input_sgst, True, "360.00"),
            (cls.vendor, False, "4720.00"),
        ])
        cls._entry(TxnType.PAYMENT, 5, "A5-PAYMENT", "2026-04-05", [
            (cls.vendor, True, "4720.00"),
            (cls.bank, False, "4720.00"),
        ])
        cls._entry(TxnType.JOURNAL, 6, "A6-ACCRUAL", "2026-04-06", [
            (cls.accrued_expense, True, "1500.00"),
            (cls.accrued_liability, False, "1500.00"),
        ])
        cls._entry(TxnType.JOURNAL, 7, "A7-REVERSAL", "2026-04-07", [
            (cls.accrued_liability, True, "1500.00"),
            (cls.accrued_expense, False, "1500.00"),
        ])
        cls._entry(TxnType.JOURNAL_BANK, 8, "A8-TRANSFER", "2026-04-08", [
            (cls.cash, True, "5000.00"),
            (cls.bank, False, "5000.00"),
        ])

        cls.customer_open_item = CustomerBillOpenItem.objects.create(
            header=cls.sales_invoice,
            entity=cls.entity,
            entityfinid=cls.entityfin,
            subentity=cls.branch,
            customer=cls.customer,
            customer_ledger=cls.customer.ledger,
            doc_type=cls.sales_invoice.doc_type,
            bill_date="2026-04-02",
            due_date="2026-04-03",
            invoice_number=cls.sales_invoice.invoice_number,
            original_amount=Decimal("11800.00"),
            gross_amount=Decimal("11800.00"),
            net_receivable_amount=Decimal("11800.00"),
            outstanding_amount=Decimal("11800.00"),
            is_open=True,
        )
        cls.customer_settlement = CustomerSettlement.objects.create(
            entity=cls.entity,
            entityfinid=cls.entityfin,
            subentity=cls.branch,
            customer=cls.customer,
            customer_ledger=cls.customer.ledger,
            settlement_type=CustomerSettlement.SettlementType.RECEIPT,
            settlement_date="2026-04-03",
            reference_no="A3-RECEIPT",
            total_amount=Decimal("11800.00"),
            status=CustomerSettlement.Status.POSTED,
            posted_at=timezone.now(),
            posted_by=cls.user,
        )
        CustomerSettlementLine.objects.create(
            settlement=cls.customer_settlement,
            open_item=cls.customer_open_item,
            amount=Decimal("11800.00"),
            applied_amount_signed=Decimal("11800.00"),
        )

        cls.vendor_open_item = VendorBillOpenItem.objects.create(
            header=cls.purchase_invoice,
            entity=cls.entity,
            entityfinid=cls.entityfin,
            subentity=cls.branch,
            vendor=cls.vendor,
            vendor_ledger=cls.vendor.ledger,
            doc_type=cls.purchase_invoice.doc_type,
            bill_date="2026-04-04",
            due_date="2026-04-05",
            purchase_number=cls.purchase_invoice.purchase_number,
            supplier_invoice_number=cls.purchase_invoice.supplier_invoice_number,
            original_amount=Decimal("4720.00"),
            gross_amount=Decimal("4720.00"),
            net_payable_amount=Decimal("4720.00"),
            outstanding_amount=Decimal("4720.00"),
            is_open=True,
        )
        cls.vendor_settlement = VendorSettlement.objects.create(
            entity=cls.entity,
            entityfinid=cls.entityfin,
            subentity=cls.branch,
            vendor=cls.vendor,
            vendor_ledger=cls.vendor.ledger,
            settlement_type=VendorSettlement.SettlementType.PAYMENT,
            settlement_date="2026-04-05",
            reference_no="A5-PAYMENT",
            total_amount=Decimal("4720.00"),
            status=VendorSettlement.Status.POSTED,
            posted_at=timezone.now(),
            posted_by=cls.user,
        )
        VendorSettlementLine.objects.create(
            settlement=cls.vendor_settlement,
            open_item=cls.vendor_open_item,
            amount=Decimal("4720.00"),
            applied_amount_signed=Decimal("4720.00"),
        )

    @classmethod
    def _account_type(cls, name, code, debit_nature):
        return accounttype.objects.create(
            entity=cls.entity,
            accounttypename=name,
            accounttypecode=code,
            balanceType=debit_nature,
            createdby=cls.user,
        )

    @classmethod
    def _account(cls, name, code, account_type, side, statement_group, is_party=False):
        head = accountHead.objects.create(
            entity=cls.entity,
            name=f"{name} Head",
            code=code,
            balanceType=side,
            drcreffect=side,
            detailsingroup=statement_group,
            accounttype=account_type,
            createdby=cls.user,
        )
        ledger = Ledger.objects.create(
            entity=cls.entity,
            ledger_code=code,
            name=name,
            accounthead=head,
            accounttype=account_type,
            is_party=is_party,
            createdby=cls.user,
        )
        return account.objects.create(
            entity=cls.entity,
            ledger=ledger,
            accountname=name,
            createdby=cls.user,
        )

    @classmethod
    def _entry(cls, txn_type, txn_id, voucher_no, posting_date, lines, status=EntryStatus.POSTED):
        batch = PostingBatch.objects.create(
            entity=cls.entity,
            entityfin=cls.entityfin,
            subentity=cls.branch,
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=voucher_no,
            created_by=cls.user,
        )
        entry = Entry.objects.create(
            entity=cls.entity,
            entityfin=cls.entityfin,
            subentity=cls.branch,
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=voucher_no,
            voucher_date=posting_date,
            posting_date=posting_date,
            status=status,
            posting_batch=batch,
            narration=voucher_no,
            created_by=cls.user,
        )
        for line_no, (target, is_debit, amount) in enumerate(lines, start=1):
            JournalLine.objects.create(
                entry=entry,
                posting_batch=batch,
                entity=cls.entity,
                entityfin=cls.entityfin,
                subentity=cls.branch,
                txn_type=txn_type,
                txn_id=txn_id,
                detail_id=line_no,
                voucher_no=voucher_no,
                account=target,
                ledger=target.ledger,
                drcr=is_debit,
                amount=Decimal(amount),
                description=voucher_no,
                posting_date=posting_date,
                created_by=cls.user,
            )

    def _scope(self):
        return {
            "entity_id": self.entity.id,
            "entityfin_id": self.entityfin.id,
            "subentity_id": self.branch.id,
            "from_date": "2026-04-01",
            "to_date": "2026-04-30",
        }

    def test_dataset_a_reconciles_daybook_ledgers_and_financial_statements(self):
        scope = self._scope()
        daybook = build_daybook(**scope, page=1, page_size=100)
        trial_balance = build_trial_balance(**scope, account_group="ledger")
        ledger_summary = build_ledger_summary(**scope, group_by="ledger", page_size=100)
        profit_loss = build_profit_and_loss(**scope, group_by="ledger", stock_valuation_mode="none")
        balance_sheet = build_balance_sheet(**scope, group_by="ledger", stock_valuation_mode="none")

        self.assertEqual(daybook["totals"]["transaction_count"], 7)
        self.assertEqual(daybook["totals"]["debit_total"], "41040.00")
        self.assertEqual(daybook["totals"]["credit_total"], "41040.00")
        self.assertEqual(
            {row["voucher_number"] for row in daybook["results"]},
            {f"A{number}-{name}" for number, name in [
                (2, "SALE"), (3, "RECEIPT"), (4, "PURCHASE"), (5, "PAYMENT"),
                (6, "ACCRUAL"), (7, "REVERSAL"), (8, "TRANSFER"),
            ]},
        )

        tb_rows = {row["ledger_name"]: row for row in trial_balance["rows"]}
        self.assertEqual(trial_balance["totals"]["closing_debit"], "111800.00")
        self.assertEqual(trial_balance["totals"]["closing_credit"], "111800.00")
        self.assertEqual(tb_rows["Main Bank"]["closing"], "102080.00")
        self.assertEqual(tb_rows["Cash In Hand"]["closing"], "5000.00")
        self.assertEqual(tb_rows["Service Customer"]["closing"], "0.00")
        self.assertEqual(tb_rows["Service Vendor"]["closing"], "0.00")

        summary_rows = {row["ledger_name"]: row for row in ledger_summary["rows"]}
        self.assertEqual(ledger_summary["totals"]["balance_debit"], "111800.00")
        self.assertEqual(ledger_summary["totals"]["balance_credit"], "111800.00")
        self.assertEqual(summary_rows["Input CGST"]["balance"], "360.00")
        self.assertEqual(summary_rows["Output CGST"]["balance"], "-900.00")

        self.assertEqual(profit_loss["totals"]["income"], "10000.00")
        self.assertEqual(profit_loss["totals"]["expense"], "4000.00")
        self.assertEqual(profit_loss["totals"]["net_profit"], "6000.00")

        self.assertEqual(balance_sheet["totals"]["assets"], "107800.00")
        self.assertEqual(balance_sheet["totals"]["liabilities_and_equity"], "107800.00")
        self.assertEqual(balance_sheet["summary"]["net_profit_brought_to_equity"], "6000.00")
        self.assertEqual(balance_sheet["summary"]["balance_difference"], "0.00")

    def test_dataset_a_excludes_draft_and_reversed_entries_from_active_books(self):
        self._entry(
            TxnType.JOURNAL,
            90,
            "A90-CONFIRMED-NOT-POSTED",
            "2026-04-09",
            [(self.bank, True, "777.00"), (self.service_revenue, False, "777.00")],
            status=EntryStatus.DRAFT,
        )
        self._entry(
            TxnType.JOURNAL,
            91,
            "A91-REVERSED",
            "2026-04-10",
            [(self.bank, True, "888.00"), (self.service_revenue, False, "888.00")],
            status=EntryStatus.REVERSED,
        )
        scope = self._scope()

        active_daybook = build_daybook(**scope, posted=True, page=1, page_size=100)
        inactive_daybook = build_daybook(**scope, posted=False, page=1, page_size=100)
        trial_balance = build_trial_balance(**scope, account_group="ledger", posted_only=True)
        profit_loss = build_profit_and_loss(
            **scope,
            group_by="ledger",
            posted_only=True,
            stock_valuation_mode="none",
        )
        balance_sheet = build_balance_sheet(
            **scope,
            group_by="ledger",
            posted_only=True,
            stock_valuation_mode="none",
        )

        self.assertEqual(active_daybook["count"], 7)
        self.assertEqual(active_daybook["totals"]["debit_total"], "41040.00")
        self.assertEqual(inactive_daybook["count"], 2)
        self.assertEqual(
            {row["voucher_number"]: row["status_name"] for row in inactive_daybook["results"]},
            {
                "A90-CONFIRMED-NOT-POSTED": "Draft",
                "A91-REVERSED": "Reversed",
            },
        )
        self.assertEqual(trial_balance["totals"]["closing_debit"], "111800.00")
        self.assertEqual(trial_balance["totals"]["closing_credit"], "111800.00")
        self.assertEqual(profit_loss["totals"]["net_profit"], "6000.00")
        self.assertEqual(balance_sheet["summary"]["balance_difference"], "0.00")
        self.assertEqual(balance_sheet["totals"]["assets"], "107800.00")

    def test_dataset_a_subledgers_reconcile_before_and_after_full_settlement(self):
        common_scope = {
            "entity_id": self.entity.id,
            "entityfin_id": self.entityfin.id,
            "subentity_id": self.branch.id,
            "from_date": "2026-04-01",
        }

        receivables_before = build_customer_outstanding_report(
            **common_scope,
            to_date="2026-04-02",
            customer_id=self.customer.id,
        )
        receivables_after = build_customer_outstanding_report(
            **common_scope,
            to_date="2026-04-30",
            customer_id=self.customer.id,
        )
        payables_before = build_vendor_outstanding_report(
            **common_scope,
            to_date="2026-04-04",
            vendor_id=self.vendor.id,
        )
        payables_after = build_vendor_outstanding_report(
            **common_scope,
            to_date="2026-04-30",
            vendor_id=self.vendor.id,
            show_settled=True,
            include_zero_balance=True,
        )

        self.assertEqual(receivables_before["totals"]["invoice_amount"], "11800.00")
        self.assertEqual(receivables_before["totals"]["net_outstanding"], "11800.00")
        self.assertEqual(receivables_after["totals"]["invoice_amount"], "11800.00")
        self.assertEqual(receivables_after["totals"]["net_outstanding"], "0.00")

        self.assertEqual(payables_before["totals"]["bill_amount"], "4720.00")
        self.assertEqual(payables_before["totals"]["outstanding"], "4720.00")
        self.assertEqual(payables_after["totals"]["bill_amount"], "4720.00")
        self.assertEqual(payables_after["totals"]["outstanding"], "0.00")

        trial_balance = build_trial_balance(**self._scope(), account_group="ledger")
        tb_rows = {row["ledger_name"]: row for row in trial_balance["rows"]}
        self.assertEqual(tb_rows["Service Customer"]["closing"], receivables_after["totals"]["net_outstanding"])
        self.assertEqual(tb_rows["Service Vendor"]["closing"], payables_after["totals"]["outstanding"])

    def test_dataset_a_gst_registers_reconcile_to_tax_control_ledgers(self):
        params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.branch.id,
            "from_date": "2026-04-01",
            "to_date": "2026-04-30",
        }

        gstr1_service = Gstr1Service()
        outward_qs, _ = gstr1_service.apply_filters(gstr1_service.get_base_queryset(), params)
        outward_totals = gstr1_service.calculate_totals(gstr1_service.annotate_register_fields(outward_qs))

        purchase_service = PurchaseRegisterService()
        inward_qs, _ = purchase_service.apply_filters(
            purchase_service.get_base_queryset(),
            {**params, "itc_eligibility": True},
        )
        inward_totals = purchase_service.calculate_totals(
            purchase_service.annotate_register_fields(inward_qs)
        )

        self.assertEqual(outward_totals["document_count"], 1)
        self.assertEqual(outward_totals["taxable_amount"], Decimal("10000.00"))
        self.assertEqual(outward_totals["cgst_amount"], Decimal("900.00"))
        self.assertEqual(outward_totals["sgst_amount"], Decimal("900.00"))
        self.assertEqual(inward_totals["document_count"], 1)
        self.assertEqual(inward_totals["taxable_amount"], Decimal("4000.00"))
        self.assertEqual(inward_totals["cgst_amount"], Decimal("360.00"))
        self.assertEqual(inward_totals["sgst_amount"], Decimal("360.00"))

        output_tax = outward_totals["cgst_amount"] + outward_totals["sgst_amount"]
        eligible_input_tax = inward_totals["cgst_amount"] + inward_totals["sgst_amount"]
        self.assertEqual(output_tax, Decimal("1800.00"))
        self.assertEqual(eligible_input_tax, Decimal("720.00"))
        self.assertEqual(output_tax - eligible_input_tax, Decimal("1080.00"))

        trial_balance = build_trial_balance(**self._scope(), account_group="ledger")
        tb_rows = {row["ledger_name"]: Decimal(row["closing"]) for row in trial_balance["rows"]}
        ledger_net_liability = (
            abs(tb_rows["Output CGST"])
            + abs(tb_rows["Output SGST"])
            - tb_rows["Input CGST"]
            - tb_rows["Input SGST"]
        )
        self.assertEqual(ledger_net_liability, output_tax - eligible_input_tax)


class TradingEntityAccountingTruthMatrixTests(TestCase):
    """Dataset B: trading activity, FIFO stock, GST, settlements, and statements agree."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="trading-oracle",
            email="trading-oracle@example.com",
            password="pass123",
        )
        gst_type = GstRegistrationType.objects.create(Name="Trading Regular", Description="Regular")
        cls.entity = Entity.objects.create(
            entityname="Dataset B Trading Entity",
            legalname="Dataset B Trading Entity",
            GstRegitrationType=gst_type,
            createdby=cls.user,
        )
        cls.branch = SubEntity.objects.create(entity=cls.entity, subentityname="Head Office")
        cls.entityfin = EntityFinancialYear.objects.create(
            entity=cls.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=cls.user,
        )

        current_asset = cls._account_type("Current Assets", "B1003", True)
        current_liability = cls._account_type("Current Liabilities", "B1006", False)
        equity = cls._account_type("Capital and Equity", "B1012", False)
        trading = cls._account_type("Trading Accounts", "B4000", True)

        cls.bank = cls._account("Trading Bank", 2101, current_asset, "Debit", 3)
        cls.customer = cls._account("Trading Customer", 2102, current_asset, "Debit", 3, is_party=True)
        cls.input_cgst = cls._account("Trading Input CGST", 2103, current_asset, "Debit", 3)
        cls.input_sgst = cls._account("Trading Input SGST", 2104, current_asset, "Debit", 3)
        cls.vendor = cls._account("Trading Vendor", 2201, current_liability, "Credit", 3, is_party=True)
        cls.output_cgst = cls._account("Trading Output CGST", 2202, current_liability, "Credit", 3)
        cls.output_sgst = cls._account("Trading Output SGST", 2203, current_liability, "Credit", 3)
        cls.capital = cls._account("Trading Capital", 2301, equity, "Credit", 3)
        cls.purchases = cls._account("Goods Purchases", 2401, trading, "Debit", 1)
        cls.purchase_returns = cls._account("Purchase Returns", 2402, trading, "Credit", 1)
        cls.sales = cls._account("Goods Sales", 2403, trading, "Credit", 1)
        cls.sales_returns = cls._account("Sales Returns", 2404, trading, "Debit", 1)
        cls.freight = cls._account("Carriage Inward", 2405, trading, "Debit", 1)

        apply_normalized_profile_payload(
            cls.customer,
            compliance_data={},
            commercial_data={"partytype": "Customer", "currency": "INR"},
            primary_address_data={},
        )
        apply_normalized_profile_payload(
            cls.vendor,
            compliance_data={},
            commercial_data={"partytype": "Vendor", "currency": "INR"},
            primary_address_data={},
        )

        category = ProductCategory.objects.create(entity=cls.entity, pcategoryname="Trading Goods")
        cls.uom = UnitOfMeasure.objects.create(entity=cls.entity, code="NOS", uqc="NOS")
        cls.product = Product.objects.create(
            entity=cls.entity,
            productname="Dataset B Product",
            sku="DATASET-B-001",
            productcategory=category,
            base_uom=cls.uom,
            purchase_account=cls.purchases,
            sales_account=cls.sales,
        )

        cls.purchase_invoice = PurchaseInvoiceHeader.objects.create(
            id=102,
            entity=cls.entity,
            entityfinid=cls.entityfin,
            subentity=cls.branch,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date="2026-04-02",
            posting_date="2026-04-02",
            doc_code="PINV",
            doc_no=102,
            purchase_number="B2-PURCHASE",
            supplier_invoice_number="B2-SUPPLIER",
            vendor=cls.vendor,
            vendor_ledger=cls.vendor.ledger,
            vendor_name=cls.vendor.accountname,
            vendor_gstin="29ABCDE5678F1Z5",
            total_taxable=Decimal("12000.00"),
            total_cgst=Decimal("1080.00"),
            total_sgst=Decimal("1080.00"),
            total_gst=Decimal("2160.00"),
            grand_total=Decimal("14160.00"),
            created_by=cls.user,
        )
        cls.purchase_return = PurchaseInvoiceHeader.objects.create(
            id=104,
            entity=cls.entity,
            entityfinid=cls.entityfin,
            subentity=cls.branch,
            doc_type=PurchaseInvoiceHeader.DocType.CREDIT_NOTE,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date="2026-04-04",
            posting_date="2026-04-04",
            doc_code="PCN",
            doc_no=104,
            purchase_number="B4-PURCHASE-RETURN",
            supplier_invoice_number="B4-SUPPLIER-CN",
            vendor=cls.vendor,
            vendor_ledger=cls.vendor.ledger,
            vendor_name=cls.vendor.accountname,
            vendor_gstin="29ABCDE5678F1Z5",
            total_taxable=Decimal("1200.00"),
            total_cgst=Decimal("108.00"),
            total_sgst=Decimal("108.00"),
            total_gst=Decimal("216.00"),
            grand_total=Decimal("1416.00"),
            ref_document=cls.purchase_invoice,
            affects_inventory=True,
            created_by=cls.user,
        )
        cls.sales_invoice = SalesInvoiceHeader.objects.create(
            id=105,
            entity=cls.entity,
            entityfinid=cls.entityfin,
            subentity=cls.branch,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2026-04-05",
            posting_date="2026-04-05",
            doc_code="SINV",
            doc_no=105,
            invoice_number="B5-SALE",
            customer=cls.customer,
            customer_ledger=cls.customer.ledger,
            customer_name=cls.customer.accountname,
            customer_gstin="29ABCDE1234F1Z5",
            customer_state_code="29",
            seller_gstin="29AAAAA9999A1Z5",
            seller_state_code="29",
            place_of_supply_state_code="29",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            total_taxable_value=Decimal("16000.00"),
            total_cgst=Decimal("1440.00"),
            total_sgst=Decimal("1440.00"),
            grand_total=Decimal("18880.00"),
            created_by=cls.user,
        )
        cls.sales_return = SalesInvoiceHeader.objects.create(
            id=106,
            entity=cls.entity,
            entityfinid=cls.entityfin,
            subentity=cls.branch,
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2026-04-06",
            posting_date="2026-04-06",
            doc_code="SCN",
            doc_no=106,
            invoice_number="B6-SALES-RETURN",
            customer=cls.customer,
            customer_ledger=cls.customer.ledger,
            customer_name=cls.customer.accountname,
            customer_gstin="29ABCDE1234F1Z5",
            customer_state_code="29",
            seller_gstin="29AAAAA9999A1Z5",
            seller_state_code="29",
            place_of_supply_state_code="29",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            total_taxable_value=Decimal("1000.00"),
            total_cgst=Decimal("90.00"),
            total_sgst=Decimal("90.00"),
            grand_total=Decimal("1180.00"),
            original_invoice=cls.sales_invoice,
            affects_inventory=True,
            created_by=cls.user,
        )

        cls._entry(TxnType.OPENING_BALANCE, 101, "B1-OPENING", "2026-04-01", [
            (cls.bank, True, "100000.00"),
            (cls.capital, False, "100000.00"),
        ])
        purchase_entry, purchase_batch = cls._entry(TxnType.PURCHASE, 102, "B2-PURCHASE", "2026-04-02", [
            (cls.purchases, True, "12000.00"),
            (cls.input_cgst, True, "1080.00"),
            (cls.input_sgst, True, "1080.00"),
            (cls.vendor, False, "14160.00"),
        ])
        cls._inventory_move(purchase_entry, purchase_batch, "100", InventoryMove.MoveType.IN_, InventoryMove.MovementNature.PURCHASE)
        cls._entry(TxnType.JOURNAL_BANK, 103, "B3-FREIGHT", "2026-04-03", [
            (cls.freight, True, "1200.00"),
            (cls.bank, False, "1200.00"),
        ])
        purchase_return_entry, purchase_return_batch = cls._entry(
            TxnType.PURCHASE_CREDIT_NOTE,
            104,
            "B4-PURCHASE-RETURN",
            "2026-04-04",
            [
                (cls.vendor, True, "1416.00"),
                (cls.purchase_returns, False, "1200.00"),
                (cls.input_cgst, False, "108.00"),
                (cls.input_sgst, False, "108.00"),
            ],
        )
        cls._inventory_move(purchase_return_entry, purchase_return_batch, "10", InventoryMove.MoveType.OUT, InventoryMove.MovementNature.RETURN)
        sale_entry, sale_batch = cls._entry(TxnType.SALES, 105, "B5-SALE", "2026-04-05", [
            (cls.customer, True, "18880.00"),
            (cls.sales, False, "16000.00"),
            (cls.output_cgst, False, "1440.00"),
            (cls.output_sgst, False, "1440.00"),
        ])
        cls._inventory_move(sale_entry, sale_batch, "80", InventoryMove.MoveType.OUT, InventoryMove.MovementNature.SALE)
        sales_return_entry, sales_return_batch = cls._entry(
            TxnType.SALES_CREDIT_NOTE,
            106,
            "B6-SALES-RETURN",
            "2026-04-06",
            [
                (cls.sales_returns, True, "1000.00"),
                (cls.output_cgst, True, "90.00"),
                (cls.output_sgst, True, "90.00"),
                (cls.customer, False, "1180.00"),
            ],
        )
        cls._inventory_move(sales_return_entry, sales_return_batch, "5", InventoryMove.MoveType.IN_, InventoryMove.MovementNature.RETURN)
        cls._entry(TxnType.RECEIPT, 107, "B7-RECEIPT", "2026-04-07", [
            (cls.bank, True, "17700.00"),
            (cls.customer, False, "17700.00"),
        ])
        cls._entry(TxnType.PAYMENT, 108, "B8-PAYMENT", "2026-04-08", [
            (cls.vendor, True, "12744.00"),
            (cls.bank, False, "12744.00"),
        ])

    @classmethod
    def _account_type(cls, name, code, debit_nature):
        return accounttype.objects.create(
            entity=cls.entity,
            accounttypename=name,
            accounttypecode=code,
            balanceType=debit_nature,
            createdby=cls.user,
        )

    @classmethod
    def _account(cls, name, code, account_type, side, statement_group, is_party=False):
        head = accountHead.objects.create(
            entity=cls.entity,
            name=f"{name} Head",
            code=code,
            balanceType=side,
            drcreffect=side,
            detailsingroup=statement_group,
            accounttype=account_type,
            createdby=cls.user,
        )
        ledger = Ledger.objects.create(
            entity=cls.entity,
            ledger_code=code,
            name=name,
            accounthead=head,
            accounttype=account_type,
            is_party=is_party,
            createdby=cls.user,
        )
        return account.objects.create(entity=cls.entity, ledger=ledger, accountname=name, createdby=cls.user)

    @classmethod
    def _entry(cls, txn_type, txn_id, voucher_no, posting_date, lines):
        batch = PostingBatch.objects.create(
            entity=cls.entity,
            entityfin=cls.entityfin,
            subentity=cls.branch,
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=voucher_no,
            created_by=cls.user,
        )
        entry = Entry.objects.create(
            entity=cls.entity,
            entityfin=cls.entityfin,
            subentity=cls.branch,
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=voucher_no,
            voucher_date=posting_date,
            posting_date=posting_date,
            status=EntryStatus.POSTED,
            posting_batch=batch,
            narration=voucher_no,
            created_by=cls.user,
        )
        for line_no, (target, is_debit, amount) in enumerate(lines, start=1):
            JournalLine.objects.create(
                entry=entry,
                posting_batch=batch,
                entity=cls.entity,
                entityfin=cls.entityfin,
                subentity=cls.branch,
                txn_type=txn_type,
                txn_id=txn_id,
                detail_id=line_no,
                voucher_no=voucher_no,
                account=target,
                ledger=target.ledger,
                drcr=is_debit,
                amount=Decimal(amount),
                description=voucher_no,
                posting_date=posting_date,
                created_by=cls.user,
            )
        return entry, batch

    @classmethod
    def _inventory_move(
        cls,
        entry,
        batch,
        qty,
        move_type,
        movement_nature,
        *,
        product=None,
        unit_cost="120.0000",
        location=None,
        batch_number="",
    ):
        quantity = Decimal(qty)
        cost = Decimal(unit_cost)
        InventoryMove.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=cls.entity,
            entityfin=cls.entityfin,
            subentity=cls.branch,
            txn_type=entry.txn_type,
            txn_id=entry.txn_id,
            detail_id=1,
            voucher_no=entry.voucher_no,
            product=product or cls.product,
            batch_number=batch_number,
            location=location,
            source_location=location if move_type == InventoryMove.MoveType.OUT else None,
            destination_location=location if move_type == InventoryMove.MoveType.IN_ else None,
            uom=cls.uom,
            base_uom=cls.uom,
            qty=quantity,
            base_qty=quantity,
            unit_cost=cost,
            ext_cost=quantity * cost,
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=move_type,
            movement_nature=movement_nature,
            posting_date=entry.posting_date,
            created_by=cls.user,
        )

    def _scope(self):
        return {
            "entity_id": self.entity.id,
            "entityfin_id": self.entityfin.id,
            "subentity_id": self.branch.id,
            "from_date": "2026-04-01",
            "to_date": "2026-04-30",
        }

    def test_dataset_b_reconciles_inventory_trading_gst_and_financial_statements(self):
        scope = self._scope()
        daybook = build_daybook(**scope, page=1, page_size=100)
        trial_balance = build_trial_balance(**scope, account_group="ledger")
        ledger_summary = build_ledger_summary(**scope, group_by="ledger", page_size=100)
        trading = build_trading_account_dynamic(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.branch.id,
            startdate="2026-04-01",
            enddate="2026-04-30",
            valuation_method="fifo",
        )
        profit_loss = build_profit_and_loss(**scope, group_by="ledger", stock_valuation_mode="fifo")
        balance_sheet = build_balance_sheet(**scope, group_by="ledger", stock_valuation_mode="fifo")
        inventory_rows, closing_qty, closing_value = inventory_breakdown_asof(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.branch.id,
            enddate="2026-04-30",
            method="fifo",
        )

        self.assertEqual(daybook["totals"]["transaction_count"], 7)
        self.assertEqual(daybook["totals"]["debit_total"], "67280.00")
        self.assertEqual(daybook["totals"]["credit_total"], "67280.00")
        self.assertEqual(trial_balance["totals"]["closing_debit"], "119900.00")
        self.assertEqual(trial_balance["totals"]["closing_credit"], "119900.00")

        tb_rows = {row["ledger_name"]: row for row in trial_balance["rows"]}
        self.assertEqual(tb_rows["Trading Bank"]["closing"], "103756.00")
        self.assertEqual(tb_rows["Trading Customer"]["closing"], "0.00")
        self.assertEqual(tb_rows["Trading Vendor"]["closing"], "0.00")
        self.assertEqual(tb_rows["Trading Input CGST"]["closing"], "972.00")
        self.assertEqual(tb_rows["Trading Output CGST"]["closing"], "-1350.00")

        summary_rows = {row["ledger_name"]: row for row in ledger_summary["rows"]}
        self.assertEqual(summary_rows["Goods Purchases"]["balance"], "12000.00")
        self.assertEqual(summary_rows["Purchase Returns"]["balance"], "-1200.00")
        self.assertEqual(summary_rows["Goods Sales"]["balance"], "-16000.00")
        self.assertEqual(summary_rows["Sales Returns"]["balance"], "1000.00")

        self.assertEqual(closing_qty, Decimal("15.00"))
        self.assertEqual(closing_value, Decimal("1800.00"))
        self.assertEqual(inventory_rows[0]["product_name"], "Dataset B Product")
        self.assertEqual(Decimal(str(trading["closing_stock"])), Decimal("1800.0"))
        self.assertEqual(Decimal(str(trading["gross_profit"])), Decimal("4800.0"))

        self.assertEqual(profit_loss["totals"]["net_profit"], "4800.00")
        self.assertEqual(balance_sheet["totals"]["assets"], "107500.00")
        self.assertEqual(balance_sheet["totals"]["liabilities_and_equity"], "107500.00")
        self.assertEqual(balance_sheet["summary"]["balance_difference"], "0.00")

        input_gst = Decimal(tb_rows["Trading Input CGST"]["closing"]) + Decimal(tb_rows["Trading Input SGST"]["closing"])
        output_gst = abs(Decimal(tb_rows["Trading Output CGST"]["closing"])) + abs(Decimal(tb_rows["Trading Output SGST"]["closing"]))
        self.assertEqual(input_gst, Decimal("1944.00"))
        self.assertEqual(output_gst, Decimal("2700.00"))
        self.assertEqual(output_gst - input_gst, Decimal("756.00"))

        register_params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.branch.id,
            "from_date": "2026-04-01",
            "to_date": "2026-04-30",
        }
        purchase_service = PurchaseRegisterService()
        purchase_qs, _ = purchase_service.apply_filters(purchase_service.get_base_queryset(), register_params)
        purchase_totals = purchase_service.calculate_totals(purchase_service.annotate_register_fields(purchase_qs))
        outward_service = Gstr1Service()
        outward_qs, _ = outward_service.apply_filters(outward_service.get_base_queryset(), register_params)
        outward_totals = outward_service.calculate_totals(outward_service.annotate_register_fields(outward_qs))

        self.assertEqual(purchase_totals["document_count"], 2)
        self.assertEqual(purchase_totals["taxable_amount"], Decimal("10800.00"))
        self.assertEqual(purchase_totals["cgst_amount"], Decimal("972.00"))
        self.assertEqual(purchase_totals["sgst_amount"], Decimal("972.00"))
        self.assertEqual(outward_totals["document_count"], 2)
        self.assertEqual(outward_totals["taxable_amount"], Decimal("15000.00"))
        self.assertEqual(outward_totals["cgst_amount"], Decimal("1350.00"))
        self.assertEqual(outward_totals["sgst_amount"], Decimal("1350.00"))

    def test_dataset_b_variant_1_capitalized_landed_cost_reconciles_fifo_and_mwa(self):
        trading_type = self.purchases.ledger.accounttype
        layered_purchases = self._account(
            "Layered Landed Purchases", 2491, trading_type, "Debit", 1
        )
        layered_sales = self._account(
            "Layered Goods Sales", 2492, trading_type, "Credit", 1
        )
        layered_product = Product.objects.create(
            entity=self.entity,
            productname="Dataset B Layered Product",
            sku="DATASET-B-LAYERED-001",
            productcategory=self.product.productcategory,
            base_uom=self.uom,
            purchase_account=layered_purchases,
            sales_account=layered_sales,
        )

        first_entry, first_batch = self._entry(
            TxnType.PURCHASE,
            901,
            "B-V1-PURCHASE-1",
            "2026-04-10",
            [(layered_purchases, True, "11000.00"), (self.vendor, False, "11000.00")],
        )
        self._inventory_move(
            first_entry,
            first_batch,
            "100",
            InventoryMove.MoveType.IN_,
            InventoryMove.MovementNature.PURCHASE,
            product=layered_product,
            unit_cost="110.0000",
        )
        second_entry, second_batch = self._entry(
            TxnType.PURCHASE,
            902,
            "B-V1-PURCHASE-2",
            "2026-04-11",
            [(layered_purchases, True, "9000.00"), (self.vendor, False, "9000.00")],
        )
        self._inventory_move(
            second_entry,
            second_batch,
            "50",
            InventoryMove.MoveType.IN_,
            InventoryMove.MovementNature.PURCHASE,
            product=layered_product,
            unit_cost="180.0000",
        )
        sale_entry, sale_batch = self._entry(
            TxnType.SALES,
            903,
            "B-V1-SALE",
            "2026-04-12",
            [(self.customer, True, "30000.00"), (layered_sales, False, "30000.00")],
        )
        self._inventory_move(
            sale_entry,
            sale_batch,
            "120",
            InventoryMove.MoveType.OUT,
            InventoryMove.MovementNature.SALE,
            product=layered_product,
            unit_cost="0.0000",
        )

        valuation_scope = {
            "entity_id": self.entity.id,
            "entityfin_id": self.entityfin.id,
            "subentity_id": self.branch.id,
            "enddate": "2026-04-30",
            "product_ids": [layered_product.id],
        }
        fifo_rows, fifo_qty, fifo_value = inventory_breakdown_asof(
            **valuation_scope, method="fifo"
        )
        mwa_rows, mwa_qty, mwa_value = inventory_breakdown_asof(
            **valuation_scope, method="mwa"
        )
        trading_scope = {
            "entity_id": self.entity.id,
            "entityfin_id": self.entityfin.id,
            "subentity_id": self.branch.id,
            "startdate": "2026-04-01",
            "enddate": "2026-04-30",
            "ledger_ids": [layered_purchases.ledger_id, layered_sales.ledger_id],
            "inventory_product_ids": [layered_product.id],
        }
        fifo_trading = build_trading_account_dynamic(**trading_scope, valuation_method="fifo")
        mwa_trading = build_trading_account_dynamic(**trading_scope, valuation_method="mwa")

        self.assertEqual(fifo_qty, Decimal("30.00"))
        self.assertEqual(mwa_qty, Decimal("30.00"))
        self.assertEqual(fifo_value, Decimal("5400.00"))
        self.assertEqual(mwa_value, Decimal("4000.00"))
        self.assertEqual(Decimal(str(fifo_rows[0]["rate"])), Decimal("180.00"))
        self.assertEqual(Decimal(str(mwa_rows[0]["rate"])), Decimal("133.33"))
        self.assertEqual(Decimal(str(fifo_trading["cogs_from_issues"])), Decimal("14600.0"))
        self.assertEqual(Decimal(str(mwa_trading["cogs_from_issues"])), Decimal("16000.0"))
        self.assertEqual(Decimal(str(fifo_trading["gross_profit"])), Decimal("15400.0"))
        self.assertEqual(Decimal(str(mwa_trading["gross_profit"])), Decimal("14000.0"))

    def test_dataset_b_variant_2_discount_cess_roundoff_reconciles_books_and_profit(self):
        current_asset_type = self.input_cgst.ledger.accounttype
        current_liability_type = self.output_cgst.ledger.accounttype
        trading_type = self.purchases.ledger.accounttype
        indirect_expense_type = self._account_type("Variant Indirect Expenses", "B5200", True)

        variant_purchases = self._account(
            "Variant Discounted Purchases", 2591, trading_type, "Debit", 1
        )
        variant_sales = self._account(
            "Variant Discounted Sales", 2592, trading_type, "Credit", 1
        )
        variant_input_cgst = self._account(
            "Variant Input CGST", 2589, current_asset_type, "Debit", 3
        )
        variant_input_sgst = self._account(
            "Variant Input SGST", 2590, current_asset_type, "Debit", 3
        )
        input_cess = self._account(
            "Variant Input CESS", 2593, current_asset_type, "Debit", 3
        )
        variant_output_cgst = self._account(
            "Variant Output CGST", 2596, current_liability_type, "Credit", 3
        )
        variant_output_sgst = self._account(
            "Variant Output SGST", 2597, current_liability_type, "Credit", 3
        )
        output_cess = self._account(
            "Variant Output CESS", 2594, current_liability_type, "Credit", 3
        )
        roundoff_expense = self._account(
            "Variant Round-off Expense", 2595, indirect_expense_type, "Debit", 2
        )
        variant_product = Product.objects.create(
            entity=self.entity,
            productname="Dataset B Discount CESS Product",
            sku="DATASET-B-TAX-001",
            productcategory=self.product.productcategory,
            base_uom=self.uom,
            purchase_account=variant_purchases,
            sales_account=variant_sales,
        )

        purchase_entry, purchase_batch = self._entry(
            TxnType.PURCHASE,
            911,
            "B-V2-PURCHASE",
            "2026-04-20",
            [
                (variant_purchases, True, "900.00"),
                (variant_input_cgst, True, "81.00"),
                (variant_input_sgst, True, "81.00"),
                (input_cess, True, "28.00"),
                (roundoff_expense, True, "0.25"),
                (self.vendor, False, "1090.25"),
            ],
        )
        self._inventory_move(
            purchase_entry,
            purchase_batch,
            "10",
            InventoryMove.MoveType.IN_,
            InventoryMove.MovementNature.PURCHASE,
            product=variant_product,
            unit_cost="90.0000",
        )
        sale_entry, sale_batch = self._entry(
            TxnType.SALES,
            912,
            "B-V2-SALE",
            "2026-04-21",
            [
                (self.customer, True, "1089.80"),
                (roundoff_expense, True, "0.20"),
                (variant_sales, False, "900.00"),
                (variant_output_cgst, False, "81.00"),
                (variant_output_sgst, False, "81.00"),
                (output_cess, False, "28.00"),
            ],
        )
        self._inventory_move(
            sale_entry,
            sale_batch,
            "5",
            InventoryMove.MoveType.OUT,
            InventoryMove.MovementNature.SALE,
            product=variant_product,
            unit_cost="0.0000",
        )

        trading = build_trading_account_dynamic(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.branch.id,
            startdate="2026-04-01",
            enddate="2026-04-30",
            ledger_ids=[variant_purchases.ledger_id, variant_sales.ledger_id],
            inventory_product_ids=[variant_product.id],
            valuation_method="fifo",
        )
        profit_loss = build_profit_and_loss(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.branch.id,
            from_date="2026-04-01",
            to_date="2026-04-30",
            group_by="ledger",
            ledger_ids=[
                variant_purchases.ledger_id,
                variant_sales.ledger_id,
                roundoff_expense.ledger_id,
            ],
            trading_snapshot=trading,
        )
        trial_balance = build_trial_balance(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.branch.id,
            from_date="2026-04-01",
            to_date="2026-04-30",
            account_group="ledger",
            ledger_ids=[
                variant_purchases.ledger_id,
                variant_sales.ledger_id,
                variant_input_cgst.ledger_id,
                variant_input_sgst.ledger_id,
                input_cess.ledger_id,
                variant_output_cgst.ledger_id,
                variant_output_sgst.ledger_id,
                output_cess.ledger_id,
                roundoff_expense.ledger_id,
                self.vendor.ledger_id,
                self.customer.ledger_id,
            ],
        )
        tb_rows = {row["ledger_name"]: Decimal(row["closing"]) for row in trial_balance["rows"]}
        self.assertEqual(tb_rows["Variant Discounted Purchases"], Decimal("900.00"))
        self.assertEqual(tb_rows["Variant Discounted Sales"], Decimal("-900.00"))
        self.assertEqual(tb_rows["Variant Input CESS"], Decimal("28.00"))
        self.assertEqual(tb_rows["Variant Output CESS"], Decimal("-28.00"))
        self.assertEqual(tb_rows["Variant Round-off Expense"], Decimal("0.45"))
        self.assertEqual(tb_rows["Trading Vendor"], Decimal("-1090.25"))
        self.assertEqual(tb_rows["Trading Customer"], Decimal("1089.80"))
        self.assertEqual(trial_balance["totals"]["closing_debit"], "2180.25")
        self.assertEqual(trial_balance["totals"]["closing_credit"], "2180.25")
        self.assertEqual(Decimal(str(trading["closing_stock"])), Decimal("450.0"))
        self.assertEqual(Decimal(str(trading["cogs_from_issues"])), Decimal("450.0"))
        self.assertEqual(Decimal(str(trading["gross_profit"])), Decimal("450.0"))
        self.assertEqual(profit_loss["totals"]["expense"], "0.45")
        self.assertEqual(profit_loss["totals"]["net_profit"], "449.55")

    def test_dataset_b_variant_3_batch_location_partial_returns_reconcile(self):
        location_a = Godown.objects.create(
            entity=self.entity,
            subentity=self.branch,
            name="Variant 3 Main Warehouse",
            code="B-V3-MAIN",
            address="Warehouse A",
            city="Mumbai",
            state="MH",
            pincode="400001",
            is_active=True,
            is_default=True,
        )
        location_b = Godown.objects.create(
            entity=self.entity,
            subentity=self.branch,
            name="Variant 3 Secondary Warehouse",
            code="B-V3-SECONDARY",
            address="Warehouse B",
            city="Mumbai",
            state="MH",
            pincode="400002",
            is_active=True,
        )
        variant_product = Product.objects.create(
            entity=self.entity,
            productname="Dataset B Batch Location Product",
            sku="DATASET-B-LOC-001",
            productcategory=self.product.productcategory,
            base_uom=self.uom,
            purchase_account=self.purchases,
            sales_account=self.sales,
            is_batch_managed=True,
        )

        purchase_a, batch_a = self._entry(
            TxnType.PURCHASE,
            921,
            "B-V3-PURCHASE-A",
            "2026-04-22",
            [(self.purchases, True, "10000.00"), (self.vendor, False, "10000.00")],
        )
        self._inventory_move(
            purchase_a,
            batch_a,
            "100",
            InventoryMove.MoveType.IN_,
            InventoryMove.MovementNature.PURCHASE,
            product=variant_product,
            unit_cost="100.0000",
            location=location_a,
            batch_number="LOT-A",
        )
        purchase_b, batch_b = self._entry(
            TxnType.PURCHASE,
            922,
            "B-V3-PURCHASE-B",
            "2026-04-23",
            [(self.purchases, True, "6000.00"), (self.vendor, False, "6000.00")],
        )
        self._inventory_move(
            purchase_b,
            batch_b,
            "50",
            InventoryMove.MoveType.IN_,
            InventoryMove.MovementNature.PURCHASE,
            product=variant_product,
            unit_cost="120.0000",
            location=location_b,
            batch_number="LOT-B",
        )

        purchase_return, purchase_return_batch = self._entry(
            TxnType.PURCHASE_CREDIT_NOTE,
            923,
            "B-V3-PURCHASE-RETURN",
            "2026-04-24",
            [(self.vendor, True, "1200.00"), (self.purchase_returns, False, "1200.00")],
        )
        self._inventory_move(
            purchase_return,
            purchase_return_batch,
            "10",
            InventoryMove.MoveType.OUT,
            InventoryMove.MovementNature.RETURN,
            product=variant_product,
            unit_cost="120.0000",
            location=location_b,
            batch_number="LOT-B",
        )
        sale, sale_batch = self._entry(
            TxnType.SALES,
            924,
            "B-V3-SALE",
            "2026-04-25",
            [(self.customer, True, "4500.00"), (self.sales, False, "4500.00")],
        )
        self._inventory_move(
            sale,
            sale_batch,
            "30",
            InventoryMove.MoveType.OUT,
            InventoryMove.MovementNature.SALE,
            product=variant_product,
            unit_cost="100.0000",
            location=location_a,
            batch_number="LOT-A",
        )
        sales_return, sales_return_batch = self._entry(
            TxnType.SALES_CREDIT_NOTE,
            925,
            "B-V3-SALES-RETURN",
            "2026-04-26",
            [(self.sales_returns, True, "750.00"), (self.customer, False, "750.00")],
        )
        self._inventory_move(
            sales_return,
            sales_return_batch,
            "5",
            InventoryMove.MoveType.IN_,
            InventoryMove.MovementNature.RETURN,
            product=variant_product,
            unit_cost="100.0000",
            location=location_a,
            batch_number="LOT-A",
        )

        inventory_rows, closing_qty, closing_value = inventory_breakdown_asof(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.branch.id,
            enddate="2026-04-30",
            method="fifo",
            product_ids=[variant_product.id],
        )
        location_report = build_inventory_location_stock(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.branch.id,
            as_of_date="2026-04-30",
            valuation_method="fifo",
            product_ids=[variant_product.id],
            location_ids=[location_a.id, location_b.id],
            paginate=False,
        )
        trial_balance = build_trial_balance(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.branch.id,
            from_date="2026-04-22",
            to_date="2026-04-30",
            account_group="ledger",
        )
        daybook = build_daybook(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.branch.id,
            from_date="2026-04-22",
            to_date="2026-04-30",
            page=1,
            page_size=100,
        )

        locations = {row["location_id"]: row for row in location_report["rows"]}
        self.assertEqual(Decimal(locations[location_a.id]["closing_qty"]), Decimal("75.0000"))
        self.assertEqual(Decimal(locations[location_a.id]["closing_value"]), Decimal("7500.00"))
        self.assertEqual(Decimal(locations[location_b.id]["closing_qty"]), Decimal("40.0000"))
        self.assertEqual(Decimal(locations[location_b.id]["closing_value"]), Decimal("4800.00"))
        self.assertEqual(closing_qty, Decimal("115.00"))
        self.assertEqual(closing_value, Decimal("12300.00"))
        self.assertEqual(Decimal(str(inventory_rows[0]["value"])), Decimal("12300.0"))
        self.assertEqual(
            closing_value,
            sum((Decimal(row["closing_value"]) for row in locations.values()), Decimal("0.00")),
        )
        self.assertEqual(daybook["totals"]["transaction_count"], 5)
        self.assertEqual(daybook["totals"]["debit_total"], "22450.00")
        self.assertEqual(daybook["totals"]["credit_total"], "22450.00")
        self.assertEqual(
            trial_balance["totals"]["closing_debit"],
            trial_balance["totals"]["closing_credit"],
        )

    def test_dataset_b_variant_4_split_settlements_advances_and_reports_reconcile(self):
        current_asset_type = self.customer.ledger.accounttype
        current_liability_type = self.vendor.ledger.accounttype
        settlement_customer = self._account(
            "Variant Settlement Customer", 2691, current_asset_type, "Debit", 3, is_party=True
        )
        settlement_vendor = self._account(
            "Variant Settlement Vendor", 2692, current_liability_type, "Credit", 3, is_party=True
        )
        apply_normalized_profile_payload(
            settlement_customer,
            compliance_data={},
            commercial_data={"partytype": "Customer", "currency": "INR"},
            primary_address_data={},
        )
        apply_normalized_profile_payload(
            settlement_vendor,
            compliance_data={},
            commercial_data={"partytype": "Vendor", "currency": "INR"},
            primary_address_data={},
        )
        PurchaseSettings.objects.create(
            entity=self.entity,
            subentity=self.branch,
            policy_controls={
                "settlement_mode": "basic",
                "allocation_policy": "manual",
                "over_settlement_rule": "block",
            },
        )

        sales_invoice = SalesInvoiceHeader.objects.create(
            id=931,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.branch,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2026-04-27",
            posting_date="2026-04-27",
            doc_code="SINV",
            doc_no=931,
            invoice_number="B-V4-SALE",
            customer=settlement_customer,
            customer_ledger=settlement_customer.ledger,
            customer_name=settlement_customer.accountname,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            total_taxable_value=Decimal("10000.00"),
            grand_total=Decimal("10000.00"),
            outstanding_amount=Decimal("10000.00"),
            created_by=self.user,
        )
        customer_item = CustomerBillOpenItem.objects.create(
            header=sales_invoice,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.branch,
            customer=settlement_customer,
            customer_ledger=settlement_customer.ledger,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            bill_date=date(2026, 4, 27),
            due_date=date(2026, 5, 10),
            invoice_number=sales_invoice.invoice_number,
            original_amount=Decimal("10000.00"),
            gross_amount=Decimal("10000.00"),
            net_receivable_amount=Decimal("10000.00"),
            outstanding_amount=Decimal("10000.00"),
        )
        self._entry(TxnType.SALES, 931, "B-V4-SALE", "2026-04-27", [
            (settlement_customer, True, "10000.00"),
            (self.sales, False, "10000.00"),
        ])

        for txn_id, amount in ((932, "3000.00"), (933, "2000.00")):
            settlement = SalesArService.create_settlement(
                entity_id=self.entity.id,
                entityfinid_id=self.entityfin.id,
                subentity_id=self.branch.id,
                customer_id=settlement_customer.id,
                settlement_type=CustomerSettlement.SettlementType.RECEIPT,
                settlement_date=date(2026, 4, txn_id - 903),
                reference_no=f"B-V4-RECEIPT-{txn_id}",
                external_voucher_no=None,
                remarks="Dataset B split receipt",
                lines=[{"open_item_id": customer_item.id, "amount": Decimal(amount)}],
            ).settlement
            SalesArService.post_settlement(settlement_id=settlement.id, posted_by_id=self.user.id)
            self._entry(TxnType.RECEIPT, txn_id, f"B-V4-RECEIPT-{txn_id}", f"2026-04-{txn_id - 903:02d}", [
                (self.bank, True, amount),
                (settlement_customer, False, amount),
            ])

        customer_advance = SalesArService.create_advance_balance(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.branch.id,
            customer_id=settlement_customer.id,
            source_type=CustomerAdvanceBalance.SourceType.RECEIPT_ADVANCE,
            credit_date=date(2026, 4, 30),
            reference_no="B-V4-CUSTOMER-ADVANCE",
            remarks="Excess receipt held on account",
            amount=Decimal("1500.00"),
        )
        self._entry(TxnType.RECEIPT, 934, "B-V4-CUSTOMER-ADVANCE", "2026-04-30", [
            (self.bank, True, "1500.00"),
            (settlement_customer, False, "1500.00"),
        ])
        customer_adjustment = SalesArService.create_settlement(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.branch.id,
            customer_id=settlement_customer.id,
            settlement_type=CustomerSettlement.SettlementType.ADVANCE_ADJUSTMENT,
            settlement_date=date(2026, 5, 1),
            reference_no="B-V4-CUSTOMER-ADVANCE-APPLY",
            external_voucher_no=None,
            remarks="Partially apply customer advance",
            lines=[{"open_item_id": customer_item.id, "amount": Decimal("500.00")}],
            advance_balance_id=customer_advance.id,
        ).settlement
        SalesArService.post_settlement(settlement_id=customer_adjustment.id, posted_by_id=self.user.id)

        customer_item.refresh_from_db()
        customer_advance.refresh_from_db()
        self.assertEqual(customer_item.outstanding_amount, Decimal("4500.00"))
        self.assertEqual(customer_advance.outstanding_amount, Decimal("1000.00"))
        rejected_receipt = SalesArService.create_settlement(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.branch.id,
            customer_id=settlement_customer.id,
            settlement_type=CustomerSettlement.SettlementType.RECEIPT,
            settlement_date=date(2026, 5, 2),
            reference_no="B-V4-REJECTED-RECEIPT",
            external_voucher_no=None,
            remarks="Must not over-allocate",
            lines=[{"open_item_id": customer_item.id, "amount": Decimal("4500.02")}],
        ).settlement
        with self.assertRaisesRegex(ValueError, "exceeds outstanding"):
            SalesArService.post_settlement(settlement_id=rejected_receipt.id, posted_by_id=self.user.id)
        customer_item.refresh_from_db()
        self.assertEqual(customer_item.outstanding_amount, Decimal("4500.00"))

        purchase_invoice = PurchaseInvoiceHeader.objects.create(
            id=941,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.branch,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date="2026-04-27",
            due_date="2026-05-10",
            posting_date="2026-04-27",
            doc_code="PINV",
            doc_no=941,
            purchase_number="B-V4-PURCHASE",
            supplier_invoice_number="B-V4-SUPPLIER",
            vendor=settlement_vendor,
            vendor_ledger=settlement_vendor.ledger,
            vendor_name=settlement_vendor.accountname,
            total_taxable=Decimal("8000.00"),
            grand_total=Decimal("8000.00"),
            created_by=self.user,
        )
        vendor_item = VendorBillOpenItem.objects.create(
            header=purchase_invoice,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.branch,
            vendor=settlement_vendor,
            vendor_ledger=settlement_vendor.ledger,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            bill_date=date(2026, 4, 27),
            due_date=date(2026, 5, 10),
            purchase_number=purchase_invoice.purchase_number,
            supplier_invoice_number=purchase_invoice.supplier_invoice_number,
            original_amount=Decimal("8000.00"),
            gross_amount=Decimal("8000.00"),
            net_payable_amount=Decimal("8000.00"),
            outstanding_amount=Decimal("8000.00"),
        )
        self._entry(TxnType.PURCHASE, 941, "B-V4-PURCHASE", "2026-04-27", [
            (self.purchases, True, "8000.00"),
            (settlement_vendor, False, "8000.00"),
        ])

        for txn_id, amount in ((942, "2500.00"), (943, "1500.00")):
            settlement = PurchaseApService.create_settlement(
                entity_id=self.entity.id,
                entityfinid_id=self.entityfin.id,
                subentity_id=self.branch.id,
                vendor_id=settlement_vendor.id,
                settlement_type=VendorSettlement.SettlementType.PAYMENT,
                settlement_date=date(2026, 4, txn_id - 913),
                reference_no=f"B-V4-PAYMENT-{txn_id}",
                external_voucher_no=None,
                remarks="Dataset B split payment",
                lines=[{"open_item_id": vendor_item.id, "amount": Decimal(amount)}],
            ).settlement
            PurchaseApService.post_settlement(settlement_id=settlement.id, posted_by_id=self.user.id)
            self._entry(TxnType.PAYMENT, txn_id, f"B-V4-PAYMENT-{txn_id}", f"2026-04-{txn_id - 913:02d}", [
                (settlement_vendor, True, amount),
                (self.bank, False, amount),
            ])

        vendor_advance = PurchaseApService.create_advance_balance(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.branch.id,
            vendor_id=settlement_vendor.id,
            source_type=VendorAdvanceBalance.SourceType.PAYMENT_ADVANCE,
            credit_date=date(2026, 4, 30),
            reference_no="B-V4-VENDOR-ADVANCE",
            remarks="Excess payment held on account",
            amount=Decimal("1000.00"),
        )
        self._entry(TxnType.PAYMENT, 944, "B-V4-VENDOR-ADVANCE", "2026-04-30", [
            (settlement_vendor, True, "1000.00"),
            (self.bank, False, "1000.00"),
        ])
        vendor_adjustment = PurchaseApService.create_settlement(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.branch.id,
            vendor_id=settlement_vendor.id,
            settlement_type=VendorSettlement.SettlementType.ADVANCE_ADJUSTMENT,
            settlement_date=date(2026, 5, 1),
            reference_no="B-V4-VENDOR-ADVANCE-APPLY",
            external_voucher_no=None,
            remarks="Partially apply vendor advance",
            lines=[{"open_item_id": vendor_item.id, "amount": Decimal("400.00")}],
            advance_balance_id=vendor_advance.id,
        ).settlement
        PurchaseApService.post_settlement(settlement_id=vendor_adjustment.id, posted_by_id=self.user.id)

        vendor_item.refresh_from_db()
        vendor_advance.refresh_from_db()
        self.assertEqual(vendor_item.outstanding_amount, Decimal("3600.00"))
        self.assertEqual(vendor_advance.outstanding_amount, Decimal("600.00"))
        rejected_payment = PurchaseApService.create_settlement(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.branch.id,
            vendor_id=settlement_vendor.id,
            settlement_type=VendorSettlement.SettlementType.PAYMENT,
            settlement_date=date(2026, 5, 2),
            reference_no="B-V4-REJECTED-PAYMENT",
            external_voucher_no=None,
            remarks="Must not over-allocate",
            lines=[{"open_item_id": vendor_item.id, "amount": Decimal("3600.02")}],
        ).settlement
        with self.assertRaisesRegex(ValueError, "exceeds allocatable amount|exceeds outstanding"):
            PurchaseApService.post_settlement(settlement_id=rejected_payment.id, posted_by_id=self.user.id)
        vendor_item.refresh_from_db()
        self.assertEqual(vendor_item.outstanding_amount, Decimal("3600.00"))

        report_scope = {
            "entity_id": self.entity.id,
            "entityfin_id": self.entityfin.id,
            "subentity_id": self.branch.id,
            "from_date": "2026-04-27",
            "to_date": "2026-05-10",
        }
        receivables = build_customer_outstanding_report(
            **report_scope, customer_id=settlement_customer.id
        )
        payables = build_vendor_outstanding_report(
            **report_scope, vendor_id=settlement_vendor.id, view="summary"
        )
        trial_balance = build_trial_balance(
            **report_scope,
            account_group="ledger",
            ledger_ids=[settlement_customer.ledger_id, settlement_vendor.ledger_id],
        )
        daybook = build_daybook(**report_scope, page=1, page_size=100)

        receivable_row = receivables["rows"][0]
        payable_row = payables["rows"][0]
        trial_rows = {row["ledger_name"]: Decimal(row["closing"]) for row in trial_balance["rows"]}
        self.assertEqual(receivable_row["invoice_amount"], "10000.00")
        self.assertEqual(receivable_row["receipt_amount"], "5000.00")
        self.assertEqual(receivable_row["unapplied_receipt"], "1000.00")
        self.assertEqual(receivable_row["net_outstanding"], "3500.00")
        self.assertEqual(payable_row["bill_amount"], "8000.00")
        self.assertEqual(payable_row["payment_amount"], "4000.00")
        self.assertEqual(payable_row["advance_balance"], "600.00")
        self.assertEqual(payable_row["net_outstanding"], "3000.00")
        self.assertEqual(trial_rows["Variant Settlement Customer"], Decimal("3500.00"))
        self.assertEqual(trial_rows["Variant Settlement Vendor"], Decimal("-3000.00"))
        self.assertEqual(Decimal(receivable_row["net_outstanding"]), trial_rows["Variant Settlement Customer"])
        self.assertEqual(Decimal(payable_row["net_outstanding"]), abs(trial_rows["Variant Settlement Vendor"]))
        self.assertEqual(daybook["totals"]["transaction_count"], 8)
        self.assertEqual(daybook["totals"]["debit_total"], "29500.00")
        self.assertEqual(daybook["totals"]["credit_total"], "29500.00")

    def test_dataset_b_variant_5_igst_and_non_taxable_supplies_reconcile(self):
        """Inter-state GST and non-taxable classes must agree across books and returns."""
        current_asset = self.input_cgst.ledger.accounttype
        current_liability = self.output_cgst.ledger.accounttype
        trading = self.purchases.ledger.accounttype

        input_igst = self._account("Variant Input IGST", 2601, current_asset, "Debit", 3)
        output_igst = self._account("Variant Output IGST", 2602, current_liability, "Credit", 3)
        variant_vendor = self._account("Variant Tax Vendor", 2603, current_liability, "Credit", 3, is_party=True)
        variant_customer = self._account("Variant Tax Customer", 2604, current_asset, "Debit", 3, is_party=True)
        variant_purchases = self._account("Variant Goods Purchases", 2605, trading, "Debit", 1)
        variant_sales = self._account("Variant Goods Sales", 2606, trading, "Credit", 1)
        apply_normalized_profile_payload(
            variant_vendor,
            compliance_data={"gstno": "27ABCDE5678F1Z5", "gstregtype": "Regular"},
            commercial_data={"partytype": "Vendor", "currency": "INR"},
            primary_address_data={},
        )
        apply_normalized_profile_payload(
            variant_customer,
            compliance_data={"gstno": "27ABCDE1234F1Z5", "gstregtype": "Regular"},
            commercial_data={"partytype": "Customer", "currency": "INR"},
            primary_address_data={},
        )
        product = Product.objects.create(
            entity=self.entity,
            productname="Dataset B Taxability Product",
            sku="DATASET-B-TAX-001",
            productcategory=self.product.productcategory,
            base_uom=self.uom,
            purchase_account=variant_purchases,
            sales_account=variant_sales,
        )

        purchase_specs = [
            (951, "2026-05-04", PurchaseInvoiceHeader.Taxability.TAXABLE, "10000.00", "1800.00", "11800.00", "100", "100.0000"),
            (952, "2026-05-05", PurchaseInvoiceHeader.Taxability.EXEMPT, "1000.00", "0.00", "1000.00", "20", "50.0000"),
            (953, "2026-05-06", PurchaseInvoiceHeader.Taxability.NIL_RATED, "400.00", "0.00", "400.00", "10", "40.0000"),
            (954, "2026-05-07", PurchaseInvoiceHeader.Taxability.NON_GST, "100.00", "0.00", "100.00", "5", "20.0000"),
        ]
        purchase_headers = []
        for txn_id, posting_date, taxability, taxable, igst, grand_total, qty, unit_cost in purchase_specs:
            header = PurchaseInvoiceHeader.objects.create(
                id=txn_id,
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.branch,
                doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
                status=PurchaseInvoiceHeader.Status.POSTED,
                bill_date=posting_date,
                posting_date=posting_date,
                due_date="2026-05-31",
                doc_code="PINV",
                doc_no=txn_id,
                purchase_number=f"B-V5-PURCHASE-{txn_id}",
                supplier_invoice_number=f"B-V5-SUPPLIER-{txn_id}",
                vendor=variant_vendor,
                vendor_ledger=variant_vendor.ledger,
                vendor_name=variant_vendor.accountname,
                vendor_gstin="27ABCDE5678F1Z5",
                supply_category=PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                default_taxability=taxability,
                tax_regime=PurchaseInvoiceHeader.TaxRegime.INTER,
                is_itc_eligible=taxability == PurchaseInvoiceHeader.Taxability.TAXABLE,
                total_taxable=Decimal(taxable),
                total_igst=Decimal(igst),
                total_gst=Decimal(igst),
                grand_total=Decimal(grand_total),
                created_by=self.user,
            )
            PurchaseTaxSummary.objects.create(
                header=header,
                taxability=taxability,
                hsn_sac="100100",
                gst_rate=Decimal("18.00") if taxability == PurchaseInvoiceHeader.Taxability.TAXABLE else Decimal("0.00"),
                taxable_value=Decimal(taxable),
                igst_amount=Decimal(igst),
                total_value=Decimal(grand_total),
                itc_eligible_tax=Decimal(igst),
            )
            lines = [(variant_purchases, True, taxable)]
            if Decimal(igst):
                lines.append((input_igst, True, igst))
            lines.append((variant_vendor, False, grand_total))
            entry, batch = self._entry(TxnType.PURCHASE, txn_id, header.purchase_number, posting_date, lines)
            self._inventory_move(
                entry,
                batch,
                qty,
                InventoryMove.MoveType.IN_,
                InventoryMove.MovementNature.PURCHASE,
                product=product,
                unit_cost=unit_cost,
            )
            purchase_headers.append(header)

        sales_specs = [
            (961, "2026-05-08", SalesInvoiceHeader.Taxability.TAXABLE, "8000.00", "1440.00", "9440.00", "40"),
            (962, "2026-05-09", SalesInvoiceHeader.Taxability.EXEMPT, "800.00", "0.00", "800.00", "10"),
            (963, "2026-05-10", SalesInvoiceHeader.Taxability.NIL_RATED, "300.00", "0.00", "300.00", "5"),
            (964, "2026-05-11", SalesInvoiceHeader.Taxability.NON_GST, "150.00", "0.00", "150.00", "5"),
        ]
        sales_headers = []
        for txn_id, posting_date, taxability, taxable, igst, grand_total, qty in sales_specs:
            header = SalesInvoiceHeader.objects.create(
                id=txn_id,
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.branch,
                doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
                status=SalesInvoiceHeader.Status.POSTED,
                bill_date=posting_date,
                posting_date=posting_date,
                doc_code="SINV",
                doc_no=txn_id,
                invoice_number=f"B-V5-SALE-{txn_id}",
                customer=variant_customer,
                customer_ledger=variant_customer.ledger,
                customer_name=variant_customer.accountname,
                customer_gstin="27ABCDE1234F1Z5",
                customer_state_code="27",
                seller_gstin="29AAAAA9999A1Z5",
                seller_state_code="29",
                place_of_supply_state_code="27",
                supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                taxability=taxability,
                tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
                total_taxable_value=Decimal(taxable),
                total_igst=Decimal(igst),
                grand_total=Decimal(grand_total),
                outstanding_amount=Decimal(grand_total),
                created_by=self.user,
            )
            SalesTaxSummary.objects.create(
                header=header,
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.branch,
                taxability=taxability,
                hsn_sac_code="100100",
                gst_rate=Decimal("18.00") if taxability == SalesInvoiceHeader.Taxability.TAXABLE else Decimal("0.00"),
                taxable_value=Decimal(taxable),
                igst_amount=Decimal(igst),
            )
            lines = [(variant_customer, True, grand_total), (variant_sales, False, taxable)]
            if Decimal(igst):
                lines.append((output_igst, False, igst))
            entry, batch = self._entry(TxnType.SALES, txn_id, header.invoice_number, posting_date, lines)
            self._inventory_move(
                entry,
                batch,
                qty,
                InventoryMove.MoveType.OUT,
                InventoryMove.MovementNature.SALE,
                product=product,
                unit_cost="0.0000",
            )
            sales_headers.append(header)

        register_params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.branch.id,
            "from_date": "2026-05-04",
            "to_date": "2026-05-11",
        }
        purchase_service = PurchaseRegisterService()
        purchase_qs, _ = purchase_service.apply_filters(
            purchase_service.get_base_queryset(),
            {**register_params, "vendor": variant_vendor.id},
        )
        annotated_purchase_qs = purchase_service.annotate_register_fields(purchase_qs)
        purchase_rows = list(annotated_purchase_qs.order_by("id"))
        purchase_totals = purchase_service.calculate_totals(annotated_purchase_qs)

        gstr1_service = Gstr1Service()
        sales_qs, _ = gstr1_service.apply_filters(
            gstr1_service.get_base_queryset(),
            {**register_params, "customer": variant_customer.id},
        )
        annotated_sales_qs = gstr1_service.annotate_register_fields(sales_qs)
        sales_rows = list(annotated_sales_qs.order_by("id"))
        sales_totals = gstr1_service.calculate_totals(annotated_sales_qs)
        nil_exempt_rows = {
            row["taxability"]: row
            for row in Gstr1SummaryService(base_queryset=sales_qs).nil_exempt_summary()
        }

        gstr3b_service = Gstr3bSummaryService()
        gstr3b_scope = gstr3b_service.build_scope(register_params)
        gstr3b = gstr3b_service.build(gstr3b_scope)

        report_scope = {
            "entity_id": self.entity.id,
            "entityfin_id": self.entityfin.id,
            "subentity_id": self.branch.id,
            "from_date": "2026-05-04",
            "to_date": "2026-05-11",
        }
        ledger_ids = [
            variant_purchases.ledger_id,
            input_igst.ledger_id,
            variant_vendor.ledger_id,
            variant_customer.ledger_id,
            variant_sales.ledger_id,
            output_igst.ledger_id,
        ]
        trial_balance = build_trial_balance(**report_scope, account_group="ledger", ledger_ids=ledger_ids)
        trading_report = build_trading_account_dynamic(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.branch.id,
            startdate="2026-05-04",
            enddate="2026-05-11",
            ledger_ids=[variant_purchases.ledger_id, variant_sales.ledger_id],
            inventory_product_ids=[product.id],
            valuation_method="fifo",
        )
        profit_loss = build_profit_and_loss(
            **report_scope,
            group_by="ledger",
            ledger_ids=[variant_purchases.ledger_id, variant_sales.ledger_id],
            trading_snapshot=trading_report,
            stock_valuation_mode="fifo",
        )
        inventory_rows, closing_qty, closing_value = inventory_breakdown_asof(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.branch.id,
            enddate="2026-05-11",
            method="fifo",
            product_ids=[product.id],
        )

        self.assertEqual(purchase_totals["document_count"], 4)
        self.assertEqual(purchase_totals["taxable_amount"], Decimal("11500.00"))
        self.assertEqual(purchase_totals["igst_amount"], Decimal("1800.00"))
        self.assertEqual(purchase_totals["cgst_amount"], Decimal("0.00"))
        self.assertEqual(purchase_totals["sgst_amount"], Decimal("0.00"))
        self.assertEqual([row.default_taxability for row in purchase_rows], [spec[2] for spec in purchase_specs])

        self.assertEqual(sales_totals["document_count"], 4)
        self.assertEqual(sales_totals["taxable_amount"], Decimal("9250.00"))
        self.assertEqual(sales_totals["igst_amount"], Decimal("1440.00"))
        self.assertEqual(sales_totals["cgst_amount"], Decimal("0.00"))
        self.assertEqual(sales_totals["sgst_amount"], Decimal("0.00"))
        self.assertEqual([row.taxability_name for row in sales_rows], ["Taxable", "Exempt", "Nil-rated", "Non-GST"])
        for row in purchase_rows[1:] + sales_rows[1:]:
            self.assertEqual(row.cgst_amount, Decimal("0.00"))
            self.assertEqual(row.sgst_amount, Decimal("0.00"))
            self.assertEqual(row.igst_amount, Decimal("0.00"))

        self.assertEqual(nil_exempt_rows[SalesInvoiceHeader.Taxability.EXEMPT]["taxable_value"], Decimal("800.00"))
        self.assertEqual(nil_exempt_rows[SalesInvoiceHeader.Taxability.NIL_RATED]["taxable_value"], Decimal("300.00"))
        self.assertEqual(nil_exempt_rows[SalesInvoiceHeader.Taxability.NON_GST]["taxable_value"], Decimal("150.00"))
        self.assertEqual(gstr3b["section_3_1"]["outward_taxable_supplies"]["taxable_value"], Decimal("8000.00"))
        self.assertEqual(gstr3b["section_3_1"]["outward_taxable_supplies"]["igst"], Decimal("1440.00"))
        self.assertEqual(gstr3b["section_3_1"]["outward_nil_exempt_non_gst"]["taxable_value"], Decimal("1250.00"))
        self.assertEqual(gstr3b["section_3_1"]["non_gst_outward_supplies"]["taxable_value"], Decimal("150.00"))
        self.assertEqual(gstr3b["section_4"]["itc_available"]["igst"], Decimal("1800.00"))
        self.assertEqual(gstr3b["section_5_1"]["inward_exempt_nil_non_gst"]["taxable_value"], Decimal("1500.00"))

        trial_rows = {row["ledger_name"]: Decimal(row["closing"]) for row in trial_balance["rows"]}
        self.assertEqual(trial_rows["Variant Goods Purchases"], Decimal("11500.00"))
        self.assertEqual(trial_rows["Variant Input IGST"], Decimal("1800.00"))
        self.assertEqual(trial_rows["Variant Tax Vendor"], Decimal("-13300.00"))
        self.assertEqual(trial_rows["Variant Tax Customer"], Decimal("10690.00"))
        self.assertEqual(trial_rows["Variant Goods Sales"], Decimal("-9250.00"))
        self.assertEqual(trial_rows["Variant Output IGST"], Decimal("-1440.00"))
        self.assertEqual(trial_balance["totals"]["closing_debit"], "23990.00")
        self.assertEqual(trial_balance["totals"]["closing_credit"], "23990.00")
        self.assertEqual(closing_qty, Decimal("75"))
        self.assertEqual(closing_value, Decimal("5500.0000"))
        self.assertEqual(len(inventory_rows), 1)
        self.assertEqual(Decimal(str(trading_report["cogs_from_issues"])), Decimal("6000.0"))
        self.assertEqual(Decimal(str(trading_report["closing_stock"])), Decimal("5500.0"))
        self.assertEqual(Decimal(str(trading_report["gross_profit"])), Decimal("3250.0"))
        self.assertEqual(profit_loss["totals"]["net_profit"], "3250.00")
