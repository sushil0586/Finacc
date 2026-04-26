from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from financial.models import account
from receipts.models.receipt_core import ReceiptVoucherHeader
from sales.models.sales_ar import (
    CustomerBillOpenItem,
    CustomerAdvanceBalance,
    CustomerSettlement,
    CustomerSettlementLine,
)
from sales.models.sales_core import SalesInvoiceHeader
from sales.services.sales_settings_service import SalesSettingsService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")
TOL = Decimal("0.01")


def q2(x) -> Decimal:
    return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class SettlementCreateResult:
    settlement: CustomerSettlement
    message: str


@dataclass(frozen=True)
class SettlementPostResult:
    settlement: CustomerSettlement
    applied_total: Decimal
    message: str


@dataclass(frozen=True)
class SettlementCancelResult:
    settlement: CustomerSettlement
    message: str


class SalesArService:
    @staticmethod
    def _get_policy(entity_id: int, subentity_id: Optional[int], entityfinid_id: Optional[int] = None):
        return SalesSettingsService.get_policy(entity_id, subentity_id, entityfinid_id=entityfinid_id)

    @staticmethod
    def _resolve_customer_ledger_id(customer_id: Optional[int]) -> Optional[int]:
        if not customer_id:
            return None
        customer = account.objects.filter(id=customer_id).only("id", "ledger_id").first()
        if not customer:
            raise ValueError("Selected customer account does not exist.")
        if not getattr(customer, "ledger_id", None):
            raise ValueError("Selected customer account does not have a linked ledger.")
        return int(customer.ledger_id)

    @staticmethod
    def _sync_header_from_open_item(item: CustomerBillOpenItem) -> None:
        header = getattr(item, "header", None)
        if not header:
            return
        header.settled_amount = q2(item.settled_amount)
        header.outstanding_amount = q2(item.outstanding_amount)
        if abs(q2(item.outstanding_amount)) <= TOL:
            header.settlement_status = SalesInvoiceHeader.SettlementStatus.SETTLED
        elif abs(q2(item.settled_amount)) > TOL:
            header.settlement_status = SalesInvoiceHeader.SettlementStatus.PARTIAL
        else:
            header.settlement_status = SalesInvoiceHeader.SettlementStatus.OPEN
        header.save(update_fields=["settled_amount", "outstanding_amount", "settlement_status", "updated_at"])

    @staticmethod
    def close_open_item_for_header(header: SalesInvoiceHeader) -> None:
        item = CustomerBillOpenItem.objects.filter(header=header).first()
        if not item:
            return
        item.is_open = False
        item.outstanding_amount = ZERO2
        item.last_settled_at = timezone.now()
        item.save(update_fields=["is_open", "outstanding_amount", "last_settled_at", "updated_at"])

    @staticmethod
    @transaction.atomic
    def create_advance_balance(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        customer_id: int,
        source_type: str,
        credit_date: date,
        reference_no: Optional[str],
        remarks: Optional[str],
        amount: Decimal,
        receipt_voucher_id: Optional[int] = None,
    ) -> CustomerAdvanceBalance:
        amt = q2(amount)
        if amt <= ZERO2:
            raise ValueError("Advance balance amount must be > 0.")
        customer_ledger_id = SalesArService._resolve_customer_ledger_id(customer_id)
        return CustomerAdvanceBalance.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
            customer_ledger_id=customer_ledger_id,
            source_type=source_type,
            credit_date=credit_date,
            reference_no=(reference_no or "").strip() or None,
            remarks=(remarks or "").strip() or None,
            original_amount=amt,
            adjusted_amount=ZERO2,
            outstanding_amount=amt,
            is_open=True,
            receipt_voucher_id=receipt_voucher_id,
        )

    @staticmethod
    def list_open_advances(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        customer_id: Optional[int] = None,
        is_open: Optional[bool] = True,
    ) -> QuerySet[CustomerAdvanceBalance]:
        qs = CustomerAdvanceBalance.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        qs = qs.exclude(receipt_voucher__status=ReceiptVoucherHeader.Status.CANCELLED)
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        if is_open is not None:
            qs = qs.filter(is_open=is_open)
        return qs.order_by("credit_date", "id")

    @staticmethod
    def _auto_adjust_credit_note_if_enabled(*, header: SalesInvoiceHeader, cn_item: CustomerBillOpenItem) -> None:
        policy = SalesArService._get_policy(header.entity_id, header.subentity_id, header.entityfinid_id)
        controls = getattr(policy, "controls", {}) or {}
        if str(controls.get("auto_adjust_credit_notes", "off")).lower().strip() != "on":
            return
        if int(header.doc_type) != int(SalesInvoiceHeader.DocType.CREDIT_NOTE):
            return
        if not getattr(header, "original_invoice_id", None):
            return

        marker = f"AUTO-CN-{header.id}"
        if CustomerSettlement.objects.filter(
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            subentity_id=header.subentity_id,
            customer_id=header.customer_id,
            reference_no=marker,
            status=CustomerSettlement.Status.POSTED,
        ).exists():
            return

        target = CustomerBillOpenItem.objects.filter(
            header_id=header.original_invoice_id,
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            customer_id=header.customer_id,
            is_open=True,
            outstanding_amount__gt=ZERO2,
        ).first()
        if not target:
            return

        cn_available = q2(abs(cn_item.outstanding_amount))
        if cn_available <= ZERO2:
            return
        apply_abs = min(q2(target.outstanding_amount), cn_available)
        if apply_abs <= ZERO2:
            return

        create_res = SalesArService.create_settlement(
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            subentity_id=header.subentity_id,
            customer_id=header.customer_id,
            settlement_type=CustomerSettlement.SettlementType.CREDIT_NOTE_ADJUSTMENT,
            settlement_date=header.bill_date,
            reference_no=marker,
            external_voucher_no=header.invoice_number,
            remarks="Auto credit-note adjustment",
            lines=[
                {"open_item_id": target.id, "amount": apply_abs, "note": "Adjusted against credit note"},
                {"open_item_id": cn_item.id, "amount": apply_abs, "note": "Credit note consumption"},
            ],
            amount=None,
        )
        SalesArService.post_settlement(settlement_id=create_res.settlement.id, posted_by_id=None)

    @staticmethod
    def _doc_sign(doc_type: int) -> Decimal:
        # Invoice / DN positive receivable, CN negative receivable
        if int(doc_type) == int(SalesInvoiceHeader.DocType.CREDIT_NOTE):
            return Decimal("-1")
        return Decimal("1")

    @staticmethod
    @transaction.atomic
    def sync_open_item_for_header(header: SalesInvoiceHeader) -> CustomerBillOpenItem:
        """
        Create/update AR open item from posted sales header.
        Idempotent and safe to call multiple times.
        """
        sign = SalesArService._doc_sign(int(header.doc_type))
        gross_amount = q2(sign * q2(getattr(header, "grand_total", ZERO2)))
        tds_collected = ZERO2
        gst_tds_collected = q2(sign * q2(getattr(header, "tcs_amount", ZERO2)))
        net_receivable = gross_amount

        item, _ = CustomerBillOpenItem.objects.select_for_update().get_or_create(
            header=header,
            defaults={
                "entity_id": header.entity_id,
                "entityfinid_id": header.entityfinid_id,
                "subentity_id": header.subentity_id,
                "customer_id": header.customer_id,
                "customer_ledger_id": header.customer_ledger_id,
                "doc_type": int(header.doc_type),
                "bill_date": header.bill_date,
                "due_date": header.due_date,
                "invoice_number": header.invoice_number,
                "customer_reference_number": header.reference,
                "original_amount": net_receivable,
                "gross_amount": gross_amount,
                "tds_collected": tds_collected,
                "gst_tds_collected": gst_tds_collected,
                "net_receivable_amount": net_receivable,
                "settled_amount": ZERO2,
                "outstanding_amount": net_receivable,
                "is_open": abs(net_receivable) > TOL,
            },
        )

        # Keep snapshot fields fresh; preserve already-applied settlements.
        item.entity_id = header.entity_id
        item.entityfinid_id = header.entityfinid_id
        item.subentity_id = header.subentity_id
        item.customer_id = header.customer_id
        item.customer_ledger_id = header.customer_ledger_id
        item.doc_type = int(header.doc_type)
        item.bill_date = header.bill_date
        item.due_date = header.due_date
        item.invoice_number = header.invoice_number
        item.customer_reference_number = header.reference
        item.original_amount = net_receivable
        item.gross_amount = gross_amount
        item.tds_collected = tds_collected
        item.gst_tds_collected = gst_tds_collected
        item.net_receivable_amount = net_receivable
        item.outstanding_amount = q2(item.original_amount - q2(item.settled_amount))
        if abs(item.outstanding_amount) <= TOL:
            item.outstanding_amount = ZERO2
            item.is_open = False
        else:
            item.is_open = True
        item.save()

        SalesArService._auto_adjust_credit_note_if_enabled(header=header, cn_item=item)
        return item

    @staticmethod
    def list_open_items(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        customer_id: Optional[int] = None,
        is_open: Optional[bool] = True,
    ) -> QuerySet[CustomerBillOpenItem]:
        qs = CustomerBillOpenItem.objects.select_related("header").filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        qs = qs.exclude(header__status=SalesInvoiceHeader.Status.CANCELLED)
        if is_open is not None:
            qs = qs.filter(is_open=is_open)
        return qs.order_by("due_date", "bill_date", "id")

    @staticmethod
    def _auto_fifo_lines(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        customer_id: int,
        amount: Decimal,
    ) -> List[Dict[str, Any]]:
        remaining = q2(amount)
        if remaining <= ZERO2:
            return []

        # FIFO only against positive outstanding invoices.
        qs = SalesArService.list_open_items(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
            is_open=True,
        ).filter(outstanding_amount__gt=ZERO2)

        out: List[Dict[str, Any]] = []
        for item in qs:
            if remaining <= ZERO2:
                break
            can = min(q2(item.outstanding_amount), remaining)
            if can <= ZERO2:
                continue
            out.append({"open_item_id": item.id, "amount": can})
            remaining = q2(remaining - can)
        return out

    @staticmethod
    @transaction.atomic
    def create_settlement(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        customer_id: int,
        settlement_type: str,
        settlement_date: date,
        reference_no: Optional[str],
        external_voucher_no: Optional[str],
        remarks: Optional[str],
        lines: Optional[Iterable[Dict[str, Any]]] = None,
        amount: Optional[Decimal] = None,
        advance_balance_id: Optional[int] = None,
    ) -> SettlementCreateResult:
        lines_data = list(lines or [])
        policy = SalesArService._get_policy(entity_id, subentity_id, entityfinid_id)
        controls = getattr(policy, "controls", {}) or {}
        settlement_mode = str(controls.get("settlement_mode", "basic")).lower().strip()
        allocation_policy = str(controls.get("allocation_policy", "manual")).lower().strip()
        if settlement_mode == "off":
            raise ValueError("Settlement is disabled by sales policy.")
        customer_ledger_id = SalesArService._resolve_customer_ledger_id(customer_id)
        if not lines_data:
            if q2(amount or ZERO2) > ZERO2 and allocation_policy == "fifo":
                lines_data = SalesArService._auto_fifo_lines(
                    entity_id=entity_id,
                    entityfinid_id=entityfinid_id,
                    subentity_id=subentity_id,
                    customer_id=customer_id,
                    amount=q2(amount or ZERO2),
                )
            if not lines_data:
                raise ValueError("Provide settlement lines (or amount with FIFO policy).")

        settlement = CustomerSettlement.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
            customer_ledger_id=customer_ledger_id,
            settlement_type=settlement_type,
            settlement_date=settlement_date,
            reference_no=(reference_no or "").strip() or None,
            external_voucher_no=(external_voucher_no or "").strip() or None,
            remarks=(remarks or "").strip() or None,
            advance_balance_id=advance_balance_id,
            total_amount=ZERO2,
            status=CustomerSettlement.Status.DRAFT,
        )

        total = ZERO2
        for idx, row in enumerate(lines_data, start=1):
            open_item_id = int(row.get("open_item_id") or 0)
            amt = q2(row.get("amount") or ZERO2)
            if open_item_id <= 0:
                raise ValueError(f"Line {idx}: open_item_id is required.")
            if amt <= ZERO2:
                raise ValueError(f"Line {idx}: amount must be > 0.")

            open_item = CustomerBillOpenItem.objects.filter(
                id=open_item_id,
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                customer_id=customer_id,
            ).first()
            if not open_item:
                raise ValueError(f"Line {idx}: open_item not found in selected scope/customer.")

            CustomerSettlementLine.objects.create(
                settlement=settlement,
                open_item=open_item,
                amount=amt,
                note=(row.get("note") or "").strip() or None,
            )
            total = q2(total + amt)

        settlement.total_amount = total
        settlement.save(update_fields=["total_amount"])
        return SettlementCreateResult(settlement=settlement, message="Settlement created as draft.")

    @staticmethod
    @transaction.atomic
    def post_settlement(*, settlement_id: int, posted_by_id: Optional[int] = None) -> SettlementPostResult:
        settlement = CustomerSettlement.objects.select_for_update().get(pk=settlement_id)
        if int(settlement.status) == int(CustomerSettlement.Status.POSTED):
            return SettlementPostResult(settlement=settlement, applied_total=q2(settlement.total_amount), message="Settlement already posted.")
        if int(settlement.status) == int(CustomerSettlement.Status.CANCELLED):
            raise ValueError("Cancelled settlement cannot be posted.")

        policy = SalesArService._get_policy(settlement.entity_id, settlement.subentity_id, settlement.entityfinid_id)
        controls = getattr(policy, "controls", {}) or {}
        over_rule = str(controls.get("over_settlement_rule", "block")).lower().strip()

        lines = list(
            settlement.lines.select_related("open_item")
            .select_for_update()
            .order_by("id")
        )
        if not lines:
            raise ValueError("Settlement has no lines.")

        applied_total = ZERO2
        advance_balance = None
        available_advance = ZERO2
        if settlement.advance_balance_id:
            advance_balance = CustomerAdvanceBalance.objects.select_for_update().get(pk=settlement.advance_balance_id)
            available_advance = q2(advance_balance.outstanding_amount)
        for ln in lines:
            item = ln.open_item
            if not item.is_open or abs(q2(item.outstanding_amount)) <= TOL:
                if over_rule == "block":
                    raise ValueError(f"Open item {item.id} is already settled.")
                continue

            remaining_abs = q2(abs(item.outstanding_amount))
            requested_abs = q2(ln.amount)

            apply_abs = requested_abs
            if requested_abs - remaining_abs > TOL:
                if over_rule == "block":
                    raise ValueError(f"Line for open item {item.id} exceeds outstanding.")
                apply_abs = remaining_abs
            if advance_balance is not None and apply_abs - available_advance > TOL:
                if over_rule == "block":
                    raise ValueError(f"Advance balance {advance_balance.id} is insufficient for line open item {item.id}.")
                apply_abs = available_advance

            if apply_abs <= ZERO2:
                continue

            direction = Decimal("1") if q2(item.outstanding_amount) > ZERO2 else Decimal("-1")
            applied_signed = q2(direction * apply_abs)

            item.settled_amount = q2(item.settled_amount + applied_signed)
            item.outstanding_amount = q2(item.original_amount - item.settled_amount)
            if abs(item.outstanding_amount) <= TOL:
                item.outstanding_amount = ZERO2
                item.is_open = False
            else:
                item.is_open = True
            item.last_settled_at = timezone.now()
            item.save(update_fields=["settled_amount", "outstanding_amount", "is_open", "last_settled_at", "updated_at"])
            SalesArService._sync_header_from_open_item(item)

            ln.applied_amount_signed = applied_signed
            ln.save(update_fields=["applied_amount_signed", "updated_at"])
            applied_total = q2(applied_total + apply_abs)
            if advance_balance is not None:
                available_advance = q2(available_advance - apply_abs)

        if advance_balance is not None:
            advance_balance.adjusted_amount = q2(advance_balance.adjusted_amount + applied_total)
            advance_balance.outstanding_amount = q2(advance_balance.original_amount - advance_balance.adjusted_amount)
            if abs(advance_balance.outstanding_amount) <= TOL:
                advance_balance.outstanding_amount = ZERO2
                advance_balance.is_open = False
            else:
                advance_balance.is_open = True
            advance_balance.last_adjusted_at = timezone.now()
            advance_balance.save(
                update_fields=["adjusted_amount", "outstanding_amount", "is_open", "last_adjusted_at", "updated_at"]
            )

        settlement.total_amount = applied_total
        settlement.status = CustomerSettlement.Status.POSTED
        settlement.posted_at = timezone.now()
        settlement.posted_by_id = posted_by_id
        settlement.save(update_fields=["total_amount", "status", "posted_at", "posted_by", "updated_at"])

        return SettlementPostResult(settlement=settlement, applied_total=applied_total, message="Settlement posted.")

    @staticmethod
    @transaction.atomic
    def cancel_settlement(*, settlement_id: int, cancelled_by_id: Optional[int] = None) -> SettlementCancelResult:
        settlement = CustomerSettlement.objects.select_for_update().get(pk=settlement_id)
        if int(settlement.status) == int(CustomerSettlement.Status.CANCELLED):
            return SettlementCancelResult(settlement=settlement, message="Settlement already cancelled.")
        if int(settlement.status) == int(CustomerSettlement.Status.DRAFT):
            settlement.status = CustomerSettlement.Status.CANCELLED
            settlement.save(update_fields=["status", "updated_at"])
            return SettlementCancelResult(settlement=settlement, message="Draft settlement cancelled.")

        lines = list(
            settlement.lines.select_related("open_item")
            .select_for_update()
            .order_by("id")
        )
        advance_balance = None
        if settlement.advance_balance_id:
            advance_balance = CustomerAdvanceBalance.objects.select_for_update().get(pk=settlement.advance_balance_id)
            reversed_total = ZERO2
        for ln in lines:
            item = ln.open_item
            applied_signed = q2(ln.applied_amount_signed)
            if applied_signed == ZERO2:
                continue
            # Reverse posted settlement effect.
            item.settled_amount = q2(item.settled_amount - applied_signed)
            item.outstanding_amount = q2(item.original_amount - item.settled_amount)
            if abs(item.outstanding_amount) <= TOL:
                item.outstanding_amount = ZERO2
                item.is_open = False
            else:
                item.is_open = True
            item.last_settled_at = timezone.now()
            item.save(update_fields=["settled_amount", "outstanding_amount", "is_open", "last_settled_at", "updated_at"])
            SalesArService._sync_header_from_open_item(item)

            ln.applied_amount_signed = ZERO2
            ln.save(update_fields=["applied_amount_signed", "updated_at"])
            if settlement.advance_balance_id:
                reversed_total = q2(reversed_total + abs(applied_signed))

        if advance_balance is not None:
            advance_balance.adjusted_amount = q2(advance_balance.adjusted_amount - reversed_total)
            if advance_balance.adjusted_amount < ZERO2:
                advance_balance.adjusted_amount = ZERO2
            advance_balance.outstanding_amount = q2(advance_balance.original_amount - advance_balance.adjusted_amount)
            advance_balance.is_open = abs(advance_balance.outstanding_amount) > TOL
            advance_balance.last_adjusted_at = timezone.now()
            advance_balance.save(
                update_fields=["adjusted_amount", "outstanding_amount", "is_open", "last_adjusted_at", "updated_at"]
            )

        settlement.status = CustomerSettlement.Status.CANCELLED
        settlement.save(update_fields=["status", "updated_at"])
        return SettlementCancelResult(settlement=settlement, message="Settlement cancelled with reversal.")

    @staticmethod
    def customer_statement(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        customer_id: int,
        include_closed: bool = False,
    ) -> Dict[str, Any]:
        open_items_qs = SalesArService.list_open_items(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
            is_open=None if include_closed else True,
        )
        settlements_qs = CustomerSettlement.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            customer_id=customer_id,
        )
        settlements_qs = settlements_qs.exclude(status=CustomerSettlement.Status.CANCELLED)
        if subentity_id is None:
            settlements_qs = settlements_qs.filter(subentity__isnull=True)
        else:
            settlements_qs = settlements_qs.filter(subentity_id=subentity_id)

        if not include_closed:
            settlements_qs = settlements_qs.filter(status=CustomerSettlement.Status.POSTED)

        settlements_qs = settlements_qs.select_related("advance_balance").prefetch_related("lines__open_item")
        totals = {
            "original_total": q2(sum((q2(x.original_amount) for x in open_items_qs), ZERO2)),
            "settled_total": q2(sum((q2(x.settled_amount) for x in open_items_qs), ZERO2)),
            "outstanding_total": q2(sum((q2(x.outstanding_amount) for x in open_items_qs), ZERO2)),
        }
        advances_qs = SalesArService.list_open_advances(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
            is_open=None if include_closed else True,
        )
        totals["advance_outstanding_total"] = q2(sum((q2(x.outstanding_amount) for x in advances_qs), ZERO2))
        advance_consumed_total = settlements_qs.filter(
            settlement_type=CustomerSettlement.SettlementType.ADVANCE_ADJUSTMENT
        )
        totals["advance_consumed_total"] = q2(sum((q2(x.total_amount) for x in advance_consumed_total), ZERO2))
        totals["net_ar_position"] = q2(totals["outstanding_total"] - totals["advance_outstanding_total"])
        totals["net_ap_position"] = totals["net_ar_position"]
        return {
            "open_items": open_items_qs,
            "advances": advances_qs,
            "settlements": settlements_qs.order_by("-settlement_date", "-id"),
            "totals": totals,
        }
