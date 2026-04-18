from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import NotFound, ValidationError

from entity.models import Entity, EntityOwnershipV2, SubEntity
from financial.models import Ledger, account, accountHead, accounttype
from financial.services import create_account_with_synced_ledger, sync_ledger_for_account
from posting.adapters.year_opening import YearOpeningPostingAdapter
from posting.common.static_accounts import StaticAccountCodes
from posting.models import EntityStaticAccountMap, StaticAccount, StaticAccountGroup
from posting.services.static_accounts import StaticAccountService
from reports.services.controls.opening_policy import resolve_opening_policy, summarize_opening_policy


@dataclass(frozen=True)
class PostingSetupTarget:
    code: str
    name: str
    kind: str
    ownership_id: int | None
    ownership_name: str | None
    ownership_type: str | None
    account_preference: str | None
    suggested_ledger_name: str
    static_account_id: int | None
    mapping_id: int | None
    account_id: int | None
    ledger_id: int | None
    status: str


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_key(value: str | None) -> str:
    return _safe_text(value).lower().replace("&", " and ")


def _normalize_preference(value: Any) -> str:
    text = _safe_text(value).lower()
    if text in {"capital", "current", "auto"}:
        return text
    return "auto"


def _entity_scope(entity_id: int, subentity_id: int | None = None) -> tuple[Entity, SubEntity | None]:
    entity = Entity.objects.filter(pk=entity_id).first()
    if entity is None:
        raise NotFound("Entity not found.")
    subentity = None
    if subentity_id is not None:
        subentity = SubEntity.objects.filter(pk=subentity_id, entity_id=entity_id).first()
        if subentity is None:
            raise ValidationError({"subentity": "Subentity does not belong to the entity."})
    return entity, subentity


def _ownership_rows(entity_id: int) -> list[dict[str, Any]]:
    try:
        rows = list(
            EntityOwnershipV2.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("-is_primary", "id")
            .values(
                "id",
                "ownership_type",
                "name",
                "share_percentage",
                "capital_contribution",
                "effective_from",
                "effective_to",
                "account_preference",
                "agreement_reference",
                "designation",
                "remarks",
                "is_primary",
            )
        )
    except Exception:
        return []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "id": row.get("id"),
                "ownership_type": _safe_text(row.get("ownership_type")).lower() or "other",
                "name": _safe_text(row.get("name")),
                "share_percentage": row.get("share_percentage"),
                "capital_contribution": row.get("capital_contribution"),
                "effective_from": row.get("effective_from").isoformat() if row.get("effective_from") else None,
                "effective_to": row.get("effective_to").isoformat() if row.get("effective_to") else None,
                "account_preference": _safe_text(row.get("account_preference")).lower() or "auto",
                "agreement_reference": row.get("agreement_reference"),
                "designation": row.get("designation"),
                "remarks": row.get("remarks"),
                "is_primary": bool(row.get("is_primary")),
            }
        )
    return normalized


def _resolve_account_type(entity_id: int, candidates: Iterable[str]) -> accounttype | None:
    qs = accounttype.objects.filter(Q(entity_id=entity_id) | Q(entity__isnull=True))
    for candidate in candidates:
        match = qs.filter(accounttypename__iexact=candidate).order_by("-entity_id").first()
        if match:
            return match
    return None


def _resolve_account_head(entity_id: int, candidates: Iterable[str]) -> accountHead | None:
    qs = accountHead.objects.filter(Q(entity_id=entity_id) | Q(entity__isnull=True))
    for candidate in candidates:
        match = qs.filter(name__iexact=candidate).order_by("-entity_id").first()
        if match:
            return match
    return None


def _target_name_prefix(constitution_mode: str, row: dict[str, Any] | None, *, kind: str) -> str:
    if kind == "inventory":
        return "Opening Inventory Carry Forward"
    if not row:
        return "Opening Equity Transfer"
    label = _safe_text(row.get("name")) or "Unnamed"
    preference = _safe_text(row.get("account_preference")).lower() or "auto"
    if constitution_mode == "proprietorship":
        return f"Opening Owner {'Current' if preference == 'current' else 'Capital'} - {label}"
    if constitution_mode in {"partnership", "llp"}:
        return f"Opening Partner {'Current' if preference == 'current' else 'Capital'} - {label}"
    return f"Opening Equity Transfer - {label}"


def _target_code(adapter: YearOpeningPostingAdapter, constitution_mode: str, row: dict[str, Any] | None, *, kind: str) -> str:
    if kind == "inventory":
        return _safe_text(StaticAccountCodes.OPENING_INVENTORY_CARRY_FORWARD).upper()
    if constitution_mode in {"company", "unconfigured", "mixed"} or not row:
        return _safe_text(StaticAccountCodes.OPENING_EQUITY_TRANSFER).upper()
    if row:
        return adapter._opening_role_code(constitution_mode=constitution_mode, row=row)  # noqa: SLF001 - service-level orchestration
    return _safe_text(StaticAccountCodes.OPENING_EQUITY_TRANSFER).upper()


def _static_group(kind: str) -> str:
    if kind == "inventory":
        return StaticAccountGroup.OTHER
    return StaticAccountGroup.EQUITY


def _existing_mapping(entity_id: int, code: str) -> EntityStaticAccountMap | None:
    static_acc = StaticAccount.objects.filter(code=code, is_active=True).first()
    if not static_acc:
        return None
    return (
        EntityStaticAccountMap.objects.filter(entity_id=entity_id, static_account=static_acc, is_active=True)
        .select_related("static_account", "account", "ledger")
        .first()
    )


def _build_target_row(
    *,
    code: str,
    name: str,
    kind: str,
    row: dict[str, Any] | None,
    mapping: EntityStaticAccountMap | None,
    static_acc: StaticAccount | None,
    edited_ledger_name: str | None = None,
    edited_account_preference: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    account_preference = _normalize_preference(row.get("account_preference")) if row else None
    mapped_account_name = _safe_text(mapping.account.accountname) if mapping and mapping.account else None
    mapped_ledger_name = _safe_text(mapping.ledger.name) if mapping and mapping.ledger else None
    return {
        "code": code,
        "name": name,
        "kind": kind,
        "ownership_id": row.get("id") if row else None,
        "ownership_name": row.get("name") if row else None,
        "ownership_type": row.get("ownership_type") if row else None,
        "account_preference": account_preference,
        "editable_ledger_name": _safe_text(edited_ledger_name) or name,
        "editable_account_preference": _normalize_preference(edited_account_preference or account_preference),
        "enabled": bool(enabled),
        "suggested_ledger_name": name,
        "mapped_account_name": mapped_account_name,
        "mapped_ledger_name": mapped_ledger_name,
        "static_account_id": static_acc.id if static_acc else None,
        "mapping_id": mapping.id if mapping else None,
        "account_id": mapping.account_id if mapping else None,
        "ledger_id": mapping.ledger_id if mapping else None,
        "status": "configured" if mapping and mapping.ledger_id else ("missing_static" if not static_acc else "missing_mapping"),
    }


def _proposal_targets(entity_id: int, *, opening_policy: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    adapter = YearOpeningPostingAdapter(entity_id=entity_id, opening_policy=opening_policy)
    constitution = adapter.build_constitution_context()
    rows = constitution["ownership_rows"]
    proposals: list[dict[str, Any]] = []

    if constitution["constitution_mode"] in {"partnership", "llp"} and rows:
        for row in rows:
            code = _target_code(adapter, constitution["constitution_mode"], row, kind="equity")
            name = _target_name_prefix(constitution["constitution_mode"], row, kind="equity")
            mapping = _existing_mapping(entity_id, code)
            static_acc = StaticAccount.objects.filter(code=code, is_active=True).first()
            proposals.append(
                _build_target_row(
                    code=code,
                    name=name,
                    kind="equity",
                    row=row,
                    mapping=mapping,
                    static_acc=static_acc,
                )
            )
    elif constitution["constitution_mode"] == "proprietorship" and rows:
        row = rows[0]
        code = _target_code(adapter, constitution["constitution_mode"], row, kind="equity")
        name = _target_name_prefix(constitution["constitution_mode"], row, kind="equity")
        mapping = _existing_mapping(entity_id, code)
        static_acc = StaticAccount.objects.filter(code=code, is_active=True).first()
        proposals.append(
            _build_target_row(
                code=code,
                name=name,
                kind="equity",
                row=row,
                mapping=mapping,
                static_acc=static_acc,
            )
        )
    else:
        code = _target_code(adapter, constitution["constitution_mode"], None, kind="equity")
        name = _target_name_prefix(constitution["constitution_mode"], None, kind="equity")
        mapping = _existing_mapping(entity_id, code)
        static_acc = StaticAccount.objects.filter(code=code, is_active=True).first()
        proposals.append(
            _build_target_row(
                code=code,
                name=name,
                kind="equity",
                row=None,
                mapping=mapping,
                static_acc=static_acc,
            )
        )

    inventory_code = _target_code(adapter, constitution["constitution_mode"], None, kind="inventory")
    inventory_name = _target_name_prefix(constitution["constitution_mode"], None, kind="inventory")
    inventory_mapping = _existing_mapping(entity_id, inventory_code)
    inventory_static = StaticAccount.objects.filter(code=inventory_code, is_active=True).first()
    proposals.append(
        _build_target_row(
            code=inventory_code,
            name=inventory_name,
            kind="inventory",
            row=None,
            mapping=inventory_mapping,
            static_acc=inventory_static,
        )
    )

    return constitution, proposals


def build_posting_setup_preview(*, entity_id: int, entityfin_id: int | None = None, subentity_id: int | None = None) -> dict[str, Any]:
    entity, subentity = _entity_scope(entity_id, subentity_id)
    opening_policy = resolve_opening_policy(entity_id)
    constitution, proposals = _proposal_targets(entity_id, opening_policy=opening_policy)
    validation_issues = constitution.get("validation_issues") or []
    configured = sum(1 for row in proposals if row["status"] == "configured")
    missing = sum(1 for row in proposals if row["status"] != "configured")
    auto = len(proposals)
    has_errors = any(issue.get("severity") == "error" for issue in validation_issues)
    preview_state = "blocked" if has_errors else ("ready" if missing == 0 else "review")
    warnings = [
        f"{row['code']} is {row['status'].replace('_', ' ')}."
        for row in proposals
        if row["status"] != "configured"
    ]
    warnings.extend(issue.get("message") for issue in validation_issues if issue.get("message"))

    return {
        "report_code": "posting_setup_preview",
        "report_name": "Automatic Posting Setup",
        "report_eyebrow": "Financial Controls",
        "entity_id": entity.id,
        "entity_name": entity.trade_name or entity.short_name or entity.entityname,
        "entityfin_id": entityfin_id,
        "entityfin_name": "Current FY" if entityfin_id is None else f"FY {entityfin_id}",
        "subentity_id": subentity.id if subentity else None,
        "subentity_name": subentity.subentityname if subentity else "All subentities",
        "generated_at": None,
        "constitution": constitution,
        "opening_policy": opening_policy,
        "opening_policy_summary": summarize_opening_policy(opening_policy),
        "summary_cards": [
            {"label": "Required roles", "value": auto, "note": "Automatic setup targets for ledgers and mappings", "tone": "accent"},
            {"label": "Configured", "value": configured, "note": "Targets already mapped in Posting", "tone": "neutral"},
            {"label": "Missing", "value": missing, "note": "Targets that can be auto-created now", "tone": "warning" if missing else "accent"},
            {"label": "Ownership rows", "value": len(constitution.get("ownership_rows") or []), "note": "Rows captured from entity onboarding", "tone": "neutral"},
            {"label": "Constitution source", "value": constitution.get("constitution_source") or "ownership rows", "note": "How the adapter resolved the rule set", "tone": "neutral"},
            {"label": "Validation issues", "value": len(validation_issues), "note": "Blocking or review issues detected before applying", "tone": "warning" if has_errors else "neutral"},
        ],
        "required_roles": proposals,
        "warnings": warnings,
        "validation_issues": validation_issues,
        "notes": [
            "This page is separate from entity onboarding.",
            "It auto-proposes the ledgers needed for posting and year opening.",
            "Posting engine remains the source of truth for final balances.",
            *(
                [f"Rule note: {note}" for note in (constitution.get("constitution_notes") or [])]
                if constitution.get("constitution_notes")
                else []
            ),
        ],
        "actions": {
            "can_preview": True,
            "can_refresh": True,
            "can_apply": not has_errors,
        },
        "preview_state": preview_state,
        "can_auto_provision": True,
    }


def _merge_user_targets(proposals: list[dict[str, Any]], overrides: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not overrides:
        return proposals
    merged: list[dict[str, Any]] = []
    override_by_code = {_safe_text(item.get("code")).upper(): item for item in overrides if _safe_text(item.get("code"))}
    for proposal in proposals:
        code = _safe_text(proposal.get("code")).upper()
        override = override_by_code.get(code)
        merged_row = dict(proposal)
        if not override:
            merged.append(merged_row)
            continue
        if "enabled" in override:
            merged_row["enabled"] = bool(override.get("enabled"))
        if "editable_ledger_name" in override:
            merged_row["editable_ledger_name"] = _safe_text(override.get("editable_ledger_name")) or merged_row["editable_ledger_name"]
        if "suggested_ledger_name" in override:
            merged_row["editable_ledger_name"] = _safe_text(override.get("suggested_ledger_name")) or merged_row["editable_ledger_name"]
        if "editable_account_preference" in override:
            merged_row["editable_account_preference"] = _normalize_preference(override.get("editable_account_preference"))
        if "account_preference" in override:
            merged_row["editable_account_preference"] = _normalize_preference(override.get("account_preference"))
        merged.append(merged_row)
    return merged or proposals


def _resolve_target_ledger_names(
    *,
    kind: str,
    suggestion: str,
    constitution_mode: str,
    row: dict[str, Any] | None,
    edited_ledger_name: str | None = None,
) -> tuple[str, str, str]:
    ledger_name = _safe_text(edited_ledger_name) or suggestion
    legal_name = ledger_name
    if _safe_text(edited_ledger_name):
        return ledger_name, legal_name, suggestion
    if kind == "inventory":
        ledger_name = "Opening Inventory Carry Forward"
        legal_name = ledger_name
    elif row:
        label = _safe_text(row.get("name")) or "Unnamed"
        preference = _normalize_preference(row.get("account_preference"))
        role = "Current" if preference == "current" else "Capital"
        if constitution_mode == "proprietorship":
            ledger_name = f"Opening Owner {role} - {label}"
        elif constitution_mode in {"partnership", "llp"}:
            ledger_name = f"Opening Partner {role} - {label}"
        else:
            ledger_name = f"Opening Equity Transfer - {label}"
        legal_name = ledger_name
    return ledger_name, legal_name, suggestion


def _existing_account_by_name(entity_id: int, name: str) -> account | None:
    normalized = _normalize_key(name)
    return (
        account.objects.filter(entity_id=entity_id)
        .filter(Q(accountname__iexact=name) | Q(legalname__iexact=name))
        .first()
        or next(
            (
                acc
                for acc in account.objects.filter(entity_id=entity_id).only("id", "accountname", "legalname", "ledger_id")
                if _normalize_key(acc.accountname) == normalized or _normalize_key(acc.legalname) == normalized
            ),
            None,
        )
    )


def _apply_target(*, entity: Entity, adapter: YearOpeningPostingAdapter, target: dict[str, Any], constitution_mode: str, row: dict[str, Any] | None, created_by=None) -> dict[str, Any]:
    kind = target["kind"]
    if not target.get("enabled", True):
        static_code = _safe_text(target.get("code"))
        return {
            "code": static_code,
            "static_account_id": None,
            "account_id": None,
            "ledger_id": None,
            "mapping_id": None,
            "static_created": False,
            "account_created": False,
            "ledger_created": False,
            "mapping_created": False,
            "mapping_updated": False,
            "skipped": True,
        }
    row_preference = _normalize_preference(target.get("editable_account_preference") or target.get("account_preference"))
    row = dict(row or {})
    if row_preference != "auto":
        row["account_preference"] = row_preference
    static_code = _target_code(adapter, constitution_mode, row if kind != "inventory" else None, kind=kind)
    static_name = _safe_text(target.get("editable_ledger_name")) or _safe_text(target.get("name"))
    static_group = _static_group(kind)
    static_acc, static_created = StaticAccount.objects.get_or_create(
        code=static_code,
        defaults={
            "name": static_name,
            "group": static_group,
            "is_required": True,
            "is_active": True,
            "description": static_name,
        },
    )
    static_updates = []
    if static_acc.name != static_name:
        static_acc.name = static_name
        static_updates.append("name")
    if static_acc.group != static_group:
        static_acc.group = static_group
        static_updates.append("group")
    if not static_acc.is_required:
        static_acc.is_required = True
        static_updates.append("is_required")
    if not static_acc.is_active:
        static_acc.is_active = True
        static_updates.append("is_active")
    if static_acc.description != static_name:
        static_acc.description = static_name
        static_updates.append("description")
    if static_updates:
        static_acc.save(update_fields=static_updates)

    ledger_name, legal_name, _ = _resolve_target_ledger_names(
        kind=kind,
        suggestion=static_name,
        constitution_mode=constitution_mode,
        row=row,
        edited_ledger_name=target.get("editable_ledger_name"),
    )
    existing_map = _existing_mapping(entity.id, static_code)
    account_obj = existing_map.account if existing_map and existing_map.account else _existing_account_by_name(entity.id, ledger_name)
    account_created = False
    ledger_created = False
    if account_obj is None:
        if kind == "inventory":
            accounthead_obj = _resolve_account_head(entity.id, ["Opening Stock", "Current Assets"])
            accounttype_obj = _resolve_account_type(entity.id, ["Current Assets", "Bank and Cash"])
        else:
            accounthead_obj = _resolve_account_head(
                entity.id,
                ["Capital and Equity", "Equity", "Proprietor Capital", "Partner Capital"],
            )
            accounttype_obj = _resolve_account_type(entity.id, ["Capital and Equity", "Equity"])
        account_obj = create_account_with_synced_ledger(
            account_data={
                "entity": entity,
                "accountname": ledger_name,
                "legalname": legal_name,
                "canbedeleted": False,
                "isactive": True,
                "createdby": created_by,
            },
            ledger_overrides={
                "name": ledger_name,
                "legal_name": legal_name,
                "is_party": False,
                "is_system": True,
                "canbedeleted": False,
                "createdby": created_by,
                **({"accounthead": accounthead_obj} if accounthead_obj else {}),
                **({"accounttype": accounttype_obj} if accounttype_obj else {}),
            },
        )
        account_created = True
        ledger_created = True
    elif not account_obj.ledger_id:
        sync_ledger_for_account(
            account_obj,
            ledger_overrides={
                "name": ledger_name,
                "legal_name": legal_name,
                "is_party": False,
                "is_system": True,
                "canbedeleted": False,
                "createdby": created_by or account_obj.createdby,
            },
        )
        ledger_created = True
    else:
        ledger = account_obj.ledger
        ledger.name = ledger_name
        ledger.legal_name = legal_name
        ledger.is_party = False
        ledger.is_system = True
        ledger.canbedeleted = False
        ledger.createdby = created_by or ledger.createdby
        if kind == "inventory":
            ledger.accounthead = ledger.accounthead or _resolve_account_head(entity.id, ["Opening Stock", "Current Assets"])
            ledger.accounttype = ledger.accounttype or _resolve_account_type(entity.id, ["Current Assets", "Bank and Cash"])
        else:
            ledger.accounthead = ledger.accounthead or _resolve_account_head(
                entity.id,
                ["Capital and Equity", "Equity", "Proprietor Capital", "Partner Capital"],
            )
            ledger.accounttype = ledger.accounttype or _resolve_account_type(entity.id, ["Capital and Equity", "Equity"])
        ledger.save()
        if account_obj.accountname != ledger_name:
            account_obj.accountname = ledger_name
        if account_obj.legalname != legal_name:
            account_obj.legalname = legal_name
        account_obj.save(update_fields=["accountname", "legalname"] if account_obj.pk else None)

    mapping, created = EntityStaticAccountMap.objects.update_or_create(
        entity=entity,
        sub_entity=None,
        static_account=static_acc,
        defaults={
            "account": account_obj,
            "ledger": account_obj.ledger,
            "effective_from": None,
            "is_active": True,
            "createdby": created_by,
        },
    )
    return {
        "code": static_code,
        "static_account_id": static_acc.id,
        "account_id": account_obj.id if account_obj else None,
        "ledger_id": account_obj.ledger_id if account_obj else None,
        "mapping_id": mapping.id if mapping else None,
        "static_created": static_created,
        "account_created": account_created,
        "ledger_created": ledger_created,
        "mapping_created": created,
        "mapping_updated": bool(existing_map and not created),
    }


@transaction.atomic
def apply_posting_setup(*, entity_id: int, entityfin_id: int | None = None, subentity_id: int | None = None, created_by=None, target_overrides: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    entity, _ = _entity_scope(entity_id, subentity_id)
    opening_policy = resolve_opening_policy(entity_id)
    adapter = YearOpeningPostingAdapter(entity_id=entity_id, opening_policy=opening_policy)
    constitution, proposals = _proposal_targets(entity_id, opening_policy=opening_policy)
    validation_issues = constitution.get("validation_issues") or []
    if any(issue.get("severity") == "error" for issue in validation_issues):
        raise ValidationError(
            {
                "detail": "Posting setup cannot be applied until constitution validation passes.",
                "validation_issues": validation_issues,
            }
        )
    proposals = _merge_user_targets(proposals, target_overrides)
    if not any(row.get("enabled", True) for row in proposals):
        raise ValidationError({"targets": "At least one provisioning target must remain enabled."})
    applied: list[dict[str, Any]] = []
    created_static_accounts = 0
    created_ledgers = 0
    created_mappings = 0
    updated_mappings = 0
    touched_codes: set[str] = set()

    ownership_index = {row.get("id"): row for row in constitution.get("ownership_rows") or []}
    for proposal in proposals:
        row = ownership_index.get(proposal.get("ownership_id"))
        outcome = _apply_target(
            entity=entity,
            adapter=adapter,
            target=proposal,
            constitution_mode=constitution["constitution_mode"],
            row=row,
            created_by=created_by,
        )
        touched_codes.add(outcome["code"])
        created_static_accounts += 1 if outcome["static_created"] else 0
        created_ledgers += 1 if outcome["ledger_created"] else 0
        created_mappings += 1 if outcome["mapping_created"] else 0
        updated_mappings += 1 if outcome["mapping_updated"] else 0
        applied.append(outcome)

    StaticAccountService.invalidate(entity.id)

    preview = build_posting_setup_preview(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id)
    return {
        "status": "success",
        "message": "Posting setup provisioned successfully.",
        "report_code": "posting_setup_apply",
        "entity_id": entity.id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "applied": {
            "created_static_accounts": created_static_accounts,
            "created_ledgers": created_ledgers,
            "created_mappings": created_mappings,
            "updated_mappings": updated_mappings,
            "touched_codes": sorted(touched_codes),
            "provisioned": applied,
            "constitution": constitution,
            "validation_issues": validation_issues,
        },
        "preview": preview,
    }
