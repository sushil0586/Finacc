from __future__ import annotations

from django.db import transaction

from numbering.seed_catalogs import NUMBERING_DOCUMENT_CATALOG
from numbering.services import ensure_document_type, ensure_series


class NumberingSeedService:
    """
    Seed numbering masters and series for a given entity scope.

    This is intentionally idempotent so onboarding and repair runs can safely
    execute it more than once.
    """

    @classmethod
    @transaction.atomic
    def seed_purchase_numbering(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id=None,
        start: int = 1,
        padding: int = 5,
        reset: str = "yearly",
    ):
        rows = []
        for spec in NUMBERING_DOCUMENT_CATALOG["purchase"]:
            doc_type = ensure_document_type(
                module="purchase",
                doc_key=spec["doc_key"],
                name=spec["name"],
                default_code=spec["default_code"],
            )
            series, created = ensure_series(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type.id,
                doc_code=spec["default_code"],
                prefix=spec["default_code"],
                start=start,
                padding=padding,
                reset=reset,
            )
            rows.append(
                {
                    "doc_key": spec["doc_key"],
                    "doc_code": spec["default_code"],
                    "document_type_id": doc_type.id,
                    "series_id": series.id,
                    "series_created": created,
                }
            )

        return {
            "purchase_numbering_count": len(rows),
            "purchase_numbering": rows,
        }
