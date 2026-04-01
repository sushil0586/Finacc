from __future__ import annotations

from decimal import Decimal
import re

from django.db.models import Q, Sum
from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from withholding.models import (
    GstTcsComputation,
    GstTcsEcoProfile,
    PartyTaxProfile,
    TcsCollection,
    TcsComputation,
    TcsDeposit,
    TcsDepositAllocation,
    TcsQuarterlyReturn,
    WithholdingSection,
)
from withholding.serializers import (
    EntityWithholdingConfigSerializer,
    GstTcsComputationSerializer,
    GstTcsComputeRequestSerializer,
    GstTcsEcoProfileSerializer,
    PartyTaxProfileSerializer,
    TcsCollectionSerializer,
    TcsComputationSerializer,
    TcsComputeConfirmSerializer,
    TcsComputeRequestSerializer,
    TcsDepositAllocationSerializer,
    TcsDepositSerializer,
    TcsQuarterlyReturnSerializer,
    WithholdingSectionSerializer,
    build_preview_payload,
)
from withholding.services import compute_withholding_preview, q2, upsert_tcs_computation
from financial.profile_access import account_pan


def _safe_int(raw):
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError({"detail": "Query parameter must be an integer."})


def _safe_bool(raw) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _expand_fy_values(raw: str) -> list[str]:
    value = (raw or "").strip()
    if not value:
        return []

    def _token(start_year: int) -> str:
        return f"{start_year}-{str(start_year + 1)[-2:]}"

    out: list[str] = [value]
    m_short = re.match(r"^(\d{4})-(\d{2})$", value)
    if m_short:
        start = int(m_short.group(1))
        end_2 = int(m_short.group(2))
        end_full = (start // 100) * 100 + end_2
        if end_full < start:
            end_full += 100
        if end_full == start + 1:
            token = _token(start)
            if token not in out:
                out.insert(0, token)
            return out
        if end_full > start + 1 and (end_full - start) <= 5:
            candidates = [_token(y) for y in range(start, end_full)]
            return list(dict.fromkeys(candidates + out))
        return out

    m_full = re.match(r"^(\d{4})-(\d{4})$", value)
    if m_full:
        start = int(m_full.group(1))
        end_full = int(m_full.group(2))
        if end_full == start + 1:
            token = _token(start)
            return list(dict.fromkeys([token] + out))
        if end_full > start + 1 and (end_full - start) <= 5:
            candidates = [_token(y) for y in range(start, end_full)]
            return list(dict.fromkeys(candidates + out))
    return out


class TcsSectionListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WithholdingSectionSerializer

    def get_queryset(self):
        qs = WithholdingSection.objects.filter(tax_type=2).order_by("section_code", "-effective_from")
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(section_code__icontains=q) | Q(description__icontains=q))
        law_type = (self.request.query_params.get("law_type") or "").strip().upper()
        if law_type:
            qs = qs.filter(law_type=law_type)
        return qs


class TcsSectionRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WithholdingSectionSerializer
    queryset = WithholdingSection.objects.filter(tax_type=2)


class TcsEntityConfigListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EntityWithholdingConfigSerializer

    def get_queryset(self):
        from withholding.models import EntityWithholdingConfig

        qs = EntityWithholdingConfig.objects.all().order_by("-effective_from", "-id")
        entity_id = self.request.query_params.get("entity_id")
        if entity_id not in (None, ""):
            qs = qs.filter(entity_id=int(entity_id))
        entityfin_id = self.request.query_params.get("entityfin_id")
        if entityfin_id not in (None, ""):
            qs = qs.filter(entityfin_id=int(entityfin_id))
        subentity_id = self.request.query_params.get("subentity_id")
        if subentity_id not in (None, ""):
            qs = qs.filter(subentity_id=int(subentity_id))
        return qs


class TcsEntityConfigRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EntityWithholdingConfigSerializer

    def get_queryset(self):
        from withholding.models import EntityWithholdingConfig

        return EntityWithholdingConfig.objects.all()


class TcsEntityConfigRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EntityWithholdingConfigSerializer

    def get_queryset(self):
        from withholding.models import EntityWithholdingConfig

        return EntityWithholdingConfig.objects.all()


class TcsPartyProfileListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PartyTaxProfileSerializer
    queryset = PartyTaxProfile.objects.all().order_by("-id")


class TcsPartyProfileRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PartyTaxProfileSerializer
    queryset = PartyTaxProfile.objects.all()


class TcsPartyProfileRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PartyTaxProfileSerializer
    queryset = PartyTaxProfile.objects.all()


class TcsComputePreviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = TcsComputeRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        req = {
            "entity_id": d["entity_id"],
            "entityfin_id": d["entityfin_id"],
            "subentity_id": d.get("subentity_id"),
            "party_account_id": d.get("party_account_id"),
            "tax_type": d["tax_type"],
            "explicit_section_id": d.get("section_id"),
            "doc_date": d["doc_date"],
            "taxable_total": d.get("taxable_total", Decimal("0.00")),
            "gross_total": d.get("gross_total", Decimal("0.00")),
        }
        return Response(build_preview_payload(req=req, user=request.user))


class TcsComputeConfirmAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = TcsComputeConfirmSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        req = {
            "entity_id": d["entity_id"],
            "entityfin_id": d["entityfin_id"],
            "subentity_id": d.get("subentity_id"),
            "party_account_id": d.get("party_account_id"),
            "tax_type": d["tax_type"],
            "explicit_section_id": d.get("section_id"),
            "doc_date": d["doc_date"],
            "taxable_total": d.get("taxable_total", Decimal("0.00")),
            "gross_total": d.get("gross_total", Decimal("0.00")),
        }
        preview = compute_withholding_preview(**req)

        if d["tax_type"] != 2:
            return Response(
                {
                    "preview": build_preview_payload(req=req, user=request.user),
                    "message": "Only TCS persistence is supported in this endpoint.",
                },
                status=status.HTTP_200_OK,
            )

        doc_id = d.get("document_id")
        if not doc_id:
            return Response({"document_id": ["This field is required for confirm."]}, status=status.HTTP_400_BAD_REQUEST)

        row = upsert_tcs_computation(
            module_name=(d.get("module_name") or "sales").strip().lower(),
            document_type=(d.get("document_type") or "invoice").strip().lower(),
            document_id=doc_id,
            document_no=(d.get("document_no") or "").strip(),
            doc_date=d["doc_date"],
            entity_id=d["entity_id"],
            entityfin_id=d["entityfin_id"],
            subentity_id=d.get("subentity_id"),
            party_account_id=d.get("party_account_id"),
            preview=preview,
            status=d.get("status") or TcsComputation.Status.CONFIRMED,
            trigger_basis=d.get("trigger_basis") or "INVOICE",
            override_reason=d.get("override_reason") or "",
            overridden_by=request.user,
        )
        return Response(TcsComputationSerializer(row).data, status=status.HTTP_201_CREATED)


class TcsComputeRecomputeAPIView(TcsComputeConfirmAPIView):
    pass


class TcsComputationListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsComputationSerializer

    def get_queryset(self):
        qs = TcsComputation.objects.all().order_by("-doc_date", "-id")
        module = (self.request.query_params.get("module") or "").strip()
        if module:
            qs = qs.filter(module_name=module)
        document_type = (self.request.query_params.get("document_type") or "").strip()
        if document_type:
            qs = qs.filter(document_type=document_type)
        doc_id = self.request.query_params.get("doc_id")
        if doc_id not in (None, ""):
            qs = qs.filter(document_id=int(doc_id))
        entity_id = self.request.query_params.get("entity_id")
        if entity_id not in (None, ""):
            qs = qs.filter(entity_id=int(entity_id))
        fy = (self.request.query_params.get("fy") or "").strip()
        if fy:
            qs = qs.filter(fiscal_year__in=_expand_fy_values(fy))
        quarter = (self.request.query_params.get("quarter") or "").strip().upper()
        if quarter:
            qs = qs.filter(quarter=quarter)
        return qs


class TcsCollectionListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsCollectionSerializer

    def get_queryset(self):
        qs = TcsCollection.objects.select_related("computation").all().order_by("-collection_date", "-id")
        entity_id = _safe_int(self.request.query_params.get("entity_id"))
        if entity_id is not None:
            qs = qs.filter(computation__entity_id=entity_id)
        fy = (self.request.query_params.get("fy") or "").strip()
        if fy:
            qs = qs.filter(computation__fiscal_year__in=_expand_fy_values(fy))
        quarter = (self.request.query_params.get("quarter") or "").strip().upper()
        if quarter:
            qs = qs.filter(computation__quarter=quarter)
        return qs

    def perform_create(self, serializer):
        row = serializer.save()
        entity_id = _safe_int(self.request.query_params.get("entity_id"))
        if entity_id is not None and int(row.computation.entity_id) != int(entity_id):
            raise ValidationError({"detail": "collection computation does not belong to the requested entity scope."})


class TcsCollectionRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsCollectionSerializer

    def get_queryset(self):
        qs = TcsCollection.objects.select_related("computation").all()
        entity_id = _safe_int(self.request.query_params.get("entity_id"))
        if entity_id is not None:
            qs = qs.filter(computation__entity_id=entity_id)
        return qs


class TcsDepositListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsDepositSerializer

    def get_queryset(self):
        qs = TcsDeposit.objects.all().order_by("-challan_date", "-id")
        entity_id = _safe_int(self.request.query_params.get("entity_id"))
        if entity_id is not None:
            qs = qs.filter(entity_id=entity_id)
        fy = (self.request.query_params.get("fy") or "").strip()
        if fy:
            qs = qs.filter(financial_year__in=_expand_fy_values(fy))
        month = _safe_int(self.request.query_params.get("month"))
        if month is not None:
            qs = qs.filter(month=month)
        return qs


class TcsDepositRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsDepositSerializer

    def get_queryset(self):
        qs = TcsDeposit.objects.all()
        entity_id = _safe_int(self.request.query_params.get("entity_id"))
        if entity_id is not None:
            qs = qs.filter(entity_id=entity_id)
        return qs


class TcsDepositAllocateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        try:
            deposit = TcsDeposit.objects.get(pk=pk)
        except TcsDeposit.DoesNotExist:
            return Response({"detail": "Deposit not found."}, status=status.HTTP_404_NOT_FOUND)

        collection_id = request.data.get("collection_id")
        allocated_amount = request.data.get("allocated_amount")
        if not collection_id or allocated_amount in (None, ""):
            return Response(
                {"detail": "collection_id and allocated_amount are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            collection = TcsCollection.objects.get(pk=int(collection_id))
        except (TcsCollection.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Invalid collection_id."}, status=status.HTTP_400_BAD_REQUEST)

        if deposit.status == TcsDeposit.Status.FILED:
            return Response({"detail": "Cannot allocate against a filed deposit."}, status=status.HTTP_400_BAD_REQUEST)
        if collection.status == TcsCollection.Status.CANCELLED:
            return Response({"detail": "Cannot allocate a cancelled collection."}, status=status.HTTP_400_BAD_REQUEST)
        if int(collection.computation.entity_id) != int(deposit.entity_id):
            return Response({"detail": "Collection and deposit must belong to the same entity."}, status=status.HTTP_400_BAD_REQUEST)
        if (collection.computation.fiscal_year or "").strip() and (deposit.financial_year or "").strip():
            if str(collection.computation.fiscal_year).strip() != str(deposit.financial_year).strip():
                return Response({"detail": "Collection and deposit financial year mismatch."}, status=status.HTTP_400_BAD_REQUEST)

        alloc_amount = q2(Decimal(allocated_amount))
        if alloc_amount <= Decimal("0.00"):
            return Response({"detail": "allocated_amount must be > 0."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            locked_deposit = TcsDeposit.objects.select_for_update().get(pk=deposit.pk)
            total_alloc = (
                TcsDepositAllocation.objects.filter(deposit=locked_deposit)
                .aggregate(v=Sum("allocated_amount"))
                .get("v")
                or Decimal("0.00")
            )
            if q2(total_alloc + alloc_amount) > q2(locked_deposit.total_deposit_amount):
                return Response({"detail": "Allocation exceeds deposit balance."}, status=status.HTTP_400_BAD_REQUEST)

            collection_alloc_total = (
                TcsDepositAllocation.objects.filter(collection=collection)
                .aggregate(v=Sum("allocated_amount"))
                .get("v")
                or Decimal("0.00")
            )
            if q2(collection_alloc_total + alloc_amount) > q2(collection.tcs_collected_amount):
                return Response({"detail": "Allocation exceeds collection amount."}, status=status.HTTP_400_BAD_REQUEST)

            row = TcsDepositAllocation.objects.create(
                deposit=locked_deposit,
                collection=collection,
                allocated_amount=alloc_amount,
            )
        return Response(TcsDepositAllocationSerializer(row).data, status=status.HTTP_201_CREATED)


class TcsDepositAllocationListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsDepositAllocationSerializer

    def get_queryset(self):
        return TcsDepositAllocation.objects.filter(deposit_id=self.kwargs["pk"]).order_by("-id")


class TcsReturn27EqListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsQuarterlyReturnSerializer

    def get_queryset(self):
        qs = TcsQuarterlyReturn.objects.filter(form_name="27EQ").order_by("-id")
        entity_id = _safe_int(self.request.query_params.get("entity_id"))
        if entity_id is not None:
            qs = qs.filter(entity_id=entity_id)
        fy = (self.request.query_params.get("fy") or "").strip()
        if fy:
            qs = qs.filter(fy__in=_expand_fy_values(fy))
        quarter = (self.request.query_params.get("quarter") or "").strip().upper()
        if quarter:
            qs = qs.filter(quarter=quarter)
        return qs

    def perform_create(self, serializer):
        entity = serializer.validated_data.get("entity")
        fy = (serializer.validated_data.get("fy") or "").strip()
        quarter = (serializer.validated_data.get("quarter") or "").strip().upper()
        snapshot = serializer.validated_data.get("json_snapshot")
        if not snapshot and entity and fy and quarter:
            snapshot = _build_tcs_27eq_snapshot(entity_id=int(entity.id), fy=fy, quarter=quarter)
        serializer.save(form_name="27EQ", json_snapshot=snapshot)


class TcsReturn27EqRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsQuarterlyReturnSerializer

    def get_queryset(self):
        qs = TcsQuarterlyReturn.objects.filter(form_name="27EQ")
        entity_id = _safe_int(self.request.query_params.get("entity_id"))
        if entity_id is not None:
            qs = qs.filter(entity_id=entity_id)
        return qs

    def perform_update(self, serializer):
        entity = serializer.validated_data.get("entity") or serializer.instance.entity
        fy = (serializer.validated_data.get("fy") or serializer.instance.fy or "").strip()
        quarter = (serializer.validated_data.get("quarter") or serializer.instance.quarter or "").strip().upper()
        snapshot = serializer.validated_data.get("json_snapshot")
        if not snapshot and entity and fy and quarter:
            snapshot = _build_tcs_27eq_snapshot(entity_id=int(entity.id), fy=fy, quarter=quarter)
        serializer.save(form_name="27EQ", json_snapshot=snapshot)


class TcsReturn27EqPrefillAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = _safe_int(request.query_params.get("entity_id"))
        fy = (request.query_params.get("fy") or "").strip()
        quarter = (request.query_params.get("quarter") or "").strip().upper()
        if entity_id is None:
            raise ValidationError({"entity_id": ["This query param is required."]})
        if not fy:
            raise ValidationError({"fy": ["This query param is required."]})
        if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
            raise ValidationError({"quarter": ["quarter must be one of Q1/Q2/Q3/Q4."]})

        snapshot = _build_tcs_27eq_snapshot(entity_id=entity_id, fy=fy, quarter=quarter)
        existing = (
            TcsQuarterlyReturn.objects.filter(entity_id=entity_id, fy__in=_expand_fy_values(fy), quarter=quarter, form_name="27EQ")
            .order_by("-id")
            .first()
        )
        return Response(
            {
                "entity_id": entity_id,
                "fy": fy,
                "quarter": quarter,
                "snapshot": snapshot,
                "existing_return": TcsQuarterlyReturnSerializer(existing).data if existing else None,
            }
        )


class TcsReportLedgerAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = TcsComputation.objects.all()
        entity_id = request.query_params.get("entity_id")
        if entity_id not in (None, ""):
            qs = qs.filter(entity_id=int(entity_id))
        fy = (request.query_params.get("fy") or "").strip()
        if fy:
            qs = qs.filter(fiscal_year__in=_expand_fy_values(fy))

        out = qs.values("section__section_code").annotate(
            total_base=Sum("tcs_base_amount"),
            total_tcs=Sum("tcs_amount"),
        ).order_by("section__section_code")

        return Response(list(out))


class TcsReportFilingPackAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _quarter_months(quarter: str):
        mapping = {
            "Q1": [4, 5, 6],
            "Q2": [7, 8, 9],
            "Q3": [10, 11, 12],
            "Q4": [1, 2, 3],
        }
        return mapping[quarter]

    def get(self, request):
        entity_id = request.query_params.get("entity_id")
        fy = (request.query_params.get("fy") or "").strip()
        quarter = (request.query_params.get("quarter") or "").strip().upper()

        if entity_id in (None, ""):
            raise ValidationError({"entity_id": ["This query param is required."]})
        if not fy:
            raise ValidationError({"fy": ["This query param is required."]})
        if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
            raise ValidationError({"quarter": ["quarter must be one of Q1/Q2/Q3/Q4."]})

        entity_id = int(entity_id)
        months = self._quarter_months(quarter)
        exceptions_only = _safe_bool(request.query_params.get("exceptions_only"))
        pending_only = _safe_bool(request.query_params.get("pending_only"))

        fy_candidates = _expand_fy_values(fy)
        computations = (
            TcsComputation.objects.select_related("party_account", "section")
            .prefetch_related("collections__deposit_allocations__deposit")
            .filter(entity_id=entity_id, fiscal_year__in=fy_candidates, quarter=quarter)
            .order_by("doc_date", "id")
        )

        deposits = TcsDeposit.objects.filter(entity_id=entity_id, financial_year__in=fy_candidates, month__in=months).order_by("challan_date", "id")
        return_row = TcsQuarterlyReturn.objects.filter(entity_id=entity_id, fy__in=fy_candidates, quarter=quarter, form_name="27EQ").order_by("-id").first()

        rows = []
        section_totals = {}
        total_base = Decimal("0.00")
        total_tcs = Decimal("0.00")
        total_collected = Decimal("0.00")

        for comp in computations:
            party = comp.party_account
            section = comp.section
            party_name = (getattr(party, "legalname", None) or getattr(party, "accountname", None) or "").strip()
            pan = (account_pan(party) or getattr(party, "pan", None) or "").strip()

            comp_collections = list(comp.collections.all().order_by("collection_date", "id"))
            if not comp_collections:
                comp_collections = [None]

            comp_alloc_total = Decimal("0.00")
            comp_collected_total = Decimal("0.00")
            for c in comp.collections.all():
                comp_collected_total += q2(c.tcs_collected_amount or Decimal("0.00"))
                alloc_sum = c.deposit_allocations.aggregate(v=Sum("allocated_amount")).get("v") or Decimal("0.00")
                comp_alloc_total += q2(alloc_sum)

            total_base += q2(comp.tcs_base_amount or Decimal("0.00"))
            total_tcs += q2(comp.tcs_amount or Decimal("0.00"))
            total_collected += q2(comp_collected_total)

            section_code = section.section_code if section else "UNMAPPED"
            if section_code not in section_totals:
                section_totals[section_code] = {"section_code": section_code, "total_base": Decimal("0.00"), "total_tcs": Decimal("0.00")}
            section_totals[section_code]["total_base"] = q2(section_totals[section_code]["total_base"] + q2(comp.tcs_base_amount or Decimal("0.00")))
            section_totals[section_code]["total_tcs"] = q2(section_totals[section_code]["total_tcs"] + q2(comp.tcs_amount or Decimal("0.00")))

            for col in comp_collections:
                allocations = list(col.deposit_allocations.all().select_related("deposit").order_by("id")) if col else [None]
                if not allocations:
                    allocations = [None]

                for alloc in allocations:
                    dep = alloc.deposit if alloc else None
                    row = {
                        "document_type": comp.document_type,
                        "document_id": comp.document_id,
                        "document_no": comp.document_no,
                        "doc_date": comp.doc_date,
                        "party_account": comp.party_account_id,
                        "party_name": party_name,
                        "pan": pan,
                        "section_id": comp.section_id,
                        "section_code": section.section_code if section else None,
                        "section_desc": section.description if section else None,
                        "taxable_base": q2(comp.tcs_base_amount or Decimal("0.00")),
                        "tcs_rate": comp.rate,
                        "tcs_amount": q2(comp.tcs_amount or Decimal("0.00")),
                        "applicability_status": comp.applicability_status,
                        "override_reason": comp.override_reason,
                        "computation_status": comp.status,
                        "is_reversal": bool(comp.status == TcsComputation.Status.REVERSED or q2(comp.tcs_amount or Decimal("0.00")) < Decimal("0.00")),
                        "collection_id": col.id if col else None,
                        "collection_date": col.collection_date if col else None,
                        "receipt_voucher_id": col.receipt_voucher_id if col else None,
                        "amount_received": q2(col.amount_received) if col else Decimal("0.00"),
                        "tcs_collected_amount": q2(col.tcs_collected_amount) if col else Decimal("0.00"),
                        "collection_reference": col.collection_reference if col else "",
                        "collection_status": col.status if col else None,
                        "deposit_id": dep.id if dep else None,
                        "challan_no": dep.challan_no if dep else None,
                        "challan_date": dep.challan_date if dep else None,
                        "bsr_code": dep.bsr_code if dep else None,
                        "cin": dep.cin if dep else None,
                        "bank_name": dep.bank_name if dep else None,
                        "allocated_amount": q2(alloc.allocated_amount) if alloc else Decimal("0.00"),
                        "deposit_status": dep.status if dep else None,
                        "return_id": return_row.id if return_row else None,
                        "return_quarter": return_row.quarter if return_row else quarter,
                        "return_type": return_row.return_type if return_row else None,
                        "return_status": return_row.status if return_row else "NOT_CREATED",
                        "ack_no": return_row.ack_no if return_row else "",
                        "filed_on": return_row.filed_on if return_row else None,
                    }
                    row["exceptions"] = {
                        "missing_pan": not bool(pan),
                        "missing_section": comp.section_id is None,
                        "not_collected": comp_collected_total <= Decimal("0.00"),
                        "not_deposited": comp_alloc_total <= Decimal("0.00"),
                        "partially_allocated": comp_alloc_total > Decimal("0.00") and comp_alloc_total < q2(comp.tcs_amount or Decimal("0.00")),
                        "deposit_mismatch": q2(comp_alloc_total) != q2(comp_collected_total),
                        "reversal_case": row["is_reversal"],
                    }
                    if exceptions_only and not any(bool(v) for v in row["exceptions"].values()):
                        continue
                    if pending_only and not (
                        row["exceptions"]["not_collected"]
                        or row["exceptions"]["not_deposited"]
                        or row["exceptions"]["partially_allocated"]
                        or row["exceptions"]["deposit_mismatch"]
                    ):
                        continue
                    rows.append(row)

        total_deposited = q2(deposits.aggregate(v=Sum("total_deposit_amount")).get("v") or Decimal("0.00"))
        pending_collection = q2(total_tcs - total_collected)
        pending_deposit = q2(total_collected - total_deposited)
        exception_row_count = sum(1 for r in rows if any(bool(v) for v in (r.get("exceptions") or {}).values()))

        return Response(
            {
                "header": {
                    "entity": entity_id,
                    "fy": fy,
                    "quarter": quarter,
                    "total_base": q2(total_base),
                    "total_tcs": q2(total_tcs),
                    "total_collected": q2(total_collected),
                    "total_deposited": q2(total_deposited),
                    "pending_collection": q2(pending_collection),
                    "pending_deposit": q2(pending_deposit),
                    "return_status": return_row.status if return_row else "NOT_CREATED",
                    "row_count": len(rows),
                    "exception_row_count": exception_row_count,
                },
                "rows": rows,
                "section_summary": list(section_totals.values()),
            }
        )


def _build_tcs_27eq_snapshot(*, entity_id: int, fy: str, quarter: str) -> dict:
    quarter = (quarter or "").strip().upper()
    months = TcsReportFilingPackAPIView._quarter_months(quarter)
    fy_candidates = _expand_fy_values(fy)
    computations = (
        TcsComputation.objects.select_related("party_account", "section")
        .prefetch_related("collections__deposit_allocations")
        .filter(entity_id=entity_id, fiscal_year__in=fy_candidates, quarter=quarter)
    )
    deposits = TcsDeposit.objects.filter(entity_id=entity_id, financial_year__in=fy_candidates, month__in=months)

    total_base = q2(computations.aggregate(v=Sum("tcs_base_amount")).get("v") or Decimal("0.00"))
    total_tcs = q2(computations.aggregate(v=Sum("tcs_amount")).get("v") or Decimal("0.00"))
    total_collected = q2(
        TcsCollection.objects.filter(computation__in=computations).exclude(status=TcsCollection.Status.CANCELLED).aggregate(v=Sum("tcs_collected_amount")).get("v")
        or Decimal("0.00")
    )
    total_deposited = q2(deposits.aggregate(v=Sum("total_deposit_amount")).get("v") or Decimal("0.00"))

    missing_pan_count = 0
    missing_section_count = 0
    not_collected_count = 0
    not_deposited_count = 0
    partially_allocated_count = 0
    deposit_mismatch_count = 0

    for comp in computations:
        pan = (account_pan(comp.party_account) or getattr(comp.party_account, "pan", None) or "").strip()
        if not pan:
            missing_pan_count += 1
        if not comp.section_id:
            missing_section_count += 1

        comp_collected_total = Decimal("0.00")
        comp_alloc_total = Decimal("0.00")
        for col in comp.collections.all():
            if col.status == TcsCollection.Status.CANCELLED:
                continue
            comp_collected_total += q2(col.tcs_collected_amount or Decimal("0.00"))
            comp_alloc_total += q2(col.deposit_allocations.aggregate(v=Sum("allocated_amount")).get("v") or Decimal("0.00"))

        comp_tcs = q2(comp.tcs_amount or Decimal("0.00"))
        if comp_tcs > Decimal("0.00") and comp_collected_total <= Decimal("0.00"):
            not_collected_count += 1
        if comp_collected_total > Decimal("0.00") and comp_alloc_total <= Decimal("0.00"):
            not_deposited_count += 1
        if comp_alloc_total > Decimal("0.00") and comp_alloc_total < comp_collected_total:
            partially_allocated_count += 1
        if q2(comp_alloc_total) != q2(comp_collected_total):
            deposit_mismatch_count += 1

    return {
        "entity_id": entity_id,
        "fy": fy,
        "quarter": quarter,
        "totals": {
            "total_base": total_base,
            "total_tcs": total_tcs,
            "total_collected": total_collected,
            "total_deposited": total_deposited,
            "pending_collection": q2(total_tcs - total_collected),
            "pending_deposit": q2(total_collected - total_deposited),
        },
        "counts": {
            "computations": computations.count(),
            "deposits": deposits.count(),
            "missing_pan": missing_pan_count,
            "missing_section": missing_section_count,
            "not_collected": not_collected_count,
            "not_deposited": not_deposited_count,
            "partially_allocated": partially_allocated_count,
            "deposit_mismatch": deposit_mismatch_count,
        },
    }


class GstTcsEcoProfileListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GstTcsEcoProfileSerializer
    queryset = GstTcsEcoProfile.objects.all().order_by("-effective_from", "-id")


class GstTcsComputationListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GstTcsComputationSerializer

    def get_queryset(self):
        qs = GstTcsComputation.objects.all().order_by("-doc_date", "-id")
        entity_id = self.request.query_params.get("entity_id")
        if entity_id not in (None, ""):
            qs = qs.filter(entity_id=int(entity_id))
        fy = (self.request.query_params.get("fy") or "").strip()
        if fy:
            qs = qs.filter(fy=fy)
        month = self.request.query_params.get("month")
        if month not in (None, ""):
            qs = qs.filter(month=int(month))
        return qs

    def create(self, request, *args, **kwargs):
        s = GstTcsComputeRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        try:
            profile = GstTcsEcoProfile.objects.get(pk=d["eco_profile_id"], entity_id=d["entity_id"])
        except GstTcsEcoProfile.DoesNotExist:
            return Response({"detail": "Invalid eco_profile_id for entity."}, status=status.HTTP_400_BAD_REQUEST)

        rate = d.get("gst_tcs_rate")
        if rate is None:
            rate = profile.default_rate

        taxable_value = q2(d["taxable_value"])
        amount = q2((taxable_value * Decimal(rate)) / Decimal("100.0"))

        row, _ = GstTcsComputation.objects.update_or_create(
            entity_id=d["entity_id"],
            document_type=(d.get("document_type") or "invoice").strip().lower(),
            document_id=d.get("document_id") or 0,
            defaults={
                "eco_profile": profile,
                "supplier_account_id": d["supplier_account_id"],
                "doc_date": d["doc_date"],
                "document_no": (d.get("document_no") or "").strip(),
                "taxable_value": taxable_value,
                "gst_tcs_rate": Decimal(rate),
                "gst_tcs_amount": amount,
                "fy": d["fy"],
                "month": d["month"],
                "status": d["status"],
                "snapshot_json": {
                    "section_code": profile.section_code,
                    "gstin": profile.gstin,
                    "computed_rate": str(rate),
                },
            },
        )
        return Response(GstTcsComputationSerializer(row).data, status=status.HTTP_201_CREATED)
