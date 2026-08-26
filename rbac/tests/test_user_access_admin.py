from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from entity.models import Entity
from entity.models import SubEntity
from subscriptions.models import UserEntityAccess
from subscriptions.services import SubscriptionService

from rbac.models import Menu, Permission, RBACAuditLog, Role, RolePermission, UserRoleAssignment


User = get_user_model()


class RbacUserAccessAdminTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="Admin@123",
            first_name="Admin",
        )
        self.entity = Entity.objects.create(entityname="Acme", createdby=self.admin_user)
        SubscriptionService.register_entity_creation(entity=self.entity, owner=self.admin_user)
        self.entity.refresh_from_db()
        self.subentity = SubEntity.objects.create(subentityname="Head Office", entity=self.entity)
        self.admin_role = Role.objects.create(
            entity=self.entity,
            name="Entity Admin",
            code="entity.admin",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        for code in (
            "admin.user.view",
            "admin.user.create",
            "admin.user.update",
            "admin.user.delete",
            "admin.user_access.view",
            "admin.user_access.update",
            "admin.role.view",
            "admin.role.create",
            "admin.role.update",
            "admin.role.delete",
            "admin.role_access.view",
            "admin.role_access.update",
        ):
            permission, _ = Permission.objects.get_or_create(
                code=code,
                defaults={
                    "name": code,
                    "module": "admin",
                    "resource": "user",
                    "action": code.rsplit(".", 1)[-1],
                },
            )
            RolePermission.objects.get_or_create(role=self.admin_role, permission=permission)
        UserRoleAssignment.objects.create(
            user=self.admin_user,
            entity=self.entity,
            role=self.admin_role,
            assigned_by=self.admin_user,
            is_primary=True,
        )
        self.client.force_authenticate(self.admin_user)

    def test_admin_user_search_is_limited_to_tenant_members(self):
        outsider = User.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="Pass@123",
            first_name="Out",
            last_name="Sider",
        )

        response = self.client.get(
            reverse("rbac_api:admin-users"),
            {"entity": self.entity.id, "q": "outsider"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_create_and_assign_creates_user_and_assignment(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="Operator",
            code="entity.operator",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        effective_from = timezone.now()
        effective_to = effective_from + timedelta(days=7)

        response = self.client.post(
            reverse("rbac_api:admin-users-create-and-assign"),
            {
                "entity": self.entity.id,
                "first_name": "New",
                "last_name": "User",
                "email": "new.user@example.com",
                "username": "new.user",
                "password": "Secure@12345",
                "role": target_role.id,
                "effective_from": effective_from.isoformat(),
                "effective_to": effective_to.isoformat(),
                "is_primary": True,
                "isactive": True,
                "scope_data": {"region": "north"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(email="new.user@example.com")
        assignment = UserRoleAssignment.objects.get(user=created_user, entity=self.entity, role=target_role)
        self.entity.refresh_from_db()
        self.assertTrue(assignment.is_primary)
        self.assertEqual(assignment.scope_data["region"], "north")
        self.assertIsNotNone(assignment.effective_from)
        self.assertIsNotNone(assignment.effective_to)
        self.assertTrue(
            UserEntityAccess.objects.filter(
                customer_account=self.entity.customer_account,
                user=created_user,
                is_active=True,
            ).exists()
        )

    def test_bulk_assign_persists_effective_dates(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="Reviewer",
            code="entity.reviewer",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        target_user = User.objects.create_user(
            username="reviewer",
            email="reviewer@example.com",
            password="Review@123",
        )
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=target_user,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.admin_user,
        )
        effective_from = timezone.now()
        effective_to = effective_from + timedelta(days=10)

        response = self.client.post(
            reverse("rbac_api:admin-assignments-bulk"),
            {
                "entity": self.entity.id,
                "user_ids": [target_user.id],
                "role": target_role.id,
                "effective_from": effective_from.isoformat(),
                "effective_to": effective_to.isoformat(),
                "is_primary": False,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assignment = UserRoleAssignment.objects.get(user=target_user, entity=self.entity, role=target_role)
        self.entity.refresh_from_db()
        self.assertIsNotNone(assignment.effective_from)
        self.assertIsNotNone(assignment.effective_to)
        self.assertTrue(
            UserEntityAccess.objects.filter(
                customer_account=self.entity.customer_account,
                user=target_user,
                is_active=True,
            ).exists()
        )

    def test_bulk_assign_rejects_user_without_tenant_membership(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="Reviewer",
            code="entity.reviewer.2",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        outsider = User.objects.create_user(
            username="reviewer-out",
            email="reviewer-out@example.com",
            password="Review@123",
        )

        response = self.client.post(
            reverse("rbac_api:admin-assignments-bulk"),
            {
                "entity": self.entity.id,
                "user_ids": [outsider.id],
                "role": target_role.id,
                "is_primary": False,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_ids", response.data)

    def test_new_primary_assignment_demotes_existing_primary(self):
        existing_role = Role.objects.create(
            entity=self.entity,
            name="Existing",
            code="entity.existing",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        existing_assignment = UserRoleAssignment.objects.create(
            user=self.admin_user,
            entity=self.entity,
            role=existing_role,
            assigned_by=self.admin_user,
            is_primary=True,
        )
        target_role = Role.objects.create(
            entity=self.entity,
            name="Operator",
            code="entity.operator",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )

        response = self.client.post(
            reverse("rbac_api:admin-assignments"),
            {
                "entity": self.entity.id,
                "user": self.admin_user.id,
                "role": target_role.id,
                "is_primary": True,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        existing_assignment.refresh_from_db()
        new_assignment = UserRoleAssignment.objects.get(user=self.admin_user, entity=self.entity, role=target_role)
        self.assertFalse(existing_assignment.is_primary)
        self.assertTrue(new_assignment.is_primary)

    def test_subentity_scoped_assignment_cannot_be_primary(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="Branch Operator",
            code="entity.branch.operator",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )

        response = self.client.post(
            reverse("rbac_api:admin-assignments"),
            {
                "entity": self.entity.id,
                "user": self.admin_user.id,
                "role": target_role.id,
                "subentity": self.subentity.id,
                "is_primary": True,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("subentity", response.data)

    def test_single_assignment_rejects_user_without_tenant_membership(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="Member Operator",
            code="entity.member.operator",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        outsider = User.objects.create_user(
            username="outsider-role",
            email="outsider-role@example.com",
            password="Out@12345",
        )

        response = self.client.post(
            reverse("rbac_api:admin-assignments"),
            {
                "entity": self.entity.id,
                "user": outsider.id,
                "role": target_role.id,
                "is_primary": False,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user", response.data)

    def test_non_assignable_role_cannot_be_assigned(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="System Role",
            code="entity.system.role",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
            is_assignable=False,
        )

        response = self.client.post(
            reverse("rbac_api:admin-assignments"),
            {
                "entity": self.entity.id,
                "user": self.admin_user.id,
                "role": target_role.id,
                "is_primary": False,
                "isactive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

    def test_delete_assignment_blocks_last_active_customer_admin_access(self):
        assignment = UserRoleAssignment.objects.get(user=self.admin_user, entity=self.entity, role=self.admin_role)

        response = self.client.delete(
            f"{reverse('rbac_api:admin-assignment-detail', kwargs={'pk': assignment.id})}?entity={self.entity.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "rbac_last_admin_assignment")
        self.assertIn("Cannot remove the last active customer-admin access", response.data["detail"])
        assignment.refresh_from_db()
        self.assertTrue(assignment.isactive)

    def test_update_assignment_blocks_demoting_last_customer_admin_role(self):
        assignment = UserRoleAssignment.objects.get(user=self.admin_user, entity=self.entity, role=self.admin_role)
        non_admin_role = Role.objects.create(
            entity=self.entity,
            name="Operations Only",
            code="entity.operations.only",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )

        response = self.client.patch(
            f"{reverse('rbac_api:admin-assignment-detail', kwargs={'pk': assignment.id})}?entity={self.entity.id}",
            {"role": non_admin_role.id, "is_primary": True, "isactive": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "rbac_last_admin_assignment")
        assignment.refresh_from_db()
        self.assertEqual(assignment.role_id, self.admin_role.id)

    def test_delete_assignment_allows_admin_removal_when_another_admin_assignment_exists(self):
        backup_admin = User.objects.create_user(
            username="backup-admin",
            email="backup-admin@example.com",
            password="Backup@123",
        )
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=backup_admin,
            role=UserEntityAccess.Role.ADMIN,
            granted_by=self.admin_user,
        )
        UserRoleAssignment.objects.create(
            user=backup_admin,
            entity=self.entity,
            role=self.admin_role,
            assigned_by=self.admin_user,
            is_primary=True,
        )
        assignment = UserRoleAssignment.objects.get(user=self.admin_user, entity=self.entity, role=self.admin_role)

        response = self.client.delete(
            f"{reverse('rbac_api:admin-assignment-detail', kwargs={'pk': assignment.id})}?entity={self.entity.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        assignment.refresh_from_db()
        self.assertFalse(assignment.isactive)

    def test_role_permission_update_blocks_removing_last_customer_admin_permission_set(self):
        original_permission_ids = set(
            RolePermission.objects.filter(role=self.admin_role).values_list("permission_id", flat=True)
        )

        response = self.client.put(
            f"{reverse('rbac_api:admin-role-permissions', kwargs={'pk': self.admin_role.id})}?entity={self.entity.id}",
            {"permission_ids": []},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "rbac_last_admin_permission_set")
        self.assertIn("Cannot remove the last admin-capable permission set", response.data["detail"])
        retained_permission_ids = set(
            RolePermission.objects.filter(role=self.admin_role).values_list("permission_id", flat=True)
        )
        self.assertEqual(retained_permission_ids, original_permission_ids)

    def test_role_permission_update_allows_admin_permission_removal_when_backup_role_exists(self):
        backup_admin = User.objects.create_user(
            username="backup-permission-admin",
            email="backup-permission-admin@example.com",
            password="Backup@123",
        )
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=backup_admin,
            role=UserEntityAccess.Role.ADMIN,
            granted_by=self.admin_user,
        )
        backup_role = Role.objects.create(
            entity=self.entity,
            name="Backup Access Admin",
            code="entity.backup.access.admin",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        admin_permission = Permission.objects.get(code="admin.user_access.update")
        RolePermission.objects.create(role=backup_role, permission=admin_permission)
        UserRoleAssignment.objects.create(
            user=backup_admin,
            entity=self.entity,
            role=backup_role,
            assigned_by=self.admin_user,
            is_primary=True,
        )

        response = self.client.put(
            f"{reverse('rbac_api:admin-role-permissions', kwargs={'pk': self.admin_role.id})}?entity={self.entity.id}",
            {"permission_ids": []},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(RolePermission.objects.filter(role=self.admin_role).exists())

    def test_role_permission_update_requires_allowed_screens_update_permission(self):
        role_editor = User.objects.create_user(
            username="role-editor",
            email="role-editor@example.com",
            password="Editor@123",
        )
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=role_editor,
            role=UserEntityAccess.Role.ADMIN,
            granted_by=self.admin_user,
        )
        editor_role = Role.objects.create(
            entity=self.entity,
            name="Role Metadata Editor",
            code="entity.role.metadata.editor",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        role_update_permission = Permission.objects.get(code="admin.role.update")
        RolePermission.objects.create(role=editor_role, permission=role_update_permission)
        UserRoleAssignment.objects.create(
            user=role_editor,
            entity=self.entity,
            role=editor_role,
            assigned_by=self.admin_user,
            is_primary=True,
        )
        target_role = Role.objects.create(
            entity=self.entity,
            name="Sales Viewer",
            code="entity.sales.viewer",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )

        self.client.force_authenticate(role_editor)
        response = self.client.put(
            f"{reverse('rbac_api:admin-role-permissions', kwargs={'pk': target_role.id})}?entity={self.entity.id}",
            {"permission_ids": [role_update_permission.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(RolePermission.objects.filter(role=target_role).exists())

    def test_role_template_apply_requires_allowed_screens_update_permission(self):
        role_editor = User.objects.create_user(
            username="template-editor",
            email="template-editor@example.com",
            password="Editor@123",
        )
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=role_editor,
            role=UserEntityAccess.Role.ADMIN,
            granted_by=self.admin_user,
        )
        editor_role = Role.objects.create(
            entity=self.entity,
            name="Template Metadata Editor",
            code="entity.template.metadata.editor",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        RolePermission.objects.create(role=editor_role, permission=Permission.objects.get(code="admin.role.update"))
        UserRoleAssignment.objects.create(
            user=role_editor,
            entity=self.entity,
            role=editor_role,
            assigned_by=self.admin_user,
            is_primary=True,
        )
        target_role = Role.objects.create(
            entity=self.entity,
            name="Template Target",
            code="entity.template.target",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )

        self.client.force_authenticate(role_editor)
        response = self.client.post(
            f"{reverse('rbac_api:admin-role-apply-template', kwargs={'pk': target_role.id})}?entity={self.entity.id}",
            {"template_code": "admin"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(RolePermission.objects.filter(role=target_role).exists())

    def test_role_clone_requires_allowed_screens_update_when_copying_permissions(self):
        role_creator = User.objects.create_user(
            username="role-creator",
            email="role-creator@example.com",
            password="Creator@123",
        )
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=role_creator,
            role=UserEntityAccess.Role.ADMIN,
            granted_by=self.admin_user,
        )
        creator_role = Role.objects.create(
            entity=self.entity,
            name="Role Creator",
            code="entity.role.creator",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        RolePermission.objects.create(role=creator_role, permission=Permission.objects.get(code="admin.role.create"))
        UserRoleAssignment.objects.create(
            user=role_creator,
            entity=self.entity,
            role=creator_role,
            assigned_by=self.admin_user,
            is_primary=True,
        )

        self.client.force_authenticate(role_creator)
        response = self.client.post(
            f"{reverse('rbac_api:admin-role-clone', kwargs={'pk': self.admin_role.id})}?entity={self.entity.id}",
            {"name": "Admin Clone", "code": "ADMIN_CLONE"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Role.objects.filter(entity=self.entity, code="ADMIN_CLONE").exists())

    def test_role_clone_with_allowed_screens_update_copies_permissions(self):
        clone_admin = User.objects.create_user(
            username="role-clone-admin",
            email="role-clone-admin@example.com",
            password="Clone@123",
        )
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=clone_admin,
            role=UserEntityAccess.Role.ADMIN,
            granted_by=self.admin_user,
        )
        clone_role = Role.objects.create(
            entity=self.entity,
            name="Role Clone Admin",
            code="entity.role.clone.admin",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        for code in ("admin.role.create", "admin.role_access.update"):
            RolePermission.objects.create(role=clone_role, permission=Permission.objects.get(code=code))
        UserRoleAssignment.objects.create(
            user=clone_admin,
            entity=self.entity,
            role=clone_role,
            assigned_by=self.admin_user,
            is_primary=True,
        )

        self.client.force_authenticate(clone_admin)
        response = self.client.post(
            f"{reverse('rbac_api:admin-role-clone', kwargs={'pk': self.admin_role.id})}?entity={self.entity.id}",
            {"name": "Admin Clone Allowed", "code": "ADMIN_CLONE_ALLOWED"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        cloned_role = Role.objects.get(entity=self.entity, code="ADMIN_CLONE_ALLOWED")
        self.assertEqual(
            RolePermission.objects.filter(role=cloned_role, isactive=True).count(),
            RolePermission.objects.filter(role=self.admin_role, isactive=True).count(),
        )

    def test_rbac_recovery_actions_write_useful_audit_logs(self):
        role = Role.objects.create(
            entity=self.entity,
            name="Audited Role",
            code="entity.audited.role",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        permission = Permission.objects.create(
            code="sales.audit.invoice.view",
            name="View Audited Sales Invoice",
            module="sales",
            resource="invoice",
            action="view",
        )
        menu = Menu.objects.create(
            name="Audited Sales",
            code="audited_sales",
            menu_type=Menu.TYPE_SCREEN,
            route_path="audited-sales",
        )
        target_user = User.objects.create_user(
            username="audited-user",
            email="audited-user@example.com",
            password="Audit@123",
        )
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=target_user,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.admin_user,
        )

        role_permission_response = self.client.put(
            f"{reverse('rbac_api:admin-role-permissions', kwargs={'pk': role.id})}?entity={self.entity.id}",
            {"permission_ids": [permission.id]},
            format="json",
        )
        self.assertEqual(role_permission_response.status_code, status.HTTP_200_OK)
        role_permission_log = RBACAuditLog.objects.filter(object_type="role", object_id=role.id, action=RBACAuditLog.ACTION_UPDATE).latest("created_at")
        self.assertEqual(role_permission_log.actor_id, self.admin_user.id)
        self.assertEqual(role_permission_log.entity_id, self.entity.id)
        self.assertEqual(role_permission_log.changes["granted_permission_ids"], [permission.id])

        template_response = self.client.post(
            f"{reverse('rbac_api:admin-role-apply-template', kwargs={'pk': role.id})}?entity={self.entity.id}",
            {"template_code": "sales_user", "permission_ids": [permission.id]},
            format="json",
        )
        self.assertEqual(template_response.status_code, status.HTTP_200_OK)
        template_log = RBACAuditLog.objects.filter(object_type="role", object_id=role.id, action=RBACAuditLog.ACTION_APPLY_TEMPLATE).latest("created_at")
        self.assertEqual(template_log.changes["template"], "sales_user")
        self.assertEqual(template_log.changes["permission_ids"], [permission.id])

        clone_response = self.client.post(
            f"{reverse('rbac_api:admin-role-clone', kwargs={'pk': role.id})}?entity={self.entity.id}",
            {"name": "Audited Role Copy", "code": "AUDITED_ROLE_COPY"},
            format="json",
        )
        self.assertEqual(clone_response.status_code, status.HTTP_201_CREATED)
        cloned_role = Role.objects.get(entity=self.entity, code="AUDITED_ROLE_COPY")
        clone_log = RBACAuditLog.objects.filter(object_type="role", object_id=cloned_role.id, action=RBACAuditLog.ACTION_CLONE).latest("created_at")
        self.assertEqual(clone_log.changes["source_role_id"], role.id)

        menu_permission_response = self.client.put(
            f"{reverse('rbac_api:admin-menu-permissions', kwargs={'pk': menu.id})}?entity={self.entity.id}",
            {"permission_ids": [permission.id], "relation_type": "visibility"},
            format="json",
        )
        self.assertEqual(menu_permission_response.status_code, status.HTTP_200_OK)
        menu_log = RBACAuditLog.objects.filter(object_type="menu", object_id=menu.id, action=RBACAuditLog.ACTION_UPDATE).latest("created_at")
        self.assertEqual(menu_log.changes["relation_type"], "visibility")
        self.assertEqual(menu_log.changes["granted_permission_ids"], [permission.id])

        assignment_response = self.client.post(
            f"{reverse('rbac_api:admin-assignments')}?entity={self.entity.id}",
            {
                "user": target_user.id,
                "role": role.id,
                "is_primary": False,
                "isactive": True,
            },
            format="json",
        )
        self.assertEqual(assignment_response.status_code, status.HTTP_201_CREATED)
        assignment = UserRoleAssignment.objects.get(user=target_user, entity=self.entity, role=role)
        assignment_log = RBACAuditLog.objects.filter(object_type="assignment", object_id=assignment.id, action=RBACAuditLog.ACTION_ASSIGN).latest("created_at")
        self.assertEqual(assignment_log.changes["user_id"], target_user.id)
        self.assertEqual(assignment_log.changes["role_id"], role.id)

        updated_effective_to = timezone.now() + timedelta(days=30)
        update_response = self.client.patch(
            f"{reverse('rbac_api:admin-assignment-detail', kwargs={'pk': assignment.id})}?entity={self.entity.id}",
            {"effective_to": updated_effective_to.isoformat(), "is_primary": False, "isactive": True},
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        update_log = RBACAuditLog.objects.filter(object_type="assignment", object_id=assignment.id, action=RBACAuditLog.ACTION_UPDATE).latest("created_at")
        self.assertIn("before", update_log.changes)
        self.assertIn("after", update_log.changes)
        self.assertIsNone(update_log.changes["before"]["effective_to"])
        self.assertIsNotNone(update_log.changes["after"]["effective_to"])

        delete_response = self.client.delete(
            f"{reverse('rbac_api:admin-assignment-detail', kwargs={'pk': assignment.id})}?entity={self.entity.id}"
        )
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        delete_log = RBACAuditLog.objects.filter(object_type="assignment", object_id=assignment.id, action=RBACAuditLog.ACTION_DEACTIVATE).latest("created_at")
        self.assertEqual(delete_log.changes["isactive"], False)

        bulk_user = User.objects.create_user(
            username="audited-bulk-user",
            email="audited-bulk-user@example.com",
            password="Audit@123",
        )
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=bulk_user,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.admin_user,
        )
        bulk_response = self.client.post(
            reverse("rbac_api:admin-assignments-bulk"),
            {
                "entity": self.entity.id,
                "user_ids": [bulk_user.id],
                "role": role.id,
                "is_primary": False,
                "isactive": True,
            },
            format="json",
        )
        self.assertEqual(bulk_response.status_code, status.HTTP_200_OK)
        bulk_log = RBACAuditLog.objects.filter(object_type="assignment_bulk", object_id=role.id, action=RBACAuditLog.ACTION_ASSIGN).latest("created_at")
        self.assertEqual(bulk_log.changes["user_ids"], [bulk_user.id])
        self.assertTrue(bulk_log.changes["created_assignment_ids"])

    def test_role_deactivation_is_blocked_when_active_assignments_exist(self):
        target_role = Role.objects.create(
            entity=self.entity,
            name="Operator",
            code="entity.operator.locked",
            role_level=Role.LEVEL_ENTITY,
            createdby=self.admin_user,
        )
        target_user = User.objects.create_user(
            username="operator-blocked",
            email="operator-blocked@example.com",
            password="Secure@123",
        )
        SubscriptionService.ensure_account_membership(
            customer_account=self.entity.customer_account,
            user=target_user,
            role=UserEntityAccess.Role.MEMBER,
            granted_by=self.admin_user,
        )
        UserRoleAssignment.objects.create(
            user=target_user,
            entity=self.entity,
            role=target_role,
            assigned_by=self.admin_user,
            isactive=True,
        )

        response = self.client.delete(
            f"{reverse('rbac_api:admin-role-detail', kwargs={'pk': target_role.id})}?entity={self.entity.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot deactivate role", response.data["detail"])
