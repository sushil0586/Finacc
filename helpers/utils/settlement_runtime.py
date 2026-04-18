from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from financial.models import account as FinancialAccount

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(x) -> Decimal:
    return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)


class SettlementVoucherRuntimeMixin:
    @staticmethod
    def _as_pk(value: Any) -> Any:
        if value in (None, ""):
            return None
        if hasattr(value, "pk"):
            return getattr(value, "pk")
        if hasattr(value, "id"):
            return getattr(value, "id")
        return value

    @staticmethod
    def _account_ledger_id(value: Any) -> Optional[int]:
        account_obj = value if hasattr(value, "ledger_id") else None
        account_id = getattr(account_obj, "pk", None) or (
            value if isinstance(value, int) else SettlementVoucherRuntimeMixin._as_pk(value)
        )
        ledger_id = getattr(account_obj, "ledger_id", None)
        if ledger_id:
            return int(ledger_id)
        if not account_id:
            return None
        row = (
            FinancialAccount.objects.filter(pk=account_id)
            .values_list("ledger_id", flat=True)
            .first()
        )
        return int(row) if row else None

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
            amount = row.get("adjusted_amount", row.get("settled_amount", ZERO2))
            total = q2(total + q2(amount or ZERO2))
        return total

    @staticmethod
    def _compute_adjustment_total(adjustments: Iterable[Dict[str, Any]], *, plus_code: str = "PLUS", minus_code: str = "MINUS") -> Decimal:
        total = ZERO2
        for row in adjustments or []:
            amt = q2(row.get("amount") or ZERO2)
            eff = str(row.get("settlement_effect") or plus_code)
            if eff == minus_code:
                total = q2(total - amt)
            else:
                total = q2(total + amt)
        return total
