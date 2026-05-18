from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from payroll.models import ContractStatutoryProfile, EntityStatutoryRegistration, StatutoryScheme
from payroll.services import (
    ContractPayrollProfileService,
    ContractStatutoryProfileService,
    EntityStatutoryRegistrationService,
    StatutoryRuleService,
    StatutorySchemeService,
    StatutorySlabService,
)
from payroll.tests.factories import PayrollFactory


class StatutoryFoundationServiceTests(TestCase):
    def setUp(self):
        self.scope = PayrollFactory.entity_scope()
        self.scheme = StatutorySchemeService.create_or_update_scheme(
            {
                "code": "PF_IN",
                "name": "Provident Fund India",
                "scheme_type": StatutoryScheme.SchemeType.PF,
                "country_code": "IN",
                "state_code": "",
                "is_system": True,
                "is_active": True,
            }
        )
        self.contract = PayrollFactory.hrms_contract(entity=self.scope["entity"], subentity=self.scope["subentity"])
        self.contract_profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )

    def test_scheme_uniqueness_per_country_and_state(self):
        with self.assertRaises(IntegrityError):
            StatutoryScheme.objects.create(
                code="PF_IN",
                name="Duplicate PF India",
                scheme_type=StatutoryScheme.SchemeType.PF,
                country_code="IN",
                state_code="",
            )

    def test_rule_effective_date_validation(self):
        with self.assertRaises(ValueError):
            StatutoryRuleService.create_or_update_rule(
                {
                    "entity": self.scope["entity"],
                    "scheme": self.scheme,
                    "rule_code": "PF_BAD_DATES",
                    "rule_name": "Bad Dates",
                    "rule_type": "PERCENTAGE",
                    "effective_from": date(2026, 5, 1),
                    "effective_to": date(2026, 4, 1),
                }
            )

    def test_slab_validation(self):
        rule = StatutoryRuleService.create_or_update_rule(
            {
                "entity": self.scope["entity"],
                "scheme": self.scheme,
                "rule_code": "PF_SLAB",
                "rule_name": "PF Slab",
                "rule_type": "SLAB",
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )
        with self.assertRaises(ValueError):
            StatutorySlabService.create_or_update_slab(
                {
                    "rule": rule,
                    "slab_from": "1000.00",
                    "slab_to": "500.00",
                    "amount": "50.00",
                    "is_active": True,
                }
            )

    def test_registration_number_unique_per_entity_and_scheme(self):
        EntityStatutoryRegistrationService.create_or_update_registration(
            {
                "entity": self.scope["entity"],
                "scheme": self.scheme,
                "registration_number": "PF-REG-001",
                "registration_state": "",
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )
        with self.assertRaises(IntegrityError):
            EntityStatutoryRegistration.objects.create(
                entity=self.scope["entity"],
                scheme=self.scheme,
                registration_number="PF-REG-001",
                effective_from=date(2026, 5, 1),
            )

    def test_registration_overlap_validation(self):
        EntityStatutoryRegistrationService.create_or_update_registration(
            {
                "entity": self.scope["entity"],
                "scheme": self.scheme,
                "registration_number": "PF-REG-001",
                "registration_state": "",
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )
        with self.assertRaises(ValueError):
            EntityStatutoryRegistrationService.create_or_update_registration(
                {
                    "entity": self.scope["entity"],
                    "scheme": self.scheme,
                    "registration_number": "PF-REG-002",
                    "registration_state": "",
                    "effective_from": date(2026, 5, 1),
                    "effective_to": date(2026, 12, 31),
                    "is_active": True,
                }
            )

    def test_contract_statutory_overlap_validation(self):
        ContractStatutoryProfileService.create_or_update_profile(
            {
                "contract_payroll_profile": self.contract_profile,
                "scheme": self.scheme,
                "is_applicable": True,
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )
        with self.assertRaises(ValueError):
            ContractStatutoryProfileService.create_or_update_profile(
                {
                    "contract_payroll_profile": self.contract_profile,
                    "scheme": self.scheme,
                    "is_applicable": True,
                    "effective_from": date(2026, 4, 15),
                    "is_active": True,
                }
            )

    def test_resolvers(self):
        global_rule = StatutoryRuleService.create_or_update_rule(
            {
                "scheme": self.scheme,
                "rule_code": "PF_GLOBAL",
                "rule_name": "PF Global",
                "rule_type": "PERCENTAGE",
                "effective_from": date(2026, 4, 1),
                "priority": 20,
                "is_active": True,
            }
        )
        entity_rule = StatutoryRuleService.create_or_update_rule(
            {
                "entity": self.scope["entity"],
                "scheme": self.scheme,
                "rule_code": "PF_ENTITY",
                "rule_name": "PF Entity Override",
                "rule_type": "PERCENTAGE",
                "effective_from": date(2026, 4, 1),
                "priority": 10,
                "is_active": True,
            }
        )
        profile = ContractStatutoryProfileService.create_or_update_profile(
            {
                "contract_payroll_profile": self.contract_profile,
                "scheme": self.scheme,
                "is_applicable": True,
                "effective_from": date(2026, 4, 1),
                "is_active": True,
            }
        )

        resolved_rules = list(
            StatutoryRuleService.resolve_rules(
                entity_id=self.scope["entity"].id,
                scheme=self.scheme,
                rule_date=date(2026, 4, 10),
                state_code=None,
            )
        )
        self.assertEqual([item.id for item in resolved_rules], [entity_rule.id, global_rule.id])

        resolved_profile = ContractStatutoryProfileService.resolve_contract_statutory_profile(
            contract_payroll_profile=self.contract_profile,
            scheme=self.scheme,
            profile_date=date(2026, 4, 10),
        )
        self.assertEqual(resolved_profile.id, profile.id)

        applicable = list(
            ContractStatutoryProfileService.list_applicable_schemes(
                contract_payroll_profile=self.contract_profile,
                profile_date=date(2026, 4, 10),
            )
        )
        self.assertEqual(len(applicable), 1)
        self.assertEqual(applicable[0].id, self.scheme.id)


class StatutoryFoundationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = PayrollFactory.user()
        self.client.force_authenticate(self.user)
        self.scope = PayrollFactory.entity_scope(user=self.user)
        self.scheme = StatutorySchemeService.create_or_update_scheme(
            {
                "code": "ESI_IN",
                "name": "ESI India",
                "scheme_type": StatutoryScheme.SchemeType.ESI,
                "country_code": "IN",
                "state_code": "",
                "is_system": True,
                "is_active": True,
            }
        )
        self.contract = PayrollFactory.hrms_contract(entity=self.scope["entity"], subentity=self.scope["subentity"])
        self.contract_profile = ContractPayrollProfileService.create_or_update_profile(
            {
                "entity": self.scope["entity"],
                "hrms_contract": self.contract,
                "pay_frequency": "MONTHLY",
                "payroll_status": "ACTIVE",
                "payroll_start_date": self.contract.payroll_effective_from,
                "is_active": True,
            }
        )

    @patch("core.entitlements.SubscriptionService.assert_entity_access")
    @patch("payroll.views.payroll_setup_views.PayrollPermissionService.has_entity_permission_access", return_value=True)
    def test_scheme_rule_registration_and_contract_profile_apis(self, _perm, _scope):
        scheme_response = self.client.post(
            f"/api/payroll/statutory/schemes/?entity={self.scope['entity'].id}",
            {
                "code": "PT_KA",
                "name": "Professional Tax Karnataka",
                "scheme_type": "PT",
                "country_code": "IN",
                "state_code": "KA",
                "is_system": False,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(scheme_response.status_code, 201, scheme_response.content)
        created_scheme_id = scheme_response.json()["id"]

        rules_response = self.client.post(
            f"/api/payroll/statutory/rules/?entity={self.scope['entity'].id}",
            {
                "entity": self.scope["entity"].id,
                "scheme": self.scheme.id,
                "rule_code": "ESI_MAIN",
                "rule_name": "ESI Main",
                "rule_type": "PERCENTAGE",
                "effective_from": "2026-04-01",
                "priority": 10,
                "rule_json": {"employee_rate": 0.75},
                "applicability_json": {"min_wage_dependent": False},
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(rules_response.status_code, 201, rules_response.content)
        rule_id = rules_response.json()["id"]

        slab_response = self.client.post(
            f"/api/payroll/statutory/rules/{rule_id}/slabs/?entity={self.scope['entity'].id}",
            {
                "slab_from": "0.00",
                "slab_to": "21000.00",
                "percentage": "0.75",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(slab_response.status_code, 201, slab_response.content)
        slab_id = slab_response.json()["id"]

        registration_response = self.client.post(
            "/api/payroll/statutory/registrations/",
            {
                "entity": self.scope["entity"].id,
                "scheme": created_scheme_id,
                "registration_number": "PT-KA-1001",
                "registration_state": "KA",
                "effective_from": "2026-04-01",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(registration_response.status_code, 201, registration_response.content)
        registration_id = registration_response.json()["id"]

        profile_response = self.client.post(
            "/api/payroll/statutory/contract-profiles/",
            {
                "contract_payroll_profile": str(self.contract_profile.id),
                "scheme": self.scheme.id,
                "is_applicable": True,
                "effective_from": "2026-04-01",
                "override_rule_json": {"employee_rate": 0.5},
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(profile_response.status_code, 201, profile_response.content)
        profile_id = profile_response.json()["id"]

        self.assertEqual(
            self.client.get(f"/api/payroll/statutory/schemes/?entity={self.scope['entity'].id}&is_active=true").status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/payroll/statutory/rules/{rule_id}/?entity={self.scope['entity'].id}",
                {"priority": 20},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/payroll/statutory/slabs/{slab_id}/?entity={self.scope['entity'].id}",
                {"amount": "350.00"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/payroll/statutory/registrations/{registration_id}/",
                {"registration_number": "PT-KA-1002"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/payroll/statutory/contract-profiles/{profile_id}/",
                {"is_applicable": False},
                format="json",
            ).status_code,
            200,
        )
