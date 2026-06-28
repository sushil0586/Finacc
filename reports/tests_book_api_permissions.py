from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from reports.tests_support.compliance_golden_dataset import build_compliance_golden_scope


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class BookReportApiPermissionTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="book-rbac-user",
            email="book-rbac@example.com",
            password="pass123",
        )
        self.permission_codes_patch = patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=[
                "reports.financial_hub.daybook.view",
                "reports.financial_hub.cashbook.view",
                "reports.financial_hub.ledger_book.view",
            ],
        )
        self.permission_codes_patch.start()
        self.addCleanup(self.permission_codes_patch.stop)
        self.client.force_authenticate(user=self.user)
        golden = build_compliance_golden_scope(user=self.user, entity_name="Book Permission Entity")
        self.scope_params = {
            "entity": golden.entity.id,
            "entityfinid": golden.entityfin.id,
            "subentity": golden.subentity.id,
            "from_date": "2025-04-01",
            "to_date": "2025-04-30",
        }

    @patch("reports.api.book_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_daybook_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:financial-daybook"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.book_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_daybook_export_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:financial-daybook-csv"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.book_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_daybook_entry_detail_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(
            reverse("reports_api:financial-daybook-detail", kwargs={"entry_id": 1}),
            self.scope_params,
        )
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.book_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_cashbook_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:financial-cashbook"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.book_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_cashbook_export_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:financial-cashbook-pdf"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.book_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_posting_document_lookup_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(
            reverse("reports_api:financial-posting-lookup"),
            {
                **self.scope_params,
                "document_type": "sales_invoice",
                "document_id": 1,
            },
        )
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.book_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_posting_detail_export_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(
            reverse("reports_api:financial-posting-detail-csv", kwargs={"entry_id": 1}),
            self.scope_params,
        )
        self.assertEqual(response.status_code, 403)
