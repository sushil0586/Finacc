from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.services.payment_choice_service import PaymentChoiceService


class PaymentCompiledChoicesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_raw = request.query_params.get("entity_id", request.query_params.get("entity"))
        subentity_raw = request.query_params.get("subentity_id", request.query_params.get("subentity"))
        entity_id = int(entity_raw) if entity_raw not in (None, "", "null", "None") else None
        subentity_id = int(subentity_raw) if subentity_raw not in (None, "", "null", "None") else None
        if subentity_id == 0:
            subentity_id = None
        return Response(PaymentChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id))
