from django.test import TestCase
from rest_framework.test import APIClient

from Authentication.models import MainMenu, Submenu, User
from entity.models import BankDetail, BankAccount, Constitution, Entity, EntityFinancialYear, GstRegistrationType, Role, RolePrivilege, UnitType, UserRole
from financial.models import FinancialSettings, Ledger, account, accountHead
from rbac.models import Role as RbacRole
from rbac.models import UserRoleAssignment
from geography.models import City, Country, District, State
from rbac.backfill import LegacyRBACBackfillService


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
        self.unit_type = UnitType.objects.create(UnitName="Unit", UnitDesc="Unit")
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
            unitType=self.unit_type,
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
        main_menu = MainMenu.objects.create(mainmenu="Sales", menuurl="/sales", menucode="sales", order=1)
        submenu = Submenu.objects.create(
            mainmenu=main_menu,
            submenu="Invoices",
            submenucode="sales.invoices",
            subMenuurl="/sales/invoices",
            order=1,
        )
        self.legacy_role = Role.objects.create(
            rolename="Sales User",
            roledesc="Sales",
            rolelevel=1,
            entity=self.entity,
        )
        UserRole.objects.create(user=self.user, entity=self.entity, role=self.legacy_role)
        RolePrivilege.objects.create(role=self.legacy_role, submenu=submenu, entity=self.entity)
        LegacyRBACBackfillService.run()
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
        self.state = State.objects.create(statename="Punjab", statecode="PB", country=self.country)
        self.district = District.objects.create(districtname="Fatehgarh", districtcode="FGS", state=self.state)
        self.city = City.objects.create(cityname="Sirhind", citycode="SRH", pincode="140406", distt=self.district)
        self.unit_type = UnitType.objects.create(UnitName="Unit", UnitDesc="Unit")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.constitution = Constitution.objects.create(
            constitutionname="Proprietorship",
            constitutiondesc="Proprietorship",
            constcode="01",
            createdby=self.user,
        )
        main_menu = MainMenu.objects.create(mainmenu="Admin", menuurl="/admin", menucode="admin", order=1)
        Submenu.objects.create(
            mainmenu=main_menu,
            submenu="Role",
            submenucode="role",
            subMenuurl="/role",
            order=1,
        )
        LegacyRBACBackfillService.run()
        self.client.force_authenticate(user=self.user)

    def test_new_onboarding_creates_entity_financial_and_rbac_defaults(self):
        payload = {
            "entity": {
                "entityname": "ABC Enterprises",
                "legalname": "ABC Enterprises",
                "unitType": self.unit_type.id,
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
                {"shareholder": "Owner Name", "pan": "APXPB5894F", "sharepercentage": "100.00"}
            ],
            "seed_options": {
                "template_code": "standard_trading",
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
        self.assertTrue(account.objects.filter(entity=entity, accountcode=4000).exists())
        self.assertTrue(Ledger.objects.filter(entity=entity, ledger_code=4000).exists())
        self.assertTrue(UserRoleAssignment.objects.filter(entity=entity, user=self.user).exists())
        self.assertTrue(RbacRole.objects.filter(entity=entity, code="entity.super_admin").exists())
