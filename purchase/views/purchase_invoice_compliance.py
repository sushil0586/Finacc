from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.views.purchase_meta import PurchaseMetaBaseAPIView


ZERO = Decimal("0.00")


class PurchaseInvoiceComplianceStatusAPIView(PurchaseMetaBaseAPIView):
    """
    Lightweight purchase compliance overview for invoice and note workspaces.

    This intentionally does not mirror sales IRN / E-Way operations. It exposes
    purchase-side statutory readiness signals that already exist on the document.
    """

    def get(self, request, pk: int):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        line_mode = self._parse_line_mode(request)
        header = self._resolve_header(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            line_mode=line_mode,
            pk=pk,
        )
        return Response(self._build_payload(header))

    def _resolve_header(
        self,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: int | None,
        line_mode: str | None,
        pk: int,
    ) -> PurchaseInvoiceHeader:
        try:
            return self._invoice_queryset(entity_id, entityfinid_id, subentity_id, line_mode=line_mode).get(pk=pk)
        except ObjectDoesNotExist:
            fallback = self._invoice_queryset(entity_id, entityfinid_id, subentity_id, line_mode=None).filter(pk=pk).first()
            if fallback is not None and line_mode in ("service", "goods"):
                actual_mode = "service" if fallback.lines.filter(is_service=True).exists() else "goods"
                if actual_mode != line_mode:
                    raise serializers.ValidationError(
                        {
                            "detail": f"Invoice belongs to '{actual_mode}' mode.",
                            "expected_line_mode": actual_mode,
                            "invoice_id": pk,
                        }
                    )
            raise NotFound("Purchase invoice not found for current scope/mode.")

    def _build_payload(self, header: PurchaseInvoiceHeader) -> dict:
        document_label = self._document_label(header)
        supplier_invoice_required = self._requires_supplier_invoice_number(header)
        supplier_invoice_present = bool((header.supplier_invoice_number or "").strip())
        vendor_registered = bool((header.vendor_gstin or "").strip())
        gst_tds_contract_present = bool((header.gst_tds_contract_ref or "").strip())
        it_tds_section_code = getattr(getattr(header, "tds_section", None), "section_code", None)
        note_reason_label = header.get_note_reason_display() if getattr(header, "note_reason", None) else None

        checks = [
            self._check(
                code="lifecycle",
                label="Lifecycle",
                status=self._lifecycle_check_status(header),
                detail=self._lifecycle_detail(header),
            ),
            self._check(
                code="supplier_invoice",
                label="Supplier Invoice Reference",
                status=(
                    "ready"
                    if supplier_invoice_present
                    else "blocked"
                    if supplier_invoice_required
                    else "info"
                ),
                detail=(
                    f"Supplier invoice number recorded as {header.supplier_invoice_number}."
                    if supplier_invoice_present
                    else "Supplier invoice number is mandatory for taxed, reverse-charge, or GST-TDS purchase flows."
                    if supplier_invoice_required
                    else "Supplier invoice number is optional for the current purchase context."
                ),
            ),
            self._check(
                code="vendor_tax_profile",
                label="Vendor GST Profile",
                status=(
                    "ready"
                    if vendor_registered
                    else "review"
                    if bool(header.is_reverse_charge)
                    else "info"
                ),
                detail=(
                    f"Vendor GSTIN captured as {header.vendor_gstin}."
                    if vendor_registered
                    else "Reverse-charge purchase is using the unregistered-vendor path."
                    if bool(header.is_reverse_charge)
                    else "Vendor GSTIN is not recorded on this document."
                ),
            ),
            self._check(
                code="itc",
                label="ITC Readiness",
                status=self._itc_check_status(header),
                detail=self._itc_detail(header),
            ),
            self._check(
                code="gst_tds",
                label="GST-TDS",
                status=(
                    "ready"
                    if bool(header.gst_tds_enabled) and gst_tds_contract_present
                    else "blocked"
                    if bool(header.gst_tds_enabled)
                    else "info"
                ),
                detail=(
                    f"GST-TDS is enabled against contract reference {header.gst_tds_contract_ref}."
                    if bool(header.gst_tds_enabled) and gst_tds_contract_present
                    else "GST-TDS is enabled but contract reference is missing."
                    if bool(header.gst_tds_enabled)
                    else "GST-TDS is not enabled on this document."
                ),
            ),
            self._check(
                code="it_tds",
                label="Income Tax TDS",
                status=(
                    "ready"
                    if bool(header.withholding_enabled) and bool(header.tds_section_id)
                    else "blocked"
                    if bool(header.withholding_enabled)
                    else "info"
                ),
                detail=(
                    f"Income Tax TDS is enabled with section {it_tds_section_code}."
                    if bool(header.withholding_enabled) and bool(header.tds_section_id)
                    else "Income Tax TDS is enabled but no section is attached."
                    if bool(header.withholding_enabled)
                    else "Income Tax TDS is not enabled on this document."
                ),
            ),
        ]
        if int(header.doc_type) != int(PurchaseInvoiceHeader.DocType.TAX_INVOICE):
            checks.append(
                self._check(
                    code="note_linkage",
                    label="Source Document Linkage",
                    status="ready" if header.ref_document_id else "blocked",
                    detail=(
                        f"{document_label} is linked to source document #{header.ref_document_id}"
                        + (f" under reason {note_reason_label}." if note_reason_label else ".")
                        if header.ref_document_id
                        else f"{document_label} is missing its source purchase document reference."
                    ),
                )
            )

        return {
            "invoice_id": header.id,
            "document_label": document_label,
            "status": int(header.status),
            "status_name": header.get_status_display(),
            "doc_type": int(header.doc_type),
            "doc_type_name": header.get_doc_type_display(),
            "can_open": True,
            "launcher_label": "Compliance",
            "launcher_hint": "Review purchase-side statutory readiness, withholding, and ITC state.",
            "summary_badges": [
                self._badge("Status", header.get_status_display(), self._status_tone(header)),
                self._badge("GSTR-2B", header.get_gstr2b_match_status_display(), self._gstr2b_tone(header)),
                self._badge("ITC", header.get_itc_claim_status_display(), self._itc_tone(header)),
                self._badge(
                    "GST-TDS",
                    header.get_gst_tds_status_display() if bool(header.gst_tds_enabled) else "Not Enabled",
                    "success" if bool(header.gst_tds_enabled) and gst_tds_contract_present else "warning" if bool(header.gst_tds_enabled) else "neutral",
                ),
                self._badge(
                    "IT-TDS",
                    it_tds_section_code or ("Enabled" if bool(header.withholding_enabled) else "Not Enabled"),
                    "success" if bool(header.withholding_enabled) and bool(header.tds_section_id) else "warning" if bool(header.withholding_enabled) else "neutral",
                ),
            ],
            "checks": checks,
            "totals": {
                "grand_total": self._money(header.grand_total),
                "total_gst": self._money(header.total_gst),
                "total_cess": self._money(header.total_cess),
                "gst_tds_amount": self._money(header.gst_tds_amount),
                "tds_amount": self._money(header.tds_amount),
            },
            "document_context": {
                "supplier_invoice_number": header.supplier_invoice_number or "",
                "vendor_gstin": header.vendor_gstin or "",
                "is_reverse_charge": bool(header.is_reverse_charge),
                "is_itc_eligible": bool(header.is_itc_eligible),
                "itc_block_reason": header.itc_block_reason or "",
                "gst_tds_enabled": bool(header.gst_tds_enabled),
                "gst_tds_contract_ref": header.gst_tds_contract_ref or "",
                "withholding_enabled": bool(header.withholding_enabled),
                "tds_section_code": it_tds_section_code or "",
                "note_reason": header.note_reason or "",
                "affects_inventory": bool(header.affects_inventory),
                "ref_document_id": header.ref_document_id,
                "supplier_invoice_required": supplier_invoice_required,
            },
        }

    def _requires_supplier_invoice_number(self, header: PurchaseInvoiceHeader) -> bool:
        if bool(header.is_reverse_charge) or bool(header.gst_tds_enabled):
            return True
        for row in list(header.lines.all()) + list(header.charges.all()):
            for field_name in (
                "gst_rate",
                "cgst_amount",
                "sgst_amount",
                "igst_amount",
                "cess_amount",
                "cgst_percent",
                "sgst_percent",
                "igst_percent",
                "cess_percent",
            ):
                raw = getattr(row, field_name, ZERO) or ZERO
                try:
                    if Decimal(str(raw)) > ZERO:
                        return True
                except Exception:
                    continue
        return False

    def _document_label(self, header: PurchaseInvoiceHeader) -> str:
        if int(header.doc_type) == int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE):
            return "Purchase Credit Note"
        if int(header.doc_type) == int(PurchaseInvoiceHeader.DocType.DEBIT_NOTE):
            return "Purchase Debit Note"
        return "Purchase Invoice"

    def _lifecycle_check_status(self, header: PurchaseInvoiceHeader) -> str:
        if int(header.status) == int(PurchaseInvoiceHeader.Status.POSTED):
            return "ready"
        if int(header.status) == int(PurchaseInvoiceHeader.Status.CONFIRMED):
            return "review"
        if int(header.status) == int(PurchaseInvoiceHeader.Status.CANCELLED):
            return "info"
        return "info"

    def _lifecycle_detail(self, header: PurchaseInvoiceHeader) -> str:
        if int(header.status) == int(PurchaseInvoiceHeader.Status.POSTED):
            return "Document is posted and its compliance snapshot reflects persisted accounting values."
        if int(header.status) == int(PurchaseInvoiceHeader.Status.CONFIRMED):
            return "Document is confirmed but not yet posted. Review statutory readiness before final posting."
        if int(header.status) == int(PurchaseInvoiceHeader.Status.CANCELLED):
            return "Document is cancelled. Compliance overview is retained for audit visibility."
        return "Document is still in draft. Save or post it to finalize statutory state."

    def _itc_check_status(self, header: PurchaseInvoiceHeader) -> str:
        if not bool(header.is_itc_eligible):
            return "blocked"
        if int(header.itc_claim_status) == int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED):
            return "ready"
        if int(header.itc_claim_status) == int(PurchaseInvoiceHeader.ItcClaimStatus.BLOCKED):
            return "blocked"
        if int(header.itc_claim_status) == int(PurchaseInvoiceHeader.ItcClaimStatus.REVERSED):
            return "review"
        return "review"

    def _itc_detail(self, header: PurchaseInvoiceHeader) -> str:
        if not bool(header.is_itc_eligible):
            reason = (header.itc_block_reason or "ITC is blocked on this document.").strip()
            return reason
        if int(header.itc_claim_status) == int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED):
            if header.itc_claim_period:
                return f"ITC already claimed for period {header.itc_claim_period}."
            return "ITC already claimed on this document."
        if int(header.itc_claim_status) == int(PurchaseInvoiceHeader.ItcClaimStatus.REVERSED):
            return "ITC was previously claimed and later reversed."
        return f"ITC is currently {header.get_itc_claim_status_display()} with GSTR-2B status {header.get_gstr2b_match_status_display()}."

    def _status_tone(self, header: PurchaseInvoiceHeader) -> str:
        if int(header.status) == int(PurchaseInvoiceHeader.Status.POSTED):
            return "success"
        if int(header.status) == int(PurchaseInvoiceHeader.Status.CONFIRMED):
            return "warning"
        if int(header.status) == int(PurchaseInvoiceHeader.Status.CANCELLED):
            return "danger"
        return "neutral"

    def _gstr2b_tone(self, header: PurchaseInvoiceHeader) -> str:
        status_value = int(header.gstr2b_match_status)
        if status_value == int(PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED):
            return "success"
        if status_value in (
            int(PurchaseInvoiceHeader.Gstr2bMatchStatus.MISMATCHED),
            int(PurchaseInvoiceHeader.Gstr2bMatchStatus.NOT_IN_2B),
        ):
            return "danger"
        if status_value == int(PurchaseInvoiceHeader.Gstr2bMatchStatus.PARTIAL):
            return "warning"
        return "neutral"

    def _itc_tone(self, header: PurchaseInvoiceHeader) -> str:
        status_value = int(header.itc_claim_status)
        if status_value == int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED):
            return "success"
        if status_value == int(PurchaseInvoiceHeader.ItcClaimStatus.BLOCKED):
            return "danger"
        if status_value == int(PurchaseInvoiceHeader.ItcClaimStatus.REVERSED):
            return "warning"
        return "neutral"

    def _badge(self, label: str, value: str, tone: str) -> dict:
        return {
            "label": label,
            "value": value,
            "tone": tone,
        }

    def _check(self, *, code: str, label: str, status: str, detail: str) -> dict:
        return {
            "code": code,
            "label": label,
            "status": status,
            "detail": detail,
        }

    def _money(self, value) -> str:
        try:
            return f"{Decimal(str(value or ZERO)).quantize(Decimal('0.01'))}"
        except Exception:
            return "0.00"
