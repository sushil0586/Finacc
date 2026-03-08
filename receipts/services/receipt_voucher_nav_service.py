from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from receipts.models.receipt_core import ReceiptVoucherHeader


@dataclass(frozen=True)
class NavItem:
    id: int
    doc_no: Optional[int]
    voucher_code: str
    status: int
    voucher_date: Any

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "doc_no": self.doc_no,
            "voucher_code": self.voucher_code,
            "status": self.status,
            "voucher_date": self.voucher_date,
        }


class ReceiptVoucherNavService:
    DEFAULT_ALLOWED_STATUSES = (
        int(ReceiptVoucherHeader.Status.DRAFT),
        int(ReceiptVoucherHeader.Status.CONFIRMED),
        int(ReceiptVoucherHeader.Status.POSTED),
        int(ReceiptVoucherHeader.Status.CANCELLED),
    )

    @staticmethod
    def _scope_qs(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_code: str,
        allowed_statuses: Sequence[int],
    ):
        filters: Dict[str, Any] = {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "doc_code": doc_code,
            "status__in": list(allowed_statuses),
        }
        if subentity_id is None:
            filters["subentity_id__isnull"] = True
        else:
            filters["subentity_id"] = subentity_id
        return ReceiptVoucherHeader.objects.filter(**filters).only(
            "id",
            "doc_no",
            "voucher_code",
            "status",
            "voucher_date",
        )

    @staticmethod
    def _empty_item() -> Dict[str, Any]:
        return {"id": -1, "doc_no": None, "voucher_code": "", "status": None, "voucher_date": None}

    @staticmethod
    def _to_item(obj: Optional[ReceiptVoucherHeader]) -> Dict[str, Any]:
        if not obj:
            return ReceiptVoucherNavService._empty_item()
        return NavItem(
            id=obj.id,
            doc_no=obj.doc_no,
            voucher_code=obj.voucher_code or "",
            status=int(obj.status),
            voucher_date=obj.voucher_date,
        ).to_dict()

    @staticmethod
    def get_prev_next_for_instance(
        instance: ReceiptVoucherHeader,
        *,
        allowed_statuses: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        allowed_statuses = allowed_statuses or ReceiptVoucherNavService.DEFAULT_ALLOWED_STATUSES
        qs = ReceiptVoucherNavService._scope_qs(
            entity_id=instance.entity_id,
            entityfinid_id=instance.entityfinid_id,
            subentity_id=instance.subentity_id,
            doc_code=str(instance.doc_code),
            allowed_statuses=allowed_statuses,
        )
        prev_obj = qs.filter(id__lt=instance.id).order_by("-id").first()
        next_obj = qs.filter(id__gt=instance.id).order_by("id").first()
        return {
            "previous": ReceiptVoucherNavService._to_item(prev_obj),
            "next": ReceiptVoucherNavService._to_item(next_obj),
        }

    @staticmethod
    def get_number_navigation(instance: ReceiptVoucherHeader) -> Dict[str, Any]:
        doc_type_row = (
            DocumentType.objects.filter(module="receipts", default_code=instance.doc_code, is_active=True)
            .only("id")
            .first()
        )
        if not doc_type_row:
            return {
                "enabled": False,
                "reason": f"DocumentType not found for receipts/{instance.doc_code}",
                "doc_type_id": None,
                "current_number": int(instance.doc_no) if instance.doc_no is not None else None,
                "previous_number": None,
                "previous_voucher_id": None,
                "previous_voucher_code": None,
                "previous_status": None,
                "previous_voucher_date": None,
                "next_number": None,
                "next_voucher_id": None,
                "next_voucher_code": None,
                "next_status": None,
                "next_voucher_date": None,
            }

        nav = ReceiptVoucherNavService.get_prev_next_for_instance(instance)
        prev_obj = nav["previous"]
        next_obj = nav["next"]

        current_number = int(instance.doc_no) if instance.doc_no is not None else None
        if current_number is None:
            try:
                preview = DocumentNumberService.peek_preview(
                    entity_id=instance.entity_id,
                    entityfinid_id=instance.entityfinid_id,
                    subentity_id=instance.subentity_id,
                    doc_type_id=doc_type_row.id,
                    doc_code=instance.doc_code,
                    on_date=instance.voucher_date,
                )
                current_number = int(preview.doc_no)
            except Exception:
                current_number = None

        return {
            "enabled": True,
            "doc_type_id": doc_type_row.id,
            "current_number": current_number,
            "previous_number": prev_obj.get("doc_no"),
            "previous_voucher_id": None if prev_obj.get("id") == -1 else prev_obj.get("id"),
            "previous_voucher_code": prev_obj.get("voucher_code") or None,
            "previous_status": prev_obj.get("status"),
            "previous_voucher_date": prev_obj.get("voucher_date"),
            "next_number": next_obj.get("doc_no"),
            "next_voucher_id": None if next_obj.get("id") == -1 else next_obj.get("id"),
            "next_voucher_code": next_obj.get("voucher_code") or None,
            "next_status": next_obj.get("status"),
            "next_voucher_date": next_obj.get("voucher_date"),
        }
