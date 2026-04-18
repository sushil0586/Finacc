# posting/services/static_accounts.py
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Tuple

from posting.models import EntityStaticAccountMap, StaticAccount, StaticAccountGroup


@dataclass(frozen=True)
class StaticAccountResolved:
    code: str
    account_id: Optional[int]
    ledger_id: Optional[int] = None


@dataclass(frozen=True)
class StaticAccountSeedDef:
    code: str
    name: str
    group: str
    description: str
    is_required: bool


STATIC_ACCOUNT_MASTER_DEFS: Tuple[StaticAccountSeedDef, ...] = (
    StaticAccountSeedDef("PURCHASE_DEFAULT", "Purchase Default", StaticAccountGroup.PURCHASE, "Fallback purchase base account when a product/account line has no dedicated purchase account.", False),
    StaticAccountSeedDef("PURCHASE_MISC_EXPENSE", "Purchase Misc Expense", StaticAccountGroup.PURCHASE, "Fallback expense ledger for purchase charges and misc adjustments.", True),
    StaticAccountSeedDef("SALES_DEFAULT", "Sales Default", StaticAccountGroup.SALES, "Fallback sales revenue account when an item has no dedicated revenue account.", False),
    StaticAccountSeedDef("SALES_REVENUE", "Sales Revenue", StaticAccountGroup.SALES, "Default revenue ledger for sales posting.", False),
    StaticAccountSeedDef("SALES_OTHER_CHARGES_INCOME", "Sales Other Charges Income", StaticAccountGroup.SALES, "Income ledger for sales invoice other charges.", False),
    StaticAccountSeedDef("SALES_MISC_EXPENSE", "Sales Misc Expense", StaticAccountGroup.SALES, "Fallback sales-side expense ledger.", False),
    StaticAccountSeedDef("ITC_BLOCKED_EXPENSE", "ITC Blocked Expense", StaticAccountGroup.GST_INPUT, "Expense ledger for GST that is not claimable as ITC.", False),
    StaticAccountSeedDef("ROUND_OFF_INCOME", "Round Off Income", StaticAccountGroup.ROUND_OFF, "Round-off gain ledger.", True),
    StaticAccountSeedDef("ROUND_OFF_EXPENSE", "Round Off Expense", StaticAccountGroup.ROUND_OFF, "Round-off loss ledger.", True),
    StaticAccountSeedDef("INPUT_CGST", "Input CGST", StaticAccountGroup.GST_INPUT, "Input tax ledger for claimable CGST.", False),
    StaticAccountSeedDef("INPUT_SGST", "Input SGST", StaticAccountGroup.GST_INPUT, "Input tax ledger for claimable SGST.", False),
    StaticAccountSeedDef("INPUT_IGST", "Input IGST", StaticAccountGroup.GST_INPUT, "Input tax ledger for claimable IGST.", False),
    StaticAccountSeedDef("INPUT_CESS", "Input CESS", StaticAccountGroup.GST_INPUT, "Input tax ledger for claimable cess.", False),
    StaticAccountSeedDef("OUTPUT_CGST", "Output CGST", StaticAccountGroup.GST_OUTPUT, "Output tax liability ledger for CGST.", False),
    StaticAccountSeedDef("OUTPUT_SGST", "Output SGST", StaticAccountGroup.GST_OUTPUT, "Output tax liability ledger for SGST.", False),
    StaticAccountSeedDef("OUTPUT_IGST", "Output IGST", StaticAccountGroup.GST_OUTPUT, "Output tax liability ledger for IGST.", False),
    StaticAccountSeedDef("OUTPUT_CESS", "Output CESS", StaticAccountGroup.GST_OUTPUT, "Output tax liability ledger for cess.", False),
    StaticAccountSeedDef("RCM_CGST_PAYABLE", "RCM CGST Payable", StaticAccountGroup.RCM_PAYABLE, "Reverse-charge liability ledger for CGST.", False),
    StaticAccountSeedDef("RCM_SGST_PAYABLE", "RCM SGST Payable", StaticAccountGroup.RCM_PAYABLE, "Reverse-charge liability ledger for SGST.", False),
    StaticAccountSeedDef("RCM_IGST_PAYABLE", "RCM IGST Payable", StaticAccountGroup.RCM_PAYABLE, "Reverse-charge liability ledger for IGST.", False),
    StaticAccountSeedDef("RCM_CESS_PAYABLE", "RCM CESS Payable", StaticAccountGroup.RCM_PAYABLE, "Reverse-charge liability ledger for cess.", False),
    StaticAccountSeedDef("TDS_PAYABLE", "TDS Payable", StaticAccountGroup.TDS, "Liability ledger for income-tax TDS payable.", False),
    StaticAccountSeedDef("GST_TDS_PAYABLE", "GST TDS Payable", StaticAccountGroup.TDS, "Liability ledger for GST-TDS payable.", False),
    StaticAccountSeedDef("TCS_PAYABLE", "TCS Payable", StaticAccountGroup.TCS, "Liability ledger for TCS payable.", False),
    StaticAccountSeedDef("OPENING_EQUITY_TRANSFER", "Opening Equity Transfer", StaticAccountGroup.EQUITY, "Destination equity/capital/retained earnings ledger for year opening.", False),
    StaticAccountSeedDef("OPENING_INVENTORY_CARRY_FORWARD", "Opening Inventory Carry Forward", StaticAccountGroup.EQUITY, "Destination inventory/stock ledger for year opening.", False),
)


class StaticAccountService:
    """
    Seed + lookup helpers for static account master and entity mappings.
    Cache is per-process; invalidate if you change mappings frequently.
    """

    @staticmethod
    def seed_static_account_master(*, defs: Iterable[StaticAccountSeedDef] = STATIC_ACCOUNT_MASTER_DEFS) -> Dict[str, int]:
        created = 0
        updated = 0
        for item in defs:
            existing = StaticAccount.objects.filter(code=item.code).first()
            if existing is None:
                StaticAccount.objects.create(
                    code=item.code,
                    name=item.name,
                    group=item.group,
                    is_required=item.is_required,
                    is_active=True,
                    description=item.description,
                )
                created += 1
                continue

            changed = (
                existing.name != item.name
                or existing.group != item.group
                or bool(existing.is_required) != bool(item.is_required)
                or (existing.description or "") != item.description
                or not existing.is_active
            )
            if changed:
                existing.name = item.name
                existing.group = item.group
                existing.is_required = item.is_required
                existing.description = item.description
                existing.is_active = True
                existing.save(update_fields=["name", "group", "is_required", "description", "is_active"])
                updated += 1
        return {"created": created, "updated": updated}

    @staticmethod
    @lru_cache(maxsize=2048)
    def _entity_map(entity_id: int) -> Dict[str, StaticAccountResolved]:
        qs = (
            EntityStaticAccountMap.objects
            .filter(entity_id=entity_id, is_active=True, static_account__is_active=True)
            .select_related("static_account")
            .values_list("static_account__code", "account_id", "ledger_id")
        )
        return {
            code: StaticAccountResolved(code=code, account_id=acc_id, ledger_id=ledger_id)
            for code, acc_id, ledger_id in qs
        }

    @staticmethod
    def invalidate(entity_id: int) -> None:
        # Clear whole cache (simple and safe). If needed, implement per-key invalidation later.
        StaticAccountService._entity_map.cache_clear()

    @staticmethod
    def get_account_id(entity_id: int, code: str, *, required: bool = True) -> Optional[int]:
        m = StaticAccountService._entity_map(entity_id)
        resolved = m.get(code)
        acc_id = resolved.account_id if resolved else None
        if required and not acc_id:
            raise ValueError(f"Missing static account mapping: entity={entity_id} code={code}")
        return acc_id

    @staticmethod
    def get_ledger_id(entity_id: int, code: str, *, required: bool = True) -> Optional[int]:
        m = StaticAccountService._entity_map(entity_id)
        resolved = m.get(code)
        ledger_id = resolved.ledger_id if resolved else None
        if required and not ledger_id:
            raise ValueError(f"Missing static ledger mapping: entity={entity_id} code={code}")
        return ledger_id

    @staticmethod
    def get_group(entity_id: int, group: str) -> Dict[str, int]:
        codes = list(
            StaticAccount.objects
            .filter(group=group, is_active=True)
            .values_list("code", flat=True)
        )
        m = StaticAccountService._entity_map(entity_id)
        return {c: m[c].account_id for c in codes if c in m}

    @staticmethod
    def missing_required_codes(entity_id: int) -> List[str]:
        required_codes = list(
            StaticAccount.objects
            .filter(is_required=True, is_active=True)
            .values_list("code", flat=True)
        )
        m = StaticAccountService._entity_map(entity_id)
        return [c for c in required_codes if c not in m]
