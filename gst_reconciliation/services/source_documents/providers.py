from __future__ import annotations

from decimal import Decimal

from gst_reconciliation.models import GstReconciliationItem, GstReconciliationRun
from gst_reconciliation.services.normalization import normalize_doc_type, normalize_gstin, normalize_invoice_number
from gst_reconciliation.services.source_documents.base import BaseSourceDocumentProvider, SourceDocumentMetadata
from purchase.models.purchase_core import PurchaseInvoiceHeader
from sales.models.sales_core import SalesInvoiceHeader
from vouchers.models.voucher_core import VoucherHeader


class PurchaseSourceProvider(BaseSourceDocumentProvider):
    provider_code = "purchase"
    source_document_type = "purchase_invoice_header"
    supported_reconciliation_types = (GstReconciliationRun.ReconciliationType.GSTR2B_PURCHASE,)
    search_fields = ("purchase_number", "supplier_invoice_number", "vendor_name", "vendor_gstin")

    def get_queryset_for_item(self, *, item):
        return self.get_queryset_for_scope(
            entity_id=item.entity_id,
            entityfinid_id=item.entityfinid_id,
            subentity_id=item.subentity_id,
        )

    def get_queryset_for_scope(self, *, entity_id: int, entityfinid_id: int, subentity_id: int | None):
        queryset = PurchaseInvoiceHeader.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        ).exclude(status=PurchaseInvoiceHeader.Status.CANCELLED)
        if subentity_id is None:
            queryset = queryset.filter(subentity__isnull=True)
        else:
            queryset = queryset.filter(subentity_id=subentity_id)
        return queryset.order_by("-bill_date", "-id")

    def apply_gstin_filter(self, *, queryset, gstin: str):
        return queryset.filter(vendor_gstin__iexact=gstin)

    def build_normalized_payload(self, obj) -> dict:
        return {
            "source_document_type": self.source_document_type,
            "source_document_id": str(obj.id),
            "document_number": self.first_nonempty(obj.purchase_number, obj.supplier_invoice_number, f"{obj.doc_code}-{obj.doc_no}"),
            "document_date": obj.bill_date.isoformat() if obj.bill_date else None,
            "doc_type_code": normalize_doc_type(obj.get_doc_type_display() if hasattr(obj, "get_doc_type_display") else obj.doc_type),
            # Purchase headers persist vendor GSTIN, but not always the buyer registration GSTIN.
            # Keep registration GSTIN empty here so run-level GSTIN validation does not
            # incorrectly compare the entity GSTIN against the vendor GSTIN.
            "gstin": None,
            "counterparty_gstin": normalize_gstin(obj.vendor_gstin),
            "invoice_number_normalized": normalize_invoice_number(self.first_nonempty(obj.supplier_invoice_number, obj.purchase_number)),
            "taxable_value": self.stringify_decimal(obj.total_taxable),
            "cgst": self.stringify_decimal(obj.total_cgst),
            "sgst": self.stringify_decimal(obj.total_sgst),
            "igst": self.stringify_decimal(obj.total_igst),
            "cess": self.stringify_decimal(obj.total_cess),
            "total_amount": self.stringify_decimal(obj.grand_total),
        }

    def to_metadata(self, obj) -> SourceDocumentMetadata:
        payload = self.build_normalized_payload(obj)
        return SourceDocumentMetadata(
            provider_code=self.provider_code,
            source_document_type=self.source_document_type,
            source_document_id=str(obj.id),
            document_number=payload["document_number"] or f"{obj.doc_code}-{obj.doc_no}",
            document_date=payload["document_date"],
            status=obj.get_status_display() if hasattr(obj, "get_status_display") else str(obj.status),
            item_type=self._map_item_type(obj.doc_type),
            direction=GstReconciliationItem.Direction.PURCHASE,
            party_name=obj.vendor_name or None,
            party_gstin=obj.vendor_gstin or None,
            gstin=None,
            taxable_value=payload["taxable_value"],
            cgst=payload["cgst"],
            sgst=payload["sgst"],
            igst=payload["igst"],
            cess=payload["cess"],
            total_amount=payload["total_amount"],
            summary=f"{payload['document_number'] or 'Purchase Invoice'} | {obj.vendor_name or obj.vendor_gstin or 'Unknown vendor'}",
            normalized_comparison_payload=payload,
        )

    @staticmethod
    def _map_item_type(doc_type: int) -> str:
        mapping = {
            PurchaseInvoiceHeader.DocType.CREDIT_NOTE: GstReconciliationItem.ItemType.CREDIT_NOTE,
            PurchaseInvoiceHeader.DocType.DEBIT_NOTE: GstReconciliationItem.ItemType.DEBIT_NOTE,
        }
        return mapping.get(doc_type, GstReconciliationItem.ItemType.INVOICE)


class SalesSourceProvider(BaseSourceDocumentProvider):
    provider_code = "sales"
    source_document_type = "sales_invoice_header"
    supported_reconciliation_types = (GstReconciliationRun.ReconciliationType.GSTR1_SALES,)
    search_fields = ("invoice_number", "customer_name", "customer_gstin")

    def get_queryset_for_item(self, *, item):
        return self.get_queryset_for_scope(
            entity_id=item.entity_id,
            entityfinid_id=item.entityfinid_id,
            subentity_id=item.subentity_id,
        )

    def get_queryset_for_scope(self, *, entity_id: int, entityfinid_id: int, subentity_id: int | None):
        queryset = SalesInvoiceHeader.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        ).exclude(status=SalesInvoiceHeader.Status.CANCELLED)
        if subentity_id is None:
            queryset = queryset.filter(subentity__isnull=True)
        else:
            queryset = queryset.filter(subentity_id=subentity_id)
        return queryset.order_by("-bill_date", "-id")

    def apply_gstin_filter(self, *, queryset, gstin: str):
        return queryset.filter(customer_gstin__iexact=gstin)

    def build_normalized_payload(self, obj) -> dict:
        total_amount = obj.grand_total or (
            (obj.total_taxable_value or Decimal("0.00"))
            + (obj.total_cgst or Decimal("0.00"))
            + (obj.total_sgst or Decimal("0.00"))
            + (obj.total_igst or Decimal("0.00"))
            + (obj.total_cess or Decimal("0.00"))
        )
        return {
            "source_document_type": self.source_document_type,
            "source_document_id": str(obj.id),
            "document_number": self.first_nonempty(obj.invoice_number, f"{obj.doc_code}-{obj.doc_no}"),
            "document_date": obj.bill_date.isoformat() if obj.bill_date else None,
            "doc_type_code": normalize_doc_type(obj.get_doc_type_display() if hasattr(obj, "get_doc_type_display") else obj.doc_type),
            "gstin": normalize_gstin(obj.seller_gstin),
            "counterparty_gstin": normalize_gstin(obj.customer_gstin),
            "invoice_number_normalized": normalize_invoice_number(obj.invoice_number),
            "taxable_value": self.stringify_decimal(obj.total_taxable_value),
            "cgst": self.stringify_decimal(obj.total_cgst),
            "sgst": self.stringify_decimal(obj.total_sgst),
            "igst": self.stringify_decimal(obj.total_igst),
            "cess": self.stringify_decimal(obj.total_cess),
            "total_amount": self.stringify_decimal(total_amount),
        }

    def to_metadata(self, obj) -> SourceDocumentMetadata:
        payload = self.build_normalized_payload(obj)
        return SourceDocumentMetadata(
            provider_code=self.provider_code,
            source_document_type=self.source_document_type,
            source_document_id=str(obj.id),
            document_number=payload["document_number"] or f"{obj.doc_code}-{obj.doc_no}",
            document_date=payload["document_date"],
            status=obj.get_status_display() if hasattr(obj, "get_status_display") else str(obj.status),
            item_type=self._map_item_type(obj.doc_type),
            direction=GstReconciliationItem.Direction.SALES,
            party_name=obj.customer_name or None,
            party_gstin=obj.customer_gstin or None,
            gstin=obj.seller_gstin or None,
            taxable_value=payload["taxable_value"],
            cgst=payload["cgst"],
            sgst=payload["sgst"],
            igst=payload["igst"],
            cess=payload["cess"],
            total_amount=payload["total_amount"],
            summary=f"{payload['document_number'] or 'Sales Invoice'} | {obj.customer_name or obj.customer_gstin or 'Unknown customer'}",
            normalized_comparison_payload=payload,
        )

    @staticmethod
    def _map_item_type(doc_type: int) -> str:
        mapping = {
            SalesInvoiceHeader.DocType.CREDIT_NOTE: GstReconciliationItem.ItemType.CREDIT_NOTE,
            SalesInvoiceHeader.DocType.DEBIT_NOTE: GstReconciliationItem.ItemType.DEBIT_NOTE,
        }
        return mapping.get(doc_type, GstReconciliationItem.ItemType.INVOICE)


class VoucherSourceProvider(BaseSourceDocumentProvider):
    provider_code = "voucher"
    source_document_type = "voucher_header"
    supported_reconciliation_types = (GstReconciliationRun.ReconciliationType.GSTR3B_BOOKS,)
    search_fields = ("voucher_code", "reference_number", "narration", "doc_code")

    def get_queryset_for_item(self, *, item):
        return self.get_queryset_for_scope(
            entity_id=item.entity_id,
            entityfinid_id=item.entityfinid_id,
            subentity_id=item.subentity_id,
        )

    def get_queryset_for_scope(self, *, entity_id: int, entityfinid_id: int, subentity_id: int | None):
        queryset = VoucherHeader.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        ).exclude(status=VoucherHeader.Status.CANCELLED)
        if subentity_id is None:
            queryset = queryset.filter(subentity__isnull=True)
        else:
            queryset = queryset.filter(subentity_id=subentity_id)
        return queryset.order_by("-voucher_date", "-id")

    def build_normalized_payload(self, obj) -> dict:
        total_amount = max(obj.total_debit_amount or Decimal("0.00"), obj.total_credit_amount or Decimal("0.00"))
        return {
            "source_document_type": self.source_document_type,
            "source_document_id": str(obj.id),
            "document_number": self.first_nonempty(obj.voucher_code, f"{obj.doc_code}-{obj.doc_no}"),
            "document_date": obj.voucher_date.isoformat() if obj.voucher_date else None,
            "doc_type_code": obj.voucher_type,
            "gstin": None,
            "counterparty_gstin": None,
            "invoice_number_normalized": normalize_invoice_number(self.first_nonempty(obj.voucher_code, obj.reference_number)),
            "taxable_value": "0.00",
            "cgst": "0.00",
            "sgst": "0.00",
            "igst": "0.00",
            "cess": "0.00",
            "total_amount": self.stringify_decimal(total_amount),
        }

    def to_metadata(self, obj) -> SourceDocumentMetadata:
        payload = self.build_normalized_payload(obj)
        return SourceDocumentMetadata(
            provider_code=self.provider_code,
            source_document_type=self.source_document_type,
            source_document_id=str(obj.id),
            document_number=payload["document_number"] or f"{obj.doc_code}-{obj.doc_no}",
            document_date=payload["document_date"],
            status=obj.get_status_display() if hasattr(obj, "get_status_display") else str(obj.status),
            item_type=GstReconciliationItem.ItemType.SUMMARY_BUCKET,
            direction=GstReconciliationItem.Direction.OUTPUT,
            party_name=None,
            party_gstin=None,
            gstin=None,
            taxable_value=payload["taxable_value"],
            cgst=payload["cgst"],
            sgst=payload["sgst"],
            igst=payload["igst"],
            cess=payload["cess"],
            total_amount=payload["total_amount"],
            summary=f"{payload['document_number'] or 'Voucher'} | {obj.voucher_type}",
            normalized_comparison_payload=payload,
        )
