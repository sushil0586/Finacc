from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from reports.gstr1.services.table_views import Gstr1TableViewService


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


class Gstr1GstnJsonExportService:
    """
    Filing-prep JSON payload generator.
    Keeps table-wise mapping explicit and deterministic from current GSTR-1 view tables.
    """

    def build(self, *, scope, base_queryset) -> dict:
        table_service = Gstr1TableViewService(scope=scope, base_queryset=base_queryset)
        table_codes = [t.code for t in Gstr1TableViewService.table_definitions()]
        table_payloads = {code: table_service.build(code) for code in table_codes}

        table11_groups = table_payloads.get("TABLE_11", {}).get("groups", {})
        from_date = getattr(scope, "from_date", None)
        to_date = getattr(scope, "to_date", None)
        ret_period = ""
        if from_date:
            ret_period = from_date.strftime("%m%Y")

        payload = {
            "schema_version": "finacc.gstr1.filing_prep.v1",
            "contracts": {
                "reverse_charge": {
                    "version": "gstr1.rcm.v1",
                    "source": "table_rows.rcm_contract",
                }
            },
            "ret_period": ret_period,
            "scope": {
                "entity": getattr(scope, "entity_id", None),
                "entityfinid": getattr(scope, "entityfinid_id", None),
                "subentity": getattr(scope, "subentity_id", None),
                "from_date": from_date,
                "to_date": to_date,
            },
            "tables": {
                "1_2_3": table_payloads.get("TAXPAYER_1_3", {}).get("rows", []),
                "4": table_payloads.get("TABLE_4", {}).get("rows", []),
                "5": table_payloads.get("TABLE_5", {}).get("rows", []),
                "6": table_payloads.get("TABLE_6", {}).get("rows", []),
                "7": table_payloads.get("TABLE_7", {}).get("rows", []),
                "8": table_payloads.get("TABLE_8", {}).get("rows", []),
                "9": table_payloads.get("TABLE_9", {}).get("rows", []),
                "10": table_payloads.get("TABLE_10", {}).get("rows", []),
                "11": table_payloads.get("TABLE_11", {}).get("rows", []),
                "11A": table11_groups.get("11A", {}).get("rows", []),
                "11B": table11_groups.get("11B", {}).get("rows", []),
                "12": table_payloads.get("TABLE_12", {}).get("rows", []),
                "13": table_payloads.get("TABLE_13", {}).get("rows", []),
                "14": table_payloads.get("TABLE_14", {}).get("rows", []),
                "14A": table_payloads.get("TABLE_14A", {}).get("rows", []),
                "15": table_payloads.get("TABLE_15", {}).get("rows", []),
                "15A": table_payloads.get("TABLE_15A", {}).get("rows", []),
            },
            "coverage": {
                code: table_payloads.get(code, {}).get("coverage", {})
                for code in table_codes
            },
        }
        return _json_safe(payload)
