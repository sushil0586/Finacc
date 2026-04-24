from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence
from django.db.models import Exists, OuterRef

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
    ✅ Prev/Next strictly by id, but only within SAME:
      - entity
      - financial year (entityfinid)
      - subentity (including NULL vs non-NULL)
      - doc_type
      - doc_code
      - allowed statuses
    """

    DEFAULT_ALLOWED_STATUSES = (
        int(Status.DRAFT),
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
        doc_code: str,
        allowed_statuses: Sequence[int],
        line_mode: Optional[str] = None,
    ):
        filters: Dict[str, Any] = {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "doc_type": doc_type,
            "doc_code": doc_code,
            "status__in": list(allowed_statuses),
        }

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
    def get_prev_next_for_instance(
        instance: PurchaseInvoiceHeader,
        *,
        allowed_statuses: Optional[Sequence[int]] = None,
        line_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        allowed_statuses = allowed_statuses or PurchaseInvoiceNavService.DEFAULT_ALLOWED_STATUSES

        qs = PurchaseInvoiceNavService._scope_qs(
            entity_id=instance.entity_id,
            entityfinid_id=instance.entityfinid_id,
            subentity_id=instance.subentity_id,
            doc_type=int(instance.doc_type),
            doc_code=str(instance.doc_code),
            allowed_statuses=allowed_statuses,
            line_mode=line_mode,
        )

        # ✅ strictly by id, within scope
        prev_obj = qs.filter(id__lt=instance.id).order_by("-id").first()
        next_obj = qs.filter(id__gt=instance.id).order_by("id").first()

        # If mode-scoped neighbors are missing, fall back to same scope across all line modes.
        # Frontend can auto-redirect when crossing goods/service pages.
        if line_mode in ("service", "goods") and (not prev_obj or not next_obj):
            all_mode_qs = PurchaseInvoiceNavService._scope_qs(
                entity_id=instance.entity_id,
                entityfinid_id=instance.entityfinid_id,
                subentity_id=instance.subentity_id,
                doc_type=int(instance.doc_type),
                doc_code=str(instance.doc_code),
                allowed_statuses=allowed_statuses,
                line_mode=None,
            )
            if not prev_obj:
                prev_obj = all_mode_qs.filter(id__lt=instance.id).order_by("-id").first()
            if not next_obj:
                next_obj = all_mode_qs.filter(id__gt=instance.id).order_by("id").first()

        return {
            "previous": PurchaseInvoiceNavService._to_item(prev_obj),
            "next": PurchaseInvoiceNavService._to_item(next_obj),
        }
