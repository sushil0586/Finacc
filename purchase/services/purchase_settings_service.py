from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import re
from typing import Optional, Dict, Tuple, Any

from purchase.models.purchase_core import PurchaseInvoiceHeader, DocType, Status

from django.db.models import Q
from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService

from purchase.models.purchase_config import (
    PurchaseSettings,
    PurchaseLockPeriod,
    PurchaseChoiceOverride,
)

ENFORCEMENT_LEVELS = {"off", "warn", "hard"}
DELETE_POLICIES = {"draft_only", "non_posted", "never"}
MATCH_MODES = {"off", "two_way", "three_way"}
SETTLEMENT_MODES = {"off", "basic"}
ALLOCATION_POLICIES = {"manual", "fifo"}
CREDIT_NOTE_CONSUMPTION_MODES = {"off", "fifo", "reference_only", "reference_then_fifo"}
OVER_SETTLEMENT_RULES = {"block", "warn"}
ON_OFF = {"off", "on"}
TWO_B_STATUS_TOKENS = {"na", "not_checked", "matched", "mismatched", "not_in_2b", "partial"}

DEFAULT_POLICY_CONTROLS: Dict[str, Any] = {
    # Mutation safety
    "delete_policy": "draft_only",      # draft_only | non_posted | never
    "allow_edit_confirmed": "on",       # on | off
    "allow_unpost_posted": "on",        # on | off
    # Confirm rules
    "confirm_lock_check": "hard",       # off | warn | hard
    "require_lines_on_confirm": "hard", # off | warn | hard
    # Action gating
    "itc_action_status_gate": "hard",   # off | warn | hard
    "two_b_action_status_gate": "hard", # off | warn | hard
    "itc_claim_requires_2b": "off",  # off | warn | hard
    "itc_claim_allowed_2b_statuses": "matched,partial",  # csv tokens
    # Validation strictness
    "line_amount_mismatch": "hard",     # off | warn | hard
    # Match hooks
    "invoice_match_mode": "off",        # off | two_way | three_way
    "invoice_match_enforcement": "off", # off | warn | hard
    "settlement_mode": "off",           # off | basic
    "allocation_policy": "manual",      # manual | fifo
    "over_settlement_rule": "block",    # block | warn
    "auto_adjust_credit_notes": "off",  # off | on
    "vendor_tds_variance_rule": "warn",     # off | warn | hard
    "vendor_gst_tds_variance_rule": "warn", # off | warn | hard
    "statutory_maker_checker": "off",       # off | warn | hard
    "allow_revised_challan_remap": "off",   # off | on
    "statutory_auto_compute_interest_late_fee": "off",  # off | on
    "it_tds_interest_rate_monthly": "1.50",
    "it_tds_late_fee_per_day": "200.00",
    "it_tds_late_fee_cap_factor": "1.00",
    "gst_tds_interest_rate_monthly": "1.50",
    "gst_tds_late_fee_per_day": "100.00",
    "gst_tds_late_fee_cap_factor": "1.00",
    "it_tds_challan_due_day": "7",
    "gst_tds_challan_due_day": "10",
    "gst_tds_return_due_day": "10",
    "it_tds_return_q1_due_month": "7",
    "it_tds_return_q1_due_day": "31",
    "it_tds_return_q2_due_month": "10",
    "it_tds_return_q2_due_day": "31",
    "it_tds_return_q3_due_month": "1",
    "it_tds_return_q3_due_day": "31",
    "it_tds_return_q4_due_month": "5",
    "it_tds_return_q4_due_day": "31",
    "vendor_gstin_format_rule": "hard",
    "withholding_pan_required_rule": "hard",
    "withholding_pan_format_rule": "hard",
}


@dataclass(frozen=True)
class PurchasePolicy:
    settings: PurchaseSettings

    @property
    def controls(self) -> Dict[str, Any]:
        raw = getattr(self.settings, "policy_controls", None) or {}
        if not isinstance(raw, dict):
            return dict(DEFAULT_POLICY_CONTROLS)
        merged = dict(DEFAULT_POLICY_CONTROLS)
        merged.update(raw)
        return merged

    @property
    def default_action(self) -> str:
        return self.settings.default_workflow_action

    @property
    def round_decimals(self) -> int:
        return int(self.settings.round_grand_total_to or 2)

    @property
    def enable_round_off(self) -> bool:
        return bool(self.settings.enable_round_off)

    @property
    def allow_mixed_taxability(self) -> bool:
        return bool(self.settings.allow_mixed_taxability_in_one_bill)

    @property
    def enforce_2b_before_itc_claim(self) -> bool:
        return bool(self.settings.enforce_2b_before_itc_claim)

    @property
    def auto_derive_tax_regime(self) -> bool:
        return bool(self.settings.auto_derive_tax_regime)

    @property
    def post_gst_tds_on_invoice(self) -> bool:
        return bool(getattr(self.settings, "post_gst_tds_on_invoice", False))

    @property
    def itc_claim_2b_gate(self) -> str:
        raw = self.controls.get("itc_claim_requires_2b")
        if raw is None:
            return "hard" if self.enforce_2b_before_itc_claim else "off"
        val = str(raw).lower().strip()
        if val not in ENFORCEMENT_LEVELS:
            return "hard" if self.enforce_2b_before_itc_claim else "off"
        return val

    @property
    def itc_claim_allowed_2b_statuses(self) -> set[str]:
        raw = self.controls.get("itc_claim_allowed_2b_statuses", "matched,partial")
        if isinstance(raw, (list, tuple, set)):
            tokens = {str(x).strip().lower() for x in raw if str(x).strip()}
        else:
            tokens = {part.strip().lower() for part in str(raw).split(",") if part.strip()}
        clean = {token for token in tokens if token in TWO_B_STATUS_TOKENS}
        if not clean:
            return {"matched", "partial"}
        return clean

    def level(self, key: str, default: str = "hard") -> str:
        val = str(self.controls.get(key, default)).lower().strip()
        return val if val in ENFORCEMENT_LEVELS else default

    @property
    def delete_policy(self) -> str:
        val = str(self.controls.get("delete_policy", "draft_only")).lower().strip()
        return val if val in DELETE_POLICIES else "draft_only"


class PurchaseSettingsService:
    _TRAILING_NUMBER_PATTERN = re.compile(r"(\d+)\s*$")

    @staticmethod
    def _extract_sequence_no(doc_no: Any, purchase_number: Any) -> int:
        doc_number = int(doc_no or 0)
        if doc_number > 0:
            return doc_number
        purchase_text = str(purchase_number or "").strip()
        if not purchase_text:
            return 0
        match = PurchaseSettingsService._TRAILING_NUMBER_PATTERN.search(purchase_text)
        if not match:
            return 0
        return int(match.group(1) or 0)

    @staticmethod
    def normalize_policy_controls(raw: Any) -> Dict[str, Any]:
        if raw in (None, ""):
            return {}
        if not isinstance(raw, dict):
            raise ValueError("policy_controls must be a JSON object.")

        normalized: Dict[str, Any] = {}
        numeric_keys = {
            "it_tds_interest_rate_monthly",
            "it_tds_late_fee_per_day",
            "it_tds_late_fee_cap_factor",
            "gst_tds_interest_rate_monthly",
            "gst_tds_late_fee_per_day",
            "gst_tds_late_fee_cap_factor",
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
        }
        for key, value in raw.items():
            if key not in DEFAULT_POLICY_CONTROLS:
                continue
            if key == "delete_policy":
                v = str(value).lower().strip()
                if v not in DELETE_POLICIES:
                    raise ValueError("policy_controls.delete_policy must be one of: draft_only, non_posted, never.")
                normalized[key] = v
                continue
            if key == "invoice_match_mode":
                v = str(value).lower().strip()
                if v not in MATCH_MODES:
                    raise ValueError("policy_controls.invoice_match_mode must be one of: off, two_way, three_way.")
                normalized[key] = v
                continue
            if key == "settlement_mode":
                v = str(value).lower().strip()
                if v not in SETTLEMENT_MODES:
                    raise ValueError("policy_controls.settlement_mode must be one of: off, basic.")
                normalized[key] = v
                continue
            if key == "allocation_policy":
                v = str(value).lower().strip()
                if v not in ALLOCATION_POLICIES:
                    raise ValueError("policy_controls.allocation_policy must be one of: manual, fifo.")
                normalized[key] = v
                continue
            if key == "credit_note_consumption_mode":
                v = str(value).lower().strip()
                if v not in CREDIT_NOTE_CONSUMPTION_MODES:
                    raise ValueError("policy_controls.credit_note_consumption_mode must be one of: off, fifo, reference_only, reference_then_fifo.")
                normalized[key] = v
                continue
            if key == "over_settlement_rule":
                v = str(value).lower().strip()
                if v not in OVER_SETTLEMENT_RULES:
                    raise ValueError("policy_controls.over_settlement_rule must be one of: block, warn.")
                normalized[key] = v
                continue
            if key == "auto_adjust_credit_notes":
                v = str(value).lower().strip()
                if v not in ON_OFF:
                    raise ValueError("policy_controls.auto_adjust_credit_notes must be one of: off, on.")
                normalized[key] = v
                continue
            if key in {"allow_revised_challan_remap", "statutory_auto_compute_interest_late_fee", "allow_edit_confirmed", "allow_unpost_posted"}:
                v = str(value).lower().strip()
                if v not in ON_OFF:
                    raise ValueError(f"policy_controls.{key} must be one of: off, on.")
                normalized[key] = v
                continue
            if key == "itc_claim_allowed_2b_statuses":
                if isinstance(value, (list, tuple, set)):
                    tokens = [str(x).strip().lower() for x in value if str(x).strip()]
                else:
                    tokens = [part.strip().lower() for part in str(value).split(",") if part.strip()]
                bad = [token for token in tokens if token not in TWO_B_STATUS_TOKENS]
                if bad:
                    raise ValueError(
                        "policy_controls.itc_claim_allowed_2b_statuses has invalid value(s): "
                        + ", ".join(sorted(set(bad)))
                    )
                normalized[key] = ",".join(tokens)
                continue
            if key in numeric_keys:
                try:
                    n = float(value)
                except (TypeError, ValueError):
                    raise ValueError(f"policy_controls.{key} must be numeric.")
                if n < 0:
                    raise ValueError(f"policy_controls.{key} cannot be negative.")
                normalized[key] = str(value)
                continue

            v = str(value).lower().strip()
            if v not in ENFORCEMENT_LEVELS:
                raise ValueError(f"policy_controls.{key} must be one of: off, warn, hard.")
            normalized[key] = v

        return normalized

    @staticmethod
    def upsert_settings(
        *,
        entity_id: int,
        subentity_id: Optional[int],
        updates: Dict[str, Any],
    ) -> PurchaseSettings:
        settings, _ = PurchaseSettings.objects.get_or_create(
            entity_id=entity_id,
            subentity_id=subentity_id,
        )

        editable_fields = {
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

        for key, val in updates.items():
            if key not in editable_fields:
                continue
            if key == "policy_controls":
                val = PurchaseSettingsService.normalize_policy_controls(val)
            setattr(settings, key, val)

        settings.save()
        return settings

    @staticmethod
    def _purchase_doc_type_from_doc_key(doc_key: str) -> int:
        """
        Map DocumentType.doc_key to PurchaseInvoiceHeader.DocType
        """
        k = (doc_key or "").upper()
        if "CREDIT" in k:
            return int(DocType.CREDIT_NOTE)
        if "DEBIT" in k:
            return int(DocType.DEBIT_NOTE)
        return int(DocType.TAX_INVOICE)

    @staticmethod
    def _last_saved_doc_in_scope(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_type: int,
        current_number: Optional[int] = None,
    ):
        inv_filters = {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "doc_type": doc_type,
            "status__in": [
                int(Status.CONFIRMED),
                int(Status.POSTED),
                int(Status.CANCELLED),
            ],
        }
        if subentity_id is None:
            inv_filters["subentity_id__isnull"] = True
        else:
            inv_filters["subentity_id"] = subentity_id

        rows = list(
            PurchaseInvoiceHeader.objects.filter(**inv_filters)
            .only("id", "purchase_number", "doc_no", "status", "bill_date")
        )

        if not rows:
            return None

        threshold = int(current_number or 0)
        candidates = []
        for row in rows:
            seq_no = PurchaseSettingsService._extract_sequence_no(
                getattr(row, "doc_no", None),
                getattr(row, "purchase_number", None),
            )
            if seq_no <= 0:
                continue
            if threshold > 0 and seq_no >= threshold:
                continue
            candidates.append((seq_no, int(getattr(row, "id", 0) or 0), row))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][2]

    @staticmethod
    def get_current_doc_no(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_key: str,
        doc_code: str,
    ) -> Dict[str, Any]:
        """
        - current_number: preview (next-to-issue) from numbering series (uses doc_code)
        - previous_*: last saved invoice by ID for given entity + FY + subentity + doc_type
                     (ignores doc_code and status)
        """

        # 1) Find DocumentType row (for numbering preview)
        doc_type_row = (
            DocumentType.objects.filter(
                module="purchase",
                doc_key=doc_key,
                is_active=True,
            )
            .only("id")
            .first()
        )

        if not doc_type_row:
            return {
                "enabled": False,
                "reason": f"DocumentType not found: purchase/{doc_key}",
                "doc_type_id": None,
                "current_number": None,
                "previous_number": None,
                "previous_invoice_id": None,
                "previous_purchase_number": None,
                "previous_status": None,
                "previous_bill_date": None,
            }

        # 2) Peek current (next-to-issue) number (still uses doc_code)
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
                "previous_invoice_id": None,
                "previous_purchase_number": None,
                "previous_status": None,
                "previous_bill_date": None,
            }

        # 3) Get PurchaseInvoiceHeader doc_type enum value from doc_key
        purchase_doc_type = PurchaseSettingsService._purchase_doc_type_from_doc_key(doc_key)

        # 4) Previous = last saved row by id (scope: entity, FY, subentity, doc_type ONLY)
        prev_doc = PurchaseSettingsService._last_saved_doc_in_scope(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type=purchase_doc_type,
            current_number=current_no,
        )
        previous_number = None
        if prev_doc:
            previous_number = PurchaseSettingsService._extract_sequence_no(
                getattr(prev_doc, "doc_no", None),
                getattr(prev_doc, "purchase_number", None),
            ) or None

        return {
            "enabled": True,
            "doc_type_id": doc_type_row.id,
            "current_number": current_no,

            # ✅ previous from nearest previous numbered record in scope
            "previous_number": previous_number,
            "previous_invoice_id": prev_doc.id if prev_doc else None,
            "previous_purchase_number": prev_doc.purchase_number if prev_doc else None,
            "previous_status": int(prev_doc.status) if prev_doc else None,
            "previous_bill_date": prev_doc.bill_date if prev_doc else None,
        }
    @staticmethod
    def get_settings(entity_id: int, subentity_id: Optional[int]) -> PurchaseSettings:
        """
        Prefer entity+subentity row. Fallback to entity-only row (subentity NULL).
        If none exists, create settings for requested scope.
        """
        scoped = PurchaseSettings.objects.filter(entity_id=entity_id, subentity_id=subentity_id).first()
        if scoped:
            return scoped

        fallback = PurchaseSettings.objects.filter(entity_id=entity_id, subentity__isnull=True).first()
        if fallback:
            return fallback

        created, _ = PurchaseSettings.objects.get_or_create(entity_id=entity_id, subentity_id=subentity_id)
        return created

    @staticmethod
    def get_policy(entity_id: int, subentity_id: Optional[int]) -> PurchasePolicy:
        return PurchasePolicy(settings=PurchaseSettingsService.get_settings(entity_id, subentity_id))

    # ----------------------------
    # Lock period enforcement
    # ----------------------------
    @staticmethod
    def is_locked(entity_id: int, subentity_id: Optional[int], bill_date: date) -> Tuple[bool, Optional[str]]:
        """
        Locked if there is any lock_date >=? rule:
          - if bill_date <= lock_date => locked
        Prefer subentity-specific lock, else entity-level lock.
        """
        lock = (
            PurchaseLockPeriod.objects
            .filter(entity_id=entity_id, subentity_id=subentity_id, lock_date__gte=bill_date)
            .order_by("-lock_date")
            .first()
        )
        if lock:
            return True, (lock.reason or f"Locked up to {lock.lock_date}")

        lock = (
            PurchaseLockPeriod.objects
            .filter(entity_id=entity_id, subentity__isnull=True, lock_date__gte=bill_date)
            .order_by("-lock_date")
            .first()
        )
        if lock:
            return True, (lock.reason or f"Locked up to {lock.lock_date}")

        return False, None

    # ----------------------------
    # Choice override helpers
    # ----------------------------
    @staticmethod
    def get_choice_overrides(entity_id: int, subentity_id: Optional[int]) -> Dict[str, Dict[str, dict]]:
        """
        Return:
          {
            "SupplyCategory": {
               "SEZ": {"is_enabled": false, "override_label": "SEZ Purchase (Disabled)"}
            }
          }
        """
        qs = PurchaseChoiceOverride.objects.filter(
            entity_id=entity_id
        ).filter(
            Q(subentity_id=subentity_id) | Q(subentity__isnull=True)
        )

        out: Dict[str, Dict[str, dict]] = {}
        for r in qs:
            out.setdefault(r.choice_group, {})
            out[r.choice_group][r.choice_key] = {
                "is_enabled": bool(r.is_enabled),
                "override_label": r.override_label,
            }
        return out
