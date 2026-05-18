from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from entity.approval_workflow_service import ApprovalWorkflowService
from entity.notification_service import NotificationService
from Authentication.models import User
from hrms.models import HrEmploymentContract, LeaveApplication, LeaveType
from hrms.services.leave_rule_engine import LeaveRuleEngine

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def _decimal(value: Any, default: Decimal = ZERO2) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default)).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return default


class LeaveApplicationService:
    @staticmethod
    def _notification_users_for_application(application: LeaveApplication, *extra_user_ids: int | None):
        user_ids: set[int] = set()
        for field_name in ("applied_by_id", "approved_by_id", "rejected_by_id", "cancelled_by_id", "locked_by_id"):
            value = getattr(application, field_name, None)
            if value:
                user_ids.add(int(value))
        linked_user_id = getattr(getattr(application.contract, "employee", None), "linked_user_id", None)
        if linked_user_id:
            user_ids.add(int(linked_user_id))
        for value in extra_user_ids:
            if value:
                user_ids.add(int(value))
        return User.objects.filter(pk__in=sorted(user_ids))

    @staticmethod
    def _coerce_date(value: Any) -> date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    @staticmethod
    def list_applications(
        *,
        entity_id: int,
        subentity_id: int | None = None,
        contract_id: str | None = None,
        status_value: str | None = None,
        employee_user_id: int | None = None,
    ):
        queryset = LeaveApplication.objects.select_related(
            "contract",
            "contract__employee",
            "leave_type",
            "leave_policy",
        ).filter(entity_id=entity_id, deleted_at__isnull=True)
        if subentity_id is not None:
            queryset = queryset.filter(Q(subentity_id=subentity_id) | Q(subentity_id__isnull=True))
        if contract_id:
            queryset = queryset.filter(contract_id=contract_id)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if employee_user_id is not None:
            queryset = queryset.filter(contract__employee__linked_user_id=employee_user_id)
        return queryset.order_by("-start_date", "-created_at")

    @staticmethod
    def _requested_days(*, start_date: date, end_date: date, payload: dict[str, Any]) -> Decimal:
        override = payload.get("requested_days")
        if override not in (None, ""):
            return _decimal(override)
        span = max((end_date - start_date).days + 1, 1)
        return Decimal(span).quantize(Q2, rounding=ROUND_HALF_UP)

    @classmethod
    @transaction.atomic
    def create_application(cls, *, attrs: dict[str, Any], actor=None) -> LeaveApplication:
        contract: HrEmploymentContract = attrs["contract"]
        leave_type: LeaveType = attrs["leave_type"]
        start_date = cls._coerce_date(attrs["start_date"])
        end_date = cls._coerce_date(attrs["end_date"])
        leave_policy = attrs.get("leave_policy") or LeaveRuleEngine.resolve_leave_policy(contract=contract, as_of_date=end_date)
        requested_days = cls._requested_days(start_date=start_date, end_date=end_date, payload=attrs)
        application = LeaveApplication(
            entity_id=contract.entity_id,
            subentity_id=contract.subentity_id,
            contract=contract,
            leave_policy=leave_policy,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            requested_days=requested_days,
            status=attrs.get("status") or LeaveApplication.Status.SUBMITTED,
            approval_status=LeaveApplication.ApprovalStatus.PENDING_APPROVAL,
            reason=attrs.get("reason", ""),
            applied_by=actor,
            submitted_at=timezone.now(),
            application_trace_json={
                "requested_days": str(requested_days),
                "created_via": attrs.get("created_via", "service"),
            },
        )
        application.save()
        ApprovalWorkflowService.submit_for_approval(
            instance=application,
            workflow_key="leave_application",
            actor_id=getattr(actor, "id", None),
            remarks=application.reason,
            title=f"Leave {getattr(contract, 'contract_code', '')}",
        )
        NotificationService.emit(
            instance=application,
            workflow_key="leave_application",
            event_code="LEAVE_APPLIED",
            title="Leave Application Submitted",
            message=f"Leave application for {getattr(contract, 'contract_code', '')} was submitted.",
            users=cls._notification_users_for_application(application, getattr(actor, "id", None)),
            actor=actor,
            target_url=NotificationService.default_target_url(workflow_key="leave_application", instance=application),
            payload={"requested_days": str(requested_days)},
        )
        return application

    @classmethod
    @transaction.atomic
    def cancel_application(cls, *, application: LeaveApplication, actor_id: int | None, manager_note: str = "") -> LeaveApplication:
        if application.status in {LeaveApplication.Status.APPROVED, LeaveApplication.Status.CANCELLED}:
            raise ValueError("Approved or cancelled leave applications cannot be cancelled.")
        ApprovalWorkflowService.cancel(
            instance=application,
            workflow_key="leave_application",
            actor_id=actor_id,
            remarks=manager_note,
        )
        application.status = LeaveApplication.Status.CANCELLED
        application.cancelled_by_id = actor_id
        application.cancelled_at = timezone.now()
        application.manager_note = manager_note or application.manager_note
        application.save(update_fields=["status", "cancelled_by", "cancelled_at", "manager_note", "updated_at"])
        return application
