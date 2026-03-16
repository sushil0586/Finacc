from __future__ import annotations

from django.db.models import QuerySet

from sales.models import SalesInvoiceHeader

from reports.gstr1.selectors.scope import Gstr1FilterParams


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
