from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from purchase.models.purchase_core import (
    PurchaseInvoiceHeader,
    Status,
    ItcClaimStatus,
)

from purchase.services.purchase_settings_service import PurchaseSettingsService

from purchase.services.purchase_invoice_service import PurchaseInvoiceService

# ✅ Numbering imports (your requirement)
from numbering.services.document_number_service import DocumentNumberService
from numbering.models import DocumentType


@dataclass(frozen=True)
class ActionResult:
    header: PurchaseInvoiceHeader
    message: str


class PurchaseInvoiceActions:
    @staticmethod
    def _get(pk: int) -> PurchaseInvoiceHeader:
        return (
            PurchaseInvoiceHeader.objects
            .select_related(
                "vendor", "vendor_state",
                "supplier_state", "place_of_supply_state",
                "entity", "entityfinid", "subentity",
                "ref_document",
            )
            .prefetch_related("lines", "tax_summaries")
            .get(pk=pk)
        )

    # ----------------------------
    # Number allocation helpers
    # ----------------------------
    @staticmethod
    def _get_document_type_id_for_purchase(doc_code: str) -> int:
        """
        Resolve DocumentType for purchase module based on doc_code (PINV/PCN/PDN).
        """
        dt = DocumentType.objects.filter(
            module="purchase",
            default_code=doc_code,
            is_active=True,
        ).first()
        if not dt:
            raise ValueError(f"DocumentType not found for module='purchase' and doc_code='{doc_code}'")
        return dt.id

    @staticmethod
    def _allocate_final_number_if_missing(h: PurchaseInvoiceHeader) -> None:
        """
        Allocate final doc_no + purchase_number only once.
        Thread-safe: DocumentNumberService.allocate_final uses select_for_update.
        """
        if h.doc_no and h.purchase_number:
            return

        if not h.entity_id or not h.entityfinid_id:
            raise ValueError("entity and entityfinid are required for number allocation.")
        if not h.doc_code:
            raise ValueError("doc_code is required for number allocation.")

        dt_id = PurchaseInvoiceActions._get_document_type_id_for_purchase(h.doc_code)

        allocated = DocumentNumberService.allocate_final(
            entity_id=h.entity_id,
            entityfinid_id=h.entityfinid_id,
            subentity_id=h.subentity_id,
            doc_type_id=dt_id,
            doc_code=h.doc_code,
            on_date=h.bill_date,
        )

        h.doc_no = allocated.doc_no
        h.purchase_number = allocated.display_no
        h.save(update_fields=["doc_no", "purchase_number"])

    # ----------------------------
    # Actions
    # ----------------------------

    @staticmethod
    @transaction.atomic
    def confirm(pk: int) -> ActionResult:
        h = PurchaseInvoiceActions._get(pk)

        if int(h.status) == int(Status.CANCELLED):
            raise ValueError("Cannot confirm: document is cancelled.")
        if int(h.status) == int(Status.POSTED):
            return ActionResult(h, "Already posted.")

        if not h.lines.exists():
            raise ValueError("Cannot confirm: no lines exist.")

        # ✅ CRITICAL: allocate number even if status already CONFIRMED
        PurchaseInvoiceActions._allocate_final_number_if_missing(h)

        # ✅ Ensure tax summary is up-to-date
        PurchaseInvoiceService.rebuild_tax_summary(h)

        # If it was already confirmed, keep it confirmed and just return
        if int(h.status) == int(Status.CONFIRMED):
            return ActionResult(h, "Already confirmed (number ensured).")

        # Otherwise confirm now
        h.status = Status.CONFIRMED
        h.save(update_fields=["status"])
        return ActionResult(h, "Confirmed.")


    @staticmethod
    @transaction.atomic
    def post(pk: int) -> ActionResult:
        """
        Posting hook:
          - requires CONFIRMED
          - rebuild tax summary
          - set POSTED
          - later: integrate GL/Stock posting engine here
        """
        h = PurchaseInvoiceActions._get(pk)

        PurchaseInvoiceService.assert_not_locked(h.entity_id, h.subentity_id, h.bill_date)


        if int(h.status) == int(Status.CANCELLED):
            raise ValueError("Cannot post: document is cancelled.")
        if int(h.status) == int(Status.POSTED):
            return ActionResult(h, "Already posted.")
        if int(h.status) != int(Status.CONFIRMED):
            raise ValueError("Only CONFIRMED documents can be posted.")

        # Safety: if someone bypassed confirm, allocate here too
        PurchaseInvoiceActions._allocate_final_number_if_missing(h)

        PurchaseInvoiceService.rebuild_tax_summary(h)

        # TODO: integrate your posting engine here (JournalLine/StockTransactions)
        # purchase_posting.post_purchase_invoice(h)

        h.status = Status.POSTED
        h.save(update_fields=["status"])
        return ActionResult(h, "Posted successfully.")

    @staticmethod
    @transaction.atomic
    def cancel(pk: int) -> ActionResult:
        h = PurchaseInvoiceActions._get(pk)

        if int(h.status) == int(Status.POSTED):
            raise ValueError("Posted document cannot be cancelled. Create a Credit Note instead.")
        if int(h.status) == int(Status.CANCELLED):
            return ActionResult(h, "Already cancelled.")

        h.status = Status.CANCELLED
        h.save(update_fields=["status"])
        return ActionResult(h, "Cancelled.")

    @staticmethod
    @transaction.atomic
    def rebuild_tax_summary(pk: int) -> ActionResult:
        h = PurchaseInvoiceActions._get(pk)
        PurchaseInvoiceService.rebuild_tax_summary(h)
        return ActionResult(h, "Tax summary rebuilt.")

    # ----------------------------
    # ITC actions
    # ----------------------------

    @staticmethod
    @transaction.atomic
    def mark_itc_blocked(pk: int, reason: str) -> ActionResult:
        h = PurchaseInvoiceActions._get(pk)

        h.itc_claim_status = ItcClaimStatus.BLOCKED
        h.is_itc_eligible = False
        h.itc_block_reason = (reason or "").strip()[:200] or "Blocked"
        h.save(update_fields=["itc_claim_status", "is_itc_eligible", "itc_block_reason"])

        # rebuild summary for ITC eligible/ineligible buckets
        PurchaseInvoiceService.rebuild_tax_summary(h)

        return ActionResult(h, "ITC marked as Blocked.")

    @staticmethod
    @transaction.atomic
    def mark_itc_pending(pk: int) -> ActionResult:
        h = PurchaseInvoiceActions._get(pk)

        h.itc_claim_status = ItcClaimStatus.PENDING
        h.itc_claim_period = None
        h.itc_claimed_at = None
        h.save(update_fields=["itc_claim_status", "itc_claim_period", "itc_claimed_at"])

        return ActionResult(h, "ITC marked as Pending.")

    @staticmethod
    @transaction.atomic
    def mark_itc_claimed(pk: int, period: str) -> ActionResult:
        h = PurchaseInvoiceActions._get(pk)

        if not h.is_itc_eligible:
            raise ValueError("Cannot claim ITC: document is not ITC-eligible.")

        h.itc_claim_status = ItcClaimStatus.CLAIMED
        h.itc_claim_period = period
        h.itc_claimed_at = timezone.now()
        h.save(update_fields=["itc_claim_status", "itc_claim_period", "itc_claimed_at"])

        return ActionResult(h, "ITC marked as Claimed.")

    @staticmethod
    @transaction.atomic
    def mark_itc_reversed(pk: int, reason: Optional[str] = None) -> ActionResult:
        h = PurchaseInvoiceActions._get(pk)

        h.itc_claim_status = ItcClaimStatus.REVERSED
        if reason:
            h.itc_block_reason = reason[:200]
        h.save(update_fields=["itc_claim_status", "itc_block_reason"])

        # rebuild summary for ITC eligible/ineligible buckets
        PurchaseInvoiceService.rebuild_tax_summary(h)

        return ActionResult(h, "ITC marked as Reversed.")

    # ----------------------------
    # GSTR-2B match status
    # ----------------------------

    @staticmethod
    @transaction.atomic
    def update_2b_match_status(pk: int, match_status: int) -> ActionResult:
        h = PurchaseInvoiceActions._get(pk)
        h.gstr2b_match_status = match_status
        h.save(update_fields=["gstr2b_match_status"])
        return ActionResult(h, "GSTR-2B match status updated.")
