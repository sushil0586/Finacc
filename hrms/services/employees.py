from __future__ import annotations

from django.db.models import Q

from hrms.models import HrEmployee


class EmployeeService:
    @staticmethod
    def list_employees(*, entity_id, subentity_id=None, search=None, status=None, active_only=True, ordering="display_name"):
        queryset = HrEmployee.all_objects.for_entity(entity_id=entity_id, subentity_id=subentity_id)
        if active_only:
            queryset = queryset.active()
        if search:
            queryset = queryset.filter(
                Q(employee_number__icontains=search)
                | Q(display_name__icontains=search)
                | Q(legal_first_name__icontains=search)
                | Q(legal_last_name__icontains=search)
                | Q(work_email__icontains=search)
                | Q(mobile_number__icontains=search)
            )
        if status:
            queryset = queryset.filter(lifecycle_status=status)
        allowed_ordering = {
            "employee_number": "employee_number",
            "-employee_number": "-employee_number",
            "display_name": "display_name",
            "-display_name": "-display_name",
            "work_email": "work_email",
            "-work_email": "-work_email",
            "lifecycle_status": "lifecycle_status",
            "-lifecycle_status": "-lifecycle_status",
        }
        queryset = queryset.order_by(allowed_ordering.get(ordering, "display_name"))
        return queryset.select_related("entity", "subentity", "linked_user")
