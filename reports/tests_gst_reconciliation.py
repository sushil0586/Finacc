from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class GstReconciliationAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="gstr-recon-user",
            email="gstr-recon@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Recon Entity",
            legalname="Recon Entity Pvt Ltd",
            GstRegitrationType=gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Head Office")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear="2025-04-01",
            finendyear="2026-03-31",
            createdby=self.user,
        )
        self.summary_url = reverse("reports_api:gst-reconciliation-summary")
        self.export_url = reverse("reports_api:gst-reconciliation-export")
        self.params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
            "from_date": "2025-04-01",
            "to_date": "2025-04-30",
        }
        self.scope = SimpleNamespace(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            month=4,
            year=2025,
            from_date="2025-04-01",
            to_date="2025-04-30",
        )
        self.gstr1_summary = {
            "sections": [
                {"section": "B2B", "taxable_amount": "1000.00", "cgst_amount": "90.00", "sgst_amount": "90.00", "igst_amount": "0.00", "cess_amount": "0.00"},
                {"section": "EXP", "taxable_amount": "300.00", "cgst_amount": "0.00", "sgst_amount": "0.00", "igst_amount": "54.00", "cess_amount": "0.00"},
            ],
            "nil_exempt_summary": [
                {"taxability": 4, "taxable_value": "50.00", "cgst_amount": "0.00", "sgst_amount": "0.00", "igst_amount": "0.00", "cess_amount": "0.00"},
            ],
        }
        self.gstr3b_summary = {
            "section_3_1": {
                "outward_taxable_supplies": {"taxable_value": "1000.00", "cgst": "90.00", "sgst": "90.00", "igst": "0.00", "cess": "0.00", "total_tax": "180.00"},
                "outward_zero_rated_supplies": {"taxable_value": "300.00", "cgst": "0.00", "sgst": "0.00", "igst": "54.00", "cess": "0.00", "total_tax": "54.00"},
                "outward_nil_exempt_non_gst": {"taxable_value": "50.00"},
                "non_gst_outward_supplies": {"taxable_value": "50.00"},
            },
            "section_3_2": {
                "interstate_supplies_to_unregistered": {"taxable_value": "10.00", "cgst": "0.00", "sgst": "0.00", "igst": "1.80", "cess": "0.00", "total_tax": "1.80"},
                "interstate_supplies_to_composition": {"taxable_value": "0.00", "cgst": "0.00", "sgst": "0.00", "igst": "0.00", "cess": "0.00", "total_tax": "0.00"},
                "interstate_supplies_to_uin_holders": {"taxable_value": "0.00", "cgst": "0.00", "sgst": "0.00", "igst": "0.00", "cess": "0.00", "total_tax": "0.00"},
            },
        }

    @patch("reports.api.gst_reconciliation_views.Gstr1VsGstr3bReconciliationAPIView.enforce_scope")
    @patch("reports.api.gst_reconciliation_views.Gstr3bSummaryService.build")
    @patch("reports.api.gst_reconciliation_views.Gstr1ReportService.summary")
    @patch("reports.api.gst_reconciliation_views.Gstr3bSummaryService.build_scope")
    @patch("reports.api.gst_reconciliation_views.Gstr1ReportService.build_scope")
    def test_summary_returns_reconciliation_payload(self, build_scope_gstr1, build_scope_gstr3b, gstr1_summary, gstr3b_build, _enforce_scope):
        build_scope_gstr1.return_value = self.scope
        build_scope_gstr3b.return_value = self.scope
        gstr1_summary.return_value = self.gstr1_summary
        gstr3b_build.return_value = self.gstr3b_summary

        response = self.client.get(self.summary_url, self.params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["report_code"], "gstr1-vs-gstr3b-reconciliation")
        self.assertEqual(payload["summary"]["mismatch_count"], 1)
        self.assertEqual(payload["rows"][0]["status"], "matched")
        self.assertEqual(payload["rows"][4]["status"], "mismatch")

    @patch("reports.api.gst_reconciliation_views.Gstr1VsGstr3bReconciliationExportAPIView.enforce_scope")
    @patch("reports.api.gst_reconciliation_views.Gstr3bSummaryService.build")
    @patch("reports.api.gst_reconciliation_views.Gstr1ReportService.summary")
    @patch("reports.api.gst_reconciliation_views.Gstr3bSummaryService.build_scope")
    @patch("reports.api.gst_reconciliation_views.Gstr1ReportService.build_scope")
    def test_export_supports_csv_and_json(self, build_scope_gstr1, build_scope_gstr3b, gstr1_summary, gstr3b_build, _enforce_scope):
        build_scope_gstr1.return_value = self.scope
        build_scope_gstr3b.return_value = self.scope
        gstr1_summary.return_value = self.gstr1_summary
        gstr3b_build.return_value = self.gstr3b_summary

        json_response = self.client.get(self.export_url, {**self.params, "format": "json"})
        self.assertEqual(json_response.status_code, 200)
        self.assertIn("rows", json_response.json())

        csv_response = self.client.get(self.export_url, {**self.params, "format": "csv"})
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response["Content-Type"], "text/csv")
        self.assertIn("attachment; filename=\"GSTR1_vs_GSTR3B_Reconciliation.csv\"", csv_response["Content-Disposition"])
