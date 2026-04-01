"""
Tests for posting service layer.
Covers: q2/q4 rounding, PostingService.post(), balance assertions, re-posting,
        ledger_balance_map aggregation.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from entity.models import Entity
from financial.models import accountHead
from posting.models import Entry, EntryStatus, JournalLine, PostingBatch
from posting.services.balances import ledger_balance_map
from posting.services.posting_service import (
    JLInput,
    PostingService,
    ZERO2,
    q2,
    q4,
)

User = get_user_model()

TODAY = date(2025, 4, 1)


# ---------------------------------------------------------------------------
# Pure rounding helpers — no DB required
# ---------------------------------------------------------------------------

class Q2RoundingTests(SimpleTestCase):

    def test_rounds_to_two_decimal_places(self):
        self.assertEqual(q2("100.555"), Decimal("100.56"))

    def test_rounds_half_up(self):
        self.assertEqual(q2("0.005"), Decimal("0.01"))

    def test_none_returns_zero(self):
        self.assertEqual(q2(None), ZERO2)

    def test_empty_string_returns_zero(self):
        self.assertEqual(q2(""), ZERO2)

    def test_integer_input(self):
        self.assertEqual(q2(100), Decimal("100.00"))

    def test_already_quantized_unchanged(self):
        self.assertEqual(q2("99.99"), Decimal("99.99"))


class Q4RoundingTests(SimpleTestCase):

    def test_rounds_to_four_decimal_places(self):
        self.assertEqual(q4("1.23456"), Decimal("1.2346"))

    def test_none_returns_zero(self):
        self.assertEqual(q4(None), Decimal("0.0000"))

    def test_integer_input(self):
        self.assertEqual(q4(5), Decimal("5.0000"))


# ---------------------------------------------------------------------------
# PostingService — DB tests
# ---------------------------------------------------------------------------

class PostingServiceBaseTest(TestCase):
    """Shared fixtures for posting service tests."""

    @classmethod
    def setUpTestData(cls):
        cls.entity = Entity.objects.create(entityname="Test Co")
        cls.ah_dr = accountHead.objects.create(name="Test Dr Head", code=9001)
        cls.ah_cr = accountHead.objects.create(name="Test Cr Head", code=9002)
        cls.svc = PostingService(
            entity_id=cls.entity.id,
            entityfin_id=None,
            subentity_id=None,
        )

    def _balanced_jl(self, amount="1000.00"):
        """Return a minimal balanced pair of JLInputs (accounthead-based, no ledger needed)."""
        amt = Decimal(amount)
        return [
            JLInput(accounthead_id=self.ah_dr.id, drcr=True,  amount=amt, description="Dr"),
            JLInput(accounthead_id=self.ah_cr.id, drcr=False, amount=amt, description="Cr"),
        ]

    def _post(self, txn_id=1, amount="1000.00", **kwargs):
        return self.svc.post(
            txn_type="JV",
            txn_id=txn_id,
            voucher_no=f"JV-{txn_id}",
            voucher_date=TODAY,
            posting_date=TODAY,
            jl_inputs=self._balanced_jl(amount),
            use_advisory_lock=False,
            **kwargs,
        )


class PostingServicePostTests(PostingServiceBaseTest):

    def test_balanced_post_creates_entry(self):
        entry = self._post()
        self.assertIsNotNone(entry.pk)
        self.assertEqual(entry.status, EntryStatus.POSTED)

    def test_balanced_post_creates_two_journal_lines(self):
        entry = self._post(txn_id=10)
        lines = JournalLine.objects.filter(entry=entry)
        self.assertEqual(lines.count(), 2)

    def test_balanced_post_creates_active_batch(self):
        self._post(txn_id=20)
        batch = PostingBatch.objects.get(entity_id=self.entity.id, txn_type="JV", txn_id=20)
        self.assertTrue(batch.is_active)

    def test_draft_post_sets_draft_status(self):
        entry = self._post(txn_id=30, mark_posted=False)
        self.assertEqual(entry.status, EntryStatus.DRAFT)

    def test_zero_amount_line_is_skipped(self):
        jl = [
            JLInput(accounthead_id=self.ah_dr.id, drcr=True,  amount=Decimal("500.00")),
            JLInput(accounthead_id=self.ah_cr.id, drcr=False, amount=Decimal("500.00")),
            JLInput(accounthead_id=self.ah_dr.id, drcr=True,  amount=Decimal("0.00")),   # skipped
        ]
        entry = self.svc.post(
            txn_type="JV", txn_id=40,
            voucher_no="JV-40", voucher_date=TODAY, posting_date=TODAY,
            jl_inputs=jl, use_advisory_lock=False,
        )
        lines = JournalLine.objects.filter(entry=entry)
        self.assertEqual(lines.count(), 2)

    def test_unbalanced_post_raises_value_error(self):
        jl = [
            JLInput(accounthead_id=self.ah_dr.id, drcr=True,  amount=Decimal("1000.00")),
            JLInput(accounthead_id=self.ah_cr.id, drcr=False, amount=Decimal("999.00")),  # off by 1
        ]
        with self.assertRaises(ValueError):
            self.svc.post(
                txn_type="JV", txn_id=50,
                voucher_no="JV-50", voucher_date=TODAY, posting_date=TODAY,
                jl_inputs=jl, use_advisory_lock=False,
            )

    def test_both_account_and_accounthead_raises(self):
        jl = [
            JLInput(account_id=1, accounthead_id=self.ah_dr.id, drcr=True,  amount=Decimal("500.00")),
            JLInput(accounthead_id=self.ah_cr.id,               drcr=False, amount=Decimal("500.00")),
        ]
        with self.assertRaises(ValueError):
            self.svc.post(
                txn_type="JV", txn_id=60,
                voucher_no="JV-60", voucher_date=TODAY, posting_date=TODAY,
                jl_inputs=jl, use_advisory_lock=False,
            )

    def test_neither_account_nor_accounthead_raises(self):
        jl = [
            JLInput(drcr=True,  amount=Decimal("500.00")),
            JLInput(drcr=False, amount=Decimal("500.00")),
        ]
        with self.assertRaises(ValueError):
            self.svc.post(
                txn_type="JV", txn_id=70,
                voucher_no="JV-70", voucher_date=TODAY, posting_date=TODAY,
                jl_inputs=jl, use_advisory_lock=False,
            )


class RePostingTests(PostingServiceBaseTest):
    """Re-posting the same txn should replace lines and deactivate old batch."""

    def test_repost_deactivates_previous_batch(self):
        self._post(txn_id=100)
        self._post(txn_id=100, amount="2000.00")

        batches = PostingBatch.objects.filter(
            entity_id=self.entity.id, txn_type="JV", txn_id=100
        )
        self.assertEqual(batches.count(), 2)
        self.assertEqual(batches.filter(is_active=True).count(), 1)
        self.assertEqual(batches.filter(is_active=False).count(), 1)

    def test_repost_replaces_journal_lines(self):
        entry1 = self._post(txn_id=101, amount="1000.00")
        entry2 = self._post(txn_id=101, amount="2000.00")

        # Same entry pk (update_or_create)
        self.assertEqual(entry1.pk, entry2.pk)

        # Lines reflect the latest amount
        lines = JournalLine.objects.filter(
            entity_id=self.entity.id, txn_type="JV", txn_id=101
        )
        self.assertEqual(lines.count(), 2)
        self.assertTrue(all(l.amount == Decimal("2000.00") for l in lines))

    def test_repost_increments_revision(self):
        self._post(txn_id=102)
        self._post(txn_id=102, amount="1500.00")

        revisions = list(
            PostingBatch.objects.filter(
                entity_id=self.entity.id, txn_type="JV", txn_id=102
            ).order_by("revision").values_list("revision", flat=True)
        )
        self.assertEqual(revisions, [1, 2])


# ---------------------------------------------------------------------------
# ledger_balance_map
# ---------------------------------------------------------------------------

class LedgerBalanceMapTests(PostingServiceBaseTest):
    """
    Verify ledger_balance_map aggregation.
    JournalLines are posted with accounthead_id only (no ledger FK).
    balance_map filters ledger_id__isnull=False, so lines without a resolved
    ledger won't appear — we test the empty-result / entity-isolation cases.
    """

    def test_outside_date_range_returns_empty(self):
        self._post(txn_id=200)
        result = ledger_balance_map(
            entity_id=self.entity.id,
            fin_start=date(2024, 1, 1),
            fin_end=date(2024, 12, 31),   # previous year — no matches
        )
        self.assertEqual(result, {})

    def test_different_entity_returns_empty(self):
        self._post(txn_id=201)
        other_entity = Entity.objects.create(entityname="Other Co")
        result = ledger_balance_map(
            entity_id=other_entity.id,
            fin_start=date(2025, 1, 1),
            fin_end=date(2025, 12, 31),
        )
        self.assertEqual(result, {})

    def test_returns_dict(self):
        self._post(txn_id=202)
        result = ledger_balance_map(
            entity_id=self.entity.id,
            fin_start=date(2025, 1, 1),
            fin_end=date(2025, 12, 31),
        )
        self.assertIsInstance(result, dict)
