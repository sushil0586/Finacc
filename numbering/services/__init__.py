from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db.models import Q
from django.utils import timezone

from numbering.models import DocumentNumberSeries, DocumentType
from numbering.services.document_number_service import DocNumberResult, DocumentNumberService
from numbering.services.series_validation import (
    SeriesPatternConflict,
    find_series_pattern_conflict,
    validate_unique_series_pattern,
)


@dataclass(frozen=True)
class SeedSequenceResult:
    created: int
    skipped: int
    message: str


def ensure_document_type(*, module: str, doc_key: str, name: str, default_code: str) -> DocumentType:
    doc_type = DocumentType.objects.filter(module=module, doc_key=doc_key).order_by("id").first()
    if doc_type is None:
        doc_type = (
            DocumentType.objects.filter(module__iexact=module, doc_key__iexact=doc_key).order_by("id").first()
            or DocumentType.objects.filter(module__iexact=module, default_code__iexact=default_code).order_by("id").first()
        )
    if doc_type is None:
        doc_type = DocumentType.objects.create(
            module=module,
            doc_key=doc_key,
            name=name,
            default_code=default_code,
            is_active=True,
        )

    changed = []
    if doc_type.module != module:
        doc_type.module = module
        changed.append("module")
    if doc_type.doc_key != doc_key:
        doc_type.doc_key = doc_key
        changed.append("doc_key")
    if not doc_type.name:
        doc_type.name = name
        changed.append("name")
    elif doc_type.name != name:
        doc_type.name = name
        changed.append("name")
    if not doc_type.default_code:
        doc_type.default_code = default_code
        changed.append("default_code")
    elif doc_type.default_code != default_code:
        doc_type.default_code = default_code
        changed.append("default_code")
    if not doc_type.is_active:
        doc_type.is_active = True
        changed.append("is_active")
    if changed:
        doc_type.save(update_fields=changed + ["updated_at"])
    return doc_type


def ensure_document_types_batch(*, module: str, configs: list[dict]) -> dict[str, DocumentType]:
    """
    Batch-oriented variant of ensure_document_type() keyed by doc_key.
    Keeps the same normalization/update guarantees while avoiding repeated
    point lookups for callers that need several document types together.
    """
    if not configs:
        return {}

    requested = []
    seen_doc_keys: set[str] = set()
    for cfg in configs:
        doc_key = str(cfg.get("doc_key") or "").strip()
        if not doc_key or doc_key in seen_doc_keys:
            continue
        seen_doc_keys.add(doc_key)
        requested.append(
            {
                "doc_key": doc_key,
                "name": str(cfg.get("name") or "").strip(),
                "default_code": str(cfg.get("default_code") or "").strip(),
            }
        )

    if not requested:
        return {}

    doc_keys = [cfg["doc_key"] for cfg in requested]
    default_codes = [cfg["default_code"] for cfg in requested if cfg["default_code"]]

    existing_rows = list(
        DocumentType.objects.filter(
            Q(module=module, doc_key__in=doc_keys)
            | Q(module__iexact=module, doc_key__in=doc_keys)
            | Q(module__iexact=module, default_code__in=default_codes)
        ).order_by("id")
    )

    by_exact_key = {(row.module, row.doc_key): row for row in existing_rows if row.module and row.doc_key}
    by_ci_key = {(str(row.module or "").lower(), str(row.doc_key or "").lower()): row for row in existing_rows if row.doc_key}
    by_ci_default_code = {
        (str(row.module or "").lower(), str(row.default_code or "").lower()): row
        for row in existing_rows
        if row.default_code
    }

    resolved: dict[str, DocumentType] = {}
    to_create: list[DocumentType] = []
    to_update: list[DocumentType] = []

    for cfg in requested:
        doc_key = cfg["doc_key"]
        name = cfg["name"]
        default_code = cfg["default_code"]
        row = (
            by_exact_key.get((module, doc_key))
            or by_ci_key.get((module.lower(), doc_key.lower()))
            or by_ci_default_code.get((module.lower(), default_code.lower()))
        )

        if row is None:
            row = DocumentType(
                module=module,
                doc_key=doc_key,
                name=name,
                default_code=default_code,
                is_active=True,
            )
            to_create.append(row)
            resolved[doc_key] = row
            continue

        changed = False
        if row.module != module:
            row.module = module
            changed = True
        if row.doc_key != doc_key:
            row.doc_key = doc_key
            changed = True
        if row.name != name:
            row.name = name
            changed = True
        if row.default_code != default_code:
            row.default_code = default_code
            changed = True
        if not row.is_active:
            row.is_active = True
            changed = True
        if changed:
            to_update.append(row)
        resolved[doc_key] = row

    if to_create:
        DocumentType.objects.bulk_create(to_create)
    if to_update:
        DocumentType.objects.bulk_update(
            to_update,
            ["module", "doc_key", "name", "default_code", "is_active", "updated_at"],
        )

    return resolved


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
    "ensure_document_types_batch",
    "ensure_series",
    "SeriesPatternConflict",
    "find_series_pattern_conflict",
    "validate_unique_series_pattern",
]
