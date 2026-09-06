from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from rbac.services import EffectivePermissionService


class EffectivePermissionScopeAccessTests(SimpleTestCase):
    def _assignments(self, *, entity_wide=False, matching_branch=False):
        queryset = Mock()
        queryset.exists.return_value = True

        def filtered(**kwargs):
            result = Mock()
            if kwargs == {"subentity__isnull": True}:
                result.exists.return_value = entity_wide
            else:
                result.exists.return_value = matching_branch
            return result

        queryset.filter.side_effect = filtered
        return queryset

    @patch("rbac.services.RBACDevelopmentAccess.allow_all", return_value=False)
    @patch("rbac.services.EffectivePermissionService.active_assignments_queryset")
    def test_entity_wide_assignment_covers_any_branch(self, assignments, _allow_all):
        assignments.return_value = self._assignments(entity_wide=True)

        self.assertTrue(EffectivePermissionService.has_scope_access(SimpleNamespace(), 1, 22))

    @patch("rbac.services.RBACDevelopmentAccess.allow_all", return_value=False)
    @patch("rbac.services.EffectivePermissionService.active_assignments_queryset")
    def test_branch_assignment_covers_matching_branch(self, assignments, _allow_all):
        assignments.return_value = self._assignments(matching_branch=True)

        self.assertTrue(EffectivePermissionService.has_scope_access(SimpleNamespace(), 1, 22))

    @patch("rbac.services.RBACDevelopmentAccess.allow_all", return_value=False)
    @patch("rbac.services.EffectivePermissionService.active_assignments_queryset")
    def test_branch_assignment_rejects_another_branch(self, assignments, _allow_all):
        assignments.return_value = self._assignments(matching_branch=False)

        self.assertFalse(EffectivePermissionService.has_scope_access(SimpleNamespace(), 1, 99))

    @patch("rbac.services.RBACDevelopmentAccess.allow_all", return_value=False)
    @patch("rbac.services.EffectivePermissionService.active_assignments_queryset")
    def test_branch_assignment_rejects_unscoped_aggregate(self, assignments, _allow_all):
        assignments.return_value = self._assignments(matching_branch=True)

        self.assertFalse(EffectivePermissionService.has_scope_access(SimpleNamespace(), 1, None))

    @patch("rbac.services.RBACDevelopmentAccess.allow_all", return_value=False)
    @patch("rbac.services.EffectivePermissionService.active_assignments_queryset")
    def test_legacy_user_without_assignments_retains_membership_access(self, assignments, _allow_all):
        queryset = Mock()
        queryset.exists.return_value = False
        assignments.return_value = queryset

        self.assertTrue(EffectivePermissionService.has_scope_access(SimpleNamespace(), 1, 22))
