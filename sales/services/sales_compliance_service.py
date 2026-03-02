from __future__ import annotations

import json
from typing import Any, Dict, Optional
from sales.services.providers.registry import ProviderRegistry

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from sales.models.sales_core import SalesInvoiceHeader
from sales.models.sales_compliance import (
    SalesEInvoice,
    SalesEWayBill,
    SalesEInvoiceStatus,
    SalesEWayStatus,
)
from sales.models.mastergst_models import SalesMasterGSTCredential, MasterGSTEnvironment
from sales.services.providers.mastergst_client import MasterGSTClient

from sales.services.irp_payload_builder import IRPPayloadBuilder
from sales.services.party_resolvers import seller_from_entity, buyer_from_account
from financial.models import account as AccountModel

from sales.services.eway_payload_builder import (
    EWayInput,
    build_generate_eway_payload,
    build_disp_dtls,
    build_exp_ship_dtls,
)

from sales.services.eway.payload_b2c import build_b2c_direct_payload


MAX_EWAY_ATTEMPTS = 10


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
    def _ensure_invoice_eligible_for_eway(inv: SalesInvoiceHeader) -> None:
        if inv.status not in (inv.Status.CONFIRMED, inv.Status.POSTED):
            raise ValidationError("E-Way allowed only after CONFIRMED/POSTED invoices.")

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
        if self.invoice.status != self.invoice.Status.CONFIRMED:
            raise ValidationError("Invoice must be CONFIRMED before generating IRN.")

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

    @staticmethod
    def _parse_dt(x: Any):
        """
        MasterGST often returns: "01/03/2026 03:44:00 PM" or "2026-03-01 15:44:00"
        We'll try parse_datetime best-effort.
        """
        if not x:
            return None
        s = str(x).strip()

        # If it's in dd/mm/yyyy format, parse_datetime won't parse.
        # We'll keep it as string if parse fails; optionally implement strict parser later.
        dt = parse_datetime(s.replace(" ", "T")) or parse_datetime(s)
        return dt or None

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

    # -------------------------
    # Credential resolver (ONE ONLY)
    # -------------------------

    @staticmethod
    def _mastergst_env_from_settings() -> int:
        # Optional global switch. If missing, default SANDBOX.
        return int(getattr(settings, "SALES_MASTERGST_ENV", MasterGSTEnvironment.SANDBOX))

    @staticmethod
    def _get_mastergst_cred_for_entity(entity) -> SalesMasterGSTCredential:
        env = SalesComplianceService._mastergst_env_from_settings()

        cred = (
            SalesMasterGSTCredential.objects
            .filter(entity=entity, environment=env, is_active=True)
            .order_by("-id")
            .first()
        )
        if not cred:
            raise ValidationError(f"MasterGST credential not configured for this entity (env={env}).")

        missing = []
        if not cred.gstin: missing.append("gstin")
        if not cred.client_id: missing.append("client_id")
        if not cred.client_secret: missing.append("client_secret")
        if not cred.email: missing.append("email")
        if not cred.gst_username: missing.append("gst_username")
        if not cred.gst_password: missing.append("gst_password")

        if missing:
            raise ValidationError(f"MasterGST credential incomplete: {', '.join(missing)}")

        return cred

    # -------------------------
    # IRN
    # -------------------------

    @transaction.atomic
    def generate_irn(self) -> SalesEInvoice:
        self._assert_confirmed_for_irn()

        einv = self._ensure_einvoice_row()
        if einv.status == SalesEInvoiceStatus.GENERATED and einv.irn:
            return einv  # idempotent

        payload = IRPPayloadBuilder(self.invoice).build()
        payload["SellerDtls"] = seller_from_entity(self.invoice.entity)

        buyer = self._buyer_account()
        payload["BuyerDtls"] = buyer_from_account(buyer, pos_state=getattr(self.invoice, "pos_state", None))

        einv.last_request_json = payload
        einv.attempt_count = int(einv.attempt_count or 0) + 1
        einv.last_attempt_at = timezone.now()
        einv.status = SalesEInvoiceStatus.PENDING
        einv.updated_by = self.user
        einv.save()

        # if you use ProviderRegistry, keep it; else call MasterGST provider directly
        provider_name = getattr(settings, "EINVOICE_PROVIDER", "mastergst")
        provider = ProviderRegistry.get_einvoice(provider_name)  # noqa: F821 (if you keep ProviderRegistry)

        try:
            result = provider.generate_irn(invoice=self.invoice, payload=payload)
        except Exception as ex:
            einv.status = SalesEInvoiceStatus.FAILED
            einv.last_error_code = "PROVIDER_EXCEPTION"
            einv.last_error_message = str(ex)
            einv.updated_by = self.user
            einv.save()
            raise

        einv.last_response_json = result.raw
        if not result.ok or not result.irn:
            einv.status = SalesEInvoiceStatus.FAILED
            einv.last_error_code = result.error_code or "IRN_FAILED"
            einv.last_error_message = result.error_message or "IRN generation failed."
            einv.updated_by = self.user
            einv.save()
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

        return einv

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

        default_disp = build_disp_dtls(
            name=getattr(entity, "legalname", None) or getattr(entity, "entityname", None),
            addr1=getattr(entity, "address", None),
            addr2=getattr(entity, "address2", None),
            loc=getattr(getattr(entity, "city", None), "cityname", None) if getattr(entity, "city", None) else None,
            pin=getattr(entity, "pincode", None),
            stcd=SalesComplianceService._stcd(getattr(getattr(entity, "state", None), "statecode", None))
                or SalesComplianceService._stcd(getattr(inv, "seller_state_code", None)),
        )

        ship = getattr(inv, "shipto_snapshot", None)
        default_ship = build_exp_ship_dtls(
            addr1=getattr(ship, "address1", None) if ship else getattr(inv, "bill_to_address1", None),
            addr2=getattr(ship, "address2", None) if ship else getattr(inv, "bill_to_address2", None),
            loc=getattr(ship, "city", None) if ship else getattr(inv, "bill_to_city", None),
            pin=getattr(ship, "pincode", None) if ship else getattr(inv, "bill_to_pincode", None),
            stcd=SalesComplianceService._stcd(getattr(ship, "state_code", None)) if ship else SalesComplianceService._stcd(getattr(inv, "bill_to_state_code", None)),
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
            disp_in = build_disp_dtls(
                name=getattr(entity, "legalname", None) or getattr(entity, "entityname", None),
                addr1=getattr(entity, "address", None),
                addr2=getattr(entity, "address2", None),
                loc=getattr(getattr(entity, "city", None), "cityname", None) if getattr(entity, "city", None) else None,
                pin=getattr(entity, "pincode", None),
                stcd=getattr(getattr(entity, "state", None), "statecode", None) if getattr(entity, "state", None) else getattr(inv, "seller_state_code", None),
            )

        if not ship_in:
            ship = getattr(inv, "shipto_snapshot", None)
            ship_in = build_exp_ship_dtls(
                addr1=getattr(ship, "address1", None) if ship else getattr(inv, "bill_to_address1", None),
                addr2=getattr(ship, "address2", None) if ship else getattr(inv, "bill_to_address2", None),
                loc=getattr(ship, "city", None) if ship else getattr(inv, "bill_to_city", None),
                pin=getattr(ship, "pincode", None) if ship else getattr(inv, "bill_to_pincode", None),
                stcd=getattr(ship, "state_code", None) if ship else getattr(inv, "bill_to_state_code", None),
            )

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
        art.save()

        cred = SalesComplianceService._get_mastergst_cred_for_entity(entity)
        client = MasterGSTClient(cred=cred)

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

            return {
                "status": "SUCCESS",
                "eway": {"ewb_no": art.ewb_no, "ewb_date": art.ewb_date, "valid_upto": art.valid_upto},
                "attempt_count": art.attempt_count,
                "idempotent": False,
                "raw": resp,
            }

        status_desc = str(resp.get("status_desc") or "")
        code, msg = SalesComplianceService._first_error_from_status_desc(status_desc)

        art.status = SalesEWayStatus.FAILED
        art.last_error_code = code or "EWB_FAILED"
        art.last_error_message = msg or "E-Way generation failed."
        art.save()

        return {
            "status": "FAILED",
            "error_code": art.last_error_code,
            "error_message": art.last_error_message,
            "attempt_count": art.attempt_count,
            "idempotent": False,
            "raw": resp,
        }

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
        ewb = getattr(invoice, "eway_artifact", None)
        if not ewb:
            ewb = SalesEWayBill.objects.create(invoice=invoice)

        # ✅ Idempotent success (strong)
        now = timezone.now()
        if ewb.status == SalesEWayStatus.GENERATED and ewb.ewb_no and ewb.valid_upto and ewb.valid_upto > now:
            return {"status": "SUCCESS", "ewb_no": ewb.ewb_no, "valid_upto": ewb.valid_upto, "idempotent": True}

        cred = self._get_mastergst_cred_for_entity(invoice.entity)
        client = MasterGSTClient(cred=cred)

        payload = build_b2c_direct_payload(invoice=invoice, ewb=ewb, entity_gstin=cred.gstin)

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
            return self._eway_fail(data=None, exc=e)

        ewb.last_response_json = mgst_resp

        status_cd = str(mgst_resp.get("status_cd") or "")
        if status_cd == "1":
            data = mgst_resp.get("data") or {}

            ewb.ewb_no = str(data.get("ewayBillNo") or data.get("EwbNo") or "") or None
            ewb.ewb_date = self._parse_dt(data.get("ewayBillDate") or data.get("EwbDt"))
            ewb.valid_upto = self._parse_dt(data.get("validUpto") or data.get("EwbValidTill"))

            ewb.status = SalesEWayStatus.GENERATED
            ewb.last_success_at = timezone.now()
            if user:
                ewb.updated_by = user
            ewb.save()

            return {"status": "SUCCESS", "ewb_no": ewb.ewb_no, "valid_upto": ewb.valid_upto, "raw": mgst_resp, "idempotent": False}

        status_desc = str(mgst_resp.get("status_desc") or "")
        code, msg = self._first_error_from_status_desc(status_desc)

        ewb.status = SalesEWayStatus.FAILED
        ewb.last_error_code = code or "EWB_FAILED"
        ewb.last_error_message = msg or self._extract_mastergst_error(mgst_resp) or "E-Way failed"
        if user:
            ewb.updated_by = user
        ewb.save()

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

        missing = []
        if not ent or not getattr(ent, "pincode", None):
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


