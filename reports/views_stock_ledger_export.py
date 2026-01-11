# reports/views_stock_ledger_export.py

import io
from datetime import datetime

from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.platypus.tables import LongTable
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from reports.serializers import StockLedgerRequestSerializer
from reports.services.stock_ledger_service import compute_stock_ledger


THIN = Side(style="thin", color="999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _set_cell(ws, row, col, value, bold=False, size=None, align="left", fill=None):
    c = ws.cell(row=row, column=col, value=value)
    c.font = Font(bold=bold, size=size) if (bold or size) else Font()
    c.alignment = Alignment(horizontal=align, vertical="center")
    if fill:
        c.fill = fill
    return c


class StockLedgerExcelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = StockLedgerRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        p = ser.validated_data

        data = compute_stock_ledger(p)
        rows = data["results"]

        wb = Workbook()
        ws = wb.active
        ws.title = "Stock Ledger"

        header_fill = PatternFill("solid", fgColor="EDEDED")

        # Title
        _set_cell(ws, 1, 1, "Stock Ledger", bold=True, size=14)
        ws.merge_cells("A1:K1")

        # Meta
        _set_cell(ws, 2, 1, f"Entity: {data['entity_name']} (#{data['entity']})", bold=True)
        ws.merge_cells("A2:K2")
        _set_cell(ws, 3, 1, f"Product: {data['product_name']} (#{data['product']})", bold=True)
        ws.merge_cells("A3:K3")

        loc_txt = "ALL" if data["location"] is None else str(data["location"])
        _set_cell(ws, 4, 1, f"Location: {loc_txt}    Period: {data['from_date']} to {data['to_date']}    Method: {data['valuation_method']}")
        ws.merge_cells("A4:K4")

        # Opening/Closing
        _set_cell(ws, 5, 1, "Opening Qty", bold=True)
        _set_cell(ws, 5, 2, float(data["opening"]["qty"]))
        _set_cell(ws, 5, 4, "Opening Value", bold=True)
        _set_cell(ws, 5, 5, float(data["opening"]["value"]))

        _set_cell(ws, 6, 1, "Closing Qty", bold=True)
        _set_cell(ws, 6, 2, float(data["closing"]["qty"]))
        _set_cell(ws, 6, 4, "Closing Value", bold=True)
        _set_cell(ws, 6, 5, float(data["closing"]["value"]))

        # Table header
        headers = [
            "Date", "Txn Type", "Txn ID", "Detail ID", "Voucher No",
            "Qty In", "Qty Out", "Unit Cost", "Amount", "Balance Qty", "Balance Value"
        ]
        start_row = 8
        for col, h in enumerate(headers, 1):
            c = _set_cell(ws, start_row, col, h, bold=True, align="center", fill=header_fill)
            c.border = BORDER

        # Freeze panes below header
        ws.freeze_panes = ws["A9"]

        # Data rows
        r = start_row + 1
        for row in rows:
            values = [
                row["entrydate"].strftime("%Y-%m-%d") if row["entrydate"] else "",
                row["transactiontype"],
                row["transactionid"],
                row["detailid"],
                row["voucherno"],
                float(row["qty_in"]),
                float(row["qty_out"]),
                float(row["unit_cost"]),
                float(row["amount"]),
                float(row["balance_qty"]),
                float(row["balance_value"]),
            ]
            for col, v in enumerate(values, 1):
                c = ws.cell(row=r, column=col, value=v)
                c.border = BORDER
                if col >= 6:
                    c.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    c.alignment = Alignment(horizontal="left", vertical="center")
            r += 1

        # Auto filter
        ws.auto_filter.ref = f"A{start_row}:K{r-1}"

        # Totals row
        r += 1
        _set_cell(ws, r, 1, "TOTALS", bold=True)
        ws.merge_cells(f"A{r}:E{r}")

        totals = data["totals"]
        ws.cell(r, 6, float(totals["total_in_qty"])).font = Font(bold=True)
        ws.cell(r, 7, float(totals["total_out_qty"])).font = Font(bold=True)
        ws.cell(r, 9, float(totals["total_amount"])).font = Font(bold=True)

        # Borders for totals row
        for col in range(1, 12):
            ws.cell(r, col).border = BORDER
            ws.cell(r, col).alignment = Alignment(horizontal="right" if col >= 6 else "left", vertical="center")

        # Column widths
        col_widths = [12, 10, 10, 10, 18, 10, 10, 12, 12, 12, 14]
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

        # Number formats
        for rr in range(start_row + 1, r + 1):
            ws.cell(rr, 6).number_format = "0.0000"
            ws.cell(rr, 7).number_format = "0.0000"
            ws.cell(rr, 8).number_format = "0.0000"
            ws.cell(rr, 9).number_format = "#,##0.00"
            ws.cell(rr, 10).number_format = "0.0000"
            ws.cell(rr, 11).number_format = "#,##0.00"

        # Signature block
        r += 3
        _set_cell(ws, r, 1, "Prepared By:", bold=True)
        _set_cell(ws, r, 4, "Checked By:", bold=True)
        _set_cell(ws, r, 7, "Approved By:", bold=True)
        r += 2
        ws.merge_cells(f"A{r}:C{r}")
        ws.merge_cells(f"D{r}:F{r}")
        ws.merge_cells(f"G{r}:K{r}")
        ws.cell(r, 1, "_______________________")
        ws.cell(r, 4, "_______________________")
        ws.cell(r, 7, "_______________________")

        r += 2
        _set_cell(ws, r, 1, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        ws.merge_cells(f"A{r}:K{r}")

        # Output
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename = f"stock_ledger_{data['product']}_{data['from_date']}_to_{data['to_date']}.xlsx"
        response = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    

def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(285 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


class StockLedgerPDFAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = StockLedgerRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        p = ser.validated_data

        data = compute_stock_ledger(p)
        rows = data["results"]

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=14 * mm,
        )

        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("Stock Ledger", styles["Title"]))
        story.append(Paragraph(f"Entity: {data['entity_name']} (#{data['entity']})", styles["Normal"]))
        story.append(Paragraph(f"Product: {data['product_name']} (#{data['product']})", styles["Normal"]))
        loc_txt = "ALL" if data["location"] is None else str(data["location"])
        story.append(Paragraph(f"Location: {loc_txt}", styles["Normal"]))
        story.append(Paragraph(f"Period: {data['from_date']} to {data['to_date']} &nbsp;&nbsp;&nbsp; Method: {data['valuation_method']}", styles["Normal"]))
        story.append(Spacer(1, 6))

        story.append(Paragraph(f"Opening Qty: {data['opening']['qty']} &nbsp;&nbsp; Opening Value: {data['opening']['value']}", styles["Normal"]))
        story.append(Paragraph(f"Closing Qty: {data['closing']['qty']} &nbsp;&nbsp; Closing Value: {data['closing']['value']}", styles["Normal"]))
        story.append(Spacer(1, 8))

        # Table
        header = [
            "Date", "Txn", "TxnID", "DtlID", "Voucher",
            "Qty In", "Qty Out", "Unit Cost", "Amount", "Bal Qty", "Bal Value"
        ]
        table_data = [header]

        for r in rows:
            table_data.append([
                r["entrydate"].strftime("%Y-%m-%d") if r["entrydate"] else "",
                r["transactiontype"] or "",
                str(r["transactionid"] or ""),
                str(r["detailid"] or ""),
                r["voucherno"] or "",
                str(r["qty_in"]),
                str(r["qty_out"]),
                str(r["unit_cost"]),
                str(r["amount"]),
                str(r["balance_qty"]),
                str(r["balance_value"]),
            ])

        # Totals row
        totals = data["totals"]
        table_data.append([
            "", "", "", "", "TOTALS",
            totals["total_in_qty"],
            totals["total_out_qty"],
            "",
            totals["total_amount"],
            "",
            "",
        ])

        # Better widths for landscape A4
        col_widths = [20*mm, 12*mm, 16*mm, 14*mm, 30*mm, 18*mm, 18*mm, 20*mm, 22*mm, 20*mm, 24*mm]

        tbl = LongTable(table_data, repeatRows=1, colWidths=col_widths)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),

            ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

            # Totals row highlight (last row)
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.whitesmoke),
        ]))

        story.append(tbl)
        story.append(Spacer(1, 12))

        # Signature footer section
        sig_tbl = Table([
            ["Prepared By", "Checked By", "Approved By"],
            ["__________________________", "__________________________", "__________________________"],
            ["Date", "Date", "Date"],
            ["__________________________", "__________________________", "__________________________"],
        ], colWidths=[90*mm, 90*mm, 90*mm])

        sig_tbl.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(sig_tbl)

        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))

        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)

        buf.seek(0)
        filename = f"stock_ledger_{data['product']}_{data['from_date']}_to_{data['to_date']}.pdf"
        response = HttpResponse(buf.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
