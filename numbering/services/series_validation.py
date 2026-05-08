from __future__ import annotations

from dataclasses import dataclass

from numbering.models import DocumentNumberSeries


@dataclass(frozen=True)
class SeriesPatternConflict:
    series_id: int
    doc_code: str
    subentity_id: int | None
    subentity_name: str


def find_series_pattern_conflict(
    *,
    series: DocumentNumberSeries,
) -> SeriesPatternConflict | None:
    conflict = (
        DocumentNumberSeries.objects.select_related("subentity")
        .filter(
            entity_id=series.entity_id,
            entityfinid_id=series.entityfinid_id,
            doc_type_id=series.doc_type_id,
            doc_code=series.doc_code,
            prefix=series.prefix,
            suffix=series.suffix,
            separator=series.separator,
            include_year=series.include_year,
            include_month=series.include_month,
            custom_format=series.custom_format,
            is_active=True,
        )
        .exclude(pk=series.pk)
        .first()
    )
    if not conflict:
        return None

    subentity_name = getattr(getattr(conflict, "subentity", None), "subentityname", "") or "Entity default"
    return SeriesPatternConflict(
        series_id=int(conflict.id),
        doc_code=str(conflict.doc_code or ""),
        subentity_id=conflict.subentity_id,
        subentity_name=subentity_name,
    )


def validate_unique_series_pattern(
    *,
    series: DocumentNumberSeries,
    doc_label: str,
) -> None:
    conflict = find_series_pattern_conflict(series=series)
    if not conflict:
        return

    raise ValueError(
        f"{doc_label} numbering pattern is already active for {conflict.subentity_name}. "
        "Change the series code or numbering format so each branch stays distinct."
    )
