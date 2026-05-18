from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from payroll.models import StatutoryRule, StatutorySlab


class StatutorySlabService:
    @staticmethod
    def list_slabs(*, rule: StatutoryRule, is_active: bool | None = None):
        queryset = StatutorySlab.objects.filter(rule=rule)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("slab_from", "id")

    @staticmethod
    @transaction.atomic
    def create_or_update_slab(attrs: dict, *, instance: StatutorySlab | None = None) -> StatutorySlab:
        slab = instance or StatutorySlab()
        for key, value in attrs.items():
            setattr(slab, key, value)
        try:
            slab.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        slab.save()
        return slab
