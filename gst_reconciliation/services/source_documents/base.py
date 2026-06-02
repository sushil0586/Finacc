from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from datetime import date
from typing import Any, Iterable

from django.db.models import Q, QuerySet


@dataclass(frozen=True)
class SourceDocumentMetadata:
    provider_code: str
    source_document_type: str
    source_document_id: str
    document_number: str
    document_date: str | None
    status: str | None
    item_type: str
    direction: str
    party_name: str | None
    party_gstin: str | None
    gstin: str | None
    taxable_value: str
    cgst: str
    sgst: str
    igst: str
    cess: str
    total_amount: str
    summary: str
    normalized_comparison_payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseSourceDocumentProvider:
    provider_code: str = ""
    source_document_type: str = ""
    supported_reconciliation_types: tuple[str, ...] = ()
    search_fields: tuple[str, ...] = ()

    def supports_run_type(self, reconciliation_type: str) -> bool:
        return not self.supported_reconciliation_types or reconciliation_type in self.supported_reconciliation_types

    def get_queryset_for_item(self, *, item) -> QuerySet:
        raise NotImplementedError

    def get_queryset_for_scope(self, *, entity_id: int, entityfinid_id: int, subentity_id: int | None) -> QuerySet:
        raise NotImplementedError

    def to_metadata(self, obj) -> SourceDocumentMetadata:
        raise NotImplementedError

    def build_normalized_payload(self, obj) -> dict[str, Any]:
        raise NotImplementedError

    def validate_manual_match(self, *, item, obj) -> None:
        if not self.supports_run_type(item.run.reconciliation_type):
            raise ValueError(
                f"{self.source_document_type} does not support reconciliation type {item.run.reconciliation_type}."
            )
        metadata = self.to_metadata(obj)
        normalized = metadata.normalized_comparison_payload or {}
        if getattr(obj, "entity_id", None) != item.entity_id or getattr(obj, "entityfinid_id", None) != item.entityfinid_id:
            raise ValueError("Selected source document is not in the same entity and financial year scope.")
        if getattr(obj, "subentity_id", None) != item.subentity_id:
            raise ValueError("Selected source document is not in the same subentity scope.")
        run_gstin = self.first_nonempty(item.run.gst_registration_gstin, item.gstin)
        if run_gstin and metadata.gstin and str(run_gstin).upper() != str(metadata.gstin).upper():
            raise ValueError("Selected source document GST registration does not match the reconciliation run GSTIN.")
        item_counterparty = self.first_nonempty(item.counterparty_gstin, item.gstin)
        source_counterparty = self.first_nonempty(normalized.get("counterparty_gstin"), metadata.party_gstin)
        if item_counterparty and source_counterparty and str(item_counterparty).upper() != str(source_counterparty).upper():
            raise ValueError("Selected source document GSTIN does not match the reconciliation item counterparty GSTIN.")
        document_date = getattr(obj, "bill_date", None) or getattr(obj, "voucher_date", None)
        if item.run.return_period and isinstance(document_date, date):
            if document_date.strftime("%Y-%m") != item.run.return_period:
                raise ValueError("Selected source document period does not match the reconciliation run return period.")

    def get_document_for_item(self, *, item, document_id: str):
        obj = self.get_queryset_for_item(item=item).filter(pk=document_id).first()
        if not obj:
            raise ValueError("Selected source document is not valid for this reconciliation item scope.")
        self.validate_manual_match(item=item, obj=obj)
        return obj

    def search(
        self,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: int | None,
        query: str | None = None,
        gstin: str | None = None,
        limit: int = 20,
    ) -> list[SourceDocumentMetadata]:
        queryset = self.get_queryset_for_scope(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
        )
        if gstin:
            queryset = self.apply_gstin_filter(queryset=queryset, gstin=gstin)
        if query:
            queryset = self.apply_search(queryset=queryset, query=query)
        results = []
        for obj in queryset[:limit]:
            results.append(self.to_metadata(obj))
        return results

    def apply_search(self, *, queryset: QuerySet, query: str) -> QuerySet:
        if not self.search_fields:
            return queryset
        filters = Q()
        for field in self.search_fields:
            filters |= Q(**{f"{field}__icontains": query})
        return queryset.filter(filters)

    def apply_gstin_filter(self, *, queryset: QuerySet, gstin: str) -> QuerySet:
        return queryset

    @staticmethod
    def stringify_decimal(value: Decimal | None) -> str:
        if value is None:
            return "0.00"
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        return format(value, ".2f")

    @staticmethod
    def total_amount(*values: Decimal | None) -> str:
        total = Decimal("0.00")
        for value in values:
            total += value or Decimal("0.00")
        return format(total, ".2f")

    @staticmethod
    def first_nonempty(*values: Any) -> Any:
        for value in values:
            if value not in (None, ""):
                return value
        return None

    def bulk_to_metadata(self, objects: Iterable[Any]) -> list[SourceDocumentMetadata]:
        return [self.to_metadata(obj) for obj in objects]
