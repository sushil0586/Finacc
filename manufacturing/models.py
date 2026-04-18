from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone

from catalog.models import Product, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, Godown, SubEntity


class ManufacturingRoute(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    code = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=500, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["code", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "subentity", "code"],
                condition=Q(subentity__isnull=False),
                name="uq_mfg_route_scope_code",
            ),
            models.UniqueConstraint(
                fields=["entity", "code"],
                condition=Q(subentity__isnull=True),
                name="uq_mfg_route_root_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class ManufacturingRouteStep(models.Model):
    route = models.ForeignKey(ManufacturingRoute, on_delete=models.CASCADE, related_name="steps")
    sequence_no = models.PositiveIntegerField(default=1)
    step_code = models.CharField(max_length=40, blank=True, default="")
    step_name = models.CharField(max_length=150)
    description = models.CharField(max_length=300, blank=True, default="")
    default_duration_mins = models.PositiveIntegerField(null=True, blank=True)
    requires_qc = models.BooleanField(default=False)
    is_mandatory = models.BooleanField(default=True)

    class Meta:
        ordering = ["sequence_no", "id"]
        constraints = [
            models.UniqueConstraint(fields=["route", "sequence_no"], name="uq_mfg_route_step_sequence"),
        ]

    def __str__(self) -> str:
        return f"{self.route_id} step {self.sequence_no}: {self.step_name}"


class ManufacturingBOM(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    code = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=500, blank=True, default="")
    finished_product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    route = models.ForeignKey(ManufacturingRoute, on_delete=models.PROTECT, null=True, blank=True, related_name="boms")
    output_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("1.0000"))
    output_uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["code", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "subentity", "code"],
                condition=Q(subentity__isnull=False),
                name="uq_mfg_bom_scope_code",
            ),
            models.UniqueConstraint(
                fields=["entity", "code"],
                condition=Q(subentity__isnull=True),
                name="uq_mfg_bom_root_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "subentity", "finished_product"], name="ix_mfg_bom_scope_product"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class ManufacturingBOMMaterial(models.Model):
    bom = models.ForeignKey(ManufacturingBOM, on_delete=models.CASCADE, related_name="materials")
    line_no = models.PositiveIntegerField(default=1)
    material_product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(max_digits=18, decimal_places=4)
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    waste_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["line_no", "id"]
        constraints = [
            models.UniqueConstraint(fields=["bom", "line_no"], name="uq_mfg_bom_line_no"),
        ]

    def __str__(self) -> str:
        return f"BOM {self.bom_id} line {self.line_no}"


DEFAULT_MANUFACTURING_POLICY_CONTROLS = {
    "auto_explode_materials_from_bom": True,
    "allow_manual_material_override": True,
    "require_batch_for_batch_managed_items": True,
    "require_expiry_when_expiry_tracked": True,
    "block_negative_stock": True,
    "default_output_batch_mode": "manual",
}


def default_manufacturing_policy_controls():
    return dict(DEFAULT_MANUFACTURING_POLICY_CONTROLS)


class ManufacturingSettings(models.Model):
    class DefaultWorkflowAction(models.TextChoices):
        DRAFT = "draft", "Save as Draft"
        POST = "post", "Auto Post on Save"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="manufacturing_settings")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="manufacturing_settings")

    default_doc_code_work_order = models.CharField(max_length=10, default="MWO")
    default_workflow_action = models.CharField(
        max_length=10,
        choices=DefaultWorkflowAction.choices,
        default=DefaultWorkflowAction.DRAFT,
        db_index=True,
    )
    policy_controls = models.JSONField(default=default_manufacturing_policy_controls, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entity", "subentity"), name="uq_mfg_settings_entity_subentity"),
        ]

    def __str__(self) -> str:
        return f"ManufacturingSettings(entity={self.entity_id}, subentity={self.subentity_id})"


class ManufacturingWorkOrderStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    CANCELLED = "CANCELLED", "Cancelled"


class ManufacturingOperationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    READY = "READY", "Ready"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETED = "COMPLETED", "Completed"
    SKIPPED = "SKIPPED", "Skipped"


class ManufacturingWorkOrder(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="+")
    entityfin = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    work_order_no = models.CharField(max_length=50, blank=True, db_index=True)
    production_date = models.DateField(db_index=True)
    bom = models.ForeignKey(ManufacturingBOM, on_delete=models.PROTECT, null=True, blank=True, related_name="work_orders")
    source_location = models.ForeignKey(Godown, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    destination_location = models.ForeignKey(Godown, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    reference_no = models.CharField(max_length=100, blank=True)
    narration = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=ManufacturingWorkOrderStatus.choices, default=ManufacturingWorkOrderStatus.DRAFT, db_index=True)
    posting_entry_id = models.IntegerField(null=True, blank=True, db_index=True)
    standard_material_cost_snapshot = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    actual_material_cost_snapshot = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    total_additional_cost_snapshot = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    standard_recovery_value_snapshot = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    actual_recovery_value_snapshot = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    net_production_cost_snapshot = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    standard_output_qty_snapshot = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    actual_output_qty_snapshot = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    standard_unit_cost_snapshot = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.0000"))
    actual_unit_cost_snapshot = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.0000"))
    material_variance_value_snapshot = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    yield_variance_qty_snapshot = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    yield_variance_percent_snapshot = models.DecimalField(max_digits=9, decimal_places=4, default=Decimal("0.0000"))

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey("Authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-production_date", "-id"]
        indexes = [
            models.Index(fields=["entity", "production_date"], name="ix_mfg_wo_entity_date"),
            models.Index(fields=["entity", "work_order_no"], name="ix_mfg_wo_entity_no"),
        ]

    def __str__(self) -> str:
        return self.work_order_no or f"Manufacturing Work Order #{self.pk or 'new'}"


class ManufacturingWorkOrderMaterial(models.Model):
    work_order = models.ForeignKey(ManufacturingWorkOrder, on_delete=models.CASCADE, related_name="materials")
    line_no = models.PositiveIntegerField(default=1)
    material_product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    batch_number = models.CharField(max_length=80, blank=True, default="")
    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    required_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    actual_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.0000"))
    waste_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["line_no", "id"]
        constraints = [
            models.UniqueConstraint(fields=["work_order", "line_no"], name="uq_mfg_wo_material_line_no"),
        ]

    def __str__(self) -> str:
        return f"WO {self.work_order_id} material {self.line_no}"


class ManufacturingWorkOrderOutput(models.Model):
    class OutputType(models.TextChoices):
        MAIN = "MAIN", "Main Output"
        BYPRODUCT = "BYPRODUCT", "Byproduct"
        SALEABLE_SCRAP = "SALEABLE_SCRAP", "Saleable Scrap"

    work_order = models.ForeignKey(ManufacturingWorkOrder, on_delete=models.CASCADE, related_name="outputs")
    line_no = models.PositiveIntegerField(default=1)
    finished_product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    output_type = models.CharField(max_length=20, choices=OutputType.choices, default=OutputType.MAIN, db_index=True)
    batch_number = models.CharField(max_length=80, blank=True, default="")
    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    planned_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    actual_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    estimated_recovery_unit_value = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.0000"))
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.0000"))
    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["line_no", "id"]
        constraints = [
            models.UniqueConstraint(fields=["work_order", "line_no"], name="uq_mfg_wo_output_line_no"),
        ]

    def __str__(self) -> str:
        return f"WO {self.work_order_id} output {self.line_no}"


class ManufacturingWorkOrderAdditionalCost(models.Model):
    class CostType(models.TextChoices):
        LABOUR = "LABOUR", "Labour"
        ELECTRICITY = "ELECTRICITY", "Electricity"
        FUEL = "FUEL", "Fuel"
        MACHINE = "MACHINE", "Machine"
        OVERHEAD = "OVERHEAD", "Overhead"
        OTHER = "OTHER", "Other"

    work_order = models.ForeignKey(ManufacturingWorkOrder, on_delete=models.CASCADE, related_name="additional_costs")
    line_no = models.PositiveIntegerField(default=1)
    cost_type = models.CharField(max_length=20, choices=CostType.choices, default=CostType.OTHER, db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["line_no", "id"]
        constraints = [
            models.UniqueConstraint(fields=["work_order", "line_no"], name="uq_mfg_wo_additional_cost_line_no"),
        ]

    def __str__(self) -> str:
        return f"WO {self.work_order_id} cost {self.line_no}"


class ManufacturingWorkOrderOperation(models.Model):
    work_order = models.ForeignKey(ManufacturingWorkOrder, on_delete=models.CASCADE, related_name="operations")
    route_step = models.ForeignKey(ManufacturingRouteStep, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    sequence_no = models.PositiveIntegerField(default=1)
    step_code = models.CharField(max_length=40, blank=True, default="")
    step_name = models.CharField(max_length=150)
    description = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=ManufacturingOperationStatus.choices,
        default=ManufacturingOperationStatus.PENDING,
        db_index=True,
    )
    requires_qc = models.BooleanField(default=False)
    input_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    output_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    scrap_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    remarks = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ["sequence_no", "id"]
        constraints = [
            models.UniqueConstraint(fields=["work_order", "sequence_no"], name="uq_mfg_wo_operation_sequence"),
        ]

    def __str__(self) -> str:
        return f"WO {self.work_order_id} operation {self.sequence_no}: {self.step_name}"


class ManufacturingBatchTraceLink(models.Model):
    work_order = models.ForeignKey(ManufacturingWorkOrder, on_delete=models.CASCADE, related_name="trace_links")
    material_line = models.ForeignKey(ManufacturingWorkOrderMaterial, on_delete=models.CASCADE, related_name="trace_links")
    output_line = models.ForeignKey(ManufacturingWorkOrderOutput, on_delete=models.CASCADE, related_name="trace_links")

    input_product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    input_batch_number = models.CharField(max_length=80, blank=True, default="")
    input_manufacture_date = models.DateField(null=True, blank=True)
    input_expiry_date = models.DateField(null=True, blank=True)
    input_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))

    output_product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    output_batch_number = models.CharField(max_length=80, blank=True, default="")
    output_manufacture_date = models.DateField(null=True, blank=True)
    output_expiry_date = models.DateField(null=True, blank=True)
    output_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["material_line__line_no", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["work_order", "material_line", "output_line"],
                name="uq_mfg_trace_work_order_material_output",
            ),
        ]

    def __str__(self) -> str:
        return f"WO {self.work_order_id} trace {self.material_line_id}->{self.output_line_id}"
