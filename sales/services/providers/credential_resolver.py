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
        raw = getattr(settings, "SALES_MASTERGST_ENV", None)
        if raw is None:
            raw = getattr(settings, "MASTERGST_ENV", "SANDBOX")
        if isinstance(raw, str):
            env = MasterGSTEnvironment.SANDBOX if raw.strip().upper() == "SANDBOX" else MasterGSTEnvironment.PRODUCTION
        else:
            env = int(raw)

        cred = (
            SalesMasterGSTCredential.objects
            .filter(
                entity_id=invoice.entity_id,
                environment=env,
                service_scope=MasterGSTServiceScope.EINVOICE,
                is_active=True,
            )
            .first()
        )
        if not cred:
            raise ValidationError("MasterGST EINVOICE credential not configured for this entity/environment.")
        return cred
