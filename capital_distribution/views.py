from __future__ import annotations

import logging
from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.models import EntityFinancialYear, SubEntity
from rbac.services import EffectivePermissionService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService

from .models import (
    CapitalDistributionAccountMapping,
    CapitalDistributionAuditEvent,
    CapitalDistributionRun,
    CapitalDistributionTaxWorking,
    CapitalDistributionTaxWorkingLine,
    DistributionPolicyVersion,
    EntityFormationProfile,
    FormationType,
    TaxPolicyVersion,
)
from .observability import (
    bind_operation_context,
    current_correlation_id,
    operation_metadata,
    reset_operation_context,
)
from .serializers import (
    DistributionPolicyPatchSerializer,
    DistributionPolicySeedSerializer,
    DistributionPolicyWriteSerializer,
    CapitalDistributionCalculateSerializer,
    CapitalDistributionAccountMappingSerializer,
    CapitalDistributionRunActionSerializer,
    AppropriationStatementQuerySerializer,
    EntityScopeSerializer,
    FormationResolveSerializer,
    PolicyActionSerializer,
    TaxPolicyPatchSerializer,
    TaxPolicyWriteSerializer,
    TaxWorkingActionSerializer,
    TaxWorkingCalculateSerializer,
    TaxWorkingLineOverrideSerializer,
    WaveOneActivationSerializer,
    WaveOneMigrationSerializer,
    serialize_policy,
    serialize_tax_policy,
    serialize_tax_working,
)
from .migration_services import (
    apply_wave_one_migration,
    assess_wave_one_migration,
    set_wave_one_activation,
)
from .services import (
    approve_policy,
    create_policy,
    materialize_formation_profile,
    reject_policy,
    resolve_entity_formation,
    seed_policy_from_ownership,
    serialize_formation_profile,
    submit_policy,
    supersede_policy,
    update_draft_policy,
    calculate_distribution_run,
    serialize_distribution_run,
    serialize_account_mapping,
    upsert_account_mapping,
    distribution_mapping_readiness,
    submit_distribution_run,
    approve_distribution_run,
    post_distribution_run,
    reverse_distribution_run,
)
from .reporting import build_appropriation_statement
from .tax_services import (
    approve_tax_policy,
    create_tax_policy,
    reject_tax_policy,
    submit_tax_policy,
    supersede_tax_policy,
    update_draft_tax_policy,
)
from .tax_working_services import (
    approve_tax_working,
    calculate_tax_working,
    override_tax_working_line,
    reproduce_tax_working,
    reverse_tax_working,
    submit_tax_working,
)
from .tax_exports import (
    build_tax_working_export,
    render_tax_working_csv,
    render_tax_working_pdf,
    render_tax_working_xlsx,
    tax_working_filename,
)


VIEW_PERMISSIONS = (
    "capital_distribution.setup.view",
    "capital_distribution.policy.view",
    "capital_distribution.run.view",
)
MANAGE_PERMISSIONS = ("capital_distribution.setup.manage", "capital_distribution.policy.manage")
SUBMIT_PERMISSIONS = ("capital_distribution.policy.submit", "capital_distribution.policy.manage")
APPROVE_PERMISSIONS = ("capital_distribution.policy.approve",)
RUN_VIEW_PERMISSIONS = ("capital_distribution.run.view", "capital_distribution.policy.view")
RUN_CALCULATE_PERMISSIONS = ("capital_distribution.run.calculate",)
MAPPING_MANAGE_PERMISSIONS = ("capital_distribution.mapping.manage", "capital_distribution.setup.manage")
RUN_SUBMIT_PERMISSIONS = ("capital_distribution.run.submit",)
RUN_APPROVE_PERMISSIONS = ("capital_distribution.run.approve",)
RUN_POST_PERMISSIONS = ("capital_distribution.run.post",)
RUN_REVERSE_PERMISSIONS = ("capital_distribution.run.reverse",)
TAX_POLICY_VIEW_PERMISSIONS = ("capital_distribution.tax_policy.view",)
TAX_POLICY_MANAGE_PERMISSIONS = ("capital_distribution.tax_policy.manage",)
TAX_POLICY_SUBMIT_PERMISSIONS = (
    "capital_distribution.tax_policy.submit",
    "capital_distribution.tax_policy.manage",
)
TAX_POLICY_APPROVE_PERMISSIONS = ("capital_distribution.tax_policy.approve",)
TAX_WORKING_VIEW_PERMISSIONS = ("capital_distribution.tax_working.view",)
TAX_WORKING_CALCULATE_PERMISSIONS = ("capital_distribution.tax_working.calculate",)
TAX_WORKING_OVERRIDE_PERMISSIONS = ("capital_distribution.tax_working.override",)
TAX_WORKING_SUBMIT_PERMISSIONS = ("capital_distribution.tax_working.submit",)
TAX_WORKING_APPROVE_PERMISSIONS = ("capital_distribution.tax_working.approve",)
TAX_WORKING_REVERSE_PERMISSIONS = ("capital_distribution.tax_working.reverse",)
TAX_WORKING_EXPORT_PERMISSIONS = ("capital_distribution.tax_working.export",)
MIGRATION_VIEW_PERMISSIONS = ("capital_distribution.migration.view", "capital_distribution.setup.view")
MIGRATION_MANAGE_PERMISSIONS = ("capital_distribution.migration.manage", "capital_distribution.setup.manage")


logger = logging.getLogger("finacc.capital_distribution")


def _as_api_validation_error(exc: DjangoValidationError) -> ValidationError:
    if hasattr(exc, "message_dict"):
        return ValidationError(exc.message_dict)
    return ValidationError({"detail": exc.messages})


class CapitalDistributionAccessMixin(ScopedEntitlementMixin):
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def dispatch(self, request, *args, **kwargs):
        self._operation_context_tokens = bind_operation_context(request.headers.get("X-Correlation-ID"))
        self._operation_entity = None
        try:
            return super().dispatch(request, *args, **kwargs)
        finally:
            reset_operation_context(self._operation_context_tokens)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["X-Correlation-ID"] = current_correlation_id()
        return response

    def handle_exception(self, exc):
        try:
            response = super().handle_exception(exc)
        except Exception:
            self._record_operation_failure(exc, status.HTTP_500_INTERNAL_SERVER_ERROR)
            logger.exception(
                "capital_distribution_unexpected_error",
                extra={"correlation_id": current_correlation_id()},
            )
            return Response({
                "detail": "The operation could not be completed. Contact support with the correlation ID.",
                "code": "internal_error",
                "correlation_id": current_correlation_id(),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        self._record_operation_failure(exc, response.status_code)
        if isinstance(getattr(response, "data", None), dict):
            response.data.setdefault("correlation_id", current_correlation_id())
        return response

    def _record_operation_failure(self, exc, status_code):
        metadata = operation_metadata(
            operation=self.__class__.__name__,
            method=getattr(self.request, "method", ""),
            path=getattr(self.request, "path", ""),
            status_code=status_code,
            error_code=getattr(exc, "default_code", exc.__class__.__name__),
            entityfinid=getattr(self, "_operation_entityfinid_id", None),
            subentity_id=getattr(self, "_operation_subentity_id", None),
        )
        logger.warning(
            "capital_distribution_operation_failed",
            extra={"correlation_id": current_correlation_id(), **metadata},
        )
        entity = getattr(self, "_operation_entity", None)
        user = getattr(self.request, "user", None)
        if entity is not None and getattr(user, "is_authenticated", False):
            try:
                CapitalDistributionAuditEvent.objects.create(
                    entity=entity,
                    actor=user,
                    action="operation_failed",
                    correlation_id=current_correlation_id(),
                    metadata=metadata,
                )
            except Exception:
                logger.exception(
                    "capital_distribution_failure_audit_failed",
                    extra={"correlation_id": current_correlation_id()},
                )

    def require_permission(self, request, *, entity_id: int, codes: tuple[str, ...]) -> None:
        current = EffectivePermissionService.permission_codes_for_user(request.user, entity_id)
        if any(code in current for code in codes):
            return
        raise PermissionDenied({"detail": "You do not have permission to access capital and distribution setup."})

    def scoped_entity(self, request, *, entity_id, entityfinid_id=None, subentity_id=None, codes=VIEW_PERMISSIONS):
        entity = self.enforce_scope(
            request,
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
        )
        self.require_permission(request, entity_id=entity.id, codes=codes)
        self._operation_entity = entity
        self._operation_entityfinid_id = entityfinid_id
        self._operation_subentity_id = subentity_id
        return entity

    def scoped_policy(
        self,
        request,
        *,
        policy_id,
        entity_id,
        codes=VIEW_PERMISSIONS,
        requested_subentity_id=None,
        allow_global_for_branch=False,
    ):
        policy = (
            DistributionPolicyVersion.objects.filter(id=policy_id, entity_id=entity_id, isactive=True)
            .select_related("formation_profile", "entityfin", "subentity")
            .first()
        )
        if not policy:
            raise ValidationError({"policy": "Policy was not found for this entity."})
        scope_subentity_id = policy.subentity_id
        if allow_global_for_branch and scope_subentity_id is None:
            scope_subentity_id = requested_subentity_id
        self.scoped_entity(
            request,
            entity_id=entity_id,
            entityfinid_id=policy.entityfin_id,
            subentity_id=scope_subentity_id,
            codes=codes,
        )
        return policy

    def scoped_run(self, request, *, run_id, entity_id, codes=RUN_VIEW_PERMISSIONS):
        run = (
            CapitalDistributionRun.objects.filter(id=run_id, entity_id=entity_id, isactive=True)
            .select_related("formation_profile", "policy", "entityfin", "subentity")
            .prefetch_related("segments__policy", "segments__lines__stakeholder")
            .first()
        )
        if not run:
            raise ValidationError({"run": "Calculation run was not found for this entity."})
        self.scoped_entity(
            request,
            entity_id=entity_id,
            entityfinid_id=run.entityfin_id,
            subentity_id=run.subentity_id,
            codes=codes,
        )
        return run

    def scoped_tax_policy(self, request, *, tax_policy_id, entity_id, codes=TAX_POLICY_VIEW_PERMISSIONS):
        policy = (
            TaxPolicyVersion.objects.filter(id=tax_policy_id, entity_id=entity_id, isactive=True)
            .select_related("formation_profile", "entityfin")
            .first()
        )
        if not policy:
            raise ValidationError({"tax_policy": "Tax policy was not found for this entity."})
        self.scoped_entity(
            request,
            entity_id=entity_id,
            entityfinid_id=policy.entityfin_id,
            codes=codes,
        )
        return policy

    def scoped_tax_working(self, request, *, tax_working_id, entity_id, codes=TAX_WORKING_VIEW_PERMISSIONS):
        working = (
            CapitalDistributionTaxWorking.objects.filter(id=tax_working_id, entity_id=entity_id, isactive=True)
            .select_related("run", "tax_policy", "entityfin", "subentity")
            .prefetch_related("lines")
            .first()
        )
        if not working:
            raise ValidationError({"tax_working": "Tax working was not found for this entity."})
        self.scoped_entity(
            request,
            entity_id=entity_id,
            entityfinid_id=working.entityfin_id,
            subentity_id=working.subentity_id,
            codes=codes,
        )
        return working


class FormationProfileAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        resolution = resolve_entity_formation(entity)
        saved = EntityFormationProfile.objects.filter(entity=entity, isactive=True).order_by("-version_number", "-id").first()
        return Response(
            {
                "entity": entity.id,
                "resolution": resolution.as_dict(),
                "saved_profile": serialize_formation_profile(saved) if saved else None,
                "available_formations": [
                    {"value": value, "label": label}
                    for value, label in FormationType.choices
                    if value != FormationType.UNCONFIGURED
                ],
            }
        )

    def post(self, request):
        serializer = FormationResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(request, entity_id=scope["entity"], codes=MANAGE_PERMISSIONS)
        try:
            profile = materialize_formation_profile(
                entity=entity,
                actor=request.user,
                effective_from=scope.get("effective_from"),
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_formation_profile(profile), status=status.HTTP_201_CREATED)


class WaveOneMigrationAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = WaveOneMigrationSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope["entityfinid"],
            codes=MIGRATION_VIEW_PERMISSIONS,
        )
        entityfin = EntityFinancialYear.objects.filter(pk=scope["entityfinid"], entity=entity).first()
        if not entityfin:
            raise ValidationError({"entityfinid": "Financial year was not found for this entity."})
        try:
            return Response(assess_wave_one_migration(entity=entity, entityfin=entityfin))
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)

    def post(self, request):
        serializer = WaveOneMigrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope["entityfinid"],
            codes=MIGRATION_MANAGE_PERMISSIONS,
        )
        entityfin = EntityFinancialYear.objects.filter(pk=scope["entityfinid"], entity=entity).first()
        if not entityfin:
            raise ValidationError({"entityfinid": "Financial year was not found for this entity."})
        try:
            return Response(apply_wave_one_migration(
                entity=entity,
                entityfin=entityfin,
                actor=request.user,
            ))
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)


class WaveOneActivationAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = WaveOneMigrationSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope["entityfinid"],
            codes=MIGRATION_VIEW_PERMISSIONS,
        )
        entityfin = EntityFinancialYear.objects.filter(pk=scope["entityfinid"], entity=entity).first()
        if not entityfin:
            raise ValidationError({"entityfinid": "Financial year was not found for this entity."})
        return Response(assess_wave_one_migration(entity=entity, entityfin=entityfin))

    def post(self, request):
        serializer = WaveOneActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope["entityfinid"],
            codes=MIGRATION_MANAGE_PERMISSIONS,
        )
        entityfin = EntityFinancialYear.objects.filter(pk=scope["entityfinid"], entity=entity).first()
        if not entityfin:
            raise ValidationError({"entityfinid": "Financial year was not found for this entity."})
        try:
            return Response(set_wave_one_activation(
                entity=entity,
                entityfin=entityfin,
                enabled=scope["enabled"],
                actor=request.user,
            ))
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)


class DistributionPolicyListCreateAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        policies = (
            DistributionPolicyVersion.objects.filter(entity=entity, isactive=True)
            .select_related("formation_profile", "entityfin", "subentity")
            .prefetch_related("stakeholders")
            .order_by("-version_number", "-id")
        )
        if scope.get("entityfinid"):
            policies = policies.filter(entityfin_id=scope["entityfinid"])
        if scope.get("subentity"):
            policies = policies.filter(Q(subentity_id=scope["subentity"]) | Q(subentity__isnull=True))
        return Response({"count": policies.count(), "results": [serialize_policy(row) for row in policies[:100]]})

    def post(self, request):
        serializer = DistributionPolicyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        entity = self.scoped_entity(
            request,
            entity_id=data["entity"],
            entityfinid_id=data.get("entityfinid"),
            subentity_id=data.get("subentity"),
            codes=MANAGE_PERMISSIONS,
        )
        formation_profile = EntityFormationProfile.objects.filter(
            id=data.pop("formation_profile"), entity=entity, isactive=True
        ).first()
        if not formation_profile:
            raise ValidationError({"formation_profile": "Formation profile was not found for this entity."})
        data.pop("entity")
        entityfin_id = data.pop("entityfinid", None)
        subentity_id = data.pop("subentity", None)
        data["entityfin"] = EntityFinancialYear.objects.filter(id=entityfin_id, entity=entity).first() if entityfin_id else None
        data["subentity"] = SubEntity.objects.filter(id=subentity_id, entity=entity).first() if subentity_id else None
        try:
            policy = create_policy(
                entity=entity,
                formation_profile=formation_profile,
                payload=data,
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_policy(policy), status=status.HTTP_201_CREATED)


class DistributionPolicySeedAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = DistributionPolicySeedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        entity = self.scoped_entity(
            request,
            entity_id=data["entity"],
            entityfinid_id=data.get("entityfinid"),
            subentity_id=data.get("subentity"),
            codes=MANAGE_PERMISSIONS,
        )
        formation_profile = EntityFormationProfile.objects.filter(
            id=data.pop("formation_profile"), entity=entity, isactive=True
        ).first()
        if not formation_profile:
            raise ValidationError({"formation_profile": "Formation profile was not found for this entity."})
        data.pop("entity")
        entityfin_id = data.pop("entityfinid", None)
        subentity_id = data.pop("subentity", None)
        data["entityfin"] = (
            EntityFinancialYear.objects.filter(id=entityfin_id, entity=entity).first()
            if entityfin_id
            else None
        )
        data["subentity"] = (
            SubEntity.objects.filter(id=subentity_id, entity=entity).first()
            if subentity_id
            else None
        )
        try:
            policy = seed_policy_from_ownership(
                entity=entity,
                formation_profile=formation_profile,
                payload=data,
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_policy(policy), status=status.HTTP_201_CREATED)


class DistributionPolicyDetailAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, policy_id):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        policy = self.scoped_policy(
            request,
            policy_id=policy_id,
            entity_id=scope["entity"],
            requested_subentity_id=scope.get("subentity"),
            allow_global_for_branch=True,
        )
        return Response(serialize_policy(policy))

    def patch(self, request, policy_id):
        serializer = DistributionPolicyPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        entity_id = data.pop("entity")
        expected_updated_at = data.pop("expected_updated_at")
        policy = self.scoped_policy(request, policy_id=policy_id, entity_id=entity_id, codes=MANAGE_PERMISSIONS)
        entityfin_id = data.pop("entityfinid", policy.entityfin_id)
        subentity_id = data.pop("subentity", policy.subentity_id)
        self.enforce_scope(
            request,
            entity_id=entity_id,
            entityfinid_id=entityfin_id,
            subentity_id=subentity_id,
        )
        if "entityfinid" in serializer.validated_data:
            data["entityfin"] = EntityFinancialYear.objects.filter(id=entityfin_id, entity_id=entity_id).first() if entityfin_id else None
        if "subentity" in serializer.validated_data:
            data["subentity"] = SubEntity.objects.filter(id=subentity_id, entity_id=entity_id).first() if subentity_id else None
        try:
            policy = update_draft_policy(
                policy=policy,
                payload=data,
                actor=request.user,
                expected_updated_at=expected_updated_at,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_policy(policy))


class DistributionPolicyActionAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    action = ""

    def post(self, request, policy_id):
        serializer = PolicyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        permission_map = {
            "submit": SUBMIT_PERMISSIONS,
            "approve": APPROVE_PERMISSIONS,
            "reject": APPROVE_PERMISSIONS,
            "supersede": APPROVE_PERMISSIONS,
        }
        policy = self.scoped_policy(
            request,
            policy_id=policy_id,
            entity_id=entity_id,
            codes=permission_map[self.action],
        )
        reason = serializer.validated_data.get("reason", "")
        expected_updated_at = serializer.validated_data["expected_updated_at"]
        action_map = {
            "submit": submit_policy,
            "approve": approve_policy,
            "reject": reject_policy,
            "supersede": supersede_policy,
        }
        try:
            policy = action_map[self.action](
                policy=policy,
                actor=request.user,
                reason=reason,
                expected_updated_at=expected_updated_at,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_policy(policy))


class DistributionPolicySubmitAPIView(DistributionPolicyActionAPIView):
    action = "submit"


class DistributionPolicyApproveAPIView(DistributionPolicyActionAPIView):
    action = "approve"


class DistributionPolicyRejectAPIView(DistributionPolicyActionAPIView):
    action = "reject"


class DistributionPolicySupersedeAPIView(DistributionPolicyActionAPIView):
    action = "supersede"


class DistributionPolicyCompareAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, policy_id, other_policy_id):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity_id = scope["entity"]
        policy = self.scoped_policy(
            request,
            policy_id=policy_id,
            entity_id=entity_id,
            requested_subentity_id=scope.get("subentity"),
            allow_global_for_branch=True,
        )
        other = self.scoped_policy(
            request,
            policy_id=other_policy_id,
            entity_id=entity_id,
            requested_subentity_id=scope.get("subentity"),
            allow_global_for_branch=True,
        )
        left = serialize_policy(policy)
        right = serialize_policy(other)
        compared_fields = (
            "formation_type",
            "status",
            "effective_from",
            "effective_to",
            "governing_document_reference",
            "configuration",
            "schema_version",
            "notes",
        )
        changes = {
            field: {"from": left[field], "to": right[field]}
            for field in compared_fields
            if left[field] != right[field]
        }
        left_stakeholders = [
            {key: value for key, value in row.items() if key != "id"}
            for row in left["stakeholders"]
        ]
        right_stakeholders = [
            {key: value for key, value in row.items() if key != "id"}
            for row in right["stakeholders"]
        ]
        if left_stakeholders != right_stakeholders:
            changes["stakeholders"] = {
                "from": left_stakeholders,
                "to": right_stakeholders,
            }
        return Response({"from_policy": policy.id, "to_policy": other.id, "changes": changes})


class TaxPolicyListCreateAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        if scope.get("subentity"):
            raise ValidationError({"subentity": "Tax policy governance is maintained at entity level."})
        entity = self.scoped_entity(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            codes=TAX_POLICY_VIEW_PERMISSIONS,
        )
        policies = TaxPolicyVersion.objects.filter(entity=entity, isactive=True).select_related(
            "formation_profile", "entityfin"
        )
        if scope.get("entityfinid"):
            policies = policies.filter(Q(entityfin_id=scope["entityfinid"]) | Q(entityfin__isnull=True))
        return Response({"count": policies.count(), "results": [serialize_tax_policy(row) for row in policies[:100]]})

    def post(self, request):
        serializer = TaxPolicyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        entity = self.scoped_entity(
            request,
            entity_id=data.pop("entity"),
            entityfinid_id=data.get("entityfinid"),
            codes=TAX_POLICY_MANAGE_PERMISSIONS,
        )
        formation_profile = EntityFormationProfile.objects.filter(
            id=data.pop("formation_profile"), entity=entity, isactive=True
        ).first()
        if not formation_profile:
            raise ValidationError({"formation_profile": "Formation profile was not found for this entity."})
        entityfin_id = data.pop("entityfinid", None)
        data["entityfin"] = (
            EntityFinancialYear.objects.filter(id=entityfin_id, entity=entity, isactive=True).first()
            if entityfin_id
            else None
        )
        if entityfin_id and not data["entityfin"]:
            raise ValidationError({"entityfinid": "Active financial year was not found for this entity."})
        try:
            policy = create_tax_policy(
                entity=entity,
                formation_profile=formation_profile,
                payload=data,
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_tax_policy(policy), status=status.HTTP_201_CREATED)


class TaxPolicyDetailAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, tax_policy_id):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        policy = self.scoped_tax_policy(request, tax_policy_id=tax_policy_id, entity_id=entity_id)
        return Response(serialize_tax_policy(policy))

    def patch(self, request, tax_policy_id):
        serializer = TaxPolicyPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        entity_id = data.pop("entity")
        expected_updated_at = data.pop("expected_updated_at")
        policy = self.scoped_tax_policy(
            request,
            tax_policy_id=tax_policy_id,
            entity_id=entity_id,
            codes=TAX_POLICY_MANAGE_PERMISSIONS,
        )
        if "entityfinid" in data:
            entityfin_id = data.pop("entityfinid")
            data["entityfin"] = (
                EntityFinancialYear.objects.filter(id=entityfin_id, entity_id=entity_id, isactive=True).first()
                if entityfin_id
                else None
            )
            if entityfin_id and not data["entityfin"]:
                raise ValidationError({"entityfinid": "Active financial year was not found for this entity."})
        try:
            policy = update_draft_tax_policy(
                policy=policy,
                payload=data,
                actor=request.user,
                expected_updated_at=expected_updated_at,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_tax_policy(policy))


class TaxPolicyActionAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    action = ""

    def post(self, request, tax_policy_id):
        serializer = PolicyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        permission_map = {
            "submit": TAX_POLICY_SUBMIT_PERMISSIONS,
            "approve": TAX_POLICY_APPROVE_PERMISSIONS,
            "reject": TAX_POLICY_APPROVE_PERMISSIONS,
            "supersede": TAX_POLICY_APPROVE_PERMISSIONS,
        }
        policy = self.scoped_tax_policy(
            request,
            tax_policy_id=tax_policy_id,
            entity_id=data["entity"],
            codes=permission_map[self.action],
        )
        action_map = {
            "submit": submit_tax_policy,
            "approve": approve_tax_policy,
            "reject": reject_tax_policy,
            "supersede": supersede_tax_policy,
        }
        try:
            policy = action_map[self.action](
                policy=policy,
                actor=request.user,
                expected_updated_at=data["expected_updated_at"],
                reason=data.get("reason", ""),
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_tax_policy(policy))


class TaxPolicySubmitAPIView(TaxPolicyActionAPIView):
    action = "submit"


class TaxPolicyApproveAPIView(TaxPolicyActionAPIView):
    action = "approve"


class TaxPolicyRejectAPIView(TaxPolicyActionAPIView):
    action = "reject"


class TaxPolicySupersedeAPIView(TaxPolicyActionAPIView):
    action = "supersede"


class TaxWorkingListCalculateAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            codes=TAX_WORKING_VIEW_PERMISSIONS,
        )
        workings = (
            CapitalDistributionTaxWorking.objects.filter(entity=entity, isactive=True)
            .select_related("run", "tax_policy", "entityfin", "subentity")
            .prefetch_related("lines")
        )
        if scope.get("entityfinid"):
            workings = workings.filter(entityfin_id=scope["entityfinid"])
        if scope.get("subentity"):
            workings = workings.filter(subentity_id=scope["subentity"])
        return Response({"count": workings.count(), "results": [serialize_tax_working(row) for row in workings[:100]]})

    def post(self, request):
        serializer = TaxWorkingCalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        run = self.scoped_run(
            request,
            run_id=data["run"],
            entity_id=data["entity"],
            codes=TAX_WORKING_CALCULATE_PERMISSIONS,
        )
        tax_policy = self.scoped_tax_policy(
            request,
            tax_policy_id=data["tax_policy"],
            entity_id=data["entity"],
            codes=TAX_WORKING_CALCULATE_PERMISSIONS,
        )
        try:
            working = calculate_tax_working(
                run=run,
                tax_policy=tax_policy,
                idempotency_key=data["idempotency_key"],
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_tax_working(working), status=status.HTTP_201_CREATED)


class TaxWorkingDetailAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, tax_working_id):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        working = self.scoped_tax_working(
            request,
            tax_working_id=tax_working_id,
            entity_id=serializer.validated_data["entity"],
        )
        return Response(serialize_tax_working(working))


class TaxWorkingExportAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, tax_working_id):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        export_format = str(request.query_params.get("format", "")).strip().lower()
        renderers = {
            "csv": (render_tax_working_csv, "text/csv"),
            "xlsx": (render_tax_working_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "pdf": (render_tax_working_pdf, "application/pdf"),
        }
        if export_format not in renderers:
            raise ValidationError({"format": "Choose one of csv, xlsx, or pdf."})
        working = self.scoped_tax_working(
            request,
            tax_working_id=tax_working_id,
            entity_id=serializer.validated_data["entity"],
            codes=TAX_WORKING_EXPORT_PERMISSIONS,
        )
        renderer, content_type = renderers[export_format]
        response = HttpResponse(renderer(build_tax_working_export(working)), content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{tax_working_filename(working, export_format)}"'
        return response


class TaxWorkingLineOverrideAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, tax_working_id, line_id):
        serializer = TaxWorkingLineOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        working = self.scoped_tax_working(
            request,
            tax_working_id=tax_working_id,
            entity_id=data["entity"],
            codes=TAX_WORKING_OVERRIDE_PERMISSIONS,
        )
        line = CapitalDistributionTaxWorkingLine.objects.filter(id=line_id, working=working, isactive=True).first()
        if not line:
            raise ValidationError({"line": "Tax working line was not found for this working."})
        try:
            working = override_tax_working_line(
                line=line,
                allowable_amount=data["allowable_amount"],
                reason=data["reason"],
                evidence_references=data["evidence_references"],
                actor=request.user,
                expected_updated_at=data["expected_updated_at"],
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_tax_working(working))


class TaxWorkingReproduceAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, tax_working_id):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        working = self.scoped_tax_working(
            request,
            tax_working_id=tax_working_id,
            entity_id=serializer.validated_data["entity"],
        )
        try:
            result = reproduce_tax_working(working)
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(result)


class TaxWorkingActionAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    action = ""

    def post(self, request, tax_working_id):
        serializer = TaxWorkingActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        permissions_by_action = {
            "submit": TAX_WORKING_SUBMIT_PERMISSIONS,
            "approve": TAX_WORKING_APPROVE_PERMISSIONS,
            "reverse": TAX_WORKING_REVERSE_PERMISSIONS,
        }
        working = self.scoped_tax_working(
            request,
            tax_working_id=tax_working_id,
            entity_id=data["entity"],
            codes=permissions_by_action[self.action],
        )
        actions = {
            "submit": submit_tax_working,
            "approve": approve_tax_working,
            "reverse": reverse_tax_working,
        }
        try:
            working = actions[self.action](
                working=working,
                actor=request.user,
                expected_updated_at=data["expected_updated_at"],
                reason=data.get("reason", ""),
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_tax_working(working))


class TaxWorkingSubmitAPIView(TaxWorkingActionAPIView):
    action = "submit"


class TaxWorkingApproveAPIView(TaxWorkingActionAPIView):
    action = "approve"


class TaxWorkingReverseAPIView(TaxWorkingActionAPIView):
    action = "reverse"


class CapitalDistributionRunListCalculateAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            codes=RUN_VIEW_PERMISSIONS,
        )
        runs = CapitalDistributionRun.objects.filter(entity=entity, isactive=True).select_related(
            "formation_profile", "policy", "entityfin", "subentity"
        )
        if scope.get("entityfinid"):
            runs = runs.filter(entityfin_id=scope["entityfinid"])
        if scope.get("subentity"):
            runs = runs.filter(subentity_id=scope["subentity"])
        return Response({"count": runs.count(), "results": [serialize_distribution_run(run) for run in runs[:100]]})

    def post(self, request):
        serializer = CapitalDistributionCalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        entity = self.scoped_entity(
            request,
            entity_id=data["entity"],
            entityfinid_id=data.get("entityfinid"),
            subentity_id=data.get("subentity"),
            codes=RUN_CALCULATE_PERMISSIONS,
        )
        entityfin = EntityFinancialYear.objects.filter(id=data["entityfinid"], entity=entity, isactive=True).first()
        if not entityfin:
            raise ValidationError({"entityfinid": "An active financial year is required."})
        subentity = None
        if data.get("subentity"):
            subentity = SubEntity.objects.filter(id=data["subentity"], entity=entity, isactive=True).first()
            if not subentity:
                raise ValidationError({"subentity": "Active branch was not found for this entity."})
        try:
            run = calculate_distribution_run(
                entity=entity,
                entityfin=entityfin,
                subentity=subentity,
                period_from=data["period_from"],
                period_to=data["period_to"],
                cadence=data["cadence"],
                profit_source=data["profit_source"],
                supplied_profit=data.get("source_profit"),
                book_adjustments=data["book_adjustments"],
                balance_inputs=data.get("balances", []),
                idempotency_key=data["idempotency_key"],
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_distribution_run(run), status=status.HTTP_201_CREATED)


class CapitalDistributionRunDetailAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, run_id):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        run = self.scoped_run(request, run_id=run_id, entity_id=serializer.validated_data["entity"])
        return Response(serialize_distribution_run(run))


class CapitalDistributionOperationalHealthAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            codes=RUN_VIEW_PERMISSIONS,
        )
        now = timezone.now()
        aging_cutoff = now - timedelta(hours=24)
        recent_cutoff = now - timedelta(hours=24)
        runs = CapitalDistributionRun.objects.filter(entity=entity, isactive=True)
        if scope.get("entityfinid"):
            runs = runs.filter(entityfin_id=scope["entityfinid"])
        if scope.get("subentity"):
            runs = runs.filter(subentity_id=scope["subentity"])

        status_counts = {value: 0 for value, _ in CapitalDistributionRun.Status.choices}
        for row in runs.values("status"):
            status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        aging = runs.filter(
            status__in=(
                CapitalDistributionRun.Status.CALCULATED,
                CapitalDistributionRun.Status.SUBMITTED,
                CapitalDistributionRun.Status.APPROVED,
            ),
            updated_at__lt=aging_cutoff,
        )
        failures = CapitalDistributionAuditEvent.objects.filter(
            entity=entity,
            action="operation_failed",
            created_at__gte=recent_cutoff,
            isactive=True,
        ).order_by("-created_at", "-id")
        if scope.get("entityfinid"):
            failures = failures.filter(metadata__entityfinid=scope["entityfinid"])
        if scope.get("subentity"):
            failures = failures.filter(metadata__subentity_id=scope["subentity"])
        duration_events = CapitalDistributionAuditEvent.objects.filter(
            entity=entity,
            created_at__gte=recent_cutoff,
            isactive=True,
        ).order_by("-created_at", "-id")
        if scope.get("entityfinid"):
            duration_events = duration_events.filter(
                Q(run__entityfin_id=scope["entityfinid"])
                | Q(tax_working__entityfin_id=scope["entityfinid"])
                | Q(policy__entityfin_id=scope["entityfinid"])
                | Q(tax_policy__entityfin_id=scope["entityfinid"])
                | Q(metadata__entityfinid=scope["entityfinid"])
            )
        if scope.get("subentity"):
            duration_events = duration_events.filter(
                Q(run__subentity_id=scope["subentity"])
                | Q(tax_working__subentity_id=scope["subentity"])
                | Q(metadata__subentity_id=scope["subentity"])
            )
        durations = [
            float(row.metadata["duration_ms"])
            for row in duration_events[:1000]
            if isinstance(row.metadata, dict) and isinstance(row.metadata.get("duration_ms"), (int, float))
        ]
        stale_count = status_counts.get(CapitalDistributionRun.Status.STALE, 0)
        aging_count = aging.count()
        failure_count = failures.count()
        return Response({
            "scope": {
                "entity": entity.id,
                "entityfinid": scope.get("entityfinid"),
                "subentity": scope.get("subentity"),
            },
            "generated_at": now.isoformat(),
            "status": "attention" if stale_count or aging_count or failure_count else "healthy",
            "runs": {
                "total": runs.count(),
                "by_status": status_counts,
                "stale_count": stale_count,
                "aging_action_count": aging_count,
                "aging_threshold_hours": 24,
            },
            "failures": {
                "last_24_hours": failure_count,
                "recent": [
                    {
                        "correlation_id": row.correlation_id,
                        "operation": (row.metadata or {}).get("operation", ""),
                        "status_code": (row.metadata or {}).get("status_code"),
                        "error_code": (row.metadata or {}).get("error_code", ""),
                        "created_at": row.created_at.isoformat(),
                    }
                    for row in failures[:20]
                ],
            },
            "latency_ms": {
                "sample_count": len(durations),
                "average": round(sum(durations) / len(durations), 3) if durations else None,
                "maximum": round(max(durations), 3) if durations else None,
            },
        })


class CapitalDistributionAccountMappingAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        mappings = CapitalDistributionAccountMapping.objects.filter(entity=entity, isactive=True).select_related(
            "ownership", "capital_account__ledger", "current_account__ledger", "drawings_account__ledger"
        )
        policy = DistributionPolicyVersion.objects.filter(
            entity=entity, status=DistributionPolicyVersion.Status.APPROVED, isactive=True
        ).order_by("-effective_from", "-id").first()
        return Response({
            "count": mappings.count(),
            "results": [serialize_account_mapping(row) for row in mappings],
            "readiness": distribution_mapping_readiness(entity=entity, policy=policy),
        })

    def post(self, request):
        serializer = CapitalDistributionAccountMappingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        entity = self.scoped_entity(
            request,
            entity_id=data.pop("entity"),
            codes=MAPPING_MANAGE_PERMISSIONS,
        )
        ownership = data.pop("ownership")
        if ownership.entity_id != entity.id:
            raise ValidationError({"ownership": "Ownership row was not found for this entity."})
        for field in ("capital_account", "current_account", "drawings_account"):
            selected = data.get(field)
            if selected and selected.entity_id != entity.id:
                raise ValidationError({field: "Account was not found for this entity."})
        try:
            mapping = upsert_account_mapping(
                entity=entity,
                ownership=ownership,
                capital_account=data.get("capital_account"),
                current_account=data.get("current_account"),
                drawings_account=data.get("drawings_account"),
                effective_from=data.get("effective_from"),
                effective_to=data.get("effective_to"),
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_account_mapping(mapping), status=status.HTTP_201_CREATED)


class CapitalDistributionRunActionAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    action = ""

    def post(self, request, run_id):
        serializer = CapitalDistributionRunActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        permission_map = {
            "submit": RUN_SUBMIT_PERMISSIONS,
            "approve": RUN_APPROVE_PERMISSIONS,
            "post": RUN_POST_PERMISSIONS,
            "reverse": RUN_REVERSE_PERMISSIONS,
        }
        run = self.scoped_run(
            request,
            run_id=run_id,
            entity_id=data["entity"],
            codes=permission_map[self.action],
        )
        action_map = {
            "submit": submit_distribution_run,
            "approve": approve_distribution_run,
            "post": post_distribution_run,
            "reverse": reverse_distribution_run,
        }
        try:
            run = action_map[self.action](
                run=run,
                actor=request.user,
                expected_updated_at=data["expected_updated_at"],
                reason=data.get("reason", ""),
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc)
        return Response(serialize_distribution_run(run))


class CapitalDistributionRunSubmitAPIView(CapitalDistributionRunActionAPIView):
    action = "submit"


class CapitalDistributionRunApproveAPIView(CapitalDistributionRunActionAPIView):
    action = "approve"


class CapitalDistributionRunPostAPIView(CapitalDistributionRunActionAPIView):
    action = "post"


class CapitalDistributionRunReverseAPIView(CapitalDistributionRunActionAPIView):
    action = "reverse"


class AppropriationStatementAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = AppropriationStatementQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        entity = self.scoped_entity(
            request,
            entity_id=data["entity"],
            entityfinid_id=data["entityfinid"],
            subentity_id=data.get("subentity"),
            codes=RUN_VIEW_PERMISSIONS,
        )
        entityfin = EntityFinancialYear.objects.filter(id=data["entityfinid"], entity=entity).first()
        if not entityfin:
            raise ValidationError({"entityfinid": "Financial year was not found for this entity."})
        subentity = None
        if data.get("subentity"):
            subentity = SubEntity.objects.filter(id=data["subentity"], entity=entity).first()
            if not subentity:
                raise ValidationError({"subentity": "Branch was not found for this entity."})
        return Response(build_appropriation_statement(
            entity=entity,
            entityfin=entityfin,
            subentity=subentity,
            period_from=data["period_from"],
            period_to=data["period_to"],
        ))
