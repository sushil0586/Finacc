from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity, UnitType
from financial.models import Ledger, account, accountHead, accounttype
from financial.profile_access import account_gstno
from financial.services import apply_normalized_profile_payload, create_account_with_synced_ledger
from geography.models import City, Country, District, State
from sales.models import SalesInvoiceHeader, SalesInvoiceLine


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class SalesRegisterAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="sales-report-user",
            email="sales-report@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("reports_api:sales-register")

        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.other_state = State.objects.create(statename="Karnataka", statecode="29", country=self.country)
        self.district = District.objects.create(districtname="District", districtcode="DT", state=self.state)
        self.city = City.objects.create(cityname="Mumbai", citycode="MUM", pincode="400001", distt=self.district)
        self.unit_type = UnitType.objects.create(UnitName="Business", UnitDesc="Business")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")

        self.entity = Entity.objects.create(
            entityname="Finacc Sales Entity",
            legalname="Finacc Sales Entity Pvt Ltd",
            unitType=self.unit_type,
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main Branch")
        self.other_subentity = SubEntity.objects.create(entity=self.entity, subentityname="Other Branch")

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
        self.other_entity_subentity = SubEntity.objects.create(
            entity=self.other_entity,
            subentityname="Other Entity Branch",
        )

        self.acc_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Receivable",
            accounttypecode="R100",
            createdby=self.user,
        )
        self.other_acc_type = accounttype.objects.create(
            entity=self.other_entity,
            accounttypename="Receivable",
            accounttypecode="R200",
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
        self.sales_head = accountHead.objects.create(
            entity=self.entity,
            name="Sales",
            code=300,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.other_customer_head = accountHead.objects.create(
            entity=self.other_entity,
            name="Sundry Debtors",
            code=101,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=self.other_acc_type,
            createdby=self.user,
        )

        self.customer_alpha = self._create_customer(name="Alpha Retail", gstin="27ABCDE1234F1Z5", accountcode=5001)
        self.customer_beta = self._create_customer(name="Beta Mart", gstin="27BBBBB1234B1Z5", accountcode=5002)
        self.other_entity_customer = self._create_customer(
            name="Other Customer",
            gstin="29CCCCC1234C1Z5",
            accountcode=9001,
            entity=self.other_entity,
            account_head=self.other_customer_head,
        )

        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="NOS", description="Numbers")
        self.category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Goods")
        self.product = Product.objects.create(
            entity=self.entity,
            productname="Widget",
            sku="WIDGET-001",
            productcategory=self.category,
            base_uom=self.uom,
            sales_account=self.customer_alpha,
        )

        self.base_params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
        }
        self.doc_no_seq = 1

    def _create_customer(self, *, name, gstin, accountcode, entity=None, account_head=None):
        entity = entity or self.entity
        account_head = account_head or self.customer_head
        ledger = Ledger.objects.create(
            entity=entity,
            ledger_code=accountcode,
            name=name,
            accounthead=account_head,
            createdby=self.user,
        )
        row = create_account_with_synced_ledger(
            account_data={
                "entity": entity,
                "ledger": ledger,
                "accountname": name,
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": accountcode, "accounthead": account_head, "is_party": True},
        )
        apply_normalized_profile_payload(
            row,
            compliance_data={"gstno": gstin},
            commercial_data={"partytype": "Customer"},
            primary_address_data={},
        )
        return row

    def _create_sales_document(
        self,
        *,
        customer=None,
        entity=None,
        entityfin=None,
        subentity=None,
        doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
        status=SalesInvoiceHeader.Status.POSTED,
        bill_date="2025-04-05",
        posting_date="2025-04-05",
        invoice_number=None,
        taxable="100.00",
        cgst="9.00",
        sgst="9.00",
        igst="0.00",
        cess="0.00",
        round_off="0.00",
        grand_total="118.00",
        total_discount="0.00",
        supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
        original_invoice=None,
        discount_amounts=None,
        customer_name=None,
        customer_gstin=None,
    ):
        entity = entity or self.entity
        entityfin = entityfin or self.entityfin
        subentity = subentity if subentity is not None else self.subentity
        customer = customer or self.customer_alpha
        discount_amounts = discount_amounts or []

        doc_code_map = {
            SalesInvoiceHeader.DocType.TAX_INVOICE: "SINV",
            SalesInvoiceHeader.DocType.CREDIT_NOTE: "SCN",
            SalesInvoiceHeader.DocType.DEBIT_NOTE: "SDN",
        }
        doc_no = self.doc_no_seq
        self.doc_no_seq += 1

        header = SalesInvoiceHeader.objects.create(
            entity=entity,
            entityfinid=entityfin,
            subentity=subentity,
            doc_type=doc_type,
            status=status,
            bill_date=bill_date,
            posting_date=posting_date,
            doc_code=doc_code_map[doc_type],
            doc_no=doc_no,
            invoice_number=invoice_number or f"{doc_code_map[doc_type]}-{doc_no:04d}",
            customer=customer,
            customer_ledger=customer.ledger,
            customer_name=customer_name or customer.accountname,
            customer_gstin=customer_gstin or account_gstno(customer),
            customer_state_code=self.state.statecode,
            seller_gstin="27AAAAA9999A1Z5",
            seller_state_code=self.state.statecode,
            place_of_supply_state_code=self.state.statecode,
            supply_category=supply_category,
            total_taxable_value=Decimal(taxable),
            total_cgst=Decimal(cgst),
            total_sgst=Decimal(sgst),
            total_igst=Decimal(igst),
            total_cess=Decimal(cess),
            total_discount=Decimal(total_discount),
            round_off=Decimal(round_off),
            grand_total=Decimal(grand_total),
            original_invoice=original_invoice,
            created_by=self.user,
        )

        for idx, discount in enumerate(discount_amounts, start=1):
            SalesInvoiceLine.objects.create(
                entity=entity,
                entityfinid=entityfin,
                subentity=subentity,
                header=header,
                line_no=idx,
                product=self.product,
                uom=self.uom,
                qty=Decimal("1.000"),
                rate=Decimal("10.0000"),
                discount_amount=Decimal(discount),
                taxable_value=Decimal("10.00"),
                line_total=Decimal("10.00"),
            )
        return header

    def _get(self, **params):
        query = {**self.base_params, **params}
        return self.client.get(self.url, query, format="json")

    def _money(self, value):
        return Decimal(str(value))

    def test_default_status_filtering(self):
        self._create_sales_document(status=SalesInvoiceHeader.Status.DRAFT, invoice_number="DRAFT-001")
        confirmed = self._create_sales_document(status=SalesInvoiceHeader.Status.CONFIRMED, invoice_number="CONF-001")
        posted = self._create_sales_document(status=SalesInvoiceHeader.Status.POSTED, invoice_number="POST-001")
        self._create_sales_document(status=SalesInvoiceHeader.Status.CANCELLED, invoice_number="CANC-001")
        self._create_sales_document(
            entity=self.other_entity,
            entityfin=self.other_entityfin,
            subentity=self.other_entity_subentity,
            customer=self.other_entity_customer,
            status=SalesInvoiceHeader.Status.POSTED,
            invoice_number="OTHER-ENTITY-001",
        )

        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            {row["sales_invoice_number"] for row in response.data["results"]},
            {confirmed.invoice_number, posted.invoice_number},
        )

    def test_explicit_status_override(self):
        draft = self._create_sales_document(status=SalesInvoiceHeader.Status.DRAFT, invoice_number="DRAFT-OVERRIDE")
        self._create_sales_document(status=SalesInvoiceHeader.Status.CONFIRMED, invoice_number="CONF-OVERRIDE")
        cancelled = self._create_sales_document(status=SalesInvoiceHeader.Status.CANCELLED, invoice_number="CANC-OVERRIDE")

        response = self._get(status=f"{SalesInvoiceHeader.Status.DRAFT},{SalesInvoiceHeader.Status.CANCELLED}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            {row["sales_invoice_number"] for row in response.data["results"]},
            {draft.invoice_number, cancelled.invoice_number},
        )

    def test_cancelled_documents_are_listed_but_zero_in_totals(self):
        active = self._create_sales_document(
            status=SalesInvoiceHeader.Status.POSTED,
            invoice_number="ACTIVE-001",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="118.00",
        )
        cancelled = self._create_sales_document(
            status=SalesInvoiceHeader.Status.CANCELLED,
            invoice_number="CANCELLED-001",
            taxable="999.00",
            cgst="99.00",
            sgst="99.00",
            grand_total="1197.00",
        )

        response = self._get(status=f"{SalesInvoiceHeader.Status.POSTED},{SalesInvoiceHeader.Status.CANCELLED}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(self._money(response.data["totals"]["grand_total"]), Decimal("118.00"))

        cancelled_row = next(row for row in response.data["results"] if row["sales_invoice_number"] == cancelled.invoice_number)
        active_row = next(row for row in response.data["results"] if row["sales_invoice_number"] == active.invoice_number)
        self.assertEqual(self._money(cancelled_row["grand_total"]), Decimal("0.00"))
        self.assertEqual(self._money(cancelled_row["taxable_amount"]), Decimal("0.00"))
        self.assertFalse(cancelled_row["affects_totals"])
        self.assertEqual(self._money(active_row["grand_total"]), Decimal("118.00"))

    def test_credit_note_negative_effect(self):
        invoice = self._create_sales_document(
            status=SalesInvoiceHeader.Status.POSTED,
            invoice_number="INV-BASE-001",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="118.00",
        )
        credit = self._create_sales_document(
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=invoice,
            status=SalesInvoiceHeader.Status.POSTED,
            invoice_number="CRN-001",
            taxable="40.00",
            cgst="3.60",
            sgst="3.60",
            grand_total="47.20",
        )

        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._money(response.data["totals"]["grand_total"]), Decimal("70.80"))
        credit_row = next(row for row in response.data["results"] if row["sales_invoice_number"] == credit.invoice_number)
        self.assertEqual(self._money(credit_row["grand_total"]), Decimal("-47.20"))
        self.assertEqual(self._money(credit_row["taxable_amount"]), Decimal("-40.00"))

    def test_debit_note_positive_effect(self):
        invoice = self._create_sales_document(
            status=SalesInvoiceHeader.Status.POSTED,
            invoice_number="INV-BASE-002",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="118.00",
        )
        self._create_sales_document(
            doc_type=SalesInvoiceHeader.DocType.DEBIT_NOTE,
            original_invoice=invoice,
            status=SalesInvoiceHeader.Status.POSTED,
            invoice_number="DBN-001",
            taxable="20.00",
            cgst="1.80",
            sgst="1.80",
            grand_total="23.60",
        )

        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._money(response.data["totals"]["grand_total"]), Decimal("141.60"))

    def test_bill_date_filtering(self):
        in_range = self._create_sales_document(
            invoice_number="BILL-RANGE-IN",
            bill_date="2025-04-15",
            posting_date="2025-04-16",
        )
        self._create_sales_document(
            invoice_number="BILL-RANGE-OUT",
            bill_date="2025-05-01",
            posting_date="2025-05-01",
        )

        response = self._get(from_date="2025-04-10", to_date="2025-04-30")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sales_invoice_number"], in_range.invoice_number)

    def test_posting_date_filtering(self):
        in_range = self._create_sales_document(
            invoice_number="POST-RANGE-IN",
            bill_date="2025-04-05",
            posting_date="2025-04-20",
        )
        self._create_sales_document(
            invoice_number="POST-RANGE-OUT",
            bill_date="2025-04-05",
            posting_date="2025-05-02",
        )

        response = self._get(posting_from_date="2025-04-18", posting_to_date="2025-04-25")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sales_invoice_number"], in_range.invoice_number)

    def test_customer_filter(self):
        alpha = self._create_sales_document(customer=self.customer_alpha, invoice_number="ALPHA-001")
        self._create_sales_document(customer=self.customer_beta, invoice_number="BETA-001")

        response = self._get(customer=self.customer_alpha.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sales_invoice_number"], alpha.invoice_number)

    def test_customer_gstin_filter(self):
        match = self._create_sales_document(customer=self.customer_alpha, invoice_number="GSTIN-001")
        self._create_sales_document(customer=self.customer_beta, invoice_number="GSTIN-002")

        response = self._get(customer_gstin="1234F1Z5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sales_invoice_number"], match.invoice_number)

    def test_supply_classification_filter(self):
        b2b = self._create_sales_document(
            invoice_number="B2B-001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
        )
        self._create_sales_document(
            invoice_number="B2C-001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
        )

        response = self._get(supply_classification=str(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sales_invoice_number"], b2b.invoice_number)

    def test_search_by_sales_invoice_number(self):
        match = self._create_sales_document(invoice_number="SINV-SRCH-001")
        self._create_sales_document(invoice_number="SINV-OTHER-001")

        response = self._get(search="SRCH-001")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sales_invoice_number"], match.invoice_number)

    def test_search_by_customer_name(self):
        match = self._create_sales_document(customer=self.customer_alpha, invoice_number="NAME-001")
        self._create_sales_document(customer=self.customer_beta, invoice_number="NAME-002")

        response = self._get(search="Alpha")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sales_invoice_number"], match.invoice_number)

    def test_numeric_search_by_doc_no(self):
        match = self._create_sales_document(invoice_number="DOCNO-001")
        self._create_sales_document(invoice_number="DOCNO-002")

        response = self._get(search=str(match.doc_no))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sales_invoice_number"], match.invoice_number)

    def test_totals_are_based_on_all_filtered_rows_not_page_slice(self):
        first = self._create_sales_document(
            invoice_number="PAGE-001",
            grand_total="118.00",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
        )
        second = self._create_sales_document(
            invoice_number="PAGE-002",
            grand_total="236.00",
            taxable="200.00",
            cgst="18.00",
            sgst="18.00",
            bill_date="2025-04-06",
            posting_date="2025-04-06",
        )

        response = self._get(page_size=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(self._money(response.data["totals"]["grand_total"]), Decimal("354.00"))
        self.assertEqual(self._money(response.data["totals"]["taxable_amount"]), Decimal("300.00"))
        self.assertIn(response.data["results"][0]["sales_invoice_number"], {first.invoice_number, second.invoice_number})

    def test_line_level_discount_subquery_does_not_duplicate_header_rows(self):
        header = self._create_sales_document(
            invoice_number="DISC-SUBQ-001",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="118.00",
            total_discount="0.00",
            discount_amounts=["10.00", "15.00"],
        )

        response = self._get(search="DISC-SUBQ-001")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["sales_invoice_number"], header.invoice_number)
        self.assertEqual(self._money(response.data["results"][0]["discount_total"]), Decimal("25.00"))
        self.assertEqual(self._money(response.data["totals"]["discount_total"]), Decimal("25.00"))
