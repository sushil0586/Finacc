from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from reports.services.controls.attachment_vault import (
    build_missing_attachment_evidence,
    enforce_posted_attachment_delete_policy,
    record_attachment_vault_event,
)
from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.models import FinancialSettings
from reports.services.controls.approval_workflow import (
    approval_submission_metadata,
    build_approval_queue,
    build_approval_workflow_readiness,
    enforce_approval_before_approve,
    enforce_approval_before_posting,
    enforce_approval_before_reject,
    record_approval_workflow_event,
)
from reports.services.controls.audit_trail import record_controls_audit_event
from reports.services.controls.close_checklist import update_close_checklist_item
from reports.models import ReportFreezeSnapshot
from reports.services.controls.evidence_pack import compare_evidence_pack_snapshots, create_evidence_pack_snapshot, list_evidence_pack_snapshots, update_evidence_pack_review
from reports.services.controls.opening_generation import _build_opening_history_payload, _build_opening_reconciliation, build_opening_generation, build_opening_generation_rollback, lock_opening_generation, mark_opening_lifecycle
from reports.services.controls.perf import profile_controls_block
from reports.services.controls.recurring_journals import mark_recurring_journal_run, resolve_recurring_journal_policy
from reports.services.controls.year_end_close import build_year_end_close_execution
from vouchers.models import VoucherHeader
from reports.services.controls.phase_one import (
    _build_control_compliance_snapshot,
    _build_bank_reconciliation_snapshot,
    _build_audit_pack,
    _build_control_checks,
    _extend_close_checklist_with_module_gates,
    _build_year_end_close_snapshot,
    _build_gst_compliance_snapshot,
    build_phase_one_controls_hub,
    mandatory_close_checklist_blockers,
)


class PhaseOneControlsManifestTests(SimpleTestCase):
    @override_settings(CONTROLS_PERF_LOGGING=False)
    @patch("reports.services.controls.perf.logger.info")
    def test_controls_perf_profiler_is_inert_when_disabled(self, mock_info):
        with profile_controls_block("controls.phase_one.test", entity=58) as state:
            state["status"] = "ready"

        mock_info.assert_not_called()

    @override_settings(CONTROLS_PERF_LOGGING=True)
    @patch("reports.services.controls.perf.logger.info")
    def test_controls_perf_profiler_logs_timing_scope_and_status(self, mock_info):
        with profile_controls_block("controls.phase_one.test", entity=58) as state:
            state["status"] = "ready"

        mock_info.assert_called_once()
        log_format, event, payload = mock_info.call_args.args
        self.assertEqual(log_format, "%s %s")
        self.assertEqual(event, "controls.phase_one.test")
        self.assertIn("duration_ms=", payload)
        self.assertIn("query_count=", payload)
        self.assertIn("slowest_query_ms=", payload)
        self.assertIn("entity=58", payload)
        self.assertIn("status=ready", payload)

    @override_settings(CONTROLS_PERF_LOGGING=True)
    @patch("reports.services.controls.perf.logger.info")
    def test_controls_perf_profiler_logs_exceptions_without_swallowing_them(self, mock_info):
        with self.assertRaisesMessage(ValueError, "bad controls state"):
            with profile_controls_block("controls.phase_one.test", entity=58):
                raise ValueError("bad controls state")

        mock_info.assert_called_once()
        payload = mock_info.call_args.args[2]
        self.assertIn("status=error", payload)
        self.assertIn("error_type=ValueError", payload)

    @patch("reports.services.controls.phase_one.mandatory_close_checklist_blockers")
    @patch("reports.services.controls.year_end_close.build_year_end_close_preview")
    def test_year_end_close_execution_blocks_mandatory_checklist_blockers(self, mock_preview, mock_blockers):
        mock_preview.return_value = {
            "close_state": {"readiness_state": "ready", "is_year_closed": False},
        }
        mock_blockers.return_value = [
            {
                "key": "bank_reconciliation_gate",
                "label": "Bank reconciliation complete",
                "detail": "Resolve reconciliation differences before close.",
            }
        ]

        with self.assertRaises(ValidationError) as ctx:
            build_year_end_close_execution(entity_id=58, entityfin_id=51, subentity_id=17)

        self.assertIn("Mandatory close checklist blockers", str(ctx.exception.detail["detail"]))
        self.assertEqual(ctx.exception.detail["checklist_blockers"][0]["key"], "bank_reconciliation_gate")

    @patch("reports.services.controls.approval_workflow.resolve_approval_workflow_policy")
    def test_approval_policy_blocks_posting_until_approved_when_configured(self, mock_policy):
        mock_policy.return_value = {
            "_configured": True,
            "enabled": True,
            "mode": "maker_checker",
            "document_types": {"journal": True},
        }

        with self.assertRaisesMessage(ValueError, "Voucher must be approved before posting by approval workflow policy."):
            enforce_approval_before_posting(
                header=SimpleNamespace(entity_id=58),
                document_type="journal",
                workflow_state={"status": "SUBMITTED"},
            )

    @patch("reports.services.controls.approval_workflow.resolve_approval_workflow_policy")
    def test_approval_policy_allows_legacy_posting_when_not_configured(self, mock_policy):
        mock_policy.return_value = {
            "_configured": False,
            "enabled": True,
            "mode": "maker_checker",
            "document_types": {"journal": True},
        }

        enforce_approval_before_posting(
            header=SimpleNamespace(entity_id=58),
            document_type="journal",
            workflow_state={"status": "SUBMITTED"},
        )

    @patch("reports.services.controls.approval_workflow.resolve_approval_workflow_policy")
    def test_approval_policy_requires_reject_comment_when_configured(self, mock_policy):
        mock_policy.return_value = {
            "_configured": True,
            "enabled": True,
            "mode": "maker_checker",
            "require_comment_on_reject": True,
            "document_types": {"journal": True},
        }

        with self.assertRaisesMessage(ValueError, "Rejection comment is required by approval workflow policy."):
            enforce_approval_before_reject(header=SimpleNamespace(entity_id=58), document_type="journal", remarks="")

    @patch("reports.services.controls.approval_workflow.resolve_approval_workflow_policy")
    def test_approval_policy_prevents_same_submitter_approval_when_configured(self, mock_policy):
        mock_policy.return_value = {
            "_configured": True,
            "enabled": True,
            "mode": "maker_checker",
            "document_types": {"journal": True},
        }

        with self.assertRaisesMessage(ValueError, "Approver must be different from submitter by approval workflow policy."):
            enforce_approval_before_approve(
                header=SimpleNamespace(entity_id=58),
                document_type="journal",
                workflow_state={"status": "SUBMITTED", "submitted_by": 7},
                approved_by_id=7,
            )

    @patch("reports.services.controls.approval_workflow.resolve_approval_workflow_policy")
    def test_threshold_submission_metadata_selects_amount_band(self, mock_policy):
        mock_policy.return_value = {
            "_configured": True,
            "enabled": True,
            "mode": "threshold",
            "default_approver_role": "finance_manager",
            "document_types": {"journal": True},
            "thresholds": [
                {"name": "Senior review", "amount_from": "1000.00", "amount_to": None, "approver_role": "controller", "required_approvals": 2}
            ],
        }

        metadata = approval_submission_metadata(entity_id=58, document_type="journal", amount="2500.00")

        self.assertTrue(metadata["approval_required"])
        self.assertEqual(metadata["approval_mode"], "threshold")
        self.assertEqual(metadata["approver_role"], "controller")
        self.assertEqual(metadata["required_approvals"], 2)
        self.assertEqual(metadata["threshold_name"], "Senior review")

    @patch("reports.services.controls.approval_workflow.AuditLog.objects.create")
    def test_approval_workflow_event_records_audit_log_scope(self, mock_create):
        record_approval_workflow_event(
            entity_id=58,
            entityfin_id=51,
            subentity_id=17,
            document_type="journal",
            document_id=99,
            action="approved",
            actor_id=7,
            workflow_state={"status": "APPROVED", "approved_by": 7},
            remarks="Approved",
        )

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["method"], "SYSTEM")
        self.assertEqual(kwargs["action"], "approval_workflow.approved")
        self.assertEqual(kwargs["user_id"], 7)
        self.assertIn("entity=58", kwargs["path"])
        self.assertEqual(kwargs["new_data"]["workflow_state"]["status"], "APPROVED")

    @patch("reports.services.controls.audit_trail.AuditLog.objects.create")
    def test_controls_audit_event_records_phase_one_scope(self, mock_create):
        request = SimpleNamespace(method="PATCH", user=SimpleNamespace(id=7))

        record_controls_audit_event(
            request=request,
            entity_id=58,
            entityfin_id=51,
            subentity_id=17,
            module="opening_policy",
            action="policy_updated",
            old_data={"opening_mode": "single_batch"},
            new_data={"updates": {"opening_mode": "hybrid"}},
        )

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["method"], "PATCH")
        self.assertEqual(kwargs["action"], "controls_phase_one.policy_updated")
        self.assertIn("entity=58", kwargs["path"])
        self.assertEqual(kwargs["old_data"]["opening_mode"], "single_batch")
        self.assertEqual(kwargs["new_data"]["module"], "opening_policy")

    @patch("reports.services.controls.attachment_vault.resolve_attachment_vault_policy")
    def test_attachment_delete_policy_blocks_posted_voucher_delete_when_disabled(self, mock_policy):
        mock_policy.return_value = {
            "enabled": True,
            "allow_delete_after_posting": False,
        }

        with self.assertRaisesMessage(ValueError, "Posted voucher attachments cannot be deleted by attachment vault policy."):
            enforce_posted_attachment_delete_policy(SimpleNamespace(entity_id=58, status=3))

    @patch("reports.services.controls.attachment_vault.resolve_attachment_vault_policy")
    def test_attachment_delete_policy_allows_draft_voucher_delete(self, mock_policy):
        mock_policy.return_value = {
            "enabled": True,
            "allow_delete_after_posting": False,
        }

        enforce_posted_attachment_delete_policy(SimpleNamespace(entity_id=58, status=2))

    @patch("reports.services.controls.attachment_vault._attachment_counts")
    def test_missing_attachment_evidence_lists_required_empty_classes(self, mock_counts):
        mock_counts.return_value = {
            "voucher_files": 0,
            "bank_reconciliation": 0,
            "year_end_close": 0,
            "statutory_tasks": 2,
        }

        rows = build_missing_attachment_evidence(
            {
                "required_documents": {
                    "vouchers": True,
                    "bank_reconciliation": True,
                    "year_end_close": False,
                    "statutory": True,
                }
            },
            entity_id=58,
        )

        self.assertEqual({row["key"] for row in rows}, {"vouchers", "bank_reconciliation"})
        bank_row = next(row for row in rows if row["key"] == "bank_reconciliation")
        self.assertEqual(bank_row["action"]["route"], "/bank-reco/workspace")

    @patch("reports.services.controls.attachment_vault.AuditLog.objects.create")
    def test_attachment_vault_event_records_audit_log_scope(self, mock_create):
        request = SimpleNamespace(method="POST", user=SimpleNamespace(id=7))

        record_attachment_vault_event(
            request=request,
            entity_id=58,
            entityfin_id=51,
            subentity_id=17,
            document_type="journal_voucher",
            document_id=99,
            action="uploaded",
            attachment_ids=[101],
            attachment_names=["invoice.pdf"],
        )

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["method"], "POST")
        self.assertEqual(kwargs["action"], "attachment_vault.uploaded")
        self.assertIn("entity=58", kwargs["path"])
        self.assertEqual(kwargs["new_data"]["attachment_ids"], [101])

    def _recurring_snapshot(self):
        return {
            "status": "ready",
            "status_label": "Scheduled",
            "summary_cards": [{"label": "Templates", "value": 1, "note": "Configured templates", "tone": "neutral"}],
            "actions": [{"label": "Review Recurring Journals", "route": "/reports/controls/phase-one"}],
            "policy": {"templates": []},
            "templates": [],
        }

    def _approval_snapshot(self):
        return {
            "status": "ready",
            "status_label": "Configured",
            "summary_cards": [{"label": "Mode", "value": "maker_checker", "note": "Approval enforcement mode.", "tone": "neutral"}],
            "actions": [{"label": "Review Approval Workflow", "route": "/reports/controls/phase-one"}],
            "policy": {"document_types": {"journal": True}},
        }

    def _audit_snapshot(self):
        return {
            "status": "ready",
            "status_label": "Capturing",
            "summary_cards": [{"label": "Recent events", "value": 3, "note": "Captured in the last 30 days.", "tone": "accent"}],
            "actions": [{"label": "Review Audit Trail", "route": "/reports/controls/phase-one"}],
            "policy": {"modules": {"vouchers": True}},
        }

    def _attachment_snapshot(self):
        return {
            "status": "ready",
            "status_label": "Indexed",
            "summary_cards": [{"label": "Attachments", "value": 2, "note": "Indexed control attachments.", "tone": "accent"}],
            "actions": [{"label": "Review Attachment Vault", "route": "/reports/controls/phase-one"}],
            "policy": {"required_documents": {"statutory": True}},
        }

    @patch("reports.services.controls.phase_one.build_attachment_vault_readiness")
    @patch("reports.services.controls.phase_one.build_audit_trail_readiness")
    @patch("reports.services.controls.phase_one.build_approval_workflow_readiness")
    @patch("reports.services.controls.phase_one.build_recurring_journal_readiness")
    @patch("reports.services.controls.phase_one._build_year_end_close_snapshot")
    @patch("reports.services.controls.phase_one._build_bank_reconciliation_snapshot")
    @patch("reports.services.controls.phase_one._resolve_scope")
    @patch("reports.services.controls.phase_one.resolve_opening_policy")
    def test_phase_one_controls_manifest_groups_new_utilities(self, mock_opening_policy, mock_resolve, mock_bank_snapshot, mock_close_snapshot, mock_recurring, mock_approval, mock_audit, mock_attachment):
        mock_resolve.return_value = {
            "entity_name": "Aditi Gupta",
            "entityfin_name": "FY 2026-27",
            "subentity_name": "Head Office",
        }
        mock_bank_snapshot.return_value = {"status": "review", "status_label": "Review", "summary_cards": [], "actions": []}
        mock_close_snapshot.return_value = {"status": "ready", "status_label": "Ready", "summary_cards": [], "actions": []}
        mock_recurring.return_value = self._recurring_snapshot()
        mock_approval.return_value = self._approval_snapshot()
        mock_audit.return_value = self._audit_snapshot()
        mock_attachment.return_value = self._attachment_snapshot()
        mock_opening_policy.return_value = {
            "opening_mode": "hybrid",
            "batch_materialization": "single_batch",
            "opening_posting_date_strategy": "first_day_of_new_year",
            "require_closed_source_year": True,
            "allow_partial_opening": False,
            "carry_forward": {
                "cash_bank": True,
                "receivables": True,
                "payables": True,
                "loans": True,
                "fixed_assets": True,
                "accumulated_depreciation": True,
                "inventory": True,
                "advances": True,
                "prepayments": True,
                "accruals": True,
                "statutory": True,
                "retained_earnings": True,
            },
            "reset": {
                "trading": True,
                "profit_loss": True,
                "temporary_accounts": True,
            },
            "grouped_sections": ["assets", "liabilities", "stock", "equity"],
        }

        payload = build_phase_one_controls_hub(entity_id=58, entityfin_id=51, subentity_id=17)

        self.assertEqual(payload["report_code"], "phase_one_controls_hub")
        self.assertEqual(payload["report_name"], "Financial Controls Phase 1")
        self.assertEqual(payload["entity_name"], "Aditi Gupta")
        self.assertEqual(payload["entityfin_name"], "FY 2026-27")
        self.assertEqual(payload["subentity_name"], "Head Office")
        self.assertEqual(len(payload["summary_cards"]), 5)
        self.assertEqual(len(payload["sections"]), 3)
        self.assertEqual(
            [section["key"] for section in payload["sections"]],
            ["control_basics", "posting_setup", "close_operations"],
        )
        self.assertEqual(
            [card["code"] for section in payload["sections"] for card in section["cards"]],
            [
                "bank_reconciliation",
                "recurring_journals",
                "voucher_approvals",
                "posting_setup",
                "opening_policy",
                "opening_preview",
                "audit_trail",
                "document_attachments",
                "year_end_close",
            ],
        )
        self.assertIn("compliance_readiness", payload)
        self.assertIn("bank_reconciliation_readiness", payload)
        self.assertIn("year_end_close_readiness", payload)
        self.assertIn("recurring_journals_readiness", payload)
        self.assertIn("approval_workflow_readiness", payload)
        self.assertIn("audit_trail_readiness", payload)
        self.assertIn("attachment_vault_readiness", payload)
        self.assertIn("control_checks", payload)
        self.assertIn("audit_pack", payload)
        for list_key in ("summary_cards", "sections", "opening_policy_summary", "build_principles", "next_steps", "roadmap", "control_checks"):
            self.assertIsInstance(payload[list_key], list)
        for readiness_key in (
            "compliance_readiness",
            "bank_reconciliation_readiness",
            "year_end_close_readiness",
            "recurring_journals_readiness",
            "approval_workflow_readiness",
            "audit_trail_readiness",
            "attachment_vault_readiness",
        ):
            self.assertIn("status", payload[readiness_key])
            self.assertIn("status_label", payload[readiness_key])
            self.assertIsInstance(payload[readiness_key].get("summary_cards"), list)
            self.assertIsInstance(payload[readiness_key].get("actions"), list)
        self.assertIn("summary", payload["audit_pack"])
        self.assertIsInstance(payload["audit_pack"].get("evidence_rows"), list)
        for summary_key in ("evidence_rows", "failed_checks", "review_checks", "passed_checks"):
            self.assertIn(summary_key, payload["audit_pack"]["summary"])
        self.assertIn("summary_cards", payload["compliance_readiness"])
        self.assertEqual(payload["bank_reconciliation_readiness"]["status_label"], "Review")
        self.assertEqual(payload["year_end_close_readiness"]["status_label"], "Ready")
        checklist_keys = {item["key"] for item in payload["year_end_close_readiness"]["checklist"]}
        self.assertTrue(
            {
                "bank_reconciliation_gate",
                "compliance_gate",
                "recurring_journals_gate",
                "approval_workflow_gate",
                "attachment_vault_gate",
                "opening_policy_confirmed_gate",
            }.issubset(checklist_keys)
        )
        self.assertIn("opening_policy", payload)
        self.assertIn("opening_policy_summary", payload)
        self.assertEqual(payload["opening_policy"]["opening_mode"], "hybrid")
        self.assertEqual(payload["opening_policy"]["batch_materialization"], "single_batch")
        self.assertGreaterEqual(len(payload["opening_policy_summary"]), 4)

    @patch("reports.services.controls.phase_one.build_attachment_vault_readiness")
    @patch("reports.services.controls.phase_one.build_audit_trail_readiness")
    @patch("reports.services.controls.phase_one.build_approval_workflow_readiness")
    @patch("reports.services.controls.phase_one.build_recurring_journal_readiness")
    @patch("reports.services.controls.phase_one._build_control_compliance_snapshot")
    @patch("reports.services.controls.phase_one._resolve_scope")
    @patch("reports.services.controls.phase_one.resolve_opening_policy")
    def test_compliance_readiness_actions_contract(self, mock_opening_policy, mock_resolve, mock_gst_snapshot, mock_recurring, mock_approval, mock_audit, mock_attachment):
        mock_resolve.return_value = {
            "entity_name": "Aditi Gupta",
            "entityfin_name": "FY 2026-27",
            "subentity_name": "Head Office",
        }
        mock_recurring.return_value = self._recurring_snapshot()
        mock_approval.return_value = self._approval_snapshot()
        mock_audit.return_value = self._audit_snapshot()
        mock_attachment.return_value = self._attachment_snapshot()
        mock_opening_policy.return_value = {
            "opening_mode": "hybrid",
            "batch_materialization": "single_batch",
            "opening_posting_date_strategy": "first_day_of_new_year",
            "require_closed_source_year": True,
            "allow_partial_opening": False,
            "carry_forward": {},
            "reset": {},
            "grouped_sections": [],
        }
        mock_gst_snapshot.return_value = {
            "status": "blocked",
            "status_label": "Blocked",
            "summary_cards": [],
            "actions": [
                {
                    "label": "Open GST Blockers",
                    "route": "/reports/compliance/gst-exception-dashboard",
                    "params": {"tab": 1, "focus": "blockers"},
                },
                {
                    "label": "Open TCS Pending Collection",
                    "route": "/tcsstatutory",
                    "params": {"workspace_status": "COMPUTED_PENDING_COLLECTION"},
                },
                {
                    "label": "Open Purchase Statutory (TDS Blocked)",
                    "route": "/purchasestatutory",
                    "params": {"readiness_status": "blocked", "tax_type": "IT_TDS"},
                },
            ],
        }

        payload = build_phase_one_controls_hub(entity_id=58, entityfin_id=51, subentity_id=17)

        actions = payload["compliance_readiness"]["actions"]
        self.assertEqual(len(actions), 3)
        self.assertEqual(actions[0]["route"], "/reports/compliance/gst-exception-dashboard")
        self.assertEqual(actions[0]["params"]["focus"], "blockers")
        self.assertEqual(actions[1]["params"]["workspace_status"], "COMPUTED_PENDING_COLLECTION")
        self.assertEqual(actions[2]["params"]["readiness_status"], "blocked")

    @patch("reports.services.controls.phase_one.GstReconciliationRun.objects.filter")
    def test_control_compliance_snapshot_uses_bounded_persisted_run(self, mock_run_filter):
        run = type(
            "Run",
            (),
            {
                "id": 91,
                "status": "IN_REVIEW",
                "return_period": "032027",
                "updated_at": None,
                "items": type(
                    "Items",
                    (),
                    {"aggregate": lambda self, **kwargs: {"mismatch_count": 2, "unmatched_count": 1, "pending_review_count": 4}},
                )(),
            },
        )()
        mock_run_filter.return_value.only.return_value.order_by.return_value.first.return_value = run

        payload = _build_control_compliance_snapshot(entity_id=58, entityfin_id=51, subentity_id=None)

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["summary_cards"][1]["value"], 3)
        self.assertEqual(payload["snapshot_run_id"], 91)

    @patch("reports.services.controls.phase_one._tcs_counts")
    @patch("reports.services.controls.phase_one._tds_counts")
    @patch("reports.services.controls.phase_one.build_gst_exception_dashboard")
    @patch("reports.services.controls.phase_one.build_gstr1_vs_gstr3b_reconciliation")
    @patch("reports.services.controls.phase_one.Gstr3bSummaryService")
    @patch("reports.services.controls.phase_one.Gstr1ReportService")
    @patch("reports.services.controls.phase_one.EntityFinancialYear.objects.filter")
    def test_gst_snapshot_builds_focused_actions(
        self,
        mock_fin_filter,
        mock_gstr1_cls,
        mock_gstr3b_cls,
        mock_reconciliation,
        mock_dashboard,
        mock_tds_counts,
        mock_tcs_counts,
    ):
        mock_fin_filter.return_value.only.return_value.first.return_value = type(
            "Fin",
            (),
            {"finstartyear": "2026-04-01", "finendyear": "2027-03-31"},
        )()

        gstr1_scope = type(
            "Gstr1Scope",
            (),
            {"entityfinid_id": 51, "subentity_id": 17, "from_date": "2026-04-01", "to_date": "2027-03-31"},
        )()
        mock_gstr1 = mock_gstr1_cls.return_value
        mock_gstr1.build_scope.return_value = gstr1_scope
        mock_gstr1.validations.return_value = []
        mock_gstr1.summary.return_value = {"sections": []}

        mock_gstr3b = mock_gstr3b_cls.return_value
        mock_gstr3b.build_scope.return_value = object()
        mock_gstr3b.validations.return_value = []
        mock_gstr3b.build.return_value = {}

        mock_reconciliation.return_value = {"rows": [], "warnings": []}
        mock_dashboard.return_value = {
            "overview": {
                "blocking_exception_count": 2,
                "total_exception_count": 3,
                "reconciliation_advisory_count": 1,
                "max_reconciliation_tax_gap": "152.54",
            }
        }
        mock_tds_counts.return_value = {"blockers": 1, "review_items": 2, "total_rows": 10}
        mock_tcs_counts.return_value = {
            "blockers": 3,
            "review_items": 1,
            "pending_collection": 2,
            "pending_deposit": 1,
            "missing_section": 1,
        }

        payload = _build_gst_compliance_snapshot(entity_id=58, entityfin_id=51, subentity_id=17)

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["status_label"], "Blocked")
        actions = payload["actions"]
        self.assertTrue(any(a["route"] == "/reports/compliance/gst-exception-dashboard" and a["params"].get("focus") == "blockers" for a in actions))
        self.assertTrue(any(a["route"] == "/reports/compliance/gst-exception-dashboard" and a["params"].get("focus") == "reconciliation" for a in actions))
        self.assertTrue(any(a["route"] == "/purchasestatutory" and a["params"].get("readiness_status") == "blocked" for a in actions))
        self.assertTrue(any(a["route"] == "/tcsstatutory" and a["params"].get("workspace_status") == "COMPUTED_PENDING_COLLECTION" for a in actions))
        self.assertTrue(any(a["route"] == "/tcsstatutory" and a["params"].get("workspace_status") == "COLLECTED_PENDING_DEPOSIT" for a in actions))
        self.assertTrue(any(a["route"] == "/tcsstatutory" and a["params"].get("section") == "UNMAPPED" for a in actions))

    @patch("reports.services.controls.phase_one.BankReconciliationRun.objects.filter")
    def test_bank_reconciliation_snapshot_summarizes_latest_run(self, mock_run_filter):
        run = type(
            "Run",
            (),
            {
                "id": 41,
                "run_code": "BRR-41",
                "status": "review",
                "as_of_date": "2026-03-31",
                "unmatched_bank_amount": "50.00",
                "unmatched_book_amount": "20.00",
                "difference_amount": "30.00",
                "matched_line_count": 8,
                "statement_line_count": 10,
                "exception_line_count": 1,
            },
        )()
        mock_run_filter.return_value.filter.return_value.only.return_value.order_by.return_value.first.return_value = run

        payload = _build_bank_reconciliation_snapshot(entity_id=58, entityfin_id=51, subentity_id=17)

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["run_id"], 41)
        self.assertTrue(any(action["route"] == "/bank-reco/reports/brs" for action in payload["actions"]))

    def test_bank_reconciliation_snapshot_handles_missing_scope(self):
        payload = _build_bank_reconciliation_snapshot(entity_id=58, entityfin_id=None, subentity_id=None)

        self.assertEqual(payload["status"], "review")
        self.assertEqual(payload["status_label"], "Scope Required")
        self.assertIsInstance(payload["summary_cards"], list)
        self.assertIsInstance(payload["actions"], list)

    @patch("reports.services.controls.phase_one.BankReconciliationRun.objects.filter")
    def test_bank_reconciliation_snapshot_handles_no_run(self, mock_run_filter):
        mock_run_filter.return_value.only.return_value.order_by.return_value.first.return_value = None

        payload = _build_bank_reconciliation_snapshot(entity_id=58, entityfin_id=51, subentity_id=None)

        self.assertEqual(payload["status"], "review")
        self.assertEqual(payload["status_label"], "Not Run")
        self.assertEqual(payload["summary_cards"][0]["value"], "Not run")
        self.assertIsInstance(payload["actions"], list)

    @patch("reports.services.controls.phase_one.build_year_end_close_preview")
    def test_year_end_close_snapshot_summarizes_preview(self, mock_preview):
        mock_preview.return_value = {
            "close_state": {"readiness_state": "ready", "is_year_closed": False},
            "summary_cards": [
                {"label": "Entries", "value": 5, "note": "Scope posting headers", "tone": "neutral"},
                {"label": "Drafts", "value": 0, "note": "Pending vouchers to review", "tone": "accent"},
            ],
            "source_summary": [
                {"label": "Balance Difference", "value": "0.00", "tone": "accent"},
            ],
            "checks": [],
            "warnings": [],
        }

        payload = _build_year_end_close_snapshot(entity_id=58, entityfin_id=51, subentity_id=17, opening_policy={})

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["status_label"], "Ready")
        self.assertEqual(payload["summary_cards"][0]["label"], "Readiness")
        self.assertEqual(payload["checklist"], [])

    def test_year_end_close_snapshot_handles_missing_scope(self):
        payload = _build_year_end_close_snapshot(entity_id=58, entityfin_id=None, subentity_id=None, opening_policy={})

        self.assertEqual(payload["status"], "review")
        self.assertEqual(payload["status_label"], "Scope Required")
        self.assertIsInstance(payload["summary_cards"], list)
        self.assertEqual(payload["checklist"][0]["key"], "scope_required")
        self.assertTrue(payload["checklist"][0]["mandatory"])
        self.assertIsInstance(payload["actions"], list)

    @patch("reports.services.controls.phase_one.build_year_end_close_preview", side_effect=Exception("boom"))
    def test_year_end_close_snapshot_handles_unavailable_preview(self, _mock_preview):
        payload = _build_year_end_close_snapshot(entity_id=58, entityfin_id=51, subentity_id=None, opening_policy={})

        self.assertEqual(payload["status"], "review")
        self.assertEqual(payload["status_label"], "Unavailable")
        self.assertIsInstance(payload["summary_cards"], list)
        self.assertEqual(payload["checklist"][0]["status"], "blocked")
        self.assertIsInstance(payload["actions"], list)

    def test_control_checks_normalize_readiness_snapshots(self):
        payload = _build_control_checks(
            compliance={
                "status": "blocked",
                "actions": [{"label": "Open GST Blockers", "route": "/reports/compliance/gst-exception-dashboard"}],
            },
            bank_reconciliation={
                "status": "ready",
                "actions": [{"label": "Open Bank Reconciliation", "route": "/bank-reco/dashboard"}],
            },
            year_end_close={
                "status": "review",
                "actions": [{"label": "Open Year-End Close", "route": "/reports/controls/year-end-close"}],
                "checks": [
                    {"key": "drafts", "label": "Draft vouchers", "status": "warning", "detail": "Drafts need review."}
                ],
            },
            recurring_journals={
                "status": "ready",
                "actions": [{"label": "Review Recurring Journals", "route": "/reports/controls/recurring-journals"}],
            },
            approval_workflow={
                "status": "ready",
                "actions": [{"label": "Review Approval Workflow", "route": "/reports/controls/phase-one"}],
            },
            audit_trail={
                "status": "ready",
                "actions": [{"label": "Review Audit Trail", "route": "/reports/controls/phase-one"}],
            },
            attachment_vault={
                "status": "ready",
                "actions": [{"label": "Review Attachment Vault", "route": "/reports/controls/phase-one"}],
            },
            opening_policy={"require_closed_source_year": True},
        )

        self.assertEqual(payload[0]["key"], "bank_reconciliation")
        self.assertEqual(payload[0]["status"], "pass")
        self.assertEqual(payload[2]["key"], "compliance_readiness")
        self.assertEqual(payload[2]["status"], "fail")
        self.assertEqual(payload[2]["action"]["label"], "Open GST Blockers")
        self.assertEqual(payload[3]["key"], "recurring_journals")
        self.assertEqual(payload[3]["status"], "pass")
        self.assertEqual(payload[3]["action"]["params"]["tab"], "policies")
        self.assertEqual(payload[3]["action"]["params"]["policy"], "recurring")
        self.assertTrue(any(item["key"] == "approval_workflow" for item in payload))
        self.assertTrue(any(item["key"] == "audit_trail" for item in payload))
        self.assertTrue(any(item["key"] == "attachment_vault" for item in payload))
        policy_actions = {
            item["key"]: item["action"]["params"].get("policy")
            for item in payload
            if item["key"] in {"approval_workflow", "audit_trail", "attachment_vault"}
        }
        self.assertEqual(policy_actions["approval_workflow"], "approvals")
        self.assertEqual(policy_actions["audit_trail"], "audit")
        self.assertEqual(policy_actions["attachment_vault"], "attachments")
        opening_action = next(item for item in payload if item["key"] == "opening_policy_closed_source")["action"]
        self.assertEqual(opening_action["params"]["tab"], "opening")
        self.assertEqual(opening_action["params"]["opening"], "preview")
        close_detail_action = next(item for item in payload if item["key"] == "year_end_close_drafts")["action"]
        self.assertEqual(close_detail_action["params"]["focus"], "check")
        self.assertEqual(close_detail_action["params"]["check"], "drafts")

    def test_bank_control_check_points_blockers_to_matching_workspace(self):
        payload = _build_control_checks(
            compliance={
                "status": "ready_to_file",
                "actions": [{"label": "Open GST Review", "route": "/reports/compliance/gst-summary"}],
            },
            bank_reconciliation={
                "status": "blocked",
                "actions": [
                    {"label": "Open Bank Reconciliation", "route": "/bank-reco/dashboard"},
                    {"label": "Open Matching Workspace", "route": "/bank-reco/workspace"},
                ],
            },
            year_end_close={
                "status": "ready",
                "actions": [{"label": "Open Year-End Close", "route": "/reports/controls/year-end-close"}],
            },
            recurring_journals={"status": "ready", "actions": []},
            approval_workflow={"status": "ready", "actions": []},
            audit_trail={"status": "ready", "actions": []},
            attachment_vault={"status": "ready", "actions": []},
            opening_policy={"require_closed_source_year": True},
        )

        self.assertEqual(payload[0]["key"], "bank_reconciliation")
        self.assertEqual(payload[0]["status"], "fail")
        self.assertEqual(payload[0]["action"]["route"], "/bank-reco/workspace")

    def test_compliance_control_check_prefers_tds_or_tcs_blocker_actions(self):
        common = {
            "bank_reconciliation": {"status": "ready", "actions": []},
            "year_end_close": {"status": "ready", "actions": []},
            "recurring_journals": {"status": "ready", "actions": []},
            "approval_workflow": {"status": "ready", "actions": []},
            "audit_trail": {"status": "ready", "actions": []},
            "attachment_vault": {"status": "ready", "actions": []},
            "opening_policy": {"require_closed_source_year": True},
        }

        tds_payload = _build_control_checks(
            compliance={
                "status": "blocked",
                "summary_cards": [
                    {"label": "GST Blockers", "value": 0},
                    {"label": "TDS Blockers", "value": 2},
                    {"label": "TCS Blockers", "value": 0},
                ],
                "actions": [
                    {"label": "Open GST Blockers", "route": "/reports/compliance/gst-exception-dashboard"},
                    {"label": "Open Purchase Statutory (TDS Blocked)", "route": "/purchasestatutory", "params": {"readiness_status": "blocked"}},
                ],
            },
            **common,
        )
        self.assertEqual(tds_payload[2]["action"]["route"], "/purchasestatutory")
        self.assertEqual(tds_payload[2]["action"]["params"]["readiness_status"], "blocked")

        tcs_payload = _build_control_checks(
            compliance={
                "status": "blocked",
                "summary_cards": [
                    {"label": "GST Blockers", "value": 0},
                    {"label": "TDS Blockers", "value": 0},
                    {"label": "TCS Blockers", "value": 3},
                ],
                "actions": [
                    {"label": "Open GST Blockers", "route": "/reports/compliance/gst-exception-dashboard"},
                    {"label": "Open TCS Pending Deposit", "route": "/tcsstatutory", "params": {"workspace_status": "COLLECTED_PENDING_DEPOSIT"}},
                ],
            },
            **common,
        )
        self.assertEqual(tcs_payload[2]["action"]["route"], "/tcsstatutory")
        self.assertEqual(tcs_payload[2]["action"]["params"]["workspace_status"], "COLLECTED_PENDING_DEPOSIT")

    def test_close_checklist_module_gates_block_bank_and_statutory_readiness(self):
        payload = _extend_close_checklist_with_module_gates(
            year_end_close={
                "status": "review",
                "checklist": [],
                "actions": [{"label": "Open Year-End Close", "route": "/reports/controls/year-end-close"}],
            },
            compliance={
                "status": "blocked",
                "summary_cards": [
                    {"label": "GST Blockers", "value": 1},
                    {"label": "TDS Blockers", "value": 2},
                    {"label": "TCS Blockers", "value": 3},
                ],
                "actions": [
                    {"label": "Open GST Blockers", "route": "/reports/compliance/gst-exception-dashboard"},
                    {"label": "Open Purchase Statutory (TDS Blocked)", "route": "/purchasestatutory", "params": {"tax_type": "IT_TDS"}},
                    {"label": "Open TCS Pending Deposit", "route": "/tcsstatutory", "params": {"workspace_status": "COLLECTED_PENDING_DEPOSIT"}},
                ],
            },
            bank_reconciliation={
                "status": "blocked",
                "actions": [{"label": "Open Matching Workspace", "route": "/bank-reco/workspace"}],
            },
            recurring_journals={"status": "ready", "actions": []},
            approval_workflow={"status": "ready", "actions": []},
            attachment_vault={"status": "ready", "actions": []},
            opening_policy={"require_closed_source_year": True},
        )

        checklist = {item["key"]: item for item in payload["checklist"]}
        self.assertEqual(checklist["bank_reconciliation_gate"]["status"], "blocked")
        self.assertTrue(checklist["bank_reconciliation_gate"]["mandatory"])
        self.assertEqual(checklist["bank_reconciliation_gate"]["detail"], "Resolve reconciliation differences before close.")
        self.assertEqual(checklist["bank_reconciliation_gate"]["action"]["route"], "/bank-reco/workspace")
        self.assertEqual(checklist["compliance_gate"]["status"], "blocked")
        self.assertTrue(checklist["compliance_gate"]["mandatory"])
        self.assertEqual(checklist["compliance_gate"]["detail"], "Resolve statutory blockers before close.")
        self.assertEqual(checklist["compliance_gate"]["action"]["route"], "/reports/compliance/gst-exception-dashboard")

    @patch("reports.services.controls.phase_one.build_phase_one_controls_hub")
    def test_mandatory_close_checklist_blockers_extracts_bank_and_statutory_gates(self, mock_hub):
        mock_hub.return_value = {
            "year_end_close_readiness": {
                "checklist": [
                    {
                        "key": "bank_reconciliation_gate",
                        "label": "Bank reconciliation complete",
                        "status": "blocked",
                        "mandatory": True,
                        "detail": "Resolve reconciliation differences before close.",
                    },
                    {
                        "key": "compliance_gate",
                        "label": "Statutory compliance reviewed",
                        "status": "blocked",
                        "mandatory": True,
                        "detail": "Resolve statutory blockers before close.",
                    },
                    {
                        "key": "attachment_vault_gate",
                        "label": "Required evidence attached",
                        "status": "blocked",
                        "mandatory": False,
                        "detail": "Optional evidence review.",
                    },
                    {
                        "key": "approval_workflow_gate",
                        "label": "Approvals cleared",
                        "status": "review",
                        "mandatory": True,
                        "detail": "Review pending approvals.",
                    },
                ]
            }
        }

        blockers = mandatory_close_checklist_blockers(entity_id=58, entityfin_id=51, subentity_id=17)

        self.assertEqual([item["key"] for item in blockers], ["bank_reconciliation_gate", "compliance_gate"])
        mock_hub.assert_called_once_with(entity_id=58, entityfin_id=51, subentity_id=17)

    def test_audit_pack_builds_evidence_rows_from_snapshots(self):
        pack = _build_audit_pack(
            scope={"entity_name": "Aditi Gupta", "entityfin_name": "FY 2026-27", "subentity_name": "Head Office"},
            generated_at="2026-10-07T00:00:00+00:00",
            compliance={"status": "ready_to_file", "status_label": "Ready to File", "summary_cards": []},
            bank_reconciliation={"status": "ready", "run_code": "BRR-1", "summary_cards": []},
            year_end_close={"status": "blocked", "status_label": "Blocked", "summary_cards": []},
            recurring_journals={"status": "ready", "status_label": "Scheduled", "summary_cards": []},
            approval_workflow={"status": "ready", "status_label": "Configured", "summary_cards": []},
            audit_trail={"status": "ready", "status_label": "Capturing", "summary_cards": []},
            attachment_vault={"status": "ready", "status_label": "Indexed", "summary_cards": []},
            opening_policy={"opening_mode": "hybrid", "require_closed_source_year": True},
            control_checks=[
                {"label": "Year-end close readiness", "status": "fail", "detail": "Resolve blockers."}
            ],
        )

        self.assertEqual(pack["status"], "blocked")
        self.assertEqual(pack["summary"]["failed_checks"], 1)
        self.assertTrue(any(row["section"] == "Recurring Journals" for row in pack["evidence_rows"]))
        self.assertTrue(any(row["section"] == "Approval Workflow" for row in pack["evidence_rows"]))
        self.assertTrue(any(row["section"] == "Audit Trail" for row in pack["evidence_rows"]))
        self.assertTrue(any(row["section"] == "Attachment Vault" for row in pack["evidence_rows"]))
        self.assertTrue(any(row["section"] == "Control Check" for row in pack["evidence_rows"]))

    def test_audit_pack_includes_executed_year_end_close_history_and_journal(self):
        pack = _build_audit_pack(
            scope={"entity_name": "Aditi Gupta", "entityfin_name": "FY 2026-27", "subentity_name": "Head Office"},
            generated_at="2026-10-07T00:00:00+00:00",
            compliance={"status": "ready_to_file", "status_label": "Ready to File", "summary_cards": []},
            bank_reconciliation={"status": "ready", "run_code": "BRR-1", "summary_cards": []},
            year_end_close={
                "status": "blocked",
                "status_label": "Closed",
                "summary_cards": [],
                "close_history": {
                    "status": "closed",
                    "closed_at": "2026-04-14T10:00:00+00:00",
                    "closed_on": "2026-03-31",
                    "closed_by": {"username": "finance"},
                    "summary": {
                        "income_total": "125000.00",
                        "expense_total": "100000.00",
                        "net_profit": "25000.00",
                    },
                    "journal_entry": {
                        "entry_id": 7001,
                        "voucher_no": "YEC-FY2026-27",
                        "line_count": 3,
                    },
                },
            },
            recurring_journals={"status": "ready", "status_label": "Scheduled", "summary_cards": []},
            approval_workflow={"status": "ready", "status_label": "Configured", "summary_cards": []},
            audit_trail={"status": "ready", "status_label": "Capturing", "summary_cards": []},
            attachment_vault={"status": "ready", "status_label": "Indexed", "summary_cards": []},
            opening_policy={"opening_mode": "hybrid", "require_closed_source_year": True},
            control_checks=[],
        )

        evidence = {(row["section"], row["label"]): row for row in pack["evidence_rows"]}
        self.assertEqual(evidence[("Year-End Close", "Executed close")]["value"], "2026-03-31")
        self.assertEqual(evidence[("Year-End Close", "Executed close")]["note"], "Closed by: finance")
        self.assertEqual(evidence[("Year-End Close", "Close net profit")]["value"], "25000.00")
        self.assertIn("Income: 125000.00", evidence[("Year-End Close", "Close net profit")]["note"])
        self.assertEqual(evidence[("Year-End Close", "Close journal")]["value"], "YEC-FY2026-27")
        self.assertEqual(evidence[("Year-End Close", "Close journal")]["note"], "Entry: 7001 | Lines: 3")

    def test_audit_pack_includes_missing_attachment_evidence_rows(self):
        pack = _build_audit_pack(
            scope={"entity_name": "Aditi Gupta", "entityfin_name": "FY 2026-27", "subentity_name": "Head Office"},
            generated_at="2026-10-07T00:00:00+00:00",
            compliance={"status": "ready_to_file", "status_label": "Ready to File", "summary_cards": []},
            bank_reconciliation={"status": "ready", "run_code": "BRR-1", "summary_cards": []},
            year_end_close={"status": "ready", "status_label": "Ready", "summary_cards": []},
            recurring_journals={"status": "ready", "status_label": "Scheduled", "summary_cards": []},
            approval_workflow={"status": "ready", "status_label": "Configured", "summary_cards": []},
            audit_trail={"status": "ready", "status_label": "Capturing", "summary_cards": []},
            attachment_vault={
                "status": "blocked",
                "status_label": "Evidence Missing",
                "summary_cards": [],
                "missing_evidence": [
                    {"key": "vouchers", "label": "Voucher evidence", "detail": "Upload voucher evidence."}
                ],
            },
            opening_policy={"opening_mode": "hybrid", "require_closed_source_year": True},
            control_checks=[],
        )

        self.assertTrue(any(row["section"] == "Missing Evidence" and row["label"] == "Voucher evidence" for row in pack["evidence_rows"]))


class EvidencePackSnapshotTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="evidence-reviewer", email="evidence@example.com")
        self.entity = Entity.objects.create(entityname="Evidence Controls", createdby=self.user)
        self.entityfin = EntityFinancialYear.objects.create(entity=self.entity, desc="FY 2026-27", year_code="2026-27", createdby=self.user)
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main")

    def _hub(self, status="review"):
        return {
            "entity_name": "Evidence Controls",
            "entityfin_name": "FY 2026-27",
            "subentity_name": "Main",
            "generated_at": "2026-10-07T00:00:00+00:00",
            "audit_pack": {
                "pack_code": "financial-controls-phase-one-audit-pack",
                "pack_name": "Financial Controls Phase 1 Audit Pack",
                "status": status,
                "status_label": status.title(),
                "summary": {"evidence_rows": 1, "failed_checks": 0, "review_checks": 1, "passed_checks": 0},
                "evidence_rows": [{"section": "Control Check", "label": "Bank", "status": "warning"}],
            },
        }

    @patch("reports.services.controls.evidence_pack.build_phase_one_controls_hub")
    def test_evidence_pack_snapshot_versions_and_preserves_payload(self, mock_hub):
        mock_hub.return_value = self._hub()

        first = create_evidence_pack_snapshot(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            generated_by=self.user,
        )
        second = create_evidence_pack_snapshot(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            generated_by=self.user,
        )

        self.assertEqual(first["version"], 1)
        self.assertEqual(second["version"], 2)
        self.assertEqual(second["status"], "prepared")
        self.assertEqual(second["payload"]["audit_pack"]["summary"]["evidence_rows"], 1)

    @patch("reports.services.controls.evidence_pack.build_phase_one_controls_hub")
    def test_evidence_pack_review_updates_status_without_replacing_snapshot(self, mock_hub):
        mock_hub.return_value = self._hub(status="ready")
        created = create_evidence_pack_snapshot(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            generated_by=self.user,
        )

        reviewed = update_evidence_pack_review(
            snapshot_id=created["id"],
            entity_id=self.entity.id,
            status="approved",
            comment="Ready for auditor",
            actor=self.user,
        )
        history = list_evidence_pack_snapshots(entity_id=self.entity.id, entityfin_id=self.entityfin.id, subentity_id=self.subentity.id)

        self.assertEqual(reviewed["status"], "approved")
        self.assertEqual(reviewed["previous_status"], "prepared")
        self.assertEqual(reviewed["review"]["comment"], "Ready for auditor")
        self.assertEqual(reviewed["payload"]["audit_pack"]["status"], "ready")
        self.assertEqual(history["count"], 1)
        self.assertEqual(ReportFreezeSnapshot.objects.get(pk=created["id"]).version, 1)

    def test_evidence_pack_snapshot_compare_marks_added_removed_and_changed_rows(self):
        previous = ReportFreezeSnapshot.objects.create(
            report_code="controls_phase_one_audit_pack",
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            version=1,
            payload={
                "snapshot": {
                    "audit_pack": {
                        "summary": {"failed_checks": 1, "review_checks": 1, "passed_checks": 0},
                        "evidence_rows": [
                            {"section": "Bank", "label": "Reconciliation", "value": "blocked", "status": "fail", "note": "Old blocker"},
                            {"section": "Opening", "label": "Policy", "value": "hybrid", "status": "pass", "note": "Removed later"},
                        ],
                    }
                }
            },
        )
        latest = ReportFreezeSnapshot.objects.create(
            report_code="controls_phase_one_audit_pack",
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            version=2,
            payload={
                "snapshot": {
                    "audit_pack": {
                        "summary": {"failed_checks": 0, "review_checks": 1, "passed_checks": 1},
                        "evidence_rows": [
                            {"section": "Bank", "label": "Reconciliation", "value": "ready", "status": "pass", "note": "Cleared"},
                            {"section": "Audit", "label": "Trail", "value": "enabled", "status": "pass", "note": "New row"},
                        ],
                    }
                }
            },
        )

        comparison = compare_evidence_pack_snapshots(latest, previous)

        self.assertEqual(comparison["from_version"], 1)
        self.assertEqual(comparison["to_version"], 2)
        self.assertEqual(comparison["summary"]["added"], 1)
        self.assertEqual(comparison["summary"]["removed"], 1)
        self.assertEqual(comparison["summary"]["changed"], 1)
        self.assertEqual(comparison["summary"]["failed_delta"], -1)
        self.assertEqual(comparison["summary"]["passed_delta"], 1)
        self.assertEqual(comparison["changed"][0]["label"], "Reconciliation")

    def test_evidence_pack_history_includes_latest_comparison(self):
        for version, label in [(1, "Previous"), (2, "Latest")]:
            ReportFreezeSnapshot.objects.create(
                report_code="controls_phase_one_audit_pack",
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.subentity,
                version=version,
                payload={"snapshot": {"audit_pack": {"summary": {"evidence_rows": 1}, "evidence_rows": [{"section": "Control", "label": label, "status": "pass"}]}}},
            )

        history = list_evidence_pack_snapshots(entity_id=self.entity.id, entityfin_id=self.entityfin.id, subentity_id=self.subentity.id)

        self.assertEqual(history["count"], 2)
        self.assertEqual(history["latest_comparison"]["from_version"], 1)
        self.assertEqual(history["latest_comparison"]["to_version"], 2)
        self.assertEqual(history["latest_comparison"]["summary"]["added"], 1)


class CloseChecklistUpdateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="close-checklist-reviewer",
            email="close-checklist@example.com",
            password="pass@12345",
        )
        self.entity = Entity.objects.create(entityname="Close Checklist Entity", createdby=self.user)
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Head Office")
        FinancialSettings.objects.create(entity=self.entity, reporting_policy={}, createdby=self.user)

    def _hub(self, *, status="review"):
        return {
            "year_end_close_readiness": {
                "status": "review",
                "status_label": "Review",
                "summary_cards": [],
                "actions": [],
                "checklist": [
                    {
                        "key": "opening_policy_confirmed_gate",
                        "label": "Opening policy confirmed",
                        "status": status,
                        "mandatory": True,
                        "detail": "Finance should confirm opening policy.",
                    }
                ],
            }
        }

    @patch("reports.services.controls.close_checklist.build_phase_one_controls_hub")
    def test_update_close_checklist_item_persists_comment_and_done_status(self, mock_hub):
        mock_hub.side_effect = [
            self._hub(status="review"),
            self._hub(status="done"),
        ]

        result = update_close_checklist_item(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            item_key="opening_policy_confirmed_gate",
            status="done",
            comment="Reviewed by finance",
            created_by=self.user,
        )

        settings = FinancialSettings.objects.get(entity=self.entity)
        scope_key = f"fy:{self.entityfin.id}|sub:{self.subentity.id}"
        stored = settings.reporting_policy["close_checklist"]["items"][scope_key]["opening_policy_confirmed_gate"]
        self.assertEqual(stored["status"], "done")
        self.assertEqual(stored["comment"], "Reviewed by finance")
        self.assertEqual(stored["updated_by"], self.user.id)
        self.assertTrue(result["manual_override_applied"])

    @patch("reports.services.controls.close_checklist.build_phase_one_controls_hub")
    def test_update_close_checklist_item_cannot_clear_blocked_gate(self, mock_hub):
        mock_hub.side_effect = [
            self._hub(status="blocked"),
            self._hub(status="blocked"),
        ]

        result = update_close_checklist_item(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            item_key="opening_policy_confirmed_gate",
            status="done",
            comment="Noted; waiting on source control",
            created_by=self.user,
        )

        settings = FinancialSettings.objects.get(entity=self.entity)
        scope_key = f"fy:{self.entityfin.id}|sub:{self.subentity.id}"
        stored = settings.reporting_policy["close_checklist"]["items"][scope_key]["opening_policy_confirmed_gate"]
        self.assertEqual(stored["status"], "review")
        self.assertEqual(stored["comment"], "Noted; waiting on source control")
        self.assertFalse(result["manual_override_applied"])


class OpeningLifecycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="opening-lifecycle",
            email="opening-lifecycle@example.com",
            password="pass@12345",
        )
        self.entity = Entity.objects.create(entityname="Opening Lifecycle Entity", createdby=self.user)
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            is_year_closed=True,
            createdby=self.user,
        )

    def _snapshot(self):
        return {"financial_year": EntityFinancialYear.objects.get(pk=self.entityfin.pk)}

    def test_opening_approval_requires_ready_for_review(self):
        with patch("reports.services.controls.opening_generation._compute_snapshot", return_value=self._snapshot()):
            with self.assertRaises(ValidationError) as ctx:
                mark_opening_lifecycle(
                    entity_id=self.entity.id,
                    entityfin_id=self.entityfin.id,
                    subentity_id=None,
                    action="approved",
                    actor=self.user,
                )

        self.assertIn("ready for review", str(ctx.exception.detail["detail"]))

    def test_opening_ready_then_approved_persists_lifecycle(self):
        with patch("reports.services.controls.opening_generation._compute_snapshot", return_value=self._snapshot()):
            ready = mark_opening_lifecycle(
                entity_id=self.entity.id,
                entityfin_id=self.entityfin.id,
                subentity_id=None,
                action="ready_for_review",
                actor=self.user,
            )
            approved = mark_opening_lifecycle(
                entity_id=self.entity.id,
                entityfin_id=self.entityfin.id,
                subentity_id=None,
                action="approved",
                actor=self.user,
            )

        self.entityfin.refresh_from_db()
        record = self.entityfin.metadata["opening_lifecycle"]["sub:all"]
        self.assertEqual(ready["lifecycle"]["status"], "ready_for_review")
        self.assertEqual(approved["lifecycle"]["status"], "approved")
        self.assertEqual(record["status"], "approved")
        self.assertEqual(record["approved_by"]["id"], self.user.id)

    @patch("reports.services.controls.opening_generation.build_opening_preview")
    @patch("reports.services.controls.opening_generation._compute_snapshot")
    def test_opening_generation_requires_approved_lifecycle(self, mock_snapshot, mock_preview):
        mock_preview.return_value = {
            "actions": {"can_generate": True},
            "opening_history": None,
            "source_year": {"is_closed": True},
            "opening_policy": {"require_closed_source_year": True},
        }
        mock_snapshot.return_value = self._snapshot()

        with self.assertRaises(ValidationError) as ctx:
            build_opening_generation(
                entity_id=self.entity.id,
                entityfin_id=self.entityfin.id,
                subentity_id=None,
                executed_by=self.user,
            )

        self.assertIn("approved opening preview lifecycle", str(ctx.exception.detail["detail"]))

    @patch("reports.services.controls.opening_generation.build_opening_preview")
    def test_opening_lock_requires_generated_history(self, mock_preview):
        mock_preview.return_value = {"opening_history": None}

        with self.assertRaises(ValidationError) as ctx:
            lock_opening_generation(
                entity_id=self.entity.id,
                entityfin_id=self.entityfin.id,
                subentity_id=None,
                actor=self.user,
            )

        self.assertIn("must be generated", str(ctx.exception.detail["detail"]))

    @patch("reports.services.controls.opening_generation._compute_snapshot")
    @patch("reports.services.controls.opening_generation.build_opening_preview")
    def test_locked_opening_blocks_rollback(self, mock_preview, mock_snapshot):
        destination = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2027-28",
            finstartyear=timezone.make_aware(datetime(2027, 4, 1)),
            finendyear=timezone.make_aware(datetime(2028, 3, 31)),
            metadata={
                "opening_carry_forward": {
                    "status": "locked",
                    "lifecycle": {"status": "locked", "status_label": "Locked"},
                    "destination_year": {"id": None},
                    "active_year_transition": {"before_generation": [self.entityfin.id]},
                    "batch": {},
                }
            },
            createdby=self.user,
        )
        destination.metadata["opening_carry_forward"]["destination_year"]["id"] = destination.id
        destination.save(update_fields=["metadata"])
        mock_preview.return_value = {
            "opening_history": {"destination_year": {"id": destination.id}},
            "destination_year": {"id": destination.id},
        }
        mock_snapshot.return_value = self._snapshot()

        with self.assertRaises(ValidationError) as ctx:
            build_opening_generation_rollback(
                entity_id=self.entity.id,
                entityfin_id=self.entityfin.id,
                subentity_id=None,
                executed_by=self.user,
            )

        self.assertIn("Locked opening", str(ctx.exception.detail["detail"]))

    def test_opening_history_payload_preserves_reconciliation_summary(self):
        destination = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2027-28",
            finstartyear=timezone.make_aware(datetime(2027, 4, 1)),
            finendyear=timezone.make_aware(datetime(2028, 3, 31)),
            createdby=self.user,
        )
        entry = SimpleNamespace(
            id=7001,
            subentity_id=None,
            posting_batch=SimpleNamespace(
                id=9001,
                txn_type="OPENING_BALANCE",
                txn_id=destination.id,
                voucher_no="OB-2027",
            ),
        )

        history = _build_opening_history_payload(
            entity_id=self.entity.id,
            source_fy=self.entityfin,
            destination_fy=destination,
            entry=entry,
            posting_batch=entry.posting_batch,
            line_meta=[
                {"section": "assets", "label": "Cash", "source": "asset_row", "amount": "100.00", "drcr": "debit"},
                {"section": "equity", "label": "Capital", "source": "liability_row", "amount": "100.00", "drcr": "credit"},
            ],
            summary={
                "entries": 2,
                "sections": {"assets": 1, "liabilities": 0, "inventory": 0, "equity": 1},
                "reconciliation": {
                    "status": "balanced",
                    "source_total": "100.00",
                    "opening_debits": "100.00",
                    "opening_credits": "100.00",
                    "opening_difference": "0.00",
                    "source_difference": "0.00",
                    "line_count": 2,
                },
            },
            opening_policy={},
            executed_by=self.user,
            destination_year_created=False,
            active_year_ids_before_generation=[self.entityfin.id],
            active_year_id_after_generation=destination.id,
        )

        self.assertEqual(history["summary"]["reconciliation"]["status"], "balanced")
        self.assertEqual(history["summary"]["reconciliation"]["opening_difference"], "0.00")

    def test_opening_reconciliation_marks_balanced_totals(self):
        reconciliation = _build_opening_reconciliation(
            source_assets=Decimal("100.00"),
            source_liabilities=Decimal("0.00"),
            source_inventory=Decimal("0.00"),
            source_net_profit=Decimal("0.00"),
            opening_debits=Decimal("100.00"),
            opening_credits=Decimal("100.00"),
            line_count=2,
        )

        self.assertEqual(reconciliation["status"], "balanced")
        self.assertEqual(reconciliation["opening_difference"], "0.00")
        self.assertEqual(reconciliation["source_difference"], "0.00")

    def test_opening_reconciliation_marks_difference_totals(self):
        reconciliation = _build_opening_reconciliation(
            source_assets=Decimal("120.00"),
            source_liabilities=Decimal("0.00"),
            source_inventory=Decimal("0.00"),
            source_net_profit=Decimal("0.00"),
            opening_debits=Decimal("100.00"),
            opening_credits=Decimal("90.00"),
            line_count=2,
        )

        self.assertEqual(reconciliation["status"], "difference")
        self.assertEqual(reconciliation["opening_difference"], "10.00")
        self.assertEqual(reconciliation["source_difference"], "20.00")

    @patch("reports.services.controls.opening_generation.PostingService")
    @patch("reports.services.controls.opening_generation._build_opening_lines")
    @patch("reports.services.controls.opening_generation._compute_snapshot")
    @patch("reports.services.controls.opening_generation.build_opening_preview")
    def test_opening_lifecycle_flow_generates_locks_and_blocks_rollback(
        self,
        mock_preview,
        mock_snapshot,
        mock_lines,
        mock_posting_service,
    ):
        with patch("reports.services.controls.opening_generation._compute_snapshot", return_value=self._snapshot()):
            mark_opening_lifecycle(
                entity_id=self.entity.id,
                entityfin_id=self.entityfin.id,
                subentity_id=None,
                action="ready_for_review",
                actor=self.user,
            )
            mark_opening_lifecycle(
                entity_id=self.entity.id,
                entityfin_id=self.entityfin.id,
                subentity_id=None,
                action="approved",
                actor=self.user,
            )

        mock_preview.return_value = {
            "actions": {"can_generate": True},
            "opening_history": None,
            "source_year": {"is_closed": True},
            "opening_policy": {"require_closed_source_year": True},
            "destination_year": {"id": None},
        }
        mock_snapshot.return_value = self._snapshot()
        mock_lines.return_value = (
            [SimpleNamespace(amount=100, drcr=True)],
            [{"section": "assets", "label": "Cash", "source": "asset_row", "amount": "100.00", "drcr": "debit"}],
            {
                "sections": {"assets": 1, "liabilities": 0, "inventory": 0, "equity": 0},
                "diagnostics": {},
                "net_profit": 0,
                "reconciliation": {
                    "status": "balanced",
                    "opening_debits": "100.00",
                    "opening_credits": "100.00",
                    "opening_difference": "0.00",
                    "source_difference": "0.00",
                },
            },
        )
        entry = SimpleNamespace(
            id=8801,
            subentity_id=None,
            posting_batch=SimpleNamespace(
                id=9901,
                txn_type="OPENING_BALANCE",
                txn_id=None,
                voucher_no="OB-TEST",
            ),
        )
        mock_posting_service.return_value.post.return_value = entry

        generated = build_opening_generation(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=None,
            executed_by=self.user,
        )

        destination_id = generated["destination_year"]["id"]
        generated["opening_history"]["destination_year"]["id"] = destination_id
        with patch(
            "reports.services.controls.opening_generation.build_opening_preview",
            return_value={"opening_history": generated["opening_history"]},
        ):
            locked = lock_opening_generation(
                entity_id=self.entity.id,
                entityfin_id=self.entityfin.id,
                subentity_id=None,
                actor=self.user,
            )

        with patch(
            "reports.services.controls.opening_generation.build_opening_preview",
            return_value={
                "opening_history": {"destination_year": {"id": destination_id}},
                "destination_year": {"id": destination_id},
            },
        ), patch("reports.services.controls.opening_generation._compute_snapshot", return_value=self._snapshot()):
            with self.assertRaises(ValidationError) as ctx:
                build_opening_generation_rollback(
                    entity_id=self.entity.id,
                    entityfin_id=self.entityfin.id,
                    subentity_id=None,
                    executed_by=self.user,
                )

        self.assertEqual(generated["opening_history"]["lifecycle"]["status"], "generated")
        self.assertEqual(locked["lifecycle"]["status"], "locked")
        self.assertIn("Locked opening", str(ctx.exception.detail["detail"]))

    @patch("reports.services.controls.opening_generation.purge_posting_locator")
    @patch("reports.services.controls.opening_generation.PostingService")
    @patch("reports.services.controls.opening_generation._build_opening_lines")
    @patch("reports.services.controls.opening_generation._compute_snapshot")
    @patch("reports.services.controls.opening_generation.build_opening_preview")
    def test_opening_can_generate_rollback_and_regenerate_for_uat(
        self,
        mock_preview,
        mock_snapshot,
        mock_lines,
        mock_posting_service,
        mock_purge,
    ):
        with patch("reports.services.controls.opening_generation._compute_snapshot", return_value=self._snapshot()):
            mark_opening_lifecycle(
                entity_id=self.entity.id,
                entityfin_id=self.entityfin.id,
                subentity_id=None,
                action="ready_for_review",
                actor=self.user,
            )
            mark_opening_lifecycle(
                entity_id=self.entity.id,
                entityfin_id=self.entityfin.id,
                subentity_id=None,
                action="approved",
                actor=self.user,
            )

        mock_snapshot.return_value = self._snapshot()
        mock_lines.return_value = (
            [SimpleNamespace(amount=100, drcr=True), SimpleNamespace(amount=100, drcr=False)],
            [
                {"section": "assets", "label": "Cash", "source": "asset_row", "amount": "100.00", "drcr": "debit"},
                {"section": "equity", "label": "Capital", "source": "retained_earnings", "amount": "100.00", "drcr": "credit"},
            ],
            {
                "sections": {"assets": 1, "liabilities": 0, "inventory": 0, "equity": 1},
                "diagnostics": {},
                "net_profit": 0,
                "constitution": {},
                "reconciliation": {
                    "status": "balanced",
                    "source_total": "100.00",
                    "opening_debits": "100.00",
                    "opening_credits": "100.00",
                    "opening_difference": "0.00",
                    "source_difference": "0.00",
                    "line_count": 2,
                },
            },
        )
        entries = [
            SimpleNamespace(
                id=8802,
                subentity_id=None,
                posting_batch=SimpleNamespace(id=9902, txn_type="OPENING_BALANCE", txn_id=None, voucher_no="OB-TEST-1"),
            ),
            SimpleNamespace(
                id=8803,
                subentity_id=None,
                posting_batch=SimpleNamespace(id=9903, txn_type="OPENING_BALANCE", txn_id=None, voucher_no="OB-TEST-2"),
            ),
        ]
        mock_posting_service.return_value.post.side_effect = entries
        mock_purge.return_value = {"deleted_entries": 1, "deleted_batches": 1}
        ready_preview = {
            "actions": {"can_generate": True},
            "opening_history": None,
            "source_year": {"is_closed": True},
            "opening_policy": {"require_closed_source_year": True},
            "destination_year": {"id": None},
        }
        mock_preview.return_value = ready_preview

        first_generation = build_opening_generation(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=None,
            executed_by=self.user,
        )
        first_destination_id = first_generation["destination_year"]["id"]
        first_destination = EntityFinancialYear.objects.get(pk=first_destination_id)
        self.assertIn("opening_carry_forward", first_destination.metadata)
        self.assertEqual(first_generation["opening_history"]["summary"]["reconciliation"]["status"], "balanced")

        mock_preview.return_value = {
            "opening_history": first_generation["opening_history"],
            "destination_year": {"id": first_destination_id},
        }
        rollback = build_opening_generation_rollback(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=None,
            executed_by=self.user,
        )

        self.assertEqual(rollback["status"], "success")
        self.assertEqual(rollback["entityfin_id"], self.entityfin.id)
        self.assertTrue(rollback["rollback"]["destination_year"]["deleted"])
        self.assertFalse(EntityFinancialYear.objects.filter(pk=first_destination_id).exists())
        self.entityfin.refresh_from_db()
        self.assertTrue(self.entityfin.isactive)

        mock_preview.return_value = ready_preview
        second_generation = build_opening_generation(
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=None,
            executed_by=self.user,
        )

        self.assertEqual(second_generation["status"], "success")
        self.assertNotEqual(second_generation["destination_year"]["id"], first_destination_id)
        self.assertEqual(second_generation["opening_history"]["summary"]["reconciliation"]["opening_difference"], "0.00")
        self.assertEqual(mock_posting_service.return_value.post.call_count, 2)


class RecurringJournalRunTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="recurring-runner",
            email="recurring-runner@example.com",
            password="pass@12345",
        )
        self.entity = Entity.objects.create(entityname="Recurring Run Entity", createdby=self.user)
        FinancialSettings.objects.create(
            entity=self.entity,
            reporting_policy={
                "recurring_journals": {
                    "enabled": True,
                    "run_mode": "manual_review",
                    "default_frequency": "monthly",
                    "templates": [
                        {
                            "code": "rent",
                            "name": "Rent Accrual",
                            "frequency": "monthly",
                            "status": "active",
                            "next_run_date": "2026-10-01",
                            "amount": "1000.00",
                        },
                        {
                            "code": "insurance",
                            "name": "Insurance Accrual",
                            "frequency": "monthly",
                            "status": "paused",
                            "next_run_date": "2026-10-01",
                            "amount": "500.00",
                        },
                    ],
                }
            },
            createdby=self.user,
        )

    def test_mark_recurring_journal_run_advances_due_active_templates(self):
        result = mark_recurring_journal_run(
            entity_id=self.entity.id,
            run_date=date(2026, 10, 7),
            created_by=self.user,
        )

        self.assertEqual(result["templates_reviewed"], 1)
        self.assertEqual(result["templates"][0]["code"], "rent")
        updated_templates = result["recurring_journal_policy"]["templates"]
        rent = next(item for item in updated_templates if item["code"] == "rent")
        insurance = next(item for item in updated_templates if item["code"] == "insurance")
        self.assertEqual(rent["last_run_date"], "2026-10-07")
        self.assertEqual(rent["next_run_date"], "2026-11-07")
        self.assertIsNone(insurance["last_run_date"])
        run_history = result["readiness"]["run_history"]
        self.assertEqual(run_history[0]["run_date"], "2026-10-07")
        self.assertEqual(run_history[0]["templates_reviewed"], 1)
        self.assertEqual(run_history[0]["vouchers_created"], 0)
        persisted_policy = resolve_recurring_journal_policy(entity_id=self.entity.id)
        self.assertEqual(persisted_policy["run_history"][0]["run_date"], "2026-10-07")

    @patch("reports.services.controls.recurring_journals.VoucherService.create_voucher")
    def test_mark_recurring_journal_run_creates_draft_voucher_when_auto_draft_is_mapped(self, mock_create):
        header = SimpleNamespace(id=77, voucher_code=None)
        mock_create.return_value = SimpleNamespace(header=header)
        settings = FinancialSettings.objects.get(entity=self.entity)
        policy = settings.reporting_policy
        policy["recurring_journals"]["run_mode"] = "auto_draft"
        policy["recurring_journals"]["templates"][0]["debit_account"] = 101
        policy["recurring_journals"]["templates"][0]["credit_account"] = 202
        settings.reporting_policy = policy
        settings.save(update_fields=["reporting_policy"])

        result = mark_recurring_journal_run(
            entity_id=self.entity.id,
            entityfin_id=55,
            subentity_id=66,
            run_date=date(2026, 10, 7),
            created_by=self.user,
        )

        self.assertEqual(result["vouchers_created"], 1)
        self.assertEqual(result["templates"][0]["status"], "draft_created")
        self.assertEqual(result["readiness"]["run_history"][0]["created_vouchers"][0]["id"], 77)
        payload = mock_create.call_args.kwargs["data"]
        self.assertEqual(payload["entityfinid_id"], 55)
        self.assertEqual(payload["subentity_id"], 66)
        self.assertEqual(payload["lines"][0]["account"], 101)
        self.assertEqual(payload["lines"][1]["account"], 202)

    def test_mark_recurring_journal_run_captures_failed_auto_draft_setup(self):
        settings = FinancialSettings.objects.get(entity=self.entity)
        policy = settings.reporting_policy
        policy["recurring_journals"]["run_mode"] = "auto_draft"
        settings.reporting_policy = policy
        settings.save(update_fields=["reporting_policy"])

        result = mark_recurring_journal_run(
            entity_id=self.entity.id,
            entityfin_id=55,
            run_date=date(2026, 10, 7),
            created_by=self.user,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["vouchers_created"], 0)
        self.assertEqual(result["failed_templates"][0]["code"], "rent")
        self.assertIn("Debit and credit posting accounts", result["failed_templates"][0]["failure_reason"])
        updated_template = next(item for item in result["recurring_journal_policy"]["templates"] if item["code"] == "rent")
        self.assertEqual(updated_template["status"], "failed")
        self.assertIn("Debit and credit posting accounts", updated_template["failure_reason"])
        self.assertTrue(result["readiness"]["run_history"][0]["retry_available"])

    @patch("reports.services.controls.recurring_journals.VoucherService.create_voucher")
    def test_mark_recurring_journal_run_retries_failed_template_after_mapping_fix(self, mock_create):
        header = SimpleNamespace(id=88, voucher_code="JV-88")
        mock_create.return_value = SimpleNamespace(header=header)
        settings = FinancialSettings.objects.get(entity=self.entity)
        policy = settings.reporting_policy
        policy["recurring_journals"]["run_mode"] = "auto_draft"
        policy["recurring_journals"]["templates"][0]["status"] = "failed"
        policy["recurring_journals"]["templates"][0]["failure_reason"] = "Debit and credit posting accounts are required."
        policy["recurring_journals"]["templates"][0]["debit_account"] = 101
        policy["recurring_journals"]["templates"][0]["credit_account"] = 202
        settings.reporting_policy = policy
        settings.save(update_fields=["reporting_policy"])

        result = mark_recurring_journal_run(
            entity_id=self.entity.id,
            entityfin_id=55,
            run_date=date(2026, 10, 7),
            created_by=self.user,
            retry_failed=True,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["vouchers_created"], 1)
        updated_template = next(item for item in result["recurring_journal_policy"]["templates"] if item["code"] == "rent")
        self.assertEqual(updated_template["status"], "active")
        self.assertIsNone(updated_template["failure_reason"])
        self.assertEqual(result["created_vouchers"][0]["id"], 88)

    @patch("reports.services.controls.recurring_journals.VoucherService.post_voucher")
    @patch("reports.services.controls.recurring_journals.VoucherService.confirm_voucher")
    @patch("reports.services.controls.recurring_journals.VoucherService.create_voucher")
    def test_mark_recurring_journal_run_auto_posts_through_voucher_service(self, mock_create, mock_confirm, mock_post):
        created_header = SimpleNamespace(id=91, voucher_code="JV-91")
        mock_create.return_value = SimpleNamespace(header=created_header)
        mock_confirm.return_value = SimpleNamespace(header=created_header)
        mock_post.return_value = SimpleNamespace(header=created_header)
        settings = FinancialSettings.objects.get(entity=self.entity)
        policy = settings.reporting_policy
        policy["recurring_journals"]["run_mode"] = "auto_post"
        policy["recurring_journals"]["templates"][0]["debit_account"] = 101
        policy["recurring_journals"]["templates"][0]["credit_account"] = 202
        settings.reporting_policy = policy
        settings.save(update_fields=["reporting_policy"])

        result = mark_recurring_journal_run(
            entity_id=self.entity.id,
            entityfin_id=55,
            run_date=date(2026, 10, 7),
            created_by=self.user,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["templates"][0]["status"], "posted")
        self.assertEqual(result["created_vouchers"][0]["status"], "posted")
        mock_confirm.assert_called_once_with(91, confirmed_by_id=self.user.id)
        mock_post.assert_called_once_with(91, posted_by_id=self.user.id)

    @patch("reports.services.controls.recurring_journals.VoucherService.post_voucher", side_effect=ValueError("Voucher must be approved before posting by approval workflow policy."))
    @patch("reports.services.controls.recurring_journals.VoucherService.confirm_voucher")
    @patch("reports.services.controls.recurring_journals.VoucherService.create_voucher")
    def test_mark_recurring_journal_run_auto_post_records_governance_blocker(self, mock_create, mock_confirm, _mock_post):
        created_header = SimpleNamespace(id=92, voucher_code="JV-92")
        mock_create.return_value = SimpleNamespace(header=created_header)
        mock_confirm.return_value = SimpleNamespace(header=created_header)
        settings = FinancialSettings.objects.get(entity=self.entity)
        policy = settings.reporting_policy
        policy["recurring_journals"]["run_mode"] = "auto_post"
        policy["recurring_journals"]["templates"][0]["debit_account"] = 101
        policy["recurring_journals"]["templates"][0]["credit_account"] = 202
        settings.reporting_policy = policy
        settings.save(update_fields=["reporting_policy"])

        result = mark_recurring_journal_run(
            entity_id=self.entity.id,
            entityfin_id=55,
            run_date=date(2026, 10, 7),
            created_by=self.user,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["templates"][0]["status"], "posting_blocked")
        self.assertEqual(result["created_vouchers"][0]["status"], "posting_blocked")
        self.assertIn("approved before posting", result["failed_templates"][0]["failure_reason"])
        updated_template = next(item for item in result["recurring_journal_policy"]["templates"] if item["code"] == "rent")
        self.assertEqual(updated_template["status"], "failed")

    @patch("reports.services.controls.recurring_journals.VoucherService.create_voucher")
    def test_mark_recurring_journal_run_does_not_duplicate_existing_same_template_run(self, mock_create):
        entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.now(),
            finendyear=timezone.now(),
            createdby=self.user,
        )
        existing = VoucherHeader.objects.create(
            entity=self.entity,
            entityfinid=entityfin,
            voucher_type=VoucherHeader.VoucherType.JOURNAL,
            voucher_date=date(2026, 10, 7),
            reference_number="RJ-rent",
            total_debit_amount="1000.00",
            total_credit_amount="1000.00",
            workflow_payload={
                "_recurring_journal": {
                    "code": "rent",
                    "name": "Rent Accrual",
                    "run_date": "2026-10-07",
                }
            },
            created_by=self.user,
        )
        settings = FinancialSettings.objects.get(entity=self.entity)
        policy = settings.reporting_policy
        policy["recurring_journals"]["run_mode"] = "auto_draft"
        policy["recurring_journals"]["templates"][0]["debit_account"] = 101
        policy["recurring_journals"]["templates"][0]["credit_account"] = 202
        settings.reporting_policy = policy
        settings.save(update_fields=["reporting_policy"])

        result = mark_recurring_journal_run(
            entity_id=self.entity.id,
            entityfin_id=entityfin.id,
            run_date=date(2026, 10, 7),
            created_by=self.user,
        )

        mock_create.assert_not_called()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["created_vouchers"][0]["id"], existing.id)
        self.assertEqual(result["created_vouchers"][0]["status"], "already_exists")
        self.assertEqual(result["templates"][0]["status"], "already_exists")
        self.assertEqual(result["skipped_templates"][0]["voucher_id"], existing.id)


class ApprovalWorkflowReadinessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="approval-readiness",
            email="approval-readiness@example.com",
            password="pass@12345",
        )
        self.entity = Entity.objects.create(entityname="Approval Readiness Entity", createdby=self.user)
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.now(),
            finendyear=timezone.now(),
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Head Office", is_head_office=True)
        FinancialSettings.objects.create(
            entity=self.entity,
            reporting_policy={
                "approval_workflow": {
                    "enabled": True,
                    "mode": "maker_checker",
                    "document_types": {"journal": True, "payment": True, "receipt": True, "bank": True, "cash": True},
                    "default_approver_role": "finance_manager",
                    "require_comment_on_reject": True,
                    "thresholds": [],
                }
            },
            createdby=self.user,
        )

    def test_approval_readiness_counts_pending_and_rejected_vouchers(self):
        VoucherHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_type=VoucherHeader.VoucherType.JOURNAL,
            doc_code="JV",
            status=VoucherHeader.Status.DRAFT,
            total_debit_amount="100.00",
            total_credit_amount="100.00",
            workflow_payload={"_approval_state": {"status": "SUBMITTED"}},
            created_by=self.user,
        )
        VoucherHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_type=VoucherHeader.VoucherType.JOURNAL,
            doc_code="JV",
            status=VoucherHeader.Status.DRAFT,
            total_debit_amount="50.00",
            total_credit_amount="50.00",
            workflow_payload={"_approval_state": {"status": "REJECTED"}},
            created_by=self.user,
        )

        payload = build_approval_workflow_readiness(self.entity.id)

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["status_label"], "Rejected Items")
        metrics = {card["label"]: card["value"] for card in payload["summary_cards"]}
        self.assertEqual(metrics["Pending"], 1)
        self.assertEqual(metrics["Rejected"], 1)
        self.assertEqual(len(payload["queue"]), 2)
        self.assertEqual(payload["queue"][0]["status"], "rejected")
        self.assertEqual(payload["queue"][0]["action"]["route"], "/journalvoucher")

    def test_approval_queue_exposes_threshold_metadata_and_actions(self):
        VoucherHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_type=VoucherHeader.VoucherType.JOURNAL,
            doc_code="JV",
            status=VoucherHeader.Status.DRAFT,
            total_debit_amount="2500.00",
            total_credit_amount="2500.00",
            workflow_payload={
                "_approval_state": {
                    "status": "SUBMITTED",
                    "submitted_by": self.user.id,
                    "approver_role": "controller",
                    "required_approvals": 2,
                    "threshold_name": "Senior review",
                    "remarks": "Needs approval",
                }
            },
            created_by=self.user,
        )

        queue = build_approval_queue(self.entity.id)

        self.assertEqual(queue[0]["threshold_name"], "Senior review")
        self.assertEqual(queue[0]["approver_role"], "controller")
        self.assertEqual(queue[0]["required_approvals"], 2)
        self.assertEqual(queue[0]["action"]["params"]["approval_status"], "submitted")
