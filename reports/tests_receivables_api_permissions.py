from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class ReceivablesAPIPermissionTests(APITestCase):
    permission_codes = {
        "reports.financial_hub.receivables_hub.customer_outstanding.view",
        "reports.financial_hub.receivables_hub.customer_outstanding.export",
        "reports.financial_hub.receivables_hub.receivable_aging.view",
        "reports.financial_hub.receivables_hub.receivable_aging.export",
        "reports.financial_hub.receivables_hub.receivable_aging_detail.view",
        "reports.financial_hub.receivables_hub.overdue_customers.view",
        "reports.financial_hub.receivables_hub.credit_exposure.view",
        "reports.financial_hub.receivables_hub.receivables_exception_report.view",
        "reports.financial_hub.receivables_hub.open_items.view",
        "reports.financial_hub.receivables_hub.open_items.export",
        "reports.financial_hub.receivables_hub.collections_history.view",
        "reports.financial_hub.receivables_hub.collections_history.export",
    }

    def setUp(self):
        suffix = uuid4().hex[:8]
        self.client = APIClient()
        self.user = User.objects.create_user(
            username=f"receivables-api-{suffix}",
            email=f"receivables-api-{suffix}@example.com",
            password="pass123",
        )
        self.other_user = User.objects.create_user(
            username=f"receivables-other-{suffix}",
            email=f"receivables-other-{suffix}@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = self._create_entity("Receivables Entity", self.user)
        self.other_entity = self._create_entity("Other Receivables Entity", self.other_user)
        self.entityfin = self._create_financial_year(self.entity, self.user)
        self.other_entityfin = self._create_financial_year(self.other_entity, self.other_user)
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main Branch")
        self.other_subentity = SubEntity.objects.create(entity=self.other_entity, subentityname="Other Branch")
        self.params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
        }

        empty_report = {"rows": [], "totals": {}, "pagination": {"total_rows": 0}}
        self.patchers = [
            patch("core.entitlements.SubscriptionService.assert_entity_access", return_value=self.entity),
            patch("core.entitlements.EffectivePermissionService.has_scope_access", return_value=True),
            patch("core.entitlements.EffectivePermissionService.has_data_scope_access", return_value=True),
            patch(
                "reports.api.receivables_views.EffectivePermissionService.permission_codes_for_user",
                return_value=self.permission_codes,
            ),
            patch("reports.api.receivables_views.build_customer_outstanding_report", return_value=empty_report.copy()),
            patch("reports.api.receivables_views.build_receivable_aging_report", return_value=empty_report.copy()),
            patch("reports.api.receivables_views.build_open_items_report", return_value=empty_report.copy()),
            patch("reports.api.receivables_views.build_collections_history_report", return_value=empty_report.copy()),
        ]
        self.mocks = [patcher.start() for patcher in self.patchers]
        self.addCleanup(self._stop_patchers)

    def _stop_patchers(self):
        for patcher in reversed(self.patchers):
            patcher.stop()

    def _create_entity(self, name, owner):
        return Entity.objects.create(
            entityname=name,
            legalname=name,
            GstRegitrationType=self.gst_type,
            createdby=owner,
        )

    @staticmethod
    def _create_financial_year(entity, owner):
        return EntityFinancialYear.objects.create(
            entity=entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=owner,
        )

    def _set_permissions(self, *codes):
        self.mocks[3].return_value = set(codes)

    def test_each_receivables_screen_requires_and_accepts_its_exact_view_permission(self):
        checks = [
            ("reports_api:customer-outstanding-report", "reports.financial_hub.receivables_hub.customer_outstanding.view", {}),
            ("reports_api:receivable-aging-report", "reports.financial_hub.receivables_hub.receivable_aging.view", {}),
            ("reports_api:receivable-aging-report", "reports.financial_hub.receivables_hub.receivable_aging_detail.view", {"view": "invoice"}),
            ("reports_api:open-items-report", "reports.financial_hub.receivables_hub.open_items.view", {}),
            ("reports_api:collections-history-report", "reports.financial_hub.receivables_hub.collections_history.view", {}),
        ]
        for route_name, permission_code, extra_params in checks:
            with self.subTest(route_name=route_name, permission_code=permission_code):
                self._set_permissions(permission_code)
                response = self.client.get(reverse(route_name), {**self.params, **extra_params})
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_customer_outstanding_variants_require_their_own_view_permissions(self):
        checks = [
            ("reports.financial_hub.receivables_hub.overdue_customers.view", {"overdue_only": "true"}),
            ("reports.financial_hub.receivables_hub.credit_exposure.view", {"credit_limit_exceeded": "true"}),
            ("reports.financial_hub.receivables_hub.receivables_exception_report.view", {"exception_only": "true"}),
        ]
        url = reverse("reports_api:customer-outstanding-report")
        for permission_code, extra_params in checks:
            with self.subTest(permission_code=permission_code):
                self._set_permissions(permission_code)
                response = self.client.get(url, {**self.params, **extra_params})
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_customer_outstanding_permission_does_not_unlock_restricted_variants(self):
        self._set_permissions("reports.financial_hub.receivables_hub.customer_outstanding.view")
        url = reverse("reports_api:customer-outstanding-report")
        for extra_params in (
            {"overdue_only": "true"},
            {"credit_limit_exceeded": "true"},
            {"exception_only": "true"},
        ):
            with self.subTest(extra_params=extra_params):
                response = self.client.get(url, {**self.params, **extra_params})
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_view_permission_is_denied(self):
        self._set_permissions()
        response = self.client.get(reverse("reports_api:customer-outstanding-report"), self.params)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_tenant_entity_is_denied_before_report_builder_runs(self):
        def assert_membership(*, entity, **kwargs):
            if entity.id == self.other_entity.id:
                raise PermissionDenied("You do not have tenant membership for this entity.")
            return entity

        self.mocks[0].side_effect = assert_membership
        response = self.client.get(
            reverse("reports_api:customer-outstanding-report"),
            {
                "entity": self.other_entity.id,
                "entityfinid": self.other_entityfin.id,
                "subentity": self.other_subentity.id,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.mocks[4].assert_not_called()

    def test_financial_year_from_another_entity_is_rejected(self):
        response = self.client.get(
            reverse("reports_api:customer-outstanding-report"),
            {**self.params, "entityfinid": self.other_entityfin.id},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mocks[4].assert_not_called()

    def test_branch_from_another_entity_is_rejected(self):
        response = self.client.get(
            reverse("reports_api:customer-outstanding-report"),
            {**self.params, "subentity": self.other_subentity.id},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mocks[4].assert_not_called()

    def test_branch_restricted_user_is_denied(self):
        self.mocks[1].return_value = False
        response = self.client.get(reverse("reports_api:customer-outstanding-report"), self.params)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.mocks[4].assert_not_called()

    def test_view_only_user_does_not_receive_export_actions(self):
        self._set_permissions("reports.financial_hub.receivables_hub.customer_outstanding.view")
        response = self.client.get(reverse("reports_api:customer-outstanding-report"), self.params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["actions"]["can_print"])
        self.assertFalse(response.data["actions"]["can_export_csv"])
        self.assertEqual(response.data["actions"]["export_urls"], {})
        self.assertEqual(response.data["available_exports"], [])

    def test_view_only_user_cannot_call_export_endpoint_directly(self):
        self._set_permissions("reports.financial_hub.receivables_hub.customer_outstanding.view")
        response = self.client.get(reverse("reports_api:customer-outstanding-report-csv"), self.params)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_export_permission_allows_direct_export(self):
        checks = [
            ("reports_api:customer-outstanding-report-csv", "reports.financial_hub.receivables_hub.customer_outstanding.export"),
            ("reports_api:receivable-aging-report-csv", "reports.financial_hub.receivables_hub.receivable_aging.export"),
            ("reports_api:open-items-report-csv", "reports.financial_hub.receivables_hub.open_items.export"),
            ("reports_api:collections-history-report-csv", "reports.financial_hub.receivables_hub.collections_history.export"),
        ]
        for route_name, permission_code in checks:
            with self.subTest(route_name=route_name):
                self._set_permissions(permission_code)
                response = self.client.get(reverse(route_name), self.params)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertTrue(response["Content-Type"].startswith("text/csv"))
