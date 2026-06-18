from __future__ import annotations

import json
from typing import Any, Dict, Optional
from sales.services.providers.registry import ProviderRegistry
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from sales.models.sales_core import SalesInvoiceHeader
from sales.models.sales_compliance import (
    SalesEInvoice,
    SalesEInvoiceCancel,
    SalesEWayBill,
    SalesEWayBillCancel,
    SalesEInvoiceStatus,
    SalesEWayStatus,
    SalesEWaySource,
)
from sales.models.mastergst_models import SalesMasterGSTCredential, MasterGSTEnvironment, MasterGSTServiceScope
from sales.services.providers.mastergst_client import MasterGSTClient
from sales.services.providers.config import active_einvoice_provider, active_eway_provider
from sales.services.providers.credential_resolver import CredentialResolver

from sales.services.irp_payload_builder import IRPPayloadBuilder
from sales.services.party_resolvers import seller_from_entity, buyer_from_account
from financial.models import account as AccountModel
from sales.services.compliance_audit_service import ComplianceAuditService
from sales.services.compliance_error_catalog_service import ComplianceErrorCatalogService

from sales.services.eway_payload_builder import (
    EWayInput,
    build_generate_eway_payload,
    build_disp_dtls,
    build_exp_ship_dtls,
)

from sales.services.eway.payload_b2c import build_b2c_direct_payload
from sales.services.profile_resolvers import entity_primary_address, entity_primary_bank_account, entity_primary_contact, entity_primary_gstin
from sales.services.sales_settings_service import SalesSettingsService


MAX_EWAY_ATTEMPTS = 10
ON_OFF = {"on", "off"}
DEFAULT_COMPLIANCE_POLICY_CONTROLS = {
    "compliance_allow_generate_irn_on_confirmed": "on",
    "compliance_allow_generate_irn_on_posted": "on",
    "compliance_allow_regenerate_irn_after_cancel": "off",
    "compliance_allow_regenerate_eway_after_cancel": "on",
    "compliance_allow_cancel_irn_when_eway_active": "off",
}


class SalesComplianceService:
    """
    Single compliance service:
      - IRN generation (E-Invoice)
      - E-Way B2B (IRN-based)
      - E-Way B2C (direct, no IRN)

    Assumption (per your latest statement):
      ✅ E-Way credentials = E-Invoice credentials
      => ONE SalesMasterGSTCredential per (entity, environment) is enough.
    """

    def __init__(self, *, invoice: SalesInvoiceHeader, user=None):
        self.invoice = invoice
        self.user = user

    # -------------------------
    # Common helpers
    # -------------------------

    @staticmethod
    def _einvoice_provider_name() -> str:
        return active_einvoice_provider()

    @staticmethod
    def _eway_provider_name() -> str:
        return active_eway_provider()

    @staticmethod
    def _ensure_invoice_eligible_for_eway(inv: SalesInvoiceHeader) -> None:
        if inv.status not in (inv.Status.CONFIRMED, inv.Status.POSTED):
            raise ValidationError("E-Way allowed only after CONFIRMED/POSTED invoices.")

    @staticmethod
    def _controls(inv: SalesInvoiceHeader) -> Dict[str, Any]:
        policy = SalesSettingsService.get_policy(
            entity_id=inv.entity_id,
            subentity_id=getattr(inv, "subentity_id", None),
            entityfinid_id=getattr(inv, "entityfinid_id", None),
        )
        controls = dict(DEFAULT_COMPLIANCE_POLICY_CONTROLS)
        controls.update(policy.controls or {})
        return controls

    @staticmethod
    def _flag_on(controls: Dict[str, Any], key: str, default: str = "on") -> bool:
        val = str(controls.get(key, default)).strip().lower()
        if val not in ON_OFF:
            val = default
        return val == "on"

    @staticmethod
    def _einvoice_min_hsn_digits(inv: SalesInvoiceHeader) -> int:
        controls = SalesComplianceService._controls(inv)
        raw = controls.get("einvoice_min_hsn_digits", 4)
        try:
            digits = int(raw)
        except (TypeError, ValueError):
            digits = 4
        return min(8, max(4, digits))

    @staticmethod
    def _money_text(value: Any) -> str:
        try:
            amount = Decimal(str(value or 0))
        except (InvalidOperation, TypeError, ValueError):
            amount = Decimal("0")
        return f"{amount.quantize(Decimal('0.01'))}"

    @staticmethod
    def _default_exp_ship_dtls(inv: SalesInvoiceHeader) -> Dict[str, Any]:
        ship = getattr(inv, "shipto_snapshot", None)
        return build_exp_ship_dtls(
            addr1=getattr(ship, "address1", None) if ship else getattr(inv, "bill_to_address1", None),
            addr2=getattr(ship, "address2", None) if ship else getattr(inv, "bill_to_address2", None),
            loc=getattr(ship, "city", None) if ship else getattr(inv, "bill_to_city", None),
            pin=getattr(ship, "pincode", None) if ship else getattr(inv, "bill_to_pincode", None),
            stcd=(getattr(ship, "state_code", None) or getattr(inv, "bill_to_state_code", None)) if ship else getattr(inv, "bill_to_state_code", None),
            gstin=(getattr(ship, "gstin", None) or getattr(inv, "customer_gstin", None)) if ship else getattr(inv, "customer_gstin", None),
        )

    @staticmethod
    def _normalize_exp_ship_dtls(inv: SalesInvoiceHeader, ship_in: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        fallback = SalesComplianceService._default_exp_ship_dtls(inv)
        current = dict(ship_in or {})
        buyer_gstin = str(getattr(inv, "customer_gstin", "") or "").strip().upper()
        current_gstin = str(current.get("Gstin") or "").strip().upper()
        current_state = str(current.get("Stcd") or "").strip()
        if current_gstin and current_state and current_state != "00":
            return None if buyer_gstin and current_gstin == buyer_gstin else current
        merged = {**fallback, **current}
        merged_gstin = str(merged.get("Gstin") or "").strip().upper()
        if not current_gstin and fallback.get("Gstin"):
            merged_gstin = str(fallback["Gstin"]).strip().upper()
            merged["Gstin"] = merged_gstin
        if not current_state or current_state == "00":
            merged["Stcd"] = fallback.get("Stcd") or current.get("Stcd")
        if buyer_gstin and merged_gstin == buyer_gstin:
            return None
        return {k: v for k, v in merged.items() if v is not None}

    @staticmethod
    def compliance_action_flags(inv: SalesInvoiceHeader) -> Dict[str, Any]:
        controls = SalesComplianceService._controls(inv)

        status = int(getattr(inv, "status", 0) or 0)
        is_confirmed = status == int(SalesInvoiceHeader.Status.CONFIRMED)
        is_posted = status == int(SalesInvoiceHeader.Status.POSTED)
        can_open = is_confirmed or is_posted

        is_b2c = int(getattr(inv, "supply_category", 0) or 0) == int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C)
        einvoice_applicable_raw = bool(getattr(inv, "is_einvoice_applicable", False))
        seller_gstin = str(getattr(inv, "seller_gstin", "") or "").strip()
        customer_gstin = str(getattr(inv, "customer_gstin", "") or "").strip()
        # Practical fallback: for non-B2C invoice with GSTINs present, keep IRN flow available
        # even if stored flag was not derived correctly on that draft/confirm cycle.
        einvoice_applicable = bool(
            einvoice_applicable_raw
            or ((not is_b2c) and len(seller_gstin) == 15 and len(customer_gstin) == 15)
        )
        eway_applicable = bool(getattr(inv, "is_eway_applicable", False))

        einv = getattr(inv, "einvoice_artifact", None)
        ewb = getattr(inv, "eway_artifact", None)
        irn_generated = bool(
            einv
            and int(getattr(einv, "status", 0) or 0) == int(SalesEInvoiceStatus.GENERATED)
            and getattr(einv, "irn", None)
        )
        irn_cancelled = bool(
            einv and int(getattr(einv, "status", 0) or 0) == int(SalesEInvoiceStatus.CANCELLED)
        )
        eway_generated = bool(
            ewb
            and int(getattr(ewb, "status", 0) or 0) == int(SalesEWayStatus.GENERATED)
            and getattr(ewb, "ewb_no", None)
        )
        eway_cancelled = bool(
            ewb and int(getattr(ewb, "status", 0) or 0) == int(SalesEWayStatus.CANCELLED)
        )

        allow_irn_confirmed = SalesComplianceService._flag_on(controls, "compliance_allow_generate_irn_on_confirmed", "on")
        allow_irn_posted = SalesComplianceService._flag_on(controls, "compliance_allow_generate_irn_on_posted", "on")
        allow_regen_irn = SalesComplianceService._flag_on(controls, "compliance_allow_regenerate_irn_after_cancel", "off")
        allow_regen_eway = SalesComplianceService._flag_on(controls, "compliance_allow_regenerate_eway_after_cancel", "on")
        irn_generation_status_ok = (is_confirmed and allow_irn_confirmed) or (is_posted and allow_irn_posted)
        irn_generation_not_already_done = (not irn_generated) and (allow_regen_irn or not irn_cancelled)
        eway_generation_not_already_done = (not eway_generated) and (allow_regen_eway or not eway_cancelled)

        can_generate_irn = can_open and einvoice_applicable and (not is_b2c) and irn_generation_status_ok and irn_generation_not_already_done
        # Keep flow practical: once IRN exists, allow E-Way actions even if applicability flag later toggles.
        eway_flow_eligible = eway_applicable or irn_generated or eway_generated or eway_cancelled
        can_generate_eway = can_open and eway_flow_eligible and eway_generation_not_already_done and (is_b2c or irn_generated)

        can_cancel_irn = can_open and irn_generated and not eway_generated
        can_cancel_eway = can_open and eway_generated

        return {
            "can_open_console": can_open,
            "can_ensure": can_open,
            "can_generate_irn": can_generate_irn,
            # Combined flow should be available when IRN can be generated now and E-Way is eligible.
            # It intentionally does not require pre-existing IRN.
            "can_generate_irn_and_eway": can_open and (not is_b2c) and can_generate_irn and eway_flow_eligible and eway_generation_not_already_done,
            "can_generate_eway": can_generate_eway,
            "can_generate_eway_b2c": can_generate_eway and is_b2c,
            "can_load_eway_prefill": can_open and (not is_b2c) and irn_generated and eway_flow_eligible and not eway_generated,
            "can_load_eway_b2c_prefill": can_open and is_b2c and not eway_generated,
            "can_cancel_irn": can_cancel_irn,
            "can_cancel_eway": can_cancel_eway,
            "can_get_irn_details": can_open and (einvoice_applicable or irn_generated or irn_cancelled),
            "can_get_gstn_details": can_open and einvoice_applicable,
            "can_get_b2c_qrcode": can_open and is_b2c,
            "can_get_eway_details": can_open and (eway_applicable or eway_generated or eway_cancelled),
            "can_get_eway_by_irn": can_open and (einvoice_applicable or irn_generated or irn_cancelled),
            "can_update_eway_vehicle": can_open and eway_generated,
            "can_update_eway_transporter": can_open and eway_generated,
            "can_extend_eway_validity": can_open and eway_generated,
            "state": {
                "invoice_confirmed_or_posted": can_open,
                "is_b2c": is_b2c,
                "einvoice_applicable": einvoice_applicable,
                "eway_applicable": eway_applicable,
                "irn_generated": irn_generated,
                "irn_cancelled": irn_cancelled,
                "eway_generated": eway_generated,
                "eway_cancelled": eway_cancelled,
            },
        }

    @staticmethod
    def assert_action_allowed(inv: SalesInvoiceHeader, action_key: str) -> None:
        flags = SalesComplianceService.compliance_action_flags(inv)
        if bool(flags.get(action_key)):
            return
        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="COMPLIANCE_POLICY_GUARD",
            outcome="FAILED",
            user=None,
            error_code="COMPLIANCE_ACTION_BLOCKED",
            error_message=f"Action '{action_key}' blocked by policy/state guard.",
            request_json={"action_key": action_key, "flags": flags},
        )
        raise ValidationError(f"Compliance action '{action_key}' is not allowed for current invoice state.")

    @staticmethod
    def _ewb_state(ewb: Any) -> Optional[Dict[str, Any]]:
        """
        Normalized EWB snapshot for UI.
        Never raises if fields are missing.
        """
        if not ewb:
            return None

        def g(name: str, default=None):
            return getattr(ewb, name, default)

        # Some projects store enum int, some store string; keep both safe.
        status_val = g("status", None)
        try:
            status_label = g("get_status_display")() if hasattr(ewb, "get_status_display") else None
        except Exception:
            status_label = None

        return {
            "id": g("id"),
            "status": status_val,
            "status_name": status_label,
            "ewb_no": g("ewb_no"),
            "ewb_date": g("ewb_date"),
            "valid_upto": g("valid_upto"),

            # transport inputs you persist
            "distance_km": g("distance_km"),
            "transport_mode": g("transport_mode"),
            "vehicle_no": g("vehicle_no"),
            "transporter_id": g("transporter_id"),
            "transporter_name": g("transporter_name"),
            "trans_doc_no": g("trans_doc_no"),
            "trans_doc_date": g("trans_doc_date"),

            # diagnostics
            "attempt_count": g("attempt_count"),
            "last_error": g("last_error") or g("error_message"),
        }

    def _assert_confirmed_for_irn(self) -> None:
        if self.invoice.status not in (self.invoice.Status.CONFIRMED, self.invoice.Status.POSTED):
            raise ValidationError("Invoice must be CONFIRMED or POSTED before generating IRN.")

    def _buyer_account(self) -> AccountModel:
        inv = self.invoice
        for attr in ("customer", "buyer", "party", "account"):
            if hasattr(inv, attr) and getattr(inv, f"{attr}_id", None):
                return getattr(inv, attr)
        for id_attr in ("customer_id", "buyer_id", "party_id", "account_id"):
            if hasattr(inv, id_attr) and getattr(inv, id_attr):
                return AccountModel.objects.get(pk=getattr(inv, id_attr))
        raise ValidationError("Buyer account FK not found on SalesInvoiceHeader.")

    def _ensure_einvoice_row(self) -> SalesEInvoice:
        obj, _ = SalesEInvoice.objects.get_or_create(
            invoice=self.invoice,
            defaults={
                "created_by": self.user,
                "updated_by": self.user,
                "status": SalesEInvoiceStatus.PENDING,
            },
        )
        return obj

    def _ensure_eway_row(self) -> SalesEWayBill:
        obj, _ = SalesEWayBill.objects.get_or_create(
            invoice=self.invoice,
            defaults={
                "created_by": self.user,
                "updated_by": self.user,
                "status": SalesEWayStatus.PENDING,
            },
        )
        return obj

    @transaction.atomic
    def ensure_rows(self, *, eway_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Ensure compliance artifact rows exist and keep NOT_APPLICABLE status aligned
        with current invoice applicability flags.
        """
        inv = self.invoice
        self.assert_action_allowed(inv, "can_ensure")
        einv = self._ensure_einvoice_row()
        ewb = self._ensure_eway_row()

        if not bool(getattr(inv, "is_einvoice_applicable", False)):
            if einv.status in (SalesEInvoiceStatus.PENDING, SalesEInvoiceStatus.FAILED):
                einv.status = SalesEInvoiceStatus.NOT_APPLICABLE
                einv.updated_by = self.user
                einv.save(update_fields=["status", "updated_by", "updated_at"])
        elif einv.status == SalesEInvoiceStatus.NOT_APPLICABLE:
            einv.status = SalesEInvoiceStatus.PENDING
            einv.updated_by = self.user
            einv.save(update_fields=["status", "updated_by", "updated_at"])

        if not bool(getattr(inv, "is_eway_applicable", False)):
            if ewb.status in (SalesEWayStatus.PENDING, SalesEWayStatus.FAILED):
                ewb.status = SalesEWayStatus.NOT_APPLICABLE
                ewb.updated_by = self.user
                ewb.save(update_fields=["status", "updated_by", "updated_at"])
        elif ewb.status == SalesEWayStatus.NOT_APPLICABLE:
            ewb.status = SalesEWayStatus.PENDING
            ewb.updated_by = self.user
            ewb.save(update_fields=["status", "updated_by", "updated_at"])

        # Optional upsert of transport details from ensure payload.
        if eway_data:
            trans_mode = eway_data.get("trans_mode")
            transport_mode = eway_data.get("transport_mode")
            if trans_mode is None and transport_mode is not None:
                trans_mode = str(transport_mode)

            changed_fields = []
            if "distance_km" in eway_data:
                ewb.distance_km = int(eway_data.get("distance_km")) if eway_data.get("distance_km") is not None else None
                changed_fields.append("distance_km")
            if trans_mode is not None:
                ewb.transport_mode = int(trans_mode) if str(trans_mode).isdigit() else None
                changed_fields.append("transport_mode")
            if "transporter_id" in eway_data:
                ewb.transporter_id = (eway_data.get("transporter_id") or "").strip() or None
                changed_fields.append("transporter_id")
            if "transporter_name" in eway_data:
                ewb.transporter_name = (eway_data.get("transporter_name") or "").strip() or None
                changed_fields.append("transporter_name")
            if "trans_doc_no" in eway_data:
                ewb.doc_no = (eway_data.get("trans_doc_no") or "").strip() or None
                changed_fields.append("doc_no")
            if "trans_doc_date" in eway_data:
                ewb.doc_date = eway_data.get("trans_doc_date")
                changed_fields.append("doc_date")
            if "doc_type" in eway_data:
                ewb.doc_type = (eway_data.get("doc_type") or "").strip() or None
                changed_fields.append("doc_type")
            if "vehicle_no" in eway_data:
                ewb.vehicle_no = (eway_data.get("vehicle_no") or "").strip() or None
                changed_fields.append("vehicle_no")
            if "vehicle_type" in eway_data:
                ewb.vehicle_type = eway_data.get("vehicle_type") or None
                changed_fields.append("vehicle_type")
            if "disp_dtls" in eway_data:
                ewb.disp_dtls_json = eway_data.get("disp_dtls")
                changed_fields.append("disp_dtls_json")
            if "exp_ship_dtls" in eway_data:
                ewb.exp_ship_dtls_json = eway_data.get("exp_ship_dtls")
                changed_fields.append("exp_ship_dtls_json")

            if changed_fields:
                ewb.updated_by = self.user
                changed_fields.extend(["updated_by", "updated_at"])
                ewb.save(update_fields=list(dict.fromkeys(changed_fields)))

        return {
            "einvoice_artifact_id": einv.id,
            "einvoice_status": einv.status,
            "eway_artifact_id": ewb.id,
            "eway_status": ewb.status,
            "eway_transport": {
                "distance_km": ewb.distance_km,
                "transport_mode": ewb.transport_mode,
                "transporter_id": ewb.transporter_id,
                "transporter_name": ewb.transporter_name,
                "doc_type": ewb.doc_type,
                "doc_no": ewb.doc_no,
                "doc_date": ewb.doc_date,
                "vehicle_no": ewb.vehicle_no,
                "vehicle_type": ewb.vehicle_type,
                "disp_dtls": ewb.disp_dtls_json,
                "exp_ship_dtls": ewb.exp_ship_dtls_json,
            },
        }

    @staticmethod
    def _parse_dt(x: Any):
        """
        MasterGST often returns: "01/03/2026 03:44:00 PM" or "2026-03-01 15:44:00"
        We'll try parse_datetime best-effort.
        """
        if not x:
            return None
        s = str(x).strip()

        dt = parse_datetime(s.replace(" ", "T")) or parse_datetime(s)
        if dt:
            if timezone.is_naive(dt):
                return timezone.make_aware(dt)
            return dt

        for fmt in (
            "%d/%m/%Y %I:%M:%S %p",  # 05/03/2026 10:22:00 PM
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
        ):
            try:
                return timezone.make_aware(datetime.strptime(s, fmt))
            except Exception:
                continue
        return None

    @staticmethod
    def _first_error_from_status_desc(status_desc: str) -> tuple[Optional[str], Optional[str]]:
        """
        status_desc may be:
          - JSON array string: [{"ErrorCode":"4038","ErrorMessage":"..."}]
          - plain string message
        """
        if not status_desc:
            return None, None
        try:
            arr = json.loads(status_desc)
            if isinstance(arr, list) and arr:
                return str(arr[0].get("ErrorCode") or "") or None, str(arr[0].get("ErrorMessage") or "") or None
        except Exception:
            pass
        return None, status_desc

    @staticmethod
    def _invoice_number(inv: SalesInvoiceHeader) -> Optional[str]:
        return getattr(inv, "sales_number", None) or getattr(inv, "invoice_number", None) or getattr(inv, "doc_no", None)

    @staticmethod
    def _stcd(value: Any) -> Optional[str]:
        s = str(value).strip() if value is not None else ""
        if not s or s in ("0", "00"):
            return None
        if s.isdigit() and len(s) == 1:
            s = "0" + s
        return s

    @staticmethod
    def _extract_status_error(resp: Dict[str, Any], default_code: str, default_msg: str) -> tuple[str, str, Optional[str], Optional[str]]:
        status_desc = str(resp.get("status_desc") or "")
        code, msg = SalesComplianceService._first_error_from_status_desc(status_desc)

        # Fallbacks for non-standard provider error shapes
        if not code:
            code = (
                (str(resp.get("error_cd")).strip() if resp.get("error_cd") not in (None, "") else None)
                or (str(resp.get("ErrorCode")).strip() if resp.get("ErrorCode") not in (None, "") else None)
            )
        if not msg:
            msg = (
                (str(resp.get("message")).strip() if resp.get("message") not in (None, "") else None)
                or (str(resp.get("Message")).strip() if resp.get("Message") not in (None, "") else None)
                or (str(resp.get("error_message")).strip() if resp.get("error_message") not in (None, "") else None)
                or (str(resp.get("ErrorMessage")).strip() if resp.get("ErrorMessage") not in (None, "") else None)
            )
        err_block = resp.get("error") or resp.get("Error")
        if isinstance(err_block, dict):
            code = code or (
                str(err_block.get("error_cd") or err_block.get("ErrorCode") or "").strip() or None
            )
            msg = msg or (
                str(err_block.get("message") or err_block.get("ErrorMessage") or "").strip() or None
            )

        # Some non-json responses are wrapped into _raw_text string JSON by _safe_json.
        raw_text = resp.get("_raw_text")
        if (not code or not msg) and isinstance(raw_text, str) and raw_text.strip().startswith("{"):
            try:
                raw_obj = json.loads(raw_text)
                raw_status_desc = str(raw_obj.get("status_desc") or "")
                rc, rm = SalesComplianceService._first_error_from_status_desc(raw_status_desc)
                code = code or rc
                msg = msg or rm
                code = code or (
                    str(raw_obj.get("error_cd") or raw_obj.get("ErrorCode") or "").strip() or None
                )
                msg = msg or (
                    str(raw_obj.get("message") or raw_obj.get("ErrorMessage") or "").strip() or None
                )
            except Exception:
                pass
        info = ComplianceErrorCatalogService.resolve(code=(code or default_code), message=(msg or default_msg))
        return (info.code or default_code, info.message or default_msg, info.reason, info.resolution)

    # -------------------------
    # Credential resolver (ONE ONLY)
    # -------------------------

    @staticmethod
    def _mastergst_env_from_settings() -> int:
        # Accept int enum or string names from either setting key.
        raw = getattr(settings, "SALES_MASTERGST_ENV", None)
        if raw is None:
            raw = getattr(settings, "MASTERGST_ENV", MasterGSTEnvironment.SANDBOX)
        if isinstance(raw, str):
            s = raw.strip().upper()
            return int(MasterGSTEnvironment.SANDBOX if s == "SANDBOX" else MasterGSTEnvironment.PRODUCTION)
        return int(raw)

    @staticmethod
    def _get_mastergst_cred_for_entity(
        entity,
        *,
        provider_name: Optional[str] = None,
        service_scope: int = MasterGSTServiceScope.EINVOICE,
    ) -> SalesMasterGSTCredential:
        provider_label = (provider_name or SalesComplianceService._einvoice_provider_name()).strip().lower()
        env = SalesComplianceService._mastergst_env_from_settings()
        scope = int(service_scope)
        cred = CredentialResolver.provider_for_entity(
            entity.id,
            provider_name=provider_label,
            service_scope=scope,
        )

        missing = []
        if not cred.gstin: missing.append("gstin")
        if not cred.client_id: missing.append("client_id")
        if not cred.client_secret: missing.append("client_secret")
        if not cred.email: missing.append("email")
        if not cred.gst_username: missing.append("gst_username")
        if not cred.gst_password: missing.append("gst_password")

        if missing:
            scope_label = MasterGSTServiceScope(scope).label.upper()
            raise ValidationError(f"{provider_label.title()} {scope_label} credential incomplete: {', '.join(missing)}")

        undecryptable = []
        if not (cred.get_client_secret() or "").strip():
            undecryptable.append("client_secret")
        if not (cred.get_gst_password() or "").strip():
            undecryptable.append("gst_password")
        if undecryptable:
            scope_label = MasterGSTServiceScope(scope).label.upper()
            raise ValidationError(
                f"{provider_label.title()} {scope_label} credential secret invalid or not decryptable: {', '.join(undecryptable)}. "
                "Re-save the credential secrets in the current environment."
            )

        gst_row = entity.gst_registrations.filter(isactive=True, is_primary=True).only("gstin").first()
        entity_gstin = str(getattr(gst_row, "gstin", "") or "").strip().upper()
        credential_gstin = str(getattr(cred, "gstin", "") or "").strip().upper()
        if entity_gstin and credential_gstin and entity_gstin != credential_gstin:
            raise ValidationError(
                f"{provider_label.title()} credential GSTIN ({credential_gstin}) does not match the entity primary GSTIN ({entity_gstin}). "
                f"Update the {MasterGSTServiceScope(scope).label.lower()} credential or the entity GST registration before generating IRN/E-Way."
            )

        return cred

    @staticmethod
    def _stamp_einvoice_provenance(
        einv: SalesEInvoice,
        *,
        provider_name: str,
        cred: Optional[SalesMasterGSTCredential] = None,
    ) -> None:
        einv.provider_name = (provider_name or "").strip().lower() or None
        env_value = getattr(cred, "environment", None)
        if env_value in (None, ""):
            env_value = SalesComplianceService._mastergst_env_from_settings()
        try:
            einv.provider_environment = int(env_value)
        except (TypeError, ValueError):
            einv.provider_environment = None
        cred_gstin = str(getattr(cred, "gstin", "") or "").strip().upper()
        einv.credential_gstin = cred_gstin or None

    @staticmethod
    def _stamp_eway_provenance(
        ewb: SalesEWayBill,
        *,
        provider_name: str,
        source: str,
        cred: Optional[SalesMasterGSTCredential] = None,
    ) -> None:
        ewb.provider_name = (provider_name or "").strip().lower() or None
        env_value = getattr(cred, "environment", None)
        if env_value in (None, ""):
            env_value = SalesComplianceService._mastergst_env_from_settings()
        try:
            ewb.provider_environment = int(env_value)
        except (TypeError, ValueError):
            ewb.provider_environment = None
        cred_gstin = str(getattr(cred, "gstin", "") or "").strip().upper()
        ewb.credential_gstin = cred_gstin or None
        ewb.eway_source = source

    @staticmethod
    def _apply_eway_summary(
        ewb: SalesEWayBill,
        *,
        ewb_no: Optional[Any],
        ewb_date: Optional[Any],
        valid_upto: Optional[Any],
        raw: Optional[Dict[str, Any]] = None,
        preserve_existing: bool = True,
        mark_generated: bool = True,
    ) -> None:
        resolved_ewb_no = str(ewb_no or "").strip() or None
        resolved_ewb_date = SalesComplianceService._parse_dt(ewb_date)
        resolved_valid_upto = SalesComplianceService._parse_dt(valid_upto)

        if preserve_existing:
            ewb.ewb_no = ewb.ewb_no or resolved_ewb_no
            ewb.ewb_date = ewb.ewb_date or resolved_ewb_date
            ewb.valid_upto = ewb.valid_upto or resolved_valid_upto
        else:
            ewb.ewb_no = resolved_ewb_no
            ewb.ewb_date = resolved_ewb_date
            ewb.valid_upto = resolved_valid_upto

        if mark_generated and ewb.ewb_no and int(getattr(ewb, "status", 0) or 0) != int(SalesEWayStatus.CANCELLED):
            ewb.status = SalesEWayStatus.GENERATED
            ewb.last_success_at = timezone.now()
        if raw is not None:
            ewb.last_response_json = raw
            ewb.last_error_code = None
            ewb.last_error_message = None

    @staticmethod
    def _mirror_eway_summary_to_einvoice(
        einv: Optional[SalesEInvoice],
        ewb: Optional[SalesEWayBill],
        *,
        user=None,
        preserve_existing: bool = True,
    ) -> None:
        if not einv or not ewb or not getattr(ewb, "ewb_no", None):
            return
        if preserve_existing:
            einv.ewb_no = einv.ewb_no or ewb.ewb_no
            einv.ewb_date = einv.ewb_date or ewb.ewb_date
            einv.ewb_valid_upto = einv.ewb_valid_upto or ewb.valid_upto
        else:
            einv.ewb_no = ewb.ewb_no
            einv.ewb_date = ewb.ewb_date
            einv.ewb_valid_upto = ewb.valid_upto
        if user:
            einv.updated_by = user
        einv.save(update_fields=["ewb_no", "ewb_date", "ewb_valid_upto", "updated_by", "updated_at"])

    # -------------------------
    # IRN
    # -------------------------

    @transaction.atomic
    def generate_irn(self) -> SalesEInvoice:
        einv = self._ensure_einvoice_row()
        if einv.status == SalesEInvoiceStatus.GENERATED and einv.irn:
            return einv  # idempotent

        self.assert_action_allowed(self.invoice, "can_generate_irn")
        self._assert_confirmed_for_irn()
        if int(getattr(self.invoice, "supply_category", 0) or 0) == int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C):
            raise ValidationError("IRN generation is not allowed for B2C invoices.")

        payload = IRPPayloadBuilder(
            self.invoice,
            min_hsn_digits=self._einvoice_min_hsn_digits(self.invoice),
        ).build()
        payload["SellerDtls"] = seller_from_entity(self.invoice.entity)

        buyer = self._buyer_account()
        payload["BuyerDtls"] = buyer_from_account(
            buyer,
            pos_state=getattr(self.invoice, "place_of_supply_state_code", None),
        )

        provider_name = self._einvoice_provider_name()
        cred = self._get_mastergst_cred_for_entity(
            self.invoice.entity,
            provider_name=provider_name,
            service_scope=MasterGSTServiceScope.EINVOICE,
        )
        self._stamp_einvoice_provenance(einv, provider_name=provider_name, cred=cred)

        einv.last_request_json = payload
        einv.attempt_count = int(einv.attempt_count or 0) + 1
        einv.last_attempt_at = timezone.now()
        einv.status = SalesEInvoiceStatus.PENDING
        einv.updated_by = self.user
        einv.save()

        # if you use ProviderRegistry, keep it; else call MasterGST provider directly
        provider = ProviderRegistry.get_einvoice(provider_name)  # noqa: F821 (if you keep ProviderRegistry)

        try:
            result = provider.generate_irn(invoice=self.invoice, payload=payload)
        except Exception as ex:
            einv.status = SalesEInvoiceStatus.FAILED
            einv.last_error_code = "PROVIDER_EXCEPTION"
            einv.last_error_message = str(ex)
            einv.updated_by = self.user
            einv.save()
            ComplianceAuditService.log_action(
                invoice=self.invoice,
                action_type="IRN_GENERATE",
                outcome="FAILED",
                user=self.user,
                error_code="PROVIDER_EXCEPTION",
                error_message=str(ex),
                request_json=payload,
            )
            ComplianceAuditService.open_exception(
                invoice=self.invoice,
                exception_type="IRN_GENERATION_FAILED",
                error_code="PROVIDER_EXCEPTION",
                error_message=str(ex),
                payload_json=result.raw if "result" in locals() else None,
            )
            raise

        einv.last_response_json = result.raw
        if not result.ok or not result.irn:
            err_info = ComplianceErrorCatalogService.resolve(code=result.error_code, message=result.error_message or "IRN generation failed.")
            einv.status = SalesEInvoiceStatus.FAILED
            einv.last_error_code = err_info.code or "IRN_FAILED"
            einv.last_error_message = err_info.as_text()
            einv.updated_by = self.user
            einv.save()
            ComplianceAuditService.log_action(
                invoice=self.invoice,
                action_type="IRN_GENERATE",
                outcome="FAILED",
                user=self.user,
                error_code=einv.last_error_code,
                error_message=einv.last_error_message,
                request_json=payload,
                response_json=result.raw,
            )
            ComplianceAuditService.open_exception(
                invoice=self.invoice,
                exception_type="IRN_GENERATION_FAILED",
                error_code=einv.last_error_code,
                error_message=einv.last_error_message,
                payload_json=result.raw,
            )
            raise ValidationError({"message": einv.last_error_message, "code": einv.last_error_code, "raw": einv.last_response_json})

        einv.irn = result.irn
        einv.ack_no = result.ack_no
        einv.ack_date = result.ack_date
        einv.signed_invoice = result.signed_invoice
        einv.signed_qr_code = result.signed_qr_code

        # if IRP response contains EWB details
        einv.ewb_no = result.ewb_no
        einv.ewb_date = result.ewb_date
        einv.ewb_valid_upto = result.ewb_valid_upto

        einv.status = SalesEInvoiceStatus.GENERATED
        einv.last_success_at = timezone.now()
        einv.last_error_code = None
        einv.last_error_message = None
        einv.updated_by = self.user
        einv.save()
        if einv.ewb_no:
            ewb = self._ensure_eway_row()
            self._stamp_eway_provenance(ewb, provider_name=provider_name, source=SalesEWaySource.IRN, cred=cred)
            self._apply_eway_summary(
                ewb,
                ewb_no=einv.ewb_no,
                ewb_date=einv.ewb_date,
                valid_upto=einv.ewb_valid_upto,
                raw=result.raw,
                preserve_existing=True,
            )
            ewb.updated_by = self.user
            ewb.save()
        ComplianceAuditService.log_action(
            invoice=self.invoice,
            action_type="IRN_GENERATE",
            outcome="SUCCESS",
            user=self.user,
            request_json=payload,
            response_json=result.raw,
        )
        ComplianceAuditService.resolve_exception(invoice=self.invoice, exception_type="IRN_GENERATION_FAILED", user=self.user)

        return einv

    @transaction.atomic
    def cancel_irn(self, *, reason_code: str, remarks: Optional[str] = None) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_cancel_irn")
        einv = self._ensure_einvoice_row()
        if not einv.irn or einv.status != SalesEInvoiceStatus.GENERATED:
            raise ValidationError("IRN cancel is allowed only for generated IRN.")
        ewb = getattr(inv, "eway_artifact", None)
        if ewb and int(getattr(ewb, "status", 0) or 0) == int(SalesEWayStatus.GENERATED) and getattr(ewb, "ewb_no", None):
            raise ValidationError("IRN cannot be cancelled while EWB is active. Cancel E-Way Bill first.")

        provider_name = self._einvoice_provider_name()
        cred = self._get_mastergst_cred_for_entity(
            inv.entity,
            provider_name=provider_name,
            service_scope=MasterGSTServiceScope.EINVOICE,
        )
        self._stamp_einvoice_provenance(einv, provider_name=provider_name, cred=cred)
        provider = ProviderRegistry.get_einvoice(provider_name)
        result = provider.cancel_irn(invoice=inv, irn=einv.irn, reason_code=reason_code, remarks=remarks)

        SalesEInvoiceCancel.objects.create(
            einvoice=einv,
            cancel_reason_code=str(reason_code),
            cancel_remarks=(remarks or "")[:255],
            irp_cancel_date=timezone.now() if result.ok else None,
            last_request_json={"irn": einv.irn, "reason_code": reason_code, "remarks": remarks},
            last_response_json=result.raw,
            error_code=result.error_code,
            error_message=result.error_message,
            created_by=self.user,
        )

        if not result.ok:
            err_info = ComplianceErrorCatalogService.resolve(
                code=result.error_code or "IRN_CANCEL_FAILED",
                message=result.error_message or "IRN cancellation failed.",
            )
            einv.last_error_code = err_info.code or "IRN_CANCEL_FAILED"
            einv.last_error_message = err_info.as_text()
            einv.updated_by = self.user
            einv.save()
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="IRN_CANCEL",
                outcome="FAILED",
                user=self.user,
                error_code=einv.last_error_code,
                error_message=einv.last_error_message,
                response_json=result.raw,
            )
            ComplianceAuditService.open_exception(
                invoice=inv,
                exception_type="STATUTORY_CANCEL_REQUIRED",
                error_code=einv.last_error_code,
                error_message=einv.last_error_message,
                payload_json=result.raw or {},
            )
            raise ValidationError(
                {
                    "code": err_info.code,
                    "message": err_info.message,
                    "reason": err_info.reason,
                    "resolution": err_info.resolution,
                    "raw": result.raw,
                }
            )

        einv.status = SalesEInvoiceStatus.CANCELLED
        einv.updated_by = self.user
        einv.last_error_code = None
        einv.last_error_message = None
        einv.save()
        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="IRN_CANCEL",
            outcome="SUCCESS",
            user=self.user,
            request_json={"irn": einv.irn, "reason_code": reason_code, "remarks": remarks},
            response_json=result.raw,
        )
        ComplianceAuditService.resolve_exception(invoice=inv, exception_type="STATUTORY_CANCEL_REQUIRED", user=self.user)
        return {"status": "SUCCESS", "irn": einv.irn, "raw": result.raw}

    @transaction.atomic
    def get_irn_details(self, *, irn: Optional[str] = None, supplier_gstin: Optional[str] = None) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_irn_details")
        einv = self._ensure_einvoice_row()
        irn_to_fetch = (irn or einv.irn or "").strip()
        if not irn_to_fetch:
            raise ValidationError("IRN is required. Generate IRN first or pass irn in request.")

        provider_name = self._einvoice_provider_name()
        cred = self._get_mastergst_cred_for_entity(
            inv.entity,
            provider_name=provider_name,
            service_scope=MasterGSTServiceScope.EINVOICE,
        )
        self._stamp_einvoice_provenance(einv, provider_name=provider_name, cred=cred)
        provider = ProviderRegistry.get_einvoice(provider_name)
        result = provider.get_irn_details(invoice=inv, irn=irn_to_fetch, supplier_gstin=supplier_gstin)

        if not result.ok:
            err_info = ComplianceErrorCatalogService.resolve(
                code=result.error_code or "IRN_GET_FAILED",
                message=result.error_message or "IRN details fetch failed.",
            )
            einv.last_error_code = err_info.code or "IRN_GET_FAILED"
            einv.last_error_message = err_info.as_text()
            einv.last_response_json = result.raw
            einv.updated_by = self.user
            einv.save()
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="IRN_FETCH",
                outcome="FAILED",
                user=self.user,
                error_code=einv.last_error_code,
                error_message=einv.last_error_message,
                request_json={"irn": irn_to_fetch, "supplier_gstin": supplier_gstin},
                response_json=result.raw,
            )
            raise ValidationError(
                {
                    "code": err_info.code,
                    "message": err_info.message,
                    "reason": err_info.reason,
                    "resolution": err_info.resolution,
                    "raw": result.raw,
                }
            )

        einv.irn = result.irn or einv.irn
        einv.ack_no = result.ack_no or einv.ack_no
        einv.ack_date = self._parse_dt(result.ack_date) or einv.ack_date
        einv.signed_invoice = result.signed_invoice or einv.signed_invoice
        einv.signed_qr_code = result.signed_qr_code or einv.signed_qr_code
        einv.ewb_no = result.ewb_no or einv.ewb_no
        einv.ewb_date = self._parse_dt(result.ewb_date) or einv.ewb_date
        einv.ewb_valid_upto = self._parse_dt(result.ewb_valid_upto) or einv.ewb_valid_upto
        einv.last_response_json = result.raw
        einv.last_error_code = None
        einv.last_error_message = None
        if einv.irn:
            einv.status = SalesEInvoiceStatus.GENERATED
            einv.last_success_at = timezone.now()
        einv.updated_by = self.user
        einv.save()

        # Sync EWB summary in artifact when present
        if einv.ewb_no:
            ewb = self._ensure_eway_row()
            self._stamp_eway_provenance(ewb, provider_name=provider_name, source=SalesEWaySource.IRN, cred=cred)
            self._apply_eway_summary(
                ewb,
                ewb_no=einv.ewb_no,
                ewb_date=einv.ewb_date,
                valid_upto=einv.ewb_valid_upto,
                raw=result.raw,
                preserve_existing=True,
            )
            ewb.updated_by = self.user
            ewb.save()

        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="IRN_FETCH",
            outcome="INFO",
            user=self.user,
            request_json={"irn": irn_to_fetch, "supplier_gstin": supplier_gstin},
            response_json=result.raw,
        )
        ComplianceAuditService.resolve_exception(
            invoice=inv,
            exception_type="IRN_GENERATION_FAILED",
            user=self.user,
        )
        return {
            "status": "SUCCESS",
            "irn": einv.irn,
            "ack_no": einv.ack_no,
            "ack_date": einv.ack_date,
            "ewb_no": einv.ewb_no,
            "ewb_date": einv.ewb_date,
            "ewb_valid_upto": einv.ewb_valid_upto,
            "raw": result.raw,
        }

    @staticmethod
    def _resolve_irn_doc_type(inv) -> str:
        doc_type = int(getattr(inv, "doc_type", SalesInvoiceHeader.DocType.TAX_INVOICE) or SalesInvoiceHeader.DocType.TAX_INVOICE)
        if doc_type == int(SalesInvoiceHeader.DocType.CREDIT_NOTE):
            return "CRN"
        if doc_type == int(SalesInvoiceHeader.DocType.DEBIT_NOTE):
            return "DBN"
        return "INV"

    @transaction.atomic
    def get_irn_details_by_doc(
        self,
        *,
        doc_type: Optional[str] = None,
        doc_number: Optional[str] = None,
        doc_date: Optional[Any] = None,
    ) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_irn_details")
        einv = self._ensure_einvoice_row()

        resolved_doc_type = (doc_type or self._resolve_irn_doc_type(inv) or "").strip().upper()
        resolved_doc_number = str(
            doc_number
            or getattr(inv, "invoice_number", None)
            or getattr(inv, "doc_no", None)
            or ""
        ).strip()
        resolved_doc_date = doc_date or getattr(inv, "bill_date", None)
        if not resolved_doc_type:
            raise ValidationError("Document type is required.")
        if not resolved_doc_number:
            raise ValidationError("Document number is required.")
        if not resolved_doc_date:
            raise ValidationError("Document date is required.")

        if hasattr(resolved_doc_date, "strftime"):
            resolved_doc_date_text = resolved_doc_date.strftime("%d/%m/%Y")
        else:
            parsed_doc_date = datetime.strptime(str(resolved_doc_date), "%Y-%m-%d")
            resolved_doc_date_text = parsed_doc_date.strftime("%d/%m/%Y")

        provider_name = self._einvoice_provider_name()
        cred = self._get_mastergst_cred_for_entity(
            inv.entity,
            provider_name=provider_name,
            service_scope=MasterGSTServiceScope.EINVOICE,
        )
        self._stamp_einvoice_provenance(einv, provider_name=provider_name, cred=cred)
        provider = ProviderRegistry.get_einvoice(provider_name)
        result = provider.get_irn_details_by_doc(
            invoice=inv,
            doc_type=resolved_doc_type,
            doc_number=resolved_doc_number,
            doc_date=resolved_doc_date_text,
        )

        if not result.ok:
            err_info = ComplianceErrorCatalogService.resolve(
                code=result.error_code or "IRN_GET_BY_DOC_FAILED",
                message=result.error_message or "IRN details by document fetch failed.",
            )
            einv.last_error_code = err_info.code or "IRN_GET_BY_DOC_FAILED"
            einv.last_error_message = err_info.as_text()
            einv.last_response_json = result.raw
            einv.updated_by = self.user
            einv.save()
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="IRN_FETCH",
                outcome="FAILED",
                user=self.user,
                error_code=einv.last_error_code,
                error_message=einv.last_error_message,
                request_json={"doc_type": resolved_doc_type, "doc_number": resolved_doc_number, "doc_date": resolved_doc_date_text},
                response_json=result.raw,
            )
            raise ValidationError(
                {
                    "code": err_info.code,
                    "message": err_info.message,
                    "reason": err_info.reason,
                    "resolution": err_info.resolution,
                    "raw": result.raw,
                }
            )

        einv.irn = result.irn or einv.irn
        einv.ack_no = result.ack_no or einv.ack_no
        einv.ack_date = self._parse_dt(result.ack_date) or einv.ack_date
        einv.signed_invoice = result.signed_invoice or einv.signed_invoice
        einv.signed_qr_code = result.signed_qr_code or einv.signed_qr_code
        einv.ewb_no = result.ewb_no or einv.ewb_no
        einv.ewb_date = self._parse_dt(result.ewb_date) or einv.ewb_date
        einv.ewb_valid_upto = self._parse_dt(result.ewb_valid_upto) or einv.ewb_valid_upto
        einv.last_response_json = result.raw
        einv.last_error_code = None
        einv.last_error_message = None
        if einv.irn:
            einv.status = SalesEInvoiceStatus.GENERATED
            einv.last_success_at = timezone.now()
        einv.updated_by = self.user
        einv.save()

        if einv.ewb_no:
            ewb = self._ensure_eway_row()
            self._stamp_eway_provenance(ewb, provider_name=provider_name, source=SalesEWaySource.IRN, cred=cred)
            self._apply_eway_summary(
                ewb,
                ewb_no=einv.ewb_no,
                ewb_date=einv.ewb_date,
                valid_upto=einv.ewb_valid_upto,
                raw=result.raw,
                preserve_existing=True,
            )
            ewb.updated_by = self.user
            ewb.save()

        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="IRN_FETCH",
            outcome="INFO",
            user=self.user,
            request_json={"doc_type": resolved_doc_type, "doc_number": resolved_doc_number, "doc_date": resolved_doc_date_text},
            response_json=result.raw,
        )
        ComplianceAuditService.resolve_exception(
            invoice=inv,
            exception_type="IRN_GENERATION_FAILED",
            user=self.user,
        )
        return {
            "status": "SUCCESS",
            "irn": einv.irn,
            "ack_no": einv.ack_no,
            "ack_date": einv.ack_date,
            "ewb_no": einv.ewb_no,
            "ewb_date": einv.ewb_date,
            "ewb_valid_upto": einv.ewb_valid_upto,
            "raw": result.raw,
        }

    @transaction.atomic
    def get_gstn_details(self, *, gstin: str) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_gstn_details")
        gstin_value = (gstin or "").strip().upper()
        if not gstin_value:
            raise ValidationError("GSTIN is required.")

        provider_name = self._einvoice_provider_name()
        provider = ProviderRegistry.get_einvoice(provider_name)
        result = provider.get_gstn_details(invoice=inv, gstin=gstin_value)

        if not result.ok:
            err_info = ComplianceErrorCatalogService.resolve(
                code=result.error_code or "GSTN_GET_FAILED",
                message=result.error_message or "GSTN details fetch failed.",
            )
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="GSTN_FETCH",
                outcome="FAILED",
                user=self.user,
                error_code=err_info.code or "GSTN_GET_FAILED",
                error_message=err_info.as_text(),
                request_json={"gstin": gstin_value},
                response_json=result.raw,
            )
            raise ValidationError(
                {
                    "code": err_info.code,
                    "message": err_info.message,
                    "reason": err_info.reason,
                    "resolution": err_info.resolution,
                    "raw": result.raw,
                }
            )

        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="GSTN_FETCH",
            outcome="INFO",
            user=self.user,
            request_json={"gstin": gstin_value},
            response_json=result.raw,
        )
        return {
            "status": "SUCCESS",
            "gstin": result.gstin or gstin_value,
            "legal_name": result.legal_name,
            "trade_name": result.trade_name,
            "registration_status": result.status,
            "raw": result.raw,
        }

    @transaction.atomic
    def get_b2c_qrcode(
        self,
        *,
        upiid: Optional[str] = None,
        bankaccno: Optional[str] = None,
        bankifsccode: Optional[str] = None,
        accountholdername: Optional[str] = None,
        sgstin: Optional[str] = None,
        docno: Optional[str] = None,
        docdate: Optional[Any] = None,
        totinvval: Optional[Any] = None,
        igstamount: Optional[Any] = None,
        cgstamount: Optional[Any] = None,
        sgstamount: Optional[Any] = None,
        cessamount: Optional[Any] = None,
    ) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_b2c_qrcode")
        einv = self._ensure_einvoice_row()

        entity = getattr(inv, "entity", None)
        bank = entity_primary_bank_account(entity) if entity else None
        contact = entity_primary_contact(entity) if entity else None

        seller_gstin = (sgstin or getattr(inv, "seller_gstin", None) or entity_primary_gstin(entity) or "").strip().upper()
        document_no = str(docno or getattr(inv, "invoice_number", None) or getattr(inv, "doc_no", None) or "").strip()
        document_date = docdate or getattr(inv, "bill_date", None)
        total_invoice_value = totinvval if totinvval is not None else getattr(inv, "grand_total", None)
        total_igst = igstamount if igstamount is not None else getattr(inv, "total_igst", None)
        total_cgst = cgstamount if cgstamount is not None else getattr(inv, "total_cgst", None)
        total_sgst = sgstamount if sgstamount is not None else getattr(inv, "total_sgst", None)
        total_cess = cessamount if cessamount is not None else getattr(inv, "total_cess", None)
        account_number = str(bankaccno or getattr(bank, "account_number", None) or "").strip()
        ifsc_code = str(bankifsccode or getattr(bank, "ifsc_code", None) or "").strip().upper()
        account_holder = str(
            accountholdername
            or getattr(contact, "name", None)
            or getattr(entity, "legalname", None)
            or getattr(entity, "entityname", None)
            or ""
        ).strip()

        if not seller_gstin:
            raise ValidationError("Seller GSTIN is required for B2C QR code.")
        if not document_no:
            raise ValidationError("Document number is required for B2C QR code.")
        if not document_date:
            raise ValidationError("Document date is required for B2C QR code.")
        if not account_number:
            raise ValidationError("Primary entity bank account number is required for B2C QR code.")
        if not ifsc_code:
            raise ValidationError("Primary entity bank IFSC code is required for B2C QR code.")
        if not account_holder:
            raise ValidationError("Account holder name is required for B2C QR code.")

        if hasattr(document_date, "strftime"):
            document_date_text = document_date.strftime("%d-%m-%Y")
        else:
            document_date_text = datetime.strptime(str(document_date), "%Y-%m-%d").strftime("%d-%m-%Y")

        payload = {
            "sgstin": seller_gstin,
            "docno": document_no,
            "docdate": document_date_text,
            "totinvval": self._money_text(total_invoice_value),
            "bankaccno": account_number,
            "bankifsccode": ifsc_code,
            "accountholdername": account_holder,
            "igstamount": self._money_text(total_igst),
            "cgstamount": self._money_text(total_cgst),
            "sgstamount": self._money_text(total_sgst),
            "cessamount": self._money_text(total_cess),
        }
        upi_value = str(upiid or "").strip()
        if upi_value:
            payload["upiid"] = upi_value

        provider_name = self._einvoice_provider_name()
        provider = ProviderRegistry.get_einvoice(provider_name)
        result = provider.get_b2c_qrcode(invoice=inv, payload=payload)

        if not result.ok:
            err_info = ComplianceErrorCatalogService.resolve(
                code=result.error_code or "B2C_QRCODE_FAILED",
                message=result.error_message or "B2C QR code fetch failed.",
            )
            einv.last_error_code = err_info.code or "B2C_QRCODE_FAILED"
            einv.last_error_message = err_info.as_text()
            einv.last_response_json = result.raw
            einv.updated_by = self.user
            einv.save(update_fields=["last_error_code", "last_error_message", "last_response_json", "updated_by", "updated_at"])
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="B2C_QRCODE_FETCH",
                outcome="FAILED",
                user=self.user,
                error_code=einv.last_error_code,
                error_message=einv.last_error_message,
                request_json=payload,
                response_json=result.raw,
            )
            raise ValidationError(
                {
                    "code": err_info.code,
                    "message": err_info.message,
                    "reason": err_info.reason,
                    "resolution": err_info.resolution,
                    "raw": result.raw,
                }
            )

        einv.signed_qr_code = result.qr_code or einv.signed_qr_code
        einv.last_response_json = result.raw
        einv.last_error_code = None
        einv.last_error_message = None
        einv.updated_by = self.user
        einv.save(update_fields=["signed_qr_code", "last_response_json", "last_error_code", "last_error_message", "updated_by", "updated_at"])

        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="B2C_QRCODE_FETCH",
            outcome="INFO",
            user=self.user,
            request_json=payload,
            response_json=result.raw,
        )
        return {
            "status": "SUCCESS",
            "qr_code": result.qr_code,
            "raw": result.raw,
        }

    @transaction.atomic
    def sync_gstin_from_cp(self, *, gstin: str) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_gstn_details")
        gstin_value = (gstin or "").strip().upper()
        if not gstin_value:
            raise ValidationError("GSTIN is required.")

        provider_name = self._einvoice_provider_name()
        provider = ProviderRegistry.get_einvoice(provider_name)
        result = provider.sync_gstin_from_cp(invoice=inv, gstin=gstin_value)

        if not result.ok:
            err_info = ComplianceErrorCatalogService.resolve(
                code=result.error_code or "GSTN_SYNC_FAILED",
                message=result.error_message or "GSTIN sync from CP failed.",
            )
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="GSTN_FETCH",
                outcome="FAILED",
                user=self.user,
                error_code=err_info.code or "GSTN_SYNC_FAILED",
                error_message=err_info.as_text(),
                request_json={"gstin": gstin_value, "mode": "sync_from_cp"},
                response_json=result.raw,
            )
            raise ValidationError(
                {
                    "code": err_info.code,
                    "message": err_info.message,
                    "reason": err_info.reason,
                    "resolution": err_info.resolution,
                    "raw": result.raw,
                }
            )

        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="GSTN_FETCH",
            outcome="INFO",
            user=self.user,
            request_json={"gstin": gstin_value, "mode": "sync_from_cp"},
            response_json=result.raw,
        )
        return {
            "status": "SUCCESS",
            "gstin": result.gstin or gstin_value,
            "legal_name": result.legal_name,
            "trade_name": result.trade_name,
            "registration_status": result.status,
            "raw": result.raw,
        }

    @transaction.atomic
    def get_eway_details_by_irn(self, *, irn: Optional[str] = None, supplier_gstin: Optional[str] = None) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_by_irn")
        einv = self._ensure_einvoice_row()
        irn_to_fetch = (irn or einv.irn or "").strip()
        if not irn_to_fetch:
            raise ValidationError("IRN is required. Generate IRN first or pass irn in request.")

        provider_name = self._einvoice_provider_name()
        cred = self._get_mastergst_cred_for_entity(
            inv.entity,
            provider_name=provider_name,
            service_scope=MasterGSTServiceScope.EINVOICE,
        )
        provider = ProviderRegistry.get_einvoice(provider_name)
        result = provider.get_eway_details_by_irn(invoice=inv, irn=irn_to_fetch, supplier_gstin=supplier_gstin)

        ewb = self._ensure_eway_row()
        self._stamp_eway_provenance(ewb, provider_name=provider_name, source=SalesEWaySource.IRN, cred=cred)
        if not result.ok:
            err_info = ComplianceErrorCatalogService.resolve(
                code=result.error_code or "EWB_GET_FAILED",
                message=result.error_message or "EWB details fetch by IRN failed.",
            )
            ewb.last_error_code = err_info.code or "EWB_GET_FAILED"
            ewb.last_error_message = err_info.as_text()
            ewb.last_response_json = result.raw
            ewb.updated_by = self.user
            ewb.save()
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="EWB_FETCH",
                outcome="FAILED",
                user=self.user,
                error_code=ewb.last_error_code,
                error_message=ewb.last_error_message,
                request_json={"irn": irn_to_fetch, "supplier_gstin": supplier_gstin},
                response_json=result.raw,
            )
            raise ValidationError(
                {
                    "code": err_info.code,
                    "message": err_info.message,
                    "reason": err_info.reason,
                    "resolution": err_info.resolution,
                    "raw": result.raw,
                }
            )

        self._apply_eway_summary(
            ewb,
            ewb_no=result.ewb_no,
            ewb_date=result.ewb_date,
            valid_upto=result.valid_upto,
            raw=result.raw,
            preserve_existing=True,
        )
        ewb.updated_by = self.user
        ewb.save()

        self._mirror_eway_summary_to_einvoice(einv, ewb, user=self.user, preserve_existing=True)

        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="EWB_FETCH",
            outcome="INFO",
            user=self.user,
            request_json={"irn": irn_to_fetch, "supplier_gstin": supplier_gstin},
            response_json=result.raw,
        )
        ComplianceAuditService.resolve_exception(
            invoice=inv,
            exception_type="EWB_GENERATION_FAILED",
            user=self.user,
        )
        return {
            "status": "SUCCESS",
            "irn": irn_to_fetch,
            "ewb_no": ewb.ewb_no,
            "ewb_date": ewb.ewb_date,
            "valid_upto": ewb.valid_upto,
            "raw": result.raw,
        }

    @transaction.atomic
    def get_eway_details(self, *, ewb_no: Optional[str] = None) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        ewb = self._ensure_eway_row()
        ewb_no_to_fetch = str(ewb_no or getattr(ewb, "ewb_no", None) or "").strip()
        if not ewb_no_to_fetch:
            raise ValidationError("E-Way bill number is required.")

        provider_name = self._eway_provider_name()
        cred = self._get_mastergst_cred_for_entity(
            inv.entity,
            provider_name=provider_name,
            service_scope=MasterGSTServiceScope.EWAY,
        )
        provider = ProviderRegistry.get_eway(provider_name)
        result = provider.get_eway_details(invoice=inv, ewb_no=ewb_no_to_fetch)
        self._stamp_eway_provenance(
            ewb,
            provider_name=provider_name,
            source=getattr(ewb, "eway_source", None) or SalesEWaySource.DIRECT,
            cred=cred,
        )

        if not result.ok:
            err_info = ComplianceErrorCatalogService.resolve(
                code=result.error_code or "EWB_GET_FAILED",
                message=result.error_message or "EWB details fetch failed.",
            )
            ewb.last_error_code = err_info.code or "EWB_GET_FAILED"
            ewb.last_error_message = err_info.as_text()
            ewb.last_response_json = result.raw
            ewb.updated_by = self.user
            ewb.save()
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="EWB_FETCH",
                outcome="FAILED",
                user=self.user,
                error_code=ewb.last_error_code,
                error_message=ewb.last_error_message,
                request_json={"ewb_no": ewb_no_to_fetch},
                response_json=result.raw,
            )
            raise ValidationError(
                {
                    "code": err_info.code,
                    "message": err_info.message,
                    "reason": err_info.reason,
                    "resolution": err_info.resolution,
                    "raw": result.raw,
                }
            )

        self._apply_eway_summary(
            ewb,
            ewb_no=result.ewb_no,
            ewb_date=result.ewb_date,
            valid_upto=result.valid_upto,
            raw=result.raw,
            preserve_existing=True,
        )
        ewb.updated_by = self.user
        ewb.save()

        einv = getattr(inv, "einvoice_artifact", None)
        self._mirror_eway_summary_to_einvoice(einv, ewb, user=self.user, preserve_existing=True)

        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="EWB_FETCH",
            outcome="INFO",
            user=self.user,
            request_json={"ewb_no": ewb_no_to_fetch},
            response_json=result.raw,
        )
        ComplianceAuditService.resolve_exception(
            invoice=inv,
            exception_type="EWB_GENERATION_FAILED",
            user=self.user,
        )
        return {
            "status": "SUCCESS",
            "ewb_no": ewb.ewb_no,
            "ewb_date": ewb.ewb_date,
            "valid_upto": ewb.valid_upto,
            "raw": result.raw,
        }

    @transaction.atomic
    def get_eway_transporter_details(self, *, transporter_id: str) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        transporter_value = str(transporter_id or "").strip()
        if not transporter_value:
            raise ValidationError("Transporter ID is required.")

        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_transporter_details(invoice=inv, transporter_id=transporter_value)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_TRANSPORTER_DETAILS_FAILED",
            lookup_message="Transporter details fetch failed.",
            request_json={"transporter_id": transporter_value},
        )

    @transaction.atomic
    def get_eway_gstin_details(self, *, gstin: str) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        gstin_value = str(gstin or "").strip().upper()
        if not gstin_value:
            raise ValidationError("GSTIN is required.")

        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_gstin_details(invoice=inv, gstin=gstin_value)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_GSTIN_DETAILS_FAILED",
            lookup_message="GSTIN details fetch failed.",
            request_json={"gstin": gstin_value},
        )

    @transaction.atomic
    def get_eway_hsn_details(self, *, hsn_code: str) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        hsn_value = str(hsn_code or "").strip()
        if not hsn_value:
            raise ValidationError("HSN code is required.")

        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_hsn_details(invoice=inv, hsn_code=hsn_value)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_HSN_DETAILS_FAILED",
            lookup_message="HSN details fetch failed.",
            request_json={"hsn_code": hsn_value},
        )

    @transaction.atomic
    def get_eway_error_list(self) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")

        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_error_list(invoice=inv)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_ERROR_LIST_FAILED",
            lookup_message="E-Way error list fetch failed.",
            request_json={},
        )

    def _finalize_eway_lookup_result(
        self,
        *,
        inv: SalesInvoiceHeader,
        result,
        lookup_code: str,
        lookup_message: str,
        request_json: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not result.ok:
            err_info = ComplianceErrorCatalogService.resolve(
                code=result.error_code or lookup_code,
                message=result.error_message or lookup_message,
            )
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="EWB_REFERENCE_FETCH",
                outcome="FAILED",
                user=self.user,
                error_code=err_info.code or lookup_code,
                error_message=err_info.as_text(),
                request_json=request_json,
                response_json=result.raw,
            )
            raise ValidationError(
                {
                    "code": err_info.code,
                    "message": err_info.message,
                    "reason": err_info.reason,
                    "resolution": err_info.resolution,
                    "raw": result.raw,
                }
            )

        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="EWB_REFERENCE_FETCH",
            outcome="INFO",
            user=self.user,
            request_json=request_json,
            response_json=result.raw,
        )
        return {
            "status": "SUCCESS",
            "data": result.data,
            "raw": result.raw,
        }

    @transaction.atomic
    def reject_eway(self, *, ewb_no: Optional[str] = None) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        art = self._ensure_eway_row()
        ewb_no_value = str(ewb_no or getattr(art, "ewb_no", None) or "").strip()
        if not ewb_no_value:
            raise ValidationError("E-Way bill number is required.")

        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.reject_eway(invoice=inv, ewb_no=ewb_no_value)
        out = self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_REJECT_FAILED",
            lookup_message="E-Way rejection failed.",
            request_json={"ewb_no": ewb_no_value},
        )
        art.last_response_json = result.raw
        art.last_error_code = None
        art.last_error_message = None
        art.updated_by = self.user
        art.save(update_fields=["last_response_json", "last_error_code", "last_error_message", "updated_by", "updated_at"])
        return out

    @transaction.atomic
    def get_trip_sheet(self, *, trip_sheet_no: str) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        trip_sheet_value = str(trip_sheet_no or "").strip()
        if not trip_sheet_value:
            raise ValidationError("Trip sheet number is required.")
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_trip_sheet(invoice=inv, trip_sheet_no=trip_sheet_value)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_TRIP_SHEET_FAILED",
            lookup_message="Trip sheet fetch failed.",
            request_json={"trip_sheet_no": trip_sheet_value},
        )

    @staticmethod
    def _resolve_eway_doc_type(inv) -> str:
        doc_type = int(getattr(inv, "doc_type", SalesInvoiceHeader.DocType.TAX_INVOICE) or SalesInvoiceHeader.DocType.TAX_INVOICE)
        if doc_type == int(SalesInvoiceHeader.DocType.CREDIT_NOTE):
            return "CHL"
        if doc_type == int(SalesInvoiceHeader.DocType.DEBIT_NOTE):
            return "OTH"
        return "INV"

    @transaction.atomic
    def get_eway_by_document(self, *, doc_type: Optional[str] = None, doc_no: Optional[str] = None) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        resolved_doc_type = str(doc_type or self._resolve_eway_doc_type(inv) or "").strip().upper()
        resolved_doc_no = str(doc_no or getattr(inv, "invoice_number", None) or getattr(inv, "doc_no", None) or "").strip()
        if not resolved_doc_type:
            raise ValidationError("Document type is required.")
        if not resolved_doc_no:
            raise ValidationError("Document number is required.")
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_eway_by_document(invoice=inv, doc_type=resolved_doc_type, doc_no=resolved_doc_no)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_GET_BY_DOC_FAILED",
            lookup_message="E-Way document lookup failed.",
            request_json={"doc_type": resolved_doc_type, "doc_no": resolved_doc_no},
        )

    @staticmethod
    def _format_eway_date(value: Any) -> str:
        if not value:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%d/%m/%Y")
        return str(value)

    @transaction.atomic
    def get_eway_bills_for_transporter(self, *, date: Any) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        formatted_date = self._format_eway_date(date)
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_eway_bills_for_transporter(invoice=inv, date=formatted_date)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_FOR_TRANSPORTER_FAILED",
            lookup_message="Transporter E-Way list fetch failed.",
            request_json={"date": formatted_date},
        )

    @transaction.atomic
    def get_eway_bill_report_by_transporter_assigned_date(self, *, date: Any, state_code: str) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        formatted_date = self._format_eway_date(date)
        state_code_value = str(state_code or "").strip()
        if not state_code_value:
            raise ValidationError("State code is required.")
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_eway_bill_report_by_transporter_assigned_date(
            invoice=inv,
            date=formatted_date,
            state_code=state_code_value,
        )
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_TRANSPORTER_REPORT_FAILED",
            lookup_message="Transporter assigned-date report fetch failed.",
            request_json={"date": formatted_date, "state_code": state_code_value},
        )

    @transaction.atomic
    def get_eway_bills_by_date(self, *, date: Any) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        formatted_date = self._format_eway_date(date)
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_eway_bills_by_date(invoice=inv, date=formatted_date)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_BY_DATE_FAILED",
            lookup_message="E-Way date-wise list fetch failed.",
            request_json={"date": formatted_date},
        )

    @transaction.atomic
    def get_eway_bills_rejected_by_others(self, *, date: Any) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        formatted_date = self._format_eway_date(date)
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_eway_bills_rejected_by_others(invoice=inv, date=formatted_date)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_REJECTED_BY_OTHERS_FAILED",
            lookup_message="Rejected E-Way list fetch failed.",
            request_json={"date": formatted_date},
        )

    @transaction.atomic
    def get_eway_bills_for_transporter_by_gstin(self, *, gen_gstin: str, date: Any) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        formatted_date = self._format_eway_date(date)
        gen_gstin_value = str(gen_gstin or "").strip().upper()
        if not gen_gstin_value:
            raise ValidationError("Generator GSTIN is required.")
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_eway_bills_for_transporter_by_gstin(
            invoice=inv,
            gen_gstin=gen_gstin_value,
            date=formatted_date,
        )
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_FOR_TRANSPORTER_GSTIN_FAILED",
            lookup_message="Transporter GSTIN/date report fetch failed.",
            request_json={"gen_gstin": gen_gstin_value, "date": formatted_date},
        )

    @transaction.atomic
    def get_eway_bills_for_transporter_by_state(self, *, state_code: str, date: Any) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        formatted_date = self._format_eway_date(date)
        state_code_value = str(state_code or "").strip()
        if not state_code_value:
            raise ValidationError("State code is required.")
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_eway_bills_for_transporter_by_state(
            invoice=inv,
            state_code=state_code_value,
            date=formatted_date,
        )
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_FOR_TRANSPORTER_STATE_FAILED",
            lookup_message="Transporter state/date report fetch failed.",
            request_json={"state_code": state_code_value, "date": formatted_date},
        )

    @transaction.atomic
    def get_eway_bills_of_other_party(self, *, date: Any) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        formatted_date = self._format_eway_date(date)
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.get_eway_bills_of_other_party(invoice=inv, date=formatted_date)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_OTHER_PARTY_FAILED",
            lookup_message="Other party E-Way list fetch failed.",
            request_json={"date": formatted_date},
        )

    def _resolve_eway_artifact_number(self) -> str:
        art = self._ensure_eway_row()
        ewb_no_value = str(getattr(art, "ewb_no", None) or "").strip()
        if not ewb_no_value:
            raise ValidationError("E-Way bill number is required.")
        return ewb_no_value

    @staticmethod
    def _to_vendor_eway_bill_refs(rows: Any) -> list[Dict[str, Any]]:
        refs = []
        for row in rows or []:
            if isinstance(row, dict):
                ewb_no = row.get("ewb_no", row.get("ewbNo"))
            else:
                ewb_no = row
            if ewb_no in (None, ""):
                continue
            refs.append({"ewbNo": ewb_no})
        return refs

    def _build_generate_consolidated_eway_payload(self, req: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "fromPlace": req.get("from_place"),
            "fromState": req.get("from_state_code"),
            "transMode": req.get("trans_mode"),
            "tripSheetEwbBills": self._to_vendor_eway_bill_refs(req.get("eway_bill_numbers")),
            "vehicleNo": req.get("vehicle_no") or "",
            "transDocNo": req.get("trans_doc_no") or "",
            "transDocDate": self._format_eway_date(req.get("trans_doc_date")),
        }

    def _build_regenerate_trip_sheet_payload(self, req: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "fromPlace": req.get("from_place"),
            "fromState": req.get("from_state_code"),
            "reasonCode": req.get("reason_code"),
            "reasonRem": req.get("remarks"),
            "transMode": req.get("trans_mode"),
            "tripSheetNo": req.get("trip_sheet_no"),
            "vehicleNo": req.get("vehicle_no") or "",
            "transDocNo": req.get("trans_doc_no") or "",
            "transDocDate": self._format_eway_date(req.get("trans_doc_date")),
        }

    def _build_initiate_multi_vehicle_payload(self, req: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ewbNo": req.get("ewb_no") or self._resolve_eway_artifact_number(),
            "fromPlace": req.get("from_place"),
            "fromState": req.get("from_state_code"),
            "toPlace": req.get("to_place"),
            "toState": req.get("to_state_code"),
            "reasonCode": req.get("reason_code"),
            "reasonRem": req.get("remarks"),
            "transMode": req.get("trans_mode"),
            "totalQuantity": req.get("total_quantity"),
            "unitCode": req.get("unit_code"),
        }

    def _build_add_multi_vehicle_payload(self, req: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ewbNo": req.get("ewb_no") or self._resolve_eway_artifact_number(),
            "groupNo": req.get("group_no"),
            "vehicleNo": req.get("vehicle_no"),
            "transDocNo": req.get("trans_doc_no"),
            "transDocDate": self._format_eway_date(req.get("trans_doc_date")),
            "quantity": req.get("quantity"),
        }

    def _build_update_multi_vehicle_payload(self, req: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ewbNo": req.get("ewb_no") or self._resolve_eway_artifact_number(),
            "groupNo": req.get("group_no"),
            "oldvehicleNo": req.get("old_vehicle_no"),
            "newVehicleNo": req.get("new_vehicle_no"),
            "oldTranNo": req.get("old_trans_no") or "",
            "newTranNo": req.get("new_trans_no") or "",
            "fromPlace": req.get("from_place"),
            "fromState": req.get("from_state_code"),
            "reasonCode": req.get("reason_code"),
            "reasonRem": req.get("remarks"),
        }

    @transaction.atomic
    def generate_consolidated_eway(self, *, req: Dict[str, Any]) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        payload = self._build_generate_consolidated_eway_payload(req)
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.generate_consolidated_eway(invoice=inv, payload=payload)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_CONSOLIDATED_FAILED",
            lookup_message="Consolidated E-Way generation failed.",
            request_json=payload,
        )

    @transaction.atomic
    def regenerate_trip_sheet(self, *, req: Dict[str, Any]) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        payload = self._build_regenerate_trip_sheet_payload(req)
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.regenerate_trip_sheet(invoice=inv, payload=payload)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_TRIP_SHEET_REGENERATE_FAILED",
            lookup_message="Trip sheet regeneration failed.",
            request_json=payload,
        )

    @transaction.atomic
    def initiate_multi_vehicle(self, *, req: Dict[str, Any]) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        payload = self._build_initiate_multi_vehicle_payload(req)
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.initiate_multi_vehicle(invoice=inv, payload=payload)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_MULTI_INIT_FAILED",
            lookup_message="Multi vehicle initiation failed.",
            request_json=payload,
        )

    @transaction.atomic
    def add_multi_vehicle(self, *, req: Dict[str, Any]) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        payload = self._build_add_multi_vehicle_payload(req)
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.add_multi_vehicle(invoice=inv, payload=payload)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_MULTI_ADD_FAILED",
            lookup_message="Add multi vehicle failed.",
            request_json=payload,
        )

    @transaction.atomic
    def update_multi_vehicle(self, *, req: Dict[str, Any]) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_get_eway_details")
        payload = self._build_update_multi_vehicle_payload(req)
        provider = ProviderRegistry.get_eway(self._eway_provider_name())
        result = provider.update_multi_vehicle(invoice=inv, payload=payload)
        return self._finalize_eway_lookup_result(
            inv=inv,
            result=result,
            lookup_code="EWB_MULTI_UPDATE_FAILED",
            lookup_message="Update multi vehicle failed.",
            request_json=payload,
        )

    @staticmethod
    def _get_irn(inv: SalesInvoiceHeader) -> str:
        einv = getattr(inv, "einvoice_artifact", None)
        if not einv:
            raise ValidationError("E-Invoice artifact not found. Generate IRN first.")
        if einv.status != SalesEInvoiceStatus.GENERATED:
            raise ValidationError(f"E-Invoice not SUCCESS (status={einv.status}).")
        if not einv.irn:
            raise ValidationError("IRN missing in e-invoice artifact.")
        return einv.irn

    # -------------------------
    # E-Way Prefill (B2B IRN-based)
    # -------------------------

    @staticmethod
    def build_eway_prefill(inv: SalesInvoiceHeader, entity: Any) -> Dict[str, Any]:
        SalesComplianceService._ensure_invoice_eligible_for_eway(inv)

        base = {
            "invoice_id": inv.id,
            "invoice_number": SalesComplianceService._invoice_number(inv),
            "bill_date": getattr(inv, "bill_date", None),
            "invoice_status": inv.status,
        }

        try:
            irn = SalesComplianceService._get_irn(inv)
        except Exception as e:
            return {
                "eligible": False,
                "reason": str(e),
                "irn": "",
                "default_disp_dtls": None,
                "default_exp_ship_dtls": None,
                "last_transport": None,
                "last_status": None,
                **base,
            }

        ent_addr = entity_primary_address(entity)
        default_disp = build_disp_dtls(
            name=getattr(entity, "legalname", None) or getattr(entity, "entityname", None),
            addr1=getattr(ent_addr, "line1", None),
            addr2=getattr(ent_addr, "line2", None),
            loc=getattr(getattr(ent_addr, "city", None), "cityname", None) if getattr(ent_addr, "city", None) else None,
            pin=getattr(ent_addr, "pincode", None),
            stcd=SalesComplianceService._stcd(getattr(getattr(ent_addr, "state", None), "statecode", None))
                or SalesComplianceService._stcd(getattr(inv, "seller_state_code", None)),
        )

        default_ship = SalesComplianceService._normalize_exp_ship_dtls(
            inv,
            SalesComplianceService._default_exp_ship_dtls(inv),
        )

        art = getattr(inv, "eway_artifact", None)
        last_transport = None
        last_status = None

        if art:
            last_status = {
                "status": art.status,
                "ewb_no": art.ewb_no,
                "ewb_date": art.ewb_date,
                "valid_upto": art.valid_upto,
                "last_error_code": art.last_error_code,
                "last_error_message": art.last_error_message,
            }
            last_transport = {
                "transporter_id": art.transporter_id,
                "transporter_name": art.transporter_name,
                "transport_mode": art.transport_mode,
                "distance_km": art.distance_km,
                "vehicle_no": art.vehicle_no,
                "vehicle_type": art.vehicle_type,
                "doc_no": art.doc_no,
                "doc_date": art.doc_date,
                "disp_dtls_json": art.disp_dtls_json,
                "exp_ship_dtls_json": art.exp_ship_dtls_json,
            }

        return {
            "eligible": True,
            "reason": None,
            "irn": irn,
            "default_disp_dtls": default_disp,
            "default_exp_ship_dtls": default_ship,
            "last_transport": last_transport,
            "last_status": last_status,
            **base,
        }

    # -------------------------
    # E-Way Generate (B2B IRN-based)
    # -------------------------

    @staticmethod
    @transaction.atomic
    def generate_eway(inv: SalesInvoiceHeader, entity, req: Dict[str, Any], created_by=None) -> Dict[str, Any]:
        SalesComplianceService.assert_action_allowed(inv, "can_generate_eway")
        SalesComplianceService._ensure_invoice_eligible_for_eway(inv)
        irn = SalesComplianceService._get_irn(inv)

        art, _ = SalesEWayBill.objects.select_for_update().get_or_create(invoice=inv)

        if art.status == SalesEWayStatus.GENERATED and art.ewb_no:
            return {
                "status": "SUCCESS",
                "eway": {"ewb_no": art.ewb_no, "ewb_date": art.ewb_date, "valid_upto": art.valid_upto},
                "attempt_count": art.attempt_count,
                "idempotent": True,
                "raw": art.last_response_json,
            }

        if int(art.attempt_count or 0) >= MAX_EWAY_ATTEMPTS:
            raise ValidationError("Max retry limit reached. Contact admin.")

        disp_in = req.get("disp_dtls") or art.disp_dtls_json
        ship_in = req.get("exp_ship_dtls") or art.exp_ship_dtls_json

        if not disp_in:
            ent_addr = entity_primary_address(entity)
            disp_in = build_disp_dtls(
                name=getattr(entity, "legalname", None) or getattr(entity, "entityname", None),
                addr1=getattr(ent_addr, "line1", None),
                addr2=getattr(ent_addr, "line2", None),
                loc=getattr(getattr(ent_addr, "city", None), "cityname", None) if getattr(ent_addr, "city", None) else None,
                pin=getattr(ent_addr, "pincode", None),
                stcd=getattr(getattr(ent_addr, "state", None), "statecode", None) if getattr(ent_addr, "state", None) else getattr(inv, "seller_state_code", None),
            )

        ship_in = SalesComplianceService._normalize_exp_ship_dtls(inv, ship_in)

        eway_input = EWayInput(
            distance_km=int(req["distance_km"]),
            trans_mode=str(req["trans_mode"]),
            transporter_id=str(req.get("transporter_id") or ""),
            transporter_name=str(req.get("transporter_name") or ""),
            trans_doc_no=str(req.get("trans_doc_no") or ""),
            trans_doc_date=req.get("trans_doc_date"),
            vehicle_no=req.get("vehicle_no"),
            vehicle_type=req.get("vehicle_type"),
            disp_dtls=disp_in,
            exp_ship_dtls=ship_in,
        )

        payload = build_generate_eway_payload(irn=irn, x=eway_input)

        art.attempt_count = int(art.attempt_count or 0) + 1
        art.last_attempt_at = timezone.now()

        art.distance_km = eway_input.distance_km
        art.transport_mode = int(eway_input.trans_mode) if str(eway_input.trans_mode).isdigit() else None
        art.transporter_id = eway_input.transporter_id or None
        art.transporter_name = eway_input.transporter_name or None
        art.doc_no = eway_input.trans_doc_no or None
        art.doc_date = eway_input.trans_doc_date
        art.vehicle_no = eway_input.vehicle_no
        art.vehicle_type = eway_input.vehicle_type

        art.disp_dtls_json = disp_in
        art.exp_ship_dtls_json = ship_in
        art.last_request_json = payload
        if created_by:
            art.updated_by = created_by
            if not art.created_by:
                art.created_by = created_by
        cred = SalesComplianceService._get_mastergst_cred_for_entity(
            entity,
            provider_name=SalesComplianceService._eway_provider_name(),
            service_scope=MasterGSTServiceScope.EWAY,
        )
        SalesComplianceService._stamp_eway_provenance(
            art,
            provider_name=SalesComplianceService._eway_provider_name(),
            source=SalesEWaySource.IRN,
            cred=cred,
        )
        art.save()

        client = MasterGSTClient(cred=cred, provider_name=SalesComplianceService._eway_provider_name())

        resp = client.generate_ewaybill(payload)
        art.last_response_json = resp

        status_cd = str(resp.get("status_cd") or "")
        if status_cd == "1":
            data = resp.get("data") or {}
            art.status = SalesEWayStatus.GENERATED
            art.ewb_no = str(data.get("EwbNo") or data.get("ewayBillNo") or "") or None
            art.ewb_date = SalesComplianceService._parse_dt(data.get("EwbDt") or data.get("ewayBillDate"))
            art.valid_upto = SalesComplianceService._parse_dt(data.get("EwbValidTill") or data.get("validUpto"))
            art.last_success_at = timezone.now()
            art.last_error_code = None
            art.last_error_message = None
            art.save()
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="EWB_GENERATE",
                outcome="SUCCESS",
                user=created_by,
                request_json=payload,
                response_json=resp,
            )
            ComplianceAuditService.resolve_exception(invoice=inv, exception_type="EWB_GENERATION_FAILED", user=created_by)

            return {
                "status": "SUCCESS",
                "eway": {"ewb_no": art.ewb_no, "ewb_date": art.ewb_date, "valid_upto": art.valid_upto},
                "attempt_count": art.attempt_count,
                "idempotent": False,
                "raw": resp,
            }

        status_desc = str(resp.get("status_desc") or "")
        code, msg = SalesComplianceService._first_error_from_status_desc(status_desc)
        err_info = ComplianceErrorCatalogService.resolve(code=(code or "EWB_FAILED"), message=(msg or "E-Way generation failed."))
        art.status = SalesEWayStatus.FAILED
        art.last_error_code = err_info.code or "EWB_FAILED"
        art.last_error_message = err_info.as_text()
        art.save()
        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="EWB_GENERATE",
            outcome="FAILED",
            user=created_by,
            error_code=art.last_error_code,
            error_message=art.last_error_message,
            request_json=payload,
            response_json=resp,
        )
        ComplianceAuditService.open_exception(
            invoice=inv,
            exception_type="EWB_GENERATION_FAILED",
            error_code=art.last_error_code,
            error_message=art.last_error_message,
            payload_json=resp,
        )

        return {
            "status": "FAILED",
            "error_code": err_info.code,
            "error_message": err_info.message,
            "reason": err_info.reason,
            "resolution": err_info.resolution,
            "attempt_count": art.attempt_count,
            "idempotent": False,
            "raw": resp,
        }

    @transaction.atomic
    def cancel_eway(self, *, reason_code: str, remarks: Optional[str] = None) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_cancel_eway")
        art = self._ensure_eway_row()
        if not art.ewb_no or art.status != SalesEWayStatus.GENERATED:
            raise ValidationError("E-Way cancel is allowed only for generated EWB.")

        cred = self._get_mastergst_cred_for_entity(
            inv.entity,
            provider_name=self._eway_provider_name(),
            service_scope=MasterGSTServiceScope.EWAY,
        )
        self._stamp_eway_provenance(
            art,
            provider_name=self._eway_provider_name(),
            source=getattr(art, "eway_source", None) or SalesEWaySource.IRN,
            cred=cred,
        )
        client = MasterGSTClient(cred=cred, provider_name=self._eway_provider_name())
        ewb_no_raw = str(art.ewb_no or "").strip()
        reason_raw = str(reason_code or "").strip()
        payload = {
            "ewbNo": int(ewb_no_raw) if ewb_no_raw.isdigit() else ewb_no_raw,
            "cancelRsnCode": int(reason_raw) if reason_raw.isdigit() else reason_raw,
            "cancelRmrk": (remarks or "Cancelled from system")[:100],
        }
        resp = client.cancel_eway_direct(payload)
        status_cd = str(resp.get("status_cd") or "")
        if status_cd != "1":
            code, msg, reason, resolution = self._extract_status_error(resp, "EWB_CANCEL_FAILED", "E-Way cancellation failed.")
            art.last_error_code = code
            art.last_error_message = ComplianceErrorCatalogService.resolve(code=code, message=msg).as_text()
            art.save(update_fields=["last_error_code", "last_error_message", "updated_at"])
            SalesEWayBillCancel.objects.create(
                eway=art,
                cancel_reason_code=str(reason_code),
                cancel_remarks=(remarks or "")[:255],
                portal_cancel_date=None,
                last_request_json=payload,
                last_response_json=resp,
                error_code=code,
                error_message=art.last_error_message,
                created_by=self.user,
            )
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="EWB_CANCEL",
                outcome="FAILED",
                user=self.user,
                error_code=code,
                error_message=art.last_error_message,
                request_json=payload,
                response_json=resp,
            )
            ComplianceAuditService.open_exception(
                invoice=inv,
                exception_type="STATUTORY_CANCEL_REQUIRED",
                error_code=code,
                error_message=msg,
                payload_json=resp,
            )
            raise ValidationError({"code": code, "message": msg, "reason": reason, "resolution": resolution, "raw": resp})

        art.status = SalesEWayStatus.CANCELLED
        art.last_error_code = None
        art.last_error_message = None
        art.save(update_fields=["status", "last_error_code", "last_error_message", "updated_at"])
        data = resp.get("data") or {}
        portal_cancel_date = self._parse_dt(data.get("cancelDate") or data.get("CancelDate")) or timezone.now()
        SalesEWayBillCancel.objects.create(
            eway=art,
            cancel_reason_code=str(reason_code),
            cancel_remarks=(remarks or "")[:255],
            portal_cancel_date=portal_cancel_date,
            last_request_json=payload,
            last_response_json=resp,
            created_by=self.user,
        )
        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="EWB_CANCEL",
            outcome="SUCCESS",
            user=self.user,
            request_json=payload,
            response_json=resp,
        )
        ComplianceAuditService.resolve_exception(invoice=inv, exception_type="STATUTORY_CANCEL_REQUIRED", user=self.user)
        return {"status": "SUCCESS", "ewb_no": art.ewb_no, "cancel_date": portal_cancel_date, "raw": resp}

    @transaction.atomic
    def update_eway_vehicle(self, *, req: Dict[str, Any]) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_update_eway_vehicle")
        art = self._ensure_eway_row()
        if not art.ewb_no:
            raise ValidationError("EWB number not found. Generate EWB first.")

        cred = self._get_mastergst_cred_for_entity(
            inv.entity,
            provider_name=self._eway_provider_name(),
            service_scope=MasterGSTServiceScope.EWAY,
        )
        self._stamp_eway_provenance(
            art,
            provider_name=self._eway_provider_name(),
            source=getattr(art, "eway_source", None) or SalesEWaySource.IRN,
            cred=cred,
        )
        client = MasterGSTClient(cred=cred, provider_name=self._eway_provider_name())
        payload = {
            "ewbNo": str(art.ewb_no),
            "vehicleNo": str(req.get("vehicle_no") or ""),
            "fromPlace": str(req.get("from_place") or ""),
            "fromState": int(str(req.get("from_state_code") or "0")) if str(req.get("from_state_code") or "").isdigit() else str(req.get("from_state_code") or ""),
            "reasonCode": str(req.get("reason_code") or ""),
            "reasonRem": str(req.get("remarks") or ""),
            "transDocNo": str(req.get("trans_doc_no") or ""),
            "transDocDate": req.get("trans_doc_date").strftime("%d/%m/%Y") if req.get("trans_doc_date") else "",
            "transMode": str(req.get("trans_mode") or ""),
            "vehicleType": str(req.get("vehicle_type") or ""),
        }
        resp = client.update_eway_vehicle(payload)
        status_cd = str(resp.get("status_cd") or "")
        if status_cd != "1":
            code, msg, reason, resolution = self._extract_status_error(resp, "EWB_VEHICLE_UPDATE_FAILED", "E-Way vehicle update failed.")
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="EWB_VEHICLE_UPDATE",
                outcome="FAILED",
                user=self.user,
                error_code=code,
                error_message=ComplianceErrorCatalogService.resolve(code=code, message=msg).as_text(),
                request_json=payload,
                response_json=resp,
            )
            raise ValidationError({"code": code, "message": msg, "reason": reason, "resolution": resolution, "raw": resp})

        data = resp.get("data") or {}
        art.vehicle_no = req.get("vehicle_no")
        art.vehicle_type = req.get("vehicle_type") or art.vehicle_type
        art.valid_upto = self._parse_dt(data.get("validUpto") or data.get("EwbValidTill")) or art.valid_upto
        if art.ewb_no:
            art.status = SalesEWayStatus.GENERATED
        art.last_response_json = resp
        art.save(update_fields=["vehicle_no", "vehicle_type", "valid_upto", "status", "last_response_json", "updated_at"])
        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="EWB_VEHICLE_UPDATE",
            outcome="SUCCESS",
            user=self.user,
            request_json=payload,
            response_json=resp,
        )
        return {
            "status": "SUCCESS",
            "ewb_no": art.ewb_no,
            "veh_update_date": self._parse_dt(data.get("vehUpdDate")),
            "valid_upto": art.valid_upto,
            "raw": resp,
        }

    @transaction.atomic
    def update_eway_transporter(self, *, transporter_id: str) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_update_eway_transporter")
        art = self._ensure_eway_row()
        if not art.ewb_no:
            raise ValidationError("EWB number not found. Generate EWB first.")

        cred = self._get_mastergst_cred_for_entity(
            inv.entity,
            provider_name=self._eway_provider_name(),
            service_scope=MasterGSTServiceScope.EWAY,
        )
        self._stamp_eway_provenance(
            art,
            provider_name=self._eway_provider_name(),
            source=getattr(art, "eway_source", None) or SalesEWaySource.IRN,
            cred=cred,
        )
        client = MasterGSTClient(cred=cred, provider_name=self._eway_provider_name())
        payload = {"ewbNo": str(art.ewb_no), "transporterId": str(transporter_id)}
        resp = client.update_eway_transporter(payload)
        status_cd = str(resp.get("status_cd") or "")
        if status_cd != "1":
            code, msg, reason, resolution = self._extract_status_error(resp, "EWB_TRANSPORTER_UPDATE_FAILED", "E-Way transporter update failed.")
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="EWB_TRANSPORTER_UPDATE",
                outcome="FAILED",
                user=self.user,
                error_code=code,
                error_message=ComplianceErrorCatalogService.resolve(code=code, message=msg).as_text(),
                request_json=payload,
                response_json=resp,
            )
            raise ValidationError({"code": code, "message": msg, "reason": reason, "resolution": resolution, "raw": resp})

        art.transporter_id = transporter_id
        art.last_response_json = resp
        art.save(update_fields=["transporter_id", "last_response_json", "updated_at"])
        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="EWB_TRANSPORTER_UPDATE",
            outcome="SUCCESS",
            user=self.user,
            request_json=payload,
            response_json=resp,
        )
        return {"status": "SUCCESS", "ewb_no": art.ewb_no, "raw": resp}

    @transaction.atomic
    def extend_eway_validity(self, *, req: Dict[str, Any]) -> Dict[str, Any]:
        inv = self.invoice
        self.assert_action_allowed(inv, "can_extend_eway_validity")
        art = self._ensure_eway_row()
        if not art.ewb_no:
            raise ValidationError("EWB number not found. Generate EWB first.")

        cred = self._get_mastergst_cred_for_entity(
            inv.entity,
            provider_name=self._eway_provider_name(),
            service_scope=MasterGSTServiceScope.EWAY,
        )
        client = MasterGSTClient(cred=cred, provider_name=self._eway_provider_name())
        payload = {
            "ewbNo": str(art.ewb_no),
            "extnRsnCode": str(req.get("reason_code") or ""),
            "extnRemarks": str(req.get("remarks") or ""),
            "fromPlace": str(req.get("from_place") or ""),
            "fromPincode": int(req.get("from_pincode") or 0) if req.get("from_pincode") not in (None, "") else "",
            "fromState": str(req.get("from_state_code") or ""),
            "remainingDistance": int(req.get("remaining_distance_km") or 0),
            "transDocNo": str(req.get("trans_doc_no") or ""),
            "transDocDate": req.get("trans_doc_date").strftime("%d/%m/%Y") if req.get("trans_doc_date") else "",
            "transMode": str(req.get("trans_mode") or ""),
            "vehicleNo": str(req.get("vehicle_no") or ""),
            "vehicleType": str(req.get("vehicle_type") or ""),
            "consignmentStatus": str(req.get("consignment_status") or ""),
            "transitType": str(req.get("transit_type") or ""),
            "addressLine1": str(req.get("address_line1") or ""),
            "addressLine2": str(req.get("address_line2") or ""),
            "addressLine3": str(req.get("address_line3") or ""),
        }
        resp = client.extend_eway_validity(payload)
        status_cd = str(resp.get("status_cd") or "")
        if status_cd != "1":
            code, msg, reason, resolution = self._extract_status_error(resp, "EWB_EXTEND_FAILED", "E-Way validity extension failed.")
            ComplianceAuditService.log_action(
                invoice=inv,
                action_type="EWB_EXTEND",
                outcome="FAILED",
                user=self.user,
                error_code=code,
                error_message=ComplianceErrorCatalogService.resolve(code=code, message=msg).as_text(),
                request_json=payload,
                response_json=resp,
            )
            raise ValidationError({"code": code, "message": msg, "reason": reason, "resolution": resolution, "raw": resp})

        data = resp.get("data") or {}
        art.valid_upto = self._parse_dt(data.get("validUpto") or data.get("EwbValidTill")) or art.valid_upto
        art.last_response_json = resp
        art.save(update_fields=["valid_upto", "last_response_json", "updated_at"])
        ComplianceAuditService.log_action(
            invoice=inv,
            action_type="EWB_EXTEND",
            outcome="SUCCESS",
            user=self.user,
            request_json=payload,
            response_json=resp,
        )
        return {"status": "SUCCESS", "ewb_no": art.ewb_no, "valid_upto": art.valid_upto, "raw": resp}

    # -------------------------
    # E-Way Generate (B2C direct, no IRN)
    # -------------------------

    @staticmethod
    def _extract_mastergst_error(data: Dict[str, Any]) -> str:
        """
        MasterGST errors often come as:
          status_cd="0"
          status_desc='[{"ErrorCode":"4038","ErrorMessage":"..."}]'
        Sometimes status_desc is plain text or missing.
        """
        if not data:
            return "Empty response from MasterGST"

        # Prefer status_desc, else other common keys, else raw text
        desc = (
            data.get("status_desc")
            or data.get("error_message")
            or data.get("message")
            or data.get("error")
            or data.get("_raw_text")
            or ""
        )

        # status_desc can be a JSON-string array
        if isinstance(desc, str):
            s = desc.strip()
            if s.startswith("[") and s.endswith("]"):
                try:
                    arr = json.loads(s)
                    if isinstance(arr, list) and arr:
                        first = arr[0] if isinstance(arr[0], dict) else {}
                        code = first.get("ErrorCode") or first.get("error_code")
                        msg = first.get("ErrorMessage") or first.get("error_message")
                        if code and msg:
                            return f"{code} - {msg}"
                        if msg:
                            return str(msg)
                except Exception:
                    # fall through to plain text
                    pass

            if s:
                return s

        # fallback: stringify whole dict
        return str(data)

    @staticmethod
    def _eway_fail(*, data: Optional[Dict[str, Any]] = None, exc: Optional[Exception] = None) -> Dict[str, Any]:
        raw = data or {}
        if exc is not None:
            raw = {**raw, "_exception": str(exc)}

        return {
            "status": "FAILED",
            "error_code": "EWB_FAILED",
            "error_message": SalesComplianceService._extract_mastergst_error(raw) or "E-Way failed",
            "raw": raw,  # ✅ never {}
        }

    def eway_generate_b2c(self, invoice: "SalesInvoiceHeader", *, user=None) -> dict:
        self.assert_action_allowed(invoice, "can_generate_eway_b2c")
        ewb = getattr(invoice, "eway_artifact", None)
        if not ewb:
            ewb = SalesEWayBill.objects.create(invoice=invoice)

        # ✅ Idempotent success (strong)
        now = timezone.now()
        if ewb.status == SalesEWayStatus.GENERATED and ewb.ewb_no and ewb.valid_upto and ewb.valid_upto > now:
            return {"status": "SUCCESS", "ewb_no": ewb.ewb_no, "valid_upto": ewb.valid_upto, "idempotent": True}

        cred = self._get_mastergst_cred_for_entity(
            invoice.entity,
            provider_name=self._eway_provider_name(),
            service_scope=MasterGSTServiceScope.EWAY,
        )
        client = MasterGSTClient(cred=cred, provider_name=self._eway_provider_name())

        payload = build_b2c_direct_payload(invoice=invoice, ewb=ewb, entity_gstin=cred.gstin)
        self._stamp_eway_provenance(
            ewb,
            provider_name=self._eway_provider_name(),
            source=SalesEWaySource.DIRECT,
            cred=cred,
        )

        # Attempt bookkeeping
        ewb.last_request_json = payload
        ewb.last_error_code = None
        ewb.last_error_message = None
        ewb.attempt_count = int(ewb.attempt_count or 0) + 1
        ewb.last_attempt_at = now
        ewb.status = SalesEWayStatus.PENDING
        if user:
            ewb.updated_by = user
        ewb.save()

        try:
            mgst_resp = client.generate_eway_direct(payload)
        except Exception as e:
            ewb.status = SalesEWayStatus.FAILED
            ewb.last_error_code = "EWB_FAILED"
            ewb.last_error_message = str(e)
            ewb.last_response_json = {"_exception": str(e)}
            if user:
                ewb.updated_by = user
            ewb.save()
            ComplianceAuditService.log_action(
                invoice=invoice,
                action_type="EWB_B2C_GENERATE",
                outcome="FAILED",
                user=user,
                error_code="EWB_FAILED",
                error_message=str(e),
                request_json=payload,
            )
            ComplianceAuditService.open_exception(
                invoice=invoice,
                exception_type="EWB_B2C_GENERATION_FAILED",
                error_code="EWB_FAILED",
                error_message=str(e),
            )
            return self._eway_fail(data=None, exc=e)

        ewb.last_response_json = mgst_resp

        status_cd = str(mgst_resp.get("status_cd") or "")
        if status_cd == "1":
            data = mgst_resp.get("data") or {}
            self._apply_eway_summary(
                ewb,
                ewb_no=data.get("ewayBillNo") or data.get("EwbNo"),
                ewb_date=data.get("ewayBillDate") or data.get("EwbDt"),
                valid_upto=data.get("validUpto") or data.get("EwbValidTill"),
                raw=mgst_resp,
                preserve_existing=False,
            )
            if user:
                ewb.updated_by = user
            ewb.save()
            ComplianceAuditService.log_action(
                invoice=invoice,
                action_type="EWB_B2C_GENERATE",
                outcome="SUCCESS",
                user=user,
                request_json=payload,
                response_json=mgst_resp,
            )
            ComplianceAuditService.resolve_exception(invoice=invoice, exception_type="EWB_B2C_GENERATION_FAILED", user=user)

            return {"status": "SUCCESS", "ewb_no": ewb.ewb_no, "valid_upto": ewb.valid_upto, "raw": mgst_resp, "idempotent": False}

        status_desc = str(mgst_resp.get("status_desc") or "")
        code, msg = self._first_error_from_status_desc(status_desc)

        ewb.status = SalesEWayStatus.FAILED
        ewb.last_error_code = code or "EWB_FAILED"
        ewb.last_error_message = msg or self._extract_mastergst_error(mgst_resp) or "E-Way failed"
        if user:
            ewb.updated_by = user
        ewb.save()
        ComplianceAuditService.log_action(
            invoice=invoice,
            action_type="EWB_B2C_GENERATE",
            outcome="FAILED",
            user=user,
            error_code=ewb.last_error_code,
            error_message=ewb.last_error_message,
            request_json=payload,
            response_json=mgst_resp,
        )
        ComplianceAuditService.open_exception(
            invoice=invoice,
            exception_type="EWB_B2C_GENERATION_FAILED",
            error_code=ewb.last_error_code,
            error_message=ewb.last_error_message,
            payload_json=mgst_resp,
        )

        return {"status": "FAILED", "error_code": ewb.last_error_code, "error_message": ewb.last_error_message, "raw": mgst_resp}


    def eway_prefill(self, invoice):
        einv = getattr(invoice, "einvoice_artifact", None)
        ewb  = getattr(invoice, "eway_artifact", None)  # ✅ standardized

        irn = None
        if einv and getattr(einv, "irn", None) and einv.status == SalesEInvoiceStatus.GENERATED:  # ✅ SUCCESS
            irn = einv.irn

        if not irn:
            return {
                "eligible": False,
                "reason": "IRN not found / not SUCCESS. Generate IRN first.",
                "invoice_id": invoice.id,
                "invoice_status": invoice.status,
                "irn": None,
                "eway": self._ewb_state(ewb),
            }

        return {
            "eligible": True,
            "reason": None,
            "invoice_id": invoice.id,
            "invoice_status": invoice.status,
            "irn": irn,
            "eway": self._ewb_state(ewb),
        }
    

    def eway_prefill_b2c(self, invoice):
        ewb = getattr(invoice, "eway_artifact", None)  # ✅ standardized

        # ✅ standardized ship-to snapshot name
        ship = getattr(invoice, "shipto_snapshot", None)
        ent = getattr(invoice, "entity", None)
        ent_addr = entity_primary_address(ent) if ent else None

        missing = []
        if not ent_addr or not getattr(ent_addr, "pincode", None):
            missing.append("entity.pincode")
        if not ship or not getattr(ship, "pincode", None):
            missing.append("shipto_snapshot.pincode")
        if not ship or not getattr(ship, "state_code", None):
            missing.append("shipto_snapshot.state_code")

        if not ewb:
            missing.append("eway_artifact (create SalesEWayBill row)")
        else:
            if not getattr(ewb, "distance_km", None):
                missing.append("eway.distance_km")
            if not getattr(ewb, "transport_mode", None):
                missing.append("eway.transport_mode")
            # road = 1 (as per your code)
            if getattr(ewb, "transport_mode", None) == 1 and not getattr(ewb, "vehicle_no", None):
                missing.append("eway.vehicle_no (road)")

        if missing:
            return {
                "eligible": False,
                "reason": f"Missing: {', '.join(missing)}",
                "invoice_id": invoice.id,
                "invoice_status": invoice.status,
                "eway": self._ewb_state(ewb),
            }

        return {
            "eligible": True,
            "reason": None,
            "invoice_id": invoice.id,
            "invoice_status": invoice.status,
            "eway": self._ewb_state(ewb),
        }
