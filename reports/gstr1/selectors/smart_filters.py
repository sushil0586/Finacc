from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from sales.models import SalesInvoiceHeader


@dataclass(frozen=True)
class Gstr1SmartFilters:
    search: str | None = None
    min_taxable_value: Decimal | None = None
    max_taxable_value: Decimal | None = None
    min_gst_rate: Decimal | None = None
    pos: str | None = None
    doc_type_values: tuple[int, ...] = ()
    gstin_only: bool = False
    warning_severity: str | None = None
    taxability: int | None = None
    tax_regime: int | None = None
    supply_category: int | None = None
    status: int | None = None

    @property
    def has_filters(self) -> bool:
        return any(
            [
                self.search,
                self.min_taxable_value is not None,
                self.max_taxable_value is not None,
                self.min_gst_rate is not None,
                self.pos,
                bool(self.doc_type_values),
                self.gstin_only,
                self.warning_severity,
                self.taxability is not None,
                self.tax_regime is not None,
                self.supply_category is not None,
                self.status is not None,
            ]
        )


def parse_smart_filters(params) -> Gstr1SmartFilters:
    search = _strip_or_none(params.get("search"))
    min_taxable_value = _parse_decimal(params.get("min_taxable_value"), "min_taxable_value")
    max_taxable_value = _parse_decimal(params.get("max_taxable_value"), "max_taxable_value")
    min_gst_rate = _parse_decimal(params.get("min_gst_rate"), "min_gst_rate")
    pos = _strip_or_none(params.get("pos"))
    gstin_only = _parse_bool(params.get("gstin_only"), default=False)
    warning_severity = _normalize_severity(params.get("warning_severity"))
    taxability = _parse_int(params.get("taxability"), "taxability", required=False)
    tax_regime = _parse_int(params.get("tax_regime"), "tax_regime", required=False)
    supply_category = _parse_int(params.get("supply_category"), "supply_category", required=False)
    status = _parse_int(params.get("status"), "status", required=False)
    doc_type_values = _parse_doc_type_values(params.get("doc_type"))

    if (
        min_taxable_value is not None
        and max_taxable_value is not None
        and min_taxable_value > max_taxable_value
    ):
        raise ValidationError(
            {"min_taxable_value": ["min_taxable_value cannot be greater than max_taxable_value."]}
        )

    return Gstr1SmartFilters(
        search=search,
        min_taxable_value=min_taxable_value,
        max_taxable_value=max_taxable_value,
        min_gst_rate=min_gst_rate,
        pos=pos,
        doc_type_values=doc_type_values,
        gstin_only=gstin_only,
        warning_severity=warning_severity,
        taxability=taxability,
        tax_regime=tax_regime,
        supply_category=supply_category,
        status=status,
    )


def smart_filters_as_dict(filters: Gstr1SmartFilters):
    payload = {
        "search": filters.search,
        "min_taxable_value": filters.min_taxable_value,
        "max_taxable_value": filters.max_taxable_value,
        "min_gst_rate": filters.min_gst_rate,
        "pos": filters.pos,
        "doc_type": ",".join(str(value) for value in filters.doc_type_values)
        if filters.doc_type_values
        else None,
        "gstin_only": filters.gstin_only if filters.gstin_only else None,
        "warning_severity": filters.warning_severity,
        "taxability": filters.taxability,
        "tax_regime": filters.tax_regime,
        "supply_category": filters.supply_category,
        "status": filters.status,
    }
    return {key: value for key, value in payload.items() if value is not None}


def _strip_or_none(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_int(value, field, *, required=True):
    if value in (None, "", 0, "0"):
        if required:
            raise ValidationError({field: [f"{field} is required."]})
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: [f"{field} must be an integer."]}) from exc


def _parse_bool(value, *, default=False):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_decimal(value, field):
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError({field: [f"{field} must be a decimal number."]}) from exc
    if parsed < 0:
        raise ValidationError({field: [f"{field} cannot be negative."]})
    return parsed


def _normalize_severity(value):
    text = _strip_or_none(value)
    if not text:
        return None
    normalized = text.lower()
    if normalized not in {"warning", "error", "info"}:
        raise ValidationError({"warning_severity": ["warning_severity must be one of: warning, error, info."]})
    return normalized


def _parse_doc_type_values(raw_value):
    text = _strip_or_none(raw_value)
    if not text:
        return ()

    chunks = [chunk.strip() for chunk in text.split(",") if chunk.strip()]
    values = set()
    for chunk in chunks:
        if chunk.isdigit():
            values.add(int(chunk))
            continue
        lowered = chunk.lower()
        for choice in SalesInvoiceHeader.DocType:
            label = str(choice.label).lower()
            name = choice.name.lower()
            if lowered in label or lowered in name:
                values.add(int(choice.value))
    if not values:
        raise ValidationError({"doc_type": ["doc_type did not match any supported document type."]})
    return tuple(sorted(values))
