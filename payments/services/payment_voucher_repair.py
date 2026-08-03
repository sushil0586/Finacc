from __future__ import annotations

from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db import transaction

from payments.models import PaymentVoucherAllocation, PaymentVoucherHeader
from purchase.services.purchase_ap_service import PurchaseApService
from purchase.models.purchase_ap import VendorSettlementLine

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value: Any) -> Decimal:
    try:
        return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


@dataclass
class PaymentVoucherRepairRow:
    voucher_id: int
    voucher_code: str
    entity_id: int
    subentity_id: int | None
    vendor_id: int
    payment_type: str
    ap_settlement_id: int | None
    advance_balance_id: int | None
    cash_paid_amount: Decimal
    adjustment_total: Decimal
    effective_amount: Decimal
    advance_total: Decimal
    created_advance_total: Decimal
    support_total: Decimal
    distribution_total: Decimal
    allocation_total: Decimal
    settlement_total: Decimal
    mismatch_kind: str
    repairable: bool
    repair_action: str
    note: str


def audit_posted_payment_voucher_settlement_mismatches(
    *,
    entity_id: int | None = None,
    subentity_id: int | None = None,
    voucher_id: int | None = None,
    voucher_code: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    queryset = (
        PaymentVoucherHeader.objects
        .filter(status=PaymentVoucherHeader.Status.POSTED)
        .select_related("vendor_advance_balance")
        .prefetch_related("allocations", "adjustments", "advance_adjustments")
        .order_by("id")
    )

    if entity_id:
        queryset = queryset.filter(entity_id=entity_id)
    if subentity_id:
        queryset = queryset.filter(subentity_id=subentity_id)
    if voucher_id:
        queryset = queryset.filter(id=voucher_id)
    if voucher_code:
        queryset = queryset.filter(voucher_code=voucher_code)

    summary: dict[str, Any] = {
        "scanned_vouchers": 0,
        "flagged_vouchers": 0,
        "repaired_vouchers": 0,
        "allocation_repairs": 0,
        "rows": [],
    }

    for voucher in queryset.iterator(chunk_size=200):
        summary["scanned_vouchers"] += 1

        adjustment_total = q2(getattr(voucher, "total_adjustment_amount", ZERO2))
        effective_amount = q2(getattr(voucher, "settlement_effective_amount", ZERO2))
        advance_total = q2(sum((q2(x.adjusted_amount) for x in voucher.advance_adjustments.all()), start=ZERO2))
        created_advance_total = q2(getattr(getattr(voucher, "vendor_advance_balance", None), "original_amount", ZERO2))
        support_total = q2(effective_amount + advance_total)
        allocation_rows = list(voucher.allocations.all())
        allocation_total = q2(sum((q2(x.settled_amount) for x in allocation_rows), start=ZERO2))
        distribution_total = q2(allocation_total + created_advance_total)

        settlement_total = ZERO2
        if getattr(voucher, "ap_settlement_id", None):
            settlement_total = q2(
                sum(
                    (
                        q2(x.amount)
                        for x in VendorSettlementLine.objects.filter(settlement_id=voucher.ap_settlement_id).only("amount")
                    ),
                    start=ZERO2,
                )
            )

        mismatch_kind = "ok"
        repairable = False
        repair_action = ""
        note = ""

        expected_cash_settlement_total = q2(allocation_total - advance_total)
        if expected_cash_settlement_total < ZERO2:
            expected_cash_settlement_total = ZERO2

        distribution_matches = distribution_total == support_total
        settlement_matches = settlement_total == expected_cash_settlement_total

        if distribution_matches and settlement_matches:
            pass
        else:
            if not distribution_matches and settlement_matches:
                mismatch_kind = "distribution_mismatch"
                note = (
                    "Voucher support does not match the distributed total across allocations and linked advance balance. "
                    "Business intent is ambiguous; manual review required."
                )
                if (
                    advance_total == ZERO2
                    and created_advance_total == ZERO2
                    and support_total == settlement_total
                    and allocation_total != settlement_total
                ):
                    repairable = True
                    repair_action = "sync_allocations_from_settlement"
                    note = (
                        "Header support matches posted cash settlement, but saved allocation rows differ. "
                        "Allocation rows can be synchronized from posted settlement lines."
                    )
                elif (
                    str(voucher.payment_type) == str(PaymentVoucherHeader.PaymentType.ON_ACCOUNT)
                    and support_total > ZERO2
                    and allocation_total == ZERO2
                    and settlement_total == ZERO2
                    and created_advance_total == ZERO2
                    and getattr(voucher, "ap_settlement_id", None) is None
                ):
                    repairable = True
                    repair_action = "create_missing_advance_balance"
                    note = (
                        "Posted on-account voucher has support but no allocations, no AP settlement, and no linked "
                        "vendor advance balance. A missing advance balance can be created safely."
                    )
                elif (
                    str(voucher.payment_type) == str(PaymentVoucherHeader.PaymentType.AGAINST_BILL)
                    and support_total > allocation_total > ZERO2
                    and settlement_total == allocation_total
                    and advance_total == ZERO2
                    and created_advance_total == ZERO2
                    and getattr(voucher, "ap_settlement_id", None) is not None
                ):
                    repairable = True
                    repair_action = "create_residual_advance_balance"
                    note = (
                        "Posted against-bill voucher has settled cash equal to allocation total, but the remaining "
                        "voucher support is undistributed. The residual can be created as a linked vendor advance balance."
                    )
            elif distribution_matches and not settlement_matches:
                mismatch_kind = "cash_settlement_mismatch"
                repairable = False
                repair_action = ""
                note = (
                    "Distributed voucher support is internally consistent, but posted AP cash settlement differs "
                    "from allocation total after advance consumption. Manual review required."
                )
            else:
                mismatch_kind = "compound_mismatch"
                note = (
                    "Voucher support distribution and posted AP cash settlement both differ. "
                    "Business intent is ambiguous; manual review required."
                )

            summary["flagged_vouchers"] += 1

        row = PaymentVoucherRepairRow(
            voucher_id=voucher.id,
            voucher_code=str(voucher.voucher_code or ""),
            entity_id=int(voucher.entity_id),
            subentity_id=voucher.subentity_id,
            vendor_id=int(voucher.paid_to_id),
            payment_type=str(voucher.payment_type),
            ap_settlement_id=getattr(voucher, "ap_settlement_id", None),
            advance_balance_id=getattr(voucher, "vendor_advance_balance_id", None),
            cash_paid_amount=q2(voucher.cash_paid_amount),
            adjustment_total=adjustment_total,
            effective_amount=effective_amount,
            advance_total=advance_total,
            created_advance_total=created_advance_total,
            support_total=support_total,
            distribution_total=distribution_total,
            allocation_total=allocation_total,
            settlement_total=settlement_total,
            mismatch_kind=mismatch_kind,
            repairable=repairable,
            repair_action=repair_action,
            note=note,
        )
        summary["rows"].append(row)

        if not apply or not repairable:
            continue

        if repair_action == "sync_allocations_from_settlement":
            if not voucher.ap_settlement_id:
                row.repairable = False
                row.note = "Voucher has no linked AP settlement; cannot auto-sync allocations."
                continue

            settlement_lines = list(
                VendorSettlementLine.objects.filter(settlement_id=voucher.ap_settlement_id)
                .only("open_item_id", "amount")
                .order_by("id")
            )
            if not settlement_lines:
                row.repairable = False
                row.note = "Linked AP settlement has no lines; cannot auto-sync allocations."
                continue

            with transaction.atomic():
                PaymentVoucherAllocation.objects.filter(payment_voucher_id=voucher.id).delete()
                for line in settlement_lines:
                    PaymentVoucherAllocation.objects.create(
                        payment_voucher=voucher,
                        open_item_id=line.open_item_id,
                        settled_amount=q2(line.amount),
                        is_full_settlement=False,
                        is_advance_adjustment=False,
                    )
                summary["repaired_vouchers"] += 1
                summary["allocation_repairs"] += len(settlement_lines)

            row.allocation_total = q2(sum((q2(x.amount) for x in settlement_lines), start=ZERO2))
            row.distribution_total = q2(row.allocation_total + row.created_advance_total)
            row.mismatch_kind = "repaired_allocation_vs_settlement"
            row.note = "Allocation rows synchronized from linked AP settlement lines."
        elif repair_action == "create_missing_advance_balance":
            with transaction.atomic():
                adv = PurchaseApService.create_advance_balance(
                    entity_id=voucher.entity_id,
                    entityfinid_id=voucher.entityfinid_id,
                    subentity_id=voucher.subentity_id,
                    vendor_id=voucher.paid_to_id,
                    source_type="on_account",
                    credit_date=voucher.voucher_date,
                    reference_no=voucher.voucher_code or voucher.reference_number,
                    remarks=voucher.narration,
                    amount=support_total,
                    payment_voucher_id=voucher.id,
                )
                summary["repaired_vouchers"] += 1
            row.created_advance_total = q2(getattr(adv, "original_amount", ZERO2))
            row.distribution_total = q2(row.allocation_total + row.created_advance_total)
            row.mismatch_kind = "repaired_missing_advance_balance"
            row.note = "Missing vendor advance balance created and linked to payment voucher."
        elif repair_action == "create_residual_advance_balance":
            residual_amount = q2(support_total - allocation_total)
            if residual_amount <= ZERO2:
                row.repairable = False
                row.note = "Residual amount is not positive; cannot create vendor advance balance."
                continue
            with transaction.atomic():
                adv = PurchaseApService.create_advance_balance(
                    entity_id=voucher.entity_id,
                    entityfinid_id=voucher.entityfinid_id,
                    subentity_id=voucher.subentity_id,
                    vendor_id=voucher.paid_to_id,
                    source_type="payment_advance",
                    credit_date=voucher.voucher_date,
                    reference_no=voucher.voucher_code or voucher.reference_number,
                    remarks=voucher.narration,
                    amount=residual_amount,
                    payment_voucher_id=voucher.id,
                )
                summary["repaired_vouchers"] += 1
            row.created_advance_total = q2(getattr(adv, "original_amount", ZERO2))
            row.distribution_total = q2(row.allocation_total + row.created_advance_total)
            row.mismatch_kind = "repaired_residual_advance_balance"
            row.note = "Residual vendor advance balance created for undistributed against-bill payment support."

    summary["rows"] = [asdict(x) for x in summary["rows"]]
    return summary
