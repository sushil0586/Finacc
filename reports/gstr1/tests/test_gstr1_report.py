from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
from financial.profile_access import account_gstno
from financial.models import Ledger, account, accountHead, accounttype
from financial.services import apply_normalized_profile_payload, create_account_with_synced_ledger
from geography.models import City, Country, District, State
from posting.models import Entry, EntryStatus, TxnType
from sales.models import (
    SalesAdvanceAdjustment,
    SalesChargeLine,
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
        self.permission_codes_patch = patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.gst.view", "reports.gstr1report.view"],
        )
        self.permission_codes_patch.start()
        self.addCleanup(self.permission_codes_patch.stop)
        self.client.force_authenticate(user=self.user)
        self.summary_url = reverse("reports_api:gstr1-summary")
        self.readiness_url = reverse("reports_api:gstr1-readiness")
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
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Finacc Entity",
            legalname="Finacc Entity Pvt Ltd",
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
        resolved_customer_gstin = customer_gstin if customer_gstin is not None else (account_gstno(customer) or "")

        header = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            customer=customer,
            customer_name=customer.accountname,
            customer_gstin=resolved_customer_gstin,
            customer_state_code="27" if resolved_customer_gstin else "",
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

    def test_invoice_detail_includes_posting_lookup_and_drilldowns(self):
        invoice = self._create_sales_document(customer=self.customer_alpha)
        Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=invoice.id,
            voucher_no="SINV-POST-001",
            voucher_date=invoice.bill_date,
            posting_date=invoice.posting_date,
            status=EntryStatus.POSTED,
            created_by=self.user,
        )

        response = self.client.get(self.invoice_url(invoice.id), self.base_params)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["invoice"]["id"], invoice.id)
        self.assertEqual(data["posting_lookup"]["entry_id"], Entry.objects.get(txn_id=invoice.id, txn_type=TxnType.SALES).id)
        self.assertEqual(data["posting_lookup"]["document_type"], "sales_invoice")
        self.assertEqual(data["drilldowns"]["source_document"]["drilldown_target"], "sales_invoice_detail")
        self.assertEqual(data["drilldowns"]["source_document"]["drilldown_params"]["id"], invoice.id)
        self.assertEqual(data["drilldowns"]["posting_detail"]["drilldown_target"], "journal_entry_detail")
        self.assertEqual(
            data["drilldowns"]["posting_detail"]["query_params"]["entityfinid"],
            self.entityfin.id,
        )

    def test_invoice_detail_handles_missing_posting_entry(self):
        invoice = self._create_sales_document(customer=self.customer_alpha)

        response = self.client.get(self.invoice_url(invoice.id), self.base_params)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["posting_lookup"])
        self.assertIsNone(data["drilldowns"]["posting_detail"])

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

    def test_section_smart_filters_min_gst_rate(self):
        self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="GST18-001",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            hsn_code="1001",
        )
        header = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="GST05-001",
            taxable="100.00",
            cgst="2.50",
            sgst="2.50",
            hsn_code="1002",
        )
        header.tax_summaries.all().delete()
        SalesTaxSummary.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=header,
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            hsn_sac_code="1002",
            is_service=False,
            gst_rate=Decimal("5.00"),
            taxable_value=Decimal("100.00"),
            cgst_amount=Decimal("2.50"),
            sgst_amount=Decimal("2.50"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
        )

        response = self.client.get(
            self.section_url("B2B"),
            {
                **self.base_params,
                "min_gst_rate": "12.00",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("count"), 1)
        self.assertEqual(data["results"][0]["invoice_number"], "GST18-001")

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

    def test_readiness_endpoint_returns_blocked_status_and_export_actions(self):
        invoice = self._create_sales_document(
            customer=self.customer_alpha,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            customer_gstin="",
        )
        response = self.client.get(self.readiness_url, self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        readiness = payload["readiness"]
        self.assertEqual(readiness["status"]["code"], "blocked")
        self.assertGreaterEqual(readiness["counts"]["blocked_warnings"], 1)
        invoice_warning = next(item for item in readiness["warnings"] if item.get("invoice_id") == invoice.id)
        self.assertIn("invoice_detail_url", invoice_warning)
        self.assertEqual(invoice_warning["drilldowns"]["source_document"]["target"], "sales_invoice_detail")
        self.assertEqual(invoice_warning["drilldowns"]["source_document"]["params"]["transactionid"], invoice.id)
        self.assertEqual(invoice_warning["drilldowns"]["posting_lookup"]["lookup"]["document_type"], "sales_invoice")
        self.assertIn("gstn_json", payload["actions"]["export_urls"])
        self.assertIn("gstn_json", payload["available_exports"])

    def test_readiness_source_document_drilldown_uses_service_invoice_route_for_service_rows(self):
        invoice = self._create_sales_document(
            customer=self.customer_alpha,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            invoice_number="SRV-001",
            customer_gstin="",
        )
        invoice.lines.update(is_service=True, hsn_sac_code="9983")

        response = self.client.get(self.readiness_url, self.base_params)

        self.assertEqual(response.status_code, 200)
        readiness = response.json()["readiness"]
        invoice_warning = next(item for item in readiness["warnings"] if item.get("invoice_id") == invoice.id)
        self.assertEqual(invoice_warning["drilldowns"]["source_document"]["route"], "/saleserviceinvoice")

    def test_readiness_endpoint_returns_review_status_for_tax_mismatch(self):
        invoice = self._create_sales_document(customer=self.customer_alpha, invoice_number="REVIEW-001")
        invoice.lines.update(line_total=Decimal("10.00"))
        response = self.client.get(self.readiness_url, self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        readiness = payload["readiness"]
        self.assertEqual(readiness["status"]["code"], "review")
        self.assertEqual(readiness["counts"]["blocked_warnings"], 0)
        self.assertGreaterEqual(readiness["counts"]["review_warnings"], 1)
        codes = {item["code"] for item in readiness["warnings"]}
        self.assertIn("INVOICE_TOTAL_MISMATCH", codes)

    def test_readiness_skips_invoice_total_warning_when_additional_charges_explain_total(self):
        invoice = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="CHARGE-001",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="124.40",
        )
        invoice.lines.update(line_total=Decimal("118.00"))
        invoice.total_other_charges = Decimal("5.00")
        invoice.round_off = Decimal("0.50")
        invoice.grand_total = Decimal("124.40")
        invoice.save(update_fields=["total_other_charges", "round_off", "grand_total"])
        SalesChargeLine.objects.create(
            header=invoice,
            line_no=1,
            charge_type=SalesChargeLine.ChargeType.OTHER,
            taxable_value=Decimal("5.00"),
            cgst_amount=Decimal("0.45"),
            sgst_amount=Decimal("0.45"),
            igst_amount=Decimal("0.00"),
            total_value=Decimal("5.90"),
        )

        response = self.client.get(self.readiness_url, self.base_params)

        self.assertEqual(response.status_code, 200)
        readiness = response.json()["readiness"]
        codes = {item["code"] for item in readiness["warnings"]}
        self.assertNotIn("INVOICE_TOTAL_MISMATCH", codes)

    def test_validation_endpoint_includes_readiness_snapshot(self):
        self._create_sales_document(
            customer=self.customer_alpha,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            customer_gstin="",
        )
        response = self.client.get(self.validation_url, self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("readiness", payload)
        self.assertEqual(payload["readiness"]["status"]["code"], "blocked")
        self.assertGreaterEqual(len(payload["readiness"]["validation_groups"]), 1)

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
        self.assertIn("readiness", payload["endpoints"])

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
        self.assertEqual(payload["groups"]["11A"]["count"], 1)
        self.assertEqual(payload["groups"]["11B"]["count"], 0)

    def test_table_endpoint_splits_advance_receipts_and_adjustments(self):
        invoice = self._create_sales_document(customer=self.customer_alpha)
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
        SalesAdvanceAdjustment.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_date="2025-04-25",
            voucher_number="ADJ-001",
            customer=self.customer_alpha,
            customer_name=self.customer_alpha.accountname or "Alpha Retail",
            customer_gstin=account_gstno(self.customer_alpha),
            place_of_supply_state_code="27",
            entry_type=SalesAdvanceAdjustment.EntryType.ADVANCE_ADJUSTMENT,
            taxable_value=Decimal("300.00"),
            cgst_amount=Decimal("27.00"),
            sgst_amount=Decimal("27.00"),
            linked_invoice=invoice,
        )
        response = self.client.get(self.table_url("TABLE_11"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["coverage"]["status"], "implemented")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["groups"]["11A"]["count"], 1)
        self.assertEqual(payload["groups"]["11B"]["count"], 1)
        self.assertEqual(payload["groups"]["11B"]["rows"][0]["linked_invoice_id"], invoice.id)

    def test_gstn_json_export_keeps_table_11_group_counts_and_adjustment_linkage_consistent(self):
        invoice = self._create_sales_document(customer=self.customer_alpha, invoice_number="ADV-LINK-001")
        receipt = SalesAdvanceAdjustment.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_date="2025-04-20",
            voucher_number="ADV-JSON-001",
            customer=self.customer_alpha,
            customer_name=self.customer_alpha.accountname or "Alpha Retail",
            customer_gstin=account_gstno(self.customer_alpha),
            place_of_supply_state_code="27",
            entry_type=SalesAdvanceAdjustment.EntryType.ADVANCE_RECEIPT,
            taxable_value=Decimal("500.00"),
            cgst_amount=Decimal("45.00"),
            sgst_amount=Decimal("45.00"),
        )
        adjustment = SalesAdvanceAdjustment.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_date="2025-04-25",
            voucher_number="ADJ-JSON-001",
            customer=self.customer_alpha,
            customer_name=self.customer_alpha.accountname or "Alpha Retail",
            customer_gstin=account_gstno(self.customer_alpha),
            place_of_supply_state_code="27",
            entry_type=SalesAdvanceAdjustment.EntryType.ADVANCE_ADJUSTMENT,
            taxable_value=Decimal("300.00"),
            cgst_amount=Decimal("27.00"),
            sgst_amount=Decimal("27.00"),
            linked_invoice=invoice,
        )

        response = self.client.get(self.export_url, {**self.base_params, "format": "gstn_json"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        table11 = payload["tables"]["11"]
        table11a = payload["tables"]["11A"]
        table11b = payload["tables"]["11B"]
        self.assertEqual(len(table11), 2)
        self.assertEqual(len(table11a), 1)
        self.assertEqual(len(table11b), 1)
        self.assertEqual({row["id"] for row in table11}, {receipt.id, adjustment.id})
        self.assertEqual(table11a[0]["entry_type"], SalesAdvanceAdjustment.EntryType.ADVANCE_RECEIPT)
        self.assertEqual(table11b[0]["entry_type"], SalesAdvanceAdjustment.EntryType.ADVANCE_ADJUSTMENT)
        self.assertEqual(table11b[0]["linked_invoice_id"], invoice.id)

    def test_gstn_json_export_core_section_counts_and_taxables_match_summary(self):
        self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="B2B-SUM-001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="118.00",
        )
        self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="B2CL-SUM-001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="29",
            taxable="250000.00",
            cgst="0.00",
            sgst="0.00",
            igst="45000.00",
            grand_total="295000.00",
        )
        self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="B2CS-SUM-001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            place_of_supply="27",
            taxable="200.00",
            cgst="18.00",
            sgst="18.00",
            grand_total="236.00",
        )
        export_invoice = self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="EXP-SUM-001",
            supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="96",
            taxable="800.00",
            cgst="0.00",
            sgst="0.00",
            igst="144.00",
            grand_total="944.00",
        )
        self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="CDNR-SUM-001",
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=export_invoice,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="50.00",
            cgst="4.50",
            sgst="4.50",
            grand_total="59.00",
        )
        self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="CDNUR-SUM-001",
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=export_invoice,
            customer_gstin="",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="29",
            taxable="75.00",
            cgst="0.00",
            sgst="0.00",
            igst="13.50",
            grand_total="88.50",
        )

        summary_response = self.client.get(self.summary_url, self.base_params)
        export_response = self.client.get(self.export_url, {**self.base_params, "format": "gstn_json"})

        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(export_response.status_code, 200)

        summary_payload = summary_response.json()["summary"]["sections"]
        export_payload = export_response.json()["tables"]

        summary_by_section = {row["section"]: row for row in summary_payload}
        table_map = {
            "B2B": "4",
            "B2CL": "5",
            "EXP": "6",
            "B2CS": "7",
            "CDNUR": "10",
        }

        for section_code, table_key in table_map.items():
            export_rows = export_payload[table_key]
            summary_row = summary_by_section[section_code]
            export_count = len(export_rows)
            taxable_field = "taxable_value" if table_key == "7" else "taxable_amount"
            export_taxable = sum(Decimal(str(row.get(taxable_field) or "0")) for row in export_rows)
            self.assertEqual(export_count, int(summary_row["document_count"]), msg=section_code)
            self.assertEqual(export_taxable, Decimal(str(summary_row["taxable_amount"])), msg=section_code)

    def test_gstn_json_export_table_12_hsn_summary_matches_signed_summary(self):
        invoice = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="HSN-INV-001",
            taxable="200.00",
            cgst="18.00",
            sgst="18.00",
            grand_total="236.00",
            hsn_code="9983",
        )
        note = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="HSN-CN-001",
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=invoice,
            taxable="50.00",
            cgst="4.50",
            sgst="4.50",
            grand_total="59.00",
            hsn_code="9983",
        )
        note.lines.update(qty=Decimal("1.000"), taxable_value=Decimal("50.00"), cgst_amount=Decimal("4.50"), sgst_amount=Decimal("4.50"), line_total=Decimal("59.00"))

        summary_response = self.client.get(self.summary_url, self.base_params)
        export_response = self.client.get(self.export_url, {**self.base_params, "format": "gstn_json"})

        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(export_response.status_code, 200)

        hsn_summary = summary_response.json()["summary"]["hsn_summary"]
        table12 = export_response.json()["tables"]["12"]

        summary_row = next(row for row in hsn_summary if row["hsn_sac_code"] == "9983")
        table_row = next(row for row in table12 if row["hsn_sac_code"] == "9983")

        self.assertEqual(Decimal(str(table_row["total_qty"])), Decimal(str(summary_row["total_qty"])))
        self.assertEqual(Decimal(str(table_row["taxable_value"])), Decimal(str(summary_row["taxable_value"])))
        self.assertEqual(Decimal(str(table_row["cgst_amount"])), Decimal(str(summary_row["cgst_amount"])))
        self.assertEqual(Decimal(str(table_row["sgst_amount"])), Decimal(str(summary_row["sgst_amount"])))

    def test_gstn_json_export_preserves_eco_table_14_15_totals_and_splits(self):
        SalesEcommerceSupply.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            invoice_date="2025-04-12",
            invoice_number="ECO-B2B-001",
            operator_gstin="27OPERA1234F1Z5",
            supplier_eco_gstin="27SUPPL1234F1Z5",
            supply_split=SalesEcommerceSupply.SupplySplit.B2B,
            taxable_value=Decimal("1000.00"),
            cgst_amount=Decimal("90.00"),
            sgst_amount=Decimal("90.00"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
        )
        SalesEcommerceSupply.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            invoice_date="2025-04-15",
            invoice_number="ECO-B2C-001",
            operator_gstin="27OPERA1234F1Z5",
            supplier_eco_gstin="27SUPPL1234F1Z5",
            supply_split=SalesEcommerceSupply.SupplySplit.B2C,
            taxable_value=Decimal("500.00"),
            cgst_amount=Decimal("45.00"),
            sgst_amount=Decimal("45.00"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
        )

        response = self.client.get(self.export_url, {**self.base_params, "format": "gstn_json"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        table14 = payload["tables"]["14"]
        table15 = payload["tables"]["15"]

        self.assertEqual(len(table14), 1)
        self.assertEqual(table14[0]["supplier_eco_gstin"], "27SUPPL1234F1Z5")
        self.assertEqual(Decimal(str(table14[0]["taxable_value"])), Decimal("1500.00"))
        self.assertEqual(Decimal(str(table14[0]["cgst_amount"])), Decimal("135.00"))
        self.assertEqual(Decimal(str(table14[0]["sgst_amount"])), Decimal("135.00"))

        self.assertEqual(len(table15), 2)
        table15_by_split = {row["supply_split"]: row for row in table15}
        self.assertEqual(set(table15_by_split), {"B2B", "B2C"})
        self.assertEqual(Decimal(str(table15_by_split["B2B"]["taxable_value"])), Decimal("1000.00"))
        self.assertEqual(Decimal(str(table15_by_split["B2C"]["taxable_value"])), Decimal("500.00"))

    def test_gstn_json_export_preserves_eco_amendment_linkage_in_table_14a_15a(self):
        original = SalesEcommerceSupply.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            invoice_date="2025-04-12",
            invoice_number="ECO-ORIG-001",
            operator_gstin="27OPERA1234F1Z5",
            supplier_eco_gstin="27SUPPL1234F1Z5",
            supply_split=SalesEcommerceSupply.SupplySplit.B2B,
            taxable_value=Decimal("1000.00"),
            cgst_amount=Decimal("90.00"),
            sgst_amount=Decimal("90.00"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
        )
        amendment = SalesEcommerceSupply.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            invoice_date="2025-04-20",
            invoice_number="ECO-AMD-001",
            operator_gstin="27OPERA1234F1Z5",
            supplier_eco_gstin="27SUPPL1234F1Z5",
            supply_split=SalesEcommerceSupply.SupplySplit.B2C,
            taxable_value=Decimal("1200.00"),
            cgst_amount=Decimal("108.00"),
            sgst_amount=Decimal("108.00"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
            original_row=original,
            is_amendment=True,
        )

        response = self.client.get(self.export_url, {**self.base_params, "format": "gstn_json"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        table14a = payload["tables"]["14A"]
        table15a = payload["tables"]["15A"]

        self.assertEqual(len(table14a), 1)
        self.assertEqual(table14a[0]["id"], amendment.id)
        self.assertEqual(table14a[0]["original_row_id"], original.id)
        self.assertEqual(table14a[0]["supplier_eco_gstin"], "27SUPPL1234F1Z5")

        self.assertEqual(len(table15a), 1)
        self.assertEqual(table15a[0]["id"], amendment.id)
        self.assertEqual(table15a[0]["original_row_id"], original.id)
        self.assertEqual(table15a[0]["operator_gstin"], "27OPERA1234F1Z5")
        self.assertEqual(table15a[0]["supply_split"], SalesEcommerceSupply.SupplySplit.B2C)

    def test_table_6_includes_export_without_igst_and_sez_without_igst(self):
        export = self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="EXP-LUT-001",
            taxable="800.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
            grand_total="800.00",
            supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITHOUT_IGST,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            is_igst=True,
            place_of_supply="96",
        )
        sez = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="SEZ-WO-001",
            taxable="600.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
            grand_total="600.00",
            supply_category=SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            is_igst=True,
            place_of_supply="29",
        )

        response = self.client.get(self.table_url("TABLE_6"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["coverage"]["status"], "implemented")
        rows = {row["invoice_number"]: row for row in payload["rows"]}
        self.assertEqual(Decimal(str(rows["EXP-LUT-001"]["igst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(rows["SEZ-WO-001"]["igst_amount"])), Decimal("0.00"))
        self.assertEqual(rows["EXP-LUT-001"]["invoice_id"], export.id)
        self.assertEqual(rows["SEZ-WO-001"]["invoice_id"], sez.id)

    def test_table_6_includes_sez_with_igst(self):
        sez = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="SEZ-W-001",
            taxable="600.00",
            cgst="0.00",
            sgst="0.00",
            igst="108.00",
            grand_total="708.00",
            supply_category=SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            is_igst=True,
            place_of_supply="29",
        )

        response = self.client.get(self.table_url("TABLE_6"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = {row["invoice_number"]: row for row in payload["rows"]}
        self.assertEqual(Decimal(str(rows["SEZ-W-001"]["igst_amount"])), Decimal("108.00"))
        self.assertEqual(rows["SEZ-W-001"]["invoice_id"], sez.id)

    def test_table_4_excludes_sez_and_deemed_export_rows(self):
        b2b = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="B2B-ONLY-001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
        )
        sez = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="SEZ-EXCLUDE-001",
            taxable="600.00",
            cgst="0.00",
            sgst="0.00",
            igst="108.00",
            grand_total="708.00",
            supply_category=SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            is_igst=True,
            place_of_supply="29",
        )
        deemed = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="DEEMED-EXCLUDE-001",
            taxable="500.00",
            cgst="45.00",
            sgst="45.00",
            grand_total="590.00",
            supply_category=SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            is_igst=False,
            place_of_supply="27",
        )

        response = self.client.get(self.table_url("TABLE_4"), self.base_params)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        invoice_numbers = {row["invoice_number"] for row in payload["rows"]}
        self.assertIn(b2b.invoice_number, invoice_numbers)
        self.assertNotIn(sez.invoice_number, invoice_numbers)
        self.assertNotIn(deemed.invoice_number, invoice_numbers)

    def test_gstn_json_export_keeps_sez_and_deemed_export_rows_out_of_table_4(self):
        b2b = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="B2B-GSTN-001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
        )
        sez = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="SEZ-GSTN-001",
            taxable="600.00",
            cgst="0.00",
            sgst="0.00",
            igst="108.00",
            grand_total="708.00",
            supply_category=SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            is_igst=True,
            place_of_supply="29",
        )
        deemed = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="DEEMED-GSTN-001",
            taxable="500.00",
            cgst="45.00",
            sgst="45.00",
            grand_total="590.00",
            supply_category=SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            is_igst=False,
            place_of_supply="27",
        )

        response = self.client.get(self.export_url, {**self.base_params, "format": "gstn_json"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        table_4_numbers = {row["invoice_number"] for row in payload["tables"]["4"]}
        table_6_numbers = {row["invoice_number"] for row in payload["tables"]["6"]}
        self.assertIn(b2b.invoice_number, table_4_numbers)
        self.assertNotIn(sez.invoice_number, table_4_numbers)
        self.assertNotIn(deemed.invoice_number, table_4_numbers)
        self.assertIn(sez.invoice_number, table_6_numbers)
        self.assertIn(deemed.invoice_number, table_6_numbers)

    def test_table_8_includes_nil_rated_and_non_gst_buckets(self):
        nil_invoice = self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="NIL-001",
            taxable="250.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
            grand_total="250.00",
            taxability=SalesInvoiceHeader.Taxability.NIL_RATED,
        )
        SalesTaxSummary.objects.filter(header=nil_invoice).update(
            taxability=SalesInvoiceHeader.Taxability.NIL_RATED,
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00"),
            igst_amount=Decimal("0.00"),
        )
        non_gst_invoice = self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="NG-001",
            taxable="400.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
            grand_total="400.00",
            taxability=SalesInvoiceHeader.Taxability.NON_GST,
        )
        SalesTaxSummary.objects.filter(header=non_gst_invoice).update(
            taxability=SalesInvoiceHeader.Taxability.NON_GST,
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00"),
            igst_amount=Decimal("0.00"),
        )

        response = self.client.get(self.table_url("TABLE_8"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = {row["taxability"]: row for row in payload["rows"]}
        self.assertEqual(Decimal(str(rows[SalesInvoiceHeader.Taxability.NIL_RATED]["taxable_value"])), Decimal("250.00"))
        self.assertEqual(Decimal(str(rows[SalesInvoiceHeader.Taxability.NON_GST]["taxable_value"])), Decimal("400.00"))

    def test_table_4_gst_rate_excludes_cess(self):
        invoice = self._create_sales_document(
            customer=self.customer_alpha,
            taxable="363000.00",
            cgst="0.00",
            sgst="0.00",
            igst="65340.00",
            cess="2280.00",
            grand_total="430620.00",
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            is_igst=True,
            place_of_supply="29",
        )
        response = self.client.get(self.table_url("TABLE_4"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["coverage"]["status"], "implemented")
        row = next(r for r in payload["rows"] if r["invoice_id"] == invoice.id)
        self.assertEqual(Decimal(str(row["gst_rate"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(row["reported_cess_amount"])), Decimal("2280.00"))

    def test_table_4_splits_mixed_rate_invoice_into_multiple_rows(self):
        invoice = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="MIXED-001",
            taxable="20500.00",
            cgst="1812.50",
            sgst="1812.50",
            grand_total="24125.00",
            hsn_code="7203",
        )
        invoice.tax_summaries.all().delete()
        SalesTaxSummary.objects.bulk_create(
            [
                SalesTaxSummary(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    header=invoice,
                    taxability=SalesInvoiceHeader.Taxability.TAXABLE,
                    hsn_sac_code="7203",
                    is_service=False,
                    gst_rate=Decimal("18.00"),
                    taxable_value=Decimal("20000.00"),
                    cgst_amount=Decimal("1800.00"),
                    sgst_amount=Decimal("1800.00"),
                    igst_amount=Decimal("0.00"),
                    cess_amount=Decimal("0.00"),
                ),
                SalesTaxSummary(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    header=invoice,
                    taxability=SalesInvoiceHeader.Taxability.TAXABLE,
                    hsn_sac_code="7203",
                    is_service=True,
                    gst_rate=Decimal("5.00"),
                    taxable_value=Decimal("500.00"),
                    cgst_amount=Decimal("12.50"),
                    sgst_amount=Decimal("12.50"),
                    igst_amount=Decimal("0.00"),
                    cess_amount=Decimal("0.00"),
                ),
            ]
        )

        response = self.client.get(self.table_url("TABLE_4"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        invoice_rows = [r for r in payload["rows"] if r["invoice_id"] == invoice.id]
        self.assertEqual(len(invoice_rows), 2)
        self.assertEqual(
            sorted(Decimal(str(row["gst_rate"])) for row in invoice_rows),
            [Decimal("5.00"), Decimal("18.00")],
        )
        by_rate = {Decimal(str(row["gst_rate"])): row for row in invoice_rows}
        self.assertEqual(Decimal(str(by_rate[Decimal("5.00")]["taxable_amount"])), Decimal("500.00"))
        self.assertEqual(Decimal(str(by_rate[Decimal("18.00")]["taxable_amount"])), Decimal("20000.00"))
        self.assertTrue(all(Decimal(str(row["grand_total"])) == Decimal("24125.00") for row in invoice_rows))

    def _assert_mixed_rate_rows(
        self,
        *,
        table_code: str,
        rows: list[dict],
        key_name: str,
        key_value: int,
        taxable_field: str,
        grand_total_field: str,
        expected_grand_total: str,
        expected_taxable_by_rate: dict[Decimal, Decimal] | None = None,
    ) -> None:
        matching_rows = [row for row in rows if row[key_name] == key_value]
        self.assertEqual(len(matching_rows), 2)
        self.assertEqual(
            sorted(Decimal(str(row["gst_rate"])) for row in matching_rows),
            [Decimal("5.00"), Decimal("18.00")],
            msg=f"{table_code} should expose one row per GST bucket",
        )
        by_rate = {Decimal(str(row["gst_rate"])): row for row in matching_rows}
        expected_taxable_by_rate = expected_taxable_by_rate or {
            Decimal("5.00"): Decimal("500.00"),
            Decimal("18.00"): Decimal("20000.00"),
        }
        for rate, expected_taxable in expected_taxable_by_rate.items():
            self.assertEqual(Decimal(str(by_rate[rate][taxable_field])), expected_taxable)
        self.assertTrue(
            all(Decimal(str(row[grand_total_field])) == Decimal(expected_grand_total) for row in matching_rows)
        )

    def test_table_5_splits_mixed_rate_invoice_into_multiple_rows(self):
        invoice = self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="B2CL-MIXED-001",
            taxable="300500.00",
            cgst="0.00",
            sgst="0.00",
            igst="54025.00",
            grand_total="354525.00",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="29",
        )
        invoice.tax_summaries.all().delete()
        SalesTaxSummary.objects.bulk_create(
            [
                SalesTaxSummary(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    header=invoice,
                    taxability=SalesInvoiceHeader.Taxability.TAXABLE,
                    hsn_sac_code="7203",
                    is_service=False,
                    gst_rate=Decimal("18.00"),
                    taxable_value=Decimal("300000.00"),
                    cgst_amount=Decimal("0.00"),
                    sgst_amount=Decimal("0.00"),
                    igst_amount=Decimal("54000.00"),
                    cess_amount=Decimal("0.00"),
                ),
                SalesTaxSummary(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    header=invoice,
                    taxability=SalesInvoiceHeader.Taxability.TAXABLE,
                    hsn_sac_code="7203",
                    is_service=True,
                    gst_rate=Decimal("5.00"),
                    taxable_value=Decimal("500.00"),
                    cgst_amount=Decimal("0.00"),
                    sgst_amount=Decimal("0.00"),
                    igst_amount=Decimal("25.00"),
                    cess_amount=Decimal("0.00"),
                ),
            ]
        )

        response = self.client.get(self.table_url("TABLE_5"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self._assert_mixed_rate_rows(
            table_code="TABLE_5",
            rows=payload["rows"],
            key_name="invoice_id",
            key_value=invoice.id,
            taxable_field="taxable_amount",
            grand_total_field="grand_total",
            expected_grand_total="354525.00",
            expected_taxable_by_rate={
                Decimal("5.00"): Decimal("500.00"),
                Decimal("18.00"): Decimal("300000.00"),
            },
        )

    def test_table_6_splits_mixed_rate_invoice_into_multiple_rows(self):
        invoice = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="EXP-MIXED-001",
            taxable="20500.00",
            cgst="0.00",
            sgst="0.00",
            igst="3625.00",
            grand_total="24125.00",
            supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="96",
        )
        invoice.tax_summaries.all().delete()
        SalesTaxSummary.objects.bulk_create(
            [
                SalesTaxSummary(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    header=invoice,
                    taxability=SalesInvoiceHeader.Taxability.TAXABLE,
                    hsn_sac_code="7203",
                    is_service=False,
                    gst_rate=Decimal("18.00"),
                    taxable_value=Decimal("20000.00"),
                    cgst_amount=Decimal("0.00"),
                    sgst_amount=Decimal("0.00"),
                    igst_amount=Decimal("3600.00"),
                    cess_amount=Decimal("0.00"),
                ),
                SalesTaxSummary(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    header=invoice,
                    taxability=SalesInvoiceHeader.Taxability.TAXABLE,
                    hsn_sac_code="9983",
                    is_service=True,
                    gst_rate=Decimal("5.00"),
                    taxable_value=Decimal("500.00"),
                    cgst_amount=Decimal("0.00"),
                    sgst_amount=Decimal("0.00"),
                    igst_amount=Decimal("25.00"),
                    cess_amount=Decimal("0.00"),
                ),
            ]
        )

        response = self.client.get(self.table_url("TABLE_6"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self._assert_mixed_rate_rows(
            table_code="TABLE_6",
            rows=payload["rows"],
            key_name="invoice_id",
            key_value=invoice.id,
            taxable_field="taxable_amount",
            grand_total_field="grand_total",
            expected_grand_total="24125.00",
        )

    def test_table_9_splits_mixed_rate_note_into_multiple_rows(self):
        original = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="ORIG-MIXED-001",
            taxable="20500.00",
            cgst="1812.50",
            sgst="1812.50",
            grand_total="24125.00",
        )
        note = self._create_sales_document(
            customer=self.customer_alpha,
            invoice_number="NOTE-MIXED-001",
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=original,
            taxable="20500.00",
            cgst="1812.50",
            sgst="1812.50",
            grand_total="24125.00",
        )
        note.tax_summaries.all().delete()
        SalesTaxSummary.objects.bulk_create(
            [
                SalesTaxSummary(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    header=note,
                    taxability=SalesInvoiceHeader.Taxability.TAXABLE,
                    hsn_sac_code="7203",
                    is_service=False,
                    gst_rate=Decimal("18.00"),
                    taxable_value=Decimal("20000.00"),
                    cgst_amount=Decimal("1800.00"),
                    sgst_amount=Decimal("1800.00"),
                    igst_amount=Decimal("0.00"),
                    cess_amount=Decimal("0.00"),
                ),
                SalesTaxSummary(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    header=note,
                    taxability=SalesInvoiceHeader.Taxability.TAXABLE,
                    hsn_sac_code="9983",
                    is_service=True,
                    gst_rate=Decimal("5.00"),
                    taxable_value=Decimal("500.00"),
                    cgst_amount=Decimal("12.50"),
                    sgst_amount=Decimal("12.50"),
                    igst_amount=Decimal("0.00"),
                    cess_amount=Decimal("0.00"),
                ),
            ]
        )

        response = self.client.get(self.table_url("TABLE_9"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self._assert_mixed_rate_rows(
            table_code="TABLE_9",
            rows=payload["rows"],
            key_name="note_id",
            key_value=note.id,
            taxable_field="taxable_amount",
            grand_total_field="grand_total",
            expected_grand_total="-24125.00",
            expected_taxable_by_rate={
                Decimal("5.00"): Decimal("-500.00"),
                Decimal("18.00"): Decimal("-20000.00"),
            },
        )

    def test_table_10_splits_mixed_rate_note_into_multiple_rows(self):
        original = self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="ORIG-CDNUR-001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            customer_gstin="",
            place_of_supply="29",
            taxable="20500.00",
            cgst="0.00",
            sgst="0.00",
            igst="3625.00",
            grand_total="24125.00",
        )
        note = self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="CDNUR-MIXED-001",
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=original,
            customer_gstin="",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="29",
            taxable="20500.00",
            cgst="0.00",
            sgst="0.00",
            igst="3625.00",
            grand_total="24125.00",
        )
        note.tax_summaries.all().delete()
        SalesTaxSummary.objects.bulk_create(
            [
                SalesTaxSummary(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    header=note,
                    taxability=SalesInvoiceHeader.Taxability.TAXABLE,
                    hsn_sac_code="7203",
                    is_service=False,
                    gst_rate=Decimal("18.00"),
                    taxable_value=Decimal("20000.00"),
                    cgst_amount=Decimal("0.00"),
                    sgst_amount=Decimal("0.00"),
                    igst_amount=Decimal("3600.00"),
                    cess_amount=Decimal("0.00"),
                ),
                SalesTaxSummary(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    header=note,
                    taxability=SalesInvoiceHeader.Taxability.TAXABLE,
                    hsn_sac_code="9983",
                    is_service=True,
                    gst_rate=Decimal("5.00"),
                    taxable_value=Decimal("500.00"),
                    cgst_amount=Decimal("0.00"),
                    sgst_amount=Decimal("0.00"),
                    igst_amount=Decimal("25.00"),
                    cess_amount=Decimal("0.00"),
                ),
            ]
        )

        response = self.client.get(self.table_url("TABLE_10"), self.base_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self._assert_mixed_rate_rows(
            table_code="TABLE_10",
            rows=payload["rows"],
            key_name="note_id",
            key_value=note.id,
            taxable_field="taxable_amount",
            grand_total_field="grand_total",
            expected_grand_total="-24125.00",
            expected_taxable_by_rate={
                Decimal("5.00"): Decimal("-500.00"),
                Decimal("18.00"): Decimal("-20000.00"),
            },
        )

    def test_table_9_uses_gstin_format_rules_for_amendment_target_section(self):
        original = self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="ORIG-MALFORMED-GSTIN-001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            customer_gstin="BADGSTIN",
            place_of_supply="29",
            taxable="300000.00",
            cgst="0.00",
            sgst="0.00",
            igst="54000.00",
            grand_total="354000.00",
        )
        note = self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="NOTE-MALFORMED-GSTIN-001",
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=original,
            customer_gstin="BADGSTIN",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="29",
            taxable="300000.00",
            cgst="0.00",
            sgst="0.00",
            igst="54000.00",
            grand_total="354000.00",
        )

        response = self.client.get(self.table_url("TABLE_9"), self.base_params)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = next(r for r in payload["rows"] if r["note_id"] == note.id)
        self.assertEqual(row["amendment_target_section"], "B2CL")

    def test_gstn_json_export_keeps_malformed_gstin_amendments_out_of_b2b_targeting(self):
        original = self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="ORIG-GSTN-MALFORMED-001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            customer_gstin="BADGSTIN",
            place_of_supply="29",
            taxable="300000.00",
            cgst="0.00",
            sgst="0.00",
            igst="54000.00",
            grand_total="354000.00",
        )
        note = self._create_sales_document(
            customer=self.customer_beta,
            invoice_number="NOTE-GSTN-MALFORMED-001",
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=original,
            customer_gstin="BADGSTIN",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            place_of_supply="29",
            taxable="300000.00",
            cgst="0.00",
            sgst="0.00",
            igst="54000.00",
            grand_total="354000.00",
        )

        response = self.client.get(self.export_url, {**self.base_params, "format": "gstn_json"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = next(r for r in payload["tables"]["9"] if r["note_id"] == note.id)
        self.assertEqual(row["amendment_target_section"], "B2CL")

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

    @patch("reports.gstr1.views.summary.Gstr1SummaryAPIView.enforce_report_scope", side_effect=PermissionDenied("forbidden"))
    def test_summary_denies_when_scope_enforcement_fails(self, _enforce_scope):
        response = self.client.get(self.summary_url, self.base_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.gstr1.views.meta.Gstr1MetaAPIView.enforce_entity_scope", side_effect=PermissionDenied("forbidden"))
    def test_meta_denies_when_scope_enforcement_fails(self, _enforce_scope):
        response = self.client.get(
            self.meta_url,
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(response.status_code, 403)

    @patch("reports.gstr1.views.utils.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_summary_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(self.summary_url, self.base_params)
        self.assertEqual(response.status_code, 403)

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
