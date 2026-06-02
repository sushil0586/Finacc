from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.serializers.purchase_gstr2b import Gstr2bImportRowInputSerializer, Gstr2bImportRowReviewSerializer
from purchase.services.purchase_gstr2b_service import PurchaseGstr2bService


class PurchaseGstr2bReviewContractTests(TestCase):
    def test_import_row_serializer_accepts_blank_gstin_for_invoice_only_review_row(self):
        serializer = Gstr2bImportRowInputSerializer(data={
            "supplier_gstin": "   ",
            "supplier_invoice_number": "INV-88",
            "supplier_invoice_date": "2026-04-06",
            "taxable_value": "250.00",
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data["supplier_gstin"])
        self.assertEqual(serializer.validated_data["supplier_invoice_number"], "INV-88")

    def test_import_row_serializer_normalizes_lowercase_gstin_to_uppercase(self):
        serializer = Gstr2bImportRowInputSerializer(data={
            "supplier_gstin": "27abcde1234f1z5",
            "supplier_invoice_number": "INV-89",
            "supplier_invoice_date": "2026-04-07",
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["supplier_gstin"], "27ABCDE1234F1Z5")

    @patch("purchase.services.purchase_gstr2b_service.PurchaseGstr2bService._sync_invoice_match_status")
    @patch("purchase.services.purchase_gstr2b_service.PurchaseInvoiceHeader.objects")
    @patch("purchase.services.purchase_gstr2b_service.Gstr2bImportRow.objects")
    @patch("purchase.services.purchase_gstr2b_service.Gstr2bImportBatch.objects")
    def test_auto_match_batch_clears_stale_invoice_state_when_row_becomes_not_matched(
        self,
        mock_batch_objects,
        mock_row_objects,
        mock_invoice_objects,
        mock_sync,
    ):
        batch = SimpleNamespace(id=5, entity_id=1, entityfinid_id=1, subentity_id=None)
        previous_invoice = MagicMock()
        previous_invoice.id = 401
        row = MagicMock()
        row.id = 51
        row.batch = batch
        row.matched_purchase = previous_invoice
        row.supplier_gstin = ""
        row.supplier_invoice_number = ""
        row.supplier_invoice_date = None

        mock_batch_objects.select_for_update.return_value.get.return_value = batch
        mock_row_objects.select_for_update.return_value.filter.return_value.order_by.return_value = [row]
        invoice_scope = MagicMock()
        invoice_scope.only.return_value = []
        mock_invoice_objects.filter.return_value.exclude.return_value = invoice_scope

        result = PurchaseGstr2bService.auto_match_batch(batch_id=5)

        self.assertEqual(result.not_matched, 1)
        self.assertEqual(row.match_status, "NOT_MATCHED")
        self.assertIsNone(row.matched_purchase_id)
        mock_sync.assert_called_once_with(previous_invoice)

    @patch("purchase.services.purchase_gstr2b_service.PurchaseGstr2bService._sync_invoice_match_status")
    @patch("purchase.services.purchase_gstr2b_service.PurchaseInvoiceHeader.objects")
    @patch("purchase.services.purchase_gstr2b_service.Gstr2bImportRow.objects")
    @patch("purchase.services.purchase_gstr2b_service.Gstr2bImportBatch.objects")
    def test_auto_match_batch_recomputes_old_and_new_invoice_state_for_partial_match(
        self,
        mock_batch_objects,
        mock_row_objects,
        mock_invoice_objects,
        mock_sync,
    ):
        batch = SimpleNamespace(id=6, entity_id=1, entityfinid_id=1, subentity_id=None)
        previous_invoice = MagicMock()
        previous_invoice.id = 402
        row = MagicMock()
        row.id = 52
        row.batch = batch
        row.matched_purchase = previous_invoice
        row.supplier_gstin = "27ABCDE1234F1Z5"
        row.supplier_invoice_number = "SUP-19"
        row.supplier_invoice_date = "2026-05-04"
        row.taxable_value = "100.00"
        row.cgst = "9.00"
        row.sgst = "9.00"
        row.igst = "0.00"
        row.cess = "0.00"
        new_invoice = MagicMock()
        new_invoice.id = 501
        new_invoice.supplier_invoice_date = "2026-05-05"
        new_invoice.total_taxable = "100.00"
        new_invoice.total_cgst = "9.00"
        new_invoice.total_sgst = "9.00"
        new_invoice.total_igst = "0.00"
        new_invoice.total_cess = "0.00"

        mock_batch_objects.select_for_update.return_value.get.return_value = batch
        mock_row_objects.select_for_update.return_value.filter.return_value.order_by.return_value = [row]
        invoice_scope = MagicMock()
        invoice_scope.filter.return_value = invoice_scope
        invoice_scope.only.return_value = [new_invoice]
        mock_invoice_objects.filter.return_value.exclude.return_value = invoice_scope

        result = PurchaseGstr2bService.auto_match_batch(batch_id=6)

        self.assertEqual(result.partial, 1)
        self.assertEqual(row.match_status, "PARTIAL")
        self.assertEqual(row.matched_purchase_id, 501)
        self.assertEqual(mock_sync.call_args_list[0].args[0], previous_invoice)
        self.assertEqual(mock_sync.call_args_list[1].args[0], new_invoice)

    def test_review_serializer_requires_purchase_link_for_matched_status(self):
        serializer = Gstr2bImportRowReviewSerializer(data={
            "match_status": "MATCHED",
            "comment": "manual confirmation",
            "matched_purchase": None,
        })

        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            serializer.errors["matched_purchase"][0],
            "A linked purchase invoice is required when marking a GSTR-2B row as matched or partial.",
        )

    def test_review_serializer_requires_purchase_link_for_partial_status(self):
        serializer = Gstr2bImportRowReviewSerializer(data={
            "match_status": "PARTIAL",
            "comment": "tax values differ",
        })

        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            serializer.errors["matched_purchase"][0],
            "A linked purchase invoice is required when marking a GSTR-2B row as matched or partial.",
        )

    @patch("purchase.services.purchase_gstr2b_service.Gstr2bImportRow.objects")
    def test_review_row_rejects_matched_status_without_purchase_link(self, mock_row_objects):
        mock_row_objects.select_for_update.return_value.get.return_value = SimpleNamespace(
            id=18,
            batch=SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None),
        )

        with self.assertRaisesMessage(
            ValueError,
            "A linked purchase invoice is required when marking a GSTR-2B row as matched or partial.",
        ):
            PurchaseGstr2bService.review_row(
                row_id=18,
                match_status="MATCHED",
                comment="manual confirmation",
                matched_purchase_id=None,
                reviewed_by_id=7,
            )

    @patch("purchase.services.purchase_gstr2b_service.timezone.now", return_value="2026-05-23T11:55:00")
    @patch("purchase.services.purchase_gstr2b_service.PurchaseInvoiceHeader.objects")
    @patch("purchase.services.purchase_gstr2b_service.Gstr2bImportRow.objects")
    def test_review_row_trims_comment_and_updates_invoice_match_state(
        self,
        mock_row_objects,
        mock_invoice_objects,
        _mock_now,
    ):
        row = MagicMock()
        row.id = 19
        row.batch = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None)
        invoice = MagicMock()
        invoice.id = 901
        invoice.gstr2b_match_status = None

        mock_row_objects.select_for_update.return_value.get.return_value = row
        mock_row_objects.filter.return_value.values_list.return_value = ["MATCHED"]
        mock_invoice_objects.filter.return_value.exclude.return_value.filter.return_value.first.return_value = invoice

        updated = PurchaseGstr2bService.review_row(
            row_id=19,
            match_status=" matched ",
            comment="  Matched from reviewer workspace  ",
            matched_purchase_id=901,
            reviewed_by_id=8,
        )

        self.assertIs(updated, row)
        self.assertEqual(row.match_status, "MATCHED")
        self.assertEqual(row.match_review_comment, "Matched from reviewer workspace")
        self.assertEqual(row.match_reviewed_by_id, 8)
        self.assertEqual(row.matched_purchase, invoice)
        row.save.assert_called_once_with(
            update_fields=[
                "match_status",
                "match_review_comment",
                "match_reviewed_by",
                "match_reviewed_at",
                "matched_purchase",
                "updated_at",
            ]
        )
        self.assertEqual(invoice.gstr2b_match_status, PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED)
        invoice.save.assert_called_once_with(update_fields=["gstr2b_match_status", "updated_at"])

    @patch("purchase.services.purchase_gstr2b_service.PurchaseGstr2bService._sync_invoice_match_status")
    @patch("purchase.services.purchase_gstr2b_service.timezone.now", return_value="2026-05-23T12:10:00")
    @patch("purchase.services.purchase_gstr2b_service.PurchaseInvoiceHeader.objects")
    @patch("purchase.services.purchase_gstr2b_service.Gstr2bImportRow.objects")
    def test_review_row_rematchs_between_invoices_and_recomputes_both_sides(
        self,
        mock_row_objects,
        mock_invoice_objects,
        _mock_now,
        mock_sync,
    ):
        previous_invoice = MagicMock()
        previous_invoice.id = 700
        previous_invoice.gstr2b_match_status = PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED
        row = MagicMock()
        row.id = 20
        row.batch = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None)
        row.matched_purchase = previous_invoice
        new_invoice = MagicMock()
        new_invoice.id = 901
        new_invoice.gstr2b_match_status = PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_CHECKED

        mock_row_objects.select_for_update.return_value.get.return_value = row
        mock_invoice_objects.filter.return_value.exclude.return_value.filter.return_value.first.return_value = new_invoice

        PurchaseGstr2bService.review_row(
            row_id=20,
            match_status="PARTIAL",
            comment="  shifted after manual review  ",
            matched_purchase_id=901,
            reviewed_by_id=8,
        )

        self.assertEqual(row.matched_purchase, new_invoice)
        self.assertEqual(row.match_status, "PARTIAL")
        self.assertEqual(row.match_review_comment, "shifted after manual review")
        self.assertEqual(mock_sync.call_args_list[0].args[0], previous_invoice)
        self.assertEqual(mock_sync.call_args_list[1].args[0], new_invoice)

    @patch("purchase.services.purchase_gstr2b_service.Gstr2bImportRow.objects")
    def test_sync_invoice_match_status_resets_to_not_checked_when_no_rows_remain(self, mock_row_objects):
        invoice = MagicMock()
        invoice.id = 300
        invoice.gstr2b_match_status = PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED
        mock_row_objects.filter.return_value.values_list.return_value = []

        PurchaseGstr2bService._sync_invoice_match_status(invoice)

        self.assertEqual(invoice.gstr2b_match_status, PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_CHECKED)
        invoice.save.assert_called_once_with(update_fields=["gstr2b_match_status", "updated_at"])

    @patch("purchase.services.purchase_gstr2b_service.Gstr2bImportRow.objects")
    def test_sync_invoice_match_status_prefers_partial_when_partial_rows_exist(self, mock_row_objects):
        invoice = MagicMock()
        invoice.id = 301
        invoice.gstr2b_match_status = PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_CHECKED
        mock_row_objects.filter.return_value.values_list.return_value = ["REVIEWED", "PARTIAL"]

        PurchaseGstr2bService._sync_invoice_match_status(invoice)

        self.assertEqual(invoice.gstr2b_match_status, PurchaseInvoiceHeader.Gstr2bMatchStatus.PARTIAL)
        invoice.save.assert_called_once_with(update_fields=["gstr2b_match_status", "updated_at"])
