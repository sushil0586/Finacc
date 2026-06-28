from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
from sales.models import SalesInvoiceHeader


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class SalesGstinAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="sales-gstin-user",
            email="sales-gstin@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("reports_api:sales-gstin")
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Sales GSTIN Entity",
            legalname="Sales GSTIN Entity Pvt Ltd",
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

        self._create_invoice(
            doc_no=1,
            customer_name="Alpha Retail",
            customer_gstin="27ABCDE1234F1Z5",
            taxable="1000.00",
            cgst="90.00",
            sgst="90.00",
            igst="0.00",
            grand_total="1180.00",
        )
        self._create_invoice(
            doc_no=2,
            customer_name="Alpha Retail",
            customer_gstin="27ABCDE1234F1Z5",
            taxable="500.00",
            cgst="45.00",
            sgst="45.00",
            igst="0.00",
            grand_total="590.00",
        )
        self._create_invoice(
            doc_no=3,
            customer_name="Beta Mart",
            customer_gstin="29BBBBB1234B1Z5",
            taxable="300.00",
            cgst="0.00",
            sgst="0.00",
            igst="54.00",
            supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
            grand_total="354.00",
        )

    def _create_invoice(
        self,
        *,
        doc_no,
        customer_name,
        customer_gstin,
        taxable,
        cgst,
        sgst,
        igst,
        grand_total,
        supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
    ):
        return SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2025-04-05",
            posting_date="2025-04-05",
            doc_code="SINV",
            doc_no=doc_no,
            invoice_number=f"S-{doc_no}",
            customer_name=customer_name,
            customer_gstin=customer_gstin,
            seller_gstin="27AAAAA9999A1Z5",
            seller_state_code="27",
            place_of_supply_state_code="27",
            supply_category=supply_category,
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            tax_regime=(
                SalesInvoiceHeader.TaxRegime.INTER_STATE if Decimal(igst) > 0 else SalesInvoiceHeader.TaxRegime.INTRA_STATE
            ),
            is_igst=Decimal(igst) > 0,
            total_taxable_value=Decimal(taxable),
            total_cgst=Decimal(cgst),
            total_sgst=Decimal(sgst),
            total_igst=Decimal(igst),
            total_cess=Decimal("0.00"),
            grand_total=Decimal(grand_total),
        )

    def test_summary_exposes_browser_contract_and_grouped_totals(self):
        response = self.client.get(self.url, self.params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["report_code"], "sales-gstin")
        self.assertEqual(payload["report_name"], "Sales GSTIN Report")
        self.assertEqual(payload["actions"]["can_drilldown"], False)
        self.assertFalse(payload["actions"]["can_export_excel"])
        self.assertFalse(payload["actions"]["can_export_pdf"])
        self.assertFalse(payload["actions"]["can_export_csv"])
        self.assertEqual(payload["available_exports"], [])
        self.assertEqual(payload["count"], 2)
        self.assertEqual(len(payload["results"]), 2)
        self.assertEqual(self._d(payload["summary"]["gstin_count"]), Decimal("2"))
        self.assertEqual(self._d(payload["summary"]["invoice_count"]), Decimal("3"))
        self.assertEqual(self._d(payload["summary"]["taxable_amount"]), Decimal("1800.00"))
        self.assertEqual(self._d(payload["summary"]["total_tax"]), Decimal("324.00"))
        self.assertEqual(payload["results"][0]["customer_gstin"], "27ABCDE1234F1Z5")
        self.assertEqual(self._d(payload["results"][0]["invoice_count"]), Decimal("2"))
        self.assertEqual(payload["results"][1]["customer_gstin"], "29BBBBB1234B1Z5")
        self.assertEqual(self._d(payload["results"][1]["grand_total"]), Decimal("354.00"))
        self.assertNotIn("page=", payload["filters"]["search"] if payload["filters"]["search"] else "")

    def test_summary_preserves_pagination_contract(self):
        response = self.client.get(self.url, {**self.params, "page_size": 1})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(len(payload["results"]), 1)
        self.assertIsNotNone(payload["next"])
        self.assertIsNone(payload["previous"])

    @staticmethod
    def _d(value):
        return Decimal(str(value))
