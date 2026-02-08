from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from django.db import transaction
from django.utils import timezone

from numbering.models import DocumentType, DocumentNumberSeries  # ✅ change to your actual app path


@dataclass(frozen=True)
class DocNumberResult:
    doc_no: int
    display_no: str


class DocumentNumberService:
    @staticmethod
    def _today() -> date:
        return timezone.localdate()

    @staticmethod
    def _needs_reset(series: DocumentNumberSeries, today: date) -> bool:
        if series.reset_frequency == "none":
            return False
        if not series.last_reset_date:
            return True
        last = series.last_reset_date
        if series.reset_frequency == "monthly":
            return (last.year, last.month) != (today.year, today.month)
        if series.reset_frequency == "yearly":
            return last.year != today.year
        return False

    @staticmethod
    def _apply_reset(series: DocumentNumberSeries, today: date) -> None:
        series.current_number = series.starting_number
        series.last_reset_date = today

    @staticmethod
    def _format_number(series: DocumentNumberSeries, number: int, on_date: date) -> str:
        year = f"{on_date.year}"
        month = f"{on_date.month:02d}"

        num_str = str(number)
        if series.number_padding and series.number_padding > 0:
            num_str = num_str.zfill(series.number_padding)

        fmt = (series.custom_format or "").strip()
        if fmt:
            return fmt.format(
                prefix=series.prefix or "",
                suffix=series.suffix or "",
                year=year if series.include_year else "",
                month=month if series.include_month else "",
                number=num_str,
                doc_code=series.doc_code,
            )

        parts = []
        if series.prefix:
            parts.append(series.prefix)
        parts.append(series.doc_code)
        if series.include_year:
            parts.append(year)
        if series.include_month:
            parts.append(month)
        parts.append(num_str)
        if series.suffix:
            parts.append(series.suffix)

        sep = series.separator or "-"
        parts = [p for p in parts if p is not None and str(p).strip() != ""]
        return sep.join(parts)

    @staticmethod
    def _get_series(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_type_id: int,
        doc_code: str,
        lock: bool,
    ) -> DocumentNumberSeries:
        qs = DocumentNumberSeries.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type_id=doc_type_id,
            doc_code=doc_code,
            is_active=True,
        )
        if lock:
            qs = qs.select_for_update()
        series = qs.first()
        if not series:
            raise ValueError(
                f"Series not found for entity={entity_id}, fin={entityfinid_id}, sub={subentity_id}, doc_type={doc_type_id}, doc_code={doc_code}"
            )
        return series

    # ---- Preview (Draft) ----
    @staticmethod
    def peek_preview(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_type_id: int,
        doc_code: str,
        on_date: Optional[date] = None,
    ) -> DocNumberResult:
        on_date = on_date or DocumentNumberService._today()
        series = DocumentNumberService._get_series(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type_id=doc_type_id,
            doc_code=doc_code,
            lock=False,
        )
        number = series.current_number
        return DocNumberResult(doc_no=number, display_no=DocumentNumberService._format_number(series, number, on_date))

    # ---- Allocate (Confirm/Post) ----
    @staticmethod
    @transaction.atomic
    def allocate_final(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_type_id: int,
        doc_code: str,
        on_date: Optional[date] = None,
    ) -> DocNumberResult:
        on_date = on_date or DocumentNumberService._today()

        series = DocumentNumberService._get_series(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type_id=doc_type_id,
            doc_code=doc_code,
            lock=True,
        )

        if DocumentNumberService._needs_reset(series, on_date):
            DocumentNumberService._apply_reset(series, on_date)

        number = series.current_number
        display = DocumentNumberService._format_number(series, number, on_date)

        series.current_number = number + 1
        series.save(update_fields=["current_number", "last_reset_date", "updated_at"])

        return DocNumberResult(doc_no=number, display_no=display)
