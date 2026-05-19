from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import Entity
from invoice_import.models import ImportJob, ImportProfile
from invoice_import.serializers import (
    ImportJobCreateSerializer,
    ImportJobSerializer,
    ImportProfileSerializer,
    ImportProfileWriteSerializer,
)
from invoice_import.services import (
    build_template_content,
    create_validated_job,
    export_job_errors,
    commit_job,
)
from purchase.views.rbac import require_purchase_request_permission
from sales.views.sales_invoice_views import require_sales_request_permission


class InvoiceImportBaseAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    module: str = ""

    def _get_entity(self, request) -> Entity:
        raw = request.query_params.get("entity") or request.data.get("entity")
        if not raw:
            raise ValidationError({"entity": "entity is required."})
        entity = get_object_or_404(Entity, pk=int(raw))
        if self.module == ImportJob.Module.SALES:
            require_sales_request_permission(user=request.user, entity_id=entity.id, doc_type=1, action="create")
        else:
            require_purchase_request_permission(user=request.user, entity_id=entity.id, doc_type=1, action="create")
        return entity

    def _get_job(self, request, job_id: int) -> ImportJob:
        entity = self._get_entity(request)
        return get_object_or_404(ImportJob.objects.prefetch_related("rows"), pk=job_id, entity=entity, module=self.module)

    def _get_profile(self, request, profile_id: int) -> ImportProfile:
        entity = self._get_entity(request)
        return get_object_or_404(ImportProfile, pk=profile_id, entity=entity, module=self.module)


class InvoiceImportTemplateAPIView(InvoiceImportBaseAPIView):
    def get(self, request):
        entity = self._get_entity(request)
        mode = request.query_params.get("mode") or ImportJob.Mode.OUTSTANDING_ONLY
        detail_level = request.query_params.get("detail_level") or ImportJob.DetailLevel.HEADER_ONLY
        content = build_template_content(module=self.module, mode=mode, detail_level=detail_level, fmt="xlsx")
        filename = f"{self.module}_{mode}_{detail_level}_template.xlsx"
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class InvoiceImportJobCreateAPIView(InvoiceImportBaseAPIView):
    def post(self, request):
        serializer = ImportJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity = self._get_entity(request)
        data = serializer.validated_data
        profile = None
        if data.get("profile"):
            profile = get_object_or_404(ImportProfile, pk=int(data["profile"]), entity=entity, module=self.module)
        upload = data["file"]
        fmt = "xlsx" if upload.name.lower().endswith(".xlsx") else "csv"
        job = create_validated_job(
            entity=entity,
            user=request.user,
            module=self.module,
            mode=data["mode"],
            detail_level=data["detail_level"],
            stock_replay=bool(data["stock_replay"]),
            compliance_mode=data["compliance_mode"],
            withholding_mode=data["withholding_mode"],
            document_number_strategy=data["document_number_strategy"],
            source_system=data["source_system"],
            filename=upload.name,
            fmt=fmt,
            file_bytes=upload.read(),
            profile=profile,
        )
        return Response(
            {
                "job": ImportJobSerializer(job).data,
                "can_commit": job.status == ImportJob.Status.VALIDATED,
            },
            status=status.HTTP_201_CREATED,
        )


class InvoiceImportJobDetailAPIView(InvoiceImportBaseAPIView):
    def get(self, request, job_id: int):
        job = self._get_job(request, job_id)
        data = ImportJobSerializer(job).data
        data["rows"] = [
            {
                "id": row.id,
                "row_no": row.row_no,
                "group_key": row.group_key,
                "status": row.status,
                "errors": row.errors,
                "warnings": row.warnings,
            }
            for row in job.rows.order_by("row_no")
        ]
        return Response(data)


class InvoiceImportJobCommitAPIView(InvoiceImportBaseAPIView):
    def post(self, request, job_id: int):
        job = self._get_job(request, job_id)
        job = commit_job(job=job, user=request.user)
        payload = ImportJobSerializer(job).data
        if job.status == ImportJob.Status.COMMITTED:
            return Response(payload, status=status.HTTP_200_OK)

        error_count = payload.get("error_count", 0)
        if job.status == ImportJob.Status.PARTIAL:
            return Response(
                {
                    **payload,
                    "detail": "Import partially completed. Some rows failed and were skipped.",
                    "error_count": error_count,
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {
                **payload,
                "detail": "Import failed. No rows were committed.",
                "error_count": error_count,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class InvoiceImportJobErrorsExportAPIView(InvoiceImportBaseAPIView):
    def get(self, request, job_id: int):
        job = self._get_job(request, job_id)
        fmt = (request.query_params.get("format") or "xlsx").lower()
        content, content_type, filename = export_job_errors(job=job, fmt=fmt)
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class InvoiceImportJobReconciliationAPIView(InvoiceImportBaseAPIView):
    def get(self, request, job_id: int):
        job = self._get_job(request, job_id)
        return Response(job.reconciliation_summary or {})


class InvoiceImportProfileListCreateAPIView(InvoiceImportBaseAPIView):
    parser_classes = [JSONParser]

    def get(self, request):
        entity = self._get_entity(request)
        rows = ImportProfile.objects.filter(entity=entity, module=self.module).order_by("name", "id")
        return Response(ImportProfileSerializer(rows, many=True).data)

    def post(self, request):
        entity = self._get_entity(request)
        payload = request.data.copy()
        payload["entity"] = entity.id
        payload["module"] = self.module
        serializer = ImportProfileWriteSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save(entity=entity, module=self.module, created_by=request.user)
        return Response(ImportProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class InvoiceImportProfileDetailAPIView(InvoiceImportBaseAPIView):
    parser_classes = [JSONParser]

    def get(self, request, profile_id: int):
        profile = self._get_profile(request, profile_id)
        return Response(ImportProfileSerializer(profile).data)

    def patch(self, request, profile_id: int):
        profile = self._get_profile(request, profile_id)
        payload = request.data.copy()
        payload["entity"] = profile.entity_id
        payload["module"] = self.module
        serializer = ImportProfileWriteSerializer(profile, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return Response(ImportProfileSerializer(profile).data)


class SalesInvoiceImportTemplateAPIView(InvoiceImportTemplateAPIView):
    module = ImportJob.Module.SALES


class SalesInvoiceImportProfileListCreateAPIView(InvoiceImportProfileListCreateAPIView):
    module = ImportJob.Module.SALES


class SalesInvoiceImportProfileDetailAPIView(InvoiceImportProfileDetailAPIView):
    module = ImportJob.Module.SALES


class SalesInvoiceImportJobCreateAPIView(InvoiceImportJobCreateAPIView):
    module = ImportJob.Module.SALES


class SalesInvoiceImportJobDetailAPIView(InvoiceImportJobDetailAPIView):
    module = ImportJob.Module.SALES


class SalesInvoiceImportJobCommitAPIView(InvoiceImportJobCommitAPIView):
    module = ImportJob.Module.SALES


class SalesInvoiceImportJobErrorsExportAPIView(InvoiceImportJobErrorsExportAPIView):
    module = ImportJob.Module.SALES


class SalesInvoiceImportJobReconciliationAPIView(InvoiceImportJobReconciliationAPIView):
    module = ImportJob.Module.SALES


class PurchaseInvoiceImportTemplateAPIView(InvoiceImportTemplateAPIView):
    module = ImportJob.Module.PURCHASE


class PurchaseInvoiceImportProfileListCreateAPIView(InvoiceImportProfileListCreateAPIView):
    module = ImportJob.Module.PURCHASE


class PurchaseInvoiceImportProfileDetailAPIView(InvoiceImportProfileDetailAPIView):
    module = ImportJob.Module.PURCHASE


class PurchaseInvoiceImportJobCreateAPIView(InvoiceImportJobCreateAPIView):
    module = ImportJob.Module.PURCHASE


class PurchaseInvoiceImportJobDetailAPIView(InvoiceImportJobDetailAPIView):
    module = ImportJob.Module.PURCHASE


class PurchaseInvoiceImportJobCommitAPIView(InvoiceImportJobCommitAPIView):
    module = ImportJob.Module.PURCHASE


class PurchaseInvoiceImportJobErrorsExportAPIView(InvoiceImportJobErrorsExportAPIView):
    module = ImportJob.Module.PURCHASE


class PurchaseInvoiceImportJobReconciliationAPIView(InvoiceImportJobReconciliationAPIView):
    module = ImportJob.Module.PURCHASE
