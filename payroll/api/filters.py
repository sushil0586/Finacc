# payroll/api/filters.py
import django_filters
from django.db.models import Q
from payroll.models import EntityPayrollComponent

class EntityPayrollComponentFilter(django_filters.FilterSet):
    """
    Query helpers:
    - ?entity_code=ORG-A
    - ?family_code=HRA
    - ?enabled=true
    - ?active_on=2025-08-01  (returns rows active on that date)
    """
    entity_code = django_filters.CharFilter(field_name="entity_code", lookup_expr="iexact")
    family_code = django_filters.CharFilter(field_name="family__code", lookup_expr="iexact")
    enabled = django_filters.BooleanFilter()
    active_on = django_filters.DateFilter(method="filter_active_on")

    class Meta:
        model = EntityPayrollComponent
        fields = ["entity_code", "family_code", "enabled"]

    def filter_active_on(self, queryset, name, value):
        # effective_from <= value <= effective_to (or null)
        return queryset.filter(
            (Q(effective_to__isnull=True) & Q(effective_from__lte=value)) |
            (Q(effective_to__isnull=False) & Q(effective_from__lte=value) & Q(effective_to__gte=value))
        )
