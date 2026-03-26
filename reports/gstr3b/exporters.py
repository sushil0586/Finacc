from __future__ import annotations

from io import BytesIO
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from reports.api.receivables_views import _write_csv


def export_gstr3b_excel(*, summary: dict, warnings: list[dict], audit_context: dict | None = None) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    header_font, header_fill, center, left, right, border = _workbook_styles()

    _write_sheet(
        wb,
        "3.1 Outward-RCM",
        ["Nature of Supplies", "Taxable Value", "CGST", "SGST", "IGST", "Cess", "Total Tax"],
        [
            ["Outward taxable supplies", *_bucket_values(summary["section_3_1"]["outward_taxable_supplies"])],
            ["Outward zero-rated supplies", *_bucket_values(summary["section_3_1"]["outward_zero_rated_supplies"])],
            ["Inward supplies liable to reverse charge", *_bucket_values(summary["section_3_1"]["inward_supplies_reverse_charge"])],
            [
                "Outward nil/exempt/non-GST",
                summary["section_3_1"]["outward_nil_exempt_non_gst"]["taxable_value"],
                0,
                0,
                0,
                0,
                0,
            ],
            [
                "Non-GST outward supplies",
                summary["section_3_1"]["non_gst_outward_supplies"]["taxable_value"],
                0,
                0,
                0,
                0,
                0,
            ],
        ],
        numeric_columns={2, 3, 4, 5, 6, 7},
        header_font=header_font,
        header_fill=header_fill,
        center=center,
        left=left,
        right=right,
        border=border,
        audit_rows=_audit_rows(audit_context),
    )
    _write_sheet(
        wb,
        "3.2 Inter-state",
        ["Supply Category", "Taxable Value", "CGST", "SGST", "IGST", "Cess", "Total Tax"],
        [
            ["Inter-state to unregistered", *_bucket_values(summary["section_3_2"]["interstate_supplies_to_unregistered"])],
            ["Inter-state to composition", *_bucket_values(summary["section_3_2"]["interstate_supplies_to_composition"])],
            ["Inter-state to UIN holders", *_bucket_values(summary["section_3_2"]["interstate_supplies_to_uin_holders"])],
        ],
        numeric_columns={2, 3, 4, 5, 6, 7},
        header_font=header_font,
        header_fill=header_fill,
        center=center,
        left=left,
        right=right,
        border=border,
        audit_rows=_audit_rows(audit_context),
    )
    _write_sheet(
        wb,
        "4 ITC",
        ["Details", "Taxable Value", "CGST", "SGST", "IGST", "Cess", "Total Tax"],
        [
            ["ITC available", *_bucket_values(summary["section_4"]["itc_available"])],
            ["ITC reversed", *_bucket_values(summary["section_4"]["itc_reversed"])],
            ["Net ITC", *_bucket_values(summary["section_4"]["net_itc"])],
        ],
        numeric_columns={2, 3, 4, 5, 6, 7},
        header_font=header_font,
        header_fill=header_fill,
        center=center,
        left=left,
        right=right,
        border=border,
        audit_rows=_audit_rows(audit_context),
    )
    _write_sheet(
        wb,
        "5.1 Inward Exempt",
        ["Details", "Taxable Value"],
        [
            ["Inward exempt / nil / non-GST", summary["section_5_1"]["inward_exempt_nil_non_gst"]["taxable_value"]],
        ],
        numeric_columns={2},
        header_font=header_font,
        header_fill=header_fill,
        center=center,
        left=left,
        right=right,
        border=border,
        audit_rows=_audit_rows(audit_context),
    )
    _write_sheet(
        wb,
        "6.1 Tax Payment",
        ["Description", "Taxable Value", "CGST", "SGST", "IGST", "Cess", "Total Tax"],
        [
            ["Tax payable", *_bucket_values(summary["section_6_1"]["tax_payable"])],
            ["Paid through ITC", *_bucket_values(summary["section_6_1"]["tax_paid_itc"])],
            ["Paid in cash", *_bucket_values(summary["section_6_1"]["tax_paid_cash"])],
            ["Balance payable", *_bucket_values(summary["section_6_1"]["balance_payable"])],
        ],
        numeric_columns={2, 3, 4, 5, 6, 7},
        header_font=header_font,
        header_fill=header_fill,
        center=center,
        left=left,
        right=right,
        border=border,
        audit_rows=_audit_rows(audit_context),
    )
    _write_sheet(
        wb,
        "Warnings",
        ["Severity", "Code", "Message"],
        [[w.get("severity"), w.get("code"), w.get("message")] for w in warnings],
        numeric_columns=set(),
        header_font=header_font,
        header_fill=header_fill,
        center=center,
        left=left,
        right=right,
        border=border,
        audit_rows=_audit_rows(audit_context),
    )

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def export_gstr3b_csv_rows(*, summary: dict, warnings: list[dict]) -> bytes:
    headers = ["Section", "Row", "Taxable Value", "CGST", "SGST", "IGST", "Cess", "Total Tax", "Severity", "Code", "Message"]
    rows = []
    rows.extend(
        [
            ["3.1", "Outward taxable supplies", *(_bucket_values(summary["section_3_1"]["outward_taxable_supplies"])), "", "", ""],
            ["3.1", "Outward zero-rated supplies", *(_bucket_values(summary["section_3_1"]["outward_zero_rated_supplies"])), "", "", ""],
            ["3.1", "Inward supplies liable to reverse charge", *(_bucket_values(summary["section_3_1"]["inward_supplies_reverse_charge"])), "", "", ""],
            ["3.2", "Inter-state to unregistered", *(_bucket_values(summary["section_3_2"]["interstate_supplies_to_unregistered"])), "", "", ""],
            ["4", "Net ITC", *(_bucket_values(summary["section_4"]["net_itc"])), "", "", ""],
            ["6.1", "Tax payable", *(_bucket_values(summary["section_6_1"]["tax_payable"])), "", "", ""],
            ["6.1", "Paid through ITC", *(_bucket_values(summary["section_6_1"]["tax_paid_itc"])), "", "", ""],
            ["6.1", "Paid in cash", *(_bucket_values(summary["section_6_1"]["tax_paid_cash"])), "", "", ""],
            ["6.1", "Balance payable", *(_bucket_values(summary["section_6_1"]["balance_payable"])), "", "", ""],
        ]
    )
    for warning in warnings:
        rows.append(["WARN", "", "", "", "", "", "", "", warning.get("severity"), warning.get("code"), warning.get("message")])
    return _write_csv(headers, rows)


def _bucket_values(bucket: dict) -> list:
    return [
        bucket.get("taxable_value", 0),
        bucket.get("cgst", 0),
        bucket.get("sgst", 0),
        bucket.get("igst", 0),
        bucket.get("cess", 0),
        bucket.get("total_tax", 0),
    ]


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
    wb: Workbook,
    title: str,
    headers: list[str],
    rows: Iterable[list],
    *,
    numeric_columns: set[int],
    header_font,
    header_fill,
    center,
    left,
    right,
    border,
    audit_rows: list[list] | None = None,
) -> None:
    ws = wb.create_sheet(title=title[:31])
    for row in audit_rows or []:
        ws.append(row)
    if audit_rows:
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


def _audit_rows(audit_context: dict | None) -> list[list]:
    if not audit_context:
        return []
    generated_on = audit_context.get("generated_on") or "-"
    scope = audit_context.get("scope") or "-"
    return [
        ["Generated On", generated_on],
        ["Scope", scope],
    ]
