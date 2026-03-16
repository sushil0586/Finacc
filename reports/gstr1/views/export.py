from __future__ import annotations

from decimal import Decimal

from django.http import HttpResponse
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.gstr1.exporters.export_service import Gstr1ExportService
from reports.gstr1.serializers.section import Gstr1SectionRowSerializer
from reports.gstr1.serializers.summary import Gstr1SummarySerializer
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr1.services.section import Gstr1SectionService


class Gstr1ExportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr1ReportService
    export_service_class = Gstr1ExportService

    def initialize_request(self, request, *args, **kwargs):
        request = super().initialize_request(request, *args, **kwargs)
        if "format" in request.query_params:
            request._gstr1_export_format = request.query_params.get("format")
            mutable = request._request.GET.copy()
            mutable.pop("format", None)
            request._request.GET = mutable
        return request

    def get(self, request):
        export_format = (getattr(request, "_gstr1_export_format", None) or request.query_params.get("format") or "json").lower()
        section = request.query_params.get("section")

        service = self.service_class()
        scope = service.build_scope(request.query_params)
        exporter = self.export_service_class()

        if section:
            return self._export_section(request, service, exporter, scope, section, export_format)
        return self._export_summary(service, exporter, scope, export_format)

    def _export_summary(self, service, exporter, scope, export_format):
        payload = service.summary(scope)
        if export_format == "json":
            return Response(Gstr1SummarySerializer(payload).data)
        if export_format == "csv":
            headers = ["Section", "Documents", "Taxable", "CGST", "SGST", "IGST", "Cess", "Total"]
            rows = [
                [
                    row.get("section"),
                    row.get("document_count"),
                    row.get("taxable_amount"),
                    row.get("cgst_amount"),
                    row.get("sgst_amount"),
                    row.get("igst_amount"),
                    row.get("cess_amount"),
                    row.get("grand_total"),
                ]
                for row in payload["sections"]
            ]
            totals = _sum_section_totals(payload["sections"])
            rows.append(["TOTAL", totals["document_count"], totals["taxable_amount"], totals["cgst_amount"], totals["sgst_amount"], totals["igst_amount"], totals["cess_amount"], totals["grand_total"]])
            content = exporter.export_section_csv(headers, rows)
            return _file_response("GSTR1_Summary.csv", content, "text/csv")
        if export_format == "xlsx":
            content = exporter.export_summary_excel(
                sections=payload["sections"],
                hsn_summary=payload["hsn_summary"],
                document_summary=payload["document_summary"],
                nil_exempt_summary=payload["nil_exempt_summary"],
            )
            return _file_response(
                "GSTR1_Summary.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        return Response({"detail": "Unsupported export format."}, status=400)

    def _export_section(self, request, service, exporter, scope, section, export_format):
        qs = service.section(scope, section)
        qs = Gstr1SectionService.annotate_rows(qs).order_by("bill_date", "doc_code", "doc_no", "id")
        rows = []
        for row in qs:
            row.drilldown = Gstr1SectionService.build_drilldown(row)
            row.taxable_amount = row.signed_taxable_amount
            row.cgst_amount = row.signed_cgst_amount
            row.sgst_amount = row.signed_sgst_amount
            row.igst_amount = row.signed_igst_amount
            row.cess_amount = row.signed_cess_amount
            row.grand_total = row.signed_grand_total
            rows.append(row)

        if export_format == "json":
            return Response(Gstr1SectionRowSerializer(rows, many=True).data)

        headers = [
            "Invoice Date",
            "Posting Date",
            "Doc Type",
            "Invoice Number",
            "Customer",
            "GSTIN",
            "POS",
            "Tax Regime",
            "Taxability",
            "Supply Category",
            "Taxable",
            "CGST",
            "SGST",
            "IGST",
            "Cess",
            "Total",
            "Status",
        ]
        data_rows = []
        for row in rows:
            data_rows.append(
                [
                    _fmt_date(row.invoice_date),
                    _fmt_date(row.posting_date),
                    row.doc_type_name,
                    row.invoice_number or f"{row.doc_code}-{row.doc_no}",
                    row.customer_name,
                    row.customer_gstin,
                    row.place_of_supply_state_code,
                    row.get_tax_regime_display(),
                    row.get_taxability_display(),
                    row.get_supply_category_display(),
                    row.taxable_amount,
                    row.cgst_amount,
                    row.sgst_amount,
                    row.igst_amount,
                    row.cess_amount,
                    row.grand_total,
                    row.status_name,
                ]
            )
        totals = _sum_rows(rows)
        data_rows.append(
            [
                "TOTAL",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                totals["taxable_amount"],
                totals["cgst_amount"],
                totals["sgst_amount"],
                totals["igst_amount"],
                totals["cess_amount"],
                totals["grand_total"],
                "",
            ]
        )

        if export_format == "csv":
            content = exporter.export_section_csv(headers, data_rows)
            return _file_response(f"GSTR1_{section.upper()}.csv", content, "text/csv")
        if export_format == "xlsx":
            content = exporter.export_section_excel(
                f"GSTR1 {section.upper()}",
                f"Section: {section.upper()}",
                headers,
                data_rows,
                numeric_columns=set(range(10, len(headers))),
            )
            return _file_response(
                f"GSTR1_{section.upper()}.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        return Response({"detail": "Unsupported export format."}, status=400)


def _file_response(filename, content, content_type):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _fmt_date(value):
    if not value:
        return ""
    return value.isoformat()


def _sum_section_totals(sections):
    totals = {
        "document_count": 0,
        "taxable_amount": Decimal("0"),
        "cgst_amount": Decimal("0"),
        "sgst_amount": Decimal("0"),
        "igst_amount": Decimal("0"),
        "cess_amount": Decimal("0"),
        "grand_total": Decimal("0"),
    }
    for row in sections:
        totals["document_count"] += int(row.get("document_count") or 0)
        totals["taxable_amount"] += Decimal(row.get("taxable_amount") or 0)
        totals["cgst_amount"] += Decimal(row.get("cgst_amount") or 0)
        totals["sgst_amount"] += Decimal(row.get("sgst_amount") or 0)
        totals["igst_amount"] += Decimal(row.get("igst_amount") or 0)
        totals["cess_amount"] += Decimal(row.get("cess_amount") or 0)
        totals["grand_total"] += Decimal(row.get("grand_total") or 0)
    return totals


def _sum_rows(rows):
    totals = {
        "taxable_amount": Decimal("0"),
        "cgst_amount": Decimal("0"),
        "sgst_amount": Decimal("0"),
        "igst_amount": Decimal("0"),
        "cess_amount": Decimal("0"),
        "grand_total": Decimal("0"),
    }
    for row in rows:
        totals["taxable_amount"] += Decimal(row.taxable_amount or 0)
        totals["cgst_amount"] += Decimal(row.cgst_amount or 0)
        totals["sgst_amount"] += Decimal(row.sgst_amount or 0)
        totals["igst_amount"] += Decimal(row.igst_amount or 0)
        totals["cess_amount"] += Decimal(row.cess_amount or 0)
        totals["grand_total"] += Decimal(row.grand_total or 0)
    return totals
