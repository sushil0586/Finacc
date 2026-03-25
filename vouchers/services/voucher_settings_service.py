from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from vouchers.models.voucher_config import VoucherSettings, DEFAULT_VOUCHER_POLICY_CONTROLS
from vouchers.models.voucher_core import VoucherHeader

ENFORCEMENT_LEVELS = {"off", "warn", "hard"}
ON_OFF = {"on", "off"}
UNPOST_TARGETS = {"confirmed", "draft"}


@dataclass(frozen=True)
class VoucherPolicy:
    settings: VoucherSettings

    @property
    def controls(self) -> Dict[str, Any]:
        raw = getattr(self.settings, "policy_controls", None) or {}
        if not isinstance(raw, dict):
            return dict(DEFAULT_VOUCHER_POLICY_CONTROLS)
        merged = dict(DEFAULT_VOUCHER_POLICY_CONTROLS)
        merged.update(raw)
        return merged

    @property
    def default_action(self) -> str:
        return self.settings.default_workflow_action


class VoucherSettingsService:
    DOC_KEY_BY_TYPE = {
        VoucherHeader.VoucherType.CASH: "CASH_VOUCHER",
        VoucherHeader.VoucherType.BANK: "BANK_VOUCHER",
        VoucherHeader.VoucherType.JOURNAL: "JOURNAL_VOUCHER",
    }
    DOC_CODE_FIELD_BY_TYPE = {
        VoucherHeader.VoucherType.CASH: "default_doc_code_cash",
        VoucherHeader.VoucherType.BANK: "default_doc_code_bank",
        VoucherHeader.VoucherType.JOURNAL: "default_doc_code_journal",
    }

    @staticmethod
    def get_settings(entity_id: int, subentity_id: Optional[int]) -> VoucherSettings:
        s = VoucherSettings.objects.filter(entity_id=entity_id, subentity_id=subentity_id).first()
        if s:
            return s
        s = VoucherSettings.objects.filter(entity_id=entity_id, subentity__isnull=True).first()
        if s:
            return s
        created, _ = VoucherSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        return created

    @staticmethod
    def get_policy(entity_id: int, subentity_id: Optional[int]) -> VoucherPolicy:
        return VoucherPolicy(settings=VoucherSettingsService.get_settings(entity_id, subentity_id))

    @staticmethod
    def normalize_policy_controls(raw: Any) -> Dict[str, Any]:
        if raw in (None, ""):
            return {}
        if not isinstance(raw, dict):
            raise ValueError("policy_controls must be a JSON object.")
        normalized: Dict[str, Any] = {}
        for key, value in raw.items():
            if key not in DEFAULT_VOUCHER_POLICY_CONTROLS:
                continue
            v = str(value).lower().strip()
            if key in {"voucher_maker_checker", "require_reference_number", "cash_bank_mixed_entry_rule"}:
                valid = ENFORCEMENT_LEVELS if key != "cash_bank_mixed_entry_rule" else {"off", "hard"}
                if v not in valid:
                    raise ValueError(f"policy_controls.{key} has invalid value.")
            elif key in {"require_confirm_before_post", "require_submit_before_approve", "allow_edit_after_submit", "same_user_submit_approve", "allow_control_account_lines", "require_cash_bank_account_for_cash_bank"}:
                if v not in ON_OFF:
                    raise ValueError(f"policy_controls.{key} must be one of: on, off.")
            elif key == "unpost_target_status":
                if v not in UNPOST_TARGETS:
                    raise ValueError("policy_controls.unpost_target_status must be one of: confirmed, draft.")
            normalized[key] = v
        return normalized



    @staticmethod
    def normalize_workflow_action(raw: Any) -> Any:
        # Backward compatibility: older clients sent VoucherHeader status ids.
        legacy_map = {
            "1": VoucherSettings.DefaultWorkflowAction.DRAFT,
            "2": VoucherSettings.DefaultWorkflowAction.CONFIRM,
            "3": VoucherSettings.DefaultWorkflowAction.POST,
            1: VoucherSettings.DefaultWorkflowAction.DRAFT,
            2: VoucherSettings.DefaultWorkflowAction.CONFIRM,
            3: VoucherSettings.DefaultWorkflowAction.POST,
        }
        return legacy_map.get(raw, raw)

    @staticmethod
    def effective_policy_controls(settings_obj: VoucherSettings) -> Dict[str, Any]:
        raw = getattr(settings_obj, "policy_controls", None) or {}
        merged = dict(DEFAULT_VOUCHER_POLICY_CONTROLS)
        if isinstance(raw, dict):
            merged.update(raw)
        return merged

    @staticmethod
    def upsert_settings(*, entity_id: int, subentity_id: Optional[int], updates: Dict[str, Any]) -> VoucherSettings:
        settings, _ = VoucherSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        editable = {
            "default_doc_code_cash",
            "default_doc_code_bank",
            "default_doc_code_journal",
            "default_workflow_action",
            "policy_controls",
        }
        workflow_values = {v for v, _ in VoucherSettings.DefaultWorkflowAction.choices}
        for key, val in updates.items():
            if key not in editable:
                continue
            if key in {"default_doc_code_cash", "default_doc_code_bank", "default_doc_code_journal"} and val is not None:
                code = str(val).strip()
                if not code:
                    raise ValueError(f"{key} cannot be blank.")
                if len(code) > 10:
                    raise ValueError(f"{key} must be at most 10 characters.")
                val = code
            if key == "default_workflow_action":
                val = VoucherSettingsService.normalize_workflow_action(val)
                if val not in workflow_values:
                    raise ValueError(f"default_workflow_action must be one of: {', '.join(sorted(workflow_values))}.")
            if key == "policy_controls":
                val = VoucherSettingsService.normalize_policy_controls(val)
            setattr(settings, key, val)
        settings.save()
        return settings

    @classmethod
    def default_doc_code_for_type(cls, settings: VoucherSettings, voucher_type: str) -> str:
        return getattr(settings, cls.DOC_CODE_FIELD_BY_TYPE[voucher_type])

    @classmethod
    def current_doc_no_for_type(cls, *, entity_id: int, entityfinid_id: int, subentity_id: Optional[int], voucher_type: str) -> Dict[str, Any]:
        settings = cls.get_settings(entity_id, subentity_id)
        doc_code = cls.default_doc_code_for_type(settings, voucher_type)
        doc_key = cls.DOC_KEY_BY_TYPE[voucher_type]
        doc_type_row = DocumentType.objects.filter(module="vouchers", doc_key=doc_key, is_active=True).only("id").first()
        if not doc_type_row:
            return {"enabled": False, "reason": f"DocumentType not found: vouchers/{doc_key}", "doc_type_id": None, "current_number": None}
        try:
            res = DocumentNumberService.peek_preview(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type_row.id,
                doc_code=doc_code,
            )
            current_no = int(res.doc_no)
        except Exception as exc:
            return {"enabled": False, "reason": str(exc), "doc_type_id": doc_type_row.id, "current_number": None}
        filters = dict(entity_id=entity_id, entityfinid_id=entityfinid_id, voucher_type=voucher_type)
        if subentity_id is None:
            filters["subentity__isnull"] = True
        else:
            filters["subentity_id"] = subentity_id
        prev = VoucherHeader.objects.filter(**filters).only("id", "voucher_code", "doc_no", "status", "voucher_date").order_by("-id").first()
        return {
            "enabled": True,
            "doc_type_id": doc_type_row.id,
            "current_number": current_no,
            "previous_number": int(prev.doc_no) if (prev and prev.doc_no is not None) else None,
            "previous_voucher_id": prev.id if prev else None,
            "previous_voucher_code": prev.voucher_code if prev else None,
            "previous_status": int(prev.status) if prev else None,
            "previous_voucher_date": prev.voucher_date if prev else None,
        }
