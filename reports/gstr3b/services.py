from __future__ import annotations

from decimal import Decimal

from django.db.models import Case, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce

from posting.common.static_accounts import StaticAccountCodes
from posting.models import EntryStatus, EntityStaticAccountMap, JournalLine, TxnType
from purchase.models import PurchaseInvoiceHeader
from sales.models import SalesInvoiceHeader

from reports.gstr3b.selectors import Gstr3bScope, parse_scope_params

ZERO = Decimal("0.00")
SIGNED_OUTPUT = DecimalField(max_digits=24, decimal_places=2)
SUM_OUTPUT = DecimalField(max_digits=24, decimal_places=2)


def _sum_dict(qs, fields: list[str]) -> dict[str, Decimal]:
    sign = Case(
        When(doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE, then=Value(Decimal("-1.00"))),
        default=Value(Decimal("1.00")),
        output_field=DecimalField(max_digits=5, decimal_places=2),
    )
    aggregates = {}
    for field in fields:
        signed_expr = ExpressionWrapper(F(field) * sign, output_field=SIGNED_OUTPUT)
        aggregates[field] = Coalesce(Sum(signed_expr, output_field=SUM_OUTPUT), Value(ZERO))
    return qs.aggregate(**aggregates)


def _bucket(row: dict[str, Decimal]) -> dict:
    cgst = row.get("cgst", ZERO) or ZERO
    sgst = row.get("sgst", ZERO) or ZERO
    igst = row.get("igst", ZERO) or ZERO
    cess = row.get("cess", ZERO) or ZERO
    return {
        "taxable_value": row.get("taxable", ZERO) or ZERO,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "cess": cess,
        "total_tax": cgst + sgst + igst + cess,
    }


def _add(a: dict, b: dict) -> dict:
    return {
        "taxable_value": (a.get("taxable_value") or ZERO) + (b.get("taxable_value") or ZERO),
        "cgst": (a.get("cgst") or ZERO) + (b.get("cgst") or ZERO),
        "sgst": (a.get("sgst") or ZERO) + (b.get("sgst") or ZERO),
        "igst": (a.get("igst") or ZERO) + (b.get("igst") or ZERO),
        "cess": (a.get("cess") or ZERO) + (b.get("cess") or ZERO),
        "total_tax": (a.get("total_tax") or ZERO) + (b.get("total_tax") or ZERO),
    }


def _sub(a: dict, b: dict) -> dict:
    taxable = (a.get("taxable_value") or ZERO) - (b.get("taxable_value") or ZERO)
    cgst = (a.get("cgst") or ZERO) - (b.get("cgst") or ZERO)
    sgst = (a.get("sgst") or ZERO) - (b.get("sgst") or ZERO)
    igst = (a.get("igst") or ZERO) - (b.get("igst") or ZERO)
    cess = (a.get("cess") or ZERO) - (b.get("cess") or ZERO)
    return {
        "taxable_value": taxable,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "cess": cess,
        "total_tax": cgst + sgst + igst + cess,
    }


def _resolve_output_tax_maps(scope: Gstr3bScope) -> tuple[dict[str, set[int]], dict[str, set[int]]]:
    code_to_ledgers = {
        StaticAccountCodes.OUTPUT_CGST: set(),
        StaticAccountCodes.OUTPUT_SGST: set(),
        StaticAccountCodes.OUTPUT_IGST: set(),
        StaticAccountCodes.OUTPUT_CESS: set(),
    }
    code_to_accounts = {
        StaticAccountCodes.OUTPUT_CGST: set(),
        StaticAccountCodes.OUTPUT_SGST: set(),
        StaticAccountCodes.OUTPUT_IGST: set(),
        StaticAccountCodes.OUTPUT_CESS: set(),
    }
    rows = list(
        EntityStaticAccountMap.objects.filter(
            entity_id=scope.entity_id,
            is_active=True,
            static_account__is_active=True,
            static_account__code__in=list(code_to_ledgers.keys()),
        ).values("static_account__code", "sub_entity_id", "ledger_id", "account_id")
    )
    for code in code_to_ledgers.keys():
        scoped_rows = [row for row in rows if row["static_account__code"] == code]
        if not scoped_rows:
            continue
        chosen = [row for row in scoped_rows if row["sub_entity_id"] == scope.subentity_id] if scope.subentity_id else []
        if not chosen:
            chosen = [row for row in scoped_rows if row["sub_entity_id"] is None]
        for row in chosen:
            if row.get("ledger_id"):
                code_to_ledgers[code].add(int(row["ledger_id"]))
            if row.get("account_id"):
                code_to_accounts[code].add(int(row["account_id"]))
    return code_to_ledgers, code_to_accounts


def _sum_cash_tax_paid(scope: Gstr3bScope) -> tuple[dict, bool]:
    code_to_ledgers, code_to_accounts = _resolve_output_tax_maps(scope)
    any_mapping = any(code_to_ledgers[code] or code_to_accounts[code] for code in code_to_ledgers.keys())
    if not any_mapping:
        return _bucket({"taxable": ZERO, "cgst": ZERO, "sgst": ZERO, "igst": ZERO, "cess": ZERO}), False

    jl_qs = JournalLine.objects.filter(
        entity_id=scope.entity_id,
        entry__status=EntryStatus.POSTED,
        posting_date__gte=scope.from_date,
        posting_date__lte=scope.to_date,
        txn_type__in=[TxnType.JOURNAL_CASH, TxnType.JOURNAL_BANK, TxnType.PAYMENT],
        drcr=True,
    )
    if scope.entityfinid_id:
        jl_qs = jl_qs.filter(entityfin_id=scope.entityfinid_id)
    if scope.subentity_id:
        jl_qs = jl_qs.filter(subentity_id=scope.subentity_id)

    def _sum_for(code):
        q = Q()
        if code_to_ledgers[code]:
            q |= Q(ledger_id__in=list(code_to_ledgers[code]))
        if code_to_accounts[code]:
            q |= Q(account_id__in=list(code_to_accounts[code]))
        if not q:
            return ZERO
        return jl_qs.filter(q).aggregate(total=Coalesce(Sum("amount"), Value(ZERO)))["total"] or ZERO

    return (
        _bucket(
            {
                "taxable": ZERO,
                "cgst": _sum_for(StaticAccountCodes.OUTPUT_CGST),
                "sgst": _sum_for(StaticAccountCodes.OUTPUT_SGST),
                "igst": _sum_for(StaticAccountCodes.OUTPUT_IGST),
                "cess": _sum_for(StaticAccountCodes.OUTPUT_CESS),
            }
        ),
        True,
    )


def _max_zero_tax_bucket(row: dict) -> dict:
    cgst = max(row.get("cgst") or ZERO, ZERO)
    sgst = max(row.get("sgst") or ZERO, ZERO)
    igst = max(row.get("igst") or ZERO, ZERO)
    cess = max(row.get("cess") or ZERO, ZERO)
    return {
        "taxable_value": max(row.get("taxable_value") or ZERO, ZERO),
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "cess": cess,
        "total_tax": cgst + sgst + igst + cess,
    }


def _named_bucket(label: str, row: dict | None) -> dict:
    source = row or {}
    return {
        "label": label,
        "taxable_value": source.get("taxable_value", ZERO) or ZERO,
        "cgst": source.get("cgst", ZERO) or ZERO,
        "sgst": source.get("sgst", ZERO) or ZERO,
        "igst": source.get("igst", ZERO) or ZERO,
        "cess": source.get("cess", ZERO) or ZERO,
        "total_tax": source.get("total_tax", ZERO) or ZERO,
    }


def _named_taxable(label: str, taxable_value: Decimal | None) -> dict:
    return {
        "label": label,
        "taxable_value": taxable_value or ZERO,
    }


class Gstr3bSummaryService:
    ZERO_RATED_SUPPLY_CATEGORIES = (
        SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
        SalesInvoiceHeader.SupplyCategory.EXPORT_WITHOUT_IGST,
        SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
        SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
        SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
    )
    NIL_EXEMPT_TAXABILITIES = (
        SalesInvoiceHeader.Taxability.EXEMPT,
        SalesInvoiceHeader.Taxability.NIL_RATED,
        SalesInvoiceHeader.Taxability.NON_GST,
    )

    def build_scope(self, params) -> Gstr3bScope:
        return parse_scope_params(params)

    def _sales_qs(self, scope: Gstr3bScope):
        qs = SalesInvoiceHeader.objects.filter(
            entity_id=scope.entity_id,
            bill_date__gte=scope.from_date,
            bill_date__lte=scope.to_date,
            status=SalesInvoiceHeader.Status.POSTED,
        )
        if scope.entityfinid_id:
            qs = qs.filter(entityfinid_id=scope.entityfinid_id)
        if scope.subentity_id:
            qs = qs.filter(subentity_id=scope.subentity_id)
        return qs

    def _purchase_qs(self, scope: Gstr3bScope):
        qs = PurchaseInvoiceHeader.objects.filter(
            entity_id=scope.entity_id,
            bill_date__gte=scope.from_date,
            bill_date__lte=scope.to_date,
            status=PurchaseInvoiceHeader.Status.POSTED,
        )
        if scope.entityfinid_id:
            qs = qs.filter(entityfinid_id=scope.entityfinid_id)
        if scope.subentity_id:
            qs = qs.filter(subentity_id=scope.subentity_id)
        return qs

    def build(self, scope: Gstr3bScope) -> dict:
        sales_qs = self._sales_qs(scope)
        purchase_qs = self._purchase_qs(scope)
        interstate_taxable_qs = (
            sales_qs.filter(tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE)
            .exclude(taxability__in=self.NIL_EXEMPT_TAXABILITIES)
            .exclude(supply_category__in=self.ZERO_RATED_SUPPLY_CATEGORIES)
        )
        composition_condition = Q(customer__compliance_profile__gstregtype__iexact="Composition")
        uin_condition = Q(customer__compliance_profile__gstregtype__iexact="UIN")
        unregistered_condition = (
            Q(customer_gstin__in=["", None])
            | Q(customer__compliance_profile__gstregtype__iexact="Unregistered")
            | Q(customer__compliance_profile__gstregtype__iexact="Consumer")
            | Q(supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C)
        )

        outward_taxable_row = _sum_dict(
            sales_qs.exclude(taxability__in=self.NIL_EXEMPT_TAXABILITIES).exclude(
                supply_category__in=self.ZERO_RATED_SUPPLY_CATEGORIES
            ),
            ["total_taxable_value", "total_cgst", "total_sgst", "total_igst", "total_cess"],
        )
        outward_zero_rated_row = _sum_dict(
            sales_qs.exclude(taxability__in=self.NIL_EXEMPT_TAXABILITIES).filter(
                supply_category__in=self.ZERO_RATED_SUPPLY_CATEGORIES
            ),
            ["total_taxable_value", "total_cgst", "total_sgst", "total_igst", "total_cess"],
        )
        outward_nil_row = _sum_dict(
            sales_qs.filter(taxability__in=self.NIL_EXEMPT_TAXABILITIES),
            ["total_taxable_value"],
        )
        non_gst_outward_row = _sum_dict(
            sales_qs.filter(taxability=SalesInvoiceHeader.Taxability.NON_GST),
            ["total_taxable_value"],
        )

        inward_reverse_charge_row = _sum_dict(
            purchase_qs.filter(is_reverse_charge=True),
            ["total_taxable", "total_cgst", "total_sgst", "total_igst", "total_cess"],
        )
        itc_available_row = _sum_dict(
            purchase_qs.filter(is_itc_eligible=True, default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE),
            ["total_taxable", "total_cgst", "total_sgst", "total_igst", "total_cess"],
        )
        itc_reversed_row = _sum_dict(
            purchase_qs.filter(is_itc_eligible=False, default_taxability=PurchaseInvoiceHeader.Taxability.TAXABLE),
            ["total_taxable", "total_cgst", "total_sgst", "total_igst", "total_cess"],
        )
        inward_exempt_row = _sum_dict(
            purchase_qs.filter(
                default_taxability__in=[
                    PurchaseInvoiceHeader.Taxability.EXEMPT,
                    PurchaseInvoiceHeader.Taxability.NIL_RATED,
                    PurchaseInvoiceHeader.Taxability.NON_GST,
                ]
            ),
            ["total_taxable"],
        )
        interstate_unregistered_row = _sum_dict(
            interstate_taxable_qs.filter(unregistered_condition).exclude(composition_condition | uin_condition),
            ["total_taxable_value", "total_cgst", "total_sgst", "total_igst", "total_cess"],
        )
        interstate_composition_row = _sum_dict(
            interstate_taxable_qs.filter(composition_condition),
            ["total_taxable_value", "total_cgst", "total_sgst", "total_igst", "total_cess"],
        )
        interstate_uin_row = _sum_dict(
            interstate_taxable_qs.filter(uin_condition),
            ["total_taxable_value", "total_cgst", "total_sgst", "total_igst", "total_cess"],
        )

        outward_taxable = _bucket(
            {
                "taxable": outward_taxable_row["total_taxable_value"],
                "cgst": outward_taxable_row["total_cgst"],
                "sgst": outward_taxable_row["total_sgst"],
                "igst": outward_taxable_row["total_igst"],
                "cess": outward_taxable_row["total_cess"],
            }
        )
        outward_zero_rated = _bucket(
            {
                "taxable": outward_zero_rated_row["total_taxable_value"],
                "cgst": outward_zero_rated_row["total_cgst"],
                "sgst": outward_zero_rated_row["total_sgst"],
                "igst": outward_zero_rated_row["total_igst"],
                "cess": outward_zero_rated_row["total_cess"],
            }
        )
        inward_reverse_charge = _bucket(
            {
                "taxable": inward_reverse_charge_row["total_taxable"],
                "cgst": inward_reverse_charge_row["total_cgst"],
                "sgst": inward_reverse_charge_row["total_sgst"],
                "igst": inward_reverse_charge_row["total_igst"],
                "cess": inward_reverse_charge_row["total_cess"],
            }
        )
        itc_available = _bucket(
            {
                "taxable": itc_available_row["total_taxable"],
                "cgst": itc_available_row["total_cgst"],
                "sgst": itc_available_row["total_sgst"],
                "igst": itc_available_row["total_igst"],
                "cess": itc_available_row["total_cess"],
            }
        )
        itc_reversed = _bucket(
            {
                "taxable": itc_reversed_row["total_taxable"],
                "cgst": itc_reversed_row["total_cgst"],
                "sgst": itc_reversed_row["total_sgst"],
                "igst": itc_reversed_row["total_igst"],
                "cess": itc_reversed_row["total_cess"],
            }
        )
        net_itc = _sub(itc_available, itc_reversed)

        tax_payable = _add(_add(outward_taxable, outward_zero_rated), inward_reverse_charge)
        cash_tax_paid, _ = _sum_cash_tax_paid(scope)
        net_cash_tax_payable = _max_zero_tax_bucket(_sub(_sub(tax_payable, net_itc), cash_tax_paid))
        section_32_unregistered = _bucket(
            {
                "taxable": interstate_unregistered_row["total_taxable_value"],
                "cgst": interstate_unregistered_row["total_cgst"],
                "sgst": interstate_unregistered_row["total_sgst"],
                "igst": interstate_unregistered_row["total_igst"],
                "cess": interstate_unregistered_row["total_cess"],
            }
        )
        section_32_composition = _bucket(
            {
                "taxable": interstate_composition_row["total_taxable_value"],
                "cgst": interstate_composition_row["total_cgst"],
                "sgst": interstate_composition_row["total_sgst"],
                "igst": interstate_composition_row["total_igst"],
                "cess": interstate_composition_row["total_cess"],
            }
        )
        section_32_uin = _bucket(
            {
                "taxable": interstate_uin_row["total_taxable_value"],
                "cgst": interstate_uin_row["total_cgst"],
                "sgst": interstate_uin_row["total_sgst"],
                "igst": interstate_uin_row["total_igst"],
                "cess": interstate_uin_row["total_cess"],
            }
        )
        return {
            "section_3_1": {
                "outward_taxable_supplies": outward_taxable,
                "outward_zero_rated_supplies": outward_zero_rated,
                "outward_nil_exempt_non_gst": {
                    "taxable_value": outward_nil_row["total_taxable_value"] or ZERO,
                },
                "inward_supplies_reverse_charge": inward_reverse_charge,
                "non_gst_outward_supplies": {
                    "taxable_value": non_gst_outward_row["total_taxable_value"] or ZERO,
                },
                "rows": [
                    _named_bucket("Outward taxable supplies", outward_taxable),
                    _named_bucket("Outward zero-rated supplies", outward_zero_rated),
                    _named_bucket("Inward supplies liable to reverse charge", inward_reverse_charge),
                    _named_bucket(
                        "Outward nil/exempt/non-GST",
                        _bucket({"taxable": outward_nil_row["total_taxable_value"] or ZERO}),
                    ),
                    _named_bucket(
                        "Non-GST outward supplies",
                        _bucket({"taxable": non_gst_outward_row["total_taxable_value"] or ZERO}),
                    ),
                ],
            },
            "section_3_2": {
                "interstate_supplies_to_unregistered": section_32_unregistered,
                "interstate_supplies_to_composition": section_32_composition,
                "interstate_supplies_to_uin_holders": section_32_uin,
                "rows": [
                    _named_bucket("Inter-state to unregistered", section_32_unregistered),
                    _named_bucket("Inter-state to composition", section_32_composition),
                    _named_bucket("Inter-state to UIN holders", section_32_uin),
                ],
            },
            "section_4": {
                "itc_available": itc_available,
                "itc_reversed": itc_reversed,
                "net_itc": net_itc,
                "rows": [
                    _named_bucket("ITC available", itc_available),
                    _named_bucket("ITC reversed", itc_reversed),
                    _named_bucket("Net ITC", net_itc),
                ],
            },
            "section_5_1": {
                "inward_exempt_nil_non_gst": {
                    "taxable_value": inward_exempt_row["total_taxable"] or ZERO,
                },
                "rows": [
                    _named_taxable(
                        "Inward exempt / nil / non-GST",
                        inward_exempt_row["total_taxable"] or ZERO,
                    ),
                ],
            },
            "section_6_1": {
                "tax_payable": tax_payable,
                "tax_paid_cash": cash_tax_paid,
                "tax_paid_itc": net_itc,
                "balance_payable": net_cash_tax_payable,
                "rows": [
                    _named_bucket("Tax payable", tax_payable),
                    _named_bucket("Paid through ITC", net_itc),
                    _named_bucket("Paid in cash", cash_tax_paid),
                    _named_bucket("Balance payable", net_cash_tax_payable),
                ],
            },
            "totals": {
                "tax_payable": tax_payable,
                "net_itc": net_itc,
                "net_cash_tax_payable": net_cash_tax_payable,
            },
        }

    def validations(self, scope: Gstr3bScope) -> list[dict]:
        sales_qs = self._sales_qs(scope)
        warnings: list[dict] = []
        missing_pos_count = sales_qs.filter(place_of_supply_state_code__in=["", None]).count()
        if missing_pos_count:
            warnings.append(
                {
                    "code": "GSTR3B_POS_MISSING",
                    "severity": "warning",
                    "message": f"{missing_pos_count} posted sales invoices have missing place of supply.",
                }
            )
        missing_tax_count = sales_qs.filter(
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            total_taxable_value__gt=0,
            total_cgst=0,
            total_sgst=0,
            total_igst=0,
        ).count()
        if missing_tax_count:
            warnings.append(
                {
                    "code": "GSTR3B_TAX_BREAKUP_MISSING",
                    "severity": "warning",
                    "message": f"{missing_tax_count} taxable posted sales invoices have zero GST breakup.",
                }
            )
        _, has_cash_tax_source = _sum_cash_tax_paid(scope)
        if sales_qs.exists() and not has_cash_tax_source:
            warnings.append(
                {
                    "code": "GSTR3B_CASH_TAX_SOURCE_PENDING",
                    "severity": "info",
                    "message": "Section 6.1 tax_paid_cash is provisional (0.00) because output GST static account mappings are missing.",
                }
            )
        return warnings
