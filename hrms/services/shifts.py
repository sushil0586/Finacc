from __future__ import annotations

from django.db.models import Q

from hrms.models import HrShift


class ShiftService:
    @staticmethod
    def list_shifts(*, entity_id, subentity_id=None, status=None, search=None, active_only=True, ordering="name"):
        queryset = HrShift.all_objects.for_entity(entity_id=entity_id, subentity_id=subentity_id)
        if active_only:
            queryset = queryset.active()
        if status:
            queryset = queryset.filter(status=status)
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(timezone__icontains=search)
            )
        allowed_ordering = {
            "code": "code",
            "-code": "-code",
            "name": "name",
            "-name": "-name",
            "shift_type": "shift_type",
            "-shift_type": "-shift_type",
            "status": "status",
            "-status": "-status",
        }
        queryset = queryset.order_by(allowed_ordering.get(ordering, "name"))
        return queryset.select_related("entity", "subentity")
