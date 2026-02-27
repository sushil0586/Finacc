from __future__ import annotations

from rest_framework import serializers

from sales.models.sales_compliance import SalesEInvoice, SalesEWayBill


class SalesEInvoiceArtifactReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesEInvoice
        fields = [
            "id",
            "status",
            "irn",
            "ack_no",
            "ack_date",
            "signed_qr_code",
            "ewb_no",
            "ewb_date",
            "ewb_valid_upto",
            "attempt_count",
            "last_attempt_at",
            "last_success_at",
            "last_error_code",
            "last_error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SalesEWayArtifactReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesEWayBill
        fields = [
            "id",
            "status",
            "ewb_no",
            "ewb_date",
            "valid_upto",
            "transporter_id",
            "transporter_name",
            "transport_mode",
            "distance_km",
            "vehicle_no",
            "vehicle_type",
            "doc_no",
            "doc_date",
            "attempt_count",
            "last_attempt_at",
            "last_success_at",
            "last_error_code",
            "last_error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class GenerateIRNActionSerializer(serializers.Serializer):
    """
    No input required. IRN is generated based on invoice stored data.
    """
    pass


class GenerateEWayActionSerializer(serializers.Serializer):
    transporter_id = serializers.CharField(required=False, allow_blank=True)
    transporter_name = serializers.CharField(required=False, allow_blank=True)
    transport_mode = serializers.IntegerField(required=False)
    distance_km = serializers.IntegerField(required=False)
    vehicle_no = serializers.CharField(required=False, allow_blank=True)
    vehicle_type = serializers.IntegerField(required=False)
    doc_no = serializers.CharField(required=False, allow_blank=True)
    doc_date = serializers.DateField(required=False)