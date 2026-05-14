from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from types import SimpleNamespace

from django.utils import timezone

from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity


@dataclass(frozen=True)
class ComplianceGoldenScope:
    entity: Entity
    subentity: SubEntity
    entityfin: EntityFinancialYear
    params: dict
    scope: SimpleNamespace


def build_compliance_golden_scope(*, user, entity_name: str, from_date: str = "2025-04-01", to_date: str = "2025-04-30") -> ComplianceGoldenScope:
    """
    Creates a deterministic entity/subentity/financial-year scope used by
    compliance API tests (GST exception, GST reconciliation, controls hub).
    """
    gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
    entity = Entity.objects.create(
        entityname=entity_name,
        legalname=f"{entity_name} Pvt Ltd",
        GstRegitrationType=gst_type,
        createdby=user,
    )
    subentity = SubEntity.objects.create(entity=entity, subentityname="Head Office")
    entityfin = EntityFinancialYear.objects.create(
        entity=entity,
        desc="FY 2025-26",
        finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
        finendyear=timezone.make_aware(datetime(2026, 3, 31)),
        createdby=user,
    )
    params = {
        "entity": entity.id,
        "entityfinid": entityfin.id,
        "subentity": subentity.id,
        "from_date": from_date,
        "to_date": to_date,
    }
    scope = SimpleNamespace(
        entity_id=entity.id,
        entityfinid_id=entityfin.id,
        subentity_id=subentity.id,
        month=4,
        year=2025,
        from_date=from_date,
        to_date=to_date,
    )
    return ComplianceGoldenScope(
        entity=entity,
        subentity=subentity,
        entityfin=entityfin,
        params=params,
        scope=scope,
    )
