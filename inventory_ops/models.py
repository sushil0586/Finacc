from __future__ import annotations

from django.db import models
from django.utils import timezone

from catalog.models import Product, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, Godown, SubEntity


class InventoryTransferStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    CANCELLED = "CANCELLED", "Cancelled"


class InventoryTransfer(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="+")
    entityfin = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    transfer_no = models.CharField(max_length=50, blank=True, db_index=True)
    transfer_date = models.DateField(db_index=True)
    source_location = models.ForeignKey(Godown, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    destination_location = models.ForeignKey(Godown, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    reference_no = models.CharField(max_length=100, blank=True)
    narration = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=InventoryTransferStatus.choices, default=InventoryTransferStatus.DRAFT, db_index=True)
    posting_entry_id = models.IntegerField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-transfer_date", "-id"]
        indexes = [
            models.Index(fields=["entity", "transfer_date"], name="ix_inv_transfer_entity_date"),
            models.Index(fields=["entity", "transfer_no"], name="ix_inv_transfer_entity_no"),
        ]

    def __str__(self) -> str:
        return self.transfer_no or f"Inventory Transfer #{self.pk or 'new'}"


class InventoryTransferLine(models.Model):
    transfer = models.ForeignKey(InventoryTransfer, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    batch_number = models.CharField(max_length=80, blank=True, default="")
    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    qty = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    note = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.transfer_id} -> {self.product_id}"


class InventoryAdjustmentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    CANCELLED = "CANCELLED", "Cancelled"


class InventoryAdjustment(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="+")
    entityfin = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    adjustment_no = models.CharField(max_length=50, blank=True, db_index=True)
    adjustment_date = models.DateField(db_index=True)
    location = models.ForeignKey(Godown, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    reference_no = models.CharField(max_length=100, blank=True)
    narration = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=InventoryAdjustmentStatus.choices, default=InventoryAdjustmentStatus.DRAFT, db_index=True)
    posting_entry_id = models.IntegerField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-adjustment_date", "-id"]
        indexes = [
            models.Index(fields=["entity", "adjustment_date"], name="ix_inv_adj_entity_date"),
            models.Index(fields=["entity", "adjustment_no"], name="ix_inv_adj_entity_no"),
        ]

    def __str__(self) -> str:
        return self.adjustment_no or f"Inventory Adjustment #{self.pk or 'new'}"


class InventoryAdjustmentLine(models.Model):
    class Direction(models.TextChoices):
        INCREASE = "INCREASE", "Increase"
        DECREASE = "DECREASE", "Decrease"

    adjustment = models.ForeignKey(InventoryAdjustment, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    batch_number = models.CharField(max_length=80, blank=True, default="")
    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    qty = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    note = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.adjustment_id} -> {self.product_id}"
