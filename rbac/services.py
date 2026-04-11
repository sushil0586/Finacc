from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from entity.models import Entity
from subscriptions.services import SubscriptionService

from .models import Menu, MenuPermission, Permission, RBACAuditLog, Role, RolePermission, UserRoleAssignment


class MenuTreeService:
    @staticmethod
    def root_queryset():
        return Menu.objects.filter(parent__isnull=True, isactive=True).order_by("sort_order", "name")


class RBACDevelopmentAccess:
    @staticmethod
    def allow_all():
        return bool(getattr(settings, "RBAC_DEV_ALLOW_ALL_ACCESS", False))


class EffectivePermissionService:
    @staticmethod
    def active_assignments_queryset(user, entity_id):
        now = timezone.now()
        return UserRoleAssignment.objects.filter(
            user=user,
            entity_id=entity_id,
            isactive=True,
            role__isactive=True,
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=now),
            Q(effective_to__isnull=True) | Q(effective_to__gte=now),
        )

    @staticmethod
    def role_summaries_for_user(user, entity_id):
        if RBACDevelopmentAccess.allow_all():
            return [
                {
                    "id": 0,
                    "name": "Development Full Access",
                    "code": "dev.full_access",
                    "description": "Dev-only synthetic full access role.",
                    "source": "development",
                    "is_primary": True,
                }
            ]

        assignments = list(
            EffectivePermissionService.active_assignments_queryset(user, entity_id)
            .select_related("role")
            .order_by("-is_primary", "role__priority", "role__name")
        )
        if assignments:
            return [
                {
                    "id": assignment.role_id,
                    "name": assignment.role.name,
                    "code": assignment.role.code,
                    "description": assignment.role.description,
                    "source": "rbac",
                    "is_primary": assignment.is_primary,
                }
                for assignment in assignments
            ]

        return []

    @staticmethod
    def permission_codes_for_user(user, entity_id, role_id=None):
        if RBACDevelopmentAccess.allow_all():
            return set(
                Permission.objects.filter(isactive=True).values_list("code", flat=True)
            )

        assignments = EffectivePermissionService.active_assignments_queryset(user, entity_id).select_related("role")
        if role_id is not None:
            assignments = assignments.filter(role_id=role_id)

        role_ids = list(assignments.values_list("role_id", flat=True))
        if not role_ids:
            return set()

        allowed = set(
            RolePermission.objects.filter(
                role_id__in=role_ids,
                isactive=True,
                effect=RolePermission.EFFECT_ALLOW,
                permission__isactive=True,
            ).values_list("permission__code", flat=True)
        )
        denied = set(
            RolePermission.objects.filter(
                role_id__in=role_ids,
                isactive=True,
                effect=RolePermission.EFFECT_DENY,
                permission__isactive=True,
            ).values_list("permission__code", flat=True)
        )
        return allowed - denied

    @staticmethod
    def entity_for_user(user, entity_id):
        if RBACDevelopmentAccess.allow_all():
            return Entity.objects.filter(id=entity_id).first()

        entity = Entity.objects.filter(id=entity_id).select_related("customer_account").first()
        if entity is None:
            return None
        if not SubscriptionService.has_entity_membership(user=user, entity=entity, backfill_owner=True):
            return None
        active_assignment_exists = EffectivePermissionService.active_assignments_queryset(
            user,
            entity_id,
        ).exists()
        if active_assignment_exists:
            return entity
        if entity.createdby_id != user.id:
            return None
        if UserRoleAssignment.objects.filter(user=user, entity_id=entity_id).exists():
            return None
        return entity


class EffectiveMenuService:
    @staticmethod
    def _collect_visible_menu_ids(permission_codes):
        visible_ids = set(
            MenuPermission.objects.filter(
                permission__code__in=permission_codes,
                isactive=True,
                relation_type=MenuPermission.RELATION_VISIBILITY,
                menu__isactive=True,
            ).values_list("menu_id", flat=True)
        )
        if not visible_ids:
            return visible_ids

        pending_parent_ids = set(
            Menu.objects.filter(id__in=visible_ids, isactive=True)
            .exclude(parent_id__isnull=True)
            .values_list("parent_id", flat=True)
        )
        pending_parent_ids.discard(None)

        while pending_parent_ids:
            parents = list(
                Menu.objects.filter(id__in=pending_parent_ids, isactive=True).only("id", "parent_id")
            )
            next_pending = set()
            for parent in parents:
                visible_ids.add(parent.id)
                if parent.parent_id and parent.parent_id not in visible_ids:
                    next_pending.add(parent.parent_id)
            pending_parent_ids = next_pending

        return visible_ids

    @staticmethod
    def _build_recursive_tree(menu_queryset):
        menu_list = list(menu_queryset)
        children_map = {}
        for menu in menu_list:
            children_map.setdefault(menu.parent_id, []).append(menu)

        def serialize_node(node):
            normalized_route_path = (node.route_path or "").strip()
            if normalized_route_path and not normalized_route_path.startswith("/"):
                normalized_route_path = f"/{normalized_route_path}"
            return {
                "id": node.id,
                "name": node.name,
                "code": node.code,
                "menu_code": node.code,
                "menu_type": node.menu_type,
                "route_path": normalized_route_path,
                "route_name": node.route_name,
                "icon": node.icon,
                "sort_order": node.sort_order,
                "depth": node.depth,
                "children": [
                    serialize_node(child)
                    for child in children_map.get(node.id, [])
                ],
            }

        return [serialize_node(root) for root in children_map.get(None, [])]

    @staticmethod
    def menu_tree_for_user(user, entity_id, role_id=None):
        if RBACDevelopmentAccess.allow_all():
            queryset = (
                Menu.objects.filter(isactive=True)
                .only("id", "parent_id", "name", "code", "menu_type", "route_path", "route_name", "icon", "sort_order", "depth")
                .order_by("parent_id", "sort_order", "name")
            )
            return EffectiveMenuService._build_recursive_tree(queryset)

        permission_codes = EffectivePermissionService.permission_codes_for_user(user, entity_id, role_id=role_id)
        visible_menu_ids = EffectiveMenuService._collect_visible_menu_ids(permission_codes)
        if not visible_menu_ids:
            return []
        queryset = (
            Menu.objects.filter(id__in=visible_menu_ids, isactive=True)
            .only("id", "parent_id", "name", "code", "menu_type", "route_path", "route_name", "icon", "sort_order", "depth")
            .order_by("parent_id", "sort_order", "name")
        )
        return EffectiveMenuService._build_recursive_tree(queryset)


class LegacyMenuCompatibilityService:
    @staticmethod
    def legacy_shape_for_user(user, entity_id, role_id=None):
        menus = EffectiveMenuService.menu_tree_for_user(user, entity_id, role_id=role_id)
        final_rows = []
        for root in menus:
            submenus = LegacyMenuCompatibilityService._collect_leaf_nodes(root.get("children", []))
            final_rows.append(
                {
                    "mainmenu": root["name"],
                    "menuurl": root.get("route_path", ""),
                    "menucode": root.get("menu_code") or root.get("code"),
                    "submenu": submenus,
                }
            )
        return final_rows

    @staticmethod
    def _collect_leaf_nodes(nodes):
        collected = []
        for node in nodes:
            children = node.get("children") or []
            if node.get("menu_type") == Menu.TYPE_SCREEN or not children:
                collected.append(
                    {
                        "submenu": node.get("name", ""),
                        "subMenuurl": node.get("route_path", ""),
                        "submenucode": node.get("menu_code") or node.get("code"),
                    }
                )
                continue
            collected.extend(LegacyMenuCompatibilityService._collect_leaf_nodes(children))
        return collected


class RBACAuditService:
    @staticmethod
    def log(*, actor=None, entity=None, object_type, object_id, action, message="", changes=None):
        RBACAuditLog.objects.create(
            actor=actor,
            entity=entity,
            object_type=object_type,
            object_id=object_id,
            action=action,
            message=message,
            changes=changes or {},
        )


class AssignmentSemanticsService:
    @staticmethod
    def _current_entity_wide_queryset(*, user, entity, exclude_id=None):
        now = timezone.now()
        queryset = UserRoleAssignment.objects.filter(
            user=user,
            entity=entity,
            isactive=True,
            role__isactive=True,
            subentity__isnull=True,
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=now),
            Q(effective_to__isnull=True) | Q(effective_to__gte=now),
        )
        if exclude_id is not None:
            queryset = queryset.exclude(pk=exclude_id)
        return queryset

    @staticmethod
    def validate_assignment_shape(*, role, is_primary, subentity, isactive):
        if role is not None and not role.is_assignable:
            raise ValueError("Selected role is not assignable to users.")
        if is_primary and subentity is not None:
            raise ValueError("Primary assignment cannot be limited to a subentity.")
        if is_primary and not isactive:
            raise ValueError("Primary assignment must remain active.")

    @staticmethod
    @transaction.atomic
    def normalize_primary_assignments(*, user, entity, preferred_assignment=None):
        current_entity_wide = list(
            UserRoleAssignment.objects.filter(
                user=user,
                entity=entity,
                isactive=True,
                role__isactive=True,
                subentity__isnull=True,
            ).order_by("-is_primary", "role__priority", "id")
        )

        current_by_id = {assignment.id: assignment for assignment in current_entity_wide}
        target = None
        if preferred_assignment is not None and preferred_assignment.pk in current_by_id and preferred_assignment.is_primary:
            target = current_by_id[preferred_assignment.pk]
        else:
            target = (
                AssignmentSemanticsService._current_entity_wide_queryset(user=user, entity=entity)
                .order_by("role__priority", "id")
                .first()
            )

        target_id = getattr(target, "id", None)
        for assignment in current_entity_wide:
            should_be_primary = assignment.id == target_id
            if assignment.is_primary != should_be_primary:
                assignment.is_primary = should_be_primary
                assignment.save(update_fields=["is_primary", "updated_at"])

    @staticmethod
    @transaction.atomic
    def finalize_assignment(assignment):
        AssignmentSemanticsService.validate_assignment_shape(
            role=assignment.role,
            is_primary=assignment.is_primary,
            subentity=assignment.subentity,
            isactive=assignment.isactive,
        )
        AssignmentSemanticsService.normalize_primary_assignments(
            user=assignment.user,
            entity=assignment.entity,
            preferred_assignment=assignment if assignment.is_primary else None,
        )


class RoleTemplateService:
    TEMPLATE_DEFINITIONS = {
        "admin": {
            "name": "Admin",
            "description": "Broad operational access for entity administrators.",
            "permission_prefixes": [
                "admin.",
                "sales.",
                "purchase.",
                "inventory.",
                "accounts.",
                "compliance.",
                "reports.",
                "stock.",
                "payment.",
                "receipt.",
                "production.",
                "tds.",
                "credit.",
                "debit.",
                "tcs.",
                "payroll.",
                "masters.",
                "voucher.",
            ],
        },
        "sales_user": {
            "name": "Sales User",
            "description": "Sales invoice and note operations.",
            "permission_prefixes": ["sales.", "credit.", "debit."],
            "exclude_codes": ["sales.settings.update"],
        },
        "purchase_user": {
            "name": "Purchase User",
            "description": "Purchase invoice operations.",
            "permission_prefixes": ["purchase."],
        },
        "accounts_user": {
            "name": "Accounts User",
            "description": "Voucher operations for receipts, payments, and TDS.",
            "permission_prefixes": ["accounts.", "payment.", "receipt.", "tds."],
        },
        "report_viewer": {
            "name": "Report Viewer",
            "description": "Read-only reporting access.",
            "permission_prefixes": ["reports."],
        },
        "payables_user": {
            "name": "Payables User",
            "description": "Core accounts payable reporting access.",
            "exact_codes": [
                "reports.payables.view",
                "reports.vendoroutstanding.view",
                "reports.accountspayableaging.view",
                "reports.purchasebook.view",
                "reports.vendorledgerstatement.view",
                "reports.vendorsettlementhistory.view",
                "reports.vendornoteregister.view",
            ],
            "exclude_codes": [
                "reports.apglreconciliation.view",
                "reports.vendorbalanceexceptions.view",
                "reports.payablesclosepack.view",
                "reports.payables.export",
            ],
        },
        "payroll_user": {
            "name": "Payroll User",
            "description": "Payroll and employee administration access.",
            "permission_prefixes": ["payroll.", "payments.payroll.", "reports.payroll."],
        },
        "compliance_user": {
            "name": "Compliance User",
            "description": "TCS and TDS compliance access.",
            "permission_prefixes": ["tcs.", "tds.", "compliance.", "reports.compliance."],
        },
    }

    @staticmethod
    def _permission_queryset_for_template(template_code):
        config = RoleTemplateService.TEMPLATE_DEFINITIONS.get(template_code)
        if not config:
            return Permission.objects.none()

        queryset = Permission.objects.filter(isactive=True)
        clauses = Q()
        for prefix in config.get("permission_prefixes", []):
            clauses |= Q(code__startswith=prefix)
        for exact_code in config.get("exact_codes", []):
            clauses |= Q(code=exact_code)
        if clauses:
            queryset = queryset.filter(clauses)
        exclude_codes = config.get("exclude_codes", [])
        if exclude_codes:
            queryset = queryset.exclude(code__in=exclude_codes)
        return queryset.distinct()

    @staticmethod
    def template_catalog():
        templates = []
        for code, config in RoleTemplateService.TEMPLATE_DEFINITIONS.items():
            permissions = list(
                RoleTemplateService._permission_queryset_for_template(code)
                .order_by("module", "resource", "action", "name")
                .values("id", "code", "name", "module", "resource", "action")
            )
            templates.append(
                {
                    "code": code,
                    "name": config["name"],
                    "description": config["description"],
                    "permissions": permissions,
                }
            )
        return templates

    @staticmethod
    @transaction.atomic
    def apply_template(role, template_code, permission_ids, actor=None):
        template_queryset = RoleTemplateService._permission_queryset_for_template(template_code)
        template_permission_ids = set(template_queryset.values_list("id", flat=True))
        if not template_permission_ids:
            selected_ids = set(permission_ids)
        else:
            selected_ids = set(permission_ids) if permission_ids else set(template_permission_ids)
            selected_ids &= template_permission_ids

        RolePermission.objects.filter(role=role, permission_id__in=template_permission_ids).exclude(
            permission_id__in=selected_ids
        ).delete()
        existing_ids = set(RolePermission.objects.filter(role=role, permission_id__in=selected_ids).values_list("permission_id", flat=True))
        missing_ids = selected_ids - existing_ids
        RolePermission.objects.bulk_create(
            [
                RolePermission(role=role, permission_id=permission_id, effect=RolePermission.EFFECT_ALLOW)
                for permission_id in missing_ids
            ]
        )
        RBACAuditService.log(
            actor=actor,
            entity=role.entity,
            object_type="role",
            object_id=role.id,
            action=RBACAuditLog.ACTION_APPLY_TEMPLATE,
            message=f"Applied template {template_code} to role {role.name}.",
            changes={"template": template_code, "permission_ids": sorted(selected_ids)},
        )
        return selected_ids


class RoleCloneService:
    @staticmethod
    @transaction.atomic
    def clone_role(source_role, *, name, code, actor=None, description=None):
        clone = Role.objects.create(
            entity=source_role.entity,
            name=name,
            code=code,
            description=description if description is not None else source_role.description,
            role_level=source_role.role_level,
            is_system_role=False,
            is_assignable=source_role.is_assignable,
            priority=source_role.priority,
            metadata=source_role.metadata,
            createdby=actor,
            isactive=True,
        )
        RolePermission.objects.bulk_create(
            [
                RolePermission(
                    role=clone,
                    permission=role_permission.permission,
                    effect=role_permission.effect,
                    metadata=role_permission.metadata,
                    isactive=role_permission.isactive,
                )
                for role_permission in source_role.role_permissions.filter(isactive=True).select_related("permission")
            ]
        )
        RBACAuditService.log(
            actor=actor,
            entity=clone.entity,
            object_type="role",
            object_id=clone.id,
            action=RBACAuditLog.ACTION_CLONE,
            message=f"Cloned role {source_role.name} to {clone.name}.",
            changes={"source_role_id": source_role.id},
        )
        return clone






