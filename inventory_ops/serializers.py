from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from catalog.models import Product, UnitOfMeasure
from entity.models import Godown, SubEntity
from .models import (
    InventoryAdjustment,
    InventoryAdjustmentLine,
    InventoryAdjustmentStatus,
    InventoryTransfer,
    InventoryTransferLine,
)


class GodownLookupSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True, allow_null=True)
    is_default = serializers.BooleanField(read_only=True)
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, obj):
        if getattr(obj, "subentity_id", None) and getattr(obj.subentity, "subentityname", None):
            return f"{obj.subentity.subentityname} - {obj.name}"
        if getattr(obj, "entity_id", None) and getattr(obj.entity, "entityname", None):
            return f"{obj.entity.entityname} - {obj.name}"
        return obj.name

    class Meta:
        model = Godown
        fields = [
            "id",
            "entity",
            "entity_name",
            "subentity",
            "subentity_name",
            "name",
            "code",
            "city",
            "state",
            "is_default",
            "display_name",
        ]


class GodownMasterSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="entity.entityname", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True, allow_null=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Godown
        fields = [
            "id",
            "entity",
            "entity_name",
            "subentity",
            "subentity_name",
            "name",
            "code",
            "address",
            "city",
            "state",
            "pincode",
            "capacity",
            "is_active",
            "is_default",
            "display_name",
        ]
        read_only_fields = ["id", "entity_name", "subentity_name", "display_name"]

    def get_display_name(self, obj):
        if getattr(obj, "subentity_id", None) and getattr(obj.subentity, "subentityname", None):
            return f"{obj.subentity.subentityname} - {obj.name}"
        if getattr(obj, "entity_id", None) and getattr(obj.entity, "entityname", None):
            return f"{obj.entity.entityname} - {obj.name}"
        return obj.name

    def validate(self, attrs):
        entity = attrs.get("entity") or getattr(self.instance, "entity", None)
        subentity = attrs.get("subentity") or getattr(self.instance, "subentity", None)
        if subentity and entity and subentity.entity_id != entity.id:
            raise serializers.ValidationError({"subentity": "Subentity must belong to the same entity as the godown."})
        if attrs.get("code"):
            attrs["code"] = attrs["code"].strip().upper()
        if attrs.get("name"):
            attrs["name"] = attrs["name"].strip()
        return attrs


class GodownWriteSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    subentity = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=150)
    code = serializers.CharField(max_length=50)
    address = serializers.CharField(allow_blank=True, required=False)
    city = serializers.CharField(allow_blank=True, required=False)
    state = serializers.CharField(allow_blank=True, required=False)
    pincode = serializers.CharField(allow_blank=True, required=False)
    capacity = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)
    is_default = serializers.BooleanField(required=False, default=False)

    def validate_subentity(self, value):
        if value is None:
            return value
        entity_id = self.initial_data.get("entity")
        if not entity_id:
            raise serializers.ValidationError("Entity is required before choosing a subentity.")
        try:
            entity_id = int(entity_id)
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError("Entity must be a valid numeric id.") from exc
        subentity = SubEntity.objects.filter(id=value, entity_id=entity_id).only("id").first()
        if subentity is None:
            raise serializers.ValidationError("Subentity must belong to the selected entity.")
        return value

    def validate(self, attrs):
        attrs["name"] = (attrs.get("name") or "").strip()
        attrs["code"] = (attrs.get("code") or "").strip().upper()
        if not attrs["name"]:
            raise serializers.ValidationError({"name": "Name is required."})
        if not attrs["code"]:
            raise serializers.ValidationError({"code": "Code is required."})
        if not attrs.get("address"):
            attrs["address"] = ""
        if not attrs.get("city"):
            attrs["city"] = ""
        if not attrs.get("state"):
            attrs["state"] = ""
        if not attrs.get("pincode"):
            attrs["pincode"] = ""
        return attrs


class InventoryTransferLineSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, allow_null=True)
    batch_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    manufacture_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_qty(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_unit_cost(self, value):
        if value is None:
            return value
        if value < 0:
            raise serializers.ValidationError("Unit cost cannot be negative.")
        return value


class InventoryTransferCreateSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    transfer_date = serializers.DateField()
    source_location = serializers.IntegerField(required=False, allow_null=True)
    destination_location = serializers.IntegerField(required=False, allow_null=True)
    reference_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    lines = InventoryTransferLineSerializer(many=True)

    def validate(self, attrs):
        if int(attrs["source_location"]) == int(attrs["destination_location"]):
            raise serializers.ValidationError("Source and destination locations must be different.")
        if not attrs["lines"]:
            raise serializers.ValidationError("At least one transfer line is required.")
        return attrs


class InventoryTransferLineResponseSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField()
    product_name = serializers.CharField(source="product.productname", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    uom_name = serializers.CharField(source="uom.code", read_only=True, allow_null=True)
    line_value = serializers.SerializerMethodField()

    class Meta:
        model = InventoryTransferLine
        fields = [
            "id",
            "product_id",
            "product_name",
            "sku",
            "uom_name",
            "batch_number",
            "manufacture_date",
            "expiry_date",
            "qty",
            "unit_cost",
            "line_value",
            "note",
        ]

    def get_line_value(self, obj):
        return (Decimal(obj.qty or 0) * Decimal(obj.unit_cost or 0)).quantize(Decimal("0.01"))


class InventoryTransferResponseSerializer(serializers.ModelSerializer):
    source_location_id = serializers.IntegerField(read_only=True)
    source_location_name = serializers.CharField(source="source_location.name", read_only=True)
    source_location_code = serializers.CharField(source="source_location.code", read_only=True)
    source_location_display_name = serializers.CharField(source="source_location.display_name", read_only=True, allow_null=True)
    destination_location_id = serializers.IntegerField(read_only=True)
    destination_location_name = serializers.CharField(source="destination_location.name", read_only=True)
    destination_location_code = serializers.CharField(source="destination_location.code", read_only=True)
    destination_location_display_name = serializers.CharField(source="destination_location.display_name", read_only=True, allow_null=True)
    lines = InventoryTransferLineResponseSerializer(many=True, read_only=True)
    total_qty = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()

    class Meta:
        model = InventoryTransfer
        fields = [
            "id",
            "transfer_no",
            "transfer_date",
            "reference_no",
            "narration",
            "status",
            "posting_entry_id",
            "source_location_id",
            "source_location_name",
            "source_location_code",
            "source_location_display_name",
            "destination_location_id",
            "destination_location_name",
            "destination_location_code",
            "destination_location_display_name",
            "total_qty",
            "total_value",
            "lines",
        ]

    def get_total_qty(self, obj):
        total = sum((Decimal(line.qty or 0) for line in obj.lines.all()), Decimal("0"))
        return total.quantize(Decimal("0.0000"))

    def get_total_value(self, obj):
        total = sum((Decimal(line.qty or 0) * Decimal(line.unit_cost or 0) for line in obj.lines.all()), Decimal("0"))
        return total.quantize(Decimal("0.01"))


class InventoryTransferListSerializer(serializers.ModelSerializer):
    source_location_name = serializers.CharField(source="source_location.name", read_only=True)
    source_location_display_name = serializers.CharField(source="source_location.display_name", read_only=True, allow_null=True)
    destination_location_name = serializers.CharField(source="destination_location.name", read_only=True)
    destination_location_display_name = serializers.CharField(source="destination_location.display_name", read_only=True, allow_null=True)
    total_qty = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()

    class Meta:
        model = InventoryTransfer
        fields = [
            "id",
            "transfer_no",
            "transfer_date",
            "reference_no",
            "narration",
            "status",
            "posting_entry_id",
            "source_location_name",
            "source_location_display_name",
            "destination_location_name",
            "destination_location_display_name",
            "total_qty",
            "total_value",
        ]

    def get_total_qty(self, obj):
        total = sum((Decimal(line.qty or 0) for line in obj.lines.all()), Decimal("0"))
        return float(total.quantize(Decimal("0.0000")))

    def get_total_value(self, obj):
        total = sum((Decimal(line.qty or 0) * Decimal(line.unit_cost or 0) for line in obj.lines.all()), Decimal("0"))
        return float(total.quantize(Decimal("0.01")))


class InventoryAdjustmentLineSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    direction = serializers.ChoiceField(choices=[choice[0] for choice in InventoryAdjustmentLine.Direction.choices])
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, allow_null=True)
    batch_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    manufacture_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_qty(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_unit_cost(self, value):
        if value is None:
            return value
        if value < 0:
            raise serializers.ValidationError("Unit cost cannot be negative.")
        return value


class InventoryAdjustmentCreateSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    adjustment_date = serializers.DateField()
    location = serializers.IntegerField(required=False, allow_null=True)
    reference_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    lines = InventoryAdjustmentLineSerializer(many=True)

    def validate(self, attrs):
        if not attrs["lines"]:
            raise serializers.ValidationError("At least one adjustment line is required.")
        return attrs


class InventoryAdjustmentLineResponseSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField()
    product_name = serializers.CharField(source="product.productname", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    uom_name = serializers.CharField(source="uom.code", read_only=True, allow_null=True)
    line_value = serializers.SerializerMethodField()

    class Meta:
        model = InventoryAdjustmentLine
        fields = [
            "id",
            "product_id",
            "product_name",
            "sku",
            "uom_name",
            "batch_number",
            "manufacture_date",
            "expiry_date",
            "direction",
            "qty",
            "unit_cost",
            "line_value",
            "note",
        ]

    def get_line_value(self, obj):
        return (Decimal(obj.qty or 0) * Decimal(obj.unit_cost or 0)).quantize(Decimal("0.01"))


class InventoryAdjustmentResponseSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)
    location_display_name = serializers.CharField(source="location.display_name", read_only=True, allow_null=True)
    lines = InventoryAdjustmentLineResponseSerializer(many=True, read_only=True)
    total_qty = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()

    class Meta:
        model = InventoryAdjustment
        fields = [
            "id",
            "adjustment_no",
            "adjustment_date",
            "reference_no",
            "narration",
            "status",
            "posting_entry_id",
            "location_name",
            "location_code",
            "location_display_name",
            "total_qty",
            "total_value",
            "lines",
        ]

    def get_total_qty(self, obj):
        total = sum((Decimal(line.qty or 0) for line in obj.lines.all()), Decimal("0"))
        return float(total.quantize(Decimal("0.0000")))

    def get_total_value(self, obj):
        total = sum((Decimal(line.qty or 0) * Decimal(line.unit_cost or 0) for line in obj.lines.all()), Decimal("0"))
        return float(total.quantize(Decimal("0.01")))


class InventoryAdjustmentListSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True, allow_null=True)
    location_display_name = serializers.CharField(source="location.display_name", read_only=True, allow_null=True)
    total_qty = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()

    class Meta:
        model = InventoryAdjustment
        fields = [
            "id",
            "adjustment_no",
            "adjustment_date",
            "reference_no",
            "narration",
            "status",
            "posting_entry_id",
            "location_name",
            "location_display_name",
            "total_qty",
            "total_value",
        ]

    def get_total_qty(self, obj):
        total = sum((Decimal(line.qty or 0) for line in obj.lines.all()), Decimal("0"))
        return float(total.quantize(Decimal("0.0000")))

    def get_total_value(self, obj):
        total = sum((Decimal(line.qty or 0) * Decimal(line.unit_cost or 0) for line in obj.lines.all()), Decimal("0"))
        return float(total.quantize(Decimal("0.01")))
