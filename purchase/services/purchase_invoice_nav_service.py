from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from django.db.models import Case, IntegerField, Value, When

from purchase.models.purchase_core import PurchaseInvoiceHeader, Status


@dataclass(frozen=True)
class NavItem:
    id: int
    doc_no: Optional[int]
    purchase_number: str
    status: int
    bill_date: Any  # date

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "doc_no": self.doc_no,
            "purchase_number": self.purchase_number,
            "status": self.status,
            "bill_date": self.bill_date,
        }


class PurchaseInvoiceNavService:
    """
    Prev/Next across ALL statuses using a unified ordering:
      - drafts (doc_no is null) come first by id
      - then numbered docs by doc_no, tie-break by id
    """

    DEFAULT_ALLOWED_STATUSES = (
        int(Status.DRAFT),
        int(Status.CONFIRMED),
        int(Status.POSTED),
        int(Status.CANCELLED),
    )

    @staticmethod
    def _base_filters(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_type: int,
        doc_code: str,
        allowed_statuses: Sequence[int],
    ) -> Dict[str, Any]:
        filters: Dict[str, Any] = dict(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            doc_type=doc_type,
            doc_code=doc_code,
            status__in=list(allowed_statuses),
        )

        # keep subentity scope consistent
        if subentity_id is None:
            filters["subentity__isnull"] = True
        else:
            filters["subentity_id"] = subentity_id

        return filters

    @staticmethod
    def _ordered_qs(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_type: int,
        doc_code: str,
        allowed_statuses: Sequence[int],
    ):
        filters = PurchaseInvoiceNavService._base_filters(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type=doc_type,
            doc_code=doc_code,
            allowed_statuses=allowed_statuses,
        )

        # ✅ has_doc_no: 0 for drafts, 1 for numbered docs
        has_doc_no = Case(
            When(doc_no__isnull=True, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )

        return (
            PurchaseInvoiceHeader.objects
            .filter(**filters)
            .annotate(_has_doc_no=has_doc_no)
            .only("id", "doc_no", "purchase_number", "status", "bill_date")
            .order_by("_has_doc_no", "doc_no", "id")
        )

    @staticmethod
    def _empty_item() -> Dict[str, Any]:
        return {
            "id": -1,
            "doc_no": None,
            "purchase_number": "",
            "status": None,
            "bill_date": None,
        }

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
    ) -> Dict[str, Any]:
        allowed_statuses = allowed_statuses or PurchaseInvoiceNavService.DEFAULT_ALLOWED_STATUSES

        qs = PurchaseInvoiceNavService._ordered_qs(
            entity_id=instance.entity_id,
            entityfinid_id=instance.entityfinid_id,
            subentity_id=instance.subentity_id,
            doc_type=int(instance.doc_type),
            doc_code=str(instance.doc_code),
            allowed_statuses=allowed_statuses,
        )

        # We need prev/next relative to the current row in that global ordering.
        # Strategy: find current position by comparing ordering keys.

        if instance.doc_no is None:
            # current is draft: (has_doc_no=0, doc_no=NULL, id=instance.id)
            prev_obj = qs.filter(doc_no__isnull=True, id__lt=instance.id).order_by("-id").first()
            # next could be another draft by id, else first numbered doc
            next_obj = (
                qs.filter(doc_no__isnull=True, id__gt=instance.id).order_by("id").first()
                or qs.filter(doc_no__isnull=False).order_by("doc_no", "id").first()
            )
        else:
            # current is numbered: (has_doc_no=1, doc_no=..., id=...)
            # prev can be:
            # - last numbered doc with smaller doc_no
            # - OR if none, last draft
            prev_obj = (
                qs.filter(doc_no__isnull=False, doc_no__lt=instance.doc_no).order_by("-doc_no", "-id").first()
                or qs.filter(doc_no__isnull=True).order_by("-id").first()
            )
            # next is next numbered by doc_no, tie by id
            next_obj = qs.filter(doc_no__isnull=False, doc_no__gt=instance.doc_no).order_by("doc_no", "id").first()

        return {
            "previous": PurchaseInvoiceNavService._to_item(prev_obj),
            "next": PurchaseInvoiceNavService._to_item(next_obj),
        }
