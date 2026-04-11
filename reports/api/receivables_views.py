from __future__ import annotations

import csv
from io import BytesIO, StringIO

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas as pdf_canvas
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from reports.schemas.common import build_report_envelope
from reports.schemas.receivables_reports import ReceivableAgingScopeSerializer, ReceivableReportScopeSerializer
from reports.services.receivables import build_customer_outstanding_report, build_receivable_aging_report


RECEIVABLE_DEFAULTS = {
    "default_page_size": 100,
    "decimal_places": 2,
    "show_zero_balances_default": False,
    "show_opening_balance_default": True,
    "enable_drilldown": True,
}


def _receivable_scope_filters(scope):
    return {
        "entity": scope["entity"],
        "entityfinid": scope.get("entityfinid"),
        "subentity": scope.get("subentity"),
        "from_date": scope.get("from_date"),
        "to_date": scope.get("to_date"),
        "as_of_date": scope.get("as_of_date"),
        "customer": scope.get("customer"),
        "customer_group": scope.get("customer_group"),
        "region": scope.get("region"),
        "territory": scope.get("territory"),
        "salesperson": scope.get("salesperson"),
        "currency": scope.get("currency"),
        "overdue_only": scope.get("overdue_only", False),
        "credit_limit_exceeded": scope.get("credit_limit_exceeded", False),
        "outstanding_gt": scope.get("outstanding_gt"),
        "search": scope.get("search"),
        "sort_by": scope.get("sort_by"),
        "sort_order": scope.get("sort_order", "desc"),
        "page": scope.get("page", 1),
        "page_size": scope.get("page_size", RECEIVABLE_DEFAULTS["default_page_size"]),
        "view": scope.get("view"),
    }


def _filtered_querydict(request, *, overrides=None, exclude=None):
    params = request.GET.copy()
    for key in exclude or []:
        params.pop(key, None)
    for key, value in (overrides or {}).items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = str(value)
    return params.urlencode()


def _attach_receivable_actions(payload, request, *, export_base_path):
    query = _filtered_querydict(request, exclude=["page", "page_size"])
    payload["actions"]["can_print"] = True
    payload["actions"]["export_urls"] = {
        "excel": f"{export_base_path}excel/?{query}",
        "pdf": f"{export_base_path}pdf/?{query}",
        "csv": f"{export_base_path}csv/?{query}",
        "print": f"{export_base_path}print/?{query}",
    }
    return payload


def _workbook_styles():
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2F5597")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    return header_font, header_fill, center, left, right, border


def _write_excel(title, subtitle, headers, rows, *, numeric_columns):
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    header_font, header_fill, center, left, right, border = _workbook_styles()

    ws.append([title])
    ws.append([subtitle])
    ws.append([])
    ws.append(headers)
    header_row = ws.max_row

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
        ws.column_dimensions[get_column_letter(col_idx)].width = max(len(headers[col_idx - 1]) + 4, 16)

    for row in rows:
        ws.append(row)

    for row in ws.iter_rows(min_row=header_row, max_row=ws.max_row, min_col=1, max_col=len(headers)):
        for cell in row:
            cell.border = border
            if cell.row == header_row:
                continue
            cell.alignment = right if cell.column in numeric_columns else left

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def _write_csv(headers, rows):
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _estimate_pdf_col_widths(headers, rows, *, available_width, min_width=42, max_width=150):
    sample_rows = rows[:20] if rows else []
    weights = []
    for index, header in enumerate(headers):
        cell_lengths = [len(str(header or ''))]
        for row in sample_rows:
            if index < len(row):
                cell_lengths.append(len(str(row[index] or '')))
        weights.append(max(cell_lengths))

    total_weight = sum(weights) or 1
    widths = []
    for weight in weights:
        share = available_width * (weight / total_weight)
        widths.append(max(min_width, min(max_width, share)))

    total_width = sum(widths)
    if total_width > available_width:
        scale = available_width / total_width
        widths = [width * scale for width in widths]

    return widths


def _decorate_pdf(canvas, doc, title):
    canvas.saveState()
    width, height = doc.pagesize
    top_y = height - 28
    canvas.setFillColor(colors.HexColor("#1f4e79"))
    canvas.rect(18, top_y, width - 36, 10, fill=1, stroke=0)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawRightString(width - 18, 12, f"Page {doc.page}")
    canvas.drawString(18, 12, "Finacc ERP")
    canvas.restoreState()


def _write_pdf(title, subtitle, headers, rows):
    buffer = BytesIO()
    page_width, _page_height = landscape(A4)
    available_width = page_width - 36
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=18,
        rightMargin=18,
        topMargin=18,
        bottomMargin=18,
        title=title,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PayablesPdfTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=21,
        textColor=colors.HexColor("#163b66"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "PayablesPdfSubtitle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#475569"),
    )
    chip_label_style = ParagraphStyle(
        "PayablesPdfChipLabel",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#1f2937"),
    )
    chip_value_style = ParagraphStyle(
        "PayablesPdfChipValue",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#334155"),
    )
    story = [
        Paragraph(title, title_style),
        Spacer(1, 3),
    ]

    subtitle_parts = [part.strip() for part in str(subtitle or '').split('|') if part.strip()]
    if subtitle_parts:
        chip_rows = []
        current_row = []
        for part in subtitle_parts:
            label, value = (part.split(':', 1) + [''])[:2] if ':' in part else ('', part)
            if label:
                chip = Paragraph(f"<b>{label.strip()}:</b> {value.strip()}", chip_value_style)
            else:
                chip = Paragraph(part, chip_value_style)
            current_row.append(chip)
            if len(current_row) == 4:
                chip_rows.append(current_row)
                current_row = []
        if current_row:
            chip_rows.append(current_row)

        for chip_row in chip_rows:
            chip_table = Table([chip_row], colWidths=[available_width / len(chip_row)] * len(chip_row))
            chip_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fbff")),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#c7d4e2")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d7e2ec")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(chip_table)
            story.append(Spacer(1, 4))
    else:
        story.append(Paragraph("", subtitle_style))
        story.append(Spacer(1, 4))

    col_widths = _estimate_pdf_col_widths(headers, rows, available_width=available_width)
    table = Table([headers] + rows, repeatRows=1, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d7e2ec")),
                ("FONTSIZE", (0, 1), (-1, -1), 7.4),
                ("LEADING", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#f2f6fb")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    doc.build(story, onFirstPage=lambda canvas, doc_: _decorate_pdf(canvas, doc_, title), onLaterPages=lambda canvas, doc_: _decorate_pdf(canvas, doc_, title))
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


class _BaseReceivableAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReceivableReportScopeSerializer

    def get_scope(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def build_envelope(self, *, report_code, report_name, payload, scope, request, export_base_path):
        response = build_report_envelope(
            report_code=report_code,
            report_name=report_name,
            payload=payload,
            filters=_receivable_scope_filters(scope),
            defaults=RECEIVABLE_DEFAULTS,
        )
        return _attach_receivable_actions(response, request, export_base_path=export_base_path)


class CustomerOutstandingReportAPIView(_BaseReceivableAPIView):
    serializer_class = ReceivableReportScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        data = build_customer_outstanding_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            customer_id=scope.get("customer"),
            customer_group=scope.get("customer_group"),
            region_id=scope.get("region") or scope.get("territory"),
            currency=scope.get("currency"),
            overdue_only=scope.get("overdue_only", False),
            outstanding_gt=scope.get("outstanding_gt"),
            credit_limit_exceeded=scope.get("credit_limit_exceeded", False),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", RECEIVABLE_DEFAULTS["default_page_size"]),
        )
        return Response(
            self.build_envelope(
                report_code="customer_outstanding",
                report_name="Customer Outstanding Report",
                payload=data,
                scope=scope,
                request=request,
                export_base_path="/api/reports/receivables/customer-outstanding/",
            )
        )


class ReceivableAgingReportAPIView(_BaseReceivableAPIView):
    serializer_class = ReceivableAgingScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        data = build_receivable_aging_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            customer_id=scope.get("customer"),
            customer_group=scope.get("customer_group"),
            region_id=scope.get("region") or scope.get("territory"),
            currency=scope.get("currency"),
            overdue_only=scope.get("overdue_only", False),
            credit_limit_exceeded=scope.get("credit_limit_exceeded", False),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", RECEIVABLE_DEFAULTS["default_page_size"]),
            view=scope.get("view") or "summary",
        )
        return Response(
            self.build_envelope(
                report_code="receivable_aging",
                report_name="Receivable Aging Report",
                payload=data,
                scope=scope,
                request=request,
                export_base_path="/api/reports/receivables/aging/",
            )
        )


class _BaseReceivableExportAPIView(_BaseReceivableAPIView):
    file_type = None
    export_mode = "attachment"

    def export_response(self, *, filename, content, content_type):
        response = HttpResponse(content, content_type=content_type)
        disposition = "inline" if self.export_mode == "inline" else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response


class _CustomerOutstandingExportMixin(_BaseReceivableExportAPIView):
    serializer_class = ReceivableReportScopeSerializer

    def report_data(self, request):
        scope = self.get_scope(request)
        data = build_customer_outstanding_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            customer_id=scope.get("customer"),
            customer_group=scope.get("customer_group"),
            region_id=scope.get("region") or scope.get("territory"),
            currency=scope.get("currency"),
            overdue_only=scope.get("overdue_only", False),
            outstanding_gt=scope.get("outstanding_gt"),
            credit_limit_exceeded=scope.get("credit_limit_exceeded", False),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=1,
            page_size=100000,
        )
        headers = [
            "Customer Name",
            "Customer Code",
            "Opening Balance",
            "Invoice Amount",
            "Receipt Amount",
            "Credit Note",
            "Net Outstanding",
            "Overdue Amount",
            "Unapplied Receipt",
            "Credit Limit",
            "Credit Days",
            "Last Invoice Date",
            "Last Payment Date",
            "Currency",
            "GSTIN",
        ]
        rows = [
            [
                row["customer_name"],
                row["customer_code"],
                row["opening_balance"],
                row["invoice_amount"],
                row["receipt_amount"],
                row["credit_note"],
                row["net_outstanding"],
                row["overdue_amount"],
                row["unapplied_receipt"],
                row["credit_limit"],
                row["credit_days"],
                row["last_invoice_date"],
                row["last_payment_date"],
                row["currency"],
                row["gstin"],
            ]
            for row in data["rows"]
        ]
        subtitle = f"Entity: {scope['entity']} | As of: {scope.get('as_of_date') or scope.get('to_date')}"
        return scope, data, headers, rows, subtitle


class CustomerOutstandingExcelAPIView(_CustomerOutstandingExportMixin):
    def get(self, request):
        scope, _data, headers, rows, subtitle = self.report_data(request)
        content = _write_excel("Customer Outstanding", subtitle, headers, rows, numeric_columns=set(range(3, 12)))
        return self.export_response(
            filename=f"CustomerOutstanding_Entity{scope['entity']}.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class CustomerOutstandingCSVAPIView(_CustomerOutstandingExportMixin):
    def get(self, request):
        scope, _data, headers, rows, _subtitle = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(
            filename=f"CustomerOutstanding_Entity{scope['entity']}.csv",
            content=content,
            content_type="text/csv",
        )


class CustomerOutstandingPDFAPIView(_CustomerOutstandingExportMixin):
    def get(self, request):
        scope, _data, headers, rows, subtitle = self.report_data(request)
        content = _write_pdf("Customer Outstanding Report", subtitle, headers, rows)
        return self.export_response(
            filename=f"CustomerOutstanding_Entity{scope['entity']}.pdf",
            content=content,
            content_type="application/pdf",
        )


class CustomerOutstandingPrintAPIView(CustomerOutstandingPDFAPIView):
    export_mode = "inline"


class _ReceivableAgingExportMixin(_BaseReceivableExportAPIView):
    serializer_class = ReceivableAgingScopeSerializer

    def report_data(self, request):
        scope = self.get_scope(request)
        data = build_receivable_aging_report(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            as_of_date=scope.get("as_of_date") or scope.get("to_date"),
            customer_id=scope.get("customer"),
            customer_group=scope.get("customer_group"),
            region_id=scope.get("region") or scope.get("territory"),
            currency=scope.get("currency"),
            overdue_only=scope.get("overdue_only", False),
            credit_limit_exceeded=scope.get("credit_limit_exceeded", False),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "desc"),
            page=1,
            page_size=100000,
            view=scope.get("view") or "summary",
        )
        if (scope.get("view") or "summary") == "invoice":
            headers = [
                "Customer",
                "Customer Code",
                "Invoice Number",
                "Invoice Date",
                "Due Date",
                "Credit Days",
                "Invoice Amount",
                "Received Amount",
                "Balance",
                "Current",
                "1-30",
                "31-60",
                "61-90",
                "90+",
                "Currency",
            ]
            rows = [
                [
                    row["customer_name"],
                    row["customer_code"],
                    row["invoice_number"],
                    row["invoice_date"],
                    row["due_date"],
                    row["credit_days"],
                    row["invoice_amount"],
                    row["received_amount"],
                    row["balance"],
                    row["current"],
                    row["bucket_1_30"],
                    row["bucket_31_60"],
                    row["bucket_61_90"],
                    row["bucket_90_plus"],
                    row["currency"],
                ]
                for row in data["rows"]
            ]
            title = "Receivable Aging Invoice Report"
            numeric_columns = set(range(6, 15))
        else:
            headers = [
                "Customer",
                "Customer Code",
                "Outstanding",
                "Overdue Amount",
                "Current",
                "1-30",
                "31-60",
                "61-90",
                "90+",
                "Unapplied Receipt",
                "Credit Limit",
                "Credit Days",
                "Last Payment Date",
                "Currency",
            ]
            rows = [
                [
                    row["customer_name"],
                    row["customer_code"],
                    row["outstanding"],
                    row["overdue_amount"],
                    row["current"],
                    row["bucket_1_30"],
                    row["bucket_31_60"],
                    row["bucket_61_90"],
                    row["bucket_90_plus"],
                    row["unapplied_receipt"],
                    row["credit_limit"],
                    row["credit_days"],
                    row["last_payment_date"],
                    row["currency"],
                ]
                for row in data["rows"]
            ]
            title = "Receivable Aging Summary Report"
            numeric_columns = set(range(3, 12))
        subtitle = f"Entity: {scope['entity']} | As of: {scope.get('as_of_date') or scope.get('to_date')} | View: {scope.get('view') or 'summary'}"
        return scope, headers, rows, subtitle, title, numeric_columns


class ReceivableAgingExcelAPIView(_ReceivableAgingExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle, title, numeric_columns = self.report_data(request)
        content = _write_excel(title, subtitle, headers, rows, numeric_columns=numeric_columns)
        return self.export_response(
            filename=f"ReceivableAging_Entity{scope['entity']}_{scope.get('view') or 'summary'}.xlsx",
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class ReceivableAgingCSVAPIView(_ReceivableAgingExportMixin):
    def get(self, request):
        scope, headers, rows, _subtitle, _title, _numeric_columns = self.report_data(request)
        content = _write_csv(headers, rows)
        return self.export_response(
            filename=f"ReceivableAging_Entity{scope['entity']}_{scope.get('view') or 'summary'}.csv",
            content=content,
            content_type="text/csv",
        )


class ReceivableAgingPDFAPIView(_ReceivableAgingExportMixin):
    def get(self, request):
        scope, headers, rows, subtitle, title, _numeric_columns = self.report_data(request)
        content = _write_pdf(title, subtitle, headers, rows)
        return self.export_response(
            filename=f"ReceivableAging_Entity{scope['entity']}_{scope.get('view') or 'summary'}.pdf",
            content=content,
            content_type="application/pdf",
        )


class ReceivableAgingPrintAPIView(ReceivableAgingPDFAPIView):
    export_mode = "inline"
