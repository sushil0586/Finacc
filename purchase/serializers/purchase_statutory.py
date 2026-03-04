from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from purchase.models.purchase_statutory import (
    PurchaseStatutoryChallan,
    PurchaseStatutoryChallanLine,
    PurchaseStatutoryReturn,
    PurchaseStatutoryReturnLine,
)


class PurchaseStatutoryChallanLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseStatutoryChallanLine
        fields = ["id", "header", "section", "amount", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class PurchaseStatutoryChallanSerializer(serializers.ModelSerializer):
    lines = PurchaseStatutoryChallanLineSerializer(many=True, required=False)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    tax_type_name = serializers.CharField(source="get_tax_type_display", read_only=True)
    total_deposit_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseStatutoryChallan
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "tax_type",
            "tax_type_name",
            "challan_no",
            "challan_date",
            "period_from",
            "period_to",
            "amount",
            "interest_amount",
            "late_fee_amount",
            "penalty_amount",
            "total_deposit_amount",
            "bank_ref_no",
            "bsr_code",
            "cin_no",
            "minor_head_code",
            "payment_payload_json",
            "ack_document",
            "status",
            "status_name",
            "deposited_on",
            "deposited_at",
            "deposited_by",
            "remarks",
            "created_by",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "amount",
            "status",
            "deposited_on",
            "deposited_at",
            "deposited_by",
            "created_at",
            "updated_at",
        ]


class PurchaseStatutoryChallanCreateLineInputSerializer(serializers.Serializer):
    header_id = serializers.IntegerField(min_value=1)
    section_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))


class PurchaseStatutoryChallanCreateInputSerializer(serializers.Serializer):
    entity = serializers.IntegerField(min_value=1)
    entityfinid = serializers.IntegerField(min_value=1)
    subentity = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    tax_type = serializers.ChoiceField(choices=PurchaseStatutoryChallan.TaxType.choices)
    challan_no = serializers.CharField(max_length=50)
    challan_date = serializers.DateField()
    period_from = serializers.DateField(required=False, allow_null=True)
    period_to = serializers.DateField(required=False, allow_null=True)
    interest_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False)
    late_fee_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False)
    penalty_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False)
    bank_ref_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bsr_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    cin_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    minor_head_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    payment_payload_json = serializers.JSONField(required=False)
    ack_document = serializers.FileField(required=False, allow_null=True)
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    lines = PurchaseStatutoryChallanCreateLineInputSerializer(many=True)


class PurchaseStatutoryReturnLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseStatutoryReturnLine
        fields = [
            "id",
            "header",
            "challan",
            "amount",
            "section_snapshot_code",
            "section_snapshot_desc",
            "deductee_pan_snapshot",
            "deductee_gstin_snapshot",
            "cin_snapshot",
            "metadata_json",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class PurchaseStatutoryReturnSerializer(serializers.ModelSerializer):
    lines = PurchaseStatutoryReturnLineSerializer(many=True, required=False)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    tax_type_name = serializers.CharField(source="get_tax_type_display", read_only=True)
    total_liability_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseStatutoryReturn
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "tax_type",
            "tax_type_name",
            "return_code",
            "period_from",
            "period_to",
            "amount",
            "interest_amount",
            "late_fee_amount",
            "penalty_amount",
            "total_liability_amount",
            "status",
            "status_name",
            "filed_on",
            "filed_at",
            "filed_by",
            "ack_no",
            "arn_no",
            "filed_payload_json",
            "ack_document",
            "original_return",
            "revision_no",
            "remarks",
            "created_by",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "amount",
            "status",
            "filed_on",
            "filed_at",
            "filed_by",
            "created_at",
            "updated_at",
        ]


class PurchaseStatutoryReturnCreateLineInputSerializer(serializers.Serializer):
    header_id = serializers.IntegerField(min_value=1)
    challan_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    section_snapshot_code = serializers.CharField(max_length=16, required=False, allow_blank=True, allow_null=True)
    section_snapshot_desc = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    deductee_pan_snapshot = serializers.CharField(max_length=16, required=False, allow_blank=True, allow_null=True)
    deductee_gstin_snapshot = serializers.CharField(max_length=15, required=False, allow_blank=True, allow_null=True)
    cin_snapshot = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    metadata_json = serializers.JSONField(required=False)


class PurchaseStatutoryReturnCreateInputSerializer(serializers.Serializer):
    entity = serializers.IntegerField(min_value=1)
    entityfinid = serializers.IntegerField(min_value=1)
    subentity = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    tax_type = serializers.ChoiceField(choices=PurchaseStatutoryReturn.TaxType.choices)
    return_code = serializers.CharField(max_length=30)
    period_from = serializers.DateField()
    period_to = serializers.DateField()
    interest_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False)
    late_fee_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False)
    penalty_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"), required=False)
    ack_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    arn_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    filed_payload_json = serializers.JSONField(required=False)
    ack_document = serializers.FileField(required=False, allow_null=True)
    original_return_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    revision_no = serializers.IntegerField(min_value=0, required=False)
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    lines = PurchaseStatutoryReturnCreateLineInputSerializer(many=True)
