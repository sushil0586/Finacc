from unittest.mock import patch
import contextlib
from datetime import date, datetime
from decimal import Decimal

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from posting.models import TxnType
from reports.services.controls.year_end_close import (
    _build_checks,
    _build_close_journal_lines,
    build_year_end_close_execution,
    build_year_end_close_preview,
    build_year_end_close_rollback,
)


class YearEndClosePreviewTests(SimpleTestCase):
    def _close_snapshot(self, *, income_credit: str, expense_debit: str, net_profit: str):
        return {
            "financial_year": type(
                "DummyFY",
                (),
                {
                    "finstartyear": date(2026, 4, 1),
                    "finendyear": date(2027, 3, 31),
                },
            )(),
            "pnl": {
                "income": [
                    {
                        "label": "Service Revenue",
                        "accounthead_id": 101,
                        "debit": "0.00",
                        "credit": income_credit,
                        "amount": income_credit,
                    }
                ],
                "expenses": [
                    {
                        "label": "Operating Expense",
                        "accounthead_id": 202,
                        "debit": expense_debit,
                        "credit": "0.00",
                        "amount": expense_debit,
                    }
                ],
            },
            "summary": {
                "income_total": Decimal(income_credit),
                "expense_total": Decimal(expense_debit),
                "net_profit": Decimal(net_profit),
            },
        }

    def _assert_journal_balances(self, journal_lines):
        debit_total = sum((line.amount for line in journal_lines if line.drcr), Decimal("0.00"))
        credit_total = sum((line.amount for line in journal_lines if not line.drcr), Decimal("0.00"))
        self.assertEqual(debit_total, credit_total)

    def test_close_readiness_checks_surface_draft_and_balance_difference_warnings(self):
        checks = _build_checks(
            scope={"is_year_closed": False, "opening_balance_edit_mode": "before_posting"},
            draft_count=3,
            balance_difference=Decimal("42.50"),
            net_profit=Decimal("0.00"),
        )

        checks_by_key = {item["key"]: item for item in checks}
        self.assertEqual(checks_by_key["drafts"]["status"], "warning")
        self.assertEqual(checks_by_key["drafts"]["detail"], "3 draft entry/entries are still pending.")
        self.assertEqual(checks_by_key["balance_sheet"]["status"], "warning")
        self.assertEqual(checks_by_key["balance_sheet"]["detail"], "Balance difference is 42.50.")
        self.assertEqual(checks_by_key["profit_transfer"]["status"], "pass")
        self.assertEqual(checks_by_key["profit_transfer"]["detail"], "Current year is break even.")

    @patch("reports.services.controls.year_end_close.StaticAccountService.get_ledger_id", return_value=909)
    @patch("reports.services.controls.year_end_close.StaticAccountService.get_account_id", return_value=808)
    @patch("reports.services.controls.year_end_close._posted_appropriation_coverage", return_value=None)
    @patch("reports.services.controls.year_end_close.YearOpeningPostingAdapter")
    def test_close_journal_moves_profit_to_retained_earnings_and_balances(
        self,
        mock_opening_adapter,
        _mock_appropriation,
        _mock_account,
        _mock_ledger,
    ):
        mock_opening_adapter.return_value.build_context.return_value = {
            "equity_allocation_mode": "retained_earnings",
            "validation_issues": [],
            "equity_targets": [],
            "missing_equity_codes": [],
        }

        journal_lines, line_meta, diagnostics = _build_close_journal_lines(
            snapshot=self._close_snapshot(income_credit="500.00", expense_debit="200.00", net_profit="300.00"),
            entity_id=58,
            entityfin_id=51,
            subentity_id=17,
            opening_policy={"opening_equity_static_account_code": "OPENING_EQUITY_TRANSFER"},
        )

        self._assert_journal_balances(journal_lines)
        self.assertEqual(diagnostics["postable_net_profit"], "300.00")
        self.assertEqual(line_meta[0]["section"], "income")
        self.assertEqual(line_meta[0]["drcr"], "debit")
        self.assertEqual(line_meta[1]["section"], "expense")
        self.assertEqual(line_meta[1]["drcr"], "credit")
        self.assertEqual(line_meta[2]["section"], "equity")
        self.assertEqual(line_meta[2]["drcr"], "credit")
        self.assertEqual(line_meta[2]["amount"], "300.00")

    @patch("reports.services.controls.year_end_close.StaticAccountService.get_ledger_id", return_value=909)
    @patch("reports.services.controls.year_end_close.StaticAccountService.get_account_id", return_value=808)
    @patch("reports.services.controls.year_end_close._posted_appropriation_coverage", return_value=None)
    @patch("reports.services.controls.year_end_close.YearOpeningPostingAdapter")
    def test_close_journal_moves_loss_against_retained_earnings_and_balances(
        self,
        mock_opening_adapter,
        _mock_appropriation,
        _mock_account,
        _mock_ledger,
    ):
        mock_opening_adapter.return_value.build_context.return_value = {
            "equity_allocation_mode": "retained_earnings",
            "validation_issues": [],
            "equity_targets": [],
            "missing_equity_codes": [],
        }

        journal_lines, line_meta, diagnostics = _build_close_journal_lines(
            snapshot=self._close_snapshot(income_credit="100.00", expense_debit="250.00", net_profit="-150.00"),
            entity_id=58,
            entityfin_id=51,
            subentity_id=17,
            opening_policy={"opening_equity_static_account_code": "OPENING_EQUITY_TRANSFER"},
        )

        self._assert_journal_balances(journal_lines)
        self.assertEqual(diagnostics["postable_net_profit"], "-150.00")
        self.assertEqual(line_meta[0]["drcr"], "debit")
        self.assertEqual(line_meta[1]["drcr"], "credit")
        self.assertEqual(line_meta[2]["section"], "equity")
        self.assertEqual(line_meta[2]["drcr"], "debit")
        self.assertEqual(line_meta[2]["amount"], "150.00")

    @patch("reports.services.controls.year_end_close._posted_appropriation_coverage", return_value=None)
    @patch("reports.services.controls.year_end_close.YearOpeningPostingAdapter")
    def test_close_journal_uses_proprietor_capital_target_and_diagnostics(self, mock_opening_adapter, _mock_appropriation):
        mock_opening_adapter.return_value.build_context.return_value = {
            "equity_allocation_mode": "single_owner",
            "validation_issues": [],
            "equity_targets": [
                {
                    "static_account_code": "OPENING_OWNER_CAPITAL__OWNERSHIP_1",
                    "static_account_name": "Opening Owner Capital - Aditi Gupta",
                    "ownership_id": 1,
                    "ownership_name": "Aditi Gupta",
                    "amount": "300.00",
                    "drcr": "credit",
                    "account_id": 8081,
                    "ledger_id": 9091,
                }
            ],
            "missing_equity_codes": [],
            "constitution": {"constitution_mode": "proprietorship"},
            "allocation_plan": [
                {
                    "ownership_id": 1,
                    "name": "Aditi Gupta",
                    "ownership_type": "proprietor",
                    "share_percentage": "100.00",
                    "amount": "300.00",
                    "drcr": "credit",
                }
            ],
        }

        journal_lines, line_meta, diagnostics = _build_close_journal_lines(
            snapshot=self._close_snapshot(income_credit="500.00", expense_debit="200.00", net_profit="300.00"),
            entity_id=58,
            entityfin_id=51,
            subentity_id=17,
            opening_policy={},
        )

        self._assert_journal_balances(journal_lines)
        self.assertEqual(line_meta[2]["label"], "Opening Owner Capital - Aditi Gupta")
        self.assertEqual(line_meta[2]["amount"], "300.00")
        self.assertEqual(line_meta[2]["drcr"], "credit")
        self.assertEqual(diagnostics["equity_allocation_mode"], "single_owner")
        self.assertEqual(diagnostics["constitution"]["constitution_mode"], "proprietorship")
        self.assertEqual(diagnostics["allocation_plan"][0]["ownership_type"], "proprietor")

    @patch("reports.services.controls.year_end_close._posted_appropriation_coverage", return_value=None)
    @patch("reports.services.controls.year_end_close.YearOpeningPostingAdapter")
    def test_close_journal_splits_partnership_profit_and_balances(self, mock_opening_adapter, _mock_appropriation):
        mock_opening_adapter.return_value.build_context.return_value = {
            "equity_allocation_mode": "ratio_split",
            "validation_issues": [],
            "equity_targets": [
                {
                    "static_account_code": "OPENING_PARTNER_CAPITAL__OWNERSHIP_1",
                    "static_account_name": "Opening Partner Capital - Aditi",
                    "ownership_id": 1,
                    "ownership_name": "Aditi",
                    "amount": "180.00",
                    "drcr": "credit",
                    "account_id": 8081,
                    "ledger_id": 9091,
                },
                {
                    "static_account_code": "OPENING_PARTNER_CAPITAL__OWNERSHIP_2",
                    "static_account_name": "Opening Partner Capital - Rohan",
                    "ownership_id": 2,
                    "ownership_name": "Rohan",
                    "amount": "120.00",
                    "drcr": "credit",
                    "account_id": 8082,
                    "ledger_id": 9092,
                },
            ],
            "missing_equity_codes": [],
            "constitution": {"constitution_mode": "partnership"},
            "allocation_plan": [
                {"ownership_id": 1, "name": "Aditi", "ownership_type": "partner", "share_percentage": "60.00", "amount": "180.00", "drcr": "credit"},
                {"ownership_id": 2, "name": "Rohan", "ownership_type": "partner", "share_percentage": "40.00", "amount": "120.00", "drcr": "credit"},
            ],
        }

        journal_lines, line_meta, diagnostics = _build_close_journal_lines(
            snapshot=self._close_snapshot(income_credit="500.00", expense_debit="200.00", net_profit="300.00"),
            entity_id=58,
            entityfin_id=51,
            subentity_id=17,
            opening_policy={},
        )

        self._assert_journal_balances(journal_lines)
        equity_lines = [line for line in line_meta if line["section"] == "equity"]
        self.assertEqual([line["amount"] for line in equity_lines], ["180.00", "120.00"])
        self.assertEqual([line["drcr"] for line in equity_lines], ["credit", "credit"])
        self.assertEqual(diagnostics["equity_allocation_mode"], "ratio_split")
        self.assertEqual(diagnostics["constitution"]["constitution_mode"], "partnership")
        self.assertEqual(len(diagnostics["allocation_plan"]), 2)

    @patch("reports.services.controls.year_end_close._posted_appropriation_coverage", return_value=None)
    @patch("reports.services.controls.year_end_close.YearOpeningPostingAdapter")
    def test_close_journal_uses_company_retained_earnings_target(self, mock_opening_adapter, _mock_appropriation):
        mock_opening_adapter.return_value.build_context.return_value = {
            "equity_allocation_mode": "retained_earnings",
            "validation_issues": [],
            "equity_targets": [
                {
                    "static_account_code": "OPENING_EQUITY_TRANSFER",
                    "static_account_name": "Retained Earnings",
                    "ownership_id": None,
                    "amount": "300.00",
                    "drcr": "credit",
                    "account_id": 8081,
                    "ledger_id": 9091,
                }
            ],
            "missing_equity_codes": [],
            "constitution": {"constitution_mode": "company"},
            "allocation_plan": [],
        }

        journal_lines, line_meta, diagnostics = _build_close_journal_lines(
            snapshot=self._close_snapshot(income_credit="500.00", expense_debit="200.00", net_profit="300.00"),
            entity_id=58,
            entityfin_id=51,
            subentity_id=17,
            opening_policy={},
        )

        self._assert_journal_balances(journal_lines)
        self.assertEqual(line_meta[2]["label"], "Retained Earnings")
        self.assertEqual(line_meta[2]["drcr"], "credit")
        self.assertEqual(line_meta[2]["amount"], "300.00")
        self.assertEqual(diagnostics["equity_allocation_mode"], "retained_earnings")
        self.assertEqual(diagnostics["constitution"]["constitution_mode"], "company")

    @patch("reports.services.controls.year_end_close._posted_appropriation_coverage", return_value=None)
    @patch("reports.services.controls.year_end_close.YearOpeningPostingAdapter")
    def test_close_journal_rejects_constitution_validation_errors(self, mock_opening_adapter, _mock_appropriation):
        mock_opening_adapter.return_value.build_context.return_value = {
            "equity_allocation_mode": "ratio_split",
            "validation_issues": [
                {
                    "code": "partner_share_total",
                    "severity": "error",
                    "message": "Partner shares must total 100% before opening and allocation can proceed.",
                }
            ],
            "equity_targets": [],
            "missing_equity_codes": [],
        }

        with self.assertRaises(ValidationError) as ctx:
            _build_close_journal_lines(
                snapshot=self._close_snapshot(income_credit="500.00", expense_debit="200.00", net_profit="300.00"),
                entity_id=58,
                entityfin_id=51,
                subentity_id=17,
                opening_policy={},
            )

        self.assertEqual(
            ctx.exception.detail["detail"],
            "Year-end close cannot proceed until constitution validation passes.",
        )
        self.assertEqual(ctx.exception.detail["validation_issues"][0]["code"], "partner_share_total")

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

    @patch("reports.services.controls.year_end_close._resolve_scope")
    @patch("reports.services.controls.year_end_close._compute_snapshot")
    def test_year_end_close_preview_explains_loss_transfer_direction(self, mock_snapshot, mock_resolve):
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
                "totals": {"income": "100000.00", "expense": "125000.00", "net_profit": "-25000.00"},
                "income": [{"label": "Sales", "amount": "100000.00"}],
                "expenses": [{"label": "Rent", "amount": "125000.00"}],
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
            "checks": [],
            "summary": {
                "total_entries": 12,
                "draft_entries": 0,
                "posted_entries": 12,
                "reversed_entries": 0,
                "income_total": 100000,
                "expense_total": 125000,
                "net_profit": -25000,
                "assets_total": 150000,
                "liabilities_total": 150000,
                "balance_difference": 0,
            },
        }

        payload = build_year_end_close_preview(entity_id=58, entityfin_id=51, subentity_id=17)

        self.assertEqual(payload["source_summary"][2]["value"], "-25000.00")
        self.assertEqual(payload["source_summary"][2]["tone"], "warning")
        self.assertEqual(payload["closing_entries"][0]["direction"], "debit_pnl_credit_equity")
        self.assertEqual(payload["closing_entries"][0]["amount"], "25000.00")
        self.assertEqual(payload["closing_entries"][0]["narration"], "Move current year loss to retained earnings.")
        self.assertIn("loss is expected to reduce", payload["carry_forward_notes"][2])

    @patch("reports.services.controls.year_end_close._resolve_scope")
    @patch("reports.services.controls.year_end_close._compute_snapshot")
    def test_year_end_close_preview_reconciles_carry_forward_rows_to_permanent_accounts(self, mock_snapshot, mock_resolve):
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
                "totals": {"income": "500.00", "expense": "200.00", "net_profit": "300.00"},
                "income": [{"label": "Sales", "amount": "500.00"}],
                "expenses": [{"label": "Rent", "amount": "200.00"}],
            },
            "bs": {
                "totals": {"assets": "900.00", "liabilities_and_equity": "900.00"},
                "assets": [
                    {
                        "label": "Current Assets",
                        "amount": "0.00",
                        "children": [
                            {"label": "Bank", "amount": "750.00"},
                            {"label": "Dormant Wallet", "amount": "0.00"},
                        ],
                    },
                    {"label": "Deposits", "amount": "150.00"},
                ],
                "liabilities_and_equity": [
                    {
                        "label": "Equity",
                        "amount": "900.00",
                        "children": [{"label": "Capital", "amount": "900.00"}],
                    }
                ],
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
            "checks": [],
            "summary": {
                "total_entries": 4,
                "draft_entries": 0,
                "posted_entries": 4,
                "reversed_entries": 0,
                "income_total": 500,
                "expense_total": 200,
                "net_profit": 300,
                "assets_total": 900,
                "liabilities_total": 900,
                "balance_difference": 0,
            },
        }

        payload = build_year_end_close_preview(entity_id=58, entityfin_id=51, subentity_id=17)

        permanent_bucket = next(item for item in payload["carry_forward_buckets"] if item["key"] == "permanent_accounts")
        temporary_bucket = next(item for item in payload["carry_forward_buckets"] if item["key"] == "temporary_accounts")
        opening_bucket = next(item for item in payload["carry_forward_buckets"] if item["key"] == "opening_balance_batch")
        asset_rows = payload["opening_balance_preview"]["assets"]
        liability_rows = payload["opening_balance_preview"]["liabilities_and_equity"]
        non_zero_permanent_rows = [
            row for row in asset_rows + liability_rows
            if Decimal(str(row["amount"])) != Decimal("0.00")
        ]

        self.assertEqual(permanent_bucket["value"], len(non_zero_permanent_rows))
        self.assertEqual(permanent_bucket["value"], 4)
        self.assertEqual(temporary_bucket["value"], 2)
        self.assertEqual(opening_bucket["value"], 1)
        self.assertEqual(payload["snapshot"]["balance_sheet"]["rows"], len(asset_rows) + len(liability_rows))
        self.assertIn("4 permanent balance rows", payload["carry_forward_notes"][0])

    @patch("reports.services.controls.year_end_close.transaction.atomic", return_value=contextlib.nullcontext())
    @patch("reports.services.controls.year_end_close.PostingService")
    @patch("reports.services.controls.year_end_close._build_close_journal_lines")
    @patch("reports.services.controls.year_end_close.FinancialSettings.objects.filter")
    @patch("reports.services.controls.year_end_close.EntityFinancialYear.objects.select_for_update")
    @patch("reports.services.controls.year_end_close._compute_snapshot")
    @patch("reports.services.controls.phase_one.mandatory_close_checklist_blockers", return_value=[])
    @patch("reports.services.controls.year_end_close.build_year_end_close_preview")
    def test_year_end_close_execution_stamps_year_metadata(
        self,
        mock_preview,
        _mock_checklist_blockers,
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
        self.assertEqual(mock_posting_service_cls.call_args.kwargs["subentity_id"], 17)
        self.assertEqual(mock_posting_service_cls.return_value.post.call_args.kwargs["txn_type"], TxnType.YEAR_END_CLOSE)
        self.assertEqual(dummy_fy.metadata["year_end_close"]["scope"]["subentity_id"], 17)
        self.assertEqual(dummy_fy.metadata["year_end_close"]["scope"]["subentity_name"], "Head Office")
        self.assertEqual(dummy_fy.metadata["year_end_close"]["journal_entry"]["drilldown"]["params"]["subentity"], 17)
        self.assertEqual(dummy_fy.saved_fields, [
            "metadata",
            "period_status",
            "is_year_closed",
            "books_locked_until",
            "gst_locked_until",
            "inventory_locked_until",
            "ap_ar_locked_until",
        ])

    @patch("reports.services.controls.year_end_close.transaction.atomic", return_value=contextlib.nullcontext())
    @patch("reports.services.controls.year_end_close.PostingService")
    @patch("reports.services.controls.year_end_close._build_close_journal_lines")
    @patch("reports.services.controls.year_end_close.FinancialSettings.objects.filter")
    @patch("reports.services.controls.year_end_close.EntityFinancialYear.objects.select_for_update")
    @patch("reports.services.controls.year_end_close._compute_snapshot")
    @patch("reports.services.controls.phase_one.mandatory_close_checklist_blockers", return_value=[])
    @patch("reports.services.controls.year_end_close.build_year_end_close_preview")
    def test_year_end_close_execution_closes_zero_activity_year_without_journal(
        self,
        mock_preview,
        _mock_checklist_blockers,
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
            "checks": [],
            "book_boundary": {"from_date": None, "to_date": None, "first_posting_date": None, "last_posting_date": None},
            "carry_forward_buckets": [],
            "carry_forward_notes": ["No permanent balance rows are expected to carry forward."],
            "closing_entries": [{"label": "Transfer P&L to equity", "direction": "none", "amount": "0.00"}],
            "source_summary": [],
            "warnings": [],
            "next_steps": [],
            "snapshot": {
                "profit_loss": {"income": "0.00", "expense": "0.00", "net_profit": "0.00"},
                "balance_sheet": {"assets": "0.00", "liabilities_and_equity": "0.00", "difference": "0.00"},
            },
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
                "total_entries": 0,
                "draft_entries": 0,
                "posted_entries": 0,
                "reversed_entries": 0,
                "income_total": 0,
                "expense_total": 0,
                "net_profit": 0,
                "assets_total": 0,
                "liabilities_total": 0,
                "balance_difference": 0,
            },
        }
        mock_settings_filter.return_value.only.return_value.first.return_value = None
        mock_build_close_journal_lines.return_value = ([], [], {"net_profit": "0.00", "postable_net_profit": "0.00"})
        mock_select_for_update.return_value = DummyQuerySet(dummy_fy)

        payload = build_year_end_close_execution(entity_id=58, entityfin_id=51, subentity_id=17, executed_by=None)

        self.assertEqual(payload["status"], "success")
        self.assertTrue(dummy_fy.is_year_closed)
        self.assertEqual(dummy_fy.period_status, "closed")
        self.assertIsNone(payload["execution"]["journal_entry"])
        self.assertIsNone(dummy_fy.metadata["year_end_close"]["journal_entry"])
        self.assertEqual(dummy_fy.metadata["year_end_close"]["summary"]["net_profit"], "0.00")
        mock_posting_service_cls.assert_not_called()

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
                        "scope": {
                            "entity_id": 58,
                            "entityfin_id": 51,
                            "subentity_id": 17,
                            "entity_name": "Aditi Gupta",
                            "entityfin_name": "FY 2026-27",
                            "subentity_name": "Head Office",
                        },
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
                        "checks": [
                            {"key": "year_not_closed", "label": "Financial year is open", "status": "pass"},
                            {"key": "drafts", "label": "Draft postings", "status": "pass"},
                        ],
                        "book_boundary": {
                            "from_date": "2026-04-01",
                            "to_date": "2027-03-31",
                            "first_posting_date": "2026-04-02",
                            "last_posting_date": "2027-03-30",
                        },
                        "carry_forward_buckets": [
                            {"key": "permanent_accounts", "title": "Permanent accounts", "value": 2},
                        ],
                        "carry_forward_notes": ["2 permanent balance rows are expected to carry forward."],
                        "closing_entries": [
                            {"label": "Transfer P&L to equity", "direction": "debit_equity_credit_pnl", "amount": "25000.00"},
                        ],
                        "source_summary": [
                            {"label": "Income", "value": "125000.00", "tone": "accent"},
                            {"label": "Expense", "value": "100000.00", "tone": "neutral"},
                        ],
                        "warnings": ["Profit and loss snapshot was generated from fallback statements."],
                        "next_steps": ["Year-end close has already been executed for this scope."],
                        "snapshot": {
                            "profit_loss": {"income": "125000.00", "expense": "100000.00", "net_profit": "25000.00"},
                            "balance_sheet": {"assets": "150000.00", "liabilities_and_equity": "150000.00", "difference": "0.00"},
                        },
                        "journal_entry": {
                            "entry_id": 7001,
                            "posting_batch_id": 9001,
                            "voucher_no": "YEC-FY2026-27",
                            "posting_date": "2027-03-31",
                            "line_count": 2,
                            "lines": [
                                {"section": "income", "label": "Sales", "amount": "125000.00", "drcr": "debit"},
                                {"section": "equity", "label": "Retained Earnings", "amount": "25000.00", "drcr": "credit"},
                            ],
                            "diagnostics": {"equity_allocation_mode": "retained_earnings"},
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
        self.assertEqual(payload["close_history"]["closed_at"], "2026-04-14T10:00:00+00:00")
        self.assertEqual(payload["close_history"]["closed_on"], "2026-03-31")
        self.assertEqual(payload["close_history"]["closed_by"]["username"], "finance")
        self.assertEqual(payload["close_history"]["scope"]["subentity_name"], "Head Office")
        self.assertEqual(payload["close_history"]["summary"]["net_profit"], "25000.00")
        self.assertEqual(payload["close_history"]["checks"][0]["key"], "year_not_closed")
        self.assertEqual(payload["close_history"]["book_boundary"]["to_date"], "2027-03-31")
        self.assertEqual(payload["close_history"]["carry_forward_buckets"][0]["value"], 2)
        self.assertIn("2 permanent balance rows", payload["close_history"]["carry_forward_notes"][0])
        self.assertEqual(payload["close_history"]["closing_entries"][0]["amount"], "25000.00")
        self.assertEqual(payload["close_history"]["source_summary"][0]["label"], "Income")
        self.assertEqual(payload["close_history"]["snapshot"]["profit_loss"]["net_profit"], "25000.00")
        self.assertEqual(payload["close_history"]["warnings"][0], "Profit and loss snapshot was generated from fallback statements.")
        self.assertEqual(payload["close_history"]["next_steps"][0], "Year-end close has already been executed for this scope.")
        self.assertEqual(payload["close_history"]["journal_entry"]["voucher_no"], "YEC-FY2026-27")
        self.assertEqual(payload["close_history"]["journal_entry"]["line_count"], 2)
        self.assertEqual(payload["close_history"]["journal_entry"]["lines"][1]["label"], "Retained Earnings")
        self.assertEqual(payload["close_history"]["journal_entry"]["diagnostics"]["equity_allocation_mode"], "retained_earnings")
        self.assertEqual(payload["close_history"]["journal_entry"]["drilldown"]["target"], "posting_detail")
        self.assertEqual(payload["close_history"]["journal_entry"]["drilldown"]["route"], "/reports/financial/posting-detail/:entry_id")
        self.assertEqual(payload["close_history"]["journal_entry"]["drilldown"]["label"], "Open close journal")
        self.assertEqual(payload["close_history"]["journal_entry"]["drilldown"]["params"]["entry_id"], 7001)
        self.assertEqual(payload["close_history"]["journal_entry"]["drilldown"]["params"]["entity"], 58)
        self.assertEqual(payload["close_history"]["journal_entry"]["drilldown"]["params"]["entityfinid"], 51)
        self.assertEqual(payload["close_history"]["journal_entry"]["drilldown"]["params"]["subentity"], 17)
        self.assertEqual(payload["journal_entry"]["drilldown"]["params"]["subentity"], 17)

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

    @patch("reports.services.controls.phase_one.mandatory_close_checklist_blockers")
    @patch("reports.services.controls.year_end_close.build_year_end_close_preview")
    def test_year_end_close_execution_returns_structured_checklist_blockers(self, mock_preview, mock_blockers):
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
                "readiness_state": "ready",
            }
        }
        mock_blockers.return_value = [
            {
                "key": "bank_reconciliation_gate",
                "label": "Bank reconciliation complete",
                "detail": "Resolve unmatched bank/book lines before close.",
                "extra": "not exposed",
            },
            {
                "key": "approval_gate",
                "label": "Approvals cleared",
                "detail": "Submitted vouchers must be approved or rejected.",
            },
        ]

        with self.assertRaises(ValidationError) as ctx:
            build_year_end_close_execution(entity_id=58, entityfin_id=51, subentity_id=17, executed_by=None)

        self.assertEqual(
            ctx.exception.detail["detail"],
            "Mandatory close checklist blockers must be cleared before year-end close execution.",
        )
        self.assertEqual(
            ctx.exception.detail["checklist_blockers"],
            [
                {
                    "key": "bank_reconciliation_gate",
                    "label": "Bank reconciliation complete",
                    "detail": "Resolve unmatched bank/book lines before close.",
                },
                {
                    "key": "approval_gate",
                    "label": "Approvals cleared",
                    "detail": "Submitted vouchers must be approved or rejected.",
                },
            ],
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

    @patch("reports.services.controls.year_end_close.transaction.atomic", return_value=contextlib.nullcontext())
    @patch("reports.services.controls.opening_preview._resolve_destination_year")
    @patch("reports.services.controls.year_end_close.EntityFinancialYear.objects.select_for_update")
    @patch("reports.services.controls.year_end_close._resolve_scope")
    def test_year_end_close_rollback_denied_when_next_year_opening_exists(
        self,
        mock_resolve_scope,
        mock_select_for_update,
        mock_resolve_destination_year,
        _mock_atomic,
    ):
        class DummyFinancialYear:
            def __init__(self, year_id, metadata=None):
                self.id = year_id
                self.pk = year_id
                self.metadata = metadata or {}
                self.period_status = "closed"
                self.is_year_closed = True

        class DummyQuerySet:
            def __init__(self, rows):
                self.rows = rows
                self.filters = {}

            def filter(self, **kwargs):
                clone = DummyQuerySet(self.rows)
                clone.filters = kwargs
                return clone

            def first(self):
                pk = self.filters.get("pk")
                return self.rows.get(pk)

        source_fy = DummyFinancialYear(
            51,
            metadata={
                "year_end_close": {
                    "scope": {"entityfin_id": 51},
                    "previous_state": {"period_status": "open", "is_year_closed": False},
                    "journal_entry": {"entry_id": 7001},
                }
            },
        )
        destination_fy = DummyFinancialYear(
            52,
            metadata={
                "opening_carry_forward": {
                    "source_year": {"id": 51},
                    "batch": {"entry_id": 8001},
                }
            },
        )
        mock_resolve_scope.return_value = {"entityfin_object": source_fy}
        mock_select_for_update.return_value = DummyQuerySet({51: source_fy, 52: destination_fy})
        mock_resolve_destination_year.return_value = {"id": 52}

        with self.assertRaises(ValidationError) as ctx:
            build_year_end_close_rollback(entity_id=58, entityfin_id=51, subentity_id=17, executed_by=None)

        self.assertEqual(
            ctx.exception.detail,
            {"detail": "Opening carry-forward already exists for the next financial year. Roll back opening generation first."},
        )
