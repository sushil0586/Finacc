from __future__ import annotations

from datetime import datetime, date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from entity.financial_year_validation import assert_document_date_within_financial_year


class FinancialYearValidationTests(SimpleTestCase):
    @patch("entity.financial_year_validation.EntityFinancialYear.objects")
    def test_allows_date_within_selected_financial_year(self, mock_objects):
        fy = SimpleNamespace(
            id=8,
            entity_id=10,
            desc="FY 2026-27",
            year_code="FY26-27",
            finstartyear=datetime(2026, 4, 1, 0, 0, 0),
            finendyear=datetime(2027, 3, 31, 0, 0, 0),
        )
        mock_qs = MagicMock()
        mock_qs.only.return_value.first.return_value = fy
        mock_objects.filter.return_value = mock_qs

        assert_document_date_within_financial_year(
            entity=10,
            entityfinid=8,
            document_date=date(2026, 7, 15),
            field_name="voucher_date",
        )

    @patch("entity.financial_year_validation.EntityFinancialYear.objects")
    def test_rejects_outside_financial_year(self, mock_objects):
        fy = SimpleNamespace(
            id=8,
            entity_id=10,
            desc="FY 2026-27",
            year_code="FY26-27",
            finstartyear=datetime(2026, 4, 1, 0, 0, 0),
            finendyear=datetime(2027, 3, 31, 0, 0, 0),
        )
        mock_qs = MagicMock()
        mock_qs.only.return_value.first.return_value = fy
        mock_objects.filter.return_value = mock_qs

        with self.assertRaises(ValueError) as ex:
            assert_document_date_within_financial_year(
                entity=10,
                entityfinid=8,
                document_date=date(2026, 3, 4),
                field_name="voucher_date",
            )
        self.assertIn("outside selected financial year", str(ex.exception))

    @patch("entity.financial_year_validation.EntityFinancialYear.objects")
    def test_rejects_financial_year_entity_mismatch(self, mock_objects):
        fy = SimpleNamespace(
            id=8,
            entity_id=99,
            desc="FY 2026-27",
            year_code="FY26-27",
            finstartyear=datetime(2026, 4, 1, 0, 0, 0),
            finendyear=datetime(2027, 3, 31, 0, 0, 0),
        )
        mock_qs = MagicMock()
        mock_qs.only.return_value.first.return_value = fy
        mock_objects.filter.return_value = mock_qs

        with self.assertRaises(ValueError) as ex:
            assert_document_date_within_financial_year(
                entity=10,
                entityfinid=8,
                document_date=date(2026, 7, 15),
                field_name="voucher_date",
            )
        self.assertIn("does not belong to the selected entity", str(ex.exception))
