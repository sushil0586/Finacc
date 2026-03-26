from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from django.db import transaction
from django.utils import timezone

from financial.models import account as FinancialAccount
from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from sales.services.sales_ar_service import SalesArService
from sales.models.sales_ar import CustomerBillOpenItem
from sales.models import SalesAdvanceAdjustment
from posting.adapters.receipt_voucher import ReceiptVoucherPostingAdapter, ReceiptVoucherPostingConfig

from receipts.models.receipt_core import (
    ReceiptVoucherHeader,
    ReceiptVoucherAllocation,
    ReceiptVoucherAdjustment,
    ReceiptVoucherAdvanceAdjustment,
)
from receipts.services.receipt_settings_service import ReceiptSettingsService
from receipts.services.receipt_allocation_service import ReceiptAllocationService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(x) -> Decimal:
    return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ReceiptVoucherResult:
    header: ReceiptVoucherHeader
    message: str


class ReceiptVoucherService:
    @staticmethod
    def _as_pk(value: Any) -> Any:
        if value in (None, ""):
            return None
        return getattr(value, "pk", value)

    @classmethod
    def _normalize_allocations(cls, allocations: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows_by_open_item: Dict[int, Dict[str, Any]] = {}
        rows_without_open_item: List[Dict[str, Any]] = []
        for row in allocations or []:
            item = dict(row or {})
            item["open_item"] = cls._as_pk(item.get("open_item"))
            open_item = item.get("open_item")
            if open_item in (None, ""):
                rows_without_open_item.append(item)
                continue

            open_item = int(open_item)
            existing = rows_by_open_item.get(open_item)
            if existing is None:
                item["open_item"] = open_item
                item["settled_amount"] = q2(item.get("settled_amount") or ZERO2)
                item["is_full_settlement"] = bool(item.get("is_full_settlement", False))
                item["is_advance_adjustment"] = bool(item.get("is_advance_adjustment", False))
                rows_by_open_item[open_item] = item
            else:
                existing["settled_amount"] = q2(existing.get("settled_amount") or ZERO2) + q2(item.get("settled_amount") or ZERO2)
                existing["is_full_settlement"] = bool(existing.get("is_full_settlement", False) or item.get("is_full_settlement", False))
                existing["is_advance_adjustment"] = bool(existing.get("is_advance_adjustment", False) or item.get("is_advance_adjustment", False))
                if not existing.get("id") and item.get("id"):
                    existing["id"] = item.get("id")

        rows: List[Dict[str, Any]] = list(rows_by_open_item.values())
        rows.extend(rows_without_open_item)
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

    @staticmethod
    def _account_ledger_id(value: Any) -> Optional[int]:
        account_id = ReceiptVoucherService._as_pk(value)
        if account_id in (None, ""):
            return None
        acct = FinancialAccount.objects.filter(pk=account_id).only("id", "ledger_id").first()
        return getattr(acct, "ledger_id", None)

    @classmethod
    def _normalize_advance_adjustments(cls, rows_in: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[tuple, Dict[str, Any]] = {}
        rows_without_keys: List[Dict[str, Any]] = []
        for row in rows_in or []:
            item = dict(row or {})
            item["advance_balance_id"] = cls._as_pk(item.get("advance_balance_id") or item.get("advance_balance"))
            item["allocation"] = cls._as_pk(item.get("allocation"))
            item["open_item"] = cls._as_pk(item.get("open_item"))
            advance_balance_id = item.get("advance_balance_id")
            open_item = item.get("open_item")
            if advance_balance_id in (None, "") or open_item in (None, ""):
                rows_without_keys.append(item)
                continue

            key = (int(advance_balance_id), int(open_item))
            existing = merged.get(key)
            if existing is None:
                item["advance_balance_id"] = int(advance_balance_id)
                item["open_item"] = int(open_item)
                item["adjusted_amount"] = q2(item.get("adjusted_amount") or ZERO2)
                merged[key] = item
            else:
                existing["adjusted_amount"] = q2(existing.get("adjusted_amount") or ZERO2) + q2(item.get("adjusted_amount") or ZERO2)
                if not existing.get("remarks") and item.get("remarks"):
                    existing["remarks"] = item.get("remarks")
                if not existing.get("id") and item.get("id"):
                    existing["id"] = item.get("id")

        rows: List[Dict[str, Any]] = list(merged.values())
        rows.extend(rows_without_keys)
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
    def _safe_state_code_from_header(header: ReceiptVoucherHeader) -> str:
        st = getattr(header, "place_of_supply_state", None)
        if not st:
            return ""
        code = (
            getattr(st, "gst_state_code", None)
            or getattr(st, "statecode", None)
            or getattr(st, "code", None)
            or ""
        )
        return str(code or "").strip()

    @staticmethod
    def _table11_voucher_no(base: str, suffix: str = "") -> str:
        raw = f"{(base or '').strip()}{suffix}"
        return raw[:50]

    @staticmethod
    def _table11_row_payload(
        *,
        header: ReceiptVoucherHeader,
        voucher_number: str,
        customer_id: Optional[int],
        customer_name: str,
        customer_gstin: str,
        pos_code: str,
        entry_type: str,
        taxable_value: Decimal,
        cgst_amount: Decimal,
        sgst_amount: Decimal,
        igst_amount: Decimal,
        cess_amount: Decimal,
        linked_invoice_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {
            "entity_id": header.entity_id,
            "entityfinid_id": header.entityfinid_id,
            "subentity_id": getattr(header, "subentity_id", None),
            "voucher_date": header.voucher_date,
            "voucher_number": voucher_number,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "customer_gstin": customer_gstin,
            "place_of_supply_state_code": pos_code,
            "entry_type": entry_type,
            "taxable_value": taxable_value,
            "cgst_amount": cgst_amount,
            "sgst_amount": sgst_amount,
            "igst_amount": igst_amount,
            "cess_amount": cess_amount,
            "linked_invoice_id": linked_invoice_id,
            "is_amendment": False,
        }

    @staticmethod
    def _table11_changed(existing: SalesAdvanceAdjustment, payload: Dict[str, Any]) -> bool:
        compare_fields = (
            "voucher_date",
            "customer_id",
            "customer_name",
            "customer_gstin",
            "place_of_supply_state_code",
            "entry_type",
            "taxable_value",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "cess_amount",
            "linked_invoice_id",
        )
        for field_name in compare_fields:
            if getattr(existing, field_name) != payload.get(field_name):
                return True
        return False

    @staticmethod
    def _table11_create_amendment_snapshot(
        *,
        source: SalesAdvanceAdjustment,
        replacement: Optional[Dict[str, Any]] = None,
    ) -> None:
        stamp = timezone.now().strftime("%Y%m%d%H%M%S")
        snap = replacement or {}
        SalesAdvanceAdjustment.objects.create(
            entity_id=source.entity_id,
            entityfinid_id=source.entityfinid_id,
            subentity_id=source.subentity_id,
            voucher_date=snap.get("voucher_date", source.voucher_date),
            voucher_number=ReceiptVoucherService._table11_voucher_no(source.voucher_number, f"-AMD-{stamp}"),
            customer_id=snap.get("customer_id", source.customer_id),
            customer_name=snap.get("customer_name", source.customer_name),
            customer_gstin=snap.get("customer_gstin", source.customer_gstin),
            place_of_supply_state_code=snap.get("place_of_supply_state_code", source.place_of_supply_state_code),
            entry_type=snap.get("entry_type", source.entry_type),
            taxable_value=snap.get("taxable_value", source.taxable_value),
            cgst_amount=snap.get("cgst_amount", source.cgst_amount),
            sgst_amount=snap.get("sgst_amount", source.sgst_amount),
            igst_amount=snap.get("igst_amount", source.igst_amount),
            cess_amount=snap.get("cess_amount", source.cess_amount),
            linked_invoice_id=snap.get("linked_invoice_id", source.linked_invoice_id),
            original_entry=source,
            is_amendment=True,
        )

    @staticmethod
    def _sync_gstr1_table11_rows(
        *,
        header: ReceiptVoucherHeader,
        live_advance_rows: List[ReceiptVoucherAdvanceAdjustment],
        track_amendments: bool = True,
    ) -> None:
        if not (
            getattr(header, "entity_id", None)
            and getattr(header, "entityfinid_id", None)
            and getattr(header, "voucher_date", None)
        ):
            return

        voucher_no = (getattr(header, "voucher_code", None) or getattr(header, "reference_number", None) or "").strip()
        if not voucher_no:
            voucher_no = f"{getattr(header, 'doc_code', 'RV') or 'RV'}-{getattr(header, 'doc_no', None) or getattr(header, 'id', None)}"
        voucher_no = ReceiptVoucherService._table11_voucher_no(voucher_no)

        from entity.models import Entity, EntityFinancialYear
        if not Entity.objects.filter(id=header.entity_id).exists():
            return
        if not EntityFinancialYear.objects.filter(id=header.entityfinid_id).exists():
            return

        active_qs = SalesAdvanceAdjustment.objects.filter(
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            subentity_id=getattr(header, "subentity_id", None),
            voucher_number=voucher_no,
            is_amendment=False,
        )
        adj_qs = SalesAdvanceAdjustment.objects.filter(
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            subentity_id=getattr(header, "subentity_id", None),
            voucher_number__startswith=ReceiptVoucherService._table11_voucher_no(f"{voucher_no}-ADJ-"),
            is_amendment=False,
        )
        existing_rows: Dict[str, SalesAdvanceAdjustment] = {
            row.voucher_number: row for row in list(active_qs) + list(adj_qs)
        }
        desired_rows: List[Dict[str, Any]] = []

        customer = getattr(header, "received_from", None)
        customer_name = (
            (getattr(customer, "legalname", None) or getattr(customer, "accountname", None) or "").strip()
            if customer
            else ""
        )
        customer_gstin = (getattr(header, "customer_gstin", "") or "").strip().upper()
        pos_code = ReceiptVoucherService._safe_state_code_from_header(header)

        customer_id = getattr(header, "received_from_id", None)
        if customer_id and not FinancialAccount.objects.filter(id=customer_id).exists():
            customer_id = None

        adv_taxable = q2(getattr(header, "advance_taxable_value", ZERO2))
        adv_cgst = q2(getattr(header, "advance_cgst", ZERO2))
        adv_sgst = q2(getattr(header, "advance_sgst", ZERO2))
        adv_igst = q2(getattr(header, "advance_igst", ZERO2))
        adv_cess = q2(getattr(header, "advance_cess", ZERO2))

        if (
            getattr(header, "receipt_type", None) in {ReceiptVoucherHeader.ReceiptType.ADVANCE, ReceiptVoucherHeader.ReceiptType.ON_ACCOUNT}
            or any(x > ZERO2 for x in [adv_taxable, adv_cgst, adv_sgst, adv_igst, adv_cess])
        ):
            desired_rows.append(
                ReceiptVoucherService._table11_row_payload(
                    header=header,
                    voucher_number=voucher_no,
                    customer_id=customer_id,
                    customer_name=customer_name,
                    customer_gstin=customer_gstin,
                    pos_code=pos_code,
                    entry_type=SalesAdvanceAdjustment.EntryType.ADVANCE_RECEIPT,
                    taxable_value=adv_taxable,
                    cgst_amount=adv_cgst,
                    sgst_amount=adv_sgst,
                    igst_amount=adv_igst,
                    cess_amount=adv_cess,
                )
            )

        # Build Table 11B from source advance snapshots (not current voucher
        # header), so invoice-period adjustments remain correct even when the
        # adjustment voucher itself has zero advance tax fields.
        linked_tax_totals: Dict[Optional[int], Dict[str, Decimal]] = {}
        for adj in live_advance_rows:
            adjusted = q2(getattr(adj, "adjusted_amount", ZERO2))
            if adjusted <= ZERO2:
                continue

            linked_invoice_id = None
            open_item_id = getattr(adj, "open_item_id", None)
            if open_item_id:
                try:
                    open_item = CustomerBillOpenItem.objects.filter(id=open_item_id).only("header_id").first()
                    linked_invoice_id = getattr(open_item, "header_id", None)
                except Exception:
                    linked_invoice_id = None

            source_taxable = ZERO2
            source_cgst = ZERO2
            source_sgst = ZERO2
            source_igst = ZERO2
            source_cess = ZERO2
            source_total = ZERO2

            adv_balance = getattr(adj, "advance_balance", None)
            if adv_balance is not None:
                rv = getattr(adv_balance, "receipt_voucher", None)
                if rv is not None:
                    source_taxable = q2(getattr(rv, "advance_taxable_value", ZERO2))
                    source_cgst = q2(getattr(rv, "advance_cgst", ZERO2))
                    source_sgst = q2(getattr(rv, "advance_sgst", ZERO2))
                    source_igst = q2(getattr(rv, "advance_igst", ZERO2))
                    source_cess = q2(getattr(rv, "advance_cess", ZERO2))
                    source_total = q2(source_taxable + source_cgst + source_sgst + source_igst + source_cess)

                if source_total <= ZERO2:
                    source_total = q2(getattr(adv_balance, "original_amount", ZERO2))

            ratio = Decimal("0.00")
            if source_total > ZERO2:
                ratio = adjusted / source_total

            taxable_part = q2(source_taxable * ratio)
            cgst_part = q2(source_cgst * ratio)
            sgst_part = q2(source_sgst * ratio)
            igst_part = q2(source_igst * ratio)
            cess_part = q2(source_cess * ratio)

            bucket = linked_tax_totals.get(linked_invoice_id)
            if bucket is None:
                bucket = {
                    "taxable_value": ZERO2,
                    "cgst_amount": ZERO2,
                    "sgst_amount": ZERO2,
                    "igst_amount": ZERO2,
                    "cess_amount": ZERO2,
                }
                linked_tax_totals[linked_invoice_id] = bucket

            bucket["taxable_value"] = q2(bucket["taxable_value"] + taxable_part)
            bucket["cgst_amount"] = q2(bucket["cgst_amount"] + cgst_part)
            bucket["sgst_amount"] = q2(bucket["sgst_amount"] + sgst_part)
            bucket["igst_amount"] = q2(bucket["igst_amount"] + igst_part)
            bucket["cess_amount"] = q2(bucket["cess_amount"] + cess_part)

        for idx, (linked_invoice_id, taxes) in enumerate(linked_tax_totals.items(), start=1):
            desired_rows.append(
                ReceiptVoucherService._table11_row_payload(
                    header=header,
                    voucher_number=ReceiptVoucherService._table11_voucher_no(f"{voucher_no}-ADJ-{idx}"),
                    customer_id=customer_id,
                    customer_name=customer_name,
                    customer_gstin=customer_gstin,
                    pos_code=pos_code,
                    entry_type=SalesAdvanceAdjustment.EntryType.ADVANCE_ADJUSTMENT,
                    taxable_value=q2(taxes["taxable_value"]),
                    cgst_amount=q2(taxes["cgst_amount"]),
                    sgst_amount=q2(taxes["sgst_amount"]),
                    igst_amount=q2(taxes["igst_amount"]),
                    cess_amount=q2(taxes["cess_amount"]),
                    linked_invoice_id=linked_invoice_id,
                )
            )

        seen = set()
        for payload in desired_rows:
            key = payload["voucher_number"]
            seen.add(key)
            existing = existing_rows.get(key)
            if not existing:
                SalesAdvanceAdjustment.objects.create(**payload)
                continue
            if not ReceiptVoucherService._table11_changed(existing, payload):
                continue
            if track_amendments:
                ReceiptVoucherService._table11_create_amendment_snapshot(source=existing)
            for field_name, value in payload.items():
                setattr(existing, field_name, value)
            existing.save()

        removed_rows = [row for key, row in existing_rows.items() if key not in seen]
        for row in removed_rows:
            if track_amendments:
                ReceiptVoucherService._table11_create_amendment_snapshot(
                    source=row,
                    replacement={
                        "taxable_value": ZERO2,
                        "cgst_amount": ZERO2,
                        "sgst_amount": ZERO2,
                        "igst_amount": ZERO2,
                        "cess_amount": ZERO2,
                    },
                )
            row.delete()

    @staticmethod
    def _unsync_gstr1_table11_rows(*, header: ReceiptVoucherHeader) -> None:
        voucher_no = (getattr(header, "voucher_code", None) or getattr(header, "reference_number", None) or "").strip()
        if not voucher_no:
            voucher_no = f"{getattr(header, 'doc_code', 'RV') or 'RV'}-{getattr(header, 'doc_no', None) or getattr(header, 'id', None)}"

        filters = {
            "entity_id": getattr(header, "entity_id", None),
            "entityfinid_id": getattr(header, "entityfinid_id", None),
            "subentity_id": getattr(header, "subentity_id", None),
            "voucher_number__startswith": voucher_no,
        }
        voucher_date = getattr(header, "voucher_date", None)
        if voucher_date is not None:
            filters["voucher_date"] = voucher_date

        customer_id = getattr(header, "received_from_id", None)
        if customer_id and FinancialAccount.objects.filter(id=customer_id).exists():
            filters["customer_id"] = customer_id

        SalesAdvanceAdjustment.objects.filter(**filters).delete()

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
    def _fresh_allocation_rows(voucher: ReceiptVoucherHeader) -> List[ReceiptVoucherAllocation]:
        # Posting paths may create allocations after the voucher was loaded with
        # prefetched relations. Always requery allocations to avoid stale
        # prefetched caches masking newly created rows.
        return list(
            ReceiptVoucherAllocation.objects.filter(receipt_voucher_id=voucher.id).select_related("open_item")
        )

    @staticmethod
    def _doc_type_id_for_receipt(doc_code: str) -> int:
        dt = DocumentType.objects.filter(module="receipts", default_code=doc_code, is_active=True).first()
        if not dt:
            raise ValueError(f"DocumentType not found for module='receipts' and doc_code='{doc_code}'")
        return dt.id

    @staticmethod
    def _compute_adjustment_total(adjustments: Iterable[Dict[str, Any]]) -> Decimal:
        total = ZERO2
        for row in adjustments or []:
            amt = q2(row.get("amount") or ZERO2)
            eff = str(row.get("settlement_effect") or ReceiptVoucherAdjustment.Effect.PLUS)
            if eff == ReceiptVoucherAdjustment.Effect.MINUS:
                total = q2(total - amt)
            else:
                total = q2(total + amt)
        return total

    @staticmethod
    def _effective_settlement_amount(cash_received_amount: Decimal, adjustment_total: Decimal) -> Decimal:
        return q2(q2(cash_received_amount) + q2(adjustment_total))

    @staticmethod
    def _validate_allocations(
        voucher: ReceiptVoucherHeader,
        allocations: List[Dict[str, Any]],
        over_settlement_rule: str = "block",
        controls: Optional[Dict[str, Any]] = None,
    ) -> list[str]:
        warnings: list[str] = []
        allocatable = ReceiptAllocationService.allocatable_map(
            entity_id=int(voucher.entity_id),
            entityfinid_id=int(voucher.entityfinid_id),
            subentity_id=voucher.subentity_id,
            customer_id=int(voucher.received_from_id),
            controls=controls,
        )
        for i, row in enumerate(allocations or [], start=1):
            open_item_id = row.get("open_item")
            amt = q2(row.get("settled_amount") or ZERO2)
            if open_item_id in (None, ""):
                raise ValueError(f"Allocation row {i}: open_item is required.")
            if amt <= ZERO2:
                raise ValueError(f"Allocation row {i}: settled_amount must be > 0.")

            open_item = CustomerBillOpenItem.objects.filter(pk=open_item_id).first()
            if not open_item:
                raise ValueError(f"Allocation row {i}: open_item not found.")
            if int(open_item.entity_id) != int(voucher.entity_id) or int(open_item.entityfinid_id) != int(voucher.entityfinid_id):
                raise ValueError(f"Allocation row {i}: open_item scope mismatch with entity/entityfinid.")
            if voucher.subentity_id != open_item.subentity_id:
                raise ValueError(f"Allocation row {i}: open_item subentity mismatch.")
            if int(open_item.customer_id) != int(voucher.received_from_id):
                raise ValueError(f"Allocation row {i}: open_item customer mismatch with received_from.")

            allowed = q2(allocatable.get(int(open_item_id), ZERO2))
            if over_settlement_rule == "block":
                if amt > allowed:
                    raise ValueError(
                        f"Allocation row {i}: settled_amount {amt} exceeds allocatable {allowed} for open_item {open_item_id}."
                    )
            elif over_settlement_rule == "warn":
                if amt > allowed:
                    warnings.append(
                        f"Allocation row {i}: settled_amount {amt} exceeds allocatable {allowed} for open_item {open_item_id}."
                    )
        return warnings

    @staticmethod
    def _validate_adjustment_allocation_links(*, voucher_id: int, adjustments: List[Dict[str, Any]]) -> None:
        for i, row in enumerate(adjustments or [], start=1):
            alloc_id = row.get("allocation")
            if alloc_id in (None, ""):
                continue
            ok = ReceiptVoucherAllocation.objects.filter(id=int(alloc_id), receipt_voucher_id=int(voucher_id)).exists()
            if not ok:
                raise ValueError(f"Adjustment row {i}: allocation must belong to this receipt voucher.")

    @staticmethod
    def _validate_advance_adjustments(
        *,
        voucher: ReceiptVoucherHeader,
        allocations: List[Dict[str, Any]],
        advance_adjustments: List[Dict[str, Any]],
    ) -> None:
        if not advance_adjustments:
            return

        alloc_open_item_map = {}
        for row in allocations or []:
            open_item_id = ReceiptVoucherService._as_pk(row.get("open_item"))
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

            adv = SalesArService.list_open_advances(
                entity_id=voucher.entity_id,
                entityfinid_id=voucher.entityfinid_id,
                subentity_id=voucher.subentity_id,
                customer_id=voucher.received_from_id,
                is_open=None,
            ).filter(id=int(balance_id)).first()
            if not adv:
                raise ValueError(f"Advance row {i}: advance balance not found in selected scope/customer.")

            if alloc_id not in (None, ""):
                alloc = ReceiptVoucherAllocation.objects.filter(
                    id=int(alloc_id),
                    receipt_voucher_id=int(voucher.id or 0),
                ).select_related("open_item").first()
                if not alloc:
                    raise ValueError(f"Advance row {i}: allocation must belong to this voucher.")
                open_item_id = open_item_id or alloc.open_item_id
                row["open_item"] = open_item_id

            if open_item_id in (None, ""):
                raise ValueError(f"Advance row {i}: open_item is required for bill adjustment.")

            open_item = CustomerBillOpenItem.objects.filter(pk=int(open_item_id)).first()
            if not open_item:
                raise ValueError(f"Advance row {i}: open_item not found.")
            if int(open_item.entity_id) != int(voucher.entity_id) or int(open_item.entityfinid_id) != int(voucher.entityfinid_id):
                raise ValueError(f"Advance row {i}: open_item scope mismatch.")
            if voucher.subentity_id != open_item.subentity_id:
                raise ValueError(f"Advance row {i}: open_item subentity mismatch.")
            if int(open_item.customer_id) != int(voucher.received_from_id):
                raise ValueError(f"Advance row {i}: open_item customer mismatch with received_from.")

            per_balance[int(balance_id)] = q2(per_balance.get(int(balance_id), ZERO2) + amount)
            per_open_item[int(open_item_id)] = q2(per_open_item.get(int(open_item_id), ZERO2) + amount)

        for balance_id, total in per_balance.items():
            adv = SalesArService.list_open_advances(
                entity_id=voucher.entity_id,
                entityfinid_id=voucher.entityfinid_id,
                subentity_id=voucher.subentity_id,
                customer_id=voucher.received_from_id,
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
        customer_id: int,
        target_amount: Decimal,
        controls: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        preview = ReceiptAllocationService.preview_allocation(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
            target_amount=q2(target_amount),
            controls=controls,
        )
        return list(preview.get("plan") or [])

    @staticmethod
    @transaction.atomic
    def create_voucher(validated_data: Dict[str, Any]) -> ReceiptVoucherHeader:
        allocations = ReceiptVoucherService._normalize_allocations(validated_data.pop("allocations", []) or [])
        adjustments = ReceiptVoucherService._normalize_adjustments(validated_data.pop("adjustments", []) or [])
        advance_adjustments = ReceiptVoucherService._normalize_advance_adjustments(
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

        policy = ReceiptSettingsService.get_policy(
            validated_data["entity"].id if hasattr(validated_data.get("entity"), "id") else validated_data.get("entity"),
            validated_data.get("subentity").id if hasattr(validated_data.get("subentity"), "id") else validated_data.get("subentity"),
        )
        ref_level = str(policy.controls.get("require_reference_number", "off")).lower().strip()
        if ref_level == "hard" and not (validated_data.get("reference_number") or "").strip():
            raise ValueError({"reference_number": "reference_number is required by receipt policy."})

        if int(validated_data.get("status", ReceiptVoucherHeader.Status.DRAFT)) != int(ReceiptVoucherHeader.Status.DRAFT):
            validated_data["status"] = ReceiptVoucherHeader.Status.DRAFT

        adjustment_total = ReceiptVoucherService._compute_adjustment_total(adjustments)
        advance_total = ReceiptVoucherService._sum_advance_adjustments(advance_adjustments)
        effective = ReceiptVoucherService._effective_settlement_amount(
            q2(validated_data.get("cash_received_amount", ZERO2)),
            adjustment_total,
        )
        validated_data["total_adjustment_amount"] = adjustment_total
        validated_data["settlement_effective_amount"] = effective
        validated_data["settlement_effective_amount_base_currency"] = q2(effective * exchange_rate)
        validated_data["received_in_ledger_id"] = ReceiptVoucherService._account_ledger_id(validated_data.get("received_in"))
        validated_data["received_from_ledger_id"] = ReceiptVoucherService._account_ledger_id(validated_data.get("received_from"))

        allocation_policy = str(policy.controls.get("allocation_policy", "manual")).lower().strip()
        if (
            not allocations
            and allocation_policy == "fifo"
            and validated_data.get("receipt_type") == ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE
        ):
            allocations = ReceiptVoucherService._auto_fifo_allocations(
                entity_id=validated_data["entity"].id if hasattr(validated_data.get("entity"), "id") else validated_data["entity"],
                entityfinid_id=validated_data["entityfinid"].id if hasattr(validated_data.get("entityfinid"), "id") else validated_data["entityfinid"],
                subentity_id=validated_data.get("subentity").id if hasattr(validated_data.get("subentity"), "id") else validated_data.get("subentity"),
                customer_id=validated_data["received_from"].id if hasattr(validated_data.get("received_from"), "id") else validated_data["received_from"],
                target_amount=effective,
                controls=policy.controls,
            )

        amount_match_level = str(policy.controls.get("allocation_amount_match_rule", "hard")).lower().strip()
        total_support = q2(effective + advance_total)
        if allocations:
            ReceiptVoucherService._validate_allocation_effective_match(
                effective_amount=total_support,
                allocation_total=ReceiptVoucherService._sum_allocations(allocations),
                level=amount_match_level,
            )

        header = ReceiptVoucherHeader.objects.create(**validated_data)

        over_settlement_rule = str(policy.controls.get("over_settlement_rule", "block")).lower().strip()
        if allocations:
            ReceiptVoucherService._validate_allocations(header, allocations, over_settlement_rule=over_settlement_rule, controls=policy.controls)

        for row in allocations:
            ReceiptVoucherAllocation.objects.create(
                receipt_voucher=header,
                open_item_id=row.get("open_item"),
                settled_amount=q2(row.get("settled_amount") or ZERO2),
                is_full_settlement=bool(row.get("is_full_settlement", False)),
                is_advance_adjustment=bool(row.get("is_advance_adjustment", False)),
            )

        for row in adjustments:
            ReceiptVoucherAdjustment.objects.create(
                receipt_voucher=header,
                allocation_id=row.get("allocation"),
                adj_type=row.get("adj_type"),
                ledger_account_id=row.get("ledger_account"),
                ledger_id=row.get("ledger"),
                amount=q2(row.get("amount") or ZERO2),
                settlement_effect=row.get("settlement_effect") or ReceiptVoucherAdjustment.Effect.PLUS,
                remarks=(row.get("remarks") or "").strip() or None,
            )

        ReceiptVoucherService._validate_adjustment_allocation_links(voucher_id=header.id, adjustments=adjustments)
        ReceiptVoucherService._validate_advance_adjustments(
            voucher=header,
            allocations=allocations,
            advance_adjustments=advance_adjustments,
        )
        for row in advance_adjustments:
            ReceiptVoucherAdvanceAdjustment.objects.create(
                receipt_voucher=header,
                advance_balance_id=row.get("advance_balance_id"),
                allocation_id=row.get("allocation"),
                open_item_id=row.get("open_item"),
                adjusted_amount=q2(row.get("adjusted_amount") or ZERO2),
                remarks=(row.get("remarks") or "").strip() or None,
            )

        if policy.default_action == "confirm":
            ReceiptVoucherService.confirm_voucher(header.id)
        elif policy.default_action == "post":
            ReceiptVoucherService.confirm_voucher(header.id)
            ReceiptVoucherService.post_voucher(header.id)

        header.refresh_from_db()
        return header

    @staticmethod
    @transaction.atomic
    def update_voucher(instance: ReceiptVoucherHeader, validated_data: Dict[str, Any]) -> ReceiptVoucherHeader:
        if int(instance.status) in (int(ReceiptVoucherHeader.Status.POSTED), int(ReceiptVoucherHeader.Status.CANCELLED)):
            raise ValueError("Posted/Cancelled receipt voucher cannot be edited.")

        allocations = validated_data.pop("allocations", None)
        adjustments = validated_data.pop("adjustments", None)
        advance_adjustments = validated_data.pop("advance_adjustments", None)
        if allocations is not None:
            allocations = ReceiptVoucherService._normalize_allocations(allocations)
        if adjustments is not None:
            adjustments = ReceiptVoucherService._normalize_adjustments(adjustments)
        if advance_adjustments is not None:
            advance_adjustments = ReceiptVoucherService._normalize_advance_adjustments(advance_adjustments)
        policy = ReceiptSettingsService.get_policy(instance.entity_id, instance.subentity_id)
        workflow_state = ReceiptVoucherService._workflow_state(instance.workflow_payload)
        if (
            str(policy.controls.get("allow_edit_after_submit", "on")).lower().strip() == "off"
            and workflow_state.get("status") == "SUBMITTED"
        ):
            raise ValueError("Submitted voucher cannot be edited by receipt policy.")
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
        if "received_in" in validated_data:
            instance.received_in_ledger_id = ReceiptVoucherService._account_ledger_id(validated_data.get("received_in"))
        if "received_from" in validated_data:
            instance.received_from_ledger_id = ReceiptVoucherService._account_ledger_id(validated_data.get("received_from"))
        instance.save()

        if allocations is not None:
            ReceiptVoucherService._validate_allocations(instance, allocations, over_settlement_rule=over_settlement_rule, controls=policy.controls)
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
            ReceiptVoucherService._validate_allocation_effective_match(
                effective_amount=q2(
                    ReceiptVoucherService._effective_settlement_amount(
                    q2(validated_data.get("cash_received_amount", instance.cash_received_amount)),
                    ReceiptVoucherService._compute_adjustment_total(
                        adjustments
                        if adjustments is not None
                        else instance.adjustments.values("amount", "settlement_effect")
                    ),
                ) + ReceiptVoucherService._sum_advance_adjustments(live_advance_rows)),
                allocation_total=ReceiptVoucherService._sum_allocations(allocations),
                level=amount_match_level,
            )
            existing = {x.id: x for x in instance.allocations.all()}
            existing_by_open_item = {
                int(x.open_item_id): x
                for x in instance.allocations.all()
                if x.open_item_id
            }
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
                    match = existing_by_open_item.get(int(row.get("open_item"))) if row.get("open_item") not in (None, "") else None
                    if match and match.id not in seen:
                        obj = match
                        obj.open_item_id = row.get("open_item")
                        obj.settled_amount = q2(row.get("settled_amount") or ZERO2)
                        obj.is_full_settlement = bool(row.get("is_full_settlement", False))
                        obj.is_advance_adjustment = bool(row.get("is_advance_adjustment", False))
                        obj.save()
                    else:
                        obj = ReceiptVoucherAllocation.objects.create(
                            receipt_voucher=instance,
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
                    obj.settlement_effect = row.get("settlement_effect") or ReceiptVoucherAdjustment.Effect.PLUS
                    obj.remarks = (row.get("remarks") or "").strip() or None
                    obj.save()
                    seen.add(rid)
                else:
                    obj = ReceiptVoucherAdjustment.objects.create(
                        receipt_voucher=instance,
                        allocation_id=row.get("allocation"),
                        adj_type=row.get("adj_type"),
                        ledger_account_id=row.get("ledger_account"),
                        ledger_id=row.get("ledger"),
                        amount=q2(row.get("amount") or ZERO2),
                        settlement_effect=row.get("settlement_effect") or ReceiptVoucherAdjustment.Effect.PLUS,
                        remarks=(row.get("remarks") or "").strip() or None,
                    )
                    seen.add(obj.id)
            for rid, obj in existing.items():
                if rid not in seen:
                    obj.delete()
            ReceiptVoucherService._validate_adjustment_allocation_links(voucher_id=instance.id, adjustments=adjustments)

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
            ReceiptVoucherService._validate_advance_adjustments(
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
                    obj = ReceiptVoucherAdvanceAdjustment.objects.create(
                        receipt_voucher=instance,
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

        adjustment_total = ReceiptVoucherService._compute_adjustment_total(
            instance.adjustments.values("amount", "settlement_effect")
        )
        instance.total_adjustment_amount = adjustment_total
        instance.settlement_effective_amount = ReceiptVoucherService._effective_settlement_amount(
            q2(instance.cash_received_amount),
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
    def confirm_voucher(voucher_id: int, confirmed_by_id: Optional[int] = None) -> ReceiptVoucherResult:
        h = ReceiptVoucherHeader.objects.select_related("entity", "entityfinid", "subentity").get(pk=voucher_id)

        if int(h.status) == int(ReceiptVoucherHeader.Status.CANCELLED):
            raise ValueError("Cannot confirm: voucher is cancelled.")
        if int(h.status) == int(ReceiptVoucherHeader.Status.POSTED):
            return ReceiptVoucherResult(h, "Already posted.")

        if not h.doc_code:
            s = ReceiptSettingsService.get_settings(h.entity_id, h.subentity_id)
            h.doc_code = s.default_doc_code_receipt or "RV"

        if not h.doc_no or not h.voucher_code:
            dt_id = ReceiptVoucherService._doc_type_id_for_receipt(h.doc_code)
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

        if int(h.status) == int(ReceiptVoucherHeader.Status.CONFIRMED):
            if confirmed_by_id and not h.approved_by_id:
                h.approved_by_id = confirmed_by_id
                h.save(update_fields=["doc_code", "doc_no", "voucher_code", "approved_by", "updated_at"])
            else:
                h.save(update_fields=["doc_code", "doc_no", "voucher_code", "updated_at"])
            return ReceiptVoucherResult(h, "Already confirmed.")

        h.status = ReceiptVoucherHeader.Status.CONFIRMED
        if confirmed_by_id and not h.approved_by_id:
            h.approved_by_id = confirmed_by_id
            h.save(update_fields=["doc_code", "doc_no", "voucher_code", "status", "approved_by", "updated_at"])
        else:
            h.save(update_fields=["doc_code", "doc_no", "voucher_code", "status", "updated_at"])
        return ReceiptVoucherResult(h, "Confirmed.")

    @staticmethod
    @transaction.atomic
    def submit_voucher(voucher_id: int, submitted_by_id: Optional[int] = None, remarks: Optional[str] = None) -> ReceiptVoucherResult:
        h = ReceiptVoucherHeader.objects.select_for_update().get(pk=voucher_id)
        if int(h.status) in (int(ReceiptVoucherHeader.Status.POSTED), int(ReceiptVoucherHeader.Status.CANCELLED)):
            raise ValueError("Only draft/confirmed vouchers can be submitted.")
        state = ReceiptVoucherService._workflow_state(h.workflow_payload)
        state.update({
            "status": "SUBMITTED",
            "submitted_by": submitted_by_id,
            "submitted_at": timezone.now().isoformat(),
            "remarks": (remarks or "").strip() or None,
        })
        h.workflow_payload = ReceiptVoucherService._set_workflow_state(h.workflow_payload, state)
        h.workflow_payload = ReceiptVoucherService._append_audit(
            h.workflow_payload,
            {"action": "SUBMITTED", "at": timezone.now().isoformat(), "by": submitted_by_id, "remarks": state["remarks"]},
        )
        h.save(update_fields=["workflow_payload", "updated_at"])
        return ReceiptVoucherResult(h, "Submitted for approval.")

    @staticmethod
    @transaction.atomic
    def approve_voucher(voucher_id: int, approved_by_id: Optional[int] = None, remarks: Optional[str] = None) -> ReceiptVoucherResult:
        h = ReceiptVoucherHeader.objects.select_for_update().get(pk=voucher_id)
        if int(h.status) in (int(ReceiptVoucherHeader.Status.POSTED), int(ReceiptVoucherHeader.Status.CANCELLED)):
            raise ValueError("Only draft/confirmed vouchers can be approved.")
        policy = ReceiptSettingsService.get_policy(h.entity_id, h.subentity_id)
        state = ReceiptVoucherService._workflow_state(h.workflow_payload)
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
        h.workflow_payload = ReceiptVoucherService._set_workflow_state(h.workflow_payload, state)
        h.workflow_payload = ReceiptVoucherService._append_audit(
            h.workflow_payload,
            {"action": "APPROVED", "at": timezone.now().isoformat(), "by": approved_by_id, "remarks": state["remarks"]},
        )
        h.save(update_fields=["workflow_payload", "updated_at"])
        return ReceiptVoucherResult(h, "Approved.")

    @staticmethod
    @transaction.atomic
    def reject_voucher(voucher_id: int, rejected_by_id: Optional[int] = None, remarks: Optional[str] = None) -> ReceiptVoucherResult:
        h = ReceiptVoucherHeader.objects.select_for_update().get(pk=voucher_id)
        if int(h.status) in (int(ReceiptVoucherHeader.Status.POSTED), int(ReceiptVoucherHeader.Status.CANCELLED)):
            raise ValueError("Only draft/confirmed vouchers can be rejected.")
        state = ReceiptVoucherService._workflow_state(h.workflow_payload)
        state.update({
            "status": "REJECTED",
            "rejected_by": rejected_by_id,
            "rejected_at": timezone.now().isoformat(),
            "remarks": (remarks or "").strip() or None,
        })
        h.workflow_payload = ReceiptVoucherService._set_workflow_state(h.workflow_payload, state)
        h.workflow_payload = ReceiptVoucherService._append_audit(
            h.workflow_payload,
            {"action": "REJECTED", "at": timezone.now().isoformat(), "by": rejected_by_id, "remarks": state["remarks"]},
        )
        h.save(update_fields=["workflow_payload", "updated_at"])
        return ReceiptVoucherResult(h, "Rejected.")

    @staticmethod
    @transaction.atomic
    def post_voucher(voucher_id: int, posted_by_id: Optional[int] = None) -> ReceiptVoucherResult:
        h = (
            ReceiptVoucherHeader.objects
            .select_related("entity", "entityfinid", "subentity")
            .prefetch_related("allocations", "adjustments", "advance_adjustments")
            .get(pk=voucher_id)
        )
        if int(h.status) == int(ReceiptVoucherHeader.Status.CANCELLED):
            raise ValueError("Cannot post: voucher is cancelled.")
        if int(h.status) == int(ReceiptVoucherHeader.Status.POSTED):
            return ReceiptVoucherResult(h, "Already posted.")

        policy = ReceiptSettingsService.get_policy(h.entity_id, h.subentity_id)
        require_confirm = str(policy.controls.get("require_confirm_before_post", "on")).lower().strip() == "on"
        if require_confirm:
            if int(h.status) != int(ReceiptVoucherHeader.Status.CONFIRMED):
                raise ValueError("Only CONFIRMED vouchers can be posted.")
        else:
            if int(h.status) not in (int(ReceiptVoucherHeader.Status.DRAFT), int(ReceiptVoucherHeader.Status.CONFIRMED)):
                raise ValueError("Only DRAFT or CONFIRMED vouchers can be posted.")
            if int(h.status) == int(ReceiptVoucherHeader.Status.DRAFT):
                ReceiptVoucherService.confirm_voucher(h.id, confirmed_by_id=posted_by_id)
                h.refresh_from_db()

        workflow_state = ReceiptVoucherService._workflow_state(h.workflow_payload)
        if str(policy.controls.get("receipt_maker_checker", "off")).lower().strip() == "hard":
            if workflow_state.get("status") != "APPROVED":
                raise ValueError("Voucher must be approved before posting by policy.")
        warnings: list[str] = []

        # Recompute monetary totals from live rows before posting so stale draft values
        # do not incorrectly block posting after edits or policy changes.
        live_adjustment_total = ReceiptVoucherService._compute_adjustment_total(
            h.adjustments.values("amount", "settlement_effect")
        )
        live_advance_rows = list(h.advance_adjustments.all())
        live_advance_total = ReceiptVoucherService._sum_advance_adjustments(
            [{"adjusted_amount": x.adjusted_amount} for x in live_advance_rows]
        )
        live_effective_amount = ReceiptVoucherService._effective_settlement_amount(
            q2(h.cash_received_amount),
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

        allocation_rows = ReceiptVoucherService._fresh_allocation_rows(h)
        over_settlement_rule = str(policy.controls.get("over_settlement_rule", "block")).lower().strip()
        amount_match_level = str(policy.controls.get("allocation_amount_match_rule", "hard")).lower().strip()
        allocation_policy = str(policy.controls.get("allocation_policy", "manual")).lower().strip()
        effective_amount = live_effective_amount
        total_support_amount = q2(live_effective_amount + live_advance_total)
        should_auto_allocate = (
            not allocation_rows
            and h.receipt_type == ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE
            and total_support_amount > ZERO2
        )
        if should_auto_allocate and allocation_policy not in {"fifo", "manual"}:
            should_auto_allocate = False
        if should_auto_allocate:
            fifo_rows = ReceiptVoucherService._auto_fifo_allocations(
                entity_id=h.entity_id,
                entityfinid_id=h.entityfinid_id,
                subentity_id=h.subentity_id,
                customer_id=h.received_from_id,
                target_amount=total_support_amount,
                controls=policy.controls,
            )
            for row in fifo_rows:
                ReceiptVoucherAllocation.objects.create(
                    receipt_voucher=h,
                    open_item_id=row["open_item"],
                    settled_amount=row["settled_amount"],
                    is_full_settlement=bool(row.get("is_full_settlement", False)),
                    is_advance_adjustment=bool(row.get("is_advance_adjustment", False)),
                )
            if fifo_rows:
                allocation_rows = ReceiptVoucherService._fresh_allocation_rows(h)

        if str(policy.controls.get("require_allocation_on_post", "hard")).lower().strip() == "hard":
            if h.receipt_type == ReceiptVoucherHeader.ReceiptType.AGAINST_INVOICE and not allocation_rows:
                raise ValueError("Allocations are required for AGAINST_INVOICE posting.")
            if (
                h.receipt_type == ReceiptVoucherHeader.ReceiptType.ADVANCE
                and str(policy.controls.get("allow_advance_without_allocation", "on")).lower().strip() == "off"
                and not allocation_rows
            ):
                raise ValueError("Allocations are required for ADVANCE posting by policy.")
            if (
                h.receipt_type == ReceiptVoucherHeader.ReceiptType.ON_ACCOUNT
                and str(policy.controls.get("allow_on_account_without_allocation", "on")).lower().strip() == "off"
                and not allocation_rows
            ):
                raise ValueError("Allocations are required for ON_ACCOUNT posting by policy.")

        if allocation_rows:
            allocation_total = ReceiptVoucherService._sum_allocations(
                [{"settled_amount": r.settled_amount} for r in allocation_rows]
            )
            ReceiptVoucherService._validate_advance_adjustments(
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
            warnings.extend(ReceiptVoucherService._validate_allocations(h, [
                {"open_item": r.open_item_id, "settled_amount": r.settled_amount}
                for r in allocation_rows
            ], over_settlement_rule=over_settlement_rule, controls=policy.controls))
            try:
                warnings.extend(
                    ReceiptVoucherService._validate_allocation_effective_match(
                        effective_amount=total_support_amount,
                        allocation_total=allocation_total,
                        level=amount_match_level,
                    )
                )
            except ValueError:
                raise ValueError(
                    f"Allocation total {q2(allocation_total)} does not match settlement support amount {q2(total_support_amount)} before posting."
                )

        if live_advance_rows and str(policy.controls.get("sync_ar_settlement_on_post", "on")).lower().strip() != "on":
            raise ValueError("Advance adjustments require AR settlement sync to be enabled.")

        if str(policy.controls.get("sync_ar_settlement_on_post", "on")).lower().strip() == "on":
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
                            "note": "Receipt voucher cash allocation",
                        })
                if cash_lines:
                    created = SalesArService.create_settlement(
                        entity_id=h.entity_id,
                        entityfinid_id=h.entityfinid_id,
                        subentity_id=h.subentity_id,
                        customer_id=h.received_from_id,
                        settlement_type="receipt",
                        settlement_date=h.voucher_date,
                        reference_no=h.voucher_code or h.reference_number,
                        external_voucher_no=h.reference_number,
                        remarks=h.narration,
                        lines=cash_lines,
                        amount=None,
                    )
                    posted = SalesArService.post_settlement(
                        settlement_id=created.settlement.id,
                        posted_by_id=posted_by_id or h.created_by_id,
                    )
                    h.ap_settlement_id = posted.settlement.id

            for adj in live_advance_rows:
                created = SalesArService.create_settlement(
                    entity_id=h.entity_id,
                    entityfinid_id=h.entityfinid_id,
                    subentity_id=h.subentity_id,
                    customer_id=h.received_from_id,
                    settlement_type="advance_adjustment",
                    settlement_date=h.voucher_date,
                    reference_no=h.voucher_code or h.reference_number,
                    external_voucher_no=h.reference_number,
                    remarks=adj.remarks or h.narration,
                    lines=[{
                        "open_item_id": adj.open_item_id,
                        "amount": q2(adj.adjusted_amount),
                        "note": "Receipt voucher advance adjustment",
                    }],
                    amount=None,
                    advance_balance_id=adj.advance_balance_id,
                )
                posted = SalesArService.post_settlement(
                    settlement_id=created.settlement.id,
                    posted_by_id=posted_by_id or h.created_by_id,
                )
                adj.ap_settlement_id = posted.settlement.id
                adj.save(update_fields=["ap_settlement", "updated_at"])

        allocation_total = ReceiptVoucherService._sum_allocations(
            [{"settled_amount": r.settled_amount} for r in allocation_rows]
        ) if allocation_rows else ZERO2
        residual_advance = q2(total_support_amount - allocation_total)
        residual_advance = q2(residual_advance - live_advance_total)
        if residual_advance < ZERO2:
            residual_advance = ZERO2
        should_create_advance = (
            str(policy.controls.get("sync_advance_balance_on_post", "on")).lower().strip() == "on"
            and (
                h.receipt_type in {ReceiptVoucherHeader.ReceiptType.ADVANCE, ReceiptVoucherHeader.ReceiptType.ON_ACCOUNT}
                or (
                    residual_advance > ZERO2
                    and str(policy.controls.get("residual_to_advance_balance", "on")).lower().strip() == "on"
                )
            )
        )
        if should_create_advance:
            source_type = "receipt_advance"
            if h.receipt_type == ReceiptVoucherHeader.ReceiptType.ON_ACCOUNT:
                source_type = "on_account"
            adv_amount = effective_amount if h.receipt_type in {
                ReceiptVoucherHeader.ReceiptType.ADVANCE,
                ReceiptVoucherHeader.ReceiptType.ON_ACCOUNT,
            } else residual_advance
            if adv_amount > ZERO2 and not getattr(h, "customer_advance_balance", None):
                SalesArService.create_advance_balance(
                    entity_id=h.entity_id,
                    entityfinid_id=h.entityfinid_id,
                    subentity_id=h.subentity_id,
                    customer_id=h.received_from_id,
                    source_type=source_type,
                    credit_date=h.voucher_date,
                    reference_no=h.voucher_code or h.reference_number,
                    remarks=h.narration,
                    amount=adv_amount,
                    receipt_voucher_id=h.id,
                )

        try:
            ReceiptVoucherPostingAdapter.post_receipt_voucher(
                header=h,
                adjustments=h.adjustments.all(),
                user_id=posted_by_id or h.created_by_id,
                config=ReceiptVoucherPostingConfig(),
            )
        except ValueError as exc:
            # Advance-only against-invoice settlements can have zero cash/adjustment impact.
            # In that case we still allow posting after AR settlement sync.
            if (
                "Computed customer settlement amount must be > 0." in str(exc)
                and live_advance_total > ZERO2
                and effective_amount <= ZERO2
            ):
                pass
            else:
                raise

        if str(policy.controls.get("sync_gstr1_table11_on_post", "on")).lower().strip() == "on":
            table11_mode = str(policy.controls.get("table11_amendment_mode", "snapshot")).lower().strip()
            ReceiptVoucherService._sync_gstr1_table11_rows(
                header=h,
                live_advance_rows=live_advance_rows,
                track_amendments=(table11_mode == "snapshot"),
            )

        h.status = ReceiptVoucherHeader.Status.POSTED
        h.approved_at = h.approved_at or timezone.now()
        h.workflow_payload = ReceiptVoucherService._append_audit(
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
        return ReceiptVoucherResult(h, msg)

    @staticmethod
    @transaction.atomic
    def unpost_voucher(voucher_id: int, unposted_by_id: Optional[int] = None) -> ReceiptVoucherResult:
        h = (
            ReceiptVoucherHeader.objects
            .select_related("entity", "entityfinid", "subentity")
            .prefetch_related("allocations", "adjustments", "advance_adjustments")
            .get(pk=voucher_id)
        )
        if int(h.status) != int(ReceiptVoucherHeader.Status.POSTED):
            raise ValueError("Only POSTED vouchers can be unposted.")

        if h.ap_settlement_id:
            SalesArService.cancel_settlement(
                settlement_id=int(h.ap_settlement_id),
                cancelled_by_id=unposted_by_id or h.created_by_id,
            )
            h.ap_settlement_id = None

        for adj in h.advance_adjustments.all():
            if adj.ap_settlement_id:
                SalesArService.cancel_settlement(
                    settlement_id=int(adj.ap_settlement_id),
                    cancelled_by_id=unposted_by_id or h.created_by_id,
                )
                adj.ap_settlement_id = None
                adj.save(update_fields=["ap_settlement", "updated_at"])

        if getattr(h, "customer_advance_balance", None):
            adv = h.customer_advance_balance
            if adv.is_open or q2(adv.adjusted_amount) == ZERO2:
                adv.is_open = False
                adv.outstanding_amount = ZERO2
                adv.save(update_fields=["is_open", "outstanding_amount", "updated_at"])
            else:
                raise ValueError("Cannot unpost receipt voucher: linked advance balance is already adjusted.")

        ReceiptVoucherService._unsync_gstr1_table11_rows(header=h)

        ReceiptVoucherPostingAdapter.unpost_receipt_voucher(
            header=h,
            adjustments=h.adjustments.all(),
            user_id=unposted_by_id or h.created_by_id,
        )

        policy = ReceiptSettingsService.get_policy(h.entity_id, h.subentity_id)
        unpost_target = str(policy.controls.get("unpost_target_status", "confirmed")).lower().strip()
        h.status = (
            ReceiptVoucherHeader.Status.DRAFT
            if unpost_target == "draft"
            else ReceiptVoucherHeader.Status.CONFIRMED
        )
        h.workflow_payload = ReceiptVoucherService._append_audit(
            h.workflow_payload,
            {"action": "UNPOSTED", "at": timezone.now().isoformat(), "by": unposted_by_id or h.created_by_id},
        )
        h.save(update_fields=["status", "ap_settlement", "workflow_payload", "updated_at"])
        return ReceiptVoucherResult(h, "Unposted with reversal entry.")

    @staticmethod
    @transaction.atomic
    def cancel_voucher(voucher_id: int, reason: Optional[str] = None, cancelled_by_id: Optional[int] = None) -> ReceiptVoucherResult:
        h = ReceiptVoucherHeader.objects.get(pk=voucher_id)
        if int(h.status) == int(ReceiptVoucherHeader.Status.POSTED):
            raise ValueError("Posted voucher cannot be cancelled in Phase-1.")
        if int(h.status) == int(ReceiptVoucherHeader.Status.CANCELLED):
            return ReceiptVoucherResult(h, "Already cancelled.")
        h.status = ReceiptVoucherHeader.Status.CANCELLED
        h.is_cancelled = True
        h.cancel_reason = (reason or "").strip() or None
        h.cancelled_by_id = cancelled_by_id
        h.cancelled_at = timezone.now()
        h.workflow_payload = ReceiptVoucherService._append_audit(
            h.workflow_payload,
            {"action": "CANCELLED", "at": timezone.now().isoformat(), "by": cancelled_by_id, "reason": h.cancel_reason},
        )
        h.save(update_fields=["status", "is_cancelled", "cancel_reason", "cancelled_by", "cancelled_at", "workflow_payload", "updated_at"])
        return ReceiptVoucherResult(h, "Cancelled.")


