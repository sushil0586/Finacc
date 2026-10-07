from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from django.test import override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from auditlogger.models import AuditLog
from reports.models import ReportFreezeSnapshot
from reports.services.controls.audit_trail import build_controls_audit_activity
from reports.tests_support.compliance_golden_dataset import build_compliance_golden_scope


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class ControlsApiPermissionTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="controls-rbac-user",
            email="controls-rbac@example.com",
            password="pass123",
        )
        self.permission_codes_patch = patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=[
                "reports.financial_hub.controls_phase_one.view",
                "reports.financial_hub.posting_setup.view",
                "reports.financial_hub.year_end_close.view",
            ],
        )
        self.permission_codes_patch.start()
        self.addCleanup(self.permission_codes_patch.stop)
        self.client.force_authenticate(user=self.user)
        golden = build_compliance_golden_scope(user=self.user, entity_name="Controls Entity")
        self.entity = golden.entity
        self.subentity = golden.subentity
        self.entityfin = golden.entityfin
        self.scope_params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
        }

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_phase_one_hub_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-meta"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_phase_one_audit_pack_export_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-audit-pack-export"), {**self.scope_params, "format": "csv"})
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_phase_one_audit_pack_snapshot_export_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(
            reverse("reports_api:controls-phase-one-audit-pack-export"),
            {**self.scope_params, "format": "csv", "snapshot_id": 99},
        )
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_posting_setup_preview_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-posting-setup-preview"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_close_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_year_end_close_meta_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-year-end-close-meta"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_opening_policy_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-opening-policy"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_recurring_journals_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-recurring-journals"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_recurring_journals_run_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.post(reverse("reports_api:controls-phase-one-recurring-journals-run"), self.scope_params, format="json")
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_approval_workflow_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-approval-workflow"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_audit_trail_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-audit-trail"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_audit_activity_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-audit-activity"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_audit_activity_export_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-audit-activity-export"), {**self.scope_params, "format": "csv"})
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_attachment_vault_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-attachment-vault"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_opening_preview_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(reverse("reports_api:controls-phase-one-opening-preview"), self.scope_params)
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_opening_generate_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.post(reverse("reports_api:controls-phase-one-opening-generate"), self.scope_params, format="json")
        self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_views.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_opening_rollback_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.post(reverse("reports_api:controls-phase-one-opening-rollback"), self.scope_params, format="json")
        self.assertEqual(response.status_code, 403)

    def test_view_only_permissions_deny_every_control_mutation(self):
        mutation_requests = (
            ("patch", "reports_api:controls-phase-one-opening-policy", {"entity": self.entity.id, "opening_mode": "hybrid"}),
            ("patch", "reports_api:controls-phase-one-recurring-journals", {"entity": self.entity.id, "run_mode": "auto_draft"}),
            ("post", "reports_api:controls-phase-one-recurring-journals-run", self.scope_params),
            ("patch", "reports_api:controls-phase-one-approval-workflow", {"entity": self.entity.id, "mode": "threshold"}),
            ("patch", "reports_api:controls-phase-one-audit-trail", {"entity": self.entity.id, "retention_days": 730}),
            ("patch", "reports_api:controls-phase-one-attachment-vault", {"entity": self.entity.id, "require_for_posting": True}),
            ("patch", "reports_api:controls-phase-one-close-checklist", {**self.scope_params, "item_key": "opening_policy_confirmed_gate", "status": "done"}),
            ("post", "reports_api:controls-phase-one-audit-pack-snapshots", self.scope_params),
            ("patch", "reports_api:controls-phase-one-audit-pack-review", {"entity": self.entity.id, "snapshot_id": 9999, "status": "reviewed"}),
            ("post", "reports_api:controls-phase-one-opening-lifecycle", {**self.scope_params, "action": "approved"}),
            ("post", "reports_api:controls-phase-one-opening-generate", self.scope_params),
            ("post", "reports_api:controls-phase-one-opening-rollback", self.scope_params),
            ("post", "reports_api:controls-posting-setup-apply", self.scope_params),
            ("post", "reports_api:controls-year-end-close-execute", self.scope_params),
            ("post", "reports_api:controls-year-end-close-rollback", self.scope_params),
        )

        for method, route_name, payload in mutation_requests:
            with self.subTest(route=route_name):
                response = getattr(self.client, method)(reverse(route_name), payload, format="json")
                self.assertEqual(response.status_code, 403)

    @patch("reports.api.controls_close_views.build_year_end_close_rollback")
    def test_year_end_close_execute_permission_does_not_allow_rollback(self, mock_rollback):
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.year_end_close.execute"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-year-end-close-rollback"),
                self.scope_params,
                format="json",
            )

        self.assertEqual(response.status_code, 403)
        mock_rollback.assert_not_called()

    @patch("reports.api.controls_close_views.build_year_end_close_execution")
    def test_year_end_close_rollback_permission_does_not_allow_execute(self, mock_execute):
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.year_end_close.rollback"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-year-end-close-execute"),
                self.scope_params,
                format="json",
            )

        self.assertEqual(response.status_code, 403)
        mock_execute.assert_not_called()

    @patch("reports.api.controls_close_views.record_controls_audit_event")
    @patch("reports.api.controls_close_views.build_year_end_close_rollback")
    @patch("reports.api.controls_close_views.build_year_end_close_execution")
    @patch("reports.api.controls_close_views.build_year_end_close_preview")
    def test_year_end_close_role_profiles_have_expected_capabilities(
        self,
        mock_preview,
        mock_execute,
        mock_rollback,
        mock_audit_event,
    ):
        role_profiles = (
            {
                "name": "viewer",
                "permissions": ["reports.financial_hub.year_end_close.view"],
                "preview": 200,
                "execute": 403,
                "rollback": 403,
            },
            {
                "name": "controller",
                "permissions": ["reports.financial_hub.year_end_close.view", "reports.financial_hub.year_end_close.execute"],
                "preview": 200,
                "execute": 200,
                "rollback": 403,
            },
            {
                "name": "admin",
                "permissions": [
                    "reports.financial_hub.year_end_close.view",
                    "reports.financial_hub.year_end_close.execute",
                    "reports.financial_hub.year_end_close.rollback",
                ],
                "preview": 200,
                "execute": 200,
                "rollback": 200,
            },
        )

        for profile in role_profiles:
            with self.subTest(profile=profile["name"]):
                mock_preview.reset_mock()
                mock_execute.reset_mock()
                mock_rollback.reset_mock()
                mock_audit_event.reset_mock()
                mock_preview.return_value = {"report_code": "year_end_close_preview", "close_state": {"readiness_state": "ready"}}
                mock_execute.return_value = {"report_code": "year_end_close_execution", "status": "success", "run_code": profile["name"]}
                mock_rollback.return_value = {"report_code": "year_end_close_rollback", "status": "success", "rollback": {}}

                with patch(
                    "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
                    return_value=profile["permissions"],
                ):
                    preview_response = self.client.get(reverse("reports_api:controls-year-end-close-meta"), self.scope_params)
                    execute_response = self.client.post(
                        reverse("reports_api:controls-year-end-close-execute"),
                        self.scope_params,
                        format="json",
                    )
                    rollback_response = self.client.post(
                        reverse("reports_api:controls-year-end-close-rollback"),
                        self.scope_params,
                        format="json",
                    )

                self.assertEqual(preview_response.status_code, profile["preview"])
                self.assertEqual(execute_response.status_code, profile["execute"])
                self.assertEqual(rollback_response.status_code, profile["rollback"])
                self.assertEqual(mock_preview.called, profile["preview"] == 200)
                self.assertEqual(mock_execute.called, profile["execute"] == 200)
                self.assertEqual(mock_rollback.called, profile["rollback"] == 200)

    @patch("reports.api.controls_views.build_opening_generation_rollback")
    def test_opening_rollback_requires_dedicated_destructive_permission(self, mock_rollback):
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.generate_opening"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-phase-one-opening-rollback"),
                self.scope_params,
                format="json",
            )

        self.assertEqual(response.status_code, 403)
        mock_rollback.assert_not_called()

    @patch("reports.api.controls_views.update_evidence_pack_review")
    def test_evidence_approval_requires_policy_update_permission(self, mock_review):
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.view"],
        ):
            response = self.client.patch(
                reverse("reports_api:controls-phase-one-audit-pack-review"),
                {"entity": self.entity.id, "snapshot_id": 9001, "status": "approved"},
                format="json",
            )

        self.assertEqual(response.status_code, 403)
        mock_review.assert_not_called()

    def test_phase_ten_runtime_indexes_are_declared(self):
        audit_index_names = {index.name for index in AuditLog._meta.indexes}
        freeze_index_names = {index.name for index in ReportFreezeSnapshot._meta.indexes}

        self.assertIn("ix_auditlog_action_ts", audit_index_names)
        self.assertIn("ix_rpt_frz_ctrl_ver", freeze_index_names)

    @patch("reports.api.controls_views.update_opening_policy")
    def test_opening_policy_patch_uses_action_permission_and_updates_policy(self, mock_update):
        mock_update.return_value = {
            "opening_mode": "hybrid",
            "batch_materialization": "hybrid",
            "opening_posting_date_strategy": "first_day_of_new_year",
            "require_closed_source_year": True,
            "allow_partial_opening": False,
            "carry_forward": {},
            "reset": {},
            "grouped_sections": [],
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.update_policy"],
        ):
            response = self.client.patch(
                reverse("reports_api:controls-phase-one-opening-policy"),
                {"entity": self.entity.id, "opening_mode": "hybrid"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_update.assert_called_once_with(
            entity_id=self.entity.id,
            updates={"opening_mode": "hybrid"},
            created_by=self.user,
        )

    @patch("reports.api.controls_views.update_recurring_journal_policy")
    def test_recurring_journals_patch_uses_action_permission_and_updates_policy(self, mock_update):
        mock_update.return_value = {
            "enabled": True,
            "run_mode": "auto_draft",
            "auto_post_after_approval": False,
            "require_attachment": False,
            "default_frequency": "monthly",
            "templates": [],
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.update_policy"],
        ):
            response = self.client.patch(
                reverse("reports_api:controls-phase-one-recurring-journals"),
                {"entity": self.entity.id, "run_mode": "auto_draft"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_update.assert_called_once_with(
            entity_id=self.entity.id,
            updates={"run_mode": "auto_draft"},
            created_by=self.user,
        )

    @patch("reports.api.controls_views.record_controls_audit_event")
    @patch("reports.api.controls_views.mark_recurring_journal_run")
    def test_recurring_journals_run_uses_action_permission_and_writes_audit_event(self, mock_run, mock_audit_event):
        mock_run.return_value = {
            "entity": self.entity.id,
            "run_date": "2026-10-07",
            "status": "success",
            "templates_reviewed": 1,
            "templates": [{"code": "rent", "name": "Rent Accrual", "status": "marked_reviewed"}],
            "recurring_journal_policy": {"templates": []},
            "summary": [],
            "readiness": {"status": "ready", "status_label": "Scheduled", "summary_cards": [], "actions": []},
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.update_policy"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-phase-one-recurring-journals-run"),
                {**self.scope_params, "run_date": "2026-10-07"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_run.assert_called_once_with(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            run_date=date(2026, 10, 7),
            created_by=self.user,
            retry_failed=False,
        )
        mock_audit_event.assert_called_once()
        self.assertEqual(mock_audit_event.call_args.kwargs["module"], "recurring_journals")
        self.assertEqual(mock_audit_event.call_args.kwargs["action"], "recurring_journal_run_marked")
        self.assertEqual(mock_audit_event.call_args.kwargs["new_data"]["templates_reviewed"], 1)

    @patch("reports.api.controls_views.record_controls_audit_event")
    @patch("reports.api.controls_views.update_close_checklist_item")
    def test_close_checklist_patch_uses_action_permission_and_writes_audit_event(self, mock_update, mock_audit_event):
        mock_update.return_value = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
            "item": {
                "key": "opening_policy_confirmed_gate",
                "label": "Opening policy confirmed",
                "status": "done",
                "mandatory": True,
                "comment": "Reviewed by finance",
            },
            "readiness": {"status": "ready", "status_label": "Ready", "summary_cards": [], "actions": [], "checklist": []},
            "manual_override_applied": True,
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.update_policy"],
        ):
            response = self.client.patch(
                reverse("reports_api:controls-phase-one-close-checklist"),
                {
                    **self.scope_params,
                    "item_key": "opening_policy_confirmed_gate",
                    "status": "done",
                    "comment": "Reviewed by finance",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_update.assert_called_once_with(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            item_key="opening_policy_confirmed_gate",
            status="done",
            comment="Reviewed by finance",
            created_by=self.user,
        )
        mock_audit_event.assert_called_once()
        self.assertEqual(mock_audit_event.call_args.kwargs["module"], "year_end_close")
        self.assertEqual(mock_audit_event.call_args.kwargs["action"], "close_checklist_updated")
        self.assertEqual(mock_audit_event.call_args.kwargs["new_data"]["item_key"], "opening_policy_confirmed_gate")
        self.assertTrue(mock_audit_event.call_args.kwargs["new_data"]["manual_override_applied"])

    @patch("reports.api.controls_views.record_controls_audit_event")
    @patch("reports.api.controls_views.mark_opening_lifecycle")
    def test_opening_lifecycle_ready_writes_audit_event(self, mock_lifecycle, mock_audit_event):
        mock_lifecycle.return_value = {
            "status": "success",
            "message": "Opening lifecycle marked Ready For Review.",
            "report_code": "opening_lifecycle",
            "entity_id": self.entity.id,
            "entityfin_id": self.entityfin.id,
            "subentity_id": self.subentity.id,
            "lifecycle": {"status": "ready_for_review", "status_label": "Ready For Review"},
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.generate_opening"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-phase-one-opening-lifecycle"),
                {**self.scope_params, "action": "ready_for_review"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_lifecycle.assert_called_once_with(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            action="ready_for_review",
            actor=self.user,
        )
        mock_audit_event.assert_called_once()
        self.assertEqual(mock_audit_event.call_args.kwargs["module"], "opening_generation")
        self.assertEqual(mock_audit_event.call_args.kwargs["action"], "opening_ready_for_review")
        self.assertEqual(mock_audit_event.call_args.kwargs["new_data"]["lifecycle"]["status"], "ready_for_review")

    @patch("reports.api.controls_views.record_controls_audit_event")
    @patch("reports.api.controls_views.lock_opening_generation")
    def test_opening_lifecycle_lock_writes_audit_event(self, mock_lock, mock_audit_event):
        mock_lock.return_value = {
            "status": "success",
            "message": "Opening carry-forward locked successfully.",
            "report_code": "opening_lifecycle_lock",
            "entity_id": self.entity.id,
            "entityfin_id": self.entityfin.id,
            "subentity_id": self.subentity.id,
            "lifecycle": {"status": "locked", "status_label": "Locked"},
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.generate_opening"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-phase-one-opening-lifecycle"),
                {**self.scope_params, "action": "lock"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_lock.assert_called_once_with(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            actor=self.user,
        )
        mock_audit_event.assert_called_once()
        self.assertEqual(mock_audit_event.call_args.kwargs["module"], "opening_generation")
        self.assertEqual(mock_audit_event.call_args.kwargs["action"], "opening_lock")
        self.assertEqual(mock_audit_event.call_args.kwargs["new_data"]["lifecycle"]["status"], "locked")

    @patch("reports.api.controls_views.update_approval_workflow_policy")
    def test_approval_workflow_patch_uses_action_permission_and_updates_policy(self, mock_update):
        mock_update.return_value = {
            "enabled": True,
            "mode": "threshold",
            "default_approver_role": "finance_manager",
            "require_comment_on_reject": True,
            "document_types": {"journal": True},
            "thresholds": [],
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.update_policy"],
        ):
            response = self.client.patch(
                reverse("reports_api:controls-phase-one-approval-workflow"),
                {"entity": self.entity.id, "mode": "threshold"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_update.assert_called_once_with(
            entity_id=self.entity.id,
            updates={"mode": "threshold"},
            created_by=self.user,
        )

    @patch("reports.api.controls_views.update_audit_trail_policy")
    def test_audit_trail_patch_uses_action_permission_and_updates_policy(self, mock_update):
        mock_update.return_value = {
            "enabled": True,
            "retention_days": 730,
            "capture_read_actions": False,
            "capture_write_actions": True,
            "export_enabled": True,
            "modules": {"vouchers": True},
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.update_policy"],
        ):
            response = self.client.patch(
                reverse("reports_api:controls-phase-one-audit-trail"),
                {"entity": self.entity.id, "retention_days": 730},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_update.assert_called_once_with(
            entity_id=self.entity.id,
            updates={"retention_days": 730},
            created_by=self.user,
        )

    @patch("reports.api.controls_views.update_attachment_vault_policy")
    def test_attachment_vault_patch_uses_action_permission_and_updates_policy(self, mock_update):
        mock_update.return_value = {
            "enabled": True,
            "require_for_posting": True,
            "allow_delete_after_posting": False,
            "max_file_mb": 20,
            "required_documents": {"statutory": True},
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.controls_phase_one.update_policy"],
        ):
            response = self.client.patch(
                reverse("reports_api:controls-phase-one-attachment-vault"),
                {"entity": self.entity.id, "require_for_posting": True},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_update.assert_called_once_with(
            entity_id=self.entity.id,
            updates={"require_for_posting": True},
            created_by=self.user,
        )

    @patch("reports.api.controls_close_views.record_controls_audit_event")
    @patch("reports.api.controls_close_views.build_year_end_close_execution")
    def test_year_end_close_execute_writes_audit_event(self, mock_execute, mock_audit_event):
        mock_execute.return_value = {
            "report_code": "year_end_close_execution",
            "status": "success",
            "run_code": "YEC-1",
            "snapshot": {"profit_loss": "100.00"},
            "close": {"entries_created": 2},
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.year_end_close.execute"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-year-end-close-execute"),
                self.scope_params,
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_execute.assert_called_once_with(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            executed_by=self.user,
        )
        mock_audit_event.assert_called_once()
        self.assertEqual(mock_audit_event.call_args.kwargs["module"], "year_end_close")
        self.assertEqual(mock_audit_event.call_args.kwargs["action"], "year_end_close_executed")
        self.assertEqual(mock_audit_event.call_args.kwargs["new_data"]["run_code"], "YEC-1")

    @patch("reports.api.controls_close_views.record_controls_audit_event")
    @patch("reports.api.controls_close_views.build_year_end_close_execution")
    def test_year_end_close_execute_preserves_checklist_blocker_payload(self, mock_execute, mock_audit_event):
        mock_execute.side_effect = ValidationError(
            {
                "detail": "Mandatory close checklist blockers must be cleared before year-end close execution.",
                "checklist_blockers": [
                    {
                        "key": "bank_reconciliation_gate",
                        "label": "Bank reconciliation complete",
                        "detail": "Resolve unmatched bank/book lines before close.",
                    }
                ],
            }
        )
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.year_end_close.execute"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-year-end-close-execute"),
                self.scope_params,
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"],
            "Mandatory close checklist blockers must be cleared before year-end close execution.",
        )
        self.assertEqual(response.data["checklist_blockers"][0]["key"], "bank_reconciliation_gate")
        mock_audit_event.assert_not_called()

    @patch("reports.api.controls_close_views.record_controls_audit_event")
    @patch("reports.api.controls_close_views.build_year_end_close_execution")
    def test_year_end_close_execute_duplicate_close_returns_400_without_audit(self, mock_execute, mock_audit_event):
        mock_execute.side_effect = ValidationError({"detail": "This financial year is already closed."})
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.year_end_close.execute"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-year-end-close-execute"),
                self.scope_params,
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "This financial year is already closed.")
        mock_audit_event.assert_not_called()

    @patch("reports.api.controls_close_views.record_controls_audit_event")
    @patch("reports.api.controls_close_views.build_year_end_close_rollback")
    def test_year_end_close_rollback_writes_audit_event(self, mock_rollback, mock_audit_event):
        mock_rollback.return_value = {
            "report_code": "year_end_close_rollback",
            "status": "success",
            "rollback": {"purge_result": {"posting_entries": 2}},
        }
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.year_end_close.rollback"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-year-end-close-rollback"),
                self.scope_params,
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        mock_rollback.assert_called_once_with(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            executed_by=self.user,
        )
        mock_audit_event.assert_called_once()
        self.assertEqual(mock_audit_event.call_args.kwargs["module"], "year_end_close")
        self.assertEqual(mock_audit_event.call_args.kwargs["action"], "year_end_close_rolled_back")
        self.assertEqual(mock_audit_event.call_args.kwargs["new_data"]["rollback"]["purge_result"]["posting_entries"], 2)

    @patch("reports.api.controls_close_views.record_controls_audit_event")
    @patch("reports.api.controls_close_views.build_year_end_close_rollback")
    def test_year_end_close_rollback_requires_close_history_without_audit(self, mock_rollback, mock_audit_event):
        mock_rollback.side_effect = ValidationError({"detail": "No year-end close history was found to roll back."})
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.year_end_close.rollback"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-year-end-close-rollback"),
                self.scope_params,
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "No year-end close history was found to roll back.")
        mock_audit_event.assert_not_called()

    @patch("reports.api.controls_close_views.record_controls_audit_event")
    @patch("reports.api.controls_close_views.build_year_end_close_rollback")
    def test_year_end_close_rollback_denies_existing_opening_without_audit(self, mock_rollback, mock_audit_event):
        mock_rollback.side_effect = ValidationError(
            {"detail": "Opening carry-forward already exists for the next financial year. Roll back opening generation first."}
        )
        with patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.financial_hub.year_end_close.rollback"],
        ):
            response = self.client.post(
                reverse("reports_api:controls-year-end-close-rollback"),
                self.scope_params,
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"],
            "Opening carry-forward already exists for the next financial year. Roll back opening generation first.",
        )
        mock_audit_event.assert_not_called()

    @patch("reports.api.controls_views.build_phase_one_controls_hub")
    def test_phase_one_hub_exposes_compliance_readiness_actions(self, mock_build_hub):
        mock_build_hub.return_value = {
            "report_code": "phase_one_controls_hub",
            "report_name": "Financial Controls Phase 1",
            "summary_cards": [],
            "sections": [],
            "compliance_readiness": {
                "status": "blocked",
                "status_label": "Blocked",
                "summary_cards": [],
                "actions": [
                    {
                        "label": "Open GST Blockers",
                        "route": "/reports/compliance/gst-exception-dashboard",
                        "params": {
                            "entityfinid": self.entityfin.id,
                            "subentity": self.subentity.id,
                            "tab": 1,
                            "focus": "blockers",
                        },
                    },
                    {
                        "label": "Open TCS Pending Collection",
                        "route": "/tcsstatutory",
                        "params": {
                            "entityfinid": self.entityfin.id,
                            "subentity": self.subentity.id,
                            "workspace_status": "COMPUTED_PENDING_COLLECTION",
                        },
                    },
                ],
            },
        }

        response = self.client.get(reverse("reports_api:controls-phase-one-meta"), self.scope_params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("compliance_readiness", payload)
        self.assertIn("actions", payload["compliance_readiness"])
        actions = payload["compliance_readiness"]["actions"]
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["route"], "/reports/compliance/gst-exception-dashboard")
        self.assertEqual(actions[0]["params"]["focus"], "blockers")
        self.assertEqual(actions[1]["route"], "/tcsstatutory")
        self.assertEqual(actions[1]["params"]["workspace_status"], "COMPUTED_PENDING_COLLECTION")

    @patch("reports.api.controls_views.record_controls_audit_event")
    @patch("reports.api.controls_views.build_phase_one_controls_hub")
    def test_phase_one_audit_pack_export_returns_csv(self, mock_build_hub, mock_audit_event):
        mock_build_hub.return_value = {
            "entity_name": "Controls Entity",
            "entityfin_name": "FY 2025-26",
            "subentity_name": "Main Branch",
            "generated_at": "2026-10-07T00:00:00+00:00",
            "audit_pack": {
                "pack_name": "Financial Controls Phase 1 Audit Pack",
                "status_label": "Review",
                "generated_at": "2026-10-07T00:00:00+00:00",
                "evidence_rows": [
                    {
                        "section": "Control Check",
                        "label": "Bank reconciliation readiness",
                        "value": "pass",
                        "status": "pass",
                        "note": "Matched",
                    }
                ],
            },
        }

        response = self.client.get(reverse("reports_api:controls-phase-one-audit-pack-export"), {**self.scope_params, "format": "csv"})

        self.assertEqual(response.status_code, 200)
        mock_audit_event.assert_called_once()
        self.assertEqual(mock_audit_event.call_args.kwargs["action"], "audit_pack_exported")
        self.assertEqual(mock_audit_event.call_args.kwargs["module"], "audit_pack")
        self.assertEqual(mock_audit_event.call_args.kwargs["new_data"]["format"], "csv")
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn('attachment; filename="financial_controls_phase_one_audit_pack.csv"', response["Content-Disposition"])
        content = response.content.decode("utf-8-sig")
        self.assertIn("Financial Controls Phase 1 Audit Pack", content)
        self.assertIn("Bank reconciliation readiness", content)

    @patch("reports.api.controls_views.record_controls_audit_event")
    @patch("reports.api.controls_views.build_phase_one_controls_hub")
    def test_phase_one_audit_pack_export_uses_stored_snapshot_when_version_requested(self, mock_build_hub, mock_audit_event):
        mock_build_hub.return_value = {
            "entity_name": "Live Controls Entity",
            "entityfin_name": "FY Live",
            "audit_pack": {
                "pack_name": "Live Audit Pack",
                "status_label": "Live",
                "evidence_rows": [{"section": "Live", "label": "Live row", "value": "live", "status": "pass"}],
            },
        }
        snapshot = ReportFreezeSnapshot.objects.create(
            report_code="controls_phase_one_audit_pack",
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            version=3,
            frozen_by=self.user,
            payload={
                "snapshot": {
                    "hub": {
                        "entity_name": "Frozen Entity",
                        "entityfin_name": "FY 2025-26",
                        "subentity_name": "Main Branch",
                        "generated_at": "2026-10-07T00:00:00+00:00",
                    },
                    "audit_pack": {
                        "pack_name": "Financial Controls Phase 1 Audit Pack",
                        "status_label": "Review",
                        "generated_at": "2026-10-07T00:00:00+00:00",
                        "summary": {"evidence_rows": 1},
                        "evidence_rows": [
                            {
                                "section": "Frozen Check",
                                "label": "Frozen bank readiness",
                                "value": "pass",
                                "status": "pass",
                                "note": "Stored row",
                            }
                        ],
                    },
                },
                "review": {"status": "approved", "status_label": "Approved"},
            },
        )

        response = self.client.get(
            reverse("reports_api:controls-phase-one-audit-pack-export"),
            {**self.scope_params, "format": "csv", "snapshot_id": snapshot.id},
        )

        self.assertEqual(response.status_code, 200)
        mock_build_hub.assert_not_called()
        self.assertIn('attachment; filename="financial_controls_phase_one_audit_pack_v3.csv"', response["Content-Disposition"])
        content = response.content.decode("utf-8-sig")
        self.assertIn("Frozen bank readiness", content)
        self.assertIn("Evidence Version", content)
        self.assertIn("v3", content)
        self.assertNotIn("Live row", content)
        self.assertEqual(mock_audit_event.call_args.kwargs["new_data"]["snapshot_id"], snapshot.id)
        self.assertEqual(mock_audit_event.call_args.kwargs["new_data"]["version"], 3)

    def test_phase_one_audit_activity_returns_filtered_events(self):
        AuditLog.objects.create(
            user=self.user,
            method="PATCH",
            path=f"/controls/phase-one/audit_trail/?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}",
            action="controls_phase_one.policy_updated",
            new_data={
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "module": "audit_trail",
                "detail": "Policy updated",
            },
        )
        AuditLog.objects.create(
            user=self.user,
            method="GET",
            path=f"/controls/phase-one/audit_pack/?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}",
            action="controls_phase_one.audit_pack_exported",
            new_data={
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "module": "audit_pack",
            },
        )

        response = self.client.get(
            reverse("reports_api:controls-phase-one-audit-activity"),
            {**self.scope_params, "module": "audit_trail", "limit": 10},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["events"][0]["module"], "audit_trail")
        self.assertEqual(payload["events"][0]["actor"]["username"], self.user.username)
        self.assertTrue(payload["filters"]["default_window_applied"])

    def test_year_end_close_audit_activity_returns_execute_and_rollback_events(self):
        AuditLog.objects.create(
            user=self.user,
            method="POST",
            path=f"/controls/phase-one/year_end_close/?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}",
            action="controls_phase_one.year_end_close_executed",
            new_data={
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "module": "year_end_close",
                "status": "success",
                "journal_entry": {"entry_id": 7001, "voucher_no": "YEC-FY2026-27"},
            },
        )
        AuditLog.objects.create(
            user=self.user,
            method="POST",
            path=f"/controls/phase-one/year_end_close/?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}",
            action="controls_phase_one.year_end_close_rolled_back",
            new_data={
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "module": "year_end_close",
                "status": "success",
                "rollback": {"purge_result": {"posting_entries": 2}},
            },
        )

        response = self.client.get(
            reverse("reports_api:controls-phase-one-audit-activity"),
            {**self.scope_params, "module": "year_end_close", "limit": 10},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["total"], 2)
        self.assertEqual(payload["summary"]["modules"][0]["module"], "year_end_close")
        self.assertEqual(payload["summary"]["modules"][0]["count"], 2)
        actions = {event["action"] for event in payload["events"]}
        self.assertEqual(
            actions,
            {
                "controls_phase_one.year_end_close_executed",
                "controls_phase_one.year_end_close_rolled_back",
            },
        )
        for event in payload["events"]:
            self.assertEqual(event["module"], "year_end_close")
            self.assertEqual(event["method"], "POST")
            self.assertEqual(event["actor"]["username"], self.user.username)
            self.assertEqual(event["entity"], self.entity.id)
            self.assertEqual(event["entityfinid"], self.entityfin.id)
            self.assertEqual(event["subentity"], self.subentity.id)
            self.assertEqual(event["new_data"]["module"], "year_end_close")

    @override_settings(CONTROLS_AUDIT_ACTIVITY_DEFAULT_DAYS=30, CONTROLS_AUDIT_ACTIVITY_MAX_DAYS=60)
    def test_phase_one_audit_activity_defaults_to_recent_window(self):
        old_event = AuditLog.objects.create(
            user=self.user,
            method="PATCH",
            path=f"/controls/phase-one/audit_trail/?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}",
            action="controls_phase_one.policy_updated",
            new_data={"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id, "module": "audit_trail"},
        )
        AuditLog.objects.filter(pk=old_event.pk).update(timestamp=timezone.now() - timedelta(days=45))
        AuditLog.objects.create(
            user=self.user,
            method="PATCH",
            path=f"/controls/phase-one/audit_trail/?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}",
            action="controls_phase_one.policy_updated",
            new_data={"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id, "module": "audit_trail"},
        )

        response = self.client.get(
            reverse("reports_api:controls-phase-one-audit-activity"),
            {**self.scope_params, "module": "audit_trail", "limit": 10},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertTrue(payload["filters"]["default_window_applied"])
        self.assertEqual(payload["filters"]["max_days"], 60)

    @override_settings(CONTROLS_AUDIT_ACTIVITY_DEFAULT_DAYS=30, CONTROLS_AUDIT_ACTIVITY_MAX_DAYS=60)
    def test_phase_one_audit_activity_rejects_oversized_date_window(self):
        response = self.client.get(
            reverse("reports_api:controls-phase-one-audit-activity"),
            {
                **self.scope_params,
                "date_from": "2026-01-01",
                "date_to": "2026-03-15",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot exceed 60 days", str(response.json()))

    @override_settings(CONTROLS_AUDIT_ACTIVITY_DEFAULT_DAYS=90, CONTROLS_AUDIT_ACTIVITY_MAX_DAYS=120)
    def test_phase_one_audit_activity_large_volume_stays_bounded(self):
        AuditLog.objects.bulk_create(
            [
                AuditLog(
                    user=self.user,
                    method="PATCH",
                    path=f"/controls/phase-one/audit_trail/?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}",
                    action="controls_phase_one.policy_updated",
                    new_data={
                        "entity": self.entity.id,
                        "entityfinid": self.entityfin.id,
                        "subentity": self.subentity.id,
                        "module": "audit_trail" if index % 2 == 0 else "audit_pack",
                        "detail": f"Policy updated {index}",
                    },
                )
                for index in range(260)
            ]
        )

        with CaptureQueriesContext(connection) as queries:
            service_payload = build_controls_audit_activity(
                entity_id=self.entity.id,
                entityfin_id=self.entityfin.id,
                subentity_id=self.subentity.id,
                limit=200,
            )

        response = self.client.get(
            reverse("reports_api:controls-phase-one-audit-activity"),
            {**self.scope_params, "limit": 200},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(service_payload["summary"]["total"], 260)
        self.assertEqual(len(service_payload["events"]), 200)
        self.assertEqual(payload["summary"]["total"], 260)
        self.assertEqual(len(payload["events"]), 200)
        self.assertLessEqual(len(payload["summary"]["modules"]), 20)
        self.assertLessEqual(len(payload["summary"]["users"]), 20)
        self.assertTrue(payload["filters"]["default_window_applied"])
        self.assertLessEqual(len(queries), 5)

    @patch("reports.api.controls_views.record_controls_audit_event")
    def test_phase_one_audit_activity_export_returns_csv(self, mock_audit_event):
        AuditLog.objects.create(
            user=self.user,
            method="PATCH",
            path=f"/controls/phase-one/audit_trail/?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}",
            action="controls_phase_one.policy_updated",
            new_data={
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "module": "audit_trail",
                "detail": "Policy updated",
            },
        )

        response = self.client.get(
            reverse("reports_api:controls-phase-one-audit-activity-export"),
            {**self.scope_params, "module": "audit_trail", "format": "csv"},
        )

        self.assertEqual(response.status_code, 200)
        mock_audit_event.assert_called_once()
        self.assertEqual(mock_audit_event.call_args.kwargs["action"], "audit_activity_exported")
        self.assertEqual(mock_audit_event.call_args.kwargs["module"], "audit_trail")
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn('attachment; filename="financial_controls_audit_activity.csv"', response["Content-Disposition"])
        content = response.content.decode("utf-8-sig")
        self.assertIn("Financial Controls Audit Activity", content)
        self.assertIn("Policy Updated", content)
