from __future__ import annotations

from datetime import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
from reports.gst_compliance import (
    GST_COMPLIANCE_DEEP_LINKS,
    GST_COMPLIANCE_STATUS_VALUES,
    build_gst_compliance_deep_link,
    parse_gst_compliance_scope,
)


class GstComplianceContractTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="gst-contract", email="gst-contract@example.com", password="pass123")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="GST Contract Entity",
            legalname="GST Contract Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Head Office",
            is_head_office=True,
        )
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )

    def test_scope_normalizes_gstin_and_return_period_to_month_window(self):
        scope = parse_gst_compliance_scope(
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "gstin": " 29abcde1234f1z5 ",
                "return_type": "gstr-1",
                "return_period": "06-2026",
            }
        )

        self.assertEqual(scope.gstin, "29ABCDE1234F1Z5")
        self.assertEqual(scope.return_type, "GSTR1")
        self.assertEqual(scope.return_period, "2026-06")
        self.assertEqual(scope.from_date.isoformat(), "2026-06-01")
        self.assertEqual(scope.to_date.isoformat(), "2026-06-30")
        self.assertEqual(scope.as_query_params()["entity"], self.entity.id)
        self.assertNotIn("missing", scope.as_query_params())

    def test_scope_derives_return_period_from_month_year(self):
        scope = parse_gst_compliance_scope(
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "month": "9",
                "year": "2026",
                "return_type": "GSTR3B",
            }
        )

        self.assertEqual(scope.return_period, "2026-09")
        self.assertEqual(scope.from_date.isoformat(), "2026-09-01")
        self.assertEqual(scope.to_date.isoformat(), "2026-09-30")

    def test_scope_rejects_dates_outside_financial_year(self):
        with self.assertRaises(ValidationError) as error:
            parse_gst_compliance_scope(
                {
                    "entity": self.entity.id,
                    "entityfinid": self.entityfin.id,
                    "from_date": "2026-03-31",
                    "to_date": "2026-04-30",
                }
            )

        self.assertIn("from_date", error.exception.message_dict)

    def test_scope_rejects_invalid_gstin_and_return_type(self):
        with self.assertRaises(ValidationError) as gstin_error:
            parse_gst_compliance_scope(
                {
                    "entity": self.entity.id,
                    "gstin": "29BAD",
                    "from_date": "2026-04-01",
                    "to_date": "2026-04-30",
                }
            )
        self.assertIn("gstin", gstin_error.exception.message_dict)

        with self.assertRaises(ValidationError) as type_error:
            parse_gst_compliance_scope(
                {
                    "entity": self.entity.id,
                    "return_type": "unknown",
                    "from_date": "2026-04-01",
                    "to_date": "2026-04-30",
                }
            )
        self.assertIn("return_type", type_error.exception.message_dict)

    def test_status_and_deep_link_contracts_are_stable(self):
        self.assertEqual(
            GST_COMPLIANCE_STATUS_VALUES,
            (
                "not_configured",
                "ready",
                "needs_review",
                "blocked",
                "prepared",
                "frozen",
                "filed",
                "amendment_needed",
                "overdue",
            ),
        )
        self.assertEqual(GST_COMPLIANCE_DEEP_LINKS["gstr1"]["route"], "/gstreport")
        self.assertEqual(GST_COMPLIANCE_DEEP_LINKS["gstr1_vs_gstr3b"]["route"], "/reports/compliance/gstr1-vs-gstr3b")
        self.assertEqual(GST_COMPLIANCE_DEEP_LINKS["gst_reconciliation"]["route"], "/gst-reconciliation")

    def test_deep_link_builder_carries_scope_and_required_path_params(self):
        scope = parse_gst_compliance_scope(
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "return_period": "2026-04",
            }
        )

        link = build_gst_compliance_deep_link("gstr1_vs_gstr3b", scope)
        self.assertEqual(link["route"], "/reports/compliance/gstr1-vs-gstr3b")
        self.assertEqual(link["params"]["from_date"], "2026-04-01")
        self.assertEqual(link["params"]["to_date"], "2026-04-30")
        self.assertIn("reports.gstr1_gstr3b_reconciliation.view", link["permissions"])

        run_link = build_gst_compliance_deep_link("gst_reconciliation_run", scope, extra_params={"run_id": 101})
        self.assertEqual(run_link["route"], "/gst-reconciliation/runs/101")
        self.assertNotIn("run_id", run_link["params"])
