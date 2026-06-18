from __future__ import annotations

from sales.services.providers.mastergst import MasterGSTProvider
from sales.services.providers.whitebooks_client import WhitebooksClient


class WhitebooksProvider(MasterGSTProvider):
    """
    Thin WhiteBooks provider split from MasterGSTProvider.

    It currently reuses the shared normalization/orchestration behavior, but
    now has dedicated module and client boundaries for future divergence.
    """

    name = "whitebooks"
    client_provider_name = "whitebooks"
    client_class = WhitebooksClient
