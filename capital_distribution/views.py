from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.models import EntityFinancialYear, SubEntity
from rbac.services import EffectivePermissionService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService

from .models import CapitalDistributionAccountMapping, CapitalDistributionRun, DistributionPolicyVersion, EntityFormationProfile, FormationType
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
    serialize_policy,
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


def _as_api_validation_error(exc: DjangoValidationError) -> ValidationError:
    if hasattr(exc, "message_dict"):
        return ValidationError(exc.message_dict)
    return ValidationError({"detail": exc.messages})


class CapitalDistributionAccessMixin(ScopedEntitlementMixin):
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

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
        return entity

    def scoped_policy(self, request, *, policy_id, entity_id, codes=VIEW_PERMISSIONS):
        entity = self.scoped_entity(request, entity_id=entity_id, codes=codes)
        policy = (
            DistributionPolicyVersion.objects.filter(id=policy_id, entity=entity, isactive=True)
            .select_related("formation_profile", "entityfin", "subentity")
            .first()
        )
        if not policy:
            raise ValidationError({"policy": "Policy was not found for this entity."})
        return policy

    def scoped_run(self, request, *, run_id, entity_id, codes=RUN_VIEW_PERMISSIONS):
        entity = self.scoped_entity(request, entity_id=entity_id, codes=codes)
        run = (
            CapitalDistributionRun.objects.filter(id=run_id, entity=entity, isactive=True)
            .select_related("formation_profile", "policy", "entityfin", "subentity")
            .prefetch_related("segments__policy", "segments__lines__stakeholder")
            .first()
        )
        if not run:
            raise ValidationError({"run": "Calculation run was not found for this entity."})
        return run


class FormationProfileAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.scoped_entity(request, entity_id=scope["entity"])
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
            policies = policies.filter(subentity_id=scope["subentity"])
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
        policy = self.scoped_policy(request, policy_id=policy_id, entity_id=serializer.validated_data["entity"])
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
        entity_id = serializer.validated_data["entity"]
        policy = self.scoped_policy(request, policy_id=policy_id, entity_id=entity_id)
        other = self.scoped_policy(request, policy_id=other_policy_id, entity_id=entity_id)
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


class CapitalDistributionAccountMappingAPIView(CapitalDistributionAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = EntityScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        entity = self.scoped_entity(request, entity_id=serializer.validated_data["entity"])
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
