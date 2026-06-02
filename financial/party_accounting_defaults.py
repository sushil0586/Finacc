from __future__ import annotations

from typing import Iterable

from financial.governance import resolve_financial_master_rule
from financial.models import accountHead, accounttype


PARTY_ACCOUNTING_RULES = {
    "Customer": {
        "account_type_codes": ("1009",),
        "account_type_names": ("Party",),
        "debit_head_codes": (8000,),
        "credit_head_codes": (7000,),
    },
    "Vendor": {
        "account_type_codes": ("1009",),
        "account_type_names": ("Party",),
        "debit_head_codes": (6100, 8000),
        "credit_head_codes": (7000,),
    },
    "Both": {
        "account_type_codes": ("1009",),
        "account_type_names": ("Party",),
        "debit_head_codes": (8000,),
        "credit_head_codes": (7000,),
    },
    "Bank": {
        "account_type_codes": ("1200", "1003"),
        "account_type_names": ("Bank and Cash",),
        "debit_head_codes": (2000,),
        "credit_head_codes": (2000,),
    },
    "Employee": {
        "account_type_codes": ("1009",),
        "account_type_names": ("Party",),
        "debit_head_codes": (6100, 8000),
        "credit_head_codes": (7000,),
    },
    "Government": {
        "account_type_codes": ("2100", "1005"),
        "account_type_names": ("Current Liabilities",),
        "debit_head_codes": (5300,),
        "credit_head_codes": (5300,),
    },
}


def normalize_party_type(partytype):
    value = str(partytype or "").strip()
    if not value:
        return ""
    for key in PARTY_ACCOUNTING_RULES:
        if key.lower() == value.lower():
            return key
    return value


def get_party_accounting_rule(partytype):
    normalized = normalize_party_type(partytype)
    return PARTY_ACCOUNTING_RULES.get(normalized)


def _matches_account_type(item, *, codes: Iterable[str], names: Iterable[str]) -> bool:
    item_code = str(getattr(item, "accounttypecode", "") or getattr(item, "code", "") or "").strip()
    item_name = str(getattr(item, "accounttypename", "") or getattr(item, "name", "") or "").strip().lower()
    return item_code in set(codes) or item_name in {name.strip().lower() for name in names}


def resolve_party_accounting_from_maps(*, type_map, head_map, partytype):
    config_rule = resolve_financial_master_rule(partytype=partytype)
    if config_rule:
        return {
            "accounttype": (
                type_map.get(config_rule.suggested_account_type.accounttypecode)
                if config_rule.suggested_account_type and config_rule.suggested_account_type.accounttypecode in type_map
                else config_rule.suggested_account_type
            ),
            "accounthead": (
                head_map.get(config_rule.suggested_debit_head.code)
                if config_rule.suggested_debit_head and config_rule.suggested_debit_head.code in head_map
                else config_rule.suggested_debit_head
            ),
            "creditaccounthead": (
                head_map.get(config_rule.suggested_credit_head.code)
                if config_rule.suggested_credit_head and config_rule.suggested_credit_head.code in head_map
                else config_rule.suggested_credit_head
            ),
        }

    rule = get_party_accounting_rule(partytype)
    if not rule:
        return {"accounttype": None, "accounthead": None, "creditaccounthead": None}

    account_type = next(
        (
            item
            for item in type_map.values()
            if _matches_account_type(item, codes=rule["account_type_codes"], names=rule["account_type_names"])
        ),
        None,
    )
    debit_head = next((head_map.get(code) for code in rule["debit_head_codes"] if head_map.get(code)), None)
    credit_head = next((head_map.get(code) for code in rule["credit_head_codes"] if head_map.get(code)), None) or debit_head
    return {
        "accounttype": account_type,
        "accounthead": debit_head,
        "creditaccounthead": credit_head,
    }


def resolve_party_accounting_ids(*, entity, partytype):
    config_rule = resolve_financial_master_rule(entity=entity, partytype=partytype)
    if config_rule:
        return {
            "accounttype_id": getattr(config_rule.suggested_account_type, "id", None),
            "accounthead_id": getattr(config_rule.suggested_debit_head, "id", None),
            "creditaccounthead_id": getattr(config_rule.suggested_credit_head, "id", None),
        }

    rule = get_party_accounting_rule(partytype)
    if entity is None or not rule:
        return {"accounttype_id": None, "accounthead_id": None, "creditaccounthead_id": None}

    account_type = next(
        (
            item
            for item in accounttype.objects.filter(entity=entity, isactive=True)
            if _matches_account_type(item, codes=rule["account_type_codes"], names=rule["account_type_names"])
        ),
        None,
    )
    heads = {
        row.code: row
        for row in accountHead.objects.filter(
            entity=entity,
            code__in=[*rule["debit_head_codes"], *rule["credit_head_codes"]],
            isactive=True,
        )
    }
    debit_head = next((heads.get(code) for code in rule["debit_head_codes"] if heads.get(code)), None)
    credit_head = next((heads.get(code) for code in rule["credit_head_codes"] if heads.get(code)), None) or debit_head
    return {
        "accounttype_id": getattr(account_type, "id", None),
        "accounthead_id": getattr(debit_head, "id", None),
        "creditaccounthead_id": getattr(credit_head, "id", None),
    }
