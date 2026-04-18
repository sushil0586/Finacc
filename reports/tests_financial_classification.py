from types import SimpleNamespace
from django.test import SimpleTestCase

from reports.services.financial.classification import classify_financial_head


class FinancialClassificationTests(SimpleTestCase):
    def _head(self, *, detailsingroup=None, drcreffect="Debit", balance_type="Debit"):
        account_type = SimpleNamespace(
            accounttypename="Direct Expenses",
            accounttypecode="5200",
            balanceType=balance_type,
        )
        return SimpleNamespace(
            name="Direct Expenses",
            code="8300",
            detailsingroup=detailsingroup,
            drcreffect=drcreffect,
            balanceType=drcreffect,
            accounttype=account_type,
        )

    def test_group_one_routes_to_trading(self):
        head = self._head(detailsingroup=1)
        classification = classify_financial_head(head, head.accounttype)

        self.assertTrue(classification.include_in_trading)
        self.assertFalse(classification.include_in_profit_loss)
        self.assertFalse(classification.include_in_balance_sheet)

    def test_group_two_routes_to_profit_loss(self):
        head = self._head(detailsingroup=2)
        classification = classify_financial_head(head, head.accounttype)

        self.assertFalse(classification.include_in_trading)
        self.assertTrue(classification.include_in_profit_loss)
        self.assertFalse(classification.include_in_balance_sheet)
        self.assertEqual(classification.profit_loss_side, "expense")

    def test_group_three_routes_to_balance_sheet(self):
        head = self._head(detailsingroup=3)
        classification = classify_financial_head(head, head.accounttype)

        self.assertFalse(classification.include_in_trading)
        self.assertFalse(classification.include_in_profit_loss)
        self.assertTrue(classification.include_in_balance_sheet)

    def test_missing_group_falls_back_to_trading_for_direct_expense(self):
        head = self._head(detailsingroup=None)
        classification = classify_financial_head(head, head.accounttype)

        self.assertTrue(classification.include_in_trading)
        self.assertFalse(classification.include_in_profit_loss)
        self.assertFalse(classification.include_in_balance_sheet)
