from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from reports.services.controls.opening_preview import build_opening_preview


class OpeningPreviewTests(SimpleTestCase):
    @patch("reports.services.controls.opening_preview.EntityFinancialYear.objects.filter")
    @patch("reports.services.controls.opening_preview.resolve_opening_policy")
    @patch("reports.services.controls.opening_preview.build_year_end_close_preview")
    @patch("reports.services.controls.opening_preview.YearOpeningPostingAdapter.build_context")
    def test_opening_preview_surfaces_destination_and_policy(self, mock_build_context, mock_close_preview, mock_policy, mock_fy_filter):
        mock_close_preview.return_value = {
            "report_code": "year_end_close_preview",
            "report_name": "Year-End Close",
            "report_eyebrow": "Financial Controls",
            "entity_id": 58,
            "entity_name": "Aditi Gupta",
            "entityfin_id": 51,
            "entityfin_name": "FY 2026-27",
            "subentity_id": 17,
            "subentity_name": "Head Office",
            "generated_at": "2026-04-15T00:00:00+05:30",
            "close_state": {
                "period_status": "closed",
                "is_year_closed": True,
                "is_audit_closed": False,
                "books_locked_until": None,
                "gst_locked_until": None,
                "inventory_locked_until": None,
                "ap_ar_locked_until": None,
                "opening_balance_edit_mode": "before_posting",
                "readiness_state": "ready",
            },
            "opening_balance_preview": {
                "assets": [{"label": "Cash", "amount": "100.00"}],
                "liabilities_and_equity": [{"label": "Capital", "amount": "100.00"}],
            },
            "book_boundary": {
                "from_date": "2026-04-01",
                "to_date": "2027-03-31",
                "first_posting_date": "2026-04-01",
                "last_posting_date": "2027-03-31",
            },
            "warnings": [],
        }
        mock_policy.return_value = {
            "opening_mode": "hybrid",
            "batch_materialization": "single_batch",
            "opening_posting_date_strategy": "first_day_of_new_year",
            "require_closed_source_year": True,
            "allow_partial_opening": False,
            "carry_forward": {"cash_bank": True, "receivables": True},
            "reset": {"trading": True, "profit_loss": True},
            "grouped_sections": ["assets", "liabilities"],
        }
        mock_build_context.return_value = {
            "constitution": {
                "constitution_mode": "company",
                "allocation_mode": "retained_earnings",
                "total_share_percentage": "100.00",
                "constitution_source": "tax_profile.cin_no",
                "constitution_notes": ["CIN detected in entity tax profile."],
                "validation_issues": [],
                "is_valid": True,
                "ownership_rows": [],
            },
            "allocation_plan": [],
            "equity_targets": [],
            "missing_equity_codes": [],
            "equity_allocation_mode": "retained_earnings",
            "validation_issues": [],
        }

        mock_fy = MagicMock()
        mock_fy.id = 52
        mock_fy.desc = "FY 2027-28"
        mock_fy.year_code = "FY2027-28"
        mock_fy.finstartyear = None
        mock_fy.finendyear = None
        mock_fy.period_status = "open"
        mock_fy_filter.return_value.order_by.return_value.first.return_value = mock_fy

        payload = build_opening_preview(entity_id=58, entityfin_id=51, subentity_id=17)

        self.assertEqual(payload["report_code"], "opening_preview")
        self.assertEqual(payload["opening_policy"]["opening_mode"], "hybrid")
        self.assertEqual(payload["destination_year"]["id"], 52)
        self.assertEqual(payload["source_year"]["name"], "FY 2026-27")
        self.assertEqual(payload["summary_cards"][0]["label"], "Opening assets")
        self.assertEqual(payload["constitution"]["constitution_source"], "tax_profile.cin_no")
        self.assertTrue(payload["actions"]["can_preview"])
        self.assertTrue(payload["actions"]["can_generate"])
        self.assertEqual(payload["preview_state"], "ready")

    @patch("reports.services.controls.opening_preview.EntityFinancialYear.objects.filter")
    @patch("reports.services.controls.opening_preview.resolve_opening_policy")
    @patch("reports.services.controls.opening_preview.build_year_end_close_preview")
    @patch("reports.services.controls.opening_preview.YearOpeningPostingAdapter.build_context")
    def test_opening_preview_blocks_generation_on_invalid_constitution(
        self,
        mock_build_context,
        mock_close_preview,
        mock_policy,
        mock_fy_filter,
    ):
        mock_close_preview.return_value = {
            "report_code": "year_end_close_preview",
            "report_name": "Year-End Close",
            "report_eyebrow": "Financial Controls",
            "entity_id": 58,
            "entity_name": "Aditi Gupta",
            "entityfin_id": 51,
            "entityfin_name": "FY 2026-27",
            "subentity_id": 17,
            "subentity_name": "Head Office",
            "generated_at": "2026-04-15T00:00:00+05:30",
            "close_state": {
                "period_status": "closed",
                "is_year_closed": True,
                "is_audit_closed": False,
                "books_locked_until": None,
                "gst_locked_until": None,
                "inventory_locked_until": None,
                "ap_ar_locked_until": None,
                "opening_balance_edit_mode": "before_posting",
                "readiness_state": "ready",
            },
            "opening_balance_preview": {
                "assets": [{"label": "Cash", "amount": "100.00"}],
                "liabilities_and_equity": [{"label": "Capital", "amount": "100.00"}],
            },
            "book_boundary": {
                "from_date": "2026-04-01",
                "to_date": "2027-03-31",
                "first_posting_date": "2026-04-01",
                "last_posting_date": "2027-03-31",
            },
            "warnings": [],
        }
        mock_policy.return_value = {
            "opening_mode": "hybrid",
            "batch_materialization": "single_batch",
            "opening_posting_date_strategy": "first_day_of_new_year",
            "require_closed_source_year": True,
            "allow_partial_opening": False,
            "carry_forward": {"cash_bank": True, "receivables": True},
            "reset": {"trading": True, "profit_loss": True},
            "grouped_sections": ["assets", "liabilities"],
        }
        mock_build_context.return_value = {
            "constitution": {
                "constitution_mode": "partnership",
                "allocation_mode": "ratio_split",
                "total_share_percentage": "90.00",
                "constitution_source": "ownership_rows",
                "constitution_notes": ["Partner shares do not total 100%."],
                "validation_issues": [
                    {
                        "code": "partner_share_total",
                        "severity": "error",
                        "message": "Partner shares must total 100% before opening and allocation can proceed.",
                    }
                ],
                "is_valid": False,
                "ownership_rows": [],
            },
            "allocation_plan": [],
            "equity_targets": [],
            "missing_equity_codes": [],
            "equity_allocation_mode": "ratio_split",
            "validation_issues": [
                {
                    "code": "partner_share_total",
                    "severity": "error",
                    "message": "Partner shares must total 100% before opening and allocation can proceed.",
                }
            ],
        }
        mock_fy = MagicMock()
        mock_fy.id = 52
        mock_fy.desc = "FY 2027-28"
        mock_fy.year_code = "FY2027-28"
        mock_fy.finstartyear = None
        mock_fy.finendyear = None
        mock_fy.period_status = "open"
        mock_fy_filter.return_value.order_by.return_value.first.return_value = mock_fy

        payload = build_opening_preview(entity_id=58, entityfin_id=51, subentity_id=17)

        self.assertEqual(payload["preview_state"], "blocked")
        self.assertFalse(payload["actions"]["can_generate"])
        self.assertTrue(any(issue["code"] == "partner_share_total" for issue in payload["validation_issues"]))
