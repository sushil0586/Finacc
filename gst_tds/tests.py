from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.models import account
from gst_tds.models import GstTdsContractLedger


class GstTdsApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="gst_tds_api_tester",
            email="gst_tds_api_tester@example.com",
            password="x",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.entity_1 = Entity.objects.create(entityname="Entity One", createdby=self.user)
        self.entity_2 = Entity.objects.create(entityname="Entity Two", createdby=self.user)

        now = timezone.now()
        self.fy_1 = EntityFinancialYear.objects.create(
            entity=self.entity_1,
            desc="FY1",
            finstartyear=now - timedelta(days=1),
            finendyear=now + timedelta(days=365),
            createdby=self.user,
        )
        self.fy_2 = EntityFinancialYear.objects.create(
            entity=self.entity_2,
            desc="FY2",
            finstartyear=now - timedelta(days=1),
            finendyear=now + timedelta(days=365),
            createdby=self.user,
        )

        self.sub_1 = SubEntity.objects.create(entity=self.entity_1, subentityname="HO 1")
        self.sub_2 = SubEntity.objects.create(entity=self.entity_2, subentityname="HO 2")

        self.vendor_1 = account.objects.create(entity=self.entity_1, accountname="Vendor 1")
        self.vendor_2 = account.objects.create(entity=self.entity_2, accountname="Vendor 2")

        GstTdsContractLedger.objects.create(
            entity=self.entity_1,
            subentity=self.sub_1,
            entityfinid=self.fy_1,
            vendor=self.vendor_1,
            contract_ref="CTR-101",
            cumulative_taxable=Decimal("10000.00"),
            cumulative_tds=Decimal("200.00"),
        )
        GstTdsContractLedger.objects.create(
            entity=self.entity_1,
            subentity=self.sub_1,
            entityfinid=self.fy_1,
            vendor=self.vendor_1,
            contract_ref="CTR-202",
            cumulative_taxable=Decimal("5000.00"),
            cumulative_tds=Decimal("100.00"),
        )

    def test_config_get_default_shape(self):
        resp = self.client.get(f"/api/gst-tds/config/?entity={self.entity_1.id}&subentity={self.sub_1.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["exists"])
        self.assertEqual(resp.data["config"]["entity"], self.entity_1.id)
        self.assertEqual(resp.data["config"]["subentity"], self.sub_1.id)

    def test_config_upsert_and_fetch(self):
        put_resp = self.client.put(
            f"/api/gst-tds/config/?entity={self.entity_1.id}&subentity={self.sub_1.id}",
            {
                "enabled": True,
                "threshold_amount": "300000.00",
                "enforce_pos_rule": False,
            },
            format="json",
        )
        self.assertEqual(put_resp.status_code, 200)
        self.assertTrue(put_resp.data["config"]["enabled"])
        self.assertEqual(Decimal(str(put_resp.data["config"]["threshold_amount"])), Decimal("300000.00"))

        get_resp = self.client.get(f"/api/gst-tds/config/?entity={self.entity_1.id}&subentity={self.sub_1.id}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertTrue(get_resp.data["exists"])
        self.assertTrue(get_resp.data["config"]["enabled"])

    def test_config_rejects_negative_threshold(self):
        resp = self.client.put(
            f"/api/gst-tds/config/?entity={self.entity_1.id}&subentity={self.sub_1.id}",
            {
                "enabled": True,
                "threshold_amount": "-1.00",
                "enforce_pos_rule": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("threshold_amount", resp.data)

    def test_config_rejects_subentity_from_other_entity(self):
        resp = self.client.get(f"/api/gst-tds/config/?entity={self.entity_1.id}&subentity={self.sub_2.id}")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("subentity", resp.data)

    def test_contract_ledgers_list_filters_and_scope_guards(self):
        resp = self.client.get(f"/api/gst-tds/contract-ledgers/?entity={self.entity_1.id}&contract_ref=CTR-101")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["contract_ref"], "CTR-101")

        bad_vendor = self.client.get(
            f"/api/gst-tds/contract-ledgers/?entity={self.entity_1.id}&vendor={self.vendor_2.id}"
        )
        self.assertEqual(bad_vendor.status_code, 400)
        self.assertIn("vendor", bad_vendor.data)

        bad_fy = self.client.get(
            f"/api/gst-tds/contract-ledgers/?entity={self.entity_1.id}&entityfinid={self.fy_2.id}"
        )
        self.assertEqual(bad_fy.status_code, 400)
        self.assertIn("entityfinid", bad_fy.data)

    def test_contract_ledger_summary_returns_totals(self):
        resp = self.client.get(
            f"/api/gst-tds/contract-ledgers/summary/?entity={self.entity_1.id}&entityfinid={self.fy_1.id}&subentity={self.sub_1.id}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total_contracts"], 2)
        self.assertEqual(Decimal(resp.data["total_taxable"]), Decimal("15000.00"))
        self.assertEqual(Decimal(resp.data["total_tds"]), Decimal("300.00"))

        filtered = self.client.get(
            f"/api/gst-tds/contract-ledgers/summary/?entity={self.entity_1.id}&entityfinid={self.fy_1.id}&subentity={self.sub_1.id}&contract_ref=CTR-101"
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.data["contract_ref"], "CTR-101")
        self.assertEqual(filtered.data["total_contracts"], 1)
        self.assertEqual(Decimal(filtered.data["total_taxable"]), Decimal("10000.00"))
