from __future__ import annotations

import types
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from entity.models import Entity, EntityFinancialYear, SubEntity
from financial.models import account
from gst_tds.models import EntityGstTdsConfig, GstTdsContractLedger
from gst_tds.services.gst_tds_service import (
    GstTdsService,
    normalize_contract_ref,
    q2,
    q4,
    RATE_TOTAL,
    RATE_HALF,
    ZERO2,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Pure helpers — no DB
# ---------------------------------------------------------------------------

class NormalizeContractRefTests(SimpleTestCase):

    def test_strips_whitespace(self):
        self.assertEqual(normalize_contract_ref("  ctr-101  "), "CTR-101")

    def test_uppercases(self):
        self.assertEqual(normalize_contract_ref("ctr-abc"), "CTR-ABC")

    def test_none_returns_empty_string(self):
        self.assertEqual(normalize_contract_ref(None), "")

    def test_empty_string_returns_empty_string(self):
        self.assertEqual(normalize_contract_ref(""), "")

    def test_integer_input(self):
        self.assertEqual(normalize_contract_ref(12345), "12345")


class GstTdsRoundingTests(SimpleTestCase):

    def test_q2_rounds_half_up(self):
        self.assertEqual(q2("100.555"), Decimal("100.56"))

    def test_q2_none_returns_zero(self):
        self.assertEqual(q2(None), ZERO2)

    def test_q4_rounds_to_four_places(self):
        self.assertEqual(q4("2.00005"), Decimal("2.0001"))

    def test_q4_none_returns_zero(self):
        self.assertEqual(q4(None), Decimal("0.0000"))

    def test_rate_constants(self):
        self.assertEqual(RATE_TOTAL, Decimal("2.0000"))
        self.assertEqual(RATE_HALF, Decimal("1.0000"))


# ---------------------------------------------------------------------------
# compute_for_invoice — DB tests
# ---------------------------------------------------------------------------

def _inv(
    entity_id,
    subentity_id=None,
    entityfinid_id=1,
    vendor_id=1,
    gst_tds_enabled=True,
    total_taxable="100000.00",
    gst_tds_contract_ref="CTR-001",
    tax_regime=1,
    is_igst=False,
):
    """Build a lightweight fake invoice using SimpleNamespace."""
    return types.SimpleNamespace(
        entity_id=entity_id,
        subentity_id=subentity_id,
        entityfinid_id=entityfinid_id,
        vendor_id=vendor_id,
        gst_tds_enabled=gst_tds_enabled,
        total_taxable=Decimal(total_taxable),
        gst_tds_contract_ref=gst_tds_contract_ref,
        tax_regime=tax_regime,
        is_igst=is_igst,
    )


class ComputeInvoiceBaseTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tds_calc", email="tds@test.com", password="x")
        cls.entity = Entity.objects.create(entityname="TDS Entity", createdby=cls.user)
        cls.sub = SubEntity.objects.create(entity=cls.entity, subentityname="Branch 1")
        now = timezone.now()
        cls.fy = EntityFinancialYear.objects.create(
            entity=cls.entity, desc="FY25",
            finstartyear=now - timedelta(days=1),
            finendyear=now + timedelta(days=365),
            createdby=cls.user,
        )
        cls.vendor = account.objects.create(entity=cls.entity, accountname="Test Vendor")

    def _config(self, enabled=True, threshold="250000.00", subentity=None):
        obj, _ = EntityGstTdsConfig.objects.update_or_create(
            entity=self.entity,
            subentity=subentity,
            defaults={"enabled": enabled, "threshold_amount": Decimal(threshold)},
        )
        return obj

    def _inv(self, **kwargs):
        defaults = dict(
            entity_id=self.entity.id,
            subentity_id=self.sub.id,
            entityfinid_id=self.fy.id,
            vendor_id=self.vendor.id,
        )
        defaults.update(kwargs)
        return _inv(**defaults)


class EligibilityGateTests(ComputeInvoiceBaseTest):

    def test_gst_tds_flag_false_returns_not_eligible(self):
        self._config()
        res = GstTdsService.compute_for_invoice(self._inv(gst_tds_enabled=False))
        self.assertFalse(res.eligible)
        self.assertIn("gst_tds_enabled", res.reason)

    def test_no_config_returns_not_eligible(self):
        # No config row exists for this entity
        res = GstTdsService.compute_for_invoice(self._inv())
        self.assertFalse(res.eligible)
        self.assertIn("config", res.reason)

    def test_config_disabled_returns_not_eligible(self):
        self._config(enabled=False)
        res = GstTdsService.compute_for_invoice(self._inv())
        self.assertFalse(res.eligible)
        self.assertIn("config", res.reason)

    def test_empty_contract_ref_returns_not_eligible(self):
        self._config()
        res = GstTdsService.compute_for_invoice(self._inv(gst_tds_contract_ref=""))
        self.assertFalse(res.eligible)
        self.assertIn("contract ref", res.reason)

    def test_whitespace_only_contract_ref_returns_not_eligible(self):
        self._config()
        res = GstTdsService.compute_for_invoice(self._inv(gst_tds_contract_ref="   "))
        self.assertFalse(res.eligible)
        self.assertIn("contract ref", res.reason)

    def test_zero_taxable_base_returns_not_eligible(self):
        self._config()
        res = GstTdsService.compute_for_invoice(self._inv(total_taxable="0.00"))
        self.assertFalse(res.eligible)
        self.assertIn("zero", res.reason)

    def test_all_amounts_zero_when_not_eligible(self):
        self._config(enabled=False)
        res = GstTdsService.compute_for_invoice(self._inv())
        self.assertEqual(res.cgst, ZERO2)
        self.assertEqual(res.sgst, ZERO2)
        self.assertEqual(res.igst, ZERO2)
        self.assertEqual(res.total, ZERO2)


class ThresholdTests(ComputeInvoiceBaseTest):

    def test_below_threshold_returns_not_eligible(self):
        # threshold 250k, cumulative before=0, this invoice 100k -> after=100k < threshold
        self._config(threshold="250000.00")
        res = GstTdsService.compute_for_invoice(self._inv(total_taxable="100000.00"))
        self.assertFalse(res.eligible)
        self.assertIn("threshold", res.reason)

    def test_exactly_at_threshold_returns_not_eligible(self):
        # after == threshold → still not eligible (rule: after must exceed threshold)
        self._config(threshold="250000.00")
        res = GstTdsService.compute_for_invoice(self._inv(total_taxable="250000.00"))
        self.assertFalse(res.eligible)

    def test_above_threshold_on_first_invoice_is_eligible(self):
        # threshold 100k, invoice 150k, before=0 → crossing: TDS on excess 50k only
        self._config(threshold="100000.00")
        res = GstTdsService.compute_for_invoice(self._inv(total_taxable="150000.00"))
        self.assertTrue(res.eligible)
        # base = taxable_for_tds = after(150k) - threshold(100k) = 50k
        self.assertEqual(res.base, Decimal("50000.00"))

    def test_threshold_crossing_applies_tds_only_on_excess(self):
        """
        Before=200k, threshold=250k, this invoice=100k → after=300k.
        Only 300k-250k=50k should attract TDS.
        """
        self._config(threshold="250000.00")
        # seed prior cumulative via ledger
        GstTdsContractLedger.objects.create(
            entity=self.entity,
            subentity=self.sub,
            entityfinid=self.fy,
            vendor=self.vendor,
            contract_ref="CTR-001",
            cumulative_taxable=Decimal("200000.00"),
            cumulative_tds=ZERO2,
        )
        res = GstTdsService.compute_for_invoice(self._inv(total_taxable="100000.00"))
        self.assertTrue(res.eligible)
        self.assertEqual(res.base, Decimal("50000.00"))   # only excess
        expected_each = q2(Decimal("50000.00") * Decimal("0.01"))
        self.assertEqual(res.cgst, expected_each)
        self.assertEqual(res.sgst, expected_each)
        self.assertEqual(res.total, q2(expected_each * 2))

    def test_already_above_threshold_applies_tds_on_full_invoice(self):
        """
        Before=300k (already past 250k threshold), this invoice=50k → TDS on full 50k.
        """
        self._config(threshold="250000.00")
        GstTdsContractLedger.objects.create(
            entity=self.entity,
            subentity=self.sub,
            entityfinid=self.fy,
            vendor=self.vendor,
            contract_ref="CTR-001",
            cumulative_taxable=Decimal("300000.00"),
            cumulative_tds=Decimal("1000.00"),
        )
        res = GstTdsService.compute_for_invoice(self._inv(total_taxable="50000.00"))
        self.assertTrue(res.eligible)
        self.assertEqual(res.base, Decimal("50000.00"))


class TaxSplitTests(ComputeInvoiceBaseTest):

    def setUp(self):
        self._config(threshold="0.00")   # threshold=0 so any positive base is eligible

    def test_intra_state_splits_into_cgst_sgst(self):
        res = GstTdsService.compute_for_invoice(
            self._inv(total_taxable="100000.00", tax_regime=1, is_igst=False)
        )
        self.assertTrue(res.eligible)
        self.assertEqual(res.cgst, Decimal("1000.00"))
        self.assertEqual(res.sgst, Decimal("1000.00"))
        self.assertEqual(res.igst, ZERO2)
        self.assertEqual(res.total, Decimal("2000.00"))

    def test_inter_state_regime_2_uses_igst(self):
        res = GstTdsService.compute_for_invoice(
            self._inv(total_taxable="100000.00", tax_regime=2, is_igst=False)
        )
        self.assertTrue(res.eligible)
        self.assertEqual(res.igst, Decimal("2000.00"))
        self.assertEqual(res.cgst, ZERO2)
        self.assertEqual(res.sgst, ZERO2)
        self.assertEqual(res.total, Decimal("2000.00"))

    def test_is_igst_flag_overrides_to_inter_state(self):
        res = GstTdsService.compute_for_invoice(
            self._inv(total_taxable="100000.00", tax_regime=1, is_igst=True)
        )
        self.assertTrue(res.eligible)
        self.assertEqual(res.igst, Decimal("2000.00"))
        self.assertEqual(res.cgst, ZERO2)
        self.assertEqual(res.sgst, ZERO2)

    def test_intra_state_cgst_equals_sgst(self):
        # Symmetry check: cgst == sgst for any intra-state amount
        res = GstTdsService.compute_for_invoice(
            self._inv(total_taxable="73456.78", tax_regime=1, is_igst=False)
        )
        self.assertEqual(res.cgst, res.sgst)
        self.assertEqual(res.total, q2(res.cgst + res.sgst))

    def test_rate_is_always_2_percent(self):
        res = GstTdsService.compute_for_invoice(
            self._inv(total_taxable="100000.00", tax_regime=1)
        )
        self.assertEqual(res.rate, Decimal("2.0000"))


class SubentityConfigFallbackTests(ComputeInvoiceBaseTest):

    def test_subentity_config_takes_precedence_over_entity_config(self):
        # Entity-wide config disabled, subentity config enabled
        EntityGstTdsConfig.objects.create(entity=self.entity, subentity=None, enabled=False, threshold_amount=Decimal("0.00"))
        EntityGstTdsConfig.objects.create(entity=self.entity, subentity=self.sub, enabled=True, threshold_amount=Decimal("0.00"))

        res = GstTdsService.compute_for_invoice(self._inv(total_taxable="100000.00"))
        self.assertTrue(res.eligible)

    def test_falls_back_to_entity_wide_config_when_no_subentity_match(self):
        sub2 = SubEntity.objects.create(entity=self.entity, subentityname="Branch 2")
        # Only entity-wide config (subentity=None)
        EntityGstTdsConfig.objects.create(entity=self.entity, subentity=None, enabled=True, threshold_amount=Decimal("0.00"))

        res = GstTdsService.compute_for_invoice(
            self._inv(subentity_id=sub2.id, total_taxable="100000.00")
        )
        self.assertTrue(res.eligible)


class ApplyToHeaderTests(ComputeInvoiceBaseTest):

    def setUp(self):
        self._config(threshold="0.00")

    def test_apply_to_header_populates_all_fields(self):
        inv = self._inv(total_taxable="100000.00", tax_regime=1)
        GstTdsService.apply_to_header(inv)

        self.assertEqual(inv.gst_tds_amount, Decimal("2000.00"))
        self.assertEqual(inv.gst_tds_cgst_amount, Decimal("1000.00"))
        self.assertEqual(inv.gst_tds_sgst_amount, Decimal("1000.00"))
        self.assertEqual(inv.gst_tds_igst_amount, ZERO2)
        self.assertEqual(inv.gst_tds_base_amount, Decimal("100000.00"))
        self.assertEqual(inv.gst_tds_rate, Decimal("2.0000"))
        self.assertEqual(inv.gst_tds_status, 1)

    def test_apply_to_header_when_not_eligible_zeros_out_amounts(self):
        inv = self._inv(gst_tds_enabled=False, total_taxable="100000.00")
        GstTdsService.apply_to_header(inv)

        self.assertEqual(inv.gst_tds_amount, ZERO2)
        self.assertEqual(inv.gst_tds_cgst_amount, ZERO2)
        self.assertEqual(inv.gst_tds_sgst_amount, ZERO2)
        self.assertEqual(inv.gst_tds_igst_amount, ZERO2)
        self.assertEqual(inv.gst_tds_status, 0)


# ---------------------------------------------------------------------------
# API-level tests (retained from original suite)
# ---------------------------------------------------------------------------

class GstTdsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
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
            entity=self.entity_1, desc="FY1",
            finstartyear=now - timedelta(days=1),
            finendyear=now + timedelta(days=365),
            createdby=self.user,
        )
        self.fy_2 = EntityFinancialYear.objects.create(
            entity=self.entity_2, desc="FY2",
            finstartyear=now - timedelta(days=1),
            finendyear=now + timedelta(days=365),
            createdby=self.user,
        )

        self.sub_1 = SubEntity.objects.create(entity=self.entity_1, subentityname="HO 1")
        self.sub_2 = SubEntity.objects.create(entity=self.entity_2, subentityname="HO 2")

        self.vendor_1 = account.objects.create(entity=self.entity_1, accountname="Vendor 1")
        self.vendor_2 = account.objects.create(entity=self.entity_2, accountname="Vendor 2")

        GstTdsContractLedger.objects.create(
            entity=self.entity_1, subentity=self.sub_1, entityfinid=self.fy_1,
            vendor=self.vendor_1, contract_ref="CTR-101",
            cumulative_taxable=Decimal("10000.00"), cumulative_tds=Decimal("200.00"),
        )
        GstTdsContractLedger.objects.create(
            entity=self.entity_1, subentity=self.sub_1, entityfinid=self.fy_1,
            vendor=self.vendor_1, contract_ref="CTR-202",
            cumulative_taxable=Decimal("5000.00"), cumulative_tds=Decimal("100.00"),
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
            {"enabled": True, "threshold_amount": "300000.00", "enforce_pos_rule": False},
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
            {"enabled": True, "threshold_amount": "-1.00", "enforce_pos_rule": True},
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
            f"/api/gst-tds/contract-ledgers/summary/?entity={self.entity_1.id}"
            f"&entityfinid={self.fy_1.id}&subentity={self.sub_1.id}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total_contracts"], 2)
        self.assertEqual(Decimal(resp.data["total_taxable"]), Decimal("15000.00"))
        self.assertEqual(Decimal(resp.data["total_tds"]), Decimal("300.00"))

        filtered = self.client.get(
            f"/api/gst-tds/contract-ledgers/summary/?entity={self.entity_1.id}"
            f"&entityfinid={self.fy_1.id}&subentity={self.sub_1.id}&contract_ref=CTR-101"
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.data["contract_ref"], "CTR-101")
        self.assertEqual(filtered.data["total_contracts"], 1)
        self.assertEqual(Decimal(filtered.data["total_taxable"]), Decimal("10000.00"))


class GstTdsDeleteProtectionTests(SimpleTestCase):
    def test_contract_ledger_vendor_uses_protect(self):
        self.assertEqual(
            GstTdsContractLedger._meta.get_field("vendor").remote_field.on_delete.__name__,
            "PROTECT",
        )
