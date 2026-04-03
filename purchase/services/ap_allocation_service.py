from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from purchase.models.purchase_ap import VendorBillOpenItem
from purchase.services.purchase_settings_service import PurchaseSettingsService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(x) -> Decimal:
    return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)


class PurchaseApAllocationService:
    """Computes reference-aware, policy-driven allocatable AP rows for settlements/payments."""

    @staticmethod
    def _policy_controls(entity_id: int, subentity_id: Optional[int]) -> Dict[str, str]:
        policy = PurchaseSettingsService.get_policy(entity_id, subentity_id)
        return policy.controls

    @staticmethod
    def _open_items_queryset(*, entity_id: int, entityfinid_id: int, subentity_id: Optional[int], vendor_id: int, is_open: bool = True):
        qs = VendorBillOpenItem.objects.select_related("header", "header__ref_document").filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            vendor_id=vendor_id,
        )
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        if is_open:
            qs = qs.filter(is_open=True)
        return qs.order_by("due_date", "bill_date", "id")

    @staticmethod
    def _consumption_mode(controls: Dict[str, str]) -> str:
        mode = str(controls.get("credit_note_consumption_mode", "reference_then_fifo")).lower().strip()
        if mode not in {"off", "fifo", "reference_only", "reference_then_fifo"}:
            return "reference_then_fifo"
        return mode

    @staticmethod
    def _positive_doc_type(doc_type: Optional[int]) -> bool:
        # Purchase: 1=invoice, 3=debit note are positive payable types.
        return int(doc_type or 0) in {1, 3}

    @staticmethod
    def _negative_doc_type(doc_type: Optional[int]) -> bool:
        # Purchase: 2=credit note.
        return int(doc_type or 0) == 2

    @classmethod
    def build_open_item_projection(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        vendor_id: int,
        controls: Optional[Dict[str, str]] = None,
    ) -> List[Dict]:
        controls = controls or cls._policy_controls(entity_id, subentity_id)
        mode = cls._consumption_mode(controls)

        rows = []
        positives = []
        negatives = []

        for idx, item in enumerate(
            cls._open_items_queryset(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                vendor_id=vendor_id,
                is_open=True,
            ),
            start=1,
        ):
            raw = q2(item.outstanding_amount)
            row = {
                "id": item.id,
                "header_id": item.header_id,
                "doc_type": int(item.doc_type or 0),
                "raw_outstanding_amount": raw,
                "credit_adjusted_amount": ZERO2,
                "allocatable_amount": ZERO2,
                "allocation_sequence": idx,
                "reference_invoice_header_id": getattr(getattr(item, "header", None), "ref_document_id", None),
                "document_number": item.purchase_number or item.supplier_invoice_number or "",
                "supplier_invoice_number": item.supplier_invoice_number or "",
                "_credit_note_details": [],
            }
            rows.append(row)
            if raw <= ZERO2:
                if cls._negative_doc_type(item.doc_type):
                    negatives.append(row)
                continue
            if cls._positive_doc_type(item.doc_type):
                row["allocatable_amount"] = raw
                positives.append(row)

        def apply_credit_to_positive(target_row: Dict, amt: Decimal, source_row: Optional[Dict] = None) -> Decimal:
            if amt <= ZERO2:
                return ZERO2
            available = q2(target_row["allocatable_amount"])
            if available <= ZERO2:
                return amt
            use = min(available, amt)
            target_row["credit_adjusted_amount"] = q2(target_row["credit_adjusted_amount"] + use)
            target_row["allocatable_amount"] = q2(available - use)
            if source_row and use > ZERO2:
                target_row.setdefault("_credit_note_details", []).append(
                    {
                        "open_item_id": source_row.get("id"),
                        "header_id": source_row.get("header_id"),
                        "doc_type": source_row.get("doc_type"),
                        "document_number": source_row.get("document_number") or "",
                        "supplier_invoice_number": source_row.get("supplier_invoice_number") or "",
                        "applied_amount": q2(use),
                    }
                )
            return q2(amt - use)

        if mode != "off" and negatives:
            positives_by_header = {p["header_id"]: p for p in positives}
            positives_fifo = sorted(positives, key=lambda x: (x["allocation_sequence"], x["id"]))

            for neg in sorted(negatives, key=lambda x: (x["allocation_sequence"], x["id"])):
                remaining_credit = q2(abs(neg["raw_outstanding_amount"]))
                if remaining_credit <= ZERO2:
                    continue

                ref_header_id = neg.get("reference_invoice_header_id")
                if mode in {"reference_only", "reference_then_fifo"} and ref_header_id:
                    target = positives_by_header.get(ref_header_id)
                    if target:
                        remaining_credit = apply_credit_to_positive(target, remaining_credit, neg)

                if mode in {"fifo", "reference_then_fifo"} and remaining_credit > ZERO2:
                    for p in positives_fifo:
                        if remaining_credit <= ZERO2:
                            break
                        remaining_credit = apply_credit_to_positive(p, remaining_credit, neg)

        for row in rows:
            row["raw_outstanding_amount"] = q2(row["raw_outstanding_amount"])
            row["credit_adjusted_amount"] = q2(row["credit_adjusted_amount"])
            row["allocatable_amount"] = q2(row["allocatable_amount"])
            row["is_allocatable"] = bool(row["allocatable_amount"] > ZERO2)
            credit_details = row.pop("_credit_note_details", [])
            row["credit_note_details"] = credit_details
            if row["credit_adjusted_amount"] > ZERO2 and credit_details:
                refs = [d.get("document_number") for d in credit_details if d.get("document_number")]
                refs_text = ", ".join(refs[:5])
                if len(refs) > 5:
                    refs_text += ", ..."
                row["credit_adjustment_reason"] = (
                    f"Adjusted by linked credit note(s): {refs_text}" if refs_text else "Adjusted by linked credit note(s)."
                )
            elif row["credit_adjusted_amount"] > ZERO2:
                row["credit_adjustment_reason"] = "Adjusted by linked credit note(s)."
            else:
                row["credit_adjustment_reason"] = ""

        return rows

    @classmethod
    def allocatable_map(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        vendor_id: int,
        controls: Optional[Dict[str, str]] = None,
    ) -> Dict[int, Decimal]:
        rows = cls.build_open_item_projection(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            controls=controls,
        )
        return {int(r["id"]): q2(r["allocatable_amount"]) for r in rows}

    @classmethod
    def preview_allocation(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        vendor_id: int,
        target_amount: Decimal,
        controls: Optional[Dict[str, str]] = None,
    ) -> Dict:
        rows = cls.build_open_item_projection(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            controls=controls,
        )
        remaining = q2(target_amount)
        plan = []
        for row in sorted(rows, key=lambda x: (x["allocation_sequence"], x["id"])):
            alloc = q2(row["allocatable_amount"])
            if alloc <= ZERO2 or remaining <= ZERO2:
                continue
            use = min(alloc, remaining)
            plan.append(
                {
                    "open_item": row["id"],
                    "settled_amount": q2(use),
                    "is_full_settlement": q2(use) >= alloc,
                    "is_advance_adjustment": False,
                }
            )
            remaining = q2(remaining - use)
        return {
            "target_amount": q2(target_amount),
            "planned_amount": q2(sum((q2(p["settled_amount"]) for p in plan), ZERO2)),
            "unallocated_amount": q2(remaining),
            "plan": plan,
            "open_items": rows,
        }
