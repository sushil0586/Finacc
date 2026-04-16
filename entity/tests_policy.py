from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from Authentication.models import User
from entity.models import Constitution, Entity, EntityPolicy, GstRegistrationType
from entity.onboarding_services import EntityOnboardingService
from geography.models import City, Country, District, State


class EntityPolicyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="policy_user",
            email="policy_user@example.com",
            password="secret123",
        )
        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Punjab", statecode="03", country=self.country)
        self.district = District.objects.create(districtname="Fatehgarh", districtcode="FGS", state=self.state)
        self.city = City.objects.create(cityname="Sirhind", citycode="SRH", pincode="140406", distt=self.district)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.constitution = Constitution.objects.create(
            constitutionname="Proprietorship",
            constitutiondesc="Proprietorship",
            constcode="01",
            createdby=self.user,
        )

    def _payload(self):
        return {
            "entity": {
                "entityname": "Policy Entity",
                "legalname": "Policy Entity Pvt Ltd",
                "GstRegitrationType": self.gst_type,
                "gstno": "03APXPB5894F1Z3",
                "panno": "APXPB5894F",
                "phoneoffice": "9855966534",
                "phoneresidence": "9855966534",
                "email": "policy@example.com",
                "address": "4369 GT Road",
                "address2": "Sirhind",
                "country": self.country,
                "state": self.state,
                "district": self.district,
                "city": self.city,
                "pincode": "140406",
                "const": self.constitution,
            },
            "financial_years": [
                {
                    "finstartyear": "2026-04-01T00:00:00Z",
                    "finendyear": "2027-03-31T00:00:00Z",
                    "desc": "FY 2026-27",
                    "isactive": True,
                }
            ],
            "seed_options": {
                "seed_financial": False,
                "seed_rbac": False,
                "seed_default_subentity": True,
                "seed_numbering": False,
            },
        }

    def test_create_entity_seeds_default_policy(self):
        result = EntityOnboardingService.create_entity(actor=self.user, payload=self._payload())
        entity = result["entity"]

        policy = EntityPolicy.objects.get(entity=entity)
        self.assertEqual(policy.gstin_state_match_mode, EntityPolicy.ValidationMode.HARD)
        self.assertEqual(policy.require_subentity_mode, EntityPolicy.ValidationMode.HARD)
        self.assertEqual(policy.require_head_office_subentity_mode, EntityPolicy.ValidationMode.HARD)
        self.assertEqual(policy.require_entity_primary_gstin_mode, EntityPolicy.ValidationMode.HARD)
        self.assertEqual(policy.subentity_gstin_state_match_mode, EntityPolicy.ValidationMode.HARD)

    def test_update_entity_persists_policy_overrides(self):
        result = EntityOnboardingService.create_entity(actor=self.user, payload=self._payload())
        entity = result["entity"]

        detail = EntityOnboardingService.update_entity(
            actor=self.user,
            entity=entity,
            payload={
                "policy": {
                    "gstin_state_match_mode": "soft",
                    "require_subentity_mode": "hard",
                    "require_head_office_subentity_mode": "soft",
                    "require_entity_primary_gstin_mode": "off",
                    "subentity_gstin_state_match_mode": "soft",
                    "metadata": {"phase": "phase2"},
                }
            },
        )

        self.assertEqual(detail["policy"]["gstin_state_match_mode"], "soft")
        self.assertEqual(detail["policy"]["require_head_office_subentity_mode"], "soft")
        self.assertEqual(detail["policy"]["require_entity_primary_gstin_mode"], "off")
        self.assertEqual(detail["policy"]["subentity_gstin_state_match_mode"], "soft")
        self.assertEqual(detail["policy"]["metadata"]["phase"], "phase2")

    def test_create_entity_promotes_first_subentity_to_head_office_when_missing(self):
        payload = self._payload()
        payload["subentities"] = [
            {
                "subentityname": "Ludhiana Branch",
                "branch_type": "branch",
                "address": "Industrial Area",
                "country": self.country,
                "state": self.state,
                "district": self.district,
                "city": self.city,
                "pincode": "140406",
            }
        ]

        result = EntityOnboardingService.create_entity(actor=self.user, payload=payload)
        subentity = result["entity"].subentity.get()

        self.assertTrue(subentity.is_head_office)
        self.assertEqual(subentity.branch_type, "head_office")

    def test_update_entity_rejects_multiple_head_offices_when_policy_is_hard(self):
        payload = self._payload()
        payload["subentities"] = [
            {
                "subentityname": "Head Office",
                "is_head_office": True,
                "country": self.country,
                "state": self.state,
                "district": self.district,
                "city": self.city,
            },
            {
                "subentityname": "Branch Office",
                "country": self.country,
                "state": self.state,
                "district": self.district,
                "city": self.city,
            },
        ]
        result = EntityOnboardingService.create_entity(actor=self.user, payload=payload)
        entity = result["entity"]
        rows = list(entity.subentity.order_by("id"))

        with self.assertRaises(DjangoValidationError) as exc:
            EntityOnboardingService.update_entity(
                actor=self.user,
                entity=entity,
                payload={
                    "subentities": [
                        {
                            "id": rows[0].id,
                            "subentityname": rows[0].subentityname,
                            "is_head_office": True,
                            "country": self.country,
                            "state": self.state,
                            "district": self.district,
                            "city": self.city,
                        },
                        {
                            "id": rows[1].id,
                            "subentityname": rows[1].subentityname,
                            "is_head_office": True,
                            "country": self.country,
                            "state": self.state,
                            "district": self.district,
                            "city": self.city,
                        },
                    ]
                },
            )
        self.assertIn("Only one active head office is allowed per entity.", str(exc.exception))

    def test_hard_policy_rejects_subentity_gstin_state_mismatch(self):
        other_state = State.objects.create(statename="Haryana", statecode="06", country=self.country)
        payload = self._payload()
        payload["subentities"] = [
            {
                "subentityname": "Head Office",
                "is_head_office": True,
                "country": self.country,
                "state": other_state,
                "district": self.district,
                "city": self.city,
                "gstno": "03APXPB5894F1Z3",
                "GstRegitrationType": self.gst_type,
            }
        ]

        with self.assertRaises(ValidationError) as exc:
            EntityOnboardingService.create_entity(actor=self.user, payload=payload)

        self.assertIn("does not match state code", str(exc.exception))

    def test_soft_policy_returns_warning_for_subentity_gstin_state_mismatch(self):
        other_state = State.objects.create(statename="Haryana", statecode="06", country=self.country)
        payload = self._payload()
        payload["policy"] = {
            "subentity_gstin_state_match_mode": "soft",
        }
        payload["subentities"] = [
            {
                "subentityname": "Head Office",
                "is_head_office": True,
                "country": self.country,
                "state": other_state,
                "district": self.district,
                "city": self.city,
                "gstno": "03APXPB5894F1Z3",
                "GstRegitrationType": self.gst_type,
            }
        ]

        result = EntityOnboardingService.create_entity(actor=self.user, payload=payload)

        self.assertTrue(
            any(
                warning["code"] == "subentity.gstin_state_mismatch"
                for warning in result["validation_warnings"]
            )
        )

    def test_off_policy_suppresses_subentity_gstin_state_warning(self):
        other_state = State.objects.create(statename="Haryana", statecode="06", country=self.country)
        payload = self._payload()
        payload["policy"] = {
            "subentity_gstin_state_match_mode": "off",
        }
        payload["subentities"] = [
            {
                "subentityname": "Head Office",
                "is_head_office": True,
                "country": self.country,
                "state": other_state,
                "district": self.district,
                "city": self.city,
                "gstno": "03APXPB5894F1Z3",
                "GstRegitrationType": self.gst_type,
            }
        ]

        result = EntityOnboardingService.create_entity(actor=self.user, payload=payload)

        self.assertFalse(
            any(
                warning["code"] == "subentity.gstin_state_mismatch"
                for warning in result["validation_warnings"]
            )
        )

    def test_entity_address_rejects_mismatched_city_state_hierarchy(self):
        other_state = State.objects.create(statename="Haryana", statecode="06", country=self.country)
        entity = Entity.objects.create(
            entityname="Geo Entity",
            legalname="Geo Entity Pvt Ltd",
            createdby=self.user,
        )

        with self.assertRaises(DjangoValidationError):
            entity.addresses.create(
                address_type="registered",
                line1="Address 1",
                country=self.country,
                state=other_state,
                district=self.district,
                city=self.city,
                pincode="140406",
                is_primary=True,
                isactive=True,
                createdby=self.user,
            )
