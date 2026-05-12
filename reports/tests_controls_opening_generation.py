from __future__ import annotations

import contextlib
from datetime import datetime

from django.test import SimpleTestCase
from unittest.mock import patch

from reports.services.controls.opening_generation import build_opening_generation, build_opening_generation_rollback


class OpeningGenerationTests(SimpleTestCase):
    @staticmethod
    def _source_year():
        class DummySourceFY:
            def __init__(self):
                self.id = 51
                self.pk = 51
                self.desc = "FY 2026-27"
                self.year_code = "FY2026-27"
                self.finstartyear = datetime(2026, 4, 1)
                self.finendyear = datetime(2027, 3, 31)
                self.period_status = "closed"
                self.is_year_closed = True
                self.is_audit_closed = False
                self.isactive = True
                self.metadata = {}
                self.saved_fields = None

            def save(self, update_fields=None):
                self.saved_fields = update_fields

        return DummySourceFY()

    @staticmethod
    def _destination_year():
        class DummyDestinationFY:
            def __init__(self):
                self.id = 52
                self.pk = 52
                self.desc = "FY 2027-28"
                self.year_code = "FY2027-28"
                self.finstartyear = datetime(2027, 4, 1)
                self.finendyear = datetime(2028, 3, 31)
                self.period_status = "open"
                self.is_year_closed = False
                self.is_audit_closed = False
                self.isactive = False
                self.metadata = {}
                self.saved_fields = None

            def save(self, update_fields=None):
                self.saved_fields = update_fields

        return DummyDestinationFY()

    @patch("reports.services.controls.opening_generation.timezone.now")
    @patch("reports.services.controls.opening_generation.PostingService")
    @patch("reports.services.controls.opening_generation._resolve_destination_fy")
    @patch("reports.services.controls.opening_generation.StaticAccountService.get_account_id")
    @patch("reports.services.controls.opening_generation.StaticAccountService.get_ledger_id")
    @patch("reports.services.controls.opening_generation.resolve_opening_policy")
    @patch("reports.services.controls.opening_generation._compute_snapshot")
    @patch("reports.services.controls.opening_generation.build_opening_preview")
    @patch("reports.services.controls.opening_generation.YearOpeningPostingAdapter.build_context")
    @patch("reports.services.controls.opening_generation.EntityFinancialYear.objects.select_for_update")
    @patch("reports.services.controls.opening_generation.EntityFinancialYear.objects.filter")
    @patch("reports.services.controls.opening_generation._activate_financial_years")
    @patch("reports.services.controls.opening_generation.transaction.atomic", return_value=contextlib.nullcontext())
    def test_opening_generation_posts_carry_forward_and_stamps_history(
        self,
        _mock_atomic,
        mock_activate_financial_years,
        mock_entity_fy_filter,
        mock_select_for_update,
        mock_build_context,
        mock_preview,
        mock_snapshot,
        mock_policy,
        mock_account_ids,
        mock_ledgers,
        mock_destination,
        mock_posting_service_cls,
        mock_now,
    ):
        source_fy = self._source_year()
        destination_fy = self._destination_year()

        mock_preview.return_value = {
            "actions": {"can_generate": True},
            "opening_history": None,
            "source_year": {"is_closed": True},
            "opening_policy": {"require_closed_source_year": True},
        }
        mock_build_context.return_value = {
            "destination_ledgers": {
                "equity": {"static_account_code": "OPENING_EQUITY_TRANSFER", "ledger_id": 6200},
                "inventory": {"static_account_code": "OPENING_INVENTORY_CARRY_FORWARD", "ledger_id": 9000},
            },
            "constitution": {
                "constitution_mode": "company",
                "allocation_mode": "retained_earnings",
                "total_share_percentage": "100.00",
                "ownership_rows": [],
                "constitution_source": "tax_profile.cin_no",
                "constitution_notes": ["CIN detected in entity tax profile."],
            },
            "allocation_plan": [],
            "equity_targets": [],
            "missing_equity_codes": [],
            "equity_allocation_mode": "retained_earnings",
        }
        mock_snapshot.return_value = {
            "financial_year": source_fy,
            "bs": {
                "assets": [
                    {"ledger_id": 401, "accounthead_id": 11, "ledger_name": "Cash", "amount_decimal": "1000.00"},
                ],
                "liabilities_and_equity": [
                    {"ledger_id": 501, "accounthead_id": 21, "ledger_name": "Sundry Creditors", "amount_decimal": "500.00"},
                ],
                "summary": {"net_profit_brought_to_equity": "250.00"},
                "stock_valuation": {"effective_mode": "valuation", "valuation_method": "fifo"},
            },
        }
        mock_policy.return_value = {
            "opening_mode": "hybrid",
            "batch_materialization": "single_batch",
            "opening_posting_date_strategy": "first_day_of_new_year",
            "require_closed_source_year": True,
            "allow_partial_opening": False,
            "opening_equity_static_account_code": "OPENING_EQUITY_TRANSFER",
            "opening_inventory_static_account_code": "OPENING_INVENTORY_CARRY_FORWARD",
            "carry_forward": {"cash_bank": True, "inventory": True, "retained_earnings": True},
            "reset": {"trading": True, "profit_loss": True},
            "grouped_sections": ["assets", "liabilities", "stock", "equity"],
        }
        mock_account_ids.side_effect = [6200, 9000]
        mock_ledgers.side_effect = [6200, 9000]
        mock_destination.return_value = destination_fy
        mock_now.return_value = datetime(2026, 4, 15, 12, 0, 0)
        mock_entity_fy_filter.return_value.order_by.return_value.values_list.return_value = [51]

        class DummyQuerySet:
            def __init__(self):
                self._kwargs = {}

            def filter(self, **_kwargs):
                self._kwargs = _kwargs
                return self

            def first(self):
                return destination_fy if self._kwargs.get("pk") == destination_fy.pk else source_fy

        mock_select_for_update.return_value = DummyQuerySet()

        posting_service = mock_posting_service_cls.return_value
        posting_service.post.return_value = type(
            "Entry",
            (),
            {
                "id": 7001,
                "posting_batch": type(
                    "Batch",
                    (),
                    {"id": 9001, "txn_type": "OB", "txn_id": 52, "voucher_no": "OB-FY2027-28"},
                )(),
            },
        )()

        payload = build_opening_generation(entity_id=58, entityfin_id=51, subentity_id=17, executed_by=None)

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["entityfin_id"], 52)
        self.assertIsNotNone(payload["opening_history"])
        self.assertEqual(payload["opening_history"]["batch"]["voucher_no"], "OB-FY2027-28")
        self.assertEqual(payload["opening_history"]["active_year_transition"]["before_generation"], [51])
        self.assertEqual(payload["opening_history"]["active_year_transition"]["after_generation"], 52)
        self.assertEqual(destination_fy.metadata["opening_carry_forward"]["status"], "generated")
        self.assertEqual(destination_fy.saved_fields, ["metadata"])
        mock_activate_financial_years.assert_called_once_with(58, [52])
        self.assertTrue(posting_service.post.called)

    @patch("reports.services.controls.opening_generation.timezone.now")
    @patch("reports.services.controls.opening_generation.PostingService")
    @patch("reports.services.controls.opening_generation._resolve_destination_fy")
    @patch("reports.services.controls.opening_generation.StaticAccountService.get_account_id")
    @patch("reports.services.controls.opening_generation.resolve_opening_policy")
    @patch("reports.services.controls.opening_generation._compute_snapshot")
    @patch("reports.services.controls.opening_generation.build_opening_preview")
    @patch("reports.services.controls.opening_generation.EntityFinancialYear.objects.select_for_update")
    @patch("reports.services.controls.opening_generation.EntityFinancialYear.objects.filter")
    @patch("reports.services.controls.opening_generation._activate_financial_years")
    @patch("reports.services.controls.opening_generation.transaction.atomic", return_value=contextlib.nullcontext())
    def test_opening_generation_splits_equity_lines_for_partnership(
        self,
        _mock_atomic,
        _mock_activate_financial_years,
        mock_entity_fy_filter,
        mock_select_for_update,
        mock_preview,
        mock_snapshot,
        mock_policy,
        mock_account_ids,
        mock_destination,
        mock_posting_service_cls,
        mock_now,
    ):
        source_fy = self._source_year()
        destination_fy = self._destination_year()

        mock_preview.return_value = {
            "actions": {"can_generate": True},
            "opening_history": None,
            "source_year": {"is_closed": True},
            "opening_policy": {"require_closed_source_year": True},
        }
        mock_snapshot.return_value = {
            "financial_year": source_fy,
            "bs": {
                "assets": [
                    {"ledger_id": 401, "accounthead_id": 11, "ledger_name": "Cash", "amount_decimal": "1000.00"},
                ],
                "liabilities_and_equity": [
                    {"ledger_id": 501, "accounthead_id": 21, "ledger_name": "Sundry Creditors", "amount_decimal": "500.00"},
                ],
                "summary": {"net_profit_brought_to_equity": "1000.00"},
                "stock_valuation": {"effective_mode": "valuation", "valuation_method": "fifo"},
            },
        }
        mock_policy.return_value = {
            "opening_mode": "hybrid",
            "batch_materialization": "single_batch",
            "opening_posting_date_strategy": "first_day_of_new_year",
            "require_closed_source_year": True,
            "allow_partial_opening": False,
            "opening_equity_static_account_code": "OPENING_EQUITY_TRANSFER",
            "opening_inventory_static_account_code": "OPENING_INVENTORY_CARRY_FORWARD",
            "carry_forward": {"cash_bank": True, "inventory": True, "retained_earnings": True},
            "reset": {"trading": True, "profit_loss": True},
            "grouped_sections": ["assets", "liabilities", "stock", "equity"],
        }
        mock_account_ids.side_effect = [7101, 7102]
        mock_destination.return_value = destination_fy
        mock_now.return_value = datetime(2026, 4, 15, 12, 0, 0)
        mock_entity_fy_filter.return_value.order_by.return_value.values_list.return_value = [51]

        class DummyQuerySet:
            def __init__(self):
                self._kwargs = {}

            def filter(self, **_kwargs):
                self._kwargs = _kwargs
                return self

            def first(self):
                return destination_fy if self._kwargs.get("pk") == destination_fy.pk else source_fy

        mock_select_for_update.return_value = DummyQuerySet()

        posting_service = mock_posting_service_cls.return_value
        posting_service.post.return_value = type(
            "Entry",
            (),
            {
                "id": 7001,
                "posting_batch": type(
                    "Batch",
                    (),
                    {"id": 9001, "txn_type": "OB", "txn_id": 52, "voucher_no": "OB-FY2027-28"},
                )(),
            },
        )()

        mock_destination.return_value = destination_fy
        with patch(
            "reports.services.controls.opening_generation.YearOpeningPostingAdapter.build_context",
            return_value={
                "destination_ledgers": {
                    "equity": {"static_account_code": "OPENING_EQUITY_TRANSFER", "ledger_id": 6200},
                    "inventory": {"static_account_code": "OPENING_INVENTORY_CARRY_FORWARD", "ledger_id": 9000},
                },
                "constitution": {
                    "constitution_mode": "partnership",
                    "allocation_mode": "ratio_split",
                    "total_share_percentage": "100.00",
                    "ownership_rows": [
                        {"id": 1, "name": "Partner A", "ownership_type": "partner", "account_preference": "capital"},
                        {"id": 2, "name": "Partner B", "ownership_type": "partner", "account_preference": "current"},
                    ],
                },
                "allocation_plan": [
                    {"ownership_id": 1, "name": "Partner A", "amount": "600.00", "drcr": "credit"},
                    {"ownership_id": 2, "name": "Partner B", "amount": "400.00", "drcr": "credit"},
                ],
                "equity_targets": [
                    {
                        "static_account_code": "OPENING_PARTNER_CAPITAL__OWNERSHIP_1",
                        "static_account_name": "Opening Partner Capital - Partner A",
                        "ownership_id": 1,
                        "ownership_name": "Partner A",
                        "ownership_type": "partner",
                        "account_preference": "capital",
                        "ledger_id": 7101,
                        "amount": "600.00",
                        "drcr": "credit",
                    },
                    {
                        "static_account_code": "OPENING_PARTNER_CURRENT__OWNERSHIP_2",
                        "static_account_name": "Opening Partner Current - Partner B",
                        "ownership_id": 2,
                        "ownership_name": "Partner B",
                        "ownership_type": "partner",
                        "account_preference": "current",
                        "ledger_id": 7102,
                        "amount": "400.00",
                        "drcr": "credit",
                    },
                ],
                "missing_equity_codes": [],
                "equity_allocation_mode": "ratio_split",
            },
        ):
            payload = build_opening_generation(entity_id=58, entityfin_id=51, subentity_id=17, executed_by=None)

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["entityfin_id"], 52)
        jl_inputs = posting_service.post.call_args.kwargs["jl_inputs"]
        self.assertEqual(len(jl_inputs), 4)
        equity_ledger_ids = [item.ledger_id for item in jl_inputs if item.accounthead_id is None]
        self.assertIn(7101, equity_ledger_ids)
        self.assertIn(7102, equity_ledger_ids)

    @patch("reports.services.controls.opening_generation.transaction.atomic", return_value=contextlib.nullcontext())
    @patch("reports.services.controls.opening_generation.Entry.objects.filter")
    @patch("reports.services.controls.opening_generation.purge_posting_locator")
    @patch("reports.services.controls.opening_generation.EntityFinancialYear.objects.select_for_update")
    @patch("reports.services.controls.opening_generation._activate_financial_years")
    @patch("reports.services.controls.opening_generation._compute_snapshot")
    @patch("reports.services.controls.opening_generation.build_opening_preview")
    def test_opening_generation_rollback_clears_history_and_may_delete_destination_year(
        self,
        mock_preview,
        mock_snapshot,
        mock_activate_financial_years,
        mock_select_for_update,
        mock_purge_posting_locator,
        mock_entry_filter,
        _mock_atomic,
    ):
        source_fy = self._source_year()
        destination_fy = self._destination_year()
        destination_fy.metadata = {
            "opening_carry_forward": {
                "source_year": {"id": 51, "name": "FY 2026-27"},
                "destination_year": {"id": 52, "name": "FY 2027-28", "was_auto_created": True},
                "batch": {"voucher_no": "OB-FY2027-28"},
                "active_year_transition": {"before_generation": [51], "after_generation": 52},
            }
        }
        destination_fy.deleted = False

        def _delete():
            destination_fy.deleted = True

        destination_fy.delete = _delete

        mock_preview.return_value = {
            "opening_history": destination_fy.metadata["opening_carry_forward"],
            "destination_year": {"id": 52, "name": "FY 2027-28"},
        }
        mock_snapshot.return_value = {"financial_year": source_fy}

        class DummyQuerySet:
            def __init__(self, source, destination):
                self.source = source
                self.destination = destination
                self._kwargs = {}

            def filter(self, **kwargs):
                self._kwargs = kwargs
                return self

            def first(self):
                return self.destination if self._kwargs.get("pk") == self.destination.pk else self.source

        mock_select_for_update.return_value = DummyQuerySet(source_fy, destination_fy)
        mock_purge_posting_locator.return_value = {"entries_deleted": 1, "journal_lines_deleted": 4}
        mock_entry_filter.return_value.count.return_value = 0

        payload = build_opening_generation_rollback(entity_id=58, entityfin_id=51, subentity_id=17, executed_by=None)

        self.assertEqual(payload["status"], "success")
        mock_activate_financial_years.assert_called_once_with(58, [51])
        self.assertTrue(destination_fy.deleted)
