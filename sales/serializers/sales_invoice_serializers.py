from __future__ import annotations

from rest_framework import serializers

from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary
from sales.services.sales_nav_service import SalesInvoiceNavService

from sales.services.sales_invoice_service import SalesInvoiceService



class SalesInvoiceLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    uom_code = serializers.CharField(source="uom.code", read_only=True)

    class Meta:
        model = SalesInvoiceLine
        fields = [
            "id",
            "line_no",
            "product",
            "product_name",
            "uom",
            "uom_code",
            "hsn_sac_code",
            "is_service",
            "qty",
            "free_qty",
            "rate",
            "is_rate_inclusive_of_tax",
            "discount_type",
            "discount_percent",
            "discount_amount",
            "gst_rate",
            "cess_percent",
            "cess_amount",
            # computed
            "taxable_value",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "line_total",
            "sales_account",
        ]
        read_only_fields = [
            "taxable_value",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "line_total",
        ]


class SalesTaxSummarySerializer(serializers.ModelSerializer):
    taxability_name = serializers.CharField(source="get_taxability_display", read_only=True)

    class Meta:
        model = SalesTaxSummary
        fields = [
            "id",
            "taxability",
            "taxability_name",
            "hsn_sac_code",
            "is_service",
            "gst_rate",
            "is_reverse_charge",
            "taxable_value",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "cess_amount",
        ]


class SalesInvoiceHeaderSerializer(serializers.ModelSerializer):
    # nested
    lines = SalesInvoiceLineSerializer(many=True)
    tax_summaries = SalesTaxSummarySerializer(many=True, read_only=True)

    # display fields
    doc_type_name = serializers.CharField(source="get_doc_type_display", read_only=True)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    taxability_name = serializers.CharField(source="get_taxability_display", read_only=True)
    tax_regime_name = serializers.CharField(source="get_tax_regime_display", read_only=True)
    supply_category_name = serializers.CharField(source="get_supply_category_display", read_only=True)
    navigation = serializers.SerializerMethodField()
    

    class Meta:
        model = SalesInvoiceHeader
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "doc_type",
            "doc_type_name",
            "doc_no",
            "invoice_number",
            "status",
            "status_name",
            "bill_date",
            "posting_date",
            "credit_days",
            "due_date",
            "doc_code",
            "customer",
            "customer_name",
            "customer_gstin",
            "customer_state_code",
            "seller_gstin",
            "seller_state_code",
            "place_of_supply_state_code",
            "supply_category",
            "supply_category_name",
            "taxability",
            "taxability_name",
            "tax_regime",
            "tax_regime_name",
            "is_igst",
            "is_reverse_charge",
            "gst_compliance_mode",
            "is_einvoice_applicable",
            "is_eway_applicable",
            # totals (computed)
            "total_taxable_value",
            "total_cgst",
            "total_sgst",
            "total_igst",
            "total_cess",
            "total_discount",
            "total_other_charges",
            "round_off",
            "grand_total",
            "reference",
            "remarks",
            # nested
            "lines",
            "tax_summaries",
            "navigation",
          
        ]
        read_only_fields = [
            "status",
            "doc_no",
            "invoice_number",
            "posting_date",
            "due_date",
            "tax_regime",
            "is_igst",
            # totals
            "total_taxable_value",
            "total_cgst",
            "total_sgst",
            "total_igst",
            "total_cess",
            "total_discount",
            "round_off",
            "grand_total",
            # navigation
            
        ]


    def get_navigation(self, obj):
        return SalesInvoiceNavService.get_prev_next_for_instance(obj)

    

    def validate(self, attrs):
        # enforce that UI cannot try to set backend-controlled fields
        if "status" in attrs:
            raise serializers.ValidationError({"status": "Status is controlled by backend."})
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        lines = validated_data.pop("lines", [])

        # scope should come from request/user context in your app
        entity_id = validated_data.get("entity").id if validated_data.get("entity") else request.data.get("entity")
        entityfinid_id = validated_data.get("entityfinid").id if validated_data.get("entityfinid") else request.data.get("entityfinid")
        subentity_id = validated_data.get("subentity").id if validated_data.get("subentity") else request.data.get("subentity")

        # Remove model instances from validated_data if DRF provided them
        if "entity" in validated_data:
            validated_data["entity_id"] = validated_data.pop("entity").id
        if "entityfinid" in validated_data:
            validated_data["entityfinid_id"] = validated_data.pop("entityfinid").id
        if "subentity" in validated_data and validated_data["subentity"] is not None:
            validated_data["subentity_id"] = validated_data.pop("subentity").id
        elif "subentity" in validated_data:
            validated_data.pop("subentity")

        header_data = dict(validated_data)
        header_data.pop("entity_id", None)
        header_data.pop("entityfinid_id", None)
        header_data.pop("subentity_id", None)

        header = SalesInvoiceService.create_with_lines(
            entity_id=int(entity_id),
            entityfinid_id=int(entityfinid_id),
            subentity_id=int(subentity_id) if subentity_id else None,
            header_data=header_data,
            lines_data=lines,
            user=request.user,
        )
        return header

    def update(self, instance, validated_data):
        request = self.context["request"]
        lines = validated_data.pop("lines", [])

        # Remove scope fields updates (do not allow moving invoice across scopes)
        validated_data.pop("entity", None)
        validated_data.pop("entityfinid", None)
        validated_data.pop("subentity", None)

        header = SalesInvoiceService.update_with_lines(
            header=instance,
            header_data=validated_data,
            lines_data=lines,
            user=request.user,
        )
        return header
