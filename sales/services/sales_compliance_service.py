from __future__ import annotations

from django.conf import settings
from django.db import transaction
from typing import Any, Dict, Optional
from sales.models.sales_compliance import NICEnvironment  # adjust import path

import inspect
from sales.services.providers.mastergst_client import MasterGSTClient
from sales.models.mastergst_models import SalesMasterGSTCredential
from django.core.exceptions import ObjectDoesNotExist

from django.utils import timezone
from rest_framework.exceptions import ValidationError
from sales.models.sales_core import SalesInvoiceHeader
from sales.services.eway_payload_builder import (
    EWayInput,
    build_generate_eway_payload,
    build_disp_dtls,
    build_exp_ship_dtls,
)


from sales.models.sales_compliance import (
    SalesEInvoice, SalesEWayBill,
    SalesEInvoiceStatus, SalesEWayStatus,
)
from sales.services.providers.registry import ProviderRegistry
from sales.services.party_resolvers import seller_from_entity, buyer_from_account
from sales.services.irp_payload_builder import IRPPayloadBuilder
from financial.models import account as AccountModel
MAX_EWAY_ATTEMPTS = 10


class SalesComplianceService:
    SUCCESS_STATUS_DB = 2  # ✅ DB truth in your system (confirmed)


    def __init__(self, *, invoice, user=None):
        self.invoice = invoice
        self.user = user

    def _buyer_account(self) -> AccountModel:
        inv = self.invoice
        # common FK names; update if yours differs
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
            defaults={"created_by": self.user, "updated_by": self.user, "status": SalesEInvoiceStatus.PENDING},
        )
        return obj

    def _ensure_eway_row(self) -> SalesEWayBill:
        obj, _ = SalesEWayBill.objects.get_or_create(
            invoice=self.invoice,
            defaults={"created_by": self.user, "updated_by": self.user, "status": SalesEWayStatus.PENDING},
        )
        return obj

    def _assert_confirmed(self):
        if self.invoice.status != self.invoice.Status.CONFIRMED:
            raise ValidationError("Invoice must be CONFIRMED before generating IRN/EWB.")

    @transaction.atomic
    def ensure_rows(self) -> dict:
        # For now: create rows always; later we add rules engine
        einv = self._ensure_einvoice_row()
        ewb = self._ensure_eway_row()
        return {"einvoice_id": einv.id, "eway_id": ewb.id}

    @transaction.atomic
    def generate_irn(self) -> SalesEInvoice:
        self._assert_confirmed()

        einv = self._ensure_einvoice_row()
        if einv.status == SalesEInvoiceStatus.GENERATED and einv.irn:
            return einv  # idempotent

        payload = IRPPayloadBuilder(self.invoice).build()

        # inject Seller/Buyer from your required sources:
        payload["SellerDtls"] = seller_from_entity(self.invoice.entity)
        buyer = self._buyer_account()
        payload["BuyerDtls"] = buyer_from_account(buyer, pos_state=getattr(self.invoice, "pos_state", None))

        einv.last_request_json = payload
        einv.attempt_count = (einv.attempt_count or 0) + 1
        einv.last_attempt_at = timezone.now()
        einv.status = SalesEInvoiceStatus.PENDING
        einv.updated_by = self.user
        einv.save()

        provider_name = getattr(settings, "EINVOICE_PROVIDER", "mastergst")
        provider = ProviderRegistry.get_einvoice(provider_name)

        try:
            result = provider.generate_irn(invoice=self.invoice, payload=payload)
        except Exception as ex:
            einv.status = SalesEInvoiceStatus.FAILED
            einv.last_error_code = "PROVIDER_EXCEPTION"
            einv.last_error_message = str(ex)
            einv.save(update_fields=["status", "last_error_code", "last_error_message", "updated_at"])
            raise

        einv.last_response_json = result.raw
        if not result.ok or not result.irn:
            einv.status = SalesEInvoiceStatus.FAILED
            einv.last_error_code = result.error_code or "IRN_FAILED"
            einv.last_error_message = result.error_message or "IRN generation failed."
            einv.save()
            raise ValidationError({
                "message": einv.last_error_message,
                "code": einv.last_error_code,
                "raw": einv.last_response_json,   # ✅ so you see MasterGST exact reason
            })

        einv.irn = result.irn
        einv.ack_no = result.ack_no
        einv.ack_date = result.ack_date
        einv.signed_invoice = result.signed_invoice
        einv.signed_qr_code = result.signed_qr_code

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
    def _ensure_invoice_eligible_for_eway(inv) -> None:
        if inv.status not in (inv.Status.CONFIRMED, inv.Status.POSTED):
            raise ValueError("E-Way allowed only after CONFIRMED/POSTED invoices.")

    @staticmethod
    def _stcd(value: Any) -> Optional[str]:
        """
        Normalize state code to 2-digit string.
        Returns None for empty/"00"/invalid values.
        """
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        if s in ("0", "00"):
            return None
        if s.isdigit() and len(s) == 1:
            s = "0" + s
        return s

    @staticmethod
    def _invoice_number(inv) -> Optional[str]:
        return getattr(inv, "sales_number", None) or getattr(inv, "invoice_number", None)

    # -------------------------
    # Final IRN getter
    # -------------------------
    @staticmethod
    def _get_irn(inv) -> str:
        """
        Source of truth:
          inv.einvoice_artifact.irn

        Status rule:
          - Prefer enum (SalesEInvoiceStatus.SUCCESS) if it matches DB
          - Safe fallback to DB success value (2)
        """
        einv = getattr(inv, "einvoice_artifact", None)
        if not einv:
            raise ValueError("E-Invoice artifact not found for invoice.")

        status_val = getattr(einv, "status", None)

        # Prefer enum if available, but don't trust it blindly (you faced mismatch earlier)
        enum_success_val = None
        try:
            enum_success_val = int(SalesEInvoiceStatus.GENERATED)
        except Exception:
            enum_success_val = None

        is_success = False
        if enum_success_val is not None:
            is_success = (status_val == enum_success_val)

        # fallback to DB truth
        if not is_success:
            is_success = (status_val == SalesComplianceService.SUCCESS_STATUS_DB)

        if not is_success:
            # try label for clarity
            try:
                label = SalesEInvoiceStatus(status_val).label
            except Exception:
                label = str(status_val)
            raise ValueError(f"E-Invoice not SUCCESS (status={status_val}, label={label}).")

        irn = getattr(einv, "irn", None) or ""
        if not irn:
            raise ValueError("IRN missing in e-invoice artifact.")

        return irn

    # -------------------------
    # Final Prefill
    # -------------------------
    @staticmethod
    def build_eway_prefill(inv, entity: Any) -> Dict[str, Any]:
        """
        Prefill:
          - DispDtls from Entity (seller/dispatch)
          - ExpShipDtls from ShipTo snapshot if present else bill_to fields
          - Includes last saved transport draft + last EWB status if eway_artifact exists
        """
        SalesComplianceService._ensure_invoice_eligible_for_eway(inv)

        # Base response fields (keep consistent for UI)
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

        # -------------------------
        # DispDtls (seller/dispatch) -> Entity
        # -------------------------
        default_disp = build_disp_dtls(
            name=getattr(entity, "legalname", None) or getattr(entity, "entityname", None),
            addr1=getattr(entity, "address", None),
            addr2=getattr(entity, "address2", None),
            loc=getattr(getattr(entity, "city", None), "cityname", None)
                if getattr(entity, "city", None) else None,
            pin=getattr(entity, "pincode", None),
            stcd=SalesComplianceService._stcd(
                getattr(getattr(entity, "state", None), "statecode", None)
            ) or SalesComplianceService._stcd(getattr(inv, "seller_state_code", None)),
        )

        # -------------------------
        # ExpShipDtls (ship) -> shipto_snapshot else bill_to
        # -------------------------
        ship = getattr(inv, "shipto_snapshot", None)
        if ship:
            default_ship = build_exp_ship_dtls(
                addr1=getattr(ship, "address1", None),
                addr2=getattr(ship, "address2", None),
                loc=getattr(ship, "city", None),
                pin=getattr(ship, "pincode", None),
                stcd=SalesComplianceService._stcd(getattr(ship, "state_code", None)),
            )
        else:
            default_ship = build_exp_ship_dtls(
                addr1=getattr(inv, "bill_to_address1", None),
                addr2=getattr(inv, "bill_to_address2", None),
                loc=getattr(inv, "bill_to_city", None),
                pin=getattr(inv, "bill_to_pincode", None),
                stcd=SalesComplianceService._stcd(getattr(inv, "bill_to_state_code", None))
                    or SalesComplianceService._stcd(getattr(inv, "place_of_supply_state_code", None)),
            )

        # -------------------------
        # Existing artifact draft (EWayBill artifact)
        # -------------------------
        art = getattr(inv, "eway_artifact", None)  # must match SalesEWayBill related_name
        last_transport = None
        last_status = None

        if art:
            last_status = {
                "status": getattr(art, "status", None),
                "ewb_no": getattr(art, "ewb_no", None),
                "ewb_date": getattr(art, "ewb_date", None),
                "valid_upto": getattr(art, "valid_upto", None),
                "last_error_code": getattr(art, "last_error_code", None),
                "last_error_message": getattr(art, "last_error_message", None),
            }

            has_any_transport = any([
                getattr(art, "transporter_id", None),
                getattr(art, "transporter_name", None),
                getattr(art, "transport_mode", None),
                getattr(art, "distance_km", None),
                getattr(art, "vehicle_no", None),
                getattr(art, "vehicle_type", None),
                getattr(art, "doc_no", None),
                getattr(art, "doc_date", None),
                getattr(art, "disp_dtls_json", None),
                getattr(art, "exp_ship_dtls_json", None),
            ])

            if has_any_transport:
                last_transport = {
                    "transporter_id": getattr(art, "transporter_id", None),
                    "transporter_name": getattr(art, "transporter_name", None),
                    "transport_mode": getattr(art, "transport_mode", None),
                    "distance_km": getattr(art, "distance_km", None),
                    "vehicle_no": getattr(art, "vehicle_no", None),
                    "vehicle_type": getattr(art, "vehicle_type", None),
                    "doc_no": getattr(art, "doc_no", None),
                    "doc_date": getattr(art, "doc_date", None),
                    "disp_dtls_json": getattr(art, "disp_dtls_json", None),
                    "exp_ship_dtls_json": getattr(art, "exp_ship_dtls_json", None),
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

    @staticmethod
    @transaction.atomic
    def generate_eway(inv: SalesInvoiceHeader, entity, req: Dict[str, Any], created_by=None) -> Dict[str, Any]:
        """
        End-to-end EWB generation using MasterGST.
        Implements:
        - Eligibility check
        - Idempotency (Policy A)
        - Retry guard
        - Snapshot persistence
        """

        # ---------------------------------------
        # 1️⃣ Eligibility
        # ---------------------------------------
        SalesComplianceService._ensure_invoice_eligible_for_eway(inv)
        irn = SalesComplianceService._get_irn(inv)

        # Lock artifact row
        art, _ = SalesEWayBill.objects.select_for_update().get_or_create(invoice=inv)

        # ---------------------------------------
        # 2️⃣ Idempotency (Policy A)
        # ---------------------------------------
        if art.status == SalesEWayStatus.GENERATED and art.ewb_no:
            return {
                "status": "SUCCESS",
                "eway": {
                    "ewb_no": art.ewb_no,
                    "ewb_date": art.ewb_date,
                    "valid_upto": art.valid_upto,
                },
                "attempt_count": art.attempt_count,
                "idempotent": True,
                "raw": art.last_response_json,
            }

        # ---------------------------------------
        # 3️⃣ Retry Guard
        # ---------------------------------------
        if art.attempt_count >= MAX_EWAY_ATTEMPTS:
            raise ValidationError("Max retry limit reached. Contact admin.")

        # ---------------------------------------
        # 4️⃣ Transport Data Resolution
        # ---------------------------------------
        disp_in = req.get("disp_dtls") or art.disp_dtls_json
        ship_in = req.get("exp_ship_dtls") or art.exp_ship_dtls_json

        if not disp_in:
            disp_in = build_disp_dtls(
                name=getattr(entity, "legalname", None) or getattr(entity, "entityname", None),
                addr1=getattr(entity, "address", None),
                addr2=getattr(entity, "address2", None),
                loc=getattr(getattr(entity, "city", None), "cityname", None) if getattr(entity, "city", None) else None,
                pin=getattr(entity, "pincode", None),
                stcd=getattr(getattr(entity, "state", None), "statecode", None)
                    if getattr(entity, "state", None) else inv.seller_state_code,
            )

        if not ship_in:
            ship = getattr(inv, "shipto_snapshot", None)
            if ship:
                ship_in = build_exp_ship_dtls(
                    ship.address1,
                    ship.address2,
                    ship.city,
                    ship.pincode,
                    ship.state_code,
                )
            else:
                ship_in = build_exp_ship_dtls(
                    inv.bill_to_address1,
                    inv.bill_to_address2,
                    inv.bill_to_city,
                    inv.bill_to_pincode,
                    inv.bill_to_state_code,
                )

        # ---------------------------------------
        # 5️⃣ Build Payload
        # ---------------------------------------
        eway_input = EWayInput(
            distance_km=int(req["distance_km"]),
            trans_mode=str(req["trans_mode"]),
            transporter_id=str(req["transporter_id"]),
            transporter_name=str(req["transporter_name"]),
            trans_doc_no=str(req["trans_doc_no"]),
            trans_doc_date=req["trans_doc_date"],
            vehicle_no=req.get("vehicle_no"),
            vehicle_type=req.get("vehicle_type"),
            disp_dtls=disp_in,
            exp_ship_dtls=ship_in,
        )

        payload = build_generate_eway_payload(irn=irn, x=eway_input)

        # ---------------------------------------
        # 6️⃣ Persist Attempt Snapshot
        # ---------------------------------------
        art.attempt_count = (art.attempt_count or 0) + 1
        art.last_attempt_at = timezone.now()

        art.distance_km = eway_input.distance_km
        art.transport_mode = int(eway_input.trans_mode) if str(eway_input.trans_mode).isdigit() else None
        art.transporter_id = eway_input.transporter_id
        art.transporter_name = eway_input.transporter_name
        art.doc_no = eway_input.trans_doc_no
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

        # ---------------------------------------
        # 7️⃣ Call Provider
        # ---------------------------------------
        client = MasterGSTClient(
            cred=SalesComplianceService._get_mastergst_cred_for_entity(entity)
        )

        resp = client.generate_ewaybill(payload)
        art.last_response_json = resp

        # ---------------------------------------
        # 8️⃣ Parse Response
        # ---------------------------------------
        status_cd = str(resp.get("status_cd") or "")

        if status_cd == "1":
            data = resp.get("data") or {}

            art.status = SalesEWayStatus.GENERATED
            art.ewb_no = str(data.get("EwbNo") or "")
            art.ewb_date = SalesComplianceService._parse_dt(data.get("EwbDt"))
            art.valid_upto = SalesComplianceService._parse_dt(data.get("EwbValidTill"))
            art.last_success_at = timezone.now()
            art.last_error_code = None
            art.last_error_message = None
            art.save()

            return {
                "status": "SUCCESS",
                "eway": {
                    "ewb_no": art.ewb_no,
                    "ewb_date": art.ewb_date,
                    "valid_upto": art.valid_upto,
                },
                "attempt_count": art.attempt_count,
                "idempotent": False,
                "raw": resp,
            }

        # ---------------------------------------
        # 9️⃣ Failure Handling
        # ---------------------------------------
        art.status = SalesEWayStatus.FAILED
        art.last_error_code = SalesComplianceService._extract_error_code(resp)
        art.last_error_message = SalesComplianceService._extract_error_message(resp)
        art.save()

        return {
            "status": "FAILED",
            "error_code": art.last_error_code,
            "error_message": art.last_error_message,
            "attempt_count": art.attempt_count,
            "idempotent": False,
            "raw": resp,
        }

    # ---- helpers you likely already have patterns for ----
    @staticmethod
    def _parse_dt(x) -> Optional[Any]:
        # MasterGST returns "YYYY-MM-DD HH:MM:SS"
        from django.utils.dateparse import parse_datetime
        if not x:
            return None
        s = str(x).strip()
        return parse_datetime(s.replace(" ", "T")) or parse_datetime(s)

    @staticmethod
    def _extract_error_code(resp: Dict[str, Any]) -> Optional[str]:
        desc = resp.get("status_desc")
        if not desc:
            return None
        # Could be JSON list string or plain text
        s = str(desc)
        # try common pattern ErrorCode
        if "ErrorCode" in s:
            return "EWB_VALIDATION"
        return None

    @staticmethod
    def _extract_error_message(resp: Dict[str, Any]) -> str:
        return str(resp.get("status_desc") or "E-Way generation failed.")

    @staticmethod
    def _get_mastergst_cred_for_entity(entity):
        # You already have this resolver in your system; keep it here as placeholder.
        # return SalesMasterGSTCredential.objects.get(entity=entity, is_active=True)
        raise NotImplementedError("Implement credential resolver for entity.")
    
    @staticmethod
    def _get_mastergst_cred_for_entity(entity) -> SalesMasterGSTCredential:
        """
        Entity-wise credential resolver.
        Assumes SalesMasterGSTCredential has FK to Entity as `entity`.
        If you also scope by gstin, you can add that filter too.
        """
        try:
            cred = (
                SalesMasterGSTCredential.objects
                .filter(entity=entity)
                .order_by("-id")
                .first()
            )
        except Exception:
            cred = None

        if not cred:
            raise ValueError("MasterGST credential not configured for this entity.")

        # optional strict checks
        missing = []
        if not cred.client_id: missing.append("client_id")
        if not cred.client_secret: missing.append("client_secret")
        if not cred.gst_username: missing.append("gst_username")
        if not cred.gst_password: missing.append("gst_password")
        if not cred.gstin: missing.append("gstin")
        if not cred.email: missing.append("email")

        if missing:
            raise ValueError(f"MasterGST credential incomplete: {', '.join(missing)}")

        return cred
    
    @staticmethod
    def _mastergst_env():
            # setting can be 1/2 or missing
        return int(getattr(settings, "SALES_MASTERGST_ENV", NICEnvironment.SANDBOX))

    @staticmethod
    def _get_mastergst_cred_for_entity(entity) -> SalesMasterGSTCredential:
        env = SalesComplianceService._mastergst_env()

        cred = (
            SalesMasterGSTCredential.objects
            .filter(entity=entity, environment=env, is_active=True)
            .order_by("-id")
            .first()
        )
        if not cred:
            raise ValueError(f"MasterGST credential not configured for this entity (env={env}).")

        missing = []
        if not cred.gstin: missing.append("gstin")
        if not cred.client_id: missing.append("client_id")
        if not cred.client_secret: missing.append("client_secret")
        if not cred.email: missing.append("email")
        if not cred.gst_username: missing.append("gst_username")
        if not cred.gst_password: missing.append("gst_password")

        if missing:
            raise ValueError(f"MasterGST credential incomplete: {', '.join(missing)}")

        return cred

    def eway_prefill(self, invoice):
        einv = getattr(invoice, "einvoice_artifact", None)
        ewb  = getattr(invoice, "ewaybill_artifact", None)

        irn = None
        if einv and einv.irn and einv.status == SalesEInvoiceStatus.GENERATED:
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