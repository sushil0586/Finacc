from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.db import transaction

from financial.models import Ledger, accountHead, accounttype
from posting.common.static_accounts import StaticAccountCodes
from posting.models import EntityStaticAccountMap


@dataclass(frozen=True)
class ManufacturingHeadPolicy:
    code: str
    head_name: str
    account_type_name: str
    account_type_code: str
    detailsingroup: int
    drcr_effect: str
    balance_type: bool


MANUFACTURING_HEAD_POLICIES: tuple[ManufacturingHeadPolicy, ...] = (
    ManufacturingHeadPolicy(
        code=StaticAccountCodes.MANUFACTURING_WIP,
        head_name="Manufacturing WIP Control",
        account_type_name="Current Assets",
        account_type_code="1100",
        detailsingroup=3,
        drcr_effect="Debit",
        balance_type=True,
    ),
    ManufacturingHeadPolicy(
        code=StaticAccountCodes.MANUFACTURING_FINISHED_GOODS,
        head_name="Manufacturing Finished Goods Control",
        account_type_name="Current Assets",
        account_type_code="1100",
        detailsingroup=3,
        drcr_effect="Debit",
        balance_type=True,
    ),
    ManufacturingHeadPolicy(
        code=StaticAccountCodes.MANUFACTURING_CONSUMPTION,
        head_name="Manufacturing Consumption",
        account_type_name="Direct Expenses",
        account_type_code="5100",
        detailsingroup=1,
        drcr_effect="Debit",
        balance_type=True,
    ),
    ManufacturingHeadPolicy(
        code=StaticAccountCodes.MANUFACTURING_OVERHEAD_ABSORPTION,
        head_name="Manufacturing Overhead Absorption",
        account_type_name="Direct Income",
        account_type_code="4100",
        detailsingroup=1,
        drcr_effect="Credit",
        balance_type=False,
    ),
    ManufacturingHeadPolicy(
        code=StaticAccountCodes.MANUFACTURING_MATERIAL_VARIANCE,
        head_name="Manufacturing Material Variance",
        account_type_name="Direct Expenses",
        account_type_code="5100",
        detailsingroup=1,
        drcr_effect="Debit",
        balance_type=True,
    ),
    ManufacturingHeadPolicy(
        code=StaticAccountCodes.MANUFACTURING_YIELD_VARIANCE,
        head_name="Manufacturing Yield Variance",
        account_type_name="Direct Expenses",
        account_type_code="5100",
        detailsingroup=1,
        drcr_effect="Debit",
        balance_type=True,
    ),
    ManufacturingHeadPolicy(
        code=StaticAccountCodes.MANUFACTURING_ADDITIONAL_COST_EXPENSE,
        head_name="Manufacturing Additional Cost Expense",
        account_type_name="Direct Expenses",
        account_type_code="5100",
        detailsingroup=1,
        drcr_effect="Debit",
        balance_type=True,
    ),
)


def _next_head_code(entity_id: int, minimum: int = 9300) -> int:
    used = set(accountHead.objects.filter(entity_id=entity_id).values_list("code", flat=True))
    code = minimum
    while code in used:
        code += 1
    return code


def _get_or_create_account_type(*, entity_id: int, policy: ManufacturingHeadPolicy, apply_changes: bool):
    existing = (
        accounttype.objects.filter(entity_id=entity_id, accounttypename__iexact=policy.account_type_name)
        .order_by("id")
        .first()
    )
    if existing or not apply_changes:
        return existing

    return accounttype.objects.create(
        entity_id=entity_id,
        accounttypename=policy.account_type_name,
        accounttypecode=policy.account_type_code,
        balanceType=policy.balance_type,
    )


def _get_or_create_account_head(*, entity_id: int, policy: ManufacturingHeadPolicy, acc_type, apply_changes: bool):
    existing = (
        accountHead.objects.filter(entity_id=entity_id, name__iexact=policy.head_name)
        .order_by("id")
        .first()
    )
    if existing or not apply_changes:
        return existing

    return accountHead.objects.create(
        entity_id=entity_id,
        name=policy.head_name,
        code=_next_head_code(entity_id),
        accounttype=acc_type,
        drcreffect=policy.drcr_effect,
        detailsingroup=policy.detailsingroup,
        balanceType="Debit" if policy.balance_type else "Credit",
        canbedeleted=False,
    )


@transaction.atomic
def classify_manufacturing_static_account_heads(
    *,
    entity_id: int,
    codes: Iterable[str] | None = None,
    apply_changes: bool = False,
) -> dict:
    selected_codes = set(codes or [policy.code for policy in MANUFACTURING_HEAD_POLICIES])
    policy_by_code = {policy.code: policy for policy in MANUFACTURING_HEAD_POLICIES if policy.code in selected_codes}
    if not policy_by_code:
        return {"heads_created": 0, "types_created": 0, "ledgers_updated": 0, "missing_mappings": [], "touched_codes": []}

    existing_type_ids = set(accounttype.objects.filter(entity_id=entity_id).values_list("id", flat=True))
    existing_head_ids = set(accountHead.objects.filter(entity_id=entity_id).values_list("id", flat=True))
    maps = (
        EntityStaticAccountMap.objects.filter(
            entity_id=entity_id,
            is_active=True,
            static_account__code__in=list(policy_by_code.keys()),
        )
        .select_related("static_account", "ledger")
        .order_by("static_account__code", "sub_entity_id", "id")
    )

    map_by_code = {}
    for mapping in maps:
        map_by_code.setdefault(mapping.static_account.code, mapping)

    summary = {
        "heads_created": 0,
        "types_created": 0,
        "ledgers_updated": 0,
        "missing_mappings": [],
        "touched_codes": [],
    }

    for code, policy in policy_by_code.items():
        mapping = map_by_code.get(code)
        if not mapping or not mapping.ledger_id:
            summary["missing_mappings"].append(code)
            continue

        acc_type = _get_or_create_account_type(entity_id=entity_id, policy=policy, apply_changes=apply_changes)
        if acc_type and acc_type.id not in existing_type_ids:
            summary["types_created"] += 1
            existing_type_ids.add(acc_type.id)

        head = _get_or_create_account_head(entity_id=entity_id, policy=policy, acc_type=acc_type, apply_changes=apply_changes)
        if head and head.id not in existing_head_ids:
            summary["heads_created"] += 1
            existing_head_ids.add(head.id)

        ledger: Ledger = mapping.ledger
        needs_update = bool(
            head
            and (
                ledger.accounthead_id != head.id
                or ledger.accounttype_id != getattr(acc_type, "id", None)
                or ledger.creditaccounthead_id is not None
            )
        )
        if needs_update:
            summary["ledgers_updated"] += 1
            summary["touched_codes"].append(code)
            if apply_changes:
                ledger.accounthead = head
                ledger.creditaccounthead = None
                ledger.accounttype = acc_type
                ledger.is_party = False
                ledger.is_system = True
                ledger.canbedeleted = False
                ledger.save(update_fields=["accounthead", "creditaccounthead", "accounttype", "is_party", "is_system", "canbedeleted", "updated_at"])

    summary["touched_codes"] = sorted(set(summary["touched_codes"]))
    summary["missing_mappings"] = sorted(set(summary["missing_mappings"]))
    return summary
