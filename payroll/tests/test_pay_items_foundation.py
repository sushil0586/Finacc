from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from payroll.models import OneTimePayItem, RecurringPayItem
from payroll.services import ContractPayrollProfileService, OneTimePayItemService, RecurringPayItemService
from payroll.tests.factories import PayrollFactory


class PayItemsFoundationServiceTests(TestCase):
    def setUp(self):
        self.scope = PayrollFactory.entity_scope()
        self.contract = PayrollFactory.hrms_contract(entity=self.scope["entity"], subentity=self.scope["subentity"])
        self.profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )
        self.component = PayrollFactory.component(entity=self.scope["entity"], code="ALLOWANCE")
        self.period = PayrollFactory.payroll_period(
            entity=self.scope["entity"],
            entityfinid=self.scope["entityfinid"],
            subentity=self.scope["subentity"],
        )

    def test_recurring_effective_date_validation(self):
        with self.assertRaises(ValueError):
            RecurringPayItemService.create_or_update_item(
                {
                    "entity": self.scope["entity"],
                    "contract_payroll_profile": self.profile,
                    "payroll_component": self.component,
                    "item_type": RecurringPayItem.ItemType.EARNING,
                    "amount": "1000.00",
                    "effective_from": date(2026, 5, 1),
                    "effective_to": date(2026, 4, 1),
                }
            )

    def test_recurring_entity_mismatch_validation(self):
        other_scope = PayrollFactory.entity_scope()
        with self.assertRaises(ValueError):
            RecurringPayItemService.create_or_update_item(
                {
                    "entity": other_scope["entity"],
                    "contract_payroll_profile": self.profile,
                    "payroll_component": self.component,
                    "item_type": RecurringPayItem.ItemType.EARNING,
                    "amount": "500.00",
                    "effective_from": date(2026, 4, 1),
                }
            )

    def test_recurring_resolver_returns_active_items(self):
        item = RecurringPayItemService.create_or_update_item(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_component": self.component,
                "item_type": RecurringPayItem.ItemType.EARNING,
                "amount": "750.00",
                "effective_from": date(2026, 4, 1),
                "priority": 10,
                "is_active": True,
            }
        )
        resolved = list(
            RecurringPayItemService.resolve_active_recurring_items(
                contract_payroll_profile=self.profile,
                payroll_date=date(2026, 4, 15),
            )
        )
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].id, item.id)

    def test_one_time_entity_mismatch_validation(self):
        other_scope = PayrollFactory.entity_scope()
        with self.assertRaises(ValueError):
            OneTimePayItemService.create_or_update_item(
                {
                    "entity": other_scope["entity"],
                    "contract_payroll_profile": self.profile,
                    "payroll_component": self.component,
                    "item_type": OneTimePayItem.ItemType.EARNING,
                    "requested_date": date(2026, 4, 10),
                    "effective_date": date(2026, 4, 10),
                    "amount": "400.00",
                    "approval_status": OneTimePayItem.ApprovalStatus.DRAFT,
                    "source_type": OneTimePayItem.SourceType.MANUAL,
                }
            )

    def test_one_time_resolver_returns_approved_items(self):
        item = OneTimePayItemService.create_or_update_item(
            {
                "entity": self.scope["entity"],
                "contract_payroll_profile": self.profile,
                "payroll_component": self.component,
                "item_type": OneTimePayItem.ItemType.EARNING,
                "payroll_period": self.period,
                "requested_date": date(2026, 4, 10),
                "effective_date": date(2026, 4, 20),
                "amount": "900.00",
                "approval_status": OneTimePayItem.ApprovalStatus.APPROVED,
                "source_type": OneTimePayItem.SourceType.INCENTIVE,
                "is_active": True,
            }
        )
        resolved = list(
            OneTimePayItemService.resolve_payable_items(
                contract_payroll_profile=self.profile,
                payroll_period=self.period,
            )
        )
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].id, item.id)

    def test_one_time_period_entity_consistency_validation(self):
        other_scope = PayrollFactory.entity_scope()
        other_period = PayrollFactory.payroll_period(
            entity=other_scope["entity"],
            entityfinid=other_scope["entityfinid"],
            subentity=other_scope["subentity"],
        )
        with self.assertRaises(ValueError):
            OneTimePayItemService.create_or_update_item(
                {
                    "entity": self.scope["entity"],
                    "contract_payroll_profile": self.profile,
                    "payroll_component": self.component,
                    "item_type": OneTimePayItem.ItemType.EARNING,
                    "payroll_period": other_period,
                    "requested_date": date(2026, 4, 10),
                    "effective_date": date(2026, 4, 20),
                    "amount": "600.00",
                    "approval_status": OneTimePayItem.ApprovalStatus.DRAFT,
                    "source_type": OneTimePayItem.SourceType.MANUAL,
                }
            )


class PayItemsFoundationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = PayrollFactory.user()
        self.client.force_authenticate(self.user)
        self.scope = PayrollFactory.entity_scope(user=self.user)
        self.contract = PayrollFactory.hrms_contract(entity=self.scope["entity"], subentity=self.scope["subentity"])
        self.profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )
        self.component = PayrollFactory.component(entity=self.scope["entity"], code="BONUS")
        self.period = PayrollFactory.payroll_period(
            entity=self.scope["entity"],
            entityfinid=self.scope["entityfinid"],
            subentity=self.scope["subentity"],
        )

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.payroll_setup_views.PayrollPermissionService.has_entity_permission_access", return_value=True)
    def test_create_list_update_recurring_pay_item(self, _perm, _scope):
        create_response = self.client.post(
            "/api/payroll/recurring-pay-items/",
            {
                "entity": self.scope["entity"].id,
                "contract_payroll_profile": str(self.profile.id),
                "payroll_component": self.component.id,
                "item_type": "EARNING",
                "amount": "1200.00",
                "effective_from": "2026-04-01",
                "recurrence_frequency": "MONTHLY",
                "priority": 50,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        item_id = create_response.json()["id"]

        list_response = self.client.get(f"/api/payroll/recurring-pay-items/?entity={self.scope['entity'].id}&is_active=true")
        self.assertEqual(list_response.status_code, 200, list_response.content)
        payload = list_response.json()
        results = payload.get("results", payload) if isinstance(payload, dict) else payload
        self.assertEqual(len(results), 1)

        patch_response = self.client.patch(
            f"/api/payroll/recurring-pay-items/{item_id}/",
            {"amount": "1500.00", "remarks": "Revised"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        self.assertEqual(float(patch_response.json()["amount"]), 1500.0)

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.payroll_setup_views.PayrollPermissionService.has_entity_permission_access", return_value=True)
    def test_create_list_update_one_time_pay_item(self, _perm, _scope):
        create_response = self.client.post(
            "/api/payroll/one-time-pay-items/",
            {
                "entity": self.scope["entity"].id,
                "contract_payroll_profile": str(self.profile.id),
                "payroll_component": self.component.id,
                "item_type": "EARNING",
                "payroll_period": self.period.id,
                "requested_date": "2026-04-10",
                "effective_date": "2026-04-20",
                "amount": "800.00",
                "quantity": "1.00",
                "approval_status": "APPROVED",
                "source_type": "INCENTIVE",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        item_id = create_response.json()["id"]

        list_response = self.client.get(f"/api/payroll/one-time-pay-items/?entity={self.scope['entity'].id}&approval_status=APPROVED")
        self.assertEqual(list_response.status_code, 200, list_response.content)
        payload = list_response.json()
        results = payload.get("results", payload) if isinstance(payload, dict) else payload
        self.assertEqual(len(results), 1)

        patch_response = self.client.patch(
            f"/api/payroll/one-time-pay-items/{item_id}/",
            {"remarks": "Approved by admin"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        self.assertEqual(patch_response.json()["remarks"], "Approved by admin")
