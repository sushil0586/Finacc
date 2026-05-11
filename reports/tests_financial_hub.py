from django.test import SimpleTestCase

from reports.schemas.financial_reports import FinancialReportScopeSerializer
from reports.services.financial.meta import _report_registry
from reports.services.financial.registry import build_financial_hub
from reports.services.financial.reporting_policy import _sanitize


class FinancialHubRegistryTests(SimpleTestCase):
    def test_financial_hub_groups_core_reports(self):
        hub = build_financial_hub(_report_registry())

        self.assertEqual(hub["version"], "2026-04")
        self.assertEqual(hub["default_report_code"], "trial_balance")
        self.assertEqual(hub["featured_reports"], [
            "trial_balance",
            "ledger_book",
            "profit_loss",
            "balance_sheet",
            "trading_account",
            "daybook",
            "cashbook",
            "controls_phase_one",
            "year_end_close",
        ])
        self.assertEqual([section["tag"] for section in hub["sections"]], ["Statements", "Statements", "Books", "Utilities"])

        all_codes = [
            report["code"]
            for section in hub["sections"]
            for report in section["reports"]
        ]
        self.assertEqual(
            all_codes,
            [
                "trial_balance",
                "ledger_book",
                "profit_loss",
                "balance_sheet",
                "trading_account",
                "daybook",
                "cashbook",
                "controls_phase_one",
                "year_end_close",
            ],
        )

    def test_reporting_policy_sanitizes_financial_hub_settings(self):
        policy = _sanitize(
            {
                "financial_hub": {
                    "default_report_code": " Trial_Balance ",
                    "enabled_reports": ("trial_balance", "ledger_book"),
                    "featured_reports": ("trial_balance", "cashbook"),
                },
                "profit_loss": {
                    "accounting_only_notes_disclosure": "invalid",
                    "accounting_only_notes_split": "wrong",
                },
                "balance_sheet": {},
            }
        )

        self.assertEqual(policy["financial_hub"]["default_report_code"], "trial_balance")
        self.assertEqual(policy["financial_hub"]["enabled_reports"], ["trial_balance", "ledger_book"])
        self.assertEqual(policy["financial_hub"]["featured_reports"], ["trial_balance", "cashbook"])
        self.assertEqual(policy["profit_loss"]["accounting_only_notes_disclosure"], "summary")
        self.assertEqual(policy["profit_loss"]["accounting_only_notes_split"], "purchase_sales")
        self.assertTrue(policy["balance_sheet"]["include_accounting_only_notes_disclosure"])

    def test_reporting_policy_includes_opening_defaults(self):
        policy = _sanitize({})

        self.assertEqual(policy["opening"]["opening_mode"], "hybrid")
        self.assertEqual(policy["opening"]["batch_materialization"], "single_batch")
        self.assertEqual(policy["opening"]["opening_posting_date_strategy"], "first_day_of_new_year")
        self.assertTrue(policy["opening"]["require_closed_source_year"])
        self.assertFalse(policy["opening"]["allow_partial_opening"])
        self.assertEqual(policy["opening"]["grouped_sections"], ["assets", "liabilities", "stock", "equity"])
        self.assertTrue(policy["opening"]["carry_forward"]["cash_bank"])
        self.assertTrue(policy["opening"]["reset"]["trading"])

    def test_statement_presentation_is_available_for_financial_statements(self):
        reports = {report["code"]: report for report in _report_registry()}

        self.assertTrue(reports["profit_loss"]["supports"]["presentation"])
        self.assertTrue(reports["balance_sheet"]["supports"]["presentation"])
        self.assertTrue(reports["trading_account"]["supports"]["presentation"])


class FinancialReportScopeSerializerTests(SimpleTestCase):
    def test_defaults_presentation_to_standard(self):
        serializer = FinancialReportScopeSerializer(data={"entity": 10})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["presentation"], "standard")

    def test_accepts_statement_presentation(self):
        serializer = FinancialReportScopeSerializer(data={"entity": 10, "presentation": "statement"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["presentation"], "statement")
