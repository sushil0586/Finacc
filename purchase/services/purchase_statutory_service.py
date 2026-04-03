from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from financial.profile_access import account_gstno, account_pan

from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.services.purchase_settings_service import PurchaseSettingsService
from purchase.models.purchase_statutory import (
    PurchaseStatutoryChallan,
    PurchaseStatutoryChallanLine,
    PurchaseStatutoryForm16AOfficialDocument,
    PurchaseStatutoryReturn,
    PurchaseStatutoryReturnLine,
)
from purchase.models.itc_models import PurchaseItcAction

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
    def _form16a_certificate_data(
        *,
        filing: PurchaseStatutoryReturn,
        issue: Dict[str, object],
    ) -> Dict[str, object]:
        line_rows = []
        for ln in filing.lines.select_related("header", "challan").all():
            line_rows.append(
                {
                    "invoice_no": getattr(ln.header, "purchase_number", "") if ln.header_id else "",
                    "bill_date": getattr(ln.header, "bill_date", None) if ln.header_id else None,
                    "section_code": ln.section_snapshot_code or "",
                    "pan": ln.deductee_pan_snapshot or "",
                    "gstin": ln.deductee_gstin_snapshot or "",
                    "challan_no": getattr(ln.challan, "challan_no", "") if ln.challan_id else "",
                    "cin": ln.cin_snapshot or "",
                    "amount": str(q2(ln.amount)),
                }
            )
        return {
            "filing_id": filing.id,
            "return_code": filing.return_code,
            "period_from": str(filing.period_from),
            "period_to": str(filing.period_to),
            "issue_no": issue.get("issue_no"),
            "issue_code": issue.get("issue_code"),
            "issued_on": issue.get("issued_on"),
            "line_count": len(line_rows),
            "total_amount": str(q2(sum((q2(r.get("amount") or 0) for r in line_rows), ZERO2))),
            "lines": line_rows,
        }

    @staticmethod
    def _is_form16a_eligible_return(filing: PurchaseStatutoryReturn) -> bool:
        if filing.tax_type != PurchaseStatutoryReturn.TaxType.IT_TDS:
            return False
        code = (filing.return_code or "").strip().upper()
        if code not in {"26Q", "27Q"}:
            return False
        return int(filing.status) in (
            int(PurchaseStatutoryReturn.Status.FILED),
            int(PurchaseStatutoryReturn.Status.REVISED),
        )

    @staticmethod
    def _clean_text(value: Optional[str]) -> Optional[str]:
        return (value or "").strip() or None

    @staticmethod
    def _coerce_date(value, *, field_name: str):
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except Exception:
            raise ValueError(f"{field_name} must be YYYY-MM-DD.")

    @staticmethod
    def _vendor_pan(header: PurchaseInvoiceHeader) -> Optional[str]:
        try:
            vendor = getattr(header, "vendor", None)
            return (account_pan(vendor) or "").strip() or None
        except Exception:
            return None

    @staticmethod
    def _vendor_country_obj(header: PurchaseInvoiceHeader):
        try:
            vendor = getattr(header, "vendor", None)
            return getattr(vendor, "country", None) if vendor is not None else None
        except Exception:
            return None

    @staticmethod
    def _derive_residency_from_country(country_obj) -> str:
        if not country_obj:
            return PurchaseStatutoryReturnLine.DeducteeResidency.RESIDENT
        code = (getattr(country_obj, "countrycode", "") or "").strip().upper()
        name = (getattr(country_obj, "countryname", "") or "").strip().upper()
        if code in {"IN", "IND", "356"} or name == "INDIA":
            return PurchaseStatutoryReturnLine.DeducteeResidency.RESIDENT
        return PurchaseStatutoryReturnLine.DeducteeResidency.NON_RESIDENT

    @staticmethod
    def _vendor_tax_id(header: PurchaseInvoiceHeader) -> Optional[str]:
        try:
            vendor = getattr(header, "vendor", None)
            if vendor is None:
                return None
            # Priority for non-resident tax-id style fields.
            for f in ("tdsno", "cin", "adhaarno"):
                val = (getattr(vendor, f, None) or "").strip()
                if val:
                    return val
            pan_val = (account_pan(vendor) or "").strip()
            if pan_val:
                return pan_val
            return None
        except Exception:
            return None

    @staticmethod
    def _vendor_deductee_snapshot(header: PurchaseInvoiceHeader) -> Dict[str, Optional[str]]:
        """
        Immutable deductee values derived from vendor account master.
        """
        country_obj = PurchaseStatutoryService._vendor_country_obj(header)
        return {
            "deductee_residency_snapshot": PurchaseStatutoryService._derive_residency_from_country(country_obj),
            "deductee_country_obj": country_obj,
            "deductee_country_code_snapshot": PurchaseStatutoryService._clean_text(
                getattr(country_obj, "countrycode", None)
            ),
            "deductee_country_name_snapshot": PurchaseStatutoryService._clean_text(
                getattr(country_obj, "countryname", None)
            ),
            "deductee_tax_id_snapshot": PurchaseStatutoryService._vendor_tax_id(header),
            "deductee_pan_snapshot": PurchaseStatutoryService._vendor_pan(header),
            "deductee_gstin_snapshot": (
                PurchaseStatutoryService._clean_text(account_gstno(getattr(header, "vendor", None)))
                or PurchaseStatutoryService._clean_text(getattr(header, "vendor_gstin", None))
            ),
        }

    @staticmethod
    def _policy_controls(entity_id: int, subentity_id: Optional[int]) -> Dict[str, object]:
        try:
            return PurchaseSettingsService.get_policy(entity_id, subentity_id).controls
        except Exception:
            return {}

    @staticmethod
    def _enforcement_level(entity_id: int, subentity_id: Optional[int], key: str, default: str = "off") -> str:
        controls = PurchaseStatutoryService._policy_controls(entity_id, subentity_id)
        val = str(controls.get(key, default)).strip().lower()
        return val if val in {"off", "warn", "hard"} else default

    @staticmethod
    def _switch(entity_id: int, subentity_id: Optional[int], key: str, default: str = "off") -> str:
        controls = PurchaseStatutoryService._policy_controls(entity_id, subentity_id)
        val = str(controls.get(key, default)).strip().lower()
        return val if val in {"off", "on"} else default

    @staticmethod
    def _decimal_control(entity_id: int, subentity_id: Optional[int], key: str, default: Decimal) -> Decimal:
        controls = PurchaseStatutoryService._policy_controls(entity_id, subentity_id)
        raw = controls.get(key, default)
        try:
            return Decimal(str(raw or default))
        except Exception:
            return Decimal(default)

    @staticmethod
    def _append_audit_event(payload: Optional[Dict], event: Dict[str, object]) -> Dict:
        data = dict(payload or {})
        logs = data.get("_audit_log")
        if not isinstance(logs, list):
            logs = []
        logs.append(event)
        data["_audit_log"] = logs
        return data

    @staticmethod
    def _approval_state(payload: Optional[Dict]) -> Dict[str, object]:
        data = dict(payload or {})
        st = data.get("_approval_state")
        if not isinstance(st, dict):
            st = {
                "status": "DRAFT",  # DRAFT | SUBMITTED | APPROVED | REJECTED
                "submitted_by": None,
                "submitted_at": None,
                "approved_by": None,
                "approved_at": None,
                "rejected_by": None,
                "rejected_at": None,
                "remarks": None,
            }
        return st

    @staticmethod
    def _set_approval_state(payload: Optional[Dict], state: Dict[str, object]) -> Dict:
        data = dict(payload or {})
        data["_approval_state"] = state
        return data

    @staticmethod
    def _require_maker_checker(
        *,
        entity_id: int,
        subentity_id: Optional[int],
        maker_user_id: Optional[int],
        checker_user_id: Optional[int],
        action_label: str,
    ) -> None:
        level = PurchaseStatutoryService._enforcement_level(
            entity_id, subentity_id, "statutory_maker_checker", default="off"
        )
        if level != "hard":
            return
        if maker_user_id and checker_user_id and int(maker_user_id) == int(checker_user_id):
            raise ValueError(f"Maker-checker control: {action_label} must be done by a different user.")

    @staticmethod
    def _int_control(
        entity_id: int,
        subentity_id: Optional[int],
        key: str,
        default: int,
        *,
        min_value: int,
        max_value: int,
    ) -> int:
        controls = PurchaseStatutoryService._policy_controls(entity_id, subentity_id)
        raw = controls.get(key, default)
        try:
            value = int(str(raw))
        except Exception:
            value = int(default)
        if value < min_value:
            return min_value
        if value > max_value:
            return max_value
        return value

    @staticmethod
    def _safe_date(year: int, month: int, day: int) -> date:
        safe_day = min(max(int(day), 1), monthrange(year, month)[1])
        return date(year, month, safe_day)

    @staticmethod
    def _next_month_day(dt: date, day: int) -> date:
        if dt.month == 12:
            return PurchaseStatutoryService._safe_date(dt.year + 1, 1, day)
        return PurchaseStatutoryService._safe_date(dt.year, dt.month + 1, day)

    @staticmethod
    def _due_date_for_challan(
        *,
        entity_id: int,
        subentity_id: Optional[int],
        tax_type: str,
        period_to: Optional[date],
        challan_date: Optional[date],
    ) -> date:
        base = period_to or challan_date or timezone.localdate()
        if tax_type == PurchaseStatutoryChallan.TaxType.IT_TDS:
            due_day = PurchaseStatutoryService._int_control(
                entity_id,
                subentity_id,
                "it_tds_challan_due_day",
                7,
                min_value=1,
                max_value=31,
            )
            return PurchaseStatutoryService._next_month_day(base, due_day)
        if tax_type == PurchaseStatutoryChallan.TaxType.GST_TDS:
            due_day = PurchaseStatutoryService._int_control(
                entity_id,
                subentity_id,
                "gst_tds_challan_due_day",
                10,
                min_value=1,
                max_value=31,
            )
            return PurchaseStatutoryService._next_month_day(base, due_day)
        return base

    @staticmethod
    def _due_date_for_return(
        *,
        entity_id: int,
        subentity_id: Optional[int],
        tax_type: str,
        return_code: str,
        period_to: date,
    ) -> date:
        code = (return_code or "").strip().upper()
        if tax_type == PurchaseStatutoryReturn.TaxType.IT_TDS and code in {"26Q", "27Q"}:
            y = int(period_to.year)
            m = int(period_to.month)
            if m in (4, 5, 6):
                due_month = PurchaseStatutoryService._int_control(
                    entity_id, subentity_id, "it_tds_return_q1_due_month", 7, min_value=1, max_value=12
                )
                due_day = PurchaseStatutoryService._int_control(
                    entity_id, subentity_id, "it_tds_return_q1_due_day", 31, min_value=1, max_value=31
                )
                return PurchaseStatutoryService._safe_date(y, due_month, due_day)
            if m in (7, 8, 9):
                due_month = PurchaseStatutoryService._int_control(
                    entity_id, subentity_id, "it_tds_return_q2_due_month", 10, min_value=1, max_value=12
                )
                due_day = PurchaseStatutoryService._int_control(
                    entity_id, subentity_id, "it_tds_return_q2_due_day", 31, min_value=1, max_value=31
                )
                return PurchaseStatutoryService._safe_date(y, due_month, due_day)
            if m in (10, 11, 12):
                due_month = PurchaseStatutoryService._int_control(
                    entity_id, subentity_id, "it_tds_return_q3_due_month", 1, min_value=1, max_value=12
                )
                due_day = PurchaseStatutoryService._int_control(
                    entity_id, subentity_id, "it_tds_return_q3_due_day", 31, min_value=1, max_value=31
                )
                return PurchaseStatutoryService._safe_date(y + 1, due_month, due_day)
            due_month = PurchaseStatutoryService._int_control(
                entity_id, subentity_id, "it_tds_return_q4_due_month", 5, min_value=1, max_value=12
            )
            due_day = PurchaseStatutoryService._int_control(
                entity_id, subentity_id, "it_tds_return_q4_due_day", 31, min_value=1, max_value=31
            )
            return PurchaseStatutoryService._safe_date(y, due_month, due_day)
        if tax_type == PurchaseStatutoryReturn.TaxType.GST_TDS:
            due_day = PurchaseStatutoryService._int_control(
                entity_id,
                subentity_id,
                "gst_tds_return_due_day",
                10,
                min_value=1,
                max_value=31,
            )
            return PurchaseStatutoryService._next_month_day(period_to, due_day)
        return period_to

    @staticmethod
    def _delay_days(actual_on: date, due_on: date) -> int:
        return max((actual_on - due_on).days, 0)

    @staticmethod
    def _auto_compute_statutory_charges(
        *,
        entity_id: int,
        subentity_id: Optional[int],
        tax_type: str,
        base_amount: Decimal,
        due_on: date,
        actual_on: date,
    ) -> Dict[str, Decimal]:
        if PurchaseStatutoryService._switch(
            entity_id, subentity_id, "statutory_auto_compute_interest_late_fee", default="off"
        ) != "on":
            return {"interest_amount": ZERO2, "late_fee_amount": ZERO2, "penalty_amount": ZERO2}

        delay = PurchaseStatutoryService._delay_days(actual_on, due_on)
        if delay <= 0:
            return {"interest_amount": ZERO2, "late_fee_amount": ZERO2, "penalty_amount": ZERO2}

        if tax_type == PurchaseStatutoryChallan.TaxType.IT_TDS:
            monthly_rate = PurchaseStatutoryService._decimal_control(
                entity_id, subentity_id, "it_tds_interest_rate_monthly", Decimal("1.50")
            )
            daily_fee = PurchaseStatutoryService._decimal_control(
                entity_id, subentity_id, "it_tds_late_fee_per_day", Decimal("200.00")
            )
            late_cap = PurchaseStatutoryService._decimal_control(
                entity_id, subentity_id, "it_tds_late_fee_cap_factor", Decimal("1.00")
            )
        else:
            monthly_rate = PurchaseStatutoryService._decimal_control(
                entity_id, subentity_id, "gst_tds_interest_rate_monthly", Decimal("1.50")
            )
            daily_fee = PurchaseStatutoryService._decimal_control(
                entity_id, subentity_id, "gst_tds_late_fee_per_day", Decimal("100.00")
            )
            late_cap = PurchaseStatutoryService._decimal_control(
                entity_id, subentity_id, "gst_tds_late_fee_cap_factor", Decimal("1.00")
            )

        # Simple monthly pro-rata model: monthly_rate% * months(delay/30) * base
        interest = q2((base_amount * monthly_rate * Decimal(delay)) / Decimal("3000"))
        late_fee = q2(daily_fee * Decimal(delay))
        cap_amount = q2(base_amount * late_cap)
        if cap_amount > ZERO2 and late_fee > cap_amount:
            late_fee = cap_amount
        return {"interest_amount": interest, "late_fee_amount": late_fee, "penalty_amount": ZERO2}

    @staticmethod
    def _validate_it_tds_return_code(
        *,
        return_code: str,
        lines: List[PurchaseStatutoryReturnLine],
    ) -> None:
        code = (return_code or "").strip().upper()
        if code not in {"26Q", "27Q"}:
            return
        if not lines:
            raise ValueError(f"{code}: at least one line is required.")
        for ln in lines:
            residency = (ln.deductee_residency_snapshot or "").strip().upper()
            if code == "26Q":
                if residency != PurchaseStatutoryReturnLine.DeducteeResidency.RESIDENT:
                    raise ValueError("26Q allows only RESIDENT deductees.")
                if not (ln.deductee_pan_snapshot or "").strip():
                    raise ValueError("26Q requires PAN for all deductees.")
            if code == "27Q":
                if residency != PurchaseStatutoryReturnLine.DeducteeResidency.NON_RESIDENT:
                    raise ValueError("27Q allows only NON_RESIDENT deductees.")
                if not (ln.deductee_tax_id_snapshot or "").strip():
                    raise ValueError("27Q requires deductee_tax_id_snapshot for all deductees.")

    @staticmethod
    def _validate_revision_lines(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        original_return_id: Optional[int],
        revision_no: int,
        line_rows: List[Dict],
    ) -> None:
        if not original_return_id:
            return
        if int(revision_no or 0) <= 0:
            raise ValueError("revision_no must be > 0 when original_return_id is provided.")

        original = (
            PurchaseStatutoryReturn.objects.prefetch_related("lines")
            .filter(pk=original_return_id)
            .first()
        )
        if not original:
            raise ValueError("original_return_id not found.")
        if int(original.entity_id) != int(entity_id) or int(original.entityfinid_id) != int(entityfinid_id):
            raise ValueError("original_return scope mismatch with entity/entityfinid.")
        if original.subentity_id != subentity_id:
            raise ValueError("original_return subentity mismatch.")
        if int(original.status) not in (
            int(PurchaseStatutoryReturn.Status.FILED),
            int(PurchaseStatutoryReturn.Status.REVISED),
        ):
            raise ValueError("original_return must be FILED/REVISED before creating revision.")

        remap_allowed = PurchaseStatutoryService._switch(
            entity_id, subentity_id, "allow_revised_challan_remap", default="off"
        ) == "on"
        if remap_allowed:
            return
        original_keys = {(int(ln.header_id), int(ln.challan_id or 0)) for ln in original.lines.all()}
        for idx, row in enumerate(line_rows, start=1):
            key = (int(row.get("header_id") or 0), int(row.get("challan_id") or 0))
            if key not in original_keys:
                raise ValueError(
                    f"Line {idx}: challan remap is disabled for revisions. Use same header/challan as original return."
                )

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
    def _assert_unique_original_return(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        tax_type: str,
        return_code: str,
        period_from,
        period_to,
        exclude_filing_id: Optional[int] = None,
    ) -> None:
        """
        Keep exactly one original return per period/scope.
        Revisions are allowed through original_return_id linkage.
        """
        qs = PurchaseStatutoryReturn.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            tax_type=tax_type,
            return_code=(return_code or "").strip(),
            period_from=period_from,
            period_to=period_to,
            original_return__isnull=True,
        ).exclude(status=PurchaseStatutoryReturn.Status.CANCELLED)
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        if exclude_filing_id:
            qs = qs.exclude(pk=exclude_filing_id)
        if qs.exists():
            raise ValueError(
                "An original return already exists for this return_code and period. "
                "Create a revision against that original return."
            )

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
    def update_challan(
        *,
        challan_id: int,
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
    ) -> StatutoryResult:
        line_rows = lines or []
        if not line_rows:
            raise ValueError("At least one line is required.")

        challan = PurchaseStatutoryChallan.objects.select_for_update().get(pk=challan_id)
        if int(challan.status) != int(PurchaseStatutoryChallan.Status.DRAFT):
            raise ValueError("Only draft challan can be edited.")

        challan.entity_id = entity_id
        challan.entityfinid_id = entityfinid_id
        challan.subentity_id = subentity_id
        challan.tax_type = tax_type
        challan.challan_no = (challan_no or "").strip()
        challan.challan_date = challan_date
        challan.period_from = period_from
        challan.period_to = period_to
        challan.bank_ref_no = PurchaseStatutoryService._clean_text(bank_ref_no)
        challan.bsr_code = PurchaseStatutoryService._clean_text(bsr_code)
        challan.cin_no = PurchaseStatutoryService._clean_text(cin_no)
        challan.minor_head_code = PurchaseStatutoryService._clean_text(minor_head_code)
        challan.interest_amount = q2(interest_amount)
        challan.late_fee_amount = q2(late_fee_amount)
        challan.penalty_amount = q2(penalty_amount)
        challan.payment_payload_json = payment_payload_json or {}
        if ack_document is not None:
            challan.ack_document = ack_document
        challan.remarks = PurchaseStatutoryService._clean_text(remarks)

        PurchaseStatutoryChallanLine.objects.filter(challan=challan).delete()

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
        challan.save()
        return StatutoryResult(challan, "Challan draft updated.")

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
        approval_state = PurchaseStatutoryService._approval_state(c.payment_payload_json)
        if PurchaseStatutoryService._enforcement_level(
            int(c.entity_id), c.subentity_id, "statutory_maker_checker", default="off"
        ) == "hard":
            if approval_state.get("status") != "APPROVED":
                raise ValueError("Challan must be approved before deposit when maker-checker is enabled.")
        PurchaseStatutoryService._require_maker_checker(
            entity_id=int(c.entity_id),
            subentity_id=c.subentity_id,
            maker_user_id=c.created_by_id,
            checker_user_id=deposited_by_id,
            action_label="challan deposit",
        )
        if int(c.status) == int(PurchaseStatutoryChallan.Status.CANCELLED):
            raise ValueError("Cancelled challan cannot be deposited.")
        if int(c.status) == int(PurchaseStatutoryChallan.Status.DEPOSITED):
            return StatutoryResult(c, "Already deposited.")

        deposited_date = PurchaseStatutoryService._coerce_date(deposited_on, field_name="deposited_on") or timezone.localdate()
        if c.interest_amount <= ZERO2 and c.late_fee_amount <= ZERO2 and c.penalty_amount <= ZERO2:
            due_on = PurchaseStatutoryService._due_date_for_challan(
                entity_id=int(c.entity_id),
                subentity_id=c.subentity_id,
                tax_type=c.tax_type,
                period_to=c.period_to,
                challan_date=c.challan_date,
            )
            calc = PurchaseStatutoryService._auto_compute_statutory_charges(
                entity_id=int(c.entity_id),
                subentity_id=c.subentity_id,
                tax_type=c.tax_type,
                base_amount=q2(c.amount),
                due_on=due_on,
                actual_on=deposited_date,
            )
            c.interest_amount = q2(calc["interest_amount"])
            c.late_fee_amount = q2(calc["late_fee_amount"])
            c.penalty_amount = q2(calc["penalty_amount"])

        c.status = PurchaseStatutoryChallan.Status.DEPOSITED
        c.deposited_on = deposited_date
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
        c.payment_payload_json = PurchaseStatutoryService._append_audit_event(
            c.payment_payload_json,
            {
                "action": "DEPOSITED",
                "at": timezone.now().isoformat(),
                "by": deposited_by_id,
                "status": int(c.status),
                "interest_amount": str(q2(c.interest_amount)),
                "late_fee_amount": str(q2(c.late_fee_amount)),
                "penalty_amount": str(q2(c.penalty_amount)),
            },
        )
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
                "interest_amount",
                "late_fee_amount",
                "penalty_amount",
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
        if not original_return_id:
            PurchaseStatutoryService._assert_unique_original_return(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                tax_type=tax_type,
                return_code=return_code,
                period_from=period_from,
                period_to=period_to,
            )
        PurchaseStatutoryService._validate_revision_lines(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            original_return_id=original_return_id,
            revision_no=revision_no,
            line_rows=line_rows,
        )
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
            ds = PurchaseStatutoryService._vendor_deductee_snapshot(header)
            if not cin_snapshot and challan is not None:
                cin_snapshot = PurchaseStatutoryService._clean_text(getattr(challan, "cin_no", None))
            PurchaseStatutoryReturnLine.objects.create(
                filing=filing,
                header=header,
                challan_id=challan_id,
                amount=amount,
                section_snapshot_code=section_snapshot_code,
                section_snapshot_desc=section_snapshot_desc,
                deductee_residency_snapshot=ds["deductee_residency_snapshot"],
                deductee_country_snapshot=ds["deductee_country_obj"],
                deductee_country_code_snapshot=ds["deductee_country_code_snapshot"],
                deductee_country_name_snapshot=ds["deductee_country_name_snapshot"],
                deductee_tax_id_snapshot=ds["deductee_tax_id_snapshot"],
                deductee_pan_snapshot=ds["deductee_pan_snapshot"],
                deductee_gstin_snapshot=ds["deductee_gstin_snapshot"],
                cin_snapshot=cin_snapshot,
                metadata_json=metadata_json,
            )
            total = q2(total + amount)

        filing.amount = total
        filing.save(update_fields=["amount", "updated_at"])
        if original_return_id:
            filing.status = PurchaseStatutoryReturn.Status.REVISED
            filing.save(update_fields=["status", "updated_at"])
        return StatutoryResult(filing, "Return draft created.")

    @staticmethod
    @transaction.atomic
    def update_return(
        *,
        filing_id: int,
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
    ) -> StatutoryResult:
        line_rows = lines or []
        if not line_rows:
            raise ValueError("At least one line is required.")
        if not original_return_id:
            PurchaseStatutoryService._assert_unique_original_return(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                tax_type=tax_type,
                return_code=return_code,
                period_from=period_from,
                period_to=period_to,
                exclude_filing_id=filing_id,
            )
        PurchaseStatutoryService._validate_revision_lines(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            original_return_id=original_return_id,
            revision_no=revision_no,
            line_rows=line_rows,
        )

        filing = PurchaseStatutoryReturn.objects.select_for_update().get(pk=filing_id)
        if int(filing.status) != int(PurchaseStatutoryReturn.Status.DRAFT):
            raise ValueError("Only draft return can be edited.")

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

        filing.entity_id = entity_id
        filing.entityfinid_id = entityfinid_id
        filing.subentity_id = subentity_id
        filing.tax_type = tax_type
        filing.return_code = (return_code or "").strip()
        filing.period_from = period_from
        filing.period_to = period_to
        filing.ack_no = PurchaseStatutoryService._clean_text(ack_no)
        filing.arn_no = PurchaseStatutoryService._clean_text(arn_no)
        filing.interest_amount = q2(interest_amount)
        filing.late_fee_amount = q2(late_fee_amount)
        filing.penalty_amount = q2(penalty_amount)
        filing.filed_payload_json = filed_payload_json or {}
        if ack_document is not None:
            filing.ack_document = ack_document
        filing.original_return_id = original_return_id
        filing.revision_no = max(int(revision_no or 0), 0)
        filing.remarks = PurchaseStatutoryService._clean_text(remarks)

        PurchaseStatutoryReturnLine.objects.filter(filing=filing).delete()

        total = ZERO2
        for idx, row in enumerate(line_rows, start=1):
            header_id = row.get("header_id")
            challan_id = row.get("challan_id")
            amount = q2(row.get("amount"))
            section_snapshot_code = PurchaseStatutoryService._clean_text(row.get("section_snapshot_code"))
            section_snapshot_desc = PurchaseStatutoryService._clean_text(row.get("section_snapshot_desc"))
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
            ds = PurchaseStatutoryService._vendor_deductee_snapshot(header)
            if not cin_snapshot and challan is not None:
                cin_snapshot = PurchaseStatutoryService._clean_text(getattr(challan, "cin_no", None))
            PurchaseStatutoryReturnLine.objects.create(
                filing=filing,
                header=header,
                challan_id=challan_id,
                amount=amount,
                section_snapshot_code=section_snapshot_code,
                section_snapshot_desc=section_snapshot_desc,
                deductee_residency_snapshot=ds["deductee_residency_snapshot"],
                deductee_country_snapshot=ds["deductee_country_obj"],
                deductee_country_code_snapshot=ds["deductee_country_code_snapshot"],
                deductee_country_name_snapshot=ds["deductee_country_name_snapshot"],
                deductee_tax_id_snapshot=ds["deductee_tax_id_snapshot"],
                deductee_pan_snapshot=ds["deductee_pan_snapshot"],
                deductee_gstin_snapshot=ds["deductee_gstin_snapshot"],
                cin_snapshot=cin_snapshot,
                metadata_json=metadata_json,
            )
            total = q2(total + amount)

        filing.amount = total
        if original_return_id:
            filing.status = PurchaseStatutoryReturn.Status.REVISED
        filing.save()
        return StatutoryResult(filing, "Return draft updated.")

    @staticmethod
    @transaction.atomic
    def delete_challan(*, challan_id: int) -> str:
        challan = PurchaseStatutoryChallan.objects.select_for_update().get(pk=challan_id)
        if int(challan.status) != int(PurchaseStatutoryChallan.Status.DRAFT):
            raise ValueError("Only draft challan can be deleted.")
        challan.delete()
        return "Challan draft deleted."

    @staticmethod
    @transaction.atomic
    def delete_return(*, filing_id: int) -> str:
        filing = PurchaseStatutoryReturn.objects.select_for_update().get(pk=filing_id)
        if int(filing.status) != int(PurchaseStatutoryReturn.Status.DRAFT):
            raise ValueError("Only draft return can be deleted.")
        filing.delete()
        return "Return draft deleted."

    @staticmethod
    @transaction.atomic
    def cancel_challan(*, challan_id: int, cancelled_by_id: Optional[int], reason: Optional[str] = None) -> StatutoryResult:
        c = PurchaseStatutoryChallan.objects.select_for_update().get(pk=challan_id)
        if int(c.status) == int(PurchaseStatutoryChallan.Status.CANCELLED):
            return StatutoryResult(c, "Already cancelled.")
        linked_active_returns = PurchaseStatutoryReturnLine.objects.filter(
            challan_id=c.id,
        ).exclude(
            filing__status=PurchaseStatutoryReturn.Status.CANCELLED
        ).exists()
        if linked_active_returns:
            raise ValueError("Cannot cancel challan linked to active statutory returns.")
        c.status = PurchaseStatutoryChallan.Status.CANCELLED
        c.remarks = PurchaseStatutoryService._clean_text(reason) or c.remarks
        c.payment_payload_json = PurchaseStatutoryService._append_audit_event(
            c.payment_payload_json,
            {
                "action": "CANCELLED",
                "at": timezone.now().isoformat(),
                "by": cancelled_by_id,
                "status": int(c.status),
                "reason": PurchaseStatutoryService._clean_text(reason),
            },
        )
        c.save(update_fields=["status", "remarks", "payment_payload_json", "updated_at"])
        return StatutoryResult(c, "Challan cancelled.")

    @staticmethod
    @transaction.atomic
    def cancel_return(*, filing_id: int, cancelled_by_id: Optional[int], reason: Optional[str] = None) -> StatutoryResult:
        f = PurchaseStatutoryReturn.objects.select_for_update().get(pk=filing_id)
        if int(f.status) == int(PurchaseStatutoryReturn.Status.CANCELLED):
            return StatutoryResult(f, "Already cancelled.")
        f.status = PurchaseStatutoryReturn.Status.CANCELLED
        f.remarks = PurchaseStatutoryService._clean_text(reason) or f.remarks
        f.filed_payload_json = PurchaseStatutoryService._append_audit_event(
            f.filed_payload_json,
            {
                "action": "CANCELLED",
                "at": timezone.now().isoformat(),
                "by": cancelled_by_id,
                "status": int(f.status),
                "reason": PurchaseStatutoryService._clean_text(reason),
            },
        )
        f.save(update_fields=["status", "remarks", "filed_payload_json", "updated_at"])
        return StatutoryResult(f, "Return cancelled.")

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
        approval_state = PurchaseStatutoryService._approval_state(f.filed_payload_json)
        if PurchaseStatutoryService._enforcement_level(
            int(f.entity_id), f.subentity_id, "statutory_maker_checker", default="off"
        ) == "hard":
            if approval_state.get("status") != "APPROVED":
                raise ValueError("Return must be approved before filing when maker-checker is enabled.")
        PurchaseStatutoryService._require_maker_checker(
            entity_id=int(f.entity_id),
            subentity_id=f.subentity_id,
            maker_user_id=f.created_by_id,
            checker_user_id=filed_by_id,
            action_label="return filing",
        )
        if int(f.status) == int(PurchaseStatutoryReturn.Status.CANCELLED):
            raise ValueError("Cancelled return cannot be filed.")
        if int(f.status) == int(PurchaseStatutoryReturn.Status.FILED):
            return StatutoryResult(f, "Already filed.")

        lines = list(f.lines.all())
        if f.tax_type == PurchaseStatutoryReturn.TaxType.IT_TDS:
            PurchaseStatutoryService._validate_it_tds_return_code(
                return_code=f.return_code,
                lines=lines,
            )

        filing_date = PurchaseStatutoryService._coerce_date(filed_on, field_name="filed_on") or timezone.localdate()
        if f.interest_amount <= ZERO2 and f.late_fee_amount <= ZERO2 and f.penalty_amount <= ZERO2:
            due_on = PurchaseStatutoryService._due_date_for_return(
                entity_id=int(f.entity_id),
                subentity_id=f.subentity_id,
                tax_type=f.tax_type,
                return_code=f.return_code,
                period_to=f.period_to,
            )
            calc = PurchaseStatutoryService._auto_compute_statutory_charges(
                entity_id=int(f.entity_id),
                subentity_id=f.subentity_id,
                tax_type=f.tax_type,
                base_amount=q2(f.amount),
                due_on=due_on,
                actual_on=filing_date,
            )
            f.interest_amount = q2(calc["interest_amount"])
            f.late_fee_amount = q2(calc["late_fee_amount"])
            f.penalty_amount = q2(calc["penalty_amount"])

        f.status = PurchaseStatutoryReturn.Status.FILED
        f.filed_on = filing_date
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
        f.filed_payload_json = PurchaseStatutoryService._append_audit_event(
            f.filed_payload_json,
            {
                "action": "FILED",
                "at": timezone.now().isoformat(),
                "by": filed_by_id,
                "status": int(f.status),
                "return_code": (f.return_code or "").strip(),
                "interest_amount": str(q2(f.interest_amount)),
                "late_fee_amount": str(q2(f.late_fee_amount)),
                "penalty_amount": str(q2(f.penalty_amount)),
            },
        )
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
                "interest_amount",
                "late_fee_amount",
                "penalty_amount",
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
        if subentity_id is not None:
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

    @staticmethod
    def itc_status_register(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        date_from=None,
        date_to=None,
        itc_claim_status: Optional[int] = None,
        gstr2b_match_status: Optional[int] = None,
        include_cancelled: bool = False,
    ) -> Dict[str, object]:
        start_date = PurchaseStatutoryService._coerce_date(date_from, field_name="date_from")
        end_date = PurchaseStatutoryService._coerce_date(date_to, field_name="date_to")
        if start_date and end_date and start_date > end_date:
            raise ValueError("date_from cannot be greater than date_to.")

        qs = PurchaseInvoiceHeader.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        ).select_related("vendor")

        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        if start_date:
            qs = qs.filter(bill_date__gte=start_date)
        if end_date:
            qs = qs.filter(bill_date__lte=end_date)
        if not include_cancelled:
            qs = qs.exclude(status=PurchaseInvoiceHeader.Status.CANCELLED)
        if itc_claim_status is not None:
            qs = qs.filter(itc_claim_status=int(itc_claim_status))
        if gstr2b_match_status is not None:
            qs = qs.filter(gstr2b_match_status=int(gstr2b_match_status))

        qs = qs.order_by("-bill_date", "-id")
        headers = list(qs)
        header_ids = [int(h.id) for h in headers]

        latest_action_by_header: Dict[int, Dict[str, object]] = {}
        if header_ids:
            actions = (
                PurchaseItcAction.objects
                .filter(header_id__in=header_ids)
                .select_related("acted_by")
                .order_by("header_id", "-acted_at", "-id")
            )
            for act in actions:
                hid = int(act.header_id)
                if hid in latest_action_by_header:
                    continue
                user_obj = getattr(act, "acted_by", None)
                user_name = (
                    getattr(user_obj, "username", None)
                    or getattr(user_obj, "email", None)
                    or (str(getattr(user_obj, "id")) if user_obj else None)
                )
                latest_action_by_header[hid] = {
                    "action_type": act.action_type,
                    "acted_at": act.acted_at,
                    "acted_by": user_name,
                    "reason": act.reason,
                }

        rows: List[Dict[str, object]] = []
        total_eligible_tax = ZERO2
        total_ineligible_tax = ZERO2

        status_counter: Dict[str, int] = {
            "pending": 0,
            "claimed": 0,
            "blocked": 0,
            "reversed": 0,
            "na": 0,
        }
        match_counter: Dict[str, int] = {
            "matched": 0,
            "partial": 0,
            "mismatched": 0,
            "not_in_2b": 0,
            "not_checked": 0,
            "na": 0,
        }

        for h in headers:
            action = latest_action_by_header.get(int(h.id)) or {}
            eligible_tax = q2(getattr(h, "total_gst", ZERO2)) if bool(getattr(h, "is_itc_eligible", False)) else ZERO2
            ineligible_tax = ZERO2 if bool(getattr(h, "is_itc_eligible", False)) else q2(getattr(h, "total_gst", ZERO2))
            total_eligible_tax = q2(total_eligible_tax + eligible_tax)
            total_ineligible_tax = q2(total_ineligible_tax + ineligible_tax)

            itc_key = (
                str(getattr(h, "get_itc_claim_status_display", lambda: "NA")())
                .strip()
                .lower()
                .replace(" ", "_")
            )
            if "pending" in itc_key:
                status_counter["pending"] += 1
            elif "claimed" in itc_key:
                status_counter["claimed"] += 1
            elif "blocked" in itc_key:
                status_counter["blocked"] += 1
            elif "reversed" in itc_key:
                status_counter["reversed"] += 1
            else:
                status_counter["na"] += 1

            match_key = int(getattr(h, "gstr2b_match_status", PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_CHECKED))
            if match_key == int(PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED):
                match_counter["matched"] += 1
            elif match_key == int(PurchaseInvoiceHeader.Gstr2bMatchStatus.PARTIAL):
                match_counter["partial"] += 1
            elif match_key == int(PurchaseInvoiceHeader.Gstr2bMatchStatus.MISMATCHED):
                match_counter["mismatched"] += 1
            elif match_key == int(PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_IN_2B):
                match_counter["not_in_2b"] += 1
            elif match_key == int(PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_CHECKED):
                match_counter["not_checked"] += 1
            else:
                match_counter["na"] += 1

            rows.append(
                {
                    "header_id": int(h.id),
                    "purchase_number": h.purchase_number or f"{h.doc_code}-{h.doc_no}",
                    "bill_date": h.bill_date,
                    "vendor_name": h.vendor_name or "",
                    "vendor_gstin": h.vendor_gstin or "",
                    "doc_type": int(h.doc_type or 0),
                    "doc_type_name": h.get_doc_type_display(),
                    "status": int(h.status or 0),
                    "status_name": h.get_status_display(),
                    "is_itc_eligible": bool(h.is_itc_eligible),
                    "itc_claim_status": int(h.itc_claim_status or 0),
                    "itc_claim_status_name": h.get_itc_claim_status_display(),
                    "itc_claim_period": h.itc_claim_period,
                    "itc_claimed_at": h.itc_claimed_at,
                    "itc_block_reason": h.itc_block_reason or "",
                    "gstr2b_match_status": int(h.gstr2b_match_status or 0),
                    "gstr2b_match_status_name": h.get_gstr2b_match_status_display(),
                    "total_taxable": str(q2(getattr(h, "total_taxable", ZERO2))),
                    "total_gst": str(q2(getattr(h, "total_gst", ZERO2))),
                    "itc_eligible_tax": str(eligible_tax),
                    "itc_ineligible_tax": str(ineligible_tax),
                    "last_itc_action": action.get("action_type"),
                    "last_itc_action_at": action.get("acted_at"),
                    "last_itc_action_by": action.get("acted_by"),
                    "last_itc_action_reason": action.get("reason"),
                }
            )

        return {
            "count": len(rows),
            "rows": rows,
            "summary": {
                "invoice_count": len(rows),
                "total_eligible_tax": str(total_eligible_tax),
                "total_ineligible_tax": str(total_ineligible_tax),
                "itc_status_counts": status_counter,
                "gstr2b_status_counts": match_counter,
            },
        }

    @staticmethod
    def challan_eligible_lines(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        tax_type: str,
        period_from,
        period_to,
    ) -> Dict[str, object]:
        if tax_type not in (PurchaseStatutoryChallan.TaxType.IT_TDS, PurchaseStatutoryChallan.TaxType.GST_TDS):
            raise ValueError("tax_type must be IT_TDS or GST_TDS.")
        if period_from is None or period_to is None:
            raise ValueError("period_from and period_to are required.")
        if period_from > period_to:
            raise ValueError("period_from cannot be greater than period_to.")

        headers = PurchaseInvoiceHeader.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            bill_date__gte=period_from,
            bill_date__lte=period_to,
            status=PurchaseInvoiceHeader.Status.POSTED,
        ).select_related("tds_section")
        if subentity_id is not None:
            headers = headers.filter(subentity_id=subentity_id)

        mapped_rows = (
            PurchaseStatutoryChallanLine.objects
            .filter(
                challan__entity_id=entity_id,
                challan__entityfinid_id=entityfinid_id,
                challan__tax_type=tax_type,
            )
            .exclude(challan__status=PurchaseStatutoryChallan.Status.CANCELLED)
            .values("header_id")
            .annotate(total=Sum("amount"))
        )
        if subentity_id is not None:
            mapped_rows = mapped_rows.filter(challan__subentity_id=subentity_id)
        mapped_by_header = {int(r["header_id"]): q2(r["total"]) for r in mapped_rows}

        lines: List[Dict[str, object]] = []
        total_amount = ZERO2
        section_totals: Dict[str, Decimal] = {}
        for h in headers:
            if tax_type == PurchaseStatutoryChallan.TaxType.IT_TDS:
                base_amount = q2(getattr(h, "tds_amount", ZERO2))
                source = "tds_amount"
                section_obj = getattr(h, "tds_section", None)
                section_id = getattr(section_obj, "id", None)
                section_code = (getattr(section_obj, "section_code", None) or "")
                section_desc = (getattr(section_obj, "description", None) or "")
            else:
                base_amount = q2(getattr(h, "gst_tds_amount", ZERO2))
                source = "gst_tds_amount"
                section_id = None
                section_code = ""
                section_desc = ""

            if base_amount <= ZERO2:
                continue

            used_amount = q2(mapped_by_header.get(int(h.id), ZERO2))
            eligible = q2(base_amount - used_amount)
            if eligible <= ZERO2:
                continue

            lines.append(
                {
                    "header_id": int(h.id),
                    "purchase_number": h.purchase_number or f"{h.doc_code}-{h.doc_no}",
                    "bill_date": h.bill_date,
                    "vendor_name": h.vendor_name or "",
                    "section_id": section_id,
                    "section_code": section_code,
                    "section_desc": section_desc,
                    "amount": str(eligible),
                    "tax_type": tax_type,
                    "source": source,
                }
            )
            total_amount = q2(total_amount + eligible)
            section_key = section_code or "UNSPECIFIED"
            section_totals[section_key] = q2(section_totals.get(section_key, ZERO2) + eligible)

        return {
            "lines": lines,
            "prefill_lines": [
                {
                    "header_id": int(row["header_id"]),
                    "section_id": row.get("section_id"),
                    "amount": row["amount"],
                }
                for row in lines
            ],
            "totals": {
                "line_count": len(lines),
                "amount": str(total_amount),
            },
            "section_totals": [
                {"section_code": code, "amount": str(amount)}
                for code, amount in sorted(section_totals.items(), key=lambda item: item[0])
            ],
        }

    @staticmethod
    def return_eligible_lines(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        tax_type: str,
        period_from,
        period_to,
    ) -> Dict[str, object]:
        if tax_type not in (PurchaseStatutoryReturn.TaxType.IT_TDS, PurchaseStatutoryReturn.TaxType.GST_TDS):
            raise ValueError("tax_type must be IT_TDS or GST_TDS.")
        if period_from is None or period_to is None:
            raise ValueError("period_from and period_to are required.")
        if period_from > period_to:
            raise ValueError("period_from cannot be greater than period_to.")

        challan_lines_qs = (
            PurchaseStatutoryChallanLine.objects
            .select_related("challan", "header", "header__tds_section")
            .filter(
                challan__entity_id=entity_id,
                challan__entityfinid_id=entityfinid_id,
                challan__tax_type=tax_type,
                challan__status=PurchaseStatutoryChallan.Status.DEPOSITED,
                challan__challan_date__gte=period_from,
                challan__challan_date__lte=period_to,
            )
        )
        if subentity_id is not None:
            challan_lines_qs = challan_lines_qs.filter(challan__subentity_id=subentity_id)

        consumed_rows = (
            PurchaseStatutoryReturnLine.objects
            .filter(
                filing__entity_id=entity_id,
                filing__entityfinid_id=entityfinid_id,
                filing__tax_type=tax_type,
                challan_id__isnull=False,
            )
            .exclude(filing__status=PurchaseStatutoryReturn.Status.CANCELLED)
            .values("header_id", "challan_id")
            .annotate(total=Sum("amount"))
        )
        if subentity_id is not None:
            consumed_rows = consumed_rows.filter(filing__subentity_id=subentity_id)
        consumed_map = {
            (int(r["header_id"]), int(r["challan_id"])): q2(r["total"])
            for r in consumed_rows
        }

        lines: List[Dict[str, object]] = []
        total_amount = ZERO2
        section_totals: Dict[str, Decimal] = {}
        for cl in challan_lines_qs:
            key = (int(cl.header_id), int(cl.challan_id))
            used = q2(consumed_map.get(key, ZERO2))
            eligible = q2(q2(cl.amount) - used)
            if eligible <= ZERO2:
                continue

            h = cl.header
            section_obj = getattr(h, "tds_section", None)
            section_code = (getattr(section_obj, "section_code", None) or "")
            section_desc = (getattr(section_obj, "description", None) or "")
            ds = PurchaseStatutoryService._vendor_deductee_snapshot(h)

            lines.append(
                {
                    "header_id": int(cl.header_id),
                    "challan_id": int(cl.challan_id),
                    "challan_no": cl.challan.challan_no or "",
                    "amount": str(eligible),
                    "section_snapshot_code": section_code,
                    "section_snapshot_desc": section_desc,
                    "deductee_residency_snapshot": ds["deductee_residency_snapshot"],
                    "deductee_country_snapshot": getattr(ds["deductee_country_obj"], "id", None),
                    "deductee_country_code_snapshot": ds["deductee_country_code_snapshot"] or "",
                    "deductee_country_name_snapshot": ds["deductee_country_name_snapshot"] or "",
                    "deductee_tax_id_snapshot": ds["deductee_tax_id_snapshot"] or "",
                    "deductee_pan_snapshot": ds["deductee_pan_snapshot"] or "",
                    "deductee_gstin_snapshot": ds["deductee_gstin_snapshot"] or "",
                    "cin_snapshot": PurchaseStatutoryService._clean_text(getattr(cl.challan, "cin_no", None)) or "",
                    "metadata_json": {},
                }
            )
            total_amount = q2(total_amount + eligible)
            section_key = section_code or "UNSPECIFIED"
            section_totals[section_key] = q2(section_totals.get(section_key, ZERO2) + eligible)

        return {
            "lines": lines,
            "prefill_lines": [
                {
                    "header_id": int(row["header_id"]),
                    "challan_id": row.get("challan_id"),
                    "amount": row["amount"],
                    "section_snapshot_code": row.get("section_snapshot_code") or "",
                    "section_snapshot_desc": row.get("section_snapshot_desc") or "",
                    "deductee_residency_snapshot": row.get("deductee_residency_snapshot"),
                    "deductee_country_snapshot": row.get("deductee_country_snapshot"),
                    "deductee_country_code_snapshot": row.get("deductee_country_code_snapshot") or "",
                    "deductee_country_name_snapshot": row.get("deductee_country_name_snapshot") or "",
                    "deductee_tax_id_snapshot": row.get("deductee_tax_id_snapshot") or "",
                    "deductee_pan_snapshot": row.get("deductee_pan_snapshot") or "",
                    "deductee_gstin_snapshot": row.get("deductee_gstin_snapshot") or "",
                    "cin_snapshot": row.get("cin_snapshot") or "",
                    "metadata_json": row.get("metadata_json") or {},
                }
                for row in lines
            ],
            "totals": {
                "line_count": len(lines),
                "amount": str(total_amount),
            },
            "section_totals": [
                {"section_code": code, "amount": str(amount)}
                for code, amount in sorted(section_totals.items(), key=lambda item: item[0])
            ],
        }

    @staticmethod
    def reconciliation_exceptions(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        tax_type: str,
        period_from,
        period_to,
    ) -> Dict[str, object]:
        challan_data = PurchaseStatutoryService.challan_eligible_lines(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            tax_type=tax_type,
            period_from=period_from,
            period_to=period_to,
        )
        return_data = PurchaseStatutoryService.return_eligible_lines(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            tax_type=tax_type,
            period_from=period_from,
            period_to=period_to,
        )
        filed_returns = PurchaseStatutoryReturn.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            tax_type=tax_type,
            status=PurchaseStatutoryReturn.Status.FILED,
        )
        if subentity_id is not None:
            filed_returns = filed_returns.filter(subentity_id=subentity_id)
        filed_returns = filed_returns.filter(period_to__gte=period_from, period_from__lte=period_to)

        missing_ack = list(
            filed_returns.filter(Q(ack_no__isnull=True) | Q(ack_no="") | Q(arn_no__isnull=True) | Q(arn_no=""))
            .values("id", "return_code", "period_from", "period_to", "ack_no", "arn_no")
        )

        return {
            "exceptions": {
                "invoices_pending_challan_mapping": challan_data["totals"],
                "challan_lines_pending_return_mapping": return_data["totals"],
                "filed_returns_missing_ack_or_arn": {
                    "count": len(missing_ack),
                    "rows": missing_ack,
                },
            }
        }

    @staticmethod
    def generate_nsdl_payload(*, filing_id: int) -> Dict[str, object]:
        filing = (
            PurchaseStatutoryReturn.objects
            .prefetch_related("lines__header", "lines__challan")
            .get(pk=filing_id)
        )
        lines = list(filing.lines.all())
        total_amt = q2(sum((q2(ln.amount) for ln in lines), ZERO2))
        code = (filing.return_code or "").strip().upper()
        residency_mode = "MIXED"
        if code == "26Q":
            residency_mode = "RESIDENT_ONLY"
        elif code == "27Q":
            residency_mode = "NON_RESIDENT_ONLY"

        txt_rows: List[str] = []
        txt_rows.append(
            f"HDR|{filing.id}|{filing.tax_type}|{code}|{filing.period_from}|{filing.period_to}|{len(lines)}|{total_amt}"
        )
        for i, ln in enumerate(lines, start=1):
            txt_rows.append(
                "|".join(
                    [
                        "DTL",
                        str(i),
                        str(ln.header_id),
                        (ln.deductee_pan_snapshot or ""),
                        (ln.deductee_tax_id_snapshot or ""),
                        (ln.deductee_residency_snapshot or ""),
                        str(q2(ln.amount)),
                        (ln.section_snapshot_code or ""),
                        (ln.cin_snapshot or ""),
                    ]
                )
            )
        txt_rows.append(f"TRL|{len(lines)}|{total_amt}")
        return {
            "filing_id": filing.id,
            "tax_type": filing.tax_type,
            "return_code": code,
            "period_from": filing.period_from,
            "period_to": filing.period_to,
            "line_count": len(lines),
            "amount": str(total_amt),
            "residency_mode": residency_mode,
            "nsdl_txt": "\n".join(txt_rows),
            "note": "NSDL/FVU pre-format payload. Validate and convert via your filing utility pipeline.",
        }

    @staticmethod
    @transaction.atomic
    def issue_form16a(*, filing_id: int, issued_by_id: Optional[int], issue_date=None, remarks: Optional[str] = None) -> Dict[str, object]:
        filing = PurchaseStatutoryReturn.objects.select_for_update().prefetch_related("lines").get(pk=filing_id)
        if not PurchaseStatutoryService._is_form16a_eligible_return(filing):
            raise ValueError("Form16A is allowed only for IT_TDS returns 26Q/27Q in FILED/REVISED status.")

        payload = dict(filing.filed_payload_json or {})
        issues = payload.get("form16a_issues")
        if not isinstance(issues, list):
            issues = []
        issue_no = len(issues) + 1
        issue_dt = PurchaseStatutoryService._coerce_date(issue_date, field_name="issue_date") or timezone.localdate()
        issue_code = f"F16A-{filing.id}-{issue_no:03d}"
        issue_row = {
            "issue_no": issue_no,
            "issue_code": issue_code,
            "issued_on": str(issue_dt),
            "issued_by": issued_by_id,
            "line_count": int(filing.lines.count()),
            "official_document_uploaded": False,
            "remarks": PurchaseStatutoryService._clean_text(remarks),
        }
        issues.append(issue_row)
        payload["form16a_issues"] = issues
        payload = PurchaseStatutoryService._append_audit_event(
            payload,
            {
                "action": "FORM16A_ISSUED",
                "at": timezone.now().isoformat(),
                "by": issued_by_id,
                "issue_code": issue_code,
            },
        )
        filing.filed_payload_json = payload
        filing.save(update_fields=["filed_payload_json", "updated_at"])
        return {"filing_id": filing.id, "issue": issue_row}

    @staticmethod
    @transaction.atomic
    def attach_form16a_official_document(
        *,
        filing_id: int,
        issue_no: int,
        document,
        uploaded_by_id: Optional[int],
        source: Optional[str] = "TRACES",
        certificate_no: Optional[str] = None,
        remarks: Optional[str] = None,
    ) -> Dict[str, object]:
        filing = PurchaseStatutoryReturn.objects.select_for_update().get(pk=filing_id)
        if not PurchaseStatutoryService._is_form16a_eligible_return(filing):
            raise ValueError("Official Form16A upload is allowed only for IT_TDS returns 26Q/27Q in FILED/REVISED status.")

        payload = dict(filing.filed_payload_json or {})
        issues = payload.get("form16a_issues")
        if not isinstance(issues, list):
            issues = []
        issue = next((i for i in issues if int(i.get("issue_no") or 0) == int(issue_no)), None)
        if not issue:
            raise ValueError("Issue number not found for this return.")

        doc_obj, _ = PurchaseStatutoryForm16AOfficialDocument.objects.update_or_create(
            filing_id=filing_id,
            issue_no=issue_no,
            defaults={
                "document": document,
                "source": (source or "TRACES").strip() or "TRACES",
                "certificate_no": PurchaseStatutoryService._clean_text(certificate_no),
                "remarks": PurchaseStatutoryService._clean_text(remarks),
                "uploaded_by_id": uploaded_by_id,
                "uploaded_at": timezone.now(),
            },
        )
        issue["official_document_uploaded"] = True
        issue["official_document_source"] = doc_obj.source
        issue["official_document_uploaded_at"] = doc_obj.uploaded_at.isoformat()
        issue["official_document_id"] = doc_obj.id
        payload["form16a_issues"] = issues
        filing.filed_payload_json = payload
        filing.save(update_fields=["filed_payload_json", "updated_at"])
        return {
            "filing_id": filing_id,
            "issue_no": issue_no,
            "official_document_id": doc_obj.id,
            "source": doc_obj.source,
        }

    @staticmethod
    def list_form16a_issues(*, filing_id: int) -> Dict[str, object]:
        filing = PurchaseStatutoryReturn.objects.get(pk=filing_id)
        if not PurchaseStatutoryService._is_form16a_eligible_return(filing):
            raise ValueError("Form16A list is available only for IT_TDS returns 26Q/27Q in FILED/REVISED status.")
        payload = dict(filing.filed_payload_json or {})
        issues = payload.get("form16a_issues")
        if not isinstance(issues, list):
            issues = []
        official_docs = {
            int(d.issue_no): d
            for d in PurchaseStatutoryForm16AOfficialDocument.objects.filter(filing_id=filing_id)
        }
        enriched = []
        for issue in issues:
            row = dict(issue)
            no = int(row.get("issue_no") or 0)
            doc = official_docs.get(no)
            row["official_document_uploaded"] = bool(doc)
            if doc:
                row["official_document_source"] = doc.source
                row["official_document_id"] = doc.id
                row["official_document_uploaded_at"] = doc.uploaded_at.isoformat() if doc.uploaded_at else None
            enriched.append(row)
        return {"filing_id": filing.id, "issues": enriched}

    @staticmethod
    @transaction.atomic
    def submit_challan_for_approval(*, challan_id: int, user_id: Optional[int], remarks: Optional[str] = None) -> StatutoryResult:
        c = PurchaseStatutoryChallan.objects.select_for_update().get(pk=challan_id)
        if int(c.status) != int(PurchaseStatutoryChallan.Status.DRAFT):
            raise ValueError("Only draft challan can be submitted.")
        st = PurchaseStatutoryService._approval_state(c.payment_payload_json)
        st.update(
            {
                "status": "SUBMITTED",
                "submitted_by": user_id,
                "submitted_at": timezone.now().isoformat(),
                "remarks": PurchaseStatutoryService._clean_text(remarks),
            }
        )
        c.payment_payload_json = PurchaseStatutoryService._set_approval_state(c.payment_payload_json, st)
        c.payment_payload_json = PurchaseStatutoryService._append_audit_event(
            c.payment_payload_json,
            {"action": "SUBMITTED_FOR_APPROVAL", "at": timezone.now().isoformat(), "by": user_id, "remarks": st.get("remarks")},
        )
        c.save(update_fields=["payment_payload_json", "updated_at"])
        return StatutoryResult(c, "Challan submitted for approval.")

    @staticmethod
    @transaction.atomic
    def approve_challan(*, challan_id: int, user_id: Optional[int], remarks: Optional[str] = None) -> StatutoryResult:
        c = PurchaseStatutoryChallan.objects.select_for_update().get(pk=challan_id)
        if int(c.status) != int(PurchaseStatutoryChallan.Status.DRAFT):
            raise ValueError("Only draft challan can be approved.")
        st = PurchaseStatutoryService._approval_state(c.payment_payload_json)
        if st.get("submitted_by") and user_id and int(st.get("submitted_by")) == int(user_id):
            raise ValueError("Approver must be different from submitter.")
        st.update(
            {
                "status": "APPROVED",
                "approved_by": user_id,
                "approved_at": timezone.now().isoformat(),
                "remarks": PurchaseStatutoryService._clean_text(remarks),
            }
        )
        c.payment_payload_json = PurchaseStatutoryService._set_approval_state(c.payment_payload_json, st)
        c.payment_payload_json = PurchaseStatutoryService._append_audit_event(
            c.payment_payload_json,
            {"action": "APPROVED", "at": timezone.now().isoformat(), "by": user_id, "remarks": st.get("remarks")},
        )
        c.save(update_fields=["payment_payload_json", "updated_at"])
        return StatutoryResult(c, "Challan approved.")

    @staticmethod
    @transaction.atomic
    def reject_challan(*, challan_id: int, user_id: Optional[int], remarks: Optional[str] = None) -> StatutoryResult:
        c = PurchaseStatutoryChallan.objects.select_for_update().get(pk=challan_id)
        if int(c.status) != int(PurchaseStatutoryChallan.Status.DRAFT):
            raise ValueError("Only draft challan can be rejected.")
        st = PurchaseStatutoryService._approval_state(c.payment_payload_json)
        st.update(
            {
                "status": "REJECTED",
                "rejected_by": user_id,
                "rejected_at": timezone.now().isoformat(),
                "remarks": PurchaseStatutoryService._clean_text(remarks),
            }
        )
        c.payment_payload_json = PurchaseStatutoryService._set_approval_state(c.payment_payload_json, st)
        c.payment_payload_json = PurchaseStatutoryService._append_audit_event(
            c.payment_payload_json,
            {"action": "REJECTED", "at": timezone.now().isoformat(), "by": user_id, "remarks": st.get("remarks")},
        )
        c.save(update_fields=["payment_payload_json", "updated_at"])
        return StatutoryResult(c, "Challan rejected.")

    @staticmethod
    @transaction.atomic
    def submit_return_for_approval(*, filing_id: int, user_id: Optional[int], remarks: Optional[str] = None) -> StatutoryResult:
        f = PurchaseStatutoryReturn.objects.select_for_update().get(pk=filing_id)
        if int(f.status) not in (
            int(PurchaseStatutoryReturn.Status.DRAFT),
            int(PurchaseStatutoryReturn.Status.REVISED),
        ):
            raise ValueError("Only draft/revised return can be submitted.")
        st = PurchaseStatutoryService._approval_state(f.filed_payload_json)
        st.update(
            {
                "status": "SUBMITTED",
                "submitted_by": user_id,
                "submitted_at": timezone.now().isoformat(),
                "remarks": PurchaseStatutoryService._clean_text(remarks),
            }
        )
        f.filed_payload_json = PurchaseStatutoryService._set_approval_state(f.filed_payload_json, st)
        f.filed_payload_json = PurchaseStatutoryService._append_audit_event(
            f.filed_payload_json,
            {"action": "SUBMITTED_FOR_APPROVAL", "at": timezone.now().isoformat(), "by": user_id, "remarks": st.get("remarks")},
        )
        f.save(update_fields=["filed_payload_json", "updated_at"])
        return StatutoryResult(f, "Return submitted for approval.")

    @staticmethod
    @transaction.atomic
    def approve_return(*, filing_id: int, user_id: Optional[int], remarks: Optional[str] = None) -> StatutoryResult:
        f = PurchaseStatutoryReturn.objects.select_for_update().get(pk=filing_id)
        if int(f.status) not in (
            int(PurchaseStatutoryReturn.Status.DRAFT),
            int(PurchaseStatutoryReturn.Status.REVISED),
        ):
            raise ValueError("Only draft/revised return can be approved.")
        st = PurchaseStatutoryService._approval_state(f.filed_payload_json)
        if st.get("submitted_by") and user_id and int(st.get("submitted_by")) == int(user_id):
            raise ValueError("Approver must be different from submitter.")
        st.update(
            {
                "status": "APPROVED",
                "approved_by": user_id,
                "approved_at": timezone.now().isoformat(),
                "remarks": PurchaseStatutoryService._clean_text(remarks),
            }
        )
        f.filed_payload_json = PurchaseStatutoryService._set_approval_state(f.filed_payload_json, st)
        f.filed_payload_json = PurchaseStatutoryService._append_audit_event(
            f.filed_payload_json,
            {"action": "APPROVED", "at": timezone.now().isoformat(), "by": user_id, "remarks": st.get("remarks")},
        )
        f.save(update_fields=["filed_payload_json", "updated_at"])
        return StatutoryResult(f, "Return approved.")

    @staticmethod
    @transaction.atomic
    def reject_return(*, filing_id: int, user_id: Optional[int], remarks: Optional[str] = None) -> StatutoryResult:
        f = PurchaseStatutoryReturn.objects.select_for_update().get(pk=filing_id)
        if int(f.status) not in (
            int(PurchaseStatutoryReturn.Status.DRAFT),
            int(PurchaseStatutoryReturn.Status.REVISED),
        ):
            raise ValueError("Only draft/revised return can be rejected.")
        st = PurchaseStatutoryService._approval_state(f.filed_payload_json)
        st.update(
            {
                "status": "REJECTED",
                "rejected_by": user_id,
                "rejected_at": timezone.now().isoformat(),
                "remarks": PurchaseStatutoryService._clean_text(remarks),
            }
        )
        f.filed_payload_json = PurchaseStatutoryService._set_approval_state(f.filed_payload_json, st)
        f.filed_payload_json = PurchaseStatutoryService._append_audit_event(
            f.filed_payload_json,
            {"action": "REJECTED", "at": timezone.now().isoformat(), "by": user_id, "remarks": st.get("remarks")},
        )
        f.save(update_fields=["filed_payload_json", "updated_at"])
        return StatutoryResult(f, "Return rejected.")

    @staticmethod
    def form16a_download_payload(*, filing_id: int, issue_no: int) -> Dict[str, object]:
        filing = PurchaseStatutoryReturn.objects.get(pk=filing_id)
        if not PurchaseStatutoryService._is_form16a_eligible_return(filing):
            raise ValueError("Form16A download is available only for IT_TDS returns 26Q/27Q in FILED/REVISED status.")
        payload = dict(filing.filed_payload_json or {})
        issues = payload.get("form16a_issues")
        if not isinstance(issues, list):
            issues = []
        issue = next((i for i in issues if int(i.get("issue_no") or 0) == int(issue_no)), None)
        if not issue:
            raise ValueError("Requested Form16A issue version not found.")
        certificate_data = PurchaseStatutoryService._form16a_certificate_data(filing=filing, issue=issue)
        official_doc = PurchaseStatutoryForm16AOfficialDocument.objects.filter(
            filing_id=filing_id, issue_no=issue_no
        ).first()
        if official_doc and official_doc.document:
            return {
                "mode": "file",
                "file_field": official_doc.document,
                "filename": official_doc.document.name.split("/")[-1] or f"form16a_{filing_id}_{issue_no}.pdf",
                "certificate_data": certificate_data,
            }
        return {
            "mode": "text",
            "filename": f"form16a_{filing_id}_{issue_no}.txt",
            "certificate_data": certificate_data,
            "content": (
                f"Form16A\n"
                f"Return ID: {filing.id}\n"
                f"Return Code: {filing.return_code}\n"
                f"Period: {filing.period_from} to {filing.period_to}\n"
                f"Issue No: {issue.get('issue_no')}\n"
                f"Issue Code: {issue.get('issue_code')}\n"
                f"Issued On: {issue.get('issued_on')}\n"
                f"Line Count: {issue.get('line_count')}\n"
            ),
        }

    @staticmethod
    def reconciliation_gl_status(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        period_from,
        period_to,
    ) -> Dict[str, object]:
        try:
            from posting.models import Entry, TxnType
        except Exception:
            return {
                "gl_reconciliation": {
                    "enabled": False,
                    "detail": "Posting app not available.",
                }
            }

        invoice_qs = PurchaseInvoiceHeader.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            bill_date__gte=period_from,
            bill_date__lte=period_to,
            status=PurchaseInvoiceHeader.Status.POSTED,
        )
        if subentity_id is not None:
            invoice_qs = invoice_qs.filter(subentity_id=subentity_id)
        posted_ids = list(invoice_qs.values_list("id", flat=True))
        if not posted_ids:
            return {"gl_reconciliation": {"enabled": True, "invoice_count": 0, "missing_gl_entries": []}}

        entry_qs = Entry.objects.filter(
            entity_id=entity_id,
            entityfin_id=entityfinid_id,
            txn_type__in=[TxnType.PURCHASE, TxnType.PURCHASE_CREDIT_NOTE, TxnType.PURCHASE_DEBIT_NOTE],
            txn_id__in=posted_ids,
        )
        if subentity_id is not None:
            entry_qs = entry_qs.filter(subentity_id=subentity_id)
        entry_ids = set(entry_qs.values_list("txn_id", flat=True))
        missing = list(invoice_qs.exclude(id__in=entry_ids).values("id", "purchase_number", "bill_date", "grand_total"))
        return {
            "gl_reconciliation": {
                "enabled": True,
                "invoice_count": len(posted_ids),
                "entry_count": int(entry_qs.count()),
                "missing_gl_entry_count": len(missing),
                "missing_gl_entries": missing,
            }
        }
