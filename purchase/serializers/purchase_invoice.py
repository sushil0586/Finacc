from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers

from withholding.models import WithholdingSection, WithholdingTaxType

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService

from purchase.models.purchase_core import (
    PurchaseInvoiceHeader,
    PurchaseInvoiceLine,
    Taxability,
    TaxRegime,
    Status,
)
from purchase.serializers.purchase_charge import PurchaseChargeLineSerializer
from purchase.services.purchase_invoice_actions import PurchaseInvoiceActions
from purchase.services.purchase_invoice_nav_service import PurchaseInvoiceNavService
from purchase.services.purchase_invoice_service import PurchaseInvoiceService
from purchase.services.purchase_settings_service import PurchaseSettingsService
from financial.invoice_custom_fields_service import InvoiceCustomFieldService


DEC2 = Decimal("0.01")
DEC4 = Decimal("0.0001")

ZERO2 = Decimal("0.00")

TDS_TOLERANCE = Decimal("0.02")      # 2 paisa tolerance
GST_TDS_TOLERANCE = Decimal("0.02")  # 2 paisa tolerance

RATE_TOTAL = Decimal("2.0000")   # GST-TDS total 2%
RATE_HALF  = Decimal("1.0000")   # GST-TDS half 1%


def q2(x) -> Decimal:
    return (Decimal(x or 0)).quantize(DEC2, rounding=ROUND_HALF_UP)


def q4(x) -> Decimal:
    return (Decimal(x or 0)).quantize(DEC4, rounding=ROUND_HALF_UP)


class PurchaseInvoiceLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    product_name = serializers.CharField(source="product.productname", read_only=True)
    uom_code = serializers.CharField(source="uom.code", read_only=True)
    taxability_name = serializers.CharField(source="get_taxability_display", read_only=True)

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

            # display (read-only)
            "product_name",
            "uom_code",
            "taxability_name",

            "qty",
            "free_qty",

            "rate",
            "is_rate_inclusive_of_tax",

            "discount_type",
            "discount_percent",
            "discount_amount",

            "taxability",
            "taxable_value",
            "gst_rate",

            "cgst_percent",
            "sgst_percent",
            "igst_percent",

            "cgst_amount",
            "sgst_amount",
            "igst_amount",

            "cess_percent",
            "cess_amount",

            "line_total",
            "is_itc_eligible",
            "itc_block_reason",
        ]
        extra_kwargs = {
            "taxable_value": {"help_text": "Computed by backend from qty, rate, discount, taxability, and regime."},
            "cgst_amount": {"help_text": "Computed by backend from tax regime and taxable value."},
            "sgst_amount": {"help_text": "Computed by backend from tax regime and taxable value."},
            "igst_amount": {"help_text": "Computed by backend from tax regime and taxable value."},
            "cess_amount": {"help_text": "Computed by backend from cess percent and taxable value."},
            "line_total": {"help_text": "Computed by backend from taxable value, GST, and cess."},
            "itc_block_reason": {"help_text": "Backend may auto-fill when ITC is not eligible."},
        }

    def validate(self, attrs):
        qty = q4(attrs.get("qty"))
        rate = q2(attrs.get("rate"))

        if qty <= 0:
            raise serializers.ValidationError({"qty": "Qty must be > 0"})
        if rate < 0:
            raise serializers.ValidationError({"rate": "Rate cannot be negative"})

        free_qty = q4(attrs.get("free_qty"))
        if free_qty < 0:
            raise serializers.ValidationError({"free_qty": "Free qty cannot be negative"})

        # Exempt/Nil/NonGST => ITC false (line-level)
        taxability = attrs.get("taxability", Taxability.TAXABLE)
        if taxability in (Taxability.EXEMPT, Taxability.NIL_RATED, Taxability.NON_GST):
            if bool(attrs.get("is_itc_eligible", True)):
                raise serializers.ValidationError({"is_itc_eligible": "Not allowed for Exempt/Nil/Non-GST line."})

        # If ITC is blocked, ensure reason
        if attrs.get("is_itc_eligible") is False:
            if not (attrs.get("itc_block_reason") or "").strip():
                attrs["itc_block_reason"] = attrs.get("itc_block_reason") or "ITC not eligible"

        dt = attrs.get("discount_type", PurchaseInvoiceLine.DiscountType.NONE)
        disc_pct = q2(attrs.get("discount_percent"))
        disc_amt = q2(attrs.get("discount_amount"))

        if dt == PurchaseInvoiceLine.DiscountType.PERCENT:
            if disc_pct < 0 or disc_pct > 100:
                raise serializers.ValidationError({"discount_percent": "Discount percent must be between 0 and 100."})
            attrs["discount_amount"] = q2(0)
        elif dt == PurchaseInvoiceLine.DiscountType.AMOUNT:
            if disc_amt < 0:
                raise serializers.ValidationError({"discount_amount": "Discount amount cannot be negative."})
            attrs["discount_percent"] = q2(0)
        else:
            attrs["discount_percent"] = q2(0)
            attrs["discount_amount"] = q2(0)

        cess_percent = q2(attrs.get("cess_percent"))
        if cess_percent < 0 or cess_percent > 100:
            raise serializers.ValidationError({"cess_percent": "Cess percent must be between 0 and 100."})

        # NOTE:
        # taxable_value validation is risky if you allow discounts/inclusive pricing.
        # Keep only a mild sanity check (non-negative) here.
        taxable_value = q2(attrs.get("taxable_value"))
        if taxable_value < ZERO2:
            raise serializers.ValidationError({"taxable_value": "Taxable value cannot be negative."})

        return attrs


class PurchaseInvoiceHeaderSerializer(serializers.ModelSerializer):
    lines = PurchaseInvoiceLineSerializer(many=True, required=False)
    charges = PurchaseChargeLineSerializer(many=True, required=False)
    custom_fields = serializers.JSONField(source="custom_fields_json", required=False)
    vendor_display_name = serializers.CharField(source="vendor.effective_accounting_name", read_only=True)
    vendor_accountcode = serializers.IntegerField(source="vendor.effective_accounting_code", read_only=True)
    vendor_ledger_id = serializers.SerializerMethodField()
    vendor_partytype = serializers.CharField(source="vendor.commercial_profile.partytype", read_only=True)

    tds_section = serializers.PrimaryKeyRelatedField(
        queryset=WithholdingSection.objects.filter(tax_type=WithholdingTaxType.TDS, is_active=True),
        required=False,
        allow_null=True,
    )

    preview_doc_no = serializers.SerializerMethodField()
    preview_purchase_number = serializers.SerializerMethodField()

    def get_vendor_ledger_id(self, obj):
        return getattr(obj, "vendor_ledger_id", None) or getattr(getattr(obj, "vendor_ledger", None), "id", None)
    status_name = serializers.SerializerMethodField()

    gst_tds_cgst_rate = serializers.SerializerMethodField()
    gst_tds_sgst_rate = serializers.SerializerMethodField()
    gst_tds_igst_rate = serializers.SerializerMethodField()

    def get_status_name(self, obj):
        return obj.get_status_display()

    def get_gst_tds_cgst_rate(self, obj):
        if not getattr(obj, "gst_tds_enabled", False):
            return "0.0000"
        is_inter = (int(getattr(obj, "tax_regime", 1)) == int(obj.TaxRegime.INTER)) or bool(getattr(obj, "is_igst", False))
        return "0.0000" if is_inter else str(q4(RATE_HALF))

    def get_gst_tds_sgst_rate(self, obj):
        if not getattr(obj, "gst_tds_enabled", False):
            return "0.0000"
        is_inter = (int(getattr(obj, "tax_regime", 1)) == int(obj.TaxRegime.INTER)) or bool(getattr(obj, "is_igst", False))
        return "0.0000" if is_inter else str(q4(RATE_HALF))

    def get_gst_tds_igst_rate(self, obj):
        if not getattr(obj, "gst_tds_enabled", False):
            return "0.0000"
        is_inter = (int(getattr(obj, "tax_regime", 1)) == int(obj.TaxRegime.INTER)) or bool(getattr(obj, "is_igst", False))
        return str(q4(RATE_TOTAL)) if is_inter else "0.0000"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get("skip_navigation", False):
            data["navigation"] = PurchaseInvoiceNavService.get_prev_next_for_instance(instance)
        return data

    class Meta:
        model = PurchaseInvoiceHeader
        fields = [
            "id",
            "doc_type",
            "bill_date",
            "posting_date",
            "due_date",
            "credit_days",
            "doc_code",
            "doc_no",
            "purchase_number",

            "supplier_invoice_number",
            "supplier_invoice_date",
            "po_reference_no",
            "grn_reference_no",
            "ref_document",

            "vendor",
            "vendor_name",
            "vendor_gstin",
            "vendor_state",
            "vendor_display_name",
            "vendor_accountcode",
            "vendor_ledger_id",
            "vendor_partytype",

            "supply_category",
            "default_taxability",
            "tax_regime",
            "is_igst",

            "supplier_state",
            "place_of_supply_state",
            "currency_code",
            "base_currency_code",
            "exchange_rate",

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
            "grand_total_base_currency",

            "status",
            "status_name",
            "confirmed_at",
            "confirmed_by",
            "posted_at",
            "posted_by",
            "cancelled_at",
            "cancelled_by",
            "cancel_reason",
            "entity",
            "entityfinid",
            "subentity",

            "preview_doc_no",
            "preview_purchase_number",

            # Income-tax TDS
            "withholding_enabled",
            "tds_is_manual",
            "tds_section",
            "tds_rate",
            "tds_base_amount",
            "tds_amount",
            "tds_reason",
            "vendor_tds_declared",
            "vendor_tds_rate",
            "vendor_tds_base_amount",
            "vendor_tds_amount",
            "vendor_tds_notes",

            # GST-TDS u/s 51
            "gst_tds_enabled",
            "gst_tds_is_manual",
            "gst_tds_contract_ref",
            "gst_tds_reason",

            "gst_tds_rate",
            "gst_tds_base_amount",
            "gst_tds_cgst_amount",
            "gst_tds_sgst_amount",
            "gst_tds_igst_amount",
            "gst_tds_amount",
            "gst_tds_status",
            "vendor_gst_tds_declared",
            "vendor_gst_tds_rate",
            "vendor_gst_tds_base_amount",
            "vendor_gst_tds_cgst_amount",
            "vendor_gst_tds_sgst_amount",
            "vendor_gst_tds_igst_amount",
            "vendor_gst_tds_amount",
            "vendor_gst_tds_notes",
            "match_status",
            "match_notes",
            "custom_fields",

            # derived rates
            "gst_tds_cgst_rate",
            "gst_tds_sgst_rate",
            "gst_tds_igst_rate",

            "lines",
            "charges",
        ]

        # Do NOT mark TDS fields read-only here; we control via validate() (manual vs auto).
        read_only_fields = ()

        extra_kwargs = {
            "posting_date": {"help_text": "If blank, backend defaults to bill date and validates it against bill date."},
            "due_date": {"help_text": "If blank, backend derives from bill date + credit days and validates it against bill date."},
            "tax_regime": {"help_text": "Backend derives or validates GST regime from vendor/place-of-supply states."},
            "is_igst": {"help_text": "Backend derives or validates IGST applicability from tax regime."},
            "is_reverse_charge": {"help_text": "Editable, but backend suppresses GST amounts on lines when enabled."},
            "is_itc_eligible": {"help_text": "Editable, but backend validates legal ITC eligibility."},
            "itc_block_reason": {"help_text": "Backend may auto-fill when ITC is blocked or not eligible."},
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
            "grand_total_base_currency": {"read_only": True},

            # server controls GST-TDS status always
            "gst_tds_status": {"read_only": True},
            "match_status": {"read_only": True},
            "confirmed_at": {"read_only": True},
            "confirmed_by": {"read_only": True},
            "posted_at": {"read_only": True},
            "posted_by": {"read_only": True},
            "cancelled_at": {"read_only": True},
            "cancelled_by": {"read_only": True},
        }

    # ----------------------------
    # Number Series – PREVIEW
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
        if self.context.get("skip_preview_numbers", False):
            return None
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
        if self.context.get("skip_preview_numbers", False):
            return None
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
        inst = getattr(self, "instance", None)

        entity = attrs.get("entity") or getattr(inst, "entity_id", None)
        subentity = attrs.get("subentity") or getattr(inst, "subentity_id", None)
        bill_date = attrs.get("bill_date") or getattr(inst, "bill_date", None)
        posting_date = attrs.get("posting_date") or getattr(inst, "posting_date", None)
        credit_days = attrs.get("credit_days") if "credit_days" in attrs else getattr(inst, "credit_days", None)
        due_date = attrs.get("due_date") if "due_date" in attrs else getattr(inst, "due_date", None)

        # Default posting_date to bill_date
        if bill_date and not posting_date:
            attrs["posting_date"] = bill_date

        # Derive due_date if missing and credit_days exists
        if bill_date and not due_date and credit_days is not None:
            attrs["due_date"] = bill_date + timedelta(days=int(credit_days))

        due_date_final = attrs.get("due_date") or due_date
        if bill_date and due_date_final and due_date_final < bill_date:
            raise serializers.ValidationError({"due_date": "Due date cannot be before bill date."})

        posting_date_final = attrs.get("posting_date") or posting_date
        if bill_date and posting_date_final and posting_date_final < bill_date:
            raise serializers.ValidationError({"posting_date": "Posting date cannot be before bill date."})

        if inst and inst.status in (Status.POSTED, Status.CANCELLED):
            raise serializers.ValidationError("Cannot edit a POSTED or CANCELLED purchase document.")

        # Lock period validation
        if entity and bill_date:
            PurchaseInvoiceService.assert_not_locked(
                entity_id=entity.id if hasattr(entity, "id") else entity,
                subentity_id=subentity.id if hasattr(subentity, "id") else subentity,
                bill_date=bill_date,
            )

        # GST regime consistency
        is_igst = attrs.get("is_igst", getattr(inst, "is_igst", False))
        tax_regime = attrs.get("tax_regime", getattr(inst, "tax_regime", None))

        if tax_regime == TaxRegime.INTER and not is_igst:
            raise serializers.ValidationError({"is_igst": "For Inter-state (IGST) regime, is_igst must be true."})
        if tax_regime == TaxRegime.INTRA and is_igst:
            raise serializers.ValidationError({"is_igst": "For Intra-state (CGST+SGST) regime, is_igst must be false."})

        # ITC header: if not eligible, ensure reason
        is_itc_eligible = attrs.get("is_itc_eligible", getattr(inst, "is_itc_eligible", True))
        if is_itc_eligible is False:
            if not (attrs.get("itc_block_reason") or getattr(inst, "itc_block_reason", "")).strip():
                attrs["itc_block_reason"] = "Not ITC eligible"

        # Mixed taxability policy
        lines = attrs.get("lines", None)
        if lines is not None and entity:
            ent_id = entity.id if hasattr(entity, "id") else entity
            sub_id = subentity.id if hasattr(subentity, "id") else subentity
            policy = PurchaseSettingsService.get_policy(ent_id, sub_id)
            if not policy.allow_mixed_taxability:
                taxabilities = {ln.get("taxability", Taxability.TAXABLE) for ln in lines}
                if len(taxabilities) > 1:
                    raise serializers.ValidationError({"lines": "Mixed taxability in one bill is disabled for this entity."})

        # Defaults for line fields (as you had)
        if lines is not None:
            default_inclusive = attrs.get(
                "is_rate_inclusive_of_tax_default",
                getattr(inst, "is_rate_inclusive_of_tax_default", False) if inst else False
            )
            for ln in lines:
                if ln.get("is_rate_inclusive_of_tax") in (None, ""):
                    ln["is_rate_inclusive_of_tax"] = bool(default_inclusive)
                if ln.get("free_qty") is None:
                    ln["free_qty"] = Decimal("0.0000")
                if ln.get("discount_type") is None:
                    ln["discount_type"] = PurchaseInvoiceLine.DiscountType.NONE
                if ln.get("discount_percent") is None:
                    ln["discount_percent"] = Decimal("0.00")
                if ln.get("discount_amount") is None:
                    ln["discount_amount"] = Decimal("0.00")
                if ln.get("cess_percent") is None:
                    ln["cess_percent"] = Decimal("0.00")

        if "custom_fields_json" in attrs:
            entity = attrs.get("entity") or getattr(inst, "entity", None)
            subentity = attrs.get("subentity") or getattr(inst, "subentity", None)
            vendor = attrs.get("vendor") or getattr(inst, "vendor", None)
            if entity:
                try:
                    attrs["custom_fields_json"] = InvoiceCustomFieldService.validate_payload(
                        entity_id=int(getattr(entity, "id", entity)),
                        module="purchase_invoice",
                        payload=attrs.get("custom_fields_json") or {},
                        subentity_id=int(getattr(subentity, "id", subentity)) if subentity else None,
                        party_account_id=int(getattr(vendor, "id", vendor)) if vendor else None,
                    )
                except ValueError as ex:
                    raise serializers.ValidationError({"custom_fields": str(ex)})

        # --------------------------
        # Income-tax TDS (manual/auto)
        # --------------------------
        withholding_enabled = attrs.get("withholding_enabled", getattr(inst, "withholding_enabled", False))

        if not withholding_enabled:
            attrs["tds_is_manual"] = False
            attrs["tds_section"] = None
            attrs["tds_rate"] = Decimal("0.0000")
            attrs["tds_base_amount"] = ZERO2
            attrs["tds_amount"] = ZERO2
            attrs["tds_reason"] = None
            attrs["vendor_tds_declared"] = False
            attrs["vendor_tds_rate"] = Decimal("0.0000")
            attrs["vendor_tds_base_amount"] = ZERO2
            attrs["vendor_tds_amount"] = ZERO2
            attrs["vendor_tds_notes"] = None
        else:
            tds_section = attrs.get("tds_section", getattr(inst, "tds_section", None))
            manual_keys = ("tds_rate", "tds_base_amount", "tds_amount")
            manual_payload_present = any(k in attrs for k in manual_keys)
            if manual_payload_present and "tds_is_manual" not in attrs:
                # UX-safe behavior: if UI sends manual fields but forgets toggle, treat as manual.
                attrs["tds_is_manual"] = True

            tds_is_manual = attrs.get("tds_is_manual", getattr(inst, "tds_is_manual", False))
            vendor_tds_declared = attrs.get("vendor_tds_declared", getattr(inst, "vendor_tds_declared", False))

            # In auto mode, section can be resolved from entity withholding config.
            if tds_is_manual and not tds_section:
                raise serializers.ValidationError({"tds_section": "TDS section is required when withholding_enabled is true."})

            if not tds_is_manual:
                # auto: ignore client values
                attrs.pop("tds_rate", None)
                attrs.pop("tds_base_amount", None)
                attrs.pop("tds_amount", None)
                attrs.pop("tds_reason", None)
            else:
                rate = q4(Decimal(str(attrs.get("tds_rate", "0.0000") or "0.0000")))
                base = q2(Decimal(str(attrs.get("tds_base_amount", "0.00") or "0.00")))
                amt = q2(Decimal(str(attrs.get("tds_amount", "0.00") or "0.00")))

                if rate < 0 or base < 0 or amt < 0:
                    raise serializers.ValidationError("Manual TDS values cannot be negative.")

                expected = q2(base * rate / Decimal("100.00"))
                if (amt - expected).copy_abs() > TDS_TOLERANCE:
                    raise serializers.ValidationError({"tds_amount": f"Amount mismatch. Expected ~{expected}."})

                # Persist normalized manual values explicitly.
                attrs["tds_rate"] = rate
                attrs["tds_base_amount"] = base
                attrs["tds_amount"] = amt
            if vendor_tds_declared:
                for f in ("vendor_tds_rate", "vendor_tds_base_amount", "vendor_tds_amount"):
                    if f not in attrs and not inst:
                        raise serializers.ValidationError({f: "Required when vendor_tds_declared is true."})
                v_rate = q4(Decimal(str(attrs.get("vendor_tds_rate", getattr(inst, "vendor_tds_rate", "0.0000")) or "0.0000")))
                v_base = q2(Decimal(str(attrs.get("vendor_tds_base_amount", getattr(inst, "vendor_tds_base_amount", "0.00")) or "0.00")))
                v_amt = q2(Decimal(str(attrs.get("vendor_tds_amount", getattr(inst, "vendor_tds_amount", "0.00")) or "0.00")))
                if min(v_rate, v_base, v_amt) < ZERO2:
                    raise serializers.ValidationError({"vendor_tds_amount": "Vendor TDS values cannot be negative."})
            else:
                attrs["vendor_tds_rate"] = Decimal("0.0000")
                attrs["vendor_tds_base_amount"] = ZERO2
                attrs["vendor_tds_amount"] = ZERO2
                attrs["vendor_tds_notes"] = None

        # --------------------------
        # GST-TDS u/s 51 (manual/auto)
        # --------------------------
        gst_enabled = attrs.get("gst_tds_enabled", getattr(inst, "gst_tds_enabled", False))

        if not gst_enabled:
            attrs["gst_tds_is_manual"] = False
            attrs.pop("gst_tds_rate", None)
            attrs.pop("gst_tds_base_amount", None)
            attrs.pop("gst_tds_cgst_amount", None)
            attrs.pop("gst_tds_sgst_amount", None)
            attrs.pop("gst_tds_igst_amount", None)
            attrs.pop("gst_tds_amount", None)
            attrs.pop("gst_tds_status", None)
            attrs["vendor_gst_tds_declared"] = False
            attrs["vendor_gst_tds_rate"] = Decimal("0.0000")
            attrs["vendor_gst_tds_base_amount"] = ZERO2
            attrs["vendor_gst_tds_cgst_amount"] = ZERO2
            attrs["vendor_gst_tds_sgst_amount"] = ZERO2
            attrs["vendor_gst_tds_igst_amount"] = ZERO2
            attrs["vendor_gst_tds_amount"] = ZERO2
            attrs["vendor_gst_tds_notes"] = None
        else:
            contract_ref = (attrs.get("gst_tds_contract_ref") if "gst_tds_contract_ref" in attrs else getattr(inst, "gst_tds_contract_ref", "")) or ""
            if not str(contract_ref).strip():
                raise serializers.ValidationError({"gst_tds_contract_ref": "Contract reference is required when gst_tds_enabled is true."})

            manual_keys = (
                "gst_tds_rate",
                "gst_tds_base_amount",
                "gst_tds_cgst_amount",
                "gst_tds_sgst_amount",
                "gst_tds_igst_amount",
                "gst_tds_amount",
            )
            manual_payload_present = any(k in attrs for k in manual_keys)
            if manual_payload_present and "gst_tds_is_manual" not in attrs:
                # UX-safe behavior: if UI sends manual fields but forgets toggle, treat as manual.
                attrs["gst_tds_is_manual"] = True

            gst_manual = attrs.get("gst_tds_is_manual", getattr(inst, "gst_tds_is_manual", False))
            vendor_gst_declared = attrs.get("vendor_gst_tds_declared", getattr(inst, "vendor_gst_tds_declared", False))

            if not gst_manual:
                attrs.pop("gst_tds_rate", None)
                attrs.pop("gst_tds_base_amount", None)
                attrs.pop("gst_tds_cgst_amount", None)
                attrs.pop("gst_tds_sgst_amount", None)
                attrs.pop("gst_tds_igst_amount", None)
                attrs.pop("gst_tds_amount", None)
                attrs.pop("gst_tds_status", None)
            else:
                for f in ("gst_tds_rate", "gst_tds_base_amount", "gst_tds_amount"):
                    if f not in attrs:
                        raise serializers.ValidationError({f: "Required in manual GST-TDS mode."})

                rate = q4(Decimal(str(attrs.get("gst_tds_rate", "0.0000") or "0.0000")))
                base = q2(Decimal(str(attrs.get("gst_tds_base_amount", "0.00") or "0.00")))
                cgst = q2(Decimal(str(attrs.get("gst_tds_cgst_amount", "0.00") or "0.00")))
                sgst = q2(Decimal(str(attrs.get("gst_tds_sgst_amount", "0.00") or "0.00")))
                igst = q2(Decimal(str(attrs.get("gst_tds_igst_amount", "0.00") or "0.00")))
                total = q2(Decimal(str(attrs.get("gst_tds_amount", "0.00") or "0.00")))

                if (total - q2(cgst + sgst + igst)).copy_abs() > GST_TDS_TOLERANCE:
                    raise serializers.ValidationError({"gst_tds_amount": "Must equal CGST+SGST+IGST in manual mode."})

                # never allow client to set status
                attrs.pop("gst_tds_status", None)

                # Persist normalized manual values explicitly.
                attrs["gst_tds_rate"] = rate
                attrs["gst_tds_base_amount"] = base
                attrs["gst_tds_cgst_amount"] = cgst
                attrs["gst_tds_sgst_amount"] = sgst
                attrs["gst_tds_igst_amount"] = igst
                attrs["gst_tds_amount"] = total
            if vendor_gst_declared:
                for f in ("vendor_gst_tds_rate", "vendor_gst_tds_base_amount", "vendor_gst_tds_amount"):
                    if f not in attrs and not inst:
                        raise serializers.ValidationError({f: "Required when vendor_gst_tds_declared is true."})
                v_rate = q4(Decimal(str(attrs.get("vendor_gst_tds_rate", getattr(inst, "vendor_gst_tds_rate", "0.0000")) or "0.0000")))
                v_base = q2(Decimal(str(attrs.get("vendor_gst_tds_base_amount", getattr(inst, "vendor_gst_tds_base_amount", "0.00")) or "0.00")))
                v_total = q2(Decimal(str(attrs.get("vendor_gst_tds_amount", getattr(inst, "vendor_gst_tds_amount", "0.00")) or "0.00")))
                v_cgst = q2(Decimal(str(attrs.get("vendor_gst_tds_cgst_amount", getattr(inst, "vendor_gst_tds_cgst_amount", "0.00")) or "0.00")))
                v_sgst = q2(Decimal(str(attrs.get("vendor_gst_tds_sgst_amount", getattr(inst, "vendor_gst_tds_sgst_amount", "0.00")) or "0.00")))
                v_igst = q2(Decimal(str(attrs.get("vendor_gst_tds_igst_amount", getattr(inst, "vendor_gst_tds_igst_amount", "0.00")) or "0.00")))
                if min(v_rate, v_base, v_total, v_cgst, v_sgst, v_igst) < ZERO2:
                    raise serializers.ValidationError({"vendor_gst_tds_amount": "Vendor GST-TDS values cannot be negative."})
                if (v_total - q2(v_cgst + v_sgst + v_igst)).copy_abs() > GST_TDS_TOLERANCE:
                    raise serializers.ValidationError({"vendor_gst_tds_amount": "Vendor GST-TDS total must equal CGST+SGST+IGST."})
            else:
                attrs["vendor_gst_tds_rate"] = Decimal("0.0000")
                attrs["vendor_gst_tds_base_amount"] = ZERO2
                attrs["vendor_gst_tds_cgst_amount"] = ZERO2
                attrs["vendor_gst_tds_sgst_amount"] = ZERO2
                attrs["vendor_gst_tds_igst_amount"] = ZERO2
                attrs["vendor_gst_tds_amount"] = ZERO2
                attrs["vendor_gst_tds_notes"] = None

        return attrs

    # ----------------------------
    # Create / Update workflow
    # ----------------------------

    def create(self, validated_data):
        # Number fields are system-managed and must not be client-controlled.
        validated_data.pop("doc_no", None)
        validated_data.pop("purchase_number", None)
        try:
            header = PurchaseInvoiceService.create_with_lines(validated_data)
        except ValueError as e:
            payload = e.args[0] if e.args else str(e)
            if isinstance(payload, dict):
                raise serializers.ValidationError(payload)
            msg = str(payload)
            if "Provide tds_section or configure default TDS section" in msg:
                raise serializers.ValidationError({"tds_section": msg})
            raise serializers.ValidationError({"non_field_errors": [msg]})

        policy = PurchaseSettingsService.get_policy(header.entity_id, header.subentity_id)
        if policy.default_action == "confirm":
            PurchaseInvoiceActions.confirm(header.pk)
        elif policy.default_action == "post":
            PurchaseInvoiceActions.confirm(header.pk)
            PurchaseInvoiceActions.post(header.pk)

        header.refresh_from_db()
        return header

    def update(self, instance, validated_data):
        # Keep allocated numbering immutable through normal edit/update calls.
        validated_data.pop("doc_no", None)
        validated_data.pop("purchase_number", None)
        try:
            updated = PurchaseInvoiceService.update_with_lines(instance, validated_data)
        except ValueError as e:
            payload = e.args[0] if e.args else str(e)
            if isinstance(payload, dict):
                raise serializers.ValidationError(payload)
            msg = str(payload)
            if "Provide tds_section or configure default TDS section" in msg:
                raise serializers.ValidationError({"tds_section": msg})
            raise serializers.ValidationError({"non_field_errors": [msg]})

        policy = PurchaseSettingsService.get_policy(updated.entity_id, updated.subentity_id)
        if updated.status == Status.DRAFT:
            if policy.default_action == "confirm":
                PurchaseInvoiceActions.confirm(updated.pk)
            elif policy.default_action == "post":
                PurchaseInvoiceActions.confirm(updated.pk)
                PurchaseInvoiceActions.post(updated.pk)

        updated.refresh_from_db()
        return updated


class PurchaseInvoiceSearchSerializer(serializers.ModelSerializer):
    doc_type_name = serializers.CharField(source="get_doc_type_display", read_only=True)
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    supply_category_name = serializers.CharField(source="get_supply_category_display", read_only=True)
    taxability_name = serializers.CharField(source="get_default_taxability_display", read_only=True)
    tax_regime_name = serializers.CharField(source="get_tax_regime_display", read_only=True)
    gstr2b_match_status_name = serializers.CharField(source="get_gstr2b_match_status_display", read_only=True)
    itc_claim_status_name = serializers.CharField(source="get_itc_claim_status_display", read_only=True)

    entity_id = serializers.IntegerField(read_only=True)
    entityfinid_id = serializers.IntegerField(read_only=True)
    subentity_id = serializers.IntegerField(read_only=True)
    vendor_id = serializers.IntegerField(read_only=True)
    vendor_state_id = serializers.IntegerField(read_only=True)
    vendor_display_name = serializers.CharField(source="vendor.effective_accounting_name", read_only=True)
    vendor_accountcode = serializers.IntegerField(source="vendor.effective_accounting_code", read_only=True)
    vendor_ledger_id = serializers.SerializerMethodField()
    vendor_partytype = serializers.CharField(source="vendor.commercial_profile.partytype", read_only=True)

    def get_vendor_ledger_id(self, obj):
        return getattr(obj, "vendor_ledger_id", None) or getattr(obj.vendor, "ledger_id", None)

    class Meta:
        model = PurchaseInvoiceHeader
        fields = [
            "id",
            "entity_id", "entityfinid_id", "subentity_id",
            "doc_type", "doc_type_name",
            "status", "status_name",
            "doc_code", "doc_no", "purchase_number",

            "bill_date",
            "posting_date",
            "credit_days",
            "due_date",

            "supplier_invoice_number",
            "supplier_invoice_date",
            "po_reference_no",
            "grn_reference_no",
            "vendor_id",
            "vendor_name",
            "vendor_gstin",
            "vendor_state_id",
            "vendor_display_name",
            "vendor_accountcode",
            "vendor_ledger_id",
            "vendor_partytype",

            "supply_category", "supply_category_name",
            "default_taxability", "taxability_name",
            "tax_regime", "tax_regime_name",
            "is_igst",
            "is_reverse_charge",
            "is_itc_eligible",
            "gstr2b_match_status", "gstr2b_match_status_name",
            "itc_claim_status", "itc_claim_status_name",
            "itc_claim_period",
            "itc_block_reason",

            "total_taxable",
            "total_gst",
            "round_off",
            "grand_total",

            "created_at",
            "updated_at",
        ]


class PurchaseInvoiceListSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    doc_type_name = serializers.CharField(source="get_doc_type_display", read_only=True)
    vendor_display_name = serializers.CharField(source="vendor.effective_accounting_name", read_only=True)
    vendor_accountcode = serializers.IntegerField(source="vendor.effective_accounting_code", read_only=True)
    vendor_ledger_id = serializers.SerializerMethodField()
    vendor_partytype = serializers.CharField(source="vendor.commercial_profile.partytype", read_only=True)

    def get_vendor_ledger_id(self, obj):
        return getattr(obj, "vendor_ledger_id", None) or getattr(obj.vendor, "ledger_id", None)

    class Meta:
        model = PurchaseInvoiceHeader
        fields = [
            "id",
            "doc_type",
            "doc_type_name",
            "status",
            "status_name",
            "bill_date",
            "posting_date",
            "due_date",
            "doc_code",
            "doc_no",
            "purchase_number",
            "supplier_invoice_number",
            "po_reference_no",
            "grn_reference_no",
            "vendor",
            "vendor_name",
            "vendor_gstin",
            "vendor_display_name",
            "vendor_accountcode",
            "vendor_ledger_id",
            "vendor_partytype",
            "supply_category",
            "default_taxability",
            "tax_regime",
            "is_reverse_charge",
            "total_taxable",
            "total_gst",
            "round_off",
            "grand_total",
            "withholding_enabled",
            "tds_amount",
            "gst_tds_enabled",
            "gst_tds_amount",
            "match_status",
            "entity",
            "entityfinid",
            "subentity",
            "created_at",
            "updated_at",
        ]
