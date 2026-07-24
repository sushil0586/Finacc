from __future__ import annotations

from rest_framework import serializers
from financial.models import ShippingDetails
from withholding.models import WithholdingSection, WithholdingTaxType
from decimal import Decimal
import re


from entity.models import Godown
from entity.financial_year_validation import assert_document_date_within_financial_year
from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary
from catalog.taxability import resolve_product_default_taxability
from sales.services.sales_nav_service import SalesInvoiceNavService

from sales.services.sales_invoice_service import SalesInvoiceService
from sales.services.sales_compliance_service import SalesComplianceService
from sales.services.sales_settings_service import SalesSettingsService
from helpers.utils.document_actions import build_document_action_flags
from financial.invoice_custom_fields_service import InvoiceCustomFieldService
from sales.serializers.sales_charge_serializers import SalesChargeLineSerializer
from sales.serializers.sales_attachment import SalesAttachmentSerializer
from sales.serializers.sales_compliance_serializers import (
    SalesEInvoiceArtifactReadSerializer,
    SalesEWayArtifactReadSerializer,
)


def _sales_lookup_identity(obj: SalesInvoiceHeader) -> str:
    invoice_number = str(getattr(obj, "invoice_number", "") or "").strip()
    if invoice_number:
        return invoice_number
    reference = str(getattr(obj, "reference", "") or "").strip()
    if reference:
        return reference
    object_id = getattr(obj, "id", None)
    if object_id not in (None, "", 0, "0"):
        return f"DRAFT-{object_id}"
    return ""



class SalesInvoiceLineSerializer(serializers.ModelSerializer):
    productDesc = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=200)
    batch_number = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=80)
    hsn_sac_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    product_name = serializers.SerializerMethodField()
    uom_code = serializers.CharField(source="uom.code", read_only=True)
    taxability_name = serializers.CharField(source="get_taxability_display", read_only=True)

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
            "batch_number",
            "manufacture_date",
            "expiry_date",
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
            "taxability",
            "taxability_name",
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
            },
            "batch_number": {"help_text": "Optional batch number for batch-managed products."},
            "manufacture_date": {"help_text": "Optional manufacture date for batch-managed products."},
            "expiry_date": {"help_text": "Optional expiry date for expiry-tracked products."},
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
        else:
            if attrs.get("taxability") in (None, ""):
                attrs["taxability"] = resolve_product_default_taxability(product=product)
            batch_number = (attrs.get("batch_number") or "").strip()
            manufacture_date = attrs.get("manufacture_date")
            expiry_date = attrs.get("expiry_date")
            if bool(getattr(product, "is_batch_managed", False)) and not batch_number:
                raise serializers.ValidationError({"batch_number": "Batch number is required for batch-managed products."})
            if bool(getattr(product, "is_expiry_tracked", False)) and expiry_date in (None, ""):
                raise serializers.ValidationError({"expiry_date": "Expiry date is required for expiry-tracked products."})
            if manufacture_date and expiry_date and manufacture_date > expiry_date:
                raise serializers.ValidationError({"expiry_date": "Expiry date must be on or after manufacture date."})

        taxability = int(
            attrs.get(
                "taxability",
                getattr(self.instance, "taxability", SalesInvoiceHeader.Taxability.TAXABLE),
            )
        )
        gst_rate = Decimal(str(attrs.get("gst_rate", getattr(self.instance, "gst_rate", "0.00")) or "0.00"))
        cess_percent = Decimal(str(attrs.get("cess_percent", getattr(self.instance, "cess_percent", "0.00")) or "0.00"))
        cess_amount = Decimal(str(attrs.get("cess_amount", getattr(self.instance, "cess_amount", "0.00")) or "0.00"))
        if taxability != int(SalesInvoiceHeader.Taxability.TAXABLE):
            if gst_rate > Decimal("0.00"):
                raise serializers.ValidationError({"gst_rate": "Must be 0 for non-taxable line."})
            if cess_percent > Decimal("0.00"):
                raise serializers.ValidationError({"cess_percent": "Must be 0 for non-taxable line."})
            if cess_amount > Decimal("0.00"):
                raise serializers.ValidationError({"cess_amount": "Must be 0 for non-taxable line."})

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


class SalesInvoiceListSerializer(serializers.ModelSerializer):
    doc_type_name = serializers.CharField(source="get_doc_type_display", read_only=True)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    customer_display_name = serializers.CharField(source="customer.effective_accounting_name", read_only=True)
    customer_accountcode = serializers.IntegerField(source="customer.effective_accounting_code", read_only=True)
    accountname = serializers.CharField(source="customer.accountname", read_only=True)
    invoice_date = serializers.DateField(source="bill_date", read_only=True)
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True)
    branch_name = serializers.CharField(source="subentity.subentityname", read_only=True)
    total_value = serializers.SerializerMethodField()

    class Meta:
        model = SalesInvoiceHeader
        fields = [
            "id",
            "is_legacy_imported",
            "legacy_source_system",
            "legacy_source_key",
            "legacy_import_mode",
            "doc_code",
            "doc_type_name",
            "invoice_number",
            "status_name",
            "customer_name",
            "customer_display_name",
            "customer_accountcode",
            "accountname",
            "bill_date",
            "invoice_date",
            "grand_total",
            "total_value",
            "outstanding_amount",
            "subentity_name",
            "branch_name",
            "location",
        ]

    def get_total_value(self, obj) -> Decimal:
        return getattr(obj, "grand_total", None) or Decimal("0.00")


class SalesInvoiceLookupSerializer(serializers.ModelSerializer):
    doc_type_name = serializers.CharField(source="get_doc_type_display", read_only=True)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    customer_display_name = serializers.CharField(source="customer.effective_accounting_name", read_only=True)
    accountname = serializers.CharField(source="customer.accountname", read_only=True)
    invoice_date = serializers.DateField(source="bill_date", read_only=True)
    total_value = serializers.SerializerMethodField()
    subentity_name = serializers.CharField(source="subentity.subentityname", read_only=True)
    branch_name = serializers.CharField(source="subentity.subentityname", read_only=True)
    lookup_identity = serializers.SerializerMethodField()

    class Meta:
        model = SalesInvoiceHeader
        fields = [
            "id",
            "doc_no",
            "doc_code",
            "doc_type",
            "doc_type_name",
            "invoice_number",
            "reference",
            "lookup_identity",
            "status",
            "status_name",
            "customer_name",
            "customer_display_name",
            "accountname",
            "bill_date",
            "invoice_date",
            "grand_total",
            "total_value",
            "outstanding_amount",
            "subentity_name",
            "branch_name",
        ]

    def get_total_value(self, obj) -> Decimal:
        return getattr(obj, "grand_total", None) or Decimal("0.00")

    def get_lookup_identity(self, obj) -> str:
        return _sales_lookup_identity(obj)


class SalesInvoiceHeaderSerializer(serializers.ModelSerializer):
    GSTIN_RE = re.compile(r"^[0-9A-Z]{15}$")
    # nested
    lines = SalesInvoiceLineSerializer(many=True, required=False)
    charges = SalesChargeLineSerializer(many=True, required=False)
    tax_summaries = SalesTaxSummarySerializer(many=True, read_only=True)
    einvoice_artifact = SalesEInvoiceArtifactReadSerializer(read_only=True)
    eway_artifact = SalesEWayArtifactReadSerializer(read_only=True)
    attachments = SalesAttachmentSerializer(many=True, read_only=True)

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
    credit_days = serializers.IntegerField(required=False, allow_null=True, max_value=2147483647)
    doc_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    customer_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    customer_gstin = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=15)
    customer_state_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=2)
    bill_to_address1 = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    bill_to_address2 = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    bill_to_city = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    bill_to_state_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=2)
    bill_to_pincode = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=10)
    seller_gstin = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=15)
    ecm_gstin = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=15)
    seller_state_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=2)
    location = serializers.PrimaryKeyRelatedField(queryset=Godown.objects.all(), required=False, allow_null=True)
    place_of_supply_state_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=2)
    place_of_supply_pincode = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=8)
    compliance_override_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    reference = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    legacy_source_system = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    legacy_source_key = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    legacy_import_mode = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=30)

    # display fields
    doc_type_name = serializers.CharField(source="get_doc_type_display", read_only=True)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    taxability_name = serializers.CharField(source="get_taxability_display", read_only=True)
    tax_regime_name = serializers.CharField(source="get_tax_regime_display", read_only=True)
    supply_category_name = serializers.CharField(source="get_supply_category_display", read_only=True)
    navigation = serializers.SerializerMethodField()
    lookup_identity = serializers.SerializerMethodField()
    customer_display_name = serializers.CharField(source="customer.effective_accounting_name", read_only=True)
    customer_accountcode = serializers.IntegerField(source="customer.effective_accounting_code", read_only=True)
    customer_ledger_id = serializers.IntegerField(read_only=True)
    customer_partytype = serializers.CharField(source="customer.commercial_profile.partytype", read_only=True)
    custom_fields = serializers.JSONField(source="custom_fields_json", required=False)
    action_flags = serializers.SerializerMethodField()
    compliance_action_flags = serializers.SerializerMethodField()

    @staticmethod
    def _merge_client_line_amount_fields(validated_lines, raw_lines):
        if not isinstance(validated_lines, list) or not isinstance(raw_lines, list):
            return validated_lines

        amount_fields = (
            "taxable_value",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "cess_amount",
            "line_total",
        )
        raw_by_id = {}
        raw_by_line_no = {}
        for raw in raw_lines:
            if not isinstance(raw, dict):
                continue
            raw_id = raw.get("id")
            raw_line_no = raw.get("line_no")
            if raw_id not in (None, "", 0, "0"):
                raw_by_id[str(raw_id)] = raw
            if raw_line_no not in (None, "", 0, "0"):
                raw_by_line_no[str(raw_line_no)] = raw

        for idx, row in enumerate(validated_lines):
            if not isinstance(row, dict):
                continue
            matched_raw = None
            row_id = row.get("id")
            row_line_no = row.get("line_no")
            if row_id not in (None, "", 0, "0"):
                matched_raw = raw_by_id.get(str(row_id))
            if matched_raw is None and row_line_no not in (None, "", 0, "0"):
                matched_raw = raw_by_line_no.get(str(row_line_no))
            if matched_raw is None and idx < len(raw_lines) and isinstance(raw_lines[idx], dict):
                matched_raw = raw_lines[idx]
            if not isinstance(matched_raw, dict):
                continue
            for field_name in amount_fields:
                if field_name in matched_raw and field_name not in row:
                    row[field_name] = matched_raw[field_name]
        return validated_lines

    class Meta:
        model = SalesInvoiceHeader
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "location",

            "doc_type",
            "doc_type_name",
            "doc_no",
            "invoice_number",
            "lookup_identity",
            "original_invoice",
            "note_reason",
            "affects_inventory",

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
            "is_legacy_imported",
            "legacy_source_system",
            "legacy_source_key",
            "legacy_import_mode",
            "legacy_behavior_flags",

            "withholding_enabled",
            "tcs_section",
            "tcs_rate", "tcs_base_amount", "tcs_amount", "tcs_reason", "tcs_is_reversal",

            # nested
            "lines",
            "charges",
            "tax_summaries",
            "attachments",
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
            "settled_amount",
            "outstanding_amount",
            "settlement_status",
            "reversed_at",
            "reversed_by",
            "reverse_reason",
            "is_posting_reversed",
            "compliance_override_at",
            "compliance_override_by",
            "is_legacy_imported",
            "legacy_source_system",
            "legacy_source_key",
            "legacy_import_mode",
            "legacy_behavior_flags",

            # nav + summaries
            "tax_summaries",
            "attachments",
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

    def get_lookup_identity(self, obj) -> str:
        return _sales_lookup_identity(obj)

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
        delete_allowed = False
        if not is_cancelled:
            if policy.delete_policy == "draft_only":
                delete_allowed = is_draft
            elif policy.delete_policy == "non_posted":
                delete_allowed = not is_posted

        return build_document_action_flags(
            status_value=int(obj.status),
            draft_status=int(SalesInvoiceHeader.Status.DRAFT),
            confirmed_status=int(SalesInvoiceHeader.Status.CONFIRMED),
            posted_status=int(SalesInvoiceHeader.Status.POSTED),
            cancelled_status=int(SalesInvoiceHeader.Status.CANCELLED),
            status_name=obj.get_status_display(),
            allow_edit_confirmed=allow_edit_confirmed,
            allow_unpost_posted=allow_unpost_posted,
            include_reverse=True,
            include_rebuild_tax_summary=True,
            can_delete=delete_allowed,
            extra={"can_post": is_draft or is_confirmed},
        )

    def get_validators(self):
        validators = super().get_validators()
        # The legacy-source unique constraint is conditional at the DB layer and
        # should only apply when both optional fields are actually provided.
        # DRF's generated UniqueTogetherValidator makes those fields required on
        # every normal invoice create/update, which breaks non-legacy flows.
        return [
            validator
            for validator in validators
            if getattr(validator, "fields", ()) != ("entity", "legacy_source_system", "legacy_source_key")
        ]

    def validate(self, attrs):
        # Normalize nullable char inputs sent by frontend as null so model-level
        # CharField(blank=True, default="") can persist safely.
        for field in ("place_of_supply_state_code", "place_of_supply_pincode"):
            if field in attrs and attrs[field] is None:
                attrs[field] = ""

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

        # note_reason / affects_inventory are only meaningful on CN/DN
        inst = self.instance
        entity = attrs.get("entity") or getattr(inst, "entity", None)
        entityfinid = attrs.get("entityfinid") or getattr(inst, "entityfinid", None)
        bill_date = attrs.get("bill_date") or getattr(inst, "bill_date", None)
        posting_date = attrs.get("posting_date") or getattr(inst, "posting_date", None)

        try:
            assert_document_date_within_financial_year(
                entity=entity,
                entityfinid=entityfinid,
                document_date=bill_date,
                field_name="bill_date",
            )
            assert_document_date_within_financial_year(
                entity=entity,
                entityfinid=entityfinid,
                document_date=posting_date,
                field_name="posting_date",
            )
        except ValueError as ex:
            payload = ex.args[0] if ex.args else str(ex)
            raise serializers.ValidationError(payload if isinstance(payload, dict) else {"non_field_errors": [str(payload)]})

        doc_type = attrs.get("doc_type") or getattr(inst, "doc_type", None)
        note_reason = attrs.get("note_reason") or getattr(inst, "note_reason", None)
        affects_inventory_provided = "affects_inventory" in attrs
        is_note = doc_type in (
            SalesInvoiceHeader.DocType.CREDIT_NOTE,
            SalesInvoiceHeader.DocType.DEBIT_NOTE,
        )
        if not is_note:
            attrs["note_reason"] = None
            attrs["affects_inventory"] = False
        elif note_reason:
            if note_reason == SalesInvoiceHeader.NoteReason.QUANTITY_RETURN:
                attrs["affects_inventory"] = True
            elif note_reason == SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE:
                attrs["affects_inventory"] = False
            else:
                if affects_inventory_provided:
                    attrs["affects_inventory"] = bool(attrs.get("affects_inventory"))
                elif "note_reason" in attrs:
                    attrs["affects_inventory"] = False
                else:
                    attrs["affects_inventory"] = bool(getattr(inst, "affects_inventory", False))
        elif "note_reason" in attrs:
            attrs["affects_inventory"] = False

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

        lines = attrs.get("lines")
        if lines is not None and entity:
            entity_id = int(getattr(entity, "id", entity))
            subentity = attrs.get("subentity") or getattr(self.instance, "subentity", None)
            subentity_id = int(getattr(subentity, "id", subentity)) if subentity else None
            policy = SalesSettingsService.get_policy(
                entity_id,
                subentity_id,
                entityfinid_id=int(getattr(entityfinid, "id", entityfinid)) if entityfinid else None,
            )
            if not policy.allow_mixed_taxability:
                header_taxability = int(
                    attrs.get("taxability", getattr(self.instance, "taxability", SalesInvoiceHeader.Taxability.TAXABLE))
                )
                line_taxabilities = {
                    int(
                        row.get("taxability")
                        or resolve_product_default_taxability(
                            product=row.get("product") if hasattr(row.get("product"), "_meta") else None,
                            product_id=getattr(row.get("product"), "pk", row.get("product")),
                            fallback=header_taxability,
                        )
                    )
                    for row in lines
                }
                if len(line_taxabilities) > 1:
                    raise serializers.ValidationError({"lines": "Mixed taxability in one invoice is disabled for this entity."})

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
        raw_lines = request.data.get("lines", []) if isinstance(getattr(request, "data", None), dict) else []
        lines = self._merge_client_line_amount_fields(lines, raw_lines)

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
        raw_lines = request.data.get("lines", None) if isinstance(getattr(request, "data", None), dict) else None
        if lines is not None:
            lines = self._merge_client_line_amount_fields(lines, raw_lines)

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
