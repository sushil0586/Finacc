from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from .discovery_views import PlatformReadAPIView
from .models import PlatformAuditEvent, PlatformOperationRequest
from .operations import (
    PlatformApprovalDecisionSerializer,
    PlatformCustomerContactUpdateSerializer,
    PlatformCustomerStatusUpdateSerializer,
    PlatformAddBranchSerializer,
    PlatformAddFinancialYearSerializer,
    PlatformEntityGstUpdateSerializer,
    PlatformSubscriptionPlanChangeSerializer,
    PlatformTenantMembershipUpdateSerializer,
    PlatformTenantUserInviteSerializer,
    PlatformTenantInvitationResendSerializer,
    PlatformCustomerOwnershipTransferSerializer,
    PlatformOperationCancellationSerializer,
    PlatformEntityNumberingRepairSerializer,
    PlatformEntityPostingMappingRepairSerializer,
    PlatformEntityRbacRoleRepairSerializer,
    PlatformEntityCatalogRepairSerializer,
    PlatformEntityAssetRepairSerializer,
    PlatformEntityTradeSettingsRepairSerializer,
    PlatformRoleChangeSerializer,
    PlatformSessionRevocationSerializer,
    PlatformOnboardingRequestSerializer,
    PlatformOperationService,
)
from .pagination import PlatformPageNumberPagination
from .permissions import PlatformMutationsEnabled
from .services import PlatformAuditService


class PlatformOnboardingRequestAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.customer.create", "platform.entity.onboard")

    def post(self, request):
        serializer = PlatformOnboardingRequestSerializer(data=request.data)
        if not serializer.is_valid():
            PlatformAuditService.log(
                actor=request.user,
                event_type="platform.onboarding.request.invalid",
                outcome=PlatformAuditEvent.Outcome.FAILED,
                request=request,
                permission_code="platform.entity.onboard",
                details={"validation_errors": serializer.errors},
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            operation, created, validation = PlatformOperationService.create_onboarding_request(
                actor=request.user,
                validated_data=serializer.validated_data,
            )
        except Exception:
            PlatformAuditService.log(
                actor=request.user,
                event_type="platform.onboarding.request.failed",
                outcome=PlatformAuditEvent.Outcome.FAILED,
                request=request,
                permission_code="platform.entity.onboard",
            )
            raise

        if operation is None:
            PlatformAuditService.log(
                actor=request.user,
                event_type="platform.onboarding.request.blocked",
                outcome=PlatformAuditEvent.Outcome.DENIED,
                request=request,
                permission_code="platform.entity.onboard",
                details={"blocking_codes": [row["code"] for row in validation["blocking_errors"]]},
            )
            return Response(
                {"code": "onboarding_blocked", **validation},
                status=status.HTTP_409_CONFLICT,
            )

        PlatformAuditService.log(
            actor=request.user,
            event_type="platform.onboarding.request.created" if created else "platform.onboarding.request.replayed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.entity.onboard",
            details={"operation_id": str(operation.id), "correlation_id": str(operation.correlation_id)},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformOperationListAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.operation.view",)
    pagination_class = PlatformPageNumberPagination

    def get(self, request):
        queryset = PlatformOperationRequest.objects.select_related("requested_by", "cancelled_by", "provisioning_job")
        status_value = (request.query_params.get("status") or "").strip()
        if status_value:
            queryset = queryset.filter(status=status_value)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([PlatformOperationService.serialize(row) for row in page])


class PlatformOperationDetailAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.operation.view",)

    def get(self, request, pk):
        operation = get_object_or_404(
            PlatformOperationRequest.objects.select_related("requested_by", "cancelled_by", "provisioning_job"),
            pk=pk,
        )
        return Response(PlatformOperationService.serialize(operation, include_detail=True))


class PlatformOperationExecuteAPIView(PlatformReadAPIView):
    retry = False
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.operation.execute",)

    def post(self, request, pk):
        operation = get_object_or_404(PlatformOperationRequest, pk=pk)
        if operation.operation_type in {
            PlatformOperationRequest.OperationType.CHANGE_PLATFORM_ROLE,
            PlatformOperationRequest.OperationType.REVOKE_PLATFORM_SESSIONS,
        } and operation.request_snapshot.get("user_id") == request.user.id:
            return Response(
                {"code": "affected_operator_cannot_execute", "detail": "The affected operator cannot execute this security operation."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if self.retry:
            PlatformOperationService.validate_retry(operation)
        else:
            operation, expired = PlatformOperationService.expire_approval_if_needed(operation_id=operation.id)
            if expired:
                PlatformAuditService.log(
                    actor=request.user,
                    event_type="platform.operation.approval.expired",
                    outcome=PlatformAuditEvent.Outcome.FAILED,
                    request=request,
                    permission_code="platform.operation.execute",
                    customer_account_id=operation.customer_account_id,
                    entity_id=operation.entity_id,
                    details={"operation_id": str(operation.id), "trigger": "execution_attempt"},
                )
                return Response(
                    {"replayed": False, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
                    status=status.HTTP_409_CONFLICT,
                )
        if operation.operation_type == PlatformOperationRequest.OperationType.ONBOARD_CUSTOMER:
            operation, replayed = PlatformOperationService.execute_onboarding(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.CUSTOMER_CONTACT_UPDATE:
            operation, replayed = PlatformOperationService.execute_customer_contact_update(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.CUSTOMER_STATUS_UPDATE:
            operation, replayed = PlatformOperationService.execute_customer_status_update(operation_id=operation.id)
        elif operation.operation_type in {
            PlatformOperationRequest.OperationType.ADD_ENTITY_BRANCH,
            PlatformOperationRequest.OperationType.ADD_ENTITY_FINANCIAL_YEAR,
        }:
            operation, replayed = PlatformOperationService.execute_entity_child_request(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.UPDATE_ENTITY_GST_REGISTRATION:
            operation, replayed = PlatformOperationService.execute_entity_gst_update(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.REPAIR_ENTITY_NUMBERING:
            operation, replayed = PlatformOperationService.execute_entity_numbering_repair(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.REPAIR_ENTITY_POSTING_MAPPINGS:
            operation, replayed = PlatformOperationService.execute_entity_posting_mapping_repair(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.REPAIR_ENTITY_RBAC_ROLES:
            operation, replayed = PlatformOperationService.execute_entity_rbac_role_repair(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.REPAIR_ENTITY_CATALOG_DEFAULTS:
            operation, replayed = PlatformOperationService.execute_entity_catalog_repair(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.REPAIR_ENTITY_ASSET_DEFAULTS:
            operation, replayed = PlatformOperationService.execute_entity_asset_repair(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.REPAIR_ENTITY_TRADE_SETTINGS:
            operation, replayed = PlatformOperationService.execute_entity_trade_settings_repair(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.CHANGE_SUBSCRIPTION_PLAN:
            operation, replayed = PlatformOperationService.execute_subscription_plan_change(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.UPDATE_TENANT_MEMBERSHIP:
            operation, replayed = PlatformOperationService.execute_tenant_membership_update(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.INVITE_TENANT_USER:
            operation, replayed = PlatformOperationService.execute_tenant_user_invite(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.RESEND_TENANT_INVITATION:
            operation, replayed = PlatformOperationService.execute_tenant_invitation_resend(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.TRANSFER_CUSTOMER_OWNERSHIP:
            operation, replayed = PlatformOperationService.execute_customer_ownership_transfer(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.CHANGE_PLATFORM_ROLE:
            operation, replayed = PlatformOperationService.execute_platform_role_change(operation_id=operation.id)
        elif operation.operation_type == PlatformOperationRequest.OperationType.REVOKE_PLATFORM_SESSIONS:
            operation, replayed = PlatformOperationService.execute_platform_session_revocation(operation_id=operation.id)
        else:
            return Response({"code": "unsupported_operation_type"}, status=status.HTTP_400_BAD_REQUEST)
        event_type = (
            "platform.operation.execution.replayed"
            if replayed else
            "platform.operation.execution.succeeded"
            if operation.status == PlatformOperationRequest.Status.SUCCEEDED else
            "platform.operation.execution.failed"
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type=event_type,
            outcome=(
                PlatformAuditEvent.Outcome.SUCCESS
                if operation.status == PlatformOperationRequest.Status.SUCCEEDED
                else PlatformAuditEvent.Outcome.FAILED
            ),
            request=request,
            permission_code="platform.operation.execute",
            customer_account_id=operation.customer_account_id,
            entity_id=operation.entity_id,
            details={"operation_id": str(operation.id), "correlation_id": str(operation.correlation_id)},
        )
        response_status = status.HTTP_200_OK if operation.status == PlatformOperationRequest.Status.SUCCEEDED else status.HTTP_409_CONFLICT
        return Response(
            {"replayed": replayed, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=response_status,
        )


class PlatformOperationCancelAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.operation.cancel",)

    def post(self, request, pk):
        serializer = PlatformOperationCancellationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, replayed = PlatformOperationService.cancel_operation(
            operation_id=pk, actor=request.user, reason=serializer.validated_data["reason"],
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type="platform.operation.cancellation.replayed" if replayed else "platform.operation.cancelled",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.operation.cancel",
            customer_account_id=operation.customer_account_id,
            entity_id=operation.entity_id,
            details={"operation_id": str(operation.id), "reason": operation.cancellation_reason},
        )
        return Response(
            {"replayed": replayed, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_200_OK,
        )


class PlatformOnboardingRepairPreviewAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.repair.preview",)

    def get(self, request, pk):
        operation = get_object_or_404(
            PlatformOperationRequest.objects.select_related("provisioning_job"), pk=pk,
        )
        preview = PlatformOperationService.onboarding_repair_preview(operation)
        PlatformAuditService.log(
            actor=request.user,
            event_type="platform.onboarding.repair.previewed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS if preview["eligible"] else PlatformAuditEvent.Outcome.DENIED,
            request=request,
            permission_code="platform.repair.preview",
            details={"operation_id": str(operation.id), "eligible": preview["eligible"], "blockers": preview["blockers"]},
        )
        return Response(preview)


class PlatformOnboardingRepairExecuteAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.repair.execute",)

    def post(self, request, pk):
        operation = get_object_or_404(
            PlatformOperationRequest.objects.select_related("provisioning_job"), pk=pk,
        )
        preview = PlatformOperationService.onboarding_repair_preview(operation)
        if not preview["eligible"]:
            return Response({"repair": preview}, status=status.HTTP_409_CONFLICT)
        operation, replayed = PlatformOperationService.execute_onboarding(operation_id=operation.id)
        succeeded = operation.status == PlatformOperationRequest.Status.SUCCEEDED
        PlatformAuditService.log(
            actor=request.user,
            event_type="platform.onboarding.repair.succeeded" if succeeded else "platform.onboarding.repair.failed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS if succeeded else PlatformAuditEvent.Outcome.FAILED,
            request=request,
            permission_code="platform.repair.execute",
            customer_account_id=operation.customer_account_id,
            entity_id=operation.entity_id,
            details={"operation_id": str(operation.id), "strategy": preview["strategy"], "replayed": replayed},
        )
        return Response(
            {"replayed": replayed, "repair_preview": preview, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_200_OK if succeeded else status.HTTP_409_CONFLICT,
        )


class PlatformCustomerContactUpdateAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.customer.update",)

    def post(self, request, pk):
        from subscriptions.models import CustomerAccount

        customer = get_object_or_404(CustomerAccount, pk=pk)
        serializer = PlatformCustomerContactUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_customer_contact_update(
            actor=request.user, customer=customer, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type="platform.customer.contact_update.requested" if created else "platform.customer.contact_update.replayed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.customer.update",
            customer_account_id=customer.id,
            details={
                "operation_id": str(operation.id),
                "correlation_id": str(operation.correlation_id),
                "customer_account_id": customer.id,
            },
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformCustomerStatusUpdateAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.customer.update",)

    def post(self, request, pk):
        from subscriptions.models import CustomerAccount

        customer = get_object_or_404(CustomerAccount, pk=pk)
        serializer = PlatformCustomerStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_customer_status_update(
            actor=request.user, customer=customer, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type="platform.customer.status_update.requested" if created else "platform.customer.status_update.replayed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.customer.update",
            customer_account_id=customer.id,
            details={
                "operation_id": str(operation.id),
                "correlation_id": str(operation.correlation_id),
                "customer_account_id": customer.id,
                "desired_status": operation.request_snapshot["desired_status"],
            },
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformOperationDecisionAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.operation.approve",)

    def post(self, request, pk):
        serializer = PlatformApprovalDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, approval = PlatformOperationService.decide_operation(
            operation_id=pk,
            actor=request.user,
            **serializer.validated_data,
        )
        stale = approval is None
        PlatformAuditService.log(
            actor=request.user,
            event_type=(
                "platform.operation.approval.stale"
                if stale else f"platform.operation.{approval.decision}"
            ),
            outcome=PlatformAuditEvent.Outcome.FAILED if stale else PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.operation.approve",
            customer_account_id=operation.customer_account_id,
            entity_id=operation.entity_id,
            details={"operation_id": str(operation.id), "correlation_id": str(operation.correlation_id)},
        )
        return Response(
            PlatformOperationService.serialize(operation, include_detail=True),
            status=status.HTTP_409_CONFLICT if stale else status.HTTP_200_OK,
        )


class PlatformRoleChangeRequestAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.security.manage",)

    def post(self, request):
        serializer = PlatformRoleChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_platform_role_change(
            actor=request.user, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type=f"platform.security.role_change.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.security.manage",
            details={"operation_id": str(operation.id), "correlation_id": str(operation.correlation_id)},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformSessionRevocationRequestAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.security.manage",)

    def post(self, request):
        serializer = PlatformSessionRevocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_platform_session_revocation(
            actor=request.user, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type=f"platform.security.session_revocation.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.security.manage",
            details={"operation_id": str(operation.id), "correlation_id": str(operation.correlation_id)},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformEntityChildRequestAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.entity.update",)
    serializer_class = None
    operation_type = None
    event_name = ""

    def post(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_entity_child_request(
            actor=request.user,
            entity=entity,
            validated_data=serializer.validated_data,
            operation_type=self.operation_type,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type=f"platform.entity.{self.event_name}.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.entity.update",
            customer_account_id=entity.customer_account_id,
            entity_id=entity.id,
            details={"operation_id": str(operation.id), "correlation_id": str(operation.correlation_id)},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformAddBranchRequestAPIView(PlatformEntityChildRequestAPIView):
    serializer_class = PlatformAddBranchSerializer
    operation_type = PlatformOperationRequest.OperationType.ADD_ENTITY_BRANCH
    event_name = "branch_add"


class PlatformAddFinancialYearRequestAPIView(PlatformEntityChildRequestAPIView):
    serializer_class = PlatformAddFinancialYearSerializer
    operation_type = PlatformOperationRequest.OperationType.ADD_ENTITY_FINANCIAL_YEAR
    event_name = "financial_year_add"


class PlatformEntityGstUpdateAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.entity.update",)

    def post(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        serializer = PlatformEntityGstUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_entity_gst_update(
            actor=request.user, entity=entity, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type="platform.entity.gst_update.requested" if created else "platform.entity.gst_update.replayed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.entity.update",
            customer_account_id=entity.customer_account_id,
            entity_id=entity.id,
            details={"operation_id": str(operation.id), "correlation_id": str(operation.correlation_id)},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformEntityNumberingRepairPreviewAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.repair.preview",)

    def get(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        preview = PlatformOperationService.entity_numbering_repair_preview(entity)
        PlatformAuditService.log(
            actor=request.user,
            event_type="platform.entity.numbering_repair.previewed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.repair.preview",
            customer_account_id=entity.customer_account_id,
            entity_id=entity.id,
            details={"missing_series_count": preview["missing_series_count"], "eligible": preview["eligible"]},
        )
        return Response(preview)


class PlatformEntityNumberingRepairRequestAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.repair.execute",)

    def post(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        serializer = PlatformEntityNumberingRepairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_entity_numbering_repair(
            actor=request.user, entity=entity, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type=f"platform.entity.numbering_repair.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.repair.execute",
            customer_account_id=entity.customer_account_id,
            entity_id=entity.id,
            details={"operation_id": str(operation.id), "missing_series_count": operation.validation_snapshot["preview"]["missing_series_count"]},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformEntityPostingMappingRepairPreviewAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.repair.preview",)

    def get(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        preview = PlatformOperationService.entity_posting_mapping_repair_preview(entity)
        PlatformAuditService.log(
            actor=request.user, event_type="platform.entity.posting_mapping_repair.previewed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS, request=request,
            permission_code="platform.repair.preview", customer_account_id=entity.customer_account_id,
            entity_id=entity.id, details={"missing_mapping_count": preview["missing_mapping_count"], "eligible": preview["eligible"]},
        )
        return Response(preview)


class PlatformEntityPostingMappingRepairRequestAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.repair.execute",)

    def post(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        serializer = PlatformEntityPostingMappingRepairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_entity_posting_mapping_repair(
            actor=request.user, entity=entity, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user, event_type=f"platform.entity.posting_mapping_repair.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS, request=request,
            permission_code="platform.repair.execute", customer_account_id=entity.customer_account_id,
            entity_id=entity.id, details={"operation_id": str(operation.id)},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformEntityRbacRoleRepairPreviewAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.repair.preview",)

    def get(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        preview = PlatformOperationService.entity_rbac_role_repair_preview(entity)
        PlatformAuditService.log(
            actor=request.user, event_type="platform.entity.rbac_role_repair.previewed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS, request=request,
            permission_code="platform.repair.preview", customer_account_id=entity.customer_account_id,
            entity_id=entity.id, details={"missing_role_count": preview["missing_role_count"], "eligible": preview["eligible"]},
        )
        return Response(preview)


class PlatformEntityRbacRoleRepairRequestAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.repair.execute",)

    def post(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        serializer = PlatformEntityRbacRoleRepairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_entity_rbac_role_repair(
            actor=request.user, entity=entity, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user, event_type=f"platform.entity.rbac_role_repair.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS, request=request,
            permission_code="platform.repair.execute", customer_account_id=entity.customer_account_id,
            entity_id=entity.id, details={"operation_id": str(operation.id)},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformEntityCatalogRepairPreviewAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.repair.preview",)

    def get(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        preview = PlatformOperationService.entity_catalog_repair_preview(entity)
        PlatformAuditService.log(
            actor=request.user, event_type="platform.entity.catalog_repair.previewed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS, request=request,
            permission_code="platform.repair.preview", customer_account_id=entity.customer_account_id,
            entity_id=entity.id, details={"missing_count": preview["missing_count"], "eligible": preview["eligible"]},
        )
        return Response(preview)


class PlatformEntityCatalogRepairRequestAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.repair.execute",)

    def post(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        serializer = PlatformEntityCatalogRepairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_entity_catalog_repair(
            actor=request.user, entity=entity, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user, event_type=f"platform.entity.catalog_repair.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS, request=request,
            permission_code="platform.repair.execute", customer_account_id=entity.customer_account_id,
            entity_id=entity.id, details={"operation_id": str(operation.id)},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformEntityAssetRepairPreviewAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.repair.preview",)

    def get(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        preview = PlatformOperationService.entity_asset_repair_preview(entity)
        PlatformAuditService.log(
            actor=request.user, event_type="platform.entity.asset_repair.previewed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS, request=request,
            permission_code="platform.repair.preview", customer_account_id=entity.customer_account_id,
            entity_id=entity.id, details={"missing_count": preview["missing_count"], "eligible": preview["eligible"]},
        )
        return Response(preview)


class PlatformEntityAssetRepairRequestAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.repair.execute",)

    def post(self, request, pk):
        from entity.models import Entity

        entity = get_object_or_404(Entity, pk=pk)
        serializer = PlatformEntityAssetRepairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_entity_asset_repair(
            actor=request.user, entity=entity, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user, event_type=f"platform.entity.asset_repair.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS, request=request,
            permission_code="platform.repair.execute", customer_account_id=entity.customer_account_id,
            entity_id=entity.id, details={"operation_id": str(operation.id)},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformEntityTradeSettingsRepairPreviewAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.repair.preview",)

    def get(self, request, pk):
        from entity.models import Entity
        entity = get_object_or_404(Entity, pk=pk)
        preview = PlatformOperationService.entity_trade_settings_repair_preview(entity)
        PlatformAuditService.log(
            actor=request.user, event_type="platform.entity.trade_settings_repair.previewed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS, request=request,
            permission_code="platform.repair.preview", customer_account_id=entity.customer_account_id,
            entity_id=entity.id, details={"missing_count": preview["missing_count"], "eligible": preview["eligible"]},
        )
        return Response(preview)


class PlatformEntityChoiceOverrideAuditAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.repair.preview",)

    def get(self, request, pk):
        from entity.models import Entity
        entity = get_object_or_404(Entity, pk=pk)
        audit = PlatformOperationService.entity_choice_override_audit(entity)
        PlatformAuditService.log(
            actor=request.user, event_type="platform.entity.choice_overrides.audited",
            outcome=PlatformAuditEvent.Outcome.SUCCESS, request=request,
            permission_code="platform.repair.preview", customer_account_id=entity.customer_account_id,
            entity_id=entity.id, details={"attention_count": audit["attention_count"], "read_only": True},
        )
        return Response(audit)


class PlatformEntityTradeSettingsRepairRequestAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.repair.execute",)

    def post(self, request, pk):
        from entity.models import Entity
        entity = get_object_or_404(Entity, pk=pk)
        serializer = PlatformEntityTradeSettingsRepairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_entity_trade_settings_repair(
            actor=request.user, entity=entity, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user, event_type=f"platform.entity.trade_settings_repair.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS, request=request,
            permission_code="platform.repair.execute", customer_account_id=entity.customer_account_id,
            entity_id=entity.id, details={"operation_id": str(operation.id)},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformSubscriptionPlanChangeAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.subscription.change",)

    def post(self, request, pk):
        from subscriptions.models import CustomerAccount

        customer = get_object_or_404(CustomerAccount, pk=pk)
        serializer = PlatformSubscriptionPlanChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_subscription_plan_change(
            actor=request.user, customer=customer, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type="platform.subscription.plan_change.requested" if created else "platform.subscription.plan_change.replayed",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.subscription.change",
            customer_account_id=customer.id,
            details={
                "operation_id": str(operation.id),
                "correlation_id": str(operation.correlation_id),
                "subscription_id": operation.subscription_id,
            },
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformTenantMembershipUpdateAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.membership.manage",)

    def post(self, request, pk, membership_id):
        from subscriptions.models import CustomerAccount, UserEntityAccess

        customer = get_object_or_404(CustomerAccount, pk=pk)
        membership = get_object_or_404(UserEntityAccess, pk=membership_id, customer_account=customer)
        serializer = PlatformTenantMembershipUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_tenant_membership_update(
            actor=request.user, customer=customer, membership=membership, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type=f"platform.membership.access_update.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.membership.manage",
            customer_account_id=customer.id,
            details={"operation_id": str(operation.id), "membership_id": membership.id, "user_id": membership.user_id},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformTenantUserInviteAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.membership.manage",)

    def post(self, request, pk):
        from subscriptions.models import CustomerAccount

        customer = get_object_or_404(CustomerAccount, pk=pk)
        serializer = PlatformTenantUserInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_tenant_user_invite(
            actor=request.user, customer=customer, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type=f"platform.membership.invite.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.membership.manage",
            customer_account_id=customer.id,
            details={"operation_id": str(operation.id), "email": operation.request_snapshot["email"]},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformTenantInvitationResendAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.membership.manage",)

    def post(self, request, pk, membership_id):
        from subscriptions.models import CustomerAccount, UserEntityAccess

        customer = get_object_or_404(CustomerAccount, pk=pk)
        membership = get_object_or_404(UserEntityAccess, pk=membership_id, customer_account=customer)
        serializer = PlatformTenantInvitationResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_tenant_invitation_resend(
            actor=request.user, customer=customer, membership=membership, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type=f"platform.membership.invite_resend.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.membership.manage",
            customer_account_id=customer.id,
            details={"operation_id": str(operation.id), "membership_id": membership.id, "user_id": membership.user_id},
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformCustomerOwnershipTransferAPIView(PlatformReadAPIView):
    permission_classes = (*PlatformReadAPIView.permission_classes, PlatformMutationsEnabled)
    required_platform_permissions = ("platform.security.manage",)

    def post(self, request, pk):
        from subscriptions.models import CustomerAccount

        customer = get_object_or_404(CustomerAccount, pk=pk)
        serializer = PlatformCustomerOwnershipTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation, created = PlatformOperationService.create_customer_ownership_transfer(
            actor=request.user, customer=customer, validated_data=serializer.validated_data,
        )
        PlatformAuditService.log(
            actor=request.user,
            event_type=f"platform.customer.ownership_transfer.{'requested' if created else 'replayed'}",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.security.manage",
            customer_account_id=customer.id,
            details={
                "operation_id": str(operation.id),
                "previous_owner_user_id": customer.owner_id,
                "target_user_id": operation.request_snapshot["target_user_id"],
                "target_membership_id": operation.request_snapshot["target_membership_id"],
            },
        )
        return Response(
            {"replayed": not created, "operation": PlatformOperationService.serialize(operation, include_detail=True)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
