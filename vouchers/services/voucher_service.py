from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from django.db import transaction
from django.utils import timezone

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from posting.adapters.voucher import VoucherPostingAdapter
from vouchers.models.voucher_core import VoucherHeader, VoucherLine
from vouchers.services.voucher_settings_service import VoucherSettingsService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(x) -> Decimal:
    return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)


def _default_doc_code(voucher_type: str, entity_id: int, subentity_id: Optional[int]) -> str:
    settings = VoucherSettingsService.get_settings(entity_id, subentity_id)
    return VoucherSettingsService.default_doc_code_for_type(settings, voucher_type)


@dataclass(frozen=True)
class VoucherResult:
    header: VoucherHeader
    message: str


class VoucherService:
    @staticmethod
    def _account_ledger_id(account_obj_or_id) -> Optional[int]:
        if account_obj_or_id in (None, "", 0):
            return None
        if hasattr(account_obj_or_id, "ledger_id"):
            ledger_id = getattr(account_obj_or_id, "ledger_id", None)
            return int(ledger_id) if ledger_id else None
        from financial.models import account as Account

        row = Account.objects.filter(pk=account_obj_or_id).values_list("ledger_id", flat=True).first()
        return int(row) if row else None

    @staticmethod
    def _workflow_state(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        data = dict(payload or {})
        st = data.get("_approval_state")
        if not isinstance(st, dict):
            st = {
                "status": "DRAFT",
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
    def _set_workflow_state(payload: Optional[Dict[str, Any]], state: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(payload or {})
        data["_approval_state"] = state
        return data

    @staticmethod
    def _append_audit(payload: Optional[Dict[str, Any]], event: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(payload or {})
        logs = data.get("_audit_log")
        if not isinstance(logs, list):
            logs = []
        logs.append(event)
        data["_audit_log"] = logs
        return data

    @staticmethod
    def _doc_type_id(voucher_type: str, doc_code: str) -> int:
        doc_key = VoucherSettingsService.DOC_KEY_BY_TYPE[voucher_type]
        row = DocumentType.objects.filter(module="vouchers", doc_key=doc_key, default_code=doc_code, is_active=True).first()
        if not row:
            row = DocumentType.objects.filter(module="vouchers", doc_key=doc_key, is_active=True).first()
        if not row:
            raise ValueError(f"DocumentType not found for vouchers/{doc_key}.")
        return int(row.id)

    @staticmethod
    def _normalize_journal_lines(rows_in: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows_in or [], start=1):
            item = dict(row or {})
            item["line_no"] = int(item.get("line_no") or idx)
            item["account"] = getattr(item.get("account"), "pk", item.get("account"))
            item["dr_amount"] = q2(item.get("dr_amount") or ZERO2)
            item["cr_amount"] = q2(item.get("cr_amount") or ZERO2)
            rows.append(item)
        return rows

    @staticmethod
    def _normalize_cash_bank_lines(rows_in: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows_in or [], start=1):
            item = dict(row or {})
            item["line_no"] = int(item.get("line_no") or idx)
            item["account"] = getattr(item.get("account"), "pk", item.get("account"))
            item["entry_type"] = str(item.get("entry_type") or "").upper().strip()
            item["amount"] = q2(item.get("amount") or ZERO2)
            rows.append(item)
        return rows

    @classmethod
    def _validate_journal_lines(cls, *, lines: List[Dict[str, Any]]) -> tuple[Decimal, Decimal]:
        if len(lines) < 2:
            raise ValueError("Journal voucher requires at least 2 valid lines.")
        total_dr = ZERO2
        total_cr = ZERO2
        for i, row in enumerate(lines, start=1):
            account_id = row.get("account")
            dr_amount = q2(row.get("dr_amount") or ZERO2)
            cr_amount = q2(row.get("cr_amount") or ZERO2)
            if not account_id:
                raise ValueError(f"Line {i}: account is required.")
            if dr_amount > ZERO2 and cr_amount > ZERO2:
                raise ValueError(f"Line {i}: both debit and credit cannot be entered in same line.")
            if dr_amount <= ZERO2 and cr_amount <= ZERO2:
                raise ValueError(f"Line {i}: debit or credit amount must be greater than zero.")
            total_dr = q2(total_dr + dr_amount)
            total_cr = q2(total_cr + cr_amount)
        if total_dr != total_cr:
            raise ValueError("Journal voucher total debit and credit must be equal.")
        if total_dr <= ZERO2:
            raise ValueError("Journal voucher total must be greater than zero.")
        return total_dr, total_cr

    @classmethod
    def _validate_cash_bank_lines(cls, *, header: VoucherHeader, lines: List[Dict[str, Any]], policy_controls: Dict[str, Any]) -> Decimal:
        if not lines:
            raise ValueError("At least one valid line is required.")
        if not header.cash_bank_account_id:
            raise ValueError(f"cash_bank_account is required for {header.voucher_type} voucher.")
        directions = set()
        total = ZERO2
        for i, row in enumerate(lines, start=1):
            account_id = row.get("account")
            entry_type = str(row.get("entry_type") or "").upper().strip()
            amount = q2(row.get("amount") or ZERO2)
            if not account_id:
                raise ValueError(f"Line {i}: account is required.")
            if int(account_id) == int(header.cash_bank_account_id):
                raise ValueError(f"Line {i}: account cannot be same as cash/bank account.")
            if entry_type not in {"DR", "CR"}:
                raise ValueError(f"Line {i}: entry_type must be DR or CR.")
            if amount <= ZERO2:
                raise ValueError(f"Line {i}: amount must be greater than zero.")
            directions.add(entry_type)
            total = q2(total + amount)
        if str(policy_controls.get("cash_bank_mixed_entry_rule", "off")).lower().strip() == "hard" and len(directions) > 1:
            raise ValueError(f"mixed DR and CR lines are not allowed in {header.voucher_type} voucher")
        return total

    @staticmethod
    def _build_offset_narration(*, line_narration: Optional[str], header_narration: Optional[str], voucher_type: str) -> str:
        if line_narration:
            return f"Against {line_narration}"
        if header_narration:
            return f"Against {header_narration}"
        return "Auto cash offset" if voucher_type == VoucherHeader.VoucherType.CASH else "Auto bank offset"

    @classmethod
    def _build_cash_bank_rows(cls, *, header: VoucherHeader, lines: List[Dict[str, Any]]) -> List[VoucherLine]:
        rows: List[VoucherLine] = []
        offset_role = VoucherLine.SystemLineRole.CASH_OFFSET if header.voucher_type == VoucherHeader.VoucherType.CASH else VoucherLine.SystemLineRole.BANK_OFFSET
        next_line_no = 1
        for pair_no, row in enumerate(lines, start=1):
            amount = q2(row["amount"])
            entry_type = row["entry_type"]
            business = VoucherLine(
                header=header,
                line_no=next_line_no,
                account_id=int(row["account"]),
                ledger_id=cls._account_ledger_id(row["account"]),
                narration=row.get("narration") or None,
                dr_amount=amount if entry_type == "DR" else ZERO2,
                cr_amount=amount if entry_type == "CR" else ZERO2,
                is_system_generated=False,
                system_line_role=VoucherLine.SystemLineRole.BUSINESS,
                pair_no=pair_no,
            )
            rows.append(business)
            next_line_no += 1
            offset = VoucherLine(
                header=header,
                line_no=next_line_no,
                account_id=int(header.cash_bank_account_id),
                ledger_id=header.cash_bank_ledger_id,
                narration=cls._build_offset_narration(
                    line_narration=row.get("narration"),
                    header_narration=header.narration,
                    voucher_type=header.voucher_type,
                ),
                dr_amount=amount if entry_type == "CR" else ZERO2,
                cr_amount=amount if entry_type == "DR" else ZERO2,
                is_system_generated=True,
                system_line_role=offset_role,
                pair_no=pair_no,
            )
            rows.append(offset)
            next_line_no += 1
        return rows

    @classmethod
    def _build_journal_rows(cls, *, header: VoucherHeader, lines: List[Dict[str, Any]]) -> List[VoucherLine]:
        rows: List[VoucherLine] = []
        for i, row in enumerate(lines, start=1):
            rows.append(
                VoucherLine(
                    header=header,
                    line_no=int(row.get("line_no") or i),
                    account_id=int(row["account"]),
                    ledger_id=cls._account_ledger_id(row["account"]),
                    narration=row.get("narration") or None,
                    dr_amount=q2(row.get("dr_amount") or ZERO2),
                    cr_amount=q2(row.get("cr_amount") or ZERO2),
                    is_system_generated=False,
                    system_line_role=VoucherLine.SystemLineRole.BUSINESS,
                    pair_no=i,
                )
            )
        return rows

    @classmethod
    def _relink_generated_rows(cls, *, rows: List[VoucherLine]) -> None:
        by_pair: Dict[int, List[VoucherLine]] = {}
        for row in rows:
            if row.pair_no is None:
                continue
            by_pair.setdefault(int(row.pair_no), []).append(row)
        for pair_rows in by_pair.values():
            business = next((x for x in pair_rows if not x.is_system_generated), None)
            if not business:
                continue
            for row in pair_rows:
                if row.is_system_generated:
                    row.generated_from_line = business

    @classmethod
    def _build_rows_and_totals(cls, *, header: VoucherHeader, payload_lines: List[Dict[str, Any]], policy_controls: Dict[str, Any]) -> tuple[List[VoucherLine], Decimal, Decimal]:
        if header.voucher_type == VoucherHeader.VoucherType.JOURNAL:
            total_dr, total_cr = cls._validate_journal_lines(lines=payload_lines)
            return cls._build_journal_rows(header=header, lines=payload_lines), total_dr, total_cr
        total = cls._validate_cash_bank_lines(header=header, lines=payload_lines, policy_controls=policy_controls)
        return cls._build_cash_bank_rows(header=header, lines=payload_lines), total, total

    @classmethod
    def _normalize_payload_lines(cls, *, voucher_type: str, payload_lines: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if voucher_type == VoucherHeader.VoucherType.JOURNAL:
            return cls._normalize_journal_lines(payload_lines)
        return cls._normalize_cash_bank_lines(payload_lines)

    @classmethod
    @transaction.atomic
    def create_voucher(cls, *, data: Dict[str, Any], created_by_id: Optional[int]) -> VoucherResult:
        payload_lines = data.pop("lines", [])
        header = VoucherHeader(**data)
        policy = VoucherSettingsService.get_policy(header.entity_id, header.subentity_id)
        # ensure doc_code matches voucher type
        header.doc_code = header.doc_code or _default_doc_code(header.voucher_type, header.entity_id, header.subentity_id)
        if header.voucher_type == VoucherHeader.VoucherType.JOURNAL:
            header.cash_bank_account_id = None
            header.cash_bank_ledger_id = None
        elif str(policy.controls.get("require_cash_bank_account_for_cash_bank", "on")).lower().strip() == "on" and not header.cash_bank_account_id:
            raise ValueError(f"cash_bank_account is required for {header.voucher_type} voucher")
        else:
            header.cash_bank_ledger_id = cls._account_ledger_id(header.cash_bank_account)
        lines = cls._normalize_payload_lines(voucher_type=header.voucher_type, payload_lines=payload_lines)
        rows, total_dr, total_cr = cls._build_rows_and_totals(header=header, payload_lines=lines, policy_controls=policy.controls)
        header.total_debit_amount = total_dr
        header.total_credit_amount = total_cr
        header.created_by_id = created_by_id
        header.save()
        VoucherLine.objects.bulk_create(rows)
        created_rows = list(VoucherLine.objects.filter(header=header).order_by("line_no", "id"))
        cls._relink_generated_rows(rows=created_rows)
        VoucherLine.objects.bulk_update([x for x in created_rows if x.generated_from_line_id], ["generated_from_line"])
        default_action = policy.default_action
        if default_action == "confirm":
            return cls.confirm_voucher(header.id, confirmed_by_id=created_by_id)
        if default_action == "post":
            result = cls.confirm_voucher(header.id, confirmed_by_id=created_by_id) if str(policy.controls.get("require_confirm_before_post", "on")).lower() == "on" else VoucherResult(header=header, message="Voucher saved.")
            return cls.post_voucher(result.header.id, posted_by_id=created_by_id)
        header.refresh_from_db()
        return VoucherResult(header=header, message="Voucher saved.")

    @classmethod
    @transaction.atomic
    def update_voucher(cls, *, instance: VoucherHeader, data: Dict[str, Any]) -> VoucherResult:
        if int(instance.status) in {VoucherHeader.Status.POSTED, VoucherHeader.Status.CANCELLED}:
            raise ValueError("Posted/cancelled vouchers cannot be edited.")
        policy = VoucherSettingsService.get_policy(instance.entity_id, instance.subentity_id)
        state = cls._workflow_state(instance.workflow_payload)
        if state.get("status") == "SUBMITTED" and str(policy.controls.get("allow_edit_after_submit", "on")).lower() == "off":
            raise ValueError("Submitted voucher is locked for edit by policy.")
        payload_lines = data.pop("lines", [])
        original_voucher_type = instance.voucher_type
        for key, value in data.items():
            setattr(instance, key, value)
        if not instance.doc_code or original_voucher_type != instance.voucher_type:
            instance.doc_code = _default_doc_code(instance.voucher_type, instance.entity_id, instance.subentity_id)
        if instance.voucher_type == VoucherHeader.VoucherType.JOURNAL:
            instance.cash_bank_account_id = None
            instance.cash_bank_ledger_id = None
        elif str(policy.controls.get("require_cash_bank_account_for_cash_bank", "on")).lower().strip() == "on" and not instance.cash_bank_account_id:
            raise ValueError(f"cash_bank_account is required for {instance.voucher_type} voucher")
        else:
            instance.cash_bank_ledger_id = cls._account_ledger_id(instance.cash_bank_account)
        lines = cls._normalize_payload_lines(voucher_type=instance.voucher_type, payload_lines=payload_lines)
        rows, total_dr, total_cr = cls._build_rows_and_totals(header=instance, payload_lines=lines, policy_controls=policy.controls)
        instance.total_debit_amount = total_dr
        instance.total_credit_amount = total_cr
        instance.save()
        instance.lines.all().delete()
        VoucherLine.objects.bulk_create(rows)
        created_rows = list(VoucherLine.objects.filter(header=instance).order_by("line_no", "id"))
        cls._relink_generated_rows(rows=created_rows)
        VoucherLine.objects.bulk_update([x for x in created_rows if x.generated_from_line_id], ["generated_from_line"])
        instance.refresh_from_db()
        return VoucherResult(header=instance, message="Voucher updated.")

    @classmethod
    @transaction.atomic
    def confirm_voucher(cls, voucher_id: int, *, confirmed_by_id: Optional[int]) -> VoucherResult:
        header = VoucherHeader.objects.select_for_update().get(pk=voucher_id)
        if int(header.status) != int(VoucherHeader.Status.DRAFT):
            raise ValueError("Only draft vouchers can be confirmed.")
        header.doc_code = header.doc_code or _default_doc_code(header.voucher_type, header.entity_id, header.subentity_id)
        if not header.doc_no:
            doc_type_id = cls._doc_type_id(header.voucher_type, header.doc_code)
            res = DocumentNumberService.allocate_final(
                entity_id=header.entity_id,
                entityfinid_id=header.entityfinid_id,
                subentity_id=header.subentity_id,
                doc_type_id=doc_type_id,
                doc_code=header.doc_code,
            )
            header.doc_no = int(res.doc_no)
            header.voucher_code = res.display_no
        header.status = VoucherHeader.Status.CONFIRMED
        payload = cls._append_audit(header.workflow_payload, {"at": timezone.now().isoformat(), "by": confirmed_by_id, "action": "CONFIRMED", "remarks": None})
        header.workflow_payload = payload
        header.save(update_fields=["doc_no", "voucher_code", "status", "workflow_payload", "updated_at"])
        return VoucherResult(header=header, message="Voucher confirmed.")

    @classmethod
    @transaction.atomic
    def submit_voucher(cls, voucher_id: int, *, submitted_by_id: int, remarks: Optional[str] = None) -> VoucherResult:
        header = VoucherHeader.objects.select_for_update().get(pk=voucher_id)
        if int(header.status) != int(VoucherHeader.Status.DRAFT):
            raise ValueError("Only draft vouchers can be submitted.")
        state = cls._workflow_state(header.workflow_payload)
        state.update({"status": "SUBMITTED", "submitted_by": submitted_by_id, "submitted_at": timezone.now().isoformat(), "remarks": remarks})
        payload = cls._set_workflow_state(header.workflow_payload, state)
        payload = cls._append_audit(payload, {"at": timezone.now().isoformat(), "by": submitted_by_id, "action": "SUBMITTED", "remarks": remarks})
        header.workflow_payload = payload
        header.save(update_fields=["workflow_payload", "updated_at"])
        return VoucherResult(header=header, message="Voucher submitted.")

    @classmethod
    @transaction.atomic
    def approve_voucher(cls, voucher_id: int, *, approved_by_id: int, remarks: Optional[str] = None) -> VoucherResult:
        header = VoucherHeader.objects.select_for_update().get(pk=voucher_id)
        if int(header.status) in {VoucherHeader.Status.POSTED, VoucherHeader.Status.CANCELLED}:
            raise ValueError("Posted/cancelled vouchers cannot be approved.")
        policy = VoucherSettingsService.get_policy(header.entity_id, header.subentity_id)
        state = cls._workflow_state(header.workflow_payload)
        if str(policy.controls.get("require_submit_before_approve", "off")).lower() == "on" and state.get("status") != "SUBMITTED":
            raise ValueError("Voucher must be submitted before approval by policy.")
        if str(policy.controls.get("same_user_submit_approve", "on")).lower() == "off" and state.get("submitted_by") and int(state["submitted_by"]) == int(approved_by_id):
            raise ValueError("Approver must be different from submitter.")
        state.update({"status": "APPROVED", "approved_by": approved_by_id, "approved_at": timezone.now().isoformat(), "remarks": remarks})
        payload = cls._set_workflow_state(header.workflow_payload, state)
        payload = cls._append_audit(payload, {"at": timezone.now().isoformat(), "by": approved_by_id, "action": "APPROVED", "remarks": remarks})
        header.workflow_payload = payload
        header.approved_by_id = approved_by_id
        header.approved_at = timezone.now()
        header.save(update_fields=["workflow_payload", "approved_by", "approved_at", "updated_at"])
        return VoucherResult(header=header, message="Voucher approved.")

    @classmethod
    @transaction.atomic
    def reject_voucher(cls, voucher_id: int, *, rejected_by_id: int, remarks: Optional[str] = None) -> VoucherResult:
        header = VoucherHeader.objects.select_for_update().get(pk=voucher_id)
        if int(header.status) in {VoucherHeader.Status.POSTED, VoucherHeader.Status.CANCELLED}:
            raise ValueError("Posted/cancelled vouchers cannot be rejected.")
        state = cls._workflow_state(header.workflow_payload)
        state.update({"status": "REJECTED", "rejected_by": rejected_by_id, "rejected_at": timezone.now().isoformat(), "remarks": remarks})
        payload = cls._set_workflow_state(header.workflow_payload, state)
        payload = cls._append_audit(payload, {"at": timezone.now().isoformat(), "by": rejected_by_id, "action": "REJECTED", "remarks": remarks})
        header.workflow_payload = payload
        header.save(update_fields=["workflow_payload", "updated_at"])
        return VoucherResult(header=header, message="Voucher rejected.")

    @classmethod
    @transaction.atomic
    def post_voucher(cls, voucher_id: int, *, posted_by_id: Optional[int]) -> VoucherResult:
        header = VoucherHeader.objects.select_for_update().prefetch_related("lines").get(pk=voucher_id)
        policy = VoucherSettingsService.get_policy(header.entity_id, header.subentity_id)
        if int(header.status) == int(VoucherHeader.Status.POSTED):
            raise ValueError("Voucher is already posted.")
        if int(header.status) == int(VoucherHeader.Status.CANCELLED):
            raise ValueError("Cancelled voucher cannot be posted.")
        if str(policy.controls.get("require_confirm_before_post", "on")).lower() == "on" and int(header.status) != int(VoucherHeader.Status.CONFIRMED):
            raise ValueError("Voucher must be confirmed before posting by policy.")
        if str(policy.controls.get("voucher_maker_checker", "off")).lower() == "hard":
            state = cls._workflow_state(header.workflow_payload)
            if state.get("status") != "APPROVED":
                raise ValueError("Voucher must be approved before posting by policy.")
        VoucherPostingAdapter.post_voucher(header=header, lines=list(header.lines.all()), user_id=posted_by_id)
        header.status = VoucherHeader.Status.POSTED
        header.save(update_fields=["status", "updated_at"])
        return VoucherResult(header=header, message="Voucher posted.")

    @classmethod
    @transaction.atomic
    def unpost_voucher(cls, voucher_id: int, *, unposted_by_id: Optional[int]) -> VoucherResult:
        header = VoucherHeader.objects.select_for_update().prefetch_related("lines").get(pk=voucher_id)
        if int(header.status) != int(VoucherHeader.Status.POSTED):
            raise ValueError("Only posted vouchers can be unposted.")
        VoucherPostingAdapter.unpost_voucher(header=header, lines=list(header.lines.all()), user_id=unposted_by_id)
        policy = VoucherSettingsService.get_policy(header.entity_id, header.subentity_id)
        target = str(policy.controls.get("unpost_target_status", "confirmed")).lower().strip()
        header.status = VoucherHeader.Status.DRAFT if target == "draft" else VoucherHeader.Status.CONFIRMED
        payload = cls._append_audit(header.workflow_payload, {"at": timezone.now().isoformat(), "by": unposted_by_id, "action": "UNPOSTED", "remarks": None})
        header.workflow_payload = payload
        header.save(update_fields=["status", "workflow_payload", "updated_at"])
        return VoucherResult(header=header, message="Voucher unposted.")

    @classmethod
    @transaction.atomic
    def cancel_voucher(cls, voucher_id: int, *, cancelled_by_id: Optional[int], reason: Optional[str] = None) -> VoucherResult:
        header = VoucherHeader.objects.select_for_update().get(pk=voucher_id)
        if int(header.status) == int(VoucherHeader.Status.POSTED):
            raise ValueError("Posted voucher cannot be cancelled. Unpost it first.")
        if int(header.status) == int(VoucherHeader.Status.CANCELLED):
            raise ValueError("Voucher is already cancelled.")
        header.status = VoucherHeader.Status.CANCELLED
        header.is_cancelled = True
        header.cancel_reason = reason
        header.cancelled_by_id = cancelled_by_id
        header.cancelled_at = timezone.now()
        payload = cls._append_audit(header.workflow_payload, {"at": timezone.now().isoformat(), "by": cancelled_by_id, "action": "CANCELLED", "remarks": reason})
        header.workflow_payload = payload
        header.save(update_fields=["status", "is_cancelled", "cancel_reason", "cancelled_by", "cancelled_at", "workflow_payload", "updated_at"])
        return VoucherResult(header=header, message="Voucher cancelled.")
