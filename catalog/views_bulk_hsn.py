from __future__ import annotations

import secrets

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import Entity

from .bulk_hsn_sac import (
    commit_payload,
    export_payload,
    parse_payload,
    render_payload,
    template_payload,
    validate_payload,
)
from .models import ProductBulkJob


class SafeFormatNegotiation(DefaultContentNegotiation):
    def filter_renderers(self, renderers, format):
        if format and not any(renderer.format == format for renderer in renderers):
            return renderers
        return super().filter_renderers(renderers, format)


def _entity_from_request(request):
    raw = request.query_params.get("entity") or request.data.get("entity")
    if not raw:
        raise ValidationError({"entity": "entity query param is required."})
    return get_object_or_404(Entity, pk=int(raw))


class HsnSacBulkTemplateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    content_negotiation_class = SafeFormatNegotiation

    def get(self, request):
        fmt = (request.query_params.get("format") or "xlsx").lower()
        if fmt not in ("xlsx", "csv"):
            raise ValidationError({"format": "Use xlsx or csv."})
        content = render_payload(template_payload(), fmt)
        if fmt == "xlsx":
            resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = 'attachment; filename="hsn_sac_bulk_template.xlsx"'
            return resp
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = 'attachment; filename="hsn_sac_bulk_template_csv.zip"'
        return resp


class HsnSacBulkExportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    content_negotiation_class = SafeFormatNegotiation

    def get(self, request):
        entity = _entity_from_request(request)
        fmt = (request.query_params.get("format") or "xlsx").lower()
        search = (request.query_params.get("search") or "").strip()
        if fmt not in ("xlsx", "csv"):
            raise ValidationError({"format": "Use xlsx or csv."})
        data = export_payload(entity, search=search)
        content = render_payload(data, fmt)
        ProductBulkJob.objects.create(
            entity=entity,
            created_by=request.user,
            job_type=ProductBulkJob.JobType.EXPORT,
            status=ProductBulkJob.JobStatus.COMPLETED,
            file_format=fmt,
            summary={"rows": {"hsn_sac": len(data.get("hsn_sac", []))}},
        )
        if fmt == "xlsx":
            resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = 'attachment; filename="hsn_sac_bulk_export.xlsx"'
            return resp
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = 'attachment; filename="hsn_sac_bulk_export_csv.zip"'
        return resp


class HsnSacBulkImportValidateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    content_negotiation_class = SafeFormatNegotiation

    def post(self, request):
        entity = _entity_from_request(request)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "Upload file is required."})
        fmt = (request.data.get("format") or "").strip().lower()
        if not fmt:
            fmt = "xlsx" if upload.name.lower().endswith(".xlsx") else "csv"
        if fmt not in ("xlsx", "csv"):
            raise ValidationError({"format": "Use xlsx or csv."})

        payload = parse_payload(upload.read(), fmt)
        result = validate_payload(payload, entity)
        token = secrets.token_hex(24)
        job = ProductBulkJob.objects.create(
            entity=entity,
            created_by=request.user,
            job_type=ProductBulkJob.JobType.VALIDATE,
            status=ProductBulkJob.JobStatus.COMPLETED if not result.errors else ProductBulkJob.JobStatus.FAILED,
            file_format=fmt,
            upsert_mode=(request.data.get("upsert_mode") or ProductBulkJob.UpsertMode.UPSERT),
            duplicate_strategy=(request.data.get("duplicate_strategy") or ProductBulkJob.DuplicateStrategy.FAIL),
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


class HsnSacBulkImportCommitAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    content_negotiation_class = SafeFormatNegotiation

    def post(self, request):
        entity = _entity_from_request(request)
        token = (request.data.get("validation_token") or "").strip()
        if not token:
            raise ValidationError({"validation_token": "validation_token is required."})
        vjob = get_object_or_404(ProductBulkJob, entity=entity, validation_token=token, job_type=ProductBulkJob.JobType.VALIDATE)
        if vjob.errors:
            raise ValidationError({"detail": "Cannot commit while validation has errors.", "error_count": len(vjob.errors)})
        if not (vjob.payload or {}).get("hsn_sac"):
            raise ValidationError({"detail": "No import rows found in validated payload."})

        upsert_mode = (request.data.get("upsert_mode") or vjob.upsert_mode or ProductBulkJob.UpsertMode.UPSERT)
        duplicate_strategy = (request.data.get("duplicate_strategy") or vjob.duplicate_strategy or ProductBulkJob.DuplicateStrategy.FAIL)
        result = commit_payload(vjob.payload or {}, entity, upsert_mode=upsert_mode, duplicate_strategy=duplicate_strategy)
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
        return Response(
            {
                "job_id": job.id,
                "summary": result.summary,
                "errors": result.errors,
                "status": job.status,
            },
            status=status.HTTP_200_OK,
        )


class HsnSacBulkJobDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    content_negotiation_class = SafeFormatNegotiation

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


class HsnSacBulkJobErrorsExportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    content_negotiation_class = SafeFormatNegotiation

    def get(self, request, job_id: int):
        entity = _entity_from_request(request)
        job = get_object_or_404(ProductBulkJob, pk=job_id, entity=entity)
        fmt = (request.query_params.get("format") or "xlsx").lower()
        if fmt not in ("xlsx", "csv"):
            raise ValidationError({"format": "Use xlsx or csv."})
        payload = {"hsn_sac_errors": job.errors or []}
        content = render_payload(payload, "xlsx" if fmt == "xlsx" else "csv")
        if fmt == "xlsx":
            resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = f'attachment; filename="hsn_sac_bulk_errors_{job.id}.xlsx"'
            return resp
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="hsn_sac_bulk_errors_{job.id}.zip"'
        return resp
