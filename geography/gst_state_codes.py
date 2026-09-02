from __future__ import annotations

import re
from typing import Any


INDIA_STATES_GST = [
    ("01", "Jammu and Kashmir"),
    ("02", "Himachal Pradesh"),
    ("03", "Punjab"),
    ("04", "Chandigarh"),
    ("05", "Uttarakhand"),
    ("06", "Haryana"),
    ("07", "Delhi"),
    ("08", "Rajasthan"),
    ("09", "Uttar Pradesh"),
    ("10", "Bihar"),
    ("11", "Sikkim"),
    ("12", "Arunachal Pradesh"),
    ("13", "Nagaland"),
    ("14", "Manipur"),
    ("15", "Mizoram"),
    ("16", "Tripura"),
    ("17", "Meghalaya"),
    ("18", "Assam"),
    ("19", "West Bengal"),
    ("20", "Jharkhand"),
    ("21", "Odisha"),
    ("22", "Chhattisgarh"),
    ("23", "Madhya Pradesh"),
    ("24", "Gujarat"),
    ("26", "Dadra and Nagar Haveli and Daman and Diu"),
    ("27", "Maharashtra"),
    ("28", "Andhra Pradesh"),
    ("29", "Karnataka"),
    ("30", "Goa"),
    ("31", "Lakshadweep"),
    ("32", "Kerala"),
    ("33", "Tamil Nadu"),
    ("34", "Puducherry"),
    ("35", "Andaman and Nicobar Islands"),
    ("36", "Telangana"),
    ("37", "Andhra Pradesh (New)"),
    ("38", "Ladakh"),
    ("97", "Other Territory"),
]

INDIA_STATE_CODE_ALIASES = {
    "AP": "37",
    "AR": "12",
    "AS": "18",
    "BR": "10",
    "CG": "22",
    "CH": "04",
    "DD": "25",
    "DH": "26",
    "DL": "07",
    "GA": "30",
    "GJ": "24",
    "HP": "02",
    "HR": "06",
    "JH": "20",
    "JK": "01",
    "KA": "29",
    "KL": "32",
    "LA": "38",
    "LD": "31",
    "MH": "27",
    "ML": "17",
    "MN": "14",
    "MP": "23",
    "MZ": "15",
    "NL": "13",
    "OD": "21",
    "OR": "21",
    "PB": "03",
    "PY": "34",
    "RJ": "08",
    "SK": "11",
    "TN": "33",
    "TS": "36",
    "TR": "16",
    "UK": "05",
    "UP": "09",
    "UT": "05",
    "WB": "19",
}

STATE_NAME_ALIASES = {
    "orissa": "odisha",
    "pondicherry": "puducherry",
    "nct of delhi": "delhi",
    "delhi ncr": "delhi",
    "andaman and nicobar": "andaman and nicobar islands",
    "andaman nicobar islands": "andaman and nicobar islands",
    "dadra and nagar haveli": "dadra and nagar haveli and daman and diu",
    "daman and diu": "dadra and nagar haveli and daman and diu",
    "jammu and kashmir": "jammu and kashmir",
}


def normalize_state_name_key(value: Any) -> str:
    value = str(value or "").strip().lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return STATE_NAME_ALIASES.get(value, value)


INDIA_STATE_CODES_BY_NAME = {
    normalize_state_name_key(name): code
    for code, name in INDIA_STATES_GST
}


def is_india_country(country: Any) -> bool:
    code = str(getattr(country, "countrycode", "") or "").strip().upper()
    name = normalize_state_name_key(getattr(country, "countryname", "") or "")
    return code in {"IN", "IND", "91"} or name == "india"


def normalize_india_state_code(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.isdigit():
        if not raw.strip("0"):
            return ""
        return raw.zfill(2)[:2]
    alias = INDIA_STATE_CODE_ALIASES.get(raw.upper())
    if alias:
        return alias
    return INDIA_STATE_CODES_BY_NAME.get(normalize_state_name_key(raw), "")


def normalize_state_code_for_country(value: Any, *, country: Any = None, statename: Any = None) -> str:
    raw = str(value or "").strip()
    if is_india_country(country):
        normalized = normalize_india_state_code(raw)
        if normalized:
            return normalized
        normalized = normalize_india_state_code(statename)
        if normalized:
            return normalized

    if not raw:
        return ""
    if raw.isdigit():
        if not raw.strip("0"):
            return ""
        return raw.zfill(2)[:2]
    return raw.upper()[:2]
