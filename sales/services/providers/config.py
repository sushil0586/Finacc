from __future__ import annotations

from django.conf import settings


DEFAULT_PROVIDER = "mastergst"


def active_einvoice_provider() -> str:
    return str(
        getattr(
            settings,
            "EINVOICE_PROVIDER",
            getattr(settings, "GST_COMPLIANCE_PROVIDER", DEFAULT_PROVIDER),
        )
        or DEFAULT_PROVIDER
    ).strip().lower()


def active_eway_provider() -> str:
    return str(
        getattr(
            settings,
            "EWAY_PROVIDER",
            getattr(settings, "GST_EWAY_PROVIDER", active_einvoice_provider()),
        )
        or active_einvoice_provider()
    ).strip().lower()


def provider_base_url(provider_name: str) -> str:
    provider = (provider_name or DEFAULT_PROVIDER).strip().lower()
    mapped = getattr(settings, "GST_PROVIDER_BASE_URLS", {}) or {}
    if provider in mapped and mapped[provider]:
        return str(mapped[provider]).rstrip("/")

    if provider == "whitebooks":
        return str(
            getattr(
                settings,
                "WHITEBOOKS_BASE_URL",
                getattr(settings, "MASTERGST_BASE_URL", "https://api.mastergst.com"),
            )
        ).rstrip("/")

    return str(getattr(settings, "MASTERGST_BASE_URL", "https://api.mastergst.com")).rstrip("/")


def provider_debug_enabled(provider_name: str) -> bool:
    provider = (provider_name or DEFAULT_PROVIDER).strip().lower()
    mapped = getattr(settings, "GST_PROVIDER_DEBUG", {}) or {}
    if provider in mapped:
        return bool(mapped[provider])
    return bool(getattr(settings, "MASTERGST_DEBUG", False))
