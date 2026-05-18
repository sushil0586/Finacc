from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from payroll.tests.factories import PayrollFactory
from payroll.views.payroll_run_views import PayrollRunListCreateAPIView, PayrollRunRetrieveAPIView


class PayrollPhase0ScopeAccessTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.setup = PayrollFactory.full_payroll_setup()
        self.setup["run"] = PayrollFactory.payroll_run(
            entity=self.setup["entity"],
            entityfinid=self.setup["entityfinid"],
            subentity=self.setup["subentity"],
            payroll_period=self.setup["period"],
        )
        self.user = self.setup["user"]

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.scoped.EffectivePermissionService.permission_codes_for_user", return_value={"payroll.run.view"})
    def test_run_list_requires_entity_scope(self, _permission_codes, _assert_entity_access):
        request = self.factory.get("/api/payroll/runs/")
        force_authenticate(request, user=self.user)

        response = PayrollRunListCreateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("entity", response.data)

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.scoped.EffectivePermissionService.permission_codes_for_user", return_value={"payroll.run.view"})
    def test_run_detail_enforces_object_scope(self, permission_codes, assert_entity_access):
        request = self.factory.get(f"/api/payroll/runs/{self.setup['run'].id}/")
        force_authenticate(request, user=self.user)

        response = PayrollRunRetrieveAPIView.as_view()(request, pk=self.setup["run"].id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(assert_entity_access.called)
        called_entity = assert_entity_access.call_args.kwargs["entity"]
        self.assertEqual(called_entity.id, self.setup["entity"].id)
        permission_codes.assert_called_with(self.user, self.setup["entity"].id)

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.scoped.EffectivePermissionService.permission_codes_for_user", return_value=set())
    def test_run_detail_blocks_missing_entity_permission(self, _permission_codes, _assert_entity_access):
        request = self.factory.get(f"/api/payroll/runs/{self.setup['run'].id}/")
        force_authenticate(request, user=self.user)

        response = PayrollRunRetrieveAPIView.as_view()(request, pk=self.setup["run"].id)

        self.assertEqual(response.status_code, 403)
        self.assertIn("Missing permission", str(response.data["detail"]))
