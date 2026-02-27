from __future__ import annotations

from typing import Dict

from sales.services.providers.base import EInvoiceProvider, EWayProvider


class ProviderRegistry:
    _einvoice: Dict[str, EInvoiceProvider] = {}
    _eway: Dict[str, EWayProvider] = {}

    @classmethod
    def register_einvoice(cls, provider: EInvoiceProvider) -> None:
        cls._einvoice[provider.name] = provider

    @classmethod
    def register_eway(cls, provider: EWayProvider) -> None:
        cls._eway[provider.name] = provider

    @classmethod
    def get_einvoice(cls, name: str) -> EInvoiceProvider:
        if name not in cls._einvoice:
            raise ValueError(f"EInvoice provider '{name}' not registered.")
        return cls._einvoice[name]

    @classmethod
    def get_eway(cls, name: str) -> EWayProvider:
        if name not in cls._eway:
            raise ValueError(f"EWay provider '{name}' not registered.")
        return cls._eway[name]