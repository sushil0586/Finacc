from __future__ import annotations

from gst_reconciliation.services.source_documents.base import BaseSourceDocumentProvider
from gst_reconciliation.services.source_documents.providers import (
    PurchaseSourceProvider,
    SalesSourceProvider,
    VoucherSourceProvider,
)


class SourceDocumentProviderRegistry:
    _providers: dict[str, BaseSourceDocumentProvider] = {
        provider.source_document_type: provider
        for provider in (
            PurchaseSourceProvider(),
            SalesSourceProvider(),
            VoucherSourceProvider(),
        )
    }

    @classmethod
    def get_provider(cls, source_document_type: str) -> BaseSourceDocumentProvider:
        provider = cls._providers.get(source_document_type)
        if not provider:
            raise ValueError(f"Unsupported source document type: {source_document_type}")
        return provider

    @classmethod
    def all_providers(cls) -> list[BaseSourceDocumentProvider]:
        return list(cls._providers.values())

    @classmethod
    def providers_for_run_type(cls, reconciliation_type: str) -> list[BaseSourceDocumentProvider]:
        return [provider for provider in cls.all_providers() if provider.supports_run_type(reconciliation_type)]

    @classmethod
    def search(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: int | None,
        source_document_type: str | None = None,
        reconciliation_type: str | None = None,
        query: str | None = None,
        gstin: str | None = None,
        limit: int = 20,
    ):
        if source_document_type:
            providers = [cls.get_provider(source_document_type)]
        elif reconciliation_type:
            providers = cls.providers_for_run_type(reconciliation_type)
        else:
            providers = cls.all_providers()
        results = []
        for provider in providers:
            results.extend(
                provider.search(
                    entity_id=entity_id,
                    entityfinid_id=entityfinid_id,
                    subentity_id=subentity_id,
                    query=query,
                    gstin=gstin,
                    limit=limit,
                )
            )
        return results[:limit]
