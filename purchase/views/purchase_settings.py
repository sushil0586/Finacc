from __future__ import annotations

from typing import Any, Optional

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from numbering.models import DocumentNumberSeries
from numbering.services import ensure_document_type, ensure_series
from purchase.models.purchase_config import PurchaseChoiceOverride, PurchaseLockPeriod, PurchaseSettings
from purchase.services.purchase_choice_service import PurchaseChoiceService
from purchase.services.purchase_settings_service import PurchaseSettingsService
from helpers.utils.meta_cache import PURCHASE_META_NAMESPACES, bump_meta_namespaces


def _choice_payload(choices) -> list[dict]:
    return [{"value": value, "label": label} for value, label in choices]


def _sections(schema: list[dict]) -> list[dict]:
    ordered_groups = []
    for item in schema:
        group = item.get("group") or "general"
        if group not in ordered_groups:
            ordered_groups.append(group)
    sections = [{"key": group, "title": group.replace("_", " ").title(), "source": "settings"} for group in ordered_groups]
    sections.append({"key": "numbering_series", "title": "Numbering Series", "source": "numbering_series"})
    sections.append({"key": "lock_periods", "title": "Lock Periods", "source": "lock_periods"})
    sections.append({"key": "choice_overrides", "title": "Choice Overrides", "source": "choice_overrides"})
    return sections


PURCHASE_SETTINGS_SCHEMA = [
    {"name": "default_doc_code_invoice", "label": "Invoice Doc Code", "type": "string", "group": "numbering_defaults"},
    {"name": "default_doc_code_cn", "label": "Credit Note Doc Code", "type": "string", "group": "numbering_defaults"},
    {"name": "default_doc_code_dn", "label": "Debit Note Doc Code", "type": "string", "group": "numbering_defaults"},
    {"name": "default_workflow_action", "label": "Default Workflow", "type": "choice", "group": "workflow", "choices": _choice_payload(PurchaseSettings.DefaultWorkflowAction.choices)},
    {"name": "auto_derive_tax_regime", "label": "Auto Derive Tax Regime", "type": "boolean", "group": "tax"},
    {"name": "enforce_2b_before_itc_claim", "label": "Enforce 2B Before ITC Claim", "type": "boolean", "group": "tax"},
    {"name": "itc_claim_requires_2b", "label": "ITC Claim Requires 2B", "type": "choice", "group": "tax", "choices": [{"value": "off", "label": "Off"}, {"value": "warn", "label": "Warn"}, {"value": "hard", "label": "Hard Block"}]},
    {"name": "itc_claim_allowed_2b_statuses", "label": "ITC Claim Allowed 2B Statuses", "type": "multi_select", "group": "tax", "choices": [
        {"value": "matched", "label": "Matched"},
        {"value": "partial", "label": "Partial / Needs Review"},
        {"value": "not_checked", "label": "Not Checked"},
        {"value": "mismatched", "label": "Mismatched"},
        {"value": "not_in_2b", "label": "Not in 2B"},
        {"value": "na", "label": "Not Applicable"},
    ]},
    {"name": "it_tds_challan_due_day", "label": "IT-TDS Challan Due Day", "type": "integer", "group": "statutory_due_dates"},
    {"name": "gst_tds_challan_due_day", "label": "GST-TDS Challan Due Day", "type": "integer", "group": "statutory_due_dates"},
    {"name": "gst_tds_return_due_day", "label": "GST-TDS Return Due Day", "type": "integer", "group": "statutory_due_dates"},
    {"name": "it_tds_return_q1_due_month", "label": "IT-TDS Q1 Return Due Month", "type": "integer", "group": "statutory_due_dates"},
    {"name": "it_tds_return_q1_due_day", "label": "IT-TDS Q1 Return Due Day", "type": "integer", "group": "statutory_due_dates"},
    {"name": "it_tds_return_q2_due_month", "label": "IT-TDS Q2 Return Due Month", "type": "integer", "group": "statutory_due_dates"},
    {"name": "it_tds_return_q2_due_day", "label": "IT-TDS Q2 Return Due Day", "type": "integer", "group": "statutory_due_dates"},
    {"name": "it_tds_return_q3_due_month", "label": "IT-TDS Q3 Return Due Month", "type": "integer", "group": "statutory_due_dates"},
    {"name": "it_tds_return_q3_due_day", "label": "IT-TDS Q3 Return Due Day", "type": "integer", "group": "statutory_due_dates"},
    {"name": "it_tds_return_q4_due_month", "label": "IT-TDS Q4 Return Due Month", "type": "integer", "group": "statutory_due_dates"},
    {"name": "it_tds_return_q4_due_day", "label": "IT-TDS Q4 Return Due Day", "type": "integer", "group": "statutory_due_dates"},
    {"name": "vendor_gstin_format_rule", "label": "Vendor GSTIN Format Rule", "type": "choice", "group": "compliance_validation", "choices": [{"value": "off", "label": "Off"}, {"value": "warn", "label": "Warn"}, {"value": "hard", "label": "Hard Block"}]},
    {"name": "withholding_pan_required_rule", "label": "PAN Required for IT-TDS", "type": "choice", "group": "compliance_validation", "choices": [{"value": "off", "label": "Off"}, {"value": "warn", "label": "Warn"}, {"value": "hard", "label": "Hard Block"}]},
    {"name": "withholding_pan_format_rule", "label": "PAN Format Rule for IT-TDS", "type": "choice", "group": "compliance_validation", "choices": [{"value": "off", "label": "Off"}, {"value": "warn", "label": "Warn"}, {"value": "hard", "label": "Hard Block"}]},
    {"name": "allow_mixed_taxability_in_one_bill", "label": "Allow Mixed Taxability In One Bill", "type": "boolean", "group": "tax"},
    {"name": "post_gst_tds_on_invoice", "label": "Post GST/TDS On Invoice", "type": "boolean", "group": "tax"},
    {"name": "enable_round_off", "label": "Enable Round Off", "type": "boolean", "group": "rounding"},
    {"name": "round_grand_total_to", "label": "Round Grand Total To", "type": "integer", "group": "rounding"},
    {"name": "policy_controls", "label": "Policy Controls", "type": "json", "group": "policy"},
]

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
    "enforce_2b_before_itc_claim",
    "allow_mixed_taxability_in_one_bill",
    "round_grand_total_to",
    "enable_round_off",
    "post_gst_tds_on_invoice",
    "policy_controls",
}

PURCHASE_DOC_TYPES = {
    "invoice": {"doc_key": "PURCHASE_TAX_INVOICE", "name": "Purchase Invoice", "default_code_field": "default_doc_code_invoice", "fallback_code": "PINV"},
    "credit_note": {"doc_key": "PURCHASE_CREDIT_NOTE", "name": "Purchase Credit Note", "default_code_field": "default_doc_code_cn", "fallback_code": "PCN"},
    "debit_note": {"doc_key": "PURCHASE_DEBIT_NOTE", "name": "Purchase Debit Note", "default_code_field": "default_doc_code_dn", "fallback_code": "PDN"},
}


class PurchaseSettingsAPIView(APIView):
    permission_classes = [IsAuthenticated]

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

    def _qp(self, request, new_key: str, legacy_key: str):
        return request.query_params.get(new_key, request.query_params.get(legacy_key))

    def _scope(self, request, *, require_entityfinid: bool) -> tuple[int, Optional[int], Optional[int]]:
        entity_id = self._parse_int(self._qp(request, "entity_id", "entity"), "entity_id", required=True)
        subentity_id = self._parse_int(self._qp(request, "subentity_id", "subentity"), "subentity_id", required=False)
        entityfinid_id = self._parse_int(request.query_params.get("entityfinid"), "entityfinid", required=require_entityfinid)
        return entity_id, subentity_id, entityfinid_id

    @staticmethod
    def _get_doc_type(doc_key: str, name: str, default_code: str):
        return ensure_document_type(module="purchase", doc_key=doc_key, name=name, default_code=default_code)

    @staticmethod
    def _validate_settings_updates(settings_updates: dict) -> None:
        workflow_values = {v for v, _ in PurchaseSettings.DefaultWorkflowAction.choices}
        for k in ("default_doc_code_invoice", "default_doc_code_cn", "default_doc_code_dn"):
            if k in settings_updates and settings_updates[k] is not None:
                code = str(settings_updates[k]).strip()
                if not code:
                    raise ValidationError({k: "This field cannot be blank."})
                if len(code) > 10:
                    raise ValidationError({k: "Ensure this value has at most 10 characters."})
        if "default_workflow_action" in settings_updates:
            action = settings_updates["default_workflow_action"]
            if action not in workflow_values:
                raise ValidationError({"default_workflow_action": f"Invalid value. Allowed: {', '.join(sorted(workflow_values))}."})
        if "round_grand_total_to" in settings_updates and settings_updates["round_grand_total_to"] is not None:
            try:
                v = int(settings_updates["round_grand_total_to"])
            except (TypeError, ValueError):
                raise ValidationError({"round_grand_total_to": "Must be an integer."})
            if v < 0 or v > 6:
                raise ValidationError({"round_grand_total_to": "Must be between 0 and 6."})

    @staticmethod
    def _valid_override_keys(catalog: dict[str, list[dict]]) -> dict[str, set[str]]:
        return {group: {item.get("key") for item in items if item.get("key")} for group, items in catalog.items()}

    def _list_lock_periods(self, *, entity_id: int, subentity_id: Optional[int]) -> list[dict]:
        qs = PurchaseLockPeriod.objects.filter(entity_id=entity_id)
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        return list(qs.order_by("lock_date", "id").values("id", "lock_date", "reason"))

    def _replace_lock_periods(self, rows: list[dict], *, entity_id: int, subentity_id: Optional[int]) -> None:
        qs = PurchaseLockPeriod.objects.filter(entity_id=entity_id)
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        qs.delete()
        for row in rows:
            if not isinstance(row, dict) or not row.get("lock_date"):
                raise ValidationError({"lock_periods": "Each lock period must include lock_date."})
            PurchaseLockPeriod.objects.create(entity_id=entity_id, subentity_id=subentity_id, lock_date=row["lock_date"], reason=row.get("reason") or "")

    def _list_choice_overrides(self, *, entity_id: int, subentity_id: Optional[int]) -> list[dict]:
        catalog = PurchaseChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id)
        valid_keys = self._valid_override_keys(catalog)
        qs = PurchaseChoiceOverride.objects.filter(entity_id=entity_id)
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

    def _replace_choice_overrides(self, rows: list[dict], *, entity_id: int, subentity_id: Optional[int]) -> None:
        catalog = PurchaseChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id)
        valid_keys = self._valid_override_keys(catalog)
        qs = PurchaseChoiceOverride.objects.filter(entity_id=entity_id)
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
            PurchaseChoiceOverride.objects.create(
                entity_id=entity_id,
                subentity_id=subentity_id,
                choice_group=group,
                choice_key=key,
                is_enabled=bool(row.get("is_enabled", True)),
                override_label=row.get("override_label") or "",
            )

    def _series_payload(self, *, entity_id: int, entityfinid_id: int, subentity_id: Optional[int], settings_obj) -> list[dict]:
        rows = []
        for row_key, config in PURCHASE_DOC_TYPES.items():
            doc_code = getattr(settings_obj, config["default_code_field"]) or config["fallback_code"]
            doc_type = self._get_doc_type(config["doc_key"], config["name"], doc_code)
            series = DocumentNumberSeries.objects.filter(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type.id,
                doc_code=doc_code,
            ).first()
            rows.append(
                {
                    "series_key": row_key,
                    "label": config["name"],
                    "doc_key": config["doc_key"],
                    "doc_type_id": doc_type.id,
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
                    "preview": None,
                    "series_exists": bool(series),
                }
            )
        return rows

    def _update_numbering_series(self, rows: list[dict], *, entity_id: int, entityfinid_id: int, subentity_id: Optional[int], settings_obj, user_id: Optional[int]) -> None:
        row_map = {row["series_key"]: row for row in rows if isinstance(row, dict) and row.get("series_key") in PURCHASE_DOC_TYPES}
        for series_key, config in PURCHASE_DOC_TYPES.items():
            if series_key not in row_map:
                continue
            row = row_map[series_key]
            doc_code = (row.get("doc_code") or getattr(settings_obj, config["default_code_field"]) or config["fallback_code"]).strip()
            if not doc_code:
                raise ValidationError({"numbering_series": f"doc_code is required for {series_key}."})
            setattr(settings_obj, config["default_code_field"], doc_code)
            doc_type = self._get_doc_type(config["doc_key"], config["name"], doc_code)
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
            series.save()
        settings_obj.save()

    def _current_doc_numbers(self, *, entity_id: int, entityfinid_id: Optional[int], subentity_id: Optional[int], settings_obj) -> Optional[dict]:
        if not entityfinid_id:
            return None
        return {
            "invoice": PurchaseSettingsService.get_current_doc_no(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, doc_key="PURCHASE_TAX_INVOICE", doc_code=settings_obj.default_doc_code_invoice),
            "credit_note": PurchaseSettingsService.get_current_doc_no(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, doc_key="PURCHASE_CREDIT_NOTE", doc_code=settings_obj.default_doc_code_cn),
            "debit_note": PurchaseSettingsService.get_current_doc_no(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, doc_key="PURCHASE_DEBIT_NOTE", doc_code=settings_obj.default_doc_code_dn),
        }

    def _payload(self, *, entity_id: int, subentity_id: Optional[int], entityfinid_id: Optional[int]) -> dict:
        settings_obj = PurchaseSettingsService.get_settings(entity_id, subentity_id)
        policy = PurchaseSettingsService.get_policy(entity_id, subentity_id)
        choice_catalog = PurchaseChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id)
        return {
            "settings": {
                "entity": settings_obj.entity_id,
                "subentity": settings_obj.subentity_id,
                "default_doc_code_invoice": settings_obj.default_doc_code_invoice,
                "default_doc_code_cn": settings_obj.default_doc_code_cn,
                "default_doc_code_dn": settings_obj.default_doc_code_dn,
                "default_workflow_action": settings_obj.default_workflow_action,
                "auto_derive_tax_regime": settings_obj.auto_derive_tax_regime,
                "enforce_2b_before_itc_claim": settings_obj.enforce_2b_before_itc_claim,
                "itc_claim_requires_2b": policy.controls.get("itc_claim_requires_2b", "off"),
                "itc_claim_allowed_2b_statuses": policy.controls.get("itc_claim_allowed_2b_statuses", "matched,partial"),
                "itc_claim_allowed_2b_statuses_list": sorted(list(policy.itc_claim_allowed_2b_statuses)),
                "it_tds_challan_due_day": policy.controls.get("it_tds_challan_due_day", "7"),
                "gst_tds_challan_due_day": policy.controls.get("gst_tds_challan_due_day", "10"),
                "gst_tds_return_due_day": policy.controls.get("gst_tds_return_due_day", "10"),
                "it_tds_return_q1_due_month": policy.controls.get("it_tds_return_q1_due_month", "7"),
                "it_tds_return_q1_due_day": policy.controls.get("it_tds_return_q1_due_day", "31"),
                "it_tds_return_q2_due_month": policy.controls.get("it_tds_return_q2_due_month", "10"),
                "it_tds_return_q2_due_day": policy.controls.get("it_tds_return_q2_due_day", "31"),
                "it_tds_return_q3_due_month": policy.controls.get("it_tds_return_q3_due_month", "1"),
                "it_tds_return_q3_due_day": policy.controls.get("it_tds_return_q3_due_day", "31"),
                "it_tds_return_q4_due_month": policy.controls.get("it_tds_return_q4_due_month", "5"),
                "it_tds_return_q4_due_day": policy.controls.get("it_tds_return_q4_due_day", "31"),
                "vendor_gstin_format_rule": policy.controls.get("vendor_gstin_format_rule", "hard"),
                "withholding_pan_required_rule": policy.controls.get("withholding_pan_required_rule", "hard"),
                "withholding_pan_format_rule": policy.controls.get("withholding_pan_format_rule", "hard"),
                "allow_mixed_taxability_in_one_bill": settings_obj.allow_mixed_taxability_in_one_bill,
                "round_grand_total_to": settings_obj.round_grand_total_to,
                "enable_round_off": settings_obj.enable_round_off,
                "post_gst_tds_on_invoice": getattr(settings_obj, "post_gst_tds_on_invoice", False),
                "policy_controls": policy.controls,
            },
            "schema": PURCHASE_SETTINGS_SCHEMA,
            "sections": _sections(PURCHASE_SETTINGS_SCHEMA),
            "current_doc_numbers": self._current_doc_numbers(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, settings_obj=settings_obj),
            "numbering_series": self._series_payload(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, settings_obj=settings_obj) if entityfinid_id else [],
            "numbering_series_schema": NUMBERING_SERIES_SCHEMA,
            "lock_periods": self._list_lock_periods(entity_id=entity_id, subentity_id=subentity_id),
            "lock_period_schema": LOCK_PERIOD_SCHEMA,
            "choice_overrides": self._list_choice_overrides(entity_id=entity_id, subentity_id=subentity_id),
            "choice_override_catalog": choice_catalog,
            "capabilities": {
                "has_lock_periods": True,
                "has_choice_overrides": True,
                "has_policy_controls": True,
                "has_doc_number_preview": bool(entityfinid_id),
                "has_numbering_management": bool(entityfinid_id),
            },
        }

    def get(self, request):
        entity_id, subentity_id, entityfinid_id = self._scope(request, require_entityfinid=True)
        return Response(self._payload(entity_id=entity_id, subentity_id=subentity_id, entityfinid_id=entityfinid_id))

    @transaction.atomic
    def patch(self, request):
        entity_id, subentity_id, entityfinid_id = self._scope(request, require_entityfinid=False)
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})

        nested_settings = request.data.get("settings") if isinstance(request.data.get("settings"), dict) else None
        settings_updates = dict(nested_settings if nested_settings is not None else request.data)

        # UI-friendly ITC/2B controls are mapped into policy_controls for persistence.
        if (
            "itc_claim_requires_2b" in settings_updates
            or "itc_claim_allowed_2b_statuses" in settings_updates
            or "itc_claim_allowed_2b_statuses_list" in settings_updates
            or "it_tds_challan_due_day" in settings_updates
            or "gst_tds_challan_due_day" in settings_updates
            or "gst_tds_return_due_day" in settings_updates
            or "it_tds_return_q1_due_month" in settings_updates
            or "it_tds_return_q1_due_day" in settings_updates
            or "it_tds_return_q2_due_month" in settings_updates
            or "it_tds_return_q2_due_day" in settings_updates
            or "it_tds_return_q3_due_month" in settings_updates
            or "it_tds_return_q3_due_day" in settings_updates
            or "it_tds_return_q4_due_month" in settings_updates
            or "it_tds_return_q4_due_day" in settings_updates
            or "vendor_gstin_format_rule" in settings_updates
            or "withholding_pan_required_rule" in settings_updates
            or "withholding_pan_format_rule" in settings_updates
        ):
            policy_controls = dict(settings_updates.get("policy_controls") or {})
            if "itc_claim_requires_2b" in settings_updates:
                policy_controls["itc_claim_requires_2b"] = settings_updates.get("itc_claim_requires_2b")

            raw = settings_updates.get("itc_claim_allowed_2b_statuses_list", settings_updates.get("itc_claim_allowed_2b_statuses"))
            if raw is not None:
                if isinstance(raw, (list, tuple, set)):
                    tokens = [str(x).strip().lower() for x in raw if str(x).strip()]
                else:
                    tokens = [part.strip().lower() for part in str(raw or "").split(",") if part.strip()]
                policy_controls["itc_claim_allowed_2b_statuses"] = ",".join(tokens)

            for key in (
                "it_tds_challan_due_day",
                "gst_tds_challan_due_day",
                "gst_tds_return_due_day",
                "it_tds_return_q1_due_month",
                "it_tds_return_q1_due_day",
                "it_tds_return_q2_due_month",
                "it_tds_return_q2_due_day",
                "it_tds_return_q3_due_month",
                "it_tds_return_q3_due_day",
                "it_tds_return_q4_due_month",
                "it_tds_return_q4_due_day",
                "vendor_gstin_format_rule",
                "withholding_pan_required_rule",
                "withholding_pan_format_rule",
            ):
                if key in settings_updates:
                    policy_controls[key] = settings_updates.get(key)

            settings_updates["policy_controls"] = policy_controls

        # remove UI-only projection keys from direct settings save map
        settings_updates.pop("itc_claim_requires_2b", None)
        settings_updates.pop("itc_claim_allowed_2b_statuses", None)
        settings_updates.pop("itc_claim_allowed_2b_statuses_list", None)
        settings_updates.pop("it_tds_challan_due_day", None)
        settings_updates.pop("gst_tds_challan_due_day", None)
        settings_updates.pop("gst_tds_return_due_day", None)
        settings_updates.pop("it_tds_return_q1_due_month", None)
        settings_updates.pop("it_tds_return_q1_due_day", None)
        settings_updates.pop("it_tds_return_q2_due_month", None)
        settings_updates.pop("it_tds_return_q2_due_day", None)
        settings_updates.pop("it_tds_return_q3_due_month", None)
        settings_updates.pop("it_tds_return_q3_due_day", None)
        settings_updates.pop("it_tds_return_q4_due_month", None)
        settings_updates.pop("it_tds_return_q4_due_day", None)
        settings_updates.pop("vendor_gstin_format_rule", None)
        settings_updates.pop("withholding_pan_required_rule", None)
        settings_updates.pop("withholding_pan_format_rule", None)

        self._validate_settings_updates(settings_updates)

        try:
            updated = PurchaseSettingsService.upsert_settings(
                entity_id=entity_id,
                subentity_id=subentity_id,
                updates={k: v for k, v in settings_updates.items() if k in EDITABLE_FIELDS},
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})

        if "numbering_series" in request.data:
            rows = request.data.get("numbering_series") or []
            if not entityfinid_id:
                raise ValidationError({"entityfinid": "entityfinid is required when updating numbering_series."})
            if not isinstance(rows, list):
                raise ValidationError({"numbering_series": "Provide a list of numbering series rows."})
            self._update_numbering_series(rows, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, settings_obj=updated, user_id=getattr(request.user, "id", None))

        if "lock_periods" in request.data:
            rows = request.data.get("lock_periods") or []
            if not isinstance(rows, list):
                raise ValidationError({"lock_periods": "Provide a list of lock periods."})
            self._replace_lock_periods(rows, entity_id=entity_id, subentity_id=subentity_id)

        if "choice_overrides" in request.data:
            rows = request.data.get("choice_overrides") or []
            if not isinstance(rows, list):
                raise ValidationError({"choice_overrides": "Provide a list of choice overrides."})
            self._replace_choice_overrides(rows, entity_id=entity_id, subentity_id=subentity_id)

        entityfinid_for_response = entityfinid_id or self._parse_int(request.query_params.get("entityfinid"), "entityfinid", required=False)
        transaction.on_commit(lambda: bump_meta_namespaces(PURCHASE_META_NAMESPACES))
        return Response(self._payload(entity_id=entity_id, subentity_id=subentity_id, entityfinid_id=entityfinid_for_response), status=status.HTTP_200_OK)

    def put(self, request):
        return self.patch(request)
