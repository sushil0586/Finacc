from __future__ import annotations

import re
from typing import Any


ERROR_CODE_PATTERN = re.compile(r"\b(?:AUTH\d{3}|RET\d{5,6}|RT_FIL_\d{2,3}|RTN_FIL_\d{2}|RTN_\d{2}|RTDSC\d{2})\b", re.IGNORECASE)

SESSION_LIMIT_CODES = {"AUTH403"}
API_ACCESS_CODES = {"AUTH002"}
AUTHENTICATION_CODES = {
    "RET11402",
    "RET11407",
    "RET11408",
    "RET11409",
    "AUTH150",
    "AUTH151",
    "RTN_27",
}
DATE_PERIOD_CODES = {
    "AUTH113",
    "AUTH117",
    "AUTH119",
    "RET12590",
    "RTN_02",
    "RET13511",
    "RET191114",
    "RET191120",
    "RET191126",
    "RET191151",
    "RET191158",
    "RET191176",
    "RET191184",
    "RET191185",
    "RET191198",
    "RET191202",
}
ALREADY_FILED_CODES = {
    "AUTH117",
    "RT_FIL_02",
    "RET12521",
    "RTN_11",
    "RTN_17",
    "RET12523",
    "RET191182",
    "RET191183",
}
SIGNATURE_EVC_CODES = {
    "RET13506",
    "RET13507",
    "RET13509",
    "RTDSC04",
    "RTDSC05",
    "RT_FIL_017",
    "RT_FIL_018",
    "RT_FIL_31",
    "RTN_FIL_28",
    "RTN_FIL_29",
    "RTN_FIL_30",
}
DUPLICATE_DOCUMENT_CODES = {
    "RET191111",
    "RET191121",
    "RET191123",
    "RET191133",
    "RET191134",
    "RET191135",
    "RET191190",
}
POS_TAX_CODES = {
    "RET11404",
    "RET191112",
    "RET191122",
    "RET191150",
    "RET191160",
    "RET191178",
    "RET191179",
    "RET191189",
}
COUNTERPARTY_CODES = {
    "RET11410",
    "RET191113",
    "RET191119",
    "RET191125",
    "RET191152",
}
HSN_UQC_RATE_CODES = {
    "RET191117",
    "RET191175",
    "RET191194",
    "RET191195",
}
PAYLOAD_CODES = {
    "RET11400",
    "RET11403",
    "RET11420",
    "AUTH141",
    "AUTH143",
    "RET12505",
    "RET13501",
    "RT_FIL_09",
    "RT_FIL_10",
    "RET191101",
    "RET191103",
    "RET191104",
    "RET191106",
    "RET191107",
    "RET191131",
    "RET191136",
    "RET191139",
    "RET191143",
    "RET191148",
    "RET191172",
    "RET191180",
    "RET191181",
    "RET191188",
    "RET191193",
    "RET191196",
    "RET191199",
    "RET191200",
    "RET191203",
    "RET191204",
}
TRACKING_REFERENCE_CODES = {
    "RET13508",
    "RET191115",
    "RET191124",
    "RET191153",
    "RET191154",
    "RET191157",
    "RET191159",
    "RET191168",
    "RET191170",
    "RET191171",
    "RET191197",
}
TEMPORARY_PROVIDER_CODES = {
    "RET13504",
    "RET13505",
    "RT_FIL_24",
    "RTN_15",
    "RTN_24",
    "RTN_25",
    "RTN_31",
    "RTN_32",
    "RT_FIL_25",
    "RET191138",
    "RET191140",
    "RET191141",
    "RET191164",
    "RET191165",
    "RET191166",
    "RET191191",
    "RET191192",
}


def extract_whitebox_error_code(payload: Any = None, message: str = "") -> str:
    direct = _extract_from_payload(payload)
    if direct:
        return direct
    match = ERROR_CODE_PATTERN.search(str(message or ""))
    return match.group(0).upper() if match else ""


def classify_whitebox_error(*, provider_code: str = "", message: str = "") -> str:
    code = str(provider_code or "").upper()
    lowered = str(message or "").lower()
    if code in SESSION_LIMIT_CODES or "maximum session" in lowered:
        return "session_limit"
    if code in API_ACCESS_CODES or "disabled api access" in lowered or "gsp/asp" in lowered:
        return "api_access_disabled"
    if code in AUTHENTICATION_CODES or "unauthorized" in lowered or "auth token" in lowered:
        return "authentication"
    if code in SIGNATURE_EVC_CODES or "evc" in lowered or "dsc" in lowered or "otp" in lowered:
        return "signature_evc"
    if code in ALREADY_FILED_CODES or "already filed" in lowered or "already submitted" in lowered:
        return "already_filed_or_submitted"
    if code in DUPLICATE_DOCUMENT_CODES or "duplicate invoice" in lowered or "already exist" in lowered:
        return "duplicate_document"
    if code in POS_TAX_CODES or "place of supply" in lowered or "state code" in lowered:
        return "pos_or_tax_mismatch"
    if code in COUNTERPARTY_CODES or "counter party" in lowered or "receiver" in lowered or "gstin is invalid" in lowered:
        return "counterparty_master_data"
    if code in DATE_PERIOD_CODES or "return period" in lowered or "invoice date" in lowered or "note date" in lowered:
        return "date_or_period"
    if code in HSN_UQC_RATE_CODES or "hsn" in lowered or "uqc" in lowered or "rate list" in lowered:
        return "hsn_uqc_rate"
    if code in TRACKING_REFERENCE_CODES or "original" in lowered or "tracked" in lowered:
        return "source_reference"
    if code in TEMPORARY_PROVIDER_CODES or "under processing" in lowered or "try after sometime" in lowered or "timeout" in lowered:
        return "provider_processing"
    if code in PAYLOAD_CODES or "payload" in lowered or "json" in lowered or "checksum" in lowered:
        return "payload_validation"
    if "not configured" in lowered or "missing" in lowered:
        return "configuration"
    if "upstream" in lowered:
        return "provider_unavailable"
    return "provider_rejected"


def whitebox_error_resolution(category: str) -> str:
    resolutions = {
        "session_limit": "A GST portal session is already active for this GST user. Logout from GST portal or WhiteBooks, wait for the provider session to expire, then retry.",
        "api_access_disabled": "Enable API access for this GSTIN and allow the WhiteBooks GSP or ASP on the GST portal before retrying.",
        "authentication": "Verify the GST username, GSTIN, state code, IP address, and active auth session before retrying.",
        "signature_evc": "Request a fresh OTP/EVC, verify PAN and DSC/EVC authorization for the GSTIN, then retry before the code expires.",
        "already_filed_or_submitted": "This return is already filed, submitted, or in progress on GSTN. Check portal status before sending another save/file request.",
        "duplicate_document": "Review invoice/note numbering in the return period. Delete or correct duplicate GSTN documents before resubmitting.",
        "pos_or_tax_mismatch": "Correct place of supply, supplier state, and IGST versus CGST/SGST tax split in the source transaction before preparing again.",
        "counterparty_master_data": "Correct customer/vendor GSTIN, recipient state, e-commerce GSTIN, or counterparty details in master/source data.",
        "date_or_period": "Correct invoice/note date and return period. The document must belong to an allowed GST filing period.",
        "hsn_uqc_rate": "Correct HSN/SAC, UQC, item grouping, or GST rate according to the GSTN accepted master list.",
        "source_reference": "Correct original invoice/note references for amendments, credit notes, debit notes, or advance adjustments.",
        "payload_validation": "Rebuild the filing payload after fixing missing headers, checksum mismatch, JSON structure, or mandatory return data.",
        "provider_processing": "GSTN is processing or temporarily unavailable. Wait and poll/retry instead of repeatedly resubmitting.",
        "configuration": "Verify the backend WhiteBooks credentials, contact email, GST username, GSTIN, state code, and IP address.",
        "provider_unavailable": "WhiteBooks or GSTN returned a temporary upstream error. Retry after a short wait and avoid repeated OTP attempts.",
        "provider_rejected": "Review the provider message, GSTIN, username, state code, email, and return period before retrying.",
        "validation": "Fix the highlighted input and retry.",
    }
    return resolutions.get(category, resolutions["provider_rejected"])


def _extract_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    keys = ("error_cd", "errorCode", "error_code", "code", "err_cd", "errCode")
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value.upper()
    error = payload.get("error")
    if isinstance(error, dict):
        nested = _extract_from_payload(error)
        if nested:
            return nested
    return ""
