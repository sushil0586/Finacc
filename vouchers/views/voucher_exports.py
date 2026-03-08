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

from vouchers.models import VoucherHeader


class VoucherPDFAPIView(APIView):
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
        qs = VoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id).select_related(
            "cash_bank_account", "entity", "entityfinid", "subentity"
        ).prefetch_related("lines__account")
        qs = qs.filter(subentity__isnull=True) if subentity_id is None else qs.filter(subentity_id=subentity_id)
        voucher = qs.get(pk=pk)

        disposition = (request.query_params.get("disposition") or "inline").strip().lower()
        if disposition not in {"inline", "attachment"}:
            disposition = "inline"

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
        styles = getSampleStyleSheet()
        elems = []

        title = voucher.voucher_code or f"{voucher.doc_code}-{voucher.doc_no or ''}".strip("-")
        elems.append(Paragraph(f"Voucher: {title}", styles["Title"]))
        elems.append(Spacer(1, 4 * mm))
        header_rows = [
            ["Voucher Date", str(voucher.voucher_date), "Status", voucher.get_status_display()],
            ["Voucher Type", voucher.get_voucher_type_display(), "Reference", voucher.reference_number or ""],
            ["Cash/Bank Account", getattr(voucher.cash_bank_account, "accountname", "") or "-", "Narration", voucher.narration or ""],
            ["Debit Total", str(voucher.total_debit_amount), "Credit Total", str(voucher.total_credit_amount)],
        ]
        t = Table(header_rows, colWidths=[32 * mm, 58 * mm, 32 * mm, 58 * mm])
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
        ]))
        elems.append(t)
        elems.append(Spacer(1, 5 * mm))
        rows = [["Line", "Ledger", "Dr", "Cr", "Narration", "Type"]]
        for line in voucher.lines.all().order_by("line_no", "id"):
            rows.append([
                str(line.line_no),
                getattr(line.account, "accountname", ""),
                str(line.dr_amount),
                str(line.cr_amount),
                line.narration or "",
                "System" if line.is_system_generated else "User",
            ])
        table = Table(rows, colWidths=[12 * mm, 45 * mm, 20 * mm, 20 * mm, 70 * mm, 18 * mm])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eef5")),
        ]))
        elems.append(table)
        doc.build(elems)
        filename = f"{voucher.voucher_code or f'voucher_{voucher.id}'}.pdf"
        response = HttpResponse(buf.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response
