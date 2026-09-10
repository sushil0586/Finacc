from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.models import accountHead
from posting.models import Entry, JournalLine, TxnType
from posting.services.posting_service import JLInput
from reports.services.controls.opening_generation import build_opening_generation, build_opening_generation_rollback
from reports.services.controls.opening_setup import apply_posting_setup
from reports.services.controls.year_end_close import build_year_end_close_execution, build_year_end_close_rollback


class FinancialControlsDestructiveWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="controls-destructive-user",
            email="controls-destructive@example.com",
            password="pass123",
        )
        cls.entity = Entity.objects.create(entityname="Disposable Controls Certification", createdby=cls.user)
        cls.subentity = SubEntity.objects.create(
            entity=cls.entity,
            subentityname="Certification Head Office",
            is_head_office=True,
            branch_type=SubEntity.BranchType.HEAD_OFFICE,
        )
        cls.debit_head = accountHead.objects.create(name="Certification Debit", code=98101)
        cls.credit_head = accountHead.objects.create(name="Certification Credit", code=98102)

    @staticmethod
    def _aware(year: int, month: int, day: int):
        return timezone.make_aware(datetime(year, month, day))

    def _financial_year(self, *, code: str, start: tuple[int, int, int], end: tuple[int, int, int], **kwargs):
        return EntityFinancialYear.objects.create(
            entity=self.entity,
            desc=f"FY {code.removeprefix('FY')}",
            year_code=code,
            finstartyear=self._aware(*start),
            finendyear=self._aware(*end),
            createdby=self.user,
            **kwargs,
        )

    def _balanced_lines(self, amount: str = "1250.50"):
        value = Decimal(amount)
        return [
            JLInput(accounthead_id=self.debit_head.id, drcr=True, amount=value, description="Certification debit"),
            JLInput(accounthead_id=self.credit_head.id, drcr=False, amount=value, description="Certification credit"),
        ]

    def test_year_close_posts_balanced_entry_prevents_duplicate_and_rolls_back(self):
        fy = self._financial_year(code="FY2025-26", start=(2025, 4, 1), end=(2026, 3, 31), isactive=True)
        preview = {
            "entity_name": self.entity.entityname,
            "entityfin_name": fy.desc,
            "subentity_name": self.subentity.subentityname,
            "checks": [],
            "book_boundary": {},
            "carry_forward_buckets": [],
            "carry_forward_notes": [],
            "closing_entries": [],
            "source_summary": [],
            "warnings": [],
            "next_steps": [],
            "snapshot": {},
            "close_state": {
                "period_status": EntityFinancialYear.PeriodStatus.OPEN,
                "is_year_closed": False,
                "readiness_state": "ready",
            },
        }
        snapshot = {
            "financial_year": fy,
            "summary": {
                "total_entries": 0,
                "draft_entries": 0,
                "posted_entries": 0,
                "reversed_entries": 0,
                "income_total": Decimal("1250.50"),
                "expense_total": Decimal("0.00"),
                "net_profit": Decimal("1250.50"),
                "assets_total": Decimal("1250.50"),
                "liabilities_total": Decimal("1250.50"),
                "balance_difference": Decimal("0.00"),
            },
        }
        line_meta = [
            {"section": "profit_loss", "label": "Certification transfer", "amount": "1250.50", "drcr": "debit"},
            {"section": "equity", "label": "Retained earnings", "amount": "1250.50", "drcr": "credit"},
        ]

        with (
            patch("reports.services.controls.year_end_close.build_year_end_close_preview", return_value=preview),
            patch("reports.services.controls.year_end_close._compute_snapshot", return_value=snapshot),
            patch("reports.services.controls.year_end_close._build_close_journal_lines", return_value=(self._balanced_lines(), line_meta, {})),
            patch("reports.services.controls.year_end_close.FinancialSettings.objects.filter") as settings_filter,
        ):
            settings_filter.return_value.only.return_value.first.return_value = None
            result = build_year_end_close_execution(
                entity_id=self.entity.id,
                entityfin_id=fy.id,
                subentity_id=self.subentity.id,
                executed_by=self.user,
            )
            with self.assertRaisesMessage(ValidationError, "already closed"):
                build_year_end_close_execution(
                    entity_id=self.entity.id,
                    entityfin_id=fy.id,
                    subentity_id=self.subentity.id,
                    executed_by=self.user,
                )

        fy.refresh_from_db()
        self.assertEqual(result["status"], "success")
        self.assertTrue(fy.is_year_closed)
        self.assertEqual(fy.period_status, EntityFinancialYear.PeriodStatus.CLOSED)
        self.assertEqual(fy.books_locked_until.isoformat(), "2026-03-31")
        self.assertEqual(fy.gst_locked_until, fy.books_locked_until)
        self.assertEqual(fy.inventory_locked_until, fy.books_locked_until)
        self.assertEqual(fy.ap_ar_locked_until, fy.books_locked_until)

        entry = Entry.objects.get(entity=self.entity, entityfin=fy, subentity=self.subentity, txn_type=TxnType.YEAR_END_CLOSE)
        lines = JournalLine.objects.filter(entry=entry)
        self.assertEqual(lines.filter(drcr=True).count(), 1)
        self.assertEqual(lines.filter(drcr=False).count(), 1)
        self.assertEqual(sum(lines.filter(drcr=True).values_list("amount", flat=True)), Decimal("1250.50"))
        self.assertEqual(sum(lines.filter(drcr=False).values_list("amount", flat=True)), Decimal("1250.50"))

        rollback = build_year_end_close_rollback(
            entity_id=self.entity.id,
            entityfin_id=fy.id,
            subentity_id=self.subentity.id,
            executed_by=self.user,
        )
        fy.refresh_from_db()
        self.assertEqual(rollback["status"], "success")
        self.assertFalse(fy.is_year_closed)
        self.assertEqual(fy.period_status, EntityFinancialYear.PeriodStatus.OPEN)
        self.assertIsNone(fy.books_locked_until)
        self.assertFalse(Entry.objects.filter(pk=entry.pk).exists())
        self.assertNotIn("year_end_close", fy.metadata)
        self.assertEqual(len(fy.metadata["year_end_close_rollbacks"]), 1)

        with self.assertRaisesMessage(ValidationError, "No year-end close history"):
            build_year_end_close_rollback(
                entity_id=self.entity.id,
                entityfin_id=fy.id,
                subentity_id=self.subentity.id,
                executed_by=self.user,
            )

    def test_opening_generation_posts_balanced_entry_prevents_duplicate_and_rolls_back(self):
        source = self._financial_year(
            code="FY2024-25",
            start=(2024, 4, 1),
            end=(2025, 3, 31),
            period_status=EntityFinancialYear.PeriodStatus.CLOSED,
            is_year_closed=True,
            isactive=True,
        )
        destination = self._financial_year(
            code="FY2025-26",
            start=(2025, 4, 1),
            end=(2026, 3, 31),
            isactive=False,
        )
        preview = {
            "actions": {"can_generate": True},
            "opening_history": None,
            "source_year": {"is_closed": True},
            "destination_year": {"id": destination.id},
            "opening_policy": {"require_closed_source_year": True},
        }
        snapshot = {"financial_year": source}
        policy = {"require_closed_source_year": True}
        line_meta = [
            {"section": "assets", "label": "Opening asset", "amount": "900.25", "drcr": "debit"},
            {"section": "liabilities", "label": "Opening liability", "amount": "900.25", "drcr": "credit"},
        ]
        summary = {
            "sections": {"assets": 1, "liabilities": 1, "inventory": 0, "equity": 0},
            "net_profit": Decimal("0.00"),
            "diagnostics": {},
        }

        with (
            patch("reports.services.controls.opening_generation.build_opening_preview", return_value=preview) as preview_mock,
            patch("reports.services.controls.opening_generation._compute_snapshot", return_value=snapshot),
            patch("reports.services.controls.opening_generation.resolve_opening_policy", return_value=policy),
            patch("reports.services.controls.opening_generation._resolve_destination_fy", return_value=destination),
            patch("reports.services.controls.opening_generation._build_opening_lines", return_value=(self._balanced_lines("900.25"), line_meta, summary)),
        ):
            result = build_opening_generation(
                entity_id=self.entity.id,
                entityfin_id=source.id,
                subentity_id=self.subentity.id,
                executed_by=self.user,
            )
            with self.assertRaisesMessage(ValidationError, "already exists"):
                build_opening_generation(
                    entity_id=self.entity.id,
                    entityfin_id=source.id,
                    subentity_id=self.subentity.id,
                    executed_by=self.user,
                )

            destination.refresh_from_db()
            opening_history = destination.metadata["opening_carry_forward"]
            preview_mock.return_value = {
                "opening_history": opening_history,
                "destination_year": {"id": destination.id},
            }
            rollback = build_opening_generation_rollback(
                entity_id=self.entity.id,
                entityfin_id=source.id,
                subentity_id=self.subentity.id,
                executed_by=self.user,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(rollback["status"], "success")
        entry_query = Entry.objects.filter(
            entity=self.entity,
            entityfin=destination,
            subentity=self.subentity,
            txn_type=TxnType.OPENING_BALANCE,
        )
        self.assertFalse(entry_query.exists())
        destination.refresh_from_db()
        self.assertNotIn("opening_carry_forward", destination.metadata)
        self.assertEqual(len(destination.metadata["opening_carry_forward_rollbacks"]), 1)
        source.refresh_from_db()
        self.assertTrue(source.isactive)
        self.assertFalse(destination.isactive)

        with patch("reports.services.controls.opening_generation.build_opening_preview", return_value={"opening_history": None}):
            with self.assertRaisesMessage(ValidationError, "No opening carry-forward history"):
                build_opening_generation_rollback(
                    entity_id=self.entity.id,
                    entityfin_id=source.id,
                    subentity_id=self.subentity.id,
                    executed_by=self.user,
                )

    @patch("reports.services.controls.opening_setup.StaticAccountService.invalidate")
    @patch("reports.services.controls.opening_setup.build_posting_setup_preview", return_value={"preview_state": "applied"})
    @patch("reports.services.controls.opening_setup._apply_target")
    @patch("reports.services.controls.opening_setup._proposal_targets")
    @patch("reports.services.controls.opening_setup.resolve_opening_policy", return_value={})
    def test_posting_setup_excludes_disabled_targets_from_applied_result(
        self,
        _policy,
        proposal_targets,
        apply_target,
        _preview,
        _invalidate,
    ):
        proposal_targets.return_value = (
            {"constitution_mode": "company", "ownership_rows": [], "validation_issues": []},
            [
                {"code": "OPENING_EQUITY_TRANSFER", "kind": "equity", "enabled": True},
                {"code": "OPENING_INVENTORY_CARRY_FORWARD", "kind": "inventory", "enabled": True},
            ],
        )
        apply_target.side_effect = [
            {
                "code": "OPENING_EQUITY_TRANSFER",
                "static_created": True,
                "ledger_created": True,
                "mapping_created": True,
                "mapping_updated": False,
            }
        ]

        result = apply_posting_setup(
            entity_id=self.entity.id,
            target_overrides=[{"code": "OPENING_INVENTORY_CARRY_FORWARD", "enabled": False}],
            created_by=self.user,
        )

        self.assertEqual(apply_target.call_count, 1)
        self.assertEqual(result["applied"]["touched_codes"], ["OPENING_EQUITY_TRANSFER"])
        self.assertEqual(result["applied"]["skipped_codes"], ["OPENING_INVENTORY_CARRY_FORWARD"])
        self.assertEqual(result["applied"]["created_ledgers"], 1)
