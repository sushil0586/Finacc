from __future__ import annotations

import django_filters
from django.core.exceptions import ValidationError
from django.db.models import Q

from purchase.models.purchase_core import PurchaseInvoiceHeader


class PurchaseRegisterFilter(django_filters.FilterSet):
    """
    Reusable filter base for purchase-register style reports.

    The register stays header-wise, so every filter targets header fields only.
    """

    from_date = django_filters.DateFilter(field_name="bill_date", lookup_expr="gte")
    to_date = django_filters.DateFilter(field_name="bill_date", lookup_expr="lte")
    posting_from_date = django_filters.DateFilter(field_name="posting_date", lookup_expr="gte")
    posting_to_date = django_filters.DateFilter(field_name="posting_date", lookup_expr="lte")

    entity = django_filters.NumberFilter(field_name="entity_id", required=True)
    entityfinid = django_filters.NumberFilter(field_name="entityfinid_id")
    subentity = django_filters.NumberFilter(field_name="subentity_id")
    vendor = django_filters.NumberFilter(field_name="vendor_id")

    supplier_gstin = django_filters.CharFilter(field_name="vendor_gstin", lookup_expr="icontains")
    reverse_charge = django_filters.BooleanFilter(field_name="is_reverse_charge")
    blocked_itc = django_filters.BooleanFilter(method="filter_blocked_itc")
    min_amount = django_filters.NumberFilter(field_name="grand_total", lookup_expr="gte")
    max_amount = django_filters.NumberFilter(field_name="grand_total", lookup_expr="lte")
    search = django_filters.CharFilter(method="filter_search")

    doc_type = django_filters.CharFilter(method="filter_doc_type")
    status = django_filters.CharFilter(method="filter_status")
    itc_eligibility = django_filters.BooleanFilter(field_name="is_itc_eligible")
    itc_claim_status = django_filters.CharFilter(method="filter_itc_claim_status")
    gstr2b_match_status = django_filters.CharFilter(method="filter_gstr2b_match_status")

    class Meta:
        model = PurchaseInvoiceHeader
        fields = []

    def filter_blocked_itc(self, queryset, name, value):
        blocked_q = Q(itc_claim_status=PurchaseInvoiceHeader.ItcClaimStatus.BLOCKED) | (
            Q(itc_block_reason__isnull=False) & ~Q(itc_block_reason="")
        )
        return queryset.filter(blocked_q if value else ~blocked_q)

    def filter_doc_type(self, queryset, name, value):
        values = self._parse_enum_csv(
            value,
            enum_cls=PurchaseInvoiceHeader.DocType,
            field_name="doc_type",
        )
        return queryset.filter(doc_type__in=values) if values else queryset

    def filter_status(self, queryset, name, value):
        values = self._parse_enum_csv(
            value,
            enum_cls=PurchaseInvoiceHeader.Status,
            field_name="status",
        )
        return queryset.filter(status__in=values) if values else queryset

    def filter_itc_claim_status(self, queryset, name, value):
        values = self._parse_enum_csv(
            value,
            enum_cls=PurchaseInvoiceHeader.ItcClaimStatus,
            field_name="itc_claim_status",
        )
        return queryset.filter(itc_claim_status__in=values) if values else queryset

    def filter_gstr2b_match_status(self, queryset, name, value):
        values = self._parse_enum_csv(
            value,
            enum_cls=PurchaseInvoiceHeader.Gstr2bMatchStatus,
            field_name="gstr2b_match_status",
        )
        return queryset.filter(gstr2b_match_status__in=values) if values else queryset

    def filter_search(self, queryset, name, value):
        term = (value or "").strip()
        if not term:
            return queryset
        if len(term) > 100:
            raise ValidationError({"search": ["Ensure this field has no more than 100 characters."]})
        query = (
            Q(doc_code__icontains=term)
            | Q(purchase_number__icontains=term)
            | Q(supplier_invoice_number__icontains=term)
            | Q(vendor_name__icontains=term)
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
