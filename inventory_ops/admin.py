from django.contrib import admin

from .models import (
    InventoryAdjustment,
    InventoryAdjustmentLine,
    InventoryTransfer,
    InventoryTransferLine,
)


@admin.register(InventoryTransfer)
class InventoryTransferAdmin(admin.ModelAdmin):
    list_display = ("id", "transfer_no", "transfer_date", "entity", "status", "source_location", "destination_location")
    search_fields = ("transfer_no", "reference_no", "narration")
    list_filter = ("status", "transfer_date")


@admin.register(InventoryTransferLine)
class InventoryTransferLineAdmin(admin.ModelAdmin):
    list_display = ("id", "transfer", "product", "qty", "unit_cost")


@admin.register(InventoryAdjustment)
class InventoryAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("id", "adjustment_no", "adjustment_date", "entity", "status", "location")
    search_fields = ("adjustment_no", "reference_no", "narration")
    list_filter = ("status", "adjustment_date")


@admin.register(InventoryAdjustmentLine)
class InventoryAdjustmentLineAdmin(admin.ModelAdmin):
    list_display = ("id", "adjustment", "product", "direction", "qty", "unit_cost")
