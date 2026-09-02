from __future__ import annotations

from rest_framework import serializers

from sales.models import SalesInvoiceTransportSnapshot


class SalesInvoiceTransportSnapshotSerializer(serializers.ModelSerializer):
    MEANINGFUL_FIELDS = (
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
    )

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

    def validate(self, attrs):
        merged = {}
        if self.instance is not None:
            merged = {field: getattr(self.instance, field, None) for field in self.MEANINGFUL_FIELDS}
        merged.update(attrs)

        has_meaningful_transport_detail = False
        for field in self.MEANINGFUL_FIELDS:
            value = merged.get(field)
            if value is None:
                continue
            if isinstance(value, str):
                if value.strip():
                    has_meaningful_transport_detail = True
                    break
                continue
            if field == "distance_km":
                try:
                    if int(value) > 0:
                        has_meaningful_transport_detail = True
                        break
                except (TypeError, ValueError):
                    continue
                continue
            has_meaningful_transport_detail = True
            break

        if not has_meaningful_transport_detail:
            raise serializers.ValidationError(
                {"detail": "Enter at least one transport detail before saving."}
            )
        return attrs
