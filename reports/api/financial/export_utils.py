from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import BytesIO, StringIO
from typing import Iterable, Sequence
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

EXECUTIVE_HEADER_BG = "3F4752"
EXECUTIVE_SECTION_BG = "F2F4F7"
EXECUTIVE_SECTION_BORDER = "D0D5DD"
EXECUTIVE_ZEBRA_BG = "FAFBFC"
EXECUTIVE_TEXT_MUTED = "#667085"
EXECUTIVE_TEXT_STRONG = "#1F2937"


@dataclass(frozen=True)
class ExportSection:
    title: str
    headers: list[str]
    rows: list[list[object]]
    row_kinds: list[str] | None = None
    numeric_columns: set[int] = field(default_factory=set)
    center_columns: set[int] = field(default_factory=set)
    col_widths: list[int | float] | None = None
    empty_message: str = "No data found."


def safe_filename(value):
    text = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "").strip())
    text = text.strip("._-")
    return text or "report"


def build_report_filename(report_slug, *, entity_name=None, scope_label=None, extension):
    parts = [report_slug]
    if entity_name:
        parts.append(str(entity_name))
    if scope_label:
        parts.append(str(scope_label))
    safe_parts = [safe_filename(part) for part in parts if part]
    filename = "_".join(part for part in safe_parts if part) or safe_filename(report_slug)
    return f"{filename}.{extension.lstrip('.')}"


def filtered_querydict(request, *, exclude=None):
    params = request.GET.copy()
    for key in exclude or []:
        params.pop(key, None)
    return params.urlencode()


def attach_export_actions(payload, request, *, export_base_path, exclude=None, include_orientation=False):
    exclusions = ["page", "page_size", *(exclude or [])]
    if include_orientation:
        exclusions.append("orientation")
    query = filtered_querydict(request, exclude=exclusions)
    payload["actions"]["can_print"] = True
    payload["actions"]["export_urls"] = {
        "excel": f"{export_base_path}excel/?{query}",
        "pdf": f"{export_base_path}pdf/?{query}",
        "csv": f"{export_base_path}csv/?{query}",
        "print": f"{export_base_path}print/?{query}",
    }
    payload["available_exports"] = ["excel", "pdf", "csv", "print"]
    return payload


def workbook_styles():
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2F5597")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    return header_font, header_fill, center, left, right, border


def write_csv(headers, rows):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8-sig")


def write_sectioned_csv(*, title, meta_items=None, sections: Sequence[ExportSection]):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([title])
    for label, value in meta_items or []:
        writer.writerow([label, value])
    if meta_items:
        writer.writerow([])

    for section_index, section in enumerate(sections):
        writer.writerow([section.title])
        writer.writerow(section.headers)
        if section.rows:
            writer.writerows(section.rows)
        else:
            writer.writerow([section.empty_message, *([""] * (len(section.headers) - 1))])
        if section_index != len(sections) - 1:
            writer.writerow([])

    return buffer.getvalue().encode("utf-8-sig")


def write_excel(title, subtitle, headers, rows, *, numeric_columns=None, orientation="landscape"):
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    orientation = (orientation or "landscape").strip().lower()
    if orientation not in {"landscape", "portrait"}:
        orientation = "landscape"
    ws.page_setup.orientation = orientation
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    header_font, header_fill, center, left, right, border = workbook_styles()
    numeric_columns = set(numeric_columns or [])

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws.cell(row=1, column=1, value=title)
    ws.cell(row=1, column=1).font = Font(bold=True, size=14)
    ws.cell(row=1, column=1).alignment = left
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
    ws.cell(row=2, column=1, value=subtitle)
    ws.cell(row=2, column=1).alignment = left

    header_row = 4
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border

    summary_labels = {"totals", "summary", "balance difference", "debit total", "credit total"}
    summary_fill = PatternFill("solid", fgColor="E8F1FB")
    zebra_fill = PatternFill("solid", fgColor="F7FAFE")
    for row_index, row in enumerate(rows, start=header_row + 1):
        row_key = str(row[0] if row else "").strip().lower()
        is_summary_row = row_key in summary_labels or row_key.endswith(" total")
        for col_index, value in enumerate(row, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.border = border
            if is_summary_row:
                cell.fill = summary_fill
                cell.font = Font(bold=True)
            elif row_index % 2 == 1:
                cell.fill = zebra_fill
            cell.alignment = right if col_index in numeric_columns else left

    for col_index, header in enumerate(headers, start=1):
        width = max(len(str(header)) + 2, 14)
        for row in rows[:100]:
            width = max(width, len(str(row[col_index - 1])) + 2 if col_index - 1 < len(row) else width)
        ws.column_dimensions[get_column_letter(col_index)].width = min(width, 40)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _apply_sheet_header(ws, *, title, subtitle, column_count, left_alignment):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=column_count)
    ws.cell(row=1, column=1, value=title)
    ws.cell(row=1, column=1).font = Font(bold=True, size=14)
    ws.cell(row=1, column=1).alignment = left_alignment
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=column_count)
    ws.cell(row=2, column=1, value=subtitle)
    ws.cell(row=2, column=1).alignment = left_alignment


def _append_section_to_sheet(ws, section: ExportSection, *, start_row, header_font, header_fill, center, left, right, border):
    ws.merge_cells(start_row=start_row, start_column=1, end_row=start_row, end_column=len(section.headers))
    title_cell = ws.cell(row=start_row, column=1, value=section.title)
    title_cell.font = header_font
    title_cell.fill = header_fill
    title_cell.alignment = left
    title_cell.border = border

    header_row = start_row + 1
    for col_index, header in enumerate(section.headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border

    rows = section.rows or [[section.empty_message, *([""] * (len(section.headers) - 1))]]
    zebra_fill = PatternFill("solid", fgColor="FAFBFD")
    group_fill = PatternFill("solid", fgColor="EEF4FB")
    subtotal_fill = PatternFill("solid", fgColor="E7EDF6")
    final_fill = PatternFill("solid", fgColor="DDE7F4")
    row_kinds = list(section.row_kinds or [])
    for row_index, row in enumerate(rows, start=header_row + 1):
        row_kind = row_kinds[row_index - header_row - 1] if row_index - header_row - 1 < len(row_kinds) else "detail"
        for col_index, value in enumerate(row, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.border = border
            if row_kind == "group":
                cell.fill = group_fill
                cell.font = Font(bold=True)
            elif row_kind == "subtotal":
                cell.fill = subtotal_fill
                cell.font = Font(bold=True)
            elif row_kind in {"final_total", "difference"}:
                cell.fill = final_fill
                cell.font = Font(bold=True)
            elif row_index % 2 == 1:
                cell.fill = zebra_fill
            if (col_index - 1) in section.center_columns:
                cell.alignment = center
            elif (col_index - 1) in section.numeric_columns:
                cell.alignment = right
            else:
                cell.alignment = left

    for col_index, header in enumerate(section.headers, start=1):
        width = max(len(str(header)) + 2, 12)
        for row in rows[:100]:
            width = max(width, len(str(row[col_index - 1])) + 2 if col_index - 1 < len(row) else width)
        ws.column_dimensions[get_column_letter(col_index)].width = min(width, 36)

    return header_row + len(rows) + 2


def write_sectioned_excel(*, title, subtitle, summary_items=None, sections: Sequence[ExportSection], orientation="landscape", freeze_header=True):
    wb = Workbook()
    header_font, _header_fill, center, left, right, border = workbook_styles()
    executive_fill = PatternFill("solid", fgColor=EXECUTIVE_HEADER_BG)
    orientation = (orientation or "landscape").strip().lower()
    if orientation not in {"landscape", "portrait"}:
        orientation = "landscape"

    if summary_items:
        ws = wb.active
        ws.title = "Summary"
        ws.page_setup.orientation = orientation
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        _apply_sheet_header(ws, title=title, subtitle=subtitle, column_count=2, left_alignment=left)
        current_row = 4
        for label, value in summary_items:
            label_cell = ws.cell(row=current_row, column=1, value=label)
            value_cell = ws.cell(row=current_row, column=2, value=value)
            label_cell.font = Font(bold=True)
            label_cell.border = border
            value_cell.border = border
            if current_row % 2 == 0:
                label_cell.fill = PatternFill("solid", fgColor=EXECUTIVE_ZEBRA_BG)
                value_cell.fill = PatternFill("solid", fgColor=EXECUTIVE_ZEBRA_BG)
            label_cell.alignment = left
            value_cell.alignment = left
            current_row += 1
        ws.column_dimensions["A"].width = 24
        ws.column_dimensions["B"].width = 42
    else:
        ws = wb.active
        ws.title = (sections[0].title if sections else title)[:31]

    for index, section in enumerate(sections):
        sheet = wb.active if index == 0 and not summary_items else wb.create_sheet(section.title[:31])
        sheet.page_setup.orientation = orientation
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        _apply_sheet_header(sheet, title=title, subtitle=subtitle, column_count=len(section.headers), left_alignment=left)
        _append_section_to_sheet(
            sheet,
            section,
            start_row=4,
            header_font=header_font,
            header_fill=executive_fill,
            center=center,
            left=left,
            right=right,
            border=border,
        )
        if freeze_header:
            sheet.freeze_panes = "A6"

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def write_pdf(
    title,
    subtitle,
    headers,
    rows,
    *,
    col_widths=None,
    meta_items=None,
    numeric_columns=None,
    center_columns=None,
    pagesize=None,
    statement_layout=False,
):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=pagesize or landscape(A4), rightMargin=18, leftMargin=18, topMargin=24, bottomMargin=18)
    styles = getSampleStyleSheet()
    title_style = styles["Title"].clone("FinancialPdfTitle")
    title_style.textColor = colors.HexColor("#FFFFFF")
    title_style.alignment = 1
    title_style.leading = 18
    title_style.fontSize = 16
    title_style.spaceAfter = 0

    subtitle_style = styles["BodyText"].clone("FinancialPdfSubtitle")
    subtitle_style.fontSize = 9
    subtitle_style.leading = 11
    subtitle_style.textColor = colors.HexColor("#4A5568")
    subtitle_style.spaceAfter = 0

    meta_label_style = styles["BodyText"].clone("FinancialPdfMetaLabel")
    meta_label_style.fontSize = 7.5
    meta_label_style.leading = 9
    meta_label_style.textColor = colors.HexColor("#5B6573")
    meta_label_style.spaceAfter = 0

    meta_value_style = styles["BodyText"].clone("FinancialPdfMetaValue")
    meta_value_style.fontSize = 9
    meta_value_style.leading = 11
    meta_value_style.textColor = colors.HexColor("#1F2937")
    meta_value_style.spaceAfter = 0

    def _page_decorator(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D7E2F1"))
        canvas.setLineWidth(0.8)
        canvas.line(doc.leftMargin, doc.bottomMargin - 8, doc.pagesize[0] - doc.rightMargin, doc.bottomMargin - 8)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, doc.bottomMargin - 18, f"Page {_doc.page}")
        canvas.restoreState()

    header_rows = [[Paragraph(escape(title), title_style)]]
    header_table = Table(header_rows, colWidths=[doc.width])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2F5597")),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#2F5597")),
    ]))

    story = [header_table, Spacer(1, 8), Paragraph(escape(subtitle), subtitle_style), Spacer(1, 10)]

    if meta_items:
        meta_cards = []
        for label, value in meta_items:
            meta_cards.append(
                Paragraph(
                    f"<font color='#5B6573'><b>{escape(str(label))}:</b></font><br/><font color='#1F2937'>{escape(str(value or '-'))}</font>",
                    meta_value_style,
                )
            )
        while len(meta_cards) % 3 != 0:
            meta_cards.append(Paragraph("&nbsp;", meta_label_style))
        meta_rows = [meta_cards[index:index + 3] for index in range(0, len(meta_cards), 3)]
        meta_table = Table(meta_rows, colWidths=[doc.width / 3.0] * 3)
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F7FB")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7E2F1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7E2F1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.extend([meta_table, Spacer(1, 10)])

    numeric_columns = set(numeric_columns or [])
    center_columns = set(center_columns or [])
    table_data = [headers, *rows]
    if col_widths:
        table_data = [
            [
                value if index in numeric_columns else truncate_text(value, col_widths[index] if index < len(col_widths) else 72)
                for index, value in enumerate(row)
            ]
            for row in table_data
        ]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5597")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.25),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D6DDE8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FC")]),
    ]))
    for col_index in numeric_columns:
        table.setStyle(TableStyle([("ALIGN", (col_index, 0), (col_index, -1), "RIGHT")]))
    for col_index in center_columns:
        table.setStyle(TableStyle([("ALIGN", (col_index, 0), (col_index, -1), "CENTER")]))

    if statement_layout:
        if numeric_columns:
            for col_index in numeric_columns:
                table.setStyle(TableStyle([("RIGHTPADDING", (col_index, 1), (col_index, -1), 12)]))
        for row_index, row in enumerate(rows, start=1):
            first_value = str(row[0] if row else "").strip()
            remaining = [str(value or "").strip() for value in row[1:]]
            is_blank_row = not first_value and not any(remaining)
            is_section_row = bool(first_value) and not any(remaining)
            normalized = first_value.lower()
            is_total_row = normalized.startswith("total ") or normalized in {
                "net profit / loss",
                "gross profit",
                "gross loss",
                "balance difference",
            }
            if is_blank_row:
                table.setStyle(TableStyle([
                    ("LINEBELOW", (0, row_index), (-1, row_index), 0, colors.white),
                    ("LINEABOVE", (0, row_index), (-1, row_index), 0, colors.white),
                    ("TOPPADDING", (0, row_index), (-1, row_index), 2),
                    ("BOTTOMPADDING", (0, row_index), (-1, row_index), 2),
                    ("BACKGROUND", (0, row_index), (-1, row_index), colors.white),
                ]))
            elif is_section_row:
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#EAF1FB")),
                    ("TEXTCOLOR", (0, row_index), (-1, row_index), colors.HexColor("#1E3A5F")),
                    ("FONTNAME", (0, row_index), (-1, row_index), "Helvetica-Bold"),
                    ("LINEABOVE", (0, row_index), (-1, row_index), 0.6, colors.HexColor("#B9C7DB")),
                ]))
            elif is_total_row:
                total_row_style = [
                    ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#EEF3F9")),
                    ("FONTNAME", (0, row_index), (-1, row_index), "Helvetica-Bold"),
                    ("LINEABOVE", (0, row_index), (-1, row_index), 0.75, colors.HexColor("#8FA5C6")),
                    ("LINEBELOW", (0, row_index), (-1, row_index), 0.4, colors.HexColor("#C9D4E5")),
                ]
                if numeric_columns:
                    for col_index in numeric_columns:
                        total_row_style.append(("RIGHTPADDING", (col_index, row_index), (col_index, row_index), 4))
                table.setStyle(TableStyle(total_row_style))
            else:
                if numeric_columns:
                    table.setStyle(TableStyle([("RIGHTPADDING", (col_index, row_index), (col_index, row_index), 14) for col_index in numeric_columns]))

    story.append(table)
    doc.build(story, onFirstPage=_page_decorator, onLaterPages=_page_decorator)
    return buffer.getvalue()


def write_sectioned_pdf(*, title, subtitle, meta_items=None, sections: Sequence[ExportSection], pagesize=None, header_density="compact", metadata_visibility="compact"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=pagesize or landscape(A4), rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=14)
    styles = getSampleStyleSheet()

    title_style = styles["Title"].clone("FinancialSectionPdfTitle")
    title_style.textColor = colors.HexColor("#FFFFFF")
    title_style.alignment = 1
    title_style.leading = 15
    title_style.fontSize = 13

    subtitle_style = styles["BodyText"].clone("FinancialSectionPdfSubtitle")
    subtitle_style.fontSize = 8
    subtitle_style.leading = 9
    subtitle_style.textColor = colors.HexColor(EXECUTIVE_TEXT_MUTED)

    section_style = styles["Heading4"].clone("FinancialSectionPdfHeading")
    section_style.fontSize = 9
    section_style.leading = 10
    section_style.textColor = colors.HexColor(EXECUTIVE_TEXT_STRONG)
    section_style.spaceAfter = 4

    body_style = styles["BodyText"].clone("FinancialSectionPdfBody")
    body_style.fontSize = 7.5
    body_style.leading = 9
    body_style.textColor = colors.HexColor(EXECUTIVE_TEXT_STRONG)
    body_bold_style = body_style.clone("FinancialSectionPdfBodyBold")
    body_bold_style.fontName = "Helvetica-Bold"
    body_right_style = body_style.clone("FinancialSectionPdfBodyRight")
    body_right_style.alignment = 2
    body_right_bold_style = body_right_style.clone("FinancialSectionPdfBodyRightBold")
    body_right_bold_style.fontName = "Helvetica-Bold"
    body_center_style = body_style.clone("FinancialSectionPdfBodyCenter")
    body_center_style.alignment = 1
    body_center_bold_style = body_center_style.clone("FinancialSectionPdfBodyCenterBold")
    body_center_bold_style.fontName = "Helvetica-Bold"

    density = (header_density or "compact").strip().lower()
    if density not in {"full", "compact", "minimal"}:
        density = "compact"
    metadata_mode = (metadata_visibility or "compact").strip().lower()
    if metadata_mode not in {"full", "compact", "hide"}:
        metadata_mode = "compact"
    title_font_size = 15 if density == "full" else 13 if density == "compact" else 11
    title_leading = 17 if density == "full" else 15 if density == "compact" else 13
    subtitle_font_size = 9 if density == "full" else 8 if density == "compact" else 7.25
    subtitle_leading = 11 if density == "full" else 9 if density == "compact" else 8
    header_top = 8 if density == "full" else 6 if density == "compact" else 4
    header_bottom = 9 if density == "full" else 7 if density == "compact" else 4
    spacer_after_header = 6 if density == "full" else 4 if density == "compact" else 2
    spacer_after_subtitle = 8 if density == "full" else 6 if density == "compact" else 3

    title_style.fontSize = title_font_size
    title_style.leading = title_leading
    subtitle_style.fontSize = subtitle_font_size
    subtitle_style.leading = subtitle_leading

    story = [Table([[Paragraph(escape(title), title_style)]], colWidths=[doc.width])]
    story[0].setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(f"#{EXECUTIVE_HEADER_BG}")),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), header_top),
        ("BOTTOMPADDING", (0, 0), (-1, -1), header_bottom),
    ]))
    story.extend([Spacer(1, spacer_after_header), Paragraph(escape(subtitle), subtitle_style), Spacer(1, spacer_after_subtitle)])

    if meta_items and metadata_mode != "hide":
        visible_meta_items = meta_items
        if metadata_mode == "compact":
            visible_meta_items = meta_items[:6]
        meta_cards = [
            Paragraph(f"<b>{escape(str(label))}:</b> {escape(str(value or '-'))}", body_style)
            for label, value in visible_meta_items
        ]
        while len(meta_cards) % 3 != 0:
            meta_cards.append(Paragraph("", body_style))
        meta_rows = [meta_cards[index:index + 3] for index in range(0, len(meta_cards), 3)]
        meta_table = Table(meta_rows, colWidths=[doc.width / 3.0] * 3)
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(f"#{EXECUTIVE_SECTION_BG}")),
            ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor(f"#{EXECUTIVE_SECTION_BORDER}")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(f"#{EXECUTIVE_SECTION_BORDER}")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.extend([meta_table, Spacer(1, 4 if density == "minimal" else 6)])

    for section in sections:
        story.append(Paragraph(escape(section.title), section_style))
        rows = section.rows or [[section.empty_message, *([""] * (len(section.headers) - 1))]]
        row_kinds = list(section.row_kinds or [])
        table_rows = [section.headers]
        for row_index, row in enumerate(rows):
            row_kind = row_kinds[row_index] if row_index < len(row_kinds) else "detail"
            table_rows.append([
                value
                if isinstance(value, Paragraph)
                else Paragraph(
                    escape(str(value if value is not None else "")),
                    (
                        body_right_bold_style
                        if index in section.numeric_columns and row_kind in {"group", "subtotal", "final_total", "difference"}
                        else body_right_style
                        if index in section.numeric_columns
                        else body_center_bold_style
                        if index in section.center_columns and row_kind in {"group", "subtotal", "final_total", "difference"}
                        else body_center_style
                        if index in section.center_columns
                        else body_bold_style
                        if row_kind in {"group", "subtotal", "final_total", "difference"}
                        else body_style
                    ),
                )
                for index, value in enumerate(row)
            ])
        table = Table(table_rows, colWidths=section.col_widths, repeatRows=1)
        base_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{EXECUTIVE_HEADER_BG}")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor(f"#{EXECUTIVE_SECTION_BORDER}")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(f"#{EXECUTIVE_ZEBRA_BG}")]),
        ]
        for row_index, row_kind in enumerate(row_kinds, start=1):
            if row_kind == "group":
                base_style.extend([
                    ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#EEF4FB")),
                    ("LINEABOVE", (0, row_index), (-1, row_index), 0.45, colors.HexColor("#B9C7DB")),
                ])
            elif row_kind == "subtotal":
                base_style.extend([
                    ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#E7EDF6")),
                    ("LINEABOVE", (0, row_index), (-1, row_index), 0.55, colors.HexColor("#A5B4CA")),
                    ("LINEBELOW", (0, row_index), (-1, row_index), 0.35, colors.HexColor("#C8D2E1")),
                ])
            elif row_kind in {"final_total", "difference"}:
                base_style.extend([
                    ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#DDE7F4")),
                    ("LINEABOVE", (0, row_index), (-1, row_index), 0.75, colors.HexColor("#879AB8")),
                    ("LINEBELOW", (0, row_index), (-1, row_index), 0.45, colors.HexColor("#A7B7CD")),
                ])
        table.setStyle(TableStyle(base_style))
        for col_index in section.numeric_columns:
            table.setStyle(TableStyle([("ALIGN", (col_index, 0), (col_index, -1), "RIGHT")]))
        for col_index in section.center_columns:
            table.setStyle(TableStyle([("ALIGN", (col_index, 0), (col_index, -1), "CENTER")]))
        story.extend([table, Spacer(1, 6)])

    doc.build(story)
    return buffer.getvalue()


def write_balance_sheet_statement_pdf(
    *,
    title,
    subtitle,
    meta_items=None,
    amount_headers: Sequence[str],
    sections: Sequence[dict],
    header_density="compact",
    metadata_visibility="compact",
):
    amount_headers = list(amount_headers or ["Current"])
    amount_count = len(amount_headers)
    if amount_count <= 2:
        pagesize = A4
        amount_width = 86
    elif amount_count <= 5:
        pagesize = landscape(A4)
        amount_width = 74
    else:
        pagesize = landscape(A3)
        amount_width = 64

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=pagesize, rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=14)
    styles = getSampleStyleSheet()

    title_style = styles["Title"].clone("BalanceStatementPdfTitle")
    title_style.textColor = colors.HexColor("#FFFFFF")
    title_style.alignment = 1
    title_style.leading = 15
    title_style.fontSize = 13

    subtitle_style = styles["BodyText"].clone("BalanceStatementPdfSubtitle")
    subtitle_style.fontSize = 8
    subtitle_style.leading = 9
    subtitle_style.textColor = colors.HexColor(EXECUTIVE_TEXT_MUTED)

    body_style = styles["BodyText"].clone("BalanceStatementPdfBody")
    body_style.fontSize = 7.5
    body_style.leading = 9
    body_style.textColor = colors.HexColor(EXECUTIVE_TEXT_STRONG)
    body_bold_style = body_style.clone("BalanceStatementPdfBodyBold")
    body_bold_style.fontName = "Helvetica-Bold"
    body_bold_inverse_style = body_bold_style.clone("BalanceStatementPdfBodyBoldInverse")
    body_bold_inverse_style.textColor = colors.white
    body_italic_style = body_style.clone("BalanceStatementPdfBodyItalic")
    body_italic_style.fontName = "Helvetica-Oblique"
    body_right_style = body_style.clone("BalanceStatementPdfBodyRight")
    body_right_style.alignment = 2
    body_right_bold_style = body_right_style.clone("BalanceStatementPdfBodyRightBold")
    body_right_bold_style.fontName = "Helvetica-Bold"
    body_right_bold_inverse_style = body_right_bold_style.clone("BalanceStatementPdfBodyRightBoldInverse")
    body_right_bold_inverse_style.textColor = colors.white

    density = (header_density or "compact").strip().lower()
    if density not in {"full", "compact", "minimal"}:
        density = "compact"
    metadata_mode = (metadata_visibility or "compact").strip().lower()
    if metadata_mode not in {"full", "compact", "hide"}:
        metadata_mode = "compact"
    title_font_size = 15 if density == "full" else 13 if density == "compact" else 11
    title_leading = 17 if density == "full" else 15 if density == "compact" else 13
    subtitle_font_size = 9 if density == "full" else 8 if density == "compact" else 7.25
    subtitle_leading = 11 if density == "full" else 9 if density == "compact" else 8
    header_top = 8 if density == "full" else 6 if density == "compact" else 4
    header_bottom = 9 if density == "full" else 7 if density == "compact" else 4
    spacer_after_header = 6 if density == "full" else 4 if density == "compact" else 2
    spacer_after_subtitle = 8 if density == "full" else 6 if density == "compact" else 3

    title_style.fontSize = title_font_size
    title_style.leading = title_leading
    subtitle_style.fontSize = subtitle_font_size
    subtitle_style.leading = subtitle_leading

    story = [Table([[Paragraph(escape(title), title_style)]], colWidths=[doc.width])]
    story[0].setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(f"#{EXECUTIVE_HEADER_BG}")),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), header_top),
        ("BOTTOMPADDING", (0, 0), (-1, -1), header_bottom),
    ]))
    story.extend([Spacer(1, spacer_after_header), Paragraph(escape(subtitle), subtitle_style), Spacer(1, spacer_after_subtitle)])

    if meta_items and metadata_mode != "hide":
        visible_meta_items = meta_items[:6] if metadata_mode == "compact" else meta_items
        meta_cards = [
            Paragraph(f"<b>{escape(str(label))}:</b> {escape(str(value or '-'))}", body_style)
            for label, value in visible_meta_items
        ]
        while len(meta_cards) % 3 != 0:
            meta_cards.append(Paragraph("", body_style))
        meta_rows = [meta_cards[index:index + 3] for index in range(0, len(meta_cards), 3)]
        meta_table = Table(meta_rows, colWidths=[doc.width / 3.0] * 3)
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(f"#{EXECUTIVE_SECTION_BG}")),
            ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor(f"#{EXECUTIVE_SECTION_BORDER}")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(f"#{EXECUTIVE_SECTION_BORDER}")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.extend([meta_table, Spacer(1, 8)])

    particulars_width = max(220, doc.width - (amount_width * amount_count))
    col_widths = [particulars_width] + [amount_width] * amount_count

    for section in sections:
        section_title = str(section.get("title") or "")
        header_row = [Paragraph(escape(section_title), body_bold_style)] + [
            Paragraph(escape(str(label)), body_right_bold_inverse_style) for label in amount_headers
        ]
        header_row[0] = Paragraph(escape(section_title), body_bold_inverse_style)
        section_table = Table([header_row], colWidths=col_widths)
        section_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(f"#{EXECUTIVE_HEADER_BG}")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]))
        story.extend([section_table, Spacer(1, 3)])

        for group in section.get("groups") or []:
            group_title = str(group.get("title") or "")
            group_table = Table([[Paragraph(escape(group_title), body_italic_style)] + [""] * amount_count], colWidths=col_widths)
            group_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#DDE7F4")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.extend([group_table, Spacer(1, 2)])

            detail_rows = []
            for line in group.get("lines") or []:
                detail_rows.append(
                    [Paragraph(escape(str(line.get("label") or "")), body_style)]
                    + [Paragraph(escape(str(value or "")), body_right_style) for value in line.get("amounts") or []]
                )
            if detail_rows:
                detail_table = Table(detail_rows, colWidths=col_widths)
                detail_table.setStyle(TableStyle([
                    ("LEFTPADDING", (0, 0), (-1, -1), 20),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ]))
                story.extend([detail_table, Spacer(1, 2)])

            if group.get("total_label"):
                total_row = [Paragraph(escape(str(group.get("total_label") or "")), body_style)] + [
                    Paragraph(escape(str(value or "")), body_right_style) for value in group.get("total_amounts") or []
                ]
                total_table = Table([total_row], colWidths=col_widths)
                total_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(f"#{EXECUTIVE_SECTION_BG}")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ]))
                story.extend([total_table, Spacer(1, 8)])

        if section.get("total_label"):
            section_total_row = [Paragraph(escape(str(section.get("total_label") or "")), body_bold_style)] + [
                Paragraph(escape(str(value or "")), body_right_bold_style) for value in section.get("total_amounts") or []
            ]
            section_total_table = Table([section_total_row], colWidths=col_widths)
            section_total_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#DDE7F4")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]))
            story.extend([section_total_table, Spacer(1, 12)])

    doc.build(story)
    return buffer.getvalue()


def truncate_text(value, width_points, *, min_chars=8):
    text = "" if value is None else str(value)
    max_chars = max(min_chars, int((width_points or 72) / 5))
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return f"{text[: max_chars - 3].rstrip()}..."
