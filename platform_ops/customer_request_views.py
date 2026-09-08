from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from entity.models import Entity
from subscriptions.models import CustomerAccount
from subscriptions.services import SubscriptionService

from .models import CustomerServiceRequest, CustomerServiceRequestEvent
from .permissions import HasPlatformPermissions, IsPlatformOperator, PlatformMutationsEnabled
from .pagination import PlatformPageNumberPagination
from .services import PlatformAuditService


class CustomerServiceRequestCreateSerializer(serializers.Serializer):
    customer_account_id = serializers.IntegerField(required=False)
    entity_id = serializers.IntegerField(required=False, allow_null=True)
    request_type = serializers.ChoiceField(choices=CustomerServiceRequest.RequestType.choices)
    subject = serializers.CharField(max_length=180)
    description = serializers.CharField(min_length=10, max_length=5000)
    priority = serializers.ChoiceField(
        choices=CustomerServiceRequest.Priority.choices,
        default=CustomerServiceRequest.Priority.NORMAL,
    )


class CustomerServiceRequestUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=CustomerServiceRequest.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    resolution = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    assign_to_me = serializers.BooleanField(required=False, default=False)


def serialize_user(user):
    if not user:
        return None
    name = " ".join(filter(None, (getattr(user, "first_name", ""), getattr(user, "last_name", "")))).strip()
    return {"id": user.id, "email": user.email, "name": name}


def serialize_request(item, *, include_events=False):
    payload = {
        "id": item.id,
        "customer_account": {"id": item.customer_account_id, "name": item.customer_account.name},
        "entity": ({"id": item.entity_id, "name": item.entity.entityname} if item.entity_id else None),
        "request_type": item.request_type,
        "subject": item.subject,
        "description": item.description,
        "priority": item.priority,
        "status": item.status,
        "submitted_by": serialize_user(item.submitted_by),
        "assigned_to": serialize_user(item.assigned_to),
        "operator_note": item.operator_note,
        "resolution": item.resolution,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "completed_at": item.completed_at,
    }
    if include_events:
        payload["events"] = [{
            "id": event.id,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "note": event.note,
            "actor": serialize_user(event.actor),
            "created_at": event.created_at,
        } for event in item.events.select_related("actor").all()]
    return payload


def tenant_accounts(user):
    account_ids = SubscriptionService.active_memberships_queryset(user=user).values_list("customer_account_id", flat=True)
    return CustomerAccount.objects.filter(id__in=account_ids, is_active=True)


class TenantCustomerServiceRequestAPIView(GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = CustomerServiceRequestCreateSerializer

    def get(self, request):
        queryset = CustomerServiceRequest.objects.filter(
            customer_account__in=tenant_accounts(request.user),
        ).select_related("customer_account", "entity", "submitted_by", "assigned_to")
        return Response([serialize_request(item) for item in queryset[:100]])

    @transaction.atomic
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        accounts = tenant_accounts(request.user)
        account_id = values.get("customer_account_id")
        account = get_object_or_404(accounts, pk=account_id) if account_id else accounts.order_by("id").first()
        if not account:
            return Response({"customer_account_id": ["No active customer account is available."]}, status=status.HTTP_400_BAD_REQUEST)
        entity = None
        if values.get("entity_id"):
            entity = get_object_or_404(Entity.objects.filter(customer_account=account, isactive=True), pk=values["entity_id"])
        item = CustomerServiceRequest.objects.create(
            customer_account=account,
            entity=entity,
            request_type=values["request_type"],
            subject=values["subject"].strip(),
            description=values["description"].strip(),
            priority=values["priority"],
            submitted_by=request.user,
        )
        CustomerServiceRequestEvent.objects.create(
            request=item,
            actor=request.user,
            to_status=CustomerServiceRequest.Status.NEW,
            note="Request submitted by customer.",
        )
        return Response(serialize_request(item, include_events=True), status=status.HTTP_201_CREATED)


class PlatformCustomerServiceRequestListAPIView(GenericAPIView):
    permission_classes = (IsAuthenticated, IsPlatformOperator, HasPlatformPermissions)
    required_platform_permissions = ("platform.support.manage",)
    pagination_class = PlatformPageNumberPagination

    def get(self, request):
        queryset = CustomerServiceRequest.objects.select_related(
            "customer_account", "entity", "submitted_by", "assigned_to"
        )
        status_value = (request.query_params.get("status") or "").strip()
        query = (request.query_params.get("q") or "").strip()
        if status_value:
            queryset = queryset.filter(status=status_value)
        if query:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(subject__icontains=query)
                | Q(description__icontains=query)
                | Q(customer_account__name__icontains=query)
                | Q(submitted_by__email__icontains=query)
            )
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset
        data = [serialize_request(item) for item in rows]
        return self.get_paginated_response(data) if page is not None else Response(data)


class PlatformCustomerServiceRequestDetailAPIView(GenericAPIView):
    permission_classes = (IsAuthenticated, IsPlatformOperator, PlatformMutationsEnabled, HasPlatformPermissions)
    required_platform_permissions = ("platform.support.manage",)
    serializer_class = CustomerServiceRequestUpdateSerializer

    def get_object(self, pk):
        return get_object_or_404(
            CustomerServiceRequest.objects.select_related("customer_account", "entity", "submitted_by", "assigned_to"),
            pk=pk,
        )

    def get(self, request, pk):
        return Response(serialize_request(self.get_object(pk), include_events=True))

    @transaction.atomic
    def patch(self, request, pk):
        item = get_object_or_404(CustomerServiceRequest.objects.select_for_update(), pk=pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        old_status = item.status
        new_status = values["status"]
        allowed = {
            "new": {"in_review", "rejected"},
            "in_review": {"approved", "rejected"},
            "approved": {"processing", "rejected"},
            "processing": {"completed", "in_review"},
            "rejected": {"in_review"},
            "completed": {"in_review"},
        }
        if new_status != old_status and new_status not in allowed.get(old_status, set()):
            return Response({"status": [f"Cannot move request from {old_status} to {new_status}."]}, status=status.HTTP_400_BAD_REQUEST)
        if values.get("assign_to_me"):
            item.assigned_to = request.user
        item.status = new_status
        item.operator_note = values.get("note", item.operator_note).strip()
        if "resolution" in values:
            item.resolution = values["resolution"].strip()
        if new_status == CustomerServiceRequest.Status.COMPLETED:
            if len(item.resolution) < 5:
                return Response({"resolution": ["Resolution is required before completion."]}, status=status.HTTP_400_BAD_REQUEST)
            item.completed_at = timezone.now()
        elif old_status == CustomerServiceRequest.Status.COMPLETED:
            item.completed_at = None
        item.save()
        if new_status != old_status or values.get("note"):
            CustomerServiceRequestEvent.objects.create(
                request=item,
                actor=request.user,
                from_status=old_status,
                to_status=new_status,
                note=values.get("note", "").strip(),
            )
        PlatformAuditService.log(
            actor=request.user,
            event_type="customer_service_request.updated",
            outcome="success",
            request=request,
            permission_code="platform.support.manage",
            customer_account_id=item.customer_account_id,
            entity_id=item.entity_id,
            details={"service_request_id": item.id, "from_status": old_status, "to_status": new_status},
        )
        item = self.get_object(pk)
        return Response(serialize_request(item, include_events=True))
