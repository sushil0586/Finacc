from __future__ import annotations

from typing import Any, Optional

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from assets.models import AssetSettings
from assets.services.settings import AssetSettingsService
from entity.models import SubEntity
from financial.models import FinancialSettings
from payments.models.payment_config import PaymentSettings
from payments.services.payment_settings_service import PaymentSettingsService
from purchase.models.purchase_config import PurchaseChoiceOverride, PurchaseLockPeriod, PurchaseSettings
from purchase.services.purchase_choice_service import PurchaseChoiceService
from purchase.services.purchase_settings_service import PurchaseSettingsService
from receipts.models.receipt_config import ReceiptSettings
from receipts.services.receipt_settings_service import ReceiptSettingsService
from sales.models.sales_settings import SalesChoiceOverride, SalesLockPeriod, SalesSettings
from sales.services.sales_choices_service import SalesChoicesService
from sales.services.sales_settings_service import SalesSettingsService
from vouchers.models.voucher_config import VoucherSettings
from vouchers.services.voucher_settings_service import VoucherSettingsService
from reports.services.financial.reporting_policy import resolve_financial_reporting_policy
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


def _choice_payload(choices) -> list[dict]:
    return [{"value": value, "label": label} for value, label in choices]


def _lock_period_schema():
    return [
        {"name": "lock_date", "label": "Lock Date", "type": "date"},
        {"name": "reason", "label": "Reason", "type": "string"},
    ]


def _policy_schema(controls: dict) -> list[dict]:
    rows = []
    for key, default in controls.items():
        field_type = "number" if str(default).replace(".", "", 1).isdigit() else "string"
        rows.append(
            {
                "name": key,
                "label": key.replace("_", " ").title(),
                "type": field_type,
                "default": default,
            }
        )
    return rows


def _with_help(schema: list[dict], help_map: dict[str, str]) -> list[dict]:
    enriched = []
    for item in schema:
        row = dict(item)
        if row.get("name") in help_map:
            row["help_text"] = help_map[row["name"]]
        enriched.append(row)
    return enriched


def _sections_from_payload(schema: list[dict], *, include_policy=False, include_locks=False, include_overrides=False) -> list[dict]:
    seen = []
    for item in schema:
        group = item.get("group") or "general"
        if group not in seen:
            seen.append(group)
    sections = [{"key": group, "title": group.replace("_", " ").title(), "source": "settings"} for group in seen]
    if include_policy:
        sections.append({"key": "advanced_policy", "title": "Advanced Policy", "source": "policy_controls"})
    if include_locks:
        sections.append({"key": "lock_periods", "title": "Lock Periods", "source": "lock_periods"})
    if include_overrides:
        sections.append({"key": "choice_overrides", "title": "Choice Overrides", "source": "choice_overrides"})
    return sections


class SettingsHubAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_SETUP

    MODULE_ORDER = ["financial", "sales", "purchase", "payments", "receipts", "vouchers", "assets"]

    @staticmethod
    def _parse_int(raw_value: Any, field_name: str, *, required: bool) -> Optional[int]:
        if raw_value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise ValidationError({field_name: f"{field_name} must be an integer."})
        return None if field_name == "subentity" and value == 0 else value

    def _scope(self, request):
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=True)
        entityfinid_id = self._parse_int(request.query_params.get("entityfinid"), "entityfinid", required=False)
        subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity", required=False)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        return entity_id, entityfinid_id, subentity_id

    def _subentity_options(self, entity_id: int):
        rows = list(
            SubEntity.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("-is_head_office", "subentityname", "id")
            .values("id", "subentityname", "is_head_office")
        )
        for row in rows:
            row["ismainentity"] = row["is_head_office"]
        return rows

    def _settings_payload(self, module_title: str, *, settings: dict, schema: list[dict], scope_subentity: bool, capabilities: dict, current_doc_numbers=None, policy_control_schema=None, lock_periods=None, lock_period_schema=None, choice_overrides=None, choice_override_catalog=None):
        payload = {
            "title": module_title,
            "scope": {"entity_only": not scope_subentity, "subentity_supported": scope_subentity},
            "settings": settings,
            "schema": schema,
            "capabilities": capabilities,
        }
        if current_doc_numbers is not None:
            payload["current_doc_numbers"] = current_doc_numbers
        if policy_control_schema is not None:
            payload["policy_control_schema"] = policy_control_schema
        if lock_periods is not None:
            payload["lock_periods"] = lock_periods
            payload["lock_period_schema"] = lock_period_schema or _lock_period_schema()
        if choice_overrides is not None:
            payload["choice_overrides"] = choice_overrides
            payload["choice_override_catalog"] = choice_override_catalog or {}
        payload["sections"] = _sections_from_payload(
            schema,
            include_policy=policy_control_schema is not None,
            include_locks=lock_periods is not None,
            include_overrides=choice_overrides is not None,
        )
        return payload

    def _list_lock_periods(self, model, *, entity_id: int, subentity_id: Optional[int]):
        qs = model.objects.filter(entity_id=entity_id)
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        return list(qs.order_by("lock_date", "id").values("id", "lock_date", "reason"))

    def _list_choice_overrides(self, model, *, entity_id: int, subentity_id: Optional[int]):
        qs = model.objects.filter(entity_id=entity_id)
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        return list(
            qs.order_by("choice_group", "choice_key", "id").values(
                "id",
                "choice_group",
                "choice_key",
                "is_enabled",
                "override_label",
            )
        )

    def _replace_lock_periods(self, model, rows: list[dict], *, entity_id: int, subentity_id: Optional[int]):
        qs = model.objects.filter(entity_id=entity_id)
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        qs.delete()
        for row in rows:
            if not isinstance(row, dict) or not row.get("lock_date"):
                raise ValidationError({"lock_periods": "Each lock period must include lock_date."})
            model.objects.create(
                entity_id=entity_id,
                subentity_id=subentity_id,
                lock_date=row["lock_date"],
                reason=row.get("reason") or "",
            )

    def _replace_choice_overrides(self, model, rows: list[dict], *, entity_id: int, subentity_id: Optional[int], choice_catalog: dict[str, list[dict]]):
        valid_keys = {group: {item["key"] for item in items} for group, items in choice_catalog.items()}
        qs = model.objects.filter(entity_id=entity_id)
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        qs.delete()
        for row in rows:
            if not isinstance(row, dict):
                raise ValidationError({"choice_overrides": "Each override must be an object."})
            group = row.get("choice_group")
            key = row.get("choice_key")
            if group not in valid_keys or key not in valid_keys[group]:
                raise ValidationError({"choice_overrides": f"Invalid override {group}:{key}."})
            model.objects.create(
                entity_id=entity_id,
                subentity_id=subentity_id,
                choice_group=group,
                choice_key=key,
                is_enabled=bool(row.get("is_enabled", True)),
                override_label=row.get("override_label") or "",
            )

    def _financial_settings(self, entity_id: int):
        settings, _ = FinancialSettings.objects.get_or_create(entity_id=entity_id)
        return settings

    def _financial_payload(self, entity_id: int):
        settings = self._financial_settings(entity_id)
        reporting_policy = resolve_financial_reporting_policy(entity_id)
        pl_policy = reporting_policy.get("profit_loss", {})
        bs_policy = reporting_policy.get("balance_sheet", {})

        return self._settings_payload(
            "Financial",
            settings={
                "opening_balance_edit_mode": settings.opening_balance_edit_mode,
                "enforce_gst_uniqueness": settings.enforce_gst_uniqueness,
                "enforce_pan_uniqueness": settings.enforce_pan_uniqueness,
                "require_gst_for_registered_parties": settings.require_gst_for_registered_parties,
                "pl_accounting_only_notes_disclosure": pl_policy.get("accounting_only_notes_disclosure", "summary"),
                "pl_accounting_only_notes_split": pl_policy.get("accounting_only_notes_split", "purchase_sales"),
                "bs_include_accounting_only_notes_disclosure": bs_policy.get("include_accounting_only_notes_disclosure", True),
            },
            schema=_with_help([
                {
                    "name": "opening_balance_edit_mode",
                    "label": "Opening Balance Edit Mode",
                    "type": "choice",
                    "group": "governance",
                    "choices": _choice_payload(FinancialSettings._meta.get_field("opening_balance_edit_mode").choices),
                },
                {"name": "enforce_gst_uniqueness", "label": "Enforce GST Uniqueness", "type": "boolean", "group": "validations"},
                {"name": "enforce_pan_uniqueness", "label": "Enforce PAN Uniqueness", "type": "boolean", "group": "validations"},
                {"name": "require_gst_for_registered_parties", "label": "Require GST For Registered Parties", "type": "boolean", "group": "validations"},
                {
                    "name": "pl_accounting_only_notes_disclosure",
                    "label": "P&L Accounting-only CN/DN Disclosure",
                    "type": "choice",
                    "group": "reporting",
                    "choices": [
                        {"value": "off", "label": "Off"},
                        {"value": "summary", "label": "Summary"},
                    ],
                },
                {
                    "name": "pl_accounting_only_notes_split",
                    "label": "P&L Disclosure Split",
                    "type": "choice",
                    "group": "reporting",
                    "choices": [
                        {"value": "purchase_sales", "label": "Purchase vs Sales"},
                        {"value": "combined", "label": "Combined"},
                    ],
                },
                {
                    "name": "bs_include_accounting_only_notes_disclosure",
                    "label": "Balance Sheet: Include Disclosure",
                    "type": "boolean",
                    "group": "reporting",
                },
            ], {
                "opening_balance_edit_mode": "Controls when opening balances can still be edited.",
                "enforce_gst_uniqueness": "Prevents duplicate GST numbers within the entity.",
                "enforce_pan_uniqueness": "Prevents duplicate PAN numbers within the entity.",
                "require_gst_for_registered_parties": "Forces GST entry when party is marked registered.",
                "pl_accounting_only_notes_disclosure": "Show or hide accounting-only CN/DN impact disclosure on Profit and Loss.",
                "pl_accounting_only_notes_split": "Display accounting-only CN/DN disclosure as combined or purchase-vs-sales split.",
                "bs_include_accounting_only_notes_disclosure": "Carry the accounting-only CN/DN disclosure into Balance Sheet response.",
            }),
            scope_subentity=False,
            capabilities={
                "has_lock_periods": False,
                "has_choice_overrides": False,
                "has_policy_controls": True,
                "has_doc_number_preview": False,
            },
            policy_control_schema=[
                {
                    "name": "pl_accounting_only_notes_disclosure",
                    "label": "P&L Accounting-only CN/DN Disclosure",
                    "type": "choice",
                    "choices": [
                        {"value": "off", "label": "Off"},
                        {"value": "summary", "label": "Summary"},
                    ],
                    "default": "summary",
                },
                {
                    "name": "pl_accounting_only_notes_split",
                    "label": "P&L Disclosure Split",
                    "type": "choice",
                    "choices": [
                        {"value": "purchase_sales", "label": "Purchase vs Sales"},
                        {"value": "combined", "label": "Combined"},
                    ],
                    "default": "purchase_sales",
                },
                {
                    "name": "bs_include_accounting_only_notes_disclosure",
                    "label": "Balance Sheet: Include Disclosure",
                    "type": "boolean",
                    "default": True,
                },
            ],
        )

    def _sales_payload(self, entity_id: int, entityfinid_id: Optional[int], subentity_id: Optional[int]):
        settings = SalesSettingsService.get_settings(entity_id, subentity_id)
        current_doc_numbers = None
        if entityfinid_id:
            current_doc_numbers = {
                "invoice": SalesSettingsService.get_current_doc_no(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, doc_key="sales_invoice", doc_code=settings.default_doc_code_invoice),
                "credit_note": SalesSettingsService.get_current_doc_no(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, doc_key="sales_credit_note", doc_code=settings.default_doc_code_cn),
                "debit_note": SalesSettingsService.get_current_doc_no(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, doc_key="sales_debit_note", doc_code=settings.default_doc_code_dn),
            }
        choice_catalog = SalesChoicesService.get_choices(entity_id=entity_id, subentity_id=subentity_id)
        return self._settings_payload(
            "Sales",
            settings={
                "default_doc_code_invoice": settings.default_doc_code_invoice,
                "default_doc_code_cn": settings.default_doc_code_cn,
                "default_doc_code_dn": settings.default_doc_code_dn,
                "default_workflow_action": settings.default_workflow_action,
                "auto_derive_tax_regime": settings.auto_derive_tax_regime,
                "allow_mixed_taxability_in_one_invoice": settings.allow_mixed_taxability_in_one_invoice,
                "enable_einvoice": settings.enable_einvoice,
                "enable_eway": settings.enable_eway,
                "einvoice_entity_applicable": settings.einvoice_entity_applicable,
                "eway_value_threshold": settings.eway_value_threshold,
                "compliance_applicability_mode": settings.compliance_applicability_mode,
                "auto_generate_einvoice_on_confirm": settings.auto_generate_einvoice_on_confirm,
                "auto_generate_einvoice_on_post": settings.auto_generate_einvoice_on_post,
                "auto_generate_eway_on_confirm": settings.auto_generate_eway_on_confirm,
                "auto_generate_eway_on_post": settings.auto_generate_eway_on_post,
                "prefer_irp_generate_einvoice_and_eway_together": settings.prefer_irp_generate_einvoice_and_eway_together,
                "enforce_statutory_cancel_before_business_cancel": settings.enforce_statutory_cancel_before_business_cancel,
                "tcs_credit_note_policy": settings.tcs_credit_note_policy,
                "enable_round_off": settings.enable_round_off,
                "round_grand_total_to": settings.round_grand_total_to,
            },
            schema=_with_help([
                {"name": "default_doc_code_invoice", "label": "Invoice Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_doc_code_cn", "label": "Credit Note Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_doc_code_dn", "label": "Debit Note Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_workflow_action", "label": "Default Workflow", "type": "choice", "group": "workflow", "choices": _choice_payload(SalesSettings.DefaultWorkflowAction.choices)},
                {"name": "enable_einvoice", "label": "Enable E-Invoice", "type": "boolean", "group": "compliance"},
                {"name": "enable_eway", "label": "Enable E-Way", "type": "boolean", "group": "compliance"},
                {"name": "tcs_credit_note_policy", "label": "TCS Credit Note Policy", "type": "choice", "group": "compliance", "choices": _choice_payload(SalesSettings.TCSCreditNotePolicy.choices)},
            ], {
                "default_doc_code_invoice": "Default document code used when creating sales invoices.",
                "default_workflow_action": "Defines whether save keeps draft, confirms, or posts immediately.",
                "enable_einvoice": "Master switch for IRN/e-invoice operations.",
                "enable_eway": "Master switch for E-Way bill operations.",
                "tcs_credit_note_policy": "Defines how TCS behaves for sales credit notes.",
            }),
            scope_subentity=True,
            capabilities={
                "has_lock_periods": True,
                "lock_period_count": SalesLockPeriod.objects.filter(entity_id=entity_id).count(),
                "has_choice_overrides": True,
                "choice_override_count": SalesChoiceOverride.objects.filter(entity_id=entity_id).count(),
                "has_policy_controls": False,
                "has_doc_number_preview": True,
            },
            current_doc_numbers=current_doc_numbers,
            lock_periods=self._list_lock_periods(SalesLockPeriod, entity_id=entity_id, subentity_id=subentity_id),
            choice_overrides=self._list_choice_overrides(SalesChoiceOverride, entity_id=entity_id, subentity_id=subentity_id),
            choice_override_catalog=choice_catalog,
        )

    def _purchase_payload(self, entity_id: int, entityfinid_id: Optional[int], subentity_id: Optional[int]):
        settings = PurchaseSettingsService.get_settings(entity_id, subentity_id)
        policy = PurchaseSettingsService.get_policy(entity_id, subentity_id)
        current_doc_numbers = None
        if entityfinid_id:
            current_doc_numbers = {
                "invoice": PurchaseSettingsService.get_current_doc_no(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, doc_key="PURCHASE_TAX_INVOICE", doc_code=settings.default_doc_code_invoice),
                "credit_note": PurchaseSettingsService.get_current_doc_no(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, doc_key="PURCHASE_CREDIT_NOTE", doc_code=settings.default_doc_code_cn),
                "debit_note": PurchaseSettingsService.get_current_doc_no(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, doc_key="PURCHASE_DEBIT_NOTE", doc_code=settings.default_doc_code_dn),
            }
        choice_catalog = PurchaseChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id)
        return self._settings_payload(
            "Purchase",
            settings={
                "default_doc_code_invoice": settings.default_doc_code_invoice,
                "default_doc_code_cn": settings.default_doc_code_cn,
                "default_doc_code_dn": settings.default_doc_code_dn,
                "default_workflow_action": settings.default_workflow_action,
                "auto_derive_tax_regime": settings.auto_derive_tax_regime,
                "enforce_2b_before_itc_claim": settings.enforce_2b_before_itc_claim,
                "itc_claim_requires_2b": policy.controls.get("itc_claim_requires_2b", "off"),
                "itc_claim_allowed_2b_statuses": policy.controls.get("itc_claim_allowed_2b_statuses", "matched,partial"),
                "itc_claim_allowed_2b_statuses_list": sorted(list(policy.itc_claim_allowed_2b_statuses)),
                "allow_mixed_taxability_in_one_bill": settings.allow_mixed_taxability_in_one_bill,
                "round_grand_total_to": settings.round_grand_total_to,
                "enable_round_off": settings.enable_round_off,
                "post_gst_tds_on_invoice": getattr(settings, "post_gst_tds_on_invoice", False),
                "policy_controls": policy.controls,
            },
            schema=_with_help([
                {"name": "default_doc_code_invoice", "label": "Invoice Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_doc_code_cn", "label": "Credit Note Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_doc_code_dn", "label": "Debit Note Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_workflow_action", "label": "Default Workflow", "type": "choice", "group": "workflow", "choices": _choice_payload(PurchaseSettings.DefaultWorkflowAction.choices)},
                {"name": "itc_claim_requires_2b", "label": "ITC Claim Requires 2B", "type": "choice", "group": "compliance", "choices": [{"value": "off", "label": "Off"}, {"value": "warn", "label": "Warn"}, {"value": "hard", "label": "Hard Block"}]},
                {"name": "itc_claim_allowed_2b_statuses", "label": "ITC Claim Allowed 2B Statuses", "type": "multi_select", "group": "compliance", "choices": [
                    {"value": "matched", "label": "Matched"},
                    {"value": "partial", "label": "Partial / Needs Review"},
                    {"value": "not_checked", "label": "Not Checked"},
                    {"value": "mismatched", "label": "Mismatched"},
                    {"value": "not_in_2b", "label": "Not in 2B"},
                    {"value": "na", "label": "Not Applicable"},
                ]},
                {"name": "policy_controls", "label": "Advanced Policy Controls", "type": "json", "group": "advanced"},
            ], {
                "default_doc_code_invoice": "Default document code used when creating purchase invoices.",
                "default_workflow_action": "Defines whether save keeps draft, confirms, or posts immediately.",
                "itc_claim_requires_2b": "Policy gate for ITC claim based on GSTR-2B status (off/warn/hard).",
                "itc_claim_allowed_2b_statuses": "Comma-separated allowed statuses: matched,partial,not_checked,mismatched,not_in_2b,na.",
                "policy_controls": "Advanced purchase governance flags for matching, settlement, and compliance.",
            }),
            scope_subentity=True,
            capabilities={
                "has_lock_periods": True,
                "lock_period_count": PurchaseLockPeriod.objects.filter(entity_id=entity_id).count(),
                "has_choice_overrides": True,
                "choice_override_count": PurchaseChoiceOverride.objects.filter(entity_id=entity_id).count(),
                "has_policy_controls": True,
                "has_doc_number_preview": True,
            },
            current_doc_numbers=current_doc_numbers,
            policy_control_schema=_policy_schema(policy.controls),
            lock_periods=self._list_lock_periods(PurchaseLockPeriod, entity_id=entity_id, subentity_id=subentity_id),
            choice_overrides=self._list_choice_overrides(PurchaseChoiceOverride, entity_id=entity_id, subentity_id=subentity_id),
            choice_override_catalog=choice_catalog,
        )

    def _payments_payload(self, entity_id: int, entityfinid_id: Optional[int], subentity_id: Optional[int]):
        settings = PaymentSettingsService.get_settings(entity_id, subentity_id)
        policy = PaymentSettingsService.get_policy(entity_id, subentity_id)
        current_doc_numbers = None
        if entityfinid_id:
            current_doc_numbers = {
                "payment_voucher": PaymentSettingsService.get_current_doc_no(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, doc_key="PAYMENT_VOUCHER", doc_code=settings.default_doc_code_payment)
            }
        return self._settings_payload(
            "Payments",
            settings={
                "default_doc_code_payment": settings.default_doc_code_payment,
                "default_workflow_action": settings.default_workflow_action,
                "policy_controls": policy.controls,
            },
            schema=_with_help([
                {"name": "default_doc_code_payment", "label": "Payment Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_workflow_action", "label": "Default Workflow", "type": "choice", "group": "workflow", "choices": _choice_payload(PaymentSettings.DefaultWorkflowAction.choices)},
                {"name": "policy_controls", "label": "Advanced Policy Controls", "type": "json", "group": "advanced"},
            ], {
                "default_doc_code_payment": "Default document code for payment vouchers.",
                "default_workflow_action": "Defines whether save keeps draft, confirms, or posts immediately.",
                "policy_controls": "Advanced payment rules for allocation, approvals, and posting checks.",
            }),
            scope_subentity=True,
            capabilities={"has_lock_periods": False, "has_choice_overrides": False, "has_policy_controls": True, "has_doc_number_preview": True},
            current_doc_numbers=current_doc_numbers,
            policy_control_schema=_policy_schema(policy.controls),
        )

    def _receipts_payload(self, entity_id: int, entityfinid_id: Optional[int], subentity_id: Optional[int]):
        settings = ReceiptSettingsService.get_settings(entity_id, subentity_id)
        policy = ReceiptSettingsService.get_policy(entity_id, subentity_id)
        current_doc_numbers = None
        if entityfinid_id:
            current_doc_numbers = {
                "receipt_voucher": ReceiptSettingsService.get_current_doc_no(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, doc_key="RECEIPT_VOUCHER", doc_code=settings.default_doc_code_receipt)
            }
        return self._settings_payload(
            "Receipts",
            settings={
                "default_doc_code_receipt": settings.default_doc_code_receipt,
                "default_workflow_action": settings.default_workflow_action,
                "policy_controls": policy.controls,
            },
            schema=_with_help([
                {"name": "default_doc_code_receipt", "label": "Receipt Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_workflow_action", "label": "Default Workflow", "type": "choice", "group": "workflow", "choices": _choice_payload(ReceiptSettings.DefaultWorkflowAction.choices)},
                {"name": "policy_controls", "label": "Advanced Policy Controls", "type": "json", "group": "advanced"},
            ], {
                "default_doc_code_receipt": "Default document code for receipt vouchers.",
                "default_workflow_action": "Defines whether save keeps draft, confirms, or posts immediately.",
                "policy_controls": "Advanced receipt rules for allocation, approvals, and posting checks.",
            }),
            scope_subentity=True,
            capabilities={"has_lock_periods": False, "has_choice_overrides": False, "has_policy_controls": True, "has_doc_number_preview": True},
            current_doc_numbers=current_doc_numbers,
            policy_control_schema=_policy_schema(policy.controls),
        )

    def _vouchers_payload(self, entity_id: int, entityfinid_id: Optional[int], subentity_id: Optional[int]):
        settings = VoucherSettingsService.get_settings(entity_id, subentity_id)
        policy = VoucherSettingsService.get_policy(entity_id, subentity_id)
        current_doc_numbers = None
        if entityfinid_id:
            current_doc_numbers = {
                "cash": VoucherSettingsService.current_doc_no_for_type(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, voucher_type="CASH"),
                "bank": VoucherSettingsService.current_doc_no_for_type(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, voucher_type="BANK"),
                "journal": VoucherSettingsService.current_doc_no_for_type(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id, voucher_type="JOURNAL"),
            }
        return self._settings_payload(
            "Vouchers",
            settings={
                "default_doc_code_cash": settings.default_doc_code_cash,
                "default_doc_code_bank": settings.default_doc_code_bank,
                "default_doc_code_journal": settings.default_doc_code_journal,
                "default_workflow_action": settings.default_workflow_action,
                "policy_controls": policy.controls,
            },
            schema=_with_help([
                {"name": "default_doc_code_cash", "label": "Cash Voucher Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_doc_code_bank", "label": "Bank Voucher Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_doc_code_journal", "label": "Journal Voucher Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_workflow_action", "label": "Default Workflow", "type": "choice", "group": "workflow", "choices": _choice_payload(VoucherSettings.DefaultWorkflowAction.choices)},
                {"name": "policy_controls", "label": "Advanced Policy Controls", "type": "json", "group": "advanced"},
            ], {
                "default_doc_code_cash": "Default code for cash vouchers.",
                "default_doc_code_bank": "Default code for bank vouchers.",
                "default_doc_code_journal": "Default code for journal vouchers.",
                "policy_controls": "Advanced voucher rules for approvals and line restrictions.",
            }),
            scope_subentity=True,
            capabilities={"has_lock_periods": False, "has_choice_overrides": False, "has_policy_controls": True, "has_doc_number_preview": True},
            current_doc_numbers=current_doc_numbers,
            policy_control_schema=_policy_schema(policy.controls),
        )

    def _assets_payload(self, entity_id: int, subentity_id: Optional[int]):
        settings = AssetSettingsService.get_settings(entity_id, subentity_id)
        return self._settings_payload(
            "Assets",
            settings={
                "default_doc_code_asset": settings.default_doc_code_asset,
                "default_doc_code_disposal": settings.default_doc_code_disposal,
                "default_workflow_action": settings.default_workflow_action,
                "default_depreciation_method": settings.default_depreciation_method,
                "default_useful_life_months": settings.default_useful_life_months,
                "default_residual_value_percent": settings.default_residual_value_percent,
                "depreciation_posting_day": settings.depreciation_posting_day,
                "allow_multiple_asset_books": settings.allow_multiple_asset_books,
                "auto_post_depreciation": settings.auto_post_depreciation,
                "auto_number_assets": settings.auto_number_assets,
                "require_asset_tag": settings.require_asset_tag,
                "enable_component_accounting": settings.enable_component_accounting,
                "enable_impairment_tracking": settings.enable_impairment_tracking,
                "capitalization_threshold": settings.capitalization_threshold,
                "policy_controls": settings.policy_controls,
            },
            schema=_with_help([
                {"name": "default_doc_code_asset", "label": "Asset Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_doc_code_disposal", "label": "Disposal Doc Code", "type": "string", "group": "numbering"},
                {"name": "default_workflow_action", "label": "Default Workflow", "type": "choice", "group": "workflow", "choices": _choice_payload(AssetSettings.DefaultWorkflowAction.choices)},
                {"name": "default_depreciation_method", "label": "Depreciation Method", "type": "choice", "group": "depreciation", "choices": _choice_payload(AssetSettings.DefaultDepreciationMethod.choices)},
                {"name": "policy_controls", "label": "Advanced Policy Controls", "type": "json", "group": "advanced"},
            ], {
                "default_doc_code_asset": "Default code for asset capitalization documents.",
                "default_doc_code_disposal": "Default code for asset disposal documents.",
                "default_depreciation_method": "Default method used when a category/asset does not override it.",
                "policy_controls": "Advanced fixed-asset rules for capitalization and depreciation handling.",
            }),
            scope_subentity=True,
            capabilities={"has_lock_periods": False, "has_choice_overrides": False, "has_policy_controls": True, "has_doc_number_preview": False},
            policy_control_schema=_policy_schema(settings.policy_controls or {}),
        )

    def _response_payload(self, request):
        entity_id, entityfinid_id, subentity_id = self._scope(request)
        return {
            "entity": entity_id,
            "entityfinid": entityfinid_id,
            "subentity": subentity_id,
            "subentity_options": self._subentity_options(entity_id),
            "modules": {
                "financial": self._financial_payload(entity_id),
                "sales": self._sales_payload(entity_id, entityfinid_id, subentity_id),
                "purchase": self._purchase_payload(entity_id, entityfinid_id, subentity_id),
                "payments": self._payments_payload(entity_id, entityfinid_id, subentity_id),
                "receipts": self._receipts_payload(entity_id, entityfinid_id, subentity_id),
                "vouchers": self._vouchers_payload(entity_id, entityfinid_id, subentity_id),
                "assets": self._assets_payload(entity_id, subentity_id),
            },
            "module_order": self.MODULE_ORDER,
        }

    def get(self, request):
        return Response(self._response_payload(request))

    @transaction.atomic
    def patch(self, request):
        entity_id, _, subentity_id = self._scope(request)
        raw_modules = request.data.get("modules") if isinstance(request.data, dict) else None
        modules = raw_modules if isinstance(raw_modules, dict) else {
            key: value for key, value in (request.data or {}).items() if key in self.MODULE_ORDER
        }
        if not modules:
            raise ValidationError({"modules": "Provide a modules object with one or more module payloads."})

        sales_choice_catalog = SalesChoicesService.get_choices(entity_id=entity_id, subentity_id=subentity_id)
        purchase_choice_catalog = PurchaseChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id)

        for module_key, payload in modules.items():
            if not isinstance(payload, dict):
                raise ValidationError({module_key: "Module payload must be an object."})
            nested_settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else None
            settings_updates = nested_settings if nested_settings is not None else payload

            if module_key == "financial":
                settings = self._financial_settings(entity_id)
                for key in {"opening_balance_edit_mode", "enforce_gst_uniqueness", "enforce_pan_uniqueness", "require_gst_for_registered_parties"}:
                    if key in settings_updates:
                        setattr(settings, key, settings_updates[key])

                policy = dict(settings.reporting_policy or {})
                pl_policy = dict(policy.get("profit_loss") or {})
                bs_policy = dict(policy.get("balance_sheet") or {})

                if "pl_accounting_only_notes_disclosure" in settings_updates:
                    pl_policy["accounting_only_notes_disclosure"] = str(settings_updates.get("pl_accounting_only_notes_disclosure") or "summary").strip().lower()
                if "pl_accounting_only_notes_split" in settings_updates:
                    pl_policy["accounting_only_notes_split"] = str(settings_updates.get("pl_accounting_only_notes_split") or "purchase_sales").strip().lower()
                if "bs_include_accounting_only_notes_disclosure" in settings_updates:
                    bs_policy["include_accounting_only_notes_disclosure"] = bool(settings_updates.get("bs_include_accounting_only_notes_disclosure"))

                if pl_policy:
                    policy["profit_loss"] = pl_policy
                if bs_policy:
                    policy["balance_sheet"] = bs_policy

                if any(
                    key in settings_updates
                    for key in {
                        "pl_accounting_only_notes_disclosure",
                        "pl_accounting_only_notes_split",
                        "bs_include_accounting_only_notes_disclosure",
                    }
                ):
                    settings.reporting_policy = policy

                settings.save()
                continue

            if module_key == "sales":
                settings = SalesSettingsService.get_settings(entity_id, subentity_id)
                editable = {
                    "default_doc_code_invoice",
                    "default_doc_code_cn",
                    "default_doc_code_dn",
                    "default_workflow_action",
                    "auto_derive_tax_regime",
                    "allow_mixed_taxability_in_one_invoice",
                    "enable_einvoice",
                    "enable_eway",
                    "einvoice_entity_applicable",
                    "eway_value_threshold",
                    "compliance_applicability_mode",
                    "auto_generate_einvoice_on_confirm",
                    "auto_generate_einvoice_on_post",
                    "auto_generate_eway_on_confirm",
                    "auto_generate_eway_on_post",
                    "prefer_irp_generate_einvoice_and_eway_together",
                    "enforce_statutory_cancel_before_business_cancel",
                    "tcs_credit_note_policy",
                    "enable_round_off",
                    "round_grand_total_to",
                }
                for key, value in settings_updates.items():
                    if key in editable:
                        setattr(settings, key, value)
                settings.save()
                if "lock_periods" in payload:
                    self._replace_lock_periods(SalesLockPeriod, payload.get("lock_periods") or [], entity_id=entity_id, subentity_id=subentity_id)
                if "choice_overrides" in payload:
                    self._replace_choice_overrides(SalesChoiceOverride, payload.get("choice_overrides") or [], entity_id=entity_id, subentity_id=subentity_id, choice_catalog=sales_choice_catalog)
                continue

            if module_key == "purchase":
                purchase_updates = dict(settings_updates)
                if (
                    "itc_claim_requires_2b" in purchase_updates
                    or "itc_claim_allowed_2b_statuses" in purchase_updates
                    or "itc_claim_allowed_2b_statuses_list" in purchase_updates
                ):
                    policy_controls = dict(purchase_updates.get("policy_controls") or {})
                    if "itc_claim_requires_2b" in purchase_updates:
                        policy_controls["itc_claim_requires_2b"] = purchase_updates.get("itc_claim_requires_2b")

                    raw = purchase_updates.get("itc_claim_allowed_2b_statuses_list", purchase_updates.get("itc_claim_allowed_2b_statuses"))
                    if raw is not None:
                        if isinstance(raw, (list, tuple, set)):
                            tokens = [str(x).strip().lower() for x in raw if str(x).strip()]
                        else:
                            tokens = [part.strip().lower() for part in str(raw or "").split(",") if part.strip()]
                        policy_controls["itc_claim_allowed_2b_statuses"] = ",".join(tokens)
                    purchase_updates["policy_controls"] = policy_controls
                purchase_updates.pop("itc_claim_requires_2b", None)
                purchase_updates.pop("itc_claim_allowed_2b_statuses", None)
                purchase_updates.pop("itc_claim_allowed_2b_statuses_list", None)

                PurchaseSettingsService.upsert_settings(entity_id=entity_id, subentity_id=subentity_id, updates=purchase_updates)
                if "lock_periods" in payload:
                    self._replace_lock_periods(PurchaseLockPeriod, payload.get("lock_periods") or [], entity_id=entity_id, subentity_id=subentity_id)
                if "choice_overrides" in payload:
                    self._replace_choice_overrides(PurchaseChoiceOverride, payload.get("choice_overrides") or [], entity_id=entity_id, subentity_id=subentity_id, choice_catalog=purchase_choice_catalog)
                continue

            if module_key == "payments":
                PaymentSettingsService.upsert_settings(entity_id=entity_id, subentity_id=subentity_id, updates=settings_updates)
                continue

            if module_key == "receipts":
                ReceiptSettingsService.upsert_settings(entity_id=entity_id, subentity_id=subentity_id, updates=settings_updates)
                continue

            if module_key == "vouchers":
                VoucherSettingsService.upsert_settings(entity_id=entity_id, subentity_id=subentity_id, updates=settings_updates)
                continue

            if module_key == "assets":
                AssetSettingsService.upsert_settings(entity_id=entity_id, subentity_id=subentity_id, updates=settings_updates, user_id=request.user.id)

        return Response(self._response_payload(request), status=status.HTTP_200_OK)


class SettingsHubLockPeriodsAPIView(SettingsHubAPIView):
    SUPPORTED_MODULES = {
        "sales": SalesLockPeriod,
        "purchase": PurchaseLockPeriod,
    }

    def get(self, request, module: str):
        entity_id, _, subentity_id = self._scope(request)
        model = self.SUPPORTED_MODULES.get(module)
        if not model:
            raise ValidationError({"module": "Unsupported module for lock periods."})
        return Response(
            {
                "module": module,
                "entity": entity_id,
                "subentity": subentity_id,
                "lock_periods": self._list_lock_periods(model, entity_id=entity_id, subentity_id=subentity_id),
                "lock_period_schema": _lock_period_schema(),
            }
        )

    @transaction.atomic
    def patch(self, request, module: str):
        entity_id, _, subentity_id = self._scope(request)
        model = self.SUPPORTED_MODULES.get(module)
        if not model:
            raise ValidationError({"module": "Unsupported module for lock periods."})
        rows = request.data.get("lock_periods") if isinstance(request.data, dict) else request.data
        if not isinstance(rows, list):
            raise ValidationError({"lock_periods": "Provide a list of lock periods."})
        self._replace_lock_periods(model, rows, entity_id=entity_id, subentity_id=subentity_id)
        return self.get(request, module)


class SettingsHubChoiceOverridesAPIView(SettingsHubAPIView):
    SUPPORTED_MODULES = {
        "sales": (SalesChoiceOverride, lambda self, entity_id, subentity_id: SalesChoicesService.get_choices(entity_id=entity_id, subentity_id=subentity_id)),
        "purchase": (PurchaseChoiceOverride, lambda self, entity_id, subentity_id: PurchaseChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id)),
    }

    def get(self, request, module: str):
        entity_id, _, subentity_id = self._scope(request)
        config = self.SUPPORTED_MODULES.get(module)
        if not config:
            raise ValidationError({"module": "Unsupported module for choice overrides."})
        model, catalog_fn = config
        catalog = catalog_fn(self, entity_id, subentity_id)
        return Response(
            {
                "module": module,
                "entity": entity_id,
                "subentity": subentity_id,
                "choice_overrides": self._list_choice_overrides(model, entity_id=entity_id, subentity_id=subentity_id),
                "choice_override_catalog": catalog,
            }
        )

    @transaction.atomic
    def patch(self, request, module: str):
        entity_id, _, subentity_id = self._scope(request)
        config = self.SUPPORTED_MODULES.get(module)
        if not config:
            raise ValidationError({"module": "Unsupported module for choice overrides."})
        model, catalog_fn = config
        rows = request.data.get("choice_overrides") if isinstance(request.data, dict) else request.data
        if not isinstance(rows, list):
            raise ValidationError({"choice_overrides": "Provide a list of choice overrides."})
        catalog = catalog_fn(self, entity_id, subentity_id)
        self._replace_choice_overrides(model, rows, entity_id=entity_id, subentity_id=subentity_id, choice_catalog=catalog)
        return self.get(request, module)
