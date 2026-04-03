from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from django.db import transaction

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
                not_matched += 1
                continue

            if len(candidates) > 1:
                row.matched_purchase_id = None
                row.match_status = "MULTIPLE"
                row.save(update_fields=["matched_purchase", "match_status", "updated_at"])
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
                invoice.gstr2b_match_status = PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED
                invoice.save(update_fields=["gstr2b_match_status", "updated_at"])
                matched += 1
            else:
                row.match_status = "PARTIAL"
                invoice.gstr2b_match_status = PurchaseInvoiceHeader.Gstr2bMatchStatus.PARTIAL
                invoice.save(update_fields=["gstr2b_match_status", "updated_at"])
                partial += 1

            row.matched_purchase_id = invoice.id
            row.save(update_fields=["matched_purchase", "match_status", "updated_at"])

        return Gstr2bMatchResult(
            batch=batch,
            total_rows=len(rows),
            matched=matched,
            partial=partial,
            multiple=multiple,
            not_matched=not_matched,
        )
