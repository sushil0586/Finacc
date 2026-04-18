from unittest.mock import patch

from django.test import SimpleTestCase

from reports.services.controls.phase_one import build_phase_one_controls_hub


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
        self.assertEqual(len(payload["summary_cards"]), 4)
        self.assertEqual(len(payload["sections"]), 2)
        self.assertEqual(
            [section["key"] for section in payload["sections"]],
            ["control_basics", "close_operations"],
        )
        self.assertEqual(
            [card["code"] for section in payload["sections"] for card in section["cards"]],
            [
                "bank_reconciliation",
                "recurring_journals",
                "voucher_approvals",
                "opening_policy",
                "opening_preview",
                "audit_trail",
                "document_attachments",
                "year_end_close",
            ],
        )
        self.assertIn("opening_policy", payload)
        self.assertIn("opening_policy_summary", payload)
        self.assertEqual(payload["opening_policy"]["opening_mode"], "hybrid")
        self.assertEqual(payload["opening_policy"]["batch_materialization"], "single_batch")
        self.assertGreaterEqual(len(payload["opening_policy_summary"]), 4)
