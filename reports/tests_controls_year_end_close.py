from unittest.mock import patch
import contextlib

from django.test import SimpleTestCase

from reports.services.controls.year_end_close import build_year_end_close_execution, build_year_end_close_preview


class YearEndClosePreviewTests(SimpleTestCase):
    @patch("reports.services.controls.year_end_close._resolve_scope")
    @patch("reports.services.controls.year_end_close._compute_snapshot")
    def test_year_end_close_preview_returns_readiness_and_snapshot(self, mock_snapshot, mock_resolve):
        mock_resolve.return_value = {
            "entity_name": "Aditi Gupta",
            "entityfin_name": "FY 2026-27",
            "subentity_name": "Head Office",
        }
        mock_snapshot.return_value = {
            "financial_year": None,
            "from_date": None,
            "to_date": None,
            "first_posting_date": None,
            "last_posting_date": None,
            "settings": None,
            "pnl": {
                "totals": {"income": "125000.00", "expense": "100000.00", "net_profit": "25000.00"},
                "income": [{"label": "Sales"}],
                "expenses": [{"label": "Rent"}],
            },
            "bs": {
                "totals": {"assets": "150000.00", "liabilities_and_equity": "150000.00"},
                "assets": [{"label": "Cash"}],
                "liabilities_and_equity": [{"label": "Equity"}],
            },
            "pnl_error": None,
            "bs_error": None,
            "close_state": {
                "period_status": "open",
                "is_year_closed": False,
                "is_audit_closed": False,
                "books_locked_until": None,
                "gst_locked_until": None,
                "inventory_locked_until": None,
                "ap_ar_locked_until": None,
                "opening_balance_edit_mode": "before_posting",
                "readiness_state": "ready",
            },
            "checks": [
                {"key": "year_not_closed", "label": "Financial year is open", "status": "pass", "detail": "ok", "tone": "available"},
            ],
            "summary": {
                "total_entries": 12,
                "draft_entries": 0,
                "posted_entries": 12,
                "reversed_entries": 0,
                "income_total": 125000,
                "expense_total": 100000,
                "net_profit": 25000,
                "assets_total": 150000,
                "liabilities_total": 150000,
                "balance_difference": 0,
            },
        }

        payload = build_year_end_close_preview(entity_id=58, entityfin_id=51, subentity_id=17)

        self.assertEqual(payload["report_code"], "year_end_close_preview")
        self.assertEqual(payload["entity_name"], "Aditi Gupta")
        self.assertEqual(payload["entityfin_name"], "FY 2026-27")
        self.assertEqual(payload["subentity_name"], "Head Office")
        self.assertEqual(payload["close_state"]["readiness_state"], "ready")
        self.assertEqual(payload["snapshot"]["profit_loss"]["net_profit"], "25000.00")
        self.assertEqual(payload["snapshot"]["balance_sheet"]["difference"], "0.00")
        self.assertEqual(payload["closing_entries"][0]["amount"], "25000.00")
        self.assertIn("assets", payload["opening_balance_preview"])
        self.assertEqual(len(payload["summary_cards"]), 4)
        self.assertIsNone(payload["close_history"])

    @patch("reports.services.controls.year_end_close.transaction.atomic", return_value=contextlib.nullcontext())
    @patch("reports.services.controls.year_end_close.EntityFinancialYear.objects.select_for_update")
    @patch("reports.services.controls.year_end_close._compute_snapshot")
    @patch("reports.services.controls.year_end_close.build_year_end_close_preview")
    def test_year_end_close_execution_stamps_year_metadata(self, mock_preview, mock_snapshot, mock_select_for_update, _mock_atomic):
        class DummyFinancialYear:
            def __init__(self):
                self.id = 51
                self.pk = 51
                self.finendyear = None
                self.metadata = {}
                self.period_status = "open"
                self.is_year_closed = False
                self.books_locked_until = None
                self.gst_locked_until = None
                self.inventory_locked_until = None
                self.ap_ar_locked_until = None
                self.saved_fields = None

            def save(self, update_fields=None):
                self.saved_fields = update_fields

        class DummyQuerySet:
            def __init__(self, financial_year):
                self.financial_year = financial_year

            def filter(self, **_kwargs):
                return self

            def first(self):
                return self.financial_year

        dummy_fy = DummyFinancialYear()
        mock_preview.return_value = {
            "entity_name": "Aditi Gupta",
            "entityfin_name": "FY 2026-27",
            "subentity_name": "Head Office",
            "checks": [
                {"key": "year_not_closed", "label": "Financial year is open", "status": "pass", "detail": "ok", "tone": "available"},
            ],
            "book_boundary": {"from_date": None, "to_date": None, "first_posting_date": None, "last_posting_date": None},
            "carry_forward_buckets": [],
            "carry_forward_notes": [],
            "closing_entries": [],
            "source_summary": [],
            "close_state": {
                "period_status": "open",
                "is_year_closed": False,
                "is_audit_closed": False,
                "books_locked_until": None,
                "gst_locked_until": None,
                "inventory_locked_until": None,
                "ap_ar_locked_until": None,
                "opening_balance_edit_mode": "before_posting",
                "readiness_state": "ready",
            },
        }
        mock_snapshot.return_value = {
            "financial_year": dummy_fy,
            "summary": {
                "total_entries": 12,
                "draft_entries": 0,
                "posted_entries": 12,
                "reversed_entries": 0,
                "income_total": 125000,
                "expense_total": 100000,
                "net_profit": 25000,
                "assets_total": 150000,
                "liabilities_total": 150000,
                "balance_difference": 0,
            },
        }
        mock_select_for_update.return_value = DummyQuerySet(dummy_fy)

        payload = build_year_end_close_execution(entity_id=58, entityfin_id=51, subentity_id=17, executed_by=None)

        self.assertEqual(payload["status"], "success")
        self.assertTrue(dummy_fy.is_year_closed)
        self.assertEqual(dummy_fy.period_status, "closed")
        self.assertIn("year_end_close", dummy_fy.metadata)
        self.assertEqual(dummy_fy.saved_fields, [
            "metadata",
            "period_status",
            "is_year_closed",
            "books_locked_until",
            "gst_locked_until",
            "inventory_locked_until",
            "ap_ar_locked_until",
        ])

    @patch("reports.services.controls.year_end_close._resolve_scope")
    @patch("reports.services.controls.year_end_close._compute_snapshot")
    def test_year_end_close_preview_includes_close_history_from_metadata(self, mock_snapshot, mock_resolve):
        dummy_fy = type(
            "DummyFY",
            (),
            {
                "id": 51,
                "metadata": {
                    "year_end_close": {
                        "status": "closed",
                        "closed_at": "2026-04-14T10:00:00+00:00",
                        "closed_on": "2026-03-31",
                        "closed_by": {"id": 10, "username": "finance", "name": "Finance User"},
                        "summary": {
                            "entries": 12,
                            "draft_entries": 0,
                            "posted_entries": 12,
                            "reversed_entries": 0,
                            "income_total": "125000.00",
                            "expense_total": "100000.00",
                            "net_profit": "25000.00",
                            "assets_total": "150000.00",
                            "liabilities_total": "150000.00",
                            "balance_difference": "0.00",
                        },
                    }
                },
            },
        )()
        mock_resolve.return_value = {
            "entity_name": "Aditi Gupta",
            "entityfin_name": "FY 2026-27",
            "subentity_name": "Head Office",
        }
        mock_snapshot.return_value = {
            "financial_year": dummy_fy,
            "summary": {
                "total_entries": 12,
                "draft_entries": 0,
                "posted_entries": 12,
                "reversed_entries": 0,
                "income_total": 125000,
                "expense_total": 100000,
                "net_profit": 25000,
                "assets_total": 150000,
                "liabilities_total": 150000,
                "balance_difference": 0,
            },
            "from_date": None,
            "to_date": None,
            "first_posting_date": None,
            "last_posting_date": None,
            "settings": None,
            "pnl": {},
            "bs": {},
            "pnl_error": None,
            "bs_error": None,
            "close_state": {
                "period_status": "closed",
                "is_year_closed": True,
                "is_audit_closed": False,
                "books_locked_until": None,
                "gst_locked_until": None,
                "inventory_locked_until": None,
                "ap_ar_locked_until": None,
                "opening_balance_edit_mode": "before_posting",
                "readiness_state": "blocked",
            },
            "checks": [],
        }

        payload = build_year_end_close_preview(entity_id=58, entityfin_id=51, subentity_id=17)

        self.assertIsNotNone(payload["close_history"])
        self.assertEqual(payload["close_history"]["status"], "closed")
        self.assertEqual(payload["close_history"]["closed_by"]["username"], "finance")
