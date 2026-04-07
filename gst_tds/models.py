from django.db import models
from decimal import Decimal

ZERO2 = Decimal("0.00")


class GstTdsMasterRule(models.Model):
    """
    Global GST-TDS master (law-level defaults).
    Tenant/entity config should reference this and can still set threshold flags separately.
    """
    code = models.CharField(max_length=32, unique=True, db_index=True, default="GST_TDS_SEC_51")
    label = models.CharField(max_length=128, default="GST-TDS Section 51")
    section_code = models.CharField(max_length=16, default="51", db_index=True)
    total_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("2.0000"))
    cgst_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("1.0000"))
    sgst_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("1.0000"))
    igst_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("2.0000"))
    effective_from = models.DateField(db_index=True)
    effective_to = models.DateField(null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "effective_from"], name="ix_gst_tds_master_eff"),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.section_code})"


class EntityGstTdsConfig(models.Model):
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, db_index=True)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    master_rule = models.ForeignKey(
        "gst_tds.GstTdsMasterRule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
    )

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

    vendor = models.ForeignKey("financial.account", on_delete=models.PROTECT, db_index=True)  # adjust app label

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
