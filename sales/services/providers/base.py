from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


# =========================
# Normalized results
# =========================
@dataclass(frozen=True)
class IRNResult:
    ok: bool
    irn: Optional[str] = None
    ack_no: Optional[str] = None
    ack_date: Optional[Any] = None
    signed_invoice: Optional[str] = None
    signed_qr_code: Optional[str] = None

    # If provider also returns EWB details
    ewb_no: Optional[str] = None
    ewb_date: Optional[Any] = None
    ewb_valid_upto: Optional[Any] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class EWayResult:
    ok: bool
    ewb_no: Optional[str] = None
    ewb_date: Optional[Any] = None
    valid_upto: Optional[Any] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


# =========================
# Provider contracts
# =========================
class EInvoiceProvider(Protocol):
    name: str
    def generate_irn(self, *, invoice, payload: Dict[str, Any]) -> IRNResult: ...
    def cancel_irn(self, *, invoice, irn: str, reason_code: str, remarks: str | None = None) -> IRNResult: ...


class EWayProvider(Protocol):
    name: str

    def generate_eway(self, *, invoice_payload: Dict[str, Any], transport_payload: Dict[str, Any]) -> EWayResult:
        ...

    def cancel_eway(self, *, ewb_no: str, reason_code: str, remarks: str | None = None) -> EWayResult:
        ...