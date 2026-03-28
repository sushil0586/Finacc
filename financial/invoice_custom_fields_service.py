from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db.models import Q

from financial.models import InvoiceCustomFieldDefinition, InvoiceCustomFieldDefault


class InvoiceCustomFieldService:
    @staticmethod
    def _specificity_rank(defn: InvoiceCustomFieldDefinition, party_account_id: int | None, subentity_id: int | None) -> int:
        rank = 0
        if party_account_id and defn.applies_to_account_id == party_account_id:
            rank += 2
        if subentity_id and defn.subentity_id == subentity_id:
            rank += 1
        return rank

    @classmethod
    def get_effective_definitions(
        cls,
        *,
        entity_id: int,
        module: str,
        subentity_id: int | None = None,
        party_account_id: int | None = None,
    ) -> list[InvoiceCustomFieldDefinition]:
        qs = InvoiceCustomFieldDefinition.objects.filter(
            entity_id=entity_id,
            module=module,
            isactive=True,
        ).filter(
            Q(subentity_id=subentity_id) | Q(subentity__isnull=True),
            Q(applies_to_account_id=party_account_id) | Q(applies_to_account__isnull=True),
        ).order_by("order_no", "id")

        by_key: dict[str, InvoiceCustomFieldDefinition] = {}
        for row in qs:
            existing = by_key.get(row.key)
            if existing is None:
                by_key[row.key] = row
                continue
            current_rank = cls._specificity_rank(row, party_account_id, subentity_id)
            existing_rank = cls._specificity_rank(existing, party_account_id, subentity_id)
            if current_rank > existing_rank:
                by_key[row.key] = row
        return list(by_key.values())

    @staticmethod
    def _validate_one_value(defn: InvoiceCustomFieldDefinition, value: Any) -> Any:
        if value in (None, ""):
            return value

        field_type = defn.field_type
        if field_type == InvoiceCustomFieldDefinition.FieldType.TEXT:
            return str(value)
        if field_type == InvoiceCustomFieldDefinition.FieldType.NUMBER:
            try:
                return str(Decimal(str(value)))
            except (InvalidOperation, TypeError, ValueError):
                raise ValueError(f"{defn.key} must be a valid number.")
        if field_type == InvoiceCustomFieldDefinition.FieldType.DATE:
            if isinstance(value, (date, datetime)):
                return value.strftime("%Y-%m-%d")
            text = str(value).strip()
            try:
                datetime.strptime(text, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"{defn.key} must be in YYYY-MM-DD format.")
            return text
        if field_type == InvoiceCustomFieldDefinition.FieldType.BOOLEAN:
            if isinstance(value, bool):
                return value
            lowered = str(value).strip().lower()
            if lowered in {"true", "1", "yes", "y"}:
                return True
            if lowered in {"false", "0", "no", "n"}:
                return False
            raise ValueError(f"{defn.key} must be boolean.")
        if field_type == InvoiceCustomFieldDefinition.FieldType.SELECT:
            options = [str(x) for x in (defn.options_json or [])]
            if str(value) not in options:
                raise ValueError(f"{defn.key} must be one of configured options.")
            return str(value)
        if field_type == InvoiceCustomFieldDefinition.FieldType.MULTISELECT:
            if not isinstance(value, list):
                raise ValueError(f"{defn.key} must be an array.")
            options = {str(x) for x in (defn.options_json or [])}
            for item in value:
                if str(item) not in options:
                    raise ValueError(f"{defn.key} contains invalid option: {item}.")
            return [str(x) for x in value]
        return value

    @classmethod
    def validate_payload(
        cls,
        *,
        entity_id: int,
        module: str,
        payload: dict[str, Any] | None,
        subentity_id: int | None = None,
        party_account_id: int | None = None,
    ) -> dict[str, Any]:
        data = payload or {}
        if not isinstance(data, dict):
            raise ValueError("custom_fields must be an object.")

        defs = cls.get_effective_definitions(
            entity_id=entity_id,
            module=module,
            subentity_id=subentity_id,
            party_account_id=party_account_id,
        )
        defs_by_key = {d.key: d for d in defs}

        unknown = [key for key in data.keys() if key not in defs_by_key]
        if unknown:
            raise ValueError(f"Unknown custom field keys: {', '.join(sorted(unknown))}.")

        normalized: dict[str, Any] = {}
        for key, raw in data.items():
            normalized[key] = cls._validate_one_value(defs_by_key[key], raw)

        for defn in defs:
            if not defn.is_required:
                continue
            val = normalized.get(defn.key)
            if val in (None, "", []):
                raise ValueError(f"{defn.key} is required.")
        return normalized

    @classmethod
    def get_defaults_map(
        cls,
        *,
        entity_id: int,
        module: str,
        party_account_id: int,
        subentity_id: int | None = None,
    ) -> dict[str, Any]:
        defs = cls.get_effective_definitions(
            entity_id=entity_id,
            module=module,
            subentity_id=subentity_id,
            party_account_id=party_account_id,
        )
        if not defs:
            return {}

        def_ids = [d.id for d in defs]
        rows = InvoiceCustomFieldDefault.objects.filter(
            definition_id__in=def_ids,
            party_account_id=party_account_id,
            isactive=True,
        ).select_related("definition")
        return {row.definition.key: row.default_value for row in rows}
