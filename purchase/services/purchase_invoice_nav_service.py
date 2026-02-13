from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from purchase.models.purchase_core import PurchaseInvoiceHeader, Status


@dataclass(frozen=True)
class NavItem:
    id: int
    doc_no: int
    purchase_number: str
    status: int
    bill_date: Any  # date

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,  # optional for fast fetch
            "doc_no": self.doc_no,
            "purchase_number": self.purchase_number,
            "status": self.status,
            "bill_date": self.bill_date,
        }


class PurchaseInvoiceNavService:
    """
    Prev/Next navigation based on BUSINESS sequence (doc_no).
    NOT based on DB id.

    Filters:
    - entity, entityfinid, subentity
    - doc_type, doc_code
    - allowed_statuses (default: confirmed+posted)
    """

    DEFAULT_ALLOWED_STATUSES = (int(Status.DRAFT),int(Status.CONFIRMED), int(Status.POSTED))

    @staticmethod
    def _base_qs(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_type: int,
        doc_code: str,
        allowed_statuses: Sequence[int],
    ):
        return (
            PurchaseInvoiceHeader.objects.filter(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type=doc_type,
                doc_code=doc_code,
                status__in=list(allowed_statuses),
            )
            .only("id", "doc_no", "purchase_number", "status", "bill_date")
        )

    @staticmethod
    def get_prev_next_by_doc_no(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_type: int,
        doc_code: str,
        current_doc_no: int,
        allowed_statuses: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        """
        Returns:
        {
          "previous": {...} | None,
          "next": {...} | None
        }
        """
        allowed_statuses = allowed_statuses or PurchaseInvoiceNavService.DEFAULT_ALLOWED_STATUSES

        base = PurchaseInvoiceNavService._base_qs(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type=doc_type,
            doc_code=doc_code,
            allowed_statuses=allowed_statuses,
        )

        prev_obj = base.filter(doc_no__lt=current_doc_no).order_by("-doc_no").first()
        next_obj = base.filter(doc_no__gt=current_doc_no).order_by("doc_no").first()

        prev_item = (
            NavItem(
                id=prev_obj.id,
                doc_no=prev_obj.doc_no,
                purchase_number=prev_obj.purchase_number or "",
                status=prev_obj.status,
                bill_date=prev_obj.bill_date,
            ).to_dict()
            if prev_obj
            else None
        )

        next_item = (
            NavItem(
                id=next_obj.id,
                doc_no=next_obj.doc_no,
                purchase_number=next_obj.purchase_number or "",
                status=next_obj.status,
                bill_date=next_obj.bill_date,
            ).to_dict()
            if next_obj
            else None
        )

        return {"previous": prev_item, "next": next_item}

    @staticmethod
    def get_prev_next_for_instance(
        instance: PurchaseInvoiceHeader,
        *,
        allowed_statuses: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        """
        Convenience method for detail response.
        """
        if not instance.doc_no:
            return {"previous": None, "next": None}

        return PurchaseInvoiceNavService.get_prev_next_by_doc_no(
            entity_id=instance.entity_id,
            entityfinid_id=instance.entityfinid_id,
            subentity_id=instance.subentity_id,
            doc_type=int(instance.doc_type),
            doc_code=str(instance.doc_code),
            current_doc_no=int(instance.doc_no),
            allowed_statuses=allowed_statuses,
        )
