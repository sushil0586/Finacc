from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from Authentication.models import User
from Authentication.models import MainMenu, Submenu
from entity.models import (
    BankDetail,
    Constitution,
    Entity,
    GstRegistrationType,
    Role as LegacyRole,
    RolePrivilege,
    SubEntity,
    UnitType,
    UserRole,
)
from geography.models import City, Country, District, State
from rbac.models import Menu, Permission, Role, RolePermission, UserRoleAssignment
from rbac.backfill import LegacyRBACBackfillService
from rbac.services import LegacyMenuCompatibilityService


class RBACModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="admin@example.com",
            username="admin@example.com",
            password="secret123",
        )
        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Karnataka", statecode="KA", country=self.country)
        self.district = District.objects.create(districtname="Bangalore", districtcode="BLR", state=self.state)
        self.city = City.objects.create(
            cityname="Bangalore",
            citycode="BLR",
            pincode="560001",
            distt=self.district,
        )
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
        self.subentity = SubEntity.objects.create(
            subentityname="Branch 1",
            address="Branch address",
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            entity=self.entity,
        )

    def test_role_assignment_supports_multiple_roles_per_entity(self):
        role1 = Role.objects.create(entity=self.entity, name="Sales User", code="SALES_USER")
        role2 = Role.objects.create(entity=self.entity, name="Reports User", code="REPORT_USER")

        UserRoleAssignment.objects.create(user=self.user, entity=self.entity, role=role1)
        UserRoleAssignment.objects.create(user=self.user, entity=self.entity, role=role2)

        self.assertEqual(
            UserRoleAssignment.objects.filter(user=self.user, entity=self.entity).count(),
            2,
        )

    def test_menu_supports_multi_level_hierarchy(self):
        root = Menu.objects.create(name="Sales", code="sales", menu_type=Menu.TYPE_GROUP)
        child = Menu.objects.create(name="Invoices", code="sales.invoices", parent=root)
        grandchild = Menu.objects.create(name="Credit Notes", code="sales.invoices.credit-notes", parent=child)

        self.assertEqual(root.depth, 0)
        self.assertEqual(child.depth, 1)
        self.assertEqual(grandchild.depth, 2)

    def test_menu_cycle_validation(self):
        root = Menu.objects.create(name="Sales", code="sales")
        child = Menu.objects.create(name="Invoices", code="sales.invoices", parent=root)
        root.parent = child

        with self.assertRaises(ValidationError):
            root.save()

    def test_role_permission_unique(self):
        role = Role.objects.create(entity=self.entity, name="Sales User", code="SALES_USER")
        permission = Permission.objects.create(
            code="sales.invoice.view",
            name="View Sales Invoice",
            module="sales",
            resource="invoice",
            action="view",
        )
        RolePermission.objects.create(role=role, permission=permission)

        with self.assertRaises(IntegrityError):
            RolePermission.objects.create(role=role, permission=permission)

    def test_legacy_backfill_and_menu_compatibility(self):
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
            roledesc="Sales access",
            rolelevel=1,
            entity=self.entity,
        )
        UserRole.objects.create(user=self.user, entity=self.entity, role=legacy_role)
        RolePrivilege.objects.create(role=legacy_role, submenu=submenu, entity=self.entity)

        LegacyRBACBackfillService.run()

        self.assertTrue(Role.objects.filter(entity=self.entity, code="legacy_role_1").exists())
        self.assertTrue(Menu.objects.filter(code="legacy.mainmenu.1").exists())
        self.assertTrue(Permission.objects.filter(code="legacy.submenu.1.access").exists())

        response = LegacyMenuCompatibilityService.legacy_shape_for_user(
            user=self.user,
            entity_id=self.entity.id,
            role_id=legacy_role.id,
        )

        self.assertEqual(response[0]["mainmenu"], "Sales")
        self.assertEqual(response[0]["submenu"][0]["submenu"], "Invoices")
