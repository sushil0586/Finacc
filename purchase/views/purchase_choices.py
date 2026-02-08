from __future__ import annotations

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers

from purchase.services.purchase_choice_service import PurchaseChoiceService


class PurchaseCompiledChoicesAPIView(APIView):
    """
    GET /api/purchase/choices/?entity=100&subentity=68

    Response:
    {
      "SupplyCategory": [{"value":1,"key":"DOMESTIC","label":"Domestic","enabled":true}, ...],
      "Taxability": [...],
      ...
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity = request.query_params.get("entity")
        subentity = request.query_params.get("subentity", None)

        if not entity:
            raise serializers.ValidationError({"entity": "entity query param is required"})

        entity_id = int(entity)
        if subentity in (None, "", "null", "None"):
            subentity_id = None
        else:
            subentity_id = int(subentity)

        data = PurchaseChoiceService.compile_choices(entity_id=entity_id, subentity_id=subentity_id)
        return Response(data)
