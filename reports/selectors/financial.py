from __future__ import annotations

from datetime import date

from django.db.models import F
from django.db.models.functions import Coalesce

from entity.models import Entity, EntityFinancialYear, SubEntity
from posting.models import EntryStatus, JournalLine


def normalize_scope_ids(entity_id, entityfin_id=None, subentity_id=None):
    entity_id = int(entity_id)
    entityfin_id = int(entityfin_id) if entityfin_id not in (None, "", 0, "0") else None
    subentity_id = int(subentity_id) if subentity_id not in (None, "", 0, "0") else None
    return entity_id, entityfin_id, subentity_id


def resolve_date_window(entityfin_id=None, from_date=None, to_date=None):
    if entityfin_id:
        fy = EntityFinancialYear.objects.get(id=entityfin_id)
        return ensure_date(fy.finstartyear), ensure_date(fy.finendyear)
    return ensure_date(from_date), ensure_date(to_date)


def journal_lines_for_scope(entity_id, entityfin_id=None, subentity_id=None, from_date=None, to_date=None):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = resolve_date_window(entityfin_id, from_date, to_date)

    qs = (
        JournalLine.objects.filter(
            entity_id=entity_id,
            entry__status=EntryStatus.POSTED,
        )
        .annotate(
            resolved_ledger_id=Coalesce(F("ledger_id"), F("account__ledger_id")),
        )
        .exclude(resolved_ledger_id__isnull=True)
        .select_related(
            "entry",
            "ledger",
            "ledger__accounthead",
            "ledger__accounthead__accounttype",
            "account",
        )
    )
    if entityfin_id:
        qs = qs.filter(entityfin_id=entityfin_id)
    if subentity_id:
        qs = qs.filter(subentity_id=subentity_id)
    if from_date:
        qs = qs.filter(posting_date__gte=from_date)
    if to_date:
        qs = qs.filter(posting_date__lte=to_date)
    return qs


def ensure_date(value):
    if value is None or isinstance(value, date):
        return value
    return value.date()


def resolve_scope_names(entity_id, entityfin_id=None, subentity_id=None):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    entity = Entity.objects.filter(id=entity_id).only("id", "entityname").first()
    entityfin = (
        EntityFinancialYear.objects.filter(id=entityfin_id).only("id", "desc").first() if entityfin_id else None
    )
    subentity = (
        SubEntity.objects.filter(id=subentity_id).only("id", "subentityname").first() if subentity_id else None
    )
    return {
        "entity_name": entity.entityname if entity else None,
        "entityfin_name": entityfin.desc if entityfin else None,
        "subentity_name": subentity.subentityname if subentity else None,
    }
