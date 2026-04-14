from unittest.mock import patch

from django.test import SimpleTestCase

from reports.services.controls.phase_one import build_phase_one_controls_hub


class PhaseOneControlsManifestTests(SimpleTestCase):
    @patch("reports.services.controls.phase_one._resolve_scope")
    def test_phase_one_controls_manifest_groups_new_utilities(self, mock_resolve):
        mock_resolve.return_value = {
            "entity_name": "Aditi Gupta",
            "entityfin_name": "FY 2026-27",
            "subentity_name": "Head Office",
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
                "audit_trail",
                "document_attachments",
                "year_end_close",
            ],
        )
