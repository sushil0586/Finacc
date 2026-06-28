from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase
from unittest.mock import patch

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
from purchase.models import PurchaseInvoiceHeader
from sales.models import SalesInvoiceHeader, SalesTaxSummary


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class Gstr9ScaffoldAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="gstr9-scaffold-user",
            email="gstr9-scaffold@example.com",
            password="pass123",
        )
        self.permission_codes_patch = patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.gstr9.view"],
        )
        self.permission_codes_patch.start()
        self.addCleanup(self.permission_codes_patch.stop)
        self.client.force_authenticate(user=self.user)

        self.summary_url = reverse("reports_api:gstr9-summary")
        self.table_url = lambda code: reverse("reports_api:gstr9-table", args=[code])
        self.validation_url = reverse("reports_api:gstr9-validations")
        self.export_url = reverse("reports_api:gstr9-export")
        self.freeze_url = reverse("reports_api:gstr9-freeze")
        self.freeze_history_url = reverse("reports_api:gstr9-freeze-history")
        self.filing_prepare_url = reverse("reports_api:gstr9-filing-prepare")
        self.filing_submit_url = reverse("reports_api:gstr9-filing-submit")
        self.filing_status_url = reverse("reports_api:gstr9-filing-status")

        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Finacc Entity",
            legalname="Finacc Entity Pvt Ltd",
            GstRegitrationType=gst_type,
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
        self.params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
        }

    def _create_sales_doc(
        self,
        *,
        doc_no: int,
        doc_type: int,
        supply_category: int,
        taxable: str,
        cgst: str,
        sgst: str,
        igst: str,
        original_invoice=None,
    ):
        return SalesInvoiceHeader.objects.create(
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
            place_of_supply_state_code="27",
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            supply_category=supply_category,
            original_invoice=original_invoice,
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

    def _create_purchase_doc(
        self,
        *,
        doc_no: int,
        doc_type: int,
        is_itc_eligible: bool,
        is_reverse_charge: bool,
        gstr2b_match_status: int = PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_CHECKED,
        taxable: str,
        cgst: str,
        sgst: str,
        igst: str,
    ):
        PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=doc_type,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date="2025-04-08",
            posting_date="2025-04-08",
            doc_code="PINV",
            doc_no=doc_no,
            purchase_number=f"P-{doc_no}",
            vendor_name="Vendor",
            supply_category=PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
            default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE,
            tax_regime=PurchaseInvoiceHeader.TaxRegime.INTRA if Decimal(igst) == 0 else PurchaseInvoiceHeader.TaxRegime.INTER,
            is_igst=Decimal(igst) > 0,
            is_reverse_charge=is_reverse_charge,
            is_itc_eligible=is_itc_eligible,
            gstr2b_match_status=gstr2b_match_status,
            total_taxable=Decimal(taxable),
            total_cgst=Decimal(cgst),
            total_sgst=Decimal(sgst),
            total_igst=Decimal(igst),
            total_cess=Decimal("0.00"),
            total_gst=Decimal(cgst) + Decimal(sgst) + Decimal(igst),
            grand_total=Decimal(taxable) + Decimal(cgst) + Decimal(sgst) + Decimal(igst),
        )

    def test_summary_contract(self):
        self._create_sales_doc(
            doc_no=1,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            igst="0.00",
        )
        response = self.client.get(self.summary_url, self.params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("summary", payload)
        self.assertIn("actions", payload)
        self.assertIn("available_exports", payload)
        self.assertEqual(set(payload["available_exports"]), {"excel", "csv", "json"})
        self.assertIn("export_urls", payload["actions"])
        self.assertIn("excel", payload["actions"]["export_urls"])
        self.assertIn("csv", payload["actions"]["export_urls"])
        self.assertIn("json", payload["actions"]["export_urls"])
        self.assertEqual(payload["summary"]["phase"], 1)
        self.assertEqual(payload["summary"]["status"], "phase1_complete")
        table_status = {row["code"]: row["status"] for row in payload["summary"]["tables"]}
        self.assertEqual(table_status["TABLE_5"], "implemented")
        self.assertEqual(table_status["TABLE_6"], "implemented")
        self.assertEqual(table_status["TABLE_7"], "implemented")
        self.assertEqual(table_status["TABLE_8"], "implemented")
        self.assertEqual(table_status["TABLE_10_14"], "implemented")
        self.assertEqual(table_status["TABLE_15_19"], "implemented")

    @patch("reports.gstr9.views.summary.Gstr9SummaryAPIView.enforce_report_scope", side_effect=PermissionDenied("forbidden"))
    def test_summary_denies_when_scope_enforcement_fails(self, _enforce_scope):
        response = self.client.get(self.summary_url, self.params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.gstr9.views.utils.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_summary_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(self.summary_url, self.params)
        self.assertEqual(response.status_code, 403)

    def test_table_4_contract_and_values(self):
        self._create_sales_doc(
            doc_no=1,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            igst="0.00",
        )
        self._create_sales_doc(
            doc_no=2,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
            taxable="50.00",
            cgst="0.00",
            sgst="0.00",
            igst="9.00",
        )
        self._create_sales_doc(
            doc_no=3,
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="10.00",
            cgst="0.90",
            sgst="0.90",
            igst="0.00",
        )

        response = self.client.get(self.table_url("TABLE_4"), self.params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["table_code"], "TABLE_4")
        self.assertEqual(payload["coverage"]["status"], "implemented")
        total_row = payload["rows"][-1]
        self.assertEqual(Decimal(str(total_row["taxable_value"])), Decimal("140.00"))
        self.assertEqual(Decimal(str(total_row["cgst"])), Decimal("8.10"))
        self.assertEqual(Decimal(str(total_row["sgst"])), Decimal("8.10"))
        self.assertEqual(Decimal(str(total_row["igst"])), Decimal("9.00"))
        self.assertEqual(Decimal(str(total_row["total_tax"])), Decimal("25.20"))

    def test_table_9_payable_aligns_with_table_4_total(self):
        self._create_sales_doc(
            doc_no=1,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            igst="0.00",
        )
        table4 = self.client.get(self.table_url("TABLE_4"), self.params).json()
        table9 = self.client.get(self.table_url("TABLE_9"), self.params).json()
        self.assertEqual(
            Decimal(str(table4["rows"][-1]["total_tax"])),
            Decimal(str(table9["rows"][0]["total_tax"])),
        )

    def test_table_5_values(self):
        self._create_sales_doc(
            doc_no=21,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            taxable="40.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
        )
        SalesInvoiceHeader.objects.filter(doc_no=21, entity=self.entity).update(
            taxability=SalesInvoiceHeader.Taxability.EXEMPT
        )
        self._create_sales_doc(
            doc_no=22,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITHOUT_IGST,
            taxable="60.00",
            cgst="0.00",
            sgst="0.00",
            igst="0.00",
        )

        table5 = self.client.get(self.table_url("TABLE_5"), self.params).json()
        self.assertEqual(table5["coverage"]["status"], "implemented")
        self.assertEqual(Decimal(str(table5["rows"][-1]["taxable_value"])), Decimal("100.00"))
        self.assertEqual(Decimal(str(table5["rows"][-1]["total_tax"])), Decimal("0.00"))

    def test_table_6_and_7_values(self):
        self._create_purchase_doc(
            doc_no=11,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            is_itc_eligible=True,
            is_reverse_charge=False,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED,
            taxable="80.00",
            cgst="7.20",
            sgst="7.20",
            igst="0.00",
        )
        self._create_purchase_doc(
            doc_no=12,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            is_itc_eligible=True,
            is_reverse_charge=True,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_IN_2B,
            taxable="20.00",
            cgst="0.00",
            sgst="0.00",
            igst="3.60",
        )
        self._create_purchase_doc(
            doc_no=13,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            is_itc_eligible=False,
            is_reverse_charge=False,
            taxable="50.00",
            cgst="4.50",
            sgst="4.50",
            igst="0.00",
        )

        table6 = self.client.get(self.table_url("TABLE_6"), self.params).json()
        self.assertEqual(table6["coverage"]["status"], "implemented")
        self.assertEqual(Decimal(str(table6["rows"][-1]["total_tax"])), Decimal("18.00"))

        table7 = self.client.get(self.table_url("TABLE_7"), self.params).json()
        self.assertEqual(table7["coverage"]["status"], "implemented")
        self.assertEqual(Decimal(str(table7["rows"][-1]["total_tax"])), Decimal("9.00"))

        table8 = self.client.get(self.table_url("TABLE_8"), self.params).json()
        self.assertEqual(table8["coverage"]["status"], "implemented")
        self.assertEqual(Decimal(str(table8["rows"][0]["total_tax"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(table8["rows"][1]["total_tax"])), Decimal("14.40"))
        self.assertEqual(Decimal(str(table8["rows"][2]["total_tax"])), Decimal("3.60"))

    def test_table_10_14_linked_and_unlinked_notes(self):
        original = self._create_sales_doc(
            doc_no=31,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            igst="0.00",
        )
        self._create_sales_doc(
            doc_no=32,
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="20.00",
            cgst="1.80",
            sgst="1.80",
            igst="0.00",
            original_invoice=original,
        )
        self._create_sales_doc(
            doc_no=33,
            doc_type=SalesInvoiceHeader.DocType.DEBIT_NOTE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="10.00",
            cgst="0.90",
            sgst="0.90",
            igst="0.00",
            original_invoice=original,
        )
        self._create_sales_doc(
            doc_no=34,
            doc_type=SalesInvoiceHeader.DocType.DEBIT_NOTE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="5.00",
            cgst="0.45",
            sgst="0.45",
            igst="0.00",
            original_invoice=None,
        )
        table = self.client.get(self.table_url("TABLE_10_14"), self.params).json()
        self.assertEqual(table["coverage"]["status"], "implemented")
        self.assertEqual(Decimal(str(table["rows"][0]["total_tax"])), Decimal("-3.60"))
        self.assertEqual(Decimal(str(table["rows"][1]["total_tax"])), Decimal("1.80"))
        self.assertEqual(Decimal(str(table["rows"][2]["total_tax"])), Decimal("-1.80"))
        self.assertEqual(Decimal(str(table["rows"][3]["total_tax"])), Decimal("0.90"))

    def test_table_15_19_values(self):
        goods = self._create_sales_doc(
            doc_no=41,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            igst="0.00",
        )
        service = self._create_sales_doc(
            doc_no=42,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="50.00",
            cgst="0.00",
            sgst="0.00",
            igst="9.00",
        )
        missing_hsn = self._create_sales_doc(
            doc_no=43,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="20.00",
            cgst="1.80",
            sgst="1.80",
            igst="0.00",
        )

        SalesTaxSummary.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=goods,
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            hsn_sac_code="1001",
            is_service=False,
            gst_rate=Decimal("18.00"),
            is_reverse_charge=False,
            taxable_value=Decimal("100.00"),
            cgst_amount=Decimal("9.00"),
            sgst_amount=Decimal("9.00"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
        )
        SalesTaxSummary.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=service,
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            hsn_sac_code="9983",
            is_service=True,
            gst_rate=Decimal("18.00"),
            is_reverse_charge=False,
            taxable_value=Decimal("50.00"),
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00"),
            igst_amount=Decimal("9.00"),
            cess_amount=Decimal("0.00"),
        )
        SalesTaxSummary.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=missing_hsn,
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            hsn_sac_code="",
            is_service=False,
            gst_rate=Decimal("18.00"),
            is_reverse_charge=False,
            taxable_value=Decimal("20.00"),
            cgst_amount=Decimal("1.80"),
            sgst_amount=Decimal("1.80"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
        )

        table = self.client.get(self.table_url("TABLE_15_19"), self.params).json()
        self.assertEqual(table["coverage"]["status"], "implemented")
        self.assertEqual(Decimal(str(table["rows"][2]["total_tax"])), Decimal("21.60"))
        self.assertEqual(Decimal(str(table["rows"][3]["total_tax"])), Decimal("9.00"))
        self.assertEqual(Decimal(str(table["rows"][6]["total_tax"])), Decimal("3.60"))

    @patch(
        "reports.gstr9.services.report.Gstr3bSummaryService.build",
        return_value={
            "section_4": {
                "itc_available": {"total_tax": Decimal("0.00")},
                "itc_reversed": {"total_tax": Decimal("0.00")},
            },
            "section_6_1": {
                "tax_paid_cash": {
                    "cgst": Decimal("0.00"),
                    "sgst": Decimal("0.00"),
                    "igst": Decimal("0.00"),
                    "cess": Decimal("0.00"),
                    "total_tax": Decimal("0.00"),
                },
                "tax_paid_itc": {
                    "cgst": Decimal("0.00"),
                    "sgst": Decimal("0.00"),
                    "igst": Decimal("0.00"),
                    "cess": Decimal("0.00"),
                    "total_tax": Decimal("0.00"),
                },
            },
        },
    )
    def test_validation_contract(self, _mock_gstr3b_build):
        self._create_purchase_doc(
            doc_no=11,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            is_itc_eligible=True,
            is_reverse_charge=False,
            gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED,
            taxable="80.00",
            cgst="7.20",
            sgst="7.20",
            igst="0.00",
        )
        response = self.client.get(self.validation_url, self.params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("warnings", payload)
        self.assertEqual(payload["warning_count"], len(payload["warnings"]))
        available_mismatch = next(
            warning
            for warning in payload["warnings"]
            if warning["code"] == "TABLE6_GSTR3B_ITC_AVAILABLE_MISMATCH"
        )
        self.assertEqual(available_mismatch["table_code"], "TABLE_6")
        self.assertEqual(
            available_mismatch["drilldowns"]["table_view"]["route"],
            "/gstr9report",
        )
        self.assertEqual(
            available_mismatch["drilldowns"]["table_view"]["params"]["table_code"],
            "TABLE_6",
        )
        self.assertEqual(
            available_mismatch["drilldowns"]["related_report"]["route"],
            "/gstr3breport",
        )
        self.assertEqual(
            available_mismatch["drilldowns"]["related_report"]["params"]["entityfinid"],
            self.entityfin.id,
        )

    def test_validation_contract_with_freeze_metadata(self):
        freeze = self.client.post(self.freeze_url, self.params, format="json")
        self.assertEqual(freeze.status_code, 201)
        freeze_version = freeze.json()["version"]

        response = self.client.get(self.validation_url, {**self.params, "freeze_version": freeze_version})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("freeze", payload)
        self.assertEqual(payload["freeze"]["version"], freeze_version)
        self.assertIn("warnings", payload)
        self.assertGreaterEqual(payload["warning_count"], 0)

    def test_export_contract(self):
        summary_response = self.client.get(self.summary_url, self.params)
        self.assertEqual(summary_response.status_code, 200)
        summary_payload = summary_response.json()
        self.assertIn("actions", summary_payload)
        self.assertIn("available_exports", summary_payload)
        self.assertEqual(set(summary_payload["available_exports"]), {"excel", "csv", "json"})
        self.assertIn("export_urls", summary_payload["actions"])
        self.assertIn("excel", summary_payload["actions"]["export_urls"])
        self.assertIn("csv", summary_payload["actions"]["export_urls"])
        self.assertIn("json", summary_payload["actions"]["export_urls"])

        response = self.client.get(self.export_url, {**self.params, "format": "json"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("summary", response.json())

        response = self.client.get(self.export_url, {**self.params, "format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])

        response = self.client.get(self.export_url, {**self.params, "format": "xlsx"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response["Content-Type"],
        )

    def test_freeze_contract(self):
        create_one = self.client.post(self.freeze_url, self.params, format="json")
        self.assertEqual(create_one.status_code, 201)
        payload_one = create_one.json()
        self.assertEqual(payload_one["report_code"], "gstr9")
        self.assertEqual(payload_one["version"], 1)
        self.assertEqual(payload_one["scope"]["entity"], self.entity.id)
        self.assertEqual(payload_one["scope"]["entityfinid"], self.entityfin.id)
        self.assertEqual(payload_one["frozen_by"], self.user.id)
        self.assertIn("summary", payload_one["payload"])
        self.assertIn("tables", payload_one["payload"])
        self.assertIn("validations", payload_one["payload"])

        create_two = self.client.post(self.freeze_url, self.params, format="json")
        self.assertEqual(create_two.status_code, 201)
        payload_two = create_two.json()
        self.assertEqual(payload_two["version"], 2)

        latest = self.client.get(self.freeze_url, self.params)
        self.assertEqual(latest.status_code, 200)
        latest_payload = latest.json()
        self.assertEqual(latest_payload["version"], 2)
        self.assertEqual(latest_payload["id"], payload_two["id"])

    def test_freeze_requires_entityfinid(self):
        response = self.client.post(
            self.freeze_url,
            {"entity": self.entity.id, "subentity": self.subentity.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "entityfinid is required.")

    def test_freeze_get_not_found_before_first_snapshot(self):
        response = self.client.get(self.freeze_url, self.params)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["status"], "not_found")

    def test_freeze_history_contract(self):
        self.client.post(self.freeze_url, self.params, format="json")
        self.client.post(self.freeze_url, self.params, format="json")
        self.client.post(self.freeze_url, self.params, format="json")

        response = self.client.get(self.freeze_history_url, self.params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["report_code"], "gstr9")
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["results"][0]["version"], 3)
        self.assertEqual(payload["results"][1]["version"], 2)
        self.assertEqual(payload["results"][2]["version"], 1)
        self.assertNotIn("payload", payload["results"][0])

        limited = self.client.get(self.freeze_history_url, {**self.params, "limit": 2})
        self.assertEqual(limited.status_code, 200)
        limited_payload = limited.json()
        self.assertEqual(limited_payload["count"], 2)
        self.assertEqual(limited_payload["results"][0]["version"], 3)
        self.assertEqual(limited_payload["results"][1]["version"], 2)
        self.assertNotIn("payload", limited_payload["results"][0])

        with_payload = self.client.get(self.freeze_history_url, {**self.params, "include_payload": 1})
        self.assertEqual(with_payload.status_code, 200)
        with_payload_json = with_payload.json()
        self.assertEqual(with_payload_json["count"], 3)
        self.assertIn("payload", with_payload_json["results"][0])
        self.assertIn("summary", with_payload_json["results"][0]["payload"])

    def test_freeze_history_limit_validation(self):
        response = self.client.get(self.freeze_history_url, {**self.params, "limit": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit must be an integer.")

        response = self.client.get(self.freeze_history_url, {**self.params, "limit": 0})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit must be a positive integer.")

        response = self.client.get(self.freeze_history_url, {**self.params, "include_payload": "maybe"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "include_payload must be a boolean.")

    def test_frozen_version_read_contract(self):
        self._create_sales_doc(
            doc_no=51,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            igst="0.00",
        )
        freeze = self.client.post(self.freeze_url, self.params, format="json")
        self.assertEqual(freeze.status_code, 201)
        self.assertEqual(freeze.json()["version"], 1)

        self._create_sales_doc(
            doc_no=52,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="50.00",
            cgst="4.50",
            sgst="4.50",
            igst="0.00",
        )

        live_table = self.client.get(self.table_url("TABLE_4"), self.params).json()
        self.assertEqual(Decimal(str(live_table["rows"][-1]["taxable_value"])), Decimal("150.00"))

        frozen_table_resp = self.client.get(self.table_url("TABLE_4"), {**self.params, "freeze_version": 1})
        self.assertEqual(frozen_table_resp.status_code, 200)
        frozen_table = frozen_table_resp.json()
        self.assertEqual(Decimal(str(frozen_table["rows"][-1]["taxable_value"])), Decimal("100.00"))
        self.assertEqual(frozen_table["freeze"]["version"], 1)

        frozen_summary_resp = self.client.get(self.summary_url, {**self.params, "freeze_version": 1})
        self.assertEqual(frozen_summary_resp.status_code, 200)
        self.assertEqual(frozen_summary_resp.json()["freeze"]["version"], 1)

        frozen_validation_resp = self.client.get(self.validation_url, {**self.params, "freeze_version": 1})
        self.assertEqual(frozen_validation_resp.status_code, 200)
        self.assertEqual(frozen_validation_resp.json()["freeze"]["version"], 1)

        frozen_export_resp = self.client.get(self.export_url, {**self.params, "format": "json", "freeze_version": 1})
        self.assertEqual(frozen_export_resp.status_code, 200)
        self.assertEqual(frozen_export_resp.json()["freeze"]["version"], 1)

    def test_frozen_version_not_found(self):
        response = self.client.get(self.summary_url, {**self.params, "freeze_version": 1})
        self.assertEqual(response.status_code, 404)
        self.assertIn("Frozen snapshot not found", response.json()["detail"])

    def test_frozen_version_validation(self):
        response = self.client.get(self.summary_url, {**self.params, "freeze_version": "abc"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "freeze_version must be an integer or 'latest'.")

        response = self.client.get(self.table_url("TABLE_4"), {**self.params, "freeze_version": 0})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "freeze_version must be a positive integer.")

    def test_filing_prepare_submit_status_flow(self):
        self._create_sales_doc(
            doc_no=61,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            igst="0.00",
        )
        freeze = self.client.post(self.freeze_url, self.params, format="json")
        self.assertEqual(freeze.status_code, 201)
        freeze_version = freeze.json()["version"]

        prepare = self.client.post(
            self.filing_prepare_url,
            {**self.params, "freeze_version": freeze_version},
            format="json",
        )
        self.assertEqual(prepare.status_code, 201)
        prepare_payload = prepare.json()
        self.assertEqual(prepare_payload["status"], "prepared")
        self.assertEqual(prepare_payload["freeze_version"], freeze_version)
        self.assertEqual(prepare_payload["prepared_by"], self.user.id)
        self.assertIn("can_submit", prepare_payload["payload"])
        filing_id = prepare_payload["id"]

        status_one = self.client.get(self.filing_status_url, {**self.params, "filing_id": filing_id})
        self.assertEqual(status_one.status_code, 200)
        self.assertEqual(status_one.json()["status"], "prepared")

        submit = self.client.post(
            self.filing_submit_url,
            {**self.params, "filing_id": filing_id},
            format="json",
        )
        self.assertEqual(submit.status_code, 200)
        submit_payload = submit.json()
        self.assertEqual(submit_payload["status"], "submitted")
        self.assertEqual(submit_payload["submitted_by"], self.user.id)
        self.assertEqual(submit_payload["portal_provider"], "simulated")
        self.assertTrue(str(submit_payload["portal_reference"]).startswith("GSTR9-SIM-"))
        self.assertEqual(submit_payload["payload"]["submission"]["provider"], "simulated")

        status_list = self.client.get(self.filing_status_url, self.params)
        self.assertEqual(status_list.status_code, 200)
        list_payload = status_list.json()
        self.assertEqual(list_payload["count"], 1)
        self.assertEqual(list_payload["results"][0]["id"], filing_id)
        self.assertEqual(list_payload["results"][0]["status"], "submitted")

    def test_filing_prepare_validation(self):
        response = self.client.post(self.filing_prepare_url, self.params, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "freeze_version is required.")

        response = self.client.post(self.filing_prepare_url, {**self.params, "freeze_version": "x"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "freeze_version must be an integer.")

        response = self.client.post(self.filing_prepare_url, {**self.params, "freeze_version": 1}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Frozen snapshot not found", response.json()["detail"])

    def test_filing_submit_and_status_validation(self):
        response = self.client.post(self.filing_submit_url, self.params, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "filing_id is required.")

        response = self.client.post(self.filing_submit_url, {**self.params, "filing_id": 999}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Filing run not found", response.json()["detail"])

        response = self.client.get(self.filing_status_url, {**self.params, "filing_id": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "filing_id must be an integer.")

        response = self.client.get(self.filing_status_url, {**self.params, "limit": 0})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit must be a positive integer.")

    @override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[], GSTR9_FILING_PROVIDER="manual")
    def test_filing_submit_manual_provider(self):
        self._create_sales_doc(
            doc_no=71,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            igst="0.00",
        )
        freeze = self.client.post(self.freeze_url, self.params, format="json")
        self.assertEqual(freeze.status_code, 201)

        prepare = self.client.post(
            self.filing_prepare_url,
            {**self.params, "freeze_version": freeze.json()["version"]},
            format="json",
        )
        self.assertEqual(prepare.status_code, 201)
        filing_id = prepare.json()["id"]

        missing_ref = self.client.post(
            self.filing_submit_url,
            {**self.params, "filing_id": filing_id},
            format="json",
        )
        self.assertEqual(missing_ref.status_code, 400)
        self.assertEqual(missing_ref.json()["detail"], "portal_reference is required for manual provider.")

        submit = self.client.post(
            self.filing_submit_url,
            {**self.params, "filing_id": filing_id, "portal_reference": "GSTP-REF-123", "ack_no": "ACK-MAN-1"},
            format="json",
        )
        self.assertEqual(submit.status_code, 200)
        payload = submit.json()
        self.assertEqual(payload["status"], "submitted")
        self.assertEqual(payload["portal_provider"], "manual")
        self.assertEqual(payload["portal_reference"], "GSTP-REF-123")
        self.assertEqual(payload["payload"]["submission"]["portal_payload"]["ack_no"], "ACK-MAN-1")
