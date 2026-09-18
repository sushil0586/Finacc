from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from reports.gst_compliance.contracts import GstComplianceScope
from reports.models import GstCompliancePeriodLifecycle, GstCompliancePeriodLifecycleAudit


@dataclass(frozen=True)
class LifecycleTransition:
    action: str
    target_status: str
    lock_state: bool
    timestamp_field: str
    actor_field: str
    requires_note: bool = False


class GstCompliancePeriodLifecycleService:
    TRANSITIONS: dict[str, LifecycleTransition] = {
        "prepare": LifecycleTransition(
            action="prepare",
            target_status=GstCompliancePeriodLifecycle.Status.PREPARED,
            lock_state=False,
            timestamp_field="prepared_at",
            actor_field="prepared_by",
        ),
        "submit_review": LifecycleTransition(
            action="submit_review",
            target_status=GstCompliancePeriodLifecycle.Status.IN_REVIEW,
            lock_state=False,
            timestamp_field="reviewed_at",
            actor_field="reviewed_by",
        ),
        "freeze": LifecycleTransition(
            action="freeze",
            target_status=GstCompliancePeriodLifecycle.Status.FROZEN,
            lock_state=True,
            timestamp_field="frozen_at",
            actor_field="frozen_by",
            requires_note=True,
        ),
        "file": LifecycleTransition(
            action="file",
            target_status=GstCompliancePeriodLifecycle.Status.FILED,
            lock_state=True,
            timestamp_field="filed_at",
            actor_field="filed_by",
        ),
        "reopen": LifecycleTransition(
            action="reopen",
            target_status=GstCompliancePeriodLifecycle.Status.AMENDMENT_OPEN,
            lock_state=False,
            timestamp_field="reopened_at",
            actor_field="reopened_by",
            requires_note=True,
        ),
    }

    TERMINAL_LOCKED_STATUSES = {
        GstCompliancePeriodLifecycle.Status.FROZEN,
        GstCompliancePeriodLifecycle.Status.FILED,
    }

    def get(self, *, scope: GstComplianceScope, gstin: str | None) -> GstCompliancePeriodLifecycle | None:
        if not self._has_minimum_scope(scope=scope, gstin=gstin):
            return None
        return (
            GstCompliancePeriodLifecycle.objects.filter(
                entity_id=scope.entity_id,
                entityfinid_id=scope.entityfinid_id,
                subentity_id=scope.subentity_id,
                gstin=gstin,
                return_period=scope.return_period,
                isactive=True,
            )
            .order_by("-updated_at", "-id")
            .first()
        )

    @transaction.atomic
    def ensure(self, *, scope: GstComplianceScope, gstin: str, portal_return_period: str | None = None) -> GstCompliancePeriodLifecycle:
        self._validate_minimum_scope(scope=scope, gstin=gstin)
        lifecycle, _created = GstCompliancePeriodLifecycle.objects.get_or_create(
            entity_id=scope.entity_id,
            entityfinid_id=scope.entityfinid_id,
            subentity_id=scope.subentity_id,
            gstin=gstin,
            return_period=scope.return_period,
            defaults={
                "portal_return_period": portal_return_period or "",
                "status": GstCompliancePeriodLifecycle.Status.OPEN,
                "locked": False,
            },
        )
        if portal_return_period and lifecycle.portal_return_period != portal_return_period:
            lifecycle.portal_return_period = portal_return_period
            lifecycle.save(update_fields=["portal_return_period", "updated_at"])
        return lifecycle

    @transaction.atomic
    def transition(
        self,
        *,
        scope: GstComplianceScope,
        gstin: str,
        action: str,
        actor=None,
        portal_return_period: str | None = None,
        checklist: dict[str, Any] | None = None,
        evidence: list[dict[str, Any]] | None = None,
        note: str = "",
        portal_reference: str = "",
    ) -> GstCompliancePeriodLifecycle:
        action = (action or "").strip().lower()
        transition = self.TRANSITIONS.get(action)
        if not transition:
            raise ValidationError({"action": [f"Unsupported GST lifecycle action: {action or '-'}"]})
        note = (note or "").strip()
        if transition.requires_note and not note:
            raise ValidationError({"note": ["A reason/note is required for this lifecycle action."]})

        lifecycle = self.ensure(scope=scope, gstin=gstin, portal_return_period=portal_return_period)
        self._validate_transition(lifecycle=lifecycle, transition=transition)
        old_data = self.serialize(lifecycle)

        lifecycle.status = transition.target_status
        lifecycle.locked = transition.lock_state
        if checklist is not None:
            lifecycle.checklist = checklist
        if evidence is not None:
            lifecycle.evidence = evidence
        if portal_reference:
            lifecycle.portal_reference = portal_reference.strip()
        if note:
            lifecycle.notes = note
        now = timezone.now()
        setattr(lifecycle, transition.timestamp_field, now)
        if actor and getattr(actor, "is_authenticated", False):
            setattr(lifecycle, transition.actor_field, actor)
        lifecycle.save()

        GstCompliancePeriodLifecycleAudit.objects.create(
            lifecycle=lifecycle,
            action=transition.action,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            old_data=old_data,
            new_data=self.serialize(lifecycle),
            note=note,
        )
        return lifecycle

    def serialize(self, lifecycle: GstCompliancePeriodLifecycle | None) -> dict[str, Any] | None:
        if not lifecycle:
            return None
        return {
            "id": lifecycle.pk,
            "entity": lifecycle.entity_id,
            "entityfinid": lifecycle.entityfinid_id,
            "subentity": lifecycle.subentity_id,
            "gstin": lifecycle.gstin,
            "return_period": lifecycle.return_period,
            "portal_return_period": lifecycle.portal_return_period,
            "status": lifecycle.status,
            "label": self._status_label(lifecycle.status),
            "locked": lifecycle.locked,
            "can_reopen": lifecycle.status in self.TERMINAL_LOCKED_STATUSES,
            "checklist": lifecycle.checklist or {},
            "evidence": lifecycle.evidence or [],
            "notes": lifecycle.notes,
            "portal_reference": lifecycle.portal_reference,
            "prepared_at": self._iso(lifecycle.prepared_at),
            "reviewed_at": self._iso(lifecycle.reviewed_at),
            "frozen_at": self._iso(lifecycle.frozen_at),
            "filed_at": self._iso(lifecycle.filed_at),
            "reopened_at": self._iso(lifecycle.reopened_at),
            "updated_at": self._iso(lifecycle.updated_at),
        }

    def _validate_transition(self, *, lifecycle: GstCompliancePeriodLifecycle, transition: LifecycleTransition) -> None:
        current = lifecycle.status
        if transition.action == "prepare" and current == GstCompliancePeriodLifecycle.Status.FILED:
            raise ValidationError({"status": ["Filed GST periods must be reopened before preparing again."]})
        if transition.action == "submit_review" and current not in {
            GstCompliancePeriodLifecycle.Status.PREPARED,
            GstCompliancePeriodLifecycle.Status.IN_REVIEW,
            GstCompliancePeriodLifecycle.Status.AMENDMENT_OPEN,
        }:
            raise ValidationError({"status": ["Only prepared or amendment-open GST periods can be submitted for review."]})
        if transition.action == "freeze" and current not in {
            GstCompliancePeriodLifecycle.Status.PREPARED,
            GstCompliancePeriodLifecycle.Status.IN_REVIEW,
            GstCompliancePeriodLifecycle.Status.FROZEN,
            GstCompliancePeriodLifecycle.Status.AMENDMENT_OPEN,
        }:
            raise ValidationError({"status": ["Only prepared, in-review, or amendment-open GST periods can be frozen."]})
        if transition.action == "file" and current not in {
            GstCompliancePeriodLifecycle.Status.FROZEN,
            GstCompliancePeriodLifecycle.Status.FILED,
        }:
            raise ValidationError({"status": ["GST period must be frozen before marking it filed."]})
        if transition.action == "reopen" and current not in self.TERMINAL_LOCKED_STATUSES:
            raise ValidationError({"status": ["Only frozen or filed GST periods can be reopened for amendment."]})

    def _has_minimum_scope(self, *, scope: GstComplianceScope, gstin: str | None) -> bool:
        return bool(scope.entity_id and scope.entityfinid_id and scope.return_period and gstin)

    def _validate_minimum_scope(self, *, scope: GstComplianceScope, gstin: str | None) -> None:
        if not self._has_minimum_scope(scope=scope, gstin=gstin):
            raise ValidationError({"scope": ["entity, entityfinid, GSTIN, and return_period are required."]})

    def _status_label(self, status: str) -> str:
        return dict(GstCompliancePeriodLifecycle.Status.choices).get(status, status.replace("_", " ").title())

    def _iso(self, value) -> str | None:
        return value.isoformat() if value else None
