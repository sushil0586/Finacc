from __future__ import annotations

from django.db.models import DecimalField, Exists, OuterRef, Q, QuerySet, Value
from django.db.models.functions import Coalesce

from sales.models import SalesInvoiceHeader, SalesTaxSummary

from reports.gstr1.selectors.scope import Gstr1FilterParams
from reports.gstr1.selectors.smart_filters import Gstr1SmartFilters


def base_queryset() -> QuerySet:
    return SalesInvoiceHeader.objects.select_related(
        "customer",
        "customer_ledger",
        "original_invoice",
        "entity",
        "entityfinid",
        "subentity",
    )


def apply_scope_filters(queryset: QuerySet, scope: Gstr1FilterParams) -> QuerySet:
    queryset = queryset.filter(entity_id=scope.entity_id)
    if scope.entityfinid_id:
        queryset = queryset.filter(entityfinid_id=scope.entityfinid_id)
    if scope.subentity_id:
        queryset = queryset.filter(subentity_id=scope.subentity_id)
    if scope.from_date:
        queryset = queryset.filter(bill_date__gte=scope.from_date)
    if scope.to_date:
        queryset = queryset.filter(bill_date__lte=scope.to_date)
    if not scope.include_cancelled:
        queryset = queryset.exclude(status=SalesInvoiceHeader.Status.CANCELLED)
    return queryset


def apply_smart_filters(queryset: QuerySet, filters: Gstr1SmartFilters) -> QuerySet:
    if not filters or not filters.has_filters:
        return queryset

    if filters.search:
        query = filters.search
        queryset = queryset.filter(
            Q(invoice_number__icontains=query)
            | Q(doc_code__icontains=query)
            | Q(customer_name__icontains=query)
            | Q(customer_gstin__icontains=query)
            | Q(place_of_supply_state_code__icontains=query)
        )

    if filters.min_taxable_value is not None:
        queryset = queryset.filter(total_taxable_value__gte=filters.min_taxable_value)

    if filters.max_taxable_value is not None:
        queryset = queryset.filter(total_taxable_value__lte=filters.max_taxable_value)

    if filters.pos:
        queryset = queryset.filter(place_of_supply_state_code=filters.pos)

    if filters.doc_type_values:
        queryset = queryset.filter(doc_type__in=filters.doc_type_values)

    if filters.gstin_only:
        queryset = queryset.exclude(customer_gstin__in=[None, ""])

    if filters.taxability is not None:
        queryset = queryset.filter(taxability=filters.taxability)

    if filters.tax_regime is not None:
        queryset = queryset.filter(tax_regime=filters.tax_regime)

    if filters.supply_category is not None:
        queryset = queryset.filter(supply_category=filters.supply_category)

    if filters.status is not None:
        queryset = queryset.filter(status=filters.status)

    if filters.min_gst_rate is not None:
        matching_tax_summary = SalesTaxSummary.objects.filter(
            header_id=OuterRef("pk"),
            gst_rate__gte=filters.min_gst_rate,
        )
        queryset = queryset.annotate(
            has_matching_tax_rate=Exists(matching_tax_summary)
        ).filter(has_matching_tax_rate=True)

    return queryset
