from __future__ import annotations

from django.http import HttpResponse
from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from financial.models import account
from reports.api.receivables_views import _write_csv, _write_excel, _write_pdf
from reports.schemas.common import build_report_envelope
from reports.selectors.financial import resolve_scope_names
from reports.serializers.sales_register_serializer import (
    SalesRegisterRowSerializer,
    SalesRegisterTotalsSerializer,
)
from reports.services.sales_register_service import SalesRegisterService
from sales.views.rbac import require_sales_scope_permission


def _sales_register_format_scope_date(value):
    if not value:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y")
    return str(value)


def _safe_filename(value):
    text = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "").strip())
    text = text.strip("._-")
    return text or "report"


def _attach_sales_register_actions(payload, request, *, export_base_path):
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


class SalesRegisterPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class SalesRegisterAPIView(APIView):
    """Sales register endpoint with full-dataset totals plus paginated rows."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = SalesRegisterPagination
    service_class = SalesRegisterService

    def get_service_payload(self, request, *, paginate=True):
        service = self.service_class()
        queryset = service.get_base_queryset()
        queryset, cleaned_filters = service.apply_filters(queryset, request.query_params)
        require_sales_scope_permission(
            user=request.user,
            entity_id=cleaned_filters["entity"],
            permission_codes=("reports.sales_register.view", "reports.sales_register.export"),
            access_mode="operational",
            feature_code="feature_reporting",
            message="Missing permission: reports.sales_register.view",
        )
        queryset = service.annotate_register_fields(queryset).order_by(
            "bill_date",
            "posting_date",
            "doc_code",
            "doc_no",
            "id",
        )
        totals = service.calculate_totals(queryset)

        if paginate:
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(queryset, request, view=self)
            rows = []
            for row in page:
                row.drilldown = service.build_drilldown(row)
                row.grand_total = row.signed_grand_total
                rows.append(row)
            payload = {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": SalesRegisterRowSerializer(rows, many=True).data,
                "totals": SalesRegisterTotalsSerializer(totals).data,
            }
            return payload, cleaned_filters, paginator

        rows = []
        for row in queryset:
            row.drilldown = service.build_drilldown(row)
            row.grand_total = row.signed_grand_total
            rows.append(row)
        payload = {
            "count": len(rows),
            "next": None,
            "previous": None,
            "results": SalesRegisterRowSerializer(rows, many=True).data,
            "totals": SalesRegisterTotalsSerializer(totals).data,
        }
        return payload, cleaned_filters, None

    def get(self, request):
        payload, cleaned_filters, paginator = self.get_service_payload(request)

        response = build_report_envelope(
            report_code="sales-register",
            report_name="Sales Register",
            payload=payload,
            filters={
                "from_date": cleaned_filters.get("from_date"),
                "to_date": cleaned_filters.get("to_date"),
                "posting_from_date": cleaned_filters.get("posting_from_date"),
                "posting_to_date": cleaned_filters.get("posting_to_date"),
                "entity": cleaned_filters.get("entity"),
                "entityfinid": cleaned_filters.get("entityfinid"),
                "subentity": cleaned_filters.get("subentity"),
                "customer": cleaned_filters.get("customer"),
                "customer_gstin": cleaned_filters.get("customer_gstin"),
                "doc_type": request.query_params.get("doc_type"),
                "status": request.query_params.get("status"),
                "invoice_type": request.query_params.get("invoice_type"),
                "supply_classification": request.query_params.get("supply_classification"),
                "is_b2b": cleaned_filters.get("is_b2b"),
                "is_b2c": cleaned_filters.get("is_b2c"),
                "is_export": cleaned_filters.get("is_export"),
                "is_sez": cleaned_filters.get("is_sez"),
                "is_deemed_export": cleaned_filters.get("is_deemed_export"),
                "min_amount": cleaned_filters.get("min_amount"),
                "max_amount": cleaned_filters.get("max_amount"),
                "search": cleaned_filters.get("search"),
                "page": paginator.page.number if paginator else 1,
                "page_size": paginator.get_page_size(request) if paginator else len(payload.get("results", [])),
            },
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": True,
            },
        )
        return Response(_attach_sales_register_actions(response, request, export_base_path="/api/reports/sales/register/"))


class _BaseSalesRegisterExportAPIView(SalesRegisterAPIView):
    export_mode = "attachment"

    def export_response(self, *, filename, content, content_type):
        response = HttpResponse(content, content_type=content_type)
        disposition = "inline" if self.export_mode == "inline" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response

    def report_data(self, request):
        payload, cleaned_filters, _paginator = self.get_service_payload(request, paginate=False)
        scope_names = resolve_scope_names(
            cleaned_filters.get("entity"),
            cleaned_filters.get("entityfinid"),
            cleaned_filters.get("subentity"),
        )
        customer_name = "All customers"
        customer_id = cleaned_filters.get("customer")
        if customer_id:
            customer = account.objects.select_related("ledger").filter(id=customer_id).only("id", "accountname", "ledger_id", "ledger__name").first()
            if customer:
                customer_name = getattr(customer, "effective_accounting_name", None) or getattr(customer, "accountname", None) or f"Customer {customer_id}"
        headers = [
            "Invoice Date",
            "Posting Date",
            "Doc Type",
            "Doc No",
            "Invoice No",
            "Customer",
            "GSTIN",
            "Invoice Type",
            "POS",
            "Supply Class",
            "Taxable",
            "CGST",
            "SGST",
            "IGST",
            "Cess",
            "Discount",
            "Round Off",
            "Total",
            "E-Invoice No",
            "E-Way Bill No",
            "Status",
        ]
        rows = []
        for row in payload["results"]:
            rows.append([
                row.get("invoice_date"),
                row.get("posting_date"),
                row.get("doc_type_name") or row.get("doc_type"),
                row.get("doc_code") or row.get("doc_no"),
                row.get("sales_invoice_number"),
                row.get("customer_name"),
                row.get("customer_gstin"),
                row.get("invoice_type_name") or row.get("invoice_type"),
                row.get("place_of_supply"),
                row.get("supply_classification_name") or row.get("supply_classification"),
                row.get("taxable_amount"),
                row.get("cgst_amount"),
                row.get("sgst_amount"),
                row.get("igst_amount"),
                row.get("cess_amount"),
                row.get("discount_total"),
                row.get("roundoff_amount"),
                row.get("grand_total"),
                row.get("e_invoice_no"),
                row.get("e_way_bill_no"),
                row.get("status_name") or row.get("status"),
            ])
        subtitle = (
            f"Entity: {scope_names['entity_name'] or 'Selected entity'} | "
            f"FY: {scope_names['entityfin_name'] or 'Current FY'} | "
            f"Subentity: {scope_names['subentity_name'] or 'All subentities'} | "
            f"Customer: {customer_name} | "
            f"Period: {_sales_register_format_scope_date(cleaned_filters.get('from_date')) or 'Start'} "
            f"to {_sales_register_format_scope_date(cleaned_filters.get('to_date')) or 'End'}"
        )
        return payload, headers, rows, subtitle


class SalesRegisterExcelAPIView(_BaseSalesRegisterExportAPIView):
    def get(self, request):
        _payload, headers, rows, subtitle = self.report_data(request)
        content = _write_excel("Sales Register", subtitle, headers, rows, numeric_columns=set(range(10, 18)))
        return self.export_response(
            filename=f"SalesRegister_{_safe_filename(subtitle)}.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class SalesRegisterCSVAPIView(_BaseSalesRegisterExportAPIView):
    def get(self, request):
        _payload, headers, rows, subtitle = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(filename=f"SalesRegister_{_safe_filename(subtitle)}.csv", content=content, content_type="text/csv")


class SalesRegisterPDFAPIView(_BaseSalesRegisterExportAPIView):
    def get(self, request):
        _payload, headers, rows, subtitle = self.report_data(request)
        content = _write_pdf("Sales Register", subtitle, headers, rows)
        return self.export_response(filename=f"SalesRegister_{_safe_filename(subtitle)}.pdf", content=content, content_type="application/pdf")


class SalesRegisterPrintAPIView(SalesRegisterPDFAPIView):
    export_mode = "inline"
