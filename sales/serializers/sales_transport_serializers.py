from __future__ import annotations

from rest_framework import serializers

from sales.models import SalesInvoiceTransportSnapshot


class SalesInvoiceTransportSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesInvoiceTransportSnapshot
        fields = (
            "transporter_id",
            "transporter_name",
            "transport_mode",
            "vehicle_no",
            "vehicle_type",
            "lr_gr_no",
            "lr_gr_date",
            "distance_km",
            "dispatch_through",
            "driver_name",
            "driver_mobile",
            "remarks",
            "source",
        )

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        for field in (
            "transporter_id",
            "transporter_name",
            "vehicle_no",
            "vehicle_type",
            "lr_gr_no",
            "dispatch_through",
            "driver_name",
            "driver_mobile",
            "remarks",
        ):
            if field in value and isinstance(value[field], str):
                value[field] = value[field].strip()
        if "vehicle_type" in value and value["vehicle_type"]:
            value["vehicle_type"] = value["vehicle_type"].upper()
        return value
