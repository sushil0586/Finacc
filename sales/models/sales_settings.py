from __future__ import annotations

from decimal import Decimal
from copy import deepcopy

from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError

from core.models.base import EntityScopedModel,TrackingModel
from sales.models.sales_core import SalesInvoiceHeader  # adjust path if needed

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")

DEFAULT_POLICY_CONTROLS = {
    "delete_policy": "draft_only",
    "allow_edit_confirmed": "on",
    "allow_unpost_posted": "on",
    "confirm_lock_check": "hard",
    "require_lines_on_confirm": "hard",
    "line_amount_mismatch": "hard",
    "invoice_match_mode": "off",
    "invoice_match_enforcement": "off",
    "settlement_mode": "basic",
    "allocation_policy": "manual",
    "over_settlement_rule": "block",
    "auto_adjust_credit_notes": "off",
    "statutory_maker_checker": "off",
    "auto_compliance_failure_mode": "warn",
    "compliance_allow_generate_irn_on_confirmed": "on",
    "compliance_allow_generate_irn_on_posted": "on",
    "compliance_allow_regenerate_irn_after_cancel": "off",
    "compliance_allow_regenerate_eway_after_cancel": "on",
    "compliance_allow_cancel_irn_when_eway_active": "off",
}

DEFAULT_INVOICE_PRINTING = {
    "default_profile": "gst_standard",
    "default_copies": ["original"],
    "profiles": [
        {
            "key": "gst_standard",
            "label": "GST Standard A4",
            "hint": "Rule-friendly layout with full statutory sections.",
            "options": {
                "show_bank_details": True,
                "show_terms": True,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": True,
                "show_compliance_qr": True,
                "show_gst_validation_panel": True,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "comfortable",
                "font_scale": 1.0,
                "template_key": "gst_a4",
                "page_size": "A4",
                "orientation": "portrait",
                "margin_mm": 10,
                "pdf_render_scale": 0.55,
                "pdf_image_quality": 0.62,
            },
        },
        {
            "key": "plain",
            "label": "Plain Paper",
            "hint": "Minimal visual layout while retaining invoice essentials.",
            "options": {
                "show_bank_details": False,
                "show_terms": False,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": True,
                "show_compliance_qr": True,
                "show_gst_validation_panel": True,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "comfortable",
                "font_scale": 1.0,
                "template_key": "plain_a4",
                "page_size": "A4",
                "orientation": "portrait",
                "margin_mm": 10,
                "pdf_render_scale": 0.5,
                "pdf_image_quality": 0.58,
            },
        },
        {
            "key": "large_invoice",
            "label": "Large Invoice (50+ Lines)",
            "hint": "Compact spacing optimized for long multi-page invoices.",
            "options": {
                "show_bank_details": True,
                "show_terms": False,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": True,
                "show_compliance_qr": True,
                "show_gst_validation_panel": True,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "compact",
                "font_scale": 0.92,
                "template_key": "gst_a4_compact",
                "page_size": "A4",
                "orientation": "portrait",
                "margin_mm": 8,
                "pdf_render_scale": 0.5,
                "pdf_image_quality": 0.58,
            },
        },
        {
            "key": "thermal_80mm",
            "label": "Thermal 80mm",
            "hint": "Narrow, fast print profile for grocery and POS printers.",
            "options": {
                "show_bank_details": False,
                "show_terms": False,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": False,
                "show_compliance_qr": False,
                "show_gst_validation_panel": False,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "compact",
                "font_scale": 0.84,
                "template_key": "thermal_80mm",
                "page_size": "80MM",
                "orientation": "portrait",
                "margin_mm": 2,
                "pdf_render_scale": 0.42,
                "pdf_image_quality": 0.5,
            },
        },
        {
            "key": "thermal_58mm",
            "label": "Thermal 58mm",
            "hint": "Ultra-compact receipt profile for narrow thermal printers.",
            "options": {
                "show_bank_details": False,
                "show_terms": False,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": False,
                "show_compliance_qr": False,
                "show_gst_validation_panel": False,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "compact",
                "font_scale": 0.8,
                "template_key": "thermal_58mm",
                "page_size": "58MM",
                "orientation": "portrait",
                "margin_mm": 1,
                "pdf_render_scale": 0.4,
                "pdf_image_quality": 0.48,
            },
        },
        {
            "key": "transport_copy",
            "label": "Transport Copy",
            "hint": "Highlights transport, E-Way and QR details for goods movement.",
            "options": {
                "show_bank_details": False,
                "show_terms": False,
                "show_einvoice_section": True,
                "show_eway_details": True,
                "show_transport_details": True,
                "show_compliance_qr": True,
                "show_gst_validation_panel": True,
                "gst_validation_checks": ["SCN_B2B", "SCN_B2C", "SCN_EXPORT", "SCN_RCM", "SCN_EINV", "SCN_EWAY", "SCN_TRANSPORT", "SCN_TAX_SPLIT"],
                "line_density": "compact",
                "font_scale": 0.9,
                "template_key": "transport_copy",
                "page_size": "A4",
                "orientation": "portrait",
                "margin_mm": 8,
                "pdf_render_scale": 0.5,
                "pdf_image_quality": 0.56,
            },
        },
    ],
    "copy_labels": {
        "original": "ORIGINAL FOR RECIPIENT",
        "duplicate": "DUPLICATE FOR TRANSPORTER",
        "triplicate": "TRIPLICATE FOR SUPPLIER",
    },
    "texts": {
        "form_label": "Form GST INV-1",
        "receiver_title": "Details of Receiver (Billed to)",
        "consignee_title": "Details of Consignee (Shipped to)",
        "terms_title": "Terms & Conditions :",
        "terms_lines": [
            "Our responsibility ceases after the goods are removed from our premises",
            "Goods once sold are not returnable or exchangeable",
            "if the bill is not paid within a week interest @24% will be charged from date of bill",
        ],
        "terms_ack_lines": [
            "Received the above goods in good condition",
            "Rate & Weight of this bill found correct.",
        ],
        "signature_labels": ["", "Checked By", "Prepared By", "Customer's Sign"],
        "line_columns": [
            {"key": "line_no", "label": "Sr", "colspan": 2, "className": "ams-border-left", "format": "index"},
            {"key": "productname", "label": "Description of Goods", "colspan": 2, "className": "ams-border-left", "format": "text"},
            {"key": "hsn", "label": "HSN", "colspan": 2, "className": "ams-border-left", "format": "text"},
            {"key": "pieces", "label": "Pcs", "colspan": 1, "className": "ams-border-left text-end", "format": "integer"},
            {"key": "orderqty", "label": "Qty", "colspan": 1, "className": "ams-border-left text-end", "format": "integer"},
            {"key": "units", "label": "Unit", "colspan": 1, "className": "ams-border-left text-start", "format": "text"},
            {"key": "ratebefdiscount", "label": "Rate", "colspan": 1, "className": "ams-border-left text-end", "format": "number"},
            {"key": "orderDiscount", "label": "Discount %", "colspan": 1, "className": "ams-border-left text-end", "format": "text"},
            {"key": "rate", "label": "Actual Rate", "colspan": 2, "className": "ams-border-left text-end", "format": "number"},
            {"key": "amount", "label": "Amount", "colspan": 2, "className": "text-end ams-border-left ams-border-right", "format": "number"},
        ],
    },
}


def default_policy_controls():
    return deepcopy(DEFAULT_POLICY_CONTROLS)

def default_invoice_printing():
    return deepcopy(DEFAULT_INVOICE_PRINTING)


class SalesSettings(EntityScopedModel):
    """
    One row per entity + (optional subentity).
    Controls default workflow + governance policies for Sales.
    """

    class DefaultWorkflowAction(models.TextChoices):
        DRAFT = "draft", "Save as Draft"
        CONFIRM = "confirm", "Auto Confirm on Save"
        POST = "post", "Auto Post on Save"

    class TCSCreditNotePolicy(models.TextChoices):
        DISALLOW = "DISALLOW", "Disallow TCS on Credit Note"
        ALLOW = "ALLOW", "Allow TCS on Credit Note"
        REVERSE = "REVERSE", "Reverse TCS on Credit Note"

    class ComplianceApplicabilityMode(models.TextChoices):
        AUTO_ONLY = "AUTO_ONLY", "Auto Derive Only"
        AUTO_WITH_OVERRIDE = "AUTO_WITH_OVERRIDE", "Auto + Manual Override (Audited)"

    entity = models.ForeignKey(
        "entity.Entity",
        on_delete=models.PROTECT,
        related_name="sales_sales_settings",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_sales_settings_scope",
    )

    # default doc codes used by your invoice creation
    default_doc_code_invoice = models.CharField(max_length=10, default="SINV")
    default_doc_code_cn = models.CharField(max_length=10, default="SCN")
    default_doc_code_dn = models.CharField(max_length=10, default="SDN")

    # ✅ default workflow behavior on create
    default_workflow_action = models.CharField(
        max_length=10,
        choices=DefaultWorkflowAction.choices,
        default=DefaultWorkflowAction.DRAFT,
        db_index=True,
    )

    # -------------------------
    # Policies / governance
    # -------------------------
    auto_derive_tax_regime = models.BooleanField(default=True)  # POS vs seller_state
    allow_mixed_taxability_in_one_invoice = models.BooleanField(default=True)

    # E-Invoice / E-Way governance
    # (actual applicability is derived in service, but these flags let SaaS tenants enforce policies)
    enable_einvoice = models.BooleanField(default=True)
    enable_eway = models.BooleanField(default=True)

    # e-invoice policy (when to attempt generation)
    auto_generate_einvoice_on_confirm = models.BooleanField(default=False)
    auto_generate_einvoice_on_post = models.BooleanField(default=False)

    # e-way policy (when to attempt generation)
    auto_generate_eway_on_confirm = models.BooleanField(default=False)
    auto_generate_eway_on_post = models.BooleanField(default=False)

    # optional: use combined IRP flow when both are needed (generate IRN + EWB together if supported)
    prefer_irp_generate_einvoice_and_eway_together = models.BooleanField(default=True)
    enforce_statutory_cancel_before_business_cancel = models.BooleanField(default=True)

    # Applicability policy
    einvoice_entity_applicable = models.BooleanField(default=False)
    eway_value_threshold = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("50000.00"))
    compliance_applicability_mode = models.CharField(
        max_length=24,
        choices=ComplianceApplicabilityMode.choices,
        default=ComplianceApplicabilityMode.AUTO_ONLY,
    )

    # TCS governance
    tcs_credit_note_policy = models.CharField(
        max_length=12,
        choices=TCSCreditNotePolicy.choices,
        default=TCSCreditNotePolicy.REVERSE,
    )

    # -------------------------
    # Rounding configuration
    # -------------------------
    round_grand_total_to = models.PositiveSmallIntegerField(default=2)  # decimals
    enable_round_off = models.BooleanField(default=True)
    policy_controls = models.JSONField(default=default_policy_controls, blank=True)
    invoice_printing = models.JSONField(default=default_invoice_printing, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "subentity"),
                name="uq_sales_settings_entity_subentity",
            ),
        ]
        indexes = [
            models.Index(fields=["entity"], name="ix_sales_settings_entity"),
            models.Index(fields=["entity", "subentity"], name="ix_sales_settings_scope"),
        ]

    def __str__(self) -> str:
        return f"SalesSettings(entity={self.entity_id}, subentity={self.subentity_id})"


class SalesLockPeriod(EntityScopedModel):
    """
    Prevent edits/posting before lock_date (per entity or entity+subentity).
    Typical for accountants after period closing.
    """

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True)

    lock_date = models.DateField()  # all invoices <= lock_date are locked
    reason = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "subentity", "lock_date"], name="ix_sales_lock_period"),
        ]

    def __str__(self) -> str:
        return f"Lock({self.entity_id}, {self.subentity_id}, {self.lock_date})"


class SalesChoiceOverride(TrackingModel):
    """
    SaaS choice governance:
      - enable/disable an enum value per entity/subentity
      - override labels without code changes

    Example:
      choice_group="SupplyCategory"
      choice_key="EXPORT_WITHOUT_IGST"
      is_enabled=False
    """

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT)
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True)

    choice_group = models.CharField(max_length=50)  # e.g. "SupplyCategory", "Taxability", "DocType"
    choice_key = models.CharField(max_length=50)    # e.g. "SEZ_WITHOUT_IGST"
    is_enabled = models.BooleanField(default=True)
    override_label = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "subentity", "choice_group", "choice_key"),
                name="uq_sales_choice_override_scope",
            ),
            models.CheckConstraint(
                name="ck_sales_choice_override_group_key_nn",
                check=Q(choice_group__isnull=False) & Q(choice_key__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "subentity", "choice_group"], name="ix_sales_choice_override_scope"),
        ]

    def __str__(self) -> str:
        return f"{self.choice_group}:{self.choice_key} ({'on' if self.is_enabled else 'off'})"


class SalesStockPolicy(TrackingModel):
    """
    Sales stock governance policy with scoped inheritance.

    Scope levels:
      - entity default
      - entity + branch
      - entity + financial year
      - entity + branch + financial year

    Resolution is handled in the service layer. This model stores the scoped
    rule set and can be edited independently from the core Sales settings row.
    """

    class ScopeLevel(models.TextChoices):
        ENTITY = "ENTITY", "Entity"
        ENTITY_SUBENTITY = "ENTITY_SUBENTITY", "Entity + Branch"
        ENTITY_FY = "ENTITY_FY", "Entity + Financial Year"
        ENTITY_SUBENTITY_FY = "ENTITY_SUBENTITY_FY", "Entity + Branch + Financial Year"

    class Mode(models.TextChoices):
        RELAXED = "RELAXED", "Relaxed"
        CONTROLLED = "CONTROLLED", "Controlled"
        STRICT = "STRICT", "Strict"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="sales_stock_policies")
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_stock_policies",
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_stock_policies",
    )

    scope_level = models.CharField(max_length=32, choices=ScopeLevel.choices, db_index=True)
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.RELAXED, db_index=True)

    allow_negative_stock = models.BooleanField(default=True)
    batch_required_for_sales = models.BooleanField(default=False)
    expiry_validation_required = models.BooleanField(default=False)
    fefo_required = models.BooleanField(default=False)
    allow_manual_batch_override = models.BooleanField(default=True)
    allow_oversell = models.BooleanField(default=False)

    scope_key = models.CharField(max_length=120, unique=True, editable=False, db_index=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="ck_sales_stock_policy_scope_level",
                check=Q(scope_level__isnull=False),
            ),
            models.CheckConstraint(
                name="ck_sales_stock_policy_mode",
                check=Q(mode__isnull=False),
            ),
            models.CheckConstraint(
                name="ck_sales_stock_policy_entity_nn",
                check=Q(entity__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "scope_level"], name="ix_sales_stock_policy_scope"),
            models.Index(fields=["entity", "entityfinid", "subentity"], name="ix_sales_stock_policy_ids"),
            models.Index(fields=["entity", "mode"], name="ix_sales_stock_policy_mode"),
        ]

    def _build_scope_key(self) -> str:
        parts = [f"entity:{self.entity_id}"]
        if self.entityfinid_id:
            parts.append(f"fy:{self.entityfinid_id}")
        if self.subentity_id:
            parts.append(f"sub:{self.subentity_id}")
        parts.append(f"scope:{self.scope_level}")
        return "|".join(parts)

    def clean(self):
        if self.scope_level == self.ScopeLevel.ENTITY and (self.entityfinid_id or self.subentity_id):
            raise ValidationError({"scope_level": "ENTITY scope cannot carry branch or financial-year references."})
        if self.scope_level == self.ScopeLevel.ENTITY_FY and (not self.entityfinid_id or self.subentity_id):
            raise ValidationError({"scope_level": "ENTITY_FY scope requires financial year only."})
        if self.scope_level == self.ScopeLevel.ENTITY_SUBENTITY and (not self.subentity_id or self.entityfinid_id):
            raise ValidationError({"scope_level": "ENTITY_SUBENTITY scope requires branch only."})
        if self.scope_level == self.ScopeLevel.ENTITY_SUBENTITY_FY and (not self.subentity_id or not self.entityfinid_id):
            raise ValidationError({"scope_level": "ENTITY_SUBENTITY_FY scope requires both branch and financial year."})
        self.scope_key = self._build_scope_key()

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"SalesStockPolicy({self.scope_key})"
