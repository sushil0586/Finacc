from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from reports.tests_support.compliance_golden_dataset import build_compliance_golden_scope


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class FinancialReportApiPermissionTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="financial-rbac-user",
            email="financial-rbac@example.com",
            password="pass123",
        )
        self.permission_codes_patch = patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=[
                "reports.financial_hub.trial_balance.view",
                "reports.financial_hub.ledger_book.view",
                "reports.financial_hub.ledger_summary.view",
                "reports.financial_hub.profit_loss.view",
                "reports.financial_hub.balance_sheet.view",
                "reports.financial_hub.trading_account.view",
            ],
        )
        self.permission_codes_patch.start()
        self.addCleanup(self.permission_codes_patch.stop)
        self.client.force_authenticate(user=self.user)
        golden = build_compliance_golden_scope(user=self.user, entity_name="Financial Permission Entity")
        self.scope_params = {
            "entity": golden.entity.id,
            "entityfinid": golden.entityfin.id,
            "subentity": golden.subentity.id,
        }

    @patch("reports.api.financial.views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_trial_balance_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:financial-trial-balance"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.financial.views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_ledger_book_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(
            reverse("reports_api:financial-ledger-book"),
            {**self.scope_params, "ledger": 999999},
        )
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.financial.views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_ledger_summary_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:financial-ledger-summary"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.financial.views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_profit_loss_export_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:financial-profit-loss-csv"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.financial.views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_balance_sheet_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:financial-balance-sheet"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.financial.views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_trading_account_export_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:financial-trading-account-pdf"), self.scope_params)
        self.assertEqual(response.status_code, 403)
