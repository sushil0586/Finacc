from unittest.mock import patch

from django.test import SimpleTestCase

from reports.services.controls.phase_one import _build_gst_compliance_snapshot, build_phase_one_controls_hub


class PhaseOneControlsManifestTests(SimpleTestCase):
    @patch("reports.services.controls.phase_one._resolve_scope")
    @patch("reports.services.controls.phase_one.resolve_opening_policy")
    def test_phase_one_controls_manifest_groups_new_utilities(self, mock_opening_policy, mock_resolve):
        mock_resolve.return_value = {
            "entity_name": "Aditi Gupta",
            "entityfin_name": "FY 2026-27",
            "subentity_name": "Head Office",
        }
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
        self.assertIn("summary_cards", payload["compliance_readiness"])
        self.assertIn("opening_policy", payload)
        self.assertIn("opening_policy_summary", payload)
        self.assertEqual(payload["opening_policy"]["opening_mode"], "hybrid")
        self.assertEqual(payload["opening_policy"]["batch_materialization"], "single_batch")
        self.assertGreaterEqual(len(payload["opening_policy_summary"]), 4)

    @patch("reports.services.controls.phase_one._build_gst_compliance_snapshot")
    @patch("reports.services.controls.phase_one._resolve_scope")
    @patch("reports.services.controls.phase_one.resolve_opening_policy")
    def test_compliance_readiness_actions_contract(self, mock_opening_policy, mock_resolve, mock_gst_snapshot):
        mock_resolve.return_value = {
            "entity_name": "Aditi Gupta",
            "entityfin_name": "FY 2026-27",
            "subentity_name": "Head Office",
        }
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
