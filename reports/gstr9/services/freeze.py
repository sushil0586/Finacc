from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from entity.models import EntityFinancialYear
from reports.gstr9.services.meta import PHASE0_TABLE_CATALOG
from reports.gstr9.services.report import Gstr9ReportService
from reports.gstr9.selectors.scope import Gstr9FilterParams
from reports.models import ReportFreezeSnapshot


class Gstr9FreezeService:
    report_code = "gstr9"

    def __init__(self, *, report_service: Gstr9ReportService | None = None):
        self.report_service = report_service or Gstr9ReportService()

    def freeze(self, scope: Gstr9FilterParams, *, user=None) -> dict:
        if not scope.entityfinid_id:
            raise ValueError("entityfinid is required.")

        with transaction.atomic():
            EntityFinancialYear.objects.select_for_update().get(
                id=scope.entityfinid_id,
                entity_id=scope.entity_id,
            )
            current_version = (
                self._scope_queryset(scope)
                .order_by("-version")
                .values_list("version", flat=True)
                .first()
                or 0
            )
            snapshot = ReportFreezeSnapshot.objects.create(
                report_code=self.report_code,
                entity_id=scope.entity_id,
                entityfinid_id=scope.entityfinid_id,
                subentity_id=scope.subentity_id,
                version=current_version + 1,
                payload=self._build_snapshot_payload(scope),
                frozen_by=user if getattr(user, "is_authenticated", False) else None,
            )
        return self._serialize_snapshot(snapshot, include_payload=True)

    def latest(self, scope: Gstr9FilterParams) -> dict | None:
        if not scope.entityfinid_id:
            raise ValueError("entityfinid is required.")
        snapshot = self._scope_queryset(scope).order_by("-version", "-id").first()
        if not snapshot:
            return None
        return self._serialize_snapshot(snapshot, include_payload=True)

    def get_snapshot(self, scope: Gstr9FilterParams, *, version: int | None = None) -> dict | None:
        if not scope.entityfinid_id:
            raise ValueError("entityfinid is required.")
        qs = self._scope_queryset(scope)
        if version is None:
            snapshot = qs.order_by("-version", "-id").first()
        else:
            snapshot = qs.filter(version=version).order_by("-id").first()
        if not snapshot:
            return None
        return self._serialize_snapshot(snapshot, include_payload=True)

    def history(
        self,
        scope: Gstr9FilterParams,
        *,
        limit: int | None = None,
        include_payload: bool = False,
    ) -> list[dict]:
        if not scope.entityfinid_id:
            raise ValueError("entityfinid is required.")
        qs = self._scope_queryset(scope).order_by("-version", "-id")
        if limit:
            qs = qs[:limit]
        return [self._serialize_snapshot(row, include_payload=include_payload) for row in qs]

    def _scope_queryset(self, scope: Gstr9FilterParams):
        return ReportFreezeSnapshot.objects.filter(
            report_code=self.report_code,
            entity_id=scope.entity_id,
            entityfinid_id=scope.entityfinid_id,
            subentity_id=scope.subentity_id,
        )

    def _build_snapshot_payload(self, scope: Gstr9FilterParams) -> dict:
        summary = self.report_service.summary(scope)
        table_codes = [row["code"] for row in PHASE0_TABLE_CATALOG]
        tables = {code: self.report_service.table(scope, code) for code in table_codes}
        validations = self.report_service.validations(scope)
        payload = {
            "schema_version": "gstr9.freeze.v1",
            "generated_at": timezone.now().isoformat(),
            "scope": {
                "entity": scope.entity_id,
                "entityfinid": scope.entityfinid_id,
                "subentity": scope.subentity_id,
            },
            "summary": summary,
            "tables": tables,
            "validations": validations,
        }
        return self._json_safe(payload)

    def _serialize_snapshot(self, snapshot: ReportFreezeSnapshot, *, include_payload: bool) -> dict:
        data = {
            "id": snapshot.id,
            "report_code": snapshot.report_code,
            "version": snapshot.version,
            "frozen_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
            "scope": {
                "entity": snapshot.entity_id,
                "entityfinid": snapshot.entityfinid_id,
                "subentity": snapshot.subentity_id,
            },
            "frozen_by": snapshot.frozen_by_id,
        }
        if include_payload:
            data["payload"] = snapshot.payload or {}
        return data

    def _json_safe(self, value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: self._json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        return value
