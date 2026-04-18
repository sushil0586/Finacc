from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.utils import timezone

from catalog.models import Product, ProductBarcode
from entity.models import Entity, SubEntity


class CommercePromotion(models.Model):
    class PromotionType(models.TextChoices):
        SAME_ITEM_SLAB = "SAME_ITEM_SLAB", "Same Item Slab"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    code = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=150)
    promotion_type = models.CharField(max_length=30, choices=PromotionType.choices, default=PromotionType.SAME_ITEM_SLAB)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "subentity", "code"],
                condition=Q(subentity__isnull=False),
                name="uq_commerce_promotion_scope_code",
            ),
            models.UniqueConstraint(
                fields=["entity", "code"],
                condition=Q(subentity__isnull=True),
                name="uq_commerce_promotion_root_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class CommercePromotionScope(models.Model):
    promotion = models.ForeignKey(CommercePromotion, on_delete=models.CASCADE, related_name="scopes")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="+")
    barcode = models.ForeignKey(ProductBarcode, on_delete=models.CASCADE, null=True, blank=True, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["promotion", "product", "barcode"],
                name="uq_commerce_promotion_scope_product_barcode",
            ),
        ]


class CommercePromotionSlab(models.Model):
    promotion = models.ForeignKey(CommercePromotion, on_delete=models.CASCADE, related_name="slabs")
    sequence_no = models.PositiveIntegerField(default=1)
    min_qty = models.DecimalField(max_digits=18, decimal_places=4)
    free_qty = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    discount_percent = models.DecimalField(max_digits=9, decimal_places=4, default=0)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        ordering = ["sequence_no", "id"]
        constraints = [
            models.UniqueConstraint(fields=["promotion", "sequence_no"], name="uq_commerce_promotion_slab_sequence"),
        ]

