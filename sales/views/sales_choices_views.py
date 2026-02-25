from __future__ import annotations

from rest_framework.views import APIView
from rest_framework.response import Response

from sales.services.sales_choices_service import SalesChoicesService


class SalesChoicesAPIView(APIView):
    def get(self, request):
        entity_id = request.query_params.get("entity_id")
        subentity_id = request.query_params.get("subentity_id")
        data = SalesChoicesService.get_choices(
            entity_id=int(entity_id),
            subentity_id=int(subentity_id) if subentity_id else None,
        )
        return Response(data)
