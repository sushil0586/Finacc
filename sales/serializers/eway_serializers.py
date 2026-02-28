from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import date
from rest_framework import serializers


class AddressBlockSerializer(serializers.Serializer):
    # DispDtls supports Nm; ExpShipDtls doesn't require Nm. We'll keep Nm optional.
    Nm = serializers.CharField(required=False, allow_blank=True, max_length=100)
    Addr1 = serializers.CharField(required=True, allow_blank=False, max_length=255)
    Addr2 = serializers.CharField(required=False, allow_blank=True, max_length=255)
    Loc = serializers.CharField(required=True, allow_blank=False, max_length=100)
    Pin = serializers.IntegerField(required=False, min_value=100000, max_value=999999)
    Stcd = serializers.CharField(required=True, allow_blank=False, max_length=2)

    def validate_Loc(self, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 3:
            raise serializers.ValidationError("Loc must be at least 3 characters.")
        return v

    def validate_Stcd(self, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit() or len(v) != 2:
            raise serializers.ValidationError("Stcd must be 2-digit state code.")
        return v


class GenerateEWayRequestSerializer(serializers.Serializer):
    distance_km = serializers.IntegerField(min_value=1, max_value=4000)
    trans_mode = serializers.ChoiceField(choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")])

    transporter_id = serializers.CharField(max_length=32)
    transporter_name = serializers.CharField(max_length=128)

    trans_doc_no = serializers.CharField(max_length=32)
    trans_doc_date = serializers.DateField()

    vehicle_no = serializers.CharField(max_length=32, required=False, allow_blank=True)
    vehicle_type = serializers.ChoiceField(choices=[("R", "Regular"), ("O", "ODC")], required=False)

    # Optional override blocks
    disp_dtls = AddressBlockSerializer(required=False)
    exp_ship_dtls = AddressBlockSerializer(required=False)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        mode = attrs.get("trans_mode")

        if mode == "1":  # road
            veh_no = (attrs.get("vehicle_no") or "").strip()
            veh_type = attrs.get("vehicle_type")

            if not veh_no:
                raise serializers.ValidationError({"vehicle_no": "Vehicle no is required for Road transport."})
            if not veh_type:
                raise serializers.ValidationError({"vehicle_type": "Vehicle type is required for Road transport."})

        return attrs


class EWayPrefillResponseSerializer(serializers.Serializer):
    eligible = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True)

    invoice_id = serializers.IntegerField()
    invoice_status = serializers.IntegerField()
    irn = serializers.CharField(required=False, allow_blank=True)

    # Defaults shown on form-open
    default_disp_dtls = AddressBlockSerializer(required=False)
    default_exp_ship_dtls = AddressBlockSerializer(required=False)

    # If artifact exists, return last-entered transport details (draft)
    last_transport = serializers.DictField(required=False)
    last_status = serializers.DictField(required=False)