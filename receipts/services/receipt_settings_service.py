from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from receipts.models.receipt_config import ReceiptSettings, DEFAULT_RECEIPT_POLICY_CONTROLS
from receipts.models.receipt_core import ReceiptVoucherHeader
from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService

ENFORCEMENT_LEVELS = {"off", "warn", "hard"}
ON_OFF = {"on", "off"}
OVER_SETTLEMENT_RULES = {"block", "warn"}
ALLOCATION_POLICIES = {"manual", "fifo"}
UNPOST_TARGETS = {"confirmed", "draft"}


@dataclass(frozen=True)
class ReceiptPolicy:
    settings: ReceiptSettings

    @property
    def controls(self) -> Dict[str, Any]:
        raw = getattr(self.settings, "policy_controls", None) or {}
        if not isinstance(raw, dict):
            return dict(DEFAULT_RECEIPT_POLICY_CONTROLS)
        merged = dict(DEFAULT_RECEIPT_POLICY_CONTROLS)
        merged.update(raw)
        return merged

    @property
    def default_action(self) -> str:
        return self.settings.default_workflow_action

    def level(self, key: str, default: str = "hard") -> str:
        val = str(self.controls.get(key, default)).lower().strip()
        return val if val in ENFORCEMENT_LEVELS else default


class ReceiptSettingsService:
    @staticmethod
    def get_settings(entity_id: int, subentity_id: Optional[int]) -> ReceiptSettings:
        s = ReceiptSettings.objects.filter(entity_id=entity_id, subentity_id=subentity_id).first()
        if s:
            return s
        s = ReceiptSettings.objects.filter(entity_id=entity_id, subentity__isnull=True).first()
        if s:
            return s
        created, _ = ReceiptSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        return created

    @staticmethod
    def get_policy(entity_id: int, subentity_id: Optional[int]) -> ReceiptPolicy:
        return ReceiptPolicy(settings=ReceiptSettingsService.get_settings(entity_id, subentity_id))

    @staticmethod
    def normalize_policy_controls(raw: Any) -> Dict[str, Any]:
        if raw in (None, ""):
            return {}
        if not isinstance(raw, dict):
            raise ValueError("policy_controls must be a JSON object.")

        normalized: Dict[str, Any] = {}
        for key, value in raw.items():
            if key not in DEFAULT_RECEIPT_POLICY_CONTROLS:
                continue
            v = str(value).lower().strip()
            if key in {"require_allocation_on_post", "allocation_amount_match_rule", "receipt_maker_checker", "require_reference_number"}:
                if v not in ENFORCEMENT_LEVELS:
                    raise ValueError(f"policy_controls.{key} must be one of: off, warn, hard.")
                normalized[key] = v
                continue
            if key in {
                "allow_advance_without_allocation",
                "allow_on_account_without_allocation",
                "sync_ap_settlement_on_post",
                "sync_advance_balance_on_post",
                "residual_to_advance_balance",
                "require_confirm_before_post",
                "require_submit_before_approve",
                "allow_edit_after_submit",
                "same_user_submit_approve",
            }:
                if v not in ON_OFF:
                    raise ValueError(f"policy_controls.{key} must be one of: on, off.")
                normalized[key] = v
                continue
            if key == "over_settlement_rule":
                if v not in OVER_SETTLEMENT_RULES:
                    raise ValueError("policy_controls.over_settlement_rule must be one of: block, warn.")
                normalized[key] = v
                continue
            if key == "allocation_policy":
                if v not in ALLOCATION_POLICIES:
                    raise ValueError("policy_controls.allocation_policy must be one of: manual, fifo.")
                normalized[key] = v
                continue
            if key == "unpost_target_status":
                if v not in UNPOST_TARGETS:
                    raise ValueError("policy_controls.unpost_target_status must be one of: confirmed, draft.")
                normalized[key] = v
                continue
        return normalized

    @staticmethod
    def effective_policy_controls(settings_obj: Any) -> Dict[str, Any]:
        raw = getattr(settings_obj, "policy_controls", None) or {}
        merged = dict(DEFAULT_RECEIPT_POLICY_CONTROLS)
        if isinstance(raw, dict):
            merged.update(raw)
        return merged

    @staticmethod
    def upsert_settings(*, entity_id: int, subentity_id: Optional[int], updates: Dict[str, Any]) -> ReceiptSettings:
        settings, _ = ReceiptSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        editable_fields = {
            "default_doc_code_receipt",
            "default_workflow_action",
            "policy_controls",
        }
        for key, val in updates.items():
            if key not in editable_fields:
                continue
            if key == "policy_controls":
                val = ReceiptSettingsService.normalize_policy_controls(val)
            setattr(settings, key, val)
        settings.save()
        return settings

    @staticmethod
    def get_current_doc_no(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_key: str,
        doc_code: str,
    ) -> Dict[str, Any]:
        doc_type_row = (
            DocumentType.objects.filter(
                module="receipts",
                doc_key=doc_key,
                is_active=True,
            )
            .only("id")
            .first()
        )
        if not doc_type_row:
            return {
                "enabled": False,
                "reason": f"DocumentType not found: receipts/{doc_key}",
                "doc_type_id": None,
                "current_number": None,
                "previous_number": None,
                "previous_voucher_id": None,
                "previous_voucher_code": None,
                "previous_status": None,
                "previous_voucher_date": None,
            }

        try:
            res = DocumentNumberService.peek_preview(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type_row.id,
                doc_code=doc_code,
            )
            current_no = int(res.doc_no)
        except Exception as e:
            return {
                "enabled": False,
                "reason": str(e),
                "doc_type_id": doc_type_row.id,
                "current_number": None,
                "previous_number": None,
                "previous_voucher_id": None,
                "previous_voucher_code": None,
                "previous_status": None,
                "previous_voucher_date": None,
            }

        voucher_filters = dict(entity_id=entity_id, entityfinid_id=entityfinid_id)
        if subentity_id is None:
            voucher_filters["subentity__isnull"] = True
        else:
            voucher_filters["subentity_id"] = subentity_id

        prev_doc = (
            ReceiptVoucherHeader.objects
            .filter(**voucher_filters)
            .only("id", "voucher_code", "doc_no", "status", "voucher_date")
            .order_by("-id")
            .first()
        )

        return {
            "enabled": True,
            "doc_type_id": doc_type_row.id,
            "current_number": current_no,
            "previous_number": int(prev_doc.doc_no) if (prev_doc and prev_doc.doc_no is not None) else None,
            "previous_voucher_id": prev_doc.id if prev_doc else None,
            "previous_voucher_code": prev_doc.voucher_code if prev_doc else None,
            "previous_status": int(prev_doc.status) if prev_doc else None,
            "previous_voucher_date": prev_doc.voucher_date if prev_doc else None,
        }
