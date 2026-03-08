from django.test import TestCase
from rest_framework.test import APIClient

from Authentication.models import MainMenu, Submenu, User
from entity.models import (
    BankDetail,
    Constitution,
    Entity,
    GstRegistrationType,
    Role as LegacyRole,
    RolePrivilege,
    UnitType,
    UserRole,
)
from geography.models import City, Country, District, State
from rbac.backfill import LegacyRBACBackfillService
from rbac.models import Menu, Permission


class RBACAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="viewer@example.com",
            username="viewer@example.com",
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
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_menu_tree_endpoint_returns_nested_children(self):
        root = Menu.objects.create(name="Sales", code="sales", menu_type=Menu.TYPE_GROUP)
        Menu.objects.create(name="Invoices", code="sales.invoices", parent=root)

        response = self.client.get("/api/rbac/menus")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["children"][0]["code"], "sales.invoices")

    def test_permissions_endpoint_returns_catalog(self):
        Permission.objects.create(
            code="sales.invoice.view",
            name="View Sales Invoice",
            module="sales",
            resource="invoice",
            action="view",
        )

        response = self.client.get("/api/rbac/permissions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["code"], "sales.invoice.view")

    def test_user_menu_endpoints_return_recursive_tree_for_entity(self):
        main_menu = MainMenu.objects.create(mainmenu="Sales", menuurl="/sales", menucode="sales", order=1)
        submenu = Submenu.objects.create(
            mainmenu=main_menu,
            submenu="Invoices",
            submenucode="sales.invoices",
            subMenuurl="/sales/invoices",
            order=1,
        )
        legacy_role = LegacyRole.objects.create(
            rolename="Sales User",
            roledesc="Sales",
            rolelevel=1,
            entity=self.entity,
        )
        UserRole.objects.create(user=self.user, entity=self.entity, role=legacy_role)
        RolePrivilege.objects.create(role=legacy_role, submenu=submenu, entity=self.entity)
        LegacyRBACBackfillService.run()

        response = self.client.get(f"/api/rbac/me/menus?entity={self.entity.id}&role={legacy_role.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["entity_id"], self.entity.id)
        self.assertEqual(response.data["menus"][0]["name"], "Sales")
        self.assertEqual(response.data["menus"][0]["children"][0]["name"], "Invoices")
