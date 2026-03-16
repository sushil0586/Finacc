from __future__ import annotations

"""
Export helpers for GSTR-1. Keeps accountant-friendly column ordering, labels, and totals.
"""

from io import BytesIO
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from reports.api.receivables_views import _write_csv, _write_excel


class Gstr1ExportService:
    def export_section_csv(self, headers, rows):
        return _write_csv(headers, rows)

    def export_section_excel(self, title, subtitle, headers, rows, *, numeric_columns):
        return _write_excel(title, subtitle, headers, rows, numeric_columns=numeric_columns)

    def export_summary_excel(self, *, sections, hsn_summary, document_summary, nil_exempt_summary):
        wb = Workbook()
        wb.remove(wb.active)
        header_font, header_fill, center, left, right, border = _workbook_styles()

        _write_sheet(
            wb,
            "Section Summary",
            ["Section", "Documents", "Taxable", "CGST", "SGST", "IGST", "Cess", "Total"],
            [
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
                for row in sections
            ],
            header_font=header_font,
            header_fill=header_fill,
            center=center,
            left=left,
            right=right,
            border=border,
            numeric_columns={2, 3, 4, 5, 6, 7},
            totals_row=_totals_row(sections),
        )
        _write_sheet(
            wb,
            "HSN Summary",
            ["HSN/SAC", "Service", "GST Rate", "Qty", "Taxable", "CGST", "SGST", "IGST", "Cess", "Docs"],
            [
                [
                    row.get("hsn_sac_code"),
                    "Y" if row.get("is_service") else "N",
                    row.get("gst_rate"),
                    row.get("total_qty"),
                    row.get("taxable_value"),
                    row.get("cgst_amount"),
                    row.get("sgst_amount"),
                    row.get("igst_amount"),
                    row.get("cess_amount"),
                    row.get("document_count"),
                ]
                for row in hsn_summary
            ],
            header_font=header_font,
            header_fill=header_fill,
            center=center,
            left=left,
            right=right,
            border=border,
            numeric_columns={2, 3, 4, 5, 6, 7, 8, 9},
            totals_row=None,
        )
        _write_sheet(
            wb,
            "Document Summary",
            ["Doc Type", "Series", "Min No", "Max No", "Total", "Cancelled"],
            [
                [
                    row.get("doc_type"),
                    row.get("doc_code"),
                    row.get("min_doc_no"),
                    row.get("max_doc_no"),
                    row.get("document_count"),
                    row.get("cancelled_count"),
                ]
                for row in document_summary
            ],
            header_font=header_font,
            header_fill=header_fill,
            center=center,
            left=left,
            right=right,
            border=border,
            numeric_columns={2, 3, 4, 5},
            totals_row=None,
        )
        _write_sheet(
            wb,
            "Nil Exempt",
            ["Taxability", "Taxable", "CGST", "SGST", "IGST", "Cess"],
            [
                [
                    row.get("taxability"),
                    row.get("taxable_value"),
                    row.get("cgst_amount"),
                    row.get("sgst_amount"),
                    row.get("igst_amount"),
                    row.get("cess_amount"),
                ]
                for row in nil_exempt_summary
            ],
            header_font=header_font,
            header_fill=header_fill,
            center=center,
            left=left,
            right=right,
            border=border,
            numeric_columns={1, 2, 3, 4, 5},
            totals_row=None,
        )

        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()


def _workbook_styles():
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2F5597")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    return header_font, header_fill, center, left, right, border


def _write_sheet(
    wb,
    title,
    headers,
    rows,
    *,
    header_font,
    header_fill,
    center,
    left,
    right,
    border,
    numeric_columns,
    totals_row,
):
    ws = wb.create_sheet(title=title[:31])
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
    if totals_row:
        ws.append(totals_row)
    for row in ws.iter_rows(min_row=header_row, max_row=ws.max_row, min_col=1, max_col=len(headers)):
        for cell in row:
            cell.border = border
            if cell.row == header_row:
                continue
            cell.alignment = right if cell.column in numeric_columns else left


def _totals_row(sections):
    if not sections:
        return None
    total_documents = sum(int(row.get("document_count") or 0) for row in sections)
    total_taxable = sum(Decimal(row.get("taxable_amount") or 0) for row in sections)
    total_cgst = sum(Decimal(row.get("cgst_amount") or 0) for row in sections)
    total_sgst = sum(Decimal(row.get("sgst_amount") or 0) for row in sections)
    total_igst = sum(Decimal(row.get("igst_amount") or 0) for row in sections)
    total_cess = sum(Decimal(row.get("cess_amount") or 0) for row in sections)
    total_grand = sum(Decimal(row.get("grand_total") or 0) for row in sections)
    return ["TOTAL", total_documents, total_taxable, total_cgst, total_sgst, total_igst, total_cess, total_grand]
