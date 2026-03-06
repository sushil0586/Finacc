from __future__ import annotations

from typing import Any, Optional
from django.utils import timezone

from sales.models.sales_compliance import (
    SalesComplianceActionLog,
    SalesComplianceExceptionQueue,
)


class ComplianceAuditService:
    @staticmethod
    def log_action(
        *,
        invoice,
        action_type: str,
        outcome: str,
        user=None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        request_json: Optional[dict] = None,
        response_json: Optional[dict] = None,
    ) -> None:
        SalesComplianceActionLog.objects.create(
            invoice=invoice,
            action_type=action_type,
            outcome=outcome,
            created_by=user,
            error_code=error_code,
            error_message=error_message,
            request_json=request_json,
            response_json=response_json,
        )

    @staticmethod
    def open_exception(
        *,
        invoice,
        exception_type: str,
        error_message: str,
        severity: str = SalesComplianceExceptionQueue.Severity.HIGH,
        error_code: Optional[str] = None,
        payload_json: Optional[dict] = None,
    ) -> None:
        now = timezone.now()
        obj, created = SalesComplianceExceptionQueue.objects.get_or_create(
            invoice=invoice,
            exception_type=exception_type,
            status=SalesComplianceExceptionQueue.Status.OPEN,
            defaults={
                "severity": severity,
                "error_code": error_code,
                "error_message": error_message,
                "payload_json": payload_json,
                "first_seen_at": now,
                "last_seen_at": now,
            },
        )
        if not created:
            obj.error_code = error_code
            obj.error_message = error_message
            obj.payload_json = payload_json
            obj.last_seen_at = now
            obj.retry_count = int(obj.retry_count or 0) + 1
            obj.save(update_fields=["error_code", "error_message", "payload_json", "last_seen_at", "retry_count"])

    @staticmethod
    def resolve_exception(*, invoice, exception_type: str, user=None) -> None:
        now = timezone.now()
        SalesComplianceExceptionQueue.objects.filter(
            invoice=invoice,
            exception_type=exception_type,
            status__in=[SalesComplianceExceptionQueue.Status.OPEN, SalesComplianceExceptionQueue.Status.IN_PROGRESS],
        ).update(
            status=SalesComplianceExceptionQueue.Status.RESOLVED,
            resolved_at=now,
            resolved_by=user,
            last_seen_at=now,
        )
