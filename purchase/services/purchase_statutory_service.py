from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from django.db import transaction
from django.db.models import Sum, Q
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
    def _clean_text(value: Optional[str]) -> Optional[str]:
        return (value or "").strip() or None

    @staticmethod
    def _vendor_pan(header: PurchaseInvoiceHeader) -> Optional[str]:
        try:
            vendor = getattr(header, "vendor", None)
            profile = getattr(vendor, "tax_profile", None) if vendor is not None else None
            return (getattr(profile, "pan", None) or "").strip() or None
        except Exception:
            return None

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
        cin_no: Optional[str] = None,
        minor_head_code: Optional[str] = None,
        interest_amount: Decimal = ZERO2,
        late_fee_amount: Decimal = ZERO2,
        penalty_amount: Decimal = ZERO2,
        payment_payload_json: Optional[Dict] = None,
        ack_document=None,
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
            bank_ref_no=PurchaseStatutoryService._clean_text(bank_ref_no),
            bsr_code=PurchaseStatutoryService._clean_text(bsr_code),
            cin_no=PurchaseStatutoryService._clean_text(cin_no),
            minor_head_code=PurchaseStatutoryService._clean_text(minor_head_code),
            interest_amount=q2(interest_amount),
            late_fee_amount=q2(late_fee_amount),
            penalty_amount=q2(penalty_amount),
            payment_payload_json=payment_payload_json or {},
            ack_document=ack_document,
            remarks=PurchaseStatutoryService._clean_text(remarks),
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
    def deposit_challan(
        *,
        challan_id: int,
        deposited_by_id: Optional[int] = None,
        deposited_on=None,
        bank_ref_no: Optional[str] = None,
        bsr_code: Optional[str] = None,
        cin_no: Optional[str] = None,
        minor_head_code: Optional[str] = None,
        payment_payload_json: Optional[Dict] = None,
        ack_document=None,
    ) -> StatutoryResult:
        c = PurchaseStatutoryChallan.objects.prefetch_related("lines__header").get(pk=challan_id)
        if int(c.status) == int(PurchaseStatutoryChallan.Status.CANCELLED):
            raise ValueError("Cancelled challan cannot be deposited.")
        if int(c.status) == int(PurchaseStatutoryChallan.Status.DEPOSITED):
            return StatutoryResult(c, "Already deposited.")

        c.status = PurchaseStatutoryChallan.Status.DEPOSITED
        c.deposited_on = deposited_on or timezone.localdate()
        c.deposited_at = timezone.now()
        c.deposited_by_id = deposited_by_id
        if bank_ref_no is not None:
            c.bank_ref_no = PurchaseStatutoryService._clean_text(bank_ref_no)
        if bsr_code is not None:
            c.bsr_code = PurchaseStatutoryService._clean_text(bsr_code)
        if cin_no is not None:
            c.cin_no = PurchaseStatutoryService._clean_text(cin_no)
        if minor_head_code is not None:
            c.minor_head_code = PurchaseStatutoryService._clean_text(minor_head_code)
        if payment_payload_json is not None:
            c.payment_payload_json = payment_payload_json
        if ack_document is not None:
            c.ack_document = ack_document
        c.save(
            update_fields=[
                "status",
                "deposited_on",
                "deposited_at",
                "deposited_by",
                "bank_ref_no",
                "bsr_code",
                "cin_no",
                "minor_head_code",
                "payment_payload_json",
                "ack_document",
                "updated_at",
            ]
        )

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
        arn_no: Optional[str] = None,
        interest_amount: Decimal = ZERO2,
        late_fee_amount: Decimal = ZERO2,
        penalty_amount: Decimal = ZERO2,
        filed_payload_json: Optional[Dict] = None,
        ack_document=None,
        original_return_id: Optional[int] = None,
        revision_no: int = 0,
        remarks: Optional[str] = None,
        lines: Optional[List[Dict]] = None,
        created_by_id: Optional[int] = None,
    ) -> StatutoryResult:
        line_rows = lines or []
        if not line_rows:
            raise ValueError("At least one line is required.")
        if original_return_id:
            original = PurchaseStatutoryReturn.objects.filter(pk=original_return_id).first()
            if not original:
                raise ValueError("original_return_id not found.")
            if int(original.entity_id) != int(entity_id) or int(original.entityfinid_id) != int(entityfinid_id):
                raise ValueError("original_return scope mismatch with entity/entityfinid.")
            if original.subentity_id != subentity_id:
                raise ValueError("original_return subentity mismatch.")
            if str(original.tax_type) != str(tax_type):
                raise ValueError("original_return tax_type mismatch.")

        filing = PurchaseStatutoryReturn.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            tax_type=tax_type,
            return_code=(return_code or "").strip(),
            period_from=period_from,
            period_to=period_to,
            ack_no=PurchaseStatutoryService._clean_text(ack_no),
            arn_no=PurchaseStatutoryService._clean_text(arn_no),
            interest_amount=q2(interest_amount),
            late_fee_amount=q2(late_fee_amount),
            penalty_amount=q2(penalty_amount),
            filed_payload_json=filed_payload_json or {},
            ack_document=ack_document,
            original_return_id=original_return_id,
            revision_no=max(int(revision_no or 0), 0),
            remarks=PurchaseStatutoryService._clean_text(remarks),
            created_by_id=created_by_id,
        )

        total = ZERO2
        for idx, row in enumerate(line_rows, start=1):
            header_id = row.get("header_id")
            challan_id = row.get("challan_id")
            amount = q2(row.get("amount"))
            section_snapshot_code = PurchaseStatutoryService._clean_text(row.get("section_snapshot_code"))
            section_snapshot_desc = PurchaseStatutoryService._clean_text(row.get("section_snapshot_desc"))
            deductee_pan_snapshot = PurchaseStatutoryService._clean_text(row.get("deductee_pan_snapshot"))
            deductee_gstin_snapshot = PurchaseStatutoryService._clean_text(row.get("deductee_gstin_snapshot"))
            cin_snapshot = PurchaseStatutoryService._clean_text(row.get("cin_snapshot"))
            metadata_json = row.get("metadata_json") or {}
            if not header_id:
                raise ValueError(f"Line {idx}: header_id is required.")
            header = PurchaseInvoiceHeader.objects.filter(pk=header_id).first()
            if not header:
                raise ValueError(f"Line {idx}: header not found.")
            if int(header.entity_id or 0) != int(entity_id) or int(header.entityfinid_id or 0) != int(entityfinid_id):
                raise ValueError(f"Line {idx}: header scope mismatch with entity/entityfinid.")
            if header.subentity_id != subentity_id:
                raise ValueError(f"Line {idx}: header subentity mismatch.")
            challan = None
            if challan_id:
                challan = PurchaseStatutoryChallan.objects.filter(pk=challan_id).first()
                if not challan:
                    raise ValueError(f"Line {idx}: challan not found.")
                if int(challan.entity_id) != int(entity_id) or int(challan.entityfinid_id) != int(entityfinid_id):
                    raise ValueError(f"Line {idx}: challan scope mismatch with entity/entityfinid.")
                if challan.subentity_id != subentity_id:
                    raise ValueError(f"Line {idx}: challan subentity mismatch.")
                if challan.tax_type != tax_type:
                    raise ValueError(f"Line {idx}: challan tax_type mismatch.")

            PurchaseStatutoryService._validate_header_amount_for_tax_type(
                header=header,
                tax_type=tax_type,
                amount=amount,
            )
            section_obj = getattr(header, "tds_section", None)
            if not section_snapshot_code and section_obj is not None:
                section_snapshot_code = PurchaseStatutoryService._clean_text(getattr(section_obj, "section_code", None))
            if not section_snapshot_desc and section_obj is not None:
                section_snapshot_desc = PurchaseStatutoryService._clean_text(getattr(section_obj, "description", None))
            if not deductee_pan_snapshot:
                deductee_pan_snapshot = PurchaseStatutoryService._vendor_pan(header)
            if not deductee_gstin_snapshot:
                deductee_gstin_snapshot = PurchaseStatutoryService._clean_text(getattr(header, "vendor_gstin", None))
            if not cin_snapshot and challan is not None:
                cin_snapshot = PurchaseStatutoryService._clean_text(getattr(challan, "cin_no", None))
            PurchaseStatutoryReturnLine.objects.create(
                filing=filing,
                header=header,
                challan_id=challan_id,
                amount=amount,
                section_snapshot_code=section_snapshot_code,
                section_snapshot_desc=section_snapshot_desc,
                deductee_pan_snapshot=deductee_pan_snapshot,
                deductee_gstin_snapshot=deductee_gstin_snapshot,
                cin_snapshot=cin_snapshot,
                metadata_json=metadata_json,
            )
            total = q2(total + amount)

        filing.amount = total
        filing.save(update_fields=["amount", "updated_at"])
        return StatutoryResult(filing, "Return draft created.")

    @staticmethod
    @transaction.atomic
    def file_return(
        *,
        filing_id: int,
        filed_by_id: Optional[int] = None,
        filed_on=None,
        ack_no: Optional[str] = None,
        arn_no: Optional[str] = None,
        filed_payload_json: Optional[Dict] = None,
        ack_document=None,
    ) -> StatutoryResult:
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
            f.ack_no = PurchaseStatutoryService._clean_text(ack_no)
        if arn_no is not None:
            f.arn_no = PurchaseStatutoryService._clean_text(arn_no)
        if filed_payload_json is not None:
            f.filed_payload_json = filed_payload_json
        if ack_document is not None:
            f.ack_document = ack_document
        f.save(
            update_fields=[
                "status",
                "filed_on",
                "filed_at",
                "filed_by",
                "ack_no",
                "arn_no",
                "filed_payload_json",
                "ack_document",
                "updated_at",
            ]
        )

        if f.tax_type == PurchaseStatutoryReturn.TaxType.GST_TDS:
            header_ids = [ln.header_id for ln in f.lines.all()]
            PurchaseInvoiceHeader.objects.filter(id__in=header_ids).update(
                gst_tds_status=PurchaseInvoiceHeader.GstTdsStatus.REPORTED
            )

        return StatutoryResult(f, "Return filed.")

    @staticmethod
    def reconciliation_summary(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        tax_type: Optional[str] = None,
        date_from=None,
        date_to=None,
    ) -> Dict[str, str]:
        header_qs = PurchaseInvoiceHeader.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        challan_qs = PurchaseStatutoryChallan.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        return_qs = PurchaseStatutoryReturn.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        if subentity_id is None:
            header_qs = header_qs.filter(subentity__isnull=True)
            challan_qs = challan_qs.filter(subentity__isnull=True)
            return_qs = return_qs.filter(subentity__isnull=True)
        else:
            header_qs = header_qs.filter(subentity_id=subentity_id)
            challan_qs = challan_qs.filter(subentity_id=subentity_id)
            return_qs = return_qs.filter(subentity_id=subentity_id)

        if date_from is not None:
            header_qs = header_qs.filter(bill_date__gte=date_from)
            challan_qs = challan_qs.filter(challan_date__gte=date_from)
            # Returns are period based; include rows where period end is after range start.
            return_qs = return_qs.filter(period_to__gte=date_from)
        if date_to is not None:
            header_qs = header_qs.filter(bill_date__lte=date_to)
            challan_qs = challan_qs.filter(challan_date__lte=date_to)
            # Returns are period based; include rows where period start is before range end.
            return_qs = return_qs.filter(period_from__lte=date_to)

        if tax_type == PurchaseStatutoryChallan.TaxType.IT_TDS:
            deducted = header_qs.aggregate(t=Sum("tds_amount"))["t"] or ZERO2
            challan_qs = challan_qs.filter(tax_type=PurchaseStatutoryChallan.TaxType.IT_TDS)
            return_qs = return_qs.filter(tax_type=PurchaseStatutoryReturn.TaxType.IT_TDS)
        elif tax_type == PurchaseStatutoryChallan.TaxType.GST_TDS:
            deducted = header_qs.aggregate(t=Sum("gst_tds_amount"))["t"] or ZERO2
            challan_qs = challan_qs.filter(tax_type=PurchaseStatutoryChallan.TaxType.GST_TDS)
            return_qs = return_qs.filter(tax_type=PurchaseStatutoryReturn.TaxType.GST_TDS)
        else:
            deducted_it = header_qs.aggregate(t=Sum("tds_amount"))["t"] or ZERO2
            deducted_gst = header_qs.aggregate(t=Sum("gst_tds_amount"))["t"] or ZERO2
            deducted = q2(q2(deducted_it) + q2(deducted_gst))

        deposited = challan_qs.filter(status=PurchaseStatutoryChallan.Status.DEPOSITED).aggregate(t=Sum("amount"))["t"] or ZERO2
        deposited_interest = challan_qs.filter(status=PurchaseStatutoryChallan.Status.DEPOSITED).aggregate(t=Sum("interest_amount"))[
            "t"
        ] or ZERO2
        deposited_late_fee = challan_qs.filter(status=PurchaseStatutoryChallan.Status.DEPOSITED).aggregate(t=Sum("late_fee_amount"))[
            "t"
        ] or ZERO2
        deposited_penalty = challan_qs.filter(status=PurchaseStatutoryChallan.Status.DEPOSITED).aggregate(t=Sum("penalty_amount"))[
            "t"
        ] or ZERO2
        filed = return_qs.filter(status=PurchaseStatutoryReturn.Status.FILED).aggregate(t=Sum("amount"))["t"] or ZERO2
        filed_interest = return_qs.filter(status=PurchaseStatutoryReturn.Status.FILED).aggregate(t=Sum("interest_amount"))["t"] or ZERO2
        filed_late_fee = return_qs.filter(status=PurchaseStatutoryReturn.Status.FILED).aggregate(t=Sum("late_fee_amount"))["t"] or ZERO2
        filed_penalty = return_qs.filter(status=PurchaseStatutoryReturn.Status.FILED).aggregate(t=Sum("penalty_amount"))["t"] or ZERO2
        draft_challan = challan_qs.filter(status=PurchaseStatutoryChallan.Status.DRAFT).aggregate(t=Sum("amount"))["t"] or ZERO2
        draft_return = return_qs.filter(status=PurchaseStatutoryReturn.Status.DRAFT).aggregate(t=Sum("amount"))["t"] or ZERO2

        return {
            "deducted": str(q2(deducted)),
            "deposited": str(q2(deposited)),
            "deposited_interest": str(q2(deposited_interest)),
            "deposited_late_fee": str(q2(deposited_late_fee)),
            "deposited_penalty": str(q2(deposited_penalty)),
            "filed": str(q2(filed)),
            "filed_interest": str(q2(filed_interest)),
            "filed_late_fee": str(q2(filed_late_fee)),
            "filed_penalty": str(q2(filed_penalty)),
            "pending_deposit": str(q2(q2(deducted) - q2(deposited))),
            "pending_filing": str(q2(q2(deposited) - q2(filed))),
            "draft_challan": str(q2(draft_challan)),
            "draft_return": str(q2(draft_return)),
        }
