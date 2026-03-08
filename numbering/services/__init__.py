from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.utils import timezone

from numbering.models import DocumentNumberSeries, DocumentType
from numbering.services.document_number_service import DocNumberResult, DocumentNumberService


@dataclass(frozen=True)
class SeedSequenceResult:
    created: int
    skipped: int
    message: str


def ensure_document_type(*, module: str, doc_key: str, name: str, default_code: str) -> DocumentType:
    doc_type, _ = DocumentType.objects.get_or_create(
        module=module,
        doc_key=doc_key,
        defaults={
            "name": name,
            "default_code": default_code,
            "is_active": True,
        },
    )
    changed = []
    if not doc_type.name:
        doc_type.name = name
        changed.append("name")
    if not doc_type.default_code:
        doc_type.default_code = default_code
        changed.append("default_code")
    if not doc_type.is_active:
        doc_type.is_active = True
        changed.append("is_active")
    if changed:
        doc_type.save(update_fields=changed + ["updated_at"])
    return doc_type


def ensure_series(
    *,
    entity_id: int,
    entityfinid_id: int,
    subentity_id: Optional[int],
    doc_type_id: int,
    doc_code: str,
    prefix: str,
    start: int = 1,
    padding: int = 5,
    reset: str = "yearly",
    include_year: bool = True,
    include_month: bool = False,
) -> tuple[DocumentNumberSeries, bool]:
    series, created = DocumentNumberSeries.objects.get_or_create(
        entity_id=entity_id,
        entityfinid_id=entityfinid_id,
        subentity_id=subentity_id,
        doc_type_id=doc_type_id,
        doc_code=doc_code,
        defaults={
            "prefix": prefix,
            "suffix": "",
            "starting_number": start,
            "current_number": start,
            "number_padding": padding,
            "include_year": include_year,
            "include_month": include_month,
            "separator": "-",
            "reset_frequency": reset,
            "last_reset_date": timezone.localdate(),
            "is_active": True,
        },
    )
    if not created:
        changed = []
        if not series.is_active:
            series.is_active = True
            changed.append("is_active")
        if not series.prefix:
            series.prefix = prefix
            changed.append("prefix")
        if changed:
            series.save(update_fields=changed + ["updated_at"])
    return series, created


__all__ = [
    "DocNumberResult",
    "DocumentNumberService",
    "DocumentType",
    "DocumentNumberSeries",
    "SeedSequenceResult",
    "ensure_document_type",
    "ensure_series",
]
