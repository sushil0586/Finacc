from datetime import timedelta
import uuid

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from Authentication.models import User
from entity.models import Entity
from subscriptions.models import CustomerAccount, SubscriptionPlan, UserEntityAccess

from .pagination import PlatformPageNumberPagination
from .permissions import HasPlatformPermissions, IsPlatformOperator
from .read_models import account_queryset, entity_health, entity_queryset, serialize_account, serialize_entity, user_display_name
from .services import PlatformAccessService
from .models import PlatformAuditEvent, PlatformOperationRequest, PlatformRole, PlatformUserRole
from .operations import PlatformOperationService


class PlatformReadAPIView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformOperator, HasPlatformPermissions)

    def reveal_sensitive(self, request):
        return PlatformAccessService.has_permission(request.user, "platform.customer.sensitive.view")


class PlatformDashboardAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.customer.view", "platform.entity.view")

    def get(self, request):
        now = timezone.now()
        accounts = account_queryset()
        entities = entity_queryset()
        approval_cutoff = PlatformOperationService.approval_expiry_cutoff(now=now)
        expiry_warning_cutoff = approval_cutoff + timedelta(hours=2)
        operations = PlatformOperationRequest.objects.all()
        return Response(
            {
                "customers": {
                    "total": accounts.count(),
                    "active": accounts.filter(status=CustomerAccount.Status.ACTIVE).count(),
                    "suspended": accounts.filter(status=CustomerAccount.Status.SUSPENDED).count(),
                },
                "entities": {
                    "total": entities.count(),
                    "active": entities.filter(organization_status=Entity.OrganizationStatus.ACTIVE, isactive=True).count(),
                    "unlinked": entities.filter(customer_account__isnull=True).count(),
                },
                "memberships": {
                    "active": UserEntityAccess.objects.filter(
                        is_active=True,
                        granted_at__lte=now,
                    )
                    .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
                    .count()
                },
                "operations": {
                    "pending_approval": operations.filter(status=PlatformOperationRequest.Status.PENDING_APPROVAL).count(),
                    "approved_expiring_soon": operations.filter(
                        status=PlatformOperationRequest.Status.APPROVED,
                        approvals__decided_at__gt=approval_cutoff,
                        approvals__decided_at__lte=expiry_warning_cutoff,
                    ).distinct().count(),
                    "expired_approval": operations.filter(
                        status=PlatformOperationRequest.Status.FAILED,
                        failure_code="approval_expired",
                    ).count(),
                    "failed_onboarding": operations.filter(
                        operation_type=PlatformOperationRequest.OperationType.ONBOARD_CUSTOMER,
                        status=PlatformOperationRequest.Status.FAILED,
                    ).count(),
                },
                "mode": "read_only",
            }
        )


class PlatformConfigurationHealthAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.entity.view",)

    def get(self, request):
        rows = []
        issue_counts = {}
        severity_counts = {"high": 0, "medium": 0, "low": 0}
        entities = list(entity_queryset())
        for entity in entities:
            health = entity_health(entity)
            if health["status"] == "healthy":
                continue
            findings = health["findings"]
            for finding in findings:
                severity = finding["severity"]
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
                issue = issue_counts.setdefault(
                    finding["code"],
                    {"code": finding["code"], "severity": severity, "message": finding["message"], "count": 0},
                )
                issue["count"] += 1
            rows.append(
                {
                    "id": entity.id,
                    "entity_name": entity.entityname,
                    "entity_code": entity.entity_code,
                    "customer_account_name": entity.customer_account.name if entity.customer_account_id else "",
                    "organization_status": entity.organization_status,
                    "findings": findings,
                    "repair_assessment_available": PlatformAccessService.has_permission(request.user, "platform.repair.preview"),
                }
            )
        severity_order = {"high": 0, "medium": 1, "low": 2}
        issues = sorted(issue_counts.values(), key=lambda item: (severity_order.get(item["severity"], 3), -item["count"], item["code"]))
        rows.sort(key=lambda item: (-sum(finding["severity"] == "high" for finding in item["findings"]), item["entity_name"].lower()))
        return Response(
            {
                "summary": {
                    "total_entities": len(entities),
                    "healthy_entities": len(entities) - len(rows),
                    "attention_entities": len(rows),
                    "total_findings": sum(severity_counts.values()),
                    "severity": severity_counts,
                },
                "issues": issues,
                "entities": rows,
                "generated_at": timezone.now(),
            }
        )


class PlatformOperatorListAPIView(PlatformReadAPIView, GenericAPIView):
    required_platform_permissions = ("platform.security.manage",)
    pagination_class = PlatformPageNumberPagination

    def get(self, request):
        now = timezone.now()
        queryset = (
            PlatformUserRole.objects.select_related("user", "role", "granted_by")
            .prefetch_related("role__permissions")
            .annotate(active_session_count=Count(
                "user__auth_sessions",
                filter=Q(user__auth_sessions__revoked_at__isnull=True, user__auth_sessions__expires_at__gt=now),
                distinct=True,
            ))
            .order_by("user__email", "role__name")
        )
        query = (request.query_params.get("q") or "").strip()
        state = (request.query_params.get("state") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(user__email__icontains=query)
                | Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(role__name__icontains=query)
                | Q(role__code__icontains=query)
            )
        if state == "effective":
            queryset = queryset.filter(
                user__is_active=True, role__is_active=True, is_active=True,
                revoked_at__isnull=True, valid_from__lte=now,
            ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        elif state == "revoked":
            queryset = queryset.filter(Q(is_active=False) | Q(revoked_at__isnull=False))
        elif state == "expired":
            queryset = queryset.filter(is_active=True, revoked_at__isnull=True, expires_at__lte=now)
        elif state == "scheduled":
            queryset = queryset.filter(is_active=True, revoked_at__isnull=True, valid_from__gt=now)

        page = self.paginate_queryset(queryset)
        assignments = page if page is not None else queryset
        rows = [self._serialize_assignment(assignment, now) for assignment in assignments]
        return self.get_paginated_response(rows) if page is not None else Response(rows)

    @staticmethod
    def _serialize_assignment(assignment, now):
        effective = (
            assignment.is_active and assignment.revoked_at is None
            and assignment.valid_from <= now
            and (assignment.expires_at is None or assignment.expires_at > now)
            and assignment.role.is_active and assignment.user.is_active
        )
        if effective:
            state = "effective"
        elif assignment.revoked_at or not assignment.is_active:
            state = "revoked"
        elif assignment.expires_at and assignment.expires_at <= now:
            state = "expired"
        else:
            state = "scheduled"
        name = user_display_name(assignment.user)
        return {
            "assignment_id": assignment.id,
            "user": {
                "id": assignment.user_id,
                "name": name,
                "email": assignment.user.email,
                "is_active": assignment.user.is_active,
                "is_locked": assignment.user.is_locked,
                "email_verified": assignment.user.email_verified,
            },
            "role": {
                "code": assignment.role.code,
                "name": assignment.role.name,
                "permission_count": assignment.role.permissions.filter(is_active=True).count(),
            },
            "state": state,
            "valid_from": assignment.valid_from,
            "expires_at": assignment.expires_at,
            "revoked_at": assignment.revoked_at,
            "granted_by": assignment.granted_by.email,
            "reason": assignment.reason,
            "active_session_count": assignment.active_session_count,
        }


class PlatformRoleListAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.security.manage",)

    def get(self, request):
        roles = PlatformRole.objects.filter(is_active=True).prefetch_related("permissions")
        return Response([{
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "is_system": role.is_system,
            "permissions": sorted(role.permissions.filter(is_active=True).values_list("code", flat=True)),
        } for role in roles])


class PlatformOperatorCandidateListAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.security.manage",)

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 2:
            return Response([])
        users = User.objects.filter(is_active=True).filter(
            Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
        ).annotate(platform_assignment_count=Count(
            "platform_role_assignments",
            filter=Q(platform_role_assignments__is_active=True, platform_role_assignments__revoked_at__isnull=True),
        )).order_by("email")[:20]
        return Response([{
            "id": user.id,
            "name": user_display_name(user),
            "email": user.email,
            "email_verified": user.email_verified,
            "is_locked": user.is_locked,
            "platform_assignment_count": user.platform_assignment_count,
        } for user in users])


class PlatformSecuritySummaryAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.security.manage",)

    def get(self, request):
        now = timezone.now()
        effective = PlatformUserRole.objects.filter(
            is_active=True, revoked_at__isnull=True, valid_from__lte=now,
            role__is_active=True, user__is_active=True,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        return Response({
            "effective_assignments": effective.count(),
            "active_operators": effective.values("user_id").distinct().count(),
            "expiring_within_24_hours": effective.filter(expires_at__lte=now + timedelta(hours=24)).count(),
            "expired_pending_sweep": PlatformUserRole.objects.filter(
                is_active=True, revoked_at__isnull=True, expires_at__lte=now,
            ).count(),
            "locked_operators": User.objects.filter(
                platform_role_assignments__is_active=True, locked_until__gt=now,
            ).distinct().count(),
            "active_sessions": User.objects.filter(
                platform_role_assignments__in=effective,
                auth_sessions__revoked_at__isnull=True,
                auth_sessions__expires_at__gt=now,
            ).values("auth_sessions__id").distinct().count(),
            "generated_at": now,
        })


class PlatformAuditEventListAPIView(PlatformReadAPIView, GenericAPIView):
    required_platform_permissions = ("platform.audit.view",)
    pagination_class = PlatformPageNumberPagination

    def get(self, request):
        queryset = PlatformAuditEvent.objects.select_related("actor")
        query = (request.query_params.get("q") or "").strip()
        outcome = (request.query_params.get("outcome") or "").strip()
        if query:
            filters = (
                Q(event_type__icontains=query)
                | Q(permission_code__icontains=query)
                | Q(actor__email__icontains=query)
                | Q(request_path__icontains=query)
            )
            try:
                filters |= Q(correlation_id=uuid.UUID(query))
            except ValueError:
                pass
            if query.isdigit():
                filters |= Q(customer_account_id=int(query)) | Q(entity_id=int(query))
            queryset = queryset.filter(filters)
        if outcome:
            queryset = queryset.filter(outcome=outcome)
        page = self.paginate_queryset(queryset)
        events = page if page is not None else queryset
        rows = [{
            "id": str(event.id),
            "correlation_id": str(event.correlation_id),
            "created_at": event.created_at,
            "event_type": event.event_type,
            "outcome": event.outcome,
            "actor": ({"id": event.actor_id, "email": event.actor.email} if event.actor_id else None),
            "permission_code": event.permission_code,
            "customer_account_id": event.customer_account_id,
            "entity_id": event.entity_id,
            "request_method": event.request_method,
            "request_path": event.request_path,
            "details": event.details,
        } for event in events]
        return self.get_paginated_response(rows) if page is not None else Response(rows)


class PlatformCustomerListAPIView(PlatformReadAPIView, GenericAPIView):
    required_platform_permissions = ("platform.customer.view",)
    pagination_class = PlatformPageNumberPagination

    def get(self, request):
        queryset = account_queryset()
        query = (request.query_params.get("q") or "").strip()
        status_value = (request.query_params.get("status") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(legal_name__icontains=query)
                | Q(trade_name__icontains=query)
                | Q(slug__icontains=query)
                | Q(owner__email__icontains=query)
                | Q(primary_contact_email__icontains=query)
                | Q(primary_contact_phone__icontains=query)
                | Q(external_customer_id__icontains=query)
                | Q(entities__entityname__icontains=query)
                | Q(entities__gst_registrations__gstin__iexact=query.upper())
            ).distinct()
        if status_value:
            queryset = queryset.filter(status=status_value)
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset
        data = [serialize_account(row, reveal_sensitive=self.reveal_sensitive(request)) for row in rows]
        return self.get_paginated_response(data) if page is not None else Response(data)


class PlatformSubscriptionPlanListAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.subscription.view",)

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order", "price_amount", "name")
        return Response([
            {
                "id": plan.id,
                "code": plan.code,
                "name": plan.name,
                "description": plan.description,
                "tier": plan.tier,
                "billing_interval": plan.billing_interval,
                "price_amount": plan.price_amount,
                "currency": plan.currency,
                "trial_days": plan.trial_days,
                "is_default": plan.is_default,
                "is_public": plan.is_public,
                "is_selectable_for_signup": plan.is_selectable_for_signup,
            }
            for plan in plans
        ])


class PlatformCustomerDetailAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.customer.view",)

    def get(self, request, pk):
        account = get_object_or_404(account_queryset(), pk=pk)
        reveal = self.reveal_sensitive(request)
        payload = serialize_account(account, reveal_sensitive=reveal, include_detail=True)
        payload["entities"] = [
            serialize_entity(row, reveal_sensitive=reveal)
            for row in entity_queryset().filter(customer_account=account)
        ]
        payload["memberships"] = [
            {
                "id": membership.id,
                "user_id": membership.user_id,
                "name": user_display_name(membership.user),
                "email": membership.user.email if reveal else self._mask_email(membership.user.email),
                "role": membership.role,
                "is_active": membership.is_active,
                "expires_at": membership.expires_at,
                "updated_at": membership.updated_at,
                "email_verified": membership.user.email_verified,
                "is_expired": membership.is_expired,
                "can_resend_invite": bool(
                    membership.is_active
                    and not membership.is_expired
                    and not membership.user.email_verified
                    and membership.role != UserEntityAccess.Role.OWNER
                    and account.owner_id != membership.user_id
                ),
            }
            for membership in account.user_accesses.select_related("user").order_by("user__email")
        ]
        return Response(payload)

    @staticmethod
    def _mask_email(value):
        from .read_models import mask_email

        return mask_email(value)


class PlatformEntityListAPIView(PlatformReadAPIView, GenericAPIView):
    required_platform_permissions = ("platform.entity.view",)
    pagination_class = PlatformPageNumberPagination

    def get(self, request):
        queryset = entity_queryset()
        query = (request.query_params.get("q") or "").strip()
        status_value = (request.query_params.get("status") or "").strip()
        customer_account_id = request.query_params.get("customer_account")
        if query:
            queryset = queryset.filter(
                Q(entityname__icontains=query)
                | Q(legalname__icontains=query)
                | Q(trade_name__icontains=query)
                | Q(entity_code__icontains=query)
                | Q(customer_account__name__icontains=query)
                | Q(gst_registrations__gstin__iexact=query.upper())
            ).distinct()
        if status_value:
            queryset = queryset.filter(organization_status=status_value)
        if customer_account_id:
            queryset = queryset.filter(customer_account_id=customer_account_id)
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset
        data = [serialize_entity(row, reveal_sensitive=self.reveal_sensitive(request)) for row in rows]
        return self.get_paginated_response(data) if page is not None else Response(data)


class PlatformEntityDetailAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.entity.view",)

    def get(self, request, pk):
        entity = get_object_or_404(entity_queryset(), pk=pk)
        return Response(
            serialize_entity(
                entity,
                reveal_sensitive=self.reveal_sensitive(request),
                include_detail=True,
            )
        )
