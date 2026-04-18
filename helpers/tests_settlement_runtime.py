from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from helpers.utils.settlement_runtime import SettlementVoucherRuntimeMixin


class DummySettlementRuntime(SettlementVoucherRuntimeMixin):
    pass


class SettlementVoucherRuntimeMixinTests(SimpleTestCase):
    def test_normalize_allocations_merges_duplicate_open_items(self):
        rows = DummySettlementRuntime._normalize_allocations(
            [
                {"open_item": 11, "settled_amount": Decimal("10.00"), "is_full_settlement": False},
                {"open_item": 11, "settled_amount": Decimal("2.50"), "is_full_settlement": True},
                {"open_item": 12, "settled_amount": Decimal("3.00")},
            ]
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["open_item"], 11)
        self.assertEqual(rows[0]["settled_amount"], Decimal("12.50"))
        self.assertTrue(rows[0]["is_full_settlement"])

    def test_workflow_state_defaults_and_audit_append(self):
        state = DummySettlementRuntime._workflow_state(None)
        self.assertEqual(state["status"], "DRAFT")

        payload = DummySettlementRuntime._append_audit(None, {"action": "CONFIRMED"})
        self.assertEqual(payload["_audit_log"], [{"action": "CONFIRMED"}])

        payload = DummySettlementRuntime._set_workflow_state(payload, {"status": "APPROVED"})
        self.assertEqual(payload["_approval_state"], {"status": "APPROVED"})

    def test_compute_adjustment_total_applies_plus_minus_effects(self):
        total = DummySettlementRuntime._compute_adjustment_total(
            [
                {"amount": Decimal("10.00"), "settlement_effect": "PLUS"},
                {"amount": Decimal("4.50"), "settlement_effect": "MINUS"},
            ]
        )

        self.assertEqual(total, Decimal("5.50"))
