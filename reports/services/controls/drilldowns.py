from __future__ import annotations


def build_posting_detail_drilldown(
    *,
    entry_id: int | None,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    label: str = "Open posting detail",
) -> dict[str, object] | None:
    if not entry_id:
        return None
    return {
        "target": "posting_detail",
        "label": label,
        "kind": "posting",
        "route": "/reports/financial/posting-detail/:entry_id",
        "params": {
            "entry_id": int(entry_id),
            "entity": int(entity_id),
            "entityfinid": int(entityfin_id) if entityfin_id else None,
            "subentity": int(subentity_id) if subentity_id else None,
        },
    }
