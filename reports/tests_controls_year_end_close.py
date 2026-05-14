from unittest.mock import patch
import contextlib
from datetime import datetime

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from posting.models import TxnType
from reports.services.controls.year_end_close import build_year_end_close_execution, build_year_end_close_preview, build_year_end_close_rollback


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
                "income": [{"label": "Sales", "amount": "125000.00"}],
                "expenses": [{"label": "Rent", "amount": "100000.00"}],
            },
            "bs": {
                "totals": {"assets": "150000.00", "liabilities_and_equity": "150000.00"},
                "assets": [{"label": "Cash", "amount": "150000.00"}],
                "liabilities_and_equity": [{"label": "Equity", "amount": "150000.00"}],
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
        self.assertEqual(payload["carry_forward_buckets"][0]["value"], 2)
        self.assertEqual(payload["carry_forward_buckets"][1]["value"], 2)
        self.assertIn("Execute the close", payload["next_steps"][0] + " " + " ".join(payload["next_steps"][1:]))
        self.assertIn("2 permanent balance rows", payload["carry_forward_notes"][0])
        self.assertIn("profit is expected to move", payload["carry_forward_notes"][2])

    @patch("reports.services.controls.year_end_close.transaction.atomic", return_value=contextlib.nullcontext())
    @patch("reports.services.controls.year_end_close.PostingService")
    @patch("reports.services.controls.year_end_close._build_close_journal_lines")
    @patch("reports.services.controls.year_end_close.FinancialSettings.objects.filter")
    @patch("reports.services.controls.year_end_close.EntityFinancialYear.objects.select_for_update")
    @patch("reports.services.controls.year_end_close._compute_snapshot")
    @patch("reports.services.controls.year_end_close.build_year_end_close_preview")
    def test_year_end_close_execution_stamps_year_metadata(
        self,
        mock_preview,
        mock_snapshot,
        mock_select_for_update,
        mock_settings_filter,
        mock_build_close_journal_lines,
        mock_posting_service_cls,
        _mock_atomic,
    ):
        class DummyFinancialYear:
            def __init__(self):
                self.id = 51
                self.pk = 51
                self.desc = "FY 2026-27"
                self.year_code = "FY2026-27"
                self.finendyear = datetime(2027, 3, 31)
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
            "warnings": [],
            "next_steps": [],
            "snapshot": {},
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
        mock_settings_filter.return_value.only.return_value.first.return_value = None
        mock_build_close_journal_lines.return_value = (
            [object()],
            [{"section": "equity", "label": "Retained Earnings", "amount": "25000.00", "drcr": "credit", "source": "retained_earnings"}],
            {"net_profit": "25000.00"},
        )
        mock_select_for_update.return_value = DummyQuerySet(dummy_fy)
        mock_posting_service_cls.return_value.post.return_value = type(
            "Entry",
            (),
            {
                "id": 7001,
                "voucher_no": "YEC-FY2026-27",
                "posting_date": datetime(2027, 3, 31).date(),
                "posting_batch": type("Batch", (), {"id": 9001})(),
            },
        )()

        payload = build_year_end_close_execution(entity_id=58, entityfin_id=51, subentity_id=17, executed_by=None)

        self.assertEqual(payload["status"], "success")
        self.assertTrue(dummy_fy.is_year_closed)
        self.assertEqual(dummy_fy.period_status, "closed")
        self.assertIn("year_end_close", dummy_fy.metadata)
        self.assertEqual(dummy_fy.metadata["year_end_close"]["journal_entry"]["entry_id"], 7001)
        self.assertEqual(payload["execution"]["journal_entry"]["voucher_no"], "YEC-FY2026-27")
        self.assertEqual(payload["execution"]["journal_entry"]["drilldown"]["target"], "posting_detail")
        self.assertEqual(payload["execution"]["journal_entry"]["drilldown"]["params"]["entry_id"], 7001)
        self.assertTrue(mock_posting_service_cls.return_value.post.called)
        self.assertEqual(mock_posting_service_cls.return_value.post.call_args.kwargs["txn_type"], TxnType.YEAR_END_CLOSE)
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
                        "warnings": ["Profit and loss snapshot was generated from fallback statements."],
                        "next_steps": ["Year-end close has already been executed for this scope."],
                        "journal_entry": {"entry_id": 7001, "posting_batch_id": 9001, "voucher_no": "YEC-FY2026-27", "posting_date": "2027-03-31", "line_count": 1, "lines": [], "diagnostics": {}},
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
        self.assertEqual(payload["close_history"]["warnings"][0], "Profit and loss snapshot was generated from fallback statements.")
        self.assertEqual(payload["close_history"]["next_steps"][0], "Year-end close has already been executed for this scope.")
        self.assertEqual(payload["close_history"]["journal_entry"]["voucher_no"], "YEC-FY2026-27")
        self.assertEqual(payload["close_history"]["journal_entry"]["drilldown"]["target"], "posting_detail")
        self.assertEqual(payload["close_history"]["journal_entry"]["drilldown"]["params"]["entry_id"], 7001)

    @patch("reports.services.controls.year_end_close.build_year_end_close_preview")
    def test_year_end_close_execution_rejects_review_state(self, mock_preview):
        mock_preview.return_value = {
            "close_state": {
                "period_status": "open",
                "is_year_closed": False,
                "is_audit_closed": False,
                "books_locked_until": None,
                "gst_locked_until": None,
                "inventory_locked_until": None,
                "ap_ar_locked_until": None,
                "opening_balance_edit_mode": "before_posting",
                "readiness_state": "review",
            }
        }

        with self.assertRaises(ValidationError) as ctx:
            build_year_end_close_execution(entity_id=58, entityfin_id=51, subentity_id=17, executed_by=None)

        self.assertEqual(
            ctx.exception.detail,
            {"detail": "Year-end close can only be executed when the readiness state is ready."}
        )

    @patch("reports.services.controls.year_end_close.transaction.atomic", return_value=contextlib.nullcontext())
    @patch("reports.services.controls.year_end_close.purge_posting_locator")
    @patch("reports.services.controls.opening_preview._resolve_destination_year")
    @patch("reports.services.controls.year_end_close.EntityFinancialYear.objects.select_for_update")
    @patch("reports.services.controls.year_end_close._resolve_scope")
    def test_year_end_close_rollback_reopens_year_and_clears_metadata(
        self,
        mock_resolve_scope,
        mock_select_for_update,
        mock_resolve_destination_year,
        mock_purge_posting_locator,
        _mock_atomic,
    ):
        class DummyFinancialYear:
            def __init__(self):
                self.id = 51
                self.pk = 51
                self.metadata = {
                    "year_end_close": {
                        "scope": {"entityfin_id": 51},
                        "previous_state": {
                            "period_status": "open",
                            "is_year_closed": False,
                            "books_locked_until": None,
                            "gst_locked_until": None,
                            "inventory_locked_until": None,
                            "ap_ar_locked_until": None,
                        },
                        "journal_entry": {"entry_id": 7001, "voucher_no": "YEC-FY2026-27"},
                    }
                }
                self.period_status = "closed"
                self.is_year_closed = True
                self.books_locked_until = datetime(2027, 3, 31).date()
                self.gst_locked_until = datetime(2027, 3, 31).date()
                self.inventory_locked_until = datetime(2027, 3, 31).date()
                self.ap_ar_locked_until = datetime(2027, 3, 31).date()
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
        mock_resolve_scope.return_value = {"entityfin_object": dummy_fy}
        mock_select_for_update.return_value = DummyQuerySet(dummy_fy)
        mock_resolve_destination_year.return_value = {"id": None}
        mock_purge_posting_locator.return_value = {"entries_deleted": 1, "journal_lines_deleted": 3}

        payload = build_year_end_close_rollback(entity_id=58, entityfin_id=51, subentity_id=17, executed_by=None)

        self.assertEqual(payload["status"], "success")
        self.assertEqual(dummy_fy.period_status, "open")
        self.assertFalse(dummy_fy.is_year_closed)
        self.assertNotIn("year_end_close", dummy_fy.metadata)
        self.assertIn("year_end_close_rollbacks", dummy_fy.metadata)
        self.assertEqual(dummy_fy.saved_fields, [
            "metadata",
            "period_status",
            "is_year_closed",
            "books_locked_until",
            "gst_locked_until",
            "inventory_locked_until",
            "ap_ar_locked_until",
        ])
