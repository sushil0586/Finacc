from __future__ import annotations

import django_filters
from django.core.exceptions import ValidationError
from django.db.models import Q

from sales.models import SalesInvoiceHeader


class Gstr1Filter(django_filters.FilterSet):
    """
    Filter set for GSTR-1 register style reporting.

    Stays header-wise to keep the report one row per sales document.
    """

    from_date = django_filters.DateFilter(field_name="bill_date", lookup_expr="gte")
    to_date = django_filters.DateFilter(field_name="bill_date", lookup_expr="lte")

    entity = django_filters.NumberFilter(field_name="entity_id", required=True)
    entityfinid = django_filters.NumberFilter(field_name="entityfinid_id")
    subentity = django_filters.NumberFilter(field_name="subentity_id")
    customer = django_filters.NumberFilter(field_name="customer_id")
    customer_gstin = django_filters.CharFilter(field_name="customer_gstin", lookup_expr="icontains")

    doc_type = django_filters.CharFilter(method="filter_doc_type")
    status = django_filters.CharFilter(method="filter_status")
    supply_category = django_filters.CharFilter(method="filter_supply_category")
    taxability = django_filters.CharFilter(method="filter_taxability")
    tax_regime = django_filters.CharFilter(method="filter_tax_regime")

    is_b2b = django_filters.BooleanFilter(method="filter_is_b2b")
    is_b2c = django_filters.BooleanFilter(method="filter_is_b2c")
    is_export = django_filters.BooleanFilter(method="filter_is_export")
    is_sez = django_filters.BooleanFilter(method="filter_is_sez")
    is_deemed_export = django_filters.BooleanFilter(method="filter_is_deemed_export")

    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = SalesInvoiceHeader
        fields = []

    def filter_doc_type(self, queryset, name, value):
        values = self._parse_enum_csv(value, enum_cls=SalesInvoiceHeader.DocType, field_name="doc_type")
        return queryset.filter(doc_type__in=values) if values else queryset

    def filter_status(self, queryset, name, value):
        values = self._parse_enum_csv(value, enum_cls=SalesInvoiceHeader.Status, field_name="status")
        return queryset.filter(status__in=values) if values else queryset

    def filter_supply_category(self, queryset, name, value):
        values = self._parse_enum_csv(
            value,
            enum_cls=SalesInvoiceHeader.SupplyCategory,
            field_name="supply_category",
        )
        return queryset.filter(supply_category__in=values) if values else queryset

    def filter_taxability(self, queryset, name, value):
        values = self._parse_enum_csv(value, enum_cls=SalesInvoiceHeader.Taxability, field_name="taxability")
        return queryset.filter(taxability__in=values) if values else queryset

    def filter_tax_regime(self, queryset, name, value):
        values = self._parse_enum_csv(value, enum_cls=SalesInvoiceHeader.TaxRegime, field_name="tax_regime")
        return queryset.filter(tax_regime__in=values) if values else queryset

    def filter_is_b2b(self, queryset, name, value):
        b2b_values = [
            SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
            SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
            SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
        ]
        return queryset.filter(supply_category__in=b2b_values) if value else queryset.exclude(supply_category__in=b2b_values)

    def filter_is_b2c(self, queryset, name, value):
        target = SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C
        return queryset.filter(supply_category=target) if value else queryset.exclude(supply_category=target)

    def filter_is_export(self, queryset, name, value):
        export_values = [
            SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST,
            SalesInvoiceHeader.SupplyCategory.EXPORT_WITHOUT_IGST,
            SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT,
        ]
        return queryset.filter(supply_category__in=export_values) if value else queryset.exclude(supply_category__in=export_values)

    def filter_is_sez(self, queryset, name, value):
        sez_values = [
            SalesInvoiceHeader.SupplyCategory.SEZ_WITH_IGST,
            SalesInvoiceHeader.SupplyCategory.SEZ_WITHOUT_IGST,
        ]
        return queryset.filter(supply_category__in=sez_values) if value else queryset.exclude(supply_category__in=sez_values)

    def filter_is_deemed_export(self, queryset, name, value):
        target = SalesInvoiceHeader.SupplyCategory.DEEMED_EXPORT
        return queryset.filter(supply_category=target) if value else queryset.exclude(supply_category=target)

    def filter_search(self, queryset, name, value):
        term = (value or "").strip()
        if not term:
            return queryset
        if len(term) > 100:
            raise ValidationError({"search": ["Ensure this field has no more than 100 characters."]})
        query = (
            Q(doc_code__icontains=term)
            | Q(invoice_number__icontains=term)
            | Q(customer_name__icontains=term)
            | Q(reference__icontains=term)
        )
        if term.isdigit():
            query |= Q(doc_no=int(term))
        return queryset.filter(query)

    @staticmethod
    def _parse_enum_csv(value, *, enum_cls, field_name):
        if value in (None, ""):
            return []

        tokens = [token.strip() for token in str(value).split(",") if token.strip()]
        if not tokens:
            return []

        value_map = {str(choice.value): choice.value for choice in enum_cls}
        name_map = {choice.name.lower(): choice.value for choice in enum_cls}
        label_map = {str(choice.label).lower(): choice.value for choice in enum_cls}

        parsed = []
        invalid = []
        for token in tokens:
            lowered = token.lower()
            if token in value_map:
                parsed.append(value_map[token])
            elif lowered in name_map:
                parsed.append(name_map[lowered])
            elif lowered in label_map:
                parsed.append(label_map[lowered])
            else:
                invalid.append(token)

        if invalid:
            valid_tokens = ", ".join(str(choice.value) for choice in enum_cls)
            raise ValidationError({field_name: [f"Invalid value(s): {', '.join(invalid)}. Allowed values: {valid_tokens}."]})
        return parsed
