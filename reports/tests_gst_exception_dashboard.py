from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class GstExceptionDashboardAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="gst-ex-dashboard",
            email="gst-ex-dashboard@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Dashboard Entity",
            legalname="Dashboard Entity Pvt Ltd",
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
        self.summary_url = reverse("reports_api:gst-exception-dashboard-summary")
        self.export_url = reverse("reports_api:gst-exception-dashboard-export")
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
        self.gstr1_warnings = [
            {"code": "INVALID_GSTIN", "severity": "warning", "message": "Invalid GSTIN", "invoice_number": "INV-1"},
            {"code": "DUPLICATE_INVOICE", "severity": "warning", "message": "Duplicate invoice", "invoice_number": "INV-2"},
        ]
        self.gstr3b_warnings = [
            {"code": "GSTR3B_TAX_BREAKUP_MISSING", "severity": "warning", "message": "Missing breakup"},
        ]
        self.reconciliation = {
            "rows": [
                {"code": "OUTWARD_TAXABLE", "label": "Outward Taxable Supplies", "status": "matched", "difference_taxable_value": "0.00", "difference_total_tax": "0.00", "note": ""},
                {"code": "INTERSTATE_DISCLOSURE", "label": "Inter-State Disclosure", "status": "mismatch", "difference_taxable_value": "10.00", "difference_total_tax": "1.80", "note": "Advisory mismatch"},
            ],
            "warnings": [{"code": "GST_RECON_SECTION32_ADVISORY", "severity": "info", "message": "Advisory mismatch"}],
        }

    @patch("reports.api.gst_exception_dashboard_views.GstExceptionDashboardAPIView.enforce_scope")
    @patch("reports.api.gst_exception_dashboard_views.build_gstr1_vs_gstr3b_reconciliation")
    @patch("reports.api.gst_exception_dashboard_views.Gstr3bSummaryService.build")
    @patch("reports.api.gst_exception_dashboard_views.Gstr1ReportService.summary")
    @patch("reports.api.gst_exception_dashboard_views.Gstr3bSummaryService.validations")
    @patch("reports.api.gst_exception_dashboard_views.Gstr1ReportService.validations")
    @patch("reports.api.gst_exception_dashboard_views.Gstr3bSummaryService.build_scope")
    @patch("reports.api.gst_exception_dashboard_views.Gstr1ReportService.build_scope")
    def test_summary_returns_overview(self, build_scope_gstr1, build_scope_gstr3b, gstr1_validations, gstr3b_validations, gstr1_summary, gstr3b_build, reconciliation_builder, _enforce_scope):
        build_scope_gstr1.return_value = self.scope
        build_scope_gstr3b.return_value = self.scope
        gstr1_validations.return_value = self.gstr1_warnings
        gstr3b_validations.return_value = self.gstr3b_warnings
        gstr1_summary.return_value = {"sections": [], "nil_exempt_summary": []}
        gstr3b_build.return_value = {}
        reconciliation_builder.return_value = self.reconciliation

        response = self.client.get(self.summary_url, self.params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["report_code"], "gst-exception-dashboard")
        self.assertEqual(payload["overview"]["total_exception_count"], 4)
        self.assertEqual(payload["overview"]["reconciliation_mismatch_count"], 1)
        self.assertTrue(any(row["category"] == "Master Data & Registration" for row in payload["gstr1_exception_rows"]))

    @patch("reports.api.gst_exception_dashboard_views.GstExceptionDashboardExportAPIView.enforce_scope")
    @patch("reports.api.gst_exception_dashboard_views.build_gstr1_vs_gstr3b_reconciliation")
    @patch("reports.api.gst_exception_dashboard_views.Gstr3bSummaryService.build")
    @patch("reports.api.gst_exception_dashboard_views.Gstr1ReportService.summary")
    @patch("reports.api.gst_exception_dashboard_views.Gstr3bSummaryService.validations")
    @patch("reports.api.gst_exception_dashboard_views.Gstr1ReportService.validations")
    @patch("reports.api.gst_exception_dashboard_views.Gstr3bSummaryService.build_scope")
    @patch("reports.api.gst_exception_dashboard_views.Gstr1ReportService.build_scope")
    def test_export_supports_csv_and_json(self, build_scope_gstr1, build_scope_gstr3b, gstr1_validations, gstr3b_validations, gstr1_summary, gstr3b_build, reconciliation_builder, _enforce_scope):
        build_scope_gstr1.return_value = self.scope
        build_scope_gstr3b.return_value = self.scope
        gstr1_validations.return_value = self.gstr1_warnings
        gstr3b_validations.return_value = self.gstr3b_warnings
        gstr1_summary.return_value = {"sections": [], "nil_exempt_summary": []}
        gstr3b_build.return_value = {}
        reconciliation_builder.return_value = self.reconciliation

        json_response = self.client.get(self.export_url, {**self.params, "format": "json"})
        self.assertEqual(json_response.status_code, 200)
        self.assertIn("overview", json_response.json())

        csv_response = self.client.get(self.export_url, {**self.params, "format": "csv"})
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response["Content-Type"], "text/csv")
