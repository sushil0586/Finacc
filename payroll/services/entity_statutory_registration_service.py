from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from payroll.models import EntityStatutoryRegistration


class EntityStatutoryRegistrationService:
    @staticmethod
    def list_registrations(
        *,
        entity_id: int,
        search: str | None = None,
        scheme_id: str | None = None,
        registration_state: str | None = None,
        is_active: bool | None = None,
    ):
        queryset = EntityStatutoryRegistration.objects.select_related("entity", "scheme").filter(entity_id=entity_id)
        if search:
            queryset = queryset.filter(Q(registration_number__icontains=search) | Q(scheme__code__icontains=search) | Q(scheme__name__icontains=search))
        if scheme_id:
            queryset = queryset.filter(scheme_id=scheme_id)
        if registration_state is not None and registration_state != "":
            queryset = queryset.filter(registration_state=registration_state)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("scheme__code", "registration_state", "-effective_from", "registration_number")

    @classmethod
    @transaction.atomic
    def create_or_update_registration(cls, attrs: dict, *, instance: EntityStatutoryRegistration | None = None) -> EntityStatutoryRegistration:
        registration = instance or EntityStatutoryRegistration()
        for key, value in attrs.items():
            setattr(registration, key, value)
        registration.registration_state = (registration.registration_state or "").strip().upper()
        cls._validate_overlap(registration=registration)
        try:
            registration.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        registration.save()
        return registration

    @staticmethod
    def _validate_overlap(*, registration: EntityStatutoryRegistration) -> None:
        if not registration.is_active:
            return
        existing = EntityStatutoryRegistration.objects.filter(
            entity=registration.entity,
            scheme=registration.scheme,
            registration_state=registration.registration_state,
            is_active=True,
        )
        if registration.pk:
            existing = existing.exclude(pk=registration.pk)
        start = registration.effective_from
        end = registration.effective_to or date.max
        for item in existing:
            item_end = item.effective_to or date.max
            if item.effective_from <= end and start <= item_end:
                raise ValueError("Active statutory registrations cannot overlap for the same entity, scheme, and state.")

    @staticmethod
    def resolve_active_registration(
        *,
        entity_id: int,
        scheme,
        registration_date: date,
        registration_state: str | None = None,
    ) -> EntityStatutoryRegistration | None:
        state = (registration_state or "").strip().upper()
        queryset = EntityStatutoryRegistration.objects.select_related("scheme").filter(
            entity_id=entity_id,
            scheme=scheme,
            is_active=True,
            effective_from__lte=registration_date,
        ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=registration_date))
        if state:
            queryset = queryset.filter(registration_state=state)
        else:
            queryset = queryset.filter(registration_state="")
        return queryset.order_by("-effective_from", "-id").first()
