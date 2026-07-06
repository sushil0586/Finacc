from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
from financial.models import Ledger, account, accountHead, accounttype
from financial.profile_access import account_gstno
from financial.services import apply_normalized_profile_payload, create_account_with_synced_ledger
from geography.models import City, Country, District, State
from reports.services.receivables import (
    build_customer_outstanding_report,
    build_open_items_report,
    build_receivable_aging_report,
)
from sales.models.sales_ar import CustomerBillOpenItem
from sales.models.sales_core import SalesInvoiceHeader, SalesInvoiceLine


class ReceivablesRouteContractTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="receivables-report-user",
            email="receivables-report@example.com",
            password="pass123",
        )
        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.district = District.objects.create(districtname="District", districtcode="DT", state=self.state)
        self.city = City.objects.create(cityname="Mumbai", citycode="MUM", pincode="400001", distt=self.district)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Finacc Receivables Entity",
            legalname="Finacc Receivables Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main Branch")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )
        self.acc_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Receivable",
            accounttypecode="R100",
            createdby=self.user,
        )
        self.customer_head = accountHead.objects.create(
            entity=self.entity,
            name="Sundry Debtors",
            code=100,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.customer = self._create_customer(name="Service Customer", gstin="27ABCDE1234F1Z5", accountcode=5001)
        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="NOS", description="Numbers")
        self.category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Services")
        self.product = Product.objects.create(
            entity=self.entity,
            productname="Consulting",
            sku="CONSULT-001",
            productcategory=self.category,
            base_uom=self.uom,
            sales_account=self.customer,
        )

    def _create_customer(self, *, name: str, gstin: str, accountcode: int) -> account:
        ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=accountcode,
            name=name,
            accounthead=self.customer_head,
            createdby=self.user,
        )
        row = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": ledger,
                "accountname": name,
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": accountcode, "accounthead": self.customer_head, "is_party": True},
        )
        apply_normalized_profile_payload(
            row,
            compliance_data={"gstno": gstin},
            commercial_data={"partytype": "Customer"},
            primary_address_data={},
        )
        return row

    def _create_service_invoice(self) -> SalesInvoiceHeader:
        invoice = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2025-04-15",
            posting_date="2025-04-15",
            doc_code="SINV",
            doc_no=1,
            invoice_number="SINV-0001",
            customer=self.customer,
            customer_ledger=self.customer.ledger,
            customer_name=self.customer.accountname,
            customer_gstin=account_gstno(self.customer),
            customer_state_code=self.state.statecode,
            seller_gstin="27AAAAA9999A1Z5",
            seller_state_code=self.state.statecode,
            place_of_supply_state_code=self.state.statecode,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            total_taxable_value=Decimal("100.00"),
            total_cgst=Decimal("9.00"),
            total_sgst=Decimal("9.00"),
            total_igst=Decimal("0.00"),
            total_cess=Decimal("0.00"),
            total_discount=Decimal("0.00"),
            round_off=Decimal("0.00"),
            grand_total=Decimal("118.00"),
            created_by=self.user,
        )
        SalesInvoiceLine.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=invoice,
            line_no=1,
            product=self.product,
            uom=self.uom,
            qty=Decimal("1.000"),
            rate=Decimal("100.0000"),
            taxable_value=Decimal("100.00"),
            line_total=Decimal("118.00"),
            is_service=True,
        )
        CustomerBillOpenItem.objects.create(
            header=invoice,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            customer=self.customer,
            customer_ledger=self.customer.ledger,
            doc_type=invoice.doc_type,
            bill_date=invoice.bill_date,
            due_date=invoice.bill_date,
            invoice_number=invoice.invoice_number,
            customer_reference_number="REF-001",
            original_amount=Decimal("118.00"),
            gross_amount=Decimal("118.00"),
            net_receivable_amount=Decimal("118.00"),
            settled_amount=Decimal("0.00"),
            outstanding_amount=Decimal("118.00"),
            is_open=True,
        )
        return invoice

    def _create_product_invoice(
        self,
        *,
        customer: account,
        doc_no: int,
        invoice_number: str,
        bill_date: str,
        due_date: str,
        amount: Decimal,
    ) -> SalesInvoiceHeader:
        invoice = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date=bill_date,
            posting_date=bill_date,
            doc_code="SINV",
            doc_no=doc_no,
            invoice_number=invoice_number,
            customer=customer,
            customer_ledger=customer.ledger,
            customer_name=customer.accountname,
            customer_gstin=account_gstno(customer),
            customer_state_code=self.state.statecode,
            seller_gstin="27AAAAA9999A1Z5",
            seller_state_code=self.state.statecode,
            place_of_supply_state_code=self.state.statecode,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            total_taxable_value=amount,
            total_cgst=Decimal("0.00"),
            total_sgst=Decimal("0.00"),
            total_igst=Decimal("0.00"),
            total_cess=Decimal("0.00"),
            total_discount=Decimal("0.00"),
            round_off=Decimal("0.00"),
            grand_total=amount,
            created_by=self.user,
        )
        CustomerBillOpenItem.objects.create(
            header=invoice,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            customer=customer,
            customer_ledger=customer.ledger,
            doc_type=invoice.doc_type,
            bill_date=invoice.bill_date,
            due_date=due_date,
            invoice_number=invoice.invoice_number,
            customer_reference_number=f"REF-{doc_no}",
            original_amount=amount,
            gross_amount=amount,
            net_receivable_amount=amount,
            settled_amount=Decimal("0.00"),
            outstanding_amount=amount,
            is_open=True,
        )
        return invoice

    def test_open_items_report_exposes_service_invoice_route(self):
        invoice = self._create_service_invoice()

        report = build_open_items_report(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
        )

        invoice_row = next(row for row in report["rows"] if row["invoice_number"] == invoice.invoice_number)
        self.assertEqual(invoice_row["drilldown"]["invoice"]["route"], "/saleserviceinvoice")

    def test_receivable_aging_invoice_view_exposes_service_invoice_route(self):
        invoice = self._create_service_invoice()

        report = build_receivable_aging_report(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of_date="2025-04-30",
            view="invoice",
        )

        invoice_row = next(row for row in report["rows"] if row["invoice_number"] == invoice.invoice_number)
        self.assertEqual(invoice_row["drilldown"]["invoice"]["route"], "/saleserviceinvoice")

    def test_receivable_aging_summary_and_invoice_views_keep_expected_totals(self):
        invoice = self._create_service_invoice()

        summary_report = build_receivable_aging_report(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of_date="2025-04-30",
            view="summary",
        )
        self.assertEqual(summary_report["view"], "summary")
        self.assertEqual(summary_report["summary"]["customer_count"], 1)
        self.assertEqual(summary_report["totals"]["outstanding"], "118.00")
        self.assertEqual(summary_report["totals"]["bucket_1_30"], "118.00")
        self.assertEqual(summary_report["rows"][0]["customer_name"], "Service Customer")

        invoice_report = build_receivable_aging_report(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of_date="2025-04-30",
            view="invoice",
        )
        self.assertEqual(invoice_report["view"], "invoice")
        self.assertEqual(invoice_report["totals"]["balance"], "118.00")
        invoice_row = next(row for row in invoice_report["rows"] if row["invoice_number"] == invoice.invoice_number)
        self.assertEqual(invoice_row["balance"], "118.00")
        self.assertEqual(invoice_row["bucket_1_30"], "118.00")

    def test_receivable_aging_overdue_only_excludes_current_customer(self):
        self._create_service_invoice()
        current_customer = self._create_customer(name="Current Customer", gstin="27ABCDE1234F1Z6", accountcode=5002)
        self._create_product_invoice(
            customer=current_customer,
            doc_no=2,
            invoice_number="SINV-0002",
            bill_date="2025-04-25",
            due_date="2025-05-20",
            amount=Decimal("75.00"),
        )

        summary_report = build_receivable_aging_report(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of_date="2025-04-30",
            view="summary",
            overdue_only=True,
        )
        self.assertEqual(summary_report["summary"]["customer_count"], 1)
        self.assertEqual(len(summary_report["rows"]), 1)
        self.assertEqual(summary_report["rows"][0]["customer_name"], "Service Customer")

        invoice_report = build_receivable_aging_report(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of_date="2025-04-30",
            view="invoice",
            overdue_only=True,
        )
        self.assertEqual(len(invoice_report["rows"]), 1)
        self.assertEqual(invoice_report["rows"][0]["invoice_number"], "SINV-0001")

    def test_customer_outstanding_totals_and_overdue_only_remain_correct(self):
        self._create_service_invoice()
        current_customer = self._create_customer(name="Current Customer", gstin="27ABCDE1234F1Z6", accountcode=5002)
        self._create_product_invoice(
            customer=current_customer,
            doc_no=2,
            invoice_number="SINV-0002",
            bill_date="2025-04-25",
            due_date="2025-05-20",
            amount=Decimal("75.00"),
        )

        report = build_customer_outstanding_report(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of_date="2025-04-30",
        )
        self.assertEqual(report["summary"]["customer_count"], 2)
        self.assertEqual(report["totals"]["net_outstanding"], "193.00")
        self.assertEqual(report["totals"]["overdue_amount"], "118.00")
        self.assertEqual({row["customer_name"] for row in report["rows"]}, {"Service Customer", "Current Customer"})

        overdue_only_report = build_customer_outstanding_report(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            as_of_date="2025-04-30",
            overdue_only=True,
        )
        self.assertEqual(overdue_only_report["summary"]["customer_count"], 1)
        self.assertEqual(len(overdue_only_report["rows"]), 1)
        self.assertEqual(overdue_only_report["rows"][0]["customer_name"], "Service Customer")
        self.assertEqual(overdue_only_report["totals"]["net_outstanding"], "118.00")
