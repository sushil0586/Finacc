from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, EntityGstRegistration, GstRegistrationType, SubEntity
from financial.models import Ledger, accountHead, accounttype
from reports.gst_compliance import GstComplianceSnapshotService, parse_gst_compliance_scope
from reports.gst_compliance.views import GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS
from reports.models import GstPortalFilingRun, GstPortalProfile, ReportFilingRun, ReportFreezeSnapshot
from posting.models import Entry, EntryStatus, EntityStaticAccountMap, JournalLine, PostingBatch, StaticAccount, TxnType
from posting.services.static_accounts import StaticAccountService


class GstComplianceSnapshotTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="gst-snapshot", email="gst-snapshot@example.com", password="pass123")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="GST Snapshot Entity",
            legalname="GST Snapshot Entity Pvt Ltd",
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
        self.scope_params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
            "return_period": "2026-06",
        }

    def test_snapshot_builds_all_cards_with_resolved_gstin_and_portal_status(self):
        EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin="29ABCDE1234F1Z5",
            registration_type=self.gst_type,
            is_primary=True,
            createdby=self.user,
        )
        GstPortalProfile.objects.create(
            entity=self.entity,
            gstin="29ABCDE1234F1Z5",
            state_cd="29",
            gst_username="gst-user",
            is_verified=True,
            updated_by=self.user,
        )
        GstPortalFilingRun.objects.create(
            return_type=GstPortalFilingRun.ReturnType.GSTR1,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            gstin="29ABCDE1234F1Z5",
            state_cd="29",
            ret_period="062026",
            status=GstPortalFilingRun.Status.FILED,
            portal_reference="ARN-1",
            prepared_by=self.user,
        )
        freeze = ReportFreezeSnapshot.objects.create(
            report_code="gstr9",
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            version=3,
            payload={"summary": "frozen"},
            frozen_by=self.user,
        )
        ReportFilingRun.objects.create(
            report_code="gstr9",
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            freeze_snapshot=freeze,
            status=ReportFilingRun.Status.PREPARED,
            payload={"filing": "prepared"},
            prepared_by=self.user,
            portal_reference="GSTR9-PREP",
        )

        scope = parse_gst_compliance_scope(self.scope_params)
        payload = GstComplianceSnapshotService().build(
            scope=scope,
            permission_codes=set(GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS),
        )

        self.assertEqual(payload["report_code"], "gst-compliance-snapshot")
        self.assertEqual(payload["scope"]["resolved_gstin"], "29ABCDE1234F1Z5")
        self.assertEqual(payload["scope"]["portal_return_period"], "062026")
        self.assertEqual(payload["summary"]["card_count"], 9)
        cards = {card["code"]: card for card in payload["cards"]}
        self.assertEqual(cards["gstr1"]["status"], "filed")
        self.assertEqual(cards["portal"]["status"], "filed")
        self.assertTrue(cards["portal"]["signals"]["profile_verified"])
        self.assertEqual(cards["gstr9"]["status"], "prepared")
        self.assertEqual(cards["gstr9"]["signals"]["freeze_version"], 3)
        self.assertEqual(cards["gstr1"]["link"]["route"], "/gstreport")
        self.assertEqual(cards["itc_2b"]["link"]["route"], "/gst-reconciliation")
        self.assertTrue(cards["gstr3b"]["access"]["has_permission"])
        self.assertGreaterEqual(len(payload["next_actions"]), 1)

    def test_snapshot_surfaces_missing_gstin_as_setup_warning_without_crashing(self):
        scope = parse_gst_compliance_scope(self.scope_params)
        payload = GstComplianceSnapshotService().build(scope=scope, permission_codes={"reports.gst.view"})
        cards = {card["code"]: card for card in payload["cards"]}

        self.assertEqual(payload["scope"]["resolved_gstin"], None)
        self.assertEqual(cards["gstr1"]["status"], "blocked")
        self.assertEqual(cards["gstr1"]["blockers"][0]["code"], "GSTIN_NOT_CONFIGURED")
        self.assertEqual(cards["itc_2b"]["status"], "needs_review")
        self.assertEqual(payload["summary"]["blocked_count"], 3)
        self.assertFalse(cards["gstr3b"]["access"]["has_permission"])

    @patch("reports.gst_compliance.services.Gstr3bSummaryService.build")
    def test_snapshot_surfaces_input_tax_ledger_tie_out_on_itc_card(self, mock_gstr3b):
        mock_gstr3b.return_value = {
            "section_4": {
                "net_itc": {
                    "cgst": Decimal("90.00"),
                    "sgst": Decimal("90.00"),
                    "igst": Decimal("25.00"),
                    "cess": Decimal("0.00"),
                    "total_tax": Decimal("205.00"),
                }
            }
        }
        StaticAccountService.seed_static_account_master()
        asset_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Current Assets",
            accounttypecode="CA-GST",
            createdby=self.user,
        )
        asset_head = accountHead.objects.create(
            entity=self.entity,
            name="GST Input Credit",
            code=8300,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=asset_type,
            createdby=self.user,
        )
        ledgers = {
            "INPUT_CGST": Ledger.objects.create(entity=self.entity, ledger_code=8301, name="Input CGST", accounthead=asset_head, createdby=self.user),
            "INPUT_SGST": Ledger.objects.create(entity=self.entity, ledger_code=8302, name="Input SGST", accounthead=asset_head, createdby=self.user),
            "INPUT_IGST": Ledger.objects.create(entity=self.entity, ledger_code=8303, name="Input IGST", accounthead=asset_head, createdby=self.user),
            "INPUT_CESS": Ledger.objects.create(entity=self.entity, ledger_code=8304, name="Input CESS", accounthead=asset_head, createdby=self.user),
        }
        for static_code, ledger in ledgers.items():
            EntityStaticAccountMap.objects.create(
                entity=self.entity,
                static_account=StaticAccount.objects.get(code=static_code),
                ledger=ledger,
                createdby=self.user,
            )
        StaticAccountService.invalidate(self.entity.id)

        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=801,
            voucher_no="ITC-TIEOUT-1",
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=801,
            voucher_no="ITC-TIEOUT-1",
            posting_date=datetime(2026, 6, 15).date(),
            status=EntryStatus.POSTED,
            posting_batch=batch,
            created_by=self.user,
        )
        for static_code, amount in (("INPUT_CGST", "90.00"), ("INPUT_SGST", "80.00"), ("INPUT_IGST", "25.00")):
            JournalLine.objects.create(
                entry=entry,
                posting_batch=batch,
                entity=self.entity,
                entityfin=self.entityfin,
                subentity=self.subentity,
                txn_type=TxnType.PURCHASE,
                txn_id=801,
                voucher_no="ITC-TIEOUT-1",
                accounthead=asset_head,
                ledger=ledgers[static_code],
                drcr=True,
                amount=Decimal(amount),
                posting_date=entry.posting_date,
                created_by=self.user,
            )

        scope = parse_gst_compliance_scope(self.scope_params)
        payload = GstComplianceSnapshotService().build(
            scope=scope,
            permission_codes=set(GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS),
        )

        ledger_recon = payload["input_tax_ledger_reconciliation"]
        self.assertEqual(ledger_recon["summary"]["return_total_itc"], Decimal("205.00"))
        self.assertEqual(ledger_recon["summary"]["ledger_total_itc"], Decimal("195.00"))
        self.assertEqual(ledger_recon["summary"]["mismatch_count"], 1)
        rows_by_code = {row["code"]: row for row in ledger_recon["rows"]}
        self.assertEqual(rows_by_code["INPUT_CGST"]["status"], "matched")
        self.assertEqual(rows_by_code["INPUT_SGST"]["status"], "mismatch")
        self.assertEqual(rows_by_code["INPUT_SGST"]["drilldowns"]["ledger_book"]["route"], "/reports/financial/ledger-book")
        cards = {card["code"]: card for card in payload["cards"]}
        self.assertEqual(cards["itc_2b"]["status"], "needs_review")
        self.assertEqual(cards["itc_2b"]["signals"]["input_ledger_mismatch_count"], 1)
        self.assertTrue(any(warning["code"] == "GST_INPUT_LEDGER_MISMATCH" for warning in cards["itc_2b"]["warnings"]))

    @patch("reports.gst_compliance.views.GstComplianceSnapshotAPIView.enforce_scope")
    @patch("reports.gst_compliance.views.assert_any_report_permission")
    def test_snapshot_api_returns_scope_cards_and_actions(self, mock_permissions, mock_enforce_scope):
        mock_permissions.return_value = set(GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS)
        EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin="29ABCDE1234F1Z5",
            registration_type=self.gst_type,
            is_primary=True,
            createdby=self.user,
        )
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get(reverse("reports_api:gst-compliance-snapshot"), self.scope_params)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scope"]["return_period"], "2026-06")
        self.assertEqual(response.data["summary"]["card_count"], 9)
        self.assertEqual(response.data["cards"][0]["code"], "gstr1")
        self.assertEqual(response.data["cards"][0]["link"]["params"]["from_date"], "2026-06-01")
        mock_enforce_scope.assert_called_once()
        mock_permissions.assert_called_once()
        self.assertEqual(tuple(mock_permissions.call_args.kwargs["required_permissions"]), GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS)

    @patch("reports.gst_compliance.views.GstComplianceSnapshotAPIView.enforce_scope")
    def test_snapshot_api_rejects_invalid_scope_before_building_snapshot(self, mock_enforce_scope):
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get(
            reverse("reports_api:gst-compliance-snapshot"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "return_type": "bad", "return_period": "2026-06"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("return_type", response.data)
        mock_enforce_scope.assert_not_called()
