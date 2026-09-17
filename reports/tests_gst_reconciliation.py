from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from financial.models import Ledger, accountHead, accounttype
from posting.models import EntityStaticAccountMap, Entry, EntryStatus, JournalLine, PostingBatch, StaticAccount, TxnType
from posting.services.static_accounts import StaticAccountService
from reports.tests_support.compliance_golden_dataset import build_compliance_golden_scope
from reports.services.gst_reconciliation import _build_source_document_drilldown


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class GstReconciliationAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="gstr-recon-user",
            email="gstr-recon@example.com",
            password="pass123",
        )
        self.permission_codes_patch = patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=[
                "reports.gstr1_gstr3b_reconciliation.view",
                "reports.gstr1_gstr3b_reconciliation.export",
            ],
        )
        self.permission_codes_patch.start()
        self.addCleanup(self.permission_codes_patch.stop)
        self.client.force_authenticate(user=self.user)
        golden = build_compliance_golden_scope(user=self.user, entity_name="Recon Entity")
        self.entity = golden.entity
        self.subentity = golden.subentity
        self.entityfin = golden.entityfin
        self.summary_url = reverse("reports_api:gst-reconciliation-summary")
        self.export_url = reverse("reports_api:gst-reconciliation-export")
        self.params = golden.params
        self.scope = golden.scope
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
        self.assertEqual(payload["report_name"], "GSTR-1 vs GSTR-3B Reconciliation")
        self.assertEqual(set(payload["available_exports"]), {"excel", "csv", "json", "evidence_pack"})
        self.assertIn("excel", payload["actions"]["export_urls"])
        self.assertIn("csv", payload["actions"]["export_urls"])
        self.assertIn("json", payload["actions"]["export_urls"])
        self.assertIn("evidence_pack", payload["actions"]["export_urls"])
        self.assertTrue(payload["actions"]["can_export_evidence_pack"])
        self.assertEqual(payload["summary"]["mismatch_count"], 1)
        self.assertEqual(payload["summary"]["actionable_mismatch_count"], 0)
        self.assertEqual(payload["summary"]["advisory_mismatch_count"], 1)
        self.assertEqual(payload["filing_evidence_pack"]["pack_code"], "gstr1-vs-gstr3b-filing-evidence")
        self.assertEqual(payload["filing_evidence_pack"]["status"], "needs_review")
        self.assertEqual(len(payload["filing_evidence_pack"]["checklist"]), 4)
        self.assertEqual(payload["filing_evidence_pack"]["included_sections"][0]["code"], "comparison_grid")
        self.assertEqual(payload["rows"][0]["status"], "matched")
        self.assertEqual(payload["rows"][4]["status"], "mismatch")
        self.assertTrue(payload["rows"][4]["is_advisory"])
        self.assertEqual(payload["rows"][0]["drilldowns"]["gstr1_workspace"]["route"], "/gstreport")
        self.assertEqual(payload["rows"][0]["drilldowns"]["gstr3b_workspace"]["route"], "/gstr3breport")
        self.assertEqual(payload["rows"][0]["drilldowns"]["gstr1_workspace"]["params"]["entityfinid"], self.entityfin.id)
        self.assertEqual(payload["rows"][0]["drilldowns"]["gstr3b_workspace"]["params"]["entityfinid"], self.entityfin.id)
        self.assertEqual(payload["rows"][0]["drilldowns"]["gstr3b_workspace"]["params"]["from_date"], self.params["from_date"])
        self.assertEqual(payload["rows"][0]["drilldowns"]["gstr3b_workspace"]["params"]["to_date"], self.params["to_date"])

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
        csv_text = csv_response.content.decode("utf-8")
        self.assertIn("Outward Taxable Supplies", csv_text)

        xlsx_response = self.client.get(self.export_url, {**self.params, "format": "xlsx"})
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertIn("attachment; filename=\"GSTR1_vs_GSTR3B_Reconciliation.xlsx\"", xlsx_response["Content-Disposition"])

    @patch("reports.api.gst_reconciliation_views.Gstr1VsGstr3bReconciliationExportAPIView.enforce_scope")
    @patch("reports.api.gst_reconciliation_views.Gstr3bSummaryService.build")
    @patch("reports.api.gst_reconciliation_views.Gstr1ReportService.summary")
    @patch("reports.api.gst_reconciliation_views.Gstr3bSummaryService.build_scope")
    @patch("reports.api.gst_reconciliation_views.Gstr1ReportService.build_scope")
    def test_export_supports_filing_evidence_pack(self, build_scope_gstr1, build_scope_gstr3b, gstr1_summary, gstr3b_build, _enforce_scope):
        build_scope_gstr1.return_value = self.scope
        build_scope_gstr3b.return_value = self.scope
        gstr1_summary.return_value = self.gstr1_summary
        gstr3b_build.return_value = self.gstr3b_summary

        json_response = self.client.get(self.export_url, {**self.params, "format": "evidence_json"})
        self.assertEqual(json_response.status_code, 200)
        json_payload = json_response.json()
        self.assertEqual(json_payload["pack_code"], "gstr1-vs-gstr3b-filing-evidence")
        self.assertEqual(json_payload["status"], "needs_review")
        self.assertEqual(json_payload["included_sections"][1]["code"], "output_tax_ledger")

        csv_response = self.client.get(self.export_url, {**self.params, "format": "evidence_csv"})
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response["Content-Type"], "text/csv")
        self.assertIn("attachment; filename=\"GSTR1_vs_GSTR3B_Filing_Evidence.csv\"", csv_response["Content-Disposition"])
        csv_text = csv_response.content.decode("utf-8")
        self.assertIn("Evidence Pack", csv_text)
        self.assertIn("Output GST ledger tie-out", csv_text)

    @patch("reports.api.gst_reconciliation_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_summary_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(self.summary_url, self.params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.gst_reconciliation_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_export_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(self.export_url, {**self.params, "format": "csv"})
        self.assertEqual(response.status_code, 403)

    def test_view_only_user_has_no_export_actions_and_cannot_export_directly(self):
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.gstr1_gstr3b_reconciliation.view"],
        ):
            summary_response = self.client.get(self.summary_url, self.params)
            export_response = self.client.get(self.export_url, {**self.params, "format": "csv"})

        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.json()["available_exports"], [])
        self.assertEqual(summary_response.json()["actions"]["export_urls"], {})
        self.assertEqual(export_response.status_code, 403)

    @patch("reports.api.gst_reconciliation_views.Gstr1VsGstr3bReconciliationAPIView.enforce_scope")
    @patch("reports.api.gst_reconciliation_views.Gstr3bSummaryService.build")
    @patch("reports.api.gst_reconciliation_views.Gstr1ReportService.summary")
    @patch("reports.api.gst_reconciliation_views.Gstr3bSummaryService.build_scope")
    @patch("reports.api.gst_reconciliation_views.Gstr1ReportService.build_scope")
    def test_summary_includes_output_tax_ledger_reconciliation(
        self,
        build_scope_gstr1,
        build_scope_gstr3b,
        gstr1_summary,
        gstr3b_build,
        _enforce_scope,
    ):
        build_scope_gstr1.return_value = self.scope
        build_scope_gstr3b.return_value = self.scope
        gstr1_summary.return_value = self.gstr1_summary
        gstr3b_build.return_value = self.gstr3b_summary
        StaticAccountService.seed_static_account_master()
        liability_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Current Liabilities",
            accounttypecode="CL-GST",
            createdby=self.user,
        )
        liability_head = accountHead.objects.create(
            entity=self.entity,
            name="GST Output Payable",
            code=9300,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=liability_type,
            createdby=self.user,
        )
        cgst_ledger = Ledger.objects.create(entity=self.entity, ledger_code=9301, name="Output CGST", accounthead=liability_head, createdby=self.user)
        sgst_ledger = Ledger.objects.create(entity=self.entity, ledger_code=9302, name="Output SGST", accounthead=liability_head, createdby=self.user)
        for static_code, ledger in (("OUTPUT_CGST", cgst_ledger), ("OUTPUT_SGST", sgst_ledger)):
            EntityStaticAccountMap.objects.create(
                entity=self.entity,
                static_account=StaticAccount.objects.get(code=static_code),
                ledger=ledger,
                createdby=self.user,
            )
        StaticAccountService.invalidate(self.entity.id)
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=901,
            voucher_no="GST-LEDGER-1",
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=901,
            voucher_no="GST-LEDGER-1",
            posting_date=self.scope.from_date,
            status=EntryStatus.POSTED,
            posting_batch=batch,
            created_by=self.user,
        )
        for ledger, amount in ((cgst_ledger, "90.00"), (sgst_ledger, "90.00")):
            JournalLine.objects.create(
                entry=entry,
                posting_batch=batch,
                entity=self.entity,
                entityfin=self.entityfin,
                subentity=self.subentity,
                txn_type=TxnType.SALES,
                txn_id=901,
                voucher_no="GST-LEDGER-1",
                accounthead=liability_head,
                ledger=ledger,
                drcr=False,
                amount=Decimal(amount),
                posting_date=self.scope.from_date,
                created_by=self.user,
            )

        response = self.client.get(self.summary_url, self.params)

        self.assertEqual(response.status_code, 200)
        ledger_recon = response.json()["output_tax_ledger_reconciliation"]
        self.assertEqual(ledger_recon["summary"]["return_total_tax"], 234.0)
        self.assertEqual(ledger_recon["summary"]["ledger_total_tax"], 180.0)
        rows_by_code = {row["code"]: row for row in ledger_recon["rows"]}
        self.assertEqual(rows_by_code["OUTPUT_CGST"]["status"], "matched")
        self.assertEqual(rows_by_code["OUTPUT_SGST"]["status"], "matched")
        self.assertEqual(rows_by_code["OUTPUT_IGST"]["mapping_status"], "missing_mapping")
        self.assertEqual(rows_by_code["OUTPUT_CGST"]["drilldowns"]["ledger_book"]["route"], "/reports/financial/ledger-book")

    @patch("reports.services.gst_reconciliation.SalesInvoiceLine.objects.filter")
    def test_source_document_drilldown_uses_service_invoice_route_when_service_lines_exist(self, mocked_filter):
        mocked_filter.return_value.exists.return_value = True

        drilldown = _build_source_document_drilldown(invoice_id=404)

        self.assertEqual(drilldown["route"], "/saleserviceinvoice")
        self.assertEqual(drilldown["params"]["transactionid"], 404)

    def test_source_document_drilldown_uses_prefetched_service_flag_without_query(self):
        with patch("reports.services.gst_reconciliation.SalesInvoiceLine.objects.filter") as mocked_filter:
            drilldown = _build_source_document_drilldown(invoice_id=505, has_service_lines=False)

        mocked_filter.assert_not_called()
        self.assertEqual(drilldown["route"], "/saleinvoice")
        self.assertEqual(drilldown["params"]["transactionid"], 505)
