import django_filters
from purchase.models.purchase_addons import PurchaseChargeType


class PurchaseChargeTypeFilter(django_filters.FilterSet):
    entity = django_filters.NumberFilter(field_name="entity_id")
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = PurchaseChargeType
        fields = ["entity", "is_active", "base_category"]