from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from purchase.models.gstr2b_models import Gstr2bImportBatch, Gstr2bImportRow
from purchase.models.purchase_core import PurchaseInvoiceHeader


@dataclass(frozen=True)
class Gstr2bMatchResult:
    batch: Gstr2bImportBatch
    total_rows: int
    matched: int
    partial: int
    multiple: int
    not_matched: int


class PurchaseGstr2bService:
    @staticmethod
    def _norm(value: Optional[str]) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _q2(value) -> Decimal:
        try:
            return Decimal(value or 0).quantize(Decimal("0.01"))
        except Exception:
            return Decimal("0.00")

    @staticmethod
    def _sync_invoice_match_status(invoice: PurchaseInvoiceHeader | None) -> None:
        if not invoice:
            return
        linked_statuses = list(
            Gstr2bImportRow.objects.filter(matched_purchase_id=invoice.id).values_list("match_status", flat=True)
        )
        normalized = {str(status or "").strip().upper() for status in linked_statuses}
        next_status = PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_CHECKED
        if "MATCHED" in normalized:
            next_status = PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED
        elif "PARTIAL" in normalized:
            next_status = PurchaseInvoiceHeader.Gstr2bMatchStatus.PARTIAL
        if invoice.gstr2b_match_status != next_status:
            invoice.gstr2b_match_status = next_status
            invoice.save(update_fields=["gstr2b_match_status", "updated_at"])

    @staticmethod
    @transaction.atomic
    def create_batch(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        period: str,
        source: str,
        reference: Optional[str],
        rows: List[Dict],
        imported_by_id: Optional[int],
    ) -> Gstr2bImportBatch:
        batch = Gstr2bImportBatch.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            period=period,
            source=(source or "gstr2b").strip()[:50],
            reference=(reference or "").strip()[:100] or None,
            imported_by_id=imported_by_id,
        )
        for row in rows:
            Gstr2bImportRow.objects.create(
                batch=batch,
                supplier_gstin=(row.get("supplier_gstin") or "").strip().upper() or None,
                supplier_name=(row.get("supplier_name") or "").strip() or None,
                supplier_invoice_number=(row.get("supplier_invoice_number") or "").strip() or None,
                supplier_invoice_date=row.get("supplier_invoice_date"),
                doc_type=(row.get("doc_type") or "").strip()[:20] or None,
                pos_state=row.get("pos_state"),
                is_igst=bool(row.get("is_igst", False)),
                taxable_value=row.get("taxable_value") or Decimal("0.00"),
                igst=row.get("igst") or Decimal("0.00"),
                cgst=row.get("cgst") or Decimal("0.00"),
                sgst=row.get("sgst") or Decimal("0.00"),
                cess=row.get("cess") or Decimal("0.00"),
                match_status="NOT_CHECKED",
            )
        return batch

    @staticmethod
    @transaction.atomic
    def auto_match_batch(*, batch_id: int) -> Gstr2bMatchResult:
        batch = Gstr2bImportBatch.objects.select_for_update().get(pk=batch_id)
        rows = list(
            Gstr2bImportRow.objects.select_for_update()
            .filter(batch_id=batch.id)
            .order_by("id")
        )

        invoices = PurchaseInvoiceHeader.objects.filter(
            entity_id=batch.entity_id,
            entityfinid_id=batch.entityfinid_id,
        ).exclude(status=PurchaseInvoiceHeader.Status.CANCELLED)
        if batch.subentity_id is None:
            invoices = invoices.filter(subentity__isnull=True)
        else:
            invoices = invoices.filter(subentity_id=batch.subentity_id)

        matched = partial = multiple = not_matched = 0
        for row in rows:
            previous_invoice = getattr(row, "matched_purchase", None)
            gstin = PurchaseGstr2bService._norm(row.supplier_gstin)
            inv_no = PurchaseGstr2bService._norm(row.supplier_invoice_number)
            qs = invoices
            if gstin:
                qs = qs.filter(vendor_gstin__iexact=gstin)
            if inv_no:
                qs = qs.filter(supplier_invoice_number__iexact=inv_no)

            candidates = list(qs.only(
                "id",
                "supplier_invoice_date",
                "total_taxable",
                "total_cgst",
                "total_sgst",
                "total_igst",
                "total_cess",
                "gstr2b_match_status",
            )[:5])

            if not candidates:
                row.matched_purchase_id = None
                row.match_status = "NOT_MATCHED"
                row.save(update_fields=["matched_purchase", "match_status", "updated_at"])
                PurchaseGstr2bService._sync_invoice_match_status(previous_invoice)
                not_matched += 1
                continue

            if len(candidates) > 1:
                row.matched_purchase_id = None
                row.match_status = "MULTIPLE"
                row.save(update_fields=["matched_purchase", "match_status", "updated_at"])
                PurchaseGstr2bService._sync_invoice_match_status(previous_invoice)
                multiple += 1
                continue

            invoice = candidates[0]
            row_tax_total = (
                PurchaseGstr2bService._q2(row.taxable_value)
                + PurchaseGstr2bService._q2(row.cgst)
                + PurchaseGstr2bService._q2(row.sgst)
                + PurchaseGstr2bService._q2(row.igst)
                + PurchaseGstr2bService._q2(row.cess)
            )
            inv_tax_total = (
                PurchaseGstr2bService._q2(getattr(invoice, "total_taxable", 0))
                + PurchaseGstr2bService._q2(getattr(invoice, "total_cgst", 0))
                + PurchaseGstr2bService._q2(getattr(invoice, "total_sgst", 0))
                + PurchaseGstr2bService._q2(getattr(invoice, "total_igst", 0))
                + PurchaseGstr2bService._q2(getattr(invoice, "total_cess", 0))
            )
            date_ok = not row.supplier_invoice_date or row.supplier_invoice_date == getattr(invoice, "supplier_invoice_date", None)
            amount_ok = abs(row_tax_total - inv_tax_total) <= Decimal("1.00")

            if date_ok and amount_ok:
                row.match_status = "MATCHED"
                matched += 1
            else:
                row.match_status = "PARTIAL"
                partial += 1

            row.matched_purchase_id = invoice.id
            row.save(update_fields=["matched_purchase", "match_status", "updated_at"])
            PurchaseGstr2bService._sync_invoice_match_status(previous_invoice)
            if not previous_invoice or getattr(previous_invoice, "id", None) != getattr(invoice, "id", None):
                PurchaseGstr2bService._sync_invoice_match_status(invoice)
            else:
                PurchaseGstr2bService._sync_invoice_match_status(previous_invoice)

        return Gstr2bMatchResult(
            batch=batch,
            total_rows=len(rows),
            matched=matched,
            partial=partial,
            multiple=multiple,
            not_matched=not_matched,
        )

    @staticmethod
    @transaction.atomic
    def review_row(
        *,
        row_id: int,
        match_status: str,
        comment: Optional[str],
        matched_purchase_id: Optional[int],
        reviewed_by_id: Optional[int],
    ) -> Gstr2bImportRow:
        row = Gstr2bImportRow.objects.select_for_update().get(pk=row_id)
        previous_invoice = getattr(row, "matched_purchase", None)
        normalized_status = str(match_status or "").strip().upper()
        allowed = {"NOT_CHECKED", "NOT_MATCHED", "PARTIAL", "MATCHED", "MULTIPLE", "REVIEWED"}
        if normalized_status not in allowed:
            raise ValueError("Invalid GSTR-2B review status.")
        if normalized_status in {"MATCHED", "PARTIAL"} and not matched_purchase_id:
            raise ValueError("A linked purchase invoice is required when marking a GSTR-2B row as matched or partial.")

        matched_purchase = None
        if matched_purchase_id:
            invoice_qs = PurchaseInvoiceHeader.objects.filter(
                pk=matched_purchase_id,
                entity_id=row.batch.entity_id,
                entityfinid_id=row.batch.entityfinid_id,
            ).exclude(status=PurchaseInvoiceHeader.Status.CANCELLED)
            if row.batch.subentity_id is None:
                invoice_qs = invoice_qs.filter(subentity__isnull=True)
            else:
                invoice_qs = invoice_qs.filter(subentity_id=row.batch.subentity_id)
            matched_purchase = invoice_qs.first()
            if not matched_purchase:
                raise ValueError("Selected purchase invoice is not valid for this GSTR-2B batch scope.")

        row.match_status = normalized_status
        row.match_review_comment = (comment or "").strip() or None
        row.match_reviewed_by_id = reviewed_by_id
        row.match_reviewed_at = timezone.now()
        row.matched_purchase = matched_purchase
        row.save(update_fields=["match_status", "match_review_comment", "match_reviewed_by", "match_reviewed_at", "matched_purchase", "updated_at"])
        PurchaseGstr2bService._sync_invoice_match_status(previous_invoice)
        if not previous_invoice or getattr(previous_invoice, "id", None) != getattr(matched_purchase, "id", None):
            PurchaseGstr2bService._sync_invoice_match_status(matched_purchase)

        return row
