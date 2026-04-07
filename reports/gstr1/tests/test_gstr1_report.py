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
from financial.profile_access import account_gstno
from financial.models import Ledger, account, accountHead, accounttype
from financial.services import apply_normalized_profile_payload, create_account_with_synced_ledger
from geography.models import City, Country, District, State
from sales.models import (
    SalesAdvanceAdjustment,
    SalesEcommerceSupply,
    SalesInvoiceHeader,
    SalesInvoiceLine,
    SalesTaxSummary,
)


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class Gstr1ReportAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="gstr1-user",
            email="gstr1@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)

        self.summary_url = reverse("reports_api:gstr1-summary")
        self.section_url = lambda section: reverse("reports_api:gstr1-section", args=[section])
        self.validation_url = reverse("reports_api:gstr1-validations")
        self.meta_url = reverse("reports_api:gstr1-meta")
        self.export_url = reverse("reports_api:gstr1-export")
        self.invoice_url = lambda pk: reverse("reports_api:gstr1-invoice-detail", args=[pk])
        self.table_url = lambda code: reverse("reports_api:gstr1-table", args=[code])

        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.other_state = State.objects.create(statename="Karnataka", statecode="29", country=self.country)
        self.district = District.objects.create(districtname="District", districtcode="DT", state=self.state)
        self.city = City.objects.create(cityname="Mumbai", citycode="MUM", pincode="400001", distt=self.district)
        self.unit_type = UnitType.objects.create(UnitName="Business", UnitDesc="Business")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")

        self.entity = Entity.objects.create(
            entityname="Finacc Entity",
            legalname="Finacc Entity Pvt Ltd",
            unitType=self.unit_type,
            GstRegitrationType=self.gst_type,
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
        self.customer_alpha = self._create_customer(name="Alpha Retail", gstin="27ABCDE1234F1Z5", accountcode=5001)
        self.customer_beta = self._create_customer(name="Beta Mart", gstin="", accountcode=5002)

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
            "from_date": "2025-04-01",
            "to_date": "2025-04-30",
        }
        self.doc_no_seq = 1

    def _make_gstin(self, prefix14: str, *, valid=True):
        base36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        factors = [1, 2]
        total = 0
        for idx, ch in enumerate(prefix14):
            val = base36.index(ch)
            product = val * factors[idx % 2]
            total += (product // 36) + (product % 36)
        check_code = (36 - (total % 36)) % 36
        check_char = base36[check_code]
        if not valid:
            check_char = base36[(check_code + 1) % 36]
        return prefix14 + check_char

    def _create_customer(self, *, name, gstin, accountcode):
        ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=accountcode,
            name=name,
            accounthead=self.customer_head,
            createdby=self.user,
        )
        customer = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": ledger,
                "accountname": name,
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": accountcode, "accounthead": self.customer_head, "is_party": True},
        )
        apply_normalized_profile_payload(
            customer,
            compliance_data={"gstno": gstin},
            commercial_data={"partytype": "Customer"},
            createdby=self.user,
        )
        return customer

    def _create_sales_document(
        self,
        *,
        customer,
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
        grand_total="118.00",
        supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
        tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
        is_igst=None,
        taxability=SalesInvoiceHeader.Taxability.TAXABLE,
        place_of_supply="27",
        hsn_code="1001",
        original_invoice=None,
        customer_gstin=None,
        doc_code_override=None,
    ):
        doc_code_map = {
            SalesInvoiceHeader.DocType.TAX_INVOICE: "SINV",
            SalesInvoiceHeader.DocType.CREDIT_NOTE: "SCN",
            SalesInvoiceHeader.DocType.DEBIT_NOTE: "SDN",
        }
        doc_no = self.doc_no_seq
        self.doc_no_seq += 1
        doc_code = doc_code_override or doc_code_map[doc_type]

        header = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            customer=customer,
            customer_name=customer.accountname,
            customer_gstin=customer_gstin if customer_gstin is not None else account_gstno(customer),
            customer_state_code=customer_gstin and "27" or "",
            seller_gstin="27AAAAA1111A1Z1",
            seller_state_code="27",
            doc_type=doc_type,
            status=status,
            bill_date=bill_date,
            posting_date=posting_date,
            doc_code=doc_code,
            doc_no=doc_no,
            invoice_number=invoice_number or f"INV-{doc_no:03d}",
            supply_category=supply_category,
            taxability=taxability,
            tax_regime=tax_regime,
            is_igst=is_igst if is_igst is not None else (tax_regime == SalesInvoiceHeader.TaxRegime.INTER_STATE),
            place_of_supply_state_code=place_of_supply,
            total_taxable_value=Decimal(taxable),
            total_cgst=Decimal(cgst),
            total_sgst=Decimal(sgst),
            total_igst=Decimal(igst),
            total_cess=Decimal(cess),
            grand_total=Decimal(grand_total),
            original_invoice=original_invoice,
        )
        SalesInvoiceLine.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=header,
            line_no=1,
            product=self.product,
            uom=self.uom,
            hsn_sac_code=hsn_code or "",
            qty=Decimal("1.000"),
            rate=Decimal(taxable),
            gst_rate=Decimal("18.00"),
            taxable_value=Decimal(taxable),
            cgst_amount=Decimal(cgst),
            sgst_amount=Decimal(sgst),
            igst_amount=Decimal(igst),
            cess_amount=Decimal(cess),
            line_total=Decimal(grand_total),
        )
        SalesTaxSummary.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=header,
            taxability=taxability,
            hsn_sac_code=hsn_code or "",
            is_service=False,
            gst_rate=Decimal("18.00"),
            taxable_value=Decimal(taxable),
            cgst_amount=Decimal(cgst),
            sgst_amount=Decimal(sgst),
            igst_amount=Decimal(igst),
            cess_amount=Decimal(cess),
        )
        return header

    def test_summary_endpoint(self):
        self._create_sales_document(customer=self.customer_alpha)
        self._create_sales_document(customer=self.customer_beta, supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C)
        self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
        )
        response = self.client.get(self.summary_url, self.base_params)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("summary", data)
        self.assertIn("sections", data["summary"])
        self.assertIn("hsn_summary", data["summary"])

    def test_section_classification(self):
        self._create_sales_document(customer=self.customer_alpha, supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B)
        self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            grand_total="300000.00",
            taxable="250000.00",
            cgst="0.00",
            sgst="0.00",
            igst="45000.00",
            place_of_supply="29",
        )
        self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
        )
        exp = self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
        )
        self._create_sales_document(
            customer=self.customer_alpha,
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=exp,
        )
        self._create_sales_document(
            customer=self.customer_beta,
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=exp,
            customer_gstin="",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
        )

        response = self.client.get(self.section_url("B2B"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)

        response = self.client.get(self.section_url("B2CL"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)

        response = self.client.get(self.section_url("B2CS"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)

        response = self.client.get(self.section_url("EXP"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)

        response = self.client.get(self.section_url("CDNR"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)

        response = self.client.get(self.section_url("CDNUR"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)

    def test_section_pagination_links(self):
        self._create_sales_document(customer=self.customer_alpha)
        self._create_sales_document(customer=self.customer_alpha)
        response = self.client.get(self.section_url("B2B"), {**self.base_params, "page_size": 1})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNotNone(data.get("next"))
        self.assertIsNone(data.get("previous"))

    def test_section_smart_filters(self):
        self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            grand_total="300000.00",
            taxable="250000.00",
            cgst="0.00",
            sgst="0.00",
            igst="45000.00",
            place_of_supply="29",
            invoice_number="BIG-001",
        )
        self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            grand_total="90000.00",
            taxable="75000.00",
            cgst="0.00",
            sgst="0.00",
            igst="15000.00",
            place_of_supply="27",
            invoice_number="SMALL-001",
        )
        response = self.client.get(
            self.section_url("B2CL"),
            {
                **self.base_params,
                "pos": "29",
                "min_taxable_value": "200000",
                "search": "BIG",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("count"), 1)
        self.assertEqual(data["results"][0]["invoice_number"], "BIG-001")

    def test_validation_warnings(self):
        self._create_sales_document(
            customer=self.customer_alpha,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            customer_gstin="",
        )
        response = self.client.get(self.validation_url, self.base_params)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        codes = {item["code"] for item in data.get("warnings", [])}
        self.assertIn("B2B_GSTIN_REQUIRED", codes)

    def test_validation_warning_severity_filter(self):
        self._create_sales_document(
            customer=self.customer_alpha,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            customer_gstin="",
        )
        warning_response = self.client.get(self.validation_url, {**self.base_params, "warning_severity": "warning"})
        self.assertEqual(warning_response.status_code, 200)
        self.assertGreaterEqual(warning_response.json().get("warning_count", 0), 1)

        error_response = self.client.get(self.validation_url, {**self.base_params, "warning_severity": "error"})
        self.assertEqual(error_response.status_code, 200)
        self.assertEqual(error_response.json().get("warning_count", 0), 0)

    def test_b2cl_threshold_boundary(self):
        self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            grand_total="250000.00",
            taxable="211864.41",
            cgst="0.00",
            sgst="0.00",
            igst="38135.59",
            place_of_supply="29",
        )
        self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            grand_total="249999.00",
            taxable="211864.00",
            cgst="0.00",
            sgst="0.00",
            igst="38135.00",
            place_of_supply="29",
        )
        response = self.client.get(self.section_url("B2CL"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)
        response = self.client.get(self.section_url("B2CS"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)

    def test_meta_endpoint(self):
        response = self.client.get(self.meta_url, {"entity": self.entity.id})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("supported_sections", payload)
        self.assertIn("supported_tables", payload)
        self.assertIn("thresholds", payload)
        self.assertIn("choices", payload)
        self.assertIn("taxability", payload["choices"])
        self.assertIn("tax_regime", payload["choices"])
        self.assertIn("supply_category", payload["choices"])
        self.assertIn("doc_type", payload["choices"])
        self.assertIn("status", payload["choices"])

    def test_table_endpoint_taxpayer(self):
        response = self.client.get(self.table_url("TAXPAYER_1_3"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["table_code"], "TAXPAYER_1_3")
        self.assertEqual(payload["coverage"]["status"], "implemented")
        self.assertEqual(payload["count"], 1)

    def test_table_endpoint_eco_sections(self):
        SalesEcommerceSupply.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            invoice_date="2025-04-12",
            invoice_number="ECO-001",
            operator_gstin="27ABCDE1234F1Z5",
            supplier_eco_gstin="27ABCDE1234F1Z5",
            supply_split=SalesEcommerceSupply.SupplySplit.B2B,
            taxable_value=Decimal("1000.00"),
            cgst_amount=Decimal("90.00"),
            sgst_amount=Decimal("90.00"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
        )
        response = self.client.get(self.table_url("TABLE_14"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["coverage"]["status"], "implemented")
        self.assertEqual(payload["count"], 1)

    def test_table_endpoint_advances(self):
        SalesAdvanceAdjustment.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_date="2025-04-20",
            voucher_number="ADV-001",
            customer=self.customer_alpha,
            customer_name=self.customer_alpha.accountname or "Alpha Retail",
            customer_gstin=account_gstno(self.customer_alpha),
            place_of_supply_state_code="27",
            entry_type=SalesAdvanceAdjustment.EntryType.ADVANCE_RECEIPT,
            taxable_value=Decimal("500.00"),
            cgst_amount=Decimal("45.00"),
            sgst_amount=Decimal("45.00"),
        )
        response = self.client.get(self.table_url("TABLE_11"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["coverage"]["status"], "implemented")
        self.assertEqual(payload["count"], 1)

    def test_table_endpoints_5_7_10(self):
        b2cl = self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            grand_total="300000.00",
            taxable="250000.00",
            cgst="0.00",
            sgst="0.00",
            igst="45000.00",
            place_of_supply="29",
        )
        b2cs = self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            grand_total="1180.00",
            taxable="1000.00",
            cgst="90.00",
            sgst="90.00",
            igst="0.00",
            place_of_supply="27",
        )
        self._create_sales_document(
            customer=self.customer_beta,
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=b2cs,
            customer_gstin="",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="29",
        )

        response = self.client.get(self.table_url("TABLE_5"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["coverage"]["status"], "implemented")
        self.assertGreaterEqual(payload["count"], 1)
        self.assertEqual(payload["rows"][0]["invoice_id"], b2cl.id)

        response = self.client.get(self.table_url("TABLE_7"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["coverage"]["status"], "implemented")
        self.assertGreaterEqual(payload["count"], 1)

        response = self.client.get(self.table_url("TABLE_10"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["coverage"]["status"], "implemented")
        self.assertGreaterEqual(payload["count"], 1)

    def test_export_smoke(self):
        self._create_sales_document(customer=self.customer_alpha)
        response = self.client.get(self.export_url, {**self.base_params, "format": "csv"})
        self.assertEqual(response.status_code, 200)
        response = self.client.get(self.export_url, {**self.base_params, "format": "xlsx"})
        self.assertEqual(response.status_code, 200)
        response = self.client.get(self.export_url, {**self.base_params, "format": "csv", "section": "B2B"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Intra-state", response.content.decode("utf-8"))

    def test_export_section_respects_smart_filters(self):
        self._create_sales_document(customer=self.customer_alpha, invoice_number="ALPHA-EXP-1")
        self._create_sales_document(customer=self.customer_alpha, invoice_number="BETA-EXP-1")
        response = self.client.get(
            self.export_url,
            {**self.base_params, "format": "csv", "section": "B2B", "search": "ALPHA-EXP-1"},
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("ALPHA-EXP-1", content)
        self.assertNotIn("BETA-EXP-1", content)

    def test_export_empty_section(self):
        response = self.client.get(self.export_url, {**self.base_params, "format": "csv", "section": "B2B"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Invoice Date", response.content.decode("utf-8"))

    def test_tax_split_validation(self):
        self._create_sales_document(
            customer=self.customer_alpha,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            igst="10.00",
            cgst="0.00",
            sgst="0.00",
        )
        response = self.client.get(self.validation_url, self.base_params)
        self.assertEqual(response.status_code, 200)
        codes = {item["code"] for item in response.json().get("warnings", [])}
        self.assertIn("IGST_ON_INTRASTATE", codes)

    def test_invalid_note_linkage_warning(self):
        self._create_sales_document(
            customer=self.customer_alpha,
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=None,
        )
        response = self.client.get(self.validation_url, self.base_params)
        self.assertEqual(response.status_code, 200)
        codes = {item["code"] for item in response.json().get("warnings", [])}
        self.assertIn("NOTE_LINK_MISSING", codes)

    def test_invalid_place_of_supply_warning(self):
        self._create_sales_document(
            customer=self.customer_alpha,
            place_of_supply="AA",
        )
        response = self.client.get(self.validation_url, self.base_params)
        self.assertEqual(response.status_code, 200)
        codes = {item["code"] for item in response.json().get("warnings", [])}
        self.assertIn("INVALID_PLACE_OF_SUPPLY", codes)

    def test_summary_vs_section_totals_alignment(self):
        inv = self._create_sales_document(customer=self.customer_alpha, taxable="200.00", cgst="18.00", sgst="18.00", grand_total="236.00")
        summary = self.client.get(self.summary_url, self.base_params).json()["summary"]["sections"]
        b2b = next(row for row in summary if row["section"] == "B2B")
        section = self.client.get(self.section_url("B2B"), self.base_params).json()
        row = section["results"][0]
        self.assertEqual(str(b2b["taxable_amount"]), str(row["taxable_amount"]))
        self.assertEqual(str(b2b["grand_total"]), str(row["grand_total"]))

    def test_requires_auth(self):
        anon = APIClient()
        response = anon.get(self.summary_url, self.base_params)
        self.assertIn(response.status_code, (401, 403))

    @override_settings(GSTR1_ENABLE_GSTIN_CHECKSUM=False)
    def test_checksum_validation_disabled(self):
        bad_checksum = self._make_gstin("27ABCDE1234F1Z", valid=False)
        self._create_sales_document(customer=self.customer_alpha, customer_gstin=bad_checksum)
        response = self.client.get(self.validation_url, self.base_params)
        codes = {item["code"] for item in response.json().get("warnings", [])}
        self.assertNotIn("INVALID_GSTIN", codes)

    @override_settings(GSTR1_ENABLE_GSTIN_CHECKSUM=True)
    def test_checksum_validation_enabled(self):
        bad_checksum = self._make_gstin("27ABCDE1234F1Z", valid=False)
        self._create_sales_document(customer=self.customer_alpha, customer_gstin=bad_checksum)
        response = self.client.get(self.validation_url, self.base_params)
        codes = {item["code"] for item in response.json().get("warnings", [])}
        self.assertIn("INVALID_GSTIN", codes)

    @override_settings(GSTR1_B2CL_THRESHOLD="100000.00")
    def test_b2cl_threshold_override(self):
        self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            grand_total="150000.00",
            taxable="127118.64",
            cgst="0.00",
            sgst="0.00",
            igst="22881.36",
            place_of_supply="29",
        )
        response = self.client.get(self.section_url("B2CL"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)

    @override_settings(GSTR1_EXPORT_POS="27")
    def test_export_pos_override(self):
        self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="27",
        )
        response = self.client.get(self.validation_url, self.base_params)
        codes = {item["code"] for item in response.json().get("warnings", [])}
        self.assertNotIn("EXPORT_POS_INVALID", codes)

    @override_settings(GSTR1_B2CL_THRESHOLD="111111.11", GSTR1_EXPORT_POS="27", GSTR1_ENABLE_GSTIN_CHECKSUM=True)
    def test_meta_shows_config(self):
        response = self.client.get(self.meta_url, {"entity": self.entity.id})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["thresholds"]["b2cl_invoice_value"], "111111.11")
        self.assertEqual(payload["config"]["export_pos_code"], "27")
        self.assertTrue(payload["config"]["gstin_checksum_enabled"])

    def test_invalid_gstin_classification_override(self):
        self._create_sales_document(
            customer=self.customer_alpha,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            customer_gstin="INVALIDGSTIN",
        )
        response = self.client.get(self.section_url("B2B"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)
        validation = self.client.get(self.validation_url, self.base_params)
        codes = {item["code"] for item in validation.json().get("warnings", [])}
        self.assertIn("INVALID_GSTIN", codes)
        self.assertIn("B2B_GSTIN_REQUIRED", codes)

    def test_interstate_fallback_uses_pos(self):
        self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            is_igst=False,
            place_of_supply="29",
            grand_total="300000.00",
            taxable="250000.00",
            cgst="0.00",
            sgst="0.00",
            igst="45000.00",
        )
        response = self.client.get(self.section_url("B2CL"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)

    def test_cdnr_based_on_original_invoice(self):
        original = self._create_sales_document(
            customer=self.customer_alpha,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
        )
        self._create_sales_document(
            customer=self.customer_beta,
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=original,
            customer_gstin="",
        )
        response = self.client.get(self.section_url("CDNR"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("count", 0), 1)

    def test_duplicate_invoice_detection_with_doc_code(self):
        inv = self._create_sales_document(customer=self.customer_alpha)
        self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number=inv.invoice_number,
            doc_code_override="SINV-DUP",
        )
        response = self.client.get(self.validation_url, self.base_params)
        codes = {item["code"] for item in response.json().get("warnings", [])}
        self.assertIn("DUPLICATE_INVOICE", codes)

    def test_pos_tax_regime_mismatch_validation(self):
        self._create_sales_document(
            customer=self.customer_alpha,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="27",
        )
        response = self.client.get(self.validation_url, self.base_params)
        codes = {item["code"] for item in response.json().get("warnings", [])}
        self.assertIn("POS_TAX_REGIME_MISMATCH", codes)

    def test_export_pos_validation(self):
        self._create_sales_document(
            customer=self.customer_beta,
            supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="27",
        )
        response = self.client.get(self.validation_url, self.base_params)
        codes = {item["code"] for item in response.json().get("warnings", [])}
        self.assertIn("EXPORT_POS_INVALID", codes)

    def test_nil_exempt_tax_validation(self):
        header = self._create_sales_document(
            customer=self.customer_alpha,
            taxability=SalesInvoiceHeader.Taxability.EXEMPT,
            cgst="5.00",
            sgst="5.00",
            grand_total="110.00",
        )
        SalesTaxSummary.objects.filter(header=header).update(
            taxability=SalesInvoiceHeader.Taxability.EXEMPT,
            cgst_amount=Decimal("5.00"),
            sgst_amount=Decimal("5.00"),
        )
        response = self.client.get(self.validation_url, self.base_params)
        codes = {item["code"] for item in response.json().get("warnings", [])}
        self.assertIn("NIL_EXEMPT_TAX_PRESENT", codes)
