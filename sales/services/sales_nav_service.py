from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from sales.models.sales_core import SalesInvoiceHeader


@dataclass(frozen=True)
class NavItem:
    id: int
    doc_no: Optional[int]
    invoice_number: str
    status: int
    bill_date: Any  # date

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "doc_no": self.doc_no,
            "invoice_number": self.invoice_number,
            "status": self.status,
            "bill_date": self.bill_date,
        }


class SalesInvoiceNavService:
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
        int(SalesInvoiceHeader.Status.DRAFT),
        int(SalesInvoiceHeader.Status.CONFIRMED),
        int(SalesInvoiceHeader.Status.POSTED),
        int(SalesInvoiceHeader.Status.CANCELLED),
    )

    @staticmethod
    def _scope_qs(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_type: int,
        doc_code: str,
        allowed_statuses: Sequence[int],
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

        return (
            SalesInvoiceHeader.objects
            .filter(**filters)
            .only("id", "doc_no", "invoice_number", "status", "bill_date")
        )

    @staticmethod
    def _empty_item() -> Dict[str, Any]:
        return {"id": -1, "doc_no": None, "invoice_number": "", "status": None, "bill_date": None}

    @staticmethod
    def _to_item(obj: Optional[SalesInvoiceHeader]) -> Dict[str, Any]:
        if not obj:
            return SalesInvoiceNavService._empty_item()

        return NavItem(
            id=obj.id,
            doc_no=obj.doc_no,
            invoice_number=obj.invoice_number or "",
            status=int(obj.status),
            bill_date=obj.bill_date,
        ).to_dict()

    @staticmethod
    def get_prev_next_for_instance(
        instance: SalesInvoiceHeader,
        *,
        allowed_statuses: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        allowed_statuses = allowed_statuses or SalesInvoiceNavService.DEFAULT_ALLOWED_STATUSES

        qs = SalesInvoiceNavService._scope_qs(
            entity_id=instance.entity_id,
            entityfinid_id=instance.entityfinid_id,
            subentity_id=instance.subentity_id,
            doc_type=int(instance.doc_type),
            doc_code=str(instance.doc_code),
            allowed_statuses=allowed_statuses,
        )

        # ✅ strictly by id, within scope
        prev_obj = qs.filter(id__lt=instance.id).order_by("-id").first()
        next_obj = qs.filter(id__gt=instance.id).order_by("id").first()

        return {
            "previous": SalesInvoiceNavService._to_item(prev_obj),
            "next": SalesInvoiceNavService._to_item(next_obj),
        }
