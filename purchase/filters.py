# purchase/api/filters.py
import django_filters
from django.db.models import Q
from purchase.models.purchase_core import PurchaseInvoiceHeader


class PurchaseInvoiceSearchFilter(django_filters.FilterSet):
    # scope
    entity = django_filters.NumberFilter(field_name="entity_id")
    entityfinid = django_filters.NumberFilter(field_name="entityfinid_id")
    subentity = django_filters.NumberFilter(field_name="subentity_id")

    # enums
    doc_type = django_filters.NumberFilter(field_name="doc_type")
    status = django_filters.NumberFilter(field_name="status")
    supply_category = django_filters.NumberFilter(field_name="supply_category")
    default_taxability = django_filters.NumberFilter(field_name="default_taxability")
    tax_regime = django_filters.NumberFilter(field_name="tax_regime")
    gstr2b_match_status = django_filters.NumberFilter(field_name="gstr2b_match_status")
    itc_claim_status = django_filters.NumberFilter(field_name="itc_claim_status")

    # booleans
    is_igst = django_filters.BooleanFilter(field_name="is_igst")
    is_reverse_charge = django_filters.BooleanFilter(field_name="is_reverse_charge")
    is_itc_eligible = django_filters.BooleanFilter(field_name="is_itc_eligible")

    # vendor
    vendor = django_filters.NumberFilter(field_name="vendor_id")
    vendor_gstin = django_filters.CharFilter(field_name="vendor_gstin", lookup_expr="icontains")
    vendor_name = django_filters.CharFilter(field_name="vendor_name", lookup_expr="icontains")

    # identity text
    doc_code = django_filters.CharFilter(field_name="doc_code", lookup_expr="iexact")
    doc_no = django_filters.NumberFilter(field_name="doc_no")
    purchase_number = django_filters.CharFilter(field_name="purchase_number", lookup_expr="icontains")
    supplier_invoice_number = django_filters.CharFilter(field_name="supplier_invoice_number", lookup_expr="icontains")

    # claim period (YYYY-MM)
    itc_claim_period = django_filters.CharFilter(field_name="itc_claim_period", lookup_expr="iexact")

    # date ranges
    bill_date_from = django_filters.DateFilter(field_name="bill_date", lookup_expr="gte")
    bill_date_to = django_filters.DateFilter(field_name="bill_date", lookup_expr="lte")

    posting_date_from = django_filters.DateFilter(field_name="posting_date", lookup_expr="gte")
    posting_date_to = django_filters.DateFilter(field_name="posting_date", lookup_expr="lte")

    due_date_from = django_filters.DateFilter(field_name="due_date", lookup_expr="gte")
    due_date_to = django_filters.DateFilter(field_name="due_date", lookup_expr="lte")

    supplier_invoice_date_from = django_filters.DateFilter(field_name="supplier_invoice_date", lookup_expr="gte")
    supplier_invoice_date_to = django_filters.DateFilter(field_name="supplier_invoice_date", lookup_expr="lte")

    # amount ranges
    grand_total_min = django_filters.NumberFilter(field_name="grand_total", lookup_expr="gte")
    grand_total_max = django_filters.NumberFilter(field_name="grand_total", lookup_expr="lte")

    total_taxable_min = django_filters.NumberFilter(field_name="total_taxable", lookup_expr="gte")
    total_taxable_max = django_filters.NumberFilter(field_name="total_taxable", lookup_expr="lte")

    # free text "q" across the most useful columns
    q = django_filters.CharFilter(method="filter_q")

    def filter_q(self, queryset, name, value):
        v = (value or "").strip()
        if not v:
            return queryset
        return queryset.filter(
            Q(purchase_number__icontains=v)
            | Q(supplier_invoice_number__icontains=v)
            | Q(vendor_name__icontains=v)
            | Q(vendor_gstin__icontains=v)
            | Q(doc_code__iexact=v)
            | Q(doc_no__icontains=v)  # works if v numeric-ish; harmless otherwise
        )

    class Meta:
        model = PurchaseInvoiceHeader
        fields = []
