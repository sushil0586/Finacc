from __future__ import annotations

"""
Validation rules for GSTR-1 readiness.

Coverage includes:
- GSTIN format and presence for likely B2B.
- POS vs tax regime coherence and export POS (96) enforcement.
- Duplicate detection by invoice_number+doc_type+doc_code within scope.
- Taxable/tax splits/line totals coherence and nil/exempt tax leakage.
- Credit/debit note linkage sanity.
- Non-positive or cancelled documents carrying amounts.
"""

from decimal import Decimal
import re

from django.db.models import Count, Q, Sum

from reports.gstr1.conf import export_pos_code, enable_gstin_checksum
from reports.gstr1.utils.gstin import format_valid as gstin_format_valid, is_valid as gstin_valid
from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary

GSTIN_RE = re.compile(r"^[0-9A-Z]{15}$")
TOLERANCE = Decimal("0.50")
POS_RE = re.compile(r"^[0-9]{2}$")


class Gstr1ValidationService:
    def __init__(self, *, base_queryset):
        self.base_queryset = base_queryset

    def run(self) -> list[dict]:
        warnings = []
        warnings.extend(self._invalid_gstin_warnings())
        warnings.extend(self._invalid_seller_gstin_warnings())
        warnings.extend(self._missing_gstin_warnings())
        warnings.extend(self._duplicate_invoice_warnings())
        warnings.extend(self._missing_place_of_supply_warnings())
        warnings.extend(self._invalid_place_of_supply_warnings())
        warnings.extend(self._pos_tax_regime_mismatch_warnings())
        warnings.extend(self._export_pos_warnings())
        warnings.extend(self._missing_hsn_warnings())
        warnings.extend(self._nil_exempt_tax_warnings())
        warnings.extend(self._tax_mismatch_warnings())
        warnings.extend(self._tax_split_mismatch_warnings())
        warnings.extend(self._invoice_total_mismatch_warnings())
        warnings.extend(self._invalid_note_linkage_warnings())
        warnings.extend(self._non_positive_taxable_warnings())
        warnings.extend(self._non_positive_total_warnings())
        warnings.extend(self._cancelled_amount_warnings())
        return warnings

    def _invalid_gstin_warnings(self):
        warnings = []
        checksum_enabled = enable_gstin_checksum()
        qs = self.base_queryset.exclude(customer_gstin__in=[None, ""])
        for row in qs.values("id", "invoice_number", "customer_gstin"):
            gstin = row["customer_gstin"]
            if not gstin_format_valid(gstin) or (checksum_enabled and not gstin_valid(gstin, checksum_enabled=True)):
                warnings.append(
                    _warning(
                        code="INVALID_GSTIN",
                        message="Customer GSTIN is invalid.",
                        invoice_id=row["id"],
                        invoice_number=row["invoice_number"],
                        field="customer_gstin",
                    )
                )
        return warnings

    def _invalid_seller_gstin_warnings(self):
        warnings = []
        qs = self.base_queryset.exclude(seller_gstin__in=[None, ""]).exclude(
            seller_gstin__regex=GSTIN_RE.pattern
        )
        for row in qs.values("id", "invoice_number", "seller_gstin"):
            warnings.append(
                _warning(
                    code="INVALID_SELLER_GSTIN",
                    message="Seller GSTIN is invalid.",
                    invoice_id=row["id"],
                    invoice_number=row["invoice_number"],
                    field="seller_gstin",
                    severity="warning",
                )
            )
        return warnings

    def _missing_gstin_warnings(self):
        b2b_supply = Q(
            supply_category__in=[
                SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
                SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
                SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
            ]
        )
        checksum = enable_gstin_checksum()
        qs = self.base_queryset.filter(b2b_supply).filter(
            Q(customer_gstin__in=[None, ""]) | ~Q(customer_gstin__regex=GSTIN_RE.pattern)
        )
        return [
            _warning(
                code="B2B_GSTIN_REQUIRED",
                message="Customer GSTIN is missing or invalid for B2B/SEZ/Deemed Export invoice.",
                invoice_id=row["id"],
                invoice_number=row["invoice_number"],
                field="customer_gstin",
                severity="warning",
            )
            for row in qs.values("id", "invoice_number")
        ]

    def _duplicate_invoice_warnings(self):
        duplicates = (
            self.base_queryset.exclude(invoice_number__in=[None, ""])
            .exclude(seller_gstin__in=[None, ""])
            .values("invoice_number", "doc_type", "seller_gstin")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        duplicate_map = {(row["invoice_number"], row["doc_type"], row["seller_gstin"]) for row in duplicates}
        if not duplicate_map:
            return []
        qs = self.base_queryset.filter(
            Q(invoice_number__in=[row[0] for row in duplicate_map]),
            Q(doc_type__in=[row[1] for row in duplicate_map]),
            Q(seller_gstin__in=[row[2] for row in duplicate_map]),
        ).values("id", "invoice_number", "doc_type", "seller_gstin")
        qs = [row for row in qs if (row["invoice_number"], row["doc_type"], row["seller_gstin"]) in duplicate_map]
        return [
            _warning(
                code="DUPLICATE_INVOICE",
                message="Duplicate invoice number found for same seller GSTIN and document type.",
                invoice_id=row["id"],
                invoice_number=row["invoice_number"],
                field="invoice_number",
                severity="warning",
            )
            for row in qs
        ]

    def _missing_place_of_supply_warnings(self):
        qs = self.base_queryset.filter(place_of_supply_state_code__in=[None, ""])
        return [
            _warning(
                code="MISSING_PLACE_OF_SUPPLY",
                message="Place of supply is missing.",
                invoice_id=row["id"],
                invoice_number=row["invoice_number"],
                field="place_of_supply_state_code",
                severity="warning",
            )
            for row in qs.values("id", "invoice_number")
        ]

    def _invalid_place_of_supply_warnings(self):
        qs = self.base_queryset.exclude(place_of_supply_state_code__in=[None, ""]).exclude(
            place_of_supply_state_code__regex=POS_RE.pattern
        )
        return [
            _warning(
                code="INVALID_PLACE_OF_SUPPLY",
                message="Place of supply must be a 2-digit GST state code.",
                invoice_id=row["id"],
                invoice_number=row["invoice_number"],
                field="place_of_supply_state_code",
                severity="warning",
            )
            for row in qs.values("id", "invoice_number")
        ]

    def _pos_tax_regime_mismatch_warnings(self):
        qs = self.base_queryset.exclude(place_of_supply_state_code__in=[None, ""]).exclude(seller_state_code__in=[None, ""])
        warnings = []
        for row in qs.values("id", "invoice_number", "place_of_supply_state_code", "seller_state_code", "tax_regime"):
            pos = row.get("place_of_supply_state_code")
            seller = row.get("seller_state_code")
            if not pos or not seller:
                continue
            if pos == seller and row["tax_regime"] == SalesInvoiceHeader.TaxRegime.INTER_STATE:
                warnings.append(
                    _warning(
                        code="POS_TAX_REGIME_MISMATCH",
                        message="Place of supply indicates intrastate but tax regime is inter-state.",
                        invoice_id=row["id"],
                        invoice_number=row["invoice_number"],
                        severity="warning",
                    )
                )
            if pos != seller and row["tax_regime"] == SalesInvoiceHeader.TaxRegime.INTRA_STATE:
                warnings.append(
                    _warning(
                        code="POS_TAX_REGIME_MISMATCH",
                        message="Place of supply indicates inter-state but tax regime is intra-state.",
                        invoice_id=row["id"],
                        invoice_number=row["invoice_number"],
                        severity="warning",
                    )
                )
        return warnings

    def _export_pos_warnings(self):
        export_supply = Q(
            supply_category__in=[
                SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
                SalesInvoiceHeader.SupplyCategory.EXPORT_WITHOUT_IGST,
            ]
        )
        export_pos = export_pos_code()
        qs = self.base_queryset.filter(export_supply).exclude(place_of_supply_state_code=export_pos)
        return [
            _warning(
                code="EXPORT_POS_INVALID",
                message=f"Export invoice should use place of supply code {export_pos}.",
                invoice_id=row["id"],
                invoice_number=row["invoice_number"],
                field="place_of_supply_state_code",
                severity="warning",
            )
            for row in qs.values("id", "invoice_number")
        ]

    def _missing_hsn_warnings(self):
        qs = SalesInvoiceLine.objects.filter(header__in=self.base_queryset).filter(
            Q(hsn_sac_code__in=[None, ""]) & (Q(gst_rate__gt=0) | Q(taxable_value__gt=0))
        ).values_list("header_id", flat=True)
        header_ids = set(qs)
        return [
            _warning(
                code="MISSING_HSN",
                message="HSN/SAC code is missing on a taxable line.",
                invoice_id=header_id,
                field="hsn_sac_code",
                severity="warning",
            )
            for header_id in header_ids
        ]

    def _nil_exempt_tax_warnings(self):
        qs = SalesTaxSummary.objects.filter(
            header__in=self.base_queryset,
            taxability__in=[
                SalesInvoiceHeader.Taxability.EXEMPT,
                SalesInvoiceHeader.Taxability.NIL_RATED,
                SalesInvoiceHeader.Taxability.NON_GST,
            ],
        ).values("header_id", "taxability").annotate(
            cgst=Sum("cgst_amount"),
            sgst=Sum("sgst_amount"),
            igst=Sum("igst_amount"),
            cess=Sum("cess_amount"),
        )
        warnings = []
        header_ids = {row["header_id"] for row in qs}
        header_map = {
            row["id"]: row
            for row in self.base_queryset.filter(id__in=header_ids).values("id", "invoice_number")
        }
        for row in qs:
            total_tax = Decimal(row.get("cgst") or 0) + Decimal(row.get("sgst") or 0) + Decimal(row.get("igst") or 0) + Decimal(row.get("cess") or 0)
            if total_tax > TOLERANCE:
                header = header_map.get(row["header_id"])
                if header:
                    warnings.append(
                        _warning(
                            code="NIL_EXEMPT_TAX_PRESENT",
                            message="Nil/Exempt/Non-GST invoice has tax amounts.",
                            invoice_id=header["id"],
                            invoice_number=header["invoice_number"],
                            severity="warning",
                        )
                    )
        return warnings

    def _tax_mismatch_warnings(self):
        tax_sums = (
            SalesTaxSummary.objects.filter(header__in=self.base_queryset)
            .values("header_id")
            .annotate(
                taxable=Sum("taxable_value"),
                cgst=Sum("cgst_amount"),
                sgst=Sum("sgst_amount"),
                igst=Sum("igst_amount"),
                cess=Sum("cess_amount"),
            )
        )
        summary_map = {row["header_id"]: row for row in tax_sums}
        warnings = []
        for header in self.base_queryset.values(
            "id",
            "invoice_number",
            "total_taxable_value",
            "total_cgst",
            "total_sgst",
            "total_igst",
            "total_cess",
        ):
            summary = summary_map.get(header["id"])
            if not summary:
                continue
            if _delta(summary["taxable"], header["total_taxable_value"]) > TOLERANCE:
                warnings.append(_warning("TAXABLE_MISMATCH", "Taxable value mismatch with tax summary.", header["id"], header["invoice_number"], severity="warning"))
            if _delta(summary["cgst"], header["total_cgst"]) > TOLERANCE:
                warnings.append(_warning("CGST_MISMATCH", "CGST mismatch with tax summary.", header["id"], header["invoice_number"], severity="warning"))
            if _delta(summary["sgst"], header["total_sgst"]) > TOLERANCE:
                warnings.append(_warning("SGST_MISMATCH", "SGST mismatch with tax summary.", header["id"], header["invoice_number"], severity="warning"))
            if _delta(summary["igst"], header["total_igst"]) > TOLERANCE:
                warnings.append(_warning("IGST_MISMATCH", "IGST mismatch with tax summary.", header["id"], header["invoice_number"], severity="warning"))
            if _delta(summary["cess"], header["total_cess"]) > TOLERANCE:
                warnings.append(_warning("CESS_MISMATCH", "Cess mismatch with tax summary.", header["id"], header["invoice_number"], severity="warning"))
        return warnings

    def _tax_split_mismatch_warnings(self):
        warnings = []
        qs = self.base_queryset.values(
            "id",
            "invoice_number",
            "tax_regime",
            "total_cgst",
            "total_sgst",
            "total_igst",
        )
        for row in qs:
            regime = row["tax_regime"]
            cgst = Decimal(row["total_cgst"] or 0)
            sgst = Decimal(row["total_sgst"] or 0)
            igst = Decimal(row["total_igst"] or 0)
            if regime == SalesInvoiceHeader.TaxRegime.INTRA_STATE and igst > TOLERANCE:
                warnings.append(
                    _warning(
                        code="IGST_ON_INTRASTATE",
                        message="IGST present for intrastate invoice.",
                        invoice_id=row["id"],
                        invoice_number=row["invoice_number"],
                        severity="warning",
                    )
                )
            if regime == SalesInvoiceHeader.TaxRegime.INTER_STATE and (cgst > TOLERANCE or sgst > TOLERANCE):
                warnings.append(
                    _warning(
                        code="CGST_SGST_ON_INTERSTATE",
                        message="CGST/SGST present for interstate invoice.",
                        invoice_id=row["id"],
                        invoice_number=row["invoice_number"],
                        severity="warning",
                    )
                )
        return warnings

    def _invoice_total_mismatch_warnings(self):
        line_sums = (
            SalesInvoiceLine.objects.filter(header__in=self.base_queryset)
            .values("header_id")
            .annotate(total=Sum("line_total"))
        )
        sum_map = {row["header_id"]: row["total"] for row in line_sums}
        warnings = []
        for header in self.base_queryset.values("id", "invoice_number", "grand_total"):
            line_total = sum_map.get(header["id"])
            if line_total is None:
                continue
            if _delta(line_total, header["grand_total"]) > TOLERANCE:
                warnings.append(
                    _warning(
                        code="INVOICE_TOTAL_MISMATCH",
                        message="Invoice grand total mismatch with line totals.",
                        invoice_id=header["id"],
                        invoice_number=header["invoice_number"],
                        severity="warning",
                    )
                )
        return warnings

    def _invalid_note_linkage_warnings(self):
        qs = self.base_queryset.filter(doc_type__in=[SalesInvoiceHeader.DocType.CREDIT_NOTE, SalesInvoiceHeader.DocType.DEBIT_NOTE])
        warnings = []
        rows = list(qs.values("id", "invoice_number", "original_invoice_id", "entity_id", "entityfinid_id", "subentity_id"))
        original_ids = {row["original_invoice_id"] for row in rows if row["original_invoice_id"]}
        originals = {
            row["id"]: row
            for row in SalesInvoiceHeader.objects.filter(id__in=original_ids).values("id", "entity_id", "entityfinid_id", "subentity_id", "doc_type")
        }
        for header in rows:
            if not header["original_invoice_id"]:
                warnings.append(_warning("NOTE_LINK_MISSING", "Credit/Debit note is missing original invoice linkage.", header["id"], header["invoice_number"], severity="warning"))
                continue
            original = originals.get(header["original_invoice_id"])
            if not original:
                warnings.append(_warning("NOTE_LINK_INVALID", "Original invoice not found for credit/debit note.", header["id"], header["invoice_number"], severity="warning"))
                continue
            if (
                int(original["entity_id"]) != int(header["entity_id"])
                or int(original["entityfinid_id"]) != int(header["entityfinid_id"])
                or int(original.get("subentity_id") or 0) != int(header.get("subentity_id") or 0)
            ):
                warnings.append(_warning("NOTE_LINK_SCOPE_MISMATCH", "Original invoice belongs to a different scope.", header["id"], header["invoice_number"], severity="warning"))
            if original.get("doc_type") not in (SalesInvoiceHeader.DocType.TAX_INVOICE,):
                warnings.append(_warning("NOTE_LINK_DOC_TYPE", "Original invoice is not a tax invoice.", header["id"], header["invoice_number"], severity="warning"))
        return warnings

    def _non_positive_taxable_warnings(self):
        qs = self.base_queryset.filter(
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            doc_type__in=[SalesInvoiceHeader.DocType.TAX_INVOICE, SalesInvoiceHeader.DocType.DEBIT_NOTE],
        ).filter(total_taxable_value__lte=0)
        return [
            _warning(
                code="NON_POSITIVE_TAXABLE",
                message="Taxable invoice has non-positive taxable value.",
                invoice_id=row["id"],
                invoice_number=row["invoice_number"],
                severity="warning",
            )
            for row in qs.values("id", "invoice_number")
        ]

    def _non_positive_total_warnings(self):
        qs = self.base_queryset.filter(doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE).filter(grand_total__lte=0)
        return [
            _warning(
                code="NON_POSITIVE_TOTAL",
                message="Tax invoice has non-positive grand total.",
                invoice_id=row["id"],
                invoice_number=row["invoice_number"],
                severity="warning",
            )
            for row in qs.values("id", "invoice_number")
        ]

    def _cancelled_amount_warnings(self):
        qs = self.base_queryset.filter(status=SalesInvoiceHeader.Status.CANCELLED).filter(
            Q(total_taxable_value__gt=0)
            | Q(total_cgst__gt=0)
            | Q(total_sgst__gt=0)
            | Q(total_igst__gt=0)
            | Q(total_cess__gt=0)
            | Q(grand_total__gt=0)
        )
        return [
            _warning(
                code="CANCELLED_HAS_AMOUNTS",
                message="Cancelled invoice has non-zero totals.",
                invoice_id=row["id"],
                invoice_number=row["invoice_number"],
                severity="warning",
            )
            for row in qs.values("id", "invoice_number")
        ]


def _warning(code, message, invoice_id=None, invoice_number=None, field=None, severity="warning"):
    payload = {"code": code, "message": message, "severity": severity}
    if invoice_id is not None:
        payload["invoice_id"] = invoice_id
    if invoice_number is not None:
        payload["invoice_number"] = invoice_number
    if field is not None:
        payload["field"] = field
    return payload


def _delta(a, b):
    if a is None or b is None:
        return Decimal("0")
    return abs(Decimal(a) - Decimal(b))
