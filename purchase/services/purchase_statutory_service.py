from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.models.purchase_statutory import (
    PurchaseStatutoryChallan,
    PurchaseStatutoryChallanLine,
    PurchaseStatutoryReturn,
    PurchaseStatutoryReturnLine,
)

Q2 = Decimal("0.01")
ZERO2 = Decimal("0.00")


def q2(x) -> Decimal:
    return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class StatutoryResult:
    obj: object
    message: str


class PurchaseStatutoryService:
    @staticmethod
    def _validate_header_amount_for_tax_type(*, header: PurchaseInvoiceHeader, tax_type: str, amount: Decimal) -> None:
        amt = q2(amount)
        if amt <= ZERO2:
            raise ValueError("Line amount must be > 0.")

        if tax_type == PurchaseStatutoryChallan.TaxType.IT_TDS:
            allowed = q2(getattr(header, "tds_amount", ZERO2))
            if allowed <= ZERO2:
                raise ValueError(f"Invoice {header.id} has no IT-TDS amount.")
            if amt > allowed:
                raise ValueError(f"Invoice {header.id}: amount {amt} exceeds IT-TDS {allowed}.")
            return

        if tax_type == PurchaseStatutoryChallan.TaxType.GST_TDS:
            allowed = q2(getattr(header, "gst_tds_amount", ZERO2))
            if allowed <= ZERO2:
                raise ValueError(f"Invoice {header.id} has no GST-TDS amount.")
            if amt > allowed:
                raise ValueError(f"Invoice {header.id}: amount {amt} exceeds GST-TDS {allowed}.")
            return

        raise ValueError("Unsupported tax_type.")

    @staticmethod
    @transaction.atomic
    def create_challan(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        tax_type: str,
        challan_no: str,
        challan_date,
        period_from=None,
        period_to=None,
        bank_ref_no: Optional[str] = None,
        bsr_code: Optional[str] = None,
        remarks: Optional[str] = None,
        lines: Optional[List[Dict]] = None,
        created_by_id: Optional[int] = None,
    ) -> StatutoryResult:
        line_rows = lines or []
        if not line_rows:
            raise ValueError("At least one line is required.")

        challan = PurchaseStatutoryChallan.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            tax_type=tax_type,
            challan_no=(challan_no or "").strip(),
            challan_date=challan_date,
            period_from=period_from,
            period_to=period_to,
            bank_ref_no=(bank_ref_no or "").strip() or None,
            bsr_code=(bsr_code or "").strip() or None,
            remarks=(remarks or "").strip() or None,
            created_by_id=created_by_id,
        )

        total = ZERO2
        for idx, row in enumerate(line_rows, start=1):
            header_id = row.get("header_id")
            amount = q2(row.get("amount"))
            section_id = row.get("section_id")
            if not header_id:
                raise ValueError(f"Line {idx}: header_id is required.")
            header = PurchaseInvoiceHeader.objects.filter(pk=header_id).first()
            if not header:
                raise ValueError(f"Line {idx}: header not found.")
            if int(header.entity_id or 0) != int(entity_id) or int(header.entityfinid_id or 0) != int(entityfinid_id):
                raise ValueError(f"Line {idx}: header scope mismatch with entity/entityfinid.")
            if header.subentity_id != subentity_id:
                raise ValueError(f"Line {idx}: header subentity mismatch.")

            PurchaseStatutoryService._validate_header_amount_for_tax_type(header=header, tax_type=tax_type, amount=amount)
            PurchaseStatutoryChallanLine.objects.create(
                challan=challan,
                header=header,
                section_id=section_id,
                amount=amount,
            )
            total = q2(total + amount)

        challan.amount = total
        challan.save(update_fields=["amount", "updated_at"])
        return StatutoryResult(challan, "Challan created.")

    @staticmethod
    @transaction.atomic
    def deposit_challan(*, challan_id: int, deposited_by_id: Optional[int] = None, deposited_on=None) -> StatutoryResult:
        c = PurchaseStatutoryChallan.objects.prefetch_related("lines__header").get(pk=challan_id)
        if int(c.status) == int(PurchaseStatutoryChallan.Status.CANCELLED):
            raise ValueError("Cancelled challan cannot be deposited.")
        if int(c.status) == int(PurchaseStatutoryChallan.Status.DEPOSITED):
            return StatutoryResult(c, "Already deposited.")

        c.status = PurchaseStatutoryChallan.Status.DEPOSITED
        c.deposited_on = deposited_on or timezone.localdate()
        c.deposited_at = timezone.now()
        c.deposited_by_id = deposited_by_id
        c.save(update_fields=["status", "deposited_on", "deposited_at", "deposited_by", "updated_at"])

        if c.tax_type == PurchaseStatutoryChallan.TaxType.GST_TDS:
            header_ids = [ln.header_id for ln in c.lines.all()]
            PurchaseInvoiceHeader.objects.filter(id__in=header_ids).update(
                gst_tds_status=PurchaseInvoiceHeader.GstTdsStatus.DEPOSITED
            )

        return StatutoryResult(c, "Challan deposited.")

    @staticmethod
    @transaction.atomic
    def create_return(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        tax_type: str,
        return_code: str,
        period_from,
        period_to,
        ack_no: Optional[str] = None,
        remarks: Optional[str] = None,
        lines: Optional[List[Dict]] = None,
        created_by_id: Optional[int] = None,
    ) -> StatutoryResult:
        line_rows = lines or []
        if not line_rows:
            raise ValueError("At least one line is required.")

        filing = PurchaseStatutoryReturn.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            tax_type=tax_type,
            return_code=(return_code or "").strip(),
            period_from=period_from,
            period_to=period_to,
            ack_no=(ack_no or "").strip() or None,
            remarks=(remarks or "").strip() or None,
            created_by_id=created_by_id,
        )

        total = ZERO2
        for idx, row in enumerate(line_rows, start=1):
            header_id = row.get("header_id")
            challan_id = row.get("challan_id")
            amount = q2(row.get("amount"))
            if not header_id:
                raise ValueError(f"Line {idx}: header_id is required.")
            header = PurchaseInvoiceHeader.objects.filter(pk=header_id).first()
            if not header:
                raise ValueError(f"Line {idx}: header not found.")
            if int(header.entity_id or 0) != int(entity_id) or int(header.entityfinid_id or 0) != int(entityfinid_id):
                raise ValueError(f"Line {idx}: header scope mismatch with entity/entityfinid.")
            if header.subentity_id != subentity_id:
                raise ValueError(f"Line {idx}: header subentity mismatch.")

            PurchaseStatutoryService._validate_header_amount_for_tax_type(
                header=header,
                tax_type=tax_type,
                amount=amount,
            )
            PurchaseStatutoryReturnLine.objects.create(
                filing=filing,
                header=header,
                challan_id=challan_id,
                amount=amount,
            )
            total = q2(total + amount)

        filing.amount = total
        filing.save(update_fields=["amount", "updated_at"])
        return StatutoryResult(filing, "Return draft created.")

    @staticmethod
    @transaction.atomic
    def file_return(*, filing_id: int, filed_by_id: Optional[int] = None, filed_on=None, ack_no: Optional[str] = None) -> StatutoryResult:
        f = PurchaseStatutoryReturn.objects.prefetch_related("lines__header").get(pk=filing_id)
        if int(f.status) == int(PurchaseStatutoryReturn.Status.CANCELLED):
            raise ValueError("Cancelled return cannot be filed.")
        if int(f.status) == int(PurchaseStatutoryReturn.Status.FILED):
            return StatutoryResult(f, "Already filed.")

        f.status = PurchaseStatutoryReturn.Status.FILED
        f.filed_on = filed_on or timezone.localdate()
        f.filed_at = timezone.now()
        f.filed_by_id = filed_by_id
        if ack_no is not None:
            f.ack_no = (ack_no or "").strip() or None
        f.save(update_fields=["status", "filed_on", "filed_at", "filed_by", "ack_no", "updated_at"])

        if f.tax_type == PurchaseStatutoryReturn.TaxType.GST_TDS:
            header_ids = [ln.header_id for ln in f.lines.all()]
            PurchaseInvoiceHeader.objects.filter(id__in=header_ids).update(
                gst_tds_status=PurchaseInvoiceHeader.GstTdsStatus.REPORTED
            )

        return StatutoryResult(f, "Return filed.")
