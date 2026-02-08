from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from purchase.services.purchase_settings_service import PurchaseSettingsService


from purchase.models.purchase_core import (
    PurchaseInvoiceHeader,
    PurchaseInvoiceLine,
    DocType,
    Status,
)
from purchase.services.purchase_invoice_service import PurchaseInvoiceService

# ✅ Numbering (your requirement)
from numbering.services.document_number_service import DocumentNumberService
from numbering.models import DocumentType


@dataclass(frozen=True)
class NoteCreateResult:
    header: PurchaseInvoiceHeader


class PurchaseNoteFactory:
    """
    Create Purchase Credit Note / Debit Note from an existing Purchase Invoice.

    - Credit Note: amounts become negative (sign = -1)
    - Debit Note: amounts stay positive (sign = +1)
    - doc_no/purchase_number allocated by DocumentNumberService.allocate_final() (thread-safe)
    """

    @staticmethod
    def _get_document_type_id_for_purchase(doc_code: str) -> int:
        dt = DocumentType.objects.filter(
            module="purchase",
            default_code=doc_code,
            is_active=True,
        ).first()
        if not dt:
            raise ValueError(f"DocumentType not found for module='purchase' and doc_code='{doc_code}'")
        return dt.id

    @staticmethod
    def _doc_code_for_note(note_type: int, fallback_doc_code: str) -> str:
        """
        Decide series doc_code for CN/DN.
        Change mapping if your customers use different codes.

        - PINV invoice -> PCN credit note / PDN debit note (recommended separate series)
        """
        if int(note_type) == int(DocType.CREDIT_NOTE):
            return "PCN"
        if int(note_type) == int(DocType.DEBIT_NOTE):
            return "PDN"
        return fallback_doc_code

    @staticmethod
    def _sign_for_note(note_type: int) -> int:
        # CN should reduce purchase: negative values
        if int(note_type) == int(DocType.CREDIT_NOTE):
            return -1
        return 1  # DN increases purchase

    @staticmethod
    @transaction.atomic
    def create_note_from_invoice(
        *,
        invoice_id: int,
        note_type: int,
        created_by_id: int | None = None,
    ) -> NoteCreateResult:
        src = (
            PurchaseInvoiceHeader.objects
            .select_related(
                "vendor", "vendor_state",
                "supplier_state", "place_of_supply_state",
                "entity", "entityfinid", "subentity",
            )
            .prefetch_related("lines")
            .get(pk=invoice_id)
        )

        if int(src.doc_type) != int(DocType.TAX_INVOICE):
            raise ValueError("Notes can be created only from a Tax Invoice document.")

        if int(src.status) == int(Status.CANCELLED):
            raise ValueError("Cannot create note from a cancelled invoice.")

        if int(note_type) not in (int(DocType.CREDIT_NOTE), int(DocType.DEBIT_NOTE)):
            raise ValueError("note_type must be CREDIT_NOTE or DEBIT_NOTE.")

        sign = PurchaseNoteFactory._sign_for_note(note_type)

        # Pick a doc_code series for the note (usually separate series PCN / PDN)
        settings = PurchaseSettingsService.get_settings(src.entity_id, src.subentity_id)

        if int(note_type) == int(DocType.CREDIT_NOTE):
            note_doc_code = settings.default_doc_code_cn
        elif int(note_type) == int(DocType.DEBIT_NOTE):
            note_doc_code = settings.default_doc_code_dn
        else:
            note_doc_code = settings.default_doc_code_invoice

        # Allocate number (thread-safe increment on series)
        dt_id = PurchaseNoteFactory._get_document_type_id_for_purchase(note_doc_code)

        allocated = DocumentNumberService.allocate_final(
            entity_id=src.entity_id,
            entityfinid_id=src.entityfinid_id,
            subentity_id=src.subentity_id,
            doc_type_id=dt_id,
            doc_code=note_doc_code,
            on_date=timezone.localdate(),
        )

        # Create note header (DRAFT by default)
        note = PurchaseInvoiceHeader.objects.create(
            # identity
            doc_type=note_type,
            bill_date=timezone.localdate(),
            doc_code=note_doc_code,
            doc_no=allocated.doc_no,
            purchase_number=allocated.display_no,

            supplier_invoice_number=None,
            supplier_invoice_date=None,

            ref_document=src,

            # vendor
            vendor=src.vendor,
            vendor_name=src.vendor_name,
            vendor_gstin=src.vendor_gstin,
            vendor_state=src.vendor_state,

            # tax settings
            supply_category=src.supply_category,
            default_taxability=src.default_taxability,
            tax_regime=src.tax_regime,
            is_igst=src.is_igst,
            supplier_state=src.supplier_state,
            place_of_supply_state=src.place_of_supply_state,

            # ITC + 2B (carry forward, user can edit)
            is_reverse_charge=src.is_reverse_charge,
            is_itc_eligible=src.is_itc_eligible,
            gstr2b_match_status=src.gstr2b_match_status,
            itc_claim_status=src.itc_claim_status,
            itc_claim_period=None,
            itc_claimed_at=None,
            itc_block_reason=src.itc_block_reason,

            # totals (will recompute after lines)
            total_taxable=0,
            total_cgst=0,
            total_sgst=0,
            total_igst=0,
            total_cess=0,
            total_gst=0,
            round_off=0,
            grand_total=0,

            status=Status.DRAFT,

            # scope
            subentity=src.subentity,
            entity=src.entity,
            entityfinid=src.entityfinid,

            created_by_id=created_by_id or src.created_by_id,
        )

        # Copy lines with sign handling:
        # - Keep qty positive (your UI can change qty if needed)
        # - Make values/taxes signed for CN
        new_lines = []
        for ln in src.lines.all().order_by("line_no", "id"):
            new_lines.append(
                PurchaseInvoiceLine(
                    header=note,
                    line_no=ln.line_no,

                    product=ln.product,
                    product_desc=ln.product_desc,
                    is_service=ln.is_service,
                    hsn_sac=ln.hsn_sac,

                    uom=ln.uom,
                    qty=ln.qty,   # qty stays positive
                    rate=ln.rate,

                    taxability=ln.taxability,
                    taxable_value=(ln.taxable_value or 0) * sign,

                    gst_rate=ln.gst_rate,
                    cgst_percent=ln.cgst_percent,
                    sgst_percent=ln.sgst_percent,
                    igst_percent=ln.igst_percent,

                    cgst_amount=(ln.cgst_amount or 0) * sign,
                    sgst_amount=(ln.sgst_amount or 0) * sign,
                    igst_amount=(ln.igst_amount or 0) * sign,
                    cess_amount=(ln.cess_amount or 0) * sign,
                    line_total=(ln.line_total or 0) * sign,

                    is_itc_eligible=ln.is_itc_eligible,
                    itc_block_reason=ln.itc_block_reason,
                )
            )

        PurchaseInvoiceLine.objects.bulk_create(new_lines)

        # Rebuild tax summary (and totals)
        PurchaseInvoiceService.rebuild_tax_summary(note)

        # Recompute totals from DB lines
        db_lines = list(note.lines.all().values(
            "taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "cess_amount"
        ))
        totals = PurchaseInvoiceService.compute_totals(db_lines)

        note.total_taxable = totals["total_taxable"]
        note.total_cgst = totals["total_cgst"]
        note.total_sgst = totals["total_sgst"]
        note.total_igst = totals["total_igst"]
        note.total_cess = totals["total_cess"]
        note.total_gst = totals["total_gst"]
        note.grand_total = totals["grand_total_base"] + (note.round_off or 0)
        note.save(update_fields=[
            "total_taxable", "total_cgst", "total_sgst", "total_igst",
            "total_cess", "total_gst", "grand_total"
        ])

        return NoteCreateResult(header=note)
