from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError, NotFound

from entity.models import Entity, SubEntity
from financial.models import account, Ledger
from posting.models import EntityStaticAccountMap, StaticAccount
from posting.services.static_accounts import StaticAccountService


class StaticAccountStatus:
    CONFIGURED = "CONFIGURED"
    CONFIGURED_INHERITED = "CONFIGURED_INHERITED"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    MISSING_OPTIONAL = "MISSING_OPTIONAL"


@dataclass(frozen=True)
class ResolvedRow:
    code: str
    name: str
    group: str
    is_required: bool
    description: Optional[str]
    account_id: Optional[int]
    ledger_id: Optional[int]
    scope: Optional[str]  # "sub_entity", "entity", or None
    effective_from: Optional[date]
    status: str
    inherited: bool


class StaticAccountMappingService:
    @staticmethod
    def _get_ledger_account_profile(ledger: Ledger) -> Optional[account]:
        try:
            return ledger.account_profile
        except account.DoesNotExist:
            return None

    @staticmethod
    def _validate_scope(entity_id: int, sub_entity_id: Optional[int]) -> Optional[SubEntity]:
        if not Entity.objects.filter(id=entity_id).exists():
            raise NotFound("Entity not found.")
        if sub_entity_id is None:
            return None
        try:
            return SubEntity.objects.get(id=sub_entity_id, entity_id=entity_id)
        except SubEntity.DoesNotExist:
            raise ValidationError("sub_entity_id does not belong to the entity.")

    @staticmethod
    def _pick_preferred(current: Optional[EntityStaticAccountMap], candidate: EntityStaticAccountMap) -> EntityStaticAccountMap:
        if current is None:
            return candidate
        # Prefer the mapping with the latest effective_from (null counts as oldest)
        cur_date = current.effective_from
        cand_date = candidate.effective_from
        if cur_date is None and cand_date is not None:
            return candidate
        if cand_date is None and cur_date is not None:
            return current
        if cur_date is None and cand_date is None:
            return current
        return candidate if cand_date >= cur_date else current

    @classmethod
    def _collect_maps(
        cls,
        *,
        entity_id: int,
        effective_on: Optional[date],
    ) -> Dict[Tuple[Optional[int], int], EntityStaticAccountMap]:
        qs = (
            EntityStaticAccountMap.objects.filter(
                entity_id=entity_id,
                is_active=True,
                static_account__is_active=True,
            )
            .select_related("static_account", "account", "ledger", "sub_entity")
        )
        if effective_on:
            qs = qs.filter(Q(effective_from__lte=effective_on) | Q(effective_from__isnull=True))

        result: Dict[Tuple[Optional[int], int], EntityStaticAccountMap] = {}
        for row in qs:
            key = (row.sub_entity_id, row.static_account_id)
            result[key] = cls._pick_preferred(result.get(key), row)
        return result

    @classmethod
    def resolve(
        cls,
        *,
        entity_id: int,
        sub_entity_id: Optional[int],
        effective_on: Optional[date] = None,
    ) -> dict:
        cls._validate_scope(entity_id, sub_entity_id)
        statics = list(
            StaticAccount.objects.filter(is_active=True)
            .order_by("sort_order", "code")
            .only("id", "code", "name", "group", "is_required", "description")
        )
        map_lookup = cls._collect_maps(entity_id=entity_id, effective_on=effective_on)

        summary = {
            "configured": 0,
            "configured_inherited": 0,
            "missing_required": 0,
            "missing_optional": 0,
        }
        groups: Dict[str, List[ResolvedRow]] = {}

        for sa in statics:
            scoped = map_lookup.get((sub_entity_id, sa.id)) if sub_entity_id else None
            fallback = map_lookup.get((None, sa.id))
            resolved = scoped or fallback

            if resolved:
                inherited = bool(fallback and not scoped and sub_entity_id is not None)
                status = (
                    StaticAccountStatus.CONFIGURED_INHERITED
                    if inherited
                    else StaticAccountStatus.CONFIGURED
                )
                summary["configured_inherited" if inherited else "configured"] += 1
                scope = "sub_entity" if scoped else "entity"
                effective_from = resolved.effective_from
                account_id = resolved.account_id
                ledger_id = resolved.ledger_id
            else:
                inherited = False
                scope = None
                effective_from = None
                account_id = None
                ledger_id = None
                if sa.is_required:
                    status = StaticAccountStatus.MISSING_REQUIRED
                    summary["missing_required"] += 1
                else:
                    status = StaticAccountStatus.MISSING_OPTIONAL
                    summary["missing_optional"] += 1

            row = ResolvedRow(
                code=sa.code,
                name=sa.name,
                group=sa.group,
                is_required=sa.is_required,
                description=sa.description,
                account_id=account_id,
                ledger_id=ledger_id,
                scope=scope,
                effective_from=effective_from,
                status=status,
                inherited=inherited,
            )
            groups.setdefault(sa.group, []).append(row)

        return {
            "summary": summary,
            "groups": groups,
        }

    @classmethod
    @transaction.atomic
    def upsert_one(
        cls,
        *,
        entity_id: int,
        static_account_code: str,
        account_id: Optional[int],
        ledger_id: Optional[int],
        sub_entity_id: Optional[int],
        effective_from: Optional[date],
        actor,
    ) -> ResolvedRow:
        sub = cls._validate_scope(entity_id, sub_entity_id)
        try:
            static_acc = StaticAccount.objects.get(code=static_account_code, is_active=True)
        except StaticAccount.DoesNotExist:
            raise ValidationError(f"Static account '{static_account_code}' not found or inactive.")

        acc, led = cls._resolve_account_ledger_pair(
            entity_id=entity_id,
            account_id=account_id,
            ledger_id=ledger_id,
        )

        cls._deactivate_existing(entity_id, static_acc.id, sub_entity_id)

        EntityStaticAccountMap.objects.create(
            entity_id=entity_id,
            sub_entity_id=sub.id if sub else None,
            static_account=static_acc,
            account=acc,
            ledger=led,
            effective_from=effective_from,
            createdby=actor if getattr(actor, "id", None) else None,
        )

        StaticAccountService.invalidate(entity_id)
        resolved = cls.resolve(entity_id=entity_id, sub_entity_id=sub_entity_id, effective_on=effective_from or date.today())
        return cls._pick_row(resolved, static_acc.group, static_acc.code)

    @classmethod
    @transaction.atomic
    def bulk_upsert(
        cls,
        *,
        entity_id: int,
        sub_entity_id: Optional[int],
        effective_from: Optional[date],
        items: Iterable[dict],
        actor,
    ) -> dict:
        sub = cls._validate_scope(entity_id, sub_entity_id)
        # last occurrence wins for same code
        deduped = {}
        for row in items:
            deduped[row["static_account_code"]] = row
        items = list(deduped.values())

        codes = [row["static_account_code"] for row in items]
        statics = {s.code: s for s in StaticAccount.objects.filter(code__in=codes, is_active=True)}
        missing_codes = [c for c in codes if c not in statics]
        if missing_codes:
            raise ValidationError(f"Unknown static_account_code(s): {', '.join(sorted(set(missing_codes)))}")

        account_ids = [row["account_id"] for row in items if row.get("account_id")]
        ledger_ids = [row["ledger_id"] for row in items if row.get("ledger_id")]

        accounts = {a.id: a for a in account.objects.filter(entity_id=entity_id, id__in=account_ids)}

        ledgers = {}
        if ledger_ids:
            ledgers = {
                l.id: l
                for l in Ledger.objects.filter(entity_id=entity_id, id__in=ledger_ids).select_related("account_profile")
            }
            if len(ledgers) != len(set(ledger_ids)):
                bad = set(ledger_ids) - set(ledgers)
                raise ValidationError(f"ledger_id(s) not found for entity: {', '.join(map(str, bad))}")

        item_errors: List[str] = []
        resolved_pairs: List[Tuple[dict, Optional[account], Optional[Ledger]]] = []
        for item in items:
            provided_account_id = item.get("account_id")
            provided_ledger_id = item.get("ledger_id")
            acc = accounts.get(provided_account_id) if provided_account_id else None
            led = ledgers.get(provided_ledger_id) if provided_ledger_id else None
            ledger_profile = cls._get_ledger_account_profile(led) if led else None

            if acc is None and led is None:
                item_errors.append(
                    f"{item['static_account_code']}: provide either a valid account_id or ledger_id."
                )
                continue

            if acc is None and ledger_profile:
                acc = ledger_profile

            if led and ledger_profile and acc and acc.id != ledger_profile.id:
                item_errors.append(
                    f"{item['static_account_code']}: account_id {acc.id} does not match ledger_id {led.id} account_profile_id {ledger_profile.id}."
                )
                continue

            resolved_pairs.append((item, acc, led))

        if item_errors:
            raise ValidationError(item_errors)

        # lock existing rows in scope
        static_ids = [statics[c].id for c in codes]
        existing = list(
            EntityStaticAccountMap.objects.select_for_update().filter(
                entity_id=entity_id,
                sub_entity_id=sub.id if sub else None,
                static_account_id__in=static_ids,
                is_active=True,
            )
        )
        for row in existing:
            row.is_active = False
        if existing:
            EntityStaticAccountMap.objects.bulk_update(existing, ["is_active", "updated_at"])

        new_rows = []
        for item, acc, led in resolved_pairs:
            sa = statics[item["static_account_code"]]
            new_rows.append(
                EntityStaticAccountMap(
                    entity_id=entity_id,
                    sub_entity_id=sub.id if sub else None,
                    static_account=sa,
                    account=acc,
                    ledger=led,
                    effective_from=effective_from,
                    createdby=actor if getattr(actor, "id", None) else None,
                )
            )
        EntityStaticAccountMap.objects.bulk_create(new_rows)

        StaticAccountService.invalidate(entity_id)
        resolved = cls.resolve(entity_id=entity_id, sub_entity_id=sub_entity_id, effective_on=effective_from or date.today())
        rows = [cls._pick_row(resolved, sa.group, sa.code) for sa in statics.values()]
        return {
            "updated": rows,
            "summary": resolved["summary"],
        }

    @classmethod
    @transaction.atomic
    def deactivate(
        cls,
        *,
        entity_id: int,
        static_account_code: str,
        sub_entity_id: Optional[int],
    ) -> ResolvedRow:
        sub = cls._validate_scope(entity_id, sub_entity_id)
        try:
            static_acc = StaticAccount.objects.get(code=static_account_code, is_active=True)
        except StaticAccount.DoesNotExist:
            raise ValidationError(f"Static account '{static_account_code}' not found or inactive.")

        updated = EntityStaticAccountMap.objects.filter(
            entity_id=entity_id,
            sub_entity_id=sub.id if sub else None,
            static_account=static_acc,
            is_active=True,
        )
        if updated.exists():
            updated.update(is_active=False)
            StaticAccountService.invalidate(entity_id)

        resolved = cls.resolve(entity_id=entity_id, sub_entity_id=sub_entity_id, effective_on=date.today())
        return cls._pick_row(resolved, static_acc.group, static_acc.code)

    @staticmethod
    def _pick_row(resolved: dict, group: str, code: str) -> ResolvedRow:
        for row in resolved["groups"].get(group, []):
            if row.code == code:
                return row
        raise NotFound("Resolved row not found after operation.")

    @staticmethod
    def _deactivate_existing(entity_id: int, static_account_id: int, sub_entity_id: Optional[int]) -> None:
        qs = EntityStaticAccountMap.objects.filter(
            entity_id=entity_id,
            sub_entity_id=sub_entity_id,
            static_account_id=static_account_id,
            is_active=True,
        )
        if qs.exists():
            qs.update(is_active=False)

    @staticmethod
    def _validate_account(entity_id: int, account_id: int) -> account:
        try:
            return account.objects.get(id=account_id, entity_id=entity_id)
        except account.DoesNotExist:
            raise ValidationError("account_id not found for entity.")

    @staticmethod
    def _validate_ledger(entity_id: int, ledger_id: int) -> Ledger:
        try:
            return Ledger.objects.get(id=ledger_id, entity_id=entity_id)
        except Ledger.DoesNotExist:
            raise ValidationError("ledger_id not found for entity.")

    @classmethod
    def _resolve_account_ledger_pair(
        cls,
        *,
        entity_id: int,
        account_id: Optional[int],
        ledger_id: Optional[int],
    ) -> Tuple[Optional[account], Optional[Ledger]]:
        led: Optional[Ledger] = None
        if ledger_id:
            led = Ledger.objects.select_related("account_profile").filter(id=ledger_id, entity_id=entity_id).first()
            if not led:
                raise ValidationError("ledger_id not found for entity.")
        ledger_profile = cls._get_ledger_account_profile(led) if led else None

        acc: Optional[account] = None
        if account_id:
            acc = cls._validate_account(entity_id, account_id)

        if acc is None:
            if ledger_profile:
                acc = ledger_profile
            elif led is None:
                raise ValidationError("Provide a valid account_id or ledger_id.")

        if led and ledger_profile and acc and acc.id != ledger_profile.id:
            raise ValidationError("account_id does not match the selected ledger_id account profile.")

        return acc, led

    @classmethod
    def validate_required(
        cls,
        *,
        entity_id: int,
        sub_entity_id: Optional[int],
        effective_on: Optional[date],
    ) -> dict:
        resolved = cls.resolve(entity_id=entity_id, sub_entity_id=sub_entity_id, effective_on=effective_on)
        missing_required = []
        missing_optional = []
        for group_rows in resolved["groups"].values():
            for row in group_rows:
                if row.status == StaticAccountStatus.MISSING_REQUIRED:
                    missing_required.append(row.code)
                if row.status == StaticAccountStatus.MISSING_OPTIONAL:
                    missing_optional.append(row.code)

        return {
            "missing_required": sorted(missing_required),
            "missing_optional": sorted(missing_optional),
            "issues": [
                f"Missing required static account mapping for {code}" for code in sorted(missing_required)
            ],
        }
