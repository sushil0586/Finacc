from __future__ import annotations

from decimal import Decimal

from django.db.models import Q, Sum
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
            qs = qs.filter(fiscal_year=fy)
        quarter = (self.request.query_params.get("quarter") or "").strip().upper()
        if quarter:
            qs = qs.filter(quarter=quarter)
        return qs


class TcsCollectionListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsCollectionSerializer
    queryset = TcsCollection.objects.all().order_by("-collection_date", "-id")


class TcsCollectionRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsCollectionSerializer
    queryset = TcsCollection.objects.all()


class TcsDepositListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsDepositSerializer
    queryset = TcsDeposit.objects.all().order_by("-challan_date", "-id")


class TcsDepositRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsDepositSerializer
    queryset = TcsDeposit.objects.all()


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

        alloc_amount = q2(Decimal(allocated_amount))
        if alloc_amount <= Decimal("0.00"):
            return Response({"detail": "allocated_amount must be > 0."}, status=status.HTTP_400_BAD_REQUEST)

        total_alloc = (
            TcsDepositAllocation.objects.filter(deposit=deposit)
            .aggregate(v=Sum("allocated_amount"))
            .get("v")
            or Decimal("0.00")
        )
        if q2(total_alloc + alloc_amount) > q2(deposit.total_deposit_amount):
            return Response({"detail": "Allocation exceeds deposit balance."}, status=status.HTTP_400_BAD_REQUEST)

        row = TcsDepositAllocation.objects.create(
            deposit=deposit,
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
        return TcsQuarterlyReturn.objects.filter(form_name="27EQ").order_by("-id")

    def perform_create(self, serializer):
        serializer.save(form_name="27EQ")


class TcsReturn27EqRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TcsQuarterlyReturnSerializer

    def get_queryset(self):
        return TcsQuarterlyReturn.objects.filter(form_name="27EQ")


class TcsReportLedgerAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = TcsComputation.objects.all()
        entity_id = request.query_params.get("entity_id")
        if entity_id not in (None, ""):
            qs = qs.filter(entity_id=int(entity_id))
        fy = (request.query_params.get("fy") or "").strip()
        if fy:
            qs = qs.filter(fiscal_year=fy)

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

        computations = (
            TcsComputation.objects.select_related("party_account", "section")
            .prefetch_related("collections__deposit_allocations__deposit")
            .filter(entity_id=entity_id, fiscal_year=fy, quarter=quarter)
            .order_by("doc_date", "id")
        )

        deposits = TcsDeposit.objects.filter(entity_id=entity_id, financial_year=fy, month__in=months).order_by("challan_date", "id")
        return_row = TcsQuarterlyReturn.objects.filter(entity_id=entity_id, fy=fy, quarter=quarter, form_name="27EQ").order_by("-id").first()

        rows = []
        section_totals = {}
        total_base = Decimal("0.00")
        total_tcs = Decimal("0.00")
        total_collected = Decimal("0.00")

        for comp in computations:
            party = comp.party_account
            section = comp.section
            party_name = (getattr(party, "legalname", None) or getattr(party, "accountname", None) or "").strip()
            pan = (getattr(party, "pan", None) or "").strip()

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
                    rows.append(row)

        total_deposited = q2(deposits.aggregate(v=Sum("total_deposit_amount")).get("v") or Decimal("0.00"))
        pending_collection = q2(total_tcs - total_collected)
        pending_deposit = q2(total_collected - total_deposited)

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
                },
                "rows": rows,
                "section_summary": list(section_totals.values()),
            }
        )


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
