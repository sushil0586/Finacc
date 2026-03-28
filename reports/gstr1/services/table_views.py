from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Max, Min, Q, Sum

from entity.models import Entity, EntityFinancialYear
from sales.models import SalesAdvanceAdjustment, SalesEcommerceSupply
from sales.models import SalesInvoiceHeader

from reports.gstr1.conf import b2cl_threshold, rcm_tax_amount_source
from reports.gstr1.services.classification import Gstr1ClassificationService, SECTION_B2CL, SECTION_B2CS, SECTION_CDNUR


@dataclass(frozen=True)
class Gstr1TableDefinition:
    code: str
    label: str


TABLE_1_3 = Gstr1TableDefinition("TAXPAYER_1_3", "1/2/3 Taxpayer Details")
TABLE_4 = Gstr1TableDefinition("TABLE_4", "4 B2B")
TABLE_5 = Gstr1TableDefinition("TABLE_5", "5 B2CL (Large)")
TABLE_6 = Gstr1TableDefinition("TABLE_6", "6 Exports / Deemed Exports / SEZ")
TABLE_7 = Gstr1TableDefinition("TABLE_7", "7 B2CS")
TABLE_8 = Gstr1TableDefinition("TABLE_8", "8 Nil Rated / Exempt / Non-GST")
TABLE_9 = Gstr1TableDefinition("TABLE_9", "9 Amendments (4/5/6)")
TABLE_10 = Gstr1TableDefinition("TABLE_10", "10 CDNUR")
TABLE_11 = Gstr1TableDefinition("TABLE_11", "11 Advances and Adjustments")
TABLE_12 = Gstr1TableDefinition("TABLE_12", "12 HSN Summary")
TABLE_13 = Gstr1TableDefinition("TABLE_13", "13 Documents Issued")
TABLE_14 = Gstr1TableDefinition("TABLE_14", "14 Supplier ECO GSTIN-wise Sales")
TABLE_14A = Gstr1TableDefinition("TABLE_14A", "14A Amendments to Table 14")
TABLE_15 = Gstr1TableDefinition("TABLE_15", "15 ECO Operator GSTIN-wise B2B/B2C")
TABLE_15A = Gstr1TableDefinition("TABLE_15A", "15A Amendments to Table 15")

ALL_GSTR1_TABLES = (
    TABLE_1_3,
    TABLE_4,
    TABLE_5,
    TABLE_6,
    TABLE_7,
    TABLE_8,
    TABLE_9,
    TABLE_10,
    TABLE_11,
    TABLE_12,
    TABLE_13,
    TABLE_14,
    TABLE_14A,
    TABLE_15,
    TABLE_15A,
)


class Gstr1TableViewService:
    def __init__(self, *, scope, base_queryset):
        self.scope = scope
        self.base_queryset = base_queryset

    @staticmethod
    def table_definitions():
        return ALL_GSTR1_TABLES

    def build(self, table_code: str):
        code = (table_code or "").upper()
        if code == TABLE_1_3.code:
            return self._table_taxpayer()
        if code in {TABLE_4.code, "4"}:
            return self._table_4()
        if code == TABLE_5.code:
            return self._table_5()
        if code == TABLE_6.code:
            return self._table_6()
        if code == TABLE_7.code:
            return self._table_7()
        if code == TABLE_8.code:
            return self._table_8()
        if code == TABLE_9.code:
            return self._table_9()
        if code == TABLE_10.code:
            return self._table_10()
        if code == TABLE_11.code:
            return self._table_11()
        if code == TABLE_12.code:
            return self._table_12()
        if code == TABLE_13.code:
            return self._table_13()
        if code == TABLE_14.code:
            return self._table_14()
        if code == TABLE_14A.code:
            return self._table_14a()
        if code == TABLE_15.code:
            return self._table_15()
        if code == TABLE_15A.code:
            return self._table_15a()
        raise ValueError(f"Unsupported table code: {table_code}")

    def _table_taxpayer(self):
        entity = Entity.objects.filter(id=self.scope.entity_id).first()
        if not entity:
            return self._unsupported(TABLE_1_3, "Entity not found in selected scope.")

        gstin = (
            entity.gst_registrations.filter(isactive=True, is_primary=True)
            .values_list("gstin", flat=True)
            .first()
            or entity.gst_registrations.filter(isactive=True).values_list("gstin", flat=True).first()
            or ""
        )
        current_fy = None
        if self.scope.entityfinid_id:
            current_fy = EntityFinancialYear.objects.filter(id=self.scope.entityfinid_id, entity_id=entity.id).first()
        previous_turnover = Decimal("0.00")
        if current_fy:
            previous_fy = (
                EntityFinancialYear.objects.filter(entity_id=entity.id, finstartyear__lt=current_fy.finstartyear)
                .order_by("-finstartyear")
                .first()
            )
            if previous_fy and previous_fy.finstartyear and previous_fy.finendyear:
                previous_turnover = (
                    SalesInvoiceHeader.objects.filter(
                        entity_id=entity.id,
                        bill_date__gte=previous_fy.finstartyear.date(),
                        bill_date__lte=previous_fy.finendyear.date(),
                    )
                    .exclude(status=SalesInvoiceHeader.Status.CANCELLED)
                    .aggregate(total=Sum("grand_total"))
                    .get("total")
                    or Decimal("0.00")
                )

        rows = [
            {
                "gstin": gstin,
                "legal_name": entity.legalname or entity.entityname or "",
                "trade_name": entity.trade_name or entity.entityname or "",
                "previous_financial_year_aggregate_turnover": previous_turnover,
            }
        ]
        return self._ok(TABLE_1_3, rows)

    def _table_5(self):
        qs = self.base_queryset.filter(
            Gstr1ClassificationService.section_filter(SECTION_B2CL.code)
        ).order_by("bill_date", "doc_code", "doc_no", "id")
        rows = []
        for row in qs:
            payload = {
                "invoice_id": row.id,
                "invoice_number": row.invoice_number or f"{row.doc_code}-{row.doc_no}",
                "invoice_date": row.bill_date,
                "customer_name": row.customer_name,
                "place_of_supply_state_code": row.place_of_supply_state_code,
                "taxable_amount": row.total_taxable_value,
                "igst_amount": row.total_igst,
                "cess_amount": row.total_cess,
                "grand_total": row.grand_total,
            }
            rows.append(self._attach_invoice_rcm_contract(payload, row, table_code=TABLE_5.code))
        return self._ok(TABLE_5, rows)

    def _table_4(self):
        qs = self.base_queryset.filter(
            Gstr1ClassificationService.section_filter("B2B")
        ).order_by("bill_date", "doc_code", "doc_no", "id")
        rows = []
        for row in qs:
            payload = {
                "invoice_id": row.id,
                "invoice_number": row.invoice_number or f"{row.doc_code}-{row.doc_no}",
                "invoice_date": row.bill_date,
                "customer_name": row.customer_name,
                "customer_gstin": row.customer_gstin,
                "place_of_supply_state_code": row.place_of_supply_state_code,
                "taxable_amount": row.total_taxable_value,
                "cgst_amount": row.total_cgst,
                "sgst_amount": row.total_sgst,
                "igst_amount": row.total_igst,
                "cess_amount": row.total_cess,
                "grand_total": row.grand_total,
            }
            rows.append(self._attach_invoice_rcm_contract(payload, row, table_code=TABLE_4.code))
        return self._ok(TABLE_4, rows)

    def _table_6(self):
        qs = self.base_queryset.filter(
            supply_category__in=[
                SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
                SalesInvoiceHeader.SupplyCategory.EXPORT_WITHOUT_IGST,
                SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
                SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
                SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
            ]
        ).order_by("bill_date", "doc_code", "doc_no", "id")
        rows = []
        for row in qs:
            payload = {
                "invoice_id": row.id,
                "invoice_number": row.invoice_number or f"{row.doc_code}-{row.doc_no}",
                "invoice_date": row.bill_date,
                "supply_category": row.get_supply_category_display(),
                "tax_regime": row.get_tax_regime_display(),
                "customer_name": row.customer_name,
                "customer_gstin": row.customer_gstin,
                "place_of_supply_state_code": row.place_of_supply_state_code,
                "taxable_amount": row.total_taxable_value,
                "igst_amount": row.total_igst,
                "cess_amount": row.total_cess,
                "grand_total": row.grand_total,
            }
            rows.append(self._attach_invoice_rcm_contract(payload, row, table_code=TABLE_6.code))
        return self._ok(TABLE_6, rows)

    def _table_7(self):
        qs = self.base_queryset.filter(
            Gstr1ClassificationService.section_filter(SECTION_B2CS.code)
        )
        tax_rows = (
            qs.values(
                "place_of_supply_state_code",
                "tax_summaries__gst_rate",
                "tax_summaries__taxability",
            )
            .annotate(
                taxable_value=Sum("tax_summaries__taxable_value"),
                cgst_amount=Sum("tax_summaries__cgst_amount"),
                sgst_amount=Sum("tax_summaries__sgst_amount"),
                igst_amount=Sum("tax_summaries__igst_amount"),
                cess_amount=Sum("tax_summaries__cess_amount"),
            )
            .order_by("place_of_supply_state_code", "tax_summaries__gst_rate", "tax_summaries__taxability")
        )
        rows = []
        for row in tax_rows:
            taxability = row.get("tax_summaries__taxability")
            rows.append(
                {
                    "place_of_supply_state_code": row.get("place_of_supply_state_code") or "",
                    "gst_rate": row.get("tax_summaries__gst_rate") or Decimal("0.00"),
                    "taxability": taxability,
                    "taxability_label": SalesInvoiceHeader.Taxability(taxability).label
                    if taxability in SalesInvoiceHeader.Taxability.values
                    else "",
                    "taxable_value": row.get("taxable_value") or Decimal("0.00"),
                    "cgst_amount": row.get("cgst_amount") or Decimal("0.00"),
                    "sgst_amount": row.get("sgst_amount") or Decimal("0.00"),
                    "igst_amount": row.get("igst_amount") or Decimal("0.00"),
                    "cess_amount": row.get("cess_amount") or Decimal("0.00"),
                }
            )
        return self._ok(TABLE_7, rows)

    def _table_8(self):
        rows = []
        tax_rows = (
            self.base_queryset.filter(
                tax_summaries__taxability__in=[
                    SalesInvoiceHeader.Taxability.EXEMPT,
                    SalesInvoiceHeader.Taxability.NIL_RATED,
                    SalesInvoiceHeader.Taxability.NON_GST,
                ]
            )
            .values("tax_summaries__taxability")
            .annotate(
                taxable_value=Sum("tax_summaries__taxable_value"),
                cgst_amount=Sum("tax_summaries__cgst_amount"),
                sgst_amount=Sum("tax_summaries__sgst_amount"),
                igst_amount=Sum("tax_summaries__igst_amount"),
                cess_amount=Sum("tax_summaries__cess_amount"),
            )
            .order_by("tax_summaries__taxability")
        )
        for row in tax_rows:
            taxability = row.get("tax_summaries__taxability")
            rows.append(
                {
                    "taxability": taxability,
                    "taxability_label": SalesInvoiceHeader.Taxability(taxability).label
                    if taxability in SalesInvoiceHeader.Taxability.values
                    else "",
                    "taxable_value": row.get("taxable_value") or Decimal("0.00"),
                    "cgst_amount": row.get("cgst_amount") or Decimal("0.00"),
                    "sgst_amount": row.get("sgst_amount") or Decimal("0.00"),
                    "igst_amount": row.get("igst_amount") or Decimal("0.00"),
                    "cess_amount": row.get("cess_amount") or Decimal("0.00"),
                }
            )
        return self._ok(TABLE_8, rows)

    def _table_9(self):
        notes = (
            self.base_queryset.filter(
                doc_type__in=[SalesInvoiceHeader.DocType.CREDIT_NOTE, SalesInvoiceHeader.DocType.DEBIT_NOTE],
                original_invoice__isnull=False,
            )
            .select_related("original_invoice")
            .order_by("bill_date", "doc_code", "doc_no", "id")
        )
        rows = []
        for note in notes:
            original = note.original_invoice
            target_section = self._classify_original_for_amendment(original)
            payload = {
                "note_id": note.id,
                "note_number": note.invoice_number or f"{note.doc_code}-{note.doc_no}",
                "note_date": note.bill_date,
                "note_type": note.get_doc_type_display(),
                "original_invoice_id": original.id if original else None,
                "original_invoice_number": original.invoice_number if original else "",
                "amendment_target_section": target_section,
                "taxable_amount": note.total_taxable_value,
                "cgst_amount": note.total_cgst,
                "sgst_amount": note.total_sgst,
                "igst_amount": note.total_igst,
                "cess_amount": note.total_cess,
                "grand_total": note.grand_total,
            }
            rows.append(self._attach_invoice_rcm_contract(payload, note, table_code=TABLE_9.code))
        return self._ok(TABLE_9, rows)

    def _table_10(self):
        notes = self.base_queryset.filter(
            Gstr1ClassificationService.section_filter(SECTION_CDNUR.code)
        ).order_by("bill_date", "doc_code", "doc_no", "id")
        rows = []
        for note in notes:
            payload = {
                "note_id": note.id,
                "note_number": note.invoice_number or f"{note.doc_code}-{note.doc_no}",
                "note_date": note.bill_date,
                "note_type": note.get_doc_type_display(),
                "place_of_supply_state_code": note.place_of_supply_state_code,
                "taxable_amount": note.total_taxable_value,
                "igst_amount": note.total_igst,
                "cess_amount": note.total_cess,
                "grand_total": note.grand_total,
            }
            rows.append(self._attach_invoice_rcm_contract(payload, note, table_code=TABLE_10.code))
        return self._ok(TABLE_10, rows)

    def _table_11(self):
        qs = self._scoped(SalesAdvanceAdjustment.objects.all()).order_by("voucher_date", "id")
        if self.scope.from_date:
            qs = qs.filter(voucher_date__gte=self.scope.from_date)
        if self.scope.to_date:
            qs = qs.filter(voucher_date__lte=self.scope.to_date)
        rows = []
        rows_11a = []
        rows_11b = []
        for row in qs:
            payload = {
                "id": row.id,
                "voucher_date": row.voucher_date,
                "voucher_number": row.voucher_number,
                "entry_type": row.entry_type,
                "customer_name": row.customer_name,
                "customer_gstin": row.customer_gstin,
                "place_of_supply_state_code": row.place_of_supply_state_code,
                "taxable_value": row.taxable_value,
                "cgst_amount": row.cgst_amount,
                "sgst_amount": row.sgst_amount,
                "igst_amount": row.igst_amount,
                "cess_amount": row.cess_amount,
                "linked_invoice_id": row.linked_invoice_id,
                "is_amendment": row.is_amendment,
                "original_entry_id": row.original_entry_id,
            }
            rows.append(payload)
            if row.entry_type == SalesAdvanceAdjustment.EntryType.ADVANCE_RECEIPT:
                rows_11a.append(payload)
            elif row.entry_type == SalesAdvanceAdjustment.EntryType.ADVANCE_ADJUSTMENT:
                rows_11b.append(payload)
        result = self._ok(TABLE_11, rows)
        result["groups"] = {
            "11A": {"count": len(rows_11a), "rows": rows_11a},
            "11B": {"count": len(rows_11b), "rows": rows_11b},
        }
        return result

    def _table_12(self):
        rows = []

        # Amount/tax from tax summary so charges are included.
        tax_rows = list(
            self.base_queryset.values(
                "tax_summaries__hsn_sac_code",
                "tax_summaries__is_service",
                "tax_summaries__gst_rate",
            )
            .annotate(
                taxable_value=Sum("tax_summaries__taxable_value"),
                cgst_amount=Sum("tax_summaries__cgst_amount"),
                sgst_amount=Sum("tax_summaries__sgst_amount"),
                igst_amount=Sum("tax_summaries__igst_amount"),
                cess_amount=Sum("tax_summaries__cess_amount"),
            )
            .order_by("tax_summaries__hsn_sac_code", "tax_summaries__gst_rate", "tax_summaries__is_service")
        )

        # Quantity from invoice lines only.
        qty_rows = (
            self.base_queryset.values(
                "lines__hsn_sac_code",
                "lines__is_service",
                "lines__gst_rate",
            )
            .annotate(total_qty=Sum("lines__qty"))
        )
        qty_map = {}
        for row in qty_rows:
            key = (row.get("lines__hsn_sac_code") or "", bool(row.get("lines__is_service")), row.get("lines__gst_rate"))
            qty_map[key] = row.get("total_qty") or Decimal("0.00")

        for row in tax_rows:
            hsn = row.get("tax_summaries__hsn_sac_code") or ""
            is_service = bool(row.get("tax_summaries__is_service"))
            gst_rate = row.get("tax_summaries__gst_rate") or Decimal("0.00")
            key = (hsn, is_service, gst_rate)
            rows.append(
                {
                    "hsn_sac_code": hsn,
                    "is_service": is_service,
                    "gst_rate": gst_rate,
                    "total_qty": qty_map.get(key, Decimal("0.00")),
                    "taxable_value": row.get("taxable_value") or Decimal("0.00"),
                    "cgst_amount": row.get("cgst_amount") or Decimal("0.00"),
                    "sgst_amount": row.get("sgst_amount") or Decimal("0.00"),
                    "igst_amount": row.get("igst_amount") or Decimal("0.00"),
                    "cess_amount": row.get("cess_amount") or Decimal("0.00"),
                }
            )
        return self._ok(TABLE_12, rows)

    def _table_13(self):
        rows = []
        doc_rows = (
            self.base_queryset.values("doc_type", "doc_code")
            .annotate(
                document_count=Count("id"),
                cancelled_count=Count("id", filter=Q(status=SalesInvoiceHeader.Status.CANCELLED)),
                min_doc_no=Min("doc_no"),
                max_doc_no=Max("doc_no"),
            )
            .order_by("doc_type", "doc_code")
        )
        # Recompute cancelled_count using dedicated query for deterministic behavior.
        for row in doc_rows:
            doc_type = row.get("doc_type")
            label = ""
            if doc_type in SalesInvoiceHeader.DocType.values:
                label = SalesInvoiceHeader.DocType(doc_type).label
            qs = self.base_queryset.filter(doc_type=doc_type, doc_code=row.get("doc_code"))
            rows.append(
                {
                    "doc_type": doc_type,
                    "doc_type_label": label,
                    "doc_code": row.get("doc_code") or "",
                    "document_count": row.get("document_count") or 0,
                    "cancelled_count": qs.filter(status=SalesInvoiceHeader.Status.CANCELLED).count(),
                    "min_doc_no": row.get("min_doc_no"),
                    "max_doc_no": row.get("max_doc_no"),
                }
            )
        return self._ok(TABLE_13, rows)

    def _table_14(self):
        base = self._scoped(SalesEcommerceSupply.objects.filter(is_amendment=False))
        if self.scope.from_date:
            base = base.filter(invoice_date__gte=self.scope.from_date)
        if self.scope.to_date:
            base = base.filter(invoice_date__lte=self.scope.to_date)
        qs = base.values("supplier_eco_gstin").annotate(
            taxable_value=Sum("taxable_value"),
            cgst_amount=Sum("cgst_amount"),
            sgst_amount=Sum("sgst_amount"),
            igst_amount=Sum("igst_amount"),
            cess_amount=Sum("cess_amount"),
        ).order_by("supplier_eco_gstin")
        rows = [
            {
                "supplier_eco_gstin": row.get("supplier_eco_gstin") or "",
                "taxable_value": row.get("taxable_value") or Decimal("0.00"),
                "cgst_amount": row.get("cgst_amount") or Decimal("0.00"),
                "sgst_amount": row.get("sgst_amount") or Decimal("0.00"),
                "igst_amount": row.get("igst_amount") or Decimal("0.00"),
                "cess_amount": row.get("cess_amount") or Decimal("0.00"),
            }
            for row in qs
        ]
        return self._ok(TABLE_14, rows)

    def _table_14a(self):
        qs = self._scoped(SalesEcommerceSupply.objects.filter(is_amendment=True))
        if self.scope.from_date:
            qs = qs.filter(invoice_date__gte=self.scope.from_date)
        if self.scope.to_date:
            qs = qs.filter(invoice_date__lte=self.scope.to_date)
        qs = qs.order_by("invoice_date", "id")
        rows = []
        for row in qs:
            rows.append(
                {
                    "id": row.id,
                    "invoice_date": row.invoice_date,
                    "invoice_number": row.invoice_number,
                    "supplier_eco_gstin": row.supplier_eco_gstin,
                    "taxable_value": row.taxable_value,
                    "cgst_amount": row.cgst_amount,
                    "sgst_amount": row.sgst_amount,
                    "igst_amount": row.igst_amount,
                    "cess_amount": row.cess_amount,
                    "original_row_id": row.original_row_id,
                }
            )
        return self._ok(TABLE_14A, rows)

    def _table_15(self):
        base = self._scoped(SalesEcommerceSupply.objects.filter(is_amendment=False))
        if self.scope.from_date:
            base = base.filter(invoice_date__gte=self.scope.from_date)
        if self.scope.to_date:
            base = base.filter(invoice_date__lte=self.scope.to_date)
        qs = base.values("operator_gstin", "supply_split").annotate(
            taxable_value=Sum("taxable_value"),
            cgst_amount=Sum("cgst_amount"),
            sgst_amount=Sum("sgst_amount"),
            igst_amount=Sum("igst_amount"),
            cess_amount=Sum("cess_amount"),
        ).order_by("operator_gstin", "supply_split")
        rows = [
            {
                "operator_gstin": row.get("operator_gstin") or "",
                "supply_split": row.get("supply_split") or "",
                "taxable_value": row.get("taxable_value") or Decimal("0.00"),
                "cgst_amount": row.get("cgst_amount") or Decimal("0.00"),
                "sgst_amount": row.get("sgst_amount") or Decimal("0.00"),
                "igst_amount": row.get("igst_amount") or Decimal("0.00"),
                "cess_amount": row.get("cess_amount") or Decimal("0.00"),
            }
            for row in qs
        ]
        return self._ok(TABLE_15, rows)

    def _table_15a(self):
        qs = self._scoped(SalesEcommerceSupply.objects.filter(is_amendment=True))
        if self.scope.from_date:
            qs = qs.filter(invoice_date__gte=self.scope.from_date)
        if self.scope.to_date:
            qs = qs.filter(invoice_date__lte=self.scope.to_date)
        qs = qs.order_by("invoice_date", "id")
        rows = []
        for row in qs:
            rows.append(
                {
                    "id": row.id,
                    "invoice_date": row.invoice_date,
                    "invoice_number": row.invoice_number,
                    "operator_gstin": row.operator_gstin,
                    "supply_split": row.supply_split,
                    "taxable_value": row.taxable_value,
                    "cgst_amount": row.cgst_amount,
                    "sgst_amount": row.sgst_amount,
                    "igst_amount": row.igst_amount,
                    "cess_amount": row.cess_amount,
                    "original_row_id": row.original_row_id,
                }
            )
        return self._ok(TABLE_15A, rows)

    def _classify_original_for_amendment(self, original: SalesInvoiceHeader | None) -> str:
        if not original:
            return "UNMAPPED"
        supply = original.supply_category
        if supply in {
            SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
            SalesInvoiceHeader.SupplyCategory.EXPORT_WITHOUT_IGST,
            SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
            SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
            SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
        }:
            return "TABLE_6"

        has_gstin = bool((original.customer_gstin or "").strip())
        if has_gstin or supply == SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B:
            return "B2B"

        interstate = False
        if original.seller_state_code and original.place_of_supply_state_code:
            interstate = original.seller_state_code != original.place_of_supply_state_code
        else:
            interstate = bool(original.is_igst) or original.tax_regime == SalesInvoiceHeader.TaxRegime.INTER_STATE
        if interstate and (original.grand_total or Decimal("0")) >= b2cl_threshold():
            return "B2CL"
        return "B2CS"

    def _ok(self, definition: Gstr1TableDefinition, rows):
        return {
            "table_code": definition.code,
            "table_label": definition.label,
            "count": len(rows),
            "rows": rows,
            "contracts": {
                "reverse_charge": {
                    "version": "gstr1.rcm.v1",
                    "tax_amount_source": rcm_tax_amount_source(),
                }
            },
            "coverage": {
                "status": "implemented",
                "message": "",
            },
        }

    def _unsupported(self, definition: Gstr1TableDefinition, message: str):
        return {
            "table_code": definition.code,
            "table_label": definition.label,
            "count": 0,
            "rows": [],
            "coverage": {
                "status": "not_available",
                "message": message,
            },
        }

    def _scoped(self, queryset):
        queryset = queryset.filter(entity_id=self.scope.entity_id)
        if self.scope.entityfinid_id:
            queryset = queryset.filter(entityfinid_id=self.scope.entityfinid_id)
        if self.scope.subentity_id:
            queryset = queryset.filter(subentity_id=self.scope.subentity_id)
        return queryset

    def _attach_invoice_rcm_contract(self, payload: dict, invoice: SalesInvoiceHeader, *, table_code: str) -> dict:
        is_reverse = bool(getattr(invoice, "is_reverse_charge", False))
        taxable = payload.get("taxable_amount", Decimal("0.00")) or Decimal("0.00")
        cgst = payload.get("cgst_amount", Decimal("0.00")) or Decimal("0.00")
        sgst = payload.get("sgst_amount", Decimal("0.00")) or Decimal("0.00")
        igst = payload.get("igst_amount", Decimal("0.00")) or Decimal("0.00")
        cess = payload.get("cess_amount", Decimal("0.00")) or Decimal("0.00")

        payload["reverse_charge"] = is_reverse
        payload["reported_taxable_amount"] = taxable
        payload["reported_cgst_amount"] = cgst
        payload["reported_sgst_amount"] = sgst
        payload["reported_igst_amount"] = igst
        payload["reported_cess_amount"] = cess
        payload["rcm_contract"] = {
            "version": "gstr1.rcm.v1",
            "table_code": table_code,
            "is_reverse_charge": is_reverse,
            "liability_side": "recipient" if is_reverse else "supplier",
            "tax_amount_source": rcm_tax_amount_source(),
            "invoice_tax_amounts_zero_expected": is_reverse,
            "reporting_note": "For reverse charge invoices, liability remains on recipient; contract fields keep filing output deterministic.",
        }
        return payload
