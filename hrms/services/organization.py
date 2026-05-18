from __future__ import annotations

from django.db.models import Q

from hrms.models import HrOrganizationUnit


class OrganizationUnitService:
    @staticmethod
    def list_units(*, entity_id, subentity_id=None, unit_type=None, status=None, search=None, active_only=True, ordering="name"):
        queryset = HrOrganizationUnit.all_objects.for_entity(entity_id=entity_id, subentity_id=subentity_id)
        if active_only:
            queryset = queryset.active()
        if unit_type:
            queryset = queryset.filter(unit_type=unit_type)
        if status:
            queryset = queryset.filter(status=status)
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(short_name__icontains=search)
                | Q(external_ref__icontains=search)
                | Q(parent__name__icontains=search)
            )
        allowed_ordering = {
            "code": "code",
            "-code": "-code",
            "name": "name",
            "-name": "-name",
            "unit_type": "unit_type",
            "-unit_type": "-unit_type",
            "status": "status",
            "-status": "-status",
            "sort_order": "sort_order",
            "-sort_order": "-sort_order",
        }
        queryset = queryset.order_by(allowed_ordering.get(ordering, "name"))
        return queryset.select_related("entity", "subentity", "parent")
