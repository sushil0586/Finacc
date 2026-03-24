from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from django.db import transaction
from django.utils import timezone

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from financial.models import account as FinancialAccount
from purchase.services.purchase_ap_service import PurchaseApService
from purchase.services.ap_allocation_service import PurchaseApAllocationService
from purchase.models.purchase_ap import VendorBillOpenItem
from posting.adapters.payment_voucher import PaymentVoucherPostingAdapter, PaymentVoucherPostingConfig

from payments.models.payment_core import (
    PaymentVoucherHeader,
    PaymentVoucherAllocation,
    PaymentVoucherAdjustment,
    PaymentVoucherAdvanceAdjustment,
)
from payments.services.payment_settings_service import PaymentSettingsService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(x) -> Decimal:
    return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PaymentVoucherResult:
    header: PaymentVoucherHeader
    message: str


class PaymentVoucherService:
    @staticmethod
    def _as_pk(value: Any) -> Any:
        if value in (None, ""):
            return None
        return getattr(value, "pk", value)

    @staticmethod
    def _account_ledger_id(value: Any) -> Optional[int]:
        account_obj = value if hasattr(value, "ledger_id") else None
        account_id = getattr(account_obj, "pk", None) or (value if isinstance(value, int) else None)
        ledger_id = getattr(account_obj, "ledger_id", None)
        if ledger_id:
            return int(ledger_id)
        if not account_id:
            return None
        return (
            FinancialAccount.objects.filter(pk=account_id)
            .values_list("ledger_id", flat=True)
            .first()
        )

    @classmethod
    def _normalize_allocations(cls, allocations: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for row in allocations or []:
            item = dict(row or {})
            item["open_item"] = cls._as_pk(item.get("open_item"))
            rows.append(item)
        return rows

    @classmethod
    def _normalize_adjustments(cls, adjustments: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for row in adjustments or []:
            item = dict(row or {})
            item["allocation"] = cls._as_pk(item.get("allocation"))
            item["ledger_account"] = cls._as_pk(item.get("ledger_account"))
            item["ledger"] = cls._account_ledger_id(item.get("ledger_account"))
            rows.append(item)
        return rows

    @classmethod
    def _normalize_advance_adjustments(cls, rows_in: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for row in rows_in or []:
            item = dict(row or {})
            item["advance_balance_id"] = cls._as_pk(item.get("advance_balance_id") or item.get("advance_balance"))
            item["allocation"] = cls._as_pk(item.get("allocation"))
            item["open_item"] = cls._as_pk(item.get("open_item"))
            rows.append(item)
        return rows

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
    def _sum_allocations(allocations: Iterable[Dict[str, Any]]) -> Decimal:
        total = ZERO2
        for row in allocations or []:
            total = q2(total + q2(row.get("settled_amount") or ZERO2))
        return total

    @staticmethod
    def _sum_advance_adjustments(rows: Iterable[Dict[str, Any]]) -> Decimal:
        total = ZERO2
        for row in rows or []:
            total = q2(total + q2(row.get("adjusted_amount") or ZERO2))
        return total

    @staticmethod
    def _fresh_allocation_rows(voucher: PaymentVoucherHeader) -> List[PaymentVoucherAllocation]:
        # Posting paths may create allocations after the voucher was loaded with
        # prefetched relations. Always requery allocations to avoid stale
        # prefetched caches masking newly created rows.
        return list(
            PaymentVoucherAllocation.objects.filter(payment_voucher_id=voucher.id).select_related("open_item")
        )

    @staticmethod
    def _doc_type_id_for_payment(doc_code: str) -> int:
        dt = DocumentType.objects.filter(module="payments", default_code=doc_code, is_active=True).first()
        if not dt:
            raise ValueError(f"DocumentType not found for module='payments' and doc_code='{doc_code}'")
        return dt.id

    @staticmethod
    def _compute_adjustment_total(adjustments: Iterable[Dict[str, Any]]) -> Decimal:
        total = ZERO2
        for row in adjustments or []:
            amt = q2(row.get("amount") or ZERO2)
            eff = str(row.get("settlement_effect") or PaymentVoucherAdjustment.Effect.PLUS)
            if eff == PaymentVoucherAdjustment.Effect.MINUS:
                total = q2(total - amt)
            else:
                total = q2(total + amt)
        return total

    @staticmethod
    def _effective_settlement_amount(cash_paid_amount: Decimal, adjustment_total: Decimal) -> Decimal:
        return q2(q2(cash_paid_amount) + q2(adjustment_total))

    @staticmethod
    def _validate_allocations(
        voucher: PaymentVoucherHeader, allocations: List[Dict[str, Any]], over_settlement_rule: str = "block", controls: Optional[Dict[str, Any]] = None
    ) -> list[str]:
        warnings: list[str] = []
        allocatable_by_item = PurchaseApAllocationService.allocatable_map(
            entity_id=int(voucher.entity_id),
            entityfinid_id=int(voucher.entityfinid_id),
            subentity_id=voucher.subentity_id,
            vendor_id=int(voucher.paid_to_id),
            controls=controls,
        )
        for i, row in enumerate(allocations or [], start=1):
            open_item_id = row.get("open_item")
            amt = q2(row.get("settled_amount") or ZERO2)
            if open_item_id in (None, ""):
                raise ValueError(f"Allocation row {i}: open_item is required.")
            if amt <= ZERO2:
                raise ValueError(f"Allocation row {i}: settled_amount must be > 0.")

            open_item = VendorBillOpenItem.objects.filter(pk=open_item_id).first()
            if not open_item:
                raise ValueError(f"Allocation row {i}: open_item not found.")
            if int(open_item.entity_id) != int(voucher.entity_id) or int(open_item.entityfinid_id) != int(voucher.entityfinid_id):
                raise ValueError(f"Allocation row {i}: open_item scope mismatch with entity/entityfinid.")
            if voucher.subentity_id != open_item.subentity_id:
                raise ValueError(f"Allocation row {i}: open_item subentity mismatch.")
            if int(open_item.vendor_id) != int(voucher.paid_to_id):
                raise ValueError(f"Allocation row {i}: open_item vendor mismatch with paid_to.")

            allocatable = q2(allocatable_by_item.get(int(open_item_id), ZERO2))
            if over_settlement_rule == "block":
                if amt > allocatable:
                    raise ValueError(
                        f"Allocation row {i}: settled_amount {amt} exceeds allocatable {allocatable} for open_item {open_item_id}."
                    )
            elif over_settlement_rule == "warn":
                if amt > allocatable:
                    warnings.append(
                        f"Allocation row {i}: settled_amount {amt} exceeds allocatable {allocatable} for open_item {open_item_id}."
                    )
        return warnings

    @staticmethod
    def _validate_adjustment_allocation_links(*, voucher_id: int, adjustments: List[Dict[str, Any]]) -> None:
        for i, row in enumerate(adjustments or [], start=1):
            alloc_id = row.get("allocation")
            if alloc_id in (None, ""):
                continue
            ok = PaymentVoucherAllocation.objects.filter(id=int(alloc_id), payment_voucher_id=int(voucher_id)).exists()
            if not ok:
                raise ValueError(f"Adjustment row {i}: allocation must belong to this payment voucher.")

    @staticmethod
    def _validate_advance_adjustments(
        *,
        voucher: PaymentVoucherHeader,
        allocations: List[Dict[str, Any]],
        advance_adjustments: List[Dict[str, Any]],
    ) -> None:
        if not advance_adjustments:
            return

        alloc_open_item_map = {}
        for row in allocations or []:
            open_item_id = PaymentVoucherService._as_pk(row.get("open_item"))
            if open_item_id in (None, ""):
                continue
            alloc_open_item_map[int(open_item_id)] = q2(row.get("settled_amount") or ZERO2)

        per_balance: Dict[int, Decimal] = {}
        per_open_item: Dict[int, Decimal] = {}

        for i, row in enumerate(advance_adjustments or [], start=1):
            balance_id = row.get("advance_balance_id")
            amount = q2(row.get("adjusted_amount") or ZERO2)
            alloc_id = row.get("allocation")
            open_item_id = row.get("open_item")

            if balance_id in (None, ""):
                raise ValueError(f"Advance row {i}: advance_balance_id is required.")
            if amount <= ZERO2:
                raise ValueError(f"Advance row {i}: adjusted_amount must be > 0.")

            adv = PurchaseApService.list_open_advances(
                entity_id=voucher.entity_id,
                entityfinid_id=voucher.entityfinid_id,
                subentity_id=voucher.subentity_id,
                vendor_id=voucher.paid_to_id,
                is_open=None,
            ).filter(id=int(balance_id)).first()
            if not adv:
                raise ValueError(f"Advance row {i}: advance balance not found in selected scope/vendor.")

            if alloc_id not in (None, ""):
                alloc = PaymentVoucherAllocation.objects.filter(
                    id=int(alloc_id),
                    payment_voucher_id=int(voucher.id or 0),
                ).select_related("open_item").first()
                if not alloc:
                    raise ValueError(f"Advance row {i}: allocation must belong to this voucher.")
                open_item_id = open_item_id or alloc.open_item_id
                row["open_item"] = open_item_id

            if open_item_id in (None, ""):
                raise ValueError(f"Advance row {i}: open_item is required for bill adjustment.")

            open_item = VendorBillOpenItem.objects.filter(pk=int(open_item_id)).first()
            if not open_item:
                raise ValueError(f"Advance row {i}: open_item not found.")
            if int(open_item.entity_id) != int(voucher.entity_id) or int(open_item.entityfinid_id) != int(voucher.entityfinid_id):
                raise ValueError(f"Advance row {i}: open_item scope mismatch.")
            if voucher.subentity_id != open_item.subentity_id:
                raise ValueError(f"Advance row {i}: open_item subentity mismatch.")
            if int(open_item.vendor_id) != int(voucher.paid_to_id):
                raise ValueError(f"Advance row {i}: open_item vendor mismatch with paid_to.")

            per_balance[int(balance_id)] = q2(per_balance.get(int(balance_id), ZERO2) + amount)
            per_open_item[int(open_item_id)] = q2(per_open_item.get(int(open_item_id), ZERO2) + amount)

        for balance_id, total in per_balance.items():
            adv = PurchaseApService.list_open_advances(
                entity_id=voucher.entity_id,
                entityfinid_id=voucher.entityfinid_id,
                subentity_id=voucher.subentity_id,
                vendor_id=voucher.paid_to_id,
                is_open=None,
            ).filter(id=balance_id).first()
            if adv and total - q2(adv.outstanding_amount) > Decimal("0.01"):
                raise ValueError(
                    f"Advance balance {balance_id} consumption {q2(total)} exceeds available balance {q2(adv.outstanding_amount)}."
                )

        for open_item_id, total in per_open_item.items():
            allocated = q2(alloc_open_item_map.get(int(open_item_id), ZERO2))
            if allocated <= ZERO2:
                raise ValueError(f"Advance adjustment references open_item {open_item_id} which is not allocated in this voucher.")
            if total - allocated > Decimal("0.01"):
                raise ValueError(
                    f"Advance consumption {q2(total)} exceeds allocated amount {q2(allocated)} for open_item {open_item_id}."
                )

    @staticmethod
    def _validate_allocation_effective_match(
        *,
        effective_amount: Decimal,
        allocation_total: Decimal,
        level: str = "hard",
        tolerance: Decimal = Decimal("0.01"),
    ) -> list[str]:
        warnings: list[str] = []
        lv = str(level or "hard").lower().strip()
        if lv not in {"off", "warn", "hard"}:
            lv = "hard"
        if lv == "off":
            return warnings
        diff = q2(abs(q2(effective_amount) - q2(allocation_total)))
        if diff <= q2(tolerance):
            return warnings
        msg = (
            f"Allocation total {q2(allocation_total)} does not match settlement effective amount {q2(effective_amount)}."
        )
        if lv == "hard":
            raise ValueError(msg)
        warnings.append(msg)
        return warnings

    @staticmethod
    def _auto_fifo_allocations(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        vendor_id: int,
        target_amount: Decimal,
        controls: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        remaining = q2(target_amount)
        if remaining <= ZERO2:
            return []
        preview = PurchaseApAllocationService.preview_allocation(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            target_amount=remaining,
            controls=controls,
        )
        return list(preview.get("plan") or [])

    @staticmethod
    @transaction.atomic
    def create_voucher(validated_data: Dict[str, Any]) -> PaymentVoucherHeader:
        allocations = PaymentVoucherService._normalize_allocations(validated_data.pop("allocations", []) or [])
        adjustments = PaymentVoucherService._normalize_adjustments(validated_data.pop("adjustments", []) or [])
        advance_adjustments = PaymentVoucherService._normalize_advance_adjustments(
            validated_data.pop("advance_adjustments", []) or []
        )

        currency_code = (validated_data.get("currency_code") or "INR").strip().upper()
        base_currency_code = (validated_data.get("base_currency_code") or "INR").strip().upper()
        exchange_rate = Decimal(validated_data.get("exchange_rate") or Decimal("1.000000"))
        if len(currency_code) != 3:
            raise ValueError({"currency_code": "currency_code must be 3 letters (ISO)."})
        if len(base_currency_code) != 3:
            raise ValueError({"base_currency_code": "base_currency_code must be 3 letters (ISO)."})
        if exchange_rate <= 0:
            raise ValueError({"exchange_rate": "exchange_rate must be > 0."})
        validated_data["currency_code"] = currency_code
        validated_data["base_currency_code"] = base_currency_code
        validated_data["exchange_rate"] = exchange_rate

        policy = PaymentSettingsService.get_policy(
            validated_data["entity"].id if hasattr(validated_data.get("entity"), "id") else validated_data.get("entity"),
            validated_data.get("subentity").id if hasattr(validated_data.get("subentity"), "id") else validated_data.get("subentity"),
        )
        ref_level = str(policy.controls.get("require_reference_number", "off")).lower().strip()
        if ref_level == "hard" and not (validated_data.get("reference_number") or "").strip():
            raise ValueError({"reference_number": "reference_number is required by payment policy."})

        if int(validated_data.get("status", PaymentVoucherHeader.Status.DRAFT)) != int(PaymentVoucherHeader.Status.DRAFT):
            validated_data["status"] = PaymentVoucherHeader.Status.DRAFT

        adjustment_total = PaymentVoucherService._compute_adjustment_total(adjustments)
        advance_total = PaymentVoucherService._sum_advance_adjustments(advance_adjustments)
        effective = PaymentVoucherService._effective_settlement_amount(
            q2(validated_data.get("cash_paid_amount", ZERO2)),
            adjustment_total,
        )
        validated_data["total_adjustment_amount"] = adjustment_total
        validated_data["settlement_effective_amount"] = effective
        validated_data["settlement_effective_amount_base_currency"] = q2(effective * exchange_rate)

        allocation_policy = str(policy.controls.get("allocation_policy", "manual")).lower().strip()
        if (
            not allocations
            and allocation_policy == "fifo"
            and validated_data.get("payment_type") == PaymentVoucherHeader.PaymentType.AGAINST_BILL
        ):
            allocations = PaymentVoucherService._auto_fifo_allocations(
                entity_id=validated_data["entity"].id if hasattr(validated_data.get("entity"), "id") else validated_data["entity"],
                entityfinid_id=validated_data["entityfinid"].id if hasattr(validated_data.get("entityfinid"), "id") else validated_data["entityfinid"],
                subentity_id=validated_data.get("subentity").id if hasattr(validated_data.get("subentity"), "id") else validated_data.get("subentity"),
                vendor_id=validated_data["paid_to"].id if hasattr(validated_data.get("paid_to"), "id") else validated_data["paid_to"],
                target_amount=effective,
                controls=policy.controls,
            )

        amount_match_level = str(policy.controls.get("allocation_amount_match_rule", "hard")).lower().strip()
        total_support = q2(effective + advance_total)
        if allocations:
            PaymentVoucherService._validate_allocation_effective_match(
                effective_amount=total_support,
                allocation_total=PaymentVoucherService._sum_allocations(allocations),
                level=amount_match_level,
            )

        validated_data["paid_from_ledger_id"] = PaymentVoucherService._account_ledger_id(validated_data.get("paid_from"))
        validated_data["paid_to_ledger_id"] = PaymentVoucherService._account_ledger_id(validated_data.get("paid_to"))

        header = PaymentVoucherHeader.objects.create(**validated_data)

        over_settlement_rule = str(policy.controls.get("over_settlement_rule", "block")).lower().strip()
        if allocations:
            PaymentVoucherService._validate_allocations(
                header,
                allocations,
                over_settlement_rule=over_settlement_rule,
                controls=policy.controls,
            )

        for row in allocations:
            PaymentVoucherAllocation.objects.create(
                payment_voucher=header,
                open_item_id=row.get("open_item"),
                settled_amount=q2(row.get("settled_amount") or ZERO2),
                is_full_settlement=bool(row.get("is_full_settlement", False)),
                is_advance_adjustment=bool(row.get("is_advance_adjustment", False)),
            )

        for row in adjustments:
            PaymentVoucherAdjustment.objects.create(
                payment_voucher=header,
                allocation_id=row.get("allocation"),
                adj_type=row.get("adj_type"),
                ledger_account_id=row.get("ledger_account"),
                ledger_id=row.get("ledger"),
                amount=q2(row.get("amount") or ZERO2),
                settlement_effect=row.get("settlement_effect") or PaymentVoucherAdjustment.Effect.PLUS,
                remarks=(row.get("remarks") or "").strip() or None,
            )

        PaymentVoucherService._validate_adjustment_allocation_links(voucher_id=header.id, adjustments=adjustments)
        PaymentVoucherService._validate_advance_adjustments(
            voucher=header,
            allocations=allocations,
            advance_adjustments=advance_adjustments,
        )
        for row in advance_adjustments:
            PaymentVoucherAdvanceAdjustment.objects.create(
                payment_voucher=header,
                advance_balance_id=row.get("advance_balance_id"),
                allocation_id=row.get("allocation"),
                open_item_id=row.get("open_item"),
                adjusted_amount=q2(row.get("adjusted_amount") or ZERO2),
                remarks=(row.get("remarks") or "").strip() or None,
            )

        if policy.default_action == "confirm":
            PaymentVoucherService.confirm_voucher(header.id)
        elif policy.default_action == "post":
            PaymentVoucherService.confirm_voucher(header.id)
            PaymentVoucherService.post_voucher(header.id)

        header.refresh_from_db()
        return header

    @staticmethod
    @transaction.atomic
    def update_voucher(instance: PaymentVoucherHeader, validated_data: Dict[str, Any]) -> PaymentVoucherHeader:
        if int(instance.status) in (int(PaymentVoucherHeader.Status.POSTED), int(PaymentVoucherHeader.Status.CANCELLED)):
            raise ValueError("Posted/Cancelled payment voucher cannot be edited.")

        allocations = validated_data.pop("allocations", None)
        adjustments = validated_data.pop("adjustments", None)
        advance_adjustments = validated_data.pop("advance_adjustments", None)
        if allocations is not None:
            allocations = PaymentVoucherService._normalize_allocations(allocations)
        if adjustments is not None:
            adjustments = PaymentVoucherService._normalize_adjustments(adjustments)
        if advance_adjustments is not None:
            advance_adjustments = PaymentVoucherService._normalize_advance_adjustments(advance_adjustments)
        policy = PaymentSettingsService.get_policy(instance.entity_id, instance.subentity_id)
        workflow_state = PaymentVoucherService._workflow_state(instance.workflow_payload)
        if (
            str(policy.controls.get("allow_edit_after_submit", "on")).lower().strip() == "off"
            and workflow_state.get("status") == "SUBMITTED"
        ):
            raise ValueError("Submitted voucher cannot be edited by payment policy.")
        over_settlement_rule = str(policy.controls.get("over_settlement_rule", "block")).lower().strip()
        amount_match_level = str(policy.controls.get("allocation_amount_match_rule", "hard")).lower().strip()

        if "currency_code" in validated_data:
            validated_data["currency_code"] = (validated_data.get("currency_code") or "INR").strip().upper()
            if len(validated_data["currency_code"]) != 3:
                raise ValueError({"currency_code": "currency_code must be 3 letters (ISO)."})
        if "base_currency_code" in validated_data:
            validated_data["base_currency_code"] = (validated_data.get("base_currency_code") or "INR").strip().upper()
            if len(validated_data["base_currency_code"]) != 3:
                raise ValueError({"base_currency_code": "base_currency_code must be 3 letters (ISO)."})
        if "exchange_rate" in validated_data:
            ex = Decimal(validated_data.get("exchange_rate") or Decimal("1.000000"))
            if ex <= 0:
                raise ValueError({"exchange_rate": "exchange_rate must be > 0."})
            validated_data["exchange_rate"] = ex

        for k, v in validated_data.items():
            setattr(instance, k, v)
        if "paid_from" in validated_data:
            instance.paid_from_ledger_id = PaymentVoucherService._account_ledger_id(validated_data.get("paid_from"))
        if "paid_to" in validated_data:
            instance.paid_to_ledger_id = PaymentVoucherService._account_ledger_id(validated_data.get("paid_to"))
        instance.save()

        if allocations is not None:
            PaymentVoucherService._validate_allocations(
                instance,
                allocations,
                over_settlement_rule=over_settlement_rule,
                controls=policy.controls,
            )
            live_advance_rows = advance_adjustments
            if live_advance_rows is None:
                live_advance_rows = [
                    {
                        "advance_balance_id": x.advance_balance_id,
                        "allocation": x.allocation_id,
                        "open_item": x.open_item_id,
                        "adjusted_amount": x.adjusted_amount,
                    }
                    for x in instance.advance_adjustments.all()
                ]
            PaymentVoucherService._validate_allocation_effective_match(
                effective_amount=q2(
                    PaymentVoucherService._effective_settlement_amount(
                    q2(validated_data.get("cash_paid_amount", instance.cash_paid_amount)),
                    PaymentVoucherService._compute_adjustment_total(
                        adjustments
                        if adjustments is not None
                        else instance.adjustments.values("amount", "settlement_effect")
                    ),
                ) + PaymentVoucherService._sum_advance_adjustments(live_advance_rows)),
                allocation_total=PaymentVoucherService._sum_allocations(allocations),
                level=amount_match_level,
            )
            existing = {x.id: x for x in instance.allocations.all()}
            seen = set()
            for row in allocations:
                rid = row.get("id")
                if rid and rid in existing:
                    obj = existing[rid]
                    obj.open_item_id = row.get("open_item")
                    obj.settled_amount = q2(row.get("settled_amount") or ZERO2)
                    obj.is_full_settlement = bool(row.get("is_full_settlement", False))
                    obj.is_advance_adjustment = bool(row.get("is_advance_adjustment", False))
                    obj.save()
                    seen.add(rid)
                else:
                    obj = PaymentVoucherAllocation.objects.create(
                        payment_voucher=instance,
                        open_item_id=row.get("open_item"),
                        settled_amount=q2(row.get("settled_amount") or ZERO2),
                        is_full_settlement=bool(row.get("is_full_settlement", False)),
                        is_advance_adjustment=bool(row.get("is_advance_adjustment", False)),
                    )
                    seen.add(obj.id)
            for rid, obj in existing.items():
                if rid not in seen:
                    obj.delete()

        if adjustments is not None:
            existing = {x.id: x for x in instance.adjustments.all()}
            seen = set()
            for row in adjustments:
                rid = row.get("id")
                if rid and rid in existing:
                    obj = existing[rid]
                    obj.allocation_id = row.get("allocation")
                    obj.adj_type = row.get("adj_type")
                    obj.ledger_account_id = row.get("ledger_account")
                    obj.ledger_id = row.get("ledger")
                    obj.amount = q2(row.get("amount") or ZERO2)
                    obj.settlement_effect = row.get("settlement_effect") or PaymentVoucherAdjustment.Effect.PLUS
                    obj.remarks = (row.get("remarks") or "").strip() or None
                    obj.save()
                    seen.add(rid)
                else:
                    obj = PaymentVoucherAdjustment.objects.create(
                        payment_voucher=instance,
                        allocation_id=row.get("allocation"),
                        adj_type=row.get("adj_type"),
                        ledger_account_id=row.get("ledger_account"),
                        ledger_id=row.get("ledger"),
                        amount=q2(row.get("amount") or ZERO2),
                        settlement_effect=row.get("settlement_effect") or PaymentVoucherAdjustment.Effect.PLUS,
                        remarks=(row.get("remarks") or "").strip() or None,
                    )
                    seen.add(obj.id)
            for rid, obj in existing.items():
                if rid not in seen:
                    obj.delete()
            PaymentVoucherService._validate_adjustment_allocation_links(voucher_id=instance.id, adjustments=adjustments)

        if advance_adjustments is not None:
            current_allocations = allocations
            if current_allocations is None:
                current_allocations = [
                    {
                        "open_item": x.open_item_id,
                        "settled_amount": x.settled_amount,
                    }
                    for x in instance.allocations.all()
                ]
            PaymentVoucherService._validate_advance_adjustments(
                voucher=instance,
                allocations=current_allocations,
                advance_adjustments=advance_adjustments,
            )
            existing = {x.id: x for x in instance.advance_adjustments.all()}
            seen = set()
            for row in advance_adjustments:
                rid = row.get("id")
                if rid and rid in existing:
                    obj = existing[rid]
                    obj.advance_balance_id = row.get("advance_balance_id")
                    obj.allocation_id = row.get("allocation")
                    obj.open_item_id = row.get("open_item")
                    obj.adjusted_amount = q2(row.get("adjusted_amount") or ZERO2)
                    obj.remarks = (row.get("remarks") or "").strip() or None
                    obj.save()
                    seen.add(rid)
                else:
                    obj = PaymentVoucherAdvanceAdjustment.objects.create(
                        payment_voucher=instance,
                        advance_balance_id=row.get("advance_balance_id"),
                        allocation_id=row.get("allocation"),
                        open_item_id=row.get("open_item"),
                        adjusted_amount=q2(row.get("adjusted_amount") or ZERO2),
                        remarks=(row.get("remarks") or "").strip() or None,
                    )
                    seen.add(obj.id)
            for rid, obj in existing.items():
                if rid not in seen:
                    obj.delete()

        adjustment_total = PaymentVoucherService._compute_adjustment_total(
            instance.adjustments.values("amount", "settlement_effect")
        )
        instance.total_adjustment_amount = adjustment_total
        instance.settlement_effective_amount = PaymentVoucherService._effective_settlement_amount(
            q2(instance.cash_paid_amount),
            adjustment_total,
        )
        ex_rate = Decimal(getattr(instance, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000"))
        if ex_rate <= 0:
            ex_rate = Decimal("1.000000")
        instance.settlement_effective_amount_base_currency = q2(instance.settlement_effective_amount * ex_rate)
        instance.save(
            update_fields=[
                "total_adjustment_amount",
                "settlement_effective_amount",
                "settlement_effective_amount_base_currency",
                "updated_at",
            ]
        )
        return instance

    @staticmethod
    @transaction.atomic
    def confirm_voucher(voucher_id: int, confirmed_by_id: Optional[int] = None) -> PaymentVoucherResult:
        h = PaymentVoucherHeader.objects.select_related("entity", "entityfinid", "subentity").get(pk=voucher_id)

        if int(h.status) == int(PaymentVoucherHeader.Status.CANCELLED):
            raise ValueError("Cannot confirm: voucher is cancelled.")
        if int(h.status) == int(PaymentVoucherHeader.Status.POSTED):
            return PaymentVoucherResult(h, "Already posted.")

        if not h.doc_code:
            s = PaymentSettingsService.get_settings(h.entity_id, h.subentity_id)
            h.doc_code = s.default_doc_code_payment or "PPV"

        if not h.doc_no or not h.voucher_code:
            dt_id = PaymentVoucherService._doc_type_id_for_payment(h.doc_code)
            allocated = DocumentNumberService.allocate_final(
                entity_id=h.entity_id,
                entityfinid_id=h.entityfinid_id,
                subentity_id=h.subentity_id,
                doc_type_id=dt_id,
                doc_code=h.doc_code,
                on_date=h.voucher_date,
            )
            h.doc_no = allocated.doc_no
            h.voucher_code = allocated.display_no

        if int(h.status) == int(PaymentVoucherHeader.Status.CONFIRMED):
            if confirmed_by_id and not h.approved_by_id:
                h.approved_by_id = confirmed_by_id
                h.save(update_fields=["doc_code", "doc_no", "voucher_code", "approved_by", "updated_at"])
            else:
                h.save(update_fields=["doc_code", "doc_no", "voucher_code", "updated_at"])
            return PaymentVoucherResult(h, "Already confirmed.")

        h.status = PaymentVoucherHeader.Status.CONFIRMED
        if confirmed_by_id and not h.approved_by_id:
            h.approved_by_id = confirmed_by_id
            h.save(update_fields=["doc_code", "doc_no", "voucher_code", "status", "approved_by", "updated_at"])
        else:
            h.save(update_fields=["doc_code", "doc_no", "voucher_code", "status", "updated_at"])
        return PaymentVoucherResult(h, "Confirmed.")

    @staticmethod
    @transaction.atomic
    def submit_voucher(voucher_id: int, submitted_by_id: Optional[int] = None, remarks: Optional[str] = None) -> PaymentVoucherResult:
        h = PaymentVoucherHeader.objects.select_for_update().get(pk=voucher_id)
        if int(h.status) in (int(PaymentVoucherHeader.Status.POSTED), int(PaymentVoucherHeader.Status.CANCELLED)):
            raise ValueError("Only draft/confirmed vouchers can be submitted.")
        state = PaymentVoucherService._workflow_state(h.workflow_payload)
        state.update({
            "status": "SUBMITTED",
            "submitted_by": submitted_by_id,
            "submitted_at": timezone.now().isoformat(),
            "remarks": (remarks or "").strip() or None,
        })
        h.workflow_payload = PaymentVoucherService._set_workflow_state(h.workflow_payload, state)
        h.workflow_payload = PaymentVoucherService._append_audit(
            h.workflow_payload,
            {"action": "SUBMITTED", "at": timezone.now().isoformat(), "by": submitted_by_id, "remarks": state["remarks"]},
        )
        h.save(update_fields=["workflow_payload", "updated_at"])
        return PaymentVoucherResult(h, "Submitted for approval.")

    @staticmethod
    @transaction.atomic
    def approve_voucher(voucher_id: int, approved_by_id: Optional[int] = None, remarks: Optional[str] = None) -> PaymentVoucherResult:
        h = PaymentVoucherHeader.objects.select_for_update().get(pk=voucher_id)
        if int(h.status) in (int(PaymentVoucherHeader.Status.POSTED), int(PaymentVoucherHeader.Status.CANCELLED)):
            raise ValueError("Only draft/confirmed vouchers can be approved.")
        policy = PaymentSettingsService.get_policy(h.entity_id, h.subentity_id)
        state = PaymentVoucherService._workflow_state(h.workflow_payload)
        if (
            str(policy.controls.get("require_submit_before_approve", "off")).lower().strip() == "on"
            and state.get("status") != "SUBMITTED"
        ):
            raise ValueError("Voucher must be submitted before approval by policy.")
        same_user_allowed = str(policy.controls.get("same_user_submit_approve", "on")).lower().strip() == "on"
        if (
            not same_user_allowed
            and state.get("submitted_by")
            and approved_by_id
            and int(state["submitted_by"]) == int(approved_by_id)
        ):
            raise ValueError("Approver must be different from submitter.")
        state.update({
            "status": "APPROVED",
            "approved_by": approved_by_id,
            "approved_at": timezone.now().isoformat(),
            "remarks": (remarks or "").strip() or None,
        })
        h.workflow_payload = PaymentVoucherService._set_workflow_state(h.workflow_payload, state)
        h.workflow_payload = PaymentVoucherService._append_audit(
            h.workflow_payload,
            {"action": "APPROVED", "at": timezone.now().isoformat(), "by": approved_by_id, "remarks": state["remarks"]},
        )
        h.save(update_fields=["workflow_payload", "updated_at"])
        return PaymentVoucherResult(h, "Approved.")

    @staticmethod
    @transaction.atomic
    def reject_voucher(voucher_id: int, rejected_by_id: Optional[int] = None, remarks: Optional[str] = None) -> PaymentVoucherResult:
        h = PaymentVoucherHeader.objects.select_for_update().get(pk=voucher_id)
        if int(h.status) in (int(PaymentVoucherHeader.Status.POSTED), int(PaymentVoucherHeader.Status.CANCELLED)):
            raise ValueError("Only draft/confirmed vouchers can be rejected.")
        state = PaymentVoucherService._workflow_state(h.workflow_payload)
        state.update({
            "status": "REJECTED",
            "rejected_by": rejected_by_id,
            "rejected_at": timezone.now().isoformat(),
            "remarks": (remarks or "").strip() or None,
        })
        h.workflow_payload = PaymentVoucherService._set_workflow_state(h.workflow_payload, state)
        h.workflow_payload = PaymentVoucherService._append_audit(
            h.workflow_payload,
            {"action": "REJECTED", "at": timezone.now().isoformat(), "by": rejected_by_id, "remarks": state["remarks"]},
        )
        h.save(update_fields=["workflow_payload", "updated_at"])
        return PaymentVoucherResult(h, "Rejected.")

    @staticmethod
    @transaction.atomic
    def post_voucher(voucher_id: int, posted_by_id: Optional[int] = None) -> PaymentVoucherResult:
        h = (
            PaymentVoucherHeader.objects
            .select_related("entity", "entityfinid", "subentity")
            .prefetch_related("allocations", "adjustments", "advance_adjustments")
            .get(pk=voucher_id)
        )
        if int(h.status) == int(PaymentVoucherHeader.Status.CANCELLED):
            raise ValueError("Cannot post: voucher is cancelled.")
        if int(h.status) == int(PaymentVoucherHeader.Status.POSTED):
            return PaymentVoucherResult(h, "Already posted.")

        policy = PaymentSettingsService.get_policy(h.entity_id, h.subentity_id)
        require_confirm = str(policy.controls.get("require_confirm_before_post", "on")).lower().strip() == "on"
        if require_confirm:
            if int(h.status) != int(PaymentVoucherHeader.Status.CONFIRMED):
                raise ValueError("Only CONFIRMED vouchers can be posted.")
        else:
            if int(h.status) not in (int(PaymentVoucherHeader.Status.DRAFT), int(PaymentVoucherHeader.Status.CONFIRMED)):
                raise ValueError("Only DRAFT or CONFIRMED vouchers can be posted.")
            if int(h.status) == int(PaymentVoucherHeader.Status.DRAFT):
                PaymentVoucherService.confirm_voucher(h.id, confirmed_by_id=posted_by_id)
                h.refresh_from_db()

        workflow_state = PaymentVoucherService._workflow_state(h.workflow_payload)
        if str(policy.controls.get("payment_maker_checker", "off")).lower().strip() == "hard":
            if workflow_state.get("status") != "APPROVED":
                raise ValueError("Voucher must be approved before posting by policy.")
        warnings: list[str] = []

        # Recompute monetary totals from live rows before posting so stale draft values
        # do not incorrectly block posting after edits or policy changes.
        live_adjustment_total = PaymentVoucherService._compute_adjustment_total(
            h.adjustments.values("amount", "settlement_effect")
        )
        live_advance_rows = list(h.advance_adjustments.all())
        live_advance_total = PaymentVoucherService._sum_advance_adjustments(
            [{"adjusted_amount": x.adjusted_amount} for x in live_advance_rows]
        )
        live_effective_amount = PaymentVoucherService._effective_settlement_amount(
            q2(h.cash_paid_amount),
            live_adjustment_total,
        )
        if (
            q2(h.total_adjustment_amount) != q2(live_adjustment_total)
            or q2(h.settlement_effective_amount) != q2(live_effective_amount)
        ):
            ex_rate = Decimal(getattr(h, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000"))
            if ex_rate <= 0:
                ex_rate = Decimal("1.000000")
            h.total_adjustment_amount = live_adjustment_total
            h.settlement_effective_amount = live_effective_amount
            h.settlement_effective_amount_base_currency = q2(live_effective_amount * ex_rate)
            h.save(update_fields=[
                "total_adjustment_amount",
                "settlement_effective_amount",
                "settlement_effective_amount_base_currency",
                "updated_at",
            ])

        allocation_rows = PaymentVoucherService._fresh_allocation_rows(h)
        over_settlement_rule = str(policy.controls.get("over_settlement_rule", "block")).lower().strip()
        amount_match_level = str(policy.controls.get("allocation_amount_match_rule", "hard")).lower().strip()
        allocation_policy = str(policy.controls.get("allocation_policy", "manual")).lower().strip()
        effective_amount = live_effective_amount
        total_support_amount = q2(live_effective_amount + live_advance_total)
        # For AGAINST_BILL posting, create missing allocations before enforcing the
        # hard allocation policy. This keeps posting strict while avoiding a separate
        # save-allocation round trip when open items are already available.
        should_auto_allocate = (
            not allocation_rows
            and h.payment_type == PaymentVoucherHeader.PaymentType.AGAINST_BILL
            and total_support_amount > ZERO2
        )
        if should_auto_allocate and allocation_policy not in {"fifo", "manual"}:
            should_auto_allocate = False
        if should_auto_allocate:
            fifo_rows = PaymentVoucherService._auto_fifo_allocations(
                entity_id=h.entity_id,
                entityfinid_id=h.entityfinid_id,
                subentity_id=h.subentity_id,
                vendor_id=h.paid_to_id,
                target_amount=total_support_amount,
                controls=policy.controls,
            )
            for row in fifo_rows:
                PaymentVoucherAllocation.objects.create(
                    payment_voucher=h,
                    open_item_id=row["open_item"],
                    settled_amount=row["settled_amount"],
                    is_full_settlement=bool(row.get("is_full_settlement", False)),
                    is_advance_adjustment=bool(row.get("is_advance_adjustment", False)),
                )
            if fifo_rows:
                allocation_rows = PaymentVoucherService._fresh_allocation_rows(h)

        if str(policy.controls.get("require_allocation_on_post", "hard")).lower().strip() == "hard":
            if h.payment_type == PaymentVoucherHeader.PaymentType.AGAINST_BILL and not allocation_rows:
                raise ValueError("Allocations are required for AGAINST_BILL posting.")
            if (
                h.payment_type == PaymentVoucherHeader.PaymentType.ADVANCE
                and str(policy.controls.get("allow_advance_without_allocation", "on")).lower().strip() == "off"
                and not allocation_rows
            ):
                raise ValueError("Allocations are required for ADVANCE posting by policy.")
            if (
                h.payment_type == PaymentVoucherHeader.PaymentType.ON_ACCOUNT
                and str(policy.controls.get("allow_on_account_without_allocation", "on")).lower().strip() == "off"
                and not allocation_rows
            ):
                raise ValueError("Allocations are required for ON_ACCOUNT posting by policy.")

        if allocation_rows:
            allocation_total = PaymentVoucherService._sum_allocations(
                [{"settled_amount": r.settled_amount} for r in allocation_rows]
            )
            PaymentVoucherService._validate_advance_adjustments(
                voucher=h,
                allocations=[{"open_item": r.open_item_id, "settled_amount": r.settled_amount} for r in allocation_rows],
                advance_adjustments=[
                    {
                        "advance_balance_id": x.advance_balance_id,
                        "allocation": x.allocation_id,
                        "open_item": x.open_item_id,
                        "adjusted_amount": x.adjusted_amount,
                    }
                    for x in live_advance_rows
                ],
            )
            warnings.extend(PaymentVoucherService._validate_allocations(
                h,
                [
                    {"open_item": r.open_item_id, "settled_amount": r.settled_amount}
                    for r in allocation_rows
                ],
                over_settlement_rule=over_settlement_rule,
                controls=policy.controls,
            ))
            try:
                warnings.extend(
                    PaymentVoucherService._validate_allocation_effective_match(
                        effective_amount=total_support_amount,
                        allocation_total=allocation_total,
                        level=amount_match_level,
                    )
                )
            except ValueError:
                raise ValueError(
                    f"Allocation total {q2(allocation_total)} does not match settlement support amount {q2(total_support_amount)} before posting."
                )

        if live_advance_rows and str(policy.controls.get("sync_ap_settlement_on_post", "on")).lower().strip() != "on":
            raise ValueError("Advance adjustments require AP settlement sync to be enabled.")

        if str(policy.controls.get("sync_ap_settlement_on_post", "on")).lower().strip() == "on":
            advance_by_open_item: Dict[int, Decimal] = {}
            for adj in live_advance_rows:
                if not adj.open_item_id:
                    continue
                advance_by_open_item[int(adj.open_item_id)] = q2(
                    advance_by_open_item.get(int(adj.open_item_id), ZERO2) + q2(adj.adjusted_amount)
                )

            if allocation_rows:
                cash_lines = []
                for row in allocation_rows:
                    if not row.open_item_id:
                        continue
                    remaining = q2(row.settled_amount) - q2(advance_by_open_item.get(int(row.open_item_id), ZERO2))
                    if remaining > ZERO2:
                        cash_lines.append({
                            "open_item_id": row.open_item_id,
                            "amount": remaining,
                            "note": "Payment voucher cash allocation",
                        })
                if cash_lines:
                    created = PurchaseApService.create_settlement(
                        entity_id=h.entity_id,
                        entityfinid_id=h.entityfinid_id,
                        subentity_id=h.subentity_id,
                        vendor_id=h.paid_to_id,
                        settlement_type="payment",
                        settlement_date=h.voucher_date,
                        reference_no=h.voucher_code or h.reference_number,
                        external_voucher_no=h.reference_number,
                        remarks=h.narration,
                        lines=cash_lines,
                        amount=None,
                    )
                    posted = PurchaseApService.post_settlement(
                        settlement_id=created.settlement.id,
                        posted_by_id=posted_by_id or h.created_by_id,
                    )
                    h.ap_settlement_id = posted.settlement.id

            for adj in live_advance_rows:
                created = PurchaseApService.create_settlement(
                    entity_id=h.entity_id,
                    entityfinid_id=h.entityfinid_id,
                    subentity_id=h.subentity_id,
                    vendor_id=h.paid_to_id,
                    settlement_type="advance_adjustment",
                    settlement_date=h.voucher_date,
                    reference_no=h.voucher_code or h.reference_number,
                    external_voucher_no=h.reference_number,
                    remarks=adj.remarks or h.narration,
                    lines=[{
                        "open_item_id": adj.open_item_id,
                        "amount": q2(adj.adjusted_amount),
                        "note": "Payment voucher advance adjustment",
                    }],
                    amount=None,
                    advance_balance_id=adj.advance_balance_id,
                )
                posted = PurchaseApService.post_settlement(
                    settlement_id=created.settlement.id,
                    posted_by_id=posted_by_id or h.created_by_id,
                )
                adj.ap_settlement_id = posted.settlement.id
                adj.save(update_fields=["ap_settlement", "updated_at"])

        allocation_total = PaymentVoucherService._sum_allocations(
            [{"settled_amount": r.settled_amount} for r in allocation_rows]
        ) if allocation_rows else ZERO2
        residual_advance = q2(total_support_amount - allocation_total)
        residual_advance = q2(residual_advance - live_advance_total)
        if residual_advance < ZERO2:
            residual_advance = ZERO2
        should_create_advance = (
            str(policy.controls.get("sync_advance_balance_on_post", "on")).lower().strip() == "on"
            and (
                h.payment_type in {PaymentVoucherHeader.PaymentType.ADVANCE, PaymentVoucherHeader.PaymentType.ON_ACCOUNT}
                or (
                    residual_advance > ZERO2
                    and str(policy.controls.get("residual_to_advance_balance", "on")).lower().strip() == "on"
                )
            )
        )
        if should_create_advance:
            source_type = "payment_advance"
            if h.payment_type == PaymentVoucherHeader.PaymentType.ON_ACCOUNT:
                source_type = "on_account"
            adv_amount = effective_amount if h.payment_type in {
                PaymentVoucherHeader.PaymentType.ADVANCE,
                PaymentVoucherHeader.PaymentType.ON_ACCOUNT,
            } else residual_advance
            if adv_amount > ZERO2 and not getattr(h, "vendor_advance_balance", None):
                PurchaseApService.create_advance_balance(
                    entity_id=h.entity_id,
                    entityfinid_id=h.entityfinid_id,
                    subentity_id=h.subentity_id,
                    vendor_id=h.paid_to_id,
                    source_type=source_type,
                    credit_date=h.voucher_date,
                    reference_no=h.voucher_code or h.reference_number,
                    remarks=h.narration,
                    amount=adv_amount,
                    payment_voucher_id=h.id,
                )

        PaymentVoucherPostingAdapter.post_payment_voucher(
            header=h,
            adjustments=h.adjustments.all(),
            user_id=posted_by_id or h.created_by_id,
            config=PaymentVoucherPostingConfig(),
        )

        h.status = PaymentVoucherHeader.Status.POSTED
        h.approved_at = h.approved_at or timezone.now()
        h.workflow_payload = PaymentVoucherService._append_audit(
            h.workflow_payload,
            {"action": "POSTED", "at": timezone.now().isoformat(), "by": posted_by_id or h.created_by_id},
        )
        if posted_by_id and not h.approved_by_id:
            h.approved_by_id = posted_by_id
            h.save(update_fields=["status", "approved_at", "approved_by", "ap_settlement", "workflow_payload", "updated_at"])
        else:
            h.save(update_fields=["status", "approved_at", "ap_settlement", "workflow_payload", "updated_at"])
        msg = "Posted."
        if warnings:
            msg = f"Posted with warnings: {' | '.join(warnings)}"
        return PaymentVoucherResult(h, msg)

    @staticmethod
    @transaction.atomic
    def unpost_voucher(voucher_id: int, unposted_by_id: Optional[int] = None) -> PaymentVoucherResult:
        h = (
            PaymentVoucherHeader.objects
            .select_related("entity", "entityfinid", "subentity")
            .prefetch_related("allocations", "adjustments", "advance_adjustments")
            .get(pk=voucher_id)
        )
        if int(h.status) != int(PaymentVoucherHeader.Status.POSTED):
            raise ValueError("Only POSTED vouchers can be unposted.")

        if h.ap_settlement_id:
            PurchaseApService.cancel_settlement(
                settlement_id=int(h.ap_settlement_id),
                cancelled_by_id=unposted_by_id or h.created_by_id,
            )
            h.ap_settlement_id = None

        for adj in h.advance_adjustments.all():
            if adj.ap_settlement_id:
                PurchaseApService.cancel_settlement(
                    settlement_id=int(adj.ap_settlement_id),
                    cancelled_by_id=unposted_by_id or h.created_by_id,
                )
                adj.ap_settlement_id = None
                adj.save(update_fields=["ap_settlement", "updated_at"])

        if getattr(h, "vendor_advance_balance", None):
            adv = h.vendor_advance_balance
            if adv.is_open or q2(adv.adjusted_amount) == ZERO2:
                adv.is_open = False
                adv.outstanding_amount = ZERO2
                adv.save(update_fields=["is_open", "outstanding_amount", "updated_at"])
            else:
                raise ValueError("Cannot unpost payment voucher: linked advance balance is already adjusted.")

        PaymentVoucherPostingAdapter.unpost_payment_voucher(
            header=h,
            adjustments=h.adjustments.all(),
            user_id=unposted_by_id or h.created_by_id,
        )

        policy = PaymentSettingsService.get_policy(h.entity_id, h.subentity_id)
        unpost_target = str(policy.controls.get("unpost_target_status", "confirmed")).lower().strip()
        h.status = (
            PaymentVoucherHeader.Status.DRAFT
            if unpost_target == "draft"
            else PaymentVoucherHeader.Status.CONFIRMED
        )
        h.workflow_payload = PaymentVoucherService._append_audit(
            h.workflow_payload,
            {"action": "UNPOSTED", "at": timezone.now().isoformat(), "by": unposted_by_id or h.created_by_id},
        )
        h.save(update_fields=["status", "ap_settlement", "workflow_payload", "updated_at"])
        return PaymentVoucherResult(h, "Unposted with reversal entry.")

    @staticmethod
    @transaction.atomic
    def cancel_voucher(voucher_id: int, reason: Optional[str] = None, cancelled_by_id: Optional[int] = None) -> PaymentVoucherResult:
        h = PaymentVoucherHeader.objects.get(pk=voucher_id)
        if int(h.status) == int(PaymentVoucherHeader.Status.POSTED):
            raise ValueError("Posted voucher cannot be cancelled in Phase-1.")
        if int(h.status) == int(PaymentVoucherHeader.Status.CANCELLED):
            return PaymentVoucherResult(h, "Already cancelled.")
        h.status = PaymentVoucherHeader.Status.CANCELLED
        h.is_cancelled = True
        h.cancel_reason = (reason or "").strip() or None
        h.cancelled_by_id = cancelled_by_id
        h.cancelled_at = timezone.now()
        h.workflow_payload = PaymentVoucherService._append_audit(
            h.workflow_payload,
            {"action": "CANCELLED", "at": timezone.now().isoformat(), "by": cancelled_by_id, "reason": h.cancel_reason},
        )
        h.save(update_fields=["status", "is_cancelled", "cancel_reason", "cancelled_by", "cancelled_at", "workflow_payload", "updated_at"])
        return PaymentVoucherResult(h, "Cancelled.")
