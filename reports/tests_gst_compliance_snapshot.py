from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, EntityGstRegistration, GstRegistrationType, SubEntity
from financial.models import Ledger, accountHead, accounttype
from gst_reconciliation.models import GstReconciliationItem, GstReconciliationRun
from reports.gst_compliance import GstComplianceSnapshotService, parse_gst_compliance_scope
from reports.gst_compliance.views import GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS
from reports.models import GstPortalFilingRun, GstPortalProfile, ReportFilingRun, ReportFreezeSnapshot
from posting.models import Entry, EntryStatus, EntityStaticAccountMap, JournalLine, PostingBatch, StaticAccount, TxnType
from posting.services.static_accounts import StaticAccountService
from sales.models import SalesInvoiceHeader
from sales.models.sales_compliance import SalesEInvoice, SalesEInvoiceStatus, SalesEWayBill, SalesEWayStatus


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

    def _create_sales_invoice(
        self,
        *,
        doc_no: int,
        bill_date,
        seller_gstin: str = "29ABCDE1234F1Z5",
        subentity=None,
        einvoice_applicable: bool = True,
        eway_applicable: bool = True,
        status=SalesInvoiceHeader.Status.POSTED,
        doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
        original_invoice=None,
        total_taxable_value=Decimal("100.00"),
        total_cgst=Decimal("9.00"),
        total_sgst=Decimal("9.00"),
        total_igst=Decimal("0.00"),
        total_cess=Decimal("0.00"),
        grand_total=Decimal("118.00"),
    ) -> SalesInvoiceHeader:
        return SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity if subentity is None else subentity,
            doc_type=doc_type,
            status=status,
            bill_date=bill_date,
            posting_date=bill_date,
            doc_code="SI",
            doc_no=doc_no,
            invoice_number=f"SI/{doc_no}",
            original_invoice=original_invoice,
            customer_name=f"Customer {doc_no}",
            customer_gstin="29ABCDE1234F2Z6",
            customer_state_code="29",
            seller_gstin=seller_gstin,
            seller_state_code="29",
            place_of_supply_state_code="29",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            gst_compliance_mode=SalesInvoiceHeader.GstComplianceMode.EINVOICE_AND_EWAY,
            is_einvoice_applicable=einvoice_applicable,
            is_eway_applicable=eway_applicable,
            total_taxable_value=total_taxable_value,
            total_cgst=total_cgst,
            total_sgst=total_sgst,
            total_igst=total_igst,
            total_cess=total_cess,
            grand_total=grand_total,
            created_by=self.user,
        )

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
        self.assertEqual(cards["gstr1"]["links"]["primary"]["route"], "/gstreport")
        self.assertEqual(cards["itc_2b"]["link"]["route"], "/gst-reconciliation")
        self.assertEqual(cards["portal"]["links"]["primary"]["route"], "/gstreport")
        self.assertTrue(cards["gstr3b"]["access"]["has_permission"])
        self.assertGreaterEqual(len(payload["next_actions"]), 1)
        self.assertEqual(payload["period_lifecycle"]["status"], "prepared")
        self.assertFalse(payload["period_lifecycle"]["locked"])
        self.assertEqual(payload["period_lifecycle"]["portal_return_period"], "062026")
        lifecycle_evidence = {item["code"]: item for item in payload["period_lifecycle"]["evidence"]}
        self.assertEqual(lifecycle_evidence["gstr1_portal"]["reference"], "ARN-1")
        self.assertEqual(lifecycle_evidence["gstr9_freeze"]["reference"], "v3")
        self.assertEqual(lifecycle_evidence["gstr9_filing"]["reference"], "GSTR9-PREP")

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
        self.assertEqual(payload["period_lifecycle"]["status"], "not_configured")
        self.assertEqual(payload["period_lifecycle"]["blockers"][0]["code"], "GSTIN_NOT_CONFIGURED")
        self.assertEqual(payload["period_lifecycle"]["evidence"], [])

    def test_snapshot_period_lifecycle_marks_monthly_period_filed_when_gstr1_and_gstr3b_are_filed(self):
        EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin="29ABCDE1234F1Z5",
            registration_type=self.gst_type,
            is_primary=True,
            createdby=self.user,
        )
        for return_type, reference in (
            (GstPortalFilingRun.ReturnType.GSTR1, "GSTR1-ARN-062026"),
            (GstPortalFilingRun.ReturnType.GSTR3B, "GSTR3B-ARN-062026"),
        ):
            GstPortalFilingRun.objects.create(
                return_type=return_type,
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.subentity,
                gstin="29ABCDE1234F1Z5",
                state_cd="29",
                ret_period="062026",
                status=GstPortalFilingRun.Status.FILED,
                portal_reference=reference,
                prepared_by=self.user,
                submitted_by=self.user,
            )

        scope = parse_gst_compliance_scope(self.scope_params)
        payload = GstComplianceSnapshotService().build(
            scope=scope,
            permission_codes=set(GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS),
        )

        self.assertEqual(payload["period_lifecycle"]["status"], "filed")
        self.assertTrue(payload["period_lifecycle"]["locked"])
        self.assertTrue(payload["period_lifecycle"]["can_reopen"])
        evidence = {item["code"]: item for item in payload["period_lifecycle"]["evidence"]}
        self.assertEqual(evidence["gstr1_portal"]["reference"], "GSTR1-ARN-062026")
        self.assertEqual(evidence["gstr3b_portal"]["reference"], "GSTR3B-ARN-062026")

    def test_snapshot_amendment_queue_summarizes_linked_sales_notes_from_prior_period(self):
        EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin="29ABCDE1234F1Z5",
            registration_type=self.gst_type,
            is_primary=True,
            createdby=self.user,
        )
        original = self._create_sales_invoice(doc_no=701, bill_date=datetime(2026, 5, 20).date())
        self._create_sales_invoice(
            doc_no=702,
            bill_date=datetime(2026, 6, 8).date(),
            doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
            original_invoice=original,
            total_taxable_value=Decimal("40.00"),
            total_cgst=Decimal("3.60"),
            total_sgst=Decimal("3.60"),
            grand_total=Decimal("47.20"),
        )
        same_period_original = self._create_sales_invoice(doc_no=703, bill_date=datetime(2026, 6, 2).date())
        self._create_sales_invoice(
            doc_no=704,
            bill_date=datetime(2026, 6, 12).date(),
            doc_type=SalesInvoiceHeader.DocType.DEBIT_NOTE,
            original_invoice=same_period_original,
            total_taxable_value=Decimal("10.00"),
            total_cgst=Decimal("0.90"),
            total_sgst=Decimal("0.90"),
            grand_total=Decimal("11.80"),
        )

        scope = parse_gst_compliance_scope(self.scope_params)
        payload = GstComplianceSnapshotService().build(
            scope=scope,
            permission_codes=set(GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS),
        )

        queue = payload["amendment_queue"]
        self.assertEqual(queue["status"], "needs_review")
        self.assertEqual(queue["summary"]["impact_count"], 1)
        self.assertEqual(queue["summary"]["sales_note_count"], 1)
        self.assertEqual(queue["summary"]["taxable_impact"], "-40.00")
        self.assertEqual(queue["summary"]["tax_impact"], "-7.20")
        self.assertEqual(queue["summary"]["net_impact"], "-47.20")
        self.assertEqual(queue["rows"][0]["document_type"], "Credit Note")
        self.assertEqual(queue["rows"][0]["original_period"], "2026-05")
        self.assertEqual(queue["rows"][0]["impact_period"], "2026-06")

    def test_snapshot_amendment_queue_includes_gstr2b_portal_revised_context(self):
        EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin="29ABCDE1234F1Z5",
            registration_type=self.gst_type,
            is_primary=True,
            createdby=self.user,
        )
        GstReconciliationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            gst_registration_gstin="29ABCDE1234F1Z5",
            return_period="2026-06",
            period_from=datetime(2026, 6, 1).date(),
            period_to=datetime(2026, 6, 30).date(),
            status=GstReconciliationRun.Status.IN_REVIEW,
            summary_json={
                "portal_context_summary": {
                    "amended_rows": 2,
                    "vendor_revised_rows": 1,
                    "ims_rows": 0,
                    "ims_pending_rows": 0,
                    "ims_rejected_rows": 0,
                }
            },
            created_by=self.user,
        )

        scope = parse_gst_compliance_scope(self.scope_params)
        payload = GstComplianceSnapshotService().build(
            scope=scope,
            permission_codes=set(GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS),
        )

        queue = payload["amendment_queue"]
        self.assertEqual(queue["status"], "needs_review")
        self.assertEqual(queue["summary"]["impact_count"], 3)
        self.assertEqual(queue["summary"]["portal_context_count"], 3)
        self.assertEqual(queue["rows"][0]["source"], "gstr2b_portal")
        self.assertIn("2 amended row(s), 1 vendor revised row(s)", queue["rows"][0]["reason"])

    def test_snapshot_aggregates_einvoice_eway_period_health(self):
        EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin="29ABCDE1234F1Z5",
            registration_type=self.gst_type,
            is_primary=True,
            createdby=self.user,
        )
        generated = self._create_sales_invoice(doc_no=501, bill_date=datetime(2026, 6, 5).date())
        SalesEInvoice.objects.create(
            invoice=generated,
            status=SalesEInvoiceStatus.GENERATED,
            irn="IRN-GEN-501",
            provider_name="whitebooks",
            provider_environment=1,
            credential_gstin="29ABCDE1234F1Z5",
            created_by=self.user,
        )
        SalesEWayBill.objects.create(
            invoice=generated,
            status=SalesEWayStatus.GENERATED,
            ewb_no="171001234501",
            valid_upto=timezone.now() + timedelta(days=2),
            vehicle_no="KA01AB1234",
            provider_name="whitebooks",
            provider_environment=1,
            credential_gstin="29ABCDE1234F1Z5",
            created_by=self.user,
        )
        failed = self._create_sales_invoice(doc_no=502, bill_date=datetime(2026, 6, 10).date())
        SalesEInvoice.objects.create(
            invoice=failed,
            status=SalesEInvoiceStatus.FAILED,
            last_error_code="DUPIRN",
            last_error_message="Duplicate IRN",
            credential_gstin="29ABCDE1234F1Z5",
            created_by=self.user,
        )
        SalesEWayBill.objects.create(
            invoice=failed,
            status=SalesEWayStatus.FAILED,
            last_error_message="Distance is invalid",
            credential_gstin="29ABCDE1234F1Z5",
            created_by=self.user,
        )
        expired = self._create_sales_invoice(doc_no=503, bill_date=datetime(2026, 6, 20).date())
        SalesEInvoice.objects.create(
            invoice=expired,
            status=SalesEInvoiceStatus.GENERATED,
            irn="IRN-GEN-503",
            credential_gstin="29ABCDE1234F1Z5",
            created_by=self.user,
        )
        SalesEWayBill.objects.create(
            invoice=expired,
            status=SalesEWayStatus.GENERATED,
            ewb_no="171001234503",
            valid_upto=timezone.now() - timedelta(days=1),
            credential_gstin="29ABCDE1234F1Z5",
            created_by=self.user,
        )
        outside_period = self._create_sales_invoice(doc_no=504, bill_date=datetime(2026, 7, 5).date())
        SalesEInvoice.objects.create(
            invoice=outside_period,
            status=SalesEInvoiceStatus.FAILED,
            credential_gstin="29ABCDE1234F1Z5",
            created_by=self.user,
        )
        other_gstin = self._create_sales_invoice(
            doc_no=505,
            bill_date=datetime(2026, 6, 12).date(),
            seller_gstin="27ABCDE1234F1Z5",
        )
        SalesEInvoice.objects.create(
            invoice=other_gstin,
            status=SalesEInvoiceStatus.FAILED,
            credential_gstin="27ABCDE1234F1Z5",
            created_by=self.user,
        )

        scope = parse_gst_compliance_scope(self.scope_params)
        payload = GstComplianceSnapshotService().build(
            scope=scope,
            permission_codes=set(GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS),
        )
        card = {item["code"]: item for item in payload["cards"]}["einvoice_eway"]

        self.assertEqual(card["status"], "blocked")
        self.assertEqual(card["summary"]["invoices"], 3)
        self.assertEqual(card["summary"]["irn_failed"], 1)
        self.assertEqual(card["summary"]["ewb_failed"], 1)
        self.assertEqual(card["summary"]["ewb_expired"], 1)
        self.assertEqual(card["signals"]["irn_generated"], 2)
        self.assertEqual(card["signals"]["ewb_generated"], 2)
        self.assertEqual(card["signals"]["retry_ready"], 2)
        self.assertEqual(card["signals"]["ewb_expiring_soon"], 1)
        self.assertEqual(card["signals"]["provider_names"], "whitebooks")
        self.assertTrue(any(item["code"] == "EWAY_EXPIRED" for item in card["blockers"]))
        self.assertTrue(any(item["code"] == "EINVOICE_EWAY_FAILED_ITEMS" for item in card["warnings"]))

    def test_snapshot_einvoice_eway_card_respects_subentity_and_not_applicable_counts(self):
        EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin="29ABCDE1234F1Z5",
            registration_type=self.gst_type,
            is_primary=True,
            createdby=self.user,
        )
        branch = SubEntity.objects.create(entity=self.entity, subentityname="Branch", is_head_office=False)
        in_scope = self._create_sales_invoice(
            doc_no=601,
            bill_date=datetime(2026, 6, 6).date(),
            einvoice_applicable=False,
            eway_applicable=False,
        )
        out_scope_branch = self._create_sales_invoice(
            doc_no=602,
            bill_date=datetime(2026, 6, 6).date(),
            subentity=branch,
        )
        SalesEInvoice.objects.create(
            invoice=out_scope_branch,
            status=SalesEInvoiceStatus.FAILED,
            credential_gstin="29ABCDE1234F1Z5",
            created_by=self.user,
        )

        scope = parse_gst_compliance_scope(self.scope_params)
        payload = GstComplianceSnapshotService().build(
            scope=scope,
            permission_codes=set(GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS),
        )
        card = {item["code"]: item for item in payload["cards"]}["einvoice_eway"]

        self.assertEqual(card["status"], "ready")
        self.assertEqual(card["summary"]["invoices"], 1)
        self.assertEqual(card["summary"]["irn_failed"], 0)
        self.assertEqual(card["signals"]["not_applicable"], 2)
        self.assertEqual(card["warning_count"], 0)

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

    def test_snapshot_rolls_up_itc_decisions_from_latest_gstr2b_run(self):
        EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin="29ABCDE1234F1Z5",
            registration_type=self.gst_type,
            is_primary=True,
            createdby=self.user,
        )
        older_run = GstReconciliationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            gst_registration_gstin="29ABCDE1234F1Z5",
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            return_period="2026-06",
            revision_no=1,
            status=GstReconciliationRun.Status.CLOSED,
            created_by=self.user,
        )
        latest_run = GstReconciliationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            gst_registration_gstin="29ABCDE1234F1Z5",
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            return_period="2026-06",
            revision_no=2,
            status=GstReconciliationRun.Status.IN_REVIEW,
            summary_json={
                "portal_context_summary": {
                    "amended_rows": 1,
                    "vendor_revised_rows": 1,
                    "ims_rows": 2,
                    "ims_pending_rows": 1,
                    "ims_rejected_rows": 1,
                }
            },
            created_by=self.user,
        )
        GstReconciliationItem.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            run=older_run,
            match_key="older-accepted",
            source_document_type="GSTR2B",
            source_document_id="older-accepted",
            match_status=GstReconciliationItem.MatchStatus.MATCHED,
            cgst_imported=Decimal("999.00"),
            metadata_json={"itc_decision": {"decision": "ACCEPT"}},
            created_by=self.user,
        )
        for index, decision, taxes in (
            (1, "ACCEPT", {"cgst_books": Decimal("18.00"), "sgst_books": Decimal("18.00")}),
            (2, "DEFER", {"igst_imported": Decimal("40.00")}),
            (3, "BLOCK", {"cgst_imported": Decimal("9.00"), "sgst_imported": Decimal("9.00")}),
            (4, None, {"igst_imported": Decimal("12.00")}),
        ):
            metadata = {"itc_decision": {"decision": decision, "reason": "reviewed"}} if decision else {}
            GstReconciliationItem.objects.create(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.subentity,
                run=latest_run,
                match_key=f"item-{index}",
                source_document_type="GSTR2B",
                source_document_id=f"item-{index}",
                match_status=GstReconciliationItem.MatchStatus.MATCHED,
                metadata_json=metadata,
                created_by=self.user,
                **taxes,
            )

        scope = parse_gst_compliance_scope(self.scope_params)
        payload = GstComplianceSnapshotService().build(
            scope=scope,
            permission_codes=set(GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS),
        )

        summary = payload["itc_decision_summary"]
        self.assertEqual(summary["run_id"], latest_run.id)
        self.assertEqual(summary["run_status"], GstReconciliationRun.Status.IN_REVIEW)
        self.assertEqual(summary["total_items"], 4)
        self.assertEqual(summary["decided_items"], 3)
        self.assertEqual(summary["pending_items"], 1)
        self.assertEqual(summary["accepted_items"], 1)
        self.assertEqual(summary["deferred_items"], 1)
        self.assertEqual(summary["blocked_items"], 1)
        self.assertEqual(summary["tax_by_decision"]["ACCEPT"], "36.00")
        self.assertEqual(summary["tax_by_decision"]["DEFER"], "40.00")
        self.assertEqual(summary["tax_by_decision"]["BLOCK"], "18.00")
        self.assertEqual(summary["tax_by_decision"]["PENDING"], "12.00")
        self.assertEqual(summary["portal_context_summary"]["amended_rows"], 1)
        self.assertEqual(summary["portal_context_summary"]["vendor_revised_rows"], 1)
        self.assertEqual(summary["portal_context_summary"]["ims_pending_rows"], 1)
        cards = {card["code"]: card for card in payload["cards"]}
        self.assertEqual(cards["itc_2b"]["status"], "needs_review")
        self.assertEqual(cards["itc_2b"]["signals"]["itc_review_run_id"], latest_run.id)
        self.assertEqual(cards["itc_2b"]["signals"]["itc_decided_items"], 3)
        self.assertEqual(cards["itc_2b"]["signals"]["itc_pending_items"], 1)
        self.assertEqual(cards["itc_2b"]["signals"]["portal_amended_rows"], 1)
        self.assertEqual(cards["itc_2b"]["signals"]["portal_vendor_revised_rows"], 1)
        self.assertEqual(cards["itc_2b"]["signals"]["ims_pending_rows"], 1)
        self.assertTrue(any(warning["code"] == "GST_2B_AMENDED_OR_REVISED_ROWS" for warning in cards["itc_2b"]["warnings"]))
        self.assertTrue(any(warning["code"] == "GST_IMS_ACTION_REVIEW" for warning in cards["itc_2b"]["warnings"]))
        self.assertTrue(any(warning["code"] == "GST_ITC_DECISION_PENDING" for warning in cards["itc_2b"]["warnings"]))
        self.assertTrue(any(warning["code"] == "GST_ITC_DECISION_EXCEPTION" for warning in cards["itc_2b"]["warnings"]))

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
