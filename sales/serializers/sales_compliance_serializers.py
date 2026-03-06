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


class EnsureComplianceActionSerializer(serializers.Serializer):
    """
    Optional transport prefill/save for e-way artifact during ensure call.
    """
    distance_km = serializers.IntegerField(required=False, min_value=0, max_value=4000)
    trans_mode = serializers.ChoiceField(
        required=False,
        choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")],
    )
    transport_mode = serializers.IntegerField(required=False, min_value=1, max_value=4)
    transporter_id = serializers.CharField(required=False, allow_blank=True, max_length=32)
    transporter_name = serializers.CharField(required=False, allow_blank=True, max_length=128)
    trans_doc_no = serializers.CharField(required=False, allow_blank=True, max_length=32)
    trans_doc_date = serializers.DateField(required=False)
    doc_type = serializers.CharField(required=False, allow_blank=True, max_length=8)
    vehicle_no = serializers.CharField(required=False, allow_blank=True, max_length=32)
    vehicle_type = serializers.ChoiceField(required=False, choices=[("R", "Regular"), ("O", "ODC")])
    disp_dtls = serializers.JSONField(required=False)
    exp_ship_dtls = serializers.JSONField(required=False)

    def validate(self, attrs):
        mode = attrs.get("trans_mode")
        if mode is None and "transport_mode" in attrs and attrs.get("transport_mode") is not None:
            mode = str(attrs.get("transport_mode"))
            attrs["trans_mode"] = mode
        if mode == "1":
            if not (attrs.get("vehicle_no") or "").strip():
                raise serializers.ValidationError({"vehicle_no": "vehicle_no required for Road transport (mode=1)."})
            if not attrs.get("vehicle_type"):
                raise serializers.ValidationError({"vehicle_type": "vehicle_type required for Road transport (mode=1)."})
        if mode in {"2", "3", "4"}:
            if not (attrs.get("trans_doc_no") or "").strip():
                raise serializers.ValidationError({"trans_doc_no": "trans_doc_no required for Rail/Air/Ship."})
            if not attrs.get("trans_doc_date"):
                raise serializers.ValidationError({"trans_doc_date": "trans_doc_date required for Rail/Air/Ship."})
        return attrs


class GenerateEWayActionSerializer(serializers.Serializer):
    transporter_id = serializers.CharField(required=False, allow_blank=True)
    transporter_name = serializers.CharField(required=False, allow_blank=True)
    transport_mode = serializers.IntegerField(required=False)
    distance_km = serializers.IntegerField(required=False)
    vehicle_no = serializers.CharField(required=False, allow_blank=True)
    vehicle_type = serializers.IntegerField(required=False)
    doc_no = serializers.CharField(required=False, allow_blank=True)
    doc_date = serializers.DateField(required=False)


class CancelIRNActionSerializer(serializers.Serializer):
    reason_code = serializers.CharField(max_length=8)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=255)


class GetIRNDetailsActionSerializer(serializers.Serializer):
    irn = serializers.CharField(required=False, allow_blank=True, max_length=64)
    supplier_gstin = serializers.CharField(required=False, allow_blank=True, max_length=15)


class GetEWayByIRNActionSerializer(serializers.Serializer):
    irn = serializers.CharField(required=False, allow_blank=True, max_length=64)
    supplier_gstin = serializers.CharField(required=False, allow_blank=True, max_length=15)


class CancelEWayActionSerializer(serializers.Serializer):
    reason_code = serializers.CharField(max_length=8)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=255)


class UpdateEWayVehicleActionSerializer(serializers.Serializer):
    vehicle_no = serializers.CharField(max_length=32)
    from_place = serializers.CharField(max_length=100)
    from_state_code = serializers.CharField(max_length=2)
    reason_code = serializers.CharField(max_length=8, required=False, allow_blank=True)
    remarks = serializers.CharField(max_length=255, required=False, allow_blank=True)
    trans_doc_no = serializers.CharField(max_length=32, required=False, allow_blank=True)
    trans_doc_date = serializers.DateField(required=False)
    trans_mode = serializers.ChoiceField(choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")], required=False)
    vehicle_type = serializers.ChoiceField(choices=[("R", "Regular"), ("O", "ODC")], required=False)


class UpdateEWayTransporterActionSerializer(serializers.Serializer):
    transporter_id = serializers.CharField(max_length=32)


class ExtendEWayValidityActionSerializer(serializers.Serializer):
    reason_code = serializers.CharField(max_length=8)
    remarks = serializers.CharField(max_length=255, required=False, allow_blank=True)
    from_place = serializers.CharField(max_length=100)
    from_state_code = serializers.CharField(max_length=2)
    remaining_distance_km = serializers.IntegerField(min_value=1)
    trans_doc_no = serializers.CharField(max_length=32, required=False, allow_blank=True)
    trans_doc_date = serializers.DateField(required=False)
    trans_mode = serializers.ChoiceField(choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")], required=False)
    vehicle_no = serializers.CharField(max_length=32, required=False, allow_blank=True)
    vehicle_type = serializers.ChoiceField(choices=[("R", "Regular"), ("O", "ODC")], required=False)
