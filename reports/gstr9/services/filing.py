from __future__ import annotations

from django.utils import timezone

from reports.gstr9.services.freeze import Gstr9FreezeService
from reports.gstr9.services.portal_gateway import build_gstr9_portal_gateway
from reports.gstr9.selectors.scope import Gstr9FilterParams
from reports.models import ReportFilingRun


class Gstr9FilingService:
    report_code = "gstr9"

    def __init__(self, *, freeze_service: Gstr9FreezeService | None = None, portal_gateway=None):
        self.freeze_service = freeze_service or Gstr9FreezeService()
        self.portal_gateway = portal_gateway or build_gstr9_portal_gateway()

    def prepare(self, scope: Gstr9FilterParams, *, freeze_version: int, user=None) -> dict:
        if not scope.entityfinid_id:
            raise ValueError("entityfinid is required.")
        snapshot = self.freeze_service.get_snapshot(scope, version=freeze_version)
        if not snapshot:
            raise LookupError(f"Frozen snapshot not found for freeze_version={freeze_version}.")

        warnings = (snapshot.get("payload", {}).get("validations") or [])
        blocking_errors = [row for row in warnings if str(row.get("severity")) == "error"]
        filing_payload = {
            "schema_version": "gstr9.filing.v1",
            "prepared_at": timezone.now().isoformat(),
            "freeze_version": snapshot["version"],
            "freeze_id": snapshot["id"],
            "summary": snapshot.get("payload", {}).get("summary") or {},
            "validations": warnings,
            "validation_summary": {
                "warning_count": len(warnings),
                "blocking_error_count": len(blocking_errors),
            },
            "can_submit": len(blocking_errors) == 0,
        }
        run = ReportFilingRun.objects.create(
            report_code=self.report_code,
            entity_id=scope.entity_id,
            entityfinid_id=scope.entityfinid_id,
            subentity_id=scope.subentity_id,
            freeze_snapshot_id=snapshot["id"],
            status=ReportFilingRun.Status.PREPARED,
            payload=filing_payload,
            prepared_by=user if getattr(user, "is_authenticated", False) else None,
            prepared_at=timezone.now(),
        )
        return self._serialize(run)

    def submit(self, scope: Gstr9FilterParams, *, filing_id: int, user=None, submission_data: dict | None = None) -> dict:
        if not scope.entityfinid_id:
            raise ValueError("entityfinid is required.")
        run = self._scope_queryset(scope).filter(id=filing_id).first()
        if not run:
            raise LookupError(f"Filing run not found for filing_id={filing_id}.")
        payload = run.payload or {}
        if not payload.get("can_submit", True):
            raise ValueError("Filing run has blocking validation errors. Resolve them before submit.")
        if run.status != ReportFilingRun.Status.SUBMITTED:
            submit_result = self.portal_gateway.submit(filing_run=run, submission_data=submission_data or {})
            if submit_result.status != "submitted":
                raise ValueError("Portal submission failed.")
            run.status = ReportFilingRun.Status.SUBMITTED
            run.submitted_by = user if getattr(user, "is_authenticated", False) else None
            run.submitted_at = timezone.now()
            run.portal_provider = submit_result.provider
            run.portal_reference = submit_result.portal_reference
            payload["submission"] = {
                "provider": submit_result.provider,
                "status": submit_result.status,
                "submitted_at": run.submitted_at.isoformat() if run.submitted_at else None,
                "portal_reference": submit_result.portal_reference,
                "portal_payload": submit_result.payload,
            }
            run.payload = payload
            run.save(
                update_fields=[
                    "status",
                    "submitted_by",
                    "submitted_at",
                    "portal_provider",
                    "portal_reference",
                    "payload",
                    "updated_at",
                ]
            )
        return self._serialize(run)

    def status(self, scope: Gstr9FilterParams, *, filing_id: int | None = None, limit: int = 10):
        if not scope.entityfinid_id:
            raise ValueError("entityfinid is required.")
        qs = self._scope_queryset(scope).order_by("-id")
        if filing_id is not None:
            run = qs.filter(id=filing_id).first()
            if not run:
                return None
            return self._serialize(run)
        return [self._serialize(row) for row in qs[:limit]]

    def _scope_queryset(self, scope: Gstr9FilterParams):
        return ReportFilingRun.objects.filter(
            report_code=self.report_code,
            entity_id=scope.entity_id,
            entityfinid_id=scope.entityfinid_id,
            subentity_id=scope.subentity_id,
        )

    def _serialize(self, run: ReportFilingRun) -> dict:
        return {
            "id": run.id,
            "report_code": run.report_code,
            "status": run.status,
            "entity": run.entity_id,
            "entityfinid": run.entityfinid_id,
            "subentity": run.subentity_id,
            "freeze_id": run.freeze_snapshot_id,
            "freeze_version": run.freeze_snapshot.version,
            "prepared_at": run.prepared_at.isoformat() if run.prepared_at else None,
            "submitted_at": run.submitted_at.isoformat() if run.submitted_at else None,
            "prepared_by": run.prepared_by_id,
            "submitted_by": run.submitted_by_id,
            "portal_provider": run.portal_provider or "",
            "portal_reference": run.portal_reference or "",
            "payload": run.payload or {},
        }
