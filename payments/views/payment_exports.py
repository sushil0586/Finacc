from __future__ import annotations

from io import BytesIO

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from payments.models import PaymentVoucherAllocation, PaymentVoucherHeader


class PaymentVoucherPDFAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _scope_ids(self, request):
        entity = request.query_params.get("entity")
        entityfinid = request.query_params.get("entityfinid")
        subentity = request.query_params.get("subentity")
        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})
        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
        return entity_id, entityfinid_id, subentity_id

    def get(self, request, pk: int):
        entity_id, entityfinid_id, subentity_id = self._scope_ids(request)
        qs = (
            PaymentVoucherHeader.objects
            .filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
            .select_related("paid_from", "paid_to", "payment_mode", "entity", "entityfinid", "subentity")
            .prefetch_related(
                "adjustments",
                "advance_adjustments__advance_balance__payment_voucher",
                "allocations__open_item",
            )
        )
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        voucher = qs.get(pk=pk)

        disposition = (request.query_params.get("disposition") or "inline").strip().lower()
        if disposition not in {"inline", "attachment"}:
            disposition = "inline"

        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
        )
        styles = getSampleStyleSheet()
        elems = []

        title = voucher.voucher_code or f"{voucher.doc_code}-{voucher.doc_no or ''}".strip("-")
        elems.append(Paragraph(f"Payment Voucher: {title}", styles["Title"]))
        elems.append(Spacer(1, 4 * mm))

        header_rows = [
            ["Voucher Date", str(voucher.voucher_date), "Status", voucher.get_status_display()],
            ["Payment Type", voucher.get_payment_type_display(), "Supply Type", voucher.get_supply_type_display()],
            ["Paid From", getattr(voucher.paid_from, "accountname", ""), "Paid To", getattr(voucher.paid_to, "accountname", "")],
            ["Payment Mode", getattr(voucher.payment_mode, "paymentmode", "") or "", "Reference No", voucher.reference_number or ""],
            ["Cash Paid", str(voucher.cash_paid_amount), "Settlement Support", str(voucher.settlement_effective_amount)],
        ]
        header_table = Table(header_rows, colWidths=[32 * mm, 58 * mm, 32 * mm, 58 * mm])
        header_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elems.append(header_table)
        elems.append(Spacer(1, 5 * mm))

        alloc_rows = [["Bill", "Supplier Invoice", "Settled Amount", "Full?"]]
        for row in voucher.allocations.all():
            item = getattr(row, "open_item", None)
            alloc_rows.append([
                getattr(item, "purchase_number", "") or f"Open Item {getattr(item, 'id', '')}",
                getattr(item, "supplier_invoice_number", "") or "",
                str(row.settled_amount),
                "Yes" if row.is_full_settlement else "No",
            ])
        if len(alloc_rows) > 1:
            elems.append(Paragraph("Allocations", styles["Heading3"]))
            alloc_table = Table(alloc_rows, colWidths=[50 * mm, 55 * mm, 35 * mm, 20 * mm])
            alloc_table.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eef5")),
            ]))
            elems.append(alloc_table)
            elems.append(Spacer(1, 4 * mm))

        adv_rows = [["Source Voucher", "Open Item", "Adjusted Amount", "Remarks"]]
        for row in voucher.advance_adjustments.all():
            source_voucher = getattr(getattr(row, "advance_balance", None), "payment_voucher", None)
            item = getattr(row, "open_item", None)
            adv_rows.append([
                getattr(source_voucher, "voucher_code", "") or getattr(getattr(row, "advance_balance", None), "reference_no", "") or "",
                getattr(item, "purchase_number", "") or f"Open Item {getattr(item, 'id', '')}",
                str(row.adjusted_amount),
                row.remarks or "",
            ])
        if len(adv_rows) > 1:
            elems.append(Paragraph("Advance Adjustments", styles["Heading3"]))
            adv_table = Table(adv_rows, colWidths=[55 * mm, 45 * mm, 30 * mm, 45 * mm])
            adv_table.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eef5")),
            ]))
            elems.append(adv_table)
            elems.append(Spacer(1, 4 * mm))

        adj_rows = [["Type", "Ledger", "Amount", "Effect", "Remarks"]]
        for row in voucher.adjustments.all():
            adj_rows.append([
                row.get_adj_type_display(),
                getattr(row.ledger_account, "accountname", ""),
                str(row.amount),
                row.get_settlement_effect_display(),
                row.remarks or "",
            ])
        if len(adj_rows) > 1:
            elems.append(Paragraph("Adjustments", styles["Heading3"]))
            adj_table = Table(adj_rows, colWidths=[30 * mm, 50 * mm, 25 * mm, 20 * mm, 55 * mm])
            adj_table.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eef5")),
            ]))
            elems.append(adj_table)
            elems.append(Spacer(1, 4 * mm))

        total_rows = [
            ["Cash Paid", str(voucher.cash_paid_amount)],
            ["Adjustment Total", str(voucher.total_adjustment_amount)],
            ["Settlement Effective", str(voucher.settlement_effective_amount)],
        ]
        total_table = Table(total_rows, colWidths=[55 * mm, 35 * mm])
        total_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
        ]))
        elems.append(Paragraph("Totals", styles["Heading3"]))
        elems.append(total_table)

        doc.build(elems)
        filename = f"{voucher.voucher_code or f'payment_voucher_{voucher.id}'}.pdf"
        response = HttpResponse(buf.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response
