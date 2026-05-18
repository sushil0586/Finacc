from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from Authentication.models import User
from entity.approval_workflow_service import ApprovalWorkflowService
from entity.notification_service import NotificationService
from hrms.models import LeaveApplication
from hrms.services.leave_balance_service import LeaveBalanceService

ZERO2 = Decimal("0.00")


class LeaveApprovalService:
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

    @classmethod
    @transaction.atomic
    def approve(cls, *, application: LeaveApplication, approver, approved_days: Decimal | None = None, manager_note: str = "") -> LeaveApplication:
        ApprovalWorkflowService.approve(
            instance=application,
            workflow_key="leave_application",
            actor_id=getattr(approver, "id", None),
            remarks=manager_note,
        )
        impact = LeaveBalanceService.consume_for_application(application=application, approved_days=approved_days)
        application.status = LeaveApplication.Status.APPROVED
        application.approval_status = LeaveApplication.ApprovalStatus.APPROVED
        application.approved_days = Decimal(str(impact["approved_days"]))
        application.paid_days = Decimal(str(impact["paid_days"]))
        application.unpaid_days = Decimal(str(impact["unpaid_days"]))
        application.approved_by = approver
        application.approved_at = timezone.now()
        application.manager_note = manager_note or application.manager_note
        application.payroll_impact_json = {
            "paid_leave_days": impact["paid_days"],
            "unpaid_leave_days": impact["unpaid_days"],
            "lop_days": impact["unpaid_days"],
            "ledger_id": impact.get("ledger_id"),
            "snapshot_id": impact.get("snapshot_id"),
            "trace": impact.get("trace", {}),
        }
        application.application_trace_json = {
            **(application.application_trace_json or {}),
            "approval_trace": impact,
        }
        application.save()
        NotificationService.emit(
            instance=application,
            workflow_key="leave_application",
            event_code="LEAVE_APPROVED",
            title="Leave Approved",
            message=f"Leave application for {getattr(application.contract, 'contract_code', '')} was approved.",
            users=cls._notification_users_for_application(application, getattr(approver, "id", None)),
            actor=approver,
            target_url=NotificationService.default_target_url(workflow_key="leave_application", instance=application),
            payload={"approved_days": str(application.approved_days), "payroll_impact": application.payroll_impact_json},
        )
        return application

    @classmethod
    @transaction.atomic
    def reject(cls, *, application: LeaveApplication, approver, manager_note: str = "") -> LeaveApplication:
        ApprovalWorkflowService.reject(
            instance=application,
            workflow_key="leave_application",
            actor_id=getattr(approver, "id", None),
            remarks=manager_note,
        )
        application.status = LeaveApplication.Status.REJECTED
        application.approval_status = LeaveApplication.ApprovalStatus.REJECTED
        application.rejected_by = approver
        application.rejected_at = timezone.now()
        application.manager_note = manager_note or application.manager_note
        application.save()
        NotificationService.emit(
            instance=application,
            workflow_key="leave_application",
            event_code="LEAVE_REJECTED",
            title="Leave Rejected",
            message=f"Leave application for {getattr(application.contract, 'contract_code', '')} was rejected.",
            users=cls._notification_users_for_application(application, getattr(approver, "id", None)),
            actor=approver,
            target_url=NotificationService.default_target_url(workflow_key="leave_application", instance=application),
            payload={"manager_note": application.manager_note},
        )
        return application
