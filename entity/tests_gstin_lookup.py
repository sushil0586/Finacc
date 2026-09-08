from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError

from entity.gstin_lookup import lookup_gstin


class GstinLookupServiceTests(TestCase):
    @patch("entity.gstin_lookup.WhitebooksClient")
    @patch("entity.gstin_lookup.CredentialResolver.provider_for_entity")
    def test_normalizes_whitebooks_response(self, credential_for_entity, client_class):
        credential_for_entity.return_value = Mock()
        client_class.return_value.get_gstn_details.return_value = {
            "status_cd": "1",
            "data": {
                "Gstin": "29ABCDE1234F1Z5",
                "LegalName": "Example Private Limited",
                "TradeName": "Example",
                "Status": "Active",
                "StateCode": "29",
                "AddrBnm": "Business Park",
                "AddrBno": "42",
                "AddrPncd": "560001",
                "TxpType": "Regular",
            },
        }

        result = lookup_gstin(gstin="29abcde1234f1z5", credential_entity_id=10)

        self.assertEqual(result["gstin"], "29ABCDE1234F1Z5")
        self.assertEqual(result["legalName"], "Example Private Limited")
        self.assertEqual(result["entityname"], "Example")
        self.assertEqual(result["pan"], "ABCDE1234F")
        self.assertEqual(result["source"], "whitebooks")
        credential_for_entity.assert_called_once_with(10, provider_name="whitebooks")

    def test_rejects_invalid_gstin_without_calling_provider(self):
        with self.assertRaises(ValidationError):
            lookup_gstin(gstin="INVALID", credential_entity_id=10)

    @override_settings(WHITEBOOKS_SANDBOX_MODE=True, ALLOW_RELAXED_GSTIN_FOR_SANDBOX=True)
    @patch("entity.gstin_lookup.WhitebooksClient")
    @patch("entity.gstin_lookup.CredentialResolver.provider_for_entity")
    def test_accepts_documented_whitebooks_sandbox_gstin(self, credential_for_entity, client_class):
        credential_for_entity.return_value = Mock()
        client_class.return_value.get_gstn_details.return_value = {
            "status_cd": "1",
            "data": {"Gstin": "29AAGCB1286Q000", "LegalName": "Sandbox Entity", "Status": "ACT"},
        }

        result = lookup_gstin(gstin="29AAGCB1286Q000", credential_entity_id=10)

        self.assertEqual(result["gstin"], "29AAGCB1286Q000")
        self.assertTrue(result["is_active"])

    @patch("entity.gstin_lookup.WhitebooksClient")
    @patch("entity.gstin_lookup.CredentialResolver.provider_for_entity")
    def test_returns_sanitized_provider_error(self, credential_for_entity, client_class):
        credential_for_entity.return_value = Mock()
        client_class.return_value.get_gstn_details.return_value = {
            "status_cd": "0",
            "message": "GSTIN was not found.",
        }

        with self.assertRaisesMessage(ValidationError, "GSTIN was not found"):
            lookup_gstin(gstin="29ABCDE1234F1Z5", credential_entity_id=10)

    @patch("entity.gstin_lookup.WhitebooksClient")
    @patch("entity.gstin_lookup.CredentialResolver.provider_for_entity")
    def test_reads_whitebooks_lower_camel_case_error(self, credential_for_entity, client_class):
        credential_for_entity.return_value = Mock()
        client_class.return_value.get_gstn_details.return_value = {
            "status_cd": "0",
            "status_desc": '[{"errorCode":"3001","errorMessage":"Requested data is not available"}]',
        }

        with self.assertRaisesMessage(ValidationError, "Requested data is not available"):
            lookup_gstin(gstin="29ABCDE1234F1Z5", credential_entity_id=10)
