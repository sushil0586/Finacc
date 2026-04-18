from __future__ import annotations

from rest_framework import serializers

from .models import CommercePromotion, CommercePromotionScope, CommercePromotionSlab


class CommercePromotionScopeWriteSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    barcode = serializers.IntegerField(required=False, allow_null=True)


class CommercePromotionSlabWriteSerializer(serializers.Serializer):
    sequence_no = serializers.IntegerField(required=False, min_value=1)
    min_qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    free_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, default=0)
    discount_percent = serializers.DecimalField(max_digits=9, decimal_places=4, required=False, default=0)
    discount_amount = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, default=0)


class CommercePromotionWriteSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    subentity = serializers.IntegerField(required=False, allow_null=True)
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=150)
    promotion_type = serializers.ChoiceField(choices=CommercePromotion.PromotionType.choices, default=CommercePromotion.PromotionType.SAME_ITEM_SLAB)
    valid_from = serializers.DateField(required=False, allow_null=True)
    valid_to = serializers.DateField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)
    scopes = CommercePromotionScopeWriteSerializer(many=True)
    slabs = CommercePromotionSlabWriteSerializer(many=True)

    def validate(self, attrs):
        if not attrs.get("scopes"):
            raise serializers.ValidationError({"scopes": "At least one promotion scope is required."})
        if not attrs.get("slabs"):
            raise serializers.ValidationError({"slabs": "At least one promotion slab is required."})
        if attrs.get("valid_from") and attrs.get("valid_to") and attrs["valid_to"] < attrs["valid_from"]:
            raise serializers.ValidationError({"valid_to": "Valid to cannot be earlier than valid from."})
        seen_sequences = set()
        for idx, row in enumerate(attrs.get("slabs") or [], start=1):
            sequence_no = int(row.get("sequence_no") or idx)
            if sequence_no in seen_sequences:
                raise serializers.ValidationError({"slabs": [f"Duplicate sequence number {sequence_no} is not allowed."]})
            seen_sequences.add(sequence_no)
            free_qty = row.get("free_qty") or 0
            discount_percent = row.get("discount_percent") or 0
            discount_amount = row.get("discount_amount") or 0
            if free_qty == 0 and discount_percent == 0 and discount_amount == 0:
                raise serializers.ValidationError({"slabs": [f"Line {idx} must define free qty or discount benefit."]})
            if discount_percent and (discount_percent < 0 or discount_percent > 100):
                raise serializers.ValidationError({"slabs": [f"Discount percent must be between 0 and 100 for line {idx}."]})
            row["sequence_no"] = sequence_no
        return attrs


class CommercePromotionScopeResponseSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.productname", read_only=True)
    barcode_value = serializers.CharField(source="barcode.barcode", read_only=True, allow_null=True)

    class Meta:
        model = CommercePromotionScope
        fields = ["id", "product", "product_name", "barcode", "barcode_value"]


class CommercePromotionSlabResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommercePromotionSlab
        fields = ["id", "sequence_no", "min_qty", "free_qty", "discount_percent", "discount_amount"]


class CommercePromotionResponseSerializer(serializers.ModelSerializer):
    scopes = CommercePromotionScopeResponseSerializer(many=True, read_only=True)
    slabs = CommercePromotionSlabResponseSerializer(many=True, read_only=True)

    class Meta:
        model = CommercePromotion
        fields = [
            "id",
            "code",
            "name",
            "promotion_type",
            "valid_from",
            "valid_to",
            "is_active",
            "scopes",
            "slabs",
        ]


class CommerceLineNormalizeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    subentity = serializers.IntegerField(required=False, allow_null=True)
    product_id = serializers.IntegerField(required=False, allow_null=True)
    barcode = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    barcode_id = serializers.IntegerField(required=False, allow_null=True)
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    manual_discount_percent = serializers.DecimalField(max_digits=9, decimal_places=4, required=False, allow_null=True)
    manual_discount_amount = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    as_of_date = serializers.DateField(required=False, allow_null=True)
