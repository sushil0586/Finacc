from __future__ import annotations

from typing import Any

from assets.models import AssetSettings, default_asset_policy_controls

DEFAULT_POLICY_CONTROLS = {
    "capitalization_basis": {"manual_or_posting", "manual_only", "posting_only"},
    "capitalization_threshold_rule": {"off", "warn", "hard"},
    "depreciation_proration": {"none", "monthly", "daily"},
    "depreciation_posting_mode": {"manual_run", "auto_run"},
    "depreciation_lock_rule": {"off", "warn", "hard"},
    "backdated_capitalization_rule": {"off", "warn", "hard"},
    "backdated_disposal_rule": {"off", "warn", "hard"},
    "negative_nbv_rule": {"off", "warn", "block"},
    "component_accounting": {"off", "on"},
    "allow_manual_depreciation_override": {"off", "warn", "hard"},
    "allow_posting_without_tag": {"off", "on"},
    "multi_book_mode": {"single", "parallel"},
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
