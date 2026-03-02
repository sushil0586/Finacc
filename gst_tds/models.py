from django.db import models
from decimal import Decimal

ZERO2 = Decimal("0.00")

class EntityGstTdsConfig(models.Model):
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True, db_index=True)

    enabled = models.BooleanField(default=False, db_index=True)
    threshold_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("250000.00"))

    # Optional strict rule many orgs follow
    # (If supplier_state != POS and POS != deductor_state -> GST-TDS not applicable)
    enforce_pos_rule = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entity", "subentity"), name="uq_gst_tds_cfg_entity_sub"),
        ]


# gst_tds/models.py (continued)
class GstTdsContractLedger(models.Model):
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.CASCADE, db_index=True)

    vendor = models.ForeignKey("financial.account", on_delete=models.CASCADE, db_index=True)  # adjust app label

    contract_ref = models.CharField(max_length=64, db_index=True)

    cumulative_taxable = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)
    cumulative_tds = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO2)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "subentity", "entityfinid", "vendor", "contract_ref"),
                name="uq_gst_tds_contract_ledger",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "vendor"], name="ix_gst_tds_ledger_vendor"),
        ]