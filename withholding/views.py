from __future__ import annotations

from decimal import Decimal
from datetime import date
import csv
import io
import re
import zipfile

from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.db import transaction
from django.utils.dateparse import parse_date
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from withholding.models import (
    EntityPartyTaxProfile,
    EntityWithholdingSectionPostingMap,
    EntityTcsThresholdOpening,
    GstTcsComputation,
    GstTcsEcoProfile,
    PartyTaxProfile,
    TcsCollection,
    TcsComputation,
    TcsDeposit,
    TcsDepositAllocation,
    TcsQuarterlyReturn,
    WithholdingSectionPolicyAudit,
    WithholdingSection,
)
from withholding.serializers import (
    EntityPartyTaxProfileSerializer,
    EntityWithholdingSectionPostingMapSerializer,
    EntityTcsThresholdOpeningSerializer,
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
    WithholdingSectionPolicyAuditSerializer,
    WithholdingSectionSerializer,
    build_preview_payload,
)
from withholding.services import compute_withholding_preview, q2, upsert_tcs_computation
from financial.profile_access import account_pan
from payments.models.payment_core import PaymentVoucherHeader


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


def _safe_decimal(raw) -> Decimal:
    try:
        return q2(raw or Decimal("0.00"))
    except Exception:
        return Decimal("0.00")


def _is_valid_pan(pan: str) -> bool:
    token = (pan or "").strip().upper()
    if not token:
        return False
    return bool(re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", token))


def _fy_quarter_for_doc(doc_date: date | None) -> tuple[str | None, str | None]:
    if not doc_date:
        return None, None
    y = doc_date.year
    if doc_date.month < 4:
        start = y - 1
        end = y
    else:
        start = y
        end = y + 1
    fy = f"{start}-{str(end)[-2:]}"
    if doc_date.month in (4, 5, 6):
        q = "Q1"
    elif doc_date.month in (7, 8, 9):
        q = "Q2"
    elif doc_date.month in (10, 11, 12):
        q = "Q3"
    else:
        q = "Q4"
    return fy, q


def _quarter_boundary_violation(*, doc_date: date | None, fiscal_year: str, quarter: str) -> bool:
    expected_fy, expected_quarter = _fy_quarter_for_doc(doc_date)
    return bool(expected_fy and expected_quarter and (expected_fy != (fiscal_year or "") or expected_quarter != (quarter or "")))


def _zip_csv_payload(named_rows: dict[str, list[dict]]) -> bytes:
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, rows in named_rows.items():
            stream = io.StringIO()
            headers = list(rows[0].keys()) if rows else []
            writer = csv.DictWriter(stream, fieldnames=headers)
            if headers:
                writer.writeheader()
                writer.writerows(rows)
            zf.writestr(filename, stream.getvalue())
    return buff.getvalue()


def _filing_readiness_errors(snapshot: dict) -> list[str]:
    counts = snapshot.get("counts") if isinstance(snapshot, dict) else {}
    totals = snapshot.get("totals") if isinstance(snapshot, dict) else {}
    errors: list[str] = []

    blocking_count_keys = {
        "missing_pan": "Missing PAN rows exist.",
        "missing_section": "Rows with missing section exist.",
        "not_collected": "Some computations are not collected.",
        "not_deposited": "Some collections are not deposited.",
        "partially_allocated": "Some collections are partially allocated.",
        "deposit_mismatch": "Collection vs deposit allocation mismatch exists.",
    }
    for key, msg in blocking_count_keys.items():
        if int(counts.get(key) or 0) > 0:
            errors.append(msg)

    pending_collection = _safe_decimal(totals.get("pending_collection"))
    pending_deposit = _safe_decimal(totals.get("pending_deposit"))
    if pending_collection != Decimal("0.00"):
        errors.append("Pending collection must be zero before marking FILED.")
    if pending_deposit != Decimal("0.00"):
        errors.append("Pending deposit must be zero before marking FILED.")
    return errors


def _exclude_cancelled_documents(qs):
    """
    Exclude computations whose backing business document is cancelled.
    This keeps ledger reports aligned with active statutory exposure.
    """
    try:
        from sales.models.sales_core import SalesInvoiceHeader
    except Exception:
        return qs

    sales_doc_types = {"invoice", "credit_note", "debit_note"}
    cancelled_sales_ids = list(
        SalesInvoiceHeader.objects.filter(status=SalesInvoiceHeader.Status.CANCELLED).values_list("id", flat=True)
    )
    if cancelled_sales_ids:
        qs = qs.exclude(
            module_name="sales",
            document_type__in=sales_doc_types,
            document_id__in=cancelled_sales_ids,
        )
    return qs


def _resolve_period_bounds(*, fy: str, quarter: str, from_date_raw: str | None, to_date_raw: str | None) -> tuple[date | None, date | None]:
    explicit_from = parse_date(str(from_date_raw or "").strip()) if from_date_raw else None
    explicit_to = parse_date(str(to_date_raw or "").strip()) if to_date_raw else None
    if explicit_from or explicit_to:
        return explicit_from, explicit_to

    fy_tokens = _expand_fy_values(fy)
    token = next((tok for tok in fy_tokens if re.match(r"^\d{4}-\d{2}$", tok or "")), None)
    if not token:
        return None, None
    start_year = int(token[:4])
    fy_start = date(start_year, 4, 1)
    fy_end = date(start_year + 1, 3, 31)
    qtr = (quarter or "").strip().upper()
    quarter_windows = {
        "Q1": (date(start_year, 4, 1), date(start_year, 6, 30)),
        "Q2": (date(start_year, 7, 1), date(start_year, 9, 30)),
        "Q3": (date(start_year, 10, 1), date(start_year, 12, 31)),
        "Q4": (date(start_year + 1, 1, 1), date(start_year + 1, 3, 31)),
    }
    return quarter_windows.get(qtr, (fy_start, fy_end))


def _runtime_quality_flags(*, section_code: str, reason_code: str, pan: str, tax_identifier: str, residency_status: str) -> dict[str, bool]:
    code = (section_code or "").strip().upper()
    reason = (reason_code or "").strip().upper()
    residency = (residency_status or "").strip().lower()
    needs_pan = code in {"194A", "194N"}
    needs_tax_id = code == "195"
    return {
        "missing_pan": bool(needs_pan and not pan),
        "missing_tax_id": bool(needs_tax_id and not tax_identifier),
        "residency_mismatch": bool((code == "195" and residency and residency != "non_resident") or (code in {"194A", "194N"} and residency == "non_resident")),
        "invalid_base_rule": reason == "INVALID_BASE_RULE",
        "missing_section": not code,
    }


def _row_readiness_status(*, amount: Decimal, flags: dict[str, bool]) -> str:
    if amount <= Decimal("0.00"):
        return "fix_now"
    blocking_keys = {"missing_tax_id", "residency_mismatch", "invalid_base_rule", "missing_section"}
    if any(bool(flags.get(k)) for k in blocking_keys):
        return "blocked"
    if bool(flags.get("missing_pan")):
        return "fix_now"
    return "ready_to_file"


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

    def perform_destroy(self, instance):
        request = self.request
        changed_by = getattr(request, "user", None) if request else None
        if changed_by is not None and not getattr(changed_by, "is_authenticated", False):
            changed_by = None
        snapshot = WithholdingSectionSerializer._policy_snapshot(instance)
        WithholdingSectionPolicyAudit.objects.create(
            section=instance,
            action=WithholdingSectionPolicyAudit.Action.DELETED,
            changed_by=changed_by,
            changed_fields_json=sorted(snapshot.keys()),
            before_snapshot_json=snapshot,
            after_snapshot_json=None,
            source="api",
        )
        instance.delete()


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


class WithholdingEntityPartyProfileListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EntityPartyTaxProfileSerializer

    def get_queryset(self):
        qs = EntityPartyTaxProfile.objects.all().order_by("-id")
        entity_id = _safe_int(self.request.query_params.get("entity_id"))
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        subentity_id = self.request.query_params.get("subentity_id")
        if subentity_id not in (None, ""):
            parsed_sub = _safe_int(subentity_id)
            if parsed_sub is None:
                qs = qs.filter(subentity__isnull=True)
            else:
                qs = qs.filter(subentity_id=parsed_sub)
        party_account_id = _safe_int(self.request.query_params.get("party_account_id"))
        if party_account_id:
            qs = qs.filter(party_account_id=party_account_id)
        is_active = self.request.query_params.get("is_active")
        if is_active not in (None, ""):
            qs = qs.filter(is_active=_safe_bool(is_active))
        return qs


class WithholdingSectionCatalogListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WithholdingSectionSerializer

    def get_queryset(self):
        qs = WithholdingSection.objects.all().order_by("tax_type", "section_code", "-effective_from")
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(section_code__icontains=q) | Q(description__icontains=q))
        tax_type = _safe_int(self.request.query_params.get("tax_type"))
        if tax_type is not None:
            qs = qs.filter(tax_type=tax_type)
        law_type = (self.request.query_params.get("law_type") or "").strip().upper()
        if law_type:
            qs = qs.filter(law_type=law_type)
        active_only = self.request.query_params.get("active_only")
        if active_only in (None, ""):
            active_only = "true"
        if _safe_bool(active_only):
            qs = qs.filter(is_active=True)
        return qs


class WithholdingSectionPolicyAuditListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WithholdingSectionPolicyAuditSerializer

    def get_queryset(self):
        qs = WithholdingSectionPolicyAudit.objects.select_related("section", "changed_by").all().order_by("-created_at", "-id")
        section_id = _safe_int(self.request.query_params.get("section_id"))
        if section_id:
            qs = qs.filter(section_id=section_id)
        tax_type = _safe_int(self.request.query_params.get("tax_type"))
        if tax_type is not None:
            qs = qs.filter(section__tax_type=tax_type)
        action = (self.request.query_params.get("action") or "").strip().upper()
        if action:
            qs = qs.filter(action=action)
        return qs


class WithholdingEntityPartyProfileRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EntityPartyTaxProfileSerializer
    queryset = EntityPartyTaxProfile.objects.all()


class WithholdingSectionPostingMapListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EntityWithholdingSectionPostingMapSerializer

    def get_queryset(self):
        qs = EntityWithholdingSectionPostingMap.objects.all().order_by("-effective_from", "-id")
        entity_id = _safe_int(self.request.query_params.get("entity_id"))
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        subentity_id = self.request.query_params.get("subentity_id")
        if subentity_id not in (None, ""):
            parsed_sub = _safe_int(subentity_id)
            if parsed_sub is None:
                qs = qs.filter(subentity__isnull=True)
            else:
                qs = qs.filter(subentity_id=parsed_sub)
        section_id = _safe_int(self.request.query_params.get("section_id"))
        if section_id:
            qs = qs.filter(section_id=section_id)
        is_active = self.request.query_params.get("is_active")
        if is_active not in (None, ""):
            qs = qs.filter(is_active=_safe_bool(is_active))
        return qs


class WithholdingSectionPostingMapRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EntityWithholdingSectionPostingMapSerializer
    queryset = EntityWithholdingSectionPostingMap.objects.all()


class WithholdingTcsThresholdOpeningListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EntityTcsThresholdOpeningSerializer

    def get_queryset(self):
        qs = EntityTcsThresholdOpening.objects.all().order_by("-effective_from", "-id")
        entity_id = _safe_int(self.request.query_params.get("entity_id"))
        if entity_id is not None:
            qs = qs.filter(entity_id=entity_id)
        entityfin_id = _safe_int(self.request.query_params.get("entityfin_id"))
        if entityfin_id is not None:
            qs = qs.filter(entityfin_id=entityfin_id)
        subentity_id = self.request.query_params.get("subentity_id")
        if subentity_id not in (None, ""):
            parsed_sub = _safe_int(subentity_id)
            if parsed_sub is None:
                qs = qs.filter(subentity__isnull=True)
            else:
                qs = qs.filter(subentity_id=parsed_sub)
        party_account_id = _safe_int(self.request.query_params.get("party_account_id"))
        if party_account_id is not None:
            qs = qs.filter(party_account_id=party_account_id)
        section_id = _safe_int(self.request.query_params.get("section_id"))
        if section_id is not None:
            qs = qs.filter(section_id=section_id)
        is_active = self.request.query_params.get("is_active")
        if is_active not in (None, ""):
            qs = qs.filter(is_active=_safe_bool(is_active))
        return qs


class WithholdingTcsThresholdOpeningRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EntityTcsThresholdOpeningSerializer
    queryset = EntityTcsThresholdOpening.objects.all()


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
        status_value = serializer.validated_data.get("status") or TcsQuarterlyReturn.Status.DRAFT
        snapshot = serializer.validated_data.get("json_snapshot")
        if (status_value == TcsQuarterlyReturn.Status.FILED and entity and fy and quarter) or (not snapshot and entity and fy and quarter):
            snapshot = _build_tcs_27eq_snapshot(entity_id=int(entity.id), fy=fy, quarter=quarter)
        if status_value == TcsQuarterlyReturn.Status.FILED:
            filing_errors = _filing_readiness_errors(snapshot or {})
            if filing_errors:
                raise ValidationError({"status": filing_errors})
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
        status_value = serializer.validated_data.get("status") or serializer.instance.status
        snapshot = serializer.validated_data.get("json_snapshot")
        if (status_value == TcsQuarterlyReturn.Status.FILED and entity and fy and quarter) or (not snapshot and entity and fy and quarter):
            snapshot = _build_tcs_27eq_snapshot(entity_id=int(entity.id), fy=fy, quarter=quarter)
        if status_value == TcsQuarterlyReturn.Status.FILED:
            filing_errors = _filing_readiness_errors(snapshot or {})
            if filing_errors:
                raise ValidationError({"status": filing_errors})
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
        include_reversed = _safe_bool(request.query_params.get("include_reversed"))
        if not include_reversed:
            qs = qs.exclude(status=TcsComputation.Status.REVERSED)
        include_draft = _safe_bool(request.query_params.get("include_draft"))
        if not include_draft:
            qs = qs.exclude(status=TcsComputation.Status.DRAFT)
        include_cancelled = _safe_bool(request.query_params.get("include_cancelled"))
        if not include_cancelled:
            qs = _exclude_cancelled_documents(qs)

        qs = qs.annotate(section_code_norm=Coalesce("section__section_code", Value("UNMAPPED")))
        out = qs.values("section_code_norm").annotate(
            doc_count=Count("id"),
            total_base=Sum("tcs_base_amount"),
            total_tcs=Sum("tcs_amount"),
        ).order_by("section_code_norm")

        return Response(list(out))


class TcsReportLedgerDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = _safe_int(request.query_params.get("entity_id"))
        if entity_id is None:
            raise ValidationError({"entity_id": ["This query param is required."]})

        section_code = (request.query_params.get("section") or "").strip().upper()
        fy = (request.query_params.get("fy") or "").strip()
        include_reversed = _safe_bool(request.query_params.get("include_reversed"))
        include_draft = _safe_bool(request.query_params.get("include_draft"))
        include_cancelled = _safe_bool(request.query_params.get("include_cancelled"))

        qs = (
            TcsComputation.objects.select_related("party_account", "section")
            .prefetch_related("collections__deposit_allocations__deposit")
            .filter(entity_id=entity_id)
            .order_by("-doc_date", "-id")
        )
        if fy:
            qs = qs.filter(fiscal_year__in=_expand_fy_values(fy))
        if not include_reversed:
            qs = qs.exclude(status=TcsComputation.Status.REVERSED)
        if not include_draft:
            qs = qs.exclude(status=TcsComputation.Status.DRAFT)
        if not include_cancelled:
            qs = _exclude_cancelled_documents(qs)
        if section_code:
            if section_code == "UNMAPPED":
                qs = qs.filter(section__isnull=True)
            else:
                qs = qs.filter(section__section_code__iexact=section_code)

        rows = []
        total_base = Decimal("0.00")
        total_tcs = Decimal("0.00")
        total_collected = Decimal("0.00")
        total_deposited = Decimal("0.00")

        for comp in qs:
            comp_base = q2(comp.tcs_base_amount or Decimal("0.00"))
            comp_tcs = q2(comp.tcs_amount or Decimal("0.00"))
            comp_collected = Decimal("0.00")
            comp_deposited = Decimal("0.00")
            challan_map = {}

            for collection in comp.collections.all():
                if collection.status == TcsCollection.Status.CANCELLED:
                    continue
                comp_collected += q2(collection.tcs_collected_amount or Decimal("0.00"))
                for alloc in collection.deposit_allocations.all():
                    alloc_amt = q2(alloc.allocated_amount or Decimal("0.00"))
                    comp_deposited += alloc_amt
                    dep = alloc.deposit
                    if dep:
                        key = dep.id
                        if key not in challan_map:
                            challan_map[key] = {
                                "id": dep.id,
                                "challan_no": dep.challan_no,
                                "challan_date": dep.challan_date,
                                "allocated_amount": Decimal("0.00"),
                            }
                        challan_map[key]["allocated_amount"] = q2(challan_map[key]["allocated_amount"] + alloc_amt)

            pending_collection = q2(comp_tcs - comp_collected)
            pending_deposit = q2(comp_collected - comp_deposited)
            challans = [
                {
                    "id": item["id"],
                    "challan_no": item["challan_no"],
                    "challan_date": item["challan_date"],
                    "allocated_amount": q2(item["allocated_amount"]),
                }
                for item in challan_map.values()
            ]

            rows.append(
                {
                    "id": comp.id,
                    "section_code": comp.section.section_code if comp.section else "UNMAPPED",
                    "document_type": comp.document_type,
                    "document_no": comp.document_no,
                    "doc_date": comp.doc_date,
                    "party_account_id": comp.party_account_id,
                    "party_name": getattr(comp.party_account, "accountname", None)
                    or getattr(comp.party_account, "legalname", None)
                    or "",
                    "pan": account_pan(comp.party_account) or getattr(comp.party_account, "pan", None) or "",
                    "status": comp.status,
                    "base_amount": comp_base,
                    "tcs_amount": comp_tcs,
                    "collected_amount": q2(comp_collected),
                    "deposited_amount": q2(comp_deposited),
                    "pending_collection": pending_collection,
                    "pending_deposit": pending_deposit,
                    "challans": challans,
                }
            )

            total_base += comp_base
            total_tcs += comp_tcs
            total_collected += q2(comp_collected)
            total_deposited += q2(comp_deposited)

        return Response(
            {
                "section": section_code or "ALL",
                "rows": rows,
                "summary": {
                    "count": len(rows),
                    "total_base": q2(total_base),
                    "total_tcs": q2(total_tcs),
                    "total_collected": q2(total_collected),
                    "total_deposited": q2(total_deposited),
                    "pending_collection": q2(total_tcs - total_collected),
                    "pending_deposit": q2(total_collected - total_deposited),
                },
            }
        )


class TcsWorkspaceTransactionsAPIView(APIView):
    """
    Operational TCS workspace:
    computation -> collection -> deposit lifecycle at transaction level.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = _safe_int(request.query_params.get("entity_id"))
        if entity_id is None:
            raise ValidationError({"entity_id": ["This query param is required."]})

        fy = (request.query_params.get("fy") or "").strip()
        quarter = (request.query_params.get("quarter") or "").strip().upper()
        from_date = parse_date((request.query_params.get("from_date") or "").strip()) if request.query_params.get("from_date") else None
        to_date = parse_date((request.query_params.get("to_date") or "").strip()) if request.query_params.get("to_date") else None
        section_code = (request.query_params.get("section") or "").strip().upper()
        customer_id = _safe_int(request.query_params.get("customer_id"))
        customer_q = (request.query_params.get("customer_q") or "").strip()
        include_reversed = _safe_bool(request.query_params.get("include_reversed"))
        include_draft = _safe_bool(request.query_params.get("include_draft"))
        include_cancelled = _safe_bool(request.query_params.get("include_cancelled"))

        qs = (
            TcsComputation.objects.select_related("party_account", "section")
            .prefetch_related("collections__deposit_allocations__deposit")
            .filter(entity_id=entity_id)
            .order_by("-doc_date", "-id")
        )

        if fy:
            qs = qs.filter(fiscal_year__in=_expand_fy_values(fy))
        if quarter:
            if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
                raise ValidationError({"quarter": ["quarter must be one of Q1/Q2/Q3/Q4."]})
            qs = qs.filter(quarter=quarter)
        if from_date:
            qs = qs.filter(doc_date__gte=from_date)
        if to_date:
            qs = qs.filter(doc_date__lte=to_date)
        if customer_id is not None:
            qs = qs.filter(party_account_id=customer_id)
        if customer_q:
            qs = qs.filter(
                Q(party_account__accountname__icontains=customer_q)
                | Q(party_account__legalname__icontains=customer_q)
            )
        if section_code:
            if section_code == "UNMAPPED":
                qs = qs.filter(section__isnull=True)
            else:
                qs = qs.filter(section__section_code__iexact=section_code)
        if not include_reversed:
            qs = qs.exclude(status=TcsComputation.Status.REVERSED)
        if not include_draft:
            qs = qs.exclude(status=TcsComputation.Status.DRAFT)
        if not include_cancelled:
            qs = _exclude_cancelled_documents(qs)

        rows = []
        party_ids = {int(comp.party_account_id) for comp in qs}
        profile_map = {
            row.party_account_id: row
            for row in EntityPartyTaxProfile.objects.filter(entity_id=entity_id, party_account_id__in=party_ids, is_active=True).order_by("-updated_at")
        }
        total_base = Decimal("0.00")
        total_computed = Decimal("0.00")
        total_collected = Decimal("0.00")
        total_deposited = Decimal("0.00")
        quality_counts = {
            "missing_pan": 0,
            "invalid_pan_format": 0,
            "missing_tax_id": 0,
            "residency_mismatch": 0,
            "missing_section": 0,
            "invalid_base_rule": 0,
            "quarter_boundary_violation": 0,
            "incomplete_compliance": 0,
        }
        status_counts = {
            "computed_pending_collection": 0,
            "partially_collected": 0,
            "collected_pending_deposit": 0,
            "deposited": 0,
            "no_computed_tcs": 0,
        }
        section_summary = {}

        for comp in qs:
            comp_base = q2(comp.tcs_base_amount or Decimal("0.00"))
            comp_tcs = q2(comp.tcs_amount or Decimal("0.00"))
            comp_collected = Decimal("0.00")
            comp_deposited = Decimal("0.00")
            collections_payload = []

            for col in comp.collections.all():
                if col.status == TcsCollection.Status.CANCELLED:
                    continue
                col_amt = q2(col.tcs_collected_amount or Decimal("0.00"))
                comp_collected += col_amt
                allocation_rows = []
                col_deposited = Decimal("0.00")
                for alloc in col.deposit_allocations.all():
                    alloc_amt = q2(alloc.allocated_amount or Decimal("0.00"))
                    dep = alloc.deposit
                    col_deposited += alloc_amt
                    comp_deposited += alloc_amt
                    allocation_rows.append(
                        {
                            "id": alloc.id,
                            "allocated_amount": alloc_amt,
                            "deposit_id": dep.id if dep else None,
                            "challan_no": dep.challan_no if dep else "",
                            "challan_date": dep.challan_date if dep else None,
                            "deposit_status": dep.status if dep else "",
                        }
                    )

                collections_payload.append(
                    {
                        "id": col.id,
                        "collection_date": col.collection_date,
                        "receipt_voucher_id": col.receipt_voucher_id,
                        "amount_received": q2(col.amount_received or Decimal("0.00")),
                        "tcs_collected_amount": col_amt,
                        "status": col.status,
                        "collection_reference": col.collection_reference,
                        "deposited_amount": q2(col_deposited),
                        "allocations": allocation_rows,
                    }
                )

            pending_collection = q2(comp_tcs - comp_collected)
            pending_deposit = q2(comp_collected - comp_deposited)
            pan_token = (account_pan(comp.party_account) or getattr(comp.party_account, "pan", None) or "").strip().upper()
            has_missing_pan = not bool(pan_token)
            has_invalid_pan_format = bool(pan_token) and not _is_valid_pan(pan_token)
            has_missing_section = comp.section_id is None
            section_upper = str(sec_code or "").strip().upper()
            profile = profile_map.get(comp.party_account_id)
            tax_identifier = str(getattr(profile, "tax_identifier", "") or "").strip()
            residency_status = str(getattr(profile, "residency_status", "") or "").strip().lower()
            has_missing_tax_id = bool(section_upper == "195" and not tax_identifier)
            has_residency_mismatch = bool(
                (section_upper == "195" and residency_status and residency_status != "non_resident")
                or (section_upper in {"194A", "194N"} and residency_status == "non_resident")
            )
            has_quarter_violation = _quarter_boundary_violation(
                doc_date=comp.doc_date,
                fiscal_year=comp.fiscal_year or "",
                quarter=comp.quarter or "",
            )
            reason_code = str(
                (comp.computation_json or {}).get("reason_code")
                or (comp.rule_snapshot_json or {}).get("reason_code")
                or ""
            ).strip().upper()
            has_invalid_base_rule = reason_code == "INVALID_BASE_RULE"
            has_incomplete = bool(
                has_missing_pan
                or has_invalid_pan_format
                or has_missing_tax_id
                or has_residency_mismatch
                or has_missing_section
                or has_invalid_base_rule
                or has_quarter_violation
            )

            if comp_tcs <= Decimal("0.00"):
                lifecycle_status = "NO_COMPUTED_TCS"
                status_counts["no_computed_tcs"] += 1
            elif q2(comp_deposited) >= comp_tcs:
                lifecycle_status = "DEPOSITED"
                status_counts["deposited"] += 1
            elif q2(comp_collected) >= comp_tcs:
                lifecycle_status = "COLLECTED_PENDING_DEPOSIT"
                status_counts["collected_pending_deposit"] += 1
            elif q2(comp_collected) > Decimal("0.00"):
                lifecycle_status = "PARTIALLY_COLLECTED"
                status_counts["partially_collected"] += 1
            else:
                lifecycle_status = "COMPUTED_PENDING_COLLECTION"
                status_counts["computed_pending_collection"] += 1

            sec_code = comp.section.section_code if comp.section else "UNMAPPED"
            bucket = section_summary.setdefault(
                sec_code,
                {
                    "section_code": sec_code,
                    "document_count": 0,
                    "total_base": Decimal("0.00"),
                    "total_computed_tcs": Decimal("0.00"),
                    "total_collected_tcs": Decimal("0.00"),
                    "total_deposited_tcs": Decimal("0.00"),
                    "pending_collection": Decimal("0.00"),
                    "pending_deposit": Decimal("0.00"),
                },
            )
            bucket["document_count"] += 1
            bucket["total_base"] = q2(bucket["total_base"] + comp_base)
            bucket["total_computed_tcs"] = q2(bucket["total_computed_tcs"] + comp_tcs)
            bucket["total_collected_tcs"] = q2(bucket["total_collected_tcs"] + q2(comp_collected))
            bucket["total_deposited_tcs"] = q2(bucket["total_deposited_tcs"] + q2(comp_deposited))
            bucket["pending_collection"] = q2(bucket["pending_collection"] + pending_collection)
            bucket["pending_deposit"] = q2(bucket["pending_deposit"] + pending_deposit)

            if has_missing_pan:
                quality_counts["missing_pan"] += 1
            if has_invalid_pan_format:
                quality_counts["invalid_pan_format"] += 1
            if has_missing_tax_id:
                quality_counts["missing_tax_id"] += 1
            if has_residency_mismatch:
                quality_counts["residency_mismatch"] += 1
            if has_missing_section:
                quality_counts["missing_section"] += 1
            if has_invalid_base_rule:
                quality_counts["invalid_base_rule"] += 1
            if has_quarter_violation:
                quality_counts["quarter_boundary_violation"] += 1
            if has_incomplete:
                quality_counts["incomplete_compliance"] += 1

            total_base += comp_base
            total_computed += comp_tcs
            total_collected += q2(comp_collected)
            total_deposited += q2(comp_deposited)

            rows.append(
                {
                    "id": comp.id,
                    "module_name": comp.module_name,
                    "voucher_type": f"{(comp.module_name or '').upper()}_{(comp.document_type or '').upper()}",
                    "voucher_date": comp.doc_date,
                    "voucher_no": comp.document_no,
                    "document_type": comp.document_type,
                    "document_id": comp.document_id,
                    "customer_id": comp.party_account_id,
                    "customer_name": (getattr(comp.party_account, "legalname", None) or getattr(comp.party_account, "accountname", None) or "").strip(),
                    "pan": pan_token,
                    "section_id": comp.section_id,
                    "section_code": sec_code,
                    "base_amount": comp_base,
                    "rate": q2(comp.rate or Decimal("0.00")),
                    "computed_tcs": comp_tcs,
                    "collected_tcs": q2(comp_collected),
                    "deposited_tcs": q2(comp_deposited),
                    "pending_collection": pending_collection,
                    "pending_deposit": pending_deposit,
                    "flags": {
                        "computed": bool(comp_tcs > Decimal("0.00")),
                        "collected": bool(comp_collected > Decimal("0.00")),
                        "deposited": bool(comp_deposited > Decimal("0.00")),
                        "pending": bool(pending_collection > Decimal("0.00") or pending_deposit > Decimal("0.00")),
                        "missing_pan": has_missing_pan,
                        "invalid_pan_format": has_invalid_pan_format,
                        "missing_tax_id": has_missing_tax_id,
                        "residency_mismatch": has_residency_mismatch,
                        "missing_section": has_missing_section,
                        "invalid_base_rule": has_invalid_base_rule,
                        "quarter_boundary_violation": has_quarter_violation,
                        "incomplete_compliance": has_incomplete,
                    },
                    "lifecycle_status": lifecycle_status,
                    "computation_status": comp.status,
                    "collections": collections_payload,
                }
            )

        unallocated_deposits = []
        deposits_qs = TcsDeposit.objects.filter(entity_id=entity_id)
        if fy:
            deposits_qs = deposits_qs.filter(financial_year__in=_expand_fy_values(fy))
        if quarter in {"Q1", "Q2", "Q3", "Q4"}:
            deposits_qs = deposits_qs.filter(month__in=TcsReportFilingPackAPIView._quarter_months(quarter))
        if from_date:
            deposits_qs = deposits_qs.filter(challan_date__gte=from_date)
        if to_date:
            deposits_qs = deposits_qs.filter(challan_date__lte=to_date)

        for dep in deposits_qs.order_by("-challan_date", "-id"):
            allocated = q2(dep.allocations.aggregate(v=Sum("allocated_amount")).get("v") or Decimal("0.00"))
            remaining = q2(q2(dep.total_deposit_amount or Decimal("0.00")) - allocated)
            if remaining > Decimal("0.00"):
                unallocated_deposits.append(
                    {
                        "id": dep.id,
                        "challan_no": dep.challan_no,
                        "challan_date": dep.challan_date,
                        "status": dep.status,
                        "total_deposit_amount": q2(dep.total_deposit_amount or Decimal("0.00")),
                        "allocated_amount": allocated,
                        "unallocated_amount": remaining,
                    }
                )

        return Response(
            {
                "filters": {
                    "entity_id": entity_id,
                    "fy": fy or None,
                    "quarter": quarter or None,
                    "from_date": from_date,
                    "to_date": to_date,
                    "section": section_code or None,
                    "customer_id": customer_id,
                    "customer_q": customer_q or None,
                    "include_reversed": include_reversed,
                    "include_draft": include_draft,
                    "include_cancelled": include_cancelled,
                },
                "summary": {
                    "total_transactions": len(rows),
                    "total_base": q2(total_base),
                    "total_computed_tcs": q2(total_computed),
                    "total_collected_tcs": q2(total_collected),
                    "total_deposited_tcs": q2(total_deposited),
                    "pending_collection": q2(total_computed - total_collected),
                    "pending_deposit": q2(total_collected - total_deposited),
                    "status_counts": status_counts,
                    "quality_counts": quality_counts,
                    "unallocated_deposit_count": len(unallocated_deposits),
                    "unallocated_deposit_amount": q2(sum((r["unallocated_amount"] for r in unallocated_deposits), Decimal("0.00"))),
                },
                "section_summary": list(section_summary.values()),
                "rows": rows,
                "unallocated_deposits": unallocated_deposits,
            }
        )


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
        party_ids = {int(row.party_account_id) for row in computations}
        profile_map = {
            row.party_account_id: row
            for row in EntityPartyTaxProfile.objects.filter(entity_id=entity_id, party_account_id__in=party_ids, is_active=True).order_by("-updated_at")
        }

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
            pan = (account_pan(party) or getattr(party, "pan", None) or "").strip().upper()
            invalid_pan_format = bool(pan) and not _is_valid_pan(pan)
            profile = profile_map.get(comp.party_account_id)
            residency_status = str(getattr(profile, "residency_status", "") or "").strip().lower()
            tax_identifier = str(getattr(profile, "tax_identifier", "") or "").strip()
            section_upper = str(getattr(section, "section_code", "") or "").strip().upper()
            missing_tax_id = bool(section_upper == "195" and not tax_identifier)
            residency_mismatch = bool(
                (section_upper == "195" and residency_status and residency_status != "non_resident")
                or (section_upper in {"194A", "194N"} and residency_status == "non_resident")
            )
            quarter_boundary_violation = _quarter_boundary_violation(
                doc_date=comp.doc_date,
                fiscal_year=comp.fiscal_year or "",
                quarter=comp.quarter or "",
            )

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
                        "invalid_pan_format": invalid_pan_format,
                        "missing_tax_id": missing_tax_id,
                        "residency_mismatch": residency_mismatch,
                        "missing_section": comp.section_id is None,
                        "not_collected": comp_collected_total <= Decimal("0.00"),
                        "not_deposited": comp_alloc_total <= Decimal("0.00"),
                        "partially_allocated": comp_alloc_total > Decimal("0.00") and comp_alloc_total < q2(comp.tcs_amount or Decimal("0.00")),
                        "deposit_mismatch": q2(comp_alloc_total) != q2(comp_collected_total),
                        "quarter_boundary_violation": quarter_boundary_violation,
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


class TcsWorkspaceTransactionsExportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = TcsWorkspaceTransactionsAPIView().get(request).data
        rows = payload.get("rows") or []
        section_summary = payload.get("section_summary") or []
        unallocated = payload.get("unallocated_deposits") or []
        summary = payload.get("summary") or {}
        filters = payload.get("filters") or {}

        tx_rows = [
            {
                "voucher_date": row.get("voucher_date"),
                "voucher_type": row.get("voucher_type"),
                "voucher_no": row.get("voucher_no"),
                "customer_name": row.get("customer_name"),
                "pan": row.get("pan"),
                "section_code": row.get("section_code"),
                "base_amount": row.get("base_amount"),
                "rate": row.get("rate"),
                "computed_tcs": row.get("computed_tcs"),
                "collected_tcs": row.get("collected_tcs"),
                "deposited_tcs": row.get("deposited_tcs"),
                "pending_collection": row.get("pending_collection"),
                "pending_deposit": row.get("pending_deposit"),
                "lifecycle_status": row.get("lifecycle_status"),
                "incomplete_compliance": (row.get("flags") or {}).get("incomplete_compliance"),
            }
            for row in rows
        ]
        meta_rows = [{"key": k, "value": v} for k, v in {**filters, **summary}.items()]
        zip_bytes = _zip_csv_payload(
            {
                "workspace_transactions.csv": tx_rows,
                "workspace_section_summary.csv": section_summary,
                "workspace_unallocated_deposits.csv": unallocated,
                "workspace_meta.csv": meta_rows,
            }
        )
        resp = HttpResponse(zip_bytes, content_type="application/zip")
        resp["Content-Disposition"] = "attachment; filename=tcs_workspace_export.zip"
        return resp


class TcsReportFilingPackExportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = TcsReportFilingPackAPIView().get(request).data
        rows = payload.get("rows") or []
        section_summary = payload.get("section_summary") or []
        header = payload.get("header") or {}

        filing_rows = []
        for row in rows:
            exc = row.get("exceptions") or {}
            filing_rows.append(
                {
                    "doc_date": row.get("doc_date"),
                    "document_type": row.get("document_type"),
                    "document_no": row.get("document_no"),
                    "party_name": row.get("party_name"),
                    "pan": row.get("pan"),
                    "section_code": row.get("section_code"),
                    "taxable_base": row.get("taxable_base"),
                    "tcs_rate": row.get("tcs_rate"),
                    "tcs_amount": row.get("tcs_amount"),
                    "tcs_collected_amount": row.get("tcs_collected_amount"),
                    "allocated_amount": row.get("allocated_amount"),
                    "return_status": row.get("return_status"),
                    "missing_pan": exc.get("missing_pan"),
                    "invalid_pan_format": exc.get("invalid_pan_format"),
                    "missing_tax_id": exc.get("missing_tax_id"),
                    "residency_mismatch": exc.get("residency_mismatch"),
                    "missing_section": exc.get("missing_section"),
                    "not_collected": exc.get("not_collected"),
                    "not_deposited": exc.get("not_deposited"),
                    "partially_allocated": exc.get("partially_allocated"),
                    "deposit_mismatch": exc.get("deposit_mismatch"),
                    "quarter_boundary_violation": exc.get("quarter_boundary_violation"),
                    "reversal_case": exc.get("reversal_case"),
                }
            )
        header_rows = [{"key": k, "value": v} for k, v in header.items()]
        zip_bytes = _zip_csv_payload(
            {
                "filing_pack_transactions.csv": filing_rows,
                "filing_pack_section_summary.csv": section_summary,
                "filing_pack_header.csv": header_rows,
            }
        )
        resp = HttpResponse(zip_bytes, content_type="application/zip")
        resp["Content-Disposition"] = "attachment; filename=tcs_filing_pack_export.zip"
        return resp


class WithholdingReadinessDashboardAPIView(APIView):
    """
    Unified compliance-readiness summary for payment-triggered withholding (TDS runtime).
    Focus buckets: 194A, 194N, 195.
    """

    permission_classes = [IsAuthenticated]
    TARGET_SECTIONS = {"194A", "194N", "195"}

    def get(self, request):
        entity_id = _safe_int(request.query_params.get("entity_id") or request.query_params.get("entity"))
        if entity_id is None:
            raise ValidationError({"entity_id": ["This query param is required."]})

        entityfin_id = _safe_int(request.query_params.get("entityfinid") or request.query_params.get("entityfin_id"))
        subentity_id = _safe_int(request.query_params.get("subentity_id") or request.query_params.get("subentity"))
        fy = (request.query_params.get("fy") or "").strip()
        quarter = (request.query_params.get("quarter") or "").strip().upper()
        from_date, to_date = _resolve_period_bounds(
            fy=fy,
            quarter=quarter,
            from_date_raw=request.query_params.get("from_date"),
            to_date_raw=request.query_params.get("to_date"),
        )
        include_all_sections = _safe_bool(request.query_params.get("include_all_sections"))

        vouchers = PaymentVoucherHeader.objects.filter(entity_id=entity_id).exclude(
            status=PaymentVoucherHeader.Status.CANCELLED
        )
        if entityfin_id is not None:
            vouchers = vouchers.filter(entityfinid_id=entityfin_id)
        if subentity_id is not None:
            vouchers = vouchers.filter(subentity_id=subentity_id)
        if from_date:
            vouchers = vouchers.filter(voucher_date__gte=from_date)
        if to_date:
            vouchers = vouchers.filter(voucher_date__lte=to_date)

        voucher_rows = list(
            vouchers.select_related("paid_to").only(
                "id",
                "entity_id",
                "entityfinid_id",
                "subentity_id",
                "voucher_date",
                "doc_code",
                "doc_no",
                "status",
                "paid_to_id",
                "workflow_payload",
            ).order_by("-voucher_date", "-id")
        )

        section_ids = set()
        party_ids = set()
        for voucher in voucher_rows:
            party_ids.add(voucher.paid_to_id)
            payload = voucher.workflow_payload if isinstance(voucher.workflow_payload, dict) else {}
            runtime = payload.get("withholding_runtime_result") if isinstance(payload.get("withholding_runtime_result"), dict) else {}
            section_id = _safe_int(runtime.get("section_id")) or _safe_int((payload.get("withholding") or {}).get("section_id"))
            if section_id:
                section_ids.add(section_id)

        section_map = {
            row.id: row
            for row in WithholdingSection.objects.filter(id__in=section_ids).only("id", "section_code", "description")
        }
        profile_map = {
            row.party_account_id: row
            for row in EntityPartyTaxProfile.objects.filter(entity_id=entity_id, party_account_id__in=party_ids, is_active=True).order_by("-updated_at")
        }

        rows: list[dict] = []
        quality_counts = {
            "missing_pan": 0,
            "missing_tax_id": 0,
            "residency_mismatch": 0,
            "invalid_base_rule": 0,
            "missing_section": 0,
        }
        status_counts = {"ready_to_file": 0, "blocked": 0, "fix_now": 0}
        section_buckets: dict[str, dict] = {}
        total_amount = Decimal("0.00")

        for voucher in voucher_rows:
            payload = voucher.workflow_payload if isinstance(voucher.workflow_payload, dict) else {}
            runtime = payload.get("withholding_runtime_result") if isinstance(payload.get("withholding_runtime_result"), dict) else {}
            withholding_cfg = payload.get("withholding") if isinstance(payload.get("withholding"), dict) else {}
            section_id = _safe_int(runtime.get("section_id")) or _safe_int(withholding_cfg.get("section_id"))
            section_obj = section_map.get(section_id) if section_id else None
            section_code = str(getattr(section_obj, "section_code", "") or "").strip().upper()
            if not include_all_sections and section_code and section_code not in self.TARGET_SECTIONS:
                continue
            if not include_all_sections and not section_code:
                continue

            amount = _safe_decimal(runtime.get("amount"))
            base_amount = _safe_decimal(runtime.get("base_amount"))
            rate = _safe_decimal(runtime.get("rate"))
            reason_code = str(runtime.get("reason_code") or "")
            reason = str(runtime.get("reason") or "")
            mode = str(runtime.get("mode") or withholding_cfg.get("mode") or "AUTO").upper().strip()
            enabled = bool(runtime.get("enabled", withholding_cfg.get("enabled", False)))
            pan = (account_pan(voucher.paid_to) or getattr(voucher.paid_to, "pan", None) or "").strip().upper()
            profile = profile_map.get(voucher.paid_to_id)
            residency_status = str(getattr(profile, "residency_status", "") or "").strip().lower()
            tax_identifier = str(getattr(profile, "tax_identifier", "") or "").strip()

            flags = _runtime_quality_flags(
                section_code=section_code,
                reason_code=reason_code,
                pan=pan,
                tax_identifier=tax_identifier,
                residency_status=residency_status,
            )
            row_status = _row_readiness_status(amount=amount, flags=flags)
            status_counts[row_status] += 1
            for key in quality_counts.keys():
                if flags.get(key):
                    quality_counts[key] += 1

            bucket_key = section_code or "UNMAPPED"
            if bucket_key not in section_buckets:
                section_buckets[bucket_key] = {
                    "section_code": bucket_key,
                    "section_description": getattr(section_obj, "description", "") if section_obj else "",
                    "voucher_count": 0,
                    "total_base": Decimal("0.00"),
                    "total_amount": Decimal("0.00"),
                    "ready_to_file": 0,
                    "blocked": 0,
                    "fix_now": 0,
                }
            bucket = section_buckets[bucket_key]
            bucket["voucher_count"] += 1
            bucket["total_base"] = q2(bucket["total_base"] + base_amount)
            bucket["total_amount"] = q2(bucket["total_amount"] + amount)
            bucket[row_status] += 1
            total_amount = q2(total_amount + amount)

            rows.append(
                {
                    "source": "payment_voucher",
                    "voucher_id": voucher.id,
                    "voucher_date": voucher.voucher_date,
                    "voucher_no": f"{voucher.doc_code}-{voucher.doc_no}" if voucher.doc_no else voucher.doc_code,
                    "status": voucher.status,
                    "party_account_id": voucher.paid_to_id,
                    "section_id": section_id,
                    "section_code": section_code,
                    "mode": mode,
                    "enabled": enabled,
                    "base_amount": base_amount,
                    "rate": rate,
                    "withholding_amount": amount,
                    "reason_code": reason_code,
                    "reason": reason,
                    "pan": pan,
                    "tax_identifier": tax_identifier,
                    "residency_status": residency_status or "unknown",
                    "quality_flags": flags,
                    "readiness_status": row_status,
                }
            )

        section_summary = sorted(section_buckets.values(), key=lambda row: row.get("section_code") or "")
        return Response(
            {
                "filters": {
                    "entity_id": entity_id,
                    "entityfinid": entityfin_id,
                    "subentity_id": subentity_id,
                    "fy": fy or None,
                    "quarter": quarter or None,
                    "from_date": from_date,
                    "to_date": to_date,
                    "include_all_sections": include_all_sections,
                },
                "header": {
                    "target_sections": sorted(self.TARGET_SECTIONS),
                    "row_count": len(rows),
                    "total_withholding_amount": total_amount,
                },
                "widgets": {
                    "ready_to_file": status_counts["ready_to_file"],
                    "blocked_items": status_counts["blocked"],
                    "fix_now_items": status_counts["fix_now"],
                },
                "quality_flags": quality_counts,
                "section_summary": section_summary,
                "rows": rows,
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
    party_ids = {int(comp.party_account_id) for comp in computations}
    profile_map = {
        row.party_account_id: row
        for row in EntityPartyTaxProfile.objects.filter(
            entity_id=entity_id,
            party_account_id__in=party_ids,
            is_active=True,
        ).order_by("-updated_at")
    }
    deposits = TcsDeposit.objects.filter(entity_id=entity_id, financial_year__in=fy_candidates, month__in=months)

    total_base = q2(computations.aggregate(v=Sum("tcs_base_amount")).get("v") or Decimal("0.00"))
    total_tcs = q2(computations.aggregate(v=Sum("tcs_amount")).get("v") or Decimal("0.00"))
    total_collected = q2(
        TcsCollection.objects.filter(computation__in=computations).exclude(status=TcsCollection.Status.CANCELLED).aggregate(v=Sum("tcs_collected_amount")).get("v")
        or Decimal("0.00")
    )
    total_deposited = q2(deposits.aggregate(v=Sum("total_deposit_amount")).get("v") or Decimal("0.00"))

    missing_pan_count = 0
    invalid_pan_format_count = 0
    missing_section_count = 0
    missing_tax_id_count = 0
    residency_mismatch_count = 0
    quarter_boundary_violation_count = 0
    not_collected_count = 0
    not_deposited_count = 0
    partially_allocated_count = 0
    deposit_mismatch_count = 0

    for comp in computations:
        pan = (account_pan(comp.party_account) or getattr(comp.party_account, "pan", None) or "").strip().upper()
        if not pan:
            missing_pan_count += 1
        elif not _is_valid_pan(pan):
            invalid_pan_format_count += 1
        if not comp.section_id:
            missing_section_count += 1
        section_upper = str(getattr(comp.section, "section_code", "") or "").strip().upper()
        party_profile = profile_map.get(comp.party_account_id)
        residency_status = str(getattr(party_profile, "residency_status", "") or "").strip().lower()
        tax_identifier = str(getattr(party_profile, "tax_identifier", "") or "").strip()
        if section_upper == "195" and not tax_identifier:
            missing_tax_id_count += 1
        if (section_upper == "195" and residency_status and residency_status != "non_resident") or (
            section_upper in {"194A", "194N"} and residency_status == "non_resident"
        ):
            residency_mismatch_count += 1
        if _quarter_boundary_violation(doc_date=comp.doc_date, fiscal_year=comp.fiscal_year or "", quarter=comp.quarter or ""):
            quarter_boundary_violation_count += 1

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
            "invalid_pan_format": invalid_pan_format_count,
            "missing_tax_id": missing_tax_id_count,
            "residency_mismatch": residency_mismatch_count,
            "quarter_boundary_violation": quarter_boundary_violation_count,
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
