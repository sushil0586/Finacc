from __future__ import annotations

from decimal import Decimal

from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    DecimalField,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from geography.models import State
from reports.filters.gstr1_filter import Gstr1Filter
from sales.models import SalesInvoiceHeader

ZERO = Decimal("0.00")


class Gstr1Service:
    """
    GSTR-1 register service.

    Header-first (SalesInvoiceHeader) to avoid row explosion from line joins.
    """

    default_statuses = (
        SalesInvoiceHeader.Status.CONFIRMED,
        SalesInvoiceHeader.Status.POSTED,
    )

    def get_base_queryset(self):
        return SalesInvoiceHeader.objects.select_related(
            "customer",
            "customer_ledger",
            "original_invoice",
            "entity",
            "entityfinid",
            "subentity",
        )

    def apply_filters(self, queryset, params):
        filterset = Gstr1Filter(data=params, queryset=queryset)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)

        cleaned = filterset.form.cleaned_data
        self._validate_date_range(cleaned)

        queryset = filterset.qs
        queryset = self.apply_default_status_rules(queryset, raw_params=params)
        return queryset, cleaned

    def apply_default_status_rules(self, queryset, *, raw_params):
        if raw_params.get("status") not in (None, ""):
            return queryset
        return queryset.filter(status__in=self.default_statuses)

    def annotate_register_fields(self, queryset):
        place_of_supply_name = (
            State.objects.filter(statecode=OuterRef("place_of_supply_state_code"))
            .values("statename")[:1]
        )

        sign_multiplier = Case(
            When(status=SalesInvoiceHeader.Status.CANCELLED, then=Value(Decimal("0"))),
            When(doc_type__in=self._negative_doc_type_values(), then=Value(Decimal("-1"))),
            default=Value(Decimal("1")),
            output_field=DecimalField(max_digits=4, decimal_places=0),
        )
        affects_totals = Case(
            When(status=SalesInvoiceHeader.Status.CANCELLED, then=Value(False)),
            default=Value(True),
            output_field=BooleanField(),
        )

        section_label = Case(
            When(
                supply_category__in=[
                    SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
                    SalesInvoiceHeader.SupplyCategory.EXPORT_WITHOUT_IGST,
                ],
                then=Value("EXPORT"),
            ),
            When(
                supply_category__in=[
                    SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
                    SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
                ],
                then=Value("SEZ"),
            ),
            When(
                supply_category=SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
                then=Value("DEEMED_EXPORT"),
            ),
            When(
                Q(customer_gstin__isnull=False) & ~Q(customer_gstin=""),
                then=Value("B2B"),
            ),
            default=Value("B2C"),
            output_field=CharField(),
        )

        return queryset.annotate(
            invoice_date=F("bill_date"),
            posting_date=F("posting_date"),
            doc_type_name=Case(
                *[
                    When(doc_type=choice.value, then=Value(str(choice.label)))
                    for choice in SalesInvoiceHeader.DocType
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            supply_category_name=Case(
                *[
                    When(supply_category=choice.value, then=Value(str(choice.label)))
                    for choice in SalesInvoiceHeader.SupplyCategory
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            taxability_name=Case(
                *[
                    When(taxability=choice.value, then=Value(str(choice.label)))
                    for choice in SalesInvoiceHeader.Taxability
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            tax_regime_name=Case(
                *[
                    When(tax_regime=choice.value, then=Value(str(choice.label)))
                    for choice in SalesInvoiceHeader.TaxRegime
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            status_name=Case(
                *[
                    When(status=choice.value, then=Value(str(choice.label)))
                    for choice in SalesInvoiceHeader.Status
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            place_of_supply=Coalesce(
                Subquery(place_of_supply_name, output_field=CharField()),
                F("place_of_supply_state_code"),
                Value(""),
                output_field=CharField(),
            ),
            section=section_label,
            affects_totals=affects_totals,
            taxable_amount=F("total_taxable_value") * sign_multiplier,
            cgst_amount=F("total_cgst") * sign_multiplier,
            sgst_amount=F("total_sgst") * sign_multiplier,
            igst_amount=F("total_igst") * sign_multiplier,
            cess_amount=F("total_cess") * sign_multiplier,
            signed_grand_total=F("grand_total") * sign_multiplier,
        )

    def calculate_totals(self, queryset):
        raw_totals = queryset.aggregate(
            document_count=Count("id"),
            taxable_amount_total=Coalesce(Sum("taxable_amount"), ZERO),
            cgst_amount_total=Coalesce(Sum("cgst_amount"), ZERO),
            sgst_amount_total=Coalesce(Sum("sgst_amount"), ZERO),
            igst_amount_total=Coalesce(Sum("igst_amount"), ZERO),
            cess_amount_total=Coalesce(Sum("cess_amount"), ZERO),
            grand_total_total=Coalesce(Sum("signed_grand_total"), ZERO),
        )
        return {
            "document_count": raw_totals["document_count"],
            "taxable_amount": raw_totals["taxable_amount_total"],
            "cgst_amount": raw_totals["cgst_amount_total"],
            "sgst_amount": raw_totals["sgst_amount_total"],
            "igst_amount": raw_totals["igst_amount_total"],
            "cess_amount": raw_totals["cess_amount_total"],
            "grand_total": raw_totals["grand_total_total"],
        }

    def summarize_by_section(self, queryset):
        return list(
            queryset.values("section")
            .annotate(
                document_count=Count("id"),
                taxable_amount=Coalesce(Sum("taxable_amount"), ZERO),
                cgst_amount=Coalesce(Sum("cgst_amount"), ZERO),
                sgst_amount=Coalesce(Sum("sgst_amount"), ZERO),
                igst_amount=Coalesce(Sum("igst_amount"), ZERO),
                cess_amount=Coalesce(Sum("cess_amount"), ZERO),
                grand_total=Coalesce(Sum("signed_grand_total"), ZERO),
            )
            .order_by("section")
        )

    def build_drilldown(self, row):
        return {
            "target": "sales_invoice_detail",
            "id": row.id,
            "doc_type": row.doc_type,
            "invoice_number": row.invoice_number,
        }

    @staticmethod
    def _negative_doc_type_values():
        return [
            choice.value
            for choice in SalesInvoiceHeader.DocType
            if "CREDIT" in choice.name.upper()
            or "CREDIT" in str(choice.label).upper()
        ]

    @staticmethod
    def _validate_date_range(cleaned_data):
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")
        if from_date and to_date and from_date > to_date:
            raise ValidationError({"from_date": ["from_date cannot be after to_date."]})
