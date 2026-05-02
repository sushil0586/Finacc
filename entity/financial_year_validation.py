from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from entity.models import EntityFinancialYear


def _as_id(value: Any) -> Optional[int]:
    if value is None:
        return None
    if hasattr(value, "id"):
        return int(value.id)
    try:
        return int(value)
    except Exception:
        return None


def _as_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return value.date()
    except Exception:
        return None


def assert_document_date_within_financial_year(
    *,
    entity: Any,
    entityfinid: Any,
    document_date: Any,
    field_name: str,
) -> None:
    """
    Validates that document_date falls within the selected entity financial year.
    Raises ValueError with field-wise payload for serializer-friendly handling.
    """
    entity_id = _as_id(entity)
    entityfinid_id = _as_id(entityfinid)
    doc_day = _as_date(document_date)

    if not entityfinid_id or not doc_day:
        return

    fy = EntityFinancialYear.objects.filter(id=entityfinid_id).only(
        "id", "entity_id", "desc", "year_code", "finstartyear", "finendyear"
    ).first()
    if not fy:
        raise ValueError({"entityfinid": "Invalid financial year."})

    if entity_id and fy.entity_id and int(fy.entity_id) != int(entity_id):
        raise ValueError({"entityfinid": "Selected financial year does not belong to the selected entity."})

    start = _as_date(getattr(fy, "finstartyear", None))
    end = _as_date(getattr(fy, "finendyear", None))
    if not start or not end:
        return

    if doc_day < start or doc_day > end:
        fy_label = getattr(fy, "desc", None) or getattr(fy, "year_code", None) or f"FY#{fy.id}"
        raise ValueError(
            {
                field_name: (
                    f"Date {doc_day.isoformat()} is outside selected financial year {fy_label} "
                    f"({start.isoformat()} to {end.isoformat()})."
                )
            }
        )
