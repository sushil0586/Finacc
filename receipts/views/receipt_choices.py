from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from receipts.services.receipt_choice_service import ReceiptChoiceService


class ReceiptCompiledChoicesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _parse_int(raw_value):
        if raw_value in (None, "", "null", "None"):
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def get(self, request):
        entity_id = self._parse_int(request.query_params.get("entity_id", request.query_params.get("entity")))
        subentity_id = self._parse_int(request.query_params.get("subentity_id", request.query_params.get("subentity")))
        if subentity_id == 0:
            subentity_id = None
        return Response(ReceiptChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id))
