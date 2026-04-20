from __future__ import annotations

import secrets

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from assets.bulk_import import (
    AssetBulkJob,
    commit_payload,
    parse_payload,
    render_payload,
    template_payload,
    validate_payload,
)
from assets.models import AssetCategory, DepreciationRun, FixedAsset
from entity.models import Entity, EntityFinancialYear, SubEntity
from assets.serializers import (
    AssetCapitalizeSerializer,
    AssetCategorySerializer,
    AssetDisposalSerializer,
    AssetImpairSerializer,
    AssetSettingsSerializer,
    AssetTransferSerializer,
    DepreciationRunCalculateSerializer,
    DepreciationRunCreateSerializer,
    DepreciationRunSerializer,
    FixedAssetListSerializer,
    FixedAssetWriteSerializer,
)
from assets.services.asset_service import AssetService
from assets.services.settings import AssetSettingsService
from financial.models import Ledger
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class AssetScopedAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_ASSETS
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    @staticmethod
    def _parse_int(raw_value, field_name: str, *, required: bool) -> int | None:
        if raw_value in (None, "", "null", "None"):
            if required:
                raise ValidationError({field_name: f"{field_name} is required."})
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise ValidationError({field_name: f"{field_name} must be an integer."})
        return None if field_name == "subentity" and value == 0 else value

    def _scope_from_query(self, request, *, require_entity: bool = True, require_entityfinid: bool = False):
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=require_entity)
        if entity_id is None:
            return None, None, None
        subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity", required=False)
        entityfinid_id = self._parse_int(request.query_params.get("entityfinid"), "entityfinid", required=require_entityfinid)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        return entity_id, entityfinid_id, subentity_id

    def _scope_from_payload(self, request, payload, *, require_entityfinid: bool = False):
        entity_id = self._parse_int(payload.get("entity"), "entity", required=True)
        subentity_id = self._parse_int(payload.get("subentity"), "subentity", required=False)
        entityfinid_id = self._parse_int(payload.get("entityfinid"), "entityfinid", required=require_entityfinid)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        return entity_id, entityfinid_id, subentity_id

    @staticmethod
    def _asset_queryset(*, entity_id: int, subentity_id: int | None = None, search: str | None = None):
        qs = AssetService.asset_queryset(entity_id=entity_id, subentity_id=subentity_id, search=search)
        return qs

    @staticmethod
    def _run_queryset(*, entity_id: int, entityfinid_id: int | None = None, subentity_id: int | None = None):
        qs = DepreciationRun.objects.prefetch_related("lines__asset__category").filter(entity_id=entity_id)
        if entityfinid_id is not None:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        return qs

    def _scoped_asset(self, request, pk: int):
        asset = get_object_or_404(FixedAsset.objects.select_related("category", "ledger", "vendor_account", "subentity"), pk=pk)
        self.enforce_scope(request, entity_id=asset.entity_id, entityfinid_id=asset.entityfinid_id, subentity_id=asset.subentity_id)
        return asset

    def _scoped_run(self, request, pk: int):
        run = get_object_or_404(DepreciationRun.objects.prefetch_related("lines__asset__category"), pk=pk)
        self.enforce_scope(request, entity_id=run.entity_id, entityfinid_id=run.entityfinid_id, subentity_id=run.subentity_id)
        return run


class AssetSettingsAPIView(AssetScopedAPIView):
    subscription_access_mode = SubscriptionService.ACCESS_MODE_SETUP

    def get(self, request):
        entity_id, _, subentity_id = self._scope_from_query(request, require_entity=True)
        settings_obj = AssetSettingsService.get_settings(entity_id, subentity_id)
        return Response(AssetSettingsSerializer(settings_obj).data)

    def put(self, request):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected an object payload."})
        try:
            entity_id, _, subentity_id = self._scope_from_payload(request, request.data)
            updated = AssetSettingsService.upsert_settings(
                entity_id=entity_id,
                subentity_id=subentity_id,
                updates=request.data,
                user_id=request.user.id,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AssetSettingsSerializer(updated).data)


class AssetCategoryListCreateAPIView(AssetScopedAPIView, generics.ListCreateAPIView):
    serializer_class = AssetCategorySerializer

    def get_queryset(self):
        entity_id, _, subentity_id = self._scope_from_query(self.request, require_entity=True)
        qs = AssetCategory.objects.filter(entity_id=entity_id, is_active=True).order_by("name")
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.enforce_scope(
            request,
            entity_id=serializer.validated_data["entity"].id,
            subentity_id=getattr(serializer.validated_data.get("subentity"), "id", None),
        )
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AssetCategoryRetrieveUpdateAPIView(AssetScopedAPIView, generics.RetrieveUpdateAPIView):
    serializer_class = AssetCategorySerializer

    def get_queryset(self):
        return AssetCategory.objects.all()

    def get_object(self):
        obj = super().get_object()
        self.enforce_scope(
            self.request,
            entity_id=obj.entity_id,
            subentity_id=obj.subentity_id,
        )
        return obj

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class AssetCategoryDestroyAPIView(AssetScopedAPIView):

    def delete(self, request, pk: int):
        category = get_object_or_404(AssetCategory.objects.select_related("entity", "subentity"), pk=pk)
        self.enforce_scope(request, entity_id=category.entity_id, subentity_id=category.subentity_id)
        try:
            AssetService.archive_category(category=category, user_id=request.user.id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FixedAssetListCreateAPIView(AssetScopedAPIView, generics.ListCreateAPIView):

    def get_queryset(self):
        entity_id, _, subentity_id = self._scope_from_query(self.request, require_entity=True)
        search = self.request.query_params.get("search")
        qs = self._asset_queryset(entity_id=entity_id, subentity_id=subentity_id, search=search)
        category_id = self.request.query_params.get("category")
        status_value = self.request.query_params.get("status")
        if category_id:
            qs = qs.filter(category_id=category_id)
        if status_value:
            qs = qs.filter(status=status_value)
        return qs

    def get_serializer_class(self):
        return FixedAssetListSerializer if self.request.method == "GET" else FixedAssetWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity = serializer.validated_data["entity"]
        subentity = serializer.validated_data.get("subentity")
        entityfinid = serializer.validated_data.get("entityfinid")
        self.enforce_scope(
            request,
            entity_id=entity.id,
            entityfinid_id=getattr(entityfinid, "id", None),
            subentity_id=getattr(subentity, "id", None),
        )
        asset = AssetService.create_asset(data=serializer.validated_data, user_id=request.user.id)
        return Response(FixedAssetListSerializer(asset).data, status=status.HTTP_201_CREATED)


class FixedAssetRetrieveUpdateAPIView(AssetScopedAPIView, generics.RetrieveUpdateAPIView):

    def get_serializer_class(self):
        return FixedAssetListSerializer if self.request.method == "GET" else FixedAssetWriteSerializer

    def get_queryset(self):
        return FixedAsset.objects.select_related("category", "ledger", "vendor_account", "subentity")

    def get_object(self):
        obj = super().get_object()
        self.enforce_scope(
            self.request,
            entity_id=obj.entity_id,
            entityfinid_id=obj.entityfinid_id,
            subentity_id=obj.subentity_id,
        )
        return obj

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        self.enforce_scope(
            request,
            entity_id=instance.entity_id,
            entityfinid_id=instance.entityfinid_id,
            subentity_id=instance.subentity_id,
        )
        asset = AssetService.update_asset(instance=instance, data=serializer.validated_data, user_id=request.user.id)
        return Response(FixedAssetListSerializer(asset).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.enforce_scope(
            request,
            entity_id=instance.entity_id,
            entityfinid_id=instance.entityfinid_id,
            subentity_id=instance.subentity_id,
        )
        try:
            AssetService.archive_asset(asset=instance, user_id=request.user.id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FixedAssetDestroyAPIView(AssetScopedAPIView):

    def delete(self, request, pk: int):
        asset = get_object_or_404(FixedAsset.objects.select_related("category", "ledger", "vendor_account", "subentity"), pk=pk)
        self.enforce_scope(request, entity_id=asset.entity_id, entityfinid_id=asset.entityfinid_id, subentity_id=asset.subentity_id)
        try:
            AssetService.archive_asset(asset=asset, user_id=request.user.id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FixedAssetCapitalizeAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        asset = self._scoped_asset(request, pk)
        serializer = AssetCapitalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.capitalize_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class FixedAssetImpairAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        asset = self._scoped_asset(request, pk)
        serializer = AssetImpairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.impair_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class FixedAssetTransferAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        asset = self._scoped_asset(request, pk)
        serializer = AssetTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.transfer_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class FixedAssetDisposeAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        asset = self._scoped_asset(request, pk)
        serializer = AssetDisposalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = AssetService.dispose_asset(asset=asset, user_id=request.user.id, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FixedAssetListSerializer(asset).data)


class AssetMetaAPIView(AssetScopedAPIView):

    def get(self, request):
        entity_id, _, subentity_id = self._scope_from_query(request, require_entity=True)
        categories = AssetCategory.objects.filter(entity_id=entity_id, is_active=True)
        if subentity_id:
            categories = categories.filter(subentity_id=subentity_id)
        ledgers = Ledger.objects.filter(entity_id=entity_id).order_by("name").values("id", "name", "ledger_code", "accounthead_id")
        return Response(
            {
                "choices": {
                    "asset_statuses": [{"value": code, "label": label} for code, label in FixedAsset.AssetStatus.choices],
                    "depreciation_methods": [{"value": code, "label": label} for code, label in FixedAsset.DepreciationMethod.choices],
                },
                "categories": list(categories.values("id", "code", "name", "nature")),
                "ledgers": list(ledgers),
            }
        )


class AssetBulkAPIView(AssetScopedAPIView):
    parser_classes = [MultiPartParser, FormParser]

    bulk_scope_type = ""
    bulk_filename_prefix = "assets_bulk"

    def _scope_from_request(self, request, *, require_entityfinid: bool = False):
        return self._scope_from_payload(request, request.data, require_entityfinid=require_entityfinid)

    @staticmethod
    def _resolve_format(raw_format: str | None, filename: str | None = None) -> str:
        fmt = (raw_format or "").strip().lower()
        if not fmt and filename:
            fmt = "xlsx" if filename.lower().endswith(".xlsx") else "csv"
        if fmt not in {"xlsx", "csv"}:
            raise ValidationError({"format": "Use xlsx or csv."})
        return fmt

    def _template_response(self, request):
        fmt = self._resolve_format(request.query_params.get("format"), None)
        payload = template_payload(self.bulk_scope_type)
        content = render_payload(payload, fmt)
        if fmt == "xlsx":
            resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = f'attachment; filename="{self.bulk_filename_prefix}_template.xlsx"'
            return resp
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="{self.bulk_filename_prefix}_template_csv.zip"'
        return resp

    def _validate_response(self, request):
        entity_id, entityfinid_id, subentity_id = self._scope_from_request(request, require_entityfinid=False)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "Upload file is required."})
        fmt = self._resolve_format(request.data.get("format"), upload.name)
        payload = parse_payload(upload.read(), fmt, self.bulk_scope_type)
        entity = get_object_or_404(Entity, pk=entity_id)
        subentity = None
        if subentity_id is not None:
            subentity = get_object_or_404(SubEntity, pk=subentity_id, entity_id=entity_id)
        entityfinid = None
        if entityfinid_id is not None:
            entityfinid = get_object_or_404(EntityFinancialYear, pk=entityfinid_id, entity_id=entity_id)
        self.enforce_scope(
            request,
            entity_id=entity.id,
            entityfinid_id=getattr(entityfinid, "id", None),
            subentity_id=getattr(subentity, "id", None),
        )
        upsert_mode = (request.data.get("upsert_mode") or AssetBulkJob.UpsertMode.UPSERT)
        duplicate_strategy = (request.data.get("duplicate_strategy") or AssetBulkJob.DuplicateStrategy.FAIL)
        token = secrets.token_hex(24)
        result = validate_payload(
            payload,
            entity,
            self.bulk_scope_type,
            subentity=subentity,
            entityfinid=entityfinid,
            upsert_mode=upsert_mode,
        )
        job = AssetBulkJob.objects.create(
            entity=entity,
            subentity=subentity,
            created_by=request.user,
            scope_type=self.bulk_scope_type,
            job_type=AssetBulkJob.JobType.VALIDATE,
            status=AssetBulkJob.JobStatus.COMPLETED if not result.errors else AssetBulkJob.JobStatus.FAILED,
            file_format=fmt,
            upsert_mode=upsert_mode,
            duplicate_strategy=duplicate_strategy,
            validation_token=token,
            input_filename=upload.name,
            payload=payload,
            summary=result.summary,
            errors=result.errors,
        )
        return Response(
            {
                "job_id": job.id,
                "validation_token": token,
                "summary": result.summary,
                "errors": result.errors,
                "can_commit": len(result.errors) == 0,
            }
        )

    def _commit_response(self, request):
        entity_id, entityfinid_id, subentity_id = self._scope_from_request(request, require_entityfinid=False)
        entity = get_object_or_404(Entity, pk=entity_id)
        subentity = None
        if subentity_id is not None:
            subentity = get_object_or_404(SubEntity, pk=subentity_id, entity_id=entity_id)
        entityfinid = None
        if entityfinid_id is not None:
            entityfinid = get_object_or_404(EntityFinancialYear, pk=entityfinid_id, entity_id=entity_id)
        self.enforce_scope(
            request,
            entity_id=entity.id,
            entityfinid_id=getattr(entityfinid, "id", None),
            subentity_id=getattr(subentity, "id", None),
        )
        token = (request.data.get("validation_token") or "").strip()
        if not token:
            raise ValidationError({"validation_token": "validation_token is required."})
        vjob = get_object_or_404(
            AssetBulkJob,
            entity=entity,
            scope_type=self.bulk_scope_type,
            validation_token=token,
            job_type=AssetBulkJob.JobType.VALIDATE,
        )
        if vjob.errors:
            raise ValidationError({"detail": "Cannot commit while validation has errors.", "error_count": len(vjob.errors)})
        upsert_mode = (request.data.get("upsert_mode") or vjob.upsert_mode or AssetBulkJob.UpsertMode.UPSERT)
        duplicate_strategy = (request.data.get("duplicate_strategy") or vjob.duplicate_strategy or AssetBulkJob.DuplicateStrategy.FAIL)
        result = commit_payload(
            vjob.payload or {},
            entity,
            self.bulk_scope_type,
            subentity=subentity,
            entityfinid=entityfinid,
            upsert_mode=upsert_mode,
            duplicate_strategy=duplicate_strategy,
            user_id=request.user.id,
        )
        job = AssetBulkJob.objects.create(
            entity=entity,
            subentity=subentity,
            created_by=request.user,
            scope_type=self.bulk_scope_type,
            job_type=AssetBulkJob.JobType.IMPORT,
            status=AssetBulkJob.JobStatus.COMPLETED if not result.errors else AssetBulkJob.JobStatus.FAILED,
            file_format=vjob.file_format,
            upsert_mode=upsert_mode,
            duplicate_strategy=duplicate_strategy,
            summary=result.summary,
            errors=result.errors,
        )
        return Response(
            {
                "job_id": job.id,
                "summary": result.summary,
                "errors": result.errors,
                "status": job.status,
            },
            status=status.HTTP_200_OK,
        )

    def _job_detail_response(self, request, job_id: int):
        entity_id, _, subentity_id = super()._scope_from_query(request, require_entity=True, require_entityfinid=False)
        entity = get_object_or_404(Entity, pk=entity_id)
        filters = {"pk": job_id, "entity": entity, "scope_type": self.bulk_scope_type}
        if subentity_id is not None:
            filters["subentity_id"] = subentity_id
        self.enforce_scope(request, entity_id=entity.id, subentity_id=subentity_id)
        job = get_object_or_404(AssetBulkJob, **filters)
        return Response(
            {
                "id": job.id,
                "scope_type": job.scope_type,
                "job_type": job.job_type,
                "status": job.status,
                "file_format": job.file_format,
                "upsert_mode": job.upsert_mode,
                "duplicate_strategy": job.duplicate_strategy,
                "summary": job.summary,
                "error_count": len(job.errors or []),
                "created_at": job.created_at,
                "updated_at": job.updated_at,
            }
        )

    def _job_errors_response(self, request, job_id: int):
        entity_id, _, subentity_id = super()._scope_from_query(request, require_entity=True, require_entityfinid=False)
        entity = get_object_or_404(Entity, pk=entity_id)
        filters = {"pk": job_id, "entity": entity, "scope_type": self.bulk_scope_type}
        if subentity_id is not None:
            filters["subentity_id"] = subentity_id
        self.enforce_scope(request, entity_id=entity.id, subentity_id=subentity_id)
        job = get_object_or_404(AssetBulkJob, **filters)
        fmt = self._resolve_format(request.query_params.get("format"), None)
        payload = {"errors": job.errors or []}
        content = render_payload(payload, fmt)
        if fmt == "xlsx":
            resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = f'attachment; filename="{self.bulk_filename_prefix}_errors_{job.id}.xlsx"'
            return resp
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="{self.bulk_filename_prefix}_errors_{job.id}.zip"'
        return resp


class AssetCategoryBulkTemplateAPIView(AssetBulkAPIView):
    bulk_scope_type = AssetBulkJob.ScopeType.CATEGORY
    bulk_filename_prefix = "asset_categories_bulk"

    def get(self, request):
        return self._template_response(request)


class AssetCategoryBulkImportValidateAPIView(AssetBulkAPIView):
    bulk_scope_type = AssetBulkJob.ScopeType.CATEGORY
    bulk_filename_prefix = "asset_categories_bulk"

    def post(self, request):
        return self._validate_response(request)


class AssetCategoryBulkImportCommitAPIView(AssetBulkAPIView):
    bulk_scope_type = AssetBulkJob.ScopeType.CATEGORY
    bulk_filename_prefix = "asset_categories_bulk"

    def post(self, request):
        return self._commit_response(request)


class AssetCategoryBulkJobDetailAPIView(AssetBulkAPIView):
    bulk_scope_type = AssetBulkJob.ScopeType.CATEGORY
    bulk_filename_prefix = "asset_categories_bulk"

    def get(self, request, job_id: int):
        return self._job_detail_response(request, job_id)


class AssetCategoryBulkJobErrorsExportAPIView(AssetBulkAPIView):
    bulk_scope_type = AssetBulkJob.ScopeType.CATEGORY
    bulk_filename_prefix = "asset_categories_bulk"

    def get(self, request, job_id: int):
        return self._job_errors_response(request, job_id)


class FixedAssetBulkTemplateAPIView(AssetBulkAPIView):
    bulk_scope_type = AssetBulkJob.ScopeType.ASSET
    bulk_filename_prefix = "fixed_assets_bulk"

    def get(self, request):
        return self._template_response(request)


class FixedAssetBulkImportValidateAPIView(AssetBulkAPIView):
    bulk_scope_type = AssetBulkJob.ScopeType.ASSET
    bulk_filename_prefix = "fixed_assets_bulk"

    def post(self, request):
        return self._validate_response(request)


class FixedAssetBulkImportCommitAPIView(AssetBulkAPIView):
    bulk_scope_type = AssetBulkJob.ScopeType.ASSET
    bulk_filename_prefix = "fixed_assets_bulk"

    def post(self, request):
        return self._commit_response(request)


class FixedAssetBulkJobDetailAPIView(AssetBulkAPIView):
    bulk_scope_type = AssetBulkJob.ScopeType.ASSET
    bulk_filename_prefix = "fixed_assets_bulk"

    def get(self, request, job_id: int):
        return self._job_detail_response(request, job_id)


class FixedAssetBulkJobErrorsExportAPIView(AssetBulkAPIView):
    bulk_scope_type = AssetBulkJob.ScopeType.ASSET
    bulk_filename_prefix = "fixed_assets_bulk"

    def get(self, request, job_id: int):
        return self._job_errors_response(request, job_id)


class DepreciationRunListCreateAPIView(AssetScopedAPIView, generics.ListCreateAPIView):

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(self.request, require_entity=True, require_entityfinid=False)
        qs = self._run_queryset(entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id).order_by("-period_to", "-id")
        return qs

    def get_serializer_class(self):
        return DepreciationRunSerializer if self.request.method == "GET" else DepreciationRunCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity = serializer.validated_data["entity"]
        entityfinid = serializer.validated_data["entityfinid"]
        subentity = serializer.validated_data.get("subentity")
        self.enforce_scope(
            request,
            entity_id=entity.id,
            entityfinid_id=entityfinid.id,
            subentity_id=getattr(subentity, "id", None),
        )
        run = serializer.save(created_by=request.user, updated_by=request.user)
        return Response(DepreciationRunSerializer(run).data, status=status.HTTP_201_CREATED)


class DepreciationRunRetrieveAPIView(AssetScopedAPIView, generics.RetrieveAPIView):
    serializer_class = DepreciationRunSerializer

    def get_queryset(self):
        return DepreciationRun.objects.prefetch_related("lines__asset__category")

    def get_object(self):
        obj = super().get_object()
        self.enforce_scope(
            self.request,
            entity_id=obj.entity_id,
            entityfinid_id=obj.entityfinid_id,
            subentity_id=obj.subentity_id,
        )
        return obj


class DepreciationRunCalculateAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        run = self._scoped_run(request, pk)
        serializer = DepreciationRunCalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = AssetService.calculate_run(run=run, category_id=serializer.validated_data.get("category_id"), user_id=request.user.id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DepreciationRunSerializer(run).data)


class DepreciationRunPostAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        run = self._scoped_run(request, pk)
        try:
            run = AssetService.post_run(run=run, user_id=request.user.id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DepreciationRunSerializer(run).data)


class DepreciationRunCancelAPIView(AssetScopedAPIView):

    def post(self, request, pk: int):
        run = self._scoped_run(request, pk)
        try:
            run = AssetService.cancel_run(run=run, user_id=request.user.id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DepreciationRunSerializer(run).data)
