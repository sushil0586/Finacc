from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from reports.gstr1.selectors.queries import apply_smart_filters, base_queryset
from reports.gstr1.selectors.smart_filters import Gstr1SmartFilters
from reports.services.sales_register_service import SalesRegisterService


class ReportQueryOptimizationTests(SimpleTestCase):
    def test_gstr1_min_gst_rate_uses_exists_without_distinct(self):
        queryset = apply_smart_filters(
            base_queryset(),
            Gstr1SmartFilters(min_gst_rate=Decimal("12.00")),
        )

        sql = str(queryset.query).upper()

        self.assertIn("EXISTS(", sql)
        self.assertNotIn(" DISTINCT ", sql)

    def test_sales_register_uses_joined_artifact_fields_not_subqueries(self):
        queryset = SalesRegisterService().annotate_register_fields(
            SalesRegisterService().get_base_queryset()
        )

        sql = str(queryset.query).upper()

        self.assertIn("SALES_EINVOICE", sql)
        self.assertIn("SALES_EWAYBILL", sql)
        self.assertNotIn("SELECT U0.\"IRN\"", sql)
        self.assertNotIn("SELECT U0.\"EWB_NO\"", sql)
