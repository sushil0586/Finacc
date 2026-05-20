from __future__ import annotations

from collections.abc import Iterable

from rest_framework.exceptions import PermissionDenied

from rbac.services import EffectivePermissionService


GST_RECON_VIEW_PERMISSIONS = ("gst.reconciliation.view",)
GST_RECON_REVIEW_PERMISSIONS = ("gst.reconciliation.review", "gst.reconciliation.manage")
GST_RECON_MANAGE_PERMISSIONS = ("gst.reconciliation.manage",)


class GstReconciliationWorkflowAccess:
    """
    Phase 3 workflow hooks.

    Keep this centralized so we can later swap these checks with
    entity/RBAC-specific policy lookups without changing the APIs.
    """

    @staticmethod
    def _is_privileged(user) -> bool:
        return bool(getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))

    @classmethod
    def permission_codes_for_entity(cls, *, user, entity_id: int | None) -> set[str]:
        if not user or not getattr(user, "is_authenticated", False) or not entity_id:
            return set()
        return set(EffectivePermissionService.permission_codes_for_user(user, entity_id))

    @classmethod
    def assert_entity_access(cls, *, user, entity_id: int):
        entity = EffectivePermissionService.entity_for_user(user, entity_id)
        if entity is None:
            raise PermissionDenied("You do not have access to this GST reconciliation entity scope.")
        return entity

    @classmethod
    def _has_any_permission(cls, *, user, entity_id: int | None, required_permissions: Iterable[str]) -> bool:
        if cls._is_privileged(user):
            return True
        resolved = cls.permission_codes_for_entity(user=user, entity_id=entity_id)
        return any(code in resolved for code in tuple(required_permissions or ()))

    @classmethod
    def assert_can_view_scope(cls, *, user, entity_id: int) -> None:
        cls.assert_entity_access(user=user, entity_id=entity_id)
        if not cls._has_any_permission(user=user, entity_id=entity_id, required_permissions=GST_RECON_VIEW_PERMISSIONS):
            raise PermissionDenied("You do not have permission to view GST reconciliation data for this entity.")

    @classmethod
    def assert_can_review_scope(cls, *, user, entity_id: int) -> None:
        cls.assert_entity_access(user=user, entity_id=entity_id)
        if not cls._has_any_permission(user=user, entity_id=entity_id, required_permissions=GST_RECON_REVIEW_PERMISSIONS):
            raise PermissionDenied("You do not have permission to review GST reconciliation items for this entity.")

    @classmethod
    def assert_can_manage_scope(cls, *, user, entity_id: int) -> None:
        cls.assert_entity_access(user=user, entity_id=entity_id)
        if not cls._has_any_permission(user=user, entity_id=entity_id, required_permissions=GST_RECON_MANAGE_PERMISSIONS):
            raise PermissionDenied("You do not have permission to manage GST reconciliation runs for this entity.")

    @classmethod
    def assert_can_view_run(cls, *, user, run) -> None:
        cls.assert_can_view_scope(user=user, entity_id=run.entity_id)

    @classmethod
    def assert_can_view_item(cls, *, user, item) -> None:
        cls.assert_can_view_run(user=user, run=item.run)

    @classmethod
    def can_assign_item(cls, *, user, item) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return cls._has_any_permission(user=user, entity_id=item.entity_id, required_permissions=GST_RECON_REVIEW_PERMISSIONS)

    @classmethod
    def can_manual_match(cls, *, user, item) -> bool:
        return cls.can_review_item(user=user, item=item)

    @classmethod
    def can_accept_mismatch(cls, *, user, item) -> bool:
        return cls.can_review_item(user=user, item=item)

    @classmethod
    def can_review_item(cls, *, user, item) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if cls._is_privileged(user):
            return True
        if not cls._has_any_permission(user=user, entity_id=item.entity_id, required_permissions=GST_RECON_REVIEW_PERMISSIONS):
            return False
        if item.assigned_reviewer_id:
            return item.assigned_reviewer_id == user.id
        return True

    @classmethod
    def can_bulk_review(cls, *, user, run) -> bool:
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and cls._has_any_permission(user=user, entity_id=run.entity_id, required_permissions=GST_RECON_REVIEW_PERMISSIONS)
        )

    @classmethod
    def can_close_run(cls, *, user, run) -> bool:
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and cls._has_any_permission(user=user, entity_id=run.entity_id, required_permissions=GST_RECON_MANAGE_PERMISSIONS)
        )

    @classmethod
    def assert_can_assign_item(cls, *, user, item) -> None:
        if not cls.can_assign_item(user=user, item=item):
            raise PermissionDenied("You are not allowed to assign this reconciliation item.")

    @classmethod
    def assert_can_review_item(cls, *, user, item) -> None:
        if not cls.can_review_item(user=user, item=item):
            raise PermissionDenied("You are not allowed to review this reconciliation item.")

    @classmethod
    def assert_can_manual_match(cls, *, user, item) -> None:
        if not cls.can_manual_match(user=user, item=item):
            raise PermissionDenied("You are not allowed to manually match this reconciliation item.")

    @classmethod
    def assert_can_accept_mismatch(cls, *, user, item) -> None:
        if not cls.can_accept_mismatch(user=user, item=item):
            raise PermissionDenied("You are not allowed to accept mismatch on this reconciliation item.")

    @classmethod
    def assert_can_bulk_review(cls, *, user, run) -> None:
        if not cls.can_bulk_review(user=user, run=run):
            raise PermissionDenied("You are not allowed to perform bulk reconciliation actions.")

    @classmethod
    def assert_can_close_run(cls, *, user, run) -> None:
        if not cls.can_close_run(user=user, run=run):
            raise PermissionDenied("You are not allowed to close this reconciliation run.")
