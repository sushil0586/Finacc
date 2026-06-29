from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.models import account
from sales.models import SalesInvoiceHeader
from sales.serializers.sales_ar import CustomerSettlementCreateInputSerializer
from sales.serializers.sales_charge_serializers import SalesChargeLineSerializer, SalesChargeTypeSerializer
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer
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
    def setUp(self):
        super().setUp()
        self.entity = Entity.objects.create(entityname="Sales Choices Entity", createdby=self.user)
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main")
        self.permission_entity = SimpleNamespace(id=self.entity.id)
        self.mock_entity_for_user = patch("sales.views.rbac.EffectivePermissionService.entity_for_user", return_value=self.permission_entity)
        self.mock_permission_codes = patch(
            "sales.views.rbac.EffectivePermissionService.permission_codes_for_user",
            return_value=["sales.invoice.view", "sales.settings.view"],
        )
        self.mock_subscription_access = patch("sales.views.rbac.SubscriptionService.assert_entity_access", return_value=self.permission_entity)
        self.mock_entity_for_user.start()
        self.mock_permission_codes.start()
        self.mock_subscription_access.start()

    def tearDown(self):
        patch.stopall()
        super().tearDown()

    def test_choices_requires_entity_id(self):
        resp = self.client.get("/api/sales/choices/")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {"entity_id": "This query parameter is required."})

    @patch("sales.views.sales_choices_views.SalesChoicesService.get_choices")
    def test_choices_returns_data(self, mocked_get_choices):
        mocked_get_choices.return_value = {"doc_types": [{"id": 1, "label": "Tax Invoice"}]}

        resp = self.client.get(f"/api/sales/choices/?entity_id={self.entity.id}&subentity_id={self.subentity.id}")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"doc_types": [{"id": 1, "label": "Tax Invoice"}]})
        mocked_get_choices.assert_called_once_with(entity_id=self.entity.id, subentity_id=self.subentity.id)


class SalesSettingsApiTests(SalesApiTestBase):
    def setUp(self):
        super().setUp()
        self.permission_entity = SimpleNamespace(id=10)
        self.mock_entity_for_user = patch("sales.views.rbac.EffectivePermissionService.entity_for_user", return_value=self.permission_entity)
        self.mock_permission_codes = patch(
            "sales.views.rbac.EffectivePermissionService.permission_codes_for_user",
            return_value=["sales.settings.view", "sales.settings.update"],
        )
        self.mock_subscription_access = patch("sales.views.rbac.SubscriptionService.assert_entity_access", return_value=self.permission_entity)
        self.mock_entity_for_user.start()
        self.mock_permission_codes.start()
        self.mock_subscription_access.start()

    def tearDown(self):
        patch.stopall()
        super().tearDown()

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
        mocked_get_current_doc_no.side_effect = lambda **kwargs: f"{kwargs.get('doc_code', 'DOC')}/0001"
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
        mocked_get_settings.assert_called_once_with(10, 30, entityfinid_id=20)
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

        with patch("sales.views.sales_settings_views.bump_meta_namespaces") as mocked_bump_cache:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                resp = self.client.patch(
                    "/api/sales/settings/?entity_id=10&subentity_id=30",
                    {"settings": {"enable_einvoice": False, "default_doc_code_invoice": "NSI"}},
                    format="json",
                )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(settings_obj.enable_einvoice, False)
        self.assertEqual(settings_obj.default_doc_code_invoice, "NSI")
        settings_obj.save.assert_called_once()
        self.assertGreaterEqual(len(callbacks), 1)
        mocked_bump_cache.assert_called_once()
        self.assertEqual(resp.data["settings"]["enable_einvoice"], False)
        self.assertEqual(resp.data["settings"]["default_doc_code_invoice"], "NSI")


    @patch("sales.views.sales_settings_views.SalesLockPeriod.objects.create")
    @patch("sales.views.sales_settings_views.SalesLockPeriod.objects.filter")
    @patch("sales.views.sales_settings_views.SalesChoicesService.get_choices")
    @patch("sales.views.sales_settings_views.SalesSettingsService.get_seller_profile")
    @patch("sales.views.sales_settings_views.SalesSettingsService.get_settings")
    def test_patch_replaces_lock_periods_with_entityfinid_scope(
        self,
        mocked_get_settings,
        mocked_get_seller_profile,
        mocked_get_choices,
        mocked_lock_filter,
        mocked_lock_create,
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
        mocked_get_choices.return_value = {}
        mocked_lock_filter.return_value.filter.return_value = mocked_lock_filter.return_value
        mocked_lock_filter.return_value.delete.return_value = None

        with patch("sales.views.sales_settings_views.bump_meta_namespaces"):
            resp = self.client.patch(
                "/api/sales/settings/?entity_id=10&entityfinid=20&subentity_id=30",
                {
                    "lock_periods": [
                        {
                            "lock_date": "2026-06-22",
                            "reason": "June books locked",
                        }
                    ]
                },
                format="json",
            )

        self.assertEqual(resp.status_code, 200, resp.content)
        mocked_lock_create.assert_called_once_with(
            entity_id=10,
            entityfinid_id=20,
            subentity_id=30,
            lock_date="2026-06-22",
            reason="June books locked",
        )


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


class SalesOversizedValidationTests(SalesApiTestBase):
    def setUp(self):
        super().setUp()
        self.entity = Entity.objects.create(entityname="Sales Oversized Entity", createdby=self.user)
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            year_code="2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1, 0, 0, 0)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31, 0, 0, 0)),
            isactive=True,
            createdby=self.user,
        )
        self.customer = account.objects.create(
            entity=self.entity,
            accountname="Oversized Customer",
            createdby=self.user,
        )
        self.sales_account = account.objects.create(
            entity=self.entity,
            accountname="Oversized Revenue Account",
            createdby=self.user,
        )

    def test_sales_invoice_serializer_rejects_oversized_header_and_line_fields(self):
        serializer = SalesInvoiceHeaderSerializer(
            data={
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "doc_type": SalesInvoiceHeader.DocType.TAX_INVOICE,
                "bill_date": "2026-04-01",
                "customer": self.customer.id,
                "credit_days": int("9" * 20),
                "doc_code": "D" * 21,
                "customer_name": "C" * 256,
                "customer_gstin": "1" * 16,
                "customer_state_code": "123",
                "bill_to_address1": "A" * 256,
                "bill_to_address2": "B" * 256,
                "bill_to_city": "C" * 101,
                "bill_to_state_code": "123",
                "bill_to_pincode": "9" * 11,
                "seller_gstin": "2" * 16,
                "ecm_gstin": "3" * 16,
                "seller_state_code": "123",
                "place_of_supply_state_code": "123",
                "place_of_supply_pincode": "9" * 9,
                "einvoice_applicable_manual": True,
                "compliance_override_reason": "R" * 256,
                "reference": "R" * 256,
                "legacy_source_system": "L" * 101,
                "legacy_source_key": "K" * 256,
                "legacy_import_mode": "M" * 31,
                "lines": [
                    {
                        "line_no": 1,
                        "sales_account": self.sales_account.id,
                        "productDesc": "D" * 201,
                        "batch_number": "B" * 81,
                        "hsn_sac_code": "H" * 21,
                        "is_service": True,
                        "qty": "1.000",
                        "rate": "1.0000",
                        "taxability": SalesInvoiceHeader.Taxability.TAXABLE,
                    }
                ],
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("credit_days", serializer.errors)
        self.assertIn("doc_code", serializer.errors)
        self.assertIn("customer_name", serializer.errors)
        self.assertIn("customer_gstin", serializer.errors)
        self.assertIn("customer_state_code", serializer.errors)
        self.assertIn("bill_to_address1", serializer.errors)
        self.assertIn("bill_to_address2", serializer.errors)
        self.assertIn("bill_to_city", serializer.errors)
        self.assertIn("bill_to_state_code", serializer.errors)
        self.assertIn("bill_to_pincode", serializer.errors)
        self.assertIn("seller_gstin", serializer.errors)
        self.assertIn("ecm_gstin", serializer.errors)
        self.assertIn("seller_state_code", serializer.errors)
        self.assertIn("place_of_supply_state_code", serializer.errors)
        self.assertIn("place_of_supply_pincode", serializer.errors)
        self.assertIn("compliance_override_reason", serializer.errors)
        self.assertIn("reference", serializer.errors)
        self.assertIn("legacy_source_system", serializer.errors)
        self.assertIn("legacy_source_key", serializer.errors)
        self.assertIn("legacy_import_mode", serializer.errors)
        self.assertIn("lines", serializer.errors)
        self.assertIn("productDesc", serializer.errors["lines"][0])
        self.assertIn("batch_number", serializer.errors["lines"][0])
        self.assertIn("hsn_sac_code", serializer.errors["lines"][0])

    def test_sales_charge_type_serializer_rejects_oversized_fields(self):
        serializer = SalesChargeTypeSerializer(
            data={
                "entity": self.entity.id,
                "code": "C" * 31,
                "name": "N" * 81,
                "base_category": "OTHER",
                "is_active": True,
                "is_service": True,
                "hsn_sac_code_default": "H" * 21,
                "gst_rate_default": "18.00",
                "description": "D" * 201,
                "revenue_account": self.sales_account.id,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("code", serializer.errors)
        self.assertIn("name", serializer.errors)
        self.assertIn("hsn_sac_code_default", serializer.errors)
        self.assertIn("description", serializer.errors)

    def test_sales_charge_line_serializer_rejects_oversized_charge_type(self):
        serializer = SalesChargeLineSerializer(
            data={
                "line_no": 1,
                "charge_type": "C" * 21,
                "description": "Freight",
                "taxability": SalesInvoiceHeader.Taxability.EXEMPT,
                "is_service": True,
                "hsn_sac_code": "",
                "taxable_value": "100.00",
                "gst_rate": "0.00",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("charge_type", serializer.errors)

    def test_customer_settlement_create_input_rejects_oversized_fields(self):
        serializer = CustomerSettlementCreateInputSerializer(
            data={
                "entity": 1,
                "entityfinid": 1,
                "customer": 1,
                "settlement_type": "receipt",
                "settlement_date": "2026-04-01",
                "reference_no": "R" * 51,
                "external_voucher_no": "E" * 51,
                "remarks": "M" * 256,
                "lines": [
                    {
                        "open_item_id": 1,
                        "amount": "10.00",
                        "note": "N" * 256,
                    }
                ],
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("reference_no", serializer.errors)
        self.assertIn("external_voucher_no", serializer.errors)
        self.assertIn("remarks", serializer.errors)
        self.assertIn("lines", serializer.errors)
        self.assertIn("note", serializer.errors["lines"][0])
