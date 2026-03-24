from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from financial.models import account
from purchase.models.purchase_ap import (
    VendorBillOpenItem,
    VendorAdvanceBalance,
    VendorSettlement,
    VendorSettlementLine,
)
from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.services.purchase_settings_service import PurchaseSettingsService
from purchase.services.ap_allocation_service import PurchaseApAllocationService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")
TOL = Decimal("0.01")


def q2(x) -> Decimal:
    return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class SettlementCreateResult:
    settlement: VendorSettlement
    message: str


@dataclass(frozen=True)
class SettlementPostResult:
    settlement: VendorSettlement
    applied_total: Decimal
    message: str


@dataclass(frozen=True)
class SettlementCancelResult:
    settlement: VendorSettlement
    message: str


class PurchaseApService:
    @staticmethod
    def _apply_subentity_scope(qs, subentity_id: Optional[int]):
        """
        AP items can be created at entity scope (subentity null) or branch scope.
        When a branch is selected, keep entity-scope liabilities visible as well,
        otherwise payment/settlement screens hide valid open payables/advances.
        """
        if subentity_id in (None, 0):
            return qs
        return qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))

    @staticmethod
    def _resolve_vendor_ledger_id(vendor_id: int) -> Optional[int]:
        return account.objects.filter(pk=vendor_id).values_list("ledger_id", flat=True).first()

    @staticmethod
    @transaction.atomic
    def create_advance_balance(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        vendor_id: int,
        source_type: str,
        credit_date: date,
        reference_no: Optional[str],
        remarks: Optional[str],
        amount: Decimal,
        payment_voucher_id: Optional[int] = None,
    ) -> VendorAdvanceBalance:
        amt = q2(amount)
        if amt <= ZERO2:
            raise ValueError("Advance balance amount must be > 0.")
        return VendorAdvanceBalance.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            vendor_ledger_id=PurchaseApService._resolve_vendor_ledger_id(vendor_id),
            source_type=source_type,
            credit_date=credit_date,
            reference_no=(reference_no or "").strip() or None,
            remarks=(remarks or "").strip() or None,
            original_amount=amt,
            adjusted_amount=ZERO2,
            outstanding_amount=amt,
            is_open=True,
            payment_voucher_id=payment_voucher_id,
        )

    @staticmethod
    def list_open_advances(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        vendor_id: Optional[int] = None,
        is_open: Optional[bool] = True,
    ) -> QuerySet[VendorAdvanceBalance]:
        qs = VendorAdvanceBalance.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        qs = PurchaseApService._apply_subentity_scope(qs, subentity_id)
        if vendor_id is not None:
            qs = qs.filter(vendor_id=vendor_id)
        if is_open is not None:
            qs = qs.filter(is_open=is_open)
        return qs.order_by("credit_date", "id")

    @staticmethod
    def _auto_adjust_credit_note_if_enabled(*, header: PurchaseInvoiceHeader, cn_item: VendorBillOpenItem) -> None:
        policy = PurchaseSettingsService.get_policy(header.entity_id, header.subentity_id)
        if str(policy.controls.get("settlement_mode", "off")).lower().strip() == "off":
            return
        if str(policy.controls.get("auto_adjust_credit_notes", "off")).lower().strip() != "on":
            return
        if int(header.doc_type) != int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE):
            return
        if not getattr(header, "ref_document_id", None):
            return

        marker = f"AUTO-CN-{header.id}"
        if VendorSettlement.objects.filter(
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            subentity_id=header.subentity_id,
            vendor_id=header.vendor_id,
            reference_no=marker,
            status=VendorSettlement.Status.POSTED,
        ).exists():
            return

        target = VendorBillOpenItem.objects.filter(
            header_id=header.ref_document_id,
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            vendor_id=header.vendor_id,
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

        create_res = PurchaseApService.create_settlement(
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            subentity_id=header.subentity_id,
            vendor_id=header.vendor_id,
            settlement_type=VendorSettlement.SettlementType.CREDIT_NOTE_ADJUSTMENT,
            settlement_date=header.bill_date,
            reference_no=marker,
            external_voucher_no=header.purchase_number,
            remarks="Auto credit-note adjustment",
            lines=[
                {"open_item_id": target.id, "amount": apply_abs, "note": "Adjusted against credit note"},
                {"open_item_id": cn_item.id, "amount": apply_abs, "note": "Credit note consumption"},
            ],
            amount=None,
        )
        PurchaseApService.post_settlement(settlement_id=create_res.settlement.id, posted_by_id=None)

    @staticmethod
    def _doc_sign(doc_type: int) -> Decimal:
        # Invoice / DN positive payable, CN negative payable
        if int(doc_type) == int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE):
            return Decimal("-1")
        return Decimal("1")

    @staticmethod
    @transaction.atomic
    def sync_open_item_for_header(header: PurchaseInvoiceHeader) -> VendorBillOpenItem:
        """
        Create/update AP open item from posted purchase header.
        Idempotent and safe to call multiple times.
        """
        sign = PurchaseApService._doc_sign(int(header.doc_type))
        gross_amount = q2(sign * q2(getattr(header, "grand_total", ZERO2)))
        tds_deducted = q2(sign * q2(getattr(header, "tds_amount", ZERO2)))
        gst_tds_deducted = q2(sign * q2(getattr(header, "gst_tds_amount", ZERO2)))
        net_payable = q2(gross_amount - tds_deducted - gst_tds_deducted)

        item, _ = VendorBillOpenItem.objects.select_for_update().get_or_create(
            header=header,
            defaults={
                "entity_id": header.entity_id,
                "entityfinid_id": header.entityfinid_id,
                "subentity_id": header.subentity_id,
                "vendor_id": header.vendor_id,
                "vendor_ledger_id": header.vendor_ledger_id or getattr(header.vendor, "ledger_id", None),
                "doc_type": int(header.doc_type),
                "bill_date": header.bill_date,
                "due_date": header.due_date,
                "purchase_number": header.purchase_number,
                "supplier_invoice_number": header.supplier_invoice_number,
                "original_amount": net_payable,
                "gross_amount": gross_amount,
                "tds_deducted": tds_deducted,
                "gst_tds_deducted": gst_tds_deducted,
                "net_payable_amount": net_payable,
                "settled_amount": ZERO2,
                "outstanding_amount": net_payable,
                "is_open": abs(net_payable) > TOL,
            },
        )

        # Keep snapshot fields fresh; preserve already-applied settlements.
        item.entity_id = header.entity_id
        item.entityfinid_id = header.entityfinid_id
        item.subentity_id = header.subentity_id
        item.vendor_id = header.vendor_id
        item.vendor_ledger_id = header.vendor_ledger_id or getattr(header.vendor, "ledger_id", None)
        item.doc_type = int(header.doc_type)
        item.bill_date = header.bill_date
        item.due_date = header.due_date
        item.purchase_number = header.purchase_number
        item.supplier_invoice_number = header.supplier_invoice_number
        item.original_amount = net_payable
        item.gross_amount = gross_amount
        item.tds_deducted = tds_deducted
        item.gst_tds_deducted = gst_tds_deducted
        item.net_payable_amount = net_payable
        item.outstanding_amount = q2(item.original_amount - q2(item.settled_amount))
        if abs(item.outstanding_amount) <= TOL:
            item.outstanding_amount = ZERO2
            item.is_open = False
        else:
            item.is_open = True
        item.save()

        PurchaseApService._auto_adjust_credit_note_if_enabled(header=header, cn_item=item)
        return item

    @staticmethod
    def list_open_items(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        vendor_id: Optional[int] = None,
        is_open: Optional[bool] = True,
    ) -> QuerySet[VendorBillOpenItem]:
        qs = VendorBillOpenItem.objects.select_related("header", "vendor", "vendor_ledger").filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        qs = PurchaseApService._apply_subentity_scope(qs, subentity_id)
        if vendor_id is not None:
            qs = qs.filter(vendor_id=vendor_id)
        if is_open is not None:
            qs = qs.filter(is_open=is_open)
        return qs.order_by("due_date", "bill_date", "id")

    @staticmethod
    def _auto_fifo_lines(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        vendor_id: int,
        amount: Decimal,
        controls: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        remaining = q2(amount)
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
        return [{"open_item_id": int(x["open_item"]), "amount": q2(x["settled_amount"])} for x in (preview.get("plan") or [])]

    @staticmethod
    @transaction.atomic
    def create_settlement(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        vendor_id: int,
        settlement_type: str,
        settlement_date: date,
        reference_no: Optional[str],
        external_voucher_no: Optional[str],
        remarks: Optional[str],
        lines: Optional[Iterable[Dict[str, Any]]] = None,
        amount: Optional[Decimal] = None,
        advance_balance_id: Optional[int] = None,
    ) -> SettlementCreateResult:
        policy = PurchaseSettingsService.get_policy(entity_id, subentity_id)
        if policy.controls.get("settlement_mode", "off") == "off":
            raise ValueError("AP settlement is disabled by purchase policy.")

        lines_data = list(lines or [])
        if not lines_data:
            allocation_policy = str(policy.controls.get("allocation_policy", "manual")).lower().strip()
            if allocation_policy == "fifo":
                lines_data = PurchaseApService._auto_fifo_lines(
                    entity_id=entity_id,
                    entityfinid_id=entityfinid_id,
                    subentity_id=subentity_id,
                    vendor_id=vendor_id,
                    amount=q2(amount or ZERO2),
                    controls=policy.controls,
                )
            if not lines_data:
                raise ValueError("Provide settlement lines (or amount with FIFO policy).")

        settlement = VendorSettlement.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            vendor_ledger_id=PurchaseApService._resolve_vendor_ledger_id(vendor_id),
            settlement_type=settlement_type,
            settlement_date=settlement_date,
            reference_no=(reference_no or "").strip() or None,
            external_voucher_no=(external_voucher_no or "").strip() or None,
            remarks=(remarks or "").strip() or None,
            advance_balance_id=advance_balance_id,
            total_amount=ZERO2,
            status=VendorSettlement.Status.DRAFT,
        )

        total = ZERO2
        for idx, row in enumerate(lines_data, start=1):
            open_item_id = int(row.get("open_item_id") or 0)
            amt = q2(row.get("amount") or ZERO2)
            if open_item_id <= 0:
                raise ValueError(f"Line {idx}: open_item_id is required.")
            if amt <= ZERO2:
                raise ValueError(f"Line {idx}: amount must be > 0.")

            open_item = VendorBillOpenItem.objects.filter(
                id=open_item_id,
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                vendor_id=vendor_id,
            ).first()
            if not open_item:
                raise ValueError(f"Line {idx}: open_item not found in selected scope/vendor.")

            VendorSettlementLine.objects.create(
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
        settlement = VendorSettlement.objects.select_for_update().get(pk=settlement_id)
        if int(settlement.status) == int(VendorSettlement.Status.POSTED):
            return SettlementPostResult(settlement=settlement, applied_total=q2(settlement.total_amount), message="Settlement already posted.")
        if int(settlement.status) == int(VendorSettlement.Status.CANCELLED):
            raise ValueError("Cancelled settlement cannot be posted.")

        policy = PurchaseSettingsService.get_policy(settlement.entity_id, settlement.subentity_id)
        if policy.controls.get("settlement_mode", "off") == "off":
            raise ValueError("AP settlement is disabled by purchase policy.")

        over_rule = str(policy.controls.get("over_settlement_rule", "block")).lower().strip()
        if over_rule not in {"block", "warn"}:
            over_rule = "block"

        lines = list(
            settlement.lines.select_related("open_item")
            .select_for_update()
            .order_by("id")
        )
        if not lines:
            raise ValueError("Settlement has no lines.")

        allocatable_remaining = PurchaseApAllocationService.allocatable_map(
            entity_id=settlement.entity_id,
            entityfinid_id=settlement.entityfinid_id,
            subentity_id=settlement.subentity_id,
            vendor_id=settlement.vendor_id,
            controls=policy.controls,
        )

        applied_total = ZERO2
        advance_balance = None
        available_advance = ZERO2
        if settlement.advance_balance_id:
            advance_balance = VendorAdvanceBalance.objects.select_for_update().get(pk=settlement.advance_balance_id)
            available_advance = q2(advance_balance.outstanding_amount)
        for ln in lines:
            item = ln.open_item
            if not item.is_open or abs(q2(item.outstanding_amount)) <= TOL:
                if over_rule == "block":
                    raise ValueError(f"Open item {item.id} is already settled.")
                continue

            remaining_abs = q2(abs(item.outstanding_amount))
            allocatable_abs = q2(allocatable_remaining.get(int(item.id), ZERO2))
            requested_abs = q2(ln.amount)

            apply_abs = requested_abs
            if allocatable_abs <= ZERO2:
                if over_rule == "block":
                    raise ValueError(f"Open item {item.id} is not allocatable after credit-note adjustment.")
                continue
            if requested_abs - allocatable_abs > TOL:
                if over_rule == "block":
                    raise ValueError(f"Line for open item {item.id} exceeds allocatable amount.")
                apply_abs = allocatable_abs
            if requested_abs - remaining_abs > TOL and apply_abs > remaining_abs:
                if over_rule == "block":
                    raise ValueError(f"Line for open item {item.id} exceeds outstanding.")
                apply_abs = min(apply_abs, remaining_abs)
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

            ln.applied_amount_signed = applied_signed
            ln.save(update_fields=["applied_amount_signed", "updated_at"])
            applied_total = q2(applied_total + apply_abs)
            allocatable_remaining[int(item.id)] = q2(max(allocatable_abs - apply_abs, ZERO2))
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
        settlement.status = VendorSettlement.Status.POSTED
        settlement.posted_at = timezone.now()
        settlement.posted_by_id = posted_by_id
        settlement.save(update_fields=["total_amount", "status", "posted_at", "posted_by", "updated_at"])

        return SettlementPostResult(settlement=settlement, applied_total=applied_total, message="Settlement posted.")

    @staticmethod
    @transaction.atomic
    def cancel_settlement(*, settlement_id: int, cancelled_by_id: Optional[int] = None) -> SettlementCancelResult:
        settlement = VendorSettlement.objects.select_for_update().get(pk=settlement_id)
        if int(settlement.status) == int(VendorSettlement.Status.CANCELLED):
            return SettlementCancelResult(settlement=settlement, message="Settlement already cancelled.")
        if int(settlement.status) == int(VendorSettlement.Status.DRAFT):
            settlement.status = VendorSettlement.Status.CANCELLED
            settlement.save(update_fields=["status", "updated_at"])
            return SettlementCancelResult(settlement=settlement, message="Draft settlement cancelled.")

        lines = list(
            settlement.lines.select_related("open_item")
            .select_for_update()
            .order_by("id")
        )
        advance_balance = None
        if settlement.advance_balance_id:
            advance_balance = VendorAdvanceBalance.objects.select_for_update().get(pk=settlement.advance_balance_id)
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

        settlement.status = VendorSettlement.Status.CANCELLED
        settlement.save(update_fields=["status", "updated_at"])
        return SettlementCancelResult(settlement=settlement, message="Settlement cancelled with reversal.")

    @staticmethod
    def vendor_statement(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        vendor_id: int,
        include_closed: bool = False,
    ) -> Dict[str, Any]:
        vendor = account.objects.select_related("ledger").get(pk=vendor_id)
        open_items_qs = PurchaseApService.list_open_items(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            is_open=None if include_closed else True,
        )
        settlements_qs = (
            VendorSettlement.objects
            .filter(entity_id=entity_id, entityfinid_id=entityfinid_id, vendor_id=vendor_id)
            .select_related("vendor", "vendor_ledger", "advance_balance", "advance_balance__payment_voucher")
        )
        settlements_qs = PurchaseApService._apply_subentity_scope(settlements_qs, subentity_id)

        if not include_closed:
            settlements_qs = settlements_qs.filter(status=VendorSettlement.Status.POSTED)

        settlements_qs = settlements_qs.prefetch_related("lines__open_item")
        totals = {
            "original_total": q2(sum((q2(x.original_amount) for x in open_items_qs), ZERO2)),
            "settled_total": q2(sum((q2(x.settled_amount) for x in open_items_qs), ZERO2)),
            "outstanding_total": q2(sum((q2(x.outstanding_amount) for x in open_items_qs), ZERO2)),
        }
        advances_qs = PurchaseApService.list_open_advances(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            vendor_id=vendor_id,
            is_open=None if include_closed else True,
        )
        totals["advance_outstanding_total"] = q2(sum((q2(x.outstanding_amount) for x in advances_qs), ZERO2))
        advance_consumed_total = settlements_qs.filter(
            settlement_type=VendorSettlement.SettlementType.ADVANCE_ADJUSTMENT
        )
        totals["advance_consumed_total"] = q2(sum((q2(x.total_amount) for x in advance_consumed_total), ZERO2))
        totals["net_ap_position"] = q2(totals["outstanding_total"] - totals["advance_outstanding_total"])
        return {
            "vendor": vendor,
            "open_items": open_items_qs,
            "advances": advances_qs,
            "settlements": settlements_qs.order_by("-settlement_date", "-id"),
            "totals": totals,
        }
