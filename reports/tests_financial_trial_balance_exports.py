from django.http import QueryDict
from django.test import SimpleTestCase

from reports.api.financial.views import _filtered_querydict, _trial_balance_subtitle, _truncate_text


class TrialBalanceExportHelperTests(SimpleTestCase):
    def test_trial_balance_subtitle_uses_scope_names_and_filters(self):
        subtitle = _trial_balance_subtitle(
            {
                "entity_name": "Acme Pvt Ltd",
                "entityfin_name": "FY 2025-26",
                "subentity_name": "Mumbai Branch",
            },
            {
                "subentity": 17,
                "scope_mode": "custom",
                "account_group": "accounthead",
                "view_type": "detailed",
                "posted_only": False,
            },
        )

        self.assertIn("Entity: Acme Pvt Ltd", subtitle)
        self.assertIn("FY: FY 2025-26", subtitle)
        self.assertIn("Subentity: Mumbai Branch", subtitle)
        self.assertIn("Scope: custom", subtitle)
        self.assertIn("Group by: accounthead", subtitle)
        self.assertIn("View: detailed", subtitle)
        self.assertIn("Posted only: False", subtitle)

    def test_trial_balance_subtitle_falls_back_to_subentity_id(self):
        subtitle = _trial_balance_subtitle(
            {
                "entity_name": None,
                "entityfin_name": None,
                "subentity_name": None,
            },
            {
                "subentity": 17,
            },
        )

        self.assertIn("Entity: Selected entity", subtitle)
        self.assertIn("FY: Current FY", subtitle)
        self.assertIn("Subentity: Subentity 17", subtitle)

    def test_filtered_querydict_keeps_current_filters(self):
        request = type("Req", (), {
            "GET": QueryDict("entity=1&entityfinid=2&subentity=3&from_date=2025-04-01&to_date=2025-04-30&page=4&page_size=50")
        })()
        query = _filtered_querydict(request, exclude=["page", "page_size"])

        self.assertIn("entity=1", query)
        self.assertIn("entityfinid=2", query)
        self.assertIn("subentity=3", query)
        self.assertIn("from_date=2025-04-01", query)
        self.assertIn("to_date=2025-04-30", query)
        self.assertNotIn("page=4", query)
        self.assertNotIn("page_size=50", query)

    def test_truncate_text_shortens_long_strings(self):
        text = "This is a very long ledger name that should not overlap nearby PDF columns"
        truncated = _truncate_text(text, 60)

        self.assertLess(len(truncated), len(text))
        self.assertTrue(truncated.endswith("..."))

    def test_truncate_text_leaves_short_values_as_is(self):
        self.assertEqual(_truncate_text("Trial Balance", 120), "Trial Balance")
