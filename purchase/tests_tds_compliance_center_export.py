from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from openpyxl import load_workbook
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from purchase.views.tds_compliance_center import PurchaseTdsComplianceCenterExportAPIView
from purchase.views.tds_compliance_center import PurchaseTdsComplianceCenterAPIView


MOCK_TDS_EXPORT_PAYLOAD = {
    "tabs": [
        {"id": "deduction-register", "label": "Deduction Register"},
        {"id": "return-filing", "label": "Return Filing"},
    ],
    "returnTabs": [
        {"id": "26q", "label": "26Q Resident Payments"},
        {"id": "27q", "label": "27Q Non-Resident Payments"},
    ],
    "headerChips": [
        {"label": "Arnika G"},
        {"label": "FY 2026-27"},
        {"label": "Q1 Apr-Jun"},
        {"label": "Head Office"},
    ],
    "filters": {
        "quarter": "Q1",
    },
    "meta": {
        "tdsSections": [
            {"id": 9, "section_code": "194C"},
        ],
    },
    "datasets": {
        "deduction-register": {
            "columns": [
                {"key": "date", "label": "Date", "type": "date"},
                {"key": "voucherNo", "label": "Voucher No", "type": "text"},
                {"key": "deductee", "label": "Deductee", "type": "text"},
                {"key": "tdsAmount", "label": "TDS Amount", "type": "currency", "align": "right"},
                {"key": "status", "label": "Status", "type": "status"},
                {"key": "actions", "label": "Actions", "type": "actions"},
            ],
            "rows": [
                {
                    "id": 1,
                    "date": "2026-06-24",
                    "voucherNo": "PI/2026/1226",
                    "deductee": "Vendor-A",
                    "tdsAmount": "50.00",
                    "status": {"label": "Pending Deposit", "tone": "warning"},
                },
                {
                    "id": 2,
                    "date": "2026-06-23",
                    "voucherNo": "PI/2026/1220",
                    "deductee": "Vendor-B",
                    "tdsAmount": "10.00",
                    "status": {"label": "Paid", "tone": "success"},
                },
            ],
        },
    },
    "returnDatasets": {
        "26q": {
            "columns": [
                {"key": "returnType", "label": "Return Type", "type": "text"},
                {"key": "quarter", "label": "Quarter", "type": "text"},
                {"key": "totalTds", "label": "Total TDS", "type": "currency", "align": "right"},
                {"key": "returnStatus", "label": "Status", "type": "status"},
            ],
            "rows": [
                {
                    "id": 1,
                    "returnType": "26Q Resident Payments",
                    "quarter": "Q1 Apr-Jun",
                    "totalTds": "5820.00",
                    "returnStatus": {"label": "Draft", "tone": "warning"},
                }
            ],
        },
        "27q": {
            "columns": [
                {"key": "returnType", "label": "Return Type", "type": "text"},
                {"key": "quarter", "label": "Quarter", "type": "text"},
                {"key": "totalTds", "label": "Total TDS", "type": "currency", "align": "right"},
                {"key": "returnStatus", "label": "Status", "type": "status"},
            ],
            "rows": [],
        },
    },
}


class PurchaseTdsComplianceCenterExportTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=1)

    @patch("purchase.views.tds_compliance_center.PurchaseTdsComplianceCenterAPIView.get")
    def test_xlsx_export_returns_workbook_for_selected_tab(self, mock_workspace_get):
        mock_workspace_get.return_value = Response(MOCK_TDS_EXPORT_PAYLOAD)
        request = self.factory.get(
            "/api/purchase/statutory/tds-compliance-center/export/",
            {
                "entity": 1,
                "entityfinid": 1,
                "tab": "deduction-register",
                "format": "xlsx",
                "columns": "date,voucherNo,tdsAmount,status",
            },
        )
        force_authenticate(request, user=self.user)

        response = PurchaseTdsComplianceCenterExportAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn('attachment; filename="tds_compliance_deduction-register_Q1.xlsx"', response["Content-Disposition"])

        workbook = load_workbook(filename=BytesIO(response.content), data_only=True)
        sheet = workbook.active
        self.assertEqual(sheet["A1"].value, "TDS Compliance Center - Deduction Register")
        self.assertEqual(sheet["A4"].value, "Date")
        self.assertEqual(sheet["B4"].value, "Voucher No")
        self.assertEqual(sheet["C4"].value, "TDS Amount")
        self.assertEqual(sheet["D4"].value, "Status")
        self.assertEqual(sheet["B5"].value, "PI/2026/1226")
        self.assertEqual(sheet["D5"].value, "Pending Deposit")

    @patch("purchase.views.tds_compliance_center.PurchaseTdsComplianceCenterAPIView.get")
    def test_pdf_export_uses_active_return_subtab(self, mock_workspace_get):
        mock_workspace_get.return_value = Response(MOCK_TDS_EXPORT_PAYLOAD)
        request = self.factory.get(
            "/api/purchase/statutory/tds-compliance-center/export/",
            {
                "entity": 1,
                "entityfinid": 1,
                "tab": "return-filing",
                "return_tab": "26q",
                "format": "pdf",
            },
        )
        force_authenticate(request, user=self.user)

        response = PurchaseTdsComplianceCenterExportAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn('attachment; filename="tds_compliance_return-filing-26q_Q1.pdf"', response["Content-Disposition"])


class PurchaseTdsComplianceCenterStatusTests(SimpleTestCase):
    def setUp(self):
        self.view = PurchaseTdsComplianceCenterAPIView()

    def test_draft_status_badges_respect_approval_state(self):
        challan = SimpleNamespace(status=1, payment_payload_json={"_approval_state": {"status": "SUBMITTED"}})
        filing = SimpleNamespace(status=1, filed_payload_json={"_approval_state": {"status": "APPROVED"}})

        self.assertEqual(self.view._challan_status_badge(challan)["label"], "Approval Submitted")
        self.assertEqual(self.view._return_status_badge(filing)["label"], "Approved Draft")

    def test_primary_actions_follow_purchase_statutory_workflow_states(self):
        challan = SimpleNamespace(status=2)
        submitted_return = SimpleNamespace(
            status=1,
            filed_payload_json={"_approval_state": {"status": "SUBMITTED"}},
            tax_type="IT_TDS",
            return_code="26Q",
        )
        filed_return = SimpleNamespace(
            status=2,
            filed_payload_json={},
            tax_type="IT_TDS",
            return_code="26Q",
        )

        self.assertEqual(self.view._challan_primary_action_label(challan), "Create return")
        self.assertEqual(self.view._return_primary_action_label(submitted_return), "Approve draft")
        self.assertEqual(self.view._return_primary_action_label(filed_return), "NSDL / 16A")
