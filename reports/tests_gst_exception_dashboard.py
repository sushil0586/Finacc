from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from reports.tests_support.compliance_golden_dataset import build_compliance_golden_scope


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class GstExceptionDashboardAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="gst-ex-dashboard",
            email="gst-ex-dashboard@example.com",
            password="pass123",
        )
        self.permission_codes_patch = patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.gst_exception_dashboard.view"],
        )
        self.permission_codes_patch.start()
        self.addCleanup(self.permission_codes_patch.stop)
        self.client.force_authenticate(user=self.user)
        golden = build_compliance_golden_scope(user=self.user, entity_name="Dashboard Entity")
        self.entity = golden.entity
        self.subentity = golden.subentity
        self.entityfin = golden.entityfin
        self.summary_url = reverse("reports_api:gst-exception-dashboard-summary")
        self.export_url = reverse("reports_api:gst-exception-dashboard-export")
        self.params = golden.params
        self.scope = golden.scope
        self.gstr1_warnings = [
            {
                "code": "INVALID_GSTIN",
                "severity": "warning",
                "message": "Invalid GSTIN",
                "invoice_number": "INV-1",
                "drilldowns": {
                    "source_document": {
                        "route": "/saleinvoice",
                        "params": {"transactionid": 101},
                    },
                    "posting_lookup": {
                        "lookup": {
                            "document_type": "sales_invoice",
                            "document_id": 101,
                            "source_module": "sales",
                        }
                    },
                },
            },
            {"code": "DUPLICATE_INVOICE", "severity": "warning", "message": "Duplicate invoice", "invoice_number": "INV-2"},
        ]
        self.gstr3b_warnings = [
            {
                "code": "GSTR3B_TAX_BREAKUP_MISSING",
                "severity": "warning",
                "message": "Missing breakup",
                "drilldowns": {
                    "section_view": {"params": {"section": "3.1"}},
                },
            },
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
        reconciliation_builder.assert_called_once()
        self.assertFalse(reconciliation_builder.call_args.kwargs["include_contributors"])
        payload = response.json()
        self.assertEqual(payload["report_code"], "gst-exception-dashboard")
        self.assertEqual(payload["report_name"], "GST Exception Dashboard")
        self.assertEqual(set(payload["available_exports"]), {"excel", "csv", "json"})
        self.assertIn("excel", payload["actions"]["export_urls"])
        self.assertIn("csv", payload["actions"]["export_urls"])
        self.assertIn("json", payload["actions"]["export_urls"])
        self.assertEqual(payload["overview"]["total_exception_count"], 3)
        self.assertEqual(payload["overview"]["reconciliation_mismatch_count"], 0)
        self.assertEqual(payload["overview"]["reconciliation_advisory_count"], 1)
        self.assertTrue(any(row["category"] == "Master Data & Registration" for row in payload["gstr1_exception_rows"]))
        gstr1_row = next(row for row in payload["gstr1_exception_rows"] if row["code"] == "INVALID_GSTIN")
        self.assertEqual(gstr1_row["drilldowns"]["report"]["route"], "/gstreport")
        self.assertEqual(gstr1_row["drilldowns"]["source_document"]["params"]["transactionid"], 101)
        gstr3b_row = next(row for row in payload["gstr3b_exception_rows"] if row["code"] == "GSTR3B_TAX_BREAKUP_MISSING")
        self.assertEqual(gstr3b_row["drilldowns"]["report"]["route"], "/gstr3breport")
        self.assertEqual(gstr3b_row["drilldowns"]["report"]["params"]["section"], "3.1")
        self.assertEqual(gstr3b_row["drilldowns"]["report"]["params"]["entityfinid"], self.entityfin.id)
        self.assertEqual(gstr3b_row["drilldowns"]["report"]["params"]["from_date"], self.params["from_date"])
        self.assertEqual(gstr3b_row["drilldowns"]["report"]["params"]["to_date"], self.params["to_date"])
        self.assertIn("review_title", gstr3b_row)
        self.assertIn("review_steps", gstr3b_row)
        self.assertGreater(len(gstr3b_row["review_steps"]), 0)
        self.assertEqual(payload["reconciliation_rows"], [])
        self.assertTrue(any(item.get("code") == "INTERSTATE_DISCLOSURE" for item in payload["warnings"]))

    @patch("reports.api.gst_exception_dashboard_views.GstExceptionDashboardAPIView.enforce_scope")
    @patch("reports.api.gst_exception_dashboard_views.build_gstr1_vs_gstr3b_reconciliation")
    @patch("reports.api.gst_exception_dashboard_views.Gstr3bSummaryService.build")
    @patch("reports.api.gst_exception_dashboard_views.Gstr1ReportService.summary")
    @patch("reports.api.gst_exception_dashboard_views.Gstr3bSummaryService.validations")
    @patch("reports.api.gst_exception_dashboard_views.Gstr1ReportService.validations")
    @patch("reports.api.gst_exception_dashboard_views.Gstr3bSummaryService.build_scope")
    @patch("reports.api.gst_exception_dashboard_views.Gstr1ReportService.build_scope")
    def test_reconciliation_rows_include_actionable_review_guidance(
        self,
        build_scope_gstr1,
        build_scope_gstr3b,
        gstr1_validations,
        gstr3b_validations,
        gstr1_summary,
        gstr3b_build,
        reconciliation_builder,
        _enforce_scope,
    ):
        build_scope_gstr1.return_value = self.scope
        build_scope_gstr3b.return_value = self.scope
        gstr1_validations.return_value = []
        gstr3b_validations.return_value = []
        gstr1_summary.return_value = {"sections": [], "nil_exempt_summary": []}
        gstr3b_build.return_value = {}
        reconciliation_builder.return_value = {
            "rows": [
                {
                    "code": "OUTWARD_TAXABLE",
                    "label": "Outward Taxable Supplies",
                    "status": "mismatch",
                    "difference_taxable_value": "847.46",
                    "difference_total_tax": "152.54",
                    "gstr1_taxable_value": "23042.38",
                    "gstr3b_taxable_value": "22194.92",
                    "gstr1_total_tax": "4082.62",
                    "gstr3b_total_tax": "3930.08",
                    "note": "",
                },
            ],
            "warnings": [],
        }

        response = self.client.get(self.summary_url, self.params)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(reconciliation_builder.call_args.kwargs["include_contributors"])
        payload = response.json()
        self.assertEqual(payload["overview"]["reconciliation_mismatch_count"], 1)
        self.assertEqual(len(payload["reconciliation_rows"]), 1)
        row = payload["reconciliation_rows"][0]
        self.assertEqual(row["code"], "OUTWARD_TAXABLE")
        self.assertIn("review_title", row)
        self.assertTrue(row["review_title"])
        self.assertIn("review_steps", row)
        self.assertTrue(isinstance(row["review_steps"], list))
        self.assertGreater(len(row["review_steps"]), 0)

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
        self.assertFalse(reconciliation_builder.call_args.kwargs["include_contributors"])
        self.assertIn("overview", json_response.json())

        csv_response = self.client.get(self.export_url, {**self.params, "format": "csv"})
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response["Content-Type"], "text/csv")
        csv_text = csv_response.content.decode("utf-8")
        self.assertIn("GSTR-1", csv_text)
        self.assertIn("INVALID_GSTIN", csv_text)
        self.assertIn("GSTR3B_TAX_BREAKUP_MISSING", csv_text)

        xlsx_response = self.client.get(self.export_url, {**self.params, "format": "xlsx"})
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertIn("attachment; filename=\"GST_Exception_Dashboard.xlsx\"", xlsx_response["Content-Disposition"])

    @patch("reports.api.gst_exception_dashboard_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_summary_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(self.summary_url, self.params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.gst_exception_dashboard_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_export_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(self.export_url, {**self.params, "format": "csv"})
        self.assertEqual(response.status_code, 403)
