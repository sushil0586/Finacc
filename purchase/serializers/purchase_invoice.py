from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService

from purchase.models.purchase_core import (
    PurchaseInvoiceHeader,
    PurchaseInvoiceLine,
    Taxability,
    TaxRegime,
    Status,
)
from purchase.services.purchase_settings_service import PurchaseSettingsService
from purchase.services.purchase_invoice_actions import PurchaseInvoiceActions
from purchase.services.purchase_invoice_service import PurchaseInvoiceService

DEC2 = Decimal("0.01")
DEC4 = Decimal("0.0001")


def q2(x) -> Decimal:
    return (Decimal(x or 0)).quantize(DEC2, rounding=ROUND_HALF_UP)


def q4(x) -> Decimal:
    return (Decimal(x or 0)).quantize(DEC4, rounding=ROUND_HALF_UP)


class PurchaseInvoiceLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = PurchaseInvoiceLine
        fields = [
            "id",
            "line_no",
            "product",
            "product_desc",
            "is_service",
            "hsn_sac",
            "uom",
            "qty",
            "rate",
            "taxability",
            "taxable_value",
            "gst_rate",
            "cgst_percent",
            "sgst_percent",
            "igst_percent",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "cess_amount",
            "line_total",
            "is_itc_eligible",
            "itc_block_reason",
        ]

    def validate(self, attrs):
        qty = q4(attrs.get("qty"))
        rate = q2(attrs.get("rate"))
        taxable_value = q2(attrs.get("taxable_value"))

        if qty <= 0:
            raise serializers.ValidationError({"qty": "Qty must be > 0"})
        if rate < 0:
            raise serializers.ValidationError({"rate": "Rate cannot be negative"})

        expected_taxable = q2(q2(qty) * rate)
        if taxable_value not in (Decimal("0.00"), expected_taxable):
            raise serializers.ValidationError({"taxable_value": f"Expected {expected_taxable} from qty*rate."})

        # Exempt/Nil/NonGST => ITC false (line-level)
        taxability = attrs.get("taxability", Taxability.TAXABLE)
        if taxability in (Taxability.EXEMPT, Taxability.NIL_RATED, Taxability.NON_GST):
            if bool(attrs.get("is_itc_eligible", True)):
                raise serializers.ValidationError({"is_itc_eligible": "Not allowed for Exempt/Nil/Non-GST line."})

        # If ITC is blocked, reason should exist
        if attrs.get("is_itc_eligible") is False:
            if not (attrs.get("itc_block_reason") or "").strip():
                # don't force for all cases, but good governance
                attrs["itc_block_reason"] = attrs.get("itc_block_reason") or "ITC not eligible"

        return attrs


class PurchaseInvoiceHeaderSerializer(serializers.ModelSerializer):
    # ✅ nested lines
    lines = PurchaseInvoiceLineSerializer(many=True, required=False)

    # preview fields
    preview_doc_no = serializers.SerializerMethodField()
    preview_purchase_number = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseInvoiceHeader
        fields = [
            "id",
            "doc_type",
            "bill_date",
            "doc_code",
            "doc_no",
            "purchase_number",

            "supplier_invoice_number",
            "supplier_invoice_date",
            "ref_document",

            "vendor",
            "vendor_name",
            "vendor_gstin",
            "vendor_state",

            "supply_category",
            "default_taxability",
            "tax_regime",
            "is_igst",

            "supplier_state",
            "place_of_supply_state",

            "is_reverse_charge",
            "is_itc_eligible",
            "itc_block_reason",

            "total_taxable",
            "total_cgst",
            "total_sgst",
            "total_igst",
            "total_cess",
            "total_gst",
            "round_off",
            "grand_total",

            "status",
            "entity",
            "entityfinid",
            "subentity",

            "preview_doc_no",
            "preview_purchase_number",

            "lines",
        ]

        extra_kwargs = {
            "status": {"read_only": True},
            "doc_no": {"required": False, "allow_null": True},
            "purchase_number": {"required": False, "allow_null": True},
            # totals are computed, not client-editable
            "total_taxable": {"required": False},
            "total_cgst": {"required": False},
            "total_sgst": {"required": False},
            "total_igst": {"required": False},
            "total_cess": {"required": False},
            "total_gst": {"required": False},
            "grand_total": {"required": False},
        }

    # ----------------------------
    # 🔢 Number Series – PREVIEW
    # ----------------------------

    def _get_document_type_id(self, obj) -> int:
        dt = DocumentType.objects.filter(
            module="purchase",
            default_code=obj.doc_code,
            is_active=True,
        ).first()
        if not dt:
            raise serializers.ValidationError(f"DocumentType not found for purchase doc_code={obj.doc_code}")
        return dt.id

    def get_preview_doc_no(self, obj):
        if obj.doc_no:
            return obj.doc_no
        try:
            dt_id = self._get_document_type_id(obj)
            res = DocumentNumberService.peek_preview(
                entity_id=obj.entity_id,
                entityfinid_id=obj.entityfinid_id,
                subentity_id=obj.subentity_id,
                doc_type_id=dt_id,
                doc_code=obj.doc_code,
                on_date=obj.bill_date,
            )
            return res.doc_no
        except Exception:
            return None

    def get_preview_purchase_number(self, obj):
        if obj.purchase_number:
            return obj.purchase_number
        try:
            dt_id = self._get_document_type_id(obj)
            res = DocumentNumberService.peek_preview(
                entity_id=obj.entity_id,
                entityfinid_id=obj.entityfinid_id,
                subentity_id=obj.subentity_id,
                doc_type_id=dt_id,
                doc_code=obj.doc_code,
                on_date=obj.bill_date,
            )
            return res.display_no
        except Exception:
            return None

    # ----------------------------
    # Header-level validations
    # ----------------------------

    def validate(self, attrs):
        # For update, merge instance values to validate consistently
        inst = getattr(self, "instance", None)

        entity_id = attrs.get("entity") or getattr(inst, "entity_id", None)
        subentity_id = attrs.get("subentity") or getattr(inst, "subentity_id", None)
        bill_date = attrs.get("bill_date") or getattr(inst, "bill_date", None)

        if inst and inst.status in (Status.POSTED, Status.CANCELLED):
            raise serializers.ValidationError("Cannot edit a POSTED or CANCELLED purchase document.")

        # Lock period validation (create + update)
        if entity_id and bill_date:
            PurchaseInvoiceService.assert_not_locked(
                entity_id=entity_id.id if hasattr(entity_id, "id") else entity_id,
                subentity_id=subentity_id.id if hasattr(subentity_id, "id") else subentity_id,
                bill_date=bill_date,
            )

        # GST regime consistency
        is_igst = attrs.get("is_igst", getattr(inst, "is_igst", False))
        tax_regime = attrs.get("tax_regime", getattr(inst, "tax_regime", None))
        if tax_regime == TaxRegime.INTER and not is_igst:
            raise serializers.ValidationError({"is_igst": "For Inter-state (IGST) regime, is_igst must be true."})
        if tax_regime == TaxRegime.INTRA and is_igst:
            raise serializers.ValidationError({"is_igst": "For Intra-state (CGST+SGST) regime, is_igst must be false."})

        # ITC header: if not eligible, require reason
        is_itc_eligible = attrs.get("is_itc_eligible", getattr(inst, "is_itc_eligible", True))
        if is_itc_eligible is False:
            if not (attrs.get("itc_block_reason") or getattr(inst, "itc_block_reason", "")).strip():
                attrs["itc_block_reason"] = "Not ITC eligible"

        # Mixed taxability rule (optional) - if settings disallow mixed, enforce in create/update
        lines = attrs.get("lines", None)
        if lines is not None and entity_id:
            ent_id = entity_id.id if hasattr(entity_id, "id") else entity_id
            sub_id = subentity_id.id if hasattr(subentity_id, "id") else subentity_id
            policy = PurchaseSettingsService.get_policy(ent_id, sub_id)
            if not policy.allow_mixed_taxability:
                taxabilities = {ln.get("taxability", Taxability.TAXABLE) for ln in lines}
                if len(taxabilities) > 1:
                    raise serializers.ValidationError({"lines": "Mixed taxability in one bill is disabled for this entity."})

        return attrs

    # ----------------------------
    # Create / Update with default workflow action
    # ----------------------------

    def create(self, validated_data):
        # service handles header + lines + totals + summary
        header = PurchaseInvoiceService.create_with_lines(validated_data)

        # Apply entity default action
        policy = PurchaseSettingsService.get_policy(header.entity_id, header.subentity_id)

        if policy.default_action == "confirm":
            PurchaseInvoiceActions.confirm(header.pk)
        elif policy.default_action == "post":
            PurchaseInvoiceActions.confirm(header.pk)
            PurchaseInvoiceActions.post(header.pk)

        header.refresh_from_db()
        return header

    def update(self, instance, validated_data):
        updated = PurchaseInvoiceService.update_with_lines(instance, validated_data)

        # Optional: if entity wants auto-confirm/auto-post even on update:
        # Usually we DO NOT auto-post on update, but if you want it, you can keep same logic.
        policy = PurchaseSettingsService.get_policy(updated.entity_id, updated.subentity_id)

        # If still draft and entity default is confirm/post, you can auto-confirm after update.
        if updated.status == Status.DRAFT:
            if policy.default_action == "confirm":
                PurchaseInvoiceActions.confirm(updated.pk)
            elif policy.default_action == "post":
                PurchaseInvoiceActions.confirm(updated.pk)
                PurchaseInvoiceActions.post(updated.pk)

        updated.refresh_from_db()
        return updated
