from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


GSTIN_RE = re.compile(r"[^A-Z0-9]")
INVOICE_RE = re.compile(r"[^A-Z0-9]")


def normalize_gstin(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return GSTIN_RE.sub("", raw)


def normalize_invoice_number(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return INVOICE_RE.sub("", raw)


def normalize_doc_type(value: Any) -> str:
    token = str(value or "").strip().upper()
    mapping = {
        "INV": "INV",
        "INVOICE": "INV",
        "BILL": "INV",
        "CN": "CN",
        "CRN": "CN",
        "CREDIT": "CN",
        "CREDIT_NOTE": "CN",
        "DN": "DN",
        "DBN": "DN",
        "DEBIT": "DN",
        "DEBIT_NOTE": "DN",
    }
    return mapping.get(token, token or "INV")


def normalize_return_period(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = raw.replace("/", "-")
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        return raw
    if re.fullmatch(r"\d{2}-\d{4}", raw):
        month, year = raw.split("-")
        return f"{year}-{month}"
    return raw


def parse_date_value(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    raw = str(value).strip().replace(",", "")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def decimal_abs_diff(left: Decimal, right: Decimal) -> Decimal:
    return (left - right).copy_abs().quantize(Decimal("0.01"))
