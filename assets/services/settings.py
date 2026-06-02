from __future__ import annotations

from typing import Any

from assets.models import (
    AssetCategory,
    AssetSettings,
    default_asset_category_accounting_controls,
    default_asset_category_traceability_controls,
    default_asset_policy_controls,
)

DEFAULT_POLICY_CONTROLS = {
    "capitalization_basis": {"manual_or_posting", "manual_only", "posting_only"},
    "capitalization_threshold_rule": {"off", "warn", "hard"},
    "purchase_review_completeness_rule": {"off", "warn", "hard"},
    "counter_ledger_match_rule": {"off", "warn", "hard"},
    "require_location_rule": {"off", "warn", "hard"},
    "require_department_rule": {"off", "warn", "hard"},
    "require_custodian_rule": {"off", "warn", "hard"},
    "require_serial_number_rule": {"off", "warn"},
    "require_manufacturer_rule": {"off", "warn"},
    "require_model_number_rule": {"off", "warn"},
    "require_vendor_account_rule": {"off", "warn"},
    "require_asset_ledger_rule": {"off", "warn", "hard"},
    "require_depreciation_ledgers_rule": {"off", "warn", "hard"},
    "require_impairment_ledgers_rule": {"off", "warn", "hard"},
    "require_disposal_ledgers_rule": {"off", "warn", "hard"},
    "require_cwip_ledger_rule": {"off", "warn", "hard"},
    "depreciation_proration": {"none", "monthly", "daily"},
    "depreciation_posting_mode": {"manual_run", "auto_run"},
    "depreciation_lock_rule": {"off", "warn", "hard"},
    "backdated_capitalization_rule": {"off", "warn", "hard"},
    "backdated_disposal_rule": {"off", "warn", "hard"},
    "negative_nbv_rule": {"off", "warn", "block"},
    "full_impairment_rule": {"off", "warn", "hard"},
    "component_accounting": {"off", "on"},
    "allow_manual_depreciation_override": {"off", "warn", "hard"},
    "allow_posting_without_tag": {"off", "on"},
    "multi_book_mode": {"single", "parallel"},
}

DEFAULT_CATEGORY_TRACEABILITY_CONTROLS = {
    "serial_number_rule": {"inherit", "off", "warn"},
    "manufacturer_rule": {"inherit", "off", "warn"},
    "model_number_rule": {"inherit", "off", "warn"},
    "vendor_account_rule": {"inherit", "off", "warn"},
}

DEFAULT_CATEGORY_ACCOUNTING_CONTROLS = {
    "asset_ledger_rule": {"inherit", "off", "warn", "hard"},
    "depreciation_ledgers_rule": {"inherit", "off", "warn", "hard"},
    "impairment_ledgers_rule": {"inherit", "off", "warn", "hard"},
    "disposal_ledgers_rule": {"inherit", "off", "warn", "hard"},
    "cwip_ledger_rule": {"inherit", "off", "warn", "hard"},
}


class AssetSettingsService:
    @staticmethod
    def get_settings(entity_id: int, subentity_id: int | None = None) -> AssetSettings:
        settings, _ = AssetSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        return settings

    @staticmethod
    def normalize_policy_controls(raw: Any) -> dict:
        if raw in (None, ""):
            return {}
        if not isinstance(raw, dict):
            raise ValueError("policy_controls must be a JSON object.")
        normalized: dict = {}
        for key, value in raw.items():
            if key not in DEFAULT_POLICY_CONTROLS:
                continue
            val = str(value).lower().strip()
            if val not in DEFAULT_POLICY_CONTROLS[key]:
                allowed = ", ".join(sorted(DEFAULT_POLICY_CONTROLS[key]))
                raise ValueError(f"policy_controls.{key} must be one of: {allowed}.")
            normalized[key] = val
        return normalized

    @staticmethod
    def resolve_policy_controls(settings_obj: AssetSettings | None) -> dict:
        controls = default_asset_policy_controls()
        if settings_obj and settings_obj.policy_controls:
            controls.update(settings_obj.policy_controls)
        return controls

    @staticmethod
    def normalize_category_traceability_controls(raw: Any) -> dict:
        if raw in (None, ""):
            return {}
        if not isinstance(raw, dict):
            raise ValueError("traceability_controls must be a JSON object.")
        normalized: dict = {}
        for key, value in raw.items():
            if key not in DEFAULT_CATEGORY_TRACEABILITY_CONTROLS:
                continue
            val = str(value).lower().strip()
            if val not in DEFAULT_CATEGORY_TRACEABILITY_CONTROLS[key]:
                allowed = ", ".join(sorted(DEFAULT_CATEGORY_TRACEABILITY_CONTROLS[key]))
                raise ValueError(f"traceability_controls.{key} must be one of: {allowed}.")
            normalized[key] = val
        return normalized

    @staticmethod
    def resolve_category_traceability_controls(category_obj: AssetCategory | None, settings_obj: AssetSettings | None) -> dict:
        controls = default_asset_category_traceability_controls()
        if category_obj and category_obj.traceability_controls:
            controls.update(category_obj.traceability_controls)
        policy_controls = AssetSettingsService.resolve_policy_controls(settings_obj)
        inherited_map = {
            "serial_number_rule": policy_controls.get("require_serial_number_rule", "off"),
            "manufacturer_rule": policy_controls.get("require_manufacturer_rule", "off"),
            "model_number_rule": policy_controls.get("require_model_number_rule", "off"),
            "vendor_account_rule": policy_controls.get("require_vendor_account_rule", "off"),
        }
        resolved = {}
        for key, value in controls.items():
            resolved[key] = inherited_map[key] if value == "inherit" else value
        return resolved

    @staticmethod
    def normalize_category_accounting_controls(raw: Any) -> dict:
        if raw in (None, ""):
            return {}
        if not isinstance(raw, dict):
            raise ValueError("accounting_controls must be a JSON object.")
        normalized: dict = {}
        for key, value in raw.items():
            if key not in DEFAULT_CATEGORY_ACCOUNTING_CONTROLS:
                continue
            val = str(value).lower().strip()
            if val not in DEFAULT_CATEGORY_ACCOUNTING_CONTROLS[key]:
                allowed = ", ".join(sorted(DEFAULT_CATEGORY_ACCOUNTING_CONTROLS[key]))
                raise ValueError(f"accounting_controls.{key} must be one of: {allowed}.")
            normalized[key] = val
        return normalized

    @staticmethod
    def resolve_category_accounting_controls(category_obj: AssetCategory | None, settings_obj: AssetSettings | None) -> dict:
        controls = default_asset_category_accounting_controls()
        if category_obj and category_obj.accounting_controls:
            controls.update(category_obj.accounting_controls)
        policy_controls = AssetSettingsService.resolve_policy_controls(settings_obj)
        inherited_map = {
            "asset_ledger_rule": policy_controls.get("require_asset_ledger_rule", "off"),
            "depreciation_ledgers_rule": policy_controls.get("require_depreciation_ledgers_rule", "off"),
            "impairment_ledgers_rule": policy_controls.get("require_impairment_ledgers_rule", "off"),
            "disposal_ledgers_rule": policy_controls.get("require_disposal_ledgers_rule", "off"),
            "cwip_ledger_rule": policy_controls.get("require_cwip_ledger_rule", "off"),
        }
        resolved = {}
        for key, value in controls.items():
            resolved[key] = inherited_map[key] if value == "inherit" else value
        return resolved

    @staticmethod
    def upsert_settings(*, entity_id: int, subentity_id: int | None, updates: dict, user_id: int | None = None) -> AssetSettings:
        settings = AssetSettingsService.get_settings(entity_id, subentity_id)
        editable_fields = {
            "default_doc_code_asset",
            "default_doc_code_disposal",
            "default_workflow_action",
            "default_depreciation_method",
            "default_useful_life_months",
            "default_residual_value_percent",
            "depreciation_posting_day",
            "allow_multiple_asset_books",
            "auto_post_depreciation",
            "auto_number_assets",
            "require_asset_tag",
            "enable_component_accounting",
            "enable_impairment_tracking",
            "capitalization_threshold",
            "policy_controls",
        }
        for key, val in updates.items():
            if key not in editable_fields:
                continue
            if key == "policy_controls":
                val = AssetSettingsService.normalize_policy_controls(val)
            setattr(settings, key, val)
        settings.updated_by_id = user_id
        if not settings.created_by_id:
            settings.created_by_id = user_id
        settings.save()
        return settings
