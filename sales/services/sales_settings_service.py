from __future__ import annotations

from dataclasses import dataclass
from entity.models import Entity, SubEntity  # adjust import paths

from datetime import date
from typing import Optional, Dict, Any, Tuple

from django.db.models import Q

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService  # adjust import

from sales.models.sales_core import SalesInvoiceHeader
from sales.models.sales_settings import (
    SalesSettings,
    SalesLockPeriod,
    SalesChoiceOverride,
    SalesStockPolicy,
)
from sales.services.sales_stock_policy_service import (
    DEFAULT_STOCK_POLICY,
    ResolvedSalesStockPolicy,
    SalesStockPolicyService,
)

ENFORCEMENT_LEVELS = {"off", "warn", "hard"}
DELETE_POLICIES = {"draft_only", "non_posted", "never"}
MATCH_MODES = {"off", "two_way", "three_way"}
SETTLEMENT_MODES = {"off", "basic"}
ALLOCATION_POLICIES = {"manual", "fifo"}
OVER_SETTLEMENT_RULES = {"block", "warn"}
ON_OFF = {"off", "on"}
STOCK_POLICY_MODES = {"RELAXED", "CONTROLLED", "STRICT"}

DEFAULT_POLICY_CONTROLS: Dict[str, Any] = {
    "delete_policy": "draft_only",
    "allow_edit_confirmed": "on",
    "allow_unpost_posted": "on",
    "confirm_lock_check": "hard",
    "require_lines_on_confirm": "hard",
    "line_amount_mismatch": "hard",
    "invoice_match_mode": "off",
    "invoice_match_enforcement": "off",
    "settlement_mode": "basic",
    "allocation_policy": "manual",
    "over_settlement_rule": "block",
    "auto_adjust_credit_notes": "off",
    "statutory_maker_checker": "off",
    "auto_compliance_failure_mode": "warn",
    "compliance_allow_generate_irn_on_confirmed": "on",
    "compliance_allow_generate_irn_on_posted": "on",
    "compliance_allow_regenerate_irn_after_cancel": "off",
    "compliance_allow_regenerate_eway_after_cancel": "on",
    "compliance_allow_cancel_irn_when_eway_active": "off",
}


@dataclass(frozen=True)
class SalesPolicy:
    settings: SalesSettings

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
        return bool(self.settings.allow_mixed_taxability_in_one_invoice)

    @property
    def auto_derive_tax_regime(self) -> bool:
        return bool(self.settings.auto_derive_tax_regime)

    # Compliance governance
    @property
    def enable_einvoice(self) -> bool:
        return bool(self.settings.enable_einvoice)

    @property
    def enable_eway(self) -> bool:
        return bool(self.settings.enable_eway)

    @property
    def auto_generate_einvoice_on_confirm(self) -> bool:
        return bool(self.settings.auto_generate_einvoice_on_confirm)

    @property
    def auto_generate_einvoice_on_post(self) -> bool:
        return bool(self.settings.auto_generate_einvoice_on_post)

    @property
    def auto_generate_eway_on_confirm(self) -> bool:
        return bool(self.settings.auto_generate_eway_on_confirm)

    @property
    def auto_generate_eway_on_post(self) -> bool:
        return bool(self.settings.auto_generate_eway_on_post)

    @property
    def prefer_irp_generate_einvoice_and_eway_together(self) -> bool:
        return bool(self.settings.prefer_irp_generate_einvoice_and_eway_together)

    @property
    def einvoice_entity_applicable(self) -> bool:
        return bool(self.settings.einvoice_entity_applicable)

    @property
    def eway_value_threshold(self):
        return self.settings.eway_value_threshold

    @property
    def compliance_applicability_mode(self) -> str:
        return self.settings.compliance_applicability_mode

    @property
    def tcs_credit_note_policy(self) -> str:
        return self.settings.tcs_credit_note_policy

    @property
    def enforce_statutory_cancel_before_business_cancel(self) -> bool:
        return bool(self.settings.enforce_statutory_cancel_before_business_cancel)

    def level(self, key: str, default: str = "hard") -> str:
        val = str(self.controls.get(key, default)).lower().strip()
        return val if val in ENFORCEMENT_LEVELS else default

    @property
    def delete_policy(self) -> str:
        val = str(self.controls.get("delete_policy", "draft_only")).lower().strip()
        return val if val in DELETE_POLICIES else "draft_only"


class SalesSettingsService:

    @staticmethod
    def normalize_policy_controls(raw: Any) -> Dict[str, Any]:
        if raw in (None, ""):
            return {}
        if not isinstance(raw, dict):
            raise ValueError("policy_controls must be a JSON object.")

        normalized: Dict[str, Any] = {}
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
            if key in {
                "allow_edit_confirmed",
                "allow_unpost_posted",
                "compliance_allow_generate_irn_on_confirmed",
                "compliance_allow_generate_irn_on_posted",
                "compliance_allow_regenerate_irn_after_cancel",
                "compliance_allow_regenerate_eway_after_cancel",
                "compliance_allow_cancel_irn_when_eway_active",
            }:
                v = str(value).lower().strip()
                if v not in ON_OFF:
                    raise ValueError(f"policy_controls.{key} must be one of: off, on.")
                normalized[key] = v
                continue

            v = str(value).lower().strip()
            if v not in ENFORCEMENT_LEVELS:
                raise ValueError(f"policy_controls.{key} must be one of: off, warn, hard.")
            normalized[key] = v
        return normalized

    @staticmethod
    def effective_policy_controls(settings_obj: Any) -> Dict[str, Any]:
        raw = getattr(settings_obj, "policy_controls", None) or {}
        merged = dict(DEFAULT_POLICY_CONTROLS)
        if isinstance(raw, dict):
            merged.update(raw)
        return merged

    @staticmethod
    def normalize_stock_policy(raw: Any) -> Dict[str, Any]:
        if raw in (None, ""):
            return {}
        if not isinstance(raw, dict):
            raise ValueError("stock_policy must be a JSON object.")

        normalized: Dict[str, Any] = {}
        for key, value in raw.items():
            if key == "mode":
                mode = str(value or "").upper().strip()
                if mode not in STOCK_POLICY_MODES:
                    raise ValueError("stock_policy.mode must be one of: RELAXED, CONTROLLED, STRICT.")
                normalized[key] = mode
                continue

            if key in DEFAULT_STOCK_POLICY:
                normalized[key] = bool(value)
        return normalized

    @staticmethod
    def build_stock_policy_scope_level(*, entityfinid_id: Optional[int], subentity_id: Optional[int]) -> str:
        if entityfinid_id and subentity_id:
            return SalesStockPolicy.ScopeLevel.ENTITY_SUBENTITY_FY
        if subentity_id:
            return SalesStockPolicy.ScopeLevel.ENTITY_SUBENTITY
        if entityfinid_id:
            return SalesStockPolicy.ScopeLevel.ENTITY_FY
        return SalesStockPolicy.ScopeLevel.ENTITY

    @staticmethod
    def get_stock_policy_payload(*, entity_id: int, subentity_id: Optional[int], entityfinid_id: Optional[int]) -> Dict[str, Any]:
        policy = SalesStockPolicyService.resolve(
            entity_id=entity_id,
            subentity_id=subentity_id,
            entityfinid_id=entityfinid_id,
        )
        return {
            "id": getattr(policy.policy, "id", None),
            "scope_level": policy.scope_level,
            "scope_key": policy.scope_key,
            "is_default": bool(policy.is_default),
            "mode": policy.mode,
            "allow_negative_stock": bool(policy.allow_negative_stock),
            "batch_required_for_sales": bool(policy.batch_required_for_sales),
            "expiry_validation_required": bool(policy.expiry_validation_required),
            "fefo_required": bool(policy.fefo_required),
            "allow_manual_batch_override": bool(policy.allow_manual_batch_override),
            "allow_oversell": bool(policy.allow_oversell),
        }

    @staticmethod
    def upsert_stock_policy(
        *,
        entity_id: int,
        subentity_id: Optional[int],
        entityfinid_id: Optional[int],
        raw: Any,
    ) -> Optional[SalesStockPolicy]:
        if raw in (None, ""):
            return None

        normalized = SalesSettingsService.normalize_stock_policy(raw)
        if not normalized:
            return None

        scope_level = SalesSettingsService.build_stock_policy_scope_level(
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
        )
        policy = SalesStockPolicy.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id if entityfinid_id else None,
            subentity_id=subentity_id if subentity_id else None,
            scope_level=scope_level,
        ).first()
        if not policy:
            policy = SalesStockPolicy(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id if entityfinid_id else None,
                subentity_id=subentity_id if subentity_id else None,
                scope_level=scope_level,
            )

        for key, value in normalized.items():
            setattr(policy, key, value)
        policy.save()
        return policy


    @staticmethod
    def get_seller_profile(*, entity_id: int, subentity_id: int | None) -> dict:
        entity = Entity.objects.get(id=entity_id)
        entity_addr = (
            entity.addresses.filter(isactive=True, is_primary=True)
            .select_related("state", "country", "district", "city")
            .first()
        )
        entity_contact = entity.contacts.filter(isactive=True, is_primary=True).first()
        entity_gst = entity.gst_registrations.filter(isactive=True, is_primary=True).first()

        se = None
        se_addr = None
        se_contact = None
        if subentity_id:
            se = SubEntity.objects.get(id=subentity_id, entity_id=entity_id)
            se_addr = (
                se.addresses.filter(isactive=True, is_primary=True)
                .select_related("state", "country", "district", "city")
                .first()
            )
            se_contact = se.contacts.filter(isactive=True, is_primary=True).first()

        # state preference: SubEntity primary state > Entity primary state
        seller_state = (se_addr.state if se_addr and se_addr.state else (entity_addr.state if entity_addr else None))
        seller_state_id = seller_state.id if seller_state else None
        seller_statecode = seller_state.statecode if seller_state else None

        return {
            "entity_id": entity.id,
            "subentity_id": se.id if se else None,

            # GST always from Entity
            "gstno": (entity_gst.gstin if entity_gst else None),

            "state_id": seller_state_id,
            "statecode": seller_statecode,  # ✅ ADDED

            # optional info for print/einvoice payloads
            "entityname": entity.entityname,
            "legalname": entity.legalname,
            "address": (se_addr.line1 if se_addr and se_addr.line1 else (entity_addr.line1 if entity_addr else None)),
            "address2": (se_addr.line2 if se_addr and se_addr.line2 else (entity_addr.line2 if entity_addr else None)),
            "pincode": (se_addr.pincode if se_addr and se_addr.pincode else (entity_addr.pincode if entity_addr else None)),

            "country_id": (se_addr.country_id if se_addr and se_addr.country_id else (entity_addr.country_id if entity_addr else None)),
            "district_id": (se_addr.district_id if se_addr and se_addr.district_id else (entity_addr.district_id if entity_addr else None)),
            "city_id": (se_addr.city_id if se_addr and se_addr.city_id else (entity_addr.city_id if entity_addr else None)),

            "phoneoffice": (se_contact.mobile if se_contact and se_contact.mobile else (entity_contact.mobile if entity_contact else None)),
            "email": (se_contact.email if se_contact and se_contact.email else (entity_contact.email if entity_contact else None)),
        }

    @staticmethod
    def _sales_doc_type_from_doc_key(doc_key: str) -> int:
        """
        Map DocumentType.doc_key to SalesInvoiceHeader.DocType
        Mirrors Purchase behavior.
        """
        k = (doc_key or "").upper()
        if "CREDIT" in k:
            return int(SalesInvoiceHeader.DocType.CREDIT_NOTE)
        if "DEBIT" in k:
            return int(SalesInvoiceHeader.DocType.DEBIT_NOTE)
        return int(SalesInvoiceHeader.DocType.TAX_INVOICE)

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
                module="sales",
                doc_key=doc_key,
                is_active=True,
            )
            .only("id")
            .first()
        )

        if not doc_type_row:
            return {
                "enabled": False,
                "reason": f"DocumentType not found: sales/{doc_key}",
                "doc_type_id": None,
                "current_number": None,
                "previous_number": None,
                "previous_invoice_id": None,
                "previous_invoice_number": None,
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
                "previous_invoice_number": None,
                "previous_status": None,
                "previous_bill_date": None,
            }

        # 3) Get SalesInvoiceHeader doc_type enum value from doc_key
        sales_doc_type = SalesSettingsService._sales_doc_type_from_doc_key(doc_key)

        # 4) Previous = last saved row by id (scope: entity, FY, subentity, doc_type ONLY)
        inv_filters = dict(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            doc_type=sales_doc_type,
        )
        if subentity_id is None:
            inv_filters["subentity__isnull"] = True
        else:
            inv_filters["subentity_id"] = subentity_id

        prev_doc = (
            SalesInvoiceHeader.objects.filter(**inv_filters)
            .only("id", "invoice_number", "doc_no", "status", "bill_date")
            .order_by("-id")
            .first()
        )

        return {
            "enabled": True,
            "doc_type_id": doc_type_row.id,
            "current_number": current_no,

            # ✅ previous from last saved record (any status)
            "previous_number": int(prev_doc.doc_no) if (prev_doc and prev_doc.doc_no is not None) else None,
            "previous_invoice_id": prev_doc.id if prev_doc else None,
            "previous_invoice_number": prev_doc.invoice_number if prev_doc else None,
            "previous_status": int(prev_doc.status) if prev_doc else None,
            "previous_bill_date": prev_doc.bill_date if prev_doc else None,
        }

    # ----------------------------
    # Settings / Policy
    # ----------------------------
    @staticmethod
    def get_settings(entity_id: int, subentity_id: Optional[int], entityfinid_id: Optional[int] = None) -> SalesSettings:
        """
        Prefer entity+subentity row. Fallback to entity-only row (subentity NULL).
        If no row exists yet, create it with the current financial-year scope.
        """
        s = SalesSettings.objects.filter(entity_id=entity_id, subentity_id=subentity_id).first()
        if s:
            return s

        s = SalesSettings.objects.filter(entity_id=entity_id, subentity__isnull=True).first()
        if s:
            return s

        if not entityfinid_id:
            raise ValueError("entityfinid_id is required to create sales settings.")

        return SalesSettings.objects.create(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)

    @staticmethod
    def get_policy(entity_id: int, subentity_id: Optional[int], entityfinid_id: Optional[int] = None) -> SalesPolicy:
        return SalesPolicy(settings=SalesSettingsService.get_settings(entity_id, subentity_id, entityfinid_id=entityfinid_id))

    @staticmethod
    def get_stock_policy(
        *,
        entity_id: int,
        subentity_id: Optional[int],
        entityfinid_id: Optional[int] = None,
    ) -> ResolvedSalesStockPolicy:
        return SalesStockPolicyService.resolve(
            entity_id=entity_id,
            subentity_id=subentity_id,
            entityfinid_id=entityfinid_id,
        )

    # ----------------------------
    # Lock period enforcement
    # ----------------------------
    @staticmethod
    def is_locked(entity_id: int, subentity_id: Optional[int], bill_date: date) -> Tuple[bool, Optional[str]]:
        """
        Locked if:
          - bill_date <= lock_date (implemented as lock_date__gte=bill_date)
        Prefer subentity-specific lock, else entity-level lock.
        """
        lock = (
            SalesLockPeriod.objects
            .filter(entity_id=entity_id, subentity_id=subentity_id, lock_date__gte=bill_date)
            .order_by("-lock_date")
            .first()
        )
        if lock:
            return True, (lock.reason or f"Locked up to {lock.lock_date}")

        lock = (
            SalesLockPeriod.objects
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
               "EXPORT_WITHOUT_IGST": {"is_enabled": false, "override_label": "Export w/o IGST (Disabled)"}
            }
          }
        """
        qs = SalesChoiceOverride.objects.filter(entity_id=entity_id).filter(
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
