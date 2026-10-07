from __future__ import annotations

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from reports.models import ReportFreezeSnapshot
from reports.services.controls.phase_one import build_phase_one_controls_hub


REPORT_CODE = "controls_phase_one_audit_pack"
REVIEW_STATUSES = {"prepared", "reviewed", "approved"}


def create_evidence_pack_snapshot(*, entity_id: int, entityfin_id: int, subentity_id: int | None = None, generated_by=None) -> dict:
    if not entityfin_id:
        raise ValueError("Financial year is required to create an evidence pack snapshot.")

    hub = build_phase_one_controls_hub(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id)
    audit_pack = hub.get("audit_pack") or {}
    payload = {
        "snapshot": {
            "hub": hub,
            "audit_pack": audit_pack,
            "export_metadata": {
                "supported_formats": ["csv", "pdf"],
                "source": "controls_phase_one",
            },
        },
        "review": {
            "status": "prepared",
            "status_label": "Prepared",
            "comment": "",
            "reviewed_by": None,
            "reviewed_at": None,
            "approved_by": None,
            "approved_at": None,
        },
    }
    with transaction.atomic():
        latest = (
            ReportFreezeSnapshot.objects.select_for_update()
            .filter(report_code=REPORT_CODE, entity_id=entity_id, entityfinid_id=entityfin_id, subentity_id=subentity_id, isactive=True)
            .aggregate(version=Max("version"))
            .get("version")
            or 0
        )
        snapshot = ReportFreezeSnapshot.objects.create(
            report_code=REPORT_CODE,
            entity_id=entity_id,
            entityfinid_id=entityfin_id,
            subentity_id=subentity_id,
            version=latest + 1,
            payload=payload,
            frozen_by=generated_by if getattr(generated_by, "is_authenticated", False) else None,
        )
    return serialize_evidence_pack_snapshot(snapshot, include_payload=True)


def list_evidence_pack_snapshots(*, entity_id: int, entityfin_id: int, subentity_id: int | None = None, include_payload: bool = False) -> dict:
    rows = list(ReportFreezeSnapshot.objects.filter(
        report_code=REPORT_CODE,
        entity_id=entity_id,
        entityfinid_id=entityfin_id,
        subentity_id=subentity_id,
        isactive=True,
    ).select_related("frozen_by")[:25])
    serialized = [serialize_evidence_pack_snapshot(row, include_payload=include_payload) for row in rows]
    comparison = compare_evidence_pack_snapshots(rows[0], rows[1]) if len(rows) >= 2 else None
    return {"count": len(serialized), "results": serialized, "latest_comparison": comparison}


def get_evidence_pack_snapshot(*, snapshot_id: int, entity_id: int, include_payload: bool = True) -> dict:
    snapshot = ReportFreezeSnapshot.objects.select_related("frozen_by").get(
        pk=snapshot_id,
        report_code=REPORT_CODE,
        entity_id=entity_id,
        isactive=True,
    )
    return serialize_evidence_pack_snapshot(snapshot, include_payload=include_payload)


def compare_evidence_pack_snapshots(latest: ReportFreezeSnapshot, previous: ReportFreezeSnapshot) -> dict:
    latest_payload = latest.payload if isinstance(latest.payload, dict) else {}
    previous_payload = previous.payload if isinstance(previous.payload, dict) else {}
    latest_pack = ((latest_payload.get("snapshot") or {}).get("audit_pack") or {}) if isinstance(latest_payload.get("snapshot"), dict) else {}
    previous_pack = ((previous_payload.get("snapshot") or {}).get("audit_pack") or {}) if isinstance(previous_payload.get("snapshot"), dict) else {}
    latest_rows = _evidence_row_map(latest_pack.get("evidence_rows") or [])
    previous_rows = _evidence_row_map(previous_pack.get("evidence_rows") or [])
    added_keys = sorted(set(latest_rows) - set(previous_rows))
    removed_keys = sorted(set(previous_rows) - set(latest_rows))
    shared_keys = sorted(set(latest_rows) & set(previous_rows))
    changed = [
        _comparison_row(key, latest_rows[key], previous_rows[key])
        for key in shared_keys
        if _row_signature(latest_rows[key]) != _row_signature(previous_rows[key])
    ]
    unchanged = len(shared_keys) - len(changed)
    return {
        "from_version": previous.version,
        "to_version": latest.version,
        "summary": {
            "added": len(added_keys),
            "removed": len(removed_keys),
            "changed": len(changed),
            "unchanged": unchanged,
            "latest_rows": len(latest_rows),
            "previous_rows": len(previous_rows),
            "failed_delta": _summary_delta(latest_pack, previous_pack, "failed_checks"),
            "review_delta": _summary_delta(latest_pack, previous_pack, "review_checks"),
            "passed_delta": _summary_delta(latest_pack, previous_pack, "passed_checks"),
        },
        "added": [latest_rows[key] for key in added_keys],
        "removed": [previous_rows[key] for key in removed_keys],
        "changed": changed,
    }


def update_evidence_pack_review(*, snapshot_id: int, entity_id: int, status: str, comment: str = "", actor=None) -> dict:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in REVIEW_STATUSES:
        raise ValueError("Unsupported evidence pack review status.")

    snapshot = ReportFreezeSnapshot.objects.select_related("frozen_by").get(
        pk=snapshot_id,
        report_code=REPORT_CODE,
        entity_id=entity_id,
        isactive=True,
    )
    payload = snapshot.payload if isinstance(snapshot.payload, dict) else {}
    review = dict(payload.get("review") or {})
    previous_status = review.get("status") or "prepared"
    review.update(
        {
            "status": normalized_status,
            "status_label": normalized_status.replace("_", " ").title(),
            "comment": str(comment or "").strip(),
        }
    )
    actor_payload = _actor_payload(actor)
    now_value = timezone.now().isoformat()
    if normalized_status == "reviewed":
        review.update({"reviewed_by": actor_payload, "reviewed_at": now_value})
    if normalized_status == "approved":
        review.update({"approved_by": actor_payload, "approved_at": now_value})
    snapshot.payload = {**payload, "review": review}
    snapshot.save(update_fields=["payload"])
    data = serialize_evidence_pack_snapshot(snapshot, include_payload=True)
    data["previous_status"] = previous_status
    return data


def serialize_evidence_pack_snapshot(snapshot: ReportFreezeSnapshot, *, include_payload: bool = False) -> dict:
    payload = snapshot.payload if isinstance(snapshot.payload, dict) else {}
    review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
    audit_pack = ((payload.get("snapshot") or {}).get("audit_pack") or {}) if isinstance(payload.get("snapshot"), dict) else {}
    data = {
        "id": snapshot.id,
        "report_code": snapshot.report_code,
        "version": snapshot.version,
        "status": review.get("status") or "prepared",
        "status_label": review.get("status_label") or "Prepared",
        "generated_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "generated_by": _actor_payload(snapshot.frozen_by),
        "scope": {
            "entity": snapshot.entity_id,
            "entityfinid": snapshot.entityfinid_id,
            "subentity": snapshot.subentity_id,
        },
        "pack_status": audit_pack.get("status"),
        "pack_status_label": audit_pack.get("status_label"),
        "summary": audit_pack.get("summary") or {},
        "review": review,
    }
    if include_payload:
        data["payload"] = payload.get("snapshot") or {}
    return data


def _actor_payload(user) -> dict | None:
    if not user:
        return None
    return {
        "id": getattr(user, "id", None),
        "username": getattr(user, "username", "") or "",
        "name": getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or "",
    }


def _evidence_row_map(rows: list[dict]) -> dict[str, dict]:
    mapped = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        key = f"{row.get('section') or '-'}::{row.get('label') or index}"
        mapped[key] = {
            "key": key,
            "section": row.get("section") or "-",
            "label": row.get("label") or "-",
            "value": row.get("value"),
            "status": row.get("status") or "-",
            "note": row.get("note") or "",
        }
    return mapped


def _row_signature(row: dict) -> tuple:
    return (row.get("value"), row.get("status"), row.get("note"))


def _comparison_row(key: str, latest: dict, previous: dict) -> dict:
    return {
        "key": key,
        "section": latest.get("section") or previous.get("section") or "-",
        "label": latest.get("label") or previous.get("label") or "-",
        "previous": previous,
        "latest": latest,
    }


def _summary_delta(latest_pack: dict, previous_pack: dict, key: str) -> int:
    latest_summary = latest_pack.get("summary") if isinstance(latest_pack.get("summary"), dict) else {}
    previous_summary = previous_pack.get("summary") if isinstance(previous_pack.get("summary"), dict) else {}
    return int(latest_summary.get(key) or 0) - int(previous_summary.get(key) or 0)
