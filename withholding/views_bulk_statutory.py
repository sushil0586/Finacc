from __future__ import annotations

import secrets

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import ProductBulkJob
from entity.models import Entity
from withholding.bulk_statutory import (
    CONFIGS_SHEET,
    SECTIONS_SHEET,
    commit_configs_payload,
    commit_sections_payload,
    configs_export_payload,
    configs_template_payload,
    parse_payload,
    render_payload,
    sections_export_payload,
    sections_template_payload,
    validate_configs_payload,
    validate_sections_payload,
)


class SafeFormatNegotiation(DefaultContentNegotiation):
    def filter_renderers(self, renderers, format):
        if format and not any(renderer.format == format for renderer in renderers):
            return renderers
        return super().filter_renderers(renderers, format)


def _entity_from_request(request):
    raw = request.query_params.get("entity") or request.data.get("entity")
    if not raw:
        raise ValidationError({"entity": "entity is required."})
    return get_object_or_404(Entity, pk=int(raw))


def _entityfin_from_request(request):
    raw = request.query_params.get("entityfin") or request.query_params.get("entityfinid") or request.data.get("entityfin") or request.data.get("entityfinid")
    return int(raw) if raw not in (None, "") else None


def _fmt(request):
    fmt = (request.query_params.get("format") or request.data.get("format") or "xlsx").lower()
    if fmt not in ("xlsx", "csv"):
        raise ValidationError({"format": "Use xlsx or csv."})
    return fmt


class _BaseBulkMixin:
    permission_classes = [permissions.IsAuthenticated]
    content_negotiation_class = SafeFormatNegotiation

    def _job_response(self, result, job):
        return Response(
            {
                "job_id": job.id,
                "validation_token": job.validation_token,
                "summary": result.summary,
                "errors": result.errors,
                "can_commit": len(result.errors) == 0,
            }
        )


class TcsSectionsBulkTemplateAPIView(_BaseBulkMixin, APIView):
    def get(self, request):
        fmt = _fmt(request)
        content = render_payload(sections_template_payload(), fmt)
        if fmt == "xlsx":
            resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = 'attachment; filename="tcs_sections_bulk_template.xlsx"'
            return resp
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = 'attachment; filename="tcs_sections_bulk_template_csv.zip"'
        return resp


class TcsSectionsBulkExportAPIView(_BaseBulkMixin, APIView):
    def get(self, request):
        entity = _entity_from_request(request)
        fmt = _fmt(request)
        search = (request.query_params.get("search") or "").strip()
        data = sections_export_payload(search=search)
        content = render_payload(data, fmt)
        ProductBulkJob.objects.create(
            entity=entity,
            created_by=request.user,
            job_type=ProductBulkJob.JobType.EXPORT,
            status=ProductBulkJob.JobStatus.COMPLETED,
            file_format=fmt,
            summary={"rows": {SECTIONS_SHEET: len(data.get(SECTIONS_SHEET, []))}},
        )
        if fmt == "xlsx":
            resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = 'attachment; filename="tcs_sections_bulk_export.xlsx"'
            return resp
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = 'attachment; filename="tcs_sections_bulk_export_csv.zip"'
        return resp


class TcsSectionsBulkImportValidateAPIView(_BaseBulkMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        entity = _entity_from_request(request)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "Upload file is required."})
        fmt = _fmt(request)
        upsert_mode = request.data.get("upsert_mode") or ProductBulkJob.UpsertMode.UPSERT
        duplicate_strategy = request.data.get("duplicate_strategy") or ProductBulkJob.DuplicateStrategy.FAIL
        payload = parse_payload(upload.read(), fmt, SECTIONS_SHEET)
        result = validate_sections_payload(payload, upsert_mode=upsert_mode)
        token = secrets.token_hex(24)
        job = ProductBulkJob.objects.create(
            entity=entity,
            created_by=request.user,
            job_type=ProductBulkJob.JobType.VALIDATE,
            status=ProductBulkJob.JobStatus.COMPLETED if not result.errors else ProductBulkJob.JobStatus.FAILED,
            file_format=fmt,
            upsert_mode=upsert_mode,
            duplicate_strategy=duplicate_strategy,
            validation_token=token,
            input_filename=upload.name,
            payload=payload,
            summary=result.summary,
            errors=result.errors,
        )
        return self._job_response(result, job)


class TcsSectionsBulkImportCommitAPIView(_BaseBulkMixin, APIView):
    def post(self, request):
        entity = _entity_from_request(request)
        token = (request.data.get("validation_token") or "").strip()
        if not token:
            raise ValidationError({"validation_token": "validation_token is required."})
        vjob = get_object_or_404(ProductBulkJob, entity=entity, validation_token=token, job_type=ProductBulkJob.JobType.VALIDATE)
        if vjob.errors:
            raise ValidationError({"detail": "Cannot commit while validation has errors.", "error_count": len(vjob.errors)})
        upsert_mode = request.data.get("upsert_mode") or vjob.upsert_mode or ProductBulkJob.UpsertMode.UPSERT
        duplicate_strategy = request.data.get("duplicate_strategy") or vjob.duplicate_strategy or ProductBulkJob.DuplicateStrategy.FAIL
        result = commit_sections_payload(vjob.payload or {}, upsert_mode=upsert_mode, duplicate_strategy=duplicate_strategy)
        job = ProductBulkJob.objects.create(
            entity=entity,
            created_by=request.user,
            job_type=ProductBulkJob.JobType.IMPORT,
            status=ProductBulkJob.JobStatus.COMPLETED if not result.errors else ProductBulkJob.JobStatus.FAILED,
            file_format=vjob.file_format,
            upsert_mode=upsert_mode,
            duplicate_strategy=duplicate_strategy,
            summary=result.summary,
            errors=result.errors,
        )
        return Response({"job_id": job.id, "summary": result.summary, "errors": result.errors, "status": job.status})


class TcsConfigsBulkTemplateAPIView(_BaseBulkMixin, APIView):
    def get(self, request):
        entity = _entity_from_request(request)
        fmt = _fmt(request)
        entityfin = _entityfin_from_request(request)
        content = render_payload(configs_template_payload(entity.id, entityfin), fmt)
        if fmt == "xlsx":
            resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = 'attachment; filename="tcs_configs_bulk_template.xlsx"'
            return resp
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = 'attachment; filename="tcs_configs_bulk_template_csv.zip"'
        return resp


class TcsConfigsBulkExportAPIView(_BaseBulkMixin, APIView):
    def get(self, request):
        entity = _entity_from_request(request)
        fmt = _fmt(request)
        entityfin = _entityfin_from_request(request)
        search = (request.query_params.get("search") or "").strip()
        data = configs_export_payload(entity_id=entity.id, entityfin_id=entityfin, search=search)
        content = render_payload(data, fmt)
        ProductBulkJob.objects.create(
            entity=entity,
            created_by=request.user,
            job_type=ProductBulkJob.JobType.EXPORT,
            status=ProductBulkJob.JobStatus.COMPLETED,
            file_format=fmt,
            summary={"rows": {CONFIGS_SHEET: len(data.get(CONFIGS_SHEET, []))}},
        )
        if fmt == "xlsx":
            resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = 'attachment; filename="tcs_configs_bulk_export.xlsx"'
            return resp
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = 'attachment; filename="tcs_configs_bulk_export_csv.zip"'
        return resp


class TcsConfigsBulkImportValidateAPIView(_BaseBulkMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        entity = _entity_from_request(request)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "Upload file is required."})
        fmt = _fmt(request)
        entityfin = _entityfin_from_request(request)
        upsert_mode = request.data.get("upsert_mode") or ProductBulkJob.UpsertMode.UPSERT
        duplicate_strategy = request.data.get("duplicate_strategy") or ProductBulkJob.DuplicateStrategy.FAIL
        payload = parse_payload(upload.read(), fmt, CONFIGS_SHEET)
        result = validate_configs_payload(payload, upsert_mode=upsert_mode, default_entity=entity.id, default_entityfin=entityfin)
        token = secrets.token_hex(24)
        job = ProductBulkJob.objects.create(
            entity=entity,
            created_by=request.user,
            job_type=ProductBulkJob.JobType.VALIDATE,
            status=ProductBulkJob.JobStatus.COMPLETED if not result.errors else ProductBulkJob.JobStatus.FAILED,
            file_format=fmt,
            upsert_mode=upsert_mode,
            duplicate_strategy=duplicate_strategy,
            validation_token=token,
            input_filename=upload.name,
            payload=payload,
            summary=result.summary,
            errors=result.errors,
        )
        return self._job_response(result, job)


class TcsConfigsBulkImportCommitAPIView(_BaseBulkMixin, APIView):
    def post(self, request):
        entity = _entity_from_request(request)
        entityfin = _entityfin_from_request(request)
        token = (request.data.get("validation_token") or "").strip()
        if not token:
            raise ValidationError({"validation_token": "validation_token is required."})
        vjob = get_object_or_404(ProductBulkJob, entity=entity, validation_token=token, job_type=ProductBulkJob.JobType.VALIDATE)
        if vjob.errors:
            raise ValidationError({"detail": "Cannot commit while validation has errors.", "error_count": len(vjob.errors)})
        upsert_mode = request.data.get("upsert_mode") or vjob.upsert_mode or ProductBulkJob.UpsertMode.UPSERT
        duplicate_strategy = request.data.get("duplicate_strategy") or vjob.duplicate_strategy or ProductBulkJob.DuplicateStrategy.FAIL
        result = commit_configs_payload(
            vjob.payload or {},
            upsert_mode=upsert_mode,
            duplicate_strategy=duplicate_strategy,
            default_entity=entity.id,
            default_entityfin=entityfin,
        )
        job = ProductBulkJob.objects.create(
            entity=entity,
            created_by=request.user,
            job_type=ProductBulkJob.JobType.IMPORT,
            status=ProductBulkJob.JobStatus.COMPLETED if not result.errors else ProductBulkJob.JobStatus.FAILED,
            file_format=vjob.file_format,
            upsert_mode=upsert_mode,
            duplicate_strategy=duplicate_strategy,
            summary=result.summary,
            errors=result.errors,
        )
        return Response({"job_id": job.id, "summary": result.summary, "errors": result.errors, "status": job.status})


class TcsBulkJobDetailAPIView(_BaseBulkMixin, APIView):
    def get(self, request, job_id: int):
        entity = _entity_from_request(request)
        job = get_object_or_404(ProductBulkJob, pk=job_id, entity=entity)
        return Response(
            {
                "id": job.id,
                "job_type": job.job_type,
                "status": job.status,
                "file_format": job.file_format,
                "upsert_mode": job.upsert_mode,
                "duplicate_strategy": job.duplicate_strategy,
                "summary": job.summary,
                "error_count": len(job.errors or []),
                "createdon": job.createdon,
                "modifiedon": job.modifiedon,
            }
        )


class TcsBulkJobErrorsExportAPIView(_BaseBulkMixin, APIView):
    def get(self, request, job_id: int):
        entity = _entity_from_request(request)
        job = get_object_or_404(ProductBulkJob, pk=job_id, entity=entity)
        fmt = _fmt(request)
        payload = {"errors": job.errors or []}
        content = render_payload(payload, fmt)
        if fmt == "xlsx":
            resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = f'attachment; filename="tcs_bulk_errors_{job.id}.xlsx"'
            return resp
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="tcs_bulk_errors_{job.id}.zip"'
        return resp

