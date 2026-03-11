from __future__ import annotations

from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product, ProductGstRate, UnitOfMeasure
from catalog.transaction_products import TransactionProductCatalogService
from entity.models import EntityFinancialYear, SubEntity
from financial.models import account
from purchase.models.purchase_config import DEFAULT_POLICY_CONTROLS
from purchase.models.purchase_ap import VendorAdvanceBalance, VendorSettlement
from purchase.models.purchase_core import PurchaseInvoiceHeader, PurchaseInvoiceLine
from purchase.models.purchase_addons import PurchaseChargeType
from purchase.models.purchase_statutory import PurchaseStatutoryChallan, PurchaseStatutoryReturn
from purchase.serializers.purchase_invoice import PurchaseInvoiceHeaderSerializer
from purchase.services.purchase_choice_service import PurchaseChoiceService
from purchase.services.purchase_settings_service import PurchaseSettingsService
from withholding.models import EntityWithholdingConfig, WithholdingSection, WithholdingTaxType


class PurchaseMetaBaseAPIView(APIView):
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
        # Frontend compatibility: treat 0 as "no subentity selected" rather than a real FK.
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
        return list(
            SubEntity.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("-ismainentity", "subentityname", "id")
            .values("id", "subentityname", "ismainentity")
        )

    def _vendors(self, entity_id: int):
        rows = list(
            account.objects.filter(entity_id=entity_id, isactive=True)
            .filter(Q(partytype__in=["Vendor", "Both", "Bank"]) | Q(partytype__isnull=True) | Q(partytype=""))
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
                "partytype": row["partytype"] or "Vendor",
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
            PurchaseChargeType.objects.filter(is_active=True)
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
                "itc_eligible_default",
                "description",
            )
        )

    def _tds_sections(self):
        return list(
            WithholdingSection.objects.filter(tax_type=WithholdingTaxType.TDS, is_active=True)
            .order_by("section_code", "id")
            .values("id", "section_code", "description", "rate_default", "threshold_default")
        )

    def _resolve_withholding_config(
        self,
        *,
        entity_id: int,
        entityfinid_id: int | None,
        subentity_id: int | None,
    ):
        if entityfinid_id is None:
            return None
        on_date = timezone.localdate()
        cfg_qs = EntityWithholdingConfig.objects.filter(
            entity_id=entity_id,
            entityfin_id=entityfinid_id,
            effective_from__lte=on_date,
        ).select_related("default_tds_section")
        if subentity_id is not None:
            cfg_qs = cfg_qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True)).order_by(
                "-subentity_id", "-effective_from", "-id"
            )
        else:
            cfg_qs = cfg_qs.filter(subentity__isnull=True).order_by("-effective_from", "-id")
        return cfg_qs.first()

    def _invoice_form_meta(self, entity_id: int, subentity_id: int | None):
        return {
            "entity_id": entity_id,
            "subentity_id": subentity_id,
            "choices": PurchaseChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id),
            "financial_years": self._financial_years(entity_id),
            "subentities": self._subentities(entity_id),
            "vendors": self._vendors(entity_id),
            "charge_types": self._charge_types(entity_id),
            "tds_sections": self._tds_sections(),
        }

    def _invoice_queryset(self, entity_id: int, entityfinid_id: int, subentity_id: int | None):
        qs = (
            PurchaseInvoiceHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
            .select_related(
                "vendor",
                "vendor__ledger",
                "vendor_state",
                "supplier_state",
                "place_of_supply_state",
                "entity",
                "entityfinid",
                "subentity",
                "ref_document",
                "tds_section",
            )
            .prefetch_related(
                Prefetch("lines", queryset=PurchaseInvoiceLine.objects.select_related("product", "uom")),
                "tax_summaries",
                "charges",
            )
        )
        if subentity_id is None:
            return qs.filter(subentity__isnull=True)
        return qs.filter(subentity_id=subentity_id)

    def _invoice_action_flags(self, header: PurchaseInvoiceHeader):
        policy = PurchaseSettingsService.get_policy(header.entity_id, header.subentity_id)
        is_draft = int(header.status) == int(PurchaseInvoiceHeader.Status.DRAFT)
        is_confirmed = int(header.status) == int(PurchaseInvoiceHeader.Status.CONFIRMED)
        is_posted = int(header.status) == int(PurchaseInvoiceHeader.Status.POSTED)
        is_cancelled = int(header.status) == int(PurchaseInvoiceHeader.Status.CANCELLED)

        delete_allowed = False
        if not is_cancelled:
            if policy.delete_policy == "draft_only":
                delete_allowed = is_draft
            elif policy.delete_policy == "non_posted":
                delete_allowed = not is_posted
            else:
                delete_allowed = False

        return {
            "can_edit": not is_posted and not is_cancelled,
            "can_confirm": is_draft,
            "can_post": is_confirmed,
            "can_cancel": is_draft or is_confirmed,
            "can_delete": delete_allowed,
            "can_rebuild_tax_summary": not is_cancelled,
            "status": int(header.status),
            "status_name": header.get_status_display(),
        }

    def _vendor_block(self, header: PurchaseInvoiceHeader):
        vendor = getattr(header, "vendor", None)
        if not vendor:
            return None
        return {
            "id": vendor.id,
            "accountname": getattr(vendor, "accountname", None),
            "display_name": getattr(vendor, "effective_accounting_name", None),
            "accountcode": getattr(vendor, "effective_accounting_code", None),
            "ledger_id": getattr(vendor, "ledger_id", None),
            "partytype": getattr(vendor, "partytype", None),
            "gstno": getattr(vendor, "gstno", None),
            "pan": getattr(vendor, "pan", None),
        }


class PurchaseInvoiceFormMetaAPIView(PurchaseMetaBaseAPIView):
    """
    One-call bootstrap for the purchase invoice create screen.
    """

    def get(self, request):
        entity_id, _, subentity_id = self._parse_scope(request, require_entityfinid=False)
        return Response(self._invoice_form_meta(entity_id, subentity_id))


class PurchaseInvoiceDetailFormMetaAPIView(PurchaseMetaBaseAPIView):
    """
    Edit/detail bootstrap: current invoice data + create-form meta + action flags.
    """

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        invoice_id = self._parse_int(request.query_params.get("invoice"), "invoice", required=True)

        header = self._invoice_queryset(entity_id, entityfinid_id, subentity_id).get(pk=invoice_id)
        invoice_data = PurchaseInvoiceHeaderSerializer(
            header,
            context={"request": request},
        ).data

        payload = self._invoice_form_meta(entity_id, subentity_id)
        payload.update(
            {
                "entityfinid_id": entityfinid_id,
                "invoice_id": invoice_id,
                "invoice": invoice_data,
                "action_flags": self._invoice_action_flags(header),
                "vendor": self._vendor_block(header),
            }
        )
        return Response(payload)


class PurchaseInvoiceSearchMetaAPIView(PurchaseMetaBaseAPIView):
    """
    Search/list popup bootstrap for filters and vendor shortlist.
    """

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        payload = {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "subentity_id": subentity_id,
            "choices": PurchaseChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id),
            "financial_years": self._financial_years(entity_id),
            "subentities": self._subentities(entity_id),
            "vendors": self._vendors(entity_id),
        }
        return Response(payload)


class PurchaseApMetaAPIView(PurchaseMetaBaseAPIView):
    """
    Shared bootstrap for AP screens: open items, advances, settlements, vendor statement.
    """

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        payload = {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "subentity_id": subentity_id,
            "financial_years": self._financial_years(entity_id),
            "subentities": self._subentities(entity_id),
            "vendors": self._vendors(entity_id),
            "settlement_statuses": [
                {"value": int(value), "label": label}
                for value, label in VendorSettlement.Status.choices
            ],
            "settlement_types": [
                {"value": value, "label": label}
                for value, label in VendorSettlement.SettlementType.choices
            ],
            "advance_source_types": [
                {"value": value, "label": label}
                for value, label in VendorAdvanceBalance.SourceType.choices
            ],
        }
        return Response(payload)


class PurchaseApSettlementFormMetaAPIView(PurchaseMetaBaseAPIView):
    """
    Settlement form bootstrap. Keeps settlement page off scattered AP defaults.
    """

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        payload = {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "subentity_id": subentity_id,
            "default_settlement_date": timezone.localdate(),
            "financial_years": self._financial_years(entity_id),
            "subentities": self._subentities(entity_id),
            "vendors": self._vendors(entity_id),
            "settlement_types": [
                {"value": value, "label": label}
                for value, label in VendorSettlement.SettlementType.choices
            ],
            "settlement_statuses": [
                {"value": int(value), "label": label}
                for value, label in VendorSettlement.Status.choices
            ],
        }
        return Response(payload)


class PurchaseInvoiceLinesMetaAPIView(PurchaseMetaBaseAPIView):
    """
    Product-entry bootstrap for purchase invoice line editing.
    """

    def get(self, request):
        entity_id, _, subentity_id = self._parse_scope(request, require_entityfinid=False)
        search = (request.query_params.get("search") or "").strip()
        as_of_date_raw = (request.query_params.get("as_of_date") or "").strip()
        as_of_date = parse_date(as_of_date_raw) if as_of_date_raw else None
        if as_of_date_raw and not as_of_date:
            raise ValidationError({"as_of_date": "Use YYYY-MM-DD format."})

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

        return Response(
            {
                "entity_id": entity_id,
                "subentity_id": subentity_id,
                "taxability_choices": PurchaseChoiceService.compile_choices(
                    entity_id=entity_id,
                    subentity_id=subentity_id,
                ).get("Taxability", []),
                "products": product_payload["items"],
                "count": product_payload["count"],
            }
        )


class PurchaseInvoiceSummaryAPIView(PurchaseMetaBaseAPIView):
    """
    Lightweight backend-driven summary for confirm/post popup or detail sidebar.
    """

    def get(self, request, pk: int):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        header = self._invoice_queryset(entity_id, entityfinid_id, subentity_id).get(pk=pk)
        line_count = header.lines.count()
        charge_count = header.charges.count()
        tax_summary_count = header.tax_summaries.count()

        return Response(
            {
                "invoice_id": header.id,
                "status": int(header.status),
                "status_name": header.get_status_display(),
                "doc_type": int(header.doc_type),
                "doc_type_name": header.get_doc_type_display(),
                "purchase_number": header.purchase_number,
                "doc_code": header.doc_code,
                "doc_no": header.doc_no,
                "bill_date": header.bill_date,
                "posting_date": header.posting_date,
                "due_date": header.due_date,
                "vendor": self._vendor_block(header),
                "totals": {
                    "total_taxable": header.total_taxable,
                    "total_gst": header.total_gst,
                    "round_off": header.round_off,
                    "grand_total": header.grand_total,
                    "tds_amount": header.tds_amount,
                    "gst_tds_amount": header.gst_tds_amount,
                },
                "counts": {
                    "lines": line_count,
                    "charges": charge_count,
                    "tax_summaries": tax_summary_count,
                },
                "action_flags": self._invoice_action_flags(header),
            }
        )


class PurchaseSettingsMetaAPIView(PurchaseMetaBaseAPIView):
    """
    One-call bootstrap for purchase settings screen.
    """

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        settings = PurchaseSettingsService.get_settings(entity_id, subentity_id)
        policy = PurchaseSettingsService.get_policy(entity_id, subentity_id)
        payload = {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "subentity_id": subentity_id,
            "financial_years": self._financial_years(entity_id),
            "subentities": self._subentities(entity_id),
            "settings": {
                "entity": settings.entity_id,
                "subentity": settings.subentity_id,
                "default_doc_code_invoice": settings.default_doc_code_invoice,
                "default_doc_code_cn": settings.default_doc_code_cn,
                "default_doc_code_dn": settings.default_doc_code_dn,
                "default_workflow_action": settings.default_workflow_action,
                "auto_derive_tax_regime": settings.auto_derive_tax_regime,
                "enforce_2b_before_itc_claim": settings.enforce_2b_before_itc_claim,
                "allow_mixed_taxability_in_one_bill": settings.allow_mixed_taxability_in_one_bill,
                "round_grand_total_to": settings.round_grand_total_to,
                "enable_round_off": settings.enable_round_off,
                "post_gst_tds_on_invoice": getattr(settings, "post_gst_tds_on_invoice", False),
                "policy_controls": policy.controls,
            },
            "defaults": {
                "policy_controls": dict(DEFAULT_POLICY_CONTROLS),
                "default_workflow_actions": [
                    {"value": value, "label": label}
                    for value, label in settings.DefaultWorkflowAction.choices
                ],
            },
        }
        return Response(payload)


class PurchaseWithholdingMetaAPIView(PurchaseMetaBaseAPIView):
    """
    Bootstrap for purchase TDS configuration and section selection.
    """

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        cfg = self._resolve_withholding_config(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
        )
        payload = {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "subentity_id": subentity_id,
            "financial_years": self._financial_years(entity_id),
            "subentities": self._subentities(entity_id),
            "tds_sections": self._tds_sections(),
            "config": {
                "enable_tds": bool(getattr(cfg, "enable_tds", True)),
                "enable_tcs": bool(getattr(cfg, "enable_tcs", True)),
                "apply_194q": bool(getattr(cfg, "apply_194q", False)),
                "apply_tcs_206c1h": bool(getattr(cfg, "apply_tcs_206c1h", False)),
                "rounding_places": getattr(cfg, "rounding_places", 2),
                "effective_from": getattr(cfg, "effective_from", None),
                "default_tds_section": getattr(cfg, "default_tds_section_id", None),
                "default_tds_section_code": (
                    getattr(getattr(cfg, "default_tds_section", None), "section_code", None)
                    if cfg is not None
                    else None
                ),
            },
        }
        return Response(payload)


class PurchaseStatutoryMetaAPIView(PurchaseMetaBaseAPIView):
    """
    Bootstrap for purchase statutory challan/return screens.
    """

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        payload = {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "subentity_id": subentity_id,
            "financial_years": self._financial_years(entity_id),
            "subentities": self._subentities(entity_id),
            "tax_types": [
                {"value": value, "label": label}
                for value, label in PurchaseStatutoryChallan.TaxType.choices
            ],
            "challan_statuses": [
                {"value": int(value), "label": label}
                for value, label in PurchaseStatutoryChallan.Status.choices
            ],
            "return_statuses": [
                {"value": int(value), "label": label}
                for value, label in PurchaseStatutoryReturn.Status.choices
            ],
            "return_codes": [
                {"value": "26Q", "label": "26Q"},
                {"value": "27Q", "label": "27Q"},
                {"value": "GSTR7", "label": "GSTR7"},
            ],
            "tds_sections": self._tds_sections(),
            "policy_controls": PurchaseSettingsService.get_policy(entity_id, subentity_id).controls,
        }
        return Response(payload)
