from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable
from xml.sax.saxutils import escape as xml_escape

from django.http import HttpResponse
from django.utils import timezone

from payroll.models import FnFSettlement, PayrollRun, PayrollRunEmployee, Payslip
from payroll.services.payroll_traceability_service import PayrollTraceabilityService

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_CONTENT_TYPE = "text/csv; charset=utf-8"
PDF_CONTENT_TYPE = "application/pdf"


def _stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return value.isoformat()
    return str(value)


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return normalized or "export"


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _xlsx_column_name(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheet_xml(rows: list[list[str]]) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_xlsx_column_name(column_index)}{row_index}"
            text = xml_escape(_stringify(value))
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        "</worksheet>"
    )


def _build_xlsx_bytes(sheets: list[tuple[str, list[list[str]]]]) -> bytes:
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        + "".join(
            f'<sheet name="{xml_escape(name[:31])}" sheetId="{index}" r:id="rId{index}"/>'
            for index, (name, _) in enumerate(sheets, start=1)
        )
        + "</sheets></workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, len(sheets) + 1)
        )
        + "</Relationships>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for index in range(1, len(sheets) + 1)
        )
        + "</Types>"
    )
    package_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", package_rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        for index, (_, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(rows))
    return buffer.getvalue()


@dataclass(frozen=True)
class _PdfPage:
    lines: list[str]


class _SimplePdfBuilder:
    def __init__(self, *, title: str, lines: list[str], lines_per_page: int = 48):
        self.title = title
        self.lines = lines
        self.lines_per_page = lines_per_page

    def _pages(self) -> list[_PdfPage]:
        paged = [
            _PdfPage(lines=self.lines[index:index + self.lines_per_page])
            for index in range(0, len(self.lines), self.lines_per_page)
        ]
        return paged or [_PdfPage(lines=["No export content is available."])]

    def _content_stream(self, page: _PdfPage) -> bytes:
        stream_lines = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
        title = _pdf_escape(self.title)
        stream_lines.append(f"({title}) Tj")
        stream_lines.append("T*")
        stream_lines.append("T*")
        for line in page.lines:
            stream_lines.append(f"({_pdf_escape(line)}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        return "\n".join(stream_lines).encode("latin-1", errors="replace")

    def build(self) -> bytes:
        pages = self._pages()
        objects: list[bytes] = []

        def add_object(payload: bytes) -> int:
            objects.append(payload)
            return len(objects)

        page_object_ids: list[int] = []
        content_object_ids: list[int] = []
        font_object_id = 0
        pages_object_id = 0

        add_object(b"<< /Type /Catalog /Pages 2 0 R >>")
        add_object(b"<< /Type /Pages /Kids [] /Count 0 >>")

        for page in pages:
            content = self._content_stream(page)
            content_object_ids.append(
                add_object(
                    f"<< /Length {len(content)} >>\nstream\n".encode("latin-1") + content + b"\nendstream"
                )
            )
            page_object_ids.append(
                add_object(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 0 0 R /Resources << /Font << /F1 0 0 R >> >> >>")
            )

        font_object_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        pages_object_id = 2

        for index, page_object_id in enumerate(page_object_ids):
            content_object_id = content_object_ids[index]
            objects[page_object_id - 1] = (
                f"<< /Type /Page /Parent {pages_object_id} 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_object_id} 0 R /Resources << /Font << /F1 {font_object_id} 0 R >> >> >>"
            ).encode("latin-1")

        kids = " ".join(f"{page_object_id} 0 R" for page_object_id in page_object_ids)
        objects[pages_object_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode("latin-1")

        pdf = io.BytesIO()
        pdf.write(b"%PDF-1.4\n")
        offsets = [0]
        for index, payload in enumerate(objects, start=1):
            offsets.append(pdf.tell())
            pdf.write(f"{index} 0 obj\n".encode("latin-1"))
            pdf.write(payload)
            pdf.write(b"\nendobj\n")
        xref_offset = pdf.tell()
        pdf.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        pdf.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
        pdf.write(
            (
                f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF"
            ).encode("latin-1")
        )
        return pdf.getvalue()


class PayrollExportService:
    @staticmethod
    def _response(*, filename: str, content_type: str) -> HttpResponse:
        response = HttpResponse(content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Access-Control-Expose-Headers"] = "Content-Disposition, X-Export-Metadata"
        return response

    @staticmethod
    def _attach_metadata(response: HttpResponse, metadata: dict) -> HttpResponse:
        response["X-Export-Metadata"] = json.dumps(metadata, default=_stringify, separators=(",", ":"))
        return response

    @staticmethod
    def _report_metadata_rows(metadata: dict) -> list[list[str]]:
        filter_payload = metadata.get("filters_applied") or {}
        return [
            ["Field", "Value"],
            ["entity", _stringify(metadata.get("entity"))],
            ["payroll_period_or_range", _stringify(metadata.get("payroll_period_or_range"))],
            ["generated_by", _stringify(metadata.get("generated_by"))],
            ["generated_at", _stringify(metadata.get("generated_at"))],
            ["source_snapshot_note", _stringify(metadata.get("source_snapshot_note"))],
            ["filters_applied", json.dumps(filter_payload, default=_stringify, separators=(",", ":"))],
        ]

    @staticmethod
    def export_report_payload(*, payload: dict, metadata: dict, file_stem: str, export_format: str) -> HttpResponse:
        columns = payload.get("columns") or []
        rows = payload.get("rows") or []
        header_row = [_stringify(column.get("label") or column.get("key") or "") for column in columns]
        data_rows = [
            [_stringify(row.get(column.get("key"))) for column in columns]
            for row in rows
        ]
        timestamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        base_name = f"{_slug(file_stem)}_{timestamp}"

        if export_format == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(header_row)
            writer.writerows(data_rows)
            response = PayrollExportService._response(filename=f"{base_name}.csv", content_type=CSV_CONTENT_TYPE)
            response.write(buffer.getvalue())
            return PayrollExportService._attach_metadata(response, metadata)

        if export_format == "xlsx":
            workbook = _build_xlsx_bytes(
                [
                    ("Report", [header_row, *data_rows]),
                    ("Metadata", PayrollExportService._report_metadata_rows(metadata)),
                ]
            )
            response = PayrollExportService._response(filename=f"{base_name}.xlsx", content_type=XLSX_CONTENT_TYPE)
            response.write(workbook)
            return PayrollExportService._attach_metadata(response, metadata)

        raise ValueError(f"Unsupported export format '{export_format}'.")

    @staticmethod
    def export_payslip_pdf(*, payslip: Payslip, generated_by: str) -> HttpResponse:
        row = payslip.payroll_run_employee
        run = row.payroll_run
        payload = payslip.payload or {}
        sections = PayrollTraceabilityService.build_payslip_sections(payslip=payslip)
        section_totals = sections.get("section_totals") or {}
        lines = [
            f"Payslip Number: {payslip.payslip_number}",
            f"Employee: {row.employee_name} ({row.employee_code})",
            f"Run: {run.run_number or f'{run.doc_code}-{run.doc_no or run.id}'}",
            f"Period: {payload.get('payroll_period_code') or getattr(run.payroll_period, 'code', '')}",
            f"Generated By: {generated_by}",
            f"Generated At: {timezone.localtime().isoformat()}",
            "Source Snapshot Note: Rendered from stored payroll run and payslip snapshots only.",
            "",
            f"Gross Amount: {_stringify(section_totals.get('gross_amount') or row.gross_amount)}",
            f"Deduction Amount: {_stringify(section_totals.get('deduction_amount') or row.deduction_amount)}",
            f"Net Payable: {_stringify(section_totals.get('net_payable') or row.payable_amount)}",
            "",
            "Earnings:",
        ]
        for item in sections.get("earnings") or []:
            lines.append(f"  - {item.get('name')}: {_stringify(item.get('amount'))}")
        lines.append("")
        lines.append("Deductions:")
        for item in sections.get("deductions") or []:
            lines.append(f"  - {item.get('name')}: {_stringify(item.get('amount'))}")
        employer_contributions = sections.get("employer_contributions") or []
        if employer_contributions:
            lines.append("")
            lines.append("Employer Contributions:")
            for item in employer_contributions:
                lines.append(f"  - {item.get('name')}: {_stringify(item.get('amount'))}")

        document = _SimplePdfBuilder(title="Payroll Payslip", lines=lines).build()
        response = PayrollExportService._response(
            filename=f"{_slug(payslip.payslip_number or 'payslip')}.pdf",
            content_type=PDF_CONTENT_TYPE,
        )
        response.write(document)
        metadata = {
            "entity": run.entity_id,
            "payroll_period_or_range": getattr(run.payroll_period, "code", ""),
            "generated_by": generated_by,
            "generated_at": timezone.localtime().isoformat(),
            "filters_applied": {
                "payroll_run": run.id,
                "employee_run": row.id,
                "payslip": payslip.id,
            },
            "source_snapshot_note": "Rendered from stored payroll run and payslip snapshots only.",
        }
        return PayrollExportService._attach_metadata(response, metadata)

    @staticmethod
    def export_fnf_statement_placeholder_pdf(*, settlement: FnFSettlement, generated_by: str) -> HttpResponse:
        lines = [
            f"Settlement Number: {settlement.settlement_number or f'FNF-{settlement.id}'}",
            f"Contract: {settlement.hrms_contract.contract_code}",
            f"Status: {settlement.status}",
            f"Separation Date: {_stringify(settlement.separation_date)}",
            f"Last Working Day: {_stringify(settlement.last_working_day)}",
            f"Settlement Date: {_stringify(settlement.settlement_date)}",
            "",
            f"Earned Amount: {_stringify(settlement.earned_amount)}",
            f"Deduction Amount: {_stringify(settlement.deduction_amount)}",
            f"Recovery Amount: {_stringify(settlement.recovery_amount)}",
            f"Reimbursement Amount: {_stringify(settlement.reimbursement_amount)}",
            f"Net Payable Amount: {_stringify(settlement.net_payable_amount)}",
            f"Net Recoverable Amount: {_stringify(settlement.net_recoverable_amount)}",
            "",
            "Placeholder Note:",
            "A full formatted FnF statement template is not exposed yet.",
            "This PDF is a placeholder rendered strictly from stored FnF settlement snapshots.",
            f"Generated By: {generated_by}",
            f"Generated At: {timezone.localtime().isoformat()}",
        ]
        document = _SimplePdfBuilder(title="FnF Statement Placeholder", lines=lines).build()
        response = PayrollExportService._response(
            filename=f"{_slug(settlement.settlement_number or f'fnf_{settlement.id}')}.pdf",
            content_type=PDF_CONTENT_TYPE,
        )
        response.write(document)
        metadata = {
            "entity": settlement.entity_id,
            "payroll_period_or_range": getattr(settlement.payroll_period, "code", "") or _stringify(settlement.settlement_date),
            "generated_by": generated_by,
            "generated_at": timezone.localtime().isoformat(),
            "filters_applied": {
                "fnf_settlement": settlement.id,
                "contract_payroll_profile": str(settlement.contract_payroll_profile_id),
            },
            "source_snapshot_note": "Rendered from stored FnF settlement snapshots only.",
        }
        return PayrollExportService._attach_metadata(response, metadata)

    @staticmethod
    def export_run_register(*, runs: Iterable[PayrollRun]) -> HttpResponse:
        response = PayrollExportService._response(filename="payroll_run_register.csv", content_type=CSV_CONTENT_TYPE)
        writer = csv.writer(response)
        writer.writerow(
            [
                "run_id",
                "run_reference",
                "entity_id",
                "entity_name",
                "entityfinid_id",
                "subentity_id",
                "period_code",
                "status",
                "payment_status",
                "employee_count",
                "gross_amount",
                "deduction_amount",
                "employer_contribution_amount",
                "reimbursement_amount",
                "net_pay_amount",
                "post_reference",
                "payment_batch_ref",
                "reversal_reason",
                "created_at",
                "posted_at",
            ]
        )
        for run in runs:
            writer.writerow(
                [
                    run.id,
                    run.run_number or f"{run.doc_code}-{run.doc_no or run.id}",
                    run.entity_id,
                    getattr(run.entity, "entityname", ""),
                    run.entityfinid_id,
                    run.subentity_id or "",
                    getattr(run.payroll_period, "code", ""),
                    run.status,
                    run.payment_status,
                    run.employee_count,
                    run.gross_amount,
                    run.deduction_amount,
                    run.employer_contribution_amount,
                    run.reimbursement_amount,
                    run.net_pay_amount,
                    run.post_reference,
                    run.payment_batch_ref,
                    run.reversal_reason,
                    run.created_at,
                    run.posted_at,
                ]
            )
        return response

    @staticmethod
    def export_employee_rows(*, rows: Iterable[PayrollRunEmployee]) -> HttpResponse:
        response = PayrollExportService._response(filename="payroll_run_employee_rows.csv", content_type=CSV_CONTENT_TYPE)
        writer = csv.writer(response)
        writer.writerow(
            [
                "row_id",
                "run_id",
                "run_reference",
                "contract_payroll_profile_id",
                "hrms_contract_id",
                "contract_code",
                "employee_code",
                "employee_name",
                "work_email",
                "status",
                "payment_status",
                "gross_amount",
                "deduction_amount",
                "employer_contribution_amount",
                "reimbursement_amount",
                "payable_amount",
                "salary_structure_id",
                "salary_structure_version_id",
            ]
        )
        for row in rows:
            run = row.payroll_run
            writer.writerow(
                [
                    row.id,
                    run.id,
                    run.run_number or f"{run.doc_code}-{run.doc_no or run.id}",
                    row.contract_payroll_profile_id,
                    row.contract_payroll_profile.hrms_contract_id if row.contract_payroll_profile_id else "",
                    row.contract_payroll_profile.hrms_contract.contract_code if row.contract_payroll_profile_id else "",
                    row.employee_code,
                    row.employee_name,
                    row.contract_payroll_profile.hrms_contract.employee.work_email if row.contract_payroll_profile_id else "",
                    row.status,
                    row.payment_status,
                    row.gross_amount,
                    row.deduction_amount,
                    row.employer_contribution_amount,
                    row.reimbursement_amount,
                    row.payable_amount,
                    row.salary_structure_id or "",
                    row.salary_structure_version_id or "",
                ]
            )
        return response

    @staticmethod
    def export_component_totals(*, runs: Iterable[PayrollRun]) -> HttpResponse:
        response = PayrollExportService._response(filename="payroll_component_totals.csv", content_type=CSV_CONTENT_TYPE)
        writer = csv.writer(response)
        writer.writerow(
            [
                "run_id",
                "run_reference",
                "component_id",
                "component_code",
                "component_name",
                "category",
                "amount",
                "employee_count",
            ]
        )
        for run in runs:
            run_ref = run.run_number or f"{run.doc_code}-{run.doc_no or run.id}"
            for total in PayrollTraceabilityService.build_component_totals(run=run):
                writer.writerow(
                    [
                        run.id,
                        run_ref,
                        total["component_id"] or "",
                        total["component_code"],
                        total["component_name"],
                        total["category"] or "",
                        total["amount"],
                        total["employee_count"],
                    ]
                )
        return response

    @staticmethod
    def export_deduction_summary(*, runs: Iterable[PayrollRun]) -> HttpResponse:
        response = PayrollExportService._response(filename="payroll_deduction_summary.csv", content_type=CSV_CONTENT_TYPE)
        writer = csv.writer(response)
        writer.writerow(
            [
                "run_id",
                "run_reference",
                "employee_count",
                "deduction_amount",
            ]
        )
        for run in runs:
            writer.writerow(
                [
                    run.id,
                    run.run_number or f"{run.doc_code}-{run.doc_no or run.id}",
                    run.employee_count,
                    run.deduction_amount,
                ]
            )
        return response
