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
    message: str


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
    def _assert_duplicate_note_guard(
        *,
        source_invoice: PurchaseInvoiceHeader,
        note_type: int,
        allow_duplicate: bool = False,
    ) -> None:
        if allow_duplicate:
            return

        existing = (
            PurchaseInvoiceHeader.objects
            .filter(
                ref_document_id=source_invoice.id,
                doc_type=note_type,
            )
            .exclude(status=Status.CANCELLED)
            .order_by("-created_at", "-id")
            .first()
        )
        if not existing:
            return

        note_label = "credit note" if int(note_type) == int(DocType.CREDIT_NOTE) else "debit note"
        raise ValueError(
            {
                "detail": f"An active {note_label} already exists for this purchase invoice. Open or cancel the existing note, or confirm if you want to create one more.",
                "duplicate_note_guard": {
                    "code": "purchase_duplicate_note_exists",
                    "note_type": int(note_type),
                    "existing_note_id": existing.id,
                    "existing_doc_no": getattr(existing, "doc_no", None),
                    "existing_purchase_number": getattr(existing, "purchase_number", None),
                    "existing_status": int(getattr(existing, "status", 0) or 0),
                },
            }
        )

    @staticmethod
    @transaction.atomic
    def create_note_from_invoice(
        *,
        invoice_id: int,
        note_type: int,
        note_reason: str = "qty_return",
        created_by_id: int | None = None,
        correction_reason: str | None = None,
        allow_duplicate: bool = False,
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

        PurchaseNoteFactory._assert_duplicate_note_guard(
            source_invoice=src,
            note_type=note_type,
            allow_duplicate=allow_duplicate,
        )

        is_qty_return = (note_reason == PurchaseInvoiceHeader.NoteReason.QUANTITY_RETURN)
        amendment_window = PurchaseInvoiceService.amendment_window_for_header(src)
        correction_date = amendment_window.correction_date or timezone.localdate()
        PurchaseInvoiceService.assert_note_correction_date_open(
            ref_document=src,
            correction_date=correction_date,
        )

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
            on_date=correction_date,
        )

        # Create note header (DRAFT by default)
        note = PurchaseInvoiceHeader.objects.create(
            # identity
            doc_type=note_type,
            bill_date=correction_date,
            posting_date=correction_date,
            due_date=correction_date,
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

            # CN/DN reason — drives inventory impact
            note_reason=note_reason,
            affects_inventory=is_qty_return,

            # scope
            subentity=src.subentity,
            location=src.location,
            entity=src.entity,
            entityfinid=src.entityfinid,

            created_by_id=created_by_id or src.created_by_id,
        )

        line_payloads = []
        for ln in src.lines.all().order_by("line_no", "id"):
            line_payloads.append(
                {
                    "line_no": ln.line_no,
                    "product": ln.product,
                    "purchase_account": getattr(ln, "purchase_account_id", None),
                    "product_desc": ln.product_desc,
                    "is_service": ln.is_service,
                    "purchase_behavior": getattr(ln, "purchase_behavior", None),
                    "hsn_sac": ln.hsn_sac,
                    "batch_number": getattr(ln, "batch_number", "") or "",
                    "manufacture_date": getattr(ln, "manufacture_date", None),
                    "expiry_date": getattr(ln, "expiry_date", None),
                    "uom": ln.uom,
                    "qty": ln.qty,
                    "free_qty": getattr(ln, "free_qty", 0),
                    "rate": ln.rate,
                    "taxability": ln.taxability,
                    "taxable_value": ln.taxable_value or 0,
                    "gst_rate": ln.gst_rate,
                    "cgst_percent": ln.cgst_percent,
                    "sgst_percent": ln.sgst_percent,
                    "igst_percent": ln.igst_percent,
                    "cgst_amount": ln.cgst_amount or 0,
                    "sgst_amount": ln.sgst_amount or 0,
                    "igst_amount": ln.igst_amount or 0,
                    "cess_amount": ln.cess_amount or 0,
                    "line_total": ln.line_total or 0,
                    "is_itc_eligible": ln.is_itc_eligible,
                    "itc_block_reason": ln.itc_block_reason,
                }
            )
        derived = PurchaseInvoiceService.derive_tax_regime(
            {
                "tax_regime": note.tax_regime,
                "is_igst": note.is_igst,
                "vendor_state": note.vendor_state,
                "supplier_state": note.supplier_state,
                "place_of_supply_state": note.place_of_supply_state,
            }
        )
        PurchaseInvoiceService.validate_lines_structural(
            {
                "doc_type": note.doc_type,
                "ref_document": src,
                "note_reason": note_reason,
                "vendor": note.vendor,
                "vendor_gstin": note.vendor_gstin,
                "default_taxability": note.default_taxability,
                "is_reverse_charge": note.is_reverse_charge,
                "is_itc_eligible": note.is_itc_eligible,
                "itc_claim_status": note.itc_claim_status,
                "supply_category": note.supply_category,
            },
            line_payloads,
            derived,
        )

        # Copy lines with document-native values.
        # Downstream posting and reports apply note polarity from doc_type.
        new_lines = []
        for ln in src.lines.all().order_by("line_no", "id"):
            new_lines.append(
                PurchaseInvoiceLine(
                    header=note,
                    line_no=ln.line_no,

                    product=ln.product,
                    purchase_account=ln.purchase_account,
                    product_desc=ln.product_desc,
                    is_service=ln.is_service,
                    purchase_behavior=getattr(ln, "purchase_behavior", None),
                    hsn_sac=ln.hsn_sac,
                    batch_number=getattr(ln, "batch_number", "") or "",
                    manufacture_date=getattr(ln, "manufacture_date", None),
                    expiry_date=getattr(ln, "expiry_date", None),

                    uom=ln.uom,
                    qty=ln.qty,
                    free_qty=getattr(ln, "free_qty", 0),
                    rate=ln.rate,

                    taxability=ln.taxability,
                    taxable_value=(ln.taxable_value or 0),

                    gst_rate=ln.gst_rate,
                    cgst_percent=ln.cgst_percent,
                    sgst_percent=ln.sgst_percent,
                    igst_percent=ln.igst_percent,

                    cgst_amount=(ln.cgst_amount or 0),
                    sgst_amount=(ln.sgst_amount or 0),
                    igst_amount=(ln.igst_amount or 0),
                    cess_amount=(ln.cess_amount or 0),
                    line_total=(ln.line_total or 0),

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
            "posting_date", "due_date",
            "total_taxable", "total_cgst", "total_sgst", "total_igst",
            "total_cess", "total_gst", "grand_total"
        ])

        PurchaseInvoiceService.append_correction_audit_event(
            original=src,
            correction=note,
            correction_type="purchase_credit_note" if int(note_type) == int(DocType.CREDIT_NOTE) else "purchase_debit_note",
            reason=correction_reason or note_reason,
            user_id=created_by_id,
            gst_period_impact=amendment_window.gst_period or correction_date.strftime("%Y-%m"),
        )

        note_label = "Credit Note" if int(note_type) == int(DocType.CREDIT_NOTE) else "Debit Note"
        return NoteCreateResult(header=note, message=f"{note_label} created successfully.")
