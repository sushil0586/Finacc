from __future__ import annotations

from sales.services.providers.mastergst_client import MasterGSTClient


class WhitebooksClient(MasterGSTClient):
    """
    Thin WhiteBooks client split from MasterGSTClient.

    Behavior is intentionally identical today; this class exists so future
    WhiteBooks-specific request/auth/normalization overrides live outside the
    shared MasterGST client module.
    """

    def __init__(self, cred, *, provider_name: str = "whitebooks"):
        super().__init__(cred, provider_name=provider_name)
