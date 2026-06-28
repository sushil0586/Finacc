from types import SimpleNamespace
from decimal import Decimal
from unittest.mock import MagicMock, patch
from datetime import date

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.exceptions import PermissionDenied, ValidationError

from sales.models import SalesInvoiceHeader, SalesSettings, SalesEWaySource
from sales.services.sales_invoice_service import SalesInvoiceService
from sales.services.sales_stock_balance_service import SalesStockBalanceService
from sales.services.sales_withholding_service import SalesWithholdingService
from sales.services.irp_payload_builder import IRPPayloadBuilder
from sales.services.compliance_error_catalog_service import ComplianceErrorCatalogService
from sales.services.eway_payload_builder import EWayInput, build_exp_ship_dtls, build_generate_eway_payload
from sales.services.eway.payload_b2c import build_b2c_direct_payload
from sales.services.sales_compliance_service import SalesComplianceService
from sales.services.sales_nav_service import SalesInvoiceNavService
from sales.services.sales_settings_service import SalesSettingsService
from sales.services.providers.mastergst import _extract_error
from sales.services.providers.mastergst_client import MasterGSTClient
from sales.services.providers.credential_resolver import CredentialResolver
from sales.models.mastergst_models import MasterGSTServiceScope
from sales.serializers.sales_compliance_serializers import (
    EnsureComplianceActionSerializer,
    ExtendEWayValidityActionSerializer,
    GenerateIRNAndEWayActionSerializer,
)
from sales.serializers.eway_serializers import GenerateEWayRequestSerializer
from withholding.services import WithholdingResult
from withholding.models import WithholdingBaseRule
from sales.views.sales_invoice_views import (
    SalesInvoiceCancelAPIView,
    SalesInvoiceConfirmAPIView,
    SalesInvoiceListCreateAPIView,
    SalesInvoicePostAPIView,
    SalesInvoicePrintAPIView,
    SalesInvoiceTransportAPIView,
    SalesInvoiceReverseAPIView,
    SalesInvoiceRetrieveUpdateAPIView,
)
from sales.views.sales_invoice_compliance_api import SalesInvoiceGenerateIRNAndEWayAPIView
from sales.views.sales_invoice_compliance_api import SalesInvoiceGenerateIRNAPIView
from sales.views.sales_invoice_compliance_api import SalesInvoiceGetIRNByDocDetailsAPIView
from sales.views.sales_invoice_compliance_api import SalesInvoiceGetGSTNDetailsAPIView
from sales.views.sales_invoice_compliance_api import SalesInvoiceSyncGSTINFromCPAPIView
from sales.views.sales_invoice_compliance_api import SalesInvoiceGetB2CQRCodeAPIView
from sales.views.sales_invoice_compliance_api import SalesInvoiceGetIRNDetailsAPIView
from sales.views.sales_invoice_compliance_api import SalesInvoiceGetEWayByIRNAPIView
from sales.views.eway_views import SalesInvoiceGetEWayDetailsAPIView
from sales.views.eway_views import (
    SalesInvoiceGetEWayTransporterDetailsAPIView,
    SalesInvoiceGetEWayGSTINDetailsAPIView,
    SalesInvoiceGetEWayHSNDetailsAPIView,
    SalesInvoiceGetEWayErrorListAPIView,
    SalesInvoiceRejectEWayAPIView,
    SalesInvoiceGetTripSheetAPIView,
    SalesInvoiceGetEWayByDocumentAPIView,
    SalesInvoiceGetEWayBillsForTransporterAPIView,
    SalesInvoiceGetEWayBillReportByTransporterAssignedDateAPIView,
    SalesInvoiceGetEWayBillsForTransporterByGSTINAPIView,
    SalesInvoiceGenerateConsolidatedEWayAPIView,
)
from sales.views.sales_ar_exports import CustomerStatementExcelAPIView
from posting.adapters.sales_invoice import SalesInvoicePostingAdapter, SalesInvoicePostingConfig
from posting.common.static_accounts import StaticAccountCodes


class SalesInvoiceServiceUnitTests(SimpleTestCase):
    def test_sanitize_header_data_inputs_removes_backend_controlled_totals(self):
        payload = {
            "bill_date": date(2026, 4, 1),
            "customer_id": 10,
            "round_off": Decimal("9.99"),
            "grand_total": Decimal("9999.99"),
            "total_taxable_value": Decimal("5000.00"),
            "total_other_charges": Decimal("10.00"),
            "status": SalesInvoiceHeader.Status.POSTED,
            "remarks": "keep me",
        }

        clean = SalesInvoiceService._sanitize_header_data_inputs(payload)

        self.assertEqual(clean["bill_date"], date(2026, 4, 1))
        self.assertEqual(clean["customer_id"], 10)
        self.assertEqual(clean["remarks"], "keep me")
        self.assertNotIn("round_off", clean)
        self.assertNotIn("grand_total", clean)
        self.assertNotIn("total_taxable_value", clean)
        self.assertNotIn("total_other_charges", clean)
        self.assertNotIn("status", clean)

    def test_sanitize_header_data_inputs_keeps_user_editable_fields(self):
        payload = {
            "doc_type": SalesInvoiceHeader.DocType.TAX_INVOICE,
            "bill_date": date(2026, 4, 2),
            "reference": "PO-123",
            "remarks": "ok",
            "withholding_enabled": True,
        }

        clean = SalesInvoiceService._sanitize_header_data_inputs(payload)

        self.assertEqual(clean, payload)

    def test_normalize_invoice_printing_applies_defaults(self):
        normalized = SalesSettingsService.normalize_invoice_printing(
            {
                "default_profile": "plain",
                "default_copies": ["original", "duplicate"],
                "profiles": [
                    {
                        "key": "plain",
                        "label": "Plain",
                        "options": {
                            "show_bank_details": False,
                            "show_terms": False,
                            "show_einvoice_section": True,
                        },
                    }
                ],
                "copy_labels": {
                    "original": "ORIGINAL",
                    "duplicate": "DUPLICATE",
                    "triplicate": "TRIPLICATE",
                },
            }
        )

        self.assertEqual(normalized["default_profile"], "plain")
        self.assertEqual(normalized["default_copies"], ["original", "duplicate"])
        self.assertEqual(len(normalized["profiles"]), 1)
        self.assertEqual(normalized["profiles"][0]["key"], "plain")
        self.assertFalse(normalized["profiles"][0]["options"]["show_bank_details"])
        self.assertIn("pdf_render_scale", normalized["profiles"][0]["options"])
        self.assertIn("pdf_image_quality", normalized["profiles"][0]["options"])
        self.assertIn("show_eway_details", normalized["profiles"][0]["options"])
        self.assertIn("show_transport_details", normalized["profiles"][0]["options"])
        self.assertIn("show_compliance_qr", normalized["profiles"][0]["options"])
        self.assertIn("show_gst_validation_panel", normalized["profiles"][0]["options"])
        self.assertIn("gst_validation_checks", normalized["profiles"][0]["options"])
        self.assertEqual(normalized["copy_labels"]["original"], "ORIGINAL")
        self.assertIn("texts", normalized)
        self.assertTrue(len(normalized["texts"]["line_columns"]) > 0)


class MasterGSTClientUnitTests(SimpleTestCase):
    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_gstn_details_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"Gstin":"03ABCDE1234F1Z5"}}'
        response.json.return_value = {"status_cd": "1", "data": {"Gstin": "03ABCDE1234F1Z5"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "get_token", return_value="tok123"), patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_gstn_details(gstin="03abcde1234f1z5")

        self.assertEqual(result["status_cd"], "1")
        self.assertEqual(result["_lookup_gstin"], "03ABCDE1234F1Z5")
        mocked_get.assert_called_once()
        called_url = mocked_get.call_args.args[0]
        called_headers = mocked_get.call_args.kwargs["headers"]
        self.assertIn("/einvoice/type/GSTNDETAILS/version/V1_03", called_url)
        self.assertIn("param1=03ABCDE1234F1Z5", called_url)
        self.assertEqual(called_headers["auth-token"], "tok123")
        self.assertEqual(called_headers["username"], "gst-user")

    def test_eway_direct_headers_use_explicit_credential_helpers(self):
        cred = SimpleNamespace(
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="10.10.10.10"):
            headers = client._eway_direct_headers()

        self.assertEqual(headers["username"], "eway-user")
        self.assertEqual(headers["password"], "eway-pass")
        self.assertEqual(headers["ip_address"], "10.10.10.10")

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_irn_details_by_doc_uses_vendor_header_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"Irn":"IRN123"}}'
        response.json.return_value = {"status_cd": "1", "data": {"Irn": "IRN123"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "get_token", return_value="tok123"), patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_irn_details_by_doc(doc_type="inv", doc_number="SINV/1", doc_date="18/06/2026")

        self.assertEqual(result["status_cd"], "1")
        mocked_get.assert_called_once()
        called_url = mocked_get.call_args.args[0]
        called_headers = mocked_get.call_args.kwargs["headers"]
        self.assertIn("/einvoice/type/GETIRNBYDOCDETAILS/version/V1_03", called_url)
        self.assertIn("param1=INV", called_url)
        self.assertEqual(called_headers["docnum"], "SINV/1")
        self.assertEqual(called_headers["docdate"], "18/06/2026")
        self.assertEqual(called_headers["auth-token"], "tok123")

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_sync_gstin_from_cp_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"Gstin":"03ABCDE1234F1Z5"}}'
        response.json.return_value = {"status_cd": "1", "data": {"Gstin": "03ABCDE1234F1Z5"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "get_token", return_value="tok123"), patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.sync_gstin_from_cp(gstin="03abcde1234f1z5")

        self.assertEqual(result["status_cd"], "1")
        mocked_get.assert_called_once()
        called_url = mocked_get.call_args.args[0]
        called_headers = mocked_get.call_args.kwargs["headers"]
        self.assertIn("/einvoice/type/SYNC_GSTIN_FROMCP/version/V1_03", called_url)
        self.assertIn("param1=03ABCDE1234F1Z5", called_url)
        self.assertEqual(called_headers["auth-token"], "tok123")

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_b2c_qrcode_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"qrCode":"base64-qr"}}'
        response.json.return_value = {"status_cd": "1", "data": {"qrCode": "base64-qr"}}
        response.text = '{"status_cd":"1","data":{"qrCode":"base64-qr"}}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_b2c_qrcode(
                payload={
                    "sgstin": "03AAAAA0000A1Z5",
                    "docno": "SINV-1001",
                    "docdate": "18-06-2026",
                    "totinvval": "1180.00",
                    "bankaccno": "1234567890",
                    "bankifsccode": "HDFC0001234",
                    "accountholdername": "Acme Pvt Ltd",
                    "igstamount": "0.00",
                    "cgstamount": "90.00",
                    "sgstamount": "90.00",
                    "cessamount": "0.00",
                }
            )

        self.assertEqual(result["status_cd"], "1")
        mocked_get.assert_called_once()
        called_url = mocked_get.call_args.args[0]
        called_headers = mocked_get.call_args.kwargs["headers"]
        self.assertIn("/einvoice/qrcode", called_url)
        self.assertEqual(called_headers["docno"], "SINV-1001")
        self.assertEqual(called_headers["bankifsccode"], "HDFC0001234")
        self.assertEqual(called_headers["username"], "gst-user")

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_eway_details_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"ewayBillNo":"171001234567","validUpto":"2026-06-19"}}'
        response.json.return_value = {"status_cd": "1", "data": {"ewayBillNo": "171001234567", "validUpto": "2026-06-19"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_eway_details(ewb_no="171001234567")

        self.assertEqual(result["status_cd"], "1")
        mocked_get.assert_called_once()
        called_url = mocked_get.call_args.args[0]
        called_headers = mocked_get.call_args.kwargs["headers"]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/getewaybill", called_url)
        self.assertIn("ewbNo=171001234567", called_url)
        self.assertEqual(called_headers["username"], "eway-user")

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_transporter_details_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"transporterId":"03TRANS1234A1Z5"}}'
        response.json.return_value = {"status_cd": "1", "data": {"transporterId": "03TRANS1234A1Z5"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_transporter_details(transporter_id="03TRANS1234A1Z5")

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_get.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/gettransporterdetails", called_url)
        self.assertIn("trn_no=03TRANS1234A1Z5", called_url)

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_gstin_details_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"Gstin":"03ABCDE1234F1Z5"}}'
        response.json.return_value = {"status_cd": "1", "data": {"Gstin": "03ABCDE1234F1Z5"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_gstin_details(gstin="03abcde1234f1z5")

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_get.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/getgstindetails", called_url)
        self.assertIn("GSTIN=03ABCDE1234F1Z5", called_url)

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_hsn_details_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"hsnCode":"9983"}}'
        response.json.return_value = {"status_cd": "1", "data": {"hsnCode": "9983"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_hsn_details(hsn_code="9983")

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_get.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/gethsndetailsbyhsncode", called_url)
        self.assertIn("hsncode=9983", called_url)

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_error_list_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":[{"code":"1001"}]}'
        response.json.return_value = {"status_cd": "1", "data": [{"code": "1001"}]}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_error_list()

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_get.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/geterrorlist", called_url)

    @patch("sales.services.providers.mastergst_client.requests.post")
    def test_reject_eway_uses_active_provider_endpoint_contract(self, mocked_post):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":"Rejected"}'
        response.json.return_value = {"status_cd": "1", "data": "Rejected"}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_post.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.reject_eway({"ewbNo": 171001234567})

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_post.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/rejewb", called_url)

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_trip_sheet_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"tripSheetNo":"TS123"}}'
        response.json.return_value = {"status_cd": "1", "data": {"tripSheetNo": "TS123"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_trip_sheet(trip_sheet_no="TS123")

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_get.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/gettripsheet", called_url)
        self.assertIn("tripSheetNo=TS123", called_url)

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_eway_by_document_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"ewayBillNo":"171001234567"}}'
        response.json.return_value = {"status_cd": "1", "data": {"ewayBillNo": "171001234567"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_eway_by_document(doc_type="INV", doc_no="SINV-1")

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_get.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/getewaybillgeneratedbyconsigner", called_url)
        self.assertIn("docType=INV", called_url)
        self.assertIn("docNo=SINV-1", called_url)

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_eway_bills_for_transporter_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":[{"ewayBillNo":"171001234567"}]}'
        response.json.return_value = {"status_cd": "1", "data": [{"ewayBillNo": "171001234567"}]}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_eway_bills_for_transporter(date="18/06/2026")

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_get.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/getewaybillsfortransporter", called_url)
        self.assertIn("date=18/06/2026", called_url)

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_eway_bill_report_by_transporter_assigned_date_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":[{"ewayBillNo":"171001234567"}]}'
        response.json.return_value = {"status_cd": "1", "data": [{"ewayBillNo": "171001234567"}]}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_eway_bill_report_by_transporter_assigned_date(date="18/06/2026", state_code="03")

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_get.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/getewaybillreportbytransporterassigneddate", called_url)
        self.assertIn("date=18/06/2026", called_url)
        self.assertIn("stateCode=03", called_url)

    @patch("sales.services.providers.mastergst_client.requests.get")
    def test_get_eway_bills_for_transporter_by_gstin_uses_active_provider_endpoint_contract(self, mocked_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":[{"ewayBillNo":"171001234567"}]}'
        response.json.return_value = {"status_cd": "1", "data": [{"ewayBillNo": "171001234567"}]}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_get.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.get_eway_bills_for_transporter_by_gstin(gen_gstin="03AAAAA0000A1Z5", date="18/06/2026")

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_get.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/getewaybillsfortransporterbygstin", called_url)
        self.assertIn("Gen_gstin=03AAAAA0000A1Z5", called_url)
        self.assertIn("date=18/06/2026", called_url)

    @patch("sales.services.providers.mastergst_client.requests.post")
    def test_generate_consolidated_eway_uses_active_provider_endpoint_contract(self, mocked_post):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"tripSheetNo":"TS123"}}'
        response.json.return_value = {"status_cd": "1", "data": {"tripSheetNo": "TS123"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_post.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.generate_consolidated_eway(
                {
                    "fromPlace": "Sirhind",
                    "fromState": 3,
                    "transMode": "1",
                    "tripSheetEwbBills": [{"ewbNo": 171001234567}],
                    "vehicleNo": "PB10AB1234",
                    "transDocNo": "LR1",
                    "transDocDate": "18/06/2026",
                }
            )

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_post.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/gencewb", called_url)

    @patch("sales.services.providers.mastergst_client.requests.post")
    def test_regenerate_trip_sheet_uses_active_provider_endpoint_contract(self, mocked_post):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"tripSheetNo":"TS123"}}'
        response.json.return_value = {"status_cd": "1", "data": {"tripSheetNo": "TS123"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_post.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.regenerate_trip_sheet(
                {
                    "fromPlace": "Sirhind",
                    "fromState": 3,
                    "reasonCode": "1",
                    "reasonRem": "Route change",
                    "transMode": "1",
                    "tripSheetNo": 123,
                    "vehicleNo": "PB10AB1234",
                    "transDocNo": "LR1",
                    "transDocDate": "18/06/2026",
                }
            )

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_post.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/regentripsheet", called_url)

    @patch("sales.services.providers.mastergst_client.requests.post")
    def test_initiate_multi_vehicle_uses_active_provider_endpoint_contract(self, mocked_post):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"groupNo":"10"}}'
        response.json.return_value = {"status_cd": "1", "data": {"groupNo": "10"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_post.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.initiate_multi_vehicle(
                {
                    "ewbNo": "171001234567",
                    "fromPlace": "Sirhind",
                    "fromState": 3,
                    "toPlace": "Patiala",
                    "toState": 3,
                    "reasonCode": "1",
                    "reasonRem": "Shift",
                    "transMode": "1",
                    "totalQuantity": 10,
                    "unitCode": "BOX",
                }
            )

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_post.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/initmulti", called_url)

    @patch("sales.services.providers.mastergst_client.requests.post")
    def test_add_multi_vehicle_uses_active_provider_endpoint_contract(self, mocked_post):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"groupNo":"10"}}'
        response.json.return_value = {"status_cd": "1", "data": {"groupNo": "10"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_post.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.add_multi_vehicle(
                {
                    "ewbNo": "171001234567",
                    "groupNo": 10,
                    "vehicleNo": "PB10AB1234",
                    "transDocNo": "LR1",
                    "transDocDate": "18/06/2026",
                    "quantity": 5,
                }
            )

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_post.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/addmulti", called_url)

    @patch("sales.services.providers.mastergst_client.requests.post")
    def test_update_multi_vehicle_uses_active_provider_endpoint_contract(self, mocked_post):
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status_cd":"1","data":{"groupNo":"10"}}'
        response.json.return_value = {"status_cd": "1", "data": {"groupNo": "10"}}
        response.text = '{"status_cd":"1"}'
        response.headers = {"Content-Type": "application/json"}
        mocked_post.return_value = response

        cred = SimpleNamespace(
            email="ops@example.com",
            client_id="cid",
            gstin="03AAAAA0000A1Z5",
            gst_username="gst-user",
            get_client_secret=lambda: "secret",
            get_eway_username=lambda: "eway-user",
            get_eway_password=lambda: "eway-pass",
        )
        client = MasterGSTClient(cred=cred, provider_name="whitebooks")

        with patch.object(client, "_resolve_ip", return_value="127.0.0.1"):
            result = client.update_multi_vehicle(
                {
                    "ewbNo": "171001234567",
                    "groupNo": 10,
                    "oldvehicleNo": "PB10AB1234",
                    "newVehicleNo": "PB10AB9999",
                    "oldTranNo": "LR1",
                    "newTranNo": "LR2",
                    "fromPlace": "Sirhind",
                    "fromState": 3,
                    "reasonCode": "1",
                    "reasonRem": "Replacement",
                }
            )

        self.assertEqual(result["status_cd"], "1")
        called_url = mocked_post.call_args.args[0]
        self.assertIn("/ewaybillapi/v1.03/ewayapi/updtmulti", called_url)

    @patch("sales.services.sales_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tcs_skips_when_entity_config_disables_tcs(self, mocked_get_cfg):
        mocked_get_cfg.return_value = SimpleNamespace(enable_tcs=False, apply_tcs_206c1h=False)
        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tcs_section=SimpleNamespace(section_code="206C(1)", rate_default=Decimal("0.1000")),
        )

        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=10,
            invoice_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )
        self.assertFalse(res.enabled)
        self.assertEqual(res.amount, Decimal("0.00"))
        self.assertEqual(res.reason_code, "DISABLED")

    @patch("sales.services.sales_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tcs_disables_206c1h_by_config(self, mocked_get_cfg):
        mocked_get_cfg.return_value = SimpleNamespace(enable_tcs=True, apply_tcs_206c1h=False)
        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tcs_section=SimpleNamespace(section_code="206C(1H)", rate_default=Decimal("0.1000")),
        )

        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=10,
            invoice_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )
        self.assertTrue(res.enabled)
        self.assertEqual(res.amount, Decimal("0.00"))
        self.assertEqual(res.reason_code, "DISABLED_206C_1H_BY_CONFIG")

    @patch("sales.services.sales_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tcs_skips_payment_based_section_in_invoice_context(self, mocked_get_cfg):
        mocked_get_cfg.return_value = SimpleNamespace(enable_tcs=True, apply_tcs_206c1h=True)
        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tcs_section=SimpleNamespace(section_code="194N", base_rule=4, rate_default=Decimal("2.0000")),
        )

        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=10,
            invoice_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )

        self.assertTrue(res.enabled)
        self.assertEqual(res.amount, Decimal("0.00"))
        self.assertEqual(res.reason_code, "NOT_APPLICABLE_BASE_RULE_CONTEXT")

    @patch("sales.services.sales_withholding_service._apply_section_threshold")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.resolve_rate")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.resolve_party_profile")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tcs_applies_when_206c1h_threshold_crosses_in_current_invoice(
        self,
        mocked_get_cfg,
        mocked_resolve_party_profile,
        mocked_resolve_rate,
        mocked_apply_threshold,
    ):
        mocked_get_cfg.return_value = SimpleNamespace(enable_tcs=True, apply_tcs_206c1h=True)
        mocked_resolve_party_profile.return_value = None
        mocked_resolve_rate.return_value = SimpleNamespace(
            rate=Decimal("0.1000"),
            reason=None,
            reason_code=None,
            no_pan_applied=False,
            sec_206ab_applied=False,
            lower_rate_applied=False,
        )
        mocked_apply_threshold.return_value = (
            Decimal("500.00"),
            "Threshold crossed in current transaction (cumulative mode).",
            "THRESHOLD_CROSSED_CUMULATIVE",
        )
        header = SimpleNamespace(
            id=55,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tcs_section=SimpleNamespace(
                id=11,
                section_code="206C(1H)",
                base_rule=1,
                rate_default=Decimal("0.1000"),
                threshold_default=Decimal("5000000.00"),
                applicability_json={"threshold_mode": "cumulative"},
            ),
        )

        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=10,
            invoice_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )

        self.assertTrue(res.enabled)
        self.assertEqual(res.base_amount, Decimal("500.00"))
        self.assertEqual(res.amount, Decimal("0.50"))
        self.assertEqual(res.reason_code, "THRESHOLD_CROSSED_CUMULATIVE")

    @patch("sales.services.sales_withholding_service._apply_section_threshold")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.resolve_rate")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.resolve_party_profile")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tcs_uses_gross_total_for_invoice_value_incl_gst_base_rule(
        self,
        mocked_get_cfg,
        mocked_resolve_party_profile,
        mocked_resolve_rate,
        mocked_apply_threshold,
    ):
        mocked_get_cfg.return_value = SimpleNamespace(enable_tcs=True, apply_tcs_206c1h=True)
        mocked_resolve_party_profile.return_value = None
        mocked_resolve_rate.return_value = SimpleNamespace(
            rate=Decimal("1.0000"),
            reason=None,
            reason_code=None,
            no_pan_applied=False,
            sec_206ab_applied=False,
            lower_rate_applied=False,
        )
        mocked_apply_threshold.return_value = (Decimal("1180.00"), None, None)
        header = SimpleNamespace(
            id=55,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tcs_section=SimpleNamespace(
                id=11,
                section_code="206C(1)",
                base_rule=int(WithholdingBaseRule.INVOICE_VALUE_INCL_GST),
                rate_default=Decimal("1.0000"),
                threshold_default=Decimal("0.00"),
                applicability_json={},
            ),
        )

        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=10,
            invoice_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )

        self.assertTrue(res.enabled)
        self.assertEqual(res.base_amount, Decimal("1180.00"))
        self.assertEqual(res.amount, Decimal("11.80"))
        self.assertEqual(mocked_apply_threshold.call_args.kwargs["base_amount"], Decimal("1180.00"))

    @patch("sales.services.sales_withholding_service._apply_section_threshold")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.resolve_rate")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.resolve_party_profile")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tcs_keeps_taxable_total_for_invoice_value_excl_gst_base_rule(
        self,
        mocked_get_cfg,
        mocked_resolve_party_profile,
        mocked_resolve_rate,
        mocked_apply_threshold,
    ):
        mocked_get_cfg.return_value = SimpleNamespace(enable_tcs=True, apply_tcs_206c1h=True)
        mocked_resolve_party_profile.return_value = None
        mocked_resolve_rate.return_value = SimpleNamespace(
            rate=Decimal("1.0000"),
            reason=None,
            reason_code=None,
            no_pan_applied=False,
            sec_206ab_applied=False,
            lower_rate_applied=False,
        )
        mocked_apply_threshold.return_value = (Decimal("1000.00"), None, None)
        header = SimpleNamespace(
            id=55,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tcs_section=SimpleNamespace(
                id=11,
                section_code="206C(1)",
                base_rule=int(WithholdingBaseRule.INVOICE_VALUE_EXCL_GST),
                rate_default=Decimal("1.0000"),
                threshold_default=Decimal("0.00"),
                applicability_json={},
            ),
        )

        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=10,
            invoice_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )

        self.assertTrue(res.enabled)
        self.assertEqual(res.base_amount, Decimal("1000.00"))
        self.assertEqual(res.amount, Decimal("10.00"))
        self.assertEqual(mocked_apply_threshold.call_args.kwargs["base_amount"], Decimal("1000.00"))

    @patch("sales.services.sales_withholding_service.WithholdingResolver.resolve_rate")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.resolve_party_profile")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tcs_applies_no_pan_higher_rate_for_customer_profile(
        self,
        mocked_get_cfg,
        mocked_resolve_party_profile,
        mocked_resolve_rate,
    ):
        mocked_get_cfg.return_value = SimpleNamespace(enable_tcs=True, apply_tcs_206c1h=True)
        mocked_resolve_party_profile.return_value = SimpleNamespace(is_pan_available=False)
        mocked_resolve_rate.return_value = SimpleNamespace(
            rate=Decimal("1.0000"),
            reason="Higher rate (PAN missing 206AA)",
            reason_code="NO_PAN_206AA",
            no_pan_applied=True,
            sec_206ab_applied=False,
            lower_rate_applied=False,
        )
        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tcs_section=SimpleNamespace(
                section_code="206C(1H)",
                base_rule=1,
                rate_default=Decimal("0.1000"),
                threshold_default=Decimal("0.00"),
                applicability_json={"threshold_mode": "cumulative"},
            ),
        )

        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=10,
            invoice_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )

        self.assertTrue(res.enabled)
        self.assertEqual(res.rate, Decimal("1.0000"))
        self.assertEqual(res.base_amount, Decimal("1000.00"))
        self.assertEqual(res.amount, Decimal("10.00"))
        self.assertEqual(res.reason_code, "NO_PAN_206AA")
        self.assertTrue(res.no_pan_applied)

    @patch("sales.services.sales_withholding_service.WithholdingResolver.resolve_party_profile")
    @patch("sales.services.sales_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tcs_skips_for_exempt_customer_profile(
        self,
        mocked_get_cfg,
        mocked_resolve_party_profile,
    ):
        mocked_get_cfg.return_value = SimpleNamespace(enable_tcs=True, apply_tcs_206c1h=True)
        mocked_resolve_party_profile.return_value = SimpleNamespace(
            is_exempt_withholding=True,
            is_pan_available=True,
        )
        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tcs_section=SimpleNamespace(
                id=11,
                section_code="206C(1H)",
                base_rule=1,
                rate_default=Decimal("0.1000"),
                threshold_default=Decimal("0.00"),
                applicability_json={"threshold_mode": "cumulative"},
                requires_pan=False,
                higher_rate_no_pan=None,
                higher_rate_206ab=None,
            ),
        )

        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=10,
            invoice_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )

        self.assertTrue(res.enabled)
        self.assertEqual(res.amount, Decimal("0.00"))
        self.assertEqual(res.reason_code, "EXEMPT")
        self.assertEqual(res.rate, Decimal("0.0000"))

    def test_reverse_move_type(self):
        self.assertEqual(SalesInvoiceService._reverse_move_type("IN"), "OUT")
        self.assertEqual(SalesInvoiceService._reverse_move_type("OUT"), "IN")
        self.assertEqual(SalesInvoiceService._reverse_move_type("ADJ"), "REV")

    @patch("sales.services.sales_invoice_service.resolve_posting_location_id", return_value=5)
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._build_stock_balance_maps")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._stock_policy")
    @patch("sales.services.sales_invoice_service.Product.objects")
    def test_validate_stock_policy_blocks_shortage_when_negative_stock_disabled(
        self,
        mocked_product_objects,
        mocked_stock_policy,
        mocked_build_maps,
        mocked_resolve_location,
    ):
        mocked_stock_policy.return_value = SimpleNamespace(
            mode="STRICT",
            allow_negative_stock=False,
            expiry_validation_required=False,
            fefo_required=False,
            allow_manual_batch_override=True,
        )
        mocked_build_maps.return_value = (
            {(1, "B1", 5): Decimal("1.0000")},
            {},
        )
        mocked_product_qs = mocked_product_objects.filter.return_value.select_related.return_value.prefetch_related.return_value.only.return_value
        mocked_product_qs.__iter__.return_value = iter([
            SimpleNamespace(
                id=1,
                productname="A-B",
                is_service=False,
                is_batch_managed=True,
                is_expiry_tracked=False,
                base_uom_id=None,
                base_uom=None,
                uom_conversions=[],
            )
        ])

        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            bill_date=date(2026, 4, 13),
            location_id=5,
            godown_id=None,
        )
        lines = [
            SimpleNamespace(
                product_id=1,
                qty=Decimal("2.000"),
                free_qty=Decimal("0.000"),
                batch_number="B1",
                expiry_date=date(2026, 5, 1),
                line_no=1,
            )
        ]

        with self.assertRaisesMessage(ValidationError, "insufficient stock"):
            SalesInvoiceService._validate_stock_policy_on_post(header=header, lines=lines)

        self.assertTrue(mocked_resolve_location.called)

    @patch("sales.services.sales_invoice_service.resolve_posting_location_id", return_value=5)
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._build_stock_balance_maps")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._stock_policy")
    @patch("sales.services.sales_invoice_service.Product.objects")
    def test_validate_stock_policy_uses_base_qty_for_alternate_uom(
        self,
        mocked_product_objects,
        mocked_stock_policy,
        mocked_build_maps,
        mocked_resolve_location,
    ):
        mocked_stock_policy.return_value = SimpleNamespace(
            mode="STRICT",
            allow_negative_stock=False,
            expiry_validation_required=False,
            fefo_required=False,
            allow_manual_batch_override=True,
        )
        mocked_build_maps.return_value = (
            {(1, "", 5): Decimal("500.0000")},
            {},
        )
        kg_uom = SimpleNamespace(id=2, code="KG")
        gms_uom = SimpleNamespace(id=1, code="GMS")
        product = SimpleNamespace(
            id=1,
            productname="Flour",
            is_service=False,
            is_batch_managed=False,
            is_expiry_tracked=False,
            base_uom_id=1,
            base_uom=gms_uom,
            uom_conversions=[
                SimpleNamespace(
                    from_uom_id=2,
                    from_uom=kg_uom,
                    to_uom_id=1,
                    to_uom=gms_uom,
                    factor=Decimal("1000"),
                )
            ],
        )
        mocked_product_objects.filter.return_value.select_related.return_value.prefetch_related.return_value.only.return_value = [product]

        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            bill_date=date(2026, 4, 13),
            location_id=5,
            godown_id=None,
        )
        lines = [
            SimpleNamespace(
                product_id=1,
                qty=Decimal("1.000"),
                free_qty=Decimal("0.000"),
                uom_id=2,
                batch_number="",
                expiry_date=None,
                line_no=1,
            )
        ]

        with self.assertRaisesMessage(ValidationError, "Required 1000.0000, available 500.0000"):
            SalesInvoiceService._validate_stock_policy_on_post(header=header, lines=lines)

        self.assertTrue(mocked_resolve_location.called)


class SalesPostingAdapterUnitTests(SimpleTestCase):
    def _base_header(self, **overrides):
        defaults = {
            "id": 201,
            "entity_id": 1,
            "entityfinid_id": 1,
            "subentity_id": None,
            "bill_date": date(2026, 3, 3),
            "posting_date": date(2026, 3, 3),
            "customer_id": 7001,
            "customer_ledger_id": 7001,
            "customer_name": "Customer-A",
            "customer": SimpleNamespace(accountname="Customer-A", ledger_id=7001),
            "doc_type": 1,
            "sales_number": "SINV-201",
            "grand_total": Decimal("250.00"),
            "roundoff": Decimal("0.00"),
            "affects_inventory": False,
            "charges": [],
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def _line(self, **overrides):
        defaults = {
            "id": 301,
            "line_no": 1,
            "product_id": 1,
            "productDesc": "Industrial Flour",
            "is_service": False,
            "taxable_value": Decimal("250.00"),
            "cgst_amount": Decimal("0.00"),
            "sgst_amount": Decimal("0.00"),
            "igst_amount": Decimal("0.00"),
            "cess_amount": Decimal("0.00"),
            "qty": Decimal("250.0000"),
            "free_qty": Decimal("0.0000"),
            "uom_id": 1,
            "sales_account_id": 5000,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    @patch("posting.adapters.sales_invoice.PostingService")
    @patch("posting.adapters.sales_invoice.Product.objects")
    @patch("posting.adapters.sales_invoice.ProductAccountResolver")
    @patch("posting.adapters.sales_invoice.StaticAccountResolver")
    def test_posts_tcs_with_single_net_customer_receivable(
        self,
        mock_static_resolver_cls,
        mock_product_resolver_cls,
        mock_product_objects,
        mock_posting_service_cls,
    ):
        code_map = {
            StaticAccountCodes.ROUND_OFF_INCOME: 8101,
            StaticAccountCodes.ROUND_OFF_EXPENSE: 8102,
            StaticAccountCodes.OUTPUT_CGST: 8103,
            StaticAccountCodes.OUTPUT_SGST: 8104,
            StaticAccountCodes.OUTPUT_IGST: 8105,
            StaticAccountCodes.OUTPUT_CESS: 8106,
            StaticAccountCodes.SALES_DEFAULT: 8107,
            StaticAccountCodes.SALES_REVENUE: 8108,
            StaticAccountCodes.TCS_PAYABLE: 8109,
        }
        resolver = mock_static_resolver_cls.return_value
        resolver.get_account_id.side_effect = lambda code, required=False: code_map.get(code)
        resolver.get_ledger_id.side_effect = lambda code, required=False: code_map.get(code)
        mock_product_resolver_cls.return_value.sales_account_id.return_value = 5000
        mock_product_objects.filter.return_value.select_related.return_value.prefetch_related.return_value = []
        mock_posting_service_cls.return_value.post.return_value = SimpleNamespace(id=999)

        SalesInvoicePostingAdapter.post_sales_invoice.__wrapped__(
            header=self._base_header(grand_total=Decimal("250.00"), tcs_amount=Decimal("5.00")),
            lines=[self._line()],
            user_id=1,
            config=SalesInvoicePostingConfig(post_inventory=False),
        )

        jl_inputs = mock_posting_service_cls.return_value.post.call_args.kwargs["jl_inputs"]
        tcs_payable = [
            x for x in jl_inputs
            if x.account_id == 8109 and x.drcr is False and x.amount == Decimal("5.00")
            and "tcs payable" in x.description.lower()
        ]
        customer_dr = [
            x for x in jl_inputs
            if x.account_id == 7001 and x.drcr is True and x.amount == Decimal("255.00")
            and "customer receivable" in x.description.lower()
        ]
        extra_customer_tcs_lines = [
            x for x in jl_inputs
            if x.account_id == 7001 and "tcs" in x.description.lower() and x.amount == Decimal("5.00")
        ]

        self.assertTrue(tcs_payable, "Expected TCS payable credit line.")
        self.assertTrue(customer_dr, "Expected single net customer receivable including TCS.")
        self.assertFalse(extra_customer_tcs_lines, "Did not expect a separate customer TCS line.")
        gst_output_lines = [
            x for x in jl_inputs
            if x.account_id in {8103, 8104, 8105, 8106}
        ]
        self.assertFalse(gst_output_lines, "TCS-only fixture should not create or distort GST output lines.")

    @patch("sales.services.sales_invoice_service.SalesWithholdingService.compute_tcs")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService.get_settings")
    def test_apply_tcs_keeps_gst_taxable_totals_unchanged(self, mocked_get_settings, mocked_compute_tcs):
        mocked_get_settings.return_value = SimpleNamespace(tcs_credit_note_policy="REVERSE")
        section = SimpleNamespace(id=11, section_code="206C(1H)")
        mocked_compute_tcs.return_value = WithholdingResult(
            enabled=True,
            section=section,
            rate=Decimal("0.1000"),
            base_amount=Decimal("1000.00"),
            amount=Decimal("5.00"),
            reason="Threshold crossed in current transaction (cumulative mode).",
            reason_code="THRESHOLD_CROSSED_CUMULATIVE",
        )

        class Header:
            withholding_enabled = True
            doc_type = int(SalesInvoiceHeader.DocType.TAX_INVOICE)
            tcs_section = section
            tcs_section_id = 11
            tcs_rate = Decimal("0.0000")
            tcs_base_amount = Decimal("0.00")
            tcs_amount = Decimal("0.00")
            tcs_reason = ""
            tcs_is_reversal = False
            entity_id = 1
            entityfinid_id = 1
            subentity_id = None
            customer_id = 1
            bill_date = date(2026, 4, 1)
            grand_total = Decimal("1180.00")
            total_taxable_value = Decimal("1000.00")
            total_cgst = Decimal("90.00")
            total_sgst = Decimal("90.00")
            total_igst = Decimal("0.00")
            legacy_behavior_flags = {}
            customer_receivable = Decimal("1180.00")

            def save(self, **kwargs):
                return None

        h = Header()
        SalesInvoiceService._apply_tcs(header=h, user=None)

        self.assertEqual(h.total_taxable_value, Decimal("1000.00"))
        self.assertEqual(h.total_cgst, Decimal("90.00"))
        self.assertEqual(h.total_sgst, Decimal("90.00"))
        self.assertEqual(h.total_igst, Decimal("0.00"))
        self.assertEqual(h.grand_total, Decimal("1180.00"))
        self.assertEqual(h.customer_receivable, Decimal("1185.00"))
        self.assertEqual(h.tcs_amount, Decimal("5.00"))

    @patch("posting.adapters.sales_invoice.PostingService")
    @patch("posting.adapters.sales_invoice.Product.objects")
    @patch("posting.adapters.sales_invoice.ProductAccountResolver")
    @patch("posting.adapters.sales_invoice.StaticAccountResolver")
    def test_posts_tcs_reversal_with_single_net_customer_reversal(
        self,
        mock_static_resolver_cls,
        mock_product_resolver_cls,
        mock_product_objects,
        mock_posting_service_cls,
    ):
        code_map = {
            StaticAccountCodes.ROUND_OFF_INCOME: 8101,
            StaticAccountCodes.ROUND_OFF_EXPENSE: 8102,
            StaticAccountCodes.OUTPUT_CGST: 8103,
            StaticAccountCodes.OUTPUT_SGST: 8104,
            StaticAccountCodes.OUTPUT_IGST: 8105,
            StaticAccountCodes.OUTPUT_CESS: 8106,
            StaticAccountCodes.SALES_DEFAULT: 8107,
            StaticAccountCodes.SALES_REVENUE: 8108,
            StaticAccountCodes.TCS_PAYABLE: 8109,
        }
        resolver = mock_static_resolver_cls.return_value
        resolver.get_account_id.side_effect = lambda code, required=False: code_map.get(code)
        resolver.get_ledger_id.side_effect = lambda code, required=False: code_map.get(code)
        mock_product_resolver_cls.return_value.sales_account_id.return_value = 5000
        mock_product_objects.filter.return_value.select_related.return_value.prefetch_related.return_value = []
        mock_posting_service_cls.return_value.post.return_value = SimpleNamespace(id=1000)

        SalesInvoicePostingAdapter.post_sales_invoice.__wrapped__(
            header=self._base_header(
                doc_type=2,
                grand_total=Decimal("250.00"),
                tcs_amount=Decimal("5.00"),
                tcs_is_reversal=True,
            ),
            lines=[self._line()],
            user_id=1,
            config=SalesInvoicePostingConfig(post_inventory=False),
        )

        jl_inputs = mock_posting_service_cls.return_value.post.call_args.kwargs["jl_inputs"]
        tcs_reversal = [
            x for x in jl_inputs
            if x.account_id == 8109 and x.drcr is True and x.amount == Decimal("5.00")
            and "tcs reversal" in x.description.lower()
        ]
        customer_cr = [
            x for x in jl_inputs
            if x.account_id == 7001 and x.drcr is False and x.amount == Decimal("255.00")
            and "customer reversal" in x.description.lower()
        ]
        extra_customer_tcs_lines = [
            x for x in jl_inputs
            if x.account_id == 7001 and "tcs" in x.description.lower() and x.amount == Decimal("5.00")
        ]

        self.assertTrue(tcs_reversal, "Expected TCS payable reversal debit line.")
        self.assertTrue(customer_cr, "Expected single net customer reversal including TCS reversal.")
        self.assertFalse(extra_customer_tcs_lines, "Did not expect a separate customer TCS reversal line.")

    @patch("posting.adapters.sales_invoice.resolve_posting_location_id", return_value=5)
    @patch("posting.adapters.sales_invoice.PostingService")
    @patch("posting.adapters.sales_invoice.Product.objects")
    @patch("posting.adapters.sales_invoice.ProductAccountResolver")
    @patch("posting.adapters.sales_invoice.StaticAccountResolver")
    def test_inventory_move_uses_uom_conversion_for_base_qty(
        self,
        mock_static_resolver_cls,
        mock_product_resolver_cls,
        mock_product_objects,
        mock_posting_service_cls,
        mocked_resolve_location,
    ):
        code_map = {
            StaticAccountCodes.ROUND_OFF_INCOME: 8101,
            StaticAccountCodes.ROUND_OFF_EXPENSE: 8102,
            StaticAccountCodes.OUTPUT_CGST: 8103,
            StaticAccountCodes.OUTPUT_SGST: 8104,
            StaticAccountCodes.OUTPUT_IGST: 8105,
            StaticAccountCodes.OUTPUT_CESS: 8106,
            StaticAccountCodes.SALES_DEFAULT: 8107,
            StaticAccountCodes.SALES_REVENUE: 8108,
        }
        resolver = mock_static_resolver_cls.return_value
        resolver.get_account_id.side_effect = lambda code, required=False: code_map.get(code)
        mock_product_resolver_cls.return_value.sales_account_id.return_value = 5000

        kg_uom = SimpleNamespace(id=2, code="KG")
        gms_uom = SimpleNamespace(id=1, code="GMS")
        product = SimpleNamespace(
            id=1,
            base_uom_id=1,
            base_uom=gms_uom,
            uom_conversions=[
                SimpleNamespace(
                    from_uom_id=2,
                    from_uom=kg_uom,
                    to_uom_id=1,
                    to_uom=gms_uom,
                    factor=Decimal("1000"),
                )
            ],
        )
        mock_product_objects.filter.return_value.select_related.return_value.prefetch_related.return_value = [product]

        posting_instance = mock_posting_service_cls.return_value
        posting_instance.post.return_value = SimpleNamespace(id=999)

        header = self._base_header(affects_inventory=True)

        SalesInvoicePostingAdapter.post_sales_invoice.__wrapped__(
            header=header,
            lines=[self._line(qty=Decimal("1.0000"), taxable_value=Decimal("250.00"), uom_id=2)],
            user_id=1,
            config=SalesInvoicePostingConfig(),
        )

        kwargs = posting_instance.post.call_args.kwargs
        move = kwargs["im_inputs"][0]
        self.assertEqual(move.qty, Decimal("1.0000"))
        self.assertEqual(move.uom_factor, Decimal("1000.0000"))
        self.assertEqual(move.base_qty, Decimal("1000.0000"))
        self.assertEqual(move.base_uom_id, 1)
        self.assertTrue(mocked_resolve_location.called)

    @patch("posting.adapters.sales_invoice.resolve_posting_location_id", return_value=5)
    @patch("posting.adapters.sales_invoice.PostingService")
    @patch("posting.adapters.sales_invoice.Product.objects")
    @patch("posting.adapters.sales_invoice.ProductAccountResolver")
    @patch("posting.adapters.sales_invoice.StaticAccountResolver")
    def test_inventory_move_generates_internal_expiry_lot_for_expiry_tracked_product(
        self,
        mock_static_resolver_cls,
        mock_product_resolver_cls,
        mock_product_objects,
        mock_posting_service_cls,
        mocked_resolve_location,
    ):
        code_map = {
            StaticAccountCodes.ROUND_OFF_INCOME: 8101,
            StaticAccountCodes.ROUND_OFF_EXPENSE: 8102,
            StaticAccountCodes.OUTPUT_CGST: 8103,
            StaticAccountCodes.OUTPUT_SGST: 8104,
            StaticAccountCodes.OUTPUT_IGST: 8105,
            StaticAccountCodes.OUTPUT_CESS: 8106,
            StaticAccountCodes.SALES_DEFAULT: 8107,
            StaticAccountCodes.SALES_REVENUE: 8108,
        }
        resolver = mock_static_resolver_cls.return_value
        resolver.get_account_id.side_effect = lambda code, required=False: code_map.get(code)
        mock_product_resolver_cls.return_value.sales_account_id.return_value = 5000
        product = SimpleNamespace(
            id=1,
            base_uom_id=1,
            base_uom=SimpleNamespace(id=1, code="PCS"),
            uom_conversions=[],
            is_batch_managed=False,
            is_expiry_tracked=True,
        )
        mock_product_objects.filter.return_value.select_related.return_value.prefetch_related.return_value = [product]

        posting_instance = mock_posting_service_cls.return_value
        posting_instance.post.return_value = SimpleNamespace(id=1000)

        header = self._base_header(affects_inventory=True, grand_total=Decimal("200.00"))

        SalesInvoicePostingAdapter.post_sales_invoice.__wrapped__(
            header=header,
            lines=[
                self._line(
                    qty=Decimal("2.0000"),
                    taxable_value=Decimal("200.00"),
                    uom_id=1,
                    batch_number="",
                    expiry_date=date(2026, 5, 1),
                )
            ],
            user_id=1,
            config=SalesInvoicePostingConfig(),
        )

        kwargs = posting_instance.post.call_args.kwargs
        move = kwargs["im_inputs"][0]
        self.assertEqual(move.batch_number, "EXP-1-20260501")
        self.assertEqual(move.expiry_date, date(2026, 5, 1))
        self.assertTrue(mocked_resolve_location.called)

    @patch("posting.adapters.sales_invoice.resolve_posting_location_id", return_value=5)
    @patch("posting.adapters.sales_invoice.PostingService")
    @patch("posting.adapters.sales_invoice.Product.objects")
    @patch("posting.adapters.sales_invoice.ProductAccountResolver")
    @patch("posting.adapters.sales_invoice.StaticAccountResolver")
    def test_sales_descriptions_include_customer_and_item_context(
        self,
        mock_static_resolver_cls,
        mock_product_resolver_cls,
        mock_product_objects,
        mock_posting_service_cls,
        mocked_resolve_location,
    ):
        code_map = {
            StaticAccountCodes.ROUND_OFF_INCOME: 8101,
            StaticAccountCodes.ROUND_OFF_EXPENSE: 8102,
            StaticAccountCodes.OUTPUT_CGST: 8103,
            StaticAccountCodes.OUTPUT_SGST: 8104,
            StaticAccountCodes.OUTPUT_IGST: 8105,
            StaticAccountCodes.OUTPUT_CESS: 8106,
            StaticAccountCodes.SALES_DEFAULT: 8107,
            StaticAccountCodes.SALES_REVENUE: 8108,
        }
        resolver = mock_static_resolver_cls.return_value
        resolver.get_account_id.side_effect = lambda code, required=False: code_map.get(code)
        mock_product_resolver_cls.return_value.sales_account_id.return_value = 5000
        mock_product_objects.filter.return_value.select_related.return_value.prefetch_related.return_value = [
            SimpleNamespace(
                id=1,
                base_uom_id=1,
                base_uom=SimpleNamespace(id=1, code="PCS"),
                uom_conversions=[],
            )
        ]
        mock_posting_service_cls.return_value.post.return_value = SimpleNamespace(id=999)

        SalesInvoicePostingAdapter.post_sales_invoice.__wrapped__(
            header=self._base_header(),
            lines=[self._line()],
            user_id=1,
            config=SalesInvoicePostingConfig(),
        )

        jl_inputs = mock_posting_service_cls.return_value.post.call_args.kwargs["jl_inputs"]
        self.assertIn("Customer Customer-A", jl_inputs[0].description)
        self.assertIn("Item Industrial Flour", jl_inputs[0].description)
        self.assertTrue(mocked_resolve_location.called)

class SalesInvoiceAdditionalServiceUnitTests(SimpleTestCase):
    @patch("sales.services.sales_invoice_service.resolve_posting_location_id", return_value=5)
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._build_stock_balance_maps")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._stock_policy")
    @patch("sales.services.sales_invoice_service.Product.objects")
    def test_validate_stock_policy_allows_numeric_batch_aliases(
        self,
        mocked_product_objects,
        mocked_stock_policy,
        mocked_build_maps,
        mocked_resolve_location,
    ):
        mocked_stock_policy.return_value = SimpleNamespace(
            mode="STRICT",
            allow_negative_stock=False,
            expiry_validation_required=False,
            fefo_required=False,
            allow_manual_batch_override=True,
        )
        mocked_build_maps.return_value = (
            {(1, "1", 5): Decimal("2.0000")},
            {},
        )
        mocked_product_qs = mocked_product_objects.filter.return_value.select_related.return_value.prefetch_related.return_value.only.return_value
        mocked_product_qs.__iter__.return_value = iter([
            SimpleNamespace(
                id=1,
                productname="Product-B",
                is_service=False,
                is_batch_managed=True,
                is_expiry_tracked=False,
                base_uom_id=None,
                base_uom=None,
                uom_conversions=[],
            )
        ])

        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            bill_date=date(2026, 4, 13),
            location_id=5,
            godown_id=None,
        )
        lines = [
            SimpleNamespace(
                product_id=1,
                qty=Decimal("2.000"),
                free_qty=Decimal("0.000"),
                batch_number="01",
                expiry_date=date(2026, 5, 1),
                line_no=1,
            )
        ]

        SalesInvoiceService._validate_stock_policy_on_post(header=header, lines=lines)
        self.assertTrue(mocked_resolve_location.called)

    @patch("sales.services.sales_invoice_service.resolve_posting_location_id", return_value=5)
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._build_stock_balance_maps")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._stock_policy")
    @patch("sales.services.sales_invoice_service.Product.objects")
    def test_allocate_batches_auto_picks_earliest_available_batch(
        self,
        mocked_product_objects,
        mocked_stock_policy,
        mocked_build_maps,
        mocked_resolve_location,
    ):
        mocked_stock_policy.return_value = SimpleNamespace(
            mode="STRICT",
            allow_negative_stock=False,
            batch_required_for_sales=True,
            expiry_validation_required=True,
            fefo_required=True,
            allow_manual_batch_override=False,
        )
        mocked_build_maps.return_value = (
            {(1, "B-A", 5): Decimal("3.0000"), (1, "B-B", 5): Decimal("4.0000")},
            {
                (1, "B-B", 5, date(2026, 6, 1)): Decimal("4.0000"),
                (1, "B-A", 5, date(2026, 5, 1)): Decimal("3.0000"),
            },
        )
        mocked_product_qs = mocked_product_objects.filter.return_value.select_related.return_value.prefetch_related.return_value.only.return_value
        mocked_product_qs.__iter__.return_value = iter([
            SimpleNamespace(
                id=1,
                productname="A-B",
                is_service=False,
                is_batch_managed=True,
                is_expiry_tracked=True,
                base_uom_id=None,
                base_uom=None,
                uom_conversions=[],
            )
        ])

        saved = []

        class Line:
            product_id = 1
            qty = Decimal("1.000")
            free_qty = Decimal("0.000")
            batch_number = ""
            manufacture_date = None
            expiry_date = None
            line_no = 1

            def save(self, update_fields=None):
                saved.append(list(update_fields or []))

        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            bill_date=date(2026, 4, 13),
            location_id=5,
            godown_id=None,
        )

        line = Line()
        SalesInvoiceService._allocate_batches_for_post(header=header, lines=[line])

        self.assertEqual(line.batch_number, "B-A")
        self.assertEqual(line.expiry_date, date(2026, 5, 1))
        self.assertTrue(saved)
        self.assertIn("batch_number", saved[0])

    @patch("sales.services.sales_invoice_service.resolve_posting_location_id", return_value=5)
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._build_stock_balance_maps")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._stock_policy")
    @patch("sales.services.sales_invoice_service.Product.objects")
    def test_allocate_batches_infers_location_when_header_location_not_set(
        self,
        mocked_product_objects,
        mocked_stock_policy,
        mocked_build_maps,
        mocked_resolve_location,
    ):
        mocked_stock_policy.return_value = SimpleNamespace(
            mode="STRICT",
            allow_negative_stock=False,
            batch_required_for_sales=True,
            expiry_validation_required=False,
            fefo_required=False,
            allow_manual_batch_override=True,
        )
        mocked_build_maps.return_value = (
            {(1, "1", 1): Decimal("3.0000")},
            {(1, "1", 1, date(2026, 5, 1)): Decimal("3.0000")},
        )
        mocked_product_qs = mocked_product_objects.filter.return_value.select_related.return_value.prefetch_related.return_value.only.return_value
        mocked_product_qs.__iter__.return_value = iter([
            SimpleNamespace(
                id=1,
                productname="Product-B",
                is_service=False,
                is_batch_managed=True,
                is_expiry_tracked=False,
                base_uom_id=None,
                base_uom=None,
                uom_conversions=[],
            )
        ])

        line = SimpleNamespace(
            product_id=1,
            qty=Decimal("1.000"),
            free_qty=Decimal("0.000"),
            batch_number="1",
            manufacture_date=None,
            expiry_date=None,
            line_no=1,
            save=lambda update_fields=None: None,
        )

        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            bill_date=date(2026, 4, 13),
            location_id=None,
            godown_id=None,
            save=MagicMock(),
        )

        SalesInvoiceService._allocate_batches_for_post(header=header, lines=[line])
        self.assertEqual(header.location_id, 1)
        header.save.assert_called()
        self.assertTrue(mocked_resolve_location.called)

    def test_recompute_settlement_fields_open(self):
        header = SimpleNamespace(
            grand_total=Decimal("1000.00"),
            tcs_amount=Decimal("20.00"),
            settled_amount=Decimal("0.00"),
            settlement_status=None,
            outstanding_amount=None,
        )
        SalesInvoiceService.recompute_settlement_fields(header=header)
        self.assertEqual(header.outstanding_amount, Decimal("1020.00"))
        self.assertEqual(header.settlement_status, int(SalesInvoiceHeader.SettlementStatus.OPEN))

    def test_recompute_settlement_fields_partial(self):
        header = SimpleNamespace(
            grand_total=Decimal("1000.00"),
            tcs_amount=Decimal("20.00"),
            settled_amount=Decimal("500.00"),
            settlement_status=None,
            outstanding_amount=None,
        )
        SalesInvoiceService.recompute_settlement_fields(header=header)
        self.assertEqual(header.outstanding_amount, Decimal("520.00"))
        self.assertEqual(header.settlement_status, int(SalesInvoiceHeader.SettlementStatus.PARTIAL))

    def test_recompute_settlement_fields_settled_caps_to_gross(self):
        header = SimpleNamespace(
            grand_total=Decimal("1000.00"),
            tcs_amount=Decimal("20.00"),
            settled_amount=Decimal("2000.00"),
            settlement_status=None,
            outstanding_amount=None,
        )
        SalesInvoiceService.recompute_settlement_fields(header=header)
        self.assertEqual(header.settled_amount, Decimal("1020.00"))
        self.assertEqual(header.outstanding_amount, Decimal("0.00"))
        self.assertEqual(header.settlement_status, int(SalesInvoiceHeader.SettlementStatus.SETTLED))

    def test_validate_doc_linkage_cn_requires_original(self):
        with self.assertRaisesMessage(ValueError, "original_invoice is required"):
            SalesInvoiceService._validate_doc_linkage(
                doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
                original_invoice=None,
                entity_id=1,
                entityfinid_id=1,
                subentity_id=None,
                customer_id=10,
            )

    def test_align_note_tax_scope_from_original_invoice(self):
        header_data = {
            "seller_gstin": "22AAAAA0000A1Z5",
            "seller_state_code": "22",
            "place_of_supply_state_code": "22",
        }
        original = SimpleNamespace(
            seller_gstin="03BNDPG2450J1Z3",
            seller_state_code="03",
            place_of_supply_state_code="0",
        )

        SalesInvoiceService._align_note_tax_scope_from_original_invoice(
            header_data=header_data,
            original_invoice=original,
        )

        self.assertEqual(header_data["seller_gstin"], "03BNDPG2450J1Z3")
        self.assertEqual(header_data["seller_state_code"], "03")
        self.assertEqual(header_data["place_of_supply_state_code"], "0")

    def test_validate_doc_linkage_tax_invoice_disallows_original(self):
        original = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, customer_id=10)
        with self.assertRaisesMessage(ValueError, "allowed only for Credit Note / Debit Note"):
            SalesInvoiceService._validate_doc_linkage(
                doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
                original_invoice=original,
                entity_id=1,
                entityfinid_id=1,
                subentity_id=None,
                customer_id=10,
            )

    def test_validate_b2b_gstin_requirements_blocks_missing_customer_gstin(self):
        header = SimpleNamespace(
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            seller_gstin="22AAAAA0000A1Z5",
            customer_gstin="",
        )
        with self.assertRaisesMessage(ValueError, "customer_gstin"):
            SalesInvoiceService._validate_b2b_gstin_requirements(header=header)

    def test_derive_compliance_flags_auto(self):
        header = SimpleNamespace(
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            seller_gstin="22AAAAA0000A1Z5",
            customer_gstin="27BBBBB1111B2Z6",
            grand_total=Decimal("75000.00"),
            einvoice_applicable_manual=None,
            eway_applicable_manual=None,
            compliance_override_reason="",
            compliance_override_at=None,
            compliance_override_by=None,
            is_einvoice_applicable=False,
            is_eway_applicable=False,
            gst_compliance_mode=int(SalesInvoiceHeader.GstComplianceMode.NONE),
        )
        settings_obj = SalesSettings(
            enable_einvoice=True,
            enable_eway=True,
            einvoice_entity_applicable=True,
            eway_value_threshold=Decimal("50000.00"),
            compliance_applicability_mode=SalesSettings.ComplianceApplicabilityMode.AUTO_ONLY,
        )
        SalesInvoiceService._derive_compliance_flags(header=header, settings_obj=settings_obj, user=None)
        self.assertTrue(header.is_einvoice_applicable)
        self.assertTrue(header.is_eway_applicable)
        self.assertEqual(header.gst_compliance_mode, int(SalesInvoiceHeader.GstComplianceMode.EINVOICE_AND_EWAY))

    def test_derive_compliance_flags_manual_requires_reason(self):
        header = SimpleNamespace(
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            seller_gstin="22AAAAA0000A1Z5",
            customer_gstin="27BBBBB1111B2Z6",
            grand_total=Decimal("1000.00"),
            einvoice_applicable_manual=True,
            eway_applicable_manual=None,
            compliance_override_reason="",
            compliance_override_at=None,
            compliance_override_by=None,
        )
        settings_obj = SalesSettings(
            enable_einvoice=True,
            enable_eway=True,
            einvoice_entity_applicable=False,
            eway_value_threshold=Decimal("50000.00"),
            compliance_applicability_mode=SalesSettings.ComplianceApplicabilityMode.AUTO_WITH_OVERRIDE,
        )
        with self.assertRaisesMessage(ValueError, "compliance_override_reason"):
            SalesInvoiceService._derive_compliance_flags(header=header, settings_obj=settings_obj, user=None)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService.get_settings")
    def test_apply_tcs_credit_note_disallow_policy(self, mocked_get_settings):
        mocked_get_settings.return_value = SimpleNamespace(tcs_credit_note_policy="DISALLOW")
        section = SimpleNamespace(section_code="206C(1)", rate_default=Decimal("0.1000"))

        class Header:
            withholding_enabled = True
            doc_type = int(SalesInvoiceHeader.DocType.CREDIT_NOTE)
            tcs_section = section
            tcs_section_id = 1
            tcs_rate = Decimal("0.1000")
            tcs_base_amount = Decimal("100.00")
            tcs_amount = Decimal("10.00")
            tcs_reason = ""
            tcs_is_reversal = False
            entity_id = 1
            subentity_id = None
            customer_id = 1
            bill_date = None

            def save(self, **kwargs):
                return None

        h = Header()
        SalesInvoiceService._apply_tcs(header=h, user=None)
        self.assertEqual(h.tcs_amount, Decimal("0.00"))
        self.assertIn("disallowed", (h.tcs_reason or "").lower())
        self.assertEqual(
            (h.legacy_behavior_flags or {}).get("tcs_runtime_result", {}).get("reason_code"),
            "CREDIT_NOTE_POLICY_DISALLOW",
        )

    @patch("sales.services.sales_invoice_service.SalesWithholdingService.compute_tcs")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService.get_settings")
    def test_apply_tcs_sales_return_credit_note_marks_tcs_reversal(
        self,
        mocked_get_settings,
        mocked_compute_tcs,
    ):
        mocked_get_settings.return_value = SimpleNamespace(tcs_credit_note_policy="REVERSE")
        section = SimpleNamespace(id=11, section_code="206C(1H)")
        mocked_compute_tcs.return_value = WithholdingResult(
            enabled=True,
            section=section,
            rate=Decimal("0.1000"),
            base_amount=Decimal("100.00"),
            amount=Decimal("10.00"),
            reason="sales return tcs reversal",
            reason_code="OK",
        )

        class Header:
            withholding_enabled = True
            doc_type = int(SalesInvoiceHeader.DocType.CREDIT_NOTE)
            note_reason = SalesInvoiceHeader.NoteReason.QUANTITY_RETURN
            affects_inventory = True
            tcs_section = section
            tcs_section_id = 11
            tcs_rate = Decimal("0.0000")
            tcs_base_amount = Decimal("0.00")
            tcs_amount = Decimal("0.00")
            tcs_reason = ""
            tcs_is_reversal = False
            entity_id = 1
            entityfinid_id = 1
            subentity_id = None
            customer_id = 1
            bill_date = date(2026, 4, 1)
            grand_total = Decimal("1180.00")
            total_taxable_value = Decimal("1000.00")
            legacy_behavior_flags = {}
            customer_receivable = Decimal("1180.00")

            def save(self, **kwargs):
                return None

        h = Header()
        SalesInvoiceService._apply_tcs(header=h, user=None)

        self.assertEqual(h.tcs_amount, Decimal("10.00"))
        self.assertTrue(h.tcs_is_reversal)
        self.assertEqual(h.customer_receivable, Decimal("1190.00"))
        runtime = (h.legacy_behavior_flags or {}).get("tcs_runtime_result", {})
        self.assertEqual(runtime.get("reason_code"), "OK")
        self.assertTrue(h.affects_inventory)
        self.assertEqual(h.note_reason, SalesInvoiceHeader.NoteReason.QUANTITY_RETURN)

    @patch("sales.services.sales_invoice_service.SalesWithholdingService.compute_tcs")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService.get_settings")
    def test_apply_tcs_persists_runtime_snapshot_for_zero_collection_reason(
        self,
        mocked_get_settings,
        mocked_compute_tcs,
    ):
        mocked_get_settings.return_value = SimpleNamespace(tcs_credit_note_policy="REVERSE")
        section = SimpleNamespace(id=11, section_code="206C(1H)")
        mocked_compute_tcs.return_value = WithholdingResult(
            enabled=True,
            section=section,
            rate=Decimal("0.1000"),
            base_amount=Decimal("0.00"),
            amount=Decimal("0.00"),
            reason="Below cumulative threshold (5000000.00)",
            reason_code="BELOW_THRESHOLD_CUMULATIVE",
        )

        class Header:
            withholding_enabled = True
            doc_type = int(SalesInvoiceHeader.DocType.TAX_INVOICE)
            tcs_section = section
            tcs_section_id = 11
            tcs_rate = Decimal("0.0000")
            tcs_base_amount = Decimal("0.00")
            tcs_amount = Decimal("0.00")
            tcs_reason = ""
            tcs_is_reversal = False
            entity_id = 1
            entityfinid_id = 1
            subentity_id = None
            customer_id = 1
            bill_date = date(2026, 4, 1)
            grand_total = Decimal("1180.00")
            total_taxable_value = Decimal("1000.00")
            legacy_behavior_flags = {}

            def save(self, **kwargs):
                return None

        h = Header()
        SalesInvoiceService._apply_tcs(header=h, user=None)

        runtime = (h.legacy_behavior_flags or {}).get("tcs_runtime_result", {})
        self.assertEqual(runtime.get("reason_code"), "BELOW_THRESHOLD_CUMULATIVE")
        self.assertEqual(runtime.get("section_code"), "206C(1H)")
        self.assertEqual(runtime.get("collection_status"), "NOT_COLLECTED")
        self.assertTrue(runtime.get("zero_collection"))
        self.assertTrue(runtime.get("user_selected_add_tcs"))

    @patch("sales.services.sales_invoice_service.SalesWithholdingService.compute_tcs")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService.get_settings")
    def test_apply_tcs_persists_runtime_snapshot_for_config_disabled_reason(
        self,
        mocked_get_settings,
        mocked_compute_tcs,
    ):
        mocked_get_settings.return_value = SimpleNamespace(tcs_credit_note_policy="REVERSE")
        mocked_compute_tcs.return_value = WithholdingResult(
            enabled=False,
            section=None,
            rate=Decimal("0.0000"),
            base_amount=Decimal("0.00"),
            amount=Decimal("0.00"),
            reason="TCS disabled in entity config",
            reason_code="DISABLED",
        )

        class Header:
            withholding_enabled = True
            doc_type = int(SalesInvoiceHeader.DocType.TAX_INVOICE)
            tcs_section = None
            tcs_section_id = 1
            tcs_rate = Decimal("0.0000")
            tcs_base_amount = Decimal("0.00")
            tcs_amount = Decimal("0.00")
            tcs_reason = ""
            tcs_is_reversal = False
            entity_id = 1
            entityfinid_id = 1
            subentity_id = None
            customer_id = 1
            bill_date = date(2026, 4, 1)
            grand_total = Decimal("1180.00")
            total_taxable_value = Decimal("1000.00")
            legacy_behavior_flags = {}

            def save(self, **kwargs):
                return None

        h = Header()
        SalesInvoiceService._apply_tcs(header=h, user=None)

        runtime = (h.legacy_behavior_flags or {}).get("tcs_runtime_result", {})
        self.assertEqual(runtime.get("reason_code"), "DISABLED")
        self.assertEqual(runtime.get("reason"), "TCS disabled in entity config")
        self.assertEqual(runtime.get("collection_status"), "NOT_COLLECTED")

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._validate_invoice_uniqueness_per_gstin")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService.ensure_doc_number")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._apply_tcs")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._validate_stock_policy_on_post")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._allocate_batches_for_post")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._validate_b2b_gstin_requirements")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._recompute_invoice_state")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._prepare_header_for_persistence")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService.get_settings")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._load_invoice_rows")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService.assert_not_locked")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService.freeze_ship_to_snapshot")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._policy_level")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._policy_controls")
    def test_confirm_reapplies_tcs_after_doc_number_allocation(
        self,
        mocked_policy_controls,
        mocked_policy_level,
        mocked_freeze_ship_to_snapshot,
        mocked_assert_not_locked,
        mocked_load_invoice_rows,
        mocked_get_settings,
        mocked_prepare_header_for_persistence,
        mocked_recompute_invoice_state,
        mocked_validate_b2b_gstin_requirements,
        mocked_allocate_batches_for_post,
        mocked_validate_stock_policy_on_post,
        mocked_apply_tcs,
        mocked_ensure_doc_number,
        mocked_validate_invoice_uniqueness_per_gstin,
        mocked_run_auto_compliance,
    ):
        mocked_policy_controls.return_value = {}
        mocked_policy_level.side_effect = lambda controls, key, default="hard": default
        mocked_load_invoice_rows.return_value = ([SimpleNamespace(id=1)], [])
        mocked_get_settings.return_value = SimpleNamespace()
        mocked_recompute_invoice_state.return_value = ([SimpleNamespace(id=1)], [])

        header = SimpleNamespace(
            id=44,
            status=SalesInvoiceHeader.Status.DRAFT,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            bill_date=date(2026, 4, 1),
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            doc_code="SINV",
            doc_no=None,
            invoice_number="",
            withholding_enabled=True,
            tcs_section=SimpleNamespace(id=11, section_code="206C(1H)"),
            tcs_rate=Decimal("0.1000"),
            tcs_base_amount=Decimal("1000.00"),
            tcs_amount=Decimal("1.00"),
            tcs_reason="Threshold crossed",
            tcs_is_reversal=False,
            is_eway_applicable=False,
            posting_date=None,
            due_date=None,
            tax_regime="INTRA",
            is_igst=False,
            gst_compliance_mode="AUTO",
            is_einvoice_applicable=False,
            eway_applicable_manual=False,
            einvoice_applicable_manual=False,
            compliance_override_reason="",
            compliance_override_at=None,
            compliance_override_by=None,
            total_taxable_value=Decimal("1000.00"),
            total_cgst=Decimal("90.00"),
            total_sgst=Decimal("90.00"),
            total_igst=Decimal("0.00"),
            total_cess=Decimal("0.00"),
            total_discount=Decimal("0.00"),
            round_off=Decimal("0.00"),
            grand_total=Decimal("1180.00"),
            settled_amount=Decimal("0.00"),
            outstanding_amount=Decimal("1181.00"),
            settlement_status="OPEN",
            save=MagicMock(),
        )

        call_order = []

        def ensure_doc_number_side_effect(*, header, user=None):
            call_order.append("ensure_doc_number")
            header.doc_no = 311
            header.invoice_number = "SI-SINV-311"

        def apply_tcs_side_effect(*, header, user):
            call_order.append("apply_tcs")
            self.assertEqual(header.invoice_number, "SI-SINV-311")
            self.assertEqual(header.doc_no, 311)

        mocked_ensure_doc_number.side_effect = ensure_doc_number_side_effect
        mocked_apply_tcs.side_effect = apply_tcs_side_effect

        user = SimpleNamespace(id=99)
        SalesInvoiceService.confirm.__func__.__wrapped__(SalesInvoiceService, header=header, user=user)

        self.assertEqual(call_order, ["ensure_doc_number", "apply_tcs"])
        self.assertEqual(header.status, SalesInvoiceHeader.Status.CONFIRMED)
        self.assertEqual(header.invoice_number, "SI-SINV-311")
        self.assertEqual(header.doc_no, 311)
        mocked_run_auto_compliance.assert_called_once_with(header=header, user=user, stage="confirm")

    @patch("sales.services.sales_invoice_service.SalesInvoiceHeader.objects")
    def test_validate_adjustment_caps_blocks_excess(self, mocked_hdr_objects):
        original = SimpleNamespace(
            id=100,
            total_taxable_value=Decimal("100.00"),
            total_cgst=Decimal("9.00"),
            total_sgst=Decimal("9.00"),
            total_igst=Decimal("0.00"),
            total_cess=Decimal("0.00"),
            grand_total=Decimal("118.00"),
        )
        header = SimpleNamespace(
            id=101,
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            original_invoice_id=100,
            original_invoice=original,
            total_taxable_value=Decimal("40.00"),
            total_cgst=Decimal("3.60"),
            total_sgst=Decimal("3.60"),
            total_igst=Decimal("0.00"),
            total_cess=Decimal("0.00"),
            grand_total=Decimal("47.20"),
        )

        qs = mocked_hdr_objects.filter.return_value.exclude.return_value
        qs.exclude.return_value = qs
        qs.aggregate.return_value = {
            "taxable": Decimal("70.00"),
            "cgst": Decimal("6.30"),
            "sgst": Decimal("6.30"),
            "igst": Decimal("0.00"),
            "cess": Decimal("0.00"),
            "grand": Decimal("82.60"),
        }
        with self.assertRaisesMessage(ValueError, "cumulative"):
            SalesInvoiceService._validate_adjustment_caps(header=header)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService.get_settings")
    @patch("sales.services.sales_invoice_service.ComplianceAuditService")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService.reverse_posting")
    def test_cancel_blocked_when_statutory_not_cancelled(self, mocked_reverse, mocked_audit, mocked_get_settings):
        mocked_get_settings.return_value = SimpleNamespace(enforce_statutory_cancel_before_business_cancel=True)
        header = SimpleNamespace(
            status=int(SalesInvoiceHeader.Status.CONFIRMED),
            entity_id=1,
            subentity_id=None,
            einvoice_artifact=SimpleNamespace(status=2, irn="x"),
            eway_artifact=SimpleNamespace(status=2, ewb_no="y"),
        )
        with self.assertRaisesMessage(ValueError, "generated but not cancelled"):
            SalesInvoiceService.cancel.__func__.__wrapped__(SalesInvoiceService, header=header, user=None, reason="")
        mocked_reverse.assert_not_called()
        self.assertTrue(mocked_audit.log_action.called)
        self.assertTrue(mocked_audit.open_exception.called)


class SalesStockBalanceServiceUnitTests(SimpleTestCase):
    @patch("sales.services.sales_stock_balance_service.Godown.objects.filter")
    @patch("sales.services.sales_stock_balance_service.SalesStockBalanceService._build_balance_maps")
    @patch("sales.services.sales_stock_balance_service.resolve_posting_location_id", return_value=5)
    def test_relaxed_mode_skips_shortage_hint_when_no_other_stock_rules(
        self,
        mocked_resolve_location,
        mocked_build_maps,
        mocked_godown_filter,
    ):
        mocked_godown_filter.return_value.values_list.return_value.first.return_value = "Main Location"
        policy = SimpleNamespace(
            mode="RELAXED",
            allow_negative_stock=True,
            batch_required_for_sales=False,
            expiry_validation_required=False,
            fefo_required=False,
            allow_manual_batch_override=True,
        )
        product = SimpleNamespace(id=10, productname="P-1", is_service=False)

        hint = SalesStockBalanceService.build_hint(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            bill_date=date(2026, 4, 16),
            product=product,
            requested_qty=Decimal("10.0000"),
            batch_number="",
            expiry_date=None,
            location_id=5,
            policy=policy,
        )

        self.assertEqual(hint["status"], "info")
        self.assertEqual(hint["message"], "")
        self.assertIsNone(hint["available_qty"])
        self.assertIsNone(hint["shortage_qty"])
        mocked_build_maps.assert_not_called()
        self.assertTrue(mocked_resolve_location.called)

    @patch("sales.services.sales_stock_balance_service.Godown.objects.filter")
    @patch("sales.services.sales_stock_balance_service.SalesStockBalanceService._best_batch", return_value=None)
    @patch(
        "sales.services.sales_stock_balance_service.SalesStockBalanceService._build_balance_maps",
        return_value=({}, {}, Decimal("3.0000")),
    )
    @patch("sales.services.sales_stock_balance_service.resolve_posting_location_id", return_value=5)
    def test_controlled_mode_returns_warning_for_location_shortage(
        self,
        mocked_resolve_location,
        mocked_build_maps,
        mocked_best_batch,
        mocked_godown_filter,
    ):
        mocked_godown_filter.return_value.values_list.return_value.first.return_value = "Main Location"
        policy = SimpleNamespace(
            mode="CONTROLLED",
            allow_negative_stock=True,
            batch_required_for_sales=False,
            expiry_validation_required=False,
            fefo_required=False,
            allow_manual_batch_override=True,
        )
        product = SimpleNamespace(id=10, productname="P-1", is_service=False)

        hint = SalesStockBalanceService.build_hint(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            bill_date=date(2026, 4, 16),
            product=product,
            requested_qty=Decimal("5.0000"),
            batch_number="",
            expiry_date=None,
            location_id=5,
            policy=policy,
        )

        self.assertEqual(hint["status"], "warning")
        self.assertIn("Only 3.0000 available", hint["message"])
        mocked_build_maps.assert_called_once()
        mocked_best_batch.assert_called_once()
        self.assertTrue(mocked_resolve_location.called)

    @patch("sales.services.sales_stock_balance_service.Godown.objects.filter")
    @patch("sales.services.sales_stock_balance_service.SalesStockBalanceService._best_batch", return_value=None)
    @patch(
        "sales.services.sales_stock_balance_service.SalesStockBalanceService._build_balance_maps",
        return_value=(
            {
                ("EXP-10-20260501", 5): Decimal("2.0000"),
                ("EXP-10-20260601", 5): Decimal("5.0000"),
            },
            {
                ("EXP-10-20260501", 5, date(2026, 5, 1)): Decimal("2.0000"),
                ("EXP-10-20260601", 5, date(2026, 6, 1)): Decimal("5.0000"),
            },
            Decimal("7.0000"),
        ),
    )
    @patch("sales.services.sales_stock_balance_service.resolve_posting_location_id", return_value=5)
    def test_build_hint_uses_internal_expiry_lot_for_expiry_only_products(
        self,
        mocked_resolve_location,
        mocked_build_maps,
        mocked_best_batch,
        mocked_godown_filter,
    ):
        mocked_godown_filter.return_value.values_list.return_value.first.return_value = "Main Location"
        policy = SimpleNamespace(
            mode="CONTROLLED",
            allow_negative_stock=False,
            batch_required_for_sales=False,
            expiry_validation_required=True,
            fefo_required=False,
            allow_manual_batch_override=True,
        )
        product = SimpleNamespace(
            id=10,
            productname="Yogurt",
            is_service=False,
            is_batch_managed=False,
            is_expiry_tracked=True,
        )

        hint = SalesStockBalanceService.build_hint(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            bill_date=date(2026, 4, 16),
            product=product,
            requested_qty=Decimal("4.0000"),
            batch_number="",
            expiry_date=date(2026, 5, 1),
            location_id=5,
            policy=policy,
        )

        self.assertEqual(hint["batch_number"], "EXP-10-20260501")
        self.assertEqual(hint["available_qty"], "2.0000")
        self.assertEqual(hint["shortage_qty"], "2.0000")
        self.assertEqual(hint["status"], "danger")
        self.assertIn("expiry lot", hint["message"].lower())
        mocked_build_maps.assert_called_once()
        mocked_best_batch.assert_called_once()
        self.assertTrue(mocked_resolve_location.called)


class SalesInvoiceViewUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=7)
        self.header = SimpleNamespace(entity_id=1, doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE))

    def _build_request(self, path: str, payload: dict | None = None):
        request = self.factory.post(path, payload or {}, format="json")
        force_authenticate(request, user=self.user)
        return request

    def _build_put_request(self, path: str, payload: dict | None = None):
        request = self.factory.put(path, payload or {}, format="json")
        force_authenticate(request, user=self.user)
        return request

    def _build_patch_request(self, path: str, payload: dict | None = None):
        request = self.factory.patch(path, payload or {}, format="json")
        force_authenticate(request, user=self.user)
        return request

    def _assert_serializer_context(self, mocked_serializer_cls, *, expected_line_mode: str):
        _, serializer_kwargs = mocked_serializer_cls.call_args
        serializer_request = serializer_kwargs["context"]["request"]
        self.assertEqual(serializer_request.method, "POST")
        self.assertEqual(serializer_request.query_params.get("line_mode"), expected_line_mode)
        self.assertEqual(serializer_kwargs["context"]["line_mode"], expected_line_mode)

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    def test_list_queryset_uses_exists_for_line_mode_filter(self, mocked_require_permission):
        request = self.factory.get("/api/sales/invoices/?entity=1&line_mode=goods")
        force_authenticate(request, user=self.user)

        view = SalesInvoiceListCreateAPIView()
        view.request = view.initialize_request(request)

        queryset = view.get_queryset()
        sql = str(queryset.query).upper()

        self.assertIn("EXISTS(", sql)
        self.assertNotIn(" DISTINCT ", sql)

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    def test_list_queryset_selects_customer_related_ledger(self, mocked_require_permission):
        request = self.factory.get("/api/sales/invoices/?entity=1")
        force_authenticate(request, user=self.user)

        view = SalesInvoiceListCreateAPIView()
        view.request = view.initialize_request(request)

        queryset = view.get_queryset()
        select_related = queryset.query.select_related

        self.assertIn("customer", select_related)
        self.assertIn("ledger", select_related["customer"])
        self.assertIn("subentity", select_related)

    def test_nav_scope_queryset_uses_exists_for_line_mode_filter(self):
        queryset = SalesInvoiceNavService._scope_qs(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            doc_code="SI",
            allowed_statuses=SalesInvoiceNavService.DEFAULT_ALLOWED_STATUSES,
            line_mode="goods",
        )
        sql = str(queryset.query).upper()
        self.assertIn("EXISTS(", sql)
        self.assertNotIn(" DISTINCT ", sql)

    def test_last_saved_doc_scope_queryset_uses_subentity_isnull(self):
        with patch("sales.services.sales_settings_service.SalesInvoiceHeader.objects.filter") as mocked_filter:
            mocked_filter.return_value.only.return_value.__iter__.return_value = iter([])

            SalesSettingsService._last_saved_doc_in_scope(
                entity_id=10,
                entityfinid_id=8,
                subentity_id=None,
                doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
                current_number=1008,
            )

        mocked_filter.assert_called_once_with(
            entity_id=10,
            entityfinid_id=8,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            status__in=[2, 3, 9],
            subentity_id__isnull=True,
        )

    @patch("sales.services.sales_nav_service.SalesInvoiceNavService._scope_qs")
    def test_prev_next_orders_by_doc_no_with_id_tiebreaker(self, mocked_scope_qs):
        scoped_qs = MagicMock()
        all_code_rows = [
            SimpleNamespace(id=77, doc_no=1006, invoice_number="SI/2026/1006", status=3, bill_date=None),
            SimpleNamespace(id=88, doc_no=None, invoice_number="SI/2026/1007", status=3, bill_date=None),
            SimpleNamespace(id=95, doc_no=1009, invoice_number="SI/2026/1009", status=3, bill_date=None),
        ]
        mocked_scope_qs.side_effect = [scoped_qs, all_code_rows]
        instance = SimpleNamespace(
            id=90,
            doc_no=1008,
            entity_id=10,
            entityfinid_id=2026,
            subentity_id=None,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            doc_code="SI",
        )

        result = SalesInvoiceNavService.get_prev_next_for_instance(instance, line_mode="service")

        self.assertEqual(result["previous"]["id"], 88)
        self.assertEqual(result["previous"]["invoice_number"], "SI/2026/1007")
        self.assertEqual(result["next"]["id"], 95)

    @patch("sales.services.sales_settings_service.SalesSettingsService._last_saved_doc_in_scope")
    @patch("sales.services.sales_settings_service.DocumentNumberService.peek_preview")
    @patch("sales.services.sales_settings_service.DocumentType.objects.filter")
    def test_get_current_doc_no_falls_back_to_latest_doc_code_when_configured_preview_is_low(
        self,
        mocked_doc_type_filter,
        mocked_peek_preview,
        mocked_last_saved_doc,
    ):
        mocked_doc_type_filter.return_value.only.return_value.first.return_value = SimpleNamespace(id=7)
        latest_doc = SimpleNamespace(
            id=30,
            doc_no=21,
            invoice_number="SDN/2026/21",
            doc_code="SDN",
            status=3,
            bill_date=date(2026, 4, 26),
        )
        previous_doc = SimpleNamespace(
            id=29,
            doc_no=20,
            invoice_number="SDN/2026/20",
            doc_code="SDN",
            status=3,
            bill_date=date(2026, 4, 25),
        )
        mocked_last_saved_doc.side_effect = [latest_doc, previous_doc]

        def _peek(**kwargs):
            if kwargs.get("doc_code") == "WRONG":
                return SimpleNamespace(doc_no=1, display_no="WRONG/1")
            if kwargs.get("doc_code") == "SDN":
                return SimpleNamespace(doc_no=22, display_no="SDN/22")
            raise ValueError("Series not found")

        mocked_peek_preview.side_effect = _peek

        result = SalesSettingsService.get_current_doc_no(
            entity_id=10,
            entityfinid_id=2026,
            subentity_id=None,
            doc_key="sales_debit_note",
            doc_code="WRONG",
        )

        self.assertTrue(result["enabled"])
        self.assertEqual(result["doc_type_id"], 7)
        self.assertEqual(result["current_number"], 22)
        self.assertEqual(result["previous_number"], 20)
        self.assertEqual(result["previous_invoice_id"], 29)
        self.assertEqual(result["previous_invoice_number"], "SDN/2026/20")
        self.assertEqual([call.kwargs.get("doc_code") for call in mocked_peek_preview.call_args_list], ["WRONG", "SDN"])

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.confirm")
    @patch("sales.views.sales_invoice_views.SalesInvoiceHeaderSerializer")
    @patch.object(SalesInvoiceConfirmAPIView, "_get_scoped_header")
    def test_confirm_view_serializes_with_line_mode_context(
        self,
        mocked_get_header,
        mocked_serializer_cls,
        mocked_confirm,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_confirm.return_value = self.header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Confirmed"}

        request = self._build_request("/api/sales/invoices/10/confirm/?line_mode=service")

        response = SalesInvoiceConfirmAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        mocked_require_permission.assert_called_once()
        mocked_confirm.assert_called_once_with(header=self.header, user=self.user)
        self._assert_serializer_context(mocked_serializer_cls, expected_line_mode="service")

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.confirm")
    @patch.object(SalesInvoiceConfirmAPIView, "_get_scoped_header")
    def test_confirm_view_returns_structured_validation_error_payload(
        self,
        mocked_get_header,
        mocked_confirm,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_confirm.side_effect = ValidationError({"customer": ["GSTIN is required."]})

        request = self._build_request("/api/sales/invoices/10/confirm/?line_mode=goods")

        response = SalesInvoiceConfirmAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"customer": ["GSTIN is required."]})
        mocked_require_permission.assert_called_once()

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.post")
    @patch("sales.views.sales_invoice_views.SalesInvoiceHeaderSerializer")
    @patch.object(SalesInvoicePostAPIView, "_get_scoped_header")
    def test_post_view_serializes_with_line_mode_context(
        self,
        mocked_get_header,
        mocked_serializer_cls,
        mocked_post,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_post.return_value = self.header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Posted"}

        request = self._build_request("/api/sales/invoices/10/post/?line_mode=goods")

        response = SalesInvoicePostAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        mocked_require_permission.assert_called_once()
        mocked_post.assert_called_once_with(header=self.header, user=self.user)
        self._assert_serializer_context(mocked_serializer_cls, expected_line_mode="goods")

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.requires_current_period_correction")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.cancel")
    @patch("sales.views.sales_invoice_views.SalesInvoiceHeaderSerializer")
    @patch.object(SalesInvoiceCancelAPIView, "_get_scoped_header")
    def test_cancel_view_requires_credit_note_permissions_for_locked_period_auto_reversal(
        self,
        mocked_get_header,
        mocked_serializer_cls,
        mocked_cancel,
        mocked_requires_correction,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_cancel.return_value = self.header
        mocked_requires_correction.return_value = True
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Posted"}

        request = self._build_request(
            "/api/sales/invoices/10/cancel/?line_mode=service",
            {"reason": "Customer requested cancellation."},
        )

        response = SalesInvoiceCancelAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mocked_require_permission.call_count, 3)
        self.assertEqual(
            mocked_require_permission.call_args_list[0].kwargs,
            {"user": self.user, "entity_id": 1, "doc_type": int(SalesInvoiceHeader.DocType.TAX_INVOICE), "action": "cancel"},
        )
        self.assertEqual(
            mocked_require_permission.call_args_list[1].kwargs,
            {"user": self.user, "entity_id": 1, "doc_type": SalesInvoiceHeader.DocType.CREDIT_NOTE, "action": "create"},
        )
        self.assertEqual(
            mocked_require_permission.call_args_list[2].kwargs,
            {"user": self.user, "entity_id": 1, "doc_type": SalesInvoiceHeader.DocType.CREDIT_NOTE, "action": "post"},
        )
        mocked_cancel.assert_called_once_with(
            header=self.header,
            user=self.user,
            reason="Customer requested cancellation.",
        )
        self._assert_serializer_context(mocked_serializer_cls, expected_line_mode="service")

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.requires_current_period_correction")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.cancel")
    @patch.object(SalesInvoiceCancelAPIView, "_get_scoped_header")
    def test_cancel_view_blocks_locked_period_auto_reversal_without_credit_note_permissions(
        self,
        mocked_get_header,
        mocked_cancel,
        mocked_requires_correction,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_requires_correction.return_value = True
        mocked_require_permission.side_effect = [
            None,
            PermissionDenied({"detail": "Missing permission: sales.credit_note.create"}),
        ]

        request = self._build_request(
            "/api/sales/invoices/10/cancel/",
            {"reason": "Customer requested cancellation."},
        )

        response = SalesInvoiceCancelAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 403)
        mocked_cancel.assert_not_called()

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.cancel")
    @patch("sales.views.sales_invoice_views.SalesInvoiceHeaderSerializer")
    @patch.object(SalesInvoiceCancelAPIView, "_get_scoped_header")
    def test_cancel_view_passes_reason_and_serializes_with_line_mode_context(
        self,
        mocked_get_header,
        mocked_serializer_cls,
        mocked_cancel,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_cancel.return_value = self.header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Cancelled"}

        request = self._build_request(
            "/api/sales/invoices/10/cancel/?line_mode=service",
            {"reason": "Customer requested cancellation."},
        )

        response = SalesInvoiceCancelAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        mocked_require_permission.assert_called_once()
        mocked_cancel.assert_called_once_with(
            header=self.header,
            user=self.user,
            reason="Customer requested cancellation.",
        )
        self._assert_serializer_context(mocked_serializer_cls, expected_line_mode="service")

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.reverse_posting")
    @patch("sales.views.sales_invoice_views.SalesInvoiceHeaderSerializer")
    @patch.object(SalesInvoiceReverseAPIView, "_get_scoped_header")
    def test_reverse_view_passes_reason_and_serializes_with_line_mode_context(
        self,
        mocked_get_header,
        mocked_serializer_cls,
        mocked_reverse,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_reverse.return_value = self.header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Confirmed"}

        request = self._build_request(
            "/api/sales/invoices/10/reverse/?line_mode=goods",
            {"reason": "Posting reversed for correction."},
        )

        response = SalesInvoiceReverseAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        mocked_require_permission.assert_called_once()
        mocked_reverse.assert_called_once_with(
            header=self.header,
            user=self.user,
            reason="Posting reversed for correction.",
        )
        self._assert_serializer_context(mocked_serializer_cls, expected_line_mode="goods")


class SalesComplianceViewUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=7)
        self.header = SimpleNamespace(entity_id=1, id=10, is_eway_applicable=True, entity=SimpleNamespace(id=1))

    def _build_request(self, path: str, payload: dict | None = None):
        request = self.factory.post(path, payload or {}, format="json")
        force_authenticate(request, user=self.user)
        return request

    @patch("sales.views.sales_invoice_compliance_api.SalesInvoiceHeaderSerializer")
    @patch("sales.views.sales_invoice_compliance_api.SalesComplianceService")
    @patch.object(SalesInvoiceGenerateIRNAndEWayAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGenerateIRNAndEWayAPIView, "get_invoice")
    def test_generate_irn_and_eway_view_returns_partial_success_errors_with_resolution(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
        mocked_serializer_cls,
    ):
        mocked_get_invoice.return_value = self.header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Confirmed"}
        mocked_service_cls.return_value.generate_irn.return_value = SimpleNamespace(
            id=21,
            status=2,
            irn="IRN123",
            ack_no="ACK123",
            ack_date="2026-05-23",
        )
        mocked_service_cls.generate_eway.side_effect = ValidationError({
            "message": "Duplicate E-Way request.",
            "code": "EWB_DUP",
            "resolution": "Review transporter details and retry.",
        })

        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/generate-irn-and-eway/",
            {
                "generate_eway": True,
                "distance_km": 120,
                "trans_mode": "1",
                "transporter_id": "05AAACG0904A1ZL",
                "transporter_name": "ABC Logistics",
                "vehicle_no": "MH12AB1234",
                "vehicle_type": "R",
            },
        )

        response = SalesInvoiceGenerateIRNAndEWayAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["ok"])
        self.assertEqual(response.data["workflow_status"], "PARTIAL_SUCCESS")
        self.assertEqual(response.data["eway"]["status"], "FAILED")
        self.assertEqual(response.data["eway"]["errors"][0]["message"], "Duplicate E-Way request.")
        self.assertEqual(
            response.data["eway"]["errors"][0]["resolution"],
            "Review transporter details and retry.",
        )

    @patch("sales.views.sales_invoice_compliance_api.SalesEInvoice.objects")
    @patch("sales.views.sales_invoice_compliance_api.SalesComplianceService")
    @patch.object(SalesInvoiceGenerateIRNAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGenerateIRNAPIView, "get_invoice")
    def test_generate_irn_view_returns_structured_duplicate_error_reason_and_resolution(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
        mocked_einvoice_objects,
    ):
        mocked_get_invoice.return_value = self.header
        mocked_einvoice_objects.filter.return_value.only.return_value.first.return_value = None
        mocked_service_cls.return_value.generate_irn.side_effect = ValidationError({
            "message": "Duplicate IRN",
            "code": "2150",
            "reason": "IRN already exists for this document.",
            "resolution": "Use IRN Details to sync the existing IRN.",
        })

        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/generate-irn/",
            {},
        )

        response = SalesInvoiceGenerateIRNAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["errors"][0]["message"], "Duplicate IRN")
        self.assertEqual(response.data["errors"][0]["code"], "2150")
        self.assertEqual(response.data["errors"][0]["reason"], "IRN already exists for this document.")
        self.assertEqual(
            response.data["errors"][0]["resolution"],
            "Use IRN Details to sync the existing IRN.",
        )

    @patch.object(SalesInvoiceGetIRNDetailsAPIView, "_compliance_summary")
    @patch("sales.views.sales_invoice_compliance_api.SalesInvoiceHeaderSerializer")
    @patch("sales.views.sales_invoice_compliance_api.SalesComplianceService")
    @patch.object(SalesInvoiceGetIRNDetailsAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetIRNDetailsAPIView, "get_invoice")
    def test_get_irn_details_view_returns_refreshed_invoice_and_compliance_state(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
        mocked_serializer_cls,
        mocked_compliance_summary,
    ):
        header = SimpleNamespace(
            entity_id=1,
            id=10,
            status=int(SalesInvoiceHeader.Status.POSTED),
            is_einvoice_applicable=True,
            is_eway_applicable=True,
            einvoice_artifact=SimpleNamespace(status=2, irn="IRN123"),
            eway_artifact=None,
        )
        mocked_get_invoice.return_value = header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Posted"}
        mocked_compliance_summary.return_value = {
            "action_flags": {
                "can_generate_irn": False,
                "can_generate_eway": True,
                "state": {"irn_generated": True, "eway_generated": False, "is_b2c": False},
            }
        }
        mocked_service_cls.return_value.get_irn_details.return_value = {
            "status": "SUCCESS",
            "irn": "IRN123",
            "ack_no": "ACK123",
            "ack_date": "2026-05-23",
            "raw": {"irn": "IRN123"},
        }

        request = self._build_request("/api/sales/sales-invoices/10/compliance/get-irn-details/", {})

        response = SalesInvoiceGetIRNDetailsAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["invoice"]["id"], 10)
        self.assertEqual(response.data["compliance"]["action_flags"]["can_generate_eway"], True)
        self.assertEqual(response.data["irn"], "IRN123")

    @patch.object(SalesInvoiceGetGSTNDetailsAPIView, "_compliance_summary")
    @patch("sales.views.sales_invoice_compliance_api.SalesInvoiceHeaderSerializer")
    @patch("sales.views.sales_invoice_compliance_api.SalesComplianceService")
    @patch.object(SalesInvoiceGetGSTNDetailsAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetGSTNDetailsAPIView, "get_invoice")
    def test_get_gstn_details_view_returns_refreshed_invoice_and_compliance_state(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
        mocked_serializer_cls,
        mocked_compliance_summary,
    ):
        header = SimpleNamespace(
            entity_id=1,
            id=10,
            status=int(SalesInvoiceHeader.Status.POSTED),
            is_einvoice_applicable=True,
            is_eway_applicable=True,
            einvoice_artifact=SimpleNamespace(status=2, irn="IRN123"),
            eway_artifact=None,
        )
        mocked_get_invoice.return_value = header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Posted"}
        mocked_compliance_summary.return_value = {
            "action_flags": {
                "can_get_gstn_details": True,
                "state": {"einvoice_applicable": True, "is_b2c": False},
            }
        }
        mocked_service_cls.return_value.get_gstn_details.return_value = {
            "status": "SUCCESS",
            "gstin": "03ABCDE1234F1Z5",
            "legal_name": "Acme Pvt Ltd",
            "trade_name": "Acme",
            "registration_status": "Active",
            "raw": {"gstin": "03ABCDE1234F1Z5"},
        }

        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-gstn-details/",
            {"gstin": "03ABCDE1234F1Z5"},
        )

        response = SalesInvoiceGetGSTNDetailsAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["invoice"]["id"], 10)
        self.assertEqual(response.data["compliance"]["action_flags"]["can_get_gstn_details"], True)
        self.assertEqual(response.data["gstin"], "03ABCDE1234F1Z5")

    @patch.object(SalesInvoiceSyncGSTINFromCPAPIView, "_compliance_summary")
    @patch("sales.views.sales_invoice_compliance_api.SalesInvoiceHeaderSerializer")
    @patch("sales.views.sales_invoice_compliance_api.SalesComplianceService")
    @patch.object(SalesInvoiceSyncGSTINFromCPAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceSyncGSTINFromCPAPIView, "get_invoice")
    def test_sync_gstin_from_cp_view_returns_refreshed_invoice_and_compliance_state(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
        mocked_serializer_cls,
        mocked_compliance_summary,
    ):
        header = SimpleNamespace(
            entity_id=1,
            id=10,
            status=int(SalesInvoiceHeader.Status.POSTED),
            is_einvoice_applicable=True,
            is_eway_applicable=True,
            einvoice_artifact=SimpleNamespace(status=2, irn="IRN123"),
            eway_artifact=None,
        )
        mocked_get_invoice.return_value = header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Posted"}
        mocked_compliance_summary.return_value = {
            "action_flags": {
                "can_get_gstn_details": True,
                "state": {"einvoice_applicable": True, "is_b2c": False},
            }
        }
        mocked_service_cls.return_value.sync_gstin_from_cp.return_value = {
            "status": "SUCCESS",
            "gstin": "03ABCDE1234F1Z5",
            "legal_name": "Acme Pvt Ltd",
            "trade_name": "Acme",
            "registration_status": "Active",
            "raw": {"gstin": "03ABCDE1234F1Z5"},
        }

        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/sync-gstin-from-cp/",
            {"gstin": "03ABCDE1234F1Z5"},
        )

        response = SalesInvoiceSyncGSTINFromCPAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["invoice"]["id"], 10)
        self.assertEqual(response.data["gstin"], "03ABCDE1234F1Z5")

    @patch.object(SalesInvoiceGetB2CQRCodeAPIView, "_compliance_summary")
    @patch("sales.views.sales_invoice_compliance_api.SalesInvoiceHeaderSerializer")
    @patch("sales.views.sales_invoice_compliance_api.SalesComplianceService")
    @patch.object(SalesInvoiceGetB2CQRCodeAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetB2CQRCodeAPIView, "get_invoice")
    def test_get_b2c_qrcode_view_returns_refreshed_invoice_and_compliance_state(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
        mocked_serializer_cls,
        mocked_compliance_summary,
    ):
        header = SimpleNamespace(
            entity_id=1,
            id=10,
            status=int(SalesInvoiceHeader.Status.POSTED),
            is_einvoice_applicable=False,
            is_eway_applicable=True,
            einvoice_artifact=SimpleNamespace(status=1, signed_qr_code=None),
            eway_artifact=None,
        )
        mocked_get_invoice.return_value = header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Posted"}
        mocked_compliance_summary.return_value = {
            "action_flags": {
                "can_get_b2c_qrcode": True,
                "state": {"is_b2c": True},
            }
        }
        mocked_service_cls.return_value.get_b2c_qrcode.return_value = {
            "status": "SUCCESS",
            "qr_code": "base64-qr",
            "raw": {"qrCode": "base64-qr"},
        }

        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-b2c-qrcode/",
            {"upiid": "merchant@upi"},
        )

        response = SalesInvoiceGetB2CQRCodeAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["invoice"]["id"], 10)
        self.assertEqual(response.data["qr_code"], "base64-qr")

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceGetEWayDetailsAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetEWayDetailsAPIView, "_fetch_invoice_with_related")
    def test_get_eway_details_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.get_eway_details.return_value = {
            "status": "SUCCESS",
            "ewb_no": "171001234567",
            "valid_upto": "2026-06-19",
            "raw": {"ewayBillNo": "171001234567"},
        }

        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-eway-details/",
            {"ewb_no": "171001234567"},
        )

        response = SalesInvoiceGetEWayDetailsAPIView.as_view()(request, id=10)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["ewb_no"], "171001234567")

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceGetEWayTransporterDetailsAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetEWayTransporterDetailsAPIView, "_fetch_invoice_with_related")
    def test_get_eway_transporter_details_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.get_eway_transporter_details.return_value = {
            "status": "SUCCESS",
            "data": {"transporterId": "03TRANS1234A1Z5"},
            "raw": {"transporterId": "03TRANS1234A1Z5"},
        }
        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-eway-transporter-details/",
            {"transporter_id": "03TRANS1234A1Z5"},
        )
        response = SalesInvoiceGetEWayTransporterDetailsAPIView.as_view()(request, id=10)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"]["transporterId"], "03TRANS1234A1Z5")

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceGetEWayGSTINDetailsAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetEWayGSTINDetailsAPIView, "_fetch_invoice_with_related")
    def test_get_eway_gstin_details_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.get_eway_gstin_details.return_value = {
            "status": "SUCCESS",
            "data": {"Gstin": "03ABCDE1234F1Z5"},
            "raw": {"Gstin": "03ABCDE1234F1Z5"},
        }
        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-eway-gstin-details/",
            {"gstin": "03ABCDE1234F1Z5"},
        )
        response = SalesInvoiceGetEWayGSTINDetailsAPIView.as_view()(request, id=10)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"]["Gstin"], "03ABCDE1234F1Z5")

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceGetEWayHSNDetailsAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetEWayHSNDetailsAPIView, "_fetch_invoice_with_related")
    def test_get_eway_hsn_details_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.get_eway_hsn_details.return_value = {
            "status": "SUCCESS",
            "data": {"hsnCode": "9983"},
            "raw": {"hsnCode": "9983"},
        }
        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-eway-hsn-details/",
            {"hsn_code": "9983"},
        )
        response = SalesInvoiceGetEWayHSNDetailsAPIView.as_view()(request, id=10)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"]["hsnCode"], "9983")

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceGetEWayErrorListAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetEWayErrorListAPIView, "_fetch_invoice_with_related")
    def test_get_eway_error_list_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.get_eway_error_list.return_value = {
            "status": "SUCCESS",
            "data": [{"code": "1001"}],
            "raw": {"data": [{"code": "1001"}]},
        }
        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-eway-error-list/",
            {},
        )
        response = SalesInvoiceGetEWayErrorListAPIView.as_view()(request, id=10)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"][0]["code"], "1001")

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceRejectEWayAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceRejectEWayAPIView, "_fetch_invoice_with_related")
    def test_reject_eway_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.reject_eway.return_value = {
            "status": "SUCCESS",
            "data": "Rejected",
            "raw": {"data": "Rejected"},
        }
        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/reject-eway/",
            {"ewb_no": "171001234567"},
        )
        response = SalesInvoiceRejectEWayAPIView.as_view()(request, id=10)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceGetTripSheetAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetTripSheetAPIView, "_fetch_invoice_with_related")
    def test_get_trip_sheet_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.get_trip_sheet.return_value = {
            "status": "SUCCESS",
            "data": {"tripSheetNo": "TS123"},
            "raw": {"tripSheetNo": "TS123"},
        }
        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-trip-sheet/",
            {"trip_sheet_no": "TS123"},
        )
        response = SalesInvoiceGetTripSheetAPIView.as_view()(request, id=10)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"]["tripSheetNo"], "TS123")

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceGetEWayByDocumentAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetEWayByDocumentAPIView, "_fetch_invoice_with_related")
    def test_get_eway_by_document_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.get_eway_by_document.return_value = {
            "status": "SUCCESS",
            "data": {"ewayBillNo": "171001234567"},
            "raw": {"ewayBillNo": "171001234567"},
        }
        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-eway-by-document/",
            {},
        )
        response = SalesInvoiceGetEWayByDocumentAPIView.as_view()(request, id=10)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"]["ewayBillNo"], "171001234567")

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceGetEWayBillsForTransporterAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetEWayBillsForTransporterAPIView, "_fetch_invoice_with_related")
    def test_get_eway_bills_for_transporter_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.get_eway_bills_for_transporter.return_value = {
            "status": "SUCCESS",
            "data": [{"ewayBillNo": "171001234567"}],
            "raw": {"data": [{"ewayBillNo": "171001234567"}]},
        }
        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-eway-bills-for-transporter/",
            {"date": "2026-06-18"},
        )
        response = SalesInvoiceGetEWayBillsForTransporterAPIView.as_view()(request, id=10)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"][0]["ewayBillNo"], "171001234567")

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceGetEWayBillReportByTransporterAssignedDateAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetEWayBillReportByTransporterAssignedDateAPIView, "_fetch_invoice_with_related")
    def test_get_eway_bill_report_by_transporter_assigned_date_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.get_eway_bill_report_by_transporter_assigned_date.return_value = {
            "status": "SUCCESS",
            "data": [{"ewayBillNo": "171001234567"}],
            "raw": {"data": [{"ewayBillNo": "171001234567"}]},
        }
        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-eway-bill-report-by-transporter-assigned-date/",
            {"date": "2026-06-18", "state_code": "03"},
        )
        response = SalesInvoiceGetEWayBillReportByTransporterAssignedDateAPIView.as_view()(request, id=10)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"][0]["ewayBillNo"], "171001234567")

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceGetEWayBillsForTransporterByGSTINAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetEWayBillsForTransporterByGSTINAPIView, "_fetch_invoice_with_related")
    def test_get_eway_bills_for_transporter_by_gstin_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.get_eway_bills_for_transporter_by_gstin.return_value = {
            "status": "SUCCESS",
            "data": [{"ewayBillNo": "171001234567"}],
            "raw": {"data": [{"ewayBillNo": "171001234567"}]},
        }
        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-eway-bills-for-transporter-by-gstin/",
            {"gen_gstin": "03AAAAA0000A1Z5", "date": "2026-06-18"},
        )
        response = SalesInvoiceGetEWayBillsForTransporterByGSTINAPIView.as_view()(request, id=10)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"][0]["ewayBillNo"], "171001234567")

    @patch("sales.views.eway_views.SalesComplianceService")
    @patch.object(SalesInvoiceGenerateConsolidatedEWayAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGenerateConsolidatedEWayAPIView, "_fetch_invoice_with_related")
    def test_generate_consolidated_eway_view_returns_lookup_result(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
    ):
        header = SimpleNamespace(entity_id=1, id=10)
        mocked_get_invoice.return_value = header
        mocked_service_cls.return_value.generate_consolidated_eway.return_value = {
            "status": "SUCCESS",
            "data": {"tripSheetNo": "TS123"},
            "raw": {"tripSheetNo": "TS123"},
        }
        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/generate-consolidated-eway/",
            {"from_place": "Sirhind", "from_state_code": 3, "trans_mode": "1", "eway_bill_numbers": [{"ewb_no": 171001234567}]},
        )
        response = SalesInvoiceGenerateConsolidatedEWayAPIView.as_view()(request, id=10)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])

    @patch.object(SalesInvoiceGetIRNByDocDetailsAPIView, "_compliance_summary")
    @patch("sales.views.sales_invoice_compliance_api.SalesInvoiceHeaderSerializer")
    @patch("sales.views.sales_invoice_compliance_api.SalesComplianceService")
    @patch.object(SalesInvoiceGetIRNByDocDetailsAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetIRNByDocDetailsAPIView, "get_invoice")
    def test_get_irn_details_by_doc_view_returns_refreshed_invoice_and_compliance_state(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
        mocked_serializer_cls,
        mocked_compliance_summary,
    ):
        header = SimpleNamespace(
            entity_id=1,
            id=10,
            status=int(SalesInvoiceHeader.Status.POSTED),
            is_einvoice_applicable=True,
            is_eway_applicable=True,
            einvoice_artifact=SimpleNamespace(status=2, irn="IRN123"),
            eway_artifact=None,
        )
        mocked_get_invoice.return_value = header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Posted"}
        mocked_compliance_summary.return_value = {
            "action_flags": {
                "can_get_irn_details": True,
                "state": {"einvoice_applicable": True, "is_b2c": False},
            }
        }
        mocked_service_cls.return_value.get_irn_details_by_doc.return_value = {
            "status": "SUCCESS",
            "irn": "IRN123",
            "ack_no": "ACK123",
            "ack_date": "2026-06-18",
            "raw": {"irn": "IRN123"},
        }

        request = self._build_request(
            "/api/sales/sales-invoices/10/compliance/get-irn-details-by-doc/",
            {"doc_type": "INV", "doc_number": "SINV/1", "doc_date": "2026-06-18"},
        )

        response = SalesInvoiceGetIRNByDocDetailsAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["invoice"]["id"], 10)
        self.assertEqual(response.data["irn"], "IRN123")

    @patch.object(SalesInvoiceGetEWayByIRNAPIView, "_compliance_summary")
    @patch("sales.views.sales_invoice_compliance_api.SalesInvoiceHeaderSerializer")
    @patch("sales.views.sales_invoice_compliance_api.SalesComplianceService")
    @patch.object(SalesInvoiceGetEWayByIRNAPIView, "_require_any_permission")
    @patch.object(SalesInvoiceGetEWayByIRNAPIView, "get_invoice")
    def test_get_eway_by_irn_view_returns_refreshed_invoice_and_compliance_state(
        self,
        mocked_get_invoice,
        mocked_require_permission,
        mocked_service_cls,
        mocked_serializer_cls,
        mocked_compliance_summary,
    ):
        header = SimpleNamespace(
            entity_id=1,
            id=10,
            status=int(SalesInvoiceHeader.Status.POSTED),
            is_einvoice_applicable=True,
            is_eway_applicable=True,
            einvoice_artifact=SimpleNamespace(status=2, irn="IRN123"),
            eway_artifact=SimpleNamespace(status=2, ewb_no="171001234567"),
        )
        mocked_get_invoice.return_value = header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Posted"}
        mocked_compliance_summary.return_value = {
            "action_flags": {
                "can_cancel_irn": False,
                "can_cancel_eway": True,
                "can_update_eway_vehicle": True,
                "state": {"irn_generated": True, "eway_generated": True, "is_b2c": False},
            }
        }
        mocked_service_cls.return_value.get_eway_details_by_irn.return_value = {
            "status": "SUCCESS",
            "irn": "IRN123",
            "ewb_no": "171001234567",
            "valid_upto": "2026-05-24",
            "raw": {"ewb_no": "171001234567"},
        }

        request = self._build_request("/api/sales/sales-invoices/10/compliance/get-eway-by-irn/", {})

        response = SalesInvoiceGetEWayByIRNAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["invoice"]["id"], 10)
        self.assertEqual(response.data["compliance"]["action_flags"]["can_cancel_eway"], True)
        self.assertEqual(response.data["ewb_no"], "171001234567")


class SalesComplianceRecoveryUnitTests(SalesInvoiceViewUnitTests):
    databases = {"default"}
    def test_ensure_compliance_serializer_accepts_null_optional_transport_fields(self):
        serializer = EnsureComplianceActionSerializer(
            data={
                "distance_km": None,
                "trans_mode": None,
                "transport_mode": None,
                "transporter_id": None,
                "transporter_name": None,
                "trans_doc_no": None,
                "trans_doc_date": None,
                "doc_type": None,
                "vehicle_no": None,
                "vehicle_type": None,
                "disp_dtls": None,
                "exp_ship_dtls": None,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_generate_irn_and_eway_serializer_ignores_null_optional_flat_fields_when_eway_disabled(self):
        serializer = GenerateIRNAndEWayActionSerializer(
            data={
                "generate_eway": False,
                "distance_km": None,
                "trans_mode": None,
                "transporter_id": None,
                "transporter_name": None,
                "trans_doc_no": None,
                "trans_doc_date": None,
                "vehicle_no": None,
                "vehicle_type": None,
                "disp_dtls": None,
                "exp_ship_dtls": None,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["eway"], {})

    def test_extend_eway_validity_serializer_accepts_whitebooks_aliases(self):
        serializer = ExtendEWayValidityActionSerializer(
            data={
                "extnRsnCode": "1",
                "extnRemarks": "Route blocked",
                "fromPlace": "Sirhind",
                "fromPincode": 140406,
                "fromState": 3,
                "remainingDistance": 120,
                "transDocNo": "LR-22",
                "transDocDate": "2026-06-18",
                "transMode": "1",
                "vehicleNo": "PB10AB1234",
                "consignmentStatus": "M",
                "transitType": "R",
                "addressLine1": "Warehouse 1",
                "addressLine2": "Industrial Area",
                "addressLine3": "Punjab",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["reason_code"], "1")
        self.assertEqual(serializer.validated_data["remarks"], "Route blocked")
        self.assertEqual(serializer.validated_data["from_pincode"], 140406)
        self.assertEqual(serializer.validated_data["consignment_status"], "M")
        self.assertEqual(serializer.validated_data["transit_type"], "R")
        self.assertEqual(serializer.validated_data["address_line1"], "Warehouse 1")

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.MasterGSTClient")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._get_mastergst_cred_for_entity")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_eway_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_extend_eway_validity_uses_whitebooks_extension_payload_contract(
        self,
        mocked_assert_allowed,
        mocked_ensure_eway,
        mocked_get_cred,
        mocked_client_cls,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        save_spy = MagicMock()
        eway = SimpleNamespace(
            ewb_no="171001234567",
            valid_upto=None,
            last_response_json={},
            save=save_spy,
        )
        mocked_ensure_eway.return_value = eway
        mocked_get_cred.return_value = SimpleNamespace()
        mocked_client = mocked_client_cls.return_value
        mocked_client.extend_eway_validity.return_value = {
            "status_cd": "1",
            "data": {"validUpto": "2026-06-20 10:00:00"},
        }

        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.extend_eway_validity(
            req={
                "reason_code": "1",
                "remarks": "Route blocked",
                "from_place": "Sirhind",
                "from_pincode": 140406,
                "from_state_code": 3,
                "remaining_distance_km": 120,
                "trans_doc_no": "LR-22",
                "trans_doc_date": date(2026, 6, 18),
                "trans_mode": "1",
                "vehicle_no": "PB10AB1234",
                "vehicle_type": "R",
                "consignment_status": "M",
                "transit_type": "R",
                "address_line1": "Warehouse 1",
                "address_line2": "Industrial Area",
                "address_line3": "Punjab",
            }
        )

        self.assertEqual(result["status"], "SUCCESS")
        mocked_client.extend_eway_validity.assert_called_once()
        payload = mocked_client.extend_eway_validity.call_args.args[0]
        self.assertEqual(payload["ewbNo"], "171001234567")
        self.assertEqual(payload["extnRsnCode"], "1")
        self.assertEqual(payload["extnRemarks"], "Route blocked")
        self.assertEqual(payload["fromPincode"], 140406)
        self.assertEqual(payload["transDocDate"], "18/06/2026")
        self.assertEqual(payload["consignmentStatus"], "M")
        self.assertEqual(payload["transitType"], "R")
        self.assertNotIn("reasonCode", payload)
        self.assertNotIn("reasonRem", payload)
        save_spy.assert_called()
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.open_exception")
    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.MasterGSTClient")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._get_mastergst_cred_for_entity")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._get_irn", return_value="IRN123")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_invoice_eligible_for_eway")
    @patch("sales.services.sales_compliance_service.SalesEWayBill.objects")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_generate_eway_repairs_stale_saved_ship_to_details_before_provider_call(
        self,
        mocked_assert_allowed,
        mocked_eway_objects,
        mocked_ensure_eligible,
        mocked_get_irn,
        mocked_get_cred,
        mocked_client_cls,
        mocked_log_action,
        mocked_open_exception,
    ):
        invoice = SimpleNamespace(
            id=65,
            entity=SimpleNamespace(id=10),
            customer_gstin="27AWGPV7107B1Z1",
            bill_to_state_code="",
            bill_to_address1="45366",
            bill_to_address2="",
            bill_to_city="Bengaluru",
            bill_to_pincode="560001",
            shipto_snapshot=SimpleNamespace(
                address1="45366",
                address2="",
                city="Bengaluru",
                pincode="560001",
                state_code="",
                gstin="29AWGPV7107B1Z1",
            ),
        )
        art = SimpleNamespace(
            status=0,
            ewb_no=None,
            attempt_count=5,
            last_response_json={},
            last_request_json=None,
            distance_km=None,
            transport_mode=None,
            transporter_id=None,
            transporter_name=None,
            doc_no=None,
            doc_date=None,
            vehicle_no=None,
            vehicle_type=None,
            disp_dtls_json={
                "Nm": "Arnika",
                "Addr1": "4368 GT Road",
                "Addr2": "sirhind",
                "Loc": "Bengaluru",
                "Pin": 560001,
                "Stcd": "29",
            },
            exp_ship_dtls_json={
                "Addr1": "45366",
                "Loc": "Bengaluru",
                "Pin": 560001,
                "Stcd": "00",
            },
            save=MagicMock(),
        )
        mocked_eway_objects.select_for_update.return_value.get_or_create.return_value = (art, False)
        mocked_get_cred.return_value = SimpleNamespace(environment=1, gstin="29AAGCB1286Q000")
        mocked_client = mocked_client_cls.return_value
        mocked_client.generate_ewaybill.return_value = {
            "status_cd": "0",
            "status_desc": '[{"ErrorCode":"5002","ErrorMessage":"The Ship TO GSTIN field is required."}]',
        }

        result = SalesComplianceService.generate_eway(
            invoice,
            invoice.entity,
            {
                "distance_km": 3,
                "trans_mode": "1",
                "transporter_id": "12AWGPV7107B1Z1",
                "transporter_name": "avccd",
                "vehicle_no": "KA123456",
                "vehicle_type": "R",
            },
        )

        self.assertEqual(result["status"], "FAILED")
        payload = mocked_client.generate_ewaybill.call_args.args[0]
        self.assertEqual(payload["ExpShipDtls"]["Gstin"], "29AWGPV7107B1Z1")
        self.assertEqual(payload["ExpShipDtls"]["Stcd"], "29")
        self.assertEqual(art.exp_ship_dtls_json["Gstin"], "29AWGPV7107B1Z1")
        self.assertEqual(art.exp_ship_dtls_json["Stcd"], "29")
        self.assertEqual(art.eway_source, SalesEWaySource.IRN)
        self.assertEqual(art.provider_name, "whitebooks")
        self.assertEqual(art.provider_environment, 1)
        self.assertEqual(art.credential_gstin, "29AAGCB1286Q000")
        art.save.assert_called()
        mocked_log_action.assert_called_once()
        mocked_open_exception.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.open_exception")
    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.MasterGSTClient")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._get_mastergst_cred_for_entity")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._get_irn", return_value="IRN123")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_invoice_eligible_for_eway")
    @patch("sales.services.sales_compliance_service.SalesEWayBill.objects")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_generate_eway_omits_ship_to_block_when_ship_gstin_matches_buyer(
        self,
        mocked_assert_allowed,
        mocked_eway_objects,
        mocked_ensure_eligible,
        mocked_get_irn,
        mocked_get_cred,
        mocked_client_cls,
        mocked_log_action,
        mocked_open_exception,
    ):
        invoice = SimpleNamespace(
            id=65,
            entity=SimpleNamespace(id=10),
            customer_gstin="29AWGPV7107B1Z1",
            bill_to_state_code="",
            bill_to_address1="45366",
            bill_to_address2="",
            bill_to_city="Bengaluru",
            bill_to_pincode="560001",
            shipto_snapshot=SimpleNamespace(
                address1="45366",
                address2="",
                city="Bengaluru",
                pincode="560001",
                state_code="",
                gstin=None,
            ),
        )
        art = SimpleNamespace(
            status=0,
            ewb_no=None,
            attempt_count=7,
            last_response_json={},
            last_request_json=None,
            distance_km=None,
            transport_mode=None,
            transporter_id=None,
            transporter_name=None,
            doc_no=None,
            doc_date=None,
            vehicle_no=None,
            vehicle_type=None,
            disp_dtls_json={
                "Nm": "Arnika",
                "Addr1": "4368 GT Road",
                "Addr2": "sirhind",
                "Loc": "Bengaluru",
                "Pin": 560001,
                "Stcd": "29",
            },
            exp_ship_dtls_json={
                "Addr1": "45366",
                "Loc": "Bengaluru",
                "Pin": 560001,
                "Stcd": "00",
            },
            save=MagicMock(),
        )
        mocked_eway_objects.select_for_update.return_value.get_or_create.return_value = (art, False)
        mocked_get_cred.return_value = SimpleNamespace(environment=1, gstin="29AAGCB1286Q000")
        mocked_client = mocked_client_cls.return_value
        mocked_client.generate_ewaybill.return_value = {
            "status_cd": "0",
            "status_desc": '[{"ErrorCode":"4073","ErrorMessage":"Buyer  GSTIN and Ship TO GSTIN should not be same"}]',
        }

        result = SalesComplianceService.generate_eway(
            invoice,
            invoice.entity,
            {
                "distance_km": 3,
                "trans_mode": "1",
                "transporter_id": "12AWGPV7107B1Z1",
                "transporter_name": "avccd",
                "vehicle_no": "KA123456",
                "vehicle_type": "R",
            },
        )

        self.assertEqual(result["status"], "FAILED")
        payload = mocked_client.generate_ewaybill.call_args.args[0]
        self.assertNotIn("ExpShipDtls", payload)
        self.assertIsNone(art.exp_ship_dtls_json)
        self.assertEqual(art.eway_source, SalesEWaySource.IRN)
        self.assertEqual(art.provider_name, "whitebooks")
        art.save.assert_called()
        mocked_log_action.assert_called_once()
        mocked_open_exception.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.resolve_exception")
    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_einvoice")
    @patch("sales.services.sales_compliance_service.buyer_from_account", return_value={"BuyerDtls": "ok"})
    @patch("sales.services.sales_compliance_service.seller_from_entity", return_value={"SellerDtls": "ok"})
    @patch("sales.services.sales_compliance_service.IRPPayloadBuilder")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._einvoice_min_hsn_digits", return_value=6)
    @patch("sales.services.sales_compliance_service.SalesComplianceService._get_mastergst_cred_for_entity")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_eway_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_einvoice_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._buyer_account")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._assert_confirmed_for_irn")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_generate_irn_syncs_eway_artifact_and_provenance_when_irp_returns_eway_details(
        self,
        mocked_assert_allowed,
        mocked_assert_confirmed,
        mocked_buyer_account,
        mocked_ensure_einv,
        mocked_ensure_eway,
        mocked_get_cred,
        mocked_min_hsn_digits,
        mocked_builder_cls,
        mocked_seller_from_entity,
        mocked_buyer_from_account,
        mocked_get_provider,
        mocked_log_action,
        mocked_resolve_exception,
    ):
        invoice = SimpleNamespace(
            id=10,
            entity=SimpleNamespace(id=1),
            entity_id=1,
            subentity_id=None,
            entityfinid_id=None,
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            place_of_supply_state_code="03",
        )
        user = SimpleNamespace(id=7)
        einv = SimpleNamespace(
            status=0,
            irn=None,
            ack_no=None,
            ack_date=None,
            signed_invoice=None,
            signed_qr_code=None,
            ewb_no=None,
            ewb_date=None,
            ewb_valid_upto=None,
            attempt_count=0,
            last_attempt_at=None,
            last_success_at=None,
            last_request_json=None,
            last_response_json=None,
            last_error_code=None,
            last_error_message=None,
            updated_by=None,
            save=MagicMock(),
        )
        ewb = SimpleNamespace(
            ewb_no=None,
            ewb_date=None,
            valid_upto=None,
            status=0,
            last_response_json=None,
            last_error_code=None,
            last_error_message=None,
            updated_by=None,
            save=MagicMock(),
        )
        mocked_ensure_einv.return_value = einv
        mocked_ensure_eway.return_value = ewb
        mocked_get_cred.return_value = SimpleNamespace(environment=1, gstin="29AAGCB1286Q000")
        mocked_builder_cls.return_value.build.return_value = {"Version": "1.1", "ItemList": [], "ValDtls": {}}
        mocked_get_provider.return_value.generate_irn.return_value = SimpleNamespace(
            ok=True,
            irn="IRN123",
            ack_no="ACK123",
            ack_date="2026-06-18 10:00:00",
            signed_invoice="signed",
            signed_qr_code="qr",
            ewb_no="171001234567",
            ewb_date="2026-06-18 10:05:00",
            ewb_valid_upto="2026-06-19 10:05:00",
            raw={"irn": "IRN123", "ewb_no": "171001234567"},
        )

        svc = SalesComplianceService(invoice=invoice, user=user)

        result = svc.generate_irn()

        self.assertIs(result, einv)
        self.assertEqual(einv.provider_name, "whitebooks")
        self.assertEqual(einv.provider_environment, 1)
        self.assertEqual(einv.credential_gstin, "29AAGCB1286Q000")
        self.assertEqual(ewb.eway_source, SalesEWaySource.IRN)
        self.assertEqual(ewb.provider_name, "whitebooks")
        self.assertEqual(ewb.provider_environment, 1)
        self.assertEqual(ewb.credential_gstin, "29AAGCB1286Q000")
        self.assertEqual(ewb.ewb_no, "171001234567")
        self.assertEqual(ewb.status, 2)
        einv.save.assert_called()
        ewb.save.assert_called()
        mocked_log_action.assert_called_once()
        mocked_resolve_exception.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.resolve_exception")
    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._get_mastergst_cred_for_entity")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_einvoice")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_einvoice_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_irn_details_success_clears_stale_error_fields(
        self,
        mocked_assert_allowed,
        mocked_ensure_einv,
        mocked_get_provider,
        mocked_get_cred,
        mocked_log_action,
        mocked_resolve_exception,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        save_spy = MagicMock()
        einv = SimpleNamespace(
            irn="IRN123",
            ack_no=None,
            ack_date=None,
            signed_invoice=None,
            signed_qr_code=None,
            ewb_no=None,
            ewb_date=None,
            ewb_valid_upto=None,
            last_response_json={},
            last_error_code="2150",
            last_error_message="Duplicate IRN",
            status=0,
            last_success_at=None,
            updated_by=None,
            save=save_spy,
        )
        mocked_ensure_einv.return_value = einv
        mocked_get_cred.return_value = SimpleNamespace(environment=1, gstin="29AAGCB1286Q000")
        mocked_get_provider.return_value.get_irn_details.return_value = SimpleNamespace(
            ok=True,
            irn="IRN123",
            ack_no="ACK123",
            ack_date="2026-05-23 10:00:00",
            signed_invoice=None,
            signed_qr_code=None,
            ewb_no=None,
            ewb_date=None,
            ewb_valid_upto=None,
            raw={"irn": "IRN123"},
        )

        svc = SalesComplianceService(invoice=invoice, user=user)

        result = svc.get_irn_details()

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(einv.last_error_code, None)
        self.assertEqual(einv.last_error_message, None)
        self.assertEqual(einv.irn, "IRN123")
        self.assertEqual(einv.provider_name, "whitebooks")
        self.assertEqual(einv.provider_environment, 1)
        self.assertEqual(einv.credential_gstin, "29AAGCB1286Q000")
        save_spy.assert_called()
        mocked_resolve_exception.assert_called_once_with(
            invoice=invoice,
            exception_type="IRN_GENERATION_FAILED",
            user=user,
        )

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_einvoice")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_gstn_details_returns_normalized_provider_result(
        self,
        mocked_assert_allowed,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_get_provider.return_value.get_gstn_details.return_value = SimpleNamespace(
            ok=True,
            gstin="03ABCDE1234F1Z5",
            legal_name="Acme Pvt Ltd",
            trade_name="Acme",
            status="Active",
            raw={"gstin": "03ABCDE1234F1Z5"},
        )

        svc = SalesComplianceService(invoice=invoice, user=user)

        result = svc.get_gstn_details(gstin="03abcde1234f1z5")

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["gstin"], "03ABCDE1234F1Z5")
        self.assertEqual(result["legal_name"], "Acme Pvt Ltd")
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_einvoice")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_sync_gstin_from_cp_returns_normalized_provider_result(
        self,
        mocked_assert_allowed,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_get_provider.return_value.sync_gstin_from_cp.return_value = SimpleNamespace(
            ok=True,
            gstin="03ABCDE1234F1Z5",
            legal_name="Acme Pvt Ltd",
            trade_name="Acme",
            status="Active",
            raw={"gstin": "03ABCDE1234F1Z5"},
        )

        svc = SalesComplianceService(invoice=invoice, user=user)

        result = svc.sync_gstin_from_cp(gstin="03abcde1234f1z5")

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["gstin"], "03ABCDE1234F1Z5")
        self.assertEqual(result["legal_name"], "Acme Pvt Ltd")
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.entity_primary_gstin", return_value="03AAAAA0000A1Z5")
    @patch("sales.services.sales_compliance_service.entity_primary_contact")
    @patch("sales.services.sales_compliance_service.entity_primary_bank_account")
    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_einvoice")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_einvoice_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_b2c_qrcode_uses_invoice_and_entity_defaults(
        self,
        mocked_assert_allowed,
        mocked_ensure_einv,
        mocked_get_provider,
        mocked_log_action,
        mocked_bank,
        mocked_contact,
        mocked_entity_gstin,
    ):
        invoice = SimpleNamespace(
            id=10,
            entity=SimpleNamespace(legalname="Acme Pvt Ltd", entityname="Acme"),
            seller_gstin="",
            invoice_number="SINV/1",
            doc_no=1,
            bill_date=date(2026, 6, 18),
            grand_total=Decimal("1180.00"),
            total_igst=Decimal("0.00"),
            total_cgst=Decimal("90.00"),
            total_sgst=Decimal("90.00"),
            total_cess=Decimal("0.00"),
        )
        user = SimpleNamespace(id=7)
        save_spy = MagicMock()
        einv = SimpleNamespace(
            signed_qr_code=None,
            last_response_json=None,
            last_error_code="OLD",
            last_error_message="Old error",
            updated_by=None,
            save=save_spy,
        )
        mocked_ensure_einv.return_value = einv
        mocked_bank.return_value = SimpleNamespace(account_number="1234567890", ifsc_code="HDFC0001234")
        mocked_contact.return_value = None
        mocked_get_provider.return_value.get_b2c_qrcode.return_value = SimpleNamespace(
            ok=True,
            qr_code="base64-qr",
            raw={"qrCode": "base64-qr"},
        )

        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.get_b2c_qrcode()

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["qr_code"], "base64-qr")
        self.assertEqual(einv.signed_qr_code, "base64-qr")
        mocked_get_provider.return_value.get_b2c_qrcode.assert_called_once()
        called_payload = mocked_get_provider.return_value.get_b2c_qrcode.call_args.kwargs["payload"]
        self.assertEqual(called_payload["sgstin"], "03AAAAA0000A1Z5")
        self.assertEqual(called_payload["docno"], "SINV/1")
        self.assertEqual(called_payload["docdate"], "18-06-2026")
        self.assertEqual(called_payload["bankaccno"], "1234567890")
        self.assertEqual(called_payload["cgstamount"], "90.00")
        save_spy.assert_called()
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.resolve_exception")
    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_eway_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_eway_details_uses_existing_artifact_number_when_request_omits_value(
        self,
        mocked_assert_allowed,
        mocked_ensure_eway,
        mocked_get_provider,
        mocked_log_action,
        mocked_resolve_exception,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1), einvoice_artifact=None)
        user = SimpleNamespace(id=7)
        save_spy = MagicMock()
        ewb = SimpleNamespace(
            ewb_no="171001234567",
            ewb_date=None,
            valid_upto=None,
            status=1,
            last_success_at=None,
            last_response_json=None,
            last_error_code="OLD",
            last_error_message="Old error",
            updated_by=None,
            save=save_spy,
        )
        mocked_ensure_eway.return_value = ewb
        mocked_get_provider.return_value.get_eway_details.return_value = SimpleNamespace(
            ok=True,
            ewb_no="171001234567",
            ewb_date="2026-06-18 10:00:00",
            valid_upto="2026-06-19 23:59:59",
            raw={"ewayBillNo": "171001234567"},
        )

        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.get_eway_details()

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["ewb_no"], "171001234567")
        mocked_get_provider.return_value.get_eway_details.assert_called_once_with(
            invoice=invoice,
            ewb_no="171001234567",
        )
        save_spy.assert_called()
        mocked_resolve_exception.assert_called_once()
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_eway_transporter_details_returns_lookup_data(
        self,
        mocked_assert_allowed,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_get_provider.return_value.get_transporter_details.return_value = SimpleNamespace(
            ok=True,
            data={"transporterId": "03TRANS1234A1Z5"},
            raw={"transporterId": "03TRANS1234A1Z5"},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.get_eway_transporter_details(transporter_id="03TRANS1234A1Z5")
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["data"]["transporterId"], "03TRANS1234A1Z5")
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_eway_gstin_details_returns_lookup_data(
        self,
        mocked_assert_allowed,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_get_provider.return_value.get_gstin_details.return_value = SimpleNamespace(
            ok=True,
            data={"Gstin": "03ABCDE1234F1Z5"},
            raw={"Gstin": "03ABCDE1234F1Z5"},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.get_eway_gstin_details(gstin="03abcde1234f1z5")
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["data"]["Gstin"], "03ABCDE1234F1Z5")
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_eway_hsn_details_returns_lookup_data(
        self,
        mocked_assert_allowed,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_get_provider.return_value.get_hsn_details.return_value = SimpleNamespace(
            ok=True,
            data={"hsnCode": "9983"},
            raw={"hsnCode": "9983"},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.get_eway_hsn_details(hsn_code="9983")
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["data"]["hsnCode"], "9983")
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_eway_error_list_returns_lookup_data(
        self,
        mocked_assert_allowed,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_get_provider.return_value.get_error_list.return_value = SimpleNamespace(
            ok=True,
            data=[{"code": "1001"}],
            raw={"data": [{"code": "1001"}]},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.get_eway_error_list()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["data"][0]["code"], "1001")
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_eway_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_reject_eway_uses_existing_artifact_number_when_request_omits_value(
        self,
        mocked_assert_allowed,
        mocked_ensure_eway,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        save_spy = MagicMock()
        ewb = SimpleNamespace(
            ewb_no="171001234567",
            last_response_json=None,
            last_error_code="OLD",
            last_error_message="Old error",
            updated_by=None,
            save=save_spy,
        )
        mocked_ensure_eway.return_value = ewb
        mocked_get_provider.return_value.reject_eway.return_value = SimpleNamespace(
            ok=True,
            data="Rejected",
            raw={"data": "Rejected"},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.reject_eway()
        self.assertEqual(result["status"], "SUCCESS")
        mocked_get_provider.return_value.reject_eway.assert_called_once_with(invoice=invoice, ewb_no="171001234567")
        save_spy.assert_called()
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_trip_sheet_returns_lookup_data(
        self,
        mocked_assert_allowed,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_get_provider.return_value.get_trip_sheet.return_value = SimpleNamespace(
            ok=True,
            data={"tripSheetNo": "TS123"},
            raw={"tripSheetNo": "TS123"},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.get_trip_sheet(trip_sheet_no="TS123")
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["data"]["tripSheetNo"], "TS123")
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_eway_by_document_uses_invoice_defaults_when_request_omits_values(
        self,
        mocked_assert_allowed,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(
            id=10,
            entity=SimpleNamespace(id=1),
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            invoice_number="SINV/1",
            doc_no=1,
        )
        user = SimpleNamespace(id=7)
        mocked_get_provider.return_value.get_eway_by_document.return_value = SimpleNamespace(
            ok=True,
            data={"ewayBillNo": "171001234567"},
            raw={"ewayBillNo": "171001234567"},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.get_eway_by_document()
        self.assertEqual(result["status"], "SUCCESS")
        mocked_get_provider.return_value.get_eway_by_document.assert_called_once_with(
            invoice=invoice,
            doc_type="INV",
            doc_no="SINV/1",
        )
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_eway_bills_for_transporter_formats_date_for_provider(
        self,
        mocked_assert_allowed,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_get_provider.return_value.get_eway_bills_for_transporter.return_value = SimpleNamespace(
            ok=True,
            data=[{"ewayBillNo": "171001234567"}],
            raw={"data": [{"ewayBillNo": "171001234567"}]},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.get_eway_bills_for_transporter(date=date(2026, 6, 18))
        self.assertEqual(result["status"], "SUCCESS")
        mocked_get_provider.return_value.get_eway_bills_for_transporter.assert_called_once_with(
            invoice=invoice,
            date="18/06/2026",
        )
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_eway_bill_report_by_transporter_assigned_date_passes_state_code(
        self,
        mocked_assert_allowed,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_get_provider.return_value.get_eway_bill_report_by_transporter_assigned_date.return_value = SimpleNamespace(
            ok=True,
            data=[{"ewayBillNo": "171001234567"}],
            raw={"data": [{"ewayBillNo": "171001234567"}]},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.get_eway_bill_report_by_transporter_assigned_date(date=date(2026, 6, 18), state_code="03")
        self.assertEqual(result["status"], "SUCCESS")
        mocked_get_provider.return_value.get_eway_bill_report_by_transporter_assigned_date.assert_called_once_with(
            invoice=invoice,
            date="18/06/2026",
            state_code="03",
        )
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_eway_bills_for_transporter_by_gstin_normalizes_gstin(
        self,
        mocked_assert_allowed,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_get_provider.return_value.get_eway_bills_for_transporter_by_gstin.return_value = SimpleNamespace(
            ok=True,
            data=[{"ewayBillNo": "171001234567"}],
            raw={"data": [{"ewayBillNo": "171001234567"}]},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.get_eway_bills_for_transporter_by_gstin(gen_gstin="03aaaaa0000a1z5", date=date(2026, 6, 18))
        self.assertEqual(result["status"], "SUCCESS")
        mocked_get_provider.return_value.get_eway_bills_for_transporter_by_gstin.assert_called_once_with(
            invoice=invoice,
            gen_gstin="03AAAAA0000A1Z5",
            date="18/06/2026",
        )
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_eway_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_initiate_multi_vehicle_uses_existing_artifact_number_when_request_omits_value(
        self,
        mocked_assert_allowed,
        mocked_ensure_eway,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_ensure_eway.return_value = SimpleNamespace(ewb_no="171001234567")
        mocked_get_provider.return_value.initiate_multi_vehicle.return_value = SimpleNamespace(
            ok=True,
            data={"groupNo": "10"},
            raw={"groupNo": "10"},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.initiate_multi_vehicle(
            req={
                "from_place": "Sirhind",
                "from_state_code": 3,
                "to_place": "Patiala",
                "to_state_code": 3,
                "reason_code": "1",
                "remarks": "Shift",
                "trans_mode": "1",
                "total_quantity": 10,
                "unit_code": "BOX",
            }
        )
        self.assertEqual(result["status"], "SUCCESS")
        mocked_get_provider.return_value.initiate_multi_vehicle.assert_called_once()
        called_payload = mocked_get_provider.return_value.initiate_multi_vehicle.call_args.kwargs["payload"]
        self.assertEqual(called_payload["ewbNo"], "171001234567")
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_eway_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_add_multi_vehicle_formats_transdoc_date_and_defaults_ewb_no(
        self,
        mocked_assert_allowed,
        mocked_ensure_eway,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_ensure_eway.return_value = SimpleNamespace(ewb_no="171001234567")
        mocked_get_provider.return_value.add_multi_vehicle.return_value = SimpleNamespace(
            ok=True,
            data={"groupNo": "10"},
            raw={"groupNo": "10"},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.add_multi_vehicle(
            req={
                "group_no": 10,
                "vehicle_no": "PB10AB1234",
                "trans_doc_no": "LR1",
                "trans_doc_date": date(2026, 6, 18),
                "quantity": 5,
            }
        )
        self.assertEqual(result["status"], "SUCCESS")
        called_payload = mocked_get_provider.return_value.add_multi_vehicle.call_args.kwargs["payload"]
        self.assertEqual(called_payload["ewbNo"], "171001234567")
        self.assertEqual(called_payload["transDocDate"], "18/06/2026")
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_eway")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_eway_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_generate_consolidated_eway_translates_app_contract_to_vendor_payload(
        self,
        mocked_assert_allowed,
        mocked_ensure_eway,
        mocked_get_provider,
        mocked_log_action,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        mocked_ensure_eway.return_value = SimpleNamespace(ewb_no="171001234567")
        mocked_get_provider.return_value.generate_consolidated_eway.return_value = SimpleNamespace(
            ok=True,
            data={"tripSheetNo": "TS123"},
            raw={"tripSheetNo": "TS123"},
        )
        svc = SalesComplianceService(invoice=invoice, user=user)
        result = svc.generate_consolidated_eway(
            req={
                "from_place": "Sirhind",
                "from_state_code": 3,
                "trans_mode": "1",
                "eway_bill_numbers": [{"ewb_no": 171001234567}],
                "vehicle_no": "PB10AB1234",
                "trans_doc_no": "LR1",
                "trans_doc_date": date(2026, 6, 18),
            }
        )
        self.assertEqual(result["status"], "SUCCESS")
        called_payload = mocked_get_provider.return_value.generate_consolidated_eway.call_args.kwargs["payload"]
        self.assertEqual(called_payload["fromPlace"], "Sirhind")
        self.assertEqual(called_payload["fromState"], 3)
        self.assertEqual(called_payload["transMode"], "1")
        self.assertEqual(called_payload["tripSheetEwbBills"], [{"ewbNo": 171001234567}])
        self.assertEqual(called_payload["transDocDate"], "18/06/2026")
        mocked_log_action.assert_called_once()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.resolve_exception")
    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_einvoice")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_einvoice_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_irn_details_by_doc_uses_invoice_defaults_when_request_omits_values(
        self,
        mocked_assert_allowed,
        mocked_ensure_einv,
        mocked_get_provider,
        mocked_log_action,
        mocked_resolve_exception,
    ):
        invoice = SimpleNamespace(
            id=10,
            entity=SimpleNamespace(id=1),
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            invoice_number="SINV/1",
            doc_no=1,
            bill_date=date(2026, 6, 18),
        )
        user = SimpleNamespace(id=7)
        save_spy = MagicMock()
        einv = SimpleNamespace(
            irn=None,
            ack_no=None,
            ack_date=None,
            signed_invoice=None,
            signed_qr_code=None,
            ewb_no=None,
            ewb_date=None,
            ewb_valid_upto=None,
            last_response_json={},
            last_error_code=None,
            last_error_message=None,
            status=0,
            last_success_at=None,
            updated_by=None,
            save=save_spy,
        )
        mocked_ensure_einv.return_value = einv
        mocked_get_provider.return_value.get_irn_details_by_doc.return_value = SimpleNamespace(
            ok=True,
            irn="IRN123",
            ack_no="ACK123",
            ack_date="2026-06-18 10:00:00",
            signed_invoice=None,
            signed_qr_code=None,
            ewb_no=None,
            ewb_date=None,
            ewb_valid_upto=None,
            raw={"irn": "IRN123"},
        )

        svc = SalesComplianceService(invoice=invoice, user=user)

        result = svc.get_irn_details_by_doc()

        self.assertEqual(result["status"], "SUCCESS")
        mocked_get_provider.return_value.get_irn_details_by_doc.assert_called_once_with(
            invoice=invoice,
            doc_type="INV",
            doc_number="SINV/1",
            doc_date="18/06/2026",
        )
        save_spy.assert_called()

    @patch("sales.services.sales_compliance_service.ComplianceAuditService.resolve_exception")
    @patch("sales.services.sales_compliance_service.ComplianceAuditService.log_action")
    @patch("sales.services.sales_compliance_service.ProviderRegistry.get_einvoice")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_eway_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService._ensure_einvoice_row")
    @patch("sales.services.sales_compliance_service.SalesComplianceService.assert_action_allowed")
    def test_get_eway_by_irn_success_clears_stale_error_fields(
        self,
        mocked_assert_allowed,
        mocked_ensure_einv,
        mocked_ensure_eway,
        mocked_get_provider,
        mocked_log_action,
        mocked_resolve_exception,
    ):
        invoice = SimpleNamespace(id=10, entity=SimpleNamespace(id=1))
        user = SimpleNamespace(id=7)
        einv_save_spy = MagicMock()
        ewb_save_spy = MagicMock()
        einv = SimpleNamespace(
            irn="IRN123",
            ewb_no=None,
            ewb_date=None,
            ewb_valid_upto=None,
            updated_by=None,
            save=einv_save_spy,
        )
        ewb = SimpleNamespace(
            ewb_no=None,
            ewb_date=None,
            valid_upto=None,
            status=0,
            last_success_at=None,
            last_response_json={},
            last_error_code="EWB_GET_FAILED",
            last_error_message="Fetch failed",
            updated_by=None,
            save=ewb_save_spy,
        )
        mocked_ensure_einv.return_value = einv
        mocked_ensure_eway.return_value = ewb
        mocked_get_provider.return_value.get_eway_details_by_irn.return_value = SimpleNamespace(
            ok=True,
            ewb_no="171001234567",
            ewb_date="2026-05-23 10:05:00",
            valid_upto="2026-05-24 23:59:00",
            raw={"ewb_no": "171001234567"},
        )

        svc = SalesComplianceService(invoice=invoice, user=user)

        result = svc.get_eway_details_by_irn()

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(ewb.last_error_code, None)
        self.assertEqual(ewb.last_error_message, None)
        self.assertEqual(ewb.ewb_no, "171001234567")
        self.assertEqual(einv.ewb_no, "171001234567")
        ewb_save_spy.assert_called()
        mocked_resolve_exception.assert_called_once_with(
            invoice=invoice,
            exception_type="EWB_GENERATION_FAILED",
            user=user,
        )

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("rest_framework.generics.ListCreateAPIView.create")
    def test_create_view_returns_structured_validation_error_payload(
        self,
        mocked_super_create,
        mocked_require_permission,
    ):
        mocked_super_create.side_effect = ValidationError({"lines": [{"gst_rate": ["This field is required."]}]})

        request = self._build_request(
            "/api/sales/invoices/?line_mode=goods",
            {"entity": 1, "doc_type": int(SalesInvoiceHeader.DocType.TAX_INVOICE)},
        )

        response = SalesInvoiceListCreateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"lines": [{"gst_rate": ["This field is required."]}]})
        mocked_require_permission.assert_called_once()

    @patch("sales.views.sales_invoice_views.SalesInvoiceListSerializer")
    @patch.object(SalesInvoiceListCreateAPIView, "filter_queryset")
    @patch.object(SalesInvoiceListCreateAPIView, "get_queryset")
    def test_list_view_uses_lightweight_serializer(
        self,
        mocked_get_queryset,
        mocked_filter_queryset,
        mocked_list_serializer,
    ):
        mocked_get_queryset.return_value = [self.header]
        mocked_filter_queryset.return_value = [self.header]
        mocked_list_serializer.return_value.data = [{"id": 10, "invoice_number": "INV-10"}]

        request = self.factory.get("/api/sales/invoices/?entity=1")
        force_authenticate(request, user=self.user)

        response = SalesInvoiceListCreateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        mocked_list_serializer.assert_called_once()
        self.assertEqual(response.data, [{"id": 10, "invoice_number": "INV-10"}])

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("rest_framework.generics.RetrieveUpdateAPIView.update")
    @patch.object(SalesInvoiceRetrieveUpdateAPIView, "get_object")
    def test_update_view_returns_structured_validation_error_payload(
        self,
        mocked_get_object,
        mocked_super_update,
        mocked_require_permission,
    ):
        mocked_get_object.return_value = self.header
        mocked_super_update.side_effect = ValidationError({"customer": ["This field is required."]})

        request = self._build_put_request(
            "/api/sales/invoices/10/?line_mode=service",
            {"customer": None},
        )

        response = SalesInvoiceRetrieveUpdateAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"customer": ["This field is required."]})
        mocked_require_permission.assert_called_once()

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("rest_framework.generics.RetrieveUpdateAPIView.partial_update")
    @patch.object(SalesInvoiceRetrieveUpdateAPIView, "get_object")
    def test_partial_update_view_returns_structured_validation_error_payload(
        self,
        mocked_get_object,
        mocked_super_partial_update,
        mocked_require_permission,
    ):
        mocked_get_object.return_value = self.header
        mocked_super_partial_update.side_effect = ValidationError({"bill_date": ["Enter a valid date."]})

        request = self._build_patch_request(
            "/api/sales/invoices/10/?line_mode=goods",
            {"bill_date": "bad-date"},
        )

        response = SalesInvoiceRetrieveUpdateAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"bill_date": ["Enter a valid date."]})
        mocked_require_permission.assert_called_once()

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch.object(SalesInvoicePrintAPIView, "_build_payload")
    @patch.object(SalesInvoicePrintAPIView, "_get_scoped_header")
    def test_print_view_returns_payload_and_checks_permission(
        self,
        mocked_get_header,
        mocked_build_payload,
        mocked_require_permission,
    ):
        header = SimpleNamespace(
            id=10,
            entity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
        )
        mocked_get_header.return_value = header
        mocked_build_payload.return_value = {"id": 10, "doctype": "Tax Invoice"}

        request = self.factory.get("/api/sales/invoices/10/print/?entity=1")
        force_authenticate(request, user=self.user)

        response = SalesInvoicePrintAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], 10)
        mocked_require_permission.assert_called_once_with(
            user=self.user,
            entity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            action="view",
        )

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch.object(SalesInvoiceTransportAPIView, "_to_transport_payload")
    @patch.object(SalesInvoiceTransportAPIView, "_get_scoped_header")
    def test_transport_get_returns_snapshot_payload_when_available(
        self,
        mocked_get_header,
        mocked_to_payload,
        mocked_require_permission,
    ):
        header = SimpleNamespace(
            id=10,
            entity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            transport_snapshot=SimpleNamespace(),
            eway_artifact=None,
        )
        mocked_get_header.return_value = header
        mocked_to_payload.return_value = {"source": "manual", "vehicle_no": "GJ01AA1111"}

        request = self.factory.get("/api/sales/invoices/10/transport/?entity=1")
        force_authenticate(request, user=self.user)

        response = SalesInvoiceTransportAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["has_snapshot"])
        self.assertEqual(response.data["transport"]["vehicle_no"], "GJ01AA1111")
        mocked_require_permission.assert_called_once_with(
            user=self.user,
            entity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            action="view",
        )
        mocked_to_payload.assert_called_once_with(header.transport_snapshot, source="snapshot")

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceTransportSnapshotSerializer")
    @patch.object(SalesInvoiceTransportAPIView, "_get_scoped_header")
    def test_transport_put_creates_snapshot_when_missing(
        self,
        mocked_get_header,
        mocked_serializer_cls,
        mocked_require_permission,
    ):
        header = SimpleNamespace(
            id=10,
            entity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            transport_snapshot=None,
        )
        mocked_get_header.return_value = header

        saved_instance = SimpleNamespace()
        serializer_instance = mocked_serializer_cls.return_value
        serializer_instance.is_valid.return_value = True
        serializer_instance.save.return_value = saved_instance
        mocked_serializer_cls.return_value.data = {"vehicle_no": "GJ01AA1111", "source": "manual"}

        request = self._build_put_request(
            "/api/sales/invoices/10/transport/?entity=1",
            {"vehicle_no": "GJ01AA1111"},
        )

        response = SalesInvoiceTransportAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["has_snapshot"])
        mocked_require_permission.assert_called_once_with(
            user=self.user,
            entity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            action="update",
        )
        serializer_instance.save.assert_called_once_with(
            invoice=header,
            created_by=self.user,
            updated_by=self.user,
        )

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch.object(SalesInvoiceTransportAPIView, "_get_scoped_header")
    def test_transport_get_fallback_to_eway_formats_doc_date(
        self,
        mocked_get_header,
        mocked_require_permission,
    ):
        header = SimpleNamespace(
            id=25,
            entity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            transport_snapshot=None,
            eway_artifact=SimpleNamespace(
                transporter_id="24AAAAA0000A1Z5",
                transporter_name="Eway Logistics",
                transport_mode=1,
                vehicle_no="MH01AB1234",
                vehicle_type="R",
                doc_no="LR-7788",
                doc_date=date(2026, 4, 26),
                distance_km=120,
            ),
        )
        mocked_get_header.return_value = header

        request = self.factory.get("/api/sales/invoices/25/transport/?entity=1")
        force_authenticate(request, user=self.user)

        response = SalesInvoiceTransportAPIView.as_view()(request, pk=25)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["has_snapshot"])
        self.assertEqual(response.data["transport"]["source"], "eway_prefill")
        self.assertEqual(response.data["transport"]["lr_gr_no"], "LR-7788")
        self.assertEqual(response.data["transport"]["lr_gr_date"], "2026-04-26")
        mocked_require_permission.assert_called_once_with(
            user=self.user,
            entity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            action="view",
        )

    def test_print_transport_prefers_snapshot_values_over_eway(self):
        view = SalesInvoicePrintAPIView()
        header = SimpleNamespace(
            transport_snapshot=SimpleNamespace(
                transporter_name="Snapshot Logistics",
                transporter_id="27ABCDE1234F1Z5",
                vehicle_no="GJ01AA1111",
                lr_gr_no="LR-1001",
            ),
            eway_artifact=SimpleNamespace(
                transporter_name="EWay Transport",
                transporter_id="24AAAAA0000A1Z5",
                vehicle_no="MH02BB2222",
                doc_no="EWB-DOC-9",
            ),
        )

        transport = view._resolve_transport_for_print(header)

        self.assertEqual(transport["transportname"], "Snapshot Logistics")
        self.assertEqual(transport["vehicle"], "GJ01AA1111")
        self.assertEqual(transport["grno"], "LR-1001")

    def test_print_transport_falls_back_to_eway_when_snapshot_missing(self):
        view = SalesInvoicePrintAPIView()
        header = SimpleNamespace(
            transport_snapshot=None,
            eway_artifact=SimpleNamespace(
                transporter_name="EWay Transport",
                transporter_id="24AAAAA0000A1Z5",
                vehicle_no="MH02BB2222",
                doc_no="EWB-DOC-9",
            ),
        )

        transport = view._resolve_transport_for_print(header)

        self.assertEqual(transport["transportname"], "EWay Transport")
        self.assertEqual(transport["vehicle"], "MH02BB2222")
        self.assertEqual(transport["grno"], "EWB-DOC-9")

    def test_print_qr_normalizer_generates_png_base64_from_signed_text(self):
        view = SalesInvoicePrintAPIView()

        png_base64 = view._normalize_qr_image_base64("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.sample")

        self.assertTrue(png_base64.startswith("iVBOR"))

    def test_print_qr_normalizer_preserves_existing_png_base64(self):
        view = SalesInvoicePrintAPIView()
        existing = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sWwWJ0AAAAASUVORK5CYII="

        png_base64 = view._normalize_qr_image_base64(existing)

        self.assertEqual(png_base64, existing)

    @patch("sales.views.sales_invoice_views.account_primary_bank_detail", return_value=None)
    @patch("sales.views.sales_invoice_views.State.objects.filter")
    @patch("sales.views.sales_invoice_views.Entity.objects.filter")
    @patch("sales.views.sales_invoice_views.SalesInvoiceLine.objects.filter")
    @patch("sales.views.sales_invoice_views.SalesSettingsService.get_seller_profile")
    def test_build_payload_derives_gst_summary_from_live_lines(
        self,
        mocked_seller_profile,
        mocked_line_filter,
        mocked_entity_filter,
        mocked_state_filter,
        _mocked_bank_detail,
    ):
        mocked_seller_profile.return_value = {
            "entityname": "Arnika G",
            "legalname": "Arnika",
            "address": "4368 GT Road",
            "address2": "sirhind",
            "city_name": "sirhind",
            "statecode": "29",
            "statename": "Karnataka",
            "pincode": "560001",
            "gstno": "29AAGCB1286Q000",
            "phoneoffice": "9855966534",
        }
        mocked_entity_filter.return_value.select_related.return_value.first.return_value = SimpleNamespace(
            tax_profile=SimpleNamespace(pan="APXPB6767F")
        )
        mocked_state_filter.return_value.first.return_value = SimpleNamespace(statename="Karnataka")

        line_one = SimpleNamespace(
            line_no=1,
            product=None,
            sales_account=None,
            uom=SimpleNamespace(code="Kgs"),
            qty=Decimal("100"),
            rate=Decimal("1000.00"),
            discount_percent=Decimal("0.00"),
            taxable_value=Decimal("100000.00"),
            cgst_amount=Decimal("9000.00"),
            sgst_amount=Decimal("9000.00"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            gst_rate=Decimal("18.00"),
            hsn_sac_code="7203",
        )
        line_two = SimpleNamespace(
            line_no=2,
            product=None,
            sales_account=None,
            uom=SimpleNamespace(code="Kgs"),
            qty=Decimal("100"),
            rate=Decimal("10000.00"),
            discount_percent=Decimal("0.00"),
            taxable_value=Decimal("1000000.00"),
            cgst_amount=Decimal("90000.00"),
            sgst_amount=Decimal("90000.00"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            gst_rate=Decimal("18.00"),
            hsn_sac_code="7203",
        )
        mocked_line_filter.return_value.select_related.return_value.order_by.return_value = [line_one, line_two]

        header = SimpleNamespace(
            id=54,
            entity_id=10,
            subentity_id=8,
            customer_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            bill_date=date(2026, 5, 9),
            due_date=None,
            customer=None,
            customer_name="Customer-A",
            customer_gstin="29AWGPV7107B1Z1",
            place_of_supply_state_code="29",
            bill_to_state_code="29",
            shipping_detail=None,
            shipto_snapshot=None,
            einvoice_artifact=None,
            eway_artifact=None,
            transport_snapshot=None,
            total_discount=Decimal("0.00"),
            total_other_charges=Decimal("0.00"),
            round_off=Decimal("0.00"),
            grand_total=Decimal("118000.00"),
            tcs_amount=Decimal("0.00"),
            credit_days=0,
            is_eway_applicable=False,
            is_einvoice_applicable=False,
            is_reverse_charge=False,
            doc_no=10,
            invoice_number="SI-SINV-10",
            remarks="",
            get_doc_type_display=lambda: "Tax Invoice",
        )

        view = SalesInvoicePrintAPIView()
        view.request = SimpleNamespace(query_params={})

        payload = view._build_payload(header)

        self.assertEqual(payload["subtotal"], 1100000.0)
        self.assertEqual(payload["cgst"], 99000.0)
        self.assertEqual(payload["sgst"], 99000.0)
        self.assertEqual(payload["totalgst"], 198000.0)
        self.assertEqual(payload["gtotal"], 1298000.0)
        self.assertEqual(len(payload["gst_summary"]), 1)
        self.assertEqual(payload["gst_summary"][0]["taxable_amount"], 1100000.0)
        self.assertEqual(payload["gst_summary"][0]["total_cgst_amount"], 99000.0)
        self.assertEqual(payload["gst_summary"][0]["total_sgst_amount"], 99000.0)


class IRPPayloadBuilderUnitTests(SimpleTestCase):
    @staticmethod
    def _make_line(**overrides):
        product = SimpleNamespace(name="Widget", hsn_code="1001")
        uom = SimpleNamespace(code="NOS")
        base = dict(
            line_no=1,
            product=product,
            uom=uom,
            hsn_sac_code="1001",
            is_service=False,
            qty=Decimal("1.000"),
            free_qty=Decimal("0.000"),
            rate=Decimal("100.0000"),
            discount_amount=Decimal("0.00"),
            taxable_value=Decimal("100.00"),
            cgst_amount=Decimal("9.00"),
            sgst_amount=Decimal("9.00"),
            igst_amount=Decimal("0.00"),
            cess_percent=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
            gst_rate=Decimal("18.00"),
            line_total=Decimal("118.00"),
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    @classmethod
    def _make_invoice(cls, **overrides):
        line = cls._make_line()
        original = SimpleNamespace(doc_no=123, bill_date=date(2026, 1, 1), id=10)
        customer = SimpleNamespace(country=SimpleNamespace(countrycode="IN"), state=SimpleNamespace(statecode="27"))
        base = dict(
            id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            is_reverse_charge=False,
            doc_no=101,
            invoice_number="SINV-101",
            bill_date=date(2026, 3, 1),
            total_discount=Decimal("0.00"),
            total_other_charges=Decimal("0.00"),
            round_off=Decimal("0.00"),
            grand_total=Decimal("118.00"),
            lines=SimpleNamespace(all=lambda: [line]),
            original_invoice=original,
            customer=customer,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_build_blocks_b2c_invoice(self):
        inv = self._make_invoice(supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C))
        with self.assertRaisesMessage(ValueError, "B2C"):
            IRPPayloadBuilder(inv).build()

    def test_build_rejects_invalid_doc_no_pattern(self):
        inv = self._make_invoice(doc_no=None, invoice_number="/BADNO")
        with self.assertRaisesMessage(ValueError, "Document number"):
            IRPPayloadBuilder(inv).build()

    def test_build_prefers_invoice_number_over_doc_no(self):
        inv = self._make_invoice(doc_no=1020, invoice_number="SI-SINV-1020")
        payload = IRPPayloadBuilder(inv).build()
        self.assertEqual(payload["DocDtls"]["No"], "SI-SINV-1020")

    def test_build_includes_ref_dtls_for_credit_note(self):
        inv = self._make_invoice(doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE))
        payload = IRPPayloadBuilder(inv).build()
        self.assertIn("RefDtls", payload)
        self.assertEqual(payload["RefDtls"]["PrecDocDtls"][0]["InvNo"], "123")

    def test_build_export_requires_country_code(self):
        customer = SimpleNamespace(country=None, state=SimpleNamespace(statecode="27"))
        inv = self._make_invoice(
            supply_category=int(SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST),
            customer=customer,
        )
        with self.assertRaisesMessage(ValueError, "country code"):
            IRPPayloadBuilder(inv).build()

    def test_build_blocks_non_notified_gst_rate(self):
        line = self._make_line()
        line.gst_rate = Decimal("9.00")
        line.cgst_amount = Decimal("450.00")
        line.sgst_amount = Decimal("450.00")
        line.igst_amount = Decimal("0.00")
        inv = self._make_invoice(lines=SimpleNamespace(all=lambda: [line]))
        with self.assertRaisesMessage(ValueError, "notified GST slab"):
            IRPPayloadBuilder(inv).build()

    def test_build_rejects_short_hsn_when_min_digits_6(self):
        inv = self._make_invoice()
        with self.assertRaisesMessage(ValueError, "HSN/SAC must be 6..8 digits"):
            IRPPayloadBuilder(inv, min_hsn_digits=6).build()

    def test_build_uses_line_derived_totinvval_even_if_header_grand_total_is_stale(self):
        inv = self._make_invoice(grand_total=Decimal("99999.99"), round_off=Decimal("0.37"))
        payload = IRPPayloadBuilder(inv).build()
        self.assertEqual(payload["ValDtls"]["AssVal"], 100.0)
        self.assertEqual(payload["ValDtls"]["CgstVal"], 9.0)
        self.assertEqual(payload["ValDtls"]["SgstVal"], 9.0)
        self.assertEqual(payload["ValDtls"]["CesVal"], 0.0)
        self.assertEqual(payload["ValDtls"]["RndOffAmt"], 0.37)
        self.assertEqual(payload["ValDtls"]["TotInvVal"], 118.37)

    def test_build_includes_cess_rate_when_cess_applies(self):
        line = self._make_line(cess_percent=Decimal("1.00"), cess_amount=Decimal("1.00"), line_total=Decimal("119.00"))
        inv = self._make_invoice(lines=SimpleNamespace(all=lambda: [line]), grand_total=Decimal("119.00"))
        payload = IRPPayloadBuilder(inv).build()
        self.assertEqual(payload["ItemList"][0]["CesRt"], 1.0)
        self.assertEqual(payload["ItemList"][0]["CesAmt"], 1.0)
        self.assertEqual(payload["ValDtls"]["CesVal"], 1.0)

    def test_build_omits_ecm_gstin_when_blank(self):
        inv = self._make_invoice(ecm_gstin="")
        payload = IRPPayloadBuilder(inv).build()
        self.assertNotIn("EcmGstin", payload["TranDtls"])

    def test_build_includes_ecm_gstin_when_present(self):
        inv = self._make_invoice(ecm_gstin="29abcde1234f1z5")
        payload = IRPPayloadBuilder(inv).build()
        self.assertEqual(payload["TranDtls"]["EcmGstin"], "29ABCDE1234F1Z5")

    def test_build_includes_eway_and_dispatch_blocks_when_available(self):
        line = self._make_line()
        eway = SimpleNamespace(
            disp_dtls_json={
                "Nm": "ABC company pvt ltd",
                "Addr1": "7th block, kuvempu layout",
                "Loc": "Bangalore",
                "Pin": "518360",
                "Stcd": "37",
            },
            exp_ship_dtls_json={
                "Gstin": "27AWGPV7107B1Z5",
                "LglNm": "XYZ company pvt ltd",
                "TrdNm": "XYZ Industries",
                "Addr1": "7th block, kuvempu layout",
                "Loc": "Bangalore",
                "Pin": "560004",
                "Stcd": "29",
            },
            transport_mode=1,
            distance_km=100,
            transporter_id="12AWGPV7107B1Z1",
            transporter_name="XYZ EXPORTS",
            doc_no="DOC01",
            doc_date=date(2026, 3, 5),
            vehicle_no="KA12AB1234",
            vehicle_type="R",
        )
        inv = SimpleNamespace(
            id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            is_reverse_charge=False,
            doc_no=101,
            invoice_number="SINV-101",
            bill_date=date(2026, 3, 1),
            total_discount=Decimal("0.00"),
            total_other_charges=Decimal("0.00"),
            round_off=Decimal("0.00"),
            grand_total=Decimal("118.00"),
            lines=SimpleNamespace(all=lambda: [line]),
            original_invoice=None,
            customer=SimpleNamespace(country=SimpleNamespace(countrycode="IN"), state=SimpleNamespace(statecode="27")),
            customer_gstin="29AWGPV7107B1Z1",
            eway_artifact=eway,
        )
        payload = IRPPayloadBuilder(inv).build()
        self.assertIn("DispDtls", payload)
        self.assertIn("ShipDtls", payload)
        self.assertIn("EwbDtls", payload)
        self.assertEqual(payload["EwbDtls"]["TransMode"], "1")

    def test_build_omits_ship_dtls_when_same_as_buyer_gstin(self):
        line = self._make_line()
        eway = SimpleNamespace(
            disp_dtls_json={
                "Nm": "ABC company pvt ltd",
                "Addr1": "7th block, kuvempu layout",
                "Loc": "Bangalore",
                "Pin": "518360",
                "Stcd": "37",
            },
            exp_ship_dtls_json={
                "Gstin": "29AWGPV7107B1Z1",
                "LglNm": "XYZ company pvt ltd",
                "TrdNm": "XYZ Industries",
                "Addr1": "7th block, kuvempu layout",
                "Loc": "Bangalore",
                "Pin": "560004",
                "Stcd": "29",
            },
            transport_mode=1,
            distance_km=100,
            transporter_id="12AWGPV7107B1Z1",
            transporter_name="XYZ EXPORTS",
            doc_no="DOC01",
            doc_date=date(2026, 3, 5),
            vehicle_no="KA12AB1234",
            vehicle_type="R",
        )
        inv = SimpleNamespace(
            id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            is_reverse_charge=False,
            doc_no=101,
            invoice_number="SINV-101",
            bill_date=date(2026, 3, 1),
            total_discount=Decimal("0.00"),
            total_other_charges=Decimal("0.00"),
            round_off=Decimal("0.00"),
            grand_total=Decimal("118.00"),
            lines=SimpleNamespace(all=lambda: [line]),
            original_invoice=None,
            customer=SimpleNamespace(country=SimpleNamespace(countrycode="IN"), state=SimpleNamespace(statecode="27")),
            customer_gstin="29AWGPV7107B1Z1",
            eway_artifact=eway,
        )

        payload = IRPPayloadBuilder(inv).build()

        self.assertNotIn("ShipDtls", payload)


class ComplianceErrorCatalogServiceUnitTests(SimpleTestCase):
    @patch("sales.services.compliance_error_catalog_service.SalesComplianceErrorCode.objects")
    def test_resolve_returns_catalog_reason_resolution(self, mocked_objects):
        mocked_objects.filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            code="2230",
            message="IRN cancel blocked due to active EWB.",
            reason="EWB exists.",
            resolution="Cancel EWB first.",
        )
        info = ComplianceErrorCatalogService.resolve(code="2230", message="fallback")
        self.assertEqual(info.code, "2230")
        self.assertIn("EWB", info.as_text())

    def test_resolve_without_code_uses_message(self):
        info = ComplianceErrorCatalogService.resolve(code=None, message="Some failure")
        self.assertEqual(info.as_text(), "Some failure")


class SalesSettingsPolicyControlUnitTests(SimpleTestCase):
    def test_normalize_policy_controls_accepts_einvoice_min_hsn_digits(self):
        data = SalesSettingsService.normalize_policy_controls({"einvoice_min_hsn_digits": 6})
        self.assertEqual(data["einvoice_min_hsn_digits"], 6)

    def test_normalize_policy_controls_rejects_invalid_einvoice_min_hsn_digits(self):
        with self.assertRaisesMessage(ValueError, "policy_controls.einvoice_min_hsn_digits must be between 4 and 8."):
            SalesSettingsService.normalize_policy_controls({"einvoice_min_hsn_digits": 3})


class EWayPayloadBuilderUnitTests(SimpleTestCase):
    def test_rail_requires_trans_doc_fields(self):
        x = EWayInput(
            distance_km=10,
            trans_mode="2",
            transporter_id="",
            transporter_name="",
            trans_doc_no="",
            trans_doc_date=None,
            vehicle_no=None,
            vehicle_type=None,
        )
        with self.assertRaisesMessage(ValueError, "TransDocNo"):
            build_generate_eway_payload("IRN123", x)

    def test_road_allows_missing_trans_doc_and_supports_zero_distance(self):
        x = EWayInput(
            distance_km=0,
            trans_mode="1",
            transporter_id="05AAACG0904A1ZL",
            transporter_name="ABC",
            trans_doc_no="",
            trans_doc_date=None,
            vehicle_no="APR3214",
            vehicle_type="R",
        )
        payload = build_generate_eway_payload("IRN123", x)
        self.assertEqual(payload["Distance"], 0)
        self.assertEqual(payload["VehType"], "R")
        self.assertNotIn("TransDocDt", payload)

    def test_build_exp_ship_dtls_falls_back_state_code_from_gstin(self):
        ship = build_exp_ship_dtls(
            addr1="45366",
            addr2="",
            loc="Bengaluru",
            pin="560001",
            stcd="",
            gstin="29AWGPV7107B1Z1",
        )
        self.assertEqual(ship["Gstin"], "29AWGPV7107B1Z1")
        self.assertEqual(ship["Stcd"], "29")

    def _build_b2c_invoice_fixture(self):
        line = SimpleNamespace(
            hsn_sac_code="9983",
            qty=2,
            free_qty=0,
            taxable_value=1000,
            gst_rate=18,
            cess_percent=0,
            uom=SimpleNamespace(code="NOS"),
            product=SimpleNamespace(name="Service Item"),
        )
        invoice = SimpleNamespace(
            supply_category="2",
            entity=SimpleNamespace(
                legalname="Test Entity",
                entityname="Test Entity",
            ),
            shipto_snapshot=SimpleNamespace(
                pincode="140406",
                state_code="03",
                full_name="Walk-in Customer",
                address1="Street 1",
                address2="Street 2",
                city="Sirhind",
            ),
            bill_date=date(2026, 6, 18),
            doc_no="SINV001",
            lines=SimpleNamespace(all=lambda: [line]),
        )
        ewb = SimpleNamespace(
            distance_km=25,
            transport_mode=1,
            transporter_id="03TRANS1234A1Z5",
            transporter_name="Fast Transport",
            doc_type=None,
            doc_no="LR001",
            doc_date=date(2026, 6, 18),
            vehicle_no="PB10AB1234",
            vehicle_type=None,
        )
        return invoice, ewb

    @patch("sales.services.eway.payload_b2c.entity_primary_address")
    @patch("sales.services.eway.payload_b2c.entity_primary_state")
    def test_build_b2c_direct_payload_uses_explicit_policy_defaults(
        self,
        mocked_primary_state,
        mocked_primary_address,
    ):
        invoice, ewb = self._build_b2c_invoice_fixture()
        mocked_primary_address.return_value = SimpleNamespace(
            pincode="140406",
            line1="Entity Street 1",
            line2="Entity Street 2",
            city=SimpleNamespace(cityname="Sirhind"),
        )
        mocked_primary_state.return_value = SimpleNamespace(statecode="03")

        payload = build_b2c_direct_payload(invoice=invoice, ewb=ewb, entity_gstin="03AAAAA0000A1Z5")

        self.assertEqual(payload["supplyType"], "O")
        self.assertEqual(payload["subSupplyType"], "1")
        self.assertEqual(payload["docType"], "INV")
        self.assertEqual(payload["toGstin"], "URP")
        self.assertEqual(payload["transactionType"], 1)
        self.assertEqual(payload["vehicleType"], "R")

    @override_settings(
        SALES_EWAY_B2C_POLICY={
            "supply_type": "I",
            "sub_supply_type": "2",
            "sub_supply_desc": "Demo policy",
            "default_doc_type": "BIL",
            "customer_gstin": "URD",
            "transaction_type": 3,
            "default_vehicle_type": "O",
        }
    )
    @patch("sales.services.eway.payload_b2c.entity_primary_address")
    @patch("sales.services.eway.payload_b2c.entity_primary_state")
    def test_build_b2c_direct_payload_allows_policy_override_from_settings(
        self,
        mocked_primary_state,
        mocked_primary_address,
    ):
        invoice, ewb = self._build_b2c_invoice_fixture()
        mocked_primary_address.return_value = SimpleNamespace(
            pincode="140406",
            line1="Entity Street 1",
            line2="Entity Street 2",
            city=SimpleNamespace(cityname="Sirhind"),
        )
        mocked_primary_state.return_value = SimpleNamespace(statecode="03")

        payload = build_b2c_direct_payload(invoice=invoice, ewb=ewb, entity_gstin="03AAAAA0000A1Z5")

        self.assertEqual(payload["supplyType"], "I")
        self.assertEqual(payload["subSupplyType"], "2")
        self.assertEqual(payload["subSupplyDesc"], "Demo policy")
        self.assertEqual(payload["docType"], "BIL")
        self.assertEqual(payload["toGstin"], "URD")
        self.assertEqual(payload["transactionType"], 3)
        self.assertEqual(payload["vehicleType"], "O")


class SalesComplianceDateParseUnitTests(SimpleTestCase):
    def test_parse_mastergst_datetime_with_ampm(self):
        dt = SalesComplianceService._parse_dt("05/03/2026 10:22:00 PM")
        self.assertIsNotNone(dt)

    def test_parse_mastergst_iso_like_datetime_returns_aware_value(self):
        dt = SalesComplianceService._parse_dt("2026-05-09 12:56:00")
        self.assertIsNotNone(dt)
        self.assertTrue(timezone.is_aware(dt))


class EWayRequestSerializerUnitTests(SimpleTestCase):
    def test_road_mode_allows_null_transport_doc_date(self):
        serializer = GenerateEWayRequestSerializer(
            data={
                "distance_km": 1,
                "trans_mode": "1",
                "vehicle_no": "KA12ER1234",
                "vehicle_type": "R",
                "trans_doc_no": "",
                "trans_doc_date": None,
                "transporter_id": "12AWGPV7107B1Z1",
                "transporter_name": "abc",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rail_mode_requires_transport_doc_date(self):
        serializer = GenerateEWayRequestSerializer(
            data={
                "distance_km": 1,
                "trans_mode": "2",
                "trans_doc_no": "LR-22",
                "trans_doc_date": None,
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("trans_doc_date", serializer.errors)


class SalesComplianceCredentialValidationUnitTests(SimpleTestCase):
    def test_get_mastergst_cred_for_entity_rejects_gstin_mismatch(self):
        entity = SimpleNamespace(
            id=1,
            gst_registrations=SimpleNamespace(
                filter=lambda **kwargs: SimpleNamespace(
                    only=lambda *args, **kw: SimpleNamespace(
                        first=lambda: SimpleNamespace(gstin="29AAGCB1286Q1Z3")
                    )
                )
            )
        )
        cred = SimpleNamespace(
            gstin="29AAGCB1286Q000",
            client_id="cid",
            client_secret="secret",
            email="ops@example.com",
            gst_username="gst-user",
            gst_password="pwd",
            get_client_secret=lambda: "secret",
            get_gst_password=lambda: "pwd",
        )

        with patch(
            "sales.services.sales_compliance_service.CredentialResolver.provider_for_entity",
            return_value=cred,
        ):
            with self.assertRaisesMessage(ValidationError, "does not match the entity primary GSTIN"):
                SalesComplianceService._get_mastergst_cred_for_entity(entity, provider_name="mastergst")

    @patch("sales.services.providers.credential_resolver.SalesMasterGSTCredential.objects.filter")
    def test_provider_for_entity_uses_requested_service_scope(self, mocked_filter):
        expected = SimpleNamespace(id=9)
        base_qs = MagicMock()
        scoped_qs = MagicMock()
        mocked_filter.return_value = base_qs
        base_qs.filter.return_value = scoped_qs
        scoped_qs.first.return_value = expected

        result = CredentialResolver.provider_for_entity(
            77,
            provider_name="whitebooks",
            service_scope=MasterGSTServiceScope.EWAY,
        )

        self.assertIs(result, expected)
        mocked_filter.assert_called_once_with(
            entity_id=77,
            environment=1,
            is_active=True,
        )
        base_qs.filter.assert_called_once_with(service_scope=int(MasterGSTServiceScope.EWAY))

    @patch("sales.services.providers.credential_resolver.SalesMasterGSTCredential.objects.filter")
    def test_provider_for_entity_falls_back_to_einvoice_credential_for_eway_scope(self, mocked_filter):
        expected = SimpleNamespace(id=11)
        base_qs = MagicMock()
        eway_qs = MagicMock()
        einvoice_qs = MagicMock()

        mocked_filter.return_value = base_qs
        base_qs.filter.side_effect = [eway_qs, einvoice_qs]
        eway_qs.first.return_value = None
        einvoice_qs.first.return_value = expected

        result = CredentialResolver.provider_for_entity(
            77,
            provider_name="whitebooks",
            service_scope=MasterGSTServiceScope.EWAY,
        )

        self.assertIs(result, expected)
        mocked_filter.assert_called_once_with(
            entity_id=77,
            environment=1,
            is_active=True,
        )
        self.assertEqual(base_qs.filter.call_count, 2)


class MasterGSTErrorExtractUnitTests(SimpleTestCase):
    @patch("sales.services.providers.mastergst.ComplianceErrorCatalogService.resolve")
    def test_extract_error_reads_status_desc_json(self, mocked_resolve):
        mocked_resolve.return_value = SimpleNamespace(code="2150", message="Duplicate IRN", reason=None, resolution=None)
        raw = {
            "status_cd": "0",
            "status_desc": '[{"ErrorCode":"2150","ErrorMessage":"Duplicate IRN"}]',
        }
        code, msg, reason, resolution = _extract_error(raw)
        self.assertEqual(code, "2150")
        self.assertEqual(msg, "Duplicate IRN")


class CustomerStatementExportViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(id=11, is_authenticated=True)

    @patch("sales.views.sales_ar_exports._require_ar_view_permission")
    @patch("sales.views.sales_ar_exports.SalesArService.customer_statement")
    @patch("sales.views.sales_ar_exports.account.objects.filter")
    @patch("sales.views.sales_ar_exports.resolve_scope_names")
    def test_customer_statement_excel_export_returns_attachment(
        self,
        mocked_resolve_scope_names,
        mocked_account_filter,
        mocked_customer_statement,
        mocked_require_permission,
    ):
        mocked_require_permission.return_value = None
        mocked_resolve_scope_names.return_value = {
            "entity_name": "Arnika G",
            "entityfin_name": "FY 2026-27",
            "subentity_name": "Main Branch",
        }

        class _Query:
            def select_related(self, *args, **kwargs):
                return self

            def only(self, *args, **kwargs):
                return self

            def first(self):
                return SimpleNamespace(
                    id=501,
                    accountname="Customer A",
                    effective_accounting_name="Customer A",
                    effective_accounting_code=9004,
                    ledger_id=268,
                )

        mocked_account_filter.return_value = _Query()
        mocked_customer_statement.return_value = {
            "totals": {
                "outstanding_total": "100.00",
                "advance_outstanding_total": "25.00",
                "advance_consumed_total": "5.00",
                "net_ar_position": "75.00",
            },
            "open_items": [
                {
                    "bill_date": "2026-04-01",
                    "due_date": "2026-04-30",
                    "invoice_number": "INV-1",
                    "customer_reference_number": "REF-1",
                    "original_amount": "100.00",
                    "settled_amount": "0.00",
                    "outstanding_amount": "100.00",
                    "is_open": True,
                }
            ],
            "advances": [],
            "settlements": [],
        }

        request = self.factory.get(
            "/api/sales/ar/customer-statement/excel/",
            {"entity": "10", "entityfinid": "8", "customer": "501"},
        )
        force_authenticate(request, user=self.user)

        response = CustomerStatementExcelAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("CustomerLedger_", response["Content-Disposition"])
