from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity, UnitType
from financial.models import Ledger, account, accountHead, accounttype
from financial.services import create_account_with_synced_ledger
from posting.models import Entry, EntityStaticAccountMap, JournalLine, PostingBatch, StaticAccount, TxnType
from purchase.models import PurchaseInvoiceHeader
from sales.models import SalesInvoiceHeader


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class Gstr3bSummaryAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="gstr3b-user",
            email="gstr3b@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)

        self.summary_url = reverse("reports_api:gstr3b-summary")
        self.meta_url = reverse("reports_api:gstr3b-meta")
        self.validation_url = reverse("reports_api:gstr3b-validations")

        unit_type = UnitType.objects.create(UnitName="Business", UnitDesc="Business")
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Finacc Entity",
            legalname="Finacc Entity Pvt Ltd",
            unitType=unit_type,
            GstRegitrationType=gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main Branch")

        fy_start = timezone.make_aware(datetime(2025, 4, 1))
        fy_end = timezone.make_aware(datetime(2026, 3, 31))
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=fy_start,
            finendyear=fy_end,
            createdby=self.user,
        )

        self.params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
            "from_date": "2025-04-01",
            "to_date": "2025-04-30",
        }
        self.acc_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Control",
            accounttypecode="CTRL",
            createdby=self.user,
        )
        self.acc_head = accountHead.objects.create(
            entity=self.entity,
            name="Control Head",
            code=999,
            drcreffect="Debit",
            balanceType="Debit",
            accounttype=self.acc_type,
            createdby=self.user,
        )

    def _create_sales_doc(
        self,
        *,
        doc_no,
        taxable,
        cgst,
        sgst,
        igst,
        taxability,
        supply_category,
        doc_type=1,
        pos_state_code="27",
    ):
        SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=doc_type,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2025-04-05",
            posting_date="2025-04-05",
            doc_code="SINV",
            doc_no=doc_no,
            invoice_number=f"S-{doc_no}",
            customer_name="Customer",
            seller_gstin="27AAAAA1111A1Z1",
            seller_state_code="27",
            place_of_supply_state_code=pos_state_code,
            taxability=taxability,
            supply_category=supply_category,
            tax_regime=(
                SalesInvoiceHeader.TaxRegime.INTER_STATE
                if Decimal(igst) > 0
                else SalesInvoiceHeader.TaxRegime.INTRA_STATE
            ),
            is_igst=Decimal(igst) > 0,
            total_taxable_value=Decimal(taxable),
            total_cgst=Decimal(cgst),
            total_sgst=Decimal(sgst),
            total_igst=Decimal(igst),
            total_cess=Decimal("0.00"),
            grand_total=Decimal(taxable) + Decimal(cgst) + Decimal(sgst) + Decimal(igst),
        )

    def _d(self, value):
        return Decimal(str(value))

    def _create_purchase_doc(
        self,
        *,
        doc_no,
        taxable,
        cgst,
        sgst,
        igst,
        default_taxability,
        is_itc_eligible=True,
        is_reverse_charge=False,
        doc_type=1,
    ):
        PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=doc_type,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date="2025-04-10",
            posting_date="2025-04-10",
            doc_code="PINV",
            doc_no=doc_no,
            vendor_name="Vendor",
            default_taxability=default_taxability,
            is_itc_eligible=is_itc_eligible,
            is_reverse_charge=is_reverse_charge,
            total_taxable=Decimal(taxable),
            total_cgst=Decimal(cgst),
            total_sgst=Decimal(sgst),
            total_igst=Decimal(igst),
            total_cess=Decimal("0.00"),
            total_gst=Decimal(cgst) + Decimal(sgst) + Decimal(igst),
            grand_total=Decimal(taxable) + Decimal(cgst) + Decimal(sgst) + Decimal(igst),
        )

    def _create_output_tax_mapping(self, code: str, ledger_code: int, account_code: int, name: str):
        static = StaticAccount.objects.create(code=code, name=code, group="GST_OUTPUT", is_required=False)
        ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=ledger_code,
            name=name,
            accounthead=self.acc_head,
            createdby=self.user,
        )
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": ledger,
                "accountname": name,
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": account_code, "accounthead": self.acc_head, "is_party": True},
        )
        EntityStaticAccountMap.objects.create(
            entity=self.entity,
            sub_entity=self.subentity,
            static_account=static,
            account=acc,
            ledger=ledger,
            is_active=True,
            createdby=self.user,
        )
        return acc, ledger

    def test_meta_endpoint(self):
        response = self.client.get(self.meta_url, {"entity": self.entity.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["phase"], 2)

    def test_summary_computes_phase1_sections(self):
        self._create_sales_doc(
            doc_no=1,
            taxable="1000.00",
            cgst="90.00",
            sgst="90.00",
            igst="0.00",
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
        )
        self._create_sales_doc(
            doc_no=2,
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            taxable="200.00",
            cgst="18.00",
            sgst="18.00",
            igst="0.00",
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
        )
        self._create_sales_doc(
            doc_no=3,
            taxable="500.00",
            cgst="0.00",
            sgst="0.00",
            igst="90.00",
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
        )
        self._create_sales_doc(
            doc_no=4,
            taxable="300.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
            taxability=SalesInvoiceHeader.Taxability.EXEMPT,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
        )

        self._create_purchase_doc(
            doc_no=11,
            taxable="400.00",
            cgst="0.00",
            sgst="0.00",
            igst="72.00",
            default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE,
            is_itc_eligible=True,
            is_reverse_charge=True,
        )
        self._create_purchase_doc(
            doc_no=12,
            taxable="500.00",
            cgst="45.00",
            sgst="45.00",
            igst="0.00",
            default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE,
            is_itc_eligible=True,
            is_reverse_charge=False,
        )
        self._create_purchase_doc(
            doc_no=13,
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            igst="0.00",
            default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE,
            is_itc_eligible=False,
            is_reverse_charge=False,
        )
        self._create_purchase_doc(
            doc_no=14,
            taxable="250.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
            default_taxability=PurchaseInvoiceHeader.Taxability.EXEMPT,
            is_itc_eligible=False,
            is_reverse_charge=False,
        )

        response = self.client.get(self.summary_url, self.params)
        self.assertEqual(response.status_code, 200)
        data = response.json()["summary"]

        self.assertEqual(self._d(data["section_3_1"]["outward_taxable_supplies"]["taxable_value"]), Decimal("800.00"))
        self.assertEqual(self._d(data["section_3_1"]["outward_taxable_supplies"]["cgst"]), Decimal("72.00"))
        self.assertEqual(self._d(data["section_3_1"]["outward_taxable_supplies"]["sgst"]), Decimal("72.00"))
        self.assertEqual(self._d(data["section_3_1"]["outward_zero_rated_supplies"]["taxable_value"]), Decimal("500.00"))
        self.assertEqual(self._d(data["section_3_1"]["outward_zero_rated_supplies"]["igst"]), Decimal("90.00"))
        self.assertEqual(self._d(data["section_3_1"]["outward_nil_exempt_non_gst"]["taxable_value"]), Decimal("300.00"))
        self.assertEqual(self._d(data["section_3_1"]["inward_supplies_reverse_charge"]["igst"]), Decimal("72.00"))
        self.assertEqual(
            self._d(data["section_3_2"]["interstate_supplies_to_unregistered"]["taxable_value"]),
            Decimal("0.00"),
        )
        self.assertEqual(
            self._d(data["section_3_2"]["interstate_supplies_to_composition"]["taxable_value"]),
            Decimal("0.00"),
        )

        self.assertEqual(self._d(data["section_4"]["itc_available"]["cgst"]), Decimal("45.00"))
        self.assertEqual(self._d(data["section_4"]["itc_reversed"]["cgst"]), Decimal("9.00"))
        self.assertEqual(self._d(data["section_4"]["net_itc"]["cgst"]), Decimal("36.00"))
        self.assertEqual(self._d(data["section_5_1"]["inward_exempt_nil_non_gst"]["taxable_value"]), Decimal("250.00"))
        self.assertEqual(self._d(data["section_6_1"]["tax_payable"]["igst"]), Decimal("162.00"))
        self.assertEqual(self._d(data["section_6_1"]["tax_paid_cash"]["igst"]), Decimal("0.00"))
        self.assertEqual(self._d(data["section_6_1"]["tax_paid_itc"]["igst"]), Decimal("72.00"))
        self.assertEqual(self._d(data["section_6_1"]["balance_payable"]["igst"]), Decimal("90.00"))

        self.assertEqual(self._d(data["totals"]["tax_payable"]["cgst"]), Decimal("72.00"))
        self.assertEqual(self._d(data["totals"]["tax_payable"]["igst"]), Decimal("162.00"))
        self.assertEqual(self._d(data["totals"]["net_cash_tax_payable"]["cgst"]), Decimal("36.00"))
        self.assertEqual(self._d(data["totals"]["net_cash_tax_payable"]["igst"]), Decimal("90.00"))

    def test_summary_uses_posted_bank_cash_vouchers_for_tax_paid_cash(self):
        self._create_sales_doc(
            doc_no=1,
            taxable="1000.00",
            cgst="90.00",
            sgst="90.00",
            igst="0.00",
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
        )
        self._create_purchase_doc(
            doc_no=12,
            taxable="500.00",
            cgst="45.00",
            sgst="45.00",
            igst="0.00",
            default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE,
            is_itc_eligible=True,
            is_reverse_charge=False,
        )
        cgst_account, cgst_ledger = self._create_output_tax_mapping("OUTPUT_CGST", 8101, 9101, "Output CGST")
        sgst_account, sgst_ledger = self._create_output_tax_mapping("OUTPUT_SGST", 8102, 9102, "Output SGST")

        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL_BANK,
            txn_id=5001,
            voucher_no="GST-PAY-001",
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL_BANK,
            txn_id=5001,
            voucher_no="GST-PAY-001",
            posting_date=timezone.datetime(2025, 4, 21).date(),
            voucher_date=timezone.datetime(2025, 4, 21).date(),
            status=2,
            posting_batch=batch,
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL_BANK,
            txn_id=5001,
            voucher_no="GST-PAY-001",
            account=cgst_account,
            ledger=cgst_ledger,
            drcr=True,
            amount=Decimal("50.00"),
            posting_date=timezone.datetime(2025, 4, 21).date(),
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.JOURNAL_BANK,
            txn_id=5001,
            voucher_no="GST-PAY-001",
            account=sgst_account,
            ledger=sgst_ledger,
            drcr=True,
            amount=Decimal("40.00"),
            posting_date=timezone.datetime(2025, 4, 21).date(),
            created_by=self.user,
        )

        response = self.client.get(self.summary_url, self.params)
        self.assertEqual(response.status_code, 200)
        data = response.json()["summary"]
        self.assertEqual(self._d(data["section_6_1"]["tax_paid_cash"]["cgst"]), Decimal("50.00"))
        self.assertEqual(self._d(data["section_6_1"]["tax_paid_cash"]["sgst"]), Decimal("40.00"))
        self.assertEqual(self._d(data["section_6_1"]["balance_payable"]["cgst"]), Decimal("0.00"))
        self.assertEqual(self._d(data["section_6_1"]["balance_payable"]["sgst"]), Decimal("5.00"))

    def test_validations_endpoint(self):
        self._create_sales_doc(
            doc_no=50,
            taxable="100.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            pos_state_code="",
        )
        response = self.client.get(self.validation_url, self.params)
        self.assertEqual(response.status_code, 200)
        warnings = response.json()["warnings"]
        self.assertTrue(any(w["code"] == "GSTR3B_POS_MISSING" for w in warnings))
        self.assertTrue(any(w["code"] == "GSTR3B_TAX_BREAKUP_MISSING" for w in warnings))
        self.assertTrue(any(w["code"] == "GSTR3B_CASH_TAX_SOURCE_PENDING" for w in warnings))
