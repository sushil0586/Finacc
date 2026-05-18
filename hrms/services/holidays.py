from __future__ import annotations

from django.db.models import Q

from hrms.models import HrHolidayCalendar


class HolidayCalendarService:
    @staticmethod
    def list_calendars(
        *,
        entity_id,
        subentity_id=None,
        calendar_year=None,
        status=None,
        search=None,
        active_only=True,
        ordering="-calendar_year",
    ):
        queryset = HrHolidayCalendar.all_objects.for_entity(entity_id=entity_id, subentity_id=subentity_id)
        if active_only:
            queryset = queryset.active()
        if calendar_year is not None:
            queryset = queryset.filter(calendar_year=calendar_year)
        if status:
            queryset = queryset.filter(status=status)
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(description__icontains=search)
            )
        allowed_ordering = {
            "code": "code",
            "-code": "-code",
            "name": "name",
            "-name": "-name",
            "calendar_year": "calendar_year",
            "-calendar_year": "-calendar_year",
            "status": "status",
            "-status": "-status",
        }
        queryset = queryset.order_by(allowed_ordering.get(ordering, "-calendar_year"))
        return queryset.select_related("entity", "subentity", "country", "state")
