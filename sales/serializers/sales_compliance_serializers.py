from __future__ import annotations

from rest_framework import serializers

from sales.models.sales_compliance import SalesEInvoice, SalesEWayBill
from sales.serializers.eway_serializers import GenerateEWayRequestSerializer


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
    distance_km = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=4000)
    trans_mode = serializers.ChoiceField(
        required=False,
        allow_null=True,
        choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")],
    )
    transport_mode = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=4)
    transporter_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    transporter_name = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=128)
    trans_doc_no = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    trans_doc_date = serializers.DateField(required=False, allow_null=True)
    doc_type = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=8)
    vehicle_no = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    vehicle_type = serializers.ChoiceField(required=False, allow_null=True, choices=[("R", "Regular"), ("O", "ODC")])
    disp_dtls = serializers.JSONField(required=False, allow_null=True)
    exp_ship_dtls = serializers.JSONField(required=False, allow_null=True)

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


class GenerateEWayActionSerializer(GenerateEWayRequestSerializer):
    """
    Use exactly the same validation contract as dedicated E-Way generate endpoints.
    """

    pass


class GenerateIRNAndEWayActionSerializer(serializers.Serializer):
    """
    Combined action:
    - generate IRN
    - optionally generate E-Way in same call

    Accepts e-way data either under `eway: {...}` or as flat keys.
    """

    generate_eway = serializers.BooleanField(required=False, default=True)
    eway = serializers.DictField(required=False, allow_null=True)

    # Flat aliases for frontend convenience
    distance_km = serializers.IntegerField(required=False, allow_null=True)
    trans_mode = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    transporter_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    transporter_name = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=128)
    trans_doc_no = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=15)
    trans_doc_date = serializers.DateField(required=False, allow_null=True)
    vehicle_no = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    vehicle_type = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=1)
    disp_dtls = serializers.JSONField(required=False, allow_null=True)
    exp_ship_dtls = serializers.JSONField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs.get("generate_eway", True):
            attrs["eway"] = {}
            return attrs

        payload = dict(attrs.get("eway") or {})
        flat_keys = (
            "distance_km",
            "trans_mode",
            "transporter_id",
            "transporter_name",
            "trans_doc_no",
            "trans_doc_date",
            "vehicle_no",
            "vehicle_type",
            "disp_dtls",
            "exp_ship_dtls",
        )
        for key in flat_keys:
            if key in attrs and attrs.get(key) not in (None, ""):
                payload[key] = attrs.get(key)

        eway_ser = GenerateEWayRequestSerializer(data=payload)
        eway_ser.is_valid(raise_exception=True)
        attrs["eway"] = eway_ser.validated_data
        return attrs


class CancelIRNActionSerializer(serializers.Serializer):
    reason_code = serializers.CharField(max_length=8)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=255)


class GetIRNDetailsActionSerializer(serializers.Serializer):
    irn = serializers.CharField(required=False, allow_blank=True, max_length=64)
    supplier_gstin = serializers.CharField(required=False, allow_blank=True, max_length=15)


class GetIRNByDocDetailsActionSerializer(serializers.Serializer):
    doc_type = serializers.ChoiceField(required=False, allow_null=True, choices=[("INV", "Invoice"), ("CRN", "Credit Note"), ("DBN", "Debit Note")])
    doc_number = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=64)
    doc_date = serializers.DateField(required=False, allow_null=True)


class GetGSTNDetailsActionSerializer(serializers.Serializer):
    gstin = serializers.CharField(required=True, allow_blank=False, max_length=15)


class SyncGSTINFromCPActionSerializer(serializers.Serializer):
    gstin = serializers.CharField(required=True, allow_blank=False, max_length=15)


class GetB2CQRCodeActionSerializer(serializers.Serializer):
    upiid = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=100)
    bankaccno = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    bankifsccode = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=20)
    accountholdername = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=140)
    sgstin = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=15)
    docno = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=64)
    docdate = serializers.DateField(required=False, allow_null=True)
    totinvval = serializers.DecimalField(required=False, allow_null=True, max_digits=18, decimal_places=2)
    igstamount = serializers.DecimalField(required=False, allow_null=True, max_digits=18, decimal_places=2)
    cgstamount = serializers.DecimalField(required=False, allow_null=True, max_digits=18, decimal_places=2)
    sgstamount = serializers.DecimalField(required=False, allow_null=True, max_digits=18, decimal_places=2)
    cessamount = serializers.DecimalField(required=False, allow_null=True, max_digits=18, decimal_places=2)


class GetEWayByIRNActionSerializer(serializers.Serializer):
    irn = serializers.CharField(required=False, allow_blank=True, max_length=64)
    supplier_gstin = serializers.CharField(required=False, allow_blank=True, max_length=15)


class GetEWayDetailsActionSerializer(serializers.Serializer):
    ewb_no = serializers.CharField(required=False, allow_blank=True, max_length=32)


class GetEWayTransporterDetailsActionSerializer(serializers.Serializer):
    transporter_id = serializers.CharField(required=True, allow_blank=False, max_length=32)


class GetEWayGSTINDetailsActionSerializer(serializers.Serializer):
    gstin = serializers.CharField(required=True, allow_blank=False, max_length=15)


class GetEWayHSNDetailsActionSerializer(serializers.Serializer):
    hsn_code = serializers.CharField(required=True, allow_blank=False, max_length=16)


class GetEWayErrorListActionSerializer(serializers.Serializer):
    pass


class RejectEWayActionSerializer(serializers.Serializer):
    ewb_no = serializers.CharField(required=False, allow_blank=True, max_length=32)


class GetTripSheetActionSerializer(serializers.Serializer):
    trip_sheet_no = serializers.CharField(required=True, allow_blank=False, max_length=32)


class GetEWayByDocumentActionSerializer(serializers.Serializer):
    doc_type = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=16)
    doc_no = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=64)


class _EWayDateActionSerializer(serializers.Serializer):
    date = serializers.DateField(required=True)


class GetEWayBillsForTransporterActionSerializer(_EWayDateActionSerializer):
    pass


class GetEWayBillReportByTransporterAssignedDateActionSerializer(_EWayDateActionSerializer):
    state_code = serializers.CharField(required=True, allow_blank=False, max_length=8)


class GetEWayBillsByDateActionSerializer(_EWayDateActionSerializer):
    pass


class GetEWayBillsRejectedByOthersActionSerializer(_EWayDateActionSerializer):
    pass


class GetEWayBillsForTransporterByGSTINActionSerializer(_EWayDateActionSerializer):
    gen_gstin = serializers.CharField(required=True, allow_blank=False, max_length=15)


class GetEWayBillsForTransporterByStateActionSerializer(_EWayDateActionSerializer):
    state_code = serializers.CharField(required=True, allow_blank=False, max_length=8)


class GetEWayBillsOfOtherPartyActionSerializer(_EWayDateActionSerializer):
    pass


class _VendorAliasSerializer(serializers.Serializer):
    """
    Canonicalize app-facing snake_case request contracts while accepting
    legacy/vendor camelCase aliases for backward compatibility.
    """

    @staticmethod
    def _alias_value(attrs, *keys):
        for key in keys:
            if key in attrs and attrs.get(key) not in (None, ""):
                return attrs.get(key)
        return None


class ConsolidatedEWayBillRefSerializer(_VendorAliasSerializer):
    ewb_no = serializers.IntegerField(required=False, min_value=1)
    ewbNo = serializers.IntegerField(required=False, min_value=1, write_only=True)

    def validate(self, attrs):
        ewb_no = self._alias_value(attrs, "ewb_no", "ewbNo")
        if not ewb_no:
            raise serializers.ValidationError({"ewb_no": "This field is required."})
        return {"ewb_no": ewb_no}


class GenerateConsolidatedEWayActionSerializer(_VendorAliasSerializer):
    from_place = serializers.CharField(required=False, max_length=100)
    fromPlace = serializers.CharField(required=False, max_length=100, write_only=True)
    from_state_code = serializers.IntegerField(required=False, min_value=1, max_value=99)
    fromState = serializers.IntegerField(required=False, min_value=1, max_value=99, write_only=True)
    trans_mode = serializers.ChoiceField(required=False, choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")])
    transMode = serializers.ChoiceField(required=False, choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")], write_only=True)
    eway_bill_numbers = ConsolidatedEWayBillRefSerializer(many=True, required=False)
    tripSheetEwbBills = ConsolidatedEWayBillRefSerializer(many=True, required=False, write_only=True)
    vehicle_no = serializers.CharField(max_length=32, required=False, allow_blank=True)
    vehicleNo = serializers.CharField(max_length=32, required=False, allow_blank=True, write_only=True)
    trans_doc_no = serializers.CharField(max_length=32, required=False, allow_blank=True)
    transDocNo = serializers.CharField(max_length=32, required=False, allow_blank=True, write_only=True)
    trans_doc_date = serializers.DateField(required=False, allow_null=True)
    transDocDate = serializers.DateField(required=False, allow_null=True, write_only=True)

    def validate(self, attrs):
        from_place = self._alias_value(attrs, "from_place", "fromPlace")
        from_state_code = self._alias_value(attrs, "from_state_code", "fromState")
        trans_mode = self._alias_value(attrs, "trans_mode", "transMode")
        eway_bill_numbers = self._alias_value(attrs, "eway_bill_numbers", "tripSheetEwbBills")
        if not from_place:
            raise serializers.ValidationError({"from_place": "This field is required."})
        if from_state_code in (None, ""):
            raise serializers.ValidationError({"from_state_code": "This field is required."})
        if not trans_mode:
            raise serializers.ValidationError({"trans_mode": "This field is required."})
        if not eway_bill_numbers:
            raise serializers.ValidationError({"eway_bill_numbers": "This field is required."})
        return {
            "from_place": from_place,
            "from_state_code": from_state_code,
            "trans_mode": trans_mode,
            "eway_bill_numbers": eway_bill_numbers,
            "vehicle_no": self._alias_value(attrs, "vehicle_no", "vehicleNo") or "",
            "trans_doc_no": self._alias_value(attrs, "trans_doc_no", "transDocNo") or "",
            "trans_doc_date": self._alias_value(attrs, "trans_doc_date", "transDocDate"),
        }


class RegenerateTripSheetActionSerializer(_VendorAliasSerializer):
    from_place = serializers.CharField(required=False, max_length=100)
    fromPlace = serializers.CharField(required=False, max_length=100, write_only=True)
    from_state_code = serializers.IntegerField(required=False, min_value=1, max_value=99)
    fromState = serializers.IntegerField(required=False, min_value=1, max_value=99, write_only=True)
    reason_code = serializers.CharField(required=False, max_length=8)
    reasonCode = serializers.CharField(required=False, max_length=8, write_only=True)
    remarks = serializers.CharField(required=False, allow_null=True, max_length=255)
    reasonRem = serializers.CharField(required=False, allow_null=True, max_length=255, write_only=True)
    trans_mode = serializers.ChoiceField(required=False, allow_null=True, choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")])
    transMode = serializers.ChoiceField(required=False, allow_null=True, choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")], write_only=True)
    trip_sheet_no = serializers.IntegerField(required=False, min_value=1)
    tripSheetNo = serializers.IntegerField(required=False, min_value=1, write_only=True)
    vehicle_no = serializers.CharField(max_length=32, required=False, allow_blank=True)
    vehicleNo = serializers.CharField(max_length=32, required=False, allow_blank=True, write_only=True)
    trans_doc_no = serializers.CharField(max_length=32, required=False, allow_blank=True)
    transDocNo = serializers.CharField(max_length=32, required=False, allow_blank=True, write_only=True)
    trans_doc_date = serializers.DateField(required=False, allow_null=True)
    transDocDate = serializers.DateField(required=False, allow_null=True, write_only=True)

    def validate(self, attrs):
        required = {
            "from_place": self._alias_value(attrs, "from_place", "fromPlace"),
            "from_state_code": self._alias_value(attrs, "from_state_code", "fromState"),
            "reason_code": self._alias_value(attrs, "reason_code", "reasonCode"),
            "remarks": self._alias_value(attrs, "remarks", "reasonRem"),
            "trans_mode": self._alias_value(attrs, "trans_mode", "transMode"),
            "trip_sheet_no": self._alias_value(attrs, "trip_sheet_no", "tripSheetNo"),
        }
        missing = {key: "This field is required." for key, value in required.items() if value in (None, "")}
        if missing:
            raise serializers.ValidationError(missing)
        required["vehicle_no"] = self._alias_value(attrs, "vehicle_no", "vehicleNo") or ""
        required["trans_doc_no"] = self._alias_value(attrs, "trans_doc_no", "transDocNo") or ""
        required["trans_doc_date"] = self._alias_value(attrs, "trans_doc_date", "transDocDate")
        return required


class InitiateMultiVehicleActionSerializer(_VendorAliasSerializer):
    ewb_no = serializers.CharField(required=False, allow_blank=True, max_length=32)
    ewbNo = serializers.CharField(required=False, allow_blank=True, max_length=32, write_only=True)
    from_place = serializers.CharField(required=False, max_length=100)
    fromPlace = serializers.CharField(required=False, max_length=100, write_only=True)
    from_state_code = serializers.IntegerField(required=False, min_value=1, max_value=99)
    fromState = serializers.IntegerField(required=False, min_value=1, max_value=99, write_only=True)
    to_place = serializers.CharField(required=False, max_length=100)
    toPlace = serializers.CharField(required=False, max_length=100, write_only=True)
    to_state_code = serializers.IntegerField(required=False, min_value=1, max_value=99)
    toState = serializers.IntegerField(required=False, min_value=1, max_value=99, write_only=True)
    reason_code = serializers.CharField(required=False, max_length=8)
    reasonCode = serializers.CharField(required=False, max_length=8, write_only=True)
    remarks = serializers.CharField(required=False, allow_null=True, max_length=255)
    reasonRem = serializers.CharField(required=False, allow_null=True, max_length=255, write_only=True)
    trans_mode = serializers.ChoiceField(required=False, allow_null=True, choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")])
    transMode = serializers.ChoiceField(required=False, allow_null=True, choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")], write_only=True)
    total_quantity = serializers.IntegerField(required=False, min_value=1)
    totalQuantity = serializers.IntegerField(required=False, min_value=1, write_only=True)
    unit_code = serializers.CharField(required=False, max_length=16)
    unitCode = serializers.CharField(required=False, max_length=16, write_only=True)

    def validate(self, attrs):
        data = {
            "ewb_no": self._alias_value(attrs, "ewb_no", "ewbNo") or "",
            "from_place": self._alias_value(attrs, "from_place", "fromPlace"),
            "from_state_code": self._alias_value(attrs, "from_state_code", "fromState"),
            "to_place": self._alias_value(attrs, "to_place", "toPlace"),
            "to_state_code": self._alias_value(attrs, "to_state_code", "toState"),
            "reason_code": self._alias_value(attrs, "reason_code", "reasonCode"),
            "remarks": self._alias_value(attrs, "remarks", "reasonRem"),
            "trans_mode": self._alias_value(attrs, "trans_mode", "transMode"),
            "total_quantity": self._alias_value(attrs, "total_quantity", "totalQuantity"),
            "unit_code": self._alias_value(attrs, "unit_code", "unitCode"),
        }
        missing = {key: "This field is required." for key, value in data.items() if key != "ewb_no" and value in (None, "")}
        if missing:
            raise serializers.ValidationError(missing)
        return data


class AddMultiVehicleActionSerializer(_VendorAliasSerializer):
    ewb_no = serializers.CharField(required=False, allow_blank=True, max_length=32)
    ewbNo = serializers.CharField(required=False, allow_blank=True, max_length=32, write_only=True)
    group_no = serializers.IntegerField(required=False, min_value=1)
    groupNo = serializers.IntegerField(required=False, min_value=1, write_only=True)
    vehicle_no = serializers.CharField(required=False, allow_null=True, max_length=32)
    vehicleNo = serializers.CharField(required=False, allow_null=True, max_length=32, write_only=True)
    trans_doc_no = serializers.CharField(required=False, allow_null=True, max_length=32)
    transDocNo = serializers.CharField(required=False, allow_null=True, max_length=32, write_only=True)
    trans_doc_date = serializers.DateField(required=False, allow_null=True)
    transDocDate = serializers.DateField(required=False, allow_null=True, write_only=True)
    quantity = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        data = {
            "ewb_no": self._alias_value(attrs, "ewb_no", "ewbNo") or "",
            "group_no": self._alias_value(attrs, "group_no", "groupNo"),
            "vehicle_no": self._alias_value(attrs, "vehicle_no", "vehicleNo"),
            "trans_doc_no": self._alias_value(attrs, "trans_doc_no", "transDocNo"),
            "trans_doc_date": self._alias_value(attrs, "trans_doc_date", "transDocDate"),
            "quantity": attrs.get("quantity"),
        }
        missing = {key: "This field is required." for key, value in data.items() if key != "ewb_no" and value in (None, "")}
        if missing:
            raise serializers.ValidationError(missing)
        return data


class UpdateMultiVehicleActionSerializer(_VendorAliasSerializer):
    ewb_no = serializers.CharField(required=False, allow_blank=True, max_length=32)
    ewbNo = serializers.CharField(required=False, allow_blank=True, max_length=32, write_only=True)
    group_no = serializers.IntegerField(required=False, min_value=1)
    groupNo = serializers.IntegerField(required=False, min_value=1, write_only=True)
    old_vehicle_no = serializers.CharField(required=False, allow_null=True, max_length=32)
    oldvehicleNo = serializers.CharField(required=False, allow_null=True, max_length=32, write_only=True)
    new_vehicle_no = serializers.CharField(required=False, allow_null=True, max_length=32)
    newVehicleNo = serializers.CharField(required=False, allow_null=True, max_length=32, write_only=True)
    old_trans_no = serializers.CharField(required=False, max_length=32, allow_blank=True)
    oldTranNo = serializers.CharField(required=False, max_length=32, allow_blank=True, write_only=True)
    new_trans_no = serializers.CharField(required=False, max_length=32, allow_blank=True)
    newTranNo = serializers.CharField(required=False, max_length=32, allow_blank=True, write_only=True)
    from_place = serializers.CharField(required=False, allow_null=True, max_length=100)
    fromPlace = serializers.CharField(required=False, allow_null=True, max_length=100, write_only=True)
    from_state_code = serializers.IntegerField(required=False, min_value=1, max_value=99)
    fromState = serializers.IntegerField(required=False, min_value=1, max_value=99, write_only=True)
    reason_code = serializers.CharField(required=False, max_length=8)
    reasonCode = serializers.CharField(required=False, max_length=8, write_only=True)
    remarks = serializers.CharField(required=False, allow_null=True, max_length=255)
    reasonRem = serializers.CharField(required=False, allow_null=True, max_length=255, write_only=True)

    def validate(self, attrs):
        data = {
            "ewb_no": self._alias_value(attrs, "ewb_no", "ewbNo") or "",
            "group_no": self._alias_value(attrs, "group_no", "groupNo"),
            "old_vehicle_no": self._alias_value(attrs, "old_vehicle_no", "oldvehicleNo"),
            "new_vehicle_no": self._alias_value(attrs, "new_vehicle_no", "newVehicleNo"),
            "old_trans_no": self._alias_value(attrs, "old_trans_no", "oldTranNo") or "",
            "new_trans_no": self._alias_value(attrs, "new_trans_no", "newTranNo") or "",
            "from_place": self._alias_value(attrs, "from_place", "fromPlace"),
            "from_state_code": self._alias_value(attrs, "from_state_code", "fromState"),
            "reason_code": self._alias_value(attrs, "reason_code", "reasonCode"),
            "remarks": self._alias_value(attrs, "remarks", "reasonRem"),
        }
        missing = {key: "This field is required." for key, value in data.items() if key not in {"ewb_no", "old_trans_no", "new_trans_no"} and value in (None, "")}
        if missing:
            raise serializers.ValidationError(missing)
        return data


class CancelEWayActionSerializer(serializers.Serializer):
    reason_code = serializers.CharField(max_length=8)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=255)


class UpdateEWayVehicleActionSerializer(serializers.Serializer):
    vehicle_no = serializers.CharField(max_length=32)
    from_place = serializers.CharField(max_length=100)
    from_state_code = serializers.CharField(max_length=2)
    reason_code = serializers.CharField(max_length=8, required=False, allow_null=True, allow_blank=True)
    remarks = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    trans_doc_no = serializers.CharField(max_length=32, required=False, allow_null=True, allow_blank=True)
    trans_doc_date = serializers.DateField(required=False, allow_null=True)
    trans_mode = serializers.ChoiceField(choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")], required=False, allow_null=True)
    vehicle_type = serializers.ChoiceField(choices=[("R", "Regular"), ("O", "ODC")], required=False, allow_null=True)


class UpdateEWayTransporterActionSerializer(serializers.Serializer):
    transporter_id = serializers.CharField(max_length=32)


class ExtendEWayValidityActionSerializer(_VendorAliasSerializer):
    reason_code = serializers.CharField(required=False, allow_null=True, max_length=8)
    reasonCode = serializers.CharField(required=False, allow_null=True, max_length=8, write_only=True)
    extnRsnCode = serializers.CharField(required=False, allow_null=True, max_length=8, write_only=True)
    remarks = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    reasonRem = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255, write_only=True)
    extnRemarks = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255, write_only=True)
    from_place = serializers.CharField(required=False, allow_null=True, max_length=100)
    fromPlace = serializers.CharField(required=False, allow_null=True, max_length=100, write_only=True)
    from_pincode = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=999999)
    fromPincode = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=999999, write_only=True)
    from_state_code = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=99)
    fromState = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=99, write_only=True)
    remaining_distance_km = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    remainingDistance = serializers.IntegerField(required=False, allow_null=True, min_value=1, write_only=True)
    trans_doc_no = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    transDocNo = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32, write_only=True)
    trans_doc_date = serializers.DateField(required=False, allow_null=True)
    transDocDate = serializers.DateField(required=False, allow_null=True, write_only=True)
    trans_mode = serializers.ChoiceField(required=False, allow_null=True, choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")])
    transMode = serializers.ChoiceField(required=False, allow_null=True, choices=[("1", "Road"), ("2", "Rail"), ("3", "Air"), ("4", "Ship")], write_only=True)
    vehicle_no = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    vehicleNo = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32, write_only=True)
    vehicle_type = serializers.ChoiceField(required=False, allow_null=True, choices=[("R", "Regular"), ("O", "ODC")])
    consignment_status = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    consignmentStatus = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32, write_only=True)
    transit_type = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    transitType = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32, write_only=True)
    address_line1 = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    addressLine1 = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255, write_only=True)
    address_line2 = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    addressLine2 = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255, write_only=True)
    address_line3 = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    addressLine3 = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255, write_only=True)

    def validate(self, attrs):
        data = {
            "reason_code": self._alias_value(attrs, "reason_code", "extnRsnCode", "reasonCode"),
            "remarks": self._alias_value(attrs, "remarks", "extnRemarks", "reasonRem") or "",
            "from_place": self._alias_value(attrs, "from_place", "fromPlace"),
            "from_pincode": self._alias_value(attrs, "from_pincode", "fromPincode"),
            "from_state_code": self._alias_value(attrs, "from_state_code", "fromState"),
            "remaining_distance_km": self._alias_value(attrs, "remaining_distance_km", "remainingDistance"),
            "trans_doc_no": self._alias_value(attrs, "trans_doc_no", "transDocNo") or "",
            "trans_doc_date": self._alias_value(attrs, "trans_doc_date", "transDocDate"),
            "trans_mode": self._alias_value(attrs, "trans_mode", "transMode"),
            "vehicle_no": self._alias_value(attrs, "vehicle_no", "vehicleNo") or "",
            "vehicle_type": attrs.get("vehicle_type"),
            "consignment_status": self._alias_value(attrs, "consignment_status", "consignmentStatus") or "",
            "transit_type": self._alias_value(attrs, "transit_type", "transitType") or "",
            "address_line1": self._alias_value(attrs, "address_line1", "addressLine1") or "",
            "address_line2": self._alias_value(attrs, "address_line2", "addressLine2") or "",
            "address_line3": self._alias_value(attrs, "address_line3", "addressLine3") or "",
        }
        missing = {
            key: "This field is required."
            for key in ("reason_code", "from_place", "from_state_code", "remaining_distance_km")
            if data.get(key) in (None, "")
        }
        if missing:
            raise serializers.ValidationError(missing)
        return data
