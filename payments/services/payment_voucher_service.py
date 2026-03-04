from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from django.db import transaction
from django.utils import timezone

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from purchase.services.purchase_ap_service import PurchaseApService
from purchase.models.purchase_ap import VendorBillOpenItem
from posting.adapters.payment_voucher import PaymentVoucherPostingAdapter, PaymentVoucherPostingConfig

from payments.models.payment_core import (
    PaymentVoucherHeader,
    PaymentVoucherAllocation,
    PaymentVoucherAdjustment,
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
    def _sum_allocations(allocations: Iterable[Dict[str, Any]]) -> Decimal:
        total = ZERO2
        for row in allocations or []:
            total = q2(total + q2(row.get("settled_amount") or ZERO2))
        return total

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
        voucher: PaymentVoucherHeader, allocations: List[Dict[str, Any]], over_settlement_rule: str = "block"
    ) -> list[str]:
        warnings: list[str] = []
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

            if over_settlement_rule == "block":
                outstanding = q2(open_item.outstanding_amount)
                if amt > outstanding:
                    raise ValueError(
                        f"Allocation row {i}: settled_amount {amt} exceeds outstanding {outstanding} for open_item {open_item_id}."
                    )
            elif over_settlement_rule == "warn":
                outstanding = q2(open_item.outstanding_amount)
                if amt > outstanding:
                    warnings.append(
                        f"Allocation row {i}: settled_amount {amt} exceeds outstanding {outstanding} for open_item {open_item_id}."
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
    ) -> List[Dict[str, Any]]:
        remaining = q2(target_amount)
        if remaining <= ZERO2:
            return []
        rows: List[Dict[str, Any]] = []
        qs = (
            PurchaseApService.list_open_items(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                vendor_id=vendor_id,
                is_open=True,
            )
            .filter(outstanding_amount__gt=ZERO2)
            .order_by("due_date", "bill_date", "id")
        )
        for item in qs:
            if remaining <= ZERO2:
                break
            can = min(q2(item.outstanding_amount), remaining)
            if can <= ZERO2:
                continue
            rows.append(
                {
                    "open_item": item.id,
                    "settled_amount": can,
                    "is_full_settlement": can >= q2(item.outstanding_amount),
                    "is_advance_adjustment": False,
                }
            )
            remaining = q2(remaining - can)
        return rows

    @staticmethod
    @transaction.atomic
    def create_voucher(validated_data: Dict[str, Any]) -> PaymentVoucherHeader:
        allocations = validated_data.pop("allocations", []) or []
        adjustments = validated_data.pop("adjustments", []) or []

        policy = PaymentSettingsService.get_policy(
            validated_data["entity"].id if hasattr(validated_data.get("entity"), "id") else validated_data.get("entity"),
            validated_data.get("subentity").id if hasattr(validated_data.get("subentity"), "id") else validated_data.get("subentity"),
        )

        if int(validated_data.get("status", PaymentVoucherHeader.Status.DRAFT)) != int(PaymentVoucherHeader.Status.DRAFT):
            validated_data["status"] = PaymentVoucherHeader.Status.DRAFT

        adjustment_total = PaymentVoucherService._compute_adjustment_total(adjustments)
        effective = PaymentVoucherService._effective_settlement_amount(
            q2(validated_data.get("cash_paid_amount", ZERO2)),
            adjustment_total,
        )
        validated_data["total_adjustment_amount"] = adjustment_total
        validated_data["settlement_effective_amount"] = effective

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
            )

        amount_match_level = str(policy.controls.get("allocation_amount_match_rule", "hard")).lower().strip()
        if allocations:
            PaymentVoucherService._validate_allocation_effective_match(
                effective_amount=effective,
                allocation_total=PaymentVoucherService._sum_allocations(allocations),
                level=amount_match_level,
            )

        header = PaymentVoucherHeader.objects.create(**validated_data)

        over_settlement_rule = str(policy.controls.get("over_settlement_rule", "block")).lower().strip()
        if allocations:
            PaymentVoucherService._validate_allocations(header, allocations, over_settlement_rule=over_settlement_rule)

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
                amount=q2(row.get("amount") or ZERO2),
                settlement_effect=row.get("settlement_effect") or PaymentVoucherAdjustment.Effect.PLUS,
                remarks=(row.get("remarks") or "").strip() or None,
            )

        PaymentVoucherService._validate_adjustment_allocation_links(voucher_id=header.id, adjustments=adjustments)

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
        policy = PaymentSettingsService.get_policy(instance.entity_id, instance.subentity_id)
        over_settlement_rule = str(policy.controls.get("over_settlement_rule", "block")).lower().strip()
        amount_match_level = str(policy.controls.get("allocation_amount_match_rule", "hard")).lower().strip()

        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        if allocations is not None:
            PaymentVoucherService._validate_allocations(instance, allocations, over_settlement_rule=over_settlement_rule)
            PaymentVoucherService._validate_allocation_effective_match(
                effective_amount=PaymentVoucherService._effective_settlement_amount(
                    q2(validated_data.get("cash_paid_amount", instance.cash_paid_amount)),
                    PaymentVoucherService._compute_adjustment_total(
                        adjustments
                        if adjustments is not None
                        else instance.adjustments.values("amount", "settlement_effect")
                    ),
                ),
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
                        amount=q2(row.get("amount") or ZERO2),
                        settlement_effect=row.get("settlement_effect") or PaymentVoucherAdjustment.Effect.PLUS,
                        remarks=(row.get("remarks") or "").strip() or None,
                    )
                    seen.add(obj.id)
            for rid, obj in existing.items():
                if rid not in seen:
                    obj.delete()
            PaymentVoucherService._validate_adjustment_allocation_links(voucher_id=instance.id, adjustments=adjustments)

        adjustment_total = PaymentVoucherService._compute_adjustment_total(
            instance.adjustments.values("amount", "settlement_effect")
        )
        instance.total_adjustment_amount = adjustment_total
        instance.settlement_effective_amount = PaymentVoucherService._effective_settlement_amount(
            q2(instance.cash_paid_amount),
            adjustment_total,
        )
        instance.save(update_fields=["total_adjustment_amount", "settlement_effective_amount", "updated_at"])
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
    def post_voucher(voucher_id: int, posted_by_id: Optional[int] = None) -> PaymentVoucherResult:
        h = (
            PaymentVoucherHeader.objects
            .select_related("entity", "entityfinid", "subentity")
            .prefetch_related("allocations", "adjustments")
            .get(pk=voucher_id)
        )
        if int(h.status) == int(PaymentVoucherHeader.Status.CANCELLED):
            raise ValueError("Cannot post: voucher is cancelled.")
        if int(h.status) == int(PaymentVoucherHeader.Status.POSTED):
            return PaymentVoucherResult(h, "Already posted.")
        if int(h.status) != int(PaymentVoucherHeader.Status.CONFIRMED):
            raise ValueError("Only CONFIRMED vouchers can be posted.")

        policy = PaymentSettingsService.get_policy(h.entity_id, h.subentity_id)
        warnings: list[str] = []

        allocation_rows = list(h.allocations.all())
        if str(policy.controls.get("require_allocation_on_post", "hard")).lower().strip() == "hard":
            if h.payment_type == PaymentVoucherHeader.PaymentType.AGAINST_BILL and not allocation_rows:
                raise ValueError("Allocations are required for AGAINST_BILL posting.")
            if (
                h.payment_type == PaymentVoucherHeader.PaymentType.ADVANCE
                and str(policy.controls.get("allow_advance_without_allocation", "on")).lower().strip() == "off"
                and not allocation_rows
            ):
                raise ValueError("Allocations are required for ADVANCE posting by policy.")

        over_settlement_rule = str(policy.controls.get("over_settlement_rule", "block")).lower().strip()
        amount_match_level = str(policy.controls.get("allocation_amount_match_rule", "hard")).lower().strip()
        allocation_policy = str(policy.controls.get("allocation_policy", "manual")).lower().strip()
        effective_amount = PaymentVoucherService._effective_settlement_amount(
            q2(h.cash_paid_amount),
            q2(h.total_adjustment_amount),
        )
        if not allocation_rows and allocation_policy == "fifo" and h.payment_type == PaymentVoucherHeader.PaymentType.AGAINST_BILL:
            fifo_rows = PaymentVoucherService._auto_fifo_allocations(
                entity_id=h.entity_id,
                entityfinid_id=h.entityfinid_id,
                subentity_id=h.subentity_id,
                vendor_id=h.paid_to_id,
                target_amount=effective_amount,
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
                allocation_rows = list(h.allocations.all())

        if allocation_rows:
            warnings.extend(PaymentVoucherService._validate_allocations(h, [
                {"open_item": r.open_item_id, "settled_amount": r.settled_amount}
                for r in allocation_rows
            ], over_settlement_rule=over_settlement_rule))
            warnings.extend(
                PaymentVoucherService._validate_allocation_effective_match(
                    effective_amount=effective_amount,
                    allocation_total=PaymentVoucherService._sum_allocations(
                        [{"settled_amount": r.settled_amount} for r in allocation_rows]
                    ),
                    level=amount_match_level,
                )
            )

        if str(policy.controls.get("sync_ap_settlement_on_post", "on")).lower().strip() == "on":
            if allocation_rows:
                lines = []
                for row in allocation_rows:
                    if not row.open_item_id:
                        continue
                    lines.append({"open_item_id": row.open_item_id, "amount": q2(row.settled_amount), "note": "Payment voucher allocation"})
                if lines:
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
                        lines=lines,
                        amount=None,
                    )
                    posted = PurchaseApService.post_settlement(
                        settlement_id=created.settlement.id,
                        posted_by_id=posted_by_id or h.created_by_id,
                    )
                    h.ap_settlement_id = posted.settlement.id

        PaymentVoucherPostingAdapter.post_payment_voucher(
            header=h,
            adjustments=h.adjustments.all(),
            user_id=posted_by_id or h.created_by_id,
            config=PaymentVoucherPostingConfig(),
        )

        h.status = PaymentVoucherHeader.Status.POSTED
        h.approved_at = h.approved_at or timezone.now()
        if posted_by_id and not h.approved_by_id:
            h.approved_by_id = posted_by_id
            h.save(update_fields=["status", "approved_at", "approved_by", "ap_settlement", "updated_at"])
        else:
            h.save(update_fields=["status", "approved_at", "ap_settlement", "updated_at"])
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
            .prefetch_related("allocations", "adjustments")
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

        PaymentVoucherPostingAdapter.unpost_payment_voucher(
            header=h,
            adjustments=h.adjustments.all(),
            user_id=unposted_by_id or h.created_by_id,
        )

        h.status = PaymentVoucherHeader.Status.CONFIRMED
        h.save(update_fields=["status", "ap_settlement", "updated_at"])
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
        h.save(update_fields=["status", "is_cancelled", "cancel_reason", "cancelled_by", "cancelled_at", "updated_at"])
        return PaymentVoucherResult(h, "Cancelled.")
