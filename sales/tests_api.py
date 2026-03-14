from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from sales.services.sales_choices_service import SalesChoicesService


User = get_user_model()


class SalesApiTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="sales_api_tester",
            email="sales_api_tester@example.com",
            password="pass@12345",
        )
        self.client.force_authenticate(user=self.user)


class SalesChoicesApiTests(SalesApiTestBase):
    def test_choices_requires_entity_id(self):
        resp = self.client.get("/api/sales/choices/")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {"entity_id": "This query parameter is required."})

    @patch("sales.views.sales_choices_views.SalesChoicesService.get_choices")
    def test_choices_returns_data(self, mocked_get_choices):
        mocked_get_choices.return_value = {"doc_types": [{"id": 1, "label": "Tax Invoice"}]}

        resp = self.client.get("/api/sales/choices/?entity_id=11&subentity_id=3")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"doc_types": [{"id": 1, "label": "Tax Invoice"}]})
        mocked_get_choices.assert_called_once_with(entity_id=11, subentity_id=3)


class SalesSettingsApiTests(SalesApiTestBase):
    def test_settings_requires_entity_id(self):
        resp = self.client.get("/api/sales/settings/")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {"entity_id": "entity_id is required."})

    def test_settings_requires_entityfinid(self):
        resp = self.client.get("/api/sales/settings/?entity_id=10")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {"entityfinid": "entityfinid is required."})

    @patch("sales.views.sales_settings_views.SalesChoicesService.get_choices")
    @patch("sales.views.sales_settings_views.SalesSettingsService.get_current_doc_no")
    @patch("sales.views.sales_settings_views.SalesSettingsService.get_seller_profile")
    @patch("sales.views.sales_settings_views.SalesSettingsService.get_settings")
    def test_settings_returns_payload(
        self,
        mocked_get_settings,
        mocked_get_seller_profile,
        mocked_get_current_doc_no,
        mocked_get_choices,
    ):
        mocked_get_settings.return_value = SimpleNamespace(
            default_doc_code_invoice="SI",
            default_doc_code_cn="SCN",
            default_doc_code_dn="SDN",
            default_workflow_action="confirm",
            auto_derive_tax_regime=True,
            allow_mixed_taxability_in_one_invoice=False,
            enable_einvoice=True,
            enable_eway=True,
            einvoice_entity_applicable=True,
            eway_value_threshold="50000.00",
            compliance_applicability_mode="AUTO_ONLY",
            auto_generate_einvoice_on_confirm=False,
            auto_generate_einvoice_on_post=True,
            auto_generate_eway_on_confirm=False,
            auto_generate_eway_on_post=True,
            prefer_irp_generate_einvoice_and_eway_together=True,
            enforce_statutory_cancel_before_business_cancel=True,
            tcs_credit_note_policy="DISALLOW",
            enable_round_off=True,
            round_grand_total_to=2,
        )
        mocked_get_seller_profile.return_value = {"entity_id": 10, "gstin": "22AAAAA0000A1Z5"}
        mocked_get_current_doc_no.side_effect = ["SI/0001", "SCN/0001", "SDN/0001"]
        mocked_get_choices.return_value = {"DocType": [{"key": "TAX_INVOICE", "label": "Tax Invoice", "enabled": True}]}

        resp = self.client.get("/api/sales/settings/?entity_id=10&entityfinid=20&subentity_id=30")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["seller"], {"entity_id": 10, "gstin": "22AAAAA0000A1Z5"})
        self.assertEqual(
            resp.data["current_doc_numbers"],
            {"invoice": "SI/0001", "credit_note": "SCN/0001", "debit_note": "SDN/0001"},
        )
        self.assertEqual(resp.data["settings"]["default_doc_code_invoice"], "SI")
        self.assertEqual(resp.data["capabilities"]["has_lock_periods"], True)
        self.assertEqual(resp.data["choice_override_catalog"], {"DocType": [{"key": "TAX_INVOICE", "label": "Tax Invoice", "enabled": True}]})
        mocked_get_settings.assert_called_once_with(10, 30)
        mocked_get_seller_profile.assert_called_once_with(entity_id=10, subentity_id=30)

    @patch("sales.views.sales_settings_views.SalesChoicesService.get_choices")
    @patch("sales.views.sales_settings_views.SalesSettingsService.get_seller_profile")
    @patch("sales.views.sales_settings_views.SalesSettingsService.get_settings")
    def test_patch_updates_sales_settings(
        self,
        mocked_get_settings,
        mocked_get_seller_profile,
        mocked_get_choices,
    ):
        settings_obj = SimpleNamespace(
            default_doc_code_invoice="SI",
            default_doc_code_cn="SCN",
            default_doc_code_dn="SDN",
            default_workflow_action="confirm",
            auto_derive_tax_regime=True,
            allow_mixed_taxability_in_one_invoice=False,
            enable_einvoice=True,
            enable_eway=True,
            einvoice_entity_applicable=True,
            eway_value_threshold="50000.00",
            compliance_applicability_mode="AUTO_ONLY",
            auto_generate_einvoice_on_confirm=False,
            auto_generate_einvoice_on_post=True,
            auto_generate_eway_on_confirm=False,
            auto_generate_eway_on_post=True,
            prefer_irp_generate_einvoice_and_eway_together=True,
            enforce_statutory_cancel_before_business_cancel=True,
            tcs_credit_note_policy="DISALLOW",
            enable_round_off=True,
            round_grand_total_to=2,
            save=Mock(),
        )
        mocked_get_settings.return_value = settings_obj
        mocked_get_seller_profile.return_value = {"entity_id": 10}
        mocked_get_choices.return_value = {"DocType": [{"key": "TAX_INVOICE", "label": "Tax Invoice", "enabled": True}]}

        resp = self.client.patch(
            "/api/sales/settings/?entity_id=10&subentity_id=30",
            {"settings": {"enable_einvoice": False, "default_doc_code_invoice": "NSI"}},
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(settings_obj.enable_einvoice, False)
        self.assertEqual(settings_obj.default_doc_code_invoice, "NSI")
        settings_obj.save.assert_called_once()
        self.assertEqual(resp.data["settings"]["enable_einvoice"], False)
        self.assertEqual(resp.data["settings"]["default_doc_code_invoice"], "NSI")


class SalesChoicesServiceTests(TestCase):
    def test_get_choices_includes_sales_settings_groups(self):
        payload = SalesChoicesService.get_choices(entity_id=999, subentity_id=None)

        self.assertIn("BillToShipTo", payload)
        self.assertIn("EInvoiceApplicable", payload)
        self.assertIn("EWayApplicable", payload)
        self.assertEqual(
            [row["key"] for row in payload["BillToShipTo"]],
            ["SAME", "DIFFERENT"],
        )
        self.assertEqual(
            [row["key"] for row in payload["EInvoiceApplicable"]],
            ["YES", "NO"],
        )

    def test_get_choices_does_not_expose_private_enum_members(self):
        payload = SalesChoicesService.get_choices(entity_id=999, subentity_id=None)

        for rows in payload.values():
            self.assertFalse(any((row.get("key") or "").startswith("_") for row in rows))
