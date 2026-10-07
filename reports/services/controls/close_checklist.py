from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from financial.models import FinancialSettings
from reports.services.controls.phase_one import _close_checklist_scope_key, build_phase_one_controls_hub
from reports.services.financial.reporting_policy import FINANCIAL_REPORTING_POLICY_DEFAULTS, _sanitize


def update_close_checklist_item(
    *,
    entity_id: int,
    entityfin_id: int | None,
    subentity_id: int | None,
    item_key: str,
    status: str,
    comment: str = "",
    created_by=None,
) -> dict[str, Any]:
    item_key = str(item_key or "").strip()
    if not item_key:
        raise ValidationError({"item_key": "Checklist item key is required."})

    status = str(status or "review").strip().lower()
    if status not in {"review", "done"}:
        raise ValidationError({"status": "Checklist status must be review or done."})

    current_hub = build_phase_one_controls_hub(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id)
    current_items = (current_hub.get("year_end_close_readiness") or {}).get("checklist") or []
    current_item = next((item for item in current_items if str(item.get("key")) == item_key), None)
    if current_item is None:
        raise ValidationError({"item_key": "Checklist item was not found for the selected scope."})

    effective_status = "review" if current_item.get("status") == "blocked" and status == "done" else status
    settings, _ = FinancialSettings.objects.get_or_create(
        entity_id=entity_id,
        defaults={
            "createdby": created_by,
            "reporting_policy": deepcopy(FINANCIAL_REPORTING_POLICY_DEFAULTS),
        },
    )
    policy = deepcopy(settings.reporting_policy or {})
    close_checklist = dict(policy.get("close_checklist") or {})
    items = dict(close_checklist.get("items") or {})
    scope_key = _close_checklist_scope_key(entityfin_id, subentity_id)
    scope_items = dict(items.get(scope_key) or {})
    scope_items[item_key] = {
        "status": effective_status,
        "comment": str(comment or "").strip()[:500],
        "updated_at": timezone.now().isoformat(),
        "updated_by": getattr(created_by, "id", None),
    }
    items[scope_key] = scope_items
    close_checklist["items"] = items
    policy["close_checklist"] = close_checklist
    settings.reporting_policy = _sanitize(policy)
    if not getattr(settings, "createdby_id", None) and created_by is not None:
        settings.createdby = created_by
    settings.save(update_fields=["reporting_policy", "updated_at"] if hasattr(settings, "updated_at") else ["reporting_policy"])

    updated_hub = build_phase_one_controls_hub(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id)
    updated_items = (updated_hub.get("year_end_close_readiness") or {}).get("checklist") or []
    updated_item = next((item for item in updated_items if str(item.get("key")) == item_key), None)
    return {
        "entity": entity_id,
        "entityfinid": entityfin_id,
        "subentity": subentity_id,
        "item": updated_item or current_item,
        "readiness": updated_hub.get("year_end_close_readiness"),
        "manual_override_applied": current_item.get("status") != "blocked",
    }
