from __future__ import annotations

import io
from datetime import datetime
from unittest.mock import patch

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, EntityPolicy, GstRegistrationType, SubEntity
from gst_reconciliation.models import (
    GstImportedReturn,
    GstImportedReturnRow,
    GstReconciliationActionLog,
    GstReconciliationItem,
    GstMismatchReason,
    GstReconciliationRun,
)
from gst_reconciliation.services.adapters import PurchaseGstr2bBatchAdapter
from gst_reconciliation.services.importing import Gstr2bImportPipeline
from gst_reconciliation.services.normalization import normalize_doc_type, normalize_gstin, normalize_invoice_number
from gst_reconciliation.services.run_service import GstReconciliationRunLifecycleService
from gst_reconciliation.services.source_documents import SourceDocumentProviderRegistry
from purchase.models.gstr2b_models import Gstr2bImportBatch, Gstr2bImportRow
from purchase.models.purchase_core import PurchaseInvoiceHeader
from rbac.models import Role, RolePermission, UserRoleAssignment
from sales.models.sales_core import SalesInvoiceHeader
from subscriptions.services import SubscriptionService
from vouchers.models.voucher_core import VoucherHeader

_USE_DEFAULT_ENTITY = object()


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[], RBAC_DEV_ALLOW_ALL_ACCESS=True)
class GstReconciliationPhaseOneTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="gst-recon-user",
            email="gst-recon@example.com",
            password="pass123",
        )
        self.gst_registration_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="GST Recon Entity",
            legalname="GST Recon Entity Pvt Ltd",
            GstRegitrationType=self.gst_registration_type,
            createdby=self.user,
        )
        EntityPolicy.objects.create(entity=self.entity, createdby=self.user)
        self.subentity = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Head Office",
        )
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )

    def test_model_creation_supports_core_scope_and_statuses(self):
        imported_return = GstImportedReturn.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            gst_registration_gstin="29ABCDE1234F1Z5",
            return_type=GstImportedReturn.ReturnType.GSTR2B,
            return_period="2026-04",
            source=GstImportedReturn.Source.MANUAL_ENTRY,
            status=GstImportedReturn.Status.UPLOADED,
            created_by=self.user,
            updated_by=self.user,
        )
        run = GstReconciliationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            gst_registration_gstin="29ABCDE1234F1Z5",
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            return_period="2026-04",
            imported_return=imported_return,
            created_by=self.user,
            updated_by=self.user,
        )
        item = GstReconciliationItem.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            run=run,
            match_key="29ABCDE1234F1Z5|INV-001",
            source_document_type="purchase_gstr2b_row",
            source_document_id="1",
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertEqual(run.status, GstReconciliationRun.Status.DRAFT)
        self.assertEqual(imported_return.return_type, GstImportedReturn.ReturnType.GSTR2B)
        self.assertEqual(item.match_status, GstReconciliationItem.MatchStatus.NOT_CHECKED)

    def test_lifecycle_transitions_create_action_logs(self):
        run = GstReconciliationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            return_period="2026-04",
            status=GstReconciliationRun.Status.IMPORTED,
            created_by=self.user,
            updated_by=self.user,
        )
        GstReconciliationRunLifecycleService.submit_run(run=run, user=self.user, comment="Ready")
        run.refresh_from_db()
        self.assertEqual(run.status, GstReconciliationRun.Status.READY_FOR_REVIEW)
        GstReconciliationRunLifecycleService.start_review(run=run, user=self.user, comment="Checking")
        run.refresh_from_db()
        self.assertEqual(run.status, GstReconciliationRun.Status.IN_REVIEW)
        GstReconciliationRunLifecycleService.approve_run(run=run, user=self.user, comment="Looks good")
        run.refresh_from_db()
        self.assertEqual(run.status, GstReconciliationRun.Status.APPROVED)
        GstReconciliationRunLifecycleService.close_run(run=run, user=self.user, comment="Closed")
        run.refresh_from_db()
        self.assertEqual(run.status, GstReconciliationRun.Status.CLOSED)
        self.assertTrue(
            GstReconciliationActionLog.objects.filter(
                run=run,
                action_type=GstReconciliationActionLog.ActionType.CLOSED,
            ).exists()
        )

    def test_purchase_gstr2b_adapter_builds_run_and_items_without_mutating_existing_api(self):
        batch = Gstr2bImportBatch.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            period="2026-04",
            source="gstr2b",
            reference="apr-2026.xlsx",
            imported_by=self.user,
        )
        Gstr2bImportRow.objects.create(
            batch=batch,
            supplier_gstin="29ABCDE1234F1Z5",
            supplier_name="Vendor One",
            supplier_invoice_number="INV-001",
            doc_type="INV",
            taxable_value="100.00",
            cgst="9.00",
            sgst="9.00",
            match_status="MATCHED",
        )
        result = PurchaseGstr2bBatchAdapter.build_run_from_batch(batch_id=batch.id, user=self.user)
        self.assertTrue(result.created)
        self.assertEqual(result.run.reconciliation_type, GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE)
        self.assertEqual(result.run.status, GstReconciliationRun.Status.IMPORTED)
        self.assertEqual(result.run.items.count(), 1)
        item = result.run.items.first()
        self.assertEqual(item.match_status, GstReconciliationItem.MatchStatus.MATCHED)
        self.assertEqual(item.resolution_status, GstReconciliationItem.ResolutionStatus.AUTO_MATCHED)
        self.assertEqual(result.imported_return.source, GstImportedReturn.Source.ADAPTER)
        self.assertTrue(
            GstReconciliationActionLog.objects.filter(
                run=result.run,
                action_type=GstReconciliationActionLog.ActionType.IMPORTED,
            ).exists()
        )


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[], RBAC_DEV_ALLOW_ALL_ACCESS=True)
class GstReconciliationPhaseTwoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="gst-recon-p2-user",
            email="gst-recon-p2@example.com",
            password="pass123",
        )
        self.gst_registration_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="GST Recon P2 Entity",
            legalname="GST Recon P2 Entity Pvt Ltd",
            GstRegitrationType=self.gst_registration_type,
            createdby=self.user,
        )
        EntityPolicy.objects.create(entity=self.entity, createdby=self.user)
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch 1")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )

    def test_normalization_utilities(self):
        self.assertEqual(normalize_gstin(" 29abcde1234f1z5 "), "29ABCDE1234F1Z5")
        self.assertEqual(normalize_invoice_number(" inv/001-a "), "INV001A")
        self.assertEqual(normalize_doc_type("credit_note"), "CN")

    def test_json_import_creates_immutable_rows_and_run(self):
        payload = {
            "data": [
                {
                    "supplier_gstin": "29ABCDE1234F1Z5",
                    "supplier_name": "Vendor One",
                    "supplier_invoice_number": "INV/001-A",
                    "supplier_invoice_date": "2026-04-12",
                    "doc_type": "invoice",
                    "taxable_value": "100.00",
                    "cgst": "9.00",
                    "sgst": "9.00",
                }
            ]
        }
        imported_return, run = Gstr2bImportPipeline.import_json(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            user=self.user,
            return_period="2026-04",
            payload=payload,
            create_run=True,
            tolerance_config_json={"amount_tolerance": "2.00"},
        )
        self.assertEqual(imported_return.status, GstImportedReturn.Status.CONSUMED)
        self.assertEqual(imported_return.rows.count(), 1)
        row = imported_return.rows.first()
        self.assertEqual(row.invoice_number_normalized, "INV001A")
        self.assertEqual(row.counterparty_gstin_normalized, "29ABCDE1234F1Z5")
        self.assertIsNotNone(run)
        self.assertEqual(run.match_strategy_code, "gstr2b_purchase_portal")
        self.assertEqual(run.tolerance_config_json["amount_tolerance"], "2.00")
        self.assertEqual(run.items.count(), 1)

    def test_excel_import_creates_normalized_rows(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "2B"
        sheet.append(
            [
                "Supplier GSTIN",
                "Supplier Name",
                "Invoice No",
                "Invoice Date",
                "Doc Type",
                "Taxable Value",
                "CGST",
                "SGST",
                "IGST",
                "CESS",
            ]
        )
        sheet.append(["29ABCDE1234F1Z5", "Vendor One", "INV-002", "12/04/2026", "INV", 200, 18, 18, 0, 0])
        content = SimpleUploadedFile("gstr2b.xlsx", b"", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        stream = io.BytesIO()
        workbook.save(stream)
        imported_return, _ = Gstr2bImportPipeline.import_excel(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            user=self.user,
            return_period="2026-04",
            filename=content.name,
            content=stream.getvalue(),
            create_run=False,
        )
        row = imported_return.rows.get()
        self.assertEqual(row.invoice_number_normalized, "INV002")
        self.assertEqual(str(row.total_amount), "236.00")

    def test_portal_matcher_generates_confidence_and_structured_reasons(self):
        PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor_gstin="29ABCDE1234F1Z5",
            supplier_invoice_number="INV-003",
            supplier_invoice_date=datetime(2026, 4, 10).date(),
            total_taxable="300.00",
            total_cgst="27.00",
            total_sgst="27.00",
            total_igst="0.00",
            total_cess="0.00",
            created_by=self.user,
        )
        imported_return, run = Gstr2bImportPipeline.import_json(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            user=self.user,
            return_period="2026-04",
            payload={
                "rows": [
                    {
                        "supplier_gstin": "29ABCDE1234F1Z5",
                        "supplier_invoice_number": "INV/003",
                        "supplier_invoice_date": "2026-04-10",
                        "doc_type": "INV",
                        "taxable_value": "300.00",
                        "cgst": "27.00",
                        "sgst": "27.00",
                    }
                ]
            },
            create_run=True,
        )
        self.assertIsNotNone(imported_return)
        GstReconciliationRunLifecycleService.execute_matching(run=run, user=self.user)
        item = run.items.get()
        item.refresh_from_db()
        self.assertEqual(item.match_status, GstReconciliationItem.MatchStatus.MATCHED)
        self.assertEqual(item.resolution_status, GstReconciliationItem.ResolutionStatus.AUTO_MATCHED)
        self.assertGreaterEqual(float(item.match_confidence_score), 90.0)
        self.assertEqual(item.linked_document_type, "purchase_invoice_header")
        self.assertEqual(item.mismatch_reasons.count(), 0)

    def test_portal_matcher_generates_structured_mismatch_reasons(self):
        PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor_gstin="29ABCDE1234F1Z5",
            supplier_invoice_number="INV-004",
            supplier_invoice_date=datetime(2026, 4, 10).date(),
            total_taxable="300.00",
            total_cgst="27.00",
            total_sgst="27.00",
            total_igst="0.00",
            total_cess="0.00",
            created_by=self.user,
        )
        _, run = Gstr2bImportPipeline.import_json(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            user=self.user,
            return_period="2026-04",
            payload={
                "rows": [
                    {
                        "supplier_gstin": "29ABCDE1234F1Z5",
                        "supplier_invoice_number": "INV-004-X",
                        "supplier_invoice_date": "2026-04-15",
                        "doc_type": "INV",
                        "taxable_value": "350.00",
                        "cgst": "31.50",
                        "sgst": "31.50",
                    }
                ]
            },
            create_run=True,
            tolerance_config_json={"date_tolerance_days": 1},
        )
        GstReconciliationRunLifecycleService.execute_matching(run=run, user=self.user)
        item = run.items.get()
        self.assertIn(item.match_status, {GstReconciliationItem.MatchStatus.PARTIAL, GstReconciliationItem.MatchStatus.MISMATCHED})
        self.assertGreater(item.mismatch_reasons.count(), 0)
        codes = set(item.mismatch_reasons.values_list("code", flat=True))
        self.assertTrue({"INVOICE_NUMBER_MISMATCH", "INVOICE_DATE_MISMATCH", "TOTAL_AMOUNT_MISMATCH"} & codes)


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[], RBAC_DEV_ALLOW_ALL_ACCESS=True)
class GstReconciliationPhaseThreeTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="gst-recon-p3-user",
            email="gst-recon-p3@example.com",
            password="pass123",
        )
        self.reviewer = User.objects.create_user(
            username="gst-recon-reviewer",
            email="gst-recon-reviewer@example.com",
            password="pass123",
        )
        self.other_user = User.objects.create_user(
            username="gst-recon-other",
            email="gst-recon-other@example.com",
            password="pass123",
        )
        self.gst_registration_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="GST Recon P3 Entity",
            legalname="GST Recon P3 Entity Pvt Ltd",
            GstRegitrationType=self.gst_registration_type,
            createdby=self.user,
        )
        EntityPolicy.objects.create(entity=self.entity, createdby=self.user)
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch 1")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.purchase_invoice = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor_gstin="29ABCDE1234F1Z5",
            supplier_invoice_number="INV-900",
            supplier_invoice_date=datetime(2026, 4, 10).date(),
            bill_date=datetime(2026, 4, 10).date(),
            total_taxable="500.00",
            total_cgst="45.00",
            total_sgst="45.00",
            total_igst="0.00",
            total_cess="0.00",
            created_by=self.user,
        )
        _, self.run = Gstr2bImportPipeline.import_json(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            user=self.user,
            return_period="2026-04",
            payload={
                "rows": [
                    {
                        "supplier_gstin": "29ABCDE1234F1Z5",
                        "supplier_invoice_number": "INV-900-X",
                        "supplier_invoice_date": "2026-04-14",
                        "doc_type": "INV",
                        "taxable_value": "510.00",
                        "cgst": "45.90",
                        "sgst": "45.90",
                    },
                    {
                        "supplier_gstin": "29ABCDE1234F1Z5",
                        "supplier_invoice_number": "INV-901",
                        "supplier_invoice_date": "2026-04-15",
                        "doc_type": "INV",
                        "taxable_value": "100.00",
                        "cgst": "9.00",
                        "sgst": "9.00",
                    },
                ]
            },
            create_run=True,
        )
        GstReconciliationRunLifecycleService.execute_matching(run=self.run, user=self.user)
        self.items = list(self.run.items.order_by("id"))
        self.client.force_authenticate(user=self.user)

    def test_manual_match_and_unmatch_api(self):
        item = self.items[0]
        match_url = reverse("gst_reconciliation_api:item-manual-match", args=[item.id])
        response = self.client.post(
            match_url,
            {"source_document_type": "purchase_invoice_header", "source_document_id": str(self.purchase_invoice.id), "note": "reviewed"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.match_status, GstReconciliationItem.MatchStatus.MANUALLY_RESOLVED)
        self.assertEqual(item.resolution_status, GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED)
        self.assertEqual(item.linked_document_id, str(self.purchase_invoice.id))
        unmatch_url = reverse("gst_reconciliation_api:item-manual-unmatch", args=[item.id])
        response = self.client.post(unmatch_url, {"note": "undo"}, format="json")
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.linked_document_id, None)
        self.assertEqual(item.resolution_status, GstReconciliationItem.ResolutionStatus.PENDING_REVIEW)

    def test_assignment_blocks_unassigned_user_and_accept_mismatch(self):
        item = self.items[0]
        assign_url = reverse("gst_reconciliation_api:item-assign", args=[item.id])
        response = self.client.post(assign_url, {"reviewer_id": self.reviewer.id, "note": "please review"}, format="json")
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.assigned_reviewer_id, self.reviewer.id)
        self.assertEqual(item.assigned_by_id, self.user.id)
        self.client.force_authenticate(user=self.other_user)
        accept_url = reverse("gst_reconciliation_api:item-accept-mismatch", args=[item.id])
        response = self.client.post(accept_url, {"note": "cannot review"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.post(accept_url, {"note": "accepted as valid mismatch"}, format="json")
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.resolution_status, GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH)
        self.assertEqual(item.accepted_mismatch_by_id, self.reviewer.id)

    def test_bulk_actions_and_dashboard_apis(self):
        response = self.client.post(
            reverse("gst_reconciliation_api:items-bulk-assign"),
            {"action": "assign", "item_ids": [item.id for item in self.items], "reviewer_id": self.reviewer.id, "note": "batch assign"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success_count"], 2)
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.post(
            reverse("gst_reconciliation_api:items-bulk-ignore"),
            {"action": "ignore", "item_ids": [self.items[1].id], "note": "ignore this"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        dashboard_url = reverse("gst_reconciliation_api:run-summary", args=[self.run.id])
        dashboard = self.client.get(dashboard_url)
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("pending_review_count", dashboard.json())
        analytics_url = reverse("gst_reconciliation_api:run-supplier-analytics", args=[self.run.id])
        analytics = self.client.get(analytics_url)
        self.assertEqual(analytics.status_code, 200)
        self.assertTrue(len(analytics.json()["results"]) >= 1)
        self.assertTrue(
            GstReconciliationActionLog.objects.filter(
                run=self.run,
                action_type=GstReconciliationActionLog.ActionType.BULK_ACTION,
            ).exists()
        )

    def test_notes_and_bulk_mark_reviewed_and_unmatch_routes(self):
        item = self.items[0]
        notes_url = reverse("gst_reconciliation_api:item-notes", args=[item.id])
        response = self.client.post(notes_url, {"reviewer_notes": "check this", "resolution_notes": "pending"}, format="json")
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.reviewer_note, "check this")
        self.assertEqual(item.resolution_note, "pending")
        bulk_reviewed = self.client.post(
            reverse("gst_reconciliation_api:items-bulk-mark-reviewed"),
            {"action": "mark_reviewed", "item_ids": [item.id], "note": "reviewed in bulk"},
            format="json",
        )
        self.assertEqual(bulk_reviewed.status_code, 200)
        item.refresh_from_db()
        self.assertIn(
            item.resolution_status,
            {
                GstReconciliationItem.ResolutionStatus.PARTIAL_MATCH,
                GstReconciliationItem.ResolutionStatus.MISMATCH,
                GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
                GstReconciliationItem.ResolutionStatus.RESOLVED,
            },
        )
        bulk_unmatch = self.client.post(
            reverse("gst_reconciliation_api:items-bulk-unmatch"),
            {"action": "unmatch", "item_ids": [item.id], "note": "clear link"},
            format="json",
        )
        self.assertEqual(bulk_unmatch.status_code, 200)
        self.assertEqual(bulk_unmatch.json()["failed_count"], 0)


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[], RBAC_DEV_ALLOW_ALL_ACCESS=True)
class GstReconciliationPhaseFourTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="gst-recon-p4-user",
            email="gst-recon-p4@example.com",
            password="pass123",
        )
        self.gst_registration_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="GST Recon P4 Entity",
            legalname="GST Recon P4 Entity Pvt Ltd",
            GstRegitrationType=self.gst_registration_type,
            createdby=self.user,
        )
        EntityPolicy.objects.create(entity=self.entity, createdby=self.user)
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch 1")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.purchase_invoice = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor_name="Vendor Four",
            vendor_gstin="29ABCDE1234F1Z5",
            supplier_invoice_number="PINV-400",
            supplier_invoice_date=datetime(2026, 4, 10).date(),
            total_taxable="500.00",
            total_cgst="45.00",
            total_sgst="45.00",
            total_igst="0.00",
            total_cess="0.00",
            grand_total="590.00",
            created_by=self.user,
        )
        self.sales_invoice = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            invoice_number="SINV-401",
            bill_date=datetime(2026, 4, 10).date(),
            customer_name="Customer Four",
            customer_gstin="27ABCDE1234F1Z5",
            seller_gstin="29ABCDE1234F1Z5",
            total_taxable_value="800.00",
            total_cgst="72.00",
            total_sgst="72.00",
            total_igst="0.00",
            total_cess="0.00",
            grand_total="944.00",
            created_by=self.user,
        )
        self.voucher = VoucherHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_code="JV-402",
            voucher_type=VoucherHeader.VoucherType.JOURNAL,
            total_debit_amount="1000.00",
            total_credit_amount="1000.00",
            created_by=self.user,
        )
        self.sales_run = GstReconciliationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR1_SALES,
            return_period="2026-04",
            created_by=self.user,
            updated_by=self.user,
        )
        self.sales_item = GstReconciliationItem.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            run=self.sales_run,
            direction=GstReconciliationItem.Direction.SALES,
            match_key="GSTR1|SINV401",
            source_document_type="gst_imported_return_row",
            source_document_id="1",
            invoice_number="SINV401",
            created_by=self.user,
            updated_by=self.user,
        )
        self.imported_return = GstImportedReturn.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            return_type=GstImportedReturn.ReturnType.GSTR2B,
            return_period="2026-04",
            source=GstImportedReturn.Source.JSON_UPLOAD,
            status=GstImportedReturn.Status.CONSUMED,
            imported_by=self.user,
            created_by=self.user,
            updated_by=self.user,
        )
        self.imported_row = GstImportedReturnRow.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            imported_return=self.imported_return,
            row_no=1,
            row_hash="row-hash-1",
            counterparty_gstin="27ABCDE1234F1Z5",
            counterparty_gstin_normalized="27ABCDE1234F1Z5",
            counterparty_name="Customer Four",
            invoice_number="SINV-401",
            invoice_number_normalized="SINV401",
            taxable_value="800.00",
            cgst="72.00",
            sgst="72.00",
            total_amount="944.00",
            normalized_row_json={"invoice_number": "SINV401"},
            created_by=self.user,
            updated_by=self.user,
        )
        self.sales_item.source_document_id = str(self.imported_row.id)
        self.sales_item.save(update_fields=["source_document_id", "updated_at"])
        self.client.force_authenticate(user=self.user)

    def test_source_document_provider_registry_exposes_expected_providers(self):
        provider = SourceDocumentProviderRegistry.get_provider("purchase_invoice_header")
        self.assertEqual(provider.provider_code, "purchase")
        sales_provider = SourceDocumentProviderRegistry.get_provider("sales_invoice_header")
        self.assertTrue(sales_provider.supports_run_type(GstReconciliationRun.ReconciliationType.GSTR1_SALES))
        voucher_provider = SourceDocumentProviderRegistry.get_provider("voucher_header")
        metadata = voucher_provider.to_metadata(self.voucher)
        self.assertEqual(metadata.source_document_id, str(self.voucher.id))
        self.assertEqual(metadata.total_amount, "1000.00")

    def test_generic_manual_match_routes_through_provider_registry(self):
        response = self.client.post(
            reverse("gst_reconciliation_api:item-manual-match", args=[self.sales_item.id]),
            {
                "source_document_type": "sales_invoice_header",
                "source_document_id": str(self.sales_invoice.id),
                "note": "matched to live sales document",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.sales_item.refresh_from_db()
        self.assertEqual(self.sales_item.linked_document_type, "sales_invoice_header")
        self.assertEqual(self.sales_item.linked_document_id, str(self.sales_invoice.id))
        self.assertEqual(self.sales_item.resolution_status, GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED)
        log = GstReconciliationActionLog.objects.filter(
            item=self.sales_item,
            action_type=GstReconciliationActionLog.ActionType.ITEM_MANUAL_MATCHED,
        ).latest("id")
        self.assertEqual(log.details_json["provider_code"], "sales")

    def test_source_document_search_and_detail_apis_return_unified_metadata(self):
        search_response = self.client.get(
            reverse("gst_reconciliation_api:source-document-search"),
            {
                "item_id": self.sales_item.id,
                "source_document_type": "sales_invoice_header",
                "query": "SINV-401",
            },
        )
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()["count"], 1)
        result = search_response.json()["results"][0]
        self.assertEqual(result["provider_code"], "sales")
        self.assertEqual(result["document_number"], "SINV-401")
        self.assertIn("normalized_comparison_payload", result)
        detail_response = self.client.get(
            reverse(
                "gst_reconciliation_api:source-document-detail",
                args=["voucher_header", str(self.voucher.id)],
            ),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
            },
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["provider_code"], "voucher")
        self.assertEqual(detail_response.json()["document_number"], "JV-402")

    def test_manual_match_rejects_provider_not_supported_for_run_type(self):
        response = self.client.post(
            reverse("gst_reconciliation_api:item-manual-match", args=[self.sales_item.id]),
            {
                "source_document_type": "purchase_invoice_header",
                "source_document_id": str(self.purchase_invoice.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not support reconciliation type", response.json()["detail"])

    def test_item_grid_and_detail_and_queue_endpoints(self):
        GstReconciliationItem.objects.filter(pk=self.sales_item.id).update(
            resolution_status=GstReconciliationItem.ResolutionStatus.MISMATCH,
            match_status=GstReconciliationItem.MatchStatus.MISMATCHED,
            assigned_reviewer=self.user,
            counterparty_gstin="27ABCDE1234F1Z5",
        )
        grid_response = self.client.get(
            reverse("gst_reconciliation_api:item-grid"),
            {
                "run": self.sales_run.id,
                "resolution_status": GstReconciliationItem.ResolutionStatus.MISMATCH,
                "supplier_gstin": "27ABCDE1234F1Z5",
                "unresolved_only": "true",
            },
        )
        self.assertEqual(grid_response.status_code, 200)
        self.assertEqual(grid_response.json()["meta"]["count"], 1)
        detail_response = self.client.get(reverse("gst_reconciliation_api:item-detail", args=[self.sales_item.id]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertIsNotNone(detail_response.json()["imported_portal_row"])
        queue_response = self.client.get(
            reverse("gst_reconciliation_api:reviewer-queue"),
            {
                "entity": self.entity.id,
                "reviewer_id": self.user.id,
            },
        )
        self.assertEqual(queue_response.status_code, 200)
        self.assertIn("summary", queue_response.json()["meta"])

    def test_run_summary_list_endpoint(self):
        response = self.client.get(
            reverse("gst_reconciliation_api:run-summary-list"),
            {
                "entity": self.entity.id,
                "reconciliation_type": GstReconciliationRun.ReconciliationType.GSTR1_SALES,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["meta"]["count"], 1)
        self.assertEqual(response.json()["rows"][0]["id"], self.sales_run.id)


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class GstReconciliationPhaseEightHardeningTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="gst-recon-p8-user",
            email="gst-recon-p8@example.com",
            password="pass123",
        )
        self.other_user = User.objects.create_user(
            username="gst-recon-p8-other",
            email="gst-recon-p8-other@example.com",
            password="pass123",
        )
        self.gst_registration_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="GST Recon P8 Entity",
            legalname="GST Recon P8 Entity Pvt Ltd",
            GstRegitrationType=self.gst_registration_type,
            createdby=self.user,
        )
        self.other_entity = Entity.objects.create(
            entityname="GST Recon P8 Other",
            legalname="GST Recon P8 Other Pvt Ltd",
            GstRegitrationType=self.gst_registration_type,
            createdby=self.other_user,
        )
        EntityPolicy.objects.create(entity=self.entity, createdby=self.user)
        EntityPolicy.objects.create(entity=self.other_entity, createdby=self.other_user)
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch 1")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.run = GstReconciliationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            gst_registration_gstin="29ABCDE1234F1Z5",
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            return_period="2026-04",
            status=GstReconciliationRun.Status.IN_REVIEW,
            created_by=self.user,
            updated_by=self.user,
        )
        self.item = GstReconciliationItem.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            run=self.run,
            direction=GstReconciliationItem.Direction.PURCHASE,
            match_key="29SUPP|PINV-1",
            source_document_type="gst_imported_return_row",
            source_document_id="1",
            gstin="29ABCDE1234F1Z5",
            counterparty_gstin="29SUPPL1234F1Z5",
            invoice_number="PINV-1",
            invoice_date=datetime(2026, 4, 10).date(),
            resolution_status=GstReconciliationItem.ResolutionStatus.PENDING_REVIEW,
            match_status=GstReconciliationItem.MatchStatus.MISMATCHED,
            created_by=self.user,
            updated_by=self.user,
        )
        self.purchase_invoice_same_scope = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor_name="Vendor Good",
            vendor_gstin="29SUPPL1234F1Z5",
            supplier_invoice_number="PINV-1",
            supplier_invoice_date=datetime(2026, 4, 10).date(),
            bill_date=datetime(2026, 4, 10).date(),
            total_taxable="500.00",
            total_cgst="45.00",
            total_sgst="45.00",
            grand_total="590.00",
            created_by=self.user,
        )
        self.purchase_invoice_wrong_period = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor_name="Vendor Wrong Period",
            vendor_gstin="29SUPPL1234F1Z5",
            supplier_invoice_number="PINV-2",
            supplier_invoice_date=datetime(2026, 5, 10).date(),
            bill_date=datetime(2026, 5, 10).date(),
            total_taxable="500.00",
            total_cgst="45.00",
            total_sgst="45.00",
            grand_total="590.00",
            created_by=self.user,
        )
        self.imported_return = GstImportedReturn.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            return_type=GstImportedReturn.ReturnType.GSTR2B,
            return_period="2026-04",
            source=GstImportedReturn.Source.JSON_UPLOAD,
            status=GstImportedReturn.Status.CONSUMED,
            imported_by=self.user,
            created_by=self.user,
            updated_by=self.user,
        )
        self.imported_row = GstImportedReturnRow.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            imported_return=self.imported_return,
            row_no=1,
            row_hash="immutable-row",
            counterparty_gstin="29SUPPL1234F1Z5",
            counterparty_gstin_normalized="29SUPPL1234F1Z5",
            invoice_number="PINV-1",
            invoice_number_normalized="PINV1",
            taxable_value="500.00",
            cgst="45.00",
            sgst="45.00",
            total_amount="590.00",
            raw_row_json={"invoice_number": "PINV-1"},
            normalized_row_json={"invoice_number": "PINV1"},
            created_by=self.user,
            updated_by=self.user,
        )
        self.client.force_authenticate(user=self.user)

    def _permission_patch(self, permissions):
        return patch(
            "gst_reconciliation.services.access.EffectivePermissionService.permission_codes_for_user",
            return_value=set(permissions),
        )

    def _entity_access_patch(self, entity=_USE_DEFAULT_ENTITY):
        return patch(
            "gst_reconciliation.services.access.EffectivePermissionService.entity_for_user",
            return_value=self.entity if entity is _USE_DEFAULT_ENTITY else entity,
        )

    def test_run_detail_requires_view_permission(self):
        with self._entity_access_patch(), self._permission_patch(set()):
            response = self.client.get(reverse("gst_reconciliation_api:run-detail", args=[self.run.id]))
        self.assertEqual(response.status_code, 403)

    def test_item_detail_rejects_other_entity_scope(self):
        with self._entity_access_patch(entity=None), self._permission_patch({"gst.reconciliation.view"}):
            response = self.client.get(reverse("gst_reconciliation_api:item-detail", args=[self.item.id]))
        self.assertEqual(response.status_code, 403)

    def test_manual_match_rejects_wrong_period_document(self):
        with self._entity_access_patch(), self._permission_patch({"gst.reconciliation.view", "gst.reconciliation.review"}):
            response = self.client.post(
                reverse("gst_reconciliation_api:item-manual-match", args=[self.item.id]),
                {
                    "source_document_type": "purchase_invoice_header",
                    "source_document_id": str(self.purchase_invoice_wrong_period.id),
                },
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("return period", response.json()["detail"])

    def test_closed_run_cannot_be_modified(self):
        self.run.status = GstReconciliationRun.Status.CLOSED
        self.run.save(update_fields=["status"])
        with self._entity_access_patch(), self._permission_patch({"gst.reconciliation.view", "gst.reconciliation.review"}):
            response = self.client.post(
                reverse("gst_reconciliation_api:item-ignore", args=[self.item.id]),
                {"note": "ignore on closed run"},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Closed GST reconciliation runs cannot be modified", response.json()["detail"])

    def test_bulk_action_handles_partial_failures_safely(self):
        closed_run = GstReconciliationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            gst_registration_gstin="29ABCDE1234F1Z5",
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            return_period="2026-04",
            revision_no=2,
            status=GstReconciliationRun.Status.CLOSED,
            created_by=self.user,
            updated_by=self.user,
        )
        second_item = GstReconciliationItem.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            run=closed_run,
            direction=GstReconciliationItem.Direction.PURCHASE,
            match_key="29SUPP|PINV-2",
            source_document_type="gst_imported_return_row",
            source_document_id="2",
            counterparty_gstin="29SUPPL1234F1Z5",
            invoice_number="PINV-2",
            match_status=GstReconciliationItem.MatchStatus.MISMATCHED,
            resolution_status=GstReconciliationItem.ResolutionStatus.PENDING_REVIEW,
            created_by=self.user,
            updated_by=self.user,
        )
        with self._entity_access_patch(), self._permission_patch({"gst.reconciliation.view", "gst.reconciliation.review"}):
            response = self.client.post(
                reverse("gst_reconciliation_api:items-bulk-ignore"),
                {"action": "ignore", "item_ids": [self.item.id, second_item.id], "note": "bulk ignore"},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["success_count"], 1)
        self.assertEqual(payload["failed_count"], 1)
        self.assertEqual(len(payload["errors"]), 1)


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[], RBAC_DEV_ALLOW_ALL_ACCESS=True, GST_RECON_CACHE_ENABLED=False)
class GstReconciliationPhaseNinePerformanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="gst-recon-p9-user",
            email="gst-recon-p9@example.com",
            password="pass123",
        )
        self.gst_registration_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="GST Recon P9 Entity",
            legalname="GST Recon P9 Entity Pvt Ltd",
            GstRegitrationType=self.gst_registration_type,
            createdby=self.user,
        )
        EntityPolicy.objects.create(entity=self.entity, createdby=self.user)
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Perf Branch")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.imported_return = GstImportedReturn.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            gst_registration_gstin="29ABCDE1234F1Z5",
            return_type=GstImportedReturn.ReturnType.GSTR2B,
            return_period="2026-04",
            source=GstImportedReturn.Source.JSON_UPLOAD,
            status=GstImportedReturn.Status.CONSUMED,
            imported_by=self.user,
            created_by=self.user,
            updated_by=self.user,
        )
        self.run = GstReconciliationRun.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            gst_registration_gstin="29ABCDE1234F1Z5",
            reconciliation_type=GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,
            return_period="2026-04",
            imported_return=self.imported_return,
            status=GstReconciliationRun.Status.IN_REVIEW,
            created_by=self.user,
            updated_by=self.user,
        )
        rows = []
        for i in range(80):
            gstin = f"29SUPP{i % 10:04d}F1Z5"[:15]
            rows.append(
                GstImportedReturnRow(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    imported_return=self.imported_return,
                    row_no=i + 1,
                    row_hash=f"perf-{i}",
                    counterparty_gstin=gstin,
                    counterparty_gstin_normalized=gstin,
                    counterparty_name=f"Supplier {i % 10}",
                    invoice_number=f"INV-{i:03d}",
                    invoice_number_normalized=f"INV{i:03d}",
                    invoice_date=datetime(2026, 4, 10).date(),
                    taxable_value="1000.00",
                    cgst="90.00",
                    sgst="90.00",
                    total_amount="1180.00",
                    normalized_row_json={"invoice_number": f"INV{i:03d}"},
                    created_by=self.user,
                    updated_by=self.user,
                )
            )
        GstImportedReturnRow.objects.bulk_create(rows, batch_size=80)
        created_rows = list(self.imported_return.rows.order_by("row_no"))
        self.imported_row = created_rows[0]
        items = []
        reason_items = []
        for i, row in enumerate(created_rows):
            match_status = [
                GstReconciliationItem.MatchStatus.MATCHED,
                GstReconciliationItem.MatchStatus.PARTIAL,
                GstReconciliationItem.MatchStatus.MISMATCHED,
                GstReconciliationItem.MatchStatus.MISSING_IN_BOOKS,
            ][i % 4]
            resolution_status = [
                GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
                GstReconciliationItem.ResolutionStatus.PARTIAL_MATCH,
                GstReconciliationItem.ResolutionStatus.MISMATCH,
                GstReconciliationItem.ResolutionStatus.PENDING_REVIEW,
            ][i % 4]
            items.append(
                GstReconciliationItem(
                    entity=self.entity,
                    entityfinid=self.entityfin,
                    subentity=self.subentity,
                    run=self.run,
                    direction=GstReconciliationItem.Direction.PURCHASE,
                    match_key=f"{row.counterparty_gstin}|{row.invoice_number}",
                    source_document_type="gst_imported_return_row",
                    source_document_id=str(row.id),
                    gstin="29ABCDE1234F1Z5",
                    counterparty_gstin=row.counterparty_gstin,
                    invoice_number=row.invoice_number,
                    invoice_date=row.invoice_date,
                    taxable_value_imported=row.taxable_value,
                    cgst_imported=row.cgst,
                    sgst_imported=row.sgst,
                    match_status=match_status,
                    resolution_status=resolution_status,
                    mismatch_count=0 if match_status == GstReconciliationItem.MatchStatus.MATCHED else 1,
                    created_by=self.user,
                    updated_by=self.user,
                )
            )
        GstReconciliationItem.objects.bulk_create(items, batch_size=80)
        for item in GstReconciliationItem.objects.filter(run=self.run, mismatch_count__gt=0)[:20]:
            reason_items.append(
                GstMismatchReason(
                    item=item,
                    code="TOTAL_AMOUNT_MISMATCH",
                    category="amount",
                    severity=GstMismatchReason.Severity.ERROR,
                    message="Total mismatch",
                )
            )
        GstMismatchReason.objects.bulk_create(reason_items, batch_size=20)

    def test_run_summary_query_count_is_bounded(self):
        from gst_reconciliation.services.dashboard_service import GstReconciliationDashboardService

        with CaptureQueriesContext(connection) as ctx:
            payload = GstReconciliationDashboardService.run_summary(run=self.run)
        self.assertEqual(payload["run_id"], self.run.id)
        self.assertLessEqual(len(ctx), 8)

    def test_supplier_analytics_query_count_is_bounded(self):
        from gst_reconciliation.services.dashboard_service import GstReconciliationDashboardService

        with CaptureQueriesContext(connection) as ctx:
            payload = GstReconciliationDashboardService.supplier_mismatch_analytics(run=self.run)
        self.assertTrue(len(payload) > 0)
        self.assertLessEqual(len(ctx), 6)

    def test_reviewer_queue_summary_query_count_is_bounded(self):
        from gst_reconciliation.services.ui_service import GstReconciliationUiService

        queryset = self.run.items.exclude(
            resolution_status__in=[
                GstReconciliationItem.ResolutionStatus.AUTO_MATCHED,
                GstReconciliationItem.ResolutionStatus.MANUAL_MATCHED,
                GstReconciliationItem.ResolutionStatus.ACCEPTED_MISMATCH,
                GstReconciliationItem.ResolutionStatus.IGNORED,
                GstReconciliationItem.ResolutionStatus.RESOLVED,
            ]
        )
        with CaptureQueriesContext(connection) as ctx:
            payload = GstReconciliationUiService.build_reviewer_queue_summary(queryset=queryset)
        self.assertGreaterEqual(payload["total_rows"], 1)
        self.assertLessEqual(len(ctx), 2)

    def test_imported_rows_are_immutable(self):
        self.imported_row.invoice_number = "MUTATED"
        with self.assertRaises(ValidationError):
            self.imported_row.save()


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[], RBAC_DEV_ALLOW_ALL_ACCESS=False)
class GstReconciliationPhaseTenRBACTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="gst-recon-rbac-user",
            email="gst-recon-rbac@example.com",
            password="pass123",
        )
        self.assigner = User.objects.create_user(
            username="gst-recon-rbac-admin",
            email="gst-recon-rbac-admin@example.com",
            password="pass123",
        )
        self.gst_registration_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="GST Recon RBAC Entity",
            legalname="GST Recon RBAC Entity Pvt Ltd",
            GstRegitrationType=self.gst_registration_type,
            createdby=self.assigner,
        )
        self.entity.customer_account = SubscriptionService.ensure_customer_account(user=self.assigner)
        self.entity.save(update_fields=["customer_account"])
        EntityPolicy.objects.create(entity=self.entity, createdby=self.assigner)

    def test_grant_gst_reconciliation_access_command_creates_membership_role_and_assignment(self):
        call_command(
            "grant_gst_reconciliation_access",
            user=self.user.id,
            entity=self.entity.id,
            assigned_by=self.assigner.id,
            tenant_role="admin",
        )
        membership = self.user.customer_accesses.get(customer_account=self.entity.customer_account)
        self.assertEqual(membership.role, "admin")
        role = Role.objects.get(entity=self.entity, code="gst.reconciliation.pilot")
        permission_codes = set(
            RolePermission.objects.filter(role=role, effect=RolePermission.EFFECT_ALLOW)
            .values_list("permission__code", flat=True)
        )
        self.assertEqual(
            permission_codes,
            {
                "gst.reconciliation.view",
                "gst.reconciliation.review",
                "gst.reconciliation.manage",
            },
        )
        assignment = UserRoleAssignment.objects.get(user=self.user, entity=self.entity, role=role, subentity__isnull=True)
        self.assertTrue(assignment.isactive)
