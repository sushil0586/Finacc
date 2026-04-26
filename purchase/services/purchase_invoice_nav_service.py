from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Optional, Sequence
from django.db.models import Exists, OuterRef, Q

from purchase.models.purchase_core import PurchaseInvoiceHeader, Status
from purchase.models.purchase_core import PurchaseInvoiceLine


@dataclass(frozen=True)
class NavItem:
    id: int
    doc_no: Optional[int]
    purchase_number: str
    status: int
    bill_date: Any  # date

    def to_dict(self) -> Dict[str, Any]:
        bill_date = self.bill_date
        return {
            "id": self.id,
            "doc_no": self.doc_no,
            "purchase_number": self.purchase_number,
            "status": self.status,
            "bill_date": bill_date.isoformat() if hasattr(bill_date, "isoformat") else str(bill_date) if bill_date else None,
        }


class PurchaseInvoiceNavService:
    """
    ✅ Prev/Next by numbered voucher sequence (doc_no), within SAME:
      - entity
      - financial year (entityfinid)
      - subentity (including NULL vs non-NULL)
      - doc_type
      - doc_code
      - allowed statuses

    Navigation is intentionally computed across combined goods+service invoices
    so doc sequence stays contiguous regardless of current screen mode.
    """

    # Navigation should move across confirmed, posted, and cancelled invoices.
    # Cancelled invoices are included only when they are numbered.
    DEFAULT_ALLOWED_STATUSES = (
        int(Status.CONFIRMED),
        int(Status.POSTED),
        int(Status.CANCELLED),
    )

    @staticmethod
    def _apply_line_mode_filter(qs, line_mode: Optional[str]):
        if line_mode not in ("service", "goods"):
            return qs
        matching_lines = PurchaseInvoiceLine.objects.filter(
            header_id=OuterRef("pk"),
            is_service=(line_mode == "service"),
        )
        return qs.annotate(_line_mode_match=Exists(matching_lines)).filter(_line_mode_match=True)

    @staticmethod
    def _scope_qs(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_type: int,
        doc_code: Optional[str],
        allowed_statuses: Sequence[int],
        line_mode: Optional[str] = None,
    ):
        filters: Dict[str, Any] = {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "doc_type": doc_type,
            "status__in": list(allowed_statuses),
        }
        if doc_code:
            filters["doc_code"] = doc_code

        # ✅ important: NULL subentity must match NULL only
        if subentity_id is None:
            filters["subentity_id__isnull"] = True
        else:
            filters["subentity_id"] = subentity_id

        qs = (
            PurchaseInvoiceHeader.objects
            .filter(**filters)
            .only("id", "doc_no", "purchase_number", "status", "bill_date")
        )
        if int(Status.CANCELLED) in set(int(value) for value in allowed_statuses):
            qs = qs.exclude(
                Q(status=int(Status.CANCELLED))
                & (Q(doc_no__isnull=True) | Q(doc_no__lte=0))
                & (Q(purchase_number__isnull=True) | Q(purchase_number__exact=""))
            )
        return PurchaseInvoiceNavService._apply_line_mode_filter(qs, line_mode)

    @staticmethod
    def _empty_item() -> Dict[str, Any]:
        return {"id": -1, "doc_no": None, "purchase_number": "", "status": None, "bill_date": None}

    @staticmethod
    def _to_item(obj: Optional[PurchaseInvoiceHeader]) -> Dict[str, Any]:
        if not obj:
            return PurchaseInvoiceNavService._empty_item()

        return NavItem(
            id=obj.id,
            doc_no=obj.doc_no,
            purchase_number=obj.purchase_number or "",
            status=obj.status,
            bill_date=obj.bill_date,
        ).to_dict()

    @staticmethod
    def _sequence_no(obj: Any) -> int:
        doc_no = int(getattr(obj, "doc_no", 0) or 0)
        if doc_no > 0:
            return doc_no
        purchase_number = str(getattr(obj, "purchase_number", "") or "").strip()
        if not purchase_number:
            return 0
        match = PurchaseInvoiceNavService._TRAILING_NUMBER_PATTERN.search(purchase_number)
        if not match:
            return 0
        return int(match.group(1) or 0)

    @staticmethod
    def get_prev_next_for_instance(
        instance: PurchaseInvoiceHeader,
        *,
        allowed_statuses: Optional[Sequence[int]] = None,
        line_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        allowed_statuses = allowed_statuses or PurchaseInvoiceNavService.DEFAULT_ALLOWED_STATUSES

        # Keep doc-code scoped queryset available for future tuning/debug parity.
        _doc_code_qs = PurchaseInvoiceNavService._scope_qs(
            entity_id=instance.entity_id,
            entityfinid_id=instance.entityfinid_id,
            subentity_id=instance.subentity_id,
            doc_type=int(instance.doc_type),
            doc_code=str(instance.doc_code),
            allowed_statuses=allowed_statuses,
            line_mode=None,
        )
        all_code_qs = PurchaseInvoiceNavService._scope_qs(
            entity_id=instance.entity_id,
            entityfinid_id=instance.entityfinid_id,
            subentity_id=instance.subentity_id,
            doc_type=int(instance.doc_type),
            doc_code=None,
            allowed_statuses=allowed_statuses,
            line_mode=None,
        )

        current_seq = PurchaseInvoiceNavService._sequence_no(instance)
        if current_seq > 0:
            rows = list(all_code_qs)
            prev_candidates = [
                row for row in rows
                if (
                    (PurchaseInvoiceNavService._sequence_no(row) < current_seq)
                    or (
                        PurchaseInvoiceNavService._sequence_no(row) == current_seq
                        and int(getattr(row, "id", 0) or 0) < int(getattr(instance, "id", 0) or 0)
                    )
                )
            ]
            next_candidates = [
                row for row in rows
                if (
                    (PurchaseInvoiceNavService._sequence_no(row) > current_seq)
                    or (
                        PurchaseInvoiceNavService._sequence_no(row) == current_seq
                        and int(getattr(row, "id", 0) or 0) > int(getattr(instance, "id", 0) or 0)
                    )
                )
            ]
            prev_obj = max(
                prev_candidates,
                key=lambda row: (
                    PurchaseInvoiceNavService._sequence_no(row),
                    int(getattr(row, "id", 0) or 0),
                ),
                default=None,
            )
            next_obj = min(
                next_candidates,
                key=lambda row: (
                    PurchaseInvoiceNavService._sequence_no(row),
                    int(getattr(row, "id", 0) or 0),
                ),
                default=None,
            )
        else:
            # Fallback for unnumbered current record (e.g., draft opened directly).
            prev_obj = all_code_qs.filter(id__lt=instance.id).order_by("-id").first()
            next_obj = all_code_qs.filter(id__gt=instance.id).order_by("id").first()

        return {
            "previous": PurchaseInvoiceNavService._to_item(prev_obj),
            "next": PurchaseInvoiceNavService._to_item(next_obj),
        }
    _TRAILING_NUMBER_PATTERN = re.compile(r"(\d+)\s*$")
