from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from payroll.models import StatutoryScheme


class StatutorySchemeService:
    @staticmethod
    def list_schemes(
        *,
        search: str | None = None,
        scheme_type: str | None = None,
        country_code: str | None = None,
        state_code: str | None = None,
        is_active: bool | None = None,
        is_system: bool | None = None,
    ):
        queryset = StatutoryScheme.objects.all()
        if search:
            queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search) | Q(description__icontains=search))
        if scheme_type:
            queryset = queryset.filter(scheme_type=scheme_type)
        if country_code:
            queryset = queryset.filter(country_code=country_code)
        if state_code is not None and state_code != "":
            queryset = queryset.filter(state_code=state_code)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        if is_system is not None:
            queryset = queryset.filter(is_system=is_system)
        return queryset.order_by("country_code", "state_code", "scheme_type", "code")

    @staticmethod
    @transaction.atomic
    def create_or_update_scheme(attrs: dict, *, instance: StatutoryScheme | None = None) -> StatutoryScheme:
        scheme = instance or StatutoryScheme()
        for key, value in attrs.items():
            setattr(scheme, key, value)
        scheme.state_code = (scheme.state_code or "").strip().upper()
        try:
            scheme.full_clean()
        except DjangoValidationError as err:
            raise ValueError(err.message_dict or err.messages)
        scheme.save()
        return scheme
