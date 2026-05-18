from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from payroll.models import EntityPayrollPolicy, PayrollPolicyRule
from payroll.services import EntityPayrollPolicyService, PayrollPolicyRuleService
from payroll.tests.factories import PayrollFactory


class PayrollPolicyFoundationServiceTests(TestCase):
    def setUp(self):
        self.scope = PayrollFactory.entity_scope()

    def _create_policy(self, **overrides):
        payload = {
            "entity": self.scope["entity"],
            "code": "MONTHLY_DEFAULT",
            "name": "Monthly Default",
            "pay_frequency": "MONTHLY",
            "effective_from": date(2026, 4, 1),
            "is_default": True,
            "is_active": True,
        }
        payload.update(overrides)
        return EntityPayrollPolicyService.create_or_update_policy(payload)

    def test_policy_code_unique_per_entity(self):
        self._create_policy()
        with self.assertRaises(IntegrityError):
            EntityPayrollPolicy.objects.create(
                entity=self.scope["entity"],
                code="MONTHLY_DEFAULT",
                name="Duplicate",
                pay_frequency="WEEKLY",
                effective_from=date(2026, 5, 1),
            )

    def test_only_one_default_active_policy_per_entity_and_frequency(self):
        first = self._create_policy(code="MONTHLY_A", name="A")
        second = self._create_policy(code="MONTHLY_B", name="B")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_effective_date_validation(self):
        with self.assertRaises(ValueError):
            self._create_policy(effective_from=date(2026, 5, 1), effective_to=date(2026, 4, 1))

    def test_default_setter_clears_previous_default(self):
        first = self._create_policy(code="POLICY_A", name="Policy A")
        second = self._create_policy(code="POLICY_B", name="Policy B", is_default=False)
        EntityPayrollPolicyService.set_default_policy(policy=second)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_resolver_returns_correct_active_policy(self):
        self._create_policy(code="OLD", name="Old Policy", effective_from=date(2026, 4, 1), effective_to=date(2026, 4, 30))
        current = self._create_policy(code="CURRENT", name="Current Policy", effective_from=date(2026, 5, 1))
        resolved = EntityPayrollPolicyService.resolve_active_policy(
            entity_id=self.scope["entity"].id,
            payroll_date=date(2026, 5, 15),
            pay_frequency="MONTHLY",
        )
        self.assertEqual(resolved.id, current.id)

    def test_rule_date_validation(self):
        policy = self._create_policy()
        with self.assertRaises(ValueError):
            PayrollPolicyRuleService.create_or_update_rule(
                {
                    "policy": policy,
                    "rule_type": "rounding",
                    "rule_key": "cutoff_grace_days",
                    "effective_from": date(2026, 3, 31),
                    "rule_value_json": {"days": 2},
                    "is_active": True,
                }
            )

    def test_resolve_active_rules(self):
        policy = self._create_policy()
        rule = PayrollPolicyRuleService.create_or_update_rule(
            {
                "policy": policy,
                "rule_type": "lop",
                "rule_key": "grace_window",
                "effective_from": date(2026, 4, 1),
                "rule_value_json": {"days": 1},
                "is_active": True,
            }
        )
        resolved = list(PayrollPolicyRuleService.resolve_active_rules(policy=policy, rule_date=date(2026, 4, 10)))
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].id, rule.id)


class PayrollPolicyFoundationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = PayrollFactory.user()
        self.client.force_authenticate(self.user)
        self.scope = PayrollFactory.entity_scope(user=self.user)

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.payroll_setup_views.PayrollPermissionService.has_entity_permission_access", return_value=True)
    def test_create_list_update_and_set_default_policy(self, _perm, _scope):
        create_response = self.client.post(
            "/api/payroll/policies/",
            {
                "entity": self.scope["entity"].id,
                "code": "MONTHLY_DEFAULT",
                "name": "Monthly Default",
                "pay_frequency": "MONTHLY",
                "effective_from": "2026-04-01",
                "is_default": True,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        policy_id = create_response.json()["id"]

        list_response = self.client.get(f"/api/payroll/policies/?entity={self.scope['entity'].id}&is_active=true")
        self.assertEqual(list_response.status_code, 200, list_response.content)
        payload = list_response.json()
        results = payload.get("results", payload) if isinstance(payload, dict) else payload
        self.assertEqual(len(results), 1)

        patch_response = self.client.patch(
            f"/api/payroll/policies/{policy_id}/",
            {"salary_disbursement_day": 7, "approval_required": False},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        self.assertEqual(patch_response.json()["salary_disbursement_day"], 7)
        self.assertFalse(patch_response.json()["approval_required"])

        create_second = self.client.post(
            "/api/payroll/policies/",
            {
                "entity": self.scope["entity"].id,
                "code": "MONTHLY_BACKUP",
                "name": "Monthly Backup",
                "pay_frequency": "MONTHLY",
                "effective_from": "2026-05-01",
                "is_default": False,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_second.status_code, 201, create_second.content)
        second_id = create_second.json()["id"]

        set_default_response = self.client.post(
            f"/api/payroll/policies/{second_id}/set-default/",
            {},
            format="json",
        )
        self.assertEqual(set_default_response.status_code, 200, set_default_response.content)
        self.assertTrue(set_default_response.json()["data"]["is_default"])

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.payroll_setup_views.PayrollPermissionService.has_entity_permission_access", return_value=True)
    def test_create_and_update_policy_rule(self, _perm, _scope):
        policy = EntityPayrollPolicyService.create_or_update_policy(
            {
                "entity": self.scope["entity"],
                "code": "MONTHLY_DEFAULT",
                "name": "Monthly Default",
                "pay_frequency": "MONTHLY",
                "effective_from": date(2026, 4, 1),
                "is_default": True,
                "is_active": True,
            }
        )

        create_response = self.client.post(
            f"/api/payroll/policies/{policy.id}/rules/",
            {
                "rule_type": "rounding",
                "rule_key": "component_half_up",
                "effective_from": "2026-04-01",
                "rule_value_json": {"precision": 0.5},
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        rule_id = create_response.json()["id"]

        patch_response = self.client.patch(
            f"/api/payroll/policy-rules/{rule_id}/",
            {"rule_value_json": {"precision": 1}, "is_active": False},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        self.assertFalse(patch_response.json()["is_active"])

        list_response = self.client.get(f"/api/payroll/policies/{policy.id}/rules/")
        self.assertEqual(list_response.status_code, 200, list_response.content)
        payload = list_response.json()
        results = payload.get("results", payload) if isinstance(payload, dict) else payload
        self.assertEqual(len(results), 1)
