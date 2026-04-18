from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import (
    ManufacturingRoute,
    ManufacturingRouteStep,
    ManufacturingBOM,
    ManufacturingBOMMaterial,
    ManufacturingSettings,
    ManufacturingOperationStatus,
    ManufacturingWorkOrder,
    ManufacturingWorkOrderOperation,
    ManufacturingBatchTraceLink,
    ManufacturingWorkOrderMaterial,
    ManufacturingWorkOrderOutput,
    ManufacturingWorkOrderAdditionalCost,
)


class ManufacturingRouteStepWriteSerializer(serializers.Serializer):
    sequence_no = serializers.IntegerField(required=False, min_value=1)
    step_code = serializers.CharField(max_length=40, required=False, allow_blank=True, allow_null=True)
    step_name = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    default_duration_mins = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    requires_qc = serializers.BooleanField(required=False, default=False)
    is_mandatory = serializers.BooleanField(required=False, default=True)


class ManufacturingRouteWriteSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    subentity = serializers.IntegerField(required=False, allow_null=True)
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)
    steps = ManufacturingRouteStepWriteSerializer(many=True)

    def validate(self, attrs):
        steps = attrs.get("steps") or []
        if not steps:
            raise serializers.ValidationError({"steps": "At least one route step is required."})
        attrs["code"] = (attrs.get("code") or "").strip().upper()
        attrs["name"] = (attrs.get("name") or "").strip()
        attrs["description"] = (attrs.get("description") or "").strip()
        seen_sequences = set()
        for index, row in enumerate(steps, start=1):
            sequence_no = int(row.get("sequence_no") or index)
            if sequence_no in seen_sequences:
                raise serializers.ValidationError({"steps": [f"Duplicate sequence number {sequence_no} is not allowed."]})
            seen_sequences.add(sequence_no)
            row["sequence_no"] = sequence_no
        return attrs


class ManufacturingRouteStepResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManufacturingRouteStep
        fields = [
            "id",
            "sequence_no",
            "step_code",
            "step_name",
            "description",
            "default_duration_mins",
            "requires_qc",
            "is_mandatory",
        ]


class ManufacturingRouteResponseSerializer(serializers.ModelSerializer):
    steps = ManufacturingRouteStepResponseSerializer(many=True, read_only=True)

    class Meta:
        model = ManufacturingRoute
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_active",
            "steps",
        ]


class ManufacturingRouteListSerializer(serializers.ModelSerializer):
    step_count = serializers.SerializerMethodField()

    class Meta:
        model = ManufacturingRoute
        fields = [
            "id",
            "code",
            "name",
            "is_active",
            "step_count",
        ]

    def get_step_count(self, obj):
        return obj.steps.count()


class ManufacturingBOMMaterialWriteSerializer(serializers.Serializer):
    material_product = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    waste_percent = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_qty(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value


class ManufacturingBOMWriteSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    subentity = serializers.IntegerField(required=False, allow_null=True)
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    finished_product = serializers.IntegerField()
    route = serializers.IntegerField(required=False, allow_null=True)
    output_qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    is_active = serializers.BooleanField(required=False, default=True)
    materials = ManufacturingBOMMaterialWriteSerializer(many=True)

    def validate_output_qty(self, value):
        if value <= 0:
            raise serializers.ValidationError("Output quantity must be greater than zero.")
        return value

    def validate(self, attrs):
        if not attrs["materials"]:
            raise serializers.ValidationError("At least one material line is required.")
        attrs["code"] = (attrs.get("code") or "").strip().upper()
        attrs["name"] = (attrs.get("name") or "").strip()
        attrs["description"] = (attrs.get("description") or "").strip()
        return attrs


class ManufacturingBOMMaterialResponseSerializer(serializers.ModelSerializer):
    material_product_id = serializers.IntegerField(read_only=True)
    material_product_name = serializers.CharField(source="material_product.productname", read_only=True)
    sku = serializers.CharField(source="material_product.sku", read_only=True)
    uom_name = serializers.CharField(source="uom.code", read_only=True, allow_null=True)

    class Meta:
        model = ManufacturingBOMMaterial
        fields = [
            "id",
            "line_no",
            "material_product_id",
            "material_product_name",
            "sku",
            "uom_name",
            "qty",
            "waste_percent",
            "note",
        ]


class ManufacturingBOMResponseSerializer(serializers.ModelSerializer):
    finished_product_id = serializers.IntegerField(read_only=True)
    finished_product_name = serializers.CharField(source="finished_product.productname", read_only=True)
    finished_product_sku = serializers.CharField(source="finished_product.sku", read_only=True)
    route_id = serializers.IntegerField(read_only=True, allow_null=True)
    route_code = serializers.CharField(source="route.code", read_only=True, allow_null=True)
    route_name = serializers.CharField(source="route.name", read_only=True, allow_null=True)
    output_uom_name = serializers.CharField(source="output_uom.code", read_only=True, allow_null=True)
    materials = ManufacturingBOMMaterialResponseSerializer(many=True, read_only=True)

    class Meta:
        model = ManufacturingBOM
        fields = [
            "id",
            "code",
            "name",
            "description",
            "finished_product_id",
            "finished_product_name",
            "finished_product_sku",
            "route_id",
            "route_code",
            "route_name",
            "output_qty",
            "output_uom_name",
            "is_active",
            "materials",
        ]


class ManufacturingBOMListSerializer(serializers.ModelSerializer):
    finished_product_name = serializers.CharField(source="finished_product.productname", read_only=True)
    finished_product_sku = serializers.CharField(source="finished_product.sku", read_only=True)
    route_code = serializers.CharField(source="route.code", read_only=True, allow_null=True)
    material_count = serializers.SerializerMethodField()

    class Meta:
        model = ManufacturingBOM
        fields = [
            "id",
            "code",
            "name",
            "finished_product_name",
            "finished_product_sku",
            "route_code",
            "output_qty",
            "is_active",
            "material_count",
        ]

    def get_material_count(self, obj):
        return obj.materials.count()


class ManufacturingWorkOrderMaterialWriteSerializer(serializers.Serializer):
    material_product = serializers.IntegerField()
    required_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    actual_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, allow_null=True)
    batch_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    manufacture_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    waste_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ManufacturingWorkOrderOutputWriteSerializer(serializers.Serializer):
    finished_product = serializers.IntegerField()
    output_type = serializers.ChoiceField(
        choices=ManufacturingWorkOrderOutput.OutputType.choices,
        required=False,
        default=ManufacturingWorkOrderOutput.OutputType.MAIN,
    )
    planned_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    actual_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    estimated_recovery_unit_value = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, allow_null=True)
    batch_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    manufacture_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ManufacturingWorkOrderAdditionalCostWriteSerializer(serializers.Serializer):
    cost_type = serializers.ChoiceField(
        choices=ManufacturingWorkOrderAdditionalCost.CostType.choices,
        required=False,
        default=ManufacturingWorkOrderAdditionalCost.CostType.OTHER,
    )
    amount = serializers.DecimalField(max_digits=18, decimal_places=4)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ManufacturingWorkOrderWriteSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    production_date = serializers.DateField()
    bom = serializers.IntegerField(required=False, allow_null=True)
    source_location = serializers.IntegerField(required=False, allow_null=True)
    destination_location = serializers.IntegerField(required=False, allow_null=True)
    reference_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    planned_output_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    materials = ManufacturingWorkOrderMaterialWriteSerializer(many=True, required=False)
    outputs = ManufacturingWorkOrderOutputWriteSerializer(many=True, required=False)
    additional_costs = ManufacturingWorkOrderAdditionalCostWriteSerializer(many=True, required=False)

    def validate(self, attrs):
        materials = attrs.get("materials") or []
        outputs = attrs.get("outputs") or []
        additional_costs = attrs.get("additional_costs") or []
        bom_id = attrs.get("bom")
        if not bom_id and not outputs:
            raise serializers.ValidationError({"outputs": "Provide outputs when BOM is not selected."})
        if attrs.get("planned_output_qty") is not None and attrs["planned_output_qty"] <= 0:
            raise serializers.ValidationError({"planned_output_qty": "Planned output quantity must be greater than zero."})
        for idx, row in enumerate(materials, start=1):
            required_qty = row.get("required_qty")
            actual_qty = row.get("actual_qty")
            waste_qty = row.get("waste_qty")
            if required_qty is not None and required_qty < 0:
                raise serializers.ValidationError({"materials": [f"Required quantity cannot be negative for line {idx}."]})
            if actual_qty is not None and actual_qty < 0:
                raise serializers.ValidationError({"materials": [f"Actual quantity cannot be negative for line {idx}."]})
            if waste_qty is not None and waste_qty < 0:
                raise serializers.ValidationError({"materials": [f"Waste quantity cannot be negative for line {idx}."]})
        for idx, row in enumerate(outputs, start=1):
            output_type = row.get("output_type") or ManufacturingWorkOrderOutput.OutputType.MAIN
            planned_qty = row.get("planned_qty")
            actual_qty = row.get("actual_qty")
            recovery_value = row.get("estimated_recovery_unit_value")
            if planned_qty is not None and planned_qty <= 0:
                raise serializers.ValidationError({"outputs": [f"Planned quantity must be greater than zero for line {idx}."]})
            if actual_qty is not None and actual_qty <= 0:
                raise serializers.ValidationError({"outputs": [f"Actual quantity must be greater than zero for line {idx}."]})
            if recovery_value is not None and recovery_value < 0:
                raise serializers.ValidationError({"outputs": [f"Recovery unit value cannot be negative for line {idx}."]})
            row["output_type"] = output_type
        if outputs:
            main_count = sum(1 for row in outputs if row.get("output_type") == ManufacturingWorkOrderOutput.OutputType.MAIN)
            if main_count != 1:
                raise serializers.ValidationError({"outputs": "Exactly one main output line is required."})
        for idx, row in enumerate(additional_costs, start=1):
            if row.get("amount") is None or row["amount"] <= 0:
                raise serializers.ValidationError({"additional_costs": [f"Amount must be greater than zero for line {idx}."]})
        return attrs


class ManufacturingOperationActionSerializer(serializers.Serializer):
    input_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    output_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    scrap_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        for key in ("input_qty", "output_qty", "scrap_qty"):
            value = attrs.get(key)
            if value is not None and value < 0:
                raise serializers.ValidationError({key: "Value cannot be negative."})
        return attrs


class ManufacturingWorkOrderMaterialResponseSerializer(serializers.ModelSerializer):
    material_product_id = serializers.IntegerField(read_only=True)
    material_product_name = serializers.CharField(source="material_product.productname", read_only=True)
    sku = serializers.CharField(source="material_product.sku", read_only=True)
    uom_name = serializers.CharField(source="uom.code", read_only=True, allow_null=True)
    standard_cost = serializers.SerializerMethodField()
    actual_cost = serializers.SerializerMethodField()
    qty_variance_qty = serializers.SerializerMethodField()
    qty_variance_percent = serializers.SerializerMethodField()
    cost_variance_value = serializers.SerializerMethodField()
    line_value = serializers.SerializerMethodField()

    class Meta:
        model = ManufacturingWorkOrderMaterial
        fields = [
            "id",
            "line_no",
            "material_product_id",
            "material_product_name",
            "sku",
            "uom_name",
            "batch_number",
            "manufacture_date",
            "expiry_date",
            "required_qty",
            "actual_qty",
            "waste_qty",
            "unit_cost",
            "standard_cost",
            "actual_cost",
            "qty_variance_qty",
            "qty_variance_percent",
            "cost_variance_value",
            "line_value",
            "note",
        ]

    def get_standard_cost(self, obj):
        return (Decimal(obj.required_qty or 0) * Decimal(obj.unit_cost or 0)).quantize(Decimal("0.01"))

    def get_actual_cost(self, obj):
        return (Decimal(obj.actual_qty or 0) * Decimal(obj.unit_cost or 0)).quantize(Decimal("0.01"))

    def get_qty_variance_qty(self, obj):
        return (Decimal(obj.actual_qty or 0) - Decimal(obj.required_qty or 0)).quantize(Decimal("0.0000"))

    def get_qty_variance_percent(self, obj):
        required_qty = Decimal(obj.required_qty or 0)
        if required_qty <= 0:
            return Decimal("0.0000")
        return (((Decimal(obj.actual_qty or 0) - required_qty) / required_qty) * Decimal("100.0000")).quantize(Decimal("0.0001"))

    def get_cost_variance_value(self, obj):
        actual_cost = Decimal(obj.actual_qty or 0) * Decimal(obj.unit_cost or 0)
        standard_cost = Decimal(obj.required_qty or 0) * Decimal(obj.unit_cost or 0)
        return (actual_cost - standard_cost).quantize(Decimal("0.01"))

    def get_line_value(self, obj):
        return (Decimal(obj.actual_qty or 0) * Decimal(obj.unit_cost or 0)).quantize(Decimal("0.01"))


class ManufacturingWorkOrderOutputResponseSerializer(serializers.ModelSerializer):
    finished_product_id = serializers.IntegerField(read_only=True)
    finished_product_name = serializers.CharField(source="finished_product.productname", read_only=True)
    sku = serializers.CharField(source="finished_product.sku", read_only=True)
    uom_name = serializers.CharField(source="uom.code", read_only=True, allow_null=True)
    line_value = serializers.SerializerMethodField()

    class Meta:
        model = ManufacturingWorkOrderOutput
        fields = [
            "id",
            "line_no",
            "finished_product_id",
            "finished_product_name",
            "sku",
            "uom_name",
            "output_type",
            "batch_number",
            "manufacture_date",
            "expiry_date",
            "planned_qty",
            "actual_qty",
            "estimated_recovery_unit_value",
            "unit_cost",
            "line_value",
            "note",
        ]

    def get_line_value(self, obj):
        return (Decimal(obj.actual_qty or 0) * Decimal(obj.unit_cost or 0)).quantize(Decimal("0.01"))


class ManufacturingWorkOrderAdditionalCostResponseSerializer(serializers.ModelSerializer):
    cost_type_label = serializers.CharField(source="get_cost_type_display", read_only=True)

    class Meta:
        model = ManufacturingWorkOrderAdditionalCost
        fields = [
            "id",
            "line_no",
            "cost_type",
            "cost_type_label",
            "amount",
            "note",
        ]


class ManufacturingWorkOrderOperationResponseSerializer(serializers.ModelSerializer):
    route_step_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = ManufacturingWorkOrderOperation
        fields = [
            "id",
            "route_step_id",
            "sequence_no",
            "step_code",
            "step_name",
            "description",
            "status",
            "requires_qc",
            "input_qty",
            "output_qty",
            "scrap_qty",
            "started_at",
            "completed_at",
            "remarks",
        ]


class ManufacturingBatchTraceLinkResponseSerializer(serializers.ModelSerializer):
    material_line_id = serializers.IntegerField(read_only=True)
    output_line_id = serializers.IntegerField(read_only=True)
    input_product_id = serializers.IntegerField(read_only=True)
    input_product_name = serializers.CharField(source="input_product.productname", read_only=True)
    output_product_id = serializers.IntegerField(read_only=True)
    output_product_name = serializers.CharField(source="output_product.productname", read_only=True)

    class Meta:
        model = ManufacturingBatchTraceLink
        fields = [
            "id",
            "material_line_id",
            "output_line_id",
            "input_product_id",
            "input_product_name",
            "input_batch_number",
            "input_manufacture_date",
            "input_expiry_date",
            "input_qty",
            "output_product_id",
            "output_product_name",
            "output_batch_number",
            "output_manufacture_date",
            "output_expiry_date",
            "output_qty",
        ]


class ManufacturingWorkOrderResponseSerializer(serializers.ModelSerializer):
    bom_id = serializers.IntegerField(read_only=True, allow_null=True)
    bom_code = serializers.CharField(source="bom.code", read_only=True, allow_null=True)
    route_id = serializers.IntegerField(source="bom.route_id", read_only=True, allow_null=True)
    route_code = serializers.CharField(source="bom.route.code", read_only=True, allow_null=True)
    route_name = serializers.CharField(source="bom.route.name", read_only=True, allow_null=True)
    source_location_id = serializers.IntegerField(read_only=True, allow_null=True)
    source_location_name = serializers.CharField(source="source_location.name", read_only=True, allow_null=True)
    destination_location_id = serializers.IntegerField(read_only=True, allow_null=True)
    destination_location_name = serializers.CharField(source="destination_location.name", read_only=True, allow_null=True)
    materials = ManufacturingWorkOrderMaterialResponseSerializer(many=True, read_only=True)
    outputs = ManufacturingWorkOrderOutputResponseSerializer(many=True, read_only=True)
    additional_costs = ManufacturingWorkOrderAdditionalCostResponseSerializer(many=True, read_only=True)
    operations = ManufacturingWorkOrderOperationResponseSerializer(many=True, read_only=True)
    trace_links = ManufacturingBatchTraceLinkResponseSerializer(many=True, read_only=True)
    current_operation = serializers.SerializerMethodField()
    operations_complete = serializers.SerializerMethodField()
    total_input_value = serializers.SerializerMethodField()
    total_output_qty = serializers.SerializerMethodField()

    class Meta:
        model = ManufacturingWorkOrder
        fields = [
            "id",
            "work_order_no",
            "production_date",
            "reference_no",
            "narration",
            "status",
            "posting_entry_id",
            "bom_id",
            "bom_code",
            "route_id",
            "route_code",
            "route_name",
            "source_location_id",
            "source_location_name",
            "destination_location_id",
            "destination_location_name",
            "operations_complete",
            "current_operation",
            "total_input_value",
            "total_output_qty",
            "standard_material_cost_snapshot",
            "actual_material_cost_snapshot",
            "total_additional_cost_snapshot",
            "standard_recovery_value_snapshot",
            "actual_recovery_value_snapshot",
            "net_production_cost_snapshot",
            "standard_output_qty_snapshot",
            "actual_output_qty_snapshot",
            "standard_unit_cost_snapshot",
            "actual_unit_cost_snapshot",
            "material_variance_value_snapshot",
            "yield_variance_qty_snapshot",
            "yield_variance_percent_snapshot",
            "materials",
            "outputs",
            "additional_costs",
            "operations",
            "trace_links",
        ]

    def get_total_input_value(self, obj):
        total = sum((Decimal(line.actual_qty or 0) * Decimal(line.unit_cost or 0) for line in obj.materials.all()), Decimal("0"))
        return total.quantize(Decimal("0.01"))

    def get_total_output_qty(self, obj):
        total = sum((Decimal(line.actual_qty or 0) for line in obj.outputs.all()), Decimal("0"))
        return total.quantize(Decimal("0.0000"))

    def get_current_operation(self, obj):
        operation = obj.operations.exclude(status__in=[ManufacturingOperationStatus.COMPLETED, ManufacturingOperationStatus.SKIPPED]).order_by("sequence_no", "id").first()
        if operation is None:
            return None
        return ManufacturingWorkOrderOperationResponseSerializer(operation).data

    def get_operations_complete(self, obj):
        return not obj.operations.exclude(status__in=[ManufacturingOperationStatus.COMPLETED, ManufacturingOperationStatus.SKIPPED]).exists()


class ManufacturingWorkOrderListSerializer(serializers.ModelSerializer):
    bom_code = serializers.CharField(source="bom.code", read_only=True, allow_null=True)
    route_code = serializers.CharField(source="bom.route.code", read_only=True, allow_null=True)
    operation_count = serializers.SerializerMethodField()
    open_operation_count = serializers.SerializerMethodField()
    total_input_value = serializers.SerializerMethodField()
    total_output_qty = serializers.SerializerMethodField()

    class Meta:
        model = ManufacturingWorkOrder
        fields = [
            "id",
            "work_order_no",
            "production_date",
            "reference_no",
            "status",
            "posting_entry_id",
            "bom_code",
            "route_code",
            "operation_count",
            "open_operation_count",
            "total_input_value",
            "total_output_qty",
            "actual_unit_cost_snapshot",
            "material_variance_value_snapshot",
            "yield_variance_qty_snapshot",
        ]

    def get_total_input_value(self, obj):
        total = sum((Decimal(line.actual_qty or 0) * Decimal(line.unit_cost or 0) for line in obj.materials.all()), Decimal("0"))
        return float(total.quantize(Decimal("0.01")))

    def get_total_output_qty(self, obj):
        total = sum((Decimal(line.actual_qty or 0) for line in obj.outputs.all()), Decimal("0"))
        return float(total.quantize(Decimal("0.0000")))

    def get_operation_count(self, obj):
        return obj.operations.count()

    def get_open_operation_count(self, obj):
        return obj.operations.exclude(status__in=[ManufacturingOperationStatus.COMPLETED, ManufacturingOperationStatus.SKIPPED]).count()
