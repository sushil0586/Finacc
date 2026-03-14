from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.db import transaction

from numbering.services import ensure_document_type, ensure_series


@dataclass(frozen=True)
class NumberingSeedSpec:
    module: str
    doc_key: str
    name: str
    default_code: str
    prefix: Optional[str] = None
    start: int = 1
    padding: int = 5
    reset: str = "yearly"
    include_year: bool = True
    include_month: bool = False


class NumberingSeedService:
    """
    Seed document master + numbering series in one consistent flow.
    """

    @classmethod
    @transaction.atomic
    def seed_document(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        module: str,
        doc_key: str,
        name: str,
        default_code: str,
        prefix: Optional[str] = None,
        start: int = 1,
        padding: int = 5,
        reset: str = "yearly",
        include_year: bool = True,
        include_month: bool = False,
    ) -> dict:
        doc_type = ensure_document_type(
            module=module,
            doc_key=doc_key,
            name=name,
            default_code=default_code,
        )
        series, series_created = ensure_series(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_type_id=doc_type.id,
            doc_code=default_code,
            prefix=prefix or default_code,
            start=start,
            padding=padding,
            reset=reset,
            include_year=include_year,
            include_month=include_month,
        )
        return {
            "module": module,
            "doc_key": doc_key,
            "default_code": default_code,
            "doc_type_id": doc_type.id,
            "series_id": series.id,
            "series_created": series_created,
        }

    @classmethod
    @transaction.atomic
    def seed_documents(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        specs: Iterable[NumberingSeedSpec],
    ) -> list[dict]:
        return [
            cls.seed_document(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                module=spec.module,
                doc_key=spec.doc_key,
                name=spec.name,
                default_code=spec.default_code,
                prefix=spec.prefix,
                start=spec.start,
                padding=spec.padding,
                reset=spec.reset,
                include_year=spec.include_year,
                include_month=spec.include_month,
            )
            for spec in specs
        ]
