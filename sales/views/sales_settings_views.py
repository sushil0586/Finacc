from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from numbering.models import DocumentNumberSeries
from numbering.services import ensure_document_type, ensure_document_types_batch, ensure_series, validate_unique_series_pattern
from sales.models import SalesChoiceOverride, SalesLockPeriod
from sales.models.sales_settings import SalesSettings
from sales.services.sales_choices_service import SalesChoicesService
from sales.services.sales_settings_service import SalesSettingsService
from sales.views.rbac import require_sales_scope_permission
from helpers.utils.meta_cache import SALES_META_NAMESPACES, bump_meta_namespaces


def _choice_payload(choices) -> list[dict]:
    return [{"value": value, "label": label} for value, label in choices]


def _with_help(schema: list[dict], help_map: dict[str, str]) -> list[dict]:
    rows = []
    for item in schema:
        row = dict(item)
        if row.get("name") in help_map:
            row["help_text"] = help_map[row["name"]]
        rows.append(row)
    return rows


def _sections(schema: list[dict]) -> list[dict]:
    ordered_groups = []
    for item in schema:
        group = item.get("group") or "general"
        if group not in ordered_groups:
            ordered_groups.append(group)
    sections = [{"key": group, "title": group.replace("_", " ").title(), "source": "settings"} for group in ordered_groups]
    sections.append({"key": "numbering_series", "title": "Numbering Series", "source": "numbering_series"})
    sections.append({"key": "stock_policy", "title": "Stock Policy", "source": "stock_policy"})
    sections.append({"key": "lock_periods", "title": "Lock Periods", "source": "lock_periods"})
    sections.append({"key": "choice_overrides", "title": "Choice Overrides", "source": "choice_overrides"})
    return sections


SALES_SETTINGS_SCHEMA = _with_help(
    [
        {"name": "default_doc_code_invoice", "label": "Invoice Doc Code", "type": "string", "group": "numbering_defaults"},
        {"name": "default_doc_code_cn", "label": "Credit Note Doc Code", "type": "string", "group": "numbering_defaults"},
        {"name": "default_doc_code_dn", "label": "Debit Note Doc Code", "type": "string", "group": "numbering_defaults"},
        {"name": "default_workflow_action", "label": "Default Workflow", "type": "choice", "group": "workflow", "choices": _choice_payload(SalesSettings.DefaultWorkflowAction.choices)},
        {"name": "auto_derive_tax_regime", "label": "Auto Derive Tax Regime", "type": "boolean", "group": "tax"},
        {"name": "allow_mixed_taxability_in_one_invoice", "label": "Allow Mixed Taxability In One Invoice", "type": "boolean", "group": "tax"},
        {"name": "enable_einvoice", "label": "Enable E-Invoice", "type": "boolean", "group": "compliance"},
        {"name": "enable_eway", "label": "Enable E-Way", "type": "boolean", "group": "compliance"},
        {"name": "einvoice_entity_applicable", "label": "Entity Eligible For E-Invoice", "type": "boolean", "group": "compliance"},
        {"name": "eway_value_threshold", "label": "E-Way Threshold", "type": "decimal", "group": "compliance"},
        {"name": "compliance_applicability_mode", "label": "Compliance Applicability Mode", "type": "choice", "group": "compliance", "choices": _choice_payload(SalesSettings.ComplianceApplicabilityMode.choices)},
        {"name": "tcs_credit_note_policy", "label": "TCS Credit Note Policy", "type": "choice", "group": "compliance", "choices": _choice_payload(SalesSettings.TCSCreditNotePolicy.choices)},
        {"name": "auto_generate_einvoice_on_confirm", "label": "Auto Generate E-Invoice On Confirm", "type": "boolean", "group": "automation"},
        {"name": "auto_generate_einvoice_on_post", "label": "Auto Generate E-Invoice On Post", "type": "boolean", "group": "automation"},
        {"name": "auto_generate_eway_on_confirm", "label": "Auto Generate E-Way On Confirm", "type": "boolean", "group": "automation"},
        {"name": "auto_generate_eway_on_post", "label": "Auto Generate E-Way On Post", "type": "boolean", "group": "automation"},
        {"name": "prefer_irp_generate_einvoice_and_eway_together", "label": "Prefer Combined IRP Flow", "type": "boolean", "group": "automation"},
        {"name": "enforce_statutory_cancel_before_business_cancel", "label": "Require Statutory Cancel Before Business Cancel", "type": "boolean", "group": "automation"},
        {"name": "enable_round_off", "label": "Enable Round Off", "type": "boolean", "group": "rounding"},
        {"name": "round_grand_total_to", "label": "Round Grand Total To", "type": "integer", "group": "rounding"},
        {"name": "invoice_printing", "label": "Invoice Printing", "type": "json", "group": "printing"},
        {"name": "policy_controls", "label": "Policy Controls", "type": "json", "group": "policy"},
    ],
    {
        "default_doc_code_invoice": "Default document code used when generating sales invoice numbers.",
        "default_doc_code_cn": "Default document code used when generating credit note numbers.",
        "default_doc_code_dn": "Default document code used when generating debit note numbers.",
        "default_workflow_action": "Controls whether a new sales invoice saves as draft, confirms, or posts immediately.",
        "auto_derive_tax_regime": "Automatically derives tax regime based on seller and place-of-supply context.",
        "allow_mixed_taxability_in_one_invoice": "Allows multiple taxability patterns in a single invoice.",
        "enable_einvoice": "Master switch for e-invoice features.",
        "enable_eway": "Master switch for E-Way bill features.",
        "einvoice_entity_applicable": "Marks this entity as eligible for e-invoice workflow.",
        "eway_value_threshold": "Invoice value above which E-Way processing becomes applicable.",
        "compliance_applicability_mode": "Choose whether compliance stays auto-derived only or allows audited override.",
        "tcs_credit_note_policy": "Defines how TCS behaves when a sales credit note is created.",
        "auto_generate_einvoice_on_confirm": "Triggers e-invoice generation immediately on confirm.",
        "auto_generate_einvoice_on_post": "Triggers e-invoice generation immediately on post.",
        "auto_generate_eway_on_confirm": "Triggers E-Way generation immediately on confirm.",
        "auto_generate_eway_on_post": "Triggers E-Way generation immediately on post.",
        "prefer_irp_generate_einvoice_and_eway_together": "Uses combined IRP generation flow when supported.",
        "enforce_statutory_cancel_before_business_cancel": "Prevents business cancellation before statutory cancellation completes.",
        "enable_round_off": "Enables round-off handling for invoice totals.",
        "round_grand_total_to": "Number of decimal places to retain after round-off.",
        "invoice_printing": "Profile-driven invoice print settings (layout profiles, copy labels, section toggles).",
        "policy_controls": "Advanced enterprise policy controls for delete/confirm/match/settlement behavior.",
        "stock_policy": "Sales stock discipline for batch, expiry, FEFO, and negative stock handling.",
    },
)

NUMBERING_SERIES_SCHEMA = [
    {"name": "doc_code", "label": "Series Code", "type": "string"},
    {"name": "prefix", "label": "Prefix", "type": "string"},
    {"name": "suffix", "label": "Suffix", "type": "string"},
    {"name": "starting_number", "label": "Starting Number", "type": "integer"},
    {"name": "current_number", "label": "Next Number", "type": "integer"},
    {"name": "number_padding", "label": "Padding", "type": "integer"},
    {"name": "separator", "label": "Separator", "type": "string"},
    {"name": "reset_frequency", "label": "Reset Frequency", "type": "choice", "choices": _choice_payload(DocumentNumberSeries.RESET_CHOICES)},
    {"name": "include_year", "label": "Include Year", "type": "boolean"},
    {"name": "include_month", "label": "Include Month", "type": "boolean"},
    {"name": "custom_format", "label": "Custom Format", "type": "string"},
    {"name": "is_active", "label": "Active", "type": "boolean"},
]

LOCK_PERIOD_SCHEMA = [
    {"name": "lock_date", "label": "Lock Date", "type": "date"},
    {"name": "reason", "label": "Reason", "type": "string"},
]

EDITABLE_FIELDS = {
    "default_doc_code_invoice",
    "default_doc_code_cn",
    "default_doc_code_dn",
    "default_workflow_action",
    "auto_derive_tax_regime",
    "allow_mixed_taxability_in_one_invoice",
    "enable_einvoice",
    "enable_eway",
    "einvoice_entity_applicable",
    "eway_value_threshold",
    "compliance_applicability_mode",
    "auto_generate_einvoice_on_confirm",
    "auto_generate_einvoice_on_post",
    "auto_generate_eway_on_confirm",
    "auto_generate_eway_on_post",
    "prefer_irp_generate_einvoice_and_eway_together",
    "enforce_statutory_cancel_before_business_cancel",
    "tcs_credit_note_policy",
    "enable_round_off",
    "round_grand_total_to",
    "invoice_printing",
    "policy_controls",
}

SALES_DOC_TYPES = {
    "invoice": {"doc_key": "sales_invoice", "name": "Sales Invoice", "default_code_field": "default_doc_code_invoice", "fallback_code": "SINV"},
    "credit_note": {"doc_key": "sales_credit_note", "name": "Sales Credit Note", "default_code_field": "default_doc_code_cn", "fallback_code": "SCN"},
    "debit_note": {"doc_key": "sales_debit_note", "name": "Sales Debit Note", "default_code_field": "default_doc_code_dn", "fallback_code": "SDN"},
}

DOC_CODE_FALLBACKS = {
    config["default_code_field"]: config["fallback_code"]
    for config in SALES_DOC_TYPES.values()
}


class SalesSettingsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _valid_override_keys(catalog: dict[str, list[dict]]) -> dict[str, set[str]]:
        return {
            group: {item.get("key") for item in items if item.get("key")}
            for group, items in catalog.items()
        }

    @staticmethod
    def _is_private_override_key(key: Any) -> bool:
        return isinstance(key, str) and key.startswith("_")

    @staticmethod
    def _parse_int(raw_value: Any, field_name: str, *, required: bool) -> Optional[int]:
        if raw_value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise ValidationError({field_name: f"{field_name} must be an integer."})
        return None if field_name == "subentity_id" and value == 0 else value

    def _scope(self, request, *, require_entityfinid: bool) -> tuple[int, Optional[int], Optional[int]]:
        entity_id = self._parse_int(request.query_params.get("entity_id"), "entity_id", required=True)
        subentity_id = self._parse_int(request.query_params.get("subentity_id"), "subentity_id", required=False)
        entityfinid_id = self._parse_int(request.query_params.get("entityfinid"), "entityfinid", required=require_entityfinid)
        return entity_id, subentity_id, entityfinid_id

    def _list_lock_periods(self, *, entity_id: int, subentity_id: Optional[int]) -> list[dict]:
        qs = SalesLockPeriod.objects.filter(entity_id=entity_id)
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        return list(qs.order_by("lock_date", "id").values("id", "lock_date", "reason"))

    def _list_choice_overrides(self, *, entity_id: int, subentity_id: Optional[int], catalog: Optional[dict] = None) -> list[dict]:
        catalog = catalog if catalog is not None else SalesChoicesService.get_choices(entity_id=entity_id, subentity_id=subentity_id)
        valid_keys = self._valid_override_keys(catalog)
        qs = SalesChoiceOverride.objects.filter(entity_id=entity_id)
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        rows = []
        for row in qs.order_by("choice_group", "choice_key", "id").values("id", "choice_group", "choice_key", "is_enabled", "override_label"):
            group = row["choice_group"]
            key = row["choice_key"]
            if self._is_private_override_key(key):
                continue
            if group in valid_keys and key in valid_keys[group]:
                rows.append(row)
        return rows

    def _replace_lock_periods(
        self,
        rows: list[dict],
        *,
        entity_id: int,
        subentity_id: Optional[int],
        entityfinid_id: Optional[int],
    ) -> None:
        qs = SalesLockPeriod.objects.filter(entity_id=entity_id)
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        qs.delete()
        for row in rows:
            if not isinstance(row, dict) or not row.get("lock_date"):
                raise ValidationError({"lock_periods": "Each lock period must include lock_date."})
            SalesLockPeriod.objects.create(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                lock_date=row["lock_date"],
                reason=row.get("reason") or "",
            )

    def _replace_choice_overrides(self, rows: list[dict], *, entity_id: int, subentity_id: Optional[int]) -> None:
        catalog = SalesChoicesService.get_choices(entity_id=entity_id, subentity_id=subentity_id)
        valid_keys = self._valid_override_keys(catalog)
        qs = SalesChoiceOverride.objects.filter(entity_id=entity_id)
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        qs.delete()
        for row in rows:
            if not isinstance(row, dict):
                raise ValidationError({"choice_overrides": "Each override must be an object."})
            group = row.get("choice_group")
            key = row.get("choice_key")
            if self._is_private_override_key(key):
                continue
            if group not in valid_keys or key not in valid_keys[group]:
                raise ValidationError({"choice_overrides": f"Invalid override {group}:{key}."})
            SalesChoiceOverride.objects.create(entity_id=entity_id, subentity_id=subentity_id, choice_group=group, choice_key=key, is_enabled=bool(row.get("is_enabled", True)), override_label=row.get("override_label") or "")

    def _resolve_doc_types(self, settings_obj) -> dict[str, dict[str, Any]]:
        configs = []
        for row_key, config in SALES_DOC_TYPES.items():
            configs.append(
                {
                    "row_key": row_key,
                    "doc_key": config["doc_key"],
                    "name": config["name"],
                    "default_code": getattr(settings_obj, config["default_code_field"]) or config["fallback_code"],
                }
            )
        doc_types_by_key = ensure_document_types_batch(
            module="sales",
            configs=[
                {
                    "doc_key": row["doc_key"],
                    "name": row["name"],
                    "default_code": row["default_code"],
                }
                for row in configs
            ],
        )
        return {
            row["row_key"]: {
                "id": doc_types_by_key[row["doc_key"]].id,
                "doc_key": row["doc_key"],
                "name": row["name"],
            }
            for row in configs
            if row["doc_key"] in doc_types_by_key
        }

    def _series_payload(
        self,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        settings_obj,
        current_doc_numbers: Optional[dict[str, dict[str, Any]]] = None,
        doc_type_configs: Optional[dict[str, Any]] = None,
    ) -> list[dict]:
        doc_type_configs = doc_type_configs or self._resolve_doc_types(settings_obj)
        doc_type_ids = [doc_type["id"] for doc_type in doc_type_configs.values()]
        series_rows = DocumentNumberSeries.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type_id__in=doc_type_ids,
        )
        series_by_key = {
            (row.doc_type_id, row.doc_code): row
            for row in series_rows
        }
        rows = []
        for row_key, config in SALES_DOC_TYPES.items():
            doc_code = getattr(settings_obj, config["default_code_field"]) or config["fallback_code"]
            doc_type = doc_type_configs[row_key]
            doc_type_id = doc_type["id"]
            series = series_by_key.get((doc_type_id, doc_code))
            preview = (current_doc_numbers or {}).get(row_key)
            if preview is None:
                preview = SalesSettingsService.get_current_doc_no(
                    entity_id=entity_id,
                    entityfinid_id=entityfinid_id,
                    subentity_id=subentity_id,
                    doc_key=config["doc_key"],
                    doc_code=doc_code,
                )
            rows.append(
                {
                    "series_key": row_key,
                    "label": config["name"],
                    "doc_key": config["doc_key"],
                    "doc_type_id": doc_type_id,
                    "doc_code": doc_code,
                    "prefix": series.prefix if series else doc_code,
                    "suffix": series.suffix if series else "",
                    "starting_number": series.starting_number if series else 1,
                    "current_number": series.current_number if series else 1,
                    "number_padding": series.number_padding if series else 5,
                    "separator": series.separator if series else "-",
                    "reset_frequency": series.reset_frequency if series else "yearly",
                    "include_year": series.include_year if series else True,
                    "include_month": series.include_month if series else False,
                    "custom_format": series.custom_format if series else "",
                    "is_active": series.is_active if series else True,
                    "preview": preview,
                    "series_exists": bool(series),
                }
            )
        return rows

    @staticmethod
    def _get_doc_type(doc_key: str, name: str, default_code: str):
        return ensure_document_type(module="sales", doc_key=doc_key, name=name, default_code=default_code)

    @staticmethod
    def _doc_code_defaults(settings_obj) -> dict[str, str]:
        return {
            field: str(getattr(settings_obj, field, "") or "").strip()
            for field in DOC_CODE_FALLBACKS
        }

    @staticmethod
    def _setting_values(settings_obj) -> dict[str, Any]:
        return {
            field: deepcopy(getattr(settings_obj, field, None))
            for field in EDITABLE_FIELDS
        }

    @staticmethod
    def _model_field_default(field_name: str) -> Any:
        field = SalesSettings._meta.get_field(field_name)
        default = field.default
        if callable(default):
            default = default()
        return deepcopy(default)

    @staticmethod
    def _settings_values_match(left: Any, right: Any) -> bool:
        if left == right:
            return True
        if left in (None, "") and right in (None, ""):
            return True
        return str(left) == str(right)

    @staticmethod
    def _propagate_entity_doc_code_defaults(
        *,
        entity_id: int,
        subentity_id: Optional[int],
        settings_obj,
        previous_defaults: dict[str, str],
    ) -> None:
        if subentity_id is not None:
            return

        for field, fallback_code in DOC_CODE_FALLBACKS.items():
            previous_value = str(previous_defaults.get(field) or "").strip()
            next_value = str(getattr(settings_obj, field, "") or "").strip()
            if not next_value or next_value == previous_value:
                continue

            # Branch rows that still carry the old entity code or stock fallback are inherited in practice.
            # Preserve branches that have been intentionally customized to a different code.
            SalesSettings.objects.filter(
                entity_id=entity_id,
                subentity__isnull=False,
            ).filter(
                **{f"{field}__in": [previous_value, fallback_code, ""]}
            ).update(**{field: next_value})

    def _ensure_default_numbering_series(
        self,
        *,
        entity_id: int,
        entityfinid_id: Optional[int],
        subentity_id: Optional[int],
        settings_obj,
        previous_defaults: dict[str, str],
        user_id: Optional[int],
    ) -> None:
        if not entityfinid_id:
            return

        for config in SALES_DOC_TYPES.values():
            field = config["default_code_field"]
            doc_code = str(getattr(settings_obj, field, "") or config["fallback_code"]).strip()
            previous_doc_code = str(previous_defaults.get(field) or "").strip()
            if not doc_code or doc_code == previous_doc_code:
                continue

            doc_type = self._get_doc_type(config["doc_key"], config["name"], doc_code)
            series, _ = ensure_series(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type.id,
                doc_code=doc_code,
                prefix=doc_code,
                start=1,
                padding=5,
                reset="yearly",
                include_year=True,
                include_month=False,
            )
            if user_id and not series.created_by_id:
                series.created_by_id = user_id
                series.save(update_fields=["created_by"])

    @classmethod
    def _propagate_entity_setting_defaults(
        cls,
        *,
        entity_id: int,
        subentity_id: Optional[int],
        settings_obj,
        previous_values: dict[str, Any],
        updated_fields: set[str],
    ) -> None:
        if subentity_id is not None:
            return

        fields_to_check = [
            field
            for field in updated_fields
            if field in EDITABLE_FIELDS and field not in DOC_CODE_FALLBACKS
        ]
        if not fields_to_check:
            return

        for branch_settings in SalesSettings.objects.filter(entity_id=entity_id, subentity__isnull=False):
            branch_update_fields = []
            for field in fields_to_check:
                previous_value = previous_values.get(field)
                next_value = deepcopy(getattr(settings_obj, field, None))
                if cls._settings_values_match(next_value, previous_value):
                    continue
                current_value = getattr(branch_settings, field, None)
                default_value = cls._model_field_default(field)
                if (
                    cls._settings_values_match(current_value, previous_value)
                    or cls._settings_values_match(current_value, default_value)
                ):
                    setattr(branch_settings, field, next_value)
                    branch_update_fields.append(field)
            if branch_update_fields:
                branch_settings.save(update_fields=branch_update_fields)

    def _update_numbering_series(self, rows: list[dict], *, entity_id: int, entityfinid_id: int, subentity_id: Optional[int], settings_obj, user_id: Optional[int]) -> None:
        row_map = {row["series_key"]: row for row in rows if isinstance(row, dict) and row.get("series_key") in SALES_DOC_TYPES}
        for series_key, config in SALES_DOC_TYPES.items():
            if series_key not in row_map:
                continue
            row = row_map[series_key]
            doc_code = (row.get("doc_code") or getattr(settings_obj, config["default_code_field"]) or config["fallback_code"]).strip()
            if not doc_code:
                raise ValidationError({"numbering_series": f"doc_code is required for {series_key}."})

            setattr(settings_obj, config["default_code_field"], doc_code)
            doc_type = self._get_doc_type(config["doc_key"], config["name"], doc_code)
            if self._drop_unissued_generated_branch_series_if_conflicting(
                row,
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type.id,
                doc_code=doc_code,
            ):
                continue
            series, _ = ensure_series(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type.id,
                doc_code=doc_code,
                prefix=(row.get("prefix") if row.get("prefix") is not None else doc_code),
                start=int(row.get("starting_number") or 1),
                padding=int(row.get("number_padding") or 0),
                reset=(row.get("reset_frequency") or "none"),
                include_year=bool(row.get("include_year", False)),
                include_month=bool(row.get("include_month", False)),
            )
            series.prefix = row.get("prefix") or ""
            series.suffix = row.get("suffix") or ""
            series.starting_number = int(row.get("starting_number") or 1)
            series.current_number = int(row.get("current_number") or series.starting_number)
            series.number_padding = int(row.get("number_padding") or 0)
            series.separator = row.get("separator") or "-"
            series.reset_frequency = row.get("reset_frequency") or "none"
            series.include_year = bool(row.get("include_year", False))
            series.include_month = bool(row.get("include_month", False))
            series.custom_format = row.get("custom_format") or ""
            series.is_active = bool(row.get("is_active", True))
            if user_id and not series.created_by_id:
                series.created_by_id = user_id
            try:
                validate_unique_series_pattern(series=series, doc_label=config["name"])
            except ValueError as exc:
                raise ValidationError({"numbering_series": str(exc)})
            series.save()

        settings_obj.save()

    def _drop_unissued_generated_branch_series_if_conflicting(
        self,
        row: dict,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_type_id: int,
        doc_code: str,
    ) -> bool:
        if not subentity_id or not self._is_generated_default_series_row(row, doc_code=doc_code):
            return False

        branch_qs = DocumentNumberSeries.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type_id=doc_type_id,
            doc_code=doc_code,
        )
        existing_branch_series = branch_qs.first()
        if existing_branch_series and existing_branch_series.current_number > existing_branch_series.starting_number:
            return False

        conflict_qs = (
            DocumentNumberSeries.objects.filter(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                doc_type_id=doc_type_id,
                doc_code=doc_code,
                prefix=doc_code,
                suffix="",
                separator="-",
                include_year=True,
                include_month=False,
                custom_format="",
                is_active=True,
            )
            .exclude(subentity_id=subentity_id)
        )
        if existing_branch_series:
            conflict_qs = conflict_qs.exclude(pk=existing_branch_series.pk)
        if not conflict_qs.exists():
            return False

        branch_qs.delete()
        return True

    @staticmethod
    def _is_generated_default_series_row(row: dict, *, doc_code: str) -> bool:
        return (
            (row.get("prefix") or "") == doc_code
            and (row.get("suffix") or "") == ""
            and int(row.get("starting_number") or 1) == 1
            and int(row.get("current_number") or 1) == 1
            and int(row.get("number_padding") or 5) == 5
            and (row.get("separator") or "-") == "-"
            and (row.get("reset_frequency") or "yearly") == "yearly"
            and bool(row.get("include_year", True)) is True
            and bool(row.get("include_month", False)) is False
            and (row.get("custom_format") or "") == ""
            and bool(row.get("is_active", True)) is True
        )

    def _current_doc_numbers(self, *, entity_id: int, entityfinid_id: Optional[int], subentity_id: Optional[int], settings_obj) -> Optional[dict]:
        if not entityfinid_id:
            return None
        return SalesSettingsService.get_current_doc_numbers_batch(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_requests={
                "invoice": {
                    "doc_key": "sales_invoice",
                    "doc_code": settings_obj.default_doc_code_invoice,
                },
                "credit_note": {
                    "doc_key": "sales_credit_note",
                    "doc_code": settings_obj.default_doc_code_cn,
                },
                "debit_note": {
                    "doc_key": "sales_debit_note",
                    "doc_code": settings_obj.default_doc_code_dn,
                },
            },
        )

    def _payload(self, *, entity_id: int, subentity_id: Optional[int], entityfinid_id: Optional[int]) -> dict:
        settings_obj = SalesSettingsService.get_settings(entity_id, subentity_id, entityfinid_id=entityfinid_id)
        policy_controls = SalesSettingsService.effective_policy_controls(settings_obj)
        resolved_stock_policy = SalesSettingsService.get_stock_policy(
            entity_id=entity_id,
            subentity_id=subentity_id,
            entityfinid_id=entityfinid_id,
        )
        stock_policy = SalesSettingsService.get_stock_policy_payload(
            entity_id=entity_id,
            subentity_id=subentity_id,
            entityfinid_id=entityfinid_id,
            resolved_policy=resolved_stock_policy,
        )
        choice_catalog = SalesChoicesService.get_choices(entity_id=entity_id, subentity_id=subentity_id)
        doc_type_configs = self._resolve_doc_types(settings_obj) if entityfinid_id else {}
        current_doc_numbers = self._current_doc_numbers(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            settings_obj=settings_obj,
        )
        payload = {
            "seller": SalesSettingsService.get_seller_profile(entity_id=entity_id, subentity_id=subentity_id),
            "settings": {
                "default_doc_code_invoice": settings_obj.default_doc_code_invoice,
                "default_doc_code_cn": settings_obj.default_doc_code_cn,
                "default_doc_code_dn": settings_obj.default_doc_code_dn,
                "default_workflow_action": settings_obj.default_workflow_action,
                "auto_derive_tax_regime": settings_obj.auto_derive_tax_regime,
                "allow_mixed_taxability_in_one_invoice": settings_obj.allow_mixed_taxability_in_one_invoice,
                "enable_einvoice": settings_obj.enable_einvoice,
                "enable_eway": settings_obj.enable_eway,
                "einvoice_entity_applicable": settings_obj.einvoice_entity_applicable,
                "eway_value_threshold": settings_obj.eway_value_threshold,
                "compliance_applicability_mode": settings_obj.compliance_applicability_mode,
                "auto_generate_einvoice_on_confirm": settings_obj.auto_generate_einvoice_on_confirm,
                "auto_generate_einvoice_on_post": settings_obj.auto_generate_einvoice_on_post,
                "auto_generate_eway_on_confirm": settings_obj.auto_generate_eway_on_confirm,
                "auto_generate_eway_on_post": settings_obj.auto_generate_eway_on_post,
                "prefer_irp_generate_einvoice_and_eway_together": settings_obj.prefer_irp_generate_einvoice_and_eway_together,
                "enforce_statutory_cancel_before_business_cancel": settings_obj.enforce_statutory_cancel_before_business_cancel,
                "tcs_credit_note_policy": settings_obj.tcs_credit_note_policy,
                "enable_round_off": settings_obj.enable_round_off,
                "round_grand_total_to": settings_obj.round_grand_total_to,
                "invoice_printing": SalesSettingsService.effective_invoice_printing_config(settings_obj),
                "policy_controls": policy_controls,
            },
            "stock_policy": stock_policy,
            "schema": SALES_SETTINGS_SCHEMA,
            "sections": _sections(SALES_SETTINGS_SCHEMA),
            "current_doc_numbers": current_doc_numbers,
            "numbering_series": self._series_payload(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                settings_obj=settings_obj,
                current_doc_numbers=current_doc_numbers,
                doc_type_configs=doc_type_configs,
            ) if entityfinid_id else [],
            "numbering_series_schema": NUMBERING_SERIES_SCHEMA,
            "lock_periods": self._list_lock_periods(entity_id=entity_id, subentity_id=subentity_id),
            "lock_period_schema": LOCK_PERIOD_SCHEMA,
            "choice_overrides": self._list_choice_overrides(
                entity_id=entity_id,
                subentity_id=subentity_id,
                catalog=choice_catalog,
            ),
            "choice_override_catalog": choice_catalog,
            "capabilities": {
                "has_lock_periods": True,
                "has_choice_overrides": True,
                "has_policy_controls": True,
                "has_stock_policy": True,
                "has_doc_number_preview": bool(entityfinid_id),
                "has_numbering_management": bool(entityfinid_id),
            },
        }
        return payload

    def get(self, request):
        entity_id, subentity_id, entityfinid_id = self._scope(request, require_entityfinid=True)
        require_sales_scope_permission(
            user=request.user,
            entity_id=entity_id,
            permission_codes=("sales.settings.view", "sales.settings.update"),
            access_mode="setup",
            feature_code="feature_sales",
            message="Missing permission: sales.settings.view",
        )
        return Response(self._payload(entity_id=entity_id, subentity_id=subentity_id, entityfinid_id=entityfinid_id))

    @transaction.atomic
    def patch(self, request):
        entity_id, subentity_id, entityfinid_id = self._scope(request, require_entityfinid=False)
        require_sales_scope_permission(
            user=request.user,
            entity_id=entity_id,
            permission_codes=("sales.settings.update",),
            access_mode="setup",
            feature_code="feature_sales",
            message="Missing permission: sales.settings.update",
        )
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})

        nested_settings = request.data.get("settings") if isinstance(request.data.get("settings"), dict) else None
        settings_updates = nested_settings if nested_settings is not None else request.data

        settings_obj = SalesSettingsService.get_settings(entity_id, subentity_id, entityfinid_id=entityfinid_id)
        previous_doc_code_defaults = self._doc_code_defaults(settings_obj)
        previous_setting_values = self._setting_values(settings_obj)
        updated_setting_fields = {key for key in settings_updates if key in EDITABLE_FIELDS}
        try:
            for key, value in settings_updates.items():
                if key == "stock_policy":
                    continue
                if key in EDITABLE_FIELDS:
                    if key == "policy_controls":
                        value = SalesSettingsService.normalize_policy_controls(value)
                    if key == "invoice_printing":
                        value = SalesSettingsService.normalize_invoice_printing(value)
                    setattr(settings_obj, key, value)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})

        if "stock_policy" in request.data:
            SalesSettingsService.upsert_stock_policy(
                entity_id=entity_id,
                subentity_id=subentity_id,
                entityfinid_id=entityfinid_id,
                raw=request.data.get("stock_policy"),
            )

        if "numbering_series" in request.data:
            rows = request.data.get("numbering_series") or []
            if not entityfinid_id:
                raise ValidationError({"entityfinid": "entityfinid is required when updating numbering_series."})
            if not isinstance(rows, list):
                raise ValidationError({"numbering_series": "Provide a list of numbering series rows."})
            self._update_numbering_series(rows, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, settings_obj=settings_obj, user_id=getattr(request.user, "id", None))
        else:
            settings_obj.save()

        self._ensure_default_numbering_series(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            settings_obj=settings_obj,
            previous_defaults=previous_doc_code_defaults,
            user_id=getattr(request.user, "id", None),
        )
        self._propagate_entity_doc_code_defaults(
            entity_id=entity_id,
            subentity_id=subentity_id,
            settings_obj=settings_obj,
            previous_defaults=previous_doc_code_defaults,
        )
        self._propagate_entity_setting_defaults(
            entity_id=entity_id,
            subentity_id=subentity_id,
            settings_obj=settings_obj,
            previous_values=previous_setting_values,
            updated_fields=updated_setting_fields,
        )

        if "lock_periods" in request.data:
            rows = request.data.get("lock_periods") or []
            if not isinstance(rows, list):
                raise ValidationError({"lock_periods": "Provide a list of lock periods."})
            self._replace_lock_periods(
                rows,
                entity_id=entity_id,
                subentity_id=subentity_id,
                entityfinid_id=entityfinid_id,
            )

        if "choice_overrides" in request.data:
            rows = request.data.get("choice_overrides") or []
            if not isinstance(rows, list):
                raise ValidationError({"choice_overrides": "Provide a list of choice overrides."})
            self._replace_choice_overrides(rows, entity_id=entity_id, subentity_id=subentity_id)

        entityfinid_for_response = entityfinid_id or self._parse_int(request.query_params.get("entityfinid"), "entityfinid", required=False)
        transaction.on_commit(lambda: bump_meta_namespaces(SALES_META_NAMESPACES))
        return Response(self._payload(entity_id=entity_id, subentity_id=subentity_id, entityfinid_id=entityfinid_for_response), status=status.HTTP_200_OK)
