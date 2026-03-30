from __future__ import annotations

from rest_framework import serializers
from financial.models import ShippingDetails
from withholding.models import WithholdingSection, WithholdingTaxType
from decimal import Decimal
import re



from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary
from sales.services.sales_nav_service import SalesInvoiceNavService

from sales.services.sales_invoice_service import SalesInvoiceService
from sales.services.sales_compliance_service import SalesComplianceService
from sales.services.sales_settings_service import SalesSettingsService
from financial.invoice_custom_fields_service import InvoiceCustomFieldService
from sales.serializers.sales_charge_serializers import SalesChargeLineSerializer
from sales.serializers.sales_compliance_serializers import (
    SalesEInvoiceArtifactReadSerializer,
    SalesEWayArtifactReadSerializer,
)



class SalesInvoiceLineSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
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
        extra_kwargs = {
            "cess_amount": {
                "help_text": "Provisional only. Backend recomputes when cess_percent > 0; manual cess survives only when cess_percent is 0."
            }
        }

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

    def get_product_name(self, obj) -> str:
        product = getattr(obj, "product", None)
        if product is not None and getattr(product, "productname", None):
            return str(product.productname)
        account_obj = getattr(obj, "sales_account", None)
        if account_obj is not None and getattr(account_obj, "accountname", None):
            return str(account_obj.accountname)
        return ""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not (data.get("productDesc") or "").strip():
            # Backward-compatible fallback for older rows where description was not saved.
            product_obj = getattr(instance, "product", None)
            fallback = getattr(product_obj, "productdesc", "") if product_obj is not None else ""
            data["productDesc"] = str(fallback or "")
        return data

    def validate(self, attrs):
        product = attrs.get("product", getattr(self.instance, "product", None))
        sales_account = attrs.get("sales_account", getattr(self.instance, "sales_account", None))
        is_service = attrs.get("is_service", getattr(self.instance, "is_service", None))
        product_desc = (attrs.get("productDesc", getattr(self.instance, "productDesc", "")) or "").strip()

        # Service-style line support:
        # allow no product, but enforce either service account mapping
        # or a product reference.
        if product is None:
            if sales_account is None:
                raise serializers.ValidationError(
                    {"sales_account": "sales_account is required when product is not provided."}
                )
            if not product_desc:
                raise serializers.ValidationError(
                    {"productDesc": "Description is required when product is not provided."}
                )
            attrs["is_service"] = True if is_service in (None, False) else bool(is_service)

        return attrs


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
    customer_partytype = serializers.CharField(source="customer.commercial_profile.partytype", read_only=True)
    custom_fields = serializers.JSONField(source="custom_fields_json", required=False)
    action_flags = serializers.SerializerMethodField()
    compliance_action_flags = serializers.SerializerMethodField()

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
            "ecm_gstin",
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
            "custom_fields",

            "withholding_enabled",
            "tcs_section",
            "tcs_rate", "tcs_base_amount", "tcs_amount", "tcs_reason", "tcs_is_reversal",

            # nested
            "lines",
            "charges",
            "tax_summaries",
            "navigation",
            "action_flags",
            "einvoice_artifact",
            "eway_artifact",
            "compliance_action_flags",
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
            "action_flags",
            "einvoice_artifact",
            "eway_artifact",
            "compliance_action_flags",
            "tcs_rate", "tcs_base_amount", "tcs_amount", "tcs_reason", "tcs_is_reversal",
        ]
        extra_kwargs = {
            "posting_date": {"help_text": "Derived by backend from bill date."},
            "due_date": {"help_text": "Derived by backend from bill date + credit days."},
            "tax_regime": {"help_text": "Derived by backend from seller state and place of supply."},
            "is_igst": {"help_text": "Derived by backend from tax regime determination."},
            "total_taxable_value": {"help_text": "Computed by backend from saved lines and charges."},
            "total_cgst": {"help_text": "Computed by backend from saved lines and charges."},
            "total_sgst": {"help_text": "Computed by backend from saved lines and charges."},
            "total_igst": {"help_text": "Computed by backend from saved lines and charges."},
            "total_cess": {"help_text": "Computed by backend from saved lines and charges."},
            "grand_total": {"help_text": "Computed by backend from saved lines and charges."},
        }

    def get_navigation(self, obj):
        return SalesInvoiceNavService.get_prev_next_for_instance(
            obj,
            line_mode=self.context.get("line_mode"),
        )

    def get_compliance_action_flags(self, obj):
        return SalesComplianceService.compliance_action_flags(obj)

    def get_action_flags(self, obj):
        policy = SalesSettingsService.get_policy(
            obj.entity_id,
            obj.subentity_id,
            entityfinid_id=getattr(obj, "entityfinid_id", None),
        )
        controls = policy.controls
        allow_edit_confirmed = str(controls.get("allow_edit_confirmed", "on")).lower().strip() == "on"
        allow_unpost_posted = str(controls.get("allow_unpost_posted", "on")).lower().strip() == "on"

        is_draft = int(obj.status) == int(SalesInvoiceHeader.Status.DRAFT)
        is_confirmed = int(obj.status) == int(SalesInvoiceHeader.Status.CONFIRMED)
        is_posted = int(obj.status) == int(SalesInvoiceHeader.Status.POSTED)
        is_cancelled = int(obj.status) == int(SalesInvoiceHeader.Status.CANCELLED)

        can_edit = is_draft or (is_confirmed and allow_edit_confirmed)
        return {
            "can_edit": can_edit and not is_cancelled,
            "can_confirm": is_draft,
            "can_post": is_confirmed,
            "can_cancel": is_draft or is_confirmed,
            "can_reverse": is_posted and allow_unpost_posted,
            "can_unpost": is_posted and allow_unpost_posted,
            "can_rebuild_tax_summary": not is_cancelled,
            "status": int(obj.status),
            "status_name": obj.get_status_display(),
        }

    def validate(self, attrs):
        # hard-block backend-controlled fields if UI tries to push them
        blocked = {
            "status",
            "doc_no",
            "invoice_number",
            "posting_date",
            "due_date",
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

        for field in ("customer_gstin", "seller_gstin", "ecm_gstin"):
            if field in attrs and attrs.get(field):
                val = str(attrs[field]).strip().upper()
                if not self.GSTIN_RE.fullmatch(val):
                    raise serializers.ValidationError({field: "GSTIN must be 15 uppercase alphanumeric characters."})
                attrs[field] = val

        if ("einvoice_applicable_manual" in attrs or "eway_applicable_manual" in attrs) and not (attrs.get("compliance_override_reason") or "").strip():
            raise serializers.ValidationError({"compliance_override_reason": "Required when manual compliance override is provided."})

        line_mode = self.context.get("line_mode")
        if line_mode in ("service", "goods"):
            lines_for_mode_check = attrs.get("lines")
            if lines_for_mode_check is None:
                lines_for_mode_check = (getattr(self, "initial_data", {}) or {}).get("lines") or []
            for idx, row in enumerate(lines_for_mode_check or [], start=1):
                # For service mode, treat account-only lines as service even if client omitted is_service.
                product_id = row.get("product")
                has_account = row.get("sales_account") not in (None, "", 0)
                inferred_service = (product_id in (None, "", 0)) and has_account
                is_service = bool(row.get("is_service")) or inferred_service
                if line_mode == "service" and not is_service:
                    raise serializers.ValidationError({"lines": [f"Line {idx}: service invoice accepts only service lines."]})
                if line_mode == "goods" and is_service:
                    raise serializers.ValidationError({"lines": [f"Line {idx}: goods invoice accepts only goods lines."]})

        if "custom_fields_json" in attrs:
            entity = attrs.get("entity") or getattr(self.instance, "entity", None)
            subentity = attrs.get("subentity") or getattr(self.instance, "subentity", None)
            customer = attrs.get("customer") or getattr(self.instance, "customer", None)
            if entity:
                try:
                    attrs["custom_fields_json"] = InvoiceCustomFieldService.validate_payload(
                        entity_id=int(getattr(entity, "id", entity)),
                        module="sales_invoice",
                        payload=attrs.get("custom_fields_json") or {},
                        subentity_id=int(getattr(subentity, "id", subentity)) if subentity else None,
                        party_account_id=int(getattr(customer, "id", customer)) if customer else None,
                    )
                except ValueError as ex:
                    raise serializers.ValidationError({"custom_fields": str(ex)})

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
