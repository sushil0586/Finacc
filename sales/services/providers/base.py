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
    error_reason: Optional[str] = None
    error_resolution: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class EWayResult:
    ok: bool
    ewb_no: Optional[str] = None
    ewb_date: Optional[Any] = None
    valid_upto: Optional[Any] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None
    error_reason: Optional[str] = None
    error_resolution: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class GSTNDetailsResult:
    ok: bool
    gstin: Optional[str] = None
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    status: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None
    error_reason: Optional[str] = None
    error_resolution: Optional[str] = None


@dataclass(frozen=True)
class QRCodeResult:
    ok: bool
    qr_code: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None
    error_reason: Optional[str] = None
    error_resolution: Optional[str] = None


@dataclass(frozen=True)
class LookupResult:
    ok: bool
    data: Optional[Any] = None
    raw: Optional[Dict[str, Any]] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None
    error_reason: Optional[str] = None
    error_resolution: Optional[str] = None


# =========================
# Provider contracts
# =========================
class EInvoiceProvider(Protocol):
    name: str
    def generate_irn(self, *, invoice, payload: Dict[str, Any]) -> IRNResult: ...
    def cancel_irn(self, *, invoice, irn: str, reason_code: str, remarks: str | None = None) -> IRNResult: ...
    def get_irn_details(self, *, invoice, irn: str, supplier_gstin: str | None = None) -> IRNResult: ...
    def get_irn_details_by_doc(self, *, invoice, doc_type: str, doc_number: str, doc_date: str) -> IRNResult: ...
    def get_gstn_details(self, *, invoice, gstin: str) -> GSTNDetailsResult: ...
    def sync_gstin_from_cp(self, *, invoice, gstin: str) -> GSTNDetailsResult: ...
    def get_b2c_qrcode(self, *, invoice, payload: Dict[str, Any]) -> QRCodeResult: ...
    def get_eway_details_by_irn(self, *, invoice, irn: str, supplier_gstin: str | None = None) -> EWayResult: ...


class EWayProvider(Protocol):
    name: str

    def generate_eway(self, *, invoice_payload: Dict[str, Any], transport_payload: Dict[str, Any]) -> EWayResult:
        ...

    def get_eway_details(self, *, invoice, ewb_no: str) -> EWayResult:
        ...

    def get_transporter_details(self, *, invoice, transporter_id: str) -> LookupResult:
        ...

    def get_gstin_details(self, *, invoice, gstin: str) -> LookupResult:
        ...

    def get_hsn_details(self, *, invoice, hsn_code: str) -> LookupResult:
        ...

    def get_error_list(self, *, invoice) -> LookupResult:
        ...

    def reject_eway(self, *, invoice, ewb_no: str) -> LookupResult:
        ...

    def get_trip_sheet(self, *, invoice, trip_sheet_no: str) -> LookupResult:
        ...

    def get_eway_by_document(self, *, invoice, doc_type: str, doc_no: str) -> LookupResult:
        ...

    def get_eway_bills_for_transporter(self, *, invoice, date: str) -> LookupResult:
        ...

    def get_eway_bill_report_by_transporter_assigned_date(self, *, invoice, date: str, state_code: str) -> LookupResult:
        ...

    def get_eway_bills_by_date(self, *, invoice, date: str) -> LookupResult:
        ...

    def get_eway_bills_rejected_by_others(self, *, invoice, date: str) -> LookupResult:
        ...

    def get_eway_bills_for_transporter_by_gstin(self, *, invoice, gen_gstin: str, date: str) -> LookupResult:
        ...

    def get_eway_bills_for_transporter_by_state(self, *, invoice, state_code: str, date: str) -> LookupResult:
        ...

    def get_eway_bills_of_other_party(self, *, invoice, date: str) -> LookupResult:
        ...

    def generate_consolidated_eway(self, *, invoice, payload: Dict[str, Any]) -> LookupResult:
        ...

    def regenerate_trip_sheet(self, *, invoice, payload: Dict[str, Any]) -> LookupResult:
        ...

    def initiate_multi_vehicle(self, *, invoice, payload: Dict[str, Any]) -> LookupResult:
        ...

    def add_multi_vehicle(self, *, invoice, payload: Dict[str, Any]) -> LookupResult:
        ...

    def update_multi_vehicle(self, *, invoice, payload: Dict[str, Any]) -> LookupResult:
        ...

    def cancel_eway(self, *, ewb_no: str, reason_code: str, remarks: str | None = None) -> EWayResult:
        ...
