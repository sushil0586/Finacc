from __future__ import annotations

from reports.models import UserReportPreference


def normalize_report_preference_payload(payload):
    if not isinstance(payload, dict):
        return {}
    normalized = {}
    for key, value in payload.items():
        if value in (None, "", [], {}, ()):
            continue
        normalized[key] = value
    return normalized


def get_user_report_preference(*, user, entity_id, report_code):
    return (
        UserReportPreference.objects.filter(user=user, entity_id=entity_id, report_code=report_code, isactive=True)
        .order_by("-updated_at", "-id")
        .first()
    )


def upsert_user_report_preference(*, user, entity, report_code, payload):
    payload = normalize_report_preference_payload(payload)
    preference, _created = UserReportPreference.objects.update_or_create(
        user=user,
        entity=entity,
        report_code=report_code,
        defaults={"payload": payload, "isactive": True},
    )
    return preference


def list_user_report_preferences(*, user, entity_id, report_codes=None):
    queryset = UserReportPreference.objects.filter(user=user, entity_id=entity_id, isactive=True)
    if report_codes:
        queryset = queryset.filter(report_code__in=list(report_codes))
    return {row.report_code: row.payload for row in queryset.order_by("report_code")}
