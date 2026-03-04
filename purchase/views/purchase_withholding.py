from __future__ import annotations

from datetime import date

from django.db.models import Q
from django.utils.dateparse import parse_date
from django.utils import timezone
from rest_framework.generics import ListAPIView
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from withholding.models import WithholdingSection, WithholdingTaxType, EntityWithholdingConfig
from purchase.serializers.purchase_withholding import PurchaseTdsSectionSerializer


class PurchaseTdsSectionListAPIView(ListAPIView):
    """
    GET /api/purchase/tds-sections/?entity=1&entityfinid=2&subentity=5&on_date=2026-03-03&q=194&is_active=true
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PurchaseTdsSectionSerializer

    def _parse_int(self, key: str, required: bool = False):
        # Allow path param override for entity route.
        if key == "entity":
            path_entity = self.kwargs.get("entity_id")
            if path_entity is not None:
                return int(path_entity)

        raw = self.request.query_params.get(key)
        if raw in (None, ""):
            if required:
                raise ValidationError({key: f"{key} query param is required."})
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise ValidationError({key: f"{key} must be an integer."})

    def _parse_on_date(self) -> date:
        raw = self.request.query_params.get("on_date")
        if not raw:
            return timezone.localdate()
        d = parse_date(raw)
        if not d:
            raise ValidationError({"on_date": "on_date must be in YYYY-MM-DD format."})
        return d

    def _parse_is_active(self, raw: str | None):
        if raw is None or raw == "":
            return True
        value = str(raw).strip().lower()
        if value in ("1", "true", "yes", "y"):
            return True
        if value in ("0", "false", "no", "n"):
            return False
        return True

    def _resolve_entity_config(self, *, entity_id: int, entityfinid_id: int | None, subentity_id: int | None, on_date: date):
        cfg_qs = EntityWithholdingConfig.objects.filter(entity_id=entity_id, effective_from__lte=on_date)
        if entityfinid_id is not None:
            cfg_qs = cfg_qs.filter(entityfin_id=entityfinid_id)

        if subentity_id is not None:
            cfg_qs = cfg_qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True)).order_by("-subentity_id", "-effective_from")
        else:
            cfg_qs = cfg_qs.filter(subentity__isnull=True).order_by("-effective_from")

        return cfg_qs.first()

    def get_queryset(self):
        entity_id = self._parse_int("entity", required=True)
        entityfinid_id = self._parse_int("entityfinid", required=False)
        subentity_id = self._parse_int("subentity", required=False)
        on_date = self._parse_on_date()

        cfg = self._resolve_entity_config(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            on_date=on_date,
        )

        # Entity explicitly has TDS disabled for the selected context/date.
        if cfg and not cfg.enable_tds:
            return WithholdingSection.objects.none()

        qs = WithholdingSection.objects.filter(tax_type=WithholdingTaxType.TDS)

        is_active = self._parse_is_active(self.request.query_params.get("is_active"))
        qs = qs.filter(is_active=is_active)
        qs = qs.filter(effective_from__lte=on_date).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))

        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(section_code__icontains=q) | Q(description__icontains=q))

        return qs.order_by("section_code", "id")
