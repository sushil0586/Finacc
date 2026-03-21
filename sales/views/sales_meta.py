from __future__ import annotations

from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.transaction_products import TransactionProductCatalogService
from entity.models import EntityFinancialYear, SubEntity
from financial.models import account
from sales.models import SalesChargeType, SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary
from sales.models.sales_ar import CustomerAdvanceBalance, CustomerSettlement
from sales.models.sales_compliance import SalesEInvoiceStatus, SalesEWayStatus
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer
from sales.services.sales_choices_service import SalesChoicesService
from core.invoice_ui_contracts import sales_invoice_ui_contract
from sales.services.sales_invoice_service import SalesInvoiceService
from sales.services.sales_settings_service import SalesSettingsService
from withholding.models import WithholdingSection, WithholdingTaxType


def _enum_choices_to_payload(enum_cls):
    out = []
    for value, label in enum_cls.choices:
        key = None
        for attr_name, attr_value in enum_cls.__dict__.items():
            if attr_value == value:
                key = attr_name
                break
        out.append({"value": value, "key": key or str(value), "label": str(label)})
    return out


class SalesMetaBaseAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _parse_int(self, raw_value, field_name: str, required: bool = False):
        if raw_value in (None, "", "null", "None"):
            if required:
                raise serializers.ValidationError({field_name: f"{field_name} query param is required"})
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            raise serializers.ValidationError({field_name: f"{field_name} must be an integer"})

    def _parse_scope(self, request, *, require_entityfinid: bool = False):
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=True)
        entityfinid_id = self._parse_int(
            request.query_params.get("entityfinid"),
            "entityfinid",
            required=require_entityfinid,
        )
        subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity", required=False)
        if subentity_id == 0:
            subentity_id = None
        return entity_id, entityfinid_id, subentity_id

    def _financial_years(self, entity_id: int):
        return list(
            EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("-isactive", "-finstartyear", "-id")
            .values("id", "finstartyear", "finendyear", "desc", "isactive")
        )

    def _subentities(self, entity_id: int):
        rows = list(
            SubEntity.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("-is_head_office", "subentityname", "id")
            .values("id", "subentityname", "is_head_office")
        )
        for row in rows:
            # Backward-compatible key for older frontend consumers.
            row["ismainentity"] = row["is_head_office"]
        return rows

    def _customers(self, entity_id: int):
        rows = list(
            account.objects.filter(entity_id=entity_id, isactive=True)
            .filter(Q(partytype__in=["Customer", "Both", "Bank"]) | Q(partytype__isnull=True) | Q(partytype=""))
            .select_related("ledger", "state", "city")
            .order_by("accountname", "id")
            .values(
                "id",
                "accountname",
                "gstno",
                "pan",
                "partytype",
                "state_id",
                "state__statecode",
                "state__statename",
                "city_id",
                "city__cityname",
                "ledger_id",
                "ledger__ledger_code",
                "ledger__name",
            )
        )
        return [
            {
                "id": row["id"],
                "accountname": row["accountname"],
                "display_name": row["ledger__name"] or row["accountname"],
                "accountcode": row["ledger__ledger_code"],
                "gstno": row["gstno"],
                "pan": row["pan"],
                "partytype": row["partytype"] or "Customer",
                "state": row["state_id"],
                "statecode": row["state__statecode"],
                "statename": row["state__statename"],
                "city": row["city_id"],
                "cityname": row["city__cityname"],
                "ledger_id": row["ledger_id"],
            }
            for row in rows
        ]

    def _charge_types(self, entity_id: int):
        return list(
            SalesChargeType.objects.filter(is_active=True)
            .filter(Q(entity_id=entity_id) | Q(entity__isnull=True))
            .order_by("entity_id", "name", "id")
            .values(
                "id",
                "code",
                "name",
                "base_category",
                "is_service",
                "hsn_sac_code_default",
                "gst_rate_default",
                "description",
                "revenue_account_id",
            )
        )

    def _tcs_sections(self):
        return list(
            WithholdingSection.objects.filter(tax_type=WithholdingTaxType.TCS, is_active=True)
            .order_by("section_code", "id")
            .values("id", "section_code", "description", "rate_default", "threshold_default")
        )

    def _invoice_form_meta(self, entity_id: int, subentity_id: int | None):
        return {
            "entity_id": entity_id,
            "subentity_id": subentity_id,
            "choices": SalesChoicesService.get_choices(entity_id=entity_id, subentity_id=subentity_id),
            "financial_years": self._financial_years(entity_id),
            "subentities": self._subentities(entity_id),
            "customers": self._customers(entity_id),
            "charge_types": self._charge_types(entity_id),
            "tcs_sections": self._tcs_sections(),
            "ui_contract": sales_invoice_ui_contract(),
        }

    def _invoice_queryset(self, entity_id: int, entityfinid_id: int, subentity_id: int | None):
        qs = (
            SalesInvoiceHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
            .select_related(
                "customer",
                "customer__ledger",
                "shipping_detail",
                "shipping_detail__state",
                "shipping_detail__city",
                "shipto_snapshot",
                "entity",
                "entityfinid",
                "subentity",
                "original_invoice",
                "tcs_section",
            )
            .prefetch_related(
                Prefetch("lines", queryset=SalesInvoiceLine.objects.select_related("product", "uom").order_by("line_no")),
                Prefetch("tax_summaries", queryset=SalesTaxSummary.objects.all()),
                "charges",
            )
        )
        if subentity_id is None:
            return qs.filter(subentity__isnull=True)
        return qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))

    def _invoice_action_flags(self, header: SalesInvoiceHeader):
        is_draft = int(header.status) == int(SalesInvoiceHeader.Status.DRAFT)
        is_confirmed = int(header.status) == int(SalesInvoiceHeader.Status.CONFIRMED)
        is_posted = int(header.status) == int(SalesInvoiceHeader.Status.POSTED)
        is_cancelled = int(header.status) == int(SalesInvoiceHeader.Status.CANCELLED)
        return {
            "can_edit": not is_posted and not is_cancelled,
            "can_confirm": is_draft,
            "can_post": is_confirmed,
            "can_cancel": is_draft or is_confirmed,
            "can_reverse": is_posted,
            "can_rebuild_tax_summary": not is_cancelled,
            "status": int(header.status),
            "status_name": header.get_status_display(),
        }

    def _customer_block(self, header: SalesInvoiceHeader):
        customer = getattr(header, "customer", None)
        if not customer:
            return None
        return {
            "id": customer.id,
            "accountname": getattr(customer, "accountname", None),
            "display_name": getattr(customer, "effective_accounting_name", None),
            "accountcode": getattr(customer, "effective_accounting_code", None),
            "ledger_id": getattr(header, "customer_ledger_id", None) or getattr(customer, "ledger_id", None),
            "partytype": getattr(customer, "partytype", None),
            "gstno": getattr(customer, "gstno", None),
            "pan": getattr(customer, "pan", None),
        }


class SalesInvoiceFormMetaAPIView(SalesMetaBaseAPIView):
    def get(self, request):
        entity_id, _, subentity_id = self._parse_scope(request, require_entityfinid=False)
        return Response(self._invoice_form_meta(entity_id, subentity_id))


class SalesInvoiceDetailFormMetaAPIView(SalesMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        invoice_id = self._parse_int(request.query_params.get("invoice"), "invoice", required=True)
        header = self._invoice_queryset(entity_id, entityfinid_id, subentity_id).get(pk=invoice_id)
        payload = self._invoice_form_meta(entity_id, subentity_id)
        payload.update(
            {
                "entityfinid_id": entityfinid_id,
                "invoice_id": invoice_id,
                "invoice": SalesInvoiceHeaderSerializer(header, context={"request": request}).data,
                "action_flags": self._invoice_action_flags(header),
                "customer": self._customer_block(header),
            }
        )
        return Response(payload)


class SalesInvoiceSearchMetaAPIView(SalesMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "choices": SalesChoicesService.get_choices(entity_id=entity_id, subentity_id=subentity_id),
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "customers": self._customers(entity_id),
            }
        )


class SalesInvoiceLinesMetaAPIView(SalesMetaBaseAPIView):
    def get(self, request):
        entity_id, _, subentity_id = self._parse_scope(request, require_entityfinid=False)
        search = (request.query_params.get("search") or "").strip()
        as_of_date_raw = (request.query_params.get("as_of_date") or "").strip()
        as_of_date = parse_date(as_of_date_raw) if as_of_date_raw else None
        if as_of_date_raw and not as_of_date:
            raise serializers.ValidationError({"as_of_date": "Use YYYY-MM-DD format."})
        try:
            limit = int(request.query_params.get("limit") or 200)
        except (TypeError, ValueError):
            limit = 200
        try:
            offset = int(request.query_params.get("offset") or 0)
        except (TypeError, ValueError):
            offset = 0

        product_payload = TransactionProductCatalogService.list_products(
            entity_id=entity_id,
            search=search,
            as_of_date=as_of_date,
            limit=max(1, min(limit, 500)),
            offset=max(0, offset),
        )
        choices = SalesChoicesService.get_choices(entity_id=entity_id, subentity_id=subentity_id)
        return Response(
            {
                "entity_id": entity_id,
                "subentity_id": subentity_id,
                "taxability_choices": choices.get("Taxability", []),
                "discount_type_choices": choices.get("DiscountType", []),
                "products": product_payload["items"],
                "count": product_payload["count"],
            }
        )


class SalesInvoiceSummaryAPIView(SalesMetaBaseAPIView):
    def get(self, request, pk: int):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        header = self._invoice_queryset(entity_id, entityfinid_id, subentity_id).get(pk=pk)
        return Response(
            {
                "invoice_id": header.id,
                "status": int(header.status),
                "status_name": header.get_status_display(),
                "doc_type": int(header.doc_type),
                "doc_type_name": header.get_doc_type_display(),
                "invoice_number": header.invoice_number,
                "doc_code": header.doc_code,
                "doc_no": header.doc_no,
                "bill_date": header.bill_date,
                "posting_date": header.posting_date,
                "due_date": header.due_date,
                "customer": self._customer_block(header),
                "totals": {
                    "total_taxable_value": header.total_taxable_value,
                    "total_cgst": header.total_cgst,
                    "total_sgst": header.total_sgst,
                    "total_igst": header.total_igst,
                    "total_cess": header.total_cess,
                    "total_discount": header.total_discount,
                    "total_other_charges": header.total_other_charges,
                    "round_off": header.round_off,
                    "grand_total": header.grand_total,
                    "tcs_amount": header.tcs_amount,
                },
                "counts": {
                    "lines": header.lines.count(),
                    "charges": header.charges.count(),
                    "tax_summaries": header.tax_summaries.count(),
                },
                "action_flags": self._invoice_action_flags(header),
            }
        )


class SalesArMetaAPIView(SalesMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "customers": self._customers(entity_id),
                "settlement_statuses": [
                    {"value": int(value), "label": label}
                    for value, label in CustomerSettlement.Status.choices
                ],
                "settlement_types": [
                    {"value": value, "label": label}
                    for value, label in CustomerSettlement.SettlementType.choices
                ],
                "advance_source_types": [
                    {"value": value, "label": label}
                    for value, label in CustomerAdvanceBalance.SourceType.choices
                ],
            }
        )


class SalesArSettlementFormMetaAPIView(SalesMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "default_settlement_date": timezone.localdate(),
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "customers": self._customers(entity_id),
                "settlement_types": [
                    {"value": value, "label": label}
                    for value, label in CustomerSettlement.SettlementType.choices
                ],
                "settlement_statuses": [
                    {"value": int(value), "label": label}
                    for value, label in CustomerSettlement.Status.choices
                ],
            }
        )


class SalesSettingsMetaAPIView(SalesMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        settings_obj = SalesInvoiceService.get_settings(entity_id, subentity_id)
        seller = SalesSettingsService.get_seller_profile(entity_id=entity_id, subentity_id=subentity_id)
        current_doc_numbers = {
            "invoice": SalesSettingsService.get_current_doc_no(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_key="sales_invoice",
                doc_code=settings_obj.default_doc_code_invoice,
            ),
            "credit_note": SalesSettingsService.get_current_doc_no(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_key="sales_credit_note",
                doc_code=settings_obj.default_doc_code_cn,
            ),
            "debit_note": SalesSettingsService.get_current_doc_no(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_key="sales_debit_note",
                doc_code=settings_obj.default_doc_code_dn,
            ),
        }
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "seller": seller,
                "settings": {
                    "default_doc_code_invoice": settings_obj.default_doc_code_invoice,
                    "default_doc_code_cn": settings_obj.default_doc_code_cn,
                    "default_doc_code_dn": settings_obj.default_doc_code_dn,
                    "default_workflow_action": settings_obj.default_workflow_action,
                    "auto_derive_tax_regime": settings_obj.auto_derive_tax_regime,
                    "allow_mixed_taxability_in_one_invoice": settings_obj.allow_mixed_taxability_in_one_invoice,
                    "enable_einvoice": settings_obj.enable_einvoice,
                    "enable_eway": settings_obj.enable_eway,
                    "einvoice_entity_applicable": settings_obj.einvoice_entity_applicable,
                    "eway_value_threshold": settings_obj.eway_value_threshold,
                    "compliance_applicability_mode": settings_obj.compliance_applicability_mode,
                    "auto_generate_einvoice_on_confirm": settings_obj.auto_generate_einvoice_on_confirm,
                    "auto_generate_einvoice_on_post": settings_obj.auto_generate_einvoice_on_post,
                    "auto_generate_eway_on_confirm": settings_obj.auto_generate_eway_on_confirm,
                    "auto_generate_eway_on_post": settings_obj.auto_generate_eway_on_post,
                    "prefer_irp_generate_einvoice_and_eway_together": settings_obj.prefer_irp_generate_einvoice_and_eway_together,
                    "enforce_statutory_cancel_before_business_cancel": settings_obj.enforce_statutory_cancel_before_business_cancel,
                    "tcs_credit_note_policy": settings_obj.tcs_credit_note_policy,
                    "enable_round_off": settings_obj.enable_round_off,
                    "round_grand_total_to": settings_obj.round_grand_total_to,
                },
                "current_doc_numbers": current_doc_numbers,
            }
        )


class SalesComplianceMetaAPIView(SalesMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        settings_obj = SalesInvoiceService.get_settings(entity_id, subentity_id)
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "choices": {
                    "gst_compliance_mode": _enum_choices_to_payload(SalesInvoiceHeader.GstComplianceMode),
                    "einvoice_status": _enum_choices_to_payload(SalesEInvoiceStatus),
                    "eway_status": _enum_choices_to_payload(SalesEWayStatus),
                },
                "tcs_sections": self._tcs_sections(),
                "settings": {
                    "enable_einvoice": settings_obj.enable_einvoice,
                    "enable_eway": settings_obj.enable_eway,
                    "einvoice_entity_applicable": settings_obj.einvoice_entity_applicable,
                    "eway_value_threshold": settings_obj.eway_value_threshold,
                    "compliance_applicability_mode": settings_obj.compliance_applicability_mode,
                    "auto_generate_einvoice_on_confirm": settings_obj.auto_generate_einvoice_on_confirm,
                    "auto_generate_einvoice_on_post": settings_obj.auto_generate_einvoice_on_post,
                    "auto_generate_eway_on_confirm": settings_obj.auto_generate_eway_on_confirm,
                    "auto_generate_eway_on_post": settings_obj.auto_generate_eway_on_post,
                    "prefer_irp_generate_einvoice_and_eway_together": settings_obj.prefer_irp_generate_einvoice_and_eway_together,
                    "enforce_statutory_cancel_before_business_cancel": settings_obj.enforce_statutory_cancel_before_business_cancel,
                    "tcs_credit_note_policy": settings_obj.tcs_credit_note_policy,
                },
            }
        )


class LegacyCombinedSalesMetaAPIView(SalesMetaBaseAPIView):
    """
    Compatibility replacement for the old /api/invoice/combinedapi endpoint.

    The legacy invoice tables were removed, so this endpoint now serves the
    same bootstrap shape from current sales metadata:
    - taxtypes     -> sales Taxability choices
    - invoicetypes -> sales DocType choices
    - branches     -> active subentities
    - defaultvalues -> derived defaults (no legacy persisted table exists now)
    """

    def get(self, request):
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=True)
        choices = SalesChoicesService.get_choices(entity_id=entity_id, subentity_id=None)
        branches = self._subentities(entity_id)

        tax_types = [
            {
                "id": row["value"],
                "taxtypename": row["label"],
                "taxtypecode": row["key"],
            }
            for row in choices.get("Taxability", [])
            if row.get("enabled", True)
        ]
        invoice_types = [
            {
                "id": row["value"],
                "invoicetype": row["label"],
                "invoicetypecode": row["key"],
            }
            for row in choices.get("DocType", [])
            if row.get("enabled", True)
        ]

        default_branch_id = next((row["id"] for row in branches if row.get("ismainentity")), None)
        if default_branch_id is None and branches:
            default_branch_id = branches[0]["id"]

        default_tax_type_id = next((row["id"] for row in tax_types if row["taxtypecode"] == "TAXABLE"), None)
        if default_tax_type_id is None and tax_types:
            default_tax_type_id = tax_types[0]["id"]

        default_invoice_type_id = next(
            (row["id"] for row in invoice_types if row["invoicetypecode"] == "TAX_INVOICE"),
            None,
        )
        if default_invoice_type_id is None and invoice_types:
            default_invoice_type_id = invoice_types[0]["id"]

        default_values = []
        if default_tax_type_id is not None or default_invoice_type_id is not None or default_branch_id is not None:
            default_values.append(
                {
                    "taxtype": default_tax_type_id,
                    "invoicetype": default_invoice_type_id,
                    "subentity": default_branch_id,
                }
            )

        return Response(
            [
                {"taxtypes": tax_types},
                {"invoicetypes": invoice_types},
                {"branches": branches},
                {"defaultvalues": default_values},
            ]
        )
