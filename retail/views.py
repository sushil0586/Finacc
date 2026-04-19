from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import Godown

from .models import RetailCloseBatch, RetailConfig, RetailSession, RetailTicket
from .serializers import (
    RetailCloseBatchDetailSerializer,
    RetailCloseBatchReadSerializer,
    RetailConfigReadSerializer,
    RetailSessionReadSerializer,
    RetailTicketReadSerializer,
    RetailTicketWriteSerializer,
)
from .services import RetailSessionService, RetailTicketCompletionService


class RetailMetaAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id = int(request.query_params.get("entity"))
        subentity_id = request.query_params.get("subentity")
        config = RetailConfig.objects.filter(entity_id=entity_id)
        godowns = Godown.objects.filter(entity_id=entity_id, is_active=True)
        if subentity_id not in (None, ""):
            subentity_value = int(subentity_id)
            config = config.filter(Q(subentity_id=subentity_value) | Q(subentity__isnull=True)).order_by("-subentity_id")
            godowns = godowns.filter(Q(subentity_id=subentity_value) | Q(subentity__isnull=True))
        else:
            config = config.filter(subentity__isnull=True)
            godowns = godowns.filter(subentity__isnull=True)

        selected = config.first()
        location_id = request.query_params.get("location")
        current_session = RetailSessionService.get_open_session(
            entity_id=entity_id,
            subentity_id=(int(subentity_id) if subentity_id not in (None, "") else None),
            location_id=(int(location_id) if location_id not in (None, "") else None),
        )
        return Response(
            {
                "config": RetailConfigReadSerializer(selected).data if selected else None,
                "current_session": RetailSessionReadSerializer(current_session).data if current_session else None,
                "billing_modes": [{"value": value, "label": label} for value, label in RetailConfig.BillingMode.choices],
                "posting_modes": [{"value": value, "label": label} for value, label in RetailConfig.PostingMode.choices],
                "customer_modes": [{"value": value, "label": label} for value, label in RetailConfig.CustomerMode.choices],
                "walk_in_capture_modes": [{"value": value, "label": label} for value, label in RetailConfig.WalkInCaptureMode.choices],
                "execution_statuses": [{"value": value, "label": label} for value, label in RetailTicket.ExecutionStatus.choices],
                "locations": [
                    {"id": row.id, "name": row.name, "code": row.code, "display_name": row.display_name, "is_default": row.is_default}
                    for row in godowns.order_by("name")
                ],
                "status_choices": [{"value": value, "label": label} for value, label in RetailTicket.Status.choices],
            }
        )


class RetailTicketListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id = int(self.request.query_params.get("entity"))
        subentity_id = self.request.query_params.get("subentity")
        queryset = RetailTicket.objects.filter(entity_id=entity_id).select_related("location", "customer", "session").prefetch_related("lines")
        if subentity_id in (None, ""):
            return queryset.filter(subentity__isnull=True).order_by("-bill_date", "-id")[:25]
        return queryset.filter(subentity_id=int(subentity_id)).order_by("-bill_date", "-id")[:25]

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return RetailTicketReadSerializer
        return RetailTicketWriteSerializer

    def list(self, request, *args, **kwargs):
        serializer = RetailTicketReadSerializer(self.get_queryset(), many=True)
        return Response({"rows": serializer.data})

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save()
        return Response(RetailTicketReadSerializer(ticket).data, status=201)


class RetailTicketDetailAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    queryset = RetailTicket.objects.select_related("location", "customer", "session").prefetch_related("lines")

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return RetailTicketReadSerializer
        return RetailTicketWriteSerializer

    def update(self, request, *args, **kwargs):
        ticket = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        serializer = self.get_serializer(ticket, data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(RetailTicketReadSerializer(updated).data)


class RetailTicketCompleteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        ticket = get_object_or_404(
            RetailTicket.objects.select_related("location", "customer", "session").prefetch_related("lines"),
            pk=pk,
        )
        completed = RetailTicketCompletionService.complete(ticket, user=request.user)
        completed = RetailTicket.objects.select_related("location", "customer", "session").prefetch_related("lines").get(pk=completed.pk)
        return Response(RetailTicketReadSerializer(completed).data)


class RetailSessionOpenAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        entity_id = int(request.data.get("entity"))
        entityfin_id = request.data.get("entityfinid")
        subentity_id = request.data.get("subentity")
        location_id = request.data.get("location")
        session_date = request.data.get("session_date")
        opening_note = request.data.get("opening_note", "")
        session = RetailSessionService.open_session(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            location_id=location_id,
            session_date=session_date,
            opening_note=opening_note,
            user=request.user,
        )
        return Response(RetailSessionReadSerializer(session).data, status=201)


class RetailSessionCloseAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        session = get_object_or_404(
            RetailSession.objects.select_related("location", "close_batch").prefetch_related("tickets"),
            pk=pk,
        )
        closed = RetailSessionService.close_session(
            session,
            closing_note=request.data.get("closing_note", ""),
            user=request.user,
        )
        closed = RetailSession.objects.select_related("location", "close_batch").prefetch_related("tickets").get(pk=closed.pk)
        return Response(RetailSessionReadSerializer(closed).data)


class RetailCloseBatchListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RetailCloseBatchReadSerializer

    def get_queryset(self):
        entity_id = int(self.request.query_params.get("entity"))
        subentity_id = self.request.query_params.get("subentity")
        location_id = self.request.query_params.get("location")
        queryset = RetailCloseBatch.objects.filter(entity_id=entity_id).select_related("session", "location")
        if subentity_id in (None, ""):
            queryset = queryset.filter(subentity__isnull=True)
        else:
            queryset = queryset.filter(subentity_id=int(subentity_id))
        if location_id not in (None, ""):
            queryset = queryset.filter(location_id=int(location_id))
        return queryset.order_by("-created_at", "-id")[:25]

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({"rows": serializer.data})


class RetailCloseBatchDetailAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RetailCloseBatchDetailSerializer
    queryset = (
        RetailCloseBatch.objects.select_related("session", "location")
        .prefetch_related("ticket_links__ticket__customer")
    )
