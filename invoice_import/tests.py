from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
from financial.services import apply_normalized_profile_payload, create_account_with_synced_ledger
from invoice_import.models import ImportJob
from invoice_import.models import ImportProfile
from invoice_import.services import _write_csv_zip, commit_job, create_validated_job
from numbering.services import ensure_document_type, ensure_series
from invoice_import.views import (
    PurchaseInvoiceImportJobCommitAPIView,
    PurchaseInvoiceImportJobCreateAPIView,
    PurchaseInvoiceImportProfileListCreateAPIView,
    PurchaseInvoiceImportJobCommitAPIView,
    PurchaseInvoiceImportJobReviewAPIView,
    PurchaseInvoiceImportJobReconciliationAPIView,
    SalesInvoiceImportJobCommitAPIView,
    SalesInvoiceImportJobCreateAPIView,
    SalesInvoiceImportJobDetailAPIView,
    SalesInvoiceImportProfileDetailAPIView,
    SalesInvoiceImportProfileListCreateAPIView,
    SalesInvoiceImportTemplateAPIView,
)
from purchase.models import PurchaseInvoiceHeader
from purchase.models.purchase_ap import VendorBillOpenItem
from sales.models import SalesInvoiceHeader
from sales.models.sales_ar import CustomerBillOpenItem


@override_settings(AUTH_PASSWORD_VALIDATORS=[])
class InvoiceImportServiceTests(TestCase):
    def setUp(self):
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"invoice-import-{suffix}",
            email=f"invoice-import-{suffix}@example.com",
            password="pass123",
        )
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Legacy Import Entity",
            legalname="Legacy Import Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Head Office",
            is_head_office=True,
        )
        now = timezone.now()
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            year_code="FY2526",
            finstartyear=now - timedelta(days=180),
            finendyear=now + timedelta(days=180),
            createdby=self.user,
        )
        self.customer = self._create_party(
            name="Alpha Retail",
            partytype="Customer",
            gstin="27ABCDE1234F1Z5",
        )
        self.vendor = self._create_party(
            name="Vendor One",
            partytype="Vendor",
            gstin="27AACCV1234F1Z5",
        )

    def _create_party(self, *, name: str, partytype: str, gstin: str):
        account_row = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "accountname": name,
                "createdby": self.user,
            }
        )
        apply_normalized_profile_payload(
            account_row,
            compliance_data={"gstno": gstin},
            commercial_data={"partytype": partytype},
            createdby=self.user,
        )
        return account_row

    def _base_row(self, *, party_name: str, source_key: str, source_invoice_number: str) -> dict[str, object]:
        return {
            "entityfinid_id": self.entityfin.id,
            "subentity_id": self.subentity.id,
            "legacy_source_system": "legacy_erp",
            "legacy_source_key": source_key,
            "doc_type": "invoice",
            "status": "posted",
            "source_invoice_number": source_invoice_number,
            "bill_date": "2025-04-01",
            "due_date": "2025-04-30",
            "party_name": party_name,
            "total_taxable": "1000.00",
            "total_cgst": "90.00",
            "total_sgst": "90.00",
            "total_igst": "0.00",
            "total_cess": "0.00",
            "round_off": "0.00",
            "grand_total": "1180.00",
            "settled_amount": "400.00",
            "outstanding_amount": "780.00",
            "reference": "Opening balance carry-forward",
            "remarks": "Imported from legacy ERP",
            "original_source_key": "",
        }

    def _build_job(self, *, module: str, mode: str, detail_level: str, rows: list[dict[str, object]], stock_replay: bool = False, compliance_mode: str = ImportJob.ComplianceMode.PASSIVE, withholding_mode: str = ImportJob.WithholdingMode.PRESERVE_LEGACY) -> ImportJob:
        return create_validated_job(
            entity=self.entity,
            user=self.user,
            module=module,
            mode=mode,
            detail_level=detail_level,
            stock_replay=stock_replay,
            compliance_mode=compliance_mode,
            withholding_mode=withholding_mode,
            source_system="legacy_erp",
            filename="import.zip",
            fmt=ImportJob.FileFormat.CSV,
            file_bytes=_write_csv_zip(rows),
        )

    def test_sales_outstanding_header_only_commit_creates_legacy_invoice_and_open_item(self):
        row = self._base_row(
            party_name=self.customer.accountname,
            source_key="sales-open-1",
            source_invoice_number="S-LEG-001",
        )
        row.update(
            {
                "party_gstin": "27ABCDE1234F1Z5",
                "party_state_code": "27",
                "seller_gstin": "27AAAAA1111A1Z5",
                "seller_state_code": "27",
                "supply_category": SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                "taxability": SalesInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            }
        )
        job = self._build_job(
            module=ImportJob.Module.SALES,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            rows=[row],
        )

        self.assertEqual(job.status, ImportJob.Status.VALIDATED)
        job = commit_job(job=job, user=self.user)

        header = SalesInvoiceHeader.objects.get(legacy_source_key="sales-open-1")
        open_item = CustomerBillOpenItem.objects.get(header=header)
        self.assertEqual(job.status, ImportJob.Status.COMMITTED)
        self.assertTrue(header.is_legacy_imported)
        self.assertEqual(header.legacy_import_mode, ImportJob.Mode.OUTSTANDING_ONLY)
        self.assertEqual(header.outstanding_amount, Decimal("780.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("780.00"))

    def test_purchase_outstanding_header_only_commit_creates_legacy_invoice_and_open_item(self):
        row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-open-1",
            source_invoice_number="P-LEG-001",
        )
        row.update(
            {
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-001",
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
            }
        )
        job = self._build_job(
            module=ImportJob.Module.PURCHASE,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            rows=[row],
        )

        self.assertEqual(job.status, ImportJob.Status.VALIDATED)
        job = commit_job(job=job, user=self.user)

        header = PurchaseInvoiceHeader.objects.get(legacy_source_key="purchase-open-1")
        open_item = VendorBillOpenItem.objects.get(header=header)
        self.assertEqual(job.status, ImportJob.Status.COMMITTED)
        self.assertTrue(header.is_legacy_imported)
        self.assertEqual(header.legacy_import_mode, ImportJob.Mode.OUTSTANDING_ONLY)
        self.assertEqual(header.match_notes["legacy_settlement"]["outstanding_amount"], "780.00")
        self.assertEqual(open_item.outstanding_amount, Decimal("780.00"))

    def test_purchase_import_can_generate_finacc_document_number(self):
        doc_type = ensure_document_type(
            module="purchase",
            doc_key="PURCHASE_INVOICE",
            name="Purchase Invoice",
            default_code="PINV",
        )
        ensure_series(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            doc_type_id=doc_type.id,
            doc_code="PINV",
            prefix="PINV",
            start=1001,
            padding=4,
        )

        row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-finacc-num-1",
            source_invoice_number="LEG-P-0001",
        )
        row.update(
            {
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "LEG-P-0001",
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
            }
        )
        job = create_validated_job(
            entity=self.entity,
            user=self.user,
            module=ImportJob.Module.PURCHASE,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            stock_replay=False,
            compliance_mode=ImportJob.ComplianceMode.PASSIVE,
            withholding_mode=ImportJob.WithholdingMode.PRESERVE_LEGACY,
            document_number_strategy="generate_finacc",
            source_system="legacy_erp",
            filename="import.zip",
            fmt=ImportJob.FileFormat.CSV,
            file_bytes=_write_csv_zip([row]),
        )
        self.assertEqual(job.status, ImportJob.Status.VALIDATED)

        job = commit_job(job=job, user=self.user)
        header = PurchaseInvoiceHeader.objects.get(legacy_source_key="purchase-finacc-num-1")
        self.assertEqual(job.status, ImportJob.Status.COMMITTED)
        self.assertTrue(bool(header.doc_no))
        self.assertNotEqual(header.purchase_number, "LEG-P-0001")
        self.assertEqual(header.supplier_invoice_number, "LEG-P-0001")

    def test_purchase_collision_with_live_invoice_is_skipped_for_generate_finacc_strategy(self):
        PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=self.vendor,
            bill_date=timezone.now().date(),
            posting_date=timezone.now().date(),
            purchase_number="P-LIVE-EXISTING-1",
            supplier_invoice_number="LIVE-SUP-1",
            status=PurchaseInvoiceHeader.Status.POSTED,
        )
        row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-collision-test-1",
            source_invoice_number="P-LIVE-EXISTING-1",
        )
        row.update(
            {
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "P-LIVE-EXISTING-1",
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
            }
        )

        preserve_job = create_validated_job(
            entity=self.entity,
            user=self.user,
            module=ImportJob.Module.PURCHASE,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            stock_replay=False,
            compliance_mode=ImportJob.ComplianceMode.PASSIVE,
            withholding_mode=ImportJob.WithholdingMode.PRESERVE_LEGACY,
            document_number_strategy="preserve_legacy",
            source_system="legacy_erp",
            filename="import.zip",
            fmt=ImportJob.FileFormat.CSV,
            file_bytes=_write_csv_zip([row]),
        )
        self.assertEqual(preserve_job.status, ImportJob.Status.FAILED)

        generate_job = create_validated_job(
            entity=self.entity,
            user=self.user,
            module=ImportJob.Module.PURCHASE,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            stock_replay=False,
            compliance_mode=ImportJob.ComplianceMode.PASSIVE,
            withholding_mode=ImportJob.WithholdingMode.PRESERVE_LEGACY,
            document_number_strategy="generate_finacc",
            source_system="legacy_erp",
            filename="import.zip",
            fmt=ImportJob.FileFormat.CSV,
            file_bytes=_write_csv_zip([row]),
        )
        self.assertEqual(generate_job.status, ImportJob.Status.VALIDATED)

    def test_purchase_header_plus_lines_rejects_group_total_mismatch(self):
        row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-lines-mismatch-1",
            source_invoice_number="P-LEG-LINE-001",
        )
        row.update(
            {
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-LINE-001",
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
                "line_no": 1,
                "product_desc": "Imported purchase line",
                "is_service": True,
                "qty": "10.0000",
                "rate": "100.00",
                "discount_type": "N",
                "discount_percent": "0.00",
                "discount_amount": "0.00",
                "taxable_value": "900.00",
                "gst_rate": "18.00",
                "cgst_amount": "81.00",
                "sgst_amount": "81.00",
                "igst_amount": "0.00",
                "cess_percent": "0.00",
                "cess_amount": "0.00",
                "line_total": "1062.00",
            }
        )
        job = self._build_job(
            module=ImportJob.Module.PURCHASE,
            mode=ImportJob.Mode.FULL_HISTORY,
            detail_level=ImportJob.DetailLevel.HEADER_PLUS_LINES,
            rows=[row],
        )

        self.assertEqual(job.status, ImportJob.Status.FAILED)
        row_state = job.rows.get()
        self.assertTrue(any(err["field"] == "total_taxable" for err in row_state.errors))

    def test_purchase_review_required_blocks_commit_until_marked_reviewed(self):
        row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-review-1",
            source_invoice_number="P-LEG-REVIEW-001",
        )
        row.update(
            {
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-REVIEW-001",
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
            }
        )
        with patch("invoice_import.services.PurchaseSettingsService.get_policy", return_value=SimpleNamespace(controls={"legacy_import_review_required": "on"})):
            job = self._build_job(
                module=ImportJob.Module.PURCHASE,
                mode=ImportJob.Mode.OUTSTANDING_ONLY,
                detail_level=ImportJob.DetailLevel.HEADER_ONLY,
                rows=[row],
            )

        self.assertTrue(job.review_required)
        with self.assertRaisesMessage(ValueError, "must be reviewed before commit"):
            commit_job(job=job, user=self.user)

    def test_purchase_review_endpoint_marks_job_reviewed(self):
        row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-review-api-1",
            source_invoice_number="P-LEG-REVIEW-API-001",
        )
        row.update(
            {
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-REVIEW-API-001",
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
            }
        )
        with patch("invoice_import.services.PurchaseSettingsService.get_policy", return_value=SimpleNamespace(controls={"legacy_import_review_required": "on"})):
            job = self._build_job(
                module=ImportJob.Module.PURCHASE,
                mode=ImportJob.Mode.OUTSTANDING_ONLY,
                detail_level=ImportJob.DetailLevel.HEADER_ONLY,
                rows=[row],
            )

        factory = APIRequestFactory()
        request = factory.post(
            f"/api/purchase/legacy-import/jobs/{job.id}/review/?entity={self.entity.id}",
            {"review_note": "Checked against legacy report"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        with patch("invoice_import.views.require_purchase_request_permission"):
            response = PurchaseInvoiceImportJobReviewAPIView.as_view()(request, job_id=job.id)
        self.assertEqual(response.status_code, 200)
        job.refresh_from_db()
        self.assertIsNotNone(job.reviewed_at)
        self.assertEqual(job.review_note, "Checked against legacy report")

    def test_purchase_credit_note_cannot_exceed_original_amount_in_same_import_job(self):
        invoice_row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-cn-base-1",
            source_invoice_number="P-LEG-CN-BASE-001",
        )
        invoice_row.update(
            {
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-CN-BASE-001",
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
            }
        )
        credit_note_row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-cn-note-1",
            source_invoice_number="P-LEG-CN-NOTE-001",
        )
        credit_note_row.update(
            {
                "doc_type": "credit_note",
                "original_source_key": "purchase-cn-base-1",
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-CN-NOTE-001",
                "supplier_invoice_date": "2025-04-02",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
                "total_taxable": "1500.00",
                "total_cgst": "135.00",
                "total_sgst": "135.00",
                "grand_total": "1770.00",
                "settled_amount": "0.00",
                "outstanding_amount": "1770.00",
            }
        )
        job = self._build_job(
            module=ImportJob.Module.PURCHASE,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            rows=[invoice_row, credit_note_row],
        )

        self.assertEqual(job.status, ImportJob.Status.FAILED)
        note_row = job.rows.get(group_key="purchase-cn-note-1")
        self.assertTrue(any(err["field"] == "grand_total" for err in note_row.errors))
        note_summary = next(item for item in (job.summary or {}).get("document_summaries", []) if item["legacy_source_key"] == "purchase-cn-note-1")
        self.assertTrue(note_summary["review_preview"].startswith("Original mismatch:"))

    def test_purchase_credit_note_earlier_bill_date_adds_review_warning(self):
        invoice_row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-cn-warn-base-1",
            source_invoice_number="P-LEG-CN-WARN-BASE-001",
        )
        invoice_row.update(
            {
                "bill_date": "2025-04-10",
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-CN-WARN-BASE-001",
                "supplier_invoice_date": "2025-04-10",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
            }
        )
        credit_note_row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-cn-warn-note-1",
            source_invoice_number="P-LEG-CN-WARN-NOTE-001",
        )
        credit_note_row.update(
            {
                "doc_type": "credit_note",
                "bill_date": "2025-04-01",
                "original_source_key": "purchase-cn-warn-base-1",
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-CN-WARN-NOTE-001",
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
                "total_taxable": "500.00",
                "total_cgst": "45.00",
                "total_sgst": "45.00",
                "grand_total": "590.00",
                "settled_amount": "0.00",
                "outstanding_amount": "590.00",
            }
        )
        job = self._build_job(
            module=ImportJob.Module.PURCHASE,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            rows=[invoice_row, credit_note_row],
        )

        self.assertEqual(job.status, ImportJob.Status.VALIDATED)
        note_row = job.rows.get(group_key="purchase-cn-warn-note-1")
        self.assertTrue(any("earlier than original invoice" in warning for warning in (note_row.warnings or [])))
        note_summary = next(item for item in (job.summary or {}).get("document_summaries", []) if item["legacy_source_key"] == "purchase-cn-warn-note-1")
        self.assertTrue(note_summary["review_preview"].startswith("Date warning:"))
        self.assertIn("earlier than original invoice", note_summary["review_preview"])

    def test_purchase_credit_note_outstanding_can_be_blocked_by_policy(self):
        invoice_row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-cn-hard-outstanding-base-1",
            source_invoice_number="P-LEG-CN-HARD-BASE-001",
        )
        invoice_row.update(
            {
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-CN-HARD-BASE-001",
                "supplier_invoice_date": "2025-04-10",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
                "grand_total": "1180.00",
                "settled_amount": "600.00",
                "outstanding_amount": "580.00",
            }
        )
        credit_note_row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-cn-hard-outstanding-note-1",
            source_invoice_number="P-LEG-CN-HARD-NOTE-001",
        )
        credit_note_row.update(
            {
                "doc_type": "credit_note",
                "original_source_key": "purchase-cn-hard-outstanding-base-1",
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-CN-HARD-NOTE-001",
                "supplier_invoice_date": "2025-04-11",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
                "total_taxable": "400.00",
                "total_cgst": "36.00",
                "total_sgst": "36.00",
                "grand_total": "472.00",
                "settled_amount": "0.00",
                "outstanding_amount": "700.00",
            }
        )
        with patch("invoice_import.services.PurchaseSettingsService.get_policy", return_value=SimpleNamespace(controls={"legacy_import_note_outstanding_rule": "hard"})):
            job = self._build_job(
                module=ImportJob.Module.PURCHASE,
                mode=ImportJob.Mode.OUTSTANDING_ONLY,
                detail_level=ImportJob.DetailLevel.HEADER_ONLY,
                rows=[invoice_row, credit_note_row],
            )

        self.assertEqual(job.status, ImportJob.Status.FAILED)
        note_row = job.rows.get(group_key="purchase-cn-hard-outstanding-note-1")
        self.assertTrue(any(err["field"] == "outstanding_amount" for err in note_row.errors))
        note_summary = next(item for item in (job.summary or {}).get("document_summaries", []) if item["legacy_source_key"] == "purchase-cn-hard-outstanding-note-1")
        self.assertTrue(note_summary["review_preview"].startswith("Outstanding issue:"))

    def test_purchase_credit_note_date_can_be_blocked_by_policy(self):
        invoice_row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-cn-hard-date-base-1",
            source_invoice_number="P-LEG-CN-HARD-DATE-BASE-001",
        )
        invoice_row.update(
            {
                "bill_date": "2025-04-10",
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-CN-HARD-DATE-BASE-001",
                "supplier_invoice_date": "2025-04-10",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
            }
        )
        credit_note_row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-cn-hard-date-note-1",
            source_invoice_number="P-LEG-CN-HARD-DATE-NOTE-001",
        )
        credit_note_row.update(
            {
                "doc_type": "credit_note",
                "bill_date": "2025-04-01",
                "original_source_key": "purchase-cn-hard-date-base-1",
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-CN-HARD-DATE-NOTE-001",
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
                "total_taxable": "500.00",
                "total_cgst": "45.00",
                "total_sgst": "45.00",
                "grand_total": "590.00",
                "settled_amount": "0.00",
                "outstanding_amount": "590.00",
            }
        )
        with patch("invoice_import.services.PurchaseSettingsService.get_policy", return_value=SimpleNamespace(controls={"legacy_import_note_date_rule": "hard"})):
            job = self._build_job(
                module=ImportJob.Module.PURCHASE,
                mode=ImportJob.Mode.OUTSTANDING_ONLY,
                detail_level=ImportJob.DetailLevel.HEADER_ONLY,
                rows=[invoice_row, credit_note_row],
            )

        self.assertEqual(job.status, ImportJob.Status.FAILED)
        note_row = job.rows.get(group_key="purchase-cn-hard-date-note-1")
        self.assertTrue(any(err["field"] == "bill_date" for err in note_row.errors))
        note_summary = next(item for item in (job.summary or {}).get("document_summaries", []) if item["legacy_source_key"] == "purchase-cn-hard-date-note-1")
        self.assertTrue(note_summary["review_preview"].startswith("Date issue:"))

    def test_purchase_credit_note_amount_tolerance_allows_small_variance(self):
        invoice_row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-cn-tolerance-base-1",
            source_invoice_number="P-LEG-CN-TOL-BASE-001",
        )
        invoice_row.update(
            {
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-CN-TOL-BASE-001",
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
                "total_taxable": "1000.00",
                "total_cgst": "90.00",
                "total_sgst": "90.00",
                "grand_total": "1180.00",
                "settled_amount": "0.00",
                "outstanding_amount": "1180.00",
            }
        )
        credit_note_row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-cn-tolerance-note-1",
            source_invoice_number="P-LEG-CN-TOL-NOTE-001",
        )
        credit_note_row.update(
            {
                "doc_type": "credit_note",
                "original_source_key": "purchase-cn-tolerance-base-1",
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-CN-TOL-NOTE-001",
                "supplier_invoice_date": "2025-04-02",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
                "total_taxable": "1005.00",
                "total_cgst": "90.45",
                "total_sgst": "90.45",
                "grand_total": "1185.90",
                "settled_amount": "0.00",
                "outstanding_amount": "1185.90",
            }
        )
        with patch("invoice_import.services.PurchaseSettingsService.get_policy", return_value=SimpleNamespace(controls={"legacy_import_note_amount_tolerance": "10.00"})):
            job = self._build_job(
                module=ImportJob.Module.PURCHASE,
                mode=ImportJob.Mode.OUTSTANDING_ONLY,
                detail_level=ImportJob.DetailLevel.HEADER_ONLY,
                rows=[invoice_row, credit_note_row],
            )

        self.assertEqual(job.status, ImportJob.Status.VALIDATED)
        note_row = job.rows.get(group_key="purchase-cn-tolerance-note-1")
        self.assertFalse(any(err["field"] in {"grand_total", "total_taxable"} for err in (note_row.errors or [])))

    def test_full_history_sales_with_stock_replay_and_live_compliance_calls_hooks(self):
        uom = UnitOfMeasure.objects.create(entity=self.entity, code="NOS", description="Numbers")
        category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Goods")
        product = Product.objects.create(
            entity=self.entity,
            productname="Widget",
            sku="WIDGET-001",
            productcategory=category,
            base_uom=uom,
            sales_account=self.customer,
        )
        row = self._base_row(
            party_name=self.customer.accountname,
            source_key="sales-full-1",
            source_invoice_number="S-LEG-002",
        )
        row.update(
            {
                "party_gstin": "27ABCDE1234F1Z5",
                "party_state_code": "27",
                "seller_gstin": "27AAAAA1111A1Z5",
                "seller_state_code": "27",
                "supply_category": SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                "taxability": SalesInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": SalesInvoiceHeader.TaxRegime.INTRA_STATE,
                "line_no": 1,
                "product_id": product.id,
                "product_desc": "Imported widget",
                "is_service": False,
                "uom_id": uom.id,
                "hsn_sac_code": "8471",
                "qty": "10.000",
                "free_qty": "0.000",
                "rate": "100.0000",
                "discount_type": SalesInvoiceHeader.DocType.TAX_INVOICE - 1,
                "discount_percent": "0.0000",
                "discount_amount": "0.00",
                "gst_rate": "18.00",
                "cess_percent": "0.00",
                "taxable_value": "1000.00",
                "cgst_amount": "90.00",
                "sgst_amount": "90.00",
                "igst_amount": "0.00",
                "cess_amount": "0.00",
                "line_total": "1180.00",
            }
        )
        job = self._build_job(
            module=ImportJob.Module.SALES,
            mode=ImportJob.Mode.FULL_HISTORY,
            detail_level=ImportJob.DetailLevel.HEADER_PLUS_LINES,
            rows=[row],
            stock_replay=True,
            compliance_mode=ImportJob.ComplianceMode.LIVE,
        )

        with patch("invoice_import.services.SalesInvoicePostingAdapter.post_sales_invoice") as post_sales_invoice, patch(
            "invoice_import.services.SalesInvoiceService._run_auto_compliance"
        ) as run_auto_compliance:
            commit_job(job=job, user=self.user)

        post_sales_invoice.assert_called_once()
        run_auto_compliance.assert_called_once()

    def test_full_history_sales_resolves_product_by_code_for_stock_replay(self):
        uom = UnitOfMeasure.objects.create(entity=self.entity, code="NOS", description="Numbers")
        category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Goods")
        product = Product.objects.create(
            entity=self.entity,
            productname="Code Resolved Widget",
            sku="CODE-WIDGET-001",
            productcategory=category,
            base_uom=uom,
            sales_account=self.customer,
        )
        row = self._base_row(
            party_name=self.customer.accountname,
            source_key="sales-code-resolve-1",
            source_invoice_number="S-LEG-CODE-001",
        )
        row.update(
            {
                "party_gstin": "27ABCDE1234F1Z5",
                "party_state_code": "27",
                "seller_gstin": "27AAAAA1111A1Z5",
                "seller_state_code": "27",
                "supply_category": SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                "taxability": SalesInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": SalesInvoiceHeader.TaxRegime.INTRA_STATE,
                "line_no": 1,
                "product_id": "",
                "product_code": product.sku,
                "product_name": "",
                "product_desc": "Imported widget by code",
                "is_service": False,
                "uom_id": uom.id,
                "hsn_sac_code": "8471",
                "qty": "10.000",
                "free_qty": "0.000",
                "rate": "100.0000",
                "discount_type": 0,
                "discount_percent": "0.0000",
                "discount_amount": "0.00",
                "gst_rate": "18.00",
                "cess_percent": "0.00",
                "taxable_value": "1000.00",
                "cgst_amount": "90.00",
                "sgst_amount": "90.00",
                "igst_amount": "0.00",
                "cess_amount": "0.00",
                "line_total": "1180.00",
            }
        )
        job = self._build_job(
            module=ImportJob.Module.SALES,
            mode=ImportJob.Mode.FULL_HISTORY,
            detail_level=ImportJob.DetailLevel.HEADER_PLUS_LINES,
            rows=[row],
            stock_replay=True,
        )

        self.assertEqual(job.status, ImportJob.Status.VALIDATED)
        normalized = job.rows.get().normalized_payload
        self.assertEqual(normalized["product_id"], product.id)
        self.assertEqual(normalized["product_code"], product.sku)

    def test_full_history_sales_resolves_product_by_name_for_stock_replay(self):
        uom = UnitOfMeasure.objects.create(entity=self.entity, code="NOS", description="Numbers")
        category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Goods")
        product = Product.objects.create(
            entity=self.entity,
            productname="Name Resolved Widget",
            sku="NAME-WIDGET-001",
            productcategory=category,
            base_uom=uom,
            sales_account=self.customer,
        )
        row = self._base_row(
            party_name=self.customer.accountname,
            source_key="sales-name-resolve-1",
            source_invoice_number="S-LEG-NAME-001",
        )
        row.update(
            {
                "party_gstin": "27ABCDE1234F1Z5",
                "party_state_code": "27",
                "seller_gstin": "27AAAAA1111A1Z5",
                "seller_state_code": "27",
                "supply_category": SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                "taxability": SalesInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": SalesInvoiceHeader.TaxRegime.INTRA_STATE,
                "line_no": 1,
                "product_id": "",
                "product_code": "",
                "product_name": product.productname,
                "product_desc": "Imported widget by name",
                "is_service": False,
                "uom_id": uom.id,
                "hsn_sac_code": "8471",
                "qty": "10.000",
                "free_qty": "0.000",
                "rate": "100.0000",
                "discount_type": 0,
                "discount_percent": "0.0000",
                "discount_amount": "0.00",
                "gst_rate": "18.00",
                "cess_percent": "0.00",
                "taxable_value": "1000.00",
                "cgst_amount": "90.00",
                "sgst_amount": "90.00",
                "igst_amount": "0.00",
                "cess_amount": "0.00",
                "line_total": "1180.00",
            }
        )
        job = self._build_job(
            module=ImportJob.Module.SALES,
            mode=ImportJob.Mode.FULL_HISTORY,
            detail_level=ImportJob.DetailLevel.HEADER_PLUS_LINES,
            rows=[row],
            stock_replay=True,
        )

        self.assertEqual(job.status, ImportJob.Status.VALIDATED)
        normalized = job.rows.get().normalized_payload
        self.assertEqual(normalized["product_id"], product.id)
        self.assertEqual(normalized["product_name"], product.productname)

    def test_purchase_withholding_recompute_records_warning(self):
        row = self._base_row(
            party_name=self.vendor.accountname,
            source_key="purchase-withholding-1",
            source_invoice_number="P-LEG-002",
        )
        row.update(
            {
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": "SUP-002",
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
                "tds_amount": "5.00",
                "gst_tds_amount": "0.00",
            }
        )
        job = self._build_job(
            module=ImportJob.Module.PURCHASE,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            rows=[row],
            withholding_mode=ImportJob.WithholdingMode.RECOMPUTE_FINACC,
        )

        def fake_apply_tds(*, header):
            header.tds_amount = Decimal("12.00")

        def fake_apply_gst_tds(*, header):
            header.gst_tds_amount = Decimal("3.00")

        with patch("invoice_import.services.PurchaseInvoiceService._apply_tds", side_effect=fake_apply_tds), patch(
            "invoice_import.services.PurchaseInvoiceService._apply_gst_tds", side_effect=fake_apply_gst_tds
        ):
            job = commit_job(job=job, user=self.user)

        warnings = job.reconciliation_summary["warnings"]
        self.assertTrue(any("Withholding recomputed" in warning for warning in warnings))

    def test_duplicate_legacy_source_key_is_blocked_on_reimport(self):
        row = self._base_row(
            party_name=self.customer.accountname,
            source_key="sales-dup-1",
            source_invoice_number="S-LEG-003",
        )
        row.update(
            {
                "party_gstin": "27ABCDE1234F1Z5",
                "party_state_code": "27",
                "seller_gstin": "27AAAAA1111A1Z5",
                "seller_state_code": "27",
                "supply_category": SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                "taxability": SalesInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            }
        )
        first_job = self._build_job(
            module=ImportJob.Module.SALES,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            rows=[row],
        )
        commit_job(job=first_job, user=self.user)

        second_job = self._build_job(
            module=ImportJob.Module.SALES,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            rows=[row],
        )

        self.assertEqual(second_job.status, ImportJob.Status.FAILED)
        row_state = second_job.rows.get()
        self.assertEqual(row_state.status, row_state.Status.ERROR)
        self.assertTrue(any(err["field"] == "legacy_source_key" for err in row_state.errors))

    def test_profile_mapping_transforms_legacy_columns_into_canonical_import(self):
        profile = ImportProfile.objects.create(
            entity=self.entity,
            created_by=self.user,
            module=ImportProfile.Module.SALES,
            name="Tally Sales Mapping",
            source_system="tally",
            mapping={
                "defaults": {
                    "entityfinid_id": self.entityfin.id,
                    "subentity_id": self.subentity.id,
                    "doc_type": "invoice",
                    "status": "posted",
                    "seller_gstin": "27AAAAA1111A1Z5",
                    "seller_state_code": "27",
                    "supply_category": SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                    "taxability": SalesInvoiceHeader.Taxability.TAXABLE,
                    "tax_regime": SalesInvoiceHeader.TaxRegime.INTRA_STATE,
                    "total_igst": "0.00",
                    "total_cess": "0.00",
                    "round_off": "0.00",
                },
                "source_to_canonical": {
                    "Invoice No": "source_invoice_number",
                    "External Key": "legacy_source_key",
                    "Bill Date": "bill_date",
                    "Due Date": "due_date",
                    "Customer": "party_name",
                    "GSTIN": "party_gstin",
                    "State Code": "party_state_code",
                    "Taxable Amount": "total_taxable",
                    "CGST": "total_cgst",
                    "SGST": "total_sgst",
                    "Gross Total": "grand_total",
                    "Received": "settled_amount",
                    "Pending": "outstanding_amount",
                },
            },
        )
        rows = [
            {
                "Invoice No": "S-TALLY-001",
                "External Key": "sales-prof-1",
                "Bill Date": "2025-04-01",
                "Due Date": "2025-04-30",
                "Customer": self.customer.accountname,
                "GSTIN": "27ABCDE1234F1Z5",
                "State Code": "27",
                "Taxable Amount": "1000.00",
                "CGST": "90.00",
                "SGST": "90.00",
                "Gross Total": "1180.00",
                "Received": "400.00",
                "Pending": "780.00",
            }
        ]
        job = create_validated_job(
            entity=self.entity,
            user=self.user,
            module=ImportJob.Module.SALES,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            stock_replay=False,
            compliance_mode=ImportJob.ComplianceMode.PASSIVE,
            withholding_mode=ImportJob.WithholdingMode.PRESERVE_LEGACY,
            source_system="tally",
            filename="tally.zip",
            fmt=ImportJob.FileFormat.CSV,
            file_bytes=_write_csv_zip(rows),
            profile=profile,
        )

        self.assertEqual(job.status, ImportJob.Status.VALIDATED)
        self.assertEqual(job.profile_id, profile.id)
        self.assertEqual(job.profile_snapshot["name"], "Tally Sales Mapping")
        first_row = job.rows.get()
        self.assertEqual(first_row.normalized_payload["legacy_source_key"], "sales-prof-1")
        self.assertEqual(first_row.normalized_payload["source_invoice_number"], "S-TALLY-001")


@override_settings(AUTH_PASSWORD_VALIDATORS=[])
class InvoiceImportAPIViewTests(InvoiceImportServiceTests):
    def setUp(self):
        super().setUp()
        self.factory = APIRequestFactory()

    def _upload(self, rows: list[dict[str, object]]) -> SimpleUploadedFile:
        return SimpleUploadedFile(
            "import.zip",
            _write_csv_zip(rows),
            content_type="application/zip",
        )

    def _sales_row(self, *, source_key: str, invoice_number: str) -> dict[str, object]:
        row = self._base_row(
            party_name=self.customer.accountname,
            source_key=source_key,
            source_invoice_number=invoice_number,
        )
        row.update(
            {
                "party_gstin": "27ABCDE1234F1Z5",
                "party_state_code": "27",
                "seller_gstin": "27AAAAA1111A1Z5",
                "seller_state_code": "27",
                "supply_category": SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                "taxability": SalesInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            }
        )
        return row

    def _purchase_row(self, *, source_key: str, invoice_number: str) -> dict[str, object]:
        row = self._base_row(
            party_name=self.vendor.accountname,
            source_key=source_key,
            source_invoice_number=invoice_number,
        )
        row.update(
            {
                "party_gstin": "27AACCV1234F1Z5",
                "supplier_invoice_number": invoice_number,
                "supplier_invoice_date": "2025-04-01",
                "supply_category": PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "tax_regime": PurchaseInvoiceHeader.TaxRegime.INTRA,
            }
        )
        return row

    def _request(self, method: str, path: str, *, data=None, query=None, format=None):
        request = getattr(self.factory, method.lower())(path, data=data, format=format)
        if query:
            request.GET = request.GET.copy()
            for key, value in query.items():
                request.GET[key] = str(value)
        force_authenticate(request, user=self.user)
        return request

    @patch("invoice_import.views.require_sales_request_permission")
    def test_sales_template_endpoint_returns_download(self, _mock_permission):
        request = self._request(
            "get",
            "/api/sales/legacy-import/template/",
            query={
                "entity": self.entity.id,
                "mode": ImportJob.Mode.OUTSTANDING_ONLY,
                "detail_level": ImportJob.DetailLevel.HEADER_ONLY,
            },
        )
        response = SalesInvoiceImportTemplateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment;", response["Content-Disposition"])
        _mock_permission.assert_called_once_with(user=self.user, entity_id=self.entity.id, doc_type=1, action="view")

    @patch("invoice_import.views.require_sales_request_permission")
    def test_sales_job_create_detail_and_commit_views(self, _mock_permission):
        profile = ImportProfile.objects.create(
            entity=self.entity,
            created_by=self.user,
            module=ImportProfile.Module.SALES,
            name="Sales API Profile",
            source_system="legacy_erp",
            mapping={},
        )
        create_request = self._request(
            "post",
            "/api/sales/legacy-import/jobs/",
            data={
                "entity": self.entity.id,
                "profile": profile.id,
                "mode": ImportJob.Mode.OUTSTANDING_ONLY,
                "detail_level": ImportJob.DetailLevel.HEADER_ONLY,
                "file": self._upload([self._sales_row(source_key="sales-api-1", invoice_number="S-API-001")]),
            },
            format="multipart",
        )
        create_response = SalesInvoiceImportJobCreateAPIView.as_view()(create_request)
        self.assertEqual(create_response.status_code, 201)
        job_id = create_response.data["job"]["id"]
        self.assertTrue(create_response.data["can_commit"])

        detail_request = self._request(
            "get",
            f"/api/sales/legacy-import/jobs/{job_id}/",
            query={"entity": self.entity.id},
        )
        detail_response = SalesInvoiceImportJobDetailAPIView.as_view()(detail_request, job_id=job_id)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["status"], ImportJob.Status.VALIDATED)
        self.assertEqual(len(detail_response.data["rows"]), 1)

        commit_request = self._request(
            "post",
            f"/api/sales/legacy-import/jobs/{job_id}/commit/",
            data={"entity": self.entity.id},
            format="json",
        )
        commit_response = SalesInvoiceImportJobCommitAPIView.as_view()(commit_request, job_id=job_id)
        self.assertEqual(commit_response.status_code, 200)
        self.assertEqual(commit_response.data["status"], ImportJob.Status.COMMITTED)
        self.assertTrue(SalesInvoiceHeader.objects.filter(legacy_source_key="sales-api-1").exists())
        actions = [call.kwargs["action"] for call in _mock_permission.call_args_list]
        self.assertEqual(actions, ["create", "view", "post"])

    @patch("invoice_import.views.require_purchase_request_permission")
    def test_purchase_review_view_uses_update_permission(self, mock_permission):
        row = self._purchase_row(source_key="purchase-review-api-2", invoice_number="P-REVIEW-API-002")
        with patch("invoice_import.services.PurchaseSettingsService.get_policy", return_value=SimpleNamespace(controls={"legacy_import_review_required": "on"})):
            job = self._build_job(
                module=ImportJob.Module.PURCHASE,
                mode=ImportJob.Mode.OUTSTANDING_ONLY,
                detail_level=ImportJob.DetailLevel.HEADER_ONLY,
                rows=[row],
            )

        request = self._request(
            "post",
            f"/api/purchase/legacy-import/jobs/{job.id}/review/",
            data={"entity": self.entity.id, "review_note": "Checked by reviewer"},
            format="json",
        )
        response = PurchaseInvoiceImportJobReviewAPIView.as_view()(request, job_id=job.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_permission.call_args_list[0].kwargs["action"], "update")

    @patch("invoice_import.views.require_purchase_request_permission")
    def test_purchase_detail_and_reconciliation_views_use_view_permission(self, mock_permission):
        job = self._build_job(
            module=ImportJob.Module.PURCHASE,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            rows=[self._purchase_row(source_key="purchase-view-api-1", invoice_number="P-VIEW-001")],
        )
        commit_job(job=job, user=self.user)

        detail_request = self._request(
            "get",
            f"/api/purchase/legacy-import/jobs/{job.id}/",
            query={"entity": self.entity.id},
        )
        detail_response = PurchaseInvoiceImportJobDetailAPIView.as_view()(detail_request, job_id=job.id)
        self.assertEqual(detail_response.status_code, 200)

        reconciliation_request = self._request(
            "get",
            f"/api/purchase/legacy-import/jobs/{job.id}/reconciliation/",
            query={"entity": self.entity.id},
        )
        reconciliation_response = PurchaseInvoiceImportJobReconciliationAPIView.as_view()(reconciliation_request, job_id=job.id)
        self.assertEqual(reconciliation_response.status_code, 200)

        actions = [call.kwargs["action"] for call in mock_permission.call_args_list]
        self.assertEqual(actions, ["view", "view"])

    @patch("invoice_import.views.require_sales_request_permission")
    def test_sales_profile_create_list_and_patch_views(self, _mock_permission):
        create_request = self._request(
            "post",
            "/api/sales/legacy-import/profiles/",
            data={
                "entity": self.entity.id,
                "name": "Busy Sales Mapping",
                "source_system": "busy",
                "description": "Maps Busy export columns",
                "is_default": True,
                "mapping": {
                    "source_to_canonical": {
                        "Voucher No": "source_invoice_number",
                    }
                },
                "options": {"date_format": "dd-mm-yyyy"},
            },
            format="json",
        )
        create_response = SalesInvoiceImportProfileListCreateAPIView.as_view()(create_request)
        self.assertEqual(create_response.status_code, 201)
        profile_id = create_response.data["id"]

        list_request = self._request(
            "get",
            "/api/sales/legacy-import/profiles/",
            query={"entity": self.entity.id},
        )
        list_response = SalesInvoiceImportProfileListCreateAPIView.as_view()(list_request)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)

        patch_request = self._request(
            "patch",
            f"/api/sales/legacy-import/profiles/{profile_id}/",
            data={
                "entity": self.entity.id,
                "description": "Updated mapping description",
            },
            format="json",
        )
        patch_response = SalesInvoiceImportProfileDetailAPIView.as_view()(patch_request, profile_id=profile_id)
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.data["description"], "Updated mapping description")

    @patch("invoice_import.views.require_purchase_request_permission")
    def test_purchase_job_commit_view_returns_partial_when_some_groups_fail(self, _mock_permission):
        ok_row = self._purchase_row(source_key="purchase-ok-1", invoice_number="P-OK-001")
        ok_row["original_source_key"] = ""
        bad_cn_row = self._purchase_row(source_key="purchase-cn-bad-1", invoice_number="P-CN-001")
        bad_cn_row["doc_type"] = 2
        bad_cn_row["original_source_key"] = "missing-original"
        rows = [
            ok_row,
            bad_cn_row,
        ]
        create_request = self._request(
            "post",
            "/api/purchase/legacy-import/jobs/",
            data={
                "entity": self.entity.id,
                "mode": ImportJob.Mode.OUTSTANDING_ONLY,
                "detail_level": ImportJob.DetailLevel.HEADER_ONLY,
                "file": self._upload(rows),
            },
            format="multipart",
        )
        create_response = PurchaseInvoiceImportJobCreateAPIView.as_view()(create_request)
        self.assertEqual(create_response.status_code, 201)
        job_id = create_response.data["job"]["id"]
        self.assertTrue(create_response.data["can_commit"])

        commit_request = self._request(
            "post",
            f"/api/purchase/legacy-import/jobs/{job_id}/commit/",
            data={"entity": self.entity.id},
            format="json",
        )
        commit_response = PurchaseInvoiceImportJobCommitAPIView.as_view()(commit_request, job_id=job_id)
        self.assertEqual(commit_response.status_code, 409)
        self.assertEqual(commit_response.data["status"], ImportJob.Status.PARTIAL)
        self.assertIn("partially completed", commit_response.data["detail"].lower())
        self.assertGreater(commit_response.data["error_count"], 0)

    @patch("invoice_import.views.require_purchase_request_permission")
    def test_purchase_job_commit_view_returns_failed_when_all_groups_fail(self, _mock_permission):
        bad_cn_row = self._purchase_row(source_key="purchase-cn-fail-1", invoice_number="P-CN-FAIL-001")
        bad_cn_row["doc_type"] = 2
        bad_cn_row["original_source_key"] = "missing-original"
        rows = [
            bad_cn_row,
        ]
        create_request = self._request(
            "post",
            "/api/purchase/legacy-import/jobs/",
            data={
                "entity": self.entity.id,
                "mode": ImportJob.Mode.OUTSTANDING_ONLY,
                "detail_level": ImportJob.DetailLevel.HEADER_ONLY,
                "file": self._upload(rows),
            },
            format="multipart",
        )
        create_response = PurchaseInvoiceImportJobCreateAPIView.as_view()(create_request)
        self.assertEqual(create_response.status_code, 201)
        job_id = create_response.data["job"]["id"]
        self.assertTrue(create_response.data["can_commit"])

        commit_request = self._request(
            "post",
            f"/api/purchase/legacy-import/jobs/{job_id}/commit/",
            data={"entity": self.entity.id},
            format="json",
        )
        commit_response = PurchaseInvoiceImportJobCommitAPIView.as_view()(commit_request, job_id=job_id)
        self.assertEqual(commit_response.status_code, 400)
        self.assertEqual(commit_response.data["status"], ImportJob.Status.FAILED)
        self.assertIn("failed", commit_response.data["detail"].lower())
        self.assertGreater(commit_response.data["error_count"], 0)

    @patch("invoice_import.views.require_purchase_request_permission")
    def test_purchase_reconciliation_view_returns_summary(self, _mock_permission):
        job = self._build_job(
            module=ImportJob.Module.PURCHASE,
            mode=ImportJob.Mode.OUTSTANDING_ONLY,
            detail_level=ImportJob.DetailLevel.HEADER_ONLY,
            rows=[self._purchase_row(source_key="purchase-api-1", invoice_number="P-API-001")],
        )
        commit_job(job=job, user=self.user)

        request = self._request(
            "get",
            f"/api/purchase/legacy-import/jobs/{job.id}/reconciliation/",
            query={"entity": self.entity.id},
        )
        response = PurchaseInvoiceImportJobReconciliationAPIView.as_view()(request, job_id=job.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["imported_documents"]), 1)
        self.assertEqual(response.data["imported_documents"][0]["legacy_source_key"], "purchase-api-1")

    @patch("invoice_import.views.require_purchase_request_permission")
    def test_purchase_profile_create_view(self, _mock_permission):
        request = self._request(
            "post",
            "/api/purchase/legacy-import/profiles/",
            data={
                "entity": self.entity.id,
                "name": "Purchase Source Profile",
                "source_system": "zoho",
                "mapping": {"defaults": {"status": "posted"}},
                "options": {},
            },
            format="json",
        )
        response = PurchaseInvoiceImportProfileListCreateAPIView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["module"], ImportProfile.Module.PURCHASE)
