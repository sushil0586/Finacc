from __future__ import annotations
from datetime import date
import csv

from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.renderers import JSONRenderer
from django.http import HttpResponse

from purchase.models.purchase_statutory import PurchaseStatutoryChallan, PurchaseStatutoryReturn
from purchase.serializers.purchase_statutory import (
    PurchaseStatutoryChallanSerializer,
    PurchaseStatutoryChallanCreateInputSerializer,
    PurchaseStatutoryReturnSerializer,
    PurchaseStatutoryReturnCreateInputSerializer,
)
from purchase.services.purchase_statutory_service import PurchaseStatutoryService


def _parse_scope(request):
    entity = request.query_params.get("entity")
    entityfinid = request.query_params.get("entityfinid")
    subentity = request.query_params.get("subentity")
    if not entity or not entityfinid:
        raise ValidationError({"detail": "entity and entityfinid query params are required."})
    try:
        entity_id = int(entity)
        entityfinid_id = int(entityfinid)
        subentity_id = int(subentity) if subentity not in (None, "", "null") else None
    except (TypeError, ValueError):
        raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
    return entity_id, entityfinid_id, subentity_id


def _parse_required_period_and_tax_type(request):
    tax_type = request.query_params.get("tax_type")
    period_from_raw = request.query_params.get("period_from")
    period_to_raw = request.query_params.get("period_to")
    if not tax_type:
        raise ValidationError({"detail": "tax_type is required."})
    if not period_from_raw or not period_to_raw:
        raise ValidationError({"detail": "period_from and period_to are required."})
    try:
        period_from = date.fromisoformat(str(period_from_raw))
        period_to = date.fromisoformat(str(period_to_raw))
    except ValueError:
        raise ValidationError({"detail": "period_from and period_to must be YYYY-MM-DD."})
    return tax_type, period_from, period_to


class PurchaseStatutoryChallanListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PurchaseStatutoryChallanSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = _parse_scope(self.request)
        qs = PurchaseStatutoryChallan.objects.prefetch_related("lines").filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        tax_type = self.request.query_params.get("tax_type")
        if tax_type:
            qs = qs.filter(tax_type=tax_type)
        status_q = self.request.query_params.get("status")
        if status_q not in (None, "", "null"):
            qs = qs.filter(status=int(status_q))
        return qs.order_by("-challan_date", "-id")

    def create(self, request, *args, **kwargs):
        inp = PurchaseStatutoryChallanCreateInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        data = inp.validated_data
        try:
            res = PurchaseStatutoryService.create_challan(
                entity_id=data["entity"],
                entityfinid_id=data["entityfinid"],
                subentity_id=data.get("subentity"),
                tax_type=data["tax_type"],
                challan_no=data["challan_no"],
                challan_date=data["challan_date"],
                period_from=data.get("period_from"),
                period_to=data.get("period_to"),
                interest_amount=data.get("interest_amount"),
                late_fee_amount=data.get("late_fee_amount"),
                penalty_amount=data.get("penalty_amount"),
                bank_ref_no=data.get("bank_ref_no"),
                bsr_code=data.get("bsr_code"),
                cin_no=data.get("cin_no"),
                minor_head_code=data.get("minor_head_code"),
                payment_payload_json=data.get("payment_payload_json"),
                ack_document=data.get("ack_document"),
                remarks=data.get("remarks"),
                lines=data["lines"],
                created_by_id=request.user.id,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        out = PurchaseStatutoryChallanSerializer(res.obj, context=self.get_serializer_context())
        return Response({"message": res.message, "data": out.data}, status=status.HTTP_201_CREATED)


class PurchaseStatutoryChallanDepositAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        deposited_on = request.data.get("deposited_on")
        bank_ref_no = request.data.get("bank_ref_no")
        bsr_code = request.data.get("bsr_code")
        cin_no = request.data.get("cin_no")
        minor_head_code = request.data.get("minor_head_code")
        payment_payload_json = request.data.get("payment_payload_json")
        ack_document = request.data.get("ack_document")
        try:
            res = PurchaseStatutoryService.deposit_challan(
                challan_id=pk,
                deposited_by_id=request.user.id,
                deposited_on=deposited_on,
                bank_ref_no=bank_ref_no,
                bsr_code=bsr_code,
                cin_no=cin_no,
                minor_head_code=minor_head_code,
                payment_payload_json=payment_payload_json,
                ack_document=ack_document,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"message": res.message, "data": PurchaseStatutoryChallanSerializer(res.obj).data})


class PurchaseStatutoryChallanCancelAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        reason = request.data.get("reason")
        try:
            res = PurchaseStatutoryService.cancel_challan(
                challan_id=pk,
                cancelled_by_id=request.user.id,
                reason=reason,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"message": res.message, "data": PurchaseStatutoryChallanSerializer(res.obj).data})


class PurchaseStatutoryChallanApprovalAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        action = (request.data.get("action") or "").strip().lower()
        remarks = request.data.get("remarks")
        try:
            if action == "submit":
                res = PurchaseStatutoryService.submit_challan_for_approval(
                    challan_id=pk, user_id=request.user.id, remarks=remarks
                )
            elif action == "approve":
                res = PurchaseStatutoryService.approve_challan(
                    challan_id=pk, user_id=request.user.id, remarks=remarks
                )
            elif action == "reject":
                res = PurchaseStatutoryService.reject_challan(
                    challan_id=pk, user_id=request.user.id, remarks=remarks
                )
            else:
                raise ValidationError({"detail": "action must be submit|approve|reject"})
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        out = PurchaseStatutoryChallanSerializer(res.obj).data
        return Response(
            {
                "message": res.message,
                "approval_status": out.get("approval_status", "DRAFT"),
                "approval_status_name": out.get("approval_status_name", "Draft"),
                "data": out,
            }
        )


class PurchaseStatutoryReturnListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PurchaseStatutoryReturnSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = _parse_scope(self.request)
        qs = PurchaseStatutoryReturn.objects.prefetch_related("lines").filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
        )
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        tax_type = self.request.query_params.get("tax_type")
        if tax_type:
            qs = qs.filter(tax_type=tax_type)
        status_q = self.request.query_params.get("status")
        if status_q not in (None, "", "null"):
            qs = qs.filter(status=int(status_q))
        return qs.order_by("-period_to", "-id")

    def create(self, request, *args, **kwargs):
        inp = PurchaseStatutoryReturnCreateInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        data = inp.validated_data
        try:
            res = PurchaseStatutoryService.create_return(
                entity_id=data["entity"],
                entityfinid_id=data["entityfinid"],
                subentity_id=data.get("subentity"),
                tax_type=data["tax_type"],
                return_code=data["return_code"],
                period_from=data["period_from"],
                period_to=data["period_to"],
                ack_no=data.get("ack_no"),
                arn_no=data.get("arn_no"),
                interest_amount=data.get("interest_amount"),
                late_fee_amount=data.get("late_fee_amount"),
                penalty_amount=data.get("penalty_amount"),
                filed_payload_json=data.get("filed_payload_json"),
                ack_document=data.get("ack_document"),
                original_return_id=data.get("original_return_id"),
                revision_no=data.get("revision_no") or 0,
                remarks=data.get("remarks"),
                lines=data["lines"],
                created_by_id=request.user.id,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        out = PurchaseStatutoryReturnSerializer(res.obj, context=self.get_serializer_context())
        return Response({"message": res.message, "data": out.data}, status=status.HTTP_201_CREATED)


class PurchaseStatutoryReturnFileAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        filed_on = request.data.get("filed_on")
        ack_no = request.data.get("ack_no")
        arn_no = request.data.get("arn_no")
        filed_payload_json = request.data.get("filed_payload_json")
        ack_document = request.data.get("ack_document")
        try:
            res = PurchaseStatutoryService.file_return(
                filing_id=pk,
                filed_by_id=request.user.id,
                filed_on=filed_on,
                ack_no=ack_no,
                arn_no=arn_no,
                filed_payload_json=filed_payload_json,
                ack_document=ack_document,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"message": res.message, "data": PurchaseStatutoryReturnSerializer(res.obj).data})


class PurchaseStatutoryReturnCancelAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        reason = request.data.get("reason")
        try:
            res = PurchaseStatutoryService.cancel_return(
                filing_id=pk,
                cancelled_by_id=request.user.id,
                reason=reason,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"message": res.message, "data": PurchaseStatutoryReturnSerializer(res.obj).data})


class PurchaseStatutoryReturnApprovalAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        action = (request.data.get("action") or "").strip().lower()
        remarks = request.data.get("remarks")
        try:
            if action == "submit":
                res = PurchaseStatutoryService.submit_return_for_approval(
                    filing_id=pk, user_id=request.user.id, remarks=remarks
                )
            elif action == "approve":
                res = PurchaseStatutoryService.approve_return(
                    filing_id=pk, user_id=request.user.id, remarks=remarks
                )
            elif action == "reject":
                res = PurchaseStatutoryService.reject_return(
                    filing_id=pk, user_id=request.user.id, remarks=remarks
                )
            else:
                raise ValidationError({"detail": "action must be submit|approve|reject"})
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        out = PurchaseStatutoryReturnSerializer(res.obj).data
        return Response(
            {
                "message": res.message,
                "approval_status": out.get("approval_status", "DRAFT"),
                "approval_status_name": out.get("approval_status_name", "Draft"),
                "data": out,
            }
        )


class PurchaseStatutorySummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = _parse_scope(request)
        tax_type = request.query_params.get("tax_type")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        try:
            summary = PurchaseStatutoryService.reconciliation_summary(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                tax_type=tax_type or None,
                date_from=date_from or None,
                date_to=date_to or None,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"summary": summary})


class PurchaseStatutoryGlReconciliationAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = _parse_scope(request)
        period_from_raw = request.query_params.get("period_from")
        period_to_raw = request.query_params.get("period_to")
        if not period_from_raw or not period_to_raw:
            raise ValidationError({"detail": "period_from and period_to are required."})
        try:
            period_from = date.fromisoformat(str(period_from_raw))
            period_to = date.fromisoformat(str(period_to_raw))
        except ValueError:
            raise ValidationError({"detail": "period_from and period_to must be YYYY-MM-DD."})
        if period_from > period_to:
            raise ValidationError({"detail": "period_from cannot be greater than period_to."})
        payload = PurchaseStatutoryService.reconciliation_gl_status(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            period_from=period_from,
            period_to=period_to,
        )
        return Response(payload)


class _PdfJsonRenderer(JSONRenderer):
    format = "pdf"


class _XlsxJsonRenderer(JSONRenderer):
    format = "xlsx"


class _CsvJsonRenderer(JSONRenderer):
    format = "csv"


class PurchaseStatutoryChallanDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk: int):
        inp = PurchaseStatutoryChallanCreateInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        data = inp.validated_data
        try:
            res = PurchaseStatutoryService.update_challan(
                challan_id=pk,
                entity_id=data["entity"],
                entityfinid_id=data["entityfinid"],
                subentity_id=data.get("subentity"),
                tax_type=data["tax_type"],
                challan_no=data["challan_no"],
                challan_date=data["challan_date"],
                period_from=data.get("period_from"),
                period_to=data.get("period_to"),
                interest_amount=data.get("interest_amount"),
                late_fee_amount=data.get("late_fee_amount"),
                penalty_amount=data.get("penalty_amount"),
                bank_ref_no=data.get("bank_ref_no"),
                bsr_code=data.get("bsr_code"),
                cin_no=data.get("cin_no"),
                minor_head_code=data.get("minor_head_code"),
                payment_payload_json=data.get("payment_payload_json"),
                ack_document=data.get("ack_document"),
                remarks=data.get("remarks"),
                lines=data["lines"],
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        out = PurchaseStatutoryChallanSerializer(res.obj)
        return Response({"message": res.message, "data": out.data})

    def delete(self, request, pk: int):
        try:
            msg = PurchaseStatutoryService.delete_challan(challan_id=pk)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"message": msg}, status=status.HTTP_200_OK)


class PurchaseStatutoryReturnDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk: int):
        inp = PurchaseStatutoryReturnCreateInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        data = inp.validated_data
        try:
            res = PurchaseStatutoryService.update_return(
                filing_id=pk,
                entity_id=data["entity"],
                entityfinid_id=data["entityfinid"],
                subentity_id=data.get("subentity"),
                tax_type=data["tax_type"],
                return_code=data["return_code"],
                period_from=data["period_from"],
                period_to=data["period_to"],
                ack_no=data.get("ack_no"),
                arn_no=data.get("arn_no"),
                interest_amount=data.get("interest_amount"),
                late_fee_amount=data.get("late_fee_amount"),
                penalty_amount=data.get("penalty_amount"),
                filed_payload_json=data.get("filed_payload_json"),
                ack_document=data.get("ack_document"),
                original_return_id=data.get("original_return_id"),
                revision_no=data.get("revision_no") or 0,
                remarks=data.get("remarks"),
                lines=data["lines"],
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        out = PurchaseStatutoryReturnSerializer(res.obj)
        return Response({"message": res.message, "data": out.data})

    def delete(self, request, pk: int):
        try:
            msg = PurchaseStatutoryService.delete_return(filing_id=pk)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"message": msg}, status=status.HTTP_200_OK)


class PurchaseStatutoryChallanExportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [JSONRenderer, _PdfJsonRenderer, _XlsxJsonRenderer, _CsvJsonRenderer]

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = _parse_scope(request)
        fmt = (request.query_params.get("format") or "xlsx").lower().strip()
        if fmt not in ("xlsx", "pdf", "csv"):
            raise ValidationError({"detail": "format must be xlsx|pdf|csv"})

        qs = PurchaseStatutoryChallan.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)

        tax_type = request.query_params.get("tax_type")
        if tax_type:
            qs = qs.filter(tax_type=tax_type)
        rows = list(qs.order_by("-challan_date", "-id").values(
            "id", "tax_type", "challan_no", "challan_date", "period_from", "period_to",
            "amount", "interest_amount", "late_fee_amount", "penalty_amount", "status", "cin_no", "bsr_code"
        ))

        if fmt in ("xlsx", "pdf"):
            # lightweight fallback without external dependencies
            return Response(
                {"format": fmt, "rows": rows, "note": "Structured export payload. File rendering can be done by frontend/report engine."}
            )

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="purchase_statutory_challans.csv"'
        writer = csv.DictWriter(response, fieldnames=list(rows[0].keys()) if rows else ["id"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        return response


class PurchaseStatutoryReturnExportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [JSONRenderer, _PdfJsonRenderer, _XlsxJsonRenderer, _CsvJsonRenderer]

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = _parse_scope(request)
        fmt = (request.query_params.get("format") or "xlsx").lower().strip()
        if fmt not in ("xlsx", "pdf", "csv"):
            raise ValidationError({"detail": "format must be xlsx|pdf|csv"})

        qs = PurchaseStatutoryReturn.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)

        tax_type = request.query_params.get("tax_type")
        if tax_type:
            qs = qs.filter(tax_type=tax_type)
        rows = list(qs.order_by("-period_to", "-id").values(
            "id", "tax_type", "return_code", "period_from", "period_to",
            "amount", "interest_amount", "late_fee_amount", "penalty_amount", "status", "ack_no", "arn_no"
        ))

        if fmt in ("xlsx", "pdf"):
            # lightweight fallback without external dependencies
            return Response(
                {"format": fmt, "rows": rows, "note": "Structured export payload. File rendering can be done by frontend/report engine."}
            )

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="purchase_statutory_returns.csv"'
        writer = csv.DictWriter(response, fieldnames=list(rows[0].keys()) if rows else ["id"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        return response


class PurchaseStatutoryChallanEligibleLinesAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = _parse_scope(request)
        tax_type, period_from, period_to = _parse_required_period_and_tax_type(request)
        try:
            payload = PurchaseStatutoryService.challan_eligible_lines(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                tax_type=tax_type,
                period_from=period_from,
                period_to=period_to,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(payload)


class PurchaseStatutoryReturnEligibleLinesAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = _parse_scope(request)
        tax_type, period_from, period_to = _parse_required_period_and_tax_type(request)
        try:
            payload = PurchaseStatutoryService.return_eligible_lines(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                tax_type=tax_type,
                period_from=period_from,
                period_to=period_to,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(payload)


class PurchaseStatutoryReconciliationExceptionsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id, entityfinid_id, subentity_id = _parse_scope(request)
        tax_type, period_from, period_to = _parse_required_period_and_tax_type(request)
        try:
            payload = PurchaseStatutoryService.reconciliation_exceptions(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                tax_type=tax_type,
                period_from=period_from,
                period_to=period_to,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(payload)


class PurchaseStatutoryReturnNsdlExportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        try:
            payload = PurchaseStatutoryService.generate_nsdl_payload(filing_id=pk)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(payload)


class PurchaseStatutoryReturnForm16AIssueAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        try:
            payload = PurchaseStatutoryService.list_form16a_issues(filing_id=pk)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(payload)

    def post(self, request, pk: int):
        issue_date = request.data.get("issue_date")
        remarks = request.data.get("remarks")
        try:
            payload = PurchaseStatutoryService.issue_form16a(
                filing_id=pk,
                issued_by_id=request.user.id,
                issue_date=issue_date,
                remarks=remarks,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"message": "Form16A issued.", "data": payload}, status=status.HTTP_201_CREATED)


class PurchaseStatutoryReturnForm16ADownloadAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int, issue_no: int):
        try:
            payload = PurchaseStatutoryService.form16a_download_payload(
                filing_id=pk, issue_no=issue_no
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        response = HttpResponse(payload["content"], content_type="text/plain")
        response["Content-Disposition"] = f'attachment; filename="{payload["filename"]}"'
        return response
