from __future__ import annotations

from rest_framework import serializers
from financial.models import ShippingDetails
from withholding.models import WithholdingSection, WithholdingTaxType
from decimal import Decimal
import re



from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary
from sales.services.sales_nav_service import SalesInvoiceNavService

from sales.services.sales_invoice_service import SalesInvoiceService
from sales.serializers.sales_charge_serializers import SalesChargeLineSerializer
from sales.serializers.sales_compliance_serializers import (
    SalesEInvoiceArtifactReadSerializer,
    SalesEWayArtifactReadSerializer,
)



class SalesInvoiceLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.productname", read_only=True)
    uom_code = serializers.CharField(source="uom.code", read_only=True)

    gstRateAmount = serializers.SerializerMethodField()
    discount_type_name = serializers.CharField(
        source="get_discount_type_display",
        read_only=True
    )

    class Meta:
        model = SalesInvoiceLine
        fields = [
            "id",
            "line_no",
            "product",
            "product_name",
            "productDesc",
            "uom",
            "uom_code",
            "hsn_sac_code",
            "is_service",
            "qty",
            "free_qty",
            "rate",
            "is_rate_inclusive_of_tax",
            "discount_type",
            "discount_type_name",
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
            "gstRateAmount",   # ✅ NEW
            "line_total",
            "sales_account",
        ]
        read_only_fields = [
            "taxable_value",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "gstRateAmount",   # ✅ NEW
            "line_total",
        ]

    def get_gstRateAmount(self, obj) -> str:
        """
        Sum of GST tax amounts for the line.
        - For intra-state: CGST + SGST
        - For inter-state: IGST
        Returns as string to match DRF Decimal JSON behavior.
        """
        ZERO = Decimal("0.00")
        cgst = getattr(obj, "cgst_amount", None) or ZERO
        sgst = getattr(obj, "sgst_amount", None) or ZERO
        igst = getattr(obj, "igst_amount", None) or ZERO

        if igst > ZERO:
            return str(igst)

        return str(cgst + sgst)


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
    GSTIN_RE = re.compile(r"^[0-9A-Z]{15}$")
    # nested
    lines = SalesInvoiceLineSerializer(many=True, required=False)
    charges = SalesChargeLineSerializer(many=True, required=False)
    tax_summaries = SalesTaxSummarySerializer(many=True, read_only=True)
    einvoice_artifact = SalesEInvoiceArtifactReadSerializer(read_only=True)
    eway_artifact = SalesEWayArtifactReadSerializer(read_only=True)

    tcs_section = serializers.PrimaryKeyRelatedField(
        queryset=WithholdingSection.objects.filter(tax_type=WithholdingTaxType.TCS, is_active=True),
        required=False,
        allow_null=True,
    )

    # ✅ explicit FK field so null works cleanly
    shipping_detail = serializers.PrimaryKeyRelatedField(
        queryset=ShippingDetails.objects.all(),
        required=False,
        allow_null=True,
    )

    # display fields
    doc_type_name = serializers.CharField(source="get_doc_type_display", read_only=True)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    taxability_name = serializers.CharField(source="get_taxability_display", read_only=True)
    tax_regime_name = serializers.CharField(source="get_tax_regime_display", read_only=True)
    supply_category_name = serializers.CharField(source="get_supply_category_display", read_only=True)
    navigation = serializers.SerializerMethodField()
    customer_display_name = serializers.CharField(source="customer.effective_accounting_name", read_only=True)
    customer_accountcode = serializers.IntegerField(source="customer.effective_accounting_code", read_only=True)
    customer_ledger_id = serializers.IntegerField(read_only=True)
    customer_partytype = serializers.CharField(source="customer.partytype", read_only=True)

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
            "original_invoice",

            "status",
            "status_name",

            "bill_date",
            "posting_date",

            "credit_days",
            "due_date",

            "doc_code",

            "customer",
            "customer_name",
            "customer_display_name",
            "customer_accountcode",
            "customer_ledger_id",
            "customer_partytype",
            "customer_gstin",
            "customer_state_code",

            "is_bill_to_ship_to_same",
            "bill_to_address1",
            "bill_to_address2",
            "bill_to_city",
            "bill_to_state_code",
            "bill_to_pincode",

            "shipping_detail",

            "seller_gstin",
            "seller_state_code",
            "place_of_supply_state_code",
            "place_of_supply_pincode",

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
            "einvoice_applicable_manual",
            "eway_applicable_manual",
            "compliance_override_reason",
            "compliance_override_at",
            "compliance_override_by",

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

            "withholding_enabled",
            "tcs_section",
            "tcs_rate", "tcs_base_amount", "tcs_amount", "tcs_reason", "tcs_is_reversal",

            # nested
            "lines",
            "charges",
            "tax_summaries",
            "navigation",
            "einvoice_artifact",
            "eway_artifact",
        ]
        read_only_fields = [
            "status",
            "doc_no",
            "invoice_number",
            "posting_date",
            "due_date",
            "tax_regime",
            "is_igst",
            "gst_compliance_mode",
            "is_einvoice_applicable",
            "is_eway_applicable",

            # totals
            "total_taxable_value",
            "total_cgst",
            "total_sgst",
            "total_igst",
            "total_cess",
            "total_discount",
            "total_other_charges",
            "round_off",
            "grand_total",
            "settled_amount",
            "outstanding_amount",
            "settlement_status",
            "reversed_at",
            "reversed_by",
            "reverse_reason",
            "is_posting_reversed",
            "compliance_override_at",
            "compliance_override_by",

            # nav + summaries
            "tax_summaries",
            "navigation",
            "einvoice_artifact",
            "eway_artifact",
            "tcs_rate", "tcs_base_amount", "tcs_amount", "tcs_reason", "tcs_is_reversal",
        ]

    def get_navigation(self, obj):
        return SalesInvoiceNavService.get_prev_next_for_instance(obj)

    def validate(self, attrs):
        # hard-block backend-controlled fields if UI tries to push them
        blocked = {
            "status",
            "doc_no",
            "invoice_number",
            "posting_date",
            "due_date",
            "tax_regime",
            "is_igst",
            "gst_compliance_mode",
            "is_einvoice_applicable",
            "is_eway_applicable",
            "total_taxable_value",
            "total_cgst",
            "total_sgst",
            "total_igst",
            "total_cess",
            "total_discount",
            "total_other_charges",
            "round_off",
            "grand_total",
            "settled_amount",
            "outstanding_amount",
            "settlement_status",
            "reversed_at",
            "reversed_by",
            "reverse_reason",
            "is_posting_reversed",
        }

        incoming = set(getattr(self, "initial_data", {}).keys())
        bad = sorted(incoming.intersection(blocked))
        if bad:
            raise serializers.ValidationError({k: "Field is controlled by backend." for k in bad})

        for field in ("customer_gstin", "seller_gstin"):
            if field in attrs and attrs.get(field):
                val = str(attrs[field]).strip().upper()
                if not self.GSTIN_RE.fullmatch(val):
                    raise serializers.ValidationError({field: "GSTIN must be 15 uppercase alphanumeric characters."})
                attrs[field] = val

        if ("einvoice_applicable_manual" in attrs or "eway_applicable_manual" in attrs) and not (attrs.get("compliance_override_reason") or "").strip():
            raise serializers.ValidationError({"compliance_override_reason": "Required when manual compliance override is provided."})

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        lines = validated_data.pop("lines", [])
        charges = validated_data.pop("charges", [])

        if not lines:
            raise serializers.ValidationError({"lines": "At least one line is required."})

        # Pop scope as ids
        entity = validated_data.pop("entity", None)
        entityfinid = validated_data.pop("entityfinid", None)
        subentity = validated_data.pop("subentity", None)

        entity_id = int(entity.id if entity else request.data.get("entity"))
        entityfinid_id = int(entityfinid.id if entityfinid else request.data.get("entityfinid"))
        subentity_id = int(subentity.id) if subentity else None

        header = SalesInvoiceService.create_with_lines(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            header_data=validated_data,
            lines_data=lines,
            charges_data=charges,
            user=request.user,
        )
        return header

    def update(self, instance, validated_data):
        request = self.context["request"]
        lines = validated_data.pop("lines", None)
        charges = validated_data.pop("charges", None)

        # do not allow moving scope
        validated_data.pop("entity", None)
        validated_data.pop("entityfinid", None)
        validated_data.pop("subentity", None)

        header = SalesInvoiceService.update_with_lines(
            header=instance,
            header_data=validated_data,
            lines_data=lines,
            charges_data=charges,
            user=request.user,
        )
        return header
