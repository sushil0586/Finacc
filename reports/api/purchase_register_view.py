from __future__ import annotations

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.api.receivables_views import _write_csv, _write_excel, _write_pdf
from reports.schemas.common import build_report_envelope
from reports.serializers.purchase_register_serializer import (
    PurchaseRegisterPostingSummarySerializer,
    PurchaseRegisterRowSerializer,
    PurchaseRegisterTotalsSerializer,
)
from reports.services.payables_config import build_related_report_links, get_payables_meta_entry, resolve_report_columns
from reports.services.purchase_register_service import PurchaseRegisterService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService



def _parse_bool_param(value, *, default=False):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _purchase_register_feature_state(request):
    return {
        "include_outstanding": _parse_bool_param(request.query_params.get("include_outstanding"), default=False),
        "include_posting_summary": _parse_bool_param(request.query_params.get("include_posting_summary"), default=False),
        "include_payables_drilldowns": _parse_bool_param(request.query_params.get("include_payables_drilldowns"), default=True),
    }


def _purchase_register_meta(*, cleaned_filters, feature_state):
    report_meta = get_payables_meta_entry("purchase_register", enabled_features=feature_state)
    return {
        "report_code": "purchase-register",
        "registry_code": "purchase_register",
        "report_name": "Purchase Register",
        "label": "Purchase Register",
        "endpoint": "/api/reports/purchases/register/",
        "generated_at": timezone.now().isoformat(),
        "configuration_driven": True,
        "feature_state": feature_state,
        "supports_traceability": bool(report_meta.get("supports_traceability")),
        "supported_filters": report_meta["supported_filters"],
        "pagination_mode": report_meta["pagination_mode"],
        "view_modes": report_meta.get("view_modes", []),
        "available_columns": report_meta["available_columns"],
        "effective_columns": report_meta["enabled_columns"],
        "available_summary_blocks": report_meta["available_summary_blocks"],
        "enabled_summary_blocks": report_meta["enabled_summary_blocks"],
        "available_drilldowns": report_meta["drilldown_targets"],
        "drilldown_targets": report_meta["drilldown_targets"],
        "available_exports": report_meta["export_formats"],
        "exportable_formats": report_meta["export_formats"],
        "print_sections": report_meta["print_sections"],
        "related_reports": build_related_report_links(
            report_meta["related_reports"],
            entity_id=cleaned_filters.get("entity"),
            entityfin_id=cleaned_filters.get("entityfinid"),
            subentity_id=cleaned_filters.get("subentity"),
            from_date=cleaned_filters.get("from_date") or cleaned_filters.get("posting_from_date"),
            to_date=cleaned_filters.get("to_date") or cleaned_filters.get("posting_to_date"),
            vendor_id=cleaned_filters.get("vendor"),
        ),
    }


def _attach_purchase_register_actions(payload, request, *, export_base_path):
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("page_size", None)
    query = params.urlencode()
    payload["actions"]["can_print"] = True
    payload["actions"]["export_urls"] = {
        "excel": f"{export_base_path}excel/?{query}",
        "pdf": f"{export_base_path}pdf/?{query}",
        "csv": f"{export_base_path}csv/?{query}",
        "print": f"{export_base_path}print/?{query}",
    }
    payload["available_exports"] = ["excel", "pdf", "csv", "print"]
    return payload


class PurchaseRegisterPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class PurchaseRegisterAPIView(ScopedEntitlementMixin, APIView):
    """Purchase register list endpoint with optional payables enrichments and exports."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PurchaseRegisterPagination
    service_class = PurchaseRegisterService
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get_service_payload(self, request, *, page=None, page_size=None):
        service = self.service_class()
        feature_state = _purchase_register_feature_state(request)
        include_outstanding = feature_state["include_outstanding"]
        include_posting_summary = feature_state["include_posting_summary"]
        include_payables_drilldowns = feature_state["include_payables_drilldowns"]

        params = request.query_params.copy()
        if params.get("date_from") and not params.get("from_date"):
            params["from_date"] = params["date_from"]
        if params.get("date_to") and not params.get("to_date"):
            params["to_date"] = params["date_to"]
        queryset = service.get_base_queryset()
        queryset, cleaned_filters = service.apply_filters(queryset, params)
        self.enforce_scope(
            request,
            entity_id=cleaned_filters.get("entity"),
            entityfinid_id=cleaned_filters.get("entityfinid"),
            subentity_id=cleaned_filters.get("subentity"),
        )
        queryset = service.annotate_register_fields(queryset, include_outstanding=include_outstanding).order_by(
            "bill_date",
            "posting_date",
            "doc_code",
            "doc_no",
            "id",
        )
        totals = service.calculate_totals(queryset, include_outstanding=include_outstanding)
        posting_summary = service.calculate_posting_summary(queryset) if include_posting_summary else None

        paginator = self.pagination_class()
        if page is not None:
            request.GET._mutable = True
            request.GET["page"] = str(page)
            request.GET["page_size"] = str(page_size)
            request.GET._mutable = False
        page_obj = paginator.paginate_queryset(queryset, request, view=self)
        rows = []
        for row in page_obj:
            row.drilldown = service.build_drilldown(row)
            row.discount_total = row.discount_total_signed
            row.grand_total = row.signed_grand_total
            if include_outstanding and hasattr(row, "outstanding_amount"):
                row.outstanding_amount = row.outstanding_amount
            if include_payables_drilldowns:
                meta = service.build_payables_drilldown(
                    row,
                    entity_id=cleaned_filters.get("entity"),
                    entityfin_id=cleaned_filters.get("entityfinid"),
                    subentity_id=cleaned_filters.get("subentity"),
                    as_of_date=cleaned_filters.get("to_date") or cleaned_filters.get("posting_to_date"),
                )
                row.drilldown_targets = list(meta.keys())
                row._meta = {"drilldown": meta, "supports_drilldown": True}
            rows.append(row)

        payload = {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": PurchaseRegisterRowSerializer(rows, many=True).data,
            "totals": PurchaseRegisterTotalsSerializer(totals).data,
        }
        if include_posting_summary:
            payload["posting_summary"] = PurchaseRegisterPostingSummarySerializer(posting_summary).data
        if not include_outstanding:
            payload["totals"].pop("outstanding_amount", None)
            for row in payload["results"]:
                row.pop("outstanding_amount", None)
        return payload, cleaned_filters, paginator, feature_state

    def get(self, request):
        payload, cleaned_filters, paginator, feature_state = self.get_service_payload(request)
        response = build_report_envelope(
            report_code="purchase-register",
            report_name="Purchase Register",
            payload=payload,
            filters={
                "from_date": cleaned_filters.get("from_date"),
                "to_date": cleaned_filters.get("to_date"),
                "posting_from_date": cleaned_filters.get("posting_from_date"),
                "posting_to_date": cleaned_filters.get("posting_to_date"),
                "entity": cleaned_filters.get("entity"),
                "entityfinid": cleaned_filters.get("entityfinid"),
                "subentity": cleaned_filters.get("subentity"),
                "vendor": cleaned_filters.get("vendor"),
                "supplier_gstin": cleaned_filters.get("supplier_gstin"),
                "doc_type": request.query_params.get("doc_type"),
                "status": request.query_params.get("status"),
                "reverse_charge": cleaned_filters.get("reverse_charge"),
                "itc_eligibility": cleaned_filters.get("itc_eligibility"),
                "itc_claim_status": request.query_params.get("itc_claim_status"),
                "blocked_itc": cleaned_filters.get("blocked_itc"),
                "gstr2b_match_status": request.query_params.get("gstr2b_match_status"),
                "min_amount": cleaned_filters.get("min_amount"),
                "max_amount": cleaned_filters.get("max_amount"),
                "search": cleaned_filters.get("search"),
                "include_outstanding": feature_state["include_outstanding"],
                "include_posting_summary": feature_state["include_posting_summary"],
                "include_payables_drilldowns": feature_state["include_payables_drilldowns"],
                "page": paginator.page.number,
                "page_size": paginator.get_page_size(request),
            },
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": True,
            },
        )
        response["_meta"] = _purchase_register_meta(cleaned_filters=cleaned_filters, feature_state=feature_state)
        response["available_drilldowns"] = response["_meta"].get("available_drilldowns", [])
        response["available_exports"] = response["_meta"].get("available_exports", [])
        response["rows"] = response.get("results", [])
        response["summary"] = response.get("summary") or {"document_count": response.get("count", 0)}
        response["pagination"] = {
            "page": paginator.page.number,
            "page_size": paginator.get_page_size(request),
            "total_rows": paginator.page.paginator.count,
            "paginated": True,
        }
        return Response(_attach_purchase_register_actions(response, request, export_base_path="/api/reports/purchases/register/"))


class _BasePurchaseRegisterExportAPIView(PurchaseRegisterAPIView):
    export_mode = "attachment"

    def export_response(self, *, filename, content, content_type):
        response = HttpResponse(content, content_type=content_type)
        disposition = "inline" if self.export_mode == "inline" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response

    def report_data(self, request):
        payload, cleaned_filters, _paginator, feature_state = self.get_service_payload(request, page=1, page_size=100000)
        include_outstanding = feature_state["include_outstanding"]
        headers = [
            column["label"]
            for column in resolve_report_columns("purchase_register", enabled_features=feature_state, export=True)
        ]
        rows = []
        for row in payload["results"]:
            values = [
                row.get("bill_date"),
                row.get("posting_date"),
                row.get("doc_type_name"),
                row.get("purchase_number") or f"{row.get('doc_code')}-{row.get('doc_no')}",
                row.get("supplier_name"),
                row.get("supplier_gstin"),
                row.get("supplier_invoice_number"),
                row.get("supplier_invoice_date"),
                row.get("place_of_supply"),
                row.get("taxable_amount"),
                row.get("cgst_amount"),
                row.get("sgst_amount"),
                row.get("igst_amount"),
                row.get("cess_amount"),
                row.get("discount_total"),
                row.get("roundoff_amount"),
                row.get("grand_total"),
                row.get("status_name"),
            ]
            if include_outstanding:
                values.insert(17, row.get("outstanding_amount"))
            rows.append(values)
        subtitle = f"Entity: {cleaned_filters.get('entity')} | From: {cleaned_filters.get('from_date')} | To: {cleaned_filters.get('to_date')}"
        return payload, headers, rows, subtitle


class PurchaseRegisterExcelAPIView(_BasePurchaseRegisterExportAPIView):
    def get(self, request):
        _payload, headers, rows, subtitle = self.report_data(request)
        content = _write_excel("Purchase Register", subtitle, headers, rows, numeric_columns=set(range(9, len(headers) - 1)))
        return self.export_response(
            filename="PurchaseRegister.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class PurchaseRegisterCSVAPIView(_BasePurchaseRegisterExportAPIView):
    def get(self, request):
        _payload, headers, rows, _subtitle = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(filename="PurchaseRegister.csv", content=content, content_type="text/csv")


class PurchaseRegisterPDFAPIView(_BasePurchaseRegisterExportAPIView):
    def get(self, request):
        _payload, headers, rows, subtitle = self.report_data(request)
        content = _write_pdf("Purchase Register", subtitle, headers, rows)
        return self.export_response(filename="PurchaseRegister.pdf", content=content, content_type="application/pdf")


class PurchaseRegisterPrintAPIView(PurchaseRegisterPDFAPIView):
    export_mode = "inline"
