from __future__ import annotations

from django.conf import settings
from rest_framework.exceptions import ValidationError

from sales.models.mastergst_models import SalesMasterGSTCredential, MasterGSTEnvironment


class CredentialResolver:
    """
    Later you can extend this for other providers too.
    """

    @staticmethod
    def mastergst_for_invoice(invoice):
        env_name = getattr(settings, "MASTERGST_ENV", "SANDBOX").upper()
        env = MasterGSTEnvironment.SANDBOX if env_name == "SANDBOX" else MasterGSTEnvironment.PRODUCTION

        cred = (
            SalesMasterGSTCredential.objects
            .filter(entity_id=invoice.entity_id, environment=env, is_active=True)
            .first()
        )
        if not cred:
            raise ValidationError("MasterGST credential not configured for this entity/environment.")
        return cred