from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from auditlogger.models import AuditLog
from financial.models import FinancialSettings
from reports.services.financial.reporting_policy import FINANCIAL_REPORTING_POLICY_DEFAULTS, _deep_merge, _sanitize


def resolve_audit_trail_policy(entity_id: int) -> dict[str, Any]:
    settings = FinancialSettings.objects.filter(entity_id=entity_id).only("reporting_policy").first()
    merged = _deep_merge(FINANCIAL_REPORTING_POLICY_DEFAULTS, getattr(settings, "reporting_policy", None) or {})
    return _sanitize(merged).get("audit_trail", {})


def record_controls_audit_event(
    *,
    request=None,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    action: str,
    module: str,
    old_data: dict[str, Any] | None = None,
    new_data: dict[str, Any] | None = None,
) -> None:
    AuditLog.objects.create(
        user=getattr(request, "user", None) if request is not None else None,
        method=getattr(request, "method", "SYSTEM") if request is not None else "SYSTEM",
        path=(
            f"/controls/phase-one/{module}/"
            f"?entity={entity_id}&entityfinid={entityfin_id or ''}&subentity={subentity_id or ''}"
        ),
        action=f"controls_phase_one.{action}",
        old_data=old_data,
        new_data={
            "entity": entity_id,
            "entityfinid": entityfin_id,
            "subentity": subentity_id,
            "module": module,
            **(new_data or {}),
        },
    )


def _audit_queryset_for_entity(entity_id: int):
    entity_token = f"entity={entity_id}"
    entity_path_token = f"/{entity_id}/"
    return AuditLog.objects.filter(path__icontains=entity_token) | AuditLog.objects.filter(path__icontains=entity_path_token)


def _labelize(value: str | None) -> str:
    if not value:
        return "-"
    return str(value).replace("controls_phase_one.", "").replace("_", " ").replace(".", " ").title()


def _event_module(event: AuditLog) -> str:
    data = event.new_data if isinstance(event.new_data, dict) else {}
    module = data.get("module")
    if module:
        return str(module)
    action = str(event.action or "")
    if action.startswith("approval_workflow."):
        return "approval_workflow"
    if action.startswith("attachment_vault."):
        return "attachment_vault"
    if action.startswith("controls_phase_one."):
        return action.replace("controls_phase_one.", "").split(".")[0]
    return "general"


def _event_detail(event: AuditLog) -> str:
    data = event.new_data if isinstance(event.new_data, dict) else {}
    for key in ("detail", "message", "document_no", "format", "status"):
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return _labelize(event.action)


def _resolve_activity_window(date_from=None, date_to=None) -> tuple:
    max_days = max(1, int(getattr(settings, "CONTROLS_AUDIT_ACTIVITY_MAX_DAYS", 366) or 366))
    default_days = max(1, int(getattr(settings, "CONTROLS_AUDIT_ACTIVITY_DEFAULT_DAYS", 90) or 90))
    if default_days > max_days:
        default_days = max_days

    resolved_to = date_to or timezone.localdate()
    resolved_from = date_from or (resolved_to - timedelta(days=default_days - 1))
    if resolved_from > resolved_to:
        raise ValidationError({"detail": "Audit activity date_from cannot be after date_to."})
    if (resolved_to - resolved_from).days + 1 > max_days:
        raise ValidationError({"detail": f"Audit activity range cannot exceed {max_days} days."})
    return resolved_from, resolved_to, max_days, (not date_from or not date_to)


def build_controls_audit_activity(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    module: str | None = None,
    user_id: int | None = None,
    date_from=None,
    date_to=None,
    limit: int = 50,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 50), 200))
    resolved_date_from, resolved_date_to, max_days, default_window_applied = _resolve_activity_window(date_from=date_from, date_to=date_to)
    queryset = _audit_queryset_for_entity(entity_id).filter(
        Q(action__startswith="controls_phase_one.")
        | Q(action__startswith="approval_workflow.")
        | Q(action__startswith="attachment_vault.")
    )
    if entityfin_id:
        queryset = queryset.filter(Q(path__icontains=f"entityfinid={entityfin_id}") | Q(new_data__entityfinid=entityfin_id))
    if subentity_id:
        queryset = queryset.filter(Q(path__icontains=f"subentity={subentity_id}") | Q(new_data__subentity=subentity_id))
    if module:
        queryset = queryset.filter(Q(new_data__module=module) | Q(action__icontains=module))
    if user_id:
        queryset = queryset.filter(user_id=user_id)
    queryset = queryset.filter(timestamp__date__gte=resolved_date_from, timestamp__date__lte=resolved_date_to)

    total = queryset.count()
    module_counts = [
        {"module": row["new_data__module"] or "general", "label": _labelize(row["new_data__module"] or "general"), "count": row["count"]}
        for row in queryset.values("new_data__module").annotate(count=Count("id")).order_by("-count", "new_data__module")[:20]
    ]
    user_counts = [
        {
            "user_id": row["user_id"],
            "username": row["user__username"] or "System",
            "count": row["count"],
        }
        for row in queryset.values("user_id", "user__username").annotate(count=Count("id")).order_by("-count", "user__username")[:20]
    ]

    events = []
    for event in queryset.select_related("user").order_by("-timestamp", "-id")[:limit]:
        module_key = _event_module(event)
        actor_name = None
        if event.user_id:
            get_full_name = getattr(event.user, "get_full_name", None)
            actor_name = get_full_name() if callable(get_full_name) else None
            actor_name = actor_name or event.user.get_username()
        actor_username = (getattr(event.user, "username", None) or event.user.get_username()) if event.user_id else "system"
        events.append(
            {
                "id": event.id,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "action": event.action,
                "action_label": _labelize(event.action),
                "module": module_key,
                "module_label": _labelize(module_key),
                "method": event.method or "-",
                "actor": {
                    "id": event.user_id,
                    "username": actor_username,
                    "name": actor_name or "System",
                },
                "path": event.path,
                "entity": entity_id,
                "entityfinid": entityfin_id,
                "subentity": subentity_id,
                "detail": _event_detail(event),
                "old_data": event.old_data,
                "new_data": event.new_data,
            }
        )

    return {
        "entity": entity_id,
        "entityfinid": entityfin_id,
        "subentity": subentity_id,
        "filters": {
            "module": module,
            "user": user_id,
            "date_from": resolved_date_from.isoformat() if resolved_date_from else None,
            "date_to": resolved_date_to.isoformat() if resolved_date_to else None,
            "limit": limit,
            "default_window_applied": default_window_applied,
            "max_days": max_days,
        },
        "summary": {
            "total": total,
            "modules": module_counts,
            "users": user_counts,
        },
        "events": events,
    }


def summarize_audit_trail_policy(policy: dict[str, Any], *, entity_id: int | None = None) -> list[dict[str, Any]]:
    modules = policy.get("modules") or {}
    enabled_modules = sum(1 for value in modules.values() if value)
    recent_count = 0
    write_count = 0
    if entity_id:
        since = timezone.now() - timedelta(days=30)
        qs = _audit_queryset_for_entity(entity_id).filter(timestamp__gte=since)
        recent_count = qs.count()
        write_count = qs.exclude(method__in=["GET", "HEAD", "OPTIONS"]).count()
    return [
        {"label": "Recent events", "value": recent_count, "note": "Captured in the last 30 days.", "tone": "accent" if recent_count else "warning"},
        {"label": "Write events", "value": write_count, "note": "Non-read audit events in the last 30 days.", "tone": "neutral"},
        {"label": "Modules", "value": enabled_modules, "note": "Control modules covered by audit policy.", "tone": "accent" if enabled_modules else "warning"},
        {"label": "Retention", "value": policy.get("retention_days") or 365, "note": "Configured retention in days.", "tone": "neutral"},
        {"label": "Export", "value": "Enabled" if policy.get("export_enabled") else "Disabled", "note": "Audit trail export control.", "tone": "neutral"},
    ]


def build_audit_trail_readiness(entity_id: int) -> dict[str, Any]:
    policy = resolve_audit_trail_policy(entity_id)
    modules = policy.get("modules") or {}
    enabled_modules = sum(1 for value in modules.values() if value)
    summary_cards = summarize_audit_trail_policy(policy, entity_id=entity_id)
    recent_events = int(summary_cards[0]["value"] or 0)
    if not policy.get("enabled", True):
        status = "review"
        status_label = "Disabled"
    elif not enabled_modules:
        status = "blocked"
        status_label = "No Modules"
    elif not policy.get("capture_write_actions", True):
        status = "blocked"
        status_label = "Writes Not Captured"
    elif recent_events == 0:
        status = "review"
        status_label = "No Recent Events"
    else:
        status = "ready"
        status_label = "Capturing"
    return {
        "status": status,
        "status_label": status_label,
        "summary_cards": summary_cards,
        "policy": policy,
        "actions": [{"label": "Review Audit Trail", "route": "/reports/controls/phase-one", "params": {}}],
    }


def update_audit_trail_policy(*, entity_id: int, updates: dict[str, Any], created_by=None) -> dict[str, Any]:
    settings, _ = FinancialSettings.objects.get_or_create(
        entity_id=entity_id,
        defaults={"createdby": created_by, "reporting_policy": deepcopy(FINANCIAL_REPORTING_POLICY_DEFAULTS)},
    )
    policy = deepcopy(settings.reporting_policy or {})
    audit = dict(policy.get("audit_trail") or {})
    for key in ("enabled", "capture_read_actions", "capture_write_actions", "export_enabled"):
        if key in updates:
            audit[key] = bool(updates.get(key))
    if "retention_days" in updates:
        audit["retention_days"] = updates.get("retention_days")
    if "modules" in updates and isinstance(updates.get("modules"), dict):
        audit["modules"] = updates.get("modules")
    policy["audit_trail"] = audit
    settings.reporting_policy = _sanitize(policy)
    if not getattr(settings, "createdby_id", None) and created_by is not None:
        settings.createdby = created_by
    settings.save(update_fields=["reporting_policy", "updated_at"] if hasattr(settings, "updated_at") else ["reporting_policy"])
    return resolve_audit_trail_policy(entity_id)
