from datetime import date, datetime, timezone as dt_timezone
from io import StringIO

from django.core.management import call_command
from django.core import mail
from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from Authentication.models import User
from assets.models import AssetCategory, DepreciationRun, DepreciationRunLine, FixedAsset
from catalog.models import Product, ProductCategory, ProductPurchaseBehavior, UnitOfMeasure
from entity.models import BankDetail, Constitution, Entity, EntityConstitutionV2, EntityFinancialYear, EntityOwnershipV2, GstRegistrationType, SubEntity, gstin_validator
from entity.models import EntityBankAccountV2 as BankAccount
from entity.onboarding_serializers import EntityOnboardingCreateSerializer, EntityOnboardingUpdateSerializer
from entity.onboarding_services import EntityOnboardingService
from entity.seeding import EntitySeedService
from financial.models import FinancialSettings, Ledger, account, accountHead
from purchase.models.purchase_core import PurchaseInvoiceHeader
from rbac.models import Role as RbacRole
from rbac.models import UserRoleAssignment
from geography.models import City, Country, District, State
from numbering.models import DocumentNumberSeries, DocumentType
from sales.models.mastergst_models import MasterGSTEnvironment, MasterGSTServiceScope, SalesMasterGSTCredential
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


class EntityGstinValidationTests(TestCase):
    @override_settings(MASTERGST_ENV="PRODUCTION", SALES_MASTERGST_ENV="PRODUCTION", ALLOW_RELAXED_GSTIN_FOR_SANDBOX=False)
    def test_strict_gstin_validator_rejects_sandbox_suffix_in_normal_mode(self):
        with self.assertRaises(ValidationError):
            gstin_validator("29AAGCB1286Q000")

    @override_settings(SALES_MASTERGST_ENV="SANDBOX")
    def test_sandbox_gstin_validator_allows_provider_pseudo_gstin(self):
        gstin_validator("29AAGCB1286Q000")

    @override_settings(SALES_MASTERGST_ENV="SANDBOX")
    def test_sandbox_onboarding_subentity_serializer_allows_gstin_state_mismatch(self):
        country = Country.objects.create(countryname="India", countrycode="IN")
        punjab = State.objects.create(statename="Punjab", statecode="03", country=country)
        district = District.objects.create(districtname="Fatehgarh", districtcode="FGS", state=punjab)
        city = City.objects.create(cityname="Sirhind", citycode="SRH", pincode="140406", distt=district)
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")

        serializer = EntityOnboardingCreateSerializer(
            data={
                "entity": {
                    "entityname": "Sandbox Entity",
                    "legalname": "Sandbox Entity",
                    "phoneoffice": "9855966534",
                    "phoneresidence": "9855966534",
                    "address": "GT Road",
                    "country": country.id,
                    "state": punjab.id,
                    "district": district.id,
                    "city": city.id,
                    "gstno": "29AAGCB1286Q000",
                },
                "subentities": [
                    {
                        "subentityname": "Head Office",
                        "branch_type": "head_office",
                        "gstno": "29AAGCB1286Q000",
                        "GstRegitrationType": gst_type.id,
                        "country": country.id,
                        "state": punjab.id,
                        "district": district.id,
                        "city": city.id,
                    }
                ],
                "financial_years": [
                    {
                        "finstartyear": "2026-04-01T00:00:00Z",
                        "finendyear": "2027-03-31T00:00:00Z",
                        "desc": "FY 2026-27",
                        "isactive": True,
                    }
                ],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)


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

    def test_onboarding_meta_includes_compliance_credentials_contract(self):
        response = self.client.get("/api/entity/onboarding/meta/")

        self.assertEqual(response.status_code, 200)
        root_keys = response.data["payload_contract"]["root_keys"]
        self.assertIn("compliance_credentials", root_keys)
        self.assertIn("compliance_credentials", response.data["payload_contract"]["arrays_allow_empty"])
        self.assertTrue(any(row["label"] == "Sandbox" for row in response.data["dropdowns"]["mastergst_environments"]))
        self.assertTrue(any(row["label"] == "E-Invoice" for row in response.data["dropdowns"]["mastergst_service_scopes"]))

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
            "compliance_credentials": [
                {
                    "environment": int(MasterGSTEnvironment.SANDBOX),
                    "service_scope": int(MasterGSTServiceScope.EINVOICE),
                    "client_id": "sandbox-client",
                    "client_secret": "sandbox-secret",
                    "email": "compliance@example.com",
                    "gst_username": "sandbox-user",
                    "gst_password": "sandbox-password",
                    "allow_all_ips": True,
                    "is_active": True,
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
        self.assertEqual(response.data["entity_name"], "ABC Enterprises")
        self.assertEqual(response.data["gstno"], "03APXPB5894F1Z3")
        self.assertEqual(entity.entityname, "ABC Enterprises")
        self.assertEqual(EntityFinancialYear.objects.filter(entity=entity).count(), 1)
        self.assertEqual(BankAccount.objects.filter(entity=entity).count(), 1)
        self.assertTrue(FinancialSettings.objects.filter(entity=entity).exists())
        self.assertTrue(accountHead.objects.filter(entity=entity, code=1000).exists())
        self.assertTrue(account.objects.filter(entity=entity, ledger__ledger_code=4000).exists())

        subentity = SubEntity.objects.filter(entity=entity).order_by("id").first()
        self.assertIsNotNone(subentity)

        cash_doc_type = DocumentType.objects.get(module="vouchers", doc_key="CASH_VOUCHER")
        bank_doc_type = DocumentType.objects.get(module="vouchers", doc_key="BANK_VOUCHER")

        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=entity,
                entityfinid__entity=entity,
                subentity=subentity,
                doc_type=cash_doc_type,
                doc_code="CV",
            ).exists()
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=entity,
                entityfinid__entity=entity,
                subentity=subentity,
                doc_type=bank_doc_type,
                doc_code="BV",
            ).exists()
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=entity,
                entityfinid__entity=entity,
                subentity__isnull=True,
                doc_type=cash_doc_type,
                doc_code="CV",
            ).exists()
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=entity,
                entityfinid__entity=entity,
                subentity__isnull=True,
                doc_type=bank_doc_type,
                doc_code="BV",
            ).exists()
        )
        self.assertTrue(Ledger.objects.filter(entity=entity, ledger_code=4000).exists())
        self.assertTrue(UserRoleAssignment.objects.filter(entity=entity, user=self.user).exists())
        self.assertTrue(RbacRole.objects.filter(entity=entity, code="entity.super_admin").exists())
        self.assertIsNotNone(entity.customer_account_id)
        self.assertTrue(CustomerSubscription.objects.filter(customer_account=entity.customer_account).exists())
        self.assertTrue(
            UserEntityAccess.objects.filter(
                customer_account=entity.customer_account,
                user=self.user,
                role=UserEntityAccess.Role.OWNER,
                is_active=True,
            ).exists()
        )
        credential = SalesMasterGSTCredential.objects.get(
            entity=entity,
            environment=MasterGSTEnvironment.SANDBOX,
            service_scope=MasterGSTServiceScope.EINVOICE,
        )
        self.assertEqual(credential.gstin, "03APXPB5894F1Z3")
        self.assertEqual(credential.client_id, "sandbox-client")
        self.assertEqual(credential.email, "compliance@example.com")
        self.assertEqual(credential.gst_username, "sandbox-user")
        self.assertEqual(credential.get_client_secret(), "sandbox-secret")
        self.assertEqual(credential.get_gst_password(), "sandbox-password")
        constitution = entity.constitutions_v2.first()
        self.assertIsNotNone(constitution)
        self.assertEqual(constitution.account_preference, "capital")
        self.assertEqual(constitution.agreement_reference, "Deed-001")
        ownership = entity.ownerships_v2.first()
        self.assertIsNotNone(ownership)
        self.assertEqual(ownership.account_preference, "capital")
        self.assertEqual(ownership.agreement_reference, "Deed-001")
        self.assertTrue(ownership.is_primary)

    def test_onboarding_rejects_oversized_nested_fields(self):
        payload = {
            "entity": {
                "entityname": "E" * 101,
                "legalname": "L" * 101,
                "entity_code": "C" * 31,
                "trade_name": "T" * 151,
                "short_name": "S" * 51,
                "phoneoffice": "9" * 21,
                "phoneresidence": "9" * 21,
                "address": "A" * 101,
                "address2": "B" * 101,
                "addressfloorno": "F" * 51,
                "addressstreet": "S" * 101,
                "country": self.country.id,
                "state": self.state.id,
                "district": self.district.id,
                "city": self.city.id,
                "pincode": "1" * 51,
                "panno": "P" * 21,
                "tds": "T" * 21,
                "tdscircle": "C" * 21,
                "tan_no": "T" * 21,
                "cin_no": "C" * 22,
                "llpin_no": "L" * 9,
                "udyam_no": "U" * 31,
                "iec_code": "I" * 11,
                "gstno": "G" * 21,
                "gstintype": "R" * 21,
                "nature_of_business": "N" * 151,
                "blockstatus": "B" * 11,
            },
            "financial_years": [
                {
                    "finstartyear": "2026-04-01T00:00:00Z",
                    "finendyear": "2027-03-31T00:00:00Z",
                    "desc": "FY 2026-27",
                    "isactive": True,
                }
            ],
            "subentities": [
                {
                    "subentityname": "S" * 256,
                    "subentity_code": "C" * 31,
                    "address": "A" * 256,
                    "address2": "B" * 256,
                    "addressfloorno": "F" * 51,
                    "addressstreet": "S" * 101,
                    "pincode": "1" * 256,
                    "phoneoffice": "9" * 256,
                    "phoneresidence": "9" * 256,
                    "mobile_primary": "9" * 21,
                    "mobile_secondary": "9" * 21,
                    "contact_person_name": "P" * 101,
                    "contact_person_designation": "D" * 101,
                    "gstno": "G" * 21,
                    "country": self.country.id,
                    "state": self.state.id,
                    "district": self.district.id,
                    "city": self.city.id,
                }
            ],
            "ownership_details": [
                {
                    "name": "N" * 101,
                    "mobile": "9" * 21,
                    "pan_number": "P" * 11,
                    "agreement_reference": "A" * 256,
                    "designation": "D" * 101,
                    "remarks": "R" * 2000,
                }
            ],
            "compliance_credentials": [
                {
                    "environment": int(MasterGSTEnvironment.SANDBOX),
                    "service_scope": int(MasterGSTServiceScope.EINVOICE),
                    "client_id": "C" * 129,
                    "client_secret": "S" * 257,
                    "email": "cred@example.com",
                    "gst_username": "U" * 129,
                    "gst_password": "P" * 257,
                }
            ],
        }

        response = self.client.post("/api/entity/onboarding/create/", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("entity", response.data)
        self.assertIn("subentities", response.data)
        self.assertIn("ownership_details", response.data)
        self.assertIn("compliance_credentials", response.data)

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

    def test_update_entity_syncs_compliance_credential_gstin_from_primary_entity_gstin(self):
        payload = {
            "entity": {
                "entityname": "Sync GST Entity",
                "legalname": "Sync GST Entity",
                "GstRegitrationType": self.gst_type.id,
                "gstno": "03APXPB5894F1Z3",
                "panno": "APXPB5894F",
                "phoneoffice": "9855966534",
                "phoneresidence": "9855966534",
                "email": "sync@example.com",
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
            "compliance_credentials": [
                {
                    "environment": int(MasterGSTEnvironment.SANDBOX),
                    "service_scope": int(MasterGSTServiceScope.EINVOICE),
                    "client_id": "sandbox-client",
                    "client_secret": "sandbox-secret",
                    "email": "compliance@example.com",
                    "gst_username": "sandbox-user",
                    "gst_password": "sandbox-password",
                    "allow_all_ips": True,
                    "is_active": True,
                }
            ],
        }

        serializer = EntityOnboardingCreateSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        result = EntityOnboardingService.create_entity(actor=self.user, payload=serializer.validated_data)
        entity = result["entity"]

        patch_serializer = EntityOnboardingUpdateSerializer(
            data={"entity": {"gstno": "29AAGCB1286Q000", "state": self.state.id}},
            partial=True,
        )
        self.assertTrue(patch_serializer.is_valid(), patch_serializer.errors)
        EntityOnboardingService.update_entity(actor=self.user, entity=entity, payload=patch_serializer.validated_data)

        credential = SalesMasterGSTCredential.objects.get(entity=entity)
        self.assertEqual(credential.gstin, "29AAGCB1286Q000")

    @override_settings(MASTERGST_ENV="PRODUCTION", SALES_MASTERGST_ENV="PRODUCTION", ALLOW_RELAXED_GSTIN_FOR_SANDBOX=False)
    def test_new_onboarding_rejects_gst_state_code_mismatch(self):
        other_state = State.objects.create(statename="Haryana", statecode="06", country=self.country)
        other_district = District.objects.create(districtname="Ambala", districtcode="AMB", state=other_state)
        other_city = City.objects.create(cityname="Ambala", citycode="AMB", pincode="133001", distt=other_district)
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
                "district": other_district.id,
                "city": other_city.id,
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
        create_result = EntityOnboardingService.create_entity(
            actor=self.user,
            payload={
                "entity": {
                    "entityname": "Existing Entity",
                    "legalname": "Existing Entity Pvt Ltd",
                    "GstRegitrationType": self.gst_type,
                    "gstno": "03APXPB5894F1Z3",
                    "panno": "APXPB5894F",
                    "phoneoffice": "9855966534",
                    "phoneresidence": "9855966534",
                    "email": "existing@example.com",
                    "address": "Main Road",
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
                "subentities": [
                    {
                        "subentityname": "Main Branch",
                        "address": "Main Road",
                        "country": self.country,
                        "state": self.state,
                        "district": self.district,
                        "city": self.city,
                        "pincode": "140406",
                        "phoneoffice": "9855966534",
                        "phoneresidence": "9855966534",
                        "email": "branch@example.com",
                        "is_head_office": True,
                    }
                ],
                "constitution_details": [
                    {
                        "shareholder": "Owner",
                        "pan": "APXPB5894F",
                        "sharepercentage": "100.00",
                        "account_preference": "capital",
                        "agreement_reference": "Deed-002",
                    }
                ],
                "ownership_details": [
                    {
                        "ownership_type": "proprietor",
                        "name": "Owner",
                        "pan_number": "APXPB5894F",
                        "sharepercentage": "100.00",
                        "capital_contribution": "100000.00",
                        "account_preference": "capital",
                        "agreement_reference": "Deed-002",
                        "is_primary": True,
                    }
                ],
            },
        )
        entity = create_result["entity"]
        fy = entity.fy.first()
        bank = entity.bank_accounts_v2.first()
        subentity = entity.subentity.first()
        constitution = entity.constitutions_v2.first()
        ownership = entity.ownerships_v2.first()

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
        create_result = EntityOnboardingService.create_entity(
            actor=self.user,
            payload={
                "entity": {
                    "entityname": "Existing Entity",
                    "legalname": "Existing Entity Pvt Ltd",
                    "GstRegitrationType": self.gst_type,
                    "phoneoffice": "9855966534",
                    "phoneresidence": "9855966534",
                    "email": "existing@example.com",
                    "address": "Main Road",
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
        )
        entity = create_result["entity"]
        fy = entity.fy.first()
        bank = entity.bank_accounts_v2.first()

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

    def test_onboarding_update_seeds_numbering_for_new_financial_year_and_subentity_scopes(self):
        create_payload = {
            "entity": {
                "entityname": "Numbering Scope Entity",
                "legalname": "Numbering Scope Entity Pvt Ltd",
                "GstRegitrationType": self.gst_type.id,
                "gstno": "03APXPB5894F1Z3",
                "panno": "APXPB5894F",
                "phoneoffice": "9855966534",
                "phoneresidence": "9855966534",
                "email": "scope@example.com",
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

        create_response = self.client.post("/api/entity/onboarding/create/", create_payload, format="json")
        self.assertEqual(create_response.status_code, 201)

        entity = Entity.objects.get(id=create_response.data["entity_id"])
        existing_fy = entity.fy.get()
        existing_subentity = entity.subentity.get()

        update_payload = {
            "financial_years": [
                {
                    "id": existing_fy.id,
                    "desc": existing_fy.desc,
                    "finstartyear": existing_fy.finstartyear,
                    "finendyear": existing_fy.finendyear,
                    "isactive": existing_fy.isactive,
                },
                {
                    "desc": "FY 2027-28",
                    "finstartyear": "2027-04-01T00:00:00Z",
                    "finendyear": "2028-03-31T00:00:00Z",
                    "isactive": False,
                },
            ],
            "subentities": [
                {
                    "id": existing_subentity.id,
                    "subentityname": existing_subentity.subentityname,
                },
                {
                    "subentityname": "Operations Branch",
                    "country": self.country.id,
                    "state": self.state.id,
                    "district": self.district.id,
                    "city": self.city.id,
                    "pincode": "140406",
                    "phoneoffice": "9855966534",
                    "phoneresidence": "9855966534",
                    "email": "ops@example.com",
                },
            ],
        }

        update_response = self.client.patch(
            f"/api/entity/onboarding/entity/{entity.id}/",
            update_payload,
            format="json",
        )
        self.assertEqual(update_response.status_code, 200)

        new_fy = EntityFinancialYear.objects.get(entity=entity, desc="FY 2027-28")
        new_subentity = SubEntity.objects.get(entity=entity, subentityname="Operations Branch")
        cash_doc_type = DocumentType.objects.get(module="vouchers", doc_key="CASH_VOUCHER")
        bank_doc_type = DocumentType.objects.get(module="vouchers", doc_key="BANK_VOUCHER")

        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=entity,
                entityfinid=existing_fy,
                subentity=new_subentity,
                doc_type=cash_doc_type,
                doc_code="CV",
            ).exists()
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=entity,
                entityfinid=new_fy,
                subentity=existing_subentity,
                doc_type=bank_doc_type,
                doc_code="BV",
            ).exists()
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=entity,
                entityfinid=new_fy,
                subentity=new_subentity,
                doc_type=bank_doc_type,
                doc_code="BV",
            ).exists()
        )


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
        self.assertTrue(CustomerAccount.objects.filter(owner=user).exists())
        self.assertTrue(
            UserEntityAccess.objects.filter(
                customer_account=entity.customer_account,
                user=user,
                role=UserEntityAccess.Role.OWNER,
                is_active=True,
            ).exists()
        )

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
        self.assertEqual(response.data["subscription"]["subscription"]["status"], "trialing")

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


class ResetTransactionalDataCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reset-assets",
            email="reset-assets@example.com",
            password="Password@123",
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
            entityname="Reset Entity",
            entitydesc="Reset Entity",
            legalname="Reset Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.foreign_entity = Entity.objects.create(
            entityname="Foreign Reset Entity",
            entitydesc="Foreign Reset Entity",
            legalname="Foreign Reset Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )

        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main Branch", is_head_office=True)
        self.foreign_subentity = SubEntity.objects.create(entity=self.foreign_entity, subentityname="Foreign Branch", is_head_office=True)
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=datetime(2026, 4, 1, tzinfo=dt_timezone.utc),
            finendyear=datetime(2027, 3, 31, tzinfo=dt_timezone.utc),
            createdby=self.user,
        )
        self.foreign_entityfin = EntityFinancialYear.objects.create(
            entity=self.foreign_entity,
            desc="FY 2026-27",
            finstartyear=datetime(2026, 4, 1, tzinfo=dt_timezone.utc),
            finendyear=datetime(2027, 3, 31, tzinfo=dt_timezone.utc),
            createdby=self.user,
        )

        self.asset_head = accountHead.objects.create(entity=self.entity, name="Asset Head", code=1001, drcreffect="Debit")
        self.foreign_asset_head = accountHead.objects.create(entity=self.foreign_entity, name="Foreign Asset Head", code=2001, drcreffect="Debit")
        self.asset_ledger = Ledger.objects.create(entity=self.entity, ledger_code=1010, name="Asset Ledger", accounthead=self.asset_head, createdby=self.user)
        self.foreign_asset_ledger = Ledger.objects.create(entity=self.foreign_entity, ledger_code=2010, name="Foreign Asset Ledger", accounthead=self.foreign_asset_head, createdby=self.user)

        self.category = AssetCategory.objects.create(
            entity=self.entity,
            code="CAT-001",
            name="Office Equipment",
            asset_ledger=self.asset_ledger,
            created_by=self.user,
            updated_by=self.user,
        )
        self.foreign_category = AssetCategory.objects.create(
            entity=self.foreign_entity,
            code="CAT-002",
            name="Foreign Equipment",
            asset_ledger=self.foreign_asset_ledger,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_reset_transactional_data_deletes_scoped_asset_data(self):
        vendor = account.objects.create(entity=self.entity, accountname="Vendor One")
        product_category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Equipment")
        uom = UnitOfMeasure.objects.create(entity=self.entity, code="PCS", description="Pieces")
        product = Product.objects.create(
            entity=self.entity,
            productname="Laptop",
            sku="LAP-001",
            productcategory=product_category,
            base_uom=uom,
            purchase_behavior=ProductPurchaseBehavior.ASSET,
            default_asset_category=self.category,
        )

        purchase_header = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=vendor,
            bill_date=date(2026, 4, 10),
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            doc_code="PINV",
            doc_no=1001,
            purchase_number="PI/PINV/2026/1001",
            status=PurchaseInvoiceHeader.Status.POSTED,
            default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE,
            tax_regime=PurchaseInvoiceHeader.TaxRegime.INTRA,
        )
        scoped_asset = FixedAsset.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            category=self.category,
            asset_code="FA-000001",
            asset_name="Scoped Asset",
            acquisition_date=date(2026, 4, 10),
            gross_block="50000.00",
            residual_value="0.00",
            net_book_value="50000.00",
            status=FixedAsset.AssetStatus.CAPITAL_WIP,
            created_by=self.user,
            updated_by=self.user,
        )
        purchase_header.lines.create(
            line_no=1,
            product=product,
            product_desc="Scoped Asset",
            is_service=False,
            purchase_behavior=ProductPurchaseBehavior.ASSET,
            uom=uom,
            qty="1.0000",
            rate="50000.00",
            taxable_value="50000.00",
            line_total="59000.00",
            asset_record=scoped_asset,
        )

        run = DepreciationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            run_code="DEP-001",
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
            posting_date=date(2026, 4, 30),
            status=DepreciationRun.RunStatus.CALCULATED,
            depreciation_method="SLM",
            created_by=self.user,
            updated_by=self.user,
        )
        run_line = DepreciationRunLine.objects.create(
            run=run,
            asset=scoped_asset,
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
            depreciation_amount="1000.00",
            closing_accumulated_depreciation="1000.00",
            closing_net_book_value="49000.00",
        )

        foreign_asset = FixedAsset.objects.create(
            entity=self.foreign_entity,
            entityfinid=self.foreign_entityfin,
            subentity=self.foreign_subentity,
            category=self.foreign_category,
            asset_code="FA-FOREIGN-1",
            asset_name="Foreign Asset",
            acquisition_date=date(2026, 4, 1),
            gross_block="25000.00",
            residual_value="0.00",
            net_book_value="25000.00",
            created_by=self.user,
            updated_by=self.user,
        )

        out = StringIO()
        call_command(
            "reset_transactional_data",
            entity=self.entity.id,
            entityfinid=self.entityfin.id,
            subentity=self.subentity.id,
            stdout=out,
        )

        self.assertFalse(PurchaseInvoiceHeader.objects.filter(id=purchase_header.id).exists())
        self.assertFalse(DepreciationRunLine.objects.filter(id=run_line.id).exists())
        self.assertFalse(DepreciationRun.objects.filter(id=run.id).exists())
        self.assertFalse(FixedAsset.objects.filter(id=scoped_asset.id).exists())
        self.assertTrue(FixedAsset.objects.filter(id=foreign_asset.id).exists())
        self.assertIn("Asset depreciation run lines: 1", out.getvalue())
        self.assertIn("Asset depreciation runs: 1", out.getvalue())
        self.assertIn("Fixed assets: 1", out.getvalue())
