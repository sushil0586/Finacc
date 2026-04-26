from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import re
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

DEFAULT_INVOICE_PRINTING_CONFIG: Dict[str, Any] = {
    "default_profile": "gst_standard",
    "default_copies": ["original"],
    "profiles": [
        {
            "key": "gst_standard",
            "label": "GST Standard A4",
            "hint": "Rule-friendly layout with full statutory sections.",
            "options": {
                "show_bank_details": True,
                "show_terms": True,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": True,
                "show_compliance_qr": True,
                "show_gst_validation_panel": True,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "comfortable",
                "font_scale": 1.0,
                "template_key": "gst_a4",
                "page_size": "A4",
                "orientation": "portrait",
                "margin_mm": 10,
                "pdf_render_scale": 0.55,
                "pdf_image_quality": 0.62,
            },
        },
        {
            "key": "plain",
            "label": "Plain Paper",
            "hint": "Minimal visual layout while retaining invoice essentials.",
            "options": {
                "show_bank_details": False,
                "show_terms": False,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": True,
                "show_compliance_qr": True,
                "show_gst_validation_panel": True,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "comfortable",
                "font_scale": 1.0,
                "template_key": "plain_a4",
                "page_size": "A4",
                "orientation": "portrait",
                "margin_mm": 10,
                "pdf_render_scale": 0.5,
                "pdf_image_quality": 0.58,
            },
        },
        {
            "key": "large_invoice",
            "label": "Large Invoice (50+ Lines)",
            "hint": "Compact spacing optimized for long multi-page invoices.",
            "options": {
                "show_bank_details": True,
                "show_terms": False,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": True,
                "show_compliance_qr": True,
                "show_gst_validation_panel": True,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "compact",
                "font_scale": 0.92,
                "template_key": "gst_a4_compact",
                "page_size": "A4",
                "orientation": "portrait",
                "margin_mm": 8,
                "pdf_render_scale": 0.5,
                "pdf_image_quality": 0.58,
            },
        },
        {
            "key": "thermal_80mm",
            "label": "Thermal 80mm",
            "hint": "Narrow, fast print profile for grocery and POS printers.",
            "options": {
                "show_bank_details": False,
                "show_terms": False,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": False,
                "show_compliance_qr": False,
                "show_gst_validation_panel": False,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "compact",
                "font_scale": 0.84,
                "template_key": "thermal_80mm",
                "page_size": "80MM",
                "orientation": "portrait",
                "margin_mm": 2,
                "pdf_render_scale": 0.42,
                "pdf_image_quality": 0.5,
            },
        },
        {
            "key": "thermal_58mm",
            "label": "Thermal 58mm",
            "hint": "Ultra-compact receipt profile for narrow thermal printers.",
            "options": {
                "show_bank_details": False,
                "show_terms": False,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": False,
                "show_compliance_qr": False,
                "show_gst_validation_panel": False,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "compact",
                "font_scale": 0.8,
                "template_key": "thermal_58mm",
                "page_size": "58MM",
                "orientation": "portrait",
                "margin_mm": 1,
                "pdf_render_scale": 0.4,
                "pdf_image_quality": 0.48,
            },
        },
        {
            "key": "transport_copy",
            "label": "Transport Copy",
            "hint": "Highlights transport, E-Way and QR details for goods movement.",
            "options": {
                "show_bank_details": False,
                "show_terms": False,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": True,
                "show_compliance_qr": True,
                "show_gst_validation_panel": True,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "compact",
                "font_scale": 0.9,
                "template_key": "transport_copy",
                "page_size": "A4",
                "orientation": "portrait",
                "margin_mm": 8,
                "pdf_render_scale": 0.5,
                "pdf_image_quality": 0.56,
            },
        },
    ],
    "copy_labels": {
        "original": "ORIGINAL FOR RECIPIENT",
        "duplicate": "DUPLICATE FOR TRANSPORTER",
        "triplicate": "TRIPLICATE FOR SUPPLIER",
    },
    "texts": {
        "form_label": "Form GST INV-1",
        "receiver_title": "Details of Receiver (Billed to)",
        "consignee_title": "Details of Consignee (Shipped to)",
        "terms_title": "Terms & Conditions :",
        "terms_lines": [
            "Our responsibility ceases after the goods are removed from our premises",
            "Goods once sold are not returnable or exchangeable",
            "if the bill is not paid within a week interest @24% will be charged from date of bill",
        ],
        "terms_ack_lines": [
            "Received the above goods in good condition",
            "Rate & Weight of this bill found correct.",
        ],
        "signature_labels": ["", "Checked By", "Prepared By", "Customer's Sign"],
        "line_columns": [
            {"key": "line_no", "label": "Sr", "colspan": 2, "className": "ams-border-left", "format": "index"},
            {"key": "productname", "label": "Description of Goods", "colspan": 2, "className": "ams-border-left", "format": "text"},
            {"key": "hsn", "label": "HSN", "colspan": 2, "className": "ams-border-left", "format": "text"},
            {"key": "pieces", "label": "Pcs", "colspan": 1, "className": "ams-border-left text-end", "format": "integer"},
            {"key": "orderqty", "label": "Qty", "colspan": 1, "className": "ams-border-left text-end", "format": "integer"},
            {"key": "units", "label": "Unit", "colspan": 1, "className": "ams-border-left text-start", "format": "text"},
            {"key": "ratebefdiscount", "label": "Rate", "colspan": 1, "className": "ams-border-left text-end", "format": "number"},
            {"key": "orderDiscount", "label": "Discount %", "colspan": 1, "className": "ams-border-left text-end", "format": "text"},
            {"key": "rate", "label": "Actual Rate", "colspan": 2, "className": "ams-border-left text-end", "format": "number"},
            {"key": "amount", "label": "Amount", "colspan": 2, "className": "text-end ams-border-left ams-border-right", "format": "number"},
        ],
    },
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
    _TRAILING_NUMBER_PATTERN = re.compile(r"(\d+)\s*$")

    @staticmethod
    def _extract_sequence_no(doc_no: Any, invoice_number: Any) -> int:
        doc_number = int(doc_no or 0)
        if doc_number > 0:
            return doc_number
        invoice_text = str(invoice_number or "").strip()
        if not invoice_text:
            return 0
        match = SalesSettingsService._TRAILING_NUMBER_PATTERN.search(invoice_text)
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
    def normalize_invoice_printing(raw: Any) -> Dict[str, Any]:
        if raw in (None, ""):
            return deepcopy(DEFAULT_INVOICE_PRINTING_CONFIG)
        if not isinstance(raw, dict):
            raise ValueError("invoice_printing must be a JSON object.")

        defaults = DEFAULT_INVOICE_PRINTING_CONFIG
        gst_validation_scenario_codes = {
            "SCN_B2B",
            "SCN_B2C",
            "SCN_EXPORT",
            "SCN_RCM",
            "SCN_EINV",
            "SCN_EWAY",
            "SCN_TRANSPORT",
            "SCN_TAX_SPLIT",
        }
        normalized: Dict[str, Any] = {
            "default_profile": str(raw.get("default_profile") or defaults["default_profile"]),
            "default_copies": list(defaults.get("default_copies") or ["original"]),
            "profiles": [],
            "copy_labels": dict(defaults["copy_labels"]),
            "texts": deepcopy(defaults["texts"]),
        }

        raw_copy_labels = raw.get("copy_labels")
        if isinstance(raw_copy_labels, dict):
            for key in ("original", "duplicate", "triplicate"):
                value = raw_copy_labels.get(key)
                if value is not None:
                    normalized["copy_labels"][key] = str(value).strip() or defaults["copy_labels"][key]

        allowed_copy_keys = {"original", "duplicate", "triplicate"}
        raw_default_copies = raw.get("default_copies")
        if isinstance(raw_default_copies, list):
            normalized_copies = []
            for item in raw_default_copies:
                key = str(item or "").strip().lower()
                if key in allowed_copy_keys:
                    normalized_copies.append(key)
            if normalized_copies:
                normalized["default_copies"] = list(dict.fromkeys(normalized_copies))
            else:
                normalized["default_copies"] = list(defaults.get("default_copies") or ["original"])

        profiles = raw.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            profiles = defaults["profiles"]

        seen_keys = set()
        for item in profiles:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            options = item.get("options") if isinstance(item.get("options"), dict) else {}
            line_density = str(options.get("line_density", "comfortable")).strip().lower()
            if line_density not in {"comfortable", "compact"}:
                line_density = "comfortable"
            try:
                font_scale = float(options.get("font_scale", 1.0))
            except (TypeError, ValueError):
                font_scale = 1.0
            if font_scale < 0.80:
                font_scale = 0.80
            if font_scale > 1.20:
                font_scale = 1.20
            orientation = str(options.get("orientation", "portrait")).strip().lower()
            if orientation not in {"portrait", "landscape"}:
                orientation = "portrait"
            page_size = str(options.get("page_size", "A4")).strip().upper()
            if page_size not in {"A4", "A5", "LETTER", "80MM", "58MM"}:
                page_size = "A4"
            template_key = str(options.get("template_key", "")).strip().lower() or "gst_a4"
            try:
                margin_mm = float(options.get("margin_mm", 10))
            except (TypeError, ValueError):
                margin_mm = 10.0
            if margin_mm < 0:
                margin_mm = 0.0
            if margin_mm > 25:
                margin_mm = 25.0
            try:
                pdf_render_scale = float(options.get("pdf_render_scale", 0.55))
            except (TypeError, ValueError):
                pdf_render_scale = 0.55
            if pdf_render_scale < 0.4:
                pdf_render_scale = 0.4
            if pdf_render_scale > 2.5:
                pdf_render_scale = 2.5
            try:
                pdf_image_quality = float(options.get("pdf_image_quality", 0.62))
            except (TypeError, ValueError):
                pdf_image_quality = 0.62
            if pdf_image_quality < 0.4:
                pdf_image_quality = 0.4
            if pdf_image_quality > 0.95:
                pdf_image_quality = 0.95
            raw_validation_checks = options.get("gst_validation_checks")
            if isinstance(raw_validation_checks, list):
                normalized_validation_checks = []
                for check_item in raw_validation_checks:
                    code = str(check_item or "").strip().upper()
                    if code in gst_validation_scenario_codes:
                        normalized_validation_checks.append(code)
                if normalized_validation_checks:
                    gst_validation_checks = list(dict.fromkeys(normalized_validation_checks))
                else:
                    gst_validation_checks = list(DEFAULT_INVOICE_PRINTING_CONFIG["profiles"][0]["options"]["gst_validation_checks"])
            else:
                gst_validation_checks = list(DEFAULT_INVOICE_PRINTING_CONFIG["profiles"][0]["options"]["gst_validation_checks"])
            normalized["profiles"].append(
                {
                    "key": key,
                    "label": str(item.get("label") or key).strip(),
                    "hint": str(item.get("hint") or "").strip(),
                    "options": {
                        "show_bank_details": bool(options.get("show_bank_details", True)),
                        "show_terms": bool(options.get("show_terms", True)),
                        "show_einvoice_section": bool(options.get("show_einvoice_section", True)),
                        "show_eway_details": bool(options.get("show_eway_details", True)),
                        "show_transport_details": bool(options.get("show_transport_details", True)),
                        "show_compliance_qr": bool(options.get("show_compliance_qr", True)),
                        "show_gst_validation_panel": bool(options.get("show_gst_validation_panel", True)),
                        "gst_validation_checks": gst_validation_checks,
                        "line_density": line_density,
                        "font_scale": font_scale,
                        "template_key": template_key,
                        "page_size": page_size,
                        "orientation": orientation,
                        "margin_mm": margin_mm,
                        "pdf_render_scale": pdf_render_scale,
                        "pdf_image_quality": pdf_image_quality,
                    },
                }
            )

        if not normalized["profiles"]:
            normalized["profiles"] = list(defaults["profiles"])

        allowed_keys = {item["key"] for item in normalized["profiles"]}
        if normalized["default_profile"] not in allowed_keys:
            normalized["default_profile"] = normalized["profiles"][0]["key"]

        raw_texts = raw.get("texts")
        if isinstance(raw_texts, dict):
            for key in ("form_label", "receiver_title", "consignee_title", "terms_title"):
                value = raw_texts.get(key)
                if value is None:
                    continue
                normalized["texts"][key] = str(value).strip() or defaults["texts"][key]

            for key in ("terms_lines", "terms_ack_lines"):
                items = raw_texts.get(key)
                if isinstance(items, list):
                    cleaned = [str(item).strip() for item in items if str(item).strip()]
                    normalized["texts"][key] = cleaned or list(defaults["texts"][key])

            signature_labels = raw_texts.get("signature_labels")
            if isinstance(signature_labels, list):
                normalized_labels = [str(item).strip() for item in signature_labels[:4]]
                while len(normalized_labels) < 4:
                    normalized_labels.append(defaults["texts"]["signature_labels"][len(normalized_labels)])
                normalized["texts"]["signature_labels"] = normalized_labels

            line_columns = raw_texts.get("line_columns")
            if isinstance(line_columns, list):
                cleaned_columns = []
                total_colspan = 0
                for item in line_columns:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key") or "").strip()
                    label = str(item.get("label") or key).strip()
                    class_name = str(item.get("className") or "").strip()
                    if not key or not label or not class_name:
                        continue
                    try:
                        colspan = int(float(item.get("colspan", 1)))
                    except (TypeError, ValueError):
                        colspan = 1
                    if colspan < 1:
                        colspan = 1
                    if colspan > 15:
                        colspan = 15
                    fmt = str(item.get("format") or "text").strip().lower()
                    if fmt not in {"text", "number", "integer", "index"}:
                        fmt = "text"
                    cleaned_columns.append(
                        {
                            "key": key,
                            "label": label,
                            "colspan": colspan,
                            "className": class_name,
                            "format": fmt,
                        }
                    )
                    total_colspan += colspan
                if cleaned_columns and total_colspan == 15:
                    normalized["texts"]["line_columns"] = cleaned_columns

        return normalized

    @staticmethod
    def effective_invoice_printing_config(settings_obj: Any) -> Dict[str, Any]:
        raw = getattr(settings_obj, "invoice_printing", None) or {}
        try:
            return SalesSettingsService.normalize_invoice_printing(raw)
        except ValueError:
            return deepcopy(DEFAULT_INVOICE_PRINTING_CONFIG)

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
                int(SalesInvoiceHeader.Status.CONFIRMED),
                int(SalesInvoiceHeader.Status.POSTED),
                int(SalesInvoiceHeader.Status.CANCELLED),
            ],
        }
        if subentity_id is None:
            inv_filters["subentity_id__isnull"] = True
        else:
            inv_filters["subentity_id"] = subentity_id

        rows = list(
            SalesInvoiceHeader.objects.filter(**inv_filters)
            .only("id", "invoice_number", "doc_no", "doc_code", "status", "bill_date")
        )
        if not rows:
            return None

        threshold = int(current_number or 0)
        candidates = []
        for row in rows:
            seq_no = SalesSettingsService._extract_sequence_no(
                getattr(row, "doc_no", None),
                getattr(row, "invoice_number", None),
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
          with fallback to the latest saved doc_code in scope when configured code drifts.
        - previous_*: nearest previous numbered invoice in scope (status-filtered).
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

        # 3) Get SalesInvoiceHeader doc_type enum value from doc_key
        sales_doc_type = SalesSettingsService._sales_doc_type_from_doc_key(doc_key)

        configured_doc_code = str(doc_code or "").strip()
        current_no: Optional[int] = None
        preview_error: Optional[str] = None

        # 2) Peek using configured code first.
        try:
            res = DocumentNumberService.peek_preview(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type_row.id,
                doc_code=configured_doc_code,
            )
            current_no = int(res.doc_no)
        except Exception as e:
            preview_error = str(e)

        # 3) Get latest saved numbered row in scope (used for fallback + previous lookup).
        latest_doc = SalesSettingsService._last_saved_doc_in_scope(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type=sales_doc_type,
            current_number=None,
        )

        # If configured code preview is stale/low, try latest doc's code.
        latest_doc_code = str(getattr(latest_doc, "doc_code", "") or "").strip()
        if (current_no is None or current_no <= 1) and latest_doc_code and latest_doc_code != configured_doc_code:
            try:
                res = DocumentNumberService.peek_preview(
                    entity_id=entity_id,
                    entityfinid_id=entityfinid_id,
                    subentity_id=subentity_id,
                    doc_type_id=doc_type_row.id,
                    doc_code=latest_doc_code,
                )
                current_no = int(res.doc_no)
            except Exception:
                pass

        # Final fallback when preview cannot be resolved from numbering series:
        # keep navigation stable from latest numbered document.
        if (current_no is None or current_no <= 0) and latest_doc:
            latest_seq = SalesSettingsService._extract_sequence_no(
                getattr(latest_doc, "doc_no", None),
                getattr(latest_doc, "invoice_number", None),
            )
            if latest_seq > 0:
                current_no = latest_seq + 1

        if current_no is None or current_no <= 0:
            return {
                "enabled": False,
                "reason": preview_error or "Unable to resolve current document number.",
                "doc_type_id": doc_type_row.id,
                "current_number": None,
                "previous_number": None,
                "previous_invoice_id": None,
                "previous_invoice_number": None,
                "previous_status": None,
                "previous_bill_date": None,
            }

        # 4) Previous = nearest numbered row < current number in scope.
        prev_doc = SalesSettingsService._last_saved_doc_in_scope(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type=sales_doc_type,
            current_number=current_no,
        )
        previous_number = None
        if prev_doc:
            previous_number = SalesSettingsService._extract_sequence_no(
                getattr(prev_doc, "doc_no", None),
                getattr(prev_doc, "invoice_number", None),
            ) or None

        return {
            "enabled": True,
            "doc_type_id": doc_type_row.id,
            "current_number": current_no,

            # ✅ previous from nearest previous numbered record in scope
            "previous_number": previous_number,
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
