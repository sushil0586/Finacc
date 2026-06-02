from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
from financial.models import Ledger, account, accountHead, accounttype
from financial.profile_access import account_gstno
from financial.services import apply_normalized_profile_payload, create_account_with_synced_ledger
from geography.models import City, Country, District, State
from sales.models import SalesInvoiceHeader, SalesInvoiceLine
from sales.models import SalesEInvoice, SalesEWayBill


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
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Finacc Sales Entity",
            legalname="Finacc Sales Entity Pvt Ltd",
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
        self.permission_entity = self.entity
        self.mock_entity_for_user = patch("sales.views.rbac.EffectivePermissionService.entity_for_user", return_value=self.permission_entity)
        self.mock_permission_codes = patch(
            "sales.views.rbac.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.sales_register.view", "reports.sales_register.export"],
        )
        self.mock_subscription_access = patch("sales.views.rbac.SubscriptionService.assert_entity_access", return_value=self.permission_entity)
        self.mock_entity_for_user.start()
        self.mock_permission_codes.start()
        self.mock_subscription_access.start()
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

    def tearDown(self):
        patch.stopall()
        super().tearDown()

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
        taxability=SalesInvoiceHeader.Taxability.TAXABLE,
        original_invoice=None,
        discount_amounts=None,
        customer_name=None,
        customer_gstin=None,
        note_reason=None,
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
            taxability=taxability,
            total_taxable_value=Decimal(taxable),
            total_cgst=Decimal(cgst),
            total_sgst=Decimal(sgst),
            total_igst=Decimal(igst),
            total_cess=Decimal(cess),
            total_discount=Decimal(total_discount),
            round_off=Decimal(round_off),
            grand_total=Decimal(grand_total),
            original_invoice=original_invoice,
            note_reason=note_reason,
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

    def test_original_and_correction_documents_stay_in_their_own_periods(self):
        invoice = self._create_sales_document(
            status=SalesInvoiceHeader.Status.POSTED,
            invoice_number="INV-AMEND-APR",
            bill_date="2025-04-10",
            posting_date="2025-04-10",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="118.00",
        )
        credit = self._create_sales_document(
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=invoice,
            status=SalesInvoiceHeader.Status.POSTED,
            invoice_number="CRN-AMEND-MAY",
            bill_date="2025-05-02",
            posting_date="2025-05-02",
            taxable="20.00",
            cgst="1.80",
            sgst="1.80",
            grand_total="23.60",
        )

        april = self._get(from_date="2025-04-01", to_date="2025-04-30")
        self.assertEqual(april.status_code, 200)
        self.assertEqual(april.data["count"], 1)
        self.assertEqual(april.data["results"][0]["sales_invoice_number"], invoice.invoice_number)
        self.assertEqual(self._money(april.data["totals"]["grand_total"]), Decimal("118.00"))

        may = self._get(from_date="2025-05-01", to_date="2025-05-31")
        self.assertEqual(may.status_code, 200)
        self.assertEqual(may.data["count"], 1)
        self.assertEqual(may.data["results"][0]["sales_invoice_number"], credit.invoice_number)
        self.assertEqual(self._money(may.data["totals"]["grand_total"]), Decimal("-23.60"))

    def test_original_and_correction_rows_keep_distinct_sales_drilldowns(self):
        invoice = self._create_sales_document(
            status=SalesInvoiceHeader.Status.POSTED,
            invoice_number="INV-TRACE-001",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="118.00",
        )
        credit = self._create_sales_document(
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=invoice,
            status=SalesInvoiceHeader.Status.POSTED,
            invoice_number="CRN-TRACE-001",
            taxable="40.00",
            cgst="3.60",
            sgst="3.60",
            grand_total="47.20",
        )

        response = self._get()
        self.assertEqual(response.status_code, 200)

        invoice_row = next(row for row in response.data["results"] if row["sales_invoice_number"] == invoice.invoice_number)
        credit_row = next(row for row in response.data["results"] if row["sales_invoice_number"] == credit.invoice_number)

        self.assertEqual(invoice_row["drilldown"]["target"], "sales_invoice_detail")
        self.assertEqual(invoice_row["drilldown"]["id"], invoice.id)
        self.assertEqual(invoice_row["drilldown"]["route"], "/saleinvoice")
        self.assertEqual(credit_row["drilldown"]["target"], "sales_invoice_detail")
        self.assertEqual(credit_row["drilldown"]["id"], credit.id)
        self.assertEqual(credit_row["linked_credit_debit_note_reference"], invoice.invoice_number)

    def test_service_sales_rows_expose_service_invoice_route_in_drilldown(self):
        invoice = self._create_sales_document(
            invoice_number="SINV-SVC-01",
            bill_date="2025-04-18",
            posting_date="2025-04-18",
        )
        SalesInvoiceLine.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=invoice,
            line_no=99,
            product=self.product,
            uom=self.uom,
            hsn_sac_code="9983",
            is_service=True,
            qty=Decimal("1.000"),
            free_qty=Decimal("0.000"),
            rate=Decimal("10.0000"),
            discount_type=SalesInvoiceLine.DiscountType.NONE,
            discount_percent=Decimal("0.0000"),
            discount_amount=Decimal("0.00"),
            gst_rate=Decimal("18.00"),
            taxable_value=Decimal("10.00"),
            cgst_amount=Decimal("0.90"),
            sgst_amount=Decimal("0.90"),
            igst_amount=Decimal("0.00"),
            cess_percent=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
            line_total=Decimal("11.80"),
        )

        response = self._get(search="SINV-SVC-01")
        self.assertEqual(response.status_code, 200)
        invoice_row = next(row for row in response.data["results"] if row["sales_invoice_number"] == invoice.invoice_number)
        self.assertEqual(invoice_row["drilldown"]["route"], "/saleserviceinvoice")

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

    def test_taxability_rows_keep_zero_tax_and_classification_labels(self):
        exempt = self._create_sales_document(
            invoice_number="EXEMPT-001",
            taxable="1000.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
            grand_total="1000.00",
            taxability=SalesInvoiceHeader.Taxability.EXEMPT,
        )
        nil_rated = self._create_sales_document(
            invoice_number="NIL-001",
            bill_date="2025-04-06",
            posting_date="2025-04-06",
            taxable="1000.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
            grand_total="1000.00",
            taxability=SalesInvoiceHeader.Taxability.NIL_RATED,
        )
        non_gst = self._create_sales_document(
            invoice_number="NONGST-001",
            bill_date="2025-04-07",
            posting_date="2025-04-07",
            taxable="1000.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
            grand_total="1000.00",
            taxability=SalesInvoiceHeader.Taxability.NON_GST,
        )

        response = self._get(status=str(SalesInvoiceHeader.Status.POSTED))
        self.assertEqual(response.status_code, 200)

        rows = {row["sales_invoice_number"]: row for row in response.data["results"]}
        self.assertEqual(rows[exempt.invoice_number]["supply_classification_name"], "Exempt")
        self.assertEqual(rows[nil_rated.invoice_number]["supply_classification_name"], "Nil-rated")
        self.assertEqual(rows[non_gst.invoice_number]["supply_classification_name"], "Non-GST")
        for invoice_number in (exempt.invoice_number, nil_rated.invoice_number, non_gst.invoice_number):
            self.assertEqual(self._money(rows[invoice_number]["cgst_amount"]), Decimal("0.00"))
            self.assertEqual(self._money(rows[invoice_number]["sgst_amount"]), Decimal("0.00"))
            self.assertEqual(self._money(rows[invoice_number]["igst_amount"]), Decimal("0.00"))
            self.assertEqual(self._money(rows[invoice_number]["grand_total"]), Decimal("1000.00"))

    def test_note_rows_keep_signed_totals_and_document_types(self):
        invoice = self._create_sales_document(
            invoice_number="INV-NOTE-001",
            taxable="1000.00",
            cgst="90.00",
            sgst="90.00",
            grand_total="1180.00",
        )
        sales_return = self._create_sales_document(
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=invoice,
            note_reason=SalesInvoiceHeader.NoteReason.QUANTITY_RETURN,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2025-04-06",
            posting_date="2025-04-06",
            invoice_number="SRN-001",
            taxable="1000.00",
            cgst="90.00",
            sgst="90.00",
            grand_total="1180.00",
        )
        credit = self._create_sales_document(
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=invoice,
            note_reason=SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2025-04-07",
            posting_date="2025-04-07",
            invoice_number="CRN-002",
            taxable="500.00",
            igst="90.00",
            cgst="0.00",
            sgst="0.00",
            grand_total="590.00",
        )
        debit = self._create_sales_document(
            doc_type=SalesInvoiceHeader.DocType.DEBIT_NOTE,
            original_invoice=invoice,
            note_reason=SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2025-04-08",
            posting_date="2025-04-08",
            invoice_number="DBN-001",
            taxable="500.00",
            igst="90.00",
            cgst="0.00",
            sgst="0.00",
            grand_total="590.00",
        )

        response = self._get(status=str(SalesInvoiceHeader.Status.POSTED))
        self.assertEqual(response.status_code, 200)
        rows = {row["sales_invoice_number"]: row for row in response.data["results"]}

        self.assertEqual(rows[sales_return.invoice_number]["doc_type_name"], "Credit Note")
        self.assertEqual(self._money(rows[sales_return.invoice_number]["taxable_amount"]), Decimal("-1000.00"))
        self.assertEqual(self._money(rows[sales_return.invoice_number]["cgst_amount"]), Decimal("-90.00"))
        self.assertEqual(self._money(rows[sales_return.invoice_number]["sgst_amount"]), Decimal("-90.00"))
        self.assertEqual(self._money(rows[sales_return.invoice_number]["grand_total"]), Decimal("-1180.00"))

        self.assertEqual(rows[credit.invoice_number]["doc_type_name"], "Credit Note")
        self.assertEqual(self._money(rows[credit.invoice_number]["taxable_amount"]), Decimal("-500.00"))
        self.assertEqual(self._money(rows[credit.invoice_number]["igst_amount"]), Decimal("-90.00"))
        self.assertEqual(self._money(rows[credit.invoice_number]["grand_total"]), Decimal("-590.00"))

        self.assertEqual(rows[debit.invoice_number]["doc_type_name"], "Debit Note")
        self.assertEqual(self._money(rows[debit.invoice_number]["taxable_amount"]), Decimal("500.00"))
        self.assertEqual(self._money(rows[debit.invoice_number]["igst_amount"]), Decimal("90.00"))
        self.assertEqual(self._money(rows[debit.invoice_number]["grand_total"]), Decimal("590.00"))

    def test_filed_period_correction_note_stays_in_current_period_register(self):
        original = self._create_sales_document(
            invoice_number="ORIG-FILED-001",
            bill_date="2025-03-29",
            posting_date="2025-03-29",
            taxable="1000.00",
            cgst="90.00",
            sgst="90.00",
            grand_total="1180.00",
        )
        correction = self._create_sales_document(
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=original,
            note_reason=SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2025-04-12",
            posting_date="2025-04-12",
            invoice_number="AMEND-001",
            taxable="200.00",
            cgst="18.00",
            sgst="18.00",
            grand_total="236.00",
        )

        response = self._get(from_date="2025-04-01", to_date="2025-04-30", status=str(SalesInvoiceHeader.Status.POSTED))
        self.assertEqual(response.status_code, 200)
        invoice_numbers = {row["sales_invoice_number"] for row in response.data["results"]}
        self.assertIn(correction.invoice_number, invoice_numbers)
        self.assertNotIn(original.invoice_number, invoice_numbers)

        correction_row = next(row for row in response.data["results"] if row["sales_invoice_number"] == correction.invoice_number)
        self.assertEqual(correction_row["linked_credit_debit_note_reference"], original.invoice_number)
        self.assertEqual(correction_row["invoice_date"], "12-04-2025")
        self.assertEqual(self._money(correction_row["taxable_amount"]), Decimal("-200.00"))
        self.assertEqual(self._money(correction_row["grand_total"]), Decimal("-236.00"))

    def test_joined_einvoice_and_eway_artifacts_are_exposed(self):
        header = self._create_sales_document(invoice_number="EINV-001")
        SalesEInvoice.objects.create(
            invoice=header,
            status=1,
            irn="IRN-123",
            ack_no="ACK-123",
            ack_date=timezone.now(),
            created_by=self.user,
        )
        SalesEWayBill.objects.create(
            invoice=header,
            status=1,
            ewb_no="EWB-123",
            ewb_date=timezone.now(),
            created_by=self.user,
        )

        response = self._get(search="EINV-001")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["sales_invoice_number"], "EINV-001")
        self.assertEqual(row["e_invoice_no"], "IRN-123")
        self.assertEqual(row["e_way_bill_no"], "EWB-123")
