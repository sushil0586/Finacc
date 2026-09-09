from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from rbac.models import DataAccessPolicy
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


class EffectivePermissionDataScopeAccessTests(SimpleTestCase):
    def _assignment_queryset(self, *role_policies):
        assignments = []
        for policies in role_policies:
            manager = Mock()
            manager.all.return_value = [
                SimpleNamespace(isactive=True, policy=policy)
                for policy in policies
            ]
            assignments.append(SimpleNamespace(role=SimpleNamespace(data_policies=manager)))
        queryset = Mock()
        queryset.prefetch_related.return_value = assignments
        return queryset

    def _policy(self, mode, values):
        return SimpleNamespace(
            isactive=True,
            entity_id=1,
            policy_type=DataAccessPolicy.TYPE_FINANCIAL_YEAR,
            scope_mode=mode,
            configuration={"ids": values},
        )

    @patch("rbac.services.RBACDevelopmentAccess.allow_all", return_value=False)
    @patch("rbac.services.EffectivePermissionService.active_assignments_queryset")
    def test_include_and_exclude_modes_apply_to_exact_resource(self, assignments, _allow_all):
        include = self._policy(DataAccessPolicy.MODE_INCLUDE, [22])
        exclude = self._policy(DataAccessPolicy.MODE_EXCLUDE, [99])
        assignments.return_value = self._assignment_queryset([include, exclude])

        self.assertTrue(
            EffectivePermissionService.has_data_scope_access(
                SimpleNamespace(), 1, DataAccessPolicy.TYPE_FINANCIAL_YEAR, 22
            )
        )
        self.assertFalse(
            EffectivePermissionService.has_data_scope_access(
                SimpleNamespace(), 1, DataAccessPolicy.TYPE_FINANCIAL_YEAR, 99
            )
        )

    @patch("rbac.services.RBACDevelopmentAccess.allow_all", return_value=False)
    @patch("rbac.services.EffectivePermissionService.active_assignments_queryset")
    def test_separate_role_without_policy_grants_scope(self, assignments, _allow_all):
        include = self._policy(DataAccessPolicy.MODE_INCLUDE, [22])
        assignments.return_value = self._assignment_queryset([include], [])

        self.assertTrue(
            EffectivePermissionService.has_data_scope_access(
                SimpleNamespace(), 1, DataAccessPolicy.TYPE_FINANCIAL_YEAR, 99
            )
        )

    @patch("rbac.services.RBACDevelopmentAccess.allow_all", return_value=False)
    @patch("rbac.services.EffectivePermissionService.active_assignments_queryset")
    def test_custom_mode_fails_closed(self, assignments, _allow_all):
        custom = self._policy(DataAccessPolicy.MODE_CUSTOM, [22])
        assignments.return_value = self._assignment_queryset([custom])

        self.assertFalse(
            EffectivePermissionService.has_data_scope_access(
                SimpleNamespace(), 1, DataAccessPolicy.TYPE_FINANCIAL_YEAR, 22
            )
        )
