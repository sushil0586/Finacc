from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    endpoints: Mapping[str, str]
    einvoice_auth_token_keys: tuple[str, ...]
    eway_auth_token_header_keys: tuple[str, ...]
    invalid_token_markers: tuple[str, ...]

    def endpoint_path(self, key: str) -> str:
        if key not in self.endpoints:
            raise KeyError(f"Endpoint '{key}' is not defined for provider '{self.name}'.")
        return self.endpoints[key]


_SHARED_ENDPOINTS = {
    "einvoice_auth": "/einvoice/authenticate",
    "einvoice_generate": "/einvoice/type/GENERATE/version/V1_03",
    "einvoice_cancel": "/einvoice/type/CANCEL/version/V1_03",
    "einvoice_get_irn": "/einvoice/type/GETIRN/version/V1_03",
    "einvoice_get_irn_by_doc_details": "/einvoice/type/GETIRNBYDOCDETAILS/version/V1_03",
    "einvoice_get_gstn_details": "/einvoice/type/GSTNDETAILS/version/V1_03",
    "einvoice_sync_gstin_from_cp": "/einvoice/type/SYNC_GSTIN_FROMCP/version/V1_03",
    "einvoice_b2c_qrcode": "/einvoice/qrcode",
    "einvoice_get_eway_by_irn": "/einvoice/type/GETEWAYBILLIRN/version/V1_03",
    "einvoice_generate_ewaybill": "/einvoice/type/GENERATE_EWAYBILL/version/V1_03",
    "eway_auth": "/ewaybillapi/v1.03/authenticate",
    "eway_generate_direct": "/ewaybillapi/v1.03/ewayapi/genewaybill",
    "eway_get_details": "/ewaybillapi/v1.03/ewayapi/getewaybill",
    "eway_get_transporter_details": "/ewaybillapi/v1.03/ewayapi/gettransporterdetails",
    "eway_get_gstin_details": "/ewaybillapi/v1.03/ewayapi/getgstindetails",
    "eway_get_hsn_details": "/ewaybillapi/v1.03/ewayapi/gethsndetailsbyhsncode",
    "eway_get_error_list": "/ewaybillapi/v1.03/ewayapi/geterrorlist",
    "eway_reject": "/ewaybillapi/v1.03/ewayapi/rejewb",
    "eway_get_trip_sheet": "/ewaybillapi/v1.03/ewayapi/gettripsheet",
    "eway_get_by_document": "/ewaybillapi/v1.03/ewayapi/getewaybillgeneratedbyconsigner",
    "eway_get_bills_for_transporter": "/ewaybillapi/v1.03/ewayapi/getewaybillsfortransporter",
    "eway_get_bill_report_by_transporter_assigned_date": "/ewaybillapi/v1.03/ewayapi/getewaybillreportbytransporterassigneddate",
    "eway_get_bills_by_date": "/ewaybillapi/v1.03/ewayapi/getewaybillsbydate",
    "eway_get_bills_rejected_by_others": "/ewaybillapi/v1.03/ewayapi/getewaybillsrejectedbyothers",
    "eway_get_bills_for_transporter_by_gstin": "/ewaybillapi/v1.03/ewayapi/getewaybillsfortransporterbygstin",
    "eway_get_bills_for_transporter_by_state": "/ewaybillapi/v1.03/ewayapi/getewaybillsfortransporterbystate",
    "eway_get_bills_of_other_party": "/ewaybillapi/v1.03/ewayapi/getewaybillsofotherparty",
    "eway_generate_consolidated": "/ewaybillapi/v1.03/ewayapi/gencewb",
    "eway_regenerate_trip_sheet": "/ewaybillapi/v1.03/ewayapi/regentripsheet",
    "eway_initiate_multi_vehicle": "/ewaybillapi/v1.03/ewayapi/initmulti",
    "eway_add_multi_vehicle": "/ewaybillapi/v1.03/ewayapi/addmulti",
    "eway_update_multi_vehicle": "/ewaybillapi/v1.03/ewayapi/updtmulti",
    "eway_cancel": "/ewaybillapi/v1.03/ewayapi/canewb",
    "eway_update_vehicle": "/ewaybillapi/v1.03/ewayapi/vehewb",
    "eway_update_vehicle_fallback": "/ewaybillapi/v1.03/ewayapi/updvehicle",
    "eway_update_transporter": "/ewaybillapi/v1.03/ewayapi/updatetransporter",
    "eway_extend_validity": "/ewaybillapi/v1.03/ewayapi/extendvalidity",
}


_SPECS = {
    "mastergst": ProviderSpec(
        name="mastergst",
        endpoints=_SHARED_ENDPOINTS,
        einvoice_auth_token_keys=("AuthToken", "auth_token", "token", "Token"),
        eway_auth_token_header_keys=("authtoken", "AuthToken", "Auth-Token", "auth-token", "authorization", "Authorization"),
        invalid_token_markers=("1005",),
    ),
    "whitebooks": ProviderSpec(
        name="whitebooks",
        endpoints=_SHARED_ENDPOINTS,
        einvoice_auth_token_keys=("AuthToken", "auth_token", "token", "Token"),
        eway_auth_token_header_keys=("authtoken", "AuthToken", "Auth-Token", "auth-token", "authorization", "Authorization"),
        invalid_token_markers=("1005",),
    ),
}


def get_provider_spec(provider_name: str) -> ProviderSpec:
    key = (provider_name or "mastergst").strip().lower()
    return _SPECS.get(key, _SPECS["mastergst"])
