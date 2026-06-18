from __future__ import annotations

from django.conf import settings
from rest_framework.exceptions import ValidationError

from sales.models.mastergst_models import SalesMasterGSTCredential, MasterGSTEnvironment, MasterGSTServiceScope


class CredentialResolver:
    """
    Later you can extend this for other providers too.
    """

    @staticmethod
    def mastergst_for_invoice(invoice):
        return CredentialResolver.provider_for_invoice(invoice, provider_name="mastergst")

    @staticmethod
    def _environment_from_settings() -> int:
        raw = getattr(settings, "SALES_MASTERGST_ENV", None)
        if raw is None:
            raw = getattr(settings, "MASTERGST_ENV", "SANDBOX")
        if isinstance(raw, str):
            return int(MasterGSTEnvironment.SANDBOX if raw.strip().upper() == "SANDBOX" else MasterGSTEnvironment.PRODUCTION)
        return int(raw)

    @staticmethod
    def provider_for_entity(entity_id: int, *, provider_name: str = "mastergst", service_scope: int = MasterGSTServiceScope.EINVOICE):
        provider = (provider_name or "mastergst").strip().lower()
        env = CredentialResolver._environment_from_settings()

        base_qs = (
            SalesMasterGSTCredential.objects
            .filter(
                entity_id=entity_id,
                environment=env,
                is_active=True,
            )
        )
        cred = base_qs.filter(service_scope=int(service_scope)).first()
        if not cred and int(service_scope) == int(MasterGSTServiceScope.EWAY):
            # Practical default: many tenants keep a single WhiteBooks credential
            # row and use it for both E-Invoice and E-Way flows.
            cred = base_qs.filter(service_scope=int(MasterGSTServiceScope.EINVOICE)).first()
        if not cred:
            scope_label = MasterGSTServiceScope(int(service_scope)).label
            raise ValidationError(
                f"{provider.title()} {scope_label} credential not configured for this entity/environment."
            )
        return cred

    @staticmethod
    def provider_for_invoice(invoice, *, provider_name: str = "mastergst", service_scope: int = MasterGSTServiceScope.EINVOICE):
        return CredentialResolver.provider_for_entity(
            invoice.entity_id,
            provider_name=provider_name,
            service_scope=service_scope,
        )
