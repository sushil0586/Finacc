from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Case, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError as DRFValidationError

from entity.models import EntityFinancialYear
from reports.gstr3b.services import Gstr3bSummaryService
from reports.gstr9.services.meta import PHASE0_TABLE_CATALOG
from reports.gstr9.selectors.scope import parse_scope_params
from reports.selectors.financial import ensure_date
from purchase.models import PurchaseInvoiceHeader
from sales.models import SalesInvoiceHeader, SalesTaxSummary

ZERO = Decimal("0.00")
TWOPLACES = Decimal("0.01")
SIGNED_OUTPUT = DecimalField(max_digits=24, decimal_places=2)
SUM_OUTPUT = DecimalField(max_digits=24, decimal_places=2)


class Gstr9ReportService:
    def build_scope(self, params):
        return parse_scope_params(params)

    def summary(self, scope):
        table_rows = []
        for row in PHASE0_TABLE_CATALOG:
            code = row["code"]
            status = "implemented" if code in {"TABLE_4", "TABLE_5", "TABLE_6", "TABLE_7", "TABLE_8", "TABLE_9", "TABLE_10_14", "TABLE_15_19"} else "planned"
            table_rows.append({"code": code, "label": row["label"], "status": status})
        return {
            "phase": 1,
            "status": "phase1_complete",
            "message": "Phase 1 complete for the locked table catalog: computation, validations, exports, and freeze snapshots are available.",
            "tables": table_rows,
        }

    def table(self, scope, table_code: str):
        requested = str(table_code or "").strip().upper()
        definition = next((row for row in PHASE0_TABLE_CATALOG if row["code"] == requested), None)
        if not definition:
            raise DRFValidationError({"table_code": ["Unsupported table code."]})
        if requested == "TABLE_4":
            return self._build_table_4(scope, definition)
        if requested == "TABLE_5":
            return self._build_table_5(scope, definition)
        if requested == "TABLE_6":
            return self._build_table_6(scope, definition)
        if requested == "TABLE_7":
            return self._build_table_7(scope, definition)
        if requested == "TABLE_8":
            return self._build_table_8(scope, definition)
        if requested == "TABLE_9":
            return self._build_table_9(scope, definition)
        if requested == "TABLE_10_14":
            return self._build_table_10_14(scope, definition)
        if requested == "TABLE_15_19":
            return self._build_table_15_19(scope, definition)
        return {
            "table_code": definition["code"],
            "table_label": definition["label"],
            "count": 0,
            "rows": [],
            "coverage": {
                "status": "planned",
                "message": "Table computation is not implemented yet in this phase.",
            },
        }

    def validations(self, scope):
        warnings = []
        table_4 = self._build_table_4(scope, {"code": "TABLE_4", "label": "Supplies on Which Tax is Payable"})
        table_5 = self._build_table_5(scope, {"code": "TABLE_5", "label": "Supplies on Which Tax is Not Payable"})
        table_6 = self._build_table_6(scope, {"code": "TABLE_6", "label": "Input Tax Credit Availed"})
        table_7 = self._build_table_7(scope, {"code": "TABLE_7", "label": "ITC Reversed and Ineligible"})
        table_8 = self._build_table_8(scope, {"code": "TABLE_8", "label": "ITC Reconciliation"})
        table_9 = self._build_table_9(scope, {"code": "TABLE_9", "label": "Tax Paid and Payable"})
        table_10_14 = self._build_table_10_14(scope, {"code": "TABLE_10_14", "label": "Amendments and Adjustments"})
        table_15_19 = self._build_table_15_19(scope, {"code": "TABLE_15_19", "label": "Demands, Refunds and HSN"})
        table_4_total_tax = Decimal(table_4["rows"][-1]["total_tax"] or ZERO)
        table_9_payable = Decimal(table_9["rows"][0]["total_tax"] or ZERO)
        if table_4_total_tax != table_9_payable:
            warnings.append(
                {
                    "code": "TABLE4_TABLE9_TAX_MISMATCH",
                    "severity": "error",
                    "message": "Table 4 total tax and Table 9 payable tax are not aligned.",
                    "table_code": "TABLE_9",
                    "field": "total_tax",
                }
            )
        table_5_total_tax = Decimal(table_5["rows"][-1]["total_tax"] or ZERO)
        if table_5_total_tax != ZERO:
            warnings.append(
                {
                    "code": "TABLE5_NONZERO_TAX_DETECTED",
                    "severity": "warning",
                    "message": "Table 5 contains non-zero tax. Review taxability and supply category tagging.",
                    "table_code": "TABLE_5",
                    "field": "total_tax",
                }
            )

        from_date, to_date, effective_entityfinid_id = self._resolve_date_window(scope)
        gstr3b_scope = Gstr3bSummaryService().build_scope(
            {
                "entity": scope.entity_id,
                "entityfinid": effective_entityfinid_id,
                "subentity": scope.subentity_id,
                "from_date": from_date,
                "to_date": to_date,
            }
        )
        gstr3b_summary = Gstr3bSummaryService().build(gstr3b_scope)
        gstr9_itc_available = Decimal(table_6["rows"][-1]["total_tax"] or ZERO)
        gstr3b_itc_available = Decimal(gstr3b_summary["section_4"]["itc_available"]["total_tax"] or ZERO)
        if gstr9_itc_available != gstr3b_itc_available:
            warnings.append(
                {
                    "code": "TABLE6_GSTR3B_ITC_AVAILABLE_MISMATCH",
                    "severity": "warning",
                    "message": "Table 6 ITC available does not match GSTR-3B section 4 ITC available.",
                    "table_code": "TABLE_6",
                    "field": "total_tax",
                }
            )

        gstr9_itc_reversed = Decimal(table_7["rows"][-1]["total_tax"] or ZERO)
        gstr3b_itc_reversed = Decimal(gstr3b_summary["section_4"]["itc_reversed"]["total_tax"] or ZERO)
        if gstr9_itc_reversed != gstr3b_itc_reversed:
            warnings.append(
                {
                    "code": "TABLE7_GSTR3B_ITC_REVERSED_MISMATCH",
                    "severity": "warning",
                    "message": "Table 7 ITC reversed does not match GSTR-3B section 4 ITC reversed.",
                    "table_code": "TABLE_7",
                    "field": "total_tax",
                }
            )
        table_8_diff_tax = Decimal(table_8["rows"][-1]["total_tax"] or ZERO)
        if table_8_diff_tax != ZERO:
            warnings.append(
                {
                    "code": "TABLE8_ITC_RECON_DIFFERENCE",
                    "severity": "info",
                    "message": "Table 8 shows a difference between books ITC and matched 2B ITC.",
                    "table_code": "TABLE_8",
                    "field": "total_tax",
                }
            )
        unlinked_amendment_tax = Decimal(table_10_14["rows"][3]["total_tax"] or ZERO)
        if unlinked_amendment_tax != ZERO:
            warnings.append(
                {
                    "code": "TABLE10_14_UNLINKED_NOTES",
                    "severity": "warning",
                    "message": "Credit/Debit notes without linked original invoice are present in annual scope.",
                    "table_code": "TABLE_10_14",
                    "field": "original_invoice",
                }
            )
        missing_hsn_tax = Decimal(table_15_19["rows"][6]["total_tax"] or ZERO)
        if missing_hsn_tax != ZERO:
            warnings.append(
                {
                    "code": "TABLE15_19_HSN_MISSING",
                    "severity": "warning",
                    "message": "Taxable sales summary rows exist without HSN/SAC code.",
                    "table_code": "TABLE_15_19",
                    "field": "hsn_sac_code",
                }
            )

        if not scope.entityfinid_id:
            warnings.append(
                {
                    "code": "ENTITYFINID_RECOMMENDED",
                    "severity": "warning",
                    "message": "entityfinid is recommended for annual-return accuracy.",
                    "table_code": "",
                    "field": "entityfinid",
                }
            )
        return warnings

    def export_payload(self, scope):
        return {
            "summary": self.summary(scope),
            "validations": self.validations(scope),
        }

    def _resolve_date_window(self, scope):
        if scope.entityfinid_id:
            fy = EntityFinancialYear.objects.filter(id=scope.entityfinid_id, entity_id=scope.entity_id).first()
        else:
            fy = (
                EntityFinancialYear.objects.filter(entity_id=scope.entity_id, isactive=True)
                .order_by("-finstartyear")
                .first()
            )
        if not fy:
            raise DRFValidationError({"entityfinid": ["No active financial year found for the selected entity."]})
        return ensure_date(fy.finstartyear), ensure_date(fy.finendyear), fy.id

    def _sales_qs(self, scope):
        from_date, to_date, effective_entityfinid_id = self._resolve_date_window(scope)
        qs = SalesInvoiceHeader.objects.filter(
            entity_id=scope.entity_id,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date__gte=from_date,
            bill_date__lte=to_date,
        )
        if scope.subentity_id:
            qs = qs.filter(subentity_id=scope.subentity_id)
        qs = qs.filter(entityfinid_id=effective_entityfinid_id)
        return qs

    def _purchase_qs(self, scope):
        from_date, to_date, effective_entityfinid_id = self._resolve_date_window(scope)
        qs = PurchaseInvoiceHeader.objects.filter(
            entity_id=scope.entity_id,
            status=PurchaseInvoiceHeader.Status.POSTED,
            bill_date__gte=from_date,
            bill_date__lte=to_date,
        )
        if scope.subentity_id:
            qs = qs.filter(subentity_id=scope.subentity_id)
        qs = qs.filter(entityfinid_id=effective_entityfinid_id)
        return qs

    def _sales_tax_summary_qs(self, scope):
        sales_qs = self._sales_qs(scope)
        return SalesTaxSummary.objects.filter(header__in=sales_qs)

    def _signed_sum_bucket(self, queryset):
        sign = Case(
            When(doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE, then=Value(Decimal("-1.00"))),
            default=Value(Decimal("1.00")),
            output_field=DecimalField(max_digits=5, decimal_places=2),
        )
        agg = queryset.aggregate(
            taxable_value=Coalesce(Sum(ExpressionWrapper(F("total_taxable_value") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            cgst=Coalesce(Sum(ExpressionWrapper(F("total_cgst") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            sgst=Coalesce(Sum(ExpressionWrapper(F("total_sgst") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            igst=Coalesce(Sum(ExpressionWrapper(F("total_igst") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            cess=Coalesce(Sum(ExpressionWrapper(F("total_cess") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
        )
        total_tax = (agg["cgst"] or ZERO) + (agg["sgst"] or ZERO) + (agg["igst"] or ZERO) + (agg["cess"] or ZERO)
        return {
            "taxable_value": self._q(agg["taxable_value"] or ZERO),
            "cgst": self._q(agg["cgst"] or ZERO),
            "sgst": self._q(agg["sgst"] or ZERO),
            "igst": self._q(agg["igst"] or ZERO),
            "cess": self._q(agg["cess"] or ZERO),
            "total_tax": self._q(total_tax),
        }

    def _signed_sum_bucket_purchase(self, queryset):
        sign = Case(
            When(doc_type=PurchaseInvoiceHeader.DocType.CREDIT_NOTE, then=Value(Decimal("-1.00"))),
            default=Value(Decimal("1.00")),
            output_field=DecimalField(max_digits=5, decimal_places=2),
        )
        agg = queryset.aggregate(
            taxable_value=Coalesce(Sum(ExpressionWrapper(F("total_taxable") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            cgst=Coalesce(Sum(ExpressionWrapper(F("total_cgst") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            sgst=Coalesce(Sum(ExpressionWrapper(F("total_sgst") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            igst=Coalesce(Sum(ExpressionWrapper(F("total_igst") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            cess=Coalesce(Sum(ExpressionWrapper(F("total_cess") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
        )
        total_tax = (agg["cgst"] or ZERO) + (agg["sgst"] or ZERO) + (agg["igst"] or ZERO) + (agg["cess"] or ZERO)
        return {
            "taxable_value": self._q(agg["taxable_value"] or ZERO),
            "cgst": self._q(agg["cgst"] or ZERO),
            "sgst": self._q(agg["sgst"] or ZERO),
            "igst": self._q(agg["igst"] or ZERO),
            "cess": self._q(agg["cess"] or ZERO),
            "total_tax": self._q(total_tax),
        }

    def _add_bucket(self, left: dict, right: dict):
        return {
            "taxable_value": self._q((left.get("taxable_value") or ZERO) + (right.get("taxable_value") or ZERO)),
            "cgst": self._q((left.get("cgst") or ZERO) + (right.get("cgst") or ZERO)),
            "sgst": self._q((left.get("sgst") or ZERO) + (right.get("sgst") or ZERO)),
            "igst": self._q((left.get("igst") or ZERO) + (right.get("igst") or ZERO)),
            "cess": self._q((left.get("cess") or ZERO) + (right.get("cess") or ZERO)),
            "total_tax": self._q((left.get("total_tax") or ZERO) + (right.get("total_tax") or ZERO)),
        }

    def _row(self, line_no: str, particulars: str, bucket: dict):
        return {
            "line_no": line_no,
            "particulars": particulars,
            "taxable_value": self._q(bucket.get("taxable_value") or ZERO),
            "cgst": self._q(bucket.get("cgst") or ZERO),
            "sgst": self._q(bucket.get("sgst") or ZERO),
            "igst": self._q(bucket.get("igst") or ZERO),
            "cess": self._q(bucket.get("cess") or ZERO),
            "total_tax": self._q(bucket.get("total_tax") or ZERO),
        }

    def _build_table_4(self, scope, definition):
        sales_qs = self._sales_qs(scope).exclude(
            taxability__in=[
                SalesInvoiceHeader.Taxability.EXEMPT,
                SalesInvoiceHeader.Taxability.NIL_RATED,
                SalesInvoiceHeader.Taxability.NON_GST,
            ]
        )
        domestic_invoices = self._signed_sum_bucket(
            sales_qs.filter(
                doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
                supply_category__in=[
                    SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                    SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
                ],
            )
        )
        export_or_sez_with_tax = self._signed_sum_bucket(
            sales_qs.filter(
                doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
                supply_category__in=[
                    SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
                    SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
                    SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
                ],
            )
        )
        debit_notes = self._signed_sum_bucket(
            sales_qs.filter(doc_type=SalesInvoiceHeader.DocType.DEBIT_NOTE)
        )
        credit_notes = self._signed_sum_bucket(
            sales_qs.filter(doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE)
        )
        total = self._add_bucket(
            self._add_bucket(domestic_invoices, export_or_sez_with_tax),
            self._add_bucket(debit_notes, credit_notes),
        )
        rows = [
            self._row("4A", "Domestic taxable supplies (B2B + B2C)", domestic_invoices),
            self._row("4B", "Exports/SEZ/Deemed exports with tax", export_or_sez_with_tax),
            self._row("4C", "Debit notes (tax impact)", debit_notes),
            self._row("4D", "Credit notes (tax impact)", credit_notes),
            self._row("4T", "Total tax payable supplies", total),
        ]
        return {
            "table_code": definition["code"],
            "table_label": definition["label"],
            "count": len(rows),
            "rows": rows,
            "coverage": {
                "status": "implemented",
                "message": "Table 4 is computed from posted sales documents for the financial year scope.",
            },
        }

    def _build_table_9(self, scope, definition):
        table_4 = self._build_table_4(scope, {"code": "TABLE_4", "label": "Supplies on Which Tax is Payable"})
        payable_row = table_4["rows"][-1]
        from_date, to_date, effective_entityfinid_id = self._resolve_date_window(scope)
        gstr3b_scope = Gstr3bSummaryService().build_scope(
            {
                "entity": scope.entity_id,
                "entityfinid": effective_entityfinid_id,
                "subentity": scope.subentity_id,
                "from_date": from_date,
                "to_date": to_date,
            }
        )
        gstr3b_summary = Gstr3bSummaryService().build(gstr3b_scope)
        paid_cash = gstr3b_summary["section_6_1"]["tax_paid_cash"]
        paid_itc = gstr3b_summary["section_6_1"]["tax_paid_itc"]
        paid_total = self._add_bucket(paid_cash, paid_itc)
        balance = {
            "taxable_value": ZERO,
            "cgst": self._q((payable_row.get("cgst") or ZERO) - (paid_total.get("cgst") or ZERO)),
            "sgst": self._q((payable_row.get("sgst") or ZERO) - (paid_total.get("sgst") or ZERO)),
            "igst": self._q((payable_row.get("igst") or ZERO) - (paid_total.get("igst") or ZERO)),
            "cess": self._q((payable_row.get("cess") or ZERO) - (paid_total.get("cess") or ZERO)),
            "total_tax": self._q((payable_row.get("total_tax") or ZERO) - (paid_total.get("total_tax") or ZERO)),
        }
        rows = [
            self._row(
                "9A",
                "Tax payable as per annual computation",
                {
                    "taxable_value": payable_row.get("taxable_value") or ZERO,
                    "cgst": payable_row.get("cgst") or ZERO,
                    "sgst": payable_row.get("sgst") or ZERO,
                    "igst": payable_row.get("igst") or ZERO,
                    "cess": payable_row.get("cess") or ZERO,
                    "total_tax": payable_row.get("total_tax") or ZERO,
                },
            ),
            self._row("9B", "Tax paid in cash (GSTR-3B aligned)", paid_cash),
            self._row("9C", "Tax paid through ITC (GSTR-3B aligned)", paid_itc),
            self._row("9D", "Balance tax payable/(excess paid)", balance),
        ]
        return {
            "table_code": definition["code"],
            "table_label": definition["label"],
            "count": len(rows),
            "rows": rows,
            "coverage": {
                "status": "implemented",
                "message": "Table 9 uses annual payable from Table 4 and paid tax from GSTR-3B Section 6.1.",
            },
        }

    def _build_table_5(self, scope, definition):
        sales_qs = self._sales_qs(scope)
        exempt_nil_non_gst = self._signed_sum_bucket(
            sales_qs.filter(
                taxability__in=[
                    SalesInvoiceHeader.Taxability.EXEMPT,
                    SalesInvoiceHeader.Taxability.NIL_RATED,
                    SalesInvoiceHeader.Taxability.NON_GST,
                ]
            )
        )
        exports_without_tax = self._signed_sum_bucket(
            sales_qs.filter(
                doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
                supply_category__in=[
                    SalesInvoiceHeader.SupplyCategory.EXPORT_WITHOUT_IGST,
                    SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
                ],
            )
        )
        credit_notes_non_taxable = self._signed_sum_bucket(
            sales_qs.filter(
                doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
                taxability__in=[
                    SalesInvoiceHeader.Taxability.EXEMPT,
                    SalesInvoiceHeader.Taxability.NIL_RATED,
                    SalesInvoiceHeader.Taxability.NON_GST,
                ],
            )
        )
        total = self._add_bucket(self._add_bucket(exempt_nil_non_gst, exports_without_tax), credit_notes_non_taxable)
        rows = [
            self._row("5A", "Exempt/Nil-rated/Non-GST outward supplies", exempt_nil_non_gst),
            self._row("5B", "Exports/SEZ without payment of tax", exports_without_tax),
            self._row("5C", "Credit notes against non-tax payable supplies", credit_notes_non_taxable),
            self._row("5T", "Total supplies on which tax is not payable", total),
        ]
        return {
            "table_code": definition["code"],
            "table_label": definition["label"],
            "count": len(rows),
            "rows": rows,
            "coverage": {
                "status": "implemented",
                "message": "Table 5 is computed from posted sales documents with non-taxable classifications.",
            },
        }

    def _build_table_6(self, scope, definition):
        purchase_qs = self._purchase_qs(scope).filter(default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE, is_itc_eligible=True)
        eligible_non_rcm = self._signed_sum_bucket_purchase(purchase_qs.filter(is_reverse_charge=False))
        eligible_rcm = self._signed_sum_bucket_purchase(purchase_qs.filter(is_reverse_charge=True))
        total = self._add_bucket(eligible_non_rcm, eligible_rcm)
        rows = [
            self._row("6A", "ITC availed on eligible inward supplies (other than RCM)", eligible_non_rcm),
            self._row("6B", "ITC availed on inward supplies liable to RCM", eligible_rcm),
            self._row("6T", "Total ITC availed", total),
        ]
        return {
            "table_code": definition["code"],
            "table_label": definition["label"],
            "count": len(rows),
            "rows": rows,
            "coverage": {
                "status": "implemented",
                "message": "Table 6 is computed from posted purchase documents and ITC eligibility flags.",
            },
        }

    def _build_table_7(self, scope, definition):
        purchase_qs = self._purchase_qs(scope).filter(default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE, is_itc_eligible=False)
        reversed_or_ineligible = self._signed_sum_bucket_purchase(purchase_qs)
        rows = [
            self._row("7A", "ITC reversed/ineligible from purchase documents", reversed_or_ineligible),
            self._row("7T", "Total ITC reversed/ineligible", reversed_or_ineligible),
        ]
        return {
            "table_code": definition["code"],
            "table_label": definition["label"],
            "count": len(rows),
            "rows": rows,
            "coverage": {
                "status": "implemented",
                "message": "Table 7 is computed from posted purchase documents marked as ineligible ITC.",
            },
        }

    def _build_table_8(self, scope, definition):
        purchase_qs = self._purchase_qs(scope).filter(default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE, is_itc_eligible=True)
        books_itc = self._signed_sum_bucket_purchase(purchase_qs)
        matched_itc = self._signed_sum_bucket_purchase(
            purchase_qs.filter(gstr2b_match_status=PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED)
        )
        pending_recon = {
            "taxable_value": self._q((books_itc.get("taxable_value") or ZERO) - (matched_itc.get("taxable_value") or ZERO)),
            "cgst": self._q((books_itc.get("cgst") or ZERO) - (matched_itc.get("cgst") or ZERO)),
            "sgst": self._q((books_itc.get("sgst") or ZERO) - (matched_itc.get("sgst") or ZERO)),
            "igst": self._q((books_itc.get("igst") or ZERO) - (matched_itc.get("igst") or ZERO)),
            "cess": self._q((books_itc.get("cess") or ZERO) - (matched_itc.get("cess") or ZERO)),
            "total_tax": self._q((books_itc.get("total_tax") or ZERO) - (matched_itc.get("total_tax") or ZERO)),
        }
        rows = [
            self._row("8A", "ITC as per books (eligible taxable purchases)", books_itc),
            self._row("8B", "ITC matched with GSTR-2B", matched_itc),
            self._row("8C", "ITC pending reconciliation", pending_recon),
        ]
        return {
            "table_code": definition["code"],
            "table_label": definition["label"],
            "count": len(rows),
            "rows": rows,
            "coverage": {
                "status": "implemented",
                "message": "Table 8 compares books ITC with purchase invoices marked as 2B matched.",
            },
        }

    def _build_table_10_14(self, scope, definition):
        sales_qs = self._sales_qs(scope).exclude(
            taxability__in=[
                SalesInvoiceHeader.Taxability.EXEMPT,
                SalesInvoiceHeader.Taxability.NIL_RATED,
                SalesInvoiceHeader.Taxability.NON_GST,
            ]
        )
        credit_notes_linked = self._signed_sum_bucket(
            sales_qs.filter(
                doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
                original_invoice__isnull=False,
            )
        )
        debit_notes_linked = self._signed_sum_bucket(
            sales_qs.filter(
                doc_type=SalesInvoiceHeader.DocType.DEBIT_NOTE,
                original_invoice__isnull=False,
            )
        )
        linked_net = self._add_bucket(credit_notes_linked, debit_notes_linked)
        notes_unlinked = self._signed_sum_bucket(
            sales_qs.filter(
                doc_type__in=[
                    SalesInvoiceHeader.DocType.CREDIT_NOTE,
                    SalesInvoiceHeader.DocType.DEBIT_NOTE,
                ],
                original_invoice__isnull=True,
            )
        )
        rows = [
            self._row("10A", "Credit notes linked to original invoice", credit_notes_linked),
            self._row("11A", "Debit notes linked to original invoice", debit_notes_linked),
            self._row("12A", "Net amendment impact (linked notes)", linked_net),
            self._row("14A", "Notes without original invoice linkage", notes_unlinked),
        ]
        return {
            "table_code": definition["code"],
            "table_label": definition["label"],
            "count": len(rows),
            "rows": rows,
            "coverage": {
                "status": "implemented",
                "message": "Table 10-14 aggregates amendment impact from linked credit/debit notes.",
            },
        }

    def _build_table_15_19(self, scope, definition):
        table_9 = self._build_table_9(scope, {"code": "TABLE_9", "label": "Tax Paid and Payable"})
        tax_summary_qs = self._sales_tax_summary_qs(scope).filter(
            taxability=SalesInvoiceHeader.Taxability.TAXABLE
        )
        hsn_goods = self._signed_sum_bucket_tax_summary(tax_summary_qs.filter(is_service=False))
        hsn_services = self._signed_sum_bucket_tax_summary(tax_summary_qs.filter(is_service=True))
        hsn_missing = self._signed_sum_bucket_tax_summary(tax_summary_qs.filter(hsn_sac_code__in=["", None]))
        paid_total = self._add_bucket(
            {
                "taxable_value": ZERO,
                "cgst": table_9["rows"][1]["cgst"],
                "sgst": table_9["rows"][1]["sgst"],
                "igst": table_9["rows"][1]["igst"],
                "cess": table_9["rows"][1]["cess"],
                "total_tax": table_9["rows"][1]["total_tax"],
            },
            {
                "taxable_value": ZERO,
                "cgst": table_9["rows"][2]["cgst"],
                "sgst": table_9["rows"][2]["sgst"],
                "igst": table_9["rows"][2]["igst"],
                "cess": table_9["rows"][2]["cess"],
                "total_tax": table_9["rows"][2]["total_tax"],
            },
        )
        refunds = {"taxable_value": ZERO, "cgst": ZERO, "sgst": ZERO, "igst": ZERO, "cess": ZERO, "total_tax": ZERO}
        interest_and_late_fee = {"taxable_value": ZERO, "cgst": ZERO, "sgst": ZERO, "igst": ZERO, "cess": ZERO, "total_tax": ZERO}
        rows = [
            self._row("15A", "Taxes paid during the year", paid_total),
            self._row("15B", "Refund claimed (placeholder until refund ledger integration)", refunds),
            self._row("16A", "HSN summary - goods", hsn_goods),
            self._row("17A", "HSN summary - services", hsn_services),
            self._row("18A", "Interest/late fee payable (placeholder)", interest_and_late_fee),
            self._row("19A", "Interest/late fee paid (placeholder)", interest_and_late_fee),
            self._row("19B", "Taxable supplies with missing HSN/SAC", hsn_missing),
        ]
        return {
            "table_code": definition["code"],
            "table_label": definition["label"],
            "count": len(rows),
            "rows": rows,
            "coverage": {
                "status": "implemented",
                "message": "Table 15-19 includes taxes paid and HSN summary; refund/interest rows are placeholders pending dedicated source integration.",
            },
        }

    def _signed_sum_bucket_tax_summary(self, queryset):
        sign = Case(
            When(header__doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE, then=Value(Decimal("-1.00"))),
            default=Value(Decimal("1.00")),
            output_field=DecimalField(max_digits=5, decimal_places=2),
        )
        agg = queryset.aggregate(
            taxable_value=Coalesce(Sum(ExpressionWrapper(F("taxable_value") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            cgst=Coalesce(Sum(ExpressionWrapper(F("cgst_amount") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            sgst=Coalesce(Sum(ExpressionWrapper(F("sgst_amount") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            igst=Coalesce(Sum(ExpressionWrapper(F("igst_amount") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
            cess=Coalesce(Sum(ExpressionWrapper(F("cess_amount") * sign, output_field=SIGNED_OUTPUT), output_field=SUM_OUTPUT), Value(ZERO)),
        )
        total_tax = (agg["cgst"] or ZERO) + (agg["sgst"] or ZERO) + (agg["igst"] or ZERO) + (agg["cess"] or ZERO)
        return {
            "taxable_value": self._q(agg["taxable_value"] or ZERO),
            "cgst": self._q(agg["cgst"] or ZERO),
            "sgst": self._q(agg["sgst"] or ZERO),
            "igst": self._q(agg["igst"] or ZERO),
            "cess": self._q(agg["cess"] or ZERO),
            "total_tax": self._q(total_tax),
        }

    def _q(self, value):
        return Decimal(value or ZERO).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
