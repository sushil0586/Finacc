from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from entity.models import Entity
from rbac import access_catalog
from rbac.canonical_seeding import CanonicalRBACCatalogSeedService
from rbac.models import Menu, MenuPermission, Permission, Role, RolePermission
from rbac.seeding import RBACSeedService
from subscriptions.models import CustomerAccount, CustomerSubscription, PlanLimit, SubscriptionPlan
from subscriptions.services import SubscriptionService


class CanonicalAccessCatalogTests(SimpleTestCase):
    def test_subscription_packages_reference_known_features(self):
        known_features = set(access_catalog.ALL_FEATURE_CODES)

        for package_code, feature_codes in access_catalog.SUBSCRIPTION_PACKAGE_FEATURES.items():
            self.assertTrue(feature_codes, f"{package_code} should expose at least one feature")
            self.assertFalse(
                set(feature_codes) - known_features,
                f"{package_code} references unknown feature codes",
            )

    def test_role_specs_reference_known_features_and_unique_codes(self):
        known_features = set(access_catalog.ALL_FEATURE_CODES)
        role_codes = [spec.code for spec in access_catalog.ROLE_SPECS]

        self.assertEqual(len(role_codes), len(set(role_codes)))
        for spec in access_catalog.ROLE_SPECS:
            self.assertTrue(spec.name)
            self.assertTrue(spec.description)
            self.assertTrue(spec.created_for_features)
            self.assertFalse(
                set(spec.created_for_features) - known_features,
                f"{spec.code} references unknown feature codes",
            )

    def test_menu_specs_have_valid_feature_parent_and_roles(self):
        known_features = set(access_catalog.ALL_FEATURE_CODES)
        menu_codes = {spec.code for spec in access_catalog.MENU_SPECS}
        role_codes = {spec.code for spec in access_catalog.ROLE_SPECS}

        self.assertEqual(len(menu_codes), len(access_catalog.MENU_SPECS))
        for spec in access_catalog.MENU_SPECS:
            self.assertIn(spec.feature_code, known_features)
            self.assertTrue(spec.permission_code)
            if spec.parent_code:
                self.assertIn(spec.parent_code, menu_codes)
            self.assertFalse(
                set(spec.default_role_codes) - role_codes,
                f"{spec.code} references unknown default roles",
            )

    def test_canonical_screen_routes_are_unique(self):
        routes = [
            spec.route_path
            for spec in access_catalog.MENU_SPECS
            if spec.canonical and spec.route_path
        ]

        self.assertEqual(len(routes), len(set(routes)))

    def test_manufacturing_report_parent_uses_manufacturing_permission(self):
        specs_by_code = {spec.code: spec for spec in access_catalog.MENU_SPECS}

        self.assertEqual(
            specs_by_code["reports.manufacturing"].permission_code,
            "reports.inventory.manufacturing_hub.view",
        )
        self.assertNotEqual(
            specs_by_code["reports.manufacturing"].permission_code,
            "reports.inventory.view",
        )
        for code in (
            "reports.inventory.production_order",
            "reports.inventory.manufacturing_browser",
            "reports.inventory.manufacturing_boms",
            "reports.inventory.manufacturing_routes",
            "reports.manufacturing.settings",
        ):
            self.assertEqual(specs_by_code[code].parent_code, "reports.manufacturing")

    def test_canonical_operational_menu_hierarchy_groups_common_workflows(self):
        specs_by_code = {spec.code: spec for spec in access_catalog.MENU_SPECS}

        expected_parents = {
            "purchase.invoice": "purchase.transactions",
            "purchase.service_invoice": "purchase.transactions",
            "purchase.credit_note": "purchase.transactions",
            "purchase.debit_note": "purchase.transactions",
            "purchase.service_credit_note": "purchase.transactions",
            "purchase.service_debit_note": "purchase.transactions",
            "purchase.statutory": "purchase.compliance",
            "sales.invoice": "sales.transactions",
            "sales.service_invoice": "sales.transactions",
            "sales.credit_note": "sales.transactions",
            "sales.debit_note": "sales.transactions",
            "sales.service_credit_note": "sales.transactions",
            "sales.service_debit_note": "sales.transactions",
            "accounts.journal_voucher": "accounts.vouchers",
            "accounts.bank_voucher": "accounts.vouchers",
            "accounts.cash_voucher": "accounts.vouchers",
            "accounts.receipt_voucher": "accounts.vouchers",
            "accounts.payment_voucher": "accounts.vouchers",
            "accounts.account_types": "accounts.financial_masters",
            "accounts.account_heads": "accounts.financial_masters",
            "accounts.ledgers": "accounts.financial_masters",
            "accounts.accounts": "accounts.financial_masters",
            "accounts.payment_settings": "accounts.settings",
            "accounts.receipt_settings": "accounts.settings",
            "accounts.voucher_settings": "accounts.settings",
            "accounts.static_account_settings": "accounts.settings",
            "reports.gst_compliance_center": "reports.compliance",
            "reports.gstr3b": "reports.compliance",
            "reports.gstr9": "reports.compliance",
            "reports.tds_compliance_center": "reports.financial_hub",
            "reports.gst_tds_compliance_center": "reports.financial_hub",
            "reports.tcs_compliance_center": "reports.financial_hub",
            "sales.commerce_promotions": "sales.setup",
            "reports.manufacturing.settings": "reports.manufacturing",
        }

        for code, parent_code in expected_parents.items():
            self.assertEqual(specs_by_code[code].parent_code, parent_code)

    def test_payables_operational_report_menus_use_current_frontend_routes(self):
        specs_by_code = {spec.code: spec for spec in access_catalog.MENU_SPECS}

        expected_routes = {
            "reports.vendorsettlementhistory": "/reports/payables/vendor_settlement_history",
            "reports.vendornoteregister": "/reports/payables/vendor_note_register",
            "reports.apglreconciliation": "/reports/payables/ap_gl_reconciliation",
            "reports.vendorbalanceexceptions": "/reports/payables/vendor_balance_exceptions",
        }

        for code, route_path in expected_routes.items():
            self.assertEqual(specs_by_code[code].parent_code, "reports.payables")
            self.assertEqual(specs_by_code[code].route_path, route_path)

    def test_admin_roles_menu_uses_current_rbac_management_route(self):
        specs_by_code = {spec.code: spec for spec in access_catalog.MENU_SPECS}

        self.assertEqual(specs_by_code["admin.role_list"].route_path, "/rbacmanagement?tab=roles")

    def test_admin_setup_menus_use_explicit_admin_permissions(self):
        specs_by_code = {spec.code: spec for spec in access_catalog.MENU_SPECS}

        expected_permissions = {
            "admin.role_list": "admin.role.view",
            "admin.users": "admin.user.view",
            "admin.rbac_management": "admin.role_access.update",
            "admin.business_settings": "admin.business_settings.view",
            "admin.entity_partner_details": "admin.business_settings.view",
            "admin.branch_workspace": "admin.branch.view",
        }

        for code, permission_code in expected_permissions.items():
            self.assertEqual(specs_by_code[code].access_mode, "setup")
            self.assertEqual(specs_by_code[code].permission_code, permission_code)

        for retired_admin_code in (
            "admin.organization_structure",
            "admin.manufacturing_settings",
            "admin.commerce_promotions",
        ):
            self.assertNotIn(retired_admin_code, specs_by_code)
            self.assertIn(retired_admin_code, access_catalog.LEGACY_DUPLICATE_MENU_CODES_TO_DISABLE)

    def test_retired_interest_calculator_menu_has_no_clickable_route(self):
        specs_by_code = {spec.code: spec for spec in access_catalog.MENU_SPECS}

        spec = specs_by_code["reports.interestcalculatorindividualreport"]
        self.assertFalse(spec.canonical)
        self.assertEqual(spec.route_path, "")
        self.assertIn(spec.code, access_catalog.LEGACY_MENU_CODES_TO_DISABLE)

    def test_legacy_tds_report_menu_is_retired_in_favor_of_compliance_center(self):
        specs_by_code = {spec.code: spec for spec in access_catalog.MENU_SPECS}

        self.assertNotIn("reports.tdsreport", specs_by_code)
        self.assertIn("reports.tdsreport", access_catalog.LEGACY_DUPLICATE_MENU_CODES_TO_DISABLE)
        self.assertEqual(specs_by_code["reports.tds_compliance_center"].route_path, "/reports/tds")

    def test_basic_accounting_excludes_advanced_modules(self):
        features = access_catalog.features_for_packages(
            [access_catalog.PACKAGE_BASIC_ACCOUNTING]
        )

        self.assertIn(access_catalog.FEATURE_FINANCIAL, features)
        self.assertIn(access_catalog.FEATURE_SALES, features)
        self.assertIn(access_catalog.FEATURE_PURCHASE, features)
        self.assertNotIn(access_catalog.FEATURE_TREASURY, features)
        self.assertNotIn(access_catalog.FEATURE_GST_COMPLIANCE, features)
        self.assertNotIn(access_catalog.FEATURE_PAYROLL, features)

    def test_enterprise_package_includes_all_features(self):
        features = access_catalog.features_for_packages(
            [access_catalog.PACKAGE_ENTERPRISE]
        )

        self.assertEqual(features, frozenset(access_catalog.ALL_FEATURE_CODES))

    def test_role_specs_for_features_are_subscription_aware(self):
        role_codes = {
            spec.code
            for spec in access_catalog.role_specs_for_features(
                [access_catalog.FEATURE_TREASURY]
            )
        }

        self.assertIn(access_catalog.ROLE_ENTITY_SUPER_ADMIN, role_codes)
        self.assertIn(access_catalog.ROLE_ADMIN, role_codes)
        self.assertIn(access_catalog.ROLE_TREASURY_USER, role_codes)
        self.assertIn(access_catalog.ROLE_TREASURY_APPROVER, role_codes)
        self.assertNotIn(access_catalog.ROLE_PAYROLL_USER, role_codes)
        self.assertNotIn(access_catalog.ROLE_GST_REVIEWER, role_codes)

    def test_permission_codes_for_features_include_route_access_permissions(self):
        permission_codes = access_catalog.permission_codes_for_features(
            [access_catalog.FEATURE_GST_COMPLIANCE]
        )

        self.assertIn("dashboard.home.view", permission_codes)
        self.assertIn("reports.gst_compliance_center.view", permission_codes)
        self.assertIn("gst.reconciliation.view", permission_codes)
        self.assertIn("reports.gstr1_gstr3b_reconciliation.view", permission_codes)
        self.assertNotIn("payroll.run.view", permission_codes)

    def test_route_permission_specs_reference_known_features_and_are_unique(self):
        known_features = set(access_catalog.ALL_FEATURE_CODES)
        permission_codes = [spec.code for spec in access_catalog.ROUTE_PERMISSION_SPECS]

        self.assertEqual(len(permission_codes), len(set(permission_codes)))
        for spec in access_catalog.ROUTE_PERMISSION_SPECS:
            self.assertIn(spec.feature_code, known_features)

    def test_critical_routes_are_mapped_to_expected_subscription_features(self):
        expected = {
            "treasury.setup.view": access_catalog.FEATURE_TREASURY,
            "posting.static_account_settings.view": access_catalog.FEATURE_FINANCIAL,
            "posting.static_account_settings.validate": access_catalog.FEATURE_FINANCIAL,
            "reports.payables.ap_compliance_aging.view": access_catalog.FEATURE_PAYABLES,
            "reports.financial_hub.receivables_hub.customer_outstanding.view": access_catalog.FEATURE_RECEIVABLES,
            "reports.gst_exception_dashboard.view": access_catalog.FEATURE_GST_COMPLIANCE,
            "financial.account.view": access_catalog.FEATURE_FINANCIAL,
            "financial.account.update": access_catalog.FEATURE_FINANCIAL,
            "gst.tds.config.view": access_catalog.FEATURE_GST_COMPLIANCE,
            "tcs.section.view": access_catalog.FEATURE_COMPLIANCE,
            "compliance.tcs_section.update": access_catalog.FEATURE_COMPLIANCE,
            "manufacturing.workorder.post": access_catalog.FEATURE_MANUFACTURING,
            "inventory.adjustment.view": access_catalog.FEATURE_INVENTORY,
            "assets.asset_events.view": access_catalog.FEATURE_ASSETS,
            "hrms.attendance_entry.view": access_catalog.FEATURE_HRMS,
            "payroll.run.payment_handoff": access_catalog.FEATURE_PAYROLL,
        }
        route_features = {spec.code: spec.feature_code for spec in access_catalog.ROUTE_PERMISSION_SPECS}

        for permission_code, feature_code in expected.items():
            self.assertEqual(route_features.get(permission_code), feature_code)


class CanonicalRBACCatalogSeedServiceTests(TestCase):
    def test_seed_global_catalog_creates_menus_permissions_and_visibility_links(self):
        result = CanonicalRBACCatalogSeedService.seed_global_catalog()

        self.assertEqual(result["menu_count"], len(access_catalog.MENU_SPECS))
        self.assertGreaterEqual(result["permission_count"], len({spec.permission_code for spec in access_catalog.MENU_SPECS}))

        treasury_menu = Menu.objects.get(code="treasury.execution")
        self.assertEqual(treasury_menu.parent.code, "treasury")
        self.assertEqual(treasury_menu.route_path, "/treasury-execution")
        self.assertEqual(treasury_menu.metadata["feature_code"], access_catalog.FEATURE_TREASURY)
        self.assertTrue(treasury_menu.metadata["is_canonical"])

        permission = Permission.objects.get(code="treasury.payment_batch.view")
        self.assertTrue(
            MenuPermission.objects.filter(
                menu=treasury_menu,
                permission=permission,
                relation_type=MenuPermission.RELATION_VISIBILITY,
                isactive=True,
            ).exists()
        )

        self.assertTrue(Permission.objects.filter(code="reports.payables.ap_compliance_aging.view").exists())
        self.assertTrue(Permission.objects.filter(code="hrms.attendance_entry.view").exists())

    def test_seed_global_catalog_deactivates_legacy_master_and_inventory_roots(self):
        Menu.objects.create(code="masters", name="Masters", menu_type=Menu.TYPE_GROUP, isactive=True)
        Menu.objects.create(code="masters.old", name="Old Master", menu_type=Menu.TYPE_SCREEN, isactive=True)
        Menu.objects.update_or_create(
            code="inventory",
            defaults={"name": "Inventory", "menu_type": Menu.TYPE_GROUP, "isactive": True},
        )

        CanonicalRBACCatalogSeedService.seed_global_catalog()

        self.assertFalse(Menu.objects.get(code="masters").isactive)
        self.assertFalse(Menu.objects.get(code="masters.old").isactive)
        self.assertFalse(Menu.objects.get(code="inventory").isactive)
        self.assertTrue(Menu.objects.get(code="reports.inventory").isactive)

    def test_seed_global_catalog_rehomes_operational_setup_menus_out_of_admin(self):
        for code, route_path in (
            ("admin.organization_structure", "/hrms/organization-units"),
            ("admin.manufacturing_settings", "/manufacturingsettings"),
            ("admin.commerce_promotions", "/commerce-promotions"),
        ):
            Menu.objects.update_or_create(
                code=code,
                defaults={
                    "name": code,
                    "menu_type": Menu.TYPE_SCREEN,
                    "route_path": route_path,
                    "isactive": True,
                },
            )

        CanonicalRBACCatalogSeedService.seed_global_catalog()

        self.assertFalse(Menu.objects.get(code="admin.organization_structure").isactive)
        self.assertFalse(Menu.objects.get(code="admin.manufacturing_settings").isactive)
        self.assertFalse(Menu.objects.get(code="admin.commerce_promotions").isactive)
        self.assertEqual(Menu.objects.get(code="hrms.organization_units").parent.code, "hrms")
        self.assertEqual(Menu.objects.get(code="reports.manufacturing.settings").parent.code, "reports.manufacturing")
        self.assertEqual(Menu.objects.get(code="sales.commerce_promotions").parent.code, "sales.setup")

    def test_seed_global_catalog_deactivates_duplicate_legacy_routes(self):
        legacy_menu = Menu.objects.create(
            code="purchase.purchaseinvoice",
            name="Purchase Invoice",
            menu_type=Menu.TYPE_SCREEN,
            route_path="/purchaseinvoice",
            isactive=True,
        )
        permission = Permission.objects.create(
            code="legacy.purchase.invoice.view",
            name="Legacy Purchase Invoice View",
            module="purchase",
            resource="invoice",
            action="view",
            scope_type=Permission.SCOPE_ENTITY,
            isactive=True,
        )
        MenuPermission.objects.create(
            menu=legacy_menu,
            permission=permission,
            relation_type=MenuPermission.RELATION_VISIBILITY,
            isactive=True,
        )

        CanonicalRBACCatalogSeedService.seed_global_catalog()

        legacy_menu.refresh_from_db()
        canonical_menu = Menu.objects.get(code="purchase.invoice")

        self.assertFalse(legacy_menu.isactive)
        self.assertTrue(canonical_menu.isactive)
        self.assertEqual(canonical_menu.route_path, "/purchaseinvoice")
        self.assertFalse(MenuPermission.objects.get(menu=legacy_menu).isactive)
        self.assertTrue(
            legacy_menu.metadata["deactivated_as_duplicate_canonical_route"]
        )

    def test_seed_global_catalog_deactivates_empty_legacy_group_folders(self):
        empty_group = Menu.objects.create(
            code="purchase.legacy_setup",
            name="Setup",
            menu_type=Menu.TYPE_GROUP,
            route_path="",
            isactive=True,
        )
        non_empty_group = Menu.objects.create(
            code="purchase.legacy_transactions",
            name="Transactions",
            menu_type=Menu.TYPE_GROUP,
            route_path="",
            isactive=True,
        )
        Menu.objects.create(
            code="purchase.legacy_training",
            name="Legacy Training",
            menu_type=Menu.TYPE_SCREEN,
            route_path="/purchase-legacy-training",
            parent=non_empty_group,
            isactive=True,
        )

        CanonicalRBACCatalogSeedService.seed_global_catalog()

        empty_group.refresh_from_db()
        non_empty_group.refresh_from_db()

        self.assertFalse(empty_group.isactive)
        self.assertTrue(empty_group.metadata["deactivated_as_empty_legacy_group"])
        self.assertTrue(non_empty_group.isactive)

    def test_seed_global_catalog_deactivates_known_semantic_duplicate_menus(self):
        legacy_ledger = Menu.objects.create(
            code="reports.ledgerbook",
            name="Ledger Book",
            menu_type=Menu.TYPE_SCREEN,
            route_path="/ledgerbook",
            isactive=True,
        )
        legacy_admin_role = Menu.objects.create(
            code="admin.role",
            name="Roles",
            menu_type=Menu.TYPE_SCREEN,
            route_path="/role",
            isactive=True,
        )

        CanonicalRBACCatalogSeedService.seed_global_catalog()

        legacy_ledger.refresh_from_db()
        legacy_admin_role.refresh_from_db()

        self.assertFalse(legacy_ledger.isactive)
        self.assertFalse(legacy_admin_role.isactive)
        self.assertTrue(
            legacy_ledger.metadata["deactivated_as_duplicate_legacy_menu"]
        )
        self.assertTrue(Menu.objects.get(code="admin.role_list").isactive)
        self.assertTrue(Menu.objects.get(code="admin.rbac_management").isactive)


class SubscriptionAwareRBACSeedServiceTests(TestCase):
    def _create_subscription_entity(self, *, enabled_features):
        user = get_user_model().objects.create_user(
            username=f"user-{len(enabled_features)}",
            email=f"user-{len(enabled_features)}@example.test",
            password="test-pass",
        )
        customer_account = CustomerAccount.objects.create(
            name=f"Account {len(enabled_features)}",
            slug=f"account-{len(enabled_features)}",
            owner=user,
            status=CustomerAccount.Status.ACTIVE,
        )
        plan = SubscriptionPlan.objects.create(
            name=f"Plan {len(enabled_features)}",
            code=f"plan-{len(enabled_features)}",
            is_public=False,
            is_default=False,
        )
        for key, definition in SubscriptionService.LIMIT_CATALOG.items():
            limit_defaults = {
                "plan": plan,
                "key": key,
                "label": definition["label"],
                "limit_type": definition["limit_type"],
            }
            if definition["limit_type"] == PlanLimit.LimitType.BOOLEAN:
                limit_defaults["bool_value"] = key in enabled_features
            elif definition["limit_type"] == PlanLimit.LimitType.INTEGER:
                limit_defaults["int_value"] = definition["default"]
            else:
                limit_defaults["text_value"] = definition["default"]
            PlanLimit.objects.create(**limit_defaults)
        CustomerSubscription.objects.create(
            customer_account=customer_account,
            plan=plan,
            status=CustomerSubscription.Status.ACTIVE,
        )
        entity = Entity.objects.create(
            entityname=f"Entity {len(enabled_features)}",
            createdby=user,
            customer_account=customer_account,
        )
        return user, entity, plan

    def test_seed_entity_grants_only_basic_subscription_roles_and_permissions(self):
        basic_features = access_catalog.features_for_packages(
            [access_catalog.PACKAGE_BASIC_ACCOUNTING]
        )
        user, entity, _plan = self._create_subscription_entity(enabled_features=basic_features)

        result = RBACSeedService.seed_entity(entity=entity, actor=user)

        self.assertEqual(set(result["feature_codes"]), set(basic_features))
        role_codes = set(Role.objects.filter(entity=entity).values_list("code", flat=True))
        self.assertIn(access_catalog.ROLE_ENTITY_SUPER_ADMIN, role_codes)
        self.assertIn(access_catalog.ROLE_ADMIN, role_codes)
        self.assertIn(access_catalog.ROLE_ACCOUNTS_MANAGER, role_codes)
        self.assertIn(access_catalog.ROLE_SALES_USER, role_codes)
        self.assertIn(access_catalog.ROLE_PURCHASE_USER, role_codes)
        self.assertNotIn(access_catalog.ROLE_TREASURY_USER, role_codes)
        self.assertNotIn(access_catalog.ROLE_GST_REVIEWER, role_codes)
        self.assertNotIn(access_catalog.ROLE_PAYROLL_USER, role_codes)

        admin_permission_codes = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_ENTITY_SUPER_ADMIN,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("sales.invoice.view", admin_permission_codes)
        self.assertIn("purchase.invoice.view", admin_permission_codes)
        self.assertIn("voucher.journal.view", admin_permission_codes)
        self.assertIn("financial.account.view", admin_permission_codes)
        self.assertNotIn("treasury.payment_batch.view", admin_permission_codes)
        self.assertNotIn("reports.gst_compliance_center.view", admin_permission_codes)
        self.assertNotIn("payroll.run.view", admin_permission_codes)

    def test_seed_entity_grants_enterprise_subscription_roles_and_permissions(self):
        enterprise_features = access_catalog.features_for_packages(
            [access_catalog.PACKAGE_ENTERPRISE]
        )
        user, entity, _plan = self._create_subscription_entity(enabled_features=enterprise_features)

        RBACSeedService.seed_entity(entity=entity, actor=user)

        role_codes = set(Role.objects.filter(entity=entity).values_list("code", flat=True))
        self.assertIn(access_catalog.ROLE_TREASURY_USER, role_codes)
        self.assertIn(access_catalog.ROLE_TREASURY_APPROVER, role_codes)
        self.assertIn(access_catalog.ROLE_GST_REVIEWER, role_codes)
        self.assertIn(access_catalog.ROLE_HRMS_USER, role_codes)
        self.assertIn(access_catalog.ROLE_PAYROLL_USER, role_codes)

        admin_permission_codes = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_ENTITY_SUPER_ADMIN,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("treasury.payment_batch.view", admin_permission_codes)
        self.assertIn("reports.gst_compliance_center.view", admin_permission_codes)
        self.assertIn("payroll.run.view", admin_permission_codes)
        self.assertIn("financial.account.view", admin_permission_codes)
        self.assertIn("financial.account.update", admin_permission_codes)

        accounts_manager_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_ACCOUNTS_MANAGER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("accounts.account.view", accounts_manager_permissions)
        self.assertIn("financial.account.view", accounts_manager_permissions)
        self.assertIn("financial.account.update", accounts_manager_permissions)
        self.assertIn("posting.static_account_settings.view", accounts_manager_permissions)
        self.assertIn("posting.static_account_settings.validate", accounts_manager_permissions)
        self.assertIn("posting.static_account_settings.update", accounts_manager_permissions)
        self.assertIn("retail.ticket.view", accounts_manager_permissions)
        self.assertIn("reports.financial_hub.daybook.view", accounts_manager_permissions)
        self.assertIn("reports.financial_hub.receivables_hub.receivable_aging.view", accounts_manager_permissions)
        self.assertIn("tcs.partyprofile.view", accounts_manager_permissions)

        sales_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_SALES_USER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("sales.invoice.view", sales_permissions)
        self.assertIn("financial.account.view", sales_permissions)
        self.assertIn("retail.ticket.view", sales_permissions)
        self.assertIn("tcs.section.view", sales_permissions)
        self.assertIn("tcs.sections.view", sales_permissions)
        self.assertIn("reports.financial_hub.daybook.view", sales_permissions)
        self.assertIn("reports.vendoroutstanding.view", sales_permissions)
        self.assertIn("reports.accountspayableaging.view", sales_permissions)
        self.assertIn("reports.financial_hub.receivables_hub.receivable_aging.view", sales_permissions)
        self.assertNotIn("financial.account.update", sales_permissions)
        self.assertNotIn("retail.ticket.update", sales_permissions)
        self.assertNotIn("tcs.section.update", sales_permissions)

        purchase_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_PURCHASE_USER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("purchase.invoice.view", purchase_permissions)
        self.assertIn("financial.account.view", purchase_permissions)
        self.assertIn("reports.financial_hub.daybook.view", purchase_permissions)
        self.assertIn("reports.vendoroutstanding.view", purchase_permissions)
        self.assertIn("reports.accountspayableaging.view", purchase_permissions)
        self.assertIn("reports.financial_hub.receivables_hub.receivable_aging.view", purchase_permissions)
        self.assertIn("inventory.transfer.view", purchase_permissions)
        self.assertNotIn("financial.account.update", purchase_permissions)

        payables_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_PAYABLES_USER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("reports.payables.view", payables_permissions)
        self.assertIn("financial.account.view", payables_permissions)
        self.assertNotIn("financial.account.update", payables_permissions)

        receivables_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_RECEIVABLES_USER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("reports.financial_hub.receivables_hub.view", receivables_permissions)
        self.assertIn("financial.account.view", receivables_permissions)
        self.assertNotIn("financial.account.update", receivables_permissions)

        treasury_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_TREASURY_USER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("treasury.payment_batch.view", treasury_permissions)
        self.assertIn("financial.account.view", treasury_permissions)
        self.assertIn("posting.static_account_settings.validate", treasury_permissions)
        self.assertNotIn("financial.account.update", treasury_permissions)

        treasury_approver_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_TREASURY_APPROVER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("treasury.payment_batch.view", treasury_approver_permissions)
        self.assertIn("financial.account.view", treasury_approver_permissions)
        self.assertNotIn("financial.account.update", treasury_approver_permissions)

        financial_report_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_FINANCIAL_REPORT_VIEWER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("reports.financial_hub.view", financial_report_permissions)
        self.assertIn("reports.financial_hub.trial_balance.view", financial_report_permissions)
        self.assertIn("reports.trial_balance.view", financial_report_permissions)
        self.assertNotIn("purchase.invoice.view", financial_report_permissions)
        self.assertNotIn("sales.invoice.view", financial_report_permissions)

        hrms_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_HRMS_USER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("hrms.employee.view", hrms_permissions)
        self.assertIn("hrms.attendance_summary.view", hrms_permissions)
        self.assertIn("hrms.attendance_payroll_period.view", hrms_permissions)
        self.assertNotIn("payroll.run.view", hrms_permissions)

        payroll_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_PAYROLL_USER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("payroll.run.view", payroll_permissions)
        self.assertIn("payroll.structure.view", payroll_permissions)
        self.assertIn("dashboard.home.view", payroll_permissions)
        self.assertNotIn("hrms.employee.view", payroll_permissions)

        payroll_finance_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_PAYROLL_FINANCE_MANAGER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("payroll.run.view", payroll_finance_permissions)
        self.assertIn("payroll.period.view", payroll_finance_permissions)
        self.assertIn("payroll.contract_profile.view", payroll_finance_permissions)
        self.assertIn("payroll.contract_salary_assignment.view", payroll_finance_permissions)

        gst_reviewer_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_GST_REVIEWER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("dashboard.home.view", gst_reviewer_permissions)
        self.assertIn("reports.gst_compliance_center.view", gst_reviewer_permissions)
        self.assertIn("gst.reconciliation.view", gst_reviewer_permissions)
        self.assertIn("tcs.section.view", gst_reviewer_permissions)
        self.assertIn("tcs.sections.view", gst_reviewer_permissions)
        self.assertNotIn("tcs.section.update", gst_reviewer_permissions)

        compliance_permissions = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_COMPLIANCE_USER,
            ).values_list("permission__code", flat=True)
        )
        self.assertIn("compliance.tcs_section.view", compliance_permissions)
        self.assertIn("compliance.tcs_section.update", compliance_permissions)
        self.assertIn("tcs.section.view", compliance_permissions)
        self.assertIn("tcs.section.update", compliance_permissions)

    def test_seed_entity_reconciles_roles_and_permissions_after_subscription_downgrade(self):
        enterprise_features = access_catalog.features_for_packages(
            [access_catalog.PACKAGE_ENTERPRISE]
        )
        user, entity, plan = self._create_subscription_entity(enabled_features=enterprise_features)
        RBACSeedService.seed_entity(entity=entity, actor=user)

        basic_features = access_catalog.features_for_packages(
            [access_catalog.PACKAGE_BASIC_ACCOUNTING]
        )
        for limit in plan.limits.filter(limit_type=PlanLimit.LimitType.BOOLEAN):
            limit.bool_value = limit.key in basic_features
            limit.save(update_fields=["bool_value", "updated_at"])

        RBACSeedService.seed_entity(entity=entity, actor=user)

        self.assertFalse(
            Role.objects.get(entity=entity, code=access_catalog.ROLE_TREASURY_USER).isactive
        )
        self.assertFalse(
            Role.objects.get(entity=entity, code=access_catalog.ROLE_GST_REVIEWER).isactive
        )
        admin_permission_codes = set(
            RolePermission.objects.filter(
                role__entity=entity,
                role__code=access_catalog.ROLE_ENTITY_SUPER_ADMIN,
            ).values_list("permission__code", flat=True)
        )
        self.assertNotIn("treasury.payment_batch.view", admin_permission_codes)
        self.assertNotIn("reports.gst_compliance_center.view", admin_permission_codes)
        self.assertNotIn("payroll.run.view", admin_permission_codes)
        self.assertIn("sales.invoice.view", admin_permission_codes)
