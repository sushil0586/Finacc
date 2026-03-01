from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple
from django.db import transaction
from django.utils import timezone

from sales.models import SalesEWayBill, SalesEWayStatus, SalesEWaySource
from sales.integrations.mastergst_eway_client import MasterGSTEWayClient
from sales.services.eway.sales_eway_payload_b2c import build_b2c_direct_eway_payload

def _parse_mastergst_status_desc(status_desc: str) -> Tuple[Optional[str], Optional[str]]:
    """
    MasterGST often returns:
    status_desc: '[{"ErrorCode":"4038","ErrorMessage":"..."}]'
    """
    if not status_desc:
        return None, None
    try:
        arr = json.loads(status_desc)
        if isinstance(arr, list) and arr:
            return str(arr[0].get("ErrorCode") or ""), str(arr[0].get("ErrorMessage") or "")
    except Exception:
        pass
    return None, status_desc

class SalesEWayService:

    @staticmethod
    def _entity_gstin(entity: Any) -> str:
        gstin = getattr(entity, "gstin", None) or getattr(entity, "gstin_no", None)
        if not gstin:
            raise ValueError("Entity GSTIN missing.")
        return gstin

    @staticmethod
    def _get_artifact(inv) -> SalesEWayBill:
        obj, _ = SalesEWayBill.objects.get_or_create(invoice=inv)
        return obj

    @staticmethod
    def _assert_transport_present(art: SalesEWayBill) -> None:
        if not art.distance_km:
            raise ValueError("distance_km missing. Save transport details before generating EWB.")
        if art.transport_mode == 1 and not art.vehicle_no:
            raise ValueError("vehicle_no is required for Road transport (transport_mode=1).")

    @staticmethod
    @transaction.atomic
    def generate_b2c_direct(*, inv: Any, entity: Any, client: MasterGSTEWayClient, user: Any | None = None) -> Dict[str, Any]:
        art = SalesEWayService._get_artifact(inv)

        # already generated
        if art.status == SalesEWayStatus.SUCCESS and art.ewb_no:
            return {
                "status": "SUCCESS",
                "message": "E-Way already generated.",
                "ewb_no": art.ewb_no,
                "valid_upto": art.valid_upto,
            }

        # validate invoice
        if str(getattr(inv, "supply_category", "")).upper() != "B2C":
            raise ValueError("This generate_b2c_direct is only for B2C invoices.")

        SalesEWayService._assert_transport_present(art)

        entity_gstin = SalesEWayService._entity_gstin(entity)

        payload = build_b2c_direct_eway_payload(inv=inv, ewb_artifact=art, entity_gstin=entity_gstin)

        # mark pending + save request snapshot
        art.eway_source = SalesEWaySource.DIRECT
        art.last_request_json = payload
        art.last_error_code = None
        art.last_error_message = None
        art.attempt_count = int(art.attempt_count or 0) + 1
        art.last_attempt_at = timezone.now()
        if user:
            art.updated_by = user
        art.status = SalesEWayStatus.PENDING
        art.save()

        res = client.generate_eway_direct(payload)
        art.last_response_json = res.data

        if res.ok:
            # keys differ in responses; handle common variants
            data = res.data.get("data") or res.data

            ewb_no = data.get("ewayBillNo") or data.get("EwbNo") or data.get("ewbNo")
            valid_upto = data.get("validUpto") or data.get("ValidUpTo") or data.get("valid_upto")

            art.ewb_no = str(ewb_no) if ewb_no else None
            art.status = SalesEWayStatus.SUCCESS
            art.last_success_at = timezone.now()
            if user:
                art.updated_by = user
            art.save()

            return {
                "status": "SUCCESS",
                "ewb_no": art.ewb_no,
                "raw": res.data,
            }

        # failure path
        status_desc = str(res.data.get("status_desc") or res.data.get("error_message") or res.error_message or "")
        code, msg = _parse_mastergst_status_desc(status_desc)

        art.status = SalesEWayStatus.FAILED
        art.last_error_code = code or res.error_code or "EWB_FAILED"
        art.last_error_message = msg or res.error_message or "E-Way generation failed"
        if user:
            art.updated_by = user
        art.save()

        return {
            "status": "FAILED",
            "error_code": art.last_error_code,
            "error_message": art.last_error_message,
            "attempt_count": art.attempt_count,
            "raw": res.data,
        }