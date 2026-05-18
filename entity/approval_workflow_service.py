from __future__ import annotations

from dataclasses import dataclass

from Authentication.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db import models
from django.utils import timezone

from entity.models import ApprovalActionLog, ApprovalRequest, ApprovalStep, EntityApprovalPolicy
from entity.notification_service import NotificationService


@dataclass(frozen=True)
class ApprovalResolution:
    request: ApprovalRequest
    status: str


class ApprovalWorkflowService:
    STATUS = ApprovalRequest.Status

    WORKFLOW_KEY_TO_POLICY_KEY = {
        "payroll_run": EntityApprovalPolicy.PolicyKey.PAYROLL_RUN,
        "payroll_payment_batch": EntityApprovalPolicy.PolicyKey.PAYROLL_PAYMENT_BATCH,
        "fnf_settlement": EntityApprovalPolicy.PolicyKey.FNF_SETTLEMENT,
        "contract_tax_declaration": EntityApprovalPolicy.PolicyKey.CONTRACT_TAX_DECLARATION,
        "leave_application": EntityApprovalPolicy.PolicyKey.LEAVE_APPLICATION,
    }

    WORKFLOW_LABELS = {
        "payroll_run": "Payroll Run",
        "payroll_payment_batch": "Payment Batch",
        "fnf_settlement": "FnF Settlement",
        "contract_tax_declaration": "Tax Declaration",
        "leave_application": "Leave Application",
    }

    @classmethod
    def _content_type(cls, instance):
        return ContentType.objects.get_for_model(instance.__class__)

    @classmethod
    def _find_request(cls, *, instance, workflow_key: str) -> ApprovalRequest | None:
        return (
            ApprovalRequest.objects.filter(
                content_type=cls._content_type(instance),
                object_id=str(instance.pk),
                workflow_key=workflow_key,
                isactive=True,
            )
            .order_by("-id")
            .first()
        )

    @classmethod
    def get_or_create_request(
        cls,
        *,
        instance,
        workflow_key: str,
        title: str = "",
    ) -> ApprovalRequest:
        request = cls._find_request(instance=instance, workflow_key=workflow_key)
        if request:
            return request
        entity_id = getattr(instance, "entity_id", None)
        if entity_id is None:
            raise ValueError("Approval workflow requires an entity-scoped object.")
        request = ApprovalRequest.objects.create(
            entity_id=entity_id,
            subentity_id=getattr(instance, "subentity_id", None),
            content_type=cls._content_type(instance),
            object_id=str(instance.pk),
            workflow_key=workflow_key,
            title=title or cls.default_title(instance=instance),
        )
        return request

    @classmethod
    def default_title(cls, *, instance) -> str:
        for field_name in ("run_number", "batch_number", "settlement_number", "contract_code", "payslip_number"):
            value = getattr(instance, field_name, "")
            if value:
                return str(value)
        return f"{instance.__class__.__name__}:{instance.pk}"

    @classmethod
    def _workflow_label(cls, *, workflow_key: str) -> str:
        return cls.WORKFLOW_LABELS.get(workflow_key, workflow_key.replace("_", " ").title())

    @classmethod
    def _title_for_instance(cls, *, instance, workflow_key: str) -> str:
        return cls.default_title(instance=instance) or f"{cls._workflow_label(workflow_key=workflow_key)} {instance.pk}"

    @classmethod
    def _resolve_actor(cls, *, actor_id: int | None) -> User | None:
        if not actor_id:
            return None
        return User.objects.filter(pk=actor_id).first()

    @classmethod
    def _related_employee_user_id(cls, *, instance) -> int | None:
        if hasattr(instance, "employee_user_id"):
            return getattr(instance, "employee_user_id", None)
        contract_profile = getattr(instance, "contract_payroll_profile", None)
        if contract_profile is not None and hasattr(contract_profile, "employee_user_id"):
            return contract_profile.employee_user_id
        contract = getattr(instance, "contract", None)
        employee = getattr(contract, "employee", None) if contract is not None else None
        return getattr(employee, "linked_user_id", None)

    @classmethod
    def _recipient_ids(cls, *, instance, workflow_key: str, actor_id: int | None) -> list[int]:
        user_ids: set[int] = set()
        for field_name in (
            "created_by_id",
            "submitted_by_id",
            "requested_by_id",
            "approved_by_id",
            "rejected_by_id",
            "cancelled_by_id",
            "applied_by_id",
        ):
            value = getattr(instance, field_name, None)
            if value:
                user_ids.add(int(value))
        employee_user_id = cls._related_employee_user_id(instance=instance)
        if employee_user_id:
            user_ids.add(int(employee_user_id))
        if actor_id:
            user_ids.add(int(actor_id))
        if workflow_key == "payroll_payment_batch":
            run = getattr(instance, "payroll_run", None)
            if run is not None:
                for field_name in ("created_by_id", "submitted_by_id", "approved_by_id"):
                    value = getattr(run, field_name, None)
                    if value:
                        user_ids.add(int(value))
        return sorted(user_ids)

    @classmethod
    def _emit_status_notification(
        cls,
        *,
        instance,
        workflow_key: str,
        event_suffix: str,
        actor_id: int | None,
        remarks: str = "",
        status_value: str,
    ) -> None:
        actor = cls._resolve_actor(actor_id=actor_id)
        user_ids = cls._recipient_ids(instance=instance, workflow_key=workflow_key, actor_id=actor_id)
        users = User.objects.filter(pk__in=user_ids) if user_ids else User.objects.none()
        label = cls._workflow_label(workflow_key=workflow_key)
        doc_title = cls._title_for_instance(instance=instance, workflow_key=workflow_key)
        message = f"{label} {doc_title} moved to {status_value.replace('_', ' ').title()}."
        if remarks:
            message = f"{message} {remarks}".strip()
        NotificationService.emit(
            instance=instance,
            workflow_key=workflow_key,
            event_code=f"{workflow_key.upper()}_{event_suffix}",
            title=f"{label} {status_value.replace('_', ' ').title()}",
            message=message,
            users=users,
            actor=actor,
            target_url=NotificationService.default_target_url(workflow_key=workflow_key, instance=instance),
            payload={
                "workflow_key": workflow_key,
                "status": status_value,
                "document_title": doc_title,
                "remarks": remarks,
            },
        )

    @classmethod
    def resolve_policy(cls, *, instance, workflow_key: str) -> EntityApprovalPolicy | None:
        policy_key = cls.WORKFLOW_KEY_TO_POLICY_KEY.get(workflow_key, workflow_key)
        entity_id = getattr(instance, "entity_id", None)
        subentity_id = getattr(instance, "subentity_id", None)
        queryset = EntityApprovalPolicy.objects.filter(
            entity_id=entity_id,
            policy_key=policy_key,
            isactive=True,
            status=EntityApprovalPolicy.Status.ACTIVE,
        )
        if subentity_id is not None:
            queryset = queryset.filter(models.Q(subentity_id=subentity_id) | models.Q(subentity__isnull=True))
        return queryset.order_by("-subentity_id", "-id").first()

    @classmethod
    def _ensure_steps(cls, *, request: ApprovalRequest, policy: EntityApprovalPolicy | None) -> None:
        if request.steps.exists():
            return
        min_approvers = max(int(getattr(policy, "min_approvers", 1) or 1), 1)
        approver_permissions = list(getattr(policy, "approver_permissions", []) or [])
        approver_roles = list(getattr(policy, "approver_roles", []) or [])
        for index in range(min_approvers):
            ApprovalStep.objects.create(
                approval_request=request,
                step_order=index + 1,
                step_name=f"Approval Step {index + 1}",
                approver_permission=approver_permissions[index] if index < len(approver_permissions) else "",
                approver_role=approver_roles[index] if index < len(approver_roles) else "",
            )

    @classmethod
    def _log(
        cls,
        *,
        request: ApprovalRequest,
        action: str,
        previous_status: str,
        new_status: str,
        actor_id: int | None,
        remarks: str = "",
        step: ApprovalStep | None = None,
        payload: dict | None = None,
    ) -> None:
        ApprovalActionLog.objects.create(
            approval_request=request,
            approval_step=step,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            acted_by_id=actor_id,
            remarks=remarks,
            payload=payload or {},
        )

    @classmethod
    def _apply_instance_status(cls, *, instance, status_value: str, actor_id: int | None, remarks: str = "") -> None:
        update_fields: list[str] = []
        now = timezone.now()
        if hasattr(instance, "approval_status") and getattr(instance, "approval_status") != status_value:
            instance.approval_status = status_value
            update_fields.append("approval_status")
        if status_value in {cls.STATUS.SUBMITTED, cls.STATUS.PENDING_APPROVAL}:
            for field_name in ("requested_by_id", "submitted_by_id"):
                if hasattr(instance, field_name) and actor_id and getattr(instance, field_name) != actor_id:
                    setattr(instance, field_name, actor_id)
                    update_fields.append(field_name[:-3] if field_name.endswith("_id") else field_name)
            for field_name in ("requested_at", "submitted_at"):
                if hasattr(instance, field_name) and getattr(instance, field_name) is None:
                    setattr(instance, field_name, now)
                    update_fields.append(field_name)
        if status_value == cls.STATUS.APPROVED:
            for field_name in ("approved_by_id",):
                if hasattr(instance, field_name) and actor_id:
                    setattr(instance, field_name, actor_id)
                    update_fields.append(field_name[:-3])
            for field_name in ("approved_at",):
                if hasattr(instance, field_name):
                    setattr(instance, field_name, now)
                    update_fields.append(field_name)
        if status_value == cls.STATUS.REJECTED:
            for field_name in ("rejected_by_id",):
                if hasattr(instance, field_name) and actor_id:
                    setattr(instance, field_name, actor_id)
                    update_fields.append(field_name[:-3])
            for field_name in ("rejected_at",):
                if hasattr(instance, field_name):
                    setattr(instance, field_name, now)
                    update_fields.append(field_name)
        if status_value == cls.STATUS.CANCELLED:
            for field_name in ("cancelled_by_id",):
                if hasattr(instance, field_name) and actor_id:
                    setattr(instance, field_name, actor_id)
                    update_fields.append(field_name[:-3])
            for field_name in ("cancelled_at",):
                if hasattr(instance, field_name):
                    setattr(instance, field_name, now)
                    update_fields.append(field_name)
        if status_value == cls.STATUS.LOCKED:
            for field_name in ("locked_by_id",):
                if hasattr(instance, field_name) and actor_id:
                    setattr(instance, field_name, actor_id)
                    update_fields.append(field_name[:-3])
            for field_name in ("locked_at",):
                if hasattr(instance, field_name):
                    setattr(instance, field_name, now)
                    update_fields.append(field_name)
        if remarks:
            for field_name in ("approval_note", "manager_note", "status_comment"):
                if hasattr(instance, field_name):
                    setattr(instance, field_name, remarks)
                    update_fields.append(field_name)
                    break
        if update_fields:
            instance.save(update_fields=list(dict.fromkeys(update_fields + ["updated_at"])))

    @classmethod
    @transaction.atomic
    def submit_for_approval(
        cls,
        *,
        instance,
        workflow_key: str,
        actor_id: int | None,
        remarks: str = "",
        title: str = "",
    ) -> ApprovalResolution:
        request = cls.get_or_create_request(instance=instance, workflow_key=workflow_key, title=title)
        policy = cls.resolve_policy(instance=instance, workflow_key=workflow_key)
        cls._ensure_steps(request=request, policy=policy)
        old_status = request.status
        request.status = cls.STATUS.PENDING_APPROVAL
        request.requested_by_id = actor_id
        request.requested_at = request.requested_at or timezone.now()
        request.submitted_at = timezone.now()
        request.remarks = remarks or request.remarks
        request.save(update_fields=["status", "requested_by", "requested_at", "submitted_at", "remarks", "updated_at"])
        cls._log(
            request=request,
            action=ApprovalActionLog.Action.SUBMITTED,
            previous_status=old_status,
            new_status=cls.STATUS.SUBMITTED,
            actor_id=actor_id,
            remarks=remarks,
        )
        cls._log(
            request=request,
            action=ApprovalActionLog.Action.ROUTED,
            previous_status=cls.STATUS.SUBMITTED,
            new_status=request.status,
            actor_id=actor_id,
            remarks=remarks,
        )
        cls._apply_instance_status(instance=instance, status_value=request.status, actor_id=actor_id, remarks=remarks)
        cls._emit_status_notification(
            instance=instance,
            workflow_key=workflow_key,
            event_suffix="SUBMITTED",
            actor_id=actor_id,
            remarks=remarks,
            status_value=request.status,
        )
        return ApprovalResolution(request=request, status=request.status)

    @classmethod
    @transaction.atomic
    def approve(
        cls,
        *,
        instance,
        workflow_key: str,
        actor_id: int | None,
        remarks: str = "",
    ) -> ApprovalResolution:
        request = cls.get_or_create_request(instance=instance, workflow_key=workflow_key)
        old_status = request.status
        step = request.steps.filter(status=ApprovalStep.Status.PENDING).order_by("step_order", "id").first()
        if step:
            step.status = ApprovalStep.Status.APPROVED
            step.acted_by_id = actor_id
            step.acted_at = timezone.now()
            step.remarks = remarks or step.remarks
            step.save(update_fields=["status", "acted_by", "acted_at", "remarks", "updated_at"])
        request.status = cls.STATUS.APPROVED
        request.approved_by_id = actor_id
        request.approved_at = timezone.now()
        request.remarks = remarks or request.remarks
        request.save(update_fields=["status", "approved_by", "approved_at", "remarks", "updated_at"])
        cls._log(
            request=request,
            action=ApprovalActionLog.Action.APPROVED,
            previous_status=old_status,
            new_status=request.status,
            actor_id=actor_id,
            remarks=remarks,
            step=step,
        )
        cls._apply_instance_status(instance=instance, status_value=request.status, actor_id=actor_id, remarks=remarks)
        cls._emit_status_notification(
            instance=instance,
            workflow_key=workflow_key,
            event_suffix="APPROVED",
            actor_id=actor_id,
            remarks=remarks,
            status_value=request.status,
        )
        return ApprovalResolution(request=request, status=request.status)

    @classmethod
    @transaction.atomic
    def reject(
        cls,
        *,
        instance,
        workflow_key: str,
        actor_id: int | None,
        remarks: str = "",
    ) -> ApprovalResolution:
        request = cls.get_or_create_request(instance=instance, workflow_key=workflow_key)
        old_status = request.status
        step = request.steps.filter(status=ApprovalStep.Status.PENDING).order_by("step_order", "id").first()
        if step:
            step.status = ApprovalStep.Status.REJECTED
            step.acted_by_id = actor_id
            step.acted_at = timezone.now()
            step.remarks = remarks or step.remarks
            step.save(update_fields=["status", "acted_by", "acted_at", "remarks", "updated_at"])
        request.status = cls.STATUS.REJECTED
        request.rejected_by_id = actor_id
        request.rejected_at = timezone.now()
        request.remarks = remarks or request.remarks
        request.save(update_fields=["status", "rejected_by", "rejected_at", "remarks", "updated_at"])
        cls._log(
            request=request,
            action=ApprovalActionLog.Action.REJECTED,
            previous_status=old_status,
            new_status=request.status,
            actor_id=actor_id,
            remarks=remarks,
            step=step,
        )
        cls._apply_instance_status(instance=instance, status_value=request.status, actor_id=actor_id, remarks=remarks)
        cls._emit_status_notification(
            instance=instance,
            workflow_key=workflow_key,
            event_suffix="REJECTED",
            actor_id=actor_id,
            remarks=remarks,
            status_value=request.status,
        )
        return ApprovalResolution(request=request, status=request.status)

    @classmethod
    @transaction.atomic
    def cancel(
        cls,
        *,
        instance,
        workflow_key: str,
        actor_id: int | None,
        remarks: str = "",
    ) -> ApprovalResolution:
        request = cls.get_or_create_request(instance=instance, workflow_key=workflow_key)
        old_status = request.status
        request.status = cls.STATUS.CANCELLED
        request.cancelled_by_id = actor_id
        request.cancelled_at = timezone.now()
        request.remarks = remarks or request.remarks
        request.save(update_fields=["status", "cancelled_by", "cancelled_at", "remarks", "updated_at"])
        request.steps.filter(status=ApprovalStep.Status.PENDING).update(status=ApprovalStep.Status.CANCELLED, acted_by_id=actor_id, acted_at=timezone.now())
        cls._log(
            request=request,
            action=ApprovalActionLog.Action.CANCELLED,
            previous_status=old_status,
            new_status=request.status,
            actor_id=actor_id,
            remarks=remarks,
        )
        cls._apply_instance_status(instance=instance, status_value=request.status, actor_id=actor_id, remarks=remarks)
        cls._emit_status_notification(
            instance=instance,
            workflow_key=workflow_key,
            event_suffix="CANCELLED",
            actor_id=actor_id,
            remarks=remarks,
            status_value=request.status,
        )
        return ApprovalResolution(request=request, status=request.status)

    @classmethod
    @transaction.atomic
    def lock_after_approval(
        cls,
        *,
        instance,
        workflow_key: str,
        actor_id: int | None,
        remarks: str = "",
    ) -> ApprovalResolution:
        request = cls.get_or_create_request(instance=instance, workflow_key=workflow_key)
        old_status = request.status
        request.status = cls.STATUS.LOCKED
        request.locked_by_id = actor_id
        request.locked_at = timezone.now()
        request.remarks = remarks or request.remarks
        request.save(update_fields=["status", "locked_by", "locked_at", "remarks", "updated_at"])
        cls._log(
            request=request,
            action=ApprovalActionLog.Action.LOCKED,
            previous_status=old_status,
            new_status=request.status,
            actor_id=actor_id,
            remarks=remarks,
        )
        cls._apply_instance_status(instance=instance, status_value=request.status, actor_id=actor_id, remarks=remarks)
        cls._emit_status_notification(
            instance=instance,
            workflow_key=workflow_key,
            event_suffix="LOCKED",
            actor_id=actor_id,
            remarks=remarks,
            status_value=request.status,
        )
        return ApprovalResolution(request=request, status=request.status)

    @classmethod
    def history_for_instance(cls, *, instance, workflow_key: str | None = None):
        queryset = ApprovalRequest.objects.filter(
            content_type=cls._content_type(instance),
            object_id=str(instance.pk),
            isactive=True,
        ).prefetch_related("steps", "action_logs__acted_by", "steps__approver_user", "steps__acted_by")
        if workflow_key:
            queryset = queryset.filter(workflow_key=workflow_key)
        return queryset.order_by("-id")
