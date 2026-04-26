from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import ProductBulkJob
from sales.models import SalesInvoiceHeader, SalesInvoiceLine
from sales.views.sales_invoice_views import require_sales_request_permission


STATUS_SLUG_TO_ID = {
    "draft": int(SalesInvoiceHeader.Status.DRAFT),
    "confirmed": int(SalesInvoiceHeader.Status.CONFIRMED),
    "posted": int(SalesInvoiceHeader.Status.POSTED),
    "cancelled": int(SalesInvoiceHeader.Status.CANCELLED),
}

STATUS_ID_TO_SLUG = {value: key for key, value in STATUS_SLUG_TO_ID.items()}

DOC_SLUG_TO_DOC_TYPE = {
    "sale_invoice": int(SalesInvoiceHeader.DocType.TAX_INVOICE),
    "sale_service_invoice": int(SalesInvoiceHeader.DocType.TAX_INVOICE),
    "sale_credit_note": int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
    "sale_debit_note": int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
}

DATE_FIELD_MAP = {
    "bill_date": "bill_date",
    "posting_date": "posting_date",
    "created_at": "createdon",
}


class _BulkPrintMixin:
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _as_dict(value: Any) -> dict:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _as_list(value: Any) -> list:
        return value if isinstance(value, list) else []

    @staticmethod
    def _as_int(value: Any, field_name: str, *, required: bool = False) -> int | None:
        if value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            raise ValidationError({field_name: f"{field_name} must be an integer."})
        return ivalue

    @staticmethod
    def _as_decimal(value: Any) -> Decimal | None:
        if value in (None, "", "null", "None"):
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    @staticmethod
    def _as_date(value: Any) -> date | None:
        if value in (None, "", "null", "None"):
            return None
        raw = str(value).strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except Exception:
            return None

    @staticmethod
    def _is_truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y"}

    def _scope(self, request) -> tuple[int, int | None, int | None]:
        payload = self._as_dict(getattr(request, "data", {}))
        entity_id = self._as_int(
            request.query_params.get("entity_id")
            or request.query_params.get("entity")
            or payload.get("entity_id")
            or payload.get("entity"),
            "entity_id",
            required=True,
        )
        entityfinid_id = self._as_int(
            request.query_params.get("entityfinid")
            or request.query_params.get("entityfinid_id")
            or payload.get("entityfinid")
            or payload.get("entityfinid_id"),
            "entityfinid",
            required=False,
        )
        subentity_id = self._as_int(
            request.query_params.get("subentity_id")
            or request.query_params.get("subentity")
            or payload.get("subentity_id")
            or payload.get("subentity"),
            "subentity_id",
            required=False,
        )
        if subentity_id == 0:
            subentity_id = None
        return int(entity_id), entityfinid_id, subentity_id

    def _require_doc_permissions(self, *, user, entity_id: int, doc_slugs: list[str]) -> None:
        if not doc_slugs:
            doc_slugs = ["sale_invoice"]
        checked_doc_types: set[int] = set()
        for slug in doc_slugs:
            doc_type = DOC_SLUG_TO_DOC_TYPE.get(str(slug).strip())
            if doc_type is None or doc_type in checked_doc_types:
                continue
            require_sales_request_permission(
                user=user,
                entity_id=entity_id,
                doc_type=doc_type,
                action="view",
            )
            checked_doc_types.add(doc_type)

    def _build_queryset(self, *, entity_id: int, entityfinid_id: int | None, subentity_id: int | None, payload: dict):
        scope = self._as_dict(payload.get("scope"))
        doc_types = [str(x).strip() for x in self._as_list(scope.get("doc_types")) if str(x).strip()]
        statuses = [str(x).strip().lower() for x in self._as_list(scope.get("statuses")) if str(x).strip()]
        date_field = str(scope.get("date_field") or "bill_date").strip()

        queryset = SalesInvoiceHeader.objects.filter(entity_id=entity_id)
        if entityfinid_id is not None:
            queryset = queryset.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            queryset = queryset.filter(subentity_id=subentity_id)

        service_lines = SalesInvoiceLine.objects.filter(header_id=OuterRef("pk"), is_service=True)
        goods_lines = SalesInvoiceLine.objects.filter(header_id=OuterRef("pk"), is_service=False)
        queryset = queryset.annotate(_has_service=Exists(service_lines), _has_goods=Exists(goods_lines))

        if statuses:
            allowed_status_ids = [STATUS_SLUG_TO_ID.get(item) for item in statuses]
            allowed_status_ids = [item for item in allowed_status_ids if item is not None]
            if allowed_status_ids:
                queryset = queryset.filter(status__in=allowed_status_ids)

        if doc_types:
            include_goods_tax = "sale_invoice" in doc_types
            include_service_tax = "sale_service_invoice" in doc_types
            include_credit = "sale_credit_note" in doc_types
            include_debit = "sale_debit_note" in doc_types

            doc_filter = Q()
            if include_goods_tax and include_service_tax:
                doc_filter |= Q(doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE)
            elif include_service_tax:
                doc_filter |= Q(doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE, _has_service=True, _has_goods=False)
            elif include_goods_tax:
                doc_filter |= Q(doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE) & (~Q(_has_service=True, _has_goods=False))

            if include_credit:
                doc_filter |= Q(doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE)
            if include_debit:
                doc_filter |= Q(doc_type=SalesInvoiceHeader.DocType.DEBIT_NOTE)

            if doc_filter:
                queryset = queryset.filter(doc_filter)

        date_col = DATE_FIELD_MAP.get(date_field, "bill_date")
        date_from = self._as_date(scope.get("date_from"))
        date_to = self._as_date(scope.get("date_to"))
        if date_from:
            queryset = queryset.filter(**{f"{date_col}__gte": date_from})
        if date_to:
            queryset = queryset.filter(**{f"{date_col}__lte": date_to})

        number_from = self._as_int(scope.get("number_from"), "number_from", required=False)
        number_to = self._as_int(scope.get("number_to"), "number_to", required=False)
        if number_from is not None:
            queryset = queryset.filter(doc_no__gte=number_from)
        if number_to is not None:
            queryset = queryset.filter(doc_no__lte=number_to)

        customer_search = str(scope.get("customer_search") or "").strip()
        if customer_search:
            queryset = queryset.filter(
                Q(customer_name__icontains=customer_search)
                | Q(invoice_number__icontains=customer_search)
                | Q(doc_code__icontains=customer_search)
            )

        min_amount = self._as_decimal(scope.get("min_amount"))
        max_amount = self._as_decimal(scope.get("max_amount"))
        if min_amount is not None:
            queryset = queryset.filter(grand_total__gte=min_amount)
        if max_amount is not None:
            queryset = queryset.filter(grand_total__lte=max_amount)

        compliance_filters = self._as_dict(scope.get("compliance_filters"))
        if self._is_truthy(compliance_filters.get("with_irn_only")):
            queryset = queryset.filter(einvoice_artifact__irn__isnull=False).exclude(einvoice_artifact__irn="")
        if self._is_truthy(compliance_filters.get("with_ewb_only")):
            queryset = queryset.filter(
                Q(eway_artifact__ewb_no__isnull=False) & ~Q(eway_artifact__ewb_no="")
                | (Q(einvoice_artifact__ewb_no__isnull=False) & ~Q(einvoice_artifact__ewb_no=""))
            )
        if self._is_truthy(compliance_filters.get("reverse_charge_only")):
            queryset = queryset.filter(is_reverse_charge=True)

        output = self._as_dict(payload.get("output"))
        sort_by = str(output.get("sort_by") or "number").strip().lower()
        sort_map = {
            "number": ["doc_no", "id"],
            "date": ["bill_date", "doc_no", "id"],
            "customer": ["customer_name", "doc_no", "id"],
            "amount": ["grand_total", "doc_no", "id"],
        }
        queryset = queryset.order_by(*sort_map.get(sort_by, ["doc_no", "id"]))

        return queryset

    @staticmethod
    def _derive_doc_slug(header: SalesInvoiceHeader) -> str:
        if int(header.doc_type or 0) == int(SalesInvoiceHeader.DocType.CREDIT_NOTE):
            return "sale_credit_note"
        if int(header.doc_type or 0) == int(SalesInvoiceHeader.DocType.DEBIT_NOTE):
            return "sale_debit_note"
        has_service = bool(getattr(header, "_has_service", False))
        has_goods = bool(getattr(header, "_has_goods", False))
        if has_service and not has_goods:
            return "sale_service_invoice"
        return "sale_invoice"

    def _build_manifest(self, headers: list[SalesInvoiceHeader], *, entity_id: int, entityfinid_id: int | None, subentity_id: int | None) -> list[dict]:
        manifest: list[dict] = []
        query_parts = [f"entity_id={int(entity_id)}"]
        if entityfinid_id is not None:
            query_parts.append(f"entityfinid={int(entityfinid_id)}")
        if subentity_id is not None:
            query_parts.append(f"subentity_id={int(subentity_id)}")

        for header in headers:
            doc_slug = self._derive_doc_slug(header)
            if doc_slug == "sale_service_invoice":
                endpoint = f"/api/sales/service-invoices/{header.id}/print/"
                line_mode = "service"
            else:
                endpoint = f"/api/sales/invoices/{header.id}/print/"
                line_mode = "goods" if doc_slug == "sale_invoice" else None
            query = query_parts.copy()
            if line_mode:
                query.append(f"line_mode={line_mode}")
            endpoint = f"{endpoint}?{'&'.join(query)}"

            manifest.append(
                {
                    "invoice_id": int(header.id),
                    "doc_type": doc_slug,
                    "status": STATUS_ID_TO_SLUG.get(int(header.status or 0), str(header.status)),
                    "doc_no": int(header.doc_no or 0) if header.doc_no is not None else None,
                    "invoice_number": str(header.invoice_number or "").strip(),
                    "bill_date": header.bill_date.isoformat() if header.bill_date else None,
                    "customer_name": str(header.customer_name or "").strip(),
                    "grand_total": float(header.grand_total or 0),
                    "print_endpoint": endpoint,
                }
            )
        return manifest

    @staticmethod
    def _build_summary(manifest: list[dict], payload: dict) -> dict:
        doc_breakdown: dict[str, int] = {}
        status_breakdown: dict[str, int] = {}
        for row in manifest:
            doc_key = str(row.get("doc_type") or "unknown")
            status_key = str(row.get("status") or "unknown")
            doc_breakdown[doc_key] = doc_breakdown.get(doc_key, 0) + 1
            status_breakdown[status_key] = status_breakdown.get(status_key, 0) + 1

        copies = 1
        try:
            copies = max(1, int(_BulkPrintMixin._as_dict(payload.get("output")).get("copies") or 1))
        except Exception:
            copies = 1

        return {
            "matched_docs": len(manifest),
            "estimated_print_pages": len(manifest) * copies,
            "doc_breakdown": doc_breakdown,
            "status_breakdown": status_breakdown,
            "generated_at": datetime.now().isoformat(),
        }


class SalesBulkPrintJobListCreateAPIView(_BulkPrintMixin, APIView):
    def post(self, request):
        entity_id, entityfinid_id, subentity_id = self._scope(request)
        payload = self._as_dict(getattr(request, "data", {}))
        scope = self._as_dict(payload.get("scope"))
        doc_types = [str(item).strip() for item in self._as_list(scope.get("doc_types")) if str(item).strip()]

        self._require_doc_permissions(user=request.user, entity_id=entity_id, doc_slugs=doc_types)

        headers_qs = self._build_queryset(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            payload=payload,
        ).only(
            "id",
            "doc_type",
            "status",
            "doc_no",
            "invoice_number",
            "bill_date",
            "customer_name",
            "grand_total",
        )

        headers = list(headers_qs)
        manifest = self._build_manifest(
            headers,
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
        )
        summary = self._build_summary(manifest, payload)

        job = ProductBulkJob.objects.create(
            entity_id=entity_id,
            created_by=request.user,
            job_type=ProductBulkJob.JobType.EXPORT,
            status=ProductBulkJob.JobStatus.COMPLETED,
            file_format=ProductBulkJob.FileFormat.CSV,
            summary=summary,
            payload={
                "request": payload,
                "scope": {
                    "entity_id": entity_id,
                    "entityfinid": entityfinid_id,
                    "subentity_id": subentity_id,
                },
                "manifest": manifest,
            },
        )

        return Response(
            {
                "id": job.id,
                "status": job.status,
                "summary": summary,
                "manifest_preview": manifest[:200],
                "error_count": 0,
                "createdon": job.createdon,
                "modifiedon": job.modifiedon,
            },
            status=status.HTTP_201_CREATED,
        )


class SalesBulkPrintJobDetailAPIView(_BulkPrintMixin, APIView):
    def get(self, request, job_id: int):
        entity_id, _, _ = self._scope(request)
        job = get_object_or_404(ProductBulkJob, pk=job_id, entity_id=entity_id)
        payload = self._as_dict(job.payload)
        manifest = self._as_list(payload.get("manifest"))

        return Response(
            {
                "id": job.id,
                "status": job.status,
                "summary": job.summary or {},
                "manifest_preview": manifest[:200],
                "error_count": len(job.errors or []),
                "download_formats": ["json", "csv", "zip", "pdf", "zip_pdf"],
                "createdon": job.createdon,
                "modifiedon": job.modifiedon,
            },
            status=status.HTTP_200_OK,
        )


class SalesBulkPrintJobDownloadAPIView(_BulkPrintMixin, APIView):
    @staticmethod
    def _safe_filename(value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        if not text:
            text = fallback
        text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
        text = text.strip("._")
        return text or fallback

    @staticmethod
    def _money(value: Any) -> str:
        try:
            return f"{Decimal(str(value or 0)):.2f}"
        except Exception:
            return "0.00"

    @staticmethod
    def _qty(value: Any) -> str:
        try:
            return f"{Decimal(str(value or 0)):.3f}"
        except Exception:
            return "0.000"

    @staticmethod
    def _line_items_for_header(header_id: int, doc_slug: str) -> list[SalesInvoiceLine]:
        lines_qs = (
            SalesInvoiceLine.objects.filter(header_id=header_id)
            .select_related("product", "sales_account", "uom")
            .order_by("line_no", "id")
        )
        if doc_slug == "sale_service_invoice":
            lines_qs = lines_qs.filter(is_service=True)
        elif doc_slug == "sale_invoice":
            lines_qs = lines_qs.filter(is_service=False)
        return list(lines_qs)

    @staticmethod
    def _line_description(line: SalesInvoiceLine) -> str:
        product_name = getattr(getattr(line, "product", None), "productname", None)
        account_name = getattr(getattr(line, "sales_account", None), "accountname", None)
        free_text = getattr(line, "productDesc", None)
        return str(product_name or account_name or free_text or "").strip()

    @classmethod
    def _build_story_for_invoice(cls, *, row: dict, header: SalesInvoiceHeader, profile_key: str | None) -> list:
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("bulkTitle", parent=styles["Heading2"], spaceAfter=6)
        meta_style = ParagraphStyle("bulkMeta", parent=styles["Normal"], fontSize=9, leading=12)
        section_style = ParagraphStyle("bulkSection", parent=styles["Heading4"], spaceBefore=8, spaceAfter=4)

        story = []
        invoice_number = str(row.get("invoice_number") or getattr(header, "invoice_number", "") or f"INV-{header.id}").strip()
        doc_label = str(row.get("doc_type") or "").replace("_", " ").title()

        story.append(Paragraph(f"{doc_label} - {invoice_number}", title_style))
        story.append(Paragraph(
            f"Date: {row.get('bill_date') or ''} | Customer: {row.get('customer_name') or ''} | "
            f"Status: {row.get('status') or ''} | Profile: {profile_key or '--'}",
            meta_style,
        ))
        story.append(Paragraph(
            f"Total: INR {cls._money(row.get('grand_total'))} | Doc No: {row.get('doc_no') or '--'} | Invoice ID: {header.id}",
            meta_style,
        ))
        story.append(Spacer(1, 8))
        story.append(Paragraph("Line Items", section_style))

        lines = cls._line_items_for_header(int(header.id), str(row.get("doc_type") or ""))
        table_rows = [["#", "Description", "HSN/SAC", "Qty", "Rate", "Taxable", "GST%", "Line Total"]]
        for line in lines:
            table_rows.append([
                str(getattr(line, "line_no", "") or ""),
                cls._line_description(line) or "-",
                str(getattr(line, "hsn_sac_code", "") or ""),
                cls._qty(getattr(line, "qty", 0)),
                cls._money(getattr(line, "rate", 0)),
                cls._money(getattr(line, "taxable_value", 0)),
                cls._money(getattr(line, "gst_rate", 0)),
                cls._money(getattr(line, "line_total", 0)),
            ])

        if len(table_rows) == 1:
            table_rows.append(["", "No line items", "", "", "", "", "", ""])

        line_table = Table(table_rows, repeatRows=1, colWidths=[26, 190, 65, 48, 58, 64, 44, 68])
        line_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6edf5")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9fb1c5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ]))
        story.append(line_table)
        story.append(Spacer(1, 10))

        total_table = Table(
            [
                ["Taxable", cls._money(getattr(header, "total_taxable_value", 0))],
                ["CGST", cls._money(getattr(header, "total_cgst", 0))],
                ["SGST", cls._money(getattr(header, "total_sgst", 0))],
                ["IGST", cls._money(getattr(header, "total_igst", 0))],
                ["CESS", cls._money(getattr(header, "total_cess", 0))],
                ["Grand Total", cls._money(getattr(header, "grand_total", 0))],
            ],
            colWidths=[120, 110],
        )
        total_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9fb1c5")),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        story.append(total_table)
        story.append(Spacer(1, 14))
        return story

    @classmethod
    def _render_single_invoice_pdf(cls, *, row: dict, header: SalesInvoiceHeader, profile_key: str | None) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18, rightMargin=18, topMargin=20, bottomMargin=20)
        story = cls._build_story_for_invoice(row=row, header=header, profile_key=profile_key)
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    @classmethod
    def _render_merged_pdf(
        cls,
        *,
        manifest: list[dict],
        headers_map: dict[int, SalesInvoiceHeader],
        profile_by_doc_type: dict[str, str],
        default_profile: str | None,
    ) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18, rightMargin=18, topMargin=20, bottomMargin=20)
        story = []
        appended = 0
        for row in manifest:
            invoice_id = int(row.get("invoice_id") or 0)
            header = headers_map.get(invoice_id)
            if header is None:
                continue
            doc_slug = str(row.get("doc_type") or "")
            profile_key = profile_by_doc_type.get(doc_slug) or default_profile
            invoice_story = cls._build_story_for_invoice(row=row, header=header, profile_key=profile_key)
            if appended > 0:
                story.append(PageBreak())
            story.extend(invoice_story)
            appended += 1
        if not story:
            story.append(Paragraph("No invoices matched for PDF rendering.", getSampleStyleSheet()["Normal"]))
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    @classmethod
    def _zip_pdf_bundle(
        cls,
        *,
        job_id: int,
        manifest: list[dict],
        headers_map: dict[int, SalesInvoiceHeader],
        profile_by_doc_type: dict[str, str],
        default_profile: str | None,
    ) -> bytes:
        archive = BytesIO()
        with ZipFile(archive, mode="w", compression=ZIP_DEFLATED) as zf:
            zf.writestr("manifest.csv", cls._manifest_csv(manifest))
            zf.writestr("manifest.json", json.dumps(manifest or [], indent=2))
            generated_count = 0
            for row in manifest:
                invoice_id = int(row.get("invoice_id") or 0)
                header = headers_map.get(invoice_id)
                if header is None:
                    continue
                doc_slug = str(row.get("doc_type") or "")
                profile_key = profile_by_doc_type.get(doc_slug) or default_profile
                pdf_bytes = cls._render_single_invoice_pdf(row=row, header=header, profile_key=profile_key)
                invoice_number = cls._safe_filename(row.get("invoice_number"), f"invoice_{invoice_id}")
                zf.writestr(f"invoices/{invoice_number}.pdf", pdf_bytes)
                generated_count += 1
            zf.writestr("README.txt", "\n".join([
                f"Sales Bulk Print PDF Bundle #{job_id}",
                f"Invoices rendered: {generated_count}",
                "Each PDF is generated from live invoice header/line data.",
            ]))
        archive.seek(0)
        return archive.getvalue()

    @staticmethod
    def _manifest_csv(manifest: list[dict]) -> str:
        buff = StringIO()
        writer = csv.writer(buff)
        writer.writerow(["invoice_id", "doc_type", "status", "doc_no", "invoice_number", "bill_date", "customer_name", "grand_total", "print_endpoint"])
        for row in manifest:
            writer.writerow(
                [
                    row.get("invoice_id") or "",
                    row.get("doc_type") or "",
                    row.get("status") or "",
                    row.get("doc_no") or "",
                    row.get("invoice_number") or "",
                    row.get("bill_date") or "",
                    row.get("customer_name") or "",
                    row.get("grand_total") or "",
                    row.get("print_endpoint") or "",
                ]
            )
        return buff.getvalue()

    @staticmethod
    def _zip_bundle(*, job_id: int, summary: dict, request_payload: dict, scope_payload: dict, manifest: list[dict]) -> bytes:
        archive = BytesIO()
        with ZipFile(archive, mode="w", compression=ZIP_DEFLATED) as zf:
            zf.writestr("summary.json", json.dumps(summary or {}, indent=2))
            zf.writestr("request.json", json.dumps(request_payload or {}, indent=2))
            zf.writestr("scope.json", json.dumps(scope_payload or {}, indent=2))
            zf.writestr("manifest.json", json.dumps(manifest or [], indent=2))
            zf.writestr("manifest.csv", SalesBulkPrintJobDownloadAPIView._manifest_csv(manifest))
            readme = [
                f"Sales Bulk Print Job #{job_id}",
                "",
                "This ZIP contains the filtered print manifest and request snapshot.",
                "Use print_endpoint values from manifest.csv/json for invoice-level print payload fetching.",
                "",
                f"Generated at: {datetime.now().isoformat()}",
            ]
            zf.writestr("README.txt", "\n".join(readme))
        archive.seek(0)
        return archive.getvalue()

    def get(self, request, job_id: int):
        entity_id, _, _ = self._scope(request)
        fmt = str(request.query_params.get("format") or "json").strip().lower()
        if fmt not in ("json", "csv", "zip", "pdf", "zip_pdf"):
            raise ValidationError({"format": "Use json, csv, zip, pdf or zip_pdf."})

        job = get_object_or_404(ProductBulkJob, pk=job_id, entity_id=entity_id)
        payload = self._as_dict(job.payload)
        request_payload = self._as_dict(payload.get("request"))
        scope_payload = self._as_dict(payload.get("scope"))
        manifest = self._as_list(payload.get("manifest"))
        summary = job.summary or {}

        invoice_ids = [int(row.get("invoice_id") or 0) for row in manifest if int(row.get("invoice_id") or 0) > 0]
        headers_qs = SalesInvoiceHeader.objects.filter(entity_id=entity_id, id__in=invoice_ids).only(
            "id",
            "invoice_number",
            "doc_no",
            "bill_date",
            "status",
            "customer_name",
            "total_taxable_value",
            "total_cgst",
            "total_sgst",
            "total_igst",
            "total_cess",
            "grand_total",
        )
        headers_map = {int(item.id): item for item in headers_qs}
        layout_payload = self._as_dict(request_payload.get("layout"))
        profile_by_doc_type = self._as_dict(layout_payload.get("profile_by_doc_type"))
        default_profile = str(layout_payload.get("default_profile") or "").strip() or None

        if fmt == "json":
            response = HttpResponse(json.dumps({"summary": summary, "manifest": manifest}, indent=2), content_type="application/json")
            response["Content-Disposition"] = f'attachment; filename="sales_bulk_print_job_{job.id}.json"'
            return response

        if fmt == "zip":
            bundle = self._zip_bundle(
                job_id=job.id,
                summary=summary,
                request_payload=request_payload,
                scope_payload=scope_payload,
                manifest=manifest,
            )
            response = HttpResponse(bundle, content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="sales_bulk_print_job_{job.id}.zip"'
            return response

        if fmt == "pdf":
            merged_pdf = self._render_merged_pdf(
                manifest=manifest,
                headers_map=headers_map,
                profile_by_doc_type=profile_by_doc_type,
                default_profile=default_profile,
            )
            response = HttpResponse(merged_pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="sales_bulk_print_job_{job.id}.pdf"'
            return response

        if fmt == "zip_pdf":
            zip_pdf = self._zip_pdf_bundle(
                job_id=job.id,
                manifest=manifest,
                headers_map=headers_map,
                profile_by_doc_type=profile_by_doc_type,
                default_profile=default_profile,
            )
            response = HttpResponse(zip_pdf, content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="sales_bulk_print_job_{job.id}_pdfs.zip"'
            return response

        response = HttpResponse(self._manifest_csv(manifest), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="sales_bulk_print_job_{job.id}.csv"'
        return response
