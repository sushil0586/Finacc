from django.core import mail
from django.test import TestCase
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import BankDetail, Constitution, Entity, EntityConstitutionV2, EntityFinancialYear, EntityOwnershipV2, GstRegistrationType, SubEntity
from entity.models import EntityBankAccountV2 as BankAccount
from entity.onboarding_serializers import EntityOnboardingCreateSerializer
from entity.onboarding_services import EntityOnboardingService
from entity.seeding import EntitySeedService
from financial.models import FinancialSettings, Ledger, account, accountHead
from rbac.models import Role as RbacRole
from rbac.models import UserRoleAssignment
from geography.models import City, Country, District, State
from subscriptions.models import CustomerAccount, CustomerSubscription, UserEntityAccess


class EntityContextV2Tests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="entity_user",
            email="entity_user@example.com",
            password="secret123",
        )
        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Karnataka", statecode="KA", country=self.country)
        self.district = District.objects.create(districtname="Bangalore", districtcode="BLR", state=self.state)
        self.city = City.objects.create(cityname="Bangalore", citycode="BLR", pincode="560001", distt=self.district)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.constitution = Constitution.objects.create(
            constitutionname="Private Limited",
            constitutiondesc="Private Limited",
            constcode="PVT",
            createdby=self.user,
        )
        self.bank = BankDetail.objects.create(bankname="ABC", bankcode="ABC", ifsccode="ABC0001")
        self.entity = Entity.objects.create(
            entityname="Demo Entity",
            entitydesc="Demo",
            legalname="Demo Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            address="Address",
            ownername="Owner",
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            bank=self.bank,
            phoneoffice="1234567890",
            phoneresidence="1234567890",
            const=self.constitution,
            createdby=self.user,
        )
        self.rbac_role = RbacRole.objects.create(
            entity=self.entity,
            name="Sales User",
            code="sales_user",
        )
        UserRoleAssignment.objects.create(
            user=self.user,
            entity=self.entity,
            role=self.rbac_role,
            is_primary=True,
        )
        self.client.force_authenticate(user=self.user)

    def test_me_entities_returns_role_context(self):
        response = self.client.get("/api/entity/me/entities")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["entityid"], self.entity.id)
        self.assertEqual(response.data[0]["roles"][0]["name"], "Sales User")


class EntityOnboardingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="onboard_user",
            email="onboard_user@example.com",
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
        self.client.force_authenticate(user=self.user)

    def test_new_onboarding_creates_entity_financial_and_rbac_defaults(self):
        payload = {
            "entity": {
                "entityname": "ABC Enterprises",
                "legalname": "ABC Enterprises",
                "GstRegitrationType": self.gst_type.id,
                "gstno": "03APXPB5894F1Z3",
                "panno": "APXPB5894F",
                "phoneoffice": "9855966534",
                "phoneresidence": "9855966534",
                "email": "abc@example.com",
                "address": "4369 GT Road",
                "address2": "Sirhind",
                "country": self.country.id,
                "state": self.state.id,
                "district": self.district.id,
                "city": self.city.id,
                "pincode": "140406",
                "const": self.constitution.id,
            },
            "financial_years": [
                {
                    "finstartyear": "2026-04-01T00:00:00Z",
                    "finendyear": "2027-03-31T00:00:00Z",
                    "desc": "FY 2026-27",
                    "isactive": True,
                }
            ],
            "bank_accounts": [
                {
                    "bank_name": "HDFC Bank",
                    "branch": "Sirhind",
                    "account_number": "1234567890",
                    "ifsc_code": "HDFC0001234",
                    "account_type": "current",
                    "is_primary": True,
                }
            ],
            "constitution_details": [
                {
                    "shareholder": "Owner Name",
                    "pan": "APXPB5894F",
                    "sharepercentage": "100.00",
                    "effective_from": "2026-04-01",
                    "effective_to": "2027-03-31",
                    "account_preference": "capital",
                    "agreement_reference": "Deed-001",
                }
            ],
            "ownership_details": [
                {
                    "ownership_type": "proprietor",
                    "name": "Owner Name",
                    "pan_number": "APXPB5894F",
                    "sharepercentage": "100.00",
                    "capital_contribution": "100000.00",
                    "effective_from": "2026-04-01",
                    "effective_to": "2027-03-31",
                    "account_preference": "capital",
                    "agreement_reference": "Deed-001",
                    "is_primary": True,
                }
            ],
            "seed_options": {
                "template_code": "indian_accounting_final",
                "seed_financial": True,
                "seed_rbac": True,
                "seed_default_subentity": True,
                "seed_default_roles": True,
            },
        }

        response = self.client.post("/api/entity/onboarding/create/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        entity = Entity.objects.get(id=response.data["entity_id"])
        self.assertEqual(entity.entityname, "ABC Enterprises")
        self.assertEqual(EntityFinancialYear.objects.filter(entity=entity).count(), 1)
        self.assertEqual(BankAccount.objects.filter(entity=entity).count(), 1)
        self.assertTrue(FinancialSettings.objects.filter(entity=entity).exists())
        self.assertTrue(accountHead.objects.filter(entity=entity, code=1000).exists())
        self.assertTrue(account.objects.filter(entity=entity, ledger__ledger_code=4000).exists())
        self.assertTrue(Ledger.objects.filter(entity=entity, ledger_code=4000).exists())
        self.assertTrue(UserRoleAssignment.objects.filter(entity=entity, user=self.user).exists())
        self.assertTrue(RbacRole.objects.filter(entity=entity, code="entity.super_admin").exists())
        self.assertIsNotNone(entity.customer_account_id)
        self.assertTrue(CustomerSubscription.objects.filter(customer_account=entity.customer_account).exists())
        self.assertTrue(UserEntityAccess.objects.filter(entity=entity, user=self.user, is_owner=True).exists())
        constitution = entity.constitutions_v2.first()
        self.assertIsNotNone(constitution)
        self.assertEqual(constitution.account_preference, "capital")
        self.assertEqual(constitution.agreement_reference, "Deed-001")
        ownership = entity.ownerships_v2.first()
        self.assertIsNotNone(ownership)
        self.assertEqual(ownership.account_preference, "capital")
        self.assertEqual(ownership.agreement_reference, "Deed-001")
        self.assertTrue(ownership.is_primary)

    def test_new_onboarding_derives_constitution_rows_from_ownership_rows(self):
        payload = {
            "entity": {
                "entityname": "Ownership Only Entity",
                "legalname": "Ownership Only Entity",
                "GstRegitrationType": self.gst_type.id,
                "gstno": "03APXPB5894F1Z3",
                "panno": "APXPB5894F",
                "phoneoffice": "9855966534",
                "phoneresidence": "9855966534",
                "email": "ownership@example.com",
                "address": "4369 GT Road",
                "address2": "Sirhind",
                "country": self.country.id,
                "state": self.state.id,
                "district": self.district.id,
                "city": self.city.id,
                "pincode": "140406",
                "const": self.constitution.id,
            },
            "financial_years": [
                {
                    "finstartyear": "2026-04-01T00:00:00Z",
                    "finendyear": "2027-03-31T00:00:00Z",
                    "desc": "FY 2026-27",
                    "isactive": True,
                }
            ],
            "ownership_details": [
                {
                    "ownership_type": "proprietor",
                    "name": "Owner Name",
                    "pan_number": "APXPB5894F",
                    "sharepercentage": "100.00",
                    "capital_contribution": "100000.00",
                    "effective_from": "2026-04-01",
                    "effective_to": "2027-03-31",
                    "account_preference": "capital",
                    "agreement_reference": "Deed-010",
                    "is_primary": True,
                }
            ],
            "seed_options": {
                "template_code": "indian_accounting_final",
                "seed_financial": True,
                "seed_rbac": True,
                "seed_default_subentity": True,
                "seed_default_roles": True,
            },
        }

        serializer = EntityOnboardingCreateSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        result = EntityOnboardingService.create_entity(actor=self.user, payload=serializer.validated_data)
        entity = result["entity"]
        self.assertEqual(entity.constitutions_v2.count(), 1)
        self.assertEqual(entity.ownerships_v2.count(), 1)
        self.assertEqual(entity.constitutions_v2.first().agreement_reference, "Deed-010")
        self.assertEqual(entity.ownerships_v2.first().agreement_reference, "Deed-010")
        self.assertTrue(entity.ownerships_v2.first().is_primary)

    def test_new_onboarding_rejects_gst_state_code_mismatch(self):
        other_state = State.objects.create(statename="Haryana", statecode="06", country=self.country)
        payload = {
            "entity": {
                "entityname": "Mismatch GST Entity",
                "legalname": "Mismatch GST Entity",
                "GstRegitrationType": self.gst_type.id,
                "gstno": "03APXPB5894F1Z3",
                "panno": "APXPB5894F",
                "phoneoffice": "9855966534",
                "phoneresidence": "9855966534",
                "email": "mismatch@example.com",
                "address": "4369 GT Road",
                "address2": "Sirhind",
                "country": self.country.id,
                "state": other_state.id,
                "district": self.district.id,
                "city": self.city.id,
                "pincode": "140406",
                "const": self.constitution.id,
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
                "template_code": "indian_accounting_final",
                "seed_financial": True,
                "seed_rbac": True,
                "seed_default_subentity": True,
                "seed_default_roles": True,
            },
        }

        response = self.client.post("/api/entity/onboarding/create/", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("gstno", response.data["entity"])
        self.assertIn("must match state code", str(response.data["entity"]["gstno"][0]))

    def test_unified_onboarding_submit_supports_authenticated_dashboard_creation(self):
        payload = {
            "entity": {
                "entityname": "Unified Dashboard Entity",
                "legalname": "Unified Dashboard Entity Pvt Ltd",
                "GstRegitrationType": self.gst_type.id,
                "gstno": "03APXPB5894F1Z3",
                "panno": "APXPB5894F",
                "phoneoffice": "9855966534",
                "phoneresidence": "9855966534",
                "email": "dashboard@example.com",
                "address": "4369 GT Road",
                "country": self.country.id,
                "state": self.state.id,
                "district": self.district.id,
                "city": self.city.id,
                "pincode": "140406",
                "const": self.constitution.id,
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
                "template_code": "indian_accounting_final",
                "seed_financial": True,
                "seed_rbac": True,
                "seed_default_subentity": True,
                "seed_default_roles": True,
            },
        }

        response = self.client.post("/api/entity/onboarding/submit/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["entity_name"], "Unified Dashboard Entity")
        entity = Entity.objects.get(id=response.data["entity_id"])
        self.assertTrue(FinancialSettings.objects.filter(entity=entity).exists())
        self.assertTrue(accountHead.objects.filter(entity=entity, accounttype__accounttypecode="1009").exists())
        self.assertTrue(Ledger.objects.filter(entity=entity, ledger_code=7000).exists())
        self.assertIn("posting_static_accounts", response.data)
        self.assertGreaterEqual(response.data["posting_static_accounts"]["created"], 0)

    def test_unified_onboarding_submit_supports_public_signup(self):
        self.client.force_authenticate(user=None)

        payload = {
            "user": {
                "email": "submitfounder@example.com",
                "username": "submitfounder@example.com",
                "first_name": "Submit",
                "last_name": "Founder",
                "password": "secret123",
            },
            "onboarding": {
                "entity": {
                    "entityname": "Submit Entity",
                    "legalname": "Submit Entity Pvt Ltd",
                    "GstRegitrationType": self.gst_type.id,
                    "gstno": "03APXPB5894F1Z3",
                    "panno": "APXPB5894F",
                    "phoneoffice": "9855966534",
                    "phoneresidence": "9855966534",
                    "email": "submitfounder@example.com",
                    "address": "4369 GT Road",
                    "country": self.country.id,
                    "state": self.state.id,
                    "district": self.district.id,
                    "city": self.city.id,
                    "pincode": "140406",
                    "const": self.constitution.id,
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
                    "template_code": "indian_accounting_final",
                    "seed_financial": True,
                    "seed_rbac": True,
                    "seed_default_subentity": True,
                    "seed_default_roles": True,
                },
            },
        }

        response = self.client.post("/api/entity/onboarding/submit/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["user"]["email"], "submitfounder@example.com")
        self.assertEqual(response.data["onboarding"]["entity_name"], "Submit Entity")

    def test_onboarding_meta_returns_bootstrap_dropdowns(self):
        response = self.client.get("/api/entity/onboarding/meta/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["defaults"]["seed_options"]["template_code"], "indian_accounting_final")
        self.assertTrue(len(response.data["dropdowns"]["gst_registration_types"]) >= 1)
        self.assertTrue(len(response.data["dropdowns"]["constitutions"]) >= 1)
        self.assertTrue(len(response.data["dropdowns"]["countries"]) >= 1)

    def test_onboarding_meta_is_public(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/entity/onboarding/meta/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("dropdowns", response.data)

    def test_onboarding_state_options_can_be_filtered_by_country(self):
        response = self.client.get(f"/api/entity/onboarding/options/states/?country_id={self.country.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.state.id)

    def test_entity_seed_service_is_idempotent(self):
        first = EntitySeedService.seed_master_data(actor=self.user)
        second = EntitySeedService.seed_master_data(actor=self.user)

        self.assertEqual(first, second)
        self.assertGreaterEqual(GstRegistrationType.objects.count(), first["gst_registration_type_count"])
        self.assertGreaterEqual(Constitution.objects.count(), first["constitution_count"])

    def test_onboarding_detail_returns_bootstrap_payload_for_edit(self):
        entity = Entity.objects.create(
            entityname="Existing Entity",
            legalname="Existing Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            gstno="03APXPB5894F1Z3",
            panno="APXPB5894F",
            phoneoffice="9855966534",
            phoneresidence="9855966534",
            email="existing@example.com",
            address="Main Road",
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            pincode="140406",
            const=self.constitution,
            createdby=self.user,
        )
        fy = EntityFinancialYear.objects.create(
            entity=entity,
            createdby=self.user,
            desc="FY 2026-27",
            finstartyear="2026-04-01T00:00:00Z",
            finendyear="2027-03-31T00:00:00Z",
            isactive=True,
        )
        bank = BankAccount.objects.create(
            entity=entity,
            bank_name="HDFC Bank",
            branch="Sirhind",
            account_number="1234567890",
            ifsc_code="HDFC0001234",
            account_type="current",
            is_primary=True,
        )
        subentity = SubEntity.objects.create(
            entity=entity,
            subentityname="Main Branch",
            address="Main Road",
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            pincode="140406",
            phoneoffice="9855966534",
            phoneresidence="9855966534",
            email="branch@example.com",
            ismainentity=True,
        )
        constitution = EntityConstitutionV2.objects.create(
            entity=entity,
            createdby=self.user,
            shareholder="Owner",
            pan="APXPB5894F",
            share_percentage="100.00",
            account_preference="capital",
            agreement_reference="Deed-002",
        )
        ownership = EntityOwnershipV2.objects.create(
            entity=entity,
            createdby=self.user,
            ownership_type="proprietor",
            name="Owner",
            pan_number="APXPB5894F",
            share_percentage="100.00",
            capital_contribution="100000.00",
            account_preference="capital",
            agreement_reference="Deed-002",
            is_primary=True,
        )

        response = self.client.get(f"/api/entity/onboarding/entity/{entity.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["entity_id"], entity.id)
        self.assertEqual(response.data["financial_years"][0]["id"], fy.id)
        self.assertEqual(response.data["bank_accounts"][0]["id"], bank.id)
        self.assertEqual(response.data["subentities"][0]["id"], subentity.id)
        self.assertEqual(response.data["constitution_details"][0]["id"], constitution.id)
        self.assertEqual(response.data["ownership_details"][0]["id"], ownership.id)
        self.assertEqual(response.data["constitution_details"][0]["account_preference"], "capital")
        self.assertEqual(response.data["constitution_details"][0]["agreement_reference"], "Deed-002")
        self.assertEqual(response.data["ownership_details"][0]["account_preference"], "capital")
        self.assertEqual(response.data["ownership_details"][0]["agreement_reference"], "Deed-002")

    def test_onboarding_detail_can_update_nested_entity_payload(self):
        entity = Entity.objects.create(
            entityname="Existing Entity",
            legalname="Existing Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            phoneoffice="9855966534",
            phoneresidence="9855966534",
            email="existing@example.com",
            address="Main Road",
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            pincode="140406",
            const=self.constitution,
            createdby=self.user,
        )
        fy = EntityFinancialYear.objects.create(
            entity=entity,
            createdby=self.user,
            desc="FY 2026-27",
            finstartyear="2026-04-01T00:00:00Z",
            finendyear="2027-03-31T00:00:00Z",
            isactive=True,
        )
        bank = BankAccount.objects.create(
            entity=entity,
            bank_name="HDFC Bank",
            branch="Sirhind",
            account_number="1234567890",
            ifsc_code="HDFC0001234",
            account_type="current",
            is_primary=True,
        )

        payload = {
            "entity": {
                "entityname": "Updated Entity",
                "legalname": "Updated Entity Pvt Ltd",
                "GstRegitrationType": self.gst_type.id,
                "phoneoffice": "9999999999",
                "phoneresidence": "9999999999",
                "email": "updated@example.com",
                "address": "Updated Road",
                "country": self.country.id,
                "state": self.state.id,
                "district": self.district.id,
                "city": self.city.id,
                "pincode": "140406",
                "const": self.constitution.id,
            },
            "financial_years": [
                {
                    "id": fy.id,
                    "desc": "FY 2026-27 Updated",
                    "finstartyear": "2026-04-01T00:00:00Z",
                    "finendyear": "2027-03-31T00:00:00Z",
                    "isactive": True,
                }
            ],
            "bank_accounts": [
                {
                    "id": bank.id,
                    "bank_name": "ICICI Bank",
                    "branch": "Patiala",
                    "account_number": "9999999999",
                    "ifsc_code": "ICIC0009999",
                    "account_type": "current",
                    "is_primary": True,
                }
            ],
        }

        response = self.client.put(f"/api/entity/onboarding/entity/{entity.id}/", payload, format="json")

        self.assertEqual(response.status_code, 200)
        entity.refresh_from_db()
        bank.refresh_from_db()
        fy.refresh_from_db()
        self.assertEqual(entity.entityname, "Updated Entity")
        self.assertEqual(bank.bank_name, "ICICI Bank")
        self.assertEqual(fy.desc, "FY 2026-27 Updated")


class RegisterAndEntityOnboardingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Punjab", statecode="03", country=self.country)
        self.district = District.objects.create(districtname="Fatehgarh", districtcode="FGS", state=self.state)
        self.city = City.objects.create(cityname="Sirhind", citycode="SRH", pincode="140406", distt=self.district)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.seed_user = User.objects.create_user(
            username="seed_user",
            email="seed_user@example.com",
            password="secret123",
        )
        self.constitution = Constitution.objects.create(
            constitutionname="Proprietorship",
            constitutiondesc="Proprietorship",
            constcode="01",
            createdby=self.seed_user,
        )

    def test_register_and_onboard_creates_user_entity_tokens_and_rbac(self):
        payload = {
            "user": {
                "email": "founder@example.com",
                "username": "founder@example.com",
                "first_name": "Founding",
                "last_name": "User",
                "password": "secret123",
            },
            "onboarding": {
                "entity": {
                    "entityname": "New Entity",
                    "legalname": "New Entity Pvt Ltd",
                    "GstRegitrationType": self.gst_type.id,
                    "gstno": "03APXPB5894F1Z3",
                    "panno": "APXPB5894F",
                    "phoneoffice": "9855966534",
                    "phoneresidence": "9855966534",
                    "email": "founder@example.com",
                    "address": "4369 GT Road",
                    "address2": "Sirhind",
                    "country": self.country.id,
                    "state": self.state.id,
                    "district": self.district.id,
                    "city": self.city.id,
                    "pincode": "140406",
                    "const": self.constitution.id,
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
                    "template_code": "indian_accounting_final",
                    "seed_financial": True,
                    "seed_rbac": True,
                    "seed_default_subentity": True,
                    "seed_default_roles": True,
                },
            },
        }

        response = self.client.post("/api/entity/onboarding/register/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertIn("subscription", response.data)
        self.assertIn("subscription", response.data["onboarding"])
        self.assertEqual(response.data["intent"], "standard")
        self.assertFalse(response.data["verification"]["email_verified"])
        self.assertTrue(response.data["verification"]["verification_required"])
        self.assertEqual(len(mail.outbox), 1)
        user = User.objects.get(email="founder@example.com")
        self.assertEqual(response.data["user"]["id"], user.id)
        entity = Entity.objects.get(id=response.data["onboarding"]["entity_id"])
        self.assertEqual(entity.createdby, user)
        self.assertTrue(UserRoleAssignment.objects.filter(entity=entity, user=user).exists())
        self.assertTrue(CustomerAccount.objects.filter(primary_user=user).exists())
        self.assertTrue(UserEntityAccess.objects.filter(entity=entity, user=user, is_owner=True).exists())

    def test_register_and_onboard_accepts_trial_intent(self):
        payload = {
            "intent": "trial",
            "user": {
                "email": "trialfounder@example.com",
                "username": "trialfounder@example.com",
                "first_name": "Trial",
                "last_name": "Founder",
                "password": "secret123",
            },
            "onboarding": {
                "entity": {
                    "entityname": "Trial Entity",
                    "legalname": "Trial Entity Pvt Ltd",
                    "GstRegitrationType": self.gst_type.id,
                    "gstno": "03APXPB5894F1Z3",
                    "panno": "APXPB5894F",
                    "phoneoffice": "9855966534",
                    "phoneresidence": "9855966534",
                    "email": "trialfounder@example.com",
                    "address": "4369 GT Road",
                    "country": self.country.id,
                    "state": self.state.id,
                    "district": self.district.id,
                    "city": self.city.id,
                    "pincode": "140406",
                    "const": self.constitution.id,
                },
                "financial_years": [
                    {
                        "finstartyear": "2026-04-01T00:00:00Z",
                        "finendyear": "2027-03-31T00:00:00Z",
                        "desc": "FY 2026-27",
                        "isactive": True,
                    }
                ],
            },
        }

        response = self.client.post("/api/entity/onboarding/register/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["intent"], "trial")
        self.assertEqual(response.data["subscription"]["subscription"]["status"], "trial")

    def test_register_and_onboard_accepts_flat_public_payload_shape(self):
        payload = {
            "user": {
                "email": "flatfounder@example.com",
                "username": "flatfounder@example.com",
                "first_name": "Flat",
                "last_name": "Founder",
                "password": "secret123",
            },
            "entity": {
                "entityname": "Flat Entity",
                "legalname": "Flat Entity Pvt Ltd",
                "GstRegitrationType": self.gst_type.id,
                "gstno": "03APXPB5894F1Z3",
                "panno": "APXPB5894F",
                "phoneoffice": "9855966534",
                "phoneresidence": "9855966534",
                "email": "flatfounder@example.com",
                "address": "4369 GT Road",
                "country": self.country.id,
                "state": self.state.id,
                "district": self.district.id,
                "city": self.city.id,
                "pincode": "140406",
                "const": self.constitution.id,
                "financial_years": [
                    {
                        "finstartyear": "2026-04-01T00:00:00Z",
                        "finendyear": "2027-03-31T00:00:00Z",
                        "desc": "FY 2026-27",
                        "isactive": True,
                        "period_status": "OPEN",
                    }
                ],
                "bank_accounts": [
                    {
                        "bank_name": "HDFC Bank",
                        "branch": "Sirhind",
                        "account_number": "1234567890",
                        "ifsc_code": "HDFC0001234",
                        "account_type": "current",
                        "is_primary": True,
                    }
                ],
            },
        }

        response = self.client.post("/api/entity/onboarding/register/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["user"]["email"], "flatfounder@example.com")
